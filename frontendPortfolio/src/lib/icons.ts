import sharp from "sharp";

export const FAVICON_SIZE = 64;
export const APPLE_TOUCH_ICON_SIZE = 180;

function circleMask(size: number): Buffer {
  const radius = size / 2;
  return Buffer.from(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}"><circle cx="${radius}" cy="${radius}" r="${radius}" fill="#fff"/></svg>`,
  );
}

export async function circularIcon(image: Uint8Array, size: number = FAVICON_SIZE): Promise<Uint8Array<ArrayBuffer>> {
  const png = await sharp(image)
    .resize(size, size, { fit: "cover", position: "attention" })
    .ensureAlpha()
    .composite([{ input: circleMask(size), blend: "dest-in" }])
    .png({ compressionLevel: 9 })
    .toBuffer();
  return Uint8Array.from(png);
}

export async function squareIcon(
  image: Uint8Array,
  size: number = APPLE_TOUCH_ICON_SIZE,
): Promise<Uint8Array<ArrayBuffer>> {
  const png = await sharp(image)
    .resize(size, size, { fit: "cover", position: "attention" })
    .flatten({ background: "#0b0b0c" })
    .png({ compressionLevel: 9 })
    .toBuffer();
  return Uint8Array.from(png);
}
