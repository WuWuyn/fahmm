"""Single-process service owner for the local Tauri sidecar."""

from __future__ import annotations

import contextlib
import io
import json
import re
import secrets
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fahmm.bridge.protocol import (
    CONTRACT,
    MAX_FRAME_BYTES,
    VERSION,
    FrameError,
    encode_frame,
    validate_frame,
)

_SAFE_ID = re.compile(CONTRACT["requestIdPattern"])


class BridgeApplication:
    """Own service instances for one desktop session; no Qt or network listener."""

    def __init__(self, data_root: Path | None = None) -> None:
        from fahmm.asr_jobs import ASRJobController
        from fahmm.audio import SoundCardCapture
        from fahmm.bridge.model_jobs import ModelInstallJobs
        from fahmm.cloud_minutes import CloudMinutesService
        from fahmm.controller import SessionController
        from fahmm.library import MeetingLibrary
        from fahmm.local_llm import LocalMinutesJobs
        from fahmm.meeting_deletion import MeetingDeletionService
        from fahmm.meeting_export import MeetingExportService
        from fahmm.minutes_store import MinutesStore
        from fahmm.models import ModelManager
        from fahmm.offline_minutes import OfflineMinutesService
        from fahmm.providers import ProviderProfiles
        from fahmm.reports.service import ReportService
        from fahmm.storage import MeetingStore
        from fahmm.transcripts import TranscriptStore

        meetings_root = data_root / "meetings" if data_root is not None else None
        self.store = MeetingStore(meetings_root)
        self.models = ModelManager(data_root / "models" if data_root is not None else None)
        self.model_jobs = ModelInstallJobs(self.models)
        self.profiles = ProviderProfiles(
            data_root / "providers.json" if data_root is not None else None
        )
        self.recorder = SessionController(SoundCardCapture(), self.store)
        self.library = MeetingLibrary(self.store)
        self.deletion = MeetingDeletionService(self.store)
        self.asr = ASRJobController(self.store, self.models)
        self.offline_minutes = OfflineMinutesService(self.store)
        self.local_minutes = LocalMinutesJobs(self.store, self.models.root.parent / "local_llm.json")
        self.cloud_minutes = CloudMinutesService(self.store, self.profiles)
        self.export = MeetingExportService(self.store, self.models.root)
        self.transcripts = TranscriptStore(self.store)
        self.reports = ReportService(self.store, self.transcripts, self.models.root.parent)
        self.minutes = MinutesStore(self.store)
        self._cloud_previews: dict[str, tuple[Any, Any, float]] = {}
        self._media_tickets: dict[str, tuple[str, Path, float]] = {}
        self.handshake_complete = False

    def handle(self, frame: dict[str, Any]) -> dict[str, Any]:
        request_id = frame["id"]
        operation = frame["op"]
        params = frame["params"]
        if operation == "session.hello":
            supported = params["versions"]
            if VERSION not in supported:
                return self._error(
                    request_id, "UNSUPPORTED_VERSION", "Incompatible desktop protocol"
                )
            self.handshake_complete = True
            result = {"selectedVersion": VERSION, "capabilities": list(CONTRACT["operations"])}
        elif not self.handshake_complete:
            return self._error(request_id, "INVALID_REQUEST", "Start a desktop session first")
        elif operation == "system.health":
            result = {"status": "ready"}
        elif operation == "report.models":
            result = self.reports.models()
        elif operation == "report.status":
            result = {"report": self.reports.status()}
        elif operation == "report.addFile":
            result = {"report": self.reports.add_file(params["nativePath"])}
        elif operation == "report.addTranscript":
            result = {"report": self.reports.add_transcript(params["meetingId"])}
        elif operation == "report.clear":
            result = {"report": self.reports.clear()}
        elif operation == "report.start":
            self.reports.start(params["model"], params["form"])
            result = {"started": True}
        elif operation == "report.pull":
            self.reports.pull(params["model"])
            result = {"started": True}
        elif operation == "report.cancel":
            self.reports.cancel()
            result = {"cancelled": True}
        elif operation == "report.export":
            result = self.reports.export(params["nativePath"])
        elif operation == "recording.devices":
            devices = self.recorder.capture.list_devices()
            result = {
                source: [{"id": device.id, "name": device.name} for device in devices[source]]
                for source in ("system", "microphone")
            }
        elif operation == "recording.start":
            result = {"meetingId": self.recorder.start(params["systemId"], params["microphoneId"])}
        elif operation == "recording.pause":
            self.recorder.pause()
            result = {"state": self.recorder.snapshot().state.value}
        elif operation == "recording.resume":
            self.recorder.resume()
            result = {"state": self.recorder.snapshot().state.value}
        elif operation == "recording.stop":
            self.recorder.stop()
            result = {"state": self.recorder.snapshot().state.value}
        elif operation == "recording.snapshot":
            snapshot = self.recorder.snapshot()
            result = {
                "state": snapshot.state.value,
                "seconds": snapshot.seconds,
                "meetingId": snapshot.meeting_id,
                "error": snapshot.error,
                "skippedChunks": len(snapshot.skipped_chunks),
                "levels": snapshot.levels,
            }
        elif operation == "recording.incomplete":
            result = {
                "meetings": [
                    {"id": item["id"], "name": item["name"], "createdAt": item["created_at"]}
                    for item in self.store.incomplete()
                ]
            }
        elif operation == "recording.recover":
            meeting_id = params["meetingId"]
            if meeting_id not in {item["id"] for item in self.store.incomplete()}:
                raise ValueError("Meeting is not recoverable")
            self.recorder.recover(meeting_id)
            result = {"state": self.recorder.snapshot().state.value}
        elif operation == "meeting.list":
            result = {"meetings": [asdict(item) for item in self.library.list_meetings()]}
        elif operation == "meeting.detail":
            result = {"meeting": asdict(self.library.get(params["meetingId"]))}
        elif operation == "meeting.rename":
            result = {"meeting": asdict(self.library.rename(params["meetingId"], params["name"]))}
        elif operation == "meeting.privacy":
            result = {
                "meeting": asdict(
                    self.library.set_privacy_mode(params["meetingId"], params["mode"])
                )
            }
        elif operation == "meeting.import":
            from fahmm.media import import_audio

            source = Path(params["nativePath"])
            if not source.is_absolute():
                raise ValueError("Choose an absolute audio file")
            resolved = source.resolve(strict=False)
            if any(
                resolved.is_relative_to(root.resolve())
                for root in (self.store.root, self.models.root)
            ):
                raise ValueError("Cannot import a file inside managed application data")
            result = {"meetingId": import_audio(self.store, source)}
        elif operation == "meeting.delete":
            self.deletion.delete(params["meetingId"])
            result = {"deleted": True}
        elif operation == "meeting.cleanupList":
            result = {
                "deletions": self.deletion.incomplete_deletions(),
                "imports": self.deletion.orphan_imports(),
            }
        elif operation == "meeting.retryCleanup":
            self.deletion.retry_cleanup(params["meetingId"])
            result = {"cleaned": True}
        elif operation == "meeting.cleanImport":
            result = {
                "cleaned": self.deletion.cleanup_orphan_import(params["meetingId"], confirmed=True)
            }
        elif operation == "transcript.list":
            metadata = self.store.metadata(params["meetingId"])
            result = {
                "runs": self.transcripts.list_runs(params["meetingId"]),
                "activeRunId": metadata.get("active_run"),
            }
        elif operation == "transcript.read":
            result = {"run": self.transcripts.read_run(params["meetingId"], params["runId"])}
        elif operation == "transcript.saveEdits":
            edits = params["edits"]
            if len(edits) > 10000 or any(
                not isinstance(key, str)
                or not re.fullmatch(r"\d+", key)
                or not isinstance(text, str)
                for key, text in edits.items()
            ):
                raise ValueError("Invalid transcript edits")
            self.transcripts.save_edits(
                params["meetingId"],
                params["runId"],
                {int(key): text for key, text in edits.items()},
            )
            result = {"saved": True}
        elif operation == "transcript.select":
            self.transcripts.select_run(params["meetingId"], params["runId"])
            result = {"activeRunId": params["runId"]}
        elif operation == "minutes.list":
            metadata = self.store.metadata(params["meetingId"])
            result = {
                "versions": self.minutes.list_versions(params["meetingId"]),
                "activeVersionId": metadata.get("active_minutes_version"),
            }
        elif operation == "minutes.read":
            result = {
                "version": self.minutes.read_version(params["meetingId"], params["versionId"])
            }
        elif operation == "minutes.renderBody":
            from fahmm.meeting_export import render_minutes

            version = self.minutes.read_version(params["meetingId"], params["versionId"])
            result = {"markdown": render_minutes(version["content"])}
        elif operation == "minutes.edit":
            result = {
                "versionId": self.minutes.edit_version(
                    params["meetingId"], params["versionId"], params["content"]
                )
            }
        elif operation == "minutes.editDomain":
            result = {
                "versionId": self.minutes.edit_domain_version(
                    params["meetingId"], params["versionId"], params["content"]
                )
            }
        elif operation == "minutes.setType":
            result = {
                "versionId": self.minutes.set_domain_type(
                    params["meetingId"], params["versionId"], params["meetingType"]
                )
            }
        elif operation == "minutes.sourceDrift":
            result = {
                "sources": self.minutes.source_drift(params["meetingId"], params["versionId"])
            }
        elif operation == "minutes.select":
            self.minutes.select_version(params["meetingId"], params["versionId"])
            result = {"activeVersionId": params["versionId"]}
        elif operation == "minutes.approve":
            self.minutes.approve_version(params["meetingId"], params["versionId"])
            result = {"reviewState": "approved"}
        elif operation == "minutes.template":
            result = {"template": self.minutes.read_template(params["meetingId"])}
        elif operation == "minutes.saveTemplate":
            self.minutes.save_template(params["meetingId"], params["template"])
            result = {"saved": True}
        elif operation == "model.catalog":
            from fahmm.model_catalog import CATALOG

            result = {
                "choices": [asdict(choice) for choice in CATALOG],
                "installed": [
                    {key: value for key, value in asdict(model).items() if key != "path"}
                    for model in self.models.installed()
                ],
                "selectedId": self.models._index()["selected"],
            }
        elif operation == "model.select":
            result = {"selectedId": self.models.select(params["modelId"]).id}
        elif operation == "model.install":
            result = {"jobId": self.model_jobs.start(params["repository"])}
        elif operation == "model.installStatus":
            result = {
                "jobId": self.model_jobs.snapshot().job_id,
                "state": self.model_jobs.snapshot().state,
                "stage": self.model_jobs.snapshot().stage,
                "progress": self.model_jobs.snapshot().progress,
                "modelId": self.model_jobs.snapshot().model_id,
                "error": self.model_jobs.snapshot().error,
            }
        elif operation == "model.delete":
            self.models.delete(params["modelId"])
            result = {"deleted": True}
        elif operation == "asr.start":
            result = {
                "runId": self.asr.start(params["meetingId"], params["modelId"], params["language"])
            }
        elif operation == "asr.startFrom":
            result = {
                "runId": self.asr.start(
                    params["meetingId"],
                    params["modelId"],
                    params["language"],
                    params["startSeconds"],
                )
            }
        elif operation == "asr.cancel":
            self.asr.cancel()
            result = {"state": self.asr.snapshot().state}
        elif operation == "asr.retry":
            result = {"runId": self.asr.retry()}
        elif operation == "asr.status":
            snapshot = self.asr.snapshot()
            result = {
                "state": snapshot.state,
                "meetingId": snapshot.meeting_id,
                "runId": snapshot.run_id,
                "progress": min(1.0, max(0.0, snapshot.progress))
                if snapshot.progress is not None
                else None,
                "segmentCount": snapshot.segment_count,
                "error": "Transcription failed" if snapshot.error else None,
            }
        elif operation == "minutes.generateOffline":
            result = {
                "versionId": self.offline_minutes.generate(
                    params["meetingId"], params.get("runId"), meeting_type=params.get("meetingType")
                )
            }
        elif operation == "llm.availability":
            result = self.local_minutes.availability()
        elif operation == "llm.select":
            self.local_minutes.select(params["model"])
            result = {"selectedModel": self.local_minutes.selected_model()}
        elif operation == "llm.pullStart":
            self.local_minutes.start_pull()
            result = {"started": True}
        elif operation == "llm.pullStatus":
            result = self.local_minutes.status("_pull")
        elif operation == "minutes.generateLocalStart":
            self.local_minutes.start_generation(params["meetingId"], params["meetingType"])
            result = {"started": True}
        elif operation == "minutes.localStatus":
            result = self.local_minutes.status("_generation")
        elif operation == "cloud.preview":
            snapshot = self.cloud_minutes.prepare(
                params["meetingId"],
                params["profileId"],
                set(params["selectedIds"]),
                set(params["reviewedIds"]),
                prompt=params["prompt"],
                max_tokens=params["maxTokens"],
            )
            preview_id = secrets.token_urlsafe(24)
            self._cloud_previews[preview_id] = (snapshot, None, time.monotonic() + 600)
            result = {"previewId": preview_id, "preview": snapshot.preview}
        elif operation == "cloud.cancel":
            result = {"cancelled": self._cloud_previews.pop(params["previewId"], None) is not None}
        elif operation == "cloud.confirm":
            preview_id = params["previewId"]
            stored = self._cloud_previews.get(preview_id)
            if stored is None or stored[2] < time.monotonic() or stored[1] is not None:
                self._cloud_previews.pop(preview_id, None)
                raise ValueError("Preview is missing, expired, or already confirmed")
            snapshot, _, expiry = stored
            if not params["accepted"]:
                self._cloud_previews.pop(preview_id)
                result = {"confirmed": False}
            else:
                authorization = self.cloud_minutes.confirm(snapshot, True)
                self._cloud_previews[preview_id] = (snapshot, authorization, expiry)
                result = {"confirmed": True}
        elif operation == "cloud.send":
            stored = self._cloud_previews.pop(params["previewId"], None)
            if stored is None or stored[2] < time.monotonic() or stored[1] is None:
                raise PermissionError("Preview and confirmation are required for each send")
            snapshot, authorization, _ = stored
            result = {
                "versionId": self.cloud_minutes.generate(
                    snapshot, authorization, meeting_type=params.get("meetingType")
                )
            }
        elif operation == "provider.list":
            result = {
                "profiles": [
                    {
                        **asdict(profile),
                        "hasKey": self.profiles.credentials.get_key(profile.id) is not None,
                    }
                    for profile in self.profiles.list_profiles()
                ]
            }
        elif operation == "provider.save":
            profile = self.profiles.save(
                params["name"],
                params["baseUrl"],
                params["modelId"],
                params["timeoutSeconds"],
                profile_id=params["profileId"],
                api_key=params["apiKey"],
            )
            result = {
                "profile": {
                    **asdict(profile),
                    "hasKey": self.profiles.credentials.get_key(profile.id) is not None,
                }
            }
        elif operation == "provider.delete":
            self.profiles.delete(params["profileId"])
            result = {"deleted": True}
        elif operation == "export.minutesMarkdown":
            result = {
                "markdown": self.export.minutes_markdown(params["meetingId"], params["versionId"])
            }
        elif operation == "export.transcriptText":
            result = {"text": self.export.transcript_text(params["meetingId"], params["runId"])}
        elif operation == "export.transcriptPlainText":
            result = {"text": self.export.transcript_plain_text(params["meetingId"], params["runId"])}
        elif operation == "export.audioInfo":
            result = self.export.audio_info(params["meetingId"])
        elif operation == "export.writeMinutes":
            target = self.export.export_minutes(
                params["meetingId"],
                params["versionId"],
                Path(params["nativePath"]),
                overwrite=params["overwrite"],
            )
            result = {"saved": target is not None, "displayName": target.name if target else ""}
        elif operation == "export.writeMinutesDocx":
            target = self.export.export_minutes_docx(
                params["meetingId"],
                params["versionId"],
                Path(params["nativePath"]),
                overwrite=params["overwrite"],
            )
            result = {"saved": target is not None, "displayName": target.name if target else ""}
        elif operation == "export.writeTranscript":
            target = self.export.export_transcript(
                params["meetingId"],
                params["runId"],
                Path(params["nativePath"]),
                overwrite=params["overwrite"],
            )
            result = {"saved": target is not None, "displayName": target.name if target else ""}
        elif operation == "export.writeTranscriptPlain":
            target = self.export.export_transcript_plain(
                params["meetingId"], params["runId"], Path(params["nativePath"]),
                overwrite=params["overwrite"],
            )
            result = {"saved": target is not None, "displayName": target.name if target else ""}
        elif operation == "export.writeAudio":
            target = self.export.export_audio(
                params["meetingId"], Path(params["nativePath"]), overwrite=params["overwrite"],
            )
            result = {"saved": target is not None, "displayName": target.name if target else ""}
        elif operation == "media.ticket":
            meeting_id = params["meetingId"]
            path = self.library.audio_path(meeting_id)
            result = self._issue_media_ticket(meeting_id, path)
        elif operation == "media.peaks":
            from fahmm.bridge.media_adapter import waveform_peaks

            result = waveform_peaks(self.library.audio_path(params["meetingId"]), params["bins"])
        elif operation == "media.fallback":
            from fahmm.bridge.media_adapter import managed_playback_wav

            meeting_id = params["meetingId"]
            path = managed_playback_wav(self.store, self.library, meeting_id)
            result = self._issue_media_ticket(meeting_id, path)
        elif operation == "media.resolve":
            ticket = params["ticket"]
            stored = self._media_tickets.get(ticket)
            if stored is None or stored[0] != params["meetingId"] or stored[2] < time.monotonic():
                self._media_tickets.pop(ticket, None)
                raise PermissionError("Media ticket is invalid or expired")
            original = self.library.audio_path(stored[0])
            playback = self.store._meeting_dir(stored[0]) / "playback.wav"
            path = stored[1]
            if path != original and path != playback:
                raise PermissionError("Meeting audio changed")
            if not path.is_file() or not path.resolve().is_relative_to(
                self.store._meeting_dir(stored[0]).resolve()
            ):
                raise PermissionError("Meeting audio is unavailable")
            result = {
                "nativePath": str(path),
                "contentType": self._audio_type(path),
                "size": path.stat().st_size,
            }
        else:
            return self._error(request_id, "UNSUPPORTED_OPERATION", "Operation is unavailable")
        return {
            "v": VERSION,
            "kind": "response",
            "id": request_id,
            "op": operation,
            "result": result,
        }

    @staticmethod
    def _audio_type(path: Path) -> str:
        return {
            ".wav": "audio/wav",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".flac": "audio/flac",
        }.get(path.suffix.lower(), "application/octet-stream")

    def _issue_media_ticket(self, meeting_id: str, path: Path) -> dict[str, str]:
        ticket = secrets.token_urlsafe(32)
        self._media_tickets[ticket] = (meeting_id, path, time.monotonic() + 3600)
        return {"ticket": ticket, "contentType": self._audio_type(path)}

    @staticmethod
    def _error(request_id: str, code: str, message: str) -> dict[str, Any]:
        return {
            "v": VERSION,
            "kind": "error",
            "id": request_id,
            "error": {"code": code, "message": message},
        }


def serve() -> int:
    """Read bounded JSON lines until the desktop host closes stdin."""
    from fahmm.single_instance import AlreadyRunningError, SingleInstanceLock
    from fahmm.storage import MeetingStore

    wire = sys.stdout.buffer
    stdin = sys.stdin.buffer
    # Keep Python print() from adding non-protocol text to stdout.
    with contextlib.redirect_stdout(io.StringIO()):
        data_root = MeetingStore().root.parent
        instance = SingleInstanceLock(data_root)
        try:
            instance.acquire()
        except AlreadyRunningError:
            sys.stderr.write("fahmm is already open for this local data folder\n")
            return 2
        try:
            application = BridgeApplication()
            while raw := stdin.readline(MAX_FRAME_BYTES + 1):
                request_id = "protocol"
                try:
                    # Preserve a valid correlation ID even when another field is invalid.
                    candidate = json.loads(raw)
                    if (
                        isinstance(candidate, dict)
                        and isinstance(candidate.get("id"), str)
                        and _SAFE_ID.fullmatch(candidate["id"])
                    ):
                        request_id = candidate["id"]
                except (UnicodeDecodeError, json.JSONDecodeError):
                    pass
                try:
                    request = validate_frame(raw)
                    if request["kind"] != "request":
                        raise FrameError("INVALID_REQUEST")
                    response = application.handle(request)
                except FrameError as exc:
                    code = str(exc) if str(exc) in CONTRACT["errorCodes"] else "INVALID_REQUEST"
                    response = BridgeApplication._error(request_id, code, "Invalid desktop request")
                except Exception as exc:
                    sys.stderr.write(f"Bridge operation failed: {type(exc).__name__}\n")
                    response = BridgeApplication._error(
                        request_id, "OPERATION_FAILED", "Operation failed"
                    )
                wire.write(encode_frame(response))
                wire.flush()
        finally:
            instance.release()
    return 0
