/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
};

const runtimeCaching = require('next-pwa/cache');

const withPWA = require('next-pwa')({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  skipWaiting: true,
  runtimeCaching,
  fallbacks: {
    document: '/offline',
  },
  additionalManifestEntries: [
    { url: '/offline', revision: null },
    { url: '/saved', revision: null },
    { url: '/reader', revision: null },
  ],
});

module.exports = withPWA(nextConfig);
