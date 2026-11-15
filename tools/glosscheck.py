#!/usr/bin/env python3
"""Glossary consistency check: where the EN record contains a glossary term,
the UK record must contain the glossary's Ukrainian form (matched by word
stems, so declined forms pass).

Proper names only by default (EN term starts with an uppercase letter):
common nouns are translated contextually and would drown the report.

Usage:
  python3 tools/glosscheck.py            # summary per term
  python3 tools/glosscheck.py -v         # + every offending record
  python3 tools/glosscheck.py -v Ristezze   # only terms matching the filter
"""
import os, re, sys, glob, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import arcfmt

STRIP = '«»"\'().,;:!?'


def stems(uk_term):
    """Stems of the significant words of a UK glossary form."""
    out = []
    # glossary may list alternatives: "Живий / Жива" -> any alternative passes
    for alt in re.split(r'\s*/\s*', uk_term):
        words = [w.strip(STRIP) for w in alt.split()]
        words = [w for w in words if len(w) >= 4 and w[0].isalpha()]
        if words:
            out.append([w[:max(3, len(w) - 3)].lower() for w in words])
    return out


def load_glossary():
    terms = []
    for line in open(os.path.join(ROOT, 'glossary', 'glossary.tsv'), encoding='utf-8'):
        cols = line.rstrip('\n').split('\t')
        if len(cols) < 2 or not cols[0] or not cols[1]:
            continue
        en, uk = cols[0].strip(), cols[1].strip()
        if not en[0].isupper() or len(en) < 4:
            continue
        st = stems(uk)
        if st:
            terms.append((en, uk, re.compile(r'(?<![A-Za-z])' + re.escape(en) + r'(?![a-z])'), st))
    return terms


def records():
    """Yield (file, key, en_text, uk_text) for every translated record."""
    for src in sorted(glob.glob(os.path.join(ROOT, 'source', '**', '*.*'), recursive=True)):
        rel = os.path.relpath(src, os.path.join(ROOT, 'source'))
        ukp = os.path.join(ROOT, 'uk', rel)
        if not os.path.exists(ukp):
            continue
        a, b = open(src, 'rb').read(), open(ukp, 'rb').read()
        try:
            if rel.endswith('.mes'):
                ea, eb = arcfmt.parse_mes(a), arcfmt.parse_mes(b)
                if len(ea) != len(eb):
                    continue
                for x, y in zip(ea, eb):
                    yield rel, x['key'].decode('latin1'), x['value'].decode('cp1252', 'replace'), \
                        y['value'].decode('utf-8', 'replace')
            elif rel.endswith('.dlg'):
                la, lb = arcfmt.parse_dlg(a), arcfmt.parse_dlg(b)
                if len(la) != len(lb):
                    continue
                for x, y in zip(la, lb):
                    num = x['num'].decode('latin1')
                    yield rel, num, x['text'].decode('cp1252', 'replace'), y['text'].decode('utf-8', 'replace')
                    if not x['intelligence'].strip() and x['female'].strip():
                        yield rel, num + 'f', x['female'].decode('cp1252', 'replace'), \
                            y['female'].decode('utf-8', 'replace')
        except ValueError:
            continue


def main():
    verbose = '-v' in sys.argv
    flt = [a for a in sys.argv[1:] if not a.startswith('-')]
    terms = load_glossary()
    if flt:
        terms = [t for t in terms if any(f.lower() in t[0].lower() for f in flt)]
    hits = collections.Counter()
    miss = collections.defaultdict(list)
    anyterm = re.compile('|'.join(re.escape(t[0]) for t in terms)) if terms else None
    for rel, key, en, uk in records():
        if not en.strip() or not uk.strip() or not anyterm or not anyterm.search(en):
            continue
        low = uk.lower()
        for term, ukform, rx, st in terms:
            if not rx.search(en):
                continue
            hits[term] += 1
            if not any(all(s in low for s in alt) for alt in st):
                miss[term].append((rel, key, en, uk))
    rows = sorted(((len(v), t) for t, v in miss.items()), reverse=True)
    ukforms = {t[0]: t[1] for t in terms}
    for n, term in rows:
        print(f'{n:4d}/{hits[term]:<4d} {term} -> {ukforms[term]}')
        if verbose:
            for rel, key, en, uk in miss[term][:40]:
                print(f'       {rel} {{{key}}}')
                print(f'         EN: {en[:110]!r}')
                print(f'         UK: {uk[:110]!r}')
    print(f'\n{sum(n for n, _ in rows)} suspicious records across {len(rows)} terms '
          f'({len(terms)} proper-name terms checked)')


if __name__ == '__main__':
    main()
