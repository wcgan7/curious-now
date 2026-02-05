# Frontend Testing Strategy — Curious Now

This document specifies the testing strategy, tools, patterns, and requirements for the frontend. It covers unit tests, integration tests, end-to-end tests, and accessibility testing.

---

## 1) Testing Philosophy

### 1.1 Principles

1. **Test behavior, not implementation** — Focus on what users see and do
2. **Pyramid strategy** — Many unit tests, fewer integration tests, minimal E2E tests
3. **Accessibility is mandatory** — Every component must be accessible
4. **Fast feedback** — Tests should run quickly in CI
5. **Realistic testing** — Use MSW for API mocking, not fake data

### 1.2 Testing pyramid

```
        ┌─────────┐
        │   E2E   │  ← Few critical user journeys
        │  (5%)   │
        ├─────────┤
        │ Integr. │  ← Component interactions, hooks
        │  (20%)  │
        ├─────────┤
        │  Unit   │  ← Components, utilities, pure functions
        │  (75%)  │
        └─────────┘
```

### 1.3 Coverage targets

| Area | Target | Notes |
|------|--------|-------|
| Overall | ≥80% | Lines covered |
| Components | ≥85% | All user-facing components |
| Hooks | ≥90% | Critical for data layer |
| Utilities | 100% | Pure functions are easy to test |
| E2E critical paths | 100% | Auth, save, read flows |

---

## 2) Testing Tools

### 2.1 Test stack

| Tool | Purpose |
|------|---------|
| **Vitest** | Unit and integration tests |
| **React Testing Library** | Component testing |
| **MSW (Mock Service Worker)** | API mocking |
| **Playwright** | End-to-end testing |
| **axe-core** | Accessibility testing |
| **@testing-library/user-event** | User interaction simulation |

### 2.2 Dependencies

```json
{
  "devDependencies": {
    "vitest": "^1.4.0",
    "@vitest/coverage-v8": "^1.4.0",
    "@vitest/ui": "^1.4.0",
    "@testing-library/react": "^14.2.0",
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/user-event": "^14.5.0",
    "msw": "^2.2.0",
    "@playwright/test": "^1.42.0",
    "axe-playwright": "^2.0.0",
    "vitest-axe": "^0.1.0"
  }
}
```

---

## 3) Test Configuration

### 3.1 Vitest configuration

```typescript
// vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['**/*.test.{ts,tsx}'],
    exclude: ['**/node_modules/**', '**/e2e/**'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      exclude: [
        'node_modules',
        'tests',
        '**/*.d.ts',
        '**/*.config.*',
        '**/types/**',
      ],
      thresholds: {
        statements: 80,
        branches: 80,
        functions: 80,
        lines: 80,
      },
    },
    // Mock Next.js modules
    alias: {
      '@/': resolve(__dirname, './'),
    },
  },
});
```

### 3.2 Test setup

```typescript
// tests/setup.ts
import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, afterAll, vi } from 'vitest';
import { server } from './mocks/server';

// Establish API mocking before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

// Reset handlers after each test
afterEach(() => {
  cleanup();
  server.resetHandlers();
});

// Clean up after all tests
afterAll(() => server.close());

// Mock Next.js router
vi.mock('next/navigation', () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => '/',
  useSearchParams: () => new URLSearchParams(),
  redirect: vi.fn(),
}));

// Mock Next.js image
vi.mock('next/image', () => ({
  default: ({ src, alt, ...props }: any) => <img src={src} alt={alt} {...props} />,
}));

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));
```

### 3.3 MSW server setup

```typescript
// tests/mocks/server.ts
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
```

```typescript
// tests/mocks/handlers.ts
import { http, HttpResponse } from 'msw';
import { mockFeed, mockCluster, mockTopics, mockUser } from './data';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1';

export const handlers = [
  // Feed
  http.get(`${API_URL}/feed`, ({ request }) => {
    const url = new URL(request.url);
    const tab = url.searchParams.get('tab') || 'latest';
    const page = parseInt(url.searchParams.get('page') || '1');

    return HttpResponse.json({
      tab,
      page,
      results: mockFeed.slice((page - 1) * 20, page * 20),
    });
  }),

  // Cluster detail
  http.get(`${API_URL}/clusters/:id`, ({ params }) => {
    const cluster = mockCluster(params.id as string);
    if (!cluster) {
      return HttpResponse.json(
        { error: { code: 'NOT_FOUND', message: 'Cluster not found' } },
        { status: 404 }
      );
    }
    return HttpResponse.json(cluster);
  }),

  // Topics
  http.get(`${API_URL}/topics`, () => {
    return HttpResponse.json({ topics: mockTopics });
  }),

  // User
  http.get(`${API_URL}/user`, () => {
    return HttpResponse.json({ user: mockUser });
  }),

  // Save cluster
  http.post(`${API_URL}/user/saves/:id`, () => {
    return HttpResponse.json({ status: 'ok' });
  }),

  http.delete(`${API_URL}/user/saves/:id`, () => {
    return HttpResponse.json({ status: 'ok' });
  }),

  // Auth
  http.post(`${API_URL}/auth/magic_link/start`, () => {
    return HttpResponse.json({ status: 'sent' });
  }),

  http.post(`${API_URL}/auth/magic_link/verify`, () => {
    return HttpResponse.json({ user: mockUser });
  }),

  http.post(`${API_URL}/auth/logout`, () => {
    return HttpResponse.json({ status: 'ok' });
  }),

  // Search
  http.get(`${API_URL}/search`, ({ request }) => {
    const url = new URL(request.url);
    const query = url.searchParams.get('q') || '';

    return HttpResponse.json({
      query,
      clusters: mockFeed.filter((c) =>
        c.canonical_title.toLowerCase().includes(query.toLowerCase())
      ),
      topics: [],
    });
  }),

  // Glossary
  http.get(`${API_URL}/glossary`, ({ request }) => {
    const url = new URL(request.url);
    const term = url.searchParams.get('term') || '';

    return HttpResponse.json({
      entry: {
        glossary_entry_id: '1',
        term,
        definition_short: `Definition of ${term}`,
      },
    });
  }),

  // Events (fire and forget)
  http.post(`${API_URL}/events`, () => {
    return HttpResponse.json({ status: 'accepted' });
  }),
];
```

```typescript
// tests/mocks/data.ts
import type { ClusterCard, ClusterDetail, Topic, User } from '@/types/api';

export const mockUser: User = {
  user_id: 'user-1',
  email: 'test@example.com',
  created_at: '2024-01-01T00:00:00Z',
};

export const mockTopics: Topic[] = [
  { topic_id: 'topic-1', name: 'AI', description_short: 'Artificial Intelligence' },
  { topic_id: 'topic-2', name: 'Space', description_short: 'Space exploration' },
  { topic_id: 'topic-3', name: 'Climate', description_short: 'Climate science' },
];

export const mockFeed: ClusterCard[] = [
  {
    cluster_id: 'cluster-1',
    canonical_title: 'New AI model achieves breakthrough performance',
    updated_at: '2024-01-15T10:00:00Z',
    distinct_source_count: 5,
    top_topics: [{ topic_id: 'topic-1', name: 'AI', score: 0.95 }],
    content_type_badges: ['preprint', 'news'],
    method_badges: ['benchmark'],
    takeaway: 'A new AI model shows significant improvements in reasoning tasks.',
    confidence_band: 'early',
    anti_hype_flags: [],
  },
  {
    cluster_id: 'cluster-2',
    canonical_title: 'NASA announces new Mars mission timeline',
    updated_at: '2024-01-14T15:00:00Z',
    distinct_source_count: 8,
    top_topics: [{ topic_id: 'topic-2', name: 'Space', score: 0.92 }],
    content_type_badges: ['press_release', 'news'],
    method_badges: [],
    takeaway: 'NASA reveals updated schedule for crewed Mars missions.',
    confidence_band: 'growing',
    anti_hype_flags: [],
  },
  // Add more mock clusters as needed
];

export function mockCluster(id: string): ClusterDetail | null {
  const card = mockFeed.find((c) => c.cluster_id === id);
  if (!card) return null;

  return {
    ...card,
    created_at: '2024-01-10T00:00:00Z',
    topics: card.top_topics || [],
    content_type_breakdown: { preprint: 1, news: 4 },
    evidence: {
      preprint: [
        {
          item_id: 'item-1',
          title: 'Original research paper',
          url: 'https://example.com/paper',
          published_at: '2024-01-10T00:00:00Z',
          source: { source_id: 'source-1', name: 'arXiv' },
          content_type: 'preprint',
        },
      ],
      news: [
        {
          item_id: 'item-2',
          title: 'News coverage',
          url: 'https://example.com/news',
          published_at: '2024-01-12T00:00:00Z',
          source: { source_id: 'source-2', name: 'Tech News' },
          content_type: 'news',
        },
      ],
    },
    summary_intuition: 'This is the intuition explanation.',
    summary_deep_dive: 'This is the deep dive with technical details.',
    assumptions: ['Assumption 1', 'Assumption 2'],
    limitations: ['Limitation 1'],
    what_could_change_this: ['Further research', 'Peer review'],
    glossary_entries: [
      {
        glossary_entry_id: 'glossary-1',
        term: 'AI',
        definition_short: 'Artificial Intelligence',
      },
    ],
  };
}
```

---

## 4) Unit Tests

### 4.1 Component tests

```typescript
// components/ui/Button/Button.test.tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { Button } from './Button';

describe('Button', () => {
  it('renders with children', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
  });

  it('handles click events', async () => {
    const user = userEvent.setup();
    const handleClick = vi.fn();

    render(<Button onClick={handleClick}>Click me</Button>);

    await user.click(screen.getByRole('button'));
    expect(handleClick).toHaveBeenCalledTimes(1);
  });

  it('shows loading state', () => {
    render(<Button isLoading>Submit</Button>);

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute('aria-busy', 'true');
  });

  it('applies variant styles', () => {
    const { rerender } = render(<Button variant="primary">Primary</Button>);
    expect(screen.getByRole('button')).toHaveClass('primary');

    rerender(<Button variant="secondary">Secondary</Button>);
    expect(screen.getByRole('button')).toHaveClass('secondary');
  });

  it('is accessible', () => {
    render(<Button>Accessible button</Button>);

    const button = screen.getByRole('button');
    expect(button).toHaveAccessibleName('Accessible button');
    expect(button).not.toHaveAttribute('aria-hidden');
  });

  it('supports disabled state', () => {
    render(<Button disabled>Disabled</Button>);

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });
});
```

```typescript
// components/feed/ClusterCard/ClusterCard.test.tsx
import { render, screen, within } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { ClusterCard } from './ClusterCard';
import { mockFeed } from '@/tests/mocks/data';

const mockCluster = mockFeed[0];

describe('ClusterCard', () => {
  it('renders cluster information', () => {
    render(<ClusterCard cluster={mockCluster} />);

    expect(screen.getByText(mockCluster.canonical_title)).toBeInTheDocument();
    expect(screen.getByText(/5 sources/i)).toBeInTheDocument();
  });

  it('renders content type badges', () => {
    render(<ClusterCard cluster={mockCluster} />);

    expect(screen.getByText(/preprint/i)).toBeInTheDocument();
    expect(screen.getByText(/news/i)).toBeInTheDocument();
  });

  it('renders topic chips when showTopics is true', () => {
    render(<ClusterCard cluster={mockCluster} showTopics />);

    expect(screen.getByText('AI')).toBeInTheDocument();
  });

  it('hides topic chips when showTopics is false', () => {
    render(<ClusterCard cluster={mockCluster} showTopics={false} />);

    expect(screen.queryByText('AI')).not.toBeInTheDocument();
  });

  it('renders takeaway when showTakeaway is true', () => {
    render(<ClusterCard cluster={mockCluster} showTakeaway />);

    expect(screen.getByText(mockCluster.takeaway!)).toBeInTheDocument();
  });

  it('links to the story page', () => {
    render(<ClusterCard cluster={mockCluster} />);

    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', `/story/${mockCluster.cluster_id}`);
  });

  it('renders anti-hype flags when present', () => {
    const clusterWithFlags = {
      ...mockCluster,
      anti_hype_flags: ['mice only', 'small sample'],
    };

    render(<ClusterCard cluster={clusterWithFlags} />);

    expect(screen.getByText('mice only')).toBeInTheDocument();
    expect(screen.getByText('small sample')).toBeInTheDocument();
  });

  it('has accessible structure', () => {
    render(<ClusterCard cluster={mockCluster} />);

    const article = screen.getByRole('article');
    expect(article).toBeInTheDocument();

    // Title should be a heading
    const heading = within(article).getByRole('heading');
    expect(heading).toHaveTextContent(mockCluster.canonical_title);
  });
});
```

### 4.2 Hook tests

```typescript
// lib/hooks/useSearch.test.ts
import { renderHook, waitFor } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { useSearch } from './useSearch';

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe('useSearch', () => {
  it('initializes with empty query', () => {
    const { result } = renderHook(() => useSearch(), { wrapper });

    expect(result.current.query).toBe('');
    expect(result.current.results).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
  });

  it('does not search with short query', async () => {
    const { result } = renderHook(() => useSearch('a'), { wrapper });

    expect(result.current.isLoading).toBe(false);
    expect(result.current.results).toBeUndefined();
  });

  it('searches with valid query', async () => {
    const { result } = renderHook(() => useSearch('AI'), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.results).toBeDefined();
    expect(result.current.results?.query).toBe('AI');
  });

  it('updates query via setQuery', async () => {
    const { result } = renderHook(() => useSearch(), { wrapper });

    result.current.setQuery('new query');

    expect(result.current.query).toBe('new query');
  });
});
```

```typescript
// lib/hooks/useSaveCluster.test.ts
import { renderHook, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { useSaveCluster } from './useUserActions';
import { ToastProvider } from '@/lib/context/ToastContext';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <ToastProvider>{children}</ToastProvider>
      </QueryClientProvider>
    );
  };
}

describe('useSaveCluster', () => {
  it('saves a cluster successfully', async () => {
    const { result } = renderHook(() => useSaveCluster(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ clusterId: 'cluster-1', save: true });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });

  it('unsaves a cluster successfully', async () => {
    const { result } = renderHook(() => useSaveCluster(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      result.current.mutate({ clusterId: 'cluster-1', save: false });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });
  });
});
```

### 4.3 Utility tests

```typescript
// lib/utils/formatters.test.ts
import { describe, it, expect } from 'vitest';
import { formatRelativeTime, formatNumber, truncateText } from './formatters';

describe('formatRelativeTime', () => {
  it('formats seconds ago', () => {
    const date = new Date(Date.now() - 30 * 1000);
    expect(formatRelativeTime(date)).toBe('less than a minute ago');
  });

  it('formats minutes ago', () => {
    const date = new Date(Date.now() - 5 * 60 * 1000);
    expect(formatRelativeTime(date)).toBe('5 minutes ago');
  });

  it('formats hours ago', () => {
    const date = new Date(Date.now() - 3 * 60 * 60 * 1000);
    expect(formatRelativeTime(date)).toBe('about 3 hours ago');
  });
});

describe('formatNumber', () => {
  it('formats small numbers', () => {
    expect(formatNumber(42)).toBe('42');
  });

  it('formats thousands', () => {
    expect(formatNumber(1234)).toBe('1.2K');
  });

  it('formats millions', () => {
    expect(formatNumber(1234567)).toBe('1.2M');
  });
});

describe('truncateText', () => {
  it('returns short text unchanged', () => {
    expect(truncateText('Hello', 10)).toBe('Hello');
  });

  it('truncates long text', () => {
    expect(truncateText('Hello world', 8)).toBe('Hello...');
  });

  it('handles empty string', () => {
    expect(truncateText('', 10)).toBe('');
  });
});
```

---

## 5) Integration Tests

### 5.1 Page-level integration tests

```typescript
// app/page.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import HomePage from './page';
import { Providers } from './providers';

// Note: For Server Components, we need a different approach
// This tests the client-side behavior after hydration

describe('HomePage', () => {
  it('renders feed tabs', async () => {
    render(
      <Providers>
        <HomePage />
      </Providers>
    );

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /latest/i })).toBeInTheDocument();
      expect(screen.getByRole('tab', { name: /trending/i })).toBeInTheDocument();
    });
  });

  it('renders cluster cards from feed', async () => {
    render(
      <Providers>
        <HomePage />
      </Providers>
    );

    await waitFor(() => {
      expect(
        screen.getByText(/new ai model achieves breakthrough/i)
      ).toBeInTheDocument();
    });
  });
});
```

```typescript
// components/story/StoryPage.integration.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect } from 'vitest';
import { StoryPageClient } from './StoryPageClient';
import { Providers } from '@/app/providers';
import { mockCluster } from '@/tests/mocks/data';

describe('StoryPage Integration', () => {
  it('renders cluster detail', async () => {
    const cluster = mockCluster('cluster-1');

    render(
      <Providers>
        <StoryPageClient cluster={cluster!} />
      </Providers>
    );

    expect(screen.getByRole('heading', { name: cluster!.canonical_title })).toBeInTheDocument();
    expect(screen.getByText(/5 sources/i)).toBeInTheDocument();
  });

  it('renders takeaway module', async () => {
    const cluster = mockCluster('cluster-1');

    render(
      <Providers>
        <StoryPageClient cluster={cluster!} />
      </Providers>
    );

    expect(screen.getByText(/takeaway/i)).toBeInTheDocument();
    expect(screen.getByText(cluster!.takeaway!)).toBeInTheDocument();
  });

  it('expands deep dive section', async () => {
    const user = userEvent.setup();
    const cluster = mockCluster('cluster-1');

    render(
      <Providers>
        <StoryPageClient cluster={cluster!} />
      </Providers>
    );

    // Deep dive should be collapsed initially
    expect(screen.queryByText(cluster!.summary_deep_dive!)).not.toBeVisible();

    // Click to expand
    await user.click(screen.getByText(/go deeper/i));

    // Now should be visible
    await waitFor(() => {
      expect(screen.getByText(cluster!.summary_deep_dive!)).toBeVisible();
    });
  });

  it('handles save action', async () => {
    const user = userEvent.setup();
    const cluster = mockCluster('cluster-1');

    render(
      <Providers>
        <StoryPageClient cluster={cluster!} />
      </Providers>
    );

    const saveButton = screen.getByRole('button', { name: /save/i });
    await user.click(saveButton);

    await waitFor(() => {
      expect(screen.getByText(/saved/i)).toBeInTheDocument();
    });
  });

  it('renders evidence panel with grouped items', async () => {
    const cluster = mockCluster('cluster-1');

    render(
      <Providers>
        <StoryPageClient cluster={cluster!} />
      </Providers>
    );

    expect(screen.getByText(/evidence & sources/i)).toBeInTheDocument();
    expect(screen.getByText(/preprints/i)).toBeInTheDocument();
    expect(screen.getByText(/news coverage/i)).toBeInTheDocument();
  });
});
```

### 5.2 Form integration tests

```typescript
// components/auth/LoginForm.integration.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { LoginForm } from './LoginForm';
import { Providers } from '@/app/providers';

describe('LoginForm Integration', () => {
  it('submits email and shows success message', async () => {
    const user = userEvent.setup();

    render(
      <Providers>
        <LoginForm />
      </Providers>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const submitButton = screen.getByRole('button', { name: /continue/i });

    await user.type(emailInput, 'test@example.com');
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/check your email/i)).toBeInTheDocument();
    });
  });

  it('shows validation error for invalid email', async () => {
    const user = userEvent.setup();

    render(
      <Providers>
        <LoginForm />
      </Providers>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const submitButton = screen.getByRole('button', { name: /continue/i });

    await user.type(emailInput, 'invalid-email');
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/valid email/i)).toBeInTheDocument();
    });
  });

  it('disables submit while loading', async () => {
    const user = userEvent.setup();

    render(
      <Providers>
        <LoginForm />
      </Providers>
    );

    const emailInput = screen.getByLabelText(/email/i);
    const submitButton = screen.getByRole('button', { name: /continue/i });

    await user.type(emailInput, 'test@example.com');
    await user.click(submitButton);

    expect(submitButton).toBeDisabled();
  });
});
```

---

## 6) End-to-End Tests

### 6.1 Playwright configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',

  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },
    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 13'] },
    },
  ],

  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

### 6.2 Critical path tests

```typescript
// tests/e2e/feed.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Feed', () => {
  test('loads the home page with latest feed', async ({ page }) => {
    await page.goto('/');

    // Check page title
    await expect(page).toHaveTitle(/Curious Now/);

    // Check feed tabs are visible
    await expect(page.getByRole('tab', { name: /latest/i })).toBeVisible();
    await expect(page.getByRole('tab', { name: /trending/i })).toBeVisible();

    // Check at least one cluster card is visible
    await expect(page.getByRole('article').first()).toBeVisible();
  });

  test('switches between feed tabs', async ({ page }) => {
    await page.goto('/');

    // Click trending tab
    await page.getByRole('tab', { name: /trending/i }).click();

    // URL should update
    await expect(page).toHaveURL('/trending');

    // Go back to latest
    await page.getByRole('tab', { name: /latest/i }).click();
    await expect(page).toHaveURL('/');
  });

  test('loads more stories on scroll', async ({ page }) => {
    await page.goto('/');

    // Count initial cards
    const initialCount = await page.getByRole('article').count();

    // Scroll to bottom and click load more
    await page.getByRole('button', { name: /load more/i }).click();

    // Wait for more cards
    await expect(page.getByRole('article')).toHaveCount(
      expect.greaterThan(initialCount)
    );
  });
});
```

```typescript
// tests/e2e/story.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Story Page', () => {
  test('navigates to story from feed', async ({ page }) => {
    await page.goto('/');

    // Click first story card
    const firstCard = page.getByRole('article').first();
    const title = await firstCard.getByRole('heading').textContent();
    await firstCard.click();

    // Check we're on the story page
    await expect(page.getByRole('heading', { name: title! })).toBeVisible();
  });

  test('displays story content', async ({ page }) => {
    await page.goto('/story/cluster-1');

    // Check main sections are visible
    await expect(page.getByText(/takeaway/i)).toBeVisible();
    await expect(page.getByText(/sources/i)).toBeVisible();
  });

  test('expands deep dive section', async ({ page }) => {
    await page.goto('/story/cluster-1');

    // Deep dive should be collapsed
    const deepDiveButton = page.getByText(/go deeper/i);
    await expect(deepDiveButton).toBeVisible();

    // Click to expand
    await deepDiveButton.click();

    // Content should be visible
    await expect(page.getByText(/technical details/i)).toBeVisible();
  });

  test('shows glossary tooltip', async ({ page }) => {
    await page.goto('/story/cluster-1');

    // Hover over a glossary term
    await page.getByText('AI').first().hover();

    // Tooltip should appear
    await expect(page.getByRole('tooltip')).toBeVisible();
  });
});
```

```typescript
// tests/e2e/auth.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('shows login page', async ({ page }) => {
    await page.goto('/auth/login');

    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
  });

  test('submits magic link request', async ({ page }) => {
    await page.goto('/auth/login');

    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByRole('button', { name: /continue/i }).click();

    // Should show success message
    await expect(page.getByText(/check your email/i)).toBeVisible();
  });

  test('redirects unauthenticated users from protected pages', async ({ page }) => {
    await page.goto('/for-you');

    // Should redirect to login
    await expect(page).toHaveURL(/\/auth\/login/);
  });

  test('redirects to saved page after login', async ({ page }) => {
    // Start at saved page (protected)
    await page.goto('/saved');

    // Will redirect to login with redirect param
    await expect(page).toHaveURL(/redirect.*saved/);

    // Complete login (mock)
    await page.getByLabel(/email/i).fill('test@example.com');
    await page.getByRole('button', { name: /continue/i }).click();

    // In a real test, we'd verify the magic link flow
  });
});
```

```typescript
// tests/e2e/search.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Search', () => {
  test('opens search modal', async ({ page }) => {
    await page.goto('/');

    // Click search button
    await page.getByRole('button', { name: /search/i }).click();

    // Search modal should be visible
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByPlaceholder(/search/i)).toBeFocused();
  });

  test('searches and shows results', async ({ page }) => {
    await page.goto('/');

    // Open search
    await page.getByRole('button', { name: /search/i }).click();

    // Type search query
    await page.getByPlaceholder(/search/i).fill('AI');

    // Wait for results
    await expect(page.getByText(/results/i)).toBeVisible();
  });

  test('navigates to search results page', async ({ page }) => {
    await page.goto('/');

    // Open search
    await page.getByRole('button', { name: /search/i }).click();

    // Type and submit
    await page.getByPlaceholder(/search/i).fill('climate');
    await page.keyboard.press('Enter');

    // Should be on search page
    await expect(page).toHaveURL(/\/search\?q=climate/);
  });

  test('closes search with Escape', async ({ page }) => {
    await page.goto('/');

    // Open search
    await page.getByRole('button', { name: /search/i }).click();
    await expect(page.getByRole('dialog')).toBeVisible();

    // Press Escape
    await page.keyboard.press('Escape');

    // Modal should close
    await expect(page.getByRole('dialog')).not.toBeVisible();
  });
});
```

---

## 7) Accessibility Testing

### 7.1 Axe integration

```typescript
// tests/e2e/accessibility.spec.ts
import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility', () => {
  test('home page has no accessibility violations', async ({ page }) => {
    await page.goto('/');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test('story page has no accessibility violations', async ({ page }) => {
    await page.goto('/story/cluster-1');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test('login page has no accessibility violations', async ({ page }) => {
    await page.goto('/auth/login');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  test('search modal has no accessibility violations', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: /search/i }).click();

    const results = await new AxeBuilder({ page })
      .include('[role="dialog"]')
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });
});
```

### 7.2 Component-level accessibility tests

```typescript
// components/ui/Button/Button.a11y.test.tsx
import { render, screen } from '@testing-library/react';
import { axe, toHaveNoViolations } from 'vitest-axe';
import { describe, it, expect } from 'vitest';
import { Button } from './Button';

expect.extend(toHaveNoViolations);

describe('Button accessibility', () => {
  it('has no accessibility violations', async () => {
    const { container } = render(<Button>Click me</Button>);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has no violations when disabled', async () => {
    const { container } = render(<Button disabled>Disabled</Button>);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('has no violations when loading', async () => {
    const { container } = render(<Button isLoading>Loading</Button>);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
```

### 7.3 Keyboard navigation tests

```typescript
// tests/e2e/keyboard.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Keyboard Navigation', () => {
  test('can navigate feed with keyboard', async ({ page }) => {
    await page.goto('/');

    // Tab to first card
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // First card should be focused
    const focusedElement = page.locator(':focus');
    await expect(focusedElement).toHaveRole('link');

    // Press Enter to navigate
    await page.keyboard.press('Enter');

    // Should be on story page
    await expect(page).toHaveURL(/\/story\//);
  });

  test('can operate modals with keyboard', async ({ page }) => {
    await page.goto('/');

    // Tab to search button and press Enter
    await page.keyboard.press('Tab');
    await page.keyboard.press('Enter');

    // Modal should open with input focused
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByPlaceholder(/search/i)).toBeFocused();

    // Escape should close
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).not.toBeVisible();
  });

  test('focus trap works in modal', async ({ page }) => {
    await page.goto('/');

    // Open search
    await page.getByRole('button', { name: /search/i }).click();

    // Tab through modal elements
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');
    await page.keyboard.press('Tab');

    // Focus should stay within modal
    const focusedElement = page.locator(':focus');
    const modal = page.getByRole('dialog');
    await expect(focusedElement).toBeVisible();

    // Focus should be inside modal
    const isInModal = await focusedElement.evaluate((el, modalEl) => {
      return modalEl?.contains(el);
    }, await modal.elementHandle());

    expect(isInModal).toBe(true);
  });

  test('skip link works', async ({ page }) => {
    await page.goto('/');

    // First Tab should reveal skip link
    await page.keyboard.press('Tab');

    const skipLink = page.getByRole('link', { name: /skip to content/i });
    await expect(skipLink).toBeFocused();

    // Activate skip link
    await page.keyboard.press('Enter');

    // Focus should be on main content
    const main = page.getByRole('main');
    await expect(main).toBeFocused();
  });
});
```

---

## 8) Visual Regression Testing

### 8.1 Playwright visual comparisons

```typescript
// tests/e2e/visual.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Visual Regression', () => {
  test('home page matches snapshot', async ({ page }) => {
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('home.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('story page matches snapshot', async ({ page }) => {
    await page.goto('/story/cluster-1');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('story.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('dark mode matches snapshot', async ({ page }) => {
    await page.goto('/');
    await page.emulateMedia({ colorScheme: 'dark' });
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('home-dark.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });

  test('mobile layout matches snapshot', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/');
    await page.waitForLoadState('networkidle');

    await expect(page).toHaveScreenshot('home-mobile.png', {
      fullPage: true,
      animations: 'disabled',
    });
  });
});
```

---

## 9) CI/CD Integration

### 9.1 GitHub Actions workflow

```yaml
# .github/workflows/test.yml
name: Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        working-directory: web
        run: npm ci

      - name: Run unit tests
        working-directory: web
        run: npm test -- --coverage

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: web/coverage/lcov.info
          fail_ci_if_error: true

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        working-directory: web
        run: npm ci

      - name: Install Playwright browsers
        working-directory: web
        run: npx playwright install --with-deps

      - name: Build app
        working-directory: web
        run: npm run build

      - name: Run E2E tests
        working-directory: web
        run: npm run test:e2e

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: web/playwright-report/

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        working-directory: web
        run: npm ci

      - name: Type check
        working-directory: web
        run: npm run typecheck

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'
          cache-dependency-path: web/package-lock.json

      - name: Install dependencies
        working-directory: web
        run: npm ci

      - name: Lint
        working-directory: web
        run: npm run lint
```

---

## 10) Testing Checklist

### 10.1 Before merging PR

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All E2E tests pass
- [ ] No accessibility violations
- [ ] Coverage thresholds met
- [ ] No TypeScript errors
- [ ] No lint errors
- [ ] Visual regression tests pass (if applicable)

### 10.2 Manual testing checklist

- [ ] Test on Chrome, Firefox, Safari
- [ ] Test on iOS Safari and Android Chrome
- [ ] Test keyboard navigation
- [ ] Test with screen reader (VoiceOver/NVDA)
- [ ] Test offline behavior
- [ ] Test slow network (3G simulation)
- [ ] Test PWA installation
