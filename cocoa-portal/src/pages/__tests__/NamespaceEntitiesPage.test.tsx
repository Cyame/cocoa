import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { fetchMe } from '@/lib/api/auth';
import NamespaceEntitiesPage from '@/pages/NamespaceEntitiesPage';
import { useSessionStore } from '@/stores/session';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

vi.mock('@/lib/api/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/auth')>();
  return { ...actual, fetchMe: vi.fn() };
});

const mockedApi = vi.mocked(api);
const mockedFetchMe = vi.mocked(fetchMe);

const ENTITY_ROW = {
  id: 'entity-1',
  namespace_id: 'ns-1',
  name: 'scout',
  slug: 'scout',
  rank: 'oracle',
  preset_slug: 'base',
  display_name: 'Scout',
  display_color: null,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/orgs/org-1/namespaces/ns-1/entities']}>
      <Routes>
        <Route path="/orgs/:orgId/namespaces/:nsId/entities" element={<NamespaceEntitiesPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockedApi.mockReset();
  mockedFetchMe.mockReset();
  useSessionStore.setState({
    token: 'jwt',
    user: {
      user_id: 'user-1',
      username: 'operator',
      identity: 'org',
      is_super_admin: false,
      token: 'jwt',
    },
    currentOrgId: null,
    currentNamespaceId: null,
  });
});

describe('NamespaceEntitiesPage', () => {
  it('labels the per-row distill button with the distil-transmute label', async () => {
    mockedFetchMe.mockResolvedValue({
      user_id: 'user-1',
      username: 'operator',
      org_identity: null,
    } as never);
    mockedApi.mockImplementation(async (path: string) => {
      if (path.startsWith('/entities')) {
        return {
          items: [ENTITY_ROW],
          offset: 0,
          limit: 200,
          total: 1,
        };
      }
      throw new Error(`unexpected api call: ${path}`);
    });

    renderPage();

    const distillButton = await screen.findByTestId(`entity-transmute-${ENTITY_ROW.id}`);
    await waitFor(() => {
      expect(distillButton.textContent).toContain('Distill / Transmute');
    });
  });
});
