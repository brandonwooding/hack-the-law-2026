import { AppHeader } from "./AppHeader";
import type { Regime } from "@/lib/regimes";

interface RegimeDetailScreenProps {
  regime: Regime;
  onBack: () => void;
}

function Placeholder() {
  return <span className="text-muted-ink italic">Not yet documented.</span>;
}

export function RegimeDetailScreen({ regime, onBack }: RegimeDetailScreenProps) {
  return (
    <div className="flex min-h-screen flex-col bg-paper">
      <AppHeader />
      <main className="flex-1 px-6 py-10">
        <div className="mx-auto max-w-[720px]">
          <button
            onClick={onBack}
            className="mb-8 text-sm text-navy transition-colors hover:underline"
          >
            ← Back to regimes
          </button>

          <h1 className="font-serif text-3xl font-semibold leading-tight tracking-tight text-ink">
            {regime.name}
          </h1>
          <hr className="my-6 border-0 border-t border-hairline" />

          <section>
            <p className="eyebrow mb-2">Summary</p>
            <p className="text-[0.9375rem] leading-relaxed text-ink">
              {regime.summary || <Placeholder />}
            </p>
          </section>

          <hr className="my-7 border-0 border-t border-hairline" />

          <table className="w-full border-collapse text-left">
            <tbody>
              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Scope
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {regime.scope || <Placeholder />}
                </td>
              </tr>

              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Regulatory process
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {regime.process || <Placeholder />}
                </td>
              </tr>

              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Consequence
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {regime.consequence || <Placeholder />}
                </td>
              </tr>

              <tr className="border-t border-hairline align-top">
                <th scope="row" className="eyebrow w-44 py-5 pr-6 text-left align-top">
                  Obligations
                </th>
                <td className="py-5 text-[0.9375rem] leading-relaxed text-ink">
                  {regime.obligations.length > 0 ? (
                    <ul className="space-y-3">
                      {regime.obligations.map((o, i) => (
                        <li key={i} className="flex gap-3">
                          <span
                            className="mt-2 h-1 w-1 flex-shrink-0 rounded-full bg-ink"
                            aria-hidden="true"
                          />
                          <span>
                            {o.text}{" "}
                            <a
                              href="#"
                              onClick={(e) => e.preventDefault()}
                              className="text-navy underline decoration-navy/30 underline-offset-2 transition-colors hover:decoration-navy"
                            >
                              ({o.reference})
                            </a>
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
                  {regime.guidance ? (
                    <blockquote className="border-l-2 border-navy bg-secondary/40 py-1 pl-4">
                      <p className="text-[0.9375rem] leading-relaxed text-ink">{regime.guidance}</p>
                    </blockquote>
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
