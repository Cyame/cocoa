import { describe, expect, it } from 'vitest';
import { isValidKebabSlug, isValidSlug, toSlug } from '@/lib/slug';

describe('toSlug', () => {
  it('kebab-cases latin display names', () => {
    expect(toSlug('White Fox Aide')).toBe('white-fox-aide');
  });

  it('converts Chinese display names to pinyin kebab-case', () => {
    expect(toSlug('白狐')).toBe('bai-hu');
  });

  it('handles mixed Chinese and latin', () => {
    expect(toSlug('云雀 Aide')).toBe('yun-que-aide');
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

describe('isValidKebabSlug', () => {
  it('accepts empty string as valid (slug is optional)', () => {
    expect(isValidKebabSlug('')).toBe(true);
  });

  it('accepts single lowercase letter', () => {
    expect(isValidKebabSlug('a')).toBe(true);
  });

  it('accepts single digit', () => {
    expect(isValidKebabSlug('1')).toBe(true);
  });

  it('accepts simple kebab-case', () => {
    expect(isValidKebabSlug('my-base-class')).toBe(true);
  });

  it('accepts mixed letters and digits', () => {
    expect(isValidKebabSlug('base-class-2')).toBe(true);
  });

  it('rejects leading hyphen', () => {
    expect(isValidKebabSlug('-abc')).toBe(false);
  });

  it('rejects trailing hyphen', () => {
    expect(isValidKebabSlug('abc-')).toBe(false);
  });

  it('rejects consecutive hyphens', () => {
    expect(isValidKebabSlug('a--b')).toBe(false);
  });

  it('rejects uppercase letters', () => {
    expect(isValidKebabSlug('MyBaseClass')).toBe(false);
  });

  it('rejects underscores', () => {
    expect(isValidKebabSlug('my_base_class')).toBe(false);
  });

  it('rejects spaces', () => {
    expect(isValidKebabSlug('my base class')).toBe(false);
  });

  it('rejects non-ASCII characters', () => {
    expect(isValidKebabSlug('神职')).toBe(false);
  });
});
