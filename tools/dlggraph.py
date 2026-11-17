#!/usr/bin/env python3
"""Dialogue graph of an Arcanum .dlg, following the engine's rules
(arcanum-ce src/game/dialog.c):

  * A record with an EMPTY intelligence field is an NPC line; with a non-zero one
    it is a player (PC) response. Negative intelligence = dumb-PC line.
  * The responses offered after NPC line N are the records that FOLLOW N in the
    file while their intelligence is non-empty (sub_414F50; at most 5 are shown
    after gender/IQ/condition filtering).
  * NPC line: field 2 = text for a female PC, field 5 = speech (voice) id.
    PC line:  field 2 = gender gate (0 female, 1 male, empty both),
              field 5 = conditions, field 6 = response value:
              >0 go to NPC line N; 0/empty = end of dialogue;
              <0 = end of dialogue and run the NPC's SCRIPT from script line |N|
              (dialog_ui.c case 2) — not a dialogue line, so not an edge here.
  * Effect "fl N" in field 7: the NPC says line N as floating text and the
    dialogue ends (DIALOG_ACTION_FL -> state 4).
  * Texts like "a:", "b:", "g:..." are filled in by the engine (barter, generic
    replies...), not by the dialogue author.

Pure model: takes records as parsed by arcfmt.parse_dlg (any encoding), returns
plain dicts. No UI, no file paths.
"""
import re

FL = re.compile(r'\bfl\s+(-?\d+)', re.I)
ENGINE = re.compile(r'^\s*[A-Za-z]:')


def _s(b, enc):
    return b.decode(enc, 'replace') if isinstance(b, bytes) else (b or '')


def _int(s):
    s = s.strip()
    try:
        return int(s)
    except ValueError:
        return None


def build(records, enc='utf-8'):
    """records: arcfmt.parse_dlg output. -> {'nodes': [...], 'edges': [...], 'roots': [...]}.
    Node: {num, text, female, voice, effects, options: [option...], blank}
    Option: {num, text, iq, gate, cond, target, effects, engine}
    Option['script'] = script line for negative targets (else None).
    Edge: {src (NPC num), via (PC num or None), dst, kind: go|fl, missing}."""
    nodes, edges = [], []
    current = None
    for r in records:
        num = _int(_s(r['num'], 'latin1'))
        intel = _s(r['intelligence'], 'latin1').strip()
        text = _s(r['text'], enc)
        effects = _s(r['effects'], 'latin1').strip()
        if not intel:
            blank = not any(_s(r[f], 'latin1').strip() for f in ('text', 'female', 'test', 'target', 'effects'))
            if blank:
                current = None
                continue
            current = {'num': num, 'text': text, 'female': _s(r['female'], enc),
                       'voice': _s(r['test'], 'latin1').strip(), 'effects': effects,
                       'engine': bool(ENGINE.match(text)), 'options': []}
            nodes.append(current)
            for m in FL.finditer(effects):
                edges.append({'src': num, 'via': None, 'dst': abs(int(m.group(1))), 'kind': 'fl'})
            continue
        tgt = _int(_s(r['target'], 'latin1')) or 0
        opt = {'num': num, 'text': text, 'iq': _int(intel), 'gate': _s(r['female'], 'latin1').strip(),
               'cond': _s(r['test'], 'latin1').strip(), 'target': tgt, 'effects': effects,
               'engine': bool(ENGINE.match(text)), 'script': -tgt if tgt < 0 else None}
        if current is None:
            # orphan PC line (never offered by the engine) — keep it visible
            current = {'num': None, 'text': '', 'female': '', 'voice': '', 'effects': '',
                       'engine': False, 'options': [], 'orphan': True}
            nodes.append(current)
        current['options'].append(opt)
        src = current['num']
        if tgt > 0:
            edges.append({'src': src, 'via': num, 'dst': tgt, 'kind': 'go'})
        for m in FL.finditer(effects):
            edges.append({'src': src, 'via': num, 'dst': abs(int(m.group(1))), 'kind': 'fl'})
    targeted = {e['dst'] for e in edges}
    roots = [n['num'] for n in nodes if n['num'] is not None and n['num'] not in targeted]
    known = {n['num'] for n in nodes}
    for e in edges:
        e['missing'] = e['dst'] not in known
    return {'nodes': nodes, 'edges': edges, 'roots': roots}


if __name__ == '__main__':
    import sys, os, json
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import arcfmt
    g = build(arcfmt.parse_dlg(open(sys.argv[1], 'rb').read()),
              'cp1252' if '/source/' in os.path.abspath(sys.argv[1]) else 'utf-8')
    print(f"{len(g['nodes'])} NPC nodes, {len(g['edges'])} edges, roots: {g['roots']}")
    for e in g['edges']:
        if e['missing']:
            print('  dangling', e)
