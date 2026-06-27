import { useState, type ReactNode } from "react";
import { ExternalLink, RefreshCw } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AppHeader } from "./AppHeader";
import { DossierReferenceText } from "./DossierReferenceText";
import { JurisdictionTag } from "./JurisdictionTag";
import type { Regime } from "@/lib/regimes";
import { fetchRegime, refreshRegulatoryGuidance, sendChat } from "@/lib/api";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  suggestions?: string[];
}

interface WorkspaceScreenProps {
  jurisdictions: string[];
  topic: string;
  regimes: Regime[];
  regimeLoadState: "idle" | "loading" | "ready" | "error";
  onToggleRegime: (id: string) => void;
  onAddRegime: (name: string, description: string) => void;
  onRemoveRegime: (id: string) => void;
  note: string;
  onNoteChange: (value: string) => void;
  onNewSession: () => void;
}

function Placeholder() {
  return <span className="italic text-muted-ink">Not yet documented.</span>;
}

function formatUpdatedAt(value?: string | null) {
  if (!value) return "Never refreshed";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Last updated date unavailable";
  return `Last updated ${new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date)}`;
}

function InlineField({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="grid gap-2 border-t border-hairline py-4 sm:grid-cols-[9rem_minmax(0,1fr)]">
      <p className="eyebrow">{label}</p>
      <div className="text-sm leading-relaxed text-ink">{children}</div>
    </div>
  );
}

function RegulatoryGuidanceSection({
  regime,
  refreshing,
  refreshError,
  onRefresh,
}: {
  regime: Regime;
  refreshing: boolean;
  refreshError: boolean;
  onRefresh: () => void;
}) {
  const rows = regime.regulatory_guidance ?? [];

  return (
    <div className="border-t border-hairline py-4">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Regulatory Guidance</p>
          <p className="mt-1 text-xs text-muted-ink">
            {formatUpdatedAt(regime.regulatory_guidance_updated_at)}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-1.5 rounded-[3px] border border-hairline bg-paper px-2.5 py-1.5 text-xs font-medium text-navy transition-colors hover:bg-secondary disabled:cursor-wait disabled:opacity-60"
        >
          <RefreshCw
            className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          {refreshing ? "Refreshing" : "Refresh"}
        </button>
      </div>

      {refreshError && (
        <p className="mb-3 text-xs text-destructive">
          Unable to refresh regulatory guidance.
        </p>
      )}

      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-[640px] border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-hairline text-muted-ink">
                <th className="py-2 pr-4 font-medium">Regulator</th>
                <th className="py-2 pr-4 font-medium">Document / Policy</th>
                <th className="py-2 pr-4 font-medium">Description</th>
                <th className="py-2 font-medium">Official Link</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={`${row.regulator}-${row.title}-${i}`} className="border-b border-hairline/70 align-top">
                  <td className="py-3 pr-4 font-medium text-ink">{row.regulator}</td>
                  <td className="py-3 pr-4 text-ink">{row.title}</td>
                  <td className="py-3 pr-4 leading-relaxed text-ink">
                    <DossierReferenceText text={row.description} regime={regime} />
                  </td>
                  <td className="py-3">
                    <a
                      href={row.official_link}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 text-navy underline decoration-navy/30 underline-offset-2 transition-colors hover:decoration-navy"
                    >
                      Source
                      <ExternalLink className="h-3 w-3" aria-hidden="true" />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Placeholder />
      )}
    </div>
  );
}

function InlineRegimeDossier({
  id,
  regime,
  status,
  refreshingRegulatoryGuidance,
  regulatoryGuidanceError,
  onRefreshRegulatoryGuidance,
}: {
  id: string;
  regime: Regime;
  status: "loading" | "ready" | "error";
  refreshingRegulatoryGuidance: boolean;
  regulatoryGuidanceError: boolean;
  onRefreshRegulatoryGuidance: () => void;
}) {
  return (
    <div id={id} className="border-t border-hairline bg-secondary/30 px-6 py-5">
      {status === "loading" && (
        <p className="text-sm text-muted-ink">Loading dossier...</p>
      )}
      {status === "error" && (
        <p className="text-sm text-muted-ink">
          Unable to load the dossier for this regime.
        </p>
      )}
      {status === "ready" && (
        <div>
          <InlineField label="Summary">
            {regime.summary ? (
              <p className="whitespace-pre-line">{regime.summary}</p>
            ) : (
              <Placeholder />
            )}
          </InlineField>

          <InlineField label="Scope">
            {regime.scope ? (
              <DossierReferenceText text={regime.scope} regime={regime} />
            ) : (
              <Placeholder />
            )}
          </InlineField>

          <InlineField label="Process">
            {regime.process ? (
              <DossierReferenceText text={regime.process} regime={regime} />
            ) : (
              <Placeholder />
            )}
          </InlineField>

          <InlineField label="Consequence">
            {regime.consequence ? (
              <DossierReferenceText text={regime.consequence} regime={regime} />
            ) : (
              <Placeholder />
            )}
          </InlineField>

          <InlineField label="Obligations">
            {regime.obligations.length > 0 ? (
              <ul className="space-y-2">
                {regime.obligations.map((o, i) => (
                  <li key={i} className="flex gap-2.5">
                    <span
                      className="mt-2 h-1 w-1 flex-shrink-0 rounded-full bg-ink"
                      aria-hidden="true"
                    />
                    <span>
                      {o.text}
                      {o.reference && (
                        <>
                          {" "}
                          {o.url ? (
                            <a
                              href={o.url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-navy underline decoration-navy/30 underline-offset-2 transition-colors hover:decoration-navy"
                            >
                              ({o.reference})
                            </a>
                          ) : (
                            <span className="text-muted-ink">({o.reference})</span>
                          )}
                        </>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <Placeholder />
            )}
          </InlineField>

          <InlineField label="Guidance">
            {regime.guidance ? (
              <blockquote className="border-l-2 border-navy py-1 pl-4">
                <DossierReferenceText text={regime.guidance} regime={regime} />
              </blockquote>
            ) : (
              <Placeholder />
            )}
          </InlineField>

          <RegulatoryGuidanceSection
            regime={regime}
            refreshing={refreshingRegulatoryGuidance}
            refreshError={regulatoryGuidanceError}
            onRefresh={onRefreshRegulatoryGuidance}
          />
        </div>
      )}
    </div>
  );
}

export function WorkspaceScreen({
  jurisdictions,
  topic,
  regimes,
  regimeLoadState,
  onToggleRegime,
  onAddRegime,
  onRemoveRegime,
  note,
  onNoteChange,
  onNewSession,
}: WorkspaceScreenProps) {
  const jurisdictionLabel =
    jurisdictions.length <= 1
      ? jurisdictions[0] ?? ""
      : `${jurisdictions.slice(0, -1).join(", ")} and ${jurisdictions.at(-1)}`;
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: "user",
      text: `What regulatory regimes apply to ${topic} in the ${jurisdictionLabel}?`,
    },
    {
      id: 2,
      role: "assistant",
      text: `For ${topic} in the ${jurisdictionLabel}, the analysis centres on platform duties, the handling of personal data, and the institutional powers behind enforcement. The relevant statutes operate together rather than in isolation, so obligations frequently overlap. I've identified the following regimes that may apply:`,
    },
  ]);
  const [draft, setDraft] = useState("");
  const [thinking, setThinking] = useState(false);
  const [expandedRegimeId, setExpandedRegimeId] = useState<string | null>(null);
  const [dossiers, setDossiers] = useState<Record<string, Regime>>({});
  const [dossierStatus, setDossierStatus] = useState<
    Record<string, "loading" | "ready" | "error">
  >({});
  const [refreshingRegulatoryGuidance, setRefreshingRegulatoryGuidance] = useState<
    Record<string, boolean>
  >({});
  const [regulatoryGuidanceErrors, setRegulatoryGuidanceErrors] = useState<
    Record<string, boolean>
  >({});

  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  async function submitQuery(raw: string) {
    const text = raw.trim();
    if (!text || thinking) return;
    setMessages((m) => [...m, { id: Date.now(), role: "user", text }]);
    setDraft("");
    const confirmedIds = regimes.filter((r) => r.confirmed).map((r) => r.id);
    const ids = confirmedIds.length > 0 ? confirmedIds : regimes.map((r) => r.id);
    setThinking(true);
    try {
      const { answer, suggestions } = await sendChat(text, ids);
      setMessages((m) => [
        ...m,
        { id: Date.now() + 1, role: "assistant", text: answer, suggestions },
      ]);
    } catch {
      setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant",
        text: "Sorry — DORA is unavailable." }]);
    } finally {
      setThinking(false);
    }
  }

  function handleSend(e: React.FormEvent) {
    e.preventDefault();
    submitQuery(draft);
  }

  function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    onAddRegime(name, newDesc.trim());
    setNewName("");
    setNewDesc("");
    setAdding(false);
  }

  async function handleToggleDossier(regime: Regime) {
    const next = expandedRegimeId === regime.id ? null : regime.id;
    setExpandedRegimeId(next);
    if (!next || dossiers[regime.id] || dossierStatus[regime.id] === "loading") return;
    setDossierStatus((s) => ({ ...s, [regime.id]: "loading" }));
    try {
      const data = await fetchRegime(regime.id);
      setDossiers((d) => ({ ...d, [regime.id]: { ...regime, ...data } }));
      setDossierStatus((s) => ({ ...s, [regime.id]: "ready" }));
    } catch {
      setDossierStatus((s) => ({ ...s, [regime.id]: "error" }));
    }
  }

  async function handleRefreshRegulatoryGuidance(regime: Regime) {
    setRefreshingRegulatoryGuidance((s) => ({ ...s, [regime.id]: true }));
    setRegulatoryGuidanceErrors((s) => ({ ...s, [regime.id]: false }));
    try {
      const data = await refreshRegulatoryGuidance(regime.id);
      setDossiers((d) => ({
        ...d,
        [regime.id]: { ...regime, ...d[regime.id], ...data },
      }));
      setDossierStatus((s) => ({ ...s, [regime.id]: "ready" }));
    } catch {
      setRegulatoryGuidanceErrors((s) => ({ ...s, [regime.id]: true }));
    } finally {
      setRefreshingRegulatoryGuidance((s) => ({ ...s, [regime.id]: false }));
    }
  }

  function handleRemove(id: string) {
    if (expandedRegimeId === id) setExpandedRegimeId(null);
    onRemoveRegime(id);
  }

  return (
    <div className="flex h-screen flex-col bg-paper">
      <AppHeader
        right={
          <button
            onClick={onNewSession}
            className="text-[0.6875rem] uppercase tracking-[0.12em] text-muted-ink transition-colors hover:text-navy"
          >
            New session
          </button>
        }
      />

      <div className="grid flex-1 grid-cols-1 overflow-hidden md:grid-cols-[45fr_55fr]">
        {/* Left — Chat */}
        <section className="flex min-h-0 flex-col border-b border-hairline md:border-b-0 md:border-r">
          <div className="border-b border-hairline px-6 py-4">
            <h2 className="font-serif text-base font-semibold text-ink">Chat</h2>
            <p className="mt-0.5 text-xs text-muted-ink">
              {topic} · {jurisdictionLabel}
            </p>
          </div>

          <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
            {messages.map((m, i) => {
              const isLast = i === messages.length - 1;
              return (
                <div key={m.id}>
                  <p className="eyebrow mb-1.5">{m.role === "user" ? "You" : "DORA"}</p>
                  {m.role === "assistant" ? (
                    <div className="prose-chat text-sm leading-relaxed text-ink">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
                    </div>
                  ) : (
                    <p className="text-sm leading-relaxed text-ink">{m.text}</p>
                  )}
                  {isLast &&
                    !thinking &&
                    m.role === "assistant" &&
                    (m.suggestions?.length ?? 0) > 0 && (
                      <div className="mt-3">
                        <p className="eyebrow mb-1.5">Suggested next steps</p>
                        <div className="flex flex-col items-start gap-1.5">
                          {m.suggestions!.map((s, si) => (
                            <button
                              key={si}
                              type="button"
                              onClick={() => submitQuery(s)}
                              className="rounded-full border border-hairline bg-paper px-3 py-1.5 text-left text-xs text-navy transition-colors hover:border-navy hover:bg-secondary"
                            >
                              {s}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                </div>
              );
            })}
            {thinking && (
              <div>
                <p className="eyebrow mb-1.5">DORA</p>
                <div className="flex items-center gap-1.5 py-1" aria-label="DORA is thinking">
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-ink [animation-delay:-0.3s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-ink [animation-delay:-0.15s]" />
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-ink" />
                </div>
              </div>
            )}
          </div>

          <form onSubmit={handleSend} className="border-t border-hairline p-4">
            <div className="flex items-center gap-2 rounded-[3px] border border-hairline bg-paper px-3 py-1.5 focus-within:border-navy">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                disabled={thinking}
                placeholder={thinking ? "Waiting for a response..." : "Ask a follow-up..."}
                className="flex-1 bg-transparent py-1 text-sm text-ink outline-none placeholder:text-muted-ink disabled:opacity-60"
              />
              <button
                type="submit"
                aria-label="Send message"
                disabled={thinking}
                className="flex h-7 w-7 items-center justify-center rounded-[3px] bg-navy text-navy-foreground transition-colors hover:bg-[#16304e] disabled:opacity-50"
              >
                <svg
                  className="h-4 w-4"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  aria-hidden="true"
                >
                  <path d="M8 13V3M8 3l-4 4M8 3l4 4" />
                </svg>
              </button>
            </div>
          </form>
        </section>

        {/* Right — Relevant regimes */}
        <section className="flex min-h-0 flex-col">
          <div className="flex items-center justify-between gap-2 border-b border-hairline px-6 py-4">
            <div className="flex items-center gap-2">
              <h2 className="font-serif text-base font-semibold text-ink">Relevant regimes</h2>
              <span
                className="group relative flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-muted-ink text-[0.625rem] font-medium text-muted-ink"
                tabIndex={0}
              >
                i
                <span className="pointer-events-none absolute left-1/2 top-6 z-10 w-56 -translate-x-1/2 rounded-[3px] border border-hairline bg-paper px-3 py-2 text-xs leading-snug text-ink opacity-0 shadow-sm transition-opacity group-hover:opacity-100 group-focus:opacity-100">
                  Regimes the system has identified as potentially applicable to your query
                </span>
              </span>
            </div>
            <button
              type="button"
              onClick={() => setAdding((v) => !v)}
              className="text-[0.6875rem] uppercase tracking-[0.12em] text-navy transition-colors hover:underline"
            >
              {adding ? "Cancel" : "+ Add regime"}
            </button>
          </div>

          {adding && (
            <form onSubmit={handleAdd} className="border-b border-hairline bg-secondary/40 px-6 py-4">
              <p className="eyebrow mb-2">Add a regime</p>
              <input
                autoFocus
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Regime name, e.g. Digital Markets Act"
                className="mb-2 w-full rounded-[3px] border border-hairline bg-paper px-3 py-2 font-serif text-sm text-ink outline-none transition-colors placeholder:font-sans placeholder:text-muted-ink focus:border-navy"
              />
              <input
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="One-line description (optional)"
                className="mb-3 w-full rounded-[3px] border border-hairline bg-paper px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted-ink focus:border-navy"
              />
              <div className="flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setAdding(false);
                    setNewName("");
                    setNewDesc("");
                  }}
                  className="rounded-[3px] border border-hairline px-3 py-1.5 text-xs text-ink transition-colors hover:bg-paper"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="rounded-[3px] bg-navy px-3 py-1.5 text-xs font-medium text-navy-foreground transition-colors hover:bg-[#16304e]"
                >
                  Add regime
                </button>
              </div>
            </form>
          )}

          <div className="flex-1 overflow-y-auto">
            <ul aria-live="polite">
              {regimeLoadState === "loading" && (
                <li className="px-6 py-8 text-sm text-muted-ink">
                  Finding relevant regimes...
                </li>
              )}
              {regimeLoadState === "error" && (
                <li className="px-6 py-8 text-sm text-muted-ink">
                  Unable to load regimes. Check the API is running, then start a new session.
                </li>
              )}
              {regimeLoadState !== "loading" && regimeLoadState !== "error" && regimes.length === 0 && (
                <li className="px-6 py-8 text-sm text-muted-ink">
                  No regimes in this session. Use “+ Add regime” to add one.
                </li>
              )}
              {regimes.map((regime) => (
                <li key={regime.id} className="border-b border-hairline">
                  <div className="group/row flex items-start gap-3.5 px-6 py-4 transition-colors hover:bg-secondary">
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={regime.confirmed}
                      aria-label={`Confirm ${regime.name} as relevant`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onToggleRegime(regime.id);
                      }}
                      className={`mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-[2px] border transition-colors ${
                        regime.confirmed
                          ? "border-navy bg-navy text-navy-foreground"
                          : "border-muted-ink bg-paper"
                      }`}
                    >
                      {regime.confirmed && (
                        <svg
                          className="h-3 w-3"
                          viewBox="0 0 12 12"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          aria-hidden="true"
                        >
                          <path d="M2.5 6.5l2.5 2.5 4.5-5" />
                        </svg>
                      )}
                    </button>
                    <button
                      type="button"
                      aria-expanded={expandedRegimeId === regime.id}
                      aria-controls={`regime-panel-${regime.id}`}
                      onClick={() => handleToggleDossier(regime)}
                      className="min-w-0 flex-1 text-left"
                    >
                      <h3 className="flex items-center gap-2 font-serif text-[0.9375rem] font-medium leading-snug text-ink">
                        <span className="min-w-0">{regime.name}</span>
                        <JurisdictionTag id={regime.id} />
                      </h3>
                      {regime.shortDescription && (
                        <p className="mt-0.5 text-xs leading-relaxed text-muted-ink">
                          {regime.shortDescription}
                        </p>
                      )}
                    </button>
                    <div className="flex flex-shrink-0 items-center gap-2">
                      <button
                        type="button"
                        aria-label={`Remove ${regime.name}`}
                        title="Remove — not relevant"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleRemove(regime.id);
                        }}
                        className="flex h-6 w-6 items-center justify-center rounded-[2px] text-muted-ink opacity-0 transition-all hover:bg-paper hover:text-destructive focus:opacity-100 group-hover/row:opacity-100"
                      >
                        <svg
                          className="h-3.5 w-3.5"
                          viewBox="0 0 14 14"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          aria-hidden="true"
                        >
                          <path d="M3.5 3.5l7 7M10.5 3.5l-7 7" />
                        </svg>
                      </button>
                      <svg
                        className={`h-3.5 w-3.5 text-muted-ink transition-transform ${
                          expandedRegimeId === regime.id ? "rotate-90" : ""
                        }`}
                        viewBox="0 0 16 16"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        aria-hidden="true"
                      >
                        <path d="M6 4l4 4-4 4" />
                      </svg>
                    </div>
                  </div>
                  {expandedRegimeId === regime.id && (
                    <InlineRegimeDossier
                      id={`regime-panel-${regime.id}`}
                      regime={dossiers[regime.id] ?? regime}
                      status={dossierStatus[regime.id] ?? "loading"}
                      refreshingRegulatoryGuidance={!!refreshingRegulatoryGuidance[regime.id]}
                      regulatoryGuidanceError={!!regulatoryGuidanceErrors[regime.id]}
                      onRefreshRegulatoryGuidance={() => handleRefreshRegulatoryGuidance(
                        dossiers[regime.id] ?? regime,
                      )}
                    />
                  )}
                </li>
              ))}
            </ul>

            <div className="px-6 py-5">
              <p className="eyebrow mb-2">Session note</p>
              <textarea
                value={note}
                onChange={(e) => onNoteChange(e.target.value)}
                placeholder="Add a note about scope or exclusions..."
                rows={3}
                className="w-full resize-y rounded-[3px] border border-hairline bg-paper px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-muted-ink focus:border-navy"
              />
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
