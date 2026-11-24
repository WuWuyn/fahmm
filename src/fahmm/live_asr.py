"""Experimental, local-only live ASR over committed recording chunks.

The caller owns capture and lifecycle.  In particular, ``finished`` must only
be set after both capture writers have exited and committed their last chunks.
No part of this module runs in a capture thread or edits the active transcript.
"""

from __future__ import annotations

import hashlib
import json
import logging
import multiprocessing
import os
import queue
import re
import sqlite3
import threading
import wave
from contextlib import ExitStack, closing, suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, Self

import numpy as np

from fahmm.shared_file_lock import SharedFileLock, live_meeting_lock_path, live_model_lock_path
from fahmm.storage import CHUNK_RE, SAMPLE_RATE, SOURCES, Chunk

_ID = re.compile(r"^[0-9a-f]{32}$")
LIVE_ERRORS = {
    "live_failed": "Live transcription failed. Check the recording and selected model.",
    "live_busy": "Another live transcription is using this meeting.",
    "live_checkpoint_mismatch": "The checkpoint does not match this model or configuration.",
    "live_checkpoint_damaged": "The live transcription checkpoint is damaged.",
    "live_audio_changed": "Recorded audio changed; resuming this transcript is unsafe.",
    "live_no_audio": "No committed audio is available for transcription.",
    "live_source_missing": "A recording source has no committed audio; review the recording.",
    "live_audio_gap": "Recorded audio contains a source gap; review the recording.",
    "live_worker_crash": "The live transcription worker stopped unexpectedly.",
    "live_capture_failed": "Recording stopped unexpectedly; recover the recording before resuming.",
    "live_resource_busy": "The recording or model is being changed; retry when it is available.",
    "live_model_changed": "The installed model no longer matches this live transcription.",
}


class LiveASRError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(LIVE_ERRORS[code])


@dataclass(frozen=True)
class LiveConfig:
    meeting_id: str
    run_id: str
    model_id: str
    model_repository: str
    model_revision: str
    language: str = "vi"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 5
    window_seconds: float = 20.0
    overlap_seconds: float = 2.0
    cpu_threads: int = 2

    def validate(self) -> None:
        if any(not _ID.fullmatch(value) for value in (self.meeting_id, self.run_id, self.model_id)):
            raise ValueError("Invalid live transcription ID")
        if not self.model_repository or not self.model_revision:
            raise ValueError("The installed model and revision are required")
        if self.language not in {"vi", "en", "auto"}:
            raise ValueError("Invalid transcription language")
        if (self.device, self.compute_type) not in {("cpu", "int8"), ("cuda", "int8_float16")}:
            raise ValueError("Invalid ASR device or compute type")
        if type(self.beam_size) is not int or not 1 <= self.beam_size <= 10:
            raise ValueError("Invalid ASR beam size")
        if type(self.cpu_threads) is not int or not 1 <= self.cpu_threads <= 4:
            raise ValueError("Invalid live ASR CPU thread limit")
        if not 0 < self.overlap_seconds < self.window_seconds <= 120:
            raise ValueError("Invalid live transcription window")
        if self.step_frames < 1 or self.overlap_frames < 1:
            raise ValueError("Live transcription window is too short")

    @property
    def overlap_frames(self) -> int:
        return round(self.overlap_seconds * SAMPLE_RATE)

    @property
    def step_frames(self) -> int:
        return round((self.window_seconds - self.overlap_seconds) * SAMPLE_RATE)


class LiveLease:
    """An OS-managed lock that is released even if its owner is terminated."""

    def __init__(self, meeting_dir: Path) -> None:
        self.path = meeting_dir / ".live-asr.lock"
        self.file = None

    def __enter__(self) -> Self:
        self.file = self.path.open("a+b")
        try:
            self.file.seek(0, os.SEEK_END)
            if self.file.tell() == 0:
                self.file.write(b"\0")
                self.file.flush()
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self.file.close()
            self.file = None
            raise LiveASRError("live_busy") from exc
        return self

    def __exit__(self, *_args: object) -> None:
        if self.file is None:
            return
        try:
            self.file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()
            self.file = None


class LiveCheckpoint:
    """Each processed window and its cursor are one FULL-synchronous transaction."""

    @staticmethod
    def load_config(meeting_dir: Path, run_id: str) -> LiveConfig:
        """Read the persisted identity for a run without creating a checkpoint."""
        if not _ID.fullmatch(run_id):
            raise ValueError("Invalid live transcription ID")
        path = meeting_dir / "transcripts" / f".live-{run_id}" / "checkpoint.sqlite3"
        if not path.is_file():
            raise FileNotFoundError("Live transcription checkpoint does not exist")
        try:
            with closing(
                sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
            ) as connection:
                metadata = dict(
                    connection.execute(
                        "SELECT key,value FROM metadata WHERE key IN ('schema','config')"
                    )
                )
            if metadata.get("schema") != "5":
                raise ValueError("Unsupported checkpoint schema")
            config = LiveConfig(**json.loads(metadata["config"]))
            config.validate()
            if config.meeting_id != meeting_dir.name or config.run_id != run_id:
                raise ValueError("Checkpoint belongs to another run")
            return config
        except (sqlite3.DatabaseError, ValueError, KeyError, TypeError) as exc:
            raise LiveASRError("live_checkpoint_damaged") from exc

    def __init__(self, meeting_dir: Path, config: LiveConfig, *, create: bool = True) -> None:
        config.validate()
        if meeting_dir.name != config.meeting_id or not meeting_dir.is_dir():
            raise ValueError("Invalid live transcription meeting")
        directory = meeting_dir / "transcripts" / f".live-{config.run_id}"
        self.path = directory / "checkpoint.sqlite3"
        if not create and not self.path.is_file():
            raise FileNotFoundError("Live transcription checkpoint does not exist")
        directory.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, timeout=10)
        try:
            self._initialize(config)
        except Exception:
            self.connection.close()
            raise

    def _initialize(self, config: LiveConfig) -> None:
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=FULL")
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS windows (
                start_frame INTEGER PRIMARY KEY, end_frame INTEGER NOT NULL,
                sources_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS segments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, start_frame INTEGER NOT NULL,
                end_frame INTEGER NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS hypotheses (
                id INTEGER PRIMARY KEY AUTOINCREMENT, window_start INTEGER NOT NULL,
                start_frame INTEGER NOT NULL, end_frame INTEGER NOT NULL,
                text TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL,
                FOREIGN KEY(window_start) REFERENCES windows(start_frame)
            );
            CREATE TABLE IF NOT EXISTS chunks (
                source TEXT NOT NULL, name TEXT NOT NULL, start_frame INTEGER NOT NULL,
                frames INTEGER NOT NULL, size INTEGER NOT NULL, sha256 TEXT NOT NULL,
                PRIMARY KEY(source, name)
            );
            """
        )
        encoded = json.dumps(asdict(config), sort_keys=True, ensure_ascii=False)
        with self.connection:
            existing = self.connection.execute(
                "SELECT value FROM metadata WHERE key='config'"
            ).fetchone()
            if existing is None:
                self.connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    [
                        ("schema", "5"),
                        ("config", encoded),
                        ("cursor", "0"),
                        ("state", "new"),
                        ("error_code", ""),
                    ],
                )
            elif self.get("schema") != "5" or existing[0] != encoded:
                raise LiveASRError("live_checkpoint_mismatch")
        if self.connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise LiveASRError("live_checkpoint_damaged")

    def close(self) -> None:
        self.connection.close()

    def get(self, key: str) -> str:
        row = self.connection.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        if row is None:
            raise ValueError("Incomplete live transcription checkpoint")
        return row[0]

    @property
    def cursor(self) -> int:
        return int(self.get("cursor"))

    def set_state(self, state: str, error_code: str = "") -> None:
        if state not in {"running", "cancelled", "error", "needs_review", "completed"}:
            raise ValueError("Invalid live transcription state")
        if error_code and not re.fullmatch(r"[a-z_]{1,40}", error_code):
            raise ValueError("Invalid live transcription error code")
        with self.connection:
            self.connection.execute("UPDATE metadata SET value=? WHERE key='state'", (state,))
            self.connection.execute(
                "UPDATE metadata SET value=? WHERE key='error_code'", (error_code,)
            )

    def known_chunks(self) -> dict[tuple[str, str], tuple[int, int, int, str]]:
        return {
            (source, name): (start, frames, size, digest)
            for source, name, start, frames, size, digest in self.connection.execute(
                "SELECT source,name,start_frame,frames,size,sha256 FROM chunks"
            )
        }

    def segments(self) -> list[dict]:
        return [
            {
                "id": row[0],
                "start": row[1] / SAMPLE_RATE,
                "end": row[2] / SAMPLE_RATE,
                "text": row[3],
                "source": row[4],
            }
            for row in self.connection.execute(
                "SELECT id,start_frame,end_frame,text,source FROM segments ORDER BY id"
            )
        ]

    def boundary_reviews(self) -> list[dict]:
        """Intervals where different Whisper window segmentations need human review."""
        return [
            {"start": start / SAMPLE_RATE, "end": end / SAMPLE_RATE}
            for start, end, sources in self.connection.execute(
                "SELECT start_frame,end_frame,sources_json FROM windows ORDER BY start_frame"
            )
            if json.loads(sources).get("boundary_review", False)
        ]

    def hypotheses(self) -> list[dict]:
        """All model output, including overlap guesses that were not committed as segments."""
        return [
            {
                "id": row[0],
                "window_start": row[1] / SAMPLE_RATE,
                "start": row[2] / SAMPLE_RATE,
                "end": row[3] / SAMPLE_RATE,
                "text": row[4],
                "source": row[5],
                "status": row[6],
            }
            for row in self.connection.execute(
                "SELECT id,window_start,start_frame,end_frame,text,source,status "
                "FROM hypotheses ORDER BY id"
            )
        ]

    def snapshot(self) -> dict:
        counts = dict(
            self.connection.execute("SELECT status,COUNT(*) FROM hypotheses GROUP BY status")
        )
        return {
            "state": self.get("state"),
            "error_code": self.get("error_code") or None,
            "cursor_seconds": self.cursor / SAMPLE_RATE,
            "segment_count": self.connection.execute("SELECT COUNT(*) FROM segments").fetchone()[0],
            "provisional_count": counts.get("provisional", 0),
            "review_windows": len(self.boundary_reviews()),
        }

    def commit_window(
        self,
        start: int,
        end: int,
        hypotheses: list[tuple[int, int, str, str, str]],
        source_info: dict,
        new_chunks: list[tuple[str, str, int, int, int, str]],
    ) -> None:
        if start < 0 or end <= start:
            raise ValueError("Invalid confirmed audio interval")
        with self.connection:
            if self.cursor != start:
                raise RuntimeError("The live checkpoint advanced unexpectedly")
            self.connection.execute(
                "INSERT INTO windows(start_frame,end_frame,sources_json) VALUES (?,?,?)",
                (start, end, json.dumps(source_info, sort_keys=True)),
            )
            for first, last, text, source, status in hypotheses:
                if not (source in SOURCES and 0 <= first < last and text.strip()):
                    raise ValueError("Invalid live segment")
                if status == "candidate":
                    if not start <= first < last <= end:
                        raise ValueError("A candidate crossed the live audio boundary")
                    duplicate = self.connection.execute(
                        "SELECT 1 FROM segments WHERE source=? AND text=? AND start_frame<? AND end_frame>? LIMIT 1",
                        (source, text, last, first),
                    ).fetchone()
                    if duplicate:
                        status = "matched"
                    else:
                        self.connection.execute(
                            "INSERT INTO segments(start_frame,end_frame,text,source) VALUES (?,?,?,?)",
                            (first, last, text, source),
                        )
                        status = "committed"
                elif status != "provisional":
                    raise ValueError("Invalid live hypothesis status")
                self.connection.execute(
                    "INSERT INTO hypotheses(window_start,start_frame,end_frame,text,source,status) "
                    "VALUES (?,?,?,?,?,?)",
                    (start, first, last, text, source, status),
                )
            self.connection.executemany(
                "INSERT INTO chunks(source,name,start_frame,frames,size,sha256) VALUES (?,?,?,?,?,?)",
                new_chunks,
            )
            self.connection.execute("UPDATE metadata SET value=? WHERE key='cursor'", (str(end),))


def _intervals(mask: np.ndarray) -> list[list[int]]:
    """Return half-open intervals of true samples in a window-local mask."""
    padded = np.concatenate(([False], mask, [False])).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    return [[int(first), int(last)] for first, last in edges.reshape(-1, 2)]


def _chunk_hash(path: Path) -> str:
    """Fingerprint committed audio so same-length replacement is rejected on resume."""
    try:
        with path.open("rb") as file:
            before = os.fstat(file.fileno())
            digest = hashlib.file_digest(file, "sha256").hexdigest()
            after = os.fstat(file.fileno())
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise LiveASRError("live_audio_changed")
        return digest
    except OSError as exc:
        raise LiveASRError("live_audio_changed") from exc


class CommittedChunkIndex:
    """Index only newly named files; never decode a previously indexed chunk again."""

    def __init__(self, meeting_dir: Path, known: dict | None = None, cursor: int = 0) -> None:
        self.meeting_dir = meeting_dir
        self.known = known or {}
        self.cursor = cursor
        self.chunks: dict[str, list[Chunk]] = {source: [] for source in SOURCES}
        self.details: dict[tuple[str, str], tuple[int, int, int, str]] = {}
        self.new_chunks: list[tuple[str, str, int, int, int, str]] = []
        self.read_positions = {source: 0 for source in SOURCES}

    def refresh(self) -> None:
        found = set()
        for source in SOURCES:
            for path in (self.meeting_dir / source).glob("*.wav"):
                match = CHUNK_RE.fullmatch(path.name)
                if not match:
                    continue
                key = (source, path.name)
                found.add(key)
                if key in self.details:
                    continue
                with wave.open(str(path), "rb") as file:
                    if (file.getnchannels(), file.getsampwidth(), file.getframerate()) != (
                        1,
                        2,
                        SAMPLE_RATE,
                    ) or file.getnframes() < 1:
                        raise ValueError("A committed recording chunk has an invalid format")
                    frames = file.getnframes()
                start = int(match.group(1))
                info = (start, frames, path.stat().st_size, _chunk_hash(path))
                if key in self.known:
                    if self.known[key] != info:
                        raise LiveASRError("live_audio_changed")
                elif start < self.cursor:
                    raise LiveASRError("live_audio_changed")
                else:
                    self.new_chunks.append((source, path.name, *info))
                self.details[key] = info
                self.chunks[source].append(Chunk(path, start, frames))
            self.chunks[source].sort(key=lambda chunk: (chunk.start_frame, chunk.path.name))
        if set(self.known) - found:
            raise LiveASRError("live_audio_changed")

    def acknowledge(self) -> None:
        for source, name, start, frames, size, digest in self.new_chunks:
            self.known[(source, name)] = (start, frames, size, digest)
        self.new_chunks.clear()

    def available_end(self, finished: bool) -> int:
        if finished:
            return max(
                (
                    chunk.start_frame + chunk.frames
                    for items in self.chunks.values()
                    for chunk in items
                ),
                default=0,
            )
        # Holding back the most recent chunk of each writer protects against a
        # later committed chunk overlapping that chunk's tail.
        return min(max((c.start_frame for c in self.chunks[s]), default=0) for s in SOURCES)

    def read(self, start: int, end: int) -> tuple[np.ndarray, dict]:
        if start < 0 or end <= start:
            raise ValueError("Invalid live audio window")
        stereo = np.zeros((end - start, 2), dtype=np.int16)
        info = {}
        for channel, source in enumerate(SOURCES):
            covered = np.zeros(end - start, dtype=bool)
            overlap = np.zeros(end - start, dtype=bool)
            chunks = self.chunks[source]
            position = self.read_positions[source]
            while (
                position < len(chunks)
                and chunks[position].start_frame + chunks[position].frames <= start
            ):
                position += 1
            self.read_positions[source] = position
            for chunk in chunks[position:]:
                if chunk.start_frame >= end:
                    break
                first = max(start, chunk.start_frame)
                last = min(end, chunk.start_frame + chunk.frames)
                if first >= last:
                    continue
                if _chunk_hash(chunk.path) != self.details[(source, chunk.path.name)][3]:
                    raise LiveASRError("live_audio_changed")
                with wave.open(str(chunk.path), "rb") as file:
                    file.setpos(first - chunk.start_frame)
                    data = file.readframes(last - first)
                if len(data) != (last - first) * 2:
                    raise ValueError("A committed recording chunk is truncated")
                target = slice(first - start, last - start)
                overlap[target] |= covered[target]
                stereo[target, channel] = np.frombuffer(data, dtype="<i2")
                covered[target] = True
            info[source] = {
                "gaps": [[a + start, b + start] for a, b in _intervals(~covered)],
                "overlaps": [[a + start, b + start] for a, b in _intervals(overlap)],
                "watermark": max((c.start_frame for c in self.chunks[source]), default=0),
            }
        return stereo, info


def _resample_mono(channel: np.ndarray) -> np.ndarray:
    import av

    mono = channel.astype(np.float32) / 32768.0
    frame = av.AudioFrame.from_ndarray(mono.reshape(1, -1), format="flt", layout="mono")
    frame.sample_rate = SAMPLE_RATE
    converter = av.AudioResampler(format="flt", layout="mono", rate=16_000)
    frames = [*converter.resample(frame), *converter.resample(None)]
    return (
        np.concatenate([item.to_ndarray().reshape(-1) for item in frames])
        if frames
        else np.empty(0, np.float32)
    )


class WindowModel(Protocol):
    def transcribe(self, audio: np.ndarray) -> list[tuple[float, float, str]]: ...


class WhisperWindowModel:
    """Load the local model once in the dedicated worker process."""

    def __init__(self, model_path: Path, config: LiveConfig) -> None:
        from fahmm.asr import ASRRuntimeError, _check_cuda_runtime, _cuda_error_code
        from fahmm.models import validate_model_dir

        validate_model_dir(model_path)
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        if config.device == "cuda":
            _check_cuda_runtime(config.compute_type)
        from faster_whisper import WhisperModel

        try:
            self.model = WhisperModel(
                str(model_path.resolve()),
                device=config.device,
                compute_type=config.compute_type,
                cpu_threads=config.cpu_threads,
                num_workers=1,
                local_files_only=True,
            )
        except Exception as exc:
            if config.device == "cuda":
                raise ASRRuntimeError(_cuda_error_code(exc)) from exc
            raise
        self.language = config.language
        self.beam_size = config.beam_size
        self.device = config.device

    def transcribe(self, audio: np.ndarray) -> list[tuple[float, float, str]]:
        from fahmm.asr import ASRRuntimeError, _cuda_error_code

        try:
            segments, _info = self.model.transcribe(
                audio,
                task="transcribe",
                language=None if self.language == "auto" else self.language,
                vad_filter=True,
                beam_size=self.beam_size,
            )
            return [(float(item.start), float(item.end), item.text.strip()) for item in segments]
        except Exception as exc:
            if self.device == "cuda":
                raise ASRRuntimeError(_cuda_error_code(exc)) from exc
            raise


def _notify(output, message: dict) -> None:
    if output is None:
        return
    try:
        output.put_nowait(message)
    except (queue.Full, OSError, ValueError):
        pass  # The durable checkpoint, not this best-effort queue, is authoritative.


def process_available(
    checkpoint: LiveCheckpoint,
    index: CommittedChunkIndex,
    config: LiveConfig,
    model: WindowModel,
    *,
    finished: bool,
    cancel=None,
) -> bool:
    """Store one window's model output and processed interval atomically."""
    index.refresh()
    cursor = checkpoint.cursor
    available = index.available_end(finished)
    if finished:
        if not any(index.chunks.values()):
            raise LiveASRError("live_no_audio")
        if any(not index.chunks[source] for source in SOURCES):
            raise LiveASRError("live_source_missing")
        if cursor >= available:
            return False
        end = min(cursor + config.step_frames, available)
        audio_end = min(available, end + config.overlap_frames)
    else:
        end = cursor + config.step_frames
        audio_end = end + config.overlap_frames
        if audio_end > available:
            return False
    audio_start = max(0, cursor - config.overlap_frames)
    stereo, source_info = index.read(audio_start, audio_end)
    if any(
        first < end and last > cursor
        for source in SOURCES
        for first, last in source_info[source]["gaps"]
    ):
        raise LiveASRError("live_audio_gap")
    hypotheses = []
    boundary_review = False
    for channel, source in enumerate(SOURCES):
        audio = stereo[:, channel]
        if not np.any(audio):
            continue
        output = model.transcribe(_resample_mono(audio))
        if cancel is not None and cancel.is_set():
            return False
        previous_near_boundary = cursor > 0 and bool(
            checkpoint.connection.execute(
                "SELECT 1 FROM segments WHERE source=? AND end_frame>? AND start_frame<? LIMIT 1",
                (source, max(0, cursor - config.overlap_frames), cursor + config.overlap_frames),
            ).fetchone()
        )
        for first, last, text in output:
            if not isinstance(text, str) or not text.strip():
                continue
            start_frame = max(audio_start, audio_start + round(first * SAMPLE_RATE))
            end_frame = min(audio_end, audio_start + round(last * SAMPLE_RATE))
            if start_frame >= end_frame:
                continue
            if cursor <= start_frame < end_frame <= end:
                status = "candidate"
            else:
                status = "provisional"
                boundary_review = True
            if previous_near_boundary and start_frame < cursor + config.overlap_frames:
                boundary_review = True
            hypotheses.append((start_frame, end_frame, text.strip(), source, status))
    source_info["boundary_review"] = boundary_review
    checkpoint.commit_window(cursor, end, sorted(hypotheses), source_info, list(index.new_chunks))
    index.acknowledge()
    index.cursor = end
    return True


def _validate_live_model(model_path: Path, config: LiveConfig) -> None:
    """Re-read the installation and revision after taking the shared model lock."""
    from fahmm.models import ModelManager

    try:
        model = ModelManager(model_path.parent.parent).get(config.model_id)
        if (
            model.path.resolve() != model_path.resolve()
            or model.repository != config.model_repository
            or model.revision != config.model_revision
        ):
            raise ValueError("Model identity changed")
    except Exception as exc:
        raise LiveASRError("live_model_changed") from exc


def run_live_asr_worker(
    meeting_dir: str,
    config: LiveConfig,
    model_path: str,
    output,
    cancel,
    finished,
    *,
    model_factory=WhisperWindowModel,
    model_validator=_validate_live_model,
    poll_seconds: float = 0.5,
    parent_poll_seconds: float = 0.5,
) -> None:
    """Spawn-safe process target; only read committed chunks and write local checkpoints."""
    if not 0.01 <= parent_poll_seconds <= 60 or not 0.01 <= poll_seconds <= 60:
        raise ValueError("Invalid live worker polling interval")
    # A hard-killed sidecar cannot run multiprocessing's normal daemon cleanup.
    # Stop this worker as well, including while native inference is blocked.
    parent = multiprocessing.parent_process()
    parent_watch_stop = threading.Event()
    if parent is not None:
        # Deprioritize only our spawned worker, never the recorder or user apps.
        try:
            import psutil
        except ImportError:
            psutil = None
        try:
            if os.name == "nt":
                if psutil is not None:
                    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            else:
                os.nice(5)
        except Exception:
            logging.getLogger(__name__).debug("Could not lower live ASR worker priority")

        def watch_parent() -> None:
            while not parent_watch_stop.wait(parent_poll_seconds):
                if not parent.is_alive():
                    os._exit(1)

        threading.Thread(target=watch_parent, daemon=True).start()
    checkpoint = None
    model = None
    resources = ExitStack()
    try:
        directory = Path(meeting_dir)
        model_dir = Path(model_path)
        config.validate()
        if (
            not directory.is_absolute()
            or directory.name != config.meeting_id
            or not model_dir.is_absolute()
            or model_dir.name != config.model_id
            or model_dir.parent.name != "installed"
        ):
            raise LiveASRError("live_failed")
        meeting_lock = SharedFileLock(
            live_meeting_lock_path(directory.parent, config.meeting_id), shared=True
        )
        meeting_lock.acquire(timeout=0, cancel=cancel)
        resources.callback(meeting_lock.release)
        model_lock = SharedFileLock(
            live_model_lock_path(model_dir.parent.parent, config.model_id), shared=True
        )
        model_lock.acquire(timeout=0, cancel=cancel)
        resources.callback(model_lock.release)
        from fahmm.storage import MeetingStore

        if MeetingStore(directory.parent).metadata(config.meeting_id)["source_kind"] != "recorded":
            raise LiveASRError("live_failed")
        model_validator(model_dir, config)
        with LiveLease(directory):
            checkpoint = LiveCheckpoint(directory, config)
            index = CommittedChunkIndex(directory, checkpoint.known_chunks(), checkpoint.cursor)
            saved_state = checkpoint.get("state")
            if saved_state in {"completed", "needs_review"}:
                index.refresh()
                if index.available_end(True) != checkpoint.cursor:
                    raise LiveASRError("live_audio_changed")
                _notify(output, {"type": saved_state, "cursor": checkpoint.cursor})
                return
            checkpoint.set_state("running")
            model = model_factory(model_dir, config)
            while not cancel.is_set():
                # Read this once: if capture finishes during inference, a stale
                # live-window result must never be mistaken for the final drain.
                capture_finished = finished.is_set()
                advanced = process_available(
                    checkpoint, index, config, model, finished=capture_finished, cancel=cancel
                )
                _notify(
                    output,
                    {
                        "type": "progress",
                        "cursor": checkpoint.cursor,
                        "available": index.available_end(capture_finished),
                    },
                )
                if cancel.is_set():
                    break
                if not advanced and capture_finished:
                    state = "needs_review" if checkpoint.boundary_reviews() else "completed"
                    checkpoint.set_state(state)
                    _notify(output, {"type": state, "cursor": checkpoint.cursor})
                    return
                if not advanced:
                    cancel.wait(poll_seconds)
            checkpoint.set_state("cancelled")
            _notify(output, {"type": "cancelled", "cursor": checkpoint.cursor})
    except InterruptedError:
        _notify(output, {"type": "cancelled"})
    except Exception as exc:
        from fahmm.asr import ASR_ERROR_MESSAGES, ASRRuntimeError

        if isinstance(exc, TimeoutError):
            code, message = "live_resource_busy", LIVE_ERRORS["live_resource_busy"]
        elif isinstance(exc, LiveASRError):
            code, message = exc.code, LIVE_ERRORS[exc.code]
        elif isinstance(exc, ASRRuntimeError):
            code, message = exc.code, ASR_ERROR_MESSAGES[exc.code]
        else:
            code, message = "live_failed", LIVE_ERRORS["live_failed"]
        if checkpoint is not None:
            with suppress(Exception):
                checkpoint.set_state("error", code)
        _notify(output, {"type": "error", "code": code, "message": message})
        raise SystemExit(1) from None
    finally:
        parent_watch_stop.set()
        try:
            if checkpoint is not None:
                checkpoint.close()
        finally:
            model = None
            resources.close()
