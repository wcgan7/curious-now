import { apiFetch } from '@/lib/api/client';
import type {
  AuthMagicLinkStartResponse,
  AuthMagicLinkVerifyResponse,
  LogoutResponse,
  SimpleOkResponse,
  UserPrefs,
  UserPrefsPatchRequest,
  UserPrefsResponse,
  UserResponse,
  UserSavesResponse,
  UserWatchesResponse,
} from '@/types/api';

export async function getMe(): Promise<UserResponse> {
  const { data } = await apiFetch<UserResponse>('/user', { method: 'GET' });
  return data;
}

export async function getUserPrefs(): Promise<UserPrefsResponse> {
  const { data } = await apiFetch<UserPrefsResponse>('/user/prefs', { method: 'GET' });
  return data;
}

export async function patchUserPrefs(patch: UserPrefsPatchRequest): Promise<UserPrefsResponse> {
  const { data } = await apiFetch<UserPrefsResponse>('/user/prefs', {
    method: 'PATCH',
    body: JSON.stringify(patch),
    headers: { 'Content-Type': 'application/json' },
  });
  return data;
}

export async function startMagicLink(email: string): Promise<AuthMagicLinkStartResponse> {
  const { data } = await apiFetch<AuthMagicLinkStartResponse>('/auth/magic_link/start', {
    method: 'POST',
    body: JSON.stringify({ email }),
    headers: { 'Content-Type': 'application/json' },
  });
  return data;
}

export async function verifyMagicLink(token: string): Promise<AuthMagicLinkVerifyResponse> {
  const { data } = await apiFetch<AuthMagicLinkVerifyResponse>('/auth/magic_link/verify', {
    method: 'POST',
    body: JSON.stringify({ token }),
    headers: { 'Content-Type': 'application/json' },
  });
  return data;
}

export async function logout(): Promise<LogoutResponse> {
  const { data } = await apiFetch<LogoutResponse>('/auth/logout', { method: 'POST' });
  return data;
}

export async function listSaves(): Promise<UserSavesResponse> {
  const { data } = await apiFetch<UserSavesResponse>('/user/saves', { method: 'GET' });
  return data;
}

export async function saveCluster(clusterId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/saves/${clusterId}`, {
    method: 'POST',
  });
  return data;
}

export async function unsaveCluster(clusterId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/saves/${clusterId}`, {
    method: 'DELETE',
  });
  return data;
}

export async function listWatches(): Promise<UserWatchesResponse> {
  const { data } = await apiFetch<UserWatchesResponse>('/user/watches/clusters', { method: 'GET' });
  return data;
}

export async function watchCluster(clusterId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/watches/clusters/${clusterId}`, {
    method: 'POST',
  });
  return data;
}

export async function unwatchCluster(clusterId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/watches/clusters/${clusterId}`, {
    method: 'DELETE',
  });
  return data;
}

export async function followTopic(topicId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/follows/topics/${topicId}`, {
    method: 'POST',
  });
  return data;
}

export async function unfollowTopic(topicId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/follows/topics/${topicId}`, {
    method: 'DELETE',
  });
  return data;
}

export async function blockSource(sourceId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/blocks/sources/${sourceId}`, {
    method: 'POST',
  });
  return data;
}

export async function unblockSource(sourceId: string): Promise<SimpleOkResponse> {
  const { data } = await apiFetch<SimpleOkResponse>(`/user/blocks/sources/${sourceId}`, {
    method: 'DELETE',
  });
  return data;
}

export function pickPrefs(data: UserPrefsResponse): UserPrefs {
  return data.prefs;
}
