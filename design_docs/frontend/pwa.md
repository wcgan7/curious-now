# Frontend PWA Implementation — Curious Now

This document specifies the Progressive Web App (PWA) implementation, including service worker configuration, offline support, and installation experience. It builds on Stage 7 requirements from `design_docs/stage7.md`.

---

## 1) PWA Goals

### 1.1 User experience targets

1. **Installable** — Users can add to home screen on mobile and desktop
2. **Offline reading** — Saved stories accessible without network
3. **Fast loading** — App shell loads instantly on repeat visits
4. **Reliable** — Works on flaky networks

### 1.2 Technical requirements

| Requirement | Target |
|-------------|--------|
| Lighthouse PWA score | 100 |
| Offline open time | < 300ms |
| Install prompt support | iOS Safari, Android Chrome, Desktop |
| Cached saved clusters | Up to 50 |

---

## 2) Web App Manifest

### 2.1 Manifest configuration

```json
// public/manifest.json
{
  "name": "Curious Now",
  "short_name": "Curious Now",
  "description": "Science news you can understand — then go deeper",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#FBFAF7",
  "theme_color": "#1E40AF",
  "orientation": "portrait-primary",
  "scope": "/",
  "lang": "en",
  "categories": ["news", "education", "science"],
  "icons": [
    {
      "src": "/icons/icon-72x72.png",
      "sizes": "72x72",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-96x96.png",
      "sizes": "96x96",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-128x128.png",
      "sizes": "128x128",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-144x144.png",
      "sizes": "144x144",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-152x152.png",
      "sizes": "152x152",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-192x192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-384x384.png",
      "sizes": "384x384",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-512x512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-maskable-192x192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "maskable"
    },
    {
      "src": "/icons/icon-maskable-512x512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ],
  "screenshots": [
    {
      "src": "/screenshots/home-mobile.png",
      "sizes": "390x844",
      "type": "image/png",
      "form_factor": "narrow",
      "label": "Home feed on mobile"
    },
    {
      "src": "/screenshots/story-mobile.png",
      "sizes": "390x844",
      "type": "image/png",
      "form_factor": "narrow",
      "label": "Story page on mobile"
    },
    {
      "src": "/screenshots/home-desktop.png",
      "sizes": "1280x720",
      "type": "image/png",
      "form_factor": "wide",
      "label": "Home feed on desktop"
    }
  ],
  "shortcuts": [
    {
      "name": "Latest Stories",
      "short_name": "Latest",
      "url": "/",
      "icons": [{ "src": "/icons/shortcut-latest.png", "sizes": "96x96" }]
    },
    {
      "name": "Trending",
      "short_name": "Trending",
      "url": "/trending",
      "icons": [{ "src": "/icons/shortcut-trending.png", "sizes": "96x96" }]
    },
    {
      "name": "Saved Stories",
      "short_name": "Saved",
      "url": "/saved",
      "icons": [{ "src": "/icons/shortcut-saved.png", "sizes": "96x96" }]
    }
  ],
  "share_target": {
    "action": "/share-target",
    "method": "GET",
    "params": {
      "url": "url",
      "text": "text",
      "title": "title"
    }
  }
}
```

### 2.2 HTML meta tags

```html
<!-- app/layout.tsx head -->
<head>
  <meta name="application-name" content="Curious Now" />
  <meta name="apple-mobile-web-app-capable" content="yes" />
  <meta name="apple-mobile-web-app-status-bar-style" content="default" />
  <meta name="apple-mobile-web-app-title" content="Curious Now" />
  <meta name="format-detection" content="telephone=no" />
  <meta name="mobile-web-app-capable" content="yes" />
  <meta name="theme-color" content="#1E40AF" />

  <link rel="manifest" href="/manifest.json" />
  <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
  <link rel="icon" type="image/png" sizes="32x32" href="/icons/favicon-32x32.png" />
  <link rel="icon" type="image/png" sizes="16x16" href="/icons/favicon-16x16.png" />
</head>
```

---

## 3) Service Worker Configuration

### 3.1 Next-PWA setup

```javascript
// next.config.js
const withPWA = require('next-pwa')({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  skipWaiting: true,

  // Workbox configuration
  runtimeCaching: [
    // App shell - cache first
    {
      urlPattern: /^https:\/\/fonts\.(?:googleapis|gstatic)\.com\/.*/i,
      handler: 'CacheFirst',
      options: {
        cacheName: 'google-fonts',
        expiration: {
          maxEntries: 10,
          maxAgeSeconds: 365 * 24 * 60 * 60, // 1 year
        },
      },
    },

    // Static assets - cache first
    {
      urlPattern: /\.(?:js|css|woff2?)$/i,
      handler: 'CacheFirst',
      options: {
        cacheName: 'static-assets',
        expiration: {
          maxEntries: 100,
          maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
        },
      },
    },

    // Images - cache first with size limit
    {
      urlPattern: /\.(?:png|jpg|jpeg|svg|gif|webp|avif)$/i,
      handler: 'CacheFirst',
      options: {
        cacheName: 'images',
        expiration: {
          maxEntries: 200,
          maxAgeSeconds: 7 * 24 * 60 * 60, // 7 days
        },
      },
    },

    // API: Feed - network first (stale while revalidate fallback)
    {
      urlPattern: /\/v1\/feed\??.*/i,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'api-feed',
        expiration: {
          maxEntries: 20,
          maxAgeSeconds: 5 * 60, // 5 minutes
        },
        networkTimeoutSeconds: 10,
      },
    },

    // API: Cluster detail - stale while revalidate
    {
      urlPattern: /\/v1\/clusters\/[^/]+$/i,
      handler: 'StaleWhileRevalidate',
      options: {
        cacheName: 'api-clusters',
        expiration: {
          maxEntries: 100,
          maxAgeSeconds: 60 * 60, // 1 hour
        },
      },
    },

    // API: Topics - stale while revalidate
    {
      urlPattern: /\/v1\/topics/i,
      handler: 'StaleWhileRevalidate',
      options: {
        cacheName: 'api-topics',
        expiration: {
          maxEntries: 50,
          maxAgeSeconds: 60 * 60, // 1 hour
        },
      },
    },

    // API: User data - network only (sensitive)
    {
      urlPattern: /\/v1\/user/i,
      handler: 'NetworkOnly',
    },

    // API: Search - network first
    {
      urlPattern: /\/v1\/search/i,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'api-search',
        expiration: {
          maxEntries: 50,
          maxAgeSeconds: 5 * 60, // 5 minutes
        },
        networkTimeoutSeconds: 5,
      },
    },

    // Pages - network first
    {
      urlPattern: /^https:\/\/.*\/?$/i,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'pages',
        expiration: {
          maxEntries: 50,
          maxAgeSeconds: 24 * 60 * 60, // 1 day
        },
        networkTimeoutSeconds: 10,
      },
    },
  ],

  // Custom service worker additions
  additionalManifestEntries: [
    { url: '/offline', revision: null },
  ],

  fallbacks: {
    document: '/offline',
  },
});

module.exports = withPWA({
  // ... rest of Next.js config
});
```

### 3.2 Caching strategy summary

| Resource Type | Strategy | Cache Duration | Notes |
|---------------|----------|----------------|-------|
| Static assets (JS/CSS) | Cache First | 30 days | Versioned by Next.js |
| Fonts | Cache First | 1 year | Rarely change |
| Images | Cache First | 7 days | Size limited |
| API: Feed | Network First | 5 min | Fallback to cache |
| API: Clusters | Stale While Revalidate | 1 hour | Background update |
| API: Topics | Stale While Revalidate | 1 hour | Background update |
| API: User | Network Only | - | Sensitive data |
| Pages | Network First | 1 day | Fallback to cache |

---

## 4) Offline Reading Implementation

### 4.1 Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Offline Reading Flow                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   User saves cluster                                         │
│          │                                                   │
│          ▼                                                   │
│   ┌──────────────┐                                          │
│   │ API: Save    │──────────▶ Backend                       │
│   │ cluster      │                                          │
│   └──────────────┘                                          │
│          │                                                   │
│          ▼                                                   │
│   ┌──────────────┐                                          │
│   │ Fetch full   │──────────▶ Cache cluster detail          │
│   │ cluster data │              in IndexedDB                │
│   └──────────────┘                                          │
│          │                                                   │
│          ▼                                                   │
│   ┌──────────────┐                                          │
│   │ Update       │──────────▶ Mark as available offline     │
│   │ UI state     │                                          │
│   └──────────────┘                                          │
│                                                              │
│   User opens saved cluster offline                          │
│          │                                                   │
│          ▼                                                   │
│   ┌──────────────┐                                          │
│   │ Check cache  │──────────▶ Return cached data            │
│   │ (IndexedDB)  │              or show offline page        │
│   └──────────────┘                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 IndexedDB storage for saved clusters

```typescript
// lib/offline/db.ts
import { openDB, DBSchema, IDBPDatabase } from 'idb';
import type { ClusterDetail } from '@/types/api';

interface CuriousNowDB extends DBSchema {
  'saved-clusters': {
    key: string;
    value: {
      cluster_id: string;
      data: ClusterDetail;
      saved_at: number;
      expires_at: number;
    };
    indexes: { 'by-saved': number };
  };
  'saved-list': {
    key: string;
    value: {
      cluster_id: string;
      title: string;
      saved_at: number;
    };
  };
}

let dbPromise: Promise<IDBPDatabase<CuriousNowDB>> | null = null;

export function getDB() {
  if (!dbPromise) {
    dbPromise = openDB<CuriousNowDB>('curious-now-offline', 1, {
      upgrade(db) {
        // Saved clusters store
        const clusterStore = db.createObjectStore('saved-clusters', {
          keyPath: 'cluster_id',
        });
        clusterStore.createIndex('by-saved', 'saved_at');

        // Saved list (lightweight index)
        db.createObjectStore('saved-list', {
          keyPath: 'cluster_id',
        });
      },
    });
  }
  return dbPromise;
}

// Save a cluster for offline access
export async function saveClusterOffline(cluster: ClusterDetail): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(['saved-clusters', 'saved-list'], 'readwrite');

  await Promise.all([
    tx.objectStore('saved-clusters').put({
      cluster_id: cluster.cluster_id,
      data: cluster,
      saved_at: Date.now(),
      expires_at: Date.now() + 30 * 24 * 60 * 60 * 1000, // 30 days
    }),
    tx.objectStore('saved-list').put({
      cluster_id: cluster.cluster_id,
      title: cluster.canonical_title,
      saved_at: Date.now(),
    }),
    tx.done,
  ]);
}

// Remove a cluster from offline storage
export async function removeClusterOffline(clusterId: string): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(['saved-clusters', 'saved-list'], 'readwrite');

  await Promise.all([
    tx.objectStore('saved-clusters').delete(clusterId),
    tx.objectStore('saved-list').delete(clusterId),
    tx.done,
  ]);
}

// Get a cluster from offline storage
export async function getClusterOffline(
  clusterId: string
): Promise<ClusterDetail | null> {
  const db = await getDB();
  const entry = await db.get('saved-clusters', clusterId);

  if (!entry) return null;

  // Check if expired
  if (entry.expires_at < Date.now()) {
    await removeClusterOffline(clusterId);
    return null;
  }

  return entry.data;
}

// Get list of saved clusters (lightweight)
export async function getSavedListOffline(): Promise<
  Array<{ cluster_id: string; title: string; saved_at: number }>
> {
  const db = await getDB();
  return db.getAll('saved-list');
}

// Check if cluster is available offline
export async function isClusterAvailableOffline(
  clusterId: string
): Promise<boolean> {
  const db = await getDB();
  const entry = await db.get('saved-clusters', clusterId);
  return !!entry && entry.expires_at > Date.now();
}

// Cleanup expired entries
export async function cleanupExpiredOffline(): Promise<number> {
  const db = await getDB();
  const tx = db.transaction(['saved-clusters', 'saved-list'], 'readwrite');
  const store = tx.objectStore('saved-clusters');

  let cursor = await store.openCursor();
  let cleaned = 0;

  while (cursor) {
    if (cursor.value.expires_at < Date.now()) {
      await cursor.delete();
      await tx.objectStore('saved-list').delete(cursor.value.cluster_id);
      cleaned++;
    }
    cursor = await cursor.continue();
  }

  await tx.done;
  return cleaned;
}

// Enforce storage limit (50 clusters)
const MAX_OFFLINE_CLUSTERS = 50;

export async function enforceStorageLimit(): Promise<void> {
  const db = await getDB();
  const tx = db.transaction(['saved-clusters', 'saved-list'], 'readwrite');
  const store = tx.objectStore('saved-clusters');
  const index = store.index('by-saved');

  const count = await store.count();
  if (count <= MAX_OFFLINE_CLUSTERS) {
    await tx.done;
    return;
  }

  // Remove oldest entries
  const toRemove = count - MAX_OFFLINE_CLUSTERS;
  let cursor = await index.openCursor(); // Oldest first
  let removed = 0;

  while (cursor && removed < toRemove) {
    await cursor.delete();
    await tx.objectStore('saved-list').delete(cursor.value.cluster_id);
    removed++;
    cursor = await cursor.continue();
  }

  await tx.done;
}
```

### 4.3 Offline-aware hooks

```typescript
// lib/hooks/useOfflineCluster.ts
'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { getCluster } from '@/lib/api/clusters';
import {
  getClusterOffline,
  saveClusterOffline,
  removeClusterOffline,
  isClusterAvailableOffline,
  enforceStorageLimit,
} from '@/lib/offline/db';
import { queryKeys } from '@/lib/api/queryKeys';
import { useNetworkStatus } from './useNetworkStatus';
import type { ClusterDetail } from '@/types/api';

export function useOfflineCluster(clusterId: string) {
  const { isOnline } = useNetworkStatus();
  const queryClient = useQueryClient();

  // Check if available offline
  const { data: isOfflineAvailable } = useQuery({
    queryKey: ['offline-available', clusterId],
    queryFn: () => isClusterAvailableOffline(clusterId),
    staleTime: Infinity,
  });

  // Main cluster query with offline fallback
  const clusterQuery = useQuery({
    queryKey: queryKeys.clusters.detail(clusterId),
    queryFn: async () => {
      // Try network first if online
      if (isOnline) {
        try {
          return await getCluster(clusterId);
        } catch (error) {
          // Fall back to offline if network fails
          const offlineData = await getClusterOffline(clusterId);
          if (offlineData) return offlineData;
          throw error;
        }
      }

      // Offline: try local storage
      const offlineData = await getClusterOffline(clusterId);
      if (offlineData) return offlineData;

      throw new Error('This story is not available offline');
    },
    staleTime: isOnline ? 60 * 1000 : Infinity, // Never stale when offline
  });

  // Sync to offline storage when data changes
  useEffect(() => {
    if (clusterQuery.data && isOfflineAvailable) {
      saveClusterOffline(clusterQuery.data);
    }
  }, [clusterQuery.data, isOfflineAvailable]);

  // Save for offline mutation
  const saveForOffline = useMutation({
    mutationFn: async (cluster: ClusterDetail) => {
      await saveClusterOffline(cluster);
      await enforceStorageLimit();
    },
    onSuccess: () => {
      queryClient.setQueryData(['offline-available', clusterId], true);
    },
  });

  // Remove from offline mutation
  const removeFromOffline = useMutation({
    mutationFn: () => removeClusterOffline(clusterId),
    onSuccess: () => {
      queryClient.setQueryData(['offline-available', clusterId], false);
    },
  });

  return {
    cluster: clusterQuery.data,
    isLoading: clusterQuery.isLoading,
    error: clusterQuery.error,
    isOfflineAvailable: !!isOfflineAvailable,
    saveForOffline: () => clusterQuery.data && saveForOffline.mutate(clusterQuery.data),
    removeFromOffline: () => removeFromOffline.mutate(),
    isSavingOffline: saveForOffline.isPending,
  };
}
```

```typescript
// lib/hooks/useNetworkStatus.ts
'use client';

import { useState, useEffect } from 'react';

export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return { isOnline };
}
```

### 4.4 Offline indicator component

```tsx
// components/shared/OfflineIndicator/OfflineIndicator.tsx
'use client';

import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';
import styles from './OfflineIndicator.module.css';

export function OfflineIndicator() {
  const { isOnline } = useNetworkStatus();

  if (isOnline) return null;

  return (
    <div className={styles.indicator} role="status" aria-live="polite">
      <span className={styles.icon} aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M1 1l22 22M9 9a6 6 0 0 0 8.5 8.5M16.7 16.7A10 10 0 0 0 21 12c0-5.5-4.5-10-10-10-2.6 0-5 1-6.8 2.6" />
        </svg>
      </span>
      <span>You're offline. Saved stories are still available.</span>
    </div>
  );
}
```

```css
/* components/shared/OfflineIndicator/OfflineIndicator.module.css */
.indicator {
  position: fixed;
  bottom: var(--s-4);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: var(--s-2);
  padding: var(--s-3) var(--s-4);
  background-color: var(--surface-1);
  border: var(--border-1);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-2);
  font-size: 14px;
  color: var(--text-2);
  z-index: 1000;
}

.icon {
  display: flex;
  color: var(--warning);
}
```

---

## 5) Offline Page

```tsx
// app/offline/page.tsx
import Link from 'next/link';
import { Button } from '@/components/ui/Button';
import styles from './page.module.css';

export const metadata = {
  title: 'Offline | Curious Now',
};

export default function OfflinePage() {
  return (
    <main className={styles.main}>
      <div className={styles.content}>
        <div className={styles.icon}>
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path d="M1 1l22 22" />
            <path d="M16.72 11.06A10.94 10.94 0 0 1 19 12.55" />
            <path d="M5 12.55a10.94 10.94 0 0 1 5.17-2.39" />
            <path d="M10.71 5.05A16 16 0 0 1 22.58 9" />
            <path d="M1.42 9a15.91 15.91 0 0 1 4.7-2.88" />
            <path d="M8.53 16.11a6 6 0 0 1 6.95 0" />
            <line x1="12" y1="20" x2="12.01" y2="20" />
          </svg>
        </div>
        <h1 className={styles.title}>You're offline</h1>
        <p className={styles.description}>
          It looks like you've lost your internet connection. Don't worry — your saved stories are still available.
        </p>
        <div className={styles.actions}>
          <Button as={Link} href="/saved">
            View saved stories
          </Button>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            Try again
          </Button>
        </div>
      </div>
    </main>
  );
}
```

---

## 6) Install Prompt

### 6.1 Install prompt hook

```typescript
// lib/hooks/useInstallPrompt.ts
'use client';

import { useState, useEffect } from 'react';

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

export function useInstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] =
    useState<BeforeInstallPromptEvent | null>(null);
  const [isInstallable, setIsInstallable] = useState(false);
  const [isInstalled, setIsInstalled] = useState(false);

  useEffect(() => {
    // Check if already installed
    if (window.matchMedia('(display-mode: standalone)').matches) {
      setIsInstalled(true);
      return;
    }

    // Listen for install prompt
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e as BeforeInstallPromptEvent);
      setIsInstallable(true);
    };

    // Listen for successful install
    const handleAppInstalled = () => {
      setIsInstalled(true);
      setIsInstallable(false);
      setDeferredPrompt(null);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const promptInstall = async () => {
    if (!deferredPrompt) return false;

    deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;

    setDeferredPrompt(null);
    setIsInstallable(false);

    return outcome === 'accepted';
  };

  return {
    isInstallable,
    isInstalled,
    promptInstall,
  };
}
```

### 6.2 Install prompt component

```tsx
// components/shared/InstallPrompt/InstallPrompt.tsx
'use client';

import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/Button';
import { useInstallPrompt } from '@/lib/hooks/useInstallPrompt';
import { useLocalStorage } from '@/lib/hooks/useLocalStorage';
import styles from './InstallPrompt.module.css';

export function InstallPrompt() {
  const { isInstallable, promptInstall } = useInstallPrompt();
  const [isDismissed, setIsDismissed] = useLocalStorage('install-dismissed', false);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    // Show prompt after user has visited a few pages
    if (isInstallable && !isDismissed) {
      const timer = setTimeout(() => setIsVisible(true), 30000); // 30 seconds
      return () => clearTimeout(timer);
    }
  }, [isInstallable, isDismissed]);

  if (!isVisible) return null;

  const handleInstall = async () => {
    const accepted = await promptInstall();
    if (!accepted) {
      setIsDismissed(true);
    }
    setIsVisible(false);
  };

  const handleDismiss = () => {
    setIsDismissed(true);
    setIsVisible(false);
  };

  return (
    <div className={styles.prompt} role="dialog" aria-labelledby="install-title">
      <div className={styles.content}>
        <h2 id="install-title" className={styles.title}>
          Install Curious Now
        </h2>
        <p className={styles.description}>
          Add to your home screen for a faster, app-like experience with offline reading.
        </p>
        <div className={styles.actions}>
          <Button onClick={handleInstall}>Install</Button>
          <Button variant="tertiary" onClick={handleDismiss}>
            Not now
          </Button>
        </div>
      </div>
    </div>
  );
}
```

---

## 7) iOS-Specific Handling

### 7.1 iOS Safari detection

```typescript
// lib/utils/platform.ts
export function isIOS(): boolean {
  if (typeof navigator === 'undefined') return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent);
}

export function isIOSSafari(): boolean {
  if (!isIOS()) return false;
  const ua = navigator.userAgent;
  return !ua.includes('CriOS') && !ua.includes('FxiOS');
}

export function isPWAInstalled(): boolean {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(display-mode: standalone)').matches;
}
```

### 7.2 iOS install instructions

```tsx
// components/shared/IOSInstallGuide/IOSInstallGuide.tsx
'use client';

import { isIOSSafari, isPWAInstalled } from '@/lib/utils/platform';
import { useLocalStorage } from '@/lib/hooks/useLocalStorage';
import styles from './IOSInstallGuide.module.css';

export function IOSInstallGuide() {
  const [isDismissed, setIsDismissed] = useLocalStorage('ios-guide-dismissed', false);

  if (!isIOSSafari() || isPWAInstalled() || isDismissed) {
    return null;
  }

  return (
    <div className={styles.guide} role="dialog" aria-labelledby="ios-guide-title">
      <button
        className={styles.closeButton}
        onClick={() => setIsDismissed(true)}
        aria-label="Dismiss"
      >
        &times;
      </button>
      <h2 id="ios-guide-title" className={styles.title}>
        Add to Home Screen
      </h2>
      <p className={styles.description}>
        Install Curious Now for quick access and offline reading:
      </p>
      <ol className={styles.steps}>
        <li>
          Tap the Share button{' '}
          <span className={styles.icon}>
            <ShareIcon />
          </span>
        </li>
        <li>Scroll down and tap "Add to Home Screen"</li>
        <li>Tap "Add" to confirm</li>
      </ol>
    </div>
  );
}

function ShareIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8" />
      <polyline points="16 6 12 2 8 6" />
      <line x1="12" y1="2" x2="12" y2="15" />
    </svg>
  );
}
```

---

## 8) Service Worker Updates

### 8.1 Update notification

```tsx
// components/shared/UpdateNotification/UpdateNotification.tsx
'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/Button';
import styles from './UpdateNotification.module.css';

export function UpdateNotification() {
  const [showUpdate, setShowUpdate] = useState(false);
  const [registration, setRegistration] = useState<ServiceWorkerRegistration | null>(null);

  useEffect(() => {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.ready.then((reg) => {
        setRegistration(reg);

        reg.addEventListener('updatefound', () => {
          const newWorker = reg.installing;
          if (!newWorker) return;

          newWorker.addEventListener('statechange', () => {
            if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
              setShowUpdate(true);
            }
          });
        });
      });
    }
  }, []);

  const handleUpdate = () => {
    if (registration?.waiting) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' });
    }
    window.location.reload();
  };

  if (!showUpdate) return null;

  return (
    <div className={styles.notification} role="alert">
      <span>A new version is available.</span>
      <Button size="sm" onClick={handleUpdate}>
        Update
      </Button>
    </div>
  );
}
```

---

## 9) Testing PWA Features

### 9.1 Manual testing checklist

- [ ] **Manifest loads correctly** — DevTools > Application > Manifest
- [ ] **Service worker registered** — DevTools > Application > Service Workers
- [ ] **App is installable** — Install prompt appears on supported browsers
- [ ] **Offline page works** — Disable network, navigate to uncached page
- [ ] **Saved stories work offline** — Save a story, go offline, open it
- [ ] **App shell caches** — Repeat visit loads instantly
- [ ] **API caching works** — Feed loads from cache when offline
- [ ] **Update notification appears** — Deploy new version, check prompt

### 9.2 Lighthouse audit targets

| Category | Target Score |
|----------|--------------|
| PWA | 100 |
| Performance | ≥90 |
| Accessibility | 100 |
| Best Practices | 100 |
| SEO | 100 |

---

## 10) Storage Quotas

### 10.1 Quota estimation

```typescript
// lib/offline/quota.ts
export async function getStorageEstimate(): Promise<{
  used: number;
  available: number;
  percentage: number;
}> {
  if (!navigator.storage?.estimate) {
    return { used: 0, available: 0, percentage: 0 };
  }

  const estimate = await navigator.storage.estimate();
  const used = estimate.usage || 0;
  const available = estimate.quota || 0;
  const percentage = available > 0 ? (used / available) * 100 : 0;

  return { used, available, percentage };
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}
```

### 10.2 Storage warning

```tsx
// Display warning when storage is running low
function StorageWarning() {
  const [estimate, setEstimate] = useState<{ percentage: number } | null>(null);

  useEffect(() => {
    getStorageEstimate().then(setEstimate);
  }, []);

  if (!estimate || estimate.percentage < 80) return null;

  return (
    <div className={styles.warning}>
      Storage is running low ({estimate.percentage.toFixed(0)}% used).
      Consider removing some saved stories.
    </div>
  );
}
```
