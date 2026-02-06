import { defineConfig } from 'vitest/config';
import path from 'node:path';

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    include: ['**/*.test.ts', '**/*.test.tsx'],
    exclude: ['e2e/**', 'node_modules/**', '.next/**'],
    environment: 'jsdom',
    setupFiles: ['./test/vitest.setup.ts'],
    globals: true,
    css: true,
  },
});
