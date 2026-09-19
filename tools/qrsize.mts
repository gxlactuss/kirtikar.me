import { buyerUrl, encodePayload, buildPayload } from '../src/util/qrpayload.ts';
import type { Listing } from '../src/api/types.ts';

const listing = {
  id: '5555fe14-3d26-45f9-a37f-8d151f222f5d',
  client_item_id: 'x',
  state: 'ready',
  title: 'Handcrafted Bidri-Style Brass Hookah Base with Silver Floral Inlay',
  description:
    'This exquisite bell-shaped hookah base is handcrafted using traditional metal inlay techniques reminiscent of Bidriware. The artisan meticulously hand-carves intricate floral motifs into the darkened alloy body.',
  image_urls: [
    'https://krs-kaustubh-kirtikar-api.hf.space/api/v1/listings/5555fe14-3d26-45f9-a37f-8d151f222f5d/media/d38259cd-6737-4e88-800d-9bca24978d00?v=1789814934',
  ],
  fact_sheet: {
    material: 'Brass with Silver Inlay', size: '9 inches (height)',
    colour: 'Black, Silver', technique: 'Bidriware (Metal Inlay Art)', origin: null,
    quantity: 1, price_in_paise: 400000, hours_to_make: null,
    material_cost_in_paise: null, is_one_of_a_kind: false,
  },
  suggestions: [], follow_up_question: null,
  suggested_price_in_paise: 400000, price_floor_in_paise: 360000,
  preview_url: null, photo_consent: true, story_consent: true, views: 0,
  used_live_model: true,
} as Listing;

const origin = 'https://kirtikar.me';
for (const limit of [180, 120, 90, 0]) {
  const enc = encodePayload(buildPayload(listing, 400000, listing.image_urls, limit));
  console.log(`desc<=${String(limit).padStart(3)}  url=${(origin+'/?p='+enc).length} chars`);
}
console.log('chosen:', buyerUrl(origin, listing, 400000, listing.image_urls).length, 'chars');
