/**
 * Fetch-based SSE reader for Composer turn streams (auth header friendly).
 */

const API_BASE_URL = (import.meta.env.VITE_API_BASE ?? '/api/v1').replace(/\/$/, '');

export type ComposerStreamFrame = {
  readonly type?: string;
  readonly turn_id?: string;
  readonly instance_id?: string;
  readonly target_entity?: string;
  readonly token?: string;
  readonly status?: string;
  readonly message?: string;
  readonly finish_reason?: string;
};

export async function streamComposerTurn(
  workspaceId: string,
  turnId: string,
  token: string | null,
  onFrame: (frame: ComposerStreamFrame) => void,
  signal?: AbortSignal,
): Promise<void> {
  const url = `${API_BASE_URL}/workspaces/${encodeURIComponent(workspaceId)}/composer/stream?turn_id=${encodeURIComponent(turnId)}`;
  const headers: HeadersInit = { Accept: 'text/event-stream' };
  if (token !== null) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(url, { headers, signal });
  if (!response.ok || response.body === null) {
    throw new Error(`composer stream failed: ${response.status}`);
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
        const frame = JSON.parse(data) as ComposerStreamFrame;
        onFrame(frame);
        // Only terminate on Tunnel-shaped terminal frames — not on status/ping
        // (late subscribe used to send status:completed and abort before tokens).
        if (frame.type === 'chat.response.done' || frame.type === 'chat.response.error') {
          return;
        }
      } catch {
        // ignore malformed SSE data
      }
    }
  }
}
