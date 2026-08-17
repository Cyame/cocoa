import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ActivityBlock } from '@/components/ActivityBlock';
import type { ActivityItem } from '@/lib/composerTranscript';

function makeThinking(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 1,
    kind: 'thinking',
    status: 'end',
    deltas: 'Let me think about this...',
    ...overrides,
  };
}

function makeToolUse(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 2,
    kind: 'tool_use',
    toolName: 'write_file',
    status: 'end',
    deltas: '',
    ...overrides,
  };
}

function makeDelegation(overrides: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: 3,
    kind: 'tool_use',
    toolName: 'subagent-research',
    status: 'start',
    deltas: '',
    isDelegation: true,
    ...overrides,
  };
}

describe('ActivityBlock', () => {
  it('renders nothing when activities is empty', () => {
    const { container } = render(<ActivityBlock activities={[]} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders thinking fold with content', () => {
    render(<ActivityBlock activities={[makeThinking()]} />);
    expect(screen.getByTestId('activity-thinking')).toBeTruthy();
    expect(screen.getByText('Let me think about this...')).toBeTruthy();
  });

  it('renders tool_use card with tool_name', () => {
    render(<ActivityBlock activities={[makeToolUse()]} />);
    expect(screen.getByTestId('activity-tool-use')).toBeTruthy();
    expect(screen.getByText('write_file')).toBeTruthy();
  });

  it('renders delegation trace for subagent tools', () => {
    render(<ActivityBlock activities={[makeDelegation()]} />);
    expect(screen.getByTestId('activity-delegation')).toBeTruthy();
    expect(screen.getByText(/subagent-research/)).toBeTruthy();
  });

  it('shows spinner for active (non-end) activities', () => {
    render(
      <ActivityBlock activities={[makeThinking({ status: 'delta', deltas: 'thinking...' })]} />,
    );
    const spinner = screen.getByTestId('activity-thinking').querySelector('.animate-spin');
    expect(spinner).toBeTruthy();
  });

  it('does not show spinner for ended activities', () => {
    render(<ActivityBlock activities={[makeThinking({ status: 'end' })]} />);
    const spinner = screen.getByTestId('activity-thinking').querySelector('.animate-spin');
    expect(spinner).toBeNull();
  });

  it('renders multiple activities in order', () => {
    render(
      <ActivityBlock
        activities={[
          makeThinking({ deltas: 'step 1' }),
          makeToolUse({ toolName: 'bash' }),
          makeDelegation({ toolName: 'subagent-ops' }),
        ]}
      />,
    );
    const thinking = screen.getByTestId('activity-thinking');
    const tools = screen.getAllByTestId('activity-tool-use');
    const delegations = screen.getAllByTestId('activity-delegation');
    expect(thinking).toBeTruthy();
    expect(tools).toHaveLength(1);
    expect(delegations).toHaveLength(1);
    expect(screen.getByText('bash')).toBeTruthy();
    expect(screen.getByText(/subagent-ops/)).toBeTruthy();
  });
});
