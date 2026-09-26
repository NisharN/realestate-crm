"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, PageHeader, StatusChip } from "@/components/ui";
import { api, fmtAed, fmtDate, useApi } from "@/lib/api";
import type { Viewing } from "@/lib/types";

const FILTERS = [
  { key: "upcoming", label: "Upcoming" },
  { key: "requested", label: "Awaiting confirmation" },
  { key: "done", label: "Completed" },
  { key: "no_show", label: "No-shows" },
  { key: "cancelled", label: "Cancelled" },
];

export default function ViewingsPage() {
  const [filter, setFilter] = useState("upcoming");
  const query = filter === "upcoming" ? `from=${encodeURIComponent(new Date().toISOString())}` : `status=${filter}`;
  const { data, mutate } = useApi<{ items: Viewing[] }>(`/api/viewings?${query}&limit=200`);

  const patch = async (id: string, status: string) => {
    const feedback = status === "done" ? window.prompt("Client feedback (optional)") ?? undefined : undefined;
    await api(`/api/viewings/${id}`, { method: "PATCH", json: { status, feedback } });
    await mutate();
  };

  const byDay = new Map<string, Viewing[]>();
  for (const v of data?.items ?? []) {
    const day = fmtDate(v.scheduled_at);
    byDay.set(day, [...(byDay.get(day) ?? []), v]);
  }

  return (
    <>
      <PageHeader kicker="Viewings" title="Viewings" description="Confirm the day before, mark the outcome the same day — the AI agent reads these to re-score leads." />

      <div className="mb-4 flex flex-wrap gap-1.5">
        {FILTERS.map((f) => (
          <button key={f.key} className={`chip ${filter === f.key ? "bg-ink text-white border-ink" : "bg-surface hover:bg-canvas"}`} onClick={() => setFilter(f.key)}>
            {f.label}
          </button>
        ))}
      </div>

      {data && data.items.length === 0 && <Empty title="No viewings here" hint="Book one from a lead's page." />}

      <div className="space-y-4">
        {Array.from(byDay.entries()).map(([day, items]) => (
          <section key={day} className="card p-4">
            <h2 className="mb-2 text-sm font-semibold">{day}</h2>
            <ul className="divide-y">
              {items.map((v) => (
                <li key={v.id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="tabular-nums text-muted">{v.scheduled_at ? new Date(v.scheduled_at).toLocaleTimeString("en-AE", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Dubai" }) : "TBC"}</span>
                      <Link href={`/leads/${v.lead_id}`} className="truncate font-medium hover:underline">
                        {v.lead?.name ?? "Lead"}
                      </Link>
                      <StatusChip status={v.status} />
                    </div>
                    <div className="truncate text-xs text-muted">
                      {v.listing ? `${v.listing.reference} · ${v.listing.title} · ${fmtAed(v.listing.price_aed)}` : v.location_note ?? "Location TBC"}
                      {v.feedback && <span> · “{v.feedback}”</span>}
                    </div>
                  </div>
                  {["requested", "confirmed"].includes(v.status) && (
                    <div className="flex gap-1">
                      {v.status === "requested" && (
                        <button className="btn-ghost btn-sm" onClick={() => patch(v.id, "confirmed")}>
                          Confirm
                        </button>
                      )}
                      <button className="btn-ghost btn-sm" onClick={() => patch(v.id, "done")}>
                        Done
                      </button>
                      <button className="btn-ghost btn-sm" onClick={() => patch(v.id, "no_show")}>
                        No-show
                      </button>
                      <button className="btn-ghost btn-sm" onClick={() => patch(v.id, "cancelled")}>
                        Cancel
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
