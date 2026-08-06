import { pinyin } from 'pinyin-pro';

const SLUG_MAX = 48;

/**
 * Derive a kebab-case slug from a display name.
 *
 * Chinese characters are converted to tone-less pinyin syllables
 * (e.g. "奈亚探子" → "nai-ya-tan-zi"), matching the onboarding UX spec.
 * Latin / digits are kept; everything else collapses to hyphens.
 */
export function toSlug(input: string, maxLength = SLUG_MAX): string {
  const trimmed = input.trim();
  if (trimmed.length === 0) return '';

  const parts = pinyin(trimmed, {
    toneType: 'none',
    type: 'array',
    nonZh: 'consecutive',
    v: true,
  });

  const joined = (Array.isArray(parts) ? parts : [String(parts)]).join(' ');
  let slug = joined
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '');

  if (slug.length === 0) return '';
  // Slug pattern requires a leading lowercase letter.
  if (!/^[a-z]/.test(slug)) {
    slug = `e-${slug}`;
  }
  return slug.slice(0, maxLength).replace(/-+$/g, '');
}

export const SLUG_PATTERN = /^[a-z][a-z0-9-]*$/;

export function isValidSlug(value: string): boolean {
  return SLUG_PATTERN.test(value);
}

/**
 * v4.9.4 C4: strict kebab-case pattern matching the backend slug validation
 * `^[a-z0-9]+(-[a-z0-9]+)*$` (min 1 char, single hyphens between segments,
 * no leading/trailing/consecutive hyphens). Empty string is valid because
 * slug is optional in the clone dialog.
 */
export const KEBAB_SLUG_PATTERN = /^[a-z0-9]+(-[a-z0-9]+)*$/;

export function isValidKebabSlug(value: string): boolean {
  if (value.length === 0) return true;
  return KEBAB_SLUG_PATTERN.test(value);
}
