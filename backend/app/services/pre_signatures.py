"""Pre-baked signatures registry — agent-managed via the Signatures admin page.

Each signature is a PNG on disk plus a metadata entry in ``signatures.json``.
The agent uploads or draws a signature in the UI; we store the PNG under
``templates/signatures/<id>.png`` and the metadata (display name, role) in
the sidecar JSON. When the agent opens a library document with sign-mode
markers like ``/pg_sig1/`` in the body, the LibraryEditor shows a dropdown
per anchor letting the agent pick which signatory signs there. The send
route passes those choices through to ``substitute`` below.

Storage layout:

    backend/app/templates/signatures/
      signatures.json     # registry: id → {display_name, role, filename, created_at}
      <id>.png            # one PNG per signatory
      .gitignore          # PNGs + signatures.json are gitignored (sensitive)
      README.md

Anchors used inside document bodies are slot markers — ``/pg_sig1/`` means
"first Palace Gate signature spot in this doc", not "this specific person".
At send time the agent picks which signatory fills each slot.
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.core.logger import get_logger

logger = get_logger(__name__)


_DIR = Path(__file__).resolve().parent.parent / "templates" / "signatures"
_REGISTRY_FILE = _DIR / "signatures.json"

# Anchor markers that document bodies can use. Add more as needed — the
# editor dropdown shows one slot per anchor found in the body.
KNOWN_ANCHORS: tuple[str, ...] = ("/pg_sig1/", "/pg_sig2/", "/pg_sig3/", "/pg_sig4/")


@dataclass(frozen=True)
class Signature:
    id: str
    display_name: str
    role: str
    filename: str
    created_at: str
    size_bytes: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "role": self.role,
            "filename": self.filename,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
        }


# ---------------------------------------------------------------------------
# Registry I/O — read on every call so the admin page changes are picked up
# without a backend restart. The signatures.json file is tiny (a few hundred
# bytes per row) so re-reading is free.
# ---------------------------------------------------------------------------
def _ensure_dir() -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    if not _REGISTRY_FILE.exists():
        _REGISTRY_FILE.write_text("{}", encoding="utf-8")


def _read_registry() -> dict:
    _ensure_dir()
    try:
        return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("signatures.json malformed — treating as empty")
        return {}


def _write_registry(reg: dict) -> None:
    _ensure_dir()
    _REGISTRY_FILE.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def list_signatures() -> list[Signature]:
    """Return every signature in the registry, sorted by display_name."""
    reg = _read_registry()
    out: list[Signature] = []
    for sid, meta in reg.items():
        path = _DIR / meta.get("filename", f"{sid}.png")
        out.append(Signature(
            id=sid,
            display_name=meta.get("display_name", sid),
            role=meta.get("role", ""),
            filename=meta.get("filename", f"{sid}.png"),
            created_at=meta.get("created_at", ""),
            size_bytes=path.stat().st_size if path.is_file() else 0,
        ))
    out.sort(key=lambda s: s.display_name.lower())
    return out


def get_signature(sig_id: str) -> Signature | None:
    """Return one Signature by id (or None)."""
    reg = _read_registry()
    if sig_id not in reg:
        return None
    meta = reg[sig_id]
    path = _DIR / meta.get("filename", f"{sig_id}.png")
    return Signature(
        id=sig_id,
        display_name=meta.get("display_name", sig_id),
        role=meta.get("role", ""),
        filename=meta.get("filename", f"{sig_id}.png"),
        created_at=meta.get("created_at", ""),
        size_bytes=path.stat().st_size if path.is_file() else 0,
    )


# ---------------------------------------------------------------------------
# Mutations — used by the CRUD endpoints.
# ---------------------------------------------------------------------------
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Convert a display name into a filesystem-safe id."""
    s = _SLUG_RE.sub("_", name.strip().lower()).strip("_")
    return s or "signature"


def _unique_id(base: str, existing: Iterable[str]) -> str:
    """If `base` collides, append _2, _3, … until unique."""
    existing_set = set(existing)
    if base not in existing_set:
        return base
    n = 2
    while f"{base}_{n}" in existing_set:
        n += 1
    return f"{base}_{n}"


def create_signature(*, display_name: str, role: str, png_bytes: bytes) -> Signature:
    """Persist a new signature: write the PNG + add the registry entry.

    The id is derived from the display name (e.g. "Lesley Smith" → "lesley_smith").
    Collisions get suffixed (_2, _3 …). Returns the resolved Signature.
    """
    if not png_bytes or png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Signature must be a PNG image")
    if len(png_bytes) > 1_000_000:
        raise ValueError("Signature PNG exceeds 1 MB — please use a smaller image")

    name = (display_name or "").strip()
    if not name:
        raise ValueError("Display name is required")

    reg = _read_registry()
    sig_id = _unique_id(_slugify(name), reg.keys())
    filename = f"{sig_id}.png"
    (_DIR / filename).write_bytes(png_bytes)

    meta = {
        "display_name": name,
        "role":         (role or "").strip(),
        "filename":     filename,
        "created_at":   datetime.now(timezone.utc).isoformat(),
    }
    reg[sig_id] = meta
    _write_registry(reg)
    logger.info("signatures.created id=%s name=%r bytes=%d", sig_id, name, len(png_bytes))

    return Signature(
        id=sig_id,
        display_name=name,
        role=meta["role"],
        filename=filename,
        created_at=meta["created_at"],
        size_bytes=len(png_bytes),
    )


def delete_signature(sig_id: str) -> bool:
    """Remove a signature from the registry + its PNG file. Idempotent."""
    reg = _read_registry()
    meta = reg.pop(sig_id, None)
    if not meta:
        return False
    _write_registry(reg)
    png = _DIR / meta.get("filename", f"{sig_id}.png")
    if png.is_file():
        try:
            png.unlink()
        except OSError as e:
            logger.warning("signatures.delete png_unlink_failed id=%s err=%s", sig_id, e)
    logger.info("signatures.deleted id=%s", sig_id)
    return True


# ---------------------------------------------------------------------------
# Substitution — called from the PDF render pipeline.
# ---------------------------------------------------------------------------
def find_used_anchors(body_html: str) -> list[str]:
    """Return the subset of KNOWN_ANCHORS that appear in body_html."""
    if not body_html:
        return []
    return [a for a in KNOWN_ANCHORS if a in body_html]


def _image_data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def _img_block(sig: Signature, *, width: int = 160, height: int = 60) -> str:
    """Render the inline signature image for one signatory.

    Kept deliberately minimal — a bare ``<img>`` tag — because the marker can
    appear inside a table cell, and fpdf2's ``write_html`` (the Windows
    fallback renderer) rejects nested block tags like ``<span>`` inside
    ``<td>``. A bare ``<img>`` renders correctly in both WeasyPrint and fpdf2.

    The signatory name/date caption is intentionally omitted: documents that
    use these anchors already have an adjacent "Signed by … / Date:" cell, so
    a baked-in caption would be redundant and risks breaking table layout in
    the fallback renderer.
    """
    path = _DIR / sig.filename
    if not path.is_file():
        return ""  # caller falls back to leaving the marker as text
    data_uri = _image_data_uri(path)
    return f'<img src="{data_uri}" width="{width}" height="{height}" alt="signature"/>'


def substitute(body_html: str, choices: dict[str, str] | None = None) -> tuple[str, dict[str, str]]:
    """Replace each ``/pg_sigN/`` anchor in ``body_html`` with the chosen
    signatory's PNG, wrapped in an inline <span><img>+caption</span> block.

    ``choices`` maps anchor → signature id (e.g. ``{"/pg_sig1/": "lesley_smith"}``).
    If an anchor has no explicit choice, falls back to the first available
    signature (alphabetical) so the renderer never leaves a half-substituted
    body in front of a recipient.

    Returns ``(new_html, applied)`` where ``applied`` is ``{anchor: signature_id}``
    so callers can log/audit which signatures landed.
    """
    if not body_html:
        return body_html, {}

    # Defensive unwrap: the TipTap editor (if autolink was ever on) wraps a
    # marker like /pg_sig1/ in an anchor tag — <a ... href="/pg_sig1/">/pg_sig1/</a>.
    # Strip that wrapper so the literal-string match below still works. Also
    # collapses the marker if it picked up surrounding entity noise.
    body_html = re.sub(
        r'<a\b[^>]*>\s*(/pg_sig\d/)\s*</a>',
        r'\1',
        body_html,
    )

    used = find_used_anchors(body_html)
    if not used:
        return body_html, {}

    sigs = list_signatures()
    if not sigs:
        logger.info("pre_signatures.substitute: anchors present but registry empty (%s)", used)
        return body_html, {}

    by_id = {s.id: s for s in sigs}
    default = sigs[0]   # alphabetical first as fallback

    applied: dict[str, str] = {}
    out = body_html
    for anchor in used:
        choice_id = (choices or {}).get(anchor)
        sig = by_id.get(choice_id) if choice_id else default
        if not sig:
            logger.warning(
                "pre_signatures.substitute: choice %s for %s not found — using default %s",
                choice_id, anchor, default.id,
            )
            sig = default
        block = _img_block(sig)
        if not block:
            logger.warning("pre_signatures.substitute: PNG missing for %s — leaving marker", sig.id)
            continue
        out = out.replace(anchor, block)
        applied[anchor] = sig.id
        logger.info(
            "pre_signatures.substituted anchor=%s signature_id=%s",
            anchor, sig.id,
        )
    return out, applied
