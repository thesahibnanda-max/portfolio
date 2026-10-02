import { PUBLIC_BACKEND_BASE_URL } from "astro:env/client";

export const BACKEND_BASE_URL: string = PUBLIC_BACKEND_BASE_URL.replace(/\/+$/, "");
