"""File links must not carry a host.

Every upload route used to bake APP_BASE_URL into the link it returned and
stored. Left at its default, that sent each file opened on the live site to
http://localhost:8000. Links are now host-relative (``/uploads/...``) and the
frontend resolves them against whichever host serves the app.
"""
import io

import pytest
from fastapi import UploadFile

from app.config import settings
from app.core.auth import Agent
from app.routers import uploads

AGENT = Agent(email="agent@example.com")


@pytest.fixture
def prop(fake_db, tmp_path, monkeypatch):
    monkeypatch.setattr(uploads, "UPLOADS_ROOT", tmp_path)
    monkeypatch.setattr(settings, "app_base_url", "http://localhost:8000")
    pid = fake_db.create("properties", {"Address": "3 Hostless Row"})["id"]
    lid = fake_db.create("landlords", {"Full Name": "Lara Landlord"})["id"]
    fake_db.update("properties", pid, {"Landlords": [lid]})
    return pid, lid


def _pdf(name="doc.pdf"):
    return UploadFile(file=io.BytesIO(b"%PDF-1.4"), filename=name)


def _assert_relative(url, pid, bucket):
    assert url.startswith(f"/uploads/{pid}/{bucket}/"), url


@pytest.mark.asyncio
async def test_agent_upload_and_listing_return_relative_links(prop):
    pid, _ = prop
    out = await uploads.upload_file_as_agent(pid, "other", file=_pdf(), expiry=None, _=AGENT)
    _assert_relative(out["url"], pid, "other")

    listed = uploads.list_property_uploads(pid, _=AGENT)["buckets"]["other"]
    assert [f["url"] for f in listed] == [out["url"]]


@pytest.mark.asyncio
async def test_replace_stores_a_relative_link_on_the_record(prop, fake_db):
    pid, lid = prop
    out = await uploads.replace_uploaded_file(
        pid, "id_document", file=_pdf("passport.pdf"), delete_filename=None, expiry=None, _=AGENT,
    )
    _assert_relative(out["url"], pid, "id_document")
    assert fake_db.get("landlords", lid)["fields"]["ID Document URL"] == out["url"]

    out = await uploads.replace_uploaded_file(
        pid, "insurance_cert", file=_pdf(), delete_filename=None, expiry=None, _=AGENT,
    )
    assert fake_db.get("properties", pid)["fields"]["Insurance_certificate_url"] == out["url"]


@pytest.mark.asyncio
async def test_deleting_repoints_the_record_at_a_relative_link(prop, fake_db):
    pid, _ = prop
    first = await uploads.replace_uploaded_file(
        pid, "insurance_cert", file=_pdf("a.pdf"), delete_filename=None, expiry=None, _=AGENT,
    )
    second = await uploads.replace_uploaded_file(
        pid, "insurance_cert", file=_pdf("b.pdf"), delete_filename=None, expiry=None, _=AGENT,
    )
    stored = second["url"].rsplit("/", 1)[1]

    out = uploads.delete_uploaded_file(pid, "insurance_cert", stored, _=AGENT)

    assert out["remaining_url"] == first["url"]
    assert fake_db.get("properties", pid)["fields"]["Insurance_certificate_url"] == first["url"]
