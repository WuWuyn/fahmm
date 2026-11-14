import json
import sys
import uuid

import httpx
import pytest
from openai import APIStatusError, DefaultHttpxClient, OpenAI
from test_minutes_store import make_meeting_with_run

from fahmm.credentials import WindowsCredentialStore
from fahmm.offline_minutes import OfflineMinutesService
from fahmm.providers import ProviderProfiles, provider_http_client, validate_base_url


class FakeCredentials:
    def __init__(self):
        self.keys = {}

    def set_key(self, profile_id, key):
        self.keys[profile_id] = key

    def get_key(self, profile_id):
        return self.keys.get(profile_id)

    def delete_key(self, profile_id):
        self.keys.pop(profile_id, None)


def test_multiple_profiles_persist_without_plaintext_keys_and_delete(tmp_path):
    secrets = FakeCredentials()
    path = tmp_path / "providers.json"
    profiles = ProviderProfiles(path, secrets)
    first = profiles.save("One", "https://example.org/v1", "model-a", 30, api_key="secret-123")
    second = profiles.save("Local", "http://127.0.0.1:1234/v1", "model-b", 45)
    assert {item.name for item in ProviderProfiles(path, secrets).list_profiles()} == {"One", "Local"}
    assert "secret-123" not in path.read_text(encoding="utf-8")
    profiles.save("Updated", first.base_url, first.model_id, 50, profile_id=first.id)
    assert profiles.get(first.id).name == "Updated"
    assert secrets.get_key(first.id) == "secret-123"
    profiles.delete(first.id)
    assert secrets.get_key(first.id) is None
    assert [item.id for item in profiles.list_profiles()] == [second.id]


@pytest.mark.parametrize("url", [
    "http://example.org/v1", "ftp://localhost/v1", "https://user:pass@example.org/v1",
    "https://example.org/v1?x=1", "https://example.org/#fragment", "http://notlocalhost/v1",
    "https://example.org:bad/v1", "https://example.org:",
])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


def test_loopback_is_explicit_and_no_provider_does_not_block_offline(tmp_path):
    assert validate_base_url("http://[::1]:8000/v1") == "http://[::1]:8000/v1"
    assert validate_base_url("https://example.org/v1/") == "https://example.org/v1"
    meetings, meeting_id, _ = make_meeting_with_run(tmp_path / "meetings")
    assert ProviderProfiles(tmp_path / "providers.json").list_profiles() == []
    assert OfflineMinutesService(meetings).generate(meeting_id)


def test_provider_client_refuses_redirect_to_other_endpoint():
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(307, headers={"location": "http://other.example/v1/chat/completions"})

    client = DefaultHttpxClient(follow_redirects=False, verify=True,
                                transport=httpx.MockTransport(respond))
    sdk = OpenAI(api_key="test-only", base_url="https://safe.example/v1",
                 http_client=client, max_retries=0)
    with pytest.raises(APIStatusError):
        sdk.chat.completions.create(model="test", messages=[{"role": "user", "content": "x"}])
    assert len(requests) == 1
    assert requests[0].url.host == "safe.example"
    assert not provider_http_client().follow_redirects


@pytest.mark.skipif(sys.platform != "win32", reason="Windows credentials only")
def test_real_profile_secret_stays_out_of_disk_and_logs(tmp_path, caplog):
    profile_id = uuid.uuid4().hex
    secret = f"fake-key-{uuid.uuid4().hex}"
    profiles = ProviderProfiles(tmp_path / "providers.json", WindowsCredentialStore())
    try:
        profiles.save("Test", "https://example.org/v1", "test-model", 10,
                      profile_id=profile_id, api_key=secret)
        assert profiles.credentials.get_key(profile_id) == secret
        assert secret not in json.dumps([item.__dict__ for item in profiles.list_profiles()])
        assert secret not in (tmp_path / "providers.json").read_text(encoding="utf-8")
        assert secret not in caplog.text
    finally:
        profiles.credentials.delete_key(profile_id)
