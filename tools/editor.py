#!/usr/bin/env python3
"""Local dialogue editor for the translation: dialogue graph, EN beside UK,
in-place editing with live hints, search. Python stdlib only.

  python3 tools/editor.py [--port 8765]     ->  http://127.0.0.1:8765

Writes go through sheet.plan_edits (the same rules as `sheet.py apply`: female
field, gender gate, line endings, structure validated against source/) and are
refused if the record changed on disk since the page loaded it. After each write
qa.check runs on the file and its result is shown.

Only listens on 127.0.0.1; POST requires a JSON body (no cross-site forms).
"""
import json, os, re, sys, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import aipack, arcfmt, dlggraph, glosscheck, livecheck, qa, sheet
import npcart

STATIC = os.path.join(ROOT, 'tools', 'editor')
LOCK = threading.Lock()
_cache = {}


def _safe_rel(rel):
    rel = sheet._rel((rel or '').strip())
    if not re.fullmatch(r'dlg/[\w.\-]+\.dlg', rel):
        raise ValueError(f'bad path {rel!r}')
    return rel


def load(rel):
    """Parsed (source, uk) records of a dialogue, cached by mtime."""
    sp, up = os.path.join(ROOT, 'source', rel), os.path.join(ROOT, 'uk', rel)
    key = (os.path.getmtime(sp), os.path.getmtime(up))
    hit = _cache.get(rel)
    if hit and hit[0] == key:
        return hit[1], hit[2]
    src = arcfmt.parse_dlg(open(sp, 'rb').read())
    uk = arcfmt.parse_dlg(open(up, 'rb').read())
    if len(src) != len(uk):
        raise ValueError(f'{rel}: record count differs from source ({len(src)} vs {len(uk)})')
    _cache[rel] = (key, src, uk)
    return src, uk


def _d(b, enc):
    return b.decode(enc, 'replace')


def record_view(s, u):
    """One record as the UI sees it."""
    intel = _d(s['intelligence'], 'latin1').strip()
    kind = 'npc' if not intel else ('dumb' if intel.startswith('-') else 'pc')
    r = {'num': int(_d(s['num'], 'latin1').strip() or 0), 'kind': kind,
         'en': _d(s['text'], 'cp1252'), 'uk': _d(u['text'], 'utf-8'),
         'iq': intel, 'cond': _d(s['test'], 'latin1').strip(),
         'target': _d(s['target'], 'latin1').strip(), 'effects': _d(s['effects'], 'latin1').strip()}
    if kind == 'npc':
        r['enf'], r['ukf'] = _d(s['female'], 'cp1252'), _d(u['female'], 'utf-8')
        r['voice'] = r.pop('cond')
    else:
        r['gate'] = _d(s['female'], 'latin1').strip()
    r['blank'] = not (r['en'].strip() or r.get('enf', '').strip())
    if not r['blank']:
        r['hints'] = livecheck.hints('npc' if kind == 'npc' else 'pc', r['en'], r['uk'],
                                     r.get('enf', ''), r.get('ukf', ''), r.get('gate', ''))
    return r


KINDS = (('examine', re.compile(r'exa(mine)?\b|_exa_|examine|exa$')),
         ('resurrect', re.compile(r'resurrect')))
_meta, _meta_state = {}, {'ready': False}


def title_of(rel):
    name = re.sub(r'^\d+', '', os.path.basename(rel))[:-4]
    name = re.sub(r'(?<=[a-z])dialogue$', '', name)
    return name.replace('_', ' ').strip()


def kind_of(rel):
    low = os.path.basename(rel).lower()[:-4]
    return next((k for k, rx in KINDS if rx.search(low)), 'talk')


def file_meta(rel):
    """Context for the file list: kind, greeting (first real NPC line, UK),
    line counts, problem counts. Cheap enough to recompute after a save."""
    src, uk = load(rel)
    kind = kind_of(rel)
    greet, npc, pc, err, warn = '', 0, 0, 0, 0
    for s, u in zip(src, uk):
        r = record_view(s, u)
        if r['blank']:
            continue
        if r['kind'] == 'npc':
            npc += 1
        else:
            pc += 1
        en = r['en'] or r.get('enf', '')
        if not greet and r['kind'] == 'npc' and en.strip() and not livecheck.ENGINE.match(en):
            greet = r['uk'].strip() or r.get('ukf', '').strip()
        sev = [i['sev'] for i in r['hints']['issues']]
        err += 'err' in sev
        warn += 'err' not in sev and 'warn' in sev
    if not greet:  # e.g. master-mage files open with an engine "G:" and go straight to PC lines
        greet = next((_d(u['text'], 'utf-8').strip() for s, u in zip(src, uk)
                      if s['text'].strip() and not livecheck.ENGINE.match(_d(s['text'], 'cp1252'))), '')
    return {'title': title_of(rel), 'kind': kind, 'greet': greet[:220], 'npc': npc, 'pc': pc,
            'err': err, 'warn': warn}


def build_meta():
    for row in status_rows():
        try:
            tm_update(row['path'])
            _meta[row['path']] = file_meta(row['path'])
        except (OSError, ValueError) as e:
            _meta[row['path']] = {'title': title_of(row['path']), 'kind': 'talk', 'greet': '',
                                  'error': str(e)}
    _meta_state['ready'] = True


def refresh_meta(rels):
    for rel in rels:
        try:
            tm_update(rel)
            _meta[rel] = file_meta(rel)
        except (OSError, ValueError):
            pass


# ---------- glossary (glossary/glossary.tsv: en, uk, note; EN may repeat) ----------

GLOSSARY = os.path.join(ROOT, 'glossary', 'glossary.tsv')
_gl = {'mtime': None, 'rows': []}


def gl_rows():
    """[{i (line index), en, uk, note, rx, low, st}] — header and blank lines skipped."""
    m = os.path.getmtime(GLOSSARY)
    if _gl['mtime'] != m:
        rows = []
        for i, line in enumerate(open(GLOSSARY, encoding='utf-8').read().split('\n')):
            c = line.split('\t')
            if i == 0 or len(c) < 2 or not c[0].strip() or not c[1].strip():
                continue
            en = c[0].strip()
            term = re.sub(r'\s*\(.*?\)\s*', ' ', en).strip()  # "Gorgoth (істота)" -> "Gorgoth"
            proper = term[:1].isupper()
            rx = re.compile(r'(?<![A-Za-z])' + re.escape(term) + (r'(?![a-z])' if proper else r"(?:s|es|'s)?(?![A-Za-z])"),
                            0 if proper else re.I)
            rows.append({'i': i, 'en': en, 'uk': c[1].strip(), 'note': c[2].strip() if len(c) > 2 else '',
                         'rx': rx, 'low': term.lower(), 'st': glosscheck.stems(c[1].strip())})
        _gl.update(mtime=m, rows=rows)
    return _gl['rows']


def gl_public(g):
    return {k: g[k] for k in ('i', 'en', 'uk', 'note')}


def terms_for(en, uk, kind='npc'):
    """Glossary rows whose EN term occurs in en; ok = the UK form is present in uk.
    Rows marked "(dumb...)" apply to dumb-PC lines only; rows with the same
    EN+UK are merged (their notes joined)."""
    out, seen, low_en, low_uk = [], {}, en.lower(), uk.lower()
    for g in gl_rows():
        if ('dumb' in g['en'].lower()) != (kind == 'dumb') and 'dumb' in g['en'].lower():
            continue
        if g['low'] in low_en and g['rx'].search(en):
            key = (g['low'], g['uk'])
            if key in seen:
                if g['note'] and g['note'] not in seen[key]['note']:
                    seen[key]['note'] = (seen[key]['note'] + ' | ' + g['note']).strip(' |')
                continue
            ok = any(all(s in low_uk for s in alt) for alt in g['st']) if g['st'] else (g['uk'].lower() in low_uk)
            seen[key] = {**gl_public(g), 'ok': ok}
            out.append(seen[key])
    return out


def api_glossary(q):
    term = (q.get('q') or '').strip().lower()
    rows = [gl_public(g) for g in gl_rows()
            if not term or term in g['en'].lower() or term in g['uk'].lower() or term in g['note'].lower()]
    return {'rows': rows[:400], 'total': len(rows)}


def api_glossary_save(body):
    """add: append a row. update/delete: row i, refused unless the line still
    equals what the page showed (expect) — glossary is shared by all sessions."""
    clean = lambda v: re.sub(r'[\t\r\n]+', ' ', str(v or '')).strip()
    act = body.get('action')
    en, uk, note = clean(body.get('en')), clean(body.get('uk')), clean(body.get('note'))
    if act in ('add', 'update') and (not en or not uk):
        return {'ok': False, 'errors': ['потрібні EN і UK']}
    with LOCK:
        lines = open(GLOSSARY, encoding='utf-8').read().split('\n')
        new = '\t'.join([en, uk, note]) if note else '\t'.join([en, uk, ''])
        if act == 'add':
            if any(l.split('\t')[:2] == [en, uk] for l in lines):
                return {'ok': False, 'errors': [f'рядок «{en} → {uk}» уже є']}
            while lines and lines[-1] == '':
                lines.pop()
            lines.append(new)
            lines.append('')
        elif act in ('update', 'delete'):
            ex = body.get('expect') or {}
            want = [ex.get('en', ''), ex.get('uk', '')]
            i = int(body.get('i', -1))
            match = lambda l: [c.strip() for c in l.split('\t')[:2]] == want and \
                (l.split('\t')[2].strip() if l.count('\t') >= 2 else '') == ex.get('note', '')
            if not (0 < i < len(lines) and match(lines[i])):
                hits = [k for k, l in enumerate(lines) if k and match(l)]
                if len(hits) != 1:
                    return {'ok': False, 'errors': ['рядок глосарія змінено поза редактором — онови список']}
                i = hits[0]
            if act == 'update':
                lines[i] = new
            else:
                del lines[i]
        else:
            return {'ok': False, 'errors': ['action: add | update | delete']}
        tmp = GLOSSARY + '.editor-tmp'
        with open(tmp, 'w', encoding='utf-8', newline='') as fh:
            fh.write('\n'.join(lines))
        os.replace(tmp, GLOSSARY)
    return {'ok': True}


# ---------- translation memory: same EN text elsewhere (as tools/tmcheck.py slots) ----------

_tm, _tm_files = {}, {}


def _tm_entries(rel):
    src, uk = load(rel)
    out = []
    for s, u in zip(src, uk):
        intel = s['intelligence'].strip()
        num = int(_d(s['num'], 'latin1').strip() or 0)
        fields = [('pc-dumb' if intel.startswith(b'-') else 'pc', 'text')] if intel else [('npc', 'text'), ('npcf', 'female')]
        for slot, f in fields:
            en = ' '.join(_d(s[f], 'cp1252').split())
            if len(en) < 4 or livecheck.ENGINE.match(en):
                continue
            out.append(((slot, en), (rel, num, ' '.join(_d(u[f], 'utf-8').split()))))
    return out


def tm_update(rel):
    for key, loc in _tm_files.pop(rel, []):
        lst = _tm.get(key)
        if lst:
            _tm[key] = [x for x in lst if x[:2] != loc[:2]]
    ent = _tm_entries(rel)
    _tm_files[rel] = ent
    for key, loc in ent:
        _tm.setdefault(key, []).append(loc)


def tm_for(rel, num, slot, en, uk):
    """Other places with the same EN in the same slot: {'same': n, 'other': [{uk, n, at}]}."""
    if not _meta_state['ready']:
        return None
    lst = [x for x in _tm.get((slot, ' '.join(en.split())), []) if (x[0], x[1]) != (rel, num)]
    if not lst:
        return None
    mine = ' '.join(uk.split())
    groups = {}
    for r, n, u in lst:
        groups.setdefault(u, []).append(f'{r}#{n}')
    other = [{'uk': u, 'n': len(at), 'at': at[:4]} for u, at in groups.items() if u != mine]
    other.sort(key=lambda x: -x['n'])
    return {'same': len(groups.get(mine, [])), 'other': other[:5]}


INDEX = os.path.join(ROOT, 'docs', 'dlg-index.tsv')
INDEX_COLS = ('title', 'who', 'where', 'context')
_index = {'mtime': None, 'rows': {}}


def load_index():
    """docs/dlg-index.tsv: file, title, who, where, context (Ukrainian, human-editable)."""
    if not os.path.exists(INDEX):
        return {}
    m = os.path.getmtime(INDEX)
    if _index['mtime'] != m:
        rows = {}
        for line in open(INDEX, encoding='utf-8'):
            c = line.rstrip('\n').split('\t')
            if c[0] and c[0] != 'file':
                rows[c[0]] = dict(zip(INDEX_COLS, (c[1:] + [''] * 4)[:4]))
        _index.update(mtime=m, rows=rows)
    return _index['rows']


def api_index_save(body):
    rel = _safe_rel(body.get('path'))
    vals = {k: re.sub(r'[\t\r\n]+', ' ', str(body.get(k, ''))).strip() for k in INDEX_COLS}
    with LOCK:
        rows = dict(load_index())
        rows[rel] = vals
        tmp = INDEX + '.editor-tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write('file\t' + '\t'.join(INDEX_COLS) + '\n')
            for f in sorted(rows):
                fh.write(f + '\t' + '\t'.join(rows[f].get(k, '') for k in INDEX_COLS) + '\n')
        os.replace(tmp, INDEX)
    return {'ok': True, 'index': vals}


_pics = npcart.Pictures(os.environ.get('ARCANUM_GAME', npcart.GAME))
_pics_lock = threading.Lock()


def speakers():
    """dlg number -> NPCs that speak it, from the player's game copy ({} without one)."""
    with _pics_lock:
        try:
            return _pics.index
        except Exception as e:  # a damaged or unusual install must not break the editor
            sys.stderr.write('npcart: %s\n' % e)
            _pics._index = {}
            return {}


def own_portrait(npc):
    """True when the NPC has its own portrait (companions: portrait/NPC*.bmp)."""
    try:
        names = _pics.gameport
    except AttributeError:
        names = _pics.gameport = _pics.game.mes('portrait/gameport.mes')
    return (names.get(npc.get('portrait') or -1) or '').upper().startswith('NPC')


def api_files():
    rows, ix, spk = [], load_index(), speakers()
    for r in status_rows():
        m = _meta.get(r['path']) or {'title': title_of(r['path']), 'kind': kind_of(r['path'])}
        num = int(re.match(r'dlg/(\d+)', r['path']).group(1))
        s = spk.get(num)
        sp = {'name': s[0]['name'], 'proto': s[0]['proto'], 'maps': s[0]['maps'][:4],
              'own': own_portrait(s[0])} if s else None
        rows.append({**r, **m, 'ix': ix.get(r['path']), 'spk': sp})
    return {'ready': _meta_state['ready'], 'files': rows, 'game': bool(spk)}


def api_pic(q):
    num = int(q.get('num', ''))
    with _pics_lock:
        return _pics.get(num)


def status_rows():
    """Dialogues to list: from status.tsv when the repo has one (working repo),
    else every uk/dlg/*.dlg that has a source/ counterpart (public repo)."""
    rows, st = [], os.path.join(ROOT, 'status.tsv')
    if os.path.exists(st):
        for line in open(st, encoding='utf-8'):
            c = line.rstrip('\n').split('\t')
            if len(c) >= 7 and c[1] == 'dlg' and c[2] == 'translate':
                rows.append({'path': c[0], 'records': c[3], 'words': c[4], 'status': c[6]})
        return rows
    for f in sorted(os.listdir(os.path.join(ROOT, 'uk', 'dlg'))):
        if f.endswith('.dlg') and os.path.exists(os.path.join(ROOT, 'source', 'dlg', f)):
            rows.append({'path': 'dlg/' + f, 'records': '', 'words': '', 'status': ''})
    return rows


def api_dialog(q):
    rel = _safe_rel(q.get('path'))
    src, uk = load(rel)
    recs = [record_view(s, u) for s, u in zip(src, uk)]
    for r in recs:
        if r['blank'] or livecheck.ENGINE.match(r['en']):
            continue
        r['terms'] = terms_for(r['en'] + ' ' + r.get('enf', ''), r['uk'] + ' ' + r.get('ukf', ''), r['kind'])
        if r['kind'] == 'npc':
            r['tm'] = {'M': tm_for(rel, r['num'], 'npc', r['en'], r['uk']) if r['en'].strip() else None,
                       'F': tm_for(rel, r['num'], 'npcf', r['enf'], r['ukf']) if r['enf'].strip() else None}
        else:
            r['tm'] = {'M': tm_for(rel, r['num'], 'pc-dumb' if r['kind'] == 'dumb' else 'pc', r['en'], r['uk'])}
    graph = dlggraph.build(src, 'cp1252')
    for n in graph['nodes']:  # the UI takes texts from records; keep the graph light
        n.pop('text'), n.pop('female')
        for o in n['options']:
            o.pop('text')
    st = next((r['status'] for r in status_rows() if r['path'] == rel), '')
    return {'path': rel, 'status': st, 'records': [r for r in recs if not r['blank']], 'graph': graph}


def api_search(q):
    term = (q.get('q') or '').strip()
    if not term:
        return {'files': [], 'hits': []}
    files = status_rows()
    m = re.fullmatch(r'(\d{3,5})(?:\s*#\s*(\d+))?', term)
    if m:
        hit = [f for f in files if os.path.basename(f['path']).startswith(m.group(1).zfill(5))]
        return {'files': hit, 'hits': [], 'line': int(m.group(2)) if m.group(2) else None}
    low = term.lower()
    named = [f for f in files if low in f['path'].lower()]
    hits = []
    for f in files:
        try:
            src, uk = load(f['path'])
        except (OSError, ValueError):
            continue
        for s, u in zip(src, uk):
            for fld in ('text', 'female'):
                if fld == 'female' and s['intelligence'].strip():
                    continue
                en, ut = _d(s[fld], 'cp1252'), _d(u[fld], 'utf-8')
                if low in en.lower() or low in ut.lower():
                    hits.append({'path': f['path'], 'num': int(_d(s['num'], 'latin1').strip() or 0),
                                 'en': en[:160], 'uk': ut[:160]})
                    break
            if len(hits) >= 300:
                return {'files': named, 'hits': hits, 'truncated': True}
    return {'files': named, 'hits': hits}


def api_check(body):
    return livecheck.hints(body.get('kind', 'pc'), body.get('en', ''), body.get('uk', ''),
                           body.get('enf', ''), body.get('ukf', ''), body.get('gate', ''))


def api_save(body):
    rel = _safe_rel(body.get('path'))
    key = str(int(body['num']))
    edit, expect = {}, {}
    for f in ('M', 'F'):
        if f in body and body[f] is not None:
            edit[f] = body[f].replace('\r\n', '\n')
        if body.get('expect', {}).get(f) is not None:
            expect[f] = body['expect'][f]
    if not edit:
        return {'ok': False, 'errors': ['нічого зберігати']}
    with LOCK:
        plans, errs, notes, _ = sheet.plan_edits({rel: {key: edit}}, {rel: {key: expect}})
        if errs:
            return {'ok': False, 'errors': errs}
        write_plans(plans)
        problems = qa.check(rel)
        refresh_meta([rel])
        src, uk = load(rel)
    rec = next(record_view(s, u) for s, u in zip(src, uk) if _d(s['num'], 'latin1').strip() == key)
    rec['terms'] = terms_for(rec['en'] + ' ' + rec.get('enf', ''), rec['uk'] + ' ' + rec.get('ukf', ''), rec['kind'])
    return {'ok': True, 'notes': notes, 'qa': problems, 'record': rec}


def write_plans(plans):
    for _, (up, new) in plans.items():
        tmp = up + '.editor-tmp'
        with open(tmp, 'wb') as fh:
            fh.write(new)
        os.replace(tmp, up)


def dialog_views(rel):
    src, uk = load(rel)
    return [r for r in (record_view(s, u) for s, u in zip(src, uk)) if not r['blank']], src


def api_pack(body):
    rel = _safe_rel(body.get('path'))
    scope = body.get('scope', 'node')
    if scope not in ('node', 'problems', 'all'):
        raise ValueError('scope: node | problems | all')
    recs, src = dialog_views(rel)
    graph = dlggraph.build(src, 'cp1252')
    focus = int(body['num']) if scope == 'node' else None
    text = aipack.build(rel, recs, graph, scope, focus, about=load_index().get(rel))
    return {'text': text}


def api_import_preview(body):
    """Parse an agent answer (sheet.py edit format) into per-record diffs.
    Nothing is written; each item carries its own validation errors."""
    files, perrs = sheet.parse_edit_lines((body.get('text') or '').splitlines())
    items = []
    for rel0, edits in files.items():
        try:
            rel = _safe_rel(rel0)
            recs, _ = dialog_views(rel)
        except (ValueError, OSError) as e:
            perrs.append(f'@ {rel0}: {e}')
            continue
        by = {r['num']: r for r in recs}
        for key, ed in edits.items():
            num = int(key) if key.isdigit() else None
            r = by.get(num)
            if r is None:
                perrs.append(f'{rel} #{key}: такого запису з текстом нема')
                continue
            ed = dict(ed)
            if r['kind'] == 'npc' and '' in ed and 'M' not in ed:
                ed['M'] = ed.pop('')
            old = {'M': r['uk']} if r['kind'] != 'npc' else {'M': r['uk'], 'F': r['ukf']}
            new = {'M': ed.get('M', ed.get('', r['uk']))}
            if r['kind'] == 'npc':
                if not r['en'].strip():
                    new['M'] = r['uk']
                new['F'] = ed['F'] if 'F' in ed else (new['M'] if r['ukf'] == r['uk'] and r['enf'].strip() else r['ukf'])
            _, errs, _, _ = sheet.plan_edits({rel: {key: ed}})
            h = livecheck.hints('npc' if r['kind'] == 'npc' else 'pc', r['en'], new['M'],
                                r.get('enf', ''), new.get('F', ''), r.get('gate', ''))
            items.append({'path': rel, 'num': num, 'kind': r['kind'], 'en': r['en'], 'enf': r.get('enf', ''),
                          'old': old, 'new': new, 'given': sorted(ed), 'errors': errs, 'hints': h,
                          'changed': any(new.get(f) != old.get(f) for f in old)})
    return {'items': items, 'errors': perrs}


def api_import_apply(body):
    """Write only the accepted items; all-or-nothing, refused if any record
    changed on disk since the preview."""
    files, expect = {}, {}
    for it in body.get('items', []):
        rel, key = _safe_rel(it['path']), str(int(it['num']))
        ed = {f: it['new'][f].replace('\r\n', '\n') for f in it.get('fields', []) if f in it['new']}
        if ed:
            files.setdefault(rel, {})[key] = ed
            expect.setdefault(rel, {})[key] = {f: it['old'][f] for f in ed if f in it['old']}
    if not files:
        return {'ok': False, 'errors': ['нічого не вибрано']}
    with LOCK:
        plans, errs, notes, total = sheet.plan_edits(files, expect)
        if errs:
            return {'ok': False, 'errors': errs}
        write_plans(plans)
        problems = {rel: qa.check(rel) for rel in plans}
        refresh_meta(plans)
    return {'ok': True, 'written': total, 'files': sorted(plans), 'notes': notes, 'qa': problems}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        if '/api/' in (args[0] if args else '') and 'POST' in str(args[0]):
            sys.stderr.write('%s\n' % (fmt % args))

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'max-age=3600' if ctype == 'image/png' else 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == '/api/files':
                return self._send(200, api_files())
            if u.path == '/api/dialog':
                return self._send(200, api_dialog(q))
            if u.path == '/api/search':
                return self._send(200, api_search(q))
            if u.path == '/api/glossary':
                return self._send(200, api_glossary(q))
            if u.path == '/api/pic':
                data = api_pic(q)
                if not data:
                    return self._send(404, {'error': 'no picture'})
                return self._send(200, data, 'image/png')
            name = 'index.html' if u.path in ('/', '/index.html') else u.path.lstrip('/')
            if not re.fullmatch(r'[\w\-]+\.(html|js|css)', name):
                return self._send(404, {'error': 'not found'})
            p = os.path.join(STATIC, name)
            if not os.path.exists(p):
                return self._send(404, {'error': 'not found'})
            ctype = {'html': 'text/html', 'js': 'text/javascript', 'css': 'text/css'}[name.rsplit('.', 1)[1]]
            return self._send(200, open(p, 'rb').read(), ctype + '; charset=utf-8')
        except (ValueError, OSError, KeyError) as e:
            return self._send(400, {'error': str(e)})

    def do_POST(self):
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            return self._send(415, {'error': 'JSON only'})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or b'{}')
            if self.path == '/api/check':
                return self._send(200, api_check(body))
            if self.path == '/api/save':
                return self._send(200, api_save(body))
            if self.path == '/api/glossary':
                return self._send(200, api_glossary_save(body))
            if self.path == '/api/index':
                return self._send(200, api_index_save(body))
            if self.path == '/api/pack':
                return self._send(200, api_pack(body))
            if self.path == '/api/import/preview':
                return self._send(200, api_import_preview(body))
            if self.path == '/api/import/apply':
                return self._send(200, api_import_apply(body))
            return self._send(404, {'error': 'not found'})
        except (ValueError, OSError, KeyError, TypeError) as e:
            return self._send(400, {'error': str(e)})


def main():
    port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 8765
    srv = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=build_meta, daemon=True).start()
    print(f'редактор діалогів: http://127.0.0.1:{port}   (Ctrl+C — зупинити)')
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
