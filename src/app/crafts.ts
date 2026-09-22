/**
 * The product rail.
 *
 * Photographs are from Wikimedia Commons under CC0 / CC BY / CC BY-SA and
 * carry an attribution obligation — see public/crafts/ATTRIBUTION.md, which
 * the explainer panel links. Do not add an image here without adding its row
 * there.
 *
 * `hint` is the sentence a visitor can read aloud if they would rather not
 * improvise. It is written the way a seller actually speaks to the app:
 * what it is, what it is made of, how big, how long it took, the price.
 */

export interface Craft {
  readonly slug: string;
  readonly label: string;
  readonly hint: string;
}

/**
 * Order matters: the first few are where a judge's eye and thumb land.
 *
 * The live pipeline's subject gate (backend/app/services/vision/pipeline.py,
 * `assess_subject`) passes jewellery, metalwork, woodwork and other as they
 * are, so those lead and a first try ends in a finished listing. The rest are
 * photographed in context - a potter's yard, a loom, a wall - and the gate
 * correctly asks for a retake, which is a real outcome worth being able to
 * see, but not the one to meet first. Re-measure before reordering:
 * run ImageStation().process_image over public/crafts/*.jpg.
 */
export const CRAFTS: readonly Craft[] = [
  {
    slug: 'jewellery',
    label: 'Jewellery',
    hint: 'This is a set of red bridal bangles. They are lac and glass work, made over two days, and the price is eighteen hundred rupees.',
  },
  {
    slug: 'metalwork',
    label: 'Metalwork',
    hint: 'This is a brass hookah base, made by hand. It is about nine inches tall and took a week. The price is four thousand rupees.',
  },
  {
    slug: 'woodwork',
    label: 'Wood carving',
    hint: 'This is a carved wooden panel made from sheesham wood. It is one foot across, took me six days, and I sell it for two thousand five hundred.',
  },
  {
    slug: 'other',
    label: 'Sindoor boxes',
    hint: 'These are small wooden sindoor boxes painted by hand. Each is three inches across, takes an afternoon, and costs two hundred rupees.',
  },
  {
    slug: 'pottery',
    label: 'Pottery',
    hint: 'This is a clay water pot I threw on the wheel. It holds about two litres and takes me half a day. I want twelve hundred rupees for it.',
  },
  {
    slug: 'weaving',
    label: 'Handloom',
    hint: 'This is a cotton shawl woven on my handloom in Banaras. It is two metres long, took four days, and the price is three thousand rupees.',
  },
  {
    slug: 'embroidery',
    label: 'Embroidery',
    hint: 'This is hand embroidery from Jodhpur done on cotton cloth. It is a metre square, took me five days, and costs two thousand two hundred.',
  },
  {
    slug: 'painting',
    label: 'Madhubani',
    hint: 'This is a Madhubani painting on handmade paper, done with natural colours. It is A3 size, took three days, and I sell it for sixteen hundred.',
  },
  {
    slug: 'leather',
    label: 'Leather',
    hint: 'These are Kolhapuri chappals made from buffalo leather, stitched by hand. Size eight, two days of work, nine hundred rupees a pair.',
  },
  {
    slug: 'bamboo',
    label: 'Bamboo',
    hint: 'This is a bamboo basket woven from cane from Purulia. It is a foot wide, takes a full day, and the price is six hundred rupees.',
  },
] as const;

export const CRAFT_BY_SLUG = new Map(CRAFTS.map((c) => [c.slug, c]));

export const craftImage = (slug: string) => `${import.meta.env.BASE_URL}crafts/${slug}.jpg`;

/** Marks a photo the visitor supplied rather than one of ours. */
export const UPLOAD_SLUG = 'upload';
