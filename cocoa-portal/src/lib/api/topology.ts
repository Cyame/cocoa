import { api } from '@/lib/api';
import type { LiveStatusItem } from '@/lib/types';

export function fetchTopologyLiveStatus(officeId: string): Promise<readonly LiveStatusItem[]> {
  return api<readonly LiveStatusItem[]>(`/offices/${encodeURIComponent(officeId)}/live-status`);
}
