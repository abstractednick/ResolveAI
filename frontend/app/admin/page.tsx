"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, loadSession } from "@/lib/api";

export default function AdminPage() {
  const router = useRouter();
  const session = useMemo(() => loadSession(), []);
  const [tenant, setTenant] = useState<any>(null);
  const [teams, setTeams] = useState<any[]>([]);
  const [sla, setSla] = useState<any[]>([]);
  const [rules, setRules] = useState<any[]>([]);
  const [kb, setKb] = useState<any[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [msg, setMsg] = useState("");

  async function refresh() {
    if (!session) return;
    const token = session.access_token;
    const [t, tm, s, r, k, a] = await Promise.all([
      api("/api/v1/admin/tenant", {}, token),
      api("/api/v1/admin/teams", {}, token),
      api("/api/v1/admin/sla", {}, token),
      api("/api/v1/admin/routing-rules", {}, token),
      api("/api/v1/admin/kb", {}, token),
      api("/api/v1/admin/audit", {}, token),
    ]);
    setTenant(t);
    setTeams(tm as any[]);
    setSla(s as any[]);
    setRules(r as any[]);
    setKb(k as any[]);
    setAudit(a as any[]);
  }

  useEffect(() => {
    if (!session) {
      router.replace("/");
      return;
    }
    refresh().catch((e) => setMsg(String(e.message || e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.access_token]);

  async function addTeam(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!session) return;
    const fd = new FormData(e.currentTarget);
    await api(
      "/api/v1/admin/teams",
      {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"),
          slug: fd.get("slug"),
          categories: String(fd.get("categories") || "")
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
        }),
      },
      session.access_token
    );
    e.currentTarget.reset();
    setMsg("Team created");
    await refresh();
  }

  async function addKb(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!session) return;
    const fd = new FormData(e.currentTarget);
    await api(
      "/api/v1/admin/kb",
      {
        method: "POST",
        body: JSON.stringify({
          title: fd.get("title"),
          content: fd.get("content"),
          category: fd.get("category") || null,
          tags: String(fd.get("tags") || "")
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          status: "published",
        }),
      },
      session.access_token
    );
    e.currentTarget.reset();
    setMsg("KB article published");
    await refresh();
  }

  async function addRule(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!session) return;
    const fd = new FormData(e.currentTarget);
    await api(
      "/api/v1/admin/routing-rules",
      {
        method: "POST",
        body: JSON.stringify({
          name: fd.get("name"),
          assign_team: fd.get("assign_team"),
          keywords: String(fd.get("keywords") || "")
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
          categories: String(fd.get("categories") || "")
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
        }),
      },
      session.access_token
    );
    e.currentTarget.reset();
    setMsg("Routing rule saved");
    await refresh();
  }

  async function publishKb(id: string) {
    if (!session) return;
    await api(`/api/v1/admin/kb/${id}/publish`, { method: "PATCH" }, session.access_token);
    await refresh();
  }

  if (!session) return null;

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 py-6 md:px-8">
      <header className="mb-8 flex items-center justify-between">
        <div>
          <p className="font-display text-3xl">Admin</p>
          <p className="text-sm text-ink/55">{tenant?.name} · /{tenant?.slug}</p>
        </div>
        <Link href="/dashboard" className="text-sm text-sea">
          ← Agent queue
        </Link>
      </header>

      {msg && <p className="mb-4 text-sm text-sea">{msg}</p>}

      <section className="mb-8 rounded-xl border border-ink/10 bg-white/80 p-4">
        <h2 className="font-display text-xl">Tenant</h2>
        <p className="mt-2 text-sm">API key for webhooks/widget:</p>
        <code className="mt-1 block break-all rounded-lg bg-ink/5 p-3 text-xs">{tenant?.api_key}</code>
      </section>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title="Teams">
          <ul className="mb-4 space-y-2 text-sm">
            {teams.map((t) => (
              <li key={t.id}>
                {t.name} <span className="text-ink/40">({t.slug})</span>
              </li>
            ))}
          </ul>
          <form onSubmit={addTeam} className="space-y-2">
            <input name="name" required placeholder="Name" className="field" />
            <input name="slug" required placeholder="slug" className="field" />
            <input name="categories" placeholder="categories,comma,separated" className="field" />
            <button className="btn">Add team</button>
          </form>
        </Panel>

        <Panel title="SLA policies">
          <ul className="space-y-3 text-sm">
            {sla.map((p) => (
              <li key={p.id} className="rounded-lg bg-ink/5 p-3">
                <p className="font-medium">
                  {p.name} {p.is_default && <span className="text-sea">(default)</span>}
                </p>
                <p className="mt-1 text-xs text-ink/55">Response mins: {JSON.stringify(p.response_targets)}</p>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Routing rules">
          <ul className="mb-4 space-y-2 text-sm">
            {rules.map((r) => (
              <li key={r.id}>
                {r.name} → {r.assign_team}
              </li>
            ))}
          </ul>
          <form onSubmit={addRule} className="space-y-2">
            <input name="name" required placeholder="Rule name" className="field" />
            <input name="assign_team" required placeholder="Assign team slug" className="field" />
            <input name="keywords" placeholder="keywords" className="field" />
            <input name="categories" placeholder="categories" className="field" />
            <button className="btn">Add rule</button>
          </form>
        </Panel>

        <Panel title="Knowledge base">
          <ul className="mb-4 max-h-48 space-y-2 overflow-auto text-sm">
            {kb.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2">
                <span>
                  {a.title} <span className="text-ink/40">[{a.status}]</span>
                </span>
                {a.status !== "published" && (
                  <button className="text-xs text-sea" onClick={() => publishKb(a.id)}>
                    Publish
                  </button>
                )}
              </li>
            ))}
          </ul>
          <form onSubmit={addKb} className="space-y-2">
            <input name="title" required placeholder="Title" className="field" />
            <textarea name="content" required placeholder="Content" rows={4} className="field" />
            <input name="category" placeholder="category" className="field" />
            <input name="tags" placeholder="tags" className="field" />
            <button className="btn">Publish article</button>
          </form>
        </Panel>
      </div>

      <section className="mt-8 rounded-xl border border-ink/10 bg-white/80 p-4">
        <h2 className="font-display text-xl">Audit log</h2>
        <div className="mt-3 max-h-72 space-y-2 overflow-auto text-sm">
          {audit.map((l) => (
            <div key={l.id} className="border-b border-ink/5 py-2">
              <div className="flex justify-between gap-2">
                <span>
                  {l.action} · {l.resource_type}
                </span>
                <span className="text-xs text-ink/40">{new Date(l.created_at).toLocaleString()}</span>
              </div>
              <p className="text-xs text-ink/50">{l.actor_email}</p>
            </div>
          ))}
        </div>
      </section>

      <style jsx>{`
        .field {
          width: 100%;
          border-radius: 0.65rem;
          border: 1px solid rgba(15, 28, 46, 0.12);
          padding: 0.55rem 0.75rem;
          font-size: 0.875rem;
          background: white;
        }
        .btn {
          border-radius: 0.65rem;
          background: #0f1c2e;
          color: white;
          padding: 0.5rem 0.9rem;
          font-size: 0.85rem;
        }
      `}</style>
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-ink/10 bg-white/80 p-4">
      <h2 className="mb-3 font-display text-xl">{title}</h2>
      {children}
    </section>
  );
}
