import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { SetupScreen } from "@/components/research/SetupScreen";
import { WorkspaceScreen } from "@/components/research/WorkspaceScreen";
import { RegimeDetailScreen } from "@/components/research/RegimeDetailScreen";
import { seedRegimes, type Regime } from "@/lib/regimes";

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

type View = "setup" | "workspace" | "detail";

function Index() {
  const [view, setView] = useState<View>("setup");
  const [jurisdiction, setJurisdiction] = useState("");
  const [topic, setTopic] = useState("");
  const [regimes, setRegimes] = useState<Regime[]>(seedRegimes);
  const [note, setNote] = useState("");
  const [activeRegimeId, setActiveRegimeId] = useState<string | null>(null);

  function handleStart(j: string, t: string) {
    setJurisdiction(j);
    setTopic(t);
    setRegimes(seedRegimes.map((r) => ({ ...r })));
    setNote("");
    setView("workspace");
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
      },
    ]);
  }

  function handleRemoveRegime(id: string) {
    setRegimes((rs) => rs.filter((r) => r.id !== id));
    setActiveRegimeId((current) => (current === id ? null : current));
  }


  function handleNewSession() {
    setView("setup");
    setJurisdiction("");
    setTopic("");
    setActiveRegimeId(null);
  }

  const activeRegime = regimes.find((r) => r.id === activeRegimeId) ?? null;

  if (view === "setup") {
    return <SetupScreen onStart={handleStart} />;
  }

  if (view === "detail" && activeRegime) {
    return (
      <RegimeDetailScreen regime={activeRegime} onBack={() => setView("workspace")} />
    );
  }

  return (
    <WorkspaceScreen
      jurisdiction={jurisdiction}
      topic={topic}
      regimes={regimes}
      onToggleRegime={handleToggleRegime}
      onOpenRegime={(id) => {
        setActiveRegimeId(id);
        setView("detail");
      }}
      onAddRegime={handleAddRegime}
      onRemoveRegime={handleRemoveRegime}
      note={note}
      onNoteChange={setNote}
      onNewSession={handleNewSession}
    />
  );
}
