// @ts-check
import react from "@astrojs/react";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig, envField } from "astro/config";
import { loadEnv } from "vite";

const { PUBLIC_SITE_URL, PUBLIC_BACKEND_BASE_URL } = loadEnv(process.env.NODE_ENV ?? "production", process.cwd(), "");

const backend = PUBLIC_BACKEND_BASE_URL ? new URL(PUBLIC_BACKEND_BASE_URL) : undefined;
const profileImagePatterns =
  backend === undefined
    ? []
    : [
        {
          protocol: backend.protocol.replace(":", ""),
          hostname: backend.hostname,
          ...(backend.port === "" ? {} : { port: backend.port }),
          pathname: "/details/profile/image",
        },
      ];

export default defineConfig({
  site: PUBLIC_SITE_URL || undefined,
  integrations: [react()],
  image: {
    remotePatterns: profileImagePatterns,
  },
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
