import { api } from '@/lib/api';
import type { CombineResult, ReapResult } from '@/lib/types';

export function fetchMemorySummary(employeeId: string): Promise<unknown> {
  return api(`/learning/memories/${encodeURIComponent(employeeId)}/summary`);
}

export function reapInstance(
  instanceId: string,
  memoryKindFilter: readonly string[] | null,
  maxCapabilities = 10,
): Promise<ReapResult> {
  return api<ReapResult>(`/learning/instances/${encodeURIComponent(instanceId)}/reap`, {
    method: 'POST',
    body: JSON.stringify({
      memory_kind_filter: memoryKindFilter,
      max_capabilities: maxCapabilities,
      snapshot_only: false,
    }),
  });
}

export function combineCapabilities(
  capabilityNames: readonly string[],
  geneSlug: string,
  geneName: string,
  kind = 'tool-gene',
  tags: readonly string[] | null = null,
): Promise<CombineResult> {
  return api<CombineResult>('/learning/capabilities/combine', {
    method: 'POST',
    body: JSON.stringify({
      capability_names: capabilityNames,
      gene_slug: geneSlug,
      gene_name: geneName,
      kind,
      tags,
      snapshot_only: false,
    }),
  });
}

export function deleteInstance(instanceId: string): Promise<void> {
  return api<void>(`/instances/${encodeURIComponent(instanceId)}`, {
    method: 'DELETE',
  });
}

export type InstanceStatusPayload = {
  readonly id: string;
  readonly entity_id: string;
  readonly workspace_id: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
};

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset?: number;
  readonly limit?: number;
  readonly total: number | null;
  readonly next_cursor?: string | null;
};

export function listInstancesForEntity(
  entityId: string,
  limit = 200,
): Promise<OffsetPage<InstanceStatusPayload>> {
  return api<OffsetPage<InstanceStatusPayload>>(
    `/instances?entity_id=${encodeURIComponent(entityId)}&limit=${limit}`,
  );
}
