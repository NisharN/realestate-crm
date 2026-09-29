"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useState } from "react";
import { ErrorText, Field } from "@/components/ui";
import { api, setToken } from "@/lib/api";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [form, setForm] = useState({ email: "", password: "", agency_name: "", full_name: "", rera_orn: "" });
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body =
        mode === "login"
          ? { email: form.email, password: form.password }
          : { email: form.email, password: form.password, agency_name: form.agency_name, full_name: form.full_name, rera_orn: form.rera_orn || null };
      const res = await api<{ token: string }>(`/api/auth/${mode}`, { method: "POST", json: body });
      setToken(res.token);
      router.replace("/");
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="card w-full max-w-sm p-6">
        <div className="kicker">PropX CRM</div>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">{mode === "login" ? "Sign in" : "Create your agency"}</h1>
        <p className="mt-1 text-sm text-muted">{mode === "login" ? "Your leads, listings and viewings in one place." : "You become the owner; add agents from Settings later."}</p>

        <form onSubmit={submit} className="mt-5 space-y-3">
          {mode === "register" && (
            <>
              <Field label="Agency name">
                <input className="input" value={form.agency_name} onChange={set("agency_name")} required minLength={2} />
              </Field>
              <Field label="Your name">
                <input className="input" value={form.full_name} onChange={set("full_name")} required minLength={2} />
              </Field>
              <Field label="RERA ORN (optional)">
                <input className="input" value={form.rera_orn} onChange={set("rera_orn")} />
              </Field>
            </>
          )}
          <Field label="E-mail">
            <input className="input" type="email" autoComplete="email" value={form.email} onChange={set("email")} required />
          </Field>
          <Field label="Password">
            <input className="input" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={form.password} onChange={set("password")} required minLength={8} />
          </Field>
          <ErrorText error={error} />
          <button className="btn-primary w-full" disabled={busy} type="submit">
            {busy ? "…" : mode === "login" ? "Sign in" : "Create agency"}
          </button>
        </form>

        <button className="mt-4 w-full text-center text-xs text-muted hover:text-ink" type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "New agency? Create an account" : "Already registered? Sign in"}
        </button>
      </div>
    </main>
  );
}
