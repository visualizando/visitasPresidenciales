import path from "node:path";
import {fileURLToPath} from "node:url";
import react from "@vitejs/plugin-react";
import {defineConfig} from "vite";

const directory = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react()],
  base: "./",
  publicDir: false,
  build: {
    outDir: "../pipeline/curation_ui/static",
    emptyOutDir: true,
    rollupOptions: {
      input: {index: path.resolve(directory, "curation.html")},
    },
  },
});
