import { api } from '@/lib/api';
import type {
  CombineResult,
  DistillEngine,
  DistillResultOut,
  MemoryKind,
  ReapResult,
} from '@/lib/types';

export function fetchMemorySummary(employeeId: string): Promise<unknown> {
  return api(`/learning/memories/${encodeURIComponent(employeeId)}/summary`);
}

/** v4.9.3: distill = Entity memory → capability_market (not a BaseClass). */
export function distillEntity(
  entityId: string,
  targetSkillSlug: string,
  engine: DistillEngine,
  memoryKindFilter: readonly MemoryKind[] | null = null,
): Promise<DistillResultOut> {
  return api<DistillResultOut>(`/learning/entities/${encodeURIComponent(entityId)}/distill`, {
    method: 'POST',
    body: JSON.stringify({
      target_skill_slug: targetSkillSlug,
      engine,
      memory_kind_filter: memoryKindFilter,
      source_preset_slug: null,
      snapshot_only: false,
    }),
  });
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
  tags: readonly string[] | null = null,
  entityId?: string | null,
  baseClassId?: string | null,
): Promise<CombineResult> {
  return api<CombineResult>('/learning/capabilities/combine', {
    method: 'POST',
    body: JSON.stringify({
      capability_names: capabilityNames,
      gene_slug: geneSlug,
      gene_name: geneName,
      tags,
      entity_id: entityId ?? null,
      base_class_id: baseClassId ?? null,
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
  readonly display_status?: string | null;
  readonly in_conversation?: boolean;
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
