"""Sent-document versioning (migration 004).

A resend of a library document can revise the earlier send: it becomes the
next version, the earlier one is marked superseded, the exact HTML that went
out is kept, and - when the agent asks - the earlier signing envelope is
voided so the outdated version can no longer be signed.

These drive the real /send and /prepare routes through the in-memory
adapter. Email, PDF rendering and the signing provider are stubbed; nothing
leaves the process.
"""
import pytest
from fastapi import HTTPException

from app.core.auth import Agent
from app.core.signing import SignSubmission
from app.routers import library
from app.services import sent_documents as sd
from app.services.document_library import get_body, get_document

DOC = "tpl_43"
AGENT = Agent(email="agent@example.com")
CTX = {"tenant_full_name": "Tom Tenant", "property_address": "1 Test Street", "agency_name": "Test Lettings"}


@pytest.fixture
def harness(fake_db, monkeypatch, tmp_path):
    calls = {"emails": [], "envelopes": [], "voids": [], "void_error": None, "order": []}

    async def _email(to, **kw):
        calls["emails"].append(to)

    async def _sign(**kw):
        env = f"env-{len(calls['envelopes']) + 1}"
        calls["envelopes"].append(env)
        calls["order"].append(("send", env))
        return SignSubmission(provider="docusign", id=env, status="sent")

    async def _void(envelope_id, reason):
        calls["order"].append(("void", envelope_id))
        if calls["void_error"]:
            raise RuntimeError(calls["void_error"])
        calls["voids"].append(envelope_id)

    monkeypatch.setattr(library, "build_merge_context", lambda pid: dict(CTX))
    monkeypatch.setattr(library, "send_email", _email)
    monkeypatch.setattr(library, "send_for_signature", _sign)
    monkeypatch.setattr(library, "void_submission", _void)
    monkeypatch.setattr(library, "_render_pdf_with_fallback", lambda *a, **k: b"%PDF-1.4 test")
    monkeypatch.setattr(library, "_persist_doc_pdf", lambda pid, doc, data: f"/uploads/{pid}/library_{doc}/v.pdf")
    monkeypatch.setattr(library, "_audience_path", lambda: tmp_path / "doc_audience.json")

    calls["property_id"] = fake_db.create("properties", {"Address": "1 Test Street"})["id"]
    return calls


async def _send(h, *, mode="email_html", body="<p>Dear {{tenant_full_name}}</p>", **extra):
    req = library.SendRequest(
        mode=mode, title="Offer acceptance", body_html=body,
        recipients=[{"role": "Tenant", "name": "Tom", "email": "tom@example.com", "mandatory": True}],
        **extra,
    )
    return await library.send_library_doc(DOC, h["property_id"], req, agent=AGENT)


def _row(sent_id):
    return sd.summarise(sd.get_sent(sent_id))


@pytest.mark.asyncio
async def test_first_send_is_v1_and_keeps_the_copy_that_went_out(harness):
    r = await _send(harness)

    assert r["version"] == 1
    row = _row(r["sent_document_id"])
    assert (row["version"], row["revises_id"], row["superseded_at"]) == (1, None, None)
    # Stored after merge fields resolved: exactly what the recipient received.
    assert sd.get_body(r["sent_document_id"]) == "<p>Dear Tom Tenant</p>"


@pytest.mark.asyncio
async def test_revision_links_numbers_and_supersedes(harness):
    v1 = await _send(harness)
    v2 = await _send(harness, body="<p>Dear {{tenant_full_name}}, revised</p>",
                     revises_id=v1["sent_document_id"])

    assert v2["version"] == 2
    new, old = _row(v2["sent_document_id"]), _row(v1["sent_document_id"])
    assert new["revises_id"] == v1["sent_document_id"]
    assert old["superseded_at"] and not new["superseded_at"]
    assert sd.current_version(harness["property_id"], DOC)["submission_id"] == v2["sent_document_id"]

    listed = sd.list_for_property(harness["property_id"])
    assert [x["version"] for x in listed] == [2, 1]  # newest first
    assert all(x["revisable"] for x in listed)
    # Both copies kept: the history shows what each version said.
    assert sd.get_body(v1["sent_document_id"]) == "<p>Dear Tom Tenant</p>"
    assert sd.get_body(v2["sent_document_id"]) == "<p>Dear Tom Tenant, revised</p>"


@pytest.mark.asyncio
async def test_revising_an_older_version_is_refused_before_anything_is_sent(harness):
    v1 = await _send(harness)
    await _send(harness, revises_id=v1["sent_document_id"])
    sent_before, rows_before = len(harness["emails"]), len(sd.list_for_property(harness["property_id"]))

    with pytest.raises(HTTPException) as exc:
        await _send(harness, revises_id=v1["sent_document_id"])

    assert exc.value.status_code == 409
    assert len(harness["emails"]) == sent_before
    assert len(sd.list_for_property(harness["property_id"])) == rows_before


@pytest.mark.asyncio
async def test_revision_must_be_this_document_on_this_property(harness, fake_db):
    other = sd.record_sent(property_id=harness["property_id"], doc_id="tpl_05",
                           doc_name="Offer confirmation", stage=4, channel="Email PDF")
    with pytest.raises(HTTPException) as wrong_doc:
        await _send(harness, revises_id=other)
    assert wrong_doc.value.status_code == 400

    with pytest.raises(HTTPException) as unknown:
        await _send(harness, revises_id="00000000-0000-0000-0000-000000000000")
    assert unknown.value.status_code == 404

    with pytest.raises(HTTPException) as nothing_to_void:
        await _send(harness, void_previous=True)
    assert nothing_to_void.value.status_code == 400
    assert harness["emails"] == []


@pytest.mark.asyncio
async def test_void_previous_cancels_the_old_envelope_after_the_new_one_is_out(harness):
    v1 = await _send(harness, mode="sign")
    v2 = await _send(harness, mode="sign", revises_id=v1["sent_document_id"], void_previous=True)

    assert v2["previous_voided"] is True
    assert harness["voids"] == ["env-1"]
    # Never void first: a failed send would leave nothing valid to sign.
    assert harness["order"] == [("send", "env-1"), ("send", "env-2"), ("void", "env-1")]
    old = _row(v1["sent_document_id"])
    assert old["status"] == "Voided" and old["envelope_open"] is False
    assert _row(v2["sent_document_id"])["envelope_open"] is True


@pytest.mark.asyncio
async def test_a_void_the_provider_refuses_is_reported_not_raised(harness):
    v1 = await _send(harness, mode="sign")
    harness["void_error"] = "envelope already completed"

    v2 = await _send(harness, mode="sign", revises_id=v1["sent_document_id"], void_previous=True)

    assert "could not be voided" in v2["previous_void_error"]
    assert "envelope already completed" in v2["previous_void_error"]
    assert _row(v2["sent_document_id"])["version"] == 2  # the revision still went out
    old = _row(v1["sent_document_id"])
    assert old["status"] == "Sent" and old["superseded_at"]


@pytest.mark.asyncio
async def test_a_signed_envelope_is_never_voided(harness):
    v1 = await _send(harness, mode="sign")
    sd.update_status_by_envelope("env-1", "Signed", completed=True)

    v2 = await _send(harness, mode="sign", revises_id=v1["sent_document_id"], void_previous=True)

    assert harness["voids"] == [] and "previous_voided" not in v2
    assert _row(v1["sent_document_id"])["status"] == "Signed"


@pytest.mark.asyncio
async def test_an_unvoided_old_version_signed_later_is_still_recorded(harness):
    v1 = await _send(harness, mode="sign")
    await _send(harness, mode="sign", revises_id=v1["sent_document_id"])  # no void

    assert sd.update_status_by_envelope("env-1", "Signed", completed=True) is True
    old = _row(v1["sent_document_id"])
    assert old["status"] == "Signed" and old["superseded_at"]  # shown as the superseded version


@pytest.mark.asyncio
async def test_prepare_offers_the_current_version_and_revises_from_the_sent_copy(harness):
    pid = harness["property_id"]
    fresh = library.prepare_library_doc(DOC, pid, from_sent=None, _=AGENT)
    assert fresh["previous"] is None and fresh["revising"] is None

    v1 = await _send(harness, body="<p>Dear {{tenant_full_name}}, as agreed by phone</p>")
    again = library.prepare_library_doc(DOC, pid, from_sent=None, _=AGENT)
    assert again["previous"]["submission_id"] == v1["sent_document_id"]
    assert again["body_html"] == get_body(get_document(DOC))  # opening normally: the template

    revise = library.prepare_library_doc(DOC, pid, from_sent=v1["sent_document_id"], _=AGENT)
    assert revise["body_html"] == "<p>Dear Tom Tenant, as agreed by phone</p>"
    assert revise["revising"]["from_snapshot"] is True
    assert revise["revising"]["version"] == 1


@pytest.mark.asyncio
async def test_revising_a_send_that_kept_no_copy_starts_from_the_template(harness):
    # Sends from before versioning have a row but no stored body.
    old = sd.record_sent(property_id=harness["property_id"], doc_id=DOC,
                         doc_name="TPL-43", stage=4, channel="Email PDF")

    revise = library.prepare_library_doc(DOC, harness["property_id"], from_sent=old, _=AGENT)

    assert revise["body_html"] == get_body(get_document(DOC))
    assert revise["revising"]["from_snapshot"] is False
