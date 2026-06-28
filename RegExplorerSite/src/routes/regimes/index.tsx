import { createFileRoute, Link } from "@tanstack/react-router";
import { useCallback, useEffect, useState } from "react";
import { ChevronRight, Search } from "lucide-react";
import { SidebarLayout } from "@/components/research/SidebarLayout";
import { JurisdictionTag, jurisdictionFromId } from "@/components/research/JurisdictionTag";
import { addRegime, fetchAllRegimes, type RegimeCard } from "@/lib/api";

export const Route = createFileRoute("/regimes/")({
  head: () => ({
    meta: [{ title: "Regimes — Cross-Jurisdiction Legal Research" }],
  }),
  component: RegimesIndex,
});

type LoadState = "loading" | "ready" | "error";

const JURISDICTION_NAMES: Record<string, string> = {
  EU: "European Union",
  UK: "United Kingdom",
};

function jurisdictionFor(regime: RegimeCard) {
  return regime.jurisdiction || jurisdictionFromId(regime.id) || "";
}

function RegimesIndex() {
  const [regimes, setRegimes] = useState<RegimeCard[]>([]);
  const [state, setState] = useState<LoadState>("loading");
  const [query, setQuery] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [addSummary, setAddSummary] = useState<string | null>(null);

  const loadRegimes = useCallback(() => {
    setState("loading");
    return fetchAllRegimes()
      .then((rs) => {
        setRegimes(rs);
        setState("ready");
      })
      .catch(() => setState("error"));
  }, []);

  useEffect(() => {
    void loadRegimes();
  }, [loadRegimes]);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim() || adding) return;
    setAdding(true);
    setAddError(null);
    setAddSummary(null);
    try {
      const { summary } = await addRegime(prompt.trim());
      setAddSummary(summary);
      setPrompt("");
      await loadRegimes();
    } catch (err) {
      setAddError(err instanceof Error ? err.message : "Failed to add regime");
    } finally {
      setAdding(false);
    }
  }

  const jurisdictionOptions = Array.from(
    new Set(regimes.map(jurisdictionFor).filter(Boolean)),
  ).sort((a, b) => a.localeCompare(b));
  const normalizedQuery = query.trim().toLowerCase();
  const visibleRegimes = regimes.filter((regime) => {
    const regimeJurisdiction = jurisdictionFor(regime);
    if (jurisdiction && regimeJurisdiction !== jurisdiction) return false;
    if (!normalizedQuery) return true;
    return [
      regime.name,
      regime.short_description ?? "",
      regime.id,
      JURISDICTION_NAMES[regimeJurisdiction] ?? regimeJurisdiction,
    ].some((value) => value.toLowerCase().includes(normalizedQuery));
  });

  return (
    <SidebarLayout>
      {showAdd && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4">
          <div className="w-full max-w-[480px] rounded-[4px] border border-hairline bg-paper p-6 shadow-lg">
            <h2 className="font-serif text-lg font-semibold text-ink">Add a regime</h2>
            <p className="mt-1 text-xs text-muted-ink">
              Describe the act to add — the agent resolves it and loads it into the graph.
            </p>
            <form onSubmit={handleAdd} className="mt-4 space-y-3">
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="e.g. add the AI Act from the EU"
                rows={3}
                disabled={adding}
                className="w-full rounded-[3px] border border-hairline bg-paper p-3 text-sm text-ink outline-none focus:border-navy disabled:opacity-60"
              />
              {addError && <p className="text-xs text-red-700">{addError}</p>}
              {addSummary && (
                <p className="whitespace-pre-wrap rounded-[3px] bg-secondary p-3 text-xs text-ink">
                  {addSummary}
                </p>
              )}
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowAdd(false)}
                  disabled={adding}
                  className="h-9 rounded-[3px] border border-hairline px-4 text-sm text-ink transition-colors hover:bg-secondary disabled:opacity-60"
                >
                  Close
                </button>
                <button
                  type="submit"
                  disabled={adding || !prompt.trim()}
                  className="h-9 rounded-[3px] bg-navy px-4 text-sm font-medium text-paper transition-colors hover:bg-ink disabled:opacity-60"
                >
                  {adding ? "Adding…" : "Add"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      <div className="flex h-full flex-col">
        <div className="border-b border-hairline px-8 py-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="font-serif text-xl font-semibold tracking-tight text-ink">
                Regimes
              </h1>
              <p className="mt-0.5 text-xs text-muted-ink">
                Top-level regulatory regimes in the dataset
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowAdd(true)}
              className="h-9 flex-shrink-0 rounded-[3px] bg-navy px-4 text-sm font-medium text-paper transition-colors hover:bg-ink"
            >
              Add a regime
            </button>
          </div>
          <div className="mt-5 flex flex-col gap-3 sm:flex-row">
            <label className="relative flex min-w-0 flex-1 items-center">
              <Search
                className="pointer-events-none absolute left-3 h-4 w-4 text-muted-ink"
                aria-hidden="true"
              />
              <input
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search regimes"
                className="h-9 w-full rounded-[3px] border border-hairline bg-paper py-2 pl-9 pr-3 text-sm text-ink outline-none transition-colors placeholder:text-muted-ink focus:border-navy"
              />
            </label>
            <select
              value={jurisdiction}
              onChange={(e) => setJurisdiction(e.target.value)}
              className="h-9 rounded-[3px] border border-hairline bg-paper px-3 text-sm text-ink outline-none transition-colors focus:border-navy"
              aria-label="Filter by jurisdiction"
            >
              <option value="">All jurisdictions</option>
              {jurisdictionOptions.map((option) => (
                <option key={option} value={option}>
                  {JURISDICTION_NAMES[option] ?? option}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {state === "loading" && (
            <p className="px-8 py-8 text-sm text-muted-ink">Loading regimes…</p>
          )}
          {state === "error" && (
            <p className="px-8 py-8 text-sm text-muted-ink">
              Unable to load regimes. Check the API is running.
            </p>
          )}
          {state === "ready" && regimes.length === 0 && (
            <p className="px-8 py-8 text-sm text-muted-ink">
              No regimes found in the dataset.
            </p>
          )}
          {state === "ready" && regimes.length > 0 && visibleRegimes.length === 0 && (
            <p className="px-8 py-8 text-sm text-muted-ink">
              No regimes match the current filters.
            </p>
          )}
          {state === "ready" && visibleRegimes.length > 0 && (
            <ul className="mx-auto max-w-[860px] px-8 py-2">
              {visibleRegimes.map((regime) => (
                <li key={regime.id} className="border-b border-hairline">
                  <Link
                    to="/regimes/$regimeId"
                    params={{ regimeId: regime.id }}
                    className="group flex items-center gap-4 py-4 transition-colors hover:bg-secondary"
                  >
                    <div className="min-w-0 flex-1 px-2">
                      <h2 className="flex items-center gap-2 font-serif text-[0.9375rem] font-medium leading-snug text-ink">
                        <span className="min-w-0">{regime.name}</span>
                        <JurisdictionTag id={regime.id} />
                      </h2>
                      {regime.short_description && (
                        <p className="mt-0.5 text-xs leading-relaxed text-muted-ink">
                          {regime.short_description}
                        </p>
                      )}
                    </div>
                    <ChevronRight
                      className="h-4 w-4 flex-shrink-0 text-muted-ink transition-transform group-hover:translate-x-0.5"
                      aria-hidden="true"
                    />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </SidebarLayout>
  );
}
