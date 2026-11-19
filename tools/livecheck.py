#!/usr/bin/env python3
"""Per-record hints for the dialogue editor: the same rules as the batch
checkers, applied to ONE record so they can run while typing.

Reuses, does not duplicate:
  sheet.check_text       — characters the game cannot show / braces
  widthcheck.layout      — engine line breaking on our .art fonts
  glosscheck             — glossary proper names (stem match)
  genderlint             — gendered forms in shared PC lines / wrong NPC field

Geometry (arcanum-ce) — NOT confirmed for dialogue: ~/arcanum_overflow.log has
never logged a dialogue line, so widths are info only, compared to the original:
  NPC reply   — info panel, intgame.c stru_5C7108 = 291x78, flare12 (15 px/line).
  PC response — tc.c: one line per option, flare12 (art 229); the draw rect is
                the iso window width minus 2x6 px (800 -> 788: past that the
                engine cuts it = warning), the visible box is 400 px (~388: info).

hints(...) -> {'issues': [{'sev': 'err'|'warn'|'info', 'msg': str}], 'metrics': {...}}
"""
import os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import sheet, widthcheck, glosscheck, genderlint

NPC_FONT, NPC_WIDTH, NPC_LINES = 'flare12', 291, 5
PC_FONT, PC_WIDTH, PC_RECT = 'flare12', 400 - 2 * 6, 800 - 2 * 6

TOKEN = re.compile(r'@\w+@|%[-+0-9.]*[dsc]')
LATIN = re.compile(r'(?<![\w@])[A-Za-z]{3,}(?![\w@])')
ENGINE = re.compile(r'^\s*[A-Za-z]:')

_gloss = {'mtime': None, 'terms': [], 'any': None}


def glossary():
    p = os.path.join(ROOT, 'glossary', 'glossary.tsv')
    m = os.path.getmtime(p)
    if _gloss['mtime'] != m:
        terms = glosscheck.load_glossary()
        _gloss.update(terms=terms, mtime=m,
                      any=re.compile('|'.join(re.escape(t[0]) for t in terms)) if terms else None)
    return _gloss['terms']


def _en_layout(text, width):
    # widthcheck measures the original as the game would draw it in cp1251
    return widthcheck.layout(widthcheck.font(NPC_FONT),
                             text.encode('cp1252', 'replace').decode('cp1251', 'replace'), width)


def _text_issues(en, uk, label=''):
    out = []
    p = f'{label}: ' if label else ''
    if en.strip() and not uk.strip():
        return [{'sev': 'err', 'msg': p + 'не перекладено (порожньо)'}]
    bad = sheet.check_text(uk)
    if bad:
        out.append({'sev': 'err', 'msg': p + bad})
    if uk.strip() and uk.strip() == en.strip() and re.search('[A-Za-z]{3}', uk):
        out.append({'sev': 'err', 'msg': p + 'збігається з оригіналом (не перекладено?)'})
    else:
        lat = LATIN.findall(uk)
        if lat:
            out.append({'sev': 'warn', 'msg': p + 'латиниця: ' + ', '.join(sorted(set(lat))[:6])})
    te, tu = sorted(TOKEN.findall(en)), sorted(TOKEN.findall(uk))
    if te != tu:
        out.append({'sev': 'err', 'msg': p + f'плейсхолдери: EN {te or "—"} ≠ UK {tu or "—"}'})
    if en.count('[') != uk.count('['):
        out.append({'sev': 'warn', 'msg': p + f'[ремарок] EN {en.count("[")}, UK {uk.count("[")}'})
    low, seen = uk.lower(), set()
    terms = glossary()
    if not _gloss['any'] or not _gloss['any'].search(en):
        terms = []
    for term, ukform, rx, st in terms:
        if term in en and rx.search(en) and not any(all(s in low for s in alt) for alt in st):
            msg = p + f'глосарій: {term} → {ukform}'
            if msg not in seen:
                seen.add(msg)
                out.append({'sev': 'warn', 'msg': msg})
    return out


def hints(kind, en, uk, enf='', ukf='', gate=''):
    """kind: 'npc' | 'pc' | 'dumb'. For NPC, enf/ukf are the female-PC texts."""
    issues, metrics = [], {}
    if ENGINE.match(en):
        return {'issues': [{'sev': 'info', 'msg': 'текст підставляє рушій — не перекладається'}],
                'metrics': {}}
    if kind == 'npc':
        if en.strip():
            issues += _text_issues(en, uk, 'M' if enf.strip() else '')
        if enf.strip():
            issues += _text_issues(enf, ukf, 'F')
        fnt = widthcheck.font(NPC_FONT)
        for lab, e, u in (('M', en, uk), ('F', enf, ukf)):
            if not e.strip():
                continue
            ul, el = len(widthcheck.layout(fnt, u, NPC_WIDTH)), len(_en_layout(e, NPC_WIDTH))
            metrics['lines' + lab] = [ul, el]
            if ul > NPC_LINES and ul > el + 1:
                issues.append({'sev': 'info', 'msg': f'{lab}: {ul} рядків по 291 px, оригінал {el}'})
        m = genderlint.masc_pc.search(ukf)
        if m:
            issues.append({'sev': 'info', 'msg': f'чоловіча форма «{m.group(0)}» у жіночому тексті'})
        m = genderlint.fem_pc.search(uk)
        if m:
            issues.append({'sev': 'info', 'msg': f'жіноча форма «{m.group(0)}» у чоловічому тексті'})
        if enf.strip() and en.strip() and ukf.strip() == uk.strip() and \
                (genderlint.masc.search(uk) or genderlint.adj.search(uk)):
            issues.append({'sev': 'info', 'msg': 'M і F однакові, але в тексті є родові форми — перевір F'})
    else:
        issues += _text_issues(en, uk)
        fnt = widthcheck.font(PC_FONT)
        uw = widthcheck.one_line_width(fnt, uk)
        ew = widthcheck.one_line_width(fnt, en.encode('cp1252', 'replace').decode('cp1251', 'replace'))
        metrics['px'] = [uw, ew, PC_WIDTH]
        if uw > PC_RECT:
            issues.append({'sev': 'warn', 'msg': f'{uw} px — рушій обріже відповідь (>{PC_RECT} px)'})
        elif uw > PC_WIDTH and uw > ew:
            issues.append({'sev': 'info', 'msg': f'{uw} px — ширше за вікно ≈{PC_WIDTH} px (оригінал {ew})'})
        if not gate:
            hits = [k for k, rx in (('ч.р.', genderlint.masc), ('ж.р.', genderlint.fem), ('прикм.', genderlint.adj))
                    if rx.search(uk)]
            if hits:
                issues.append({'sev': 'warn', 'msg': 'спільна репліка гравця з родовою формою ('
                               + ', '.join(hits) + ') — має бути нейтральна'})
    if en.strip() and uk.strip():
        metrics['ratio'] = round(len(uk) / max(1, len(en)), 2)
    return {'issues': issues, 'metrics': metrics}


if __name__ == '__main__':
    import json
    print(json.dumps(hints(sys.argv[1], sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=1))


def mes_hints(rel, key, en, uk):
    """Hints for one .mes entry: text checks + the width rules that cover it."""
    if not en.strip() and not uk.strip():
        return {'issues': []}
    issues = _text_issues(en, uk) + widthcheck.fit_hints(rel, key, en, uk)
    return {'issues': issues}
