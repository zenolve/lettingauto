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
      <header className="bg-cream-50 border-b border-cream-300">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 py-4">
          <Link to="/agent" className="flex items-center gap-3">
            <Logo name={agencyName} />
            <div className="leading-tight">
              <div className="font-serif text-lg font-semibold text-navy-700 tracking-tight">{agencyName}</div>
              <div className="text-xs text-ink-muted">Powered by {brand.name}</div>
            </div>
          </Link>
          <nav className="flex items-center gap-1 text-sm">
            <NavLink to="/agent" end className={tabCls}>Dashboard</NavLink>
            <NavLink to="/agent/properties" end className={tabCls}>Properties</NavLink>
            <NavLink to="/agent/library" className={tabCls}>Library</NavLink>
            <NavLink to="/agent/signatures" className={tabCls}>Signatures</NavLink>
            <NavLink to="/agent/properties/new" className={tabCls}>New property</NavLink>
            <NavLink to="/agent/settings" className={tabCls}>Settings</NavLink>
            <div className="ml-4 pl-4 border-l border-cream-400 flex items-center gap-3">
              <span className="text-ink-muted">{session?.email}</span>
              <button
                onClick={() => { signOut(); nav("/login"); }}
                className="px-3 py-1.5 rounded-md border border-cream-400 text-ink-soft hover:bg-cream-200 text-sm transition">
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
  // Active tab gets a gold underline rather than a navy chip — quieter, more
  // editorial. Inactive tabs hover to cream-200.
  return [
    "px-3 py-1.5 text-sm transition",
    isActive
      ? "text-ink font-medium border-b-2 border-gold-500"
      : "text-ink-soft hover:text-ink hover:bg-cream-200 rounded-md",
  ].join(" ");
}

function Logo({ name }: { name: string }) {
  // Outlined navy square with the agency's initials (max two letters).
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("") || "LA";
  return (
    <div className="h-10 w-10 rounded-md border-2 border-navy-700 text-navy-700 grid place-items-center font-serif text-lg font-semibold">
      {initials}
    </div>
  );
}
