import { describe, expect, it } from 'vitest';
import {
  type Directive,
  parse_turn,
  SlashParserError,
  segmentCompartments,
} from '@/lib/slash-parser';

describe('slash-parser', () => {
  it('parses @slug /cmd @workspace:path into 1 directive + 1 content-ref', () => {
    // Note: 白狐 (CJK) does not match the [a-zA-Z0-9_-]+ target regex,
    // so target_entity is null - mirroring the Python parser exactly.
    // The /plan command still makes this a directive, and @workspace:foo.md
    // is extracted as a content-ref (legacy scope normalized to hub).
    const turn = parse_turn('@白狐 /plan @workspace:foo.md');

    expect(turn.directives).toHaveLength(1);
    expect(turn.general_text).toBeNull();

    const d: Directive = turn.directives[0];
    expect(d.cmd).toBe('/plan');
    expect(d.target_entity).toBeNull();
    expect(d.args).toEqual(['@白狐']);
    expect(d.content_ref).not.toBeNull();
    expect(d.content_ref?.scope).toBe('hub');
    expect(d.content_ref?.path).toBe('foo.md');
    expect(d.raw_text).toBe('@白狐 /plan @workspace:foo.md');
  });

  it('normalizes legacy scopes to hub/instance and passes canonical through', () => {
    const hub = parse_turn('/read @workspace:x').directives[0].content_ref;
    expect(hub?.scope).toBe('hub');
    const hub2 = parse_turn('/read @fornix:x').directives[0].content_ref;
    expect(hub2?.scope).toBe('hub');
    const hub3 = parse_turn('/read @vault:x').directives[0].content_ref;
    expect(hub3?.scope).toBe('hub');
    const inst = parse_turn('/read @memory:y').directives[0].content_ref;
    expect(inst?.scope).toBe('instance');
    const canonical = parse_turn('/read @hub:a @instance:b').directives[0].content_ref;
    expect(canonical?.scope).toBe('instance');
  });

  it('parses bare text with no /cmd into general_text only', () => {
    const turn = parse_turn('hello world this is broadcast');

    expect(turn.directives).toHaveLength(0);
    expect(turn.general_text).toBe('hello world this is broadcast');
  });

  it('parses unknown slug as a directive target (validation is separate)', () => {
    // "unknown" is alphanumeric so it matches the target regex.
    // The parser does NOT validate whether the slug exists - that's
    // the backend directive_router's job.
    const turn = parse_turn('@unknown /plan');

    expect(turn.directives).toHaveLength(1);
    expect(turn.general_text).toBeNull();

    const d = turn.directives[0];
    expect(d.target_entity).toBe('unknown');
    expect(d.cmd).toBe('/plan');
    expect(d.args).toEqual([]);
    expect(d.content_ref).toBeNull();
  });

  it('segments a multi-directive turn into compartments', () => {
    const turn = parse_turn('broadcast message\n@alice /read\n@bob /write @workspace:notes.md');
    const compartments = segmentCompartments(turn);

    expect(compartments).toHaveLength(3);
    expect(compartments[0].label).toBe('general');
    expect(compartments[0].general_text).toBe('broadcast message');
    expect(compartments[1].label).toBe('alice');
    expect(compartments[1].directives).toHaveLength(1);
    expect(compartments[2].label).toBe('bob');
    expect(compartments[2].directives[0].content_ref?.scope).toBe('hub');
  });

  it('throws SlashParserError for non-string input', () => {
    expect(() => parse_turn(null as unknown as string)).toThrow(SlashParserError);
    expect(() => parse_turn(undefined as unknown as string)).toThrow(SlashParserError);
  });
});

describe('segmentCompartments', () => {
  it('always places general compartment first', () => {
    const turn = parse_turn('@alice /read\n@bob /write');
    const compartments = segmentCompartments(turn);
    expect(compartments[0].label).toBe('general');
  });

  it('creates one compartment per unique target slug', () => {
    const turn = parse_turn('@alice /read\n@bob /write\n@alice /status');
    const compartments = segmentCompartments(turn);
    const labels = compartments.map((c) => c.label);
    expect(labels).toEqual(['general', 'alice', 'bob']);
  });

  it('groups directives by target_entity correctly', () => {
    const turn = parse_turn('@alice /read\n@bob /write\n@alice /status');
    const compartments = segmentCompartments(turn);
    const alice = compartments.find((c) => c.label === 'alice');
    const bob = compartments.find((c) => c.label === 'bob');
    expect(alice?.directives).toHaveLength(2);
    expect(bob?.directives).toHaveLength(1);
    expect(alice?.directives[0].cmd).toBe('/read');
    expect(alice?.directives[1].cmd).toBe('/status');
    expect(bob?.directives[0].cmd).toBe('/write');
  });

  it('includes general_text in the general compartment', () => {
    const turn = parse_turn('hello\n@alice /read');
    const compartments = segmentCompartments(turn);
    expect(compartments[0].label).toBe('general');
    expect(compartments[0].general_text).toBe('hello');
    expect(compartments[0].directives).toHaveLength(0);
  });

  it('general compartment has null general_text when no free text', () => {
    const turn = parse_turn('@alice /read');
    const compartments = segmentCompartments(turn);
    expect(compartments[0].general_text).toBeNull();
  });

  it('G2 bidirectional: directives where lineage X is addressed all appear in X segment', () => {
    const turn = parse_turn('@bob /read\n@bob /write @workspace:notes.md');
    const compartments = segmentCompartments(turn);
    const bob = compartments.find((c) => c.label === 'bob');
    expect(bob).toBeDefined();
    expect(bob?.directives).toHaveLength(2);
    expect(bob?.directives[0].cmd).toBe('/read');
    expect(bob?.directives[1].cmd).toBe('/write');
  });

  it('G2: multi-lineage input produces separate segments per lineage', () => {
    const turn = parse_turn(
      '@alice /read @hub:spec.md\n@bob /write @hub:output.md\n@alice /status',
    );
    const compartments = segmentCompartments(turn);
    expect(compartments).toHaveLength(3);
    const alice = compartments.find((c) => c.label === 'alice');
    const bob = compartments.find((c) => c.label === 'bob');
    expect(alice?.directives).toHaveLength(2);
    expect(bob?.directives).toHaveLength(1);
  });

  it('produces only general compartment for untargeted turn', () => {
    const turn = parse_turn('just some text');
    const compartments = segmentCompartments(turn);
    expect(compartments).toHaveLength(1);
    expect(compartments[0].label).toBe('general');
    expect(compartments[0].general_text).toBe('just some text');
  });

  it('empty general compartment when turn has only directives', () => {
    const turn = parse_turn('@alice /read');
    const compartments = segmentCompartments(turn);
    expect(compartments).toHaveLength(2);
    expect(compartments[0].label).toBe('general');
    expect(compartments[0].directives).toHaveLength(0);
    expect(compartments[0].general_text).toBeNull();
    expect(compartments[1].label).toBe('alice');
  });
});
