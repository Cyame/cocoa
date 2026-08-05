import { api } from '@/lib/api';
import type { BrainstemSchedule, JsonObject } from '@/lib/types';

/**
 * v4.8 Brainstem schedules — `/api/v1/central-hubs/{workspace_id}/brainstem/schedules`.
 *
 * Fields match app/schemas/brain_regions.py. Cancel is expressed as
 * `updateSchedule(..., { enabled: false })` (plan M1 recommendation).
 */

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export type BrainstemScheduleCreatePayload = {
  readonly name: string;
  readonly cron_expr: string;
  readonly action_payload?: JsonObject | null;
  readonly enabled?: boolean;
};

export type BrainstemScheduleUpdatePayload = {
  readonly name?: string;
  readonly cron_expr?: string;
  readonly action_payload?: JsonObject | null;
  readonly enabled?: boolean;
};

function schedulesBase(workspaceId: string): string {
  return `/central-hubs/${encodeURIComponent(workspaceId)}/brainstem/schedules`;
}

export function fetchSchedules(workspaceId: string): Promise<OffsetPage<BrainstemSchedule>> {
  const search = new URLSearchParams();
  search.set('limit', '200');
  return api<OffsetPage<BrainstemSchedule>>(`${schedulesBase(workspaceId)}?${search.toString()}`);
}

export function createSchedule(
  workspaceId: string,
  payload: BrainstemScheduleCreatePayload,
): Promise<BrainstemSchedule> {
  return api<BrainstemSchedule>(schedulesBase(workspaceId), {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateSchedule(
  workspaceId: string,
  scheduleId: string,
  payload: BrainstemScheduleUpdatePayload,
): Promise<BrainstemSchedule> {
  return api<BrainstemSchedule>(`${schedulesBase(workspaceId)}/${encodeURIComponent(scheduleId)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteSchedule(workspaceId: string, scheduleId: string): Promise<void> {
  return api<void>(`${schedulesBase(workspaceId)}/${encodeURIComponent(scheduleId)}`, {
    method: 'DELETE',
  });
}
