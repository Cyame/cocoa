import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import TopologyToolbar from '@/components/TopologyToolbar';
import { useSelectedStore } from '@/stores/selected';

beforeEach(() => {
  useSelectedStore.setState({ officeId: null, instanceId: null, interactionMode: 'select' });
});

afterEach(() => {
  useSelectedStore.setState({ officeId: null, instanceId: null, interactionMode: 'select' });
});

describe('TopologyToolbar', () => {
  it('switches the active mode when a toolbar button is clicked', () => {
    render(<TopologyToolbar />);

    const selectBtn = screen.getByTestId('topology-toolbar-select');
    expect(selectBtn.getAttribute('data-active')).toBe('true');

    const connectBtn = screen.getByTestId('topology-toolbar-connect');
    fireEvent.click(connectBtn);

    expect(useSelectedStore.getState().interactionMode).toBe('connect');
    expect(connectBtn.getAttribute('data-active')).toBe('true');
    expect(selectBtn.getAttribute('data-active')).toBe('false');

    const moveBtn = screen.getByTestId('topology-toolbar-move');
    fireEvent.click(moveBtn);
    expect(useSelectedStore.getState().interactionMode).toBe('move');
    expect(moveBtn.getAttribute('data-active')).toBe('true');
  });

  it('toggles the interaction mode via V / C / M keyboard shortcuts', () => {
    render(<TopologyToolbar />);

    expect(useSelectedStore.getState().interactionMode).toBe('select');

    fireEvent.keyDown(window, { key: 'c' });
    expect(useSelectedStore.getState().interactionMode).toBe('connect');

    fireEvent.keyDown(window, { key: 'M' });
    expect(useSelectedStore.getState().interactionMode).toBe('move');

    fireEvent.keyDown(window, { key: 'v' });
    expect(useSelectedStore.getState().interactionMode).toBe('select');
  });
});
