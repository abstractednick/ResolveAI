"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, loadSession, Ticket } from "@/lib/api";

export default function TicketDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const session = useMemo(() => loadSession(), []);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    if (!session) return;
    const [t, e, m] = await Promise.all([
      api<Ticket>(`/api/v1/tickets/${id}`, {}, session.access_token),
      api<any[]>(`/api/v1/tickets/${id}/events`, {}, session.access_token),
      api<any[]>(`/api/v1/tickets/${id}/messages`, {}, session.access_token),
    ]);
    setTicket(t);
    setEvents(e);
    setMessages(m);
    if (t.suggested_reply && !reply) setReply(t.suggested_reply);
  }

  useEffect(() => {
    if (!session) {
      router.replace("/");
      return;
    }
    load().catch((err) => setError(String(err.message || err)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, session?.access_token]);

  async function draft() {
    if (!session) return;
    setBusy(true);
    try {
      const res = await api<{ draft: string }>(`/api/v1/tickets/${id}/draft`, { method: "POST" }, session.access_token);
      setReply(res.draft);
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function sendReply() {
    if (!session || !reply.trim()) return;
    setBusy(true);
    try {
      await api(`/api/v1/tickets/${id}/reply`, {
        method: "POST",
        body: JSON.stringify({ body: reply, send_translation: true }),
      }, session.access_token);
      setReply("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  if (!ticket) {
    return <div className="p-8 text-ink/50">{error || "Loading…"}</div>;
  }

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-6 md:px-8">
      <Link href="/dashboard" className="text-sm text-sea">
        ← Queue
      </Link>
      <header className="mt-4 animate-rise">
        <h1 className="font-display text-3xl">{ticket.subject}</h1>
        <p className="mt-2 text-sm text-ink/55">
          {ticket.customer_email} · {ticket.status} · {ticket.priority} · {ticket.sentiment} · lang {ticket.language}
        </p>
      </header>

      {ticket.summary && (
        <div className="mt-6 rounded-xl border border-sea/20 bg-sea/5 p-4 text-sm animate-rise">
          <p className="text-[11px] uppercase tracking-wide text-sea">Handoff summary</p>
          <p className="mt-1">{ticket.summary}</p>
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="space-y-4">
          <div className="rounded-xl border border-ink/10 bg-white/80 p-4">
            <p className="text-[11px] uppercase tracking-wide text-ink/40">Original</p>
            <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{ticket.body}</p>
          </div>

          <div className="rounded-xl border border-ink/10 bg-white/80 p-4">
            <p className="mb-3 text-[11px] uppercase tracking-wide text-ink/40">Thread</p>
            <div className="space-y-3">
              {messages.map((m) => (
                <div key={m.id} className="border-l-2 border-ink/10 pl-3 text-sm">
                  <p className="text-[11px] uppercase text-ink/40">{m.author_type}</p>
                  <p className="mt-1 whitespace-pre-wrap">{m.body}</p>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-ink/10 bg-white/80 p-4">
            <div className="mb-2 flex items-center justify-between">
              <p className="text-[11px] uppercase tracking-wide text-ink/40">Agent reply assistant</p>
              <button onClick={draft} disabled={busy} className="text-xs text-sea">
                Regenerate draft
              </button>
            </div>
            <textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              rows={8}
              className="w-full rounded-lg border border-ink/10 bg-white p-3 text-sm outline-none focus:border-sea"
            />
            <button
              onClick={sendReply}
              disabled={busy || !reply.trim()}
              className="mt-3 rounded-xl bg-ink px-4 py-2 text-sm text-white hover:bg-sea disabled:opacity-50"
            >
              Send reply
            </button>
          </div>
        </section>

        <section className="space-y-4">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <Stat label="SLA risk" value={`${(ticket.breach_risk_score * 100).toFixed(0)}%`} />
            <Stat label="Sentiment" value={`${ticket.sentiment} (${ticket.sentiment_score.toFixed(2)})`} />
            <Stat label="Team" value={ticket.assigned_team || "—"} />
            <Stat label="CSAT pred." value={ticket.predicted_csat != null ? `${(ticket.predicted_csat * 100).toFixed(0)}%` : "—"} />
          </div>

          <div className="rounded-xl border border-ink/10 bg-white/80 p-4">
            <p className="mb-3 text-[11px] uppercase tracking-wide text-ink/40">Audit / AI actions</p>
            <div className="max-h-[520px] space-y-3 overflow-auto">
              {events.map((e) => (
                <div key={e.id} className="border-b border-ink/5 pb-2 text-sm last:border-0">
                  <div className="flex justify-between gap-2">
                    <span className="font-medium">{e.action}</span>
                    <span className="text-[11px] text-ink/40">{new Date(e.created_at).toLocaleString()}</span>
                  </div>
                  <p className="mt-1 text-xs text-ink/50">{e.actor_type}{e.actor_id ? ` · ${e.actor_id}` : ""}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
      {error && <p className="mt-4 text-sm text-coral">{error}</p>}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-ink/10 bg-white/80 p-3">
      <p className="text-[11px] uppercase tracking-wide text-ink/40">{label}</p>
      <p className="mt-1 font-medium">{value}</p>
    </div>
  );
}
