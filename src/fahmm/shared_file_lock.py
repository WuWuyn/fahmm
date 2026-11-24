"""Shared/exclusive OS locks for cooperative local processes.

Lock files must live outside the data directory protected by the lock and must
never be replaced or unlinked: on POSIX a new inode would create a new lock.
Each process needs its own acquisition. Locks are released on handle close or
process exit; they do not protect against applications that ignore the lock.
"""

from __future__ import annotations

import errno
import math
import os
import re
import threading
import time
from pathlib import Path
from typing import Self

if os.name == "nt":
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _lock_file = _kernel32.LockFileEx
    _lock_file.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    )
    _lock_file.restype = wintypes.BOOL
    _unlock_file = _kernel32.UnlockFileEx
    _unlock_file.argtypes = (
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    )
    _unlock_file.restype = wintypes.BOOL
else:
    import fcntl


def _live_lock_path(root: Path, kind: str, identifier: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Invalid live resource ID")
    root = Path(root).resolve()
    directory = root / ".live-locks"
    if directory.is_symlink():
        raise ValueError("Live lock directory must not be a symbolic link")
    directory.mkdir(parents=True, exist_ok=True)
    if directory.resolve().parent != root:
        raise ValueError("Live lock directory must remain inside its root")
    return directory / f"{kind}-{identifier}.lock"


def live_meeting_lock_path(root: Path, meeting_id: str) -> Path:
    """Stable lock outside the individual meeting directory; never remove it."""
    return _live_lock_path(root, "meeting", meeting_id)


def live_model_lock_path(root: Path, model_id: str) -> Path:
    """Stable lock outside the individual model directory; never remove it."""
    return _live_lock_path(root, "model", model_id)


def _try_lock(fd: int, shared: bool, overlapped: object | None) -> bool:
    if os.name == "nt":
        flags = 0x00000001 | (0 if shared else 0x00000002)  # FAIL_IMMEDIATELY, EXCLUSIVE
        handle = msvcrt.get_osfhandle(fd)
        if _lock_file(handle, flags, 0, 1, 0, ctypes.byref(overlapped)):
            return True
        error = ctypes.get_last_error()
        if error == 33:  # ERROR_LOCK_VIOLATION: conflicting lock
            return False
        raise ctypes.WinError(error)
    try:
        fcntl.flock(fd, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
            return False
        raise
    return True


def _unlock(fd: int, overlapped: object | None) -> None:
    if os.name == "nt":
        if not _unlock_file(msvcrt.get_osfhandle(fd), 0, 1, 0, ctypes.byref(overlapped)):
            raise ctypes.WinError(ctypes.get_last_error())
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


class SharedFileLock:
    """A lock handle that can be released by a different thread in the owner process.

    Each successful acquire requires one release. Separate processes must open
    and acquire their own handles; an inherited handle is not a new acquisition.
    """

    def __init__(self, path: Path, *, shared: bool) -> None:
        if type(shared) is not bool:
            raise TypeError("shared must be a boolean")
        self.path = Path(path)
        self.shared = shared
        self._state_lock = threading.Lock()
        self._fd: int | None = None
        self._overlapped = None

    def acquire(self, *, timeout: float = 10.0, cancel=None) -> None:
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("timeout must be a finite non-negative number")
        with self._state_lock:
            if self._fd is not None:
                raise RuntimeError("This lock handle is already acquired")
            if cancel is not None and cancel.is_set():
                raise InterruptedError("Lock acquisition cancelled")
            flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
            fd = os.open(self.path, flags, 0o600)
            locked = False
            overlapped = _Overlapped() if os.name == "nt" else None
            deadline = time.monotonic() + timeout
            try:
                while True:
                    if cancel is not None and cancel.is_set():
                        raise InterruptedError("Lock acquisition cancelled")
                    if _try_lock(fd, self.shared, overlapped):
                        locked = True
                        if cancel is not None and cancel.is_set():
                            raise InterruptedError("Lock acquisition cancelled")
                        self._fd = fd
                        self._overlapped = overlapped
                        return
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError("File lock is busy")
                    delay = min(0.05, remaining)
                    if cancel is None:
                        time.sleep(delay)
                    else:
                        cancel.wait(delay)
            except BaseException:
                self._fd = None
                self._overlapped = None
                try:
                    if locked:
                        _unlock(fd, overlapped)
                finally:
                    os.close(fd)
                raise

    def release(self) -> None:
        with self._state_lock:
            if self._fd is None:
                return
            fd, overlapped = self._fd, self._overlapped
            self._fd = None
            self._overlapped = None
            try:
                _unlock(fd, overlapped)
            finally:
                os.close(fd)

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *_args: object) -> None:
        self.release()
