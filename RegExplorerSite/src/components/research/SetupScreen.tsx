import { useState } from "react";
import { AppHeader } from "./AppHeader";

const JURISDICTIONS = [
  "United Kingdom",
  "European Union",
  "United States (federal)",
];

interface SetupScreenProps {
  onStart: (jurisdiction: string, topic: string) => void;
}

export function SetupScreen({ onStart }: SetupScreenProps) {
  const [jurisdiction, setJurisdiction] = useState("");
  const [topic, setTopic] = useState("");
  const [touched, setTouched] = useState(false);

  const jurisdictionError = touched && !jurisdiction;
  const topicError = touched && !topic.trim();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setTouched(true);
    if (!jurisdiction || !topic.trim()) return;
    onStart(jurisdiction, topic.trim());
  }

  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <AppHeader />
      <main className="flex flex-1 items-center justify-center px-6 py-16">
        <div className="w-full max-w-[480px]">
          <p className="eyebrow mb-6">New research session</p>

          <form onSubmit={handleSubmit} className="space-y-7" noValidate>
            <div>
              <label
                htmlFor="jurisdiction"
                className="mb-2 block font-serif text-base font-medium text-ink"
              >
                Reference jurisdiction
              </label>
              <div className="relative">
                <select
                  id="jurisdiction"
                  value={jurisdiction}
                  onChange={(e) => setJurisdiction(e.target.value)}
                  className={`w-full appearance-none rounded-[3px] border bg-paper px-3.5 py-2.5 pr-9 text-sm text-ink outline-none transition-colors focus:border-navy ${
                    jurisdictionError ? "border-destructive" : "border-hairline"
                  } ${jurisdiction ? "text-ink" : "text-muted-ink"}`}
                >
                  <option value="" disabled>
                    Select a jurisdiction
                  </option>
                  {JURISDICTIONS.map((j) => (
                    <option key={j} value={j}>
                      {j}
                    </option>
                  ))}
                </select>
                <svg
                  className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-ink"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  aria-hidden="true"
                >
                  <path d="M4 6l4 4 4-4" />
                </svg>
              </div>
              {jurisdictionError && (
                <p className="mt-1.5 text-xs text-destructive">Please select a jurisdiction.</p>
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
