"""Process-lifetime Windows lock for one fahmm writer per local data root."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import BinaryIO, Self


class AlreadyRunningError(RuntimeError):
    pass


class SingleInstanceLock:
    def __init__(self, data_root: Path) -> None:
        self.data_root = Path(data_root)
        self._file: BinaryIO | None = None

    def acquire(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("The fahmm instance lock requires Windows")
        if self._file is not None:
            raise RuntimeError("This instance lock is already held")
        import msvcrt

        self.data_root.mkdir(parents=True, exist_ok=True)
        handle = (self.data_root / ".instance.lock").open("a+b")
        try:
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise AlreadyRunningError("fahmm is already open for this local data folder") from exc
            self._file = handle
        except Exception:
            handle.close()
            raise

    def release(self) -> None:
        handle = self._file
        if handle is None:
            return
        import msvcrt

        try:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self._file = None
            handle.close()

    def __enter__(self) -> Self:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
