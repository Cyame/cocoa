import { api } from '@/lib/api';

export type AiGeneScope = 'system' | 'org' | 'namespace';

export type AiGeneCatalogItem = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly tags: readonly string[] | null;
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
