# Frontend Components — Curious Now

This document specifies the complete component hierarchy, props interfaces, and implementation patterns. It maps the design system in `design_docs/stage3.md` to concrete React components.

---

## 1) Component Design Principles

### 1.1 Rules

1. **Composition over configuration** — Small, focused components combined via composition
2. **Props are the API** — Well-typed props with sensible defaults
3. **Server-first** — Default to Server Components; add `'use client'` only when needed
4. **Design token adherence** — All styling uses CSS variables from design tokens
5. **Accessibility built-in** — ARIA attributes, keyboard support, focus management

### 1.2 Component categories

| Category | Purpose | Client/Server |
|----------|---------|---------------|
| `ui/` | Design system primitives | Client |
| `layout/` | Page structure | Server (mostly) |
| `feed/` | Feed-specific components | Mixed |
| `story/` | StoryCluster page components | Mixed |
| `topic/` | Topic page components | Mixed |
| `search/` | Search components | Client |
| `auth/` | Authentication components | Client |
| `shared/` | Cross-cutting components | Mixed |

---

## 2) Base UI Components (`components/ui/`)

### 2.1 Button

```tsx
// components/ui/Button/Button.tsx
'use client';

import { forwardRef } from 'react';
import { clsx } from 'clsx';
import styles from './Button.module.css';

type ButtonVariant = 'primary' | 'secondary' | 'tertiary';
type ButtonSize = 'sm' | 'md';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      isLoading = false,
      disabled,
      leftIcon,
      rightIcon,
      children,
      className,
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={clsx(
          styles.button,
          styles[variant],
          styles[size],
          isLoading && styles.loading,
          className
        )}
        {...props}
      >
        {isLoading ? (
          <span className={styles.spinner} aria-hidden="true" />
        ) : leftIcon ? (
          <span className={styles.icon}>{leftIcon}</span>
        ) : null}
        <span className={styles.label}>{children}</span>
        {rightIcon && !isLoading && (
          <span className={styles.icon}>{rightIcon}</span>
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';
```

```css
/* components/ui/Button/Button.module.css */
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--s-2);
  border: none;
  cursor: pointer;
  font-family: var(--font-ui);
  font-weight: 600;
  transition: background-color var(--t-fast) var(--ease),
              border-color var(--t-fast) var(--ease);
}

.button:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

/* Sizes */
.md {
  height: 44px;
  padding: 0 var(--s-4);
  border-radius: var(--r-md);
  font-size: 16px;
}

.sm {
  height: 36px;
  padding: 0 var(--s-3);
  border-radius: var(--r-sm);
  font-size: 14px;
}

/* Variants */
.primary {
  background-color: var(--primary);
  color: var(--surface-1);
}

.primary:hover:not(:disabled) {
  background-color: var(--primary-hover);
}

.secondary {
  background-color: transparent;
  border: var(--border-1);
  color: var(--text-1);
}

.secondary:hover:not(:disabled) {
  background-color: var(--surface-2);
}

.tertiary {
  background-color: transparent;
  color: var(--primary);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.tertiary:hover:not(:disabled) {
  color: var(--primary-hover);
}

/* Loading */
.loading {
  pointer-events: none;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.icon {
  display: flex;
  flex-shrink: 0;
}
```

### 2.2 Input

```tsx
// components/ui/Input/Input.tsx
'use client';

import { forwardRef } from 'react';
import { clsx } from 'clsx';
import styles from './Input.module.css';

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, id, className, ...props }, ref) => {
    const inputId = id || props.name;

    return (
      <div className={clsx(styles.wrapper, className)}>
        {label && (
          <label htmlFor={inputId} className={styles.label}>
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={clsx(styles.input, error && styles.error)}
          aria-invalid={!!error}
          aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
          {...props}
        />
        {error && (
          <p id={`${inputId}-error`} className={styles.errorText} role="alert">
            {error}
          </p>
        )}
        {hint && !error && (
          <p id={`${inputId}-hint`} className={styles.hint}>
            {hint}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';
```

```css
/* components/ui/Input/Input.module.css */
.wrapper {
  display: flex;
  flex-direction: column;
  gap: var(--s-1);
}

.label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-1);
}

.input {
  height: 44px;
  padding: 0 var(--s-3);
  border: var(--border-1);
  border-radius: var(--r-md);
  background-color: var(--surface-1);
  font-family: var(--font-ui);
  font-size: 16px;
  color: var(--text-1);
  transition: border-color var(--t-fast) var(--ease);
}

.input::placeholder {
  color: var(--text-3);
}

.input:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--border) 70%, var(--text-3));
}

.input:focus {
  outline: none;
  border-color: color-mix(in srgb, var(--primary) 55%, var(--border));
}

.input:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.input.error {
  border-color: var(--danger);
}

.errorText {
  font-size: 13px;
  color: var(--danger);
}

.hint {
  font-size: 13px;
  color: var(--text-3);
}
```

### 2.3 Badge

```tsx
// components/ui/Badge/Badge.tsx
import { clsx } from 'clsx';
import styles from './Badge.module.css';

type BadgeVariant = 'default' | 'preprint' | 'peer_reviewed' | 'press_release' | 'news' | 'report';

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

export function Badge({ variant = 'default', children, className }: BadgeProps) {
  return (
    <span className={clsx(styles.badge, styles[variant], className)}>
      {children}
    </span>
  );
}

// Convenience component for content type badges
export function ContentTypeBadge({ type }: { type: string }) {
  const labels: Record<string, string> = {
    preprint: 'Preprint',
    peer_reviewed: 'Peer Reviewed',
    press_release: 'Press Release',
    news: 'News',
    report: 'Report',
  };

  return (
    <Badge variant={type as BadgeVariant}>
      {labels[type] || type}
    </Badge>
  );
}
```

```css
/* components/ui/Badge/Badge.module.css */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: var(--font-ui);
  font-size: 12px;
  font-weight: 500;
  line-height: 1.3;
  white-space: nowrap;
}

.default {
  background-color: var(--surface-2);
  color: var(--text-2);
}

.preprint {
  background-color: color-mix(in srgb, var(--warning) 15%, var(--surface-1));
  color: var(--warning);
}

.peer_reviewed {
  background-color: color-mix(in srgb, var(--success) 15%, var(--surface-1));
  color: var(--success);
}

.press_release {
  background-color: color-mix(in srgb, var(--info) 15%, var(--surface-1));
  color: var(--info);
}

.news {
  background-color: var(--surface-2);
  color: var(--text-2);
}

.report {
  background-color: color-mix(in srgb, var(--accent) 15%, var(--surface-1));
  color: var(--accent);
}
```

### 2.4 Chip (Topic chip / Filter chip)

```tsx
// components/ui/Chip/Chip.tsx
'use client';

import { clsx } from 'clsx';
import styles from './Chip.module.css';

interface ChipProps {
  label: string;
  selected?: boolean;
  onClick?: () => void;
  href?: string;
  className?: string;
}

export function Chip({ label, selected = false, onClick, href, className }: ChipProps) {
  const Component = href ? 'a' : 'button';

  return (
    <Component
      href={href}
      onClick={onClick}
      className={clsx(styles.chip, selected && styles.selected, className)}
      aria-pressed={href ? undefined : selected}
    >
      {label}
    </Component>
  );
}
```

```css
/* components/ui/Chip/Chip.module.css */
.chip {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 var(--s-3);
  border: var(--border-1);
  border-radius: 999px;
  background-color: var(--surface-1);
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-2);
  text-decoration: none;
  cursor: pointer;
  transition: background-color var(--t-fast) var(--ease),
              border-color var(--t-fast) var(--ease);
}

.chip:hover {
  background-color: var(--surface-2);
}

.chip:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.selected {
  background-color: color-mix(in srgb, var(--primary) 10%, var(--surface-1));
  border-color: color-mix(in srgb, var(--primary) 30%, var(--border));
  color: var(--text-1);
}

@media (max-width: 767px) {
  .chip {
    height: 36px;
  }
}
```

### 2.5 Card

```tsx
// components/ui/Card/Card.tsx
import { clsx } from 'clsx';
import styles from './Card.module.css';

interface CardProps {
  children: React.ReactNode;
  as?: 'div' | 'article' | 'section';
  variant?: 'default' | 'featured';
  href?: string;
  className?: string;
}

export function Card({
  children,
  as: Component = 'div',
  variant = 'default',
  href,
  className,
}: CardProps) {
  const content = (
    <Component className={clsx(styles.card, styles[variant], className)}>
      {children}
    </Component>
  );

  if (href) {
    return (
      <a href={href} className={styles.cardLink}>
        {content}
      </a>
    );
  }

  return content;
}

// Sub-components for composition
Card.Image = function CardImage({
  src,
  alt,
  aspectRatio = '16/9',
}: {
  src: string;
  alt: string;
  aspectRatio?: string;
}) {
  return (
    <div className={styles.imageWrapper} style={{ aspectRatio }}>
      <img src={src} alt={alt} className={styles.image} loading="lazy" />
    </div>
  );
};

Card.Content = function CardContent({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={clsx(styles.content, className)}>{children}</div>;
};

Card.Title = function CardTitle({
  children,
  as: Component = 'h3',
}: {
  children: React.ReactNode;
  as?: 'h2' | 'h3' | 'h4';
}) {
  return <Component className={styles.title}>{children}</Component>;
};

Card.Meta = function CardMeta({ children }: { children: React.ReactNode }) {
  return <div className={styles.meta}>{children}</div>;
};
```

```css
/* components/ui/Card/Card.module.css */
.card {
  background-color: var(--surface-1);
  border: var(--border-1);
  border-radius: var(--r-md);
  overflow: hidden;
  transition: border-color var(--t-fast) var(--ease);
}

.cardLink {
  display: block;
  text-decoration: none;
  color: inherit;
}

.cardLink:hover .card {
  border-color: color-mix(in srgb, var(--border) 70%, var(--text-3));
}

.cardLink:hover .title {
  text-decoration: underline;
}

.cardLink:focus-visible .card {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.featured {
  border-radius: var(--r-lg);
}

.imageWrapper {
  position: relative;
  width: 100%;
  overflow: hidden;
}

.image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.content {
  padding: var(--s-4);
}

.featured .content {
  padding: var(--s-6);
}

.title {
  font-family: var(--font-ui);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.3;
  color: var(--text-1);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.featured .title {
  font-size: 24px;
}

.meta {
  display: flex;
  align-items: center;
  gap: var(--s-2);
  margin-top: var(--s-2);
  font-size: 13px;
  color: var(--text-3);
}
```

### 2.6 Modal

```tsx
// components/ui/Modal/Modal.tsx
'use client';

import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { clsx } from 'clsx';
import styles from './Modal.module.css';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: React.ReactNode;
  size?: 'sm' | 'md' | 'lg';
}

export function Modal({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
}: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const previousActiveElement = useRef<Element | null>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen) {
      previousActiveElement.current = document.activeElement;
      dialog.showModal();
    } else {
      dialog.close();
      (previousActiveElement.current as HTMLElement)?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (typeof window === 'undefined') return null;

  return createPortal(
    <dialog
      ref={dialogRef}
      className={clsx(styles.dialog, styles[size])}
      onClick={(e) => {
        if (e.target === dialogRef.current) onClose();
      }}
    >
      <div className={styles.content}>
        <div className={styles.header}>
          {title && <h2 className={styles.title}>{title}</h2>}
          <button
            onClick={onClose}
            className={styles.closeButton}
            aria-label="Close modal"
          >
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
        <div className={styles.body}>{children}</div>
      </div>
    </dialog>,
    document.body
  );
}
```

### 2.7 Toast

```tsx
// components/ui/Toast/Toast.tsx
'use client';

import { useEffect, useState } from 'react';
import { clsx } from 'clsx';
import styles from './Toast.module.css';

type ToastType = 'info' | 'success' | 'warning' | 'error';

interface ToastProps {
  message: string;
  type?: ToastType;
  duration?: number;
  onDismiss: () => void;
}

export function Toast({
  message,
  type = 'info',
  duration = 4000,
  onDismiss,
}: ToastProps) {
  const [isExiting, setIsExiting] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setIsExiting(true);
      setTimeout(onDismiss, 200);
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onDismiss]);

  return (
    <div
      className={clsx(styles.toast, styles[type], isExiting && styles.exiting)}
      role="alert"
      aria-live="polite"
    >
      <p className={styles.message}>{message}</p>
      <button
        onClick={() => {
          setIsExiting(true);
          setTimeout(onDismiss, 200);
        }}
        className={styles.dismissButton}
        aria-label="Dismiss"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  );
}
```

### 2.8 Tooltip

```tsx
// components/ui/Tooltip/Tooltip.tsx
'use client';

import { useState, useRef, useEffect } from 'react';
import { clsx } from 'clsx';
import styles from './Tooltip.module.css';

interface TooltipProps {
  content: React.ReactNode;
  children: React.ReactNode;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export function Tooltip({ content, children, position = 'top' }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const triggerRef = useRef<HTMLSpanElement>(null);

  return (
    <span
      ref={triggerRef}
      className={styles.trigger}
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
      onFocus={() => setIsVisible(true)}
      onBlur={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <span
          className={clsx(styles.tooltip, styles[position])}
          role="tooltip"
        >
          {content}
        </span>
      )}
    </span>
  );
}
```

### 2.9 Skeleton

```tsx
// components/ui/Skeleton/Skeleton.tsx
import { clsx } from 'clsx';
import styles from './Skeleton.module.css';

interface SkeletonProps {
  width?: string | number;
  height?: string | number;
  borderRadius?: string;
  className?: string;
}

export function Skeleton({
  width,
  height,
  borderRadius,
  className,
}: SkeletonProps) {
  return (
    <div
      className={clsx(styles.skeleton, className)}
      style={{ width, height, borderRadius }}
      aria-hidden="true"
    />
  );
}

Skeleton.Text = function SkeletonText({ lines = 1 }: { lines?: number }) {
  return (
    <div className={styles.textWrapper}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height="1em"
          width={i === lines - 1 ? '80%' : '100%'}
          borderRadius="4px"
        />
      ))}
    </div>
  );
};

Skeleton.Circle = function SkeletonCircle({ size = 40 }: { size?: number }) {
  return <Skeleton width={size} height={size} borderRadius="50%" />;
};
```

```css
/* components/ui/Skeleton/Skeleton.module.css */
.skeleton {
  background: linear-gradient(
    90deg,
    var(--surface-2) 25%,
    var(--surface-1) 50%,
    var(--surface-2) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s ease-in-out infinite;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.textWrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

@media (prefers-reduced-motion: reduce) {
  .skeleton {
    animation: none;
  }
}
```

---

## 3) Feed Components (`components/feed/`)

### 3.1 ClusterCard

```tsx
// components/feed/ClusterCard/ClusterCard.tsx
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import { Card } from '@/components/ui/Card';
import { Badge, ContentTypeBadge } from '@/components/ui/Badge';
import { Chip } from '@/components/ui/Chip';
import type { ClusterCard as ClusterCardType } from '@/types/api';
import styles from './ClusterCard.module.css';

interface ClusterCardProps {
  cluster: ClusterCardType;
  variant?: 'standard' | 'compact';
  showTopics?: boolean;
  showTakeaway?: boolean;
}

export function ClusterCard({
  cluster,
  variant = 'standard',
  showTopics = true,
  showTakeaway = false,
}: ClusterCardProps) {
  const {
    cluster_id,
    canonical_title,
    updated_at,
    distinct_source_count,
    top_topics,
    content_type_badges,
    takeaway,
    confidence_band,
    anti_hype_flags,
  } = cluster;

  return (
    <Card as="article" href={`/story/${cluster_id}`}>
      <Card.Content>
        {/* Meta row: badges + source count */}
        <div className={styles.metaRow}>
          <div className={styles.badges}>
            {content_type_badges?.map((type) => (
              <ContentTypeBadge key={type} type={type} />
            ))}
            {confidence_band && (
              <Badge variant="default">{confidence_band}</Badge>
            )}
          </div>
        </div>

        {/* Title */}
        <Card.Title>{canonical_title}</Card.Title>

        {/* Optional takeaway */}
        {showTakeaway && takeaway && (
          <p className={styles.takeaway}>{takeaway}</p>
        )}

        {/* Anti-hype flags */}
        {anti_hype_flags && anti_hype_flags.length > 0 && (
          <div className={styles.flags}>
            {anti_hype_flags.map((flag) => (
              <span key={flag} className={styles.flag}>
                {flag}
              </span>
            ))}
          </div>
        )}

        {/* Footer: sources + time + topics */}
        <Card.Meta>
          <span>{distinct_source_count} sources</span>
          <span aria-hidden="true">&middot;</span>
          <time dateTime={updated_at}>
            {formatDistanceToNow(new Date(updated_at), { addSuffix: true })}
          </time>
        </Card.Meta>

        {/* Topic chips */}
        {showTopics && top_topics && top_topics.length > 0 && (
          <div className={styles.topics}>
            {top_topics.slice(0, 2).map((topic) => (
              <Chip
                key={topic.topic_id}
                label={topic.name}
                href={`/topic/${topic.topic_id}`}
              />
            ))}
          </div>
        )}
      </Card.Content>
    </Card>
  );
}
```

```css
/* components/feed/ClusterCard/ClusterCard.module.css */
.metaRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--s-2);
}

.badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
}

.takeaway {
  margin: var(--s-2) 0;
  font-size: 15px;
  line-height: 1.5;
  color: var(--text-2);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.flags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-1);
  margin-top: var(--s-2);
}

.flag {
  font-size: 12px;
  color: var(--warning);
  background-color: color-mix(in srgb, var(--warning) 10%, var(--surface-1));
  padding: 2px 6px;
  border-radius: 4px;
}

.topics {
  display: flex;
  flex-wrap: wrap;
  gap: var(--s-2);
  margin-top: var(--s-3);
}
```

### 3.2 ClusterCardSkeleton

```tsx
// components/feed/ClusterCard/ClusterCardSkeleton.tsx
import { Card } from '@/components/ui/Card';
import { Skeleton } from '@/components/ui/Skeleton';
import styles from './ClusterCard.module.css';

export function ClusterCardSkeleton() {
  return (
    <Card as="div">
      <Card.Content>
        <div className={styles.metaRow}>
          <div className={styles.badges}>
            <Skeleton width={60} height={20} borderRadius="4px" />
            <Skeleton width={80} height={20} borderRadius="4px" />
          </div>
        </div>
        <Skeleton.Text lines={2} />
        <div style={{ marginTop: 'var(--s-3)' }}>
          <Skeleton width={150} height={16} />
        </div>
      </Card.Content>
    </Card>
  );
}
```

### 3.3 FeaturedHeroCard

```tsx
// components/feed/FeaturedHeroCard/FeaturedHeroCard.tsx
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import { ContentTypeBadge } from '@/components/ui/Badge';
import type { ClusterCard as ClusterCardType } from '@/types/api';
import styles from './FeaturedHeroCard.module.css';

interface FeaturedHeroCardProps {
  cluster: ClusterCardType;
  imageUrl?: string;
}

export function FeaturedHeroCard({ cluster, imageUrl }: FeaturedHeroCardProps) {
  const {
    cluster_id,
    canonical_title,
    updated_at,
    distinct_source_count,
    top_topics,
    content_type_badges,
    takeaway,
  } = cluster;

  return (
    <article className={styles.hero}>
      <Link href={`/story/${cluster_id}`} className={styles.link}>
        {imageUrl && (
          <div className={styles.imageWrapper}>
            <img
              src={imageUrl}
              alt=""
              className={styles.image}
              loading="eager"
            />
          </div>
        )}
        <div className={styles.content}>
          {top_topics && top_topics[0] && (
            <span className={styles.topicLabel}>{top_topics[0].name}</span>
          )}
          <h2 className={styles.title}>{canonical_title}</h2>
          {takeaway && <p className={styles.deck}>{takeaway}</p>}
          <div className={styles.meta}>
            <div className={styles.badges}>
              {content_type_badges?.slice(0, 2).map((type) => (
                <ContentTypeBadge key={type} type={type} />
              ))}
            </div>
            <span className={styles.metaText}>
              {distinct_source_count} sources &middot;{' '}
              {formatDistanceToNow(new Date(updated_at), { addSuffix: true })}
            </span>
          </div>
        </div>
      </Link>
    </article>
  );
}
```

```css
/* components/feed/FeaturedHeroCard/FeaturedHeroCard.module.css */
.hero {
  background-color: var(--surface-1);
  border: var(--border-1);
  border-radius: var(--r-lg);
  overflow: hidden;
  transition: border-color var(--t-fast) var(--ease);
}

.link {
  display: block;
  text-decoration: none;
  color: inherit;
}

.link:hover .hero {
  border-color: color-mix(in srgb, var(--border) 70%, var(--text-3));
}

.link:hover .title {
  text-decoration: underline;
}

.link:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

.imageWrapper {
  aspect-ratio: 16 / 9;
  overflow: hidden;
}

.image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.content {
  padding: var(--s-6);
}

.topicLabel {
  display: inline-block;
  margin-bottom: var(--s-2);
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 600;
  color: var(--primary);
  text-transform: capitalize;
}

.title {
  font-family: var(--font-ui);
  font-size: 32px;
  font-weight: 600;
  line-height: 1.15;
  color: var(--text-1);
  margin: 0 0 var(--s-3);
}

.deck {
  font-family: var(--font-article);
  font-size: 18px;
  line-height: 1.6;
  color: var(--text-2);
  margin: 0 0 var(--s-4);
}

.meta {
  display: flex;
  align-items: center;
  gap: var(--s-3);
}

.badges {
  display: flex;
  gap: var(--s-1);
}

.metaText {
  font-size: 13px;
  color: var(--text-3);
}

@media (max-width: 767px) {
  .content {
    padding: var(--s-4);
  }

  .title {
    font-size: 24px;
  }

  .deck {
    font-size: 16px;
  }
}
```

### 3.4 FeedTabs

```tsx
// components/feed/FeedTabs/FeedTabs.tsx
'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { clsx } from 'clsx';
import { useAuth } from '@/lib/context/AuthContext';
import styles from './FeedTabs.module.css';

const tabs = [
  { label: 'Latest', href: '/', tab: 'latest' },
  { label: 'Trending', href: '/trending', tab: 'trending' },
  { label: 'For You', href: '/for-you', tab: 'for_you', requiresAuth: true },
];

export function FeedTabs() {
  const pathname = usePathname();
  const { isAuthenticated } = useAuth();

  const activeTab = tabs.find((t) => t.href === pathname)?.tab || 'latest';

  return (
    <nav className={styles.tabs} aria-label="Feed tabs">
      <ul className={styles.tabList} role="tablist">
        {tabs.map((tab) => {
          if (tab.requiresAuth && !isAuthenticated) return null;

          const isActive = activeTab === tab.tab;

          return (
            <li key={tab.tab} role="presentation">
              <Link
                href={tab.href}
                className={clsx(styles.tab, isActive && styles.active)}
                role="tab"
                aria-selected={isActive}
              >
                {tab.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
```

```css
/* components/feed/FeedTabs/FeedTabs.module.css */
.tabs {
  border-bottom: var(--border-1);
  margin-bottom: var(--s-6);
}

.tabList {
  display: flex;
  gap: var(--s-6);
  list-style: none;
  margin: 0;
  padding: 0;
}

.tab {
  display: block;
  padding: var(--s-3) 0;
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 500;
  color: var(--text-2);
  text-decoration: none;
  border-bottom: 2px solid transparent;
  transition: color var(--t-fast) var(--ease),
              border-color var(--t-fast) var(--ease);
}

.tab:hover {
  color: var(--text-1);
}

.tab:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 2px;
}

.tab.active {
  color: var(--text-1);
  border-bottom-color: var(--primary);
}
```

### 3.5 LoadMoreButton

```tsx
// components/feed/LoadMoreButton/LoadMoreButton.tsx
'use client';

import { Button } from '@/components/ui/Button';
import styles from './LoadMoreButton.module.css';

interface LoadMoreButtonProps {
  onClick: () => void;
  isLoading: boolean;
  hasMore: boolean;
  currentCount: number;
  totalCount?: number;
}

export function LoadMoreButton({
  onClick,
  isLoading,
  hasMore,
  currentCount,
  totalCount,
}: LoadMoreButtonProps) {
  if (!hasMore) return null;

  return (
    <div className={styles.wrapper}>
      <Button
        variant="secondary"
        onClick={onClick}
        isLoading={isLoading}
        disabled={isLoading}
      >
        Load more stories
      </Button>
      {totalCount && (
        <p className={styles.count}>
          Showing {currentCount} of {totalCount}
        </p>
      )}
    </div>
  );
}
```

---

## 4) Story Components (`components/story/`)

### 4.1 TakeawayModule

```tsx
// components/story/TakeawayModule/TakeawayModule.tsx
import styles from './TakeawayModule.module.css';

interface TakeawayModuleProps {
  takeaway: string;
}

export function TakeawayModule({ takeaway }: TakeawayModuleProps) {
  return (
    <aside className={styles.module} aria-labelledby="takeaway-heading">
      <h2 id="takeaway-heading" className={styles.heading}>
        Takeaway
      </h2>
      <p className={styles.text}>{takeaway}</p>
    </aside>
  );
}
```

```css
/* components/story/TakeawayModule/TakeawayModule.module.css */
.module {
  background-color: var(--surface-2);
  border: var(--border-1);
  border-radius: var(--r-lg);
  padding: var(--s-4);
  margin: var(--s-6) 0;
}

.heading {
  font-family: var(--font-ui);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.02em;
  margin: 0 0 var(--s-2);
}

.text {
  font-family: var(--font-article);
  font-size: 18px;
  line-height: 1.6;
  color: var(--text-1);
  margin: 0;
}

@media (min-width: 768px) {
  .module {
    padding: var(--s-6);
  }

  .text {
    font-size: 19px;
  }
}
```

### 4.2 TrustBox

```tsx
// components/story/TrustBox/TrustBox.tsx
import { ContentTypeBadge } from '@/components/ui/Badge';
import styles from './TrustBox.module.css';

interface TrustBoxProps {
  contentTypeBreakdown: Record<string, number>;
  distinctSourceCount: number;
  confidenceBand?: 'early' | 'growing' | 'established' | null;
}

export function TrustBox({
  contentTypeBreakdown,
  distinctSourceCount,
  confidenceBand,
}: TrustBoxProps) {
  const confidenceLabels = {
    early: 'Early — Limited evidence, may change significantly',
    growing: 'Growing — Multiple sources, gaining clarity',
    established: 'Established — Consistent reporting over time',
  };

  return (
    <aside className={styles.trustBox} aria-labelledby="trust-heading">
      <h3 id="trust-heading" className={styles.heading}>
        Evidence summary
      </h3>

      {/* Confidence band */}
      {confidenceBand && (
        <div className={styles.confidence}>
          <span className={styles.confidenceLabel}>Confidence:</span>
          <span className={styles.confidenceValue}>
            {confidenceLabels[confidenceBand]}
          </span>
        </div>
      )}

      {/* Source diversity */}
      <div className={styles.row}>
        <span className={styles.label}>Independent sources:</span>
        <span className={styles.value}>{distinctSourceCount}</span>
      </div>

      {/* Content type breakdown */}
      <div className={styles.breakdown}>
        <span className={styles.label}>Source types:</span>
        <div className={styles.types}>
          {Object.entries(contentTypeBreakdown)
            .filter(([_, count]) => count > 0)
            .map(([type, count]) => (
              <div key={type} className={styles.typeItem}>
                <ContentTypeBadge type={type} />
                <span className={styles.typeCount}>{count}</span>
              </div>
            ))}
        </div>
      </div>
    </aside>
  );
}
```

### 4.3 EvidencePanel

```tsx
// components/story/EvidencePanel/EvidencePanel.tsx
import Link from 'next/link';
import { formatDistanceToNow } from 'date-fns';
import type { EvidenceItem } from '@/types/api';
import styles from './EvidencePanel.module.css';

interface EvidencePanelProps {
  evidence: Record<string, EvidenceItem[]>;
}

const typeOrder = ['peer_reviewed', 'preprint', 'report', 'press_release', 'news'];
const typeLabels: Record<string, string> = {
  peer_reviewed: 'Peer Reviewed',
  preprint: 'Preprints',
  report: 'Reports',
  press_release: 'Press Releases',
  news: 'News Coverage',
};

export function EvidencePanel({ evidence }: EvidencePanelProps) {
  const sortedTypes = typeOrder.filter((type) => evidence[type]?.length > 0);

  return (
    <section className={styles.panel} aria-labelledby="evidence-heading">
      <h2 id="evidence-heading" className={styles.heading}>
        Evidence &amp; Sources
      </h2>

      {sortedTypes.map((type) => (
        <div key={type} className={styles.group}>
          <h3 className={styles.groupHeading}>
            {typeLabels[type]} ({evidence[type].length})
          </h3>
          <ul className={styles.list}>
            {evidence[type].map((item) => (
              <li key={item.item_id} className={styles.item}>
                <a
                  href={item.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.itemLink}
                >
                  <span className={styles.itemTitle}>{item.title}</span>
                  <span className={styles.itemMeta}>
                    {item.source.name}
                    {item.published_at && (
                      <>
                        {' · '}
                        {formatDistanceToNow(new Date(item.published_at), {
                          addSuffix: true,
                        })}
                      </>
                    )}
                  </span>
                </a>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>
  );
}
```

### 4.4 GlossaryTooltip

```tsx
// components/story/GlossaryTooltip/GlossaryTooltip.tsx
'use client';

import { useState } from 'react';
import { Tooltip } from '@/components/ui/Tooltip';
import type { GlossaryEntry } from '@/types/api';
import styles from './GlossaryTooltip.module.css';

interface GlossaryTooltipProps {
  term: string;
  entry: GlossaryEntry;
}

export function GlossaryTooltip({ term, entry }: GlossaryTooltipProps) {
  return (
    <Tooltip
      content={
        <div className={styles.content}>
          <strong className={styles.term}>{entry.term}</strong>
          <p className={styles.definition}>{entry.definition_short}</p>
        </div>
      }
    >
      <span className={styles.trigger} tabIndex={0} role="button">
        {term}
      </span>
    </Tooltip>
  );
}
```

```css
/* components/story/GlossaryTooltip/GlossaryTooltip.module.css */
.trigger {
  border-bottom: 1px dotted var(--text-3);
  cursor: help;
}

.trigger:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 2px;
}

.content {
  max-width: 280px;
}

.term {
  display: block;
  font-weight: 600;
  margin-bottom: var(--s-1);
}

.definition {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
}
```

### 4.5 StoryActions

```tsx
// components/story/StoryActions/StoryActions.tsx
'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { useAuth } from '@/lib/context/AuthContext';
import { useToast } from '@/lib/hooks/useToast';
import { saveCluster, watchCluster } from '@/lib/api/user';
import styles from './StoryActions.module.css';

interface StoryActionsProps {
  clusterId: string;
  isSaved?: boolean;
  isWatched?: boolean;
}

export function StoryActions({
  clusterId,
  isSaved: initialSaved = false,
  isWatched: initialWatched = false,
}: StoryActionsProps) {
  const { isAuthenticated } = useAuth();
  const { showToast } = useToast();
  const [isSaved, setIsSaved] = useState(initialSaved);
  const [isWatched, setIsWatched] = useState(initialWatched);
  const [isLoading, setIsLoading] = useState(false);

  const handleSave = async () => {
    if (!isAuthenticated) {
      showToast('Sign in to save stories', 'info');
      return;
    }

    setIsLoading(true);
    try {
      await saveCluster(clusterId, !isSaved);
      setIsSaved(!isSaved);
      showToast(isSaved ? 'Removed from saved' : 'Saved to reading list', 'success');
    } catch {
      showToast('Failed to save', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleWatch = async () => {
    if (!isAuthenticated) {
      showToast('Sign in to watch stories', 'info');
      return;
    }

    setIsLoading(true);
    try {
      await watchCluster(clusterId, !isWatched);
      setIsWatched(!isWatched);
      showToast(
        isWatched ? 'Stopped watching' : "You'll be notified of updates",
        'success'
      );
    } catch {
      showToast('Failed to update watch', 'error');
    } finally {
      setIsLoading(false);
    }
  };

  const handleShare = async () => {
    const url = window.location.href;

    if (navigator.share) {
      try {
        await navigator.share({ url });
      } catch {
        // User cancelled
      }
    } else {
      await navigator.clipboard.writeText(url);
      showToast('Link copied to clipboard', 'success');
    }
  };

  return (
    <div className={styles.actions}>
      <Button
        variant="secondary"
        size="sm"
        onClick={handleSave}
        disabled={isLoading}
        aria-pressed={isSaved}
      >
        {isSaved ? 'Saved' : 'Save'}
      </Button>
      <Button
        variant="secondary"
        size="sm"
        onClick={handleWatch}
        disabled={isLoading}
        aria-pressed={isWatched}
      >
        {isWatched ? 'Watching' : 'Watch'}
      </Button>
      <Button variant="tertiary" size="sm" onClick={handleShare}>
        Share
      </Button>
    </div>
  );
}
```

### 4.6 UpdateLog

```tsx
// components/story/UpdateLog/UpdateLog.tsx
import { formatDistanceToNow } from 'date-fns';
import type { ClusterUpdateEntry } from '@/types/api';
import styles from './UpdateLog.module.css';

interface UpdateLogProps {
  updates: ClusterUpdateEntry[];
}

export function UpdateLog({ updates }: UpdateLogProps) {
  if (!updates || updates.length === 0) return null;

  return (
    <section className={styles.log} aria-labelledby="updates-heading">
      <h2 id="updates-heading" className={styles.heading}>
        What Changed
      </h2>

      <ul className={styles.list}>
        {updates.map((update, index) => (
          <li key={index} className={styles.entry}>
            <time className={styles.time} dateTime={update.created_at}>
              {formatDistanceToNow(new Date(update.created_at), {
                addSuffix: true,
              })}
            </time>
            <span className={styles.type}>{update.change_type}</span>
            <p className={styles.summary}>{update.summary}</p>

            {update.diff && (
              <div className={styles.diff}>
                {update.diff.previously && update.diff.previously.length > 0 && (
                  <div className={styles.diffSection}>
                    <strong>Previously:</strong>
                    <ul>
                      {update.diff.previously.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {update.diff.now && update.diff.now.length > 0 && (
                  <div className={styles.diffSection}>
                    <strong>Now:</strong>
                    <ul>
                      {update.diff.now.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {update.diff.because && update.diff.because.length > 0 && (
                  <div className={styles.diffSection}>
                    <strong>Because:</strong>
                    <ul>
                      {update.diff.because.map((item, i) => (
                        <li key={i}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
```

---

## 5) Layout Components (`components/layout/`)

### 5.1 Header

```tsx
// components/layout/Header/Header.tsx
'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/context/AuthContext';
import { Button } from '@/components/ui/Button';
import { SearchModal } from '@/components/layout/SearchModal';
import { MobileNav } from '@/components/layout/MobileNav';
import styles from './Header.module.css';

export function Header() {
  const { isAuthenticated, user } = useAuth();
  const [isScrolled, setIsScrolled] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isMobileNavOpen, setIsMobileNavOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10);
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <>
      <header className={`${styles.header} ${isScrolled ? styles.scrolled : ''}`}>
        <div className={styles.container}>
          {/* Mobile menu button */}
          <button
            className={styles.menuButton}
            onClick={() => setIsMobileNavOpen(true)}
            aria-label="Open menu"
          >
            <MenuIcon />
          </button>

          {/* Logo */}
          <Link href="/" className={styles.logo}>
            Curious Now
          </Link>

          {/* Desktop navigation */}
          <nav className={styles.nav} aria-label="Main navigation">
            <Link href="/" className={styles.navLink}>
              Latest
            </Link>
            <Link href="/trending" className={styles.navLink}>
              Trending
            </Link>
            <Link href="/topics" className={styles.navLink}>
              Topics
            </Link>
          </nav>

          {/* Actions */}
          <div className={styles.actions}>
            <button
              className={styles.iconButton}
              onClick={() => setIsSearchOpen(true)}
              aria-label="Search"
            >
              <SearchIcon />
            </button>

            {isAuthenticated ? (
              <>
                <Link href="/saved" className={styles.iconButton} aria-label="Saved">
                  <BookmarkIcon />
                </Link>
                <Link href="/settings" className={styles.iconButton} aria-label="Settings">
                  <UserIcon />
                </Link>
              </>
            ) : (
              <Button variant="primary" size="sm" as={Link} href="/auth/login">
                Sign in
              </Button>
            )}
          </div>
        </div>
      </header>

      {/* Search modal */}
      <SearchModal isOpen={isSearchOpen} onClose={() => setIsSearchOpen(false)} />

      {/* Mobile navigation */}
      <MobileNav isOpen={isMobileNavOpen} onClose={() => setIsMobileNavOpen(false)} />
    </>
  );
}

// Icon components (simplified)
function MenuIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M3 12h18M3 6h18M3 18h18" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function BookmarkIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="7" r="4" />
      <path d="M5.5 21a8.5 8.5 0 0 1 13 0" />
    </svg>
  );
}
```

```css
/* components/layout/Header/Header.module.css */
.header {
  position: sticky;
  top: 0;
  z-index: 100;
  background-color: var(--surface-1);
  transition: border-color var(--t-fast) var(--ease),
              height var(--t-fast) var(--ease);
}

.scrolled {
  border-bottom: var(--border-1);
}

.container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 var(--s-4);
  height: 72px;
}

.scrolled .container {
  height: 56px;
}

.menuButton {
  display: none;
  width: 44px;
  height: 44px;
  padding: 0;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text-1);
}

.logo {
  font-family: var(--font-ui);
  font-size: 20px;
  font-weight: 700;
  color: var(--text-1);
  text-decoration: none;
}

.nav {
  display: flex;
  gap: var(--s-6);
}

.navLink {
  font-family: var(--font-ui);
  font-size: 15px;
  font-weight: 500;
  color: var(--text-2);
  text-decoration: none;
  transition: color var(--t-fast) var(--ease);
}

.navLink:hover {
  color: var(--text-1);
}

.navLink:focus-visible {
  outline: var(--focus-ring);
  outline-offset: 4px;
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--s-2);
}

.iconButton {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: none;
  background: none;
  cursor: pointer;
  color: var(--text-2);
  border-radius: var(--r-sm);
  transition: background-color var(--t-fast) var(--ease);
}

.iconButton:hover {
  background-color: var(--surface-2);
  color: var(--text-1);
}

.iconButton:focus-visible {
  outline: var(--focus-ring);
  outline-offset: var(--focus-offset);
}

@media (max-width: 767px) {
  .container {
    height: 64px;
  }

  .menuButton {
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .nav {
    display: none;
  }

  .logo {
    position: absolute;
    left: 50%;
    transform: translateX(-50%);
  }
}
```

### 5.2 Footer

```tsx
// components/layout/Footer/Footer.tsx
import Link from 'next/link';
import styles from './Footer.module.css';

export function Footer() {
  return (
    <footer className={styles.footer}>
      <div className={styles.container}>
        <div className={styles.primary}>
          <Link href="/" className={styles.logo}>
            Curious Now
          </Link>
          <p className={styles.tagline}>
            Science news you can understand — then go deeper.
          </p>
        </div>

        <nav className={styles.nav} aria-label="Footer navigation">
          <div className={styles.navGroup}>
            <h3 className={styles.navHeading}>Explore</h3>
            <ul className={styles.navList}>
              <li><Link href="/">Latest</Link></li>
              <li><Link href="/trending">Trending</Link></li>
              <li><Link href="/topics">Topics</Link></li>
              <li><Link href="/search">Search</Link></li>
            </ul>
          </div>

          <div className={styles.navGroup}>
            <h3 className={styles.navHeading}>About</h3>
            <ul className={styles.navList}>
              <li><Link href="/about">About us</Link></li>
              <li><Link href="/how-we-source">How we source</Link></li>
              <li><Link href="/editorial-policy">Editorial policy</Link></li>
              <li><Link href="/corrections">Corrections</Link></li>
            </ul>
          </div>

          <div className={styles.navGroup}>
            <h3 className={styles.navHeading}>Legal</h3>
            <ul className={styles.navList}>
              <li><Link href="/privacy">Privacy policy</Link></li>
              <li><Link href="/terms">Terms of service</Link></li>
              <li><Link href="/contact">Contact</Link></li>
            </ul>
          </div>
        </nav>

        <div className={styles.bottom}>
          <p className={styles.copyright}>
            &copy; {new Date().getFullYear()} Curious Now. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
```

---

## 6) Page Templates

### 6.1 Home Page (Feed)

```tsx
// app/page.tsx
import { Suspense } from 'react';
import { getFeed } from '@/lib/api/feed';
import { FeedTabs } from '@/components/feed/FeedTabs';
import { FeaturedHeroCard } from '@/components/feed/FeaturedHeroCard';
import { ClusterCard } from '@/components/feed/ClusterCard';
import { ClusterCardSkeleton } from '@/components/feed/ClusterCard/ClusterCardSkeleton';
import { NewsletterCTA } from '@/components/shared/NewsletterCTA';
import styles from './page.module.css';

export const revalidate = 60; // Revalidate every 60 seconds

export default async function HomePage() {
  const feed = await getFeed({ tab: 'latest', page: 1, page_size: 20 });
  const [featured, ...rest] = feed.results;

  return (
    <main className={styles.main}>
      <FeedTabs />

      {/* Featured story */}
      {featured && (
        <section className={styles.featured}>
          <FeaturedHeroCard cluster={featured} />
        </section>
      )}

      {/* Today's stories */}
      <section className={styles.section}>
        <h2 className={styles.sectionHeading}>Today's stories</h2>
        <div className={styles.grid}>
          {rest.slice(0, 6).map((cluster) => (
            <ClusterCard key={cluster.cluster_id} cluster={cluster} />
          ))}
        </div>
      </section>

      {/* Newsletter CTA */}
      <NewsletterCTA />

      {/* More stories */}
      <section className={styles.section}>
        <h2 className={styles.sectionHeading}>More to explore</h2>
        <Suspense fallback={<FeedSkeleton />}>
          <FeedList initialData={rest.slice(6)} tab="latest" />
        </Suspense>
      </section>
    </main>
  );
}

function FeedSkeleton() {
  return (
    <div className={styles.grid}>
      {Array.from({ length: 6 }).map((_, i) => (
        <ClusterCardSkeleton key={i} />
      ))}
    </div>
  );
}
```

### 6.2 Story Page (StoryCluster)

```tsx
// app/story/[id]/page.tsx
import { Suspense } from 'react';
import { notFound } from 'next/navigation';
import { getCluster } from '@/lib/api/clusters';
import { TakeawayModule } from '@/components/story/TakeawayModule';
import { TrustBox } from '@/components/story/TrustBox';
import { EvidencePanel } from '@/components/story/EvidencePanel';
import { StoryActions } from '@/components/story/StoryActions';
import { UpdateLog } from '@/components/story/UpdateLog';
import { GlossaryTooltip } from '@/components/story/GlossaryTooltip';
import { RelatedStories } from '@/components/story/RelatedStories';
import { ReadingProgress } from '@/components/shared/ReadingProgress';
import { ContentTypeBadge } from '@/components/ui/Badge';
import { Chip } from '@/components/ui/Chip';
import { formatDistanceToNow } from 'date-fns';
import type { Metadata } from 'next';
import styles from './page.module.css';

interface StoryPageProps {
  params: { id: string };
}

export async function generateMetadata({ params }: StoryPageProps): Promise<Metadata> {
  try {
    const cluster = await getCluster(params.id);
    return {
      title: `${cluster.canonical_title} | Curious Now`,
      description: cluster.takeaway || cluster.canonical_title,
      openGraph: {
        title: cluster.canonical_title,
        description: cluster.takeaway || cluster.canonical_title,
        type: 'article',
      },
    };
  } catch {
    return { title: 'Story | Curious Now' };
  }
}

export default async function StoryPage({ params }: StoryPageProps) {
  const cluster = await getCluster(params.id);

  if (!cluster) {
    notFound();
  }

  return (
    <>
      <ReadingProgress />

      <article className={styles.article}>
        {/* Header */}
        <header className={styles.header}>
          <div className={styles.badges}>
            {cluster.content_type_breakdown &&
              Object.entries(cluster.content_type_breakdown)
                .filter(([_, count]) => count > 0)
                .map(([type]) => <ContentTypeBadge key={type} type={type} />)}
          </div>

          <h1 className={styles.title}>{cluster.canonical_title}</h1>

          <div className={styles.meta}>
            <span>{cluster.distinct_source_count} sources</span>
            <span>&middot;</span>
            <time dateTime={cluster.updated_at}>
              Updated {formatDistanceToNow(new Date(cluster.updated_at), { addSuffix: true })}
            </time>
          </div>

          {cluster.topics && cluster.topics.length > 0 && (
            <div className={styles.topics}>
              {cluster.topics.map((topic) => (
                <Chip
                  key={topic.topic_id}
                  label={topic.name}
                  href={`/topic/${topic.topic_id}`}
                />
              ))}
            </div>
          )}

          <StoryActions
            clusterId={cluster.cluster_id}
            isSaved={cluster.is_saved}
            isWatched={cluster.is_watched}
          />
        </header>

        {/* Takeaway */}
        {cluster.takeaway && <TakeawayModule takeaway={cluster.takeaway} />}

        {/* Anti-hype flags */}
        {cluster.anti_hype_flags && cluster.anti_hype_flags.length > 0 && (
          <aside className={styles.flags}>
            {cluster.anti_hype_flags.map((flag) => (
              <span key={flag} className={styles.flag}>
                {flag}
              </span>
            ))}
          </aside>
        )}

        {/* Main content */}
        <div className={styles.content}>
          {/* Intuition (default visible) */}
          {cluster.summary_intuition && (
            <section className={styles.section}>
              <h2 className={styles.sectionHeading}>What's happening</h2>
              <div className={styles.prose}>
                {cluster.summary_intuition}
              </div>
            </section>
          )}

          {/* Deep Dive (expandable) */}
          {cluster.summary_deep_dive && (
            <details className={styles.deepDive}>
              <summary className={styles.deepDiveSummary}>
                Go deeper: Methods & details
              </summary>
              <div className={styles.prose}>
                {cluster.summary_deep_dive}
              </div>

              {/* Assumptions & Limitations */}
              {((cluster.assumptions && cluster.assumptions.length > 0) ||
                (cluster.limitations && cluster.limitations.length > 0)) && (
                <div className={styles.caveats}>
                  {cluster.assumptions && cluster.assumptions.length > 0 && (
                    <div>
                      <h4>Key assumptions</h4>
                      <ul>
                        {cluster.assumptions.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {cluster.limitations && cluster.limitations.length > 0 && (
                    <div>
                      <h4>Limitations</h4>
                      <ul>
                        {cluster.limitations.map((item, i) => (
                          <li key={i}>{item}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </details>
          )}

          {/* What could change */}
          {cluster.what_could_change_this && cluster.what_could_change_this.length > 0 && (
            <section className={styles.section}>
              <h3 className={styles.sectionHeading}>What could change this?</h3>
              <ul className={styles.changeList}>
                {cluster.what_could_change_this.map((item, i) => (
                  <li key={i}>{item}</li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* Sidebar content */}
        <aside className={styles.sidebar}>
          <TrustBox
            contentTypeBreakdown={cluster.content_type_breakdown || {}}
            distinctSourceCount={cluster.distinct_source_count}
            confidenceBand={cluster.confidence_band}
          />
        </aside>

        {/* Evidence panel */}
        <EvidencePanel evidence={cluster.evidence} />

        {/* Update log */}
        <Suspense fallback={null}>
          <UpdateLogSection clusterId={params.id} />
        </Suspense>

        {/* Related stories */}
        <Suspense fallback={null}>
          <RelatedStories topicIds={cluster.topics?.map((t) => t.topic_id) || []} />
        </Suspense>
      </article>
    </>
  );
}

async function UpdateLogSection({ clusterId }: { clusterId: string }) {
  const { updates } = await getClusterUpdates(clusterId);
  return <UpdateLog updates={updates} />;
}
```

---

## 7) Component Checklist

### 7.1 Priority 1 (MVP)

- [x] `ui/Button`
- [x] `ui/Input`
- [x] `ui/Badge`
- [x] `ui/Chip`
- [x] `ui/Card`
- [x] `ui/Modal`
- [x] `ui/Toast`
- [x] `ui/Skeleton`
- [x] `layout/Header`
- [x] `layout/Footer`
- [x] `feed/ClusterCard`
- [x] `feed/FeaturedHeroCard`
- [x] `feed/FeedTabs`
- [x] `feed/LoadMoreButton`
- [x] `story/TakeawayModule`
- [x] `story/EvidencePanel`
- [x] `story/TrustBox`
- [x] `story/StoryActions`

### 7.2 Priority 2 (Stage 3-4)

- [ ] `ui/Tooltip` (enhanced)
- [ ] `story/GlossaryTooltip`
- [ ] `story/UpdateLog`
- [ ] `topic/LineageGraph`
- [ ] `shared/ReadingProgress`

### 7.3 Priority 3 (Stage 5+)

- [ ] `auth/LoginForm`
- [ ] `auth/AuthGuard`
- [ ] `search/SearchModal`
- [ ] `layout/MobileNav`
- [ ] `shared/NewsletterCTA`
- [ ] `shared/FeedbackButton`
