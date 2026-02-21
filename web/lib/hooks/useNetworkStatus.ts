'use client';

import { useEffect, useState } from 'react';

const OFFLINE_RECHECK_MS = 15_000;
const PROBE_TIMEOUT_MS = 3_000;

async function probeConnectivity(): Promise<boolean> {
  if (typeof window === 'undefined') return true;

  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);

  try {
    const probeUrl = new URL('/manifest.json', window.location.origin);
    probeUrl.searchParams.set('_', String(Date.now()));
    await fetch(probeUrl, {
      method: 'HEAD',
      cache: 'no-store',
      signal: controller.signal,
    });
    return true;
  } catch {
    return false;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

export function useNetworkStatus() {
  const [isOnline, setIsOnline] = useState(() =>
    typeof navigator !== 'undefined' ? navigator.onLine : true
  );

  useEffect(() => {
    let disposed = false;
    const setOnlineSafe = (value: boolean) => {
      if (!disposed) setIsOnline(value);
    };

    const reconcile = async () => {
      if (typeof navigator === 'undefined') return;
      if (navigator.onLine) {
        setOnlineSafe(true);
        return;
      }
      const reachable = await probeConnectivity();
      setOnlineSafe(reachable);
    };

    function handleOnline() {
      setOnlineSafe(true);
    }
    function handleOffline() {
      // Validate connectivity because navigator.onLine can report false positives.
      void reconcile();
    }

    void reconcile();
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    const intervalId = window.setInterval(() => {
      if (!navigator.onLine) {
        void reconcile();
      }
    }, OFFLINE_RECHECK_MS);

    return () => {
      disposed = true;
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
      window.clearInterval(intervalId);
    };
  }, []);

  return { isOnline };
}
