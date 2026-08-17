import type { TFunction } from 'i18next';

/** Legacy onboarding keys → canonical seeded API tags. */
const TAG_ALIASES: Readonly<Record<string, string>> = {
  plan: 'planning',
  execute: 'execution',
};

export function canonicalizeBaseClassTag(tag: string): string {
  const lower = tag.toLowerCase().trim();
  if (lower.length === 0) return lower;
  return TAG_ALIASES[lower] ?? lower;
}

export function normalizeBaseClassTags(
  tags: readonly string[] | null | undefined,
): readonly string[] {
  if (!tags) return [];
  const out: string[] = [];
  const seen = new Set<string>();
  for (const raw of tags) {
    const tag = canonicalizeBaseClassTag(raw);
    if (tag.length === 0 || seen.has(tag)) continue;
    seen.add(tag);
    out.push(tag);
  }
  return out;
}

/** Primary + secondary base-class tags — always resolve through i18n. */
export function translateBaseClassTag(tag: string, t: TFunction): string {
  const key = canonicalizeBaseClassTag(tag);
  if (key.length === 0) return key;
  return t(`namespaces.tag.${key}`, { defaultValue: key });
}
