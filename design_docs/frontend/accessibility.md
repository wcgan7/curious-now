# Accessibility Specification

## Overview

This document specifies accessibility requirements and implementation patterns for Curious Now. The goal is WCAG 2.1 AA compliance, ensuring the platform is usable by people with various disabilities.

**Token note:** Canonical UI tokens (colors/spacing/radius) are defined in `design_docs/stage3.md`. Some snippets in this doc use generic `--color-*` / `--space-*` names; translate them to the canonical tokens or use the compat aliases in `design_docs/frontend_handoff.md`.

---

## Accessibility Standards

### Target Compliance

- **WCAG 2.1 Level AA** - Primary target
- **Section 508** - US federal accessibility
- **EN 301 549** - European accessibility standard

### Key Principles (POUR)

1. **Perceivable** - Information must be presentable in ways users can perceive
2. **Operable** - UI components must be operable by all users
3. **Understandable** - Information and UI operation must be understandable
4. **Robust** - Content must be robust enough for assistive technologies

---

## Color & Contrast

### Contrast Requirements

| Element | Minimum Ratio | Our Target |
|---------|--------------|------------|
| Normal text (< 18px) | 4.5:1 | 7:1 |
| Large text (≥ 18px bold, ≥ 24px) | 3:1 | 4.5:1 |
| UI components & graphics | 3:1 | 4.5:1 |
| Focus indicators | 3:1 | 4.5:1 |

### Color Palette Accessibility

```css
/* Light Mode - All pass WCAG AA */
:root {
  /* Text on white background */
  --color-text-primary: #1a202c;    /* 16.1:1 on white */
  --color-text-secondary: #4a5568;  /* 7.0:1 on white */
  --color-text-tertiary: #718096;   /* 4.6:1 on white */

  /* Primary blue */
  --color-primary: #1a4d7c;         /* 7.3:1 on white */
  --color-primary-dark: #143d63;    /* 9.5:1 on white */

  /* Accent teal */
  --color-accent: #1d6f6f;          /* 5.2:1 on white */

  /* Status colors */
  --color-error: #c53030;           /* 5.9:1 on white */
  --color-warning: #b7791f;         /* 4.6:1 on white */
  --color-success: #276749;         /* 5.5:1 on white */
}

/* Dark Mode */
@media (prefers-color-scheme: dark) {
  :root {
    /* Text on dark background (#1a202c) */
    --color-text-primary: #f7fafc;  /* 15.5:1 */
    --color-text-secondary: #cbd5e0; /* 10.3:1 */
    --color-text-tertiary: #a0aec0; /* 7.0:1 */

    /* Adjusted colors for dark backgrounds */
    --color-primary: #63b3ed;       /* 8.6:1 */
    --color-accent: #4fd1c5;        /* 9.4:1 */
  }
}
```

### Non-Color Indicators

Never rely on color alone to convey information:

```tsx
// Bad - color only
<span className={isError ? 'text-red' : 'text-green'}>
  {message}
</span>

// Good - color + icon + text
<span className={isError ? styles.error : styles.success}>
  {isError ? <AlertCircle aria-hidden /> : <CheckCircle aria-hidden />}
  <span>{isError ? 'Error: ' : 'Success: '}{message}</span>
</span>
```

---

## Keyboard Navigation

### Focus Management

```css
/* Global focus styles */
:focus {
  outline: none;
}

:focus-visible {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}

/* Focus ring color */
:root {
  --color-focus: #4299e1; /* Blue that works on both light/dark */
}

/* Custom focus for specific components */
.button:focus-visible {
  box-shadow: 0 0 0 3px var(--color-primary-ring);
}

.card:focus-visible {
  box-shadow: 0 0 0 3px var(--color-focus);
}
```

### Focus Order

Ensure logical tab order by:

1. Using semantic HTML (headers, nav, main, footer)
2. Avoiding positive `tabindex` values
3. Managing focus programmatically when needed

```tsx
// Focus management hook
export function useFocusManagement() {
  const focusRef = useRef<HTMLElement>(null);

  const setFocus = useCallback(() => {
    focusRef.current?.focus();
  }, []);

  const returnFocus = useCallback((previousElement: HTMLElement | null) => {
    previousElement?.focus();
  }, []);

  return { focusRef, setFocus, returnFocus };
}

// Usage in Modal
function Modal({ isOpen, onClose, children }) {
  const previousFocus = useRef<HTMLElement | null>(null);
  const { focusRef, setFocus, returnFocus } = useFocusManagement();

  useEffect(() => {
    if (isOpen) {
      previousFocus.current = document.activeElement as HTMLElement;
      setFocus();
    } else {
      returnFocus(previousFocus.current);
    }
  }, [isOpen]);

  return (
    <div
      ref={focusRef}
      role="dialog"
      aria-modal="true"
      tabIndex={-1}
    >
      {children}
    </div>
  );
}
```

### Skip Links

```tsx
// src/components/layout/SkipLinks.tsx
import styles from './SkipLinks.module.css';

export function SkipLinks() {
  return (
    <nav className={styles.skipLinks} aria-label="Skip links">
      <a href="#main-content" className={styles.skipLink}>
        Skip to main content
      </a>
      <a href="#main-navigation" className={styles.skipLink}>
        Skip to navigation
      </a>
      <a href="#search" className={styles.skipLink}>
        Skip to search
      </a>
    </nav>
  );
}
```

```css
/* SkipLinks.module.css */
.skipLinks {
  position: absolute;
  top: 0;
  left: 0;
  z-index: var(--z-skip-links);
}

.skipLink {
  position: absolute;
  transform: translateY(-100%);
  padding: var(--space-3) var(--space-4);
  background-color: var(--color-primary);
  color: white;
  font-weight: 600;
  text-decoration: none;
  transition: transform 0.2s;
}

.skipLink:focus {
  transform: translateY(0);
}
```

### Keyboard Shortcuts

```tsx
// src/hooks/useKeyboardShortcuts.ts
import { useEffect } from 'react';

interface Shortcut {
  key: string;
  ctrl?: boolean;
  shift?: boolean;
  alt?: boolean;
  action: () => void;
  description: string;
}

export function useKeyboardShortcuts(shortcuts: Shortcut[]) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger in input fields
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement
      ) {
        return;
      }

      for (const shortcut of shortcuts) {
        const keyMatch = e.key.toLowerCase() === shortcut.key.toLowerCase();
        const ctrlMatch = !!shortcut.ctrl === (e.ctrlKey || e.metaKey);
        const shiftMatch = !!shortcut.shift === e.shiftKey;
        const altMatch = !!shortcut.alt === e.altKey;

        if (keyMatch && ctrlMatch && shiftMatch && altMatch) {
          e.preventDefault();
          shortcut.action();
          return;
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [shortcuts]);
}

// Default shortcuts for the app
const globalShortcuts: Shortcut[] = [
  { key: '/', action: () => focusSearch(), description: 'Focus search' },
  { key: 'g', action: () => goHome(), description: 'Go to home' },
  { key: 's', action: () => goSaved(), description: 'Go to saved' },
  { key: '?', shift: true, action: () => showHelp(), description: 'Show shortcuts' },
];
```

---

## ARIA Patterns

### Buttons

```tsx
// Standard button
<button type="button" aria-label="Close modal">
  <X aria-hidden="true" />
</button>

// Toggle button
<button
  type="button"
  aria-pressed={isPressed}
  aria-label={isPressed ? 'Remove from saved' : 'Save story'}
>
  <Bookmark aria-hidden="true" />
</button>

// Loading button
<button type="submit" disabled={isLoading} aria-busy={isLoading}>
  {isLoading ? (
    <>
      <Spinner aria-hidden="true" />
      <span>Saving...</span>
    </>
  ) : (
    'Save'
  )}
</button>

// Button with expanded content
<button
  type="button"
  aria-expanded={isExpanded}
  aria-controls="panel-content"
>
  {isExpanded ? 'Show less' : 'Show more'}
</button>
```

### Navigation

```tsx
// Main navigation
<nav aria-label="Main navigation" id="main-navigation">
  <ul role="list">
    <li>
      <a href="/" aria-current={isHome ? 'page' : undefined}>
        Home
      </a>
    </li>
    <li>
      <a href="/saved" aria-current={isSaved ? 'page' : undefined}>
        Saved
      </a>
    </li>
  </ul>
</nav>

// Breadcrumb
<nav aria-label="Breadcrumb">
  <ol role="list">
    <li>
      <a href="/">Home</a>
    </li>
    <li aria-hidden="true">/</li>
    <li>
      <a href="/topic/climate">Climate</a>
    </li>
    <li aria-hidden="true">/</li>
    <li>
      <span aria-current="page">Story Title</span>
    </li>
  </ol>
</nav>

// Pagination
<nav aria-label="Pagination">
  <ul role="list">
    <li>
      <a
        href="/page/1"
        aria-label="Go to previous page"
        aria-disabled={currentPage === 1}
      >
        Previous
      </a>
    </li>
    <li>
      <a href="/page/1" aria-label="Page 1" aria-current={currentPage === 1 ? 'page' : undefined}>
        1
      </a>
    </li>
    {/* ... */}
    <li>
      <a href="/page/2" aria-label="Go to next page">
        Next
      </a>
    </li>
  </ul>
</nav>
```

### Tabs

```tsx
// src/components/ui/Tabs.tsx
interface TabsProps {
  tabs: Array<{ id: string; label: string; panel: React.ReactNode }>;
  defaultTab?: string;
}

export function Tabs({ tabs, defaultTab }: TabsProps) {
  const [activeTab, setActiveTab] = useState(defaultTab || tabs[0].id);
  const tablistRef = useRef<HTMLDivElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    let newIndex = index;

    switch (e.key) {
      case 'ArrowLeft':
        newIndex = index === 0 ? tabs.length - 1 : index - 1;
        break;
      case 'ArrowRight':
        newIndex = index === tabs.length - 1 ? 0 : index + 1;
        break;
      case 'Home':
        newIndex = 0;
        break;
      case 'End':
        newIndex = tabs.length - 1;
        break;
      default:
        return;
    }

    e.preventDefault();
    setActiveTab(tabs[newIndex].id);

    // Focus the new tab
    const tabButtons = tablistRef.current?.querySelectorAll('[role="tab"]');
    (tabButtons?.[newIndex] as HTMLElement)?.focus();
  };

  return (
    <div className={styles.tabs}>
      <div
        ref={tablistRef}
        role="tablist"
        aria-label="Content tabs"
        className={styles.tablist}
      >
        {tabs.map((tab, index) => (
          <button
            key={tab.id}
            role="tab"
            id={`tab-${tab.id}`}
            aria-selected={activeTab === tab.id}
            aria-controls={`panel-${tab.id}`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            className={styles.tab}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {tabs.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`panel-${tab.id}`}
          aria-labelledby={`tab-${tab.id}`}
          hidden={activeTab !== tab.id}
          tabIndex={0}
          className={styles.panel}
        >
          {tab.panel}
        </div>
      ))}
    </div>
  );
}
```

### Modal / Dialog

```tsx
// src/components/ui/Modal.tsx
import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import FocusTrap from 'focus-trap-react';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  description?: string;
}

export function Modal({ isOpen, onClose, title, children, description }: ModalProps) {
  const titleId = useId();
  const descId = useId();
  const previousFocus = useRef<HTMLElement | null>(null);

  // Store focus and handle escape key
  useEffect(() => {
    if (isOpen) {
      previousFocus.current = document.activeElement as HTMLElement;

      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === 'Escape') onClose();
      };
      document.addEventListener('keydown', handleEscape);
      return () => document.removeEventListener('keydown', handleEscape);
    } else {
      previousFocus.current?.focus();
    }
  }, [isOpen, onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = '';
      };
    }
  }, [isOpen]);

  if (!isOpen) return null;

  return createPortal(
    <FocusTrap>
      <div
        className={styles.overlay}
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descId : undefined}
        className={styles.modal}
      >
        <header className={styles.header}>
          <h2 id={titleId} className={styles.title}>
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close dialog"
            className={styles.closeButton}
          >
            <X aria-hidden="true" />
          </button>
        </header>
        {description && (
          <p id={descId} className={styles.description}>
            {description}
          </p>
        )}
        <div className={styles.content}>{children}</div>
      </div>
    </FocusTrap>,
    document.body
  );
}
```

### Accordion

```tsx
// src/components/ui/Accordion.tsx
interface AccordionItem {
  id: string;
  title: string;
  content: React.ReactNode;
}

export function Accordion({ items }: { items: AccordionItem[] }) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const toggleItem = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div className={styles.accordion}>
      {items.map((item) => {
        const isExpanded = expandedIds.has(item.id);
        const headerId = `accordion-header-${item.id}`;
        const panelId = `accordion-panel-${item.id}`;

        return (
          <div key={item.id} className={styles.item}>
            <h3>
              <button
                id={headerId}
                type="button"
                aria-expanded={isExpanded}
                aria-controls={panelId}
                onClick={() => toggleItem(item.id)}
                className={styles.trigger}
              >
                <span>{item.title}</span>
                <ChevronDown
                  className={`${styles.icon} ${isExpanded ? styles.iconExpanded : ''}`}
                  aria-hidden="true"
                />
              </button>
            </h3>
            <div
              id={panelId}
              role="region"
              aria-labelledby={headerId}
              hidden={!isExpanded}
              className={styles.panel}
            >
              {item.content}
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

### Tooltip

```tsx
// src/components/ui/Tooltip.tsx
import { useState, useRef, useId } from 'react';

interface TooltipProps {
  content: string;
  children: React.ReactElement;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

export function Tooltip({ content, children, position = 'top' }: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const tooltipId = useId();
  const timeoutRef = useRef<NodeJS.Timeout>();

  const showTooltip = () => {
    clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => setIsVisible(true), 200);
  };

  const hideTooltip = () => {
    clearTimeout(timeoutRef.current);
    setIsVisible(false);
  };

  return (
    <div
      className={styles.container}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onFocus={showTooltip}
      onBlur={hideTooltip}
    >
      {React.cloneElement(children, {
        'aria-describedby': isVisible ? tooltipId : undefined,
      })}
      {isVisible && (
        <div
          id={tooltipId}
          role="tooltip"
          className={`${styles.tooltip} ${styles[position]}`}
        >
          {content}
        </div>
      )}
    </div>
  );
}
```

### Live Regions

```tsx
// Polite announcement (non-urgent)
<div aria-live="polite" aria-atomic="true" className="sr-only">
  {notification}
</div>

// Assertive announcement (urgent)
<div aria-live="assertive" aria-atomic="true" className="sr-only">
  {errorMessage}
</div>

// Status update
<div role="status" aria-live="polite">
  Showing {count} results
</div>

// Alert
<div role="alert">
  Your session will expire in 5 minutes.
</div>

// Progress
<div role="progressbar" aria-valuenow={75} aria-valuemin={0} aria-valuemax={100}>
  75% complete
</div>
```

### Feed/List

```tsx
// Article feed
<main id="main-content">
  <h1>Today's Science News</h1>
  <div role="feed" aria-label="Science news feed" aria-busy={isLoading}>
    {stories.map((story, index) => (
      <article
        key={story.id}
        aria-posinset={index + 1}
        aria-setsize={totalCount}
        aria-labelledby={`story-title-${story.id}`}
      >
        <h2 id={`story-title-${story.id}`}>
          <a href={`/story/${story.slug}`}>{story.headline}</a>
        </h2>
        <p>{story.takeaway}</p>
        <footer>
          <time dateTime={story.created_at}>
            {formatDate(story.created_at)}
          </time>
        </footer>
      </article>
    ))}
  </div>
</main>
```

---

## Forms

### Form Structure

```tsx
// Complete accessible form
<form onSubmit={handleSubmit} aria-labelledby="form-title">
  <h2 id="form-title">Sign in to your account</h2>

  {formError && (
    <div role="alert" className={styles.formError}>
      <AlertCircle aria-hidden="true" />
      {formError}
    </div>
  )}

  <div className={styles.field}>
    <label htmlFor="email">
      Email address
      <span aria-hidden="true" className={styles.required}>*</span>
    </label>
    <input
      type="email"
      id="email"
      name="email"
      required
      aria-required="true"
      aria-invalid={errors.email ? 'true' : undefined}
      aria-describedby={errors.email ? 'email-error' : 'email-hint'}
      autoComplete="email"
    />
    {errors.email ? (
      <p id="email-error" className={styles.error} role="alert">
        {errors.email}
      </p>
    ) : (
      <p id="email-hint" className={styles.hint}>
        We'll send you a sign-in link
      </p>
    )}
  </div>

  <button type="submit" disabled={isSubmitting} aria-busy={isSubmitting}>
    {isSubmitting ? 'Sending...' : 'Send sign-in link'}
  </button>
</form>
```

### Input Types

```tsx
// Email
<input
  type="email"
  inputMode="email"
  autoComplete="email"
  autoCapitalize="none"
  spellCheck="false"
/>

// Search
<input
  type="search"
  role="searchbox"
  aria-label="Search stories"
  autoComplete="off"
  autoCorrect="off"
/>

// Checkbox
<label className={styles.checkbox}>
  <input
    type="checkbox"
    checked={isChecked}
    onChange={(e) => setIsChecked(e.target.checked)}
    aria-describedby="checkbox-hint"
  />
  <span className={styles.checkmark} aria-hidden="true" />
  <span>Remember me</span>
</label>
<p id="checkbox-hint" className={styles.hint}>
  Stay signed in for 30 days
</p>

// Radio group
<fieldset>
  <legend>Digest frequency</legend>
  {options.map((option) => (
    <label key={option.value} className={styles.radio}>
      <input
        type="radio"
        name="frequency"
        value={option.value}
        checked={value === option.value}
        onChange={(e) => setValue(e.target.value)}
      />
      <span className={styles.radioMark} aria-hidden="true" />
      <span>{option.label}</span>
    </label>
  ))}
</fieldset>
```

---

## Images & Media

### Images

```tsx
// Decorative image (no alt)
<img src="/decoration.svg" alt="" aria-hidden="true" />

// Informative image
<img
  src={story.image}
  alt={`Illustration showing ${story.imageDescription}`}
  loading="lazy"
/>

// Image with caption
<figure>
  <img
    src={story.image}
    alt={story.imageAlt}
  />
  <figcaption>{story.imageCaption}</figcaption>
</figure>

// Background image with text overlay
<div
  className={styles.hero}
  style={{ backgroundImage: `url(${imageUrl})` }}
  role="img"
  aria-label={imageDescription}
>
  <h1>{title}</h1>
</div>
```

### Icons

```tsx
// Decorative icon (hidden from AT)
<Search aria-hidden="true" className={styles.icon} />

// Icon-only button (needs label)
<button type="button" aria-label="Close">
  <X aria-hidden="true" />
</button>

// Icon with visible text (hidden from AT)
<button type="button">
  <Bookmark aria-hidden="true" />
  <span>Save</span>
</button>

// Meaningful icon (rare - usually use button label instead)
<span role="img" aria-label="Warning">
  <AlertTriangle />
</span>
```

---

## Screen Reader Only Utility

```css
/* Visually hidden but accessible to screen readers */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

/* Show on focus (for skip links) */
.sr-only-focusable:focus {
  position: static;
  width: auto;
  height: auto;
  padding: inherit;
  margin: inherit;
  overflow: visible;
  clip: auto;
  white-space: inherit;
}
```

Usage:

```tsx
// Hidden text for context
<button>
  <span className="sr-only">Remove</span>
  <span aria-hidden="true">×</span>
</button>

// Hidden heading for screen reader navigation
<section aria-labelledby="latest-heading">
  <h2 id="latest-heading" className="sr-only">Latest Stories</h2>
  {/* content */}
</section>

// Count for screen readers
<span className="sr-only">{unreadCount} unread notifications</span>
```

---

## Motion & Animation

### Reduced Motion

```css
/* Default animations */
.card {
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.card:hover {
  transform: translateY(-2px);
}

/* Respect user preference */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}

/* Or per-component */
@media (prefers-reduced-motion: reduce) {
  .card {
    transition: none;
  }

  .card:hover {
    transform: none;
  }
}
```

### Hook for reduced motion

```tsx
// src/hooks/useReducedMotion.ts
export function useReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPrefersReducedMotion(mediaQuery.matches);

    const handler = (e: MediaQueryListEvent) => {
      setPrefersReducedMotion(e.matches);
    };

    mediaQuery.addEventListener('change', handler);
    return () => mediaQuery.removeEventListener('change', handler);
  }, []);

  return prefersReducedMotion;
}

// Usage
const prefersReducedMotion = useReducedMotion();

const variants = prefersReducedMotion
  ? { initial: {}, animate: {}, exit: {} }
  : { initial: { opacity: 0 }, animate: { opacity: 1 }, exit: { opacity: 0 } };
```

---

## Testing Requirements

### Automated Testing

```typescript
// vitest.setup.ts
import { configureAxe, toHaveNoViolations } from 'jest-axe';

expect.extend(toHaveNoViolations);

// Configure axe for our needs
const axe = configureAxe({
  rules: {
    // Ensure our custom rules
    'color-contrast': { enabled: true },
    'focus-visible': { enabled: true },
  },
});
```

```typescript
// Component test example
import { render } from '@testing-library/react';
import { axe } from 'jest-axe';

describe('Button', () => {
  it('should have no accessibility violations', async () => {
    const { container } = render(
      <Button onClick={() => {}}>Click me</Button>
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('should be keyboard accessible', async () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Click me</Button>);

    const button = screen.getByRole('button');
    button.focus();
    expect(button).toHaveFocus();

    await userEvent.keyboard('{Enter}');
    expect(onClick).toHaveBeenCalled();

    await userEvent.keyboard(' ');
    expect(onClick).toHaveBeenCalledTimes(2);
  });
});
```

### Manual Testing Checklist

**Keyboard Navigation:**
- [ ] All interactive elements reachable via Tab
- [ ] Focus order is logical
- [ ] Focus indicator is visible
- [ ] No keyboard traps
- [ ] Skip links work
- [ ] Escape closes modals/dropdowns

**Screen Reader:**
- [ ] All content is announced
- [ ] Headings create logical outline
- [ ] Links have descriptive text
- [ ] Images have appropriate alt text
- [ ] Forms have proper labels
- [ ] Errors are announced
- [ ] Dynamic content updates announced

**Visual:**
- [ ] 200% zoom is usable
- [ ] Text resizes properly
- [ ] Content reflows at 320px
- [ ] Color is not only indicator
- [ ] Focus is visible
- [ ] Contrast meets requirements

### Screen Reader Testing Matrix

| Screen Reader | Browser | Platform |
|--------------|---------|----------|
| VoiceOver | Safari | macOS |
| VoiceOver | Safari | iOS |
| NVDA | Firefox | Windows |
| NVDA | Chrome | Windows |
| TalkBack | Chrome | Android |

---

## Component Accessibility Checklist

### For Every Component

- [ ] Semantic HTML used
- [ ] ARIA only when needed
- [ ] Keyboard accessible
- [ ] Focus visible
- [ ] Sufficient contrast
- [ ] Tested with axe
- [ ] Tested with screen reader
- [ ] Works at 200% zoom
- [ ] Works with reduced motion
- [ ] Has accessible name

### Interactive Components

- [ ] Clear affordance
- [ ] State changes announced
- [ ] Loading states accessible
- [ ] Error states accessible
- [ ] Touch target ≥ 44px

### Forms

- [ ] Labels associated
- [ ] Required fields marked
- [ ] Errors linked to inputs
- [ ] Hints provided
- [ ] Autocomplete attributes
