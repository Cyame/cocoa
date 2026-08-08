import { describe, expect, it } from 'vitest';
import {
  canonicalizeBaseClassTag,
  normalizeBaseClassTags,
  translateBaseClassTag,
} from '@/lib/baseClassTags';

const t = ((key: string, opts?: { defaultValue?: string }) => {
  const map: Record<string, string> = {
    'namespaces.tag.planning': '策划',
    'namespaces.tag.execution': '执行',
    'namespaces.tag.oracle': '灵视',
    'namespaces.tag.ultraworker': '超工',
  };
  return map[key] ?? opts?.defaultValue ?? key;
}) as import('i18next').TFunction;

describe('baseClassTags', () => {
  it('aliases legacy plan/execute to canonical keys', () => {
    expect(canonicalizeBaseClassTag('plan')).toBe('planning');
    expect(canonicalizeBaseClassTag('Execute')).toBe('execution');
  });

  it('normalizes and de-duplicates tags', () => {
    expect(normalizeBaseClassTags(['plan', 'planning', 'oracle'])).toEqual(['planning', 'oracle']);
  });

  it('translates primary and secondary tags via i18n', () => {
    expect(translateBaseClassTag('planning', t)).toBe('策划');
    expect(translateBaseClassTag('plan', t)).toBe('策划');
    expect(translateBaseClassTag('oracle', t)).toBe('灵视');
    expect(translateBaseClassTag('ultraworker', t)).toBe('超工');
  });
});
