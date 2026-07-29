import { useSessionStore } from '@/stores/session';

const API_BASE_URL = (import.meta.env.VITE_API_BASE ?? '/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, payload: unknown) {
    const message =
      typeof payload === 'object' &&
      payload !== null &&
      'message' in payload &&
      typeof payload.message === 'string'
        ? payload.message
        : `API request failed with status ${status}`;

    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.payload = payload;
  }
}

export function api(path: string, init?: RequestInit): Promise<void>;
export function api<T>(path: string, init?: RequestInit): Promise<T>;
export async function api(path: string, init?: RequestInit): Promise<unknown> {
  const token = useSessionStore.getState().token;
  const headers = new Headers(init?.headers);

  headers.set('Accept', 'application/json');
  if (typeof init?.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (token !== null) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const response = await fetch(`${API_BASE_URL}${normalizedPath}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const responseText = await response.text();
    let payload: unknown = responseText.length > 0 ? responseText : null;

    if (responseText.length > 0) {
      try {
        payload = JSON.parse(responseText);
      } catch (error) {
        if (!(error instanceof SyntaxError)) {
          throw error;
        }
      }
    }

    if (response.status === 401) {
      useSessionStore.getState().clearToken();
      if (window.location.pathname !== '/login') {
        window.location.assign('/login');
      }
    }

    if (response.status === 403) {
      const details =
        typeof payload === 'object' && payload !== null ? (payload as Record<string, unknown>) : {};
      const missing =
        typeof details.missing === 'string'
          ? details.missing
          : Array.isArray(details.missing)
            ? details.missing.join(',')
            : '';
      const gene = typeof details.gene === 'string' ? details.gene : '';
      const from = encodeURIComponent(window.location.pathname + window.location.search);
      const params = new URLSearchParams();
      if (missing.length > 0) params.set('missing', missing);
      if (gene.length > 0) params.set('gene', gene);
      params.set('from', from);
      if (window.location.pathname !== '/403') {
        window.location.assign(`/403?${params.toString()}`);
      }
    }

    throw new ApiError(response.status, payload);
  }

  if (response.status === 204) {
    return undefined;
  }

  return response.json();
}
