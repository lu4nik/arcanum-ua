#!/usr/bin/env python3
"""Localize the stat/spell names in rules/npc.txt, monster.txt, unique.txt.

Why: when data/proto is missing (fresh install, RemoveProtos, our install
step 4) the engine rebuilds every critter prototype from these files. Its
parser (sub_49BB70, 0x49BB70 in Arcanum.exe; src/game/proto.c in arcanum-ce)
matches "Basic Stat: <name> <n>" and "Spell: <name>" against stat_name() /
spell_name(), i.e. against the strings in mes/stat.mes and mes/spell.mes.
With our translated mes nothing matched, so the regenerated NPCs lost gender
(all male), race, stats and spells. Writing the same Ukrainian names into the
rules files makes the original exe parse them again.

The files themselves come from the player's own game archives, exactly as the
game resolves them:
  npc.txt, monster.txt: Arcanum5.dat (UAP) / Arcanum4.dat (vanilla GOG)
  unique.txt:           modules/Arcanum.PATCH0 (a module patch outranks
                        every root .dat, UAP's Arcanum5.dat included)

Every rewritten line is checked by re-running the engine's matching rule
(first name, in engine order, that is a case-insensitive prefix) against the
Ukrainian names: it must pick the same stat/spell as the English line did.

Usage:
  python3 tools/rules_l10n.py OUT_DIR [game_dir]
    -> OUT_DIR/uap/rules/*.txt and OUT_DIR/vanilla/rules/*.txt (cp1251, CRLF kept)
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import tdat

# Stats the parser accepts: STAT_STRENGTH..STAT_CHARISMA, STAT_MAGICK_POINTS..STAT_RACE.
STAT_IDS = list(range(0, 8)) + list(range(22, 28))
SPELL_COUNT = 80

SOURCES = {
    'uap':     {'npc.txt': 'Arcanum5.dat', 'monster.txt': 'Arcanum5.dat', 'unique.txt': 'modules/Arcanum.PATCH0'},
    'vanilla': {'npc.txt': 'Arcanum4.dat', 'monster.txt': 'Arcanum4.dat', 'unique.txt': 'modules/Arcanum.PATCH0'},
}

LINE = re.compile(rb'^(\s*(basic stat|spell)\s*:[: ]*)(.*?)(\r?\n?)$', re.I | re.S)


def mes(data):
    return {int(m.group(1)): m.group(2) for m in re.finditer(rb'\{(\d+)\}\{([^}]*)\}', data)}


def dat_file(path, name):
    for e in tdat.read_entries(path):
        if e[0] == name:
            return tdat.read_file(path, e)
    raise KeyError(f'{name} not in {path}')


def match(text, names, ids):
    """Engine rule: first id whose name is a case-insensitive prefix of text."""
    low = text.lower()
    for i in ids:
        n = names[i]
        if n and low.startswith(n.lower()):
            return i, len(n)
    return None, 0


def localize(data, en_stat, uk_stat, en_spell, uk_spell, label):
    out, n_stat, n_spell = [], 0, 0
    for line in data.splitlines(keepends=True):
        m = LINE.match(line)
        if not m:
            out.append(line)
            continue
        head, kind, rest, eol = m.group(1), m.group(2).lower(), m.group(3), m.group(4)
        if kind == b'basic stat':
            en, uk, ids = en_stat, uk_stat, STAT_IDS
        else:
            en, uk, ids = en_spell, uk_spell, range(SPELL_COUNT)
        idx, ln = match(rest, en, ids)
        if idx is None:
            # the engine ignores it in English too; leave as is
            print(f'  {label}: unmatched {line.strip()!r}', file=sys.stderr)
            out.append(line)
            continue
        new_rest = uk[idx] + rest[ln:]
        idx2, _ = match(new_rest, uk, ids)
        if idx2 != idx:
            raise SystemExit(f'{label}: {line.strip()!r} -> {new_rest!r} resolves to {idx2}, not {idx}')
        out.append(head + new_rest + eol)
        if kind == b'basic stat':
            n_stat += 1
        else:
            n_spell += 1
    return b''.join(out), n_stat, n_spell


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out_dir = sys.argv[1]
    game = sys.argv[2] if len(sys.argv) > 2 else '/Applications/Arcanum'

    en_stat = mes(dat_file(os.path.join(game, 'arcanum3.dat'), 'mes/stat.mes'))
    en_spell = mes(dat_file(os.path.join(game, 'Arcanum4.dat'), 'mes/spell.mes'))
    uk_stat = mes(open(os.path.join(ROOT, 'uk/mes/stat.mes'), encoding='utf-8').read().encode('cp1251'))
    uk_spell = mes(open(os.path.join(ROOT, 'uk/mes/spell.mes'), encoding='utf-8').read().encode('cp1251'))

    # Translated names must not shadow each other under the prefix rule.
    for names, ids, what in ((uk_stat, STAT_IDS, 'stat'), (uk_spell, range(SPELL_COUNT), 'spell')):
        for i in ids:
            j, _ = match(names[i], names, ids)
            if j != i:
                raise SystemExit(f'{what} {i} {names[i]!r} is shadowed by {j} {names[j]!r}')

    for variant, files in SOURCES.items():
        dest = os.path.join(out_dir, variant, 'rules')
        os.makedirs(dest, exist_ok=True)
        for name, src in files.items():
            data = dat_file(os.path.join(game, src), 'rules/' + name)
            new, ns, nsp = localize(data, en_stat, uk_stat, en_spell, uk_spell, f'{variant}/{name}')
            open(os.path.join(dest, name), 'wb').write(new)
            print(f'{variant}/rules/{name}: {ns} stat lines, {nsp} spell lines')


if __name__ == '__main__':
    main()
