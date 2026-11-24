"""Short-lived, reentrant advisory locks for local app data."""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_registry_lock = threading.Lock()
_locks: dict[str, threading.RLock] = {}
_thread_state = threading.local()


@contextmanager
def exclusive_file_lock(
    path: Path, *, timeout: float = 10.0, cancel: threading.Event | None = None
):
    """Serialize cooperating threads and processes; the OS releases on process exit."""
    key = os.path.normcase(os.path.abspath(path))
    with _registry_lock:
        local_lock = _locks.setdefault(key, threading.RLock())
    deadline = time.monotonic() + timeout
    while True:
        if cancel is not None and cancel.is_set():
            raise InterruptedError("Local work was cancelled while waiting for a lock")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Local meeting data is busy; try again")
        if local_lock.acquire(timeout=min(0.05, remaining)):
            break
    try:
        held = getattr(_thread_state, "held", None)
        if held is None:
            held = _thread_state.held = set()
        if key in held:
            yield
            return
        if path.is_symlink():
            raise ValueError("Refusing to lock through a symbolic link")
        with path.open("a+b") as file:
            if os.name == "nt":
                import msvcrt

                file.seek(0, os.SEEK_END)
                if not file.tell():
                    file.write(b"\0")
                    file.flush()

                def lock() -> None:
                    file.seek(0)
                    msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)

                def unlock() -> None:
                    file.seek(0)
                    msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                def lock() -> None:
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

                def unlock() -> None:
                    fcntl.flock(file.fileno(), fcntl.LOCK_UN)

            while True:
                if cancel is not None and cancel.is_set():
                    raise InterruptedError("Local work was cancelled while waiting for a lock")
                try:
                    lock()
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Local meeting data is busy; try again") from None
                    time.sleep(0.05)
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                unlock()
    finally:
        local_lock.release()
