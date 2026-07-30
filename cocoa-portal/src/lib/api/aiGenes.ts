import { api } from '@/lib/api';

export type AiGeneCatalogItem = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly tags: readonly string[] | null;
  readonly description: string | null;
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
