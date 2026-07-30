import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import BatchRestartModal, { type OutdatedInstanceRow } from '@/components/BatchRestartModal';
import { ApiError } from '@/lib/api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const NOW = '2026-07-29T12:00:00Z';
const UPDATED_3H_AGO = '2026-07-29T09:00:00Z';
const UPDATED_1D_AGO = '2026-07-28T12:00:00Z';
const UPDATED_2M_AGO = '2026-07-29T11:58:00Z';

function row(
  overrides: Partial<OutdatedInstanceRow> & { readonly instance_id: string },
): OutdatedInstanceRow {
  return {
    employee_id: `emp-${overrides.instance_id}`,
    employee_label: `Employee ${overrides.instance_id}`,
    loop_status: 'paused',
    active_hash: 'abcdef1234567890',
    outdated_for_iso: UPDATED_3H_AGO,
    is_running: false,
    ...overrides,
  };
}

const OUTDATED_ROWS: readonly OutdatedInstanceRow[] = [
  row({
    instance_id: 'inst-1',
    employee_label: 'Researcher Alpha',
    loop_status: 'paused',
    outdated_for_iso: UPDATED_1D_AGO,
  }),
  row({
    instance_id: 'inst-2',
    employee_label: 'Researcher Beta',
    loop_status: 'idle',
    outdated_for_iso: UPDATED_3H_AGO,
  }),
  row({
    instance_id: 'inst-3',
    employee_label: 'Researcher Gamma',
    loop_status: 'running',
    outdated_for_iso: UPDATED_2M_AGO,
    is_running: true,
  }),
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderModal(overrides: Partial<React.ComponentProps<typeof BatchRestartModal>> = {}) {
  const onConfirm = vi.fn().mockResolvedValue(true);
  const onClose = vi.fn();
  const props = {
    isOpen: true,
    outdatedInstances: OUTDATED_ROWS,
    totalInstanceCount: 5,
    onClose,
    onConfirm,
    ...overrides,
  } satisfies React.ComponentProps<typeof BatchRestartModal>;
  const view = render(<BatchRestartModal {...props} />);
  return { ...view, onConfirm, onClose, props };
}

beforeEach(() => {
  vi.setSystemTime(new Date(NOW));
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BatchRestartModal', () => {
  it('renders the title, subtitle, and one row per outdated instance', () => {
    renderModal();

    expect(screen.getByRole('dialog', { name: 'Apply updated configuration' })).toBeInTheDocument();
    expect(
      screen.getByText(
        '3 of 5 instances are running on an older config — restart to apply changes',
      ),
    ).toBeInTheDocument();

    for (const r of OUTDATED_ROWS) {
      expect(screen.getByTestId(`batch-restart-row-${r.instance_id}`)).toBeInTheDocument();
    }
  });

  it('selects every non-running instance by default and skips running ones', () => {
    renderModal();

    const checkbox1 = screen.getByTestId('batch-restart-checkbox-inst-1');
    const checkbox2 = screen.getByTestId('batch-restart-checkbox-inst-2');
    const checkbox3 = screen.getByTestId('batch-restart-checkbox-inst-3');

    expect(checkbox1).toBeChecked();
    expect(checkbox2).toBeChecked();
    expect(checkbox3).not.toBeChecked();
    expect(checkbox3).toBeDisabled();

    expect(screen.getByTestId('batch-restart-selected-count')).toHaveTextContent('2/2');
  });

  it('toggles a checkbox and updates the selected count', () => {
    renderModal();

    const checkbox1 = screen.getByTestId('batch-restart-checkbox-inst-1');
    fireEvent.click(checkbox1);
    expect(checkbox1).not.toBeChecked();
    expect(screen.getByTestId('batch-restart-selected-count')).toHaveTextContent('1/2');
  });

  it('sorts rows by outdated duration ascending (oldest first)', () => {
    renderModal();

    const items = screen.getAllByTestId(/^batch-restart-row-/);
    expect(items.map((el) => el.getAttribute('data-testid'))).toEqual([
      'batch-restart-row-inst-1',
      'batch-restart-row-inst-2',
      'batch-restart-row-inst-3',
    ]);
  });

  it('surfaces a running-disabled hint when at least one outdated instance is running', () => {
    renderModal();

    expect(screen.getByTestId('batch-restart-running-hint')).toBeInTheDocument();
  });

  it('does not surface the running-disabled hint when all selectable', () => {
    renderModal({
      outdatedInstances: OUTDATED_ROWS.filter((r) => !r.is_running),
    });

    expect(screen.queryByTestId('batch-restart-running-hint')).not.toBeInTheDocument();
  });

  it('switches the toggle-all label to "Clear all" once everything is selected', () => {
    renderModal();

    const toggle = screen.getByTestId('batch-restart-toggle-all');
    expect(toggle).toHaveTextContent('Clear all');
    fireEvent.click(toggle);
    expect(toggle).toHaveTextContent('Select all');
    expect(screen.getByTestId('batch-restart-selected-count')).toHaveTextContent('0/2');
  });

  it('requires the confirmation step before calling onConfirm', async () => {
    const { onConfirm } = renderModal();

    fireEvent.click(screen.getByTestId('batch-restart-submit'));

    expect(screen.getByTestId('batch-restart-confirm-step')).toBeInTheDocument();
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('batch-restart-submit'));

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });
    expect(onConfirm).toHaveBeenCalledWith(['inst-1', 'inst-2']);
  });

  it('renders an empty state when no instances are outdated', () => {
    renderModal({ outdatedInstances: [] });

    expect(screen.getByTestId('batch-restart-empty')).toBeInTheDocument();
    expect(screen.getByTestId('batch-restart-submit')).toBeDisabled();
  });

  it('closes the modal via the X button and onClose', () => {
    const { onClose } = renderModal();

    fireEvent.click(screen.getByTestId('batch-restart-close'));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('closes the modal when Escape is pressed', () => {
    const { onClose } = renderModal();

    fireEvent.keyDown(window, { key: 'Escape' });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders nothing when isOpen is false', () => {
    renderModal({ isOpen: false });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('surfaces the running-conflict error when onConfirm rejects with ApiError 409', async () => {
    const onConfirm = vi
      .fn()
      .mockRejectedValue(new ApiError(409, { message: 'Batch contains running' }));

    renderModal({ onConfirm });

    fireEvent.click(screen.getByTestId('batch-restart-submit'));
    fireEvent.click(screen.getByTestId('batch-restart-submit'));

    expect(await screen.findByTestId('batch-restart-error')).toHaveTextContent(
      'Some selected instances are still running. Stop them and retry.',
    );
  });

  it('falls back to a generic error when onConfirm rejects with a non-ApiError', async () => {
    const onConfirm = vi.fn().mockRejectedValue(new Error('boom'));

    renderModal({ onConfirm });

    fireEvent.click(screen.getByTestId('batch-restart-submit'));
    fireEvent.click(screen.getByTestId('batch-restart-submit'));

    expect(await screen.findByTestId('batch-restart-error')).toHaveTextContent('boom');
  });

  it('shows the short hash and a status badge per row', () => {
    renderModal();

    const row1 = screen.getByTestId('batch-restart-row-inst-1');
    expect(row1).toHaveTextContent('Researcher Alpha');
    expect(row1).toHaveTextContent('#abcdef12');
    expect(row1).toHaveTextContent('paused');
  });
});
