import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError } from '@/lib/api';
import LoginPage from '@/pages/LoginPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/offices" element={<p>Office destination</p>} />
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

  it('stores the token and redirects after successful login', async () => {
    mockedApi.mockResolvedValue({ access_token: 'jwt-token', token_type: 'bearer' });
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
});
