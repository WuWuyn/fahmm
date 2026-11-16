"""Versioned JSON-lines envelope shared with the Tauri host and TypeScript client."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

CONTRACT_PATH = (
    Path(sys._MEIPASS) / "desktop" / "protocol" / "contract.json"
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[3] / "desktop" / "protocol" / "contract.json"
)
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
VERSION: int = CONTRACT["version"]
MAX_FRAME_BYTES: int = CONTRACT["maxFrameBytes"]
_ID = re.compile(CONTRACT["requestIdPattern"])


class FrameError(ValueError):
    """A malformed, incompatible, or oversized protocol frame."""


def _record(value: Any) -> bool:
    return isinstance(value, dict)


def _fields_match(value: Any, fields: dict[str, str]) -> bool:
    if not _record(value):
        return False
    for name, kind in fields.items():
        item = value.get(name)
        match kind:
            case "string":
                valid = isinstance(item, str)
            case "string?":
                valid = item is None or isinstance(item, str)
            case "number":
                valid = type(item) in (int, float)
            case "number?":
                valid = item is None or type(item) in (int, float)
            case "integer":
                valid = type(item) is int
            case "boolean":
                valid = type(item) is bool
            case "string[]":
                valid = isinstance(item, list) and all(isinstance(x, str) for x in item)
            case "integer[]":
                valid = isinstance(item, list) and all(type(x) is int for x in item)
            case "number[]":
                valid = isinstance(item, list) and all(type(x) in (int, float) for x in item)
            case "object":
                valid = _record(item)
            case "object?":
                valid = item is None or _record(item)
            case "object[]":
                valid = isinstance(item, list) and all(_record(x) for x in item)
            case _:
                valid = False
        if not valid:
            return False
    return True


def validate_frame(raw: bytes | str) -> dict[str, Any]:
    payload = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    if len(payload) > MAX_FRAME_BYTES:
        raise FrameError("FRAME_TOO_LARGE")
    try:
        frame = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FrameError("MALFORMED_FRAME") from exc
    if not _record(frame) or frame.get("v") != VERSION or type(frame.get("v")) is not int:
        raise FrameError("UNSUPPORTED_VERSION")
    kind = frame.get("kind")
    identifier = frame.get("id")
    id_ok = isinstance(identifier, str) and _ID.fullmatch(identifier) is not None
    if kind == "request":
        if frame.get("op") not in CONTRACT["operations"]:
            raise FrameError("UNSUPPORTED_OPERATION")
        operation = CONTRACT["operations"].get(frame.get("op"))
        valid = (
            id_ok
            and operation is not None
            and _fields_match(frame.get("params"), operation["params"])
        )
    elif kind == "response":
        operation = CONTRACT["operations"].get(frame.get("op"))
        valid = (
            id_ok
            and operation is not None
            and _fields_match(frame.get("result"), operation["result"])
        )
    elif kind == "error":
        error = frame.get("error")
        valid = (
            id_ok
            and _record(error)
            and error.get("code") in CONTRACT["errorCodes"]
            and isinstance(error.get("message"), str)
            and len(error["message"]) <= 200
        )
    elif kind == "event":
        event = CONTRACT["events"].get(frame.get("event"))
        job_id = frame.get("jobId")
        valid = (
            event is not None
            and (job_id is None or (isinstance(job_id, str) and _ID.fullmatch(job_id)))
            and _fields_match(frame.get("data"), event)
        )
    else:
        valid = False
    if not valid:
        raise FrameError("INVALID_FRAME")
    return frame


def encode_frame(frame: dict[str, Any]) -> bytes:
    payload = json.dumps(frame, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    validate_frame(payload)
    return payload + b"\n"
