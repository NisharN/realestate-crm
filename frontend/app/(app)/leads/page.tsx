"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Empty, ErrorText, Field, LeadRow, Modal, PageHeader } from "@/components/ui";
import { STAGES, api, relTime, stageLabel, useApi } from "@/lib/api";
import type { Lead, Paged, User } from "@/lib/types";

const SOURCES = ["property_finder", "bayut", "dubizzle", "meta_ads", "whatsapp", "website", "referral", "walk_in", "other"];

export default function LeadsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [creating, setCreating] = useState(params.get("new") === "1");
  const stage = params.get("stage") ?? "";
  const band = params.get("band") ?? "";
  const source = params.get("source") ?? "";
  const openOnly = !stage && !["closed", "lost", "opted_out"].includes(stage);
  const page = Number(params.get("page") ?? "0");

  const query = new URLSearchParams({ limit: "50", offset: String(page * 50), open_only: String(openOnly) });
  if (q) query.set("q", q);
  if (stage) query.set("stage", stage);
  if (band) query.set("band", band);
  if (source) query.set("source", source);
  const { data, mutate } = useApi<Paged<Lead>>(`/api/leads?${query}`);

  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v);
    else next.delete(k);
    next.delete("page");
    router.replace(`/leads?${next}`);
  };

  return (
    <>
      <PageHeader
        kicker="Leads"
        title={data ? `${data.total} leads` : "Leads"}
        actions={
          <button className="btn-primary btn-sm" onClick={() => setCreating(true)}>
            New lead
          </button>
        }
      />

      <div className="card mb-4 flex flex-wrap items-center gap-2 p-3">
        <form
          className="flex-1 min-w-[200px]"
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", q);
          }}
        >
          <input className="input" placeholder="Search name, phone, e-mail…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search leads" />
        </form>
        <select className="input w-auto" value={stage} onChange={(e) => setParam("stage", e.target.value)} aria-label="Stage">
          <option value="">All open stages</option>
          {STAGES.map((s) => (
            <option key={s} value={s}>
              {stageLabel(s)}
            </option>
          ))}
        </select>
        <select className="input w-auto" value={band} onChange={(e) => setParam("band", e.target.value)} aria-label="Score band">
          <option value="">Any score</option>
          <option value="hot">Hot</option>
          <option value="warm">Warm</option>
          <option value="cold">Cold</option>
        </select>
        <select className="input w-auto" value={source} onChange={(e) => setParam("source", e.target.value)} aria-label="Source">
          <option value="">Any source</option>
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {s.replace(/_/g, " ")}
            </option>
          ))}
        </select>
      </div>

      <div className="card p-2">
        {data && data.items.length === 0 && <Empty title="No leads match" hint="Try clearing a filter, or add a lead manually." />}
        {data?.items.map((l) => <LeadRow key={l.id} lead={l} meta={<span className="hidden sm:inline">{l.source.replace(/_/g, " ")} · {relTime(l.updated_at)}</span>} />)}
      </div>

      {data && data.total > 50 && (
        <div className="mt-3 flex items-center justify-between text-xs text-muted">
          <button className="btn-ghost btn-sm" disabled={page === 0} onClick={() => setParam("page", String(page - 1))}>
            Previous
          </button>
          <span>
            {page * 50 + 1}–{Math.min((page + 1) * 50, data.total)} of {data.total}
          </span>
          <button className="btn-ghost btn-sm" disabled={(page + 1) * 50 >= data.total} onClick={() => setParam("page", String(page + 1))}>
            Next
          </button>
        </div>
      )}

      {creating && (
        <NewLeadModal
          onClose={() => setCreating(false)}
          onCreated={async (id) => {
            setCreating(false);
            await mutate();
            router.push(`/leads/${id}`);
          }}
        />
      )}
    </>
  );
}

function NewLeadModal({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const { data: team } = useApi<{ items: User[] }>("/api/settings/team", { shouldRetryOnError: false });
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ first_name: "", last_name: "", phone: "", email: "", source: "walk_in", purpose: "buy", bedrooms: "", areas: "", budget_max_aed: "", assigned_agent_id: "", notes: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api<{ lead: Lead; created: boolean }>("/api/leads", {
        method: "POST",
        json: {
          first_name: f.first_name || null,
          last_name: f.last_name || null,
          phone: f.phone || null,
          email: f.email || null,
          source: f.source,
          purpose: f.purpose || null,
          bedrooms: f.bedrooms ? Number(f.bedrooms) : null,
          areas: f.areas ? f.areas.split(",").map((s) => s.trim()).filter(Boolean) : null,
          budget_max_aed: f.budget_max_aed ? Number(f.budget_max_aed) : null,
          assigned_agent_id: f.assigned_agent_id || null,
          notes: f.notes || null,
        },
      });
      onCreated(res.lead.id);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="New lead" onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <Field label="First name">
          <input className="input" value={f.first_name} onChange={set("first_name")} />
        </Field>
        <Field label="Last name">
          <input className="input" value={f.last_name} onChange={set("last_name")} />
        </Field>
        <Field label="Phone (UAE or E.164)">
          <input className="input" value={f.phone} onChange={set("phone")} placeholder="050 123 4567" />
        </Field>
        <Field label="E-mail">
          <input className="input" type="email" value={f.email} onChange={set("email")} />
        </Field>
        <Field label="Source">
          <select className="input" value={f.source} onChange={set("source")}>
            {SOURCES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Purpose">
          <select className="input" value={f.purpose} onChange={set("purpose")}>
            <option value="buy">Buy</option>
            <option value="rent">Rent</option>
            <option value="invest">Invest</option>
          </select>
        </Field>
        <Field label="Bedrooms">
          <input className="input" type="number" min={0} value={f.bedrooms} onChange={set("bedrooms")} />
        </Field>
        <Field label="Max budget (AED)">
          <input className="input" type="number" min={0} value={f.budget_max_aed} onChange={set("budget_max_aed")} />
        </Field>
        <Field label="Areas (comma-separated)" className="col-span-2">
          <input className="input" value={f.areas} onChange={set("areas")} placeholder="Dubai Marina, JVC" />
        </Field>
        {team && team.items.length > 1 && (
          <Field label="Assign to" className="col-span-2">
            <select className="input" value={f.assigned_agent_id} onChange={set("assigned_agent_id")}>
              <option value="">Me</option>
              {team.items.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </Field>
        )}
        <Field label="Notes" className="col-span-2">
          <textarea className="input h-20 py-2" value={f.notes} onChange={set("notes")} />
        </Field>
        <div className="col-span-2">
          <ErrorText error={error} />
        </div>
        <div className="col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy || (!f.phone && !f.email)}>
            Save lead
          </button>
        </div>
      </form>
    </Modal>
  );
}
