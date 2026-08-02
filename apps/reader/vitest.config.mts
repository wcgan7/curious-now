import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// The reader had no test setup at all. This is the minimum that lets pure
// logic be tested without pulling in the database connection: the same "@"
// alias tsconfig already uses, and nothing else.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./", import.meta.url)),
    },
  },
});
