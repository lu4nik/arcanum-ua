#!/usr/bin/env python3
"""Context pack for another AI: the records to work on, the neighbouring
dialogue nodes, the glossary rows they touch, the style guide and the hard
constraints, plus the exact answer format. The answer is a sheet.py edit file,
so it is imported through the same validator (editor: diff, accept/reject).

build(rel, records, graph, scope, focus) -> str
  records: editor record views (num, kind, en, uk, enf, ukf, iq, gate, cond,
           target, effects, voice, hints)
  graph:   dlggraph.build(...) output
  scope:   'node' (NPC node `focus` + its responses; context = lines leading
           to it and the lines it leads to) | 'problems' (records with errors
           or warnings; context = their NPC lines) | 'all'
"""
import os, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = re.compile(r'^\s*[A-Za-z]:')


def glossary_rows():
    rows = []
    for line in open(os.path.join(ROOT, 'glossary', 'glossary.tsv'), encoding='utf-8'):
        c = line.rstrip('\n').split('\t')
        if len(c) >= 2 and c[0] and c[1] and c[0] != 'en':
            rows.append((c[0].strip(), c[1].strip(), c[2].strip() if len(c) > 2 else ''))
    return rows


def voice_row(rel):
    p = os.path.join(ROOT, 'docs', 'voices.tsv')
    if not os.path.exists(p):
        return None
    lines = open(p, encoding='utf-8').read().splitlines()
    head = lines[0].split('\t')
    for l in lines[1:]:
        c = l.split('\t')
        if c[0] == os.path.basename(rel):
            return dict(zip(head, c))
    return None


def _one(s):
    return (s or '').replace('\r\n', '\n').replace('\n', '\\n')


def _worst(r):
    sev = [i['sev'] for i in (r.get('hints') or {}).get('issues', [])]
    return 'err' if 'err' in sev else 'warn' if 'warn' in sev else ''


def _owner(graph, num):
    for n in graph['nodes']:
        if n['num'] == num or any(o['num'] == num for o in n['options']):
            return n
    return None


def _select(records, graph, scope, focus):
    """-> (work nums in file order, context nums)."""
    by = {r['num']: r for r in records}
    if scope == 'all':
        return [r['num'] for r in records], []
    if scope == 'problems':
        work = [r['num'] for r in records if _worst(r) and not ENGINE.match(r['en'])]
        ctx = []
        for k in work:
            n = _owner(graph, k)
            if n and n['num'] is not None and n['num'] not in work and n['num'] not in ctx:
                ctx.append(n['num'])
        return work, ctx
    node = _owner(graph, focus)
    if node is None:
        raise ValueError(f'нема запису #{focus}')
    work = ([node['num']] if node['num'] is not None else []) + [o['num'] for o in node['options']]
    ctx = []
    for e in graph['edges']:  # who leads here: the NPC line and the response used
        if e['dst'] == node['num'] and e['src'] is not None:
            for k in (e['src'], e['via']):
                if k is not None and k not in work and k not in ctx:
                    ctx.append(k)
    for o in node['options']:  # where the responses lead
        if o['target'] > 0 and o['target'] not in work and o['target'] not in ctx:
            ctx.append(o['target'])
    return work, [k for k in ctx if k in by]


def _rec(r, with_hints):
    if r['kind'] == 'npc':
        head = f"#{r['num']} NPC"
    else:
        iq = int(r['iq'])
        head = f"#{r['num']} {'DUMB' if iq < 0 else 'PC'} int={r['iq']}"
        if r.get('gate'):
            head += ' g=' + r['gate'] + (' (лише ГГ-жінка)' if r['gate'] == '0' else ' (лише ГГ-чоловік)')
        t = int(r['target'] or 0)
        head += f' ->{t}' if t > 0 else ' ->кінець' if t == 0 else f' ->кінець+скрипт'
        if r.get('cond'):
            head += f" [умова: {r['cond']}]"
    if r.get('effects'):
        head += f" [ефекти: {r['effects']}]"
    if ENGINE.match(r['en']):
        return head + f"\n  EN: {_one(r['en'])}   (підставляє рушій — НЕ чіпати)"
    out = [head]
    if r['en'].strip():
        out.append('  EN: ' + _one(r['en']))
    if r['kind'] == 'npc' and r.get('enf', '').strip() and r['enf'] != r['en']:
        out.append('  ENf: ' + _one(r['enf']))
    if r['en'].strip():
        out.append('  UK: ' + _one(r['uk']))
    if r['kind'] == 'npc' and r.get('enf', '').strip() and (r['ukf'] != r['uk'] or not r['en'].strip()):
        out.append('  UKf: ' + _one(r['ukf']))
    if with_hints:
        for i in (r.get('hints') or {}).get('issues', []):
            if i['sev'] in ('err', 'warn'):
                out.append(f"  ! {i['msg']}")
    return '\n'.join(out)


RULES = """\
- Відповідай ЛИШЕ блоком правок у форматі вище; без пояснень поза ним. Можна рядки-коментарі `// ...`.
- Пиши правку лише для записів, які справді змінюєш. Не повторюй незмінені.
- Редагуй ТІЛЬКИ записи з розділу «Записи до роботи». «Контекст» — лише для розуміння.
- Рядок NPC: `#N M: текст` — для ГГ-чоловіка, `#N F: текст` — для ГГ-жінки. Якщо в записі є UKf
  (жіночий текст відрізняється) — давай обидва, M і F. Якщо UKf немає, а українською форми мають різнитися
  (звертання, минулий час про ГГ) — дай і F.
- Репліка гравця (PC/DUMB): лише `#N: текст`. Число g= — фільтр статі, НЕ текст; не додавай F.
  Спільні репліки гравця (без g=) — гендерно нейтральні (без «я радий/рада», «зробив/зробила»).
- DUMB (int від'ємний) — мова недоумкуватого ГГ: «Моя не розуміти», інфінітиви, гендерно нейтрально.
- Плейсхолдери (@pcname@, %d тощо) зберігати точно; [ремарки в дужках] — зберігати як ремарки, перекладені.
- Лише символи кодування cp1251: без «…» (пиши три крапки), без фігурних дужок; «лапки-ялинки» можна.
- Перенос рядка в тексті — літерально `\\n`.
- Тексти на кшталт `E:`, `G:`, `b:` підставляє рушій — не перекладати.
- Не «покращуй» оригінал: зміст, жарти, грубість, стиль автора зберігати; вікторіанська епоха.
- Власні назви — строго за глосарієм нижче (відмінювати можна)."""


def build(rel, records, graph, scope='node', focus=None, style_text=None, gloss=None, voice=None, about=None):
    by = {r['num']: r for r in records}
    work, ctx = _select(records, graph, scope, focus)
    if not work:
        raise ValueError('нема записів для пакета (у цьому діалозі нема проблемних?)')
    texts = ' '.join((by[k]['en'] + ' ' + by[k].get('enf', '')) for k in work + ctx if k in by)
    gloss = glossary_rows() if gloss is None else gloss
    used = [g for g in gloss if re.search(r'(?<![A-Za-z])' + re.escape(g[0]) + r'(?![a-z])', texts,
                                          0 if g[0][:1].isupper() else re.I)]
    if style_text is None:
        style_text = open(os.path.join(ROOT, 'docs', 'style.md'), encoding='utf-8').read()
    voice = voice_row(rel) if voice is None else voice
    name = re.sub(r'^\d+', '', os.path.basename(rel)).replace('.dlg', '').replace('_', ' ')
    what = {'node': f'вузол #{focus} з відповідями', 'problems': 'записи з помилками/попередженнями перевірок',
            'all': 'весь діалог'}[scope]

    p = [f'# Завдання\n\nРедагування українського перекладу діалогу гри Arcanum: Of Steamworks and Magick Obscura '
         f'(1901, вікторіанське стімпанк-фентезі). Файл `{rel}`, персонаж: {name.strip()}. '
         f'Обсяг: {what}. Перевір переклад записів до роботи проти оригіналу (зміст, тон, звертання, '
         f'гендер, глосарій), виправ помилки й позначки «!» від автоматичних перевірок. Якщо запис добрий — не чіпай.']
    if about and any(about.values()):
        p.append('Про діалог (docs/dlg-index.tsv): ' + ' · '.join(
            v for v in (about.get('title'), about.get('who'), about.get('where'), about.get('context')) if v))
    if voice:
        bits = [f"звертання до ГГ: {voice.get('address')} (ти {voice.get('ty')} / ви {voice.get('vy')})"]
        for k, lab in (('dialect', 'частка говірки'), ('broken', 'частка ламаної мови'), ('colloq', 'розмовність')):
            try:
                if float(voice.get(k) or 0) > 0:
                    bits.append(f'{lab} {voice[k]}')
            except ValueError:
                pass
        p.append('Мовлення персонажа в оригіналі (docs/voices.tsv): ' + ', '.join(bits) + '.')
    p.append('# Формат відповіді (суворо)\n\n```\n@ ' + rel + '\n#14 M: текст для ГГ-чоловіка\n'
             '#14 F: текст для ГГ-жінки\n#15: репліка гравця\n```')
    p.append('# Обмеження\n\n' + RULES)
    p.append('# Позначення в записах\n\n`#N NPC` — репліка NPC; `PC int=5` — відповідь гравця, видна при інтелекті ≥5; '
             '`DUMB int=-4` — при інтелекті ≤4; `->N` — куди веде відповідь; `EN/ENf` — оригінал для ГГ-чоловіка/жінки; '
             '`UK/UKf` — поточний переклад; `!` — сигнал перевірки (може бути хибним).')
    if used:
        p.append('# Глосарій (терміни з цих записів)\n\n' + '\n'.join(
            f'- {en} → {uk}' + (f' — {note}' if note else '') for en, uk, note in used))
    if ctx:
        p.append('# Контекст (НЕ редагувати)\n\n' + '\n'.join(_rec(by[k], False) for k in ctx))
    p.append('# Записи до роботи\n\n' + '\n'.join(_rec(by[k], True) for k in work if k in by))
    p.append('# Стайлгайд проєкту (docs/style.md)\n\n' + style_text.strip())
    return '\n\n'.join(p) + '\n'
