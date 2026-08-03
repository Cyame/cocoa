import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import EntityDetailModal from '@/components/EntityDetailModal';
import { api } from '@/lib/api';
import { useEntityModalStore } from '@/stores/entityModalStore';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const ENTITY_ID = 'entity-1';

const ENTITY_RESPONSE = {
  id: ENTITY_ID,
  name: '密士',
  slug: 'mi-shi',
  rank: 'researcher',
  preset_slug: 'mi-shi-base',
  display_name: '密士',
  display_color: null,
  description: 'A research-grade entity for testing.',
  base_class_slug: 'mi-shi',
  capabilities: [
    {
      name: 'workflow-patterns',
      type: 'skill',
      version: '0.1.2',
      source: 'from_base_class',
      description: null,
      tags: [],
    },
  ],
  ai_genes: [{ slug: 'workflow-patterns', source: 'from_base_class' }],
  creator_email: 'user@example.com',
  workspace_id: 'workspace-1',
  created_at: '2026-07-01T00:00:00Z',
  updated_at: '2026-07-01T00:00:00Z',
};

const INSTANCES_RESPONSE = {
  items: [
    {
      id: 'inst-aaaa',
      entity_id: ENTITY_ID,
      workspace_id: 'workspace-1',
      status: 'running',
      workspace_path: null,
      runtime_config: null,
      created_at: '2026-07-01T00:00:00Z',
      updated_at: '2026-07-01T00:00:00Z',
    },
  ],
  next_cursor: null,
  total: 1,
};

const PROMOTE_RESPONSE = {
  status: 'ok',
  mode: 'update',
  promoted_at: '2026-07-29T12:00:00Z',
  entity_id: ENTITY_ID,
  entity_promotion_migration_hash: 'abc123',
  capability_promoted_count: 2,
  prompt_regenerated: false,
  new_prompt_preview: '',
  outdated_instances_count: 1,
  capability_market_uploaded: 2,
};

const TRANSMUTE_RESPONSE = {
  new_base_class_id: 'bc-1',
  new_base_class_slug: 'jin-mi-shi',
  new_base_class_name: '金密士',
  manifest_preview: {
    name: '金密士',
    slug: 'jin-mi-shi',
    provider: 'anthropic/claude-3.5',
    skills: ['workflow-patterns'],
    tools: ['shell'],
    commands: ['/plan'],
    based_on_memory: 23,
  },
  source_entity_id: ENTITY_ID,
};

function openModal(tab: 'basic' | 'distill' | 'instances' = 'basic') {
  useEntityModalStore.getState().open(ENTITY_ID, tab === 'basic' ? undefined : tab);
}

function renderModal() {
  const onClose = vi.fn();
  const result = render(
    <MemoryRouter initialEntries={['/entities/test']}>
      <EntityDetailModal onClose={onClose} />
    </MemoryRouter>,
  );
  return { ...result, onClose };
}

beforeEach(() => {
  mockedApi.mockReset();
  useEntityModalStore.setState({ entityId: null, initialTab: null });
  mockedApi.mockImplementation((path, init) => {
    if (path === `/entities/${ENTITY_ID}` && (!init || init.method === undefined)) {
      return Promise.resolve(ENTITY_RESPONSE);
    }
    if (path.startsWith(`/instances?entity_id=${ENTITY_ID}`)) {
      return Promise.resolve(INSTANCES_RESPONSE);
    }
    if (path === `/learning/entities/${ENTITY_ID}/promote` && (init?.method ?? 'GET') === 'POST') {
      return Promise.resolve(PROMOTE_RESPONSE);
    }
    if (
      path === `/learning/entities/${ENTITY_ID}/transmute` &&
      (init?.method ?? 'GET') === 'POST'
    ) {
      return Promise.resolve(TRANSMUTE_RESPONSE);
    }
    return Promise.reject(new Error(`Unmocked call: ${init?.method ?? 'GET'} ${path}`));
  });
});

describe('EntityDetailModal', () => {
  it('renders the modal with entity header and the basic tab by default', async () => {
    openModal();
    renderModal();

    expect(await screen.findByTestId('entity-detail-modal')).toBeInTheDocument();
    expect(screen.getByTestId('entity-modal-title')).toHaveTextContent('密士');
    expect(screen.getByTestId('entity-modal-slug')).toHaveTextContent('mi-shi');
    expect(screen.getByTestId('entity-modal-tabs')).toBeInTheDocument();
    expect(screen.getByText('Display name')).toBeInTheDocument();
    expect(mockedApi).toHaveBeenCalledWith(`/entities/${ENTITY_ID}`);
  });

  it('navigates between the 5 tabs via keyboard arrows and click', async () => {
    openModal();
    renderModal();
    await screen.findByTestId('entity-modal-title');

    fireEvent.click(screen.getByTestId('entity-tab-capabilities'));
    expect(await screen.findByText('Group by type')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('entity-tab-ai_genes'));
    expect(await screen.findByTestId('genes-group-fromBaseClass')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('entity-tab-distill'));
    expect(await screen.findByTestId('distill-open-transmute')).toBeInTheDocument();
    expect(screen.queryByTestId('distill-open-promote')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('entity-tab-basic'));
    expect(screen.getByTestId('entity-tab-basic')).toHaveAttribute('aria-selected', 'true');
  });

  it('opens promote modal from the instances tab and submits update mode', async () => {
    openModal('instances');
    renderModal();
    await screen.findByTestId('entity-modal-title');
    expect(await screen.findByTestId('instances-table')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('instance-promote'));
    expect(await screen.findByTestId('promote-modal')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('promote-modal-submit'));

    await waitFor(() => {
      const call = mockedApi.mock.calls.find(
        ([path, init]) =>
          path === `/learning/entities/${ENTITY_ID}/promote` && (init?.method ?? 'GET') === 'POST',
      );
      expect(call).toBeDefined();
    });

    const promoteCall = mockedApi.mock.calls.find(
      ([path, init]) =>
        path === `/learning/entities/${ENTITY_ID}/promote` && (init?.method ?? 'GET') === 'POST',
    );
    expect(promoteCall).toBeDefined();
    if (promoteCall === undefined) throw new Error('expected promote call');
    const init = promoteCall[1] as RequestInit;
    const body = JSON.parse(init.body as string);
    expect(body.mode).toBe('update');
    expect(body.from_instance_id).toBe('inst-aaaa');
  });

  it('opens transmute modal and shows result after submit', async () => {
    openModal('distill');
    renderModal();
    await screen.findByTestId('entity-modal-title');

    fireEvent.click(screen.getByTestId('distill-open-transmute'));
    expect(await screen.findByTestId('transmute-modal')).toBeInTheDocument();

    fireEvent.change(screen.getByTestId('transmute-modal-slug'), {
      target: { value: 'jin-mi-shi' },
    });
    fireEvent.change(screen.getByTestId('transmute-modal-name'), {
      target: { value: '金密士' },
    });

    fireEvent.click(screen.getByTestId('transmute-modal-submit'));

    const resultDialog = await screen.findByTestId('distill-result-modal');
    expect(resultDialog).toBeInTheDocument();
    expect(screen.getByTestId('distill-result-slug')).toHaveTextContent('jin-mi-shi');

    const transmuteCall = mockedApi.mock.calls.find(
      ([path, init]) =>
        path === `/learning/entities/${ENTITY_ID}/transmute` && (init?.method ?? 'GET') === 'POST',
    );
    expect(transmuteCall).toBeDefined();
    if (transmuteCall === undefined) throw new Error('expected transmute call');
    const init = transmuteCall[1] as RequestInit;
    const body = JSON.parse(init.body as string);
    expect(body.target_base_class_slug).toBe('jin-mi-shi');
    expect(body.target_base_class_name).toBe('金密士');
  });

  it('opens gene attach picker when add extra is clicked', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === `/entities/${ENTITY_ID}` && (!init || init.method === undefined)) {
        return Promise.resolve(ENTITY_RESPONSE);
      }
      if (path.startsWith(`/instances?entity_id=${ENTITY_ID}`)) {
        return Promise.resolve(INSTANCES_RESPONSE);
      }
      if (path.startsWith('/ai-genes?')) {
        return Promise.resolve({
          items: [
            {
              id: 'gene-extra-1',
              slug: 'extra-tool',
              name: 'Extra tool',
              tags: [],
              description: null,
              scope: 'org',
              created_at: '2026-07-01T00:00:00Z',
              updated_at: null,
            },
          ],
          total: 1,
        });
      }
      return Promise.reject(new Error(`Unmocked call: ${init?.method ?? 'GET'} ${path}`));
    });

    openModal();
    renderModal();
    await screen.findByTestId('entity-modal-title');
    fireEvent.click(screen.getByTestId('entity-tab-ai_genes'));
    expect(await screen.findByTestId('genes-add-extra')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('genes-add-extra'));
    expect(await screen.findByTestId('genes-add-modal')).toBeInTheDocument();
    expect(screen.queryByTestId('genes-add-modal-stub')).not.toBeInTheDocument();
  });
});
