"""Background model installation for the desktop protocol."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass

from fahmm.model_catalog import BY_REPOSITORY
from fahmm.models import ModelManager


@dataclass(frozen=True)
class InstallSnapshot:
    job_id: str | None = None
    state: str = "idle"
    stage: str = ""
    progress: float | None = None
    model_id: str | None = None
    error: str | None = None


class ModelInstallJobs:
    def __init__(self, models: ModelManager) -> None:
        self.models = models
        self._lock = threading.RLock()
        self._snapshot = InstallSnapshot()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> InstallSnapshot:
        with self._lock:
            return self._snapshot

    def start(self, repository: str) -> str:
        if repository not in BY_REPOSITORY:
            raise ValueError("Choose a model from the reviewed catalog")
        with self._lock:
            if self._snapshot.state == "running":
                raise RuntimeError("A model installation is already running")
            job_id = uuid.uuid4().hex
            self._snapshot = InstallSnapshot(job_id, "running", "Starting", 0.0)
            self._thread = threading.Thread(target=self._run, args=(repository,), daemon=True)
            self._thread.start()
            return job_id

    def _run(self, repository: str) -> None:
        def progress(stage: str, current: int, total: int) -> None:
            with self._lock:
                fraction = max(0.0, min(1.0, current / total)) if total > 0 else None
                self._snapshot = InstallSnapshot(self._snapshot.job_id, "running", stage, fraction)

        try:
            model = self.models.download(repository, progress=progress)
            with self._lock:
                self._snapshot = InstallSnapshot(
                    self._snapshot.job_id, "completed", "Installed", 1.0, model.id
                )
        except Exception:
            with self._lock:
                self._snapshot = InstallSnapshot(
                    self._snapshot.job_id,
                    "error",
                    "Failed",
                    None,
                    error="Model installation failed",
                )

    def wait(self, timeout: float = 10.0) -> None:
        if self._thread is not None:
            self._thread.join(timeout)
