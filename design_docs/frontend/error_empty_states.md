# Error States & Empty States Specification

## Overview

This document specifies all error states, empty states, loading states, and offline states for Curious Now. Consistent handling of these states improves user experience and reduces confusion.

**Token note:** Canonical UI tokens (colors/spacing/radius) are defined in `design_docs/stage3.md`. Some snippets in this doc use generic `--color-*` / `--space-*` / `--radius-*` / `--text-*` names; translate them to the canonical tokens or use the compat aliases in `design_docs/frontend_handoff.md`.

---

## Design Principles

1. **Be helpful, not technical** - Use plain language, not error codes
2. **Suggest next steps** - Always provide an action the user can take
3. **Match the context** - Inline errors for forms, full-page for navigation
4. **Maintain brand voice** - Keep the curious, friendly tone even in errors
5. **Preserve progress** - Never lose user data due to an error

---

## Error State Components

### Full-Page Error

Used for route-level errors (404, 500, etc.)

```tsx
// components/errors/FullPageError.tsx
import styles from './FullPageError.module.css';
import { Button } from '@/components/ui/Button';

interface FullPageErrorProps {
  title: string;
  message: string;
  illustration: 'not-found' | 'server-error' | 'offline' | 'maintenance';
  primaryAction?: {
    label: string;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
}

export function FullPageError({
  title,
  message,
  illustration,
  primaryAction,
  secondaryAction,
}: FullPageErrorProps) {
  return (
    <div className={styles.container}>
      <div className={styles.content}>
        <div className={styles.illustration}>
          <ErrorIllustration type={illustration} />
        </div>
        <h1 className={styles.title}>{title}</h1>
        <p className={styles.message}>{message}</p>
        <div className={styles.actions}>
          {primaryAction && (
            <Button variant="primary" onClick={primaryAction.onClick}>
              {primaryAction.label}
            </Button>
          )}
          {secondaryAction && (
            <Button variant="tertiary" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
```

```css
/* FullPageError.module.css */
.container {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-8);
  text-align: center;
}

.content {
  max-width: 400px;
}

.illustration {
  margin-bottom: var(--space-6);
}

.illustration svg {
  width: 200px;
  height: 160px;
  color: var(--color-primary);
}

.title {
  font-family: var(--font-serif);
  font-size: var(--text-2xl);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 var(--space-3) 0;
}

.message {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin: 0 0 var(--space-6) 0;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

@media (min-width: 480px) {
  .actions {
    flex-direction: row;
    justify-content: center;
  }
}
```

### Inline Error

Used for component-level errors within a page.

```tsx
// components/errors/InlineError.tsx
import styles from './InlineError.module.css';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface InlineErrorProps {
  message: string;
  onRetry?: () => void;
  compact?: boolean;
}

export function InlineError({ message, onRetry, compact }: InlineErrorProps) {
  return (
    <div className={`${styles.container} ${compact ? styles.compact : ''}`}>
      <AlertCircle className={styles.icon} size={compact ? 16 : 20} />
      <span className={styles.message}>{message}</span>
      {onRetry && (
        <button className={styles.retryButton} onClick={onRetry}>
          <RefreshCw size={14} />
          Try again
        </button>
      )}
    </div>
  );
}
```

```css
/* InlineError.module.css */
.container {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background-color: var(--color-error-bg);
  border: 1px solid var(--color-error-border);
  border-radius: var(--radius-md);
}

.compact {
  padding: var(--space-2) var(--space-3);
}

.icon {
  color: var(--color-error);
  flex-shrink: 0;
}

.message {
  font-size: var(--text-sm);
  color: var(--color-error-text);
  flex: 1;
}

.retryButton {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-1) var(--space-2);
  font-size: var(--text-xs);
  font-weight: 500;
  color: var(--color-error);
  background: none;
  border: 1px solid var(--color-error);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background-color 0.15s;
}

.retryButton:hover {
  background-color: var(--color-error-bg);
}
```

### Toast Error

Used for transient errors that don't block interaction.

```tsx
// Already defined in design_docs/frontend/components.md
// Usage example:
const { showToast } = useToast();

showToast({
  type: 'error',
  message: 'Failed to save story. Please try again.',
  action: {
    label: 'Retry',
    onClick: handleRetry,
  },
});
```

---

## Specific Error States

### 404 - Page Not Found

`app/not-found.tsx`

```tsx
import { FullPageError } from '@/components/errors/FullPageError';
import { useRouter } from 'next/navigation';

export default function NotFound() {
  const router = useRouter();

  return (
    <FullPageError
      title="Page not found"
      message="The page you're looking for doesn't exist or may have been moved. Let's get you back on track."
      illustration="not-found"
      primaryAction={{
        label: 'Go to homepage',
        onClick: () => router.push('/'),
      }}
      secondaryAction={{
        label: 'Search stories',
        onClick: () => router.push('/search'),
      }}
    />
  );
}
```

**Illustration Description:**
- Telescope pointing at empty stars
- Muted primary blue color
- Subtle animation: stars twinkling

### 500 - Server Error

`app/error.tsx`

```tsx
'use client';

import { useEffect } from 'react';
import { FullPageError } from '@/components/errors/FullPageError';
import { useAnalytics } from '@/providers/AnalyticsProvider';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  const { track } = useAnalytics();

  useEffect(() => {
    // Log error to analytics/monitoring
    track({
      name: 'error_boundary',
      properties: {
        error: error.message,
        digest: error.digest,
        page: window.location.pathname,
      },
    });
  }, [error, track]);

  return (
    <FullPageError
      title="Something went wrong"
      message="We're having trouble loading this page. Our team has been notified and is working on it."
      illustration="server-error"
      primaryAction={{
        label: 'Try again',
        onClick: reset,
      }}
      secondaryAction={{
        label: 'Go to homepage',
        onClick: () => (window.location.href = '/'),
      }}
    />
  );
}
```

**Illustration Description:**
- Broken beaker or test tube
- Spilled liquid forming question mark
- Warm error orange accent

### Offline State

`components/errors/OfflineState.tsx`

```tsx
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import { FullPageError } from './FullPageError';
import { Cloud, CloudOff } from 'lucide-react';

export function OfflineFallback() {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <FullPageError
      title="You're offline"
      message="Check your internet connection. Your saved stories are still available to read."
      illustration="offline"
      primaryAction={{
        label: 'View saved stories',
        onClick: () => (window.location.href = '/saved'),
      }}
    />
  );
}
```

**Illustration Description:**
- Cloud with disconnected signal waves
- Subtle dashed lines suggesting broken connection
- Muted gray tones

### Maintenance Mode

`app/maintenance/page.tsx`

```tsx
import { FullPageError } from '@/components/errors/FullPageError';

export default function MaintenancePage() {
  return (
    <FullPageError
      title="We'll be right back"
      message="We're making some improvements to Curious Now. Check back in a few minutes."
      illustration="maintenance"
      primaryAction={{
        label: 'Check status',
        onClick: () => window.open('https://status.curious.now', '_blank'),
      }}
    />
  );
}
```

**Illustration Description:**
- Microscope with wrench
- "Under construction" vibe but scientific
- Primary blue with accent yellow

### Rate Limited

```tsx
<FullPageError
  title="Slow down there!"
  message="You're making requests too quickly. Please wait a moment before trying again."
  illustration="rate-limit"
  primaryAction={{
    label: 'Go back',
    onClick: () => router.back(),
  }}
/>
```

### Authentication Required

```tsx
<FullPageError
  title="Sign in required"
  message="You need to be signed in to view this page. It only takes a few seconds."
  illustration="auth-required"
  primaryAction={{
    label: 'Sign in',
    onClick: () => router.push('/auth/login?redirect=' + pathname),
  }}
  secondaryAction={{
    label: 'Go to homepage',
    onClick: () => router.push('/'),
  }}
/>
```

---

## Empty States

### Empty Feed

When no stories are available (rare, but possible during initial launch or filters).

```tsx
// components/feed/EmptyFeed.tsx
import styles from './EmptyFeed.module.css';
import { Newspaper } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface EmptyFeedProps {
  type: 'today' | 'topic' | 'filter';
  topicName?: string;
  onClearFilters?: () => void;
}

export function EmptyFeed({ type, topicName, onClearFilters }: EmptyFeedProps) {
  const content = {
    today: {
      title: 'No stories yet today',
      message:
        "We're still gathering today's science news. Check back soon or explore yesterday's stories.",
      action: 'View recent stories',
    },
    topic: {
      title: `No ${topicName} stories`,
      message: `We haven't found any ${topicName?.toLowerCase()} stories recently. Try exploring other topics.`,
      action: 'Browse all topics',
    },
    filter: {
      title: 'No matching stories',
      message:
        "No stories match your current filters. Try adjusting your search or clearing filters.",
      action: 'Clear filters',
    },
  };

  const { title, message, action } = content[type];

  return (
    <div className={styles.container}>
      <div className={styles.iconWrapper}>
        <Newspaper className={styles.icon} />
      </div>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.message}>{message}</p>
      {onClearFilters && type === 'filter' && (
        <Button variant="secondary" onClick={onClearFilters}>
          {action}
        </Button>
      )}
    </div>
  );
}
```

```css
/* EmptyFeed.module.css */
.container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.iconWrapper {
  width: 80px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-surface-alt);
  border-radius: 50%;
  margin-bottom: var(--space-6);
}

.icon {
  width: 36px;
  height: 36px;
  color: var(--color-text-tertiary);
}

.title {
  font-family: var(--font-serif);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 var(--space-2) 0;
}

.message {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  max-width: 300px;
  line-height: 1.6;
  margin: 0 0 var(--space-6) 0;
}
```

### Empty Saved Stories

```tsx
// components/saved/EmptySaved.tsx
import styles from './EmptySaved.module.css';
import { Bookmark } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import Link from 'next/link';

export function EmptySaved() {
  return (
    <div className={styles.container}>
      <div className={styles.iconWrapper}>
        <Bookmark className={styles.icon} />
      </div>
      <h3 className={styles.title}>No saved stories yet</h3>
      <p className={styles.message}>
        When you find a story you want to read later, tap the bookmark icon to save it here.
        Saved stories are available offline too!
      </p>
      <Link href="/">
        <Button variant="primary">Browse stories</Button>
      </Link>
    </div>
  );
}
```

### Empty Search Results

```tsx
// components/search/EmptySearch.tsx
import styles from './EmptySearch.module.css';
import { Search } from 'lucide-react';

interface EmptySearchProps {
  query: string;
  suggestions?: string[];
}

export function EmptySearch({ query, suggestions }: EmptySearchProps) {
  return (
    <div className={styles.container}>
      <div className={styles.iconWrapper}>
        <Search className={styles.icon} />
      </div>
      <h3 className={styles.title}>No results for "{query}"</h3>
      <p className={styles.message}>
        We couldn't find any stories matching your search. Try different keywords
        or check the spelling.
      </p>
      {suggestions && suggestions.length > 0 && (
        <div className={styles.suggestions}>
          <p className={styles.suggestionsLabel}>Try searching for:</p>
          <div className={styles.suggestionsList}>
            {suggestions.map((suggestion) => (
              <Link
                key={suggestion}
                href={`/search?q=${encodeURIComponent(suggestion)}`}
                className={styles.suggestionChip}
              >
                {suggestion}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
```

```css
/* EmptySearch.module.css */
.container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.iconWrapper {
  width: 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--color-surface-alt);
  border-radius: var(--radius-lg);
  margin-bottom: var(--space-5);
}

.icon {
  width: 28px;
  height: 28px;
  color: var(--color-text-tertiary);
}

.title {
  font-family: var(--font-serif);
  font-size: var(--text-lg);
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 var(--space-2) 0;
}

.message {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  max-width: 320px;
  line-height: 1.6;
  margin: 0;
}

.suggestions {
  margin-top: var(--space-6);
}

.suggestionsLabel {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin: 0 0 var(--space-3) 0;
}

.suggestionsList {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  justify-content: center;
}

.suggestionChip {
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-primary);
  background-color: var(--color-primary-bg);
  border-radius: var(--radius-full);
  text-decoration: none;
  transition: background-color 0.15s;
}

.suggestionChip:hover {
  background-color: var(--color-primary-bg-hover);
}
```

### Empty Notifications

```tsx
// components/notifications/EmptyNotifications.tsx
import styles from './EmptyNotifications.module.css';
import { Bell } from 'lucide-react';
import Link from 'next/link';

export function EmptyNotifications() {
  return (
    <div className={styles.container}>
      <Bell className={styles.icon} />
      <h3 className={styles.title}>No notifications</h3>
      <p className={styles.message}>
        You're all caught up! Follow topics to get notified about new stories.
      </p>
      <Link href="/topics" className={styles.link}>
        Browse topics
      </Link>
    </div>
  );
}
```

### Empty Following

```tsx
// components/topics/EmptyFollowing.tsx
import styles from './EmptyFollowing.module.css';
import { Hash } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import Link from 'next/link';

export function EmptyFollowing() {
  return (
    <div className={styles.container}>
      <div className={styles.iconWrapper}>
        <Hash className={styles.icon} />
      </div>
      <h3 className={styles.title}>Not following any topics</h3>
      <p className={styles.message}>
        Follow topics you're interested in to personalize your feed and get
        notified about new discoveries.
      </p>
      <div className={styles.topicSuggestions}>
        <p className={styles.label}>Popular topics:</p>
        <div className={styles.topics}>
          {['Climate', 'AI', 'Space', 'Health', 'Physics'].map((topic) => (
            <Link
              key={topic}
              href={`/topic/${topic.toLowerCase()}`}
              className={styles.topicChip}
            >
              {topic}
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
```

---

## Loading States

### Skeleton Components

```tsx
// components/ui/Skeleton.tsx
import styles from './Skeleton.module.css';

interface SkeletonProps {
  variant?: 'text' | 'circular' | 'rectangular';
  width?: string | number;
  height?: string | number;
  className?: string;
}

export function Skeleton({
  variant = 'text',
  width,
  height,
  className,
}: SkeletonProps) {
  return (
    <div
      className={`${styles.skeleton} ${styles[variant]} ${className || ''}`}
      style={{ width, height }}
    />
  );
}
```

```css
/* Skeleton.module.css */
.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-skeleton-base) 25%,
    var(--color-skeleton-highlight) 50%,
    var(--color-skeleton-base) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

.text {
  height: 1em;
  border-radius: var(--radius-sm);
}

.circular {
  border-radius: 50%;
}

.rectangular {
  border-radius: var(--radius-md);
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* Color tokens */
:root {
  --color-skeleton-base: #e2e8f0;
  --color-skeleton-highlight: #f1f5f9;
}

@media (prefers-color-scheme: dark) {
  :root {
    --color-skeleton-base: #2d3748;
    --color-skeleton-highlight: #4a5568;
  }
}
```

### Feed Loading Skeleton

```tsx
// components/feed/FeedSkeleton.tsx
import styles from './FeedSkeleton.module.css';
import { Skeleton } from '@/components/ui/Skeleton';

export function FeedSkeleton() {
  return (
    <div className={styles.container}>
      {/* Featured story skeleton */}
      <div className={styles.featured}>
        <Skeleton variant="rectangular" height={200} />
        <div className={styles.featuredContent}>
          <Skeleton width={80} height={20} />
          <Skeleton height={28} />
          <Skeleton height={28} width="80%" />
          <Skeleton height={16} />
          <Skeleton height={16} width="60%" />
        </div>
      </div>

      {/* Story cards skeleton */}
      <div className={styles.grid}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className={styles.card}>
            <Skeleton width={60} height={18} />
            <Skeleton height={22} />
            <Skeleton height={22} width="90%" />
            <Skeleton height={14} />
            <Skeleton height={14} width="70%" />
            <div className={styles.cardFooter}>
              <Skeleton width={100} height={14} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

### Story Page Loading Skeleton

```tsx
// components/story/StorySkeleton.tsx
import styles from './StorySkeleton.module.css';
import { Skeleton } from '@/components/ui/Skeleton';

export function StorySkeleton() {
  return (
    <article className={styles.container}>
      {/* Header */}
      <header className={styles.header}>
        <Skeleton width={80} height={24} />
        <Skeleton height={36} />
        <Skeleton height={36} width="90%" />
        <div className={styles.meta}>
          <Skeleton width={120} height={16} />
          <Skeleton width={80} height={16} />
        </div>
      </header>

      {/* Takeaway box */}
      <div className={styles.takeaway}>
        <Skeleton width={100} height={18} />
        <Skeleton height={20} />
        <Skeleton height={20} />
        <Skeleton height={20} width="60%" />
      </div>

      {/* Sources */}
      <div className={styles.sources}>
        <Skeleton width={80} height={18} />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className={styles.sourceCard}>
            <div className={styles.sourceHeader}>
              <Skeleton variant="circular" width={32} height={32} />
              <Skeleton width={100} height={16} />
            </div>
            <Skeleton height={18} />
            <Skeleton height={14} />
            <Skeleton height={14} width="80%" />
          </div>
        ))}
      </div>
    </article>
  );
}
```

### Button Loading State

```tsx
// Example usage
<Button loading disabled>
  <Spinner size="small" />
  Saving...
</Button>

// Spinner component
export function Spinner({ size = 'medium' }: { size?: 'small' | 'medium' | 'large' }) {
  const sizes = {
    small: 14,
    medium: 20,
    large: 28,
  };

  return (
    <svg
      className={styles.spinner}
      width={sizes[size]}
      height={sizes[size]}
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className={styles.track}
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
      />
      <circle
        className={styles.progress}
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}
```

```css
/* Spinner.module.css */
.spinner {
  animation: rotate 1s linear infinite;
}

.track {
  opacity: 0.25;
}

.progress {
  stroke-dasharray: 60;
  stroke-dashoffset: 45;
  animation: dash 1s ease-in-out infinite;
}

@keyframes rotate {
  100% {
    transform: rotate(360deg);
  }
}

@keyframes dash {
  0% {
    stroke-dashoffset: 60;
  }
  50% {
    stroke-dashoffset: 15;
  }
  100% {
    stroke-dashoffset: 60;
  }
}
```

---

## Form Validation States

### Input Error State

```tsx
// components/ui/Input.tsx (with error state)
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export function Input({ label, error, hint, id, ...props }: InputProps) {
  const inputId = id || useId();
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;

  return (
    <div className={styles.field}>
      {label && (
        <label htmlFor={inputId} className={styles.label}>
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`${styles.input} ${error ? styles.inputError : ''}`}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error ? errorId : hint ? hintId : undefined}
        {...props}
      />
      {error && (
        <p id={errorId} className={styles.error} role="alert">
          <AlertCircle size={14} />
          {error}
        </p>
      )}
      {hint && !error && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
    </div>
  );
}
```

```css
/* Input error styles */
.inputError {
  border-color: var(--color-error);
  background-color: var(--color-error-bg);
}

.inputError:focus {
  border-color: var(--color-error);
  box-shadow: 0 0 0 3px var(--color-error-ring);
}

.error {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-error);
}

.hint {
  margin-top: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}
```

### Form-Level Error

```tsx
// components/forms/FormError.tsx
import styles from './FormError.module.css';
import { AlertTriangle } from 'lucide-react';

interface FormErrorProps {
  title?: string;
  message: string;
  onDismiss?: () => void;
}

export function FormError({ title = 'Error', message, onDismiss }: FormErrorProps) {
  return (
    <div className={styles.container} role="alert">
      <AlertTriangle className={styles.icon} />
      <div className={styles.content}>
        <p className={styles.title}>{title}</p>
        <p className={styles.message}>{message}</p>
      </div>
      {onDismiss && (
        <button
          className={styles.dismiss}
          onClick={onDismiss}
          aria-label="Dismiss error"
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}
```

---

## Offline-Aware States

### Offline Banner

```tsx
// components/OfflineBanner.tsx
'use client';

import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import styles from './OfflineBanner.module.css';
import { WifiOff } from 'lucide-react';

export function OfflineBanner() {
  const isOnline = useOnlineStatus();

  if (isOnline) return null;

  return (
    <div className={styles.banner} role="status" aria-live="polite">
      <WifiOff size={16} />
      <span>You're offline. Some features may be limited.</span>
    </div>
  );
}
```

```css
/* OfflineBanner.module.css */
.banner {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background-color: var(--color-warning-bg);
  color: var(--color-warning-text);
  font-size: var(--text-sm);
  font-weight: 500;
  z-index: var(--z-banner);
  animation: slideUp 0.3s ease-out;
}

@keyframes slideUp {
  from {
    transform: translateY(100%);
  }
  to {
    transform: translateY(0);
  }
}

/* Account for safe area on iOS */
@supports (padding-bottom: env(safe-area-inset-bottom)) {
  .banner {
    padding-bottom: calc(var(--space-3) + env(safe-area-inset-bottom));
  }
}
```

### Offline-Disabled Action

```tsx
// components/OfflineDisabled.tsx
import { useOnlineStatus } from '@/hooks/useOnlineStatus';
import { Tooltip } from '@/components/ui/Tooltip';

interface OfflineDisabledProps {
  children: React.ReactElement;
  action?: string;
}

export function OfflineDisabled({ children, action = 'This action' }: OfflineDisabledProps) {
  const isOnline = useOnlineStatus();

  if (isOnline) {
    return children;
  }

  return (
    <Tooltip content={`${action} requires an internet connection`}>
      {React.cloneElement(children, {
        disabled: true,
        'aria-disabled': true,
        onClick: (e: React.MouseEvent) => e.preventDefault(),
      })}
    </Tooltip>
  );
}

// Usage
<OfflineDisabled action="Searching">
  <Button onClick={handleSearch}>Search</Button>
</OfflineDisabled>
```

---

## Error Boundary

```tsx
// components/ErrorBoundary.tsx
'use client';

import { Component, ErrorInfo, ReactNode } from 'react';
import { InlineError } from './errors/InlineError';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    this.props.onError?.(error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <InlineError
          message="Something went wrong loading this content."
          onRetry={() => this.setState({ hasError: false })}
        />
      );
    }

    return this.props.children;
  }
}

// Usage
<ErrorBoundary
  fallback={<InlineError message="Failed to load sources" />}
  onError={(error) => trackError(error)}
>
  <SourcesList sources={sources} />
</ErrorBoundary>
```

---

## Illustrations

SVG illustrations should be stored in `public/illustrations/` and imported as React components.

### Illustration Guidelines

| State | Illustration | Colors | Animation |
|-------|-------------|--------|-----------|
| 404 Not Found | Telescope + empty stars | Primary blue, muted | Stars twinkling |
| 500 Server Error | Broken beaker | Error orange, muted | None |
| Offline | Cloud with disconnect | Gray | Subtle pulse |
| Maintenance | Microscope + wrench | Primary blue, yellow | None |
| Empty Feed | Newspaper stack | Gray | None |
| Empty Saved | Bookmark | Gray | None |
| Empty Search | Magnifying glass | Gray | None |
| Rate Limited | Speedometer | Warning yellow | None |

---

## Copy Guidelines

### Do

- Use plain, friendly language
- Be specific about what went wrong
- Suggest a clear next action
- Keep messages short (under 2 sentences)

### Don't

- Use technical jargon ("500 Internal Server Error")
- Blame the user ("You did something wrong")
- Be vague ("An error occurred")
- Use all caps or exclamation marks for errors

### Example Copies

| Scenario | Bad | Good |
|----------|-----|------|
| API timeout | "Request timed out" | "This is taking longer than expected. Please try again." |
| Invalid input | "Validation error" | "Please enter a valid email address" |
| No permission | "403 Forbidden" | "You don't have access to this page" |
| Rate limited | "Too many requests" | "You're making requests too quickly. Please wait a moment." |
| Offline save | "Cannot save offline" | "Saving requires an internet connection. We'll save it when you're back online." |
