import json
import socket
import threading
import uuid
from dataclasses import FrozenInstanceError

import pytest
from test_minutes_store import make_meeting_with_run
from test_providers import FakeCredentials

from fahmm.cloud_minutes import CloudMinutesService
from fahmm.models import InstalledModel
from fahmm.providers import ProviderProfiles
from fahmm.transcripts import TranscriptStore


def make_cloud_service(tmp_path):
    meetings, meeting_id, old_run = make_meeting_with_run(tmp_path / "meetings")
    transcript = TranscriptStore(meetings)
    model = InstalledModel(
        uuid.uuid4().hex, "test/whisper", "test", "MIT", "a" * 40, 100, tmp_path / "model"
    )
    run_id = uuid.uuid4().hex
    transcript.save_run(
        meeting_id,
        run_id,
        model,
        "vi",
        {"duration": 4},
        [
            {"id": 2, "start": 0, "end": 2, "text": "Original selected"},
            {"id": 3, "start": 2, "end": 4, "text": "Unselected secret"},
        ],
    )
    transcript.save_edits(meeting_id, run_id, {2: "Reviewed corrected text"})
    meetings.set_privacy_mode(meeting_id, "cloud_permitted")
    profiles = ProviderProfiles(tmp_path / "providers.json", FakeCredentials())
    profile = profiles.save(
        "Provider", "https://example.org/v1", "model-id", 30, api_key="test-secret-key"
    )
    return CloudMinutesService(meetings, profiles), meeting_id, profile.id, old_run, run_id


def test_snapshot_is_frozen_and_contains_only_selected_working_text(tmp_path):
    service, meeting_id, profile_id, old_run, run_id = make_cloud_service(tmp_path)
    snapshot = service.prepare(
        meeting_id, profile_id, {2}, {2}, prompt="Viết bản nháp", max_tokens=500
    )
    preview = snapshot.preview
    serialized = json.dumps(preview, ensure_ascii=False)
    assert preview["destination_hostname"] == "example.org"
    assert preview["data_types"] == ("selected reviewed transcript segments", "generation prompt")
    assert preview["token_limit"] == 500
    assert "Reviewed corrected text" in serialized
    assert "Viết bản nháp" in serialized
    assert "Unselected secret" not in serialized
    assert "Original selected" not in serialized
    assert old_run not in serialized
    assert run_id not in serialized
    assert str(tmp_path) not in serialized
    assert "test-secret-key" not in serialized
    with pytest.raises(FrozenInstanceError):
        snapshot.max_tokens = 999
    original_digest = snapshot.digest
    preview["request_body"]["messages"][1]["content"] = "tampered"
    assert snapshot.digest == original_digest


def test_snapshot_requires_explicit_review_and_current_segments(tmp_path):
    service, meeting_id, profile_id, _, _ = make_cloud_service(tmp_path)
    with pytest.raises(ValueError, match="review"):
        service.prepare(meeting_id, profile_id, {2}, set())
    with pytest.raises(ValueError, match="no longer exist"):
        service.prepare(meeting_id, profile_id, {99}, {99})
    service.meetings.set_privacy_mode(meeting_id, "restricted")
    with pytest.raises(PermissionError, match="Restricted"):
        service.prepare(meeting_id, profile_id, {2}, {2})


def test_confirmation_is_single_use_and_cancel_never_sends(tmp_path):
    service, meeting_id, profile_id, _, _ = make_cloud_service(tmp_path)
    calls = []
    service._transport = lambda snapshot, key: calls.append((snapshot.digest, key)) or "ok"
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    assert service.confirm(snapshot, False) is None
    with pytest.raises(PermissionError, match="Confirm"):
        service.send(snapshot, None)
    assert calls == []
    authorization = service.confirm(snapshot, True)
    assert service.send(snapshot, authorization) == "ok"
    assert len(calls) == 1
    with pytest.raises(PermissionError, match="already used"):
        service.send(snapshot, authorization)
    assert len(calls) == 1
    retry = service.prepare(meeting_id, profile_id, {2}, {2})
    with pytest.raises(PermissionError, match="Confirm"):
        service.send(retry, None)
    assert service.send(retry, service.confirm(retry, True)) == "ok"
    assert len(calls) == 2


@pytest.mark.parametrize("change", ["mode", "profile", "payload"])
def test_changed_state_blocks_send_before_any_socket_connection(tmp_path, monkeypatch, change):
    service, meeting_id, profile_id, _, run_id = make_cloud_service(tmp_path)
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    authorization = service.confirm(snapshot, True)
    socket_calls = []

    def spy(*_args, **_kwargs):
        socket_calls.append(True)
        raise AssertionError("Unauthorized network connection")

    monkeypatch.setattr(socket.socket, "connect", spy)
    service._transport = lambda *_args: spy()
    if change == "mode":
        service.meetings.set_privacy_mode(meeting_id, "restricted")
    elif change == "profile":
        profile = service.profiles.get(profile_id)
        service.profiles.save(
            profile.name,
            "https://another.example/v1",
            profile.model_id,
            profile.timeout_seconds,
            profile_id=profile_id,
        )
    else:
        TranscriptStore(service.meetings).save_edits(
            meeting_id, run_id, {2: "Changed after preview"}
        )
    with pytest.raises(PermissionError):
        service.send(snapshot, authorization)
    assert socket_calls == []


def test_meeting_metadata_remains_readable_during_send_and_mode_change_is_rejected(tmp_path):
    service, meeting_id, profile_id, _, _ = make_cloud_service(tmp_path)
    entered = threading.Event()
    release = threading.Event()
    result = []

    def slow_transport(*_args):
        entered.set()
        release.wait(5)
        return "ok"

    service._transport = slow_transport
    snapshot = service.prepare(meeting_id, profile_id, {2}, {2})
    authorization = service.confirm(snapshot, True)
    thread = threading.Thread(target=lambda: result.append(service.send(snapshot, authorization)))
    thread.start()
    try:
        assert entered.wait(3)
        assert service.meetings.metadata(meeting_id)["privacy_mode"] == "cloud_permitted"
        with pytest.raises(RuntimeError, match="provider request"):
            service.meetings.set_privacy_mode(meeting_id, "restricted")
    finally:
        release.set()
        thread.join(timeout=5)
    assert result == ["ok"]
    service.meetings.set_privacy_mode(meeting_id, "restricted")
