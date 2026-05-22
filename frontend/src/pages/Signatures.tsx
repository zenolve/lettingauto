import { useEffect, useRef, useState } from "react";

import { api } from "../lib/api";

type Signature = {
  id: string;
  display_name: string;
  role: string;
  filename: string;
  created_at: string;
  size_bytes: number;
};

type Mode = "list" | "draw" | "upload";

export default function Signatures() {
  const [signatures, setSignatures] = useState<Signature[]>([]);
  const [mode, setMode] = useState<Mode>("list");
  const [err, setErr] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);

  async function refresh() {
    setErr(null);
    try {
      const r = await api.get<{ signatures: Signature[] }>("/api/signatures");
      setSignatures(r.data.signatures);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Failed to load signatures");
    }
  }

  useEffect(() => { refresh(); }, []);

  async function onDelete(sig: Signature) {
    if (!confirm(`Delete ${sig.display_name}'s signature? This affects every document that references this slot.`)) return;
    try {
      await api.delete(`/api/signatures/${encodeURIComponent(sig.id)}`);
      setFlash(`Deleted ${sig.display_name}.`);
      await refresh();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Delete failed");
    }
  }

  return (
    <div className="space-y-6">
      <header className="rounded-lg border border-cream-300 bg-white shadow-paper p-6 md:p-8"
        style={{ backgroundImage: "radial-gradient(600px 250px at 100% 0%, rgba(201, 162, 76, 0.07), transparent 60%)" }}>
        <div className="kicker">Document store</div>
        <h1 className="mt-1">Signatures</h1>
        <p className="mt-3 text-ink-soft max-w-2xl">
          Palace Gate signatures available to bake into documents. Each agent or director gets a registered
          signature here — when sending a document with one or more <code>/pg_sigN/</code> slots, you pick
          which person fills each slot from a dropdown on the editor.
        </p>
      </header>

      {flash && <div className="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 rounded px-3 py-2">{flash}</div>}
      {err && <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded px-3 py-2">{err}</div>}

      <div className="flex gap-2">
        <button
          className={`btn-${mode === "draw" ? "primary" : "secondary"} text-sm`}
          onClick={() => setMode(mode === "draw" ? "list" : "draw")}>
          {mode === "draw" ? "Cancel drawing" : "+ Draw new"}
        </button>
        <button
          className={`btn-${mode === "upload" ? "primary" : "secondary"} text-sm`}
          onClick={() => setMode(mode === "upload" ? "list" : "upload")}>
          {mode === "upload" ? "Cancel upload" : "+ Upload PNG"}
        </button>
      </div>

      {mode === "draw" && (
        <DrawPanel
          onCreated={() => { setMode("list"); setFlash("Signature saved."); refresh(); }}
          onError={setErr}
        />
      )}
      {mode === "upload" && (
        <UploadPanel
          onCreated={() => { setMode("list"); setFlash("Signature saved."); refresh(); }}
          onError={setErr}
        />
      )}

      <section className="card overflow-hidden">
        <header className="bg-cream-100 px-5 py-3 border-b border-cream-300">
          <h3 className="font-serif text-base font-semibold text-navy-700">Installed signatures ({signatures.length})</h3>
        </header>
        {signatures.length === 0 ? (
          <div className="p-6 text-center text-ink-muted">
            No signatures installed yet. Draw or upload one to get started.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-ink-muted text-xs uppercase tracking-kicker">
              <tr className="text-left border-b border-cream-300">
                <th className="px-5 py-3">Signatory</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-cream-300">
              {signatures.map((s) => (
                <tr key={s.id} className="hover:bg-cream-100">
                  <td className="px-5 py-3 font-medium text-ink">{s.display_name}</td>
                  <td className="px-4 py-3 text-ink-soft">{s.role || "—"}</td>
                  <td className="px-4 py-3 text-ink-muted text-xs font-mono">{s.id}</td>
                  <td className="px-4 py-3 text-ink-muted text-xs">
                    {s.size_bytes ? `${(s.size_bytes / 1024).toFixed(0)} KB` : "—"}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      className="text-xs text-rose-700 hover:underline"
                      onClick={() => onDelete(s)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Draw panel — HTML5 canvas with mouse + touch handlers, exports as PNG.
// ---------------------------------------------------------------------------
function DrawPanel({ onCreated, onError }: {
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [hasInk, setHasInk] = useState(false);
  const [busy, setBusy] = useState(false);

  // Drawing state — kept in refs so the event handlers don't re-bind every
  // render and lose continuity mid-stroke.
  const drawing = useRef(false);
  const lastPt = useRef<{ x: number; y: number } | null>(null);

  function getCtx(): CanvasRenderingContext2D | null {
    const c = canvasRef.current;
    if (!c) return null;
    const ctx = c.getContext("2d");
    if (!ctx) return null;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    ctx.strokeStyle = "#15171a";
    ctx.lineWidth = 2.5;
    return ctx;
  }

  function pointFromEvent(e: React.MouseEvent | React.TouchEvent): { x: number; y: number } {
    const c = canvasRef.current!;
    const rect = c.getBoundingClientRect();
    // The canvas's CSS size and its internal coordinate size aren't equal —
    // scale the event coords up to canvas-internal pixels so lines stay sharp.
    const scaleX = c.width / rect.width;
    const scaleY = c.height / rect.height;
    const native: any = "touches" in e ? e.touches[0] : e;
    return {
      x: (native.clientX - rect.left) * scaleX,
      y: (native.clientY - rect.top) * scaleY,
    };
  }

  function start(e: React.MouseEvent | React.TouchEvent) {
    e.preventDefault();
    drawing.current = true;
    lastPt.current = pointFromEvent(e);
  }
  function move(e: React.MouseEvent | React.TouchEvent) {
    if (!drawing.current) return;
    e.preventDefault();
    const ctx = getCtx();
    if (!ctx || !lastPt.current) return;
    const p = pointFromEvent(e);
    ctx.beginPath();
    ctx.moveTo(lastPt.current.x, lastPt.current.y);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
    lastPt.current = p;
    setHasInk(true);
  }
  function end() {
    drawing.current = false;
    lastPt.current = null;
  }

  function clear() {
    const ctx = getCtx();
    const c = canvasRef.current;
    if (ctx && c) ctx.clearRect(0, 0, c.width, c.height);
    setHasInk(false);
  }

  async function save() {
    if (!name.trim()) { onError("Please enter the signatory's name."); return; }
    if (!hasInk) { onError("Please draw a signature first."); return; }
    const c = canvasRef.current;
    if (!c) return;
    setBusy(true);
    try {
      const dataUrl = c.toDataURL("image/png");
      await api.post("/api/signatures/draw", {
        display_name: name.trim(),
        role: role.trim(),
        data_url: dataUrl,
      });
      onCreated();
    } catch (e: any) {
      onError(e?.response?.data?.detail ?? "Save failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card p-5 space-y-3">
      <h3 className="font-serif text-base font-semibold text-navy-700">Draw new signature</h3>
      <p className="text-xs text-ink-muted">
        Sign with your mouse, trackpad, or touch screen. Press &amp; hold to draw.
      </p>
      <div className="grid md:grid-cols-2 gap-3">
        <label className="block">
          <span className="label">Signatory name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lesley Smith" />
        </label>
        <label className="block">
          <span className="label">Role (optional)</span>
          <input className="input" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Director, Palace Gate Lettings" />
        </label>
      </div>
      <div className="relative">
        <canvas
          ref={canvasRef}
          width={640}
          height={200}
          className="w-full bg-white border-2 border-dashed border-cream-400 rounded-md cursor-crosshair touch-none"
          style={{ aspectRatio: "640 / 200" }}
          onMouseDown={start}
          onMouseMove={move}
          onMouseUp={end}
          onMouseLeave={end}
          onTouchStart={start}
          onTouchMove={move}
          onTouchEnd={end}
        />
        {!hasInk && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none text-ink-muted text-sm italic">
            Sign here
          </div>
        )}
      </div>
      <div className="flex gap-2 justify-end">
        <button type="button" className="btn-ghost text-sm" onClick={clear}>Clear</button>
        <button type="button" className="btn-primary text-sm" onClick={save} disabled={busy || !hasInk}>
          {busy ? "Saving…" : "Save signature"}
        </button>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------------------
// Upload panel — file picker that POSTs multipart to /api/signatures/upload.
// ---------------------------------------------------------------------------
function UploadPanel({ onCreated, onError }: {
  onCreated: () => void;
  onError: (msg: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [pickedName, setPickedName] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!name.trim()) { onError("Please enter the signatory's name."); return; }
    const file = inputRef.current?.files?.[0];
    if (!file) { onError("Please pick a PNG file."); return; }
    if (!file.name.toLowerCase().endsWith(".png")) { onError("PNG only — please convert your signature first."); return; }
    setBusy(true);
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      form.append("display_name", name.trim());
      form.append("role", role.trim());
      await api.post("/api/signatures/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      onCreated();
    } catch (e: any) {
      onError(e?.response?.data?.detail ?? "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card p-5 space-y-3">
      <h3 className="font-serif text-base font-semibold text-navy-700">Upload PNG signature</h3>
      <p className="text-xs text-ink-muted">
        Transparent background ideal. Max 1 MB. Scaled to 160×60 in documents.
      </p>
      <div className="grid md:grid-cols-2 gap-3">
        <label className="block">
          <span className="label">Signatory name</span>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Lesley Smith" />
        </label>
        <label className="block">
          <span className="label">Role (optional)</span>
          <input className="input" value={role} onChange={(e) => setRole(e.target.value)} placeholder="e.g. Director, Palace Gate Lettings" />
        </label>
      </div>
      <label
        className="block border-2 border-dashed border-cream-400 rounded-md p-4 text-center text-sm cursor-pointer hover:bg-cream-100">
        <input
          ref={inputRef}
          type="file"
          accept="image/png"
          className="hidden"
          onChange={(e) => setPickedName(e.target.files?.[0]?.name ?? null)}
        />
        {pickedName ? (
          <span className="text-ink-soft">{pickedName} <span className="text-ink-muted">— click to pick a different file</span></span>
        ) : (
          <span className="text-navy-700 font-medium">Click to choose a PNG file</span>
        )}
      </label>
      <div className="flex justify-end">
        <button type="button" className="btn-primary text-sm" onClick={save} disabled={busy || !pickedName}>
          {busy ? "Saving…" : "Save signature"}
        </button>
      </div>
    </section>
  );
}
