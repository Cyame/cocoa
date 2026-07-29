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

export async function fetchDefaultNamespace(): Promise<NamespaceWithStats | null> {
  try {
    const page = await fetchNamespaces();
    return page.items[0] ?? null;
  } catch {
    return null;
  }
}
