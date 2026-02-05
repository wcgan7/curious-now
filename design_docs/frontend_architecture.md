# Frontend Architecture — Curious Now

This document specifies the frontend architecture, framework choices, project structure, and development patterns. It complements the UI design system in `design_docs/stage3.md` and connects to the API contract in `design_docs/openapi.v0.yaml`.

---

## 1) Framework Decision: Next.js 14+ (App Router)

### 1.1 Choice rationale

| Requirement | Next.js Solution |
|-------------|------------------|
| SEO for public pages (feed, clusters, topics) | Server-side rendering (SSR) + static generation |
| Fast initial load | React Server Components (RSC) reduce client JS |
| PWA support (Stage 7) | `next-pwa` plugin with Workbox |
| API integration | Server Actions + fetch with caching |
| TypeScript | First-class support |
| Image optimization | `next/image` with automatic optimization |
| Incremental adoption | File-based routing, easy migration path |

### 1.2 Version requirements

```json
{
  "next": "^14.2.0",
  "react": "^18.3.0",
  "react-dom": "^18.3.0",
  "typescript": "^5.4.0"
}
```

### 1.3 Key architectural decisions (locked)

1. **App Router** (not Pages Router) — enables RSC, layouts, streaming
2. **Server Components by default** — client components only where interactivity required
3. **No Redux** — use React Context + server state (TanStack Query) instead
4. **CSS Modules + CSS Variables** — matches design tokens, no runtime CSS-in-JS
5. **Strict TypeScript** — `strict: true`, no `any` types in production code

---

## 2) Project Structure

```
web/
├── app/                          # Next.js App Router
│   ├── layout.tsx               # Root layout (fonts, providers, header/footer)
│   ├── page.tsx                 # Home page (/ → feed with latest tab)
│   ├── globals.css              # CSS variables from design tokens
│   ├── error.tsx                # Global error boundary
│   ├── not-found.tsx            # 404 page
│   ├── loading.tsx              # Global loading skeleton
│   │
│   ├── (feed)/                  # Route group for feed pages
│   │   ├── page.tsx             # /feed redirects to /
│   │   ├── latest/page.tsx      # /latest (tab=latest)
│   │   ├── trending/page.tsx    # /trending (tab=trending)
│   │   └── for-you/page.tsx     # /for-you (tab=for_you, auth required)
│   │
│   ├── story/
│   │   └── [id]/
│   │       ├── page.tsx         # /story/{cluster_id} — StoryCluster page
│   │       ├── loading.tsx      # Skeleton for story page
│   │       └── updates/
│   │           └── page.tsx     # /story/{id}/updates — update log
│   │
│   ├── topic/
│   │   └── [id]/
│   │       ├── page.tsx         # /topic/{topic_id} — Topic page
│   │       ├── loading.tsx
│   │       └── lineage/
│   │           └── page.tsx     # /topic/{id}/lineage — lineage graph
│   │
│   ├── entity/
│   │   └── [id]/
│   │       └── page.tsx         # /entity/{entity_id} — Entity page (Stage 10)
│   │
│   ├── search/
│   │   └── page.tsx             # /search?q=...
│   │
│   ├── saved/
│   │   └── page.tsx             # /saved — reading list (auth required)
│   │
│   ├── settings/
│   │   ├── page.tsx             # /settings — user preferences
│   │   ├── topics/page.tsx      # /settings/topics — followed topics
│   │   ├── sources/page.tsx     # /settings/sources — blocked sources
│   │   └── notifications/page.tsx # /settings/notifications
│   │
│   ├── auth/
│   │   ├── login/page.tsx       # /auth/login — magic link request
│   │   ├── verify/page.tsx      # /auth/verify?token=... — verify magic link
│   │   └── logout/page.tsx      # /auth/logout
│   │
│   └── api/                     # API routes (BFF pattern for sensitive ops)
│       └── auth/
│           └── [...nextauth]/route.ts  # Optional: if using NextAuth adapter
│
├── components/
│   ├── ui/                      # Base UI components (design system)
│   │   ├── Button/
│   │   │   ├── Button.tsx
│   │   │   ├── Button.module.css
│   │   │   └── index.ts
│   │   ├── Input/
│   │   ├── Card/
│   │   ├── Badge/
│   │   ├── Chip/
│   │   ├── Modal/
│   │   ├── Toast/
│   │   ├── Tooltip/
│   │   ├── Skeleton/
│   │   └── index.ts             # Barrel export
│   │
│   ├── layout/                  # Layout components
│   │   ├── Header/
│   │   ├── Footer/
│   │   ├── MobileNav/
│   │   ├── SearchModal/
│   │   └── PageContainer/
│   │
│   ├── feed/                    # Feed-specific components
│   │   ├── ClusterCard/
│   │   │   ├── ClusterCard.tsx
│   │   │   ├── ClusterCard.module.css
│   │   │   ├── ClusterCardSkeleton.tsx
│   │   │   └── index.ts
│   │   ├── FeaturedHeroCard/
│   │   ├── CompactRowCard/
│   │   ├── FeedTabs/
│   │   ├── FeedFilters/
│   │   └── LoadMoreButton/
│   │
│   ├── story/                   # StoryCluster page components
│   │   ├── TakeawayModule/
│   │   ├── IntuitionSection/
│   │   ├── DeepDiveSection/
│   │   ├── EvidencePanel/
│   │   ├── TrustBox/
│   │   ├── ConfidenceBand/
│   │   ├── AntiHypeFlags/
│   │   ├── MethodBadges/
│   │   ├── GlossaryTooltip/
│   │   ├── UpdateLog/
│   │   ├── StoryActions/        # Save, Watch, Share buttons
│   │   └── RelatedStories/
│   │
│   ├── topic/                   # Topic page components
│   │   ├── TopicHeader/
│   │   ├── TopicClusters/
│   │   ├── LineageGraph/
│   │   └── FollowButton/
│   │
│   ├── search/                  # Search components
│   │   ├── SearchInput/
│   │   ├── SearchResults/
│   │   └── SearchSuggestions/
│   │
│   ├── auth/                    # Auth components
│   │   ├── LoginForm/
│   │   ├── MagicLinkSent/
│   │   └── AuthGuard/
│   │
│   └── shared/                  # Cross-cutting components
│       ├── ReadingProgress/
│       ├── NewsletterCTA/
│       ├── FeedbackButton/
│       └── ErrorBoundary/
│
├── lib/
│   ├── api/                     # API client layer
│   │   ├── client.ts            # Base fetch wrapper with error handling
│   │   ├── types.ts             # TypeScript types (generated from OpenAPI)
│   │   ├── feed.ts              # Feed API functions
│   │   ├── clusters.ts          # Cluster API functions
│   │   ├── topics.ts            # Topic API functions
│   │   ├── search.ts            # Search API functions
│   │   ├── auth.ts              # Auth API functions
│   │   ├── user.ts              # User prefs/actions API functions
│   │   └── events.ts            # Engagement events API
│   │
│   ├── hooks/                   # Custom React hooks
│   │   ├── useAuth.ts           # Auth state hook
│   │   ├── useFeed.ts           # Feed data hook (TanStack Query)
│   │   ├── useCluster.ts        # Cluster data hook
│   │   ├── useSearch.ts         # Search hook with debounce
│   │   ├── useGlossary.ts       # Glossary lookup hook
│   │   ├── useMediaQuery.ts     # Responsive breakpoints
│   │   ├── useLocalStorage.ts   # Persistent local state
│   │   ├── useToast.ts          # Toast notifications
│   │   └── useOffline.ts        # Offline detection
│   │
│   ├── context/                 # React Context providers
│   │   ├── AuthContext.tsx      # Auth state provider
│   │   ├── ThemeContext.tsx     # Light/dark theme
│   │   ├── ToastContext.tsx     # Toast notifications
│   │   └── OfflineContext.tsx   # Offline state
│   │
│   ├── utils/                   # Utility functions
│   │   ├── formatters.ts        # Date, number formatters
│   │   ├── validators.ts        # Input validation
│   │   ├── cn.ts                # className merge utility
│   │   └── constants.ts         # App constants
│   │
│   └── config/                  # Configuration
│       ├── env.ts               # Environment variables (typed)
│       ├── routes.ts            # Route constants
│       └── seo.ts               # SEO defaults
│
├── public/
│   ├── manifest.json            # PWA manifest
│   ├── sw.js                    # Service worker (generated)
│   ├── icons/                   # PWA icons (multiple sizes)
│   ├── fonts/                   # Self-hosted fonts (Inter, Source Serif 4)
│   └── og/                      # Open Graph images
│
├── styles/
│   └── tokens.css               # Design tokens as CSS variables
│
├── types/
│   ├── api.ts                   # API response types
│   ├── components.ts            # Component prop types
│   └── global.d.ts              # Global type declarations
│
├── tests/
│   ├── __mocks__/               # Test mocks
│   ├── setup.ts                 # Test setup (Vitest)
│   ├── components/              # Component tests
│   ├── hooks/                   # Hook tests
│   └── e2e/                     # Playwright E2E tests
│
├── .env.example                 # Environment template
├── .env.local                   # Local environment (gitignored)
├── next.config.js               # Next.js configuration
├── tailwind.config.js           # Optional: if using Tailwind
├── tsconfig.json                # TypeScript configuration
├── vitest.config.ts             # Vitest configuration
├── playwright.config.ts         # Playwright E2E config
└── package.json
```

---

## 3) Routing Architecture

### 3.1 Route definitions

| Route | Page | Auth | SSR/SSG | Description |
|-------|------|------|---------|-------------|
| `/` | Home | No | SSR | Latest feed (default) |
| `/trending` | Trending | No | SSR | Trending tab |
| `/for-you` | For You | Yes | SSR | Personalized feed |
| `/story/[id]` | Story | No | SSR | StoryCluster detail |
| `/story/[id]/updates` | Updates | No | SSR | Cluster update log |
| `/topic/[id]` | Topic | No | SSR | Topic page |
| `/topic/[id]/lineage` | Lineage | No | SSR | Lineage graph |
| `/entity/[id]` | Entity | No | SSR | Entity page (Stage 10) |
| `/search` | Search | No | CSR | Search results |
| `/saved` | Saved | Yes | CSR | Reading list |
| `/settings` | Settings | Yes | CSR | User preferences |
| `/settings/topics` | Topics | Yes | CSR | Followed topics |
| `/settings/sources` | Sources | Yes | CSR | Blocked sources |
| `/settings/notifications` | Notifications | Yes | CSR | Notification settings |
| `/auth/login` | Login | No | CSR | Magic link request |
| `/auth/verify` | Verify | No | CSR | Magic link verification |

### 3.2 URL patterns (SEO-friendly)

**StoryCluster URLs:**
```
/story/{cluster_id}
/story/{cluster_id}/updates
```

Note: Consider adding slug for SEO in v1:
```
/story/{cluster_id}/{slug}  → /story/abc123/nasa-artemis-mission-crew
```

**Topic URLs:**
```
/topic/{topic_id}
/topic/{topic_id}/lineage
```

**Search:**
```
/search?q={query}&type={clusters|topics|entities}
```

### 3.3 Redirect handling

When API returns `301` with `redirect_to_cluster_id`:
1. Intercept in the fetch layer
2. Use `redirect()` from `next/navigation` to canonical URL
3. Preserve any query parameters

```typescript
// lib/api/clusters.ts
export async function getCluster(id: string): Promise<ClusterDetail> {
  const res = await fetch(`${API_URL}/clusters/${id}`);

  if (res.status === 301) {
    const { redirect_to_cluster_id } = await res.json();
    redirect(`/story/${redirect_to_cluster_id}`);
  }

  return res.json();
}
```

---

## 4) Rendering Strategy

### 4.1 Server Components (default)

Use Server Components for:
- Feed pages (fetch data on server, stream to client)
- Story pages (SEO-critical, mostly static content)
- Topic pages
- Any component that doesn't need interactivity

### 4.2 Client Components (`'use client'`)

Use Client Components for:
- Interactive controls (buttons, forms, modals)
- Components using hooks (useState, useEffect)
- Components using browser APIs
- Real-time features

### 4.3 Streaming and Suspense

Use `<Suspense>` with streaming for progressive loading:

```tsx
// app/story/[id]/page.tsx
import { Suspense } from 'react';
import { StoryHeader } from '@/components/story/StoryHeader';
import { StoryContent } from '@/components/story/StoryContent';
import { EvidencePanel } from '@/components/story/EvidencePanel';
import { StorySkeleton } from '@/components/story/StorySkeleton';

export default async function StoryPage({ params }: { params: { id: string } }) {
  return (
    <article>
      <Suspense fallback={<StorySkeleton.Header />}>
        <StoryHeader clusterId={params.id} />
      </Suspense>

      <Suspense fallback={<StorySkeleton.Content />}>
        <StoryContent clusterId={params.id} />
      </Suspense>

      <Suspense fallback={<StorySkeleton.Evidence />}>
        <EvidencePanel clusterId={params.id} />
      </Suspense>
    </article>
  );
}
```

### 4.4 Data fetching pattern

**Server Components (preferred for initial data):**

```tsx
// Direct fetch in Server Component
async function FeedPage({ searchParams }) {
  const tab = searchParams.tab || 'latest';
  const feed = await getFeed({ tab, page: 1 });

  return <FeedList initialData={feed} tab={tab} />;
}
```

**Client Components (for mutations and real-time):**

```tsx
'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { saveCluster } from '@/lib/api/user';

function SaveButton({ clusterId }: { clusterId: string }) {
  const queryClient = useQueryClient();

  const { mutate, isPending } = useMutation({
    mutationFn: () => saveCluster(clusterId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cluster', clusterId] });
    },
  });

  return (
    <Button onClick={() => mutate()} disabled={isPending}>
      {isPending ? 'Saving...' : 'Save'}
    </Button>
  );
}
```

---

## 5) Authentication Architecture

### 5.1 Auth flow (magic link)

```
┌─────────────────────────────────────────────────────────────┐
│                      Login Flow                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. User enters email on /auth/login                        │
│     │                                                        │
│     ▼                                                        │
│  2. POST /v1/auth/magic_link/start { email }                │
│     │                                                        │
│     ▼                                                        │
│  3. Backend sends email with magic link                     │
│     (link points to /auth/verify?token=...)                 │
│     │                                                        │
│     ▼                                                        │
│  4. User clicks link → /auth/verify?token=xyz               │
│     │                                                        │
│     ▼                                                        │
│  5. POST /v1/auth/magic_link/verify { token }               │
│     │                                                        │
│     ▼                                                        │
│  6. Backend sets cn_session cookie (httpOnly, secure)       │
│     │                                                        │
│     ▼                                                        │
│  7. Redirect to / or original destination                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 Session management

**Cookie-based sessions (backend manages):**
- Cookie name: `cn_session`
- Flags: `httpOnly`, `secure`, `sameSite=lax`
- Frontend never sees token value directly

**Auth state in React:**

```tsx
// lib/context/AuthContext.tsx
'use client';

import { createContext, useContext, useEffect, useState } from 'react';
import { getUser } from '@/lib/api/auth';
import type { User } from '@/types/api';

interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = async () => {
    try {
      const { user } = await getUser();
      setUser(user);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  return (
    <AuthContext.Provider value={{
      user,
      isLoading,
      isAuthenticated: !!user,
      refresh,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
}
```

### 5.3 Protected routes

```tsx
// components/auth/AuthGuard.tsx
'use client';

import { useAuth } from '@/lib/context/AuthContext';
import { useRouter, usePathname } from 'next/navigation';
import { useEffect } from 'react';

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push(`/auth/login?redirect=${encodeURIComponent(pathname)}`);
    }
  }, [isLoading, isAuthenticated, router, pathname]);

  if (isLoading) return <LoadingSkeleton />;
  if (!isAuthenticated) return null;

  return <>{children}</>;
}
```

---

## 6) Environment Configuration

### 6.1 Environment variables

```bash
# .env.example

# API
NEXT_PUBLIC_API_URL=http://localhost:8000/v1
NEXT_PUBLIC_APP_URL=http://localhost:3000

# Feature flags
NEXT_PUBLIC_ENABLE_FOR_YOU=true
NEXT_PUBLIC_ENABLE_ENTITIES=false
NEXT_PUBLIC_ENABLE_LINEAGE=true

# Analytics (optional)
NEXT_PUBLIC_ANALYTICS_ID=

# PWA
NEXT_PUBLIC_PWA_ENABLED=true

# Development
NEXT_PUBLIC_DEV_MODE=true
```

### 6.2 Typed environment access

```typescript
// lib/config/env.ts

const requiredEnvVars = ['NEXT_PUBLIC_API_URL', 'NEXT_PUBLIC_APP_URL'] as const;

function getEnvVar(key: string): string {
  const value = process.env[key];
  if (!value && requiredEnvVars.includes(key as any)) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value || '';
}

export const env = {
  apiUrl: getEnvVar('NEXT_PUBLIC_API_URL'),
  appUrl: getEnvVar('NEXT_PUBLIC_APP_URL'),

  features: {
    forYou: getEnvVar('NEXT_PUBLIC_ENABLE_FOR_YOU') === 'true',
    entities: getEnvVar('NEXT_PUBLIC_ENABLE_ENTITIES') === 'true',
    lineage: getEnvVar('NEXT_PUBLIC_ENABLE_LINEAGE') === 'true',
  },

  pwa: {
    enabled: getEnvVar('NEXT_PUBLIC_PWA_ENABLED') === 'true',
  },

  isDev: process.env.NODE_ENV === 'development',
  isProd: process.env.NODE_ENV === 'production',
} as const;
```

---

## 7) Build and Deployment

### 7.1 Build configuration

```javascript
// next.config.js

const withPWA = require('next-pwa')({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  skipWaiting: true,
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Strict mode for development
  reactStrictMode: true,

  // Image optimization
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: '**.example.com' },
    ],
    formats: ['image/avif', 'image/webp'],
  },

  // Headers
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },

  // Redirects
  async redirects() {
    return [
      { source: '/feed', destination: '/', permanent: true },
      { source: '/home', destination: '/', permanent: true },
    ];
  },
};

module.exports = withPWA(nextConfig);
```

### 7.2 TypeScript configuration

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

### 7.3 Package scripts

```json
// package.json (scripts section)
{
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "lint:fix": "next lint --fix",
    "typecheck": "tsc --noEmit",
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage",
    "test:e2e": "playwright test",
    "test:e2e:ui": "playwright test --ui",
    "generate:types": "openapi-typescript ../design_docs/openapi.v0.yaml -o types/api.generated.ts",
    "analyze": "ANALYZE=true next build"
  }
}
```

---

## 8) Performance Budgets

### 8.1 Core Web Vitals targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| LCP (Largest Contentful Paint) | < 2.5s | p75 |
| FID (First Input Delay) | < 100ms | p75 |
| CLS (Cumulative Layout Shift) | < 0.1 | p75 |
| TTFB (Time to First Byte) | < 800ms | p75 |
| FCP (First Contentful Paint) | < 1.8s | p75 |

### 8.2 Bundle size budgets

| Bundle | Max Size (gzip) |
|--------|-----------------|
| Initial JS | 100KB |
| Initial CSS | 30KB |
| Per-route JS | 50KB |
| Total first load | 150KB |

### 8.3 Monitoring

Use Next.js built-in analytics or integrate with:
- Vercel Analytics (if hosting on Vercel)
- Google Analytics 4
- Plausible (privacy-focused alternative)

---

## 9) Browser Support

### 9.1 Support matrix

| Browser | Minimum Version | Notes |
|---------|-----------------|-------|
| Chrome | 90+ | Full support |
| Firefox | 90+ | Full support |
| Safari | 15+ | Full support |
| Edge | 90+ | Full support |
| Safari iOS | 15+ | PWA limitations |
| Chrome Android | 90+ | Full PWA support |

### 9.2 Polyfills (if needed)

The following are handled by Next.js automatically:
- `Promise`
- `fetch`
- `Object.assign`

Additional polyfills (add only if supporting older browsers):
```javascript
// next.config.js
module.exports = {
  // Only if supporting IE11 (not recommended)
  // transpilePackages: ['...'],
};
```

---

## 10) Security Considerations

### 10.1 Content Security Policy

```javascript
// next.config.js headers
{
  key: 'Content-Security-Policy',
  value: [
    "default-src 'self'",
    "script-src 'self' 'unsafe-eval' 'unsafe-inline'", // Required for Next.js dev
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https:",
    "font-src 'self'",
    "connect-src 'self' " + process.env.NEXT_PUBLIC_API_URL,
    "frame-ancestors 'none'",
  ].join('; '),
}
```

### 10.2 Security checklist

- [ ] All API calls use HTTPS in production
- [ ] Session cookies are httpOnly and secure
- [ ] CSRF protection via SameSite cookies
- [ ] No sensitive data in localStorage
- [ ] Input sanitization for user-generated content
- [ ] XSS prevention via React's automatic escaping
- [ ] No inline event handlers

---

## 11) Accessibility Requirements

### 11.1 WCAG 2.1 AA compliance

Required for all components:

1. **Perceivable**
   - All images have alt text
   - Color contrast ratio ≥ 4.5:1 for normal text
   - Color is not the only means of conveying information

2. **Operable**
   - All interactive elements are keyboard accessible
   - Focus indicators are visible (see design tokens)
   - No keyboard traps
   - Skip links for main content

3. **Understandable**
   - Form inputs have associated labels
   - Error messages are clear and specific
   - Consistent navigation

4. **Robust**
   - Valid HTML
   - ARIA attributes used correctly
   - Works with screen readers (VoiceOver, NVDA)

### 11.2 Testing tools

- axe DevTools browser extension
- Lighthouse accessibility audit
- Manual screen reader testing
- Keyboard-only navigation testing

---

## 12) Dependencies (Recommended)

### 12.1 Core dependencies

```json
{
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "@tanstack/react-query": "^5.28.0",
    "clsx": "^2.1.0",
    "date-fns": "^3.6.0",
    "zod": "^3.22.0"
  }
}
```

### 12.2 Development dependencies

```json
{
  "devDependencies": {
    "typescript": "^5.4.0",
    "@types/react": "^18.2.0",
    "@types/node": "^20.0.0",
    "eslint": "^8.57.0",
    "eslint-config-next": "^14.2.0",
    "vitest": "^1.4.0",
    "@testing-library/react": "^14.2.0",
    "@playwright/test": "^1.42.0",
    "openapi-typescript": "^6.7.0",
    "next-pwa": "^5.6.0"
  }
}
```

### 12.3 Dependency guidelines

**Avoid adding:**
- Heavy animation libraries (use CSS)
- Full-featured component libraries (build to design spec)
- Multiple state management solutions
- Lodash (use native JS)

**Allowed additions:**
- Accessibility primitives (Radix UI, Headless UI)
- Chart library for lineage graph (D3 or similar)
- Form validation (React Hook Form if needed)
