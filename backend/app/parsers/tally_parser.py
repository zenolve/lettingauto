"""Generic Tally webhook parser.

Tally form keys (`question_48Jzqk`, …) are stable per form revision but can
change when the form is duplicated. The spec requires label-first matching
with key-based fallback (§4.3).
"""
from __future__ import annotations

from typing import Any, Iterable


def resolve_field(field: dict[str, Any]) -> Any:
    """Resolve a single Tally field dict to its human-readable value."""
    if field is None:
        return None

    ftype = field.get("type")

    if ftype == "FILE_UPLOAD":
        vals = field.get("value") or []
        if isinstance(vals, list) and vals:
            return vals[0].get("url")
        return None

    if ftype in ("MULTIPLE_CHOICE", "DROPDOWN", "CHECKBOXES"):
        ids = field.get("value") or []
        if not isinstance(ids, list):
            ids = [ids]
        opts = {o["id"]: (o.get("text") or "").strip() for o in field.get("options", [])}
        resolved = [opts[i] for i in ids if i in opts]
        if not resolved:
            return None
        return ", ".join(resolved)

    if ftype == "INPUT_DATE":
        return field.get("value")  # ISO 8601 string

    val = field.get("value")
    if isinstance(val, list):
        return val[0] if val else None
    return val if val not in ("",) else None


def get_by_label(fields: list[dict], label_fragment: str) -> Any:
    """Find the first field whose label *contains* the fragment (ci)."""
    frag = label_fragment.lower()
    for f in fields:
        if frag in (f.get("label") or "").lower():
            return resolve_field(f)
    return None


def get_by_key(fields: list[dict], key: str) -> Any:
    for f in fields:
        if f.get("key") == key:
            return resolve_field(f)
    return None


def get_hidden(fields: list[dict], label: str) -> Any:
    for f in fields:
        if f.get("label") == label and f.get("type") == "HIDDEN_FIELDS":
            return f.get("value")
    return None


def first_present(fields: list[dict], *labels: Iterable[str]) -> Any:
    """Try each label fragment; return the first one that resolves to non-None."""
    for lbl in labels:
        v = get_by_label(fields, lbl)
        if v is not None:
            return v
    return None
