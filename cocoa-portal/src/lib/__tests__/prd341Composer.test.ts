import { describe, expect, it } from 'vitest';
import { fitNodes } from '@/lib/topologyFit';
import { parse_directive, parse_turn } from '@/lib/slash-parser';

describe('slash-parser mention chat', () => {
  it('parses @slug text without /cmd', () => {
    const d = parse_directive('@alice hello there');
    expect(typeof d).toBe('object');
    if (typeof d === 'string') throw new Error('expected directive');
    expect(d.target_entity).toBe('alice');
    expect(d.cmd).toBe('');
    expect(d.args).toEqual(['hello', 'there']);
  });

  it('parses multi-line mentions into directives', () => {
    const turn = parse_turn('@a hi\n@b yo');
    expect(turn.directives).toHaveLength(2);
    expect(turn.directives[0]?.target_entity).toBe('a');
    expect(turn.directives[1]?.target_entity).toBe('b');
  });
});

describe('topologyFit', () => {
  it('centers a single node', () => {
    const vp = fitNodes([{ x: 100, y: 50 }], { padding: 0.15 });
    expect(vp.zoom).toBeGreaterThan(0);
    expect(vp.panX).toBeCloseTo(-100 * vp.zoom, 5);
    expect(vp.panY).toBeCloseTo(-50 * vp.zoom, 5);
  });

  it('returns identity for empty nodes', () => {
    expect(fitNodes([])).toEqual({ panX: 0, panY: 0, zoom: 1 });
  });
});
