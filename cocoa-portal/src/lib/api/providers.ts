import { api } from '@/lib/api';
import { getCurrentOrgId } from '@/stores/session';

/**
 * Org-scoped provider lanes live at /organizations/{org_id}/providers...
 * Resolution order for the URL segment: explicit orgId argument → session
 * current org (the same context the API layer sends as X-Organization-Id) →
 * the legacy 'default' alias, which the backend keeps for backward compat.
 */
function orgSegment(orgId?: string): string {
  return encodeURIComponent(orgId ?? getCurrentOrgId() ?? 'default');
}

export type Organization = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly description: string | null;
  readonly system_hub_provider_id: string | null;
  readonly system_hub_model: string | null;
  readonly cerebellum_default_provider_id: string | null;
  readonly cerebellum_default_model: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
};

export type OrganizationProvider = {
  readonly id: string;
  readonly organization_id: string;
  readonly origin: 'catalog' | 'custom';
  readonly catalog_provider_id: string | null;
  readonly name: string;
  readonly slug: string;
  readonly request_format: string;
  readonly base_url: string | null;
  readonly api_key_ref: string;
  readonly default_model: string;
  readonly models_allowlist: readonly string[] | null;
  readonly verify_ssl: boolean;
  readonly models_endpoint_mode: string;
  readonly models_base_url: string | null;
  readonly enabled: boolean;
  readonly last_test_status: string | null;
  readonly last_tested_at: string | null;
  readonly last_test_detail: Record<string, unknown> | null;
  readonly created_at: string;
  readonly updated_at: string | null;
};

export type ProviderCatalogEntry = {
  readonly id: string;
  readonly name: string;
  readonly api: string | null;
  readonly inferred_request_format: string;
  readonly model_count: number;
  readonly doc: string | null;
};

export type CatalogModel = {
  readonly id: string;
  readonly name: string;
  readonly provider: string;
  readonly context_length: number | null;
};

export type CatalogModelsPage = {
  readonly items: readonly CatalogModel[];
  readonly degraded: boolean;
  readonly default_model: string | null;
  readonly error: string | null;
};

export type SystemHubConfig = {
  readonly provider_id: string | null;
  readonly model: string | null;
  readonly configured: boolean;
};

export type CerebellumDefaults = {
  readonly provider_id: string | null;
  readonly model: string | null;
};

export type BaseClassProviderDefault = {
  readonly id: string;
  readonly base_class_id: string;
  readonly provider_id: string;
  readonly model: string;
  readonly created_at: string;
  readonly updated_at: string | null;
};

export type SetDefaultTarget = 'base_class' | 'system_hub' | 'cerebellum';

export type ProviderTestResult = {
  readonly status: 'ok' | 'error';
  readonly detail: Record<string, unknown> | null;
};

export type CerebellumAgent = {
  readonly id: string;
  readonly central_hub_id: string;
  readonly name: string;
  readonly base_slug: string;
  readonly system_prompt: string | null;
  readonly loop_status: string;
  readonly heartbeat_at: string | null;
  readonly installed_genes: unknown;
  readonly provider_id: string | null;
  readonly model: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
};

export function fetchDefaultOrganization(orgId?: string): Promise<Organization> {
  return api<Organization>(`/organizations/${orgSegment(orgId)}`);
}

export function updateDefaultOrganization(
  body: {
    readonly name?: string;
    readonly description?: string | null;
  },
  orgId?: string,
): Promise<Organization> {
  return api<Organization>(`/organizations/${orgSegment(orgId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function listOrganizationProviders(
  enabled?: boolean,
  orgId?: string,
): Promise<readonly OrganizationProvider[]> {
  const query = enabled === undefined ? '' : `?enabled=${enabled ? 'true' : 'false'}`;
  return api<readonly OrganizationProvider[]>(
    `/organizations/${orgSegment(orgId)}/providers${query}`,
  );
}

export type OrganizationProviderCreatePayload = {
  readonly origin: 'catalog' | 'custom';
  readonly catalog_provider_id?: string | null;
  readonly name?: string | null;
  readonly slug?: string | null;
  readonly request_format?: string | null;
  readonly base_url?: string | null;
  readonly api_key_ref: string;
  readonly default_model?: string | null;
  readonly models_allowlist?: readonly string[] | null;
  readonly verify_ssl?: boolean;
  readonly models_endpoint_mode?: 'inherit' | 'separate';
  readonly models_base_url?: string | null;
  readonly enabled?: boolean;
};

export function createOrganizationProvider(
  payload: OrganizationProviderCreatePayload,
  orgId?: string,
): Promise<OrganizationProvider> {
  return api<OrganizationProvider>(`/organizations/${orgSegment(orgId)}/providers`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export type OrganizationProviderUpdatePayload = {
  readonly name?: string;
  readonly request_format?: string;
  readonly base_url?: string | null;
  readonly api_key_ref?: string;
  readonly default_model?: string;
  readonly models_allowlist?: readonly string[] | null;
  readonly verify_ssl?: boolean;
  readonly models_endpoint_mode?: 'inherit' | 'separate';
  readonly models_base_url?: string | null;
  readonly enabled?: boolean;
};

export function updateOrganizationProvider(
  providerId: string,
  payload: OrganizationProviderUpdatePayload,
  orgId?: string,
): Promise<OrganizationProvider> {
  return api<OrganizationProvider>(
    `/organizations/${orgSegment(orgId)}/providers/${encodeURIComponent(providerId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function deleteOrganizationProvider(providerId: string, orgId?: string): Promise<void> {
  return api<void>(
    `/organizations/${orgSegment(orgId)}/providers/${encodeURIComponent(providerId)}`,
    {
      method: 'DELETE',
    },
  );
}

export function testOrganizationProvider(
  providerId: string,
  orgId?: string,
): Promise<ProviderTestResult> {
  return api<ProviderTestResult>(
    `/organizations/${orgSegment(orgId)}/providers/${encodeURIComponent(providerId)}/test`,
    { method: 'POST' },
  );
}

export function setProviderDefault(
  providerId: string,
  payload: {
    readonly target: SetDefaultTarget;
    readonly model: string;
    readonly base_class_ids?: readonly string[];
  },
  orgId?: string,
): Promise<{
  readonly status: string;
  readonly target: string;
  readonly provider_id: string;
  readonly model: string;
}> {
  return api<{
    readonly status: string;
    readonly target: string;
    readonly provider_id: string;
    readonly model: string;
  }>(
    `/organizations/${orgSegment(orgId)}/providers/${encodeURIComponent(providerId)}/set-default`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    },
  );
}

export function fetchSystemHub(orgId?: string): Promise<SystemHubConfig> {
  return api<SystemHubConfig>(`/organizations/${orgSegment(orgId)}/system-hub`);
}

export function updateSystemHub(
  payload: {
    readonly provider_id?: string | null;
    readonly model?: string | null;
  },
  orgId?: string,
): Promise<SystemHubConfig> {
  return api<SystemHubConfig>(`/organizations/${orgSegment(orgId)}/system-hub`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function fetchCerebellumDefaults(orgId?: string): Promise<CerebellumDefaults> {
  return api<CerebellumDefaults>(`/organizations/${orgSegment(orgId)}/cerebellum-defaults`);
}

export function updateCerebellumDefaults(
  payload: {
    readonly provider_id?: string | null;
    readonly model?: string | null;
  },
  orgId?: string,
): Promise<CerebellumDefaults> {
  return api<CerebellumDefaults>(`/organizations/${orgSegment(orgId)}/cerebellum-defaults`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function fetchProviderCatalog(q?: string): Promise<{
  readonly items: readonly ProviderCatalogEntry[];
  readonly degraded: boolean;
}> {
  const query = q ? `?q=${encodeURIComponent(q)}` : '';
  return api<{ readonly items: readonly ProviderCatalogEntry[]; readonly degraded: boolean }>(
    `/provider-catalog${query}`,
  );
}

export function fetchCatalogProviderModels(
  catalogProviderId: string,
  q?: string,
): Promise<CatalogModelsPage> {
  const query = q ? `?q=${encodeURIComponent(q)}` : '';
  return api<CatalogModelsPage>(
    `/provider-catalog/${encodeURIComponent(catalogProviderId)}/models${query}`,
  );
}

export function fetchModelCatalog(
  providerId: string,
  q?: string,
  refresh = false,
): Promise<CatalogModelsPage> {
  const params = new URLSearchParams({ provider_id: providerId });
  if (q) params.set('q', q);
  if (refresh) params.set('refresh', 'true');
  return api<CatalogModelsPage>(`/model-catalog?${params.toString()}`);
}

export function previewProviderModels(
  payload: {
    readonly api_key_ref: string;
    readonly base_url?: string | null;
    readonly request_format?: string;
    readonly verify_ssl?: boolean;
    readonly models_endpoint_mode?: 'inherit' | 'separate';
    readonly models_base_url?: string | null;
    readonly catalog_provider_id?: string | null;
  },
  orgId?: string,
): Promise<CatalogModelsPage> {
  return api<CatalogModelsPage>(`/organizations/${orgSegment(orgId)}/providers/preview-models`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function refreshProviderModels(
  providerId: string,
  orgId?: string,
): Promise<CatalogModelsPage> {
  return api<CatalogModelsPage>(
    `/organizations/${orgSegment(orgId)}/providers/${encodeURIComponent(providerId)}/refresh-models`,
    { method: 'POST' },
  );
}

export function generateDescription(payload: {
  readonly name: string;
  readonly description?: string | null;
  readonly kind?: 'entity' | 'world' | 'namespace' | 'gene' | 'generic';
}): Promise<{ readonly description: string }> {
  return api<{ readonly description: string }>('/system-hub/generate-description', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchBaseClassProviderDefault(
  baseClassId: string,
): Promise<BaseClassProviderDefault | null> {
  return api<BaseClassProviderDefault>(
    `/base-classes/by-id/${encodeURIComponent(baseClassId)}/provider-default`,
  ).catch(() => null);
}

export function updateBaseClassProviderDefault(
  baseClassId: string,
  payload: { readonly provider_id?: string | null; readonly model?: string | null },
): Promise<BaseClassProviderDefault> {
  return api<BaseClassProviderDefault>(
    `/base-classes/by-id/${encodeURIComponent(baseClassId)}/provider-default`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function fetchWorkspaceCerebellum(workspaceId: string): Promise<CerebellumAgent> {
  return api<CerebellumAgent>(`/central-hubs/${encodeURIComponent(workspaceId)}/cerebellum`);
}

export function patchWorkspaceCerebellum(
  workspaceId: string,
  payload: { readonly provider_id?: string | null; readonly model?: string | null },
): Promise<CerebellumAgent> {
  return api<CerebellumAgent>(`/central-hubs/${encodeURIComponent(workspaceId)}/cerebellum`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
