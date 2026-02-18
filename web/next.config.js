/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

const runtimeCaching = require('next-pwa/cache');

const withPWA = require('next-pwa')({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development' || process.env.NEXT_PUBLIC_PWA_ENABLED === 'false',
  register: true,
  skipWaiting: true,
  runtimeCaching,
  fallbacks: {
    document: '/offline',
  },
  additionalManifestEntries: [
    { url: '/offline', revision: null },
  ],
});

module.exports = withPWA(nextConfig);
