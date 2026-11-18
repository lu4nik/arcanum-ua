#!/usr/bin/env python3
"""Cyrillic for morph30 built from the game's own Morpheus Latin glyphs.

Instead of rendering a TTF (genfont.py), every Cyrillic letter is assembled
from the original bitmap glyphs of the player's copy: shared shapes are copied
(А=A, В=B ...), others are mirrored, cut or combined (Я = mirrored R,
Л = A without its bar, П = N without its tail ...), and the few missing
strokes are drawn in the font's stem width. Lowercase is small caps, as in
the original. Nothing from the game is stored in the repo: the recipe runs
on the local .dat.

Usage:
  python3 tools/morphcyr.py [--font morph30|morph15|morph15_system]   # -> fonts/<font>.art
  python3 tools/morphcyr.py --preview out.png     # glyph sheet + sample lines
  python3 tools/morphcyr.py --dat PATH --base fonts/morph30font.art --out X.art
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdat, artfont
from PIL import Image, ImageOps, ImageChops, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAT = '/Applications/Arcanum/arcanum1.dat'
# Metrics, set by setup() from the original font (values below: morph30).
H = 33             # frame height
BASE = 27          # last ink row of caps and small caps
TOP = {'C': 5, 's': 10}   # first ink row: caps / small caps
HOTY = 28
K = 1.0            # cap height / morph30 cap height: scales every drawn offset
SS = 8             # supersampling for drawn strokes

FONTS = {  # name -> (archive, path inside, our font file)
    'morph30': ('arcanum1.dat', 'art/interface/morph30font.art', 'morph30font.art'),
    'morph15': ('arcanum1.dat', 'art/interface/morph15font.art', 'morph15font.art'),
    'morph15_system': ('tig.dat', 'art/morph15font.art', 'morph15font_system.art'),
}


def u(v):
    """An offset designed at morph30 size, scaled to the current font."""
    return v * K


def setup(art):
    global H, BASE, TOP, HOTY, K
    def rows(ch):
        fr = art.frames[ord(ch) - 31]
        r = [y for y in range(fr['h']) if any(fr['pixels'][y * fr['w']:(y + 1) * fr['w']])]
        return r[0], r[-1]
    H = art.frames[ord('H') - 31]['h']
    HOTY = art.frames[ord('H') - 31]['hot_y']
    ct, BASE = rows('H')
    TOP = {'C': ct, 's': rows('h')[0]}
    K = (BASE - ct) / 22


# ---------------------------------------------------------------- pixels

class Font:
    def __init__(self, art):
        self.art = art
        self.pal = next(p for p in art.palettes if p)
        # grey ramp: the non-black grey palette indices the original glyphs use
        used = set()
        for fr in art.frames:
            used.update(fr['pixels'])
        grey = lambda v: ((v >> 16) & 255) == ((v >> 8) & 255) == (v & 255) and v & 255
        self.ramp = sorted(((self.pal[i] >> 16) & 255, i) for i in used if i > 1 and grey(self.pal[i]))

    def glyph(self, byte):
        fr = self.art.frames[byte - 31]
        im = Image.new('L', (fr['w'], fr['h']))
        im.putdata([((self.pal[p] >> 16) & 255) if p > 1 else 0 for p in fr['pixels']])
        if fr['h'] != H:
            c = Image.new('L', (fr['w'], H)); c.paste(im, (0, 0)); im = c
        return G(im, fr['hot_x'])

    def frame(self, g):
        im = g.im
        px = bytearray()
        for v in im.getdata():
            if v < 10:
                px.append(0)
            else:
                px.append(min(self.ramp, key=lambda r: abs(r[0] - v))[1])
        return dict(w=im.width, h=im.height, hot_x=g.adv, hot_y=HOTY, ox=0, oy=0, pixels=px)


class G:
    """Glyph: L image (coverage), advance."""
    def __init__(self, im, adv=None):
        self.im = im
        self.adv = adv if adv is not None else self.right() + max(1, round(u(2)))

    def copy(self):
        return G(self.im.copy(), self.adv)

    def cols(self):
        w = self.im.width
        d = self.im.load()
        return [x for x in range(w) if any(d[x, y] > 40 for y in range(H))]

    def right(self):
        c = self.cols()
        return c[-1] + 1 if c else 0

    def tight(self, pad=None):
        """Shift ink to x=0. Advance: kept relative to the ink start (tails of
        K/R overhang the next letter, as in the original), or ink width + pad."""
        c = self.cols()
        if not c:
            return self
        im = self.im.crop((c[0], 0, c[-1] + 1, H))
        return G(im, im.width + pad if pad is not None else self.adv - c[0])

    def widen(self, w):
        if w <= self.im.width:
            return self
        im = Image.new('L', (w, H)); im.paste(self.im, (0, 0))
        return G(im, self.adv)

    def stems(self, top, base=None, frac=0.8):
        """Vertical stems: column runs dark in >frac of rows top..base."""
        base = BASE if base is None else base
        d = self.im.load()
        n = base - top + 1
        good = [x for x in range(self.im.width)
                if sum(d[x, y] > 128 for y in range(top, base + 1)) >= frac * n]
        runs = []
        for x in good:
            if runs and x == runs[-1][1] + 1:
                runs[-1][1] = x
            else:
                runs.append([x, x])
        return [tuple(r) for r in runs]


def mirror(g):
    return G(ImageOps.mirror(g.im)).tight()


def over(*parts):
    """Overlay (glyph, dx, dy) parts by max coverage."""
    w = max(p[0].im.width + p[1] for p in parts)
    im = Image.new('L', (w, H))
    for g, dx, dy in parts:
        layer = Image.new('L', (w, H))
        layer.paste(g.im, (dx, dy))
        im = ImageChops.lighter(im, layer)
    return G(im).tight()


def erase(g, x0, y0, x1, y1):
    g = g.copy()
    ImageDraw.Draw(g.im).rectangle((x0, y0, x1, y1), fill=0)
    return g


def keep(g, x0, y0, x1, y1):
    """Only the given box survives (same canvas)."""
    im = Image.new('L', g.im.size)
    im.paste(g.im.crop((x0, y0, x1 + 1, y1 + 1)), (x0, y0))
    return G(im, g.adv)


def shift(g, dx, dy):
    im = Image.new('L', (g.im.width + max(dx, 0), H))
    im.paste(g.im, (dx, dy))
    return G(im, g.adv + dx)


def draw(g, fn, w=None):
    """fn(ImageDraw, scale) draws strokes in supersampled space."""
    w = w or g.im.width
    big = Image.new('L', (w * SS, H * SS))
    fn(ImageDraw.Draw(big), SS)
    small = big.resize((w, H), Image.BOX)
    base = g.widen(w)
    return G(ImageChops.lighter(base.im, small), base.adv)


def rect(x0, y0, x1, y1):
    """Filled box in pixel coords (inclusive); fractional edges antialias."""
    def fn(d, s):
        d.rectangle((x0 * s, y0 * s, (x1 + 1) * s - 1, (y1 + 1) * s - 1), fill=255)
    return fn


def line(x0, y0, x1, y1, width):
    def fn(d, s):
        d.line((x0 * s, y0 * s, x1 * s, y1 * s), fill=255, width=int(width * s))
    return fn


def arc(box, start, end, width):
    def fn(d, s):
        d.arc(tuple(v * s for v in box), start, end, fill=255, width=int(width * s))
    return fn


def scale_to(g, top_from, top_to):
    """Scale a glyph so its ink rows top_from..BASE fit top_to..BASE."""
    hs, ht = BASE - top_from + 1, BASE - top_to + 1
    k = ht / hs
    w = max(1, round(g.im.width * k))
    band = g.im.crop((0, top_from, g.im.width, BASE + 1)).resize((w, ht), Image.LANCZOS)
    im = Image.new('L', (w, H)); im.paste(band, (0, top_to))
    # keep strokes as dark as the original after the blur
    im = im.point(lambda v: min(255, int(v * 1.25)))
    return G(im).tight()


# ---------------------------------------------------------------- recipes

def build(f):
    L = lambda ch: f.glyph(ord(ch))
    B = lambda b: f.glyph(b)
    out = {}
    r = lambda v: max(1, round(u(v)))       # integer offset, at least 1 px

    def ink_top(g):
        d = g.im.load()
        return min(y for y in range(H) for x in range(g.im.width) if d[x, y] > 40)

    for case in ('C', 's'):
        top = TOP[case]
        up = case == 'C'
        src = lambda a, b: L(a if up else b)
        o = {}
        for cy, (a, b) in {'А': 'Aa', 'В': 'Bb', 'Е': 'Ee', 'К': 'Kk', 'М': 'Mm', 'Н': 'Hh',
                           'О': 'Oo', 'Р': 'Pp', 'С': 'Cc', 'Х': 'Xx', 'І': 'Ii'}.items():
            o[cy] = src(a, b).tight()
        # К is far more frequent in Ukrainian than K in English: clip the long
        # tail so it stops just past the advance instead of running under the next letter
        Kc = o['К']
        o['К'] = erase(Kc, Kc.adv + r(1), 0, Kc.im.width, H - 1).tight()
        o['К'].adv = Kc.adv
        o['Ї'] = B(0xCF if up else 0xEF).tight()
        o['Ё'] = B(0xCB if up else 0xEB).tight()
        T, three = L('T').tight(), L('3').tight()
        o['Т'] = T if up else scale_to(T, ink_top(T), top - r(3))
        o['З'] = three if up else scale_to(three, ink_top(three), top)

        # Н-based: two stems without the bar
        Hg = o['Н']
        st = Hg.stems(top)
        (l0, l1), (r0, r1) = st[0], st[-1]
        sw = l1 - l0 + 1
        lw = max(sw - 0.6, 1.3)               # drawn stroke width
        mid = (top + BASE) // 2
        bar_rows = [y for y in range(top + r(3), BASE - r(3))
                    if all(Hg.im.getpixel((x, y)) > 100 for x in range(l1 + 1, r0))]
        b0, b1 = (min(bar_rows), max(bar_rows)) if bar_rows else (mid - 1, mid + 1)
        bare = erase(Hg, l1 + 1, b0 - 1, r0 - 1, b1 + 1)

        # И: bare H + diagonal from bottom-left to top-right
        o['И'] = draw(bare, line(l1 + 0.5, BASE - u(1.5), r0 + 0.5, top + u(1.5), lw))
        # Й: И + breve
        by = top - u(5 if up else 6)
        cx = (l0 + r1 + 1) / 2
        o['Й'] = draw(o['И'], arc((cx - u(4.5), by - u(3), cx + u(4.5), by + u(3)), 20, 160,
                                  max(u(1.6), 1.1)))

        # Ц, Ш, Щ: stems + baseline bar (+ tail)
        bt = max(u(1.6), 1.0)
        def baseline_bar(g, x0, x1):
            return draw(g, rect(x0, BASE - bt, x1, BASE))
        tail = lambda g, x: draw(g, line(x + sw / 2, BASE - u(1), x + sw / 2 + u(1.2), BASE + u(4.5),
                                         max(sw - 0.8, 1.2)), w=g.im.width + r(3))
        c = baseline_bar(erase(bare, r1 + 1, BASE - r(2), bare.im.width, BASE), l0, r1)
        o['Ц'] = tail(c, r0).tight()
        o['Ц'].adv -= r(2)
        gap = r0 - l1 - 1
        D = round((r0 - l0) * 0.8)
        right = keep(bare, l1 + gap // 2 + 1, 0, bare.im.width - 1, H - 1)
        left = keep(bare, 0, 0, l1 + gap // 2, H - 1)
        mstem = keep(bare, max(l0 - r(2), 0), 0, l1 + r(2), H - 1)
        mx = round((l0 + r0 + D) / 2) - l0
        w3 = over((left, 0, 0), (shift(right, D, 0), 0, 0), (shift(mstem, mx, 0), 0, 0))
        st3 = w3.stems(top)
        sh_ = erase(w3, st3[-1][1] + 1, BASE - r(2), w3.im.width, BASE)
        sh_ = erase(sh_, 0, BASE - r(2), st3[0][0] - 1, BASE)  # drop outer foot serifs
        o['Ш'] = baseline_bar(sh_, st3[0][0], st3[-1][1]).tight()
        o['Щ'] = tail(o['Ш'].copy(), o['Ш'].stems(top)[-1][0]).tight()
        o['Щ'].adv -= r(2)

        # Ч: right stem + short left stem + curve
        ch = erase(erase(bare, 0, mid + 1, l1 + r(2), H - 1), 0, BASE - r(3), r0 - r(2), H - 1)
        o['Ч'] = draw(ch, arc((l0 + sw / 2 - 0.3, mid - u(9), r0 + sw / 2, mid + u(3)), 0, 180, lw)).tight()

        # П: N without its descender; foot serif on the right stem like the left one
        n = src('N', 'n').tight()
        n = erase(n, 0, BASE + 1, n.im.width, H - 1)
        ns = n.stems(top)
        if ns:
            rs0, rs1 = ns[-1]
            n = draw(n, rect(rs0 - u(1.5), BASE - max(u(0.8), 0.6), rs1 + u(1.5), BASE))
        o['П'] = n.tight()

        # Л: A without the bar (cleared between the legs, interpolated)
        A = o['А']
        aw = A.im.width
        lam = A.copy()
        d = lam.im.load()

        def runs_of(y):
            rs, cur = [], None
            for x in range(aw):
                if d[x, y] > 100:
                    if cur and x == cur[1] + 1:
                        cur[1] = x
                    else:
                        cur = [x, x]; rs.append(cur)
            return rs
        legs = {}
        for y in range(top, BASE + 1):
            rr = runs_of(y)
            if len(rr) >= 2:
                legs[y] = (rr[0][1], rr[-1][0])
        bar = [y for y in range(top + r(5), BASE - r(2)) if y not in legs]
        if bar:
            ya, yb = bar[0] - 1, bar[-1] + 1
            (la, ra), (lb, rb) = legs.get(ya, legs[max(k for k in legs if k < bar[0])]), \
                legs.get(yb, legs[min(k for k in legs if k > bar[-1])])
            for y in range(ya - 1, yb + 2):
                t = (y - ya) / max(1, yb - ya)
                le = round(la + (lb - la) * t)
                re = round(ra + (rb - ra) * t)
                for x in range(le + 1, re):
                    d[x, y] = 0
        o['Л'] = lam
        # Д: Л + base bar with feet
        p2 = r(2)
        fw = sw if K >= 1 else lw        # foot width
        db = bt if K >= 1 else bt - 0.5  # small sizes: rect rows are inclusive, keep it light
        dd = erase(lam, 0, BASE - r(3), aw, BASE)
        dd = shift(dd, p2, 0)
        dd = draw(dd, rect(p2 - 1, BASE - db, aw + p2, BASE), w=aw + 2 * p2 + 1)
        dd = draw(dd, rect(p2 - 1, BASE, p2 - 2 + fw, BASE + u(4)))
        dd = draw(dd, rect(aw + p2 - fw + 1, BASE, aw + p2, BASE + u(4)))
        o['Д'] = dd.tight()

        # Г: F without its middle arm; Ґ: Г + upturn
        F = src('F', 'f').tight()
        fst = F.stems(top)
        fs1 = fst[0][1] if fst else r(3)
        inked = lambda y: any(F.im.getpixel((x, y)) > 100 for x in range(fs1 + r(3), F.im.width))
        y = top
        while y < BASE and not inked(y):  # find the top arm ...
            y += 1
        while y < BASE and inked(y):      # ... and skip it with its serif drop
            y += 1
        frows = [yy for yy in range(max(y, top + r(5)), BASE - r(3)) if inked(yy)]
        g_ = erase(F, fs1 + 1, min(frows) - 1, F.im.width, max(frows) + 1) if frows else F
        o['Г'] = g_.tight()
        gw = o['Г'].im.width
        uw = lw + 0.2 if K >= 1 else lw * 0.8
        o['Ґ'] = draw(o['Г'], rect(gw - uw, top - u(4), gw - 0.6, top + u(1))).tight()

        # Є: C + bar; Э: mirrored C + bar
        C = o['С']
        cw = C.im.width
        h1, h2 = max(u(1.2), 0.7), max(u(0.6), 0.5)
        o['Є'] = draw(C, rect(sw - 1, mid - h1, cw * 0.62, mid + h2)).tight()
        o['Э'] = draw(mirror(C), rect(cw * 0.38, mid - h1, cw - sw, mid + h2)).tight()

        # Я: mirrored R without the long tail below the baseline
        R = src('R', 'r').tight()
        o['Я'] = mirror(erase(R, 0, BASE + 1, R.im.width, H - 1))

        # Ж: mirrored K + K sharing the stem
        Kg = o['К']
        ks = Kg.stems(top)[0]
        Km = mirror(erase(Kg, Kg.adv, 0, Kg.im.width, H - 1))
        kms = Km.stems(top)[-1]
        o['Ж'] = over((Km, 0, 0), (Kg, kms[0] - ks[0], 0))
        o['Ж'].adv = kms[0] - ks[0] + Kg.adv

        # У: the deep cup of Morpheus Y, its vertical stem replaced by a diagonal
        # running down-left into a small foot (Y alone reads as Ү)
        Y = src('Y', 'y').tight()
        yd = Y.im.load()
        yw = Y.im.width

        def runs_y(y):
            rs, cur = [], None
            for x in range(yw):
                if yd[x, y] > 100:
                    if cur and x == cur[1] + 1:
                        cur[1] = x
                    else:
                        cur = [x, x]; rs.append(cur)
            return rs
        jy = next(y for y in range(top + r(6), BASE)
                  if len(runs_y(y)) == 1 and runs_y(y)[0][1] - runs_y(y)[0][0] <= sw + 2)
        jr = runs_y(jy)[0]
        jx = (jr[0] + jr[1]) / 2
        uy = erase(Y, 0, jy + 1, yw, H - 1)
        xl = r(2) + sw / 2
        if K >= 1:
            uy = draw(uy, line(jx + 0.5, jy - 0.5, xl, BASE - 0.4, lw))
        else:        # run past the baseline and cut, so the end is solid
            dxl = (xl - jx) / (BASE - jy + 0.5)
            uy = draw(uy, line(jx + 0.5, jy - 0.5, xl + dxl * 1.5, BASE + 1.5, lw))
            uy = erase(uy, 0, BASE + 1, uy.im.width, H - 1)
        if K >= 1:   # at small sizes the foot is a blob: end on the diagonal
            uy = draw(uy, rect(max(xl - sw - 0.5, 0), BASE - u(1), xl + sw * 0.8, BASE))
        o['У'] = uy.tight()
        o['У'].adv = Y.adv

        # Ф: O without its centre dot, split in half, a long stem between the halves
        O = o['О']
        ow = O.im.width
        Oh = O.copy()
        od = Oh.im.load()
        for y in range(top, BASE + 1):
            runs, cur = [], None
            for x in range(ow):
                if od[x, y] > 100:
                    if cur and x == cur[1] + 1:
                        cur[1] = x
                    else:
                        cur = [x, x]; runs.append(cur)
            if len(runs) >= 2:
                for x in range(runs[0][1] + 1, runs[-1][0]):
                    od[x, y] = 0
        half = ow // 2
        gap = sw + r(1)
        # small sizes: drop an empty inner column of the right half to keep names
        # within their rects (the left one is needed to keep the stem off the ring)
        cut = 0 if K >= 1 else 1
        lh = keep(Oh, 0, 0, half - 1, H - 1)
        rh = keep(Oh, half + cut, 0, ow - 1, H - 1)
        fo = over((lh, 0, 0), (shift(rh, gap - cut, 0), 0, 0))
        sx = half + (gap - sw) / 2 - 0.5
        o['Ф'] = draw(fo, rect(sx, top - u(3), sx + sw - 1, BASE + u(3))).tight()

        # Ь: P with the bowl moved to the bottom; Б, Ъ, Ы from it
        P = o['Р']
        pst = P.stems(top)[0]
        prow_end = max(y for y in range(top, BASE)
                       if any(P.im.getpixel((x, y)) > 100 for x in range(pst[1] + r(3), P.im.width)))
        bowl = keep(P, pst[1] + 1, top, P.im.width - 1, prow_end)
        stem = erase(P, pst[1] + 1, 0, P.im.width, H - 1)
        dy = BASE - prow_end
        bowl_dn = G(Image.new('L', P.im.size))
        bowl_dn.im.paste(bowl.im.crop((0, 0, P.im.width, H - dy)), (0, dy))
        soft = over((stem, 0, 0), (bowl_dn, 0, 0))
        o['Ь'] = soft
        E = o['Е']
        est = E.stems(top)[0]
        arm = keep(E, est[1] + 1, top - 1, E.im.width - 1, top + r(4))
        o['Б'] = over((soft, 0, 0), (arm, pst[0] - est[0], 0))
        Tg = T if up else o['Т']
        tst = Tg.stems(top)
        o['Ъ'] = over((keep(Tg, 0, 0, tst[0][0] - 1, top + r(4)), 0, 0), (soft, tst[0][0], 0)) if tst else soft
        Ig = o['І']
        o['Ы'] = over((soft, 0, 0), (Ig, soft.im.width + 1, 0))
        o['Ы'].adv = o['Ы'].im.width + r(2)
        # Ю: І + bar + О
        iw = Ig.im.width
        ist = Ig.stems(top)[0]
        ju = over((Ig, 0, 0), (O, iw + r(2), 0))
        o['Ю'] = draw(ju, rect(ist[1], mid - max(u(1), 0.7), iw + r(2) + 0.5, mid + h2)).tight()

        for k, g in o.items():
            out[k if up else k.lower()] = g
    return out


CYR = [chr(c) for c in range(0x410, 0x450)] + list('ЁёҐґЄєІіЇї')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--font', default='morph30', choices=sorted(FONTS))
    ap.add_argument('--game', default=os.path.dirname(DAT), help='game folder with the .dat files')
    ap.add_argument('--base', help='font whose non-Cyrillic cp1251 frames are kept (default: ours)')
    ap.add_argument('--out', help='default: fonts/<our font file>')
    ap.add_argument('--preview')
    a = ap.parse_args()
    dat_name, inner, ours = FONTS[a.font]
    dat = os.path.join(a.game, dat_name)
    e = next(e for e in tdat.read_entries(dat) if e[0] == inner)
    art = artfont.decode(tdat.read_file(dat, e))
    setup(art)
    orig = Font(art)
    glyphs = build(orig)
    base_path = a.base or os.path.join(ROOT, 'fonts', ours)
    base = artfont.decode(open(base_path, 'rb').read())
    for ch in CYR:
        if ch in glyphs:
            base.frames[ch.encode('cp1251')[0] - 31] = orig.frame(glyphs[ch])
    if a.preview:
        preview(base, orig, a.preview)
    else:
        out = a.out or os.path.join(ROOT, 'fonts', ours)
        open(out, 'wb').write(artfont.encode(base))
        print('wrote', out, len(glyphs), 'glyphs')


def preview(art, f, path, S=3):
    lines = ['АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ',
             'абвгґдеєжзиіїйклмнопрстуфхцчшщьюя',
             'Нова гра  Завантажити  Налаштування',
             'Вихід  Продовжити  Зберегти гру  Ще',
             'Щасливої дороги, Їжаче! Ґанок, Юрко, Ємність',
             'ЖУРНАЛ  ЧУТКИ  ЗАВДАННЯ  ЛЮДИ  БЮЛЕТЕНЬ  ФІЗИКА  ЦЕХ  ЩЕДРІСТЬ  ЇЖА  ҐРУНТ  ЄВА  ЙОД  ЯР',
             'New Game  Load Game  Options']
    pal = f.pal
    rows = []
    for t in lines:
        bs = t.encode('cp1251')
        w = sum(art.frames[b - 31]['hot_x'] for b in bs) + 8
        im = Image.new('RGB', (w, H), (28, 24, 20))
        x = 4
        for b in bs:
            fr = art.frames[b - 31]
            for y in range(fr['h']):
                for xx in range(fr['w']):
                    p = fr['pixels'][y * fr['w'] + xx]
                    if p > 1:
                        v = (pal[p] >> 16) & 255
                        im.putpixel((x + xx, y), (v, v, int(v * 0.92)))
            x += fr['hot_x']
        rows.append(im)
    W = max(r.width for r in rows) * S
    out = Image.new('RGB', (W, sum(r.height + 6 for r in rows) * S), (28, 24, 20))
    y = 0
    for r in rows:
        out.paste(r.resize((r.width * S, r.height * S), Image.NEAREST), (0, y))
        y += (r.height + 6) * S
    out.save(path)
    print('preview', path, out.size)


if __name__ == '__main__':
    main()
