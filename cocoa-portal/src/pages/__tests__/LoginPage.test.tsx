import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import LoginPage from '@/pages/LoginPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function renderLogin(initialPath = '/login') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/offices" element={<p>Office destination</p>} />
        <Route path="/offices/:officeId" element={<p>Office detail destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  useSessionStore.setState({ token: null, user: null });
});

describe('LoginPage', () => {
  it('shows an accessible username and password form', () => {
    renderLogin();

    expect(screen.getByRole('textbox', { name: 'Username' })).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('stores the token and lands on the first existing office after login', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/auth/login') {
        return Promise.resolve({ access_token: 'jwt-token', token_type: 'bearer' });
      }
      if (path === '/offices') {
        return Promise.resolve({
          items: [{ id: 'office-existing', name: 'Existing', slug: 'existing' }],
        });
      }
      throw new Error(`unexpected api call: ${path}`);
    });
    renderLogin();

    fireEvent.change(screen.getByRole('textbox', { name: 'Username' }), {
      target: { value: 'operator' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'secret-pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username: 'operator', password: 'secret-pass' }),
      });
    });
    expect(useSessionStore.getState().token).toBe('jwt-token');
    expect(await screen.findByText('Office detail destination')).toBeInTheDocument();
  });

  it('falls back to the office list when the login user has no offices', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/auth/login') {
        return Promise.resolve({ access_token: 'jwt-token', token_type: 'bearer' });
      }
      if (path === '/offices') {
        return Promise.resolve({ items: [] });
      }
      throw new Error(`unexpected api call: ${path}`);
    });
    renderLogin();

    fireEvent.change(screen.getByRole('textbox', { name: 'Username' }), {
      target: { value: 'fresh' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'secret-pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByText('Office destination')).toBeInTheDocument();
  });

  it('shows an authentication error after a 401 response', async () => {
    mockedApi.mockRejectedValue(new ApiError(401, { message: 'Invalid username or password' }));
    renderLogin();

    fireEvent.change(screen.getByRole('textbox', { name: 'Username' }), {
      target: { value: 'operator' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'wrong-pass' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password');
    expect(useSessionStore.getState().token).toBeNull();
  });

  it('renders register mode with email field when ?mode=register', () => {
    renderLogin('/login?mode=register');

    expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Email' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Create account' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Sign in/i })).toHaveAttribute('href', '/login');
  });

  it('lands directly on the personal workspace after register', async () => {
    mockedApi.mockResolvedValue({
      access_token: 'new-jwt',
      token_type: 'bearer',
      office_id: 'office-personal',
    });
    renderLogin('/login?mode=register');

    fireEvent.change(screen.getByRole('textbox', { name: 'Username' }), {
      target: { value: 'newbie' },
    });
    fireEvent.change(screen.getByRole('textbox', { name: 'Email' }), {
      target: { value: 'newbie@test.local' },
    });
    fireEvent.change(screen.getByLabelText('Password'), {
      target: { value: 'securepass1' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/auth/register', {
        method: 'POST',
        body: JSON.stringify({
          username: 'newbie',
          email: 'newbie@test.local',
          password: 'securepass1',
        }),
      });
    });
    expect(useSessionStore.getState().token).toBe('new-jwt');
    expect(await screen.findByText('Office detail destination')).toBeInTheDocument();
  });

  it('renders sign-in mode by default', () => {
    renderLogin('/login');

    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Email' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Register/i })).toHaveAttribute(
      'href',
      '/login?mode=register',
    );
  });
});
