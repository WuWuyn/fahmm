"""Explicit cloud minutes request snapshots and disclosure boundary."""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from fahmm.minutes_store import MinutesStore
from fahmm.providers import ProviderProfile, ProviderProfiles
from fahmm.storage import MeetingStore
from fahmm.transcripts import TranscriptStore

DEFAULT_PROMPT = (
    "Viết biên bản cuộc họp bằng tiếng Việt từ các đoạn transcript được cung cấp. "
    "Không tự tạo người tham dự, quyết định, người phụ trách hoặc thời hạn. "
    "Nếu thiếu dữ liệu, ghi Chưa rõ. Trích dẫn ID đoạn và timestamp cho các kết luận quan trọng."
)


@dataclass(frozen=True)
class SelectedSegment:
    id: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class CloudRequestSnapshot:
    meeting_id: str
    run_id: str
    profile: ProviderProfile
    prompt: str
    max_tokens: int
    segments: tuple[SelectedSegment, ...]

    @property
    def transcript_text(self) -> str:
        return "\n".join(
            f"[{segment.id} | {segment.start:.2f}-{segment.end:.2f}s] {segment.text}"
            for segment in self.segments
        )

    @property
    def request_body(self) -> dict:
        return {
            "model": self.profile.model_id,
            "messages": [
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": self.transcript_text},
            ],
            "max_tokens": self.max_tokens,
        }

    @property
    def digest(self) -> str:
        envelope = {
            "meeting_id": self.meeting_id,
            "run_id": self.run_id,
            "profile_id": self.profile.id,
            "base_url": self.profile.base_url,
            "timeout": self.profile.timeout_seconds,
            "body": self.request_body,
        }
        serialized = json.dumps(envelope, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @property
    def preview(self) -> dict:
        return {
            "destination_hostname": urlsplit(self.profile.base_url).hostname,
            "data_types": ("selected reviewed transcript segments", "generation prompt"),
            "warning": "Meeting content will leave this device. The provider may charge you.",
            "request_body": self.request_body,
            "transcript": self.transcript_text,
            "prompt": self.prompt,
            "token_limit": self.max_tokens,
        }


@dataclass(frozen=True)
class DisclosureAuthorization:
    token: str
    digest: str


class CloudMinutesService:
    def __init__(
        self,
        meetings: MeetingStore,
        profiles: ProviderProfiles,
        transport: Callable[[CloudRequestSnapshot, str | None], object] | None = None,
    ) -> None:
        self.meetings = meetings
        self.profiles = profiles
        self.transcripts = TranscriptStore(meetings)
        self.minutes = MinutesStore(meetings)
        self._transport = transport
        self._authorizations: dict[str, str] = {}
        self._authorization_lock = threading.Lock()

    def prepare(
        self,
        meeting_id: str,
        profile_id: str,
        selected_ids: set[int],
        reviewed_ids: set[int],
        *,
        prompt: str = DEFAULT_PROMPT,
        max_tokens: int = 2000,
    ) -> CloudRequestSnapshot:
        if self.meetings.privacy_mode(meeting_id) != "cloud_permitted":
            raise PermissionError("This meeting is Internal/Restricted")
        if not selected_ids or not selected_ids.issubset(reviewed_ids):
            raise ValueError("Select and review transcript segments before sharing")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Enter a minutes prompt")
        if type(max_tokens) is not int or not 100 <= max_tokens <= 8000:
            raise ValueError("Token limit must be between 100 and 8000")
        profile = self.profiles.get(profile_id)
        metadata = self.meetings.metadata(meeting_id)
        run_id = metadata.get("active_run")
        if not run_id:
            raise ValueError("No active transcript run")
        run = self.transcripts.read_run(meeting_id, run_id)
        selected = [segment for segment in run["working"] if segment["id"] in selected_ids]
        if len(selected) != len(selected_ids):
            raise ValueError("Some selected transcript segments no longer exist")
        segments = tuple(
            SelectedSegment(
                segment["id"], float(segment["start"]), float(segment["end"]), segment["text"]
            )
            for segment in selected
        )
        return CloudRequestSnapshot(
            meeting_id, run_id, profile, prompt.strip(), max_tokens, segments
        )

    def confirm(
        self, snapshot: CloudRequestSnapshot, accepted: bool
    ) -> DisclosureAuthorization | None:
        if not accepted:
            return None
        self._check_current(snapshot)
        token = secrets.token_urlsafe(32)
        with self._authorization_lock:
            self._authorizations[token] = snapshot.digest
        return DisclosureAuthorization(token, snapshot.digest)

    def _check_current(self, snapshot: CloudRequestSnapshot) -> None:
        current = self.prepare(
            snapshot.meeting_id,
            snapshot.profile.id,
            {segment.id for segment in snapshot.segments},
            {segment.id for segment in snapshot.segments},
            prompt=snapshot.prompt,
            max_tokens=snapshot.max_tokens,
        )
        if current.digest != snapshot.digest:
            raise PermissionError(
                "The meeting, provider, or transcript changed; review the payload again"
            )

    def send(
        self,
        snapshot: CloudRequestSnapshot,
        authorization: DisclosureAuthorization | None,
    ) -> object:
        if authorization is None:
            raise PermissionError("Confirm this provider send first")
        with self._authorization_lock:
            stored = self._authorizations.pop(authorization.token, None)
        if stored != snapshot.digest or authorization.digest != snapshot.digest:
            raise PermissionError("This disclosure confirmation is invalid or already used")
        with self.meetings._metadata_lock:
            self._check_current(snapshot)
            key = self.profiles.credentials.get_key(snapshot.profile.id)
            self.meetings.begin_cloud_send(snapshot.meeting_id)
            if self._transport is None:
                from fahmm.provider_transport import send_chat_completion

                transport = send_chat_completion
            else:
                transport = self._transport
        try:
            return transport(snapshot, key)
        finally:
            self.meetings.end_cloud_send(snapshot.meeting_id)

    def generate(
        self,
        snapshot: CloudRequestSnapshot,
        authorization: DisclosureAuthorization | None,
        *,
        meeting_type: str | None = None,
    ) -> str:
        if meeting_type is not None:
            from fahmm.minutes_domain import MEETING_TYPES

            if not isinstance(meeting_type, str) or meeting_type not in MEETING_TYPES:
                raise ValueError("Invalid meeting type")
        with self.meetings.activity(snapshot.meeting_id, "provider_generation"):
            return self._generate(snapshot, authorization, meeting_type)

    def _generate(
        self,
        snapshot: CloudRequestSnapshot,
        authorization: DisclosureAuthorization | None,
        meeting_type: str | None,
    ) -> str:
        from fahmm.provider_minutes import (
            normalize_domain_provider_minutes,
            normalize_provider_minutes,
        )
        from fahmm.provider_transport import ProviderError

        raw = self.send(snapshot, authorization)
        try:
            meeting = self.meetings.metadata(snapshot.meeting_id)
            content = (
                normalize_provider_minutes(raw, snapshot, meeting)
                if meeting_type is None
                else normalize_domain_provider_minutes(raw, snapshot, meeting, meeting_type)
            )
        except (TypeError, ValueError):
            raise ProviderError(
                "format", "Provider returned unusable minutes; retry or change provider"
            ) from None
        return self.minutes.save_version(
            snapshot.meeting_id,
            snapshot.run_id,
            "provider",
            content,
            snapshot.prompt,
            snapshot.profile.id,
        )
