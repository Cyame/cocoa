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
    {
      name: 'planted-skill-1',
      type: 'skill',
      version: '1.0.0',
      source: 'extra_added',
      description: null,
      tags: [],
    },
    {
      name: 'shell',
      type: 'tool',
      version: '1.0.0',
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
      employee_id: ENTITY_ID,
      office_id: 'office-1',
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
  source_employee_id: ENTITY_ID,
};

function openModal() {
  useEntityModalStore.getState().open(ENTITY_ID);
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
  useEntityModalStore.setState({ entityId: null });
  mockedApi.mockImplementation((path, init) => {
    if (path === `/entities/${ENTITY_ID}` && (!init || init.method === undefined)) {
      return Promise.resolve(ENTITY_RESPONSE);
    }
    if (path.startsWith(`/instances?employee_id=${ENTITY_ID}`)) {
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

    const capabilitiesTab = screen.getByTestId('entity-tab-capabilities');
    fireEvent.click(capabilitiesTab);
    expect(capabilitiesTab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('Group by type')).toBeInTheDocument();

    const genesTab = screen.getByTestId('entity-tab-ai_genes');
    fireEvent.click(genesTab);
    expect(genesTab).toHaveAttribute('aria-selected', 'true');

    const instancesTab = screen.getByTestId('entity-tab-instances');
    fireEvent.click(instancesTab);
    expect(instancesTab).toHaveAttribute('aria-selected', 'true');

    const distillTab = screen.getByTestId('entity-tab-distill');
    fireEvent.click(distillTab);
    expect(distillTab).toHaveAttribute('aria-selected', 'true');
    expect(await screen.findByText('Promote')).toBeInTheDocument();
    expect(screen.getByText('Transmute')).toBeInTheDocument();

    const basicTab = screen.getByTestId('entity-tab-basic');
    fireEvent.click(basicTab);
    expect(basicTab).toHaveAttribute('aria-selected', 'true');
  });

  it('triggers promote, hits the endpoint, and shows a success toast', async () => {
    openModal();
    renderModal();
    await screen.findByTestId('entity-modal-title');

    fireEvent.click(screen.getByTestId('entity-tab-distill'));

    const submit = await screen.findByTestId('distill-promote-submit');
    fireEvent.click(submit);

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
    expect(body.memory_kind_filter).toEqual(
      expect.arrayContaining(['experience', 'lesson', 'decision', 'problem']),
    );
  });

  it('triggers transmute and opens the DistillResultModal with manifest preview', async () => {
    openModal();
    renderModal();
    await screen.findByTestId('entity-modal-title');

    fireEvent.click(screen.getByTestId('entity-tab-distill'));

    fireEvent.change(screen.getByTestId('distill-transmute-slug'), {
      target: { value: 'jin-mi-shi' },
    });
    fireEvent.change(screen.getByTestId('distill-transmute-name'), {
      target: { value: '金密士' },
    });

    fireEvent.click(screen.getByTestId('distill-transmute-submit'));

    const resultDialog = await screen.findByTestId('distill-result-modal');
    expect(resultDialog).toBeInTheDocument();
    expect(screen.getByTestId('distill-result-slug')).toHaveTextContent('jin-mi-shi');
    expect(screen.getByText('金密士')).toBeInTheDocument();
    expect(screen.getByText('Based on 23 memory entries')).toBeInTheDocument();

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
    expect(body.snapshot_only).toBe(false);
  });

  it('disables transmute submit when target slug is invalid', async () => {
    openModal();
    renderModal();
    await screen.findByTestId('entity-modal-title');

    fireEvent.click(screen.getByTestId('entity-tab-distill'));

    fireEvent.change(screen.getByTestId('distill-transmute-slug'), {
      target: { value: 'Invalid Slug' },
    });
    fireEvent.change(screen.getByTestId('distill-transmute-name'), {
      target: { value: '名称' },
    });

    const submit = screen.getByTestId('distill-transmute-submit');
    expect(submit).toBeDisabled();

    fireEvent.click(submit);
    expect(
      mockedApi.mock.calls.find(
        ([path, init]) =>
          path === `/learning/entities/${ENTITY_ID}/transmute` &&
          (init?.method ?? 'GET') === 'POST',
      ),
    ).toBeUndefined();
  });
});
