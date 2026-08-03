import { api } from '@/lib/api';

export type CapabilityScope = 'system' | 'org' | 'namespace';
export type CapabilityType = 'skill' | 'tool' | 'mcp' | 'lsp' | 'command';

export type CapabilityMarketEntry = {
  readonly id: string;
  readonly name: string;
  readonly type: CapabilityType | string;
  readonly description: string | null;
  readonly config_template: Record<string, unknown> | null;
  readonly tags: readonly string[] | null;
  readonly scope: CapabilityScope | string;
  readonly organization_id: string | null;
  readonly namespace_id: string | null;
  readonly created_by_user_id: string | null;
  readonly created_via: string;
  readonly source_entity_slug: string | null;
  readonly readonly?: boolean;
  readonly created_at: string;
  readonly updated_at: string | null;
};

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export function listCapabilityMarket(limit = 200): Promise<OffsetPage<CapabilityMarketEntry>> {
  return api<OffsetPage<CapabilityMarketEntry>>(
    `/capability-market?limit=${limit}&offset=0`,
  );
}

export function createCapability(body: {
  readonly name: string;
  readonly type?: CapabilityType;
  readonly description?: string | null;
  readonly scope?: CapabilityScope;
  readonly organization_id?: string | null;
  readonly namespace_id?: string | null;
  readonly tags?: readonly string[] | null;
}): Promise<CapabilityMarketEntry> {
  return api<CapabilityMarketEntry>('/capability-market', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function updateCapability(
  entryId: string,
  body: {
    readonly name?: string;
    readonly type?: CapabilityType;
    readonly description?: string | null;
    readonly tags?: readonly string[] | null;
  },
): Promise<CapabilityMarketEntry> {
  return api<CapabilityMarketEntry>(`/capability-market/${encodeURIComponent(entryId)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deleteCapability(entryId: string): Promise<void> {
  return api<void>(`/capability-market/${encodeURIComponent(entryId)}`, {
    method: 'DELETE',
  });
}
