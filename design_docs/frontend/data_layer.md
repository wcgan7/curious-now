# Frontend Data Layer — Curious Now

This document specifies state management, data fetching patterns, caching strategies, and API integration. It complements `design_docs/frontend/architecture.md` and connects to `design_docs/openapi.v0.yaml`.

---

## 1) Data Layer Architecture

### 1.1 Design principles

1. **Server state is king** — Most data comes from the API; treat it as the source of truth
2. **Minimal client state** — Only store UI state (modals, form inputs) in React state
3. **Cache intelligently** — Use TanStack Query for server state caching
4. **Type safety** — Generate types from OpenAPI spec
5. **Optimistic updates** — For better UX on mutations

### 1.2 State categories

| Category | Storage | Example |
|----------|---------|---------|
| Server state | TanStack Query cache | Feed data, cluster details, user prefs |
| Auth state | React Context + cookies | Current user, session status |
| UI state | React useState/useReducer | Modal open, form values |
| Persistent local | localStorage | Theme preference, dismissed banners |
| URL state | Next.js router | Search query, current tab, pagination |

---

## 2) Type Generation from OpenAPI

### 2.1 Setup

```bash
# Install type generator
npm install -D openapi-typescript

# Add script to package.json
# "generate:types": "openapi-typescript ../design_docs/openapi.v0.yaml -o types/api.generated.ts"
```

### 2.2 Generated types usage

```typescript
// types/api.ts
// Re-export and enhance generated types

import type { components, paths } from './api.generated';

// Schema types
export type ClusterCard = components['schemas']['ClusterCard'];
export type ClusterDetail = components['schemas']['ClusterDetail'];
export type Topic = components['schemas']['Topic'];
export type TopicDetail = components['schemas']['TopicDetail'];
export type EvidenceItem = components['schemas']['EvidenceItem'];
export type GlossaryEntry = components['schemas']['GlossaryEntry'];
export type User = components['schemas']['User'];
export type UserPrefs = components['schemas']['UserPrefs'];
export type ClusterUpdateEntry = components['schemas']['ClusterUpdateEntry'];

// Response types
export type FeedResponse = components['schemas']['ClustersFeedResponse'];
export type SearchResponse = components['schemas']['SearchResponse'];
export type TopicLineageResponse = components['schemas']['TopicLineageResponse'];

// Request types
export type FeedTab = 'latest' | 'trending' | 'for_you';
export type ContentType = components['schemas']['ContentType'];
export type FeedbackType = components['schemas']['FeedbackIn']['feedback_type'];
export type EventType = components['schemas']['EventIn']['event_type'];

// API path types for typed fetch
export type ApiPaths = paths;
```

---

## 3) API Client Layer

### 3.1 Base client

```typescript
// lib/api/client.ts
import { env } from '@/lib/config/env';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface FetchOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined>;
}

export async function apiClient<T>(
  endpoint: string,
  options: FetchOptions = {}
): Promise<T> {
  const { params, ...fetchOptions } = options;

  // Build URL with query params
  const url = new URL(`${env.apiUrl}${endpoint}`);
  if (params) {
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        url.searchParams.set(key, String(value));
      }
    });
  }

  // Default headers
  const headers = new Headers(fetchOptions.headers);
  if (!headers.has('Content-Type') && fetchOptions.body) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url.toString(), {
    ...fetchOptions,
    headers,
    credentials: 'include', // Include cookies for auth
  });

  // Handle redirects (301 for merged clusters/topics)
  if (response.status === 301) {
    const data = await response.json();
    throw new ApiRedirectError(data);
  }

  // Handle errors
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      error.error?.code || 'UNKNOWN_ERROR',
      error.error?.message || 'An error occurred',
      error
    );
  }

  // Handle empty responses
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export class ApiRedirectError extends Error {
  constructor(public data: { redirect_to_cluster_id?: string; redirect_to_topic_id?: string }) {
    super('Resource has been merged');
    this.name = 'ApiRedirectError';
  }
}

// Typed fetch helpers
export const api = {
  get: <T>(endpoint: string, params?: Record<string, any>) =>
    apiClient<T>(endpoint, { method: 'GET', params }),

  post: <T>(endpoint: string, body?: unknown) =>
    apiClient<T>(endpoint, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(endpoint: string, body: unknown) =>
    apiClient<T>(endpoint, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  put: <T>(endpoint: string, body: unknown) =>
    apiClient<T>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  delete: <T>(endpoint: string) =>
    apiClient<T>(endpoint, { method: 'DELETE' }),
};
```

### 3.2 Domain-specific API modules

```typescript
// lib/api/feed.ts
import { api } from './client';
import type { FeedResponse, FeedTab, ContentType } from '@/types/api';

interface GetFeedParams {
  tab?: FeedTab;
  topic_id?: string;
  content_type?: ContentType;
  page?: number;
  page_size?: number;
}

export async function getFeed(params: GetFeedParams = {}): Promise<FeedResponse> {
  return api.get<FeedResponse>('/feed', {
    tab: params.tab || 'latest',
    topic_id: params.topic_id,
    content_type: params.content_type,
    page: params.page || 1,
    page_size: params.page_size || 20,
  });
}
```

```typescript
// lib/api/clusters.ts
import { api, ApiRedirectError } from './client';
import { redirect } from 'next/navigation';
import type { ClusterDetail, ClusterUpdatesResponse } from '@/types/api';

export async function getCluster(id: string): Promise<ClusterDetail> {
  try {
    return await api.get<ClusterDetail>(`/clusters/${id}`);
  } catch (error) {
    if (error instanceof ApiRedirectError && error.data.redirect_to_cluster_id) {
      redirect(`/story/${error.data.redirect_to_cluster_id}`);
    }
    throw error;
  }
}

export async function getClusterUpdates(
  id: string,
  page = 1
): Promise<ClusterUpdatesResponse> {
  return api.get<ClusterUpdatesResponse>(`/clusters/${id}/updates`, { page });
}
```

```typescript
// lib/api/topics.ts
import { api, ApiRedirectError } from './client';
import { redirect } from 'next/navigation';
import type { TopicsResponse, TopicDetail, TopicLineageResponse } from '@/types/api';

export async function getTopics(): Promise<TopicsResponse> {
  return api.get<TopicsResponse>('/topics');
}

export async function getTopic(id: string): Promise<TopicDetail> {
  try {
    return await api.get<TopicDetail>(`/topics/${id}`);
  } catch (error) {
    if (error instanceof ApiRedirectError && error.data.redirect_to_topic_id) {
      redirect(`/topic/${error.data.redirect_to_topic_id}`);
    }
    throw error;
  }
}

export async function getTopicLineage(id: string): Promise<TopicLineageResponse> {
  return api.get<TopicLineageResponse>(`/topics/${id}/lineage`);
}
```

```typescript
// lib/api/search.ts
import { api } from './client';
import type { SearchResponse } from '@/types/api';

export async function search(query: string): Promise<SearchResponse> {
  return api.get<SearchResponse>('/search', { q: query });
}
```

```typescript
// lib/api/auth.ts
import { api } from './client';
import type { User } from '@/types/api';

export async function startMagicLink(email: string): Promise<{ status: 'sent' }> {
  return api.post('/auth/magic_link/start', { email });
}

export async function verifyMagicLink(token: string): Promise<{ user: User }> {
  return api.post('/auth/magic_link/verify', { token });
}

export async function logout(): Promise<{ status: 'ok' }> {
  return api.post('/auth/logout');
}

export async function getUser(): Promise<{ user: User }> {
  return api.get('/user');
}
```

```typescript
// lib/api/user.ts
import { api } from './client';
import type { UserPrefs, UserPrefsResponse, SavedCluster } from '@/types/api';

export async function getUserPrefs(): Promise<UserPrefsResponse> {
  return api.get('/user/prefs');
}

export async function updateUserPrefs(
  prefs: Partial<UserPrefs>
): Promise<UserPrefsResponse> {
  return api.patch('/user/prefs', prefs);
}

export async function getSavedClusters(): Promise<{ saved: SavedCluster[] }> {
  return api.get('/user/saves');
}

export async function saveCluster(
  clusterId: string,
  save = true
): Promise<{ status: 'ok' }> {
  if (save) {
    return api.post(`/user/saves/${clusterId}`);
  }
  return api.delete(`/user/saves/${clusterId}`);
}

export async function watchCluster(
  clusterId: string,
  watch = true
): Promise<{ status: 'ok' }> {
  if (watch) {
    return api.post(`/user/watches/clusters/${clusterId}`);
  }
  return api.delete(`/user/watches/clusters/${clusterId}`);
}

export async function followTopic(
  topicId: string,
  follow = true
): Promise<{ status: 'ok' }> {
  if (follow) {
    return api.post(`/user/follows/topics/${topicId}`);
  }
  return api.delete(`/user/follows/topics/${topicId}`);
}

export async function blockSource(
  sourceId: string,
  block = true
): Promise<{ status: 'ok' }> {
  if (block) {
    return api.post(`/user/blocks/sources/${sourceId}`);
  }
  return api.delete(`/user/blocks/sources/${sourceId}`);
}
```

```typescript
// lib/api/events.ts
import { api } from './client';
import type { EventType } from '@/types/api';

interface EventPayload {
  event_type: EventType;
  cluster_id?: string;
  item_id?: string;
  topic_id?: string;
  meta?: Record<string, unknown>;
}

export async function trackEvent(payload: EventPayload): Promise<void> {
  // Fire and forget - don't block UI
  api.post('/events', payload).catch(() => {
    // Silently fail for analytics
  });
}

// Convenience methods
export const track = {
  openCluster: (clusterId: string) =>
    trackEvent({ event_type: 'open_cluster', cluster_id: clusterId }),

  clickItem: (itemId: string, clusterId?: string) =>
    trackEvent({ event_type: 'click_item', item_id: itemId, cluster_id: clusterId }),

  saveCluster: (clusterId: string) =>
    trackEvent({ event_type: 'save_cluster', cluster_id: clusterId }),

  followTopic: (topicId: string) =>
    trackEvent({ event_type: 'follow_topic', topic_id: topicId }),
};
```

```typescript
// lib/api/glossary.ts
import { api } from './client';
import type { GlossaryEntry } from '@/types/api';

export async function lookupGlossary(
  term: string
): Promise<{ entry: GlossaryEntry | null }> {
  try {
    return await api.get('/glossary', { term });
  } catch {
    return { entry: null };
  }
}
```

---

## 4) TanStack Query Setup

### 4.1 Provider configuration

```typescript
// lib/providers/QueryProvider.tsx
'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { useState } from 'react';

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Data is considered fresh for 60 seconds
            staleTime: 60 * 1000,
            // Cache data for 5 minutes
            gcTime: 5 * 60 * 1000,
            // Retry failed requests 2 times
            retry: 2,
            // Don't refetch on window focus in production
            refetchOnWindowFocus: process.env.NODE_ENV === 'development',
          },
          mutations: {
            // Retry mutations once
            retry: 1,
          },
        },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {process.env.NODE_ENV === 'development' && (
        <ReactQueryDevtools initialIsOpen={false} />
      )}
    </QueryClientProvider>
  );
}
```

### 4.2 Query key factory

```typescript
// lib/api/queryKeys.ts

export const queryKeys = {
  // Feed
  feed: {
    all: ['feed'] as const,
    list: (params: { tab?: string; topicId?: string }) =>
      [...queryKeys.feed.all, params] as const,
  },

  // Clusters
  clusters: {
    all: ['clusters'] as const,
    detail: (id: string) => [...queryKeys.clusters.all, id] as const,
    updates: (id: string) => [...queryKeys.clusters.all, id, 'updates'] as const,
  },

  // Topics
  topics: {
    all: ['topics'] as const,
    list: () => [...queryKeys.topics.all, 'list'] as const,
    detail: (id: string) => [...queryKeys.topics.all, id] as const,
    lineage: (id: string) => [...queryKeys.topics.all, id, 'lineage'] as const,
  },

  // Search
  search: {
    all: ['search'] as const,
    results: (query: string) => [...queryKeys.search.all, query] as const,
  },

  // User
  user: {
    all: ['user'] as const,
    current: () => [...queryKeys.user.all, 'current'] as const,
    prefs: () => [...queryKeys.user.all, 'prefs'] as const,
    saves: () => [...queryKeys.user.all, 'saves'] as const,
    watches: () => [...queryKeys.user.all, 'watches'] as const,
  },

  // Glossary
  glossary: {
    all: ['glossary'] as const,
    term: (term: string) => [...queryKeys.glossary.all, term] as const,
  },
} as const;
```

---

## 5) Custom Hooks

### 5.1 Feed hooks

```typescript
// lib/hooks/useFeed.ts
'use client';

import { useInfiniteQuery } from '@tanstack/react-query';
import { getFeed } from '@/lib/api/feed';
import { queryKeys } from '@/lib/api/queryKeys';
import type { FeedTab, ContentType, ClusterCard } from '@/types/api';

interface UseFeedOptions {
  tab?: FeedTab;
  topicId?: string;
  contentType?: ContentType;
  initialData?: ClusterCard[];
}

export function useFeed({
  tab = 'latest',
  topicId,
  contentType,
  initialData,
}: UseFeedOptions = {}) {
  return useInfiniteQuery({
    queryKey: queryKeys.feed.list({ tab, topicId }),
    queryFn: ({ pageParam = 1 }) =>
      getFeed({
        tab,
        topic_id: topicId,
        content_type: contentType,
        page: pageParam,
      }),
    getNextPageParam: (lastPage, pages) => {
      // Assume 20 items per page; if less, no more pages
      if (lastPage.results.length < 20) return undefined;
      return pages.length + 1;
    },
    initialPageParam: 1,
    initialData: initialData
      ? {
          pages: [{ tab, page: 1, results: initialData }],
          pageParams: [1],
        }
      : undefined,
  });
}

// Flattened results helper
export function useFeedResults(options: UseFeedOptions) {
  const query = useFeed(options);

  const clusters = query.data?.pages.flatMap((page) => page.results) ?? [];

  return {
    ...query,
    clusters,
    hasMore: query.hasNextPage,
    loadMore: query.fetchNextPage,
  };
}
```

### 5.2 Cluster hooks

```typescript
// lib/hooks/useCluster.ts
'use client';

import { useQuery } from '@tanstack/react-query';
import { getCluster, getClusterUpdates } from '@/lib/api/clusters';
import { queryKeys } from '@/lib/api/queryKeys';
import type { ClusterDetail } from '@/types/api';

export function useCluster(id: string, initialData?: ClusterDetail) {
  return useQuery({
    queryKey: queryKeys.clusters.detail(id),
    queryFn: () => getCluster(id),
    initialData,
  });
}

export function useClusterUpdates(id: string) {
  return useQuery({
    queryKey: queryKeys.clusters.updates(id),
    queryFn: () => getClusterUpdates(id),
  });
}
```

### 5.3 Search hooks

```typescript
// lib/hooks/useSearch.ts
'use client';

import { useQuery } from '@tanstack/react-query';
import { useState, useDeferredValue } from 'react';
import { search } from '@/lib/api/search';
import { queryKeys } from '@/lib/api/queryKeys';

export function useSearch(initialQuery = '') {
  const [query, setQuery] = useState(initialQuery);
  const deferredQuery = useDeferredValue(query);

  const searchQuery = useQuery({
    queryKey: queryKeys.search.results(deferredQuery),
    queryFn: () => search(deferredQuery),
    enabled: deferredQuery.length >= 2,
    staleTime: 30 * 1000, // 30 seconds
  });

  return {
    query,
    setQuery,
    results: searchQuery.data,
    isLoading: searchQuery.isLoading,
    isStale: query !== deferredQuery,
  };
}
```

### 5.4 User action hooks

```typescript
// lib/hooks/useUserActions.ts
'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  saveCluster,
  watchCluster,
  followTopic,
  blockSource,
} from '@/lib/api/user';
import { queryKeys } from '@/lib/api/queryKeys';
import { useToast } from './useToast';

export function useSaveCluster() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: ({ clusterId, save }: { clusterId: string; save: boolean }) =>
      saveCluster(clusterId, save),

    onMutate: async ({ clusterId, save }) => {
      // Cancel outgoing refetches
      await queryClient.cancelQueries({
        queryKey: queryKeys.clusters.detail(clusterId),
      });

      // Snapshot previous value
      const previousCluster = queryClient.getQueryData(
        queryKeys.clusters.detail(clusterId)
      );

      // Optimistically update
      queryClient.setQueryData(
        queryKeys.clusters.detail(clusterId),
        (old: any) => (old ? { ...old, is_saved: save } : old)
      );

      return { previousCluster };
    },

    onError: (err, { clusterId }, context) => {
      // Rollback on error
      if (context?.previousCluster) {
        queryClient.setQueryData(
          queryKeys.clusters.detail(clusterId),
          context.previousCluster
        );
      }
      showToast('Failed to save', 'error');
    },

    onSuccess: (_, { save }) => {
      showToast(
        save ? 'Saved to reading list' : 'Removed from saved',
        'success'
      );
    },

    onSettled: () => {
      // Invalidate saves list
      queryClient.invalidateQueries({ queryKey: queryKeys.user.saves() });
    },
  });
}

export function useWatchCluster() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: ({ clusterId, watch }: { clusterId: string; watch: boolean }) =>
      watchCluster(clusterId, watch),

    onMutate: async ({ clusterId, watch }) => {
      await queryClient.cancelQueries({
        queryKey: queryKeys.clusters.detail(clusterId),
      });

      const previousCluster = queryClient.getQueryData(
        queryKeys.clusters.detail(clusterId)
      );

      queryClient.setQueryData(
        queryKeys.clusters.detail(clusterId),
        (old: any) => (old ? { ...old, is_watched: watch } : old)
      );

      return { previousCluster };
    },

    onError: (err, { clusterId }, context) => {
      if (context?.previousCluster) {
        queryClient.setQueryData(
          queryKeys.clusters.detail(clusterId),
          context.previousCluster
        );
      }
      showToast('Failed to update watch', 'error');
    },

    onSuccess: (_, { watch }) => {
      showToast(
        watch ? "You'll be notified of updates" : 'Stopped watching',
        'success'
      );
    },

    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.user.watches() });
    },
  });
}

export function useFollowTopic() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: ({ topicId, follow }: { topicId: string; follow: boolean }) =>
      followTopic(topicId, follow),

    onSuccess: (_, { follow }) => {
      showToast(
        follow ? 'Following topic' : 'Unfollowed topic',
        'success'
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.user.prefs() });
      queryClient.invalidateQueries({ queryKey: queryKeys.topics.all });
    },

    onError: () => {
      showToast('Failed to update', 'error');
    },
  });
}

export function useBlockSource() {
  const queryClient = useQueryClient();
  const { showToast } = useToast();

  return useMutation({
    mutationFn: ({ sourceId, block }: { sourceId: string; block: boolean }) =>
      blockSource(sourceId, block),

    onSuccess: (_, { block }) => {
      showToast(
        block ? 'Source blocked' : 'Source unblocked',
        'success'
      );
      queryClient.invalidateQueries({ queryKey: queryKeys.user.prefs() });
      queryClient.invalidateQueries({ queryKey: queryKeys.feed.all });
    },

    onError: () => {
      showToast('Failed to update', 'error');
    },
  });
}
```

### 5.5 Glossary hook

```typescript
// lib/hooks/useGlossary.ts
'use client';

import { useQuery } from '@tanstack/react-query';
import { lookupGlossary } from '@/lib/api/glossary';
import { queryKeys } from '@/lib/api/queryKeys';

export function useGlossary(term: string | null) {
  return useQuery({
    queryKey: queryKeys.glossary.term(term || ''),
    queryFn: () => lookupGlossary(term!),
    enabled: !!term && term.length >= 2,
    staleTime: 10 * 60 * 1000, // 10 minutes - glossary entries don't change often
  });
}
```

### 5.6 Auth hook

```typescript
// lib/hooks/useAuth.ts
'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { getUser, logout as logoutApi, startMagicLink, verifyMagicLink } from '@/lib/api/auth';
import { queryKeys } from '@/lib/api/queryKeys';

export function useAuth() {
  const queryClient = useQueryClient();
  const router = useRouter();

  const userQuery = useQuery({
    queryKey: queryKeys.user.current(),
    queryFn: getUser,
    retry: false,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });

  const logoutMutation = useMutation({
    mutationFn: logoutApi,
    onSuccess: () => {
      queryClient.clear();
      router.push('/');
    },
  });

  return {
    user: userQuery.data?.user ?? null,
    isLoading: userQuery.isLoading,
    isAuthenticated: !!userQuery.data?.user,
    logout: logoutMutation.mutate,
    isLoggingOut: logoutMutation.isPending,
    refetch: userQuery.refetch,
  };
}

export function useLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();

  const startMutation = useMutation({
    mutationFn: startMagicLink,
  });

  const verifyMutation = useMutation({
    mutationFn: verifyMagicLink,
    onSuccess: (data) => {
      queryClient.setQueryData(queryKeys.user.current(), { user: data.user });
      router.push('/');
    },
  });

  return {
    startLogin: startMutation.mutate,
    isStarting: startMutation.isPending,
    startError: startMutation.error,
    startSuccess: startMutation.isSuccess,

    verifyToken: verifyMutation.mutate,
    isVerifying: verifyMutation.isPending,
    verifyError: verifyMutation.error,
  };
}
```

---

## 6) Context Providers

### 6.1 Auth context

```typescript
// lib/context/AuthContext.tsx
'use client';

import { createContext, useContext } from 'react';
import { useAuth as useAuthHook } from '@/lib/hooks/useAuth';

type AuthContextType = ReturnType<typeof useAuthHook>;

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const auth = useAuthHook();

  return <AuthContext.Provider value={auth}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
```

### 6.2 Toast context

```typescript
// lib/context/ToastContext.tsx
'use client';

import { createContext, useContext, useState, useCallback } from 'react';
import { Toast } from '@/components/ui/Toast';
import styles from './ToastContext.module.css';

type ToastType = 'info' | 'success' | 'warning' | 'error';

interface ToastItem {
  id: string;
  message: string;
  type: ToastType;
}

interface ToastContextType {
  showToast: (message: string, type?: ToastType) => void;
}

const ToastContext = createContext<ToastContextType | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const showToast = useCallback((message: string, type: ToastType = 'info') => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className={styles.container} aria-live="polite">
        {toasts.map((toast) => (
          <Toast
            key={toast.id}
            message={toast.message}
            type={toast.type}
            onDismiss={() => dismissToast(toast.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return context;
}
```

### 6.3 Theme context

```typescript
// lib/context/ThemeContext.tsx
'use client';

import { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';

interface ThemeContextType {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  resolvedTheme: 'light' | 'dark';
}

const ThemeContext = createContext<ThemeContextType | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>('system');
  const [resolvedTheme, setResolvedTheme] = useState<'light' | 'dark'>('light');

  useEffect(() => {
    // Load from localStorage
    const stored = localStorage.getItem('theme') as Theme | null;
    if (stored) {
      setThemeState(stored);
    }
  }, []);

  useEffect(() => {
    // Determine resolved theme
    let resolved: 'light' | 'dark' = 'light';

    if (theme === 'system') {
      resolved = window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light';
    } else {
      resolved = theme;
    }

    setResolvedTheme(resolved);

    // Apply to document
    document.documentElement.classList.remove('theme-light', 'theme-dark');
    document.documentElement.classList.add(`theme-${resolved}`);
  }, [theme]);

  useEffect(() => {
    // Listen for system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');

    const handleChange = () => {
      if (theme === 'system') {
        setResolvedTheme(mediaQuery.matches ? 'dark' : 'light');
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  const setTheme = (newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem('theme', newTheme);
  };

  return (
    <ThemeContext.Provider value={{ theme, setTheme, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within ThemeProvider');
  }
  return context;
}
```

---

## 7) Local Storage Utilities

```typescript
// lib/hooks/useLocalStorage.ts
'use client';

import { useState, useEffect, useCallback } from 'react';

export function useLocalStorage<T>(
  key: string,
  initialValue: T
): [T, (value: T | ((prev: T) => T)) => void] {
  // State to store our value
  const [storedValue, setStoredValue] = useState<T>(initialValue);

  // Load from localStorage on mount
  useEffect(() => {
    try {
      const item = window.localStorage.getItem(key);
      if (item) {
        setStoredValue(JSON.parse(item));
      }
    } catch (error) {
      console.warn(`Error reading localStorage key "${key}":`, error);
    }
  }, [key]);

  // Return a wrapped version of useState's setter function
  const setValue = useCallback(
    (value: T | ((prev: T) => T)) => {
      try {
        // Allow value to be a function
        const valueToStore =
          value instanceof Function ? value(storedValue) : value;

        setStoredValue(valueToStore);
        window.localStorage.setItem(key, JSON.stringify(valueToStore));
      } catch (error) {
        console.warn(`Error setting localStorage key "${key}":`, error);
      }
    },
    [key, storedValue]
  );

  return [storedValue, setValue];
}
```

---

## 8) Prefetching Strategies

### 8.1 Link prefetching

```typescript
// components/shared/PrefetchLink.tsx
'use client';

import Link from 'next/link';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/api/queryKeys';
import { getCluster } from '@/lib/api/clusters';
import { getTopic } from '@/lib/api/topics';

interface PrefetchLinkProps extends React.ComponentProps<typeof Link> {
  prefetchType?: 'cluster' | 'topic';
  prefetchId?: string;
}

export function PrefetchLink({
  prefetchType,
  prefetchId,
  onMouseEnter,
  ...props
}: PrefetchLinkProps) {
  const queryClient = useQueryClient();

  const handleMouseEnter = (e: React.MouseEvent<HTMLAnchorElement>) => {
    // Prefetch data on hover
    if (prefetchType === 'cluster' && prefetchId) {
      queryClient.prefetchQuery({
        queryKey: queryKeys.clusters.detail(prefetchId),
        queryFn: () => getCluster(prefetchId),
        staleTime: 60 * 1000,
      });
    } else if (prefetchType === 'topic' && prefetchId) {
      queryClient.prefetchQuery({
        queryKey: queryKeys.topics.detail(prefetchId),
        queryFn: () => getTopic(prefetchId),
        staleTime: 60 * 1000,
      });
    }

    onMouseEnter?.(e);
  };

  return <Link {...props} onMouseEnter={handleMouseEnter} />;
}
```

### 8.2 Route-based prefetching

```typescript
// app/page.tsx (example)
import { HydrationBoundary, dehydrate } from '@tanstack/react-query';
import { getQueryClient } from '@/lib/providers/getQueryClient';
import { getFeed } from '@/lib/api/feed';
import { queryKeys } from '@/lib/api/queryKeys';
import { FeedPageClient } from './FeedPageClient';

export default async function HomePage() {
  const queryClient = getQueryClient();

  // Prefetch initial data
  await queryClient.prefetchQuery({
    queryKey: queryKeys.feed.list({ tab: 'latest' }),
    queryFn: () => getFeed({ tab: 'latest', page: 1 }),
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <FeedPageClient />
    </HydrationBoundary>
  );
}
```

---

## 9) Error Handling

### 9.1 Error boundary integration

```typescript
// components/shared/QueryErrorBoundary.tsx
'use client';

import { QueryErrorResetBoundary } from '@tanstack/react-query';
import { ErrorBoundary } from 'react-error-boundary';
import { Button } from '@/components/ui/Button';
import styles from './QueryErrorBoundary.module.css';

interface QueryErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}

export function QueryErrorBoundary({
  children,
  fallback,
}: QueryErrorBoundaryProps) {
  return (
    <QueryErrorResetBoundary>
      {({ reset }) => (
        <ErrorBoundary
          onReset={reset}
          fallbackRender={({ error, resetErrorBoundary }) =>
            fallback || (
              <div className={styles.error}>
                <h2>Something went wrong</h2>
                <p>{error.message}</p>
                <Button onClick={resetErrorBoundary}>Try again</Button>
              </div>
            )
          }
        >
          {children}
        </ErrorBoundary>
      )}
    </QueryErrorResetBoundary>
  );
}
```

### 9.2 API error handling in hooks

```typescript
// lib/hooks/useApiError.ts
'use client';

import { useEffect } from 'react';
import { useToast } from './useToast';
import { ApiError } from '@/lib/api/client';

export function useApiError(error: Error | null) {
  const { showToast } = useToast();

  useEffect(() => {
    if (!error) return;

    if (error instanceof ApiError) {
      switch (error.status) {
        case 401:
          showToast('Please sign in to continue', 'warning');
          break;
        case 403:
          showToast('You do not have permission', 'error');
          break;
        case 404:
          showToast('Not found', 'error');
          break;
        case 429:
          showToast('Too many requests. Please slow down.', 'warning');
          break;
        default:
          showToast(error.message || 'Something went wrong', 'error');
      }
    } else {
      showToast('Network error. Please check your connection.', 'error');
    }
  }, [error, showToast]);
}
```

---

## 10) Performance Optimizations

### 10.1 Query deduplication

TanStack Query automatically deduplicates identical queries. No additional config needed.

### 10.2 Selective cache updates

```typescript
// Example: Update feed cache when saving a cluster
const queryClient = useQueryClient();

// Update specific cluster in all feeds
queryClient.setQueriesData(
  { queryKey: queryKeys.feed.all },
  (oldData: FeedResponse | undefined) => {
    if (!oldData) return oldData;
    return {
      ...oldData,
      results: oldData.results.map((cluster) =>
        cluster.cluster_id === clusterId
          ? { ...cluster, is_saved: true }
          : cluster
      ),
    };
  }
);
```

### 10.3 Background refetching

```typescript
// Refetch stale data when user returns to tab
const { data } = useQuery({
  queryKey: queryKeys.feed.list({ tab: 'latest' }),
  queryFn: () => getFeed({ tab: 'latest' }),
  refetchOnWindowFocus: true,
  refetchInterval: 5 * 60 * 1000, // Every 5 minutes
});
```

---

## 11) Caching Strategy Summary

| Data Type | Stale Time | GC Time | Refetch Strategy |
|-----------|------------|---------|------------------|
| Feed data | 60s | 5min | On window focus, on navigation |
| Cluster detail | 60s | 5min | On navigation |
| Topic list | 5min | 10min | Manual invalidation |
| Search results | 30s | 2min | On query change |
| User data | 5min | 10min | On auth state change |
| Glossary | 10min | 30min | Rarely changes |

---

## 12) Data Flow Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        Data Flow                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   Server    │     │  TanStack   │     │   React     │       │
│  │  Component  │────▶│   Query     │────▶│ Components  │       │
│  │   (SSR)     │     │   Cache     │     │             │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│        │                    │                   │                │
│        │                    │                   │                │
│        ▼                    ▼                   ▼                │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │   API       │     │  Optimistic │     │    UI       │       │
│  │  Client     │◀────│   Updates   │◀────│   State     │       │
│  │             │     │             │     │             │       │
│  └─────────────┘     └─────────────┘     └─────────────┘       │
│        │                                                         │
│        ▼                                                         │
│  ┌─────────────┐                                                │
│  │  Backend    │                                                │
│  │   API       │                                                │
│  └─────────────┘                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```
