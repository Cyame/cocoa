import { api } from '@/lib/api';
import type { AuthUserPayload, OrgIdentity } from '@/lib/types';

export type MeResponse = AuthUserPayload & {
  readonly org_identity: OrgIdentity | null;
};

export function fetchMe(): Promise<MeResponse> {
  return api<MeResponse>('/auth/me');
}
