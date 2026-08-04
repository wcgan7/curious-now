import type { Metadata } from "next";
import { Instrument_Sans, Newsreader } from "next/font/google";
import type { ReactNode } from "react";

import { Masthead } from "@/components/Masthead";
import { THEME_SCRIPT } from "@/components/ThemeToggle";

// Self-hosted: the package ships its own fonts and Next bundles them, so
// nothing is fetched from a CDN at read time.
import "katex/dist/katex.min.css";
import "@/app/globals.css";

const sans = Instrument_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Newsreader({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
});

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
    <html className={`${sans.variable} ${serif.variable}`} lang="en">
      <body>
        {/* Before the first paint, so a stored dark choice never flashes
            white — the bug nearly every theme toggle ships with. React hoists
            it; an explicit <head> in a root layout is not the documented
            shape and gets in the way of Next's own bootstrap. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
        <Masthead />
        <main>{children}</main>
      </body>
    </html>
  );
}
