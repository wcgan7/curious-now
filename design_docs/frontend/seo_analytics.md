# SEO & Analytics Specification

## Overview

This document specifies the SEO strategy, metadata generation, structured data implementation, and analytics tracking for Curious Now.

---

## SEO Architecture

### URL Structure

```
/                           # Home (Today's Feed)
/story/[slug]               # Story detail page
/topic/[slug]               # Topic feed
/search                     # Search results
/search?q=[query]           # Search with query
/saved                      # Saved stories (auth required)
/settings                   # User settings (auth required)
/about                      # About page
/privacy                    # Privacy policy
/terms                      # Terms of service
```

### Slug Generation Rules

```typescript
// src/lib/seo/slugify.ts

export function generateStorySlug(headline: string, clusterId: string): string {
  const baseSlug = headline
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')  // Replace non-alphanumeric with hyphens
    .replace(/^-+|-+$/g, '')      // Trim leading/trailing hyphens
    .slice(0, 60);                 // Max 60 chars for readability

  // Append short ID for uniqueness
  const shortId = clusterId.slice(0, 8);
  return `${baseSlug}-${shortId}`;
}

// Examples:
// "New Study Reveals Climate Impact" + "abc123def456"
// → "new-study-reveals-climate-impact-abc123de"

export function generateTopicSlug(topicName: string): string {
  return topicName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

// Examples:
// "Climate Science" → "climate-science"
// "AI & Machine Learning" → "ai-machine-learning"
```

---

## Metadata Configuration

### Global Metadata

`src/app/layout.tsx`

```tsx
import { Metadata } from 'next';

export const metadata: Metadata = {
  metadataBase: new URL('https://curious.now'),
  title: {
    default: 'Curious Now - Science News That Makes You Think',
    template: '%s | Curious Now',
  },
  description:
    'Stay informed with curated science news from multiple sources. Get clear takeaways, evidence-based reporting, and diverse perspectives on the latest discoveries.',
  keywords: [
    'science news',
    'research',
    'discoveries',
    'technology',
    'health',
    'environment',
    'physics',
    'biology',
    'astronomy',
  ],
  authors: [{ name: 'Curious Now' }],
  creator: 'Curious Now',
  publisher: 'Curious Now',
  formatDetection: {
    email: false,
    address: false,
    telephone: false,
  },
  openGraph: {
    type: 'website',
    locale: 'en_US',
    url: 'https://curious.now',
    siteName: 'Curious Now',
    title: 'Curious Now - Science News That Makes You Think',
    description:
      'Stay informed with curated science news from multiple sources.',
    images: [
      {
        url: '/og-image.png',
        width: 1200,
        height: 630,
        alt: 'Curious Now - Science News',
      },
    ],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'Curious Now - Science News That Makes You Think',
    description:
      'Stay informed with curated science news from multiple sources.',
    images: ['/twitter-image.png'],
    creator: '@curiousnow',
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-video-preview': -1,
      'max-image-preview': 'large',
      'max-snippet': -1,
    },
  },
  icons: {
    icon: '/favicon.ico',
    shortcut: '/favicon-16x16.png',
    apple: '/apple-touch-icon.png',
  },
  manifest: '/manifest.json',
  alternates: {
    canonical: 'https://curious.now',
    types: {
      'application/rss+xml': '/feed.xml',
    },
  },
};
```

### Story Page Metadata

`src/app/story/[slug]/page.tsx`

```tsx
import { Metadata } from 'next';
import { notFound } from 'next/navigation';
import { getClusterBySlug } from '@/lib/api';

interface Props {
  params: { slug: string };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const cluster = await getClusterBySlug(params.slug);

  if (!cluster) {
    return {};
  }

  const title = cluster.headline;
  const description = cluster.takeaway || cluster.headline;
  const publishedTime = cluster.created_at;
  const modifiedTime = cluster.updated_at;
  const topic = cluster.topic?.name || 'Science';

  // Generate OG image URL with dynamic parameters
  const ogImageUrl = new URL('/api/og', 'https://curious.now');
  ogImageUrl.searchParams.set('title', title);
  ogImageUrl.searchParams.set('topic', topic);
  if (cluster.image_url) {
    ogImageUrl.searchParams.set('image', cluster.image_url);
  }

  return {
    title,
    description,
    keywords: [
      topic.toLowerCase(),
      'science news',
      ...cluster.keywords || [],
    ],
    openGraph: {
      type: 'article',
      title,
      description,
      url: `https://curious.now/story/${params.slug}`,
      publishedTime,
      modifiedTime,
      section: topic,
      tags: cluster.keywords,
      images: [
        {
          url: ogImageUrl.toString(),
          width: 1200,
          height: 630,
          alt: title,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [ogImageUrl.toString()],
    },
    alternates: {
      canonical: `https://curious.now/story/${params.slug}`,
    },
  };
}
```

### Topic Page Metadata

`src/app/topic/[slug]/page.tsx`

```tsx
export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const topic = await getTopicBySlug(params.slug);

  if (!topic) {
    return {};
  }

  const title = `${topic.name} News`;
  const description = `Latest ${topic.name.toLowerCase()} news and research. Stay updated with curated stories from multiple sources.`;

  return {
    title,
    description,
    openGraph: {
      type: 'website',
      title: `${topic.name} News | Curious Now`,
      description,
      url: `https://curious.now/topic/${params.slug}`,
    },
    twitter: {
      card: 'summary',
      title: `${topic.name} News | Curious Now`,
      description,
    },
    alternates: {
      canonical: `https://curious.now/topic/${params.slug}`,
    },
  };
}
```

### Search Page Metadata

`src/app/search/page.tsx`

```tsx
export async function generateMetadata({
  searchParams,
}: {
  searchParams: { q?: string };
}): Promise<Metadata> {
  const query = searchParams.q;

  if (!query) {
    return {
      title: 'Search',
      description: 'Search for science news stories across all topics.',
      robots: { index: false }, // Don't index empty search page
    };
  }

  return {
    title: `Search: ${query}`,
    description: `Search results for "${query}" - Find science news and research.`,
    robots: { index: false }, // Don't index search results
  };
}
```

---

## Dynamic OG Image Generation

`src/app/api/og/route.tsx`

```tsx
import { ImageResponse } from 'next/og';
import { NextRequest } from 'next/server';

export const runtime = 'edge';

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);

  const title = searchParams.get('title') || 'Curious Now';
  const topic = searchParams.get('topic') || 'Science';
  const imageUrl = searchParams.get('image');

  // Load fonts
  const interSemiBold = await fetch(
    new URL('/fonts/Inter-SemiBold.ttf', request.url)
  ).then((res) => res.arrayBuffer());

  const sourceSerif = await fetch(
    new URL('/fonts/SourceSerif4-SemiBold.ttf', request.url)
  ).then((res) => res.arrayBuffer());

  return new ImageResponse(
    (
      <div
        style={{
          height: '100%',
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          backgroundColor: '#1a4d7c',
          padding: '60px',
        }}
      >
        {/* Background Image (if provided) */}
        {imageUrl && (
          <img
            src={imageUrl}
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              opacity: 0.3,
            }}
          />
        )}

        {/* Content */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            height: '100%',
            position: 'relative',
          }}
        >
          {/* Topic Badge */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <div
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.2)',
                borderRadius: '8px',
                padding: '8px 16px',
                color: '#ffffff',
                fontSize: '24px',
                fontFamily: 'Inter',
              }}
            >
              {topic}
            </div>
          </div>

          {/* Title */}
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <h1
              style={{
                color: '#ffffff',
                fontSize: title.length > 80 ? '48px' : '56px',
                fontFamily: 'Source Serif',
                lineHeight: 1.2,
                margin: 0,
                textShadow: '0 2px 10px rgba(0,0,0,0.3)',
              }}
            >
              {title.length > 120 ? `${title.slice(0, 117)}...` : title}
            </h1>
          </div>

          {/* Logo */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                color: '#ffffff',
                fontSize: '28px',
                fontFamily: 'Inter',
              }}
            >
              <img
                src="https://curious.now/logo-white.png"
                width={40}
                height={40}
                style={{ marginRight: '12px' }}
              />
              Curious Now
            </div>
            <div
              style={{
                color: 'rgba(255, 255, 255, 0.7)',
                fontSize: '20px',
                fontFamily: 'Inter',
              }}
            >
              curious.now
            </div>
          </div>
        </div>
      </div>
    ),
    {
      width: 1200,
      height: 630,
      fonts: [
        {
          name: 'Inter',
          data: interSemiBold,
          style: 'normal',
          weight: 600,
        },
        {
          name: 'Source Serif',
          data: sourceSerif,
          style: 'normal',
          weight: 600,
        },
      ],
    }
  );
}
```

---

## Structured Data (JSON-LD)

### Organization Schema

`src/components/seo/OrganizationSchema.tsx`

```tsx
export function OrganizationSchema() {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    name: 'Curious Now',
    url: 'https://curious.now',
    logo: 'https://curious.now/logo.png',
    sameAs: [
      'https://twitter.com/curiousnow',
      'https://github.com/curious-now',
    ],
    contactPoint: {
      '@type': 'ContactPoint',
      email: 'hello@curious.now',
      contactType: 'customer service',
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
```

### WebSite Schema (for Sitelinks Search)

`src/components/seo/WebSiteSchema.tsx`

```tsx
export function WebSiteSchema() {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    name: 'Curious Now',
    url: 'https://curious.now',
    potentialAction: {
      '@type': 'SearchAction',
      target: {
        '@type': 'EntryPoint',
        urlTemplate: 'https://curious.now/search?q={search_term_string}',
      },
      'query-input': 'required name=search_term_string',
    },
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
```

### Article Schema (Story Pages)

`src/components/seo/ArticleSchema.tsx`

```tsx
interface ArticleSchemaProps {
  headline: string;
  description: string;
  datePublished: string;
  dateModified: string;
  imageUrl?: string;
  topic: string;
  sources: Array<{ name: string; url: string }>;
  url: string;
}

export function ArticleSchema({
  headline,
  description,
  datePublished,
  dateModified,
  imageUrl,
  topic,
  sources,
  url,
}: ArticleSchemaProps) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'NewsArticle',
    headline,
    description,
    datePublished,
    dateModified,
    image: imageUrl ? [imageUrl] : undefined,
    author: {
      '@type': 'Organization',
      name: 'Curious Now',
      url: 'https://curious.now',
    },
    publisher: {
      '@type': 'Organization',
      name: 'Curious Now',
      logo: {
        '@type': 'ImageObject',
        url: 'https://curious.now/logo.png',
        width: 600,
        height: 60,
      },
    },
    mainEntityOfPage: {
      '@type': 'WebPage',
      '@id': url,
    },
    articleSection: topic,
    // Citation of original sources
    citation: sources.map((source) => ({
      '@type': 'WebPage',
      name: source.name,
      url: source.url,
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
```

### BreadcrumbList Schema

`src/components/seo/BreadcrumbSchema.tsx`

```tsx
interface Breadcrumb {
  name: string;
  url: string;
}

export function BreadcrumbSchema({ items }: { items: Breadcrumb[] }) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: item.url,
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}

// Usage on story page:
<BreadcrumbSchema
  items={[
    { name: 'Home', url: 'https://curious.now' },
    { name: topic.name, url: `https://curious.now/topic/${topic.slug}` },
    { name: headline, url: `https://curious.now/story/${slug}` },
  ]}
/>
```

### FAQ Schema (for FAQ pages or story Q&A)

```tsx
interface FAQItem {
  question: string;
  answer: string;
}

export function FAQSchema({ items }: { items: FAQItem[] }) {
  const schema = {
    '@context': 'https://schema.org',
    '@type': 'FAQPage',
    mainEntity: items.map((item) => ({
      '@type': 'Question',
      name: item.question,
      acceptedAnswer: {
        '@type': 'Answer',
        text: item.answer,
      },
    })),
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(schema) }}
    />
  );
}
```

---

## Technical SEO

### robots.txt

`public/robots.txt`

```
# https://curious.now/robots.txt

User-agent: *
Allow: /
Disallow: /api/
Disallow: /saved
Disallow: /settings
Disallow: /auth/
Disallow: /search?
Disallow: /*.json$

# Crawl-delay for well-behaved bots
Crawl-delay: 1

# Sitemaps
Sitemap: https://curious.now/sitemap.xml
Sitemap: https://curious.now/sitemap-stories.xml
Sitemap: https://curious.now/sitemap-topics.xml
```

### Sitemap Generation

`src/app/sitemap.ts`

```typescript
import { MetadataRoute } from 'next';

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const baseUrl = 'https://curious.now';

  // Static pages
  const staticPages = [
    '',
    '/about',
    '/privacy',
    '/terms',
  ].map((route) => ({
    url: `${baseUrl}${route}`,
    lastModified: new Date(),
    changeFrequency: 'weekly' as const,
    priority: route === '' ? 1 : 0.8,
  }));

  return staticPages;
}
```

`src/app/sitemap-stories.xml/route.ts`

```typescript
import { getRecentClusters } from '@/lib/api';

export async function GET() {
  const clusters = await getRecentClusters({ limit: 1000 });

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
${clusters
  .map(
    (cluster) => `
  <url>
    <loc>https://curious.now/story/${cluster.slug}</loc>
    <lastmod>${new Date(cluster.updated_at).toISOString()}</lastmod>
    <changefreq>daily</changefreq>
    <priority>0.9</priority>
    <news:news>
      <news:publication>
        <news:name>Curious Now</news:name>
        <news:language>en</news:language>
      </news:publication>
      <news:publication_date>${new Date(cluster.created_at).toISOString()}</news:publication_date>
      <news:title>${escapeXml(cluster.headline)}</news:title>
    </news:news>
  </url>`
  )
  .join('')}
</urlset>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
    },
  });
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}
```

`src/app/sitemap-topics.xml/route.ts`

```typescript
import { getAllTopics } from '@/lib/api';

export async function GET() {
  const topics = await getAllTopics();

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${topics
  .map(
    (topic) => `
  <url>
    <loc>https://curious.now/topic/${topic.slug}</loc>
    <changefreq>daily</changefreq>
    <priority>0.8</priority>
  </url>`
  )
  .join('')}
</urlset>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/xml',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
    },
  });
}
```

### RSS Feed

`src/app/feed.xml/route.ts`

```typescript
import { getRecentClusters } from '@/lib/api';

export async function GET() {
  const clusters = await getRecentClusters({ limit: 50 });

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Curious Now - Science News</title>
    <link>https://curious.now</link>
    <description>Stay informed with curated science news from multiple sources.</description>
    <language>en-us</language>
    <lastBuildDate>${new Date().toUTCString()}</lastBuildDate>
    <atom:link href="https://curious.now/feed.xml" rel="self" type="application/rss+xml"/>
    <image>
      <url>https://curious.now/logo.png</url>
      <title>Curious Now</title>
      <link>https://curious.now</link>
    </image>
${clusters
  .map(
    (cluster) => `
    <item>
      <title>${escapeXml(cluster.headline)}</title>
      <link>https://curious.now/story/${cluster.slug}</link>
      <guid isPermaLink="true">https://curious.now/story/${cluster.slug}</guid>
      <pubDate>${new Date(cluster.created_at).toUTCString()}</pubDate>
      <description>${escapeXml(cluster.takeaway || '')}</description>
      <category>${escapeXml(cluster.topic?.name || 'Science')}</category>
    </item>`
  )
  .join('')}
  </channel>
</rss>`;

  return new Response(xml, {
    headers: {
      'Content-Type': 'application/rss+xml',
      'Cache-Control': 'public, max-age=3600, s-maxage=3600',
    },
  });
}
```

---

## Analytics Implementation

### Analytics Provider Setup

`src/providers/AnalyticsProvider.tsx`

```tsx
'use client';

import { createContext, useContext, useEffect, useCallback } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';

// Types
interface AnalyticsEvent {
  name: string;
  properties?: Record<string, any>;
}

interface AnalyticsContextValue {
  track: (event: AnalyticsEvent) => void;
  identify: (userId: string, traits?: Record<string, any>) => void;
}

const AnalyticsContext = createContext<AnalyticsContextValue | null>(null);

// Initialize analytics services
function initAnalytics() {
  // Google Analytics 4
  if (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_GA_ID) {
    const script = document.createElement('script');
    script.src = `https://www.googletagmanager.com/gtag/js?id=${process.env.NEXT_PUBLIC_GA_ID}`;
    script.async = true;
    document.head.appendChild(script);

    window.dataLayer = window.dataLayer || [];
    function gtag(...args: any[]) {
      window.dataLayer.push(args);
    }
    gtag('js', new Date());
    gtag('config', process.env.NEXT_PUBLIC_GA_ID, {
      send_page_view: false, // We'll send manually
    });
  }

  // PostHog (optional)
  if (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_POSTHOG_KEY) {
    import('posthog-js').then((posthog) => {
      posthog.default.init(process.env.NEXT_PUBLIC_POSTHOG_KEY!, {
        api_host: 'https://app.posthog.com',
        capture_pageview: false, // We'll send manually
        persistence: 'localStorage',
        autocapture: false, // Manual events only
      });
    });
  }
}

export function AnalyticsProvider({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Initialize on mount
  useEffect(() => {
    initAnalytics();
  }, []);

  // Track page views
  useEffect(() => {
    const url = pathname + (searchParams.toString() ? `?${searchParams}` : '');
    trackPageView(url);
  }, [pathname, searchParams]);

  const track = useCallback((event: AnalyticsEvent) => {
    // Google Analytics
    if (typeof window !== 'undefined' && window.gtag) {
      window.gtag('event', event.name, event.properties);
    }

    // PostHog
    if (typeof window !== 'undefined' && window.posthog) {
      window.posthog.capture(event.name, event.properties);
    }

    // Console in development
    if (process.env.NODE_ENV === 'development') {
      console.log('[Analytics]', event.name, event.properties);
    }
  }, []);

  const identify = useCallback((userId: string, traits?: Record<string, any>) => {
    // Google Analytics
    if (typeof window !== 'undefined' && window.gtag) {
      window.gtag('config', process.env.NEXT_PUBLIC_GA_ID!, {
        user_id: userId,
      });
    }

    // PostHog
    if (typeof window !== 'undefined' && window.posthog) {
      window.posthog.identify(userId, traits);
    }
  }, []);

  return (
    <AnalyticsContext.Provider value={{ track, identify }}>
      {children}
    </AnalyticsContext.Provider>
  );
}

export function useAnalytics() {
  const context = useContext(AnalyticsContext);
  if (!context) {
    throw new Error('useAnalytics must be used within AnalyticsProvider');
  }
  return context;
}

// Helper functions
function trackPageView(url: string) {
  if (typeof window !== 'undefined' && window.gtag) {
    window.gtag('event', 'page_view', {
      page_path: url,
    });
  }
  if (typeof window !== 'undefined' && window.posthog) {
    window.posthog.capture('$pageview', { $current_url: url });
  }
}
```

### Event Tracking Schema

```typescript
// src/lib/analytics/events.ts

// Event type definitions
export const AnalyticsEvents = {
  // Page Events (automatic)
  PAGE_VIEW: 'page_view',

  // Story Events
  STORY_VIEW: 'story_view',
  STORY_SAVE: 'story_save',
  STORY_UNSAVE: 'story_unsave',
  STORY_SHARE: 'story_share',
  SOURCE_CLICK: 'source_click',

  // Feed Events
  FEED_TAB_CHANGE: 'feed_tab_change',
  FEED_SCROLL: 'feed_scroll',
  FEED_REFRESH: 'feed_refresh',

  // Search Events
  SEARCH_QUERY: 'search_query',
  SEARCH_RESULT_CLICK: 'search_result_click',
  SEARCH_NO_RESULTS: 'search_no_results',

  // Topic Events
  TOPIC_FOLLOW: 'topic_follow',
  TOPIC_UNFOLLOW: 'topic_unfollow',
  TOPIC_VIEW: 'topic_view',

  // Auth Events
  AUTH_START: 'auth_start',
  AUTH_SUCCESS: 'auth_success',
  AUTH_FAIL: 'auth_fail',
  LOGOUT: 'logout',

  // Settings Events
  SETTINGS_CHANGE: 'settings_change',
  DIGEST_FREQUENCY_CHANGE: 'digest_frequency_change',

  // PWA Events
  PWA_INSTALL_PROMPT: 'pwa_install_prompt',
  PWA_INSTALL_ACCEPT: 'pwa_install_accept',
  PWA_INSTALL_DISMISS: 'pwa_install_dismiss',

  // Engagement Events
  TIME_ON_PAGE: 'time_on_page',
  SCROLL_DEPTH: 'scroll_depth',

  // Error Events
  ERROR_BOUNDARY: 'error_boundary',
  API_ERROR: 'api_error',
} as const;

// Property schemas for each event
export interface EventProperties {
  // Story events
  story_view: {
    story_id: string;
    story_slug: string;
    topic: string;
    source_count: number;
    referrer?: string;
  };

  story_save: {
    story_id: string;
    topic: string;
    location: 'feed' | 'story_page' | 'search';
  };

  story_share: {
    story_id: string;
    method: 'copy_link' | 'twitter' | 'facebook' | 'native';
  };

  source_click: {
    story_id: string;
    source_name: string;
    source_url: string;
    position: number;
  };

  // Feed events
  feed_tab_change: {
    from_tab: string;
    to_tab: string;
  };

  feed_scroll: {
    depth: number; // 25, 50, 75, 100
    items_loaded: number;
  };

  // Search events
  search_query: {
    query: string;
    results_count: number;
    filters?: Record<string, any>;
  };

  search_result_click: {
    query: string;
    story_id: string;
    position: number;
  };

  // Topic events
  topic_follow: {
    topic_id: string;
    topic_name: string;
  };

  // Auth events
  auth_start: {
    method: 'magic_link';
  };

  auth_success: {
    method: 'magic_link';
    is_new_user: boolean;
  };

  // Settings events
  settings_change: {
    setting: string;
    old_value: any;
    new_value: any;
  };

  // PWA events
  pwa_install_prompt: {
    platform: 'android' | 'ios' | 'desktop';
  };

  // Engagement events
  time_on_page: {
    page: string;
    duration_seconds: number;
  };

  scroll_depth: {
    page: string;
    depth: 25 | 50 | 75 | 100;
  };

  // Error events
  error_boundary: {
    error: string;
    component_stack: string;
    page: string;
  };

  api_error: {
    endpoint: string;
    status: number;
    error_message: string;
  };
}
```

### Usage Examples

```tsx
// In a component
import { useAnalytics } from '@/providers/AnalyticsProvider';
import { AnalyticsEvents } from '@/lib/analytics/events';

function StoryCard({ story }) {
  const { track } = useAnalytics();

  const handleSave = () => {
    track({
      name: AnalyticsEvents.STORY_SAVE,
      properties: {
        story_id: story.id,
        topic: story.topic.name,
        location: 'feed',
      },
    });
    // ... save logic
  };

  const handleShare = (method: string) => {
    track({
      name: AnalyticsEvents.STORY_SHARE,
      properties: {
        story_id: story.id,
        method,
      },
    });
    // ... share logic
  };

  return (
    // ... component JSX
  );
}
```

### Scroll Depth Tracking

```tsx
// src/hooks/useScrollDepth.ts
import { useEffect, useRef } from 'react';
import { useAnalytics } from '@/providers/AnalyticsProvider';
import { AnalyticsEvents } from '@/lib/analytics/events';

export function useScrollDepth(page: string) {
  const { track } = useAnalytics();
  const trackedDepths = useRef<Set<number>>(new Set());

  useEffect(() => {
    const handleScroll = () => {
      const scrollTop = window.scrollY;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const scrollPercent = Math.round((scrollTop / docHeight) * 100);

      const thresholds = [25, 50, 75, 100];
      for (const threshold of thresholds) {
        if (scrollPercent >= threshold && !trackedDepths.current.has(threshold)) {
          trackedDepths.current.add(threshold);
          track({
            name: AnalyticsEvents.SCROLL_DEPTH,
            properties: { page, depth: threshold },
          });
        }
      }
    };

    window.addEventListener('scroll', handleScroll, { passive: true });
    return () => window.removeEventListener('scroll', handleScroll);
  }, [page, track]);
}
```

### Time on Page Tracking

```tsx
// src/hooks/useTimeOnPage.ts
import { useEffect, useRef } from 'react';
import { useAnalytics } from '@/providers/AnalyticsProvider';
import { AnalyticsEvents } from '@/lib/analytics/events';

export function useTimeOnPage(page: string) {
  const { track } = useAnalytics();
  const startTime = useRef(Date.now());

  useEffect(() => {
    startTime.current = Date.now();

    const handleVisibilityChange = () => {
      if (document.hidden) {
        const duration = Math.round((Date.now() - startTime.current) / 1000);
        if (duration > 5) {
          // Only track if > 5 seconds
          track({
            name: AnalyticsEvents.TIME_ON_PAGE,
            properties: { page, duration_seconds: duration },
          });
        }
      } else {
        startTime.current = Date.now();
      }
    };

    const handleBeforeUnload = () => {
      const duration = Math.round((Date.now() - startTime.current) / 1000);
      if (duration > 5) {
        // Use sendBeacon for reliability
        const data = JSON.stringify({
          name: AnalyticsEvents.TIME_ON_PAGE,
          properties: { page, duration_seconds: duration },
        });
        navigator.sendBeacon('/api/analytics', data);
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, [page, track]);
}
```

---

## Performance Monitoring

### Web Vitals Tracking

`src/components/analytics/WebVitals.tsx`

```tsx
'use client';

import { useReportWebVitals } from 'next/web-vitals';

export function WebVitals() {
  useReportWebVitals((metric) => {
    // Send to analytics
    if (typeof window !== 'undefined' && window.gtag) {
      window.gtag('event', metric.name, {
        event_category: 'Web Vitals',
        event_label: metric.id,
        value: Math.round(
          metric.name === 'CLS' ? metric.value * 1000 : metric.value
        ),
        non_interaction: true,
      });
    }

    // Log in development
    if (process.env.NODE_ENV === 'development') {
      console.log(`[Web Vital] ${metric.name}:`, metric.value);
    }
  });

  return null;
}
```

---

## Privacy & Compliance

### Cookie Consent

```tsx
// src/components/CookieConsent.tsx
'use client';

import { useState, useEffect } from 'react';

export function CookieConsent() {
  const [showBanner, setShowBanner] = useState(false);

  useEffect(() => {
    const consent = localStorage.getItem('cookie-consent');
    if (!consent) {
      setShowBanner(true);
    }
  }, []);

  const handleAccept = () => {
    localStorage.setItem('cookie-consent', 'accepted');
    setShowBanner(false);
    // Enable analytics
    window.gtag?.('consent', 'update', {
      analytics_storage: 'granted',
    });
  };

  const handleDecline = () => {
    localStorage.setItem('cookie-consent', 'declined');
    setShowBanner(false);
    // Keep analytics disabled
    window.gtag?.('consent', 'update', {
      analytics_storage: 'denied',
    });
  };

  if (!showBanner) return null;

  return (
    <div className={styles.banner}>
      <p>
        We use cookies to improve your experience and analyze site traffic.
        <a href="/privacy">Learn more</a>
      </p>
      <div className={styles.buttons}>
        <button onClick={handleDecline}>Decline</button>
        <button onClick={handleAccept}>Accept</button>
      </div>
    </div>
  );
}
```

### Analytics Configuration for Privacy

```typescript
// Initialize GA4 with consent mode
window.gtag('consent', 'default', {
  analytics_storage: 'denied', // Default to denied
  ad_storage: 'denied',
  wait_for_update: 500,
});

// Configure privacy-preserving settings
window.gtag('config', GA_ID, {
  anonymize_ip: true,
  allow_google_signals: false,
  allow_ad_personalization_signals: false,
});
```
