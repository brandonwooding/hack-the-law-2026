import { useState } from "react";
import { AppHeader } from "./AppHeader";

const JURISDICTIONS = [
  "United Kingdom",
  "European Union",
  "United States (federal)",
];

interface SetupScreenProps {
  onStart: (jurisdictions: string[], topic: string) => void;
}

export function SetupScreen({ onStart }: SetupScreenProps) {
  const [jurisdictions, setJurisdictions] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [touched, setTouched] = useState(false);

  const jurisdictionError = touched && jurisdictions.length === 0;
  const topicError = touched && !topic.trim();

  function toggleJurisdiction(j: string) {
    setJurisdictions((prev) =>
      prev.includes(j) ? prev.filter((x) => x !== j) : [...prev, j],
    );
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (jurisdictions.length === 0 || !topic.trim()) return;
    onStart(jurisdictions, topic.trim());
  }

  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <AppHeader />
      <main className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-[480px]">
          <p className="eyebrow mb-3">New research session</p>
          <h1 className="mb-8 font-serif text-3xl font-semibold leading-tight tracking-tight text-ink">
            What regime do you want to look into today?
          </h1>

          <form onSubmit={handleSubmit} className="space-y-7" noValidate>
            <div>
              <label className="mb-2 block font-serif text-base font-medium text-ink">
                Reference jurisdictions
              </label>
              <p className="mb-3 text-xs text-muted-ink">
                Select one or more to scope the search across jurisdictions.
              </p>
              <div
                role="group"
                aria-label="Reference jurisdictions"
                className="flex flex-wrap gap-2"
              >
                {JURISDICTIONS.map((j) => {
                  const selected = jurisdictions.includes(j);
                  return (
                    <button
                      key={j}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => toggleJurisdiction(j)}
                      className={`rounded-full border px-3.5 py-2 text-sm transition-colors ${
                        selected
                          ? "border-navy bg-navy text-navy-foreground"
                          : `bg-paper text-ink hover:border-navy ${
                              jurisdictionError ? "border-destructive" : "border-hairline"
                            }`
                      }`}
                    >
                      {j}
                    </button>
                  );
                })}
              </div>
              {jurisdictionError && (
                <p className="mt-1.5 text-xs text-destructive">
                  Please select at least one jurisdiction.
                </p>
              )}
            </div>

            <div>
              <label
                htmlFor="topic"
                className="mb-2 block font-serif text-base font-medium text-ink"
              >
                Area of law
              </label>
              <input
                id="topic"
                type="text"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
                placeholder="e.g. online safety, data protection, financial promotions"
                className={`w-full rounded-full border bg-paper px-4 py-2.5 text-sm text-ink outline-none transition-colors placeholder:text-muted-ink focus:border-navy ${
                  topicError ? "border-destructive" : "border-hairline"
                }`}
              />
              {topicError && (
                <p className="mt-1.5 text-xs text-destructive">Please enter an area of law.</p>
              )}
            </div>

            <button
              type="submit"
              className="w-full rounded-[3px] bg-navy px-4 py-3 text-sm font-medium text-navy-foreground transition-colors hover:bg-[#16304e]"
            >
              Start research
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
