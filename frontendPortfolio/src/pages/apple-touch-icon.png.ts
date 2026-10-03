import type { APIRoute } from "astro";
import { profileImage } from "../content/snapshot";
import { squareIcon } from "../lib/icons";

export const GET: APIRoute = async () =>
  new Response(await squareIcon(profileImage), { headers: { "Content-Type": "image/png" } });
