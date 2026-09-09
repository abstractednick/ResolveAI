"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, saveSession, AuthSession } from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setLoading(true);
    const fd = new FormData(e.currentTarget);
    try {
      if (mode === "register") {
        const session = await api<AuthSession>("/api/v1/auth/register", {
          method: "POST",
          body: JSON.stringify({
            tenant_name: fd.get("tenant_name"),
            tenant_slug: fd.get("tenant_slug"),
            email: fd.get("email"),
            full_name: fd.get("full_name"),
            password: fd.get("password"),
          }),
        });
        saveSession(session);
      } else {
        const session = await api<AuthSession>("/api/v1/auth/login", {
          method: "POST",
          body: JSON.stringify({
            email: fd.get("email"),
            password: fd.get("password"),
            tenant_slug: fd.get("tenant_slug"),
          }),
        });
        saveSession(session);
      }
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative mx-auto flex min-h-screen max-w-6xl flex-col justify-center px-6 py-16">
      <div className="pointer-events-none absolute inset-x-0 top-10 mx-auto h-40 w-[70%] rounded-full bg-sea/10 blur-3xl animate-pulse-soft" />
      <div className="grid items-center gap-12 lg:grid-cols-2">
        <section className="animate-rise">
          <p className="font-display text-5xl tracking-tight text-ink md:text-6xl">ResolveAI</p>
          <p className="mt-4 max-w-md text-lg text-ink/70">
            Classify, resolve, route, and summarize support tickets — with agent assist built in.
          </p>
          <ul className="mt-8 space-y-2 text-sm text-ink/60">
            <li>Auto-classification, sentiment, and SLA risk</li>
            <li>KB deflection widget and duplicate merge</li>
            <li>Multi-tenant admin with full audit trail</li>
          </ul>
        </section>

        <section className="animate-rise rounded-2xl border border-ink/10 bg-white/70 p-8 shadow-sm backdrop-blur" style={{ animationDelay: "120ms" }}>
          <div className="mb-6 flex gap-4 text-sm">
            <button
              type="button"
              className={mode === "login" ? "font-semibold text-sea" : "text-ink/50"}
              onClick={() => setMode("login")}
            >
              Sign in
            </button>
            <button
              type="button"
              className={mode === "register" ? "font-semibold text-sea" : "text-ink/50"}
              onClick={() => setMode("register")}
            >
              Create workspace
            </button>
          </div>
          <form className="space-y-4" onSubmit={onSubmit}>
            {mode === "register" && (
              <>
                <input name="tenant_name" required placeholder="Company name" className="input" />
                <input name="full_name" required placeholder="Your name" className="input" />
              </>
            )}
            <input name="tenant_slug" required placeholder="Workspace slug" className="input" />
            <input name="email" type="email" required placeholder="Email" className="input" />
            <input name="password" type="password" required minLength={8} placeholder="Password" className="input" />
            {error && <p className="text-sm text-coral">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-xl bg-ink px-4 py-3 text-sm font-medium text-white transition hover:bg-sea disabled:opacity-60"
            >
              {loading ? "Working…" : mode === "login" ? "Enter dashboard" : "Launch ResolveAI"}
            </button>
          </form>
        </section>
      </div>
      <style jsx>{`
        .input {
          width: 100%;
          border-radius: 0.75rem;
          border: 1px solid rgba(15, 28, 46, 0.12);
          background: rgba(255, 255, 255, 0.9);
          padding: 0.75rem 1rem;
          font-size: 0.95rem;
          outline: none;
        }
        .input:focus {
          border-color: #1f6f8b;
          box-shadow: 0 0 0 3px rgba(31, 111, 139, 0.15);
        }
      `}</style>
    </main>
  );
}
