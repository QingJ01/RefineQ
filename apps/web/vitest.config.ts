import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL(".", import.meta.url)),
    },
  },
  test: {
    environment: "node",
    include: ["tests/**/*.test.{ts,tsx}"],
    // Deadline handling is local-calendar-day semantics, so the suite must run in
    // a fixed non-UTC zone. Without this the timezone regressions only fail on a
    // developer machine that happens to share the author's offset, and CI (UTC)
    // and local runs disagree.
    env: { TZ: "Asia/Shanghai" },
  },
});
