'use client';

import { useEffect, useRef, useState } from 'react';

const OFFLINE_RECHECK_MS = 15_000;
const PROBE_TIMEOUT_MS = 3_000;

async function probeConnectivity(): Promise<boolean> {
  if (typeof window === 'undefined') return true;

  // Try two same-origin resources to avoid false negatives from one blocked path.
  const probePaths = ['/manifest.json', '/'];

  for (const path of probePaths) {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timeoutId = controller
      ? window.setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS)
      : null;

    try {
      const probeUrl = new URL(path, window.location.origin);
      probeUrl.searchParams.set('_', String(Date.now()));
      const res = await fetch(probeUrl, {
        method: 'GET',
        cache: 'no-store',
        credentials: 'same-origin',
        signal: controller?.signal,
      });
      if (res.status < 500) return true;
    } catch {
      // Try next probe path.
    } finally {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    }
  }

  return false;
}

export function useNetworkStatus() {
  // Start optimistic — only show the banner after a probe confirms we're offline.
  const [isOnline, setIsOnline] = useState(true);
  const isOnlineRef = useRef(true);

  useEffect(() => {
    isOnlineRef.current = isOnline;
  }, [isOnline]);

  useEffect(() => {
    let disposed = false;
    const setOnlineSafe = (value: boolean) => {
      if (!disposed) setIsOnline(value);
    };

    const probe = async () => {
      const reachable = await probeConnectivity();
      setOnlineSafe(reachable);
    };

    function handleOnline() {
      setOnlineSafe(true);
    }
    function handleOffline() {
      // Don't trust the event — probe to verify actual connectivity.
      void probe();
    }

    // Don't probe on mount — we're optimistic and the page just loaded successfully.
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    const intervalId = window.setInterval(() => {
      if (!isOnlineRef.current) void probe();
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
