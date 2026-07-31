/**
 * Agent thinking-block filter — port of nodeskclaw `utils/agentOutput.ts`.
 */

const REASONING_TAGS = [
  'think',
  'redacted_thinking',
  'reasoning',
  'thinking',
  'thought',
] as const;

const TAG_PATTERN = REASONING_TAGS.join('|');
const OPEN_TAG_RE = new RegExp(`<\\s*(?:${TAG_PATTERN})\\b[^>]*>`, 'i');
const CLOSE_TAG_RE = new RegExp(`<\\/\\s*(?:${TAG_PATTERN})\\s*>`, 'i');
const MAX_TAG_TAIL = 64;

function hasReasoningMarkup(text: string): boolean {
  if (OPEN_TAG_RE.test(text) || CLOSE_TAG_RE.test(text)) return true;
  const lower = text.toLowerCase();
  return REASONING_TAGS.some((tag) => lower.includes(`<${tag}`));
}

function thinkingBlockRegex(tag: string): RegExp {
  return new RegExp(`<\\s*${tag}\\b[^>]*>[\\s\\S]*?(?:<\\/\\s*${tag}\\s*>|$)`, 'gi');
}

export function stripAgentThinkingBlocks(text: string): string {
  if (!text) return text;
  if (!hasReasoningMarkup(text)) return text;

  let result = text;
  for (const tag of REASONING_TAGS) {
    result = result.replace(thinkingBlockRegex(tag), '');
    result = result.replace(new RegExp(`<\\/\\s*${tag}\\s*>`, 'gi'), '');
  }

  return result
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{2,}/g, '\n')
    .trim();
}

export function extractThinkingBlocks(text: string): string {
  if (!text || !hasReasoningMarkup(text)) return '';
  const parts: string[] = [];
  for (const tag of REASONING_TAGS) {
    const re = new RegExp(`<\\s*${tag}\\b[^>]*>([\\s\\S]*?)(?:<\\/\\s*${tag}\\s*>|$)`, 'gi');
    let match = re.exec(text);
    while (match !== null) {
      const body = (match[1] ?? '').trim();
      if (body) parts.push(body);
      match = re.exec(text);
    }
  }
  return parts.join('\n\n');
}

function looksLikePartialOpenTag(suffix: string): boolean {
  if (!suffix.startsWith('<') || suffix.includes('>')) return false;
  const body = suffix.slice(1).trimStart().toLowerCase();
  if (!body) return true;
  for (const tag of REASONING_TAGS) {
    if (tag.startsWith(body)) return true;
    if (body.startsWith(tag)) {
      if (body.length === tag.length) return true;
      const next = body[tag.length];
      return !/[a-z0-9_-]/i.test(next || '');
    }
  }
  return false;
}

function partialOpenSuffix(text: string): string {
  const start = Math.max(0, text.length - MAX_TAG_TAIL);
  for (let index = start; index < text.length; index += 1) {
    const suffix = text.slice(index);
    if (looksLikePartialOpenTag(suffix)) return suffix;
  }
  return '';
}

/** Streaming filter that suppresses thinking tags while tokens arrive. */
export class AgentThinkingStreamFilter {
  private buffer = '';
  private insideThink = false;

  feed(chunk: string): string {
    if (!chunk) return '';
    this.buffer += chunk;
    return this.drain(false);
  }

  flush(): string {
    return this.drain(true);
  }

  private drain(final: boolean): string {
    const output: string[] = [];

    while (this.buffer) {
      if (this.insideThink) {
        const closeMatch = this.buffer.match(CLOSE_TAG_RE);
        if (!closeMatch || closeMatch.index === undefined) {
          if (final) {
            this.buffer = '';
            this.insideThink = false;
          } else {
            this.buffer = this.buffer.slice(-MAX_TAG_TAIL);
          }
          break;
        }
        this.buffer = this.buffer.slice(closeMatch.index + closeMatch[0].length);
        this.insideThink = false;
        continue;
      }

      const openMatch = this.buffer.match(OPEN_TAG_RE);
      if (openMatch && openMatch.index !== undefined) {
        output.push(this.buffer.slice(0, openMatch.index));
        this.buffer = this.buffer.slice(openMatch.index + openMatch[0].length);
        this.insideThink = true;
        continue;
      }

      const keep = partialOpenSuffix(this.buffer);
      if (keep) {
        output.push(this.buffer.slice(0, -keep.length));
        this.buffer = final ? '' : keep;
      } else {
        output.push(this.buffer);
        this.buffer = '';
      }
      break;
    }

    return output.join('');
  }
}
