#!/usr/bin/env python3
"""Generate Cyrillic glyphs into an Arcanum .art font from a TTF.

Takes the original font, measures its Latin metrics (cap height, baseline,
advance padding, grayscale ramp), renders the cp1251 Cyrillic range from a
TTF at matching size, and writes a new .art with those frames replaced.

Usage:
  python3 tools/genfont.py art/interface/flare12font.art \
      "/System/Library/Fonts/Supplemental/Georgia Bold.ttf" fonts/flare12font.art
  --track N  (optional 4th arg) adds N px to every Cyrillic advance (e.g. -1 to tighten)
  --cap N    render Cyrillic with cap height N px instead of the original Latin one
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdat, artfont
from PIL import Image, ImageFont

ARC = '/Applications/Arcanum/arcanum1.dat'

# cp1251 slots to generate: А-Я а-я + ЁёҐґЄєІіЇї
CP1251_CHARS = ([chr(c) for c in range(0x410, 0x450)] +  # А-я
                ['Ё', 'ё', 'Ґ', 'ґ', 'Є', 'є', 'І', 'і', 'Ї', 'ї'])

def cp1251_byte(ch):
    return ch.encode('cp1251')[0]

def ink_rows(frame):
    w, h, px = frame['w'], frame['h'], frame['pixels']
    rows = [y for y in range(h) if any(px[y*w:(y+1)*w])]
    return (rows[0], rows[-1]) if rows else (None, None)

def measure(orig):
    """Latin metrics of the original font."""
    A = orig.frames[ord('A') - 31]
    top, bottom = ink_rows(A)
    cap_h = bottom - top + 1
    baseline = bottom  # row of the last cap pixel
    x = orig.frames[ord('x') - 31]
    xtop, xbot = ink_rows(x)
    # advance padding: hot_x - width, averaged over letters
    pads = [orig.frames[ord(c) - 31]['hot_x'] - orig.frames[ord(c) - 31]['w']
            for c in 'ABCHKMOPWabcehkmopw']
    pad = round(sum(pads) / len(pads))
    hot_y = orig.frames[ord('A') - 31]['hot_y']
    # grayscale ramp: index -> luminance from palette 0
    pal = next(p for p in orig.palettes if p)
    used = set()
    for c in 'ABCHKMOPWabcehkmopwgjpqy':
        used.update(orig.frames[ord(c) - 31]['pixels'])
    used.discard(0)
    ramp = sorted(used, key=lambda i: (pal[i] & 0xFF) + ((pal[i] >> 8) & 0xFF) + ((pal[i] >> 16) & 0xFF))
    desc = max((ink_rows(orig.frames[ord(c) - 31])[1] or 0) for c in 'gjpqy') - baseline
    return dict(cap_h=cap_h, baseline=baseline, x_h=(xbot - xtop + 1),
                pad=pad, hot_y=hot_y, ramp=ramp, h=A['h'], desc=max(desc, 0))

def load_font(ttf_path, size):
    """ttf_path may be 'Collection.ttc#N' to pick face N from a font collection."""
    path, _, idx = ttf_path.partition('#')
    return ImageFont.truetype(path, size, index=int(idx) if idx else 0)

def pick_size(ttf_path, cap_h):
    """TTF pixel size whose capital А matches cap_h."""
    best = None
    for size in range(6, 60):
        font = load_font(ttf_path, size)
        bbox = font.getbbox('А')
        hh = bbox[3] - bbox[1]
        d = abs(hh - cap_h)
        if best is None or d < best[0]:
            best = (d, size, font)
        if hh > cap_h + 6:
            break
    return best[2]

def render_glyph(font, ch, m, stroke=0, gamma=1.0):
    """Render ch -> art frame dict matching original metrics.
    stroke: fake-bold width in px (0 = off). gamma: <1 brightens antialiasing."""
    from PIL import ImageDraw
    if stroke:
        probe = Image.new('L', (4, 4), 0)
        bbox0 = ImageDraw.Draw(probe).textbbox((0, 0), ch, font=font, stroke_width=stroke)
        img = Image.new('L', (max(bbox0[2], 1) + 16, max(bbox0[3], 1) + 24), 0)
        ImageDraw.Draw(img).text((8, 8), ch, font=font, fill=255,
                                 stroke_width=stroke, stroke_fill=255)
        mask = None
    else:
        mask = font.getmask(ch, mode='L')
        mw, mh = mask.size
        img = Image.new('L', (mw + 8, mh + 16), 0)
        img.paste(Image.frombytes('L', mask.size, bytes(mask)), (4, 8))
    bbox = img.getbbox()
    # vertical anchor: distance from ascent top to ink top (stroke widens ink upward)
    try:
        glyph_top_offset = font.getbbox(ch, stroke_width=stroke)[1]
    except TypeError:
        glyph_top_offset = font.getbbox(ch)[1]
    if bbox is None:
        # whitespace-like glyph
        return dict(w=3, h=m['h'], hot_x=3 + m['pad'], hot_y=m['hot_y'], ox=0, oy=0,
                    pixels=bytearray(3 * m['h']))
    img = img.crop(bbox)
    w, h = img.size
    H = m['h']
    frame_px = bytearray(w * H)
    # ink top row in frame: baseline - (ink height above baseline)
    # rows of ink above baseline = asc - glyph_top_offset
    above = (font.getmetrics()[0] - glyph_top_offset)
    top_row = m['baseline'] - (above - 1)
    if top_row < 0:
        # Diacritics (Ї Й Ё) above a short cell would be clipped away entirely:
        # first drop blank rows between accent and body, then squash vertically.
        overflow = -top_row
        rows = [img.crop((0, y, w, y + 1)).getbbox() is not None for y in range(h)]
        blank = [y for y in range(1, h - 1) if not rows[y]]
        drop = set(blank[:overflow])
        if drop:
            kept = [img.crop((0, y, w, y + 1)) for y in range(h) if y not in drop]
            img2 = Image.new('L', (w, len(kept)), 0)
            for i, r in enumerate(kept):
                img2.paste(r, (0, i))
            img, h = img2, len(kept)
            top_row += len(drop)
        if top_row < 0:
            img = img.resize((w, h + top_row), Image.LANCZOS)
            h += top_row
            top_row = 0
    data = img.tobytes()
    ramp = m['ramp']
    for y in range(h):
        fy = top_row + y
        if 0 <= fy < H:
            for x in range(w):
                v = data[y * w + x]
                if v >= 32:
                    vn = (v / 255.0) ** gamma
                    idx = ramp[min(int(vn * len(ramp)), len(ramp) - 1)]
                    frame_px[fy * w + x] = idx
    return dict(w=w, h=H, hot_x=w + m['pad'], hot_y=m['hot_y'], ox=0, oy=0,
                pixels=frame_px)

def main():
    src_name, ttf_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    track = int(sys.argv[sys.argv.index('--track') + 1]) if '--track' in sys.argv else 0
    e = next(x for x in tdat.read_entries(ARC) if x[0].endswith(src_name.split('/')[-1].lower()))
    orig = artfont.decode(tdat.read_file(ARC, e))
    m = measure(orig)
    print(f'{src_name}: cell_h={m["h"]} cap_h={m["cap_h"]} baseline={m["baseline"]} '
          f'pad={m["pad"]} ramp={len(m["ramp"])} steps')
    cap = int(sys.argv[sys.argv.index('--cap') + 1]) if '--cap' in sys.argv else m['cap_h']
    font = pick_size(ttf_path, cap)
    for ch in CP1251_CHARS:
        frame_idx = cp1251_byte(ch) - 31
        fr = render_glyph(font, ch, m)
        fr['hot_x'] = max(1, fr['hot_x'] + track)
        orig.frames[frame_idx] = fr
    out = artfont.encode(orig)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(out)
    print(f'-> {out_path} ({len(out)} bytes), generated {len(CP1251_CHARS)} glyphs '
          f'at TTF size {font.size}')

if __name__ == '__main__':
    main()
