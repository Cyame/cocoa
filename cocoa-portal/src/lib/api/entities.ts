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
  readonly namespace_id?: string;
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

type EntityDetailRaw = Omit<EntityDetail, 'capabilities' | 'ai_genes' | 'description'> & {
  readonly capabilities?: readonly Capability[] | null;
  readonly ai_genes?: EntityDetail['ai_genes'] | null;
  readonly description?: string | null;
};

function normalizeEntityDetail(raw: EntityDetailRaw): EntityDetail {
  const capabilities = Array.isArray(raw.capabilities) ? raw.capabilities : [];
  const aiGenes = Array.isArray(raw.ai_genes)
    ? raw.ai_genes
    : capabilities.map((cap) => ({
        slug: cap.name,
        source:
          cap.source === 'extra_added' ? ('extra_added' as const) : ('from_base_class' as const),
      }));
  return {
    ...raw,
    description: raw.description ?? null,
    base_class_slug: raw.base_class_slug ?? raw.preset_slug ?? null,
    creator_email: raw.creator_email ?? null,
    workspace_id: raw.workspace_id ?? null,
    capabilities: capabilities.map((cap) => ({
      ...cap,
      tags: Array.isArray(cap.tags) ? cap.tags : [],
    })),
    ai_genes: aiGenes,
  };
}

export function fetchEntity(entityId: string): Promise<EntityDetail> {
  return api<EntityDetailRaw>(`/entities/${encodeURIComponent(entityId)}`).then(
    normalizeEntityDetail,
  );
}

export function deleteEntity(entityId: string): Promise<void> {
  return api<void>(`/entities/${encodeURIComponent(entityId)}`, {
    method: 'DELETE',
  });
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

export type PromotePayload = {
  readonly mode?: 'update' | 'fork';
  readonly from_instance_id?: string | null;
  readonly include_prompt_regen?: boolean;
  readonly snapshot_only?: boolean;
  readonly new_entity_name?: string | null;
  readonly new_entity_slug?: string | null;
};

export function promoteEntity(
  entityId: string,
  payload: PromotePayload = {},
): Promise<PromoteResult> {
  return api<PromoteResult>(`/learning/entities/${encodeURIComponent(entityId)}/promote`, {
    method: 'POST',
    body: JSON.stringify(payload),
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
