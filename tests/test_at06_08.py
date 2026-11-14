"""AT-06–AT-08: negative and positive meeting-content egress paths."""

import json
import socket

import pytest
from test_cloud_minutes import make_cloud_service
from test_provider_transport import start_provider

from fahmm.provider_transport import ProviderError


def test_restricted_block_confirmed_loopback_and_retry_after_provider_error(tmp_path, monkeypatch):
    server, handler = start_provider()
    try:
        service, meeting_id, profile_id, _, run_id = make_cloud_service(tmp_path)
        profile = service.profiles.get(profile_id)
        service.profiles.save(profile.name, f"http://127.0.0.1:{server.server_port}/v1",
                              profile.model_id, 5, profile_id=profile_id)
        service.meetings.set_privacy_mode(meeting_id, "restricted")
        blocked_sockets = []

        def blocked(*_args, **_kwargs):
            blocked_sockets.append(True)
            raise AssertionError("Restricted meeting attempted network egress")

        with monkeypatch.context() as patcher:
            patcher.setattr(socket.socket, "connect", blocked)
            with pytest.raises(PermissionError, match="Restricted"):
                service.prepare(meeting_id, profile_id, {2}, {2})
        assert blocked_sockets == [] and handler.requests == []

        service.meetings.set_privacy_mode(meeting_id, "cloud_permitted")
        socket_destinations = []
        original_connect = socket.socket.connect

        def spy(sock, address):
            socket_destinations.append(address)
            return original_connect(sock, address)

        monkeypatch.setattr(socket.socket, "connect", spy)
        snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
        assert snapshot.preview["destination_hostname"] == "127.0.0.1"
        assert "Reviewed corrected text" in snapshot.preview["transcript"]
        assert service.confirm(snapshot, False) is None
        with pytest.raises(PermissionError, match="Confirm"):
            service.generate(snapshot, None)
        assert handler.requests == []

        first = service.generate(snapshot, service.confirm(snapshot, True))
        assert service.minutes.read_version(meeting_id, first)["manifest"]["review_state"] == "unverified"
        assert len(handler.requests) == 1
        outgoing = json.loads(handler.requests[0][1])
        assert "Reviewed corrected text" in outgoing["messages"][1]["content"]
        assert "Unselected secret" not in outgoing["messages"][1]["content"]
        assert "test-secret-key" not in json.dumps(outgoing)
        assert all(destination[0] == "127.0.0.1" for destination in socket_destinations)

        folder = tmp_path / "meetings" / meeting_id
        before = {str(path.relative_to(folder)): path.read_bytes()
                  for path in folder.rglob("*") if path.is_file()}
        handler.status = 429
        retry = service.prepare(meeting_id, profile_id, {2}, {2})
        with pytest.raises(ProviderError) as error:
            service.generate(retry, service.confirm(retry, True))
        assert error.value.kind == "quota"
        assert "test-secret-key" not in str(error.value)
        after = {str(path.relative_to(folder)): path.read_bytes()
                 for path in folder.rglob("*") if path.is_file()}
        assert after == before
        assert service.transcripts.read_run(meeting_id, run_id)["working"]
        assert service.meetings.privacy_mode(meeting_id) == "cloud_permitted"
        handler.status = 200
        fresh = service.prepare(meeting_id, profile_id, {2}, {2})
        second = service.generate(fresh, service.confirm(fresh, True))
        assert second != first and len(service.minutes.list_versions(meeting_id)) == 2
        assert len(handler.requests) == 3
    finally:
        server.shutdown()
        server.server_close()
