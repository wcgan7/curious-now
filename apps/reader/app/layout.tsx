import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

// Self-hosted: the package ships its own fonts and Next bundles them, so
// nothing is fetched from a CDN at read time.
import "katex/dist/katex.min.css";
import "@/app/globals.css";

export const metadata: Metadata = {
  title: {
    default: "Curious Now — science worth understanding",
    template: "%s — Curious Now",
  },
  description:
    "A calm, continuously updated feed of science, grounded in visible sources.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="siteHeader">
          <div className="headerInner">
            <Link className="wordmark" href="/">
              curious<span>.now</span>
            </Link>
            <p className="headerPromise">science worth understanding</p>
            <nav aria-label="Primary navigation">
              <Link href="/">Latest</Link>
              <Link href="/search">Search</Link>
            </nav>
          </div>
        </header>
        <main>{children}</main>
        <footer className="siteFooter">
          <p>Built for curiosity, not engagement.</p>
          <p>Every claim should lead back to evidence.</p>
        </footer>
      </body>
    </html>
  );
}
