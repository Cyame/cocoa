import { describe, expect, it } from 'vitest';
import {
  buildInjectPayload,
  buildInstanceEventsPath,
  mergeHarnessEvents,
} from '@/lib/instanceHarness';
import type { Event } from '@/lib/types';

function makeEvent(id: string, createdAt: string, type = 'harness.inject_requested'): Event {
  return {
    id,
    type,
    actor_type: 'user',
    actor_id: null,
    resource_type: 'instance',
    resource_id: 'inst-1',
    payload: {},
    request_id: null,
    created_at: createdAt,
  };
}

describe('buildInstanceEventsPath', () => {
  it('sets limit, type_prefix and resource_id', () => {
    const path = buildInstanceEventsPath('inst-1', 'harness.inject_');
    const [pathname, query] = path.split('?');
    expect(pathname).toBe('/events');
    const params = new URLSearchParams(query);
    expect(params.get('limit')).toBe('20');
    expect(params.get('type_prefix')).toBe('harness.inject_');
    expect(params.get('resource_id')).toBe('inst-1');
  });

  it('respects a custom limit', () => {
    const path = buildInstanceEventsPath('inst-1', 'harness.report_', 5);
    const params = new URLSearchParams(path.split('?')[1]);
    expect(params.get('limit')).toBe('5');
  });
});

describe('mergeHarnessEvents', () => {
  it('merges both pages newest-first and dedupes by id', () => {
    const injectEvents = [
      makeEvent('a', '2026-08-05T10:00:00Z'),
      makeEvent('b', '2026-08-05T12:00:00Z'),
    ];
    const reportEvents = [
      makeEvent('b', '2026-08-05T12:00:00Z', 'harness.report_received'),
      makeEvent('c', '2026-08-05T11:00:00Z', 'harness.report_received'),
    ];
    const merged = mergeHarnessEvents(injectEvents, reportEvents);
    expect(merged.map((event) => event.id)).toEqual(['b', 'c', 'a']);
  });

  it('truncates to the limit', () => {
    const injectEvents = Array.from({ length: 20 }, (_, index) =>
      makeEvent(`i-${index}`, `2026-08-05T10:${String(index).padStart(2, '0')}:00Z`),
    );
    const reportEvents = Array.from({ length: 20 }, (_, index) =>
      makeEvent(`r-${index}`, `2026-08-05T11:${String(index).padStart(2, '0')}:00Z`),
    );
    const merged = mergeHarnessEvents(injectEvents, reportEvents);
    expect(merged).toHaveLength(20);
    expect(merged[0].id).toBe('r-19');
  });
});

describe('buildInjectPayload', () => {
  it('keeps a non-empty trimmed tldr', () => {
    expect(
      buildInjectPayload({ kind: 'gene_inject', deliveryMode: 'soft_inject', tldr: '  hi  ' }),
    ).toEqual({ kind: 'gene_inject', delivery_mode: 'soft_inject', tldr: 'hi' });
  });

  it('omits tldr when blank or whitespace-only', () => {
    expect(
      buildInjectPayload({ kind: 'collab_inject', deliveryMode: 'notify', tldr: '   ' }),
    ).toEqual({ kind: 'collab_inject', delivery_mode: 'notify' });
    expect(
      buildInjectPayload({ kind: 'cerebellum_route', deliveryMode: 'wake', tldr: '' }),
    ).toEqual({ kind: 'cerebellum_route', delivery_mode: 'wake' });
  });
});
