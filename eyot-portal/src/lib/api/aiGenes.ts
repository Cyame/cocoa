import { api } from '@/lib/api';

export type AiGeneScope = 'system' | 'org' | 'namespace';

/** Manifest-inline capability (v4.9.2 A2) — must stay isomorphic to backend `build_capabilities_manifest` output: exactly `{name, type, description}`. */
export type CapabilityInline = {
  readonly name: string;
  readonly type: string;
  readonly description: string | null;
};

export type AiGeneCatalogItem = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly tags: readonly string[] | null;
  readonly manifest?: Record<string, unknown> | null;
  readonly capabilities?: readonly CapabilityInline[] | null;
  readonly description: string | null;
  readonly scope?: AiGeneScope | string;
  readonly organization_id?: string | null;
  readonly namespace_id?: string | null;
  readonly readonly?: boolean;
  readonly created_at: string;
  readonly updated_at: string | null;
};

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

export function listAiGenes(limit = 200): Promise<OffsetPage<AiGeneCatalogItem>> {
  return api<OffsetPage<AiGeneCatalogItem>>(`/ai-genes?limit=${limit}&offset=0`);
}

export function createAiGene(body: {
  readonly slug: string;
  readonly name: string;
  readonly description?: string | null;
  readonly tags?: readonly string[] | null;
  readonly manifest?: Record<string, unknown> | null;
  readonly capabilities?: readonly CapabilityInline[];
  readonly scope?: AiGeneScope;
  readonly organization_id?: string | null;
  readonly namespace_id?: string | null;
}): Promise<AiGeneCatalogItem> {
  return api<AiGeneCatalogItem>('/ai-genes', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function updateAiGene(
  geneId: string,
  body: {
    readonly name?: string;
    readonly description?: string | null;
    readonly tags?: readonly string[] | null;
    readonly manifest?: Record<string, unknown> | null;
    readonly capabilities?: readonly CapabilityInline[];
  },
): Promise<AiGeneCatalogItem> {
  return api<AiGeneCatalogItem>(`/ai-genes/${encodeURIComponent(geneId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deleteAiGene(geneId: string): Promise<void> {
  return api<void>(`/ai-genes/${encodeURIComponent(geneId)}`, {
    method: 'DELETE',
  });
}

export function attachAiGeneToEntity(entityId: string, aiGeneId: string): Promise<void> {
  return api(`/entities/${encodeURIComponent(entityId)}/ai-genes`, {
    method: 'POST',
    body: JSON.stringify({ ai_gene_id: aiGeneId }),
  });
}

export function detachAiGeneFromEntity(entityId: string, aiGeneId: string): Promise<void> {
  return api<void>(
    `/entities/${encodeURIComponent(entityId)}/ai-genes/${encodeURIComponent(aiGeneId)}`,
    { method: 'DELETE' },
  );
}
