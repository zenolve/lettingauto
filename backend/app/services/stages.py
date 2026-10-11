"""Where a property is in the pipeline, worked out from its fields.

Priority is most-advanced state first: a tenancy that has been ended outranks
its signatures, and a signed tenancy agreement outranks a landlord still
missing an EICR. Stage 9 comes from ``Tenancy Ended Date`` ("End tenancy");
a re-let clears it along with the rest of the tenancy, which drops the
property back to the offer stage.

Single backend copy - the dashboard, the property list and the stage guards
all call this. Mirrors ``frontend/src/lib/stages.ts:deriveCurrentStage``;
keep the two in step.
"""
from __future__ import annotations

CERT_KEYS = ("Gas_Cert_Status", "EPC_Status", "EICR_Status")
_CERT_ACCEPTABLE = ("On File", "Agency Arranging")


def derive_stage(f: dict) -> int:
    if f.get("Tenancy Ended Date"):
        return 9
    if f.get("TA_LL_Signed") and f.get("TA_TT_Signed"):
        return 8
    tenant_linked = bool(f.get("Tenant"))
    if tenant_linked and (f.get("TA_LL_Signed") or f.get("TA_TT_Signed")):
        return 7
    if tenant_linked and f.get("LL_Offer_Accepted"):
        return 6
    if tenant_linked:
        return 5
    if f.get("TC_Signed"):
        return 4
    if all(f.get(k) in _CERT_ACCEPTABLE for k in CERT_KEYS):
        return 3
    if bool(f.get("Landlords")) and any(f.get(k) for k in CERT_KEYS):
        return 2
    return 1
