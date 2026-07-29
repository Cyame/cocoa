import { api } from '@/lib/api';
import type { LiveStatusItem } from '@/lib/types';

/**
 * Phase-15f T6: fetch the live-status snapshot for an office.
 *
 * Each item carries an ``outdated`` flag (true when the instance's
 * ``active_hash`` does not match the current ``Employee.migration_hash``)
 * and the raw ``active_hash`` so the portal can render the "needs
 * restart" badge and surface outdated instances in the batch-restart
 * modal.
 */
export function fetchLiveStatus(workspaceId: string): Promise<readonly LiveStatusItem[]> {
  return api<readonly LiveStatusItem[]>(
    `/workspaces/${encodeURIComponent(workspaceId)}/live-status`,
  );
}
