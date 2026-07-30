import { describe, expect, it } from 'vitest';
import { isValidSlug, toSlug } from '@/lib/slug';

describe('toSlug', () => {
  it('kebab-cases latin display names', () => {
    expect(toSlug('Nyar Proutzi Aide')).toBe('nyar-proutzi-aide');
  });

  it('converts Chinese display names to pinyin kebab-case', () => {
    expect(toSlug('奈亚探子')).toBe('nai-ya-tan-zi');
  });

  it('handles mixed Chinese and latin', () => {
    expect(toSlug('密士 Aide')).toBe('mi-shi-aide');
  });

  it('returns empty for empty / punctuation-only input', () => {
    expect(toSlug('')).toBe('');
    expect(toSlug('   ')).toBe('');
    expect(toSlug('---')).toBe('');
  });

  it('prefixes a letter when the result would start with a digit', () => {
    expect(toSlug('2026助手')).toMatch(/^e-/);
    expect(isValidSlug(toSlug('2026助手'))).toBe(true);
  });
});
