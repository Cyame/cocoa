import { ApiError, api } from '@/lib/api';
import type { Organization, OrgMember, UserBrief } from '@/lib/types';

export type OrganizationCreatePayload = {
  readonly name: string;
  readonly slug: string;
  readonly description?: string | null;
};

export type OrganizationUpdatePayload = {
  readonly name?: string;
  readonly slug?: string;
  readonly description?: string | null;
};

export type OrgMembersPage = {
  readonly items: readonly OrgMember[];
};

export type OrganizationMemberAddPayload = {
  readonly user_id?: string;
  readonly q?: string;
  readonly atom_slugs?: readonly string[];
};

export type OrganizationMemberUpdatePayload = {
  readonly atom_slugs: readonly string[];
};

export type SearchUsersPage = {
  readonly items: readonly UserBrief[];
};

export function fetchOrganizations(): Promise<readonly Organization[]> {
  return api<readonly Organization[]>('/organizations');
}

export async function createOrganization(
  payload: OrganizationCreatePayload,
): Promise<Organization> {
  const created = await api<Organization>('/organizations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  // POST /organizations returns 201 with the created org in the body
  // (incl. its id). Fail loudly instead of returning an id-less object.
  if (created === null || typeof created.id !== 'string' || created.id.length === 0) {
    throw new ApiError(201, created);
  }
  return created;
}

export function fetchOrganization(orgId: string): Promise<Organization> {
  return api<Organization>(`/organizations/${encodeURIComponent(orgId)}`);
}

export function updateOrganization(
  orgId: string,
  payload: OrganizationUpdatePayload,
): Promise<Organization> {
  return api<Organization>(`/organizations/${encodeURIComponent(orgId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteOrganization(orgId: string): Promise<void> {
  return api<void>(`/organizations/${encodeURIComponent(orgId)}`, { method: 'DELETE' });
}

export function fetchOrganizationMembers(orgId: string): Promise<OrgMembersPage> {
  return api<OrgMembersPage>(`/organizations/${encodeURIComponent(orgId)}/members`);
}

export function addOrganizationMember(
  orgId: string,
  payload: OrganizationMemberAddPayload,
): Promise<OrgMember> {
  return api<OrgMember>(`/organizations/${encodeURIComponent(orgId)}/members`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateOrganizationMember(
  orgId: string,
  contractId: string,
  payload: OrganizationMemberUpdatePayload,
): Promise<OrgMember> {
  return api<OrgMember>(
    `/organizations/${encodeURIComponent(orgId)}/members/${encodeURIComponent(contractId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    },
  );
}

export function removeOrganizationMember(orgId: string, contractId: string): Promise<void> {
  return api<void>(
    `/organizations/${encodeURIComponent(orgId)}/members/${encodeURIComponent(contractId)}`,
    { method: 'DELETE' },
  );
}

export function searchUsers(q: string, limit = 20): Promise<SearchUsersPage> {
  const search = new URLSearchParams({ q, limit: String(limit) });
  return api<SearchUsersPage>(`/users?${search.toString()}`);
}
