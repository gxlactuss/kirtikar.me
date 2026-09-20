#!/usr/bin/env python3
"""Trace the Kirtikar logo into per-petal SVG paths for the opening screen.

The artwork ships as a flat JPEG, which is no use for an animation that has
to fly each petal off in its own direction. This separates it by ink colour,
crack-follows every boundary, smooths out the JPEG jitter, and fits cubics
through what is left — keeping sharp corners sharp, which is the one place
the eye can tell a trace from the original.

Rewrites src/intro/mark.ts in place.

    python3 -m venv .venv && .venv/bin/pip install numpy scipy pillow
    .venv/bin/python tools/trace-logo.py
"""
import json, math
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage

SRC = str(Path(__file__).with_name('logo-source.jpeg'))
im = Image.open(SRC).convert('RGB')
a = np.asarray(im).astype(float)

PAL = [('bg',(240,240,240)), ('navy',(20,62,99)), ('terra',(205,100,60)), ('steel',(72,115,150))]
ref = np.array([c for _,c in PAL], float)
idx = ((a[:,:,None,:]-ref[None,None,:,:])**2).sum(-1).argmin(-1)

def mask_for(name):
    i = [n for n,_ in PAL].index(name)
    return idx == i

def clean(m, r=2):
    """Close single-pixel JPEG noise, then drop specks."""
    m = ndimage.binary_closing(m, np.ones((r,r)))
    m = ndimage.binary_opening(m, np.ones((r,r)))
    return m

def trace(mask):
    """Crack-follow every boundary loop. Outer loops come out clockwise
    (y down), holes counter-clockwise — exactly what even-odd fill wants."""
    m = np.pad(mask, 1)
    ys, xs = np.nonzero(m)
    edges = {}
    def add(p, q):
        edges.setdefault(p, []).append(q)
    for y, x in zip(ys, xs):
        if not m[y-1, x]: add((x, y),     (x+1, y))
        if not m[y, x+1]: add((x+1, y),   (x+1, y+1))
        if not m[y+1, x]: add((x+1, y+1), (x, y+1))
        if not m[y, x-1]: add((x, y+1),   (x, y))
    loops = []
    while edges:
        start = next(iter(edges))
        loop = [start]
        cur = start
        while True:
            outs = edges.get(cur)
            if not outs:
                break
            nxt = outs.pop()
            if not outs: del edges[cur]
            if nxt == start:
                break
            loop.append(nxt)
            cur = nxt
        if len(loop) > 8:
            loops.append([(x-1, y-1) for x, y in loop])   # undo the pad
    return loops

def presmooth(loop, w=7):
    """Circular moving average over the crack-followed boundary.

    The source is a JPEG, so its edges carry compression jitter of a pixel or
    two. Left in, RDP faithfully preserves that jitter as visible lumps along
    the letter curves; averaging it out first is what makes the traced
    outlines read as drawn rather than scanned."""
    P = np.asarray(loop, float)
    n = len(P)
    if n < w * 2: return loop
    k = np.arange(-(w//2), w//2 + 1)
    S = sum(np.roll(P, -i, axis=0) for i in k) / len(k)
    return [tuple(q) for q in S]


def rdp(pts, eps):
    if len(pts) < 3: return pts
    keep = np.zeros(len(pts), bool); keep[0] = keep[-1] = True
    stack = [(0, len(pts)-1)]
    P = np.asarray(pts, float)
    while stack:
        i, j = stack.pop()
        if j - i < 2: continue
        seg = P[j] - P[i]
        L = math.hypot(*seg)
        if L == 0:
            d = np.hypot(*(P[i+1:j] - P[i]).T)
        else:
            d = np.abs(seg[0]*(P[i+1:j,1]-P[i,1]) - seg[1]*(P[i+1:j,0]-P[i,0])) / L
        k = int(d.argmax())
        if d[k] > eps:
            k += i + 1
            keep[k] = True
            stack += [(i, k), (k, j)]
    return [tuple(p) for p in P[keep]]

def catmull(pts, tension=1.0, corner_deg=118):
    """Closed Catmull-Rom through pts, emitted as SVG cubics.

    A vertex whose interior angle is sharper than `corner_deg` is treated as a
    corner: its tangent is dropped so the curve arrives at a point. Without
    this the spline rounds off the diamond cut-outs and the petal tips, which
    is the one place the eye notices a trace is not the original."""
    n = len(pts)
    P = [np.asarray(p, float) for p in pts]

    def tangent(i):
        a, b, c = P[(i-1) % n], P[i], P[(i+1) % n]
        u, v = a - b, c - b
        lu, lv = np.hypot(*u), np.hypot(*v)
        if lu == 0 or lv == 0:
            return np.zeros(2)
        cosang = float(np.clip(np.dot(u, v) / (lu * lv), -1, 1))
        if math.degrees(math.acos(cosang)) < corner_deg:
            return np.zeros(2)          # corner
        return (c - a) / 6 * tension

    T = [tangent(i) for i in range(n)]
    out = [f'M{P[0][0]:.1f} {P[0][1]:.1f}']
    for i in range(n):
        j = (i+1) % n
        c1, c2 = P[i] + T[i], P[j] - T[j]
        out.append(f'C{c1[0]:.1f} {c1[1]:.1f} {c2[0]:.1f} {c2[1]:.1f} {P[j][0]:.1f} {P[j][1]:.1f}')
    out.append('Z')
    return ''.join(out)

def shape_path(mask, eps, sx, sy, k):
    segs = []
    for loop in trace(mask):
        if len(loop) < 24: continue
        loop = presmooth(loop)
        s = rdp(loop + [loop[0]], eps)[:-1]
        if len(s) < 4: continue
        s = [((x - sx) * k, (y - sy) * k) for x, y in s]
        segs.append(catmull(s))
    return ''.join(segs)

# --- the mark: split each colour into its own components ---
navy  = clean(mask_for('navy'))
terra = clean(mask_for('terra'))
steel = clean(mask_for('steel'))

MARK_BOTTOM = 690        # below this the navy pixels are the "Kirtikar" wordmark
mark_navy = navy.copy(); mark_navy[MARK_BOTTOM:, :] = False

def components(m, minpx=800):
    lab, n = ndimage.label(m)
    out = []
    for j in range(1, n+1):
        c = lab == j
        if c.sum() < minpx: continue
        ys, xs = np.nonzero(c)
        out.append((c, xs.min(), xs.max(), ys.min(), ys.max(), int(c.sum())))
    out.sort(key=lambda t: -t[5])
    return out

pieces = []   # (id, colour, mask)
for c,*_ in components(mark_navy):        pieces.append(('base', 'navy', c))
for c, x0, x1, y0, y1, n in components(terra, 1000):
    pid = 'centre' if n > 30000 else 'seed' if n < 4000 else ('petalR' if x0 > 760 else 'petalL')
    pieces.append((pid, 'terra', c))
for c, x0, *_ in components(steel):
    pieces.append(('leafR' if x0 > 760 else 'leafL', 'steel', c))

# common viewBox over the whole mark
allmask = np.zeros_like(navy)
for _, _, c in pieces: allmask |= c
ys, xs = np.nonzero(allmask)
sx, sy = xs.min(), ys.min()
w, h = xs.max()-sx+1, ys.max()-sy+1
K = 1000.0 / w
print('mark viewBox 0 0 %.1f %.1f' % (w*K, h*K))

INK = {'navy': '#123e63', 'terra': '#cd643c', 'steel': '#48738f'}
out = {}
for pid, col, c in pieces:
    d = shape_path(c, 2.0, sx, sy, K)
    ys2, xs2 = np.nonzero(c)
    out[pid] = dict(
        fill=INK[col],
        d=d,
        # centroid in viewBox units — the animation pivots each petal here
        cx=round(float(xs2.mean()-sx)*K, 1),
        cy=round(float(ys2.mean()-sy)*K, 1),
    )
    print(f'{pid:8s} {col:6s} {len(d):6d} chars')

meta = dict(vbw=round(w*K,1), vbh=round(h*K,1), pieces=out)


# --- the wordmark: traced too, so the hero stays crisp at any size ---
word = navy.copy(); word[:MARK_BOTTOM, :] = False
word = clean(word)
ys, xs = np.nonzero(word)
wsx, wsy = xs.min(), ys.min()
ww, wh = xs.max()-wsx+1, ys.max()-wsy+1
WK = 1000.0 / ww
wd = shape_path(word, 2.0, wsx, wsy, WK)
print('word viewBox 0 0 %.1f %.1f  %d chars' % (ww*WK, wh*WK, len(wd)))
meta['word'] = dict(vbw=round(ww*WK,1), vbh=round(wh*WK,1), d=wd, fill=INK['navy'])


# --- emit the TS module the intro imports ---
ORDER = ['base', 'leafL', 'leafR', 'petalL', 'petalR', 'centre', 'seed']
lines = ['''/* GENERATED — do not hand-edit.
 *
 * The Kirtikar logo, traced from the original artwork into one path per
 * petal so the opening screen can fly them apart individually. Regenerate
 * with tools/trace-logo.py if the artwork ever changes.
 *
 * Paths are in a 0 0 {vbw} {vbh} viewBox; `cx`/`cy` are each piece's
 * centroid in those units, which is the pivot the drift animates around. */

export interface MarkPiece {{
  readonly id: string;
  readonly fill: string;
  readonly d: string;
  readonly cx: number;
  readonly cy: number;
}}

export const MARK_VIEWBOX = {{ w: {vbw}, h: {vbh} }} as const;

/** Painted back to front: base sweep first, seed dot last. */
export const MARK_PIECES: readonly MarkPiece[] = ['''.format(vbw=meta['vbw'], vbh=meta['vbh'])]
for k in ORDER:
    p = out[k]
    lines.append(f"  {{ id: '{k}', fill: '{p['fill']}', cx: {p['cx']}, cy: {p['cy']}, d: '{p['d']}' }},")
w = meta['word']
lines.append(f'''];

export const WORD_VIEWBOX = {{ w: {w['vbw']}, h: {w['vbh']} }} as const;

export const WORD_FILL = '{w['fill']}';

/** The "Kirtikar" wordmark as one even-odd path. */
export const WORD_PATH =
  '{w['d']}';
''')
dest = Path(__file__).resolve().parents[1] / 'src' / 'intro' / 'mark.ts'
dest.write_text('\n'.join(lines))
print('wrote', dest)
