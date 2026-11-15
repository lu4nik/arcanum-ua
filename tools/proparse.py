#!/usr/bin/env python3
"""Parser for Arcanum binary prototype files (.pro).

Format transcribed from the arcanum-ce engine sources (src/game/obj.c:
obj_read / obj_proto_read_file / obj_data_read_file_slow, field tables in
sub_40A8A0; src/game/sa.c: sa_read_no_dealloc; src/game/obj_private.c:
bitset_read_file). Little-endian throughout:

  int32     version (119)
  ObjectID  prototype_oid (24 B; type == -1 marks a prototype)
  ObjectID  oid           (24 B; type == 1, d.a = proto number)
  int32     object type (ObjectType 0..17)
  int32[n]  per-type "changed" bitmap (n per sub_40C030; ignored for protos)
  ...then EVERY field of the type's sections, in ObjectField enum order:
  INT32   -> 4 B raw, no presence byte
  INT64   -> 1 presence byte; if nonzero: 8 B
  HANDLE  -> 1 presence byte; if nonzero: 24 B (ObjectID)
  STRING  -> 1 presence byte; if nonzero: int32 len, then len+1 B
  *_ARRAY -> 1 presence byte; if nonzero a SizeableArray:
             int32 elem_size, int32 count, int32 junk(bitset_id),
             elem_size*count B values (rank order), int32 nwords,
             nwords*4 B key bitmap (bit k of word w => key w*32+k, LSB first)

Critter gender lives in OBJ_F_CRITTER_STAT_BASE_IDX (an int32 array keyed
by Stat) at key STAT_GENDER=26 (0=female, 1=male; src/game/stat.h); the
description.mes key is the plain OBJ_F_DESCRIPTION int32 (no offset:
description_get uses it directly for num < 30000).

CLI: python3 tools/proparse.py [game_dir]  — TSV of all critter protos
(loose data/proto/*.pro override same-named entries in *.dat archives).
"""
import os, struct, sys

I32, I64, STR, HDL, ARR = 'i32', 'i64', 'str', 'hdl', 'arr'

# Sections in ObjectField enum order (obj.h), types per sub_40A8A0 (obj.c).
COMMON = [
    ('current_aid', I32), ('location', I64), ('offset_x', I32),
    ('offset_y', I32), ('shadow', I32), ('overlay_fore', ARR),
    ('overlay_back', ARR), ('underlay', ARR), ('blit_flags', I32),
    ('blit_color', I32), ('blit_alpha', I32), ('blit_scale', I32),
    ('light_flags', I32), ('light_aid', I32), ('light_color', I32),
    ('overlay_light_flags', ARR), ('overlay_light_aid', ARR),
    ('overlay_light_color', ARR), ('flags', I32), ('spell_flags', I32),
    ('blocking_mask', I32), ('name', I32), ('description', I32),
    ('aid', I32), ('destroyed_aid', I32), ('ac', I32), ('hp_pts', I32),
    ('hp_adj', I32), ('hp_damage', I32), ('material', I32),
    ('resistance_idx', ARR), ('scripts_idx', ARR), ('sound_effect', I32),
    ('category', I32), ('pad_ias_1', ARR), ('pad_i64as_1', ARR),
]
WALL = [('wall_flags', I32), ('wall_pad_i_1', I32), ('wall_pad_i_2', I32),
        ('wall_pad_ias_1', ARR), ('wall_pad_i64as_1', ARR)]
PORTAL = [('portal_flags', I32), ('portal_lock_difficulty', I32),
          ('portal_key_id', I32), ('portal_notify_npc', I32),
          ('portal_pad_i_1', I32), ('portal_pad_i_2', I32),
          ('portal_pad_ias_1', ARR), ('portal_pad_i64as_1', ARR)]
CONTAINER = [('container_flags', I32), ('container_lock_difficulty', I32),
             ('container_key_id', I32), ('container_inventory_num', I32),
             ('container_inventory_list_idx', ARR),
             ('container_inventory_source', I32),
             ('container_notify_npc', I32), ('container_pad_i_1', I32),
             ('container_pad_i_2', I32), ('container_pad_ias_1', ARR),
             ('container_pad_i64as_1', ARR)]
SCENERY = [('scenery_flags', I32), ('scenery_whos_in_me', HDL),
           ('scenery_respawn_delay', I32), ('scenery_pad_i_2', I32),
           ('scenery_pad_ias_1', ARR), ('scenery_pad_i64as_1', ARR)]
PROJECTILE = [('projectile_flags_combat', I32),
              ('projectile_flags_combat_damage', I32),
              ('projectile_hit_loc', I32), ('projectile_parent_weapon', HDL),
              ('projectile_pad_i_1', I32), ('projectile_pad_i_2', I32),
              ('projectile_pad_ias_1', ARR), ('projectile_pad_i64as_1', ARR)]
ITEM = [('item_flags', I32), ('item_parent', HDL), ('item_weight', I32),
        ('item_magic_weight_adj', I32), ('item_worth', I32),
        ('item_mana_store', I32), ('item_inv_aid', I32),
        ('item_inv_location', I32), ('item_use_aid_fragment', I32),
        ('item_magic_tech_complexity', I32), ('item_discipline', I32),
        ('item_description_unknown', I32), ('item_description_effects', I32),
        ('item_spell_1', I32), ('item_spell_2', I32), ('item_spell_3', I32),
        ('item_spell_4', I32), ('item_spell_5', I32),
        ('item_spell_mana_store', I32), ('item_ai_action', I32),
        ('item_pad_i_1', I32), ('item_pad_ias_1', ARR),
        ('item_pad_i64as_1', ARR)]
WEAPON = [('weapon_flags', I32), ('weapon_paper_doll_aid', I32),
          ('weapon_bonus_to_hit', I32), ('weapon_magic_hit_adj', I32),
          ('weapon_damage_lower_idx', ARR), ('weapon_damage_upper_idx', ARR),
          ('weapon_magic_damage_adj_idx', ARR), ('weapon_speed_factor', I32),
          ('weapon_magic_speed_adj', I32), ('weapon_range', I32),
          ('weapon_magic_range_adj', I32), ('weapon_min_strength', I32),
          ('weapon_magic_min_strength_adj', I32), ('weapon_ammo_type', I32),
          ('weapon_ammo_consumption', I32), ('weapon_missile_aid', I32),
          ('weapon_visual_effect_aid', I32), ('weapon_crit_hit_chart', I32),
          ('weapon_magic_crit_hit_chance', I32),
          ('weapon_magic_crit_hit_effect', I32),
          ('weapon_crit_miss_chart', I32),
          ('weapon_magic_crit_miss_chance', I32),
          ('weapon_magic_crit_miss_effect', I32), ('weapon_pad_i_1', I32),
          ('weapon_pad_i_2', I32), ('weapon_pad_ias_1', ARR),
          ('weapon_pad_i64as_1', ARR)]
AMMO = [('ammo_flags', I32), ('ammo_quantity', I32), ('ammo_type', I32),
        ('ammo_pad_i_1', I32), ('ammo_pad_i_2', I32),
        ('ammo_pad_ias_1', ARR), ('ammo_pad_i64as_1', ARR)]
ARMOR = [('armor_flags', I32), ('armor_paper_doll_aid', I32),
         ('armor_ac_adj', I32), ('armor_magic_ac_adj', I32),
         ('armor_resistance_adj_idx', ARR),
         ('armor_magic_resistance_adj_idx', ARR),
         ('armor_silent_move_adj', I32), ('armor_magic_silent_move_adj', I32),
         ('armor_unarmed_bonus_damage', I32), ('armor_pad_i_2', I32),
         ('armor_pad_ias_1', ARR), ('armor_pad_i64as_1', ARR)]
GOLD = [('gold_flags', I32), ('gold_quantity', I32), ('gold_pad_i_1', I32),
        ('gold_pad_i_2', I32), ('gold_pad_ias_1', ARR),
        ('gold_pad_i64as_1', ARR)]
FOOD = [('food_flags', I32), ('food_pad_i_1', I32), ('food_pad_i_2', I32),
        ('food_pad_ias_1', ARR), ('food_pad_i64as_1', ARR)]
SCROLL = [('scroll_flags', I32), ('scroll_pad_i_1', I32),
          ('scroll_pad_i_2', I32), ('scroll_pad_ias_1', ARR),
          ('scroll_pad_i64as_1', ARR)]
KEY = [('key_key_id', I32), ('key_pad_i_1', I32), ('key_pad_i_2', I32),
       ('key_pad_ias_1', ARR), ('key_pad_i64as_1', ARR)]
KEY_RING = [('key_ring_flags', I32), ('key_ring_list_idx', ARR),
            ('key_ring_pad_i_1', I32), ('key_ring_pad_i_2', I32),
            ('key_ring_pad_ias_1', ARR), ('key_ring_pad_i64as_1', ARR)]
WRITTEN = [('written_flags', I32), ('written_subtype', I32),
           ('written_text_start_line', I32), ('written_text_end_line', I32),
           ('written_pad_i_1', I32), ('written_pad_i_2', I32),
           ('written_pad_ias_1', ARR), ('written_pad_i64as_1', ARR)]
GENERIC = [('generic_flags', I32), ('generic_usage_bonus', I32),
           ('generic_usage_count_remaining', I32), ('generic_pad_ias_1', ARR),
           ('generic_pad_i64as_1', ARR)]
CRITTER = [('critter_flags', I32), ('critter_flags2', I32),
           ('critter_stat_base_idx', ARR), ('critter_basic_skill_idx', ARR),
           ('critter_tech_skill_idx', ARR), ('critter_spell_tech_idx', ARR),
           ('critter_fatigue_pts', I32), ('critter_fatigue_adj', I32),
           ('critter_fatigue_damage', I32), ('critter_crit_hit_chart', I32),
           ('critter_effects_idx', ARR), ('critter_effect_cause_idx', ARR),
           ('critter_fleeing_from', HDL), ('critter_portrait', I32),
           ('critter_gold', HDL), ('critter_arrows', HDL),
           ('critter_bullets', HDL), ('critter_power_cells', HDL),
           ('critter_fuel', HDL), ('critter_inventory_num', I32),
           ('critter_inventory_list_idx', ARR),
           ('critter_inventory_source', I32),
           ('critter_description_unknown', I32),
           ('critter_follower_idx', ARR), ('critter_teleport_dest', I64),
           ('critter_teleport_map', I32), ('critter_death_time', I32),
           ('critter_auto_level_scheme', I32), ('critter_pad_i_1', I32),
           ('critter_pad_i_2', I32), ('critter_pad_i_3', I32),
           ('critter_pad_ias_1', ARR), ('critter_pad_i64as_1', ARR)]
PC = [('pc_flags', I32), ('pc_flags_fate', I32), ('pc_reputation_idx', ARR),
      ('pc_reputation_ts_idx', ARR), ('pc_background', I32),
      ('pc_background_text', I32), ('pc_quest_idx', ARR),
      ('pc_blessing_idx', ARR), ('pc_blessing_ts_idx', ARR),
      ('pc_curse_idx', ARR), ('pc_curse_ts_idx', ARR), ('pc_party_id', I32),
      ('pc_rumor_idx', ARR), ('pc_pad_ias_2', ARR),
      ('pc_schematics_found_idx', ARR), ('pc_logbook_ego_idx', ARR),
      ('pc_fog_mask', I32), ('pc_player_name', STR), ('pc_bank_money', I32),
      ('pc_global_flags', ARR), ('pc_global_variables', ARR),
      ('pc_pad_i_1', I32), ('pc_pad_i_2', I32), ('pc_pad_ias_1', ARR),
      ('pc_pad_i64as_1', ARR)]
NPC = [('npc_flags', I32), ('npc_leader', HDL), ('npc_ai_data', I32),
       ('npc_combat_focus', HDL), ('npc_who_hit_me_last', HDL),
       ('npc_experience_worth', I32), ('npc_experience_pool', I32),
       ('npc_waypoints_idx', ARR), ('npc_waypoint_current', I32),
       ('npc_standpoint_day', I64), ('npc_standpoint_night', I64),
       ('npc_origin', I32), ('npc_faction', I32),
       ('npc_retail_price_multiplier', I32),
       ('npc_substitute_inventory', HDL), ('npc_reaction_base', I32),
       ('npc_social_class', I32), ('npc_reaction_pc_idx', ARR),
       ('npc_reaction_level_idx', ARR), ('npc_reaction_time_idx', ARR),
       ('npc_wait', I32), ('npc_generator_data', I32), ('npc_pad_i_1', I32),
       ('npc_damage_idx', ARR), ('npc_shit_list_idx', ARR)]
TRAP = [('trap_flags', I32), ('trap_difficulty', I32), ('trap_pad_i_2', I32),
        ('trap_pad_ias_1', ARR), ('trap_pad_i64as_1', ARR)]

TYPE_NAMES = ['wall', 'portal', 'container', 'scenery', 'projectile',
              'weapon', 'ammo', 'armor', 'gold', 'food', 'scroll', 'key',
              'key_ring', 'written', 'generic', 'pc', 'npc', 'trap']
TYPE_SECTIONS = [
    [COMMON, WALL], [COMMON, PORTAL], [COMMON, CONTAINER], [COMMON, SCENERY],
    [COMMON, PROJECTILE], [COMMON, ITEM, WEAPON], [COMMON, ITEM, AMMO],
    [COMMON, ITEM, ARMOR], [COMMON, ITEM, GOLD], [COMMON, ITEM, FOOD],
    [COMMON, ITEM, SCROLL], [COMMON, ITEM, KEY], [COMMON, ITEM, KEY_RING],
    [COMMON, ITEM, WRITTEN], [COMMON, ITEM, GENERIC], [COMMON, CRITTER, PC],
    [COMMON, CRITTER, NPC], [COMMON, TRAP],
]

OBJ_TYPE_PC, OBJ_TYPE_NPC = 15, 16
STAT_GENDER, STAT_RACE = 26, 27
GENDERS = {0: 'female', 1: 'male'}


def _bitmap_words(sections):
    """Per-type word count of the leading 'changed' bitmap (sub_40C030)."""
    return sum((len(s) + 31) // 32 for s in sections)


def _read_array(data, pos):
    """SizeableArray -> ({key: value}, new_pos); value only for 4/8-byte elems."""
    elem_size, count, _junk = struct.unpack_from('<iii', data, pos)
    pos += 12
    raw = data[pos:pos + elem_size * count]
    pos += elem_size * count
    (nwords,) = struct.unpack_from('<i', data, pos)
    pos += 4
    words = struct.unpack_from('<%dI' % nwords, data, pos)
    pos += 4 * nwords
    keys = [w * 32 + b for w, word in enumerate(words)
            for b in range(32) if word & (1 << b)]
    out = {}
    if elem_size in (4, 8):
        fmt = '<i' if elem_size == 4 else '<q'
        for rank, key in enumerate(keys[:count]):
            out[key] = struct.unpack_from(fmt, raw, rank * elem_size)[0]
    return out, pos


def parse_pro(data):
    """Parse one .pro blob -> dict (proto_id, type, type_name, fields{...}).

    Raises ValueError on version/layout mismatch; asserts the whole file is
    consumed, so a silent misparse cannot slip through.
    """
    (version,) = struct.unpack_from('<i', data, 0)
    if version != 119:
        raise ValueError('bad version %d (want 119)' % version)
    proto_type = struct.unpack_from('<h', data, 4)[0]
    if proto_type != -1:
        raise ValueError('not a prototype (oid type %d)' % proto_type)
    oid_type = struct.unpack_from('<h', data, 28)[0]
    (proto_id,) = struct.unpack_from('<i', data, 36)
    if oid_type != 1:
        raise ValueError('unexpected oid type %d' % oid_type)
    (obj_type,) = struct.unpack_from('<i', data, 52)
    if not 0 <= obj_type <= 17:
        raise ValueError('bad object type %d' % obj_type)
    sections = TYPE_SECTIONS[obj_type]
    pos = 56 + 4 * _bitmap_words(sections)

    fields = {}
    for section in sections:
        for name, ftype in section:
            if ftype == I32:
                (fields[name],) = struct.unpack_from('<i', data, pos)
                pos += 4
                continue
            present = data[pos]
            pos += 1
            if not present:
                fields[name] = None
            elif ftype == I64:
                (fields[name],) = struct.unpack_from('<q', data, pos)
                pos += 8
            elif ftype == HDL:
                fields[name] = data[pos:pos + 24]
                pos += 24
            elif ftype == STR:
                (slen,) = struct.unpack_from('<i', data, pos)
                pos += 4
                fields[name] = data[pos:pos + slen].decode('cp1252', 'replace')
                pos += slen + 1
            else:
                fields[name], pos = _read_array(data, pos)
    if pos != len(data):
        raise ValueError('trailing bytes: parsed %d of %d' % (pos, len(data)))
    return {'proto_id': proto_id, 'type': obj_type,
            'type_name': TYPE_NAMES[obj_type], 'fields': fields}


def art_gender(art_id):
    """Gender encoded in a critter art id, or None.

    tig art (first_party/tig/src/art.c): type = art_id >> 28; for
    TIG_ART_TYPE_CRITTER (2) the body-art gender is bit 27 (0=female,
    1=male — TIG_ART_CRITTER_GENDER_*). MONSTER (12) / UNIQUE_NPC (13)
    art carries the bit too but the engine does not select body art by
    it, so only plain critter art is reported.
    """
    if art_id is None:
        return None
    art_id &= 0xFFFFFFFF
    if art_id >> 28 != 2:
        return None
    return GENDERS[(art_id >> 27) & 1]


def critter_info(parsed):
    """-> (gender, description_id, name_id, art_gender) for a critter, else None.

    gender is 'female'/'male'/None (None = STAT_GENDER absent from the
    stored base-stat array; the engine would then read it as 0 = female).
    art_gender is the gender of the body sprite per OBJ_F_AID (fallback
    OBJ_F_CURRENT_AID), or None for monster/unique-NPC art.
    """
    if parsed['type'] not in (OBJ_TYPE_PC, OBJ_TYPE_NPC):
        return None
    f = parsed['fields']
    stats = f.get('critter_stat_base_idx') or {}
    gender = GENDERS.get(stats.get(STAT_GENDER))
    aid = f.get('aid')
    ag = art_gender(aid if aid not in (None, -1) else f.get('current_aid'))
    return gender, f.get('description'), f.get('name'), ag


def load_protos(game_dir='/Applications/Arcanum'):
    """All prototypes: loose data/proto/*.pro override *.dat entries.

    -> dict proto_id -> (source_label, parsed_dict)
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import tdat
    protos = {}
    dats = [os.path.join(game_dir, n) for n in
            ('arcanum1.dat', 'arcanum2.dat', 'arcanum3.dat',
             'Arcanum4.dat', 'Arcanum5.dat')]
    for dat in dats:
        if not os.path.exists(dat):
            continue
        for e in tdat.read_entries(dat):
            if e[0].startswith('proto/') and e[0].endswith('.pro') and e[2] > 0:
                parsed = parse_pro(tdat.read_file(dat, e))
                protos[parsed['proto_id']] = (os.path.basename(dat) + ':'
                                              + os.path.basename(e[0]), parsed)
    loose = os.path.join(game_dir, 'data', 'proto')
    if os.path.isdir(loose):
        for fname in sorted(os.listdir(loose)):
            if not fname.endswith('.pro'):
                continue
            with open(os.path.join(loose, fname), 'rb') as fh:
                parsed = parse_pro(fh.read())
            protos[parsed['proto_id']] = (fname, parsed)
    return protos


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else '/Applications/Arcanum'
    protos = load_protos(game)
    ncrit = 0
    print('proto_id\tsource\ttype\tgender\tdescription_id\tname_id\tart_gender')
    for pid in sorted(protos):
        source, parsed = protos[pid]
        info = critter_info(parsed)
        if info is None:
            continue
        gender, desc, name, ag = info
        ncrit += 1
        print('%d\t%s\t%s\t%s\t%s\t%s\t%s'
              % (pid, source, parsed['type_name'], gender, desc, name, ag))
    print('# %d protos total, %d critters' % (len(protos), ncrit),
          file=sys.stderr)


if __name__ == '__main__':
    main()
