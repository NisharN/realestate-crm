"use client";

import { Mail, MessageCircle, Mic, Phone, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Empty, PageHeader, StatusChip } from "@/components/ui";
import { api, fmtDate, relTime, useApi } from "@/lib/api";
import type { Followup } from "@/lib/types";

const ICON: Record<string, typeof Phone> = { call: Phone, whatsapp: MessageCircle, email: Mail, voice_note: Mic, meeting: Users };

export default function FollowupsPage() {
  const [status, setStatus] = useState<"open" | "done" | "skipped">("open");
  const { data, mutate } = useApi<{ items: Followup[] }>(`/api/followups?status=${status}&limit=300`);

  const patch = async (id: string, s: string) => {
    await api(`/api/followups/${id}`, { method: "PATCH", json: { status: s } });
    await mutate();
  };

  const items = data?.items ?? [];
  const overdue = items.filter((f) => f.overdue);
  const upcoming = items.filter((f) => !f.overdue);

  return (
    <>
      <PageHeader
        kicker="Follow-ups"
        title={status === "open" ? `${items.length} open` : status === "done" ? "Completed" : "Skipped"}
        description="Marking one done stamps the lead as contacted, so it drops off your 'going cold' list."
        actions={
          <div className="flex rounded-xl border p-0.5 text-xs">
            {(["open", "done", "skipped"] as const).map((s) => (
              <button key={s} className={`rounded-lg px-3 py-1.5 capitalize ${status === s ? "bg-ink text-white" : ""}`} onClick={() => setStatus(s)}>
                {s}
              </button>
            ))}
          </div>
        }
      />

      {data && items.length === 0 && <Empty title="Nothing here" hint="Schedule follow-ups from a lead's page." />}

      {status === "open" ? (
        <>
          {overdue.length > 0 && <Group title="Overdue" tone="text-danger" items={overdue} onPatch={patch} />}
          {upcoming.length > 0 && <Group title="Coming up" items={upcoming} onPatch={patch} />}
        </>
      ) : (
        items.length > 0 && <Group title={status === "done" ? "Done" : "Skipped"} items={items} />
      )}
    </>
  );
}

function Group({ title, tone, items, onPatch }: { title: string; tone?: string; items: Followup[]; onPatch?: (id: string, s: string) => void }) {
  return (
    <section className="card mb-4 p-4">
      <h2 className={`mb-2 text-sm font-semibold ${tone ?? ""}`}>
        {title} <span className="ml-1 tabular-nums text-muted">{items.length}</span>
      </h2>
      <ul className="divide-y">
        {items.map((f) => {
          const Icon = ICON[f.channel] ?? Phone;
          return (
            <li key={f.id} className="flex items-center justify-between gap-3 py-2.5">
              <div className="flex min-w-0 items-center gap-3">
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-canvas">
                  <Icon className="h-4 w-4" strokeWidth={1.75} />
                </span>
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-sm">
                    <Link href={`/leads/${f.lead_id}`} className="truncate font-medium hover:underline">
                      {f.lead?.name ?? "Lead"}
                    </Link>
                    <span className="truncate text-muted">{f.title}</span>
                  </div>
                  <div className="text-xs text-muted">
                    <span className={f.overdue ? "text-danger" : undefined}>{fmtDate(f.due_at, true)}</span> · {relTime(f.due_at)}
                    {f.note && <span> · {f.note}</span>}
                  </div>
                </div>
              </div>
              {onPatch ? (
                <div className="flex gap-1">
                  <button className="btn-ghost btn-sm" onClick={() => onPatch(f.id, "done")}>
                    Done
                  </button>
                  <button className="btn-ghost btn-sm" onClick={() => onPatch(f.id, "skipped")}>
                    Skip
                  </button>
                </div>
              ) : (
                <StatusChip status={f.status} />
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
