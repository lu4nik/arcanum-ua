#!/usr/bin/env python3
"""Cyrillic for zurich16 (journal tabs, newspaper rubrics) in the game's own style.

zurich16 is a 12 px condensed grotesque with 1 px stems and a grey halo, too
small for the cut-and-mirror tricks of morphcyr.py. Letters shared with Latin
are copied from the player's copy (А=A, В=B ... ї=ï); И, Я, Э are mirrored
N, R, Є; the rest are drawn here pixel by pixel in the same manner.

Pixel maps: ' ' empty, '.' ':' '+' '#' greys, '@' full ink. Each entry is
(first row, rows); the advance is the row width.

Usage:
  python3 tools/zurichcyr.py                    # -> fonts/zurich16font.art
  python3 tools/zurichcyr.py --preview out.png
"""
import os, sys, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdat, artfont, morphcyr as m
from PIL import Image, ImageOps

ROOT = m.ROOT
SHADE = {' ': 0, '.': 50, ':': 100, '+': 150, '#': 205, '@': 255}

CAPS = {  # rows 2..13 = cap height, 14..15 descenders
    'Г': (2, [":::.", "@@#:"] + ["@:  "] * 10),
    'Ґ': (0, ["   :", "  .@", "..:@", "@@@@"] + ["@:  "] * 10),
    'Б': (2, [":::::", "@@@@:"] + ["@:   "] * 3 + ["@@@#.", "@: +@", "@:  @", "@:  @", "@:  @", "@: +@", "@@@#."]),
    'Д': (2, ["  :::. ", "  #@@: ", "  @ @: ", "  @ @: ", "  @ @: ", "  @ @: ", "  @ @: ",
              " .@ @: ", " :# @: ", " @+ @: ", ".@: @: ", "@@@@@@:", "@:   @:", ".    . "]),
    'Є': (2, [" .::.", ".@@@:", "#+ .@", "@:   ", "@:   ", "@@@: ", "@:   ", "@:   ", "@:   ",
              "@: .@", "#+ :@", ".@@@."]),
    'Ж': (2, ["::.:.::", "@.:@:.@", "+#.@.#+", ".@:@:@.", " @+@+@ ", " #@@@# ", " .@@@. ",
              " #@@@# ", " @+@+@ ", ".@:@:@.", "#+.@.+#", "@:.@.:@"]),
    'Л': (2, ["  :::.", "  #@@:", "  @ @:", "  @ @:", "  @ @:", "  @ @:", "  @ @:", " .@ @:",
              " :# @:", " @+ @:", ".@: @:", "@+  @:"]),
    'П': (2, [":::::", "@@@@:"] + ["@: @:"] * 10),
    'У': (2, [":. :.", "@: @:", "#+ #+", "+# @:", ".@.@.", " @+@ ", " #@+ ", " :@: ", " :@. ",
              " @+  ", ":@:  ", "@+   "]),
    'Ф': (2, ["  :  ", " .@. ", ".#@#.", "@:@:@", "@:@:@", "@:@:@", "@:@:@", "@:@:@", "@:@:@",
              ".#@#.", " .@. ", "  @  "]),
    'Ц': (2, [":. :. "] + ["@: @: "] * 10 + ["@@@@@:", "    @:", "    . "]),
    'Ч': (2, [":. :.", "@: @:", "@: @:", "@: @:", "@: @:", "@+.@:", ".@@@:"] + ["   @:"] * 5),
    'Ш': (2, [":. :. :."] + ["@: @: @:"] * 10 + ["@@@@@@@:"]),
    'Щ': (2, [":. :. :. "] + ["@: @: @: "] * 10 + ["@@@@@@@@:", "       @:", "       . "]),
    'Ь': (2, [":.   "] + ["@:   "] * 5 + ["@@@#.", "@: +@", "@:  @", "@:  @", "@: +@", "@@@#."]),
    'Ъ': (2, ["::.   ", "#@:   "] + [" @:   "] * 4 + [" @@@#.", " @: +@", " @:  @", " @:  @", " @: +@", " @@@#."]),
    'Ы': (2, [":.    :."] + ["@:    @:"] * 5 + ["@@@#. @:", "@: +@ @:", "@:  @ @:", "@:  @ @:", "@: +@ @:", "@@@#. @:"]),
    'Ю': (2, [":.  ::. ", "@: .@#@.", "@: ## @:", "@: @: @:", "@: @: @:", "@@@@: @:", "@: @: @:",
              "@: @: @:", "@: @: @:", "@: @: @:", "@: ## @:", "@: .@#@."]),
}

SMALL = {  # x-height rows 6..13
    'б': (2, ["  .::", ".@@@:", ":@.  ", ":@   ", ":@#@:", ":@ @:", ":@ @:", ":@ @:", ":@ @:",
              ":@ @:", ":@ @:", ".@#@."]),
    'в': (6, ["@@#. ", "@: @:", "@: @:", "@@#: ", "@: @:", "@: @:", "@: @:", "@@@+ "]),
    'г': (6, ["@@@:"] + ["@:  "] * 7),
    'ґ': (4, ["   :", "  .@", "@@@@"] + ["@:  "] * 7),
    'д': (6, ["  #@@: ", "  @ @: ", "  @ @: ", "  @ @: ", "  @ @: ", " .@ @: ", " :# @: ",
              "@@@@@@:", "@:   @:", ".    . "]),
    'є': (6, [".@@@.", "@: .@", "@:   ", "@@@: ", "@:   ", "@:   ", "@: .@", ".@@@."]),
    'ж': (6, ["@.:@:.@", "+#.@.#+", ".@:@:@.", " #@@@# ", " #@@@# ", ".@:@:@.", "+#.@.#+", "@:.@.:@"]),
    'з': (6, [".@@#.", "@: .@", "   .@", " .@@:", "   .@", "   .@", "@: .@", ".@@#."]),
    'и': (6, ["@: @:", "@:.@:", "@:#@:", "@.@@:", "@@:@:", "@#.@:", "@+ @:", "@: @:"]),
    'й': (3, [":  :", ".@@.", "     "] + ["@: @:", "@:.@:", "@:#@:", "@.@@:", "@@:@:", "@#.@:", "@+ @:", "@: @:"]),
    'к': (6, ["@: .@", "@: @:", "@:#: ", "@@#  ", "@@@  ", "@:#: ", "@: @:", "@: .@"]),
    'л': (6, ["  #@@:", "  @ @:", "  @ @:", "  @ @:", "  @ @:", " .@ @:", " @+ @:", "@+  @:"]),
    'м': (6, ["@:  :@", "@#  #@", "@@..@@", "@+@@+@", "@:##:@", "@: : @", "@:   @", "@:   @"]),
    'н': (6, ["@: @:", "@: @:", "@: @:", "@@@@:", "@: @:", "@: @:", "@: @:", "@: @:"]),
    'п': (6, ["@@@@:"] + ["@: @:"] * 7),
    'т': (6, ["@@@@@"] + ["  @: "] * 7),
    'ф': (3, ["  :  ", "  @  ", "  @  ", ".#@#.", "@:@:@", "@:@:@", "@:@:@", "@:@:@", "@:@:@",
              "@:@:@", ".#@#.", "  @  ", "  @  "]),
    'ц': (6, ["@: @: "] * 7 + ["@@@@@:", "    @:", "    . "]),
    'ч': (6, ["@: @:", "@: @:", "@: @:", "@+.@:", ".@@@:", "   @:", "   @:", "   @:"]),
    'ш': (6, ["@: @: @:"] * 7 + ["@@@@@@@:"]),
    'щ': (6, ["@: @: @: "] * 7 + ["@@@@@@@@:", "       @:", "       . "]),
    'ь': (6, ["@:   "] * 3 + ["@@@#.", "@: +@", "@:  @", "@: +@", "@@@#."]),
    'ъ': (6, ["#@:   "] + [" @:   "] * 2 + [" @@@#.", " @: +@", " @:  @", " @: +@", " @@@#."]),
    'ы': (6, ["@:    @:"] * 3 + ["@@@#. @:", "@: +@ @:", "@:  @ @:", "@: +@ @:", "@@@#. @:"]),
    'ю': (6, ["@: .@#@.", "@: ## @:", "@: @: @:", "@@@@: @:", "@: @: @:", "@: @: @:", "@: ## @:", "@: .@#@."]),
    'я': (6, [".#@@@", "@: @:", "@: @:", ".#@@:", " .@@:", " @:@:", ".@.@:", "@: @:"]),
}


def pix(top, rows):
    w = max(len(r) for r in rows)
    im = Image.new('L', (w, m.H))
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if SHADE[c]:
                im.putpixel((x, top + y), SHADE[c])
    return m.G(im, w)


def build(f):
    L = lambda ch: f.glyph(ord(ch))
    out = {}
    for cy, la in zip('АВЕКМНОРСТХІ', 'ABEKMHOPCTXI'):
        out[cy] = L(la)
    for cy, la in zip('аеорсхуі', 'aeopcxyi'):
        out[cy] = L(la)
    out['Ї'], out['Ё'], out['ї'], out['ё'] = f.glyph(0xCF), f.glyph(0xCB), f.glyph(0xEF), f.glyph(0xEB)
    out['З'] = L('3')
    for d in (CAPS, SMALL):
        for k, (top, rows) in d.items():
            out[k] = pix(top, rows)
    flip = lambda g: m.G(ImageOps.mirror(g.im), g.adv)
    out['И'] = flip(L('N'))
    out['Я'] = flip(L('R'))
    out['Э'] = flip(out['Є'])
    out['э'] = flip(out['є'])
    br = pix(0, [":  :", ".@@."])  # breve over И
    out['Й'] = m.over((out['И'], 0, 0), (br, 1, 0))
    out['Й'].adv = out['И'].adv
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=os.path.dirname(m.DAT))
    ap.add_argument('--base', default=os.path.join(ROOT, 'fonts', 'zurich16font.art'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'fonts', 'zurich16font.art'))
    ap.add_argument('--preview')
    a = ap.parse_args()
    dat = os.path.join(a.game, 'arcanum1.dat')
    e = next(e for e in tdat.read_entries(dat) if e[0] == 'art/interface/zurich16font.art')
    art = artfont.decode(tdat.read_file(dat, e))
    m.setup(art)
    f = m.Font(art)
    glyphs = build(f)
    base = artfont.decode(open(a.base, 'rb').read())
    for ch in m.CYR:
        if ch in glyphs:
            base.frames[ch.encode('cp1251')[0] - 31] = f.frame(glyphs[ch])
    if a.preview:
        m.preview(base, f, a.preview, S=5)
    else:
        open(a.out, 'wb').write(artfont.encode(base))
        print('wrote', a.out, len(glyphs), 'glyphs')


if __name__ == '__main__':
    main()
