import { useRef, useState } from "react";

import { publicApi } from "../../lib/api";

type Props = {
  /** Form token from the URL — authorises the upload for this property only. */
  token: string;
  /** Property record id (recXXX) extracted from the form-token payload. */
  propertyId: string;
  /** Upload bucket — must be on the backend allowlist (mortgage_consent, head_lease, …). */
  bucket: string;
  /** Visible label shown above the dropzone. */
  label: string;
  hint?: string;
  accept?: string;
  /** Called with the absolute URL of the stored file (or undefined to clear). */
  onChange: (url: string | undefined) => void;
  /** Current value — if present, shown as a "✓ filename" badge instead of the dropzone. */
  value?: string;
};

/**
 * Form-token-authorised file upload used by the public landlord pages
 * (admin / verification). Calls
 *   POST /api/uploads/{propertyId}/{bucket}?token={token}
 * and bubbles the returned absolute URL back to the parent form via onChange.
 * The same URL is what the form payload eventually submits — and what
 * Airtable's URL-type fields store.
 */
export function PublicUpload({ token, propertyId, bucket, label, hint, accept, onChange, value }: Props) {
  const [uploading, setUploading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  async function upload(picked: FileList | null) {
    if (!picked || picked.length === 0) return;
    setUploading(true); setErr(null);
    const form = new FormData();
    form.append("file", picked[0], picked[0].name);
    try {
      const r = await publicApi.post(
        `/api/uploads/${propertyId}/${bucket}?token=${encodeURIComponent(token)}`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      onChange(r.data.url as string);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="space-y-1">
      <label className="block text-sm font-medium text-slate-700">{label}</label>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
      {value ? (
        <div className="flex items-center justify-between gap-2 border border-emerald-200 bg-emerald-50 rounded-md px-3 py-2">
          <span className="text-sm text-emerald-800 truncate">
            <a href={value} target="_blank" rel="noreferrer" className="hover:underline">
              {decodeURIComponent(value.split("/").pop() ?? "uploaded file").replace(/^\d{14}_[a-f0-9]{8}_/, "")}
            </a>
          </span>
          <button
            type="button"
            className="text-xs text-emerald-700 hover:text-emerald-900"
            onClick={() => onChange(undefined)}>
            Replace
          </button>
        </div>
      ) : (
        <label className={`block border-2 border-dashed rounded-md p-3 text-center text-sm cursor-pointer transition-colors ${
          uploading ? "border-navy-300 bg-navy-50 text-navy-600" : "border-slate-300 hover:border-navy-400 hover:bg-slate-50 text-slate-600"
        }`}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); upload(e.dataTransfer.files); }}>
          {uploading ? "Uploading…" : (
            <>
              <span className="text-navy-700 font-medium">Click or drag a file</span>
              <div className="text-xs text-slate-400">{accept ?? "PDF / JPG / PNG"}</div>
            </>
          )}
          <input ref={inputRef} type="file" className="hidden" accept={accept}
                 onChange={(e) => upload(e.target.files)} />
        </label>
      )}
      {err && <p className="text-xs text-rose-600">{err}</p>}
    </div>
  );
}
