import json
import multiprocessing
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_shared_file_lock import _hold_lock
from tokenizers import Tokenizer, models

from fahmm import models as model_module
from fahmm.models import InstalledModel, ModelManager, validate_model_dir
from fahmm.shared_file_lock import SharedFileLock, live_model_lock_path


def make_bundle(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.bin").write_bytes(b"ct2-placeholder")
    (path / "config.json").write_text(json.dumps({"suppress_ids": []}), encoding="utf-8")
    Tokenizer(models.BPE()).save(str(path / "tokenizer.json"))
    (path / "vocabulary.txt").write_text("word 0\n", encoding="utf-8")


def test_offline_model_manifest_and_selection(tmp_path, monkeypatch):
    manager = ModelManager(tmp_path / "models")
    first_id = uuid.uuid4().hex
    first_path = manager._path(first_id)
    make_bundle(first_path)

    def no_network(*args, **kwargs):
        raise AssertionError("Model selection attempted network access")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    validate_model_dir(first_path)
    manager._register(
        InstalledModel(first_id, "test/whisper", "test", "MIT", "a" * 40, 20, first_path)
    )
    assert ModelManager(manager.root).selected().id == first_id
    assert ModelManager(manager.root).installed()[0].repository == "test/whisper"


def test_missing_tokenizer_and_non_whisper_config_are_rejected(tmp_path):
    path = tmp_path / "model"
    make_bundle(path)
    (path / "tokenizer.json").unlink()
    with pytest.raises(ValueError, match="tokenizer.json"):
        validate_model_dir(path)
    Tokenizer(models.BPE()).save(str(path / "tokenizer.json"))
    (path / "config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="Whisper configuration"):
        validate_model_dir(path)


def test_interrupted_download_retries_without_meeting_data(tmp_path, monkeypatch):
    manager = ModelManager(tmp_path / "models")
    calls = []
    progress = []

    class Sibling:
        def __init__(self, name):
            self.rfilename = name
            self.size = 100

    class Info:
        def __init__(self):
            self.sha = "a" * 40
            self.siblings = [
                Sibling(name)
                for name in ("model.bin", "config.json", "tokenizer.json", "vocabulary.txt")
            ]
            self.card_data = {"license": "mit"}

    class Api:
        def model_info(self, *args, **kwargs):
            calls.append(("metadata", args, kwargs))
            return Info()

    count = 0

    def fake_snapshot(*args, **kwargs):
        nonlocal count
        calls.append(("download", args, kwargs))
        count += 1
        stage = kwargs["local_dir"]
        if count == 1:
            (stage / "model.bin").write_bytes(b"partial")
            raise OSError("connection interrupted")
        make_bundle(stage)
        bar = kwargs["tqdm_class"](total=4, disable=True)
        bar.update(4)
        return str(stage)

    monkeypatch.setattr(model_module, "HfApi", Api)
    monkeypatch.setattr(model_module, "snapshot_download", fake_snapshot)
    monkeypatch.setattr(ModelManager, "_verify_runtime_model", lambda self, path: None)
    with pytest.raises(OSError, match="interrupted"):
        manager.download("test/whisper", progress=lambda *x: progress.append(x))
    assert manager.installed() == []
    installed = manager.download("test/whisper", progress=lambda *x: progress.append(x))
    assert installed.revision == "a" * 40
    assert manager.selected().id == installed.id
    assert count == 2
    assert any(item[0] == "Downloading model files" for item in progress)
    assert all("meeting" not in str(args) + str(kwargs) for _, args, kwargs in calls)
    assert all(kwargs.get("token") is False for _, _, kwargs in calls)
    cached = manager.download("test/whisper", progress=lambda *x: progress.append(x))
    assert cached.id == installed.id
    assert count == 2
    assert progress[-1][0] == "Already installed; using local cache"


def test_custom_repository_rejection_and_safe_model_deletion(tmp_path, monkeypatch):
    manager = ModelManager(tmp_path / "models")

    class IncompatibleInfo:
        def __init__(self):
            self.sha = "b" * 40
            self.siblings = []
            self.card_data = {"license": "mit"}

    class Api:
        def model_info(self, *args, **kwargs):
            return IncompatibleInfo()

    monkeypatch.setattr(model_module, "HfApi", Api)
    with pytest.raises(ValueError, match="CTranslate2 Whisper"):
        manager.inspect_repository("custom/not-whisper")

    meeting_file = tmp_path / "meetings" / "audio.wav"
    meeting_file.parent.mkdir()
    meeting_file.write_bytes(b"meeting data")
    model_id = uuid.uuid4().hex
    path = manager._path(model_id)
    make_bundle(path)
    manager._register(InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40, 20, path))
    manager.begin_use(model_id)
    with pytest.raises(RuntimeError, match="in use"):
        manager.delete(model_id)
    assert path.exists()
    manager.end_use(model_id)
    manager.delete(model_id)
    assert manager.installed() == []
    assert meeting_file.read_bytes() == b"meeting data"


def test_model_delete_rejects_live_process_until_shared_lock_is_released(tmp_path, monkeypatch):
    manager = ModelManager(tmp_path / "models")
    model_id = uuid.uuid4().hex
    path = manager._path(model_id)
    make_bundle(path)
    manager._register(InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40, 20, path))
    lock_path = live_model_lock_path(manager.root, model_id)
    lock_path.write_bytes(b"stable model lock")
    index_before = (manager.root / "index.json").read_bytes()
    context = multiprocessing.get_context("spawn")
    ready, release, finished = (context.Event() for _ in range(3))
    holder = context.Process(
        target=_hold_lock, args=(str(lock_path), True, ready, release, finished)
    )
    holder.start()
    try:
        assert ready.wait(10)
        started = time.monotonic()
        with pytest.raises(RuntimeError, match="in use by live transcription"):
            manager.delete(model_id)
        assert time.monotonic() - started < 2
        assert path.exists() and (manager.root / "index.json").read_bytes() == index_before
        assert not (manager.root / "trash" / model_id).exists()
        release.set()
        holder.join(timeout=10)
        assert holder.exitcode == 0 and finished.is_set()
        original_rmtree = model_module.shutil.rmtree

        def verify_lock_during_removal(target, *args, **kwargs):
            if target == manager.root / "trash" / model_id:
                with pytest.raises(TimeoutError):
                    SharedFileLock(lock_path, shared=True).acquire(timeout=0)
            return original_rmtree(target, *args, **kwargs)

        monkeypatch.setattr(model_module.shutil, "rmtree", verify_lock_during_removal)
        manager.delete(model_id)
        assert not path.exists() and not manager.installed()
        assert lock_path.read_bytes() == b"stable model lock"
    finally:
        if holder.is_alive():
            release.set()
            holder.join(timeout=5)
            if holder.is_alive():
                holder.terminate()
                holder.join(timeout=5)


def test_model_use_counts_are_shared_and_delete_waits_for_all_workers(tmp_path):
    root = tmp_path / "models"
    manager = ModelManager(root)
    first_manager = ModelManager(root)
    second_manager = ModelManager(root)
    model_id = uuid.uuid4().hex
    path = manager._path(model_id)
    make_bundle(path)
    manager._register(InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40, 20, path))
    ready = threading.Barrier(3)
    release_first = threading.Event()
    release_second = threading.Event()

    def use_model(owner, release):
        owner.begin_use(model_id)
        try:
            ready.wait(timeout=10)
            if not release.wait(timeout=10):
                raise TimeoutError("Test did not release the model")
        finally:
            owner.end_use(model_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(use_model, first_manager, release_first)
        second = pool.submit(use_model, second_manager, release_second)
        try:
            ready.wait(timeout=10)
            with pytest.raises(RuntimeError, match="in use"):
                manager.delete(model_id)
            release_first.set()
            first.result(timeout=10)
            with pytest.raises(RuntimeError, match="in use"):
                manager.delete(model_id)
            assert path.exists()
            release_second.set()
            second.result(timeout=10)
        finally:
            release_first.set()
            release_second.set()
    manager.delete(model_id)
    assert not path.exists()


def test_model_use_counts_are_scoped_to_model_root(tmp_path):
    first = ModelManager(tmp_path / "first")
    second = ModelManager(tmp_path / "second")
    model_id = uuid.uuid4().hex
    for manager in (first, second):
        path = manager._path(model_id)
        make_bundle(path)
        manager._register(
            InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40, 20, path)
        )
    first.end_use(model_id)  # Releasing an unused model remains a no-op.
    first.begin_use(model_id)
    first.begin_use(model_id)
    first.end_use(model_id)  # The first completion cannot release the second use.
    same_root = ModelManager(first.root)
    same_root.end_use(model_id)  # A different manager cannot release this use.
    second.delete(model_id)
    with pytest.raises(RuntimeError, match="in use"):
        first.delete(model_id)
    first.end_use(model_id)
    first.delete(model_id)
