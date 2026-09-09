export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export type AuthSession = {
  access_token: string;
  role: string;
  tenant_id: string;
  user_id: string;
  email: string;
};

const SESSION_KEY = "resolveai_session";

export function saveSession(session: AuthSession) {
  if (typeof window !== "undefined") {
    localStorage.setItem(SESSION_KEY, JSON.stringify(session));
  }
}

export function loadSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    return null;
  }
}

export function clearSession() {
  if (typeof window !== "undefined") localStorage.removeItem(SESSION_KEY);
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers.Authorization = `Bearer ${token}`;
  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json() as Promise<T>;
}

export type Ticket = {
  id: string;
  subject: string;
  body: string;
  customer_email: string;
  status: string;
  priority: string;
  category?: string;
  assigned_team?: string;
  sentiment: string;
  sentiment_score: number;
  breach_risk_score: number;
  predicted_csat?: number;
  summary?: string;
  suggested_reply?: string;
  auto_resolved: boolean;
  channel: string;
  language: string;
  created_at: string;
};
