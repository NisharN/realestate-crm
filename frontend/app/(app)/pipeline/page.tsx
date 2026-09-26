"use client";

import Link from "next/link";
import { PageHeader, ScoreBadge } from "@/components/ui";
import { api, fmtAed, relTime, stageLabel, useApi } from "@/lib/api";
import type { Lead, Pipeline } from "@/lib/types";

const BOARD = ["new", "qualifying", "qualified", "handed_off", "viewing_booked", "offer"];

export default function PipelinePage() {
  const { data, mutate } = useApi<Pipeline>("/api/leads/pipeline");

  const move = async (lead: Lead, stage: string) => {
    await api(`/api/leads/${lead.id}/stage`, { method: "POST", json: { stage } });
    await mutate();
  };

  const columns = data?.columns.filter((c) => BOARD.includes(c.stage)) ?? [];
  const parked = data?.columns.filter((c) => !BOARD.includes(c.stage)) ?? [];

  return (
    <>
      <PageHeader
        kicker="Pipeline"
        title={data ? `${data.total} leads` : "Pipeline"}
        description="Drag-free board: move a lead with the arrows, or open it for the full picture."
        actions={
          <Link href="/leads?new=1" className="btn-primary btn-sm">
            New lead
          </Link>
        }
      />

      <div className="-mx-4 overflow-x-auto px-4 pb-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8">
        <div className="flex min-w-max gap-3">
          {columns.map((col, i) => (
            <div key={col.stage} className="w-72 shrink-0">
              <div className="mb-2 flex items-center justify-between px-1">
                <span className="text-sm font-semibold">{stageLabel(col.stage)}</span>
                <span className="tabular-nums text-xs text-muted">{col.count}</span>
              </div>
              <div className="space-y-2">
                {col.leads.map((lead) => (
                  <article key={lead.id} className="card p-3">
                    <div className="flex items-start justify-between gap-2">
                      <Link href={`/leads/${lead.id}`} className="truncate text-sm font-medium hover:underline">
                        {lead.name || "Unnamed"}
                      </Link>
                      <ScoreBadge score={lead.ai_score} band={lead.ai_band} />
                    </div>
                    <div className="mt-1 truncate text-xs text-muted">
                      {[lead.purpose, lead.bedrooms != null ? `${lead.bedrooms}BR` : null, lead.areas[0], lead.budget_max_aed ? fmtAed(lead.budget_max_aed) : null].filter(Boolean).join(" · ") || lead.source}
                    </div>
                    <div className="mt-2 flex items-center justify-between text-[11px] text-muted">
                      <span>{lead.assigned_agent?.full_name?.split(" ")[0] ?? "Unassigned"} · {relTime(lead.stage_changed_at)}</span>
                      <span className="flex gap-1">
                        {i > 0 && (
                          <button className="rounded-md border px-1.5 hover:bg-canvas" title={`Back to ${stageLabel(BOARD[i - 1])}`} onClick={() => move(lead, BOARD[i - 1])}>
                            ←
                          </button>
                        )}
                        {i < BOARD.length - 1 && (
                          <button className="rounded-md border px-1.5 hover:bg-canvas" title={`Move to ${stageLabel(BOARD[i + 1])}`} onClick={() => move(lead, BOARD[i + 1])}>
                            →
                          </button>
                        )}
                      </span>
                    </div>
                  </article>
                ))}
                {col.leads.length === 0 && <div className="rounded-xl border border-dashed p-4 text-center text-xs text-muted">Empty</div>}
                {col.count > col.leads.length && (
                  <Link href={`/leads?stage=${col.stage}`} className="block text-center text-xs text-muted hover:text-ink">
                    +{col.count - col.leads.length} more
                  </Link>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted">
        {parked.map((c) => (
          <Link key={c.stage} href={`/leads?stage=${c.stage}`} className="chip bg-canvas hover:bg-surface">
            {stageLabel(c.stage)} <span className="ml-1 tabular-nums">{c.count}</span>
          </Link>
        ))}
      </div>
    </>
  );
}
