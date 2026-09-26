"use client";

import { clsx } from "clsx";
import Link from "next/link";
import { type ReactNode } from "react";
import { fmtAed, stageLabel } from "@/lib/api";
import type { Lead } from "@/lib/types";

export function PageHeader({ kicker, title, description, actions }: { kicker?: ReactNode; title: string; description?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {kicker && <div className="kicker mb-1">{kicker}</div>}
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: string | number; hint?: string; tone?: "warn" | "good" }) {
  return (
    <div className="card p-4">
      <div className="kicker">{label}</div>
      <div className={clsx("mt-1 text-2xl font-semibold tabular-nums", tone === "warn" && "text-warning", tone === "good" && "text-success")}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

const STAGE_TONE: Record<string, string> = {
  new: "bg-canvas text-ink",
  qualifying: "bg-brand-soft text-brand",
  qualified: "bg-brand-soft text-brand",
  handed_off: "bg-warning-soft text-warning",
  viewing_booked: "bg-success-soft text-success",
  offer: "bg-success-soft text-success",
  closed: "bg-ink text-white border-ink",
  lost: "bg-danger-soft text-danger",
  opted_out: "bg-danger-soft text-danger",
};

export function StageChip({ stage }: { stage: string }) {
  return <span className={clsx("chip", STAGE_TONE[stage] ?? "bg-canvas")}>{stageLabel(stage)}</span>;
}

export function ScoreBadge({ score, band }: { score: number | null; band: string | null }) {
  if (score == null) return <span className="chip bg-canvas text-muted">unscored</span>;
  const tone = band === "hot" ? "bg-danger-soft text-danger" : band === "warm" ? "bg-warning-soft text-warning" : "bg-canvas text-muted";
  return (
    <span className={clsx("chip tabular-nums", tone)} title={band ?? undefined}>
      {score} · {band}
    </span>
  );
}

export function StatusChip({ status }: { status: string }) {
  const tone =
    ["done", "confirmed", "delivered", "closed", "live"].includes(status)
      ? "bg-success-soft text-success"
      : ["no_show", "cancelled", "failed", "lost", "withdrawn", "skipped"].includes(status)
        ? "bg-danger-soft text-danger"
        : ["requested", "pending", "open", "offer", "under_offer"].includes(status)
          ? "bg-warning-soft text-warning"
          : "bg-canvas text-muted";
  return <span className={clsx("chip", tone)}>{stageLabel(status)}</span>;
}

export function LeadRow({ lead, meta }: { lead: Lead; meta?: ReactNode }) {
  const budget = lead.budget_max_aed ?? lead.budget_min_aed;
  return (
    <Link href={`/leads/${lead.id}`} className="flex items-center justify-between gap-3 rounded-xl px-3 py-2.5 transition hover:bg-canvas">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{lead.name || "Unnamed lead"}</span>
          <ScoreBadge score={lead.ai_score} band={lead.ai_band} />
        </div>
        <div className="mt-0.5 truncate text-xs text-muted">
          {[lead.purpose, lead.bedrooms != null ? `${lead.bedrooms}BR` : null, lead.areas.slice(0, 2).join(", "), budget ? fmtAed(budget) : null].filter(Boolean).join(" · ") || lead.source}
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2 text-xs text-muted">
        {meta}
        <StageChip stage={lead.stage} />
      </div>
    </Link>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-dashed p-8 text-center">
      <div className="text-sm font-medium">{title}</div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={clsx("block", className)}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-40 flex items-end justify-center bg-ink/30 p-4 sm:items-center" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="card w-full max-w-lg p-5" onClick={(e) => e.stopPropagation()}>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold">{title}</h2>
          <button className="btn-ghost btn-sm" onClick={onClose} type="button">
            Close
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export function ErrorText({ error }: { error: unknown }) {
  if (!error) return null;
  return <p className="rounded-xl bg-danger-soft px-3 py-2 text-sm text-danger">{error instanceof Error ? error.message : String(error)}</p>;
}
