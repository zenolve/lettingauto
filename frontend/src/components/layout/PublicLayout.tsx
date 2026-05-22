import { Outlet } from "react-router-dom";

import { brand } from "../../lib/brand";

export function PublicLayout() {
  return (
    <div className="min-h-full bg-cream-50">
      <header className="bg-navy-700 text-white border-b-2 border-gold-500">
        <div className="max-w-3xl mx-auto px-6 py-5 flex items-center gap-3">
          <div className="h-10 w-10 rounded-md bg-white text-navy-700 grid place-items-center font-serif font-bold text-base shadow-sm">PG</div>
          <div className="leading-tight">
            <div className="font-serif font-semibold tracking-wide text-lg">{brand.name}</div>
            <div className="text-xs uppercase tracking-kicker text-cream-200 mt-0.5">Secure submission portal</div>
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
