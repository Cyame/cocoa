import { api } from '@/lib/api';

/**
 * v4.5 Fornix hub — CentralHub virtual filesystem CRUD + Vault archive.
 *
 * All paths are relative to `/api/v1` (the `api()` helper prepends it).
 * Field names match the backend schemas (app/schemas/fornix_file.py +
 * app/schemas/vault.py), snake_case end-to-end.
 */

export type FornixFile = {
  readonly id: string;
  readonly workspace_id: string;
  readonly name: string;
  readonly parent_path: string | null;
  readonly storage_key: string;
  readonly content_type: string | null;
  readonly file_size: number | null;
  readonly is_directory: boolean;
  readonly content: string | null;
  readonly uploader_user_id: string | null;
  readonly uploader_instance_id: string | null;
  readonly created_at: string;
};

export type VaultEntry = {
  readonly id: string;
  readonly vault_id: string;
  readonly source_type: string;
  readonly source_ref: string | null;
  readonly archived_key: string | null;
  readonly archived_at: string | null;
  readonly created_at: string;
};

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

export type FornixFileCreatePayload = {
  readonly workspace_id: string;
  readonly name: string;
  readonly parent_path?: string | null;
  readonly storage_key?: string;
  readonly content_type?: string | null;
  readonly file_size?: number | null;
  readonly is_directory?: boolean;
  readonly content?: string | null;
};

export type FornixFileUpdatePayload = {
  readonly name?: string | null;
  readonly parent_path?: string | null;
};

function hubBase(workspaceId: string): string {
  return `/central-hubs/${encodeURIComponent(workspaceId)}`;
}

export function listFornixFiles(
  workspaceId: string,
  params: {
    readonly parent_path?: string;
    readonly limit?: number;
    readonly offset?: number;
  } = {},
): Promise<OffsetPage<FornixFile>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.parent_path !== undefined && params.parent_path.length > 0) {
    search.set('parent_path', params.parent_path);
  }
  return api<OffsetPage<FornixFile>>(`${hubBase(workspaceId)}/files?${search.toString()}`);
}

export function fetchFornixFile(workspaceId: string, fileId: string): Promise<FornixFile> {
  return api<FornixFile>(`${hubBase(workspaceId)}/files/${encodeURIComponent(fileId)}`);
}

export function createFornixFile(
  workspaceId: string,
  payload: FornixFileCreatePayload,
): Promise<FornixFile> {
  return api<FornixFile>(`${hubBase(workspaceId)}/files`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function patchFornixFile(
  workspaceId: string,
  fileId: string,
  payload: FornixFileUpdatePayload,
): Promise<FornixFile> {
  return api<FornixFile>(`${hubBase(workspaceId)}/files/${encodeURIComponent(fileId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteFornixFile(workspaceId: string, fileId: string): Promise<void> {
  return api<void>(`${hubBase(workspaceId)}/files/${encodeURIComponent(fileId)}`, {
    method: 'DELETE',
  });
}

export function archiveFornixFile(workspaceId: string, fileId: string): Promise<VaultEntry> {
  return api<VaultEntry>(`${hubBase(workspaceId)}/files/${encodeURIComponent(fileId)}/archive`, {
    method: 'POST',
  });
}

export function listVaultEntries(
  workspaceId: string,
  params: {
    readonly source_type?: string;
    readonly archived_key?: string;
    readonly limit?: number;
    readonly offset?: number;
  } = {},
): Promise<OffsetPage<VaultEntry>> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  if (params.source_type !== undefined && params.source_type.length > 0) {
    search.set('source_type', params.source_type);
  }
  if (params.archived_key !== undefined && params.archived_key.length > 0) {
    search.set('archived_key', params.archived_key);
  }
  return api<OffsetPage<VaultEntry>>(`${hubBase(workspaceId)}/vault/entries?${search.toString()}`);
}

export function restoreVaultEntry(workspaceId: string, entryId: string): Promise<FornixFile> {
  return api<FornixFile>(
    `${hubBase(workspaceId)}/vault/entries/${encodeURIComponent(entryId)}/restore`,
    { method: 'POST' },
  );
}
