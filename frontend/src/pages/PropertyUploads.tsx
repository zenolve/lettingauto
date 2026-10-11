import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { BackLink } from "../components/ui/BackLink";
import { api } from "../lib/api";

type Stored = {
  filename: string;
  size: number;
  url: string;
  uploaded_at?: string;
};

type BucketMeta = {
  name: string;
  /** Certificate buckets: the property field this file's expiry date goes in. */
  expiry_field?: string | null;
};

type ListResponse = { property_id: string; buckets: Record<string, Stored[]> };
type BucketsResponse = { buckets: BucketMeta[] };

// Friendly labels for the agent. Anything not in this map renders the raw
// bucket name (still readable — underscores get swapped for spaces).
const BUCKET_LABEL: Record<string, string> = {
  mortgage_consent:   "Mortgage consent letter",
  head_lease:         "Head lease",
  freeholder_consent: "Freeholder consent",
  insurance_cert:     "Insurance certificate",
  gas_cert:           "Gas safety certificate (CP12)",
  epc:                "EPC (Energy Performance)",
  eicr:               "EICR (Electrical)",
  id_document:        "Landlord ID document",
  visa_snapshot:      "Landlord visa / BRP",
  address_doc:        "Landlord proof of address",
  ownership_doc:      "Property ownership doc",
  incorporation_doc:  "Company — certificate of incorporation",
  bank_statements:    "Company — bank statements",
  photos:             "Marketing photos",
  floor_plan:         "Floor plan",
  tds_certificate:    "TDS deposit certificate",
  passport:           "Tenant passport",
  utility_bill:       "Tenant utility bill",
  // Executed paperwork for a tenancy imported from another system.
  signed_ta:          "Signed tenancy agreement",
  signed_tc:          "Signed terms of business",
  inventory:          "Inventory / check-in report",
  other:              "Other",
};

function prettyName(bucket: string): string {
  return BUCKET_LABEL[bucket] ?? bucket.replace(/_/g, " ");
}

function prettyFilename(stored: string): string {
  // Strip the timestamp_nonce_ prefix the backend storage layer adds.
  return decodeURIComponent(stored).replace(/^\d{14}_[a-f0-9]{8}_/, "");
}

function kb(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export default function PropertyUploads() {
  const { id: propertyId = "" } = useParams();
  const [list, setList] = useState<ListResponse | null>(null);
  const [meta, setMeta] = useState<BucketMeta[]>([]);
  const [filter, setFilter] = useState<"all" | "has_files">("has_files");
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  // e.g. "Gas Safety Certificate renewed - the tenant must be served the new copy…"
  const [notices, setNotices] = useState<string[]>([]);

  async function refresh() {
    setErr(null);
    try {
      const [a, b] = await Promise.all([
        api.get<ListResponse>(`/api/uploads/${propertyId}/list`),
        api.get<BucketsResponse>(`/api/uploads/${propertyId}/buckets`),
      ]);
      setList(a.data);
      setMeta(b.data.buckets);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Failed to load uploads");
    }
  }

  useEffect(() => {
    refresh(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [propertyId]);

  const rows = useMemo(() => {
    const buckets = list?.buckets ?? {};
    return meta
      .map((m) => ({ ...m, files: buckets[m.name] ?? [] }))
      .filter((r) => {
        if (filter === "all") return true;
        return r.files.length > 0;
      });
  }, [meta, list, filter]);

  return (
    <div className="space-y-6">
      <header className="card bg-mesh-corner p-6 md:p-8">
        <BackLink to={`/agent/properties/${propertyId}`} label="Property" />
        <div className="kicker mt-2">Document store</div>
        <h1 className="mt-1">Uploads</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          Every file the landlord (or you) has uploaded against this property, grouped by purpose. Replacing a file updates
          the property record automatically; deleting the last file in a bucket clears it.
        </p>
      </header>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-md border border-cream-300 bg-white p-0.5 text-sm">
          {(["has_files", "all"] as const).map((k) => (
            <button
              key={k}
              onClick={() => setFilter(k)}
              className={`px-3 py-1.5 rounded ${filter === k ? "bg-navy-600 text-white" : "text-ink-soft hover:bg-cream-100"}`}>
              {k === "has_files" ? "With files" : "All buckets"}
            </button>
          ))}
        </div>
        {flash && <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-3 py-1.5">{flash}</div>}
        {err && <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-1.5">{err}</div>}
      </div>

      {notices.map((n, i) => (
        <div key={i} className="text-sm text-amber-900 bg-amber-50 border border-amber-200 rounded px-3 py-2">{n}</div>
      ))}

      <div className="grid gap-4 lg:grid-cols-2">
        {rows.map((r) => (
          <BucketCard
            key={r.name}
            meta={r}
            files={r.files}
            busy={busyKey?.startsWith(r.name + "::") ? busyKey.split("::")[1] : null}
            onUpload={async (files, oldFilename, expiry) => {
              setBusyKey(`${r.name}::${oldFilename ?? "new"}`);
              setErr(null); setFlash(null); setNotices([]);
              const seen: string[] = [];
              // A replace swaps exactly one file; a new upload takes every file picked.
              // One bad file doesn't stop the rest - failures are listed after.
              const failed: string[] = [];
              for (const file of files) {
                try {
                  const form = new FormData();
                  form.append("file", file, file.name);
                  if (expiry) form.append("expiry", expiry);
                  const qs = oldFilename ? `?delete_filename=${encodeURIComponent(oldFilename)}` : "";
                  const { data } = await api.post(
                    `/api/uploads/agent/${propertyId}/${r.name}/replace${qs}`,
                    form,
                    { headers: { "Content-Type": "multipart/form-data" } },
                  );
                  for (const n of data?.notices ?? []) if (!seen.includes(n)) seen.push(n);
                } catch (e: any) {
                  failed.push(`${file.name}: ${e?.response?.data?.detail ?? "upload failed"}`);
                }
              }
              await refresh();
              const ok = files.length - failed.length;
              if (ok > 0) {
                setFlash((oldFilename
                  ? `Replaced → ${prettyName(r.name)}.`
                  : `Uploaded ${ok} file${ok === 1 ? "" : "s"} → ${prettyName(r.name)}.`)
                  + (expiry ? ` Expiry ${expiry} saved.` : ""));
              }
              setNotices(seen);
              if (failed.length > 0) setErr(`Not uploaded — ${failed.join("; ")}`);
              setBusyKey(null);
            }}
            onDelete={async (filename) => {
              if (!confirm(`Delete ${prettyFilename(filename)}? This can't be undone.`)) return;
              setBusyKey(`${r.name}::${filename}`);
              setErr(null); setFlash(null);
              try {
                await api.delete(`/api/uploads/agent/${propertyId}/${r.name}/${encodeURIComponent(filename)}`);
                await refresh();
                setFlash("Deleted.");
              } catch (e: any) {
                setErr(e?.response?.data?.detail ?? "Delete failed");
              } finally {
                setBusyKey(null);
              }
            }}
          />
        ))}
        {rows.length === 0 && (
          <div className="card p-6 text-center text-ink-muted lg:col-span-2">
            No uploads in scope. Switch filter to "All buckets" to see everything available.
          </div>
        )}
      </div>
    </div>
  );
}

function BucketCard({
  meta, files, busy, onUpload, onDelete,
}: {
  meta: BucketMeta;
  files: Stored[];
  busy: string | null;
  onUpload: (files: File[], oldFilename?: string, expiry?: string) => Promise<void>;
  onDelete: (filename: string) => Promise<void>;
}) {
  const newFileRef = useRef<HTMLInputElement | null>(null);
  const replaceRefs = useRef<Record<string, HTMLInputElement | null>>({});
  const [dragOver, setDragOver] = useState(false);
  const [expiry, setExpiry] = useState("");
  const [needDate, setNeedDate] = useState(false);
  const needsExpiry = !!meta.expiry_field;

  // A certificate and its expiry date are stored together (the renewal check
  // and the 28-day re-serve prompt key off the date), so no date, no upload.
  function upload(picked: File[], oldFilename?: string) {
    if (picked.length === 0 || busy) return;
    if (needsExpiry && !expiry) { setNeedDate(true); return; }
    setNeedDate(false);
    onUpload(picked, oldFilename, needsExpiry ? expiry : undefined);
  }

  return (
    <section
      className={`card p-5 space-y-3 transition-shadow ${dragOver ? "ring-2 ring-navy-400" : ""}`}
      onDragOver={(e) => { e.preventDefault(); if (!busy) setDragOver(true); }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        upload(Array.from(e.dataTransfer.files));
      }}>
      <header className="flex items-start justify-between gap-3">
        <div>
          <h3 className="font-serif text-base font-semibold text-navy-700 leading-tight">{prettyName(meta.name)}</h3>
          <div className="text-xs uppercase tracking-kicker text-ink-muted mt-1">{meta.name}</div>
        </div>
      </header>

      {needsExpiry && (
        <label className="block">
          <span className="text-xs text-ink-soft">Expiry date on this certificate</span>
          <input
            type="date"
            className={`input text-sm w-full mt-1 ${needDate ? "border-rose-400" : ""}`}
            value={expiry}
            onChange={(e) => { setExpiry(e.target.value); setNeedDate(false); }}
          />
          <span className={`text-[11px] ${needDate ? "text-rose-700" : "text-ink-muted"}`}>
            {needDate
              ? "Enter the expiry date shown on the certificate first — it's stored with the file so the two can't drift apart."
              : "Saved against the property with the file. If this replaces a certificate the tenant already holds, they must be served the new copy within 28 days of the inspection."}
          </span>
        </label>
      )}

      {files.length === 0 ? (
        <div className="text-sm text-ink-muted italic">No files uploaded yet.</div>
      ) : (
        <ul className="divide-y divide-cream-300 -my-2">
          {files.map((f) => (
            <li key={f.filename} className="py-2 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <a href={f.url} target="_blank" rel="noreferrer"
                  className="text-sm text-navy-600 hover:underline truncate block">
                  {prettyFilename(f.filename)}
                </a>
                <div className="text-xs text-ink-muted mt-0.5">
                  {kb(f.size)}{f.uploaded_at ? ` · ${new Date(f.uploaded_at).toLocaleDateString()}` : ""}
                </div>
              </div>
              <div className="flex gap-1 shrink-0">
                <button
                  type="button"
                  className="btn-ghost text-xs px-2 py-1"
                  disabled={busy === f.filename}
                  onClick={() => replaceRefs.current[f.filename]?.click()}>
                  {busy === f.filename ? "Working…" : "Replace"}
                </button>
                <button
                  type="button"
                  className="btn-ghost text-xs px-2 py-1 text-rose-700 hover:bg-rose-50"
                  disabled={busy === f.filename}
                  onClick={() => onDelete(f.filename)}>
                  Delete
                </button>
                <input
                  type="file"
                  ref={(el) => (replaceRefs.current[f.filename] = el)}
                  className="hidden"
                  onChange={(e) => {
                    const picked = e.target.files?.[0];
                    if (picked) upload([picked], f.filename);
                    e.target.value = "";
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        className="btn-secondary text-xs w-full"
        disabled={busy === "new"}
        onClick={() => newFileRef.current?.click()}>
        {busy === "new" ? "Uploading…" : "+ Upload files"}
      </button>
      <p className="text-[11px] text-ink-muted text-center -mt-1">Pick several at once, or drop them on this card.</p>
      <input
        type="file"
        ref={newFileRef}
        className="hidden"
        multiple
        onChange={(e) => {
          upload(Array.from(e.target.files ?? []));
          e.target.value = "";
        }}
      />
    </section>
  );
}
