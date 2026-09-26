"use client";

import Link from "next/link";
import { Empty, LeadRow, PageHeader, Stat, StatusChip } from "@/components/ui";
import { api, fmtAed, fmtDate, relTime, useApi } from "@/lib/api";
import type { Dashboard, Today } from "@/lib/types";

export default function MyDayPage() {
  const { data: dash } = useApi<Dashboard>("/api/dashboard");
  const { data: today, mutate } = useApi<Today>("/api/leads/today");

  const done = async (id: string) => {
    await api(`/api/followups/${id}`, { method: "PATCH", json: { status: "done" } });
    await mutate();
  };

  return (
    <>
      <PageHeader kicker={new Date().toLocaleDateString("en-AE", { weekday: "long", day: "numeric", month: "long", timeZone: "Asia/Dubai" })} title="My day" description="What needs your attention before the phone starts ringing." />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Stat label="New this week" value={dash?.new_leads_7d ?? "—"} />
        <Stat label="Overdue follow-ups" value={dash?.overdue_followups ?? "—"} tone={dash?.overdue_followups ? "warn" : undefined} />
        <Stat label="Viewings · 7d" value={dash?.viewings_next_7d ?? "—"} />
        <Stat label="Live listings" value={dash?.live_listings ?? "—"} />
        <Stat label="Closed · 30d" value={dash?.closed_30d ?? "—"} tone="good" />
        <Stat label="Commission · 30d" value={fmtAed(dash?.commission_30d_aed)} />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section className="card p-4">
          <SectionHead title="Follow-ups due" href="/followups" count={today?.followups.length} />
          {today && today.followups.length === 0 && <Empty title="Nothing due" hint="Schedule follow-ups from a lead's page." />}
          <ul className="divide-y">
            {today?.followups.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <Link href={`/leads/${f.lead_id}`} className="truncate text-sm font-medium hover:underline">
                    {f.lead?.name ?? "Lead"}
                  </Link>
                  <div className="text-xs text-muted">
                    {f.title} · {f.channel} · <span className={f.overdue ? "text-danger" : undefined}>{relTime(f.due_at)}</span>
                  </div>
                </div>
                <button className="btn-ghost btn-sm" onClick={() => done(f.id)}>
                  Done
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="card p-4">
          <SectionHead title="Viewings today" href="/viewings" count={today?.viewings.length} />
          {today && today.viewings.length === 0 && <Empty title="No viewings scheduled" />}
          <ul className="divide-y">
            {today?.viewings.map((v) => (
              <li key={v.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <Link href={`/leads/${v.lead_id}`} className="truncate text-sm font-medium hover:underline">
                    {v.lead?.name ?? "Lead"}
                  </Link>
                  <div className="text-xs text-muted">
                    {fmtDate(v.scheduled_at, true)} · {v.location_note ?? "—"}
                  </div>
                </div>
                <StatusChip status={v.status} />
              </li>
            ))}
          </ul>
        </section>

        <section className="card p-4">
          <SectionHead title="Hot leads to work" href="/pipeline" count={today?.hot_leads.length} />
          {today && today.hot_leads.length === 0 && <Empty title="No hot leads right now" hint="Scores arrive from the AI agent as leads are qualified." />}
          <div className="-mx-3">{today?.hot_leads.map((l) => <LeadRow key={l.id} lead={l} meta={<span>{relTime(l.updated_at)}</span>} />)}</div>
        </section>

        <section className="card p-4">
          <SectionHead title="Going cold" href="/leads?stale=1" count={today?.stale_leads.length} />
          {today && today.stale_leads.length === 0 && <Empty title="Everyone has been contacted this week" />}
          <div className="-mx-3">{today?.stale_leads.map((l) => <LeadRow key={l.id} lead={l} meta={<span>last touch {relTime(l.last_contacted_at)}</span>} />)}</div>
        </section>
      </div>

      {dash && (
        <section className="card mt-4 p-4">
          <SectionHead title="Where leads came from · 30 days" />
          <div className="flex flex-wrap gap-2">
            {dash.sources_30d.map((s) => (
              <span key={s.source} className="chip bg-canvas">
                {s.source.replace(/_/g, " ")} <span className="ml-1 tabular-nums text-muted">{s.count}</span>
              </span>
            ))}
            {dash.sources_30d.length === 0 && <span className="text-sm text-muted">No leads yet.</span>}
          </div>
        </section>
      )}
    </>
  );
}

function SectionHead({ title, href, count }: { title: string; href?: string; count?: number }) {
  return (
    <div className="mb-2 flex items-center justify-between">
      <h2 className="text-sm font-semibold">
        {title} {count != null && <span className="ml-1 tabular-nums text-muted">{count}</span>}
      </h2>
      {href && (
        <Link href={href} className="text-xs text-muted hover:text-ink">
          View all
        </Link>
      )}
    </div>
  );
}
