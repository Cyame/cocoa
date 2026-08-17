/**
 * Composer markdown rendering — lean port of nodeskclaw `utils/markdown.ts`
 * (marked GFM + DOMPurify). Mermaid / KaTeX left for a later wave.
 */

import DOMPurify from 'dompurify';
import { marked } from 'marked';

marked.setOptions({ breaks: true, gfm: true });

export function renderMarkdown(content: string): string {
  if (!content) return '';
  const html = marked.parse(content, { async: false }) as string;
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
  });
}
