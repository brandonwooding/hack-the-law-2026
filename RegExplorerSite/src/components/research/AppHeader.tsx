interface AppHeaderProps {
  right?: React.ReactNode;
}

export function AppHeader({ right }: AppHeaderProps) {
  return (
    <header className="flex items-center justify-between border-b border-hairline px-6 py-3.5">
      <div className="flex items-baseline gap-2.5">
        <span className="font-serif text-lg font-semibold tracking-tight text-ink">DORA</span>
        <span className="hidden text-[0.6875rem] uppercase tracking-[0.14em] text-muted-ink sm:inline">
          The Regulatory Explorer
        </span>
      </div>
      {right}
    </header>
  );
}
