import { api } from '@/lib/api';
import type { LiveStatusItem } from '@/lib/types';

export function fetchTopologyLiveStatus(workspaceId: string): Promise<readonly LiveStatusItem[]> {
  return api<readonly LiveStatusItem[]>(
    `/workspaces/${encodeURIComponent(workspaceId)}/live-status`,
  );
}
