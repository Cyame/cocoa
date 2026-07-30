import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import FirstRunOnboardingModal from '@/pages/FirstRunOnboardingModal';
import { useOnboardingStore } from '@/stores/onboardingStore';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const MI_SHI_BASE_CLASS = {
  id: 'base-mi-shi',
  slug: 'mi-shi',
  name: 'mi-shi',
  display_name: '密士',
  description: '战略规划师：拆解目标、规划路径。',
  manifest: { default_model: 'gpt-4o-mini', commands: ['/plan', '/decompose', '/prioritize'] },
  version: '1.0',
  tags: ['plan'],
  created_at: '2026-07-01T00:00:00Z',
};

const HIDE_SEEK_BASE_CLASS = {
  id: 'base-an-ying',
  slug: 'an-ying',
  name: 'an-ying',
  display_name: '暗影',
  description: '初级执行：快速、低成本完成任务。',
  manifest: { default_model: 'gpt-4o-mini', commands: ['/execute', '/build', '/test'] },
  version: '1.0',
  tags: ['execute'],
  created_at: '2026-07-01T00:00:00Z',
};

const BASE_CLASSES_PAGE = {
  items: [MI_SHI_BASE_CLASS, HIDE_SEEK_BASE_CLASS],
  offset: 0,
  limit: 50,
  total: 2,
};

const CREATED_EMPLOYEE = {
  id: 'employee-1',
  name: 'nyar-proutzi',
  slug: 'nyar-proutzi',
  rank: 'researcher',
  preset_slug: 'mi-shi',
  display_name: 'nyar-proutzi',
  display_color: null,
  created_at: '2026-07-29T00:00:00Z',
  updated_at: '2026-07-29T00:00:00Z',
};

function renderModal(onClose = vi.fn()) {
  return render(<FirstRunOnboardingModal onClose={onClose} />);
}

function mockApiSuccess() {
  mockedApi.mockImplementation((path, init) => {
    if (path.startsWith('/base-classes') && (init?.method ?? 'GET') === 'GET') {
      return Promise.resolve(BASE_CLASSES_PAGE);
    }
    if (path.startsWith('/organizations/default/providers') && (init?.method ?? 'GET') === 'GET') {
      return Promise.resolve([
        {
          id: 'prov-1',
          organization_id: 'org-1',
          origin: 'custom',
          catalog_provider_id: null,
          name: 'OpenAI Compatible',
          slug: 'openai-compatible',
          request_format: 'completion',
          base_url: 'https://api.example.com',
          api_key_ref: 'OPENAI_API_KEY',
          default_model: 'gpt-4o-mini',
          models_allowlist: null,
          verify_ssl: true,
          models_endpoint_mode: 'inherit',
          models_base_url: null,
          enabled: true,
          last_test_status: 'ok',
          last_tested_at: null,
          last_test_detail: null,
          created_at: '2026-07-01T00:00:00Z',
          updated_at: null,
        },
      ]);
    }
    if (path.startsWith('/organizations/default/system-hub') && (init?.method ?? 'GET') === 'GET') {
      return Promise.resolve({ provider_id: 'prov-1', model: 'gpt-4o-mini', configured: true });
    }
    if (path.startsWith('/model-catalog') && (init?.method ?? 'GET') === 'GET') {
      return Promise.resolve({
        items: [
          { id: 'gpt-4o-mini', name: 'gpt-4o-mini', provider: 'openai', context_length: 128000 },
        ],
        degraded: false,
        default_model: 'gpt-4o-mini',
        error: null,
      });
    }
    if (path.startsWith('/base-classes/by-id/') && path.endsWith('/provider-default')) {
      return Promise.resolve(null);
    }
    if (path === '/entities' && init?.method === 'POST') {
      return Promise.resolve(CREATED_EMPLOYEE);
    }
    return Promise.reject(new Error(`Unmocked call: ${init?.method ?? 'GET'} ${path}`));
  });
}

beforeEach(() => {
  mockedApi.mockReset();
  mockApiSuccess();
  useOnboardingStore.setState({
    step: 1,
    selectedBaseClass: null,
    displayName: '',
    slug: '',
    slugTouched: false,
    rank: 'researcher',
    providerId: '',
    model: '',
    description: '',
    knowledgeRows: [],
    knowledgeFiles: [],
    knowledgeScope: 'instance',
    submitError: null,
  });
});

afterEach(() => {
  useOnboardingStore.setState({
    step: 1,
    selectedBaseClass: null,
    displayName: '',
    slug: '',
    slugTouched: false,
    rank: 'researcher',
    providerId: '',
    model: '',
    description: '',
    knowledgeRows: [],
    knowledgeFiles: [],
    knowledgeScope: 'instance',
    submitError: null,
  });
});

describe('FirstRunOnboardingModal', () => {
  it('renders Step 1 with the deity cards and step indicator', async () => {
    renderModal();

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();
    const indicator = await screen.findByTestId('step-indicator');
    expect(indicator).toHaveTextContent(/Step 1\/3/);

    const miShi = await screen.findByTestId('deity-card-mi-shi');
    expect(miShi).toBeInTheDocument();
    expect(miShi).toHaveTextContent('密士');

    const anYing = screen.getByTestId('deity-card-an-ying');
    expect(anYing).toHaveTextContent('暗影');

    expect(mockedApi).toHaveBeenCalledWith('/base-classes?limit=50&offset=0');
  });

  it('keeps the Next button disabled until a deity is selected', async () => {
    renderModal();

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();
    const next = screen.getByTestId('onboarding-next');
    expect(next).toBeDisabled();

    fireEvent.click(screen.getByTestId('deity-card-mi-shi'));

    expect(next).not.toBeDisabled();
  });

  it('navigates Step 1 → Step 2 → Step 3 via Next and Back', async () => {
    renderModal();

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('deity-card-mi-shi'));
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step2')).toBeInTheDocument();
    expect(screen.getByTestId('step-indicator')).toHaveTextContent(/Step 2\/3/);

    fireEvent.change(screen.getByLabelText(/Display name/i), {
      target: { value: 'nyar-proutzi' },
    });
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step3')).toBeInTheDocument();
    expect(screen.getByTestId('step-indicator')).toHaveTextContent(/Step 3\/3/);

    fireEvent.click(screen.getByTestId('onboarding-back'));
    expect(await screen.findByTestId('onboarding-step2')).toBeInTheDocument();
  });

  it('validates Step 2 form: blocks Next when display_name is empty or slug invalid', async () => {
    renderModal();

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('deity-card-mi-shi'));
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step2')).toBeInTheDocument();

    const next = screen.getByTestId('onboarding-next');
    expect(next).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Display name/i), {
      target: { value: 'nyar-proutzi' },
    });

    expect(next).not.toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Slug/i), {
      target: { value: 'Nyar Proutzi' },
    });

    expect(await screen.findByText(/Slug must start with a lowercase letter/i)).toBeInTheDocument();
    expect(next).toBeDisabled();

    fireEvent.change(screen.getByLabelText(/Slug/i), {
      target: { value: 'nyar-proutzi' },
    });

    expect(next).not.toBeDisabled();
  });

  it('auto-generates slug from display_name until the user edits the slug', async () => {
    renderModal();

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('deity-card-mi-shi'));
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step2')).toBeInTheDocument();

    const displayInput = screen.getByLabelText(/Display name/i);
    const slugInput = screen.getByLabelText(/Slug/i);

    fireEvent.change(displayInput, { target: { value: 'Nyar Proutzi Aide' } });
    expect((slugInput as HTMLInputElement).value).toBe('nyar-proutzi-aide');

    fireEvent.change(displayInput, { target: { value: '奈亚探子' } });
    expect((slugInput as HTMLInputElement).value).toBe('nai-ya-tan-zi');

    fireEvent.change(slugInput, { target: { value: 'custom-slug' } });
    fireEvent.change(displayInput, { target: { value: 'cthulhu-aide' } });
    expect((slugInput as HTMLInputElement).value).toBe('custom-slug');
  });

  it('submits POST /entities at Step 3 with the full payload and closes via "completed"', async () => {
    const onClose = vi.fn();
    renderModal(onClose);

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('deity-card-mi-shi'));
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step2')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Display name/i), {
      target: { value: 'nyar-proutzi' },
    });
    useOnboardingStore.setState({
      providerId: 'prov-1',
      model: 'gpt-4o-mini',
    });

    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step3')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('onboarding-next'));

    await waitFor(() => {
      const submitCall = mockedApi.mock.calls.find(
        ([path, init]) => path === '/entities' && init?.method === 'POST',
      );
      expect(submitCall).toBeDefined();
      if (submitCall === undefined) return;
      const init = submitCall[1] as RequestInit;
      const body = JSON.parse(init.body as string);
      expect(body).toEqual({
        name: 'nyar-proutzi',
        slug: 'nyar-proutzi',
        rank: 'researcher',
        preset_slug: 'mi-shi',
        display_name: 'nyar-proutzi',
        system_prompt: null,
        config_override: {
          provider_id: 'prov-1',
          model: 'gpt-4o-mini',
        },
      });
    });

    expect(await screen.findByTestId('onboarding-success')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Confirm/i }));

    expect(onClose).toHaveBeenCalledWith('completed');
  });

  it('surfaces an error banner and stays on Step 3 when POST /entities fails', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path.startsWith('/base-classes') && (init?.method ?? 'GET') === 'GET') {
        return Promise.resolve(BASE_CLASSES_PAGE);
      }
      if (path === '/entities' && init?.method === 'POST') {
        return Promise.reject(new ApiError(409, { message: 'slug already taken' }));
      }
      return Promise.reject(new Error(`Unmocked: ${init?.method ?? 'GET'} ${path}`));
    });

    renderModal();

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('deity-card-mi-shi'));
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step2')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Display name/i), {
      target: { value: 'nyar-proutzi' },
    });
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByTestId('onboarding-step3')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('onboarding-next'));

    expect(await screen.findByText(/slug already taken/i)).toBeInTheDocument();
    expect(screen.queryByTestId('onboarding-success')).not.toBeInTheDocument();
    expect(screen.getByTestId('onboarding-step3')).toBeInTheDocument();
  });

  it('fires onClose("dismissed") when the close button is clicked', async () => {
    const onClose = vi.fn();
    renderModal(onClose);

    expect(await screen.findByTestId('onboarding-step1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Close/i }));

    expect(onClose).toHaveBeenCalledWith('dismissed');
  });
});
