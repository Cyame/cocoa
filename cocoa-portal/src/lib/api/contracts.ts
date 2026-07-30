import { api } from '@/lib/api';

export type NamespaceContract = {
  readonly id: string;
  readonly namespace_id: string;
  readonly user_id: string;
  readonly role: string;
  readonly permissions: Record<string, unknown> | null;
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
