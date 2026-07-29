import { api } from '@/lib/api';

/**
 * Phase-15f T3 / T6: response shape for
 * ``POST /api/v1/instances/batch-restart``.
 *
 * Mirrors :class:`app.schemas.instance_actions.BatchRestartResultOut`.
 */
export type BatchRestartResult = {
  readonly restarted_count: number;
  readonly restarted_at: string;
  readonly instance_ids: readonly string[];
  readonly skipped: readonly string[];
};

/**
 * Phase-15f T3 / T6: bulk re-sync outdated instances to the current
 * ``Employee.migration_hash``.
 *
 * The backend rejects the entire batch with ``409`` if any of the
 * referenced instances is currently ``running`` (the operator must stop
 * running instances first, or restart them individually with
 * ``force=true``).
 *
 * @param instanceIds Non-empty list of instance UUIDs to re-sync.
 * @param reason Optional free-form reason recorded in the audit event.
 */
export function batchRestartInstances(
  instanceIds: readonly string[],
  reason: string | null = null,
): Promise<BatchRestartResult> {
  return api<BatchRestartResult>('/instances/batch-restart', {
    method: 'POST',
    body: JSON.stringify({
      instance_ids: instanceIds,
      reason,
    }),
  });
}
