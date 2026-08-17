import { api } from '@/lib/api';
import type { BaseClass, Entity, Organization, Workspace } from '@/lib/types';

// v4.4 clone operations. Instance clone is permanently closed on the backend
// (no route registered) — no cloneInstance helper exists on purpose.
export type ClonePayload = {
  readonly name?: string;
  readonly slug?: string;
};

export function cloneOrganization(
  orgId: string,
  payload: ClonePayload = {},
): Promise<Organization> {
  return api<Organization>(`/organizations/${encodeURIComponent(orgId)}/clone`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function cloneWorkspace(
  workspaceId: string,
  payload: ClonePayload = {},
): Promise<Workspace> {
  return api<Workspace>(`/workspaces/${encodeURIComponent(workspaceId)}/clone`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function cloneBaseClass(
  baseClassId: string,
  payload: ClonePayload = {},
): Promise<BaseClass> {
  return api<BaseClass>(`/base-classes/${encodeURIComponent(baseClassId)}/clone`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function cloneEntity(entityId: string, payload: ClonePayload = {}): Promise<Entity> {
  return api<Entity>(`/entities/${encodeURIComponent(entityId)}/clone`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
