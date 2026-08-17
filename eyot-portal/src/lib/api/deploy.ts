/**
 * Deploy progress SSE + cancel helpers.
 */

import { api } from '@/lib/api';

const API_BASE_URL = (import.meta.env.VITE_API_BASE ?? '/api/v1').replace(/\/$/, '');

export type DeploySnapshot = {
  readonly id: string;
  readonly instance_id: string;
  readonly revision: number;
  readonly action: string;
  readonly status: string;
  readonly image_version: string | null;
  readonly started_at: string | null;
  readonly finished_at: string | null;
  readonly message: string | null;
};

export type DeployProgressFrame = {
  readonly record_id?: string;
  readonly instance_id?: string;
  readonly step?: number;
  readonly status?: string;
  readonly message?: string;
};

export function fetchDeploySnapshot(recordId: string): Promise<DeploySnapshot> {
  return api<DeploySnapshot>(`/deploy/deploy-progress/${encodeURIComponent(recordId)}/snapshot`);
}

export function cancelDeploy(recordId: string): Promise<{ status: string }> {
  return api<{ status: string }>(`/deploy/deploy-cancel/${encodeURIComponent(recordId)}`, {
    method: 'POST',
  });
}

export async function streamDeployProgress(
  recordId: string,
  token: string | null,
  onFrame: (frame: DeployProgressFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${API_BASE_URL}/deploy/deploy-progress/${encodeURIComponent(recordId)}`;
  const headers: HeadersInit = { Accept: 'text/event-stream' };
  if (token !== null) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(url, { headers, signal });
  if (!response.ok || response.body === null) {
    throw new Error(`deploy stream failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const block of parts) {
      const lines = block.split('\n');
      let data = '';
      for (const line of lines) {
        if (line.startsWith('data:')) {
          data += line.slice(5).trimStart();
        }
      }
      if (data.length === 0) continue;
      try {
        const frame = JSON.parse(data) as DeployProgressFrame;
        onFrame(frame);
        if (frame.status === 'failed' || (frame.step === 9 && frame.status === 'done')) {
          return;
        }
      } catch {
        // ignore malformed SSE
      }
    }
  }
}
