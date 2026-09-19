/**
 * Client-side image preparation.
 *
 * Matches what the Flutter app exports after its crop editor —
 * editedPhotoMaxSide = 1600, editedPhotoJpegQuality = 88
 * (app/lib/core/constants/app_constants.dart:35-36) — so the bytes the
 * backend sees from the web are the same shape as the bytes it sees from a
 * phone. That keeps the pipeline's blur and brightness gates comparable.
 */

export const MAX_SIDE = 1600;
export const JPEG_QUALITY = 0.88;

/** Backend rejects anything over MAX_MEDIA_UPLOAD_SIZE (10 MB). */
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export interface PreparedImage {
  blob: Blob;
  width: number;
  height: number;
  /** Object URL for display. Caller owns it and must revoke it. */
  url: string;
}

/**
 * Decode, downscale to fit MAX_SIDE, re-encode as JPEG.
 *
 * Always re-encodes, even when the source is already small: it strips EXIF
 * (which can carry location) and normalises orientation, so a photo shot on
 * a phone does not arrive at the pipeline rotated 90 degrees.
 */
export async function prepareImage(source: Blob): Promise<PreparedImage> {
  const bitmap = await createImageBitmap(source, { imageOrientation: 'from-image' });

  try {
    const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));

    const canvas = makeCanvas(width, height);
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('2D canvas is unavailable');

    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(bitmap, 0, 0, width, height);

    const blob = await toJpeg(canvas);
    if (blob.size > MAX_UPLOAD_BYTES) {
      throw new Error(
        `Image is ${(blob.size / 1e6).toFixed(1)} MB after compression; the server accepts 10 MB.`,
      );
    }

    return { blob, width, height, url: URL.createObjectURL(blob) };
  } finally {
    bitmap.close();
  }
}

/** Loads one of the bundled craft photos and prepares it the same way. */
export async function prepareFromUrl(url: string): Promise<PreparedImage> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not load ${url} (${res.status})`);
  return prepareImage(await res.blob());
}

function makeCanvas(width: number, height: number): HTMLCanvasElement | OffscreenCanvas {
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(width, height);
  const c = document.createElement('canvas');
  c.width = width;
  c.height = height;
  return c;
}

async function toJpeg(canvas: HTMLCanvasElement | OffscreenCanvas): Promise<Blob> {
  if ('convertToBlob' in canvas) {
    return canvas.convertToBlob({ type: 'image/jpeg', quality: JPEG_QUALITY });
  }
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error('Canvas produced no JPEG'))),
      'image/jpeg',
      JPEG_QUALITY,
    );
  });
}
