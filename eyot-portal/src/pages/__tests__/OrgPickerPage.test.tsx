import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import type { Organization } from '@/lib/types';
import OrgPickerPage from '@/pages/OrgPickerPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function makeOrg(overrides: Partial<Organization>): Organization {
  return {
    id: 'org-1',
    slug: 'acme',
    name: 'Acme',
    description: null,
    system_hub_provider_id: null,
    system_hub_model: null,
    cerebellum_default_provider_id: null,
    cerebellum_default_model: null,
    use_proxy: false,
    proxy_host: null,
    proxy_port: null,
    proxy_username: null,
    proxy_password: null,
    created_at: '2026-08-03T00:00:00Z',
    updated_at: null,
    ...overrides,
  };
}

function renderPicker() {
  return render(
    <MemoryRouter initialEntries={['/orgs/picker']}>
      <Routes>
        <Route path="/orgs/picker" element={<OrgPickerPage />} />
        <Route path="/orgs/:orgId" element={<p>Org dashboard destination</p>} />
        <Route path="/login" element={<p>Login destination</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  useSessionStore.setState({
    token: 'jwt',
    user: null,
    currentOrgId: null,
    currentNamespaceId: null,
  });
});

describe('OrgPickerPage', () => {
  it('renders the empty-state create CTA when the account has no worlds', async () => {
    mockedApi.mockResolvedValue({ items: [], offset: 0, limit: 50, total: 0 });
    renderPicker();

    expect(await screen.findByText('No continents yet')).toBeInTheDocument();
    expect(screen.getByTestId('org-picker-empty-cta')).toHaveTextContent('Create continent');
  });

  it('lists the fetched worlds as selectable cards', async () => {
    mockedApi.mockResolvedValue({
      items: [makeOrg({}), makeOrg({ id: 'org-2', slug: 'omega', name: 'Omega' })],
      offset: 0,
      limit: 50,
      total: 2,
    });
    renderPicker();

    expect(await screen.findByText('Acme')).toBeInTheDocument();
    expect(screen.getByText('Omega')).toBeInTheDocument();
    expect(screen.getByTestId('org-card-acme')).toHaveTextContent('acme');
  });

  it('selecting a world sets the org context and enters its dashboard', async () => {
    mockedApi.mockResolvedValue({ items: [makeOrg({})], offset: 0, limit: 50, total: 1 });
    renderPicker();

    fireEvent.click(await screen.findByTestId('org-card-acme'));

    expect(useSessionStore.getState().currentOrgId).toBe('org-1');
    expect(await screen.findByText('Org dashboard destination')).toBeInTheDocument();
  });

  it('surfaces an error instead of crashing when the list payload is not paginated', async () => {
    mockedApi.mockResolvedValue([]);
    renderPicker();

    expect(
      await screen.findByText('Received an unexpected response from the server.'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('org-picker-empty-cta')).not.toBeInTheDocument();
  });

  it('creates a world and auto-enters it without returning to the picker', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/organizations' && init?.method === 'POST') {
        return Promise.resolve(makeOrg({ id: 'org-new', slug: 'acme', name: 'Acme' }));
      }
      if (path === '/organizations') {
        return Promise.resolve({ items: [], offset: 0, limit: 50, total: 0 });
      }
      return Promise.resolve(undefined);
    });
    renderPicker();

    fireEvent.click(await screen.findByTestId('org-picker-empty-cta'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Acme' } });
    fireEvent.change(screen.getByLabelText('Slug'), { target: { value: 'acme' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create and enter' }));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/organizations', {
        method: 'POST',
        body: JSON.stringify({ name: 'Acme', slug: 'acme', description: null }),
      });
    });
    expect(useSessionStore.getState().currentOrgId).toBe('org-new');
    expect(await screen.findByText('Org dashboard destination')).toBeInTheDocument();
  });

  it('surfaces a validation error for a malformed slug without navigating', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/organizations') {
        return Promise.resolve({ items: [], offset: 0, limit: 50, total: 0 });
      }
      return Promise.resolve(undefined);
    });
    renderPicker();

    fireEvent.click(await screen.findByTestId('org-picker-empty-cta'));
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Acme' } });
    fireEvent.change(screen.getByLabelText('Slug'), { target: { value: 'Bad Slug!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create and enter' }));

    expect(
      await screen.findByText(
        'Slug must start with a lowercase letter, then lowercase letters, digits, or hyphens.',
      ),
    ).toBeInTheDocument();
    expect(
      mockedApi.mock.calls.filter(
        ([path, init]) => path === '/organizations' && init?.method === 'POST',
      ),
    ).toHaveLength(0);
    expect(screen.queryByText('Org dashboard destination')).not.toBeInTheDocument();
  });
});
