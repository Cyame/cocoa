import { api } from '@/lib/api';
import type { Instance, Membership } from '@/lib/types';

/**
 * Phase-15f T3 / T6: response shape for
 * ``POST /api/v1/instances/batch-restart``.
 *
 * Mirrors :class:`app.schemas.instance_actions.BatchRestartResultOut`.
 */
export type BatchRestartResult = {
  readonly restarted_count: number;
  readonly restarted_at: string;
  readonly instance_ids: readonly string[];
  readonly skipped: readonly string[];
};

export type InstanceCreatePayload = {
  readonly entity_id: string;
  readonly workspace_id: string;
  readonly workspace_path?: string | null;
  readonly runtime_config?: Record<string, unknown> | null;
};

export type InstanceWithToken = Instance & {
  readonly proxy_token?: string | null;
  readonly deploy_record_id?: string | null;
};

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export function createInstance(payload: InstanceCreatePayload): Promise<InstanceWithToken> {
  return api<InstanceWithToken>('/instances', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listInstances(params: {
  readonly entity_id?: string;
  readonly workspace_id?: string;
  readonly status?: string;
  readonly limit?: number;
  readonly offset?: number;
}): Promise<OffsetPage<Instance>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.entity_id !== undefined) search.set('entity_id', params.entity_id);
  if (params.workspace_id !== undefined) search.set('workspace_id', params.workspace_id);
  if (params.status !== undefined) search.set('status', params.status);
  return api<OffsetPage<Instance>>(`/instances?${search.toString()}`);
}

/**
 * Phase-15f T3 / T6: bulk re-sync outdated instances to the current
 * ``Employee.migration_hash``.
 *
 * The backend rejects the entire batch with ``409`` if any of the
 * referenced instances is currently ``running`` (the operator must stop
 * running instances first, or restart them individually with
 * ``force=true``).
 *
 * @param instanceIds Non-empty list of instance UUIDs to re-sync.
 * @param reason Optional free-form reason recorded in the audit event.
 */
export function batchRestartInstances(
  instanceIds: readonly string[],
  reason: string | null = null,
): Promise<BatchRestartResult> {
  return api<BatchRestartResult>('/instances/batch-restart', {
    method: 'POST',
    body: JSON.stringify({
      instance_ids: instanceIds,
      reason,
    }),
  });
}

export function stopInstance(instanceId: string): Promise<Instance> {
  return api<Instance>(`/instances/${encodeURIComponent(instanceId)}/stop`, {
    method: 'POST',
  });
}

export function restartInstance(
  instanceId: string,
  options: { readonly force?: boolean; readonly reason?: string | null } = {},
): Promise<{
  readonly restarted_at: string;
  readonly instance_id: string;
  readonly old_hash: string | null;
  readonly new_hash: string | null;
  readonly status_after: string;
}> {
  return api<{
    readonly restarted_at: string;
    readonly instance_id: string;
    readonly old_hash: string | null;
    readonly new_hash: string | null;
    readonly status_after: string;
  }>(`/instances/${encodeURIComponent(instanceId)}/restart`, {
    method: 'POST',
    body: JSON.stringify({
      force: options.force ?? true,
      reason: options.reason ?? null,
    }),
  });
}

export function deleteInstanceById(instanceId: string): Promise<void> {
  return api<void>(`/instances/${encodeURIComponent(instanceId)}`, {
    method: 'DELETE',
  });
}

export function deleteMembership(membershipId: string): Promise<void> {
  return api<void>(`/messaging/memberships/${encodeURIComponent(membershipId)}`, {
    method: 'DELETE',
  });
}

export type MembershipCreatePayload = {
  readonly workspace_id: string;
  readonly user_id?: string | null;
  readonly instance_id?: string | null;
  readonly posx?: number;
  readonly posy?: number;
  readonly role?: 'owner' | 'editor' | 'viewer';
};

export function createMembership(payload: MembershipCreatePayload): Promise<Membership> {
  return api<Membership>('/messaging/memberships', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function listMemberships(
  workspaceId: string,
  limit = 200,
  kind?: 'user' | 'instance',
): Promise<OffsetPage<Membership>> {
  const search = new URLSearchParams();
  search.set('workspace_id', workspaceId);
  search.set('limit', String(limit));
  search.set('offset', '0');
  if (kind !== undefined) search.set('kind', kind);
  return api<OffsetPage<Membership>>(`/messaging/memberships?${search.toString()}`);
}

/** Pick a free canvas slot for a new membership in the workspace. */
export async function nextMembershipPosition(
  workspaceId: string,
): Promise<{ posx: number; posy: number }> {
  const page = await listMemberships(workspaceId);
  const occupied = new Set(page.items.map((m) => `${m.posx},${m.posy}`));
  for (let row = 0; row < 40; row += 1) {
    for (let col = 0; col < 40; col += 1) {
      const posx = col * 120;
      const posy = row * 120;
      if (!occupied.has(`${posx},${posy}`)) {
        return { posx, posy };
      }
    }
  }
  return { posx: 0, posy: 0 };
}

/**
 * PRD-v3.4 primary path: introduce 眷族 into a workspace → create 迷失者.
 */
export function introduceEntityIntoWorkspace(
  workspaceId: string,
  entityId: string,
): Promise<InstanceWithToken> {
  return api<InstanceWithToken>(`/workspaces/${encodeURIComponent(workspaceId)}/introduce-entity`, {
    method: 'POST',
    body: JSON.stringify({ entity_id: entityId }),
  });
}

/**
 * @deprecated Prefer {@link introduceEntityIntoWorkspace} (PRD-v3.4).
 * Kept for internal/compat callers.
 */
export async function spawnInstanceIntoWorkspace(
  entityId: string,
  workspaceId: string,
): Promise<InstanceWithToken> {
  return introduceEntityIntoWorkspace(workspaceId, entityId);
}
