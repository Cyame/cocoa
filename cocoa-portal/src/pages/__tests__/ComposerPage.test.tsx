import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { parse_turn, SlashParserError, type Turn } from '@/lib/slash-parser';
import ComposerPage from '@/pages/ComposerPage';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

vi.mock('@/lib/slash-parser', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/slash-parser')>();
  return { ...actual, parse_turn: vi.fn(actual.parse_turn) };
});

const mockedApi = vi.mocked(api);
const mockedParseTurn = vi.mocked(parse_turn);

let realParseTurn: (rawText: string) => Turn;

beforeAll(async () => {
  const actual = await vi.importActual<typeof import('@/lib/slash-parser')>('@/lib/slash-parser');
  realParseTurn = actual.parse_turn;
});

afterAll(() => {
  vi.restoreAllMocks();
});

beforeEach(() => {
  mockedApi.mockReset();
  mockedParseTurn.mockReset();
  mockedParseTurn.mockImplementation(realParseTurn);
});

const PRESET = {
  id: 'preset-1',
  slug: 'unknown',
  name: 'Unknown Employee',
  version: '1.0.0',
  manifest: {
    model: 'gpt-4',
    prompt: 'You are a helpful agent.',
    skills: [],
    tools: [],
    commands: ['/plan', '/read', '/write'],
  },
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const MESSAGE_RESULT = {
  directives: ['/plan'],
  general_text: null,
  results: [],
};

function renderComposer() {
  return render(
    <MemoryRouter initialEntries={['/offices/office-1/composer']}>
      <Routes>
        <Route path="/offices/:id/composer" element={<ComposerPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('ComposerPage', () => {
  it('shows compartment preview when typing @slug /command', async () => {
    mockedApi.mockImplementation((path) => {
      if (typeof path === 'string' && path.startsWith('/employee-presets/')) {
        return Promise.resolve(PRESET) as never;
      }
      return Promise.resolve(MESSAGE_RESULT) as never;
    });

    renderComposer();

    const textarea = screen.getByLabelText('Turn text');
    await act(async () => {
      fireEvent.change(textarea, { target: { value: '@unknown /plan' } });
    });

    await waitFor(() => {
      expect(screen.getByText('@unknown')).toBeInTheDocument();
    });

    // /plan appears in both the directive card and the preset command hints.
    expect(screen.getAllByText('/plan').length).toBeGreaterThan(0);

    await waitFor(() => {
      expect(screen.getByText('Available commands:')).toBeInTheDocument();
    });
  });

  it('shows general compartment for bare text without directives', async () => {
    mockedApi.mockResolvedValue(MESSAGE_RESULT as never);

    renderComposer();

    const textarea = screen.getByLabelText('Turn text');
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'hello broadcast message' } });
    });

    await waitFor(() => {
      expect(screen.getByText('General')).toBeInTheDocument();
    });
    // Text appears in both the textarea value and the compartment card.
    expect(screen.getAllByText('hello broadcast message').length).toBeGreaterThan(0);
  });

  it('disables send button and shows error banner when parser throws', async () => {
    mockedParseTurn.mockImplementation(() => {
      throw new SlashParserError('mock parse error');
    });
    mockedApi.mockResolvedValue(MESSAGE_RESULT as never);

    renderComposer();

    const textarea = screen.getByLabelText('Turn text');
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'some text' } });
    });

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByText(/Parse error: mock parse error/)).toBeInTheDocument();

    const sendButton = screen.getByRole('button', { name: /Send/ });
    expect(sendButton).toBeDisabled();
  });

  it('posts message to /messaging/messages on send', async () => {
    const sendCall = vi.fn().mockResolvedValue(MESSAGE_RESULT as never);
    const presetCall = vi.fn().mockResolvedValue(PRESET as never);
    mockedApi.mockImplementation((path, init) => {
      if (typeof path === 'string' && path.startsWith('/employee-presets/')) {
        return presetCall(path) as never;
      }
      return sendCall(path, init) as never;
    });

    renderComposer();

    const textarea = screen.getByLabelText('Turn text');
    await act(async () => {
      fireEvent.change(textarea, { target: { value: '@unknown /plan' } });
    });

    await waitFor(() => {
      expect(screen.getByText('@unknown')).toBeInTheDocument();
    });

    const sendButton = screen.getByRole('button', { name: /Send/ });
    expect(sendButton).not.toBeDisabled();

    await act(async () => {
      fireEvent.click(sendButton);
    });

    await waitFor(() => {
      expect(sendCall).toHaveBeenCalledWith(
        '/messaging/messages',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ turn_text: '@unknown /plan', office_id: 'office-1' }),
        }),
      );
    });

    await waitFor(() => {
      expect(screen.getByText(/Sent 1 directive/)).toBeInTheDocument();
    });
  });
});
