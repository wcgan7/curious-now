'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Download, Trash2 } from 'lucide-react';

import styles from './SavedPage.module.css';
import { AuthGuard } from '@/components/auth/AuthGuard/AuthGuard';
import { EmptySaved } from '@/components/saved/EmptySaved/EmptySaved';
import { Button } from '@/components/ui/Button/Button';
import { listSaves, unsaveCluster } from '@/lib/api/user';
import { getClusterDetailClient } from '@/lib/api/clustersClient';
import {
  enforceStorageLimit,
  isClusterAvailableOffline,
  listOfflineClusters,
  removeClusterOffline,
  saveClusterOffline,
} from '@/lib/offline/db';
import { useNetworkStatus } from '@/lib/hooks/useNetworkStatus';

export function SavedPage() {
  return (
    <AuthGuard allowOffline>
      <SavedInner />
    </AuthGuard>
  );
}

function SavedInner() {
  const qc = useQueryClient();
  const { isOnline } = useNetworkStatus();

  const offlineList = useQuery({
    queryKey: ['offline-list'],
    queryFn: listOfflineClusters,
    staleTime: 10_000,
  });

  const savesQuery = useQuery({
    queryKey: ['saves'],
    queryFn: listSaves,
    enabled: isOnline,
  });

  const offlineQuery = useQuery({
    queryKey: ['offline-available-map', savesQuery.data?.saved.map((s) => s.cluster.cluster_id).join(',') || ''],
    enabled: !!savesQuery.data?.saved.length,
    queryFn: async () => {
      const map = new Map<string, boolean>();
      for (const s of savesQuery.data!.saved) {
        map.set(s.cluster.cluster_id, await isClusterAvailableOffline(s.cluster.cluster_id));
      }
      return map;
    },
    staleTime: 15_000,
  });

  const removeMutation = useMutation({
    mutationFn: async (clusterId: string) => unsaveCluster(clusterId),
    onSuccess: async (_data, clusterId) => {
      await removeClusterOffline(clusterId);
      qc.invalidateQueries({ queryKey: ['saves'] });
      qc.invalidateQueries({ queryKey: ['offline-list'] });
      qc.invalidateQueries({ queryKey: ['offline-available-map'] });
    },
  });

  const downloadMutation = useMutation({
    mutationFn: async (clusterId: string) => {
      const result = await getClusterDetailClient(clusterId);
      if (result.kind !== 'ok') {
        throw new Error('Unable to fetch story for offline');
      }
      await saveClusterOffline(result.cluster);
      await enforceStorageLimit();
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['offline-available-map'] }),
  });

  const items = savesQuery.data?.saved || [];
  const empty = isOnline && savesQuery.isSuccess && items.length === 0;

  const offlineAvailable = useMemo(() => {
    return offlineQuery.data || new Map<string, boolean>();
  }, [offlineQuery.data]);

  return (
    <main className={styles.main}>
      <div className={styles.container}>
        <header className={styles.header}>
          <h1 className={styles.title}>Saved</h1>
          <p className={styles.subtitle}>
            Your reading list{isOnline ? '' : ' (offline mode)'}.
          </p>
        </header>

        {!isOnline ? (
          <div className={styles.offlineBox}>
            <p className={styles.hint}>
              You&apos;re offline. Showing stories you&apos;ve downloaded for offline reading.
            </p>
            {offlineList.isLoading ? (
              <p className={styles.hint}>Loading offline stories…</p>
            ) : offlineList.isError ? (
              <p className={styles.error}>Failed to read offline storage.</p>
            ) : offlineList.data && offlineList.data.length ? (
              <ul className={styles.list}>
                {offlineList.data.map((c) => (
                  <li key={c.cluster_id} className={styles.item}>
                    <div className={styles.itemMain}>
                      <Link href={`/reader?id=${encodeURIComponent(c.cluster_id)}`} className={styles.itemTitle}>
                        {c.canonical_title}
                      </Link>
                      <div className={styles.meta}>
                        <span>Available offline</span>
                      </div>
                    </div>
                    <div className={styles.actions}>
                      <Button
                        variant="tertiary"
                        size="sm"
                        onClick={async () => {
                          await removeClusterOffline(c.cluster_id);
                          qc.invalidateQueries({ queryKey: ['offline-list'] });
                        }}
                      >
                        Remove offline
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.hint}>No offline stories yet. Download some while online.</p>
            )}
          </div>
        ) : savesQuery.isLoading ? (
          <p className={styles.hint}>Loading…</p>
        ) : savesQuery.isError ? (
          <p className={styles.error}>Failed to load saved stories.</p>
        ) : empty ? (
          <EmptySaved />
        ) : (
          <ul className={styles.list}>
            {items.map((s) => {
              const cluster = s.cluster;
              const available = offlineAvailable.get(cluster.cluster_id);
              return (
                <li key={cluster.cluster_id} className={styles.item}>
                  <div className={styles.itemMain}>
                    <Link href={`/story/${cluster.cluster_id}`} className={styles.itemTitle}>
                      {cluster.canonical_title}
                    </Link>
                    <div className={styles.meta}>
                      <span>{cluster.distinct_source_count} sources</span>
                      <span aria-hidden="true">&middot;</span>
                      <span>{available ? 'Available offline' : 'Not offline yet'}</span>
                    </div>
                  </div>
                  <div className={styles.actions}>
                    <Button
                      variant="secondary"
                      size="sm"
                      leftIcon={<Download size={16} />}
                      onClick={() => downloadMutation.mutate(cluster.cluster_id)}
                      isLoading={downloadMutation.isPending && downloadMutation.variables === cluster.cluster_id}
                      disabled={!isOnline}
                      title={!isOnline ? 'Connect to download for offline' : 'Download for offline'}
                    >
                      Offline
                    </Button>
                    {available ? (
                      <Link className={styles.readerLink} href={`/reader?id=${encodeURIComponent(cluster.cluster_id)}`}>
                        Read offline
                      </Link>
                    ) : null}
                    <Button
                      variant="tertiary"
                      size="sm"
                      leftIcon={<Trash2 size={16} />}
                      onClick={() => removeMutation.mutate(cluster.cluster_id)}
                      isLoading={removeMutation.isPending && removeMutation.variables === cluster.cluster_id}
                    >
                      Remove
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </main>
  );
}
