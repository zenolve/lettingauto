"""File uploads — per-property document storage.

Replaces the legacy "url" fields on landlord admin / verification forms (which
used to point at Tally's storage). Files now live on the backend filesystem
under ``backend/uploads/<property_id>/<bucket>/<timestamped_filename>`` and are
served back via the static ``/uploads`` mount.

Endpoints:
  POST  /api/uploads/{property_id}/{bucket}   (agent or form-token auth)
        multipart form-data: `file=<binary>`
        Returns: { "url": "/uploads/<property_id>/<bucket>/<file>",
                   "filename": "<original.ext>",
                   "size": <bytes>,
                   "content_type": "<mime>" }

  GET   /uploads/<property_id>/<bucket>/<file>  (static mount; see main.py)

Buckets in use (one per logical field on the admin/verification forms):
  mortgage_consent, head_lease, freeholder_consent, insurance_cert,
  gas_cert, epc, eicr, id_document, address_doc, ownership_doc,
  incorporation_doc, bank_statements, visa_snapshot, other.

Authorization:
  - Agents send `Authorization: Bearer <jwt>`.
  - Public form pages (landlord admin/verification) call with `?token=<form_token>`
    minted for the property. The token's property_id must match the URL.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status

from app.core.auth import Agent, decode_form_token, require_agent
from app.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/uploads", tags=["uploads"])


# Root for stored files. Lives outside the package source tree so it survives
# code redeploys without rebuilding. Symlinkable to a network share or S3 mount
# if we move off local disk later.
UPLOADS_ROOT = Path(__file__).resolve().parent.parent.parent / "uploads"
UPLOADS_ROOT.mkdir(parents=True, exist_ok=True)


# Per-bucket size + extension policy. Keeps the surface area tight so an
# attacker can't dump a 1GB .exe into our static mount.
MAX_BYTES = 25 * 1024 * 1024  # 25MB
ALLOWED_EXTS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif",
    ".doc", ".docx", ".xls", ".xlsx", ".txt",
}
ALLOWED_BUCKETS = {
    "mortgage_consent", "head_lease", "freeholder_consent", "insurance_cert",
    "gas_cert", "epc", "eicr",
    "id_document", "address_doc", "ownership_doc", "incorporation_doc",
    "bank_statements", "visa_snapshot",
    "photos", "floor_plan", "tds_certificate", "passport", "utility_bill",
    "other",
}

# Supabase rows use UUID ids; legacy Airtable "rec..." ids are still accepted
# so pre-migration upload folders stay reachable.
_PROPERTY_ID_RE = re.compile(
    r"^(rec[a-zA-Z0-9]{14}"
    r"|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$"
)
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _check_property_id(property_id: str) -> None:
    if not _PROPERTY_ID_RE.match(property_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "property_id must be a record id (uuid)")


def _check_bucket(bucket: str) -> None:
    if bucket not in ALLOWED_BUCKETS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"bucket must be one of: {', '.join(sorted(ALLOWED_BUCKETS))}",
        )


def _safe_filename(name: str) -> str:
    # Strip directory components and replace anything unusual with underscores.
    base = Path(name).name
    return _UNSAFE_CHARS.sub("_", base)[:200] or "file"


def _ensure_dir(property_id: str, bucket: str) -> Path:
    target = UPLOADS_ROOT / property_id / bucket
    target.mkdir(parents=True, exist_ok=True)
    return target


def _public_url(property_id: str, bucket: str, filename: str) -> str:
    # Absolute URL so Airtable URL-type fields accept it directly (Airtable
    # rejects relative paths). Falls back to a relative path if app_base_url
    # is not configured.
    from app.config import settings  # noqa: PLC0415
    base = (settings.app_base_url or "").rstrip("/")
    rel = f"/uploads/{property_id}/{bucket}/{filename}"
    return f"{base}{rel}" if base else rel


@router.post("/{property_id}/{bucket}", status_code=status.HTTP_201_CREATED)
async def upload_file(
    property_id: str,
    bucket: str,
    file: UploadFile = File(...),
    token: str = Query(..., description="Form token minted for this property"),
) -> dict:
    """Public upload (used by the landlord admin/verification form pages).

    Requires a form token that's bound to this exact `property_id`. Agents
    should use the `/api/uploads/agent/...` variant instead.
    """
    _check_property_id(property_id)
    _check_bucket(bucket)

    payload = decode_form_token(token)
    if payload.property_id != property_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Form token does not match property_id")

    contents = await file.read(MAX_BYTES + 1)
    if len(contents) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {MAX_BYTES} bytes")

    original = _safe_filename(file.filename or "upload")
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"File extension {ext!r} not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    nonce = secrets.token_hex(4)
    stored_name = f"{stamp}_{nonce}_{original}"
    target_dir = _ensure_dir(property_id, bucket)
    target_path = target_dir / stored_name
    target_path.write_bytes(contents)

    url = _public_url(property_id, bucket, stored_name)
    logger.info(
        "upload.stored property=%s bucket=%s file=%s size=%d url=%s",
        property_id, bucket, original, len(contents), url,
    )
    return {
        "url": url,
        "filename": original,
        "size": len(contents),
        "content_type": file.content_type,
    }


@router.post("/agent/{property_id}/{bucket}", status_code=status.HTTP_201_CREATED)
async def upload_file_as_agent(
    property_id: str,
    bucket: str,
    file: UploadFile = File(...),
    _: Agent = Depends(require_agent),
) -> dict:
    """Agent-authenticated upload variant. Same shape as the public route."""
    _check_property_id(property_id)
    _check_bucket(bucket)

    contents = await file.read(MAX_BYTES + 1)
    if len(contents) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {MAX_BYTES} bytes")

    original = _safe_filename(file.filename or "upload")
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"File extension {ext!r} not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    nonce = secrets.token_hex(4)
    stored_name = f"{stamp}_{nonce}_{original}"
    target_dir = _ensure_dir(property_id, bucket)
    (target_dir / stored_name).write_bytes(contents)

    url = _public_url(property_id, bucket, stored_name)
    logger.info(
        "upload.stored property=%s bucket=%s file=%s size=%d url=%s by=agent",
        property_id, bucket, original, len(contents), url,
    )
    return {
        "url": url,
        "filename": original,
        "size": len(contents),
        "content_type": file.content_type,
    }


@router.get("/{property_id}/list")
def list_property_uploads(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """List all stored files for a property, grouped by bucket. Agent-only."""
    _check_property_id(property_id)
    base = UPLOADS_ROOT / property_id
    out: dict[str, list[dict]] = {}
    if not base.exists():
        return {"property_id": property_id, "buckets": out}
    for bucket_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        files: list[dict] = []
        for f in sorted(bucket_dir.iterdir()):
            if not f.is_file():
                continue
            mtime = f.stat().st_mtime
            files.append({
                "filename": f.name,
                "size": f.stat().st_size,
                "url": _public_url(property_id, bucket_dir.name, f.name),
                "uploaded_at": datetime.utcfromtimestamp(mtime).isoformat() + "Z",
            })
        out[bucket_dir.name] = files
    return {"property_id": property_id, "buckets": out}


# ---------------------------------------------------------------------------
# Bucket → Airtable URL-field mapping. When a file is uploaded to / replaced
# in / deleted from one of these buckets, the agent-facing uploads manager
# syncs the matching record's URL field automatically.
#
#   target = "properties"  → field on the Properties record
#   target = "landlord"    → field on the FIRST linked Landlord (primary)
#
# Buckets not listed here are file-only (the file is still served, but no
# Airtable column tracks it).
# ---------------------------------------------------------------------------
BUCKET_FIELD_MAP: dict[str, dict[str, str]] = {
    "mortgage_consent":    {"target": "properties", "field": "mortgage_consent_url"},
    "head_lease":          {"target": "properties", "field": "head_lease_url"},
    "freeholder_consent":  {"target": "properties", "field": "freeholder_consent_url"},
    "insurance_cert":      {"target": "properties", "field": "Insurance_certificate_url"},
    "id_document":         {"target": "landlord",   "field": "ID Document URL"},
    "visa_snapshot":       {"target": "landlord",   "field": "Visa Snapshot URL"},
    "address_doc":         {"target": "landlord",   "field": "Address Document URL"},
    "ownership_doc":       {"target": "landlord",   "field": "Ownership Document URL"},
    "incorporation_doc":   {"target": "landlord",   "field": "Incorporation Doc URL"},
    "bank_statements":     {"target": "landlord",   "field": "Bank Statements URL"},
}


def _sync_bucket_url_to_airtable(property_id: str, bucket: str, url: str | None) -> dict | None:
    """If this bucket maps to an Airtable URL field, write `url` (or null) there.

    Returns a small `{table, field, record_id}` audit object on success, or
    `None` if the bucket has no Airtable mapping.
    """
    from app.db import supabase_client as at  # noqa: PLC0415

    mapping = BUCKET_FIELD_MAP.get(bucket)
    if not mapping:
        return None
    field = mapping["field"]
    target = mapping["target"]
    if target == "properties":
        at.update(at.TableNames.PROPERTIES, property_id, {field: url})
        return {"table": "properties", "field": field, "record_id": property_id}
    if target == "landlord":
        prop = at.get(at.TableNames.PROPERTIES, property_id)
        linked = prop.get("fields", {}).get("Landlords") or []
        if not linked:
            logger.warning("upload.sync.no_landlord property=%s bucket=%s", property_id, bucket)
            return None
        landlord_id = linked[0]
        at.update(at.TableNames.LANDLORDS, landlord_id, {field: url})
        return {"table": "landlords", "field": field, "record_id": landlord_id}
    return None


def _find_remaining_url_for_bucket(property_id: str, bucket: str) -> str | None:
    """After deleting a file, pick a sensible URL to leave in the Airtable
    field. Prefer the most-recently-uploaded remaining file; if none, return
    None (cleared)."""
    bucket_dir = UPLOADS_ROOT / property_id / bucket
    if not bucket_dir.exists():
        return None
    remaining = [p for p in bucket_dir.iterdir() if p.is_file()]
    if not remaining:
        return None
    latest = max(remaining, key=lambda p: p.name)  # name carries the timestamp prefix
    return _public_url(property_id, bucket, latest.name)


@router.delete("/agent/{property_id}/{bucket}/{filename}", status_code=status.HTTP_200_OK)
def delete_uploaded_file(
    property_id: str,
    bucket: str,
    filename: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """Delete one stored file from a bucket, then re-sync the matching
    Airtable URL field (clears it if no files remain, or points at the
    newest remaining file)."""
    _check_property_id(property_id)
    _check_bucket(bucket)
    if "/" in filename or "\\" in filename or filename in ("", ".", ".."):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid filename")

    target = UPLOADS_ROOT / property_id / bucket / filename
    if not target.exists() or not target.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")
    target.unlink()
    logger.info("upload.deleted property=%s bucket=%s file=%s", property_id, bucket, filename)

    # Re-sync Airtable: point at next-newest file, or clear the field.
    next_url = _find_remaining_url_for_bucket(property_id, bucket)
    synced = None
    try:
        synced = _sync_bucket_url_to_airtable(property_id, bucket, next_url)
    except Exception as e:  # noqa: BLE001
        logger.warning("upload.delete.sync_failed err=%s", e)

    return {"deleted": filename, "synced": synced, "remaining_url": next_url}


@router.post("/agent/{property_id}/{bucket}/replace", status_code=status.HTTP_200_OK)
async def replace_uploaded_file(
    property_id: str,
    bucket: str,
    file: UploadFile = File(...),
    delete_filename: str | None = Query(None, description="Optional: filename of the old file to remove after the upload succeeds"),
    _: Agent = Depends(require_agent),
) -> dict:
    """Upload a new file to a bucket, optionally remove a named old file,
    then sync the new URL into the matching Airtable URL column."""
    _check_property_id(property_id)
    _check_bucket(bucket)

    contents = await file.read(MAX_BYTES + 1)
    if len(contents) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, f"File exceeds {MAX_BYTES} bytes")

    original = _safe_filename(file.filename or "upload")
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"File extension {ext!r} not allowed. Allowed: {', '.join(sorted(ALLOWED_EXTS))}",
        )

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    nonce = secrets.token_hex(4)
    stored_name = f"{stamp}_{nonce}_{original}"
    target_dir = _ensure_dir(property_id, bucket)
    (target_dir / stored_name).write_bytes(contents)
    new_url = _public_url(property_id, bucket, stored_name)
    logger.info(
        "upload.replaced property=%s bucket=%s new=%s old=%s by=agent",
        property_id, bucket, stored_name, delete_filename,
    )

    # Optional cleanup of the old file (after new one is safely on disk).
    if delete_filename and "/" not in delete_filename and "\\" not in delete_filename:
        old_path = target_dir / delete_filename
        if old_path.exists() and old_path.is_file():
            old_path.unlink()

    synced = None
    try:
        synced = _sync_bucket_url_to_airtable(property_id, bucket, new_url)
    except Exception as e:  # noqa: BLE001
        logger.warning("upload.replace.sync_failed err=%s", e)

    return {
        "url": new_url,
        "filename": original,
        "size": len(contents),
        "synced": synced,
    }


@router.get("/{property_id}/buckets")
def list_known_buckets(
    property_id: str,
    _: Agent = Depends(require_agent),
) -> dict:
    """Returns the full set of buckets known to the system plus a hint about
    whether each bucket syncs to an Airtable URL field. Used by the agent
    uploads page so empty buckets still appear."""
    _check_property_id(property_id)
    return {
        "buckets": [
            {
                "name": name,
                "syncs_to_airtable": name in BUCKET_FIELD_MAP,
                "airtable_target": BUCKET_FIELD_MAP.get(name),
            }
            for name in sorted(ALLOWED_BUCKETS)
        ],
    }
