#!/usr/bin/env python3
"""Check uk/mes/gamenewspaper.mes against the newspaper layout of the engine
(src/ui/written_ui.c): headline rect 255x90 (font 490), columns 120 px wide
(fonts 492 = section headers, 483 = body). A word wider than its rect is not
drawn at all and breaks the layout below it; a headline taller than 90 px is cut.

Usage: python3 tools/newscheck.py
"""
import os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import widthcheck as wc, artfont

ROOT = wc.ROOT
FONT = {'490': 'swiss921', '492': 'zurich16', '483': 'garmond9', '482': 'garmond8', '485': 'zurich20'}
HEAD_W, HEAD_H, COL_W = 255, 90, 120
# In the game (Windows, 2026-11-15) a 253 px headline line already wrapped, so
# keep a safety margin: the headline must still fit when wrapped at HEAD_SAFE px.
HEAD_SAFE = 240


def cell_h(name):
    f = artfont.decode(open(os.path.join(ROOT, 'fonts', name + 'font.art'), 'rb').read())
    return max(fr['h'] for fr in f.frames)


def entries(path):
    t = open(path, encoding='utf-8').read()
    return re.findall(r'\{(\d+)\}\{(\d+)[a-z]? ?([^}]*)\}', t)


def main():
    bad = 0
    heights = {}
    for key, fnum, text in entries(os.path.join(ROOT, 'uk', 'mes', 'gamenewspaper.mes')):
        if fnum not in FONT or int(key) < 10:
            continue
        name = FONT[fnum]
        fnt = wc.font(name)
        h = heights.setdefault(name, cell_h(name))
        if fnum == '490':
            lines = wc.layout(fnt, text, HEAD_W)
            if -1 in lines:
                print(f'{key}: заголовок — слово ширше за {HEAD_W} px: {text!r}'); bad += 1
            elif len(wc.layout(fnt, text, HEAD_SAFE)) * h > HEAD_H:
                print(f'{key}: заголовок з запасом ({HEAD_SAFE} px) не влазить у {HEAD_H // h} рядки: {text!r} {lines}'); bad += 1
            elif len(lines) * h > HEAD_H:
                print(f'{key}: заголовок {len(lines)} рядки x {h} px > {HEAD_H}: {text!r}'); bad += 1
        else:
            for word in re.split(r'[ \n\t]+', text):
                if set(word) <= {'_'}:
                    continue  # '_' is a full-width rule in these fonts
                w = wc.one_line_width(fnt, word)
                # the engine may break after a hyphen
                parts = [p for p in re.split(r'(?<=-)', word) if p]
                if any(wc.one_line_width(fnt, p) > COL_W for p in parts):
                    print(f'{key}: {name}: слово {word!r} = {w} px > {COL_W}'); bad += 1
    bad += flow(os.path.join(ROOT, 'uk', 'mes', 'gamenewspaper.mes'))
    bad += prefixes()
    print(f'{bad} проблем')


def prefixes():
    """The engine skips exactly one separator after '<font><l|c>'; anything else
    (e.g. ' \\t' where the original has '\\t') becomes part of the first word,
    which is then too wide and the whole line disappears. Prefixes must match
    the original byte for byte."""
    rx = re.compile(r'\{(\d+)\}\{(\d+[lc][ \t]*)')
    src = open(os.path.join(ROOT, 'source', 'mes', 'gamenewspaper.mes'), encoding='cp1252').read()
    uk = open(os.path.join(ROOT, 'uk', 'mes', 'gamenewspaper.mes'), encoding='utf-8').read()
    want = {m.group(1): m.group(2) for m in rx.finditer(src)}
    bad = 0
    for m in rx.finditer(uk):
        key, got = m.group(1), m.group(2)
        if key in want and got != want[key]:
            print(f'{key}: префікс {got!r}, в оригіналі {want[key]!r}'); bad += 1
    return bad


COLS = [175, 175, 270, 270]  # column heights (written_ui_newspaper_content_rects 1..4)


def flow(path):
    """The main story (entries base+1..base+9) flows through 4 columns; the engine
    simply stops drawing when the columns run out. Report stories that do not fit.
    (The original English has 3 such stories, short by 1-2 lines.)"""
    E = {int(k): (f, t) for k, f, t in entries(path)}
    bad = 0
    for base in sorted(k for k in E if k >= 1000 and k % 10 == 0):
        col, used = 0, 0
        for k in range(base + 1, base + 10):
            if k not in E:
                break
            fnum, text = E[k]
            if fnum not in FONT:
                continue  # clip art
            h = cell_h(FONT[fnum])
            n = len(wc.layout(wc.font(FONT[fnum]), text, COL_W))
            while n > (COLS[col] - used) // h:
                n -= (COLS[col] - used) // h
                col, used = col + 1, 0
                if col >= len(COLS):
                    print(f'{base}: стаття не влазить у колонки — запис {k}, бракує {n} рядків'); bad += 1
                    break
            else:
                used += n * h
                continue
            break
    return bad


if __name__ == '__main__':
    main()
