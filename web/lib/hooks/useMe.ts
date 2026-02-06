'use client';

import { useQuery } from '@tanstack/react-query';

import { ApiError } from '@/lib/api/errors';
import { getMe } from '@/lib/api/user';
import type { UserResponse } from '@/types/api';

export function useMe() {
  return useQuery<UserResponse | null, Error>({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await getMe();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null;
        throw err as Error;
      }
    },
    staleTime: 30_000,
  });
}

