#!/usr/bin/env python3
"""Who speaks each dialogue, and a picture of them — from the player's copy.

Nothing from the game is stored in the repo: the index and the pictures are
built on demand from the installed game (default /Applications/Arcanum) and
cached under ~/.cache/arcanum-ua/.

Link dialogue -> NPC: a critter's OBJ_F_SCRIPTS_IDX[SAP_DIALOG=9].num is the
script number, and dlg/NNNNN*.dlg shares it. Critters come from map mobiles
(modules/Arcanum.dat maps/*/*.mob, instance objects: only overridden fields,
the rest from the prototype) and from prototypes (spawned critters).

Picture: the companion portrait (OBJ_F_CRITTER_PORTRAIT -> portrait/
gameport.mes -> portrait/NAME.bmp) when there is one, otherwise frame 0 of
the standing sprite (OBJ_F_AID -> art path per arcanum-ce src/game/name.c
name_art_id_to_path, art id bit layout per first_party/tig/src/art.c).

CLI:
  python3 tools/npcart.py                 # summary: dialogues matched
  python3 tools/npcart.py 01687 out.png   # picture for one dialogue
"""
import os, sys, struct, json, zlib, re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tdat, proparse as pp

GAME = os.environ.get('ARCANUM_GAME', '/Applications/Arcanum')
CACHE = os.path.expanduser('~/.cache/arcanum-ua')
SAP_DIALOG = 9
INDEX_VERSION = 1


# ---------------------------------------------------------------- game files

class Game:
    """Effective file tree: base .dat (1..5), module .dat, loose folders."""

    def __init__(self, root=GAME):
        self.root = root
        self.files = {}
        dats = ['arcanum1.dat', 'arcanum2.dat', 'arcanum3.dat', 'Arcanum4.dat',
                'Arcanum5.dat', 'modules/Arcanum.dat']
        for n in dats:
            p = os.path.join(root, n)
            if os.path.exists(p):
                for e in tdat.read_entries(p):
                    if e[2] > 0:
                        self.files[e[0].lower()] = (p, e)
        for loose in ('data', 'modules/Arcanum'):
            base = os.path.join(root, loose)
            for sub in ('proto', 'art', 'portrait'):
                d = os.path.join(base, sub)
                for dp, _, fs in os.walk(d):
                    for f in fs:
                        full = os.path.join(dp, f)
                        rel = os.path.relpath(full, base).replace(os.sep, '/').lower()
                        self.files[rel] = (None, full)

    def has(self, name):
        return name.lower() in self.files

    def read(self, name):
        dat, e = self.files[name.lower()]
        if dat is None:
            with open(e, 'rb') as fh:
                return fh.read()
        return tdat.read_file(dat, e)

    def mes(self, name):
        if not self.has(name):
            return {}
        txt = self.read(name).decode('cp1252', 'replace')
        txt = re.sub(r'//[^\n]*', '', txt)
        return {int(k): v for k, v in re.findall(r'\{(\d+)\}\s*\{([^}]*)\}', txt)}


# ------------------------------------------------------------ object parsing

def _array(data, pos):
    """SizeableArray with keys; 12-byte elements (scripts) kept as tuples."""
    es, cnt, _ = struct.unpack_from('<iii', data, pos)
    pos += 12
    raw = data[pos:pos + es * cnt]
    pos += es * cnt
    (nw,) = struct.unpack_from('<i', data, pos)
    pos += 4
    words = struct.unpack_from('<%dI' % nw, data, pos)
    pos += 4 * nw
    keys = [w * 32 + b for w, x in enumerate(words) for b in range(32) if x >> b & 1]
    out = {}
    fmt = {4: '<i', 8: '<q', 12: '<iii'}.get(es)
    if fmt:
        for r, k in enumerate(keys[:cnt]):
            v = struct.unpack_from(fmt, raw, r * es)
            out[k] = v if es == 12 else v[0]
    return out, pos


def _field(data, pos, ft, presence_for_i32=False):
    if ft == pp.I32:
        return struct.unpack_from('<i', data, pos)[0], pos + 4
    present = data[pos]
    pos += 1
    if not present:
        return None, pos
    if ft == pp.I64:
        return struct.unpack_from('<q', data, pos)[0], pos + 8
    if ft == pp.HDL:
        return data[pos:pos + 24], pos + 24
    if ft == pp.STR:
        (n,) = struct.unpack_from('<i', data, pos)
        return data[pos + 4:pos + 4 + n].decode('cp1252', 'replace'), pos + 4 + n + 1
    return _array(data, pos)


def parse_obj(data):
    """.pro or .mob -> (is_proto, proto_id, obj_type, fields).

    Prototype: every field (obj_proto_read_file). Instance: version,
    prototype oid, oid, type, int16 num_fields, 'overridden' bitmap, then
    only the fields whose bit is set (obj_inst_read_file; each section starts
    on a fresh 32-bit word, sub_40A8A0).
    """
    (ver,) = struct.unpack_from('<i', data, 0)
    if ver != 119:
        raise ValueError('bad version %d' % ver)
    is_proto = struct.unpack_from('<h', data, 4)[0] == -1
    if is_proto:
        proto_id = struct.unpack_from('<i', data, 36)[0]
    else:
        proto_id = struct.unpack_from('<i', data, 12)[0]
    (typ,) = struct.unpack_from('<i', data, 52)
    secs = pp.TYPE_SECTIONS[typ]
    nw = pp._bitmap_words(secs)
    pos = 56 if is_proto else 58
    words = struct.unpack_from('<%dI' % nw, data, pos)
    pos += 4 * nw
    fields, w0 = {}, 0
    for s in secs:
        for i, (name, ft) in enumerate(s):
            if is_proto or words[w0 + i // 32] >> (i % 32) & 1:
                fields[name], pos = _field(data, pos, ft)
        w0 += (len(s) + 31) // 32
    if pos != len(data):
        raise ValueError('trailing bytes %d of %d' % (pos, len(data)))
    return is_proto, proto_id, typ, fields


# --------------------------------------------------------------- the index

def _dialog_script(f):
    s = (f.get('scripts_idx') or {}).get(SAP_DIALOG)
    return s[2] if s and s[2] > 0 else None


def build_index(game):
    """-> {dlg_num: [npc, ...]}; npc = dict(map, proto, name, aid, portrait, count)."""
    protos = {}
    for name in game.files:
        if name.startswith('proto/') and name.endswith('.pro'):
            try:
                ip, pid, typ, f = parse_obj(game.read(name))
            except Exception:
                continue
            if typ in (pp.OBJ_TYPE_PC, pp.OBJ_TYPE_NPC):
                protos[pid] = f
    desc = game.mes('mes/description.mes')
    found = {}

    def add(num, where, pid, f, base):
        g = lambda k: f[k] if f.get(k) is not None else base.get(k)
        aid = g('aid') if g('aid') not in (None, -1) else g('current_aid')
        key = (num, pid, aid, g('critter_portrait'), g('description'))
        n = found.get(key)
        if n:
            n['count'] += 1
            if where and where not in n['maps']:
                n['maps'].append(where)
            return
        found[key] = {'proto': pid, 'aid': (aid or 0) & 0xFFFFFFFF,
                      'portrait': g('critter_portrait') or 0,
                      'name': desc.get(g('description') or -1, ''),
                      'maps': [where] if where else [], 'count': 1}

    for name in game.files:
        if not (name.startswith('maps/') and name.endswith('.mob')):
            continue
        try:
            ip, pid, typ, f = parse_obj(game.read(name))
        except Exception:
            continue
        if typ != pp.OBJ_TYPE_NPC:
            continue
        base = protos.get(pid, {})
        num = _dialog_script(f) if f.get('scripts_idx') is not None else _dialog_script(base)
        if num:
            add(num, name.split('/')[1], pid, f, base)
    seen = {k[0] for k in found}
    for pid, f in protos.items():
        num = _dialog_script(f)
        if num and num not in seen:
            add(num, None, pid, {}, f)
    out = {}
    for (num, *_), n in found.items():
        out.setdefault(num, []).append(n)
    for v in out.values():
        v.sort(key=lambda n: (-bool(n['portrait']), -n['count']))
    return out


def load_index(game_root=GAME):
    """Cached index keyed by the game files' mtimes."""
    stamp = []
    for n in ('modules/Arcanum.dat', 'arcanum1.dat', 'Arcanum5.dat', 'data/proto'):
        p = os.path.join(game_root, n)
        stamp.append(int(os.path.getmtime(p)) if os.path.exists(p) else 0)
    cache = os.path.join(CACHE, 'npc-index.json')
    try:
        with open(cache) as fh:
            c = json.load(fh)
        if c.get('v') == INDEX_VERSION and c.get('stamp') == stamp and c.get('root') == game_root:
            return {int(k): v for k, v in c['index'].items()}
    except (OSError, ValueError):
        pass
    idx = build_index(Game(game_root))
    os.makedirs(CACHE, exist_ok=True)
    with open(cache, 'w') as fh:
        json.dump({'v': INDEX_VERSION, 'stamp': stamp, 'root': game_root,
                   'index': {str(k): v for k, v in idx.items()}}, fh)
    return idx


# ------------------------------------------------------------- art -> path

BODY = ['HM', 'DF', 'GH', 'HG', 'EF']
ARMOR = ['UW', 'V1', 'LA', 'CM', 'PM', 'RB', 'PC', 'BN', 'CD']
GENDER = 'FMX'
SHIELD = 'XS'
WEAPON = 'ABCDEFGHIJKXYNZ'
T_CRITTER, T_MONSTER, T_UNIQUE = 2, 12, 13


def art_paths(aid, game):
    """Candidate .art paths for the standing pose of a critter art id."""
    t = aid >> 28
    shield = aid >> 19 & 1
    weapon = aid & 0xF
    if weapon == 7 and shield:
        weapon = 3
    out = []
    if t == T_CRITTER:
        armor, body, gender = aid >> 20 & 0xF, aid >> 24 & 7, aid >> 27 & 1
        if armor >= len(ARMOR) or body >= len(BODY):
            return []
        if body == 4 and gender == 0:
            body = 0
        if armor in (4, 6):
            body = {4: 0, 2: 1}.get(body, body)
            g = 'X'
        else:
            g = GENDER[gender]
        b = BODY[body]
        for w in (weapon, 0):
            out.append('art/critter/%s%s/%s%s%s%s%sa.art'
                       % (b, g, b, g, ARMOR[armor], SHIELD[shield], WEAPON[w]))
    elif t == T_MONSTER:
        name = game.mes('art/monster/monster.mes').get(aid >> 23 & 0x1F)
        if name:
            armor = aid >> 20 & 7
            for w in (weapon, 0):
                out.append('art/monster/%s/%s%s%s%sa.art'
                           % (name, name, ARMOR[armor], SHIELD[shield], WEAPON[w]))
    elif t == T_UNIQUE:
        name = game.mes('art/unique_npc/unique_npc.mes').get(aid >> 20 & 0xFF)
        if name:
            for w in (weapon, 0):
                out.append('art/unique_npc/%s/%s%s%sa.art'
                           % (name, name, SHIELD[shield], WEAPON[w]))
    return out


# ------------------------------------------------------ art / bmp -> pixels

def art_frame(data, palette=0, rotation=4):
    """Frame 0 of one rotation -> (w, h, rgba bytes)."""
    flags = struct.unpack_from('<i', data, 0)[0]
    markers = struct.unpack_from('<4i', data, 12)
    (nframes,) = struct.unpack_from('<i', data, 32)
    off = 132
    pals = []
    for m in markers:
        if m:
            pals.append(struct.unpack_from('<256I', data, off))
            off += 1024
    pal = pals[palette] if palette < len(pals) else pals[0]
    nrot = 1 if flags & 1 else 8
    tbl = []
    for _ in range(nrot):
        tbl.append([struct.unpack_from('<7i', data, off + 28 * i) for i in range(nframes)])
        off += 28 * nframes
    rotation = 0 if nrot == 1 else rotation
    for r in range(nrot):
        for fi, (w, h, size, *_r) in enumerate(tbl[r]):
            if r == rotation and fi == 0:
                px = _unrle(data, off, size, w * h)
                rgba = bytearray()
                for c in px:
                    if c == 0:
                        rgba += b'\0\0\0\0'
                    else:
                        v = pal[c]
                        rgba += bytes((v >> 16 & 255, v >> 8 & 255, v & 255, 255))
                return w, h, bytes(rgba)
            off += size
    raise ValueError('no frame')


def _unrle(data, off, size, n):
    if size == n:
        return data[off:off + n]
    out, cnt = bytearray(), 0
    while cnt < size:
        c = data[off]
        off += 1
        ln = c & 0x7F
        if c & 0x80:
            out += data[off:off + ln]
            off += ln
            cnt += 1 + ln
        else:
            out += bytes([data[off]]) * ln
            off += 1
            cnt += 2
    return out


def bmp_pixels(data):
    """8/24-bit uncompressed BMP -> (w, h, rgba)."""
    off = struct.unpack_from('<I', data, 10)[0]
    w, h = struct.unpack_from('<ii', data, 18)
    bpp = struct.unpack_from('<H', data, 28)[0]
    flip = h > 0
    h = abs(h)
    pal = []
    if bpp == 8:
        hs = struct.unpack_from('<I', data, 14)[0]
        ncol = struct.unpack_from('<I', data, 46)[0] or 256
        p = 14 + hs
        pal = [data[p + 4 * i:p + 4 * i + 3] for i in range(ncol)]
    stride = (w * bpp // 8 + 3) & ~3
    rows = []
    for y in range(h):
        row = data[off + y * stride: off + y * stride + w * bpp // 8]
        out = bytearray()
        for x in range(w):
            if bpp == 8:
                b, g, r = pal[row[x]]
            else:
                b, g, r = row[3 * x:3 * x + 3]
            out += bytes((r, g, b, 255))
        rows.append(bytes(out))
    if flip:
        rows.reverse()
    return w, h, b''.join(rows)


def png(w, h, rgba):
    raw = b''.join(b'\0' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    chunk = lambda t, d: (struct.pack('>I', len(d)) + t + d
                          + struct.pack('>I', zlib.crc32(t + d) & 0xFFFFFFFF))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b''))


def _crop(w, h, rgba):
    xs = [x for y in range(h) for x in range(w) if rgba[(y * w + x) * 4 + 3]]
    ys = [y for y in range(h) for x in range(w) if rgba[(y * w + x) * 4 + 3]]
    if not xs:
        return w, h, rgba
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    nw = x1 - x0
    out = b''.join(rgba[(y * w + x0) * 4:(y * w + x1) * 4] for y in range(y0, y1))
    return nw, y1 - y0, out


def _portrait(npc, game, npc_only):
    name = game.mes('portrait/gameport.mes').get(npc.get('portrait') or -1)
    if not name or (npc_only and not name.upper().startswith('NPC')):
        return None
    f = 'portrait/%s.bmp' % name.lower()
    return png(*bmp_pixels(game.read(f))) if game.has(f) else None


def npc_picture(npc, game):
    """-> (kind, png bytes) or None.

    Own portrait (NPC*.bmp, the companions) first; then the critter's own
    standing sprite, which tells villagers apart; the generic race portrait
    the protos carry (HUM1 etc.) only when there is no sprite.
    """
    pic = _portrait(npc, game, True)
    if pic:
        return 'portrait', pic
    aid = npc.get('aid') or 0
    for p in art_paths(aid, game):
        if game.has(p):
            try:
                return 'sprite', png(*_crop(*art_frame(game.read(p), palette=aid >> 4 & 3)))
            except (ValueError, struct.error, IndexError):
                continue
    pic = _portrait(npc, game, False)
    return ('portrait', pic) if pic else None


class Pictures:
    """Cached pictures per dialogue number (files under ~/.cache)."""

    def __init__(self, game_root=GAME):
        self.root = game_root
        self._game = None
        self._index = None

    @property
    def game(self):
        if self._game is None:
            self._game = Game(self.root)
        return self._game

    @property
    def index(self):
        if self._index is None:
            self._index = load_index(self.root) if os.path.isdir(self.root) else {}
        return self._index

    def get(self, num):
        d = os.path.join(CACHE, 'pic')
        p = os.path.join(d, '%05d.png' % num)
        miss = p + '.none'
        if os.path.exists(p):
            return open(p, 'rb').read()
        if os.path.exists(miss) or num not in self.index:
            return None
        res = None
        for npc in self.index[num]:
            res = npc_picture(npc, self.game)
            if res:
                break
        os.makedirs(d, exist_ok=True)
        if not res:
            open(miss, 'w').close()
            return None
        open(p, 'wb').write(res[1])
        return res[1]


def main():
    idx = load_index()
    if len(sys.argv) >= 3:
        pics = Pictures()
        data = pics.get(int(sys.argv[1]))
        print(idx.get(int(sys.argv[1])))
        if data:
            open(sys.argv[2], 'wb').write(data)
            print('wrote', sys.argv[2])
        else:
            print('no picture')
        return
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'source', 'dlg')
    nums = sorted(int(f[:5]) for f in os.listdir(src)) if os.path.isdir(src) else []
    hit = [n for n in nums if n in idx]
    print('dialogues %d, with a speaker %d' % (len(nums), len(hit)))


if __name__ == '__main__':
    main()
