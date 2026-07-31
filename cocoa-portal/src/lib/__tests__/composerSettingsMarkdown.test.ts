import { describe, expect, it } from 'vitest';
import {
  AgentThinkingStreamFilter,
  extractThinkingBlocks,
  stripAgentThinkingBlocks,
} from '@/lib/agentOutput';
import { renderMarkdown } from '@/lib/markdown';

describe('agentOutput', () => {
  it('strips thinking blocks', () => {
    const raw = 'hello <thinking>secret</thinking> world';
    expect(stripAgentThinkingBlocks(raw)).toBe('hello  world');
    expect(extractThinkingBlocks(raw)).toBe('secret');
  });

  it('filters thinking during stream', () => {
    const f = new AgentThinkingStreamFilter();
    expect(f.feed('a ')).toBe('a ');
    expect(f.feed('<thinking>x')).toBe('');
    expect(f.feed('y</thinking> b')).toBe(' b');
    expect(f.flush()).toBe('');
  });
});

describe('markdown', () => {
  it('renders bold and sanitizes script', () => {
    const html = renderMarkdown('**hi** <script>alert(1)</script>');
    expect(html).toContain('<strong>hi</strong>');
    expect(html.toLowerCase()).not.toContain('<script');
  });
});
