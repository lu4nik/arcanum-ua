#!/usr/bin/env python3
"""Parsers for Arcanum text formats (.mes, .dlg). Lossless by design:
we never rewrite a file wholesale — we substitute brace-group contents
in the original bytes, so comments/whitespace survive verbatim.

.mes  — entries {key}{value}; // comments outside braces; braces never nest.
.dlg  — logical lines of 7 brace groups:
        {line#}{text}{female text}{intelligence}{test}{target}{effects}
        NPC lines: text+female filled. PC responses: female usually empty,
        intelligence may be negative (dumb dialogue).

Both decode as cp1252 (EN source) or cp1251 (UK translation).
"""
import re

GROUP = re.compile(rb'\{([^{}]*)\}')

def scan_groups(data: bytes):
    """All brace groups as (start, end, content-bytes), content excludes braces."""
    return [(m.start(), m.end(), m.group(1)) for m in GROUP.finditer(data)]

def parse_mes(data: bytes):
    """-> list of dicts {key, value, vstart, vend} (byte offsets of value content)."""
    groups = scan_groups(data)
    if len(groups) % 2 != 0:
        raise ValueError(f'odd brace-group count: {len(groups)}')
    entries = []
    for i in range(0, len(groups), 2):
        k, v = groups[i], groups[i + 1]
        entries.append({'key': k[2], 'value': v[2], 'vstart': v[0] + 1, 'vend': v[1] - 1})
    return entries

DLG_FIELDS = ('num', 'text', 'female', 'intelligence', 'test', 'target', 'effects')

def _records(data: bytes):
    """Split into records: groups collected until a newline at brace depth 0.
    Newlines INSIDE braces (multiline text) do not split. Tolerates records
    with fewer than 7 groups (a few vanilla files are sloppy)."""
    records, current = [], []
    pos = 0
    for m in GROUP.finditer(data):
        gap = data[pos:m.start()]
        if current and b'\n' in gap:
            records.append(current)
            current = []
        current.append((m.start(), m.end(), m.group(1)))
        pos = m.end()
    if current:
        records.append(current)
    return records

def parse_dlg(data: bytes):
    """-> list of dicts, one per logical record (normally 7 groups)."""
    lines = []
    for rec in _records(data):
        if len(rec) < 3 or len(rec) > 7:
            raise ValueError(f'record with {len(rec)} groups at offset {rec[0][0]}')
        d = {f: b'' for f in DLG_FIELDS}
        for f, g in zip(DLG_FIELDS, rec):
            d[f] = g[2]
        d['spans'] = [(x[0] + 1, x[1] - 1) for x in rec]
        lines.append(d)
    return lines

def substitute(data: bytes, replacements):
    """replacements: list of (start, end, new_bytes) in original offsets."""
    out, pos = [], 0
    for start, end, new in sorted(replacements):
        if start < pos:
            raise ValueError('overlapping replacements')
        out.append(data[pos:start])
        out.append(new)
        pos = end
    out.append(data[pos:])
    return b''.join(out)

def validate_pair(src: bytes, dst: bytes, kind: str):
    """Structural QA: translation must mirror source exactly except text fields.
    Returns list of problem strings (empty = OK)."""
    problems = []
    try:
        if kind == 'mes':
            a, b = parse_mes(src), parse_mes(dst)
            if len(a) != len(b):
                return [f'entry count {len(a)} != {len(b)}']
            for ea, eb in zip(a, b):
                if ea['key'].strip() != eb['key'].strip():
                    problems.append(f'key mismatch: {ea["key"]!r} vs {eb["key"]!r}')
        elif kind == 'dlg':
            a, b = parse_dlg(src), parse_dlg(dst)
            if len(a) != len(b):
                return [f'line count {len(a)} != {len(b)}']
            for la, lb in zip(a, b):
                for f in ('num', 'intelligence', 'test', 'target', 'effects'):
                    if la[f].strip() != lb[f].strip():
                        problems.append(f'line {la["num"].decode(errors="replace")}: field {f} changed')
                if la['intelligence'].strip():
                    # PC line: field 2 is a GENDER GATE number (0/1/empty), not text —
                    # it must stay byte-identical (see CLAUDE.md / dialog.c dialog_parse_entry)
                    if la['female'].strip() != lb['female'].strip():
                        problems.append(f'line {la["num"].decode(errors="replace")}: gender gate changed')
                    if bool(la['text'].strip()) != bool(lb['text'].strip()):
                        problems.append(f'line {la["num"].decode(errors="replace")}: text emptiness changed')
                else:
                    # NPC line: field 2 is the female-PC text
                    for f in ('text', 'female'):
                        if bool(la[f].strip()) != bool(lb[f].strip()):
                            problems.append(f'line {la["num"].decode(errors="replace")}: {f} emptiness changed')
        else:
            problems.append(f'unknown kind {kind}')
    except ValueError as e:
        problems.append(str(e))
    return problems
