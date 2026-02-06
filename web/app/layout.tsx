import type { Metadata } from 'next';
import { Manrope, Source_Serif_4 } from 'next/font/google';

import './globals.css';
import { Providers } from '@/app/providers';
import { Header } from '@/components/layout/Header/Header';
import { OfflineIndicator } from '@/components/shared/OfflineIndicator/OfflineIndicator';

const fontUi = Manrope({
  subsets: ['latin'],
  variable: '--font-ui',
});

const fontArticle = Source_Serif_4({
  subsets: ['latin'],
  variable: '--font-article',
});

export const metadata: Metadata = {
  title: {
    default: 'Curious Now',
    template: '%s | Curious Now',
  },
  description: 'Science news that makes you think.',
  manifest: '/manifest.json',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${fontUi.variable} ${fontArticle.variable}`}>
        <Providers>
          <Header />
          {children}
          <OfflineIndicator />
        </Providers>
      </body>
    </html>
  );
}
