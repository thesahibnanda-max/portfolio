import type { APIRoute } from "astro";
import { profileImage } from "../content/snapshot";
import { circularIcon } from "../lib/icons";

export const GET: APIRoute = async () =>
  new Response(await circularIcon(profileImage), { headers: { "Content-Type": "image/png" } });
