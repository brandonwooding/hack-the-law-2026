import { useEffect, useState } from "react";
import { ExternalLink, RefreshCw, Pencil } from "lucide-react";
import type { Regime } from "@/lib/regimes";
import { fetchRegime, refreshRegulatoryGuidance, saveRegime } from "@/lib/api";

interface RegimeDetailScreenProps {
  regime: Regime;
  onBack: () => void;
}

// Prose fields the user may edit. Obligations and regulatory guidance are
// deliberately excluded — they stay read-only.
const EDITABLE_FIELDS = [
  "summary",
  "scope",
  "process",
  "consequence",
  "guidance",
] as const;
type EditableField = (typeof EDITABLE_FIELDS)[number];
type Draft = Record<EditableField, string>;

function draftFrom(regime: Regime): Draft {
  return {
    summary: regime.summary ?? "",
    scope: regime.scope ?? "",
    process: regime.process ?? "",
    consequence: regime.consequence ?? "",
    guidance: regime.guidance ?? "",
  };
}

function Placeholder() {
  return <span className="text-muted-ink italic">Not yet documented.</span>;
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

function EditTextarea({
  value,
  onChange,
  rows = 5,
}: {
  value: string;
  onChange: (v: string) => void;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      rows={rows}
      className="w-full resize-y rounded-[3px] border border-hairline bg-paper px-3 py-2 text-[0.9375rem] leading-relaxed text-ink outline-none transition-colors placeholder:text-muted-ink focus:border-navy"
    />
  );
}

export function RegimeDetailScreen({ regime, onBack }: RegimeDetailScreenProps) {
  const [data, setData] = useState(regime);
  const [loaded, setLoaded] = useState(false);
  const [refreshingRegulatoryGuidance, setRefreshingRegulatoryGuidance] = useState(false);
  const [regulatoryGuidanceError, setRegulatoryGuidanceError] = useState(false);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Draft>(draftFrom(regime));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(false);

  useEffect(() => {
    fetchRegime(regime.id)
      .then((d) => setData((current) => ({ ...current, ...d })))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, [regime.id]);

  async function handleRefreshRegulatoryGuidance() {
    setRefreshingRegulatoryGuidance(true);
    setRegulatoryGuidanceError(false);
    try {
      const refreshed = await refreshRegulatoryGuidance(regime.id);
      setData((current) => ({ ...current, ...refreshed }));
    } catch {
      setRegulatoryGuidanceError(true);
    } finally {
      setRefreshingRegulatoryGuidance(false);
    }
  }

  function startEditing() {
    setDraft(draftFrom(data));
    setSaveError(false);
    setEditing(true);
  }

  function cancelEditing() {
    setEditing(false);
    setSaveError(false);
  }

  async function handleSave() {
    setSaving(true);
    setSaveError(false);
    try {
      const updated = await saveRegime(regime.id, draft);
      setData((current) => ({ ...current, ...updated }));
      setEditing(false);
    } catch {
      setSaveError(true);
    } finally {
      setSaving(false);
    }
  }

  function setField(field: EditableField, value: string) {
    setDraft((d) => ({ ...d, [field]: value }));
  }

  return (
    <div className="flex h-full flex-col bg-paper">
      <header className="flex items-center justify-between border-b border-hairline px-6 py-3.5">
        <button
          onClick={onBack}
          className="text-sm text-navy transition-colors hover:underline"
        >
          ← Back to regimes
        </button>
        {editing ? (
          <div className="flex items-center gap-2">
            {saveError && (
              <span className="text-xs text-destructive">Couldn’t save.</span>
            )}
            <button
              type="button"
              onClick={cancelEditing}
              disabled={saving}
              className="rounded-[3px] border border-hairline px-3 py-1.5 text-xs text-ink transition-colors hover:bg-secondary disabled:opacity-60"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              className="rounded-[3px] bg-navy px-3 py-1.5 text-xs font-medium text-navy-foreground transition-colors hover:bg-[#16304e] disabled:cursor-wait disabled:opacity-60"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        ) : (
          loaded && (
            <button
              type="button"
              onClick={startEditing}
              className="inline-flex items-center gap-1.5 rounded-[3px] border border-hairline bg-paper px-2.5 py-1.5 text-xs font-medium text-navy transition-colors hover:bg-secondary"
            >
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
              Edit
            </button>
          )
        )}
      </header>

      <main className="flex-1 overflow-y-auto px-6 py-10">
        <div className="mx-auto max-w-[720px]">
          <h1 className="font-serif text-3xl font-semibold leading-tight tracking-tight text-ink">
            {data.name || (loaded ? regime.id : "Loading…")}
          </h1>
          <hr className="my-6 border-0 border-t border-hairline" />

          <section>
            <p className="eyebrow mb-2">Summary</p>
            {editing ? (
              <EditTextarea
                value={draft.summary}
                onChange={(v) => setField("summary", v)}
              />
            ) : (
              <p className="text-[0.9375rem] leading-relaxed text-ink">
                {data.summary || <Placeholder />}
              </p>
            )}
          </section>

          <hr className="my-7 border-0 border-t border-hairline" />

          <table className="w-full border-collapse text-left">
            <tbody>
              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Scope
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {editing ? (
                    <EditTextarea
                      value={draft.scope}
                      onChange={(v) => setField("scope", v)}
                    />
                  ) : (
                    data.scope || <Placeholder />
                  )}
                </td>
              </tr>

              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Regulatory process
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {editing ? (
                    <EditTextarea
                      value={draft.process}
                      onChange={(v) => setField("process", v)}
                    />
                  ) : (
                    data.process || <Placeholder />
                  )}
                </td>
              </tr>

              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Consequence
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {editing ? (
                    <EditTextarea
                      value={draft.consequence}
                      onChange={(v) => setField("consequence", v)}
                    />
                  ) : (
                    data.consequence || <Placeholder />
                  )}
                </td>
              </tr>

              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Obligations
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {data.obligations.length > 0 ? (
                    <ul className="space-y-3">
                      {data.obligations.map((o, i) => (
                        <li key={i} className="flex gap-3">
                          <span
                            className="mt-2 h-1 w-1 flex-shrink-0 rounded-full bg-ink"
                            aria-hidden="true"
                          />
                          <span>
                            {o.text}{" "}
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
                              o.reference && (
                                <span className="text-muted-ink">({o.reference})</span>
                              )
                            )}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <Placeholder />
                  )}
                </td>
              </tr>

              <tr className="border-t border-b border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Guidance
                </th>
                <td className="py-5">
                  {editing ? (
                    <EditTextarea
                      value={draft.guidance}
                      onChange={(v) => setField("guidance", v)}
                    />
                  ) : data.guidance ? (
                    <blockquote className="border-l-2 border-navy bg-secondary/40 py-1 pl-4">
                      <p className="text-[0.9375rem] leading-relaxed text-ink">{data.guidance}</p>
                    </blockquote>
                  ) : (
                    <p className="text-[0.9375rem] leading-relaxed">
                      <Placeholder />
                    </p>
                  )}
                </td>
              </tr>

              <tr className="border-b border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Regulatory Guidance
                </th>
                <td className="py-5">
                  <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                    <p className="text-xs text-muted-ink">
                      {formatUpdatedAt(data.regulatory_guidance_updated_at)}
                    </p>
                    <button
                      type="button"
                      onClick={handleRefreshRegulatoryGuidance}
                      disabled={refreshingRegulatoryGuidance || editing}
                      className="inline-flex items-center gap-1.5 rounded-[3px] border border-hairline bg-paper px-2.5 py-1.5 text-xs font-medium text-navy transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <RefreshCw
                        className={`h-3.5 w-3.5 ${refreshingRegulatoryGuidance ? "animate-spin" : ""}`}
                        aria-hidden="true"
                      />
                      {refreshingRegulatoryGuidance ? "Refreshing" : "Refresh"}
                    </button>
                  </div>

                  {regulatoryGuidanceError && (
                    <p className="mb-3 text-xs text-destructive">
                      Unable to refresh regulatory guidance.
                    </p>
                  )}

                  {(data.regulatory_guidance ?? []).length > 0 ? (
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
                          {(data.regulatory_guidance ?? []).map((row, i) => (
                            <tr
                              key={`${row.regulator}-${row.title}-${i}`}
                              className="border-b border-hairline/70 align-top"
                            >
                              <td className="py-3 pr-4 font-medium text-ink">
                                {row.regulator}
                              </td>
                              <td className="py-3 pr-4 text-ink">{row.title}</td>
                              <td className="py-3 pr-4 leading-relaxed text-ink">
                                {row.description}
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
                    <p className="text-[0.9375rem] leading-relaxed">
                      <Placeholder />
                    </p>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </main>
    </div>
  );
}
