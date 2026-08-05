import { api } from '@/lib/api';
import type { Meeting } from '@/lib/types';

/**
 * v4.8 Meetings — `/api/v1/meetings`.
 *
 * Field names match the backend schemas (app/schemas/meeting.py),
 * snake_case end-to-end. List responses carry `participants: []`; only
 * create / detail responses include the participant rows.
 */

export type OffsetPage<T> = {
  readonly items: readonly T[];
  readonly offset: number;
  readonly limit: number;
  readonly total: number;
};

export type MeetingCreatePayload = {
  readonly workspace_id: string;
  readonly title: string;
  readonly agenda?: string | null;
  /** ISO 8601; required by the backend schema. */
  readonly scheduled_at: string;
  readonly participant_membership_ids?: readonly string[];
};

export function createMeeting(payload: MeetingCreatePayload): Promise<Meeting> {
  return api<Meeting>('/meetings', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function fetchMeetings(workspaceId: string): Promise<OffsetPage<Meeting>> {
  const search = new URLSearchParams();
  search.set('workspace_id', workspaceId);
  search.set('limit', '200');
  return api<OffsetPage<Meeting>>(`/meetings?${search.toString()}`);
}

export function fetchMeeting(meetingId: string): Promise<Meeting> {
  return api<Meeting>(`/meetings/${encodeURIComponent(meetingId)}`);
}

export function startMeeting(meetingId: string): Promise<Meeting> {
  return api<Meeting>(`/meetings/${encodeURIComponent(meetingId)}/start`, { method: 'POST' });
}

export function endMeeting(meetingId: string): Promise<Meeting> {
  return api<Meeting>(`/meetings/${encodeURIComponent(meetingId)}/end`, { method: 'POST' });
}

export function cancelMeeting(meetingId: string): Promise<Meeting> {
  return api<Meeting>(`/meetings/${encodeURIComponent(meetingId)}/cancel`, { method: 'POST' });
}
