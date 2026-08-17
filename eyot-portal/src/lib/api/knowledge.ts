import { api } from '@/lib/api';

/**
 * v4.2 Knowledge system — knowledge_entries / knowledge_dimensions CRUD.
 *
 * Field names match the backend schemas (app/schemas/knowledge.py), snake_case
 * end-to-end. `key` / dimension `slug` are normalized to lowercase by the
 * backend at write time; the portal also lowercases key input client-side.
 */

export type KnowledgeEntryScope = 'system' | 'org' | 'namespace' | 'workspace';

export type KnowledgeEntry = {
  readonly id: string;
  readonly key: string;
  readonly title: string;
  readonly body: string;
  readonly dimension_id: string | null;
  readonly scope: KnowledgeEntryScope;
  readonly organization_id: string | null;
  readonly namespace_id: string | null;
  readonly workspace_id: string | null;
  readonly entity_id: string | null;
  readonly instance_id: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
};

export type KnowledgeDimension = {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly description: string | null;
  readonly scope: KnowledgeEntryScope;
  readonly organization_id: string | null;
  readonly namespace_id: string | null;
  readonly workspace_id: string | null;
  readonly created_at: string;
  readonly updated_at: string | null;
};

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export type KnowledgeEntryCreatePayload = {
  readonly key: string;
  readonly title: string;
  readonly body: string;
  readonly dimension_id?: string | null;
  readonly scope: KnowledgeEntryScope;
  readonly organization_id?: string | null;
  readonly namespace_id?: string | null;
  readonly workspace_id?: string | null;
};

export type KnowledgeEntryUpdatePayload = {
  readonly key?: string;
  readonly title?: string;
  readonly body?: string;
  readonly dimension_id?: string | null;
};

export type KnowledgeDimensionCreatePayload = {
  readonly name: string;
  readonly slug?: string | null;
  readonly description?: string | null;
  readonly scope: KnowledgeEntryScope;
  readonly organization_id?: string | null;
  readonly namespace_id?: string | null;
  readonly workspace_id?: string | null;
};

export function fetchKnowledgeEntries(
  params: {
    readonly scope?: KnowledgeEntryScope;
    readonly limit?: number;
    readonly offset?: number;
  } = {},
): Promise<OffsetPage<KnowledgeEntry>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.scope !== undefined) {
    search.set('scope', params.scope);
  }
  return api<OffsetPage<KnowledgeEntry>>(`/knowledge?${search.toString()}`);
}

export function fetchKnowledgeEntry(entryId: string): Promise<KnowledgeEntry> {
  return api<KnowledgeEntry>(`/knowledge/${encodeURIComponent(entryId)}`);
}

export function createKnowledgeEntry(
  payload: KnowledgeEntryCreatePayload,
): Promise<KnowledgeEntry> {
  return api<KnowledgeEntry>('/knowledge', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateKnowledgeEntry(
  entryId: string,
  payload: KnowledgeEntryUpdatePayload,
): Promise<KnowledgeEntry> {
  return api<KnowledgeEntry>(`/knowledge/${encodeURIComponent(entryId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteKnowledgeEntry(entryId: string): Promise<void> {
  return api<void>(`/knowledge/${encodeURIComponent(entryId)}`, { method: 'DELETE' });
}

export function fetchKnowledgeDimensions(
  params: { readonly limit?: number; readonly offset?: number } = {},
): Promise<OffsetPage<KnowledgeDimension>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  return api<OffsetPage<KnowledgeDimension>>(`/knowledge-dimensions?${search.toString()}`);
}

export function createKnowledgeDimension(
  payload: KnowledgeDimensionCreatePayload,
): Promise<KnowledgeDimension> {
  return api<KnowledgeDimension>('/knowledge-dimensions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteKnowledgeDimension(dimensionId: string): Promise<void> {
  return api<void>(`/knowledge-dimensions/${encodeURIComponent(dimensionId)}`, {
    method: 'DELETE',
  });
}
