export const env = {
  apiUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1',
  appUrl: process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000',
  features: {
    forYou: (process.env.NEXT_PUBLIC_ENABLE_FOR_YOU || 'true') === 'true',
    entities: (process.env.NEXT_PUBLIC_ENABLE_ENTITIES || 'false') === 'true',
    lineage: (process.env.NEXT_PUBLIC_ENABLE_LINEAGE || 'true') === 'true',
  },
  pwa: {
    enabled: (process.env.NEXT_PUBLIC_PWA_ENABLED || 'true') === 'true',
  },
} as const;

