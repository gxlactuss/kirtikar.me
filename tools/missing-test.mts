/* Tests for what step 3 asks, and what it sends. Pure logic, no DOM. */
import {
  afterPipeline,
  answersToPatch,
  applyLocally,
  missingFields,
  rupeesToPaise,
} from '../src/machine/missing.ts';
import type { Listing } from '../src/api/types.ts';
import { readFileSync } from 'node:fs';

let failures = 0;
const check = (name: string, ok: boolean, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures++;
};
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

const base: Listing = {
  id: 'x',
  client_item_id: 'y',
  state: 'ready',
  title: 'Brass lamp',
  description: 'A lamp.',
  image_urls: ['/a.jpg'],
  fact_sheet: {
    material: 'Brass',
    size: '9 inches',
    colour: 'Gold',
    technique: 'Casting',
    origin: null,
    quantity: 1,
    price_in_paise: 400000,
    hours_to_make: null,
    material_cost_in_paise: null,
    is_one_of_a_kind: false,
  },
  suggestions: [],
  follow_up_question: null,
  suggested_price_in_paise: 400000,
  price_floor_in_paise: 300000,
  preview_url: null,
  photo_consent: false,
  story_consent: false,
  views: 0,
  used_live_model: true,
};
const sug = (field: string, approved: boolean | null = null) => ({
  id: field,
  field,
  spoken_prompt: `did not mention ${field}`,
  text_if_accepted: field,
  approved,
});

// 1. Everything said: nothing to ask, straight to the product.
check('complete listing asks nothing', missingFields(base).length === 0);
check('complete listing goes to final', afterPipeline(base) === 'final');

// 2. Origin being empty alone is not a question; the server has to flag it.
check('unflagged empty origin is not asked', !missingFields(base).includes('origin'));
check(
  'flagged origin is asked',
  same(missingFields({ ...base, suggestions: [sug('origin')] }), ['origin']),
);

// 3. Price is filled with the recommendation when unsaid; the flag is what counts.
check(
  'flagged price is asked even with a value',
  same(missingFields({ ...base, suggestions: [sug('price')] }), ['price']),
);
check(
  'settled suggestion is not asked again',
  missingFields({ ...base, suggestions: [sug('price', true)] }).length === 0,
);

// 4. Empty core facts are asked, in a stable order.
const sparse: Listing = {
  ...base,
  fact_sheet: { ...base.fact_sheet, material: null, colour: '  ', price_in_paise: null },
  suggestions: [sug('size'), sug('origin')],
};
check(
  'sparse listing asks in order',
  same(missingFields(sparse), ['material', 'size', 'colour', 'origin', 'price']),
  missingFields(sparse).join(','),
);
check('sparse listing goes to missing', afterPipeline(sparse) === 'missing');

// 5. A halted run asks nothing and still stops at step 3 to say why.
const halted = { ...base, title: null, follow_up_question: 'Could not hear the voice note.' };
check('halted run asks no fields', missingFields(halted).length === 0);
check('halted run stops at missing', afterPipeline(halted) === 'missing');

// 6. Price parsing.
for (const [text, want] of [
  ['1200', 120000],
  ['1,200', 120000],
  ['₹ 1,200', 120000],
  ['Rs. 1200.50', 120050],
  ['1200 rupees', 120000],
  ['0', null],
  ['twelve hundred', null],
  ['12.345', null],
  ['', null],
] as const) {
  check(`rupeesToPaise(${JSON.stringify(text)})`, rupeesToPaise(text) === want, String(rupeesToPaise(text)));
}

// 7. The PATCH body: blank answers left out, price in paise, only allowed keys.
const patch = answersToPatch({ material: ' Brass ', size: '', colour: 'Red', price: '₹950' });
check('patch body', same(patch, { material: 'Brass', colour: 'Red', price: 95000 }), JSON.stringify(patch));
check('blank answers send nothing', same(answersToPatch({ size: '  ' }), {}));

// 8. Applying locally mirrors the server: values land, suggestions settle.
const applied = applyLocally(
  { ...base, suggestions: [sug('price'), sug('origin')] },
  { price: 95000, origin: 'Moradabad' },
);
check('local price lands in paise', applied.fact_sheet.price_in_paise === 95000);
check('local origin lands', applied.fact_sheet.origin === 'Moradabad');
check('answered suggestions settle', applied.suggestions.every((s) => s.approved === true));
check('nothing left to ask after answering', missingFields(applied).length === 0);

// 9. Every recorded fixture lands somewhere sensible.
const index = JSON.parse(readFileSync('public/fixtures/index.json', 'utf8')) as { slug: string }[];
for (const { slug } of index) {
  const fx = JSON.parse(readFileSync(`public/fixtures/${slug}/listing.json`, 'utf8'));
  const l = fx.listing as Listing;
  console.log(`      fixture ${slug.padEnd(11)} -> ${afterPipeline(l).padEnd(7)} asks [${missingFields(l).join(', ')}]`);
}

console.log(failures ? `\n${failures} FAILED` : '\nall passed');
process.exit(failures ? 1 : 0);
