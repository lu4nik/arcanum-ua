#!/usr/bin/env python3
"""Human-readable dialogue conditions (.dlg field 5) and effects (field 7).

Semantics transcribed from arcanum-ce src/game/dialog.c: sub_4150D0
(conditions; a reply is shown only when every condition holds) and
sub_416C10's action switch (effects, applied when the reply is chosen).
A code is two letters followed by numbers: "ps 5", "qu 1023 2", "re +5".

Names come from our own Ukrainian mes files (quests, rumours, items, areas,
reputations, skills, races) and from the original editor notes in
source/semes (global flags/vars, PC vars), which are English developer
comments such as "1 = Archibald hooks up with Gladys".

explain(text, 'cond'|'act') -> [{'code', 'raw', 'text', 'detail'}]
"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_mes = {}


def mes(rel, src='uk'):
    key = (src, rel)
    if key not in _mes:
        p = os.path.join(ROOT, src, rel)
        d = {}
        if os.path.exists(p):
            raw = open(p, 'rb').read()
            txt = raw.decode('utf-8') if src == 'uk' else raw.decode('cp1252', 'replace')
            txt = re.sub(r'//[^\n]*', '', txt)
            for k, v in re.findall(r'\{(\d+)\}\s*\{([^}]*)\}', txt):
                d[int(k)] = v.strip()
        _mes[key] = d
    return _mes[key]


def short(s, n=70):
    s = ' '.join(s.split())
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def q(s):
    return '«%s»' % short(s, 90) if s else ''


QUEST_STATES = ['невідомий', 'згаданий', 'прийнятий', 'досягнутий (ще не здано)',
                'виконаний', 'виконаний іншим', 'провалений']
TRAINING = ['без навчання', 'учень', 'експерт', 'майстер']


def skill(n):
    return mes('mes/skill.mes').get(n, 'навичка %d' % n)


def stat(n):
    return mes('mes/stat.mes').get(n, 'стат %d' % n)


def race(n):  # dialog uses race + 1
    return mes('mes/stat.mes').get(30 + n - 1, 'раса %d' % n)


def quest(n):
    return mes('mes/gamequestlog.mes').get(n, '')


_onames = None


def _oname_to_desc():
    """Internal object name id (oname.mes, what 'in'/'pa' test) -> description.mes id,
    from the prototypes in the player's game copy; {} without one. Cached."""
    global _onames
    if _onames is not None:
        return _onames
    import json
    cache = os.path.expanduser('~/.cache/arcanum-ua/oname-desc.json')
    try:
        _onames = {int(k): v for k, v in json.load(open(cache)).items()}
        return _onames
    except (OSError, ValueError):
        pass
    _onames = {}
    try:
        import npcart
        g = npcart.Game()
        # unique items/critters carry their own name on the map object (.mob),
        # generic ones on the prototype; a mob's missing fields come from its proto
        protos = {}
        for name in sorted(g.files, key=lambda n: not n.startswith('proto/')):
            if not name.endswith(('.pro', '.mob')):
                continue
            try:
                ip, pid, _, f = npcart.parse_obj(g.read(name))
            except Exception:
                continue
            if ip:
                protos[pid] = f
            base = protos.get(pid, {}) if not ip else {}
            nm = f.get('name') if f.get('name') is not None else base.get('name')
            ds = f.get('description') if f.get('description') is not None else base.get('description')
            if nm and ds:
                _onames.setdefault(nm, ds)
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        json.dump({str(k): v for k, v in _onames.items()}, open(cache, 'w'))
    except Exception:
        pass
    return _onames


def item(n):
    """Ukrainian name of an object by its internal name id; English editor name as a fallback."""
    en = re.sub(r'^\d+\s*', '', mes('oemes/oname.mes', 'source').get(n, ''))
    d = _oname_to_desc().get(n)
    uk = mes('mes/description.mes').get(d, '') if d else ''
    if not uk:
        uk = glossary().get(en.lower(), '')
    if uk and en and uk.lower() != en.lower():
        return '%s (%s)' % (uk, en)
    return uk or en


_gloss = None


def glossary():
    global _gloss
    if _gloss is None:
        _gloss = {}
        p = os.path.join(ROOT, 'glossary', 'glossary.tsv')
        if os.path.exists(p):
            for line in open(p, encoding='utf-8'):
                c = line.rstrip('\n').split('\t')
                if len(c) >= 2 and c[0] and c[1]:
                    _gloss.setdefault(c[0].lower(), c[1])
    return _gloss


def rumor(n):
    return mes('mes/game_rd_npc_m2m.mes').get(20 * n + 1, '')


def area(n):
    v = mes('mes/gamearea.mes').get(n, '')
    parts = v.split('/')
    return parts[1].strip() if len(parts) > 1 else ''


def rep(n):
    return mes('mes/gamereplog.mes').get(n, '')


def college(n):
    return mes('mes/spell.mes').get(500 + n, 'школа %d' % n)


def gflag(n):
    return mes('semes/globalflags.mes', 'source').get(n, '')


def gvar(n):
    return mes('semes/globalvars.mes', 'source').get(n, '')


def pcvar(n):
    return mes('semes/pcvars.mes', 'source').get(n, '')


def story(n):
    return mes('mes/storystate.mes').get(n, '')


def cmp(name, v):
    """'name ≥ v' for v >= 0, 'name ≤ |v|' for v < 0 (the engine's convention)."""
    return '%s ≥ %d' % (name, v) if v >= 0 else '%s ≤ %d' % (name, -v)


def _cond(c, a, b, sign):
    """-> (text, detail)."""
    if c == 'ps': return cmp('Переконання ГГ', a), 'базовий рівень навички'
    if c == 'ha': return cmp('Торгівля ГГ', a), 'базовий рівень навички'
    if c == 'ch': return cmp(stat(7) + ' ГГ', a), ''
    if c == 'pe': return cmp(stat(5) + ' ГГ', a), ''
    if c == 'al': return cmp(stat(19) + ' ГГ', a), 'добрий > 0, злий < 0'
    if c == 'na':
        return ('%s ГГ ≤ %d' % (stat(19), a) if a < 0 else '%s ГГ ≥ %d' % (stat(19), -a)), 'світогляд, від’ємна межа'
    if c == 'ma': return cmp('магічна схильність ГГ', a), 'шкала магія/технологія, магія > 0'
    if c == 'ta': return cmp('технологічна схильність ГГ', a), 'шкала магія/технологія, технологія > 0'
    if c == 'le': return cmp('рівень ГГ', a), ''
    if c == 're': return cmp('ставлення NPC до ГГ', a), 'реакція: 50 — байдуже, більше — прихильніше'
    if c == '$$': return cmp('золото ГГ і загону', a), ''
    if c == 'in':
        return ('у NPC є предмет %s' % q(item(-a)) if a < 0 else 'у ГГ або загону є предмет %s' % q(item(a))), 'предмет %d' % abs(a)
    if c == 'ni':
        return ('у NPC немає предмета %s' % q(item(-a)) if a < 0 else 'у ГГ і загону немає предмета %s' % q(item(a))), 'предмет %d' % abs(a)
    if c == 'gf': return 'глобальний прапорець %d = %d' % (a, b), gflag(a)
    if c == 'gv': return 'глобальна змінна %d = %d' % (a, b), gvar(a)
    if c == 'pf': return 'прапорець ГГ %d = %d' % (a, b), pcvar(a)
    if c == 'pv': return 'змінна ГГ %d = %d' % (a, b), pcvar(a)
    if c == 'lf': return 'прапорець цього NPC %d = %d' % (a, b), 'локальний прапорець діалогового скрипта; ставиться ефектом lf'
    if c == 'lc': return 'лічильник цього NPC %d = %d' % (a, b), 'локальний лічильник діалогового скрипта; ставиться ефектом lc'
    st = QUEST_STATES[b] if 0 <= b < len(QUEST_STATES) else str(b)
    if c == 'qu': return 'квест %d: %s' % (a, st), quest(a)
    if c == 'qa': return 'квест %d: не раніше ніж «%s»' % (a, st), quest(a)
    if c == 'qb': return 'квест %d: не далі ніж «%s»' % (a, st), quest(a)
    if c == 'ru':
        return ('ГГ ще не чув чутку %d' % -a if a < 0 else 'ГГ чув чутку %d' % a), rumor(abs(a))
    if c == 'rq':
        return ('чутка %d ще актуальна' % -a if a < 0 else 'чутку %d уже «погашено»' % a), rumor(abs(a))
    if c == 'fo': return ('NPC іде з ГГ (у загоні)' if a == 0 else 'NPC не в загоні ГГ'), ''
    if c == 'me': return ('NPC бачить ГГ уперше' if a == 0 else 'NPC уже зустрічав ГГ'), 'перша/повторна зустріч'
    if c == 'ra': return ('ГГ — %s' % race(a) if a > 0 else 'ГГ — не %s' % race(-a)), ''
    if c == 'pa':
        n = item(abs(a)) or str(abs(a))
        return ('у загоні немає: %s' % n if a < 0 else 'у загоні є: %s' % n), 'супутник за назвою'
    if c == 'ss': return cmp('сюжетний етап', a), story(abs(a))
    if c == 'wa': return ('NPC чекає на місці (відпущений)' if a == 1 else 'NPC не чекає на місці'), ''
    if c == 'wt': return ('NPC покинутий ГГ' if a == 1 else 'NPC не покинутий ГГ'), 'jilted: ГГ кинув супутника'
    if c == 'ar': return ('ГГ знає місце %s' % q(area(a)) if a > 0 else 'ГГ не знає місця %s' % q(area(-a))), 'місце %d' % abs(a)
    if c == 'ia': return ('ГГ зараз у місці %s' % q(area(a)) if a > 0 else 'ГГ зараз не в місці %s' % q(area(-a))), 'місце %d' % abs(a)
    if c == 'rp': return ('ГГ має репутацію %s' % q(rep(a)) if a > 0 else 'ГГ не має репутації %s' % q(rep(-a))), 'репутація %d' % abs(a)
    if c == 'sk': return cmp('%s ГГ' % skill(a), b), 'рівень навички'
    if c == 'tr':
        t = TRAINING[abs(b)] if abs(b) < len(TRAINING) else str(b)
        return ('%s: навчання не вище «%s»' % (skill(a), t) if b < 0 else '%s: навчання щонайменше «%s»' % (skill(a), t)), ''
    if c == 'sc': return cmp('магія школи «%s»' % college(a), b), 'скільки заклять школи знає ГГ'
    return None, ''


def _act(c, a, b, sign):
    if c == '$$': return ('ГГ отримує %d золота' % a if a >= 0 else 'ГГ платить NPC %d золота' % -a), ''
    if c in ('re', 'al'):
        what = 'ставлення NPC до ГГ' if c == 're' else '%s ГГ' % stat(19)
        if sign in '+-': return '%s %+d' % (what, a), ''
        if sign == '>': return '%s піднімається щонайменше до %d' % (what, a), ''
        if sign == '<': return '%s опускається щонайбільше до %d' % (what, a), ''
        return '%s = %d' % (what, a), ''
    st = QUEST_STATES[b] if 0 <= b < len(QUEST_STATES) else str(b)
    if c == 'qu': return 'квест %d → %s' % (a, st), quest(a)
    if c == 'fl': return 'NPC каже рядок #%d над головою, розмова закінчується' % a, ''
    if c == 'co': return 'NPC нападає на ГГ', ''
    if c == 'gf': return 'глобальний прапорець %d := %d' % (a, b), gflag(a)
    if c == 'gv': return 'глобальна змінна %d := %d' % (a, b), gvar(a)
    if c == 'pf': return 'прапорець ГГ %d := %d' % (a, b), pcvar(a)
    if c == 'pv': return 'змінна ГГ %d := %d' % (a, b), pcvar(a)
    if c == 'lf': return 'прапорець цього NPC %d := %d' % (a, b), 'перевіряється умовою lf'
    if c == 'lc': return 'лічильник цього NPC %d := %d' % (a, b), 'перевіряється умовою lc'
    if c == 'mm': return 'на мапі з’являється місце %s' % q(area(a)), 'місце %d' % a
    if c == 'in':
        return ('NPC дає ГГ предмет %s' % q(item(-a)) if a < 0 else 'ГГ віддає NPC предмет %s' % q(item(a))), 'предмет %d' % abs(a)
    if c == 'tr':
        t = TRAINING[b] if 0 <= b < len(TRAINING) else str(b)
        return '%s: навчання → «%s»' % (skill(a), t), ''
    if c == 'et': return 'навчання %s на експерта (якщо ГГ готовий; інакше NPC відмовляє)' % skill(a), 'далі — рядок #%d' % b
    if c == 'ru': return 'ГГ дізнається чутку %d' % a, rumor(a)
    if c == 'rq': return 'чутку %d «погашено»' % a, rumor(a)
    if c == 'jo': return 'NPC приєднується до загону (або відмовляє)', ('далі — рядок #%d' % b) if b else ''
    if c == 'uw': return 'NPC знову йде з ГГ (або відмовляє)', ('далі — рядок #%d' % b) if b else ''
    if c == 'wa': return 'NPC лишається чекати тут', ''
    if c == 'lv': return 'NPC іде із загону', ''
    if c == 'sc': return 'загін тримається ближче', ''
    if c == 'so': return 'загін розходиться', ''
    if c == 'ss': return 'сюжетний етап := %d' % a, story(a)
    if c == 'xp': return 'ГГ отримує досвід за квест %d' % a, quest(a)
    if c == 'nk': return 'NPC помирає', ''
    if c == 'rp': return ('ГГ отримує репутацію %s' % q(rep(a)) if a > 0 else 'ГГ втрачає репутацію %s' % q(rep(-a))), 'репутація %d' % abs(a)
    if c == 'np': return 'у газеті з’явиться стаття %d' % a, ''
    if c == 'ce': return 'відкриває характеристики NPC', 'перегляд супутника'
    if c == 'su': return 'відкриває креслення NPC', 'вікно схем (технологія)'
    if c == 'ii': return 'NPC визначає предмети ГГ', 'ідентифікація'
    if c == 'ri': return 'NPC лагодить предмети ГГ', 'ремонт'
    if c == 'fp': return 'ГГ отримує очко долі', ''
    if c == 'or': return 'походження NPC := %d' % a, ''
    return None, ''


CODE = re.compile(r'([A-Za-z$]{2})\s*([+\-<>]?)\s*(-?\d+)?(?:\s+(-?\d+))?')


def explain(text, kind='cond'):
    out = []
    for m in CODE.finditer(text or ''):
        c = m.group(1).lower()
        sign = m.group(2) or ''
        a = int(m.group(3)) if m.group(3) else 0
        if sign == '-':
            a = -a
        b = int(m.group(4)) if m.group(4) else 0
        fn = _cond if kind == 'cond' else _act
        txt, det = fn(c, a, b, sign)
        out.append({'code': c, 'raw': m.group(0).strip(),
                    'text': txt or 'невідомий код «%s» — рушій його пропускає' % m.group(0).strip(),
                    'detail': det or '', 'unknown': not txt})
    return out


if __name__ == '__main__':
    import sys
    for t in sys.argv[1:] or ['ps 5 me 0', 'qu 1023 2 ru 2015', 'in -6001']:
        print(t, '->', explain(t, 'cond'))
    for t in ['re +5 qu 1023 4 $$ -100', 'al -2 fl 30', 'jo 0 40']:
        print(t, '->', explain(t, 'act'))
