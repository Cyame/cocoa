import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import type { OrgMember, UserBrief } from '@/lib/types';
import WorldMembersPage from '@/pages/WorldMembersPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

function makeMember(overrides: Partial<OrgMember> = {}): OrgMember {
  return {
    id: 'contract-1',
    user: { id: 'u-1', username: 'alice', email: 'alice@example.com', nickname: 'Alice' },
    atoms: [{ id: 'g-1', slug: 'can_manage_org_members', name: 'can_manage_org_members' }],
    created_at: '2026-08-03T00:00:00Z',
    ...overrides,
  };
}

function makeUser(overrides: Partial<UserBrief> = {}): UserBrief {
  return {
    id: 'u-1',
    username: 'alice',
    email: 'alice@example.com',
    nickname: 'Alice',
    ...overrides,
  };
}

function renderMembersPage() {
  return render(
    <MemoryRouter initialEntries={['/orgs/org-1/members']}>
      <Routes>
        <Route path="/orgs/:orgId/members" element={<WorldMembersPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  useSessionStore.setState({
    token: 'jwt',
    user: null,
    currentOrgId: 'org-1',
    currentNamespaceId: null,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('WorldMembersPage', () => {
  it('renders member usernames, emails and atom grants (no UUID wall)', async () => {
    mockedApi.mockResolvedValue({ items: [makeMember()] });
    renderMembersPage();

    expect(await screen.findByText('Alice')).toBeInTheDocument();
    expect(screen.getByText(/alice · alice@example\.com/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Manage world members/ })).toBeInTheDocument();
    expect(screen.queryByText('contract-1')).not.toBeInTheDocument();
    expect(screen.getByText('1 members')).toBeInTheDocument();
  });

  it('offers the full 16-atom catalog as toggle buttons per member', async () => {
    mockedApi.mockResolvedValue({ items: [makeMember()] });
    renderMembersPage();

    expect(await screen.findByText('Alice')).toBeInTheDocument();
    const expectedNames = [
      'Manage world',
      'Manage world members',
      'Manage namespaces',
      'Manage workspaces',
      'Edit workspaces',
      'View workspaces',
      'Operate workspaces',
      'Manage genes',
      'Manage capabilities',
      'Manage AI genes',
      'Clone base classes',
      'Clone entities',
      'Clone world',
      'Clone workspace',
      'Manage knowledge',
      'Manage meetings',
    ];
    for (const name of expectedNames) {
      expect(
        screen.getByRole('button', { name: new RegExp(`^${name}: (on|off)$`) }),
      ).toBeInTheDocument();
    }
  });

  it('renders an empty state when the world has no members', async () => {
    mockedApi.mockResolvedValue({ items: [] });
    renderMembersPage();

    expect(await screen.findByText('No members yet')).toBeInTheDocument();
  });

  it('surfaces a localized message when stripping your own permission is rejected', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    mockedApi.mockImplementation((path, init) => {
      if (
        path === '/organizations/org-1/members' &&
        (init === undefined || init.method === 'GET')
      ) {
        return Promise.resolve({ items: [makeMember()] });
      }
      if (path === '/organizations/org-1/members/contract-1' && init?.method === 'DELETE') {
        return Promise.reject(
          new ApiError(400, {
            error_code: 'errors.org.cannot_lock_self',
            message_key: 'organization.cannot_lock_self',
            message: 'Cannot strip your own last can_manage_org_members grant',
          }),
        );
      }
      return Promise.resolve({ items: [] });
    });
    renderMembersPage();

    fireEvent.click(await screen.findByRole('button', { name: 'Remove' }));
    expect(
      await screen.findByText('Cannot remove your own world-management permission.'),
    ).toBeInTheDocument();
  });

  it('adds a member picked from search results with the granted atom set', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/organizations/org-1/members') {
        return Promise.resolve({ items: [] });
      }
      if (path === '/users?q=alice&limit=20') {
        return Promise.resolve({ items: [makeUser()] });
      }
      return Promise.resolve({ items: [] });
    });
    renderMembersPage();

    fireEvent.click(await screen.findByTestId('world-members-add-toggle'));
    fireEvent.change(screen.getByLabelText('Search users by username or email'), {
      target: { value: 'alice' },
    });
    fireEvent.click(await screen.findByText('alice'));
    fireEvent.click(screen.getByLabelText('Manage world members'));
    fireEvent.click(screen.getByTestId('world-members-submit'));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/organizations/org-1/members', {
        method: 'POST',
        body: JSON.stringify({ user_id: 'u-1', atom_slugs: ['can_manage_org_members'] }),
      });
    });
  });

  it('submits the typed query when no search result was picked', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/organizations/org-1/members') {
        return Promise.resolve({ items: [] });
      }
      if (path === '/users?q=some-user-id&limit=20') {
        return Promise.resolve({ items: [] });
      }
      return Promise.resolve({ items: [] });
    });
    renderMembersPage();

    fireEvent.click(await screen.findByTestId('world-members-add-toggle'));
    fireEvent.change(screen.getByLabelText('Search users by username or email'), {
      target: { value: 'some-user-id' },
    });
    fireEvent.click(screen.getByTestId('world-members-submit'));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/organizations/org-1/members', {
        method: 'POST',
        body: JSON.stringify({ q: 'some-user-id', atom_slugs: [] }),
      });
    });
  });

  it('keeps the submit disabled while the form has no user id or query', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/organizations/org-1/members') {
        return Promise.resolve({ items: [] });
      }
      return Promise.resolve({ items: [] });
    });
    renderMembersPage();

    fireEvent.click(await screen.findByTestId('world-members-add-toggle'));
    const submit = screen.getByTestId('world-members-submit');
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByLabelText('Search users by username or email'), {
      target: { value: 'alice' },
    });
    expect(screen.getByTestId('world-members-submit')).toBeEnabled();
  });
});
