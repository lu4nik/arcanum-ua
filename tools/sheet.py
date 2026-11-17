#!/usr/bin/env python3
"""Reviewer's workbench: a compact side-by-side sheet of a file, and a safe way
to write edits back. Use it instead of reading raw .dlg/.mes and instead of
ad-hoc replace scripts.

  python3 tools/sheet.py show dlg/01040ristezze.dlg            # whole file
  python3 tools/sheet.py show dlg/01040ristezze.dlg 100-250    # records 100..250
  python3 tools/sheet.py show mes/gamedesc.mes 30000-30100
  python3 tools/sheet.py show4 gd_cls 1000-1200               # 4 gender variants side by side
  python3 tools/sheet.py show4 gd_cls --odd                   # only records whose variants
                                                              # diverge by more than gender forms
  python3 tools/sheet.py apply edits.txt                       # write edits
  python3 tools/sheet.py apply edits.txt --dry                 # validate only

SHEET FORMAT (dlg)
  #20 NPC
    EN: Nobody just "HAPPENS BY" Ristezze's...
    UK: До Рістецце ніхто не заходить «ВИПАДКОВО»!...
    UKf: ...            <- shown only when the female-PC text differs from UK
    ENf: ...            <- shown only when the original itself has a different female text
  #21 PC int=5 ->30       <- player line: intelligence gate, target record
    EN: ...
    UK: ...
  #22 DUMB int=-4 ->30    <- dumb-PC line ("Моя не розуміти" style)
Records are listed in file order; "->N" is where the line leads, follow it to
read a branch. Player lines with a gender gate show g=0 (female only) / g=1.

EDIT FILE FORMAT (plain text, UTF-8)
  @ dlg/01040ristezze.dlg
  #20 M: новий текст для гравця-чоловіка
  #20 F: новий текст для гравчині
  #21: новий текст репліки гравця
  @ mes/gamedesc.mes
  #30038: Рістецце
Rules enforced by apply:
  * NPC record: give M, or M and F. If only M is given and the old F was
    identical to the old M, F follows M automatically. If the old F DIFFERED
    (gendered wording), you must give F too — otherwise the edit is rejected.
    "#N:" on an NPC record means M (same rule).
  * Player record: only "#N:"; the gender gate and all other groups are untouchable.
  * A literal "\\n" in the text becomes a line break (books, notes).
  * Text must be cp1251-encodable, without "…" and without braces.
  * The file keeps its line endings; structure is validated against source/
    before anything is written. Nothing is written if any edit is rejected.
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import arcfmt


def _rel(arg):
    arg = arg.replace('\\', '/')
    for pre in ('uk/', 'source/'):
        if arg.startswith(pre):
            arg = arg[len(pre):]
    return arg


def _one(s):
    return s.replace('\r\n', '\n').replace('\n', '\\n')


def _in_range(key, rng):
    if not rng:
        return True
    return key.isdigit() and rng[0] <= int(key) <= rng[1]


def show(rel, rng):
    src = open(os.path.join(ROOT, 'source', rel), 'rb').read()
    uk = open(os.path.join(ROOT, 'uk', rel), 'rb').read()
    out = []
    if rel.endswith('.mes'):
        a, b = arcfmt.parse_mes(src), arcfmt.parse_mes(uk)
        assert len(a) == len(b), 'record count differs from source'
        for x, y in zip(a, b):
            k = x['key'].decode('latin1').strip()
            if not _in_range(k, rng) or not x['value'].strip():
                continue
            out.append(f'#{k}\n  EN: {_one(x["value"].decode("cp1252", "replace"))}\n'
                       f'  UK: {_one(y["value"].decode("utf-8", "replace"))}')
    else:
        a, b = arcfmt.parse_dlg(src), arcfmt.parse_dlg(uk)
        assert len(a) == len(b), 'record count differs from source'
        for x, y in zip(a, b):
            k = x['num'].decode('latin1').strip()
            en = x['text'].decode('cp1252', 'replace')
            # some NPC records carry text only in the female field (male empty)
            only_f = not x['intelligence'].strip() and x['female'].strip()
            if not _in_range(k, rng) or not (en.strip() or only_f):
                continue
            intel = x['intelligence'].decode('latin1').strip()
            tgt = x['target'].decode('latin1').strip()
            if intel:
                gate = x['female'].decode('latin1').strip()
                head = f'#{k} {"DUMB" if intel.startswith("-") else "PC"} int={intel}' + \
                       (f' g={gate}' if gate else '') + (f' ->{tgt}' if tgt else '')
                out.append(f'{head}\n  EN: {_one(en)}\n  UK: {_one(y["text"].decode("utf-8", "replace"))}')
            else:
                enf = x['female'].decode('cp1252', 'replace')
                ukm, ukf = y['text'].decode('utf-8', 'replace'), y['female'].decode('utf-8', 'replace')
                rec = f'#{k} NPC' + (f' ->{tgt}' if tgt and tgt != '0' else '')
                if not en.strip():
                    rec += ' (лише жіноче поле: правити тільки "#N F:")'
                else:
                    rec += f'\n  EN: {_one(en)}'
                if enf.strip() and enf != en:
                    rec += f'\n  ENf: {_one(enf)}'
                if en.strip():
                    rec += f'\n  UK: {_one(ukm)}'
                if ukf.strip() and ukf != ukm:
                    rec += f'\n  UKf: {_one(ukf)}'
                out.append(rec)
    print(f'@ {rel}  ({len(out)} records)')
    print('\n'.join(out))


VARIANTS = ('m2m', 'm2f', 'f2m', 'f2f')


def _odd(m, o):
    """True when variant o differs from base m by more than gendered endings."""
    import difflib
    tok = lambda t: re.findall(r"[\w'%]+|[^\w\s]", t.lower())
    a, b = tok(m), tok(o)
    ops = difflib.SequenceMatcher(None, a, b).get_opcodes()
    ins = sum((i2 - i1) + (j2 - j1) for op, i1, i2, j1, j2 in ops if op in ('insert', 'delete'))
    rep = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in ops if op == 'replace')
    return (ins >= 1 and ins + rep >= 2) or rep >= 5 or abs(len(a) - len(b)) >= 2


def show4(base, rng, odd=False):
    """Rumor/greeting files exist in 4 copies: speaker gender 2 listener gender.
    Print each record once: EN, then the m2m text, then only the variants that
    differ from it. Edit each variant under its own "@ mes/<base>_<v>.mes"."""
    data = {}
    for v in VARIANTS:
        up = os.path.join(ROOT, 'uk', 'mes', f'{base}_{v}.mes')
        if os.path.exists(up):
            data[v] = {e['key'].decode('latin1').strip(): e['value'].decode('utf-8', 'replace')
                       for e in arcfmt.parse_mes(open(up, 'rb').read())}
    assert 'm2m' in data, f'нема uk/mes/{base}_m2m.mes'
    src = arcfmt.parse_mes(open(os.path.join(ROOT, 'source', 'mes', f'{base}_m2m.mes'), 'rb').read())
    n = 0
    print(f'@ mes/{base}_{{{",".join(data)}}}.mes — m2m = чоловік каже чоловікові, f2m = жінка чоловікові тощо')
    for x in src:
        k = x['key'].decode('latin1').strip()
        if not _in_range(k, rng) or not x['value'].strip():
            continue
        base_uk = data['m2m'].get(k, '')
        if odd and not any(v in data and data[v].get(k, '').strip() and base_uk.strip()
                           and _odd(base_uk, data[v][k]) for v in VARIANTS[1:]):
            continue
        n += 1
        print(f'#{k}\n  EN: {_one(x["value"].decode("cp1252", "replace"))}\n  m2m: {_one(base_uk)}')
        for v in VARIANTS[1:]:
            if v in data and data[v].get(k, '') != base_uk:
                print(f'  {v}: {_one(data[v].get(k, ""))}')
    print(f'({n} records)')


EDIT = re.compile(r'^#(\S+?)(?:\s+([MF]))?:\s?(.*)$')


def parse_edits(path):
    return parse_edit_lines(open(path, encoding='utf-8'))


def parse_edit_lines(lines):
    """Edit-file text (iterable of lines) -> ({rel: {key: {''|'M'|'F': text}}}, errors)."""
    files, cur, errs = {}, None, []
    for n, line in enumerate(lines, 1):
        line = line.rstrip('\n').rstrip('\r')
        if not line.strip() or line.lstrip().startswith('//'):
            continue
        if line.startswith('@'):
            cur = _rel(line[1:].strip().split('  ')[0])
            files.setdefault(cur, {})
            continue
        m = EDIT.match(line)
        if not m or cur is None:
            errs.append(f'рядок {n}: не розпізнано: {line[:60]!r}')
            continue
        key, which, text = m.group(1), m.group(2) or '', m.group(3).replace('\\n', '\n')
        files[cur].setdefault(key, {})[which] = text
    return files, errs


def check_text(t):
    if '…' in t:
        return 'символ «…» заборонено (пиши три крапки)'
    if '{' in t or '}' in t:
        return 'фігурні дужки в тексті'
    try:
        t.encode('cp1251')
    except UnicodeEncodeError as e:
        return f'символ поза cp1251: {t[e.start:e.end]!r}'
    return None


def plan_edits(files, expect=None):
    """files: {rel: {key: {'' | 'M' | 'F': text}}} -> (plans, errs, notes, total).
    plans: {rel: (uk_path, new_bytes)}; nothing is written here.
    expect (optional): {rel: {key: {'M'|'F'|'': current_text}}} — the UK text the
    caller last saw; a record whose file content differs is rejected (somebody
    else edited it meanwhile)."""
    plans, notes, total, errs = {}, [], 0, []
    for rel, edits in files.items():
        up = os.path.join(ROOT, 'uk', rel)
        sp = os.path.join(ROOT, 'source', rel)
        if not os.path.exists(up) or not os.path.exists(sp):
            errs.append(f'{rel}: нема файлу')
            continue
        data, src = open(up, 'rb').read(), open(sp, 'rb').read()
        crlf = b'\r\n' in data

        def enc(t):
            t = t.replace('\r\n', '\n')
            return (t.replace('\n', '\r\n') if crlf else t).encode('utf-8')

        reps, seen = [], set()
        if rel.endswith('.mes'):
            for e in arcfmt.parse_mes(data):
                k = e['key'].decode('latin1').strip()
                if k in edits and k not in seen:
                    seen.add(k)
                    ed = edits[k]
                    cur = {'': e['value'].decode('utf-8', 'replace')}
                    if _conflict(expect, rel, k, cur):
                        errs.append(f'{rel} #{k}: запис змінено поза редактором — перезавантаж')
                        continue
                    if set(ed) - {''}:
                        errs.append(f'{rel} #{k}: у .mes лише "#ключ: текст"')
                        continue
                    bad = check_text(ed[''])
                    if bad:
                        errs.append(f'{rel} #{k}: {bad}')
                        continue
                    reps.append((e['vstart'], e['vend'], enc(ed[''])))
        else:
            for l in arcfmt.parse_dlg(data):
                k = l['num'].decode('latin1').strip()
                if k not in edits or k in seen:
                    continue
                seen.add(k)
                ed = dict(edits[k])
                cur = {'M': l['text'].decode('utf-8', 'replace'), 'F': l['female'].decode('utf-8', 'replace')}
                if _conflict(expect, rel, k, cur):
                    errs.append(f'{rel} #{k}: запис змінено поза редактором — перезавантаж')
                    continue
                if '' in ed and 'M' not in ed:
                    ed['M'] = ed.pop('')
                for t in ed.values():
                    bad = check_text(t)
                    if bad:
                        errs.append(f'{rel} #{k}: {bad}')
                if l['intelligence'].strip():
                    if 'F' in ed:
                        errs.append(f'{rel} #{k}: це репліка гравця, поле F — числовий фільтр, його не можна міняти')
                        continue
                    if 'M' in ed:
                        reps.append((*l['spans'][1], enc(ed['M'])))
                    continue
                oldm, oldf = l['text'], l['female']
                if 'M' in ed:
                    reps.append((*l['spans'][1], enc(ed['M'])))
                if 'F' in ed:
                    if len(l['spans']) > 2:
                        reps.append((*l['spans'][2], enc(ed['F'])))
                elif 'M' in ed and oldf.strip():
                    if oldf == oldm:
                        reps.append((*l['spans'][2], enc(ed['M'])))
                        notes.append(f'{rel} #{k}: F продубльовано з M')
                    else:
                        errs.append(f'{rel} #{k}: старе жіноче поле відрізнялося від чоловічого — дай і "#{k} F: ..."')
        missing = set(edits) - seen
        for k in sorted(missing):
            errs.append(f'{rel} #{k}: запису з таким номером нема')
        if reps:
            new = arcfmt.substitute(data, sorted(set(reps)))
            probs = arcfmt.validate_pair(src, new, 'mes' if rel.endswith('.mes') else 'dlg')
            if probs:
                errs += [f'{rel}: структура: {p}' for p in probs[:5]]
            plans[rel] = (up, new)
            total += len(seen)
    return plans, errs, notes, total


def _conflict(expect, rel, key, cur):
    seen = (expect or {}).get(rel, {}).get(key)
    if not seen:
        return False
    norm = lambda t: t.replace('\r\n', '\n')
    return any(norm(cur.get(f if f else '', cur.get('M', ''))) != norm(v) for f, v in seen.items())


def apply(path, dry):
    files, errs = parse_edits(path)
    plans, errs2, notes, total = plan_edits(files)
    errs += errs2
    if errs:
        print(f'ВІДХИЛЕНО — {len(errs)} помилок, нічого не записано:')
        for e in errs[:40]:
            print('  ' + e)
        sys.exit(1)
    if not dry:
        for rel, (up, new) in plans.items():
            open(up, 'wb').write(new)
    print(f'{"перевірено" if dry else "записано"}: {total} записів у {len(plans)} файлах')
    for n in notes[:12]:
        print('  ' + n)
    if len(notes) > 12:
        print(f'  ...і ще {len(notes) - 12} автодублів F')
    if not dry and plans:
        print('далі: python3 tools/qa.py ' + ' '.join(f'"uk/{r}"' for r in plans) +
              '  (+ genderlint.py для .dlg, widthcheck.py для назв у .mes)')


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == 'show':
        rng = None
        if len(sys.argv) > 3 and re.match(r'^\d+-\d+$', sys.argv[3]):
            a, b = sys.argv[3].split('-')
            rng = (int(a), int(b))
        show(_rel(sys.argv[2]), rng)
    elif len(sys.argv) >= 3 and sys.argv[1] == 'show4':
        rng = None
        if len(sys.argv) > 3 and re.match(r'^\d+-\d+$', sys.argv[3]):
            a, b = sys.argv[3].split('-')
            rng = (int(a), int(b))
        show4(sys.argv[2], rng, '--odd' in sys.argv)
    elif len(sys.argv) >= 3 and sys.argv[1] == 'apply':
        apply(sys.argv[2], '--dry' in sys.argv)
    else:
        print(__doc__)


if __name__ == '__main__':
    main()
