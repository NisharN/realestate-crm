"use client";

import Link from "next/link";
import { useState } from "react";
import { Empty, PageHeader, Stat, StatusChip } from "@/components/ui";
import { api, fmtAed, relTime, stageLabel, useApi } from "@/lib/api";
import type { Deal } from "@/lib/types";

const FLOW = ["offer", "mou", "deposit", "transfer", "closed"];

export default function DealsPage() {
  const [filter, setFilter] = useState("");
  const { data, mutate } = useApi<{ items: Deal[] }>(`/api/deals?limit=300${filter ? `&status=${filter}` : ""}`);
  const items = data?.items ?? [];

  const advance = async (d: Deal, s: string) => {
    let agreed: number | null = null;
    if (s === "mou" && !d.agreed_aed) {
      const raw = window.prompt("Agreed price (AED)", String(d.offer_aed ?? ""));
      if (raw == null) return;
      agreed = Number(raw) || null;
    }
    await api(`/api/deals/${d.id}`, { method: "PATCH", json: { status: s, ...(agreed ? { agreed_aed: agreed } : {}) } });
    await mutate();
  };

  const open = items.filter((d) => !["closed", "lost"].includes(d.status));
  const pipelineAed = open.reduce((s, d) => s + (d.commission_aed ?? 0), 0);
  const closedAed = items.filter((d) => d.status === "closed").reduce((s, d) => s + (d.commission_aed ?? 0), 0);

  return (
    <>
      <PageHeader kicker="Deals" title="Deals" description="Offer → MOU (Form F) → deposit → transfer at the trustee office. Commission is calculated from the agreed price." />

      <div className="mb-4 grid grid-cols-3 gap-3">
        <Stat label="Open deals" value={open.length} />
        <Stat label="Commission in play" value={fmtAed(pipelineAed)} />
        <Stat label="Commission closed" value={fmtAed(closedAed)} tone="good" />
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {["", ...FLOW, "lost"].map((s) => (
          <button key={s} className={`chip ${filter === s ? "bg-ink text-white border-ink" : "bg-surface hover:bg-canvas"}`} onClick={() => setFilter(s)}>
            {s ? stageLabel(s) : "All"}
          </button>
        ))}
      </div>

      <div className="card overflow-x-auto">
        {data && items.length === 0 && (
          <div className="p-4">
            <Empty title="No deals yet" hint="Record an offer from a lead's page." />
          </div>
        )}
        {items.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr className="border-b">
                <th className="px-4 py-2 font-medium">Lead</th>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Offer</th>
                <th className="px-4 py-2 font-medium">Agreed</th>
                <th className="px-4 py-2 font-medium">Commission</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Updated</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {items.map((d) => {
                const idx = FLOW.indexOf(d.status);
                const next = idx >= 0 && idx < FLOW.length - 1 ? FLOW[idx + 1] : null;
                return (
                  <tr key={d.id} className="hover:bg-canvas/60">
                    <td className="px-4 py-2">
                      <Link href={`/leads/${d.lead_id}`} className="font-medium hover:underline">
                        View lead
                      </Link>
                    </td>
                    <td className="px-4 py-2 capitalize">{d.deal_type}</td>
                    <td className="px-4 py-2 tabular-nums">{fmtAed(d.offer_aed)}</td>
                    <td className="px-4 py-2 tabular-nums">{fmtAed(d.agreed_aed)}</td>
                    <td className="px-4 py-2 tabular-nums">
                      {fmtAed(d.commission_aed)} {d.commission_pct != null && <span className="text-xs text-muted">({d.commission_pct}%)</span>}
                    </td>
                    <td className="px-4 py-2">
                      <StatusChip status={d.status} />
                    </td>
                    <td className="px-4 py-2 text-xs text-muted">{relTime(d.updated_at)}</td>
                    <td className="px-4 py-2 text-right">
                      {next && (
                        <span className="flex justify-end gap-1">
                          <button className="btn-ghost btn-sm" onClick={() => advance(d, next)}>
                            → {stageLabel(next)}
                          </button>
                          <button className="btn-ghost btn-sm text-danger" onClick={() => advance(d, "lost")}>
                            Lost
                          </button>
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
