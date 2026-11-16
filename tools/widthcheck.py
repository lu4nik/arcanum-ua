#!/usr/bin/env python3
"""Static text-fit check: simulates the engine's line breaking (tig/font.c,
sub_535C40) with our .art fonts and reports strings that need more lines than
their UI rect can show. Replaces hunting overflows by playing.

A string that does not fit is not clipped gracefully: the engine either drops
the lines that fall below the rect, or (one-line fields) draws nothing at all.

Rules below map text sources to (font, rect width, max lines), taken from
arcanum-ce UI code and confirmed against ~/arcanum_overflow.log:
  intgame.c message window: title 291x19 (morph15), body 291x36/54/78 (flare12)

Usage:
  python3 tools/widthcheck.py              # all rules, offenders only
  python3 tools/widthcheck.py --text "Поклик повітряного елементаля" morph15 291
"""
import os, sys, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import arcfmt, artfont

_fonts = {}


def font(name):
    if name not in _fonts:
        f = artfont.decode(open(os.path.join(ROOT, 'fonts', name + 'font.art'), 'rb').read())
        _fonts[name] = [(fr['w'], fr['hot_x']) for fr in f.frames]
    return _fonts[name]


def glyph(fnt, byte):
    w, dx = fnt[byte - 31] if 31 <= byte < 31 + len(fnt) else (0, 0)
    return (w, dx + 20) if byte == 9 else (w, dx)


def break_line(fnt, data, max_width):
    """Port of sub_535C40: -> (chars consumed, line width)."""
    total, prev, pos, width_at_prev = 0, -1, 0, 0
    n = len(data)
    while pos < n:
        ch = data[pos]
        if ch == 10:
            return pos, total
        w, dx = glyph(fnt, ch)
        if ch == 32:
            prev, width_at_prev = pos, total
        step = dx if pos + 1 < n else w
        if total + step > max_width:
            break
        total += dx
        if ch == 45:
            prev, width_at_prev = pos, total
        pos += 1
    if pos < n:
        if prev != pos:
            return prev, width_at_prev
        return pos, total
    return pos, total


def layout(fnt, text, max_width):
    """-> list of line widths; a width of -1 marks a word wider than the rect."""
    data = text.encode('cp1251', 'replace')
    lines, guard = [], 0
    while data and guard < 500:
        guard += 1
        n, w = break_line(fnt, data, max_width)
        if n <= 0:
            if data[:1] in (b' ', b'\n'):
                data = data[1:]
                if n == 0 and w == 0:
                    lines.append(0) if False else None
                continue
            lines.append(-1)
            break
        lines.append(w)
        data = data[n:]
        if data[:1] in (b' ', b'\n'):
            data = data[1:]
    return lines


def one_line_width(fnt, text):
    data = text.encode('cp1251', 'replace')
    if not data:
        return 0
    return sum(glyph(fnt, b)[1] for b in data[:-1]) + glyph(fnt, data[-1])[0]


# (label, file, key predicate, font, rect width, max lines)
def _range(a, b):
    return lambda k: k.isdigit() and a <= int(k) <= b


ANY = lambda k: True
RULES = [
    ('назва об\'єкта (інфо-панель 291x19)', 'mes/description.mes', ANY, 'morph15', 291, 1),
    ('назва предмета (інфо-панель 291x19)', 'mes/gamedesc.mes', ANY, 'morph15', 291, 1),
    ('назва закляття (291x19)', 'mes/spell.mes', _range(0, 999), 'morph15', 291, 1),
    # charedit_ui.c: spell titles start at x=59 of a 235px window and are clipped by it
    ('назва закляття у списку на екрані персонажа (176 px)', 'mes/spell.mes', _range(0, 79), 'morph15', 176, 1),
    ('назва навички (291x19)', 'mes/skill.mes', _range(0, 99), 'morph15', 291, 1),
    ('назва техдисципліни/схеми (291x19)', 'mes/tech.mes', _range(0, 99), 'morph15', 291, 1),
    ('ім\'я NPC/контейнера при торгу й обшуку (200x20)', 'mes/description.mes',
     lambda k: k.isdigit() and (3000 <= int(k) <= 3999 or int(k) >= 16000), 'morph15', 200, 1),
    ('унікальне ім\'я при торгу й обшуку (200x20)', 'mes/gamedesc.mes', ANY, 'morph15', 200, 1),
    ('опис закляття (інфо-панель, 2-5 рядків)', 'mes/spell.mes', ANY, 'flare12', 291, 0),
    ('опис навички (інфо-панель)', 'mes/skill.mes', ANY, 'flare12', 291, 0),
    ('опис техдисципліни (інфо-панель)', 'mes/tech.mes', ANY, 'flare12', 291, 0),
    ('опис на екрані персонажа (інфо-панель)', 'mes/charedit.mes', ANY, 'flare12', 291, 0),
    ('заголовок журналу (187x19)', 'mes/logbk_ui.mes', ANY, 'morph15', 187, 1),
    # intgame.c intgame_examine_item: effects line, rect 291x18 = ONE line, the rest is cut
    ('рядок ефектів предмета (291x18, один рядок)', 'mes/item_effect.mes', ANY, 'flare12', 291, -1),
    ('рядок ефектів предмета модуля (291x18)', 'mes/gameitemeffect.mes', ANY, 'flare12', 291, -1),
]


def check_rules():
    total = 0
    for label, rel, pred, fname, width, maxl in RULES:
        p = os.path.join(ROOT, 'uk', rel)
        if not os.path.exists(p):
            print(f'-- {rel}: нема файлу, пропущено')
            continue
        fnt = font(fname)
        bad, vanilla = [], 0
        srcp = os.path.join(ROOT, 'source', rel)
        en = {x['key'].strip(): x['value'].decode('cp1252', 'replace')
              for x in arcfmt.parse_mes(open(srcp, 'rb').read())} if os.path.exists(srcp) else {}
        for e in arcfmt.parse_mes(open(p, 'rb').read()):
            k = e['key'].decode('latin1').strip()
            v = e['value'].decode('utf-8', 'replace')
            if not v.strip() or not pred(k):
                continue
            # one-line rules apply to NAMES only: descriptions share key ranges
            src = en.get(e['key'].strip(), '')
            is_name = not (len(src) > 48 or src.rstrip().endswith('.') or '\n' in src)
            if maxl == -1:
                maxl_e = 1  # every entry, name or not
            elif (maxl == 1) != is_name:
                continue
            else:
                maxl_e = maxl
            if maxl == 0:
                # description: the panel is 2, 3 or 5 lines tall, sized for the original
                need = len(layout(fnt, src.encode('cp1252', 'replace').decode('cp1251', 'replace'), width))
                allowed = next((n for n in (2, 3, 5) if n >= need), need)
                got = len(layout(fnt, v, width))
                if got > allowed:
                    bad.append((got * 100 + allowed, k, f'[{got} рядків, місця на {allowed}] ' + v))
                continue
            lines = layout(fnt, v, width)
            if len(lines) > maxl_e or -1 in lines:
                # the original overflowing too means vanilla behaves the same: not our bug
                el = layout(fnt, src.encode('cp1252', 'replace').decode('cp1251', 'replace'), width) if src else []
                if src and (len(el) > maxl_e or -1 in el):
                    vanilla += 1
                    continue
                bad.append((one_line_width(fnt, v), k, v))
        print(f'== {label}: {rel} — не влазить {len(bad)} (ще {vanilla} не влазять і в оригіналі)')
        for w, k, v in sorted(bad, reverse=True):
            print(f'   {w:4d}px {{{k}}} {v[:70]}')
        total += len(bad)
    print(f'\nразом: {total}')


if __name__ == '__main__':
    if '--text' in sys.argv:
        i = sys.argv.index('--text')
        text, fname, width = sys.argv[i + 1], sys.argv[i + 2], int(sys.argv[i + 3])
        fnt = font(fname)
        print(one_line_width(fnt, text), 'px;', 'lines:', layout(fnt, text, width))
    else:
        check_rules()
