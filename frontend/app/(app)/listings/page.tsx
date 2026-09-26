"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { type FormEvent, useState } from "react";
import { Empty, ErrorText, Field, Modal, PageHeader, StatusChip } from "@/components/ui";
import { api, fmtAed, relTime, useApi } from "@/lib/api";
import type { Listing, Paged } from "@/lib/types";

const STATUSES = ["draft", "live", "under_offer", "sold", "rented", "withdrawn"];

export default function ListingsPage() {
  const params = useSearchParams();
  const router = useRouter();
  const view = params.get("view") ?? "all";
  const [q, setQ] = useState("");
  const [creating, setCreating] = useState(false);
  const status = params.get("status") ?? "";
  const type = params.get("type") ?? "";

  const query = new URLSearchParams({ limit: "100" });
  if (q) query.set("q", q);
  if (status) query.set("status", status);
  if (type) query.set("listing_type", type);
  const { data, mutate } = useApi<Paged<Listing>>(view === "stale" ? null : `/api/listings?${query}`);
  const { data: stale, mutate: mutateStale } = useApi<{ items: Listing[]; days: number }>(view === "stale" ? "/api/listings/stale" : null);

  const setParam = (k: string, v: string) => {
    const next = new URLSearchParams(params.toString());
    if (v) next.set(k, v);
    else next.delete(k);
    router.replace(`/listings?${next}`);
  };

  const verify = async (id: string) => {
    await api(`/api/listings/${id}/verify`, { method: "POST" });
    await Promise.all([mutate(), mutateStale()]);
  };
  const setStatus = async (id: string, s: string) => {
    await api(`/api/listings/${id}`, { method: "PATCH", json: { status: s } });
    await mutate();
  };

  const rows = view === "stale" ? stale?.items : data?.items;

  return (
    <>
      <PageHeader
        kicker="Listings"
        title={view === "stale" ? "Needs verification" : data ? `${data.total} listings` : "Listings"}
        description={view === "stale" ? `Live for ${stale?.days ?? 14}+ days without a check. Portals de-rank unverified stock — confirm or withdraw.` : "Your inventory with Trakheesi permit and DLD numbers."}
        actions={
          <>
            <div className="flex rounded-xl border p-0.5 text-xs">
              <button className={`rounded-lg px-3 py-1.5 ${view === "all" ? "bg-ink text-white" : ""}`} onClick={() => setParam("view", "")}>
                All
              </button>
              <button className={`rounded-lg px-3 py-1.5 ${view === "stale" ? "bg-ink text-white" : ""}`} onClick={() => setParam("view", "stale")}>
                Stale
              </button>
            </div>
            <button className="btn-primary btn-sm" onClick={() => setCreating(true)}>
              Add listing
            </button>
          </>
        }
      />

      {view === "all" && (
        <div className="card mb-4 flex flex-wrap items-center gap-2 p-3">
          <input className="input min-w-[200px] flex-1" placeholder="Search reference, title, building, community…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search listings" />
          <select className="input w-auto" value={status} onChange={(e) => setParam("status", e.target.value)} aria-label="Status">
            <option value="">Any status</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
          <select className="input w-auto" value={type} onChange={(e) => setParam("type", e.target.value)} aria-label="Type">
            <option value="">Sale & rent</option>
            <option value="sale">Sale</option>
            <option value="rent">Rent</option>
          </select>
        </div>
      )}

      <div className="card overflow-x-auto">
        {rows && rows.length === 0 && (
          <div className="p-4">
            <Empty title={view === "stale" ? "All live listings verified recently" : "No listings"} />
          </div>
        )}
        {rows && rows.length > 0 && (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted">
              <tr className="border-b">
                <th className="px-4 py-2 font-medium">Ref</th>
                <th className="px-4 py-2 font-medium">Property</th>
                <th className="px-4 py-2 font-medium">Price</th>
                <th className="px-4 py-2 font-medium">Permit</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Verified</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.map((l) => (
                <tr key={l.id} className="hover:bg-canvas/60">
                  <td className="px-4 py-2 font-mono text-xs">{l.reference}</td>
                  <td className="px-4 py-2">
                    <div className="font-medium">{l.title}</div>
                    <div className="text-xs text-muted">
                      {[l.bedrooms != null ? `${l.bedrooms}BR` : null, l.property_type, l.community, l.building, l.size_sqft ? `${Math.round(l.size_sqft)} sqft` : null].filter(Boolean).join(" · ")}
                    </div>
                  </td>
                  <td className="px-4 py-2 tabular-nums">
                    {fmtAed(l.price_aed)}
                    {l.listing_type === "rent" && <span className="text-xs text-muted"> / {l.rent_frequency ?? "yr"}</span>}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{l.permit_number ?? <span className="text-warning">missing</span>}</td>
                  <td className="px-4 py-2">
                    <select className="input h-8 w-auto text-xs" value={l.status} onChange={(e) => setStatus(l.id, e.target.value)} aria-label="Change status">
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>
                          {s.replace(/_/g, " ")}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-2 text-xs text-muted">{l.last_verified_at ? relTime(l.last_verified_at) : "never"}</td>
                  <td className="px-4 py-2 text-right">
                    {l.status === "live" && (
                      <button className="btn-ghost btn-sm" onClick={() => verify(l.id)}>
                        Still available
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {creating && (
        <NewListingModal
          onClose={() => setCreating(false)}
          onCreated={async () => {
            setCreating(false);
            await mutate();
          }}
        />
      )}
    </>
  );
}

function NewListingModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({ reference: "", title: "", listing_type: "sale", status: "live", property_type: "apartment", community: "", building: "", bedrooms: "", bathrooms: "", size_sqft: "", price_aed: "", permit_number: "", dld_number: "", owner_name: "", owner_phone: "" });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/api/listings", {
        method: "POST",
        json: {
          reference: f.reference,
          title: f.title,
          listing_type: f.listing_type,
          status: f.status,
          property_type: f.property_type,
          community: f.community,
          building: f.building || null,
          bedrooms: f.bedrooms ? Number(f.bedrooms) : null,
          bathrooms: f.bathrooms ? Number(f.bathrooms) : null,
          size_sqft: f.size_sqft ? Number(f.size_sqft) : null,
          price_aed: Number(f.price_aed),
          rent_frequency: f.listing_type === "rent" ? "yearly" : null,
          permit_number: f.permit_number || null,
          dld_number: f.dld_number || null,
          owner_name: f.owner_name || null,
          owner_phone: f.owner_phone || null,
        },
      });
      onCreated();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title="Add listing" onClose={onClose}>
      <form onSubmit={submit} className="grid grid-cols-2 gap-3">
        <Field label="Reference">
          <input className="input" value={f.reference} onChange={set("reference")} required />
        </Field>
        <Field label="Type">
          <select className="input" value={f.listing_type} onChange={set("listing_type")}>
            <option value="sale">Sale</option>
            <option value="rent">Rent</option>
          </select>
        </Field>
        <Field label="Title" className="col-span-2">
          <input className="input" value={f.title} onChange={set("title")} required minLength={2} />
        </Field>
        <Field label="Community">
          <input className="input" value={f.community} onChange={set("community")} required minLength={2} />
        </Field>
        <Field label="Building">
          <input className="input" value={f.building} onChange={set("building")} />
        </Field>
        <Field label="Property type">
          <select className="input" value={f.property_type} onChange={set("property_type")}>
            {["apartment", "villa", "townhouse", "penthouse", "plot", "office", "retail"].map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Price (AED)">
          <input className="input" type="number" min={1} value={f.price_aed} onChange={set("price_aed")} required />
        </Field>
        <Field label="Bedrooms">
          <input className="input" type="number" min={0} value={f.bedrooms} onChange={set("bedrooms")} />
        </Field>
        <Field label="Bathrooms">
          <input className="input" type="number" min={0} value={f.bathrooms} onChange={set("bathrooms")} />
        </Field>
        <Field label="Size (sqft)">
          <input className="input" type="number" min={1} value={f.size_sqft} onChange={set("size_sqft")} />
        </Field>
        <Field label="Status">
          <select className="input" value={f.status} onChange={set("status")}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Trakheesi permit no.">
          <input className="input" value={f.permit_number} onChange={set("permit_number")} />
        </Field>
        <Field label="DLD number">
          <input className="input" value={f.dld_number} onChange={set("dld_number")} />
        </Field>
        <Field label="Owner name (private)">
          <input className="input" value={f.owner_name} onChange={set("owner_name")} />
        </Field>
        <Field label="Owner phone (private)">
          <input className="input" value={f.owner_phone} onChange={set("owner_phone")} />
        </Field>
        <div className="col-span-2">
          <ErrorText error={error} />
        </div>
        <div className="col-span-2 flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={busy}>
            Save listing
          </button>
        </div>
      </form>
    </Modal>
  );
}
