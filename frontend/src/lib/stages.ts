/**
 * Frontend stage model — 9 conceptual stages the agent navigates through.
 *
 * The live Airtable base has 17 stage records with finer-grained names, but
 * the UI only needs nine logical buckets. We derive the current stage from
 * concrete property fields (landlord linked, certs uploaded, T&C signed, etc.)
 * rather than relying on the Airtable Stage Name string, which has drifted.
 *
 * See backend/app/handlers/pg00_gate.py for the matching backend transitions.
 */
import type { PropertyDetail } from "./api";

export type StageKey =
  | "takeon"
  | "compliance"
  | "marketing"
  | "offer"
  | "referencing"
  | "ta_signing"
  | "pre_movein"
  | "live"
  | "end";

export type StageMeta = {
  order: number;
  key: StageKey;
  name: string;
  /** Short text shown under the chip / heading. */
  blurb: string;
};

export const STAGES: StageMeta[] = [
  { order: 1, key: "takeon",      name: "Take-on",        blurb: "Property registered. Landlord admin form sent." },
  { order: 2, key: "compliance",  name: "Compliance",     blurb: "Landlord uploads docs. Agent edits T&C, instruction letter." },
  { order: 3, key: "marketing",   name: "Marketing",      blurb: "Photos, floor plan, portals." },
  { order: 4, key: "offer",       name: "Offer",          blurb: "Tenant offer recorded. APT / Common-Law rules applied." },
  { order: 5, key: "referencing", name: "Referencing",    blurb: "Paragon checks. Guarantor flow if needed." },
  { order: 6, key: "ta_signing",  name: "TA Signing",     blurb: "Tenancy Agreement editor + DocuSign." },
  { order: 7, key: "pre_movein",  name: "Pre Move-in",    blurb: "Inventory, keys, prescribed-document service." },
  { order: 8, key: "live",        name: "Live Tenancy",   blurb: "Rent collection, diary entries, maintenance." },
  { order: 9, key: "end",         name: "End of Tenancy", blurb: "Notice, check-out, deposit release." },
];

export function stageByOrder(order: number): StageMeta {
  return STAGES.find((s) => s.order === order) ?? STAGES[0];
}

/**
 * Derive the property's current stage from concrete fields. This is the
 * "where are we in the workflow" answer — it ignores the user's chosen view
 * (which is controlled by ?stage=N).
 *
 * Priority is most-advanced-state-first: a tenant signed TA outranks a
 * landlord still missing an EICR.
 */
export function deriveCurrentStage(property: PropertyDetail): number {
  const f = property.fields ?? {};
  const tenant = property.tenant ?? null;

  // End of tenancy — explicit notice fields would go here later
  // (Currently no field captures "notice served"; will wire when implemented.)

  // Live tenancy — TA signed by both parties
  if (f["TA_LL_Signed"] && f["TA_TT_Signed"]) {
    // If we ever set a "moved in" / "tenancy started" flag, gate Stage 8 on that.
    return 8;
  }

  // Pre move-in — tenant linked + at least one signature in flight
  if (tenant && (f["TA_LL_Signed"] || f["TA_TT_Signed"])) {
    return 7;
  }

  // TA signing — offer recorded, no signatures yet
  if (tenant && f["LL_Offer_Accepted"]) {
    return 6;
  }

  // Referencing — tenant linked but offer not yet accepted by landlord
  if (tenant) {
    return 5;
  }

  // Offer — marketing assets ready (T&C signed is the proxy until we track
  // portal launches explicitly)
  if (f["TC_Signed"]) {
    return 4;
  }

  // Marketing — all three compliance certs at least flagged
  const certsOk = ["Gas_Cert_Status", "EPC_Status", "EICR_Status"].every(
    (k) => f[k] === "On File" || f[k] === "Agency Arranging",
  );
  if (certsOk) {
    return 3;
  }

  // Compliance — landlord linked (admin form submitted) but certs not ready
  const landlordLinked = (f["Landlords"] ?? []).length > 0 || (property.landlords ?? []).length > 0;
  if (landlordLinked && (f["Gas_Cert_Status"] || f["EPC_Status"] || f["EICR_Status"])) {
    return 2;
  }

  // Take-on — default
  return 1;
}

/**
 * Resolve the stage the user wants to view, given the URL search param.
 * Clamps to [1, 9]. Defaults to the property's current stage if not set
 * or invalid.
 */
export function resolveViewStage(searchParam: string | null, current: number): number {
  if (!searchParam) return current;
  const n = parseInt(searchParam, 10);
  if (!Number.isFinite(n) || n < 1 || n > STAGES.length) return current;
  return n;
}
