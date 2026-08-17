import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '@/lib/api';
import {
  createKnowledgeEntry,
  deleteKnowledgeEntry,
  fetchKnowledgeDimensions,
  fetchKnowledgeEntries,
  type KnowledgeDimension,
  type KnowledgeEntry,
} from '@/lib/api/knowledge';
import { fetchNamespaces } from '@/lib/api/namespaces';
import { fetchOrganization } from '@/lib/api/organizations';
import { fetchWorkspaces } from '@/lib/api/workspaces';
import KnowledgePage from '@/pages/KnowledgePage';

vi.mock('@/lib/api/knowledge', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api/knowledge')>();
  return {
    ...actual,
    fetchKnowledgeEntries: vi.fn(),
    fetchKnowledgeDimensions: vi.fn(),
    createKnowledgeEntry: vi.fn(),
    updateKnowledgeEntry: vi.fn(),
    deleteKnowledgeEntry: vi.fn(),
    createKnowledgeDimension: vi.fn(),
    deleteKnowledgeDimension: vi.fn(),
  };
});

vi.mock('@/lib/api/namespaces', () => ({ fetchNamespaces: vi.fn() }));

vi.mock('@/lib/api/organizations', () => ({ fetchOrganization: vi.fn() }));

vi.mock('@/lib/api/workspaces', () => ({
  fetchWorkspaces: vi.fn(),
  fetchWorkspace: vi.fn(),
}));

const mockedFetchEntries = vi.mocked(fetchKnowledgeEntries);
const mockedFetchDimensions = vi.mocked(fetchKnowledgeDimensions);
const mockedCreateEntry = vi.mocked(createKnowledgeEntry);
const mockedDeleteEntry = vi.mocked(deleteKnowledgeEntry);
const mockedFetchOrganization = vi.mocked(fetchOrganization);
const mockedFetchNamespaces = vi.mocked(fetchNamespaces);
const mockedFetchWorkspaces = vi.mocked(fetchWorkspaces);

const org = {
  id: 'org-1',
  slug: 'eyot',
  name: 'Eyot 世界',
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
  created_at: '2026-07-01T00:00:00Z',
  updated_at: null,
};

const entry1: KnowledgeEntry = {
  id: 'k-1',
  key: 'eyot.collab.passage',
  title: '近邻通道约束',
  body: '近邻通道只允许相邻成员互通',
  dimension_id: 'dim-1',
  scope: 'org',
  organization_id: 'org-1',
  namespace_id: null,
  workspace_id: null,
  entity_id: null,
  instance_id: null,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
};

const entry2: KnowledgeEntry = {
  id: 'k-2',
  key: 'eyot.hub.shared_work',
  title: '共享工作区约定',
  body: 'shared/ 为协作面',
  dimension_id: null,
  scope: 'workspace',
  organization_id: 'org-1',
  namespace_id: 'ns-1',
  workspace_id: 'ws-1',
  entity_id: null,
  instance_id: null,
  created_at: '2026-08-02T00:00:00Z',
  updated_at: null,
};

const dimension1: KnowledgeDimension = {
  id: 'dim-1',
  name: '协作规范',
  slug: 'collab',
  description: null,
  scope: 'org',
  organization_id: 'org-1',
  namespace_id: null,
  workspace_id: null,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
};

const namespace1 = {
  id: 'ns-1',
  org_id: 'org-1',
  slug: 'default',
  name: '默认命名空间',
  description: null,
  tags: null,
  workspace_count: 1,
  entity_count: 0,
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const workspace1 = {
  id: 'ws-1',
  namespace_id: 'ns-1',
  name: '研究实验室',
  slug: 'research-lab',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

function mockAll(entryItems: readonly KnowledgeEntry[] = [entry1, entry2]) {
  mockedFetchEntries.mockResolvedValue({
    items: entryItems,
    offset: 0,
    limit: 50,
    total: entryItems.length,
  });
  mockedFetchDimensions.mockResolvedValue({
    items: [dimension1],
    offset: 0,
    limit: 50,
    total: 1,
  });
  mockedFetchOrganization.mockResolvedValue(org);
  mockedFetchNamespaces.mockResolvedValue({ items: [namespace1], offset: 0, limit: 50, total: 1 });
  mockedFetchWorkspaces.mockResolvedValue({ items: [workspace1], offset: 0, limit: 200, total: 1 });
}

function renderKnowledgePage() {
  return render(
    <MemoryRouter initialEntries={['/orgs/org-1/knowledge']}>
      <Routes>
        <Route path="/orgs/:orgId/knowledge" element={<KnowledgePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAll();
});

describe('KnowledgePage', () => {
  it('renders the knowledge entry list with keys, scope badges and resolved bindings', async () => {
    renderKnowledgePage();

    expect(await screen.findByText('eyot.collab.passage')).toBeInTheDocument();
    expect(screen.getByText('近邻通道约束')).toBeInTheDocument();
    expect(screen.getByText('共享工作区约定')).toBeInTheDocument();
    // org binding resolves to the org name; workspace binding to "ns / ws".
    expect(screen.getByText('Eyot 世界')).toBeInTheDocument();
    expect(screen.getByText('默认命名空间 / 研究实验室')).toBeInTheDocument();
    // scope badges
    expect(screen.getAllByText('组织').length).toBeGreaterThan(0);
    expect(screen.getByText('工作区')).toBeInTheDocument();
    // dimension name appears in the table and in the dimension list section
    expect(screen.getAllByText('协作规范').length).toBeGreaterThan(0);
  });

  it('renders an empty state when there are no entries', async () => {
    mockAll([]);
    renderKnowledgePage();

    expect(await screen.findByText('暂无知识条目')).toBeInTheDocument();
  });

  it('create form: lowercases the key, requires the org id for org scope, and sends the exact payload', async () => {
    renderKnowledgePage();
    await screen.findByText('eyot.collab.passage');

    fireEvent.click(screen.getByTestId('knowledge-create-entry'));

    // key input normalizes to lowercase as the user types
    const keyInput = screen.getByLabelText('Key');
    fireEvent.change(keyInput, { target: { value: 'MyKey' } });
    expect(keyInput).toHaveValue('mykey');

    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '协作约定' } });
    fireEvent.change(screen.getByLabelText('内容'), { target: { value: '这是内容' } });

    const submit = screen.getByTestId('knowledge-form-submit');
    // org scope defaults to the current org → submit enabled
    expect(submit).toBeEnabled();

    // clearing the org id must disable submit (org scope requires org id)
    const orgSelect = screen.getByTestId('knowledge-org-select');
    fireEvent.change(orgSelect, { target: { value: '' } });
    expect(submit).toBeDisabled();
    fireEvent.change(orgSelect, { target: { value: 'org-1' } });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);

    await waitFor(() =>
      expect(mockedCreateEntry).toHaveBeenCalledWith({
        key: 'mykey',
        title: '协作约定',
        body: '这是内容',
        dimension_id: null,
        scope: 'org',
        organization_id: 'org-1',
        namespace_id: null,
        workspace_id: null,
      }),
    );
    // stale_state: the list is re-fetched after create
    expect(mockedFetchEntries).toHaveBeenCalledTimes(2);
  });

  it('workspace scope requires org + namespace + workspace ids before submit', async () => {
    renderKnowledgePage();
    await screen.findByText('eyot.collab.passage');

    fireEvent.click(screen.getByTestId('knowledge-create-entry'));

    fireEvent.change(screen.getByTestId('knowledge-scope-select'), {
      target: { value: 'workspace' },
    });
    fireEvent.change(screen.getByLabelText('Key'), { target: { value: 'ws.key' } });
    fireEvent.change(screen.getByLabelText('标题'), { target: { value: '工作区知识' } });

    const submit = screen.getByTestId('knowledge-form-submit');
    // org preselected, but namespace and workspace are still missing
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId('knowledge-namespace-select'), {
      target: { value: 'ns-1' },
    });
    expect(submit).toBeDisabled();

    fireEvent.change(screen.getByTestId('knowledge-workspace-select'), {
      target: { value: 'ws-1' },
    });
    expect(submit).toBeEnabled();

    fireEvent.click(submit);

    await waitFor(() =>
      expect(mockedCreateEntry).toHaveBeenCalledWith({
        key: 'ws.key',
        title: '工作区知识',
        body: '',
        dimension_id: null,
        scope: 'workspace',
        organization_id: 'org-1',
        namespace_id: 'ns-1',
        workspace_id: 'ws-1',
      }),
    );
  });

  it('delete asks for confirmation, then soft-deletes and re-fetches the list', async () => {
    renderKnowledgePage();
    await screen.findByText('eyot.collab.passage');

    fireEvent.click(screen.getByTestId('knowledge-delete-k-1'));
    expect(screen.getByText(/确认删除/)).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('knowledge-delete-confirm-k-1'));

    await waitFor(() => expect(mockedDeleteEntry).toHaveBeenCalledWith('k-1'));
    expect(mockedFetchEntries).toHaveBeenCalledTimes(2);
  });

  it('surfaces backend errors from the list fetch', async () => {
    mockedFetchEntries.mockRejectedValue(
      new ApiError(422, { message: 'scope 校验失败', error_code: 'scope.fk_mismatch' }),
    );
    renderKnowledgePage();

    expect(await screen.findByText('scope 校验失败')).toBeInTheDocument();
  });
});
