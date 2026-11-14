import json
import socket
import uuid

import pytest
from tokenizers import Tokenizer, models

from fahmm import models as model_module
from fahmm.models import InstalledModel, ModelManager, validate_model_dir


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
    manager._register(InstalledModel(model_id, "test/whisper", "test", "MIT", "a" * 40,
                                     20, path))
    manager.begin_use(model_id)
    with pytest.raises(RuntimeError, match="in use"):
        manager.delete(model_id)
    assert path.exists()
    manager.end_use(model_id)
    manager.delete(model_id)
    assert manager.installed() == []
    assert meeting_file.read_bytes() == b"meeting data"
