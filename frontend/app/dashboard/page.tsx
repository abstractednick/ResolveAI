"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearSession, loadSession, Ticket, WS_URL } from "@/lib/api";

const priorities = ["all", "urgent", "high", "medium", "low"];
const statuses = ["all", "open", "in_progress", "pending", "resolved"];

export default function DashboardPage() {
  const router = useRouter();
  const session = useMemo(() => loadSession(), []);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [priority, setPriority] = useState("all");
  const [status, setStatus] = useState("all");
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    if (!session) return;
    const params = new URLSearchParams();
    if (status !== "all") params.set("status", status);
    if (priority !== "all") params.set("priority", priority);
    const qs = params.toString() ? `?${params}` : "";
    const [t, a] = await Promise.all([
      api<Ticket[]>(`/api/v1/tickets${qs}`, {}, session.access_token),
      api<any[]>("/api/v1/admin/alerts", {}, session.access_token),
    ]);
    setTickets(t);
    setAlerts(a.filter((x) => !x.acknowledged).slice(0, 8));
  }

  useEffect(() => {
    if (!session) {
      router.replace("/");
      return;
    }
    refresh().catch((e) => setError(String(e.message || e)));
    const ws = new WebSocket(`${WS_URL}/ws/${session.tenant_id}`);
    ws.onopen = () => setLive(true);
    ws.onclose = () => setLive(false);
    ws.onmessage = () => {
      refresh().catch(() => undefined);
    };
    return () => ws.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.access_token, priority, status]);

  if (!session) return null;

  return (
    <div className="mx-auto min-h-screen max-w-7xl px-4 py-6 md:px-8">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-4 animate-rise">
        <div>
          <p className="font-display text-3xl tracking-tight">ResolveAI</p>
          <p className="text-sm text-ink/60">
            {session.email} · {session.role}
            <span className={`ml-3 inline-flex items-center gap-1 ${live ? "text-sea" : "text-ink/40"}`}>
              <span className={`h-2 w-2 rounded-full ${live ? "bg-sea animate-pulse-soft" : "bg-ink/30"}`} />
              {live ? "live" : "offline"}
            </span>
          </p>
        </div>
        <nav className="flex gap-3 text-sm">
          <Link href="/dashboard" className="rounded-lg bg-ink px-3 py-2 text-white">
            Queue
          </Link>
          <Link href="/admin" className="rounded-lg border border-ink/15 bg-white/70 px-3 py-2">
            Admin
          </Link>
          <button
            className="rounded-lg border border-ink/15 px-3 py-2 text-ink/60"
            onClick={() => {
              clearSession();
              router.push("/");
            }}
          >
            Sign out
          </button>
        </nav>
      </header>

      {error && <p className="mb-4 text-sm text-coral">{error}</p>}

      <div className="mb-6 flex flex-wrap gap-2">
        {statuses.map((s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={`rounded-full px-3 py-1 text-xs ${status === s ? "bg-sea text-white" : "bg-white/70 text-ink/70"}`}
          >
            {s}
          </button>
        ))}
        <span className="mx-2 text-ink/20">|</span>
        {priorities.map((p) => (
          <button
            key={p}
            onClick={() => setPriority(p)}
            className={`rounded-full px-3 py-1 text-xs ${priority === p ? "bg-coral text-white" : "bg-white/70 text-ink/70"}`}
          >
            {p}
          </button>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        <section className="space-y-3">
          {tickets.length === 0 && (
            <div className="rounded-xl border border-dashed border-ink/20 bg-white/50 p-8 text-center text-ink/50">
              No tickets yet. Create one via API, email webhook, or widget.
            </div>
          )}
          {tickets.map((t, i) => (
            <Link
              key={t.id}
              href={`/tickets/${t.id}`}
              className="block rounded-xl border border-ink/10 bg-white/80 p-4 transition hover:border-sea/40 animate-rise"
              style={{ animationDelay: `${i * 40}ms` }}
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <p className="font-medium">{t.subject}</p>
                  <p className="mt-1 text-xs text-ink/50">
                    {t.customer_email} · {t.channel} · {t.category || "unclassified"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2 text-[11px] uppercase tracking-wide">
                  <span className="rounded bg-ink/5 px-2 py-1">{t.status}</span>
                  <span className="rounded bg-coral/15 px-2 py-1 text-coral">{t.priority}</span>
                  {t.auto_resolved && <span className="rounded bg-sea/15 px-2 py-1 text-sea">auto</span>}
                  {t.breach_risk_score >= 0.7 && (
                    <span className="rounded bg-coral/20 px-2 py-1 text-coral">
                      SLA {(t.breach_risk_score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
              </div>
              {t.summary && <p className="mt-3 line-clamp-2 text-sm text-ink/65">{t.summary}</p>}
            </Link>
          ))}
        </section>

        <aside className="space-y-3">
          <h2 className="font-display text-xl">Alerts</h2>
          {alerts.length === 0 && <p className="text-sm text-ink/45">All clear.</p>}
          {alerts.map((a) => (
            <div key={a.id} className="rounded-xl border border-ink/10 bg-white/70 p-3 text-sm">
              <p className="text-[11px] uppercase tracking-wide text-ink/40">{a.alert_type}</p>
              <p className="mt-1 text-ink/80">{a.message}</p>
            </div>
          ))}
        </aside>
      </div>
    </div>
  );
}
