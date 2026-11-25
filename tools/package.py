#!/usr/bin/env python3
"""Build a distributable archive of the Ukrainian localization.

Mirrors the layout tools/inject.py deploys into a working game, so the
archive is unpacked straight into the game folder:

  data/mes/, data/dlg/                 } translations, cp1251
  modules/Arcanum/mes/, .../dlg/       }
  data/art/interface/*font.art         } Cyrillic fonts
  modules/Arcanum/art/interface/       }
  art/morph15font.art                  system font (game root)
  data/rules/, modules/Arcanum/rules/  npc/monster/unique.txt with localized
                                       stat/spell names (UAP variant)
  no-UAP/...                           the same for a game without UAP
  HighRes/gamepad.bmp                  Ukrainian gamepad button chart for the
                                       lu4nik/arcanum-ce fork (rendered by its
                                       scripts/gamepad_chart.py from CE)

The rules files are the one exception to "only our own files": the original
exe rebuilds NPC prototypes from them and matches stat/spell names against
our translated stat.mes/spell.mes, so they have to carry the same names
(tools/rules_l10n.py; owner's decision 2026-11-22). They are generated from
the game copy at GAME (default /Applications/Arcanum).

Only our own files go in: translated text (converted UTF-8 -> cp1251), the
generated fonts and the localized rules files (see below).

Usage:
  python3 tools/package.py [version]    # -> dist/arcanum-ua-<version>.zip
"""
import datetime, io, os, subprocess, sys, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UK = os.path.join(ROOT, 'uk')
FONTS = os.path.join(ROOT, 'fonts')
DOCS = os.path.join(ROOT, 'dist-docs')

# The 25 interface fonts the game loads; dev-only A/B and preview renders are excluded.
INTERFACE_FONTS = [
    'arial10', 'arialb12', 'casablanca16', 'clarendonblk18', 'courier10', 'casablancaantique30', 'cloister18', 'euph30',
    'flare12', 'flare14', 'garmond6', 'garmond8', 'garmond9', 'georgia30', 'latinxcn30',
    'morph15', 'morph30', 'newtimes16', 'nick16', 'pepper20', 'pork12',
    'roller', 'swiss921', 'zurich16', 'zurich20',
]
TEXT_DESTS = ['data', 'modules/Arcanum']
GAME = os.environ.get('ARCANUM_GAME', '/Applications/Arcanum')
CE = os.environ.get('ARCANUM_CE', os.path.expanduser('~/Games/arcanum-ce'))
NO_UAP_DIR = 'no-UAP'  # ASCII: Windows unzip tools mangle non-ASCII folder names


def translations():
    for dirpath, _, files in os.walk(UK):
        for name in sorted(files):
            if name.endswith(('.mes', '.dlg')):
                full = os.path.join(dirpath, name)
                yield os.path.relpath(full, UK).replace(os.sep, '/'), full


def build(version):
    top = f'arcanum-ua-{version}'
    out_dir = os.path.join(ROOT, 'dist')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, top + '.zip')
    n_text = n_font = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for rel, full in translations():
            data = open(full, encoding='utf-8').read().encode('cp1251')
            for dest in TEXT_DESTS:
                z.writestr(f'{top}/{dest}/{rel}', data)
            n_text += 1
        for name in INTERFACE_FONTS:
            src = os.path.join(FONTS, f'{name}font.art')
            for dest in TEXT_DESTS:
                z.write(src, f'{top}/{dest}/art/interface/{name}font.art')
            n_font += 1
        z.write(os.path.join(FONTS, 'morph15font_system.art'), f'{top}/art/morph15font.art')
        n_font += 1
        n_rules = 0
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run([sys.executable, os.path.join(ROOT, 'tools', 'rules_l10n.py'), tmp, GAME], check=True)
            for variant, prefix in (('uap', top), ('vanilla', f'{top}/{NO_UAP_DIR}')):
                rules = os.path.join(tmp, variant, 'rules')
                for name in sorted(os.listdir(rules)):
                    for dest in TEXT_DESTS:
                        z.write(os.path.join(rules, name), f'{prefix}/{dest}/rules/{name}')
                    n_rules += 1
        with tempfile.TemporaryDirectory() as tmp:
            chart = os.path.join(tmp, 'gamepad.bmp')
            subprocess.run([sys.executable, os.path.join(CE, 'scripts', 'gamepad_chart.py'), 'uk', chart], check=True)
            z.write(chart, f'{top}/HighRes/gamepad.bmp')
        for doc in sorted(os.listdir(DOCS)):
            z.write(os.path.join(DOCS, doc), f'{top}/{doc}')
    print(f'{out}: {n_text} text files x{len(TEXT_DESTS)}, {n_font} fonts, {n_rules} rules files, '
          f'{os.path.getsize(out) // 1024} KiB')
    return out


if __name__ == '__main__':
    build(sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().strftime('%Y%m%d'))
