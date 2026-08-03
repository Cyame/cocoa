import { api } from '@/lib/api';

export type NamespaceContractGeneRef = {
  readonly id: string;
  readonly slug: string;
};

export type NamespaceContract = {
  readonly id: string;
  readonly namespace_id: string;
  readonly user_id: string;
  // v4.0: no role — the grant is the atomic gene set.
  readonly genes: readonly NamespaceContractGeneRef[];
  readonly created_at: string;
  readonly updated_at: string;
};

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

export function listNamespaceContracts(
  namespaceId: string,
  limit = 200,
): Promise<OffsetPage<NamespaceContract>> {
  const search = new URLSearchParams({
    limit: String(limit),
    offset: '0',
  });
  return api<OffsetPage<NamespaceContract>>(
    `/namespaces/${encodeURIComponent(namespaceId)}/contracts?${search.toString()}`,
  );
}
