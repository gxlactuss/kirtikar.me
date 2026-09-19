/**
 * Runtime switches that change how the demo sources its data.
 *
 * These are read at call time rather than captured once, so a page opened
 * with `?demo=1` behaves the same as a build made with the env flag set.
 */

/**
 * Skip the network entirely and replay a recorded run.
 *
 * Set `VITE_FORCE_FIXTURES=1` at build time, or open the site with `?demo=1`.
 * The query string wins where both are present — including `?demo=0`, which
 * forces the live path back on — so a deployed build can be shown offline,
 * or debugged against the real backend, without rebuilding either time.
 */
export function forceFixtures(): boolean {
  const param = new URLSearchParams(window.location.search).get('demo');
  if (param !== null) return param !== '0';
  return import.meta.env.VITE_FORCE_FIXTURES === '1';
}
