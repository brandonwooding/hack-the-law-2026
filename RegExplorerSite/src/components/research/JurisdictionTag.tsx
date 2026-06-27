// Regime ids are canonically prefixed with their jurisdiction code
// (e.g. "uk-ukpga-2023-50", "eu-celex-32022R2065"). We derive the tag from the
// id so it works everywhere a regime is rendered, with no extra API field.
const JURISDICTION_LABELS: Record<string, string> = {
  uk: "UK",
  eu: "EU",
};

export function jurisdictionFromId(id: string): string | null {
  const prefix = id.split("-")[0]?.toLowerCase() ?? "";
  return JURISDICTION_LABELS[prefix] ?? null;
}

export function JurisdictionTag({
  id,
  className = "",
}: {
  id: string;
  className?: string;
}) {
  const label = jurisdictionFromId(id);
  if (!label) return null;
  return (
    <span
      className={`inline-flex flex-shrink-0 items-center rounded-[2px] border border-hairline px-1.5 py-0.5 text-[0.625rem] font-medium uppercase tracking-[0.08em] text-muted-ink ${className}`}
    >
      {label}
    </span>
  );
}
