"""Versioned, conservative content shape for customer-facing IT meeting minutes."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

DOMAIN_SCHEMA_VERSION = 1
MEETING_TYPES = frozenset(
    {
        "general",
        "requirement_gathering",
        "technical_discussion",
        "project_status",
        "issue_incident",
        "uat_feedback",
    }
)
METADATA_FIELDS = (
    "title",
    "meeting_datetime",
    "project_customer",
    "participants",
    "objective",
)
SECTIONS = frozenset(
    {
        "summary",
        "topics",
        "requirements",
        "decisions",
        "proposed_solutions",
        "open_questions",
        "risks_blockers",
        "actions",
        "next_steps",
        "technical_considerations",
        "status_updates",
        "incident_findings",
        "uat_observations",
    }
)
SECTION_KINDS = {
    "requirements": frozenset(
        {
            "business",
            "functional",
            "non_functional",
            "business_rule",
            "constraint",
            "assumption",
            "change",
        }
    ),
    "risks_blockers": frozenset({"risk", "blocker", "dependency"}),
    "technical_considerations": frozenset(
        {
            "architecture",
            "technology",
            "api_integration",
            "database",
            "security",
            "performance",
            "dependency",
            "alternative",
        }
    ),
    "status_updates": frozenset(
        {"progress", "milestone", "issue", "blocker", "risk", "dependency", "next_step"}
    ),
    "incident_findings": frozenset(
        {
            "problem",
            "impact",
            "finding",
            "suspected_cause",
            "confirmed_cause",
            "workaround",
            "resolution_proposal",
            "follow_up",
        }
    ),
    "uat_observations": frozenset(
        {
            "scenario",
            "observed_result",
            "customer_feedback",
            "defect",
            "change_request",
            "pending_confirmation",
            "acceptance",
        }
    ),
}
PROVENANCE = frozenset({"user_provided", "source_supported", "unknown"})
CLAIM_ORIGINS = frozenset({"extractive", "provider", "user_provided"})
REVIEW_STATES = frozenset({"needs_review", "confirmed", "rejected"})
ID_RE = re.compile(r"[0-9a-f]{32}\Z")


def _metadata_value(value: object, provenance: str = "unknown") -> dict:
    return {"value": value, "provenance": provenance, "sources": []}


def new_domain_content(meeting_type: str = "general", *, title: str | None = None) -> dict:
    if not isinstance(meeting_type, str) or meeting_type not in MEETING_TYPES:
        raise ValueError("Invalid meeting type")
    saved_title = title.strip() if isinstance(title, str) else ""
    if saved_title == "Untitled meeting":
        saved_title = ""
    metadata = {
        "title": _metadata_value(
            saved_title or "Chưa rõ", "user_provided" if saved_title else "unknown"
        ),
        "meeting_datetime": _metadata_value(None),
        "project_customer": _metadata_value(None),
        "participants": _metadata_value([]),
        "objective": _metadata_value(None),
    }
    return {
        "domain_schema_version": DOMAIN_SCHEMA_VERSION,
        "domain": {"meeting_type": meeting_type, "metadata": metadata, "sections": {}},
    }


def _valid_datetime(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def validate_domain_content(content: object) -> None:
    if not isinstance(content, dict) or type(content.get("domain_schema_version")) is not int:
        raise ValueError("Invalid minutes domain schema")
    if content["domain_schema_version"] != DOMAIN_SCHEMA_VERSION:
        raise ValueError("Unsupported minutes domain schema")
    if set(content) - {"domain_schema_version", "domain", "user_text", "headings", "label"}:
        raise ValueError("Unknown minutes domain content field")
    if "user_text" in content and not isinstance(content["user_text"], str):
        raise ValueError("Invalid minutes edited text")
    domain = content.get("domain")
    if not isinstance(domain, dict) or set(domain) != {"meeting_type", "metadata", "sections"}:
        raise ValueError("Invalid minutes domain")
    if not isinstance(domain["meeting_type"], str) or domain["meeting_type"] not in MEETING_TYPES:
        raise ValueError("Invalid meeting type")
    metadata = domain["metadata"]
    if not isinstance(metadata, dict) or set(metadata) != set(METADATA_FIELDS):
        raise ValueError("Invalid meeting metadata")
    for name, field in metadata.items():
        if not isinstance(field, dict) or set(field) != {"value", "provenance", "sources"}:
            raise ValueError(f"Invalid {name} metadata")
        value, provenance = field["value"], field["provenance"]
        if (
            not isinstance(provenance, str)
            or provenance not in PROVENANCE
            or not isinstance(field["sources"], list)
        ):
            raise ValueError(f"Invalid {name} provenance")
        if provenance == "source_supported" and not field["sources"]:
            raise ValueError(f"Missing {name} source")
        if name == "participants":
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise ValueError("Invalid participants")
        elif name == "meeting_datetime":
            if value is not None and (not isinstance(value, str) or not _valid_datetime(value)):
                raise ValueError("Invalid meeting datetime")
        elif value is not None and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"Invalid {name} value")
        if name == "title" and value is None:
            raise ValueError("Missing meeting title")
        if provenance == "unknown" and value not in (None, [], "Chưa rõ"):
            raise ValueError(f"Unconfirmed {name} value")
    sections = domain["sections"]
    if not isinstance(sections, dict) or set(sections) - SECTIONS:
        raise ValueError("Invalid minutes section")
    item_ids: set[str] = set()
    for section, items in sections.items():
        if not isinstance(items, list):
            raise TypeError(f"Invalid {section} items")
        for item in items:
            _validate_claim(section, item, item_ids)


def _validate_claim(section: str, item: object, item_ids: set[str]) -> None:
    if not isinstance(item, dict):
        raise TypeError("Invalid minutes claim")
    required = {"item_id", "text", "sources", "origin", "review_status"}
    extra = {
        "requirements": {"kind", "formality"},
        "actions": {"owner", "due_date", "confirmation_status"},
        "uat_observations": {"kind", "acceptance_status"},
    }.get(section, {"kind"} if section in SECTION_KINDS else set())
    if set(item) != required | extra:
        raise ValueError(f"Invalid {section} claim fields")
    item_id = item["item_id"]
    if not isinstance(item_id, str) or not ID_RE.fullmatch(item_id) or item_id in item_ids:
        raise ValueError("Invalid or repeated minutes claim ID")
    item_ids.add(item_id)
    if not isinstance(item["text"], str) or not item["text"].strip():
        raise ValueError("Invalid minutes claim text")
    if not isinstance(item["sources"], list):
        raise TypeError("Invalid minutes claim sources")
    if (
        not isinstance(item["origin"], str)
        or item["origin"] not in CLAIM_ORIGINS
        or not isinstance(item["review_status"], str)
        or item["review_status"] not in REVIEW_STATES
    ):
        raise ValueError("Invalid minutes claim state")
    if item["origin"] != "user_provided" and not item["sources"]:
        raise ValueError("Generated minutes claim needs a source")
    if section in SECTION_KINDS and (
        not isinstance(item["kind"], str) or item["kind"] not in SECTION_KINDS[section]
    ):
        raise ValueError(f"Invalid {section} kind")
    if section == "requirements" and item["formality"] not in {"candidate", "user_confirmed"}:
        raise ValueError("Invalid requirement formality")
    if section == "actions":
        if any(
            not isinstance(item[key], str) or not item[key].strip() for key in ("owner", "due_date")
        ):
            raise ValueError("Invalid action owner or deadline")
        if item["confirmation_status"] not in {"suggested", "reviewed"}:
            raise ValueError("Invalid action confirmation")
    if section == "uat_observations" and item["acceptance_status"] not in {
        "pending",
        "user_confirmed",
    }:
        raise ValueError("Invalid UAT acceptance status")


def new_claim(
    text: str, origin: str, *, sources: list[dict] | None = None, **fields: object
) -> dict:
    return {
        "item_id": uuid.uuid4().hex,
        "text": text,
        "sources": sources or [],
        "origin": origin,
        "review_status": "needs_review",
        **fields,
    }
