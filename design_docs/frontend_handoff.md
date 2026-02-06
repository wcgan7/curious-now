# Frontend Handoff (v0) — Curious Now

This is the single “handoff” doc for a developer implementing the **Next.js (App Router) frontend** described in `design_docs/stage3.md`, backed by the API contract in `design_docs/openapi.v0.yaml`.

## Read Order (recommended)

1. `design_docs/openapi.v0.yaml` (API contract + response shapes)
2. `design_docs/stage3.md` (design tokens + implementation-ready UI spec)
3. `design_docs/frontend/architecture.md` (project structure + routing + auth approach)
4. `design_docs/frontend/data_layer.md` (typed API client + TanStack Query patterns)
5. `design_docs/frontend/components.md` (component hierarchy + props + CSS Modules patterns)
6. `design_docs/frontend/pwa.md` (service worker + offline saved reading list)
7. `design_docs/frontend/testing.md` (Vitest/MSW/Playwright strategy)
8. `design_docs/frontend/error_empty_states.md` + `design_docs/frontend/accessibility.md` (quality bar)
9. `design_docs/frontend/seo_analytics.md` (optional; some sections are v1-oriented)

## Locked Decisions (do not re-litigate for v0)

- **Framework:** Next.js 14+ (App Router) + React 18 + TypeScript (`strict: true`)
- **Styling:** CSS Modules + CSS Variables (design tokens); no runtime CSS-in-JS
- **Server-first:** Server Components by default; client components only when needed
- **Server state:** TanStack Query for client-side server state + mutations
- **Auth:** Backend-managed **cookie session** (`cn_session`, HttpOnly). All authenticated fetches must set `credentials: 'include'`.
- **Routing (v0):** ID-based routes:
  - `/story/[id]` (StoryCluster UUID)
  - `/topic/[id]` (Topic UUID)
  - `/entity/[id]` (Entity UUID; behind feature flag)
  - Optional v1: add a human slug as a *secondary* segment (`/story/[id]/[slug]`) but never rely on slugs for lookup.

## Folder / Path Conventions

All frontend code lives under **`web/`** (see `design_docs/frontend/architecture.md`).

Some older snippets in docs use a `src/` prefix. For this project, treat those as paths **relative to `web/`** (e.g. `src/app/layout.tsx` → `web/app/layout.tsx`).

## Design Tokens: Canonical vs Compat

**Canonical tokens** are defined in `design_docs/stage3.md` (e.g. `--bg`, `--surface-1`, `--text-1`, `--primary`, `--s-*`, `--r-*`).

Some supporting docs include example CSS using `--color-*`, `--space-*`, `--radius-*`, and a small `--text-*` size scale. To avoid churn, either:

1. **Translate samples** to the canonical Stage 3 tokens, or
2. Add a small **compat alias layer** in `web/app/globals.css` so both naming schemes work.

Minimal compat aliases (recommended if you want to copy/paste from the supporting docs):

```css
/* web/app/globals.css (compat aliases; keep canonical tokens as source of truth) */
:root {
  /* Spacing */
  --space-1: var(--s-1);
  --space-2: var(--s-2);
  --space-3: var(--s-3);
  --space-4: var(--s-4);
  --space-5: 20px; /* used in some docs; not in the canonical --s-* scale */
  --space-6: var(--s-6);
  --space-8: var(--s-8);
  --space-12: var(--s-12);

  /* Radius */
  --radius-sm: var(--r-sm);
  --radius-md: var(--r-md);
  --radius-lg: var(--r-lg);
  --radius-full: 9999px;

  /* Colors */
  --color-text-primary: var(--text-1);
  --color-text-secondary: var(--text-2);
  --color-text-tertiary: var(--text-3);
  --color-primary: var(--primary);

  --color-error: var(--danger);
  --color-warning-text: var(--warning);
  --color-warning-bg: color-mix(in srgb, var(--warning) 12%, var(--surface-1));

  /* Common “bg/border/ring” helpers used in examples */
  --color-primary-bg: color-mix(in srgb, var(--primary) 10%, var(--surface-1));
  --color-primary-bg-hover: color-mix(in srgb, var(--primary) 14%, var(--surface-1));

  --color-error-text: var(--danger);
  --color-error-bg: color-mix(in srgb, var(--danger) 10%, var(--surface-1));
  --color-error-border: color-mix(in srgb, var(--danger) 35%, var(--border));
  --color-error-ring: color-mix(in srgb, var(--danger) 30%, transparent);

  /* Skeleton */
  --color-skeleton-base: color-mix(in srgb, var(--border) 70%, var(--surface-2));
  --color-skeleton-highlight: var(--surface-1);

  /* Type scale (only for examples that use these names) */
  --text-xs: 12px;
  --text-sm: 14px;
  --text-base: 16px;
  --text-lg: 18px;
  --text-2xl: 24px;

  /* Font aliases */
  --font-serif: var(--font-article);
}
```

## Implementation Checklist (v0)

- **Project bootstrap**
  - Create `web/` Next.js app per `design_docs/frontend/architecture.md`
  - Add envs from the architecture doc (`NEXT_PUBLIC_API_URL`, etc.)
  - Generate TypeScript types from `design_docs/openapi.v0.yaml` (see `design_docs/frontend/data_layer.md`)
- **Core pages**
  - Feed: `/` (latest), `/trending`, `/for-you` (auth)
  - Story: `/story/[id]` + `/story/[id]/updates`
  - Topic: `/topic/[id]` + `/topic/[id]/lineage` (feature-flagged)
  - Search: `/search?q=...`
  - Saved: `/saved` (auth, offline support)
  - Settings: `/settings/*` (auth)
- **Auth flow (magic link)**
  - `/auth/login` (start) → `/auth/verify?token=...` (verify) → cookie session set by backend
  - Ensure all API calls use `credentials: 'include'`
- **Mutations + optimistic UX**
  - Save/unsave, watch/unwatch, follow/unfollow, block/unblock, prefs updates, feedback, events
- **Offline / PWA**
  - Implement “Saved stories work offline” per `design_docs/frontend/pwa.md`
  - v0 decision: do not depend on backend `/v1/offline/*` endpoints; treat them as optional future optimization
- **Quality bar**
  - Error/empty/loading/offline states covered (`design_docs/frontend/error_empty_states.md`)
  - WCAG 2.1 AA target (`design_docs/frontend/accessibility.md`)
  - Tests set up (unit/integration/E2E) per `design_docs/frontend/testing.md`

## Notes About Backend Data (so UI doesn’t break)

- StoryCluster “understanding” fields (`takeaway`, `summary_*`, etc.) are nullable; UI must support **evidence-only mode** (show evidence list and omit missing sections).
- Redirect behavior for merged clusters/topics is represented via `301` responses with JSON redirect payloads (see OpenAPI); fetch layer should handle this and route to the canonical ID.
- “Semantic search” is optional; frontend should treat it as a progressive enhancement and fall back to `/v1/search`.

