import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { Home, Scale } from "lucide-react";

const NAV = [
  { to: "/", label: "Home", icon: Home, exact: true },
  { to: "/regimes", label: "Regimes", icon: Scale, exact: false },
] as const;

export function SidebarLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen bg-paper">
      <nav className="flex w-56 shrink-0 flex-col border-r border-hairline">
        <div className="flex items-baseline gap-2.5 border-b border-hairline px-5 py-3.5">
          <span className="font-serif text-lg font-semibold tracking-tight text-ink">
            Regime
          </span>
        </div>
        <ul className="flex-1 space-y-0.5 px-3 py-4">
          {NAV.map(({ to, label, icon: Icon, exact }) => (
            <li key={to}>
              <Link
                to={to}
                activeOptions={{ exact }}
                className="flex items-center gap-2.5 rounded-[3px] px-3 py-2 text-sm text-ink transition-colors hover:bg-secondary data-[status=active]:bg-secondary data-[status=active]:font-medium data-[status=active]:text-navy"
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {label}
              </Link>
            </li>
          ))}
        </ul>
        <div className="border-t border-hairline px-5 py-3">
          <span className="text-[0.6875rem] uppercase tracking-[0.14em] text-muted-ink">
            Cross-Jurisdiction Legal Research
          </span>
        </div>
      </nav>
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">{children}</div>
    </div>
  );
}
