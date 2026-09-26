"use client";

import { clsx } from "clsx";
import { Building2, CalendarClock, Handshake, KanbanSquare, LayoutDashboard, LogOut, Menu, PhoneForwarded, Settings, Users, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { getToken, setToken, useApi } from "@/lib/api";
import type { Agency, User } from "@/lib/types";

const NAV = [
  { href: "/", label: "My day", icon: LayoutDashboard },
  { href: "/pipeline", label: "Pipeline", icon: KanbanSquare },
  { href: "/leads", label: "Leads", icon: Users },
  { href: "/followups", label: "Follow-ups", icon: PhoneForwarded },
  { href: "/viewings", label: "Viewings", icon: CalendarClock },
  { href: "/listings", label: "Listings", icon: Building2 },
  { href: "/deals", label: "Deals", icon: Handshake },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Shell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [open, setOpen] = useState(false);
  const { data: me } = useApi<{ user: User; agency: Agency | null }>(ready ? "/api/auth/me" : null);

  useEffect(() => {
    if (!getToken()) router.replace("/login");
    else setReady(true);
  }, [router]);

  useEffect(() => setOpen(false), [pathname]);

  if (!ready) return null;

  const signOut = () => {
    setToken(null);
    router.replace("/login");
  };

  const nav = (
    <nav className="flex flex-1 flex-col gap-0.5">
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
        return (
          <Link key={href} href={href} className={clsx("flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition", active ? "bg-ink text-white" : "text-ink/80 hover:bg-canvas")}>
            <Icon className="h-4 w-4" strokeWidth={1.75} />
            {label}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col border-r bg-surface p-4 lg:flex">
        <Brand agency={me?.agency ?? null} />
        {nav}
        <UserFoot user={me?.user} onSignOut={signOut} />
      </aside>

      {open && (
        <div className="fixed inset-0 z-30 flex lg:hidden">
          <aside className="flex w-64 flex-col bg-surface p-4 shadow-xl">
            <div className="flex items-center justify-between">
              <Brand agency={me?.agency ?? null} />
              <button className="btn-ghost btn-sm" onClick={() => setOpen(false)} aria-label="Close menu">
                <X className="h-4 w-4" />
              </button>
            </div>
            {nav}
            <UserFoot user={me?.user} onSignOut={signOut} />
          </aside>
          <div className="flex-1 bg-ink/30" onClick={() => setOpen(false)} />
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b bg-surface px-4 py-3 lg:hidden">
          <button className="btn-ghost btn-sm" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu className="h-4 w-4" />
          </button>
          <span className="text-sm font-semibold">{me?.agency?.name ?? "CRM"}</span>
        </header>
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}

function Brand({ agency }: { agency: Agency | null }) {
  return (
    <div className="mb-6 px-1">
      <div className="text-sm font-semibold tracking-tight">{agency?.name ?? "UAE Real Estate CRM"}</div>
      <div className="text-[11px] text-muted">{agency?.rera_orn ? `RERA ORN ${agency.rera_orn}` : "Broker workspace"}</div>
    </div>
  );
}

function UserFoot({ user, onSignOut }: { user?: User; onSignOut: () => void }) {
  return (
    <div className="mt-4 flex items-center justify-between gap-2 border-t pt-4">
      <div className="min-w-0">
        <div className="truncate text-sm font-medium">{user?.full_name ?? "…"}</div>
        <div className="truncate text-[11px] capitalize text-muted">{user?.role}</div>
      </div>
      <button className="btn-ghost btn-sm" onClick={onSignOut} title="Sign out" aria-label="Sign out">
        <LogOut className="h-4 w-4" />
      </button>
    </div>
  );
}
