"""App-owned Whisper installations. Reading or selecting a model is offline."""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import ctranslate2
from huggingface_hub import HfApi, snapshot_download
from tokenizers import Tokenizer
from tqdm import tqdm

from fahmm.model_catalog import BY_REPOSITORY

MODEL_ASSETS = (
    "model.bin",
    "config.json",
    "tokenizer.json",
    "vocabulary.txt",
    "vocabulary.json",
    "preprocessor_config.json",
)
ProgressCallback = Callable[[str, int, int], None]


def default_model_root() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "fahmm" / "models"


def validate_model_dir(path: Path) -> None:
    """Reject missing assets, tokenizer fallback, and obvious non-Whisper bundles."""
    path = Path(path).resolve()
    required = ("model.bin", "config.json", "tokenizer.json")
    for name in required:
        item = path / name
        if not item.is_file() or item.stat().st_size == 0 or not item.resolve().is_relative_to(path):
            raise ValueError(f"Incomplete local Whisper model: missing {name}")
    vocabulary = [path / name for name in ("vocabulary.txt", "vocabulary.json")]
    if not any(
        item.is_file() and item.stat().st_size > 0 and item.resolve().is_relative_to(path)
        for item in vocabulary
    ):
        raise ValueError("Incomplete local Whisper model: missing vocabulary")
    try:
        with (path / "config.json").open(encoding="utf-8") as file:
            config = json.load(file)
        if not isinstance(config, dict) or not isinstance(config.get("suppress_ids"), list):
            raise TypeError("Invalid Whisper configuration")
        Tokenizer.from_file(str(path / "tokenizer.json"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid local Whisper model assets: {exc}") from exc
    if not ctranslate2.contains_model(str(path)):
        raise ValueError("The directory does not contain a CTranslate2 model")


@dataclass(frozen=True)
class InstalledModel:
    id: str
    repository: str
    publisher: str
    license: str
    revision: str
    bytes: int
    path: Path


@dataclass(frozen=True)
class RemoteModel:
    repository: str
    publisher: str
    license: str
    revision: str
    files: tuple[tuple[str, int], ...]

    @property
    def estimated_bytes(self) -> int:
        return sum(size for _, size in self.files)


class ModelManager:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_model_root()
        self._active_ids: set[str] = set()
        self._usage_lock = threading.RLock()

    def _index(self) -> dict:
        target = self.root / "index.json"
        if not target.exists():
            return {"schema_version": 1, "selected": None, "installations": {}}
        with target.open(encoding="utf-8") as file:
            data = json.load(file)
        if data.get("schema_version") != 1 or not isinstance(data.get("installations"), dict):
            raise ValueError("Incompatible local model index")
        return data

    def _save_index(self, data: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        target = self.root / "index.json"
        temporary = self.root / f".index-{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _path(self, model_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", model_id):
            raise ValueError("Invalid model installation ID")
        return self.root / "installed" / model_id

    def installed(self) -> list[InstalledModel]:
        data = self._index()
        result = []
        for model_id, record in data["installations"].items():
            path = self._path(model_id)
            validate_model_dir(path)
            result.append(InstalledModel(model_id, path=path, **record))
        return result

    def get(self, model_id: str) -> InstalledModel:
        data = self._index()
        record = data["installations"].get(model_id)
        if record is None:
            raise KeyError("Model is not installed")
        path = self._path(model_id)
        validate_model_dir(path)
        return InstalledModel(model_id, path=path, **record)

    def selected(self) -> InstalledModel | None:
        model_id = self._index()["selected"]
        return self.get(model_id) if model_id else None

    def select(self, model_id: str) -> InstalledModel:
        model = self.get(model_id)
        data = self._index()
        data["selected"] = model_id
        self._save_index(data)
        return model

    def begin_use(self, model_id: str) -> InstalledModel:
        with self._usage_lock:
            model = self.get(model_id)
            self._active_ids.add(model_id)
            return model

    def end_use(self, model_id: str) -> None:
        with self._usage_lock:
            self._active_ids.discard(model_id)

    def delete(self, model_id: str) -> None:
        with self._usage_lock:
            if model_id in self._active_ids:
                raise RuntimeError("This model is in use by a transcription job")
            model = self.get(model_id)
            expected_root = (self.root / "installed").resolve()
            if not model.path.resolve().is_relative_to(expected_root):
                raise ValueError("Refusing to delete a path outside managed models")
            trash = self.root / "trash" / model_id
            trash.parent.mkdir(parents=True, exist_ok=True)
            if trash.exists():
                raise FileExistsError("A previous model deletion is incomplete")
            os.replace(model.path, trash)
            try:
                data = self._index()
                del data["installations"][model_id]
                if data["selected"] == model_id:
                    data["selected"] = next(iter(data["installations"]), None)
                self._save_index(data)
            except Exception:
                os.replace(trash, model.path)
                raise
            if not trash.resolve().is_relative_to((self.root / "trash").resolve()):
                raise ValueError("Refusing to remove a path outside managed model trash")
            shutil.rmtree(trash)

    def _register(self, model: InstalledModel) -> None:
        if model.path.resolve() != self._path(model.id).resolve():
            raise ValueError("Model path is outside the managed installation directory")
        validate_model_dir(model.path)
        data = self._index()
        data["installations"][model.id] = {
            "repository": model.repository,
            "publisher": model.publisher,
            "license": model.license,
            "revision": model.revision,
            "bytes": model.bytes,
        }
        if data["selected"] is None:
            data["selected"] = model.id
        self._save_index(data)

    @staticmethod
    def _verify_runtime_model(path: Path) -> None:
        """A generic CT2 model can pass file checks but cannot load as Whisper."""
        ctranslate2.models.Whisper(str(path), device="cpu", compute_type="int8")

    def inspect_repository(self, repository: str, *, revision: str | None = None) -> RemoteModel:
        """Explicit Hub metadata request; accepts only repository IDs, never meeting data."""
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Enter a Hugging Face repository ID as publisher/name")
        if repository in BY_REPOSITORY and revision is None:
            revision = BY_REPOSITORY[repository].revision
        info = HfApi().model_info(
            repository, revision=revision, files_metadata=True, token=False
        )
        commit = info.sha
        if not re.fullmatch(r"[0-9a-f]{40}", commit or ""):
            raise ValueError("Repository did not return a fixed model revision")
        files = {item.rfilename: item for item in info.siblings or []}
        if not all(name in files for name in ("model.bin", "config.json", "tokenizer.json")):
            raise ValueError("Repository is not a complete CTranslate2 Whisper model")
        if not any(name in files for name in ("vocabulary.txt", "vocabulary.json")):
            raise ValueError("Repository has no compatible Whisper vocabulary")
        selected = [files[name] for name in MODEL_ASSETS if name in files]
        if any(item.size is None for item in selected):
            raise ValueError("Repository does not provide file sizes for the disk check")
        card = info.card_data or {}
        license_name = card.get("license", "unknown") if isinstance(card, dict) else "unknown"
        return RemoteModel(
            repository,
            repository.split("/", 1)[0],
            str(license_name),
            commit,
            tuple((item.rfilename, item.size) for item in selected),
        )

    def download(
        self,
        repository: str,
        *,
        revision: str | None = None,
        progress: ProgressCallback | None = None,
    ) -> InstalledModel:
        """Explicit operation; callers must invoke this only after a Download action."""
        report = progress or (lambda stage, current, total: None)
        requested_revision = revision or (
            BY_REPOSITORY[repository].revision if repository in BY_REPOSITORY else None
        )
        for existing in self.installed():
            if existing.repository == repository and (
                requested_revision is None or existing.revision == requested_revision
            ):
                self.select(existing.id)
                report("Already installed; using local cache", 1, 1)
                return existing
        report("Inspecting repository", 0, 1)
        remote = self.inspect_repository(repository, revision=revision)
        staging_key = sha256(f"{repository}@{remote.revision}".encode()).hexdigest()
        staging = self.root / "staging" / staging_key
        staging.mkdir(parents=True, exist_ok=True)
        staged_bytes = sum(
            (staging / name).stat().st_size for name, _ in remote.files
            if (staging / name).is_file()
        )
        needed = max(0, remote.estimated_bytes - staged_bytes) + 64 * 1024 * 1024
        if shutil.disk_usage(self.root).free < needed:
            raise OSError("Not enough free disk space for this model download")

        class FileProgress(tqdm):
            def update(self, n: float = 1) -> bool | None:
                result = super().update(n)
                report("Downloading model files", int(self.n), int(self.total or 0))
                return result

        report("Downloading model files", 0, len(remote.files))
        snapshot_download(
            repository,
            revision=remote.revision,
            local_dir=staging,
            allow_patterns=list(MODEL_ASSETS),
            token=False,
            tqdm_class=FileProgress,
        )
        report("Validating local model", 0, 1)
        validate_model_dir(staging)
        self._verify_runtime_model(staging)
        installation_id = uuid.uuid4().hex
        target = self._path(installation_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
        model = InstalledModel(
            installation_id,
            repository,
            remote.publisher,
            remote.license,
            remote.revision,
            sum((target / name).stat().st_size for name, _ in remote.files),
            target,
        )
        try:
            self._register(model)
        except Exception:
            os.replace(target, staging)
            raise
        report("Installed", 1, 1)
        return model
