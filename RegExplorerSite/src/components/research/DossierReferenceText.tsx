import type { ReactNode } from "react";
import type { Regime } from "@/lib/regimes";

interface ReferenceLink {
  label: string;
  url: string;
}

function addLink(links: Map<string, string>, label: string, url: string) {
  const clean = label.trim();
  if (clean.length < 4 || links.has(clean)) return;
  links.set(clean, url);
}

function referenceLabels(reference: string) {
  const labels = new Set<string>();
  const primary = reference.split(/\s+[–-]\s+/)[0]?.trim();
  if (primary) labels.add(primary);

  const afterComma = primary?.split(",").at(-1)?.trim();
  if (afterComma && afterComma !== primary) labels.add(afterComma);

  for (const match of reference.matchAll(/\bArticle\s+\d+[A-Za-z]?(?:\(\d+\))*/g)) {
    labels.add(match[0]);
    labels.add(match[0].replace(/\(\d+\)$/, ""));
  }

  for (const match of reference.matchAll(/\bPart\s+\d+[A-Za-z]?\b/g)) {
    labels.add(match[0]);
  }

  for (const match of reference.matchAll(/\b(?:section|Section|s\.)\s*\d+[A-Za-z]?\b/g)) {
    labels.add(match[0]);
  }

  return [...labels];
}

function referenceLinks(regime: Pick<Regime, "obligations">) {
  const links = new Map<string, string>();

  for (const obligation of regime.obligations) {
    if (!obligation.reference || !obligation.url) continue;
    addLink(links, obligation.reference, obligation.url);
    for (const label of referenceLabels(obligation.reference)) {
      addLink(links, label, obligation.url);
    }
  }

  return [...links.entries()]
    .map(([label, url]) => ({ label, url }))
    .sort((a, b) => b.label.length - a.label.length);
}

function isBoundary(char: string | undefined) {
  return !char || !/[A-Za-z0-9]/.test(char);
}

function findNextLink(text: string, links: ReferenceLink[], from: number) {
  let best:
    | { link: ReferenceLink; start: number; end: number }
    | undefined;

  for (const link of links) {
    let start = text.indexOf(link.label, from);
    while (start !== -1) {
      const end = start + link.label.length;
      if (isBoundary(text[start - 1]) && isBoundary(text[end])) {
        if (!best || start < best.start || (start === best.start && end > best.end)) {
          best = { link, start, end };
        }
        break;
      }
      start = text.indexOf(link.label, start + 1);
    }
  }

  return best;
}

export function DossierReferenceText({
  text,
  regime,
}: {
  text: string;
  regime: Pick<Regime, "obligations">;
}) {
  const links = referenceLinks(regime);
  const nodes: ReactNode[] = [];
  let index = 0;
  let key = 0;

  while (index < text.length) {
    const next = findNextLink(text, links, index);
    if (!next) {
      nodes.push(text.slice(index));
      break;
    }

    if (next.start > index) nodes.push(text.slice(index, next.start));
    nodes.push(
      <a
        key={`ref-${key++}`}
        href={next.link.url}
        target="_blank"
        rel="noreferrer"
        className="text-navy underline decoration-navy/30 underline-offset-2 transition-colors hover:decoration-navy"
      >
        {next.link.label}
      </a>,
    );
    index = next.end;
  }

  return <>{nodes}</>;
}
