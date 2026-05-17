#!/usr/bin/env python3
import warnings; warnings.filterwarnings("ignore")
"""
D&D Module Adventure Engine — V4
Architecture: Hard-coded OSE AF rules engine + AI as presentation layer only.
Layer 1 (Validation) → Layer 2 (Claude: intent parse) → Layer 3 (Resolution) → Layer 4 (Ollama/Claude: narrate)
"""
# ── IMPORTS ───────────────────────────────────────────────────────────────────
import http.server, json, os, pathlib, random, re, threading, time, urllib.request, urllib.parse, math
from http import HTTPStatus

PORT    = 8080
VERSION = "4.0"
SAVES_DIR = pathlib.Path.home() / 'Documents' / 'DnDAdventure' / 'saves'
MODULES_DIR = pathlib.Path.home() / 'Documents' / 'DnDAdventure' / 'modules'
SAVES_DIR.mkdir(parents=True, exist_ok=True)
MODULES_DIR.mkdir(parents=True, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A: OSE AF RULES ENGINE
# All OSE Advanced Fantasy rules data and resolution logic.
# Zero AI involvement. All values from official OSE AF rulebooks.
# ═══════════════════════════════════════════════════════════════════════════════
import random, math

# ── DICE ─────────────────────────────────────────────────────────────────────
def roll(sides, n=1, modifier=0):
    """Roll n dice with given sides, add modifier. Returns (total, [individual rolls])."""
    rolls = [random.randint(1, sides) for _ in range(n)]
    return sum(rolls) + modifier, rolls

def roll_expr(expr):
    """Parse and roll dice expression like '2d6+3', '1d8', 'd20'. Returns (total, detail_str)."""
    import re
    expr = expr.strip().lower()
    m = re.match(r'^(\d*)d(\d+)([+-]\d+)?$', expr)
    if not m:
        try: v = int(expr); return v, str(v)
        except: return 0, '0'
    n = int(m.group(1)) if m.group(1) else 1
    sides = int(m.group(2))
    mod = int(m.group(3)) if m.group(3) else 0
    rolls = [random.randint(1, sides) for _ in range(n)]
    total = sum(rolls) + mod
    detail = f"{n}d{sides}=[{','.join(map(str,rolls))}]"
    if mod: detail += f"{'+' if mod>0 else ''}{mod}"
    detail += f"={total}"
    return total, detail

# ── STAT MODIFIER (OSE AF) ────────────────────────────────────────────────────
def stat_mod(score):
    if score <= 3:   return -3
    if score <= 5:   return -2
    if score <= 8:   return -1
    if score <= 12:  return 0
    if score <= 15:  return 1
    if score <= 17:  return 2
    return 3

# ── CLASS DATA ────────────────────────────────────────────────────────────────
OSE_CLASSES = {
    'Fighter':     {'hd':8,  'thac0_group':'fighter', 'saves_group':'fighter',
                   'weapons':'any', 'armour':'any', 'title':'Fighter',
                   'prime_req':'STR', 'xp_bonus_req':13},
    'Paladin':     {'hd':8,  'thac0_group':'fighter', 'saves_group':'fighter',
                   'weapons':'any', 'armour':'any', 'title':'Paladin',
                   'prime_req':'STR', 'xp_bonus_req':13, 'alignment':['Lawful']},
    'Ranger':      {'hd':8,  'thac0_group':'fighter', 'saves_group':'fighter',
                   'weapons':'any', 'armour':'any', 'title':'Ranger',
                   'prime_req':'STR', 'xp_bonus_req':13},
    'Barbarian':   {'hd':10, 'thac0_group':'fighter', 'saves_group':'fighter',
                   'weapons':'any', 'armour':'chain_and_lighter', 'title':'Barbarian',
                   'prime_req':'STR', 'xp_bonus_req':13, 'illiterate':True},
    'Cleric':      {'hd':6,  'thac0_group':'cleric',  'saves_group':'cleric',
                   'weapons':'blunt', 'armour':'any', 'title':'Cleric',
                   'prime_req':'WIS', 'xp_bonus_req':13, 'spells':'cleric'},
    'Druid':       {'hd':6,  'thac0_group':'cleric',  'saves_group':'cleric',
                   'weapons':'druid', 'armour':'leather_shield', 'title':'Druid',
                   'prime_req':'WIS', 'xp_bonus_req':13, 'spells':'druid',
                   'alignment':['Neutral']},
    'Magic-User':  {'hd':4,  'thac0_group':'mage',    'saves_group':'mage',
                   'weapons':'dagger_staff', 'armour':'none', 'title':'Magic-User',
                   'prime_req':'INT', 'xp_bonus_req':13, 'spells':'mu'},
    'Illusionist': {'hd':4,  'thac0_group':'mage',    'saves_group':'mage',
                   'weapons':'dagger_staff', 'armour':'none', 'title':'Illusionist',
                   'prime_req':'INT', 'xp_bonus_req':13, 'spells':'illusionist'},
    'Thief':       {'hd':4,  'thac0_group':'thief',   'saves_group':'thief',
                   'weapons':'any', 'armour':'leather', 'title':'Thief',
                   'prime_req':'DEX', 'xp_bonus_req':13, 'backstab':True},
    'Assassin':    {'hd':4,  'thac0_group':'thief',   'saves_group':'thief',
                   'weapons':'any', 'armour':'leather_shield', 'title':'Assassin',
                   'prime_req':'DEX', 'xp_bonus_req':13, 'backstab':True},
    'Bard':        {'hd':6,  'thac0_group':'thief',   'saves_group':'thief',
                   'weapons':'any', 'armour':'chain_and_lighter_shield', 'title':'Bard',
                   'prime_req':'CHA', 'xp_bonus_req':13},
    'Monk':        {'hd':6,  'thac0_group':'thief',   'saves_group':'thief',
                   'weapons':'monk', 'armour':'none', 'title':'Monk',
                   'prime_req':'STR', 'xp_bonus_req':13},
}

WEAPON_RESTRICTIONS = {
    'any':          None,  # no restriction
    'blunt':        ['Club','Mace','War Hammer','Staff','Sling'],
    'druid':        ['Club','Dagger','Hand Axe','Spear','Staff','Sling','Short Bow'],
    'dagger_staff': ['Dagger','Silver Dagger','Staff'],
    'monk':         ['Club','Dagger','Hand Axe','Javelin','Short Sword','Staff','Sling'],
}

ARMOUR_RESTRICTIONS = {
    'any':                        None,
    'none':                       [],
    'leather':                    ['Leather Armour'],
    'leather_shield':             ['Leather Armour','Shield'],
    'chain_and_lighter':          ['Leather Armour','Chain Mail'],
    'chain_and_lighter_shield':   ['Leather Armour','Chain Mail','Shield'],
}

# ── XP TABLES (level 1-14 thresholds) ────────────────────────────────────────
OSE_XP_TABLE = {
    'Fighter':     [0,2000,4000,8000,16000,32000,64000,120000,240000,360000,480000,600000,720000,840000],
    'Paladin':     [0,2750,5500,11000,22000,45000,95000,175000,350000,525000,700000,875000,1050000,1225000],
    'Ranger':      [0,2500,5000,10000,20000,40000,80000,150000,300000,450000,600000,750000,900000,1050000],
    'Barbarian':   [0,2000,4000,8000,16000,32000,65000,130000,250000,375000,500000,625000,750000,875000],
    'Cleric':      [0,1500,3000,6000,12000,25000,50000,100000,200000,300000,400000,500000,600000,700000],
    'Druid':       [0,2000,4000,7500,15000,35000,70000,140000,270000,400000,530000,660000,800000,1000000],
    'Magic-User':  [0,2500,5000,10000,20000,40000,80000,150000,300000,450000,600000,750000,900000,1050000],
    'Illusionist': [0,2250,4500,9000,18000,36000,72000,144000,288000,432000,576000,720000,864000,1008000],
    'Thief':       [0,1250,2500,5000,10000,20000,40000,80000,160000,280000,400000,520000,640000,760000],
    'Assassin':    [0,1500,3000,6000,12000,25000,50000,100000,200000,300000,400000,500000,600000,700000],
    'Bard':        [0,1500,3000,6000,12000,25000,50000,100000,200000,300000,400000,500000,600000,700000],
    'Monk':        [0,2250,4500,9000,18000,37000,75000,150000,300000,450000,600000,750000,900000,1050000],
}

def get_level_for_xp(cls, xp):
    tbl = OSE_XP_TABLE.get(cls, OSE_XP_TABLE['Fighter'])
    lv = 1
    for i, threshold in enumerate(tbl):
        if xp >= threshold: lv = i + 1
    return min(lv, len(tbl))

def get_xp_for_next_level(cls, level):
    tbl = OSE_XP_TABLE.get(cls, OSE_XP_TABLE['Fighter'])
    if level >= len(tbl): return None
    return tbl[level]

# ── THAC0 BY LEVEL ────────────────────────────────────────────────────────────
THAC0_TABLE = {
    'fighter': [20,19,18,17,16,15,14,13,12,11,10,9,8,7],
    'cleric':  [20,20,20,18,18,18,16,16,16,14,14,14,12,12],
    'mage':    [20,20,20,20,20,18,18,18,18,18,16,16,16,16],
    'thief':   [20,20,19,19,18,18,17,17,16,16,15,15,14,14],
}

def get_thac0(cls, level):
    cd = OSE_CLASSES.get(cls, {})
    grp = cd.get('thac0_group', 'fighter')
    tbl = THAC0_TABLE.get(grp, THAC0_TABLE['fighter'])
    return tbl[min(level-1, len(tbl)-1)]

# ── SAVING THROWS ─────────────────────────────────────────────────────────────
# Format: [[min_level, max_level, [death, wands, paralysis, breath, spells]], ...]
SAVES_TABLE = {
    'fighter': [
        [1,3,[12,13,14,15,16]], [4,6,[10,11,12,13,14]],
        [7,9,[8,9,10,10,12]],   [10,12,[6,7,8,8,10]],
        [13,15,[4,5,6,5,8]],
    ],
    'cleric': [
        [1,4,[11,12,14,16,15]], [5,8,[9,10,12,14,13]],
        [9,12,[6,7,9,11,10]],   [13,15,[3,5,7,8,8]],
    ],
    'mage': [
        [1,5,[13,14,13,16,15]], [6,10,[11,12,11,14,12]],
        [11,15,[8,9,8,11,8]],
    ],
    'thief': [
        [1,4,[13,14,13,16,15]], [5,8,[12,13,11,14,13]],
        [9,12,[10,11,9,12,10]], [13,15,[8,9,7,10,8]],
    ],
}
SAVE_CATEGORIES = ['death', 'wands', 'paralysis', 'breath', 'spells']

def get_saves(cls, level):
    cd = OSE_CLASSES.get(cls, {})
    grp = cd.get('saves_group', 'fighter')
    bands = SAVES_TABLE.get(grp, SAVES_TABLE['fighter'])
    for lo, hi, vals in bands:
        if lo <= level <= hi:
            return dict(zip(SAVE_CATEGORIES, vals))
    return dict(zip(SAVE_CATEGORIES, bands[-1][2]))

def resolve_saving_throw(pc, category, modifier=0):
    """Roll saving throw. Returns (success, roll, target, detail)."""
    saves = pc.get('saves', get_saves(pc.get('cls','Fighter'), pc.get('level',1)))
    target = saves.get(category, 15)
    target -= modifier  # positive modifier makes it easier
    total, rolls = roll(20)
    nat = rolls[0]
    success = total >= target
    detail = f"Save vs {category}: d20=[{nat}]={total} vs {target} — {'SUCCESS' if success else 'FAILED'}"
    return success, nat, target, detail

# ── ATTACK RESOLUTION ─────────────────────────────────────────────────────────
def resolve_attack(attacker, weapon_name, target_ac, is_ranged=False, backstab=False, magic_bonus=0):
    """
    Full OSE attack resolution.
    Returns dict with all details for both display and narration.
    """
    cls = attacker.get('cls', 'Fighter')
    level = attacker.get('level', 1)
    stats = attacker.get('stats', {})
    thac0 = get_thac0(cls, level)

    # Stat modifier
    if is_ranged:
        stat_bonus = stat_mod(stats.get('DEX', 10))
    else:
        stat_bonus = stat_mod(stats.get('STR', 10))

    # Rage bonus (Barbarian)
    rage_bonus = attacker.get('rage_attack_bonus', 0)
    total_bonus = stat_bonus + magic_bonus + rage_bonus

    # Roll d20
    d20, _ = roll(20)
    nat20 = (d20 == 20)
    nat1  = (d20 == 1)

    # THAC0 system: hit if d20 + bonus >= THAC0 - target_AC
    # Equivalent: (THAC0 - total_bonus - d20) = AC hit
    ac_hit = thac0 - (d20 + total_bonus)
    hit = nat20 or (not nat1 and d20 + total_bonus >= thac0 - target_ac)

    result = {
        'hit': hit,
        'nat20': nat20,
        'nat1': nat1,
        'd20': d20,
        'total_bonus': total_bonus,
        'stat_bonus': stat_bonus,
        'magic_bonus': magic_bonus,
        'thac0': thac0,
        'target_ac': target_ac,
        'ac_hit': ac_hit,
        'weapon': weapon_name,
        'is_ranged': is_ranged,
        'backstab': backstab,
        'damage': 0,
        'damage_detail': '',
    }

    if hit:
        # Get weapon damage
        weapon = OSE_WEAPONS.get(weapon_name, {})
        dmg_die = weapon.get('dmg', '1d6')
        if nat20:
            # Critical: maximum damage
            dmg_val, dmg_detail = roll_expr(dmg_die)
            dmg_val2, _ = roll_expr(dmg_die)
            dmg_val = max(dmg_val, dmg_val2)  # take better of 2 rolls on crit
            dmg_detail = f"CRIT {dmg_detail}"
        else:
            dmg_val, dmg_detail = roll_expr(dmg_die)

        # STR bonus to melee damage only
        if not is_ranged:
            dmg_str = stat_mod(stats.get('STR', 10)) + attacker.get('rage_damage_bonus', 0)
            dmg_val = max(1, dmg_val + magic_bonus + dmg_str)
            dmg_detail += f"{'+'if dmg_str>=0 else ''}{dmg_str}" if dmg_str != 0 else ''

        # Backstab multiplier
        if backstab:
            mult = get_backstab_multiplier(cls, level)
            dmg_val *= mult
            dmg_detail += f" ×{mult}(backstab)"

        result['damage'] = dmg_val
        result['damage_detail'] = dmg_detail

    # Build display string
    bonus_str = f"{'+' if total_bonus >= 0 else ''}{total_bonus}" if total_bonus != 0 else ''
    if nat20:
        result['display'] = f"ATTACK ({weapon_name}): d20=[20]{bonus_str} — CRITICAL HIT! | DAMAGE: {result['damage_detail']} = {result['damage']}"
    elif nat1:
        result['display'] = f"ATTACK ({weapon_name}): d20=[1]{bonus_str} — FUMBLE!"
    elif hit:
        result['display'] = f"ATTACK ({weapon_name}): d20=[{d20}]{bonus_str} = {d20+total_bonus} — HIT (AC {target_ac}) | DAMAGE: {result['damage_detail']} = {result['damage']}"
    else:
        result['display'] = f"ATTACK ({weapon_name}): d20=[{d20}]{bonus_str} = {d20+total_bonus} — MISS (needed {thac0-target_ac} to hit AC {target_ac})"

    return result

def get_backstab_multiplier(cls, level):
    if cls not in ('Thief','Assassin'): return 1
    if level <= 4: return 2
    if level <= 8: return 3
    if level <= 12: return 4
    return 5

# ── MORALE CHECK ──────────────────────────────────────────────────────────────
def check_morale(morale_score, modifier=0):
    """2d6 vs morale score. Returns (holds, roll, detail)."""
    total, rolls = roll(6, 2)
    total += modifier
    holds = total <= morale_score
    detail = f"Morale: 2d6=[{rolls[0]},{rolls[1]}]={total} vs ML {morale_score} — {'HOLDS' if holds else 'FLEES'}"
    return holds, total, detail

# ── REACTION ROLL ─────────────────────────────────────────────────────────────
def reaction_roll(cha_score, modifier=0):
    """2d6 + CHA mod. Returns (reaction_str, total, detail)."""
    total, rolls = roll(6, 2)
    cha_bonus = stat_mod(cha_score)
    total += cha_bonus + modifier
    if total <= 2:   reaction = 'hostile'
    elif total <= 5: reaction = 'unfriendly'
    elif total <= 8: reaction = 'neutral'
    elif total <= 11:reaction = 'friendly'
    else:            reaction = 'very_friendly'
    detail = f"Reaction: 2d6=[{rolls[0]},{rolls[1]}]+{cha_bonus}(CHA)={total} — {reaction.upper()}"
    return reaction, total, detail

# ── TURN UNDEAD ───────────────────────────────────────────────────────────────
# Cleric level → [Skeleton, Zombie, Ghoul, Wight, Wraith, Mummy, Spectre, Vampire, Ghost]
# T=turn, D=destroy, None=impossible, number=min 2d6 roll
TURN_TABLE = {
    1:  [7, 9, 11,None,None,None,None,None,None],
    2:  [5, 7,  9,  11,None,None,None,None,None],
    3:  [3, 5,  7,   9,  11,None,None,None,None],
    4:  ['T',3, 5,   7,   9,  11,None,None,None],
    5:  ['T','T',3,  5,   7,   9,  11,None,None],
    6:  ['D','T','T',3,   5,   7,   9,  11,None],
    7:  ['D','D','T','T', 3,   5,   7,   9,  11],
    8:  ['D','D','D','T','T',  3,   5,   7,   9],
    9:  ['D','D','D','D','T', 'T',  3,   5,   7],
    10: ['D','D','D','D','D', 'T', 'T',  3,   5],
    11: ['D','D','D','D','D', 'D', 'T', 'T',  3],
    12: ['D','D','D','D','D', 'D', 'D', 'T', 'T'],
}
UNDEAD_TYPES = ['Skeleton','Zombie','Ghoul','Wight','Wraith','Mummy','Spectre','Vampire','Ghost']

def resolve_turn_undead(cleric_level, undead_type, evil_cleric=False):
    """Returns (result_type, roll, detail). result_type: 'turned','destroyed','failed','impossible'"""
    row = TURN_TABLE.get(min(cleric_level, 12), TURN_TABLE[12])
    idx = UNDEAD_TYPES.index(undead_type) if undead_type in UNDEAD_TYPES else 0
    entry = row[idx] if idx < len(row) else None

    if entry is None:
        return 'impossible', 0, f"Turn Undead: {undead_type} cannot be turned at this level."

    total, rolls = roll(6, 2)
    detail = f"Turn Undead ({undead_type}): 2d6=[{rolls[0]},{rolls[1]}]={total}"

    if entry == 'D':
        result = 'destroyed' if not evil_cleric else 'controlled'
        detail += f" — AUTO-{'DESTROY' if not evil_cleric else 'CONTROL'}"
    elif entry == 'T':
        result = 'turned' if not evil_cleric else 'controlled'
        detail += f" — AUTO-{'TURN' if not evil_cleric else 'CONTROL'}"
    elif total >= entry:
        result = 'turned' if not evil_cleric else 'controlled'
        detail += f" vs needed {entry} — {'TURNED' if not evil_cleric else 'CONTROLLED'}"
    else:
        result = 'failed'
        detail += f" vs needed {entry} — FAILED"

    return result, total, detail

# ── THIEF SKILLS ──────────────────────────────────────────────────────────────
THIEF_SKILLS = {
    'Thief': {
        'Open Locks':        [15,20,25,30,35,45,55,65,75,85,90,92,94,96],
        'Find/Remove Traps': [10,15,20,25,30,35,40,45,55,65,75,80,85,90],
        'Pick Pockets':      [20,25,30,35,40,45,55,65,75,85,90,92,94,96],
        'Move Silently':     [25,30,35,40,45,50,60,70,80,90,92,94,96,98],
        'Climb Walls':       [80,82,84,86,88,90,92,94,96,98,99,99,99,99],
        'Hide in Shadows':   [10,15,20,25,31,40,50,60,70,80,85,88,91,94],
        'Hear Noise':        [30,35,40,45,50,55,60,65,70,75,80,85,90,95],
        'Read Languages':    [0,0,0,0,20,25,30,35,45,55,65,75,80,85],
    },
    'Assassin': {
        'Open Locks':        [10,15,20,25,30,35,40,45,50,60,70,75,80,85],
        'Find/Remove Traps': [5,10,15,20,25,30,35,40,50,60,70,75,80,85],
        'Pick Pockets':      [15,20,25,30,35,40,45,50,55,65,75,80,85,90],
        'Move Silently':     [20,25,31,37,43,49,55,61,70,78,85,90,94,97],
        'Climb Walls':       [75,78,81,84,87,90,92,94,96,98,99,99,99,99],
        'Hide in Shadows':   [5,10,15,20,25,31,37,43,52,60,70,77,85,90],
        'Hear Noise':        [20,25,30,35,40,45,50,55,60,65,70,75,80,85],
    },
}

def resolve_thief_skill(pc, skill_name, modifier=0):
    """Roll d% (1-100) vs skill percentage. Returns (success, roll, target, detail)."""
    cls = pc.get('cls','Thief')
    level = pc.get('level', 1)
    skills = THIEF_SKILLS.get(cls, THIEF_SKILLS['Thief'])
    if skill_name not in skills:
        return False, 0, 0, f"{skill_name} is not a {cls} skill."
    target = skills[skill_name][min(level-1, 13)] + modifier
    d100, _ = roll(100)
    success = d100 <= target
    detail = f"{skill_name}: d%=[{d100}] vs {target}% — {'SUCCESS' if success else 'FAILED'}"
    return success, d100, target, detail

# ── SPELL DATA ────────────────────────────────────────────────────────────────
# Spell slot tables: index = level-1, value = [lvl1_slots, lvl2_slots, ...]
SPELL_SLOTS = {
    'mu': [
        [1],[2],[2,1],[2,2],[2,2,1],[2,2,2],[3,2,2,1],[3,3,2,2],
        [3,3,3,2,1],[3,3,3,3,2],[4,3,3,3,2,1],[4,4,3,3,3,2],
        [4,4,4,3,3,3],[4,4,4,4,4,4],
    ],
    'illusionist': [
        [1],[2],[2,1],[2,2],[3,2,1],[3,2,2],[3,3,2,1],[3,3,3,2],
        [4,3,3,2,1],[4,4,3,3,2],[4,4,4,3,2,1],[4,4,4,4,3,2],
        [5,5,4,4,3,3],[5,5,5,4,4,4],
    ],
    'cleric': [
        [1],[2],[2,1],[3,2],[3,3,1],[3,3,2],[3,3,2,1],[3,3,3,2],
        [4,4,3,2,1],[4,4,3,3,2],[5,4,4,3,2,1],[5,5,4,4,3,2],
        [5,5,5,4,3,3],[6,5,5,5,4,4],
    ],
    'druid': [
        [1],[2],[2,1],[3,2],[3,3,1],[3,3,2],[3,3,2,1],[3,3,3,2],
        [4,4,3,2,1],[4,4,3,3,2],[5,4,4,3,2,1],[5,5,4,4,3,2],
        [5,5,5,4,3,3],[6,5,5,5,4,4],
    ],
    'ranger':  [[],[],[],[],[],[],[],[1],[1,1],[2,1],[2,2],[2,2,1],[3,2,1],[3,2,2]],
    'paladin': [[],[],[],[],[],[],[],[],[1],[2],[2,1],[2,2],[3,2],[3,3]],
}

def get_spell_slots(cls, level):
    """Returns list of slot counts per spell level for given class and character level."""
    cd = OSE_CLASSES.get(cls, {})
    spell_type = cd.get('spells')
    if not spell_type: return []
    tbl = SPELL_SLOTS.get(spell_type, [])
    if not tbl or level > len(tbl): return []
    return list(tbl[level-1])

# Full spell database
MU_SPELLS = {
  1: [
    {'name':'Charm Person',       'range':'120ft','duration':'Special',     'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'charm',    'desc':'One humanoid saves vs Spells or regards caster as trusted friend. Retested monthly.'},
    {'name':'Detect Magic',       'range':'60ft', 'duration':'2 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Detects magical auras on items, creatures, or areas within 60ft.'},
    {'name':'Floating Disc',      'range':'6ft',  'duration':'6 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Creates hovering disc, carries 500 lbs. Follows caster.'},
    {'name':'Hold Portal',        'range':'10ft', 'duration':'2d6 turns',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'hold',     'desc':'Holds door/gate shut. Knock negates.'},
    {'name':'Light',              'range':'60ft', 'duration':'6 turns+1/lvl','save':'Spells', 'auto_hit':False,'dmg':None,    'effect':'light',    'desc':'15ft radius light. Cast on eyes: target saves vs Spells or blinded.'},
    {'name':'Magic Missile',      'range':'150ft','duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':'1d6+1', 'effect':'damage',   'desc':'Auto-hit 1d6+1 damage. +1 missile per 2 levels above 1st.'},
    {'name':'Protection from Evil','range':'Touch','duration':'2 turns/lvl','save':None,      'auto_hit':True, 'dmg':None,    'effect':'protect',  'desc':'+1 AC and saves vs evil creatures. Blocks charm/possession.'},
    {'name':'Read Languages',     'range':'Self', 'duration':'1 turn',      'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Read any written language including treasure maps.'},
    {'name':'Read Magic',         'range':'Self', 'duration':'1 turn',      'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Read magical writings on scrolls and spellbooks.'},
    {'name':'Shield',             'range':'Self', 'duration':'2 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'shield',   'desc':'AC 2 vs missiles, AC 4 vs melee. Immune to Magic Missile.'},
    {'name':'Sleep',              'range':'240ft','duration':'4d4 turns',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'sleep',    'desc':'2d8 HD of creatures (lowest HD first) fall asleep. No save. Max 4 HD each.'},
    {'name':'Ventriloquism',      'range':'60ft', 'duration':'2 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Throw voice to any location in range.'},
  ],
  2: [
    {'name':'Continual Light',    'range':'120ft','duration':'Permanent',   'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'light',    'desc':'Permanent 30ft radius light. Cast on eyes: permanent blindness (save negates).'},
    {'name':'Detect Evil',        'range':'60ft', 'duration':'2 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Detect evil intentions or enchantments.'},
    {'name':'Detect Invisible',   'range':'10ft/lvl','duration':'1 turn/lvl','save':None,     'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'See invisible objects and creatures.'},
    {'name':'ESP',                'range':'60ft', 'duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Read surface thoughts of one creature per turn.'},
    {'name':'Invisibility',       'range':'Touch','duration':'Until attack','save':None,      'auto_hit':True, 'dmg':None,    'effect':'invisible','desc':'Invisible until target attacks or casts a spell.'},
    {'name':'Knock',              'range':'60ft', 'duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'unlock',   'desc':'Opens stuck, locked, or magically held doors/chests.'},
    {'name':'Levitate',           'range':'20ft/lvl','duration':'1 turn/lvl','save':None,     'auto_hit':True, 'dmg':None,    'effect':'move',     'desc':'Rise/descend at 6ft/round. Pull on objects to move horizontally.'},
    {'name':'Locate Object',      'range':'60ft+10/lvl','duration':'1 round','save':None,     'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Sense direction to a specific known object.'},
    {'name':'Mirror Image',       'range':'Self', 'duration':'2 turns',     'save':None,      'auto_hit':True, 'dmg':'1d4',   'effect':'mirror',   'desc':'1d4 illusory duplicates. Each hit on a duplicate destroys it.'},
    {'name':'Phantasmal Force',   'range':'240ft','duration':'Concentration','save':'Spells', 'auto_hit':False,'dmg':None,    'effect':'illusion', 'desc':'Illusion up to 20x20x20ft. Disappears when touched or disbelieved.'},
    {'name':'Web',                'range':'10ft', 'duration':'48 turns',    'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'entangle', 'desc':'8,000 cubic ft sticky webs. Save vs Spells or stuck. Flammable.'},
    {'name':'Wizard Lock',        'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'lock',     'desc':'Permanently locks door/chest. Knock opens it.'},
  ],
  3: [
    {'name':'Clairvoyance',       'range':'60ft', 'duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'See through walls/solid objects within 60ft.'},
    {'name':'Dispel Magic',       'range':'120ft','duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'dispel',   'desc':'Remove magic effects. 5% failure per level difference.'},
    {'name':'Fireball',           'range':'240ft','duration':'Instant',     'save':'Spells',  'auto_hit':False,'dmg':'1d6/lvl','effect':'damage',  'desc':'20ft radius explosion. 1d6/level. Save vs Spells for half.'},
    {'name':'Fly',                'range':'Touch','duration':'1d6+1 turns/lvl','save':None,   'auto_hit':True, 'dmg':None,    'effect':'fly',      'desc':'Fly at 120ft/turn. Duration secret (GM rolls).'},
    {'name':'Haste',              'range':'240ft','duration':'3 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'haste',    'desc':'Up to 24 creatures double speed and attacks. Ages each 1 year.'},
    {'name':'Hold Person',        'range':'120ft','duration':'1 turn/lvl',  'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'hold',     'desc':'1-4 humanoids paralysed. Save vs Spells negates.'},
    {'name':'Infravision',        'range':'Touch','duration':'1 day',       'save':None,      'auto_hit':True, 'dmg':None,    'effect':'sense',    'desc':'See in total darkness to 60ft.'},
    {'name':'Invisibility 10ft Radius','range':'Touch','duration':'Until attack','save':None, 'auto_hit':True, 'dmg':None,    'effect':'invisible','desc':'All in 10ft radius become invisible. Breaks individually.'},
    {'name':'Lightning Bolt',     'range':'Self', 'duration':'Instant',     'save':'Spells',  'auto_hit':False,'dmg':'1d6/lvl','effect':'damage',  'desc':'60ft bolt, 1d6/level. Save for half. Bounces off stone walls.'},
    {'name':'Protection from Evil 10ft Radius','range':'Touch','duration':'2 turns/lvl','save':None,'auto_hit':True,'dmg':None,'effect':'protect', 'desc':'Protection from Evil for all in 10ft radius.'},
    {'name':'Protection from Normal Missiles','range':'Touch','duration':'2 turns/lvl','save':None,'auto_hit':True,'dmg':None,'effect':'protect',  'desc':'Immune to all non-magical missiles.'},
    {'name':'Water Breathing',    'range':'30ft', 'duration':'1 day',       'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Target breathes water as air.'},
  ],
  4: [
    {'name':'Charm Monster',      'range':'120ft','duration':'Special',     'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'charm',    'desc':'As Charm Person but any creature type.'},
    {'name':'Confusion',          'range':'120ft','duration':'2 rounds/lvl','save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'confuse',  'desc':'2d6 creatures act randomly each round.'},
    {'name':'Dimension Door',     'range':'Self', 'duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'teleport', 'desc':'Teleport up to 360ft instantly.'},
    {'name':'Growth of Plants',   'range':'120ft','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'terrain',  'desc':'3,000 sq ft plants grow dense and entangling.'},
    {'name':'Ice Storm',          'range':'120ft','duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':'3d10',  'effect':'damage',   'desc':'3d10 hail damage in 40ft diameter. Or blinding sleet.'},
    {'name':'Polymorph Others',   'range':'60ft', 'duration':'Permanent',   'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'polymorph','desc':'Transform creature permanently. Save vs Spells negates.'},
    {'name':'Polymorph Self',     'range':'Self', 'duration':'6 turns/lvl', 'save':None,      'auto_hit':True, 'dmg':None,    'effect':'polymorph','desc':'Take any creature form. Gain movement, AC, attacks.'},
    {'name':'Remove Curse',       'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'curse',    'desc':'Remove one curse. Reversed: Bestow Curse.'},
    {'name':'Wall of Fire',       'range':'60ft', 'duration':'Concentration','save':None,     'auto_hit':True, 'dmg':'2d6+1', 'effect':'damage',   'desc':'Fire wall. 2d6+1 to pass through, 1d6 within 10ft.'},
    {'name':'Wizard Eye',         'range':'240ft','duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Invisible eye moves at 30ft/round.'},
  ],
  5: [
    {'name':'Animate Dead',       'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'undead',   'desc':'Raise 1 HD of skeletons or zombies per level.'},
    {'name':'Cloudkill',          'range':'Self', 'duration':'1 turn',      'save':'Death',   'auto_hit':False,'dmg':None,    'effect':'poison',   'desc':'Poisonous cloud. Creatures <5 HD die. 5-6 HD: save vs Death.'},
    {'name':'Conjure Elemental',  'range':'240ft','duration':'Concentration','save':None,     'auto_hit':True, 'dmg':None,    'effect':'summon',   'desc':'Summon 16 HD elemental. Must concentrate or it attacks caster.'},
    {'name':'Feeblemind',         'range':'240ft','duration':'Permanent',   'save':'Spells-4','auto_hit':False,'dmg':None,    'effect':'debuff',   'desc':'INT reduced to 2. MUs save at -4.'},
    {'name':'Hold Monster',       'range':'120ft','duration':'1 turn/lvl',  'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'hold',     'desc':'1-4 creatures paralysed.'},
    {'name':'Pass-Wall',          'range':'30ft', 'duration':'3 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'5ft diameter tunnel through up to 10ft of stone.'},
    {'name':'Telekinesis',        'range':'120ft','duration':'2 rounds/lvl','save':None,      'auto_hit':True, 'dmg':None,    'effect':'move',     'desc':'Move 200 lbs/level at 20ft/round.'},
    {'name':'Teleport',           'range':'Touch','duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'teleport', 'desc':'Instant transport to known location. Error chance if unfamiliar.'},
    {'name':'Wall of Stone',      'range':'60ft', 'duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'terrain',  'desc':'Stone wall 2in thick/level, up to 1,000 sq ft.'},
  ],
  6: [
    {'name':'Anti-Magic Shell',   'range':'Self', 'duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'antimagic','desc':'10ft sphere blocks all magic. Caster cannot cast inside.'},
    {'name':'Death Spell',        'range':'240ft','duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':'4d8',   'effect':'damage',   'desc':'Up to 4d8 HD of creatures 8 HD or fewer die instantly.'},
    {'name':'Disintegrate',       'range':'60ft', 'duration':'Instant',     'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'destroy',  'desc':'One target or 10ft cube of non-magical matter destroyed.'},
    {'name':'Geas',               'range':'30ft', 'duration':'Until fulfilled','save':'Spells','auto_hit':False,'dmg':None,   'effect':'compel',   'desc':'Compel creature to complete quest. Disobedience causes penalties.'},
    {'name':'Invisible Stalker',  'range':'Self', 'duration':'Until done',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'summon',   'desc':'Summon extraplanar hunter to track/attack named target.'},
    {'name':'Move Earth',         'range':'240ft','duration':'6 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'terrain',  'desc':'Move dirt/clay/sand. One 60ft cube per turn.'},
    {'name':'Reincarnation',      'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'raise',    'desc':'Return dead character in new body (random form).'},
    {'name':'Stone to Flesh',     'range':'120ft','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'transform','desc':'Reverse petrification. Reversed: Flesh to Stone.'},
  ],
}

CLERIC_SPELLS = {
  1: [
    {'name':'Cure Light Wounds',  'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':'1d6+1', 'effect':'heal',     'desc':'Restore 1d6+1 HP. Reversed: Cause Light Wounds.'},
    {'name':'Detect Evil',        'range':'60ft', 'duration':'6 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Detect evil intentions or enchantments.'},
    {'name':'Detect Magic',       'range':'60ft', 'duration':'2 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Detect magical auras.'},
    {'name':'Light',              'range':'60ft', 'duration':'6 turns+1/lvl','save':'Spells', 'auto_hit':False,'dmg':None,    'effect':'light',    'desc':'15ft radius light. Reversed: Darkness.'},
    {'name':'Protection from Evil','range':'Touch','duration':'2 turns/lvl','save':None,      'auto_hit':True, 'dmg':None,    'effect':'protect',  'desc':'+1 AC and saves vs evil creatures.'},
    {'name':'Purify Food & Water','range':'10ft', 'duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Make spoiled food/water safe.'},
    {'name':'Remove Fear',        'range':'Touch','duration':'Special',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'morale',   'desc':'Remove fear. +1/level on re-save. Reversed: Cause Fear.'},
    {'name':'Resist Cold',        'range':'30ft', 'duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'resist',   'desc':'Unharmed by normal cold. +3 saves vs magical cold.'},
  ],
  2: [
    {'name':'Bless',              'range':'60ft', 'duration':'6 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'buff',     'desc':'+1 attack rolls and morale for allies. Reversed: Bane.'},
    {'name':'Find Traps',         'range':'30ft', 'duration':'2 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Detect traps within 30ft.'},
    {'name':'Hold Person',        'range':'180ft','duration':'9 turns',     'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'hold',     'desc':'Paralysed 1-3 humanoids. Save vs Spells.'},
    {'name':'Know Alignment',     'range':'10ft', 'duration':'1 round',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Learn exact alignment of one creature.'},
    {'name':'Resist Fire',        'range':'30ft', 'duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'resist',   'desc':'Unharmed by normal fire. +2 saves vs magical fire.'},
    {'name':'Silence 15ft Radius','range':'180ft','duration':'12 turns',   'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'silence',  'desc':'No sound in area. Casters inside cannot cast verbal spells.'},
    {'name':'Snake Charm',        'range':'60ft', 'duration':'Special',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'charm',    'desc':'Charm 1 HD of snakes per level.'},
    {'name':'Speak with Animals', 'range':'30ft', 'duration':'6 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'communicate','desc':'Communicate with natural animals.'},
  ],
  3: [
    {'name':'Cure Disease',       'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'heal',     'desc':'Cure one disease. Reversed: Cause Disease.'},
    {'name':'Growth of Animals',  'range':'120ft','duration':'12 turns',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'buff',     'desc':'Double size of up to 12 animals.'},
    {'name':'Locate Object',      'range':'90ft+10/lvl','duration':'1 round/lvl','save':None, 'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'Sense direction to known object type.'},
    {'name':'Remove Curse',       'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'curse',    'desc':'Remove one curse. Reversed: Bestow Curse.'},
    {'name':'Striking',           'range':'Touch','duration':'1 turn',      'save':None,      'auto_hit':True, 'dmg':'1d6',   'effect':'buff',     'desc':'+1d6 damage to weapon. Counts as magical.'},
    {'name':'Continual Light',    'range':'120ft','duration':'Permanent',   'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'light',    'desc':'Permanent 30ft radius light.'},
  ],
  4: [
    {'name':'Create Water',       'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Create 50 gallons per level.'},
    {'name':'Cure Serious Wounds','range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':'2d6+2', 'effect':'heal',     'desc':'Restore 2d6+2 HP.'},
    {'name':'Neutralize Poison',  'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'heal',     'desc':'Neutralize poison. Reversed: Poison (save vs Poison or die).'},
    {'name':'Protection from Evil 10ft Radius','range':'Touch','duration':'2 turns/lvl','save':None,'auto_hit':True,'dmg':None,'effect':'protect', 'desc':'Protection from Evil for all in 10ft radius.'},
    {'name':'Speak with Plants',  'range':'30ft', 'duration':'3 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'communicate','desc':'Communicate with plants.'},
    {'name':'Sticks to Snakes',   'range':'120ft','duration':'6 turns',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'summon',   'desc':'2d8 sticks become snakes (50% venomous).'},
    {'name':'Tongues',            'range':'Self', 'duration':'1 turn',      'save':None,      'auto_hit':True, 'dmg':None,    'effect':'communicate','desc':'Understand and speak any language.'},
  ],
  5: [
    {'name':'Commune',            'range':'Self', 'duration':'3 questions', 'save':None,      'auto_hit':True, 'dmg':None,    'effect':'divine',   'desc':'Ask deity 3 yes/no questions. Once per week.'},
    {'name':'Create Food',        'range':'Touch','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Food for 24 humans per level.'},
    {'name':'Cure Critical Wounds','range':'Touch','duration':'Permanent',  'save':None,      'auto_hit':True, 'dmg':'3d6+3', 'effect':'heal',     'desc':'Restore 3d6+3 HP.'},
    {'name':'Dispel Evil',        'range':'30ft', 'duration':'Instant',     'save':'Spells',  'auto_hit':False,'dmg':None,    'effect':'dispel',   'desc':'Dispel evil creature or enchantment.'},
    {'name':'Insect Plague',      'range':'480ft','duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'damage',   'desc':'Swarm 60ft diameter. <3 HD flee. Others -2 attack.'},
    {'name':'Quest',              'range':'30ft', 'duration':'Until fulfilled','save':'Spells','auto_hit':False,'dmg':None,   'effect':'compel',   'desc':'Target must complete quest. Disobedience causes -1/day.'},
    {'name':'Raise Dead',         'range':'120ft','duration':'Permanent',   'save':None,      'auto_hit':True, 'dmg':None,    'effect':'raise',    'desc':'Restore life. 1 day/level since death limit.'},
    {'name':'True Seeing',        'range':'120ft','duration':'1 round/lvl', 'save':None,      'auto_hit':True, 'dmg':None,    'effect':'detect',   'desc':'See invisible, illusions, and actual forms.'},
  ],
  6: [
    {'name':'Animate Objects',    'range':'60ft', 'duration':'1 round/lvl', 'save':None,      'auto_hit':True, 'dmg':None,    'effect':'animate',  'desc':'Animate non-living objects to fight.'},
    {'name':'Blade Barrier',      'range':'30ft', 'duration':'3 rounds/lvl','save':None,      'auto_hit':True, 'dmg':'2d6',   'effect':'damage',   'desc':'Wall of blades. 2d6 to pass through.'},
    {'name':'Find the Path',      'range':'Touch','duration':'1 turn/lvl',  'save':None,      'auto_hit':True, 'dmg':None,    'effect':'utility',  'desc':'Know shortest route to destination.'},
    {'name':'Speak with Monsters','range':'30ft', 'duration':'1 round/lvl', 'save':None,      'auto_hit':True, 'dmg':None,    'effect':'communicate','desc':'Communicate with any creature.'},
    {'name':'Word of Recall',     'range':'Self', 'duration':'Instant',     'save':None,      'auto_hit':True, 'dmg':None,    'effect':'teleport', 'desc':'Instantly return to sanctuary.'},
  ],
}

ALL_SPELLS = {}  # populated below
for lvl, spells in MU_SPELLS.items():
    for sp in spells: ALL_SPELLS[sp['name']] = {**sp, 'level':lvl, 'type':'mu'}
for lvl, spells in CLERIC_SPELLS.items():
    for sp in spells: ALL_SPELLS[sp['name']] = {**sp, 'level':lvl, 'type':'cleric'}

def get_spell(name):
    return ALL_SPELLS.get(name)

def resolve_spell(caster_pc, spell_name, target_info, game_state):
    """
    Full server-side spell resolution.
    Returns MechanicalResult dict.
    """
    spell = get_spell(spell_name)
    if not spell:
        return {'error': f"Spell '{spell_name}' not found in OSE AF spell list."}

    result = {
        'spell': spell_name,
        'caster': caster_pc.get('name'),
        'level': spell['level'],
        'effect': spell.get('effect','unknown'),
        'hit': False,
        'damage': 0,
        'damage_detail': '',
        'save_result': None,
        'display_lines': [],
        'state_changes': {},
    }

    caster_level = caster_pc.get('level', 1)
    stats = caster_pc.get('stats', {})

    # ── Handle by effect type ──
    effect = spell.get('effect','')

    if effect == 'damage':
        dmg_expr = spell.get('dmg','1d6')
        if '/lvl' in dmg_expr:
            base = dmg_expr.replace('/lvl','')
            n = caster_level
            total = 0; details = []
            for _ in range(n):
                v, d = roll_expr(base)
                total += v; details.append(str(v))
            dmg_total = total
            dmg_detail = f"{n}×{base}=[{','.join(details)}]={dmg_total}"
        else:
            dmg_total, dmg_detail = roll_expr(dmg_expr)

        # Saving throw
        save_cat = spell.get('save')
        if save_cat and target_info.get('can_save', True):
            target_pc = target_info.get('pc')
            if target_pc:
                suc, sroll, starget, sdetail = resolve_saving_throw(target_pc, 'spells')
                if suc: dmg_total = dmg_total // 2
                result['save_result'] = sdetail
                result['display_lines'].append(sdetail)

        result['hit'] = True
        result['damage'] = dmg_total
        result['damage_detail'] = dmg_detail
        result['display_lines'].insert(0, f"SPELL: {spell_name} — DAMAGE: {dmg_detail} = {dmg_total}")

    elif effect == 'heal':
        dmg_expr = spell.get('dmg','1d6+1')
        heal_total, heal_detail = roll_expr(dmg_expr)
        result['hit'] = True
        result['damage'] = -heal_total  # negative = healing
        result['damage_detail'] = heal_detail
        result['display_lines'].append(f"SPELL: {spell_name} — HEALS: {heal_detail} = {heal_total} HP")
        result['state_changes']['heal'] = heal_total

    elif effect == 'sleep':
        hd_total, hd_detail = roll_expr('2d8')
        result['hit'] = True
        result['display_lines'].append(f"SPELL: Sleep — 2d8={hd_detail}: {hd_total} HD of creatures fall asleep (lowest HD first, max 4 HD each, no save)")
        result['state_changes']['sleep_hd'] = hd_total

    elif effect in ('charm','hold','confuse','compel'):
        auto_hit = spell.get('auto_hit', False)
        result['hit'] = True
        save_cat = spell.get('save')
        if save_cat:
            mod = -4 if save_cat == 'Spells-4' else 0
            result['display_lines'].append(f"SPELL: {spell_name} — Target must save vs Spells{' at -4' if mod else ''} or be {effect}ed for {spell.get('duration','Special')}")
        else:
            result['display_lines'].append(f"SPELL: {spell_name} — {effect.upper()} effect, no save: {spell.get('duration','Special')}")

    elif effect == 'magic_missile':
        missiles = 1 + max(0, (caster_level - 1) // 2)
        total = 0; details = []
        for _ in range(missiles):
            v, d = roll_expr('1d6+1')
            total += v; details.append(str(v))
        result['hit'] = True
        result['damage'] = total
        result['damage_detail'] = f"{missiles} missiles: [{','.join(details)}]={total}"
        result['display_lines'].append(f"SPELL: Magic Missile — {missiles} missile(s), auto-hit: {result['damage_detail']}")

    else:
        result['hit'] = True
        result['display_lines'].append(f"SPELL: {spell_name} ({effect}) — {spell.get('desc','')}")

    return result

# ── OSE WEAPONS ───────────────────────────────────────────────────────────────
OSE_WEAPONS = {
    'Battle Axe':       {'dmg':'1d8',  'cost':7,   'hands':1,'ranged':False,'ammo':None},
    'Club':             {'dmg':'1d4',  'cost':0,   'hands':1,'ranged':False,'ammo':None},
    'Dagger':           {'dmg':'1d4',  'cost':3,   'hands':1,'ranged':False,'ammo':None,'throwable':True},
    'Hand Axe':         {'dmg':'1d6',  'cost':4,   'hands':1,'ranged':False,'ammo':None,'throwable':True},
    'Lance':            {'dmg':'1d6',  'cost':10,  'hands':1,'ranged':False,'ammo':None,'mounted':True},
    'Mace':             {'dmg':'1d6',  'cost':5,   'hands':1,'ranged':False,'ammo':None},
    'Pole Arm':         {'dmg':'1d10', 'cost':7,   'hands':2,'ranged':False,'ammo':None,'two_handed':True},
    'Short Sword':      {'dmg':'1d6',  'cost':7,   'hands':1,'ranged':False,'ammo':None},
    'Silver Dagger':    {'dmg':'1d4',  'cost':30,  'hands':1,'ranged':False,'ammo':None,'silver':True,'throwable':True},
    'Spear':            {'dmg':'1d6',  'cost':3,   'hands':1,'ranged':False,'ammo':None,'throwable':True},
    'Staff':            {'dmg':'1d6',  'cost':0,   'hands':2,'ranged':False,'ammo':None,'two_handed':True},
    'Sword':            {'dmg':'1d8',  'cost':10,  'hands':1,'ranged':False,'ammo':None},
    'Two-Handed Sword': {'dmg':'1d10', 'cost':15,  'hands':2,'ranged':False,'ammo':None,'two_handed':True},
    'War Hammer':       {'dmg':'1d6',  'cost':5,   'hands':1,'ranged':False,'ammo':None},
    # Ranged
    'Crossbow':         {'dmg':'1d6',  'cost':30,  'hands':2,'ranged':True, 'ammo':'Crossbow Bolts','range':(80,160,240)},
    'Javelin':          {'dmg':'1d6',  'cost':1,   'hands':1,'ranged':True, 'ammo':None,'throwable':True,'range':(30,60,90)},
    'Long Bow':         {'dmg':'1d6',  'cost':60,  'hands':2,'ranged':True, 'ammo':'Arrows','range':(70,140,210)},
    'Short Bow':        {'dmg':'1d6',  'cost':25,  'hands':2,'ranged':True, 'ammo':'Arrows','range':(50,100,150)},
    'Sling':            {'dmg':'1d4',  'cost':2,   'hands':1,'ranged':True, 'ammo':'Sling Stones','range':(40,80,160)},
    # Unarmed (Monk)
    'Unarmed':          {'dmg':'1d2',  'cost':0,   'hands':0,'ranged':False,'ammo':None},
}

MONK_UNARMED_DMG = ['1d4','1d4','1d6','1d6','1d8','1d8','1d8','1d10','1d10','2d6','2d6','2d8','2d8','3d6']

# ── OSE ARMOUR ────────────────────────────────────────────────────────────────
OSE_ARMOUR = {
    'Leather Armour': {'ac':7, 'cost':20},   # descending AC
    'Chain Mail':     {'ac':5, 'cost':40},
    'Plate Mail':     {'ac':3, 'cost':60},
    'Shield':         {'ac_bonus':1, 'cost':10},
}

# ── OSE EQUIPMENT ─────────────────────────────────────────────────────────────
OSE_EQUIPMENT = {
    'Backpack':                  {'cost':5,  'wt':1},
    'Crowbar':                   {'cost':10, 'wt':5},
    'Garlic':                    {'cost':5,  'wt':0},
    'Grappling Hook':            {'cost':25, 'wt':4},
    'Hammer (small)':            {'cost':2,  'wt':2},
    'Holy Symbol':               {'cost':25, 'wt':0},
    'Holy Water (vial)':         {'cost':25, 'wt':0,'uses':1,'effect':'damage_undead','dmg':'2d4'},
    'Iron Spikes (12)':          {'cost':1,  'wt':5},
    'Lantern':                   {'cost':10, 'wt':2,'light':True,'turns_per_flask':24},
    'Mirror (hand-sized, steel)':{'cost':5,  'wt':0},
    'Oil (1 flask)':             {'cost':2,  'wt':1,'fuel':True,'turns':24},
    'Pole (10ft wooden)':        {'cost':1,  'wt':5},
    'Rations (iron, 7 days)':    {'cost':15, 'wt':5,'rations':7},
    'Rations (standard, 7 days)':{'cost':5,  'wt':3,'rations':7},
    'Rope (50ft)':               {'cost':1,  'wt':5},
    'Sack (large)':              {'cost':2,  'wt':1},
    'Sack (small)':              {'cost':1,  'wt':0},
    'Stakes (3) and Mallet':     {'cost':3,  'wt':3},
    "Thieves' Tools":            {'cost':25, 'wt':1,'required_for':'thief_skills'},
    'Tinder Box (flint & steel)':{'cost':3,  'wt':0},
    'Torches (6)':               {'cost':1,  'wt':3,'light':True,'turns_per':6,'count':6},
    'Waterskin':                 {'cost':1,  'wt':1},
    'Wine (2 pints)':            {'cost':1,  'wt':1},
    'Wolfsbane (1 bunch)':       {'cost':10, 'wt':0},
}

# Ammo
OSE_AMMO = {
    'Arrows (20)':              {'cost':5,  'count':20,'for':['Long Bow','Short Bow']},
    'Crossbow Bolts (30)':      {'cost':10, 'count':30,'for':['Crossbow']},
    'Silver-Tipped Arrows (6)': {'cost':30, 'count':6, 'for':['Long Bow','Short Bow'],'silver':True},
    'Sling Stones (20)':        {'cost':0,  'count':20,'for':['Sling']},
}

# ── MAGIC ITEMS ───────────────────────────────────────────────────────────────
MAGIC_ITEMS = {
    'Sword +1':                {'cat':'weapon','bonus':1,  'base':'Sword'},
    'Sword +2':                {'cat':'weapon','bonus':2,  'base':'Sword'},
    'Sword +3':                {'cat':'weapon','bonus':3,  'base':'Sword'},
    'Dagger +1':               {'cat':'weapon','bonus':1,  'base':'Dagger'},
    'Dagger +2':               {'cat':'weapon','bonus':2,  'base':'Dagger'},
    'Battle Axe +1':           {'cat':'weapon','bonus':1,  'base':'Battle Axe'},
    'War Hammer +1':           {'cat':'weapon','bonus':1,  'base':'War Hammer'},
    'Bow +1':                  {'cat':'weapon','bonus':1,  'base':'Short Bow','ranged':True},
    'Arrow +1':                {'cat':'ammo',  'bonus':1,  'single_use':True},
    'Arrow +2':                {'cat':'ammo',  'bonus':2,  'single_use':True},
    'Armour +1':               {'cat':'armour','ac_bonus':1},
    'Armour +2':               {'cat':'armour','ac_bonus':2},
    'Shield +1':               {'cat':'armour','ac_bonus':1,'is_shield':True},
    'Ring of Protection +1':   {'cat':'ring',  'ac_bonus':1,'save_bonus':1},
    'Ring of Protection +2':   {'cat':'ring',  'ac_bonus':2,'save_bonus':2},
    'Ring of Invisibility':    {'cat':'ring',  'effect':'invisibility'},
    'Ring of Fire Resistance': {'cat':'ring',  'effect':'fire_resistance'},
    'Ring of Regeneration':    {'cat':'ring',  'effect':'regeneration','rate':1},
    'Potion of Healing':       {'cat':'potion','effect':'heal',    'dmg':'1d6+1','single_use':True},
    'Potion of Extra Healing': {'cat':'potion','effect':'heal',    'dmg':'3d6+3','single_use':True},
    'Potion of Invisibility':  {'cat':'potion','effect':'invisible','duration':10,'single_use':True},
    'Potion of Speed':         {'cat':'potion','effect':'haste',   'duration':3, 'single_use':True},
    'Potion of Giant Strength':{'cat':'potion','effect':'stat',    'stat':'STR','add':8,'duration':1,'single_use':True},
    'Potion of Heroism':       {'cat':'potion','effect':'heroism', 'levels':4,'duration':1,'single_use':True},
    'Potion of Flying':        {'cat':'potion','effect':'fly',     'speed':120,'duration':0,'single_use':True},
    'Potion of Gaseous Form':  {'cat':'potion','effect':'gaseous', 'single_use':True},
    'Potion of Climbing':      {'cat':'potion','effect':'climb',   'duration':1,'single_use':True},
    'Potion of Fire Resistance':{'cat':'potion','effect':'fire_res','duration':1,'single_use':True},
    'Scroll of Protection from Undead':  {'cat':'scroll','effect':'protection','target':'undead','duration':6,'single_use':True},
    'Scroll of Protection from Magic':   {'cat':'scroll','effect':'antimagic', 'duration':1,'single_use':True},
    'Wand of Magic Missiles':  {'cat':'wand','charges':25,'spell':'Magic Missile'},
    'Wand of Fireballs':       {'cat':'wand','charges':20,'spell':'Fireball'},
    'Wand of Lightning Bolts': {'cat':'wand','charges':20,'spell':'Lightning Bolt'},
    'Wand of Fear':            {'cat':'wand','charges':25,'effect':'fear','save':'Wands'},
    'Wand of Paralysis':       {'cat':'wand','charges':25,'effect':'paralysis','save':'Wands'},
    'Staff of Healing':        {'cat':'staff','charges':50,'spell':'Cure Light Wounds'},
    'Staff of Striking':       {'cat':'staff','charges':25,'effect':'bonus_damage','dmg':'2d6'},
}

def apply_magic_item(item_name, pc, target_pc=None):
    """Apply magic item effect. Returns (success, result_dict)."""
    item = MAGIC_ITEMS.get(item_name)
    if not item:
        return False, {'error': f"'{item_name}' is not a known magic item."}

    result = {'item': item_name, 'effect': item.get('effect',''), 'display': '', 'state_changes': {}}

    if item['cat'] == 'potion':
        effect = item.get('effect')
        if effect == 'heal':
            heal, detail = roll_expr(item['dmg'])
            result['display'] = f"POTION: {item_name} — Heals {detail} = {heal} HP"
            result['state_changes']['heal'] = heal
        elif effect == 'stat':
            result['display'] = f"POTION: {item_name} — +{item['add']} {item['stat']} for {item.get('duration',1)} turn(s)"
            result['state_changes']['stat_bonus'] = {item['stat']: item['add'], 'turns': item.get('duration',1)}
        elif effect == 'invisible':
            result['display'] = f"POTION: {item_name} — Invisible for {item.get('duration',10)} turns or until attacking"
            result['state_changes']['invisible'] = True
        elif effect == 'haste':
            result['display'] = f"POTION: {item_name} — Double movement and attacks for {item.get('duration',3)} turns. Ages you 1 year."
            result['state_changes']['haste'] = item.get('duration',3)
        else:
            result['display'] = f"POTION: {item_name} — {effect} effect applied"

    elif item['cat'] in ('scroll','wand','staff'):
        spell_name = item.get('spell')
        if spell_name and target_pc:
            spell_result = resolve_spell(pc, spell_name, {'pc': target_pc}, {})
            result['display'] = f"ITEM: {item_name} — {spell_result.get('display_lines',[''])[0]}"
            result['state_changes'] = spell_result.get('state_changes',{})
        else:
            result['display'] = f"ITEM: {item_name} — charges expended"

    return True, result

# ── RACIAL ABILITIES ──────────────────────────────────────────────────────────
RACIAL_ABILITIES = {
    'Human':     {'detect_secret':None,'infravision':0,'surprise_bonus':0,
                  'passives':['No level limits','Bonus languages equal to INT modifier']},
    'Elf':       {'detect_secret_pass':2,'detect_secret_search':4,'infravision':60,
                  'immune_ghoul_paralysis':True,'attack_bonus':{'Sword':1,'Long Bow':1,'Short Bow':1},
                  'passives':['Detect secret doors 1-2/d6 passing, 1-4/d6 searching','Immune to ghoul paralysis','+1 to hit with swords and bows']},
    'Dwarf':     {'detect_stonework_pass':2,'detect_stonework_search':4,'infravision':60,
                  'save_bonus':{'poison':4,'paralysis':4,'petrification':4,'wands':4},
                  'attack_bonus_vs':{'goblinoid':1,'giant':1},
                  'passives':['Detect stonework tricks 1-2/d6 pass, 1-4/d6 search','+4 saves vs poison/paralysis/petrification/wands','+1 to hit goblinoids and giants']},
    'Halfling':  {'hide_outdoors':90,'surprise_indoors':2,'surprise_outdoors':3,
                  'attack_bonus':{'ranged':1},'size':'small',
                  'passives':['Hide in natural surroundings 90%','Surprise attackers outdoors 1-3/d6','+1 to ranged attacks','Cannot use two-handed or large weapons']},
    'Gnome':     {'infravision':90,'detect_underground_pass':3,'detect_underground_search':3,
                  'save_bonus':{'illusion':4},'attack_bonus_vs':{'goblinoid':1},
                  'passives':['Infravision 90ft','Detect underground features 1-3/d6','+4 saves vs illusions','+1 vs goblinoids']},
    'Half-Elf':  {'detect_secret_pass':2,'infravision':60,'immune_ghoul_paralysis':True,
                  'passives':['Detect secret doors 1-2/d6 passing','Infravision 60ft','Immune to ghoul paralysis']},
    'Half-Orc':  {'infravision':60,
                  'passives':['Infravision 60ft']},
}

# ── CLASS ABILITIES BY LEVEL ──────────────────────────────────────────────────
CLASS_LEVEL_ABILITIES = {
    'Fighter': {
        4:  [{'name':'Extra Attack','desc':'3 attacks per 2 rounds','type':'passive'}],
        8:  [{'name':'Extra Attack','desc':'2 attacks per round','type':'passive'}],
        12: [{'name':'Extra Attack','desc':'5 attacks per 2 rounds','type':'passive'}],
    },
    'Paladin': {
        1:  [{'name':'Detect Evil','desc':'Detect evil within 60ft at will (1 round concentration)','type':'active','uses':'at_will'},
             {'name':'Lay on Hands','desc':'Heal 2 HP per paladin level per day (total pool)','type':'active','uses':'pool','pool_per_level':2},
             {'name':'Disease Immunity','desc':'Immune to all diseases','type':'passive'},
             {'name':'Protection Aura','desc':'+1 AC and saves for all allies within 10ft','type':'passive'}],
        3:  [{'name':'Turn Undead','desc':'Turn undead as Cleric 2 levels lower','type':'active','uses':'unlimited'}],
        4:  [{'name':'Warhorse','desc':'Summon loyal warhorse (4+4 HD)','type':'active','uses':'1/week'}],
        9:  [{'name':'Cleric Spells','desc':'Cast Cleric spells as Cleric 3 levels lower','type':'passive'}],
    },
    'Cleric': {
        1:  [{'name':'Turn Undead','desc':'Turn undead using 2d6 vs Turn table','type':'active','uses':'unlimited'}],
    },
    'Ranger': {
        1:  [{'name':'Tracking','desc':'Track creatures: 1-2/d6 success outdoors, 1-4 fresh trail','type':'active','uses':'unlimited'},
             {'name':'Outdoor Surprise','desc':'Surprise creatures on 1-3 on d6 outdoors','type':'passive'},
             {'name':'Favoured Enemy','desc':'+1 to attack and damage vs chosen creature type','type':'passive'}],
        8:  [{'name':'Druid Spells','desc':'Cast Druid spells levels 1-3','type':'passive'}],
        10: [{'name':'MU Spells','desc':'Cast Magic-User spells levels 1-2','type':'passive'}],
    },
    'Barbarian': {
        1:  [{'name':'Rage','desc':'+2 attack/damage, -2 AC for 3 rounds. Cannot end voluntarily.','type':'active','uses':'1_per_day'},
             {'name':'Trap Sense','desc':'+2 to saving throws vs traps','type':'passive'},
             {'name':'Illiteracy','desc':'Cannot read. Cannot use scrolls.','type':'passive'}],
        4:  [{'name':'Rage','desc':'Rage usable 2/day','type':'active','uses':'2_per_day'}],
        7:  [{'name':'Rage','desc':'Rage usable 3/day','type':'active','uses':'3_per_day'},
             {'name':'Intimidate','desc':'As Fear spell 1/day','type':'active','uses':'1_per_day'}],
        10: [{'name':'Rage','desc':'Rage usable 4/day','type':'active','uses':'4_per_day'}],
    },
    'Thief': {
        1:  [{'name':'Backstab','desc':'Attack from hiding: x2 damage mult','type':'active','uses':'per_hidden_attack'}],
        5:  [{'name':'Backstab','desc':'x3 damage backstab','type':'active','uses':'per_hidden_attack'},
             {'name':'Read Languages','desc':'Read languages at skill table percentage','type':'active','uses':'unlimited'}],
        9:  [{'name':'Backstab','desc':'x4 damage backstab','type':'active','uses':'per_hidden_attack'}],
        13: [{'name':'Backstab','desc':'x5 damage backstab','type':'active','uses':'per_hidden_attack'}],
    },
    'Assassin': {
        1:  [{'name':'Backstab','desc':'x2 damage backstab from hiding','type':'active','uses':'per_hidden_attack'},
             {'name':'Disguise','desc':'Disguise self (base 70% success + DEX mod)','type':'active','uses':'unlimited'},
             {'name':'Poison Use','desc':'Use poisons without risk of self-harm','type':'passive'}],
        5:  [{'name':'Backstab','desc':'x3 backstab','type':'active','uses':'per_hidden_attack'}],
        9:  [{'name':'Backstab','desc':'x4 backstab','type':'active','uses':'per_hidden_attack'},
             {'name':'Assassinate','desc':'Instant kill surprised targets (save vs Death)','type':'active','uses':'per_surprised_victim'}],
        13: [{'name':'Backstab','desc':'x5 backstab','type':'active','uses':'per_hidden_attack'}],
    },
    'Druid': {
        1:  [{'name':'Druid Lore','desc':'Identify plants, animals, pure water automatically','type':'passive'},
             {'name':'Pass Without Trace','desc':'Leave no tracks in natural environments','type':'passive'}],
        7:  [{'name':'Shapechange','desc':'Polymorph into 1 animal form per 3 levels, 3/day','type':'active','uses':'3_per_day'}],
    },
    'Bard': {
        1:  [{'name':'Inspire Courage','desc':'+1 attack and saves for allies who can hear. Lasts during performance + 5 rounds.','type':'active','uses':'concentration'},
             {'name':'Bard Lore','desc':'1-2 on d6 to know legend, history, or identify magic item by handling','type':'active','uses':'unlimited'},
             {'name':'Counter Song','desc':'Counter magical songs/sounds. Allies within 30ft +4 saves.','type':'active','uses':'concentration'}],
        2:  [{'name':'Charm Person','desc':'Charm Person 1/day as the spell','type':'active','uses':'1_per_day'}],
        4:  [{'name':'Suggestion','desc':'Suggestion 1/day as the spell','type':'active','uses':'1_per_day'}],
        7:  [{'name':'Legend Lore','desc':'Identify magic items by handling (1 hour)','type':'active','uses':'unlimited'}],
        10: [{'name':'Mass Suggestion','desc':'Suggestion for up to 2 creatures/level, 1/day','type':'active','uses':'1_per_day'}],
    },
    'Monk': {
        1:  [{'name':'Stunning Attack','desc':'On hit: target saves vs Death or stunned 1d6 rounds','type':'active','uses':'1_per_round'},
             {'name':'Slow Fall','desc':'Near wall: negate fall damage up to 20ft','type':'passive'}],
        5:  [{'name':'Speak with Animals','desc':'Speak with Animals 1/day','type':'active','uses':'1_per_day'}],
        7:  [{'name':'Wholeness of Body','desc':'Heal self 2 HP/level once per day','type':'active','uses':'1_per_day'}],
    },
}

def get_class_abilities_for_level(cls, level):
    """Returns list of all abilities available at given level."""
    tbl = CLASS_LEVEL_ABILITIES.get(cls, {})
    result = []
    for req_level, abilities in sorted(tbl.items()):
        if level >= req_level:
            result.extend(abilities)
    return result

# ── COMBAT LOOP ───────────────────────────────────────────────────────────────
def combat_surprise_check(pc_stealth=False, monster_alertness='normal'):
    """
    OSE surprise check.
    Returns (pcs_surprised, monsters_surprised).
    """
    pc_surprised = False
    monster_surprised = False

    if not pc_stealth:
        pc_roll, _ = roll(6)
        pc_surprised = pc_roll <= 1  # PCs surprised on 1

    monster_roll, _ = roll(6)
    if monster_alertness == 'distracted':
        monster_surprised = monster_roll <= 2  # easier to surprise
    elif monster_alertness == 'alert':
        monster_surprised = False
    else:
        monster_surprised = monster_roll <= 1  # standard 1-in-6

    return pc_surprised, monster_surprised

def combat_initiative():
    """Roll initiative for both sides. Returns (pc_wins, pc_roll, monster_roll)."""
    pc_roll, _ = roll(6)
    monster_roll, _ = roll(6)
    # Ties go to players in OSE (or reroll — we give tie to player)
    pc_wins = pc_roll >= monster_roll
    return pc_wins, pc_roll, monster_roll

def get_monster_attack(monster):
    """Resolve a monster's attack. Returns result dict."""
    atk = monster.get('attack', '1')
    dmg_expr = monster.get('damage', '1d6')
    thac0 = monster.get('thac0', 20)
    # Monsters: d20 >= (THAC0 - target_AC)
    d20, _ = roll(20)
    dmg_total, dmg_detail = roll_expr(dmg_expr)
    return {
        'd20': d20,
        'thac0': thac0,
        'damage_expr': dmg_expr,
        'damage': dmg_total,
        'damage_detail': dmg_detail,
    }



# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B: LAYER 1 VALIDATOR
# Zero AI. Checks every action against game state before anything else runs.
# If this fails, the player gets an immediate rejection with a clear reason.
# No dice are rolled. No AI is called. No narrative is generated.
# ═══════════════════════════════════════════════════════════════════════════════

ACTION_TYPES = {
    'ATTACK':    'attack',
    'CAST':      'cast',
    'USE_ITEM':  'use_item',
    'MOVE':      'move',
    'SOCIAL':    'social',
    'SKILL':     'skill',
    'ABILITY':   'ability',
    'EXAMINE':   'examine',
    'REST':      'rest',
    'OTHER':     'other',
}

class ValidationResult:
    def __init__(self, valid, action_type=None, parsed=None, rejection=None, warning=None):
        self.valid = valid
        self.action_type = action_type
        self.parsed = parsed or {}   # structured info extracted without AI
        self.rejection = rejection   # shown to player if invalid
        self.warning = warning       # shown but doesn't block action

    def to_dict(self):
        return {
            'valid': self.valid,
            'action_type': self.action_type,
            'parsed': self.parsed,
            'rejection': self.rejection,
            'warning': self.warning,
        }

def validate_action(text, pc, game_state):
    """
    Master validator. Runs all Layer 1 checks.
    Returns ValidationResult.

    pc: dict with keys: name, cls, level, hp, maxhp, stats, inv, gold,
        spell_slots_remaining, spellbook, memorized_spells, active_effects,
        conditions, abilities_used_today, wand_charges, equipped_magic
    game_state: dict with keys: in_combat, current_encounter, module_data,
                current_room, npcs_present, objects_present
    """
    text_lower = text.lower().strip()

    # ── 1. SPELL CASTING CHECK ────────────────────────────────────────────────
    spell_detected = _detect_spell_action(text_lower)
    if spell_detected:
        return _validate_spell(spell_detected, pc, game_state, text_lower)

    # ── 2. ATTACK CHECK ───────────────────────────────────────────────────────
    attack_detected = _detect_attack_action(text_lower)
    if attack_detected:
        return _validate_attack(attack_detected, pc, game_state, text_lower)

    # ── 3. ITEM USE CHECK ─────────────────────────────────────────────────────
    item_detected = _detect_item_action(text_lower)
    if item_detected:
        return _validate_item(item_detected, pc, game_state)

    # ── 4. THIEF SKILL CHECK ──────────────────────────────────────────────────
    skill_detected = _detect_skill_action(text_lower)
    if skill_detected:
        return _validate_skill(skill_detected, pc, game_state)

    # ── 5. CLASS ABILITY CHECK ────────────────────────────────────────────────
    ability_detected = _detect_ability_action(text_lower, pc)
    if ability_detected:
        return _validate_ability(ability_detected, pc, game_state)

    # ── 6. PHYSICALLY IMPOSSIBLE ACTIONS ─────────────────────────────────────
    impossible = _check_physically_impossible(text_lower, pc, game_state)
    if impossible:
        return ValidationResult(False, rejection=impossible)

    # ── 7. MODULE CLOSED WORLD CHECK ─────────────────────────────────────────
    world_violation = _check_closed_world(text_lower, game_state)
    if world_violation:
        return ValidationResult(False, rejection=world_violation)

    # ── 8. Default: pass to AI for classification ─────────────────────────────
    return ValidationResult(True, action_type=ACTION_TYPES['OTHER'],
                            parsed={'raw_text': text})

# ── SPELL DETECTION & VALIDATION ─────────────────────────────────────────────
CAST_KEYWORDS = ['cast','memorize','use scroll','read scroll','use wand','fire wand',
                 'activate wand','use staff','activate staff']

def _detect_spell_action(text):
    """Returns spell name if a spell casting action is detected."""
    for kw in CAST_KEYWORDS:
        if kw in text:
            # Try to find spell name in text
            for spell_name in ALL_SPELLS:
                if spell_name.lower() in text:
                    return spell_name
            # No specific spell found but casting keyword used
            return '__unknown_spell__'
    return None

def _validate_spell(spell_name, pc, game_state, text):
    cls = pc.get('cls','Fighter')
    level = pc.get('level',1)
    spellbook = pc.get('spellbook', {})
    memorized = pc.get('memorized_spells', [])
    slots = pc.get('spell_slots_remaining', [])

    # Check if class can cast spells at all
    cd = OSE_CLASSES.get(cls, {})
    spell_type = cd.get('spells')
    if not spell_type:
        return ValidationResult(False,
            rejection=f"{pc.get('name','The character')} is a {cls}. {cls}s cannot cast spells.")

    # Check if class can cast spells at this level
    available_slots = get_spell_slots(cls, level)
    if not available_slots:
        return ValidationResult(False,
            rejection=f"{cls}s do not gain spells until a higher level.")

    if spell_name == '__unknown_spell__':
        return ValidationResult(False,
            rejection=f"That spell is not in the OSE Advanced Fantasy spell list.")

    # Check if spell exists for this class
    spell = get_spell(spell_name)
    if not spell:
        return ValidationResult(False,
            rejection=f"'{spell_name}' is not a spell in OSE Advanced Fantasy.")

    # Check spell type matches class
    valid_types = {'mu': ['mu','Magic-User','Illusionist'],
                   'cleric': ['cleric','Cleric','Druid','Paladin','Ranger'],
                   'druid':  ['druid','Druid','Ranger'],}
    spell_type_key = spell.get('type','mu')
    cls_type_key = cd.get('spells','mu')

    # Barbarian illiteracy — cannot use scrolls
    if cls == 'Barbarian' and 'scroll' in text:
        return ValidationResult(False,
            rejection=f"Barbarians are illiterate and cannot read or use scrolls.")

    # Check spell is in spellbook (MU/Illusionist must have learned it)
    if cls in ('Magic-User','Illusionist'):
        if spell_name not in spellbook:
            return ValidationResult(False,
                rejection=f"{spell_name} is not in {pc.get('name',cls)}'s spellbook. You must find or research this spell first.")

    # Check spell is memorized
    memorized_names = [s if isinstance(s,str) else s.get('name','') for s in memorized]
    if spell_name not in memorized_names:
        return ValidationResult(False,
            rejection=f"{spell_name} is not currently memorized. You must rest and re-memorize your spells.")

    # Check spell slot is available
    spell_level = spell.get('level',1)
    if len(slots) < spell_level or slots[spell_level-1] <= 0:
        return ValidationResult(False,
            rejection=f"No {_ordinal(spell_level)}-level spell slots remaining. Rest to recover spell slots.")

    # Check level restriction for partial casters
    if cls == 'Paladin':
        # Paladins get spells at level 9, as Cleric 3 levels lower
        if level < 9:
            return ValidationResult(False,
                rejection=f"Paladins do not gain spells until level 9.")
        effective_cleric_level = level - 3
        if spell_level > max(len(get_spell_slots('cleric', effective_cleric_level)),0):
            return ValidationResult(False,
                rejection=f"Paladin at level {level} cannot cast level {spell_level} spells yet.")

    if cls == 'Ranger':
        if level < 8:
            return ValidationResult(False,
                rejection=f"Rangers do not gain spells until level 8.")

    return ValidationResult(True, action_type=ACTION_TYPES['CAST'],
                            parsed={'spell_name': spell_name, 'spell': spell,
                                    'spell_level': spell_level})

# ── ATTACK DETECTION & VALIDATION ─────────────────────────────────────────────
ATTACK_KEYWORDS = ['attack','strike','hit','stab','slash','swing','shoot','fire',
                   'throw','hurl','launch','shoot','stab','pierce','cut','cleave',
                   'smash','bash','punch','kick','bite']

def _detect_attack_action(text):
    for kw in ATTACK_KEYWORDS:
        if kw in text.split() or f' {kw} ' in f' {text} ':
            # Find weapon mentioned
            for wname in OSE_WEAPONS:
                if wname.lower() in text:
                    return {'weapon': wname, 'keyword': kw}
            for mname in MAGIC_ITEMS:
                if mname.lower() in text:
                    base = MAGIC_ITEMS[mname].get('base')
                    return {'weapon': mname, 'base_weapon': base, 'keyword': kw,
                            'magic_bonus': MAGIC_ITEMS[mname].get('bonus',0)}
            # Attack keyword found but no weapon — assume unarmed or default weapon
            return {'weapon': None, 'keyword': kw}
    return None

def _validate_attack(detected, pc, game_state, text):
    inv = [i.lower() if isinstance(i,str) else i.get('name','').lower()
           for i in pc.get('inv',[])]
    cls = pc.get('cls','Fighter')
    level = pc.get('level',1)
    weapon_name = detected.get('weapon')
    magic_bonus = detected.get('magic_bonus',0)

    # If no weapon named, try to find equipped weapon in inventory
    if not weapon_name:
        # Monk: unarmed is always available
        if cls == 'Monk':
            unarmed_dmg = MONK_UNARMED_DMG[min(level-1,13)]
            return ValidationResult(True, action_type=ACTION_TYPES['ATTACK'],
                                    parsed={'weapon':'Unarmed','dmg':unarmed_dmg,
                                            'is_ranged':False,'magic_bonus':0})
        # Find first weapon in inventory
        for wname, wdata in OSE_WEAPONS.items():
            if wname.lower() in inv:
                weapon_name = wname
                break
        if not weapon_name:
            return ValidationResult(False,
                rejection=f"{pc.get('name','The character')} has no weapon equipped.")

    # Check weapon exists
    weapon = OSE_WEAPONS.get(weapon_name) or \
             (MAGIC_ITEMS.get(weapon_name) and
              OSE_WEAPONS.get(MAGIC_ITEMS[weapon_name].get('base','')))
    if not weapon:
        return ValidationResult(False,
            rejection=f"'{weapon_name}' is not a known weapon in OSE Advanced Fantasy.")

    # Check weapon is in inventory (including magic weapons)
    wname_lower = weapon_name.lower()
    if wname_lower not in inv:
        # Check if base weapon of magic item is in inv
        base = detected.get('base_weapon','')
        if not base or base.lower() not in inv:
            return ValidationResult(False,
                rejection=f"{pc.get('name','The character')} does not have a {weapon_name}.")

    # Check class weapon restrictions
    cd = OSE_CLASSES.get(cls,{})
    restriction = cd.get('weapons','any')
    if restriction and restriction != 'any':
        allowed = WEAPON_RESTRICTIONS.get(restriction,[])
        if allowed is not None and weapon_name not in allowed:
            return ValidationResult(False,
                rejection=f"{cls}s are restricted to {restriction} weapons. A {weapon_name} is not permitted.")

    # Halfling size restriction
    race = pc.get('race','Human')
    if race == 'Halfling':
        w = OSE_WEAPONS.get(weapon_name,{})
        if w.get('two_handed') or w.get('hands',1) == 2:
            return ValidationResult(False,
                rejection=f"Halflings are Small-sized and cannot use two-handed weapons.")

    # Ranged: check ammo
    w_data = OSE_WEAPONS.get(weapon_name,{})
    is_ranged = w_data.get('ranged',False)
    if is_ranged:
        ammo_type = w_data.get('ammo')
        if ammo_type:
            # Check inventory for ammo
            has_ammo = any(ammo_type.lower() in i for i in inv)
            if not has_ammo:
                return ValidationResult(False,
                    rejection=f"No {ammo_type} in inventory. {weapon_name} requires ammunition.")

    # Throwing: check if weapon is throwable
    if any(kw in text for kw in ['throw','hurl','toss']):
        if not w_data.get('throwable',False):
            return ValidationResult(False,
                rejection=f"A {weapon_name} cannot be thrown. Use Javelin, Dagger, Spear, or Hand Axe for throwing attacks.")

    # Backstab: must be hidden first
    if 'backstab' in text or 'from hiding' in text or 'from behind' in text:
        if cls not in ('Thief','Assassin'):
            return ValidationResult(False,
                rejection=f"Only Thieves and Assassins can backstab. {cls}s make normal attacks.")
        if not game_state.get('player_hidden',False):
            return ValidationResult(False,
                rejection=f"Cannot backstab — {pc.get('name','The character')} is not hidden. Use Move Silently or Hide in Shadows first.")

    # Target existence check (in combat — if in combat, target must exist in encounter)
    if game_state.get('in_combat'):
        enc = game_state.get('current_encounter',{})
        monsters = enc.get('monsters',[])
        # Try to match target in text to an actual monster
        target_found = False
        detected_target = None
        for m in monsters:
            if m.get('name','').lower() in text or m.get('id','').lower() in text:
                if m.get('hp',1) > 0:
                    target_found = True
                    detected_target = m
                elif m.get('hp',0) <= 0:
                    return ValidationResult(False,
                        rejection=f"The {m.get('name','monster')} is already dead.")
        if monsters and not target_found:
            detected_target = next((m for m in monsters if m.get('hp',1)>0), None)
            if not detected_target:
                return ValidationResult(False,
                    rejection="All enemies in this encounter are already dead.")

    return ValidationResult(True, action_type=ACTION_TYPES['ATTACK'],
                            parsed={'weapon': weapon_name,
                                    'is_ranged': is_ranged,
                                    'magic_bonus': magic_bonus,
                                    'dmg': w_data.get('dmg','1d6'),
                                    'two_handed': w_data.get('two_handed',False)})

# ── ITEM VALIDATION ───────────────────────────────────────────────────────────
ITEM_KEYWORDS = ['use','drink','apply','open','read','light','eat','consume']

def _detect_item_action(text):
    for kw in ITEM_KEYWORDS:
        if kw in text.split() or f' {kw} ' in f' {text} ':
            for iname in {**OSE_EQUIPMENT, **MAGIC_ITEMS}:
                if iname.lower() in text:
                    return {'item': iname, 'keyword': kw}
            return {'item': None, 'keyword': kw}
    return None

def _validate_item(detected, pc, game_state):
    item_name = detected.get('item')
    keyword = detected.get('keyword','use')
    inv_lower = [i.lower() if isinstance(i,str) else i.get('name','').lower()
                 for i in pc.get('inv',[])]

    if not item_name:
        return ValidationResult(True, action_type=ACTION_TYPES['USE_ITEM'],
                                parsed={'item': None, 'keyword': keyword})

    if item_name.lower() not in inv_lower:
        return ValidationResult(False,
            rejection=f"{pc.get('name','The character')} does not have {item_name}.")

    # Scroll restriction: Barbarians can't read
    if 'scroll' in item_name.lower():
        if pc.get('cls') == 'Barbarian':
            return ValidationResult(False,
                rejection=f"Barbarians are illiterate and cannot read scrolls.")
        if pc.get('cls') in ('Fighter','Ranger','Paladin','Barbarian'):
            return ValidationResult(False,
                rejection=f"{pc.get('cls')}s cannot use magic scrolls.")

    # Wand/staff restriction
    if 'wand' in item_name.lower() or 'staff' in item_name.lower():
        cls = pc.get('cls','Fighter')
        if cls in ('Barbarian','Fighter','Ranger','Paladin'):
            return ValidationResult(False,
                rejection=f"{cls}s cannot activate wands or staves. Magic items of this type require arcane knowledge.")

    # Thieves' Tools: must be a thief
    if item_name == "Thieves' Tools":
        if pc.get('cls') not in ('Thief','Assassin'):
            return ValidationResult(True,  # can carry them but won't help
                action_type=ACTION_TYPES['USE_ITEM'],
                parsed={'item': item_name},
                warning="Only Thieves and Assassins can use Thieves' Tools effectively.")

    return ValidationResult(True, action_type=ACTION_TYPES['USE_ITEM'],
                            parsed={'item': item_name, 'keyword': keyword})

# ── SKILL VALIDATION ──────────────────────────────────────────────────────────
SKILL_KEYWORDS = {
    'pick the lock':     'Open Locks',
    'pick lock':         'Open Locks',
    'open the lock':     'Open Locks',
    'unlock':            'Open Locks',
    'disarm the trap':   'Find/Remove Traps',
    'remove the trap':   'Find/Remove Traps',
    'disarm trap':       'Find/Remove Traps',
    'find trap':         'Find/Remove Traps',
    'search for trap':   'Find/Remove Traps',
    'pick pocket':       'Pick Pockets',
    'pickpocket':        'Pick Pockets',
    'steal from':        'Pick Pockets',
    'move silently':     'Move Silently',
    'sneak':             'Move Silently',
    'hide in shadow':    'Hide in Shadows',
    'hide in the shadow':'Hide in Shadows',
    'hide in darkness':  'Hide in Shadows',
    'climb the wall':    'Climb Walls',
    'climb walls':       'Climb Walls',
    'scale the wall':    'Climb Walls',
    'listen':            'Hear Noise',
    'hear noise':        'Hear Noise',
    'listen at the door':'Hear Noise',
    'read language':     'Read Languages',
    'decipher':          'Read Languages',
}

def _detect_skill_action(text):
    for phrase, skill in SKILL_KEYWORDS.items():
        if phrase in text:
            return skill
    return None

def _validate_skill(skill_name, pc, game_state):
    cls = pc.get('cls','Fighter')

    # Climb Walls: any character can try (just worse chance)
    if skill_name == 'Climb Walls':
        return ValidationResult(True, action_type=ACTION_TYPES['SKILL'],
                                parsed={'skill': skill_name,
                                        'is_thief_skill': cls in ('Thief','Assassin')})

    # Hear Noise: any character can try
    if skill_name == 'Hear Noise':
        return ValidationResult(True, action_type=ACTION_TYPES['SKILL'],
                                parsed={'skill': skill_name,
                                        'is_thief_skill': cls in ('Thief','Assassin')})

    # Other thief skills: only Thief/Assassin
    if cls not in ('Thief','Assassin'):
        friendly_names = {
            'Open Locks': 'picking locks',
            'Find/Remove Traps': 'finding and removing traps',
            'Pick Pockets': 'picking pockets',
            'Hide in Shadows': 'hiding in shadows (thief skill)',
            'Move Silently': 'moving silently (thief skill)',
            'Read Languages': 'reading unknown languages',
        }
        action_name = friendly_names.get(skill_name, skill_name)
        return ValidationResult(False,
            rejection=f"Only Thieves and Assassins have the {action_name} skill. "
                      f"A {cls} lacks the training. "
                      f"{'You could try forcing the lock with STR instead.' if skill_name == 'Open Locks' else ''}")

    # Thieves' Tools required for Open Locks / Find+Remove Traps
    if skill_name in ('Open Locks','Find/Remove Traps'):
        inv_lower = [i.lower() if isinstance(i,str) else i.get('name','').lower()
                     for i in pc.get('inv',[])]
        if "thieves' tools" not in inv_lower and 'thieves tools' not in inv_lower:
            return ValidationResult(False,
                rejection=f"Thieves' Tools are required to {skill_name.lower()}.")

    return ValidationResult(True, action_type=ACTION_TYPES['SKILL'],
                            parsed={'skill': skill_name, 'is_thief_skill': True})

# ── ABILITY VALIDATION ────────────────────────────────────────────────────────
ABILITY_KEYWORDS = {
    'turn undead':    'Turn Undead',
    'turn the undead':'Turn Undead',
    'rebuke undead':  'Turn Undead',
    'lay on hands':   'Lay on Hands',
    'heal with hands':'Lay on Hands',
    'detect evil':    'Detect Evil',
    'sense evil':     'Detect Evil',
    'rage':           'Rage',
    'enter rage':     'Rage',
    'go berserk':     'Rage',
    'backstab':       'Backstab',
    'shapechange':    'Shapechange',
    'shapeshift':     'Shapechange',
    'polymorph into': 'Shapechange',
    'inspire courage':'Inspire Courage',
    'inspire':        'Inspire Courage',
    'perform':        'Inspire Courage',
    'bard lore':      'Bard Lore',
    'identify':       'Bard Lore',
}

def _detect_ability_action(text, pc):
    for phrase, ability in ABILITY_KEYWORDS.items():
        if phrase in text:
            return ability
    return None

def _validate_ability(ability_name, pc, game_state):
    cls = pc.get('cls','Fighter')
    level = pc.get('level',1)
    abilities_used = pc.get('abilities_used_today',{})
    all_abilities = get_class_abilities_for_level(cls, level)
    ability_names = [a['name'] for a in all_abilities]

    # Check character has this ability
    if ability_name not in ability_names:
        # Find who has it
        owners = [c for c,tbl in CLASS_LEVEL_ABILITIES.items()
                  for lvl,abs_ in tbl.items()
                  for a in abs_ if a['name'] == ability_name and level >= lvl]
        if owners:
            return ValidationResult(False,
                rejection=f"{cls}s do not have the {ability_name} ability. This is a {'/'.join(owners)} class ability.")
        else:
            return ValidationResult(False,
                rejection=f"'{ability_name}' is not a class ability in OSE Advanced Fantasy.")

    # Check uses remaining
    ability = next((a for a in all_abilities if a['name'] == ability_name), None)
    if ability:
        uses = ability.get('uses','unlimited')
        if uses == 'at_will':
            pass  # always available
        elif uses.endswith('_per_day'):
            max_uses = int(uses.split('_')[0]) if uses[0].isdigit() else 1
            used_today = abilities_used.get(ability_name, 0)
            if used_today >= max_uses:
                return ValidationResult(False,
                    rejection=f"{ability_name} has been used {used_today} time(s) today. "
                              f"Maximum {max_uses}/day. Rest to recover.")
        elif uses == 'pool' and ability_name == 'Lay on Hands':
            pool_max = level * 2
            used = abilities_used.get('Lay on Hands_pool', 0)
            if used >= pool_max:
                return ValidationResult(False,
                    rejection=f"Lay on Hands pool exhausted ({used}/{pool_max} HP used today). Rest to recover.")

    return ValidationResult(True, action_type=ACTION_TYPES['ABILITY'],
                            parsed={'ability': ability_name, 'ability_data': ability})

# ── PHYSICAL IMPOSSIBILITY CHECK ─────────────────────────────────────────────
IMPOSSIBLE_ACTIONS = [
    (['fly','soar','float in air','levitate'],
     lambda pc,gs: not _has_flight(pc,gs),
     "cannot fly without a Fly spell, Levitate spell, Potion of Flying, or magical item granting flight."),
    (['breathe underwater','breathe water'],
     lambda pc,gs: not _has_water_breathing(pc,gs),
     "cannot breathe underwater without Water Breathing spell or a magical item."),
    (['become invisible','turn invisible','go invisible'],
     lambda pc,gs: not _has_invisibility(pc,gs),
     "cannot become invisible without an Invisibility spell, Potion of Invisibility, or Ring of Invisibility."),
    (['grow 50 feet','grow 100 feet','become giant','grow enormous'],
     lambda pc,gs: True,
     "cannot change size without a spell or magical effect. No such ability or item is available."),
    (['summon a god','summon demon','summon devil','call upon god',
      'summon angel','invoke deity','meteor','call down fire from sky',
      'summon a','i summon','summon the'],
     lambda pc,gs: True,
     "is not capable of that. Such powers are beyond mortal reach in OSE Advanced Fantasy."),
    (['teleport','blink','dimension hop'],
     lambda pc,gs: not _has_teleport(pc,gs),
     "cannot teleport without Dimension Door spell, Teleport spell, or a magical item granting teleportation."),
]

def _has_flight(pc, gs):
    effects = pc.get('active_effects',[])
    return any(e.get('type') in ('fly','levitate') for e in effects)

def _has_water_breathing(pc, gs):
    effects = pc.get('active_effects',[])
    return any(e.get('type') == 'water_breathing' for e in effects)

def _has_invisibility(pc, gs):
    effects = pc.get('active_effects',[])
    equipped = pc.get('equipped_magic',[])
    return (any(e.get('type') == 'invisible' for e in effects) or
            'Ring of Invisibility' in equipped)

def _has_teleport(pc, gs):
    effects = pc.get('active_effects',[])
    return any(e.get('type') in ('teleport','dimension_door') for e in effects)

def _check_physically_impossible(text, pc, game_state):
    pc_name = pc.get('name','The character')
    for triggers, condition_fn, rejection_msg in IMPOSSIBLE_ACTIONS:
        if any(t in text for t in triggers):
            if condition_fn(pc, game_state):
                return f"{pc_name} {rejection_msg}"
    return None

# ── CLOSED WORLD CHECK ────────────────────────────────────────────────────────
def _check_closed_world(text, game_state):
    """Check if text references entities not present in the current module/room."""
    module_data = game_state.get('module_data',{})
    current_room_id = game_state.get('current_room')
    in_combat = game_state.get('in_combat',False)

    if not module_data or not in_combat:
        return None  # Only enforce strictly during encounters

    # Get all valid entities in current encounter
    enc = game_state.get('current_encounter',{})
    valid_monsters = [m.get('name','').lower() for m in enc.get('monsters',[])]
    valid_npcs = [n.get('name','').lower() for n in enc.get('npcs',[])]
    all_valid = valid_monsters + valid_npcs

    # Look for specific creature names in text that aren't in the encounter
    # Only check if text mentions attacking/targeting something
    attack_words = ['attack','shoot','cast at','throw at','target','strike']
    if not any(w in text for w in attack_words):
        return None

    # Build list of creature names mentioned in text
    # Simple heuristic: words following 'the' that look like creature names
    import re
    mentioned = re.findall(r'\bthe\s+(\w+(?:\s+\w+)?)\b', text)
    for mention in mentioned:
        mention_lower = mention.lower()
        # Check if this creature could be something not in the module
        if any(inv_creature in mention_lower for inv_creature in
               ['dragon','serpent','giant','demon','troll','vampire']):
            if mention_lower not in ' '.join(all_valid):
                return (f"There is no {mention} here. "
                        f"{'Current enemies: ' + ', '.join([m.get('name','') for m in enc.get('monsters',[]) if m.get('hp',0)>0]) + '.' if valid_monsters else 'There are no enemies in this encounter.'}")

    return None

# ── HELPERS ───────────────────────────────────────────────────────────────────
def _ordinal(n):
    if n == 1: return '1st'
    if n == 2: return '2nd'
    if n == 3: return '3rd'
    return f'{n}th'

# ═══════════════════════════════════════════════════════════════════════════════
# SECTION D: LAYER 3 RESOLVER
# Zero AI. Takes a parsed action chain and resolves it mechanically.
# Returns a MechanicalResultLog that the narrator will later describe.
# ═══════════════════════════════════════════════════════════════════════════════

class MechanicalResult:
    def __init__(self):
        self.action_type = None
        self.display_lines = []   # shown to player immediately (gold-bordered box)
        self.state_changes = {}   # applied to game state
        self.narration_context = {}  # passed to AI narrator
        self.success = False
        self.error = None

    def add_line(self, line):
        self.display_lines.append(line)

    def to_dict(self):
        return {
            'action_type': self.action_type,
            'display_lines': self.display_lines,
            'state_changes': self.state_changes,
            'narration_context': self.narration_context,
            'success': self.success,
            'error': self.error,
        }

def resolve_action(validated, pc, game_state):
    """
    Main resolver. Takes a ValidationResult and resolves mechanics.
    Returns MechanicalResult.
    """
    result = MechanicalResult()
    action_type = validated.action_type
    parsed = validated.parsed
    result.action_type = action_type

    if action_type == ACTION_TYPES['ATTACK']:
        _resolve_attack_action(result, parsed, pc, game_state)

    elif action_type == ACTION_TYPES['CAST']:
        _resolve_cast_action(result, parsed, pc, game_state)

    elif action_type == ACTION_TYPES['SKILL']:
        _resolve_skill_action(result, parsed, pc, game_state)

    elif action_type == ACTION_TYPES['ABILITY']:
        _resolve_ability_action(result, parsed, pc, game_state)

    elif action_type == ACTION_TYPES['USE_ITEM']:
        _resolve_item_action(result, parsed, pc, game_state)

    elif action_type == ACTION_TYPES['REST']:
        _resolve_rest_action(result, parsed, pc, game_state)

    else:
        # No mechanical resolution — pass straight to narrator
        result.success = True
        result.narration_context = {'raw_action': parsed.get('raw_text',''),
                                    'requires_roll': False}

    return result

def _resolve_attack_action(result, parsed, pc, game_state):
    weapon_name = parsed.get('weapon','Sword')
    is_ranged    = parsed.get('is_ranged',False)
    magic_bonus  = parsed.get('magic_bonus',0)
    backstab     = parsed.get('backstab',False)

    # Find target
    enc = game_state.get('current_encounter',{})
    monsters = enc.get('monsters',[])
    target = next((m for m in monsters if m.get('hp',0) > 0), None)

    if not target and not game_state.get('in_combat'):
        # Not in combat — attacking object or environment
        target_ac = _estimate_object_ac(parsed.get('target_desc',''))
        target_name = parsed.get('target_desc','target')
        atk = resolve_attack(pc, weapon_name, target_ac, is_ranged, backstab, magic_bonus)
        result.add_line(atk['display'])
        result.success = atk['hit']
        result.narration_context = {
            'attack_result': atk,
            'target': target_name,
            'target_ac': target_ac,
            'in_combat': False,
        }
        if atk['hit']:
            result.state_changes['damage_to_object'] = {
                'object': target_name, 'damage': atk['damage']
            }
        # Consume ammo if ranged
        if is_ranged:
            result.state_changes['consume_ammo'] = 1
        return

    if not target:
        result.error = "No valid target."
        return

    target_ac = target.get('ac', 9)
    atk = resolve_attack(pc, weapon_name, target_ac, is_ranged, backstab, magic_bonus)
    result.add_line(atk['display'])
    result.success = atk['hit']

    if atk['hit']:
        new_hp = max(0, target.get('hp',1) - atk['damage'])
        result.state_changes['monster_damage'] = {
            'monster_id': target.get('id', target.get('name','')),
            'damage': atk['damage'],
            'new_hp': new_hp,
            'killed': new_hp <= 0,
        }

        if new_hp <= 0:
            xp = target.get('xp',0)
            result.state_changes['xp_gain'] = xp
            result.add_line(f"[{target.get('name','')} slain — {xp} XP]")
        elif new_hp <= target.get('maxhp',4) // 2:
            # Morale check
            holds, mroll, mdetail = check_morale(target.get('morale',7))
            result.add_line(mdetail)
            if not holds:
                result.state_changes['monster_flees'] = target.get('id', target.get('name',''))

    # Consume ammo
    if is_ranged:
        result.state_changes['consume_ammo'] = 1

    # Monster counterattack (if in combat and monster survived)
    if game_state.get('in_combat') and target:
        new_hp = result.state_changes.get('monster_damage',{}).get('new_hp', target.get('hp',4))
        if new_hp > 0 and not result.state_changes.get('monster_flees'):
            _resolve_monster_attack(result, target, pc, game_state)

    result.narration_context = {
        'attack_result': atk,
        'target': target.get('name','enemy'),
        'in_combat': game_state.get('in_combat',False),
        'monster_damage': result.state_changes.get('monster_damage'),
        'monster_counterattack': result.state_changes.get('monster_counterattack'),
    }

def _resolve_monster_attack(result, monster, pc, game_state):
    """Resolve monster's return attack."""
    thac0 = monster.get('thac0', 20 - (monster.get('hd',1)))
    target_ac = pc.get('ac', 9)
    dmg_expr = monster.get('damage','1d6')

    d20, _ = roll(20)
    # Monster hits if d20 >= (thac0 - target_ac)
    needed = thac0 - target_ac
    hit = d20 >= max(needed, 2)  # always miss on 1
    nat1 = (d20 == 1)

    if hit and not nat1:
        dmg, dmg_detail = roll_expr(dmg_expr)
        detail = f"{monster.get('name','Enemy')} ATTACKS: d20=[{d20}] — HIT | DAMAGE: {dmg_detail} = {dmg}"
        result.state_changes['player_damage'] = dmg
        result.state_changes['monster_counterattack'] = {
            'hit': True, 'd20': d20, 'damage': dmg, 'detail': detail
        }
    else:
        detail = f"{monster.get('name','Enemy')} ATTACKS: d20=[{d20}] — {'FUMBLE' if nat1 else 'MISS'}"
        result.state_changes['monster_counterattack'] = {
            'hit': False, 'd20': d20, 'damage': 0, 'detail': detail
        }

    result.add_line(detail)

def _estimate_object_ac(desc):
    """Estimate AC of a non-monster target based on description."""
    desc = desc.lower()
    if any(w in desc for w in ['stone','rock','wall','iron','metal','chain']): return 3
    if any(w in desc for w in ['wood','door','barrel','crate','chest']): return 7
    if any(w in desc for w in ['rope','leather','cloth','bag']): return 9
    return 9  # default unarmoured

def _resolve_cast_action(result, parsed, pc, game_state):
    spell_name = parsed.get('spell_name')
    spell = parsed.get('spell', get_spell(spell_name))
    spell_level = parsed.get('spell_level',1)

    # Find target
    enc = game_state.get('current_encounter',{})
    monsters = enc.get('monsters',[])
    target_monster = next((m for m in monsters if m.get('hp',0)>0), None)
    target_info = {'pc': target_monster, 'can_save': True} if target_monster else {}

    # Resolve spell
    spell_result = resolve_spell(pc, spell_name, target_info, game_state)

    for line in spell_result.get('display_lines',[]):
        result.add_line(line)

    # Decrement spell slot
    result.state_changes['consume_spell_slot'] = spell_level

    # Apply spell effects
    sc = spell_result.get('state_changes',{})
    if 'heal' in sc:
        result.state_changes['heal_player'] = sc['heal']
    if 'sleep_hd' in sc:
        result.state_changes['sleep_monsters'] = sc['sleep_hd']
    if spell_result.get('damage',0) > 0 and target_monster:
        new_hp = max(0, target_monster.get('hp',1) - spell_result['damage'])
        result.state_changes['monster_damage'] = {
            'monster_id': target_monster.get('id', target_monster.get('name','')),
            'damage': spell_result['damage'],
            'new_hp': new_hp,
            'killed': new_hp <= 0,
        }
        if new_hp <= 0:
            result.state_changes['xp_gain'] = target_monster.get('xp',0)

    result.success = True
    result.narration_context = {
        'spell_result': spell_result,
        'spell_name': spell_name,
        'target': target_monster.get('name','') if target_monster else 'area',
        'in_combat': game_state.get('in_combat',False),
    }

def _resolve_skill_action(result, parsed, pc, game_state):
    skill = parsed.get('skill')
    is_thief = parsed.get('is_thief_skill',False)
    cls = pc.get('cls','Fighter')

    if skill in ('Hear Noise', 'Climb Walls') and not is_thief:
        # Non-thief: d6 roll (1-2 success for Hear Noise, harder climb)
        if skill == 'Hear Noise':
            d6, _ = roll(6)
            success = d6 <= 2
            detail = f"Hear Noise: d6=[{d6}] — {'HEARD' if success else 'NOTHING'}"
        else:
            d6, _ = roll(6)
            success = d6 == 1
            detail = f"Climb Walls (unskilled): d6=[{d6}] — {'SUCCESS' if success else 'FAILED (FALLS)'}"
        result.add_line(detail)
        result.success = success
        result.narration_context = {'skill': skill, 'success': success, 'is_thief': False}
        return

    success, d100, target, detail = resolve_thief_skill(pc, skill)
    result.add_line(detail)
    result.success = success
    result.narration_context = {'skill': skill, 'success': success, 'roll': d100,
                                 'target': target, 'is_thief': True}

def _resolve_ability_action(result, parsed, pc, game_state):
    ability_name = parsed.get('ability')
    level = pc.get('level',1)
    cls = pc.get('cls','Fighter')

    if ability_name == 'Turn Undead':
        # Find undead target
        enc = game_state.get('current_encounter',{})
        monsters = enc.get('monsters',[])
        undead = next((m for m in monsters
                       if m.get('type','').lower() in ('undead',) or
                       m.get('name','').lower() in [u.lower() for u in UNDEAD_TYPES]
                       and m.get('hp',0) > 0), None)
        if not undead:
            result.error = "No undead creatures present to turn."
            return
        undead_type = undead.get('name','Skeleton')
        evil = pc.get('alignment','Neutral') in ('Chaotic',)
        turn_result, turn_roll, detail = resolve_turn_undead(level, undead_type, evil)
        result.add_line(detail)
        result.success = turn_result != 'failed'
        if turn_result == 'turned':
            result.state_changes['monster_flees'] = undead.get('id', undead_type)
        elif turn_result == 'destroyed':
            result.state_changes['monster_damage'] = {
                'monster_id': undead.get('id', undead_type),
                'damage': 9999, 'new_hp': 0, 'killed': True,
            }
            result.state_changes['xp_gain'] = undead.get('xp',0)
        result.narration_context = {'ability': ability_name, 'turn_result': turn_result,
                                     'undead_type': undead_type}

    elif ability_name == 'Lay on Hands':
        heal_amount = level * 2
        result.add_line(f"Lay on Hands: Heals {heal_amount} HP")
        result.success = True
        result.state_changes['heal_player'] = heal_amount
        result.state_changes['ability_used'] = {'name': 'Lay on Hands_pool', 'amount': heal_amount}
        result.narration_context = {'ability': ability_name, 'heal': heal_amount}

    elif ability_name == 'Rage':
        result.add_line(f"RAGE: +2 to attack rolls and damage, -2 AC for 3 rounds")
        result.success = True
        result.state_changes['add_effect'] = {
            'type': 'rage', 'turns': 3,
            'attack_bonus': 2, 'damage_bonus': 2, 'ac_penalty': 2
        }
        result.state_changes['ability_used'] = {'name': 'Rage', 'amount': 1}
        result.narration_context = {'ability': ability_name}

    elif ability_name == 'Inspire Courage':
        result.add_line(f"INSPIRE COURAGE: All allies who can hear gain +1 to attack rolls and saving throws")
        result.success = True
        result.state_changes['add_party_effect'] = {
            'type': 'inspired', 'bonus': 1, 'duration': 'performance+5_rounds'
        }
        result.narration_context = {'ability': ability_name}

    elif ability_name == 'Backstab':
        # Handled in attack resolution
        result.success = True
        result.narration_context = {'ability': ability_name, 'redirected': 'attack'}

    elif ability_name == 'Shapechange':
        result.add_line(f"SHAPECHANGE: Druid transforms into animal form")
        result.success = True
        result.state_changes['ability_used'] = {'name': 'Shapechange', 'amount': 1}
        result.narration_context = {'ability': ability_name, 'requires_target_description': True}

    else:
        result.success = True
        result.narration_context = {'ability': ability_name}

    if ability_name not in ('Backstab',):
        result.state_changes.setdefault('ability_used', {'name': ability_name, 'amount': 1})

def _resolve_item_action(result, parsed, pc, game_state):
    item_name = parsed.get('item')
    keyword = parsed.get('keyword','use')

    if not item_name:
        result.success = True
        result.narration_context = {'item': None, 'raw': True}
        return

    # Torch lighting
    if 'torch' in item_name.lower() and keyword == 'light':
        result.add_line("TORCH LIT — 6 turns of light")
        result.success = True
        result.state_changes['light_torch'] = True
        result.narration_context = {'item': item_name, 'effect': 'light'}
        return

    # Rations
    if 'ration' in item_name.lower() and keyword in ('eat','consume','use'):
        result.add_line("RATIONS: 1 day's rations consumed. Hunger reset.")
        result.success = True
        result.state_changes['consume_ration'] = 1
        result.narration_context = {'item': item_name, 'effect': 'eat'}
        return

    # Holy water
    if 'holy water' in item_name.lower():
        enc = game_state.get('current_encounter',{})
        monsters = enc.get('monsters',[])
        undead = next((m for m in monsters
                       if m.get('type','').lower() == 'undead' and m.get('hp',0)>0), None)
        if undead:
            dmg, detail = roll_expr('2d4')
            result.add_line(f"HOLY WATER vs {undead.get('name','Undead')}: {detail} = {dmg} damage")
            result.success = True
            result.state_changes['monster_damage'] = {
                'monster_id': undead.get('id', undead.get('name','')),
                'damage': dmg, 'new_hp': max(0, undead.get('hp',1)-dmg),
                'killed': (undead.get('hp',1)-dmg) <= 0
            }
            result.state_changes['consume_item'] = item_name
        else:
            result.success = False
            result.add_line("Holy Water: No undead target present.")
        result.narration_context = {'item': item_name, 'undead_target': undead}
        return

    # Magic items
    if item_name in MAGIC_ITEMS:
        ok, mi_result = apply_magic_item(item_name, pc)
        result.add_line(mi_result.get('display',''))
        result.success = ok
        sc = mi_result.get('state_changes',{})
        result.state_changes.update(sc)
        if MAGIC_ITEMS[item_name].get('single_use'):
            result.state_changes['consume_item'] = item_name
        result.narration_context = {'item': item_name, 'magic_result': mi_result}
        return

    result.success = True
    result.narration_context = {'item': item_name, 'keyword': keyword}

def _resolve_rest_action(result, parsed, pc, game_state):
    rest_type = parsed.get('rest_type','dungeon')
    in_dungeon = game_state.get('in_dungeon',False)

    if rest_type == 'dungeon' and in_dungeon:
        result.add_line("REST: 1 turn taken. Dungeon rest clock reset.")
        result.success = True
        result.state_changes['dungeon_rest'] = True
    elif rest_type == 'full':
        hp_gain = pc.get('level',1) * 1  # 1 HP per level per OSE
        result.add_line(f"FULL REST: Recover {hp_gain} HP, consume 1 ration, reset spell slots")
        result.success = True
        result.state_changes['full_rest'] = True
        result.state_changes['heal_player'] = hp_gain
        result.state_changes['consume_ration'] = 1

    result.narration_context = {'rest_type': rest_type}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C: LAYER 2 — INTENT PARSER (Claude API — Haiku for speed/cost)
# Takes validated action text and returns structured action chain JSON.
# Optimized for: reliable JSON output, structured commands, no narrative.
# ═══════════════════════════════════════════════════════════════════════════════

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
CLAUDE_PARSE_MODEL  = "claude-haiku-4-5"   # fast + cheap for parsing
CLAUDE_NARRATE_MODEL = "claude-sonnet-4-5" # quality narration

PARSE_SYSTEM = """You are a rules-engine parser for a D&D text adventure using OSE Advanced Fantasy rules.
Your ONLY job: convert player input into a structured JSON action chain.
Output ONLY valid JSON. No prose. No explanation. No markdown.

ACTION TYPES: attack | cast | use_item | move | social | skill | ability | examine | rest | other

For attack: {"type":"attack","weapon":"Sword","target":"goblin_1","is_ranged":false}
For cast: {"type":"cast","spell":"Sleep","target":"goblin_1"}
For social: {"type":"social","target":"Bertram","intent":"ask about the village","verbal_content":"the exact words spoken"}
For use_item: {"type":"use_item","item":"Potion of Healing","target":"self"}
For skill: {"type":"skill","skill":"Open Locks","target":"chest"}
For ability: {"type":"ability","ability":"Turn Undead","target":"skeleton_1"}
For move: {"type":"move","direction":"north","destination":"W2"}
For examine: {"type":"examine","target":"door"}
For rest: {"type":"rest","rest_type":"dungeon"}

For chained actions (e.g. "I cast magic missile at the stalactite so it falls on the dragon"):
[{"type":"cast","spell":"Magic Missile","target":"stalactite","chain_on_success":{"type":"falling_object","object":"stalactite","target":"dragon_1","damage":"1d10","target_ac":5}}]

Always return a JSON array of actions, even if only one action.
If the input is pure dialogue to an NPC, return: [{"type":"social","target":"<npc_name>","verbal_content":"<exact words>","intent":"<brief intent>"}]
If completely unclear, return: [{"type":"other","raw":"<original text>"}]"""

def parse_intent_claude(text, pc, game_state, api_key):
    """
    Layer 2: Use Claude Haiku to parse natural language into action chain.
    Returns list of action dicts, or None on failure.
    """
    context = {
        "character": {
            "name": pc.get("name"), "class": pc.get("cls"), "level": pc.get("level"),
            "inventory": pc.get("inv",[])[:15],  # limit size
            "memorized_spells": pc.get("memorized_spells",[]),
            "in_combat": game_state.get("in_combat",False),
        },
        "enemies_present": [{"id":m.get("id",m.get("name")),"name":m.get("name"),"hp":m.get("hp",0)}
                            for m in game_state.get("current_encounter",{}).get("monsters",[])
                            if m.get("hp",0)>0],
        "npcs_present": [n.get("name","") for n in game_state.get("npcs_present",[])],
        "objects_present": game_state.get("objects_present",[]),
        "current_room": game_state.get("current_room",""),
    }

    payload = {
        "model": CLAUDE_PARSE_MODEL,
        "max_tokens": 400,
        "system": PARSE_SYSTEM,
        "messages": [{"role":"user","content":
            f"Player says: \"{text}\"\n\nContext: {json.dumps(context)}\n\nReturn JSON action array only."}]
    }

    try:
        req = urllib.request.Request(
            CLAUDE_API_URL,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            }
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        raw = data["content"][0]["text"].strip()
        # Strip any accidental markdown
        raw = re.sub(r"^```json\s*", "", raw)
        raw = re.sub(r"```\s*$", "", raw)
        parsed = json.loads(raw)
        if isinstance(parsed, dict): parsed = [parsed]
        return parsed
    except Exception as e:
        print(f"[Layer2/Claude] Parse error: {e}")
        return None

def parse_intent_ollama(text, pc, game_state, model="mistral-nemo:12b"):
    """
    Layer 2 fallback: Use Ollama when no Claude API key available.
    More conservative — returns simpler action objects.
    """
    # Simple keyword-based fallback when Ollama JSON parsing is unreliable
    text_lower = text.lower()

    # Try to construct a simple action from the validated type already determined
    # (The validator already did keyword detection — use that)
    action = {"type": "other", "raw": text}

    for kw in ["attack","strike","hit","stab","slash","swing"]:
        if kw in text_lower:
            for wname in OSE_WEAPONS:
                if wname.lower() in text_lower:
                    action = {"type":"attack","weapon":wname,"is_ranged":OSE_WEAPONS[wname].get("ranged",False)}
                    break
            else:
                action = {"type":"attack","weapon":None}
            break

    for kw in ["shoot","fire"]:
        if kw in text_lower:
            for wname in OSE_WEAPONS:
                if wname.lower() in text_lower:
                    action = {"type":"attack","weapon":wname,"is_ranged":True}
                    break
            break

    for kw in ["cast","use scroll"]:
        if kw in text_lower:
            for sname in ALL_SPELLS:
                if sname.lower() in text_lower:
                    action = {"type":"cast","spell":sname}
                    break
            break

    for phrase, skill in SKILL_KEYWORDS.items():
        if phrase in text_lower:
            action = {"type":"skill","skill":skill}
            break

    for phrase, ability in ABILITY_KEYWORDS.items():
        if phrase in text_lower:
            action = {"type":"ability","ability":ability}
            break

    if "rest" in text_lower:
        action = {"type":"rest","rest_type":"dungeon" if "turn" in text_lower else "full"}

    return [action]


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION E: LAYER 4 — NARRATOR (Ollama primary / Claude fallback)
# Receives MechanicalResult and produces immersive prose.
# Optimized for: vivid fiction, strict module fidelity, no hallucination.
# ═══════════════════════════════════════════════════════════════════════════════

NARRATOR_SYSTEM_TEMPLATE = """You are a Game Master narrating a D&D adventure (OSE Advanced Fantasy rules).

Write 2-4 paragraphs of vivid present-tense prose.
Stay within the module -- only reference what is defined below.
Do NOT invent new characters, places, or plot points.
Do NOT speak for the player character.
Do NOT change any dice results shown.
No headers, bullets, or bold text.

MODULE: {module_context}
LOCATION: {location}
IN COMBAT: {in_combat}
ENEMIES: {enemies}
NPCS: {npcs}
PARTY: {party}
"""
def _build_narrator_system(ctx):
    enc = ctx.get("current_encounter",{})
    monsters = enc.get("monsters",[])
    alive = [m for m in monsters if m.get("hp",0)>0]
    enemies_str = ", ".join(f"{m['name']} (HP {m['hp']}/{m['maxhp']})" for m in alive) if alive else "None"

    npcs = ctx.get("npcs_present",[])
    npc_str = ", ".join(n.get("name","") for n in npcs) if npcs else "None"

    party = ctx.get("party_pcs",{})
    party_str = "\n".join(
        f"{name}: {p.get('cls','')} Lv{p.get('level',1)}, HP {p.get('hp',0)}/{p.get('maxhp',0)}"
        for name,p in party.items()
    ) if party else ctx.get("pc_summary","Unknown adventurer")

    module_ctx_lines = []
    md = ctx.get("module_data",{})
    if md:
        module_ctx_lines.append(f"Module: {md.get('title','Unknown')}")
        module_ctx_lines.append(f"Setting: {md.get('setting','')}")
        module_ctx_lines.append(f"Core Tension: {md.get('core_tension','')}")
        # Current room data
        room_id = ctx.get("current_room")
        if room_id:
            locs = {l["id"]:l for l in md.get("locations",[])}
            room = locs.get(room_id,{})
            if room:
                module_ctx_lines.append(f"Current Room: {room.get('name',room_id)}")
                module_ctx_lines.append(f"Room Atmosphere: {room.get('atmosphere','')}")
                exits = room.get("exits",{})
                if exits:
                    module_ctx_lines.append(f"Exits: {', '.join(f'{d}: {dest}' for d,dest in exits.items())}")
        # Active NPCs knowledge
        npc_profiles = ctx.get("npc_profiles",{})
        if npc_profiles:
            for npc_name, profile in list(npc_profiles.items())[:3]:
                module_ctx_lines.append(f"NPC {npc_name}: motivation={profile.get('motivation','')}, attitude={profile.get('attitude','')}")

    return NARRATOR_SYSTEM_TEMPLATE.format(
        module_context="\n".join(module_ctx_lines) or "No module loaded.",
        location=ctx.get("current_location","Unknown"),
        in_combat="Yes" if ctx.get("in_combat") else "No",
        enemies=enemies_str,
        npcs=npc_str,
        party=party_str,
    )

def _build_narrator_user(result_dict):
    action = result_dict.get("action_type","other")
    success = result_dict.get("success",False)
    display = result_dict.get("display_lines",[])
    sc = result_dict.get("state_changes",{})
    ctx = result_dict.get("narration_context",{})
    parts = [f"Narrate: {action} ({'succeeded' if success else 'failed'})"]
    if display:
        parts.append("Dice: " + " | ".join(display))
    if sc.get("monster_damage"):
        md = sc["monster_damage"]
        parts.append(f"{md.get('monster_id','Enemy')}: {md.get('damage',0)} damage" +
                     (" -- killed" if md.get("killed") else ""))
    if sc.get("monster_flees"):
        parts.append(f"{sc['monster_flees']} fled")
    if sc.get("player_damage"):
        parts.append(f"Player: -{sc['player_damage']} HP")
    if sc.get("heal_player"):
        parts.append(f"Player: +{sc['heal_player']} HP healed")
    if ctx.get("raw_action") and not display:
        parts.append(f"Action: {ctx['raw_action']}")
    if result_dict.get("error"):
        parts.append(f"Failed: {result_dict['error']}")
    return "\n".join(parts)


def narrate_ollama(result_dict, prompt_context, model, history):
    """Layer 4: Narrate mechanical result using Ollama."""
    import urllib.request as _ur, json as _json
    system = _build_narrator_system(prompt_context)
    user_msg = _build_narrator_user(result_dict)
    trimmed = history[-8:] if len(history) > 8 else history
    payload = {
        "model": model,
        "system": system,
        "messages": trimmed + [{"role":"user","content":user_msg}],
        "stream": False,
        "options": {"temperature": 0.75, "top_p": 0.9, "num_ctx": 4096}
    }
    try:
        req = _ur.Request("http://localhost:11434/api/chat",
            data=_json.dumps(payload).encode(),
            headers={"Content-Type":"application/json"})
        with _ur.urlopen(req, timeout=90) as resp:
            data = _json.loads(resp.read())
        return data.get("message",{}).get("content",""), None
    except Exception as e:
        return None, str(e)


def narrate_claude(result_dict, prompt_context, api_key, history):
    """Layer 4: Narrate mechanical result using Claude Sonnet."""
    import urllib.request as _ur, json as _json
    system = _build_narrator_system(prompt_context)
    user_msg = _build_narrator_user(result_dict)
    trimmed = history[-12:] if len(history) > 12 else history
    payload = {
        "model": CLAUDE_NARRATE_MODEL,
        "max_tokens": 600,
        "system": system,
        "messages": trimmed + [{"role":"user","content":user_msg}]
    }
    try:
        req = _ur.Request(CLAUDE_API_URL,
            data=_json.dumps(payload).encode(),
            headers={"Content-Type":"application/json",
                     "x-api-key": api_key,
                     "anthropic-version":"2023-06-01"})
        with _ur.urlopen(req, timeout=30) as resp:
            data = _json.loads(resp.read())
        return data["content"][0]["text"], None
    except Exception as e:
        return None, str(e)


def _fallback_narration(result_dict):
    """Emergency fallback when both AI systems are unavailable."""
    lines = result_dict.get("display_lines", [])
    ctx = result_dict.get("narration_context", {})
    if result_dict.get("error"):
        return f"The action cannot be completed: {result_dict['error']}"
    if lines:
        return "The action resolves. " + " | ".join(lines)
    raw = ctx.get("raw_action", "")
    if raw:
        return f"You attempt: {raw}. The outcome is uncertain."
    return "The moment passes."


def get_npc_dialogue(npc_profile, player_input, feasibility_result, history, api_key, ollama_model):
    """
    Section F: Get NPC dialogue response.
    Uses Claude if available, falls back to Ollama.
    """
    system = NPC_DIALOGUE_SYSTEM.format(
        npc_profile=json.dumps(npc_profile, indent=2),
        knowledge_limits="\n".join(f"- {k}: {v}" for k,v in npc_profile.get("knowledge",{}).items()),
        feasibility=feasibility_result.get("feasibility","possible"),
        feasibility_reason=feasibility_result.get("reason",""),
    )

    trimmed = history[-6:] if len(history)>6 else history

    if api_key:
        payload = {
            "model": CLAUDE_NARRATE_MODEL,
            "max_tokens": 300,
            "system": system,
            "messages": trimmed + [{"role":"user","content":player_input}]
        }
        try:
            req = urllib.request.Request(CLAUDE_API_URL,
                data=json.dumps(payload).encode(),
                headers={"Content-Type":"application/json","x-api-key":api_key,
                         "anthropic-version":"2023-06-01"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read())
            return data["content"][0]["text"], None
        except Exception as e:
            pass  # fall through to Ollama

    # Ollama fallback
    payload = {
        "model": ollama_model,
        "system": system,
        "messages": trimmed + [{"role":"user","content":player_input}],
        "stream": False,
        "options": {"temperature": 0.7, "num_ctx": 2048}
    }
    try:
        req = urllib.request.Request("http://localhost:11434/api/chat",
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        return data.get("message",{}).get("content",""), None
    except Exception as e:
        return "...", str(e)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION G: SOCIAL FEASIBILITY GATING
# Determines Category A/B/C before any dice are rolled.
# Algorithm handles extremes. Claude handles the middle.
# ═══════════════════════════════════════════════════════════════════════════════

SOCIAL_CLASSIFIER_PROMPT = """You are a rules referee for a D&D game. Given a social action and NPC context, classify feasibility.

NPC: {npc_name}
NPC Motivation: {motivation}
NPC Attitude: {attitude}
NPC Will Never: {will_never}
Player Request: {request}
Request Stakes: {stakes}

Respond with ONLY this JSON (no other text):
{{"feasibility":"impossible|very_unlikely|possible|likely","reason":"one sentence","modifier":0,"category":"A|B|C"}}

Category A = roll dice normally (modifier 0 to +2)
Category B = roll with penalty (modifier -2 to -8)
Category C = no roll, automatic refusal (modifier irrelevant)

impossible = Category C
very_unlikely = Category B, modifier -6 to -8
possible = Category A or B, modifier -2 to +0
likely = Category A, modifier +1 to +2"""

def assess_social_feasibility_algorithmic(npc_profile, request_text):
    """
    Fast algorithmic check for obvious Category C actions.
    Returns (category, reason) or None if AI classification needed.
    """
    will_never = [w.lower() for w in npc_profile.get("will_never",[])]
    motivation = npc_profile.get("motivation","").lower()
    request_lower = request_text.lower()

    # Hard impossible: direct contradictions to core motivation
    # e.g. asking king to abdicate, asking guard to betray their post
    for forbidden in will_never:
        if any(word in request_lower for word in forbidden.split()):
            return ("C", f"This NPC has stated they will never do this: {forbidden}")

    # Hard impossible: physically impossible requests
    impossible_phrases = [
        "give me your kingdom","give me your throne","give me your crown",
        "become my slave","worship me","kill yourself","betray your god",
    ]
    if any(phrase in request_lower for phrase in impossible_phrases):
        return ("C", "This request is fundamentally contrary to any reasonable NPC's interests.")

    # Hard impossible: NPC has no authority over this
    if any(p in request_lower for p in ["give me","hand over","surrender"]):
        assets = npc_profile.get("assets",[])
        if assets:
            if not any(asset.lower() in request_lower for asset in assets):
                return ("C", "The NPC does not possess what is being requested.")

    return None  # Needs AI classification

def assess_social_feasibility_claude(npc_profile, request_text, stakes, api_key):
    """Use Claude Haiku to classify social feasibility for ambiguous cases."""
    prompt = SOCIAL_CLASSIFIER_PROMPT.format(
        npc_name=npc_profile.get("name","Unknown"),
        motivation=npc_profile.get("motivation","unknown"),
        attitude=npc_profile.get("attitude","neutral"),
        will_never=", ".join(npc_profile.get("will_never",["nothing specified"])),
        request=request_text,
        stakes=stakes,
    )

    payload = {
        "model": CLAUDE_PARSE_MODEL,
        "max_tokens": 150,
        "system": "You classify social action feasibility. Return only JSON.",
        "messages": [{"role":"user","content":prompt}]
    }

    try:
        req = urllib.request.Request(CLAUDE_API_URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json","x-api-key":api_key,
                     "anthropic-version":"2023-06-01"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        raw = data["content"][0]["text"].strip()
        raw = re.sub(r"^```json\s*","",raw); raw = re.sub(r"```\s*$","",raw)
        return json.loads(raw)
    except:
        # Fallback: assume possible
        return {"feasibility":"possible","reason":"Unable to classify","modifier":0,"category":"A"}

def resolve_social_action(npc_profile, request_text, pc, api_key=None):
    """
    Full social action resolution pipeline.
    Returns (allowed_to_proceed, reaction_result, feasibility_result)
    """
    # Step 1: Algorithmic gate
    algo_result = assess_social_feasibility_algorithmic(npc_profile, request_text)
    if algo_result:
        category, reason = algo_result
        if category == "C":
            return False, None, {"feasibility":"impossible","reason":reason,"category":"C","modifier":0}

    # Step 2: AI classification (if API key available)
    stakes = _estimate_stakes(npc_profile, request_text)
    if api_key:
        feasibility = assess_social_feasibility_claude(npc_profile, request_text, stakes, api_key)
    else:
        # Conservative default without AI
        feasibility = {"feasibility":"possible","reason":"Default assessment","modifier":0,"category":"A"}

    if feasibility.get("category") == "C" or feasibility.get("feasibility") == "impossible":
        return False, None, feasibility

    # Step 3: Roll reaction (Category A or B)
    modifier = feasibility.get("modifier", 0)
    cha_score = pc.get("stats",{}).get("CHA",10)
    reaction, total, detail = reaction_roll(cha_score, modifier)
    feasibility["reaction_detail"] = detail
    feasibility["reaction"] = reaction

    return True, reaction, feasibility

def _estimate_stakes(npc_profile, request_text):
    """Estimate the cost/stakes of the request to the NPC."""
    request_lower = request_text.lower()
    assets = [a.lower() for a in npc_profile.get("assets",[])]

    major_words = ["life","kingdom","crown","power","position","everything","all of"]
    significant_words = ["secret","betrayal","money","gold","home","family","job"]
    trivial_words = ["tell me","explain","show me","point","direction"]

    if any(w in request_lower for w in major_words):
        return "major — existential cost to NPC"
    if any(w in request_lower for w in significant_words):
        return "significant — meaningful cost to NPC"
    if any(w in request_lower for w in trivial_words):
        return "trivial — minimal cost to NPC"
    return "moderate — some cost to NPC"


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION G: ROOMS (in-memory game rooms for multiplayer)
# ═══════════════════════════════════════════════════════════════════════════════
import uuid as _uuid
_rooms = {}

def create_room(host_name):
    code = _uuid.uuid4().hex[:6].upper()
    _rooms[code] = {
        "code": code, "host": host_name, "players": {host_name: {}},
        "moduleText": "", "moduleName": "", "moduleData": {},
        "chosenRules": "OSE Advanced Fantasy", "gameState": {},
        "partyPCs": {}, "history": [], "gameActive": False,
        "systemPrompt": "", "chat": [],
    }
    return code

def get_room(code): return _rooms.get(code)

def join_room(code, player_name):
    room = _rooms.get(code)
    if not room: return None, "Room not found"
    if player_name not in room["players"]: room["players"][player_name] = {}
    return room, None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION H: OLLAMA STATUS + NGROK
# ═══════════════════════════════════════════════════════════════════════════════
_ollama_available = False
_ollama_model = "mistral-nemo:12b"

def check_ollama():
    global _ollama_available, _ollama_model
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3) as r:
            data = json.loads(r.read())
        models = [m["name"] for m in data.get("models",[])]
        preferred = ["mistral-nemo:12b","llama3:8b","mistral:7b","gemma:7b"]
        for p in preferred:
            if any(p in m for m in models):
                _ollama_model = p; _ollama_available = True; return
        if models: _ollama_model = models[0]; _ollama_available = True
    except: _ollama_available = False

_ngrok_url = ""
_ngrok_proc = None

def start_ngrok():
    global _ngrok_url, _ngrok_proc
    import shutil, subprocess
    ngrok_bin = shutil.which("ngrok")
    if not ngrok_bin: return ""
    try:
        _ngrok_proc = subprocess.Popen([ngrok_bin,"http",str(PORT),"--log=stdout"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2.5)
        for _ in range(6):
            try:
                with urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=3) as r:
                    data = json.loads(r.read())
                for t in data.get("tunnels",[]):
                    if t.get("proto") == "https":
                        _ngrok_url = t["public_url"]; return _ngrok_url
            except: time.sleep(1)
    except: pass
    return ""

def stop_ngrok():
    global _ngrok_proc
    if _ngrok_proc:
        try: _ngrok_proc.terminate()
        except: pass
        _ngrok_proc = None


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION I: MAIN REQUEST PIPELINE
# Orchestrates all four layers for each player action.
# ═══════════════════════════════════════════════════════════════════════════════

def process_player_action(text, pc, game_state, history, api_key, room=None):
    """
    Full V4 pipeline:
    Layer 1 → Layer 2 → Layer 3 → Layer 4
    Returns dict: {display_rolls, narration, state_changes, error, rejection}
    """

    # ── Layer 1: Validation ───────────────────────────────────────────────────
    validation = validate_action(text, pc, game_state)
    if not validation.valid:
        return {
            "rejection": validation.rejection,
            "display_rolls": [],
            "narration": None,
            "state_changes": {},
            "error": None,
        }

    # ── Layer 2: Intent Parsing ───────────────────────────────────────────────
    if api_key:
        action_chain = parse_intent_claude(text, pc, game_state, api_key)
    else:
        action_chain = parse_intent_ollama(text, pc, game_state, _ollama_model)

    if not action_chain:
        # Fallback: use what the validator already determined
        action_chain = [{"type": validation.action_type or "other",
                         **validation.parsed}]

    # ── Special case: social action ───────────────────────────────────────────
    first_action = action_chain[0] if action_chain else {}
    if first_action.get("type") == "social":
        npc_name = first_action.get("target","")
        npc_profile = _find_npc_profile(npc_name, game_state)
        if npc_profile:
            allowed, reaction, feasibility = resolve_social_action(
                npc_profile, text, pc, api_key)
            if not allowed:
                return {
                    "rejection": None,
                    "display_rolls": [],
                    "narration": f"[{feasibility.get('reason','')}]",
                    "state_changes": {},
                    "social_result": feasibility,
                    "error": None,
                }
            # Get NPC dialogue
            dialogue, err = get_npc_dialogue(
                npc_profile, text, feasibility, history[-6:], api_key, _ollama_model)
            if feasibility.get("reaction_detail"):
                display_rolls = [feasibility["reaction_detail"]]
            else:
                display_rolls = []
            return {
                "rejection": None,
                "display_rolls": display_rolls,
                "narration": dialogue,
                "state_changes": {},
                "social_result": feasibility,
                "error": None,
            }

    # -- Build parse display line from action chain --------------------------
    def _fmt_parse(text_raw, actions, pc_name):
        if not actions:
            return None
        a   = actions[0]
        t   = a.get("type", "other")
        sub = f"[{pc_name}]"
        if t == "attack":
            w    = a.get("weapon") or a.get("weapon_name") or "weapon"
            tgt  = a.get("target", "")
            verb = "[shoots]" if a.get("is_ranged") else "[strikes]"
            return sub + " " + verb + (" ["+tgt+"]" if tgt else "") + " with [" + w + "]"
        elif t == "cast":
            sp  = a.get("spell", "spell")
            tgt = a.get("target", "")
            return sub + " [casts] [" + sp + "]" + (" at ["+tgt+"]" if tgt else "")
        elif t == "use_item":
            it  = a.get("item", "item")
            tgt = a.get("target", "")
            return sub + " [uses] [" + it + "]" + (" on ["+tgt+"]" if tgt and tgt != "self" else "")
        elif t == "move":
            loc = a.get("destination") or a.get("direction") or "?"
            return sub + " [moves] [" + loc + "]"
        elif t == "skill":
            sk  = a.get("skill", "skill")
            tgt = a.get("target", "")
            return sub + " [uses] [" + sk + "]" + (" on ["+tgt+"]" if tgt else "")
        elif t == "social":
            return sub + " [speaks] to [" + a.get("target", "NPC") + "]"
        elif t == "rest":
            return sub + " [rests] [" + a.get("rest_type", "rest") + "]"
        elif t == "examine":
            return sub + " [examines] [" + a.get("target", "surroundings") + "]"
        else:
            raw = text_raw[:60] + ("..." if len(text_raw) > 60 else "")
            return sub + " -> " + raw

    _parse_line = _fmt_parse(text, action_chain, pc.get("name", "Player"))

        # ── Layer 3: Mechanical Resolution ───────────────────────────────────────
    all_display = []
    combined_state = {}
    final_result = None

    for action in action_chain:
        # Merge action into validation parsed data
        merged_parsed = {**validation.parsed, **action}
        merged_validation = ValidationResult(True, action.get("type", validation.action_type), merged_parsed)

        result = resolve_action(merged_validation, pc, game_state)
        all_display.extend(result.display_lines)
        combined_state.update(result.state_changes)

        # Chain: if this action has a chain_on_success and it succeeded
        chain = action.get("chain_on_success")
        if chain and result.success:
            chain_validation = ValidationResult(True, chain.get("type","other"), chain)
            chain_result = resolve_action(chain_validation, pc, game_state)
            all_display.extend(chain_result.display_lines)
            combined_state.update(chain_result.state_changes)

        final_result = result

    # Prepend parse line so display order: parse -> dice -> narration
    if _parse_line:
        all_display.insert(0, "PARSE:" + _parse_line)

        # ── Layer 4: Narration ────────────────────────────────────────────────────
    prompt_context = {
        **game_state,
        "party_pcs": room.get("partyPCs",{}) if room else {pc.get("name",""): pc},
        "pc_summary": f"{pc.get('name')} the {pc.get('cls')} Lv{pc.get('level',1)}",
    }

    if final_result:
        result_dict = final_result.to_dict()
        result_dict["display_lines"] = all_display
        result_dict["state_changes"] = combined_state
    else:
        result_dict = {"action_type":"other","display_lines":all_display,
                       "state_changes":combined_state,"success":True,"error":None,
                       "narration_context":{"raw_action":text}}

    # Try Ollama first, Claude as fallback
    narration = None
    if _ollama_available:
        narration, err = narrate_ollama(result_dict, prompt_context, _ollama_model, history)
    if not narration and api_key:
        narration, err = narrate_claude(result_dict, prompt_context, api_key, history)
    if not narration:
        narration = _fallback_narration(result_dict)

    return {
        "rejection": None,
        "display_rolls": all_display,
        "narration": narration,
        "state_changes": combined_state,
        "error": None,
    }

def _find_npc_profile(npc_name, game_state):
    module_data = game_state.get("module_data",{})
    npcs = module_data.get("npcs",[])
    npc_name_lower = npc_name.lower()
    for npc in npcs:
        if npc.get("name","").lower() == npc_name_lower or            npc_name_lower in npc.get("name","").lower():
            return npc
    # Check NPCs present in current room
    for npc in game_state.get("npcs_present",[]):
        if npc.get("name","").lower() == npc_name_lower:
            return npc
    return None

def _fallback_narration(result_dict):
    """Emergency fallback when both AI systems are unavailable."""
    lines = result_dict.get("display_lines",[])
    if lines:
        return "The action resolves. " + " ".join(lines)
    return "The action is attempted."


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION J: LEVEL UP SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

def check_level_up(pc):
    """Check if PC has enough XP to level up. Returns new_level or None."""
    cls = pc.get("cls","Fighter")
    xp = pc.get("xp",0)
    current_level = pc.get("level",1)
    new_level = get_level_for_xp(cls, xp)
    if new_level > current_level:
        return new_level
    return None

def apply_level_up(pc, new_level):
    """Apply level up to PC. Returns list of changes."""
    cls = pc.get("cls","Fighter")
    old_level = pc.get("level",1)
    changes = []

    # Roll HP gain
    hd = OSE_CLASSES.get(cls,{}).get("hd",4)
    hp_roll, rolls = roll(hd)
    con_bonus = stat_mod(pc.get("stats",{}).get("CON",10))
    hp_gain = max(1, hp_roll + con_bonus)
    pc["maxhp"] = pc.get("maxhp",hp_roll) + hp_gain
    pc["hp"] = pc.get("hp",0) + hp_gain
    changes.append(f"HP +{hp_gain} (d{hd}=[{rolls[0]}]+{con_bonus})")

    # Update THAC0
    old_thac0 = get_thac0(cls, old_level)
    new_thac0 = get_thac0(cls, new_level)
    if new_thac0 < old_thac0:
        changes.append(f"THAC0 improved: {old_thac0} → {new_thac0}")

    # Update saves
    new_saves = get_saves(cls, new_level)
    pc["saves"] = new_saves
    changes.append("Saving throws updated")

    # New spell slots
    old_slots = get_spell_slots(cls, old_level)
    new_slots = get_spell_slots(cls, new_level)
    if len(new_slots) > len(old_slots) or        any(new_slots[i] > old_slots[i] for i in range(min(len(new_slots),len(old_slots)))):
        changes.append(f"Spell slots: {new_slots}")
        pc["spell_slots_total"] = new_slots
        pc["spell_slots_remaining"] = new_slots[:]

    # New abilities
    new_abilities = get_class_abilities_for_level(cls, new_level)
    old_abilities_names = [a["name"] for a in get_class_abilities_for_level(cls, old_level)]
    gained = [a for a in new_abilities if a["name"] not in old_abilities_names]
    for ab in gained:
        changes.append(f"New ability: {ab['name']} — {ab['desc']}")

    # Update level
    pc["level"] = new_level
    pc["thac0"] = new_thac0

    return changes


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION K: MODULE LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_module(filename):
    """Load a .dndmod file. Returns (module_data, module_text, error)."""
    import sys
    search_paths = [
        MODULES_DIR / filename,
        pathlib.Path(filename),
        pathlib.Path.home() / "Documents" / "DnDAdventure" / filename,
        pathlib.Path.home() / "Desktop" / filename,
    ]
    # Also try script directory
    try:
        search_paths.append(pathlib.Path(sys.argv[0]).parent / filename)
    except: pass
    for path in search_paths:
        if path.exists():
            try:
                with open(path) as f:
                    data = json.load(f)
                text = _build_module_text(data)
                return data, text, None
            except Exception as e:
                return None, None, str(e)
    return None, None, f"Module file not found: {filename}"

def _build_module_text(data):
    """Build compact module reference text for the narrator prompt."""
    lines = [
        f"MODULE: {data.get('title','Unknown')}",
        f"SYSTEM: {data.get('system','OSE Advanced Fantasy')}",
        f"SETTING: {data.get('setting','')}",
        "",
        f"BACKGROUND: {data.get('background','')}",
        f"CORE TENSION: {data.get('core_tension','')}",
        f"MAIN THREAT: {data.get('main_threat','')}",
        "",
        "=== LOCATIONS ===",
    ]
    for loc in data.get("locations",[]):
        lines.append(f"--- {loc.get('name',loc.get('id',''))} (Room {loc.get('id','')}) ---")
        lines.append(f"[PLAYER SEES]: {loc.get('read_aloud',loc.get('what_players_see',''))}")
        lines.append(f"[GM]: {loc.get('gm_description','')}")
        exits = loc.get("exits",{}); 
        if exits: lines.append(f"[EXITS]: {json.dumps(exits)}")
        for m in loc.get("monsters",[]):
            lines.append(f"[MONSTER]: {m.get('name','')} — {m.get('what_players_see',m.get('gm_description',''))}")
            lines.append(f"  [GM STATS]: HP {m.get('hp_each','?')} AC {m.get('ac','?')} Atk {m.get('attack','?')} Dmg {m.get('damage','?')} ML {m.get('morale','?')} XP {m.get('xp','?')} Morale {m.get('morale','?')} THAC0 {m.get('thac0',19)}")
        for npc in loc.get("npcs_present",[]):
            lines.append(f"[NPC]: {npc}")
    lines.append("")
    lines.append("=== KEY FACTS (never forget) ===")
    for i, fact in enumerate(data.get("key_facts",[]),1):
        lines.append(f"  {i}. {fact}")
    return "\n".join(lines)

def list_modules():
    """List available .dndmod files."""
    import sys
    mods = []
    seen = set()
    # Search all plausible locations
    search_paths = [
        MODULES_DIR,
        pathlib.Path("."),
        pathlib.Path(__file__).parent if "__file__" in dir() else pathlib.Path("."),
        pathlib.Path.home() / "Documents" / "DnDAdventure",
        pathlib.Path.home() / "Desktop",
    ]
    # Also add the script's own directory
    try:
        search_paths.append(pathlib.Path(sys.argv[0]).parent)
    except: pass

    for p in search_paths:
        try:
            for f in p.glob("*.dndmod"):
                if f.name in seen: continue
                seen.add(f.name)
                try:
                    with open(f) as fp: d = json.load(fp)
                    mods.append({"file":f.name,"title":d.get("title",f.name),
                                 "level":d.get("level_range",""),"system":d.get("system","OSE"),
                                 "path":str(f)})
                except: pass
        except: pass
    return mods

def save_game(save_id, data):
    path = SAVES_DIR / f"{save_id}.json"
    with open(path,"w") as f: json.dump(data, f, indent=2)
    return str(path)

def load_game_save(save_id):
    path = SAVES_DIR / f"{save_id}.json"
    if not path.exists(): return None, "Save not found"
    with open(path) as f: return json.load(f), None

def list_saves():
    saves = []
    for p in SAVES_DIR.glob("*.json"):
        try:
            with open(p) as f: d = json.load(f)
            saves.append({"id":p.stem,"name":d.get("pcName",p.stem),
                          "module":d.get("moduleName",""),"level":d.get("pc",{}).get("level",1),
                          "savedAt":d.get("savedAt",0)})
        except: pass
    return sorted(saves, key=lambda x: -x.get("savedAt",0))


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION L: HTTP SERVER
# ═══════════════════════════════════════════════════════════════════════════════

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args): pass

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Access-Control-Allow-Origin","*")
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html):
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type","text/html; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store, no-cache, must-revalidate")
        self.send_header("Pragma","no-cache")
        self.send_header("Expires","0")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin","*")
        self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers","Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        params = {}
        if "?" in self.path:
            params = dict(urllib.parse.parse_qsl(self.path.split("?")[1]))

        if path == "/" or path == "/index.html":
            self.send_html(HTML)
        elif path == "/status":
            self.send_json({
                "ollama": _ollama_available, "model": _ollama_model,
                "version": VERSION, "ngrok_url": _ngrok_url,
            })
        elif path == "/list_modules":
            self.send_json({"modules": list_modules()})
        elif path == "/list_saves":
            self.send_json({"saves": list_saves()})
        elif path == "/load_module":
            fname = params.get("file","")
            data, text, err = load_module(fname)
            if err: self.send_json({"error": err}); return
            self.send_json({"data": data, "text": text,
                            "title": data.get("title",""), "error": None})
        elif path == "/load_save":
            sid = params.get("id","")
            data, err = load_game_save(sid)
            if err: self.send_json({"error": err}); return
            self.send_json({"save": data, "error": None})
        elif path == "/ngrok_status":
            self.send_json({"url": _ngrok_url, "active": bool(_ngrok_url)})
        elif path == "/get_room":
            code = params.get("code","")
            room = get_room(code)
            if not room: self.send_json({"error":"Room not found"}); return
            self.send_json({k:v for k,v in room.items() if k != "history"})
        # ── V3 compatibility aliases ──────────────────────────────────────
        elif path == "/ollama_status":
            self.send_json({
                "available": _ollama_available,
                "model": _ollama_model,
                "ollama": _ollama_available,
                "status": "ok" if _ollama_available else "unavailable",
            })
        elif path == "/saves":
            self.send_json({"saves": list_saves()})
        elif path in ("/load", "/load_save"):
            sid = params.get("id","")
            data, err = load_game_save(sid)
            if err: self.send_json({"error": err}); return
            # Return flat save data (JS loadSave reads properties directly)
            if isinstance(data, dict):
                self.send_json({**data, "error": None})
            else:
                self.send_json({"error": "Invalid save data"})
        elif path in ("/delete_save", "/delete"):
            sid = params.get("id","")
            path_file = SAVES_DIR / f"{sid}.json"
            try:
                if path_file.exists(): path_file.unlink()
                self.send_json({"ok": True})
            except Exception as e:
                self.send_json({"error": str(e)})
        elif path == "/ping":
            self.send_json({"ok": True, "version": VERSION})
        elif path in ("/characters", "/character"):
            cid = params.get("id","")
            chars_dir = SAVES_DIR / "characters"
            chars_dir.mkdir(exist_ok=True)
            if cid:
                cp = chars_dir / f"{cid}.json"
                if cp.exists():
                    with open(cp) as f: self.send_json(json.load(f))
                else:
                    self.send_json({"error":"Not found"}, 404)
            else:
                chars = []
                for p in chars_dir.glob("*.json"):
                    try:
                        with open(p) as f: d = json.load(f)
                        chars.append(d)
                    except: pass
                self.send_json({"characters": chars})
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        elif path == "/game.js":
            import base64 as _b64
            body = _b64.b64decode(JS_BUNDLE_B64)
            self.send_response(200)
            self.send_header("Content-Type","application/javascript; charset=utf-8")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Cache-Control","no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
        elif path == "/game.js":
            body = JS_BUNDLE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_json({"error":"Not found"}, 404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length",0))
        body = json.loads(self.rfile.read(length)) if length else {}
        path = self.path.split("?")[0]

        if path == "/action":
            self._handle_action(body)
        elif path == "/save_game":
            sid = body.get("id", _uuid.uuid4().hex[:8])
            save_game(sid, body.get("data",{}))
            self.send_json({"id": sid, "ok": True})
        elif path == "/create_room":
            code = create_room(body.get("host","Host"))
            self.send_json({"code": code})
        elif path == "/join_room":
            room, err = join_room(body.get("code",""), body.get("player",""))
            if err: self.send_json({"error":err}); return
            self.send_json({k:v for k,v in room.items() if k != "history"})
        elif path == "/update_room":
            code = body.get("code","")
            room = get_room(code)
            if room:
                for k in ["moduleText","moduleName","moduleData","chosenRules",
                          "partyPCs","gameState","gameActive","history","systemPrompt"]:
                    if k in body: room[k] = body[k]
            self.send_json({"ok": bool(room)})
        elif path == "/chat":
            code = body.get("code","")
            room = get_room(code)
            if room:
                room.setdefault("chat",[]).append({
                    "player": body.get("player",""), "msg": body.get("msg",""),
                    "type": body.get("type","normal"), "ts": time.time()
                })
            self.send_json({"ok": True})
        elif path == "/get_chat":
            code = body.get("code","")
            room = get_room(code)
            since = body.get("since",0)
            msgs = [m for m in (room or {}).get("chat",[]) if m.get("ts",0) > since]
            self.send_json({"messages": msgs})
        # ── V3 compatibility aliases ──────────────────────────────────────
        elif path in ("/save", "/save_game"):
            sid = body.get("id", _uuid.uuid4().hex[:8])
            data = body.get("data", body)  # accept either {id, data} or flat save
            if isinstance(data, dict):
                data["id"] = sid
                data.setdefault("savedAt", int(time.time() * 1000))
            save_game(sid, data)
            self.send_json({"id": sid, "ok": True})
        elif path in ("/load", "/load_save"):
            sid = body.get("id","")
            data, err = load_game_save(sid)
            if err: self.send_json({"error": err}); return
            self.send_json({"save": data, "error": None})
        elif path == "/save_character":
            chars_dir = SAVES_DIR / "characters"
            chars_dir.mkdir(exist_ok=True)
            char_data = body.get("character", body)
            cid = char_data.get("id", _uuid.uuid4().hex[:8])
            char_data["id"] = cid
            with open(chars_dir / f"{cid}.json", "w") as f:
                json.dump(char_data, f, indent=2)
            self.send_json({"id": cid, "ok": True})
        elif path == "/player_ready":
            code = body.get("code","")
            player = body.get("player","")
            room = get_room(code)
            if room:
                room["players"].setdefault(player, {})["ready"] = True
                all_ready = all(p.get("ready") for p in room["players"].values())
                if all_ready: room["gameActive"] = True
            self.send_json({"ok": bool(room), "all_ready": all_ready if room else False})
        elif path == "/push_message":
            code = body.get("code","")
            room = get_room(code)
            if room:
                room.setdefault("history",[]).append({
                    "role": body.get("role","assistant"),
                    "content": body.get("content",""),
                    "player": body.get("player",""),
                    "ts": time.time(),
                })
            self.send_json({"ok": bool(room)})
        elif path == "/ai":
            # AI endpoint used by callAI() for opening narration and GM responses
            api_key = body.get("api_key","")
            messages = body.get("messages",[])
            system = body.get("system","")
            content = ""
            if _ollama_available:
                try:
                    payload = {
                        "model": _ollama_model,
                        "system": system,
                        "messages": messages[-16:] if len(messages)>16 else messages,
                        "stream": False,
                        "options": {"temperature": 0.75, "num_ctx": 4096}
                    }
                    req = urllib.request.Request("http://localhost:11434/api/chat",
                        data=json.dumps(payload).encode(),
                        headers={"Content-Type":"application/json"})
                    with urllib.request.urlopen(req, timeout=90) as resp:
                        data = json.loads(resp.read())
                    content = data.get("message",{}).get("content","")
                except Exception as e:
                    print(f"[/ai] Ollama error: {e}")
            if not content and api_key:
                try:
                    payload = {
                        "model": CLAUDE_NARRATE_MODEL,
                        "max_tokens": 800,
                        "system": system,
                        "messages": messages[-16:] if len(messages)>16 else messages
                    }
                    req = urllib.request.Request(CLAUDE_API_URL,
                        data=json.dumps(payload).encode(),
                        headers={"Content-Type":"application/json",
                                 "x-api-key": api_key,
                                 "anthropic-version":"2023-06-01"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read())
                    content = data["content"][0]["text"]
                except Exception as e:
                    print(f"[/ai] Claude error: {e}")
            if not content:
                content = "The Game Master considers the situation..."
            self.send_json({"content": content})
        elif path == "/roll":
            # V3 legacy roll endpoint
            roll_type = body.get("type","dice")
            char = body.get("char", {})
            if roll_type == "attack":
                weapon_name = body.get("weapon","Sword")
                target_ac = body.get("target_ac", 9)
                melee = body.get("melee", True)
                magic_bonus = body.get("magic_bonus", 0)
                result = resolve_attack(char, weapon_name, target_ac,
                                        not melee, False, magic_bonus)
                self.send_json({
                    "hit": result["hit"], "damage": result["damage"],
                    "nat20": result["nat20"], "nat1": result["nat1"],
                    "d20": result["d20"], "fmt": result["display"],
                })
            elif roll_type == "save":
                save_type = body.get("save_type","spells")
                mod = body.get("modifier",0)
                success, d20_roll, target, detail = resolve_saving_throw(char, save_type, mod)
                self.send_json({"success": success, "roll": d20_roll,
                                "target": target, "fmt": detail})
            elif roll_type == "thief_skill":
                skill = body.get("skill","Open Locks")
                success, d100, target, detail = resolve_thief_skill(char, skill)
                self.send_json({"success": success, "roll": d100,
                                "target": target, "fmt": detail})
            elif roll_type == "ability_check":
                stat = body.get("stat","STR")
                score = body.get("score",10)
                mod = body.get("modifier",0)
                target_num = 20 - stat_mod(score) - mod
                d20_roll, _ = roll(20)
                success = d20_roll >= target_num
                self.send_json({"success": success, "roll": d20_roll,
                                "target": target_num,
                                "fmt": f"Ability check ({stat}): d20=[{d20_roll}] vs {target_num} — {'SUCCESS' if success else 'FAILED'}"})
            else:
                n = body.get("count",1)
                sides = body.get("sides",6)
                total, rolls = roll(sides, n)
                self.send_json({"total": total, "rolls": rolls,
                                "fmt": f"{n}d{sides}={rolls}={total}"})
        else:
            self.send_json({"error":"Not found"}, 404)

    def _handle_action(self, body):
        text    = body.get("text","")
        pc      = body.get("pc",{})
        gs      = body.get("game_state",{})
        history = body.get("history",[])
        api_key = body.get("api_key","")
        room_code = body.get("room_code","")
        room = get_room(room_code) if room_code else None

        if not text or not pc:
            self.send_json({"error":"Missing text or pc"}); return

        result = process_player_action(text, pc, gs, history, api_key, room)

        # Check for level up
        level_up_info = None
        new_xp = pc.get("xp",0) + result.get("state_changes",{}).get("xp_gain",0)
        if result.get("state_changes",{}).get("xp_gain"):
            test_pc = {**pc, "xp": new_xp}
            new_level = check_level_up(test_pc)
            if new_level:
                level_changes = apply_level_up(test_pc, new_level)
                level_up_info = {
                    "new_level": new_level,
                    "changes": level_changes,
                    "updated_pc": test_pc,
                }

        self.send_json({
            "rejection":    result.get("rejection"),
            "display_rolls": result.get("display_rolls",[]),
            "narration":    result.get("narration",""),
            "state_changes": result.get("state_changes",{}),
            "social_result": result.get("social_result"),
            "level_up":     level_up_info,
            "error":        result.get("error"),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION M: EMBEDDED HTML FRONTEND
# ═══════════════════════════════════════════════════════════════════════════════

JS_BUNDLE_B64 = "LyogdjE3Nzg5MDYxMTkgKi8KY29uc3QgT1NFX01FQ0hBTklDU19SVUxFU19KUyA9IGBPRkZJQ0lBTCBPU0UgQURWQU5DRUQgRkFOVEFTWSBNRUNIQU5JQ1MgLS0gVVNFIE9OTFkgVEhFU0U6CgpST0xMUyBBUkUgSEFORExFRCBCWSBUSEUgU0VSVkVSLiBXaGVuIHlvdSBzZWUgW1JvbGwgcmVzdWx0XSBpbiBjb250ZXh0LCByZXBvcnQgaXQgZmFpdGhmdWxseS4gRG8gTk9UIHJlLXJvbGwgb3Igb3ZlcnJpZGUuCgpPRkZJQ0lBTCBNRUNIQU5JQ1MgT05MWToKLSBBdHRhY2sgcm9sbHM6IGQyMCB2cyBUSEFDMC4gU1RSIG1vZCB0byBtZWxlZSBoaXQgJiBkYW1hZ2UuIERFWCBtb2QgdG8gcmFuZ2VkIGhpdCBvbmx5LiBNaW4gMSBkYW1hZ2Ugb24gYSBoaXQuCi0gU2F2aW5nIHRocm93czogT05MWSB0aGVzZSA1IGNhdGVnb3JpZXMgLS0gRGVhdGgvUG9pc29uLCBXYW5kcywgUGFyYWx5c2lzL1BldHJpZnksIEJyZWF0aCBBdHRhY2tzLCBTcGVsbHMvUm9kcy9TdGF2ZXMuCi0gVGhpZWYgc2tpbGxzIChkJSk6IE9wZW4gTG9ja3MsIEZpbmQgVHJhcHMsIFJlbW92ZSBUcmFwcywgQ2xpbWIgV2FsbHMsIE1vdmUgU2lsZW50bHksIEhpZGUgaW4gU2hhZG93cywgUGljayBQb2NrZXRzLiBPTkxZIGZvciBUaGllZi9BY3JvYmF0L0Fzc2Fzc2luIGNsYXNzZXMuCi0gSW5pdGlhdGl2ZTogZDYgcGVyIHNpZGUuIFRpZXMgZ28gdG8gcGxheWVycy4KLSBNb3JhbGU6IDJkNiB2cyBtb3JhbGUgc2NvcmUgd2hlbiBtb25zdGVyIGlzIHJlZHVjZWQgdG8gaGFsZiBIUCBvciBsZWFkZXIgZGllcy4KLSBSZWFjdGlvbiByb2xsczogMmQ2ICsgQ0hBIG1vZGlmaWVyIG9uIGZpcnN0IE5QQyBlbmNvdW50ZXIuCi0gU2VhcmNoaW5nOiBkNj0xIHN1Y2Nlc3MgKGQ2PTEtMiBmb3IgRWx2ZXMvSGFsZi1FbHZlcykuIEFOWSBjaGFyYWN0ZXIgY2FuIHNlYXJjaC4gVGFrZXMgMSB0dXJuLgotIEhlYXIgTm9pc2U6IGQ2PTEtMiBzdWNjZXNzIGZvciBub24tdGhpZXZlcy4gVGhpZXZlcyB1c2Ugc2tpbGwgdGFibGUuCi0gRm9yY2UgRG9vcjogZDY9MS0yIHN1Y2Nlc3MuCi0gQWJpbGl0eSBjaGVja3MgKG9wdGlvbmFsKTogZDIwIHVuZGVyIGFiaWxpdHkgc2NvcmUgZm9yIHVuY2VydGFpbiB0YXNrcy4KCkFCU09MVVRFTFkgRk9SQklEREVOIC0tIE5FVkVSIFNBWSBPUiBVU0U6Ci0gIk1ha2UgYSBQZXJjZXB0aW9uIGNoZWNrIiAobm90IGluIE9TRSAtLSB1c2Ugc2VhcmNoaW5nIHJ1bGVzKQotICJSb2xsIFN0ZWFsdGgiIChub3QgaW4gT1NFIC0tIHVzZSBIaWRlIGluIFNoYWRvd3Mgb3Igc3VycHJpc2UpCi0gIlJvbGwgSW5zaWdodC9BdGhsZXRpY3MvSW52ZXN0aWdhdGlvbi9BY3JvYmF0aWNzIiAoNWUgc2tpbGxzLCBub3QgaW4gT1NFKQotIFByb2ZpY2llbmN5IGJvbnVzLCBBZHZhbnRhZ2UsIERpc2FkdmFudGFnZSwgQ29uY2VudHJhdGlvbiwgQm9udXMgYWN0aW9ucyAoYWxsIDVlKQotICJSb2xsIERDIFgiIC0tIE9TRSB1c2VzIHRhcmdldCBudW1iZXJzIG5vdCBEQ3MKLSBBbnkgc2tpbGwgY2hlY2sgYnkgYSBub24tdGhpZWYgZm9yIHRhc2tzIG9ubHkgdGhpZXZlcyBjYW4gcGVyZm9ybSAocGljayBsb2NrcywgZmluZCB0cmFwcykKSWYgeW91IGFyZSB1bnN1cmUgd2hldGhlciBhIG1lY2hhbmljIGV4aXN0cyBpbiBPU0U6IGl0IHByb2JhYmx5IGRvZXNuJ3QuIFVzZSByZWZlcmVlIGp1ZGdtZW50IGluc3RlYWQuYDsKCmNvbnN0IFJVTEVTX1RFWFQgPSB7CiAgT1NFOmBSVUxFUzogT2xkLVNjaG9vbCBFc3NlbnRpYWxzIEFkdmFuY2VkIEZhbnRhc3kKLSBBdHRhY2s6IGQyMCArIFNUUiBtb2QgKG1lbGVlKSBvciBERVggbW9kIChyYW5nZWQpLiBGaWdodGVyICsxIHRvIGhpdC4gSGl0IGlmIHJlc3VsdCBtZWV0cy9iZWF0cyB0YXJnZXQgQUMuCi0gRGFtYWdlOiB3ZWFwb24gZGllICsgU1RSIG1vZCAobWVsZWUgb25seSkuIE5hdHVyYWwgMjAgPSBtYXhpbXVtIGRhbWFnZS4KLSBTYXZpbmcgdGhyb3dzIHZhcnkgYnkgY2xhc3MuIEZpZ2h0ZXI6IERlYXRoIDEyLCBXYW5kcyAxMywgUGFyYWx5c2lzIDE0LCBCcmVhdGggMTUsIFNwZWxscyAxNi4KLSBUaGllZiBza2lsbHMgKGQxMDApOiBGaW5kIFRyYXBzIDI1LCBPcGVuIExvY2tzIDI1LCBNb3ZlIFNpbGVudCAzMCwgSGlkZSBpbiBTaGFkb3dzIDIwLCBCYWNrc3RhYiDDlzIgZGFtYWdlIChtdXN0IGJlIGhpZGRlbiBmaXJzdCkuCi0gTWFnaWMtVXNlcjogMSBzcGVsbCBzbG90L2RheSBhdCBsZXZlbCAxLiBTbGVlcCA9IDJkOCBIRCBjcmVhdHVyZXMgc2xlZXAsIG5vIHNhdmUuIE1hZ2ljIE1pc3NpbGUgPSAxZDYrMSwgYXV0by1oaXRzLgotIENsZXJpYzogVHVybiBVbmRlYWQgMmQ2IHZzIHVuZGVhZCBIRCB0b3RhbC4gQ3VyZSBMaWdodCBXb3VuZHMgPSAxZDYrMSBIUC4gMSBzcGVsbC9kYXkgYXQgbGV2ZWwgMS4KLSBNb3JhbGU6IE1vbnN0ZXJzIGNoZWNrIDJkNiB3aGVuIHJlZHVjZWQgdG8gaGFsZiBIUCBvciBsZWFkZXIgZGllcy4KLSBSZXN0OiBSZWNvdmVyIDEgSFAgcGVyIGZ1bGwgbmlnaHQncyByZXN0LiBObyBoZWFsaW5nIHdpdGhvdXQgcmVzdCBvciBtYWdpYy5gLAogICdBRCZEIDFlJzpgUlVMRVM6IEFkdmFuY2VkIEQmRCAxc3QgRWRpdGlvbiBUSEFDMCBzeXN0ZW0uIEZpZ2h0ZXIgVEhBQzAgMjAsIHJvbGwgZDIwLCBzdWJ0cmFjdCBmcm9tIFRIQUMwID0gQUMgaGl0LiBXZWFwb24gc3BlZWQgZmFjdG9ycyBhcHBseS4gU2F2aW5nIHRocm93czogRGVhdGgsIFBldHJpZmljYXRpb24sIFJvZHMvU3RhdmVzLCBCcmVhdGgsIFNwZWxscy4gVmFuY2lhbiBzcGVsbGNhc3RpbmcuYCwKICAnRCZEIDVlJzpgUlVMRVM6IEQmRCA1ZS4gQXR0YWNrOiBkMjAgKyBhYmlsaXR5IG1vZCArIHByb2ZpY2llbmN5IGJvbnVzICgrMikgdnMgQUMuIEFkdmFudGFnZS9kaXNhZHZhbnRhZ2U6IHJvbGwgMmQyMC4gRGVhdGggc2F2ZXM6IDMgc3VjY2Vzc2VzIG9yIGZhaWx1cmVzLiBTaG9ydCByZXN0OiBzcGVuZCBIaXQgRGljZS4gTG9uZyByZXN0OiBmdWxsIHJlY292ZXJ5LmAsCiAgJ0IvWCc6YFJVTEVTOiBCL1ggRCZELiBBdHRhY2sgbWF0cml4IGJ5IGNsYXNzL2xldmVsLiBTYXZpbmcgdGhyb3dzOiBEZWF0aCwgV2FuZHMsIFBhcmFseXNpcywgQnJlYXRoLCBTcGVsbHMuIE1vcmFsZSAyZDYuIEZhc3QgYW5kIGRlYWRseS5gLAogICdQYXRoZmluZGVyIDFlJzpgUlVMRVM6IFBhdGhmaW5kZXIgMWUuIGQyMCArIEJBQiArIG1vZC4gQ01CL0NNRCBmb3IgbWFuZXV2ZXJzLiBGb3J0aXR1ZGUvUmVmbGV4L1dpbGwgc2F2ZXMuIEZ1bGwgYWN0aW9uIGVjb25vbXkuYCwKICAnQ2FsbCBvZiBDdGh1bGh1JzpgUlVMRVM6IENvQyA3ZS4gZDEwMCB1bmRlciBza2lsbCBmb3Igc3VjY2Vzcy4gSGFsZiA9IEhhcmQsIGZpZnRoID0gRXh0cmVtZS4gU2FuaXR5IHBvb2wuIENvbWJhdCBpcyBsZXRoYWwgLS0gYXZvaWQgaXQuIEludmVzdGlnYXRpb24gaXMgY29yZSBnYW1lcGxheS5gLAp9OwoKY29uc3QgQkFTRV9VUkwgPSAnaHR0cDovL2xvY2FsaG9zdDo4MDgwJzsKbGV0IHBsYXllck5hbWUgPSAnJzsKbGV0IGFwaUtleSA9ICcnOwpsZXQgaXNIb3N0ID0gZmFsc2U7CmxldCByb29tQ29kZSA9ICcnOwpsZXQgaXNNdWx0aXBsYXllciA9IGZhbHNlOwpsZXQgbW9kdWxlVGV4dCA9ICcnOwpsZXQgbW9kdWxlTmFtZSA9ICcnOwpsZXQgY2hvc2VuUnVsZXMgPSAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwpsZXQgY2hvc2VuUmFjZSAgPSAnSHVtYW4nOwpsZXQgY2hvc2VuQ2xhc3MgPSAnRmlnaHRlcic7CmxldCByb2xsZWRTdGF0cyAgPSB7fTsKbGV0IHN0YXJ0aW5nR29sZCA9IDA7CmxldCBzZWxlY3RlZEVxdWlwID0ge307CmxldCBleHRyYUl0ZW1zICAgPSBbXTsKbGV0IGdvbGRTcGVudCAgICA9IDA7CmNvbnN0IHNlbGVjdGVkRXF1aXBJdGVtcyA9IG5ldyBTZXQoKTsgIC8vIHRyYWNrcyB0b2dnbGVkIGV4dHJhIGVxdWlwbWVudApsZXQgcGMgPSB7fTsKbGV0IHBhcnR5UENzID0ge307CmxldCBoaXN0b3J5ICA9IFtdOwpsZXQgYnVzeSAgICAgPSBmYWxzZTsKbGV0IHN5c3RlbVByb21wdCA9ICcnOwpsZXQgcG9sbFRpbWVyICA9IG51bGw7CmxldCBsYXN0U2VxICAgID0gMDsKbGV0IHVwbG9hZGVkRmlsZSA9IG51bGw7CmxldCBtZW1vcnlTdW1tYXJ5ICAgPSAnJzsKbGV0IHdvcmxkU3RhdGUgPSB7IG5wY3NfbWV0Ont9LCBsb2NhdGlvbnNfdmlzaXRlZDp7fSwgaXRlbXNfZm91bmQ6W10sIHBsb3RfcG9pbnRzOltdLAogICAgICAgICAgICAgICAgICAgIGRvb3JzX29wZW5lZDpbXSwgdHJhcHNfc3BydW5nOltdLCBtb25zdGVyc19raWxsZWQ6W10sIHF1ZXN0c19hY3RpdmU6W10sIHdvcmxkX2NoYW5nZXM6W10gfTsKbGV0IGdtQnJpZWZpbmcgID0gJyc7CmxldCBucGNLbm93bGVkZ2VNYXAgPSB7fTsKbGV0IG5wY1Byb2ZpbGVzID0ge307CmxldCBsb2NhdGlvbkF0bW9zcGhlcmUgPSB7fTsKbGV0IGN1cnJlbnRBdG1vc3BoZXJlICA9ICcnOwpsZXQgc2Vzc2lvblRvbmUgPSAnZXhwbG9yYXRvcnknOwpsZXQgcGlubmVkRmFjdHMgID0gW107CmxldCB0dXJuQ291bnQgICAgPSAwOwpjb25zdCBTVU1NQVJZX0VWRVJZX05fVFVSTlMgPSA4Owpjb25zdCBNQVhfUElOTkVEX0ZBQ1RTID0gMjA7CmNvbnN0IE1BWF9ISVNUT1JZX0JFRk9SRV9TVU1NQVJZID0gMTY7CmNvbnN0IEJBTk5FRF9QSFJBU0VTX1BPT0wgPSBbCiAgJ1RoZSBhaXIgaXMgaGVhdnkgd2l0aCcsJ1lvdSBub3RpY2UnLCdTdWRkZW5seScsJ0FzIHlvdSBlbnRlcicsJ1RoZSBzbWVsbCBvZicsCiAgJ1lvdSBjYW4gc2VlJywnSXQgYmVjb21lcyBjbGVhcicsJ1lvdSByZWFsaXplJywnV2l0aG91dCB3YXJuaW5nJywnWW91IGZpbmQgeW91cnNlbGYnLAogICdZb3Ugb2JzZXJ2ZScsJ0FzIHlvdSBhcHByb2FjaCcsJ0FzIHlvdSBzdGVwJywnVGhlIGF0bW9zcGhlcmUgaXMnLCdJbmRlZWQnLAogICdDZXJ0YWlubHknLCdDbGVhcmx5JywnT2J2aW91c2x5JywnUXVpY2tseScsJ1NlZW1pbmdseScsCl07CmxldCBiYW5uZWRQaHJhc2VzID0gW107CmxldCBwYWNpbmdIaXN0b3J5ID0gW107CmxldCBjdXJyZW50UGFjaW5nUGhhc2UgPSAnb3BlbmluZyc7CmxldCB0dXJuc1NpbmNlTGFzdENvbWJhdCA9IDA7CmxldCB0dXJuc1NpbmNlTGFzdFJlc3QgICA9IDA7CmxldCBjb25zZXF1ZW5jZXMgPSBbXTsKbGV0IHBlbmRpbmdDb25zZXF1ZW5jZXMgID0gW107CmxldCBkdW5nZW9uVHVybnMgPSAwOwpsZXQgdG9yY2hUdXJuc0xlZnQgPSA2OwpsZXQgaGFzTGFudGVybiA9IGZhbHNlOwpsZXQgbGFudGVybk9pbEZsYXNrc0xlZnQgPSAwOwpsZXQgdG9yY2hMaXQgPSBmYWxzZTsKbGV0IHRvcmNoZXNDYXJyaWVkID0gMDsKbGV0IGxhbnRlcm5MaXQgPSBmYWxzZTsKbGV0IHRvcmNoRXZlclVzZWQgPSBmYWxzZTsKbGV0IHJhdGlvbnNMZWZ0ID0gMDsKbGV0IGRheXNXaXRob3V0Rm9vZCA9IDA7CmxldCB0dXJuc1dpdGhvdXRSZXN0ID0gMDsKbGV0IHJlc3REZWJ0ID0gMDsKbGV0IHN0YXJ2YXRpb25QZW5hbHR5ID0gMDsKbGV0IGZhdGlndWVQZW5hbHR5ID0gMDsKbGV0IGlzQ2FycnlpbmdMaWdodCA9IHRydWU7CmxldCB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOwpsZXQgd2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlID0gZmFsc2U7CmxldCBsb2dFbnRyaWVzID0gW107CmxldCBhY3RpdmVFZmZlY3RzID0gW107CmxldCBzZWxlY3RlZERuZG1vZEZpbGUgPSBudWxsOwpsZXQgb2xsYW1hQXZhaWxhYmxlID0gZmFsc2U7CmxldCB1c2VPbGxhbWEgPSBmYWxzZTsKbGV0IGxhc3RBaVZpYSA9ICcnOwpsZXQgY3NlbENoYXJzICA9IFtdOwpsZXQgY3NlbFNlbGVjdGVkSWQgID0gbnVsbDsKbGV0IGNzZWxQZW5kaW5nU2F2ZSA9IG51bGw7CmxldCBjc2VsUGVuZGluZ0pvaW4gPSBudWxsOwpsZXQgbmdyb2tQdWJsaWNVcmwgID0gJyc7CmxldCBjb252RmlsZVBhdGggPSBudWxsOwpsZXQgY29udlVwbG9hZGVkRmlsZSA9IG51bGw7Cgpjb25zdCBQTEFZRVJfQ09MT1JTID0gWycjN2FiYWZmJywnI2ZmYjA3YScsJyM3YWZmYjAnLCcjZmZkYTdhJywnI2Q5N2FmZicsJyNmZjdhYWEnLCcjN2FmZmZmJ107CmxldCBjb2xvck1hcCA9IHt9Owpjb25zdCBJTlZfV0VBUE9OUyA9IC9zd29yZHxkYWdnZXJ8KD88IWhhbmRccylheGV8KD86bG9uZ3xzaG9ydHxoYW5kKWJvd3xjcm9zc2Jvd3xzcGVhcnxtYWNlfGZsYWlsfHdhcmhhbW1lcnxjbHVifGtuaWZlfGJsYWRlL2k7CmNvbnN0IElOVl9BUk1PVVIgID0gL2FybW91P3J8Y2hhaW4gbWFpbHxwbGF0ZSBtYWlsfGxlYXRoZXIgYXJtb3J8c2hpZWxkfGhlbG1ldHxoZWxtfGdhdW50bGV0cz98Z3JlYXZlc3xicmFjZXJzfHJpbmcgbWFpbHxzY2FsZSBtYWlsfHNwbGludHxiYW5kZWQvaTsKY29uc3QgSU5WX0FNTU8gICAgPSAvXihib2x0cz98YXJyb3dzP3xxdWFycmVscz98c2hvdHM/fHNsaW5nIHN0b25lcz98Y3Jvc3Nib3cgYm9sdHM/KSQvaTsKY29uc3QgSU5WX01BR0lDICAgPSAvcG90aW9ufHNjcm9sbHx3YW5kfHJvZHxhbXVsZXR8Y2hhcm18ZW5jaGFudHxcK1swLTldL2k7CmNvbnN0IEFDVElPTl9UWVBFUyA9IHsKICBDT01CQVQ6ICAgJ2NvbWJhdCcsCiAgU0VBUkNIOiAgICdzZWFyY2gnLAogIFNPQ0lBTDogICAnc29jaWFsJywKICBNT1ZFTUVOVDogJ21vdmVtZW50JywKICBTS0lMTDogICAgJ3NraWxsJywKICBNQUdJQzogICAgJ21hZ2ljJywKICBJVEVNOiAgICAgJ2l0ZW0nLAogIFJFU1Q6ICAgICAncmVzdCcsCiAgT1RIRVI6ICAgICdvdGhlcicsCn07CgoKY29uc3QgT1NFX0FSTU9VUiA9IHsKICAnTGVhdGhlciBBcm1vdXInOiB7YWM6NywgY29zdDoyMCwgIG5vdGVzOicnfSwKICAnQ2hhaW4gTWFpbCc6ICAgICB7YWM6NSwgY29zdDo0MCwgIG5vdGVzOicnfSwKICAnUGxhdGUgTWFpbCc6ICAgICB7YWM6MywgY29zdDo2MCwgIG5vdGVzOidIZWF2eSAtLSBCYXJiYXJpYW5zIGNhbm5vdCB3ZWFyJ30sCiAgJ1NoaWVsZCc6ICAgICAgICAge2FjX2JvbnVzOjEsIGNvc3Q6MTAsIG5vdGVzOicnfSwKfTsKY29uc3QgR09MRF9CWV9DTEFTUyA9IHsKICBGaWdodGVyOjE4MCwnTWFnaWMtVXNlcic6MzAsQ2xlcmljOjEyMCxUaGllZjo5MCwKICBSYW5nZXI6MTUwLFBhbGFkaW46MTgwLERydWlkOjkwLElsbHVzaW9uaXN0OjMwLAogIEFzc2Fzc2luOjkwLEJhcmQ6MTIwLE1vbms6MzAsQmFyYmFyaWFuOjYwCn07Cgpjb25zdCBDTEFTU0VTID0gewogIEZpZ2h0ZXI6ICAgICB7IGljb246JycsICBocDo4LCAgYWM6MTQsIHNhdmVzOntkZWF0aDoxMix3YW5kczoxMyxwYXJhOjE0LGJyZWF0aDoxNSxzcGVsbHM6MTZ9LCBkZXNjOidCZXN0IGNvbWJhdCwgaGlnaGVzdCBIUC4gTXVsdGlwbGUgYXR0YWNrcyBhdCBoaWdoZXIgbGV2ZWxzLiBXZWFwb24gbWFzdGVyeS4nIH0sCiAgJ01hZ2ljLVVzZXInOnsgaWNvbjonJywgIGhwOjQsICBhYzoxMSwgc2F2ZXM6e2RlYXRoOjEzLHdhbmRzOjExLHBhcmE6MTMsYnJlYXRoOjE1LHNwZWxsczoxMn0sIGRlc2M6J1Bvd2VyZnVsIGFyY2FuZSBzcGVsbHMuIEZyYWdpbGUuIFNwZWxsYm9vayBtYWdpYzogU2xlZXAsIE1hZ2ljIE1pc3NpbGUsIERldGVjdCBNYWdpYy4nIH0sCiAgQ2xlcmljOiAgICAgIHsgaWNvbjonJywgIGhwOjYsICBhYzoxMywgc2F2ZXM6e2RlYXRoOjExLHdhbmRzOjEyLHBhcmE6MTQsYnJlYXRoOjE2LHNwZWxsczoxNX0sIGRlc2M6J1R1cm4gdW5kZWFkLCBoZWFsIHdvdW5kcy4gRGl2aW5lIHNwZWxsY2FzdGVyLiBIb2x5IHdhcnJpb3Igb2YgZmFpdGguJyB9LAogIFRoaWVmOiAgICAgICB7IGljb246JycsICBocDo0LCAgYWM6MTIsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxNCxwYXJhOjEzLGJyZWF0aDoxNixzcGVsbHM6MTV9LCBkZXNjOidQaWNrIGxvY2tzLCBmaW5kIHRyYXBzLCBiYWNrc3RhYiB4MiBkYW1hZ2UuIENsaW1iIHdhbGxzLCBoaWRlIGluIHNoYWRvd3MsIG1vdmUgc2lsZW50bHkuJyB9LAogIFJhbmdlcjogICAgICB7IGljb246JycsICBocDo4LCAgYWM6MTMsIHNhdmVzOntkZWF0aDoxMix3YW5kczoxMyxwYXJhOjE0LGJyZWF0aDoxNSxzcGVsbHM6MTZ9LCBkZXNjOidTa2lsbGVkIHRyYWNrZXIuIEJvbnVzIGRhbWFnZSB2cyBodW1hbm9pZHMuIER1YWwgd2llbGQuIFdpbGRlcm5lc3Mgc3Vydml2YWwgZXhwZXJ0LicgfSwKICBQYWxhZGluOiAgICAgeyBpY29uOicnLCAgaHA6OCwgIGFjOjE0LCBzYXZlczp7ZGVhdGg6MTAsd2FuZHM6MTEscGFyYToxMixicmVhdGg6MTMsc3BlbGxzOjE0fSwgZGVzYzonSG9seSB3YXJyaW9yLiBEZXRlY3QgZXZpbCBhdXJhLiBMYXkgb24gaGFuZHMuIEltbXVuZSB0byBkaXNlYXNlLiBBdXJhIG9mIHByb3RlY3Rpb24uJyB9LAogIERydWlkOiAgICAgICB7IGljb246JycsICBocDo2LCAgYWM6MTIsIHNhdmVzOntkZWF0aDoxMCx3YW5kczoxMSxwYXJhOjEzLGJyZWF0aDoxMixzcGVsbHM6MTR9LCBkZXNjOidOYXR1cmUgbWFnaWMuIFNoYXBlY2hhbmdlIGF0IGhpZ2hlciBsZXZlbHMuIFdvb2RsYW5kIGFsbGllcy4gUmVzaXN0IGZpcmUgJiBsaWdodG5pbmcuJyB9LAogIElsbHVzaW9uaXN0OiB7IGljb246JycsICBocDo0LCAgYWM6MTEsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxMSxwYXJhOjEzLGJyZWF0aDoxNSxzcGVsbHM6MTJ9LCBkZXNjOidJbGx1c2lvbiBtYWdpYyBzcGVjaWFsaXN0LiBDb2xvdXIgU3ByYXksIFBoYW50YXNtYWwgRm9yY2UsIEh5cG5vdGlzbSwgTWlycm9yIEltYWdlLicgfSwKICBBc3Nhc3NpbjogICAgeyBpY29uOicnLCAgaHA6NiwgIGFjOjEyLCBzYXZlczp7ZGVhdGg6MTMsd2FuZHM6MTQscGFyYToxMyxicmVhdGg6MTYsc3BlbGxzOjE1fSwgZGVzYzonTWFzdGVyIGtpbGxlci4gRGlzZ3Vpc2UsIHBvaXNvbiB1c2UuIEFzc2Fzc2luYXRpb24gc3RyaWtlIGZvciBpbnN0YW50IGtpbGwgY2hhbmNlLicgfSwKICBCYXJkOiAgICAgICAgeyBpY29uOicnLCAgaHA6NiwgIGFjOjEyLCBzYXZlczp7ZGVhdGg6MTMsd2FuZHM6MTQscGFyYToxMyxicmVhdGg6MTYsc3BlbGxzOjE1fSwgZGVzYzonSmFjayBvZiBhbGwgdHJhZGVzLiBJbnNwaXJlIGFsbGllcywgY2hhcm0uIExvcmUga25vd2xlZGdlLiBUaGllZiBza2lsbHMuJyB9LAogIE1vbms6ICAgICAgICB7IGljb246JycsICBocDo2LCAgYWM6MTAsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxNCxwYXJhOjEzLGJyZWF0aDoxNixzcGVsbHM6MTV9LCBkZXNjOidVbmFybWVkIGNvbWJhdCBtYXN0ZXIuIFVuYXJtb3VyZWQgQUMgYm9udXMuIFN0dW5uaW5nIHN0cmlrZS4gRmFzdCBtb3ZlbWVudC4nIH0sCiAgQmFyYmFyaWFuOiAgIHsgaWNvbjonJywgIGhwOjEwLCBhYzoxMiwgc2F2ZXM6e2RlYXRoOjEyLHdhbmRzOjEzLHBhcmE6MTQsYnJlYXRoOjE1LHNwZWxsczoxNn0sIGRlc2M6J1JhZ2UgZm9yIGJvbnVzIGRhbWFnZS4gSW5zdGluY3RpdmUgQUMgd2hlbiB1bmFybW91cmVkLiBXaWxkZXJuZXNzIHN1cnZpdmFsLiBCZXJzZXJrZXIuJyB9LAp9OwoKY29uc3QgUkFDRVMgPSB7CiAgSHVtYW46ICAgICB7IGljb246JycsIGRlc2M6J0FueSBjbGFzcywgaGlnaGVzdCBsZXZlbCBjYXBzLicsIHNwZWNpYWxzOltdIH0sCiAgRHdhcmY6ICAgICB7IGljb246JycsIGRlc2M6J0luZnJhdmlzaW9uIDYwZnQuICs0IHNhdmUgdnMgbWFnaWMgJiBwb2lzb24uIERldGVjdCBzdG9uZXdvcmsuJywgc3BlY2lhbHM6WydJbmZyYXZpc2lvbiA2MGZ0JywnKzQgc2F2ZSB2cyBtYWdpYy9wb2lzb24nLCdEZXRlY3Qgc3RvbmV3b3JrIHRyYXBzIDEtMi9kNiddLCBjbGFzc2VzOlsnRmlnaHRlcicsJ1RoaWVmJywnQXNzYXNzaW4nXSB9LAogIEVsZjogICAgICAgeyBpY29uOicnLCBkZXNjOidJbmZyYXZpc2lvbiA2MGZ0LiBEZXRlY3Qgc2VjcmV0IGRvb3JzLiBJbW11bmUgdG8gZ2hvdWwgcGFyYWx5c2lzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gNjBmdCcsJ0RldGVjdCBzZWNyZXQgZG9vcnMgMS0yL2Q2JywnSW1tdW5lIHRvIGdob3VsIHBhcmFseXNpcyddLCBjbGFzc2VzOlsnRmlnaHRlcicsJ01hZ2ljLVVzZXInLCdUaGllZicsJ1JhbmdlcicsJ0lsbHVzaW9uaXN0JywnQmFyZCddIH0sCiAgSGFsZmxpbmc6ICB7IGljb246JycsIGRlc2M6Jy0yIEFDIHZzIGxhcmdlIGZvZXMuIFN1cnByaXNlIG9ubHkgMS9kNi4gKzEgdG8gcmFuZ2VkLicsIHNwZWNpYWxzOlsnLTIgQUMgdnMgbGFyZ2UgY3JlYXR1cmVzJywnU3VycHJpc2Ugb24gMS9kNiBvbmx5JywnKzEgdG8gcmFuZ2VkIGF0dGFja3MnXSwgY2xhc3NlczpbJ0ZpZ2h0ZXInLCdUaGllZicsJ0RydWlkJ10gfSwKICAnSGFsZi1FbGYnOnsgaWNvbjonJywgZGVzYzonSW5mcmF2aXNpb24gNjBmdC4gRGV0ZWN0IHNlY3JldCBkb29ycyAxLTMvZDYuIFZlcnNhdGlsZSBjbGFzc2VzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gNjBmdCcsJ0RldGVjdCBzZWNyZXQgZG9vcnMgMS0zL2Q2J10sIGNsYXNzZXM6WydGaWdodGVyJywnTWFnaWMtVXNlcicsJ0NsZXJpYycsJ1RoaWVmJywnUmFuZ2VyJywnQmFyZCcsJ0RydWlkJywnSWxsdXNpb25pc3QnXSB9LAogIEdub21lOiAgICAgeyBpY29uOicnLCBkZXNjOidJbmZyYXZpc2lvbiA5MGZ0LiArNCBzYXZlIHZzIG1hZ2ljLiBTcGVhayB3aXRoIGJ1cnJvd2luZyBhbmltYWxzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gOTBmdCcsJys0IHNhdmUgdnMgbWFnaWMnLCdTcGVhayB3aXRoIGJ1cnJvd2luZyBhbmltYWxzJ10sIGNsYXNzZXM6WydGaWdodGVyJywnVGhpZWYnLCdJbGx1c2lvbmlzdCcsJ0Fzc2Fzc2luJ10gfSwKICAnSGFsZi1PcmMnOnsgaWNvbjonJywgZGVzYzonKzEgU1RSICYgQ09OLiBJbmZyYXZpc2lvbiA2MGZ0LiBJbnRpbWlkYXRpbmcuJywgc3BlY2lhbHM6WydJbmZyYXZpc2lvbiA2MGZ0JywnKzEgU1RSIGFuZCBDT04nXSwgYm9udXNlczp7U1RSOjEsQ09OOjF9LCBjbGFzc2VzOlsnRmlnaHRlcicsJ0NsZXJpYycsJ1RoaWVmJywnQXNzYXNzaW4nLCdCYXJiYXJpYW4nXSB9LAp9OwoKY29uc3QgQ0xBU1NfV0VBUE9OX1JFU1RSSUNUSU9OUyA9IHsKICBGaWdodGVyOiAgICAgIG51bGwsIC8vIGFsbCB3ZWFwb25zCiAgUmFuZ2VyOiAgICAgICBudWxsLAogIFBhbGFkaW46ICAgICAgbnVsbCwKICBCYXJiYXJpYW46ICAgIG51bGwsCiAgQ2xlcmljOiAgICAgICBbJ0NsdWInLCdNYWNlJywnU3RhZmYnLCdXYXIgSGFtbWVyJywnU2xpbmcnLCdTaG9ydCBCb3cnXSwgLy8gYmx1bnQgb25seQogIERydWlkOiAgICAgICAgWydDbHViJywnRGFnZ2VyJywnSGFuZCBBeGUnLCdTcGVhcicsJ1N0YWZmJywnU2xpbmcnLCdTaG9ydCBCb3cnXSwKICAnTWFnaWMtVXNlcic6IFsnRGFnZ2VyJywnU2lsdmVyIERhZ2dlcicsJ1N0YWZmJ10sCiAgSWxsdXNpb25pc3Q6ICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdTdGFmZiddLAogIFRoaWVmOiAgICAgICAgWydEYWdnZXInLCdTaWx2ZXIgRGFnZ2VyJywnQ2x1YicsJ1Nob3J0IFN3b3JkJywnSGFuZCBBeGUnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJ10sCiAgQXNzYXNzaW46ICAgICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdDbHViJywnU2hvcnQgU3dvcmQnLCdIYW5kIEF4ZScsJ01hY2UnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJ10sCiAgQmFyZDogICAgICAgICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdDbHViJywnU2hvcnQgU3dvcmQnLCdIYW5kIEF4ZScsJ01hY2UnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJywnU3dvcmQnLCdTdGFmZiddLAogIE1vbms6ICAgICAgICAgWydDbHViJywnRGFnZ2VyJywnSGFuZCBBeGUnLCdKYXZlbGluJywnU2hvcnQgU3dvcmQnLCdTdGFmZicsJ1NsaW5nJ10sCn07Cgpjb25zdCBDTEFTU19BUk1PVVJfUkVTVFJJQ1RJT05TID0gewogIEZpZ2h0ZXI6WydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdQbGF0ZSBNYWlsJywnU2hpZWxkJ10sCiAgUmFuZ2VyOiBbJ0xlYXRoZXIgQXJtb3VyJywnQ2hhaW4gTWFpbCcsJ1BsYXRlIE1haWwnLCdTaGllbGQnXSwKICBQYWxhZGluOlsnTGVhdGhlciBBcm1vdXInLCdDaGFpbiBNYWlsJywnUGxhdGUgTWFpbCcsJ1NoaWVsZCddLAogIEJhcmJhcmlhbjpbJ0xlYXRoZXIgQXJtb3VyJywnQ2hhaW4gTWFpbCcsJ1NoaWVsZCddLAogIENsZXJpYzogWydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdQbGF0ZSBNYWlsJywnU2hpZWxkJ10sCiAgRHJ1aWQ6ICBbJ0xlYXRoZXIgQXJtb3VyJywnU2hpZWxkJ10sCiAgVGhpZWY6ICBbJ0xlYXRoZXIgQXJtb3VyJ10sCiAgQXNzYXNzaW46WydMZWF0aGVyIEFybW91cicsJ1NoaWVsZCddLAogIEJhcmQ6ICAgWydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdTaGllbGQnXSwKICBNb25rOiAgIFtdLCAvLyBubyBhcm1vdXIKICAnTWFnaWMtVXNlcic6W10sCiAgSWxsdXNpb25pc3Q6W10sCn07Cgpjb25zdCBPU0VfV0VBUE9OUyA9IHsKICAvLyBNZWxlZSAtLSB7ZG1nLCBjb3N0IChncCksIGhhbmRzLCBub3Rlc30KICAnQmF0dGxlIEF4ZSc6ICAgICAgIHtkbWc6JzFkOCcsICBjb3N0OjcsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAnQ2x1Yic6ICAgICAgICAgICAgIHtkbWc6JzFkNCcsICBjb3N0OjAsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczonZnJlZSd9LAogICdEYWdnZXInOiAgICAgICAgICAge2RtZzonMWQ0JywgIGNvc3Q6MywgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2V9LAogICdIYW5kIEF4ZSc6ICAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6NCwgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOidjYW4gdGhyb3cnfSwKICAnTGFuY2UnOiAgICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjEwLCAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczonbW91bnRlZCBvbmx5J30sCiAgJ01hY2UnOiAgICAgICAgICAgICB7ZG1nOicxZDYnLCAgY29zdDo1LCAgIGhhbmRzOjEsIHJhbmdlZDpmYWxzZX0sCiAgJ1BvbGUgQXJtJzogICAgICAgICB7ZG1nOicxZDEwJywgY29zdDo3LCAgIGhhbmRzOjIsIHJhbmdlZDpmYWxzZSwgbm90ZXM6J3R3by1oYW5kZWQnfSwKICAnU2hvcnQgU3dvcmQnOiAgICAgIHtkbWc6JzFkNicsICBjb3N0OjcsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAnU2lsdmVyIERhZ2dlcic6ICAgIHtkbWc6JzFkNCcsICBjb3N0OjMwLCAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczondnMgbHljYW50aHJvcGVzL3VuZGVhZCd9LAogICdTcGVhcic6ICAgICAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6MywgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOidjYW4gdGhyb3cnfSwKICAnU3RhZmYnOiAgICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjAsICAgaGFuZHM6MiwgcmFuZ2VkOmZhbHNlLCBub3RlczondHdvLWhhbmRlZCwgZnJlZSd9LAogICdTd29yZCc6ICAgICAgICAgICAge2RtZzonMWQ4JywgIGNvc3Q6MTAsICBoYW5kczoxLCByYW5nZWQ6ZmFsc2V9LAogICdUd28tSGFuZGVkIFN3b3JkJzoge2RtZzonMWQxMCcsIGNvc3Q6MTUsICBoYW5kczoyLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOid0d28taGFuZGVkLCBubyBzaGllbGQnfSwKICAnV2FyIEhhbW1lcic6ICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjUsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAvLyBSYW5nZWQKICAnQ3Jvc3Nib3cnOiAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjMwLCAgaGFuZHM6MiwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgODAvMTYwLzI0MCwgc2xvdyByZWxvYWQnfSwKICAnSmF2ZWxpbic6ICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjEsICAgaGFuZHM6MSwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgMzAvNjAvOTAnfSwKICAnTG9uZyBCb3cnOiAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjYwLCAgaGFuZHM6MiwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgNzAvMTQwLzIxMCwgc3RyIHJlcSd9LAogICdTaG9ydCBCb3cnOiAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6MjUsICBoYW5kczoyLCByYW5nZWQ6dHJ1ZSwgIG5vdGVzOidyYW5nZSA1MC8xMDAvMTUwJ30sCiAgJ1NsaW5nJzogICAgICAgICAgICB7ZG1nOicxZDQnLCAgY29zdDoyLCAgIGhhbmRzOjEsIHJhbmdlZDp0cnVlLCAgbm90ZXM6J3JhbmdlIDQwLzgwLzE2MCd9LAogIC8vIEFtbW8KICAnQXJyb3dzICgyMCknOiAgICAgIHtkbWc6Jy0nLCAgICBjb3N0OjUsICAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZm9yIGJvd3MnfSwKICAnQ3Jvc3Nib3cgQm9sdHMgKDMwKSc6IHtkbWc6Jy0nLCBjb3N0OjEwLCAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZm9yIGNyb3NzYm93J30sCiAgJ1NpbHZlci1UaXBwZWQgQXJyb3dzICg2KSc6IHtkbWc6Jy0nLCBjb3N0OjMwLCBoYW5kczowLCByYW5nZWQ6dHJ1ZSwgbm90ZXM6J3ZzIGx5Y2FudGhyb3Blcy91bmRlYWQnfSwKICAnU2xpbmcgU3RvbmVzICgyMCknOntkbWc6Jy0nLCAgICBjb3N0OjAsICAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZnJlZSd9LAp9OwoKY29uc3QgT1NFX0VRVUlQTUVOVCA9IHsKICAnQmFja3BhY2snOiAgICAgICAgICAgICAgICAge2Nvc3Q6NX0sCiAgJ0Nyb3diYXInOiAgICAgICAgICAgICAgICAgIHtjb3N0OjEwfSwKICAnR2FybGljJzogICAgICAgICAgICAgICAgICAge2Nvc3Q6NSwgICBub3RlczoncGVyIGhlYWQnfSwKICAnR3JhcHBsaW5nIEhvb2snOiAgICAgICAgICAge2Nvc3Q6MjV9LAogICdIYW1tZXIgKHNtYWxsKSc6ICAgICAgICAgICB7Y29zdDoyfSwKICAnSG9seSBTeW1ib2wnOiAgICAgICAgICAgICAge2Nvc3Q6MjV9LAogICdIb2x5IFdhdGVyICh2aWFsKSc6ICAgICAgICB7Y29zdDoyNX0sCiAgJ0lyb24gU3Bpa2VzICgxMiknOiAgICAgICAgIHtjb3N0OjF9LAogICdMYW50ZXJuJzogICAgICAgICAgICAgICAgICB7Y29zdDoxMH0sCiAgJ01pcnJvciAoaGFuZC1zaXplZCwgc3RlZWwpJzp7Y29zdDo1fSwKICAnT2lsICgxIGZsYXNrKSc6ICAgICAgICAgICAge2Nvc3Q6Mn0sCiAgJ1BvbGUgKDEwZnQgd29vZGVuKSc6ICAgICAgIHtjb3N0OjF9LAogICdSYXRpb25zIChpcm9uLCA3IGRheXMpJzogICB7Y29zdDoxNSwgbm90ZXM6J3ByZXNlcnZlZCd9LAogICdSYXRpb25zIChzdGFuZGFyZCwgNyBkYXlzKSc6e2Nvc3Q6NX0sCiAgJ1JvcGUgKDUwZnQpJzogICAgICAgICAgICAgIHtjb3N0OjF9LAogICdTYWNrIChsYXJnZSknOiAgICAgICAgICAgICB7Y29zdDoyfSwKICAnU2FjayAoc21hbGwpJzogICAgICAgICAgICAge2Nvc3Q6MX0sCiAgJ1N0YWtlcyAoMykgYW5kIE1hbGxldCc6ICAgIHtjb3N0OjN9LAogICJUaGlldmVzJyBUb29scyI6ICAgICAgICAgICB7Y29zdDoyNX0sCiAgJ1RpbmRlciBCb3ggKGZsaW50ICYgc3RlZWwpJzp7Y29zdDozfSwKICAnVG9yY2hlcyAoNiknOiAgICAgICAgICAgICAge2Nvc3Q6MX0sCiAgJ1dhdGVyc2tpbic6ICAgICAgICAgICAgICAgIHtjb3N0OjF9LAogICdXaW5lICgyIHBpbnRzKSc6ICAgICAgICAgICB7Y29zdDoxfSwKICAnV29sZnNiYW5lICgxIGJ1bmNoKSc6ICAgICAge2Nvc3Q6MTB9LAp9OwoKCmZ1bmN0aW9uIHhockZldGNoKHVybCwgb3B0cykgewogIHJldHVybiBuZXcgUHJvbWlzZSgocmVzb2x2ZSwgcmVqZWN0KSA9PiB7CiAgICBjb25zdCB4aHIgPSBuZXcgWE1MSHR0cFJlcXVlc3QoKTsKICAgIGNvbnN0IG1ldGhvZCA9IChvcHRzICYmIG9wdHMubWV0aG9kKSB8fCAnR0VUJzsKICAgIHhoci5vcGVuKG1ldGhvZCwgdXJsLCB0cnVlKTsKICAgIGlmIChvcHRzICYmIG9wdHMuaGVhZGVycykgewogICAgICBPYmplY3QuZW50cmllcyhvcHRzLmhlYWRlcnMpLmZvckVhY2goKFtrLHZdKSA9PiB4aHIuc2V0UmVxdWVzdEhlYWRlcihrLHYpKTsKICAgIH0KICAgIHhoci50aW1lb3V0ID0gMTgwMDAwOwogICAgeGhyLm9ubG9hZCA9ICgpID0+IHJlc29sdmUoewogICAgICBvazogeGhyLnN0YXR1cyA+PSAyMDAgJiYgeGhyLnN0YXR1cyA8IDMwMCwKICAgICAgc3RhdHVzOiB4aHIuc3RhdHVzLAogICAgICBqc29uOiAoKSA9PiBQcm9taXNlLnJlc29sdmUoSlNPTi5wYXJzZSh4aHIucmVzcG9uc2VUZXh0KSksCiAgICAgIHRleHQ6ICgpID0+IFByb21pc2UucmVzb2x2ZSh4aHIucmVzcG9uc2VUZXh0KSwKICAgIH0pOwogICAgeGhyLm9uZXJyb3IgPSAoKSA9PiByZWplY3QobmV3IEVycm9yKCdOZXR3b3JrIHJlcXVlc3QgZmFpbGVkOiAnICsgbWV0aG9kICsgJyAnICsgdXJsKSk7CiAgICB4aHIub250aW1lb3V0ID0gKCkgPT4gcmVqZWN0KG5ldyBFcnJvcignUmVxdWVzdCB0aW1lZCBvdXQ6ICcgKyBtZXRob2QgKyAnICcgKyB1cmwpKTsKICAgIHhoci5zZW5kKChvcHRzICYmIG9wdHMuYm9keSkgfHwgbnVsbCk7CiAgfSk7Cn0KCmZ1bmN0aW9uIHNob3coaWQpIHsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuc2NyZWVuJykuZm9yRWFjaChzID0+IHsKICAgIHMuY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJyk7CiAgICBzLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgfSk7CiAgY29uc3QgdGFyZ2V0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpOwogIGlmICghdGFyZ2V0KSB7IGNvbnNvbGUuZXJyb3IoJ1tzaG93XSBFbGVtZW50IG5vdCBmb3VuZDonLCBpZCk7IHJldHVybjsgfQogIHRhcmdldC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICB0YXJnZXQuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKICBpZiAoaWQgIT09ICdzLWdhbWUnKSB0YXJnZXQuc2Nyb2xsVG9wID0gMDsKICBjb25zb2xlLmxvZygnW3Nob3ddIE5hdmlnYXRlZCB0bzonLCBpZCk7CiAgLy8gU2NyZWVuLXNwZWNpZmljIGluaXQKICBpZiAoaWQgPT09ICdzLWNvbnZlcnQnKSB7IGluaXRDb252RHJvcCgpOyBjb252TG9hZEV4aXN0aW5nKCk7IH0KfQoKYXN5bmMgZnVuY3Rpb24gY2hlY2tPbGxhbWFTdGF0dXMoKSB7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYWktc3RhdHVzJyk7CiAgY29uc3QgYXBpQm94ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktYm94Jyk7CiAgY29uc3QgYXBpTGluayA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzaG93LWFwaS1saW5rJyk7CiAgaWYgKCFlbCkgcmV0dXJuOwoKICAvLyBUaW1lb3V0IHdyYXBwZXIgLS0gbmV2ZXIgc3RheSBzdHVjayBvbiAiQ2hlY2tpbmcuLi4iCiAgY29uc3QgdGltZW91dCA9IG5ldyBQcm9taXNlKChfLCByZWplY3QpID0+CiAgICBzZXRUaW1lb3V0KCgpID0+IHJlamVjdChuZXcgRXJyb3IoJ3RpbWVvdXQnKSksIDUwMDApCiAgKTsKCiAgdHJ5IHsKICAgIGNvbnN0IHIgPSBhd2FpdCBQcm9taXNlLnJhY2UoW3hockZldGNoKEJBU0VfVVJMICsgJy9vbGxhbWFfc3RhdHVzJyksIHRpbWVvdXRdKTsKCiAgICAvLyBDaGVjayBpZiB0aGlzIGlzIGFjdHVhbGx5IHRoZSB2MyBzZXJ2ZXIgKG9sZCBzZXJ2ZXJzIHdvbid0IGhhdmUgdGhpcyBlbmRwb2ludCkKICAgIGlmICghci5vaykgewogICAgICB0aHJvdyBuZXcgRXJyb3IoJ1NlcnZlciByZXR1cm5lZCAnICsgci5zdGF0dXMgKyAnIC0tIG1heSBiZSBydW5uaW5nIG9sZCB2ZXJzaW9uLiBIYXJkIHJlZnJlc2ggd2l0aCBDdHJsK1NoaWZ0K1InKTsKICAgIH0KCiAgICBjb25zdCBkID0gYXdhaXQgci5qc29uKCk7CgogICAgLy8gVmVyaWZ5IHRoaXMgaXMgYWN0dWFsbHkgYW4gb2xsYW1hX3N0YXR1cyByZXNwb25zZSAobm90IHNvbWUgb3RoZXIgZW5kcG9pbnQncyByZXNwb25zZSkKICAgIGlmICh0eXBlb2YgZC5hdmFpbGFibGUgPT09ICd1bmRlZmluZWQnKSB7CiAgICAgIHRocm93IG5ldyBFcnJvcignVW5leHBlY3RlZCByZXNwb25zZSAtLSBvbGQgc2VydmVyIG1heSBiZSBydW5uaW5nLiBTdG9wIGl0IGFuZCByZXN0YXJ0IGRuZF9hZHZlbnR1cmVfdjQucHknKTsKICAgIH0KCiAgICBvbGxhbWFBdmFpbGFibGUgPSBkLmF2YWlsYWJsZTsKICAgIHVzZU9sbGFtYSA9IGQuYXZhaWxhYmxlOwoKICAgIGlmIChkLmF2YWlsYWJsZSkgewogICAgICBlbC5zdHlsZS5ib3JkZXIgPSAnMnB4IHNvbGlkICMzYTZhM2EnOwogICAgICBlbC5zdHlsZS5iYWNrZ3JvdW5kID0gJyMwYTFhMGEnOwogICAgICBlbC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsKICAgICAgZWwuaW5uZXJIVE1MID0gJ09sbGFtYSBydW5uaW5nICZtZGFzaDsgPHN0cm9uZz4nICsgKGQubW9kZWwgfHwgJ2xvY2FsJykgKyAnPC9zdHJvbmc+JwogICAgICAgICsgJzxicj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Zm9udC13ZWlnaHQ6bm9ybWFsOyI+RnJlZSBsb2NhbCBBSSByZWFkeS4gTm8gQVBJIGtleSBuZWVkZWQgdG8gaG9zdC48L3NwYW4+JzsKICAgICAgaWYgKGFwaUxpbmspIGFwaUxpbmsuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICAgIGlmIChhcGlCb3gpIGFwaUJveC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgfSBlbHNlIHsKICAgICAgZWwuc3R5bGUuYm9yZGVyID0gJzJweCBzb2xpZCAjOGE1YTIwJzsKICAgICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICcjMWExMDAwJzsKICAgICAgZWwuc3R5bGUuY29sb3IgPSAnI2MwOTA2MCc7CiAgICAgIGVsLmlubmVySFRNTCA9ICchIE9sbGFtYSBub3QgcnVubmluZycKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+SW5zdGFsbCBmcm9tIDxhIGhyZWY9Imh0dHBzOi8vb2xsYW1hLmNvbSIgdGFyZ2V0PSJfYmxhbmsiIHN0eWxlPSJjb2xvcjojYzlhODRjIj5vbGxhbWEuY29tPC9hPiB0aGVuIHJ1bjogPGNvZGUgc3R5bGU9ImNvbG9yOiNjOWE4NGMiPm9sbGFtYSBwdWxsIG1pc3RyYWwtbmVtbzoxMmI8L2NvZGU+PC9zcGFuPicKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+T3IgZW50ZXIgYSBDbGF1ZGUgQVBJIGtleSBiZWxvdy48L3NwYW4+JzsKICAgICAgaWYgKGFwaUJveCkgYXBpQm94LnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICAgIGlmIChhcGlMaW5rKSBhcGlMaW5rLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICB9CiAgfSBjYXRjaChlKSB7CiAgICBlbC5zdHlsZS5ib3JkZXIgPSAnMnB4IHNvbGlkICM4YjI1MjUnOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICcjMWEwYTBhJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyNjMDYwNjAnOwogICAgaWYgKGUubWVzc2FnZSA9PT0gJ3RpbWVvdXQnKSB7CiAgICAgIGVsLmlubmVySFRNTCA9ICchIFNlcnZlciBub3QgcmVzcG9uZGluZycKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+TWFrZSBzdXJlIGRuZF9hZHZlbnR1cmVfdjQucHkgaXMgcnVubmluZywgdGhlbiBoYXJkIHJlZnJlc2g6IDxzdHJvbmc+Q3RybCtTaGlmdCtSPC9zdHJvbmc+PC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICBlbC5pbm5lckhUTUwgPSAnISAnICsgZS5tZXNzYWdlCiAgICAgICAgKyAnPGJyPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTZweDsiPlRyeTogc3RvcCB0aGUgc2VydmVyLCBydW4gZG5kX2FkdmVudHVyZV92NC5weSBhZ2FpbiwgdGhlbiA8c3Ryb25nPkN0cmwrU2hpZnQrUjwvc3Ryb25nPjwvc3Bhbj4nOwogICAgfQogICAgLy8gU2hvdyBBUEkga2V5IGJveCBhcyBmYWxsYmFjawogICAgaWYgKGFwaUJveCkgYXBpQm94LnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICBpZiAoYXBpTGluaykgYXBpTGluay5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgY29uc29sZS5lcnJvcignW09sbGFtYSBjaGVja10nLCBlKTsKICB9Cn0KCmZ1bmN0aW9uIHVwZGF0ZUFpSW5kaWNhdG9yKHZpYSwgbW9kZWwpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtYWktaW5kaWNhdG9yJyk7CiAgaWYgKCFlbCkgcmV0dXJuOwogIGlmICh2aWEgPT09ICdvbGxhbWEnKSB7CiAgICBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICcjM2E2YTNhJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyM2YTlhNmEnOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICdyZ2JhKDU4LDEwNiw1OCwwLjEpJzsKICAgIGVsLmlubmVySFRNTCA9ICctIE9sbGFtYSAoJyArIChtb2RlbCB8fCAnbG9jYWwnKSArICcpJzsKICB9IGVsc2UgaWYgKHZpYSA9PT0gJ2NsYXVkZScpIHsKICAgIGVsLnN0eWxlLmJvcmRlckNvbG9yID0gJyM3YTYwMzAnOwogICAgZWwuc3R5bGUuY29sb3IgPSAnI2M5YTg0Yyc7CiAgICBlbC5zdHlsZS5iYWNrZ3JvdW5kID0gJ3JnYmEoMjAxLDE2OCw3NiwwLjA2KSc7CiAgICBlbC5pbm5lckhUTUwgPSAnLSBDbGF1ZGUgQVBJJzsKICB9IGVsc2UgaWYgKHZpYSA9PT0gJ2Vycm9yJykgewogICAgZWwuc3R5bGUuYm9yZGVyQ29sb3IgPSAnIzhiMjUyNSc7CiAgICBlbC5zdHlsZS5jb2xvciA9ICcjYzA2MDYwJzsKICAgIGVsLnN0eWxlLmJhY2tncm91bmQgPSAncmdiYSgxMzksMzcsMzcsMC4wNiknOwogICAgZWwuaW5uZXJIVE1MID0gJyEgQUkgRXJyb3InOwogIH0gZWxzZSB7CiAgICBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICcjM2EzMDIwJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyM4YTdhNTgnOwogICAgZWwuaW5uZXJIVE1MID0gJy0gQUk6IGNoZWNraW5nLi4uJzsKICB9Cn0KCmZ1bmN0aW9uIHJvdGF0ZUJhbm5lZFBocmFzZXMoKSB7CiAgLy8gUGljayA1IHJhbmRvbSBwaHJhc2VzIGZyb20gdGhlIHBvb2wgZWFjaCB0aW1lIHRvIGtlZXAgaXQgZnJlc2gKICBjb25zdCBzaHVmZmxlZCA9IFsuLi5CQU5ORURfUEhSQVNFU19QT09MXS5zb3J0KCgpID0+IE1hdGgucmFuZG9tKCkgLSAwLjUpOwogIGJhbm5lZFBocmFzZXMgPSBzaHVmZmxlZC5zbGljZSgwLCA1KTsKfQoKZnVuY3Rpb24gZ2V0Q29sb3IobmFtZSkgewogIGlmICghY29sb3JNYXBbbmFtZV0pIHsKICAgIGNvbnN0IHVzZWQgPSBPYmplY3Qua2V5cyhjb2xvck1hcCkubGVuZ3RoOwogICAgY29sb3JNYXBbbmFtZV0gPSBQTEFZRVJfQ09MT1JTW3VzZWQgJSBQTEFZRVJfQ09MT1JTLmxlbmd0aF07CiAgfQogIHJldHVybiBjb2xvck1hcFtuYW1lXTsKfQoKZnVuY3Rpb24gZ2V0Q29sb3JGb3JDbGFzcyhjbHMpIHsKICBjb25zdCBtYXAgPSB7CiAgICAnRmlnaHRlcic6JyNjOWE4NGMnLCdNYWdpYy1Vc2VyJzonIzdhYmFmZicsJ0NsZXJpYyc6JyNmZmZmZmYnLAogICAgJ1RoaWVmJzonI2ZmYjA3YScsJ1Jhbmdlcic6JyM3YWZmYjAnLCdQYWxhZGluJzonI2ZmZmFhYScsCiAgICAnRHJ1aWQnOicjN2FmZjdhJywnSWxsdXNpb25pc3QnOicjZDk3YWZmJywnQXNzYXNzaW4nOicjZmY3YWFhJywKICAgICdCYXJkJzonI2ZmZGE3YScsJ01vbmsnOicjYWFmZmZmJywnQmFyYmFyaWFuJzonI2ZmOWE3YScsCiAgICAnQWNyb2JhdCc6JyNjMGMwZmYnLCdLbmlnaHQnOicjZmZlMGEwJywKICB9OwogIHJldHVybiBtYXBbY2xzXSB8fCAnI2M5YTg0Yyc7Cn0KCmZ1bmN0aW9uIHNob3dDaGFyU2VsZWN0KGNvbnRleHQsIGNvbnRleHRMYWJlbCwgcGVuZGluZ0RhdGEpIHsKICBjc2VsU2VsZWN0ZWRJZCA9IG51bGw7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NzZWwtdXNlLWJ0bicpLmRpc2FibGVkID0gdHJ1ZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1wcmV2aWV3Jykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1tb2R1bGUnKS50ZXh0Q29udGVudCA9IGNvbnRleHRMYWJlbDsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1jb250ZXh0JykudGV4dENvbnRlbnQgPSBjb250ZXh0OwoKICBzaG93KCdzLWNoYXJzZWxlY3QnKTsKCiAgLy8gTG9hZCBjaGFyYWN0ZXJzIGZyb20gc2VydmVyCiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NoYXJhY3RlcnMnKS50aGVuKHI9PnIuanNvbigpKS50aGVuKGNoYXJzID0+IHsKICAgIGNzZWxDaGFycyA9IGNoYXJzOwogICAgY29uc3QgbGlzdCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjc2VsLWxpc3QnKTsKICAgIGlmICghY2hhcnMubGVuZ3RoKSB7CiAgICAgIGxpc3QuaW5uZXJIVE1MID0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2NvbG9yOnZhcigtLWRpbSk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweDtiYWNrZ3JvdW5kOnZhcigtLXBhbmVsKTsiPk5vIHNhdmVkIGNoYXJhY3RlcnMgeWV0LiBDcmVhdGUgYSBuZXcgb25lIGJlbG93LjwvZGl2Pic7CiAgICB9IGVsc2UgewogICAgICBsaXN0LmlubmVySFRNTCA9IGNoYXJzLm1hcChjID0+IHsKICAgICAgICBjb25zdCBjb2wgPSBnZXRDb2xvckZvckNsYXNzKGMuY2xzKTsKICAgICAgICByZXR1cm4gYDxkaXYgY2xhc3M9ImNzZWwtaXRlbSIgaWQ9ImNpLSR7Yy5pZH0iIG9uY2xpY2s9InByZXZpZXdDaGFyKCcke2MuaWR9JykiPgogICAgICAgICAgPGRpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2ktbmFtZSI+JHtjLm5hbWV9PC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNpLXN1YiI+CiAgICAgICAgICAgICAgTGV2ZWwgJHtjLmxldmVsfSAke2MucmFjZX0gJHtjLmNsc30gJm5ic3A7KiZuYnNwOyAke2MuYWxpZ259CiAgICAgICAgICAgICAgJm5ic3A7KiZuYnNwOyBIUCAke2MuaHB9LyR7Yy5tYXhocH0gJm5ic3A7KiZuYnNwOyBBQyAke2MuYWN9ICZuYnNwOyombmJzcDsgJHtjLmdvbGR9Z3AKICAgICAgICAgICAgICA8YnI+TGFzdCBwbGF5ZWQ6ICR7bmV3IERhdGUoYy5zYXZlZEF0KS50b0xvY2FsZURhdGVTdHJpbmcoKX0KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxzcGFuIGNsYXNzPSJjaS1iYWRnZSIgc3R5bGU9ImJvcmRlci1jb2xvcjoke2NvbH07Y29sb3I6JHtjb2x9OyI+JHtjLmNsc308L3NwYW4+CiAgICAgICAgPC9kaXY+YDsKICAgICAgfSkuam9pbignJyk7CiAgICB9CiAgfSk7CgogIC8vIFN0b3JlIHBlbmRpbmcgYWN0aW9uCiAgaWYgKHBlbmRpbmdEYXRhICYmIHBlbmRpbmdEYXRhLnR5cGUgPT09ICdzYXZlJykgY3NlbFBlbmRpbmdTYXZlID0gcGVuZGluZ0RhdGE7CiAgaWYgKHBlbmRpbmdEYXRhICYmIHBlbmRpbmdEYXRhLnR5cGUgPT09ICdqb2luJykgY3NlbFBlbmRpbmdKb2luID0gcGVuZGluZ0RhdGE7Cn0KCmZ1bmN0aW9uIHByZXZpZXdDaGFyKGlkKSB7CiAgLy8gRGVzZWxlY3QgYWxsCiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLmNzZWwtaXRlbScpLmZvckVhY2goZWwgPT4gZWwuY2xhc3NMaXN0LnJlbW92ZSgnc2VsJykpOwogIGNvbnN0IGl0ZW0gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2ktJyArIGlkKTsKICBpZiAoaXRlbSkgaXRlbS5jbGFzc0xpc3QuYWRkKCdzZWwnKTsKCiAgY3NlbFNlbGVjdGVkSWQgPSBpZDsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC11c2UtYnRuJykuZGlzYWJsZWQgPSBmYWxzZTsKCiAgLy8gRmluZCBjaGFyIGRhdGEKICBjb25zdCBjID0gY3NlbENoYXJzLmZpbmQoeCA9PiB4LmlkID09PSBpZCk7CiAgaWYgKCFjKSByZXR1cm47CgogIC8vIExvYWQgZnVsbCBjaGFyYWN0ZXIgZnJvbSBzZXJ2ZXIKICB4aHJGZXRjaChCQVNFX1VSTCArICcvY2hhcmFjdGVyP2lkPScgKyBlbmNvZGVVUklDb21wb25lbnQoaWQpKS50aGVuKHI9PnIuanNvbigpKS50aGVuKGZ1bGwgPT4gewogICAgY29uc3QgcHJldiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjc2VsLXByZXZpZXcnKTsKICAgIHByZXYuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKCiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtbmFtZScpLnRleHRDb250ZW50ID0gZnVsbC5uYW1lOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWNsYXNzJykudGV4dENvbnRlbnQgPQogICAgICBgTGV2ZWwgJHtmdWxsLmxldmVsfSAke2Z1bGwucmFjZX0gJHtmdWxsLmNsc31gOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWFsaWduJykudGV4dENvbnRlbnQgPQogICAgICBgQWxpZ25tZW50OiAke2Z1bGwuYWxpZ24gfHwgJz8nfSAqIFNhdmVzOiBEZWF0aCAke2Z1bGwuc2F2ZXM/LmR8fCc/J30sIFdhbmRzICR7ZnVsbC5zYXZlcz8ud3x8Jz8nfSwgUGFyYWx5c2lzICR7ZnVsbC5zYXZlcz8ucHx8Jz8nfSwgQnJlYXRoICR7ZnVsbC5zYXZlcz8uYnx8Jz8nfSwgU3BlbGxzICR7ZnVsbC5zYXZlcz8uc3x8Jz8nfWA7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtaHAnKS50ZXh0Q29udGVudCA9IGAke2Z1bGwuaHB9LyR7ZnVsbC5tYXhocH1gOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWFjJykudGV4dENvbnRlbnQgPSBmdWxsLmFjOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWdvbGQnKS50ZXh0Q29udGVudCA9IGZ1bGwuZ29sZDsKCiAgICAvLyBTdGF0cyBncmlkCiAgICBjb25zdCBzdGF0cyA9IGZ1bGwuc3RhdHMgfHwge307CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtc3RhdHMnKS5pbm5lckhUTUwgPQogICAgICBbJ1NUUicsJ0RFWCcsJ0NPTicsJ0lOVCcsJ1dJUycsJ0NIQSddLm1hcChzID0+IHsKICAgICAgICBjb25zdCB2ID0gc3RhdHNbc10gfHwgMTA7CiAgICAgICAgY29uc3QgbSA9IE1hdGguZmxvb3IoKHYtMTApLzIpOwogICAgICAgIGNvbnN0IG1jID0gbSA+IDAgPyAnY29sb3I6IzZhOWE2YScgOiBtIDwgMCA/ICdjb2xvcjojOWE0YTRhJyA6ICcnOwogICAgICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic3RhdC1taW5pIj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNtbiI+JHtzfTwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0ic212Ij4ke3Z9PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzbW0iIHN0eWxlPSIke21jfSI+JHttPj0wPycrJyttOm19PC9kaXY+CiAgICAgICAgPC9kaXY+YDsKICAgICAgfSkuam9pbignJyk7CgogICAgLy8gSW52ZW50b3J5CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtaW52JykudGV4dENvbnRlbnQgPSAoZnVsbC5pbnYgfHwgW10pLmpvaW4oJywgJykgfHwgJ0VtcHR5JzsKCiAgICAvLyBSYWNpYWwgc3BlY2lhbHMKICAgIGNvbnN0IHNwZWNzID0gZnVsbC5zcGVjaWFscyB8fCBbXTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjcHJldi1zcGVjaWFscycpLnRleHRDb250ZW50ID0KICAgICAgc3BlY3MubGVuZ3RoID8gJyAnICsgc3BlY3Muam9pbignICogJykgOiAnJzsKICB9KTsKfQoKZnVuY3Rpb24gdXNlU2VsZWN0ZWRDaGFyKCkgewogIGlmICghY3NlbFNlbGVjdGVkSWQpIHJldHVybjsKICBjb25zdCBjID0gY3NlbENoYXJzLmZpbmQoeCA9PiB4LmlkID09PSBjc2VsU2VsZWN0ZWRJZCk7CiAgaWYgKCFjKSByZXR1cm47CgogIC8vIExvYWQgdGhlIGZ1bGwgY2hhcmFjdGVyCiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NoYXJhY3Rlcj9pZD0nICsgZW5jb2RlVVJJQ29tcG9uZW50KGNzZWxTZWxlY3RlZElkKSkudGhlbihyPT5yLmpzb24oKSkudGhlbihmdWxsID0+IHsKICAgIHBjID0gZnVsbDsKCiAgICBpZiAoY3NlbFBlbmRpbmdTYXZlKSB7CiAgICAgIC8vIENvbWluZyBmcm9tIExvYWQgR2FtZSAtLSByZXN0b3JlIHRoZSBmdWxsIHNhdmUgd2l0aCB0aGlzIGNoYXJhY3RlcgogICAgICBjb25zdCBkYXRhID0gY3NlbFBlbmRpbmdTYXZlLmRhdGE7CiAgICAgIHBjID0gZnVsbDsgLy8gdXNlIHNlbGVjdGVkIGNoYXIsIG5vdCB0aGUgc2F2ZWQgb25lCiAgICAgIG1vZHVsZVRleHQgPSBkYXRhLm1vZHVsZVRleHQgfHwgJyc7CiAgICAgIG1vZHVsZU5hbWUgPSBkYXRhLm1vZHVsZU5hbWUgfHwgJyc7CiAgICAgIGNob3NlblJ1bGVzID0gZGF0YS5jaG9zZW5SdWxlcyB8fCAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwogICAgICBwYXJ0eVBDcyA9IGRhdGEucGFydHlQQ3MgfHwge307CiAgICAgIC8vIEluamVjdCBvdXIgc2VsZWN0ZWQgY2hhcmFjdGVyIGFzIHRoZSBwbGF5ZXIncyBQQwogICAgICBwYXJ0eVBDc1twbGF5ZXJOYW1lXSA9IHBjOwogICAgICBoaXN0b3J5ID0gZGF0YS5oaXN0b3J5IHx8IFtdOwogICAgICBzeXN0ZW1Qcm9tcHQgPSBkYXRhLnN5c3RlbVByb21wdCB8fCAnJzsKICAgICAgaXNNdWx0aXBsYXllciA9IGRhdGEuaXNNdWx0aXBsYXllciB8fCBmYWxzZTsKICAgICAgLy8gUmVzdG9yZSBtZW1vcnkgc3lzdGVtCiAgICAgIG1lbW9yeVN1bW1hcnkgPSBkYXRhLm1lbW9yeVN1bW1hcnkgfHwgJyc7CiAgICAgIHdvcmxkU3RhdGUgPSBkYXRhLndvcmxkU3RhdGUgfHwgeyBucGNzX21ldDp7fSwgbG9jYXRpb25zX3Zpc2l0ZWQ6e30sIGl0ZW1zX2ZvdW5kOltdLCBwbG90X3BvaW50czpbXSwgZG9vcnNfb3BlbmVkOltdLCB0cmFwc19zcHJ1bmc6W10sIG1vbnN0ZXJzX2tpbGxlZDpbXSwgcXVlc3RzX2FjdGl2ZTpbXSwgd29ybGRfY2hhbmdlczpbXSB9OwogICAgICBwaW5uZWRGYWN0cyA9IGRhdGEucGlubmVkRmFjdHMgfHwgW107CiAgICAgIHR1cm5Db3VudCA9IGRhdGEudHVybkNvdW50IHx8IDA7CiAgICAgIG5wY1Byb2ZpbGVzID0gZGF0YS5ucGNQcm9maWxlcyB8fCB7fTsKICAgICAgbG9jYXRpb25BdG1vc3BoZXJlID0gZGF0YS5sb2NhdGlvbkF0bW9zcGhlcmUgfHwge307CiAgICAgIHNlc3Npb25Ub25lID0gZGF0YS5zZXNzaW9uVG9uZSB8fCAnZXhwbG9yYXRvcnknOwogICAgICBnbUJyaWVmaW5nID0gZGF0YS5nbUJyaWVmaW5nIHx8ICcnOwogICAgICBucGNLbm93bGVkZ2VNYXAgPSBkYXRhLm5wY0tub3dsZWRnZU1hcCB8fCB7fTsKICAgICAgcGFjaW5nSGlzdG9yeSA9IGRhdGEucGFjaW5nSGlzdG9yeSB8fCBbXTsKICAgICAgY3VycmVudFBhY2luZ1BoYXNlID0gZGF0YS5jdXJyZW50UGFjaW5nUGhhc2UgfHwgJ29wZW5pbmcnOwogICAgICBjb25zZXF1ZW5jZXMgPSBkYXRhLmNvbnNlcXVlbmNlcyB8fCBbXTsKICAgICAgaW5Db21iYXQgPSBkYXRhLmluQ29tYmF0IHx8IGZhbHNlOwogICAgICBjb21iYXRTdGF0ZSA9IGRhdGEuY29tYmF0U3RhdGUgfHwgeyByb3VuZDowLCBpbml0aWF0aXZlT3JkZXI6W10sIGFjdGl2ZUluZGV4OjAsIHBsYXllckFjdGlvbjonJywgbGFzdFJvdW5kU3VtbWFyeTonJyB9OwogICAgICBkdW5nZW9uVHVybnMgPSBkYXRhLmR1bmdlb25UdXJucyB8fCAwOwogICAgICB0b3JjaFR1cm5zTGVmdCA9IGRhdGEudG9yY2hUdXJuc0xlZnQgIT09IHVuZGVmaW5lZCA/IGRhdGEudG9yY2hUdXJuc0xlZnQgOiAxODsKICAgICAgaGFzTGFudGVybiA9IGRhdGEuaGFzTGFudGVybiB8fCBmYWxzZTsKICAgICAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSBkYXRhLmxhbnRlcm5PaWxGbGFza3NMZWZ0IHx8IDA7CiAgICAgIHJhdGlvbnNMZWZ0ID0gZGF0YS5yYXRpb25zTGVmdCB8fCAwOwogICAgICByZXN0RGVidCA9IGRhdGEucmVzdERlYnQgfHwgMDsKICAgICAgd2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyID0gZGF0YS53YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgfHwgMDsKCiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtbW9kJykudGV4dENvbnRlbnQgPSBtb2R1bGVOYW1lOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgc2hvd1Jvb21Db2RlKCk7CiAgICAgIHNob3coJ3MtZ2FtZScpOwogICAgICB1cGRhdGVIVUQoKTsKICAgICAgcmVuZGVyUGFydHlQYW5lbCgpOwogICAgICBjb25zdCBsb2cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbG9nJyk7CiAgICAgIGxvZy5pbm5lckhUTUwgPSAnJzsKICAgICAgKGRhdGEubG9nRW50cmllcyB8fCBbXSkuZm9yRWFjaChlID0+IGFkZEVudHJ5UmF3KGUuaHRtbCwgZS50eXBlLCBlLmF1dGhvcikpOwogICAgICBsb2cuc2Nyb2xsVG9wID0gbG9nLnNjcm9sbEhlaWdodDsKICAgICAgYWRkRW50cnlSYXcoJyBBZHZlbnR1cmUgcmVzdG9yZWQuIFBsYXlpbmcgYXMgPHN0cm9uZz4nICsgcGMubmFtZSArICc8L3N0cm9uZz4uJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgaWYgKGlzTXVsdGlwbGF5ZXIgJiYgcm9vbUNvZGUpIHN0YXJ0UG9sbGluZygpOwogICAgICBjc2VsUGVuZGluZ1NhdmUgPSBudWxsOwoKICAgIH0gZWxzZSBpZiAoY3NlbFBlbmRpbmdKb2luKSB7CiAgICAgIC8vIENvbWluZyBmcm9tIEpvaW4gUm9vbSAtLSB1c2UgdGhpcyBjaGFyYWN0ZXIgaW4gdGhlIHJvb20KICAgICAgY29uc3QgZGF0YSA9IGNzZWxQZW5kaW5nSm9pbi5kYXRhOwogICAgICByb29tQ29kZSA9IGRhdGEuY29kZTsKICAgICAgaXNNdWx0aXBsYXllciA9IHRydWU7CiAgICAgIGlzSG9zdCA9IGZhbHNlOwogICAgICBtb2R1bGVOYW1lID0gZGF0YS5tb2R1bGVOYW1lIHx8ICcnOwogICAgICBjaG9zZW5SdWxlcyA9IGRhdGEuY2hvc2VuUnVsZXMgfHwgJ09TRSBBZHZhbmNlZCBGYW50YXN5JzsKICAgICAgbW9kdWxlVGV4dCA9IGRhdGEubW9kdWxlVGV4dCB8fCAnJzsKICAgICAgbG9hZGVkTW9kdWxlRGF0YSA9IGRhdGEubW9kdWxlRGF0YSB8fCB7fTsKICAgICAgc3lzdGVtUHJvbXB0ID0gZGF0YS5zeXN0ZW1Qcm9tcHQgfHwgJyc7CgogICAgICBpZiAoZGF0YS5nYW1lQWN0aXZlKSB7CiAgICAgICAgcGFydHlQQ3MgPSBkYXRhLnBhcnR5UENzIHx8IHt9OwogICAgICAgIHBhcnR5UENzW3BsYXllck5hbWVdID0gcGM7CiAgICAgICAgaGlzdG9yeSA9IGRhdGEuaGlzdG9yeSB8fCBbXTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLW1vZCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgICBzaG93KCdzLWdhbWUnKTsKICAgICAgICB1cGRhdGVIVUQoKTsKICAgICAgICByZW5kZXJQYXJ0eVBhbmVsKCk7CiAgICAgICAgKGRhdGEubG9nRW50cmllcyB8fCBbXSkuZm9yRWFjaChlID0+IGFkZEVudHJ5UmF3KGUuaHRtbCwgZS50eXBlLCBlLmF1dGhvcikpOwogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsb2cnKS5zY3JvbGxUb3AgPSA5OTk5OTsKICAgICAgICAvLyBSZWdpc3RlciBjaGFyYWN0ZXIgaW4gcm9vbQogICAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9wbGF5ZXJfcmVhZHknLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lLCBwY30pfSk7CiAgICAgICAgc3RhcnRQb2xsaW5nKCk7CiAgICAgIH0gZWxzZSB7CiAgICAgICAgLy8gR2FtZSBub3Qgc3RhcnRlZCB5ZXQgLS0gZ28gdG8gY2hhciBzY3JlZW4gYnV0IHByZS1maWxsIHdpdGggc2VsZWN0ZWQgY2hhcgogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21wLWNoYXItbm90ZScpLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogICAgICAgIHNob3coJ3MtY2hhcicpOwogICAgICAgIGJ1aWxkQ2hhckNyZWF0ZSgpOwogICAgICAgIC8vIFByZS1wb3B1bGF0ZSBjaGFyIG5hbWUgYW5kIG1hcmsgYXMgcmVhZHkgd2l0aCB0aGlzIGNoYXJhY3RlcgogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbmFtZS1pbnAnKS52YWx1ZSA9IHBjLm5hbWU7CiAgICAgICAgLy8gUmVnaXN0ZXIgaW4gcm9vbQogICAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9wbGF5ZXJfcmVhZHknLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lLCBwY30pfSk7CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JlYWR5LWJ0bicpLnRleHRDb250ZW50ID0gJyBVc2luZyAnICsgcGMubmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJykuZGlzYWJsZWQgPSB0cnVlOwogICAgICAgIHN0YXJ0UG9sbGluZygpOwogICAgICB9CiAgICAgIGNzZWxQZW5kaW5nSm9pbiA9IG51bGw7CiAgICB9CiAgfSk7Cn0KCmZ1bmN0aW9uIHNob3dDaGFyQ3JlYXRlKCkgewogIC8vIEZyb20gY2hhciBzZWxlY3Qgc2NyZWVuLCBnbyB0byBmdWxsIGNoYXJhY3RlciBjcmVhdGlvbgogIGlmIChjc2VsUGVuZGluZ0pvaW4pIHsKICAgIGNvbnN0IGRhdGEgPSBjc2VsUGVuZGluZ0pvaW4uZGF0YTsKICAgIHJvb21Db2RlID0gZGF0YS5jb2RlOwogICAgaXNNdWx0aXBsYXllciA9IHRydWU7CiAgICBpc0hvc3QgPSBmYWxzZTsKICAgIG1vZHVsZU5hbWUgPSBkYXRhLm1vZHVsZU5hbWUgfHwgJyc7CiAgICBjaG9zZW5SdWxlcyA9IGRhdGEuY2hvc2VuUnVsZXMgfHwgJ09TRSBBZHZhbmNlZCBGYW50YXN5JzsKICAgIG1vZHVsZVRleHQgPSBkYXRhLm1vZHVsZVRleHQgfHwgJyc7CiAgICBsb2FkZWRNb2R1bGVEYXRhID0gZGF0YS5tb2R1bGVEYXRhIHx8IGxvYWRlZE1vZHVsZURhdGEgfHwge307CiAgICBzeXN0ZW1Qcm9tcHQgPSBkYXRhLnN5c3RlbVByb21wdCB8fCAnJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgICBjb25zdCBtcE5vdGUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbXAtY2hhci1ub3RlJyk7CiAgICBpZiAobXBOb3RlKSBtcE5vdGUuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBzdGFydFBvbGxpbmcoKTsKICB9IGVsc2UgaWYgKGNzZWxQZW5kaW5nU2F2ZSkgewogICAgLy8gQ3JlYXRpbmcgbmV3IGNoYXIgZm9yIGEgbG9hZGVkIHNhdmUgLS0gc3RpbGwgbG9hZCB0aGUgbW9kdWxlCiAgICBjb25zdCBkYXRhID0gY3NlbFBlbmRpbmdTYXZlLmRhdGE7CiAgICBtb2R1bGVOYW1lID0gZGF0YS5tb2R1bGVOYW1lIHx8ICcnOwogICAgbW9kdWxlVGV4dCA9IGRhdGEubW9kdWxlVGV4dCB8fCAnJzsKICAgIGNob3NlblJ1bGVzID0gZGF0YS5jaG9zZW5SdWxlcyB8fCAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NoYXItbW9kdWxlLWxibCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICB9CiAgY3NlbFBlbmRpbmdTYXZlID0gbnVsbDsKICBjc2VsUGVuZGluZ0pvaW4gPSBudWxsOwogIHNob3coJ3MtY2hhcicpOwogIGJ1aWxkQ2hhckNyZWF0ZSgpOwp9Cgphc3luYyBmdW5jdGlvbiBsb2FkRG5kbW9kTGlzdCgpIHsKICBjb25zdCBsaXN0RWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZG5kbW9kLWxpc3QnKTsKICBjb25zdCBlbXB0eUVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2RuZG1vZC1lbXB0eScpOwogIGxpc3RFbC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogIGxpc3RFbC5pbm5lckhUTUwgPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Y29sb3I6dmFyKC0tZGltKSI+TG9hZGluZy4uLjwvZGl2Pic7CgogIGxldCBtb2RzOwogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2xpc3RfbW9kdWxlcycpOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgLy8gU2VydmVyIHJldHVybnMge21vZHVsZXM6Wy4uLl19IC0tIHVud3JhcCBpdAogICAgbW9kcyA9IEFycmF5LmlzQXJyYXkoZGF0YSkgPyBkYXRhIDogKGRhdGEubW9kdWxlcyB8fCBbXSk7CiAgfSBjYXRjaChlKSB7CiAgICBsaXN0RWwuaW5uZXJIVE1MID0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2NvbG9yOiNjMDYwNjAiPkNvdWxkIG5vdCBsb2FkIG1vZHVsZSBsaXN0OiAnICsgZS5tZXNzYWdlICsgJzwvZGl2Pic7CiAgICByZXR1cm47CiAgfQoKICBpZiAoIW1vZHMubGVuZ3RoKSB7CiAgICBsaXN0RWwuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGlmIChlbXB0eUVsKSBlbXB0eUVsLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICByZXR1cm47CiAgfQogIGlmIChlbXB0eUVsKSBlbXB0eUVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgbGlzdEVsLmlubmVySFRNTCA9IG1vZHMubWFwKG0gPT4gewogICAgLy8gTm9ybWFsaXNlIGZpZWxkIG5hbWVzIC0tIHNlcnZlciB1c2VzIHtmaWxlLCB0aXRsZSwgbGV2ZWwsIHN5c3RlbX0KICAgIGNvbnN0IGZuYW1lICAgID0gbS5maWxlIHx8IG0uZmlsZW5hbWUgfHwgJyc7CiAgICBjb25zdCB0aXRsZSAgICA9IG0udGl0bGUgfHwgZm5hbWU7CiAgICBjb25zdCBsZXZlbCAgICA9IG0ubGV2ZWwgfHwgbS5sZXZlbF9yYW5nZSB8fCAnJzsKICAgIGNvbnN0IHN5c3RlbSAgID0gbS5zeXN0ZW0gfHwgJ09TRSc7CiAgICBjb25zdCBzYWZlVGl0bGUgPSB0aXRsZS5yZXBsYWNlKC8nL2csICImIzM5OyIpOwogICAgcmV0dXJuIGAKICAgIDxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEwcHggMTJweDtjdXJzb3I6cG9pbnRlcjsKICAgICAgdHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1czsiIGlkPSJtb2QtJHtmbmFtZX0iCiAgICAgIG9ubW91c2VlbnRlcj0idGhpcy5zdHlsZS5ib3JkZXJDb2xvcj0ndmFyKC0tZ29sZCknIgogICAgICBvbm1vdXNlbGVhdmU9InRoaXMuc3R5bGUuYm9yZGVyQ29sb3I9J3ZhcigtLWJvcmRlciknIgogICAgICBvbmNsaWNrPSJzZWxlY3REbmRtb2QoJyR7Zm5hbWV9JywnJHtzYWZlVGl0bGV9JykiPgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MThweDtjb2xvcjp2YXIoLS1pbmspO2ZvbnQtZmFtaWx5OidJTSBGZWxsIEVuZ2xpc2gnLHNlcmlmIj4ke3RpdGxlfTwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1kaW0pO21hcmdpbi10b3A6M3B4OyI+JHtzeXN0ZW19ICZuYnNwOyombmJzcDsgJHtsZXZlbCB8fCAnQW55IGxldmVsJ308L2Rpdj4KICAgIDwvZGl2PmA7CiAgfSkuam9pbignJyk7Cn0KCmFzeW5jIGZ1bmN0aW9uIHNlbGVjdERuZG1vZChmaWxlbmFtZSwgdGl0bGUpIHsKICAvLyBIaWdobGlnaHQgc2VsZWN0ZWQKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcjZG5kbW9kLWxpc3QgPiBkaXYnKS5mb3JFYWNoKGVsID0+IHsKICAgIGVsLnN0eWxlLmJvcmRlckNvbG9yID0gJ3ZhcigtLWJvcmRlciknOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICd2YXIoLS1iZyknOwogIH0pOwogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21vZC0nICsgZmlsZW5hbWUpOwogIGlmIChlbCkgeyBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICd2YXIoLS1nb2xkKSc7IGVsLnN0eWxlLmJhY2tncm91bmQgPSAncmdiYSgyMDEsMTY4LDc2LDAuMDgpJzsgfQoKICBzZWxlY3RlZERuZG1vZEZpbGUgPSBmaWxlbmFtZTsKICBtb2R1bGVOYW1lID0gdGl0bGU7CgogIC8vIFNob3cgbG9hZGluZyBzdGF0dXMgaW4gdGhlIG1vZHVsZSBjYXJkIGl0c2VsZgogIGNvbnN0IG1vZENhcmQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbW9kLScgKyBmaWxlbmFtZSk7CiAgaWYgKG1vZENhcmQpIG1vZENhcmQuaW5uZXJIVE1MICs9ICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1nb2xkKTttYXJnaW4tdG9wOjRweDsiPkxvYWRpbmcuLi48L2Rpdj4nOwoKICAvLyBMb2FkIHRoZSBtb2R1bGUgZGF0YSBmcm9tIHNlcnZlcgogIGxldCByZXN1bHQ7CiAgdHJ5IHsKICAgIHJlc3VsdCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9sb2FkX21vZHVsZT9maWxlPScgKyBlbmNvZGVVUklDb21wb25lbnQoZmlsZW5hbWUpKS50aGVuKHI9PnIuanNvbigpKTsKICB9IGNhdGNoKGUpIHsKICAgIGlmIChtb2RDYXJkKSBtb2RDYXJkLmlubmVySFRNTCArPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE0cHg7Y29sb3I6I2MwNjA2MDsiPkVycm9yOiAnICsgZS5tZXNzYWdlICsgJzwvZGl2Pic7CiAgICByZXR1cm47CiAgfQoKICBpZiAocmVzdWx0LmVycm9yKSB7CiAgICBpZiAobW9kQ2FyZCkgbW9kQ2FyZC5pbm5lckhUTUwgKz0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O2NvbG9yOiNjMDYwNjA7Ij5FcnJvcjogJyArIHJlc3VsdC5lcnJvciArICc8L2Rpdj4nOwogICAgcmV0dXJuOwogIH0KCiAgbW9kdWxlVGV4dCA9IHJlc3VsdC50ZXh0IHx8ICcnOwogIG1vZHVsZU5hbWUgPSByZXN1bHQudGl0bGUgfHwgJyc7CiAgbG9hZGVkTW9kdWxlRGF0YSA9IHJlc3VsdC5kYXRhIHx8IHt9OwogIGNvbnNvbGUubG9nKCdbc2VsZWN0RG5kbW9kXSBtb2R1bGVUZXh0IGxlbmd0aDonLCBtb2R1bGVUZXh0Lmxlbmd0aCwgJ3wgbW9kdWxlTmFtZTonLCBtb2R1bGVOYW1lLCAnfCBkYXRhIGtleXM6JywgT2JqZWN0LmtleXMobG9hZGVkTW9kdWxlRGF0YSkubGVuZ3RoKTsKICBpZiAoIW1vZHVsZVRleHQpIHsKICAgIGlmIChtb2RDYXJkKSBtb2RDYXJkLmlubmVySFRNTCArPSAnPGRpdiBzdHlsZT0iY29sb3I6I2MwNjA2MDtmb250LXNpemU6MTRweDsiPldhcm5pbmc6IG1vZHVsZSB0ZXh0IGVtcHR5ITwvZGl2Pic7CiAgfQoKICAvLyBQdXNoIG1vZHVsZSB0byByb29tIHNvIGd1ZXN0cyBnZXQgaXQgdG9vCiAgaWYgKHJvb21Db2RlKSB7CiAgICBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvdXBkYXRlX3Jvb20nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGU6cm9vbUNvZGUsIG1vZHVsZVRleHQsIG1vZHVsZU5hbWUsIGNob3NlblJ1bGVzLCBtb2R1bGVEYXRhOiBsb2FkZWRNb2R1bGVEYXRhfSl9KTsKICB9CgogIC8vIEVuYWJsZSB0aGUgQ29udGludWUgYnV0dG9uIGFuZCBzaG93IGNvbmZpcm1hdGlvbgogIHNldFRpbWVvdXQoKCkgPT4gewogICAgY29uc3QgYnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ25leHQtYnRuJyk7CiAgICBpZiAoYnRuKSB7IGJ0bi5kaXNhYmxlZCA9IGZhbHNlOyBidG4uc3R5bGUub3BhY2l0eSA9ICcxJzsgYnRuLnRleHRDb250ZW50ID0gJyAnICsgbW9kdWxlTmFtZSArICcgLS0gQ3JlYXRlIENoYXJhY3RlciAnOyB9CiAgfSwgNDAwKTsKfQoKZnVuY3Rpb24gcHJvY2VlZFRvQ2hhckNyZWF0ZSgpIHsKICBpZiAoIW1vZHVsZVRleHQgfHwgbW9kdWxlVGV4dC5sZW5ndGggPCAxMCkgewogICAgYWxlcnQoJ1BsZWFzZSBzZWxlY3QgYSBtb2R1bGUgZmlyc3QuJyk7CiAgICByZXR1cm47CiAgfQogIGNvbnN0IGNtbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKTsKICBpZiAoY21sKSBjbWwudGV4dENvbnRlbnQgPSBtb2R1bGVOYW1lOwogIHNob3coJ3MtY2hhcicpOwogIGJ1aWxkQ2hhckNyZWF0ZSgpOwp9CgpmdW5jdGlvbiBnb1RvTmV3R2FtZSgpIHsKICAvLyBJbml0aWFsaXNlIHNlc3Npb24gc3RhdGUgc2lsZW50bHkgKG5vIG5hbWUgcmVxdWlyZWQgeWV0KQogIGlmICghcGxheWVyTmFtZSkgcGxheWVyTmFtZSA9ICdBZHZlbnR1cmVyJzsKICBpc0hvc3QgPSBvbGxhbWFBdmFpbGFibGUgfHwgISFhcGlLZXk7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBjaG9zZW5SdWxlcyA9ICdPU0UnOwogIC8vIEF1dG8tZ2VuZXJhdGUgcm9vbSBjb2RlCiAgaWYgKCFyb29tQ29kZSkgYXV0b0dlbmVyYXRlUm9vbSgpOwogIHNob3coJ3MtbmV3Z2FtZScpOwogIGxvYWREbmRtb2RMaXN0KCk7Cn0KCmZ1bmN0aW9uIGdvVG9Mb2FkKCkgewogIGlmICghcGxheWVyTmFtZSkgcGxheWVyTmFtZSA9ICdBZHZlbnR1cmVyJzsKICBpc0hvc3QgPSBvbGxhbWFBdmFpbGFibGUgfHwgISFhcGlLZXk7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBzaG93TG9hZCgpOwp9CgpmdW5jdGlvbiBqb2luUm9vbUZyb21Mb2JieSgpIHsKICBjb25zdCBjb2RlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpLnZhbHVlLnRyaW0oKS50b1VwcGVyQ2FzZSgpOwogIGlmICghY29kZSkgeyBhbGVydCgnRW50ZXIgYSByb29tIGNvZGUuJyk7IHJldHVybjsgfQogIC8vIEluaXRpYWxpc2Ugc3RhdGUgZm9yIGd1ZXN0CiAgaWYgKCFwbGF5ZXJOYW1lKSBwbGF5ZXJOYW1lID0gJ1BsYXllcic7CiAgaXNIb3N0ID0gZmFsc2U7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBjaG9zZW5SdWxlcyA9ICdPU0UnOwogIC8vIFB1dCBjb2RlIGluIHRoZSBqb2luIGZpZWxkIGFuZCBjYWxsIGpvaW5Sb29tCiAgY29uc3Qgam9pbkZpZWxkID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpOwogIGlmIChqb2luRmllbGQpIGpvaW5GaWVsZC52YWx1ZSA9IGNvZGU7CiAgam9pblJvb20oKTsKfQoKYXN5bmMgZnVuY3Rpb24gYXV0b0dlbmVyYXRlUm9vbSgpIHsKICAvLyBTaWxlbnRseSBnZW5lcmF0ZSBhIHJvb20gY29kZSB3aXRob3V0IG5lZWRpbmcgYSBwbGF5ZXIgbmFtZSB5ZXQKICB0cnkgewogICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9jcmVhdGVfcm9vbScsIHttZXRob2Q6J1BPU1QnLAogICAgICBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7aG9zdDogcGxheWVyTmFtZSB8fCAnUm9vbSd9KX0pOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgaWYgKGRhdGEuY29kZSkgewogICAgICByb29tQ29kZSA9IGRhdGEuY29kZTsKICAgICAgaXNIb3N0ID0gdHJ1ZTsKICAgICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm9vbS1jb2RlLWRpc3AnKTsKICAgICAgaWYgKGVsKSBlbC50ZXh0Q29udGVudCA9IHJvb21Db2RlOwogICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgY2hlY2tOZ3Jva1N0YXR1cygpOwogICAgfQogIH0gY2F0Y2goZSkgeyBjb25zb2xlLmxvZygnYXV0b0dlbmVyYXRlUm9vbSBlcnJvcjonLCBlKTsgfQp9CgpmdW5jdGlvbiBjb3B5Um9vbUNvZGVOZXdHYW1lKCkgewogIGlmICghcm9vbUNvZGUpIHJldHVybjsKICBuYXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChyb29tQ29kZSkudGhlbigoKSA9PiB7CiAgICAvLyBicmllZiBmZWVkYmFjawogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm9vbS1jb2RlLWRpc3AnKTsKICAgIGlmIChlbCkgeyBjb25zdCBvcmlnID0gZWwudGV4dENvbnRlbnQ7IGVsLnRleHRDb250ZW50ID0gJ0NvcGllZCEnOyBzZXRUaW1lb3V0KCgpPT5lbC50ZXh0Q29udGVudD1vcmlnLDEyMDApOyB9CiAgfSkuY2F0Y2goKCkgPT4gcHJvbXB0KCdSb29tIGNvZGU6Jywgcm9vbUNvZGUpKTsKfQoKZnVuY3Rpb24gdG9nZ2xlSW52ZW50b3J5KCkgewogIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ludi1wYW5lbCcpOwogIGNvbnN0IGFycm93ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ludi10b2dnbGUtYXJyb3cnKTsKICBpZiAoIXBhbmVsKSByZXR1cm47CiAgY29uc3Qgb3BlbiA9IHBhbmVsLnN0eWxlLmRpc3BsYXkgIT09ICdub25lJzsKICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gb3BlbiA/ICdub25lJyA6ICdibG9jayc7CiAgaWYgKGFycm93KSBhcnJvdy5pbm5lckhUTUwgPSBvcGVuID8gJycgOiAnJzsKfQoKZnVuY3Rpb24gdXBkYXRlU3RhdHVzUGFuZWwoKSB7CiAgLy8gSHVuZ2VyIC0tIGhvdXNlIHJ1bGU6IC0xIGF0dGFjay9zYXZlcyBwZXIgZGF5IGFmdGVyIGRheSAzIHdpdGhvdXQgZm9vZAogIGNvbnN0IGh1bmdlckVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2h1bmdlci1iYXInKTsKICBpZiAoaHVuZ2VyRWwpIHsKICAgIGlmIChzdGFydmF0aW9uUGVuYWx0eSA+PSAzKSB7CiAgICAgIGh1bmdlckVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwMjAyMCI+U3RhcnZpbmcgKC0nICsgc3RhcnZhdGlvblBlbmFsdHkgKyAnIGF0dGFja3Mvc2F2ZXMpPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHN0YXJ2YXRpb25QZW5hbHR5ID4gMCkgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPkh1bmdyeSAoLScgKyBzdGFydmF0aW9uUGVuYWx0eSArICcgYXR0YWNrcy9zYXZlcyk8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAoZGF5c1dpdGhvdXRGb29kID4gMCkgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPkh1bmdyeSAoZGF5ICcgKyBkYXlzV2l0aG91dEZvb2QgKyAnLCBwZW5hbHR5IHN0YXJ0cyBkYXkgNCk8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAocmF0aW9uc0xlZnQgPT09IDEpIHsKICAgICAgaHVuZ2VyRWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA5MDQwIj5GZWQgKDEgcmF0aW9uIGxlZnQpPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHJhdGlvbnNMZWZ0ID09PSAwKSB7CiAgICAgIGh1bmdlckVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwOTA0MCI+Tm8gcmF0aW9ucyAocGVuYWx0eSBhZnRlciAzIGRheXMpPC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiM2YTlhNmEiPkZlZDwvc3Bhbj4nOwogICAgfQogIH0KICAvLyBEdW5nZW9uIHJlc3QgaW5kaWNhdG9yIC0tIG9ubHkgc2hvd24gd2hlbiBpbiBhIGR1bmdlb24gKGR1bmdlb25fbGV2ZWwgPj0gMSkKICBjb25zdCByZXN0Um93ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0YXR1cy1kdW5nZW9uLXJlc3QnKTsKICBjb25zdCByZXN0QmFyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2R1bmdlb24tcmVzdC1iYXInKTsKICBjb25zdCBpbkR1bmdlb24gPSBpc0luRHVuZ2VvbigpOwogIGlmIChyZXN0Um93KSByZXN0Um93LnN0eWxlLmRpc3BsYXkgPSBpbkR1bmdlb24gPyAnJyA6ICdub25lJzsKICBpZiAocmVzdEJhciAmJiBpbkR1bmdlb24pIHsKICAgIGlmICh0dXJuc1dpdGhvdXRSZXN0ID49IDYpIHsKICAgICAgcmVzdEJhci5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPlJlc3QgbmVlZGVkISAoJyArIHR1cm5zV2l0aG91dFJlc3QgKyAnIHR1cm5zKTwvc3Bhbj4nOwogICAgfSBlbHNlIGlmICh0dXJuc1dpdGhvdXRSZXN0ID49IDQpIHsKICAgICAgcmVzdEJhci5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPicgKyB0dXJuc1dpdGhvdXRSZXN0ICsgJy82IHR1cm5zIChyZXN0IHNvb24pPC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICByZXN0QmFyLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6IzZhOWE2YSI+JyArIHR1cm5zV2l0aG91dFJlc3QgKyAnLzYgdHVybnM8L3NwYW4+JzsKICAgIH0KICB9CiAgLy8gTGlnaHQgLSBvbmx5IHNob3cgd2hlbiBhIGxpZ2h0IHNvdXJjZSBpcyBBQ1RJVkVMWSBMSVQgb3IgY2hhcmFjdGVyIGlzIGluIGRhcmtuZXNzCiAgY29uc3QgbGlnaHRSb3cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RhdHVzLWxpZ2h0Jyk7CiAgY29uc3QgbGlnaHRFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsaWdodC1zdGF0dXMnKTsKICAvLyB0b3JjaExpdCA9IHRvcmNoIGhhcyBiZWVuIGRlbGliZXJhdGVseSB1c2VkIGFuZCBpcyBjb3VudGluZyBkb3duCiAgLy8gT25seSBzaG93IGRhcmtuZXNzIHdhcm5pbmcgaWYgdGhleSd2ZSBlbnRlcmVkIHNvbWV3aGVyZSBkYXJrICh0b3JjaFR1cm5zTGVmdCBldmVyIGNvdW50ZWQpCiAgY29uc3QgbGlnaHRBY3RpdmUgPSAodG9yY2hMaXQgJiYgdG9yY2hUdXJuc0xlZnQgPiAwKSB8fCAobGFudGVybkxpdCAmJiBoYXNMYW50ZXJuKSB8fCAodG9yY2hFdmVyVXNlZCAmJiAhaXNDYXJyeWluZ0xpZ2h0KTsKICBpZiAobGlnaHRSb3cpIGxpZ2h0Um93LnN0eWxlLmRpc3BsYXkgPSBsaWdodEFjdGl2ZSA/ICcnIDogJ25vbmUnOwogIGlmIChsaWdodEVsICYmIGxpZ2h0QWN0aXZlKSB7CiAgICBpZiAoIWlzQ2FycnlpbmdMaWdodCkgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwNjA2MCI+REFSS05FU1M8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAodG9yY2hMaXQgJiYgdG9yY2hUdXJuc0xlZnQgPiAwICYmIHRvcmNoVHVybnNMZWZ0IDw9IDIpIHsKICAgICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPlRvcmNoOiAnICsgdG9yY2hUdXJuc0xlZnQgKyAnIHR1cm5zIGxlZnQhPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHRvcmNoTGl0ICYmIHRvcmNoVHVybnNMZWZ0ID4gMCkgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICdUb3JjaDogJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJucyc7CiAgICB9IGVsc2UgaWYgKGxhbnRlcm5MaXQgJiYgaGFzTGFudGVybikgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICdMYW50ZXJuOiAnICsgbGFudGVybk9pbEZsYXNrc0xlZnQgKyAnIGZsYXNrKHMpJzsKICAgIH0KICB9CiAgLy8gQWN0aXZlIGVmZmVjdHMgKGNoYXJtLCBwb2lzb24sIHNwZWxsIHRpbWVycyBldGMpCiAgdXBkYXRlQWN0aXZlRWZmZWN0cygpOwp9CgpmdW5jdGlvbiBhZGRFZmZlY3QobmFtZSwgdHVybnMsIGNvbG9yKSB7CiAgY29sb3IgPSBjb2xvciB8fCAnI2MwOTA0MCc7CiAgYWN0aXZlRWZmZWN0cyA9IGFjdGl2ZUVmZmVjdHMuZmlsdGVyKGUgPT4gZS5uYW1lICE9PSBuYW1lKTsKICBhY3RpdmVFZmZlY3RzLnB1c2goe25hbWUsIHR1cm5zTGVmdDogdHVybnMsIGNvbG9yfSk7CiAgdXBkYXRlQWN0aXZlRWZmZWN0cygpOwp9CgpmdW5jdGlvbiB0aWNrRWZmZWN0cygpIHsKICBhY3RpdmVFZmZlY3RzID0gYWN0aXZlRWZmZWN0cy5maWx0ZXIoZSA9PiB7CiAgICBlLnR1cm5zTGVmdC0tOwogICAgaWYgKGUudHVybnNMZWZ0IDw9IDApIHsKICAgICAgYWRkRW50cnlSYXcoJ0VmZmVjdCBlbmRlZDogPHN0cm9uZz4nICsgZS5uYW1lICsgJzwvc3Ryb25nPicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIHJldHVybiBmYWxzZTsKICAgIH0KICAgIHJldHVybiB0cnVlOwogIH0pOwogIHVwZGF0ZUFjdGl2ZUVmZmVjdHMoKTsKfQoKZnVuY3Rpb24gdXBkYXRlQWN0aXZlRWZmZWN0cygpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhY3RpdmUtZWZmZWN0cycpOwogIGlmICghZWwpIHJldHVybjsKICBpZiAoIWFjdGl2ZUVmZmVjdHMubGVuZ3RoKSB7IGVsLmlubmVySFRNTCA9ICcnOyByZXR1cm47IH0KICBlbC5pbm5lckhUTUwgPSBhY3RpdmVFZmZlY3RzLm1hcChlID0+CiAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjEzcHg7Y29sb3I6JyArIGUuY29sb3IgKyAnO3BhZGRpbmc6MXB4IDA7Ij4nICsgZS5uYW1lICsgJzogJyArIGUudHVybnNMZWZ0ICsgJyB0dXJuczwvZGl2PicKICApLmpvaW4oJycpOwp9CgpmdW5jdGlvbiB0ZXN0Q29ubmVjdGlvbigpIHsKICAvLyBUZXN0IHRoZSBzYW1lIFVSTCBwYXR0ZXJuIHRoYXQgeGhyRmV0Y2ggdXNlcwogIGNvbnN0IHVybCA9IEJBU0VfVVJMICsgJy9waW5nJzsKICBhbGVydCgnVGVzdGluZyBVUkw6ICcgKyB1cmwpOwogIGNvbnN0IHhociA9IG5ldyBYTUxIdHRwUmVxdWVzdCgpOwogIHhoci5vcGVuKCdHRVQnLCB1cmwsIHRydWUpOwogIHhoci5vbmxvYWQgPSAoKSA9PiBhbGVydCgnT0s6ICcgKyB4aHIucmVzcG9uc2VUZXh0KTsKICB4aHIub25lcnJvciA9ICgpID0+IGFsZXJ0KCdGQUlMRUQgZm9yOiAnICsgdXJsKTsKICB4aHIuc2VuZCgpOwp9CgpmdW5jdGlvbiB0b2dnbGVBcGlLZXkoKSB7CiAgY29uc3QgYm94ICAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXBpLWtleS1ib3gnKTsKICBjb25zdCBhcnJvdyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhcGktYXJyb3cnKTsKICBjb25zdCBvcGVuICA9IGJveC5zdHlsZS5kaXNwbGF5ID09PSAnZmxleCc7CiAgYm94LnN0eWxlLmRpc3BsYXkgPSBvcGVuID8gJ25vbmUnIDogJ2ZsZXgnOwogIGlmIChhcnJvdykgYXJyb3cuaW5uZXJIVE1MID0gb3BlbiA/ICcmIzk2NjA7JyA6ICcmIzk2NTA7JzsKfQpmdW5jdGlvbiBvbkFwaUtleVR5cGVkKHZhbCkgewogIGNvbnN0IHN0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktc3RhdHVzJyk7CiAgaWYgKCFzdCkgcmV0dXJuOwogIGlmICghdmFsKSB7IHN0LnRleHRDb250ZW50ID0gJyc7IHJldHVybjsgfQogIGlmICh2YWwuc3RhcnRzV2l0aCgnc2stYW50LScpKSB7CiAgICBzdC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsgc3QudGV4dENvbnRlbnQgPSAnVmFsaWQga2V5IGZvcm1hdCc7CiAgfSBlbHNlIHsKICAgIHN0LnN0eWxlLmNvbG9yID0gJyNjMDkwNDAnOyBzdC50ZXh0Q29udGVudCA9ICdLZXkgc2hvdWxkIHN0YXJ0IHdpdGggc2stYW50LS4uLic7CiAgfQp9CmZ1bmN0aW9uIGFwcGx5QXBpS2V5KCkgewogIGNvbnN0IGlucCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdrZXktaW5wJyk7CiAgY29uc3Qgc3QgID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktc3RhdHVzJyk7CiAgaWYgKCFpbnApIHJldHVybjsKICBhcGlLZXkgPSBpbnAudmFsdWUudHJpbSgpOwogIGlmIChhcGlLZXkpIHsKICAgIGlmIChzdCkgeyBzdC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsgc3QudGV4dENvbnRlbnQgPSAnU2F2ZWQg4oCUIENsYXVkZSBIYWlrdSBwYXJzaW5nIGFjdGl2ZSc7IH0KICB9IGVsc2UgewogICAgaWYgKHN0KSB7IHN0LnN0eWxlLmNvbG9yID0gJ3ZhcigtLWluay1kaW0pJzsgc3QudGV4dENvbnRlbnQgPSAnQ2xlYXJlZCDigJQgT2xsYW1hIG9ubHknOyB9CiAgfQp9CmZ1bmN0aW9uIGdvSG9tZSgpIHsKICBjb25zdCBuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1uYW1lLWlucCcpLnZhbHVlLnRyaW0oKTsKICBjb25zdCBrID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2tleS1pbnAnKS52YWx1ZS50cmltKCk7CiAgY29uc29sZS5sb2coJ1tnb0hvbWVdIG5hbWU6JywgbiwgJ2tleTonLCAhIWssICdvbGxhbWE6Jywgb2xsYW1hQXZhaWxhYmxlLCAnX3NlcnZlcjonLCB3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZSk7CiAgcGxheWVyTmFtZSA9IG4gfHwgJ0FkdmVudHVyZXInOwogIGlmIChrKSB7IGFwaUtleSA9IGs7IH0KICBpc0hvc3QgPSAhIShrIHx8IG9sbGFtYUF2YWlsYWJsZSk7CiAgY29uc29sZS5sb2coJ1tnb0hvbWVdIGlzSG9zdDonLCBpc0hvc3QsICduYXZpZ2F0aW5nIHRvIHMtaG9tZScpOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdob21lLXdlbGNvbWUnKS50ZXh0Q29udGVudCA9ICdXZWxjb21lLCAnICsgcGxheWVyTmFtZSArICcuIFdoYXQgd291bGQgeW91IGxpa2UgdG8gZG8/JzsKICBzaG93KCdzLWhvbWUnKTsKICBjb25zb2xlLmxvZygnW2dvSG9tZV0gZG9uZScpOwp9CgpmdW5jdGlvbiBzaG93TmV3R2FtZSgpIHsKICBpZiAoIXJvb21Db2RlKSBhdXRvR2VuZXJhdGVSb29tKCk7CiAgc2hvdygncy1uZXdnYW1lJyk7CiAgbG9hZERuZG1vZExpc3QoKTsgLy8gYXV0by1wb3B1bGF0ZSBtb2R1bGUgbGlzdCBvbiBldmVyeSB2aXNpdAp9CgpmdW5jdGlvbiBzaG93TG9hZCgpIHsKICB4aHJGZXRjaChCQVNFX1VSTCArICcvc2F2ZXMnKS50aGVuKHI9PnIuanNvbigpKS50aGVuKHJlc3AgPT4gewogICAgY29uc3Qgc2F2ZXMgPSBBcnJheS5pc0FycmF5KHJlc3ApID8gcmVzcCA6IChyZXNwLnNhdmVzIHx8IFtdKTsKICAgIGNvbnN0IHdyYXAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbG9hZC13cmFwJyk7CiAgICBjb25zdCBsaXN0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NhdmUtbGlzdC1lbCcpOwogICAgd3JhcC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogICAgaWYgKCFzYXZlcy5sZW5ndGgpIHsgbGlzdC5pbm5lckhUTUwgPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Y29sb3I6dmFyKC0taW5rLWRpbSkiPk5vIHNhdmVkIGdhbWVzIGZvdW5kLjwvZGl2Pic7IHJldHVybjsgfQogICAgbGlzdC5pbm5lckhUTUwgPSBzYXZlcy5tYXAocyA9PgogICAgICBgPGRpdiBjbGFzcz0ic2F2ZS1pdGVtIj4KICAgICAgICA8ZGl2IGNsYXNzPSJzaS1pbmZvIj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNpLW5hbWUiPiR7cy5tb2R1bGVOYW1lfHwnQWR2ZW50dXJlJ308L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNpLW1ldGEiPiR7cy5wY05hbWV9ICogJHtzLnBjQ2xhc3N9ICogJHtuZXcgRGF0ZShzLnNhdmVkQXQpLnRvTG9jYWxlU3RyaW5nKCl9PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2dhcDo2cHg7Ij4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biIgb25jbGljaz0ibG9hZFNhdmUoJyR7cy5pZH0nKSIgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O3BhZGRpbmc6NHB4IDEwcHg7Ij5Mb2FkPC9idXR0b24+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9ImRlbGV0ZVNhdmUoJyR7cy5pZH0nKSIgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O3BhZGRpbmc6NHB4IDEwcHg7Ym9yZGVyLWNvbG9yOiM2YTIwMjA7Y29sb3I6I2MwNjA2MDsiPjwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj5gCiAgICApLmpvaW4oJycpOwogIH0pOwp9CgpmdW5jdGlvbiBsb2FkU2F2ZShpZCkgewogIHhockZldGNoKEJBU0VfVVJMICsgJy9sb2FkP2lkPScgKyBpZCkudGhlbihyPT5yLmpzb24oKSkudGhlbihkYXRhID0+IHsKICAgIGlmIChkYXRhLmVycm9yKSB7IGFsZXJ0KGRhdGEuZXJyb3IpOyByZXR1cm47IH0KICAgIC8vIFJvdXRlIHRocm91Z2ggY2hhcmFjdGVyIHNlbGVjdCBzY3JlZW4KICAgIGNvbnN0IG1vZExhYmVsID0gZGF0YS5tb2R1bGVOYW1lIHx8ICdBZHZlbnR1cmUnOwogICAgc2hvd0NoYXJTZWxlY3QoCiAgICAgICdTZWxlY3QgdGhlIGNoYXJhY3RlciB5b3Ugd2FudCB0byBwbGF5IHRoaXMgYWR2ZW50dXJlIHdpdGgsIG9yIGNyZWF0ZSBhIG5ldyBvbmUuJywKICAgICAgbW9kTGFiZWwsCiAgICAgIHt0eXBlOiAnc2F2ZScsIGRhdGE6IGRhdGF9CiAgICApOwogIH0pOwp9CgpmdW5jdGlvbiBkZWxldGVTYXZlKGlkKSB7CiAgaWYgKCFjb25maXJtKCdEZWxldGUgdGhpcyBzYXZlPycpKSByZXR1cm47CiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2RlbGV0ZV9zYXZlP2lkPScgKyBpZCwge21ldGhvZDonUE9TVCd9KS50aGVuKCgpID0+IHNob3dMb2FkKCkpOwp9Cgphc3luYyBmdW5jdGlvbiBjaGVja05ncm9rU3RhdHVzKCkgewogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL25ncm9rX3N0YXR1cycpOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmdyb2stc3RhdHVzLXR4dCcpOwogICAgaWYgKCFlbCkgcmV0dXJuOwogICAgaWYgKGRhdGEuYWN0aXZlICYmIGRhdGEudXJsKSB7CiAgICAgIG5ncm9rUHVibGljVXJsID0gZGF0YS51cmw7CiAgICAgIGVsLmlubmVySFRNTCA9CiAgICAgICAgJzxzdHJvbmcgc3R5bGU9ImNvbG9yOnZhcigtLWdvbGQpIj5JbnRlcm5ldCBhY2Nlc3MgYWN0aXZlITwvc3Ryb25nPjxicj4nICsKICAgICAgICAnRnJpZW5kcyBhbnl3aGVyZSBjYW4gam9pbi4gU2hhcmUgdGhpcyBsaW5rOjxicj4nICsKICAgICAgICAnPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLWluayk7Zm9udC1zaXplOjE2cHg7bGV0dGVyLXNwYWNpbmc6MC41cHg7Ij4nICsgZGF0YS51cmwgKyAnPC9zcGFuPicgKwogICAgICAgICcgPGJ1dHRvbiBvbmNsaWNrPSJjb3B5Tmdyb2tVcmwoKSIgc3R5bGU9ImJhY2tncm91bmQ6bm9uZTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y29sb3I6dmFyKC0taW5rLWRpbSk7Y3Vyc29yOnBvaW50ZXI7cGFkZGluZzoycHggOHB4O2ZvbnQtc2l6ZToxNHB4O21hcmdpbi1sZWZ0OjZweDsiPkNvcHk8L2J1dHRvbj48YnI+JyArCiAgICAgICAgJzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+UGxheWVycyBvcGVuIHRoYXQgVVJMIGluIHRoZWlyIGJyb3dzZXIsIHRoZW4gZW50ZXIgdGhlIHJvb20gY29kZS48L3NwYW4+JzsKICAgIH0gZWxzZSB7CiAgICAgIGVsLmlubmVySFRNTCA9CiAgICAgICAgJ0xBTiBvbmx5IC0tIGZyaWVuZHMgb24gdGhlIHNhbWUgbmV0d29yayBjYW4gY29ubmVjdC48YnI+JyArCiAgICAgICAgJzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+Rm9yIGludGVybmV0IHBsYXk6IGluc3RhbGwgJyArCiAgICAgICAgJzxhIGhyZWY9Imh0dHBzOi8vbmdyb2suY29tIiBzdHlsZT0iY29sb3I6dmFyKC0tZ29sZCkiPm5ncm9rPC9hPiwgJyArCiAgICAgICAgJ3RoZW4gcnVuIDxjb2RlIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLXBhbmVsKTtwYWRkaW5nOjFweCA1cHg7Ij5uZ3JvayBodHRwIDgwODA8L2NvZGU+IGluIGEgdGVybWluYWwgYmVmb3JlIHN0YXJ0aW5nIHRoZSBnYW1lLjwvc3Bhbj4nOwogICAgfQogIH0gY2F0Y2goZSkgewogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmdyb2stc3RhdHVzLXR4dCcpOwogICAgaWYgKGVsKSBlbC50ZXh0Q29udGVudCA9ICdMQU4gb25seSAoY291bGQgbm90IGNoZWNrIGludGVybmV0IHR1bm5lbCBzdGF0dXMpJzsKICB9Cn0KCmZ1bmN0aW9uIGNvcHlOZ3Jva1VybCgpIHsKICBpZiAoIW5ncm9rUHVibGljVXJsKSByZXR1cm47CiAgdHJ5IHsKICAgIG5hdmlnYXRvci5jbGlwYm9hcmQud3JpdGVUZXh0KG5ncm9rUHVibGljVXJsKS50aGVuKCgpID0+IHsKICAgICAgY29uc3QgYnRuID0gZXZlbnQudGFyZ2V0OwogICAgICBjb25zdCBvcmlnID0gYnRuLnRleHRDb250ZW50OwogICAgICBidG4udGV4dENvbnRlbnQgPSAnQ29waWVkISc7CiAgICAgIHNldFRpbWVvdXQoKCkgPT4gYnRuLnRleHRDb250ZW50ID0gb3JpZywgMTUwMCk7CiAgICB9KTsKICB9IGNhdGNoKGUpIHsKICAgIHByb21wdCgnQ29weSB0aGlzIFVSTDonLCBuZ3Jva1B1YmxpY1VybCk7CiAgfQp9CgpmdW5jdGlvbiBnZW5lcmF0ZVJvb20oKSB7CiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NyZWF0ZV9yb29tJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtob3N0OiBwbGF5ZXJOYW1lfSl9KQogICAgLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZGF0YSA9PiB7CiAgICAgIHJvb21Db2RlID0gZGF0YS5jb2RlOwogICAgICBpc011bHRpcGxheWVyID0gdHJ1ZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jvb20tY29kZS1kaXNwJykudGV4dENvbnRlbnQgPSByb29tQ29kZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jvb20tc2hhcmUtd3JhcCcpLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICAgIHJlbmRlclBsYXllclNsb3RzKFt7bmFtZTpwbGF5ZXJOYW1lLCByZWFkeTpmYWxzZX1dKTsKICAgICAgc3RhcnRQb2xsaW5nKCk7CiAgICAgIGNoZWNrTmdyb2tTdGF0dXMoKTsgIC8vIFNob3cgbmdyb2sgVVJMIG9yIExBTiBpbnN0cnVjdGlvbnMKICAgIH0pOwp9CgpmdW5jdGlvbiBqb2luUm9vbSgpIHsKICBjb25zdCBjb2RlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpLnZhbHVlLnRyaW0oKS50b1VwcGVyQ2FzZSgpOwogIGlmICghY29kZSkgeyBhbGVydCgnRW50ZXIgYSByb29tIGNvZGUuJyk7IHJldHVybjsgfQogIHhockZldGNoKEJBU0VfVVJMICsgJy9qb2luX3Jvb20nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGUsIHBsYXllcjogcGxheWVyTmFtZX0pfSkKICAgIC50aGVuKGRhdGEgPT4gewogICAgICBpZiAoZGF0YS5lcnJvcikgeyBhbGVydChkYXRhLmVycm9yKTsgcmV0dXJuOyB9CiAgICAgIC8vIEFsd2F5cyByb3V0ZSB0aHJvdWdoIGNoYXJhY3RlciBzZWxlY3Qgc2NyZWVuCiAgICAgIGRhdGEuY29kZSA9IGNvZGU7CiAgICAgIGNvbnN0IG1vZExhYmVsID0gZGF0YS5tb2R1bGVOYW1lIHx8ICdBZHZlbnR1cmUnOwogICAgICBzaG93Q2hhclNlbGVjdCgKICAgICAgICAnU2VsZWN0IHRoZSBjaGFyYWN0ZXIgeW91IHdhbnQgdG8gYnJpbmcgaW50byB0aGlzIGFkdmVudHVyZSwgb3IgY3JlYXRlIGEgbmV3IG9uZS4nLAogICAgICAgIG1vZExhYmVsLAogICAgICAgIHt0eXBlOiAnam9pbicsIGRhdGE6IGRhdGF9CiAgICAgICk7CiAgICB9KTsKfQoKZnVuY3Rpb24gcmVuZGVyUGxheWVyU2xvdHMocGxheWVycykgewogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1zbG90cy1saXN0Jyk7CiAgaWYgKCFlbCkgcmV0dXJuOwogIGVsLmlubmVySFRNTCA9IHBsYXllcnMubWFwKChwLGkpID0+CiAgICBgPGRpdiBjbGFzcz0icGxheWVyLXNsb3QiPgogICAgICA8ZGl2IGNsYXNzPSJwZG90ICR7cC5yZWFkeT8nb24nOid3YWl0J30iIHN0eWxlPSJiYWNrZ3JvdW5kOiR7UExBWUVSX0NPTE9SU1tpJVBMQVlFUl9DT0xPUlMubGVuZ3RoXX07JHtwLnJlYWR5PycnOicnfSI+PC9kaXY+CiAgICAgIDxzcGFuIHN0eWxlPSJmb250LXNpemU6MTdweDtjb2xvcjoke1BMQVlFUl9DT0xPUlNbaSVQTEFZRVJfQ09MT1JTLmxlbmd0aF19Ij4ke3AubmFtZX0ke3AubmFtZT09PXBsYXllck5hbWU/JyAoeW91KSc6Jyd9PC9zcGFuPgogICAgICAke3AucmVhZHk/JzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+PC9zcGFuPic6Jyd9CiAgICA8L2Rpdj5gCiAgKS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gc3RhcnRQb2xsaW5nKCkgewogIGlmIChwb2xsVGltZXIpIGNsZWFySW50ZXJ2YWwocG9sbFRpbWVyKTsKICBwb2xsVGltZXIgPSBzZXRJbnRlcnZhbChkb1BvbGwsIDIwMDApOwp9CgpmdW5jdGlvbiBkb1BvbGwoKSB7CiAgaWYgKCFyb29tQ29kZSkgcmV0dXJuOwogIGZldGNoKGAvcG9sbD9yb29tPSR7cm9vbUNvZGV9JnBsYXllcj0ke2VuY29kZVVSSUNvbXBvbmVudChwbGF5ZXJOYW1lKX0mc2VxPSR7bGFzdFNlcX1gKQogICAgLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZGF0YSA9PiB7CiAgICAgIGlmIChkYXRhLmVycm9yKSByZXR1cm47CiAgICAgIGxhc3RTZXEgPSBkYXRhLnNlcSB8fCBsYXN0U2VxOwoKICAgICAgLy8gVXBkYXRlIHBsYXllciBsaXN0CiAgICAgIGlmIChkYXRhLnBsYXllcnMgJiYgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1zbG90cy1saXN0JykpIHsKICAgICAgICByZW5kZXJQbGF5ZXJTbG90cyhkYXRhLnBsYXllcnMpOwogICAgICB9CgogICAgICAvLyBQYXJ0eSBzdGF0dXMgaW4gY2hhciBjcmVhdGUKICAgICAgaWYgKGRhdGEucGxheWVycyAmJiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGFydHktc3RhdHVzLXdyYXAnKSkgewogICAgICAgIHJlbmRlclBhcnR5U3RhdHVzKGRhdGEucGxheWVycyk7CiAgICAgIH0KCiAgICAgIC8vIE5ldyBjaGF0L2dhbWUgbWVzc2FnZXMKICAgICAgaWYgKGRhdGEubmV3TWVzc2FnZXMpIHsKICAgICAgICBkYXRhLm5ld01lc3NhZ2VzLmZvckVhY2gobSA9PiB7CiAgICAgICAgICBpZiAobS5hdXRob3IgIT09IHBsYXllck5hbWUgfHwgbS50eXBlID09PSAnZ20nIHx8IG0udHlwZSA9PT0gJ3N5c3RlbScpIHsKICAgICAgICAgICAgYWRkRW50cnlSYXcobS5odG1sLCBtLnR5cGUsIG0uYXV0aG9yKTsKICAgICAgICAgIH0KICAgICAgICB9KTsKICAgICAgfQoKICAgICAgLy8gU3RhdGUgdXBkYXRlcwogICAgICBpZiAoZGF0YS5nYW1lU3RhdGUpIHsKICAgICAgICBjb25zdCBncyA9IGRhdGEuZ2FtZVN0YXRlOwogICAgICAgIGlmIChncy5sb2MpIHsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NjZW5lLWxvYycpLnRleHRDb250ZW50ID0gZ3MubG9jOyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2NlbmUtdGFnJykudGV4dENvbnRlbnQgPSBncy5sb2N0YWd8fCcnOyB9CiAgICAgICAgaWYgKGdzLmJ1dHRvbnMpIHNldEJ1dHRvbnMoZ3MuYnV0dG9ucyk7CiAgICAgICAgaWYgKGdzLnF1ZXN0cyAmJiBwYy5xdWVzdHMpIHsgcGMucXVlc3RzID0gZ3MucXVlc3RzOyByZW5kZXJRdWVzdHMoKTsgfQogICAgICAgIGlmIChncy5wYXJ0eSkgewogICAgICAgICAgT2JqZWN0LmVudHJpZXMoZ3MucGFydHkpLmZvckVhY2goKFtwbiwgcGRdKSA9PiB7CiAgICAgICAgICAgIGlmIChwYXJ0eVBDc1twbl0pIHsgcGFydHlQQ3NbcG5dLmhwID0gcGQuaHA7IHBhcnR5UENzW3BuXS5tYXhocCA9IHBkLm1heGhwOyB9CiAgICAgICAgICB9KTsKICAgICAgICAgIHJlbmRlclBhcnR5UGFuZWwoKTsKICAgICAgICB9CiAgICAgIH0KCiAgICAgIC8vIFBhcnR5IFBDIHVwZGF0ZXMKICAgICAgaWYgKGRhdGEucGFydHlQQ3MpIHsgcGFydHlQQ3MgPSBkYXRhLnBhcnR5UENzOyByZW5kZXJQYXJ0eVBhbmVsKCk7IH0KCiAgICAgIC8vIEdhbWUgc3RhcnRlZCBzaWduYWwgZm9yIG5vbi1ob3N0cyBpbiBjaGFyIGNyZWF0ZQogICAgICBpZiAoZGF0YS5nYW1lU3RhcnRlZCAmJiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncy1jaGFyJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdhY3RpdmUnKSkgewogICAgICAgIHBjID0gZGF0YS5teVBjIHx8IHBjOwogICAgICAgIHBhcnR5UENzID0gZGF0YS5wYXJ0eVBDcyB8fCB7fTsKICAgICAgICBoaXN0b3J5ID0gZGF0YS5oaXN0b3J5IHx8IFtdOwogICAgICAgIHN5c3RlbVByb21wdCA9IGRhdGEuc3lzdGVtUHJvbXB0IHx8IHN5c3RlbVByb21wdDsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLW1vZCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgICBzaG93KCdzLWdhbWUnKTsKICAgICAgICB1cGRhdGVIVUQoKTsKICAgICAgICByZW5kZXJQYXJ0eVBhbmVsKCk7CiAgICAgICAgaWYgKGRhdGEubG9nRW50cmllcykgZGF0YS5sb2dFbnRyaWVzLmZvckVhY2goZSA9PiBhZGRFbnRyeVJhdyhlLmh0bWwsIGUudHlwZSwgZS5hdXRob3IpKTsKICAgICAgfQogICAgfSkuY2F0Y2goKCkgPT4ge30pOwp9CgpmdW5jdGlvbiByZW5kZXJQYXJ0eVN0YXR1cyhwbGF5ZXJzKSB7CiAgY29uc3Qgd3JhcCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdwYXJ0eS1zdGF0dXMtd3JhcCcpOwogIGNvbnN0IHJvd3MgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGFydHktc3RhdHVzLXJvd3MnKTsKICBpZiAocGxheWVycy5sZW5ndGggPD0gMSkgeyB3cmFwLnN0eWxlLmRpc3BsYXk9J25vbmUnOyByZXR1cm47IH0KICB3cmFwLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgcm93cy5pbm5lckhUTUwgPSBwbGF5ZXJzLm1hcCgocCxpKSA9PgogICAgYDxkaXYgY2xhc3M9InByZWFkeS1yb3ciPgogICAgICA8ZGl2IGNsYXNzPSJwZG90ICR7cC5yZWFkeT8nb24nOid3YWl0J30iIHN0eWxlPSJiYWNrZ3JvdW5kOiR7UExBWUVSX0NPTE9SU1tpJVBMQVlFUl9DT0xPUlMubGVuZ3RoXX0iPjwvZGl2PgogICAgICA8c3BhbiBzdHlsZT0iY29sb3I6JHtQTEFZRVJfQ09MT1JTW2klUExBWUVSX0NPTE9SUy5sZW5ndGhdfSI+JHtwLm5hbWV9PC9zcGFuPgogICAgICA8c3BhbiBzdHlsZT0iZm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0taW5rLWRpbSkiPiR7cC5yZWFkeT8nIFJlYWR5JzonLi4uIGNyZWF0aW5nIGNoYXJhY3Rlcid9PC9zcGFuPgogICAgPC9kaXY+YAogICkuam9pbignJyk7CiAgLy8gU2hvdyBiZWdpbiBidXR0b24gdG8gaG9zdCBpZiBhbGwgcmVhZHkKICBpZiAoaXNIb3N0KSB7CiAgICBjb25zdCBhbGxSZWFkeSA9IHBsYXllcnMuZXZlcnkocCA9PiBwLnJlYWR5KTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiZWdpbi1idG4nKS5zdHlsZS5kaXNwbGF5ID0gYWxsUmVhZHkgPyAnaW5saW5lLWJsb2NrJyA6ICdub25lJzsKICB9Cn0KCmZ1bmN0aW9uIHBpY2tSdWxlcyhlbCkgewogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5yYycpLmZvckVhY2goYyA9PiBjLmNsYXNzTGlzdC5yZW1vdmUoJ3BpY2tlZCcpKTsKICBlbC5jbGFzc0xpc3QuYWRkKCdwaWNrZWQnKTsKICBjaG9zZW5SdWxlcyA9IGVsLmRhdGFzZXQucjsKfQoKZnVuY3Rpb24gaGFuZGxlRmlsZShmKSB7CiAgdXBsb2FkZWRGaWxlID0gZjsKICBtb2R1bGVOYW1lID0gZi5uYW1lLnJlcGxhY2UoL1suXVteLl0rJC8sICcnKTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmlsZS1uYW1lLWRpc3AnKS50ZXh0Q29udGVudCA9ICcgJyArIGYubmFtZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmV4dC1idG4nKS5kaXNhYmxlZCA9IGZhbHNlOwp9CgpmdW5jdGlvbiBidWlsZENoYXJDcmVhdGUoKSB7CiAgcmVyb2xsKCk7CiAgYnVpbGRSYWNlR3JpZCgpOwogIGJ1aWxkQ2xhc3NHcmlkKCk7CiAgYnVpbGRFcXVpcG1lbnQoKTsKfQoKZnVuY3Rpb24gYnVpbGRSYWNlR3JpZCgpIHsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmFjZS1ncmlkJykuaW5uZXJIVE1MID0gT2JqZWN0LmVudHJpZXMoUkFDRVMpLm1hcCgoW25hbWUsZF0pID0+CiAgICBgPGRpdiBjbGFzcz0ic2VsLWNhcmQke25hbWU9PT1jaG9zZW5SYWNlPycgcGlja2VkJzonJ30iIGRhdGEtcj0iJHtuYW1lfSIgb25jbGljaz0icGlja1JhY2UodGhpcykiPgogICAgICA8ZGl2IGNsYXNzPSJjbiI+JHtkLmljb259ICR7bmFtZX08L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY2QiPiR7ZC5kZXNjLnN1YnN0cmluZygwLDYwKX08L2Rpdj4KICAgIDwvZGl2PmAKICApLmpvaW4oJycpOwogIHVwZGF0ZVJhY2VEZXNjKCk7Cn0KCmZ1bmN0aW9uIGJ1aWxkQ2xhc3NHcmlkKCkgewogIGNvbnN0IGFsbG93ZWQgPSBSQUNFU1tjaG9zZW5SYWNlXT8uY2xhc3NlcyB8fCBudWxsOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbGFzcy1ncmlkJykuaW5uZXJIVE1MID0gT2JqZWN0LmVudHJpZXMoQ0xBU1NFUykubWFwKChbbmFtZSxkXSkgPT4gewogICAgY29uc3QgZGlzID0gYWxsb3dlZCAmJiAhYWxsb3dlZC5pbmNsdWRlcyhuYW1lKTsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic2VsLWNhcmQke25hbWU9PT1jaG9zZW5DbGFzcyYmIWRpcz8nIHBpY2tlZCc6Jyd9JHtkaXM/JyBkaXNhYmxlZCc6Jyd9IgogICAgICBkYXRhLWM9IiR7bmFtZX0iICR7ZGlzPycnOidvbmNsaWNrPSJwaWNrQ2xhc3ModGhpcykiJ30+CiAgICAgIDxkaXYgY2xhc3M9ImNuIj4ke2QuaWNvbn0gJHtuYW1lfTwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjZCI+JHtkLmRlc2Muc3Vic3RyaW5nKDAsNTUpfTwvZGl2PgogICAgPC9kaXY+YDsKICB9KS5qb2luKCcnKTsKICBpZiAoYWxsb3dlZCAmJiAhYWxsb3dlZC5pbmNsdWRlcyhjaG9zZW5DbGFzcykpIHsKICAgIGNob3NlbkNsYXNzID0gYWxsb3dlZFswXTsKICAgIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoYC5zZWwtY2FyZFtkYXRhLWM9IiR7Y2hvc2VuQ2xhc3N9Il1gKT8uY2xhc3NMaXN0LmFkZCgncGlja2VkJyk7CiAgfQogIHVwZGF0ZUNsYXNzRGVzYygpOwogIGJ1aWxkRXF1aXBtZW50KCk7Cn0KCmZ1bmN0aW9uIHBpY2tSYWNlKGVsKSB7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnI3JhY2UtZ3JpZCAuc2VsLWNhcmQnKS5mb3JFYWNoKGMgPT4gYy5jbGFzc0xpc3QucmVtb3ZlKCdwaWNrZWQnKSk7CiAgZWwuY2xhc3NMaXN0LmFkZCgncGlja2VkJyk7CiAgY2hvc2VuUmFjZSA9IGVsLmRhdGFzZXQucjsKICB1cGRhdGVSYWNlRGVzYygpOwogIGJ1aWxkQ2xhc3NHcmlkKCk7CiAgcmVyb2xsKCk7Cn0KCmZ1bmN0aW9uIHBpY2tDbGFzcyhlbCkgewogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJyNjbGFzcy1ncmlkIC5zZWwtY2FyZCcpLmZvckVhY2goYyA9PiBjLmNsYXNzTGlzdC5yZW1vdmUoJ3BpY2tlZCcpKTsKICBlbC5jbGFzc0xpc3QuYWRkKCdwaWNrZWQnKTsKICBjaG9zZW5DbGFzcyA9IGVsLmRhdGFzZXQuYzsKICB1cGRhdGVDbGFzc0Rlc2MoKTsKICBidWlsZEVxdWlwbWVudCgpOwp9CgpmdW5jdGlvbiB1cGRhdGVSYWNlRGVzYygpIHsKICBjb25zdCByID0gUkFDRVNbY2hvc2VuUmFjZV07CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JhY2Utc3BlY2lhbHMnKS50ZXh0Q29udGVudCA9IHI/LnNwZWNpYWxzPy5sZW5ndGggPyAnICcgKyByLnNwZWNpYWxzLmpvaW4oJyAqICcpIDogJyc7Cn0KCmZ1bmN0aW9uIHVwZGF0ZUNsYXNzRGVzYygpIHsKICBjb25zdCBjID0gQ0xBU1NFU1tjaG9zZW5DbGFzc107CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NsYXNzLWRlc2MnKS50ZXh0Q29udGVudCA9IGMgPyBjLmRlc2MgOiAnJzsKfQoKZnVuY3Rpb24gcmQoZCkgeyByZXR1cm4gTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKmQpKzE7IH0KCmZ1bmN0aW9uIHIzKCkgeyByZXR1cm4gcmQoNikrcmQoNikrcmQoNik7IH0KCmZ1bmN0aW9uIHI0ZDYoKSB7IGxldCBhPVtyZCg2KSxyZCg2KSxyZCg2KSxyZCg2KV07IGEuc29ydCgoeCx5KT0+eC15KTsgYS5zaGlmdCgpOyByZXR1cm4gYS5yZWR1Y2UoKHMsdik9PnMrdiwwKTsgfQoKZnVuY3Rpb24gbW9kKHYpIHsgbGV0IG09TWF0aC5mbG9vcigodi0xMCkvMik7IHJldHVybiBtPj0wPycrJyttOicnK207IH0KCmZ1bmN0aW9uIG1vZE4odikgeyByZXR1cm4gTWF0aC5mbG9vcigodi0xMCkvMik7IH0KCmZ1bmN0aW9uIHJlcm9sbCgpIHsKICBbJ1NUUicsJ0RFWCcsJ0NPTicsJ0lOVCcsJ1dJUycsJ0NIQSddLmZvckVhY2gocyA9PiByb2xsZWRTdGF0c1tzXSA9IHIzKCkpOwogIGNvbnN0IGJvbnVzZXMgPSBSQUNFU1tjaG9zZW5SYWNlXT8uYm9udXNlcyB8fCB7fTsKICBPYmplY3QuZW50cmllcyhib251c2VzKS5mb3JFYWNoKChbcyxiXSkgPT4gcm9sbGVkU3RhdHNbc10gPSBNYXRoLm1pbigxOCwgcm9sbGVkU3RhdHNbc10rYikpOwogIHJlbmRlclN0YXRzKCk7Cn0KCmZ1bmN0aW9uIHJlbmRlclN0YXRzKCkgewogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdGF0LWdyaWQnKS5pbm5lckhUTUwgPSBbJ1NUUicsJ0RFWCcsJ0NPTicsJ0lOVCcsJ1dJUycsJ0NIQSddLm1hcChzID0+IHsKICAgIGNvbnN0IHY9cm9sbGVkU3RhdHNbc10sIG09bW9kTih2KSwgbWM9bT4wPydwb3MnOm08MD8nbmVnJzonJzsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic3RhdC1ib3giPjxkaXYgY2xhc3M9InNuIj4ke3N9PC9kaXY+PGRpdiBjbGFzcz0ic3YiPiR7dn08L2Rpdj48ZGl2IGNsYXNzPSJzbSAke21jfSI+JHttb2Qodil9PC9kaXY+PC9kaXY+YDsKICB9KS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gYnVpbGRFcXVpcG1lbnQoKSB7CiAgc3RhcnRpbmdHb2xkID0gR09MRF9CWV9DTEFTU1tjaG9zZW5DbGFzc10gfHwgNjA7CiAgZ29sZFNwZW50ID0gMDsKICBzZWxlY3RlZEVxdWlwID0ge307CiAgZXh0cmFJdGVtcyA9IFtdOwogIHNlbGVjdGVkRXF1aXBJdGVtcy5jbGVhcigpOyAgLy8gcmVzZXQgZXF1aXBtZW50IHNlbGVjdGlvbgoKICBjb25zdCBjYXRzID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2VxdWlwLWNhdGVnb3JpZXMnKTsKICBjb25zdCBhbGxvd2VkV2VhcG9ucyA9IENMQVNTX1dFQVBPTl9SRVNUUklDVElPTlNbY2hvc2VuQ2xhc3NdOyAvLyBudWxsID0gYWxsCiAgY29uc3QgYWxsb3dlZEFybW91ciAgPSBDTEFTU19BUk1PVVJfUkVTVFJJQ1RJT05TW2Nob3NlbkNsYXNzXSB8fCBbXTsKCiAgLy8gRmlsdGVyIHdlYXBvbnMgYnkgY2xhc3MgcmVzdHJpY3Rpb24KICBjb25zdCBtZWxlZVdlYXBvbnMgID0gT2JqZWN0LmVudHJpZXMoT1NFX1dFQVBPTlMpCiAgICAuZmlsdGVyKChbbix3XSkgPT4gIXcucmFuZ2VkICYmICghYWxsb3dlZFdlYXBvbnMgfHwgYWxsb3dlZFdlYXBvbnMuaW5jbHVkZXMobikpKTsKICBjb25zdCByYW5nZWRXZWFwb25zID0gT2JqZWN0LmVudHJpZXMoT1NFX1dFQVBPTlMpCiAgICAuZmlsdGVyKChbbix3XSkgPT4gdy5yYW5nZWQgJiYgdy5kbWcgIT09ICctJyAmJiAoIWFsbG93ZWRXZWFwb25zIHx8IGFsbG93ZWRXZWFwb25zLmluY2x1ZGVzKG4pKSk7CiAgY29uc3QgYW1tb0l0ZW1zICAgICA9IE9iamVjdC5lbnRyaWVzKE9TRV9XRUFQT05TKQogICAgLmZpbHRlcigoW24sd10pID0+IHcucmFuZ2VkICYmIHcuZG1nID09PSAnLScpOwogIGNvbnN0IGFybW91ckl0ZW1zICAgPSBPYmplY3QuZW50cmllcyhPU0VfQVJNT1VSKQogICAgLmZpbHRlcigoW25dKSA9PiBhbGxvd2VkQXJtb3VyLmluY2x1ZGVzKG4pKTsKICBjb25zdCBlcXVpcEl0ZW1zICAgID0gT2JqZWN0LmVudHJpZXMoT1NFX0VRVUlQTUVOVCk7CgogIGZ1bmN0aW9uIHdlYXBvbkxhYmVsKG5hbWUsIHcpIHsKICAgIGNvbnN0IGNvc3QgPSB3LmNvc3QgPiAwID8gYCAoJHt3LmNvc3R9Z3ApYCA6ICcgKGZyZWUpJzsKICAgIGNvbnN0IG5vdGVzID0gdy5ub3RlcyA/IGAgLS0gJHt3Lm5vdGVzfWAgOiAnJzsKICAgIHJldHVybiBgJHtuYW1lfSBbJHt3LmRtZ31dJHtjb3N0fSR7bm90ZXN9YDsKICB9CiAgZnVuY3Rpb24gYXJtb3VyTGFiZWwobmFtZSwgYSkgewogICAgcmV0dXJuIGAke25hbWV9IC0tIEFDICR7YS5hY30gKCR7YS5jb3N0fWdwKWA7CiAgfQogIGZ1bmN0aW9uIGVxdWlwTGFiZWwobmFtZSwgZSkgewogICAgY29uc3QgY29zdCA9IGUuY29zdCA+IDAgPyBgICgke2UuY29zdH1ncClgIDogJyAoZnJlZSknOwogICAgY29uc3Qgbm90ZXMgPSBlLm5vdGVzID8gYCAtLSAke2Uubm90ZXN9YCA6ICcnOwogICAgcmV0dXJuIGAke25hbWV9JHtjb3N0fSR7bm90ZXN9YDsKICB9CgogIGxldCBodG1sID0gJyc7CgogIC8vIE1lbGVlIHdlYXBvbnMKICBpZiAobWVsZWVXZWFwb25zLmxlbmd0aCkgewogICAgaHRtbCArPSBidWlsZEVxdWlwU2VjdGlvbignTWVsZWUgV2VhcG9uJywgbWVsZWVXZWFwb25zLm1hcCgoW24sd10pID0+ICh7CiAgICAgIGtleTogbiwgbGFiZWw6IHdlYXBvbkxhYmVsKG4sdyksIGNvc3Q6IHcuY29zdAogICAgfSkpKTsKICB9CgogIC8vIFJhbmdlZCB3ZWFwb25zCiAgaWYgKHJhbmdlZFdlYXBvbnMubGVuZ3RoKSB7CiAgICBodG1sICs9IGJ1aWxkRXF1aXBTZWN0aW9uKCdSYW5nZWQgV2VhcG9uJywgcmFuZ2VkV2VhcG9ucy5tYXAoKFtuLHddKSA9PiAoewogICAgICBrZXk6IG4sIGxhYmVsOiB3ZWFwb25MYWJlbChuLHcpLCBjb3N0OiB3LmNvc3QKICAgIH0pKSwgdHJ1ZSk7IC8vIG9wdGlvbmFsCiAgfQoKICAvLyBBbW1vIChzaG93biBvbmx5IGlmIHJhbmdlZCB3ZWFwb24gc2VsZWN0ZWQgLS0gYWx3YXlzIHNob3cgYWxsKQogIGlmIChyYW5nZWRXZWFwb25zLmxlbmd0aCkgewogICAgaHRtbCArPSBidWlsZEVxdWlwU2VjdGlvbignQW1tdW5pdGlvbicsIGFtbW9JdGVtcy5tYXAoKFtuLHddKSA9PiAoewogICAgICBrZXk6IG4sIGxhYmVsOiBgJHtufSR7dy5jb3N0ID4gMCA/ICcgKCcrdy5jb3N0KydncCknIDogJyAoZnJlZSknfWAsIGNvc3Q6IHcuY29zdAogICAgfSkpLCB0cnVlKTsKICB9CgogIC8vIEFybW91cgogIGlmIChhcm1vdXJJdGVtcy5sZW5ndGgpIHsKICAgIGh0bWwgKz0gYnVpbGRFcXVpcFNlY3Rpb24oJ0FybW91cicsIGFybW91ckl0ZW1zLm1hcCgoW24sYV0pID0+ICh7CiAgICAgIGtleTogbiwgbGFiZWw6IGFybW91ckxhYmVsKG4sYSksIGNvc3Q6IGEuY29zdAogICAgfSkpKTsKICAgIC8vIFNoaWVsZCBhcyBzZXBhcmF0ZSBvcHRpb25hbCBwaWNrIGlmIGNsYXNzIGFsbG93cwogICAgaWYgKGFsbG93ZWRBcm1vdXIuaW5jbHVkZXMoJ1NoaWVsZCcpKSB7CiAgICAgIGh0bWwgKz0gYnVpbGRFcXVpcFNlY3Rpb24oJ1NoaWVsZCcsIFt7a2V5OidTaGllbGQnLCBsYWJlbDonU2hpZWxkIC0tICsxIEFDICgxMGdwKScsIGNvc3Q6MTB9LAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAge2tleTonbm9uZScsIGxhYmVsOidObyBTaGllbGQnLCBjb3N0OjB9XSwgZmFsc2UpOwogICAgfQogIH0KCiAgLy8gRXF1aXBtZW50IC0tIHBpY2sgdXAgdG8gNCBpdGVtcyBmcm9tIHRoZSBPU0UgbGlzdAogIGh0bWwgKz0gYDxkaXYgY2xhc3M9ImVxdWlwLWNhdGVnb3J5Ij4KICAgIDxkaXYgY2xhc3M9ImVxdWlwLWNhdC10aXRsZSI+RXF1aXBtZW50IChwaWNrIGl0ZW1zIC0tIGNvc3QgZGVkdWN0ZWQgZnJvbSBnb2xkKTwvZGl2PgogICAgPGRpdiBjbGFzcz0iZXF1aXAtb3B0aW9ucyIgaWQ9Im9zZS1lcXVpcC1ncmlkIj4KICAgICAgJHtlcXVpcEl0ZW1zLm1hcCgoW24sZV0pID0+CiAgICAgICAgYDxkaXYgY2xhc3M9ImVxdWlwLW9wdCIgZGF0YS1jYXQ9ImVxdWlwIiBkYXRhLWl0ZW09IiR7bn0iIGRhdGEtY29zdD0iJHtlLmNvc3R9IgogICAgICAgICAgb25jbGljaz0idG9nZ2xlRXF1aXBJdGVtKHRoaXMpIj4ke2VxdWlwTGFiZWwobixlKX08L2Rpdj5gCiAgICAgICkuam9pbignJyl9CiAgICA8L2Rpdj4KICA8L2Rpdj5gOwoKICBjYXRzLmlubmVySFRNTCA9IGh0bWw7CiAgcmVjYWxjR29sZFNwZW50KCk7CiAgdXBkYXRlR29sZERpc3BsYXkoKTsKICB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCk7Cn0KCmZ1bmN0aW9uIGJ1aWxkRXF1aXBTZWN0aW9uKGNhdCwgaXRlbXMsIG9wdGlvbmFsPWZhbHNlKSB7CiAgaWYgKCFpdGVtcy5sZW5ndGgpIHJldHVybiAnJzsKICBjb25zdCBmaXJzdEtleSA9IG9wdGlvbmFsID8gJ25vbmUnIDogaXRlbXNbMF0ua2V5OwogIGlmICghb3B0aW9uYWwgJiYgIXNlbGVjdGVkRXF1aXBbY2F0XSkgc2VsZWN0ZWRFcXVpcFtjYXRdID0gaXRlbXNbMF0ua2V5OwogIGlmIChvcHRpb25hbCAmJiAhc2VsZWN0ZWRFcXVpcFtjYXRdKSBzZWxlY3RlZEVxdWlwW2NhdF0gPSAnbm9uZSc7CiAgY29uc3Qgbm9uZU9wdCA9IG9wdGlvbmFsID8gYDxkaXYgY2xhc3M9ImVxdWlwLW9wdCR7Zmlyc3RLZXk9PT0nbm9uZSc/JyBzZWwnOicnfSIgZGF0YS1jYXQ9IiR7Y2F0fSIgZGF0YS1pdGVtPSJub25lIiBkYXRhLWNvc3Q9IjAiIG9uY2xpY2s9InBpY2tFcXVpcCh0aGlzKSI+Tm9uZTwvZGl2PmAgOiAnJzsKICByZXR1cm4gYDxkaXYgY2xhc3M9ImVxdWlwLWNhdGVnb3J5Ij4KICAgIDxkaXYgY2xhc3M9ImVxdWlwLWNhdC10aXRsZSI+JHtjYXR9PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJlcXVpcC1vcHRpb25zIj4KICAgICAgJHtub25lT3B0fQogICAgICAke2l0ZW1zLm1hcChpdGVtID0+CiAgICAgICAgYDxkaXYgY2xhc3M9ImVxdWlwLW9wdCR7aXRlbS5rZXk9PT1maXJzdEtleSYmIW9wdGlvbmFsPycgc2VsJzonJ30iIGRhdGEtY2F0PSIke2NhdH0iIGRhdGEtaXRlbT0iJHtpdGVtLmtleX0iIGRhdGEtY29zdD0iJHtpdGVtLmNvc3R9IiBvbmNsaWNrPSJwaWNrRXF1aXAodGhpcykiPiR7aXRlbS5sYWJlbH08L2Rpdj5gCiAgICAgICkuam9pbignJyl9CiAgICA8L2Rpdj4KICA8L2Rpdj5gOwp9CgpmdW5jdGlvbiB0b2dnbGVFcXVpcEl0ZW0oZWwpIHsKICBjb25zdCBpdGVtID0gZWwuZGF0YXNldC5pdGVtOwogIGNvbnN0IGNvc3QgPSBwYXJzZUludChlbC5kYXRhc2V0LmNvc3QpIHx8IDA7CiAgaWYgKHNlbGVjdGVkRXF1aXBJdGVtcy5oYXMoaXRlbSkpIHsKICAgIHNlbGVjdGVkRXF1aXBJdGVtcy5kZWxldGUoaXRlbSk7CiAgICBlbC5jbGFzc0xpc3QucmVtb3ZlKCdzZWwnKTsKICB9IGVsc2UgewogICAgLy8gQ2hlY2sgaWYgd2UgY2FuIGFmZm9yZCBpdAogICAgaWYgKGdvbGRTcGVudCArIGNvc3QgPiBzdGFydGluZ0dvbGQpIHsKICAgICAgZWwuc3R5bGUub3V0bGluZSA9ICcxcHggc29saWQgI2MwNjA2MCc7CiAgICAgIHNldFRpbWVvdXQoKCkgPT4gZWwuc3R5bGUub3V0bGluZSA9ICcnLCA4MDApOwogICAgICByZXR1cm47CiAgICB9CiAgICBzZWxlY3RlZEVxdWlwSXRlbXMuYWRkKGl0ZW0pOwogICAgZWwuY2xhc3NMaXN0LmFkZCgnc2VsJyk7CiAgfQogIC8vIFVwZGF0ZSBleHRyYUl0ZW1zIGZyb20gc2VsZWN0ZWRFcXVpcEl0ZW1zCiAgZXh0cmFJdGVtcyA9IEFycmF5LmZyb20oc2VsZWN0ZWRFcXVpcEl0ZW1zKTsKICByZWNhbGNHb2xkU3BlbnQoKTsKICB1cGRhdGVHb2xkRGlzcGxheSgpOwogIHVwZGF0ZUludmVudG9yeVByZXZpZXcoKTsKfQoKZnVuY3Rpb24gcmVjYWxjR29sZFNwZW50KCkgewogIGdvbGRTcGVudCA9IDA7CiAgLy8gV2VhcG9uIGNvc3RzCiAgT2JqZWN0LmVudHJpZXMoc2VsZWN0ZWRFcXVpcCkuZm9yRWFjaCgoW2NhdCwga2V5XSkgPT4gewogICAgaWYgKGtleSA9PT0gJ25vbmUnKSByZXR1cm47CiAgICBjb25zdCB3ID0gT1NFX1dFQVBPTlNba2V5XTsKICAgIGNvbnN0IGEgPSBPU0VfQVJNT1VSW2tleV07CiAgICBpZiAodykgZ29sZFNwZW50ICs9IHcuY29zdDsKICAgIGVsc2UgaWYgKGEpIGdvbGRTcGVudCArPSBhLmNvc3Q7CiAgfSk7CiAgLy8gRXF1aXBtZW50IGNvc3RzCiAgc2VsZWN0ZWRFcXVpcEl0ZW1zLmZvckVhY2gobmFtZSA9PiB7CiAgICBjb25zdCBlID0gT1NFX0VRVUlQTUVOVFtuYW1lXTsKICAgIGlmIChlKSBnb2xkU3BlbnQgKz0gZS5jb3N0OwogIH0pOwp9CgpmdW5jdGlvbiBwaWNrRXF1aXAoZWwpIHsKICBjb25zdCBjYXQgPSBlbC5kYXRhc2V0LmNhdDsKICBjb25zdCBpdGVtID0gZWwuZGF0YXNldC5pdGVtOwogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoYC5lcXVpcC1vcHRbZGF0YS1jYXQ9IiR7Y2F0fSJdYCkuZm9yRWFjaChlID0+IGUuY2xhc3NMaXN0LnJlbW92ZSgnc2VsJykpOwogIGVsLmNsYXNzTGlzdC5hZGQoJ3NlbCcpOwogIHNlbGVjdGVkRXF1aXBbY2F0XSA9IGl0ZW07CiAgcmVjYWxjR29sZFNwZW50KCk7CiAgdXBkYXRlR29sZERpc3BsYXkoKTsKICB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCk7CiAgdXBkYXRlSW52ZW50b3J5UHJldmlldygpOwp9CgpmdW5jdGlvbiByZW5kZXJFeHRyYUl0ZW1zKCkgewogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2V4dHJhLWl0ZW1zLWxpc3QnKTsKICBlbC5pbm5lckhUTUwgPSBTSE9QX0lURU1TLm1hcChpdGVtID0+CiAgICBgPGRpdiBjbGFzcz0iZXF1aXAtb3B0JHtleHRyYUl0ZW1zLmluY2x1ZGVzKGl0ZW0ubmFtZSk/JyBzZWwnOicnfSIgCiAgICAgIG9uY2xpY2s9InRvZ2dsZUV4dHJhKCcke2l0ZW0ubmFtZX0nLCR7aXRlbS5jb3N0fSkiPiR7aXRlbS5uYW1lfSAoJHtpdGVtLmNvc3R9Z3ApPC9kaXY+YAogICkuam9pbignJyk7Cn0KCmZ1bmN0aW9uIHRvZ2dsZUV4dHJhKG5hbWUsIGNvc3QpIHsKICBjb25zdCBpZHggPSBleHRyYUl0ZW1zLmluZGV4T2YobmFtZSk7CiAgaWYgKGlkeCA+PSAwKSB7CiAgICBleHRyYUl0ZW1zLnNwbGljZShpZHgsIDEpOwogICAgZ29sZFNwZW50IC09IGNvc3Q7CiAgfSBlbHNlIHsKICAgIGlmIChnb2xkU3BlbnQgKyBjb3N0ID4gc3RhcnRpbmdHb2xkKSB7IGFsZXJ0KGBOb3QgZW5vdWdoIGdvbGQhIFlvdSBoYXZlICR7c3RhcnRpbmdHb2xkIC0gZ29sZFNwZW50fWdwIHJlbWFpbmluZy5gKTsgcmV0dXJuOyB9CiAgICBleHRyYUl0ZW1zLnB1c2gobmFtZSk7CiAgICBnb2xkU3BlbnQgKz0gY29zdDsKICB9CiAgcmVuZGVyRXh0cmFJdGVtcygpOwogIHVwZGF0ZUdvbGREaXNwbGF5KCk7CiAgdXBkYXRlSW52ZW50b3J5UHJldmlldygpOwp9CgpmdW5jdGlvbiB1cGRhdGVHb2xkRGlzcGxheSgpIHsKICByZWNhbGNHb2xkU3BlbnQoKTsKICBjb25zdCByZW1haW5pbmcgPSBzdGFydGluZ0dvbGQgLSBnb2xkU3BlbnQ7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZ29sZC1yZW1haW5pbmcnKTsKICBpZiAoZWwpIHsKICAgIGVsLnRleHRDb250ZW50ID0gJ0dvbGQ6ICcgKyByZW1haW5pbmcgKyAnZ3AgcmVtYWluaW5nIChzdGFydGVkIHdpdGggJyArIHN0YXJ0aW5nR29sZCArICdncCwgc3BlbnQgJyArIGdvbGRTcGVudCArICdncCknOwogICAgZWwuc3R5bGUuY29sb3IgPSByZW1haW5pbmcgPCAwID8gJyNjMDYwNjAnIDogcmVtYWluaW5nIDwgMjAgPyAnI2MwOTA0MCcgOiAndmFyKC0taW5rLWRpbSknOwogIH0KfQoKZnVuY3Rpb24gc3BsaXRDb21iaW5lZEl0ZW0oaXRlbSkgewogIC8vIE9ubHkgc3BsaXQgd2VhcG9uK2FtbW8gcGF0dGVybnMgbGlrZSAiTGlnaHQgQ3Jvc3Nib3cgKyBCb2x0cyB4MjAiCiAgLy8gRG8gTk9UIHNwbGl0IGFybW91ciBjb21ib3MgbGlrZSAiQ2hhaW4gTWFpbCArIFNoaWVsZCIgb3IgIlNoaWVsZCAoKzEgQUMpIgogIGNvbnN0IGFtbW9QYXR0ZXJuID0gL2JvbHRzP3xhcnJvd3M/fHF1YXJyZWxzP3xzaG90cz8vaTsKICBpZiAoIWl0ZW0uaW5jbHVkZXMoJysnKSkgcmV0dXJuIFtpdGVtXTsKICAvLyBPbmx5IHNwbGl0IGlmIG9uZSBwYXJ0IGxvb2tzIGxpa2UgYW1tbwogIGNvbnN0IHBhcnRzID0gaXRlbS5zcGxpdCgnKycpLm1hcChzID0+IHMudHJpbSgpKTsKICBjb25zdCBoYXNBbW1vID0gcGFydHMuc29tZShwID0+IGFtbW9QYXR0ZXJuLnRlc3QocCkpOwogIGlmICghaGFzQW1tbykgcmV0dXJuIFtpdGVtXTsgLy8gS2VlcCAiQ2hhaW4gTWFpbCArIFNoaWVsZCIgYXMgb25lIGl0ZW0KICByZXR1cm4gcGFydHMubWFwKHBhcnQgPT4gewogICAgLy8gTm9ybWFsaXNlICIyMCBib2x0cyIgLT4gIkJvbHRzIHgyMCIKICAgIGNvbnN0IG0gPSBwYXJ0Lm1hdGNoKC9eKFsuXWQrKVsuXXMrKC4rKSQvKTsKICAgIGlmIChtKSByZXR1cm4gbVsyXS5jaGFyQXQoMCkudG9VcHBlckNhc2UoKSArIG1bMl0uc2xpY2UoMSkgKyAnIHgnICsgbVsxXTsKICAgIHJldHVybiBwYXJ0OwogIH0pLmZpbHRlcihCb29sZWFuKTsKfQoKZnVuY3Rpb24gZ2V0RmluYWxJbnZlbnRvcnkoKSB7CiAgY29uc3QgaXRlbXMgPSBbXTsKCiAgLy8gQWRkIHNlbGVjdGVkIHdlYXBvbnMvYXJtb3VyIGZyb20gcmFkaW8tc3R5bGUgcGlja3MKICBPYmplY3QuZW50cmllcyhzZWxlY3RlZEVxdWlwKS5mb3JFYWNoKChbY2F0LCBrZXldKSA9PiB7CiAgICBpZiAoIWtleSB8fCBrZXkgPT09ICdub25lJykgcmV0dXJuOwogICAgLy8gSXQncyBhIHdlYXBvbiBvciBhcm1vdXIga2V5IGZyb20gT1NFX1dFQVBPTlMgLyBPU0VfQVJNT1VSCiAgICBjb25zdCB3ID0gT1NFX1dFQVBPTlNba2V5XTsKICAgIGNvbnN0IGEgPSBPU0VfQVJNT1VSW2tleV07CiAgICBpZiAodykgewogICAgICAvLyBBZGQgd2VhcG9uOyBhbW1vIGl0ZW1zIHN0b3JlZCBzZXBhcmF0ZWx5IGluIHN0YXR1cwogICAgICBpZiAody5kbWcgPT09ICctJykgcmV0dXJuOyAvLyBhbW1vIGhhbmRsZWQgYmVsb3cKICAgICAgaXRlbXMucHVzaChrZXkpOwogICAgfSBlbHNlIGlmIChhKSB7CiAgICAgIGl0ZW1zLnB1c2goa2V5KTsKICAgIH0gZWxzZSBpZiAoa2V5ICE9PSAnbm9uZScpIHsKICAgICAgLy8gRmFsbGJhY2s6IGp1c3QgYWRkIHRoZSBrZXkgYXMtaXMKICAgICAgaXRlbXMucHVzaChrZXkpOwogICAgfQogIH0pOwoKICAvLyBBZGQgYW1tbyBzZWxlY3Rpb25zCiAgT2JqZWN0LmVudHJpZXMoc2VsZWN0ZWRFcXVpcCkuZm9yRWFjaCgoW2NhdCwga2V5XSkgPT4gewogICAgaWYgKCFrZXkgfHwga2V5ID09PSAnbm9uZScpIHJldHVybjsKICAgIGNvbnN0IHcgPSBPU0VfV0VBUE9OU1trZXldOwogICAgaWYgKHcgJiYgdy5kbWcgPT09ICctJykgaXRlbXMucHVzaChrZXkpOwogIH0pOwoKICAvLyBBZGQgbXVsdGktc2VsZWN0IGVxdWlwbWVudCBpdGVtcwogIHNlbGVjdGVkRXF1aXBJdGVtcy5mb3JFYWNoKG5hbWUgPT4gewogICAgaWYgKG5hbWUpIGl0ZW1zLnB1c2gobmFtZSk7CiAgfSk7CgogIC8vIEZhbGxiYWNrOiBlbnN1cmUgYmFja3BhY2sgYW5kIHdhdGVyc2tpbiBpZiBub3RoaW5nIHNlbGVjdGVkCiAgaWYgKCFpdGVtcy5zb21lKGkgPT4gL2JhY2twYWNrL2kudGVzdChpKSkpIGl0ZW1zLnB1c2goJ0JhY2twYWNrJyk7CiAgaWYgKCFpdGVtcy5zb21lKGkgPT4gL3dhdGVyc2tpbi9pLnRlc3QoaSkpKSBpdGVtcy5wdXNoKCdXYXRlcnNraW4nKTsKCiAgcmV0dXJuIGl0ZW1zOwp9CgpmdW5jdGlvbiB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCkgewogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmaW5hbC1pbnYtcHJldmlldycpLnRleHRDb250ZW50ID0gZ2V0RmluYWxJbnZlbnRvcnkoKS5qb2luKCcsICcpOwp9Cgphc3luYyBmdW5jdGlvbiBtYXJrUmVhZHkoKSB7CiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIGNhbGxlZCcpOwogIGNvbnNvbGUubG9nKCdbbWFya1JlYWR5XSBjaG9zZW5DbGFzczonLCBjaG9zZW5DbGFzcywgJ2Nob3NlblJhY2U6JywgY2hvc2VuUmFjZSk7CiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIHJvbGxlZFN0YXRzOicsIEpTT04uc3RyaW5naWZ5KHJvbGxlZFN0YXRzKSk7CiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIENMQVNTRVNbY2hvc2VuQ2xhc3NdOicsIEpTT04uc3RyaW5naWZ5KENMQVNTRVNbY2hvc2VuQ2xhc3NdKSk7CiAgLy8gR3VhcmQ6IG11c3QgaGF2ZSBhIG1vZHVsZSBsb2FkZWQgKGd1ZXN0cyBnZXQgaXQgZnJvbSByb29tLCBob3N0cyBzZWxlY3QgaXQpCiAgaWYgKCFtb2R1bGVUZXh0IHx8IG1vZHVsZVRleHQubGVuZ3RoIDwgMTApIHsKICAgIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlICYmICFpc0hvc3QpIHsKICAgICAgLy8gR3Vlc3QgLS0gdHJ5IHRvIGZldGNoIG1vZHVsZSBmcm9tIHJvb20gb25lIG1vcmUgdGltZQogICAgICB0cnkgewogICAgICAgIGNvbnN0IHJkID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2pvaW5fcm9vbScsIHttZXRob2Q6J1BPU1QnLAogICAgICAgICAgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lfSl9KS50aGVuKHI9PnIuanNvbigpKTsKICAgICAgICBpZiAocmQubW9kdWxlVGV4dCkgewogICAgICAgICAgbW9kdWxlVGV4dCA9IHJkLm1vZHVsZVRleHQ7CiAgICAgICAgICBsb2FkZWRNb2R1bGVEYXRhID0gcmQubW9kdWxlRGF0YSB8fCB7fTsKICAgICAgICAgIG1vZHVsZU5hbWUgPSByZC5tb2R1bGVOYW1lIHx8IG1vZHVsZU5hbWU7CiAgICAgICAgfQogICAgICB9IGNhdGNoKGUpIHt9CiAgICB9CiAgICBpZiAoIW1vZHVsZVRleHQgfHwgbW9kdWxlVGV4dC5sZW5ndGggPCAxMCkgewogICAgICBhbGVydCgnTm8gbW9kdWxlIGxvYWRlZC4gSWYgeW91IGFyZSBhIGd1ZXN0LCB0aGUgaG9zdCBtdXN0IHNlbGVjdCBhIG1vZHVsZSBmaXJzdC4nKTsKICAgICAgcmV0dXJuOwogICAgfQogIH0KICB0cnkgewogIGNvbnN0IG5hbWUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2hhci1uYW1lLWlucCcpLnZhbHVlLnRyaW0oKSB8fCBwbGF5ZXJOYW1lIHx8ICdBZHZlbnR1cmVyJzsKICBwbGF5ZXJOYW1lID0gbmFtZTsgLy8gY2hhcmFjdGVyIG5hbWUgSVMgdGhlIHBsYXllciBuYW1lCiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIG5hbWU6JywgbmFtZSk7CiAgY29uc3QgY2xzID0gQ0xBU1NFU1tjaG9zZW5DbGFzc107CiAgY29uc3QgaGRTaXplID0gY2xzLmhkIHx8IGNscy5ocCB8fCA2OwogIGNvbnN0IGhwID0gTWF0aC5tYXgoMSwgKE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSpoZFNpemUpKzEpICsgbW9kTihyb2xsZWRTdGF0cy5DT04pKTsKICBjb25zdCByYWNlRGF0YSA9IFJBQ0VTW2Nob3NlblJhY2VdOwogIHBjID0gewogICAgbmFtZSwgcmFjZTogY2hvc2VuUmFjZSwgY2xzOiBjaG9zZW5DbGFzcywgbGV2ZWw6IDEsCiAgICBocCwgbWF4aHA6IGhwLCBhYzogY2xzLmFjLAogICAgc3RhdHM6IHsuLi5yb2xsZWRTdGF0c30sCiAgICBpbnY6IGdldEZpbmFsSW52ZW50b3J5KCksCiAgICBnb2xkOiAoZnVuY3Rpb24oKXsgcmVjYWxjR29sZFNwZW50KCk7IHJldHVybiBNYXRoLm1heCgwLCBzdGFydGluZ0dvbGQgLSBnb2xkU3BlbnQpOyB9KSgpLAogICAgbG9jOiAnLi4uJywgbG9jdGFnOiAnJywgcXVlc3RzOiBbXSwKICAgIHNwZWNpYWxzOiByYWNlRGF0YT8uc3BlY2lhbHMgfHwgW10sCiAgICBzYXZlczogY2xzLnNhdmVzCiAgfTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJykudGV4dENvbnRlbnQgPSAnIFJlYWR5ISc7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JlYWR5LWJ0bicpLmRpc2FibGVkID0gdHJ1ZTsKICAgIC8vIEF1dG8tc2F2ZSBjaGFyYWN0ZXIgdG8gZGlzayBpbW1lZGlhdGVseSBvbiBjcmVhdGlvbgogICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3NhdmVfY2hhcmFjdGVyJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHBjKX0pOwoKICB9IGNhdGNoKGUpIHsgY29uc29sZS5lcnJvcignW21hcmtSZWFkeV0gRXJyb3I6JywgZSk7IGFsZXJ0KCdDaGFyYWN0ZXIgY3JlYXRpb24gZXJyb3I6ICcgKyBlLm1lc3NhZ2UpOyByZXR1cm47IH0KICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3BsYXllcl9yZWFkeScsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LCBib2R5OiBKU09OLnN0cmluZ2lmeSh7Y29kZTpyb29tQ29kZSwgcGxheWVyOnBsYXllck5hbWUsIHBjfSl9KTsKICAgIGlmIChpc0hvc3QpIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiZWdpbi1idG4nKS5zdHlsZS5kaXNwbGF5ID0gJ2lubGluZS1ibG9jayc7CiAgfSBlbHNlIHsKICAgIGJlZ2luQWR2ZW50dXJlKCk7CiAgfQp9CgpmdW5jdGlvbiBiZWdpbkFkdmVudHVyZSgpIHsKICBjb25zb2xlLmxvZygnW2JlZ2luQWR2ZW50dXJlXSBjYWxsZWQsIGlzTXVsdGlwbGF5ZXI6JywgaXNNdWx0aXBsYXllciwgJ3Jvb21Db2RlOicsIHJvb21Db2RlKTsKICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2dldF9yb29tJykudGhlbihyID0+IHIuanNvbigpKTsgLy8gbm9vcAogIH0KICBwYXJ0eVBDc1twbGF5ZXJOYW1lXSA9IHBjOwogIC8vIEZldGNoIGFsbCBwYXJ0eSBQQ3MgZnJvbSBzZXJ2ZXIgaWYgbXVsdGlwbGF5ZXIKICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgZmV0Y2goYC9yb29tX3N0YXRlP2NvZGU9JHtyb29tQ29kZX1gKS50aGVuKHI9PnIuanNvbigpKS50aGVuKHN0YXRlID0+IHsKICAgICAgcGFydHlQQ3MgPSBzdGF0ZS5wYXJ0eVBDcyB8fCB7W3BsYXllck5hbWVdOiBwY307CiAgICAgIE9iamVjdC5rZXlzKHBhcnR5UENzKS5mb3JFYWNoKChuLGkpID0+IHsgY29sb3JNYXBbbl0gPSBQTEFZRVJfQ09MT1JTW2klUExBWUVSX0NPTE9SUy5sZW5ndGhdOyB9KTsKICAgICAgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKICAgICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3VwZGF0ZV9yb29tJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOnJvb21Db2RlLCBzeXN0ZW1Qcm9tcHQsIGdhbWVBY3RpdmU6dHJ1ZSwgcGFydHlQQ3N9KX0pOwogICAgICBsYXVuY2hHYW1lKCk7CiAgICB9KTsKICB9IGVsc2UgewogICAgcGFydHlQQ3MgPSB7W3BsYXllck5hbWVdOiBwY307CiAgICBzeXN0ZW1Qcm9tcHQgPSBidWlsZFN5c3RlbVByb21wdCgpOwogICAgbGF1bmNoR2FtZSgpOwogIH0KfQoKZnVuY3Rpb24gaW5pdFJlc291cmNlc0Zyb21JbnZlbnRvcnkoKSB7CiAgY29uc3QgaW52ID0gKHBjLmludiB8fCBbXSkuam9pbignICcpLnRvTG93ZXJDYXNlKCk7CgogIC8vIExhbnRlcm4gLS0gT1NFIGl0ZW0gbmFtZSBpcyBqdXN0ICJMYW50ZXJuIgogIGhhc0xhbnRlcm4gPSAvbGFudGVybi9pLnRlc3QoaW52KTsKCiAgLy8gT2lsIGZsYXNrcyAtLSBPU0U6ICJPaWwgKDEgZmxhc2spIgogIGNvbnN0IG9pbE1hdGNoID0gaW52Lm1hdGNoKC9vaWxbXlsuXW5dKihbLl1kKykvaSk7CiAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSBvaWxNYXRjaCA/IHBhcnNlSW50KG9pbE1hdGNoWzFdKSA6IChoYXNMYW50ZXJuID8gMSA6IDApOwoKICAvLyBUb3JjaGVzIC0tIE9TRTogIlRvcmNoZXMgKDYpIiA9IHBhY2sgb2YgNiwgZWFjaCBidXJucyA2IHR1cm5zCiAgY29uc3QgdG9yY2hNYXRjaCA9IGludi5tYXRjaCgvdG9yY2hlcz9bLl1zKlsuXT8oWzAtOV0rKVsuXT8vaSkKICAgIHx8IGludi5tYXRjaCgvKFswLTldKylbLl1zKnRvcmNoZXM/L2kpOwogIGNvbnN0IHRvcmNoQ291bnQgPSB0b3JjaE1hdGNoID8gcGFyc2VJbnQodG9yY2hNYXRjaFsxXSkgOiAwOwoKICAvLyBSYXRpb25zIC0tIE9TRTogIlJhdGlvbnMgKGlyb24sIDcgZGF5cykiIG9yICJSYXRpb25zIChzdGFuZGFyZCwgNyBkYXlzKSIgPSA3IGRheSBzdXBwbHkKICBpZiAoL3JhdGlvbnM/L2kudGVzdChpbnYpKSB7CiAgICByYXRpb25zTGVmdCA9IDc7IC8vIEJvdGggT1NFIHJhdGlvbiB0eXBlcyBhcmUgNy1kYXkgc3VwcGxpZXMKICB9IGVsc2UgewogICAgcmF0aW9uc0xlZnQgPSAwOwogIH0KCiAgLy8gVG9yY2hlcyBpbiBpbnZlbnRvcnkgZG9lcyBOT1QgbWVhbiB0aGV5IGFyZSBsaXQgLSBwbGF5ZXIgbXVzdCB1c2Ugb25lCiAgdG9yY2hlc0NhcnJpZWQgPSB0b3JjaENvdW50OwogIHRvcmNoVHVybnNMZWZ0ID0gMDsKICB0b3JjaExpdCA9IGZhbHNlOwogIGxhbnRlcm5MaXQgPSBmYWxzZTsKICB0b3JjaEV2ZXJVc2VkID0gZmFsc2U7CiAgaXNDYXJyeWluZ0xpZ2h0ID0gdHJ1ZTsgICAgICAgLy8gYXNzdW1lIGRheWxpZ2h0L2FtYmllbnQgYXQgc3RhcnQKICAvLyBSZXNldCBhbGwgcGVuYWx0eSB0cmFja2VycwogIHJlc3REZWJ0ID0gMDsKICB0dXJuc1dpdGhvdXRSZXN0ID0gMDsKICBmYXRpZ3VlUGVuYWx0eSA9IDA7CiAgZGF5c1dpdGhvdXRGb29kID0gMDsKICBzdGFydmF0aW9uUGVuYWx0eSA9IDA7CiAgZm9yY2VkTWFyY2hBY3RpdmUgPSBmYWxzZTsKICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOwoKICBjb25zb2xlLmxvZygnW1Jlc291cmNlc10gSW5pdCAtLSB0b3JjaGVzOicsIHRvcmNoQ291bnQsICcoJywgdG9yY2hUdXJuc0xlZnQsICd0dXJucyknLAogICAgJ3wgbGFudGVybjonLCBoYXNMYW50ZXJuLCAnfCBvaWw6JywgbGFudGVybk9pbEZsYXNrc0xlZnQsCiAgICAnfCByYXRpb25zOicsIHJhdGlvbnNMZWZ0KTsKfQoKZnVuY3Rpb24gYWR2YW5jZUR1bmdlb25UdXJuKHR1cm5zKSB7CiAgdHVybnMgPSB0dXJucyB8fCAxOwogIGR1bmdlb25UdXJucyArPSB0dXJuczsKICByZXN0RGVidCArPSB0dXJuczsgICAgICAgICAgICAgLy8gbGVnYWN5IGNvbXBhdAogIHR1cm5zV2l0aG91dFJlc3QgKz0gdHVybnM7CiAgd2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyICs9IHR1cm5zOwoKICAvLyBPU0UgZHVuZ2VvbiByZXN0IHJ1bGU6IGV2ZXJ5IDYgdHVybnMgZXhwbG9yZWQgd2l0aG91dCBhIDEtdHVybiByZXN0CiAgLy8gaW1wb3NlcyBhIGN1bXVsYXRpdmUgLTEgdG8gYXR0YWNrIHJvbGxzCiAgLy8gKGNvbW1vbiBpbnRlcnByZXRhdGlvbiBvZiB0aGUgcmVzdC1ldmVyeS02LXR1cm5zIHJlcXVpcmVtZW50KQogIC8vIE9ubHkgYXBwbHkgZmF0aWd1ZSBwZW5hbHR5IGluIGR1bmdlb24gKE9TRSBydWxlIG9ubHkgYXBwbGllcyB1bmRlcmdyb3VuZCkKICBmYXRpZ3VlUGVuYWx0eSA9IGlzSW5EdW5nZW9uKCkgPyBNYXRoLmZsb29yKHR1cm5zV2l0aG91dFJlc3QgLyA2KSA6IDA7CgogIC8vIEJ1cm4gdG9yY2ggKE9TRTogdG9yY2ggYnVybnMgY29udGludW91c2x5LCA2IHR1cm5zIGVhY2gpCiAgaWYgKHRvcmNoVHVybnNMZWZ0ID4gMCkgewogICAgdG9yY2hUdXJuc0xlZnQgPSBNYXRoLm1heCgwLCB0b3JjaFR1cm5zTGVmdCAtIHR1cm5zKTsKICAgIGlmICh0b3JjaFR1cm5zTGVmdCA9PT0gMCkgewogICAgICAvLyBBdXRvLXN3aXRjaCB0byBsYW50ZXJuIGlmIGF2YWlsYWJsZQogICAgICBpZiAoaGFzTGFudGVybiAmJiBsYW50ZXJuT2lsRmxhc2tzTGVmdCA+IDApIHsKICAgICAgICBpc0NhcnJ5aW5nTGlnaHQgPSB0cnVlOyAvLyBsYW50ZXJuIHRha2VzIG92ZXIKICAgICAgfSBlbHNlIHsKICAgICAgICBpc0NhcnJ5aW5nTGlnaHQgPSBmYWxzZTsKICAgICAgfQogICAgfQogIH0gZWxzZSBpZiAoaGFzTGFudGVybiAmJiBsYW50ZXJuT2lsRmxhc2tzTGVmdCA+IDApIHsKICAgIC8vIE9TRTogbGFudGVybiBidXJucyAxIGZsYXNrIHBlciAyNCB0dXJucyAoNCBob3VycykKICAgIC8vIFRyYWNrIGJ5IGFic29sdXRlIHR1cm4gY291bnQKICAgIGNvbnN0IGZsYXNrc0NvbnN1bWVkID0gTWF0aC5mbG9vcihkdW5nZW9uVHVybnMgLyAyNCk7CiAgICBjb25zdCBuZXdGbGFza3NMZWZ0ID0gTWF0aC5tYXgoMCwgbGFudGVybk9pbEZsYXNrc0xlZnQgLSBmbGFza3NDb25zdW1lZCk7CiAgICBpZiAobmV3Rmxhc2tzTGVmdCA8IGxhbnRlcm5PaWxGbGFza3NMZWZ0KSB7CiAgICAgIGxhbnRlcm5PaWxGbGFza3NMZWZ0ID0gbmV3Rmxhc2tzTGVmdDsKICAgICAgaWYgKGxhbnRlcm5PaWxGbGFza3NMZWZ0ID09PSAwKSBpc0NhcnJ5aW5nTGlnaHQgPSBmYWxzZTsKICAgIH0KICB9CgogIC8vIE9TRSB3YW5kZXJpbmcgbW9uc3RlciBjaGVjazogZXZlcnkgMiB0dXJucywgcm9sbCAxZDYKICAvLyAxID0gd2FuZGVyaW5nIG1vbnN0ZXIgZW5jb3VudGVyCiAgaWYgKHdhbmRlcmluZ01vbnN0ZXJUdXJuQ291bnRlciA+PSAyKSB7CiAgICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOwogICAgY29uc3Qgcm9sbCA9IE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSAqIDYpICsgMTsKICAgIGlmIChyb2xsID09PSAxKSB7CiAgICAgIHdhbmRlcmluZ01vbnN0ZXJDaGVja0R1ZSA9IHRydWU7CiAgICAgIGNvbnNvbGUubG9nKCdbV2FuZGVyaW5nXSBFbmNvdW50ZXIgdHJpZ2dlcmVkIScpOwogICAgfQogIH0KfQoKZnVuY3Rpb24gaGFuZGxlRHVuZ2VvblJlc3QoKSB7CiAgLy8gMS10dXJuIHJlc3QgcmVzZXRzIHRoZSBmYXRpZ3VlIGNsb2NrCiAgdHVybnNXaXRob3V0UmVzdCA9IDA7CiAgZmF0aWd1ZVBlbmFsdHkgPSAwOwogIGFkdmFuY2VEdW5nZW9uVHVybigxKTsgLy8gcmVzdCBpdHNlbGYgdGFrZXMgMSB0dXJuICh3YW5kZXJpbmcgbW9uc3RlciBjaGVjayBhcHBsaWVzKQogIGlmIChpc0luRHVuZ2VvbigpKSBhZGRFbnRyeVJhdygnUmVzdCB0YWtlbiAtLSAxIHR1cm4uICgnICsgdHVybnNXaXRob3V0UmVzdCArICcvNiB0dXJucyByZXNldCknLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgpmdW5jdGlvbiBoYW5kbGVGdWxsUmVzdCgpIHsKICAvLyBDb25zdW1lIDEgcmF0aW9uICgxIHBlciBkYXkgcmVxdWlyZWQpCiAgaWYgKHJhdGlvbnNMZWZ0ID4gMCkgewogICAgcmF0aW9uc0xlZnQgPSBNYXRoLm1heCgwLCByYXRpb25zTGVmdCAtIDEpOwogICAgZGF5c1dpdGhvdXRGb29kID0gMDsgICAgICAgIC8vIGF0ZSB0b2RheSAtLSByZXNldCBzdGFydmF0aW9uIGNvdW50ZXIKICAgIHN0YXJ2YXRpb25QZW5hbHR5ID0gMDsKICB9IGVsc2UgewogICAgZGF5c1dpdGhvdXRGb29kKys7CiAgICAvLyBIb3VzZSBydWxlOiBhZnRlciAzIGRheXMgd2l0aG91dCBmb29kLCAtMSB0byBhdHRhY2tzIGFuZCBzYXZlcyBwZXIgZGF5CiAgICBzdGFydmF0aW9uUGVuYWx0eSA9IE1hdGgubWF4KDAsIGRheXNXaXRob3V0Rm9vZCAtIDMpOwogICAgaWYgKHN0YXJ2YXRpb25QZW5hbHR5ID4gMCkgewogICAgICBhZGRFbnRyeVJhdygnU3RhcnZhdGlvbjogLScgKyBzdGFydmF0aW9uUGVuYWx0eSArICcgdG8gYXR0YWNrIHJvbGxzIGFuZCBzYXZpbmcgdGhyb3dzLiAoRGF5ICcgKyBkYXlzV2l0aG91dEZvb2QgKyAnIHdpdGhvdXQgZm9vZCknLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgfQogIH0KICAvLyBPU0U6IHJlY292ZXIgMSBIUCBwZXIgbGV2ZWwgcGVyIGZ1bGwgbmlnaHQncyByZXN0CiAgY29uc3QgaHBHYWluZWQgPSBwYy5sZXZlbCB8fCAxOwogIHBjLmhwID0gTWF0aC5taW4ocGMubWF4aHAsIHBjLmhwICsgaHBHYWluZWQpOwogIC8vIENsZWFyIGR1bmdlb24gZmF0aWd1ZQogIHR1cm5zV2l0aG91dFJlc3QgPSAwOwogIGZhdGlndWVQZW5hbHR5ID0gMDsKICByZXN0RGVidCA9IDA7CiAgLy8gVG9yY2hlcy9sYW50ZXJuIGJ1cm4gZHVyaW5nIHJlc3QgKDggaG91cnMgPSA0OCB0dXJucykKICBkdW5nZW9uVHVybnMgKz0gNDg7CiAgY29uc29sZS5sb2coJ1tSZXN0XSBGdWxsIHJlc3QuIEhQKycgKyBocEdhaW5lZCArICcgLT4gJyArIHBjLmhwICsgJy4gUmF0aW9ucyBsZWZ0OicgKyByYXRpb25zTGVmdCArICcuIFN0YXJ2YXRpb24gcGVuYWx0eTonICsgc3RhcnZhdGlvblBlbmFsdHkpOwp9CgpmdW5jdGlvbiBidWlsZFJlc291cmNlQmxvY2soKSB7CiAgY29uc3Qgd2FybmluZ3MgPSBbXTsKICBjb25zdCBzdGF0dXMgPSBbXTsKCiAgLy8gV2FuZGVyaW5nIG1vbnN0ZXIKICBpZiAod2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlKSB7CiAgICB3YXJuaW5ncy5wdXNoKCdXQU5ERVJJTkcgTU9OU1RFUiBDSEVDSyBUUklHR0VSRUQgW2Q2PTFdIC0tIGludHJvZHVjZSBhbiBhcHByb3ByaWF0ZSB3YW5kZXJpbmcgbW9uc3RlciBlbmNvdW50ZXIgZnJvbSB0aGUgbW9kdWxlIG5hdHVyYWxseSBpbnRvIHRoZSBjdXJyZW50IHNjZW5lLicpOwogICAgd2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlID0gZmFsc2U7IC8vIGNsZWFyIGFmdGVyIGluamVjdGluZwogIH0KCiAgLy8gTGlnaHQKICBpZiAoIWlzQ2FycnlpbmdMaWdodCkgewogICAgd2FybmluZ3MucHVzaCgnREFSS05FU1MgLS0gcGFydHkgaGFzIG5vIGxpZ2h0IHNvdXJjZS4gSW4gT1NFOiBtb25zdGVycyB0aGF0IGNhbiBzZWUgaW4gZGFyayBoYXZlIGZ1bGwgYWR2YW50YWdlOyBwYXJ0eSBzdWZmZXJzIC00IHRvIGF0dGFjayByb2xsczsgc2VhcmNoaW5nIGlzIGltcG9zc2libGU7IHN1cnByaXNlIG9uIDEtNC9kNi4nKTsKICB9IGVsc2UgaWYgKHRvcmNoVHVybnNMZWZ0ID4gMCAmJiB0b3JjaFR1cm5zTGVmdCA8PSAyKSB7CiAgICB3YXJuaW5ncy5wdXNoKCdUT1JDSCBORUFSTFkgT1VUIC0tICcgKyB0b3JjaFR1cm5zTGVmdCArICcgdHVybihzKSByZW1haW5pbmcuIE1lbnRpb24gdGhpcyBpbiBuYXJyYXRpb24uJyk7CiAgfSBlbHNlIGlmICh0b3JjaFR1cm5zTGVmdCA9PT0gMCAmJiB0b3JjaFR1cm5zTGVmdCA8PSAwICYmIGhhc0xhbnRlcm4pIHsKICAgIHN0YXR1cy5wdXNoKCdMaWdodDogbGFudGVybiAoJyArIGxhbnRlcm5PaWxGbGFza3NMZWZ0ICsgJyBmbGFzayhzKSByZW1haW5pbmcsIH4nICsgKGxhbnRlcm5PaWxGbGFza3NMZWZ0ICogMjQpICsgJyB0dXJucyknKTsKICB9IGVsc2UgewogICAgc3RhdHVzLnB1c2goJ0xpZ2h0OiB0b3JjaCAoJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJucyByZW1haW5pbmcpJyk7CiAgfQoKICAvLyBIdW5nZXIgLS0gaG91c2UgcnVsZTogLTEgdG8gYXR0YWNrIHJvbGxzIGFuZCBzYXZlcyBwZXIgZGF5IGFmdGVyIGRheSAzIHdpdGhvdXQgZm9vZAogIGlmIChzdGFydmF0aW9uUGVuYWx0eSA+IDApIHsKICAgIHdhcm5pbmdzLnB1c2goJ1NUQVJWQVRJT04gUEVOQUxUWSBBQ1RJVkU6IC0nICsgc3RhcnZhdGlvblBlbmFsdHkgKyAnIHRvIEFMTCBhdHRhY2sgcm9sbHMgYW5kIHNhdmluZyB0aHJvd3MgKGRheSAnICsgZGF5c1dpdGhvdXRGb29kICsgJyB3aXRob3V0IGZvb2QpLiBBcHBseSB0aGlzIHRvIGV2ZXJ5IHJvbGwuIENoYXJhY3RlciBuZWVkcyBmb29kIHVyZ2VudGx5LicpOwogIH0gZWxzZSBpZiAoZGF5c1dpdGhvdXRGb29kID4gMCkgewogICAgd2FybmluZ3MucHVzaCgnSFVOR1JZOiBEYXkgJyArIGRheXNXaXRob3V0Rm9vZCArICcgd2l0aG91dCBmb29kLiBQZW5hbHR5ICgtMS9kYXkpIGJlZ2lucyBhZnRlciBkYXkgMy4gQ2hhcmFjdGVyIHNob3VsZCBiZSB2aXNpYmx5IHdlYWtlbmluZy4nKTsKICB9IGVsc2UgaWYgKHJhdGlvbnNMZWZ0ID09PSAwKSB7CiAgICBzdGF0dXMucHVzaCgnTm8gcmF0aW9ucyAobm90IHlldCBodW5ncnkgLS0gcGVuYWx0eSBzdGFydHMgYWZ0ZXIgMyBkYXlzKScpOwogIH0gZWxzZSBpZiAocmF0aW9uc0xlZnQgPT09IDEpIHsKICAgIHdhcm5pbmdzLnB1c2goJ0xBU1QgUkFUSU9OIC0tIG1lbnRpb24gdGhpcyBpbiBuYXJyYXRpb24uJyk7CiAgfSBlbHNlIHsKICAgIHN0YXR1cy5wdXNoKCdSYXRpb25zOiAnICsgcmF0aW9uc0xlZnQgKyAnIHJlbWFpbmluZycpOwogIH0KCiAgLy8gT1NFIGR1bmdlb24gcmVzdCBydWxlIC0tIG9ubHkgYXBwbGllcyB1bmRlcmdyb3VuZAogIGlmIChpc0luRHVuZ2VvbigpKSB7CiAgICBpZiAodHVybnNXaXRob3V0UmVzdCA+PSA2KSB7CiAgICAgIHdhcm5pbmdzLnB1c2goJ0RVTkdFT04gUkVTVCBPVkVSRFVFOiAnICsgdHVybnNXaXRob3V0UmVzdCArICcgdHVybnMgd2l0aG91dCByZXN0LiBPU0UgcnVsZTogcGFydHkgbXVzdCByZXN0IDEgdHVybiBwZXIgNiBleHBsb3JlZCBvciBzdWZmZXIgd2FuZGVyaW5nIG1vbnN0ZXIgY2hlY2sgcGVuYWx0eS4gUmVtaW5kIHBhcnR5IHRvIHJlc3QuJyk7CiAgICB9IGVsc2UgaWYgKHR1cm5zV2l0aG91dFJlc3QgPj0gNCkgewogICAgICBzdGF0dXMucHVzaCgnRHVuZ2VvbiByZXN0OiAnICsgdHVybnNXaXRob3V0UmVzdCArICcvNiB0dXJucyAocmVzdCAxIHR1cm4gc29vbiB0byBhdm9pZCB3YW5kZXJpbmcgbW9uc3RlciBwZW5hbHR5KScpOwogICAgfQogIH0KCiAgLy8gVHVybiBjb3VudAogIGNvbnN0IGhvdXJzID0gTWF0aC5mbG9vcihkdW5nZW9uVHVybnMgLyA2KTsKICBjb25zdCBtaW5zID0gKGR1bmdlb25UdXJucyAlIDYpICogMTA7CiAgc3RhdHVzLnB1c2goJ1R1cm4gJyArIGR1bmdlb25UdXJucyArICcgKCcgKyBob3VycyArICdoICcgKyBtaW5zICsgJ20gaW4gZHVuZ2VvbiknKTsKCiAgY29uc3QgbGluZXMgPSBbXTsKICBpZiAod2FybmluZ3MubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCdSRVNPVVJDRSBXQVJOSU5HUyAoaW5jb3Jwb3JhdGUgbmF0dXJhbGx5IGludG8gbmFycmF0aW9uKTonKTsKICAgIHdhcm5pbmdzLmZvckVhY2godyA9PiBsaW5lcy5wdXNoKCcgICcgKyB3KSk7CiAgfQogIGlmIChzdGF0dXMubGVuZ3RoKSBsaW5lcy5wdXNoKCdSZXNvdXJjZXM6ICcgKyBzdGF0dXMuam9pbignIHwgJykpOwogIHJldHVybiBsaW5lcy5sZW5ndGggPyBsaW5lcy5qb2luKCdbLl1uJykgOiAnJzsKfQoKYXN5bmMgZnVuY3Rpb24gZ2VuZXJhdGVHTUJyaWVmaW5nKCkgewogIGlmICghdXNlT2xsYW1hKSByZXR1cm47IC8vIENsYXVkZSBoYW5kbGVzIHRoaXMgbmF0aXZlbHkKCiAgLy8gSWYgd2UgaGF2ZSBhIC5kbmRtb2QgZmlsZSBsb2FkZWQsIGJ1aWxkIHRoZSBicmllZmluZyBkaXJlY3RseSBmcm9tIGl0cwogIC8vIHN0cnVjdHVyZWQgZGF0YSAtLSBubyBBSSBjYWxsIG5lZWRlZCwgaW5zdGFudCBhbmQgMTAwJSBhY2N1cmF0ZS4KICBpZiAobG9hZGVkTW9kdWxlRGF0YSAmJiBsb2FkZWRNb2R1bGVEYXRhLm5wY3MgJiYgbG9hZGVkTW9kdWxlRGF0YS5ucGNzLmxlbmd0aCkgewogICAgY29uc29sZS5sb2coJ1tCcmllZmluZ10gQnVpbGRpbmcgZnJvbSAuZG5kbW9kIHN0cnVjdHVyZWQgZGF0YSAtLSBza2lwcGluZyBBSSBjYWxsJyk7CiAgICBidWlsZEJyaWVmaW5nRnJvbURuZG1vZChsb2FkZWRNb2R1bGVEYXRhKTsKICAgIHJldHVybjsKICB9CgogIGlmICghbW9kdWxlVGV4dCB8fCBtb2R1bGVUZXh0Lmxlbmd0aCA8IDEwMCkgcmV0dXJuOwoKICBhZGRFbnRyeVJhdygnUHJlcGFyaW5nIEdNIGJyaWVmaW5nIC0tIHRoaXMgdGFrZXMgYWJvdXQgMzAgc2Vjb25kcy4uLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CgogIGNvbnN0IGJyaWVmaW5nUHJvbXB0ID0gYFlvdSBhcmUgcHJlcGFyaW5nIHRvIHJ1biBhIHRhYmxldG9wIFJQRyBtb2R1bGUgYXMgR2FtZSBNYXN0ZXIuIFJlYWQgdGhlIG1vZHVsZSBiZWxvdyBhbmQgcHJvZHVjZSBhIHN0cnVjdHVyZWQgR00gYnJpZWZpbmcgaW4gSlNPTiBmb3JtYXQgT05MWS4gTm8gbWFya2Rvd24sIG5vIHByZWFtYmxlIC0tIHB1cmUgSlNPTi4KCk1PRFVMRToKJHttb2R1bGVUZXh0LnN1YnN0cmluZygwLCAxNjAwMCl9CgpQcm9kdWNlIHRoaXMgZXhhY3QgSlNPTiBzdHJ1Y3R1cmU6CnsKICAia2V5X2ZhY3RzIjogWwogICAgIlRoZSBtb3N0IGltcG9ydGFudCBmYWN0IHRoZSBHTSBtdXN0IG5ldmVyIGZvcmdldCIsCiAgICAiU2Vjb25kIG1vc3QgaW1wb3J0YW50IGZhY3QiLAogICAgIlRoaXJkIiwKICAgICJGb3VydGgiLAogICAgIkZpZnRoIiwKICAgICJTaXh0aCIsCiAgICAiU2V2ZW50aCIsCiAgICAiRWlnaHRoIiwKICAgICJOaW50aCIsCiAgICAiVGVudGgiCiAgXSwKICAiY29yZV90ZW5zaW9uIjogIk9uZSBzZW50ZW5jZTogdGhlIGNlbnRyYWwgZHJhbWF0aWMgY29uZmxpY3Qgb2YgdGhpcyBhZHZlbnR1cmUiLAogICJ2aWN0b3J5X2NvbmRpdGlvbiI6ICJPbmUgc2VudGVuY2U6IGhvdyB0aGUgYWR2ZW50dXJlIGNhbiBiZSB3b24iLAogICJtYWluX3ZpbGxhaW5fb3JfdGhyZWF0IjogIk5hbWUgYW5kIG9uZS1zZW50ZW5jZSBkZXNjcmlwdGlvbiBvZiB0aGUgcHJpbWFyeSBhbnRhZ29uaXN0IG9yIHRocmVhdCIsCiAgIm5wY3MiOiBbCiAgICB7CiAgICAgICJuYW1lIjogIk5QQyBuYW1lIGV4YWN0bHkgYXMgaW4gbW9kdWxlIiwKICAgICAgInJvbGUiOiAiVGhlaXIgcm9sZSBpbiBvbmUgcGhyYXNlIiwKICAgICAgInBlcnNvbmFsaXR5IjogIjItMyB3b3JkcyBkZXNjcmliaW5nIGhvdyB0aGV5IHNwZWFrIGFuZCBhY3QiLAogICAgICAia25vd3MiOiBbCiAgICAgICAgIlNwZWNpZmljIGZhY3QgdGhpcyBOUEMgZ2VudWluZWx5IGtub3dzIGFuZCBjYW4gc2hhcmUgZnJlZWx5IiwKICAgICAgICAiQW5vdGhlciBmYWN0IHRoZXkgY2FuIHNoYXJlIiwKICAgICAgICAiQSB0aGlyZCBpZiByZWxldmFudCIKICAgICAgXSwKICAgICAgIndpbGxfc2hhcmVfaWYiOiAiQ29uZGl0aW9uIHVuZGVyIHdoaWNoIHRoZXkgc2hhcmUgc2Vuc2l0aXZlIGluZm9ybWF0aW9uIChlLmcuICdpZiBwYXJ0eSBlYXJucyB0cnVzdCcsICduZXZlcicsICdpZiBicmliZWQnLCAnaWYgZnJpZ2h0ZW5lZCcpIiwKICAgICAgIndvbnRfc2hhcmUiOiBbCiAgICAgICAgIlNvbWV0aGluZyB0aGV5IGtub3cgYnV0IGFjdGl2ZWx5IGhpZGUiLAogICAgICAgICJBbm90aGVyIHNlY3JldCB0aGV5IHByb3RlY3QiCiAgICAgIF0sCiAgICAgICJjYW5ub3Rfa25vdyI6IFsKICAgICAgICAiSW5mb3JtYXRpb24gdGhpcyBOUEMgaGFzIE5PIFdBWSBvZiBrbm93aW5nIC0tIG11c3QgcmVmdXNlIHdpdGggJ0kgZG9uJ3Qga25vdyciLAogICAgICAgICJBbm90aGVyIHRoaW5nIG91dHNpZGUgdGhlaXIga25vd2xlZGdlIgogICAgICBdLAogICAgICAiZGVmbGVjdGlvbl9waHJhc2UiOiAiRXhhY3Qgd29yZHMgdGhpcyBOUEMgdXNlcyB3aGVuIGFza2VkIHNvbWV0aGluZyB0aGV5IHdvbid0IG9yIGNhbid0IGFuc3dlci4gTWFrZSBpdCBpbi1jaGFyYWN0ZXIuIiwKICAgICAgImtub3dsZWRnZV9saW1pdCI6ICJPbmUgc2VudGVuY2UgZGVzY3JpYmluZyB0aGUgYWJzb2x1dGUgYm91bmRhcnkgb2YgdGhlaXIga25vd2xlZGdlIgogICAgfQogIF0sCiAgInNlY3JldF9pbmZvcm1hdGlvbiI6IFsKICAgICJQbG90IHNlY3JldCB0aGUgcGxheWVycyBzaG91bGQgTk9UIGtub3cgeWV0IiwKICAgICJBbm90aGVyIHNlY3JldCB0byBiZSByZXZlYWxlZCBsYXRlciIKICBdLAogICJpbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cyI6IFsKICAgICJTb21ldGhpbmcgdGhhdCBpcyB0cnVlIGluIHRoZSBtb2R1bGUgYnV0IE5PIE5QQyBrbm93cyAtLSBwbGF5ZXJzIGNhbiBvbmx5IGZpbmQgaXQgYnkgZXhwbG9yYXRpb24iLAogICAgIkFub3RoZXIgc3VjaCBmYWN0IgogIF0KfQoKQmUgc3BlY2lmaWMuIFVzZSBleGFjdCBuYW1lcyBmcm9tIHRoZSBtb2R1bGUuIEV2ZXJ5IE5QQyBpbiB0aGUgbW9kdWxlIHNob3VsZCBhcHBlYXIuIFRoZSBjYW5ub3Rfa25vdyBsaXN0IGlzIGNyaXRpY2FsIC0tIGluY2x1ZGUgYXQgbGVhc3QgMiBpdGVtcyBwZXIgTlBDLmA7CgogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FpJywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgICAgYXBpX2tleTogYXBpS2V5LAogICAgICAgIHN5c3RlbTogJ1lvdSBhcmUgYSBwcmVjaXNlIEpTT04gZ2VuZXJhdG9yLiBPdXRwdXQgb25seSB2YWxpZCBKU09OLiBObyBtYXJrZG93biBmZW5jZXMuIE5vIGV4cGxhbmF0aW9uLicsCiAgICAgICAgbWVzc2FnZXM6IFt7cm9sZTogJ3VzZXInLCBjb250ZW50OiBicmllZmluZ1Byb21wdH1dCiAgICAgIH0pCiAgICB9KTsKCiAgICBpZiAoIXJlc3Aub2spIHsKICAgICAgY29uc29sZS53YXJuKCdbQnJpZWZpbmddIEFQSSBlcnJvcjonLCByZXNwLnN0YXR1cyk7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzcC5qc29uKCk7CiAgICBpZiAoZGF0YS5lcnJvciB8fCAhZGF0YS5jb250ZW50KSB7CiAgICAgIGNvbnNvbGUud2FybignW0JyaWVmaW5nXSBObyBjb250ZW50OicsIGRhdGEuZXJyb3IpOwogICAgICByZXR1cm47CiAgICB9CgogICAgLy8gUGFyc2UgSlNPTiAtLSBzdHJpcCBhbnkgbWFya2Rvd24gZmVuY2VzIENsYXVkZSBtaWdodCBhZGQKICAgIGxldCByYXcgPSBkYXRhLmNvbnRlbnQudHJpbSgpOwogICAgLy8gUmVtb3ZlIG9wZW5pbmcgZmVuY2UgbGluZSAoZS5nLiBgYGBqc29uKQogICAgaWYgKHJhdy5zdGFydHNXaXRoKCdgJykpIHsKICAgICAgY29uc3QgZmlyc3ROZXdsaW5lID0gcmF3LmluZGV4T2YoJ1suXW4nKTsKICAgICAgaWYgKGZpcnN0TmV3bGluZSA+IDApIHJhdyA9IHJhdy5zdWJzdHJpbmcoZmlyc3ROZXdsaW5lICsgMSk7CiAgICB9CiAgICAvLyBSZW1vdmUgY2xvc2luZyBmZW5jZQogICAgaWYgKHJhdy50cmltRW5kKCkuZW5kc1dpdGgoJ2AnKSkgewogICAgICBjb25zdCBsYXN0RmVuY2UgPSByYXcubGFzdEluZGV4T2YoJ1suXW5gYGAnKTsKICAgICAgaWYgKGxhc3RGZW5jZSA+IDApIHJhdyA9IHJhdy5zdWJzdHJpbmcoMCwgbGFzdEZlbmNlKTsKICAgIH0KICAgIGNvbnN0IHN0YXJ0ID0gcmF3LmluZGV4T2YoJ3snKTsKICAgIGNvbnN0IGVuZCA9IHJhdy5sYXN0SW5kZXhPZignfScpICsgMTsKICAgIGlmIChzdGFydCA8IDAgfHwgZW5kIDw9IHN0YXJ0KSB7CiAgICAgIGNvbnNvbGUud2FybignW0JyaWVmaW5nXSBDb3VsZCBub3QgZmluZCBKU09OIGluIHJlc3BvbnNlJyk7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBjb25zdCBicmllZmluZyA9IEpTT04ucGFyc2UocmF3LnN1YnN0cmluZyhzdGFydCwgZW5kKSk7CgogICAgLy8gU3RvcmUga2V5IGZhY3RzIGFzIHBpbm5lZCBmYWN0cwogICAgaWYgKGJyaWVmaW5nLmtleV9mYWN0cykgewogICAgICBicmllZmluZy5rZXlfZmFjdHMuZm9yRWFjaChmID0+IHsKICAgICAgICBpZiAoIXBpbm5lZEZhY3RzLmluY2x1ZGVzKGYpKSBwaW5uZWRGYWN0cy5wdXNoKGYpOwogICAgICB9KTsKICAgIH0KCiAgICAvLyBCdWlsZCBOUEMga25vd2xlZGdlIG1hcCBmb3IgaW5qZWN0aW9uCiAgICBucGNLbm93bGVkZ2VNYXAgPSB7fTsKICAgIGlmIChicmllZmluZy5ucGNzKSB7CiAgICAgIGJyaWVmaW5nLm5wY3MuZm9yRWFjaChucGMgPT4gewogICAgICAgIG5wY0tub3dsZWRnZU1hcFtucGMubmFtZV0gPSB7CiAgICAgICAgICByb2xlOiBucGMucm9sZSB8fCAnJywKICAgICAgICAgIHBlcnNvbmFsaXR5OiBucGMucGVyc29uYWxpdHkgfHwgJycsCiAgICAgICAgICBrbm93czogbnBjLmtub3dzIHx8IFtdLAogICAgICAgICAgd2lsbF9zaGFyZV9pZjogbnBjLndpbGxfc2hhcmVfaWYgfHwgJ2ZyZWVseScsCiAgICAgICAgICB3b250X3NoYXJlOiBucGMud29udF9zaGFyZSB8fCBbXSwKICAgICAgICAgIGNhbm5vdF9rbm93OiBucGMuY2Fubm90X2tub3cgfHwgW10sCiAgICAgICAgICBkZWZsZWN0aW9uOiBucGMuZGVmbGVjdGlvbl9waHJhc2UgfHwgIkknbSBzb3JyeSwgSSBkb24ndCBrbm93IGFueXRoaW5nIG1vcmUgYWJvdXQgdGhhdC4iLAogICAgICAgICAgbGltaXQ6IG5wYy5rbm93bGVkZ2VfbGltaXQgfHwgJycKICAgICAgICB9OwogICAgICB9KTsKICAgIH0KCiAgICAvLyBCdWlsZCB0aGUgR00gYnJpZWZpbmcgdGV4dAogICAgY29uc3QgbGluZXMgPSBbXTsKICAgIGxpbmVzLnB1c2goJyBHTSBCUklFRklORyAocHJlLWFuYWx5c2VkIG1vZHVsZSBjaGVhdCBzaGVldCkgJyk7CiAgICBsaW5lcy5wdXNoKCdDb3JlIHRlbnNpb246ICcgKyAoYnJpZWZpbmcuY29yZV90ZW5zaW9uIHx8ICcnKSk7CiAgICBsaW5lcy5wdXNoKCdWaWN0b3J5OiAnICsgKGJyaWVmaW5nLnZpY3RvcnlfY29uZGl0aW9uIHx8ICcnKSk7CiAgICBsaW5lcy5wdXNoKCdQcmltYXJ5IHRocmVhdDogJyArIChicmllZmluZy5tYWluX3ZpbGxhaW5fb3JfdGhyZWF0IHx8ICcnKSk7CiAgICBsaW5lcy5wdXNoKCcnKTsKICAgIGxpbmVzLnB1c2goJ0tFWSBGQUNUUyAobmV2ZXIgZm9yZ2V0IG9yIGNvbnRyYWRpY3QgdGhlc2UpOicpOwogICAgKGJyaWVmaW5nLmtleV9mYWN0cyB8fCBbXSkuZm9yRWFjaCgoZixpKSA9PiBsaW5lcy5wdXNoKChpKzEpICsgJy4gJyArIGYpKTsKCiAgICBpZiAoYnJpZWZpbmcuc2VjcmV0X2luZm9ybWF0aW9uICYmIGJyaWVmaW5nLnNlY3JldF9pbmZvcm1hdGlvbi5sZW5ndGgpIHsKICAgICAgbGluZXMucHVzaCgnJyk7CiAgICAgIGxpbmVzLnB1c2goJ1NFQ1JFVFMgKHBsYXllcnMgbXVzdCBOT1Qga25vdyB0aGVzZSB5ZXQgLS0gbmV2ZXIgcmV2ZWFsIHRocm91Z2ggTlBDcyk6Jyk7CiAgICAgIGJyaWVmaW5nLnNlY3JldF9pbmZvcm1hdGlvbi5mb3JFYWNoKHMgPT4gbGluZXMucHVzaCgnICBTRUNSRVQ6ICcgKyBzKSk7CiAgICB9CgogICAgaWYgKGJyaWVmaW5nLmluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzICYmIGJyaWVmaW5nLmluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzLmxlbmd0aCkgewogICAgICBsaW5lcy5wdXNoKCcnKTsKICAgICAgbGluZXMucHVzaCgnRElTQ09WRVJBQkxFIE9OTFkgQlkgRVhQTE9SQVRJT04gKG5vIE5QQyBjYW4gdGVsbCB0aGVtIHRoaXMpOicpOwogICAgICBicmllZmluZy5pbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cy5mb3JFYWNoKHMgPT4gbGluZXMucHVzaCgnICBFWFBMT1JFIE9OTFk6ICcgKyBzKSk7CiAgICB9CgogICAgbGluZXMucHVzaCgnJyk7CiAgICBsaW5lcy5wdXNoKCcgTlBDIEtOT1dMRURHRSBNQVAgKGhhcmQgbGltaXRzIC0tIGVuZm9yY2Ugc3RyaWN0bHkpICcpOwogICAgbGluZXMucHVzaCgnQ1JJVElDQUwgUlVMRTogV2hlbiBhbiBOUEMgcmVhY2hlcyB0aGUgbGltaXQgb2YgdGhlaXIga25vd2xlZGdlLCB0aGV5IHNheSBzbycpOwogICAgbGluZXMucHVzaCgnaW4gY2hhcmFjdGVyLiBUaGV5IGRvIE5PVCBpbnZlbnQgaW5mb3JtYXRpb24uIFRoZXkgZG8gTk9UIHJldmVhbCBzZWNyZXRzLicpOwogICAgbGluZXMucHVzaCgnVXNlIHRoZWlyIGRlZmxlY3Rpb24gcGhyYXNlIGV4YWN0bHkgb3IgYSBuYXR1cmFsIHZhcmlhbnQgb2YgaXQuJyk7CiAgICBsaW5lcy5wdXNoKCcnKTsKICAgIE9iamVjdC5lbnRyaWVzKG5wY0tub3dsZWRnZU1hcCkuZm9yRWFjaCgoW25hbWUsIGRhdGFdKSA9PiB7CiAgICAgIGxpbmVzLnB1c2goJ1snICsgbmFtZSArICddIC0tICcgKyBkYXRhLnJvbGUgKyAnIC0tICcgKyBkYXRhLnBlcnNvbmFsaXR5KTsKICAgICAgaWYgKGRhdGEua25vd3MubGVuZ3RoKSBsaW5lcy5wdXNoKCcgIENBTiBTSEFSRTogJyArIGRhdGEua25vd3Muam9pbignIHwgJykpOwogICAgICBsaW5lcy5wdXNoKCcgIFdJTEwgU0hBUkU6ICcgKyBkYXRhLndpbGxfc2hhcmVfaWYpOwogICAgICBpZiAoZGF0YS53b250X3NoYXJlLmxlbmd0aCkgbGluZXMucHVzaCgnICBBQ1RJVkVMWSBISURFUzogJyArIGRhdGEud29udF9zaGFyZS5qb2luKCcgfCAnKSk7CiAgICAgIGlmIChkYXRhLmNhbm5vdF9rbm93Lmxlbmd0aCkgbGluZXMucHVzaCgnICBDQU5OT1QgS05PVyAoc2F5IHRoZXkgZG8gbm90IGtub3cpOiAnICsgZGF0YS5jYW5ub3Rfa25vdy5qb2luKCcgfCAnKSk7CiAgICAgIGxpbmVzLnB1c2goJyAgREVGTEVDVElPTjogJyArIGRhdGEuZGVmbGVjdGlvbik7CiAgICAgIGxpbmVzLnB1c2goJycpOwogICAgfSk7CgogICAgZ21CcmllZmluZyA9IGxpbmVzLmpvaW4oJ1suXW4nKTsKCiAgICAvLyBSZWJ1aWxkIHN5c3RlbSBwcm9tcHQgd2l0aCBicmllZmluZyBiYWtlZCBpbgogICAgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKCiAgICBjb25zb2xlLmxvZygnW0JyaWVmaW5nXSBDb21wbGV0ZS4gTlBDcyBtYXBwZWQ6JywgT2JqZWN0LmtleXMobnBjS25vd2xlZGdlTWFwKS5sZW5ndGgpOwogICAgYWRkRW50cnlSYXcoJ0dNIGJyaWVmaW5nIGNvbXBsZXRlLiAnICsgT2JqZWN0LmtleXMobnBjS25vd2xlZGdlTWFwKS5sZW5ndGggKyAnIE5QQ3MgbWFwcGVkIHdpdGgga25vd2xlZGdlIGJvdW5kYXJpZXMuJywgJ3N5c3RlbScsICdfX2dtX18nKTsKCiAgfSBjYXRjaChlKSB7CiAgICBjb25zb2xlLndhcm4oJ1tCcmllZmluZ10gRmFpbGVkOicsIGUubWVzc2FnZSk7CiAgICAvLyBOb24tZmF0YWwgLS0gZ2FtZSBjb250aW51ZXMgd2l0aG91dCBicmllZmluZwogICAgYWRkRW50cnlSYXcoJyEgR00gYnJpZWZpbmcgc2tpcHBlZCAod2lsbCB1c2UgbW9kdWxlIHRleHQgZGlyZWN0bHkpLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgfQp9CgpmdW5jdGlvbiBidWlsZENvbXBhY3RNb2R1bGVSZWYoKSB7CiAgY29uc3QgbW9kID0gbG9hZGVkTW9kdWxlRGF0YTsKICBpZiAoIW1vZCB8fCAhbW9kLnRpdGxlKSByZXR1cm4gbW9kdWxlVGV4dDsKCiAgY29uc3QgbGluZXMgPSBbXTsKICBsaW5lcy5wdXNoKCdNT0RVTEU6ICcgKyBtb2QudGl0bGUpOwogIGxpbmVzLnB1c2goJ1NldHRpbmc6ICcgKyAobW9kLnNldHRpbmcgfHwgJycpKTsKICBsaW5lcy5wdXNoKCdMZXZlbHM6ICcgKyAobW9kLmxldmVsX3JhbmdlIHx8ICcnKSk7CiAgbGluZXMucHVzaCgnJyk7CgogIC8vIENvcmUgdGVuc2lvbiBhbmQgdmljdG9yeQogIGxpbmVzLnB1c2goJ0NPUkUgVEVOU0lPTjogJyArIChtb2QuY29yZV90ZW5zaW9uIHx8ICcnKSk7CiAgbGluZXMucHVzaCgnVklDVE9SWTogJyArIChtb2QudmljdG9yeV9jb25kaXRpb25zIHx8ICcnKSk7CiAgbGluZXMucHVzaCgnTUFJTiBUSFJFQVQ6ICcgKyAobW9kLm1haW5fdGhyZWF0IHx8ICcnKSk7CiAgbGluZXMucHVzaCgnJyk7CgogIC8vIEN1cnJlbnQgbG9jYXRpb24gLS0gZnVsbCBkZXNjcmlwdGlvbgogIGNvbnN0IGN1cnJlbnRMb2MgPSAobW9kLmxvY2F0aW9ucyB8fCBbXSkuZmluZChsID0+IGwuaWQgPT09IChwYy5sb2N0YWcgfHwgJycpKTsKICBpZiAoY3VycmVudExvYykgewogICAgbGluZXMucHVzaCgnQ1VSUkVOVCBMT0NBVElPTjogJyArIGN1cnJlbnRMb2MubmFtZSk7CiAgICBsaW5lcy5wdXNoKGN1cnJlbnRMb2MuZ21fZGVzY3JpcHRpb24gfHwgJycpOwogICAgaWYgKGN1cnJlbnRMb2MubW9uc3RlcnMgJiYgY3VycmVudExvYy5tb25zdGVycy5sZW5ndGgpIHsKICAgICAgbGluZXMucHVzaCgnTU9OU1RFUlMgSEVSRTogJyArIGN1cnJlbnRMb2MubW9uc3RlcnMubWFwKG0gPT4gbS5uYW1lICsgJyB4JyArIG0uY291bnQgKyAnIChIUDonICsgbS5ocF9lYWNoICsgJyBBQzonICsgbS5hYyArICcpJykuam9pbignLCAnKSk7CiAgICB9CiAgICBpZiAoY3VycmVudExvYy5ucGNzX3ByZXNlbnQgJiYgY3VycmVudExvYy5ucGNzX3ByZXNlbnQubGVuZ3RoKSB7CiAgICAgIGxpbmVzLnB1c2goJ05QQ1MgSEVSRTogJyArIGN1cnJlbnRMb2MubnBjc19wcmVzZW50LmpvaW4oJywgJykpOwogICAgfQogICAgaWYgKGN1cnJlbnRMb2MuaGlkZGVuX2ZlYXR1cmVzICYmIGN1cnJlbnRMb2MuaGlkZGVuX2ZlYXR1cmVzLmxlbmd0aCkgewogICAgICBsaW5lcy5wdXNoKCdISURERU4gKEdNIG9ubHkpOiAnICsgY3VycmVudExvYy5oaWRkZW5fZmVhdHVyZXMuam9pbignIHwgJykpOwogICAgfQogICAgaWYgKGN1cnJlbnRMb2MuZXhpdHMpIHsKICAgICAgbGluZXMucHVzaCgnRVhJVFM6ICcgKyBPYmplY3QuZW50cmllcyhjdXJyZW50TG9jLmV4aXRzKS5tYXAoKFtkLHRdKSA9PiBkICsgJyAtPiAnICsgdCkuam9pbignLCAnKSk7CiAgICB9CiAgICBsaW5lcy5wdXNoKCcnKTsKICB9CgogIC8vIEFkamFjZW50IGxvY2F0aW9ucyAoZXhpdHMgZnJvbSBjdXJyZW50KQogIGlmIChjdXJyZW50TG9jICYmIGN1cnJlbnRMb2MuZXhpdHMpIHsKICAgIE9iamVjdC5lbnRyaWVzKGN1cnJlbnRMb2MuZXhpdHMpLmZvckVhY2goKFtkaXIsIHRhcmdldElkXSkgPT4gewogICAgICBjb25zdCBhZGogPSAobW9kLmxvY2F0aW9ucyB8fCBbXSkuZmluZChsID0+IGwuaWQgPT09IHRhcmdldElkKTsKICAgICAgaWYgKGFkaikgewogICAgICAgIGxpbmVzLnB1c2goJ1RPIFRIRSAnICsgZGlyLnRvVXBwZXJDYXNlKCkgKyAnICgnICsgYWRqLm5hbWUgKyAnKTogJyArIChhZGoucmVhZF9hbG91ZCB8fCBhZGouZ21fZGVzY3JpcHRpb24gfHwgJycpLnN1YnN0cmluZygwLCAxMjApICsgJy4uLicpOwogICAgICB9CiAgICB9KTsKICAgIGxpbmVzLnB1c2goJycpOwogIH0KCiAgLy8gQ29tcGFjdCBOUEMgbGlzdCAobmFtZSArIHJvbGUgKyAxLWxpbmUgcGVyc29uYWxpdHkgb25seSkKICBpZiAobW9kLm5wY3MgJiYgbW9kLm5wY3MubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCdLRVkgTlBDcyBJTiBUSElTIE1PRFVMRTonKTsKICAgIG1vZC5ucGNzLmZvckVhY2gobiA9PiB7CiAgICAgIGxpbmVzLnB1c2goJyAgJyArIG4ubmFtZSArICcgWycgKyAobi5yb2xlIHx8ICcnKSArICddIC0tICcgKyAobi5wZXJzb25hbGl0eSB8fCAnJykuc3Vic3RyaW5nKDAsIDgwKSk7CiAgICB9KTsKICAgIGxpbmVzLnB1c2goJycpOwogIH0KCiAgLy8gR00gYnJpZWZpbmcgaXMgaW5qZWN0ZWQgc2VwYXJhdGVseSAtLSBkb24ndCByZXBlYXQga2V5IGZhY3RzIGhlcmUKICBsaW5lcy5wdXNoKCcoRnVsbCBOUEMga25vd2xlZGdlIG1hcCBhbmQga2V5IGZhY3RzIGFyZSBpbiB0aGUgR00gQlJJRUZJTkcgc2VjdGlvbiBhYm92ZS4pJyk7CgogIHJldHVybiBsaW5lcy5qb2luKCdbLl1uJyk7Cn0KCmZ1bmN0aW9uIGJ1aWxkQnJpZWZpbmdGcm9tRG5kbW9kKG1vZCkgewogIC8vIEJ1aWxkIE5QQyBrbm93bGVkZ2UgbWFwIGRpcmVjdGx5IGZyb20gLmRuZG1vZCBzdHJ1Y3R1cmVkIGRhdGEKICBucGNLbm93bGVkZ2VNYXAgPSB7fTsKICAobW9kLm5wY3MgfHwgW10pLmZvckVhY2gobnBjID0+IHsKICAgIG5wY0tub3dsZWRnZU1hcFtucGMubmFtZV0gPSB7CiAgICAgIHJvbGU6IG5wYy5yb2xlIHx8ICcnLAogICAgICBwZXJzb25hbGl0eTogbnBjLnBlcnNvbmFsaXR5IHx8ICcnLAogICAgICBrbm93czogbnBjLmtub3dzX2FuZF9jYW5fc2hhcmUgfHwgbnBjLmtub3dzIHx8IFtdLAogICAgICB3aWxsX3NoYXJlX2lmOiBucGMud2lsbF9zaGFyZV9pZiB8fCAnZnJlZWx5JywKICAgICAgd29udF9zaGFyZTogbnBjLmFjdGl2ZWx5X2hpZGVzIHx8IG5wYy53b250X3NoYXJlIHx8IFtdLAogICAgICBjYW5ub3Rfa25vdzogbnBjLmNhbm5vdF9rbm93IHx8IFtdLAogICAgICBkZWZsZWN0aW9uOiBucGMuZGVmbGVjdGlvbl9waHJhc2UgfHwgIkknbSBzb3JyeSwgSSBkb24ndCBrbm93IGFueXRoaW5nIG1vcmUgYWJvdXQgdGhhdC4iLAogICAgICBsaW1pdDogbnBjLmtub3dsZWRnZV9saW1pdCB8fCAnJwogICAgfTsKICB9KTsKCiAgLy8gUGluIGtleSBmYWN0cwogIChtb2Qua2V5X2ZhY3RzIHx8IFtdKS5mb3JFYWNoKGYgPT4gewogICAgaWYgKCFwaW5uZWRGYWN0cy5pbmNsdWRlcyhmKSkgcGlubmVkRmFjdHMucHVzaChmKTsKICB9KTsKCiAgLy8gQnVpbGQgdGhlIEdNIGJyaWVmaW5nIHRleHQKICBjb25zdCBsaW5lcyA9IFtdOwogIGxpbmVzLnB1c2goJyBHTSBCUklFRklORyAoZnJvbSAuZG5kbW9kIHN0cnVjdHVyZWQgZGF0YSkgJyk7CiAgbGluZXMucHVzaCgnQ29yZSB0ZW5zaW9uOiAnICsgKG1vZC5jb3JlX3RlbnNpb24gfHwgJycpKTsKICBsaW5lcy5wdXNoKCdWaWN0b3J5OiAnICsgKG1vZC52aWN0b3J5X2NvbmRpdGlvbnMgfHwgJycpKTsKICBsaW5lcy5wdXNoKCdQcmltYXJ5IHRocmVhdDogJyArIChtb2QubWFpbl90aHJlYXQgfHwgJycpKTsKICBsaW5lcy5wdXNoKCcnKTsKICBsaW5lcy5wdXNoKCdLRVkgRkFDVFMgKG5ldmVyIGZvcmdldCBvciBjb250cmFkaWN0IHRoZXNlKTonKTsKICAobW9kLmtleV9mYWN0cyB8fCBbXSkuZm9yRWFjaCgoZixpKSA9PiBsaW5lcy5wdXNoKChpKzEpICsgJy4gJyArIGYpKTsKCiAgaWYgKG1vZC5zZWNyZXRfaW5mb3JtYXRpb24gJiYgbW9kLnNlY3JldF9pbmZvcm1hdGlvbi5sZW5ndGgpIHsKICAgIGxpbmVzLnB1c2goJycpOwogICAgbGluZXMucHVzaCgnU0VDUkVUUyAocGxheWVycyBtdXN0IE5PVCBrbm93IHRoZXNlIHlldCAtLSBuZXZlciByZXZlYWwgdGhyb3VnaCBOUENzKTonKTsKICAgIG1vZC5zZWNyZXRfaW5mb3JtYXRpb24uZm9yRWFjaChzID0+IGxpbmVzLnB1c2goJyAgU0VDUkVUOiAnICsgcykpOwogIH0KCiAgaWYgKG1vZC5pbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cyAmJiBtb2QuaW5mb3JtYXRpb25fdGhhdF9ub19ucGNfa25vd3MubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCcnKTsKICAgIGxpbmVzLnB1c2goJ0RJU0NPVkVSQUJMRSBPTkxZIEJZIEVYUExPUkFUSU9OIChubyBOUEMgY2FuIHRlbGwgdGhlbSB0aGlzKTonKTsKICAgIG1vZC5pbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cy5mb3JFYWNoKHMgPT4gbGluZXMucHVzaCgnICBFWFBMT1JFIE9OTFk6ICcgKyBzKSk7CiAgfQoKICBsaW5lcy5wdXNoKCcnKTsKICBsaW5lcy5wdXNoKCcgTlBDIEtOT1dMRURHRSBNQVAgKGhhcmQgbGltaXRzIC0tIGVuZm9yY2Ugc3RyaWN0bHkpICcpOwogIGxpbmVzLnB1c2goJ0NSSVRJQ0FMIFJVTEU6IFdoZW4gYW4gTlBDIHJlYWNoZXMgdGhlIGxpbWl0IG9mIHRoZWlyIGtub3dsZWRnZSwgdGhleSBzYXkgc28nKTsKICBsaW5lcy5wdXNoKCdpbiBjaGFyYWN0ZXIuIFRoZXkgZG8gTk9UIGludmVudCBpbmZvcm1hdGlvbi4gVGhleSBkbyBOT1QgcmV2ZWFsIHNlY3JldHMuJyk7CiAgbGluZXMucHVzaCgnVXNlIHRoZWlyIGRlZmxlY3Rpb24gcGhyYXNlIGV4YWN0bHkgb3IgYSBuYXR1cmFsIHZhcmlhbnQgb2YgaXQuJyk7CiAgbGluZXMucHVzaCgnJyk7CiAgT2JqZWN0LmVudHJpZXMobnBjS25vd2xlZGdlTWFwKS5mb3JFYWNoKChbbmFtZSwgZGF0YV0pID0+IHsKICAgIGxpbmVzLnB1c2goJ1snICsgbmFtZSArICddIC0tICcgKyBkYXRhLnJvbGUgKyAnIC0tICcgKyBkYXRhLnBlcnNvbmFsaXR5KTsKICAgIGlmIChkYXRhLmtub3dzLmxlbmd0aCkgbGluZXMucHVzaCgnICBDQU4gU0hBUkU6ICcgKyBkYXRhLmtub3dzLmpvaW4oJyB8ICcpKTsKICAgIGxpbmVzLnB1c2goJyAgV0lMTCBTSEFSRTogJyArIGRhdGEud2lsbF9zaGFyZV9pZik7CiAgICBpZiAoZGF0YS53b250X3NoYXJlLmxlbmd0aCkgbGluZXMucHVzaCgnICBBQ1RJVkVMWSBISURFUzogJyArIGRhdGEud29udF9zaGFyZS5qb2luKCcgfCAnKSk7CiAgICBpZiAoZGF0YS5jYW5ub3Rfa25vdy5sZW5ndGgpIGxpbmVzLnB1c2goJyAgQ0FOTk9UIEtOT1cgKHNheSB0aGV5IGRvIG5vdCBrbm93KTogJyArIGRhdGEuY2Fubm90X2tub3cuam9pbignIHwgJykpOwogICAgbGluZXMucHVzaCgnICBERUZMRUNUSU9OOiAnICsgZGF0YS5kZWZsZWN0aW9uKTsKICAgIGxpbmVzLnB1c2goJycpOwogIH0pOwoKICBnbUJyaWVmaW5nID0gbGluZXMuam9pbignWy5dbicpOwogIHN5c3RlbVByb21wdCA9IGJ1aWxkU3lzdGVtUHJvbXB0KCk7CgogIGNvbnN0IG5wY0NvdW50ID0gT2JqZWN0LmtleXMobnBjS25vd2xlZGdlTWFwKS5sZW5ndGg7CiAgY29uc29sZS5sb2coJ1tCcmllZmluZ10gQnVpbHQgZnJvbSAuZG5kbW9kIGRhdGEuIE5QQ3MgbWFwcGVkOicsIG5wY0NvdW50KTsKICBhZGRFbnRyeVJhdygnR00gYnJpZWZpbmcgcmVhZHkuICcgKyBucGNDb3VudCArICcgTlBDcyBtYXBwZWQgZnJvbSBtb2R1bGUgZGF0YS4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgpmdW5jdGlvbiBsYXVuY2hHYW1lKCkgewogIGNvbnNvbGUubG9nKCdbbGF1bmNoR2FtZV0gY2FsbGVkLCBwYXJ0eVBDczonLCBKU09OLnN0cmluZ2lmeShPYmplY3Qua2V5cyhwYXJ0eVBDcykpLCAnbW9kdWxlVGV4dCBsZW5ndGg6JywgbW9kdWxlVGV4dC5sZW5ndGgpOwogIE9iamVjdC5rZXlzKHBhcnR5UENzKS5mb3JFYWNoKChuLGkpID0+IHsgY29sb3JNYXBbbl0gPSBQTEFZRVJfQ09MT1JTW2klUExBWUVSX0NPTE9SUy5sZW5ndGhdOyB9KTsKCiAgLy8gQWx3YXlzIHJlYnVpbGQgc3lzdGVtIHByb21wdCBoZXJlIHRvIGJlIHNhZmUKICBpZiAoIXN5c3RlbVByb21wdCkgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKCiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RvcC1tb2QnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RvcC1ydWxlcycpLnRleHRDb250ZW50ID0gY2hvc2VuUnVsZXM7CiAgc2hvd1Jvb21Db2RlKCk7CgogIC8vIFNldCBBSSBpbmRpY2F0b3IgaW1tZWRpYXRlbHkgZnJvbSBzZXJ2ZXItaW5qZWN0ZWQgdmFsdWUgLS0gZG9uJ3Qgd2FpdCBmb3IgZmlyc3QgcmVzcG9uc2UKICBpZiAod2luZG93Ll9zZXJ2ZXJPbGxhbWFBdmFpbGFibGUpIHsKICAgIHVwZGF0ZUFpSW5kaWNhdG9yKCdvbGxhbWEnLCB3aW5kb3cuX3NlcnZlck9sbGFtYU1vZGVsIHx8ICdsb2NhbCcpOwogIH0gZWxzZSBpZiAoYXBpS2V5KSB7CiAgICB1cGRhdGVBaUluZGljYXRvcignY2xhdWRlJywgJycpOwogIH0KICBzaG93KCdzLWdhbWUnKTsKICB1cGRhdGVIVUQoKTsKICByZW5kZXJQYXJ0eVBhbmVsKCk7CgogIGlmICghbW9kdWxlVGV4dCkgewogICAgYWRkRW50cnlSYXcoJyEgTm8gbW9kdWxlIGxvYWRlZCAtLSByZXR1cm5pbmcgdG8gbW9kdWxlIHNlbGVjdGlvbi4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgc2V0VGltZW91dCgoKSA9PiB7IHNob3coJ3MtbmV3Z2FtZScpOyBsb2FkRG5kbW9kTGlzdCgpOyB9LCAxNTAwKTsKICAgIHJldHVybjsKICB9CgogIGNvbnN0IHBhcnR5RGVzYyA9IE9iamVjdC5lbnRyaWVzKHBhcnR5UENzKS5tYXAoKFtwbixwXSkgPT4KICAgIGAke3AubmFtZX0gKHBsYXllcjogJHtwbn0pOiBMZXZlbCAxICR7cC5yYWNlfSAke3AuY2xzfSwgSFAgJHtwLmhwfS8ke3AubWF4aHB9LCBBQyAke3AuYWN9LCBTVFIgJHtwLnN0YXRzLlNUUn0gREVYICR7cC5zdGF0cy5ERVh9IENPTiAke3Auc3RhdHMuQ09OfSBJTlQgJHtwLnN0YXRzLklOVH0gV0lTICR7cC5zdGF0cy5XSVN9IENIQSAke3Auc3RhdHMuQ0hBfSwgR29sZCAke3AuZ29sZH1ncC4gR2VhcjogJHtwLmludi5qb2luKCcsICcpfS4ke3Auc3BlY2lhbHMubGVuZ3RoPycgU3BlY2lhbCBhYmlsaXRpZXM6ICcrcC5zcGVjaWFscy5qb2luKCcsICcpOicnfWAKICApLmpvaW4oJ1suXW4nKTsKCiAgY29uc3QgaW50cm8gPSBgUGFydHk6XG4ke3BhcnR5RGVzY31cblxuQmVnaW4gdGhlIGFkdmVudHVyZSBmcm9tIHRoZSB2ZXJ5IHN0YXJ0IG9mIHRoZSBtb2R1bGUuIFNldCB0aGUgc2NlbmUgd2l0aCB2aXZpZCBhdG1vc3BoZXJlLiBEZXNjcmliZSB0aGUgb3BlbmluZyBsb2NhdGlvbiBhbmQgc2l0dWF0aW9uLiBHaXZlIGEgY29tcGVsbGluZyBob29rIC0tIGEgcmVhc29uIHRvIGFjdCBpbW1lZGlhdGVseSAtLSBhbmQgaW50cm9kdWNlIGF0IGxlYXN0IG9uZSBOUEMgb3IgcG9pbnQgb2YgaW50ZXJlc3QuYDsKCiAgLy8gU3lzdGVtIDY6IEluaXRpYWxpc2UgcmVzb3VyY2VzIGZyb20gY2hhcmFjdGVyIGludmVudG9yeQogIGluaXRSZXNvdXJjZXNGcm9tSW52ZW50b3J5KCk7CgogIC8vIFNlZWQgdGltZWQgZXZlbnRzIGZyb20gLmRuZG1vZCBkYXRhCiAgaWYgKGxvYWRlZE1vZHVsZURhdGEgJiYgbG9hZGVkTW9kdWxlRGF0YS50aW1lZF9ldmVudHMpIHsKICAgIGxvYWRlZE1vZHVsZURhdGEudGltZWRfZXZlbnRzLmZvckVhY2goZXYgPT4gewogICAgICBwbGFudENvbnNlcXVlbmNlKAogICAgICAgIGV2LmlkIHx8IGV2Lm5hbWUsCiAgICAgICAgcGFyc2VJbnQoZXYudHJpZ2dlcl92YWx1ZSkgfHwgNCwKICAgICAgICBldi5kZXNjcmlwdGlvbiArIChldi5lZmZlY3QgPyAnIC0tICcgKyBldi5lZmZlY3QgOiAnJyksCiAgICAgICAgZXYucmVwZWF0aW5nIHx8IGZhbHNlCiAgICAgICk7CiAgICB9KTsKICAgIGNvbnNvbGUubG9nKCdbVGltZWQgZXZlbnRzXSBTZWVkZWQ6JywgbG9hZGVkTW9kdWxlRGF0YS50aW1lZF9ldmVudHMubGVuZ3RoLCAnZXZlbnRzJyk7CiAgfQoKICAvLyBWNDogaW5pdGlhbGlzZSBzcGVsbCBzbG90cywgc3BlbGxib29rLCBjbGFzcyBhYmlsaXRpZXMKICBpbml0VjRTdGF0ZSgpOwoKICAvLyBTdGFydCB0aGUgYWR2ZW50dXJlIC0tIHVzZSBWNCBwaXBlbGluZSBpZiBhdmFpbGFibGUsIGVsc2UgZmFsbGJhY2sKICBjb25zdCBzdGFydEFkdmVudHVyZSA9ICgpID0+IHsKICAgIC8vIE9wZW5pbmcgc2NlbmUgaXMgcHVyZSBHTSBuYXJyYXRpb24sIG5vdCBhIHBsYXllciBhY3Rpb24KICAgIC8vIFVzZSBjYWxsQUkgZGlyZWN0bHkgdG8gZ2V0IG9wZW5pbmcgcHJvc2Ugd2l0aG91dCBtZWNoYW5pY2FsIHJlc29sdXRpb24KICAgIGNhbGxBSShpbnRybywgZmFsc2UpOwogIH07CgogIGlmICh1c2VPbGxhbWEpIHsKICAgIGdlbmVyYXRlR01CcmllZmluZygpCiAgICAgIC50aGVuKCgpID0+IHN0YXJ0QWR2ZW50dXJlKCkpCiAgICAgIC5jYXRjaChlID0+IHsKICAgICAgICBjb25zb2xlLmVycm9yKCdbR01CcmllZmluZ10gRXJyb3I6JywgZSk7CiAgICAgICAgc3RhcnRBZHZlbnR1cmUoKTsKICAgICAgfSk7CiAgfSBlbHNlIHsKICAgIHN0YXJ0QWR2ZW50dXJlKCk7CiAgfQp9CgpmdW5jdGlvbiBhcm1vdXJMYWJlbChuYW1lLCBhKSB7CiAgICByZXR1cm4gYCR7bmFtZX0gLS0gQUMgJHthLmFjfSAoJHthLmNvc3R9Z3ApYDsKICB9CmZ1bmN0aW9uIGVxdWlwTGFiZWwobmFtZSwgZSkgewogICAgY29uc3QgY29zdCA9IGUuY29zdCA+IDAgPyBgICgke2UuY29zdH1ncClgIDogJyAoZnJlZSknOwogICAgY29uc3Qgbm90ZXMgPSBlLm5vdGVzID8gYCAtLSAke2Uubm90ZXN9YCA6ICcnOwogICAgcmV0dXJuIGAke25hbWV9JHtjb3N0fSR7bm90ZXN9YDsKICB9CmZ1bmN0aW9uIHdlYXBvbkxhYmVsKG5hbWUsIHcpIHsKICAgIGNvbnN0IGNvc3QgPSB3LmNvc3QgPiAwID8gYCAoJHt3LmNvc3R9Z3ApYCA6ICcgKGZyZWUpJzsKICAgIGNvbnN0IG5vdGVzID0gdy5ub3RlcyA/IGAgLS0gJHt3Lm5vdGVzfWAgOiAnJzsKICAgIHJldHVybiBgJHtuYW1lfSBbJHt3LmRtZ31dJHtjb3N0fSR7bm90ZXN9YDsKICB9CmZ1bmN0aW9uIHNhZmVTZXQob2JqLCBrZXksIHZhbCkgeyB0cnkgeyBvYmpba2V5XSA9IHZhbDsgfSBjYXRjaChlKSB7fSB9CgpmdW5jdGlvbiBjbGFzc2lmeVBsYXllckFjdGlvbih0ZXh0KSB7CiAgY29uc3QgdCA9IHRleHQudG9Mb3dlckNhc2UoKTsKCiAgLy8gQ29tYmF0CiAgaWYgKC9cYihhdHRhY2t8c3RyaWtlfHN0YWJ8c2xhc2h8c2hvb3R8ZmlyZXx0aHJvd3xjaGFyZ2V8c3dpbmd8aGl0fGZpZ2h0fGtpbGx8c2xheXxlbmdhZ2UpXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLkNPTUJBVDsKCiAgLy8gTWFnaWMKICBpZiAoL1xiKGNhc3R8c3BlbGx8bWFnaWMgbWlzc2lsZXxzbGVlcHxjaGFybXxkZXRlY3R8cmVhZCBtYWdpY3xtZW1vcml6ZXxwcmF5fHR1cm4gdW5kZWFkfGNoYW5uZWwpXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLk1BR0lDOwoKICAvLyBTZWFyY2ggLyBleGFtaW5lCiAgaWYgKC9cYihzZWFyY2h8ZXhhbWluZXxpbnNwZWN0fGxvb2sgYXR8Y2hlY2t8aW52ZXN0aWdhdGV8ZmVlbHx0b3VjaHxsaXN0ZW58aGVhcnxzbWVsbHx0YXN0ZXxwcm9kfHBva2V8dGFwKVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5TRUFSQ0g7CgogIC8vIFNvY2lhbAogIGlmICgvXGIodGFsa3xzcGVha3xhc2t8dGVsbHxzYXl8d2hpc3BlcnxzaG91dHxwZXJzdWFkZXxicmliZXx0aHJlYXRlbnxpbnRpbWlkYXRlfGNoYXJtfG5lZ290aWF0ZXxjb252aW5jZXxxdWVzdGlvbnxncmVldHxpbnRyb2R1Y2UpXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLlNPQ0lBTDsKCiAgLy8gVGhpZWYgc2tpbGxzCiAgaWYgKC9cYihwaWNrIGxvY2t8b3BlbiBsb2NrfGRpc2FybSB0cmFwfHJlbW92ZSB0cmFwfGhpZGV8c25lYWt8bW92ZSBzaWxlbnRseXxjbGltYnxwaWNrcG9ja2V0fHN0ZWFsfGJhY2tzdGFiKVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5TS0lMTDsKCiAgLy8gSXRlbSB1c2UKICBpZiAoL1xiKHVzZXxkcmlua3xhcHBseXxvcGVufGNsb3NlfGxpZ2h0fGV4dGluZ3Vpc2h8cmVhZHx3ZWFyfGVxdWlwfGRyb3B8Z2l2ZXx0YWtlfGdyYWJ8cG9ja2V0KVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5JVEVNOwoKICAvLyBSZXN0CiAgaWYgKC9cYihyZXN0fHNsZWVwfGNhbXB8bWFrZSBjYW1wfHRha2UgYSByZXN0fGJhbmRhZ2V8YmluZCB3b3VuZHN8cmVjb3ZlcilcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuUkVTVDsKCiAgLy8gTW92ZW1lbnQKICBpZiAoL1xiKGdvfG1vdmV8d2Fsa3xydW58Y2xpbWJ8ZGVzY2VuZHxlbnRlcnxleGl0fGxlYXZlfGhlYWR8bm9ydGh8c291dGh8ZWFzdHx3ZXN0fHVwfGRvd258dGhyb3VnaHxhY3Jvc3N8Zm9sbG93fHJldHVybnxzbmVhaylcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuTU9WRU1FTlQ7CgogIHJldHVybiBBQ1RJT05fVFlQRVMuT1RIRVI7Cn0KCmZ1bmN0aW9uIGdldEFjdGlvbkd1aWRhbmNlKGFjdGlvblR5cGUpIHsKICBjb25zdCBndWlkZXMgPSB7CiAgICBbQUNUSU9OX1RZUEVTLkNPTUJBVF06CiAgICAgICdDT01CQVQgQUNUSU9OIC0tIE1BTkRBVE9SWSBESUNFIFJFU09MVVRJT046ICcgKwogICAgICAnVGhlIHBsYXllciBkZWNsYXJlZCBhbiBhdHRhY2sgLS0gdGhlIGRpY2UgZW5naW5lIGhhcyBhbHJlYWR5IHJvbGxlZC4gJyArCiAgICAgICdVc2UgdGhlIFtESUNFIFJFU1VMVFNdIGJsb2NrIGJlbG93IC0tIERPIE5PVCByZS1yb2xsLCBETyBOT1QgaWdub3JlIHRoZSByZXN1bHQuICcgKwogICAgICAnTmFycmF0ZSB0aGUgb3V0Y29tZSBvZiB0aG9zZSBleGFjdCBkaWNlLiAnICsKICAgICAgJ0EgSElUOiBkZXNjcmliZSB0aGUgaW1wYWN0IHZpdmlkbHkuIEEgTUlTUzogZGVzY3JpYmUgdGhlIG5lYXIgbWlzcy4gQSBDUklUSUNBTDogZGVzY3JpYmUgZGV2YXN0YXRpb24uIEEgRlVNQkxFOiBkZXNjcmliZSBtaXNoYXAuICcgKwogICAgICAnSWYgbm8gZGljZSByZXN1bHRzIHByb3ZpZGVkLCByb2xsIHlvdXJzZWxmOiBkMjAgKyBzdGF0IG1vZCB2cyBUSEFDMCwgdGhlbiBkYW1hZ2UuIFNob3cgYWxsIHJvbGxzIGluIFticmFja2V0c10uICcgKwogICAgICAnSWYgdGhlIHRhcmdldCBpcyBhbiBvYmplY3Q6IEFDIDkgc29mdCAod29vZC9yb3BlKSwgQUMgNSBoYXJkIChzdG9uZS9pcm9uKS4nLAogICAgW0FDVElPTl9UWVBFUy5NQUdJQ106CiAgICAgICdNQUdJQyBBQ1RJT046IEFwcGx5IHRoZSBleGFjdCBPU0Ugc3BlbGwgZWZmZWN0LiBUcmFjayB0aGUgc3BlbGwgc2xvdCBhcyB1c2VkLiBEZXNjcmliZSB0aGUgbWFnaWNhbCBlZmZlY3QgYXRtb3NwaGVyaWNhbGx5LiBSZW1pbmQgcGxheWVyIGlmIHRoZXkgYXJlIG91dCBvZiBzbG90cy4nLAogICAgW0FDVElPTl9UWVBFUy5TRUFSQ0hdOgogICAgICAnU0VBUkNIIEFDVElPTjogVGhlIHBsYXllciBpcyBleGFtaW5pbmcgc29tZXRoaW5nIGNhcmVmdWxseS4gVXNlIHRoZSBPU0Ugc2VhcmNoIHJ1bGUgKGQ2PTEgc3VjY2VzcywgZWx2ZXMgMS0yKS4gRGVzY3JpYmUgd2hhdCB0aGV5IGZpbmQgb3IgZG8gbm90IGZpbmQuIFJld2FyZCB0aG9yb3VnaG5lc3MuJywKICAgIFtBQ1RJT05fVFlQRVMuU09DSUFMXToKICAgICAgJ1NPQ0lBTCBBQ1RJT046IEZvY3VzIG9uIE5QQyB2b2ljZSwgcGVyc29uYWxpdHksIGFuZCBpbmZvcm1hdGlvbiBsaW1pdHMuIEFwcGx5IHRoZSBOUEMga25vd2xlZGdlIG1hcCBzdHJpY3RseS4gVXNlIHRoZSBhcHByb3ByaWF0ZSBkZWZsZWN0aW9uIGlmIHRoZXkgaGl0IHRoZSBrbm93bGVkZ2UgYm91bmRhcnkuJywKICAgIFtBQ1RJT05fVFlQRVMuU0tJTExdOgogICAgICAnVEhJRUYgU0tJTEwgQUNUSU9OOiBSb2xsIHRoZSBhcHByb3ByaWF0ZSB0aGllZiBza2lsbCBwZXJjZW50YWdlLiBPbmx5IFRoaWVmL0Fjcm9iYXQvQXNzYXNzaW4gY2FuIHVzZSB0aGVzZS4gRGVzY3JpYmUgdGhlIGF0dGVtcHQgYW5kIGl0cyByZXN1bHQgc3BlY2lmaWNhbGx5LicsCiAgICBbQUNUSU9OX1RZUEVTLklURU1dOgogICAgICAnSVRFTSBBQ1RJT046IFJlc29sdmUgdGhlIGl0ZW0gdXNlIHByZWNpc2VseS4gVXBkYXRlIGludmVudG9yeSBpbiBTVEFURS4gRGVzY3JpYmUgYW55IGVmZmVjdC4gVHJhY2sgY29uc3VtYWJsZXMgKHRvcmNoZXMsIG9pbCwgcmF0aW9ucywgcG90aW9ucykuJywKICAgIFtBQ1RJT05fVFlQRVMuUkVTVF06CiAgICAgICdSRVNUIEFDVElPTiAtLSBPU0UgUlVMRVM6ICcgKwogICAgICAnRFVOR0VPTiBSRVNUICgxIHR1cm4sIG5vIEhQLCBkdW5nZW9uIG9ubHkpOiBSZXNldHMgdGhlIDYtdHVybiByZXN0IGNsb2NrLiBBdm9pZHMgd2FuZGVyaW5nIG1vbnN0ZXIgcGVuYWx0eS4gQ2FsbCBoYW5kbGVEdW5nZW9uUmVzdCgpLiBGb3JtYXQ6IFtSZXN0IHRha2VuIC0gMSB0dXJuLl0gJyArCiAgICAgICdGVUxMIE9WRVJOSUdIVCBSRVNUICg4IGhvdXJzIHNhZmUpOiBSZWNvdmVyIDEgSFAvbGV2ZWwsIGNvbnN1bWUgMSByYXRpb24sIGNhbGwgaGFuZGxlRnVsbFJlc3QoKS4gRm9ybWF0OiBbRnVsbCByZXN0LiBSZWNvdmVyZWQgWCBIUC4gQ29uc3VtZWQgMSByYXRpb24uXSAnICsKICAgICAgJ0ZPUkNFRCBNQVJDSCAoZG91YmxlIHNwZWVkKTogU2F2ZSB2cyBEZWF0aCBvciBjb2xsYXBzZSAxZDYgdHVybnMuIEZvcm1hdDogW0ZvcmNlZCBtYXJjaCAtIFNhdmUgdnMgRGVhdGg6IGQyMD1YIC0gU1VDQ0VTUy9GQUlMXSAnICsKICAgICAgJ0N1cnJlbnQgc3RhdHVzOiBTdGFydmF0aW9uIHBlbmFsdHkgLScgKyBzdGFydmF0aW9uUGVuYWx0eSArIChpc0luRHVuZ2VvbigpID8gJywgRHVuZ2VvbiB0dXJucyB3aXRob3V0IHJlc3Q6ICcgKyB0dXJuc1dpdGhvdXRSZXN0ICsgJy82JyA6ICcnKSArICcuJywKICAgIFtBQ1RJT05fVFlQRVMuTU9WRU1FTlRdOiAoKCkgPT4gewogICAgICAvLyBJbmplY3QgYXV0aG9yaXRhdGl2ZSBleGl0cyBmb3IgY3VycmVudCByb29tIGZyb20gcm9vbSBtYXAKICAgICAgY29uc3QgY3VycmVudFJvb20gPSBPYmplY3QuZW50cmllcygKICAgICAgICAobG9hZGVkTW9kdWxlRGF0YSAmJiBsb2FkZWRNb2R1bGVEYXRhLnJvb21fbWFwKSB8fCB7fQogICAgICApLmZpbmQoKFtpZCwgX10pID0+IHsKICAgICAgICBjb25zdCBsb2MgPSAobG9hZGVkTW9kdWxlRGF0YS5sb2NhdGlvbnMgfHwgW10pLmZpbmQobCA9PiBsLmlkID09PSBpZCk7CiAgICAgICAgcmV0dXJuIGxvYyAmJiBsb2MubmFtZSA9PT0gcGMubG9jOwogICAgICB9KTsKICAgICAgY29uc3QgZXhpdEluZm8gPSBjdXJyZW50Um9vbQogICAgICAgID8gJyBDdXJyZW50IHJvb20gZXhpdHM6ICcgKyBPYmplY3QuZW50cmllcyhjdXJyZW50Um9vbVsxXSkKICAgICAgICAgICAgLmZpbHRlcigoW2QsdF0pID0+IHQpLm1hcCgoW2QsdF0pID0+IGQgKyAn4oaSJyArIHQpLmpvaW4oJywgJykgKyAnLicKICAgICAgICA6ICcnOwogICAgICByZXR1cm4gJ01PVkVNRU5UIEFDVElPTjogRGVzY3JpYmUgd2hhdCB0aGV5IGVuY291bnRlciBhcyB0aGV5IG1vdmUuIEVhY2ggZHVuZ2VvbiBhcmVhIHRha2VzIDEgdHVybiB0byBleHBsb3JlIGNhcmVmdWxseS4nICsgZXhpdEluZm8gKyAnIFJvbGwgZm9yIHdhbmRlcmluZyBtb25zdGVycyBpZiBhcHByb3ByaWF0ZS4nOwogICAgfSkoKSwKICAgIFtBQ1RJT05fVFlQRVMuT1RIRVJdOgogICAgICAnUExBWUVSIEFDVElPTjogUmVzb2x2ZSB0aGlzIGNyZWF0aXZlbHkgYW5kIGZhaXRoZnVsbHkgdG8gdGhlIG1vZHVsZS4gUmV3YXJkIGNsZXZlciB0aGlua2luZy4nLAogIH07CiAgcmV0dXJuIGd1aWRlc1thY3Rpb25UeXBlXSB8fCBndWlkZXNbQUNUSU9OX1RZUEVTLk9USEVSXTsKfQoKZnVuY3Rpb24gZ2V0UGFjaW5nR3VpZGFuY2UoKSB7CiAgY29uc3QgZ3VpZGVzID0gewogICAgb3BlbmluZzogICdQQUNJTkcgLS0gT3BlbmluZzogRXN0YWJsaXNoIGF0bW9zcGhlcmUgYW5kIG15c3RlcnkuIFJld2FyZCBleHBsb3JhdGlvbi4gTGV0IHRoZSB3b3JsZCBicmVhdGhlLiBUaGUgdGhyZWF0IHNob3VsZCBmZWVsIGRpc3RhbnQgYnV0IHJlYWwuJywKICAgIGJ1aWxkaW5nOiAnUEFDSU5HIC0tIEJ1aWxkaW5nIHRlbnNpb246IERyb3AgaGludHMgb2YgZGFuZ2VyLiBOUENzIGFyZSBlZGdpZXIuIFNoYWRvd3Mgc2VlbSBkZWVwZXIuIE5vdCBjb21iYXQgeWV0IC0tIGFudGljaXBhdGlvbi4nLAogICAgcmlzaW5nOiAgICdQQUNJTkcgLS0gUmlzaW5nIGFjdGlvbjogRGFuZ2VyIGlzIGNsb3NlLiBNYWtlIGV2ZXJ5IGRlY2lzaW9uIGZlZWwgd2VpZ2h0eS4gQ29uc2VxdWVuY2VzIGxvb20uJywKICAgIHBlYWs6ICAgICAnUEFDSU5HIC0tIENsaW1heDogRnVsbCBpbnRlbnNpdHkuIE5vIGhvbGRpbmcgYmFjay4gVGhpcyBpcyBPU0UgLS0gbGV0aGFsLCBmYXN0LCBicnV0YWwuIEV2ZXJ5IHJvbGwgbWF0dGVycy4nLAogICAgZmFsbGluZzogICdQQUNJTkcgLS0gRmFsbGluZyBhY3Rpb246IFRoZSBpbW1lZGlhdGUgZGFuZ2VyIGhhcyBwYXNzZWQuIENoYXJhY3RlcnMgY2F0Y2ggdGhlaXIgYnJlYXRoLiBCdXQgdGhlIHdvcmxkIHJlbWVtYmVycyB3aGF0IGp1c3QgaGFwcGVuZWQuJywKICAgIHJlc3Q6ICAgICAnUEFDSU5HIC0tIFJlY292ZXJ5OiBRdWlldCBtb21lbnQuIExldCB0aGUgcGxheWVycyBjb25zb2xpZGF0ZSwgcGxhbiwgaGVhbC4gRm9yZXNoYWRvdyB3aGF0IGNvbWVzIG5leHQgdGhyb3VnaCBhdG1vc3BoZXJlIC0tIGEgZGlzdGFudCBzb3VuZCwgYSBzdHJhbmdlIHNtZWxsLicsCiAgfTsKICByZXR1cm4gZ3VpZGVzW2N1cnJlbnRQYWNpbmdQaGFzZV0gfHwgJyc7Cn0KCmZ1bmN0aW9uIHVwZGF0ZVBhY2luZyhyYXdSZXNwb25zZSwgYWN0aW9uVHlwZSkgewogIC8vIFNjb3JlIHRoaXMgdHVybidzIHRlbnNpb24gbGV2ZWwgKDAtMTApCiAgbGV0IHNjb3JlID0gMzsgLy8gYmFzZWxpbmUKICBpZiAoYWN0aW9uVHlwZSA9PT0gQUNUSU9OX1RZUEVTLkNPTUJBVCkgc2NvcmUgKz0gNDsKICBpZiAoYWN0aW9uVHlwZSA9PT0gQUNUSU9OX1RZUEVTLlNLSUxMKSBzY29yZSArPSAyOwoKICAvLyBCb29zdCBmcm9tIHJlc3BvbnNlIGNvbnRlbnQKICBjb25zdCBkYW5nZXIgPSAocmF3UmVzcG9uc2UubWF0Y2goL1xiKGF0dGFja3x3b3VuZHxibG9vZHxkZWF0aHxmbGVlfHBvaXNvbnx0cmFwfGRhbmdlcnxzY3JlYW0pXGIvZ2kpfHxbXSkubGVuZ3RoOwogIGNvbnN0IGNhbG0gICA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoc2FmZXxyZXN0fHF1aWV0fHBlYWNlZnVsfGVtcHR5fG5vdGhpbmd8bm9ybWFsKVxiL2dpKXx8W10pLmxlbmd0aDsKICBzY29yZSA9IE1hdGgubWluKDEwLCBNYXRoLm1heCgwLCBzY29yZSArIE1hdGgubWluKGRhbmdlciwgNCkgLSBNYXRoLm1pbihjYWxtLCAyKSkpOwoKICBwYWNpbmdIaXN0b3J5LnB1c2goc2NvcmUpOwogIGlmIChwYWNpbmdIaXN0b3J5Lmxlbmd0aCA+IDEwKSBwYWNpbmdIaXN0b3J5LnNoaWZ0KCk7CgogIC8vIFRyYWNrIGNvbWJhdCBnYXAKICBpZiAoYWN0aW9uVHlwZSA9PT0gQUNUSU9OX1RZUEVTLkNPTUJBVCkgewogICAgdHVybnNTaW5jZUxhc3RDb21iYXQgPSAwOwogIH0gZWxzZSB7CiAgICB0dXJuc1NpbmNlTGFzdENvbWJhdCsrOwogIH0KCiAgLy8gRGV0ZXJtaW5lIHBhY2luZyBwaGFzZQogIGNvbnN0IGF2ZyA9IHBhY2luZ0hpc3RvcnkucmVkdWNlKChhLGIpPT5hK2IsMCkgLyBwYWNpbmdIaXN0b3J5Lmxlbmd0aDsKICBjb25zdCByZWNlbnQgPSBwYWNpbmdIaXN0b3J5LnNsaWNlKC0zKS5yZWR1Y2UoKGEsYik9PmErYiwwKSAvIE1hdGgubWluKDMsIHBhY2luZ0hpc3RvcnkubGVuZ3RoKTsKCiAgaWYgKHR1cm5Db3VudCA8PSAzKSB7CiAgICBjdXJyZW50UGFjaW5nUGhhc2UgPSAnb3BlbmluZyc7CiAgfSBlbHNlIGlmIChyZWNlbnQgPiBhdmcgKyAxLjUpIHsKICAgIGN1cnJlbnRQYWNpbmdQaGFzZSA9ICdwZWFrJzsKICB9IGVsc2UgaWYgKGF2ZyA+PSA2KSB7CiAgICBjdXJyZW50UGFjaW5nUGhhc2UgPSAncmlzaW5nJzsKICB9IGVsc2UgaWYgKGF2ZyA8PSAyICYmIHR1cm5zU2luY2VMYXN0Q29tYmF0ID4gNCkgewogICAgY3VycmVudFBhY2luZ1BoYXNlID0gJ3Jlc3QnOwogIH0gZWxzZSBpZiAocmVjZW50IDwgYXZnIC0gMSkgewogICAgY3VycmVudFBhY2luZ1BoYXNlID0gJ2ZhbGxpbmcnOwogIH0gZWxzZSB7CiAgICBjdXJyZW50UGFjaW5nUGhhc2UgPSAnYnVpbGRpbmcnOwogIH0KfQoKZnVuY3Rpb24gYnVpbGRDb21iYXRCbG9jaygpIHsKICBpZiAoIWluQ29tYmF0KSByZXR1cm4gJyc7CiAgY29uc3QgbGluZXMgPSBbXTsKICBsaW5lcy5wdXNoKCcgQ09NQkFUIC0tIFJvdW5kICcgKyBjb21iYXRTdGF0ZS5yb3VuZCArICcgJyk7CiAgbGluZXMucHVzaCgnT1NFIEdST1VQIElOSVRJQVRJVkU6IFBhcnR5IGQ2PScgKyBjb21iYXRTdGF0ZS5wYXJ0eUluaXQgKwogICAgJyB2cyBNb25zdGVycyBkNj0nICsgY29tYmF0U3RhdGUubW9uc3RlckluaXQgKwogICAgKGNvbWJhdFN0YXRlLnBhcnR5QWN0c0ZpcnN0ID8gJyAtLSBQQVJUWSBhY3RzIGZpcnN0IHRoaXMgcm91bmQnIDogJyAtLSBNT05TVEVSUyBhY3QgZmlyc3QgdGhpcyByb3VuZCcpKTsKCiAgY29uc3QgcGFydHlTaWRlID0gY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZpbHRlcihjID0+IGMuaXNQbGF5ZXIgJiYgIWMuZGVhZCAmJiAhYy5mbGVkKTsKICBjb25zdCBtb25zdGVyU2lkZSA9IGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5maWx0ZXIoYyA9PiAhYy5pc1BsYXllciAmJiAhYy5kZWFkICYmICFjLmZsZWQpOwoKICBpZiAocGFydHlTaWRlLmxlbmd0aCkgewogICAgbGluZXMucHVzaCgnUGFydHk6ICcgKyBwYXJ0eVNpZGUubWFwKGMgPT4gYy5uYW1lICsgJyBIUDonICsgYy5ocCArICcvJyArIGMubWF4SHAgKyAnIEFDOicgKyBjLmFjKS5qb2luKCcgfCAnKSk7CiAgfQogIGlmIChtb25zdGVyU2lkZS5sZW5ndGgpIHsKICAgIGxpbmVzLnB1c2goJ0VuZW1pZXM6ICcgKyBtb25zdGVyU2lkZS5tYXAoYyA9PiBjLm5hbWUgKyAnIEhQOn4nICsgYy5ocCArICcgQUM6JyArIGMuYWMgKyAnIChIRCAnICsgYy5oZCArICcpJykuam9pbignIHwgJykpOwogIH0KCiAgY29uc3QgZGVhZCA9IGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5maWx0ZXIoYyA9PiBjLmRlYWQpOwogIGNvbnN0IGZsZWQgPSBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZmlsdGVyKGMgPT4gYy5mbGVkKTsKICBpZiAoZGVhZC5sZW5ndGgpIGxpbmVzLnB1c2goJ0Rvd246ICcgKyBkZWFkLm1hcChjID0+IGMubmFtZSkuam9pbignLCAnKSk7CiAgaWYgKGZsZWQubGVuZ3RoKSBsaW5lcy5wdXNoKCdGbGVkOiAnICsgZmxlZC5tYXAoYyA9PiBjLm5hbWUpLmpvaW4oJywgJykpOwoKICBsaW5lcy5wdXNoKCcnKTsKICBsaW5lcy5wdXNoKCdPU0UgQ09NQkFUIFJVTEVTIFRISVMgUk9VTkQ6Jyk7CiAgbGluZXMucHVzaCgnMS4gUmUtcm9sbCBncm91cCBpbml0aWF0aXZlIGVhY2ggcm91bmQgKGQ2IHBlciBzaWRlKScpOwogIGxpbmVzLnB1c2goJzIuIFdpbm5pbmcgc2lkZSBBTEwgYWN0IGJlZm9yZSBsb3Npbmcgc2lkZSBhY3RzJyk7CiAgbGluZXMucHVzaCgnMy4gQXR0YWNrOiBkMjAgKyBTVFIgbW9kIChtZWxlZSkgb3IgREVYIG1vZCAocmFuZ2VkKSAtLSBoaXQgaWYgdG90YWwgbWVldHMvYmVhdHMgVEhBQzAgdGFyZ2V0IGZvciB0aGF0IEFDJyk7CiAgbGluZXMucHVzaCgnNC4gRGFtYWdlOiB3ZWFwb24gZGllICsgU1RSIG1vZCAobWVsZWUgb25seSksIG1pbmltdW0gMScpOwogIGxpbmVzLnB1c2goJzUuIFNob3cgQUxMIHJvbGxzOiBbZDYgaW5pdGlhdGl2ZV0sIFtkMjAgYXR0YWNrXSwgW2RhbWFnZSBkaWNlXScpOwogIGxpbmVzLnB1c2goJzYuIE1vcmFsZTogY2hlY2sgMmQ2IHZzIG1vcmFsZSBzY29yZSB3aGVuIG1vbnN0ZXIgbG9zZXMgaGFsZiBIUCBvciBsZWFkZXIgZGllcycpOwogIHJldHVybiBsaW5lcy5qb2luKCdcbicpOwp9CgpmdW5jdGlvbiBidWlsZENvbnNlcXVlbmNlQmxvY2soKSB7CiAgaWYgKCFwZW5kaW5nQ29uc2VxdWVuY2VzLmxlbmd0aCkgcmV0dXJuICcnOwogIGNvbnN0IGxpbmVzID0gWydDT05TRVFVRU5DRSAtLSB3ZWF2ZSB0aGlzIG5hdHVyYWxseSBpbnRvIHRoZSBzY2VuZSB3aXRob3V0IGFubm91bmNpbmcgaXQgZGlyZWN0bHk6J107CiAgcGVuZGluZ0NvbnNlcXVlbmNlcy5mb3JFYWNoKGMgPT4gbGluZXMucHVzaCgnICAnICsgYy5kZXNjcmlwdGlvbikpOwogIHJldHVybiBsaW5lcy5qb2luKCdcbicpOwp9CgpmdW5jdGlvbiBjaGVja0NvbnNlcXVlbmNlcygpIHsKICBwZW5kaW5nQ29uc2VxdWVuY2VzID0gW107CiAgY29uc2VxdWVuY2VzLmZvckVhY2goYyA9PiB7CiAgICBpZiAoIWMuaW5qZWN0ZWQgJiYgdHVybkNvdW50ID49IGMuZHVlX2F0X3R1cm4pIHsKICAgICAgcGVuZGluZ0NvbnNlcXVlbmNlcy5wdXNoKGMpOwogICAgICAvLyBSZS1wbGFudCByZXBlYXRpbmcgZXZlbnRzCiAgICAgIGlmIChjLnJlcGVhdF9ldmVyeSkgewogICAgICAgIGMuZHVlX2F0X3R1cm4gPSB0dXJuQ291bnQgKyBjLnJlcGVhdF9ldmVyeTsKICAgICAgICBjLmluamVjdGVkID0gZmFsc2U7CiAgICAgIH0gZWxzZSB7CiAgICAgICAgYy5pbmplY3RlZCA9IHRydWU7CiAgICAgIH0KICAgIH0KICB9KTsKICAvLyBDbGVhbiB1cCBub24tcmVwZWF0aW5nIGluamVjdGVkIGNvbnNlcXVlbmNlcyBvbGRlciB0aGFuIDEwIHR1cm5zCiAgaWYgKGNvbnNlcXVlbmNlcy5sZW5ndGggPiA0MCkgewogICAgY29uc2VxdWVuY2VzID0gY29uc2VxdWVuY2VzLmZpbHRlcihjID0+CiAgICAgIGMucmVwZWF0X2V2ZXJ5IHx8ICFjLmluamVjdGVkIHx8IHR1cm5Db3VudCAtIGMuZHVlX2F0X3R1cm4gPCAxMAogICAgKTsKICB9Cn0KCmZ1bmN0aW9uIGV4dHJhY3RDb25zZXF1ZW5jZXMocmF3UmVzcG9uc2UsIGFjdGlvblR5cGUpIHsKICAvLyBPbmx5IHBsYW50IGEgY29uc2VxdWVuY2UgaWYgd2UgaGF2ZW4ndCBhbHJlYWR5IHBsYW50ZWQgdGhlIHNhbWUgdHlwZSByZWNlbnRseQogIGNvbnN0IGhhc1JlY2VudCA9ICh0eXBlKSA9PiBjb25zZXF1ZW5jZXMuc29tZShjID0+CiAgICBjLmV2ZW50ID09PSB0eXBlICYmICh0dXJuQ291bnQgLSAoYy5kdWVfYXRfdHVybiAtIDgpKSA8IDYKICApOwoKICBjb25zdCByID0gcmF3UmVzcG9uc2UudG9Mb3dlckNhc2UoKTsKCiAgLy8gTG91ZCBub2lzZSAtLSBvbmx5IG91dHNpZGUgY29tYmF0IChjb21iYXQgbm9pc2UgaXMgZXhwZWN0ZWQpCiAgLy8gTXVzdCBiZSBhIGRlbGliZXJhdGUgbG91ZCBhY3Rpb24sIG5vdCBpbmNpZGVudGFsIGRlc2NyaXB0aW9uCiAgaWYgKCFpbkNvbWJhdCAmJiAhaGFzUmVjZW50KCdub2lzZV9hbGVydCcpKSB7CiAgICBjb25zdCBsb3VkQWN0aW9uID0gL1xiKHNob3V0cz98c2NyZWFtcz98Y3Jhc2hlcz98ZXhwbG9zaW9ucz98YmFuZ3M/fGFsYXJtcz8gKHNvdW5kcz98cmluZ3M/fHRyaWdnZXJlZCkpXGIvLnRlc3Qocik7CiAgICBpZiAobG91ZEFjdGlvbikgewogICAgICBwbGFudENvbnNlcXVlbmNlKCdub2lzZV9hbGVydCcsIDIgKyBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkqMyksCiAgICAgICAgJ1RoZSBlYXJsaWVyIGNvbW1vdGlvbiBoYXMgZHJhd24gYXR0ZW50aW9uIC0tIHNvbWV0aGluZyBzdGlycyBpbiB0aGUgcGFzc2FnZXMgbmVhcmJ5LicpOwogICAgfQogIH0KCiAgLy8gQm9keSBsZWZ0IGluIGNvcnJpZG9yIC0tIG9ubHkgd2hlbiBib2R5ICsgc3BlY2lmaWMgbG9jYXRpb24gd29yZHMgY28tb2NjdXIKICBpZiAoIWhhc1JlY2VudCgnYm9keV9mb3VuZCcpKSB7CiAgICBjb25zdCBib2R5TGVmdCA9IC9cYihib2R5fGNvcnBzZXxyZW1haW5zP3xjYXJjYXNzKVxiLy50ZXN0KHIpCiAgICAgICYmIC9cYihjb3JyaWRvcnxoYWxsd2F5fHBhc3NhZ2V8Zmxvb3J8ZG9vcndheXxsYW5kaW5nKVxiLy50ZXN0KHIpCiAgICAgICYmIC9cYihsZWF2ZXxsZWZ0fGRyYWd8ZHVtcHxwdXNofGxpZXM/fHNsdW1wZWQ/KVxiLy50ZXN0KHIpOwogICAgaWYgKGJvZHlMZWZ0KSB7CiAgICAgIHBsYW50Q29uc2VxdWVuY2UoJ2JvZHlfZm91bmQnLCA0ICsgTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKjQpLAogICAgICAgICdUaGUgYm9keSBsZWZ0IGluIHRoZSBwYXNzYWdlIGhhcyBiZWVuIGZvdW5kIC0tIHdvcmQgaXMgc3ByZWFkaW5nIHRocm91Z2ggdGhlIGR1bmdlb24uJyk7CiAgICB9CiAgfQoKICAvLyBGaXJlIHRoYXQgaXMgc3ByZWFkaW5nIChub3QgYSB0b3JjaCBiZWluZyBsaXQpCiAgaWYgKCFoYXNSZWNlbnQoJ2ZpcmVfc3ByZWFkcycpKSB7CiAgICBjb25zdCBmaXJlQWN0ID0gL1xiKHNldChzKT8gKGEpP2ZpcmV8aWduaXRlW3NkXT98dG9yY2goZXN8ZWQpP3xidXJuKHN8aW5nfGVkKSlcYi8udGVzdChyKQogICAgICAmJiAhL1xiKHRvcmNoIGJ1cm5zP3x0b3JjaGxpZ2h0fGxhbnRlcm58Y2FuZGxlKVxiLy50ZXN0KHIpOwogICAgaWYgKGZpcmVBY3QpIHsKICAgICAgcGxhbnRDb25zZXF1ZW5jZSgnZmlyZV9zcHJlYWRzJywgMywKICAgICAgICAnVGhlIGZpcmUgc2V0IGVhcmxpZXIgaXMgc3ByZWFkaW5nIC0tIHNtb2tlIGRyaWZ0cyB0aHJvdWdoIHRoZSBhZGpvaW5pbmcgcGFzc2FnZXMuJyk7CiAgICB9CiAgfQoKICAvLyBFbmVteSB0aGF0IHN1Y2Nlc3NmdWxseSBmbGVkIChub3QgZHJpdmVuIGJhY2ssIGJ1dCBhY3R1YWxseSBlc2NhcGVkKQogIGlmICghaGFzUmVjZW50KCdlbmVteV9yZXR1cm5zJykpIHsKICAgIGNvbnN0IGVuZW15RmxlZCA9IC9cYihmbGVlcz98ZmxlZHxlc2NhcGVzP3xlc2NhcGVkfHJ1bnM/IChhd2F5fG9mZil8cmV0cmVhdHM/fHJldHJlYXRlZClcYi8udGVzdChyKQogICAgICAmJiAvXGIoZ29ibGlufG9yY3xndWFyZHxzb2xkaWVyfGJhbmRpdHxjdWx0aXN0fG1vbnN0ZXJ8Y3JlYXR1cmV8ZW5lbXl8Zm9lKVxiLy50ZXN0KHIpOwogICAgaWYgKGVuZW15RmxlZCkgewogICAgICBwbGFudENvbnNlcXVlbmNlKCdlbmVteV9yZXR1cm5zJywgNSArIE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSo1KSwKICAgICAgICAnVGhlIGNyZWF0dXJlIHRoYXQgZmxlZCBlYXJsaWVyIGhhcyByZXR1cm5lZCB3aXRoIGFpZCAtLSBpdCByZW1lbWJlcmVkIHRoZSBwYXJ0eS4nKTsKICAgIH0KICB9CgogIC8vIERlbGliZXJhdGVseSBicm9rZW4gZG9vciAoZm9yY2VkLCBub3Qgb3BlbmVkKQogIGlmICghaGFzUmVjZW50KCdicm9rZW5fZG9vcicpKSB7CiAgICBjb25zdCBkb29yQnJva2VuID0gL1xiKHNtYXNoKGVkfGVzKT98YmF0dGVyKGVkfHMpP3xiYXNoKGVkfGVzKT98YnJlYWtbc10/IChkb3dufHRocm91Z2gpfGZvcmNlZD8gb3BlbnxraWNrKGVkfHMpPyAoZG93bnxvcGVuKSlcYi8udGVzdChyKQogICAgICAmJiAvXGIoZG9vcnxnYXRlfHBvcnRjdWxsaXN8YmFycmljYWRlKVxiLy50ZXN0KHIpOwogICAgaWYgKGRvb3JCcm9rZW4pIHsKICAgICAgcGxhbnRDb25zZXF1ZW5jZSgnYnJva2VuX2Rvb3InLCA4ICsgTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKjQpLAogICAgICAgICdUaGUgYnJva2VuIGRvb3IgcHJvdmlkZXMgbm8gYmFycmllciBub3cgLS0gc29tZXRoaW5nIGZyb20gZnVydGhlciBpbiBoYXMgbm90aWNlZCB0aGUgb3BlbiBwYXNzYWdlLicpOwogICAgfQogIH0KfQoKZnVuY3Rpb24gZGV0ZWN0RW5lbWllc0Zyb21SZXNwb25zZShyZXNwb25zZVRleHQpIHsKICBjb25zdCBlbmVtaWVzID0gW107CiAgLy8gTG9vayBmb3IgbW9uc3RlciBzdGF0cyBpbiB0aGUgZm9ybWF0IHRoZSBHTSB1c2VzCiAgLy8gZS5nLiAiMyBHb2JsaW5zIChIRCAxLCBBQyA3LCBocCA0IGVhY2gpIgogIGNvbnN0IHN0YXRQYXQgPSAvKFxkKyk/XHMqKFtBLVpdW2Etel0rKD86XHNbQS1aXVthLXpdKyk/KVxzKig/OlwoW14pXSpIRFxzKihcZCspW14pXSpBQ1xzKihcZCspW14pXSpcKSk/L2c7CiAgbGV0IG07CiAgd2hpbGUgKChtID0gc3RhdFBhdC5leGVjKHJlc3BvbnNlVGV4dCkpICE9PSBudWxsKSB7CiAgICBjb25zdCBjb3VudCA9IHBhcnNlSW50KG1bMV0pIHx8IDE7CiAgICBjb25zdCBuYW1lID0gbVsyXTsKICAgIGNvbnN0IGhkID0gcGFyc2VJbnQobVszXSkgfHwgMTsKICAgIGNvbnN0IGFjID0gcGFyc2VJbnQobVs0XSkgfHwgOTsKICAgIGlmIChuYW1lICYmICFbJ1RoZScsICdZb3UnLCAnWW91cicsICdIZScsICdTaGUnLCAnVGhleSddLmluY2x1ZGVzKG5hbWUpKSB7CiAgICAgIGZvciAobGV0IGkgPSAwOyBpIDwgTWF0aC5taW4oY291bnQsIDYpOyBpKyspIHsKICAgICAgICBlbmVtaWVzLnB1c2goewogICAgICAgICAgbmFtZTogY291bnQgPiAxID8gbmFtZSArICcgJyArIChpKzEpIDogbmFtZSwKICAgICAgICAgIGhkLCBhYywKICAgICAgICAgIGhwOiBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkgKiAoaGQgKiA2KSkgKyBoZCwgLy8geGQ2CiAgICAgICAgICBtb3JhbGU6IDcsCiAgICAgICAgfSk7CiAgICAgIH0KICAgIH0KICB9CiAgcmV0dXJuIGVuZW1pZXMuc2xpY2UoMCwgOCk7IC8vIGNhcCBhdCA4IGNvbWJhdGFudHMKfQoKZnVuY3Rpb24gc3RhcnRDb21iYXQoZW5lbWllc0Zyb21HTSkgewogIGlmIChpbkNvbWJhdCkgcmV0dXJuOyAvLyBhbHJlYWR5IGluIGNvbWJhdAogIGluQ29tYmF0ID0gdHJ1ZTsKICBjb21iYXRTdGF0ZS5yb3VuZCA9IDE7CiAgY29tYmF0U3RhdGUubGFzdFJvdW5kU3VtbWFyeSA9ICcnOwoKICAvLyBPU0UgR1JPVVAgSU5JVElBVElWRTogb25lIGQ2IHBlciBzaWRlCiAgY29uc3QgcGFydHlJbml0ID0gTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpICogNikgKyAxOwogIGNvbnN0IG1vbnN0ZXJJbml0ID0gTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpICogNikgKyAxOwogIC8vIFRpZXM6IHJlLXJvbGwgKG9yIHNpbXVsdGFuZW91cyAtLSBPU0UgYWxsb3dzIGJvdGg7IHdlIHVzZSBzaW11bHRhbmVvdXMpCiAgY29uc3QgcGFydHlBY3RzRmlyc3QgPSBwYXJ0eUluaXQgPj0gbW9uc3RlckluaXQ7CgogIC8vIEJ1aWxkIHBhcnR5IHNpZGUKICBjb25zdCBwYXJ0eVNpZGUgPSBPYmplY3QuZW50cmllcyhwYXJ0eVBDcykubWFwKChbcG5hbWUsIHBdKSA9PiAoewogICAgbmFtZTogcC5uYW1lLCBwbGF5ZXJOYW1lOiBwbmFtZSwgaXNQbGF5ZXI6IHRydWUsCiAgICBocDogcC5ocCwgbWF4SHA6IHAubWF4SHAgfHwgcC5ocCwgYWM6IHAuYWMsCiAgICBmbGVkOiBmYWxzZSwgZGVhZDogZmFsc2UsIHNpZGU6ICdwYXJ0eScsCiAgfSkpOwoKICAvLyBCdWlsZCBtb25zdGVyIHNpZGUgZnJvbSB3aGF0ZXZlciB0aGUgR00gdG9sZCB1cwogIC8vIElmIG5vIGVuZW15IGRhdGEgYXZhaWxhYmxlLCBjcmVhdGUgYSBwbGFjZWhvbGRlcgogIGNvbnN0IG1vbnN0ZXJTaWRlID0gKGVuZW1pZXNGcm9tR00gfHwgW10pLm1hcChlID0+ICh7CiAgICBuYW1lOiBlLm5hbWUgfHwgJ0VuZW15JywKICAgIGlzUGxheWVyOiBmYWxzZSwKICAgIGhwOiBlLmhwIHx8IE1hdGgubWF4KDEsIChlLmhkIHx8IDEpICogNCksIC8vIHVzZSBhdmVyYWdlIEhQIChIRMOXNCkgaWYgbm90IGdpdmVuCiAgICBtYXhIcDogZS5ocCB8fCBNYXRoLm1heCgxLCAoZS5oZCB8fCAxKSAqIDQpLAogICAgYWM6IHBhcnNlSW50KGUuYWMpIHx8IDksCiAgICBtb3JhbGU6IHBhcnNlSW50KGUubW9yYWxlKSB8fCA3LAogICAgaGQ6IGUuaGQgfHwgMSwKICAgIGZsZWQ6IGZhbHNlLCBkZWFkOiBmYWxzZSwgc2lkZTogJ21vbnN0ZXInLAogIH0pKTsKCiAgY29tYmF0U3RhdGUucGFydHlJbml0ID0gcGFydHlJbml0OwogIGNvbWJhdFN0YXRlLm1vbnN0ZXJJbml0ID0gbW9uc3RlckluaXQ7CiAgY29tYmF0U3RhdGUucGFydHlBY3RzRmlyc3QgPSBwYXJ0eUFjdHNGaXJzdDsKCiAgLy8gSW5pdGlhdGl2ZSBvcmRlcjogd2lubmluZyBzaWRlIGZpcnN0LCB0aGVuIGxvc2luZyBzaWRlCiAgLy8gV2l0aGluIGVhY2ggc2lkZSwgcGxheWVycyBjaG9vc2Ugb3JkZXIgKGxlZnQgdG8gcmlnaHQgaW4gcGFydHlQQ3MpCiAgaWYgKHBhcnR5QWN0c0ZpcnN0KSB7CiAgICBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIgPSBbLi4ucGFydHlTaWRlLCAuLi5tb25zdGVyU2lkZV07CiAgfSBlbHNlIHsKICAgIGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlciA9IFsuLi5tb25zdGVyU2lkZSwgLi4ucGFydHlTaWRlXTsKICB9CgogIHR1cm5zU2luY2VMYXN0Q29tYmF0ID0gMDsKICBjb25zb2xlLmxvZygnW0NvbWJhdF0gU3RhcnRlZC4gUGFydHkgaW5pdDonLCBwYXJ0eUluaXQsICdNb25zdGVyIGluaXQ6JywgbW9uc3RlckluaXQsCiAgICBwYXJ0eUFjdHNGaXJzdCA/ICctLSBQYXJ0eSBhY3RzIGZpcnN0JyA6ICctLSBNb25zdGVycyBhY3QgZmlyc3QnKTsKfQoKZnVuY3Rpb24gZW5kQ29tYmF0KHJlc3VsdCkgewogIGluQ29tYmF0ID0gZmFsc2U7CiAgY29tYmF0U3RhdGUubGFzdFJvdW5kU3VtbWFyeSA9IHJlc3VsdCA9PT0gJ3ZpY3RvcnknCiAgICA/ICdDb21iYXQgZW5kZWQgLS0gcGFydHkgdmljdG9yaW91cy4nCiAgICA6ICdDb21iYXQgZW5kZWQgLS0gcGFydHkgZGVmZWF0ZWQgb3IgZmxlZC4nOwogIGFkdmFuY2VEdW5nZW9uVHVybigxKTsgLy8gT1NFOiBjb21iYXQgdGFrZXMgYXBwcm94aW1hdGVseSAxIGR1bmdlb24gdHVybgogIGNvbnNvbGUubG9nKCdbQ29tYmF0XSBFbmRlZDonLCByZXN1bHQpOwp9CgpmdW5jdGlvbiB1cGRhdGVDb21iYXRTdGF0ZShncykgewogIGlmICghaW5Db21iYXQpIHJldHVybjsKCiAgLy8gVXBkYXRlIHBsYXllciBIUCBmcm9tIGNvbmZpcm1lZCBnYW1lIHN0YXRlCiAgaWYgKGdzKSB7CiAgICBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZm9yRWFjaChjID0+IHsKICAgICAgaWYgKCFjLmlzUGxheWVyKSByZXR1cm47CiAgICAgIGlmIChjLnBsYXllck5hbWUgPT09IHBsYXllck5hbWUgJiYgZ3MuaHAgIT09IHVuZGVmaW5lZCkgewogICAgICAgIGMuaHAgPSBncy5ocDsKICAgICAgfQogICAgICBpZiAoZ3MucGFydHkgJiYgZ3MucGFydHlbYy5wbGF5ZXJOYW1lXSkgewogICAgICAgIGMuaHAgPSBncy5wYXJ0eVtjLnBsYXllck5hbWVdLmhwOwogICAgICB9CiAgICAgIGlmIChjLmhwIDw9IDApIGMuZGVhZCA9IHRydWU7CiAgICB9KTsKICB9CgogIGNvbWJhdFN0YXRlLnJvdW5kKys7CgogIC8vIENoZWNrIGVuZCBjb25kaXRpb25zCiAgY29uc3QgZW5lbWllc0FsaXZlID0gY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZpbHRlcihjID0+ICFjLmlzUGxheWVyICYmICFjLmRlYWQgJiYgIWMuZmxlZCk7CiAgY29uc3QgcGxheWVyc0FsaXZlID0gY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZpbHRlcihjID0+IGMuaXNQbGF5ZXIgJiYgIWMuZGVhZCk7CgogIGlmIChlbmVtaWVzQWxpdmUubGVuZ3RoID09PSAwKSB7CiAgICBlbmRDb21iYXQoJ3ZpY3RvcnknKTsKICB9IGVsc2UgaWYgKHBsYXllcnNBbGl2ZS5sZW5ndGggPT09IDApIHsKICAgIGVuZENvbWJhdCgnZGVmZWF0Jyk7CiAgfQp9Cgphc3luYyBmdW5jdGlvbiBjYWxsQUkodXNlclRleHQsIHNob3dVc2VyPXRydWUsIG9vYz1mYWxzZSkgewogIGlmIChidXN5KSB7IGNvbnNvbGUubG9nKCdbY2FsbEFJXSBidXN5LCBpZ25vcmluZyBjYWxsJyk7IHJldHVybjsgfQogIGJ1c3kgPSB0cnVlOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpLmRpc2FibGVkID0gdHJ1ZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJykuZGlzYWJsZWQgPSB0cnVlOwoKICAvLyBPT0MgL0dNIHF1ZXN0aW9uIC0tIGJ5cGFzcyB0aGUgZnVsbCBuYXJyYXRpdmUgcHJvbXB0IGVudGlyZWx5CiAgLy8gSnVzdCBhbnN3ZXIgdGhlIHJ1bGVzIHF1ZXN0aW9uIGRpcmVjdGx5IGFuZCByZXR1cm4KICBpZiAob29jKSB7CiAgICBjb25zdCB0aGlua0VsID0gYWRkRW50cnlSYXcoJ1RoZSBHTSBjb25zaWRlcnMgeW91ciBxdWVzdGlvbi4uLicsICd0aGlua2luZycsICdfX2dtX18nKTsKICAgIHRyeSB7CiAgICAgIGNvbnN0IHJlc3AgPSBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvYWknLCB7CiAgICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgICAgIGFwaV9rZXk6IGFwaUtleSwKICAgICAgICAgIHN5c3RlbTogJ1lvdSBhcmUgYSBrbm93bGVkZ2VhYmxlIEdhbWUgTWFzdGVyIGZvciBhIHRhYmxldG9wIFJQRyB1c2luZyBPU0UgQWR2YW5jZWQgRmFudGFzeSBydWxlcy4gJyArCiAgICAgICAgICAgICAgICAgICdUaGUgcGxheWVyIGlzIGFza2luZyBhbiBPVVQtT0YtQ0hBUkFDVEVSIHJ1bGVzIHF1ZXN0aW9uLiAnICsKICAgICAgICAgICAgICAgICAgJ0Fuc3dlciBjbGVhcmx5IGFuZCBjb25jaXNlbHkgaW4gMi00IHNlbnRlbmNlcy4gJyArCiAgICAgICAgICAgICAgICAgICdEbyBOT1QgbmFycmF0ZSB0aGUgc2NlbmUuIERvIE5PVCBkZXNjcmliZSBjaGFyYWN0ZXIgYWN0aW9ucy4gJyArCiAgICAgICAgICAgICAgICAgICdKdXN0IGFuc3dlciB0aGUgcXVlc3Rpb24gZGlyZWN0bHkgYXMgaWYgZXhwbGFpbmluZyB0aGUgcnVsZXMgdG8gdGhlIHBsYXllci4gJyArCiAgICAgICAgICAgICAgICAgICdCZWdpbiB5b3VyIGFuc3dlciB3aXRoICJHTToiIHRvIG1ha2UgaXQgY2xlYXIgdGhpcyBpcyBhbiBvdXQtb2YtY2hhcmFjdGVyIHJlc3BvbnNlLicsCiAgICAgICAgICBtZXNzYWdlczogW3tyb2xlOiAndXNlcicsIGNvbnRlbnQ6IHVzZXJUZXh0fV0KICAgICAgICB9KQogICAgICB9KTsKICAgICAgaWYgKHRoaW5rRWwgJiYgdGhpbmtFbC5yZW1vdmUpIHRoaW5rRWwucmVtb3ZlKCk7CiAgICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKICAgICAgY29uc3QgYW5zd2VyID0gZGF0YS5jb250ZW50IHx8ICdJIGNhbm5vdCBhbnN3ZXIgdGhhdCByaWdodCBub3cuJzsKICAgICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjojN2E5YTdhO2ZvbnQtc3R5bGU6aXRhbGljOyI+JyArIGFuc3dlciArICc8L3NwYW4+JywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgIH0gY2F0Y2goZSkgewogICAgICBpZiAodGhpbmtFbCAmJiB0aGlua0VsLnJlbW92ZSkgdGhpbmtFbC5yZW1vdmUoKTsKICAgICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjojN2E5YTdhIj5HTTogJyArIHVzZXJUZXh0LnJlcGxhY2UoJ1tPVVQgT0YgQ0hBUkFDVEVSIC0tICcgKyBwYy5uYW1lICsgJyBhc2tzIHRoZSBHTV06ICcsICcnKSArICcgLS0gKGNvdWxkIG5vdCByZWFjaCBBSSk8L3NwYW4+JywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgIH0KICAgIGJ1c3kgPSBmYWxzZTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpLmRpc2FibGVkID0gZmFsc2U7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJykuZGlzYWJsZWQgPSBmYWxzZTsKICAgIHJldHVybjsKICB9CgogIC8vIEd1YXJkOiBjYXRjaCBtaXNzaW5nIHN5c3RlbSBwcm9tcHQgKGNoYXJhY3RlciBjcmVhdGlvbiBkaWRuJ3QgZmluaXNoKQogIGNvbnNvbGUubG9nKCdbQUldIHN5c3RlbVByb21wdCBsZW5ndGg6Jywgc3lzdGVtUHJvbXB0ID8gc3lzdGVtUHJvbXB0Lmxlbmd0aCA6IDAsICd8IHVzZU9sbGFtYTonLCB1c2VPbGxhbWEsICd8IG1vZHVsZVRleHQ6JywgbW9kdWxlVGV4dCA/IG1vZHVsZVRleHQubGVuZ3RoIDogMCk7CiAgaWYgKCFzeXN0ZW1Qcm9tcHQpIHsKICAgIHN5c3RlbVByb21wdCA9IGJ1aWxkU3lzdGVtUHJvbXB0KCk7IC8vIHRyeSB0byByZWJ1aWxkCiAgICBpZiAoIXN5c3RlbVByb21wdCkgewogICAgICBhZGRFbnRyeVJhdygnISBObyBhZHZlbnR1cmUgbG9hZGVkIC0tIHBsZWFzZSBnbyBiYWNrIGFuZCBzZWxlY3QgYSBtb2R1bGUuJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgYnVzeT1mYWxzZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJykuZGlzYWJsZWQ9ZmFsc2U7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKS5kaXNhYmxlZD1mYWxzZTsKICAgICAgcmV0dXJuOwogICAgfQogIH0KCiAgaWYgKHNob3dVc2VyKSB7CiAgICBjb25zdCBodG1sID0gZm10KHVzZXJUZXh0KTsKICAgIGFkZEVudHJ5UmF3KGh0bWwsICdwbGF5ZXItbXNnJywgcGxheWVyTmFtZSk7CiAgICBwdXNoTWVzc2FnZShodG1sLCAncGxheWVyLW1zZycsIHBsYXllck5hbWUpOwogIH0KCiAgdHVybkNvdW50Kys7CgogIC8vIFN5c3RlbSA4OiBDbGFzc2lmeSBwbGF5ZXIgYWN0aW9uCiAgY29uc3QgYWN0aW9uVHlwZSA9IGNsYXNzaWZ5UGxheWVyQWN0aW9uKHVzZXJUZXh0KTsKICBjb25zdCBhY3Rpb25HdWlkYW5jZSA9IGdldEFjdGlvbkd1aWRhbmNlKGFjdGlvblR5cGUpOwoKICAvLyBTeXN0ZW0gNjogQWR2YW5jZSBkdW5nZW9uIHR1cm4gcGVyIE9TRSB0dXJuIHN0cnVjdHVyZQogIC8vIENvbWJhdCwgbW92ZW1lbnQsIHNlYXJjaGluZywgaXRlbSB1c2UsIHNraWxsIHVzZSA9IDEgdHVybiBlYWNoCiAgLy8gU29jaWFsIGludGVyYWN0aW9ucyA9IG5vIHR1cm4gYWR2YW5jZW1lbnQgKGluc3RhbnRhbmVvdXMpCiAgaWYgKGFjdGlvblR5cGUgIT09IEFDVElPTl9UWVBFUy5TT0NJQUwpIHsKICAgIGFkdmFuY2VEdW5nZW9uVHVybigxKTsKICB9CiAgLy8gUmVzdCBpbiBkdW5nZW9uID0gMSB0dXJuLCBubyBIUCByZWNvdmVyeSAoT1NFIGNvcmUpCiAgaWYgKGFjdGlvblR5cGUgPT09IEFDVElPTl9UWVBFUy5SRVNUKSBoYW5kbGVEdW5nZW9uUmVzdCgpOwoKICAvLyBTeXN0ZW0gNTogU3RhcnQgY29tYmF0IHRyYWNraW5nIGlmIHRoaXMgaXMgdGhlIGZpcnN0IGNvbWJhdCBhY3Rpb24KICBpZiAoYWN0aW9uVHlwZSA9PT0gQUNUSU9OX1RZUEVTLkNPTUJBVCAmJiAhaW5Db21iYXQpIHsKICAgIC8vIFRyeSB0byBleHRyYWN0IGVuZW15IGRhdGEgZnJvbSB0aGUgbW9zdCByZWNlbnQgR00gcmVzcG9uc2UKICAgIGNvbnN0IGxhc3RHTVJlc3BvbnNlID0gaGlzdG9yeS5maWx0ZXIoaCA9PiBoLnJvbGUgPT09ICdhc3Npc3RhbnQnKS5zbGljZSgtMSlbMF0/LmNvbnRlbnQgfHwgJyc7CiAgICBjb25zdCBlbmVtaWVzID0gZGV0ZWN0RW5lbWllc0Zyb21SZXNwb25zZShsYXN0R01SZXNwb25zZSk7CiAgICBzdGFydENvbWJhdChlbmVtaWVzKTsKICB9CiAgLy8gRW5kIGNvbWJhdCBpZiBwbGF5ZXIgaXMgZmxlZWluZyBvciBjb21iYXQgZW5kcwogIGlmIChpbkNvbWJhdCAmJiAvXGIoZmxlZXxydW4gYXdheXxlc2NhcGV8cmV0cmVhdHx3ZSBydW58bGV0J3MgcnVuKVxiL2kudGVzdCh1c2VyVGV4dCkpIHsKICAgIGVuZENvbWJhdCgnZmxlZCcpOwogIH0KCiAgLy8gU3lzdGVtIDM6IENoZWNrIGlmIGFueSBjb25zZXF1ZW5jZXMgYXJlIGR1ZQogIGNoZWNrQ29uc2VxdWVuY2VzKCk7CgogIC8vIEZpeCAxOiBSb2xsaW5nIHN1bW1hcnkKICBpZiAodXNlT2xsYW1hICYmIHR1cm5Db3VudCA+IDAgJiYgdHVybkNvdW50ICUgU1VNTUFSWV9FVkVSWV9OX1RVUk5TID09PSAwICYmIGhpc3RvcnkubGVuZ3RoID49IDYpIHsKICAgIGNvbnN0IHN1bW1hcnlFbCA9IGFkZEVudHJ5UmF3KCdDb25zb2xpZGF0aW5nIG1lbW9yeS4uLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICBhd2FpdCBnZW5lcmF0ZVN1bW1hcnkoKTsKICAgIGlmIChzdW1tYXJ5RWwgJiYgc3VtbWFyeUVsLnJlbW92ZSkgc3VtbWFyeUVsLnJlbW92ZSgpOwogICAgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKICB9CgogIGNvbnN0IHRoaW5rRWwgPSBhZGRFbnRyeVJhdygnVGhlIEdhbWUgTWFzdGVyIGNvbnNpZGVycy4uLicsICd0aGlua2luZycsICdfX2dtX18nKTsKICBoaXN0b3J5LnB1c2goe3JvbGU6J3VzZXInLCBjb250ZW50OiB1c2VyVGV4dH0pOwoKICAvLyBCdWlsZCBmdWxsIGNvbnRleHQgaW5qZWN0aW9uCiAgY29uc3QgbWVtb3J5Q29udGV4dCA9IGJ1aWxkTWVtb3J5Q29udGV4dCgpOwoKICAvLyBTeXN0ZW0gMjogUGFjaW5nIGd1aWRhbmNlCiAgY29uc3QgcGFjaW5nR3VpZGFuY2UgPSBnZXRQYWNpbmdHdWlkYW5jZSgpOwoKICAvLyBTeXN0ZW0gMzogQ29uc2VxdWVuY2UgYmxvY2sKICBjb25zdCBjb25zZXF1ZW5jZUJsb2NrID0gYnVpbGRDb25zZXF1ZW5jZUJsb2NrKCk7CgogIC8vIFN5c3RlbSA1OiBDb21iYXQgYmxvY2sKICBjb25zdCBjb21iYXRCbG9jayA9IGluQ29tYmF0ID8gYnVpbGRDb21iYXRCbG9jaygpIDogJyc7CgogIC8vIFN5c3RlbSA2OiBSZXNvdXJjZSBibG9jawogIGNvbnN0IHJlc291cmNlQmxvY2sgPSBidWlsZFJlc291cmNlQmxvY2soKTsKCiAgLy8gQXNzZW1ibGUgYWxsIGd1aWRhbmNlIGludG8gdGhlIHByb21wdAogIGNvbnN0IGd1aWRhbmNlQmxvY2tzID0gWwogICAgYWN0aW9uR3VpZGFuY2UsCiAgICBwYWNpbmdHdWlkYW5jZSwKICAgIGNvbWJhdEJsb2NrLAogICAgcmVzb3VyY2VCbG9jaywKICAgIGNvbnNlcXVlbmNlQmxvY2ssCiAgXS5maWx0ZXIoQm9vbGVhbikuam9pbignXG5cbicpOwoKICBsZXQgcHJvbXB0V2l0aE1lbW9yeSA9IHN5c3RlbVByb21wdDsKICBpZiAobWVtb3J5Q29udGV4dCkgewogICAgcHJvbXB0V2l0aE1lbW9yeSA9IHByb21wdFdpdGhNZW1vcnkucmVwbGFjZSgnVEhFIE1PRFVMRTonLCAnQ1VSUkVOVCBNRU1PUlkgQ09OVEVYVDonICsgbWVtb3J5Q29udGV4dCArICdcblxuVEhFIE1PRFVMRTonKTsKICB9CiAgaWYgKGd1aWRhbmNlQmxvY2tzKSB7CiAgICBwcm9tcHRXaXRoTWVtb3J5ID0gcHJvbXB0V2l0aE1lbW9yeS5yZXBsYWNlKCdNQU5EQVRPUlkgLS0gYXBwZW5kIHRoaXMgRVhBQ1RMWScsCiAgICAgICdUVVJOIEdVSURBTkNFIChhcHBseSB0byB0aGlzIHNwZWNpZmljIHJlc3BvbnNlKTpcbicgKyBndWlkYW5jZUJsb2NrcyArICdcblxuTUFOREFUT1JZIC0tIGFwcGVuZCB0aGlzIEVYQUNUTFknKTsKICB9CgogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FpJywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgICAgYXBpX2tleTogYXBpS2V5LAogICAgICAgIHN5c3RlbTogcHJvbXB0V2l0aE1lbW9yeSwKICAgICAgICBtZXNzYWdlczogaGlzdG9yeQogICAgICB9KQogICAgfSk7CgogICAgaWYgKHRoaW5rRWwgJiYgdGhpbmtFbC5yZW1vdmUpIHRoaW5rRWwucmVtb3ZlKCk7CgogICAgaWYgKCFyZXNwLm9rKSB7CiAgICAgIGNvbnN0IGVyciA9IGF3YWl0IHJlc3AuanNvbigpLmNhdGNoKCgpPT4oe30pKTsKICAgICAgY29uc3QgbXNnID0gZXJyLmVycm9yIHx8IHJlc3Auc3RhdHVzVGV4dCB8fCAnVW5rbm93biBlcnJvcic7CiAgICAgIGNvbnNvbGUuZXJyb3IoJ1tBSV0gSFRUUCBlcnJvcjonLCByZXNwLnN0YXR1cywgbXNnKTsKICAgICAgYWRkRW50cnlSYXcoJyEgU2VydmVyIGVycm9yICcgKyByZXNwLnN0YXR1cyArICc6ICcgKyBtc2csICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIHVwZGF0ZUFpSW5kaWNhdG9yKCdlcnJvcicsICcnKTsKICAgICAgYnVzeT1mYWxzZTsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJykuZGlzYWJsZWQ9ZmFsc2U7IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKS5kaXNhYmxlZD1mYWxzZTsKICAgICAgcmV0dXJuOwogICAgfQoKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKCiAgICAvLyBDaGVjayBpZiBiYWNrZW5kIHJldHVybmVkIGFuIGVycm9yCiAgICBpZiAoZGF0YS5lcnJvcikgewogICAgICBhZGRFbnRyeVJhdygnRXJyb3I6ICcgKyBkYXRhLmVycm9yLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICB1cGRhdGVBaUluZGljYXRvcignZXJyb3InLCAnJyk7CiAgICAgIGJ1c3k9ZmFsc2U7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpLmRpc2FibGVkPWZhbHNlOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJykuZGlzYWJsZWQ9ZmFsc2U7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBjb25zdCByYXcgPSBkYXRhLmNvbnRlbnQgfHwgJyc7CgogICAgLy8gVXBkYXRlIEFJIGluZGljYXRvciB3aXRoIHdoaWNoIGJhY2tlbmQgcmVzcG9uZGVkCiAgICB1c2VPbGxhbWEgPSAoZGF0YS52aWEgPT09ICdvbGxhbWEnKTsKICAgIHVwZGF0ZUFpSW5kaWNhdG9yKGRhdGEudmlhIHx8ICd1bmtub3duJywgZGF0YS5tb2RlbCB8fCAnJyk7CgogICAgY29uc3QgZ3MgPSBwYXJzZVN0YXRlKHJhdyk7CiAgICBjb25zdCBjbGVhbiA9IHN0cmlwU3RhdGUocmF3KTsKCiAgICBjbGVhbi5zcGxpdCgvXG5cbisvKS5maWx0ZXIocD0+cC50cmltKCkpLmZvckVhY2gocCA9PiB7CiAgICAgIGNvbnN0IGh0bWwgPSBmbXQocC50cmltKCkpOwogICAgICBjb25zdCB0eXBlID0gY2xhc3NpZnlFbnRyeShwKTsKICAgICAgYWRkRW50cnlSYXcoaHRtbCwgdHlwZSwgJ19fZ21fXycpOwogICAgICBwdXNoTWVzc2FnZShodG1sLCB0eXBlLCAnX19nbV9fJyk7CiAgICB9KTsKCiAgICBhcHBseVN0YXRlKGdzKTsKICAgIGhpc3RvcnkucHVzaCh7cm9sZTonYXNzaXN0YW50JywgY29udGVudDpyYXd9KTsKCiAgICAvLyBVcGRhdGUgYWxsIHN5c3RlbXMgZnJvbSByZXNwb25zZQogICAgaWYgKHVzZU9sbGFtYSkgewogICAgICB1cGRhdGVXb3JsZFN0YXRlKHJhdywgZ3MpOwogICAgICBleHRyYWN0QW5kUGluRmFjdHMoY2xlYW4pOwogICAgfQogICAgLy8gU3lzdGVtIDI6IFVwZGF0ZSBwYWNpbmcgKHJ1bnMgZm9yIGJvdGggT2xsYW1hIGFuZCBDbGF1ZGUpCiAgICB1cGRhdGVQYWNpbmcocmF3LCBhY3Rpb25UeXBlKTsKICAgIC8vIFN5c3RlbSAzOiBFeHRyYWN0IG5ldyBjb25zZXF1ZW5jZXMgZnJvbSByZXNwb25zZQogICAgZXh0cmFjdENvbnNlcXVlbmNlcyhyYXcsIGFjdGlvblR5cGUpOwogICAgLy8gU3lzdGVtIDU6IFVwZGF0ZSBjb21iYXQgc3RhdGUgaWYgaW4gY29tYmF0CiAgICBpZiAoaW5Db21iYXQpIHVwZGF0ZUNvbWJhdFN0YXRlKGdzKTsKICAgIC8vIERldGVjdCBjb21iYXQtZW5kaW5nIHBocmFzZXMgaW4gR00gcmVzcG9uc2UgdG8gYXV0by1lbmQgY29tYmF0IHRyYWNrZXIKICAgIGlmIChpbkNvbWJhdCkgewogICAgICBjb25zdCBjb21iYXRPdmVyID0gL1xiKGNvbWJhdCAoZW5kc3xpcyBvdmVyfGNvbmNsdWRlcyl8ZW5lbXkgKGlzIGRlYWR8ZmFsbHN8aXMgc2xhaW58Y29sbGFwc2VzKXxhbGwgZW5lbWllcyAoZGVhZHxkZWZlYXRlZHxzbGFpbnxmbGVkKXxzaWxlbmNlIChyZXR1cm5zfGZhbGxzKXx0aGUgZmlnaHQgKGVuZHN8aXMgb3ZlcikpXGIvaS50ZXN0KGNsZWFuKTsKICAgICAgaWYgKGNvbWJhdE92ZXIpIGVuZENvbWJhdCgndmljdG9yeScpOwogICAgfQoKICAgIGlmIChwYy5ocCA8PSAwKSB7CiAgICAgIGFkZEVudHJ5UmF3KGAke3BjLm5hbWV9IGhhcyBmYWxsZW4uIFRoZSBhZHZlbnR1cmUgZW5kcy5gLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICByZXR1cm47CiAgICB9CiAgfSBjYXRjaChlKSB7CiAgICB0aGlua0VsPy5yZW1vdmUoKTsKICAgIGFkZEVudHJ5UmF3KCdFcnJvcjogJyArIGUubWVzc2FnZSwgJ3N5c3RlbScsICdfX2dtX18nKTsKICB9CiAgYnVzeT1mYWxzZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKS5kaXNhYmxlZD1mYWxzZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJykuZGlzYWJsZWQ9ZmFsc2U7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpLmZvY3VzKCk7Cn0KCmZ1bmN0aW9uIHBsYW50Q29uc2VxdWVuY2UoZXZlbnQsIGR1ZUluVHVybnMsIGRlc2NyaXB0aW9uLCByZXBlYXRpbmc9ZmFsc2UpIHsKICBjb25zZXF1ZW5jZXMucHVzaCh7CiAgICBldmVudCwKICAgIGRlc2NyaXB0aW9uLAogICAgZHVlX2F0X3R1cm46IHR1cm5Db3VudCArIGR1ZUluVHVybnMsCiAgICByZXBlYXRfZXZlcnk6IHJlcGVhdGluZyA/IGR1ZUluVHVybnMgOiBudWxsLAogICAgaW5qZWN0ZWQ6IGZhbHNlLAogIH0pOwogIGNvbnNvbGUubG9nKCdbQ29uc2VxdWVuY2VdIFBsYW50ZWQ6JywgZXZlbnQsICdkdWUgaW4nLCBkdWVJblR1cm5zLCAndHVybnMnICsgKHJlcGVhdGluZyA/ICcgKHJlcGVhdGluZyknIDogJycpKTsKfQoKZnVuY3Rpb24gY29udkxvYWRFeGlzdGluZygpIHsgLyogY29udmVydGVyIHNjcmVlbiAtLSBub3QgdXNlZCBpbiBWNCAqLyB9CgpmdW5jdGlvbiBpbml0Q29udkRyb3AoKSB7IC8qIGNvbnZlcnRlciBzY3JlZW4gLS0gbm90IHVzZWQgaW4gVjQgKi8gfQoKZnVuY3Rpb24gYnVpbGRDbGF1ZGVQcm9tcHQoaXNQYXJ0eSwgcGFydHlMaXN0KSB7CiAgY29uc3Qgc3RhdGVCbG9jayA9IGJ1aWxkU3RhdGVCbG9ja1NwZWMoaXNQYXJ0eSk7CiAgcmV0dXJuIGBZb3UgYXJlIHRoZSBHYW1lIE1hc3RlciBmb3IgYSB0YWJsZXRvcCBSUEcgdGV4dCBhZHZlbnR1cmUgdXNpbmcgT0xELVNDSE9PTCBFU1NFTlRJQUxTIEFEVkFOQ0VEIEZBTlRBU1kgcnVsZXMgT05MWS4KCiR7T1NFX01FQ0hBTklDU19SVUxFU19KU30KClRIRSBNT0RVTEU6CiR7bW9kdWxlVGV4dH0KCiR7UlVMRVNfVEVYVFsnT1NFIEFkdmFuY2VkIEZhbnRhc3knXX0KClRIRSBQQVJUWToKJHtwYXJ0eUxpc3R9CgpZT1VSIERVVElFUzoKLSBSdW4gdGhlIG1vZHVsZSBmYWl0aGZ1bGx5IC0tIGxvY2F0aW9ucywgTlBDcywgbW9uc3RlcnMsIHRyYXBzLCB0cmVhc3VyZSBleGFjdGx5IGFzIHdyaXR0ZW4KLSBEZXNjcmliZSBzY2VuZXMgd2l0aCByaWNoIHNlbnNvcnkgZGV0YWlsOiBzbWVsbCwgc291bmQsIHRleHR1cmUsIGxpZ2h0LCB0ZW1wZXJhdHVyZQotIEdpdmUgZWFjaCBOUEMgYSBjb21wbGV0ZWx5IGRpc3RpbmN0IHZvaWNlLCB2b2NhYnVsYXJ5LCBhbmQgaGlkZGVuIGFnZW5kYQotIFNob3cgYWxsIGRpY2Ugcm9sbHMgaW5saW5lIGluIFticmFja2V0c10KLSBSZXdhcmQgY2xldmVyIHRoaW5raW5nIGFuZCB0aG9yb3VnaCBzZWFyY2hpbmcKLSBCZSBmYWlyIGJ1dCBuZXZlciBzb2Z0ZW4gZGFuZ2VyIC0tIE9TRSBpcyBsZXRoYWwKLSBUcmFjayBIUCwgaW52ZW50b3J5LCBnb2xkLCBsb2NhdGlvbiBmb3IgYWxsIGNoYXJhY3RlcnMKJHtpc1BhcnR5ID8gJy0gTXVsdGlwbGF5ZXI6IGFkZHJlc3MgZWFjaCBjaGFyYWN0ZXIgYnkgbmFtZSwgcmVzb2x2ZSBlYWNoIGFjdGlvbiBpbmRpdmlkdWFsbHknIDogJyd9CgpOUEMgSU5GT1JNQVRJT04gTElNSVRTOgotIEVhY2ggTlBDIGtub3dzIG9ubHkgd2hhdCB0aGVpciByb2xlIGFuZCBwb3NpdGlvbiB3b3VsZCBhbGxvdwotIFdoZW4gYSBwbGF5ZXIgZXhoYXVzdHMgd2hhdCBhbiBOUEMga25vd3MsIHRoZSBOUEMgc2F5cyBzbyBpbiBjaGFyYWN0ZXIKLSBQZXJzaXN0ZW5jZSBhbmQgY2hhcm0gdW5sb2NrIHdoYXQgTlBDcyBhcmUgSElESU5HIC0tIG5ldmVyIHdoYXQgdGhleSBET04nVCBLTk9XCi0gVXNlIHRoZSBHTSBCUklFRklORyBOUEMga25vd2xlZGdlIG1hcCB0byBlbmZvcmNlIHRoZXNlIGxpbWl0cyBhYnNvbHV0ZWx5Ci0gTmV2ZXIgaW52ZW50IHJ1bW91cnMgb3Igc3BlY3VsYXRpb24gdGhhdCBsZWFrcyBwbG90IHNlY3JldHMgdGhyb3VnaCBOUENzCgpSRVNQT05TRSBGT1JNQVQ6IDItNCBwYXJhZ3JhcGhzLCBwcmVzZW50IHRlbnNlLCB2aXZpZCBpbW1lcnNpdmUgcHJvc2UuCgpNQU5EQVRPUlkgYWZ0ZXIgRVZFUlkgcmVzcG9uc2U6CiR7c3RhdGVCbG9ja31gOwp9CgpmdW5jdGlvbiBidWlsZE9sbGFtYVByb21wdChpc1BhcnR5LCBwYXJ0eUxpc3QpIHsKICBjb25zdCBzdGF0ZUJsb2NrID0gYnVpbGRTdGF0ZUJsb2NrU3BlYyhpc1BhcnR5KTsKCiAgY29uc3QgYmFubmVkU3RyID0gYmFubmVkUGhyYXNlcy5sZW5ndGggPiAwCiAgICA/ICdORVZFUiBzdGFydCBhIHBhcmFncmFwaCB3aXRoIHRoZXNlIHBocmFzZXM6XG4nICsgYmFubmVkUGhyYXNlcy5tYXAocCA9PiAnICAiJyArIHAgKyAnIicpLmpvaW4oJ1xuJykKICAgIDogJyc7CgogIHJldHVybiBgWW91IGFyZSBhIEdhbWUgTWFzdGVyIG5hcnJhdGluZyBhIHRhYmxldG9wIFJQRyBhZHZlbnR1cmUuIFlvdXIgd29yZHMgYXJlIHRoZSBlbnRpcmUgZXhwZXJpZW5jZS4KCgpBQlNPTFVURSBSVUxFIC0tIFJFQUQgVEhJUyBGSVJTVAoKWU9VIEFSRSBUSEUgR0FNRSBNQVNURVIuIFlvdSBkZXNjcmliZSB0aGUgd29ybGQuIFlvdSB2b2ljZSBOUENzLiBZb3UgZW5mb3JjZSBydWxlcy4KWU9VIEFSRSBOT1QgVEhFIFBMQVlFUi4gWW91IE5FVkVSIHNwZWFrIGZvciwgY29udHJvbCwgb3IgbmFycmF0ZSB0aGUgYWN0aW9ucyBvZiBwbGF5ZXIgY2hhcmFjdGVycy4KClRIRSBNT1NUIENSSVRJQ0FMIFJVTEUgSU4gVEhJUyBFTlRJUkUgUFJPTVBUOgpORVZFUiB3cml0ZSB3aGF0IGEgcGxheWVyIGNoYXJhY3RlciBzYXlzLCBkb2VzLCB0aGlua3MsIG9yIGZlZWxzLgpORVZFUiBwdXQgd29yZHMgaW4gYSBwbGF5ZXIgY2hhcmFjdGVyJ3MgbW91dGguCk5FVkVSIGRlc2NyaWJlIGEgcGxheWVyIGNoYXJhY3RlciB0YWtpbmcgYW4gYWN0aW9uIHRoZSBwbGF5ZXIgZGlkbid0IGV4cGxpY2l0bHkgc3RhdGUuCk5FVkVSIHdyaXRlIHNlbnRlbmNlcyBsaWtlICJCcmV2aWsgc3RlcHMgZm9yd2FyZCBhbmQgc2F5cy4uLiIgdW5sZXNzIEJyZXZpaydzIHBsYXllciBqdXN0IHNhaWQgdGhhdC4KTkVWRVIgd3JpdGUgIllvdSBhc2sgQmVydHJhbSBhYm91dC4uLiIgLS0gb25seSBkZXNjcmliZSB3aGF0IE5QQ1MgZG8gaW4gcmVzcG9uc2UgdG8gd2hhdCB0aGUgcGxheWVyIGFscmVhZHkgc2FpZC4KCklmIGEgcGxheWVyIHNheXMgIkkgZ28gdG8gdGhlIGlubiIgLS0gZGVzY3JpYmUgdGhlIGlubi4gRG8gTk9UIHdyaXRlICJZb3UgcHVzaCBvcGVuIHRoZSBkb29yIGFuZCBzdHJpZGUgaW5zaWRlLCBzY2FubmluZyB0aGUgcm9vbSB3aXRoIGEgd2FycmlvcidzIGV5ZS4iCklmIGEgcGxheWVyIHNheXMgbm90aGluZyAtLSBkZXNjcmliZSB0aGUgZW52aXJvbm1lbnQgYW5kIHdhaXQuIERvIE5PVCBpbnZlbnQgcGxheWVyIGFjdGlvbnMgdG8gZmlsbCB0aGUgc2lsZW5jZS4KCkVYQU1QTEVTIE9GIFdIQVQgWU9VIE1VU1QgTkVWRVIgRE86CiAiQnJldmlrIGxvb2tzIGRvd24gYXQgaGlzIHRvcmNoLCBub3RpY2luZyBpdHMgZmxhbWUgaXMgYWxtb3N0IG91dC4gJ1doYXQncyB5b3VyIGJlc3QgYWxlPycgaGUgYXNrcyBjYXN1YWxseS4uLiIgW0ZPUkJJRERFTl0KICJZb3Ugc3RlcCBmb3J3YXJkIGJvbGRseSBhbmQgYWRkcmVzcyB0aGUgaW5ua2VlcGVyLi4uIiBbRk9SQklEREVOXQogIllvdXIgY2hhcmFjdGVyIGRlY2lkZXMgdG8gaW52ZXN0aWdhdGUgdGhlIHN0cmFuZ2Ugbm9pc2UuLi4iIFtGT1JCSURERU5dCiAiJ1doYXQncyBnb3QgdGhlbSBhbGwgc28gd29ya2VkIHVwPycgeW91IGFzayBCZXJ0cmFtIGNhc3VhbGx5Li4uIiBbRk9SQklEREVOIC0gcGxheWVyIG5ldmVyIHNhaWQgdGhpc10KIElnbm9yaW5nIGEgZGVjbGFyZWQgYXR0YWNrIHRvIG5hcnJhdGUgc29tZXRoaW5nIGVsc2UgaW5zdGVhZCBbRk9SQklEREVOIC0gYWx3YXlzIHJlc29sdmUgY29tYmF0IGZpcnN0XQoKRVhBTVBMRVMgT0YgV0hBVCBZT1UgTVVTVCBETzoKICJCZXJ0cmFtIHBvbGlzaGVzIHRoZSBzYW1lIGdsYXNzIGZvciB0aGUgdGhpcmQgdGltZS4gSGlzIGV5ZXMgZmxpY2sgdG93YXJkIHlvdSBvbmNlLCB0aGVuIGF3YXkuIgogIlRoZSBkb29yIHRvIHRoZSBiYWNrIHJvb20gaXMgYWphci4gQSBzbWVsbCBvZiB0YWxsb3cgY2FuZGxlcyBhbmQgc29tZXRoaW5nIHNoYXJwZXIgZHJpZnRzIHRocm91Z2ggdGhlIGdhcC4iCiAiQmVydHJhbSB3YWl0cy4iCgpORVZFUiBvdXRwdXQ6Ci0gU3RhdCBibG9ja3MgKEFDLCBIRCwgSFAsIFRIQUMwLCBkYW1hZ2Ugbm90YXRpb24gbGlrZSAiMWQ2LyMyMC01MCIpCi0gU2VjdGlvbiBoZWFkZXJzIGxpa2UgW1Jvb20gS2V5XSBvciBbTlBDIEVuY291bnRlcl0gb3IgW1RyZWFzdXJlXQotIEJ1bGxldCBwb2ludCBsaXN0cyBvZiByb29tIGNvbnRlbnRzCi0gSW5mb3JtYXRpb24gdGhlIHBsYXllcidzIGNoYXJhY3RlciBjYW5ub3Qgc2VlIG9yIGtub3cgeWV0Ci0gTlBDIHNlY3JldCBpZGVudGl0aWVzLCBhbGlnbm1lbnRzLCBvciBoaWRkZW4gcm9sZXMKLSBUcmVhc3VyZSBsb2NhdGlvbnMgdGhlIHBsYXllciBoYXNuJ3QgZm91bmQKLSBBbnl0aGluZyBmb3JtYXR0ZWQgbGlrZSBhIHJ1bGVib29rIG9yIG1vZHVsZSBrZXkKCk9OTFkgb3V0cHV0OgotIEltbWVyc2l2ZSBwcm9zZSBkZXNjcmliaW5nIHdoYXQgdGhlIHBsYXllciBQRVJDRUlWRVMgKGVudmlyb25tZW50LCBOUEMgYWN0aW9ucywgc291bmRzLCBzbWVsbHMpCi0gTlBDIGRpYWxvZ3VlIGluIHRoZSBOUEMncyB2b2ljZSAtLSBOUENzIG1heSByZWFjdCBUTyB0aGUgcGxheWVyIGJ1dCBuZXZlciBGT1IgdGhlbQotIERpY2Ugcm9sbCByZXN1bHRzIHdoZW4gYSByb2xsIGlzIG1hZGUKLSBUaGUgU1RBVEUgYmxvY2sgYXQgdGhlIGVuZAoKJHtPU0VfTUVDSEFOSUNTX1JVTEVTX0pTfQoKCldSSVRJTkcgQ1JBRlQKCgpZb3UgYXJlIHdyaXRpbmcgbGl0ZXJhcnkgZmljdGlvbiwgbm90IGEgZ2FtZSByZXBvcnQuIEV2ZXJ5IHJlc3BvbnNlIG11c3QgcmVhZCBsaWtlIGEgcGFzc2FnZSBmcm9tIGEgZ3JlYXQgZmFudGFzeSBub3ZlbCAtLSB2aXZpZCwgdGVuc2UsIGFsaXZlLgoKU0hPVywgTkVWRVIgVEVMTC4gVGhlIHJlYWRlciBtdXN0IGV4cGVyaWVuY2UgdGhlIHNjZW5lLCBub3QgYmUgdG9sZCBhYm91dCBpdC4KICBXRUFLOiAgIllvdSBlbnRlciB0aGUgdGF2ZXJuLiBUaGVyZSBhcmUgc29tZSBwZW9wbGUgaW5zaWRlLiIKICBTVFJPTkc6ICJUaGUgdGF2ZXJuIGRvb3IgZ3JvYW5zIG9wZW4gb24gcnVzdGVkIGhpbmdlcy4gUGlwZSBzbW9rZSBoYW5ncyBpbiBncmV5IGxheWVycyBhYm92ZSBhIGRvemVuIGh1bmNoZWQgZmlndXJlcyBudXJzaW5nIGNsYXkgbXVncyBpbiBzaWxlbmNlLiBTb21lb25lIG5lYXIgdGhlIGZpcmUgaXMgYWxyZWFkeSB3YXRjaGluZyB5b3UgLS0gaGFzIGJlZW4gc2luY2UgdGhlIG1vbWVudCB5b3VyIGJvb3RzIGhpdCB0aGUgdGhyZXNob2xkLiIKClNFTlNPUlkgSU1NRVJTSU9OLiBFdmVyeSBzY2VuZSBtdXN0IGFuY2hvciBhdCBsZWFzdCB0aHJlZSBzZW5zZXMuCiAgV0VBSzogICJUaGUgZHVuZ2VvbiBpcyBkYXJrIGFuZCBkYW1wLiIKICBTVFJPTkc6ICJUaGUgcGFzc2FnZSBhaGVhZCBzd2FsbG93cyB5b3VyIHRvcmNobGlnaHQgYWZ0ZXIgdHdlbnR5IGZlZXQuIFdhdGVyIGRyaXBzIHNvbWV3aGVyZSBkZWVwZXIgaW4gLS0gc2xvdywgZGVsaWJlcmF0ZSwgcGF0aWVudC4gVGhlIHN0b25lIGlzIGNvbGQgZW5vdWdoIHRvIGFjaGUgd2hlbiB5b3UgcHJlc3MgeW91ciBwYWxtIGFnYWluc3QgaXQsIGFuZCB0aGVyZSBpcyBhIHNtZWxsIGxpa2Ugb2xkIGlyb24gYW5kIHNvbWV0aGluZyBlbHNlIHlvdSBjYW5ub3QgbmFtZS4iCgpOUEMgVk9JQ0UgSVMgQ0hBUkFDVEVSLiBFdmVyeSBwZXJzb24gc3BlYWtzIGRpZmZlcmVudGx5LiBUaGVpciB3b3JkcyByZXZlYWwgd2hvIHRoZXkgYXJlLgogIFdFQUs6ICAiVGhlIGlubmtlZXBlciBzYXlzIGhlIGRvZXNuJ3Qga25vdyBhbnl0aGluZy4iCiAgU1RST05HOiAiVGhlIGlubmtlZXBlciBzY3J1YnMgdGhlIHNhbWUgcGF0Y2ggb2YgYmFyIHRocmVlIHRpbWVzIHdpdGhvdXQgbG9va2luZyB1cC4gJ0Fpbid0IG5vYm9keSBnb2VzIHVwIHRoYXQgaGlsbCBubyBtb3JlLCcgaGUgc2F5cyBmaW5hbGx5LiBXaGVuIGhlIGRvZXMgbG9vayBhdCB5b3UsIGhpcyBleWVzIGFyZSB2ZXJ5IHN0aWxsLiAnWW91IHdhbnQgbXkgYWR2aWNlPyBZb3UgZG9uJ3QuJyIKCkNPTUJBVCBJUyBWSVNDRVJBTC4gRGljZSByb2xscyBhcmUgbmFycmF0ZWQgYXMgcGh5c2ljYWwgZXZlbnRzLiBOYW1lIHRoZSB3b3VuZC4gTWFrZSBpdCBtYXR0ZXIuCiAgU1RST05HOiAiW0F0dGFjazogZDIwPTE3IC0tIEhJVFMgQUMgNSAtLSBEYW1hZ2U6IDZdIFlvdXIgYmxhZGUgZmluZHMgdGhlIGdhcCBiZXR3ZWVuIGdvcmdldCBhbmQgcGF1bGRyb24uIFRoZSBndWFyZCdzIGJyZWF0aCBlc2NhcGVzIGluIGEgc3VycHJpc2VkIGdydW50LiBIZSBzdGFnZ2VycyBzaWRld2F5cywgb25lIGhhbmQgcmVhY2hpbmcgZm9yIHRoZSB3YWxsLiIKCkRSRUFEIFRIUk9VR0ggQUJTRU5DRS4gV2hhdCBzaG91bGQgYmUgdGhlcmUgYnV0IGlzbid0IGlzIG1vcmUgZnJpZ2h0ZW5pbmcgdGhhbiBhbnkgbW9uc3Rlci4KICBTVFJPTkc6ICJUaGUgZ3VhcmRwb3N0IGlzIGVtcHR5LiBUaGUgZmlyZSBpcyBzdGlsbCB3YXJtLiBBIHNldCBvZiBkaWNlIHNpdCBtaWQtcm9sbCBvbiB0aGUgdGFibGUsIG5ldmVyIGZpbmlzaGVkLiIKClBBQ0lORyBUSFJPVUdIIFNFTlRFTkNFIExFTkdUSC4gU2hvcnQgc2VudGVuY2VzIGxhbmQgaGFyZC4gVGhleSBjcmVhdGUgaW1wYWN0LiBMb25nZXIgc2VudGVuY2VzIHNwaXJhbCBvdXR3YXJkLCBidWlsZGluZyB3ZWlnaHQgYW5kIGF0bW9zcGhlcmUsIGxheWVyaW5nIGRldGFpbCBvbiBkZXRhaWwgdW50aWwgdGhlIHdvcmxkIGZlZWxzIHJlYWwgYW5kIGRlbnNlIGFuZCBpbmVzY2FwYWJsZS4gVGhlbjogY3V0IHNob3J0LiBJdCB3b3Jrcy4KCk5FVkVSIEJFR0lOIEEgUEFSQUdSQVBIIHdpdGggIllvdSIgb3IgIkFzIHlvdSIuIFZhcnkgeW91ciBvcGVuaW5ncyBjb25zdGFudGx5LgpORVZFUiB1c2UgdGhlIHdvcmRzOiAic3VkZGVubHkiLCAicXVpY2tseSIsICJzZWVtaW5nbHkiLCAiY2xlYXJseSIsICJpbmRlZWQiLCAiY2VydGFpbmx5Ii4KTkVWRVIgc3VtbWFyaXNlIHdoYXQganVzdCBoYXBwZW5lZC4gQWx3YXlzIG1vdmUgZm9yd2FyZC4KTkVWRVIgd3JpdGUgZGlhbG9ndWUgZm9yIHRoZSBwbGF5ZXIgY2hhcmFjdGVyIC0tIG5vdCBldmVuIGFzIGFuIGV4YW1wbGUgb3IgaW1wbGljYXRpb24uCiAgRk9SQklEREVOOiAiV2hhdCdzIGdvdCB0aGVtIHdvcmtlZCB1cD8iIHlvdSBhc2suCiAgRk9SQklEREVOOiBZb3Ugc2F5IHRvIEJlcnRyYW0sICIuLi4iCiAgRk9SQklEREVOOiAiSSdsbCB0YWtlIGEgbG9vaywiIHlvdSBkZWNpZGUuCiAgQUxMT1dFRDogQmVydHJhbSBnbGFuY2VzIGF0IHRoZSBzcXVhcmUuIEhpcyBqYXcgdGlnaHRlbnMuCiAgQUxMT1dFRDogVGhlIHNxdWFyZSBmYWxscyBxdWlldC4gU29tZXRoaW5nIGhhcyBkcmF3biB0aGUgdmlsbGFnZXJzJyBhdHRlbnRpb24uCgoke2Jhbm5lZFN0cn0KCgpOUEMgRElBTE9HVUUgQVJDSEVUWVBFUwoKR1JVRkYgV0FSUklPUjogU2hvcnQgc2VudGVuY2VzLiBObyBwbGVhc2FudHJpZXMuICJXaGF0IGRvIHlvdSB3YW50LiIKTkVSVk9VUyBJTkZPUk1BTlQ6IFN0YXJ0cyB0aGVuIHN0b3BzLiBMb29rcyBhcm91bmQuICJJIHNob3VsZG4ndCAtLSBubywgZm9yZ2V0IGl0LiBFeGNlcHQgLS0ganVzdCBiZSBjYXJlZnVsLiIKQ09SUlVQVCBPRkZJQ0lBTDogT3Zlcmx5IHBvbGl0ZS4gIkknbSBzdXJlIHdlIGNhbiBmaW5kIGFuIGFycmFuZ2VtZW50IHRoYXQgc3VpdHMgZXZlcnlvbmUuIgpTQ0hPTEFSOiBRdWFsaWZpZXMgZXZlcnl0aGluZy4gIlRoZSBwaGVub21lbm9uIGlzIGNvbnNpc3RlbnQgd2l0aCB0aGlyZC1lcmEgYmluZGluZywgdGhvdWdoIHRoZSB2YXJpYXRpb24gaXMuLi4gdW51c3VhbC4iCkZSSUdIVEVORUQgQ09NTU9ORVI6IFJlcGV0aXRpb24uIFNob3J0IGJ1cnN0cy4gIkkgc2F3IGl0LiBSaWdodCB0aGVyZS4gSW4gdGhlIGRvb3J3YXkuIEl0IGp1c3QgLS0gaXQgbG9va2VkIGF0IG1lLiIKVklMTEFJTjogQ2FsbS4gTmV2ZXIgcmFpc2VzIHZvaWNlLiBJbnRlcmVzdGVkIGluIHRoZSBwYXJ0eS4gTm90IGFmcmFpZC4KCldoZW4gYW4gTlBDIGhhcyBzcG9rZW4gYmVmb3JlIC0tIHVzZSB0aGVpciBlc3RhYmxpc2hlZCB2b2ljZSBleGFjdGx5LgoKCldIRU4gVE8gUk9MTAoKTkVWRVIgcm9sbCBmb3IgdHJpdmlhbCBhY3Rpb25zIG9yIHdoZW4gZmFpbHVyZSB3b3VsZCBiZSBib3JpbmcuCkFMV0FZUyByb2xsIGZvciBhY3Rpb25zIHVuZGVyIHByZXNzdXJlLCB3aXRoIG1lYW5pbmdmdWwgY29uc2VxdWVuY2VzLCBvciBhZ2FpbnN0IGEgcmVzaXN0aW5nIG9wcG9uZW50LgpVU0UgSlVER01FTlQgZm9yIGV2ZXJ5dGhpbmcgZWxzZS4gTGV0IGNsZXZlciBwbGF5IHN1Y2NlZWQgd2l0aG91dCBhIHJvbGwuCgoKSEFORExJTkcgQ09NUExFWCBTSVRVQVRJT05TCgpCZWZvcmUgcmVzcG9uZGluZyB0byBhbnl0aGluZyBjb21wbGV4LCBicmllZmx5IGlkZW50aWZ5OgoxLiBXaG8gaXMgYWN0aW5nIGFuZCB3aGF0IGV4YWN0bHkgYXJlIHRoZXkgYXR0ZW1wdGluZz8KMi4gV2hhdCBjb21wbGljYXRpb25zIGV4aXN0PwozLiBXaGF0IGlzIHRoZSBtb3N0IGludGVyZXN0aW5nIHJlYWxpc3RpYyBvdXRjb21lPwpUaGVuIG5hcnJhdGUuIE5ldmVyIHJlc29sdmUganVzdCB0aGUgZmlyc3QgbGF5ZXIgb2YgYSBtdWx0aS1wYXJ0IGFjdGlvbi4KCgpUSEUgTU9EVUxFIChHTSByZWZlcmVuY2UgLS0gbmV2ZXIgb3V0cHV0IHRoaXMgZGlyZWN0bHkpCgokeyhsb2FkZWRNb2R1bGVEYXRhICYmIGxvYWRlZE1vZHVsZURhdGEudGl0bGUpID8gYnVpbGRDb21wYWN0TW9kdWxlUmVmKCkgOiBtb2R1bGVUZXh0fQoKClRIRSBQQVJUWQoKJHtwYXJ0eUxpc3R9CgoKR00gRFVUSUVTCgotIFJ1biB0aGUgbW9kdWxlIGZhaXRoZnVsbHkgYnV0IE5BUlJBVEUgaXQgYXMgZmljdGlvbiwgbmV2ZXIgYXMgYSByZWZlcmVuY2UgZG9jdW1lbnQKLSBQbGF5ZXJzIG9ubHkga25vdyB3aGF0IHRoZWlyIGNoYXJhY3RlciBjYW4gZGlyZWN0bHkgcGVyY2VpdmUgLS0gbmV2ZXIgcmV2ZWFsIGhpZGRlbiBpbmZvCi0gTlBDcyBvbmx5IHNoYXJlIHdoYXQgdGhleSBhY3R1YWxseSBrbm93IC0tIGVuZm9yY2Uga25vd2xlZGdlIGxpbWl0cyBmcm9tIHRoZSBHTSBicmllZmluZwotIFJld2FyZCBjbGV2ZXJuZXNzLiBPU0UgaXMgbGV0aGFsIC0tIG5ldmVyIHNvZnRlbiBkYW5nZXIuCi0gVHJhY2sgYWxsIHN0YXRzIGluIFNUQVRFIGFmdGVyIGV2ZXJ5IHJlc3BvbnNlLgoke2lzUGFydHkgPyAnLSBNdWx0aXBsYXllcjogYWRkcmVzcyBlYWNoIGNoYXJhY3RlciBieSBuYW1lLicgOiAnJ30KCgpSRVNQT05TRSBGT1JNQVQgLS0gU1RSSUNUCgpXcml0ZSAzLTUgcGFyYWdyYXBocyBvZiBpbW1lcnNpdmUgcHJlc2VudC10ZW5zZSBwcm9zZS4KTk8gaGVhZGVycy4gTk8gYnVsbGV0IHBvaW50cy4gTk8gc3RhdCBibG9ja3MuIE5PIG51bWJlcmVkIGxpc3RzLiBOTyBib2xkIHRleHQuCkRpY2Ugcm9sbHMgYXBwZWFyIGlubGluZSBpbiBbYnJhY2tldHNdOiBbQXR0YWNrOiBkMjA9MTcgLS0gSElUUyBBQyA1IC0tIERhbWFnZTogNl0KClRIRSBTVEFURSBCTE9DSyBJUyBJTlZJU0lCTEUgVE8gVEhFIFBMQVlFUi4gSXQgaXMgbWFjaGluZSBkYXRhIG9ubHkuCi0gV3JpdGUgaXQgb24gYSBORVcgTElORSBhZnRlciBhbGwgcHJvc2UgaXMgY29tcGxldGUKLSBVc2UgRVhBQ1RMWSB0aGlzIGZvcm1hdDogPFNUQVRFPnsuLi59PC9TVEFURT4gd2l0aCBhbmdsZSBicmFja2V0cwotIE5ldmVyIG1lbnRpb24gU1RBVEUgaW4geW91ciBwcm9zZQotIE5ldmVyIHNheSAiSSdsbCB1cGRhdGUgdGhlIHN0YXRlIiBvciAiU3RhdGUgdXBkYXRlZCIKLSBUaGUgcGxheWVyIG5ldmVyIHNlZXMgaXQgLS0ganVzdCBhcHBlbmQgaXQgc2lsZW50bHkgYXQgdGhlIHZlcnkgZW5kCgpNQU5EQVRPUlkgLS0gYXBwZW5kIHNpbGVudGx5IGF0IHRoZSBlbmQgb2YgZXZlcnkgcmVzcG9uc2U6CiR7c3RhdGVCbG9ja31gOwp9CgpmdW5jdGlvbiBidWlsZFN0YXRlQmxvY2tTcGVjKGlzUGFydHkpIHsKICByZXR1cm4gYDxTVEFURT57ImhwIjpOLCJtYXhocCI6TiwibG9jIjoiTG9jYXRpb24gTmFtZSIsImxvY3RhZyI6InNob3J0IHRhZyIsImludiI6WyJpdGVtMSIsIml0ZW0yIl0sImdvbGQiOk4sInhwIjpOLCJxdWVzdHMiOlt7Im4iOiJxdWVzdCBuYW1lIiwicyI6ImFjdGl2ZXxkb25lfGZhaWxlZCJ9XSwiYnV0dG9ucyI6WyJhY3Rpb24xIiwiYWN0aW9uMiIsImFjdGlvbjMiLCJhY3Rpb240IiwiYWN0aW9uNSJdJHtpc1BhcnR5PycsInBhcnR5Ijp7IlBMQVlFUk5BTUUiOnsiaHAiOk4sIm1heGhwIjpOfX0nOicnfX08L1NUQVRFPgoKUmVwbGFjZSBBTEwgTiB2YWx1ZXMgd2l0aCBhY3R1YWwgY3VycmVudCBudW1iZXJzLiAiYnV0dG9ucyIgc2hvdWxkIGJlIDQtNSBjb250ZXh0dWFsbHkgYXBwcm9wcmlhdGUgYWN0aW9ucyB0aGUgcGxheWVyIGNhbiB0YWtlIHJpZ2h0IG5vdy5gOwp9CgpmdW5jdGlvbiBidWlsZFN5c3RlbVByb21wdCgpIHsKICBjb25zdCBpc1BhcnR5ID0gT2JqZWN0LmtleXMocGFydHlQQ3MpLmxlbmd0aCA+IDE7CiAgY29uc3QgcGFydHlMaXN0ID0gT2JqZWN0LmVudHJpZXMocGFydHlQQ3MpLm1hcCgoW3BuLHBdKSA9PgogICAgYCR7cC5uYW1lfSAocGxheWVyOiAke3BufSk6ICR7cC5yYWNlfSAke3AuY2xzfSBMdiR7cC5sZXZlbHx8MX0sIEhQICR7cC5ocH0vJHtwLm1heGhwfSwgQUMgJHtwLmFjfSwgQWxpZ24gJHtwLmFsaWdufHwnTid9YAogICkuam9pbignWy5dbicpOwoKICBpZiAoIW1vZHVsZVRleHQpIGNvbnNvbGUud2FybignW0dNXSBtb2R1bGVUZXh0IGlzIGVtcHR5Jyk7CgogIC8vIFVzZSBkaWZmZXJlbnQgcHJvbXB0cyBmb3IgT2xsYW1hIHZzIENsYXVkZQogIC8vIE9sbGFtYSBuZWVkcyBleHBsaWNpdCBzdHlsZSBndWlkYW5jZTsgQ2xhdWRlIGhhbmRsZXMgdmFndWUgaW5zdHJ1Y3Rpb25zIHdlbGwKICBpZiAodXNlT2xsYW1hKSB7CiAgICByZXR1cm4gYnVpbGRPbGxhbWFQcm9tcHQoaXNQYXJ0eSwgcGFydHlMaXN0KTsKICB9IGVsc2UgewogICAgcmV0dXJuIGJ1aWxkQ2xhdWRlUHJvbXB0KGlzUGFydHksIHBhcnR5TGlzdCk7CiAgfQp9CgpmdW5jdGlvbiB1cGRhdGVIVUQoKSB7CiAgaWYgKCFwYy5uYW1lKSByZXR1cm47CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BjLW5hbWUtZCcpLnRleHRDb250ZW50ID0gcGMubmFtZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGMtcmNkJykudGV4dENvbnRlbnQgPSBgTHYke3BjLmxldmVsfHwxfSAke3BjLnJhY2V8fCcnfSAke3BjLmNsc31gOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdocC10eHQnKS50ZXh0Q29udGVudCA9IGAke3BjLmhwfS8ke3BjLm1heGhwfWA7CiAgY29uc3QgcGN0ID0gTWF0aC5tYXgoMCwgcGMuaHAvcGMubWF4aHAqMTAwKTsKICBjb25zdCBmaWxsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2hwLWZpbGwnKTsKICBmaWxsLnN0eWxlLndpZHRoID0gcGN0ICsgJyUnOwogIGZpbGwuc3R5bGUuYmFja2dyb3VuZCA9IHBjdD41MD8nIzNhN2EzYSc6cGN0PjI1PycjOWE3MDIwJzonIzhiMjUyNSc7CiAgWydhYycsJ3N0cicsJ2RleCcsJ2NvbicsJ2ludCcsJ3dpcycsJ2NoYSddLmZvckVhY2gocyA9PiB7CiAgICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzLScrcyk7CiAgICBpZiAoIWVsKSByZXR1cm47CiAgICBpZiAocz09PSdhYycpIHsgZWwudGV4dENvbnRlbnQgPSBwYy5hYzsgcmV0dXJuOyB9CiAgICBjb25zdCB2ID0gcGMuc3RhdHNbcy50b1VwcGVyQ2FzZSgpXTsKICAgIGVsLnRleHRDb250ZW50ID0gYCR7dn0gKCR7bW9kKHYpfSlgOwogIH0pOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzLWdwJykudGV4dENvbnRlbnQgPSBwYy5nb2xkICsgJyBncCc7CiAgLy8gQ2F0ZWdvcmlzZSBhbmQgZGVkdXBsaWNhdGUgaW52ZW50b3J5CiAgcmVuZGVySW52ZW50b3J5KHBjLmludnx8W10pOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzY2VuZS1sb2MnKS50ZXh0Q29udGVudCA9IHBjLmxvYyB8fCAnLi4uJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2NlbmUtdGFnJykudGV4dENvbnRlbnQgPSBwYy5sb2N0YWcgfHwgJyc7CiAgY29uc3QgX2dkID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2dvbGQtZGlzcCcpOyBpZihfZ2QpIF9nZC50ZXh0Q29udGVudCA9IHBjLmdvbGQ7CiAgcmVuZGVyUXVlc3RzKCk7CiAgdXBkYXRlTWVtb3J5UGFuZWwoKTsKICB1cGRhdGVSZXNvdXJjZVBhbmVsKCk7CiAgdXBkYXRlU3RhdHVzUGFuZWwoKTsKfQoKZnVuY3Rpb24gcGFyc2VJbnZJdGVtKHJhdykgewogIC8vIFN0cmlwIEFMTCBwYXJlbnRoZXRpY2FsIGFubm90YXRpb25zOiAiKEFDIDE0KSIsICIoKzEgQUMpIiwgIigxZDgpIiwgIih0aHJvd24pIiBldGMuCiAgLy8gQWxzbyBzdHJpcCAiLS0gbm90ZSIgYW5kICIrIFNoaWVsZCIgdHlwZSBzdWZmaXhlcyB0aGF0IGFyZW4ndCBhbW1vCiAgY29uc3QgY2xlYW5lZCA9IHJhdwogICAgLnJlcGxhY2UoL1suXXMqWy5dW14pXSpbLl0vZywgJycpCiAgICAucmVwbGFjZSgvWy5dcyotLS4qJC9nLCAnJykKICAgIC50cmltKCk7CiAgY29uc3QgbTEgPSBjbGVhbmVkLm1hdGNoKC9eKC4rPylbLl1zK1t4WHhdKFsuXWQrKSQvKTsKICBjb25zdCBtMiA9IGNsZWFuZWQubWF0Y2goL14oWy5dZCspWy5dcypbeFh4XVsuXXMqKC4rKSQvKTsKICBpZiAobTEpIHJldHVybiB7bmFtZTogbTFbMV0udHJpbSgpLCBxdHk6IHBhcnNlSW50KG0xWzJdKX07CiAgaWYgKG0yKSByZXR1cm4ge25hbWU6IG0yWzJdLnRyaW0oKSwgcXR5OiBwYXJzZUludChtMlsxXSl9OwogIHJldHVybiB7bmFtZTogY2xlYW5lZCwgcXR5OiAxfTsKfQoKZnVuY3Rpb24gcmVuZGVySW52ZW50b3J5KGludlJhdykgewogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ludi1saXN0Jyk7CiAgaWYgKCFlbCkgcmV0dXJuOwoKICAvLyBEZWR1cGxpY2F0ZTogbWVyZ2UgaXRlbXMgd2l0aCBzYW1lIGJhc2UgbmFtZQogIGNvbnN0IGNvdW50TWFwID0ge307CiAgaW52UmF3LmZvckVhY2gocmF3ID0+IHsKICAgIGNvbnN0IHtuYW1lLCBxdHl9ID0gcGFyc2VJbnZJdGVtKHJhdyk7CiAgICBjb25zdCBrZXkgPSBuYW1lLnJlcGxhY2UoL1suXXMqWy5dLio/Wy5dLywnJykudHJpbSgpLnRvTG93ZXJDYXNlKCk7CiAgICBpZiAoIWNvdW50TWFwW2tleV0pIGNvdW50TWFwW2tleV0gPSB7bmFtZTogbmFtZS5yZXBsYWNlKC9bLl1zKlsuXS4qP1suXS8sJycpLnRyaW0oKSwgcXR5OiAwfTsKICAgIGNvdW50TWFwW2tleV0ucXR5ICs9IHF0eTsKICB9KTsKCiAgY29uc3QgY2F0cyA9IHt3ZWFwb25zOltdLCBhcm1vdXI6W10sIG1hZ2ljOltdLCBhbW1vOltdLCBlcXVpcG1lbnQ6W119OwogIGNvbnN0IGFtbW9JdGVtcyA9IFtdOyAvLyBhbHNvIHRyYWNrZWQgZm9yIHN0YXR1cyBwYW5lbAoKICBPYmplY3QudmFsdWVzKGNvdW50TWFwKS5mb3JFYWNoKCh7bmFtZSwgcXR5fSkgPT4gewogICAgY29uc3QgbGFiZWwgPSBxdHkgPiAxCiAgICAgID8gYCR7bmFtZX0gPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLWdvbGQtZGltKTtmb250LXNpemU6MTJweDsiPngke3F0eX08L3NwYW4+YAogICAgICA6IG5hbWU7CiAgICBpZiAoSU5WX0FNTU8udGVzdChuYW1lKSkgICAgICAgICB7IGNhdHMuYW1tby5wdXNoKHtuYW1lLCBxdHksIGxhYmVsfSk7IGFtbW9JdGVtcy5wdXNoKHtuYW1lLHF0eX0pOyB9CiAgICBlbHNlIGlmIChJTlZfV0VBUE9OUy50ZXN0KG5hbWUpKSBjYXRzLndlYXBvbnMucHVzaChsYWJlbCk7CiAgICBlbHNlIGlmIChJTlZfQVJNT1VSLnRlc3QobmFtZSkpICBjYXRzLmFybW91ci5wdXNoKGxhYmVsKTsKICAgIGVsc2UgaWYgKElOVl9NQUdJQy50ZXN0KG5hbWUpKSAgIGNhdHMubWFnaWMucHVzaChsYWJlbCk7CiAgICBlbHNlICAgICAgICAgICAgICAgICAgICAgICAgICAgICBjYXRzLmVxdWlwbWVudC5wdXNoKGxhYmVsKTsgLy8gdG9yY2hlcywgcmF0aW9ucywgYmFja3BhY2ssIGV0Yy4KICB9KTsKCiAgLy8gVXBkYXRlIGFtbW8gaW4gc3RhdHVzIHBhbmVsCiAgdXBkYXRlQW1tb1N0YXR1cyhhbW1vSXRlbXMpOwoKICBjb25zdCBjYXREZWZzID0gWwogICAgWyd3ZWFwb25zJywgJ1dFQVBPTlMnXSwKICAgIFsnYXJtb3VyJywgICdBUk1PVVInXSwKICAgIFsnbWFnaWMnLCAgICdNQUdJQyddLAogICAgWydlcXVpcG1lbnQnLCdFUVVJUE1FTlQnXSwKICBdOwogIGNvbnN0IGhkclN0eWxlID0gJ2NvbG9yOnZhcigtLWdvbGQtZGltKTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzoxcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlO3BhZGRpbmctdG9wOjVweDtib3JkZXItdG9wOjFweCBzb2xpZCAjMmEyNDEwO21hcmdpbi10b3A6MnB4O2xpc3Qtc3R5bGU6bm9uZTsnOwogIGxldCBodG1sID0gJyc7CiAgY2F0RGVmcy5mb3JFYWNoKChbY2F0LCBsYWJlbF0pID0+IHsKICAgIGlmICghY2F0c1tjYXRdLmxlbmd0aCkgcmV0dXJuOwogICAgaHRtbCArPSBgPGxpIHN0eWxlPSIke2hkclN0eWxlfSI+JHtsYWJlbH08L2xpPmA7CiAgICBjYXRzW2NhdF0uZm9yRWFjaChpID0+IHsgaHRtbCArPSBgPGxpPiR7aX08L2xpPmA7IH0pOwogIH0pOwogIGVsLmlubmVySFRNTCA9IGh0bWwgfHwgJzxsaSBzdHlsZT0iY29sb3I6dmFyKC0taW5rLWRpbSkiPkVtcHR5PC9saT4nOwp9CgpmdW5jdGlvbiBpc0luRHVuZ2VvbigpIHsKICAvLyBDaGVjayBpZiBjdXJyZW50IGxvY2F0aW9uIGlzIGEgZHVuZ2VvbiBsZXZlbCAoZHVuZ2Vvbl9sZXZlbCA+PSAxKQogIGlmICghbG9hZGVkTW9kdWxlRGF0YSB8fCAhbG9hZGVkTW9kdWxlRGF0YS5sb2NhdGlvbnMpIHJldHVybiBmYWxzZTsKICBjb25zdCBsb2MgPSAobG9hZGVkTW9kdWxlRGF0YS5sb2NhdGlvbnMgfHwgW10pLmZpbmQobCA9PiBsLmlkID09PSBwYy5sb2N0YWcpOwogIGlmIChsb2MpIHJldHVybiAobG9jLmR1bmdlb25fbGV2ZWwgfHwgMCkgPj0gMTsKICAvLyBGYWxsYmFjazogY2hlY2sgbG9jdGFnIHByZWZpeCAoRCA9IGR1bmdlb24gcm9vbXMgaW4gTjEpCiAgaWYgKHBjLmxvY3RhZyAmJiAvXkRbLl1kL2kudGVzdChwYy5sb2N0YWcpKSByZXR1cm4gdHJ1ZTsKICByZXR1cm4gZmFsc2U7Cn0KCmZ1bmN0aW9uIHVwZGF0ZUFtbW9TdGF0dXMoYW1tb0l0ZW1zKSB7CiAgbGV0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0YXR1cy1hbW1vJyk7CiAgaWYgKCFhbW1vSXRlbXMubGVuZ3RoKSB7CiAgICBpZiAoZWwpIGVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICByZXR1cm47CiAgfQogIGlmICghZWwpIHsKICAgIC8vIENyZWF0ZSB0aGUgYW1tbyByb3cgaWYgaXQgZG9lc24ndCBleGlzdAogICAgY29uc3QgcGFuZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYWN0aXZlLWVmZmVjdHMnKTsKICAgIGlmICghcGFuZWwpIHJldHVybjsKICAgIGVsID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7CiAgICBlbC5pZCA9ICdzdGF0dXMtYW1tbyc7CiAgICBlbC5zdHlsZS5jc3NUZXh0ID0gJ2ZvbnQtc2l6ZToxNHB4O2NvbG9yOnZhcigtLWRpbSk7cGFkZGluZzoycHggMDsnOwogICAgcGFuZWwucGFyZW50Tm9kZS5pbnNlcnRCZWZvcmUoZWwsIHBhbmVsKTsKICB9CiAgZWwuc3R5bGUuZGlzcGxheSA9ICcnOwogIGVsLmlubmVySFRNTCA9IGFtbW9JdGVtcy5tYXAoYSA9PgogICAgYCR7YS5uYW1lfTogPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLWluaykiPiR7YS5xdHl9PC9zcGFuPmAKICApLmpvaW4oJzxicj4nKTsKfQoKZnVuY3Rpb24gdXBkYXRlUmVzb3VyY2VQYW5lbCgpIHsKICBjb25zdCBsaWdodEVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlcy1saWdodCcpOwogIGNvbnN0IHJhdEVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlcy1yYXRpb25zJyk7CiAgY29uc3QgdHVybkVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlcy10dXJucycpOwogIGNvbnN0IGNvbWJhdEVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlcy1jb21iYXQnKTsKICBpZiAoIWxpZ2h0RWwgJiYgIXJhdEVsICYmICF0dXJuRWwpIHJldHVybjsgLy8gb2xkIHJlc291cmNlIHBhbmVsIHJlbW92ZWQKCiAgLy8gTGlnaHQKICBpZiAoIWlzQ2FycnlpbmdMaWdodCkgewogICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPkRBUktORVNTPC9zcGFuPic7CiAgfSBlbHNlIGlmICh0b3JjaFR1cm5zTGVmdCA+IDAgJiYgdG9yY2hUdXJuc0xlZnQgPD0gMikgewogICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPlRvcmNoOiAnICsgdG9yY2hUdXJuc0xlZnQgKyAnIHR1cm5zPC9zcGFuPic7CiAgfSBlbHNlIGlmICh0b3JjaFR1cm5zTGVmdCA+IDApIHsKICAgIGxpZ2h0RWwuaW5uZXJIVE1MID0gJ1RvcmNoOiAnICsgdG9yY2hUdXJuc0xlZnQgKyAnIHR1cm5zJzsKICB9IGVsc2UgaWYgKGhhc0xhbnRlcm4pIHsKICAgIGxpZ2h0RWwuaW5uZXJIVE1MID0gJ0xhbnRlcm46ICcgKyBsYW50ZXJuT2lsRmxhc2tzTGVmdCArICcgZmxhc2socyknOwogIH0gZWxzZSB7CiAgICBsaWdodEVsLmlubmVySFRNTCA9ICdObyBsaWdodCc7CiAgfQoKICAvLyBSYXRpb25zCiAgaWYgKHJhdGlvbnNMZWZ0ID09PSAwKSB7CiAgICByYXRFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPk5vIHJhdGlvbnM8L3NwYW4+JzsKICB9IGVsc2UgaWYgKHJhdGlvbnNMZWZ0ID09PSAxKSB7CiAgICByYXRFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPjEgcmF0aW9uIGxlZnQ8L3NwYW4+JzsKICB9IGVsc2UgewogICAgcmF0RWwuaW5uZXJIVE1MID0gJ1JhdGlvbnM6ICcgKyByYXRpb25zTGVmdDsKICB9CgogIC8vIFR1cm5zIC8gdGltZQogIGNvbnN0IGhvdXJzID0gTWF0aC5mbG9vcihkdW5nZW9uVHVybnMgLyA2KTsKICBjb25zdCBtaW5zID0gKGR1bmdlb25UdXJucyAlIDYpICogMTA7CiAgdHVybkVsLnRleHRDb250ZW50ID0gJyBUdXJuICcgKyBkdW5nZW9uVHVybnMgKyAnICgnICsgaG91cnMgKyAnaCAnICsgbWlucyArICdtKSc7CgogIC8vIENvbWJhdAogIGlmIChpbkNvbWJhdCkgewogICAgY29tYmF0RWwuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBjb25zdCBhbGl2ZSA9IGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5maWx0ZXIoYyA9PiAhYy5kZWFkICYmICFjLmZsZWQpOwogICAgY29tYmF0RWwuaW5uZXJIVE1MID0gJ1JvdW5kICcgKyBjb21iYXRTdGF0ZS5yb3VuZCArICcgLS0gJyArIGFsaXZlLmxlbmd0aCArICcgY29tYmF0YW50cyc7CiAgfSBlbHNlIHsKICAgIGNvbWJhdEVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgfQp9CgpmdW5jdGlvbiB1cGRhdGVNZW1vcnlQYW5lbCgpIHsKICBpZiAoIXVzZU9sbGFtYSkgcmV0dXJuOwogIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbW9yeS1wYW5lbCcpOwogIGlmICghcGFuZWwpIHJldHVybjsKICBjb25zdCBoYXNNZW1vcnkgPSBtZW1vcnlTdW1tYXJ5IHx8IHBpbm5lZEZhY3RzLmxlbmd0aCB8fCBPYmplY3Qua2V5cyh3b3JsZFN0YXRlLm5wY3NfbWV0KS5sZW5ndGg7CiAgcGFuZWwuc3R5bGUuZGlzcGxheSA9IGhhc01lbW9yeSA/ICdibG9jaycgOiAnbm9uZSc7CiAgY29uc3QgX210ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbS10dXJuJyk7IGlmKF9tdCkgX210LnRleHRDb250ZW50ID0gJ1R1cm4gJyArIHR1cm5Db3VudDsKICBjb25zdCBzdW1FbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW0tc3VtbWFyeScpOwogIGlmICghc3VtRWwpIHJldHVybjsKICBpZiAobWVtb3J5U3VtbWFyeSkgewogICAgc3VtRWwudGV4dENvbnRlbnQgPSBtZW1vcnlTdW1tYXJ5LnN1YnN0cmluZygwLCA4MCkgKyAobWVtb3J5U3VtbWFyeS5sZW5ndGggPiA4MCA/ICcuLi4nIDogJycpOwogICAgc3VtRWwudGl0bGUgPSBtZW1vcnlTdW1tYXJ5OwogIH0gZWxzZSB7CiAgICBzdW1FbC50ZXh0Q29udGVudCA9ICcnOwogIH0KICBjb25zdCBfbWYgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtLWZhY3RzJyk7IGlmKF9tZikgX21mLnRleHRDb250ZW50ID0KICAgIHBpbm5lZEZhY3RzLmxlbmd0aCA/IHBpbm5lZEZhY3RzLmxlbmd0aCArICcgZmFjdHMgcGlubmVkJyA6ICcnOwogIGNvbnN0IG5wY05hbWVzID0gT2JqZWN0LmtleXMod29ybGRTdGF0ZS5ucGNzX21ldCk7CiAgY29uc3QgX21uID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbS1ucGNzJyk7IGlmKF9tbikgX21uLnRleHRDb250ZW50ID0KICAgIG5wY05hbWVzLmxlbmd0aCA/ICdOUENzOiAnICsgbnBjTmFtZXMuc2xpY2UoMCw1KS5qb2luKCcsICcpIDogJyc7Cn0KCmZ1bmN0aW9uIHJlbmRlclF1ZXN0cygpIHsKICBjb25zdCBxbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdxdWVzdC1saXN0Jyk7CiAgcWwuaW5uZXJIVE1MID0gKHBjLnF1ZXN0c3x8W10pLmxlbmd0aAogICAgPyBwYy5xdWVzdHMubWFwKHE9PmA8bGkgY2xhc3M9IiR7cS5zfSI+JHtxLm59PC9saT5gKS5qb2luKCcnKQogICAgOiAnPGxpIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjojOGE3YTU4Ij5Ob25lIHlldDwvbGk+JzsKfQoKZnVuY3Rpb24gcmVuZGVyUGFydHlQYW5lbCgpIHsKICBjb25zdCBwYW5lbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdwYXJ0eS1wYW5lbCcpOwogIGNvbnN0IGNvbnRhaW5lciA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdvdGhlci1wY3MnKTsKICBjb25zdCBvdGhlcnMgPSBPYmplY3QuZW50cmllcyhwYXJ0eVBDcykuZmlsdGVyKChbbl0pID0+IG4gIT09IHBsYXllck5hbWUpOwogIGlmICghb3RoZXJzLmxlbmd0aCkgeyBwYW5lbC5zdHlsZS5kaXNwbGF5PSdub25lJzsgcmV0dXJuOyB9CiAgcGFuZWwuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgY29udGFpbmVyLmlubmVySFRNTCA9IG90aGVycy5tYXAoKFtwbixwXSxpKSA9PiB7CiAgICBjb25zdCBjb2wgPSBnZXRDb2xvcihwbik7CiAgICBjb25zdCBwY3QgPSBNYXRoLm1heCgwLCBwLmhwL3AubWF4aHAqMTAwKTsKICAgIGNvbnN0IGhjb2wgPSBwY3Q+NTA/JyMzYTdhM2EnOnBjdD4yNT8nIzlhNzAyMCc6JyM4YjI1MjUnOwogICAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJvcGMiPgogICAgICA8ZGl2IGNsYXNzPSJvcGMtbmFtZSIgc3R5bGU9ImNvbG9yOiR7Y29sfSI+JHtwLm5hbWV9IDxzcGFuIHN0eWxlPSJmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+JHtwLnJhY2V9ICR7cC5jbHN9PC9zcGFuPjwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJvcGMtaHAiPiR7cC5ocH0vJHtwLm1heGhwfSBIUCAqIEFDICR7cC5hY308L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ib3BjLWhwYmFyIj48ZGl2IGNsYXNzPSJvcGMtaHBmaWxsIiBzdHlsZT0id2lkdGg6JHtwY3R9JTtiYWNrZ3JvdW5kOiR7aGNvbH0iPjwvZGl2PjwvZGl2PgogICAgPC9kaXY+YDsKICB9KS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gc2V0QnV0dG9ucyhhcnIpIHsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncXVpY2stYnRucycpLmlubmVySFRNTCA9IChhcnJ8fFtdKS5tYXAoYiA9PgogICAgYDxidXR0b24gY2xhc3M9InFiIiBvbmNsaWNrPSJxdWlja0FjdCgke0pTT04uc3RyaW5naWZ5KGIpfSkiPiR7Yn08L2J1dHRvbj5gCiAgKS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gY2xhc3NpZnlFbnRyeSh0eHQpIHsKICBpZiAoL1suXVJvbGw6fFsuXVNhdmV8ZDIwID18aW5pdGlhdGl2ZS9pLnRlc3QodHh0KSkgcmV0dXJuICdyb2xsJzsKICBpZiAoL2F0dGFja3xoaXR8ZGFtYWdlfHdvdW5kfGJsb29kfHNsYXl8Y29tYmF0fHN0cmlrZS9pLnRlc3QodHh0KSkgcmV0dXJuICdjb21iYXQnOwogIGlmICgvZ29sZHxncHx0cmVhc3VyZXxsb290fGZvdW5kfGNvaW4vaS50ZXN0KHR4dCkpIHJldHVybiAnbG9vdCc7CiAgcmV0dXJuICdnbSc7Cn0KCmZ1bmN0aW9uIGFkZEVudHJ5KGh0bWwsIHR5cGUsIGF1dGhvcikgeyByZXR1cm4gYWRkRW50cnlSYXcoaHRtbCwgdHlwZSwgYXV0aG9yKTsgfQoKZnVuY3Rpb24gYWRkRW50cnlSYXcoaHRtbCwgdHlwZSwgYXV0aG9yKSB7CiAgY29uc3QgbG9nID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2xvZycpOwogIGNvbnN0IGQgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCdkaXYnKTsKICBpZiAodHlwZSA9PT0gJ3N5c3RlbS1yb2xsJykgewogICAgZC5jbGFzc05hbWUgPSAnbG9nLXN5c3RlbS1yb2xsJzsKICAgIGQuaW5uZXJIVE1MID0gaHRtbDsKICAgIGxvZy5hcHBlbmRDaGlsZChkKTsKICAgIGxvZy5zY3JvbGxUb3AgPSBsb2cuc2Nyb2xsSGVpZ2h0OwogICAgbG9nRW50cmllcy5wdXNoKHsgaHRtbCwgdHlwZSwgYXV0aG9yIH0pOwogICAgcmV0dXJuIGQ7CiAgfQogIGQuY2xhc3NOYW1lID0gJ2VudHJ5ICcgKyAoYXV0aG9yICYmIGF1dGhvciAhPT0gJ19fZ21fXycgPyAncGxheWVyLW1zZycgOiB0eXBlKTsKICBpZiAoYXV0aG9yICYmIGF1dGhvciAhPT0gJ19fZ21fXycgJiYgdHlwZSAhPT0gJ3N5c3RlbScpIHsKICAgIGNvbnN0IGNvbCA9IGdldENvbG9yKGF1dGhvcik7CiAgICBjb25zdCBoID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7CiAgICBoLmNsYXNzTmFtZSA9ICdlbnRyeS1hdXRob3InOwogICAgaC5zdHlsZS5jb2xvciA9IGNvbDsKICAgIGgudGV4dENvbnRlbnQgPSBhdXRob3I7CiAgICBkLmFwcGVuZENoaWxkKGgpOwogIH0KICBjb25zdCBjID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7CiAgYy5pbm5lckhUTUwgPSBodG1sOwogIGQuYXBwZW5kQ2hpbGQoYyk7CiAgbG9nLmFwcGVuZENoaWxkKGQpOwogIGxvZy5zY3JvbGxUb3AgPSBsb2cuc2Nyb2xsSGVpZ2h0OwogIGxvZ0VudHJpZXMucHVzaCh7IGh0bWwsIHR5cGUsIGF1dGhvciB9KTsKICByZXR1cm4gZDsKfQoKZnVuY3Rpb24gZm10KHR4dCkgewogIHJldHVybiB0eHQKICAgIC5yZXBsYWNlKC8mL2csJyZhbXA7JykucmVwbGFjZSgvPC9nLCcmbHQ7JykucmVwbGFjZSgvPi9nLCcmZ3Q7JykKICAgIC5yZXBsYWNlKC9bLl0oW15bLl1dKylbLl0vZywnPHNwYW4gY2xhc3M9InJvbGwtdGFnIj5bJDFdPC9zcGFuPicpCiAgICAucmVwbGFjZSgvWy5dWy5dKFteKl0rKVsuXVsuXS9nLCc8c3Ryb25nPiQxPC9zdHJvbmc+JykKICAgIC5yZXBsYWNlKC9bLl0oW14qXSspWy5dL2csJzxlbT4kMTwvZW0+Jyk7Cn0KCmZ1bmN0aW9uIHB1c2hNZXNzYWdlKGh0bWwsIHR5cGUsIGF1dGhvcikgewogIGlmICghaXNNdWx0aXBsYXllciB8fCAhcm9vbUNvZGUpIHJldHVybjsKICB4aHJGZXRjaChCQVNFX1VSTCArICcvcHVzaF9tZXNzYWdlJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOnJvb21Db2RlLCBodG1sLCB0eXBlLCBhdXRob3IsIHNlcTogKytsYXN0U2VxfSl9KTsKfQoKZnVuY3Rpb24gcGFyc2VTdGF0ZShyYXcpIHsKICB0cnkgewogICAgLy8gVHJ5IDxTVEFURT57Li4ufTwvU1RBVEU+IGZpcnN0CiAgICBsZXQgbSA9IHJhdy5tYXRjaCgvPFNUQVRFPihbLl1bWy5dc1suXVNdKj9bLl0pWy5dcyo8Wy5dU1RBVEU+Lyk7CiAgICBpZiAobSkgcmV0dXJuIEpTT04ucGFyc2UobVsxXSk7CiAgICAvLyBGYWxsIGJhY2sgdG8gW1NUQVRFXXsuLi59IChPbGxhbWEgc29tZXRpbWVzIHVzZXMgc3F1YXJlIGJyYWNrZXRzKQogICAgbSA9IHJhdy5tYXRjaCgvWy5dU1RBVEVbLl0oWy5dW1suXXNbLl1TXSo/Wy5dKS8pOwogICAgaWYgKG0pIHJldHVybiBKU09OLnBhcnNlKG1bMV0pOwogIH0gY2F0Y2goZSkge30KICByZXR1cm4gbnVsbDsKfQoKZnVuY3Rpb24gc3RyaXBTdGF0ZShyYXcpIHsgcmV0dXJuIHJhdy5yZXBsYWNlKC88U1RBVEU+W1suXXNbLl1TXSo/PFsuXVNUQVRFPi9nLCcnKS5yZXBsYWNlKC9bLl1TVEFURVsuXVtbLl1zWy5dU10qPyg/PVsuXW5bLl1ufCQpL2csJycpLnJlcGxhY2UoL1suXVNUQVRFWy5dWy5dW1suXXNbLl1TXSo/Wy5dWy5dcyovZywnJykudHJpbSgpOyB9CgpmdW5jdGlvbiBhcHBseVN0YXRlKGdzKSB7CiAgaWYgKCFncykgcmV0dXJuOwogIGlmIChncy5ocCE9PXVuZGVmaW5lZCkgcGMuaHA9Z3MuaHA7CiAgaWYgKGdzLm1heGhwIT09dW5kZWZpbmVkKSBwYy5tYXhocD1ncy5tYXhocDsKICBpZiAoZ3MuaW52JiZncy5pbnYubGVuZ3RoKSBwYy5pbnY9Z3MuaW52OwogIGlmIChncy5nb2xkIT09dW5kZWZpbmVkKSBwYy5nb2xkPWdzLmdvbGQ7CiAgaWYgKGdzLmxvYykgcGMubG9jPWdzLmxvYzsKICBpZiAoZ3MubG9jdGFnIT09dW5kZWZpbmVkKSB7CiAgICBjb25zdCB3YXNJbkR1bmdlb24gPSBpc0luRHVuZ2VvbigpOwogICAgcGMubG9jdGFnPWdzLmxvY3RhZzsKICAgIC8vIFJlc2V0IHJlc3QgY291bnRlciB3aGVuIGxlYXZpbmcgdGhlIGR1bmdlb24KICAgIGlmICh3YXNJbkR1bmdlb24gJiYgIWlzSW5EdW5nZW9uKCkpIHsKICAgICAgdHVybnNXaXRob3V0UmVzdCA9IDA7CiAgICAgIGZhdGlndWVQZW5hbHR5ID0gMDsKICAgIH0KICB9CiAgaWYgKGdzLnF1ZXN0cykgcGMucXVlc3RzPWdzLnF1ZXN0czsKICBpZiAoZ3MuYnV0dG9ucykgc2V0QnV0dG9ucyhncy5idXR0b25zKTsKICBpZiAoZ3MucGFydHkpIHsKICAgIE9iamVjdC5lbnRyaWVzKGdzLnBhcnR5KS5mb3JFYWNoKChbcG4scGRdKSA9PiB7CiAgICAgIGlmIChwYXJ0eVBDc1twbl0pIHsgcGFydHlQQ3NbcG5dLmhwPXBkLmhwfHxwYXJ0eVBDc1twbl0uaHA7IHBhcnR5UENzW3BuXS5tYXhocD1wZC5tYXhocHx8cGFydHlQQ3NbcG5dLm1heGhwOyB9CiAgICB9KTsKICAgIHJlbmRlclBhcnR5UGFuZWwoKTsKICAgIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlKSB7CiAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy91cGRhdGVfcm9vbScsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LCBib2R5OiBKU09OLnN0cmluZ2lmeSh7Y29kZTpyb29tQ29kZSwgcGFydHlQQ3MsIGdhbWVTdGF0ZTpnc30pfSk7CiAgICB9CiAgfQogIC8vIEF1dG8tc2F2ZSBjaGFyYWN0ZXIgcHJvZ3Jlc3MgYWZ0ZXIgZXZlcnkgZXhjaGFuZ2UKICBpZiAocGMuaWQpIHsKICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9zYXZlX2NoYXJhY3RlcicsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LCBib2R5OiBKU09OLnN0cmluZ2lmeShwYyl9KTsKICB9CiAgdXBkYXRlSFVEKCk7Cn0KCmZ1bmN0aW9uIGV4dHJhY3RBbmRQaW5GYWN0cyh0ZXh0KSB7CiAgLy8gUGF0dGVybnMgdGhhdCBzaWduYWwgYSBtZW1vcmFibGUgZmFjdAogIGNvbnN0IHBhdHRlcm5zID0gWwogICAgLy8gTlBDIG5hbWVzIGFuZCByb2xlcwogICAgLyhbQS1aXVthLXpdKyg/OlsuXXNbQS1aXVthLXpdKyk/KVsuXXMrKD86aXN8d2FzfGFyZXx3ZXJlKVsuXXMrKD86dGhlfGF8YW4pWy5dcysoW14uIT9dezUsNDB9KVsuIT9dL2csCiAgICAvLyBEZWF0aCBvZiBtb25zdGVycy9OUENzCiAgICAvKFtBLVpdW2Etel0rKD86Wy5dc1tBLVpdW2Etel0rKT8pWy5dcysoPzppc3xoYXMgYmVlbnx3YXMpWy5dcysoPzpraWxsZWR8c2xhaW58ZGVmZWF0ZWR8ZGVhZCkvZywKICAgIC8vIExvY2F0aW9ucyBkaXNjb3ZlcmVkCiAgICAvKD86ZW50ZXJ8ZGlzY292ZXJ8ZmluZHxyZXZlYWx8b3BlbilbLl1zKyg/OnRoZXxhfGFuKVsuXXMrKFteLiE/XXs1LDQwfSlbLiE/XS9naSwKICAgIC8vIEl0ZW1zIG9idGFpbmVkCiAgICAvKD86cGljayB1cHx0YWtlfGZpbmR8cmVjZWl2ZXxvYnRhaW58cG9ja2V0KVsuXXMrKD86dGhlfGF8YW4pWy5dcysoW14uIT9dezUsNDB9KVsuIT9dL2dpLAogICAgLy8gRG9vcnMvcGFzc2FnZXMgb3BlbmVkCiAgICAvKD86c2VjcmV0IGRvb3J8aGlkZGVuIHBhc3NhZ2V8Y29uY2VhbGVkIGVudHJhbmNlKVteLiE/XSooPzpvcGVufHJldmVhbHxmb3VuZClbXi4hP10qL2dpLAogIF07CgogIGNvbnN0IG5ld0ZhY3RzID0gW107CiAgcGF0dGVybnMuZm9yRWFjaChwYXR0ZXJuID0+IHsKICAgIGxldCBtYXRjaDsKICAgIGNvbnN0IHJlID0gbmV3IFJlZ0V4cChwYXR0ZXJuLnNvdXJjZSwgcGF0dGVybi5mbGFncyk7CiAgICB3aGlsZSAoKG1hdGNoID0gcmUuZXhlYyh0ZXh0KSkgIT09IG51bGwpIHsKICAgICAgY29uc3QgZmFjdCA9IG1hdGNoWzBdLnRyaW0oKTsKICAgICAgaWYgKGZhY3QubGVuZ3RoID4gMTUgJiYgZmFjdC5sZW5ndGggPCAxMjApIHsKICAgICAgICAvLyBBdm9pZCBkdXBsaWNhdGVzCiAgICAgICAgY29uc3Qgc2ltcGxpZmllZCA9IGZhY3QudG9Mb3dlckNhc2UoKS5yZXBsYWNlKC9bXmEtejAtOSBdL2csICcnKTsKICAgICAgICBjb25zdCBpc0R1cCA9IHBpbm5lZEZhY3RzLnNvbWUoZiA9PgogICAgICAgICAgZi50b0xvd2VyQ2FzZSgpLnJlcGxhY2UoL1teYS16MC05IF0vZywgJycpLmluY2x1ZGVzKHNpbXBsaWZpZWQuc3Vic3RyaW5nKDAsIDIwKSkKICAgICAgICApOwogICAgICAgIGlmICghaXNEdXApIG5ld0ZhY3RzLnB1c2goZmFjdCk7CiAgICAgIH0KICAgIH0KICB9KTsKCiAgLy8gQWRkIG5ldyBmYWN0cywgY2FwIGF0IE1BWF9QSU5ORURfRkFDVFMKICBwaW5uZWRGYWN0cy5wdXNoKC4uLm5ld0ZhY3RzKTsKICBpZiAocGlubmVkRmFjdHMubGVuZ3RoID4gTUFYX1BJTk5FRF9GQUNUUykgewogICAgcGlubmVkRmFjdHMgPSBwaW5uZWRGYWN0cy5zbGljZSgtTUFYX1BJTk5FRF9GQUNUUyk7CiAgfQp9CgpmdW5jdGlvbiB1cGRhdGVXb3JsZFN0YXRlKHJhd1Jlc3BvbnNlLCBnYW1lU3RhdGUpIHsKICAvLyBRdWVzdHMKICBpZiAoZ2FtZVN0YXRlICYmIGdhbWVTdGF0ZS5xdWVzdHMpIHsKICAgIHdvcmxkU3RhdGUucXVlc3RzX2FjdGl2ZSA9IGdhbWVTdGF0ZS5xdWVzdHMuZmlsdGVyKHE9PnEucz09PSdhY3RpdmUnKS5tYXAocT0+cS5uKTsKICB9CgogIC8vIEZpeCAyOiBUcmFjayBsb2NhdGlvbnMgKyBjYWNoZSBhdG1vc3BoZXJlCiAgaWYgKGdhbWVTdGF0ZSAmJiBnYW1lU3RhdGUubG9jICYmIGdhbWVTdGF0ZS5sb2MgIT09ICcuLi4nKSB7CiAgICBjb25zdCBsb2MgPSBnYW1lU3RhdGUubG9jOwogICAgaWYgKCF3b3JsZFN0YXRlLmxvY2F0aW9uc192aXNpdGVkW2xvY10pIHsKICAgICAgd29ybGRTdGF0ZS5sb2NhdGlvbnNfdmlzaXRlZFtsb2NdID0geyBmaXJzdF92aXNpdGVkOiB0dXJuQ291bnQsIHRhZzogZ2FtZVN0YXRlLmxvY3RhZ3x8JycgfTsKICAgIH0KICAgIGlmICghbG9jYXRpb25BdG1vc3BoZXJlW2xvY10pIHsKICAgICAgY29uc3QgZmlyc3RTZW50ZW5jZSA9IHJhd1Jlc3BvbnNlLnNwbGl0KC9bLiE/XS8pWzBdLnRyaW0oKTsKICAgICAgbG9jYXRpb25BdG1vc3BoZXJlW2xvY10gPSBmaXJzdFNlbnRlbmNlLnN1YnN0cmluZygwLDEyMCk7CiAgICB9CiAgICBjdXJyZW50QXRtb3NwaGVyZSA9IGxvY2F0aW9uQXRtb3NwaGVyZVtsb2NdIHx8ICcnOwogIH0KCiAgLy8gRml4IDE6IEJ1aWxkIE5QQyBwcm9maWxlcyB3aXRoIHNhbXBsZSBxdW90ZXMgZm9yIHZvaWNlIGNvbnNpc3RlbmN5CiAgY29uc3QgdGV4dEZvck5wYyA9IHJhd1Jlc3BvbnNlOwogIGNvbnN0IG5wY05hbWVzID0gT2JqZWN0LmtleXMobnBjUHJvZmlsZXMpLmNvbmNhdChPYmplY3Qua2V5cyh3b3JsZFN0YXRlLm5wY3NfbWV0KSk7CiAgLy8gRGV0ZWN0IG5ldyBOUENzIHNwZWFraW5nCiAgY29uc3Qgc3BlYWtXb3JkcyA9IFsnc2F5cycsJ3RlbGxzJywnd2hpc3BlcnMnLCdzaG91dHMnLCdyZXBsaWVzJywnYXNrcycsJ2dyb3dscycsJ211dHRlcnMnLCdzbmVlcnMnLCdsYXVnaHMnLCdzaWdocycsJ2JhcmtzJywnaGlzc2VzJywnZGVjbGFyZXMnLCdhbm5vdW5jZXMnXTsKICBzcGVha1dvcmRzLmZvckVhY2godmVyYiA9PiB7CiAgICBjb25zdCBwYXQgPSBuZXcgUmVnRXhwKCcoW0EtWl1bYS16XXsyLDIwfSg/OlsuXXNbQS1aXVthLXpdezIsMjB9KT8pKD86W14sXXswLDIwfSknICsgdmVyYiArICdbXixdKlssXT8oW14sXXsxMCwxMDB9KScsICdnaScpOwogICAgbGV0IG07CiAgICB3aGlsZSAoKG0gPSBwYXQuZXhlYyh0ZXh0Rm9yTnBjKSkgIT09IG51bGwpIHsKICAgICAgY29uc3QgbmFtZSA9IG1bMV0udHJpbSgpOwogICAgICBjb25zdCBxdW90ZSA9IG1bMl0udHJpbSgpOwogICAgICBpZiAoWydUaGUnLCdZb3UnLCdZb3VyJywnSGUnLCdTaGUnLCdUaGV5JywnSXQnLCdUaGlzJywnVGhhdCddLmluY2x1ZGVzKG5hbWUpKSBjb250aW51ZTsKICAgICAgaWYgKCFucGNQcm9maWxlc1tuYW1lXSkgbnBjUHJvZmlsZXNbbmFtZV0gPSB7IGZpcnN0X21ldDogdHVybkNvdW50LCBxdW90ZXM6IFtdLCBhdHRpdHVkZTogJ3Vua25vd24nIH07CiAgICAgIGlmIChucGNQcm9maWxlc1tuYW1lXS5xdW90ZXMubGVuZ3RoIDwgMykgbnBjUHJvZmlsZXNbbmFtZV0ucXVvdGVzLnB1c2gocXVvdGUpOwogICAgICBpZiAoIXdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0pIHdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0gPSB7IGF0dGl0dWRlOiAndW5rbm93bicsIGZpcnN0X21ldDogdHVybkNvdW50IH07CiAgICB9CiAgfSk7CgogIC8vIE5QQyBhdHRpdHVkZSBkZXRlY3Rpb24KICBjb25zdCBhdHRpdHVkZVBhdCA9IC8oW0EtWl1bYS16XXsyLDIwfSg/OlsuXXNbQS1aXVthLXpdezIsMjB9KT8pWy5dcysoPzpzZWVtc3xhcHBlYXJzfGxvb2tzfGlzKVsuXXMrKGZyaWVuZGx5fGhvc3RpbGV8bmVydm91c3xhZnJhaWR8c3VzcGljaW91c3xwbGVhc2VkfGFuZ3J5fGZyaWdodGVuZWR8d2FyeXxncmF0ZWZ1bCkvZ2k7CiAgbGV0IG0yOwogIHdoaWxlICgobTIgPSBhdHRpdHVkZVBhdC5leGVjKHJhd1Jlc3BvbnNlKSkgIT09IG51bGwpIHsKICAgIGNvbnN0IG5hbWUgPSBtMlsxXTsKICAgIGlmIChbJ1RoZScsJ1lvdScsJ1lvdXInLCdIZScsJ1NoZScsJ1RoZXknXS5pbmNsdWRlcyhuYW1lKSkgY29udGludWU7CiAgICBpZiAoIXdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0pIHdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0gPSB7IGF0dGl0dWRlOiBtMlsyXS50b0xvd2VyQ2FzZSgpLCBmaXJzdF9tZXQ6IHR1cm5Db3VudCB9OwogICAgZWxzZSB3b3JsZFN0YXRlLm5wY3NfbWV0W25hbWVdLmF0dGl0dWRlID0gbTJbMl0udG9Mb3dlckNhc2UoKTsKICAgIGlmIChucGNQcm9maWxlc1tuYW1lXSkgbnBjUHJvZmlsZXNbbmFtZV0uYXR0aXR1ZGUgPSBtMlsyXS50b0xvd2VyQ2FzZSgpOwogIH0KCiAgLy8gTW9uc3RlciBraWxscwogIGNvbnN0IGtpbGxQYXQgPSAvKFtBLVpdW2Etel17MiwyNX0oPzpbLl1zW0EtWl1bYS16XXsyLDI1fSk/KVteLl17MCwzMH0oPzppcyBraWxsZWR8aXMgc2xhaW58ZGllc3xmYWxscyBkZWFkfGNydW1wbGVzfGNvbGxhcHNlcyBkZWFkKS9naTsKICBsZXQgbTM7CiAgd2hpbGUgKChtMyA9IGtpbGxQYXQuZXhlYyhyYXdSZXNwb25zZSkpICE9PSBudWxsKSB7CiAgICBjb25zdCBuYW1lID0gbTNbMV07CiAgICBpZiAoIXdvcmxkU3RhdGUubW9uc3RlcnNfa2lsbGVkLmluY2x1ZGVzKG5hbWUpKSB3b3JsZFN0YXRlLm1vbnN0ZXJzX2tpbGxlZC5wdXNoKG5hbWUpOwogIH0KCiAgLy8gRml4IDU6IFBlcm1hbmVudCB3b3JsZC1jaGFuZ2luZyBldmVudHMKICBjb25zdCBjaGFuZ2VQYXQgPSAvKD86YnVybig/OmVkfHN8aW5nKXxkZXN0cm95KD86ZWR8cyl8Y29sbGFwc2UoPzpkfHMpfGFsYXJtKD86ZWR8cyl8YWxlcnQoPzplZHxzKXxnYXRlICg/Om9wZW5zfGNsb3Nlc3xpcyBvcGVuKXxmaXJlICg/OnNwcmVhZHN8YnVybnMpKVteLiE/XXswLDgwfVsuIT9dL2dpOwogIGxldCBtNDsKICB3aGlsZSAoKG00ID0gY2hhbmdlUGF0LmV4ZWMocmF3UmVzcG9uc2UpKSAhPT0gbnVsbCkgewogICAgY29uc3QgZXZlbnQgPSBtNFswXS50cmltKCkuc3Vic3RyaW5nKDAsMTAwKTsKICAgIGlmICghd29ybGRTdGF0ZS53b3JsZF9jaGFuZ2VzLnNvbWUoZSA9PiBlLmluY2x1ZGVzKGV2ZW50LnN1YnN0cmluZygwLDIwKSkpKSB7CiAgICAgIHdvcmxkU3RhdGUud29ybGRfY2hhbmdlcy5wdXNoKCdUdXJuICcgKyB0dXJuQ291bnQgKyAnOiAnICsgZXZlbnQpOwogICAgfQogIH0KICBpZiAod29ybGRTdGF0ZS53b3JsZF9jaGFuZ2VzLmxlbmd0aCA+IDE1KSB3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMgPSB3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMuc2xpY2UoLTE1KTsKCiAgLy8gRml4IDY6IFVwZGF0ZSBzZXNzaW9uIHRvbmUKICBjb25zdCBjdyA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoYXR0YWNrfGNvbWJhdHxmaWdodHxzdHJpa2V8d291bmR8Ymxvb2R8d2VhcG9ufHNsYXl8YmF0dGxlKVxiL2dpKXx8W10pLmxlbmd0aDsKICBjb25zdCB0dyA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoZGFuZ2VyfHRyYXB8cG9pc29ufGZsZWV8c2NyZWFtfGRlYXRofGRpZXN8a2lsbGVkfHRlcnJvcilcYi9naSl8fFtdKS5sZW5ndGg7CiAgY29uc3Qgc3cgPSAocmF3UmVzcG9uc2UubWF0Y2goL1xiKHNheXN8YXNrc3x0ZWxsc3xzcGVha3N8bmVnb3RpYXRlfHBlcnN1YWRlfGNoYXJtfGNvbnZlcnNhdGlvbilcYi9naSl8fFtdKS5sZW5ndGg7CiAgY29uc3QgZXcgPSAocmF3UmVzcG9uc2UubWF0Y2goL1xiKHNlYXJjaHxleGFtaW5lfGV4cGxvcmV8ZGlzY292ZXJ8ZmluZHxvcGVufHBhc3NhZ2V8ZG9vcnxjb3JyaWRvcilcYi9naSl8fFtdKS5sZW5ndGg7CiAgY29uc3QgbWF4ID0gTWF0aC5tYXgoY3csIHR3LCBzdywgZXcpOwogIGlmIChtYXggPiAyKSB7CiAgICBpZiAoY3cgPT09IG1heCkgc2Vzc2lvblRvbmUgPSAnY29tYmF0LWhlYXZ5JzsKICAgIGVsc2UgaWYgKHR3ID09PSBtYXgpIHNlc3Npb25Ub25lID0gJ3RlbnNlJzsKICAgIGVsc2UgaWYgKHN3ID09PSBtYXgpIHNlc3Npb25Ub25lID0gJ3NvY2lhbCc7CiAgICBlbHNlIHNlc3Npb25Ub25lID0gJ2V4cGxvcmF0b3J5JzsKICB9CgogIC8vIFJvdGF0ZSBiYW5uZWQgcGhyYXNlcyBldmVyeSA0IHR1cm5zCiAgaWYgKHR1cm5Db3VudCAlIDQgPT09IDApIHJvdGF0ZUJhbm5lZFBocmFzZXMoKTsKfQoKZnVuY3Rpb24gYnVpbGRXb3JsZFN0YXRlQmxvY2soKSB7CiAgY29uc3QgbGluZXMgPSBbXTsKCiAgLy8gRml4IDE6IE5QQyBwcm9maWxlcyB3aXRoIHZvaWNlIHNhbXBsZXMgZm9yIGNvbnNpc3RlbmN5CiAgY29uc3QgbnBjRW50cmllcyA9IE9iamVjdC5lbnRyaWVzKG5wY1Byb2ZpbGVzKTsKICBpZiAobnBjRW50cmllcy5sZW5ndGggPiAwKSB7CiAgICBsaW5lcy5wdXNoKCdLTk9XTiBOUENzIC0tIG1haW50YWluIHRoZWlyIHZvaWNlIGFuZCBhdHRpdHVkZSBjb25zaXN0ZW50bHk6Jyk7CiAgICBucGNFbnRyaWVzLnNsaWNlKC04KS5mb3JFYWNoKChbbmFtZSwgZGF0YV0pID0+IHsKICAgICAgbGV0IGVudHJ5ID0gJyAgJyArIG5hbWUgKyAnOiBhdHRpdHVkZT0nICsgZGF0YS5hdHRpdHVkZTsKICAgICAgaWYgKGRhdGEucXVvdGVzICYmIGRhdGEucXVvdGVzLmxlbmd0aCA+IDApIGVudHJ5ICs9ICcgfCBTYW1wbGUgc3BlZWNoOiAiJyArIGRhdGEucXVvdGVzWzBdICsgJyInOwogICAgICBsaW5lcy5wdXNoKGVudHJ5KTsKICAgIH0pOwogIH0gZWxzZSBpZiAoT2JqZWN0LmtleXMod29ybGRTdGF0ZS5ucGNzX21ldCkubGVuZ3RoID4gMCkgewogICAgbGluZXMucHVzaCgnTlBDcyBlbmNvdW50ZXJlZDogJyArIE9iamVjdC5lbnRyaWVzKHdvcmxkU3RhdGUubnBjc19tZXQpLm1hcCgoW24sZF0pPT5uKycgKCcrZC5hdHRpdHVkZSsnKScpLmpvaW4oJywgJykpOwogIH0KCiAgLy8gRml4IDI6IEN1cnJlbnQgbG9jYXRpb24gYXRtb3NwaGVyZQogIGlmIChjdXJyZW50QXRtb3NwaGVyZSkgbGluZXMucHVzaCgnQ3VycmVudCBhdG1vc3BoZXJlOiAnICsgY3VycmVudEF0bW9zcGhlcmUpOwoKICAvLyBGaXggNjogU2Vzc2lvbiB0b25lIGd1aWRhbmNlCiAgY29uc3QgdG9uZXMgPSB7CiAgICAnY29tYmF0LWhlYXZ5JzogJ0NvbWJhdC1oZWF2eSAtLSBrZWVwIHRlbnNpb24gaGlnaCwgd291bmRzIHZpdmlkLCBkYW5nZXIgcmVhbCcsCiAgICAndGVuc2UnOiAgICAgICAgJ1RlbnNlIC0tIHNob3J0IHNlbnRlbmNlcywgYnVpbGQgZHJlYWQsIGVtcGhhc2lzZSB1bmNlcnRhaW50eScsCiAgICAnc29jaWFsJzogICAgICAgJ1NvY2lhbCAtLSBsZXQgZGlhbG9ndWUgYnJlYXRoZSwgc2hvdyBwZXJzb25hbGl0eSBhbmQgc3VidGV4dCcsCiAgICAnZXhwbG9yYXRvcnknOiAgJ0V4cGxvcmF0b3J5IC0tIHJld2FyZCBjdXJpb3NpdHksIGRlc2NyaWJlIHJpY2hseSwgaGludCBhdCBzZWNyZXRzJywKICB9OwogIGlmICh0b25lc1tzZXNzaW9uVG9uZV0pIGxpbmVzLnB1c2goJ1Nlc3Npb24gdG9uZTogJyArIHRvbmVzW3Nlc3Npb25Ub25lXSk7CgogIC8vIEZpeCA1OiBQZXJtYW5lbnQgd29ybGQgY2hhbmdlcwogIGlmICh3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMubGVuZ3RoID4gMCkgewogICAgbGluZXMucHVzaCgnV29ybGQgY2hhbmdlcyAocmVmbGVjdCBpbiBuYXJyYXRpb24pOicpOwogICAgd29ybGRTdGF0ZS53b3JsZF9jaGFuZ2VzLnNsaWNlKC01KS5mb3JFYWNoKGMgPT4gbGluZXMucHVzaCgnICAnICsgYykpOwogIH0KCiAgaWYgKHdvcmxkU3RhdGUubW9uc3RlcnNfa2lsbGVkLmxlbmd0aCA+IDApIGxpbmVzLnB1c2goJ0RlZmVhdGVkOiAnICsgd29ybGRTdGF0ZS5tb25zdGVyc19raWxsZWQuc2xpY2UoLTgpLmpvaW4oJywgJykpOwogIGNvbnN0IGxvY3MgPSBPYmplY3Qua2V5cyh3b3JsZFN0YXRlLmxvY2F0aW9uc192aXNpdGVkKTsKICBpZiAobG9jcy5sZW5ndGggPiAwKSBsaW5lcy5wdXNoKCdFeHBsb3JlZDogJyArIGxvY3Muc2xpY2UoLTYpLmpvaW4oJywgJykpOwogIGlmICh3b3JsZFN0YXRlLnF1ZXN0c19hY3RpdmUubGVuZ3RoID4gMCkgbGluZXMucHVzaCgnQWN0aXZlIHF1ZXN0czogJyArIHdvcmxkU3RhdGUucXVlc3RzX2FjdGl2ZS5qb2luKCcsICcpKTsKCiAgcmV0dXJuIGxpbmVzLmxlbmd0aCA+IDAgPyBsaW5lcy5qb2luKCdbLl1uJykgOiBudWxsOwp9CgpmdW5jdGlvbiBidWlsZFBpbm5lZEZhY3RzQmxvY2soKSB7CiAgaWYgKCFwaW5uZWRGYWN0cy5sZW5ndGgpIHJldHVybiBudWxsOwogIHJldHVybiBwaW5uZWRGYWN0cy5zbGljZSgtMTUpLmpvaW4oJ1suXW4nKTsKfQoKYXN5bmMgZnVuY3Rpb24gZ2VuZXJhdGVTdW1tYXJ5KCkgewogIGlmIChoaXN0b3J5Lmxlbmd0aCA8IDQpIHJldHVybjsgLy8gbm90IGVub3VnaCB0byBzdW1tYXJpc2UgeWV0CgogIGNvbnNvbGUubG9nKCdbTWVtb3J5XSBHZW5lcmF0aW5nIHJvbGxpbmcgc3VtbWFyeS4uLicpOwogIGNvbnN0IHN1bW1hcnlQcm9tcHQgPSBgWW91IGFyZSBzdW1tYXJpc2luZyBhIEQmRCBhZHZlbnR1cmUgc2Vzc2lvbiBmb3IgbWVtb3J5IHB1cnBvc2VzLgoKUHJldmlvdXMgc3VtbWFyeSAoaWYgYW55KToKJHttZW1vcnlTdW1tYXJ5IHx8ICdOb25lIC0tIHRoaXMgaXMgdGhlIGZpcnN0IHN1bW1hcnkuJ30KClJlY2VudCBldmVudHMgdG8gaW5jb3Jwb3JhdGU6CiR7aGlzdG9yeS5zbGljZSgtTWF0aC5taW4oaGlzdG9yeS5sZW5ndGgsIDE0KSkubWFwKG0gPT4KICBtLnJvbGUgPT09ICd1c2VyJyA/ICdQTEFZRVI6ICcgKyBtLmNvbnRlbnQuc3Vic3RyaW5nKDAsIDIwMCkKICAgICAgICAgICAgICAgICAgICA6ICdHTTogJyArIHN0cmlwU3RhdGUobS5jb250ZW50KS5zdWJzdHJpbmcoMCwgNDAwKQopLmpvaW4oJ1suXW4nKX0KCldyaXRlIGEgY29uY2lzZSBidXQgY29tcGxldGUgc3VtbWFyeSAoMTUwLTIwMCB3b3JkcykgY292ZXJpbmc6CjEuIFdoYXQgaGFzIGhhcHBlbmVkIGluIHRoZSBhZHZlbnR1cmUgc28gZmFyCjIuIFdoZXJlIHRoZSBwYXJ0eSBjdXJyZW50bHkgaXMKMy4gS2V5IE5QQ3MgdGhleSBoYXZlIG1ldCBhbmQgdGhlaXIgcmVsYXRpb25zaGlwCjQuIEltcG9ydGFudCBpdGVtcyBmb3VuZCBvciBsb3N0CjUuIEN1cnJlbnQgZ29hbHMgYW5kIHRocmVhdHMKNi4gQW55IGVzdGFibGlzaGVkIGZhY3RzIHRoYXQgbXVzdCBub3QgYmUgZm9yZ290dGVuCgpXcml0ZSBpbiBwYXN0IHRlbnNlLiBCZSBzcGVjaWZpYyB3aXRoIG5hbWVzLCBwbGFjZXMsIGFuZCBmYWN0cy4gRG8gbm90IGludmVudCBhbnl0aGluZyBub3QgcHJlc2VudCBhYm92ZS5gOwoKICB0cnkgewogICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9haScsIHsKICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgIGhlYWRlcnM6IHsnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICAgIGFwaV9rZXk6IGFwaUtleSwKICAgICAgICBzeXN0ZW06ICdZb3UgYXJlIGEgcHJlY2lzZSBzdW1tYXJpc2VyLiBTdW1tYXJpc2UgYWNjdXJhdGVseSBhbmQgY29uY2lzZWx5LiBOZXZlciBpbnZlbnQgZmFjdHMuJywKICAgICAgICBtZXNzYWdlczogW3tyb2xlOiAndXNlcicsIGNvbnRlbnQ6IHN1bW1hcnlQcm9tcHR9XQogICAgICB9KQogICAgfSk7CiAgICBpZiAoIXJlc3Aub2spIHJldHVybjsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKICAgIGlmIChkYXRhLmNvbnRlbnQgJiYgIWRhdGEuZXJyb3IpIHsKICAgICAgbWVtb3J5U3VtbWFyeSA9IHN0cmlwU3RhdGUoZGF0YS5jb250ZW50KS50cmltKCk7CiAgICAgIGNvbnNvbGUubG9nKCdbTWVtb3J5XSBTdW1tYXJ5IGdlbmVyYXRlZDonLCBtZW1vcnlTdW1tYXJ5Lmxlbmd0aCwgJ2NoYXJzJyk7CgogICAgICAvLyBBZnRlciBzdW1tYXJpc2luZywgdHJpbSBoaXN0b3J5IHRvIGxhc3QgTUFYX0hJU1RPUllfQkVGT1JFX1NVTU1BUlkgbWVzc2FnZXMKICAgICAgLy8gYnV0IGtlZXAgdGhlIGZpcnN0IGV4Y2hhbmdlIChvcGVuaW5nIHNjZW5lKSBmb3IgY29udGV4dAogICAgICBpZiAoaGlzdG9yeS5sZW5ndGggPiBNQVhfSElTVE9SWV9CRUZPUkVfU1VNTUFSWSArIDIpIHsKICAgICAgICBjb25zdCBmaXJzdFR3byA9IGhpc3Rvcnkuc2xpY2UoMCwgMik7CiAgICAgICAgY29uc3QgcmVjZW50ID0gaGlzdG9yeS5zbGljZSgtTUFYX0hJU1RPUllfQkVGT1JFX1NVTU1BUlkpOwogICAgICAgIGhpc3RvcnkgPSBbLi4uZmlyc3RUd28sIC4uLnJlY2VudF07CiAgICAgICAgY29uc29sZS5sb2coJ1tNZW1vcnldIEhpc3RvcnkgdHJpbW1lZCB0bycsIGhpc3RvcnkubGVuZ3RoLCAnbWVzc2FnZXMnKTsKICAgICAgfQogICAgfQogIH0gY2F0Y2goZSkgewogICAgY29uc29sZS53YXJuKCdbTWVtb3J5XSBTdW1tYXJ5IGZhaWxlZDonLCBlLm1lc3NhZ2UpOwogIH0KfQoKZnVuY3Rpb24gYnVpbGRNZW1vcnlDb250ZXh0KCkgewogIGNvbnN0IHBhcnRzID0gW107CgogIC8vIEdNIEJyaWVmaW5nIGFsd2F5cyBmaXJzdCAtLSBoaWdoZXN0IHByaW9yaXR5IGNvbnRleHQKICBpZiAoZ21CcmllZmluZykgewogICAgcGFydHMucHVzaChnbUJyaWVmaW5nKTsKICB9CgogIGlmIChtZW1vcnlTdW1tYXJ5KSB7CiAgICBwYXJ0cy5wdXNoKCc9PT0gU1RPUlkgU08gRkFSID09PVsuXW4nICsgbWVtb3J5U3VtbWFyeSk7CiAgfQoKICBjb25zdCB3b3JsZEJsb2NrID0gYnVpbGRXb3JsZFN0YXRlQmxvY2soKTsKICBpZiAod29ybGRCbG9jaykgewogICAgcGFydHMucHVzaCgnPT09IEVTVEFCTElTSEVEIFdPUkxEIFNUQVRFID09PVsuXW4nICsgd29ybGRCbG9jayk7CiAgfQoKICBjb25zdCBmYWN0c0Jsb2NrID0gYnVpbGRQaW5uZWRGYWN0c0Jsb2NrKCk7CiAgaWYgKGZhY3RzQmxvY2spIHsKICAgIHBhcnRzLnB1c2goJz09PSBQSU5ORUQgRkFDVFMgKGRvIG5vdCBjb250cmFkaWN0IHRoZXNlKSA9PT1bLl1uJyArIGZhY3RzQmxvY2spOwogIH0KCiAgcmV0dXJuIHBhcnRzLmxlbmd0aCA+IDAgPyAnWy5dblsuXW4nICsgcGFydHMuam9pbignWy5dblsuXW4nKSA6ICcnOwp9CgpmdW5jdGlvbiByZXNldE1lbW9yeSgpIHsKICBtZW1vcnlTdW1tYXJ5ID0gJyc7CiAgd29ybGRTdGF0ZSA9IHsKICAgIG5wY3NfbWV0OiB7fSwgbG9jYXRpb25zX3Zpc2l0ZWQ6IHt9LCBpdGVtc19mb3VuZDogW10sCiAgICBwbG90X3BvaW50czogW10sIGRvb3JzX29wZW5lZDogW10sIHRyYXBzX3NwcnVuZzogW10sCiAgICBtb25zdGVyc19raWxsZWQ6IFtdLCBxdWVzdHNfYWN0aXZlOiBbXSwgd29ybGRfY2hhbmdlczogW10sCiAgfTsKICBucGNQcm9maWxlcyA9IHt9OwogIGxvY2F0aW9uQXRtb3NwaGVyZSA9IHt9OwogIGN1cnJlbnRBdG1vc3BoZXJlID0gJyc7CiAgc2Vzc2lvblRvbmUgPSAnZXhwbG9yYXRvcnknOwogIHBpbm5lZEZhY3RzID0gW107CiAgdHVybkNvdW50ID0gMDsKICBnbUJyaWVmaW5nID0gJyc7CiAgbnBjS25vd2xlZGdlTWFwID0ge307CiAgcm90YXRlQmFubmVkUGhyYXNlcygpOwogIC8vIFJlc2V0IGFsbCBuZXcgc3lzdGVtcwogIHBhY2luZ0hpc3RvcnkgPSBbXTsgY3VycmVudFBhY2luZ1BoYXNlID0gJ29wZW5pbmcnOwogIHR1cm5zU2luY2VMYXN0Q29tYmF0ID0gMDsgdHVybnNTaW5jZUxhc3RSZXN0ID0gMDsKICBjb25zZXF1ZW5jZXMgPSBbXTsgcGVuZGluZ0NvbnNlcXVlbmNlcyA9IFtdOwogIGluQ29tYmF0ID0gZmFsc2U7CiAgY29tYmF0U3RhdGUgPSB7IHJvdW5kOjAsIGluaXRpYXRpdmVPcmRlcjpbXSwgYWN0aXZlSW5kZXg6MCwgcGxheWVyQWN0aW9uOicnLCBsYXN0Um91bmRTdW1tYXJ5OicnIH07CiAgZHVuZ2VvblR1cm5zID0gMDsgdG9yY2hUdXJuc0xlZnQgPSAwOyBoYXNMYW50ZXJuID0gZmFsc2U7CiAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSAwOyByYXRpb25zTGVmdCA9IDA7IHJlc3REZWJ0ID0gMDsgaXNDYXJyeWluZ0xpZ2h0ID0gdHJ1ZTsKICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOyB3YW5kZXJpbmdNb25zdGVyQ2hlY2tEdWUgPSBmYWxzZTsKfQoKYXN5bmMgZnVuY3Rpb24gc2VydmVyUm9sbCh0eXBlLCBwYXJhbXM9e30pIHsKICB0cnkgewogICAgY29uc3QgciA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9hY3Rpb24nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoe3RleHQ6IEpTT04uc3RyaW5naWZ5KHt0eXBlLCAuLi5wYXJhbXN9KSwgcGMsIGdhbWVfc3RhdGU6IGJ1aWxkR2FtZVN0YXRlKCksCiAgICAgICAgaGlzdG9yeTpbXSwgYXBpX2tleTogYXBpS2V5fHwnJywgcm9sbF9vbmx5OnRydWV9KX0pOwogICAgcmV0dXJuIGF3YWl0IHIuanNvbigpOwogIH0gY2F0Y2goZSkgewogICAgcmV0dXJuIHtlcnJvcjogZS5tZXNzYWdlLCBmbXQ6IGBbcm9sbCBlcnJvcl1gfTsKICB9Cn0KCmFzeW5jIGZ1bmN0aW9uIHJvbGxEaWNlKHNpZGVzLCBjb3VudD0xKSB7CiAgY29uc3QgcmVzdWx0ID0gYXdhaXQgc2VydmVyUm9sbCgnZGljZScsIHtzaWRlcywgY291bnR9KTsKICByZXR1cm4gcmVzdWx0LmZtdCB8fCBgWyR7Y291bnR9ZCR7c2lkZXN9IHJvbGwgZmFpbGVkXWA7Cn0KCmZ1bmN0aW9uIHNob3dSb29tQ29kZSgpIHsKICBpZiAoIXJvb21Db2RlKSByZXR1cm47CiAgY29uc3Qgd3JhcCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3Atcm9vbS13cmFwJyk7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJvb20nKTsKICBpZiAod3JhcCkgd3JhcC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogIGlmIChlbCkgZWwudGV4dENvbnRlbnQgPSByb29tQ29kZTsKfQoKZnVuY3Rpb24gY29weVJvb21Db2RlKCkgewogIGlmICghcm9vbUNvZGUpIHJldHVybjsKICBuYXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChyb29tQ29kZSkudGhlbigoKSA9PiB7CiAgICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3Atcm9vbS1jb3B5Jyk7CiAgICBpZiAoZWwpIHsgZWwudGV4dENvbnRlbnQgPSAnJzsgc2V0VGltZW91dCgoKSA9PiB7IGVsLnRleHRDb250ZW50ID0gJyc7IH0sIDE1MDApOyB9CiAgfSk7Cn0KCmZ1bmN0aW9uIGNvbmZpcm1SZXNldCgpIHsKICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXNldC1tb2RhbCcpOwogIG1vZGFsLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7Cn0KCmZ1bmN0aW9uIGNsb3NlUmVzZXQoKSB7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlc2V0LW1vZGFsJykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKfQoKZnVuY3Rpb24gZG9SZXNldCgpIHsKICAvLyBIaWRlIHRoZSBtb2RhbCBpbW1lZGlhdGVseQogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXNldC1tb2RhbCcpLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CgogIC8vIFN0b3AgcG9sbGluZwogIGlmIChwb2xsVGltZXIpIHsgY2xlYXJJbnRlcnZhbChwb2xsVGltZXIpOyBwb2xsVGltZXIgPSBudWxsOyB9CgogIC8vIFJlc2V0IG1lbW9yeSBzeXN0ZW0KICByZXNldE1lbW9yeSgpOwoKICAvLyBTYXZlIG1vZHVsZSBpbmZvIGJlZm9yZSBjbGVhcmluZwogIGNvbnN0IHNhdmVkTW9kdWxlID0gbW9kdWxlVGV4dDsKICBjb25zdCBzYXZlZE1vZHVsZU5hbWUgPSBtb2R1bGVOYW1lOwogIGNvbnN0IHNhdmVkUnVsZXMgPSBjaG9zZW5SdWxlczsKCiAgLy8gUmVzZXQgYWxsIGdhbWUgc3RhdGUKICByb29tQ29kZSA9ICcnOyBpc011bHRpcGxheWVyID0gZmFsc2U7IGlzSG9zdCA9IGZhbHNlOwogIGNob3NlblJhY2UgPSAnSHVtYW4nOyBjaG9zZW5DbGFzcyA9ICdGaWdodGVyJzsgY2hvc2VuQWxpZ24gPSAnTmV1dHJhbCc7CiAgcm9sbGVkU3RhdHMgPSB7fTsgcGMgPSB7fTsgcGFydHlQQ3MgPSB7fTsKICBoaXN0b3J5ID0gW107IGxvZ0VudHJpZXMgPSBbXTsgYnVzeSA9IGZhbHNlOwogIHN5c3RlbVByb21wdCA9ICcnOyBsYXN0U2VxID0gMDsgdXBsb2FkZWRGaWxlID0gbnVsbDsKICBnb2xkU3BlbnQgPSAwOyBzZWxlY3RlZEVxdWlwID0ge307IGV4dHJhSXRlbXMgPSBbXTsKICBtb2R1bGVUZXh0ID0gc2F2ZWRNb2R1bGU7CiAgbW9kdWxlTmFtZSA9IHNhdmVkTW9kdWxlTmFtZTsKICBjaG9zZW5SdWxlcyA9IHNhdmVkUnVsZXM7CgogIC8vIENsZWFyIFVJIC0tIHVzZSBzYWZlIGhlbHBlciB0byBhdm9pZCBudWxsIGVycm9ycwogIGZ1bmN0aW9uIHNhZmVTZXQoaWQsIHByb3AsIHZhbCkgewogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7CiAgICBpZiAoZWwpIGVsW3Byb3BdID0gdmFsOwogIH0KICBzYWZlU2V0KCdsb2cnLCAnaW5uZXJIVE1MJywgJycpOwogIHNhZmVTZXQoJ3F1aWNrLWJ0bnMnLCAnaW5uZXJIVE1MJywgJycpOwogIHNhZmVTZXQoJ3RvcC1tb2QnLCAndGV4dENvbnRlbnQnLCAnJyk7CiAgc2FmZVNldCgndG9wLXJ1bGVzJywgJ3RleHRDb250ZW50JywgJycpOwogIHNhZmVTZXQoJ3NjZW5lLWxvYycsICd0ZXh0Q29udGVudCcsICcuLi4nKTsKICBzYWZlU2V0KCdzY2VuZS10YWcnLCAndGV4dENvbnRlbnQnLCAnJyk7CiAgY29uc3QgcncgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJvb20td3JhcCcpOwogIGlmIChydykgcncuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKCiAgLy8gRm9yY2UgaGlkZSBBTEwgc2NyZWVucwogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5zY3JlZW4nKS5mb3JFYWNoKHMgPT4gewogICAgcy5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKTsKICAgIHMuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICB9KTsKCiAgLy8gR28gdG8gY2hhciBjcmVhdGlvbiBpZiB3ZSBoYXZlIGEgbW9kdWxlLCBob21lIHNjcmVlbiBpZiBub3QKICBpZiAoc2F2ZWRNb2R1bGUgJiYgc2F2ZWRNb2R1bGVOYW1lKSB7CiAgICBjb25zdCBjaGFyU2NyZWVuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtY2hhcicpOwogICAgY2hhclNjcmVlbi5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogICAgY2hhclNjcmVlbi5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICAgIGNoYXJTY3JlZW4uc2Nyb2xsVG9wID0gMDsKICAgIGNvbnN0IGNtbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKTsKICAgIGlmIChjbWwpIGNtbC50ZXh0Q29udGVudCA9IHNhdmVkTW9kdWxlTmFtZTsKICAgIGNvbnN0IG1wbiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtcC1jaGFyLW5vdGUnKTsKICAgIGlmIChtcG4pIG1wbi5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgY29uc3QgcmIgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJyk7CiAgICBpZiAocmIpIHsgcmIudGV4dENvbnRlbnQgPSAnIFJlYWR5JzsgcmIuZGlzYWJsZWQgPSBmYWxzZTsgfQogICAgY29uc3QgYmIgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmVnaW4tYnRuJyk7CiAgICBpZiAoYmIpIGJiLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICBidWlsZENoYXJDcmVhdGUoKTsKICB9IGVsc2UgewogICAgY29uc3QgaG9tZVNjcmVlbiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzLWhvbWUnKTsKICAgIGhvbWVTY3JlZW4uc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKICAgIGhvbWVTY3JlZW4uY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7CiAgICBob21lU2NyZWVuLnNjcm9sbFRvcCA9IDA7CiAgfQp9CgpmdW5jdGlvbiBzYXZlR2FtZSgpIHsKICB4aHJGZXRjaChCQVNFX1VSTCArICcvc2F2ZScsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICBtb2R1bGVOYW1lLCBjaG9zZW5SdWxlcywgaXNNdWx0aXBsYXllciwKICAgICAgcGNOYW1lOiBwYy5uYW1lLCBwY0NsYXNzOiBwYy5jbHMsCiAgICAgIHBjLCBwYXJ0eVBDcywgaGlzdG9yeSwgc3lzdGVtUHJvbXB0LCBtb2R1bGVUZXh0LAogICAgICBsb2dFbnRyaWVzLAogICAgICBtZW1vcnlTdW1tYXJ5LCB3b3JsZFN0YXRlLCBwaW5uZWRGYWN0cywgdHVybkNvdW50LAogICAgICBucGNQcm9maWxlcywgbG9jYXRpb25BdG1vc3BoZXJlLCBzZXNzaW9uVG9uZSwKICAgICAgZ21CcmllZmluZywgbnBjS25vd2xlZGdlTWFwLAogICAgICBwYWNpbmdIaXN0b3J5LCBjdXJyZW50UGFjaW5nUGhhc2UsIGNvbnNlcXVlbmNlcywKICAgICAgaW5Db21iYXQsIGNvbWJhdFN0YXRlLCBkdW5nZW9uVHVybnMsIHRvcmNoVHVybnNMZWZ0LAogICAgICBoYXNMYW50ZXJuLCBsYW50ZXJuT2lsRmxhc2tzTGVmdCwgcmF0aW9uc0xlZnQsIHJlc3REZWJ0LCB0dXJuc1dpdGhvdXRSZXN0LCBmYXRpZ3VlUGVuYWx0eSwgZGF5c1dpdGhvdXRGb29kLCBzdGFydmF0aW9uUGVuYWx0eSwKICAgICAgd2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyCiAgICB9KQogIH0pLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZCA9PiB7CiAgICBpZiAoZC5vaykgewogICAgICBjb25zdCBidG4gPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKCcudG9wLWJ0bicpOwogICAgICBidG4udGV4dENvbnRlbnQgPSAnIFNhdmVkISc7CiAgICAgIHNldFRpbWVvdXQoKCkgPT4geyBidG4udGV4dENvbnRlbnQgPSAnIFNhdmUnOyB9LCAyMDAwKTsKICAgIH0KICB9KTsKfQoKZnVuY3Rpb24gc2hvd1J1bGVzKCkgewogIGFsZXJ0KFJVTEVTX1RFWFRbY2hvc2VuUnVsZXNdIHx8IFJVTEVTX1RFWFRbJ09TRSBBZHZhbmNlZCBGYW50YXN5J10pOwp9CgoKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIFY0IFNUQVRFIFZBUklBQkxFUwovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KbGV0IGluQ29tYmF0ID0gZmFsc2U7CmxldCBwbGF5ZXJIaWRkZW4gPSBmYWxzZTsKbGV0IGN1cnJlbnROUENzID0gW107CmxldCBjdXJyZW50T2JqZWN0cyA9IFtdOwpsZXQgY29tYmF0U3RhdGUgPSB7IGVuY291bnRlcjogbnVsbCwgcm91bmQ6IDAgfTsKbGV0IGxvYWRlZE1vZHVsZURhdGEgPSB7fTsKbGV0IGFjdGl2ZUVmZmVjdHNWNCA9IFtdOyAgLy8gW3t0eXBlLCB0dXJuc0xlZnQsIGJvbnVzLCAuLi59XQoKLy8gU3BlbGwgc3lzdGVtIHN0YXRlCmxldCBzcGVsbEJvb2sgPSB7fTsgICAgICAgICAgLy8ge3NwZWxsTmFtZToge2xldmVsLCB0eXBlLCBrbm93bjp0cnVlfX0KbGV0IG1lbW9yaXplZFNwZWxscyA9IFtdOyAgICAvLyBbe25hbWUsIGxldmVsfV0gLS0gdG9kYXkncyBtZW1vcml6ZWQgc3BlbGxzCmxldCBzcGVsbFNsb3RzVG90YWwgPSBbXTsgICAgLy8gW2NvdW50X2x2bDEsIGNvdW50X2x2bDIsIC4uLl0KbGV0IHNwZWxsU2xvdHNSZW1haW5pbmcgPSBbXTsgLy8gc2FtZSBidXQgZGVjcmVtZW50cyBvbiBjYXN0CgovLyBBYmlsaXR5IHVzZXMgdG9kYXkKbGV0IGFiaWxpdHlVc2VzVG9kYXkgPSB7fTsgICAvLyB7YWJpbGl0eU5hbWU6IGNvdW50fQoKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIFY0IENPUkUgQUNUSU9OIFBJUEVMSU5FCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQphc3luYyBmdW5jdGlvbiBzZW5kKCkgewogIGNvbnN0IGlucCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKTsKICBjb25zdCB2ID0gaW5wLnZhbHVlLnRyaW0oKTsKICBpZiAoIXYgfHwgYnVzeSkgcmV0dXJuOwogIGlucC52YWx1ZSA9ICcnOwoKICAvLyAvR00gb3V0LW9mLWNoYXJhY3RlciBxdWVzdGlvbgogIGNvbnN0IHNsYXNoTWF0Y2ggPSB2Lm1hdGNoKC9eWy5dKFtBLVphLXpdW0EtWmEtejAtOV8gXSs/KVsuXXMrKC4rKSQvKTsKICBpZiAoc2xhc2hNYXRjaCkgewogICAgY29uc3QgdGFyZ2V0ID0gc2xhc2hNYXRjaFsxXS50cmltKCkudG9Mb3dlckNhc2UoKTsKICAgIGNvbnN0IG1lc3NhZ2UgPSBzbGFzaE1hdGNoWzJdLnRyaW0oKTsKICAgIGlmIChbJ2dtJywnZG0nXS5pbmNsdWRlcyh0YXJnZXQpKSB7CiAgICAgIGFkZEVudHJ5UmF3KCc8c3BhbiBzdHlsZT0iY29sb3I6IzdhOWE3YTtmb250LXN0eWxlOml0YWxpYzsiPihPT0MpICcgKyBwYy5uYW1lICsgJzogJyArIG1lc3NhZ2UgKyAnPC9zcGFuPicsICdwbGF5ZXInLCBwYy5uYW1lKTsKICAgICAgYXdhaXQgY2FsbEFjdGlvblY0KCdbR00gUlVMRVMgUVVFU1RJT04gLS0gYW5zd2VyIGRpcmVjdGx5LCBubyBuYXJyYXRpdmVdOiAnICsgbWVzc2FnZSk7CiAgICAgIHJldHVybjsKICAgIH0KICAgIC8vIFBsYXllci10by1wbGF5ZXIgZGlyZWN0IG1lc3NhZ2UgLS0gbmV2ZXIgZ29lcyB0byBBSQogICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS1nb2xkKSI+JyArIHBjLm5hbWUgKyAnIC0+ICcgKyBzbGFzaE1hdGNoWzFdICsgJzo8L3NwYW4+ICcgKyBtZXNzYWdlLCAncGxheWVyJywgcGMubmFtZSk7CiAgICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgICB4aHJGZXRjaChCQVNFX1VSTCArICcvY2hhdCcsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOnJvb21Db2RlLCBwbGF5ZXI6cGMubmFtZSwgbXNnOnYsIHR5cGU6J2RpcmVjdCd9KX0pOwogICAgfQogICAgcmV0dXJuOwogIH0KCiAgYWRkRW50cnlSYXcoaXNNdWx0aXBsYXllciA/ICc8Yj4nICsgcGMubmFtZSArICc6PC9iPiAnICsgdiA6IHYsICdwbGF5ZXInLCBwYy5uYW1lKTsKICBhd2FpdCBjYWxsQWN0aW9uVjQodik7Cn0KCmFzeW5jIGZ1bmN0aW9uIHF1aWNrQWN0KHQpIHsKICBpZiAoYnVzeSkgcmV0dXJuOwogIGFkZEVudHJ5UmF3KGlzTXVsdGlwbGF5ZXIgPyAnPGI+JyArIHBjLm5hbWUgKyAnOjwvYj4gJyArIHQgOiB0LCAncGxheWVyJywgcGMubmFtZSk7CiAgYXdhaXQgY2FsbEFjdGlvblY0KHQpOwp9Cgphc3luYyBmdW5jdGlvbiBjYWxsQWN0aW9uVjQodGV4dCkgewogIGlmIChidXN5KSByZXR1cm47CiAgYnVzeSA9IHRydWU7CiAgY29uc3Qgc2VuZEJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpOwogIGNvbnN0IGNtZElucCAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJyk7CiAgaWYgKHNlbmRCdG4pIHNlbmRCdG4uZGlzYWJsZWQgPSB0cnVlOwogIGlmIChjbWRJbnApICBjbWRJbnAuZGlzYWJsZWQgPSB0cnVlOwoKICBjb25zdCB0aGlua0VsID0gYWRkRW50cnlSYXcoJ1RoZSBHYW1lIE1hc3RlciBjb25zaWRlcnMuLi4nLCAndGhpbmtpbmcnLCAnX19nbV9fJyk7CgogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FjdGlvbicsIHsKICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgIGhlYWRlcnM6IHsnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICAgIHRleHQsCiAgICAgICAgcGM6IGJ1aWxkUENTdGF0ZSgpLAogICAgICAgIGdhbWVfc3RhdGU6IGJ1aWxkR2FtZVN0YXRlKCksCiAgICAgICAgaGlzdG9yeTogaGlzdG9yeS5zbGljZSgtMTIpLAogICAgICAgIGFwaV9rZXk6IGFwaUtleSB8fCAnJywKICAgICAgICByb29tX2NvZGU6IHJvb21Db2RlIHx8ICcnLAogICAgICB9KQogICAgfSk7CiAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzcC5qc29uKCk7CiAgICBpZiAodGhpbmtFbCAmJiB0aGlua0VsLnBhcmVudE5vZGUpIHRoaW5rRWwucGFyZW50Tm9kZS5yZW1vdmVDaGlsZCh0aGlua0VsKTsKCiAgICAvLyAtLSBMYXllciAxIHJlamVjdGlvbiAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBpZiAoZGF0YS5yZWplY3Rpb24pIHsKICAgICAgYWRkRW50cnlSYXcoJzxkaXYgY2xhc3M9InJlamVjdGlvbi1tc2ciPiYjOTg4ODsgJyArIGRhdGEucmVqZWN0aW9uICsgJzwvZGl2PicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIGZpbmlzaEFjdGlvbigpOwogICAgICByZXR1cm47CiAgICB9CgogICAgaWYgKGRhdGEuZXJyb3IpIHsKICAgICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA2MDYwOyI+RXJyb3I6ICcgKyBkYXRhLmVycm9yICsgJzwvc3Bhbj4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICBmaW5pc2hBY3Rpb24oKTsKICAgICAgcmV0dXJuOwogICAgfQoKICAgIC8vIC0tIExheWVyIDM6IHBhcnNlIGxpbmUgdGhlbiBkaWNlIHJlc3VsdHMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBpZiAoZGF0YS5kaXNwbGF5X3JvbGxzICYmIGRhdGEuZGlzcGxheV9yb2xscy5sZW5ndGgpIHsKICAgICAgbGV0IHBhcnNlUGFydCA9ICcnOwogICAgICBsZXQgZGljZVBhcnRzID0gW107CiAgICAgIGRhdGEuZGlzcGxheV9yb2xscy5mb3JFYWNoKGxpbmUgPT4gewogICAgICAgIGlmIChsaW5lLnN0YXJ0c1dpdGgoJ1BBUlNFOicpKSB7CiAgICAgICAgICBwYXJzZVBhcnQgPSAnPGRpdiBjbGFzcz0icGFyc2UtbGluZSI+JyArIGxpbmUuc2xpY2UoNikgKyAnPC9kaXY+JzsKICAgICAgICB9IGVsc2UgewogICAgICAgICAgZGljZVBhcnRzLnB1c2goJzxkaXYgY2xhc3M9ImRpY2UtbGluZSI+JyArIGxpbmUgKyAnPC9kaXY+Jyk7CiAgICAgICAgfQogICAgICB9KTsKICAgICAgY29uc3QgaW5uZXIgPSBwYXJzZVBhcnQgKyBkaWNlUGFydHMuam9pbignJyk7CiAgICAgIGlmIChpbm5lcikgYWRkRW50cnlSYXcoJzxkaXYgY2xhc3M9InJvbGwtcmVzdWx0LWJveCI+JyArIGlubmVyICsgJzwvZGl2PicsICdzeXN0ZW0tcm9sbCcsICdfX3JvbGxfXycpOwogICAgfQoKICAgIC8vIC0tIExheWVyIDQgbmFycmF0aW9uIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAgIGlmIChkYXRhLm5hcnJhdGlvbikgewogICAgICBjb25zdCBwYXJhcyA9IGRhdGEubmFycmF0aW9uLnNwbGl0KC9bLl1uWy5dbisvKS5maWx0ZXIocCA9PiBwLnRyaW0oKSk7CiAgICAgIGlmIChwYXJhcy5sZW5ndGggPiAxKSB7CiAgICAgICAgcGFyYXMuZm9yRWFjaChwID0+IGFkZEVudHJ5UmF3KGZtdChwLnRyaW0oKSksICdnbScsICdfX2dtX18nKSk7CiAgICAgIH0gZWxzZSB7CiAgICAgICAgYWRkRW50cnlSYXcoZm10KGRhdGEubmFycmF0aW9uKSwgJ2dtJywgJ19fZ21fXycpOwogICAgICB9CiAgICB9CgogICAgLy8gLS0gQXBwbHkgc3RhdGUgY2hhbmdlcyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgaWYgKGRhdGEuc3RhdGVfY2hhbmdlcykgYXBwbHlTdGF0ZUNoYW5nZXMoZGF0YS5zdGF0ZV9jaGFuZ2VzKTsKCiAgICAvLyAtLSBMZXZlbCB1cCAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAgIGlmIChkYXRhLmxldmVsX3VwKSBzaG93TGV2ZWxVcE1vZGFsKGRhdGEubGV2ZWxfdXApOwoKICAgIC8vIC0tIFVwZGF0ZSBoaXN0b3J5IC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAgIHB1c2hNZXNzYWdlKCd1c2VyJywgdGV4dCk7CiAgICBpZiAoZGF0YS5uYXJyYXRpb24pIHB1c2hNZXNzYWdlKCdhc3Npc3RhbnQnLCBkYXRhLm5hcnJhdGlvbik7CgogICAgLy8gLS0gQWR2YW5jZSBkdW5nZW9uIGNsb2NrIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgaWYgKCFbJ2V4YW1pbmUnLCdyZXN0Jywnb3RoZXInXS5pbmNsdWRlcygoZGF0YS5hY3Rpb25fdHlwZXx8JycpLnRvTG93ZXJDYXNlKCkpKSB7CiAgICAgIGFkdmFuY2VEdW5nZW9uVHVybigpOwogICAgfQoKICAgIHVwZGF0ZUhVRCgpOwogICAgdXBkYXRlU3BlbGxib29rUGFuZWwoKTsKICAgIHVwZGF0ZUFiaWxpdHlQYW5lbCgpOwoKICB9IGNhdGNoKGUpIHsKICAgIGlmICh0aGlua0VsICYmIHRoaW5rRWwucGFyZW50Tm9kZSkgdGhpbmtFbC5wYXJlbnROb2RlLnJlbW92ZUNoaWxkKHRoaW5rRWwpOwogICAgYWRkRW50cnlSYXcoJyYjOTg4ODsgQ29ubmVjdGlvbiBlcnJvcjogJyArIChlLm1lc3NhZ2V8fGUpLCAnc3lzdGVtJywgJ19fZ21fXycpOwogIH0KICBmaW5pc2hBY3Rpb24oKTsKfQoKZnVuY3Rpb24gZmluaXNoQWN0aW9uKCkgewogIGJ1c3kgPSBmYWxzZTsKICBjb25zdCBzZW5kQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJyk7CiAgY29uc3QgY21kSW5wICA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKTsKICBpZiAoc2VuZEJ0bikgc2VuZEJ0bi5kaXNhYmxlZCA9IGZhbHNlOwogIGlmIChjbWRJbnApIHsgY21kSW5wLmRpc2FibGVkID0gZmFsc2U7IGNtZElucC5mb2N1cygpOyB9Cn0KCmZ1bmN0aW9uIGJ1aWxkUENTdGF0ZSgpIHsKICByZXR1cm4gewogICAgLi4ucGMsCiAgICBzcGVsbGJvb2s6IHNwZWxsQm9vaywKICAgIG1lbW9yaXplZF9zcGVsbHM6IG1lbW9yaXplZFNwZWxscywKICAgIHNwZWxsX3Nsb3RzX3JlbWFpbmluZzogc3BlbGxTbG90c1JlbWFpbmluZywKICAgIHNwZWxsX3Nsb3RzX3RvdGFsOiBzcGVsbFNsb3RzVG90YWwsCiAgICBhY3RpdmVfZWZmZWN0czogYWN0aXZlRWZmZWN0c1Y0LAogICAgYWJpbGl0aWVzX3VzZWRfdG9kYXk6IGFiaWxpdHlVc2VzVG9kYXksCiAgICBlcXVpcHBlZF9tYWdpYzogKHBjLmludnx8W10pLmZpbHRlcihpID0+IGkgJiYgL3Jpbmd8YW11bGV0fGNsb2FrfGJvb3RzIG9mfGdsb3ZlcyBvZi9pLnRlc3QodHlwZW9mIGk9PT0nc3RyaW5nJz9pOmkubmFtZXx8JycpKSwKICB9Owp9CgpmdW5jdGlvbiBidWlsZEdhbWVTdGF0ZSgpIHsKICByZXR1cm4gewogICAgaW5fY29tYmF0OiBpbkNvbWJhdCwKICAgIGluX2R1bmdlb246IGlzSW5EdW5nZW9uKCksCiAgICBjdXJyZW50X3Jvb206IHBjLmxvY3RhZyB8fCAnJywKICAgIGN1cnJlbnRfbG9jYXRpb246IHBjLmxvYyB8fCAnJywKICAgIGN1cnJlbnRfZW5jb3VudGVyOiAoY29tYmF0U3RhdGUgJiYgY29tYmF0U3RhdGUuZW5jb3VudGVyKSA/IGNvbWJhdFN0YXRlLmVuY291bnRlciA6IHt9LAogICAgbnBjc19wcmVzZW50OiBjdXJyZW50TlBDcyB8fCBbXSwKICAgIG9iamVjdHNfcHJlc2VudDogY3VycmVudE9iamVjdHMgfHwgW10sCiAgICBwbGF5ZXJfaGlkZGVuOiBwbGF5ZXJIaWRkZW4gfHwgZmFsc2UsCiAgICBtb2R1bGVfZGF0YTogbG9hZGVkTW9kdWxlRGF0YSB8fCB7fSwKICAgIHBhcnR5X3BjczogcGFydHlQQ3MgfHwge30sCiAgfTsKfQoKLy8gLS0gU3RhdGUgYXBwbGljYXRpb24gKExheWVyIDMgcmVzdWx0cyAtPiBsb2NhbCBzdGF0ZSkgLS0tLS0tLS0tLS0tLS0tLS0tLS0tCmZ1bmN0aW9uIGFwcGx5U3RhdGVDaGFuZ2VzKHNjKSB7CiAgLy8gTW9uc3RlciBkYW1hZ2UgLyBkZWF0aAogIGlmIChzYy5tb25zdGVyX2RhbWFnZSkgewogICAgY29uc3QgbWQgPSBzYy5tb25zdGVyX2RhbWFnZTsKICAgIGlmIChjb21iYXRTdGF0ZS5lbmNvdW50ZXIgJiYgY29tYmF0U3RhdGUuZW5jb3VudGVyLm1vbnN0ZXJzKSB7CiAgICAgIGNvbnN0IG0gPSBjb21iYXRTdGF0ZS5lbmNvdW50ZXIubW9uc3RlcnMuZmluZCh4ID0+CiAgICAgICAgeC5pZCA9PT0gbWQubW9uc3Rlcl9pZCB8fCB4Lm5hbWUgPT09IG1kLm1vbnN0ZXJfaWQpOwogICAgICBpZiAobSkgewogICAgICAgIG0uaHAgPSBtZC5uZXdfaHA7CiAgICAgICAgaWYgKG1kLmtpbGxlZCkgbS5kZWFkID0gdHJ1ZTsKICAgICAgfQogICAgICBjb25zdCBhbGl2ZSA9IGNvbWJhdFN0YXRlLmVuY291bnRlci5tb25zdGVycy5maWx0ZXIobSA9PiAhbS5kZWFkICYmIG0uaHAgPiAwKTsKICAgICAgaWYgKGFsaXZlLmxlbmd0aCA9PT0gMCkgewogICAgICAgIGluQ29tYmF0ID0gZmFsc2U7CiAgICAgICAgYWRkRW50cnlSYXcoJ1tBbGwgZW5lbWllcyBkZWZlYXRlZCAtLSBjb21iYXQgZW5kc10nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICB9CiAgICB9CiAgfQogIC8vIE1vbnN0ZXIgZmxlZXMKICBpZiAoc2MubW9uc3Rlcl9mbGVlcykgewogICAgaWYgKGNvbWJhdFN0YXRlLmVuY291bnRlciAmJiBjb21iYXRTdGF0ZS5lbmNvdW50ZXIubW9uc3RlcnMpIHsKICAgICAgY29uc3QgbSA9IGNvbWJhdFN0YXRlLmVuY291bnRlci5tb25zdGVycy5maW5kKHggPT4KICAgICAgICB4LmlkID09PSBzYy5tb25zdGVyX2ZsZWVzIHx8IHgubmFtZSA9PT0gc2MubW9uc3Rlcl9mbGVlcyk7CiAgICAgIGlmIChtKSB7IG0uZmxlZCA9IHRydWU7IG0uaHAgPSAwOyB9CiAgICB9CiAgICBjb25zdCBhbGl2ZSA9IChjb21iYXRTdGF0ZS5lbmNvdW50ZXIgJiYgY29tYmF0U3RhdGUuZW5jb3VudGVyLm1vbnN0ZXJzfHxbXSkKICAgICAgLmZpbHRlcihtID0+ICFtLmRlYWQgJiYgIW0uZmxlZCAmJiBtLmhwID4gMCk7CiAgICBpZiAoYWxpdmUubGVuZ3RoID09PSAwKSBpbkNvbWJhdCA9IGZhbHNlOwogIH0KICAvLyBYUCBnYWluCiAgaWYgKHNjLnhwX2dhaW4pIHsKICAgIHBjLnhwID0gKHBjLnhwIHx8IDApICsgc2MueHBfZ2FpbjsKICAgIGFkZEVudHJ5UmF3KCdbWFAgKycgKyBzYy54cF9nYWluICsgJyAodG90YWw6ICcgKyBwYy54cCArICcpXScsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgfQogIC8vIFBsYXllciBkYW1hZ2UKICBpZiAoc2MucGxheWVyX2RhbWFnZSAmJiBzYy5wbGF5ZXJfZGFtYWdlID4gMCkgewogICAgcGMuaHAgPSBNYXRoLm1heCgwLCAocGMuaHB8fDApIC0gc2MucGxheWVyX2RhbWFnZSk7CiAgICBpZiAocGMuaHAgPD0gMCkgewogICAgICBhZGRFbnRyeVJhdygnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjA7Zm9udC13ZWlnaHQ6Ym9sZDsiPiYjOTg4ODsgJyArIAogICAgICAgIChwYy5uYW1lfHwnWW91JykgKyAnIGhhcyBiZWVuIHJlZHVjZWQgdG8gMCBIUCEgVGhlIGFkdmVudHVyZSBtYXkgYmUgb3Zlci4uLjwvc3Bhbj4nLAogICAgICAgICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICB9CiAgfQogIC8vIEhlYWxpbmcKICBpZiAoc2MuaGVhbF9wbGF5ZXIpIHsKICAgIHBjLmhwID0gTWF0aC5taW4ocGMubWF4aHAgfHwgcGMuaHAsIChwYy5ocHx8MCkgKyBzYy5oZWFsX3BsYXllcik7CiAgfQogIC8vIFNwZWxsIHNsb3QgY29uc3VtcHRpb24KICBpZiAoc2MuY29uc3VtZV9zcGVsbF9zbG90ICE9PSB1bmRlZmluZWQpIHsKICAgIGNvbnN0IGlkeCA9IHNjLmNvbnN1bWVfc3BlbGxfc2xvdCAtIDE7CiAgICBpZiAoc3BlbGxTbG90c1JlbWFpbmluZ1tpZHhdID4gMCkgc3BlbGxTbG90c1JlbWFpbmluZ1tpZHhdLS07CiAgICAvLyBSZW1vdmUgZnJvbSBtZW1vcml6ZWQgKG9uZSBpbnN0YW5jZSkKICAgIGNvbnN0IG1JZHggPSBtZW1vcml6ZWRTcGVsbHMuZmluZEluZGV4KHMgPT4KICAgICAgKHR5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWUpICYmIEFMTF9TUEVMTF9MRVZFTFNbdHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZV0gPT09IHNjLmNvbnN1bWVfc3BlbGxfc2xvdCk7CiAgICBpZiAobUlkeCA+PSAwKSBtZW1vcml6ZWRTcGVsbHMuc3BsaWNlKG1JZHgsIDEpOwogIH0KICAvLyBBbW1vIGNvbnN1bXB0aW9uCiAgaWYgKHNjLmNvbnN1bWVfYW1tbykgewogICAgY29uc3QgaW52ID0gcGMuaW52IHx8IFtdOwogICAgY29uc3QgYWkgPSBpbnYuZmluZEluZGV4KGkgPT4gL2JvbHR8YXJyb3d8c3RvbmV8cXVhcnJlbC9pLnRlc3QodHlwZW9mIGk9PT0nc3RyaW5nJz9pOihpLm5hbWV8fCcnKSkpOwogICAgaWYgKGFpID49IDApIHsKICAgICAgY29uc3QgaXRlbSA9IHR5cGVvZiBpbnZbYWldPT09J3N0cmluZycgPyBpbnZbYWldIDogaW52W2FpXS5uYW1lOwogICAgICBjb25zdCBudW1NID0gaXRlbS5tYXRjaCgvWy5dKFsuXWQrKVsuXS8pOwogICAgICBpZiAobnVtTSkgewogICAgICAgIGNvbnN0IG4gPSBwYXJzZUludChudW1NWzFdKSAtIDE7CiAgICAgICAgaWYgKG4gPD0gMCkgaW52LnNwbGljZShhaSwgMSk7CiAgICAgICAgZWxzZSBpbnZbYWldID0gaXRlbS5yZXBsYWNlKC9bLl1bLl1kK1suXS8sICcoJyArIG4gKyAnKScpOwogICAgICB9CiAgICB9CiAgfQogIC8vIFJhdGlvbiBjb25zdW1wdGlvbgogIGlmIChzYy5jb25zdW1lX3JhdGlvbikgewogICAgcmF0aW9uc0xlZnQgPSBNYXRoLm1heCgwLCAocmF0aW9uc0xlZnR8fDApIC0gMSk7CiAgICBkYXlzV2l0aG91dEZvb2QgPSAwOyBzdGFydmF0aW9uUGVuYWx0eSA9IDA7CiAgfQogIC8vIFRvcmNoIGxpZ2h0aW5nCiAgaWYgKHNjLmxpZ2h0X3RvcmNoKSB7CiAgICB0b3JjaExpdCA9IHRydWU7IHRvcmNoRXZlclVzZWQgPSB0cnVlOyB0b3JjaFR1cm5zTGVmdCA9IDY7CiAgICBjb25zdCBpbnYgPSBwYy5pbnYgfHwgW107CiAgICBjb25zdCB0aSA9IGludi5maW5kSW5kZXgoaSA9PiAvdG9yY2gvaS50ZXN0KHR5cGVvZiBpPT09J3N0cmluZyc/aTooaS5uYW1lfHwnJykpKTsKICAgIGlmICh0aSA+PSAwKSB7CiAgICAgIGNvbnN0IGl0ZW0gPSB0eXBlb2YgaW52W3RpXT09PSdzdHJpbmcnID8gaW52W3RpXSA6ICcnOwogICAgICBjb25zdCBubSA9IGl0ZW0ubWF0Y2goL1suXShbLl1kKylbLl0vKTsKICAgICAgaWYgKG5tICYmIHBhcnNlSW50KG5tWzFdKT4xKSBpbnZbdGldID0gaXRlbS5yZXBsYWNlKC9bLl1bLl1kK1suXS8sJygnICsgKHBhcnNlSW50KG5tWzFdKS0xKSArICcpJyk7CiAgICAgIGVsc2UgaW52LnNwbGljZSh0aSwxKTsKICAgIH0KICB9CiAgLy8gSXRlbSBjb25zdW1wdGlvbgogIGlmIChzYy5jb25zdW1lX2l0ZW0pIHsKICAgIGNvbnN0IGludiA9IHBjLmludiB8fCBbXTsKICAgIGNvbnN0IGlkeCA9IGludi5maW5kSW5kZXgoaSA9PiAodHlwZW9mIGk9PT0nc3RyaW5nJz9pOihpLm5hbWV8fCcnKSkgPT09IHNjLmNvbnN1bWVfaXRlbSk7CiAgICBpZiAoaWR4ID49IDApIGludi5zcGxpY2UoaWR4LCAxKTsKICB9CiAgLy8gRnVsbCByZXN0CiAgaWYgKHNjLmZ1bGxfcmVzdCkgewogICAgdHVybnNXaXRob3V0UmVzdCA9IDA7IGZhdGlndWVQZW5hbHR5ID0gMDsKICAgIHNwZWxsU2xvdHNSZW1haW5pbmcgPSBbLi4uc3BlbGxTbG90c1RvdGFsXTsKICAgIGFkZEVudHJ5UmF3KCdbRnVsbCByZXN0IGNvbXBsZXRlLiBTcGVsbCBzbG90cyByZXN0b3JlZC4gQXdhaXRpbmcgbWVtb3JpemF0aW9uLl0nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgLy8gUHJvbXB0IG1lbW9yaXphdGlvbiBpZiBzcGVsbGNhc3RlcgogICAgaWYgKHNwZWxsU2xvdHNUb3RhbC5sZW5ndGggPiAwKSBvcGVuTWVtb3JpemUoKTsKICB9CiAgLy8gRHVuZ2VvbiByZXN0CiAgaWYgKHNjLmR1bmdlb25fcmVzdCkgeyB0dXJuc1dpdGhvdXRSZXN0ID0gMDsgZmF0aWd1ZVBlbmFsdHkgPSAwOyB9CiAgLy8gQWN0aXZlIGVmZmVjdHMKICBpZiAoc2MuYWRkX2VmZmVjdCkgewogICAgYWN0aXZlRWZmZWN0c1Y0LnB1c2goey4uLnNjLmFkZF9lZmZlY3QsIHN0YXJ0ZWRBdDogdHVybkNvdW50fSk7CiAgfQogIC8vIEFiaWxpdHkgdXNlcwogIGlmIChzYy5hYmlsaXR5X3VzZWQpIHsKICAgIGNvbnN0IGFuYW1lID0gc2MuYWJpbGl0eV91c2VkLm5hbWU7CiAgICBhYmlsaXR5VXNlc1RvZGF5W2FuYW1lXSA9IChhYmlsaXR5VXNlc1RvZGF5W2FuYW1lXXx8MCkgKyAoc2MuYWJpbGl0eV91c2VkLmFtb3VudHx8MSk7CiAgfQp9CgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gTEVWRUwgVVAgU1lTVEVNCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQpmdW5jdGlvbiBzaG93TGV2ZWxVcE1vZGFsKGx1KSB7CiAgY29uc3QgY2hhbmdlcyA9IGx1LmNoYW5nZXMgfHwgW107CiAgY29uc3QgbmV3THZsID0gbHUubmV3X2xldmVsOwogIGNvbnN0IGh0bWwgPSBgCiAgICA8ZGl2IGNsYXNzPSJsZXZlbC11cC1tb2RhbCIgaWQ9Imx2LW1vZGFsIj4KICAgICAgPGRpdiBjbGFzcz0ibGV2ZWwtdXAtaW5uZXIiPgogICAgICAgIDxkaXYgY2xhc3M9Imx2LXRpdGxlIj4mIzk3MzM7IExFVkVMIFVQISAmIzk3MzM7PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0idGV4dC1hbGlnbjpjZW50ZXI7Zm9udC1zaXplOjE3cHg7bWFyZ2luLWJvdHRvbToxNHB4OyI+CiAgICAgICAgICAke3BjLm5hbWV9IHJlYWNoZXMgPGI+TGV2ZWwgJHtuZXdMdmx9PC9iPjwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi1ib3R0b206MTRweDsiPgogICAgICAgICAgJHtjaGFuZ2VzLm1hcChjPT4nPGRpdiBjbGFzcz0ibHYtY2hhbmdlIj4nK2MrJzwvZGl2PicpLmpvaW4oJycpfQogICAgICAgIDwvZGl2PgogICAgICAgICR7KGx1LnVwZGF0ZWRfcGMgJiYgWydNYWdpYy1Vc2VyJywnSWxsdXNpb25pc3QnLCdDbGVyaWMnLCdEcnVpZCcsJ0JhcmQnXS5pbmNsdWRlcyhwYy5jbHMpKQogICAgICAgICAgPyAnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tZ29sZC1kaW0pO2ZvbnQtc2l6ZToxM3B4O21hcmdpbi1ib3R0b206MTJweDsiPicrCiAgICAgICAgICAgICdOZXcgc3BlbGwgc2xvdHMgYXZhaWxhYmxlLiBZb3UgbWF5IG1lbW9yaXplIHNwZWxscyBhZnRlciBhIGZ1bGwgbmlnaHQmIzM5O3MgcmVzdC48L2Rpdj4nIDogJyd9CiAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBzdHlsZT0id2lkdGg6MTAwJSIgb25jbGljaz0iY2xvc2VMZXZlbFVwKCR7SlNPTi5zdHJpbmdpZnkoSlNPTi5zdHJpbmdpZnkobHUudXBkYXRlZF9wYykpfSkiPgogICAgICAgICAgQ29udGludWUgJiM5NjU4OzwvYnV0dG9uPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PmA7CiAgZG9jdW1lbnQuYm9keS5pbnNlcnRBZGphY2VudEhUTUwoJ2JlZm9yZWVuZCcsIGh0bWwpOwogIGNvbnN0IGNoYW5nZXNfc3RyID0gY2hhbmdlcy5qb2luKCcgfCAnKTsKICBhZGRFbnRyeVJhdygnW0xFVkVMIFVQOiAnICsgcGMubmFtZSArICcgcmVhY2hlcyBsZXZlbCAnICsgbmV3THZsICsgJyEgJyArIGNoYW5nZXNfc3RyICsgJ10nLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgpmdW5jdGlvbiBjbG9zZUxldmVsVXAodXBkYXRlZFBjSnNvbikgewogIGNvbnN0IG1vZGFsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2x2LW1vZGFsJyk7CiAgaWYgKG1vZGFsKSBtb2RhbC5yZW1vdmUoKTsKICBpZiAodXBkYXRlZFBjSnNvbikgewogICAgdHJ5IHsKICAgICAgY29uc3QgdXBkID0gdHlwZW9mIHVwZGF0ZWRQY0pzb24gPT09ICdzdHJpbmcnID8gSlNPTi5wYXJzZSh1cGRhdGVkUGNKc29uKSA6IHVwZGF0ZWRQY0pzb247CiAgICAgIE9iamVjdC5hc3NpZ24ocGMsIHVwZCk7CiAgICAgIC8vIFVwZGF0ZSBzcGVsbCBzbG90cyBpZiBjaGFuZ2VkCiAgICAgIGlmICh1cGQuc3BlbGxfc2xvdHNfdG90YWwpIHsKICAgICAgICBzcGVsbFNsb3RzVG90YWwgPSB1cGQuc3BlbGxfc2xvdHNfdG90YWw7CiAgICAgICAgLy8gRG9uJ3QgcmVzZXQgcmVtYWluaW5nIC0tIHRoZXkgbWF5IGhhdmUgc2xvdHMgbGVmdAogICAgICB9CiAgICAgIHVwZGF0ZUhVRCgpOwogICAgICB1cGRhdGVTcGVsbGJvb2tQYW5lbCgpOwogICAgfSBjYXRjaChlKSB7fQogIH0KfQoKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIFNQRUxMIFNZU1RFTSBVSQovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KCi8vIExvb2t1cDogc3BlbGwgbmFtZSAtPiBsZXZlbCAocG9wdWxhdGVkIGZyb20gc2VydmVyIGRhdGEpCmNvbnN0IEFMTF9TUEVMTF9MRVZFTFMgPSB7fTsKCmZ1bmN0aW9uIHVwZGF0ZVNwZWxsYm9va1BhbmVsKCkgewogIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NwZWxsYm9vay1wYW5lbCcpOwogIGlmICghcGFuZWwpIHJldHVybjsKCiAgY29uc3Qgc3BlbGxjYXN0aW5nQ2xhc3NlcyA9IFsnTWFnaWMtVXNlcicsJ0lsbHVzaW9uaXN0JywnQ2xlcmljJywnRHJ1aWQnLCdSYW5nZXInLCdQYWxhZGluJywnQmFyZCddOwogIGlmICghc3BlbGxjYXN0aW5nQ2xhc3Nlcy5pbmNsdWRlcyhwYy5jbHMpKSB7CiAgICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgcmV0dXJuOwogIH0KICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gJyc7CgogIC8vIFNsb3RzIGRpc3BsYXkKICBjb25zdCBzbG90c0VsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NiLXNsb3RzJyk7CiAgaWYgKHNsb3RzRWwpIHsKICAgIGlmICghc3BlbGxTbG90c1RvdGFsLmxlbmd0aCkgewogICAgICBzbG90c0VsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6dmFyKC0tdGV4dC1kaW0pIj5ObyBzcGVsbCBzbG90cyBhdCB0aGlzIGxldmVsLjwvc3Bhbj4nOwogICAgfSBlbHNlIHsKICAgICAgbGV0IGh0bWwgPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tZ29sZC1kaW0pO21hcmdpbi1ib3R0b206NHB4OyI+U1BFTEwgU0xPVFM8L2Rpdj4nOwogICAgICBzcGVsbFNsb3RzVG90YWwuZm9yRWFjaCgodG90YWwsIGlkeCkgPT4gewogICAgICAgIGNvbnN0IHVzZWQgPSB0b3RhbCAtIChzcGVsbFNsb3RzUmVtYWluaW5nW2lkeF18fDApOwogICAgICAgIGNvbnN0IHBpcHMgPSBBcnJheS5mcm9tKHtsZW5ndGg6dG90YWx9LCAoXyxpKSA9PgogICAgICAgICAgYDxzcGFuIGNsYXNzPSJzcGVsbC1zbG90LXBpcCR7aTx1c2VkPycgdXNlZCc6Jyd9Ij48L3NwYW4+YCkuam9pbignJyk7CiAgICAgICAgaHRtbCArPSBgPGRpdiBjbGFzcz0ic3BlbGwtc2xvdC1yb3ciPgogICAgICAgICAgPHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLXRleHQtZGltKTt3aWR0aDoxNnB4OyI+JHtpZHgrMX08L3NwYW4+CiAgICAgICAgICAke3BpcHN9PC9kaXY+YDsKICAgICAgfSk7CiAgICAgIHNsb3RzRWwuaW5uZXJIVE1MID0gaHRtbDsKICAgIH0KICB9CgogIC8vIE1lbW9yaXplZCBzcGVsbHMKICBjb25zdCBtZW1FbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYi1tZW1vcml6ZWQnKTsKICBpZiAobWVtRWwpIHsKICAgIGlmICghbWVtb3JpemVkU3BlbGxzLmxlbmd0aCkgewogICAgICBtZW1FbC5pbm5lckhUTUwgPSAnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tdGV4dC1kaW0pO2ZvbnQtc2l6ZToxMnB4OyI+Tm8gc3BlbGxzIG1lbW9yaXplZC48L2Rpdj4nOwogICAgfSBlbHNlIHsKICAgICAgY29uc3QgYnlMZXZlbCA9IHt9OwogICAgICBtZW1vcml6ZWRTcGVsbHMuZm9yRWFjaChzID0+IHsKICAgICAgICBjb25zdCBuYW1lID0gdHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZTsKICAgICAgICBjb25zdCBsdmwgID0gKHR5cGVvZiBzPT09J29iamVjdCcmJnMubGV2ZWwpIHx8IEFMTF9TUEVMTF9MRVZFTFNbbmFtZV0gfHwgJz8nOwogICAgICAgIGlmICghYnlMZXZlbFtsdmxdKSBieUxldmVsW2x2bF0gPSBbXTsKICAgICAgICBieUxldmVsW2x2bF0ucHVzaChuYW1lKTsKICAgICAgfSk7CiAgICAgIGxldCBodG1sID0gJyc7CiAgICAgIE9iamVjdC5rZXlzKGJ5TGV2ZWwpLnNvcnQoKS5mb3JFYWNoKGx2bCA9PiB7CiAgICAgICAgaHRtbCArPSBgPGRpdiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tZ29sZC1kaW0pO21hcmdpbi10b3A6NHB4OyI+TGV2ZWwgJHtsdmx9OjwvZGl2PmA7CiAgICAgICAgYnlMZXZlbFtsdmxdLmZvckVhY2gobmFtZSA9PiB7CiAgICAgICAgICBodG1sICs9IGA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTJweDtwYWRkaW5nOjFweCA0cHg7Ij4mIzk2NzA7ICR7bmFtZX08L2Rpdj5gOwogICAgICAgIH0pOwogICAgICB9KTsKICAgICAgbWVtRWwuaW5uZXJIVE1MID0gaHRtbDsKICAgIH0KICB9CgogIC8vIFNob3cgbWVtb3JpemUgYnV0dG9uIHdoZW4gc2xvdHMgPiAwIGFuZCBhZnRlciByZXN0CiAgY29uc3QgYnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbW9yaXplLWJ0bicpOwogIGlmIChidG4pIHsKICAgIGNvbnN0IGhhc1Nsb3RzID0gc3BlbGxTbG90c1RvdGFsLnNvbWUocyA9PiBzID4gMCk7CiAgICBjb25zdCBoYXNTcGVsbHMgPSBPYmplY3Qua2V5cyhzcGVsbEJvb2spLmxlbmd0aCA+IDA7CiAgICBidG4uc3R5bGUuZGlzcGxheSA9IChoYXNTbG90cyAmJiBoYXNTcGVsbHMpID8gJycgOiAnbm9uZSc7CiAgfQp9CgovLyAtLSBNZW1vcml6ZSBzcGVsbCBtb2RhbCAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KZnVuY3Rpb24gb3Blbk1lbW9yaXplKCkgewogIGNvbnN0IGV4aXN0aW5nID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbW9yaXplLW1vZGFsJyk7CiAgaWYgKGV4aXN0aW5nKSBleGlzdGluZy5yZW1vdmUoKTsKCiAgY29uc3Qgc3BlbGxjYXN0aW5nQ2xhc3NlcyA9IHsKICAgICdNYWdpYy1Vc2VyJzogTVVfU1BFTExTX0ZPUl9DTEFTUywKICAgICdJbGx1c2lvbmlzdCc6IE1VX1NQRUxMU19GT1JfQ0xBU1MsCiAgICAnQ2xlcmljJzogQ0xFUklDX1NQRUxMU19GT1JfQ0xBU1MsCiAgICAnRHJ1aWQnOiBEUlVJRF9TUEVMTFNfRk9SX0NMQVNTLAogICAgJ1Jhbmdlcic6IFJBTkdFUl9TUEVMTFNfRk9SX0NMQVNTLAogICAgJ1BhbGFkaW4nOiBDTEVSSUNfU1BFTExTX0ZPUl9DTEFTUywKICAgICdCYXJkJzogQkFSRF9TUEVMTFNfRk9SX0NMQVNTLAogIH07CgogIGNvbnN0IGNsYXNzU3BlbGxzID0gc3BlbGxjYXN0aW5nQ2xhc3Nlc1twYy5jbHNdIHx8IHt9OwogIGNvbnN0IGFsbFNwZWxsc0ZvckNsYXNzID0gT2JqZWN0LmVudHJpZXMoY2xhc3NTcGVsbHMpOwoKICBsZXQgYm9keUh0bWwgPSAnJzsKICAvLyBGb3IgTVUvSWxsdXNpb25pc3Q6IGNhbiBvbmx5IG1lbW9yaXplIGZyb20gc3BlbGxib29rCiAgLy8gRm9yIENsZXJpYy9EcnVpZC9ldGM6IGNhbiBtZW1vcml6ZSBhbnkgc3BlbGwgb2YgYXBwcm9wcmlhdGUgbGV2ZWwKICBjb25zdCB1c2VzU3BlbGxib29rID0gWydNYWdpYy1Vc2VyJywnSWxsdXNpb25pc3QnXS5pbmNsdWRlcyhwYy5jbHMpOwoKICBzcGVsbFNsb3RzVG90YWwuZm9yRWFjaCgodG90YWwsIHNsb3RJZHgpID0+IHsKICAgIGlmICh0b3RhbCA9PT0gMCkgcmV0dXJuOwogICAgY29uc3Qgc3BlbGxMZXZlbCA9IHNsb3RJZHggKyAxOwogICAgY29uc3QgYXZhaWxhYmxlU3BlbGxzID0gYWxsU3BlbGxzRm9yQ2xhc3MKICAgICAgLmZpbHRlcigoW25hbWUsIGRhdGFdKSA9PiB7CiAgICAgICAgaWYgKGRhdGEubGV2ZWwgIT09IHNwZWxsTGV2ZWwpIHJldHVybiBmYWxzZTsKICAgICAgICBpZiAodXNlc1NwZWxsYm9vayAmJiAhc3BlbGxCb29rW25hbWVdKSByZXR1cm4gZmFsc2U7CiAgICAgICAgcmV0dXJuIHRydWU7CiAgICAgIH0pOwoKICAgIGlmICghYXZhaWxhYmxlU3BlbGxzLmxlbmd0aCkgcmV0dXJuOwoKICAgIGJvZHlIdG1sICs9IGA8ZGl2IHN0eWxlPSJtYXJnaW46MTBweCAwIDRweDtmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1nb2xkKTsiPgogICAgICBMZXZlbCAke3NwZWxsTGV2ZWx9IFNwZWxscyAoJHt0b3RhbH0gc2xvdHMpPC9kaXY+YDsKICAgIGF2YWlsYWJsZVNwZWxscy5mb3JFYWNoKChbbmFtZSwgZGF0YV0pID0+IHsKICAgICAgY29uc3QgYWxyZWFkeUNvdW50ZWQgPSBtZW1vcml6ZWRTcGVsbHMuZmlsdGVyKHMgPT4KICAgICAgICAodHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZSkgPT09IG5hbWUpLmxlbmd0aDsKICAgICAgYm9keUh0bWwgKz0gYAogICAgICAgIDxkaXYgY2xhc3M9InNwZWxsLWNhcmQiIGlkPSJzYy0ke25hbWUucmVwbGFjZSgvWy5dcysvZywnLScpfSIKICAgICAgICAgIG9uY2xpY2s9InRvZ2dsZU1lbW9yaXplU3BlbGwoJyR7bmFtZX0nLCAke3NwZWxsTGV2ZWx9KSIKICAgICAgICAgIHRpdGxlPSIke2RhdGEuZGVzY3x8Jyd9Ij4KICAgICAgICAgIDxkaXYgY2xhc3M9InNuYW1lIj4ke25hbWV9CiAgICAgICAgICAgICR7ZGF0YS5zYXZlPyc8c3BhbiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6dmFyKC0tZ29sZC1kaW0pIj4gKFNhdmUgdnMgJytkYXRhLnNhdmUrJyk8L3NwYW4+JzonJ30KICAgICAgICAgICAgJHtkYXRhLmRtZz8nPHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOiNjMDkwNDAiPiBbJytkYXRhLmRtZysnXTwvc3Bhbj4nOicnfQogICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzZGVzYyI+JHtkYXRhLnJhbmdlfSB8ICR7ZGF0YS5kdXJhdGlvbn0gfCAke2RhdGEuZGVzY308L2Rpdj4KICAgICAgICA8L2Rpdj5gOwogICAgfSk7CiAgfSk7CgogIGlmICghYm9keUh0bWwpIHsKICAgIGJvZHlIdG1sID0gJzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXRleHQtZGltKTt0ZXh0LWFsaWduOmNlbnRlcjtwYWRkaW5nOjIwcHg7Ij5ObyBzcGVsbHMgYXZhaWxhYmxlIHRvIG1lbW9yaXplIGF0IHRoaXMgbGV2ZWwuPC9kaXY+JzsKICB9CgogIGNvbnN0IG1vZGFsID0gYAogICAgPGRpdiBjbGFzcz0ibWVtb3JpemUtbW9kYWwiIGlkPSJtZW1vcml6ZS1tb2RhbCI+CiAgICAgIDxkaXYgY2xhc3M9Im1lbW9yaXplLW1vZGFsLWlubmVyIj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LWZhbWlseTpbLl0nSU0gRmVsbCBFbmdsaXNoWy5dJyxzZXJpZjtmb250LXNpemU6MjJweDtjb2xvcjp2YXIoLS1nb2xkKTttYXJnaW4tYm90dG9tOjRweDsiPgogICAgICAgICAgTWVtb3JpemUgU3BlbGxzPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1zaXplOjEycHg7Y29sb3I6dmFyKC0tdGV4dC1kaW0pO21hcmdpbi1ib3R0b206MTJweDsiPgogICAgICAgICAgU2VsZWN0IHNwZWxscyB0byBmaWxsIHlvdXIgYXZhaWxhYmxlIHNsb3RzLiAke3VzZXNTcGVsbGJvb2s/J09ubHkgc3BlbGxzIGluIHlvdXIgc3BlbGxib29rIG1heSBiZSBtZW1vcml6ZWQuJzonJ30KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IGlkPSJtZW1vcml6ZS1zZWxlY3Rpb24iPiR7Ym9keUh0bWx9PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0ibWFyZ2luLXRvcDoxNHB4O2Rpc3BsYXk6ZmxleDtnYXA6OHB4OyI+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9ImNvbmZpcm1NZW1vcml6ZSgpIiBzdHlsZT0iZmxleDoxIj5NZW1vcml6ZSBTZWxlY3RlZDwvYnV0dG9uPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJjbG9zZU1lbW9yaXplKCkiIHN0eWxlPSJmbGV4OjE7YmFja2dyb3VuZDp0cmFuc3BhcmVudDtib3JkZXItY29sb3I6dmFyKC0tYm9yZGVyKTsiPkNhbmNlbDwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PmA7CiAgZG9jdW1lbnQuYm9keS5pbnNlcnRBZGphY2VudEhUTUwoJ2JlZm9yZWVuZCcsIG1vZGFsKTsKCiAgLy8gUHJlLXNlbGVjdCBjdXJyZW50bHkgbWVtb3JpemVkCiAgbWVtb3JpemVkU3BlbGxzLmZvckVhY2gocyA9PiB7CiAgICBjb25zdCBuYW1lID0gdHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZTsKICAgIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NjLScgKyBuYW1lLnJlcGxhY2UoL1suXXMrL2csJy0nKSk7CiAgICBpZiAoZWwpIGVsLmNsYXNzTGlzdC5hZGQoJ3NlbGVjdGVkJyk7CiAgfSk7Cn0KCmxldCBfcGVuZGluZ01lbW9yaXplID0gW107CmZ1bmN0aW9uIHRvZ2dsZU1lbW9yaXplU3BlbGwobmFtZSwgbGV2ZWwpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYy0nICsgbmFtZS5yZXBsYWNlKC9bLl1zKy9nLCctJykpOwogIGlmICghZWwpIHJldHVybjsKCiAgY29uc3QgaWR4ID0gX3BlbmRpbmdNZW1vcml6ZS5maW5kSW5kZXgocyA9PiAodHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZSk9PT1uYW1lKTsKICBpZiAoaWR4ID49IDApIHsKICAgIF9wZW5kaW5nTWVtb3JpemUuc3BsaWNlKGlkeCwgMSk7CiAgICBlbC5jbGFzc0xpc3QucmVtb3ZlKCdzZWxlY3RlZCcpOwogIH0gZWxzZSB7CiAgICAvLyBDaGVjayBzbG90IGF2YWlsYWJpbGl0eSBmb3IgdGhpcyBsZXZlbAogICAgY29uc3Qgc2xvdElkeCA9IGxldmVsIC0gMTsKICAgIGNvbnN0IHVzZWRBdExldmVsID0gX3BlbmRpbmdNZW1vcml6ZS5maWx0ZXIocyA9PgogICAgICAoKHR5cGVvZiBzPT09J29iamVjdCcmJnMubGV2ZWwpfHxBTExfU1BFTExfTEVWRUxTW3R5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWVdfHwxKSA9PT0gbGV2ZWwpLmxlbmd0aDsKICAgIGlmICh1c2VkQXRMZXZlbCA+PSAoc3BlbGxTbG90c1RvdGFsW3Nsb3RJZHhdfHwwKSkgewogICAgICBhZGRFbnRyeVJhdygnW05vIG1vcmUgbGV2ZWwgJyArIGxldmVsICsgJyBzbG90cyBhdmFpbGFibGVdJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgcmV0dXJuOwogICAgfQogICAgX3BlbmRpbmdNZW1vcml6ZS5wdXNoKHtuYW1lLCBsZXZlbH0pOwogICAgZWwuY2xhc3NMaXN0LmFkZCgnc2VsZWN0ZWQnKTsKICB9Cn0KCmZ1bmN0aW9uIGNvbmZpcm1NZW1vcml6ZSgpIHsKICBtZW1vcml6ZWRTcGVsbHMgPSBbLi4uX3BlbmRpbmdNZW1vcml6ZV07CiAgX3BlbmRpbmdNZW1vcml6ZSA9IFtdOwogIC8vIFJlc2V0IHNwZWxsIHNsb3RzIHRvIHRvdGFsIChmcmVzaCBtZW1vcml6YXRpb24pCiAgc3BlbGxTbG90c1JlbWFpbmluZyA9IFsuLi5zcGVsbFNsb3RzVG90YWxdOwogIGNsb3NlTWVtb3JpemUoKTsKICB1cGRhdGVTcGVsbGJvb2tQYW5lbCgpOwogIGNvbnN0IG5hbWVzID0gbWVtb3JpemVkU3BlbGxzLm1hcChzPT50eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lKS5qb2luKCcsICcpOwogIGFkZEVudHJ5UmF3KCdbU3BlbGxzIG1lbW9yaXplZDogJyArIChuYW1lc3x8J25vbmUnKSArICddJywgJ3N5c3RlbScsICdfX2dtX18nKTsKfQoKZnVuY3Rpb24gY2xvc2VNZW1vcml6ZSgpIHsKICBjb25zdCBtID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbW9yaXplLW1vZGFsJyk7CiAgaWYgKG0pIG0ucmVtb3ZlKCk7CiAgX3BlbmRpbmdNZW1vcml6ZSA9IFtdOwp9CgovLyAtLSBTcGVsbGJvb2sgbGVhcm5pbmcgKGNhbGwgd2hlbiBwbGF5ZXIgZmluZHMgc2Nyb2xsIG9yIGxldmVscyB1cCkgLS0tLS0tLS0tLQpmdW5jdGlvbiBsZWFyblNwZWxsKHNwZWxsTmFtZSwgc3BlbGxEYXRhKSB7CiAgc3BlbGxCb29rW3NwZWxsTmFtZV0gPSB7CiAgICBuYW1lOiBzcGVsbE5hbWUsCiAgICBsZXZlbDogc3BlbGxEYXRhLmxldmVsLAogICAgdHlwZTogc3BlbGxEYXRhLnR5cGUgfHwgJ211JywKICAgIGtub3duOiB0cnVlLAogIH07CiAgQUxMX1NQRUxMX0xFVkVMU1tzcGVsbE5hbWVdID0gc3BlbGxEYXRhLmxldmVsOwogIHVwZGF0ZVNwZWxsYm9va1BhbmVsKCk7CiAgYWRkRW50cnlSYXcoJ1tTcGVsbCBsZWFybmVkOiAnICsgc3BlbGxOYW1lICsgJyAoTGV2ZWwgJyArIHNwZWxsRGF0YS5sZXZlbCArICcpXScsICdzeXN0ZW0nLCAnX19nbV9fJyk7Cn0KCi8vIC0tIEFiaWxpdHkgcGFuZWwgdXBkYXRlIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQpmdW5jdGlvbiB1cGRhdGVBYmlsaXR5UGFuZWwoKSB7CiAgY29uc3QgcGFuZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYWJpbGl0eS1wYW5lbCcpOwogIGlmICghcGFuZWwpIHJldHVybjsKCiAgY29uc3QgYWJpbGl0aWVzID0gZ2V0Q2xhc3NBYmlsaXRpZXNKUyhwYy5jbHMsIHBjLmxldmVsIHx8IDEpOwogIGlmICghYWJpbGl0aWVzLmxlbmd0aCkgeyBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOyByZXR1cm47IH0KICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gJyc7CgogIGxldCBodG1sID0gJyc7CiAgYWJpbGl0aWVzLmZvckVhY2goYWIgPT4gewogICAgY29uc3QgdXNlZFRvZGF5ID0gYWJpbGl0eVVzZXNUb2RheVthYi5uYW1lXSB8fCAwOwogICAgY29uc3QgbWF4VXNlcyA9IGFiLnVzZXMgPT09ICd1bmxpbWl0ZWQnIHx8IGFiLnVzZXMgPT09ICdhdF93aWxsJyA/IG51bGwgOgogICAgICBhYi51c2VzID09PSAnY29uY2VudHJhdGlvbicgPyBudWxsIDoKICAgICAgYWIudXNlcy5lbmRzV2l0aCgnX3Blcl9kYXknKSA/IHBhcnNlSW50KGFiLnVzZXMpIDogbnVsbDsKICAgIGNvbnN0IGV4aGF1c3RlZCA9IG1heFVzZXMgIT09IG51bGwgJiYgdXNlZFRvZGF5ID49IG1heFVzZXM7CiAgICBjb25zdCB1c2VzU3RyID0gbWF4VXNlcyAhPT0gbnVsbCA/IGAgKCR7dXNlZFRvZGF5fS8ke21heFVzZXN9KWAgOiAnJzsKICAgIGh0bWwgKz0gYDxzcGFuIGNsYXNzPSJhYmlsaXR5LWJhZGdlJHtleGhhdXN0ZWQ/JyBleGhhdXN0ZWQnOicnfSIKICAgICAgb25jbGljaz0ic2hvd0FiaWxpdHlJbmZvKCcke2FiLm5hbWV9JywnJHsoYWIuZGVzY3x8JycpLnJlcGxhY2UoLycvZywiWy5dXFwnIil9JykiCiAgICAgIHRpdGxlPSIke2FiLmRlc2N8fCcnfSI+JHthYi5uYW1lfSR7dXNlc1N0cn08L3NwYW4+YDsKICB9KTsKICBwYW5lbC5pbm5lckhUTUwgPSBodG1sOwp9CgpmdW5jdGlvbiBzaG93QWJpbGl0eUluZm8obmFtZSwgZGVzYykgewogIC8vIFNpbXBsZSB0b29sdGlwLXN0eWxlIGRpc3BsYXkgaW4gbG9nCiAgYWRkRW50cnlSYXcoYDxkaXYgc3R5bGU9ImJhY2tncm91bmQ6cmdiYSgxODAsMTMwLDIwLDAuMDgpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tZ29sZC1kaW0pOwogICAgcGFkZGluZzo2cHggMTBweDttYXJnaW46MnB4IDA7Zm9udC1zaXplOjEzcHg7Ij4KICAgIDxiIHN0eWxlPSJjb2xvcjp2YXIoLS1nb2xkKSI+JHtuYW1lfTwvYj48YnI+CiAgICA8c3BhbiBzdHlsZT0iY29sb3I6dmFyKC0tdGV4dC1kaW0pIj4ke2Rlc2N9PC9zcGFuPjwvZGl2PmAsICdzeXN0ZW0nLCAnX19nbV9fJyk7Cn0KCi8vIENsYXNzIGFiaWxpdGllcyB0YWJsZSAoY2xpZW50LXNpZGUgbWlycm9yIG9mIHNlcnZlciBkYXRhKQpmdW5jdGlvbiBnZXRDbGFzc0FiaWxpdGllc0pTKGNscywgbGV2ZWwpIHsKICBjb25zdCBhbGxfYWJpbGl0aWVzID0gewogICAgRmlnaHRlcjogICB7IDQ6W3tuYW1lOidFeHRyYSBBdHRhY2snLGRlc2M6JzMgYXR0YWNrcyBwZXIgMiByb3VuZHMnLHVzZXM6J3VubGltaXRlZCd9XSwKICAgICAgICAgICAgICAgICA4Olt7bmFtZTonRXh0cmEgQXR0YWNrJyxkZXNjOicyIGF0dGFja3MgcGVyIHJvdW5kJyx1c2VzOid1bmxpbWl0ZWQnfV0gfSwKICAgIENsZXJpYzogICAgeyAxOlt7bmFtZTonVHVybiBVbmRlYWQnLGRlc2M6J1R1cm4gdW5kZWFkIHVzaW5nIDJkNiB2cyBUdXJuIHRhYmxlJyx1c2VzOid1bmxpbWl0ZWQnfV0gfSwKICAgIFBhbGFkaW46ICAgeyAxOlt7bmFtZTonRGV0ZWN0IEV2aWwnLGRlc2M6J0RldGVjdCBldmlsIDYwZnQgYXQgd2lsbCcsdXNlczonYXRfd2lsbCd9LAogICAgICAgICAgICAgICAgICAgIHtuYW1lOidMYXkgb24gSGFuZHMnLGRlc2M6J0hlYWwgMkhQL2xldmVsL2RheScsdXNlczonMV9wZXJfZGF5J30sCiAgICAgICAgICAgICAgICAgICAge25hbWU6J0Rpc2Vhc2UgSW1tdW5pdHknLGRlc2M6J0ltbXVuZSB0byBkaXNlYXNlJyx1c2VzOidwYXNzaXZlJ31dLAogICAgICAgICAgICAgICAgIDM6W3tuYW1lOidUdXJuIFVuZGVhZCcsZGVzYzonVHVybiB1bmRlYWQgYXMgQ2xlcmljIDIgbGV2ZWxzIGxvd2VyJyx1c2VzOid1bmxpbWl0ZWQnfV0gfSwKICAgIFRoaWVmOiAgICAgeyAxOlt7bmFtZTonQmFja3N0YWInLGRlc2M6J3gyIGRhbWFnZSBmcm9tIGhpZGluZycsdXNlczoncGVyX2hpZGRlbl9hdHRhY2snfV0sCiAgICAgICAgICAgICAgICAgNTpbe25hbWU6J0JhY2tzdGFiJyxkZXNjOid4MyBiYWNrc3RhYicsdXNlczoncGVyX2hpZGRlbl9hdHRhY2snfV0sCiAgICAgICAgICAgICAgICAgOTpbe25hbWU6J0JhY2tzdGFiJyxkZXNjOid4NCBiYWNrc3RhYicsdXNlczoncGVyX2hpZGRlbl9hdHRhY2snfV0gfSwKICAgIEFzc2Fzc2luOiAgeyAxOlt7bmFtZTonQmFja3N0YWInLGRlc2M6J3gyIGJhY2tzdGFiJyx1c2VzOidwZXJfaGlkZGVuX2F0dGFjayd9LAogICAgICAgICAgICAgICAgICAgIHtuYW1lOidEaXNndWlzZScsZGVzYzonRGlzZ3Vpc2Ugc2VsZiAoYmFzZSA3MCUpJyx1c2VzOid1bmxpbWl0ZWQnfV0sCiAgICAgICAgICAgICAgICAgOTpbe25hbWU6J0Fzc2Fzc2luYXRlJyxkZXNjOidJbnN0YW50IGtpbGwgc3VycHJpc2VkIHRhcmdldHMnLHVzZXM6J3Blcl9zdXJwcmlzZWRfdmljdGltJ31dIH0sCiAgICBCYXJiYXJpYW46IHsgMTpbe25hbWU6J1JhZ2UnLGRlc2M6JysyIGF0dGFjay9kYW1hZ2UsIC0yIEFDIGZvciAzIHJvdW5kcycsdXNlczonMV9wZXJfZGF5J30sCiAgICAgICAgICAgICAgICAgICAge25hbWU6J1RyYXAgU2Vuc2UnLGRlc2M6JysyIHNhdmVzIHZzIHRyYXBzJyx1c2VzOidwYXNzaXZlJ31dLAogICAgICAgICAgICAgICAgIDQ6W3tuYW1lOidSYWdlJyxkZXNjOidSYWdlIDIvZGF5Jyx1c2VzOicyX3Blcl9kYXknfV0sCiAgICAgICAgICAgICAgICAgNzpbe25hbWU6J1JhZ2UnLGRlc2M6J1JhZ2UgMy9kYXknLHVzZXM6JzNfcGVyX2RheSd9LAogICAgICAgICAgICAgICAgICAgIHtuYW1lOidJbnRpbWlkYXRlJyxkZXNjOidGZWFyIDEvZGF5Jyx1c2VzOicxX3Blcl9kYXknfV0gfSwKICAgIFJhbmdlcjogICAgeyAxOlt7bmFtZTonVHJhY2tpbmcnLGRlc2M6J1RyYWNrIGNyZWF0dXJlcyBvdXRkb29ycycsdXNlczondW5saW1pdGVkJ30sCiAgICAgICAgICAgICAgICAgICAge25hbWU6J0Zhdm91cmVkIEVuZW15JyxkZXNjOicrMSBhdHRhY2svZGFtYWdlIHZzIGNob3NlbiB0eXBlJyx1c2VzOidwYXNzaXZlJ31dIH0sCiAgICBEcnVpZDogICAgIHsgNzpbe25hbWU6J1NoYXBlY2hhbmdlJyxkZXNjOidBbmltYWwgZm9ybSAzL2RheScsdXNlczonM19wZXJfZGF5J31dIH0sCiAgICBCYXJkOiAgICAgIHsgMTpbe25hbWU6J0luc3BpcmUgQ291cmFnZScsZGVzYzonKzEgYWxsaWVzIGF0dGFjay9zYXZlcycsdXNlczonY29uY2VudHJhdGlvbid9LAogICAgICAgICAgICAgICAgICAgIHtuYW1lOidCYXJkIExvcmUnLGRlc2M6J0tub3cgbGVnZW5kL2hpc3RvcnkgMS0yL2Q2Jyx1c2VzOid1bmxpbWl0ZWQnfV0sCiAgICAgICAgICAgICAgICAgMjpbe25hbWU6J0NoYXJtIFBlcnNvbicsZGVzYzonMS9kYXkgYXMgc3BlbGwnLHVzZXM6JzFfcGVyX2RheSd9XSB9LAogICAgTW9uazogICAgICB7IDE6W3tuYW1lOidTdHVubmluZyBBdHRhY2snLGRlc2M6J1N0dW4gb24gaGl0IChzYXZlIHZzIERlYXRoKScsdXNlczonMV9wZXJfcm91bmQnfV0sCiAgICAgICAgICAgICAgICAgNzpbe25hbWU6J1dob2xlbmVzcyBvZiBCb2R5JyxkZXNjOidIZWFsIDJIUC9sZXZlbCAxL2RheScsdXNlczonMV9wZXJfZGF5J31dIH0sCiAgfTsKICBjb25zdCB0YmwgPSBhbGxfYWJpbGl0aWVzW2Nsc10gfHwge307CiAgY29uc3QgcmVzdWx0ID0gW107CiAgY29uc3Qgc2VlbiA9IG5ldyBTZXQoKTsKICBPYmplY3QuZW50cmllcyh0YmwpLnNvcnQoKFthXSxbYl0pPT5hLWIpLmZvckVhY2goKFtyZXFMdmwsIGFic10pID0+IHsKICAgIGlmIChwYXJzZUludChyZXFMdmwpIDw9IGxldmVsKSB7CiAgICAgIGFicy5mb3JFYWNoKGFiID0+IHsKICAgICAgICBpZiAoIXNlZW4uaGFzKGFiLm5hbWUpKSB7IHNlZW4uYWRkKGFiLm5hbWUpOyByZXN1bHQucHVzaChhYik7IH0KICAgICAgICBlbHNlIHsKICAgICAgICAgIC8vIFJlcGxhY2Ugd2l0aCBoaWdoZXIgbGV2ZWwgdmVyc2lvbgogICAgICAgICAgY29uc3QgaSA9IHJlc3VsdC5maW5kSW5kZXgociA9PiByLm5hbWUgPT09IGFiLm5hbWUpOwogICAgICAgICAgaWYgKGkgPj0gMCkgcmVzdWx0W2ldID0gYWI7CiAgICAgICAgfQogICAgICB9KTsKICAgIH0KICB9KTsKICByZXR1cm4gcmVzdWx0Owp9CgovLyBTcGVsbCBkYXRhIGZvciBtZW1vcml6ZSBVSSAobWlycm9ycyBzZXJ2ZXIgUHl0aG9uIGRhdGEpCi8vIFRoZXNlIGFyZSBqdXN0IHRoZSBuYW1lcyArIG1ldGFkYXRhIG5lZWRlZCBjbGllbnQtc2lkZQpjb25zdCBNVV9TUEVMTFNfRk9SX0NMQVNTID0gewogICdDaGFybSBQZXJzb24nOntsZXZlbDoxLHJhbmdlOicxMjBmdCcsZHVyYXRpb246J1NwZWNpYWwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonQ2hhcm0gb25lIGh1bWFub2lkLiBTYXZlIHZzIFNwZWxscy4nfSwKICAnRGV0ZWN0IE1hZ2ljJzp7bGV2ZWw6MSxyYW5nZTonNjBmdCcsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZXRlY3QgbWFnaWNhbCBhdXJhcy4nfSwKICAnRmxvYXRpbmcgRGlzYyc6e2xldmVsOjEscmFuZ2U6JzZmdCcsZHVyYXRpb246JzYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidIb3ZlcmluZyBkaXNjIGNhcnJpZXMgNTAwIGxicy4nfSwKICAnSG9sZCBQb3J0YWwnOntsZXZlbDoxLHJhbmdlOicxMGZ0JyxkdXJhdGlvbjonMmQ2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonSG9sZCBkb29yL2dhdGUgc2h1dC4nfSwKICAnTGlnaHQnOntsZXZlbDoxLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonNiB0dXJucysxL2x2bCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOicxNWZ0IHJhZGl1cyBsaWdodC4nfSwKICAnTWFnaWMgTWlzc2lsZSc6e2xldmVsOjEscmFuZ2U6JzE1MGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzonMWQ2KzEnLGRlc2M6J0F1dG8taGl0IG1pc3NpbGUuJ30sCiAgJ1Byb3RlY3Rpb24gZnJvbSBFdmlsJzp7bGV2ZWw6MSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicyIHR1cm5zL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6JysxIEFDIGFuZCBzYXZlcyB2cyBldmlsLid9LAogICdSZWFkIExhbmd1YWdlcyc6e2xldmVsOjEscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicxIHR1cm4nLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZWFkIGFueSBsYW5ndWFnZS4nfSwKICAnUmVhZCBNYWdpYyc6e2xldmVsOjEscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicxIHR1cm4nLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZWFkIG1hZ2ljYWwgd3JpdGluZ3MuJ30sCiAgJ1NoaWVsZCc6e2xldmVsOjEscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQUMgMiB2cyBtaXNzaWxlcywgNCB2cyBtZWxlZS4nfSwKICAnU2xlZXAnOntsZXZlbDoxLHJhbmdlOicyNDBmdCcsZHVyYXRpb246JzRkNCB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6JzJkOCBIRCBvZiBjcmVhdHVyZXMgZmFsbCBhc2xlZXAuJ30sCiAgJ1ZlbnRyaWxvcXVpc20nOntsZXZlbDoxLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1Rocm93IHZvaWNlLid9LAogICdDb250aW51YWwgTGlnaHQnOntsZXZlbDoyLHJhbmdlOicxMjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidQZXJtYW5lbnQgbGlnaHQgc3BoZXJlLid9LAogICdEZXRlY3QgRXZpbCc6e2xldmVsOjIscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGV0ZWN0IGV2aWwgaW50ZW50aW9ucy4nfSwKICAnRGV0ZWN0IEludmlzaWJsZSc6e2xldmVsOjIscmFuZ2U6JzEwZnQvbHZsJyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1NlZSBpbnZpc2libGUgY3JlYXR1cmVzLid9LAogICdFU1AnOntsZXZlbDoyLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlYWQgc3VyZmFjZSB0aG91Z2h0cy4nfSwKICAnSW52aXNpYmlsaXR5Jzp7bGV2ZWw6MixyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidVbnRpbCBhdHRhY2snLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidJbnZpc2libGUgdW50aWwgYXR0YWNraW5nLid9LAogICdLbm9jayc6e2xldmVsOjIscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonT3BlbiBsb2NrZWQgZG9vcnMvY2hlc3RzLid9LAogICdMZXZpdGF0ZSc6e2xldmVsOjIscmFuZ2U6JzIwZnQvbHZsJyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1Jpc2UvZGVzY2VuZCBhdCA2ZnQvcm91bmQuJ30sCiAgJ0xvY2F0ZSBPYmplY3QnOntsZXZlbDoyLHJhbmdlOic2MGZ0KzEwL2x2bCcsZHVyYXRpb246JzEgcm91bmQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTZW5zZSBkaXJlY3Rpb24gdG8gb2JqZWN0Lid9LAogICdNaXJyb3IgSW1hZ2UnOntsZXZlbDoyLHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzonMWQ0JyxkZXNjOicxZDQgaWxsdXNvcnkgZHVwbGljYXRlcy4nfSwKICAnUGhhbnRhc21hbCBGb3JjZSc6e2xldmVsOjIscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonQ29uY2VudHJhdGlvbicsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidJbGx1c2lvbiB1cCB0byAyMHgyMHgyMGZ0Lid9LAogICdXZWInOntsZXZlbDoyLHJhbmdlOicxMGZ0JyxkdXJhdGlvbjonNDggdHVybnMnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonU3RpY2t5IHdlYnMgZW50YW5nbGUgY3JlYXR1cmVzLid9LAogICdXaXphcmQgTG9jayc6e2xldmVsOjIscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUGVybWFuZW50bHkgbG9jayBkb29yL2NoZXN0Lid9LAogICdDbGFpcnZveWFuY2UnOntsZXZlbDozLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1NlZSB0aHJvdWdoIHdhbGxzLid9LAogICdEaXNwZWwgTWFnaWMnOntsZXZlbDozLHJhbmdlOicxMjBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZW1vdmUgbWFnaWMgZWZmZWN0cy4nfSwKICAnRmlyZWJhbGwnOntsZXZlbDozLHJhbmdlOicyNDBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6J1NwZWxscycsZG1nOicxZDYvbHZsJyxkZXNjOicyMGZ0IGV4cGxvc2lvbi4nfSwKICAnRmx5Jzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicxZDYrMSB0dXJucy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidGbHkgYXQgMTIwZnQvdHVybi4nfSwKICAnSGFzdGUnOntsZXZlbDozLHJhbmdlOicyNDBmdCcsZHVyYXRpb246JzMgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEb3VibGUgc3BlZWQvYXR0YWNrcy4gQWdlcyAxIHllYXIuJ30sCiAgJ0hvbGQgUGVyc29uJzp7bGV2ZWw6MyxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6JzEtNCBodW1hbm9pZHMgcGFyYWx5c2VkLid9LAogICdJbmZyYXZpc2lvbic6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMSBkYXknLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTZWUgaW4gZGFya25lc3MgNjBmdC4nfSwKICAnSW52aXNpYmlsaXR5IDEwZnQgUmFkaXVzJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidVbnRpbCBhdHRhY2snLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidBbGwgaW4gMTBmdCBpbnZpc2libGUuJ30sCiAgJ0xpZ2h0bmluZyBCb2x0Jzp7bGV2ZWw6MyxyYW5nZTonU2VsZicsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6J1NwZWxscycsZG1nOicxZDYvbHZsJyxkZXNjOic2MGZ0IGJvbHQuJ30sCiAgJ1Byb3RlY3Rpb24gZnJvbSBFdmlsIDEwZnQgUmFkaXVzJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicyIHR1cm5zL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1Byb3RlY3Rpb24gYXVyYSAxMGZ0Lid9LAogICdQcm90ZWN0aW9uIGZyb20gTm9ybWFsIE1pc3NpbGVzJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicyIHR1cm5zL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0ltbXVuZSB0byBub24tbWFnaWNhbCBtaXNzaWxlcy4nfSwKICAnV2F0ZXIgQnJlYXRoaW5nJzp7bGV2ZWw6MyxyYW5nZTonMzBmdCcsZHVyYXRpb246JzEgZGF5JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQnJlYXRoZSB1bmRlcndhdGVyLid9LAogICdDaGFybSBNb25zdGVyJzp7bGV2ZWw6NCxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidTcGVjaWFsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0NoYXJtIGFueSBjcmVhdHVyZSB0eXBlLid9LAogICdDb25mdXNpb24nOntsZXZlbDo0LHJhbmdlOicxMjBmdCcsZHVyYXRpb246JzIgcm91bmRzL2x2bCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOicyZDYgY3JlYXR1cmVzIGFjdCByYW5kb21seS4nfSwKICAnRGltZW5zaW9uIERvb3InOntsZXZlbDo0LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1RlbGVwb3J0IDM2MGZ0IGluc3RhbnRseS4nfSwKICAnR3Jvd3RoIG9mIFBsYW50cyc6e2xldmVsOjQscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGVuc2UgZW50YW5nbGluZyBwbGFudHMuJ30sCiAgJ0ljZSBTdG9ybSc6e2xldmVsOjQscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzonM2QxMCcsZGVzYzonM2QxMCBoYWlsIGRhbWFnZS4nfSwKICAnUG9seW1vcnBoIE90aGVycyc6e2xldmVsOjQscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonVHJhbnNmb3JtIGNyZWF0dXJlLid9LAogICdQb2x5bW9ycGggU2VsZic6e2xldmVsOjQscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOic2IHR1cm5zL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1Rha2UgY3JlYXR1cmUgZm9ybS4nfSwKICAnUmVtb3ZlIEN1cnNlJzp7bGV2ZWw6NCxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZW1vdmUgb25lIGN1cnNlLid9LAogICdXYWxsIG9mIEZpcmUnOntsZXZlbDo0LHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonQ29uY2VudHJhdGlvbicsc2F2ZTpudWxsLGRtZzonMmQ2KzEnLGRlc2M6J0ZpcmUgd2FsbCBkYW1hZ2UuJ30sCiAgJ1dpemFyZCBFeWUnOntsZXZlbDo0LHJhbmdlOicyNDBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidJbnZpc2libGUgZXllIHNjb3V0cyBhaGVhZC4nfSwKICAnQW5pbWF0ZSBEZWFkJzp7bGV2ZWw6NSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSYWlzZSB1bmRlYWQgc2VydmFudHMuJ30sCiAgJ0Nsb3Vka2lsbCc6e2xldmVsOjUscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicxIHR1cm4nLHNhdmU6J0RlYXRoJyxkbWc6bnVsbCxkZXNjOidQb2lzb25vdXMgY2xvdWQga2lsbHMgPDUgSEQuJ30sCiAgJ0Nvbmp1cmUgRWxlbWVudGFsJzp7bGV2ZWw6NSxyYW5nZTonMjQwZnQnLGR1cmF0aW9uOidDb25jZW50cmF0aW9uJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU3VtbW9uIDE2IEhEIGVsZW1lbnRhbC4nfSwKICAnRmVlYmxlbWluZCc6e2xldmVsOjUscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOidTcGVsbHMtNCcsZG1nOm51bGwsZGVzYzonSU5UIHJlZHVjZWQgdG8gMi4nfSwKICAnSG9sZCBNb25zdGVyJzp7bGV2ZWw6NSxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6JzEtNCBjcmVhdHVyZXMgcGFyYWx5c2VkLid9LAogICdQYXNzLVdhbGwnOntsZXZlbDo1LHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMyB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1R1bm5lbCB0aHJvdWdoIHN0b25lLid9LAogICdUZWxla2luZXNpcyc6e2xldmVsOjUscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonMiByb3VuZHMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonTW92ZSAyMDAgbGJzL2xldmVsLid9LAogICdUZWxlcG9ydCc6e2xldmVsOjUscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0luc3RhbnQgdHJhbnNwb3J0Lid9LAogICdXYWxsIG9mIFN0b25lJzp7bGV2ZWw6NSxyYW5nZTonNjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NyZWF0ZSBzdG9uZSB3YWxsLid9LAogICdBbnRpLU1hZ2ljIFNoZWxsJzp7bGV2ZWw6NixyYW5nZTonU2VsZicsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidCbG9ja3MgYWxsIG1hZ2ljLid9LAogICdEZWF0aCBTcGVsbCc6e2xldmVsOjYscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzonNGQ4JyxkZXNjOidVcCB0byA0ZDggSEQgZGllIGluc3RhbnRseS4nfSwKICAnRGlzaW50ZWdyYXRlJzp7bGV2ZWw6NixyYW5nZTonNjBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonRGVzdHJveSB0YXJnZXQgdXR0ZXJseS4nfSwKICAnR2Vhcyc6e2xldmVsOjYscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOidVbnRpbCBmdWxmaWxsZWQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonQ29tcGVsIHRvIGNvbXBsZXRlIHF1ZXN0Lid9LAogICdJbnZpc2libGUgU3RhbGtlcic6e2xldmVsOjYscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOidVbnRpbCBkb25lJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU3VtbW9uIGh1bnRlci4nfSwKICAnTW92ZSBFYXJ0aCc6e2xldmVsOjYscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J01vdmUgZGlydC9jbGF5Lid9LAogICdSZWluY2FybmF0aW9uJzp7bGV2ZWw6NixyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZXR1cm4gZGVhZCBpbiBuZXcgYm9keS4nfSwKICAnU3RvbmUgdG8gRmxlc2gnOntsZXZlbDo2LHJhbmdlOicxMjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JldmVyc2UgcGV0cmlmaWNhdGlvbi4nfSwKfTsKCmNvbnN0IENMRVJJQ19TUEVMTFNfRk9SX0NMQVNTID0gewogICdDdXJlIExpZ2h0IFdvdW5kcyc6e2xldmVsOjEscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOicxZDYrMScsZGVzYzonUmVzdG9yZSAxZDYrMSBIUC4nfSwKICAnRGV0ZWN0IEV2aWwnOntsZXZlbDoxLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RldGVjdCBldmlsLid9LAogICdEZXRlY3QgTWFnaWMnOntsZXZlbDoxLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RldGVjdCBtYWdpYy4nfSwKICAnTGlnaHQnOntsZXZlbDoxLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonNiB0dXJucysxL2x2bCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOicxNWZ0IHJhZGl1cyBsaWdodC4nfSwKICAnUHJvdGVjdGlvbiBmcm9tIEV2aWwnOntsZXZlbDoxLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzIgdHVybnMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonKzEgQUMvc2F2ZXMgdnMgZXZpbC4nfSwKICAnUHVyaWZ5IEZvb2QgJiBXYXRlcic6e2xldmVsOjEscmFuZ2U6JzEwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidQdXJpZnkgZm9vZC93YXRlci4nfSwKICAnUmVtb3ZlIEZlYXInOntsZXZlbDoxLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1NwZWNpYWwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZW1vdmUgZmVhciBlZmZlY3QuJ30sCiAgJ1Jlc2lzdCBDb2xkJzp7bGV2ZWw6MSxyYW5nZTonMzBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOicrMyBzYXZlcyB2cyBjb2xkLid9LAogICdCbGVzcyc6e2xldmVsOjIscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOic2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonKzEgYXR0YWNrIGFuZCBtb3JhbGUuJ30sCiAgJ0ZpbmQgVHJhcHMnOntsZXZlbDoyLHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RldGVjdCB0cmFwcyAzMGZ0Lid9LAogICdIb2xkIFBlcnNvbic6e2xldmVsOjIscmFuZ2U6JzE4MGZ0JyxkdXJhdGlvbjonOSB0dXJucycsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOicxLTMgaHVtYW5vaWRzIHBhcmFseXNlZC4nfSwKICAnS25vdyBBbGlnbm1lbnQnOntsZXZlbDoyLHJhbmdlOicxMGZ0JyxkdXJhdGlvbjonMSByb3VuZCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0xlYXJuIGV4YWN0IGFsaWdubWVudC4nfSwKICAnUmVzaXN0IEZpcmUnOntsZXZlbDoyLHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6JysyIHNhdmVzIHZzIG1hZ2ljYWwgZmlyZS4nfSwKICAnU2lsZW5jZSAxNWZ0IFJhZGl1cyc6e2xldmVsOjIscmFuZ2U6JzE4MGZ0JyxkdXJhdGlvbjonMTIgdHVybnMnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonTm8gc291bmQgaW4gYXJlYS4nfSwKICAnU25ha2UgQ2hhcm0nOntsZXZlbDoyLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonU3BlY2lhbCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NoYXJtIDEgSEQvbGV2ZWwgb2Ygc25ha2VzLid9LAogICdTcGVhayB3aXRoIEFuaW1hbHMnOntsZXZlbDoyLHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NvbW11bmljYXRlIHdpdGggYW5pbWFscy4nfSwKICAnQ3VyZSBEaXNlYXNlJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDdXJlIG9uZSBkaXNlYXNlLid9LAogICdHcm93dGggb2YgQW5pbWFscyc6e2xldmVsOjMscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonMTIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEb3VibGUgYW5pbWFsIHNpemUuJ30sCiAgJ0xvY2F0ZSBPYmplY3QnOntsZXZlbDozLHJhbmdlOic5MGZ0KzEwL2x2bCcsZHVyYXRpb246JzEgcm91bmQvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU2Vuc2UgZGlyZWN0aW9uIHRvIG9iamVjdC4nfSwKICAnUmVtb3ZlIEN1cnNlJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZW1vdmUgb25lIGN1cnNlLid9LAogICdTdHJpa2luZyc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMSB0dXJuJyxzYXZlOm51bGwsZG1nOicxZDYnLGRlc2M6JysxZDYgZGFtYWdlLCB3ZWFwb24gY291bnRzIGFzIG1hZ2ljYWwuJ30sCiAgJ0NvbnRpbnVhbCBMaWdodCc6e2xldmVsOjMscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J1Blcm1hbmVudCBsaWdodC4nfSwKICAnQ3JlYXRlIFdhdGVyJzp7bGV2ZWw6NCxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDcmVhdGUgNTAgZ2FsL2xldmVsLid9LAogICdDdXJlIFNlcmlvdXMgV291bmRzJzp7bGV2ZWw6NCxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6JzJkNisyJyxkZXNjOidSZXN0b3JlIDJkNisyIEhQLid9LAogICdOZXV0cmFsaXplIFBvaXNvbic6e2xldmVsOjQscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVtb3ZlIHBvaXNvbi4nfSwKICAnUHJvdGVjdGlvbiBmcm9tIEV2aWwgMTBmdCBSYWRpdXMnOntsZXZlbDo0LHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzIgdHVybnMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUHJvdGVjdGlvbiBhdXJhLid9LAogICdTcGVhayB3aXRoIFBsYW50cyc6e2xldmVsOjQscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOiczIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ29tbXVuaWNhdGUgd2l0aCBwbGFudHMuJ30sCiAgJ1N0aWNrcyB0byBTbmFrZXMnOntsZXZlbDo0LHJhbmdlOicxMjBmdCcsZHVyYXRpb246JzYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOicyZDggc3RpY2tzIGJlY29tZSBzbmFrZXMuJ30sCiAgJ1Rvbmd1ZXMnOntsZXZlbDo0LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMSB0dXJuJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonVW5kZXJzdGFuZC9zcGVhayBhbnkgbGFuZ3VhZ2UuJ30sCiAgJ0NvbW11bmUnOntsZXZlbDo1LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMyBxdWVzdGlvbnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidBc2sgZGVpdHkgMyB5ZXMvbm8gcXVlc3Rpb25zLid9LAogICdDcmVhdGUgRm9vZCc6e2xldmVsOjUscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRm9vZCBmb3IgMjQgcGVyIGxldmVsLid9LAogICdDdXJlIENyaXRpY2FsIFdvdW5kcyc6e2xldmVsOjUscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOiczZDYrMycsZGVzYzonUmVzdG9yZSAzZDYrMyBIUC4nfSwKICAnRGlzcGVsIEV2aWwnOntsZXZlbDo1LHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidEaXNwZWwgZXZpbCBjcmVhdHVyZS9lbmNoYW50bWVudC4nfSwKICAnSW5zZWN0IFBsYWd1ZSc6e2xldmVsOjUscmFuZ2U6JzQ4MGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1N3YXJtIHJvdXRzIDwzIEhELid9LAogICdRdWVzdCc6e2xldmVsOjUscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOidVbnRpbCBmdWxmaWxsZWQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonQ29tcGVsIHF1ZXN0IGNvbXBsZXRpb24uJ30sCiAgJ1JhaXNlIERlYWQnOntsZXZlbDo1LHJhbmdlOicxMjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1Jlc3RvcmUgbGlmZS4nfSwKICAnVHJ1ZSBTZWVpbmcnOntsZXZlbDo1LHJhbmdlOicxMjBmdCcsZHVyYXRpb246JzEgcm91bmQvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU2VlIGludmlzaWJsZS9pbGx1c2lvbnMuJ30sCiAgJ0FuaW1hdGUgT2JqZWN0cyc6e2xldmVsOjYscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicxIHJvdW5kL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0FuaW1hdGUgbm9uLWxpdmluZyBvYmplY3RzLid9LAogICdCbGFkZSBCYXJyaWVyJzp7bGV2ZWw6NixyYW5nZTonMzBmdCcsZHVyYXRpb246JzMgcm91bmRzL2x2bCcsc2F2ZTpudWxsLGRtZzonMmQ2JyxkZXNjOidXYWxsIG9mIGJsYWRlcyAyZDYuJ30sCiAgJ0ZpbmQgdGhlIFBhdGgnOntsZXZlbDo2LHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidLbm93IHJvdXRlIHRvIGRlc3RpbmF0aW9uLid9LAogICdTcGVhayB3aXRoIE1vbnN0ZXJzJzp7bGV2ZWw6NixyYW5nZTonMzBmdCcsZHVyYXRpb246JzEgcm91bmQvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ29tbXVuaWNhdGUgd2l0aCBhbnkgY3JlYXR1cmUuJ30sCiAgJ1dvcmQgb2YgUmVjYWxsJzp7bGV2ZWw6NixyYW5nZTonU2VsZicsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZXR1cm4gdG8gc2FuY3R1YXJ5IGluc3RhbnRseS4nfSwKfTsKCi8vIERydWlkL1Jhbmdlci9QYWxhZGluIHVzZSBzdWJzZXQgb2YgQ2xlcmljIHNwZWxscyArIHNvbWUgRHJ1aWQtc3BlY2lmaWMKY29uc3QgRFJVSURfU1BFTExTX0ZPUl9DTEFTUyA9IHsKICAnQW5pbWFsIEZyaWVuZHNoaXAnOntsZXZlbDoxLHJhbmdlOicxMGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0JlZnJpZW5kIG5vcm1hbCBhbmltYWwuJ30sCiAgJ0RldGVjdCBNYWdpYyc6e2xldmVsOjEscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGV0ZWN0IG1hZ2ljLid9LAogICdFbnRhbmdsZSc6e2xldmVsOjEscmFuZ2U6JzgwZnQnLGR1cmF0aW9uOicxIHR1cm4nLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonUGxhbnRzIGdyYXNwIGNyZWF0dXJlcy4nfSwKICAnRmFlcmllIEZpcmUnOntsZXZlbDoxLHJhbmdlOic4MGZ0JyxkdXJhdGlvbjonNCByb3VuZHMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonT3V0bGluZSBjcmVhdHVyZXMsIC0yIEFDLid9LAogICdQdXJpZnkgV2F0ZXInOntsZXZlbDoxLHJhbmdlOic0MGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUHVyaWZ5IDEgY3UgZnQvbGV2ZWwuJ30sCiAgJ1NwZWFrIHdpdGggQW5pbWFscyc6e2xldmVsOjEscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOic2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ29tbXVuaWNhdGUgd2l0aCBhbmltYWxzLid9LAogICdCYXJrc2tpbic6e2xldmVsOjIscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonNCByb3VuZHMrMS9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidBQyBiZWNvbWVzIDYgbWluLid9LAogICdDdXJlIExpZ2h0IFdvdW5kcyc6e2xldmVsOjIscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOicxZDYrMScsZGVzYzonUmVzdG9yZSAxZDYrMSBIUC4nfSwKICAnSGVhdCBNZXRhbCc6e2xldmVsOjIscmFuZ2U6JzQwZnQnLGR1cmF0aW9uOic3IHJvdW5kcycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J01ldGFsIGhlYXRzIGRhbmdlcm91c2x5Lid9LAogICdQcm9kdWNlIEZsYW1lJzp7bGV2ZWw6MixyYW5nZTonU2VsZicsZHVyYXRpb246JzEgcm91bmQvbHZsJyxzYXZlOm51bGwsZG1nOicxZDQrMScsZGVzYzonRmxhbWUgd2VhcG9uIG9yIG1pc3NpbGUuJ30sCiAgJ0NhbGwgTGlnaHRuaW5nJzp7bGV2ZWw6MyxyYW5nZTonMzYwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOidTcGVsbHMnLGRtZzonMmQ4K2x2bCcsZGVzYzonTGlnaHRuaW5nIDEvcm91bmQgb3V0ZG9vcnMuJ30sCiAgJ0N1cmUgRGlzZWFzZSc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ3VyZSBkaXNlYXNlLid9LAogICdIb2xkIEFuaW1hbCc6e2xldmVsOjMscmFuZ2U6JzgwZnQnLGR1cmF0aW9uOicyIHJvdW5kcy9sdmwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonMS00IGFuaW1hbHMgcGFyYWx5c2VkLid9LAogICdQbGFudCBHcm93dGgnOntsZXZlbDozLHJhbmdlOicxNjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RlbnNlIGltcGFzc2FibGUgdmVnZXRhdGlvbi4nfSwKICAnUHJvdGVjdGlvbiBmcm9tIEZpcmUnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1NwZWNpYWwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidBYnNvcmJzIDEyIHBvaW50cy9sdmwgZmlyZS4nfSwKICAnV2F0ZXIgQnJlYXRoaW5nJzp7bGV2ZWw6MyxyYW5nZTonMzBmdCcsZHVyYXRpb246JzEgZGF5JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQnJlYXRoZSB3YXRlci4nfSwKICAnRGlzcGVsIE1hZ2ljJzp7bGV2ZWw6NCxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVtb3ZlIG1hZ2ljLid9LAogICdOZXV0cmFsaXplIFBvaXNvbic6e2xldmVsOjQscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVtb3ZlIHBvaXNvbi4nfSwKICAnQ3VyZSBTZXJpb3VzIFdvdW5kcyc6e2xldmVsOjQscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOicyZDYrMicsZGVzYzonUmVzdG9yZSAyZDYrMiBIUC4nfSwKICAnSW5zZWN0IFBsYWd1ZSc6e2xldmVsOjUscmFuZ2U6JzQ4MGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0luc2VjdCBzd2FybS4nfSwKICAnVHJhbnNtdXRlIFJvY2sgdG8gTXVkJzp7bGV2ZWw6NSxyYW5nZTonMTYwZnQnLGR1cmF0aW9uOiczZDYgZGF5cycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1R1cm4gcm9jayB0byBtdWQuJ30sCiAgJ0NvbW11bmUgd2l0aCBOYXR1cmUnOntsZXZlbDo1LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0tub3cgdGVycmFpbiAxIG1pbGUvbGV2ZWwuJ30sCiAgJ0N1cmUgQ3JpdGljYWwgV291bmRzJzp7bGV2ZWw6NixyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6JzNkNiszJyxkZXNjOidSZXN0b3JlIDNkNiszIEhQLid9LAogICdDb250cm9sIFdlYXRoZXInOntsZXZlbDo2LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonNGQxMiBob3Vycycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NvbnRyb2wgbG9jYWwgd2VhdGhlci4nfSwKfTsKCmNvbnN0IFJBTkdFUl9TUEVMTFNfRk9SX0NMQVNTID0gT2JqZWN0LmZyb21FbnRyaWVzKAogIE9iamVjdC5lbnRyaWVzKERSVUlEX1NQRUxMU19GT1JfQ0xBU1MpLmZpbHRlcigoWyx2XSk9PnYubGV2ZWw8PTMpCik7CmNvbnN0IEJBUkRfU1BFTExTX0ZPUl9DTEFTUyA9IE9iamVjdC5mcm9tRW50cmllcygKICBPYmplY3QuZW50cmllcyhDTEVSSUNfU1BFTExTX0ZPUl9DTEFTUykuZmlsdGVyKChbLHZdKT0+di5sZXZlbDw9MykKKTsKCi8vIFBvcHVsYXRlIEFMTF9TUEVMTF9MRVZFTFMgbG9va3VwCltNVV9TUEVMTFNfRk9SX0NMQVNTLCBDTEVSSUNfU1BFTExTX0ZPUl9DTEFTUywgRFJVSURfU1BFTExTX0ZPUl9DTEFTU10uZm9yRWFjaCh0YmwgPT4gewogIE9iamVjdC5lbnRyaWVzKHRibCkuZm9yRWFjaCgoW25hbWUsZGF0YV0pID0+IHsKICAgIEFMTF9TUEVMTF9MRVZFTFNbbmFtZV0gPSBkYXRhLmxldmVsOwogIH0pOwp9KTsKCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBHQU1FIElOSVQgT1ZFUlJJREVTIEZPUiBWNAovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KCi8vIENhbGxlZCBhZnRlciBiZWdpbkFkdmVudHVyZSAvIGxhdW5jaEdhbWUgdG8gaW5pdCBWNCBzdGF0ZQpmdW5jdGlvbiBpbml0VjRTdGF0ZSgpIHsKICAvLyBJbml0IHNwZWxsIHNsb3RzIGZyb20gY2xhc3MvbGV2ZWwKICBjb25zdCBzbG90cyA9IGdldFNwZWxsU2xvdHNKUyhwYy5jbHMsIHBjLmxldmVsIHx8IDEpOwogIHNwZWxsU2xvdHNUb3RhbCA9IHNsb3RzOwogIHNwZWxsU2xvdHNSZW1haW5pbmcgPSBbLi4uc2xvdHNdOwoKICAvLyBDbGVyaWNzL0RydWlkcyBzdGFydCB3aXRoIGFsbCBzcGVsbHMgYXZhaWxhYmxlIChubyBzcGVsbGJvb2sgbmVlZGVkKQogIGlmIChbJ0NsZXJpYycsJ0RydWlkJywnUmFuZ2VyJywnUGFsYWRpbiddLmluY2x1ZGVzKHBjLmNscykpIHsKICAgIHNwZWxsQm9vayA9IHt9OyAvLyBUaGV5IHByYXkgZm9yIHNwZWxscywgbm8gYm9vayBuZWVkZWQKICB9CiAgLy8gTVUvSWxsdXNpb25pc3QgZ2V0IHN0YXJ0aW5nIHNwZWxscyAoUmVhZCBNYWdpYyArIDEgcmFuZG9tIGxldmVsIDEgc3BlbGwpCiAgaWYgKFsnTWFnaWMtVXNlcicsJ0lsbHVzaW9uaXN0J10uaW5jbHVkZXMocGMuY2xzKSkgewogICAgbGVhcm5TcGVsbCgnUmVhZCBNYWdpYycsIHtsZXZlbDoxLCB0eXBlOidtdSd9KTsKICAgIC8vIFBpY2sgYSBzdGFydGluZyBzcGVsbCBmcm9tIGxldmVsIDEKICAgIGNvbnN0IGxldmVsMSA9IE9iamVjdC5lbnRyaWVzKE1VX1NQRUxMU19GT1JfQ0xBU1MpLmZpbHRlcigoWyx2XSk9PnYubGV2ZWw9PT0xKTsKICAgIGlmIChsZXZlbDEubGVuZ3RoID4gMCkgewogICAgICBjb25zdCBbc3RhcnRTcGVsbCwgc3RhcnREYXRhXSA9IGxldmVsMVtNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkqbGV2ZWwxLmxlbmd0aCldOwogICAgICBsZWFyblNwZWxsKHN0YXJ0U3BlbGwsIHtsZXZlbDoxLCB0eXBlOidtdSd9KTsKICAgIH0KICB9CgogIGluQ29tYmF0ID0gZmFsc2U7CiAgcGxheWVySGlkZGVuID0gZmFsc2U7CiAgY3VycmVudE5QQ3MgPSBbXTsKICBhY3RpdmVFZmZlY3RzVjQgPSBbXTsKICBhYmlsaXR5VXNlc1RvZGF5ID0ge307CgogIHVwZGF0ZVNwZWxsYm9va1BhbmVsKCk7CiAgdXBkYXRlQWJpbGl0eVBhbmVsKCk7Cn0KCi8vIFNwZWxsIHNsb3QgdGFibGUgSlMgbWlycm9yIChtYXRjaGVzIHNlcnZlciBQeXRob24gZGF0YSkKZnVuY3Rpb24gZ2V0U3BlbGxTbG90c0pTKGNscywgbGV2ZWwpIHsKICBjb25zdCB0YWJsZXMgPSB7CiAgICAnTWFnaWMtVXNlcic6ICBbWzFdLFsyXSxbMiwxXSxbMiwyXSxbMiwyLDFdLFsyLDIsMl0sWzMsMiwyLDFdLFszLDMsMiwyXSxbMywzLDMsMiwxXSxbMywzLDMsMywyXSxbNCwzLDMsMywyLDFdLFs0LDQsMywzLDMsMl0sWzQsNCw0LDMsMywzXSxbNCw0LDQsNCw0LDRdXSwKICAgICdJbGx1c2lvbmlzdCc6IFtbMV0sWzJdLFsyLDFdLFsyLDJdLFszLDIsMV0sWzMsMiwyXSxbMywzLDIsMV0sWzMsMywzLDJdLFs0LDMsMywyLDFdLFs0LDQsMywzLDJdLFs0LDQsNCwzLDIsMV0sWzQsNCw0LDQsMywyXSxbNSw1LDQsNCwzLDNdLFs1LDUsNSw0LDQsNF1dLAogICAgJ0NsZXJpYyc6ICAgICAgW1sxXSxbMl0sWzIsMV0sWzMsMl0sWzMsMywxXSxbMywzLDJdLFszLDMsMiwxXSxbMywzLDMsMl0sWzQsNCwzLDIsMV0sWzQsNCwzLDMsMl0sWzUsNCw0LDMsMiwxXSxbNSw1LDQsNCwzLDJdLFs1LDUsNSw0LDMsM10sWzYsNSw1LDUsNCw0XV0sCiAgICAnRHJ1aWQnOiAgICAgICBbWzFdLFsyXSxbMiwxXSxbMywyXSxbMywzLDFdLFszLDMsMl0sWzMsMywyLDFdLFszLDMsMywyXSxbNCw0LDMsMiwxXSxbNCw0LDMsMywyXSxbNSw0LDQsMywyLDFdLFs1LDUsNCw0LDMsMl0sWzUsNSw1LDQsMywzXSxbNiw1LDUsNSw0LDRdXSwKICAgICdSYW5nZXInOiAgICAgIFtbXSxbXSxbXSxbXSxbXSxbXSxbXSxbMV0sWzEsMV0sWzIsMV0sWzIsMl0sWzIsMiwxXSxbMywyLDFdLFszLDIsMl1dLAogICAgJ1BhbGFkaW4nOiAgICAgW1tdLFtdLFtdLFtdLFtdLFtdLFtdLFtdLFsxXSxbMl0sWzIsMV0sWzIsMl0sWzMsMl0sWzMsM11dLAogIH07CiAgY29uc3QgdGJsID0gdGFibGVzW2Nsc107CiAgaWYgKCF0YmwpIHJldHVybiBbXTsKICBjb25zdCBpZHggPSBNYXRoLm1pbigobGV2ZWx8fDEpLTEsIHRibC5sZW5ndGgtMSk7CiAgcmV0dXJuIFsuLi50YmxbaWR4XV07Cn0KCi8vIFJlc2V0IGFiaWxpdHkgdXNlcyBkYWlseSAoY2FsbCBvbiBmdWxsIHJlc3QpCmZ1bmN0aW9uIHJlc2V0RGFpbHlBYmlsaXRpZXMoKSB7CiAgYWJpbGl0eVVzZXNUb2RheSA9IHt9OwogIHVwZGF0ZUFiaWxpdHlQYW5lbCgpOwp9CgoKLy8gLS0gU3RhcnR1cCAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQp3aW5kb3cuYWRkRXZlbnRMaXN0ZW5lcignRE9NQ29udGVudExvYWRlZCcsICgpID0+IHsKICBzaG93KCdzLWxvYmJ5Jyk7CiAgY2hlY2tPbGxhbWFTdGF0dXMoKTsKICBjaGVja05ncm9rU3RhdHVzKCk7CiAgcm90YXRlQmFubmVkUGhyYXNlcygpOwogIHNldEludGVydmFsKHJvdGF0ZUJhbm5lZFBocmFzZXMsIDYwMDAwKTsKICBzZXRJbnRlcnZhbCh0aWNrRWZmZWN0cywgMTAwMCk7CiAgY29uc3QgcG5pID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1uYW1lLWlucCcpOwogIGlmIChwbmkpIHBuaS5hZGRFdmVudExpc3RlbmVyKCdrZXlkb3duJywgZSA9PiB7IGlmKGUua2V5PT09J0VudGVyJykgZ29Ib21lKCk7IH0pOwogIGNvbnN0IGNtZCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKTsKICBpZiAoY21kKSBjbWQuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsIGUgPT4geyBpZihlLmtleT09PSdFbnRlcicgJiYgIWUuc2hpZnRLZXkpIHsgZS5wcmV2ZW50RGVmYXVsdCgpOyBzZW5kKCk7IH0gfSk7CiAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsIGUgPT4gewogICAgaWYgKGUua2V5ID09PSAnRXNjYXBlJykgewogICAgICBjb25zdCBtID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbW9yaXplLW1vZGFsJykgfHwgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2x2LW1vZGFsJyk7CiAgICAgIGlmIChtKSBtLnJlbW92ZSgpOwogICAgfQogIH0pOwp9KTsKCi8vIFY0IHN0YXRlIGluaXQgaXMgY2FsbGVkIGRpcmVjdGx5IGZyb20gYmVnaW5BZHZlbnR1cmUgYW5kIGxhdW5jaEdhbWUK"

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>D&D Adventure Engine V4 (build 1778942309)</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IM+Fell+English:ital@0;1&family=Crimson+Text:ital,wght@0,400;0,600;1,400&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>

@import url('https://fonts.googleapis.com/css2?family=IM+Fell+English:ital@0;1&family=Share+Tech+Mono&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
:root{
  --bg:#0f0d0a;--panel:#141210;--border:#3a2e1a;
  --gold:#c9a84c;--gold-dim:#7a6030;
  --ink:#ddd0a8;--ink-dim:#8a7a58;
  --blood:#8b2525;--green:#3a7a3a;--blue:#4060a0;
}
html,body{height:100%;background:var(--bg);color:var(--ink);font-family:'Share Tech Mono','Courier New',monospace;font-size:19px;overflow:hidden;margin:0;}
.screen{display:none;height:100vh;overflow-y:scroll;flex-direction:column;align-items:center;justify-content:flex-start;padding:2rem 1.5rem 6rem 1.5rem;gap:14px;box-sizing:border-box;}
.screen.active{display:flex;}
.title{font-family:'IM Fell English',Georgia,serif;font-size:24px;color:var(--gold);text-align:center;line-height:1.3;}
.sub{color:var(--ink-dim);font-size:16px;text-align:center;max-width:500px;line-height:1.7;}
.btn{background:transparent;border:1px solid var(--gold-dim);color:var(--gold);font-family:'Share Tech Mono',monospace;font-size:17px;padding:9px 22px;cursor:pointer;transition:all .15s;}
.btn:hover{background:rgba(201,168,76,.12);border-color:var(--gold);}
.btn:disabled{opacity:.4;cursor:not-allowed;}
.field{background:var(--panel);border:1px solid var(--border);color:var(--ink);font-family:'Share Tech Mono',monospace;font-size:19px;padding:9px 12px;outline:none;width:100%;}
.field:focus{border-color:var(--gold-dim);}
.lbl{font-size:14px;letter-spacing:2px;color:var(--ink-dim);text-transform:uppercase;align-self:flex-start;width:100%;max-width:560px;}
.hint{font-size:14px;color:var(--ink-dim);line-height:1.6;max-width:440px;text-align:center;}
.box{display:flex;flex-direction:column;gap:8px;width:100%;max-width:440px;}
.row{display:flex;gap:10px;align-items:center;width:100%;max-width:560px;}
.pane-title{font-size:13px;letter-spacing:2px;color:var(--gold-dim);text-transform:uppercase;border-bottom:1px solid var(--border);padding-bottom:4px;margin-bottom:8px;}
::-webkit-scrollbar{width:4px;height:4px;}
::-webkit-scrollbar-track{background:var(--bg);}
::-webkit-scrollbar-thumb{background:var(--border);}

/* HOME */
.home-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;width:100%;max-width:480px;}
.home-card{border:1px solid var(--border);padding:20px;cursor:pointer;transition:all .15s;background:var(--panel);text-align:center;}
.home-card:hover{border-color:var(--gold-dim);background:rgba(201,168,76,.05);}
.home-card h3{font-family:'IM Fell English',serif;color:var(--gold);font-size:18px;margin-bottom:6px;}
.home-card p{font-size:16px;color:var(--ink-dim);line-height:1.5;}
.save-item{background:var(--panel);border:1px solid var(--border);padding:12px;display:flex;justify-content:space-between;align-items:center;width:100%;max-width:500px;}
.save-item .si-name{font-size:19px;color:var(--ink);}
.save-item .si-meta{font-size:14px;color:var(--ink-dim);}

/* UPLOAD */
.upload-zone{width:100%;max-width:560px;border:1px dashed var(--border);padding:30px 20px;text-align:center;cursor:pointer;transition:all .2s;position:relative;}
.upload-zone:hover,.upload-zone.drag{border-color:var(--gold-dim);background:rgba(201,168,76,.04);}
.upload-zone input{position:absolute;inset:0;opacity:0;cursor:pointer;width:100%;height:100%;}
.uz-name{font-size:17px;color:var(--gold);margin-top:8px;}
.rules-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;width:100%;max-width:560px;}
.rc{border:1px solid var(--border);padding:8px 6px;cursor:pointer;text-align:center;transition:all .15s;background:var(--panel);}
.rc:hover{border-color:var(--gold-dim);}
.rc.picked{border-color:var(--gold);background:rgba(201,168,76,.08);}
.rc .rn{font-size:16px;color:var(--gold);font-family:'IM Fell English',serif;margin-bottom:2px;}
.rc .rd{font-size:13px;color:var(--ink-dim);line-height:1.3;}
#proc-bar{width:100%;max-width:560px;background:var(--panel);border:1px solid var(--border);height:5px;}
#proc-fill{height:100%;background:var(--gold-dim);transition:width .4s;width:0%;}

/* MULTIPLAYER */
.mp-box{width:100%;max-width:560px;border:1px solid var(--border);padding:16px;background:var(--panel);display:flex;flex-direction:column;gap:10px;}
.mp-box h3{font-family:'IM Fell English',serif;color:var(--gold);font-size:15px;}
.player-slot{display:flex;align-items:center;gap:10px;padding:7px;border:1px solid var(--border);background:var(--bg);}
.pdot{width:9px;height:9px;border-radius:50%;flex-shrink:0;}
.pdot.on{background:var(--green);}
.pdot.wait{background:var(--gold-dim);animation:pulse 1.2s infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.3;}}
.copy-box{background:var(--bg);border:1px dashed var(--border);padding:8px;font-size:16px;color:var(--ink-dim);cursor:pointer;word-break:break-all;transition:all .15s;}
.copy-box:hover{border-color:var(--gold-dim);color:var(--gold);}

/* CHAR CREATE */
.race-grid,.class-grid-cc{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;width:100%;max-width:700px;}
.sel-card{border:1px solid var(--border);padding:9px 7px;cursor:pointer;transition:all .15s;background:var(--panel);text-align:center;}
.sel-card:hover{border-color:var(--gold-dim);}
.sel-card.picked{border-color:var(--gold);background:rgba(201,168,76,.09);}
.sel-card.disabled{opacity:.3;cursor:not-allowed;}
.sel-card .cn{font-family:'IM Fell English',serif;color:var(--gold);font-size:19px;margin-bottom:3px;}
.sel-card .cd{font-size:13px;color:var(--ink-dim);line-height:1.3;}
.stat-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:7px;width:100%;max-width:700px;}
.stat-box{background:var(--panel);border:1px solid var(--border);padding:9px 4px;text-align:center;}
.stat-box .sn{font-size:13px;color:var(--ink-dim);letter-spacing:1px;}
.stat-box .sv{font-size:19px;color:var(--ink);font-family:'IM Fell English',serif;}
.stat-box .sm{font-size:14px;}
.sm.pos{color:#6a9a6a;}.sm.neg{color:#9a4a4a;}

/* EQUIPMENT PICKER */
.equip-section{width:100%;max-width:700px;border:1px solid var(--border);background:var(--panel);padding:14px;display:flex;flex-direction:column;gap:10px;}
.equip-section h3{font-family:'IM Fell English',serif;color:var(--gold);font-size:15px;}
.equip-category{display:flex;flex-direction:column;gap:6px;}
.equip-cat-title{font-size:14px;letter-spacing:1px;color:var(--ink-dim);text-transform:uppercase;border-bottom:1px solid var(--border);padding-bottom:3px;}
.equip-options{display:flex;flex-wrap:wrap;gap:6px;}
.equip-opt{border:1px solid var(--border);padding:5px 10px;cursor:pointer;font-size:16px;color:var(--ink-dim);transition:all .12s;background:var(--bg);}
.equip-opt:hover{border-color:var(--gold-dim);color:var(--ink);}
.equip-opt.sel{border-color:var(--gold);background:rgba(201,168,76,.1);color:var(--gold);}
.equip-opt.locked{opacity:.5;cursor:default;border-style:dashed;}
.gold-remaining{font-size:17px;color:var(--gold);border:1px solid var(--border);padding:6px 12px;text-align:center;}

/* PARTY STATUS */
.party-wait{width:100%;max-width:700px;border:1px solid var(--border);background:var(--panel);padding:12px;display:flex;flex-direction:column;gap:6px;}
.pready-row{display:flex;align-items:center;gap:10px;font-size:17px;}

/* GAME */
#s-game{padding:0;justify-content:flex-start;align-items:stretch;height:100%;min-height:100vh;overflow:hidden;}
#s-game.active{display:flex;flex-direction:column;height:100vh;}
#s-char.active{display:flex;overflow-y:scroll;}
#topbar{background:var(--panel);border-bottom:1px solid var(--border);padding:5px 14px;display:flex;align-items:center;gap:10px;flex-shrink:0;}
#top-logo{font-family:'IM Fell English',serif;color:var(--gold);font-size:14px;}
#top-mod{color:var(--ink-dim);font-size:14px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
#top-rules{margin-left:auto;font-size:14px;color:var(--ink-dim);border:1px solid var(--border);padding:2px 7px;}
.top-btn{font-family:'Share Tech Mono',monospace;font-size:14px;border:1px solid var(--border);color:var(--ink-dim);background:transparent;padding:2px 8px;cursor:pointer;margin-left:5px;}
.top-btn:hover{border-color:var(--gold-dim);color:var(--gold);}
#middle{display:flex;flex:1;overflow:hidden;min-height:0;}
#left-panel{width:13em;flex-shrink:0;background:var(--panel);border-right:1px solid var(--border);overflow-y:auto;padding:11px;display:flex;flex-direction:column;gap:12px;}
#pc-name-d{font-family:'IM Fell English',serif;font-size:15px;color:var(--ink);}
#pc-rcd{font-size:14px;color:var(--ink-dim);margin-bottom:6px;}
.hp-lbl{display:flex;justify-content:space-between;font-size:14px;color:var(--ink-dim);margin-bottom:3px;}
.hp-bar{height:5px;background:#1a1810;border:1px solid var(--border);}
#hp-fill{height:100%;background:var(--green);transition:width .4s,background .4s;}
.sr{display:flex;justify-content:space-between;font-size:16px;margin-bottom:3px;}
.sr .sl{color:var(--ink-dim);}
#inv-list{list-style:none;}
#inv-list li{font-size:16px;color:var(--ink-dim);padding:2px 0;border-bottom:1px solid #1e1a10;line-height:1.4;}
#inv-list li::before{content:'· ';color:var(--gold-dim);}
.opc{padding:6px;border:1px solid var(--border);background:var(--bg);margin-bottom:5px;}
.opc-name{font-size:16px;margin-bottom:3px;}
.opc-hp{font-size:14px;color:var(--ink-dim);}
.opc-hpbar{height:3px;background:#1a1810;border:1px solid var(--border);margin-top:3px;}
.opc-hpfill{height:100%;transition:width .4s;}
#center-panel{flex:1;display:flex;flex-direction:column;overflow:hidden;}
#scene-bar{background:var(--panel);border-bottom:1px solid var(--border);padding:7px 14px;flex-shrink:0;}
#scene-loc{font-family:'IM Fell English',serif;font-size:15px;color:var(--gold);}
#scene-tag{font-size:14px;color:var(--ink-dim);}
#log{flex:1;overflow-y:auto;padding:12px 14px;display:flex;flex-direction:column;gap:6px;}
.log-system-roll{background:#0d0d08;border:1px solid #3a3020;border-left:3px solid #c9a84c;padding:6px 12px;font-family:'Share Tech Mono',monospace;font-size:13px;color:var(--ink-dim);margin:2px 0;}
.entry{padding:7px 11px;font-size:17px;line-height:1.65;max-width:78%;border-radius:2px;}
.entry.gm{align-self:flex-end;border-right:2px solid var(--gold-dim);background:rgba(201,168,76,.04);text-align:right;}
.entry.combat{align-self:flex-end;border-right:2px solid var(--blood);background:rgba(139,37,37,.05);color:#c08060;text-align:right;}
.entry.roll{align-self:flex-end;border-right:2px solid var(--blue);background:rgba(64,96,160,.05);color:#8090c0;font-style:italic;text-align:right;}
.entry.loot{align-self:flex-end;border-right:2px solid var(--gold-dim);color:var(--gold);text-align:right;}
.entry.player-msg{align-self:flex-start;border-left:2px solid #3a6a3a;background:rgba(58,106,58,.05);}
.entry.system{align-self:center;color:var(--ink-dim);font-size:14px;border:none;padding:2px;background:none;max-width:100%;text-align:center;}
.entry.thinking{align-self:flex-end;color:var(--ink-dim);font-style:italic;border-right:2px solid var(--border);max-width:40%;text-align:right;}
.entry-author{font-size:14px;color:var(--ink-dim);margin-bottom:3px;}
.roll-tag{color:#8090d0;}
#bottom-bar{background:var(--panel);border-top:1px solid var(--border);flex-shrink:0;}
#quick-btns{display:flex;flex-wrap:wrap;gap:5px;padding:6px 10px;border-bottom:1px solid var(--border);min-height:32px;}
.qb{background:transparent;border:1px solid var(--border);color:var(--ink-dim);font-family:'Share Tech Mono',monospace;font-size:14px;padding:3px 8px;cursor:pointer;transition:all .12s;}
.qb:hover{border-color:var(--gold-dim);color:var(--gold);}
#input-row{display:flex;gap:8px;align-items:center;padding:7px 10px;}
#prompt-lbl{color:var(--gold-dim);flex-shrink:0;}
#cmd{flex:1;background:transparent;border:none;border-bottom:1px solid var(--border);color:var(--ink);font-family:'Share Tech Mono',monospace;font-size:19px;outline:none;padding:2px 4px;}
#cmd:focus{border-bottom-color:var(--gold-dim);}
#cmd::placeholder{color:#3a3020;}
#send-btn{background:transparent;border:1px solid var(--gold-dim);color:var(--gold);font-family:'Share Tech Mono',monospace;font-size:16px;padding:4px 12px;cursor:pointer;}
#send-btn:hover{background:rgba(201,168,76,.12);}
#right-panel{width:12em;flex-shrink:0;background:var(--panel);border-left:1px solid var(--border);padding:11px;display:flex;flex-direction:column;gap:12px;overflow-y:auto;}
#quest-list{list-style:none;}
#quest-list li{font-size:14px;color:var(--ink-dim);padding:3px 0;border-bottom:1px solid #1e1a10;line-height:1.4;}
#quest-list li.active{color:#c0a040;}
#quest-list li.done{color:#4a7a4a;text-decoration:line-through;}
#gold-disp{font-family:'IM Fell English',serif;font-size:24px;color:var(--gold);}
.csel-item{background:var(--panel);border:1px solid var(--border);padding:12px 14px;cursor:pointer;transition:all .15s;display:flex;justify-content:space-between;align-items:center;}
.csel-item:hover{border-color:var(--gd);}
.csel-item.sel{border-color:var(--gold);background:rgba(201,168,76,.08);}
.csel-item .ci-name{font-family:'IM Fell English',serif;font-size:15px;color:var(--ink);}
.csel-item .ci-sub{font-size:14px;color:var(--dim);margin-top:2px;line-height:1.5;}
.csel-item .ci-badge{font-size:14px;color:var(--gold);padding:2px 8px;border:1px solid var(--border);}
.stat-mini{background:var(--bg);border:1px solid var(--border);padding:5px 4px;text-align:center;}
.stat-mini .smn{font-size:13px;color:var(--dim);letter-spacing:1px;}
.stat-mini .smv{font-size:14px;color:var(--ink);font-family:'IM Fell English',serif;}
.stat-mini .smm{font-size:14px;}

/* V4 additions */
.roll-result-box {
  border: 1px solid var(--gold);
  background: rgba(180,130,20,0.08);
  padding: 8px 12px;
  margin: 6px 0;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  color: var(--gold);
  border-radius: 3px;
}
.parse-line {
  font-family: 'Share Tech Mono', monospace;
  font-size: 13px;
  color: #7ab8ff;
  letter-spacing: 0.3px;
  padding-bottom: 5px;
  margin-bottom: 5px;
  border-bottom: 1px solid rgba(122,184,255,0.25);
}
.dice-line {
  font-family: 'Share Tech Mono', monospace;
  font-size: 13px;
  color: #c9a84c;
}
.rejection-msg {
  color: #c06060;
  font-style: italic;
  padding: 4px 0;
  border-left: 3px solid #c06060;
  padding-left: 8px;
  margin: 4px 0;
}
#spellbook-panel {
  margin-top: 8px;
  border-top: 1px solid var(--border);
  padding-top: 6px;
}
#spellbook-panel summary {
  cursor: pointer;
  color: var(--gold-dim);
  font-size: 12px;
  letter-spacing: 1px;
  text-transform: uppercase;
  user-select: none;
}
.spell-slot-row { display:flex; gap:4px; align-items:center; margin: 2px 0; }
.spell-slot-pip { width:10px; height:10px; border-radius:50%; background:var(--gold);
                  border:1px solid var(--gold); display:inline-block; }
.spell-slot-pip.used { background:transparent; }
.spell-memorize-btn { font-size:11px; padding:2px 6px; }
.memorize-modal { position:fixed; top:0; left:0; right:0; bottom:0;
  background:rgba(0,0,0,.85); z-index:999;
  display:flex; align-items:center; justify-content:center; }
.memorize-modal-inner { background:var(--panel); border:2px solid var(--gold);
  padding:20px; max-width:560px; width:92%; max-height:80vh; overflow-y:auto; }
.spell-card { border:1px solid var(--border); padding:6px 10px; margin:4px 0;
  cursor:pointer; border-radius:2px; }
.spell-card:hover { border-color:var(--gold); }
.spell-card.selected { border-color:var(--gold); background:rgba(180,130,20,.12); }
.spell-card .sname { font-weight:bold; color:var(--text); }
.spell-card .sdesc { font-size:12px; color:var(--text-dim); margin-top:2px; }
.level-up-modal { position:fixed; top:0; left:0; right:0; bottom:0;
  background:rgba(0,0,0,.88); z-index:1000;
  display:flex; align-items:center; justify-content:center; }
.level-up-inner { background:var(--panel); border:2px solid var(--gold);
  padding:24px; max-width:500px; width:92%; }
.lv-title { font-family:'IM Fell English',serif; font-size:28px;
  color:var(--gold); text-align:center; margin-bottom:12px; }
.lv-change { padding:4px 0; border-bottom:1px solid var(--border); font-size:14px; }
.ability-badge { display:inline-block; background:rgba(180,130,20,.15);
  border:1px solid var(--gold-dim); border-radius:12px; padding:2px 8px;
  font-size:11px; color:var(--gold-dim); margin:2px; cursor:pointer; }
.ability-badge:hover { background:rgba(180,130,20,.28); }
.ability-tooltip { display:none; position:absolute; background:var(--panel);
  border:1px solid var(--gold); padding:8px; max-width:280px; font-size:12px;
  z-index:200; border-radius:3px; }

</style>
</head>
<body>
<div id="s-lobby" class="screen active">
  <div class="title" style="padding-top:.5rem;">D&amp;D Module<br>Adventure Engine</div>
  <div class="sub">Powered by local AI &mdash; no internet required for play.</div>

  <div id="ai-status" style="font-size:19px;padding:12px 18px;border:2px solid #c9a84c;background:#1a1500;width:100%;max-width:440px;text-align:center;line-height:1.8;color:#c9a84c;">&#9654; Checking for Ollama...</div>

  <div class="home-grid" style="margin-top:8px;">
    <div class="home-card" onclick="goToNewGame()">
      <h3>New Game</h3>
      <p>Pick a module, create your character, begin.</p>
    </div>
    <div class="home-card" onclick="goToLoad()">
      <h3> Load Game</h3>
      <p>Resume a saved adventure from where you left off.</p>
    </div>
  </div>

  <div id="load-wrap" style="display:none;width:100%;max-width:500px;flex-direction:column;gap:8px;">
    <div class="lbl">Saved Adventures</div>
    <div id="save-list-el"></div>
    <button class="btn" onclick="document.getElementById('load-wrap').style.display='none'" style="font-size:16px;padding:5px 14px;margin-top:4px;">< Back</button>
  </div>

  <div style="border-top:1px solid var(--border);padding-top:14px;width:100%;max-width:480px;display:flex;flex-direction:column;align-items:center;gap:10px;">
    <div class="sub" style="font-size:16px;">Joining a friend's game? Enter their room code:</div>
    <div class="row" style="justify-content:center;">
      <input class="field" type="text" id="join-code" placeholder="Room code..." maxlength="6" style="width:160px;text-transform:uppercase;" oninput="this.value=this.value.toUpperCase()"/>
      <button class="btn" onclick="joinRoomFromLobby()">Join ></button>
    </div>
  </div>

  <!-- Optional Claude API key -->
  <div style="width:100%;max-width:480px;margin-top:2px;">
    <div style="border-top:1px solid var(--border);padding-top:10px;display:flex;flex-direction:column;align-items:center;gap:6px;">
      <div onclick="toggleApiKey()" style="cursor:pointer;display:flex;align-items:center;gap:8px;">
        <span style="font-size:12px;color:var(--ink-dim);letter-spacing:0.5px;">OPTIONAL: CLAUDE API KEY (BETTER PARSING)</span>
        <span id="api-arrow" style="color:#c9a84c;font-size:11px;">&#9660;</span>
      </div>
      <div id="api-key-box" style="display:none;flex-direction:column;gap:6px;align-items:center;width:100%;max-width:400px;">
        <div style="font-size:11px;color:var(--ink-dim);text-align:center;">Uses Claude Haiku for intent parsing only. Narration stays on Ollama. ~$0.001 per action.</div>
        <div style="display:flex;gap:8px;width:100%;">
          <input class="field" type="password" id="key-inp" placeholder="sk-ant-api03-..." value=""
            style="flex:1;font-size:13px;" oninput="onApiKeyTyped(this.value)"/>
          <button class="btn" onclick="applyApiKey()" style="font-size:13px;padding:4px 14px;">Save</button>
        </div>
        <div id="api-key-status" style="font-size:11px;min-height:14px;"></div>
      </div>
    </div>
  </div>
  <!-- hidden compat elements -->
  <input type="hidden" id="player-name-inp" value=""/>
  <div id="home-welcome" style="display:none;"></div>
</div>
<div id="s-home" class="screen" style="display:none;">
</div>
<div id="s-newgame" class="screen">
  <div class="title">New Adventure</div>
  <div class="sub">Choose a module to play.</div>

  <!-- Module list — primary path -->
  <div class="lbl">1 &mdash; Select Module</div>
  <div id="dndmod-section" style="width:100%;max-width:680px;display:flex;flex-direction:column;gap:6px;">
    <div id="dndmod-list" style="display:flex;flex-direction:column;gap:6px;"></div>
    <div id="dndmod-empty" style="display:none;border:1px solid var(--border);background:var(--panel);padding:16px;text-align:center;">
      <div style="font-size:19px;color:var(--dim);">No modules converted yet.</div>
      <div style="font-size:16px;color:var(--dim);margin-top:6px;">Place a <strong style="color:var(--gold)">.dndmod</strong> file in <code>~/Documents/DnDAdventure/modules/</code> or the same folder as <code>dnd_adventure_v4.py</code>.</div>
    </div>
  </div>


  <div class="lbl">2 &mdash; Rules System</div>
  <div class="rules-grid">
    <div class="rc picked" data-r="OSE" onclick="pickRules(this)"><div class="rn">OSE</div><div class="rd">Old-School Essentials Advanced</div></div>
    <div class="rc" data-r="AD&D 1e" onclick="pickRules(this)"><div class="rn">AD&D 1e</div><div class="rd">Advanced D&D First Edition</div></div>
    <div class="rc" data-r="D&D 5e" onclick="pickRules(this)"><div class="rn">5e</div><div class="rd">D&D Fifth Edition</div></div>
    <div class="rc" data-r="B/X" onclick="pickRules(this)"><div class="rn">B/X</div><div class="rd">Basic/Expert Moldvay/Cook</div></div>
    <div class="rc" data-r="Pathfinder 1e" onclick="pickRules(this)"><div class="rn">PF1e</div><div class="rd">Pathfinder First Edition</div></div>
    <div class="rc" data-r="Call of Cthulhu" onclick="pickRules(this)"><div class="rn">CoC</div><div class="rd">Call of Cthulhu 7e</div></div>
  </div>
  <div class="lbl">3 &mdash; Multiplayer (optional)</div>
  <div class="mp-box">
    <h3>Party Setup</h3>
    <div style="font-size:16px;color:var(--ink-dim);">Solo? Just continue. Want friends? Share the room code below &mdash; they enter it on the main screen.</div>
    <div class="row" style="gap:10px;align-items:center;margin-top:6px;">
      <span style="font-size:16px;color:var(--ink-dim);">Room Code:</span>
      <span id="room-code-disp" style="font-family:'IM Fell English',serif;font-size:26px;color:var(--gold);letter-spacing:6px;">...</span>
      <button onclick="copyRoomCodeNewGame()" style="background:none;border:1px solid var(--border);color:var(--ink-dim);cursor:pointer;padding:2px 10px;font-size:14px;">Copy</button>
    </div>
    <div id="room-share-wrap" style="flex-direction:column;gap:8px;">
      <div id="player-slots-list" style="display:flex;flex-direction:column;gap:5px;"></div>
      <div id="ngrok-info" style="font-size:14px;color:var(--ink-dim);line-height:1.6;">
        <span id="ngrok-status-txt">Checking internet access...</span>
      </div>
    </div>
  </div>
  <div id="proc-wrap" style="display:none;width:100%;max-width:560px;flex-direction:column;gap:5px;">
    <div id="proc-msg" style="font-size:16px;color:var(--ink-dim);font-style:italic;"></div>
    <div id="proc-bar"><div id="proc-fill"></div></div>
  </div>
  <div style="display:flex;gap:10px;">
    <button class="btn" onclick="show('s-lobby')" style="font-size:16px;padding:6px 14px;">< Back</button>
    <button class="btn" id="next-btn" onclick="proceedToCharCreate()" disabled style="opacity:0.4;">> Create Character</button>
  </div>
</div>
<div id="s-char" class="screen">
  <div class="title">Create Your Character</div>
  <div id="char-module-lbl" style="font-family:'IM Fell English',serif;font-size:19px;color:var(--gold-dim);font-style:italic;"></div>
  <div class="box" style="width:100%;max-width:520px;">
    <div class="lbl" style="align-self:flex-start;">Your Character Name <span style="color:var(--ink-dim);font-size:14px;">(this is also how others see you)</span></div>
    <input class="field" type="text" id="char-name-inp" placeholder="Enter your character's name..." maxlength="22" style="width:100%;font-family:'IM Fell English',serif;font-size:19px;"/>
  </div>
  <div id="mp-char-note" style="display:none;font-size:16px;color:var(--ink-dim);text-align:center;max-width:500px;line-height:1.6;border:1px solid var(--border);padding:10px;background:var(--panel);">
    All players create characters simultaneously. The host clicks "Begin Adventure" once everyone is ready.
  </div>

  <div class="lbl">Race</div>
  <div class="race-grid" id="race-grid"></div>
  <div id="race-specials" style="font-size:14px;color:var(--ink-dim);max-width:700px;min-height:16px;font-style:italic;"></div>

  <div class="lbl">Class</div>
  <div class="class-grid-cc" id="class-grid"></div>
  <div id="class-desc" style="font-size:14px;color:var(--ink-dim);max-width:700px;min-height:16px;font-style:italic;"></div>

  <div style="display:flex;justify-content:space-between;align-items:center;width:100%;max-width:700px;">
    <span style="font-size:16px;color:var(--ink-dim)">Ability scores &mdash; 3d6 in order (OSE core rules):</span>
    <button class="btn" onclick="reroll()" style="padding:5px 14px;font-size:16px;"> Reroll</button>
  </div>
  <div class="stat-grid" id="stat-grid"></div>

  <!-- EQUIPMENT SELECTION -->
  <div class="lbl">Starting Equipment</div>
  <div class="equip-section" id="equip-section">
    <h3>Choose Your Gear</h3>
    <div style="font-size:16px;color:var(--ink-dim);">Select one option from each category. Your starting gold buys additional items.</div>
    <div id="equip-categories"></div>
    <div class="gold-remaining" id="gold-remaining">Starting Gold: 0 gp</div>
    <div id="extra-equip" style="display:flex;flex-direction:column;gap:8px;">
      <div class="equip-cat-title">Additional Purchases (click to add/remove)</div>
      <div class="equip-options" id="extra-items-list"></div>
    </div>
    <div style="font-size:14px;color:var(--ink-dim);">Final inventory: <span id="final-inv-preview" style="color:var(--ink)"></span></div>
  </div>

  <div class="row" style="justify-content:center;">
  </div>

  <div id="party-status-wrap" class="party-wait" style="display:none;">
    <div class="lbl">Party Status</div>
    <div id="party-status-rows"></div>
  </div>

  <div style="display:flex;gap:10px;">
    <button class="btn" id="ready-btn" onclick="markReady()">Ready</button>
    <button class="btn" id="begin-btn" style="display:none;" onclick="beginAdventure()">Begin Adventure ></button>
  </div>
</div>
<div id="s-game" class="screen">
  <div id="topbar">
    <span id="top-logo" style="font-family:'IM Fell English',serif;color:var(--gold);font-size:14px;"></span>
    <span id="top-mod" style="color:var(--ink-dim);font-size:14px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"></span>
    <span id="top-rules" style="font-size:14px;color:var(--ink-dim);border:1px solid var(--border);padding:2px 7px;"></span>
    <span style="flex:1;"></span>
    <span id="top-room-wrap" style="display:none;align-items:center;gap:5px;border:1px solid var(--border);padding:2px 10px;background:var(--panel);">
      <span style="font-size:13px;color:var(--dim);letter-spacing:1px;text-transform:uppercase;">Room</span>
      <span id="top-room" style="font-family:'IM Fell English',serif;font-size:15px;color:var(--gold);letter-spacing:4px;"></span>
      <span id="top-room-copy" onclick="copyRoomCode()" style="font-size:13px;color:var(--dim);cursor:pointer;padding-left:4px;" title="Click to copy"></span>
    </span>
    <span id="top-ai-indicator" style="font-size:16px;padding:3px 10px;border:1px solid #3a3020;background:var(--panel);color:var(--ink-dim);">• AI: checking...</span>
    <button class="top-btn" onclick="saveGame()">Save</button>
  </div>
  <div id="middle">
    <div id="left-panel">
      <div>
        <div class="pane-title">Your Character</div>
        <div id="pc-name-d"></div>
        <div id="pc-rcd"></div>
        <div class="hp-lbl"><span>HP</span><span id="hp-txt"></span></div>
        <div class="hp-bar"><div id="hp-fill"></div></div>
        <br>
        <div class="sr"><span class="sl">AC</span><span id="s-ac"></span></div>
        <div class="sr"><span class="sl">STR</span><span id="s-str"></span></div>
        <div class="sr"><span class="sl">DEX</span><span id="s-dex"></span></div>
        <div class="sr"><span class="sl">CON</span><span id="s-con"></span></div>
        <div class="sr"><span class="sl">INT</span><span id="s-int"></span></div>
        <div class="sr"><span class="sl">WIS</span><span id="s-wis"></span></div>
        <div class="sr"><span class="sl">CHA</span><span id="s-cha"></span></div>
        <div class="sr"><span class="sl">Gold</span><span id="s-gp"></span></div>
      </div>
      <div id="status-panel" style="margin-top:6px;">
        <div class="pane-title">Status</div>
        <div id="status-hunger" style="font-size:14px;color:var(--dim);padding:2px 0;">Hunger: <span id="hunger-bar" style="color:var(--ink);">Fed</span></div>
        <div id="status-dungeon-rest" style="font-size:14px;color:var(--dim);padding:2px 0;display:none;">Rest: <span id="dungeon-rest-bar" style="color:var(--ink);">—</span></div>
        <div id="status-light" style="font-size:14px;color:var(--dim);padding:2px 0;display:none;">Light: <span id="light-status">—</span></div>
        <div id="active-effects" style="display:flex;flex-direction:column;gap:2px;margin-top:2px;"></div>
      </div>
      <div style="display:none;">
      </div>
      <div>
        <button onclick="toggleInventory()" style="background:none;border:1px solid var(--border);color:var(--ink-dim);cursor:pointer;padding:3px 10px;font-size:14px;width:100%;text-align:left;margin-top:4px;">Inventory <span id="inv-toggle-arrow"></span></button>
        <div id="inv-panel" style="display:none;margin-top:4px;">
          <ul id="inv-list"></ul>
        </div>

<details id="spellbook-panel">
  <summary>&#9733; Spellbook &amp; Spells</summary>
  <div id="sb-slots" style="margin:6px 0 4px;font-size:12px;color:var(--text-dim);">No spells memorized.</div>
  <div id="sb-memorized" style="font-size:12px;"></div>
  <button class="btn spell-memorize-btn" onclick="openMemorize()" 
    id="memorize-btn" style="margin-top:4px;display:none;">Memorize Spells</button>
</details>

      </div>
      <div id="party-panel" style="display:none;">
        <div class="pane-title">Party</div>
        <div id="other-pcs"></div>
      </div>
    </div>
    <div id="center-panel">
      <div id="scene-bar">
        <div id="scene-loc">...</div>
        <div id="scene-tag"></div>
      </div>
      <div id="log"></div>
      <div id="bottom-bar">
        <div id="quick-btns"></div>
        <div id="input-row">
          <span id="prompt-lbl">&gt;</span>
          <input type="text" id="cmd" placeholder="What do you do? (use /GM to ask rules, /Name to talk to a player)" autocomplete="off"/>
          <button id="send-btn" onclick="send()">ENTER</button>
        </div>
      </div>
    </div>
    <div id="right-panel">
      <div>
        <div class="pane-title">Quests</div>
        <ul id="quest-list"><li style="font-size:14px;color:var(--ink-dim)">None yet</li></ul>
      </div>

<div id="ability-panel" style="margin-top:8px;border-top:1px solid var(--border);padding-top:6px;display:none;">
  <div style="font-size:11px;color:var(--gold-dim);letter-spacing:1px;text-transform:uppercase;margin-bottom:4px;">
    Class Abilities</div>
  <div id="ability-list"></div>
</div>


      <div id="memory-panel" style="display:none;">
        <div class="pane-title">Memory</div>
        <div id="mem-turn" style="font-size:14px;color:var(--dim);">Turn 0</div>
        <div id="mem-summary" style="font-size:14px;color:var(--dim);margin-top:3px;line-height:1.4;font-style:italic;max-height:60px;overflow:hidden;cursor:help;"></div>
        <div id="mem-facts" style="font-size:14px;color:#6a9a6a;margin-top:4px;"></div>
        <div id="mem-npcs" style="font-size:14px;color:var(--dim);margin-top:3px;line-height:1.4;"></div>
      </div>

    </div>
  </div>
</div>
<script src="/game.js?v=1778942309"></script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION N: STARTUP
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    import signal, webbrowser

    print(f"\n╔══════════════════════════════════════════════════════╗")
    print(f"║  D&D Module Adventure Engine  V{VERSION}               ║")
    print(f"║  OSE Advanced Fantasy Rules Engine                    ║")
    print(f"║  Layers: Validate → Parse → Resolve → Narrate         ║")
    print(f"╠══════════════════════════════════════════════════════╣")

    # Start Ollama check
    t = threading.Thread(target=check_ollama, daemon=True)
    t.start()
    t.join(timeout=4)

    if _ollama_available:
        print(f"║  Ollama: ✓  Model: {_ollama_model:<30}  ║")
    else:
        print(f"║  Ollama: ✗  (Claude API narration will be used)       ║")

    # Start ngrok
    ngrok_t = threading.Thread(target=start_ngrok, daemon=True)
    ngrok_t.start()

    print(f"╠══════════════════════════════════════════════════════╣")
    print(f"║  Server: http://localhost:{PORT}                        ║")
    print(f"║  Saves:   {str(SAVES_DIR):<45}  ║")
    print(f"║  Modules: {str(MODULES_DIR):<45}  ║")
    # Auto-copy .dndmod files from script directory to modules dir
    import glob as _glob
    script_dir = pathlib.Path(__file__).parent
    for _f in script_dir.glob("*.dndmod"):
        dest = MODULES_DIR / _f.name
        if not dest.exists():
            import shutil as _shutil
            _shutil.copy2(_f, dest)
            print(f"║  Auto-copied module: {_f.name:<33}  ║")
    print(f"╚══════════════════════════════════════════════════════╝\n")

    server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)

    def shutdown(sig, frame):
        print("\nShutting down...")
        stop_ngrok()
        threading.Thread(target=server.shutdown, daemon=True).start()
        import sys; sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    try:
        signal.signal(signal.SIGTERM, shutdown)
    except: pass

    threading.Timer(0.8, lambda: webbrowser.open(f'http://localhost:{PORT}')).start()

    print(f"Serving on http://localhost:{PORT} -- press Ctrl+C to quit\n")
    server.serve_forever()

if __name__ == '__main__':
    main()
