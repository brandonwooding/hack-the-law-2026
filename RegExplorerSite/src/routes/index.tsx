import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { SetupScreen } from "@/components/research/SetupScreen";
import { WorkspaceScreen } from "@/components/research/WorkspaceScreen";
import { SidebarLayout } from "@/components/research/SidebarLayout";
import { seedRegimes, type Regime } from "@/lib/regimes";
import { fetchRegimes } from "@/lib/api";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Regime — Cross-Jurisdiction Legal Research" },
      {
        name: "description",
        content:
          "A precise legal research instrument for checking regulatory obligations across jurisdictions.",
      },
    ],
  }),
  component: Index,
});

type View = "setup" | "workspace";
type RegimeLoadState = "idle" | "loading" | "ready" | "error";

function Index() {
  const [view, setView] = useState<View>("setup");
  const [jurisdiction, setJurisdiction] = useState("");
  const [topic, setTopic] = useState("");
  const [regimes, setRegimes] = useState<Regime[]>(seedRegimes);
  const [regimeLoadState, setRegimeLoadState] = useState<RegimeLoadState>("idle");
  const [note, setNote] = useState("");

  async function handleStart(j: string, t: string) {
    setJurisdiction(j);
    setTopic(t);
    setNote("");
    setRegimes([]);
    setRegimeLoadState("loading");
    setView("workspace");
    try {
      const cards = await fetchRegimes(t, j);
      setRegimes(cards.map((c) => ({
        id: c.id,
        name: c.name,
        shortDescription: c.short_description ?? "",
        confirmed: false,
        summary: "", scope: "", process: "", consequence: "",
        obligations: [], guidance: "",
        regulatory_guidance: [],
        regulatory_guidance_updated_at: null,
      })));
      setRegimeLoadState("ready");
    } catch {
      setRegimes([]);
      setRegimeLoadState("error");
    }
  }

  function handleToggleRegime(id: string) {
    setRegimes((rs) =>
      rs.map((r) => (r.id === id ? { ...r, confirmed: !r.confirmed } : r)),
    );
  }

  function handleAddRegime(name: string, description: string) {
    const id = `custom-${Date.now()}`;
    setRegimes((rs) => [
      ...rs,
      {
        id,
        name,
        shortDescription: description,
        confirmed: true,
        summary: "",
        scope: "",
        process: "",
        consequence: "",
        obligations: [],
        guidance: "",
        regulatory_guidance: [],
        regulatory_guidance_updated_at: null,
      },
    ]);
  }

  function handleRemoveRegime(id: string) {
    setRegimes((rs) => rs.filter((r) => r.id !== id));
  }


  function handleNewSession() {
    setView("setup");
    setJurisdiction("");
    setTopic("");
    setRegimeLoadState("idle");
  }

  if (view === "setup") {
    return (
      <SidebarLayout>
        <SetupScreen onStart={handleStart} />
      </SidebarLayout>
    );
  }

  return (
    <SidebarLayout>
      <WorkspaceScreen
        jurisdiction={jurisdiction}
        topic={topic}
        regimes={regimes}
        regimeLoadState={regimeLoadState}
        onToggleRegime={handleToggleRegime}
        onAddRegime={handleAddRegime}
        onRemoveRegime={handleRemoveRegime}
        note={note}
        onNoteChange={setNote}
        onNewSession={handleNewSession}
      />
    </SidebarLayout>
  );
}
