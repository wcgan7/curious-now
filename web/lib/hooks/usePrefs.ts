'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/errors';
import { getUserPrefs, patchUserPrefs } from '@/lib/api/user';
import type { UserPrefsPatchRequest, UserPrefsResponse } from '@/types/api';

export function usePrefs() {
  return useQuery<UserPrefsResponse | null, Error>({
    queryKey: ['prefs'],
    queryFn: async () => {
      try {
        return await getUserPrefs();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err as Error;
      }
    },
  });
}

export function usePatchPrefs() {
  const qc = useQueryClient();
  return useMutation<UserPrefsResponse, Error, UserPrefsPatchRequest>({
    mutationFn: patchUserPrefs,
    onSuccess: (data) => {
      qc.setQueryData(['prefs'], data);
    },
  });
}

