/**
 * Slash-protocol parser - TypeScript mirror of P4 ``app/core/slash_parser.py``.
 *
 * This is a **pure parser** - it only validates structural syntax, NOT
 * whether targets or commands exist. Mirrors the Python ``parse_turn()``
 * exactly so the two outputs are interchangeable (verified by
 * ``tests/test_phase9_portal.py::test_slash_parser_parity``).
 *
 * Grammar (informal, matches Python docstring):
 *
 *     <turn>        := <directive>+
 *     <directive>   := [<target>] <cmd> [<args>] [<content-ref>]
 *     <target>      := "@" <employee-name>   (at line start, followed by whitespace)
 *     <cmd>         := "/" <name>            (lowercase-start, alphanumeric + hyphens)
 *     <content-ref> : "@" <scope> [":" <path>]
 *     scope         := "hub" | "instance"
 *
 * Legacy content-ref scopes (workspace | fornix | vault | blackboard |
 * memory) are still *accepted* in input text so existing messages don't
 * break, but the parsed ``scope`` is always normalized to the canonical
 * enum — ``hub`` for hub-scoped storage, ``instance`` for memory.
 */

// ---------------------------------------------------------------------------
// Types - mirror app/schemas/slash.py (Pydantic models)
// ---------------------------------------------------------------------------

export type Scope = 'hub' | 'instance';

export type ContentRef = {
  readonly scope: Scope;
  readonly path: string | null;
};

export type Directive = {
  readonly target_entity: string | null;
  /** Empty string = chat mention (@slug text) without a slash command. */
  readonly cmd: string;
  readonly args: readonly string[];
  readonly content_ref: ContentRef | null;
  readonly raw_text: string;
};

export type Turn = {
  readonly directives: readonly Directive[];
  readonly general_text: string | null;
};

// ---------------------------------------------------------------------------
// Regexes - mirror Python re.compile patterns character-for-character
// ---------------------------------------------------------------------------

/**
 * @employee-name at line start (alphanumeric + hyphens/underscores),
 * followed by whitespace or end-of-line. Matches Python
 * ``^@([a-zA-Z0-9_-]+)(?:\s+|$)``.
 */
const RE_TARGET = /^@([a-zA-Z0-9_-]+)(?:\s+|$)/;

/**
 * /command (lowercase-start, alphanumeric + hyphens).
 * Matches Python ``/(?P<cmd>[a-z][a-z0-9-]*)``. Used with .match() (first
 * occurrence, leftmost) to mirror Python ``re.search``.
 */
const RE_CMD = /\/([a-z][a-z0-9-]*)/;

/**
 * @scope:path where scope is a canonical (hub|instance) or legacy
 * (workspace|fornix|vault|memory) keyword — legacy values are normalized by
 * {@link normalizeScope} after capture. The global flag is required for both
 * matchAll (mirrors Python ``re.finditer``) and replace (mirrors Python
 * ``re.sub``, which is global by default).
 */
const RE_CONTENT_REF = /@(hub|instance|workspace|fornix|vault|memory)(?::(\S+))?/g;

/** Inline @slug tokens for same-line multi-mention chat expansion. */
const RE_AT_TOKEN = /@([a-zA-Z0-9_-]+)/g;
// Both canonical and legacy scopes — legacy values still appear in inbound
// text and must be excluded from @slug mention expansion.
const CONTENT_REF_SCOPES = new Set(['hub', 'instance', 'workspace', 'fornix', 'vault', 'memory']);

/** Map a legacy ContentRef scope string to the v4.5 canonical enum. */
export function normalizeScope(scope: string): Scope {
  switch (scope) {
    case 'workspace':
    case 'fornix':
    case 'vault':
    case 'blackboard':
      return 'hub';
    case 'memory':
      return 'instance';
    default:
      return scope as Scope;
  }
}

/**
 * Expand ``@a hi @b bye`` (no slash cmds) into one {@link Directive} per @slug.
 * Returns ``null`` when the line should stay a single parse_directive result.
 */
export function expandInlineChatMentions(raw: string): Directive[] | null {
  if (/\/([a-z][a-z0-9-]*)/.test(raw)) {
    return null;
  }
  const matches: RegExpExecArray[] = [];
  RE_AT_TOKEN.lastIndex = 0;
  let m = RE_AT_TOKEN.exec(raw);
  while (m !== null) {
    const slug = m[1];
    if (CONTENT_REF_SCOPES.has(slug)) continue;
    if (m.index > 0 && !/\s/.test(raw[m.index - 1] ?? '')) continue;
    matches.push(m);
    m = RE_AT_TOKEN.exec(raw);
  }
  if (matches.length <= 1) return null;
  const out: Directive[] = [];
  for (let i = 0; i < matches.length; i++) {
    const cur = matches[i];
    const start = cur.index + cur[0].length;
    const end = i + 1 < matches.length ? matches[i + 1].index : raw.length;
    const body = raw.slice(start, end).trim();
    const args = body.split(/\s+/).filter((a) => a.length > 0);
    const segment = raw.slice(cur.index, end).trim();
    out.push({
      target_entity: cur[1],
      cmd: '',
      args,
      content_ref: null,
      raw_text: segment,
    });
  }
  return out;
}

// ---------------------------------------------------------------------------
// Parser error
// ---------------------------------------------------------------------------

export class SlashParserError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'SlashParserError';
  }
}

// ---------------------------------------------------------------------------
// parse_directive - mirror Python parse_directive(line)
// ---------------------------------------------------------------------------

/**
 * Parse a single line into a {@link Directive}, or return the raw line
 * string (to be merged into ``general_text``).
 *
 * Mirrors ``app/core/slash_parser.py::parse_directive`` exactly.
 */
export function parse_directive(line: string): Directive | string {
  const original = line;
  let remaining = line;

  // 1. Extract optional @target at line start.
  let target: string | null = null;
  const targetMatch = remaining.match(RE_TARGET);
  if (targetMatch !== null) {
    target = targetMatch[1];
    remaining = remaining.slice(targetMatch[0].length);
  }

  // 2. Extract /cmd (first occurrence, leftmost).
  // PRD-v3.4.1: bare ``@slug message`` (no /cmd) is a chat mention.
  const cmdMatch = remaining.match(RE_CMD);
  if (cmdMatch === null) {
    if (target !== null) {
      const args = remaining.split(/\s+/).filter((a) => a.length > 0);
      return {
        target_entity: target,
        cmd: '',
        args,
        content_ref: null,
        raw_text: original,
      };
    }
    return original;
  }
  const cmd = cmdMatch[1];
  const cmdStart = cmdMatch.index;
  if (cmdStart === undefined) return original;
  const cmdEnd = cmdStart + cmdMatch[0].length;
  remaining = remaining.slice(0, cmdStart) + remaining.slice(cmdEnd);

  // 3. Extract @scope:path content-ref(s). Take the *last* one (closest
  //    to end-of-line). Remove all content-ref tokens from remaining.
  let contentRef: ContentRef | null = null;
  const refMatches = remaining.matchAll(RE_CONTENT_REF);
  for (const m of refMatches) {
    contentRef = {
      scope: normalizeScope(m[1]),
      path: m[2] ?? null,
    };
  }
  if (contentRef !== null) {
    remaining = remaining.replace(RE_CONTENT_REF, '').trim();
  }

  // 4. Remaining text -> args (whitespace-split, filter empties).
  const args = remaining.split(/\s+/).filter((a) => a.length > 0);

  return {
    target_entity: target,
    cmd: `/${cmd}`,
    args,
    content_ref: contentRef,
    raw_text: original,
  };
}

// ---------------------------------------------------------------------------
// parse_turn - mirror Python parse_turn(raw_text)
// ---------------------------------------------------------------------------

/**
 * Parse raw multi-line user input into a {@link Turn}.
 *
 * Each non-empty line is parsed via {@link parse_directive}. Lines that
 * parse into a {@link Directive} go into ``directives``; lines that don't
 * are joined with ``\n`` and placed in ``general_text``.
 *
 * Mirrors ``app/core/slash_parser.py::parse_turn`` exactly.
 *
 * @throws {SlashParserError} if `rawText` is not a string.
 */
export function parse_turn(rawText: string): Turn {
  if (typeof rawText !== 'string') {
    throw new SlashParserError('parse_turn expects a string input');
  }

  const lines = rawText.trim().split('\n');

  const directives: Directive[] = [];
  const generalParts: string[] = [];

  for (const line of lines) {
    const stripped = line.trim();
    if (stripped.length === 0) {
      continue;
    }
    const expanded = expandInlineChatMentions(stripped);
    if (expanded !== null) {
      directives.push(...expanded);
      continue;
    }
    const result = parse_directive(stripped);
    if (typeof result === 'string') {
      generalParts.push(result);
    } else {
      directives.push(result);
    }
  }

  const generalText = generalParts.length > 0 ? generalParts.join('\n') : null;
  return { directives, general_text: generalText };
}

// ---------------------------------------------------------------------------
// Compartment segmentation (UI-only, not in backend)
// ---------------------------------------------------------------------------

/**
 * A visual compartment for the composer preview panel. Derived from a
 * parsed {@link Turn}: the "general" compartment holds free-form text +
 * untargeted directives; each targeted directive opens a per-slug
 * compartment.
 *
 * Segmentation rules (cocoa-v2-program.md L171-179):
 * - First compartment = "general" (text before any @employee + directives
 *   with no target).
 * - Subsequent compartments = per {@link Directive.target_entity} slug.
 */
export type Compartment = {
  readonly label: string;
  readonly directives: readonly Directive[];
  readonly general_text: string | null;
};

/**
 * Group a parsed {@link Turn} into visual compartments for the composer
 * preview panel. The "general" compartment always comes first (even if
 * empty) so the UI has a stable anchor.
 */
export function segmentCompartments(turn: Turn): readonly Compartment[] {
  const generalDirectives: Directive[] = [];
  const bySlug = new Map<string, Directive[]>();
  const slugOrder: string[] = [];

  for (const d of turn.directives) {
    if (d.target_entity === null) {
      generalDirectives.push(d);
    } else {
      const slug = d.target_entity;
      let bucket = bySlug.get(slug);
      if (bucket === undefined) {
        bucket = [];
        bySlug.set(slug, bucket);
        slugOrder.push(slug);
      }
      bucket.push(d);
    }
  }

  const compartments: Compartment[] = [
    {
      label: 'general',
      directives: generalDirectives,
      general_text: turn.general_text,
    },
  ];

  for (const slug of slugOrder) {
    compartments.push({
      label: slug,
      directives: bySlug.get(slug) ?? [],
      general_text: null,
    });
  }

  return compartments;
}
