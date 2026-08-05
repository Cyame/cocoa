import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useRef, useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CommandAutocomplete } from '@/components/CommandAutocomplete';
import { api } from '@/lib/api';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function Wrapper({
  targetSlugs = [] as readonly string[],
  presetByEntitySlug = {} as Readonly<Record<string, string | null | undefined>>,
}) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  return (
    <div className="relative">
      <textarea
        ref={textareaRef}
        data-testid="composer"
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <CommandAutocomplete
        textareaRef={textareaRef}
        text={text}
        onTextChange={setText}
        targetSlugs={targetSlugs}
        presetByEntitySlug={presetByEntitySlug}
      />
    </div>
  );
}

function typeAndPlaceCursor(textarea: HTMLTextAreaElement, value: string) {
  fireEvent.change(textarea, { target: { value } });
  const pos = value.length;
  textarea.setSelectionRange(pos, pos);
  fireEvent.select(textarea);
}

beforeEach(() => {
  mockedApi.mockReset();
});

describe('CommandAutocomplete', () => {
  it('shows GLOBAL + CONTROL + LEARNING commands when / is typed with no target', async () => {
    render(<Wrapper />);
    const textarea = screen.getByTestId('composer') as HTMLTextAreaElement;

    act(() => {
      typeAndPlaceCursor(textarea, '/');
    });

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    expect(screen.getByText('/read')).toBeInTheDocument();
    expect(screen.getByText('/list')).toBeInTheDocument();
    expect(screen.getByText('/write')).toBeInTheDocument();
    expect(screen.getByText('/archive')).toBeInTheDocument();

    expect(screen.getByText('/interrupt')).toBeInTheDocument();
    expect(screen.getByText('/pause')).toBeInTheDocument();
    expect(screen.getByText('/resume')).toBeInTheDocument();
    expect(screen.getByText('/status')).toBeInTheDocument();
    expect(screen.getByText('/snapshot')).toBeInTheDocument();

    expect(screen.getByText('/distill')).toBeInTheDocument();
    expect(screen.getByText('/consolidate')).toBeInTheDocument();
    expect(screen.getByText('/reflect')).toBeInTheDocument();
  });

  it('includes per-preset commands when a target slug is present', async () => {
    mockedApi.mockResolvedValue({
      id: 'preset-1',
      slug: '密士',
      name: 'Mishi',
      version: '1.0.0',
      manifest: {
        model: 'gpt-4',
        prompt: 'You are a helpful agent.',
        skills: [],
        tools: [],
        commands: ['/plan', '/review'],
      },
      created_at: '2026-07-01T00:00:00Z',
      updated_at: '2026-07-01T00:00:00Z',
    } as never);

    render(<Wrapper targetSlugs={['密士']} presetByEntitySlug={{ 密士: 'mi-shi' }} />);
    const textarea = screen.getByTestId('composer') as HTMLTextAreaElement;

    act(() => {
      typeAndPlaceCursor(textarea, '@密士 /');
    });

    await waitFor(() => {
      expect(screen.getByText('/plan')).toBeInTheDocument();
    });

    expect(screen.getByText('/review')).toBeInTheDocument();
    expect(screen.getByText('/read')).toBeInTheDocument();
    expect(screen.getByText('/interrupt')).toBeInTheDocument();
    expect(screen.getByText('/distill')).toBeInTheDocument();
    // Commands are read from the base-class GET (junction-aggregated mirror),
    // not the legacy employee-presets endpoint.
    expect(mockedApi).toHaveBeenCalledWith(`/base-classes/${encodeURIComponent('mi-shi')}`);
  });

  it('inserts the highlighted command into the textarea on Enter when a filter is typed', async () => {
    render(<Wrapper />);
    const textarea = screen.getByTestId('composer') as HTMLTextAreaElement;

    act(() => {
      typeAndPlaceCursor(textarea, '/r');
    });

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    act(() => {
      fireEvent.keyDown(textarea, { key: 'Enter' });
    });

    await waitFor(() => {
      expect(textarea.value).toBe('/read ');
    });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('keeps bare "/" editable on Enter (baseline: menu stays open, no forced pick)', async () => {
    render(<Wrapper />);
    const textarea = screen.getByTestId('composer') as HTMLTextAreaElement;

    act(() => {
      typeAndPlaceCursor(textarea, '/');
    });

    await waitFor(() => {
      expect(screen.getByRole('listbox')).toBeInTheDocument();
    });

    act(() => {
      fireEvent.keyDown(textarea, { key: 'Enter' });
    });

    // Bare "/" stays editable — Enter does not force a command pick, and the
    // suggestion menu remains open so the user can keep typing a filter.
    expect(textarea.value).toBe('/');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });
});
