import { api } from '@/lib/api';

export type IdentityKey = 'system' | 'org' | 'namespace' | 'workspace' | 'member';

export type UserGeneRef = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly locked: boolean;
};

export type AdminUser = {
  readonly id: string;
  readonly username: string;
  readonly nickname: string | null;
  readonly email: string;
  readonly is_super_admin: boolean;
  readonly identity: IdentityKey | null;
  readonly locked_genes: readonly UserGeneRef[];
  readonly extra_genes: readonly UserGeneRef[];
  readonly created_at: string | null;
  readonly updated_at: string | null;
};

export type AdminUserCreateOut = AdminUser & {
  readonly temporary_password: string;
};

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export type AccountProfile = {
  readonly id: string;
  readonly username: string;
  readonly nickname: string | null;
  readonly email: string;
  readonly is_super_admin: boolean;
  readonly identity: IdentityKey | null;
  readonly locked_genes: readonly UserGeneRef[];
  readonly extra_genes: readonly UserGeneRef[];
};

export async function listUsers(limit = 100, offset = 0): Promise<OffsetPage<AdminUser>> {
  return api<OffsetPage<AdminUser>>(`/users?limit=${limit}&offset=${offset}`);
}

export async function createUser(body: {
  readonly username: string;
  readonly nickname?: string | null;
  readonly email: string;
  readonly identity?: IdentityKey;
}): Promise<AdminUserCreateOut> {
  return api<AdminUserCreateOut>('/users', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function updateUser(
  userId: string,
  body: {
    readonly email?: string;
    readonly nickname?: string | null;
    readonly identity?: IdentityKey;
  },
): Promise<AdminUser> {
  return api<AdminUser>(`/users/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function setUserIdentity(
  userId: string,
  identity: IdentityKey,
): Promise<AdminUser> {
  return api<AdminUser>(`/users/${userId}/identity`, {
    method: 'POST',
    body: JSON.stringify({ identity }),
  });
}

export async function setUserExtraGenes(
  userId: string,
  geneIds: readonly string[],
): Promise<AdminUser> {
  return api<AdminUser>(`/users/${userId}/extra-genes`, {
    method: 'PUT',
    body: JSON.stringify({ gene_ids: geneIds }),
  });
}

export async function deleteUser(userId: string): Promise<void> {
  await api(`/users/${userId}`, { method: 'DELETE' });
}

export async function fetchAccount(): Promise<AccountProfile> {
  return api<AccountProfile>('/account');
}

export async function updateAccount(body: {
  readonly email?: string;
  readonly nickname?: string | null;
}): Promise<AccountProfile> {
  return api<AccountProfile>('/account', {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function changeAccountPassword(body: {
  readonly current_password: string;
  readonly new_password: string;
}): Promise<void> {
  await api('/account/password', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export type CatalogUserGene = {
  readonly id: string;
  readonly slug: string;
  readonly name: string;
  readonly kind: string;
  readonly permission_keys: readonly string[];
  readonly description: string | null;
};

export async function listUserGenes(limit = 200): Promise<OffsetPage<CatalogUserGene>> {
  return api<OffsetPage<CatalogUserGene>>(`/user-genes?limit=${limit}&offset=0`);
}

export async function listPermissionKeys(): Promise<readonly string[]> {
  const page = await api<{ readonly items: readonly string[] }>('/user-genes/permission-keys');
  return page.items;
}

export async function updateUserGene(
  geneId: string,
  body: {
    readonly name?: string;
    readonly permission_keys?: readonly string[];
    readonly description?: string | null;
  },
): Promise<CatalogUserGene> {
  return api<CatalogUserGene>(`/user-genes/${encodeURIComponent(geneId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export async function createUserGene(body: {
  readonly slug: string;
  readonly name: string;
  readonly permission_keys?: readonly string[];
  readonly description?: string | null;
}): Promise<CatalogUserGene> {
  return api<CatalogUserGene>('/user-genes', {
    method: 'POST',
    body: JSON.stringify({ kind: 'custom', ...body }),
  });
}
