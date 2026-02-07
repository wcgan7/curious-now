'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useEffect, useState } from 'react';

import { applyFontPreference, getStoredFontPreference } from '@/lib/preferences/font';

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(() => new QueryClient());

  useEffect(() => {
    const stored = getStoredFontPreference() || 'sans';
    applyFontPreference(stored);
  }, []);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
