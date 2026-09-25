/**
 * The ready-made products a visitor can pick instead of uploading one.
 *
 * Drop images into src/assets/products/ and they appear in the rail: no list
 * to edit. The file name is the label, so `03-brass-diya.jpg` shows as
 * "Brass diya" in third place; a leading number only sets the order. Only
 * the first PRODUCT_SLOTS files are used.
 *
 * Vite resolves the glob at build time, so an empty folder builds fine and
 * simply shows no catalog. Keep each image under ~500 KB; they ship with the
 * site, and the rail shows them as small squares.
 */

export const PRODUCT_SLOTS = 20;

export interface Product {
  readonly slug: string;
  readonly label: string;
  readonly image: string;
}

const files = import.meta.glob<string>('../assets/products/*.{jpg,jpeg,png,webp,JPG,JPEG,PNG,WEBP}', {
  eager: true,
  query: '?url',
  import: 'default',
});

export const PRODUCTS: readonly Product[] = Object.entries(files)
  .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
  .slice(0, PRODUCT_SLOTS)
  .map(([path, image]) => {
    const slug = path.split('/').pop()!.replace(/\.[^.]+$/, '');
    return { slug, label: labelOf(slug), image };
  });

/** `03-brass_diya` -> "Brass diya". */
export function labelOf(stem: string): string {
  const words = stem.replace(/^\d+[\s._-]*/, '').replace(/[._-]+/g, ' ').trim();
  return words ? words[0]!.toUpperCase() + words.slice(1) : stem;
}

/** Marks a photo the visitor supplied rather than one of ours. */
export const UPLOAD_SLUG = 'upload';

export function photoLabel(slug: string): string {
  if (slug === UPLOAD_SLUG) return 'Your photo';
  return PRODUCTS.find((p) => p.slug === slug)?.label ?? labelOf(slug);
}
