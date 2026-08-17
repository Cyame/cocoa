import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api } from '@/lib/api';
import { createOrganization } from '@/lib/api/organizations';
import { useSessionStore } from '@/stores/session';

const fetchMock = vi.fn();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
  useSessionStore.setState({ token: null, user: null, currentOrgId: null });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('api() header injection', () => {
  it('sends no auth headers when session is empty', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    await api('/ping');
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.has('Authorization')).toBe(false);
    expect(headers.has('X-Organization-Id')).toBe(false);
  });

  it('sends Authorization only when currentOrgId is null', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    useSessionStore.setState({ token: 'jwt-abc', currentOrgId: null });
    await api('/ping');
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer jwt-abc');
    expect(headers.has('X-Organization-Id')).toBe(false);
  });

  it('sends X-Organization-Id with the current org id alongside Authorization', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    useSessionStore.setState({ token: 'jwt-abc', currentOrgId: 'org-123' });
    await api('/ping');
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer jwt-abc');
    expect(headers.get('X-Organization-Id')).toBe('org-123');
  });

  it('keeps a caller-supplied X-Organization-Id header untouched', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));
    useSessionStore.setState({ token: null, currentOrgId: null });
    await api('/ping', { headers: { 'X-Organization-Id': 'explicit-org' } });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const headers = new Headers(init.headers);
    expect(headers.get('X-Organization-Id')).toBe('explicit-org');
  });
});

describe('api() response handling', () => {
  it('resolves undefined on 204', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api('/ping', { method: 'DELETE' })).resolves.toBeUndefined();
  });

  it('parses the JSON body on success', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: 'org-1', slug: 'acme' }));
    await expect(api('/organizations')).resolves.toEqual({ id: 'org-1', slug: 'acme' });
  });

  it('throws ApiError with status and payload on 500', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ message: 'boom' }, 500));
    await expect(api('/ping')).rejects.toMatchObject({ status: 500, payload: { message: 'boom' } });
  });
});

describe('createOrganization()', () => {
  it('returns the created org parsed from the 201 body', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        { id: 'org-new', slug: 'acme', name: 'Acme', description: null, created_at: '2026-08-03' },
        201,
      ),
    );
    const created = await createOrganization({ name: 'Acme', slug: 'acme' });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/organizations');
    expect(init.method).toBe('POST');
    expect(JSON.parse(String(init.body))).toEqual({ name: 'Acme', slug: 'acme' });
    expect(created.id).toBe('org-new');
  });

  it('throws ApiError(201) when the 201 body has no usable id', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: 'created' }, 201));
    await expect(createOrganization({ name: 'Acme', slug: 'acme' })).rejects.toMatchObject({
      status: 201,
    });
  });

  it('propagates ApiError when the create request fails', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ message: 'slug taken' }, 409));
    await expect(createOrganization({ name: 'Acme', slug: 'acme' })).rejects.toMatchObject({
      status: 409,
      payload: { message: 'slug taken' },
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe('ApiError', () => {
  it('extracts message from payload', () => {
    const error = new ApiError(400, { message: 'bad input' });
    expect(error.message).toBe('bad input');
    expect(error.name).toBe('ApiError');
  });

  it('falls back to a generic message', () => {
    const error = new ApiError(500, { detail: 'x' });
    expect(error.message).toContain('500');
  });
});
