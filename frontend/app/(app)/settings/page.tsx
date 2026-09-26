"use client";

import { type FormEvent, useState } from "react";
import { Empty, ErrorText, Field, Modal, PageHeader, StatusChip } from "@/components/ui";
import { API_BASE, api, fmtDate, relTime, useApi } from "@/lib/api";
import type { Agency, ApiKey, Delivery, User, Webhook } from "@/lib/types";

const SCOPES = ["leads:read", "leads:write", "listings:read", "listings:write", "viewings:read", "viewings:write", "followups:read", "followups:write", "agents:read"];
const EVENTS = ["*", "lead.*", "listing.*", "viewing.*", "followup.*", "deal.*"];

export default function SettingsPage() {
  const { data: me } = useApi<{ user: User; agency: Agency | null }>("/api/auth/me");
  const isManager = me?.user.role === "owner" || me?.user.role === "manager";

  return (
    <>
      <PageHeader kicker="Settings" title="Workspace" description="Agency details, your team, and the keys that let the AI agent platform read and write your CRM." />
      <div className="space-y-4">
        <AgencyCard agency={me?.agency ?? null} />
        {isManager && <TeamCard />}
        {isManager && <ApiKeysCard />}
        {isManager && <WebhooksCard />}
        {me && !isManager && <p className="text-sm text-muted">API keys, webhooks and team management are available to owners and managers.</p>}
      </div>
    </>
  );
}

function Card({ title, description, action, children }: { title: string; description?: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="card p-4">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description && <p className="text-xs text-muted">{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

function AgencyCard({ agency }: { agency: Agency | null }) {
  return (
    <Card title="Agency">
      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <KV k="Name" v={agency?.name} />
        <KV k="RERA ORN" v={agency?.rera_orn} />
        <KV k="Phone" v={agency?.phone} />
        <KV k="E-mail" v={agency?.email} />
      </dl>
      <p className="mt-3 text-xs text-muted">
        Integration base URL: <code className="rounded bg-canvas px-1">{API_BASE}/v1</code>
      </p>
    </Card>
  );
}

function KV({ k, v }: { k: string; v: string | null | undefined }) {
  return (
    <div>
      <dt className="text-xs text-muted">{k}</dt>
      <dd>{v || "—"}</dd>
    </div>
  );
}

function TeamCard() {
  const { data, mutate } = useApi<{ items: User[] }>("/api/settings/team");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [f, setF] = useState({ full_name: "", email: "", password: "", role: "agent", rera_brn: "" });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await api("/api/settings/team", { method: "POST", json: { ...f, rera_brn: f.rera_brn || null } });
      setAdding(false);
      setF({ full_name: "", email: "", password: "", role: "agent", rera_brn: "" });
      await mutate();
    } catch (err) {
      setError(err);
    }
  };
  const patch = async (id: string, body: Record<string, unknown>) => {
    setError(null);
    try {
      await api(`/api/settings/team/${id}`, { method: "PATCH", json: body });
      await mutate();
    } catch (err) {
      setError(err);
    }
  };

  return (
    <Card
      title="Team"
      description="Agents only see leads assigned to them."
      action={
        <button className="btn-ghost btn-sm" onClick={() => setAdding(true)}>
          Add agent
        </button>
      }
    >
      <ErrorText error={error} />
      <ul className="divide-y">
        {data?.items.map((u) => (
          <li key={u.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
            <div>
              <span className={`font-medium ${u.active ? "" : "line-through text-muted"}`}>{u.full_name}</span>
              <span className="ml-2 text-xs text-muted">
                {u.email}
                {u.rera_brn && ` · BRN ${u.rera_brn}`}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <select className="input h-8 w-auto text-xs" value={u.role} onChange={(e) => patch(u.id, { role: e.target.value })} aria-label="Role">
                <option value="owner">Owner</option>
                <option value="manager">Manager</option>
                <option value="agent">Agent</option>
              </select>
              <button className="btn-ghost btn-sm" onClick={() => patch(u.id, { active: !u.active })}>
                {u.active ? "Deactivate" : "Reactivate"}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {adding && (
        <Modal title="Add team member" onClose={() => setAdding(false)}>
          <form onSubmit={submit} className="grid grid-cols-2 gap-3">
            <Field label="Full name" className="col-span-2">
              <input className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} required minLength={2} />
            </Field>
            <Field label="E-mail">
              <input className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required />
            </Field>
            <Field label="Temporary password">
              <input className="input" type="text" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required minLength={8} />
            </Field>
            <Field label="Role">
              <select className="input" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })}>
                <option value="agent">Agent</option>
                <option value="manager">Manager</option>
              </select>
            </Field>
            <Field label="RERA BRN">
              <input className="input" value={f.rera_brn} onChange={(e) => setF({ ...f, rera_brn: e.target.value })} />
            </Field>
            <div className="col-span-2 flex justify-end gap-2">
              <button type="button" className="btn-ghost" onClick={() => setAdding(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-primary">
                Add
              </button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}

function ApiKeysCard() {
  const { data, mutate } = useApi<{ items: ApiKey[] }>("/api/settings/api-keys");
  const [creating, setCreating] = useState(false);
  const [plaintext, setPlaintext] = useState<string | null>(null);
  const [name, setName] = useState("AI agent platform");
  const [scopes, setScopes] = useState<string[]>(SCOPES.filter((s) => s !== "listings:write"));
  const [error, setError] = useState<unknown>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      const res = await api<{ plaintext: string }>("/api/settings/api-keys", { method: "POST", json: { name, scopes } });
      setPlaintext(res.plaintext);
      setCreating(false);
      await mutate();
    } catch (err) {
      setError(err);
    }
  };
  const revoke = async (id: string) => {
    if (!window.confirm("Revoke this key? Anything using it will stop working immediately.")) return;
    await api(`/api/settings/api-keys/${id}`, { method: "DELETE" });
    await mutate();
  };

  return (
    <Card
      title="API keys"
      description="Paste one into the agent platform's CRM connection. The key is shown once."
      action={
        <button className="btn-ghost btn-sm" onClick={() => setCreating(true)}>
          New key
        </button>
      }
    >
      <ErrorText error={error} />
      {plaintext && (
        <div className="mb-3 rounded-xl border border-success/40 bg-success-soft p-3 text-sm">
          <div className="font-medium">Copy your key now — it won&apos;t be shown again.</div>
          <code className="mt-1 block select-all break-all rounded bg-surface px-2 py-1 font-mono text-xs">{plaintext}</code>
          <button className="btn-ghost btn-sm mt-2" onClick={() => setPlaintext(null)}>
            I&apos;ve saved it
          </button>
        </div>
      )}
      {data && data.items.length === 0 && <Empty title="No API keys" hint="Create one to connect the AI agent platform." />}
      <ul className="divide-y">
        {data?.items.map((k) => (
          <li key={k.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
            <div>
              <span className={`font-medium ${k.revoked_at ? "line-through text-muted" : ""}`}>{k.name}</span>
              <span className="ml-2 font-mono text-xs text-muted">{k.prefix}…</span>
              <div className="text-xs text-muted">
                {k.scopes.join(", ")} · {k.last_used_at ? `used ${relTime(k.last_used_at)}` : "never used"}
              </div>
            </div>
            {!k.revoked_at && (
              <button className="btn-ghost btn-sm text-danger" onClick={() => revoke(k.id)}>
                Revoke
              </button>
            )}
          </li>
        ))}
      </ul>

      {creating && (
        <Modal title="New API key" onClose={() => setCreating(false)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Name">
              <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
            <fieldset>
              <legend className="label">Scopes</legend>
              <div className="grid grid-cols-2 gap-1.5 text-sm">
                {SCOPES.map((s) => (
                  <label key={s} className="flex items-center gap-2">
                    <input type="checkbox" checked={scopes.includes(s)} onChange={(e) => setScopes(e.target.checked ? [...scopes, s] : scopes.filter((x) => x !== s))} />
                    <code className="text-xs">{s}</code>
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={scopes.length === 0}>
                Create key
              </button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}

function WebhooksCard() {
  const { data, mutate } = useApi<{ items: Webhook[] }>("/api/settings/webhooks");
  const [creating, setCreating] = useState(false);
  const [secret, setSecret] = useState<{ id: string; value: string } | null>(null);
  const [openDeliveries, setOpenDeliveries] = useState<string | null>(null);
  const [f, setF] = useState({ name: "AI agent platform", url: "", events: ["*"] });
  const [error, setError] = useState<unknown>(null);
  const [testResult, setTestResult] = useState<Delivery | null>(null);

  const wrap = async (fn: () => Promise<void>) => {
    setError(null);
    try {
      await fn();
    } catch (err) {
      setError(err);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void wrap(async () => {
      const res = await api<{ webhook: Webhook & { secret: string } }>("/api/settings/webhooks", { method: "POST", json: f });
      setSecret({ id: res.webhook.id, value: res.webhook.secret });
      setCreating(false);
      await mutate();
    });
  };

  return (
    <Card
      title="Webhooks"
      description="Signed (HMAC-SHA256, X-Signature-256) POSTs to your endpoint whenever leads, listings, viewings, follow-ups or deals change."
      action={
        <button className="btn-ghost btn-sm" onClick={() => setCreating(true)}>
          Add endpoint
        </button>
      }
    >
      <ErrorText error={error} />
      {secret && (
        <div className="mb-3 rounded-xl border border-success/40 bg-success-soft p-3 text-sm">
          <div className="font-medium">Signing secret — store it with the receiver.</div>
          <code className="mt-1 block select-all break-all rounded bg-surface px-2 py-1 font-mono text-xs">{secret.value}</code>
          <button className="btn-ghost btn-sm mt-2" onClick={() => setSecret(null)}>
            Hide
          </button>
        </div>
      )}
      {testResult && (
        <div className="mb-3 rounded-xl bg-canvas p-3 text-xs">
          Test delivery: <StatusChip status={testResult.status} /> {testResult.response_status && `HTTP ${testResult.response_status}`} {testResult.error && <span className="text-danger">{testResult.error}</span>}
        </div>
      )}
      {data && data.items.length === 0 && <Empty title="No webhooks" hint="Add the agent platform's inbound URL to push changes in real time." />}
      <ul className="divide-y">
        {data?.items.map((w) => (
          <li key={w.id} className="py-2 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <span className={`font-medium ${w.active ? "" : "text-muted"}`}>{w.name}</span>
                <span className="ml-2 break-all font-mono text-xs text-muted">{w.url}</span>
                <div className="text-xs text-muted">
                  {w.events.join(", ")} · {w.last_delivery_at ? `last ${relTime(w.last_delivery_at)} (HTTP ${w.last_status ?? "—"})` : "no deliveries yet"}
                  {w.failure_count > 0 && <span className="text-danger"> · {w.failure_count} failures</span>}
                </div>
              </div>
              <div className="flex flex-wrap gap-1">
                <button className="btn-ghost btn-sm" onClick={() => wrap(async () => setTestResult((await api<{ delivery: Delivery }>(`/api/settings/webhooks/${w.id}/test`, { method: "POST" })).delivery))}>
                  Send test
                </button>
                <button className="btn-ghost btn-sm" onClick={() => setOpenDeliveries(openDeliveries === w.id ? null : w.id)}>
                  History
                </button>
                <button className="btn-ghost btn-sm" onClick={() => wrap(async () => setSecret({ id: w.id, value: (await api<{ secret: string }>(`/api/settings/webhooks/${w.id}/secret`)).secret }))}>
                  Show secret
                </button>
                <button className="btn-ghost btn-sm" onClick={() => wrap(async () => { await api(`/api/settings/webhooks/${w.id}`, { method: "PATCH", json: { active: !w.active } }); await mutate(); })}>
                  {w.active ? "Pause" : "Resume"}
                </button>
                <button
                  className="btn-ghost btn-sm text-danger"
                  onClick={() =>
                    wrap(async () => {
                      if (!window.confirm("Delete this webhook?")) return;
                      await api(`/api/settings/webhooks/${w.id}`, { method: "DELETE" });
                      await mutate();
                    })
                  }
                >
                  Delete
                </button>
              </div>
            </div>
            {openDeliveries === w.id && <Deliveries id={w.id} />}
          </li>
        ))}
      </ul>

      {creating && (
        <Modal title="Add webhook endpoint" onClose={() => setCreating(false)}>
          <form onSubmit={submit} className="space-y-3">
            <Field label="Name">
              <input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
            </Field>
            <Field label="HTTPS URL">
              <input className="input" type="url" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} placeholder="https://agent.example.com/webhooks/crm" required />
            </Field>
            <fieldset>
              <legend className="label">Events</legend>
              <div className="grid grid-cols-2 gap-1.5 text-sm">
                {EVENTS.map((ev) => (
                  <label key={ev} className="flex items-center gap-2">
                    <input type="checkbox" checked={f.events.includes(ev)} onChange={(e) => setF({ ...f, events: e.target.checked ? [...f.events, ev] : f.events.filter((x) => x !== ev) })} />
                    <code className="text-xs">{ev === "*" ? "everything" : ev}</code>
                  </label>
                ))}
              </div>
            </fieldset>
            <div className="flex justify-end gap-2">
              <button type="button" className="btn-ghost" onClick={() => setCreating(false)}>
                Cancel
              </button>
              <button type="submit" className="btn-primary" disabled={f.events.length === 0}>
                Create
              </button>
            </div>
          </form>
        </Modal>
      )}
    </Card>
  );
}

function Deliveries({ id }: { id: string }) {
  const { data } = useApi<{ items: Delivery[] }>(`/api/settings/webhooks/${id}/deliveries`);
  if (!data) return <div className="mt-2 text-xs text-muted">Loading…</div>;
  if (data.items.length === 0) return <div className="mt-2 text-xs text-muted">No deliveries yet.</div>;
  return (
    <table className="mt-2 w-full text-xs">
      <tbody className="divide-y">
        {data.items.map((d) => (
          <tr key={d.id}>
            <td className="py-1 pr-3 font-mono">{d.event}</td>
            <td className="py-1 pr-3">
              <StatusChip status={d.status} />
            </td>
            <td className="py-1 pr-3 tabular-nums">{d.attempts} attempt{d.attempts === 1 ? "" : "s"}</td>
            <td className="py-1 pr-3">{d.response_status ? `HTTP ${d.response_status}` : d.error ?? "—"}</td>
            <td className="py-1 text-muted">{fmtDate(d.created_at, true)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
