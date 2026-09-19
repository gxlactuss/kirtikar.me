/* Invariant tests for PipelineTicker. Pure logic, no DOM, no browser. */
import { PipelineTicker, STAGES, SLOW_AFTER_MS } from '../src/machine/ticker.ts';
import type { Progress } from '../src/machine/types.ts';

let failures = 0;
const check = (name: string, ok: boolean, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
  if (!ok) failures++;
};

const make = () => new PipelineTicker(() => {}, STAGES, () => 0, () => 0, () => {});
const TOTAL = STAGES.reduce((n, s) => n + s.nominalMs, 0);

// 1. Never reaches 100% before the server confirms, however long we wait.
{
  const t = make();
  let worst = 0;
  let p!: Progress;
  for (let i = 0; i < 400; i++) {
    p = t.advance(1_000); // 400 seconds
    worst = Math.max(worst, p.overall);
  }
  check('never completes before finish()', !p.finished && worst <= 0.995,
        `max overall=${worst.toFixed(4)}`);
}

// 2. The last stage advances and is never reported complete, however long
//    the server stays silent. (Visible liveness past saturation is the CSS
//    shimmer on the active row, not this number.)
{
  const t = make();
  t.advance(TOTAL);
  const a = t.snapshot().stageProgress;
  t.advance(60_000);
  const b = t.snapshot().stageProgress;
  t.advance(600_000);
  const c = t.snapshot();
  check('last stage advances then holds below complete',
        b > a && c.stageProgress <= 0.99 && !c.finished && c.overall <= 0.995,
        `${a.toFixed(4)} -> ${b.toFixed(4)} -> ${c.stageProgress.toFixed(4)}, overall=${c.overall.toFixed(4)}`);
}

// 3. finish() completes everything, and a fast finish still runs stages out.
{
  const t = make();
  t.advance(2_000);            // server answered after 2s
  const before = t.snapshot();
  t.finish();
  // settleMs is max(1100, unfinished * 240); with 5 stages left that is 1200.
  const settle = t.advance(1_200);
  check('fast finish reaches 100%', settle.finished && settle.overall === 1,
        `done=${settle.done.filter(Boolean).length}/5`);
  check('fast finish had stages left to show',
        before.done.filter(Boolean).length < 5,
        `only ${before.done.filter(Boolean).length} were complete at finish()`);
}

// 4. The run-out is visible, not instant: stages complete progressively.
{
  const t = make();
  t.advance(2_000);
  t.finish();
  const seen = new Set<number>();
  for (let i = 0; i < 12; i++) seen.add(t.advance(100).done.filter(Boolean).length);
  check('run-out shows intermediate states', seen.size >= 3,
        `distinct completion counts: ${[...seen].sort((a,b)=>a-b).join(',')}`);
}

// 5. Slow flag fires at the threshold and not before.
{
  const t = make();
  const before = t.advance(SLOW_AFTER_MS - 1_000);
  const after = t.advance(2_000);
  check('slow flag fires only past the threshold', !before.slow && after.slow);
}

// 6. Stage order is monotonic; the bar never goes backwards.
{
  const t = make();
  let prev = -1, monotonic = true;
  for (let i = 0; i < 200; i++) {
    const p = t.advance(500);
    if (p.overall < prev - 1e-9) monotonic = false;
    prev = p.overall;
  }
  check('overall never decreases', monotonic);
}

console.log(failures === 0 ? '\nall invariants hold' : `\n${failures} FAILED`);
process.exit(failures === 0 ? 0 : 1);
