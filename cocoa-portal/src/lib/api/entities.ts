import { api } from '@/lib/api';
import type {
  BaseClass,
  Capability,
  EntityPatchPayload,
  PromoteResult,
  TransmuteResult,
} from '@/lib/types';

export type { TransmuteResult };

export type EntityDetail = {
  readonly id: string;
  readonly name: string;
  readonly slug: string;
  readonly rank: 'intern' | 'researcher' | 'director';
  readonly preset_slug: string | null;
  readonly display_name: string | null;
  readonly display_color: string | null;
  readonly description: string | null;
  readonly base_class_slug: string | null;
  readonly capabilities: readonly Capability[];
  readonly ai_genes: readonly {
    readonly slug: string;
    readonly source: 'from_base_class' | 'extra_added';
  }[];
  readonly creator_email: string | null;
  readonly workspace_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
};

export function fetchEntity(entityId: string): Promise<EntityDetail> {
  return api<EntityDetail>(`/entities/${encodeURIComponent(entityId)}`);
}

export function patchEntity(
  entityId: string,
  payload: EntityPatchPayload,
  ifMatch: string,
): Promise<EntityDetail> {
  return api<EntityDetail>(`/entities/${encodeURIComponent(entityId)}`, {
    method: 'PATCH',
    headers: { 'If-Match': ifMatch },
    body: JSON.stringify(payload),
  });
}

export function fetchBaseClass(slug: string): Promise<BaseClass> {
  return api<BaseClass>(`/base-classes/${encodeURIComponent(slug)}`);
}

export function promoteEntity(
  entityId: string,
  memoryKindFilter: readonly string[] | null,
): Promise<PromoteResult> {
  return api<PromoteResult>(`/learning/entities/${encodeURIComponent(entityId)}/promote`, {
    method: 'POST',
    body: JSON.stringify({ memory_kind_filter: memoryKindFilter }),
  });
}

export function transmuteEntity(
  entityId: string,
  targetBaseClassSlug: string,
  targetBaseClassName: string,
  memoryKindFilter: readonly string[] | null,
): Promise<TransmuteResult> {
  return api<TransmuteResult>(`/learning/entities/${encodeURIComponent(entityId)}/transmute`, {
    method: 'POST',
    body: JSON.stringify({
      target_base_class_slug: targetBaseClassSlug,
      target_base_class_name: targetBaseClassName,
      memory_kind_filter: memoryKindFilter,
      snapshot_only: false,
    }),
  });
}
