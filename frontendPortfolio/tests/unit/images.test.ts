import { readFile } from "node:fs/promises";
import sharp from "sharp";
import { describe, expect, it } from "vitest";
import { ApiClient } from "../../src/lib/api/client";
import { ApiError, InvalidResponseError } from "../../src/lib/api/errors";
import { profileSchema } from "../../src/lib/api/schemas";
import { APPLE_TOUCH_ICON_SIZE, circularIcon, FAVICON_SIZE, squareIcon } from "../../src/lib/icons";
import { errorBody, FakeFetch, jsonResponse } from "./support";

const PHOTO = new Uint8Array(await readFile(new URL("../fixtures/api/profile-image.jpg", import.meta.url)));
const PROFILE = JSON.parse(await readFile(new URL("../fixtures/api/profile.json", import.meta.url), "utf8"));

async function alphaAt(png: Uint8Array, x: number, y: number): Promise<number> {
  const { data, info } = await sharp(png).ensureAlpha().raw().toBuffer({ resolveWithObject: true });
  return data[(y * info.width + x) * info.channels + 3] ?? -1;
}

describe("ApiClient.requestBytes", () => {
  it("returns image bytes", async () => {
    const fake = new FakeFetch([new Response(PHOTO, { status: 200, headers: { "content-type": "image/jpeg" } })]);

    const bytes = await new ApiClient("http://api.test", fake.fetch).requestBytes("/details/profile/image?v=1");

    expect(bytes).toEqual(PHOTO);
    expect(fake.requests[0]?.url).toBe("http://api.test/details/profile/image?v=1");
  });

  it("rejects responses that are not images", async () => {
    const fake = new FakeFetch([new Response("<html>", { status: 200, headers: { "content-type": "text/html" } })]);

    await expect(new ApiClient("http://api.test", fake.fetch).requestBytes("/x")).rejects.toBeInstanceOf(
      InvalidResponseError,
    );
  });

  it("maps server errors like every other request", async () => {
    const fake = new FakeFetch([jsonResponse(500, errorBody(500, "INTERNAL_ERROR"))]);

    await expect(new ApiClient("http://api.test", fake.fetch).requestBytes("/x")).rejects.toBeInstanceOf(ApiError);
  });

  it("builds absolute URLs from API paths", () => {
    expect(new ApiClient("http://api.test/").url("/details/profile/image?v=1")).toBe(
      "http://api.test/details/profile/image?v=1",
    );
  });
});

describe("icons", () => {
  it("makes a circular favicon with transparent corners", async () => {
    const png = await circularIcon(PHOTO);
    const meta = await sharp(png).metadata();

    expect([meta.format, meta.width, meta.height, meta.hasAlpha]).toEqual(["png", FAVICON_SIZE, FAVICON_SIZE, true]);
    expect(await alphaAt(png, 0, 0)).toBe(0);
    expect(await alphaAt(png, FAVICON_SIZE - 1, FAVICON_SIZE - 1)).toBe(0);
    expect(await alphaAt(png, FAVICON_SIZE / 2, FAVICON_SIZE / 2)).toBe(255);
  });

  it("makes an opaque square apple touch icon", async () => {
    const meta = await sharp(await squareIcon(PHOTO)).metadata();

    expect([meta.format, meta.width, meta.height, meta.hasAlpha]).toEqual([
      "png",
      APPLE_TOUCH_ICON_SIZE,
      APPLE_TOUCH_ICON_SIZE,
      false,
    ]);
  });
});

describe("profileSchema", () => {
  it("requires a relative profile image url", () => {
    expect(profileSchema.parse(PROFILE).profile_image_url).toMatch(/^\/details\/profile\/image\?v=[0-9a-f]{16}$/);
    expect(profileSchema.safeParse({ ...PROFILE, profile_image_url: "https://elsewhere.test/x.jpg" }).success).toBe(
      false,
    );
    const { profile_image_url: _ignored, ...withoutUrl } = PROFILE;
    expect(profileSchema.safeParse(withoutUrl).success).toBe(false);
  });
});
