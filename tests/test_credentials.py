import sys
import uuid

import pytest

from fahmm import credentials
from fahmm.credentials import WindowsCredentialStore
from fahmm.storage import MeetingStore


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager only")
def test_windows_credential_round_trip_without_disk_or_log_leak(tmp_path, caplog):
    meeting_store = MeetingStore(tmp_path / "meetings")
    meeting_store.create({})
    profile_id = uuid.uuid4().hex
    secret = f"test-only-{uuid.uuid4().hex}"
    store = WindowsCredentialStore()
    try:
        assert store.get_key(profile_id) is None
        store.set_key(profile_id, secret)
        assert WindowsCredentialStore().get_key(profile_id) == secret
        disk_text = "".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in tmp_path.rglob("*")
            if path.is_file()
        )
        assert secret not in disk_text
        assert secret not in caplog.text
    finally:
        store.delete_key(profile_id)
    assert store.get_key(profile_id) is None


def test_credential_store_fails_closed_off_windows(monkeypatch):
    monkeypatch.setattr(credentials.sys, "platform", "not-windows")
    with pytest.raises(RuntimeError, match="unavailable"):
        WindowsCredentialStore()
