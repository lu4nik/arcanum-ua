#!/usr/bin/env python3
"""Extract the EFFECTIVE English text tree (dlg/mes) from the game archives.

Mirrors engine repository priority (tig_file_repository_add is head-insert,
so later additions win; see arcanum-ce gamelib.c gamelib_load_data /
gamelib_load_module_data):

  lowest  arcanum1.dat .. Arcanum5.dat   (strcasecmp ascending)
          data/                          (loose)
          modules/Arcanum.dat
          modules/Arcanum.PATCH0..9      (ascending)
  highest modules/Arcanum/               (loose)

Writes verbatim bytes to source/<path> and source/provenance.tsv.
Usage: python3 tools/extract.py [game_dir] [out_dir]
"""
import os, sys, fnmatch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdat

EXTS = ('.dlg', '.mes')

def archives(game):
    arcs = []
    for name in ['arcanum1.dat', 'arcanum2.dat', 'arcanum3.dat',
                 'Arcanum4.dat', 'Arcanum5.dat']:
        p = os.path.join(game, name)
        if os.path.exists(p):
            arcs.append(p)
    p = os.path.join(game, 'modules', 'Arcanum.dat')
    if os.path.exists(p):
        arcs.append(p)
    for i in range(10):
        p = os.path.join(game, 'modules', f'Arcanum.PATCH{i}')
        if os.path.exists(p):
            arcs.append(p)
    return arcs

def loose_dirs(game):
    return [os.path.join(game, 'data'), os.path.join(game, 'modules', 'Arcanum')]

def build_effective(game):
    eff = {}  # relpath -> ('dat', archive, entry) | ('fs', abspath, size)
    for arc in archives(game):
        for e in tdat.read_entries(arc):
            if e[0].endswith(EXTS) and e[2] > 0:
                eff[e[0]] = ('dat', arc, e)
    for d in loose_dirs(game):
        for root, _, files in os.walk(d):
            for f in files:
                if f.lower().endswith(EXTS):
                    full = os.path.join(root, f)
                    rel = os.path.relpath(full, d).replace(os.sep, '/').lower()
                    eff[rel] = ('fs', full, os.path.getsize(full))
    return eff

def main():
    game = sys.argv[1] if len(sys.argv) > 1 else '/Applications/Arcanum'
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'source')
    eff = build_effective(game)
    rows = []
    for rel in sorted(eff):
        kind = eff[rel]
        if kind[0] == 'dat':
            data = tdat.read_file(kind[1], kind[2])
            origin = os.path.relpath(kind[1], game)
        else:
            with open(kind[1], 'rb') as f:
                data = f.read()
            origin = os.path.relpath(kind[1], game)
        dst = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as f:
            f.write(data)
        rows.append((rel, origin, len(data)))
    with open(os.path.join(out, 'provenance.tsv'), 'w') as f:
        f.write('path\torigin\tbytes\n')
        for rel, origin, n in rows:
            f.write(f'{rel}\t{origin}\t{n}\n')
    print(f'{len(rows)} files -> {out}')

if __name__ == '__main__':
    main()
