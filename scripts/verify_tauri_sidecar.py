"""Exercise a frozen sidecar with disposable meeting data and a loopback provider."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import threading
import uuid
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import numpy as np

from fahmm.models import InstalledModel
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "desktop/src-tauri/binaries/fahmm-sidecar-x86_64-pc-windows-msvc.exe"


class ProviderHandler(BaseHTTPRequestHandler):
    requests: ClassVar[list[dict]] = []

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        body = json.loads(self.rfile.read(length))
        self.requests.append(body)
        response = {
            "id": "chat-test",
            "object": "chat.completion",
            "created": 1,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps(
                            {"summary": [{"text": "Thống nhất thử nghiệm", "source_ids": [1]}]}
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        payload = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        pass


class Sidecar:
    def __init__(self, env: dict[str, str]) -> None:
        self.process = subprocess.Popen(
            [str(BINARY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
        )
        self.counter = 0

    def call(self, operation: str, **params: object) -> dict:
        self.counter += 1
        request_id = f"verify-{self.counter}"
        request = {"v": 1, "kind": "request", "id": request_id, "op": operation, "params": params}
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(request, ensure_ascii=False).encode() + b"\n")
        self.process.stdin.flush()
        raw = self.process.stdout.readline()
        assert raw, f"Sidecar exited during {operation}"
        response = json.loads(raw)
        assert response["id"] == request_id
        return response

    def result(self, operation: str, **params: object) -> dict:
        response = self.call(operation, **params)
        assert response["kind"] == "response", (operation, response)
        return response["result"]

    def close(self) -> None:
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)


def verify(*, offline_only: bool = False) -> dict:
    assert BINARY.is_file(), "Build the sidecar first with scripts/build_sidecar.py"
    ProviderHandler.requests = []
    # Windows sandbox temp roots can exceed MAX_PATH before the transcript
    # staging directory is added. Keep disposable integration data near ROOT.
    with tempfile.TemporaryDirectory(prefix="tauri-", dir=ROOT / ".build") as directory:
        data_root = Path(directory)
        env = {**os.environ, "LOCALAPPDATA": directory}
        store = MeetingStore(data_root / "fahmm" / "meetings")
        meeting = store.create({"system": "speaker", "microphone": "mic"})
        store.write_chunk(meeting, "system", 0, np.ones(48_000, dtype=np.float32) * 0.1)
        store.finalize(meeting)
        run_id = uuid.uuid4().hex
        model = InstalledModel(
            uuid.uuid4().hex, "test/model", "test", "MIT", "a" * 40, 1, data_root
        )
        TranscriptStore(store).save_run(
            meeting,
            run_id,
            model,
            "vi",
            {"duration": 1},
            [
                {"id": 1, "start": 0, "end": 1, "text": "Thống nhất thử nghiệm"},
            ],
        )
        provider = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
        thread = threading.Thread(target=provider.serve_forever, daemon=True)
        thread.start()
        try:
            sidecar = Sidecar(env)
            try:
                sidecar.result("session.hello", versions=[1])
                assert [item["id"] for item in sidecar.result("meeting.list")["meetings"]] == [
                    meeting
                ]
                offline = sidecar.result("minutes.generateOffline", meetingId=meeting, runId=None)
                active_version = offline["versionId"]
                version = sidecar.result(
                    "minutes.read", meetingId=meeting, versionId=offline["versionId"]
                )["version"]
                assert version["manifest"]["review_state"] == "unverified"
                ticket = sidecar.result("media.ticket", meetingId=meeting)["ticket"]
                assert sidecar.result("media.resolve", meetingId=meeting, ticket=ticket)["size"] > 0
                assert (
                    len(sidecar.result("media.peaks", meetingId=meeting, bins=128)["peaks"]) == 128
                )

                source = data_root / "input.wav"
                with wave.open(str(source), "wb") as audio:
                    audio.setnchannels(1)
                    audio.setsampwidth(2)
                    audio.setframerate(16_000)
                    audio.writeframes(b"\0\0" * 16_000)
                imported = sidecar.result("meeting.import", nativePath=str(source))["meetingId"]
                imported_run = uuid.uuid4().hex
                TranscriptStore(store).save_run(
                    imported,
                    imported_run,
                    model,
                    "vi",
                    {"duration": 1},
                    [
                        {"id": 1, "start": 0, "end": 1, "text": "Thống nhất thử nghiệm"},
                    ],
                )
                imported_version = sidecar.result(
                    "minutes.generateOffline", meetingId=imported, runId=imported_run
                )["versionId"]
                minutes_path = data_root / "minutes.md"
                transcript_path = data_root / "transcript.txt"
                assert sidecar.result(
                    "export.writeMinutes",
                    meetingId=imported,
                    versionId=imported_version,
                    nativePath=str(minutes_path),
                    overwrite=False,
                )["saved"]
                assert sidecar.result(
                    "export.writeTranscript",
                    meetingId=imported,
                    runId=imported_run,
                    nativePath=str(transcript_path),
                    overwrite=False,
                )["saved"]
                assert "Thống nhất thử nghiệm" in minutes_path.read_text(encoding="utf-8")
                assert "Thống nhất thử nghiệm" in transcript_path.read_text(encoding="utf-8")
                sidecar.result("meeting.delete", meetingId=imported)
                assert source.is_file() and minutes_path.is_file() and transcript_path.is_file()
                assert (
                    sidecar.result("meeting.detail", meetingId=meeting)["meeting"]["id"] == meeting
                )
                if not offline_only:
                    profile = sidecar.result(
                        "provider.save",
                        name="Test provider",
                        baseUrl=f"http://127.0.0.1:{provider.server_port}/v1",
                        modelId="test-model",
                        timeoutSeconds=10,
                        profileId=None,
                        apiKey=None,
                    )["profile"]
                    assert not profile["hasKey"]
                    preview_args = {
                        "meetingId": meeting,
                        "profileId": profile["id"],
                        "selectedIds": [1],
                        "reviewedIds": [1],
                        "prompt": "Viết biên bản",
                        "maxTokens": 500,
                    }
                    assert sidecar.call("cloud.preview", **preview_args)["kind"] == "error"
                    assert not ProviderHandler.requests
                    sidecar.result("meeting.privacy", meetingId=meeting, mode="cloud_permitted")
                    cancelled = sidecar.result("cloud.preview", **preview_args)["previewId"]
                    sidecar.result("cloud.cancel", previewId=cancelled)
                    assert sidecar.call("cloud.send", previewId=cancelled)["kind"] == "error"
                    assert not ProviderHandler.requests
                    confirmed = sidecar.result("cloud.preview", **preview_args)["previewId"]
                    sidecar.result("cloud.confirm", previewId=confirmed, accepted=True)
                    active_version = sidecar.result("cloud.send", previewId=confirmed)["versionId"]
                    assert sidecar.call("cloud.send", previewId=confirmed)["kind"] == "error"
                    assert len(ProviderHandler.requests) == 1
                    assert ProviderHandler.requests[0]["messages"][1]["content"].endswith(
                        "Thống nhất thử nghiệm"
                    )
                    assert (
                        sidecar.result("minutes.read", meetingId=meeting, versionId=active_version)[
                            "version"
                        ]["manifest"]["review_state"]
                        == "unverified"
                    )
            finally:
                sidecar.close()
            restarted = Sidecar(env)
            try:
                restarted.result("session.hello", versions=[1])
                assert (
                    restarted.result("meeting.detail", meetingId=meeting)["meeting"]["id"]
                    == meeting
                )
                assert (
                    restarted.result("minutes.list", meetingId=meeting)["activeVersionId"]
                    == active_version
                )
                assert (
                    restarted.call("media.resolve", meetingId=meeting, ticket=ticket)["kind"]
                    == "error"
                )
            finally:
                restarted.close()
            return {
                "offline_no_key": "pass",
                "restricted_no_send": "not_run" if offline_only else "pass",
                "preview_cancel_confirm": "not_run" if offline_only else "pass",
                "sidecar_restart": "pass",
                "media_ticket": "pass",
                "local_document_flow": "pass",
                "provider_requests": len(ProviderHandler.requests),
            }
        finally:
            provider.shutdown()
            provider.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="Skip provider checks when Windows Credential Manager is unavailable",
    )
    args = parser.parse_args()
    print(json.dumps(verify(offline_only=args.offline_only), indent=2))
