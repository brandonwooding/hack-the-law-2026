import { useState } from "react";
import { AppHeader } from "./AppHeader";
import type { Regime } from "@/lib/regimes";
import { sendChat } from "@/lib/api";

interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
}

interface WorkspaceScreenProps {
  jurisdiction: string;
  topic: string;
  regimes: Regime[];
  onToggleRegime: (id: string) => void;
  onOpenRegime: (id: string) => void;
  onAddRegime: (name: string, description: string) => void;
  onRemoveRegime: (id: string) => void;
  note: string;
  onNoteChange: (value: string) => void;
  onNewSession: () => void;
}

export function WorkspaceScreen({
  jurisdiction,
  topic,
  regimes,
  onToggleRegime,
  onOpenRegime,
  onAddRegime,
  onRemoveRegime,
  note,
  onNoteChange,
  onNewSession,
}: WorkspaceScreenProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: 1,
      role: "user",
      text: `What regulatory regimes apply to ${topic} in the ${jurisdiction}?`,
    },
    {
      id: 2,
      role: "assistant",
      text: `For ${topic} in the ${jurisdiction}, the analysis centres on platform duties, the handling of personal data, and the institutional powers behind enforcement. The relevant statutes operate together rather than in isolation, so obligations frequently overlap. I've identified the following regimes that may apply:`,
    },
  ]);
  const [draft, setDraft] = useState("");

  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setMessages((m) => [...m, { id: Date.now(), role: "user", text }]);
    setDraft("");
    const ids = regimes.filter((r) => r.confirmed).map((r) => r.id);
    try {
      const { answer } = await sendChat(text, ids);
      setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant", text: answer }]);
    } catch {
      setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant",
        text: "Sorry — the assistant is unavailable." }]);
    }
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
              {topic} · {jurisdiction}
            </p>
          </div>

          <div className="flex-1 space-y-6 overflow-y-auto px-6 py-6">
            {messages.map((m) => (
              <div key={m.id}>
                <p className="eyebrow mb-1.5">{m.role === "user" ? "You" : "Assistant"}</p>
                <p className="text-sm leading-relaxed text-ink">{m.text}</p>
              </div>
            ))}
          </div>

          <form onSubmit={handleSend} className="border-t border-hairline p-4">
            <div className="flex items-center gap-2 rounded-[3px] border border-hairline bg-paper px-3 py-1.5 focus-within:border-navy">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder="Ask a follow-up..."
                className="flex-1 bg-transparent py-1 text-sm text-ink outline-none placeholder:text-muted-ink"
              />
              <button
                type="submit"
                aria-label="Send message"
                className="flex h-7 w-7 items-center justify-center rounded-[3px] bg-navy text-navy-foreground transition-colors hover:bg-[#16304e]"
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
            <ul>
              {regimes.length === 0 && (
                <li className="px-6 py-8 text-sm text-muted-ink">
                  No regimes in this session. Use “+ Add regime” to add one.
                </li>
              )}
              {regimes.map((regime) => (
                <li key={regime.id} className="border-b border-hairline">
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => onOpenRegime(regime.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        onOpenRegime(regime.id);
                      }
                    }}
                    className="group/row flex cursor-pointer items-start gap-3.5 px-6 py-4 transition-colors hover:bg-secondary"
                  >
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
                    <div className="min-w-0 flex-1">
                      <h3 className="font-serif text-[0.9375rem] font-medium leading-snug text-ink">
                        {regime.name}
                      </h3>
                      {regime.shortDescription && (
                        <p className="mt-0.5 text-xs leading-relaxed text-muted-ink">
                          {regime.shortDescription}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-shrink-0 items-center gap-2">
                      <button
                        type="button"
                        aria-label={`Remove ${regime.name}`}
                        title="Remove — not relevant"
                        onClick={(e) => {
                          e.stopPropagation();
                          onRemoveRegime(regime.id);
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
                        className="h-3.5 w-3.5 text-muted-ink"
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
