#!/usr/bin/env python3
"""Deploy uk/ translations into the game as loose files (highest priority
repository: modules/Arcanum/). Converts UTF-8 (repo) -> cp1251 (game).

Usage:
  python3 tools/inject.py            # deploy everything under uk/
  python3 tools/inject.py --clean    # remove previously deployed files
  python3 tools/inject.py uk/mes/mainmenu.mes ...   # deploy selected
"""
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GAME = '/Applications/Arcanum'
# Deploy to BOTH loose repositories: modules/Arcanum/ is highest priority,
# but some .mes load before the module repository is added — data/ covers those.
DESTS = [os.path.join(GAME, 'modules', 'Arcanum'), os.path.join(GAME, 'data')]
DEST = DESTS[0]
MANIFEST = os.path.join(ROOT, '.deployed')  # list of deployed rel paths

def deployed():
    if os.path.exists(MANIFEST):
        return [l.strip() for l in open(MANIFEST) if l.strip()]
    return []

def clean():
    for rel in deployed():
        for dest in DESTS:
            p = os.path.join(dest, rel)
            if os.path.exists(p):
                os.remove(p)
                print('removed', p)
    if os.path.exists(MANIFEST):
        os.remove(MANIFEST)

def deploy(targets):
    done = set(deployed())
    for rel in targets:
        src = os.path.join(ROOT, 'uk', rel)
        text = open(src, encoding='utf-8').read()
        data = text.encode('cp1251')  # hard fail on unrepresentable chars
        for dest in DESTS:
            dst = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, 'wb') as f:
                f.write(data)
            print('deployed', dst)
        done.add(rel)
    with open(MANIFEST, 'w') as f:
        f.write('\n'.join(sorted(done)) + '\n')

def main():
    if '--clean' in sys.argv:
        clean()
        return
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if args:
        targets = [os.path.relpath(os.path.abspath(a), os.path.join(ROOT, 'uk')).replace(os.sep, '/')
                   for a in args]
    else:
        targets = []
        base = os.path.join(ROOT, 'uk')
        for root, _, files in os.walk(base):
            for f in files:
                if f.endswith(('.mes', '.dlg')):
                    targets.append(os.path.relpath(os.path.join(root, f), base).replace(os.sep, '/'))
    deploy(sorted(targets))

if __name__ == '__main__':
    main()
