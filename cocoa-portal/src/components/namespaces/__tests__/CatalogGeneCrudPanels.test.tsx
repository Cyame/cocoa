import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { TFunction } from 'i18next';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buildConfigTemplate,
  CapabilityMarketTab,
  DeepSeaGenesPanel,
  normalizeTagsInput,
  parseJsonObjectInput,
} from '@/components/namespaces/CatalogGeneCrudPanels';
import { api } from '@/lib/api';

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: vi.fn() };
});

const mockedApi = vi.mocked(api);

const t = ((key: string) => key) as unknown as TFunction;

const CAPABILITY_ENTRY = {
  id: 'cap-1',
  name: 'Web search',
  type: 'tool',
  description: 'Search the web',
  config_template: { engine: 'bing' },
  required_knowledge: null,
  tags: ['search'],
  scope: 'org',
  organization_id: null,
  namespace_id: null,
  created_by_user_id: null,
  created_via: 'manual',
  source_entity_slug: null,
  readonly: false,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
};

const AI_GENE = {
  id: 'gene-1',
  slug: 'deep-one',
  name: 'Deep One',
  tags: ['planning'],
  manifest: { skills: ['debug'] },
  description: 'A gene',
  scope: 'org',
  organization_id: null,
  namespace_id: null,
  readonly: false,
  created_at: '2026-08-01T00:00:00Z',
  updated_at: null,
};

const CODE_EXEC_ENTRY = {
  ...CAPABILITY_ENTRY,
  id: 'cap-2',
  name: 'Code exec',
  description: 'Run code',
};

function lastCallBody(method: string): Record<string, unknown> {
  const call = mockedApi.mock.calls.find(([, init]) => init?.method === method);
  if (!call) throw new Error(`no ${method} call recorded`);
  const init = call[1] as RequestInit;
  return JSON.parse(init.body as string) as Record<string, unknown>;
}

beforeEach(() => {
  mockedApi.mockReset();
});

describe('normalizeTagsInput', () => {
  it('normalizes case, spaces, duplicates and empty entries', () => {
    expect(normalizeTagsInput('Planning, Multi Modal , planning,,')).toEqual([
      'planning',
      'multi-modal',
    ]);
  });

  it('returns null for empty or all-blank input', () => {
    expect(normalizeTagsInput('')).toBeNull();
    expect(normalizeTagsInput(' , , ')).toBeNull();
  });

  it('strips characters outside kebab-case alphabet', () => {
    expect(normalizeTagsInput('R&D, ops!')).toEqual(['rd', 'ops']);
  });
});

describe('parseJsonObjectInput', () => {
  it('maps empty input to null', () => {
    expect(parseJsonObjectInput('   ')).toEqual({ ok: true, value: null });
  });

  it('parses a valid JSON object', () => {
    expect(parseJsonObjectInput('{"a": 1}')).toEqual({ ok: true, value: { a: 1 } });
  });

  it('rejects arrays, primitives and invalid JSON', () => {
    expect(parseJsonObjectInput('[1,2]').ok).toBe(false);
    expect(parseJsonObjectInput('"text"').ok).toBe(false);
    expect(parseJsonObjectInput('null').ok).toBe(false);
    expect(parseJsonObjectInput('{broken').ok).toBe(false);
  });
});

describe('buildConfigTemplate (B1c structured builders)', () => {
  const empty = {
    skillName: '',
    skillDescription: '',
    skillBody: '',
    mcpCommand: '',
    mcpArgsText: '',
    mcpEnvText: '',
    mcpTransport: 'stdio',
    paramsText: '',
  };

  it('builds a skill template from name / description / body', () => {
    expect(
      buildConfigTemplate('skill', {
        ...empty,
        skillName: 'Research planner',
        skillBody: 'Plan multi-step research.',
      }),
    ).toEqual({ name: 'Research planner', body: 'Plan multi-step research.' });
  });

  it('builds an mcp server template with command, args, env and transport', () => {
    expect(
      buildConfigTemplate('mcp', {
        ...empty,
        mcpCommand: 'npx',
        mcpArgsText: '-y @modelcontextprotocol/server-foo',
        mcpEnvText: 'API_KEY=abc\nBASE_URL=https://example.com',
        mcpTransport: 'sse',
      }),
    ).toEqual({
      command: 'npx',
      args: ['-y', '@modelcontextprotocol/server-foo'],
      env: { API_KEY: 'abc', BASE_URL: 'https://example.com' },
      transport: 'sse',
    });
  });

  it('builds a parameter surface for tool/command/lsp types', () => {
    expect(
      buildConfigTemplate('tool', {
        ...empty,
        paramsText: '[{"name": "query", "type": "string", "required": true}]',
      }),
    ).toEqual({ parameters: [{ name: 'query', type: 'string', required: true }] });
  });

  it('returns null when every structured field is empty', () => {
    expect(buildConfigTemplate('skill', empty)).toBeNull();
    expect(buildConfigTemplate('mcp', empty)).toBeNull();
    expect(buildConfigTemplate('lsp', empty)).toBeNull();
  });
});

describe('CapabilityMarketTab tags + config_template', () => {
  it('submits normalized tags and parsed config_template on create', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      if (path === '/capability-market' && init?.method === 'POST') {
        return Promise.resolve(CAPABILITY_ENTRY);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<CapabilityMarketTab t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createCapability' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.name'), {
      target: { value: 'Web search' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.genesTagsLabel'), {
      target: { value: 'Search, Web Tools, search' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.capabilityConfigTemplateLabel'), {
      target: { value: '{"engine": "bing"}' },
    });
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('POST');
      expect(body.name).toBe('Web search');
      expect(body.type).toBe('skill');
      expect(body.tags).toEqual(['search', 'web-tools']);
      expect(body.config_template).toEqual({ engine: 'bing' });
    });
  });

  it('blocks submit and shows an error when config_template is not a valid JSON object', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<CapabilityMarketTab t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createCapability' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.name'), {
      target: { value: 'Broken' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.capabilityConfigTemplateLabel'), {
      target: { value: '{not-json' },
    });
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    expect(await within(modal).findByRole('alert')).toHaveTextContent(
      'namespaces.invalidJsonObject',
    );
    expect(mockedApi.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  });

  it('prefills tags and config_template in edit mode and sends them on PATCH', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [CAPABILITY_ENTRY], offset: 0, limit: 200, total: 1 });
      }
      if (path === '/capability-market/cap-1' && init?.method === 'PATCH') {
        return Promise.resolve(CAPABILITY_ENTRY);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<CapabilityMarketTab t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.edit' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    const tagsInput = within(modal).getByLabelText('namespaces.genesTagsLabel');
    const jsonInput = within(modal).getByLabelText('namespaces.capabilityConfigTemplateLabel');
    expect(tagsInput).toHaveValue('search');
    expect(jsonInput).toHaveValue(JSON.stringify({ engine: 'bing' }, null, 2));

    fireEvent.change(tagsInput, { target: { value: 'Search, Extra' } });
    fireEvent.change(jsonInput, { target: { value: '{"engine": "kagi"}' } });
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('PATCH');
      expect(body.tags).toEqual(['search', 'extra']);
      expect(body.config_template).toEqual({ engine: 'kagi' });
    });
  });

  it('builds a structured skill definition and wires required_knowledge into the payload', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      if (path === '/knowledge?limit=200&offset=0') {
        return Promise.resolve({
          items: [
            {
              id: 'k-1',
              key: 'debug-checklist',
              title: 'Debugging checklist',
              body: '...',
              dimension_id: null,
              scope: 'org',
              organization_id: null,
              namespace_id: null,
              workspace_id: null,
              entity_id: null,
              instance_id: null,
              created_at: '2026-08-01T00:00:00Z',
              updated_at: null,
            },
          ],
          offset: 0,
          limit: 200,
          total: 1,
        });
      }
      if (path === '/capability-market' && init?.method === 'POST') {
        return Promise.resolve(CAPABILITY_ENTRY);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<CapabilityMarketTab t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createCapability' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.capabilitySkillBodyLabel'), {
      target: { value: 'Follow the debug checklist step by step.' },
    });
    const picker = within(modal).getByTestId('required-knowledge-picker');
    fireEvent.click(await within(picker).findByRole('checkbox', { name: /debug-checklist/ }));
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('POST');
      expect(body.config_template).toEqual({
        body: 'Follow the debug checklist step by step.',
      });
      expect(body.required_knowledge).toEqual(['debug-checklist']);
    });
  });

  it('blocks submit when tool parameters are not a valid JSON array', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<CapabilityMarketTab t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createCapability' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.type'), {
      target: { value: 'tool' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.capabilityParamsLabel'), {
      target: { value: 'not-an-array' },
    });
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    expect(await within(modal).findByRole('alert')).toHaveTextContent(
      'namespaces.capabilityParamsInvalid',
    );
    expect(mockedApi.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  });
});

describe('DeepSeaGenesPanel tags + manifest', () => {
  it('submits normalized tags and parsed manifest on create', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/ai-genes?limit=200&offset=0') {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      if (path === '/ai-genes' && init?.method === 'POST') {
        return Promise.resolve(AI_GENE);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createAiGene' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.genesSlug'), {
      target: { value: 'deep-one' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.name'), {
      target: { value: 'Deep One' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.genesTagsLabel'), {
      target: { value: 'Planning, Review' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.genesManifestLabel'), {
      target: { value: '{"gene_refs":[],"skills":["debug"],"tools":[],"commands":[]}' },
    });
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('POST');
      expect(body.slug).toBe('deep-one');
      expect(body.tags).toEqual(['planning', 'review']);
      expect(body.manifest).toEqual({
        gene_refs: [],
        skills: ['debug'],
        tools: [],
        commands: [],
      });
    });
  });

  it('blocks submit and shows an error when manifest is invalid JSON', async () => {
    mockedApi.mockImplementation((path) => {
      if (path === '/ai-genes?limit=200&offset=0') {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createAiGene' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.genesManifestLabel'), {
      target: { value: '["not", "an", "object"]' },
    });
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    expect(await within(modal).findByRole('alert')).toHaveTextContent(
      'namespaces.invalidJsonObject',
    );
    expect(mockedApi.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  });

  it('prefills tags and manifest in edit mode and sends them on PATCH', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/ai-genes?limit=200&offset=0') {
        return Promise.resolve({ items: [AI_GENE], total: 1 });
      }
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      if (path === '/ai-genes/gene-1' && init?.method === 'PATCH') {
        return Promise.resolve(AI_GENE);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.edit' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    const tagsInput = within(modal).getByLabelText('namespaces.genesTagsLabel');
    const jsonInput = within(modal).getByLabelText('namespaces.genesManifestLabel');
    expect(tagsInput).toHaveValue('planning');
    expect(jsonInput).toHaveValue(JSON.stringify({ skills: ['debug'] }, null, 2));

    fireEvent.change(jsonInput, { target: { value: '{"skills": ["review"]}' } });
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('PATCH');
      expect(body.tags).toEqual(['planning']);
      expect(body.manifest).toEqual({ skills: ['review'] });
    });
  });
});

describe('DeepSeaGenesPanel capability multi-select', () => {
  const marketPage = {
    items: [CAPABILITY_ENTRY, CODE_EXEC_ENTRY],
    offset: 0,
    limit: 200,
    total: 2,
  };

  function mockApis(geneItems: readonly unknown[]) {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/ai-genes?limit=200&offset=0') {
        return Promise.resolve({ items: geneItems, total: geneItems.length });
      }
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve(marketPage);
      }
      if (path === '/ai-genes' && init?.method === 'POST') {
        return Promise.resolve(AI_GENE);
      }
      if (path === '/ai-genes/gene-1' && init?.method === 'PATCH') {
        return Promise.resolve(AI_GENE);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });
  }

  it('submits checked capabilities in the combine-isomorphic shape', async () => {
    mockApis([]);

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createAiGene' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.name'), {
      target: { value: 'Deep One' },
    });

    const picker = within(modal).getByTestId('gene-capabilities-picker');
    fireEvent.click(await within(picker).findByRole('checkbox', { name: /Web search/ }));
    fireEvent.click(within(picker).getByRole('checkbox', { name: /Code exec/ }));

    const summary = within(modal).getByTestId('gene-capabilities-summary');
    expect(summary).toHaveTextContent('Web search');
    expect(summary).toHaveTextContent('Code exec');

    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('POST');
      const capabilities = body.capabilities as Record<string, unknown>[];
      expect(capabilities).toEqual([
        { name: 'Web search', type: 'tool', description: 'Search the web' },
        { name: 'Code exec', type: 'tool', description: 'Run code' },
      ]);
      for (const cap of capabilities) {
        expect(Object.keys(cap).sort()).toEqual(['description', 'name', 'type']);
      }
    });
  });

  it('echoes manifest.capabilities as checked on edit and clears them on uncheck', async () => {
    const geneWithCaps = {
      ...AI_GENE,
      manifest: {
        skills: ['debug'],
        capabilities: [{ name: 'Web search', type: 'tool', description: 'Search the web' }],
      },
    };
    mockApis([geneWithCaps]);

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.edit' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    const picker = within(modal).getByTestId('gene-capabilities-picker');
    const webSearch = await within(picker).findByRole('checkbox', { name: /Web search/ });
    expect(webSearch).toBeChecked();
    expect(within(picker).getByRole('checkbox', { name: /Code exec/ })).not.toBeChecked();

    fireEvent.click(webSearch);
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('PATCH');
      expect(body.capabilities).toEqual([]);
      expect(body.manifest).toEqual({ skills: ['debug'] });
    });
  });

  it('reflects manifest-JSON capabilities into checkboxes and dedups JSON + checkbox overlap', async () => {
    mockApis([]);

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createAiGene' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    fireEvent.change(within(modal).getByLabelText('namespaces.name'), {
      target: { value: 'Deep One' },
    });
    fireEvent.change(within(modal).getByLabelText('namespaces.genesManifestLabel'), {
      target: {
        value: JSON.stringify({
          skills: ['debug'],
          capabilities: [
            { name: 'Web search', type: 'tool', description: 'From JSON' },
            { name: 'Web search', type: 'tool', description: 'JSON duplicate' },
          ],
        }),
      },
    });

    const picker = within(modal).getByTestId('gene-capabilities-picker');
    const webSearch = await within(picker).findByRole('checkbox', { name: /Web search/ });
    expect(webSearch).toBeChecked();

    fireEvent.click(within(picker).getByRole('checkbox', { name: /Code exec/ }));
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('POST');
      expect(body.capabilities).toEqual([
        { name: 'Web search', type: 'tool', description: 'From JSON' },
        { name: 'Code exec', type: 'tool', description: 'Run code' },
      ]);
      expect(body.manifest).toEqual({ skills: ['debug'] });
    });
  });
});

describe('DeepSeaGenesPanel required_knowledge', () => {
  const knowledgePage = {
    items: [
      {
        id: 'k-1',
        key: 'debug-checklist',
        title: 'Debugging checklist',
        body: '...',
        dimension_id: null,
        scope: 'org',
        organization_id: null,
        namespace_id: null,
        workspace_id: null,
        entity_id: null,
        instance_id: null,
        created_at: '2026-08-01T00:00:00Z',
        updated_at: null,
      },
      {
        id: 'k-2',
        key: 'research-method',
        title: 'Research method',
        body: '...',
        dimension_id: null,
        scope: 'org',
        organization_id: null,
        namespace_id: null,
        workspace_id: null,
        entity_id: null,
        instance_id: null,
        created_at: '2026-08-01T00:00:00Z',
        updated_at: null,
      },
    ],
    offset: 0,
    limit: 200,
    total: 2,
  };

  it('writes ordered required_knowledge into the gene manifest on create', async () => {
    mockedApi.mockImplementation((path, init) => {
      if (path === '/ai-genes?limit=200&offset=0') {
        return Promise.resolve({ items: [], total: 0 });
      }
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      if (path === '/knowledge?limit=200&offset=0') {
        return Promise.resolve(knowledgePage);
      }
      if (path === '/ai-genes' && init?.method === 'POST') {
        return Promise.resolve(AI_GENE);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.createAiGene' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    const picker = within(modal).getByTestId('required-knowledge-picker');
    fireEvent.click(await within(picker).findByRole('checkbox', { name: /research-method/ }));
    fireEvent.click(within(picker).getByRole('checkbox', { name: /debug-checklist/ }));
    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('POST');
      expect(body.manifest).toEqual({
        required_knowledge: ['research-method', 'debug-checklist'],
      });
    });
  });

  it('echoes manifest.required_knowledge as checked in edit mode and keeps the raw key untouched on save', async () => {
    const geneWithKnowledge = {
      ...AI_GENE,
      manifest: {
        skills: ['debug'],
        required_knowledge: ['debug-checklist'],
      },
    };
    mockedApi.mockImplementation((path, init) => {
      if (path === '/ai-genes?limit=200&offset=0') {
        return Promise.resolve({ items: [geneWithKnowledge], total: 1 });
      }
      if (path === '/capability-market?limit=200&offset=0') {
        return Promise.resolve({ items: [], offset: 0, limit: 200, total: 0 });
      }
      if (path === '/knowledge?limit=200&offset=0') {
        return Promise.resolve(knowledgePage);
      }
      if (path === '/ai-genes/gene-1' && init?.method === 'PATCH') {
        return Promise.resolve(geneWithKnowledge);
      }
      return Promise.reject(new Error(`unexpected ${String(path)}`));
    });

    render(<DeepSeaGenesPanel t={t} />);
    fireEvent.click(await screen.findByRole('button', { name: 'namespaces.edit' }));

    const modal = await screen.findByTestId('catalog-form-modal');
    const picker = within(modal).getByTestId('required-knowledge-picker');
    const debugChecklist = await within(picker).findByRole('checkbox', { name: /debug-checklist/ });
    expect(debugChecklist).toBeChecked();
    expect(within(picker).getByRole('checkbox', { name: /research-method/ })).not.toBeChecked();

    fireEvent.click(within(modal).getByRole('button', { name: 'namespaces.save' }));

    await waitFor(() => {
      const body = lastCallBody('PATCH');
      expect(body.manifest).toEqual({
        skills: ['debug'],
        required_knowledge: ['debug-checklist'],
      });
    });
  });
});
