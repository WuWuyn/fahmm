"""Strict, reversible short-key representation of the local DENSO form."""

from __future__ import annotations

TOP_KEYS = {"summary": "s", "source_ids": "r", "items": "i"}
ITEM_KEYS = {
    "section": "c",
    "label": "l",
    "text": "t",
    "method": "m",
    "data_source": "d",
    "open_point": "q",
    "owner": "o",
    "due_date": "u",
    "source_ids": "r",
}
SECTION_CODES = {
    "dashboard_layout": "dl",
    "kpi_scope": "ks",
    "sqdcm_kpis": "sq",
    "color_alerts": "ca",
    "warehouse_model": "wm",
    "input_data": "in",
    "project_actions": "pa",
    "partner_support": "ps",
}
_REVERSE_TOP = {short: full for full, short in TOP_KEYS.items()}
_REVERSE_ITEM = {short: full for full, short in ITEM_KEYS.items()}
_REVERSE_SECTION = {short: full for full, short in SECTION_CODES.items()}

COMPACT_FORM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "s": {"type": "string", "maxLength": 450},
        "r": {"type": "array", "items": {"type": "integer"}, "minItems": 1, "maxItems": 8},
        "i": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "c": {"type": "string", "enum": list(SECTION_CODES.values())},
                    **{key: {"type": "string"} for key in ("l", "t", "m", "d", "q", "o", "u")},
                    "r": {"type": "array", "items": {"type": "integer"}, "minItems": 1},
                },
                "required": ["c", "l", "t", "r"],
            },
        },
    },
    "required": ["s", "r", "i"],
}

COMPACT_INSTRUCTIONS = (
    "\nDùng đúng khóa JSON rút gọn: s=summary, r=source_ids, i=items. "
    "Mỗi item: c=section, l=label, t=text, m=method, d=data_source, "
    "q=open_point, o=owner, u=due_date, r=source_ids. "
    "Mã c: dl=dashboard_layout, ks=kpi_scope, sq=sqdcm_kpis, ca=color_alerts, "
    "wm=warehouse_model, in=input_data, pa=project_actions, ps=partner_support. "
    "Không thêm khóa khác; không thay đổi hoặc đoán ID nguồn."
)


def _ids(value: object, *, maximum: int | None = None) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= 1
        and (maximum is None or len(value) <= maximum)
        and all(type(item) is int for item in value)
    )


def _validate(value: object, *, compact: bool) -> dict:
    if not isinstance(value, dict):
        raise TypeError("Invalid form object")
    top = TOP_KEYS if compact else {name: name for name in TOP_KEYS}
    item_keys = ITEM_KEYS if compact else {name: name for name in ITEM_KEYS}
    if set(value) != set(top.values()):
        raise ValueError("Invalid form fields")
    summary, ids, items = value[top["summary"]], value[top["source_ids"]], value[top["items"]]
    if not isinstance(summary, str) or len(summary) > 450 or not _ids(ids, maximum=8):
        raise ValueError("Invalid form summary or sources")
    if not isinstance(items, list) or len(items) > 8:
        raise ValueError("Invalid form items")
    required = {item_keys[name] for name in ("section", "label", "text", "source_ids")}
    allowed = set(item_keys.values())
    sections = set(SECTION_CODES.values()) if compact else set(SECTION_CODES)
    for item in items:
        if not isinstance(item, dict) or not required <= set(item) or set(item) - allowed:
            raise ValueError("Invalid form item fields")
        section = item[item_keys["section"]]
        if not isinstance(section, str) or section not in sections:
            raise ValueError("Invalid form section")
        if not _ids(item[item_keys["source_ids"]]):
            raise ValueError("Invalid form item sources")
        for name in ("label", "text", "method", "data_source", "open_point", "owner", "due_date"):
            key = item_keys[name]
            if key in item and not isinstance(item[key], str):
                raise ValueError("Invalid form item text")
    return value


def encode_compact_form(value: object) -> dict:
    """Map a validated full-form object to short keys without dropping fields."""
    full = _validate(value, compact=False)
    result = {
        TOP_KEYS["summary"]: full["summary"],
        TOP_KEYS["source_ids"]: list(full["source_ids"]),
        TOP_KEYS["items"]: [],
    }
    for item in full["items"]:
        short = {ITEM_KEYS[key]: val for key, val in item.items()}
        short["c"] = SECTION_CODES[item["section"]]
        short["r"] = list(item["source_ids"])
        result["i"].append(short)
    return result


def decode_compact_form(value: object) -> dict:
    """Reject malformed short-form objects and restore every supplied field."""
    short = _validate(value, compact=True)
    result = {
        _REVERSE_TOP["s"]: short["s"],
        _REVERSE_TOP["r"]: list(short["r"]),
        _REVERSE_TOP["i"]: [],
    }
    for item in short["i"]:
        full = {_REVERSE_ITEM[key]: val for key, val in item.items()}
        full["section"] = _REVERSE_SECTION[item["c"]]
        full["source_ids"] = list(item["r"])
        result["items"].append(full)
    return result
