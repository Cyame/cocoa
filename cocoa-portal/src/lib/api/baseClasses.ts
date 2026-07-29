import { api } from '@/lib/api';
import type { BaseClass } from '@/lib/types';

export type BaseClassPage = {
  readonly items: readonly BaseClass[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export async function fetchBaseClassesPage(
  params: { readonly limit?: number; readonly offset?: number } = {},
): Promise<BaseClassPage> {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 50));
  search.set('offset', String(params.offset ?? 0));
  return api<BaseClassPage>(`/base-classes?${search.toString()}`);
}
