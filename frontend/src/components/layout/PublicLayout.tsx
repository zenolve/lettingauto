import { Outlet } from "react-router-dom";

import { brand } from "../../lib/brand";

/** Shell for the public landlord/tenant form pages (token-gated URLs).
 * Editorial Mesh: warm paper, serif mark, mesh wash behind the header. The
 * inviting agency's name appears inside the form content itself. */
export function PublicLayout() {
  return (
    <div className="min-h-full bg-cream-50">
      <header className="bg-mesh-hero border-b border-cream-300">
        <div className="max-w-3xl mx-auto px-6 py-6 flex items-center gap-3">
          <div aria-hidden
            className="h-10 w-10 grid place-items-center bg-ink text-cream-50 font-serif font-semibold text-base shadow-paper"
            style={{ borderRadius: "38% 62% 55% 45% / 45% 42% 58% 55%" }}>
            LA
          </div>
          <div className="leading-tight">
            <div className="font-serif font-semibold tracking-tight text-lg text-ink">{brand.name}</div>
            <div className="text-[11px] uppercase tracking-kicker text-ink-muted mt-0.5">Secure submission portal</div>
          </div>
        </div>
      </header>
      <main className="max-w-3xl mx-auto px-6 py-10">
        <Outlet />
      </main>
      <footer className="max-w-3xl mx-auto px-6 pb-10 text-xs text-ink-muted">
        <p>This link is unique to you. Please do not share it.</p>
      </footer>
    </div>
  );
}
