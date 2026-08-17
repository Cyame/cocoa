import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CloneDialog from '@/components/CloneDialog';
import { toSlug } from '@/lib/slug';

const defaultProps = {
  open: true,
  title: 'Clone progenitor',
  confirmMessage: 'Clone base class "Test"?',
  confirmLabel: 'Clone',
  busy: false,
  onConfirm: vi.fn(),
  onCancel: vi.fn(),
};

describe('CloneDialog', () => {
  it('renders nothing when open is false', () => {
    render(<CloneDialog {...defaultProps} open={false} />);
    expect(screen.queryByTestId('clone-dialog')).toBeNull();
  });

  it('renders name and slug inputs when open', () => {
    render(<CloneDialog {...defaultProps} />);
    expect(screen.getByTestId('clone-dialog')).toBeInTheDocument();
    expect(screen.getByTestId('clone-dialog-name')).toBeInTheDocument();
    expect(screen.getByTestId('clone-dialog-slug')).toBeInTheDocument();
  });

  it('disables confirm button when slug is invalid kebab-case', () => {
    render(<CloneDialog {...defaultProps} />);
    const slugInput = screen.getByTestId('clone-dialog-slug');
    fireEvent.change(slugInput, { target: { value: 'Invalid Slug' } });
    expect(screen.getByTestId('clone-dialog-slug-error')).toBeInTheDocument();
    expect(screen.getByTestId('clone-dialog-confirm')).toBeDisabled();
  });

  it('enables confirm button when slug is valid kebab-case', () => {
    render(<CloneDialog {...defaultProps} />);
    const slugInput = screen.getByTestId('clone-dialog-slug');
    fireEvent.change(slugInput, { target: { value: 'my-clone' } });
    expect(screen.queryByTestId('clone-dialog-slug-error')).toBeNull();
    expect(screen.getByTestId('clone-dialog-confirm')).not.toBeDisabled();
  });

  it('enables confirm button when slug is empty (optional)', () => {
    render(<CloneDialog {...defaultProps} />);
    expect(screen.queryByTestId('clone-dialog-slug-error')).toBeNull();
    expect(screen.getByTestId('clone-dialog-confirm')).not.toBeDisabled();
  });

  it('sends name and slug in payload on confirm', () => {
    const onConfirm = vi.fn();
    render(<CloneDialog {...defaultProps} onConfirm={onConfirm} />);
    fireEvent.change(screen.getByTestId('clone-dialog-name'), {
      target: { value: 'My Clone' },
    });
    fireEvent.change(screen.getByTestId('clone-dialog-slug'), {
      target: { value: 'my-clone' },
    });
    fireEvent.click(screen.getByTestId('clone-dialog-confirm'));
    expect(onConfirm).toHaveBeenCalledWith({ name: 'My Clone', slug: 'my-clone' });
  });

  it('sends empty payload when both inputs are blank', () => {
    const onConfirm = vi.fn();
    render(<CloneDialog {...defaultProps} onConfirm={onConfirm} />);
    fireEvent.click(screen.getByTestId('clone-dialog-confirm'));
    expect(onConfirm).toHaveBeenCalledWith({});
  });

  it('trims whitespace from name and slug before sending', () => {
    const onConfirm = vi.fn();
    render(<CloneDialog {...defaultProps} onConfirm={onConfirm} />);
    fireEvent.change(screen.getByTestId('clone-dialog-name'), {
      target: { value: '  Spaced  ' },
    });
    fireEvent.change(screen.getByTestId('clone-dialog-slug'), {
      target: { value: '  valid-slug  ' },
    });
    fireEvent.click(screen.getByTestId('clone-dialog-confirm'));
    expect(onConfirm).toHaveBeenCalledWith({ name: 'Spaced', slug: 'valid-slug' });
  });

  it('calls onCancel when cancel button is clicked', () => {
    const onCancel = vi.fn();
    render(<CloneDialog {...defaultProps} onCancel={onCancel} />);
    fireEvent.click(screen.getByTestId('clone-dialog-cancel'));
    expect(onCancel).toHaveBeenCalled();
  });

  it('disables confirm button when busy', () => {
    render(<CloneDialog {...defaultProps} busy />);
    expect(screen.getByTestId('clone-dialog-confirm')).toBeDisabled();
  });

  it('auto-fills the slug as pinyin kebab when a Chinese name is typed', () => {
    render(<CloneDialog {...defaultProps} />);
    fireEvent.change(screen.getByTestId('clone-dialog-name'), {
      target: { value: '测试神职' },
    });
    expect((screen.getByTestId('clone-dialog-slug') as HTMLInputElement).value).toBe(
      toSlug('测试神职'),
    );
  });

  it('does not overwrite the slug after the user manually edits it', () => {
    render(<CloneDialog {...defaultProps} />);
    fireEvent.change(screen.getByTestId('clone-dialog-slug'), {
      target: { value: 'my-slug' },
    });
    fireEvent.change(screen.getByTestId('clone-dialog-name'), {
      target: { value: '测试神职' },
    });
    expect((screen.getByTestId('clone-dialog-slug') as HTMLInputElement).value).toBe('my-slug');
  });

  it('clears the auto-filled slug when the name is cleared', () => {
    render(<CloneDialog {...defaultProps} />);
    fireEvent.change(screen.getByTestId('clone-dialog-name'), {
      target: { value: '测试神职' },
    });
    fireEvent.change(screen.getByTestId('clone-dialog-name'), {
      target: { value: '' },
    });
    expect((screen.getByTestId('clone-dialog-slug') as HTMLInputElement).value).toBe('');
  });
});
