import { useEffect, useRef, useState } from "react";

import { api } from "../../lib/api";

type UploadedFile = { filename: string; size: number; url: string };

// Buckets whose file is only meaningful alongside its expiry date. Capturing
// the date with the upload is what stops the stored certificate and the
// property's expiry field drifting apart — and it's the moment the sitting
// tenant's copy becomes superseded, so it drives the re-serve prompt.
// Mirrors BUCKET_EXPIRY_FIELD in backend/app/services/cert_renewal.py.
const CERT_EXPIRY_LABEL: Record<string, string> = {
  gas_cert: "Expiry date on this gas safety certificate",
  eicr: "Expiry date on this EICR",
};

type Props = {
  /** Property id (recXXX). */
  propertyId: string;
  /** Upload bucket (`photos`, `floor_plan`, `id_document`, …). */
  bucket: string;
  /** Visible label shown above the dropzone. */
  label: string;
  /** Optional short hint shown under the label. */
  hint?: string;
  /** Allowed mime types passed to <input accept=…>. */
  accept?: string;
  /** Allow uploading multiple files in one drop. */
  multiple?: boolean;
  /** Callback when the list of stored files changes. */
  onChange?: (files: UploadedFile[]) => void;
};

/**
 * Agent-only uploader. Calls POST /api/uploads/agent/{property}/{bucket} for
 * each picked file, then refreshes the list via GET /api/uploads/{property}/list.
 * Public landlord forms should use the form-token variant elsewhere.
 */
export function FileUploader({ propertyId, bucket, label, hint, accept, multiple = true, onChange }: Props) {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [expiry, setExpiry] = useState("");
  const [notices, setNotices] = useState<string[]>([]);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const expiryLabel = CERT_EXPIRY_LABEL[bucket];

  async function refresh() {
    try {
      const r = await api.get<{ buckets: Record<string, UploadedFile[]> }>(
        `/api/uploads/${propertyId}/list`,
      );
      const next = r.data.buckets[bucket] ?? [];
      setFiles(next);
      onChange?.(next);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Failed to load uploads");
    }
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [propertyId, bucket]);

  async function uploadFiles(picked: FileList | null) {
    if (!picked || picked.length === 0) return;
    if (expiryLabel && !expiry) {
      setErr("Enter the expiry date shown on the certificate first — it's stored with the file so the two can't drift apart.");
      if (fileInput.current) fileInput.current.value = "";
      return;
    }
    setUploading(true); setErr(null); setNotices([]);
    try {
      const seen: string[] = [];
      for (const f of Array.from(picked)) {
        const form = new FormData();
        form.append("file", f, f.name);
        if (expiryLabel && expiry) form.append("expiry", expiry);
        const { data } = await api.post(`/api/uploads/agent/${propertyId}/${bucket}`, form, {
          headers: { "Content-Type": "multipart/form-data" },
        });
        // e.g. "Gas Safety Certificate renewed - serve the new copy…"
        for (const n of data?.notices ?? []) if (!seen.includes(n)) seen.push(n);
      }
      setNotices(seen);
      await refresh();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Upload failed");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  return (
    <section className="card p-4">
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="text-sm font-semibold text-slate-700">{label}</h3>
        <span className="text-xs text-slate-400">{files.length} file{files.length === 1 ? "" : "s"}</span>
      </div>
      {hint && <p className="text-xs text-slate-500 mb-3">{hint}</p>}

      {expiryLabel && (
        <label className="block mb-3">
          <span className="text-xs text-ink-soft">{expiryLabel}</span>
          <input
            type="date"
            className="input text-sm w-full mt-1"
            value={expiry}
            onChange={(e) => { setExpiry(e.target.value); setErr(null); }}
          />
          <span className="text-[11px] text-ink-muted">
            Saved against the property with the file. If this replaces a certificate the tenant
            already holds, they must be served the new copy within 28 days of the inspection.
          </span>
        </label>
      )}

      {notices.map((n, i) => (
        <div key={i} className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-2.5 py-1.5 mb-3">
          {n}
        </div>
      ))}

      <label
        className={`block border-2 border-dashed rounded-md p-4 text-center text-sm cursor-pointer transition-colors ${
          uploading ? "border-navy-300 bg-navy-50 text-navy-600" : "border-slate-300 hover:border-navy-400 hover:bg-slate-50 text-slate-600"
        }`}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => { e.preventDefault(); uploadFiles(e.dataTransfer.files); }}>
        {uploading ? "Uploading…" : (
          <>
            <strong className="text-navy-700">Click to choose</strong> or drag files here
            <div className="text-xs text-slate-400 mt-1">{accept ? `Accepted: ${accept}` : "Max 25 MB per file"}</div>
          </>
        )}
        <input
          ref={fileInput}
          type="file"
          className="hidden"
          accept={accept}
          multiple={multiple}
          onChange={(e) => uploadFiles(e.target.files)}
        />
      </label>

      {err && <p className="text-xs text-rose-600 mt-2">{err}</p>}

      {files.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {files.map((f) => (
            <li key={f.filename} className="flex justify-between gap-3 border-b last:border-0 border-slate-100 py-1">
              <a href={f.url} target="_blank" rel="noreferrer" className="text-navy-600 hover:underline truncate">
                {/* Strip the timestamp_nonce_ prefix added by the backend storage layer */}
                {f.filename.replace(/^\d{14}_[a-f0-9]{8}_/, "")}
              </a>
              <span className="text-xs text-slate-400 shrink-0">{(f.size / 1024).toFixed(0)} KB</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
