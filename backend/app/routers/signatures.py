"""Signatures admin CRUD — agent-managed signatory registry.

Used by the ``/agent/signatures`` admin page. Each signature is a PNG image
plus a small metadata record (display name, role). The LibraryEditor reads
this list to populate the dropdown that fills each ``/pg_sigN/`` slot in a
document.

PNG bytes can arrive two ways:
  - **Upload**: agent picks a transparent-bg PNG file → multipart POST
  - **Draw**:   agent signs on a <canvas> → exported as PNG base64 → JSON POST

Both paths converge on ``pre_signatures.create_signature``.
"""
from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field

from app.core.auth import Agent, require_agent
from app.core.logger import get_logger
from app.services import pre_signatures

logger = get_logger(__name__)

router = APIRouter(prefix="/api/signatures", tags=["signatures"])


@router.get("")
def list_(_: Agent = Depends(require_agent)) -> dict[str, Any]:
    """Return every installed signature (id, display name, role, size)."""
    return {"signatures": [s.to_dict() for s in pre_signatures.list_signatures()]}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def create_via_upload(
    file: UploadFile = File(...),
    display_name: str = Form(...),
    role: str = Form(""),
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Multipart upload of a PNG — used by the file-picker on the admin page."""
    contents = await file.read(2_000_000)   # generous 2MB read cap; create_signature enforces 1MB final
    try:
        sig = pre_signatures.create_signature(
            display_name=display_name,
            role=role,
            png_bytes=contents,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return sig.to_dict()


class DrawnSignature(BaseModel):
    display_name: str = Field(..., min_length=1)
    role: str = ""
    # Data URL (``data:image/png;base64,...``) emitted by the canvas via
    # ``canvas.toDataURL('image/png')``. We strip the prefix and base64-decode.
    data_url: str


@router.post("/draw", status_code=status.HTTP_201_CREATED)
def create_via_draw(
    body: DrawnSignature,
    _: Agent = Depends(require_agent),
) -> dict[str, Any]:
    """Canvas-drawn signature — used by the in-browser signature pad."""
    prefix = "data:image/png;base64,"
    if not body.data_url.startswith(prefix):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "data_url must be a base64 PNG")
    try:
        png_bytes = base64.b64decode(body.data_url[len(prefix):], validate=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Invalid base64 PNG: {e}")
    try:
        sig = pre_signatures.create_signature(
            display_name=body.display_name,
            role=body.role,
            png_bytes=png_bytes,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return sig.to_dict()


@router.delete("/{signature_id}", status_code=status.HTTP_200_OK)
def delete(signature_id: str, _: Agent = Depends(require_agent)) -> dict[str, Any]:
    """Remove a signature. Idempotent — returns ``{deleted: bool}``."""
    return {"deleted": pre_signatures.delete_signature(signature_id)}
