import { env } from '@/lib/config/env';
import { ApiError } from '@/lib/api/errors';

type QueryParams = Record<string, string | number | boolean | undefined | null>;

function buildUrl(endpoint: string, params?: QueryParams) {
  const url = new URL(`${env.apiUrl}${endpoint}`);
  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url;
}

async function parseJsonSafe(res: Response): Promise<unknown | undefined> {
  const ct = res.headers.get('content-type') || '';
  if (!ct.includes('application/json')) return undefined;
  try {
    return await res.json();
  } catch {
    return undefined;
  }
}

export async function apiFetch<T>(
  endpoint: string,
  options: RequestInit & { params?: QueryParams } = {}
): Promise<{ res: Response; data: T }> {
  const { params, ...init } = options;
  const url = buildUrl(endpoint, params);

  const res = await fetch(url, {
    ...init,
    headers: {
      ...(init.headers || {}),
      Accept: 'application/json',
    },
    credentials: 'include',
    cache: 'no-store',
  });

  if (!res.ok) {
    const body = await parseJsonSafe(res);
    const message =
      typeof body === 'object' && body && 'detail' in body
        ? String((body as any).detail)
        : `Request failed: ${res.status}`;
    throw new ApiError(res.status, 'http_error', message, body);
  }

  const data = (await res.json()) as T;
  return { res, data };
}
