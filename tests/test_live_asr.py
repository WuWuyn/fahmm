"""Crash, alignment, and capture-isolation checks for the live ASR core."""

from __future__ import annotations

import json
import multiprocessing
import os
import queue
import sqlite3
import threading
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from fahmm.live_asr import (
    CommittedChunkIndex,
    LiveASRError,
    LiveCheckpoint,
    LiveConfig,
    LiveLease,
    WhisperWindowModel,
    process_available,
    run_live_asr_worker,
)
from fahmm.shared_file_lock import SharedFileLock, live_meeting_lock_path, live_model_lock_path
from fahmm.storage import SAMPLE_RATE, MeetingStore


def make_config(meeting_id: str) -> LiveConfig:
    return LiveConfig(
        meeting_id=meeting_id,
        run_id="a" * 32,
        model_id="b" * 32,
        model_repository="test/base",
        model_revision="revision-1",
        window_seconds=0.4,
        overlap_seconds=0.1,
    )


def make_meeting(tmp_path: Path) -> tuple[MeetingStore, str, Path, LiveConfig]:
    store = MeetingStore(tmp_path)
    meeting_id = store.create({"system": "speaker", "microphone": "mic"})
    return store, meeting_id, store._meeting_dir(meeting_id), make_config(meeting_id)


def fake_model_path(directory: Path, config: LiveConfig) -> str:
    path = directory.parent / "fake-models" / "installed" / config.model_id
    path.mkdir(parents=True, exist_ok=True)
    return str(path)


def fake_model_validator(path: Path, config: LiveConfig) -> None:
    assert path.is_dir() and path.name == config.model_id


def write_pair(store: MeetingStore, meeting: str, start: int, count: int) -> None:
    store.write_chunk(meeting, "system", start, np.full(count, 0.2, np.float32))
    store.write_chunk(meeting, "microphone", start, np.full(count, 0.3, np.float32))


class FakeModel:
    def transcribe(self, audio: np.ndarray) -> list[tuple[float, float, str]]:
        assert audio.dtype == np.float32
        return [(0.15, 0.2, "Thử nghiệm")]


def test_live_model_limits_cpu_threads_and_uses_one_worker(tmp_path, monkeypatch):
    import faster_whisper

    import fahmm.models

    _store, _meeting, _directory, config = make_meeting(tmp_path)
    captured = {}

    def create_model(*_args, **kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(fahmm.models, "validate_model_dir", lambda _path: None)
    monkeypatch.setattr(faster_whisper, "WhisperModel", create_model)
    WhisperWindowModel(tmp_path, replace(config, cpu_threads=3))
    assert captured["cpu_threads"] == 3 and captured["num_workers"] == 1


def test_legacy_checkpoint_remains_readable_but_is_not_silently_resumed(tmp_path):
    import json

    _store, _meeting, directory, config = make_meeting(tmp_path)
    saved = LiveCheckpoint(directory, config)
    old_config = json.loads(saved.get("config"))
    del old_config["cpu_threads"]
    with saved.connection:
        saved.connection.execute(
            "UPDATE metadata SET value=? WHERE key='config'",
            (json.dumps(old_config, sort_keys=True, ensure_ascii=False),),
        )
    saved.close()
    readable = LiveCheckpoint.load_config(directory, config.run_id)
    with pytest.raises(LiveASRError, match="does not match"):
        LiveCheckpoint(directory, readable, create=False)
    assert (directory / "transcripts" / f".live-{config.run_id}" / "checkpoint.sqlite3").is_file()


def test_alignment_padding_overlap_and_read_only_committed_files(tmp_path):
    store, meeting, directory, _config = make_meeting(tmp_path)
    store.write_chunk(meeting, "system", 0, np.full(100, 0.2, np.float32))
    store.write_chunk(meeting, "system", 80, np.full(100, 0.4, np.float32))
    store.write_chunk(meeting, "microphone", 40, np.full(100, 0.6, np.float32))
    # Open/temp files are never indexed even if they contain valid WAV bytes.
    (directory / "system" / ".000000000180-deadbeef.wav.tmp").write_bytes(b"partial")
    index = CommittedChunkIndex(directory)
    index.refresh()
    assert index.available_end(False) == 40
    assert index.available_end(True) == 180
    stereo, sources = index.read(0, 180)
    assert stereo.shape == (180, 2)
    assert np.all(stereo[:40, 1] == 0)
    assert np.all(stereo[80:, 0] == round(0.4 * 32767))
    assert sources["system"]["overlaps"] == [[80, 100]]
    assert sources["system"]["gaps"] == []
    assert sources["microphone"]["gaps"] == [[0, 40], [140, 180]]


def test_windows_checkpoint_resume_and_model_mismatch(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    n = SAMPLE_RATE // 5
    for offset in range(0, 5 * n, n):
        write_pair(store, meeting, offset, n)
    store.update_metadata(meeting, active_run="c" * 32)
    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory, checkpoint.known_chunks(), checkpoint.cursor)
    assert process_available(checkpoint, index, config, FakeModel(), finished=False)
    saved_cursor, saved_segments = checkpoint.cursor, checkpoint.segments()
    assert saved_cursor == config.step_frames
    assert saved_segments
    assert checkpoint.snapshot()["segment_count"] == len(saved_segments)
    checkpoint.close()

    assert LiveCheckpoint.load_config(directory, config.run_id) == config
    with pytest.raises(FileNotFoundError):
        LiveCheckpoint.load_config(directory, "c" * 32)
    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory, checkpoint.known_chunks(), checkpoint.cursor)
    while process_available(checkpoint, index, config, FakeModel(), finished=True):
        pass
    assert checkpoint.cursor == 5 * n
    segments = checkpoint.segments()
    assert segments[: len(saved_segments)] == saved_segments
    assert len({item["id"] for item in segments}) == len(segments)
    assert all(0 <= item["start"] < item["end"] <= 1 for item in segments)
    assert store.metadata(meeting)["active_run"] == "c" * 32
    checkpoint.close()
    with pytest.raises(LiveASRError, match="does not match"):
        LiveCheckpoint(directory, replace(config, model_revision="revision-2"))


def _die_before_commit(database: str, ready) -> None:
    connection = sqlite3.connect(database)
    connection.execute("BEGIN IMMEDIATE")
    connection.execute(
        "INSERT INTO segments(start_frame,end_frame,text,source) VALUES(1,2,'uncommitted','system')"
    )
    connection.execute("UPDATE metadata SET value='123' WHERE key='cursor'")
    ready.set()
    time.sleep(30)


def test_process_killed_mid_transaction_keeps_segment_and_cursor_together(tmp_path):
    _store, _meeting, directory, config = make_meeting(tmp_path)
    checkpoint = LiveCheckpoint(directory, config)
    database = str(checkpoint.path)
    checkpoint.close()
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    process = context.Process(target=_die_before_commit, args=(database, ready))
    process.start()
    try:
        assert ready.wait(15)
        process.terminate()
        process.join(10)
        assert not process.is_alive()
    finally:
        if process.is_alive():
            process.kill()
            process.join(5)
    checkpoint = LiveCheckpoint(directory, config)
    assert checkpoint.cursor == 0
    assert checkpoint.segments() == []
    checkpoint.close()


def test_changed_or_late_audio_rejected_on_resume(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    n = SAMPLE_RATE // 5
    for offset in range(0, 4 * n, n):
        write_pair(store, meeting, offset, n)
    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory, checkpoint.known_chunks(), checkpoint.cursor)
    assert process_available(checkpoint, index, config, FakeModel(), finished=False)
    known, cursor = checkpoint.known_chunks(), checkpoint.cursor
    store.write_chunk(meeting, "system", 1, np.ones(100, np.float32))
    resumed = CommittedChunkIndex(directory, known, cursor)
    with pytest.raises(LiveASRError, match="resuming this transcript is unsafe"):
        resumed.refresh()
    checkpoint.close()


def test_resume_detects_same_size_replacement_with_same_timestamp(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    n = SAMPLE_RATE // 5
    for offset in range(0, 4 * n, n):
        write_pair(store, meeting, offset, n)
    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory, checkpoint.known_chunks(), checkpoint.cursor)
    assert process_available(checkpoint, index, config, FakeModel(), finished=False)
    known, cursor = checkpoint.known_chunks(), checkpoint.cursor
    path = next((directory / "system").glob("*.wav"))
    original = path.stat()
    changed = bytearray(path.read_bytes())
    changed[-1] ^= 1
    path.write_bytes(changed)
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    assert path.stat().st_size == original.st_size
    resumed = CommittedChunkIndex(directory, known, cursor)
    with pytest.raises(LiveASRError, match="Recorded audio changed"):
        resumed.refresh()
    checkpoint.close()


def test_different_segmentation_at_window_boundary_is_marked_for_review(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    n = SAMPLE_RATE // 5
    for offset in range(0, 5 * n, n):
        write_pair(store, meeting, offset, n)

    class BoundaryModel:
        calls = 0

        def transcribe(self, _audio):
            self.calls += 1
            if self.calls == 1:
                return [(0.24, 0.29, "Chúng ta")]
            if self.calls == 3:
                return [(0.07, 0.17, "ta đi tiếp")]
            return []

    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory)
    model = BoundaryModel()
    while process_available(checkpoint, index, config, model, finished=True):
        pass
    assert [segment["text"] for segment in checkpoint.segments()] == ["Chúng ta"]
    assert [item["text"] for item in checkpoint.hypotheses()] == ["Chúng ta", "ta đi tiếp"]
    assert checkpoint.hypotheses()[-1]["status"] == "provisional"
    assert checkpoint.boundary_reviews()
    checkpoint.close()


@pytest.mark.parametrize(
    ("first", "second", "expected_count"),
    [
        ([(0.20, 0.35, "alpha beta")], [(0.05, 0.20, "beta")], 0),
        ([(0.25, 0.40, "alpha beta")], [(0.02, 0.16, "alpha")], 0),
        ([], [(0.02, 0.08, "alpha")], 0),
    ],
)
def test_known_boundary_ambiguity_never_reports_completed(tmp_path, first, second, expected_count):
    store, meeting, directory, config = make_meeting(tmp_path)
    store.write_chunk(meeting, "system", 0, np.full(SAMPLE_RATE, 0.2, np.float32))
    store.write_chunk(meeting, "microphone", 0, np.zeros(SAMPLE_RATE, np.float32))

    class AmbiguousModel:
        calls = 0

        def transcribe(self, _audio):
            self.calls += 1
            if self.calls == 1:
                return first
            if self.calls == 2:
                return second
            return []

    cancel, finished = threading.Event(), threading.Event()
    finished.set()
    run_live_asr_worker(
        str(directory),
        config,
        fake_model_path(directory, config),
        None,
        cancel,
        finished,
        model_validator=fake_model_validator,
        model_factory=lambda _path, _config: AmbiguousModel(),
    )
    checkpoint = LiveCheckpoint(directory, config)
    assert len(checkpoint.segments()) == expected_count
    assert checkpoint.hypotheses()
    assert all(item["status"] == "provisional" for item in checkpoint.hypotheses())
    assert checkpoint.boundary_reviews()
    assert checkpoint.get("state") == "needs_review"
    checkpoint.close()


def test_opposite_phase_sources_transcribed_independently_without_cross_source_dedup(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    store.write_chunk(meeting, "system", 0, np.full(SAMPLE_RATE, 0.3, np.float32))
    store.write_chunk(meeting, "microphone", 0, np.full(SAMPLE_RATE, -0.3, np.float32))

    class InspectModel:
        def __init__(self):
            self.seen = []

        def transcribe(self, audio):
            self.seen.append(float(np.mean(audio)))
            return [(0.05, 0.1, "same words")]

    model = InspectModel()
    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory)
    assert process_available(checkpoint, index, config, model, finished=True)
    assert model.seen[0] > 0.1 and model.seen[1] < -0.1
    assert {item["source"] for item in checkpoint.segments()} == {"system", "microphone"}
    checkpoint.close()


def test_finished_recording_missing_source_or_gap_cannot_complete(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    store.write_chunk(meeting, "system", 0, np.full(SAMPLE_RATE, 0.2, np.float32))
    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory)
    with pytest.raises(LiveASRError, match="source has no committed audio"):
        process_available(checkpoint, index, config, FakeModel(), finished=True)
    checkpoint.close()
    cancel, finished = threading.Event(), threading.Event()
    finished.set()
    with pytest.raises(SystemExit):
        run_live_asr_worker(
            str(directory),
            config,
            fake_model_path(directory, config),
            None,
            cancel,
            finished,
            model_validator=fake_model_validator,
            model_factory=lambda _path, _config: FakeModel(),
        )
    checkpoint = LiveCheckpoint(directory, config, create=False)
    assert checkpoint.get("state") == "error"
    assert checkpoint.get("error_code") == "live_source_missing"
    checkpoint.close()

    store.write_chunk(meeting, "microphone", 0, np.full(2000, 0.2, np.float32))
    store.write_chunk(meeting, "microphone", 3000, np.full(SAMPLE_RATE - 3000, 0.2, np.float32))
    checkpoint = LiveCheckpoint(directory, config)
    index = CommittedChunkIndex(directory)
    with pytest.raises(LiveASRError, match="source gap"):
        process_available(checkpoint, index, config, FakeModel(), finished=True)
    assert checkpoint.cursor == 0
    checkpoint.close()

    with pytest.raises(SystemExit):
        run_live_asr_worker(
            str(directory),
            config,
            fake_model_path(directory, config),
            None,
            cancel,
            finished,
            model_validator=fake_model_validator,
            model_factory=lambda _path, _config: FakeModel(),
        )
    checkpoint = LiveCheckpoint(directory, config, create=False)
    assert checkpoint.get("state") == "error"
    assert checkpoint.get("error_code") == "live_audio_gap"
    assert checkpoint.cursor == 0
    checkpoint.close()


def test_completed_checkpoint_revalidates_the_recording(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    write_pair(store, meeting, 0, SAMPLE_RATE)
    cancel, finished = threading.Event(), threading.Event()
    finished.set()
    run_live_asr_worker(
        str(directory),
        config,
        fake_model_path(directory, config),
        None,
        cancel,
        finished,
        model_validator=fake_model_validator,
        model_factory=lambda _path, _config: FakeModel(),
    )
    checkpoint = LiveCheckpoint(directory, config, create=False)
    assert checkpoint.get("state") in {"completed", "needs_review"}
    checkpoint.close()
    source = next((directory / "system").glob("*.wav"))
    content = bytearray(source.read_bytes())
    content[-1] ^= 1
    source.write_bytes(content)
    with pytest.raises(SystemExit):
        run_live_asr_worker(
            str(directory),
            config,
            fake_model_path(directory, config),
            None,
            cancel,
            finished,
            model_validator=fake_model_validator,
            model_factory=lambda _path, _config: FakeModel(),
        )
    checkpoint = LiveCheckpoint(directory, config, create=False)
    assert checkpoint.get("state") == "error"
    assert checkpoint.get("error_code") == "live_audio_changed"
    checkpoint.close()


def test_lease_released_on_close(tmp_path):
    _store, _meeting, directory, _config = make_meeting(tmp_path)
    with (
        LiveLease(directory),
        pytest.raises(RuntimeError, match="Another live transcription"),
        LiveLease(directory),
    ):
        pass
    with LiveLease(directory):
        pass


class BlockingModel:
    def __init__(self, entered, release):
        self.entered = entered
        self.release = release
        self.calls = 0

    def transcribe(self, _audio):
        self.calls += 1
        self.entered.set()
        assert self.release.wait(10)
        return [(0.15, 0.2, "Đã ghi")]


def test_slow_asr_and_full_notification_queue_do_not_block_capture(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    n = SAMPLE_RATE // 5
    for offset in range(0, 5 * n, n):
        write_pair(store, meeting, offset, n)
    entered, release, cancel, finished = (threading.Event() for _ in range(4))
    model = BlockingModel(entered, release)
    output = queue.Queue(maxsize=1)
    output.put_nowait({"type": "full"})
    worker = threading.Thread(
        target=run_live_asr_worker,
        args=(str(directory), config, fake_model_path(directory, config), output, cancel, finished),
        kwargs={
            "model_validator": fake_model_validator,
            "model_factory": lambda _path, _config: model,
            "poll_seconds": 0.01,
        },
    )
    worker.start()
    try:
        assert entered.wait(10)
        # The inference is blocked, yet capture can commit both sources.
        write_pair(store, meeting, 5 * n, n)
        finished.set()  # Caller must do this only once the capture writers have stopped.
        release.set()
        worker.join(15)
        assert not worker.is_alive()
        checkpoint = LiveCheckpoint(directory, config)
        assert checkpoint.get("state") == "completed"
        assert checkpoint.cursor == 6 * n
        assert model.calls > 1
        checkpoint.close()
    finally:
        cancel.set()
        release.set()
        worker.join(5)


def test_cancel_during_inference_does_not_commit_late_segments(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    n = SAMPLE_RATE // 5
    for offset in range(0, 5 * n, n):
        write_pair(store, meeting, offset, n)
    entered, release, cancel, finished = (threading.Event() for _ in range(4))
    model = BlockingModel(entered, release)
    worker = threading.Thread(
        target=run_live_asr_worker,
        args=(str(directory), config, fake_model_path(directory, config), None, cancel, finished),
        kwargs={
            "model_validator": fake_model_validator,
            "model_factory": lambda _path, _config: model,
            "poll_seconds": 0.01,
        },
    )
    worker.start()
    try:
        assert entered.wait(10)
        cancel.set()
        release.set()
        worker.join(10)
        assert not worker.is_alive()
        checkpoint = LiveCheckpoint(directory, config)
        assert checkpoint.get("state") == "cancelled"
        assert checkpoint.cursor == 0
        assert checkpoint.segments() == []
        checkpoint.close()
    finally:
        cancel.set()
        release.set()
        worker.join(5)


class CrashSecondModel(FakeModel):
    def __init__(self, ready, blocker):
        self.calls = 0
        self.ready = ready
        self.blocker = blocker

    def transcribe(self, audio):
        self.calls += 1
        if self.calls == 3:
            self.ready.set()
            self.blocker.wait(30)
        return super().transcribe(audio)


class CrashSecondFactory:
    def __init__(self, ready, blocker):
        self.ready = ready
        self.blocker = blocker

    def __call__(self, _path, _config):
        return CrashSecondModel(self.ready, self.blocker)


def fake_model_factory(_path, _config):
    return FakeModel()


def test_worker_killed_during_second_window_restarts_at_committed_cursor(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    n = SAMPLE_RATE // 5
    for offset in range(0, 5 * n, n):
        write_pair(store, meeting, offset, n)
    context = multiprocessing.get_context("spawn")
    cancel, finished, ready, blocker = (context.Event() for _ in range(4))
    finished.set()
    worker = context.Process(
        target=run_live_asr_worker,
        args=(str(directory), config, fake_model_path(directory, config), None, cancel, finished),
        kwargs={
            "model_validator": fake_model_validator,
            "model_factory": CrashSecondFactory(ready, blocker),
        },
    )
    worker.start()
    try:
        assert ready.wait(15)
        worker.terminate()
        worker.join(10)
        assert not worker.is_alive()
        checkpoint = LiveCheckpoint(directory, config)
        original_segments = checkpoint.segments()
        assert checkpoint.cursor == config.step_frames
        assert original_segments
        checkpoint.close()
        resumed = context.Process(
            target=run_live_asr_worker,
            args=(
                str(directory),
                config,
                fake_model_path(directory, config),
                None,
                cancel,
                finished,
            ),
            kwargs={"model_validator": fake_model_validator, "model_factory": fake_model_factory},
        )
        resumed.start()
        resumed.join(15)
        assert not resumed.is_alive() and resumed.exitcode == 0
        checkpoint = LiveCheckpoint(directory, config)
        assert checkpoint.get("state") == "completed"
        assert checkpoint.cursor == 5 * n
        segments = checkpoint.segments()
        assert segments[: len(original_segments)] == original_segments
        assert len({segment["id"] for segment in segments}) == len(segments)
        checkpoint.close()
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join(5)


def test_live_cuda_uses_shared_preflight_and_does_not_fallback(tmp_path, monkeypatch):
    from fahmm.asr import ASRRuntimeError

    _store, _meeting, _directory, config = make_meeting(tmp_path)
    monkeypatch.setattr("fahmm.models.validate_model_dir", lambda _path: None)

    def reject_cuda(_compute_type):
        raise ASRRuntimeError("cuda_runtime")

    monkeypatch.setattr("fahmm.asr._check_cuda_runtime", reject_cuda)
    with pytest.raises(ASRRuntimeError) as error:
        WhisperWindowModel(tmp_path, replace(config, device="cuda", compute_type="int8_float16"))
    assert error.value.code == "cuda_runtime"


def test_worker_error_is_safe_and_exits_nonzero(tmp_path):
    _store, _meeting, directory, config = make_meeting(tmp_path)
    output = queue.Queue()
    cancel, finished = threading.Event(), threading.Event()

    def fail_model(_path, _config):
        raise RuntimeError("C:/private/persons-name/file")

    with pytest.raises(SystemExit) as result:
        run_live_asr_worker(
            str(directory),
            config,
            fake_model_path(directory, config),
            output,
            cancel,
            finished,
            model_validator=fake_model_validator,
            model_factory=fail_model,
        )
    assert result.value.code == 1
    message = output.get_nowait()
    assert message["code"] == "live_failed"
    assert "private" not in str(message)
    checkpoint = LiveCheckpoint(directory, config)
    assert checkpoint.get("state") == "error"
    assert checkpoint.get("error_code") == "live_failed"
    checkpoint.close()


@pytest.mark.parametrize("resource", ["meeting", "model"])
def test_worker_fails_safely_if_deletion_acquired_exclusive_first(tmp_path, resource):
    store, meeting, directory, config = make_meeting(tmp_path)
    model_path = Path(fake_model_path(directory, config))
    meeting_path = live_meeting_lock_path(store.root, meeting)
    model_lock_path = live_model_lock_path(model_path.parent.parent, config.model_id)
    lock = SharedFileLock(meeting_path if resource == "meeting" else model_lock_path, shared=False)
    lock.acquire(timeout=0)
    output = queue.Queue()
    try:
        with pytest.raises(SystemExit):
            run_live_asr_worker(
                str(directory),
                config,
                str(model_path),
                output,
                threading.Event(),
                threading.Event(),
                model_factory=fake_model_factory,
                model_validator=fake_model_validator,
            )
        assert output.get_nowait()["code"] == "live_resource_busy"
        assert not (directory / "transcripts" / f".live-{config.run_id}").exists()
        if resource == "model":
            meeting_lock = SharedFileLock(meeting_path, shared=False)
            meeting_lock.acquire(timeout=0)
            meeting_lock.release()
    finally:
        lock.release()


def test_worker_cancelled_before_lock_acquisition_does_not_create_checkpoint(tmp_path):
    store, meeting, directory, config = make_meeting(tmp_path)
    model_path = Path(fake_model_path(directory, config))
    cancel, finished = threading.Event(), threading.Event()
    cancel.set()
    output = queue.Queue()
    run_live_asr_worker(
        str(directory),
        config,
        str(model_path),
        output,
        cancel,
        finished,
        model_factory=fake_model_factory,
        model_validator=fake_model_validator,
    )
    assert output.get_nowait()["type"] == "cancelled"
    assert not (directory / "transcripts" / f".live-{config.run_id}").exists()
    for lock_path in (
        live_meeting_lock_path(store.root, meeting),
        live_model_lock_path(model_path.parent.parent, config.model_id),
    ):
        lock = SharedFileLock(lock_path, shared=False)
        lock.acquire(timeout=0)
        lock.release()


def test_worker_rechecks_model_revision_after_taking_locks(tmp_path, monkeypatch):
    _store, _meeting, directory, config = make_meeting(tmp_path)
    model_path = Path(fake_model_path(directory, config))
    model_index = {
        "schema_version": 1,
        "selected": config.model_id,
        "installations": {
            config.model_id: {
                "repository": config.model_repository,
                "publisher": "test",
                "license": "MIT",
                "revision": "different",
                "bytes": 1,
            }
        },
    }
    (model_path.parent.parent / "index.json").write_text(json.dumps(model_index), encoding="utf-8")
    monkeypatch.setattr("fahmm.models.validate_model_dir", lambda _path: None)
    output = queue.Queue()
    with pytest.raises(SystemExit):
        run_live_asr_worker(
            str(directory),
            config,
            str(model_path),
            output,
            threading.Event(),
            threading.Event(),
            model_factory=fake_model_factory,
        )
    assert output.get_nowait()["code"] == "live_model_changed"
    assert not (directory / "transcripts" / f".live-{config.run_id}").exists()
