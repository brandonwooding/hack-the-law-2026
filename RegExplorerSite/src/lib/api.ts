const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export interface RegimeCard {
  id: string;
  name: string;
  short_description?: string;
  why_surfaced?: "primary" | "related";
  source_url?: string;
}

export async function fetchRegimes(
  topic: string,
  jurisdictions: string[],
): Promise<RegimeCard[]> {
  const u = new URL(`${BASE}/regimes`);
  u.searchParams.set("topic", topic);
  for (const j of jurisdictions) {
    if (j) u.searchParams.append("jurisdiction", j);
  }
  const r = await fetch(u);
  if (!r.ok) throw new Error(`regimes ${r.status}`);
  return (await r.json()).regimes;
}

export async function fetchAllRegimes(): Promise<RegimeCard[]> {
  const r = await fetch(`${BASE}/regimes/all`);
  if (!r.ok) throw new Error(`regimes/all ${r.status}`);
  return (await r.json()).regimes;
}

export async function sendChat(query: string, regimeIds: string[]) {
  const r = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, regime_ids: regimeIds }),
  });
  if (!r.ok) throw new Error(`chat ${r.status}`);
  return (await r.json()) as {
    answer: string;
    suggestions?: string[];
    citations: unknown[];
  };
}

export async function fetchRegime(id: string) {
  const r = await fetch(`${BASE}/regime/${id}`);
  if (!r.ok) throw new Error(`regime ${r.status}`);
  return r.json();
}

export async function refreshRegulatoryGuidance(id: string) {
  const r = await fetch(`${BASE}/regime/${id}/regulatory-guidance/refresh`, {
    method: "POST",
  });
  if (!r.ok) throw new Error(`regulatory guidance refresh ${r.status}`);
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
