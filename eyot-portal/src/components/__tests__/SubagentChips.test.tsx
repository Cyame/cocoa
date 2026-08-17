import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import SubagentChips, { extractSubagentCapabilities } from '@/components/SubagentChips';
import type { JsonObject } from '@/lib/types';

/* ---------- fixtures (real manifest shapes from builtin_presets.py) ---------- */

const BEAVER_MANIFEST: JsonObject = {
  subagent_strategy: {
    enabled: ['explore', 'research', 'architecture', 'quality'],
    constraints: { max_parallel: 4 },
  },
};

const LION_MANIFEST: JsonObject = {
  subagent_strategy: {
    enabled: ['intent', 'architecture', 'quality', 'explore', 'research', 'vision'],
    constraints: { max_parallel: 4 },
  },
};

const FOX_MANIFEST: JsonObject = {
  subagent_strategy: {
    enabled: ['intent', 'architecture', 'research'],
    constraints: { max_parallel: 4 },
  },
};

const SPARROW_MANIFEST: JsonObject = {
  subagent_strategy: {
    enabled: ['explore', 'quality'],
    constraints: { max_parallel: 4 },
  },
};

const NO_STRATEGY_MANIFEST: JsonObject = {
  model: 'gpt-4o-mini',
  prompt: 'test prompt',
};

const NULL_MANIFEST: null = null;

/* ---------- extractSubagentCapabilities (pure function) ---------- */

describe('extractSubagentCapabilities', () => {
  it('extracts 4 capabilities from beaver manifest', () => {
    const caps = extractSubagentCapabilities(BEAVER_MANIFEST);
    expect(caps).toEqual(['explore', 'research', 'architecture', 'quality']);
    expect(caps).toHaveLength(4);
  });

  it('extracts 6 capabilities from lion manifest', () => {
    const caps = extractSubagentCapabilities(LION_MANIFEST);
    expect(caps).toEqual(['intent', 'architecture', 'quality', 'explore', 'research', 'vision']);
    expect(caps).toHaveLength(6);
  });

  it('extracts 3 capabilities from fox manifest', () => {
    const caps = extractSubagentCapabilities(FOX_MANIFEST);
    expect(caps).toEqual(['intent', 'architecture', 'research']);
    expect(caps).toHaveLength(3);
  });

  it('extracts 2 capabilities from sparrow manifest', () => {
    const caps = extractSubagentCapabilities(SPARROW_MANIFEST);
    expect(caps).toEqual(['explore', 'quality']);
    expect(caps).toHaveLength(2);
  });

  it('returns empty array when manifest has no subagent_strategy', () => {
    const caps = extractSubagentCapabilities(NO_STRATEGY_MANIFEST);
    expect(caps).toEqual([]);
  });

  it('returns empty array for null manifest', () => {
    const caps = extractSubagentCapabilities(NULL_MANIFEST);
    expect(caps).toEqual([]);
  });

  it('returns empty array for undefined manifest', () => {
    const caps = extractSubagentCapabilities(undefined);
    expect(caps).toEqual([]);
  });

  it('filters out unknown capability IDs', () => {
    const manifest: JsonObject = {
      subagent_strategy: {
        enabled: ['explore', 'unknown-cap', 'research'],
      },
    };
    const caps = extractSubagentCapabilities(manifest);
    expect(caps).toEqual(['explore', 'research']);
  });
});

/* ---------- SubagentChips (rendered component) ---------- */

describe('SubagentChips', () => {
  it('renders 4 chips for beaver capabilities', () => {
    const caps = extractSubagentCapabilities(BEAVER_MANIFEST);
    render(<SubagentChips capabilities={caps} />);

    const chipContainer = screen.getByTestId('subagent-chips');
    expect(chipContainer).toBeInTheDocument();
    const chips = chipContainer.querySelectorAll('li');
    expect(chips).toHaveLength(4);

    expect(screen.getByTestId('subagent-chip-explore')).toHaveTextContent('Search');
    expect(screen.getByTestId('subagent-chip-research')).toHaveTextContent('Research');
    expect(screen.getByTestId('subagent-chip-architecture')).toHaveTextContent('Architecture');
    expect(screen.getByTestId('subagent-chip-quality')).toHaveTextContent('Quality');
  });

  it('renders 6 chips for lion capabilities', () => {
    const caps = extractSubagentCapabilities(LION_MANIFEST);
    render(<SubagentChips capabilities={caps} />);

    const chipContainer = screen.getByTestId('subagent-chips');
    const chips = chipContainer.querySelectorAll('li');
    expect(chips).toHaveLength(6);

    expect(screen.getByTestId('subagent-chip-intent')).toHaveTextContent('Intent');
    expect(screen.getByTestId('subagent-chip-vision')).toHaveTextContent('Vision');
  });

  it('renders nothing when capabilities array is empty', () => {
    const { container } = render(<SubagentChips capabilities={[]} />);
    expect(container.innerHTML).toBe('');
    expect(screen.queryByTestId('subagent-chips')).not.toBeInTheDocument();
  });

  it('renders heading text', () => {
    const caps = extractSubagentCapabilities(BEAVER_MANIFEST);
    render(<SubagentChips capabilities={caps} />);
    expect(screen.getByTestId('subagent-chips-heading')).toHaveTextContent(
      'Available Subagent Capabilities',
    );
  });
});
