const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface RegimeCard {
  id: string;
  name: string;
  short_description?: string;
  why_surfaced?: "primary" | "related";
  source_url?: string;
}

export async function fetchRegimes(topic: string, jurisdiction: string): Promise<RegimeCard[]> {
  const u = new URL(`${BASE}/regimes`);
  u.searchParams.set("topic", topic);
  if (jurisdiction) u.searchParams.set("jurisdiction", jurisdiction);
  const r = await fetch(u);
  if (!r.ok) throw new Error(`regimes ${r.status}`);
  return (await r.json()).regimes;
}

export async function sendChat(query: string, regimeIds: string[]) {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, regime_ids: regimeIds }),
  });
  if (!r.ok) throw new Error(`chat ${r.status}`);
  return (await r.json()) as { answer: string; citations: unknown[] };
}

export async function fetchRegime(id: string) {
  const r = await fetch(`${BASE}/regime/${id}`);
  if (!r.ok) throw new Error(`regime ${r.status}`);
  return r.json();
}

export async function saveRegime(id: string, fields: Record<string, unknown>) {
  const r = await fetch(`${BASE}/regime/${id}`, {
    method: "PUT",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!r.ok) throw new Error(`save ${r.status}`);
  return r.json();
}
