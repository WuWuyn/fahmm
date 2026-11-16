import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar

import httpx
import pytest
from openai import APIConnectionError
from test_cloud_minutes import make_cloud_service

from fahmm import provider_transport
from fahmm.minutes_store import MinutesStore
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.provider_transport import ProviderError


class ProviderHandler(BaseHTTPRequestHandler):
    status = 200
    delay = 0.0
    requests: ClassVar[list] = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append((self.path, body, self.headers.get("Authorization")))
        if self.delay:
            time.sleep(self.delay)
        payload = {
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "# Biên bản\nChưa rõ"},
                    "finish_reason": "stop",
                }
            ]
        }
        raw = json.dumps(payload).encode("utf-8")
        try:
            self.send_response(self.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *_args):
        pass


def start_provider(status=200, delay=0.0):
    handler = type(
        "LocalProvider", (ProviderHandler,), {"status": status, "delay": delay, "requests": []}
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, handler


def authorize_for_server(service, meeting_id, profile_id, port, timeout=10):
    profile = service.profiles.get(profile_id)
    service.profiles.save(
        profile.name,
        f"http://127.0.0.1:{port}/v1",
        profile.model_id,
        timeout,
        profile_id=profile_id,
    )
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    return snapshot, service.confirm(snapshot, True)


def test_loopback_text_provider_receives_only_confirmed_payload(tmp_path):
    server, handler = start_provider()
    try:
        service, meeting_id, profile_id, _, _ = make_cloud_service(tmp_path)
        snapshot, authorization = authorize_for_server(
            service, meeting_id, profile_id, server.server_port
        )
        assert service.send(snapshot, authorization).startswith("# Biên bản")
        assert len(handler.requests) == 1
        path, body, header = handler.requests[0]
        assert path == "/v1/chat/completions"
        assert b"Reviewed corrected text" in body
        assert b"Unselected secret" not in body
        assert header == "Bearer test-secret-key"
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("status,delay,kind", [(429, 0, "quota"), (200, 2, "timeout")])
def test_provider_failure_is_safe_and_preserves_local_data(tmp_path, caplog, status, delay, kind):
    server, _ = start_provider(status, delay)
    try:
        service, meeting_id, profile_id, _, run_id = make_cloud_service(tmp_path)
        minutes = MinutesStore(service.meetings)
        version = OfflineMinutesService(service.meetings).generate(meeting_id, run_id)
        minutes.approve_version(meeting_id, version)
        folder = tmp_path / "meetings" / meeting_id
        before = {
            str(path.relative_to(folder)): path.read_bytes()
            for path in folder.rglob("*")
            if path.is_file()
        }
        snapshot, authorization = authorize_for_server(
            service, meeting_id, profile_id, server.server_port, timeout=1
        )
        with pytest.raises(ProviderError) as error:
            service.send(snapshot, authorization)
        assert error.value.kind == kind
        assert "test-secret-key" not in str(error.value)
        assert "test-secret-key" not in caplog.text
        after = {
            str(path.relative_to(folder)): path.read_bytes()
            for path in folder.rglob("*")
            if path.is_file()
        }
        assert after == before
        assert service.meetings.privacy_mode(meeting_id) == "cloud_permitted"
    finally:
        server.shutdown()
        server.server_close()


def test_lost_network_is_retryable_without_data_loss(tmp_path, monkeypatch):
    service, meeting_id, profile_id, _, run_id = make_cloud_service(tmp_path)
    original = service.transcripts.read_run(meeting_id, run_id)

    def disconnected(**_kwargs):
        raise APIConnectionError(request=httpx.Request("POST", "https://example.org/v1"))

    monkeypatch.setattr(provider_transport, "OpenAI", disconnected)
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    authorization = service.confirm(snapshot, True)
    with pytest.raises(ProviderError) as error:
        service.send(snapshot, authorization)
    assert error.value.kind == "network"
    assert service.transcripts.read_run(meeting_id, run_id) == original
