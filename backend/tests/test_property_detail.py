"""The property page payload carries every party, not just the first.

A joint tenancy links two or more tenants to the property, but the detail
route only returned the first - so the second could not be opened from
"Edit records" or seen on the tenant card.
"""
from app.core.auth import Agent
from app.routers import properties

AGENT = Agent(email="agent@example.com")


def test_joint_tenants_are_all_returned_lead_first(fake_db):
    pid = fake_db.create("properties", {"Address": "12 Joint Street"})["id"]
    lead = fake_db.create("tenants", {"Name": "Tamara Ralph"})["id"]
    joint = fake_db.create("tenants", {"Name": "Bhanu Choudhrie"})["id"]
    fake_db.update("properties", pid, {"Tenant": [lead, joint]})

    out = properties.get_property(pid, _=AGENT)

    assert [t["id"] for t in out["tenants"]] == [lead, joint]
    assert [t["Name"] for t in out["tenants"]] == ["Tamara Ralph", "Bhanu Choudhrie"]
    assert out["tenant"]["id"] == lead


def test_no_tenant_yet(fake_db):
    pid = fake_db.create("properties", {"Address": "1 Empty Road"})["id"]

    out = properties.get_property(pid, _=AGENT)

    assert out["tenants"] == [] and out["tenant"] is None
