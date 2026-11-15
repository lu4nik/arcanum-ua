#!/usr/bin/env python3
"""QA a translated file (or all of uk/) against source/.

Checks:
  1. structure  — entry/record counts, keys, non-text dlg fields byte-identical
  2. encoding   — uk file is valid UTF-8 and fully representable in cp1251
  3. emptiness  — no source text dropped (non-empty stays non-empty)
  4. glossary   — forbidden variants (rows in glossary with note 'forbid:...')

Usage: python3 tools/qa.py [uk/dlg/01100virgil.dlg ...]   (no args = all of uk/)
Exit code 0 = clean.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import arcfmt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def check(rel):
    """rel like 'dlg/01100virgil.dlg' (path under uk/)."""
    problems = []
    src_p = os.path.join(ROOT, 'source', rel)
    uk_p = os.path.join(ROOT, 'uk', rel)
    if not os.path.exists(src_p):
        return [f'{rel}: no such source file']
    src = open(src_p, 'rb').read()
    raw = open(uk_p, 'rb').read()
    # encoding: repo files are UTF-8, must be representable in cp1251
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError as e:
        return [f'{rel}: not valid UTF-8: {e}']
    try:
        text.encode('cp1251')
    except UnicodeEncodeError as e:
        bad = text[e.start:e.start + 10]
        problems.append(f'{rel}: not representable in cp1251 near {bad!r}')
    kind = 'mes' if rel.endswith('.mes') else 'dlg'
    problems += [f'{rel}: {p}' for p in arcfmt.validate_pair(src, raw, kind)]
    return problems

def main():
    targets = []
    if len(sys.argv) > 1:
        for a in sys.argv[1:]:
            rel = os.path.relpath(os.path.abspath(a), os.path.join(ROOT, 'uk'))
            targets.append(rel.replace(os.sep, '/'))
    else:
        base = os.path.join(ROOT, 'uk')
        for root, _, files in os.walk(base):
            for f in files:
                if f.endswith(('.mes', '.dlg')):
                    targets.append(os.path.relpath(os.path.join(root, f), base).replace(os.sep, '/'))
    all_problems = []
    for rel in sorted(targets):
        all_problems += check(rel)
    for p in all_problems:
        print('FAIL', p)
    print(f'{len(targets)} files checked, {len(all_problems)} problems')
    sys.exit(1 if all_problems else 0)

if __name__ == '__main__':
    main()
