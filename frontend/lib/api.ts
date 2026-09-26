"use client";

import useSWR, { type SWRConfiguration } from "swr";

export const API_BASE = process.env.NEXT_PUBLIC_CRM_API ?? "http://localhost:8100";
const TOKEN_KEY = "crm.token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers, body, cache: "no-store" });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/api/auth/")) {
    setToken(null);
    window.location.href = "/login";
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = (await res.json()) as { detail?: unknown };
      if (typeof data.detail === "string") detail = data.detail;
      else if (Array.isArray(data.detail)) detail = data.detail.map((d: { msg?: string }) => d.msg ?? "").join("; ");
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function useApi<T>(path: string | null, config?: SWRConfiguration<T>) {
  return useSWR<T>(path, (p: string) => api<T>(p), { revalidateOnFocus: false, ...config });
}

export const fmtAed = (n: number | null | undefined) =>
  n == null ? "—" : n >= 1_000_000 ? `AED ${(n / 1_000_000).toFixed(n % 1_000_000 ? 2 : 0)}M` : `AED ${Math.round(n).toLocaleString()}`;

export const fmtDate = (s: string | null | undefined, withTime = false) => {
  if (!s) return "—";
  const d = new Date(s);
  return d.toLocaleString("en-AE", {
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    timeZone: "Asia/Dubai",
  });
};

export const relTime = (s: string | null | undefined) => {
  if (!s) return "—";
  const diff = (Date.now() - new Date(s).getTime()) / 1000;
  const abs = Math.abs(diff);
  const unit = abs < 3600 ? [60, "m"] : abs < 86400 ? [3600, "h"] : [86400, "d"];
  const n = Math.max(1, Math.round(abs / (unit[0] as number)));
  return diff >= 0 ? `${n}${unit[1]} ago` : `in ${n}${unit[1]}`;
};

export const STAGES = ["new", "qualifying", "qualified", "handed_off", "viewing_booked", "offer", "closed", "lost", "opted_out"] as const;
export type Stage = (typeof STAGES)[number];
export const stageLabel = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
