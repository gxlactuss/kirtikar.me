import { useEffect, useRef, useState } from 'react';

import css from './DevProof.module.css';

/**
 * Scaffold verification, not product. Confirms three things before any real
 * screen exists:
 *   1. every AppColors token resolves to the right hex,
 *   2. the type scale renders at the Dart's exact sizes,
 *   3. the viewport really is the width the picker claims, so the frame
 *      reflows rather than scaling.
 *
 * Deleted once DemoApp lands in step 3.
 */

const COLORS = [
  ['terracotta', '#894500'],
  ['primary-pressed', '#6E3700'],
  ['cream', '#FEF5EC'],
  ['marigold', '#C98A3E'],
  ['ink', '#3A2415'],
  ['muted', '#7A5C42'],
  ['success', '#5B7535'],
  ['success-pressed', '#475C29'],
  ['danger', '#A4432A'],
  ['surface', '#FDECE0'],
  ['border', '#E8D5C0'],
  ['success-tint', '#EEF2E2'],
  ['warning-tint', '#FAF0D8'],
  ['danger-tint', '#F7E6DF'],
] as const;

const TYPE = [
  ['displaySmall', '34/1.2/700'],
  ['headlineMedium', '28/1.25/700'],
  ['headlineSmall', '24/1.3/600'],
  ['titleLarge', '21/1.3/600'],
  ['bodyLarge', '20/1.45/400'],
  ['bodyMedium', '18/1.45/400'],
  ['labelLarge', '20/1.2/600'],
  ['subtitle', '17/1.35/400'],
] as const;

export function DevProof() {
  const ref = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState(0);

  // Reads the element's real width. If this tracks the picker, the frame is
  // resizing; if it stays at 360 while the label says 320, it is scaling.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      if (entry) setMeasured(Math.round(entry.contentRect.width));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div className={css.root} ref={ref}>
      <p className={css.measure}>
        Viewport content box: <strong>{measured}px</strong> — this number must move
        when you change size.
      </p>

      <section className={css.section}>
        <h2 className={css.sectionTitle}>AppColors</h2>
        <div className={css.swatches}>
          {COLORS.map(([name, hex]) => (
            <div className={css.swatch} key={name}>
              <div className={css.chip} style={{ background: `var(--${name})` }} />
              <div className={css.swatchName}>{name}</div>
              <div className={css.swatchHex}>{hex}</div>
            </div>
          ))}
        </div>
      </section>

      <hr className={css.rule} />

      <section className={css.section}>
        <h2 className={css.sectionTitle}>Type scale</h2>
        {TYPE.map(([cls, spec]) => (
          <div key={cls}>
            <div className={`${cls} wholeWord`}>Hand-thrown blue pottery jug</div>
            <div className={css.measure}>
              {cls} · {spec}
            </div>
          </div>
        ))}
      </section>

      <hr className={css.rule} />

      <section className={css.section}>
        <h2 className={css.sectionTitle}>Tap targets (64px minimum)</h2>
        <button type="button" className={css.button}>
          Take the photo
        </button>
        <button type="button" className={`${css.button} ${css.buttonGreen}`}>
          These photos are good
        </button>
        <p className={css.measure}>
          The green one is the BigActionButton rule: a primary button whose icon is
          check, arrow_forward or play_arrow renders success green, not terracotta.
        </p>
      </section>
    </div>
  );
}
