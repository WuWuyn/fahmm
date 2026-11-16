"""Exact-scope meeting deletion with a retryable tombstone."""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from fahmm.storage import MeetingStore


class DeletionIncompleteError(RuntimeError):
    def __init__(self, meeting_id: str) -> None:
        self.meeting_id = meeting_id
        super().__init__(
            f"Meeting data remains in pending cleanup for {meeting_id}; retry deletion cleanup"
        )


def _is_reparse(path: Path) -> bool:
    info = path.lstat()
    attribute = getattr(info, "st_file_attributes", 0)
    return stat.S_ISLNK(info.st_mode) or bool(
        attribute & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _assert_safe_tree(path: Path) -> None:
    if _is_reparse(path):
        raise ValueError(f"Refusing to traverse a link or reparse point: {path.name}")
    if path.is_dir():
        with os.scandir(path) as entries:
            for entry in entries:
                _assert_safe_tree(Path(entry.path))


def _remove_tree(path: Path) -> None:
    if _is_reparse(path):
        raise ValueError(f"Refusing to traverse a link or reparse point: {path.name}")
    if path.is_dir():
        with os.scandir(path) as entries:
            for entry in entries:
                _remove_tree(Path(entry.path))
        path.rmdir()
    else:
        path.unlink()


class MeetingDeletionService:
    def __init__(self, meetings: MeetingStore) -> None:
        self.meetings = meetings

    def _tombstone(self, meeting_id: str) -> Path:
        self.meetings._meeting_dir(meeting_id)
        return self.meetings.root / f".deleting-{meeting_id}"

    def incomplete_deletions(self) -> list[str]:
        if not self.meetings.root.exists():
            return []
        return sorted(
            path.name.removeprefix(".deleting-")
            for path in self.meetings.root.iterdir()
            if re.fullmatch(r"\.deleting-[0-9a-f]{32}", path.name)
        )

    def orphan_imports(self) -> list[str]:
        root = self.meetings.root
        if not root.exists():
            return []
        active = set(self.meetings.active_imports())
        result = []
        for path in root.iterdir():
            if not re.fullmatch(r"\.import-[0-9a-f]{32}", path.name):
                continue
            meeting_id = path.name.removeprefix(".import-")
            if (
                meeting_id not in active
                and not self.meetings._meeting_dir(meeting_id).exists()
                and not self._tombstone(meeting_id).exists()
            ):
                result.append(meeting_id)
        return sorted(result)

    def cleanup_orphan_import(self, meeting_id: str, *, confirmed: bool) -> bool:
        if not confirmed:
            return False
        stage = self.meetings.root / f".import-{meeting_id}"
        if meeting_id not in self.orphan_imports():
            raise RuntimeError("This import is active, completed, or unavailable")
        self.meetings.begin_tombstone_cleanup(meeting_id)
        try:
            if _is_reparse(self.meetings.root):
                raise ValueError("Refusing to clean through a linked meetings root")
            _assert_safe_tree(stage)
            _remove_tree(stage)
        finally:
            self.meetings.end_deletion(meeting_id)
        return True

    def delete(self, meeting_id: str) -> None:
        self.meetings.begin_deletion(meeting_id)
        renamed = False
        try:
            root = self.meetings.root
            if _is_reparse(root):
                raise ValueError("Refusing to delete through a linked meetings root")
            target = self.meetings._meeting_dir(meeting_id)
            tombstone = self._tombstone(meeting_id)
            stage = root / f".import-{meeting_id}"
            if tombstone.exists():
                raise RuntimeError("An incomplete deletion already exists; retry its cleanup")
            if meeting_id in self.meetings.active_imports():
                raise RuntimeError("Wait for the active import to finish")
            _assert_safe_tree(target)
            if stage.exists():
                _assert_safe_tree(stage)
            os.replace(target, tombstone)
            renamed = True
            if stage.exists():
                _remove_tree(stage)
            _remove_tree(tombstone)
        except Exception as exc:
            if renamed:
                raise DeletionIncompleteError(meeting_id) from exc
            raise
        finally:
            self.meetings.end_deletion(meeting_id)

    def retry_cleanup(self, meeting_id: str) -> None:
        tombstone = self._tombstone(meeting_id)
        if not tombstone.exists():
            raise FileNotFoundError("No incomplete deletion exists for this meeting")
        self.meetings.begin_tombstone_cleanup(meeting_id)
        try:
            root = self.meetings.root
            if _is_reparse(root):
                raise ValueError("Refusing to clean through a linked meetings root")
            stage = root / f".import-{meeting_id}"
            if meeting_id in self.meetings.active_imports():
                raise RuntimeError("Wait for the active import to finish")
            _assert_safe_tree(tombstone)
            if stage.exists():
                _assert_safe_tree(stage)
                _remove_tree(stage)
            _remove_tree(tombstone)
        except Exception as exc:
            raise DeletionIncompleteError(meeting_id) from exc
        finally:
            self.meetings.end_deletion(meeting_id)
