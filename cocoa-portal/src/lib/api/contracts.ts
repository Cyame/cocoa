import { api } from '@/lib/api';
import type { GeneBrief, UserBrief } from '@/lib/types';

export type NamespaceContractGeneRef = {
  readonly id: string;
  readonly slug: string;
};

export type NamespaceContract = {
  readonly id: string;
  readonly namespace_id: string;
  readonly user_id: string;
  // v4.0: no role — the grant is the atomic gene set.
  readonly genes: readonly NamespaceContractGeneRef[];
  readonly created_at: string;
  readonly updated_at: string;
};

type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly total: number;
};

// v4.3 次元契印 detail shape (GET .../contracts?include_inherited=true).
export type NamespaceContractDetail = {
  readonly contract_id: string;
  readonly user: UserBrief;
  readonly namespace_atoms: readonly GeneBrief[];
  readonly inherited_org_atoms?: readonly GeneBrief[];
  readonly created_at: string;
};

export type NamespaceContractsPage = {
  readonly items: readonly NamespaceContractDetail[];
  readonly limit: number;
  readonly offset: number;
  readonly total: number;
};

export type ListNamespaceContractsOptions = {
  readonly includeInherited?: boolean;
  readonly limit?: number;
};

function contractsSearch(opts?: ListNamespaceContractsOptions): URLSearchParams {
  const search = new URLSearchParams({
    limit: String(opts?.limit ?? 200),
    offset: '0',
  });
  if (opts?.includeInherited === true) {
    search.set('include_inherited', 'true');
  }
  return search;
}

export function listNamespaceContracts(
  namespaceId: string,
  opts?: ListNamespaceContractsOptions,
): Promise<OffsetPage<NamespaceContract>> {
  return api<OffsetPage<NamespaceContract>>(
    `/namespaces/${encodeURIComponent(namespaceId)}/contracts?${contractsSearch(opts).toString()}`,
  );
}

// v4.3 wire shape (nested user + atoms; inherited org atoms when requested).
export function listNamespaceContractDetails(
  namespaceId: string,
  opts?: ListNamespaceContractsOptions,
): Promise<NamespaceContractsPage> {
  return api<NamespaceContractsPage>(
    `/namespaces/${encodeURIComponent(namespaceId)}/contracts?${contractsSearch(opts).toString()}`,
  );
}

export function updateNamespaceContractAtoms(
  namespaceId: string,
  contractId: string,
  atomSlugs: readonly string[],
): Promise<NamespaceContractDetail> {
  return api<NamespaceContractDetail>(
    `/namespaces/${encodeURIComponent(namespaceId)}/contracts/${encodeURIComponent(contractId)}/atoms`,
    {
      method: 'PATCH',
      body: JSON.stringify({ atom_slugs: atomSlugs }),
    },
  );
}
