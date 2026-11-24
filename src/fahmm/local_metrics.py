"""Privacy-preserving, local-only measurements for one AI minutes invocation."""

from __future__ import annotations

import math
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from fahmm.minutes_store import _atomic_json

_COUNT_FIELDS = ("prompt_eval_count", "prompt_eval_cached_count", "eval_count")
_DURATION_FIELDS = (
    "total_duration_ns",
    "load_duration_ns",
    "prompt_eval_duration_ns",
    "eval_duration_ns",
)
_REASONS = {"stop", "length", "load", "unload"}
_PHASES = {"chunk", "reduce"}
_STATES = {"completed", "failed", "cancelled", "timed_out", "worker_stuck"}


class LocalGenerationMetrics:
    """Never accept or persist prompts, model outputs, excerpts, or error text."""

    def __init__(self, directory: Path, job_id: str, *, resumed: bool) -> None:
        if not re.fullmatch(r"[0-9a-f]{32}", job_id):
            raise ValueError("Invalid AI metrics job ID")
        self.path = directory / f"{job_id}.json"
        self.started = time.monotonic()
        self._enabled = True
        self.data = {
            "schema_version": 1,
            "job_id": job_id,
            "resumed": resumed,
            "wire_mode": None,
            "model": None,
            "model_digest": None,
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "state": "running",
            "wall_seconds": None,
            "model_calls": 0,
            "reduce_calls": 0,
            "post_attempts": 0,
            "post_count_complete": True,
            "http_json_retries": 0,
            "validation_retries": 0,
            "split_attempts": {"chunk": 0, "reduce": 0},
            "posts": [],
        }
        try:
            if (
                directory.is_symlink()
                or directory.is_junction()
                or directory.parent.is_symlink()
                or directory.parent.is_junction()
            ):
                raise ValueError("AI metrics directory must not be a link")
            # Never recreate an already deleted meeting while preparing metrics.
            directory.parent.mkdir(exist_ok=True)
            directory.mkdir(exist_ok=True)
            if (
                directory.is_symlink()
                or directory.is_junction()
                or directory.parent.is_symlink()
                or directory.parent.is_junction()
            ):
                raise ValueError("AI metrics directory must not be a link")
        except (OSError, ValueError):
            self._disable()
        self._persist()

    def _disable(self) -> None:
        if self._enabled:
            self._enabled = False
            try:
                sys.stderr.write("Local AI metrics could not be saved.\n")
            except (OSError, ValueError):
                return

    def _persist(self) -> None:
        if self._enabled:
            try:
                _atomic_json(self.path, self.data)
            except OSError:
                self._disable()

    def model_call(self, phase: str, *, counts_known: bool) -> None:
        if phase not in _PHASES:
            raise ValueError("Invalid AI metrics phase")
        self.data["model_calls"] += 1
        self.data["reduce_calls"] += int(phase == "reduce")
        if not counts_known:
            self.data["post_count_complete"] = False
        self._persist()

    def identify_model(self, model: str, digest: str) -> None:
        if isinstance(model, str) and re.fullmatch(r"[A-Za-z0-9._:/-]{1,200}", model):
            self.data["model"] = model
        if isinstance(digest, str) and re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", digest):
            self.data["model_digest"] = digest
        self._persist()

    def set_wire_mode(self, mode: str) -> None:
        if mode not in ("full", "compact"):
            raise ValueError("Invalid AI metrics wire mode")
        self.data["wire_mode"] = mode
        self._persist()

    def validation_retry(self) -> None:
        self.data["validation_retries"] += 1
        self._persist()

    def post_count_incomplete(self) -> None:
        self.data["post_count_complete"] = False
        self._persist()

    def split(self, phase: str) -> None:
        if phase not in _PHASES:
            raise ValueError("Invalid AI metrics phase")
        self.data["split_attempts"][phase] += 1
        self._persist()

    def worker_event(self, call: int, phase: str, event: dict) -> None:
        if phase not in _PHASES or type(call) is not int or call < 1 or not isinstance(event, dict):
            self.data["post_count_complete"] = False
            self._persist()
            return
        attempt = event.get("attempt")
        if type(attempt) is not int or attempt not in (1, 2):
            self.data["post_count_complete"] = False
            self._persist()
            return
        posts = self.data["posts"]
        if event.get("type") == "post_started":
            if any(row["model_call"] == call and row["attempt"] == attempt for row in posts):
                self.data["post_count_complete"] = False
            else:
                posts.append(
                    {
                        "model_call": call,
                        "attempt": attempt,
                        "phase": phase,
                        "state": "started",
                        "wall_seconds": None,
                        "done_reason": None,
                        **{name: None for name in (*_COUNT_FIELDS, *_DURATION_FIELDS)},
                    }
                )
                self.data["post_attempts"] += 1
                self.data["http_json_retries"] += int(attempt == 2)
        elif event.get("type") == "post_finished":
            row = next(
                (
                    item
                    for item in posts
                    if item["model_call"] == call and item["attempt"] == attempt
                ),
                None,
            )
            if row is None or row["state"] != "started":
                self.data["post_count_complete"] = False
            else:
                row["state"] = "finished" if event.get("completed") is True else "interrupted"
                wall = event.get("wall_seconds")
                row["wall_seconds"] = (
                    round(wall, 3)
                    if type(wall) in (int, float) and math.isfinite(wall) and wall >= 0
                    else None
                )
                reason = event.get("done_reason")
                row["done_reason"] = (
                    reason if isinstance(reason, str) and reason in _REASONS else None
                )
                for name in (*_COUNT_FIELDS, *_DURATION_FIELDS):
                    value = event.get(name)
                    row[name] = value if type(value) is int and 0 <= value <= 10**18 else None
        else:
            self.data["post_count_complete"] = False
        self._persist()

    def finish(self, state: str) -> None:
        if state not in _STATES:
            raise ValueError("Invalid AI metrics state")
        for row in self.data["posts"]:
            if row["state"] == "started":
                row["state"] = "interrupted"
                self.data["post_count_complete"] = False
        self.data["finished_at"] = datetime.now(UTC).isoformat()
        self.data["wall_seconds"] = round(max(0, time.monotonic() - self.started), 3)
        self.data["state"] = state
        self._persist()
