import { api } from '@/lib/api';
import type { Workspace } from '@/lib/types';

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export function fetchWorkspaces(
  params: {
    readonly limit?: number;
    readonly offset?: number;
    readonly namespace_id?: string;
  } = {},
): Promise<OffsetPage<Workspace>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.namespace_id !== undefined) {
    search.set('namespace_id', params.namespace_id);
  }
  return api<OffsetPage<Workspace>>(`/workspaces?${search.toString()}`);
}

export function fetchWorkspace(workspaceId: string): Promise<Workspace> {
  return api<Workspace>(`/workspaces/${encodeURIComponent(workspaceId)}`);
}

export type WorkspaceCreatePayload = {
  readonly name: string;
  readonly slug: string;
  readonly namespace_id?: string | null;
};

export function createWorkspace(payload: WorkspaceCreatePayload): Promise<Workspace> {
  return api<Workspace>('/workspaces', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
