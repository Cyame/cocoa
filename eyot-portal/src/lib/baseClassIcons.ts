/**
 * Canonical slug → lucide-react icon mapping for base-class entity types.
 *
 * Shared by onboarding card grid (Step1DivinityCards) and topology canvas
 * (TopologyPage — T6 integration). New base classes should be added here
 * before wiring into either consumer.
 */
import type { LucideIcon } from 'lucide-react';
import { Binary, Compass, Flame, Layers, Sparkles } from 'lucide-react';

/** Maps a base-class slug to its representative lucide icon. */
export const ICON_FOR_SLUG: Record<string, LucideIcon> = {
  fox: Compass,
  beaver: Flame,
  sparrow: Binary,
  coyote: Layers,
  lion: Sparkles,
};

/** All known base-class slugs that have an explicit icon mapping. */
export const KNOWN_SLUGS = Object.keys(ICON_FOR_SLUG) as readonly string[];

/**
 * Resolve the icon for a base-class slug, falling back to `Compass` for
 * unknown slugs. This is a convenience wrapper so consumers don't need
 * the nullish coalescing pattern at every call-site.
 */
export function getIconForSlug(slug: string): LucideIcon {
  return ICON_FOR_SLUG[slug] ?? Compass;
}
