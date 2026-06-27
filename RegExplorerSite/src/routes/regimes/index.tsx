import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ChevronRight } from "lucide-react";
import { SidebarLayout } from "@/components/research/SidebarLayout";
import { JurisdictionTag } from "@/components/research/JurisdictionTag";
import { fetchAllRegimes, type RegimeCard } from "@/lib/api";

export const Route = createFileRoute("/regimes/")({
  head: () => ({
    meta: [{ title: "Regimes — Cross-Jurisdiction Legal Research" }],
  }),
  component: RegimesIndex,
});

type LoadState = "loading" | "ready" | "error";

function RegimesIndex() {
  const [regimes, setRegimes] = useState<RegimeCard[]>([]);
  const [state, setState] = useState<LoadState>("loading");

  useEffect(() => {
    let active = true;
    setState("loading");
    fetchAllRegimes()
      .then((rs) => {
        if (!active) return;
        setRegimes(rs);
        setState("ready");
      })
      .catch(() => active && setState("error"));
    return () => {
      active = false;
    };
  }, []);

  return (
    <SidebarLayout>
      <div className="flex h-full flex-col">
        <div className="border-b border-hairline px-8 py-5">
          <h1 className="font-serif text-xl font-semibold tracking-tight text-ink">
            Regimes
          </h1>
          <p className="mt-0.5 text-xs text-muted-ink">
            Top-level regulatory regimes in the dataset
          </p>
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
          {state === "ready" && regimes.length > 0 && (
            <ul className="mx-auto max-w-[860px] px-8 py-2">
              {regimes.map((regime) => (
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
