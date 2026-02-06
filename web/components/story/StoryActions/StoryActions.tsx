'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import styles from './StoryActions.module.css';
import { Button } from '@/components/ui/Button/Button';
import {
  saveCluster,
  unsaveCluster,
  watchCluster,
  unwatchCluster,
} from '@/lib/api/user';
import { ApiError } from '@/lib/api/errors';
import type { ClusterDetail } from '@/types/api';
import { enforceStorageLimit, removeClusterOffline, saveClusterOffline } from '@/lib/offline/db';

export function StoryActions({
  clusterId,
  cluster,
  initial,
}: {
  clusterId: string;
  cluster?: ClusterDetail;
  initial: { saved: boolean; watched: boolean };
}) {
  const qc = useQueryClient();
  const [saved, setSaved] = useState(initial.saved);
  const [watched, setWatched] = useState(initial.watched);

  const redirectPath =
    typeof window !== 'undefined'
      ? `${window.location.pathname}${window.location.search}`
      : '/';
  const loginHref = `/auth/login?redirect=${encodeURIComponent(redirectPath)}`;

  const save = useMutation({
    mutationFn: async (next: boolean) => {
      if (next) return await saveCluster(clusterId);
      return await unsaveCluster(clusterId);
    },
    onSuccess: async (_data, next) => {
      qc.invalidateQueries({ queryKey: ['saves'] });
      setSaved(next);
      if (next) {
        if (cluster) {
          await saveClusterOffline(cluster);
          await enforceStorageLimit();
        }
      } else {
        await removeClusterOffline(clusterId);
      }
    },
  });

  const watch = useMutation({
    mutationFn: async (next: boolean) => {
      if (next) return await watchCluster(clusterId);
      return await unwatchCluster(clusterId);
    },
    onSuccess: (_data, next) => {
      qc.invalidateQueries({ queryKey: ['watches'] });
      setWatched(next);
    },
  });

  const needsAuth =
    (save.error instanceof ApiError && save.error.status === 401) ||
    (watch.error instanceof ApiError && watch.error.status === 401);

  return (
    <div className={styles.row}>
      <Button
        variant={saved ? 'secondary' : 'primary'}
        size="sm"
        onClick={() => save.mutate(!saved)}
        isLoading={save.isPending}
      >
        {saved ? 'Saved' : 'Save'}
      </Button>
      <Button
        variant={watched ? 'secondary' : 'tertiary'}
        size="sm"
        onClick={() => watch.mutate(!watched)}
        isLoading={watch.isPending}
      >
        {watched ? 'Watching' : 'Watch'}
      </Button>
      {needsAuth ? (
        <span className={styles.hint}>
          Login required.{' '}
          <Link className={styles.loginLink} href={loginHref}>
            Log in
          </Link>
        </span>
      ) : null}
    </div>
  );
}
