import { api } from '@/lib/api';
import type { Namespace } from '@/lib/types';

export type NamespaceWithStats = Namespace & {
  readonly workspace_count: number;
  readonly entity_count: number;
};

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export async function fetchNamespaces(): Promise<OffsetPage<NamespaceWithStats>> {
  return api<OffsetPage<NamespaceWithStats>>('/namespaces?limit=50&offset=0');
}

export async function createNamespace(body: {
  readonly name: string;
  readonly slug: string;
  readonly description?: string | null;
  readonly org_id?: string | null;
}): Promise<Namespace> {
  return api<Namespace>('/namespaces', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateNamespace(
  id: string,
  body: { readonly name?: string; readonly description?: string | null },
): Promise<Namespace> {
  return api<Namespace>(`/namespaces/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function deleteNamespace(id: string): Promise<void> {
  await api(`/namespaces/${id}`, { method: 'DELETE' });
}

export async function fetchDefaultNamespace(): Promise<NamespaceWithStats | null> {
  try {
    const page = await fetchNamespaces();
    return page.items[0] ?? null;
  } catch {
    return null;
  }
}
