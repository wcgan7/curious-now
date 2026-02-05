# Stage 3 — Understanding Layer UI (Curious Now)

You gave a really clear vibe. Here’s a **Curious Now** design direction that translates:

> **Calm curiosity, not noisy urgency.**
> **Scrolling that makes you feel smarter, not stressed.**
> **Quiet + inviting, like a good library corner — but modern.**

This doc covers the **Stage 3 UI direction + design system**, tuned to the core product experience defined in `design_docs/stage0.md` and staged in `design_docs/implementation_plan_overview.md`.

Backend implementation for Stage 3 (schema + enrichment job + guardrails) is specified in `design_docs/stage3_backend.md`.

In Stage 3, the product upgrades the StoryCluster page from “coverage list” to “understanding”:

* **Takeaway** (1 sentence)
* **Intuition** (default; plain language)
* **Deep Dive** (expandable; methods/assumptions/limitations)
* **Trust + uncertainty framing** (content-type labels, confidence band, “what could change this?”)
* **Anti-hype flags** (small sample, mice-only, press-release-only, etc.)
* **Just-in-time glossary tooltips**
* **Evidence panel** (links grouped by content type; always present)

Everything below translates the “quiet curiosity” brand into build-ready UI tokens and components.

---

# 1) Brand Translation: “Quiet + Inviting” → Concrete UI Rules

### What Curious Now should *feel* like

* **Unhurried confidence:** fewer “Breaking!” signals, more “Here’s what we know.”
* **Breathing room:** generous whitespace, softer borders, minimal shadows.
* **Guided learning:** built-in “Takeaway,” definitions, and “evidence” modules.
* **Stable attention:** avoid jumpy feed mechanics and loud badges.

### Practical UI rules

* Prefer **borders + spacing** over heavy shadows.
* Avoid all-caps labels and bright reds (they read as urgent).
* Use **one primary accent** and one subtle highlight—sparingly.
* Default to **“Load more”** over infinite scroll (calmer stopping points).
* No autoplay media. No popups that interrupt reading.

---

# 2) Visual Identity: Palette, Type, and Texture

## 2.1 Color Direction: “Paper + Ocean”

Warm paper backgrounds + calm blue/teal accents = “quietly smart.”

### Light theme palette (recommended)

**Surfaces (warm + calm)**

* `Paper-0` (page background): `#FBFAF7`
* `Paper-1` (card/background): `#FFFFFF`
* `Paper-2` (raised/alt sections): `#F4F1EA`
* `Line` (borders/dividers): `#E6E1D7`

**Text**

* `Ink-900` (primary): `#111827`
* `Ink-700` (secondary): `#374151`
* `Ink-500` (muted): `#6B7280`

**Brand accents**

* `Curious Blue` (links/primary): `#1E40AF`
* `Curious Blue Hover`: `#1D4ED8`
* `Sea Glass` (secondary accent): `#0F766E`
* `Highlighter` (soft emphasis): `#F3D36B` (use like a subtle marker, not a neon CTA)

**Semantic (used carefully)**

* `Success`: `#15803D`
* `Warning`: `#B45309` (muted amber)
* `Danger`: `#B91C1C` (**rare**; avoid urgency feelings unless truly needed)
* `Info`: `#0369A1`

### Dark theme (calm, not “gamer”)

* Background: `#070A12`
* Surface: `#0B1220`
* Raised: `#111B2E`
* Text: `#E5E7EB` / `#CBD5E1`
* Border: `#1F2A44`
* Primary: `#93C5FD`
* Highlight: `#FDE68A`

**How it supports the vibe:** warm paper reduces “cold dashboard” energy; ocean accents feel trustworthy, not hype.

---

## 2.2 Typography: “Readable, editorial, modern”

Two-font pairing keeps it calm: one for UI clarity, one for long reads.

**UI / Navigation:** `Inter` (or `Source Sans 3`)
**Long-form reading (StoryCluster pages):** `Source Serif 4` (or `Newsreader` if you want slightly more “magazine”)

### Type scale (Curious Now tuned)

* Home hero headline: **44–52px / 1.08**
* Story title (H1): **36–44px / 1.12**
* H2: **24–28px / 1.25**
* H3: **18–20px / 1.3**
* Story body: **19px (desktop) / 17–18px (mobile) / 1.7**
* UI body: **16px / 1.5**
* Meta/captions: **13–14px / 1.45**

**Tone detail:** avoid ultra-bold weights everywhere. Use **Medium** for UI and **SemiBold** for headlines (not ExtraBold).

---

## 2.3 Layout & spacing: “Breathing room by default”

* Max reading width (story body): **680–760px**
* Paragraph spacing: **0.9–1.2em** (avoid dense blocks)
* Card padding: **16–20px**
* Section spacing on home: **48–64px** between major modules

**Shadows:** keep to one subtle elevation style; mostly rely on borders and paper surfaces.

---

# 3) Signature “Curious Now” UI Behaviors (What makes it feel unique)

These are the *brand* moments that make scrolling feel smarter:

## 3.1 “Takeaway” as a calm anchor

On StoryCluster pages, add a small module near the top:

**Takeaway**

* 1 sentence max (from Stage 3 `story_clusters.takeaway`)
* Plain language
* If `takeaway` is missing (evidence-only mode), omit the module

Design: Paper-2 background, thin border, small icon (line-style), no loud color blocks.

## 3.2 “Define on hover / tap” for science terms

A gentle, optional tooltip for terms like “p-value,” “exoplanet,” “mRNA,” etc.

* Desktop: hover + focus reveals definition
* Mobile: tap reveals bottom sheet
* Include “Learn more” link (topic hub)

This makes readers feel smarter without leaving the page.

## 3.3 “What we know / What we don’t”

A calm credibility module (especially for evolving stories):

* What we know (supported)
* What’s uncertain
* What’s next to watch

No dramatic warnings—just clarity.

## 3.4 Calm progress indicator

A thin reading progress bar at the very top:

* 2px height
* Same as `Curious Blue` at 60–80% opacity
  (Feels helpful, not gamified.)

---

# 4) Component Design: Calm Variants

## 4.1 Header (quiet, editorial)

**Desktop**

* Left: Curious Now wordmark
* Center: sections (or a “Explore” dropdown to reduce visual noise)
* Right: Search, Save/Reading List, Subscribe

**Sticky behavior**

* Default height: **72px**
* Scroll height: **56px**
* Border bottom appears on scroll (instead of shadow)

**Copy tone**

* “Subscribe” → could be “Support” (less salesy)
* “Trending” → “What readers are exploring”

## 4.2 Story cards (StoryCluster feed cards)

**Card style rules**

* Default: white surface with 1px border
* Hover: slightly darken border + underline title
* Avoid “lift” animations that make the page feel twitchy

### Featured hero card (home)

* Image is large but not shouty
* Topic label is subtle (not all caps)
* Add a short deck (1–2 lines) that frames the *idea*, not drama

### Standard grid card

* Image optional: allow image-less “idea cards” for explainers
* Meta row (cluster-first): source count • updated time • content-type badges
* Optional topic chips: 1–2 max

### Compact row card

* Perfect for “More to explore”
* Title + 1-line context snippet

## 4.3 Buttons (calm CTA)

* Primary button: Curious Blue background, slightly rounded (10–12px)
* Secondary: border button on Paper-1
* Tertiary: text button with underline on hover

**Rule:** limit primaries on screen to 1–2 at a time.

## 4.4 Newsletter module (quietly inviting)

Title ideas:

* “A calmer way to keep up with science.”
* “One thoughtful email. A few times a week.”

Design:

* Paper-2 background, thin border
* One input + button, no confetti animations

## 4.5 Footer (trust & clarity)

* About, Editorial policy, Corrections, Contact
* “How we source science” (this reinforces credibility)

---

# 5) Page Templates (Curious Now flavor)

## 5.1 Home

Replace the typical loud “Trending” layout with calmer modules:

1. **Lead story** (featured hero)
2. **Today’s Curiosities** (3–5 cards; hand-curated feel)
3. **Explainers** (evergreen)
4. **Deep Reads** (long-form)
5. **In Brief** (compact rows, low visual weight)
6. Newsletter CTA (quiet)
7. Footer

Optional: a “Calm Mode” toggle that hides popularity metrics (views/comments).

## 5.2 Topic pages

* Topic intro is short, human, and helpful (“What this topic covers…”)
* Filter chips for subtopics (later)
* Sort options are present but not emphasized

## 5.3 StoryCluster page (the heart of the product)

* Top: title, meta (updated time, source count), save/share
* Immediately after: **Takeaway** (1 sentence, if available)
* Body: comfortable serif for Intuition/Deep Dive, consistent figure captions
* Side rail (desktop): related stories + topic chips + “Define this term” help
* End: “Evidence & sources” + “What changed in this update” (if updated)

---

# 6) Motion & Interaction (Quiet by default)

Animation spec:

* Duration: **150–220ms**
* Easing: gentle ease-out
* Never bounce, never shake
* Respect reduced motion settings

Interaction style:

* Underlines, border shifts, subtle background changes
* Not big transforms or card jumps

---

# 7) Voice & Microcopy (so it doesn’t feel like social media)

**Avoid**

* “BREAKING”
* “You won’t believe”
* “Don’t miss”
* Red urgency badges

**Prefer**

* “Worth your attention”
* “In context”
* “A quick primer”
* “Dig deeper”
* “What the evidence says”

**Badge vocabulary**

* “Explainer”
* “In Context”
* “Updated”
* “Opinion” (if you ever publish analysis)

---

# 8) Dev‑Ready Tokens (Curious Now v1)

```css
:root {
  /* Curious Now — Paper + Ocean */
  --bg: #FBFAF7;
  --surface-1: #FFFFFF;
  --surface-2: #F4F1EA;
  --border: #E6E1D7;

  --text-1: #111827;
  --text-2: #374151;
  --text-3: #6B7280;

  --primary: #1E40AF;
  --primary-hover: #1D4ED8;
  --accent: #0F766E;
  --highlight: #F3D36B;

  --success: #15803D;
  --warning: #B45309;
  --danger: #B91C1C;
  --info: #0369A1;

  --font-ui: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  --font-article: "Source Serif 4", Georgia, serif;

  --s-1: 4px;  --s-2: 8px;  --s-3: 12px; --s-4: 16px;
  --s-6: 24px; --s-8: 32px; --s-12: 48px; --s-16: 64px;

  --r-sm: 8px;
  --r-md: 12px;
  --r-lg: 16px;
}

/* Dark mode */
.theme-dark {
  --bg: #070A12;
  --surface-1: #0B1220;
  --surface-2: #111B2E;
  --border: #1F2A44;

  --text-1: #E5E7EB;
  --text-2: #CBD5E1;
  --text-3: #94A3B8;

  --primary: #93C5FD;
  --primary-hover: #60A5FA;
  --accent: #5EEAD4;
  --highlight: #FDE68A;
}
```

---

# 9) If you want one “signature” detail

A small brand motif that reinforces “curiosity” without being loud:

**The Curious Marker**

* Use the `highlight` color as a soft underline behind a word in the hero headline or section titles (very subtle, like a real highlighter).
* Use it only **1–2 times per screen**.

It creates a recognizable feel without noise.


---

# 10) Component Spec Sheet (Implementation-ready)

This section is the implementation-ready spec (spacing, typography per breakpoint, component dimensions, and interaction states). It was merged from the former `design_docs/stage3b.md`.

This is the **implementation-ready spec**: exact spacing, typography per breakpoint, component dimensions, and interaction states. I’ll reference the tokens you already have (`--bg`, `--surface-1`, `--primary`, `--s-*`, etc.) so this can be dropped into Figma styles *and* dev CSS quickly.

## 1) Breakpoints, Layout, and Containers

### Breakpoints

* **Mobile:** 360–479
* **Large mobile:** 480–767
* **Tablet:** 768–1023
* **Desktop:** 1024–1279
* **Wide:** 1280–1535
* **XL:** 1536+

### Page container

* **Max content width:** `1200px` (wide editorial feel without stretching)
* **Max story body width (StoryCluster page):** `720px` (reading width)
* **Default page padding:**

  * Mobile: `16px`
  * Tablet: `24px`
  * Desktop+: `24px` (keep stable; don’t over-widen)

### Grid

* Mobile: **4 columns**, `16px` gutter
* Tablet: **8 columns**, `20px` gutter
* Desktop+: **12 columns**, `24px` gutter

### Section spacing (vertical rhythm)

* Between major homepage sections:

  * Mobile: `48px`
  * Tablet+: `64px`
* Between cards in grids:

  * Mobile: `16px`
  * Tablet+: `20px`

---

## 2) Core Tokens Needed for Build

You already have colors/spacing/radius. Add these build-critical tokens:

```css
:root {
  /* Borders */
  --border-1: 1px solid var(--border);
  --border-2: 1px solid color-mix(in srgb, var(--border) 70%, var(--text-3));

  /* Focus */
  --focus: color-mix(in srgb, var(--primary) 70%, white);
  --focus-ring: 2px solid var(--focus);
  --focus-offset: 2px;

  /* Shadows (keep quiet) */
  --shadow-1: 0 1px 2px rgba(17, 24, 39, 0.06);
  --shadow-2: 0 6px 18px rgba(17, 24, 39, 0.10);

  /* Motion */
  --t-fast: 150ms;
  --t-med: 220ms;
  --ease: cubic-bezier(0.2, 0.8, 0.2, 1);

  /* Tap targets */
  --tap: 44px;
}
```

Accessibility rule: **Every interactive element must show focus** using `outline: var(--focus-ring); outline-offset: var(--focus-offset);`

---

## 3) Typography: Figma Text Styles + Responsive Sizes

Font families:

* UI: `--font-ui` (Inter)
* Article: `--font-article` (Source Serif 4)

### Font weights

* UI: Regular 400, Medium 500, Semibold 600
* Article: Regular 400, Semibold 600 (avoid ultra-bold)

### Text styles (define as Figma styles + CSS classes)

#### Display / Hero

* **CN / Display**

  * Desktop: `52px / 1.08` weight 600
  * Tablet: `44px / 1.10` weight 600
  * Mobile: `34px / 1.12` weight 600
  * Font: UI (Inter) or Serif (optional for a more editorial hero)

#### Headings (story + page)

* **CN / H1**

  * Desktop: `40px / 1.12` w600
  * Tablet: `36px / 1.14` w600
  * Mobile: `30px / 1.18` w600
* **CN / H2**

  * Desktop: `28px / 1.25` w600
  * Tablet: `26px / 1.25` w600
  * Mobile: `22px / 1.28` w600
* **CN / H3**

  * Desktop: `20px / 1.30` w600
  * Tablet: `19px / 1.30` w600
  * Mobile: `18px / 1.33` w600

#### Body

* **CN / Body UI**

  * All: `16px / 1.55` w400
* **CN / Body Article**

  * Desktop: `19px / 1.75` w400
  * Tablet: `18px / 1.75` w400
  * Mobile: `17px / 1.70` w400
  * Font: Article (serif)

#### Meta / labels

* **CN / Meta**

  * All: `13px / 1.45` w500
  * Letter spacing: `0.01em`
* **CN / Caption**

  * All: `14px / 1.45` w400 (serif or UI; pick one and stay consistent)
* **CN / Overline (use sparingly)**

  * All: `12px / 1.3` w600
  * Letter spacing: `0.06em`
  * Case: Title Case preferred (avoid ALL CAPS for calm vibe)

#### Link style rules

* Default: `color: var(--primary); text-decoration: underline; text-decoration-thickness: 1px; text-underline-offset: 2px;`
* Hover: increase thickness to `2px`
* Visited: optional (keep subtle, maybe a slightly muted primary)

---

## 4) Component Specs

Each component includes **layout**, **type**, **states**, and **responsive behavior**.

---

### 4.1 Header (Global Navigation)

#### Layout

* Height:

  * Desktop default: `72px`
  * Desktop scrolled: `56px`
  * Mobile: `64px`
* Container: page container width (max `1200px`)
* Padding:

  * Horizontal: `16px` mobile, `24px` tablet+
* Divider: **none at top**, but on scroll add bottom border `--border-1`

#### Contents

* Left: Wordmark (Curious Now)
* Center (desktop): Section links (5–7 max) OR “Explore” dropdown (recommended for calm)
* Right: Search icon, Reading List, “Support” button

#### States

* Nav link default: `--text-2`
* Hover: underline + text `--text-1`
* Active page: `--text-1` + underline (persistent)
* Focus-visible: focus ring around the link target (not the whole header)

#### Mobile

* Left: menu button (tap target `44px`)
* Center: wordmark
* Right: search button
* Slide-over menu:

  * Width: `min(92vw, 360px)`
  * Background: `--surface-1`
  * Divider between items: `--border-1`
  * Close button always visible

---

### 4.2 Primary Button

#### Sizes

All buttons: min height `44px` (tap target)

**Primary / M (default)**

* Height: `44px`
* Padding: `0 16px`
* Radius: `12px`
* Font: UI 16px w600
* Background: `--primary`
* Text: `--surface-1`

**Primary / S**

* Height: `36px`
* Padding: `0 12px`
* Font: 14px w600
* Use for compact toolbars only (not mobile primary CTAs)

#### States

* Hover: background `--primary-hover`
* Active: background slightly darker (or `filter: brightness(0.95)`)
* Focus-visible: `outline: var(--focus-ring); outline-offset: 2px;`
* Disabled:

  * Background: `color-mix(in srgb, var(--primary) 25%, var(--surface-2))`
  * Text: `--text-3`
  * Cursor: not-allowed

---

### 4.3 Secondary Button

#### Layout

* Height: `44px`
* Padding: `0 16px`
* Radius: `12px`
* Border: `--border-1`
* Background: `transparent` or `--surface-1`
* Text: `--text-1`

#### States

* Hover: background `--surface-2`
* Active: background `color-mix(in srgb, var(--surface-2) 70%, var(--border))`
* Focus-visible: same as primary
* Disabled: border + text `--text-3`

---

### 4.4 Tertiary Button (Quiet text action)

#### Layout

* Height: `44px` (still meet tap target)
* Padding: `0 8px`
* Text: `--primary`, underline on hover only (or always underline if link-like)

#### States

* Hover: underline + text `--primary-hover`
* Focus-visible: ring

Use for: “Save”, “Share”, “Learn more”.

---

### 4.5 Input Field (Search / Newsletter)

#### Layout

* Height: `44px`
* Padding: `0 12px`
* Radius: `12px`
* Border: `--border-1`
* Background: `--surface-1`
* Placeholder: `--text-3`

#### States

* Hover: border `--border-2`
* Focus: border becomes `color-mix(in srgb, var(--primary) 55%, var(--border))`
* Focus-visible: ring on wrapper
* Error: border `--danger`, helper text `--danger` (use sparingly; keep tone calm)

---

### 4.6 Search Modal / Drawer

#### Desktop (popover modal)

* Width: `min(720px, 92vw)`
* Top offset: `72px` (below header)
* Background: `--surface-1`
* Radius: `16px`
* Shadow: `--shadow-2`
* Internal padding: `16px`
* Sections:

  1. Input row
  2. Suggestions list (topics/authors)
  3. Recent searches (optional)

#### Mobile (full screen or bottom sheet)

* Recommended: full-screen with top search field
* Close button: always visible, tap target 44px

Keyboard:

* Esc closes
* Arrow keys navigate suggestions
* Enter selects

---

### 4.7 Topic Chips (Filters)

#### Layout

* Height: `32px` (desktop), `36px` (mobile)
* Padding: `0 12px`
* Radius: `999px`
* Border: `--border-1`
* Background: `--surface-1`
* Text: `--text-2` (13–14px w500)

#### States

* Hover: background `--surface-2`
* Selected:

  * Background: `color-mix(in srgb, var(--primary) 10%, var(--surface-1))`
  * Border: `color-mix(in srgb, var(--primary) 30%, var(--border))`
  * Text: `--text-1`
* Focus-visible: ring
* Disabled: text `--text-3`, background `--surface-2`

---

### 4.8 Story Cards (StoryCluster feed cards)

#### General rules (all card types)

* Background: `--surface-1`
* Border: `--border-1`
* Radius: `16px` for featured, `12px` for standard, `12px` for compact
* Shadow: none by default (calm). Optional `--shadow-1` on hover only.
* Click area: entire card clickable **but** keep inner links accessible (don’t nest interactive controls badly).

##### Card hover behavior (calm)

* Border becomes slightly darker: `--border-2`
* Title underline appears
* Optional: add `--shadow-1` (very subtle)

##### Card focus-visible

* Ring around the entire card (wrapper)

---

#### 4.8A Featured Hero Card (Home lead story / Topic lead)

**Desktop layout**

* Media: 16:9 image, full width of card
* Content padding: `20px`
* Gap between elements: `8px`

**Typography**

* Topic label: Meta (13px w600, Title Case)
* Title: Display or H1 variant (depends on placement)
* Deck: UI Body 16px or Article Body 17–18px (1–2 lines max)
* Meta row (cluster-first): source count • updated time • content-type badges

**Image**

* Corner radius matches card radius at top only (clip)
* No gradient overlays unless necessary for contrast (keep quiet)

**Mobile**

* Same structure, reduce padding to `16px`
* Title size down one step

---

#### 4.8B Standard Card (Grid)

**Layout**

* Image: 3:2 ratio
* Card padding: `16px`
* Spacing: `8px` between title/deck/meta
* Title: 2 lines max (clamp)
* Deck: 2–3 lines max

**Typography**

* Title: 18–20px w600 (UI font)
* Deck: 15–16px (UI font) `--text-2`
* Meta: 13px `--text-3`

---

#### 4.8C Compact Row Card (Lists, “More to explore”)

**Layout**

* Height: auto; min padding `12px 0` inside list rows
* Divider between rows: `--border-1`
* Optional thumbnail: `56px` square with radius `12px`
* Title to the right; meta below

**Typography**

* Title: 16–17px w600
* Meta: 13px

---

### 4.9 Newsletter CTA Module

#### Layout

* Background: `--surface-2`
* Border: `--border-1`
* Radius: `16px`
* Padding:

  * Desktop: `24px`
  * Mobile: `16px`
* Grid:

  * Desktop: content left, form right (2 columns)
  * Mobile: stacked

#### Contents

* Title: H3 or 20px w600
* Subtext: UI body 16px `--text-2`
* Input + button:

  * Input grows to fill
  * Button fixed width ~120–160px

#### States

* Input focus ring
* Success: show small inline message (no confetti, no animations)

---

### 4.10 “Takeaway” Module (Signature Curious Now)

#### Layout

* Background: `--surface-2`
* Border: `--border-1`
* Radius: `16px`
* Padding: `16px` mobile, `20px` desktop
* Icon: 20px line icon (optional)
* Body: 1 sentence (no bullets)

#### Typography

* Title “Takeaway”: Meta (13px w600)
* Body: Article body size, but slightly tighter: `line-height 1.6`

#### Placement

* StoryCluster page: after title + meta, before Intuition (recommended)

---

### 4.11 “Define This Term” Tooltip / Sheet

#### Desktop tooltip

* Trigger: dotted underline on terms (subtle)
* Tooltip max width: `320px`
* Padding: `12px`
* Radius: `12px`
* Border: `--border-1`
* Shadow: `--shadow-2` (tooltips can float)
* Contains:

  * Term (w600)
  * 1–2 sentence definition
  * Optional “Learn more” link

#### Mobile sheet

* Bottom sheet:

  * Height: up to 60vh
  * Radius: `16px` top corners
  * Padding: `16px`
  * Close button: 44px target

Accessibility:

* Tooltip opens on keyboard focus
* ESC closes
* Sheet traps focus while open

---

### 4.12 “What We Know / What We Don’t” Evidence Module

#### Layout

* Background: `--surface-2`
* Border: `--border-1`
* Radius: `16px`
* Padding: `20px` desktop / `16px` mobile
* Two columns on desktop, stacked on mobile
* Iconography: minimal (optional)

#### Typography

* Section headers: Meta 13px w600
* Body (modules): UI 15–16px

---

### 4.13 Pagination: “Load more” (Calm stopping points)

* Prefer button: “Load more stories”
* Place after 12–18 items
* Show subtle progress text: “Showing 18 of 120” (optional)

---

### 4.14 Toasts (Save/Subscribe feedback)

* Position: bottom-left desktop; bottom-center mobile
* Width: `min(360px, 92vw)`
* Padding: `12px 14px`
* Radius: `14px`
* Background: `--surface-1`
* Border: `--border-1`
* Shadow: `--shadow-2`
* Duration: 4–6s (but allow manual dismiss)
* Motion: fade + slight rise (8px), respect reduced motion

---

### 4.15 Modal (Sign in / Support)

* Max width: `520px`
* Padding: `24px`
* Radius: `16px`
* Shadow: `--shadow-2`
* Overlay: `rgba(0,0,0,0.35)` (dark mode may reduce alpha slightly)
* Focus trap + ESC close + close button

---

## 5) StoryCluster Typography Rules (Full Reading Spec)

This is the “make it feel like a good magazine” part.

### 5.1 StoryCluster page layout

* Story container: centered, max width `720px`
* Top “chrome” (breadcrumbs/meta) max width matches story
* Side rail (desktop optional): max width `320px`, gap `48px` from story

### 5.2 Spacing rules

* Paragraph spacing:

  * `margin: 0 0 1.05em 0;`
* Heading spacing (calm, generous):

  * H2: `margin-top: 1.8em; margin-bottom: 0.6em;`
  * H3: `margin-top: 1.4em; margin-bottom: 0.4em;`
* Lists:

  * `margin: 0.6em 0 1.0em;`
  * List item spacing: `0.35em`

### 5.3 Text rules

* Story body:

  * Color: `--text-1`
  * Line height: `1.7–1.75`
* Secondary text inside story (captions, small modules):

  * `--text-2` or `--text-3` depending on emphasis

### 5.4 Links inside story text

* Always underline by default (trust + clarity)
* Avoid noisy hover colors; just thicken underline
* External link icon optional, but keep subtle

### 5.5 Pull quotes

* Style:

  * Left border: 3px `color-mix(in srgb, var(--primary) 35%, var(--border))`
  * Background: transparent
  * Padding-left: `16px`
  * Font: Article serif, size `22px` desktop / `20px` mobile
  * Line-height: `1.45`
* Attribution below in Meta style

### 5.6 Figures and captions

* Figure max width: story width
* Image radius: `16px`
* Caption:

  * 14px, `--text-2`
  * Spacing: `8px` top
* Credit line (optional): 13px `--text-3`

### 5.7 Inline code / data

Keep minimal and readable (don’t make it look like dev docs):

* Inline code background: `--surface-2`
* Border: `--border-1`
* Radius: `8px`
* Padding: `2px 6px`
* Font: UI monospace fallback (system)

### 5.8 Callout boxes (inside story)

Use 1–2 types only to avoid clutter:

1. **Takeaway** (signature)
2. **Evidence / What we know** module

Never use bright banners.

### 5.9 Reading comfort constraints

* Avoid more than **3 consecutive short paragraphs** that feel choppy.
* Avoid walls of text: insert a subheading every ~300–500 words (as content allows).
* Avoid auto-playing embeds and heavy sticky video.

---

## 6) Interaction & Motion Requirements (Quiet UI)

### Motion

* Default transitions: `var(--t-fast)` for hover/focus, `var(--t-med)` for modals/drawers
* Properties allowed:

  * opacity
  * background-color
  * border-color
  * box-shadow (subtle)
  * transform limited to **<= 8px** and only for overlays/toasts
* Respect reduced motion:

  * disable transforms and reduce durations

### Scroll behavior

* Prefer “Load more” (calm stopping points)
* If infinite scroll is required, add **clear section separators** and a “Back to top” affordance

---

## 7) Quick Dev Checklist (So the vibe stays intact)

* No red urgency badges unless truly necessary
* Underlined story links by default
* Min tap targets 44px
* Focus rings everywhere
* Borders + spacing over heavy shadows
* No autoplay anything
* Fewer “metrics” (views/likes) on the main reading experience
