"use client";

import { Mail, MessageCircle, Phone } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Empty, ErrorText, Field, Modal, PageHeader, ScoreBadge, StageChip, StatusChip } from "@/components/ui";
import { STAGES, api, fmtAed, fmtDate, relTime, stageLabel, useApi } from "@/lib/api";
import type { Lead, LeadDetail, Listing, User } from "@/lib/types";

export default function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, mutate } = useApi<LeadDetail>(`/api/leads/${id}`);
  const { data: team } = useApi<{ items: User[] }>("/api/settings/team", { shouldRetryOnError: false });
  const [modal, setModal] = useState<"note" | "followup" | "viewing" | "deal" | "edit" | null>(null);
  const [actionError, setActionError] = useState<unknown>(null);

  if (error) return <ErrorText error={error} />;
  if (!data) return <div className="text-sm text-muted">Loading…</div>;
  const { lead } = data;

  const run = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try {
      await fn();
      await mutate();
      setModal(null);
    } catch (e) {
      setActionError(e);
    }
  };

  const setStage = (stage: string) => {
    const lost_reason = stage === "lost" ? window.prompt("Why was this lead lost?") ?? undefined : undefined;
    return run(() => api(`/api/leads/${lead.id}/stage`, { method: "POST", json: { stage, lost_reason } }));
  };

  const wa = lead.phone ? `https://wa.me/${lead.phone.replace(/\D/g, "")}` : null;

  return (
    <>
      <PageHeader
        kicker={
          <Link href="/leads" className="hover:text-ink">
            ← Leads
          </Link>
        }
        title={lead.name || "Unnamed lead"}
        description={[lead.source.replace(/_/g, " "), lead.external_id ? `ref ${lead.external_id}` : null, `added ${relTime(lead.created_at)}`].filter(Boolean).join(" · ")}
        actions={
          <>
            {lead.phone && (
              <a className="btn-ghost btn-sm" href={`tel:${lead.phone}`}>
                <Phone className="h-3.5 w-3.5" /> Call
              </a>
            )}
            {wa && (
              <a className="btn-ghost btn-sm" href={wa} target="_blank" rel="noreferrer">
                <MessageCircle className="h-3.5 w-3.5" /> WhatsApp
              </a>
            )}
            {lead.email && (
              <a className="btn-ghost btn-sm" href={`mailto:${lead.email}`}>
                <Mail className="h-3.5 w-3.5" /> E-mail
              </a>
            )}
            <button className="btn-primary btn-sm" onClick={() => setModal("note")}>
              Log activity
            </button>
          </>
        }
      />

      <ErrorText error={actionError} />

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <section className="card p-4">
            <div className="flex flex-wrap items-center gap-2">
              <StageChip stage={lead.stage} />
              <ScoreBadge score={lead.ai_score} band={lead.ai_band} />
              {lead.do_not_contact && <span className="chip bg-danger-soft text-danger">Do not contact</span>}
              <span className="ml-auto text-xs text-muted">stage since {relTime(lead.stage_changed_at)}</span>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {STAGES.filter((s) => s !== lead.stage && s !== "opted_out").map((s) => (
                <button key={s} className="chip bg-canvas hover:bg-surface" onClick={() => setStage(s)}>
                  → {stageLabel(s)}
                </button>
              ))}
            </div>
            {lead.ai_summary && (
              <p className="mt-3 rounded-xl bg-brand-soft/60 p-3 text-sm">
                <span className="kicker mr-2">AI brief</span>
                {lead.ai_summary}
                {lead.ai_scored_at && <span className="ml-2 text-xs text-muted">{relTime(lead.ai_scored_at)}</span>}
              </p>
            )}
            {lead.lost_reason && <p className="mt-2 text-sm text-danger">Lost: {lead.lost_reason}</p>}
          </section>

          <section className="card p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-sm font-semibold">Requirements</h2>
              <button className="btn-ghost btn-sm" onClick={() => setModal("edit")}>
                Edit
              </button>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3">
              <KV k="Purpose" v={lead.purpose} />
              <KV k="Property" v={[lead.bedrooms != null ? `${lead.bedrooms}BR` : null, lead.property_type].filter(Boolean).join(" ")} />
              <KV k="Budget" v={lead.budget_min_aed || lead.budget_max_aed ? `${fmtAed(lead.budget_min_aed)} – ${fmtAed(lead.budget_max_aed)}` : null} />
              <KV k="Areas" v={lead.areas.join(", ")} />
              <KV k="Timeline" v={lead.timeline} />
              <KV k="Payment" v={lead.payment_method} />
              <KV k="Nationality" v={lead.nationality} />
              <KV k="Language" v={lead.language} />
              <KV k="Assigned to" v={lead.assigned_agent?.full_name ?? "Unassigned"} />
            </dl>
            {lead.notes && <p className="mt-3 whitespace-pre-wrap rounded-xl bg-canvas p-3 text-sm">{lead.notes}</p>}
          </section>

          <section className="card p-4">
            <h2 className="mb-2 text-sm font-semibold">Timeline</h2>
            {data.activities.length === 0 && <Empty title="No activity yet" />}
            <ol className="relative space-y-3 border-l pl-4">
              {data.activities.map((a) => (
                <li key={a.id} className="text-sm">
                  <span className="absolute -left-[5px] mt-1.5 h-2 w-2 rounded-full bg-line" />
                  <div className="flex items-baseline justify-between gap-2">
                    <span>{a.summary}</span>
                    <span className="shrink-0 text-xs text-muted">{fmtDate(a.created_at, true)}</span>
                  </div>
                  <div className="text-xs text-muted">
                    {a.kind.replace(/_/g, " ")} · {a.actor_type.replace(/_/g, " ")}
                  </div>
                </li>
              ))}
            </ol>
          </section>
        </div>

        <div className="space-y-4">
          <section className="card p-4">
            <h2 className="text-sm font-semibold">Contact</h2>
            <dl className="mt-2 space-y-1 text-sm">
              <KV k="Phone" v={lead.phone} />
              <KV k="E-mail" v={lead.email} />
              <KV k="Last contact" v={relTime(lead.last_contacted_at)} />
              <KV k="Next follow-up" v={lead.next_follow_up_at ? fmtDate(lead.next_follow_up_at, true) : "—"} />
              <KV k="Marketing consent" v={lead.consent_marketing ? "Yes" : "No"} />
            </dl>
          </section>

          <Panel title="Follow-ups" onAdd={() => setModal("followup")}>
            {data.followups.length === 0 && <Empty title="None scheduled" />}
            {data.followups.map((f) => (
              <div key={f.id} className="flex items-center justify-between gap-2 py-1.5 text-sm">
                <div className="min-w-0">
                  <div className="truncate">{f.title}</div>
                  <div className="text-xs text-muted">
                    {f.channel} · {fmtDate(f.due_at, true)}
                  </div>
                </div>
                {f.status === "open" ? (
                  <button className="btn-ghost btn-sm" onClick={() => run(() => api(`/api/followups/${f.id}`, { method: "PATCH", json: { status: "done" } }))}>
                    Done
                  </button>
                ) : (
                  <StatusChip status={f.status} />
                )}
              </div>
            ))}
          </Panel>

          <Panel title="Viewings" onAdd={() => setModal("viewing")}>
            {data.viewings.length === 0 && <Empty title="No viewings" />}
            {data.viewings.map((v) => (
              <div key={v.id} className="py-1.5 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span>{fmtDate(v.scheduled_at, true)}</span>
                  <StatusChip status={v.status} />
                </div>
                <div className="text-xs text-muted">{v.location_note ?? v.source}</div>
                {["requested", "confirmed"].includes(v.status) && (
                  <div className="mt-1 flex gap-1">
                    {v.status === "requested" && <MiniBtn onClick={() => run(() => api(`/api/viewings/${v.id}`, { method: "PATCH", json: { status: "confirmed" } }))}>Confirm</MiniBtn>}
                    <MiniBtn onClick={() => run(() => api(`/api/viewings/${v.id}`, { method: "PATCH", json: { status: "done" } }))}>Done</MiniBtn>
                    <MiniBtn onClick={() => run(() => api(`/api/viewings/${v.id}`, { method: "PATCH", json: { status: "no_show" } }))}>No-show</MiniBtn>
                    <MiniBtn onClick={() => run(() => api(`/api/viewings/${v.id}`, { method: "PATCH", json: { status: "cancelled" } }))}>Cancel</MiniBtn>
                  </div>
                )}
              </div>
            ))}
          </Panel>

          <Panel title="Deals" onAdd={() => setModal("deal")}>
            {data.deals.length === 0 && <Empty title="No offers yet" />}
            {data.deals.map((d) => (
              <div key={d.id} className="py-1.5 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span>{fmtAed(d.agreed_aed ?? d.offer_aed)}</span>
                  <StatusChip status={d.status} />
                </div>
                <div className="text-xs text-muted">commission {fmtAed(d.commission_aed)}</div>
                {!["closed", "lost"].includes(d.status) && (
                  <div className="mt-1 flex gap-1">
                    {["mou", "deposit", "transfer", "closed", "lost"].map((s) => (
                      <MiniBtn key={s} onClick={() => run(() => api(`/api/deals/${d.id}`, { method: "PATCH", json: { status: s } }))}>
                        {stageLabel(s)}
                      </MiniBtn>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </Panel>
        </div>
      </div>

      {modal === "note" && (
        <QuickForm
          title="Log activity"
          fields={[
            { k: "kind", label: "Type", type: "select", options: ["note", "call", "whatsapp", "email", "meeting", "voice_note"], value: "call" },
            { k: "summary", label: "What happened?", type: "textarea", required: true },
          ]}
          onClose={() => setModal(null)}
          onSubmit={(v) => run(() => api(`/api/leads/${lead.id}/activities`, { method: "POST", json: { kind: v.kind, summary: v.summary, mark_contacted: v.kind !== "note" } }))}
        />
      )}
      {modal === "followup" && (
        <QuickForm
          title="Schedule follow-up"
          fields={[
            { k: "title", label: "Title", type: "text", required: true, value: "Call back" },
            { k: "channel", label: "Channel", type: "select", options: ["call", "whatsapp", "email", "voice_note", "meeting"], value: "call" },
            { k: "due_at", label: "Due", type: "datetime-local", required: true, value: defaultTomorrow() },
            { k: "note", label: "Note", type: "textarea" },
          ]}
          onClose={() => setModal(null)}
          onSubmit={(v) => run(() => api("/api/followups", { method: "POST", json: { lead_id: lead.id, title: v.title, channel: v.channel, due_at: new Date(v.due_at).toISOString(), note: v.note || null } }))}
        />
      )}
      {modal === "viewing" && <ViewingForm lead={lead} onClose={() => setModal(null)} onSubmit={(json) => run(() => api("/api/viewings", { method: "POST", json }))} />}
      {modal === "deal" && (
        <QuickForm
          title="Record offer"
          fields={[
            { k: "offer_aed", label: "Offer (AED)", type: "number", required: true },
            { k: "commission_pct", label: "Commission %", type: "number", value: "2" },
            { k: "deal_type", label: "Type", type: "select", options: ["sale", "rent"], value: lead.purpose === "rent" ? "rent" : "sale" },
            { k: "notes", label: "Notes", type: "textarea" },
          ]}
          onClose={() => setModal(null)}
          onSubmit={(v) => run(() => api("/api/deals", { method: "POST", json: { lead_id: lead.id, offer_aed: Number(v.offer_aed), commission_pct: v.commission_pct ? Number(v.commission_pct) : null, deal_type: v.deal_type, notes: v.notes || null } }))}
        />
      )}
      {modal === "edit" && (
        <QuickForm
          title="Edit requirements"
          fields={[
            { k: "purpose", label: "Purpose", type: "select", options: ["", "buy", "rent", "invest"], value: lead.purpose ?? "" },
            { k: "property_type", label: "Property type", type: "text", value: lead.property_type ?? "" },
            { k: "bedrooms", label: "Bedrooms", type: "number", value: lead.bedrooms?.toString() ?? "" },
            { k: "areas", label: "Areas (comma-separated)", type: "text", value: lead.areas.join(", ") },
            { k: "budget_min_aed", label: "Budget min (AED)", type: "number", value: lead.budget_min_aed?.toString() ?? "" },
            { k: "budget_max_aed", label: "Budget max (AED)", type: "number", value: lead.budget_max_aed?.toString() ?? "" },
            { k: "timeline", label: "Timeline", type: "text", value: lead.timeline ?? "" },
            { k: "payment_method", label: "Payment", type: "select", options: ["", "cash", "mortgage"], value: lead.payment_method ?? "" },
            ...(team && team.items.length > 1 ? [{ k: "assigned_agent_id", label: "Assigned to", type: "select" as const, options: team.items.map((u) => u.id), labels: team.items.map((u) => u.full_name), value: lead.assigned_agent_id ?? "" }] : []),
            { k: "notes", label: "Notes", type: "textarea", value: lead.notes ?? "" },
          ]}
          onClose={() => setModal(null)}
          onSubmit={(v) =>
            run(() =>
              api(`/api/leads/${lead.id}`, {
                method: "PATCH",
                json: {
                  purpose: v.purpose || null,
                  property_type: v.property_type || null,
                  bedrooms: v.bedrooms ? Number(v.bedrooms) : null,
                  areas: v.areas.split(",").map((s) => s.trim()).filter(Boolean),
                  budget_min_aed: v.budget_min_aed ? Number(v.budget_min_aed) : null,
                  budget_max_aed: v.budget_max_aed ? Number(v.budget_max_aed) : null,
                  timeline: v.timeline || null,
                  payment_method: v.payment_method || null,
                  ...(v.assigned_agent_id !== undefined ? { assigned_agent_id: v.assigned_agent_id || null } : {}),
                  notes: v.notes || null,
                },
              }),
            )
          }
        />
      )}
    </>
  );
}

function KV({ k, v }: { k: string; v: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs text-muted">{k}</dt>
      <dd className="capitalize">{v || "—"}</dd>
    </div>
  );
}

function Panel({ title, onAdd, children }: { title: string; onAdd: () => void; children: React.ReactNode }) {
  return (
    <section className="card p-4">
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        <button className="btn-ghost btn-sm" onClick={onAdd}>
          Add
        </button>
      </div>
      <div className="divide-y">{children}</div>
    </section>
  );
}

function MiniBtn({ onClick, children }: { onClick: () => void; children: React.ReactNode }) {
  return (
    <button className="rounded-md border px-1.5 py-0.5 text-[11px] hover:bg-canvas" onClick={onClick} type="button">
      {children}
    </button>
  );
}

type FieldSpec = { k: string; label: string; type: "text" | "number" | "textarea" | "select" | "datetime-local"; options?: string[]; labels?: string[]; value?: string; required?: boolean };

function QuickForm({ title, fields, onClose, onSubmit }: { title: string; fields: FieldSpec[]; onClose: () => void; onSubmit: (values: Record<string, string>) => Promise<void> }) {
  const [values, setValues] = useState<Record<string, string>>(Object.fromEntries(fields.map((f) => [f.k, f.value ?? ""])));
  const [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await onSubmit(values);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        {fields.map((f) => (
          <Field key={f.k} label={f.label} className={f.type === "textarea" ? "col-span-2" : undefined}>
            {f.type === "select" ? (
              <select className="input" value={values[f.k]} onChange={(e) => setValues({ ...values, [f.k]: e.target.value })}>
                {f.options?.map((o, i) => (
                  <option key={o} value={o}>
                    {f.labels?.[i] ?? (o ? stageLabel(o) : "—")}
                  </option>
                ))}
              </select>
            ) : f.type === "textarea" ? (
              <textarea className="input h-20 py-2" value={values[f.k]} required={f.required} onChange={(e) => setValues({ ...values, [f.k]: e.target.value })} />
            ) : (
              <input className="input" type={f.type} value={values[f.k]} required={f.required} onChange={(e) => setValues({ ...values, [f.k]: e.target.value })} />
            )}
          </Field>
        ))}
        <div className="col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy}>
            Save
          </button>
        </div>
      </form>
    </Modal>
  );
}

function ViewingForm({ lead, onClose, onSubmit }: { lead: Lead; onClose: () => void; onSubmit: (json: Record<string, unknown>) => Promise<void> }) {
  const [q, setQ] = useState("");
  const [listingId, setListingId] = useState("");
  const [when, setWhen] = useState(defaultTomorrow());
  const [note, setNote] = useState("");
  const { data } = useApi<{ items: Listing[] }>(`/api/listings?limit=8${q ? `&q=${encodeURIComponent(q)}` : lead.areas[0] ? `&community=${encodeURIComponent(lead.areas[0])}` : ""}`);
  return (
    <Modal title="Book viewing" onClose={onClose}>
      <form
        className="space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void onSubmit({ lead_id: lead.id, listing_id: listingId || null, scheduled_at: new Date(when).toISOString(), location_note: note || null });
        }}
      >
        <Field label="Listing">
          <input className="input mb-2" placeholder="Search reference, title, community…" value={q} onChange={(e) => setQ(e.target.value)} />
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {data?.items.map((l) => (
              <label key={l.id} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-2 py-1.5 text-sm ${listingId === l.id ? "border-ink bg-canvas" : ""}`}>
                <input type="radio" name="listing" value={l.id} checked={listingId === l.id} onChange={() => setListingId(l.id)} />
                <span className="truncate">
                  {l.reference} · {l.title} · {fmtAed(l.price_aed)}
                </span>
              </label>
            ))}
          </div>
        </Field>
        <Field label="When">
          <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} required />
        </Field>
        <Field label="Meeting point / note">
          <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary">
            Book
          </button>
        </div>
      </form>
    </Modal>
  );
}

function defaultTomorrow() {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  d.setHours(10, 0, 0, 0);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
