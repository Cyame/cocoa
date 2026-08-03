import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import type { NamespaceContractDetail } from '@/lib/api/contracts';
import NamespaceContractsPage from '@/pages/NamespaceContractsPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const INHERITED_ORG_ATOMS = [
  { id: 'g-can_edit_workspace', slug: 'can_edit_workspace', name: 'can_edit_workspace' },
  {
    id: 'g-can_manage_organization',
    slug: 'can_manage_organization',
    name: 'can_manage_organization',
  },
];

function makeContract(
  namespaceSlugs: readonly string[],
  overrides: Partial<NamespaceContractDetail> = {},
): NamespaceContractDetail {
  return {
    contract_id: 'c-1',
    user: { id: 'u-1', username: 'alice', email: 'alice@example.com', nickname: 'Alice' },
    namespace_atoms: namespaceSlugs.map((slug) => ({ id: `g-${slug}`, slug, name: slug })),
    inherited_org_atoms: INHERITED_ORG_ATOMS,
    created_at: '2026-08-03T00:00:00Z',
    ...overrides,
  };
}

function renderContractsPage() {
  return render(
    <MemoryRouter initialEntries={['/orgs/org-1/namespaces/ns-1/contracts']}>
      <Routes>
        <Route
          path="/orgs/:orgId/namespaces/:nsId/contracts"
          element={<NamespaceContractsPage />}
        />
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
    currentNamespaceId: 'ns-1',
  });
});

describe('NamespaceContractsPage', () => {
  it('renders contract users and separates namespace from inherited atoms', async () => {
    mockedApi.mockResolvedValue({
      items: [makeContract(['can_edit_workspace', 'can_manage_knowledge'])],
      limit: 200,
      offset: 0,
      total: 1,
    });
    renderContractsPage();

    expect(await screen.findByText('Alice')).toBeInTheDocument();
    expect(screen.getByText(/alice · alice@example\.com/)).toBeInTheDocument();
    const inheritedSection = screen.getByTestId('inherited-atoms');
    expect(within(inheritedSection).getByText('can_manage_organization')).toBeInTheDocument();
    expect(within(inheritedSection).queryAllByRole('button')).toHaveLength(0);
    expect(screen.getByText('1 contracts')).toBeInTheDocument();
  });

  it('removing a namespace atom sends only the namespace_atoms in the PATCH', async () => {
    let namespaceSlugs: string[] = ['can_edit_workspace', 'can_manage_knowledge'];
    mockedApi.mockImplementation((path, init) => {
      if (
        path === '/namespaces/ns-1/contracts?limit=200&offset=0&include_inherited=true' &&
        (init === undefined || init.method === 'GET')
      ) {
        return Promise.resolve({
          items: [makeContract(namespaceSlugs)],
          limit: 200,
          offset: 0,
          total: 1,
        });
      }
      if (path === '/namespaces/ns-1/contracts/c-1/atoms' && init?.method === 'PATCH') {
        const body = JSON.parse(init.body as string) as { atom_slugs: string[] };
        namespaceSlugs = body.atom_slugs;
        return Promise.resolve(makeContract(namespaceSlugs));
      }
      return Promise.resolve({ items: [], limit: 200, offset: 0, total: 0 });
    });
    renderContractsPage();

    fireEvent.click(await screen.findByTitle('Remove atom: can_manage_knowledge'));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/namespaces/ns-1/contracts/c-1/atoms', {
        method: 'PATCH',
        body: JSON.stringify({ atom_slugs: ['can_edit_workspace'] }),
      });
    });
    const inheritedSection = screen.getByTestId('inherited-atoms');
    expect(screen.getAllByText('can_edit_workspace').length).toBeGreaterThanOrEqual(2);
    expect(within(inheritedSection).getByText('can_manage_organization')).toBeInTheDocument();
  });

  it('adding an atom appends it to namespace_atoms without touching inherited atoms', async () => {
    let namespaceSlugs: string[] = ['can_edit_workspace'];
    mockedApi.mockImplementation((path, init) => {
      if (
        path === '/namespaces/ns-1/contracts?limit=200&offset=0&include_inherited=true' &&
        (init === undefined || init.method === 'GET')
      ) {
        return Promise.resolve({
          items: [makeContract(namespaceSlugs)],
          limit: 200,
          offset: 0,
          total: 1,
        });
      }
      if (path === '/namespaces/ns-1/contracts/c-1/atoms' && init?.method === 'PATCH') {
        const body = JSON.parse(init.body as string) as { atom_slugs: string[] };
        namespaceSlugs = body.atom_slugs;
        return Promise.resolve(makeContract(namespaceSlugs));
      }
      return Promise.resolve({ items: [], limit: 200, offset: 0, total: 0 });
    });
    renderContractsPage();

    fireEvent.click(await screen.findByTitle('Add atom: can_operate_workspace'));

    await waitFor(() => {
      expect(mockedApi).toHaveBeenCalledWith('/namespaces/ns-1/contracts/c-1/atoms', {
        method: 'PATCH',
        body: JSON.stringify({ atom_slugs: ['can_edit_workspace', 'can_operate_workspace'] }),
      });
    });
    const inheritedSection = screen.getByTestId('inherited-atoms');
    expect(within(inheritedSection).getByText('can_manage_organization')).toBeInTheDocument();
  });

  it('renders an empty state when the namespace has no contracts', async () => {
    mockedApi.mockResolvedValue({ items: [], limit: 200, offset: 0, total: 0 });
    renderContractsPage();

    expect(await screen.findByText('No contracts in this namespace yet.')).toBeInTheDocument();
  });
});
