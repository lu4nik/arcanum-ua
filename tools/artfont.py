#!/usr/bin/env python3
"""Codec for Arcanum font .art files (tig art, single rotation, 8bpp).

Format (reversed from arcanum-ce tig/src/art.c, documented in docs/fonts.md):
  header 132 B: flags, fps, bpp, palette_markers[4], action_frame, num_frames,
                frames_ptrs[8] (junk), data_size[8], pixels_ptrs[8] (junk)
  then: for each non-zero palette marker: 256 x uint32 BGRA palette
  then: frame table: num_frames x 28 B (w, h, data_size, hot_x, hot_y, ox, oy)
        (single rotation when flags & 1)
  then: pixel data per frame: raw if data_size == w*h else RLE
        RLE: ctrl byte c: len = c & 0x7F; c & 0x80 -> len literal bytes follow,
             else one color byte follows, repeated len times.

Fonts: glyph for byte b is frame (b - 31). hot_x = advance (dx), hot_y = dy.
"""
import struct

class ArtFont:
    def __init__(self):
        self.flags = 0
        self.fps = 0
        self.bpp = 8
        self.action_frame = 0
        self.palettes = [None] * 4   # None or list of 256 uint32
        self.frames = []             # dicts: w h hot_x hot_y ox oy pixels(bytearray w*h)

def decode(data: bytes) -> ArtFont:
    a = ArtFont()
    a.flags, a.fps, a.bpp = struct.unpack_from('<3i', data, 0)
    markers = struct.unpack_from('<4i', data, 12)
    a.action_frame, num_frames = struct.unpack_from('<2i', data, 28)
    if a.flags & 1 == 0:
        raise ValueError('multi-rotation art not supported (not a font)')
    off = 132
    for i, m in enumerate(markers):
        if m:
            a.palettes[i] = list(struct.unpack_from('<256I', data, off))
            off += 1024
    metas = []
    for _ in range(num_frames):
        metas.append(struct.unpack_from('<7i', data, off))
        off += 28
    for w, h, data_size, hot_x, hot_y, ox, oy in metas:
        if data_size == w * h:
            pixels = bytearray(data[off:off + data_size])
            off += data_size
        else:
            pixels = bytearray()
            cnt = 0
            while cnt < data_size:
                c = data[off]; off += 1
                ln = c & 0x7F
                if c & 0x80:
                    pixels += data[off:off + ln]
                    off += ln
                    cnt += 1 + ln
                else:
                    pixels += bytes([data[off]]) * ln
                    off += 1
                    cnt += 2
            if len(pixels) != w * h:
                raise ValueError(f'RLE decoded {len(pixels)} != {w}x{h}')
        a.frames.append(dict(w=w, h=h, hot_x=hot_x, hot_y=hot_y, ox=ox, oy=oy,
                             pixels=pixels))
    return a

def _rle(pixels: bytes) -> bytes:
    """Encode like the originals do (runs vs literals)."""
    out = bytearray()
    i, n = 0, len(pixels)
    while i < n:
        # find run length
        j = i
        while j < n and j - i < 0x7F and pixels[j] == pixels[i]:
            j += 1
        run = j - i
        if run >= 3:
            out.append(run)
            out.append(pixels[i])
            i = j
        else:
            # literal: until next run of >=3 or 0x7F cap
            j = i
            while j < n and j - i < 0x7F:
                if j + 2 < n and pixels[j] == pixels[j+1] == pixels[j+2]:
                    break
                j += 1
            out.append(0x80 | (j - i))
            out += pixels[i:j]
            i = j
    return bytes(out)

def encode(a: ArtFont) -> bytes:
    out = bytearray()
    payloads = []
    for f in a.frames:
        raw = bytes(f['pixels'])
        rle = _rle(raw)
        payloads.append(rle if len(rle) < len(raw) else raw)
    out += struct.pack('<3i', a.flags, a.fps, a.bpp)
    out += struct.pack('<4i', *[1 if p else 0 for p in a.palettes])
    out += struct.pack('<2i', a.action_frame, len(a.frames))
    out += b'\0' * 32  # frames ptrs (ignored)
    total = sum(len(p) for p in payloads)
    out += struct.pack('<8i', total, 0, 0, 0, 0, 0, 0, 0)
    out += b'\0' * 32  # pixel ptrs (ignored)
    for p in a.palettes:
        if p:
            out += struct.pack('<256I', *p)
    for f, payload in zip(a.frames, payloads):
        out += struct.pack('<7i', f['w'], f['h'], len(payload),
                           f['hot_x'], f['hot_y'], f['ox'], f['oy'])
    for payload in payloads:
        out += payload
    return bytes(out)

def show(frame, ramp=' .:-=+*#%@'):
    """ASCII visualization of one glyph frame."""
    w, h, px = frame['w'], frame['h'], frame['pixels']
    vals = sorted(set(px))
    lines = []
    for y in range(h):
        row = px[y*w:(y+1)*w]
        lines.append(''.join(ramp[min(vals.index(v) * (len(ramp)-1) // max(1, len(vals)-1), len(ramp)-1)] for v in row))
    return '\n'.join(lines)
