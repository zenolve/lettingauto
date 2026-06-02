"""Backfill an Accepted Offer row for every property that already has a
linked tenant (pre-Gap-5 data).

After the Gap 5 rewrite, ``Properties.Tenant`` is only set when an offer is
accepted, and the lifecycle lives in the ``Offers`` table. Properties created
under the old model have a tenant link but no Offer row — this script creates
one ``Status=Accepted`` offer per such property so the data is consistent and
the new Stage-4 offers UI shows them.

Idempotent: skips any property that already has at least one Offer row.

Run from ``backend/``:

    python -m scripts.backfill_offers          # dry run (prints plan)
    python -m scripts.backfill_offers --apply   # actually create rows
"""
from __future__ import annotations

import sys
from datetime import date

from app.db import airtable_client as at


def _first(v):
    return v[0] if isinstance(v, list) and v else None


def main(apply: bool) -> None:
    props = at.all_records(at.TableNames.PROPERTIES)
    created = 0
    skipped = 0
    for p in props:
        pid = p["id"]
        pf = p.get("fields", {})
        tenant_ids = pf.get("Tenant") or []
        if not tenant_ids:
            continue
        if pf.get("Offers"):
            skipped += 1
            continue

        # Snapshot terms from the lead tenant.
        lead_id = _first(tenant_ids)
        tf = {}
        if lead_id:
            try:
                tf = at.get(at.TableNames.TENANTS, lead_id).get("fields", {})
            except Exception:
                pass

        fields = {
            "Name": f"Offer · {tf.get('Name', 'tenant')} · {pf.get('Address', '')}".strip(" ·"),
            "Property": [pid],
            "Tenants": tenant_ids,
            "Status": "Accepted",
            "Offered Rent": tf.get("Amount"),
            "Rent Frequency": tf.get("Rent_Frequency"),
            "Deposit": tf.get("Deposit Amount"),
            "Holding Deposit": tf.get("Holding_Deposit"),
            "Start Date": tf.get("Start Date"),
            "End Date": tf.get("End Date"),
            "Tenancy Term": tf.get("Tenancy Term"),
            "Holding Deposit Deadline": pf.get("Holding_Deposit_Deadline"),
            "Created At": date.today().isoformat(),
            "Closed At": date.today().isoformat(),
            "Close Reason": "Backfilled from existing tenant link (pre-Gap-5).",
            "Created By": "migration",
        }
        fields = {k: v for k, v in fields.items() if v is not None}

        if apply:
            rec = at.create(at.TableNames.OFFERS, fields)
            print(f"[ok]   {pf.get('Address','?'):40} -> offer {rec['id']}")
        else:
            print(f"[plan] would create Accepted offer for {pf.get('Address','?')} "
                  f"({len(tenant_ids)} tenant(s))")
        created += 1

    verb = "created" if apply else "would create"
    print(f"\n{verb} {created} offer(s); skipped {skipped} property(ies) that already have offers.")
    if not apply:
        print("Dry run — re-run with --apply to write.")


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
