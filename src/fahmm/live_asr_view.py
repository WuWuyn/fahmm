"""Read local live checkpoints in bounded pages without modifying them."""

from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing, contextmanager
from pathlib import Path

from fahmm.asr import ASR_ERROR_MESSAGES
from fahmm.live_asr import LIVE_ERRORS, LiveASRError, LiveCheckpoint
from fahmm.shared_file_lock import SharedFileLock, live_meeting_lock_path
from fahmm.storage import SAMPLE_RATE, MeetingStore

_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_PAGE_BYTES = 256 * 1024
MAX_ITEMS = 100


class LiveASRView:
    def __init__(self, store: MeetingStore) -> None:
        self.store = store

    @contextmanager
    def _meeting(self, meeting_id: str):
        directory = self.store._meeting_dir(meeting_id)
        lock = SharedFileLock(live_meeting_lock_path(self.store.root, meeting_id), shared=True)
        lock.acquire(timeout=0)
        try:
            if directory.resolve().parent != self.store.root.resolve():
                raise ValueError("Invalid meeting directory")
            self.store.metadata(meeting_id)
            yield directory
        finally:
            lock.release()

    @staticmethod
    def _path(directory: Path, run_id: str) -> Path:
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid live transcription ID")
        parent = directory / "transcripts" / f".live-{run_id}"
        path = parent / "checkpoint.sqlite3"
        if parent.is_symlink() or path.is_symlink() or not path.is_file():
            raise FileNotFoundError("Live transcription checkpoint does not exist")
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError("Invalid live checkpoint location")
        return path

    @staticmethod
    def _open(path: Path):
        return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=2)

    def list_runs(self, meeting_id: str, *, after: str = "", limit: int = 50) -> dict:
        if after and not _RUN_ID.fullmatch(after):
            raise ValueError("Invalid live run cursor")
        if type(limit) is not int or not 1 <= limit <= MAX_ITEMS:
            raise ValueError("Invalid page size")
        with self._meeting(meeting_id) as directory:
            root = directory / "transcripts"
            if not root.exists():
                return {"runs": [], "nextCursor": None}
            if root.is_symlink() or not root.resolve().is_relative_to(directory.resolve()):
                raise ValueError("Invalid live transcript directory")
            names = sorted(
                child.name[6:]
                for child in root.iterdir()
                if child.name.startswith(".live-")
                and _RUN_ID.fullmatch(child.name[6:])
                and child.name[6:] > after
            )
            selected = names[:limit]
            results = []
            for run_id in selected:
                try:
                    path = self._path(directory, run_id)
                    config = LiveCheckpoint.load_config(directory, run_id)
                    with closing(self._open(path)) as connection:
                        data = dict(connection.execute("SELECT key,value FROM metadata"))
                        provisional = connection.execute(
                            "SELECT COUNT(*) FROM hypotheses WHERE status='provisional'"
                        ).fetchone()[0]
                        count = connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0]
                    state = data["state"]
                    if state not in {
                        "new",
                        "running",
                        "cancelled",
                        "error",
                        "needs_review",
                        "completed",
                    }:
                        raise ValueError("Invalid checkpoint state")
                    cursor = int(data["cursor"])
                    if cursor < 0:
                        raise ValueError("Invalid checkpoint cursor")
                    error_code = data.get("error_code") or None
                    if (
                        error_code is not None
                        and error_code not in LIVE_ERRORS
                        and error_code not in ASR_ERROR_MESSAGES
                    ):
                        error_code = "live_failed"
                    results.append(
                        {
                            "runId": run_id,
                            "state": state,
                            "errorCode": error_code,
                            "cursorSeconds": cursor / SAMPLE_RATE,
                            "segmentCount": count,
                            "provisionalCount": provisional,
                            "modelId": config.model_id,
                            "language": config.language,
                        }
                    )
                except (OSError, sqlite3.Error, ValueError, KeyError, LiveASRError):
                    results.append({"runId": run_id, "state": "unreadable"})
            return {"runs": results, "nextCursor": selected[-1] if len(names) > limit else None}

    def read_page(
        self,
        meeting_id: str,
        run_id: str,
        *,
        kind: str = "hypotheses",
        after: int = 0,
        limit: int = 50,
        latest: bool = False,
    ) -> dict:
        if kind not in {"hypotheses", "segments"}:
            raise ValueError("Invalid live transcript page")
        if (
            type(after) is not int
            or after < 0
            or type(limit) is not int
            or not 1 <= limit <= MAX_ITEMS
            or type(latest) is not bool
            or (latest and after != 0)
        ):
            raise ValueError("Invalid live transcript cursor or page size")
        with self._meeting(meeting_id) as directory:
            path = self._path(directory, run_id)
            LiveCheckpoint.load_config(directory, run_id)
            safe_text = "CASE WHEN length(CAST(text AS BLOB)) <= ? THEN text ELSE NULL END"
            columns = (
                f"id,start_frame,end_frame,{safe_text},source,status,window_start"
                if kind == "hypotheses"
                else f"id,start_frame,end_frame,{safe_text},source"
            )
            with closing(self._open(path)) as connection:
                direction = "DESC" if latest else "ASC"
                rows = connection.execute(
                    f"SELECT {columns} FROM {kind} WHERE id>? ORDER BY id {direction} LIMIT ?",
                    (MAX_PAGE_BYTES, after, limit + 1),
                )
                items = []
                size = 0
                more = False
                for row in rows:
                    if (
                        type(row[0]) is not int
                        or type(row[1]) is not int
                        or type(row[2]) is not int
                        or not 0 <= row[1] < row[2]
                        or not isinstance(row[3], str)
                        or row[4] not in {"system", "microphone"}
                        or (
                            kind == "hypotheses"
                            and (
                                row[5] not in {"committed", "matched", "provisional"}
                                or type(row[6]) is not int
                            )
                        )
                    ):
                        raise ValueError("Invalid or oversized live transcript item")
                    item = {
                        "id": row[0],
                        "start": row[1] / SAMPLE_RATE,
                        "end": row[2] / SAMPLE_RATE,
                        "text": row[3],
                        "source": row[4],
                    }
                    if kind == "hypotheses":
                        item.update(status=row[5], windowStart=row[6] / SAMPLE_RATE)
                    item_size = len(json.dumps(item, ensure_ascii=False).encode("utf-8")) + 1
                    if not items and item_size > MAX_PAGE_BYTES:
                        raise ValueError("A live transcript item exceeds the page size limit")
                    if len(items) == limit or size + item_size > MAX_PAGE_BYTES:
                        more = True
                        break
                    items.append(item)
                    size += item_size
            if latest:
                items.reverse()
                return {"items": items, "nextCursor": None}
            return {"items": items, "nextCursor": items[-1]["id"] if more else None}
