#!/usr/bin/env python3
"""Draw a string the way the game does: our .art font, the engine's line
breaking (widthcheck.break_line = tig/font.c sub_535C40), inside a rect of the
real UI size. Lines that fall outside the rect are drawn below it in red, so
the overflow is visible. Output: PNG bytes (no dependencies).

  python3 tools/textpreview.py "Сувій: вихід" morph15 291 1 out.png
"""
import os, sys, struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import artfont, widthcheck, npcart

ROOT = widthcheck.ROOT
_fonts = {}
BG = (29, 26, 22)
INK = (236, 226, 200)
BAD = (230, 90, 70)
FRAME = (120, 108, 88)


def _font(name):
    if name not in _fonts:
        a = artfont.decode(open(os.path.join(ROOT, 'fonts', name + 'font.art'), 'rb').read())
        pal = next(p for p in a.palettes if p)
        lum = [((c >> 16 & 255) * 3 + (c >> 8 & 255) * 6 + (c & 255)) // 10 for c in pal]
        h = max(f['h'] for f in a.frames)
        _fonts[name] = (a.frames, lum, h)
    return _fonts[name]


def split(fname, text, width):
    """-> list of (bytes, overflow_word) lines, as the engine breaks them."""
    fnt = widthcheck.font(fname)
    data = text.encode('cp1251', 'replace')
    out, guard = [], 0
    while data and guard < 200:
        guard += 1
        n, w = widthcheck.break_line(fnt, data, width)
        if n <= 0:
            if data[:1] in (b' ', b'\n'):
                data = data[1:]
                continue
            word = data.split(b' ')[0]
            out.append((word, True))  # wider than the rect: the engine skips it
            data = data[len(word):]
            continue
        out.append((data[:n], False))
        data = data[n:]
        if data[:1] in (b' ', b'\n'):
            data = data[1:]
    return out


def render(text, fname='flare12', width=291, lines=0, scale=2):
    """lines = rect height in lines (0: as many as the text needs)."""
    frames, lum, lh = _font(fname)
    rows = split(fname, text, width)
    nl = max(1, len(rows))
    allowed = lines or nl
    pad = 4
    W = width + 2 * pad
    H = max(allowed, nl) * lh + 2 * pad + 2
    img = bytearray(bytes(BG + (255,)) * (W * H))

    def put(x, y, col, a=255):
        if 0 <= x < W and 0 <= y < H:
            i = (y * W + x) * 4
            for c in range(3):
                img[i + c] = (img[i + c] * (255 - a) + col[c] * a) // 255

    # the UI rect
    rh = allowed * lh
    for x in range(pad - 1, pad + width + 1):
        put(x, pad - 1, FRAME), put(x, pad + rh, FRAME)
    for y in range(pad - 1, pad + rh + 1):
        put(pad - 1, y, FRAME), put(pad + width, y, FRAME)
    for li, (data, wide) in enumerate(rows):
        bad = wide or li >= allowed
        col = BAD if bad else INK
        x, y0 = pad, pad + li * lh
        for b in data:
            i = b - 31
            if not 0 <= i < len(frames):
                continue
            f = frames[i]
            px = f['pixels']
            for yy in range(f['h']):
                for xx in range(f['w']):
                    c = px[yy * f['w'] + xx]
                    if c:
                        put(x + xx, y0 + yy, col, min(255, lum[c] + 40))
            x += f['hot_x'] + (20 if b == 9 else 0)
    if scale > 1:
        big = bytearray()
        for y in range(H):
            row = b''.join(bytes(img[(y * W + x) * 4:(y * W + x) * 4 + 4]) * scale for x in range(W))
            big += row * scale
        img, W, H = big, W * scale, H * scale
    return npcart.png(W, H, bytes(img)), {
        'lines': len(rows), 'allowed': allowed,
        'fits': len(rows) <= allowed and not any(w for _, w in rows)}


if __name__ == '__main__':
    t, f, w, n, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    data, info = render(t, f, w, n)
    open(out, 'wb').write(data)
    print(info)
