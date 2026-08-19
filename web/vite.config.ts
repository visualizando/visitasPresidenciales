import {defineConfig} from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig(({command}) => ({
  plugins: [react()],
  base: "./",
  // Development serves the generated datasets directly. Production copies
  // them after Vite builds the app so large shards stay out of its build step.
  publicDir: command === "serve" ? "public" : false,
  test: {
    include: ["src/**/*.test.{ts,tsx}"],
    environment: "jsdom",
    setupFiles: "./src/test/setup.ts",
    css: true,
  },
}));
