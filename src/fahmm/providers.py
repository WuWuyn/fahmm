"""Optional local provider profiles; API keys live only in Windows credentials."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from fahmm.credentials import WindowsCredentialStore


def provider_http_client():
    """Keep provider redirects from forwarding disclosed content to another host."""
    from openai import DefaultHttpxClient

    return DefaultHttpxClient(follow_redirects=False, verify=True)


def validate_base_url(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("Provider Base URL must be text")
    value = value.strip().rstrip("/")
    try:
        parsed = urlsplit(value)
        _port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid provider Base URL") from exc
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.netloc.endswith(":"):
        raise ValueError("Provider Base URL must use HTTPS or local HTTP")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Provider Base URL must not contain credentials, query, or fragment")
    if parsed.scheme == "http":
        host = parsed.hostname.casefold()
        try:
            loopback = ipaddress.ip_address(host).is_loopback
        except ValueError:
            loopback = host == "localhost"
        if not loopback:
            raise ValueError("HTTP provider URL is allowed only on localhost")
    return value


@dataclass(frozen=True)
class ProviderProfile:
    id: str
    name: str
    base_url: str
    model_id: str
    timeout_seconds: float


class ProviderProfiles:
    def __init__(
        self, path: Path | None = None, credentials: WindowsCredentialStore | None = None
    ) -> None:
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        self.path = Path(path) if path is not None else base / "fahmm" / "providers.json"
        self._credentials = credentials

    @property
    def credentials(self) -> WindowsCredentialStore:
        if self._credentials is None:
            self._credentials = WindowsCredentialStore()
        return self._credentials

    def list_profiles(self) -> list[ProviderProfile]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            raise TypeError("Invalid provider settings")
        return [ProviderProfile(**item) for item in data]

    def get(self, profile_id: str) -> ProviderProfile:
        for profile in self.list_profiles():
            if profile.id == profile_id:
                return profile
        raise KeyError("Provider profile not found")

    def save(
        self,
        name: str,
        base_url: str,
        model_id: str,
        timeout_seconds: float,
        *,
        profile_id: str | None = None,
        api_key: str | None = None,
    ) -> ProviderProfile:
        name, model_id = name.strip(), model_id.strip()
        if not name or len(name) > 120 or not model_id or len(model_id) > 200:
            raise ValueError("Provider name and model ID are required")
        if any(ord(c) < 32 for c in name + model_id):
            raise ValueError("Provider name or model ID contains a control character")
        if not 1 <= timeout_seconds <= 600:
            raise ValueError("Provider timeout must be between 1 and 600 seconds")
        if profile_id is not None and not re.fullmatch(r"[0-9a-f]{32}", profile_id):
            raise ValueError("Invalid provider profile ID")
        profiles = self.list_profiles()
        profile_id = profile_id or uuid.uuid4().hex
        profile = ProviderProfile(
            profile_id, name, validate_base_url(base_url), model_id, float(timeout_seconds)
        )
        if api_key is not None:
            old_key = self.credentials.get_key(profile_id)
            if api_key:
                self.credentials.set_key(profile_id, api_key)
            else:
                self.credentials.delete_key(profile_id)
        try:
            updated = [item for item in profiles if item.id != profile_id] + [profile]
            self._write(updated)
        except Exception:
            if api_key is not None:
                if old_key:
                    self.credentials.set_key(profile_id, old_key)
                else:
                    self.credentials.delete_key(profile_id)
            raise
        return profile

    def delete(self, profile_id: str) -> None:
        self.get(profile_id)
        self.credentials.delete_key(profile_id)
        self._write([profile for profile in self.list_profiles() if profile.id != profile_id])

    def _write(self, profiles: list[ProviderProfile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.parent / f".providers-{uuid.uuid4().hex}.tmp"
        try:
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(
                    [asdict(profile) for profile in profiles], file, ensure_ascii=False, indent=2
                )
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
