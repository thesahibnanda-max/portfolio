// @ts-check
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, envField } from "astro/config";
import { loadEnv } from "vite";

const { PUBLIC_SITE_URL } = loadEnv(process.env.NODE_ENV ?? "production", process.cwd(), "");

export default defineConfig({
  site: PUBLIC_SITE_URL || undefined,
  integrations: [react()],
  build: {
    inlineStylesheets: "always",
  },
  vite: {
    plugins: [tailwindcss()],
  },
  env: {
    schema: {
      PUBLIC_BACKEND_BASE_URL: envField.string({ context: "client", access: "public", url: true }),
      PUBLIC_SITE_URL: envField.string({ context: "client", access: "public", url: true, optional: true }),
    },
    validateSecrets: true,
  },
});
