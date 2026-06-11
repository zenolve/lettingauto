import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAgencyName } from "../../lib/agency";
import { signOut, useAuth } from "../../lib/auth";
import { brand } from "../../lib/brand";
import { ConfirmDialogProvider } from "../ui/ConfirmDialog";

export function AgentLayout() {
  const session = useAuth((s) => s.session);
  const agencyName = useAgencyName();
  const nav = useNavigate();

  return (
    <ConfirmDialogProvider>
    <div className="min-h-full">
      {/* Sticky paper header — hairline rule, quiet until needed. */}
      <header className="sticky top-0 z-30 bg-cream-50/90 backdrop-blur-sm border-b border-cream-300">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-3.5">
          <Link to="/agent" className="flex items-center gap-3 group">
            <Logo name={agencyName} />
            <div className="leading-tight">
              <div className="font-serif text-lg font-semibold tracking-tight text-ink group-hover:text-ink-soft transition">
                {agencyName}
              </div>
              <div className="text-[11px] uppercase tracking-kicker text-ink-muted">
                Powered by {brand.name}
              </div>
            </div>
          </Link>
          <nav aria-label="Primary" className="flex items-center gap-0.5 text-sm">
            <NavLink to="/agent" end className={tabCls}>Dashboard</NavLink>
            <NavLink to="/agent/properties" end className={tabCls}>Properties</NavLink>
            <NavLink to="/agent/library" className={tabCls}>Library</NavLink>
            <NavLink to="/agent/signatures" className={tabCls}>Signatures</NavLink>
            <NavLink to="/agent/properties/new" className={tabCls}>New property</NavLink>
            <NavLink to="/agent/settings" className={tabCls}>Settings</NavLink>
            <div className="ml-4 pl-4 border-l border-cream-300 flex items-center gap-3">
              <span className="text-ink-muted hidden md:inline" title={session?.email}>{session?.email}</span>
              <button
                onClick={() => { signOut(); nav("/login"); }}
                className="px-3.5 py-1.5 rounded-full border border-cream-400 text-ink-soft
                           hover:bg-cream-200 hover:text-ink hover:border-navy-300
                           active:scale-[0.98] text-sm transition">
                Sign out
              </button>
            </div>
          </nav>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-6 py-10">
        <Outlet />
      </main>
    </div>
    </ConfirmDialogProvider>
  );
}

function tabCls({ isActive }: { isActive: boolean }) {
  // Active tab carries the honey underline (the F hairline accent); inactive
  // tabs are quiet ink that warms on hover.
  return [
    "px-3 py-2 text-sm transition rounded-md",
    isActive
      ? "text-ink font-medium border-b-2 border-gold-500 rounded-b-none"
      : "text-ink-muted hover:text-ink hover:bg-cream-200",
  ].join(" ");
}

function Logo({ name }: { name: string }) {
  // Organic ink tile with the agency's initials (max two letters).
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("") || "LA";
  return (
    <div aria-hidden
      className="h-10 w-10 grid place-items-center bg-ink text-cream-50 font-serif text-base font-semibold shadow-paper
                 transition group-hover:shadow-lift"
      style={{ borderRadius: "38% 62% 55% 45% / 45% 42% 58% 55%" }}>
      {initials}
    </div>
  );
}
