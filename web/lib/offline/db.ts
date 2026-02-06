import { openDB, type DBSchema, type IDBPDatabase } from 'idb';

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
}

let dbPromise: Promise<IDBPDatabase<CuriousNowDB>> | null = null;

function getDB() {
  if (!dbPromise) {
    dbPromise = openDB<CuriousNowDB>('curious-now-offline', 1, {
      upgrade(db) {
        const store = db.createObjectStore('saved-clusters', { keyPath: 'cluster_id' });
        store.createIndex('by-saved', 'saved_at');
      },
    });
  }
  return dbPromise;
}

const DEFAULT_TTL_MS = 30 * 24 * 60 * 60 * 1000;
const MAX_OFFLINE_CLUSTERS = 50;

export async function saveClusterOffline(cluster: ClusterDetail): Promise<void> {
  const db = await getDB();
  await db.put('saved-clusters', {
    cluster_id: cluster.cluster_id,
    data: cluster,
    saved_at: Date.now(),
    expires_at: Date.now() + DEFAULT_TTL_MS,
  });
}

export async function removeClusterOffline(clusterId: string): Promise<void> {
  const db = await getDB();
  await db.delete('saved-clusters', clusterId);
}

export async function getClusterOffline(clusterId: string): Promise<ClusterDetail | null> {
  const db = await getDB();
  const entry = await db.get('saved-clusters', clusterId);
  if (!entry) return null;
  if (entry.expires_at < Date.now()) {
    await db.delete('saved-clusters', clusterId);
    return null;
  }
  return entry.data;
}

export async function isClusterAvailableOffline(clusterId: string): Promise<boolean> {
  const db = await getDB();
  const entry = await db.get('saved-clusters', clusterId);
  return !!entry && entry.expires_at > Date.now();
}

export async function listOfflineClusters(): Promise<
  Array<{ cluster_id: string; canonical_title: string; saved_at: number }>
> {
  const db = await getDB();
  const all = await db.getAll('saved-clusters');
  const now = Date.now();
  const valid = all.filter((e) => e.expires_at > now);
  const expired = all.filter((e) => e.expires_at <= now);
  if (expired.length) {
    const tx = db.transaction('saved-clusters', 'readwrite');
    await Promise.all(expired.map((e) => tx.store.delete(e.cluster_id)));
    await tx.done;
  }
  return valid
    .map((e) => ({ cluster_id: e.cluster_id, canonical_title: e.data.canonical_title, saved_at: e.saved_at }))
    .sort((a, b) => b.saved_at - a.saved_at);
}

export async function enforceStorageLimit(): Promise<void> {
  const db = await getDB();
  const count = await db.count('saved-clusters');
  if (count <= MAX_OFFLINE_CLUSTERS) return;

  const index = db.transaction('saved-clusters', 'readwrite').store.index('by-saved');
  const toRemove = count - MAX_OFFLINE_CLUSTERS;

  let cursor = await index.openCursor();
  let removed = 0;
  while (cursor && removed < toRemove) {
    await cursor.delete();
    removed++;
    cursor = await cursor.continue();
  }
}
