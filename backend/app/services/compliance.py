"""PG_02 compliance check engine (spec §6.2.1).

Produces a structured `ComplianceReport` consumed by the agent summary email.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.services.derivations import is_overseas, parse_iso_date


@dataclass
class ComplianceReport:
    flags: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(self.warnings or self.actions)

    def to_dict(self) -> dict:
        return {"flags": self.flags, "warnings": self.warnings, "actions": self.actions,
                "has_issues": self.has_issues}


def _days_until(d: Optional[date]) -> Optional[int]:
    if not d:
        return None
    return (d - date.today()).days


def run_checks(*, admin: dict) -> ComplianceReport:
    """Run all PG_02 admin-form compliance checks.

    `admin` is a dict of normalised values:
        residency, nrl_approval_number,
        gas_cert_status, gas_cert_expiry (date or None),
        epc_status, epc_rating,
        eicr_status, eicr_expiry (date or None),
        smoke_detectors, furniture_fire,
        consent_mortgagor, mortgage_consent_upload,
        tenure, freeholder_consent, insurance_in_place,
        has_photos, auth_photos,
        supply_keys, alt_access,
        has_inventory, auth_inventory,
        service_level, third_party_manager
    """
    r = ComplianceReport()
    isNRL = is_overseas(admin.get("residency"))

    # --- NRL --------------------------------------------------------------
    nrl_num = (admin.get("nrl_approval_number") or "").strip()
    if isNRL and not nrl_num:
        r.flags.append("Non-resident landlord — 20% withholding ACTIVE.")
        r.actions.append("Chase landlord for HMRC NRL approval number.")
    elif isNRL and nrl_num:
        r.flags.append(f"NRL approval number on file: {nrl_num}")

    # --- Gas certificate --------------------------------------------------
    gas = admin.get("gas_cert_status")
    gas_exp: Optional[date] = admin.get("gas_cert_expiry")
    if gas == "Not Provided":
        r.warnings.append("URGENT: No gas certificate. Landlord declined arrangement. Property cannot proceed.")
    elif gas == "Palace Gate Arranging":
        r.actions.append("URGENT: Instruct Gas Safe engineer. Create checklist item.")
    elif gas == "On File":
        d = _days_until(gas_exp)
        if d is not None and d < 0:
            r.warnings.append(f"Gas cert EXPIRED {abs(d)} days ago. New cert required.")
        elif d is not None and d < 30:
            r.warnings.append(f"Gas cert expires in {d} days. Consider renewing.")
        else:
            r.flags.append(f"Gas cert on file. Expires {gas_exp} ({d} days).")

    # --- EPC --------------------------------------------------------------
    epc = admin.get("epc_status")
    epc_rating = (admin.get("epc_rating") or "").strip().upper()
    if epc == "Not Provided":
        r.warnings.append("No EPC. Landlord declined arrangement. Legal requirement.")
    elif epc == "Palace Gate Arranging":
        r.actions.append("Instruct accredited EPC assessor. Create checklist item.")
    elif epc == "On File":
        if epc_rating in ("F", "G"):
            r.warnings.append(f"URGENT: EPC rating {epc_rating}. Cannot legally let. Landlord must upgrade.")
        else:
            r.flags.append(f"EPC on file. Rating: {epc_rating}.")

    # --- EICR -------------------------------------------------------------
    eicr = admin.get("eicr_status")
    eicr_exp: Optional[date] = admin.get("eicr_expiry")
    if eicr == "Not Provided":
        r.warnings.append("No EICR. Legal requirement since April 2021.")
    elif eicr == "Palace Gate Arranging":
        r.actions.append("Instruct NICEIC/NAPIT electrician. Create checklist item.")
    elif eicr == "On File":
        d = _days_until(eicr_exp)
        if d is not None and d < 0:
            r.warnings.append(f"EICR EXPIRED {abs(d)} days ago. New report required.")
        else:
            r.flags.append(f"EICR on file. Expires {eicr_exp} ({d} days).")

    # --- Misc property-level warnings ------------------------------------
    if (admin.get("smoke_detectors") or "").lower().startswith("no"):
        r.warnings.append("Smoke detectors NOT fitted. Legal requirement.")
    if (admin.get("furniture_fire") or "").lower().startswith("no"):
        r.warnings.append("Furniture may not comply with Fire Regulations.")
    if (admin.get("consent_mortgagor") or "").lower().startswith("yes") and not admin.get("mortgage_consent_upload"):
        r.warnings.append("Mortgage consent required but no document uploaded.")
    if (admin.get("tenure") or "").lower() == "leasehold" and (admin.get("freeholder_consent") or "").lower().startswith("no"):
        r.warnings.append("LEASEHOLD: Freeholder consent not confirmed. Urgent.")
    if (admin.get("insurance_in_place") or "").lower().startswith("no"):
        r.warnings.append("No insurance in place. Advise landlord.")

    # --- Photos -----------------------------------------------------------
    if (admin.get("has_photos") or "").lower().startswith("no"):
        if (admin.get("auth_photos") or "").lower().startswith("yes"):
            r.actions.append("Arrange photography. Landlord authorised.")
        else:
            r.warnings.append("No photos. Landlord declined authorisation.")

    # --- Keys / access ---------------------------------------------------
    if (admin.get("supply_keys") or "").lower().startswith("no"):
        r.warnings.append(f"No keys supplied. Alt access: {admin.get('alt_access') or '—'}")

    # --- Inventory --------------------------------------------------------
    if (admin.get("has_inventory") or "").lower().startswith("no"):
        if (admin.get("auth_inventory") or "").lower().startswith("yes"):
            r.actions.append("Prepare inventory. Landlord authorised.")
        else:
            r.warnings.append("No inventory. Landlord declined authorisation.")

    # --- Third party manager / who-manages-property ----------------------
    # When the landlord picks "Other" (or "Other manages but PG collects rent"),
    # service-level derivation drops it onto Let Only/Rent Collection. We
    # surface this explicitly so the agent confirms PG isn't on the hook for
    # day-to-day management, and to chase the third-party contact details.
    wm_raw = (admin.get("who_manages_property") or "").strip().lower()
    is_other_manager = wm_raw.startswith("other")
    third = (admin.get("third_party_manager") or "").strip()
    if is_other_manager and not third:
        r.warnings.append(
            "Property managed by a third party — no manager contact details on file."
        )
    elif is_other_manager and third:
        r.flags.append(f"Third party manager: {third}")
    elif admin.get("service_level") == "Let Only" and third:
        r.flags.append(f"Third party manager: {third}. Service level = Let Only.")

    # --- Bank details -----------------------------------------------------
    # Rent disbursement is impossible without these. Flag any missing piece
    # so the agent can chase before stage 5 (offer accepted).
    bank_keys = ("bank_name", "sort_code", "account_name", "account_number")
    missing_bank = [k for k in bank_keys if not (admin.get(k) or "").strip()]
    if len(missing_bank) == len(bank_keys):
        r.actions.append("Bank details missing — chase before first rent disbursement.")
    elif missing_bank:
        r.actions.append(
            f"Partial bank details: missing {', '.join(missing_bank)}. Chase landlord."
        )

    return r
