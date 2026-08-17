import { Compass } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import { getIconForSlug, ICON_FOR_SLUG, KNOWN_SLUGS } from '@/lib/baseClassIcons';

describe('baseClassIcons', () => {
  it('maps every known slug to a non-null icon component', () => {
    for (const slug of KNOWN_SLUGS) {
      expect(ICON_FOR_SLUG[slug]).toBeDefined();
      expect(typeof ICON_FOR_SLUG[slug]).toBe('object');
    }
  });

  it('contains exactly the five expected base-class slugs', () => {
    expect(KNOWN_SLUGS).toEqual(['fox', 'beaver', 'sparrow', 'coyote', 'lion']);
  });

  it('getIconForSlug returns Compass fallback for unknown slugs', () => {
    expect(getIconForSlug('unknown-slug')).toBe(Compass);
  });

  it('getIconForSlug returns the mapped icon for known slugs', () => {
    expect(getIconForSlug('fox')).toBe(ICON_FOR_SLUG.fox);
    expect(getIconForSlug('lion')).toBe(ICON_FOR_SLUG.lion);
  });
});
