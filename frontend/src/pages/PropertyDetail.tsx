import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BrowseLibrary } from "../components/ui/BrowseLibrary";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { FileUploader } from "../components/ui/FileUploader";
import { PropertyFlags } from "../components/ui/PropertyFlags";
import { ReferencingPanel } from "../components/ui/ReferencingPanel";
import { ReviewPanel } from "../components/ui/ReviewPanel";
import { StagePipeline } from "../components/ui/StagePipeline";
import { OffersPanel } from "../components/ui/OffersPanel";
import { TenancyChecklist } from "../components/ui/TenancyChecklist";
import { WarningsRecap } from "../components/ui/WarningsRecap";
import { api, PropertyDetail as PD } from "../lib/api";
import { deriveCurrentStage, resolveViewStage, stageByOrder } from "../lib/stages";

// Legacy quick links to the per-template editor. New "Browse document library"
// (per stage) is the primary path — these are kept as shortcuts for the
// signing-stage TA editor only.
const CONTRACT_LINKS = [
  { key: "ta",    label: "Tenancy Agreement (legacy editor)" },
];

export default function PropertyDetail() {
  const { id = "" } = useParams();
  const [search, setSearch] = useSearchParams();
  const [data, setData] = useState<PD | null>(null);
  const [err, setErr] = useState<string | null>(null);

  // PropertyFlags toggles call this to re-fetch the property record so any
  // stage-derivation that depends on the toggled field (e.g. flipping
  // funds_cleared changes the served-flags badge) updates immediately.
  const refresh = useCallback(() => {
    api.get<PD>(`/api/properties/${id}`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e.response?.data?.detail ?? "Failed to load"));
  }, [id]);

  useEffect(() => { refresh(); }, [refresh]);

  if (err) return <div className="card p-4 text-rose-700 bg-rose-50">{err}</div>;
  if (!data) return <div>Loading…</div>;

  const f = data.fields;
  const current = deriveCurrentStage(data);
  const viewing = resolveViewStage(search.get("stage"), current);
  const meta = stageByOrder(viewing);
  const onSelect = (order: number) => {
    if (order === current) {
      // Going back to "the current stage" → drop the param so the URL stays clean.
      const next = new URLSearchParams(search);
      next.delete("stage");
      setSearch(next, { replace: true });
    } else {
      setSearch({ stage: String(order) }, { replace: true });
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link to="/agent" className="text-sm text-navy-600 hover:underline">← All properties</Link>
          <h1 className="text-2xl font-bold text-navy-700 mt-1">{f["Address"]}</h1>
          <p className="text-sm text-slate-500">
            {f["post_code"] ?? f["Post Code"]} · {f["Tenancy Type"] ?? "—"} · {f["Service Level"] ?? "—"}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to={`/agent/properties/${id}/uploads`} className="btn-secondary text-sm">
            Uploads →
          </Link>
        </div>
      </div>

      <StagePipeline viewing={viewing} current={current} gateStatus={f["Gate Status"]} onSelect={onSelect} />

      <ReviewPanel propertyId={id} />

      <GateStatusBar
        propertyId={id}
        gateStatus={f["Gate Status"]}
        gateBlockReason={f["Gate Block Reason"]}
        onUpdated={refresh}
      />


      <header className="flex items-end justify-between border-b border-slate-200 pb-2">
        <div>
          <h2 className="text-lg font-semibold text-navy-700">Stage {viewing}: {meta.name}</h2>
          <p className="text-sm text-slate-500">{meta.blurb}</p>
        </div>
        {viewing > current && (
          <span className="text-xs px-2 py-1 rounded bg-amber-50 text-amber-700 border border-amber-200">
            Not reached yet
          </span>
        )}
      </header>

      <DocumentsSentOnStage propertyId={id} stage={viewing} />

      {renderStage(viewing, id, data, current, refresh)}

      <DangerZone propertyId={id} address={f["Address"]} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Danger zone — permanent cascade delete behind a danger confirmation modal.
// ---------------------------------------------------------------------------
function DangerZone({ propertyId, address }: { propertyId: string; address?: string }) {
  const confirm = useConfirm();
  const nav = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function onDelete() {
    const ok = await confirm({
      title: "Delete this property permanently?",
      tone: "danger",
      confirmLabel: "Delete everything",
      cancelLabel: "Keep property",
      body: (
        <div className="space-y-2">
          <p>
            This permanently deletes <strong>{address || "this property"}</strong> and{" "}
            <strong>everything linked to it</strong>. This cannot be undone.
          </p>
          <p className="text-sm">The following are erased:</p>
          <ul className="text-sm list-disc ml-5 space-y-0.5">
            <li>All tenants &amp; offers (including past/competing offers)</li>
            <li>Diary entries, compliance &amp; financial records</li>
            <li>Gate history, form submissions &amp; sent documents</li>
            <li>All uploaded files for this property</li>
            <li>The landlord, if this is their only property</li>
          </ul>
        </div>
      ),
    });
    if (!ok) return;
    setBusy(true);
    setErr(null);
    try {
      await api.delete(`/api/properties/${propertyId}`);
      nav("/agent/properties");
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Delete failed");
      setBusy(false);
    }
  }

  return (
    <section className="card p-5 border-rose-200 bg-rose-50/40 mt-2">
      <h3 className="font-serif text-base font-semibold text-rose-800">Danger zone</h3>
      <div className="mt-1 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-soft max-w-xl">
          Permanently delete this property and all of its tenants, offers, documents, records and
          uploaded files. This action cannot be undone.
        </p>
        <button
          type="button"
          onClick={onDelete}
          disabled={busy}
          className="shrink-0 px-4 py-2 rounded-md bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium disabled:opacity-50">
          {busy ? "Deleting…" : "Delete property"}
        </button>
      </div>
      {err && <p className="text-xs text-rose-700 mt-2">{err}</p>}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Stage routing — `current` is the property's actual derived stage, used to
// gate critical actions (you can't "Send tenant pack" until stage 7).
// `refresh` re-fetches the property record so PropertyFlags toggles + other
// in-stage mutations propagate through the rest of the UI.
// ---------------------------------------------------------------------------
function renderStage(stage: number, id: string, data: PD, current: number, refresh: () => void) {
  switch (stage) {
    case 1: return <Stage1Takeon data={data} />;
    case 2: return <Stage2Compliance id={id} data={data} refresh={refresh} />;
    case 3: return <Stage3Marketing id={id} data={data} refresh={refresh} />;
    case 4: return <Stage4Offer id={id} data={data} current={current} refresh={refresh} />;
    case 5: return <Stage5Referencing id={id} data={data} current={current} />;
    case 6: return <Stage6TASigning id={id} data={data} refresh={refresh} />;
    case 7: return <Stage7PreMovein id={id} data={data} current={current} refresh={refresh} />;
    case 8: return <Stage8Live id={id} data={data} refresh={refresh} />;
    case 9: return <Stage9End id={id} data={data} />;
    default: return null;
  }
}

// ---------------------------------------------------------------------------
// Stage views
// ---------------------------------------------------------------------------
function Stage1Takeon({ data }: { data: PD }) {
  const f = data.fields;
  const formSent = (f["Stage Name"] ?? []).some?.((n: string) => /landlord form sent/i.test(n));
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <PropertyCard f={f} />
      <LandlordCard landlords={data.landlords} />
      <NextStepCard
        title="Awaiting landlord admin"
        body={
          formSent
            ? "Admin form sent to landlord. The compliance stage opens once they submit it (plus the verification form)."
            : "Once you create the property the landlord receives the admin form by email. They fill it (with document uploads) — the system then advances to Compliance."
        }
        muted={formSent}
      />
    </div>
  );
}

function Stage2Compliance({ id, data, refresh }: { id: string; data: PD; refresh: () => void }) {
  const f = data.fields;
  // Pick the primary landlord (first linked) for the AML/NRL panel. Multi-
  // landlord properties show only the primary here; secondary landlords can
  // be edited via Airtable for now (uncommon edge case).
  const primaryLandlord = data.landlords?.[0];
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <ComplianceCard f={f} />
      <UploadsCard propertyId={id} />
      {primaryLandlord && (
        <PropertyFlags
          entityId={primaryLandlord.id}
          fields={primaryLandlord}
          show={["Verification Status", "ID_Name_Match", "NRL_Approval_Number"]}
          title={`Landlord review — ${primaryLandlord["Full Name"] ?? "unnamed"}`}
          description="AML decision + NRL approval number. Flipping ID match off 'Pending' stamps AML_Check_Date and AML_Checked_By automatically."
          catalogPath="/api/landlords/flags-catalog"
          patchPath={`/api/landlords/${primaryLandlord.id}/flags`}
          onUpdated={refresh}
        />
      )}
      <section className="card p-5">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Add a document</h3>
        <p className="text-sm text-slate-600 mb-3">
          Pick a pre-classified document from the library — T&amp;C, KYC request, legal-requirements checklist
          and pre-tenancy works sign-off all live here.
        </p>
        <BrowseLibrary propertyId={id} stage={2} />
      </section>
      <NextStepCard
        title="Move to marketing"
        body="Confirm gas / EPC / EICR are all 'On File' and T&C has been signed via DocuSeal. The gate then advances to Marketing."
      />
    </div>
  );
}

function Stage3Marketing({ id, data, refresh }: { id: string; data: PD; refresh: () => void }) {
  const f = data.fields;
  const [photoCount, setPhotoCount] = useState(0);
  const [planCount, setPlanCount] = useState(0);
  const readyToMarket = photoCount >= 1 && planCount >= 1;
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <PropertyCard f={f} compact />
      <Card title={readyToMarket ? "✅ Ready to market" : "⏳ Not yet ready to market"}>
        <p className="text-sm text-slate-600">
          {readyToMarket
            ? "At least one photo and a floor plan are on file. The portals checklist can be launched."
            : "Upload at least one photo and a floor plan to mark this property ready for portal launch."}
        </p>
        <div className="text-xs text-slate-500 mt-2">
          Photos: {photoCount} · Floor plans: {planCount}
        </div>
      </Card>
      <FileUploader
        propertyId={id}
        bucket="photos"
        label="Marketing photos"
        hint="JPG / PNG / WebP / HEIC. Min one. Drop multiple files at once."
        accept="image/*"
        onChange={(files) => setPhotoCount(files.length)}
      />
      <FileUploader
        propertyId={id}
        bucket="floor_plan"
        label="Floor plan"
        hint="PDF or image. One per property is usually enough."
        accept="application/pdf,image/*"
        onChange={(files) => setPlanCount(files.length)}
      />
      <PropertyFlags
        entityId={id}
        fields={f}
        show={["TC_Signed", "Westminster_Licence_Number"]}
        title="Stage gate + licensing"
        description="TC manual override for offline/wet-ink signing. Westminster licence number if the property falls under that council's licensing."
        onUpdated={refresh}
      />
      <Placeholder
        title="Portals checklist"
        body="Rightmove / Zoopla / LonRes / palacegate.com tick-list. Not yet implemented — see IMPLEMENTATION_STATUS.md step 31."
      />
      <NextStepCard
        title="Record the first offer"
        body="When you have a tenant offer, navigate to stage 4 (Offer) to record it."
      />
    </div>
  );
}

function Stage4Offer({ id, data, current, refresh }: { id: string; data: PD; current: number; refresh: () => void }) {
  const f = data.fields;
  const tenant = data.tenant;
  const offerLocked = current < 4;
  // HMO licence only matters when the offer flagged 3+ occupants. Show the
  // toggle then, plus anti-discrim (used by the APT stage-5 gate).
  const flagsToShow = ["Anti_Discrimination_Confirmed", ...(f["HMO_Flag"] ? ["HMO_Licence_Confirmed"] : [])];
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <PropertyCard f={f} compact />
      <LandlordCard landlords={data.landlords} compact />
      {tenant ? <TenantCard tenant={tenant} /> : (
        <NextStepCard
          title={offerLocked ? `Offer locked — property is at stage ${current}` : "Record an offer"}
          body={
            offerLocked ? (
              <span className="text-sm">
                Resolve stages 1–3 first (compliance + marketing). Once the property reaches stage 4 the form unlocks.
              </span>
            ) : (
              <Link to={`/agent/properties/${id}/offer`} className="btn-primary inline-block mt-2">
                Open offer form →
              </Link>
            )
          }
          muted={offerLocked}
        />
      )}
      <PropertyFlags
        propertyId={id}
        fields={f}
        show={flagsToShow}
        title="Stage 5 gate flags"
        description="Tick once confirmed. APT properties need anti-discrimination confirmation; HMOs need the licence on file before the offer can advance."
        onUpdated={refresh}
      />
      <OffersPanel propertyId={id} onChanged={refresh} />
      <section className="card p-5">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Send to landlord / tenant</h3>
        <p className="text-sm text-slate-600 mb-3">Offer confirmation, referencing request, and acceptance letters.</p>
        <BrowseLibrary propertyId={id} stage={4} />
      </section>
    </div>
  );
}

function Stage5Referencing({ id, data, current }: { id: string; data: PD; current: number }) {
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <ReferencingPanel propertyId={id} disabled={current < 5} />
      <section className="card p-5">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Re-serve a document</h3>
        <p className="text-sm text-slate-600 mb-3">Resend the referencing request or guarantor pack if needed.</p>
        <BrowseLibrary propertyId={id} stage={5} />
      </section>
    </div>
  );
}

function Stage6TASigning({ id, data, refresh }: { id: string; data: PD; refresh: () => void }) {
  const f = data.fields;
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <section className="card p-5">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Tenancy Agreement</h3>
        <p className="text-sm text-slate-600 mb-3">
          Two TAs in the library — pick <strong>Common Law</strong> for annual rent over £100k, otherwise
          the <strong>APT Pet/ABNB</strong> variant. Both are wired to DocuSeal by default.
        </p>
        <BrowseLibrary propertyId={id} stage={6} />
      </section>
      <Card title="Signature status">
        <KV k="Landlord signed" v={f["TA_LL_Signed"] ? "Yes" : "Awaiting"} />
        <KV k="Tenant signed" v={f["TA_TT_Signed"] ? "Yes" : "Awaiting"} />
        <KV k="TDS cert on file" v={f["TDS Cert On File"] ? "Yes" : "Not yet"} />
        <KV k="Deposit registered" v={f["Deposit Registered"] ? "Yes" : "Not yet"} />
        <div className="text-xs text-slate-500 mt-3">
          Legacy TA editor: {" "}
          <Link to={`/agent/properties/${id}/contracts/ta`} className="text-navy-600 hover:underline">open →</Link>
        </div>
      </Card>
      <PropertyFlags
        propertyId={id}
        fields={f}
        show={["TDS Cert On File", "Deposit Registered"]}
        title="Deposit & TDS"
        description="Both required before the property can advance to Stage 7 (Pre Move-in). Ticking 'Deposit Registered' auto-stamps today's date — required by the Housing Act 2004 30-day rule."
        onUpdated={refresh}
      />
      <PropertyFlags
        propertyId={id}
        fields={f}
        show={["TA_LL_Signed", "TA_TT_Signed"]}
        title="TA signing — manual override"
        description="DocuSign normally flips these. Use only for wet-ink signing, webhook failures, retroactive migration, or amendments. Each toggle requires confirmation."
        onUpdated={refresh}
      />
    </div>
  );
}

function Stage7PreMovein({ id, data, current, refresh }: { id: string; data: PD; current: number; refresh: () => void }) {
  const f = data.fields;
  const locked = current < 7;
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <Card title="Prescribed documents served">
        <KV k="How to Rent" v={bool(f["How_To_Rent_Served"])} />
        <KV k="Gas cert" v={bool(f["Gas_Cert_Served"])} />
        <KV k="EPC" v={bool(f["EPC_Served"])} />
        <KV k="EICR" v={bool(f["EICR_Served"])} />
        <KV k="TDS info" v={bool(f["TDS_Info_Served"])} />
        <KV k="RRA sheet (APT)" v={bool(f["RRA_Sheet_Served"])} />
      </Card>
      <Card title="Move-in actions">
        {locked ? (
          <>
            <button
              disabled
              title={`Property is at stage ${current}. Send tenant pack unlocks once the property reaches stage 7 (TA signed).`}
              className="btn-primary opacity-50 cursor-not-allowed inline-block">
              Send tenant pack →
            </button>
            <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded p-2 mt-3">
              Locked — property is at stage {current}. The TA must be signed by both parties (stage 7) before
              the tenant pack can be served.
            </p>
          </>
        ) : (
          <>
            <Link to={`/agent/properties/${id}/move-in`} className="btn-primary inline-block">
              Send tenant pack →
            </Link>
            <p className="text-xs text-slate-500 mt-3">
              Once funds clear and all prescribed documents are served, the gate advances to Live Tenancy.
            </p>
          </>
        )}
      </Card>
      <div className="md:col-span-2">
        <PropertyFlags
          propertyId={id}
          fields={f}
          show={["funds_cleared", "Works_Signed_Off", "Inventory_Clerk"]}
          title="Pre-move-in checks"
          description="Tick once each is in place — these are gate conditions for advancing into Stage 8 (Live Tenancy)."
          onUpdated={refresh}
        />
      </div>
      <section className="card p-5 md:col-span-2">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Move-in correspondence</h3>
        <p className="text-sm text-slate-600 mb-3">Welcome letter, check-in confirmation, bank/standing-order, utility transfer.</p>
        <BrowseLibrary propertyId={id} stage={7} />
      </section>

      <div className="md:col-span-2">
        <TenancyChecklist propertyId={id} />
      </div>
      <div className="md:col-span-2">
        <WarningsRecap propertyId={id} />
      </div>
    </div>
  );
}

function Stage8Live({ id, data, refresh }: { id: string; data: PD; refresh: () => void }) {
  const f = data.fields;
  const isApt = f["Tenancy Type"] === "APT";
  // Per-doc served flags: usually set automatically by the tenant-pack
  // handler, but exposed here for manual override (e.g. document served
  // outside the system, or the system missed an event).
  const servedFlags = [
    "How_To_Rent_Served",
    "Gas_Cert_Served",
    "EPC_Served",
    "EICR_Served",
    "TDS_Info_Served",
    ...(isApt ? ["RRA_Sheet_Served"] : []),
  ];
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <Card title="Tenancy">
        {data.tenant ? (
          <>
            <KV k="Start date" v={data.tenant["Start Date"]} />
            <KV k="End date" v={data.tenant["End Date"] ?? "Periodic"} />
            <KV k="Monthly rent" v={data.tenant["Amount"] && `£${data.tenant["Amount"]}`} />
            <KV k="Tenancy type" v={data.fields["Tenancy Type"]} />
          </>
        ) : <span className="text-sm text-slate-500">No tenant linked.</span>}
      </Card>
      <DiaryCard propertyId={id} />
      <div className="md:col-span-2">
        <PropertyFlags
          propertyId={id}
          fields={f}
          show={servedFlags}
          title="Prescribed documents served"
          description="The tenant-pack flow auto-ticks these. Override here if a document was served outside the system or to correct a missed event."
          onUpdated={refresh}
        />
      </div>
      <section className="card p-5 md:col-span-2">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Send during the tenancy</h3>
        <p className="text-sm text-slate-600 mb-3">
          Rent reminders, arrears notices, maintenance acknowledgements, contractor instructions,
          inspection reports, periodic check-ins and market updates.
        </p>
        <BrowseLibrary propertyId={id} stage={8} />
      </section>
    </div>
  );
}

function Stage9End({ id }: { id: string; data: PD }) {
  return (
    <div className="grid md:grid-cols-2 gap-6">
      <section className="card p-5 md:col-span-2">
        <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">End-of-tenancy correspondence</h3>
        <p className="text-sm text-slate-600 mb-3">
          Renewal prompts, notices to quit (APT / Section 8 / Common Law), check-out cover letters,
          deposit release / dispute and farewell.
        </p>
        <BrowseLibrary propertyId={id} stage={9} />
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Documents sent at this stage — appears above the stage view, lists every
// library doc the agent has already sent for this property+stage.
// ---------------------------------------------------------------------------
type SentDoc = {
  submission_id: string;
  doc_id: string;
  doc_name: string;
  stage: number | null;
  mode: "sign" | "email_pdf" | "email_html" | "attachment" | null;
  title?: string;
  recipients: string[];
  pdf_url?: string;
  submitted_date?: string;
  status?: string;
  completed_date?: string;
};

function SentStatusBadge({ status }: { status?: string }) {
  if (!status || status === "Sent") return null;
  const cls = status === "Signed" ? "bg-emerald-50 text-emerald-700 border-emerald-200"
    : status === "Declined" || status === "Voided" ? "bg-rose-50 text-rose-700 border-rose-200"
    : "bg-cream-100 text-ink-soft border-cream-300";
  return <span className={`text-[10px] px-1.5 py-0.5 rounded-full border ${cls} shrink-0`}>{status}</span>;
}

// ---------------------------------------------------------------------------
// Gate status bar — shows the current Gate Block Reason when present, plus a
// "Re-evaluate" button that re-runs the gate logic against current field
// values. Use case: agent fixed an expired cert in Airtable; without this
// the cached Gate Status / Gate Block Reason stay stale forever.
// ---------------------------------------------------------------------------
function GateStatusBar({ propertyId, gateStatus, gateBlockReason, onUpdated }: {
  propertyId: string;
  gateStatus?: string;
  gateBlockReason?: string;
  onUpdated: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const blocked = gateStatus === "Blocked" && !!gateBlockReason;

  async function reevaluate() {
    setBusy(true); setErr(null); setFlash(null);
    try {
      const { data } = await api.post(`/api/properties/${propertyId}/reevaluate-gate`);
      if (data.no_op) {
        setFlash(data.message ?? "Property is at the final tracked stage.");
      } else if (data.advanced) {
        setFlash(`Gate cleared — advanced to Stage ${data.target_stage}.`);
      } else if (data.failures?.length) {
        setFlash(`Still blocked (${data.failures.length} condition${data.failures.length === 1 ? "" : "s"} unmet).`);
      } else {
        setFlash("No change.");
      }
      onUpdated();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Re-evaluation failed");
    } finally {
      setBusy(false);
    }
  }

  // When not blocked and there's nothing to flash, render nothing — keep the
  // page quiet on the happy path.
  if (!blocked && !flash && !err) return null;

  return (
    <div className="space-y-2">
      {blocked && (
        <div className="card p-4 bg-rose-50 border-rose-200 text-rose-800 flex items-start justify-between gap-3">
          <div>
            <strong>Blocked:</strong> {gateBlockReason}
          </div>
          <button
            type="button"
            className="text-xs px-3 py-1.5 rounded border border-rose-300 bg-white text-rose-800 hover:bg-rose-100 disabled:opacity-50 shrink-0"
            onClick={reevaluate}
            disabled={busy}>
            {busy ? "Re-checking…" : "Re-evaluate gate"}
          </button>
        </div>
      )}
      {!blocked && (
        <div className="flex justify-end">
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={reevaluate}
            disabled={busy}>
            {busy ? "Re-checking…" : "Re-evaluate gate"}
          </button>
        </div>
      )}
      {flash && (
        <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-3 py-1.5">
          {flash}
        </div>
      )}
      {err && (
        <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-1.5">
          {err}
        </div>
      )}
    </div>
  );
}


function DocumentsSentOnStage({ propertyId, stage }: { propertyId: string; stage: number }) {
  const [rows, setRows] = useState<SentDoc[]>([]);
  useEffect(() => {
    api.get<{ sent: SentDoc[] }>(`/api/library/property/${propertyId}/sent`)
      .then((r) => setRows(r.data.sent))
      .catch(() => setRows([]));
  }, [propertyId, stage]);
  const onStage = rows.filter((r) => r.stage === stage);
  if (onStage.length === 0) return null;
  return (
    <section className="card p-4 bg-slate-50/60">
      <h3 className="text-xs uppercase tracking-wide text-slate-500 mb-2">Documents sent at this stage</h3>
      <ul className="space-y-1 text-sm">
        {onStage.map((r) => (
          <li key={r.submission_id} className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium text-slate-800 truncate">{r.doc_name}</span>
                <SentStatusBadge status={r.status} />
              </div>
              <div className="text-xs text-slate-500 truncate">
                {r.submitted_date} · {modeLabel(r.mode)}
                {r.recipients.length > 0 && <> · to {r.recipients.join(", ")}</>}
              </div>
            </div>
            {r.pdf_url ? (
              <a href={r.pdf_url} target="_blank" rel="noreferrer" className="btn-ghost text-navy-700 text-sm">View PDF →</a>
            ) : (
              <span className="text-xs text-slate-400">No PDF</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function modeLabel(m: SentDoc["mode"]): string {
  if (m === "sign") return "Sent for signing";
  if (m === "email_pdf") return "Emailed as PDF";
  if (m === "email_html") return "Emailed as HTML";
  if (m === "attachment") return "Attached to email";
  return "Sent";
}

// ---------------------------------------------------------------------------
// Diary card — Stage 8 live list of upcoming + fired alerts.
// ---------------------------------------------------------------------------
type DiaryEntry = {
  id: string;
  type: string | null;
  alert_date: string | null;
  message: string | null;
  assigned_to: string | null;
  fired: boolean;
};

function DiaryCard({ propertyId }: { propertyId: string }) {
  const [entries, setEntries] = useState<DiaryEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    api.get<{ entries: DiaryEntry[] }>(`/api/properties/${propertyId}/diary`)
      .then((r) => setEntries(r.data.entries))
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load"));
  }, [propertyId]);

  if (err) return <Card title="Diary"><span className="text-sm text-rose-600">{err}</span></Card>;
  if (!entries) return <Card title="Diary"><span className="text-sm text-slate-500">Loading…</span></Card>;
  if (entries.length === 0) {
    return <Card title="Diary">
      <p className="text-sm text-slate-500">
        No diary entries yet. Entries are auto-created on TA-signed (rent review S13, cert renewals,
        tenancy expiry warning) and when an overseas landlord submits PG_02.
      </p>
    </Card>;
  }

  const today = new Date().toISOString().slice(0, 10);
  return (
    <section className="card p-5">
      <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">Diary ({entries.length})</h3>
      <ul className="space-y-2 text-sm">
        {entries.map((d) => {
          const overdue = d.alert_date && d.alert_date < today && !d.fired;
          const due = d.alert_date && d.alert_date <= today && !d.fired;
          return (
            <li key={d.id} className={`p-2 rounded-md border ${
              d.fired ? "bg-slate-50 text-slate-500 border-slate-200" :
              overdue ? "bg-rose-50 border-rose-200" :
              due ? "bg-amber-50 border-amber-200" : "border-slate-200"
            }`}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium">{d.type ?? "Diary entry"}</span>
                <span className="text-xs">{d.alert_date ?? "—"}</span>
              </div>
              {d.message && <div className="text-xs text-slate-600 mt-0.5">{d.message}</div>}
              {d.assigned_to && <div className="text-xs text-slate-400 mt-0.5">Assigned: {d.assigned_to}</div>}
              {d.fired && <div className="text-xs text-slate-400 mt-0.5">Fired</div>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Reusable cards
// ---------------------------------------------------------------------------
function PropertyCard({ f, compact = false }: { f: Record<string, any>; compact?: boolean }) {
  return (
    <Card title="Property">
      <KV k="Address" v={f["Address"]} />
      <KV k="Postcode" v={f["post_code"] ?? f["Post Code"]} />
      <KV k="Tenancy type" v={f["Tenancy Type"]} />
      <KV k="Service level" v={f["Service Level"]} />
      {!compact && (
        <>
          <KV k="EPC rating" v={f["EPC Rating "] ?? f["EPC Rating"]} />
          <KV k="Gas cert" v={f["Gas_Cert_Status"]} />
          <KV k="EPC" v={f["EPC_Status"]} />
          <KV k="EICR" v={f["EICR_Status"]} />
        </>
      )}
    </Card>
  );
}

function LandlordCard({ landlords, compact = false }: { landlords: Array<Record<string, any>>; compact?: boolean }) {
  return (
    <Card title="Landlord">
      {landlords.length === 0 && <p className="text-sm text-slate-500">No landlord linked.</p>}
      {landlords.map((ll) => (
        <div key={ll.id} className="space-y-1">
          <KV k="Name" v={ll["Full Name"]} />
          <KV k="Email" v={ll["Email Address"]} />
          {!compact && <KV k="Mobile" v={ll["Mobile Number"]} />}
          <KV k="Verification" v={ll["Verification Status"]} />
          {!compact && <KV k="T&C signed" v={ll["TC_Signed"] ? "Yes" : "No"} />}
        </div>
      ))}
    </Card>
  );
}

function TenantCard({ tenant }: { tenant: Record<string, any> }) {
  return (
    <Card title="Tenant">
      <KV k="Name" v={tenant["Name"]} />
      <KV k="Email" v={tenant["Tenant Email"]} />
      <KV k="Start date" v={tenant["Start Date"]} />
      <KV k="End date" v={tenant["End Date"] ?? "Periodic"} />
      <KV k="Monthly rent" v={tenant["Amount"] && `£${tenant["Amount"]}`} />
      <KV k="Deposit" v={tenant["Deposit Amount"] && `£${tenant["Deposit Amount"]}`} />
    </Card>
  );
}

function ComplianceCard({ f }: { f: Record<string, any> }) {
  return (
    <Card title="Compliance status">
      <KV k="Gas cert" v={f["Gas_Cert_Status"]} />
      <KV k="EPC" v={f["EPC_Status"]} />
      <KV k="EPC rating" v={f["EPC Rating "] ?? f["EPC Rating"]} />
      <KV k="EICR" v={f["EICR_Status"]} />
      <KV k="Smoke detectors" v={bool(f["smoke_detectors_fitted"])} />
      <KV k="T&C signed" v={bool(f["TC_Signed"])} />
    </Card>
  );
}

function UploadsCard({ propertyId }: { propertyId: string }) {
  const [buckets, setBuckets] = useState<Record<string, any[]> | null>(null);
  useEffect(() => {
    api.get<{ buckets: Record<string, any[]> }>(`/api/uploads/${propertyId}/list`)
      .then((r) => setBuckets(r.data.buckets))
      .catch(() => setBuckets({}));
  }, [propertyId]);
  if (!buckets) return <Card title="Uploaded documents"><span className="text-sm text-slate-500">Loading…</span></Card>;
  const entries = Object.entries(buckets);
  return (
    <Card title="Uploaded documents">
      {entries.length === 0 ? (
        <p className="text-sm text-slate-500">No documents uploaded yet.</p>
      ) : (
        <ul className="space-y-1 text-sm">
          {entries.map(([bucket, files]) => (
            <li key={bucket}>
              <span className="text-slate-500">{bucket.replace(/_/g, " ")}:</span>{" "}
              {files.map((file: any, i: number) => (
                <span key={file.filename}>
                  <a href={file.url} target="_blank" rel="noreferrer" className="text-navy-600 hover:underline">
                    {file.filename.replace(/^\d{14}_[a-f0-9]{8}_/, "")}
                  </a>
                  {i < files.length - 1 && ", "}
                </span>
              ))}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function NextStepCard({ title, body, muted }: { title: string; body: React.ReactNode; muted?: boolean }) {
  return (
    <section className={`card p-5 ${muted ? "bg-slate-50" : "bg-amber-50 border-amber-200"}`}>
      <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-2">Next step</h3>
      <p className={`font-medium ${muted ? "text-slate-700" : "text-amber-900"}`}>{title}</p>
      <div className={`text-sm mt-1 ${muted ? "text-slate-600" : "text-amber-800"}`}>{body}</div>
    </section>
  );
}

function Placeholder({ title, body }: { title: string; body: string }) {
  return (
    <section className="card p-5 border-dashed">
      <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-1">{title}</h3>
      <p className="text-sm text-slate-600">{body}</p>
    </section>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="card p-5">
      <h3 className="text-sm uppercase tracking-wide text-slate-500 mb-3">{title}</h3>
      <div className="space-y-1.5 text-sm">{children}</div>
    </section>
  );
}

function KV({ k, v }: { k: string; v: any }) {
  return (
    <div className="flex justify-between gap-3 border-b last:border-0 border-slate-100 py-1">
      <span className="text-slate-500">{k}</span>
      <span className="text-slate-900 text-right">{v ?? "—"}</span>
    </div>
  );
}

function bool(v: any): string {
  if (v === true) return "Yes";
  if (v === false || v === undefined || v === null) return "No";
  return String(v);
}
