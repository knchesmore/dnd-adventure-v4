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
VERSION = "4.1"

# =============================================================================
# AUTO-UPDATE SYSTEM
# Checks GitHub for a newer version. If running as a .py script, downloads
# the new .py and rebuilds the .exe using PyInstaller, then restarts.
# If running as a .exe, downloads new .py, rebuilds exe, swaps it, restarts.
# Update URL: https://raw.githubusercontent.com/knchesmore/dnd-adventure-v4/main/dnd-adventure-v4.py
# =============================================================================
UPDATE_URL = "https://raw.githubusercontent.com/knchesmore/dnd-adventure-v4/main/dnd-adventure-v4.py"

def _check_and_update():
    import urllib.request, sys, subprocess, re as _re, os, pathlib as _pl, shutil, tempfile

    print("[Updater] Checking for updates...")

    # Fetch remote source
    try:
        req = urllib.request.Request(
            UPDATE_URL,
            headers={"User-Agent": "dnd-adventure-v4-updater/1.0", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=10) as r:
            remote_src = r.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"[Updater] Cannot reach GitHub ({e}) -- running local version.")
        return

    # Compare versions
    m_r = _re.search(r'^VERSION\s*=\s*"([^"]+)"', remote_src, _re.MULTILINE)
    rv = m_r.group(1) if m_r else "0"
    # When frozen as exe, __file__ is in a temp dir -- use the VERSION constant directly
    frozen = getattr(sys, "frozen", False)
    if frozen:
        lv = VERSION
    else:
        try:
            m_l = _re.search(r'^VERSION\s*=\s*"([^"]+)"', open(__file__, errors="replace").read(), _re.MULTILINE)
            lv = m_l.group(1) if m_l else "0"
        except Exception:
            lv = VERSION

    def _vt(v):
        try:    return tuple(int(x) for x in v.split("."))
        except: return (0,)

    if _vt(rv) <= _vt(lv):
        print(f"[Updater] Up to date (v{lv}).")
        return

    print(f"[Updater] New version v{rv} found (current: v{lv}). Updating...")

    # Determine if we are running as a frozen exe (PyInstaller) or plain .py
    frozen = getattr(sys, "frozen", False)

    if frozen:
        # Running as .exe
        exe_path = _pl.Path(sys.executable).resolve()
        # Canonical location for the exe
        home_dir  = _pl.Path.home() / 'Documents' / 'DnDAdventure'
        home_dir.mkdir(parents=True, exist_ok=True)
        canon_exe = home_dir / exe_path.name
        # If exe isn't already in DnDAdventure, target that location
        if exe_path.parent != home_dir:
            exe_path = canon_exe
        # Write new .py to a temp file
        tmp_dir  = _pl.Path(tempfile.mkdtemp())
        new_py   = tmp_dir / "dnd_adventure_v4.py"
        new_exe  = tmp_dir / "dnd_adventure_v4.exe"
        new_py.write_text(remote_src, encoding="utf-8")
        print(f"[Updater] Building new exe (this takes ~30 seconds)...")
        result = subprocess.run(
            ["pyinstaller", "--onefile", "--distpath", str(tmp_dir),
             "--workpath", str(tmp_dir / "build"),
             "--specpath", str(tmp_dir),
             "--name", "dnd_adventure_v4",
             str(new_py)],
            capture_output=True, text=True)
        if result.returncode != 0 or not new_exe.exists():
            print("[Updater] PyInstaller failed:", result.stdout[:200], result.stderr[:200])
            shutil.rmtree(tmp_dir, ignore_errors=True)
            return
        # Write a small launcher bat that swaps exe and restarts
        bat = tmp_dir / "_update.bat"
        bat_lines = [
            "@echo off",
            "timeout /t 2 /nobreak >nul",
            'copy /y "' + str(new_exe) + '" "' + str(exe_path) + '"',
            'start "" "' + str(exe_path) + '"',
            "del \"%~f0\"",
        ]
        bat.write_text("\n".join(bat_lines) + "\n", encoding="utf-8")
        print(f"[Updater] Launching update bat, restarting...")
        subprocess.Popen(["cmd", "/c", str(bat)], creationflags=0x00000008)  # DETACHED
        sys.exit(0)

    else:
        # Running as plain .py script
        script_path = _pl.Path(__file__).resolve()
        # Save new .py to DnDAdventure folder (canonical location)
        home_dir = _pl.Path.home() / 'Documents' / 'DnDAdventure'
        home_dir.mkdir(parents=True, exist_ok=True)
        canonical_py = home_dir / 'dnd_adventure_v4.py'
        canonical_py.write_text(remote_src, encoding="utf-8")
        # Also overwrite the running script if it's somewhere else
        if script_path != canonical_py:
            try:
                script_path.write_text(remote_src, encoding="utf-8")
            except Exception:
                pass
        print(f"[Updater] Script updated to v{rv}.")

        # Try to rebuild exe if pyinstaller is available
        exe_name    = script_path.stem + ".exe"
        exe_target  = script_path.parent / exe_name
        pi_result = shutil.which("pyinstaller")
        if pi_result:
            print(f"[Updater] Rebuilding exe with PyInstaller...")
            tmp_dir = _pl.Path(tempfile.mkdtemp())
            result  = subprocess.run(
                ["pyinstaller", "--onefile",
                 "--distpath", str(home_dir),
                 "--workpath", str(tmp_dir / "build"),
                 "--specpath", str(tmp_dir),
                 "--name", script_path.stem,
                 str(script_path)],
                capture_output=True, text=True)
            shutil.rmtree(tmp_dir, ignore_errors=True)
            if result.returncode == 0 and exe_target.exists():
                print(f"[Updater] Exe rebuilt successfully: {exe_target}")
            else:
                print(f"[Updater] PyInstaller rebuild failed (script is still updated).")
        else:
            print(f"[Updater] PyInstaller not found -- script updated but exe not rebuilt.")

        # Restart the script
        print(f"[Updater] Restarting...")
        os.execv(sys.executable, [sys.executable, str(script_path)] + sys.argv[1:])


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

CLOSED WORLD -- HIGHEST PRIORITY RULE:
You may ONLY describe what is explicitly written in the MODULE CONTEXT below.
NEVER invent new creatures, NPCs, locations, taverns, cities, or plot events.
The world contains ONLY what the module describes. Nothing else exists.
If the module says there is one goblin, there is ONE goblin. No serpents, no other creatures.

NARRATION RULES:
- Write 2-4 paragraphs of vivid present-tense prose
- Do NOT speak for or control the player character
- Do NOT re-roll or change any dice results -- narrate them exactly as given
- If dice say MISS: the attack goes wide -- it does not land
- If dice say HIT: the blow lands, dealing exactly the damage shown
- No headers, bullet points, or bold text
- End with the current scene state so the player knows what to do next

MODULE CONTEXT:
{module_context}

CURRENT LOCATION: {location}
IN COMBAT: {in_combat}
ACTIVE ENEMIES: {enemies}
NPCS PRESENT: {npcs}
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

    # ── Layer 3: Mechanical Resolution ───────────────────────────────────────
    # -- Build parse display line from action chain --------------------------
    def _fmt_parse(text_raw, actions, pc_name):
        if not actions:
            return None
        a   = actions[0]
        t   = a.get("type", "other")
        sub = "[" + pc_name + "]"
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
        try:
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(body)))
            self.send_header("Access-Control-Allow-Origin","*")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            pass  # Client closed connection

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

JS_BUNDLE_B64 = "LyogdjE3Nzg5MDYxMTkgKi8KY29uc3QgT1NFX01FQ0hBTklDU19SVUxFU19KUyA9IGBPRkZJQ0lBTCBPU0UgQURWQU5DRUQgRkFOVEFTWSBNRUNIQU5JQ1MgLS0gVVNFIE9OTFkgVEhFU0U6CgpST0xMUyBBUkUgSEFORExFRCBCWSBUSEUgU0VSVkVSLiBXaGVuIHlvdSBzZWUgW1JvbGwgcmVzdWx0XSBpbiBjb250ZXh0LCByZXBvcnQgaXQgZmFpdGhmdWxseS4gRG8gTk9UIHJlLXJvbGwgb3Igb3ZlcnJpZGUuCgpPRkZJQ0lBTCBNRUNIQU5JQ1MgT05MWToKLSBBdHRhY2sgcm9sbHM6IGQyMCB2cyBUSEFDMC4gU1RSIG1vZCB0byBtZWxlZSBoaXQgJiBkYW1hZ2UuIERFWCBtb2QgdG8gcmFuZ2VkIGhpdCBvbmx5LiBNaW4gMSBkYW1hZ2Ugb24gYSBoaXQuCi0gU2F2aW5nIHRocm93czogT05MWSB0aGVzZSA1IGNhdGVnb3JpZXMgLS0gRGVhdGgvUG9pc29uLCBXYW5kcywgUGFyYWx5c2lzL1BldHJpZnksIEJyZWF0aCBBdHRhY2tzLCBTcGVsbHMvUm9kcy9TdGF2ZXMuCi0gVGhpZWYgc2tpbGxzIChkJSk6IE9wZW4gTG9ja3MsIEZpbmQgVHJhcHMsIFJlbW92ZSBUcmFwcywgQ2xpbWIgV2FsbHMsIE1vdmUgU2lsZW50bHksIEhpZGUgaW4gU2hhZG93cywgUGljayBQb2NrZXRzLiBPTkxZIGZvciBUaGllZi9BY3JvYmF0L0Fzc2Fzc2luIGNsYXNzZXMuCi0gSW5pdGlhdGl2ZTogZDYgcGVyIHNpZGUuIFRpZXMgZ28gdG8gcGxheWVycy4KLSBNb3JhbGU6IDJkNiB2cyBtb3JhbGUgc2NvcmUgd2hlbiBtb25zdGVyIGlzIHJlZHVjZWQgdG8gaGFsZiBIUCBvciBsZWFkZXIgZGllcy4KLSBSZWFjdGlvbiByb2xsczogMmQ2ICsgQ0hBIG1vZGlmaWVyIG9uIGZpcnN0IE5QQyBlbmNvdW50ZXIuCi0gU2VhcmNoaW5nOiBkNj0xIHN1Y2Nlc3MgKGQ2PTEtMiBmb3IgRWx2ZXMvSGFsZi1FbHZlcykuIEFOWSBjaGFyYWN0ZXIgY2FuIHNlYXJjaC4gVGFrZXMgMSB0dXJuLgotIEhlYXIgTm9pc2U6IGQ2PTEtMiBzdWNjZXNzIGZvciBub24tdGhpZXZlcy4gVGhpZXZlcyB1c2Ugc2tpbGwgdGFibGUuCi0gRm9yY2UgRG9vcjogZDY9MS0yIHN1Y2Nlc3MuCi0gQWJpbGl0eSBjaGVja3MgKG9wdGlvbmFsKTogZDIwIHVuZGVyIGFiaWxpdHkgc2NvcmUgZm9yIHVuY2VydGFpbiB0YXNrcy4KCkFCU09MVVRFTFkgRk9SQklEREVOIC0tIE5FVkVSIFNBWSBPUiBVU0U6Ci0gIk1ha2UgYSBQZXJjZXB0aW9uIGNoZWNrIiAobm90IGluIE9TRSAtLSB1c2Ugc2VhcmNoaW5nIHJ1bGVzKQotICJSb2xsIFN0ZWFsdGgiIChub3QgaW4gT1NFIC0tIHVzZSBIaWRlIGluIFNoYWRvd3Mgb3Igc3VycHJpc2UpCi0gIlJvbGwgSW5zaWdodC9BdGhsZXRpY3MvSW52ZXN0aWdhdGlvbi9BY3JvYmF0aWNzIiAoNWUgc2tpbGxzLCBub3QgaW4gT1NFKQotIFByb2ZpY2llbmN5IGJvbnVzLCBBZHZhbnRhZ2UsIERpc2FkdmFudGFnZSwgQ29uY2VudHJhdGlvbiwgQm9udXMgYWN0aW9ucyAoYWxsIDVlKQotICJSb2xsIERDIFgiIC0tIE9TRSB1c2VzIHRhcmdldCBudW1iZXJzIG5vdCBEQ3MKLSBBbnkgc2tpbGwgY2hlY2sgYnkgYSBub24tdGhpZWYgZm9yIHRhc2tzIG9ubHkgdGhpZXZlcyBjYW4gcGVyZm9ybSAocGljayBsb2NrcywgZmluZCB0cmFwcykKSWYgeW91IGFyZSB1bnN1cmUgd2hldGhlciBhIG1lY2hhbmljIGV4aXN0cyBpbiBPU0U6IGl0IHByb2JhYmx5IGRvZXNuJ3QuIFVzZSByZWZlcmVlIGp1ZGdtZW50IGluc3RlYWQuYDsKCmNvbnN0IFJVTEVTX1RFWFQgPSB7CiAgT1NFOmBSVUxFUzogT2xkLVNjaG9vbCBFc3NlbnRpYWxzIEFkdmFuY2VkIEZhbnRhc3kKLSBBdHRhY2s6IGQyMCArIFNUUiBtb2QgKG1lbGVlKSBvciBERVggbW9kIChyYW5nZWQpLiBGaWdodGVyICsxIHRvIGhpdC4gSGl0IGlmIHJlc3VsdCBtZWV0cy9iZWF0cyB0YXJnZXQgQUMuCi0gRGFtYWdlOiB3ZWFwb24gZGllICsgU1RSIG1vZCAobWVsZWUgb25seSkuIE5hdHVyYWwgMjAgPSBtYXhpbXVtIGRhbWFnZS4KLSBTYXZpbmcgdGhyb3dzIHZhcnkgYnkgY2xhc3MuIEZpZ2h0ZXI6IERlYXRoIDEyLCBXYW5kcyAxMywgUGFyYWx5c2lzIDE0LCBCcmVhdGggMTUsIFNwZWxscyAxNi4KLSBUaGllZiBza2lsbHMgKGQxMDApOiBGaW5kIFRyYXBzIDI1LCBPcGVuIExvY2tzIDI1LCBNb3ZlIFNpbGVudCAzMCwgSGlkZSBpbiBTaGFkb3dzIDIwLCBCYWNrc3RhYiDDlzIgZGFtYWdlIChtdXN0IGJlIGhpZGRlbiBmaXJzdCkuCi0gTWFnaWMtVXNlcjogMSBzcGVsbCBzbG90L2RheSBhdCBsZXZlbCAxLiBTbGVlcCA9IDJkOCBIRCBjcmVhdHVyZXMgc2xlZXAsIG5vIHNhdmUuIE1hZ2ljIE1pc3NpbGUgPSAxZDYrMSwgYXV0by1oaXRzLgotIENsZXJpYzogVHVybiBVbmRlYWQgMmQ2IHZzIHVuZGVhZCBIRCB0b3RhbC4gQ3VyZSBMaWdodCBXb3VuZHMgPSAxZDYrMSBIUC4gMSBzcGVsbC9kYXkgYXQgbGV2ZWwgMS4KLSBNb3JhbGU6IE1vbnN0ZXJzIGNoZWNrIDJkNiB3aGVuIHJlZHVjZWQgdG8gaGFsZiBIUCBvciBsZWFkZXIgZGllcy4KLSBSZXN0OiBSZWNvdmVyIDEgSFAgcGVyIGZ1bGwgbmlnaHQncyByZXN0LiBObyBoZWFsaW5nIHdpdGhvdXQgcmVzdCBvciBtYWdpYy5gLAogICdBRCZEIDFlJzpgUlVMRVM6IEFkdmFuY2VkIEQmRCAxc3QgRWRpdGlvbiBUSEFDMCBzeXN0ZW0uIEZpZ2h0ZXIgVEhBQzAgMjAsIHJvbGwgZDIwLCBzdWJ0cmFjdCBmcm9tIFRIQUMwID0gQUMgaGl0LiBXZWFwb24gc3BlZWQgZmFjdG9ycyBhcHBseS4gU2F2aW5nIHRocm93czogRGVhdGgsIFBldHJpZmljYXRpb24sIFJvZHMvU3RhdmVzLCBCcmVhdGgsIFNwZWxscy4gVmFuY2lhbiBzcGVsbGNhc3RpbmcuYCwKICAnRCZEIDVlJzpgUlVMRVM6IEQmRCA1ZS4gQXR0YWNrOiBkMjAgKyBhYmlsaXR5IG1vZCArIHByb2ZpY2llbmN5IGJvbnVzICgrMikgdnMgQUMuIEFkdmFudGFnZS9kaXNhZHZhbnRhZ2U6IHJvbGwgMmQyMC4gRGVhdGggc2F2ZXM6IDMgc3VjY2Vzc2VzIG9yIGZhaWx1cmVzLiBTaG9ydCByZXN0OiBzcGVuZCBIaXQgRGljZS4gTG9uZyByZXN0OiBmdWxsIHJlY292ZXJ5LmAsCiAgJ0IvWCc6YFJVTEVTOiBCL1ggRCZELiBBdHRhY2sgbWF0cml4IGJ5IGNsYXNzL2xldmVsLiBTYXZpbmcgdGhyb3dzOiBEZWF0aCwgV2FuZHMsIFBhcmFseXNpcywgQnJlYXRoLCBTcGVsbHMuIE1vcmFsZSAyZDYuIEZhc3QgYW5kIGRlYWRseS5gLAogICdQYXRoZmluZGVyIDFlJzpgUlVMRVM6IFBhdGhmaW5kZXIgMWUuIGQyMCArIEJBQiArIG1vZC4gQ01CL0NNRCBmb3IgbWFuZXV2ZXJzLiBGb3J0aXR1ZGUvUmVmbGV4L1dpbGwgc2F2ZXMuIEZ1bGwgYWN0aW9uIGVjb25vbXkuYCwKICAnQ2FsbCBvZiBDdGh1bGh1JzpgUlVMRVM6IENvQyA3ZS4gZDEwMCB1bmRlciBza2lsbCBmb3Igc3VjY2Vzcy4gSGFsZiA9IEhhcmQsIGZpZnRoID0gRXh0cmVtZS4gU2FuaXR5IHBvb2wuIENvbWJhdCBpcyBsZXRoYWwgLS0gYXZvaWQgaXQuIEludmVzdGlnYXRpb24gaXMgY29yZSBnYW1lcGxheS5gLAp9OwoKY29uc3QgQkFTRV9VUkwgPSAnaHR0cDovL2xvY2FsaG9zdDo4MDgwJzsKbGV0IHBsYXllck5hbWUgPSAnJzsKbGV0IGFwaUtleSA9ICcnOwpsZXQgaXNIb3N0ID0gZmFsc2U7CmxldCByb29tQ29kZSA9ICcnOwpsZXQgaXNNdWx0aXBsYXllciA9IGZhbHNlOwpsZXQgbW9kdWxlVGV4dCA9ICcnOwpsZXQgbW9kdWxlTmFtZSA9ICcnOwpsZXQgY2hvc2VuUnVsZXMgPSAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwpsZXQgY2hvc2VuUmFjZSAgPSAnSHVtYW4nOwpsZXQgY2hvc2VuQ2xhc3MgPSAnRmlnaHRlcic7CmxldCByb2xsZWRTdGF0cyAgPSB7fTsKbGV0IHN0YXJ0aW5nR29sZCA9IDA7CmxldCBzZWxlY3RlZEVxdWlwID0ge307CmxldCBleHRyYUl0ZW1zICAgPSBbXTsKbGV0IGdvbGRTcGVudCAgICA9IDA7CmNvbnN0IHNlbGVjdGVkRXF1aXBJdGVtcyA9IG5ldyBTZXQoKTsgIC8vIHRyYWNrcyB0b2dnbGVkIGV4dHJhIGVxdWlwbWVudApsZXQgcGMgPSB7fTsKbGV0IHBhcnR5UENzID0ge307CmxldCBoaXN0b3J5ICA9IFtdOwpsZXQgYnVzeSAgICAgPSBmYWxzZTsKbGV0IHN5c3RlbVByb21wdCA9ICcnOwpsZXQgcG9sbFRpbWVyICA9IG51bGw7CmxldCBsYXN0U2VxICAgID0gMDsKbGV0IHVwbG9hZGVkRmlsZSA9IG51bGw7CmxldCBtZW1vcnlTdW1tYXJ5ICAgPSAnJzsKbGV0IHdvcmxkU3RhdGUgPSB7IG5wY3NfbWV0Ont9LCBsb2NhdGlvbnNfdmlzaXRlZDp7fSwgaXRlbXNfZm91bmQ6W10sIHBsb3RfcG9pbnRzOltdLAogICAgICAgICAgICAgICAgICAgIGRvb3JzX29wZW5lZDpbXSwgdHJhcHNfc3BydW5nOltdLCBtb25zdGVyc19raWxsZWQ6W10sIHF1ZXN0c19hY3RpdmU6W10sIHdvcmxkX2NoYW5nZXM6W10gfTsKbGV0IGdtQnJpZWZpbmcgID0gJyc7CmxldCBucGNLbm93bGVkZ2VNYXAgPSB7fTsKbGV0IG5wY1Byb2ZpbGVzID0ge307CmxldCBsb2NhdGlvbkF0bW9zcGhlcmUgPSB7fTsKbGV0IGN1cnJlbnRBdG1vc3BoZXJlICA9ICcnOwpsZXQgc2Vzc2lvblRvbmUgPSAnZXhwbG9yYXRvcnknOwpsZXQgcGlubmVkRmFjdHMgID0gW107CmxldCB0dXJuQ291bnQgICAgPSAwOwpjb25zdCBTVU1NQVJZX0VWRVJZX05fVFVSTlMgPSA4Owpjb25zdCBNQVhfUElOTkVEX0ZBQ1RTID0gMjA7CmNvbnN0IE1BWF9ISVNUT1JZX0JFRk9SRV9TVU1NQVJZID0gMTY7CmNvbnN0IEJBTk5FRF9QSFJBU0VTX1BPT0wgPSBbCiAgJ1RoZSBhaXIgaXMgaGVhdnkgd2l0aCcsJ1lvdSBub3RpY2UnLCdTdWRkZW5seScsJ0FzIHlvdSBlbnRlcicsJ1RoZSBzbWVsbCBvZicsCiAgJ1lvdSBjYW4gc2VlJywnSXQgYmVjb21lcyBjbGVhcicsJ1lvdSByZWFsaXplJywnV2l0aG91dCB3YXJuaW5nJywnWW91IGZpbmQgeW91cnNlbGYnLAogICdZb3Ugb2JzZXJ2ZScsJ0FzIHlvdSBhcHByb2FjaCcsJ0FzIHlvdSBzdGVwJywnVGhlIGF0bW9zcGhlcmUgaXMnLCdJbmRlZWQnLAogICdDZXJ0YWlubHknLCdDbGVhcmx5JywnT2J2aW91c2x5JywnUXVpY2tseScsJ1NlZW1pbmdseScsCl07CmxldCBiYW5uZWRQaHJhc2VzID0gW107CmxldCBwYWNpbmdIaXN0b3J5ID0gW107CmxldCBjdXJyZW50UGFjaW5nUGhhc2UgPSAnb3BlbmluZyc7CmxldCB0dXJuc1NpbmNlTGFzdENvbWJhdCA9IDA7CmxldCB0dXJuc1NpbmNlTGFzdFJlc3QgICA9IDA7CmxldCBjb25zZXF1ZW5jZXMgPSBbXTsKbGV0IHBlbmRpbmdDb25zZXF1ZW5jZXMgID0gW107CmxldCBkdW5nZW9uVHVybnMgPSAwOwpsZXQgdG9yY2hUdXJuc0xlZnQgPSA2OwpsZXQgaGFzTGFudGVybiA9IGZhbHNlOwpsZXQgbGFudGVybk9pbEZsYXNrc0xlZnQgPSAwOwpsZXQgdG9yY2hMaXQgPSBmYWxzZTsKbGV0IHRvcmNoZXNDYXJyaWVkID0gMDsKbGV0IGxhbnRlcm5MaXQgPSBmYWxzZTsKbGV0IHRvcmNoRXZlclVzZWQgPSBmYWxzZTsKbGV0IHJhdGlvbnNMZWZ0ID0gMDsKbGV0IGRheXNXaXRob3V0Rm9vZCA9IDA7CmxldCB0dXJuc1dpdGhvdXRSZXN0ID0gMDsKbGV0IHJlc3REZWJ0ID0gMDsKbGV0IHN0YXJ2YXRpb25QZW5hbHR5ID0gMDsKbGV0IGZhdGlndWVQZW5hbHR5ID0gMDsKbGV0IGlzQ2FycnlpbmdMaWdodCA9IHRydWU7CmxldCB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOwpsZXQgd2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlID0gZmFsc2U7CmxldCBsb2dFbnRyaWVzID0gW107CmxldCBhY3RpdmVFZmZlY3RzID0gW107CmxldCBzZWxlY3RlZERuZG1vZEZpbGUgPSBudWxsOwpsZXQgb2xsYW1hQXZhaWxhYmxlID0gZmFsc2U7CmxldCB1c2VPbGxhbWEgPSBmYWxzZTsKbGV0IGxhc3RBaVZpYSA9ICcnOwpsZXQgY3NlbENoYXJzICA9IFtdOwpsZXQgY3NlbFNlbGVjdGVkSWQgID0gbnVsbDsKbGV0IGNzZWxQZW5kaW5nU2F2ZSA9IG51bGw7CmxldCBjc2VsUGVuZGluZ0pvaW4gPSBudWxsOwpsZXQgbmdyb2tQdWJsaWNVcmwgID0gJyc7CmxldCBjb252RmlsZVBhdGggPSBudWxsOwpsZXQgY29udlVwbG9hZGVkRmlsZSA9IG51bGw7Cgpjb25zdCBQTEFZRVJfQ09MT1JTID0gWycjN2FiYWZmJywnI2ZmYjA3YScsJyM3YWZmYjAnLCcjZmZkYTdhJywnI2Q5N2FmZicsJyNmZjdhYWEnLCcjN2FmZmZmJ107CmxldCBjb2xvck1hcCA9IHt9Owpjb25zdCBJTlZfV0VBUE9OUyA9IC9zd29yZHxkYWdnZXJ8KD88IWhhbmRccylheGV8KD86bG9uZ3xzaG9ydHxoYW5kKWJvd3xjcm9zc2Jvd3xzcGVhcnxtYWNlfGZsYWlsfHdhcmhhbW1lcnxjbHVifGtuaWZlfGJsYWRlL2k7CmNvbnN0IElOVl9BUk1PVVIgID0gL2FybW91P3J8Y2hhaW4gbWFpbHxwbGF0ZSBtYWlsfGxlYXRoZXIgYXJtb3J8c2hpZWxkfGhlbG1ldHxoZWxtfGdhdW50bGV0cz98Z3JlYXZlc3xicmFjZXJzfHJpbmcgbWFpbHxzY2FsZSBtYWlsfHNwbGludHxiYW5kZWQvaTsKY29uc3QgSU5WX0FNTU8gICAgPSAvXihib2x0cz98YXJyb3dzP3xxdWFycmVscz98c2hvdHM/fHNsaW5nIHN0b25lcz98Y3Jvc3Nib3cgYm9sdHM/KSQvaTsKY29uc3QgSU5WX01BR0lDICAgPSAvcG90aW9ufHNjcm9sbHx3YW5kfHJvZHxhbXVsZXR8Y2hhcm18ZW5jaGFudHxcK1swLTldL2k7CmNvbnN0IEFDVElPTl9UWVBFUyA9IHsKICBDT01CQVQ6ICAgJ2NvbWJhdCcsCiAgU0VBUkNIOiAgICdzZWFyY2gnLAogIFNPQ0lBTDogICAnc29jaWFsJywKICBNT1ZFTUVOVDogJ21vdmVtZW50JywKICBTS0lMTDogICAgJ3NraWxsJywKICBNQUdJQzogICAgJ21hZ2ljJywKICBJVEVNOiAgICAgJ2l0ZW0nLAogIFJFU1Q6ICAgICAncmVzdCcsCiAgT1RIRVI6ICAgICdvdGhlcicsCn07CgoKY29uc3QgT1NFX0FSTU9VUiA9IHsKICAnTGVhdGhlciBBcm1vdXInOiB7YWM6NywgY29zdDoyMCwgIG5vdGVzOicnfSwKICAnQ2hhaW4gTWFpbCc6ICAgICB7YWM6NSwgY29zdDo0MCwgIG5vdGVzOicnfSwKICAnUGxhdGUgTWFpbCc6ICAgICB7YWM6MywgY29zdDo2MCwgIG5vdGVzOidIZWF2eSAtLSBCYXJiYXJpYW5zIGNhbm5vdCB3ZWFyJ30sCiAgJ1NoaWVsZCc6ICAgICAgICAge2FjX2JvbnVzOjEsIGNvc3Q6MTAsIG5vdGVzOicnfSwKfTsKY29uc3QgR09MRF9CWV9DTEFTUyA9IHsKICBGaWdodGVyOjE4MCwnTWFnaWMtVXNlcic6MzAsQ2xlcmljOjEyMCxUaGllZjo5MCwKICBSYW5nZXI6MTUwLFBhbGFkaW46MTgwLERydWlkOjkwLElsbHVzaW9uaXN0OjMwLAogIEFzc2Fzc2luOjkwLEJhcmQ6MTIwLE1vbms6MzAsQmFyYmFyaWFuOjYwCn07Cgpjb25zdCBDTEFTU0VTID0gewogIEZpZ2h0ZXI6ICAgICB7IGljb246JycsICBocDo4LCAgYWM6MTQsIHNhdmVzOntkZWF0aDoxMix3YW5kczoxMyxwYXJhOjE0LGJyZWF0aDoxNSxzcGVsbHM6MTZ9LCBkZXNjOidCZXN0IGNvbWJhdCwgaGlnaGVzdCBIUC4gTXVsdGlwbGUgYXR0YWNrcyBhdCBoaWdoZXIgbGV2ZWxzLiBXZWFwb24gbWFzdGVyeS4nIH0sCiAgJ01hZ2ljLVVzZXInOnsgaWNvbjonJywgIGhwOjQsICBhYzoxMSwgc2F2ZXM6e2RlYXRoOjEzLHdhbmRzOjExLHBhcmE6MTMsYnJlYXRoOjE1LHNwZWxsczoxMn0sIGRlc2M6J1Bvd2VyZnVsIGFyY2FuZSBzcGVsbHMuIEZyYWdpbGUuIFNwZWxsYm9vayBtYWdpYzogU2xlZXAsIE1hZ2ljIE1pc3NpbGUsIERldGVjdCBNYWdpYy4nIH0sCiAgQ2xlcmljOiAgICAgIHsgaWNvbjonJywgIGhwOjYsICBhYzoxMywgc2F2ZXM6e2RlYXRoOjExLHdhbmRzOjEyLHBhcmE6MTQsYnJlYXRoOjE2LHNwZWxsczoxNX0sIGRlc2M6J1R1cm4gdW5kZWFkLCBoZWFsIHdvdW5kcy4gRGl2aW5lIHNwZWxsY2FzdGVyLiBIb2x5IHdhcnJpb3Igb2YgZmFpdGguJyB9LAogIFRoaWVmOiAgICAgICB7IGljb246JycsICBocDo0LCAgYWM6MTIsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxNCxwYXJhOjEzLGJyZWF0aDoxNixzcGVsbHM6MTV9LCBkZXNjOidQaWNrIGxvY2tzLCBmaW5kIHRyYXBzLCBiYWNrc3RhYiB4MiBkYW1hZ2UuIENsaW1iIHdhbGxzLCBoaWRlIGluIHNoYWRvd3MsIG1vdmUgc2lsZW50bHkuJyB9LAogIFJhbmdlcjogICAgICB7IGljb246JycsICBocDo4LCAgYWM6MTMsIHNhdmVzOntkZWF0aDoxMix3YW5kczoxMyxwYXJhOjE0LGJyZWF0aDoxNSxzcGVsbHM6MTZ9LCBkZXNjOidTa2lsbGVkIHRyYWNrZXIuIEJvbnVzIGRhbWFnZSB2cyBodW1hbm9pZHMuIER1YWwgd2llbGQuIFdpbGRlcm5lc3Mgc3Vydml2YWwgZXhwZXJ0LicgfSwKICBQYWxhZGluOiAgICAgeyBpY29uOicnLCAgaHA6OCwgIGFjOjE0LCBzYXZlczp7ZGVhdGg6MTAsd2FuZHM6MTEscGFyYToxMixicmVhdGg6MTMsc3BlbGxzOjE0fSwgZGVzYzonSG9seSB3YXJyaW9yLiBEZXRlY3QgZXZpbCBhdXJhLiBMYXkgb24gaGFuZHMuIEltbXVuZSB0byBkaXNlYXNlLiBBdXJhIG9mIHByb3RlY3Rpb24uJyB9LAogIERydWlkOiAgICAgICB7IGljb246JycsICBocDo2LCAgYWM6MTIsIHNhdmVzOntkZWF0aDoxMCx3YW5kczoxMSxwYXJhOjEzLGJyZWF0aDoxMixzcGVsbHM6MTR9LCBkZXNjOidOYXR1cmUgbWFnaWMuIFNoYXBlY2hhbmdlIGF0IGhpZ2hlciBsZXZlbHMuIFdvb2RsYW5kIGFsbGllcy4gUmVzaXN0IGZpcmUgJiBsaWdodG5pbmcuJyB9LAogIElsbHVzaW9uaXN0OiB7IGljb246JycsICBocDo0LCAgYWM6MTEsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxMSxwYXJhOjEzLGJyZWF0aDoxNSxzcGVsbHM6MTJ9LCBkZXNjOidJbGx1c2lvbiBtYWdpYyBzcGVjaWFsaXN0LiBDb2xvdXIgU3ByYXksIFBoYW50YXNtYWwgRm9yY2UsIEh5cG5vdGlzbSwgTWlycm9yIEltYWdlLicgfSwKICBBc3Nhc3NpbjogICAgeyBpY29uOicnLCAgaHA6NiwgIGFjOjEyLCBzYXZlczp7ZGVhdGg6MTMsd2FuZHM6MTQscGFyYToxMyxicmVhdGg6MTYsc3BlbGxzOjE1fSwgZGVzYzonTWFzdGVyIGtpbGxlci4gRGlzZ3Vpc2UsIHBvaXNvbiB1c2UuIEFzc2Fzc2luYXRpb24gc3RyaWtlIGZvciBpbnN0YW50IGtpbGwgY2hhbmNlLicgfSwKICBCYXJkOiAgICAgICAgeyBpY29uOicnLCAgaHA6NiwgIGFjOjEyLCBzYXZlczp7ZGVhdGg6MTMsd2FuZHM6MTQscGFyYToxMyxicmVhdGg6MTYsc3BlbGxzOjE1fSwgZGVzYzonSmFjayBvZiBhbGwgdHJhZGVzLiBJbnNwaXJlIGFsbGllcywgY2hhcm0uIExvcmUga25vd2xlZGdlLiBUaGllZiBza2lsbHMuJyB9LAogIE1vbms6ICAgICAgICB7IGljb246JycsICBocDo2LCAgYWM6MTAsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxNCxwYXJhOjEzLGJyZWF0aDoxNixzcGVsbHM6MTV9LCBkZXNjOidVbmFybWVkIGNvbWJhdCBtYXN0ZXIuIFVuYXJtb3VyZWQgQUMgYm9udXMuIFN0dW5uaW5nIHN0cmlrZS4gRmFzdCBtb3ZlbWVudC4nIH0sCiAgQmFyYmFyaWFuOiAgIHsgaWNvbjonJywgIGhwOjEwLCBhYzoxMiwgc2F2ZXM6e2RlYXRoOjEyLHdhbmRzOjEzLHBhcmE6MTQsYnJlYXRoOjE1LHNwZWxsczoxNn0sIGRlc2M6J1JhZ2UgZm9yIGJvbnVzIGRhbWFnZS4gSW5zdGluY3RpdmUgQUMgd2hlbiB1bmFybW91cmVkLiBXaWxkZXJuZXNzIHN1cnZpdmFsLiBCZXJzZXJrZXIuJyB9LAp9OwoKY29uc3QgUkFDRVMgPSB7CiAgSHVtYW46ICAgICB7IGljb246JycsIGRlc2M6J0FueSBjbGFzcywgaGlnaGVzdCBsZXZlbCBjYXBzLicsIHNwZWNpYWxzOltdIH0sCiAgRHdhcmY6ICAgICB7IGljb246JycsIGRlc2M6J0luZnJhdmlzaW9uIDYwZnQuICs0IHNhdmUgdnMgbWFnaWMgJiBwb2lzb24uIERldGVjdCBzdG9uZXdvcmsuJywgc3BlY2lhbHM6WydJbmZyYXZpc2lvbiA2MGZ0JywnKzQgc2F2ZSB2cyBtYWdpYy9wb2lzb24nLCdEZXRlY3Qgc3RvbmV3b3JrIHRyYXBzIDEtMi9kNiddLCBjbGFzc2VzOlsnRmlnaHRlcicsJ1RoaWVmJywnQXNzYXNzaW4nXSB9LAogIEVsZjogICAgICAgeyBpY29uOicnLCBkZXNjOidJbmZyYXZpc2lvbiA2MGZ0LiBEZXRlY3Qgc2VjcmV0IGRvb3JzLiBJbW11bmUgdG8gZ2hvdWwgcGFyYWx5c2lzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gNjBmdCcsJ0RldGVjdCBzZWNyZXQgZG9vcnMgMS0yL2Q2JywnSW1tdW5lIHRvIGdob3VsIHBhcmFseXNpcyddLCBjbGFzc2VzOlsnRmlnaHRlcicsJ01hZ2ljLVVzZXInLCdUaGllZicsJ1JhbmdlcicsJ0lsbHVzaW9uaXN0JywnQmFyZCddIH0sCiAgSGFsZmxpbmc6ICB7IGljb246JycsIGRlc2M6Jy0yIEFDIHZzIGxhcmdlIGZvZXMuIFN1cnByaXNlIG9ubHkgMS9kNi4gKzEgdG8gcmFuZ2VkLicsIHNwZWNpYWxzOlsnLTIgQUMgdnMgbGFyZ2UgY3JlYXR1cmVzJywnU3VycHJpc2Ugb24gMS9kNiBvbmx5JywnKzEgdG8gcmFuZ2VkIGF0dGFja3MnXSwgY2xhc3NlczpbJ0ZpZ2h0ZXInLCdUaGllZicsJ0RydWlkJ10gfSwKICAnSGFsZi1FbGYnOnsgaWNvbjonJywgZGVzYzonSW5mcmF2aXNpb24gNjBmdC4gRGV0ZWN0IHNlY3JldCBkb29ycyAxLTMvZDYuIFZlcnNhdGlsZSBjbGFzc2VzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gNjBmdCcsJ0RldGVjdCBzZWNyZXQgZG9vcnMgMS0zL2Q2J10sIGNsYXNzZXM6WydGaWdodGVyJywnTWFnaWMtVXNlcicsJ0NsZXJpYycsJ1RoaWVmJywnUmFuZ2VyJywnQmFyZCcsJ0RydWlkJywnSWxsdXNpb25pc3QnXSB9LAogIEdub21lOiAgICAgeyBpY29uOicnLCBkZXNjOidJbmZyYXZpc2lvbiA5MGZ0LiArNCBzYXZlIHZzIG1hZ2ljLiBTcGVhayB3aXRoIGJ1cnJvd2luZyBhbmltYWxzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gOTBmdCcsJys0IHNhdmUgdnMgbWFnaWMnLCdTcGVhayB3aXRoIGJ1cnJvd2luZyBhbmltYWxzJ10sIGNsYXNzZXM6WydGaWdodGVyJywnVGhpZWYnLCdJbGx1c2lvbmlzdCcsJ0Fzc2Fzc2luJ10gfSwKICAnSGFsZi1PcmMnOnsgaWNvbjonJywgZGVzYzonKzEgU1RSICYgQ09OLiBJbmZyYXZpc2lvbiA2MGZ0LiBJbnRpbWlkYXRpbmcuJywgc3BlY2lhbHM6WydJbmZyYXZpc2lvbiA2MGZ0JywnKzEgU1RSIGFuZCBDT04nXSwgYm9udXNlczp7U1RSOjEsQ09OOjF9LCBjbGFzc2VzOlsnRmlnaHRlcicsJ0NsZXJpYycsJ1RoaWVmJywnQXNzYXNzaW4nLCdCYXJiYXJpYW4nXSB9LAp9OwoKY29uc3QgQ0xBU1NfV0VBUE9OX1JFU1RSSUNUSU9OUyA9IHsKICBGaWdodGVyOiAgICAgIG51bGwsIC8vIGFsbCB3ZWFwb25zCiAgUmFuZ2VyOiAgICAgICBudWxsLAogIFBhbGFkaW46ICAgICAgbnVsbCwKICBCYXJiYXJpYW46ICAgIG51bGwsCiAgQ2xlcmljOiAgICAgICBbJ0NsdWInLCdNYWNlJywnU3RhZmYnLCdXYXIgSGFtbWVyJywnU2xpbmcnLCdTaG9ydCBCb3cnXSwgLy8gYmx1bnQgb25seQogIERydWlkOiAgICAgICAgWydDbHViJywnRGFnZ2VyJywnSGFuZCBBeGUnLCdTcGVhcicsJ1N0YWZmJywnU2xpbmcnLCdTaG9ydCBCb3cnXSwKICAnTWFnaWMtVXNlcic6IFsnRGFnZ2VyJywnU2lsdmVyIERhZ2dlcicsJ1N0YWZmJ10sCiAgSWxsdXNpb25pc3Q6ICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdTdGFmZiddLAogIFRoaWVmOiAgICAgICAgWydEYWdnZXInLCdTaWx2ZXIgRGFnZ2VyJywnQ2x1YicsJ1Nob3J0IFN3b3JkJywnSGFuZCBBeGUnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJ10sCiAgQXNzYXNzaW46ICAgICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdDbHViJywnU2hvcnQgU3dvcmQnLCdIYW5kIEF4ZScsJ01hY2UnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJ10sCiAgQmFyZDogICAgICAgICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdDbHViJywnU2hvcnQgU3dvcmQnLCdIYW5kIEF4ZScsJ01hY2UnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJywnU3dvcmQnLCdTdGFmZiddLAogIE1vbms6ICAgICAgICAgWydDbHViJywnRGFnZ2VyJywnSGFuZCBBeGUnLCdKYXZlbGluJywnU2hvcnQgU3dvcmQnLCdTdGFmZicsJ1NsaW5nJ10sCn07Cgpjb25zdCBDTEFTU19BUk1PVVJfUkVTVFJJQ1RJT05TID0gewogIEZpZ2h0ZXI6WydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdQbGF0ZSBNYWlsJywnU2hpZWxkJ10sCiAgUmFuZ2VyOiBbJ0xlYXRoZXIgQXJtb3VyJywnQ2hhaW4gTWFpbCcsJ1BsYXRlIE1haWwnLCdTaGllbGQnXSwKICBQYWxhZGluOlsnTGVhdGhlciBBcm1vdXInLCdDaGFpbiBNYWlsJywnUGxhdGUgTWFpbCcsJ1NoaWVsZCddLAogIEJhcmJhcmlhbjpbJ0xlYXRoZXIgQXJtb3VyJywnQ2hhaW4gTWFpbCcsJ1NoaWVsZCddLAogIENsZXJpYzogWydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdQbGF0ZSBNYWlsJywnU2hpZWxkJ10sCiAgRHJ1aWQ6ICBbJ0xlYXRoZXIgQXJtb3VyJywnU2hpZWxkJ10sCiAgVGhpZWY6ICBbJ0xlYXRoZXIgQXJtb3VyJ10sCiAgQXNzYXNzaW46WydMZWF0aGVyIEFybW91cicsJ1NoaWVsZCddLAogIEJhcmQ6ICAgWydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdTaGllbGQnXSwKICBNb25rOiAgIFtdLCAvLyBubyBhcm1vdXIKICAnTWFnaWMtVXNlcic6W10sCiAgSWxsdXNpb25pc3Q6W10sCn07Cgpjb25zdCBPU0VfV0VBUE9OUyA9IHsKICAvLyBNZWxlZSAtLSB7ZG1nLCBjb3N0IChncCksIGhhbmRzLCBub3Rlc30KICAnQmF0dGxlIEF4ZSc6ICAgICAgIHtkbWc6JzFkOCcsICBjb3N0OjcsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAnQ2x1Yic6ICAgICAgICAgICAgIHtkbWc6JzFkNCcsICBjb3N0OjAsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczonZnJlZSd9LAogICdEYWdnZXInOiAgICAgICAgICAge2RtZzonMWQ0JywgIGNvc3Q6MywgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2V9LAogICdIYW5kIEF4ZSc6ICAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6NCwgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOidjYW4gdGhyb3cnfSwKICAnTGFuY2UnOiAgICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjEwLCAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczonbW91bnRlZCBvbmx5J30sCiAgJ01hY2UnOiAgICAgICAgICAgICB7ZG1nOicxZDYnLCAgY29zdDo1LCAgIGhhbmRzOjEsIHJhbmdlZDpmYWxzZX0sCiAgJ1BvbGUgQXJtJzogICAgICAgICB7ZG1nOicxZDEwJywgY29zdDo3LCAgIGhhbmRzOjIsIHJhbmdlZDpmYWxzZSwgbm90ZXM6J3R3by1oYW5kZWQnfSwKICAnU2hvcnQgU3dvcmQnOiAgICAgIHtkbWc6JzFkNicsICBjb3N0OjcsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAnU2lsdmVyIERhZ2dlcic6ICAgIHtkbWc6JzFkNCcsICBjb3N0OjMwLCAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczondnMgbHljYW50aHJvcGVzL3VuZGVhZCd9LAogICdTcGVhcic6ICAgICAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6MywgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOidjYW4gdGhyb3cnfSwKICAnU3RhZmYnOiAgICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjAsICAgaGFuZHM6MiwgcmFuZ2VkOmZhbHNlLCBub3RlczondHdvLWhhbmRlZCwgZnJlZSd9LAogICdTd29yZCc6ICAgICAgICAgICAge2RtZzonMWQ4JywgIGNvc3Q6MTAsICBoYW5kczoxLCByYW5nZWQ6ZmFsc2V9LAogICdUd28tSGFuZGVkIFN3b3JkJzoge2RtZzonMWQxMCcsIGNvc3Q6MTUsICBoYW5kczoyLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOid0d28taGFuZGVkLCBubyBzaGllbGQnfSwKICAnV2FyIEhhbW1lcic6ICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjUsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAvLyBSYW5nZWQKICAnQ3Jvc3Nib3cnOiAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjMwLCAgaGFuZHM6MiwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgODAvMTYwLzI0MCwgc2xvdyByZWxvYWQnfSwKICAnSmF2ZWxpbic6ICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjEsICAgaGFuZHM6MSwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgMzAvNjAvOTAnfSwKICAnTG9uZyBCb3cnOiAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjYwLCAgaGFuZHM6MiwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgNzAvMTQwLzIxMCwgc3RyIHJlcSd9LAogICdTaG9ydCBCb3cnOiAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6MjUsICBoYW5kczoyLCByYW5nZWQ6dHJ1ZSwgIG5vdGVzOidyYW5nZSA1MC8xMDAvMTUwJ30sCiAgJ1NsaW5nJzogICAgICAgICAgICB7ZG1nOicxZDQnLCAgY29zdDoyLCAgIGhhbmRzOjEsIHJhbmdlZDp0cnVlLCAgbm90ZXM6J3JhbmdlIDQwLzgwLzE2MCd9LAogIC8vIEFtbW8KICAnQXJyb3dzICgyMCknOiAgICAgIHtkbWc6Jy0nLCAgICBjb3N0OjUsICAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZm9yIGJvd3MnfSwKICAnQ3Jvc3Nib3cgQm9sdHMgKDMwKSc6IHtkbWc6Jy0nLCBjb3N0OjEwLCAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZm9yIGNyb3NzYm93J30sCiAgJ1NpbHZlci1UaXBwZWQgQXJyb3dzICg2KSc6IHtkbWc6Jy0nLCBjb3N0OjMwLCBoYW5kczowLCByYW5nZWQ6dHJ1ZSwgbm90ZXM6J3ZzIGx5Y2FudGhyb3Blcy91bmRlYWQnfSwKICAnU2xpbmcgU3RvbmVzICgyMCknOntkbWc6Jy0nLCAgICBjb3N0OjAsICAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZnJlZSd9LAp9OwoKY29uc3QgT1NFX0VRVUlQTUVOVCA9IHsKICAnQmFja3BhY2snOiAgICAgICAgICAgICAgICAge2Nvc3Q6NX0sCiAgJ0Nyb3diYXInOiAgICAgICAgICAgICAgICAgIHtjb3N0OjEwfSwKICAnR2FybGljJzogICAgICAgICAgICAgICAgICAge2Nvc3Q6NSwgICBub3RlczoncGVyIGhlYWQnfSwKICAnR3JhcHBsaW5nIEhvb2snOiAgICAgICAgICAge2Nvc3Q6MjV9LAogICdIYW1tZXIgKHNtYWxsKSc6ICAgICAgICAgICB7Y29zdDoyfSwKICAnSG9seSBTeW1ib2wnOiAgICAgICAgICAgICAge2Nvc3Q6MjV9LAogICdIb2x5IFdhdGVyICh2aWFsKSc6ICAgICAgICB7Y29zdDoyNX0sCiAgJ0lyb24gU3Bpa2VzICgxMiknOiAgICAgICAgIHtjb3N0OjF9LAogICdMYW50ZXJuJzogICAgICAgICAgICAgICAgICB7Y29zdDoxMH0sCiAgJ01pcnJvciAoaGFuZC1zaXplZCwgc3RlZWwpJzp7Y29zdDo1fSwKICAnT2lsICgxIGZsYXNrKSc6ICAgICAgICAgICAge2Nvc3Q6Mn0sCiAgJ1BvbGUgKDEwZnQgd29vZGVuKSc6ICAgICAgIHtjb3N0OjF9LAogICdSYXRpb25zIChpcm9uLCA3IGRheXMpJzogICB7Y29zdDoxNSwgbm90ZXM6J3ByZXNlcnZlZCd9LAogICdSYXRpb25zIChzdGFuZGFyZCwgNyBkYXlzKSc6e2Nvc3Q6NX0sCiAgJ1JvcGUgKDUwZnQpJzogICAgICAgICAgICAgIHtjb3N0OjF9LAogICdTYWNrIChsYXJnZSknOiAgICAgICAgICAgICB7Y29zdDoyfSwKICAnU2FjayAoc21hbGwpJzogICAgICAgICAgICAge2Nvc3Q6MX0sCiAgJ1N0YWtlcyAoMykgYW5kIE1hbGxldCc6ICAgIHtjb3N0OjN9LAogICJUaGlldmVzJyBUb29scyI6ICAgICAgICAgICB7Y29zdDoyNX0sCiAgJ1RpbmRlciBCb3ggKGZsaW50ICYgc3RlZWwpJzp7Y29zdDozfSwKICAnVG9yY2hlcyAoNiknOiAgICAgICAgICAgICAge2Nvc3Q6MX0sCiAgJ1dhdGVyc2tpbic6ICAgICAgICAgICAgICAgIHtjb3N0OjF9LAogICdXaW5lICgyIHBpbnRzKSc6ICAgICAgICAgICB7Y29zdDoxfSwKICAnV29sZnNiYW5lICgxIGJ1bmNoKSc6ICAgICAge2Nvc3Q6MTB9LAp9OwoKCmZ1bmN0aW9uIHhockZldGNoKHVybCwgb3B0cykgewogIHJldHVybiBuZXcgUHJvbWlzZSgocmVzb2x2ZSwgcmVqZWN0KSA9PiB7CiAgICBjb25zdCB4aHIgPSBuZXcgWE1MSHR0cFJlcXVlc3QoKTsKICAgIGNvbnN0IG1ldGhvZCA9IChvcHRzICYmIG9wdHMubWV0aG9kKSB8fCAnR0VUJzsKICAgIHhoci5vcGVuKG1ldGhvZCwgdXJsLCB0cnVlKTsKICAgIGlmIChvcHRzICYmIG9wdHMuaGVhZGVycykgewogICAgICBPYmplY3QuZW50cmllcyhvcHRzLmhlYWRlcnMpLmZvckVhY2goKFtrLHZdKSA9PiB4aHIuc2V0UmVxdWVzdEhlYWRlcihrLHYpKTsKICAgIH0KICAgIHhoci50aW1lb3V0ID0gMTgwMDAwOwogICAgeGhyLm9ubG9hZCA9ICgpID0+IHJlc29sdmUoewogICAgICBvazogeGhyLnN0YXR1cyA+PSAyMDAgJiYgeGhyLnN0YXR1cyA8IDMwMCwKICAgICAgc3RhdHVzOiB4aHIuc3RhdHVzLAogICAgICBqc29uOiAoKSA9PiBQcm9taXNlLnJlc29sdmUoSlNPTi5wYXJzZSh4aHIucmVzcG9uc2VUZXh0KSksCiAgICAgIHRleHQ6ICgpID0+IFByb21pc2UucmVzb2x2ZSh4aHIucmVzcG9uc2VUZXh0KSwKICAgIH0pOwogICAgeGhyLm9uZXJyb3IgPSAoKSA9PiByZWplY3QobmV3IEVycm9yKCdOZXR3b3JrIHJlcXVlc3QgZmFpbGVkOiAnICsgbWV0aG9kICsgJyAnICsgdXJsKSk7CiAgICB4aHIub250aW1lb3V0ID0gKCkgPT4gcmVqZWN0KG5ldyBFcnJvcignUmVxdWVzdCB0aW1lZCBvdXQ6ICcgKyBtZXRob2QgKyAnICcgKyB1cmwpKTsKICAgIHhoci5zZW5kKChvcHRzICYmIG9wdHMuYm9keSkgfHwgbnVsbCk7CiAgfSk7Cn0KCmZ1bmN0aW9uIHNob3coaWQpIHsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuc2NyZWVuJykuZm9yRWFjaChzID0+IHsKICAgIHMuY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJyk7CiAgICBzLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgfSk7CiAgY29uc3QgdGFyZ2V0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpOwogIGlmICghdGFyZ2V0KSB7IGNvbnNvbGUuZXJyb3IoJ1tzaG93XSBFbGVtZW50IG5vdCBmb3VuZDonLCBpZCk7IHJldHVybjsgfQogIHRhcmdldC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICB0YXJnZXQuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKICBpZiAoaWQgIT09ICdzLWdhbWUnKSB0YXJnZXQuc2Nyb2xsVG9wID0gMDsKICBjb25zb2xlLmxvZygnW3Nob3ddIE5hdmlnYXRlZCB0bzonLCBpZCk7CiAgLy8gU2NyZWVuLXNwZWNpZmljIGluaXQKICBpZiAoaWQgPT09ICdzLWNvbnZlcnQnKSB7IGluaXRDb252RHJvcCgpOyBjb252TG9hZEV4aXN0aW5nKCk7IH0KfQoKYXN5bmMgZnVuY3Rpb24gY2hlY2tPbGxhbWFTdGF0dXMoKSB7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYWktc3RhdHVzJyk7CiAgY29uc3QgYXBpQm94ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktYm94Jyk7CiAgY29uc3QgYXBpTGluayA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzaG93LWFwaS1saW5rJyk7CiAgaWYgKCFlbCkgcmV0dXJuOwoKICAvLyBUaW1lb3V0IHdyYXBwZXIgLS0gbmV2ZXIgc3RheSBzdHVjayBvbiAiQ2hlY2tpbmcuLi4iCiAgY29uc3QgdGltZW91dCA9IG5ldyBQcm9taXNlKChfLCByZWplY3QpID0+CiAgICBzZXRUaW1lb3V0KCgpID0+IHJlamVjdChuZXcgRXJyb3IoJ3RpbWVvdXQnKSksIDUwMDApCiAgKTsKCiAgdHJ5IHsKICAgIGNvbnN0IHIgPSBhd2FpdCBQcm9taXNlLnJhY2UoW3hockZldGNoKEJBU0VfVVJMICsgJy9vbGxhbWFfc3RhdHVzJyksIHRpbWVvdXRdKTsKCiAgICAvLyBDaGVjayBpZiB0aGlzIGlzIGFjdHVhbGx5IHRoZSB2MyBzZXJ2ZXIgKG9sZCBzZXJ2ZXJzIHdvbid0IGhhdmUgdGhpcyBlbmRwb2ludCkKICAgIGlmICghci5vaykgewogICAgICB0aHJvdyBuZXcgRXJyb3IoJ1NlcnZlciByZXR1cm5lZCAnICsgci5zdGF0dXMgKyAnIC0tIG1heSBiZSBydW5uaW5nIG9sZCB2ZXJzaW9uLiBIYXJkIHJlZnJlc2ggd2l0aCBDdHJsK1NoaWZ0K1InKTsKICAgIH0KCiAgICBjb25zdCBkID0gYXdhaXQgci5qc29uKCk7CgogICAgLy8gVmVyaWZ5IHRoaXMgaXMgYWN0dWFsbHkgYW4gb2xsYW1hX3N0YXR1cyByZXNwb25zZSAobm90IHNvbWUgb3RoZXIgZW5kcG9pbnQncyByZXNwb25zZSkKICAgIGlmICh0eXBlb2YgZC5hdmFpbGFibGUgPT09ICd1bmRlZmluZWQnKSB7CiAgICAgIHRocm93IG5ldyBFcnJvcignVW5leHBlY3RlZCByZXNwb25zZSAtLSBvbGQgc2VydmVyIG1heSBiZSBydW5uaW5nLiBTdG9wIGl0IGFuZCByZXN0YXJ0IGRuZF9hZHZlbnR1cmVfdjQucHknKTsKICAgIH0KCiAgICBvbGxhbWFBdmFpbGFibGUgPSBkLmF2YWlsYWJsZTsKICAgIHVzZU9sbGFtYSA9IGQuYXZhaWxhYmxlOwoKICAgIGlmIChkLmF2YWlsYWJsZSkgewogICAgICBlbC5zdHlsZS5ib3JkZXIgPSAnMnB4IHNvbGlkICMzYTZhM2EnOwogICAgICBlbC5zdHlsZS5iYWNrZ3JvdW5kID0gJyMwYTFhMGEnOwogICAgICBlbC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsKICAgICAgZWwuaW5uZXJIVE1MID0gJ09sbGFtYSBydW5uaW5nICZtZGFzaDsgPHN0cm9uZz4nICsgKGQubW9kZWwgfHwgJ2xvY2FsJykgKyAnPC9zdHJvbmc+JwogICAgICAgICsgJzxicj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Zm9udC13ZWlnaHQ6bm9ybWFsOyI+RnJlZSBsb2NhbCBBSSByZWFkeS4gTm8gQVBJIGtleSBuZWVkZWQgdG8gaG9zdC48L3NwYW4+JzsKICAgICAgaWYgKGFwaUxpbmspIGFwaUxpbmsuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICAgIGlmIChhcGlCb3gpIGFwaUJveC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgfSBlbHNlIHsKICAgICAgZWwuc3R5bGUuYm9yZGVyID0gJzJweCBzb2xpZCAjOGE1YTIwJzsKICAgICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICcjMWExMDAwJzsKICAgICAgZWwuc3R5bGUuY29sb3IgPSAnI2MwOTA2MCc7CiAgICAgIGVsLmlubmVySFRNTCA9ICchIE9sbGFtYSBub3QgcnVubmluZycKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+SW5zdGFsbCBmcm9tIDxhIGhyZWY9Imh0dHBzOi8vb2xsYW1hLmNvbSIgdGFyZ2V0PSJfYmxhbmsiIHN0eWxlPSJjb2xvcjojYzlhODRjIj5vbGxhbWEuY29tPC9hPiB0aGVuIHJ1bjogPGNvZGUgc3R5bGU9ImNvbG9yOiNjOWE4NGMiPm9sbGFtYSBwdWxsIG1pc3RyYWwtbmVtbzoxMmI8L2NvZGU+PC9zcGFuPicKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+T3IgZW50ZXIgYSBDbGF1ZGUgQVBJIGtleSBiZWxvdy48L3NwYW4+JzsKICAgICAgaWYgKGFwaUJveCkgYXBpQm94LnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICAgIGlmIChhcGlMaW5rKSBhcGlMaW5rLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICB9CiAgfSBjYXRjaChlKSB7CiAgICBlbC5zdHlsZS5ib3JkZXIgPSAnMnB4IHNvbGlkICM4YjI1MjUnOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICcjMWEwYTBhJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyNjMDYwNjAnOwogICAgaWYgKGUubWVzc2FnZSA9PT0gJ3RpbWVvdXQnKSB7CiAgICAgIGVsLmlubmVySFRNTCA9ICchIFNlcnZlciBub3QgcmVzcG9uZGluZycKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+TWFrZSBzdXJlIGRuZF9hZHZlbnR1cmVfdjQucHkgaXMgcnVubmluZywgdGhlbiBoYXJkIHJlZnJlc2g6IDxzdHJvbmc+Q3RybCtTaGlmdCtSPC9zdHJvbmc+PC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICBlbC5pbm5lckhUTUwgPSAnISAnICsgZS5tZXNzYWdlCiAgICAgICAgKyAnPGJyPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTZweDsiPlRyeTogc3RvcCB0aGUgc2VydmVyLCBydW4gZG5kX2FkdmVudHVyZV92NC5weSBhZ2FpbiwgdGhlbiA8c3Ryb25nPkN0cmwrU2hpZnQrUjwvc3Ryb25nPjwvc3Bhbj4nOwogICAgfQogICAgLy8gU2hvdyBBUEkga2V5IGJveCBhcyBmYWxsYmFjawogICAgaWYgKGFwaUJveCkgYXBpQm94LnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICBpZiAoYXBpTGluaykgYXBpTGluay5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgY29uc29sZS5lcnJvcignW09sbGFtYSBjaGVja10nLCBlKTsKICB9Cn0KCmZ1bmN0aW9uIHVwZGF0ZUFpSW5kaWNhdG9yKHZpYSwgbW9kZWwpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtYWktaW5kaWNhdG9yJyk7CiAgaWYgKCFlbCkgcmV0dXJuOwogIGlmICh2aWEgPT09ICdvbGxhbWEnKSB7CiAgICBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICcjM2E2YTNhJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyM2YTlhNmEnOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICdyZ2JhKDU4LDEwNiw1OCwwLjEpJzsKICAgIGVsLmlubmVySFRNTCA9ICctIE9sbGFtYSAoJyArIChtb2RlbCB8fCAnbG9jYWwnKSArICcpJzsKICB9IGVsc2UgaWYgKHZpYSA9PT0gJ2NsYXVkZScpIHsKICAgIGVsLnN0eWxlLmJvcmRlckNvbG9yID0gJyM3YTYwMzAnOwogICAgZWwuc3R5bGUuY29sb3IgPSAnI2M5YTg0Yyc7CiAgICBlbC5zdHlsZS5iYWNrZ3JvdW5kID0gJ3JnYmEoMjAxLDE2OCw3NiwwLjA2KSc7CiAgICBlbC5pbm5lckhUTUwgPSAnLSBDbGF1ZGUgQVBJJzsKICB9IGVsc2UgaWYgKHZpYSA9PT0gJ2Vycm9yJykgewogICAgZWwuc3R5bGUuYm9yZGVyQ29sb3IgPSAnIzhiMjUyNSc7CiAgICBlbC5zdHlsZS5jb2xvciA9ICcjYzA2MDYwJzsKICAgIGVsLnN0eWxlLmJhY2tncm91bmQgPSAncmdiYSgxMzksMzcsMzcsMC4wNiknOwogICAgZWwuaW5uZXJIVE1MID0gJyEgQUkgRXJyb3InOwogIH0gZWxzZSB7CiAgICBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICcjM2EzMDIwJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyM4YTdhNTgnOwogICAgZWwuaW5uZXJIVE1MID0gJy0gQUk6IGNoZWNraW5nLi4uJzsKICB9Cn0KCmZ1bmN0aW9uIHJvdGF0ZUJhbm5lZFBocmFzZXMoKSB7CiAgLy8gUGljayA1IHJhbmRvbSBwaHJhc2VzIGZyb20gdGhlIHBvb2wgZWFjaCB0aW1lIHRvIGtlZXAgaXQgZnJlc2gKICBjb25zdCBzaHVmZmxlZCA9IFsuLi5CQU5ORURfUEhSQVNFU19QT09MXS5zb3J0KCgpID0+IE1hdGgucmFuZG9tKCkgLSAwLjUpOwogIGJhbm5lZFBocmFzZXMgPSBzaHVmZmxlZC5zbGljZSgwLCA1KTsKfQoKZnVuY3Rpb24gZ2V0Q29sb3IobmFtZSkgewogIGlmICghY29sb3JNYXBbbmFtZV0pIHsKICAgIGNvbnN0IHVzZWQgPSBPYmplY3Qua2V5cyhjb2xvck1hcCkubGVuZ3RoOwogICAgY29sb3JNYXBbbmFtZV0gPSBQTEFZRVJfQ09MT1JTW3VzZWQgJSBQTEFZRVJfQ09MT1JTLmxlbmd0aF07CiAgfQogIHJldHVybiBjb2xvck1hcFtuYW1lXTsKfQoKZnVuY3Rpb24gZ2V0Q29sb3JGb3JDbGFzcyhjbHMpIHsKICBjb25zdCBtYXAgPSB7CiAgICAnRmlnaHRlcic6JyNjOWE4NGMnLCdNYWdpYy1Vc2VyJzonIzdhYmFmZicsJ0NsZXJpYyc6JyNmZmZmZmYnLAogICAgJ1RoaWVmJzonI2ZmYjA3YScsJ1Jhbmdlcic6JyM3YWZmYjAnLCdQYWxhZGluJzonI2ZmZmFhYScsCiAgICAnRHJ1aWQnOicjN2FmZjdhJywnSWxsdXNpb25pc3QnOicjZDk3YWZmJywnQXNzYXNzaW4nOicjZmY3YWFhJywKICAgICdCYXJkJzonI2ZmZGE3YScsJ01vbmsnOicjYWFmZmZmJywnQmFyYmFyaWFuJzonI2ZmOWE3YScsCiAgICAnQWNyb2JhdCc6JyNjMGMwZmYnLCdLbmlnaHQnOicjZmZlMGEwJywKICB9OwogIHJldHVybiBtYXBbY2xzXSB8fCAnI2M5YTg0Yyc7Cn0KCmZ1bmN0aW9uIHNob3dDaGFyU2VsZWN0KGNvbnRleHQsIGNvbnRleHRMYWJlbCwgcGVuZGluZ0RhdGEpIHsKICBjc2VsU2VsZWN0ZWRJZCA9IG51bGw7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NzZWwtdXNlLWJ0bicpLmRpc2FibGVkID0gdHJ1ZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1wcmV2aWV3Jykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1tb2R1bGUnKS50ZXh0Q29udGVudCA9IGNvbnRleHRMYWJlbDsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1jb250ZXh0JykudGV4dENvbnRlbnQgPSBjb250ZXh0OwoKICBzaG93KCdzLWNoYXJzZWxlY3QnKTsKCiAgLy8gTG9hZCBjaGFyYWN0ZXJzIGZyb20gc2VydmVyCiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NoYXJhY3RlcnMnKS50aGVuKHI9PnIuanNvbigpKS50aGVuKGNoYXJzID0+IHsKICAgIGNzZWxDaGFycyA9IGNoYXJzOwogICAgY29uc3QgbGlzdCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjc2VsLWxpc3QnKTsKICAgIGlmICghY2hhcnMubGVuZ3RoKSB7CiAgICAgIGxpc3QuaW5uZXJIVE1MID0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2NvbG9yOnZhcigtLWRpbSk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweDtiYWNrZ3JvdW5kOnZhcigtLXBhbmVsKTsiPk5vIHNhdmVkIGNoYXJhY3RlcnMgeWV0LiBDcmVhdGUgYSBuZXcgb25lIGJlbG93LjwvZGl2Pic7CiAgICB9IGVsc2UgewogICAgICBsaXN0LmlubmVySFRNTCA9IGNoYXJzLm1hcChjID0+IHsKICAgICAgICBjb25zdCBjb2wgPSBnZXRDb2xvckZvckNsYXNzKGMuY2xzKTsKICAgICAgICByZXR1cm4gYDxkaXYgY2xhc3M9ImNzZWwtaXRlbSIgaWQ9ImNpLSR7Yy5pZH0iIG9uY2xpY2s9InByZXZpZXdDaGFyKCcke2MuaWR9JykiPgogICAgICAgICAgPGRpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2ktbmFtZSI+JHtjLm5hbWV9PC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNpLXN1YiI+CiAgICAgICAgICAgICAgTGV2ZWwgJHtjLmxldmVsfSAke2MucmFjZX0gJHtjLmNsc30gJm5ic3A7KiZuYnNwOyAke2MuYWxpZ259CiAgICAgICAgICAgICAgJm5ic3A7KiZuYnNwOyBIUCAke2MuaHB9LyR7Yy5tYXhocH0gJm5ic3A7KiZuYnNwOyBBQyAke2MuYWN9ICZuYnNwOyombmJzcDsgJHtjLmdvbGR9Z3AKICAgICAgICAgICAgICA8YnI+TGFzdCBwbGF5ZWQ6ICR7bmV3IERhdGUoYy5zYXZlZEF0KS50b0xvY2FsZURhdGVTdHJpbmcoKX0KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxzcGFuIGNsYXNzPSJjaS1iYWRnZSIgc3R5bGU9ImJvcmRlci1jb2xvcjoke2NvbH07Y29sb3I6JHtjb2x9OyI+JHtjLmNsc308L3NwYW4+CiAgICAgICAgPC9kaXY+YDsKICAgICAgfSkuam9pbignJyk7CiAgICB9CiAgfSk7CgogIC8vIFN0b3JlIHBlbmRpbmcgYWN0aW9uCiAgaWYgKHBlbmRpbmdEYXRhICYmIHBlbmRpbmdEYXRhLnR5cGUgPT09ICdzYXZlJykgY3NlbFBlbmRpbmdTYXZlID0gcGVuZGluZ0RhdGE7CiAgaWYgKHBlbmRpbmdEYXRhICYmIHBlbmRpbmdEYXRhLnR5cGUgPT09ICdqb2luJykgY3NlbFBlbmRpbmdKb2luID0gcGVuZGluZ0RhdGE7Cn0KCmZ1bmN0aW9uIHByZXZpZXdDaGFyKGlkKSB7CiAgLy8gRGVzZWxlY3QgYWxsCiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLmNzZWwtaXRlbScpLmZvckVhY2goZWwgPT4gZWwuY2xhc3NMaXN0LnJlbW92ZSgnc2VsJykpOwogIGNvbnN0IGl0ZW0gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2ktJyArIGlkKTsKICBpZiAoaXRlbSkgaXRlbS5jbGFzc0xpc3QuYWRkKCdzZWwnKTsKCiAgY3NlbFNlbGVjdGVkSWQgPSBpZDsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC11c2UtYnRuJykuZGlzYWJsZWQgPSBmYWxzZTsKCiAgLy8gRmluZCBjaGFyIGRhdGEKICBjb25zdCBjID0gY3NlbENoYXJzLmZpbmQoeCA9PiB4LmlkID09PSBpZCk7CiAgaWYgKCFjKSByZXR1cm47CgogIC8vIExvYWQgZnVsbCBjaGFyYWN0ZXIgZnJvbSBzZXJ2ZXIKICB4aHJGZXRjaChCQVNFX1VSTCArICcvY2hhcmFjdGVyP2lkPScgKyBlbmNvZGVVUklDb21wb25lbnQoaWQpKS50aGVuKHI9PnIuanNvbigpKS50aGVuKGZ1bGwgPT4gewogICAgY29uc3QgcHJldiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjc2VsLXByZXZpZXcnKTsKICAgIHByZXYuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKCiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtbmFtZScpLnRleHRDb250ZW50ID0gZnVsbC5uYW1lOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWNsYXNzJykudGV4dENvbnRlbnQgPQogICAgICBgTGV2ZWwgJHtmdWxsLmxldmVsfSAke2Z1bGwucmFjZX0gJHtmdWxsLmNsc31gOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWFsaWduJykudGV4dENvbnRlbnQgPQogICAgICBgQWxpZ25tZW50OiAke2Z1bGwuYWxpZ24gfHwgJz8nfSAqIFNhdmVzOiBEZWF0aCAke2Z1bGwuc2F2ZXM/LmR8fCc/J30sIFdhbmRzICR7ZnVsbC5zYXZlcz8ud3x8Jz8nfSwgUGFyYWx5c2lzICR7ZnVsbC5zYXZlcz8ucHx8Jz8nfSwgQnJlYXRoICR7ZnVsbC5zYXZlcz8uYnx8Jz8nfSwgU3BlbGxzICR7ZnVsbC5zYXZlcz8uc3x8Jz8nfWA7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtaHAnKS50ZXh0Q29udGVudCA9IGAke2Z1bGwuaHB9LyR7ZnVsbC5tYXhocH1gOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWFjJykudGV4dENvbnRlbnQgPSBmdWxsLmFjOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWdvbGQnKS50ZXh0Q29udGVudCA9IGZ1bGwuZ29sZDsKCiAgICAvLyBTdGF0cyBncmlkCiAgICBjb25zdCBzdGF0cyA9IGZ1bGwuc3RhdHMgfHwge307CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtc3RhdHMnKS5pbm5lckhUTUwgPQogICAgICBbJ1NUUicsJ0RFWCcsJ0NPTicsJ0lOVCcsJ1dJUycsJ0NIQSddLm1hcChzID0+IHsKICAgICAgICBjb25zdCB2ID0gc3RhdHNbc10gfHwgMTA7CiAgICAgICAgY29uc3QgbSA9IE1hdGguZmxvb3IoKHYtMTApLzIpOwogICAgICAgIGNvbnN0IG1jID0gbSA+IDAgPyAnY29sb3I6IzZhOWE2YScgOiBtIDwgMCA/ICdjb2xvcjojOWE0YTRhJyA6ICcnOwogICAgICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic3RhdC1taW5pIj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNtbiI+JHtzfTwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0ic212Ij4ke3Z9PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzbW0iIHN0eWxlPSIke21jfSI+JHttPj0wPycrJyttOm19PC9kaXY+CiAgICAgICAgPC9kaXY+YDsKICAgICAgfSkuam9pbignJyk7CgogICAgLy8gSW52ZW50b3J5CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtaW52JykudGV4dENvbnRlbnQgPSAoZnVsbC5pbnYgfHwgW10pLmpvaW4oJywgJykgfHwgJ0VtcHR5JzsKCiAgICAvLyBSYWNpYWwgc3BlY2lhbHMKICAgIGNvbnN0IHNwZWNzID0gZnVsbC5zcGVjaWFscyB8fCBbXTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjcHJldi1zcGVjaWFscycpLnRleHRDb250ZW50ID0KICAgICAgc3BlY3MubGVuZ3RoID8gJyAnICsgc3BlY3Muam9pbignICogJykgOiAnJzsKICB9KTsKfQoKZnVuY3Rpb24gdXNlU2VsZWN0ZWRDaGFyKCkgewogIGlmICghY3NlbFNlbGVjdGVkSWQpIHJldHVybjsKICBjb25zdCBjID0gY3NlbENoYXJzLmZpbmQoeCA9PiB4LmlkID09PSBjc2VsU2VsZWN0ZWRJZCk7CiAgaWYgKCFjKSByZXR1cm47CgogIC8vIExvYWQgdGhlIGZ1bGwgY2hhcmFjdGVyCiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NoYXJhY3Rlcj9pZD0nICsgZW5jb2RlVVJJQ29tcG9uZW50KGNzZWxTZWxlY3RlZElkKSkudGhlbihyPT5yLmpzb24oKSkudGhlbihmdWxsID0+IHsKICAgIHBjID0gZnVsbDsKCiAgICBpZiAoY3NlbFBlbmRpbmdTYXZlKSB7CiAgICAgIC8vIENvbWluZyBmcm9tIExvYWQgR2FtZSAtLSByZXN0b3JlIHRoZSBmdWxsIHNhdmUgd2l0aCB0aGlzIGNoYXJhY3RlcgogICAgICBjb25zdCBkYXRhID0gY3NlbFBlbmRpbmdTYXZlLmRhdGE7CiAgICAgIHBjID0gZnVsbDsgLy8gdXNlIHNlbGVjdGVkIGNoYXIsIG5vdCB0aGUgc2F2ZWQgb25lCiAgICAgIG1vZHVsZVRleHQgPSBkYXRhLm1vZHVsZVRleHQgfHwgJyc7CiAgICAgIG1vZHVsZU5hbWUgPSBkYXRhLm1vZHVsZU5hbWUgfHwgJyc7CiAgICAgIGNob3NlblJ1bGVzID0gZGF0YS5jaG9zZW5SdWxlcyB8fCAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwogICAgICBwYXJ0eVBDcyA9IGRhdGEucGFydHlQQ3MgfHwge307CiAgICAgIC8vIEluamVjdCBvdXIgc2VsZWN0ZWQgY2hhcmFjdGVyIGFzIHRoZSBwbGF5ZXIncyBQQwogICAgICBwYXJ0eVBDc1twbGF5ZXJOYW1lXSA9IHBjOwogICAgICBoaXN0b3J5ID0gZGF0YS5oaXN0b3J5IHx8IFtdOwogICAgICBzeXN0ZW1Qcm9tcHQgPSBkYXRhLnN5c3RlbVByb21wdCB8fCAnJzsKICAgICAgaXNNdWx0aXBsYXllciA9IGRhdGEuaXNNdWx0aXBsYXllciB8fCBmYWxzZTsKICAgICAgLy8gUmVzdG9yZSBtZW1vcnkgc3lzdGVtCiAgICAgIG1lbW9yeVN1bW1hcnkgPSBkYXRhLm1lbW9yeVN1bW1hcnkgfHwgJyc7CiAgICAgIHdvcmxkU3RhdGUgPSBkYXRhLndvcmxkU3RhdGUgfHwgeyBucGNzX21ldDp7fSwgbG9jYXRpb25zX3Zpc2l0ZWQ6e30sIGl0ZW1zX2ZvdW5kOltdLCBwbG90X3BvaW50czpbXSwgZG9vcnNfb3BlbmVkOltdLCB0cmFwc19zcHJ1bmc6W10sIG1vbnN0ZXJzX2tpbGxlZDpbXSwgcXVlc3RzX2FjdGl2ZTpbXSwgd29ybGRfY2hhbmdlczpbXSB9OwogICAgICBwaW5uZWRGYWN0cyA9IGRhdGEucGlubmVkRmFjdHMgfHwgW107CiAgICAgIHR1cm5Db3VudCA9IGRhdGEudHVybkNvdW50IHx8IDA7CiAgICAgIG5wY1Byb2ZpbGVzID0gZGF0YS5ucGNQcm9maWxlcyB8fCB7fTsKICAgICAgbG9jYXRpb25BdG1vc3BoZXJlID0gZGF0YS5sb2NhdGlvbkF0bW9zcGhlcmUgfHwge307CiAgICAgIHNlc3Npb25Ub25lID0gZGF0YS5zZXNzaW9uVG9uZSB8fCAnZXhwbG9yYXRvcnknOwogICAgICBnbUJyaWVmaW5nID0gZGF0YS5nbUJyaWVmaW5nIHx8ICcnOwogICAgICBucGNLbm93bGVkZ2VNYXAgPSBkYXRhLm5wY0tub3dsZWRnZU1hcCB8fCB7fTsKICAgICAgcGFjaW5nSGlzdG9yeSA9IGRhdGEucGFjaW5nSGlzdG9yeSB8fCBbXTsKICAgICAgY3VycmVudFBhY2luZ1BoYXNlID0gZGF0YS5jdXJyZW50UGFjaW5nUGhhc2UgfHwgJ29wZW5pbmcnOwogICAgICBjb25zZXF1ZW5jZXMgPSBkYXRhLmNvbnNlcXVlbmNlcyB8fCBbXTsKICAgICAgaW5Db21iYXQgPSBkYXRhLmluQ29tYmF0IHx8IGZhbHNlOwogICAgICBjb21iYXRTdGF0ZSA9IGRhdGEuY29tYmF0U3RhdGUgfHwgeyByb3VuZDowLCBpbml0aWF0aXZlT3JkZXI6W10sIGFjdGl2ZUluZGV4OjAsIHBsYXllckFjdGlvbjonJywgbGFzdFJvdW5kU3VtbWFyeTonJyB9OwogICAgICBkdW5nZW9uVHVybnMgPSBkYXRhLmR1bmdlb25UdXJucyB8fCAwOwogICAgICB0b3JjaFR1cm5zTGVmdCA9IGRhdGEudG9yY2hUdXJuc0xlZnQgIT09IHVuZGVmaW5lZCA/IGRhdGEudG9yY2hUdXJuc0xlZnQgOiAxODsKICAgICAgaGFzTGFudGVybiA9IGRhdGEuaGFzTGFudGVybiB8fCBmYWxzZTsKICAgICAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSBkYXRhLmxhbnRlcm5PaWxGbGFza3NMZWZ0IHx8IDA7CiAgICAgIHJhdGlvbnNMZWZ0ID0gZGF0YS5yYXRpb25zTGVmdCB8fCAwOwogICAgICByZXN0RGVidCA9IGRhdGEucmVzdERlYnQgfHwgMDsKICAgICAgd2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyID0gZGF0YS53YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgfHwgMDsKCiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtbW9kJykudGV4dENvbnRlbnQgPSBtb2R1bGVOYW1lOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgc2hvd1Jvb21Db2RlKCk7CiAgICAgIHNob3coJ3MtZ2FtZScpOwogICAgICB1cGRhdGVIVUQoKTsKICAgICAgcmVuZGVyUGFydHlQYW5lbCgpOwogICAgICBjb25zdCBsb2cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbG9nJyk7CiAgICAgIGxvZy5pbm5lckhUTUwgPSAnJzsKICAgICAgKGRhdGEubG9nRW50cmllcyB8fCBbXSkuZm9yRWFjaChlID0+IGFkZEVudHJ5UmF3KGUuaHRtbCwgZS50eXBlLCBlLmF1dGhvcikpOwogICAgICBsb2cuc2Nyb2xsVG9wID0gbG9nLnNjcm9sbEhlaWdodDsKICAgICAgYWRkRW50cnlSYXcoJyBBZHZlbnR1cmUgcmVzdG9yZWQuIFBsYXlpbmcgYXMgPHN0cm9uZz4nICsgcGMubmFtZSArICc8L3N0cm9uZz4uJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgaWYgKGlzTXVsdGlwbGF5ZXIgJiYgcm9vbUNvZGUpIHN0YXJ0UG9sbGluZygpOwogICAgICBjc2VsUGVuZGluZ1NhdmUgPSBudWxsOwoKICAgIH0gZWxzZSBpZiAoY3NlbFBlbmRpbmdKb2luKSB7CiAgICAgIC8vIENvbWluZyBmcm9tIEpvaW4gUm9vbSAtLSB1c2UgdGhpcyBjaGFyYWN0ZXIgaW4gdGhlIHJvb20KICAgICAgY29uc3QgZGF0YSA9IGNzZWxQZW5kaW5nSm9pbi5kYXRhOwogICAgICByb29tQ29kZSA9IGRhdGEuY29kZTsKICAgICAgaXNNdWx0aXBsYXllciA9IHRydWU7CiAgICAgIGlzSG9zdCA9IGZhbHNlOwogICAgICBtb2R1bGVOYW1lID0gZGF0YS5tb2R1bGVOYW1lIHx8ICcnOwogICAgICBjaG9zZW5SdWxlcyA9IGRhdGEuY2hvc2VuUnVsZXMgfHwgJ09TRSBBZHZhbmNlZCBGYW50YXN5JzsKICAgICAgbW9kdWxlVGV4dCA9IGRhdGEubW9kdWxlVGV4dCB8fCAnJzsKICAgICAgbG9hZGVkTW9kdWxlRGF0YSA9IGRhdGEubW9kdWxlRGF0YSB8fCB7fTsKICAgICAgc3lzdGVtUHJvbXB0ID0gZGF0YS5zeXN0ZW1Qcm9tcHQgfHwgJyc7CgogICAgICBpZiAoZGF0YS5nYW1lQWN0aXZlKSB7CiAgICAgICAgcGFydHlQQ3MgPSBkYXRhLnBhcnR5UENzIHx8IHt9OwogICAgICAgIHBhcnR5UENzW3BsYXllck5hbWVdID0gcGM7CiAgICAgICAgaGlzdG9yeSA9IGRhdGEuaGlzdG9yeSB8fCBbXTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLW1vZCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgICBzaG93KCdzLWdhbWUnKTsKICAgICAgICB1cGRhdGVIVUQoKTsKICAgICAgICByZW5kZXJQYXJ0eVBhbmVsKCk7CiAgICAgICAgKGRhdGEubG9nRW50cmllcyB8fCBbXSkuZm9yRWFjaChlID0+IGFkZEVudHJ5UmF3KGUuaHRtbCwgZS50eXBlLCBlLmF1dGhvcikpOwogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsb2cnKS5zY3JvbGxUb3AgPSA5OTk5OTsKICAgICAgICAvLyBSZWdpc3RlciBjaGFyYWN0ZXIgaW4gcm9vbQogICAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9wbGF5ZXJfcmVhZHknLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lLCBwY30pfSk7CiAgICAgICAgc3RhcnRQb2xsaW5nKCk7CiAgICAgIH0gZWxzZSB7CiAgICAgICAgLy8gR2FtZSBub3Qgc3RhcnRlZCB5ZXQgLS0gZ28gdG8gY2hhciBzY3JlZW4gYnV0IHByZS1maWxsIHdpdGggc2VsZWN0ZWQgY2hhcgogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21wLWNoYXItbm90ZScpLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogICAgICAgIHNob3coJ3MtY2hhcicpOwogICAgICAgIGJ1aWxkQ2hhckNyZWF0ZSgpOwogICAgICAgIC8vIFByZS1wb3B1bGF0ZSBjaGFyIG5hbWUgYW5kIG1hcmsgYXMgcmVhZHkgd2l0aCB0aGlzIGNoYXJhY3RlcgogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbmFtZS1pbnAnKS52YWx1ZSA9IHBjLm5hbWU7CiAgICAgICAgLy8gUmVnaXN0ZXIgaW4gcm9vbQogICAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9wbGF5ZXJfcmVhZHknLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lLCBwY30pfSk7CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JlYWR5LWJ0bicpLnRleHRDb250ZW50ID0gJyBVc2luZyAnICsgcGMubmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJykuZGlzYWJsZWQgPSB0cnVlOwogICAgICAgIHN0YXJ0UG9sbGluZygpOwogICAgICB9CiAgICAgIGNzZWxQZW5kaW5nSm9pbiA9IG51bGw7CiAgICB9CiAgfSk7Cn0KCmZ1bmN0aW9uIHNob3dDaGFyQ3JlYXRlKCkgewogIC8vIEZyb20gY2hhciBzZWxlY3Qgc2NyZWVuLCBnbyB0byBmdWxsIGNoYXJhY3RlciBjcmVhdGlvbgogIGlmIChjc2VsUGVuZGluZ0pvaW4pIHsKICAgIGNvbnN0IGRhdGEgPSBjc2VsUGVuZGluZ0pvaW4uZGF0YTsKICAgIHJvb21Db2RlID0gZGF0YS5jb2RlOwogICAgaXNNdWx0aXBsYXllciA9IHRydWU7CiAgICBpc0hvc3QgPSBmYWxzZTsKICAgIG1vZHVsZU5hbWUgPSBkYXRhLm1vZHVsZU5hbWUgfHwgJyc7CiAgICBjaG9zZW5SdWxlcyA9IGRhdGEuY2hvc2VuUnVsZXMgfHwgJ09TRSBBZHZhbmNlZCBGYW50YXN5JzsKICAgIG1vZHVsZVRleHQgPSBkYXRhLm1vZHVsZVRleHQgfHwgJyc7CiAgICBsb2FkZWRNb2R1bGVEYXRhID0gZGF0YS5tb2R1bGVEYXRhIHx8IGxvYWRlZE1vZHVsZURhdGEgfHwge307CiAgICBzeXN0ZW1Qcm9tcHQgPSBkYXRhLnN5c3RlbVByb21wdCB8fCAnJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgICBjb25zdCBtcE5vdGUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbXAtY2hhci1ub3RlJyk7CiAgICBpZiAobXBOb3RlKSBtcE5vdGUuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBzdGFydFBvbGxpbmcoKTsKICB9IGVsc2UgaWYgKGNzZWxQZW5kaW5nU2F2ZSkgewogICAgLy8gQ3JlYXRpbmcgbmV3IGNoYXIgZm9yIGEgbG9hZGVkIHNhdmUgLS0gc3RpbGwgbG9hZCB0aGUgbW9kdWxlCiAgICBjb25zdCBkYXRhID0gY3NlbFBlbmRpbmdTYXZlLmRhdGE7CiAgICBtb2R1bGVOYW1lID0gZGF0YS5tb2R1bGVOYW1lIHx8ICcnOwogICAgbW9kdWxlVGV4dCA9IGRhdGEubW9kdWxlVGV4dCB8fCAnJzsKICAgIGNob3NlblJ1bGVzID0gZGF0YS5jaG9zZW5SdWxlcyB8fCAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NoYXItbW9kdWxlLWxibCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICB9CiAgY3NlbFBlbmRpbmdTYXZlID0gbnVsbDsKICBjc2VsUGVuZGluZ0pvaW4gPSBudWxsOwogIHNob3coJ3MtY2hhcicpOwogIGJ1aWxkQ2hhckNyZWF0ZSgpOwp9Cgphc3luYyBmdW5jdGlvbiBsb2FkRG5kbW9kTGlzdCgpIHsKICBjb25zdCBsaXN0RWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZG5kbW9kLWxpc3QnKTsKICBjb25zdCBlbXB0eUVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2RuZG1vZC1lbXB0eScpOwogIGxpc3RFbC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogIGxpc3RFbC5pbm5lckhUTUwgPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Y29sb3I6dmFyKC0tZGltKSI+TG9hZGluZy4uLjwvZGl2Pic7CgogIGxldCBtb2RzOwogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2xpc3RfbW9kdWxlcycpOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgLy8gU2VydmVyIHJldHVybnMge21vZHVsZXM6Wy4uLl19IC0tIHVud3JhcCBpdAogICAgbW9kcyA9IEFycmF5LmlzQXJyYXkoZGF0YSkgPyBkYXRhIDogKGRhdGEubW9kdWxlcyB8fCBbXSk7CiAgfSBjYXRjaChlKSB7CiAgICBsaXN0RWwuaW5uZXJIVE1MID0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2NvbG9yOiNjMDYwNjAiPkNvdWxkIG5vdCBsb2FkIG1vZHVsZSBsaXN0OiAnICsgZS5tZXNzYWdlICsgJzwvZGl2Pic7CiAgICByZXR1cm47CiAgfQoKICBpZiAoIW1vZHMubGVuZ3RoKSB7CiAgICBsaXN0RWwuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGlmIChlbXB0eUVsKSBlbXB0eUVsLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICByZXR1cm47CiAgfQogIGlmIChlbXB0eUVsKSBlbXB0eUVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgbGlzdEVsLmlubmVySFRNTCA9IG1vZHMubWFwKG0gPT4gewogICAgLy8gTm9ybWFsaXNlIGZpZWxkIG5hbWVzIC0tIHNlcnZlciB1c2VzIHtmaWxlLCB0aXRsZSwgbGV2ZWwsIHN5c3RlbX0KICAgIGNvbnN0IGZuYW1lICAgID0gbS5maWxlIHx8IG0uZmlsZW5hbWUgfHwgJyc7CiAgICBjb25zdCB0aXRsZSAgICA9IG0udGl0bGUgfHwgZm5hbWU7CiAgICBjb25zdCBsZXZlbCAgICA9IG0ubGV2ZWwgfHwgbS5sZXZlbF9yYW5nZSB8fCAnJzsKICAgIGNvbnN0IHN5c3RlbSAgID0gbS5zeXN0ZW0gfHwgJ09TRSc7CiAgICBjb25zdCBzYWZlVGl0bGUgPSB0aXRsZS5yZXBsYWNlKC8nL2csICImIzM5OyIpOwogICAgcmV0dXJuIGAKICAgIDxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEwcHggMTJweDtjdXJzb3I6cG9pbnRlcjsKICAgICAgdHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1czsiIGlkPSJtb2QtJHtmbmFtZX0iCiAgICAgIG9ubW91c2VlbnRlcj0idGhpcy5zdHlsZS5ib3JkZXJDb2xvcj0ndmFyKC0tZ29sZCknIgogICAgICBvbm1vdXNlbGVhdmU9InRoaXMuc3R5bGUuYm9yZGVyQ29sb3I9J3ZhcigtLWJvcmRlciknIgogICAgICBvbmNsaWNrPSJzZWxlY3REbmRtb2QoJyR7Zm5hbWV9JywnJHtzYWZlVGl0bGV9JykiPgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MThweDtjb2xvcjp2YXIoLS1pbmspO2ZvbnQtZmFtaWx5OidJTSBGZWxsIEVuZ2xpc2gnLHNlcmlmIj4ke3RpdGxlfTwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1kaW0pO21hcmdpbi10b3A6M3B4OyI+JHtzeXN0ZW19ICZuYnNwOyombmJzcDsgJHtsZXZlbCB8fCAnQW55IGxldmVsJ308L2Rpdj4KICAgIDwvZGl2PmA7CiAgfSkuam9pbignJyk7Cn0KCmFzeW5jIGZ1bmN0aW9uIHNlbGVjdERuZG1vZChmaWxlbmFtZSwgdGl0bGUpIHsKICAvLyBIaWdobGlnaHQgc2VsZWN0ZWQKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcjZG5kbW9kLWxpc3QgPiBkaXYnKS5mb3JFYWNoKGVsID0+IHsKICAgIGVsLnN0eWxlLmJvcmRlckNvbG9yID0gJ3ZhcigtLWJvcmRlciknOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICd2YXIoLS1iZyknOwogIH0pOwogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21vZC0nICsgZmlsZW5hbWUpOwogIGlmIChlbCkgeyBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICd2YXIoLS1nb2xkKSc7IGVsLnN0eWxlLmJhY2tncm91bmQgPSAncmdiYSgyMDEsMTY4LDc2LDAuMDgpJzsgfQoKICBzZWxlY3RlZERuZG1vZEZpbGUgPSBmaWxlbmFtZTsKICBtb2R1bGVOYW1lID0gdGl0bGU7CgogIC8vIFNob3cgbG9hZGluZyBzdGF0dXMgaW4gdGhlIG1vZHVsZSBjYXJkIGl0c2VsZgogIGNvbnN0IG1vZENhcmQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbW9kLScgKyBmaWxlbmFtZSk7CiAgaWYgKG1vZENhcmQpIG1vZENhcmQuaW5uZXJIVE1MICs9ICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1nb2xkKTttYXJnaW4tdG9wOjRweDsiPkxvYWRpbmcuLi48L2Rpdj4nOwoKICAvLyBMb2FkIHRoZSBtb2R1bGUgZGF0YSBmcm9tIHNlcnZlcgogIGxldCByZXN1bHQ7CiAgdHJ5IHsKICAgIHJlc3VsdCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9sb2FkX21vZHVsZT9maWxlPScgKyBlbmNvZGVVUklDb21wb25lbnQoZmlsZW5hbWUpKS50aGVuKHI9PnIuanNvbigpKTsKICB9IGNhdGNoKGUpIHsKICAgIGlmIChtb2RDYXJkKSBtb2RDYXJkLmlubmVySFRNTCArPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE0cHg7Y29sb3I6I2MwNjA2MDsiPkVycm9yOiAnICsgZS5tZXNzYWdlICsgJzwvZGl2Pic7CiAgICByZXR1cm47CiAgfQoKICBpZiAocmVzdWx0LmVycm9yKSB7CiAgICBpZiAobW9kQ2FyZCkgbW9kQ2FyZC5pbm5lckhUTUwgKz0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O2NvbG9yOiNjMDYwNjA7Ij5FcnJvcjogJyArIHJlc3VsdC5lcnJvciArICc8L2Rpdj4nOwogICAgcmV0dXJuOwogIH0KCiAgbW9kdWxlVGV4dCA9IHJlc3VsdC50ZXh0IHx8ICcnOwogIG1vZHVsZU5hbWUgPSByZXN1bHQudGl0bGUgfHwgJyc7CiAgbG9hZGVkTW9kdWxlRGF0YSA9IHJlc3VsdC5kYXRhIHx8IHt9OwogIGNvbnNvbGUubG9nKCdbc2VsZWN0RG5kbW9kXSBtb2R1bGVUZXh0IGxlbmd0aDonLCBtb2R1bGVUZXh0Lmxlbmd0aCwgJ3wgbW9kdWxlTmFtZTonLCBtb2R1bGVOYW1lLCAnfCBkYXRhIGtleXM6JywgT2JqZWN0LmtleXMobG9hZGVkTW9kdWxlRGF0YSkubGVuZ3RoKTsKICBpZiAoIW1vZHVsZVRleHQpIHsKICAgIGlmIChtb2RDYXJkKSBtb2RDYXJkLmlubmVySFRNTCArPSAnPGRpdiBzdHlsZT0iY29sb3I6I2MwNjA2MDtmb250LXNpemU6MTRweDsiPldhcm5pbmc6IG1vZHVsZSB0ZXh0IGVtcHR5ITwvZGl2Pic7CiAgfQoKICAvLyBQdXNoIG1vZHVsZSB0byByb29tIHNvIGd1ZXN0cyBnZXQgaXQgdG9vCiAgaWYgKHJvb21Db2RlKSB7CiAgICBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvdXBkYXRlX3Jvb20nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGU6cm9vbUNvZGUsIG1vZHVsZVRleHQsIG1vZHVsZU5hbWUsIGNob3NlblJ1bGVzLCBtb2R1bGVEYXRhOiBsb2FkZWRNb2R1bGVEYXRhfSl9KTsKICB9CgogIC8vIEVuYWJsZSB0aGUgQ29udGludWUgYnV0dG9uIGFuZCBzaG93IGNvbmZpcm1hdGlvbgogIHNldFRpbWVvdXQoKCkgPT4gewogICAgY29uc3QgYnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ25leHQtYnRuJyk7CiAgICBpZiAoYnRuKSB7IGJ0bi5kaXNhYmxlZCA9IGZhbHNlOyBidG4uc3R5bGUub3BhY2l0eSA9ICcxJzsgYnRuLnRleHRDb250ZW50ID0gJyAnICsgbW9kdWxlTmFtZSArICcgLS0gQ3JlYXRlIENoYXJhY3RlciAnOyB9CiAgfSwgNDAwKTsKfQoKZnVuY3Rpb24gcHJvY2VlZFRvQ2hhckNyZWF0ZSgpIHsKICBpZiAoIW1vZHVsZVRleHQgfHwgbW9kdWxlVGV4dC5sZW5ndGggPCAxMCkgewogICAgYWxlcnQoJ1BsZWFzZSBzZWxlY3QgYSBtb2R1bGUgZmlyc3QuJyk7CiAgICByZXR1cm47CiAgfQogIGNvbnN0IGNtbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKTsKICBpZiAoY21sKSBjbWwudGV4dENvbnRlbnQgPSBtb2R1bGVOYW1lOwogIHNob3coJ3MtY2hhcicpOwogIGJ1aWxkQ2hhckNyZWF0ZSgpOwp9CgpmdW5jdGlvbiBnb1RvTmV3R2FtZSgpIHsKICAvLyBJbml0aWFsaXNlIHNlc3Npb24gc3RhdGUgc2lsZW50bHkgKG5vIG5hbWUgcmVxdWlyZWQgeWV0KQogIGlmICghcGxheWVyTmFtZSkgcGxheWVyTmFtZSA9ICdBZHZlbnR1cmVyJzsKICBpc0hvc3QgPSBvbGxhbWFBdmFpbGFibGUgfHwgISFhcGlLZXk7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBjaG9zZW5SdWxlcyA9ICdPU0UnOwogIC8vIEF1dG8tZ2VuZXJhdGUgcm9vbSBjb2RlCiAgaWYgKCFyb29tQ29kZSkgYXV0b0dlbmVyYXRlUm9vbSgpOwogIHNob3coJ3MtbmV3Z2FtZScpOwogIGxvYWREbmRtb2RMaXN0KCk7Cn0KCmZ1bmN0aW9uIGdvVG9Mb2FkKCkgewogIGlmICghcGxheWVyTmFtZSkgcGxheWVyTmFtZSA9ICdBZHZlbnR1cmVyJzsKICBpc0hvc3QgPSBvbGxhbWFBdmFpbGFibGUgfHwgISFhcGlLZXk7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBzaG93TG9hZCgpOwp9CgpmdW5jdGlvbiBqb2luUm9vbUZyb21Mb2JieSgpIHsKICBjb25zdCBjb2RlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpLnZhbHVlLnRyaW0oKS50b1VwcGVyQ2FzZSgpOwogIGlmICghY29kZSkgeyBhbGVydCgnRW50ZXIgYSByb29tIGNvZGUuJyk7IHJldHVybjsgfQogIC8vIEluaXRpYWxpc2Ugc3RhdGUgZm9yIGd1ZXN0CiAgaWYgKCFwbGF5ZXJOYW1lKSBwbGF5ZXJOYW1lID0gJ1BsYXllcic7CiAgaXNIb3N0ID0gZmFsc2U7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBjaG9zZW5SdWxlcyA9ICdPU0UnOwogIC8vIFB1dCBjb2RlIGluIHRoZSBqb2luIGZpZWxkIGFuZCBjYWxsIGpvaW5Sb29tCiAgY29uc3Qgam9pbkZpZWxkID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpOwogIGlmIChqb2luRmllbGQpIGpvaW5GaWVsZC52YWx1ZSA9IGNvZGU7CiAgam9pblJvb20oKTsKfQoKYXN5bmMgZnVuY3Rpb24gYXV0b0dlbmVyYXRlUm9vbSgpIHsKICAvLyBTaWxlbnRseSBnZW5lcmF0ZSBhIHJvb20gY29kZSB3aXRob3V0IG5lZWRpbmcgYSBwbGF5ZXIgbmFtZSB5ZXQKICB0cnkgewogICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9jcmVhdGVfcm9vbScsIHttZXRob2Q6J1BPU1QnLAogICAgICBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7aG9zdDogcGxheWVyTmFtZSB8fCAnUm9vbSd9KX0pOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgaWYgKGRhdGEuY29kZSkgewogICAgICByb29tQ29kZSA9IGRhdGEuY29kZTsKICAgICAgaXNIb3N0ID0gdHJ1ZTsKICAgICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm9vbS1jb2RlLWRpc3AnKTsKICAgICAgaWYgKGVsKSBlbC50ZXh0Q29udGVudCA9IHJvb21Db2RlOwogICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgY2hlY2tOZ3Jva1N0YXR1cygpOwogICAgfQogIH0gY2F0Y2goZSkgeyBjb25zb2xlLmxvZygnYXV0b0dlbmVyYXRlUm9vbSBlcnJvcjonLCBlKTsgfQp9CgpmdW5jdGlvbiBjb3B5Um9vbUNvZGVOZXdHYW1lKCkgewogIGlmICghcm9vbUNvZGUpIHJldHVybjsKICBuYXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChyb29tQ29kZSkudGhlbigoKSA9PiB7CiAgICAvLyBicmllZiBmZWVkYmFjawogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm9vbS1jb2RlLWRpc3AnKTsKICAgIGlmIChlbCkgeyBjb25zdCBvcmlnID0gZWwudGV4dENvbnRlbnQ7IGVsLnRleHRDb250ZW50ID0gJ0NvcGllZCEnOyBzZXRUaW1lb3V0KCgpPT5lbC50ZXh0Q29udGVudD1vcmlnLDEyMDApOyB9CiAgfSkuY2F0Y2goKCkgPT4gcHJvbXB0KCdSb29tIGNvZGU6Jywgcm9vbUNvZGUpKTsKfQoKZnVuY3Rpb24gdG9nZ2xlSW52ZW50b3J5KCkgewogIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ludi1wYW5lbCcpOwogIGNvbnN0IGFycm93ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ludi10b2dnbGUtYXJyb3cnKTsKICBpZiAoIXBhbmVsKSByZXR1cm47CiAgY29uc3Qgb3BlbiA9IHBhbmVsLnN0eWxlLmRpc3BsYXkgIT09ICdub25lJzsKICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gb3BlbiA/ICdub25lJyA6ICdibG9jayc7CiAgaWYgKGFycm93KSBhcnJvdy5pbm5lckhUTUwgPSBvcGVuID8gJycgOiAnJzsKfQoKZnVuY3Rpb24gdXBkYXRlU3RhdHVzUGFuZWwoKSB7CiAgLy8gSHVuZ2VyIC0tIGhvdXNlIHJ1bGU6IC0xIGF0dGFjay9zYXZlcyBwZXIgZGF5IGFmdGVyIGRheSAzIHdpdGhvdXQgZm9vZAogIGNvbnN0IGh1bmdlckVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2h1bmdlci1iYXInKTsKICBpZiAoaHVuZ2VyRWwpIHsKICAgIGlmIChzdGFydmF0aW9uUGVuYWx0eSA+PSAzKSB7CiAgICAgIGh1bmdlckVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwMjAyMCI+U3RhcnZpbmcgKC0nICsgc3RhcnZhdGlvblBlbmFsdHkgKyAnIGF0dGFja3Mvc2F2ZXMpPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHN0YXJ2YXRpb25QZW5hbHR5ID4gMCkgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPkh1bmdyeSAoLScgKyBzdGFydmF0aW9uUGVuYWx0eSArICcgYXR0YWNrcy9zYXZlcyk8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAoZGF5c1dpdGhvdXRGb29kID4gMCkgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPkh1bmdyeSAoZGF5ICcgKyBkYXlzV2l0aG91dEZvb2QgKyAnLCBwZW5hbHR5IHN0YXJ0cyBkYXkgNCk8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAocmF0aW9uc0xlZnQgPT09IDEpIHsKICAgICAgaHVuZ2VyRWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA5MDQwIj5GZWQgKDEgcmF0aW9uIGxlZnQpPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHJhdGlvbnNMZWZ0ID09PSAwKSB7CiAgICAgIGh1bmdlckVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwOTA0MCI+Tm8gcmF0aW9ucyAocGVuYWx0eSBhZnRlciAzIGRheXMpPC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiM2YTlhNmEiPkZlZDwvc3Bhbj4nOwogICAgfQogIH0KICAvLyBEdW5nZW9uIHJlc3QgaW5kaWNhdG9yIC0tIG9ubHkgc2hvd24gd2hlbiBpbiBhIGR1bmdlb24gKGR1bmdlb25fbGV2ZWwgPj0gMSkKICBjb25zdCByZXN0Um93ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0YXR1cy1kdW5nZW9uLXJlc3QnKTsKICBjb25zdCByZXN0QmFyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2R1bmdlb24tcmVzdC1iYXInKTsKICBjb25zdCBpbkR1bmdlb24gPSBpc0luRHVuZ2VvbigpOwogIGlmIChyZXN0Um93KSByZXN0Um93LnN0eWxlLmRpc3BsYXkgPSBpbkR1bmdlb24gPyAnJyA6ICdub25lJzsKICBpZiAocmVzdEJhciAmJiBpbkR1bmdlb24pIHsKICAgIGlmICh0dXJuc1dpdGhvdXRSZXN0ID49IDYpIHsKICAgICAgcmVzdEJhci5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPlJlc3QgbmVlZGVkISAoJyArIHR1cm5zV2l0aG91dFJlc3QgKyAnIHR1cm5zKTwvc3Bhbj4nOwogICAgfSBlbHNlIGlmICh0dXJuc1dpdGhvdXRSZXN0ID49IDQpIHsKICAgICAgcmVzdEJhci5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPicgKyB0dXJuc1dpdGhvdXRSZXN0ICsgJy82IHR1cm5zIChyZXN0IHNvb24pPC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICByZXN0QmFyLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6IzZhOWE2YSI+JyArIHR1cm5zV2l0aG91dFJlc3QgKyAnLzYgdHVybnM8L3NwYW4+JzsKICAgIH0KICB9CiAgLy8gTGlnaHQgLSBvbmx5IHNob3cgd2hlbiBhIGxpZ2h0IHNvdXJjZSBpcyBBQ1RJVkVMWSBMSVQgb3IgY2hhcmFjdGVyIGlzIGluIGRhcmtuZXNzCiAgY29uc3QgbGlnaHRSb3cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RhdHVzLWxpZ2h0Jyk7CiAgY29uc3QgbGlnaHRFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsaWdodC1zdGF0dXMnKTsKICAvLyB0b3JjaExpdCA9IHRvcmNoIGhhcyBiZWVuIGRlbGliZXJhdGVseSB1c2VkIGFuZCBpcyBjb3VudGluZyBkb3duCiAgLy8gT25seSBzaG93IGRhcmtuZXNzIHdhcm5pbmcgaWYgdGhleSd2ZSBlbnRlcmVkIHNvbWV3aGVyZSBkYXJrICh0b3JjaFR1cm5zTGVmdCBldmVyIGNvdW50ZWQpCiAgY29uc3QgbGlnaHRBY3RpdmUgPSAodG9yY2hMaXQgJiYgdG9yY2hUdXJuc0xlZnQgPiAwKSB8fCAobGFudGVybkxpdCAmJiBoYXNMYW50ZXJuKSB8fCAodG9yY2hFdmVyVXNlZCAmJiAhaXNDYXJyeWluZ0xpZ2h0KTsKICBpZiAobGlnaHRSb3cpIGxpZ2h0Um93LnN0eWxlLmRpc3BsYXkgPSBsaWdodEFjdGl2ZSA/ICcnIDogJ25vbmUnOwogIGlmIChsaWdodEVsICYmIGxpZ2h0QWN0aXZlKSB7CiAgICBpZiAoIWlzQ2FycnlpbmdMaWdodCkgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwNjA2MCI+REFSS05FU1M8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAodG9yY2hMaXQgJiYgdG9yY2hUdXJuc0xlZnQgPiAwICYmIHRvcmNoVHVybnNMZWZ0IDw9IDIpIHsKICAgICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPlRvcmNoOiAnICsgdG9yY2hUdXJuc0xlZnQgKyAnIHR1cm5zIGxlZnQhPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHRvcmNoTGl0ICYmIHRvcmNoVHVybnNMZWZ0ID4gMCkgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICdUb3JjaDogJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJucyc7CiAgICB9IGVsc2UgaWYgKGxhbnRlcm5MaXQgJiYgaGFzTGFudGVybikgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICdMYW50ZXJuOiAnICsgbGFudGVybk9pbEZsYXNrc0xlZnQgKyAnIGZsYXNrKHMpJzsKICAgIH0KICB9CiAgLy8gQWN0aXZlIGVmZmVjdHMgKGNoYXJtLCBwb2lzb24sIHNwZWxsIHRpbWVycyBldGMpCiAgdXBkYXRlQWN0aXZlRWZmZWN0cygpOwp9CgpmdW5jdGlvbiBhZGRFZmZlY3QobmFtZSwgdHVybnMsIGNvbG9yKSB7CiAgY29sb3IgPSBjb2xvciB8fCAnI2MwOTA0MCc7CiAgYWN0aXZlRWZmZWN0cyA9IGFjdGl2ZUVmZmVjdHMuZmlsdGVyKGUgPT4gZS5uYW1lICE9PSBuYW1lKTsKICBhY3RpdmVFZmZlY3RzLnB1c2goe25hbWUsIHR1cm5zTGVmdDogdHVybnMsIGNvbG9yfSk7CiAgdXBkYXRlQWN0aXZlRWZmZWN0cygpOwp9CgpmdW5jdGlvbiB0aWNrRWZmZWN0cygpIHsKICBhY3RpdmVFZmZlY3RzID0gYWN0aXZlRWZmZWN0cy5maWx0ZXIoZSA9PiB7CiAgICBlLnR1cm5zTGVmdC0tOwogICAgaWYgKGUudHVybnNMZWZ0IDw9IDApIHsKICAgICAgYWRkRW50cnlSYXcoJ0VmZmVjdCBlbmRlZDogPHN0cm9uZz4nICsgZS5uYW1lICsgJzwvc3Ryb25nPicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIHJldHVybiBmYWxzZTsKICAgIH0KICAgIHJldHVybiB0cnVlOwogIH0pOwogIHVwZGF0ZUFjdGl2ZUVmZmVjdHMoKTsKfQoKZnVuY3Rpb24gdXBkYXRlQWN0aXZlRWZmZWN0cygpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhY3RpdmUtZWZmZWN0cycpOwogIGlmICghZWwpIHJldHVybjsKICBpZiAoIWFjdGl2ZUVmZmVjdHMubGVuZ3RoKSB7IGVsLmlubmVySFRNTCA9ICcnOyByZXR1cm47IH0KICBlbC5pbm5lckhUTUwgPSBhY3RpdmVFZmZlY3RzLm1hcChlID0+CiAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjEzcHg7Y29sb3I6JyArIGUuY29sb3IgKyAnO3BhZGRpbmc6MXB4IDA7Ij4nICsgZS5uYW1lICsgJzogJyArIGUudHVybnNMZWZ0ICsgJyB0dXJuczwvZGl2PicKICApLmpvaW4oJycpOwp9CgpmdW5jdGlvbiB0ZXN0Q29ubmVjdGlvbigpIHsKICAvLyBUZXN0IHRoZSBzYW1lIFVSTCBwYXR0ZXJuIHRoYXQgeGhyRmV0Y2ggdXNlcwogIGNvbnN0IHVybCA9IEJBU0VfVVJMICsgJy9waW5nJzsKICBhbGVydCgnVGVzdGluZyBVUkw6ICcgKyB1cmwpOwogIGNvbnN0IHhociA9IG5ldyBYTUxIdHRwUmVxdWVzdCgpOwogIHhoci5vcGVuKCdHRVQnLCB1cmwsIHRydWUpOwogIHhoci5vbmxvYWQgPSAoKSA9PiBhbGVydCgnT0s6ICcgKyB4aHIucmVzcG9uc2VUZXh0KTsKICB4aHIub25lcnJvciA9ICgpID0+IGFsZXJ0KCdGQUlMRUQgZm9yOiAnICsgdXJsKTsKICB4aHIuc2VuZCgpOwp9CgpmdW5jdGlvbiB0b2dnbGVBcGlLZXkoKSB7CiAgY29uc3QgYm94ICAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXBpLWtleS1ib3gnKTsKICBjb25zdCBhcnJvdyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhcGktYXJyb3cnKTsKICBjb25zdCBvcGVuICA9IGJveC5zdHlsZS5kaXNwbGF5ID09PSAnZmxleCc7CiAgYm94LnN0eWxlLmRpc3BsYXkgPSBvcGVuID8gJ25vbmUnIDogJ2ZsZXgnOwogIGlmIChhcnJvdykgYXJyb3cuaW5uZXJIVE1MID0gb3BlbiA/ICcmIzk2NjA7JyA6ICcmIzk2NTA7JzsKfQpmdW5jdGlvbiBvbkFwaUtleVR5cGVkKHZhbCkgewogIGNvbnN0IHN0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktc3RhdHVzJyk7CiAgaWYgKCFzdCkgcmV0dXJuOwogIGlmICghdmFsKSB7IHN0LnRleHRDb250ZW50ID0gJyc7IHJldHVybjsgfQogIGlmICh2YWwuc3RhcnRzV2l0aCgnc2stYW50LScpKSB7CiAgICBzdC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsgc3QudGV4dENvbnRlbnQgPSAnVmFsaWQga2V5IGZvcm1hdCc7CiAgfSBlbHNlIHsKICAgIHN0LnN0eWxlLmNvbG9yID0gJyNjMDkwNDAnOyBzdC50ZXh0Q29udGVudCA9ICdLZXkgc2hvdWxkIHN0YXJ0IHdpdGggc2stYW50LS4uLic7CiAgfQp9CmZ1bmN0aW9uIGFwcGx5QXBpS2V5KCkgewogIGNvbnN0IGlucCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdrZXktaW5wJyk7CiAgY29uc3Qgc3QgID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktc3RhdHVzJyk7CiAgaWYgKCFpbnApIHJldHVybjsKICBhcGlLZXkgPSBpbnAudmFsdWUudHJpbSgpOwogIGlmIChhcGlLZXkpIHsKICAgIGlmIChzdCkgeyBzdC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsgc3QudGV4dENvbnRlbnQgPSAnU2F2ZWQg4oCUIENsYXVkZSBIYWlrdSBwYXJzaW5nIGFjdGl2ZSc7IH0KICB9IGVsc2UgewogICAgaWYgKHN0KSB7IHN0LnN0eWxlLmNvbG9yID0gJ3ZhcigtLWluay1kaW0pJzsgc3QudGV4dENvbnRlbnQgPSAnQ2xlYXJlZCDigJQgT2xsYW1hIG9ubHknOyB9CiAgfQp9CmZ1bmN0aW9uIGdvSG9tZSgpIHsKICBjb25zdCBuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1uYW1lLWlucCcpLnZhbHVlLnRyaW0oKTsKICBjb25zdCBrID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2tleS1pbnAnKS52YWx1ZS50cmltKCk7CiAgY29uc29sZS5sb2coJ1tnb0hvbWVdIG5hbWU6JywgbiwgJ2tleTonLCAhIWssICdvbGxhbWE6Jywgb2xsYW1hQXZhaWxhYmxlLCAnX3NlcnZlcjonLCB3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZSk7CiAgcGxheWVyTmFtZSA9IG4gfHwgJ0FkdmVudHVyZXInOwogIGlmIChrKSB7IGFwaUtleSA9IGs7IH0KICBpc0hvc3QgPSAhIShrIHx8IG9sbGFtYUF2YWlsYWJsZSk7CiAgY29uc29sZS5sb2coJ1tnb0hvbWVdIGlzSG9zdDonLCBpc0hvc3QsICduYXZpZ2F0aW5nIHRvIHMtaG9tZScpOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdob21lLXdlbGNvbWUnKS50ZXh0Q29udGVudCA9ICdXZWxjb21lLCAnICsgcGxheWVyTmFtZSArICcuIFdoYXQgd291bGQgeW91IGxpa2UgdG8gZG8/JzsKICBzaG93KCdzLWhvbWUnKTsKICBjb25zb2xlLmxvZygnW2dvSG9tZV0gZG9uZScpOwp9CgpmdW5jdGlvbiBzaG93TmV3R2FtZSgpIHsKICBpZiAoIXJvb21Db2RlKSBhdXRvR2VuZXJhdGVSb29tKCk7CiAgc2hvdygncy1uZXdnYW1lJyk7CiAgbG9hZERuZG1vZExpc3QoKTsgLy8gYXV0by1wb3B1bGF0ZSBtb2R1bGUgbGlzdCBvbiBldmVyeSB2aXNpdAp9CgpmdW5jdGlvbiBzaG93TG9hZCgpIHsKICB4aHJGZXRjaChCQVNFX1VSTCArICcvc2F2ZXMnKS50aGVuKHI9PnIuanNvbigpKS50aGVuKHJlc3AgPT4gewogICAgY29uc3Qgc2F2ZXMgPSBBcnJheS5pc0FycmF5KHJlc3ApID8gcmVzcCA6IChyZXNwLnNhdmVzIHx8IFtdKTsKICAgIGNvbnN0IHdyYXAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbG9hZC13cmFwJyk7CiAgICBjb25zdCBsaXN0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NhdmUtbGlzdC1lbCcpOwogICAgd3JhcC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogICAgaWYgKCFzYXZlcy5sZW5ndGgpIHsgbGlzdC5pbm5lckhUTUwgPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Y29sb3I6dmFyKC0taW5rLWRpbSkiPk5vIHNhdmVkIGdhbWVzIGZvdW5kLjwvZGl2Pic7IHJldHVybjsgfQogICAgbGlzdC5pbm5lckhUTUwgPSBzYXZlcy5tYXAocyA9PgogICAgICBgPGRpdiBjbGFzcz0ic2F2ZS1pdGVtIj4KICAgICAgICA8ZGl2IGNsYXNzPSJzaS1pbmZvIj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNpLW5hbWUiPiR7cy5tb2R1bGVOYW1lfHwnQWR2ZW50dXJlJ308L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNpLW1ldGEiPiR7cy5wY05hbWV9ICogJHtzLnBjQ2xhc3N9ICogJHtuZXcgRGF0ZShzLnNhdmVkQXQpLnRvTG9jYWxlU3RyaW5nKCl9PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2dhcDo2cHg7Ij4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biIgb25jbGljaz0ibG9hZFNhdmUoJyR7cy5pZH0nKSIgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O3BhZGRpbmc6NHB4IDEwcHg7Ij5Mb2FkPC9idXR0b24+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9ImRlbGV0ZVNhdmUoJyR7cy5pZH0nKSIgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O3BhZGRpbmc6NHB4IDEwcHg7Ym9yZGVyLWNvbG9yOiM2YTIwMjA7Y29sb3I6I2MwNjA2MDsiPjwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj5gCiAgICApLmpvaW4oJycpOwogIH0pOwp9CgpmdW5jdGlvbiBsb2FkU2F2ZShpZCkgewogIHhockZldGNoKEJBU0VfVVJMICsgJy9sb2FkP2lkPScgKyBpZCkudGhlbihyPT5yLmpzb24oKSkudGhlbihkYXRhID0+IHsKICAgIGlmIChkYXRhLmVycm9yKSB7IGFsZXJ0KGRhdGEuZXJyb3IpOyByZXR1cm47IH0KICAgIC8vIFJvdXRlIHRocm91Z2ggY2hhcmFjdGVyIHNlbGVjdCBzY3JlZW4KICAgIGNvbnN0IG1vZExhYmVsID0gZGF0YS5tb2R1bGVOYW1lIHx8ICdBZHZlbnR1cmUnOwogICAgc2hvd0NoYXJTZWxlY3QoCiAgICAgICdTZWxlY3QgdGhlIGNoYXJhY3RlciB5b3Ugd2FudCB0byBwbGF5IHRoaXMgYWR2ZW50dXJlIHdpdGgsIG9yIGNyZWF0ZSBhIG5ldyBvbmUuJywKICAgICAgbW9kTGFiZWwsCiAgICAgIHt0eXBlOiAnc2F2ZScsIGRhdGE6IGRhdGF9CiAgICApOwogIH0pOwp9CgpmdW5jdGlvbiBkZWxldGVTYXZlKGlkKSB7CiAgaWYgKCFjb25maXJtKCdEZWxldGUgdGhpcyBzYXZlPycpKSByZXR1cm47CiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2RlbGV0ZV9zYXZlP2lkPScgKyBpZCwge21ldGhvZDonUE9TVCd9KS50aGVuKCgpID0+IHNob3dMb2FkKCkpOwp9Cgphc3luYyBmdW5jdGlvbiBjaGVja05ncm9rU3RhdHVzKCkgewogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL25ncm9rX3N0YXR1cycpOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmdyb2stc3RhdHVzLXR4dCcpOwogICAgaWYgKCFlbCkgcmV0dXJuOwogICAgaWYgKGRhdGEuYWN0aXZlICYmIGRhdGEudXJsKSB7CiAgICAgIG5ncm9rUHVibGljVXJsID0gZGF0YS51cmw7CiAgICAgIGVsLmlubmVySFRNTCA9CiAgICAgICAgJzxzdHJvbmcgc3R5bGU9ImNvbG9yOnZhcigtLWdvbGQpIj5JbnRlcm5ldCBhY2Nlc3MgYWN0aXZlITwvc3Ryb25nPjxicj4nICsKICAgICAgICAnRnJpZW5kcyBhbnl3aGVyZSBjYW4gam9pbi4gU2hhcmUgdGhpcyBsaW5rOjxicj4nICsKICAgICAgICAnPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLWluayk7Zm9udC1zaXplOjE2cHg7bGV0dGVyLXNwYWNpbmc6MC41cHg7Ij4nICsgZGF0YS51cmwgKyAnPC9zcGFuPicgKwogICAgICAgICcgPGJ1dHRvbiBvbmNsaWNrPSJjb3B5Tmdyb2tVcmwoKSIgc3R5bGU9ImJhY2tncm91bmQ6bm9uZTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y29sb3I6dmFyKC0taW5rLWRpbSk7Y3Vyc29yOnBvaW50ZXI7cGFkZGluZzoycHggOHB4O2ZvbnQtc2l6ZToxNHB4O21hcmdpbi1sZWZ0OjZweDsiPkNvcHk8L2J1dHRvbj48YnI+JyArCiAgICAgICAgJzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+UGxheWVycyBvcGVuIHRoYXQgVVJMIGluIHRoZWlyIGJyb3dzZXIsIHRoZW4gZW50ZXIgdGhlIHJvb20gY29kZS48L3NwYW4+JzsKICAgIH0gZWxzZSB7CiAgICAgIGVsLmlubmVySFRNTCA9CiAgICAgICAgJ0xBTiBvbmx5IC0tIGZyaWVuZHMgb24gdGhlIHNhbWUgbmV0d29yayBjYW4gY29ubmVjdC48YnI+JyArCiAgICAgICAgJzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+Rm9yIGludGVybmV0IHBsYXk6IGluc3RhbGwgJyArCiAgICAgICAgJzxhIGhyZWY9Imh0dHBzOi8vbmdyb2suY29tIiBzdHlsZT0iY29sb3I6dmFyKC0tZ29sZCkiPm5ncm9rPC9hPiwgJyArCiAgICAgICAgJ3RoZW4gcnVuIDxjb2RlIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLXBhbmVsKTtwYWRkaW5nOjFweCA1cHg7Ij5uZ3JvayBodHRwIDgwODA8L2NvZGU+IGluIGEgdGVybWluYWwgYmVmb3JlIHN0YXJ0aW5nIHRoZSBnYW1lLjwvc3Bhbj4nOwogICAgfQogIH0gY2F0Y2goZSkgewogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmdyb2stc3RhdHVzLXR4dCcpOwogICAgaWYgKGVsKSBlbC50ZXh0Q29udGVudCA9ICdMQU4gb25seSAoY291bGQgbm90IGNoZWNrIGludGVybmV0IHR1bm5lbCBzdGF0dXMpJzsKICB9Cn0KCmZ1bmN0aW9uIGNvcHlOZ3Jva1VybCgpIHsKICBpZiAoIW5ncm9rUHVibGljVXJsKSByZXR1cm47CiAgdHJ5IHsKICAgIG5hdmlnYXRvci5jbGlwYm9hcmQud3JpdGVUZXh0KG5ncm9rUHVibGljVXJsKS50aGVuKCgpID0+IHsKICAgICAgY29uc3QgYnRuID0gZXZlbnQudGFyZ2V0OwogICAgICBjb25zdCBvcmlnID0gYnRuLnRleHRDb250ZW50OwogICAgICBidG4udGV4dENvbnRlbnQgPSAnQ29waWVkISc7CiAgICAgIHNldFRpbWVvdXQoKCkgPT4gYnRuLnRleHRDb250ZW50ID0gb3JpZywgMTUwMCk7CiAgICB9KTsKICB9IGNhdGNoKGUpIHsKICAgIHByb21wdCgnQ29weSB0aGlzIFVSTDonLCBuZ3Jva1B1YmxpY1VybCk7CiAgfQp9CgpmdW5jdGlvbiBnZW5lcmF0ZVJvb20oKSB7CiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NyZWF0ZV9yb29tJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtob3N0OiBwbGF5ZXJOYW1lfSl9KQogICAgLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZGF0YSA9PiB7CiAgICAgIHJvb21Db2RlID0gZGF0YS5jb2RlOwogICAgICBpc011bHRpcGxheWVyID0gdHJ1ZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jvb20tY29kZS1kaXNwJykudGV4dENvbnRlbnQgPSByb29tQ29kZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jvb20tc2hhcmUtd3JhcCcpLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICAgIHJlbmRlclBsYXllclNsb3RzKFt7bmFtZTpwbGF5ZXJOYW1lLCByZWFkeTpmYWxzZX1dKTsKICAgICAgc3RhcnRQb2xsaW5nKCk7CiAgICAgIGNoZWNrTmdyb2tTdGF0dXMoKTsgIC8vIFNob3cgbmdyb2sgVVJMIG9yIExBTiBpbnN0cnVjdGlvbnMKICAgIH0pOwp9CgpmdW5jdGlvbiBqb2luUm9vbSgpIHsKICBjb25zdCBjb2RlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpLnZhbHVlLnRyaW0oKS50b1VwcGVyQ2FzZSgpOwogIGlmICghY29kZSkgeyBhbGVydCgnRW50ZXIgYSByb29tIGNvZGUuJyk7IHJldHVybjsgfQogIHhockZldGNoKEJBU0VfVVJMICsgJy9qb2luX3Jvb20nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGUsIHBsYXllcjogcGxheWVyTmFtZX0pfSkKICAgIC50aGVuKGRhdGEgPT4gewogICAgICBpZiAoZGF0YS5lcnJvcikgeyBhbGVydChkYXRhLmVycm9yKTsgcmV0dXJuOyB9CiAgICAgIC8vIEFsd2F5cyByb3V0ZSB0aHJvdWdoIGNoYXJhY3RlciBzZWxlY3Qgc2NyZWVuCiAgICAgIGRhdGEuY29kZSA9IGNvZGU7CiAgICAgIGNvbnN0IG1vZExhYmVsID0gZGF0YS5tb2R1bGVOYW1lIHx8ICdBZHZlbnR1cmUnOwogICAgICBzaG93Q2hhclNlbGVjdCgKICAgICAgICAnU2VsZWN0IHRoZSBjaGFyYWN0ZXIgeW91IHdhbnQgdG8gYnJpbmcgaW50byB0aGlzIGFkdmVudHVyZSwgb3IgY3JlYXRlIGEgbmV3IG9uZS4nLAogICAgICAgIG1vZExhYmVsLAogICAgICAgIHt0eXBlOiAnam9pbicsIGRhdGE6IGRhdGF9CiAgICAgICk7CiAgICB9KTsKfQoKZnVuY3Rpb24gcmVuZGVyUGxheWVyU2xvdHMocGxheWVycykgewogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1zbG90cy1saXN0Jyk7CiAgaWYgKCFlbCkgcmV0dXJuOwogIGVsLmlubmVySFRNTCA9IHBsYXllcnMubWFwKChwLGkpID0+CiAgICBgPGRpdiBjbGFzcz0icGxheWVyLXNsb3QiPgogICAgICA8ZGl2IGNsYXNzPSJwZG90ICR7cC5yZWFkeT8nb24nOid3YWl0J30iIHN0eWxlPSJiYWNrZ3JvdW5kOiR7UExBWUVSX0NPTE9SU1tpJVBMQVlFUl9DT0xPUlMubGVuZ3RoXX07JHtwLnJlYWR5PycnOicnfSI+PC9kaXY+CiAgICAgIDxzcGFuIHN0eWxlPSJmb250LXNpemU6MTdweDtjb2xvcjoke1BMQVlFUl9DT0xPUlNbaSVQTEFZRVJfQ09MT1JTLmxlbmd0aF19Ij4ke3AubmFtZX0ke3AubmFtZT09PXBsYXllck5hbWU/JyAoeW91KSc6Jyd9PC9zcGFuPgogICAgICAke3AucmVhZHk/JzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+PC9zcGFuPic6Jyd9CiAgICA8L2Rpdj5gCiAgKS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gc3RhcnRQb2xsaW5nKCkgewogIGlmIChwb2xsVGltZXIpIGNsZWFySW50ZXJ2YWwocG9sbFRpbWVyKTsKICBwb2xsVGltZXIgPSBzZXRJbnRlcnZhbChkb1BvbGwsIDIwMDApOwp9CgpmdW5jdGlvbiBkb1BvbGwoKSB7CiAgaWYgKCFyb29tQ29kZSkgcmV0dXJuOwogIGZldGNoKGAvcG9sbD9yb29tPSR7cm9vbUNvZGV9JnBsYXllcj0ke2VuY29kZVVSSUNvbXBvbmVudChwbGF5ZXJOYW1lKX0mc2VxPSR7bGFzdFNlcX1gKQogICAgLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZGF0YSA9PiB7CiAgICAgIGlmIChkYXRhLmVycm9yKSByZXR1cm47CiAgICAgIGxhc3RTZXEgPSBkYXRhLnNlcSB8fCBsYXN0U2VxOwoKICAgICAgLy8gVXBkYXRlIHBsYXllciBsaXN0CiAgICAgIGlmIChkYXRhLnBsYXllcnMgJiYgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1zbG90cy1saXN0JykpIHsKICAgICAgICByZW5kZXJQbGF5ZXJTbG90cyhkYXRhLnBsYXllcnMpOwogICAgICB9CgogICAgICAvLyBQYXJ0eSBzdGF0dXMgaW4gY2hhciBjcmVhdGUKICAgICAgaWYgKGRhdGEucGxheWVycyAmJiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGFydHktc3RhdHVzLXdyYXAnKSkgewogICAgICAgIHJlbmRlclBhcnR5U3RhdHVzKGRhdGEucGxheWVycyk7CiAgICAgIH0KCiAgICAgIC8vIE5ldyBjaGF0L2dhbWUgbWVzc2FnZXMKICAgICAgaWYgKGRhdGEubmV3TWVzc2FnZXMpIHsKICAgICAgICBkYXRhLm5ld01lc3NhZ2VzLmZvckVhY2gobSA9PiB7CiAgICAgICAgICBpZiAobS5hdXRob3IgIT09IHBsYXllck5hbWUgfHwgbS50eXBlID09PSAnZ20nIHx8IG0udHlwZSA9PT0gJ3N5c3RlbScpIHsKICAgICAgICAgICAgYWRkRW50cnlSYXcobS5odG1sLCBtLnR5cGUsIG0uYXV0aG9yKTsKICAgICAgICAgIH0KICAgICAgICB9KTsKICAgICAgfQoKICAgICAgLy8gU3RhdGUgdXBkYXRlcwogICAgICBpZiAoZGF0YS5nYW1lU3RhdGUpIHsKICAgICAgICBjb25zdCBncyA9IGRhdGEuZ2FtZVN0YXRlOwogICAgICAgIGlmIChncy5sb2MpIHsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NjZW5lLWxvYycpLnRleHRDb250ZW50ID0gZ3MubG9jOyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2NlbmUtdGFnJykudGV4dENvbnRlbnQgPSBncy5sb2N0YWd8fCcnOyB9CiAgICAgICAgaWYgKGdzLmJ1dHRvbnMpIHNldEJ1dHRvbnMoZ3MuYnV0dG9ucyk7CiAgICAgICAgaWYgKGdzLnF1ZXN0cyAmJiBwYy5xdWVzdHMpIHsgcGMucXVlc3RzID0gZ3MucXVlc3RzOyByZW5kZXJRdWVzdHMoKTsgfQogICAgICAgIGlmIChncy5wYXJ0eSkgewogICAgICAgICAgT2JqZWN0LmVudHJpZXMoZ3MucGFydHkpLmZvckVhY2goKFtwbiwgcGRdKSA9PiB7CiAgICAgICAgICAgIGlmIChwYXJ0eVBDc1twbl0pIHsgcGFydHlQQ3NbcG5dLmhwID0gcGQuaHA7IHBhcnR5UENzW3BuXS5tYXhocCA9IHBkLm1heGhwOyB9CiAgICAgICAgICB9KTsKICAgICAgICAgIHJlbmRlclBhcnR5UGFuZWwoKTsKICAgICAgICB9CiAgICAgIH0KCiAgICAgIC8vIFBhcnR5IFBDIHVwZGF0ZXMKICAgICAgaWYgKGRhdGEucGFydHlQQ3MpIHsgcGFydHlQQ3MgPSBkYXRhLnBhcnR5UENzOyByZW5kZXJQYXJ0eVBhbmVsKCk7IH0KCiAgICAgIC8vIEdhbWUgc3RhcnRlZCBzaWduYWwgZm9yIG5vbi1ob3N0cyBpbiBjaGFyIGNyZWF0ZQogICAgICBpZiAoZGF0YS5nYW1lU3RhcnRlZCAmJiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncy1jaGFyJykuY2xhc3NMaXN0LmNvbnRhaW5zKCdhY3RpdmUnKSkgewogICAgICAgIHBjID0gZGF0YS5teVBjIHx8IHBjOwogICAgICAgIHBhcnR5UENzID0gZGF0YS5wYXJ0eVBDcyB8fCB7fTsKICAgICAgICBoaXN0b3J5ID0gZGF0YS5oaXN0b3J5IHx8IFtdOwogICAgICAgIHN5c3RlbVByb21wdCA9IGRhdGEuc3lzdGVtUHJvbXB0IHx8IHN5c3RlbVByb21wdDsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLW1vZCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgICBzaG93KCdzLWdhbWUnKTsKICAgICAgICB1cGRhdGVIVUQoKTsKICAgICAgICByZW5kZXJQYXJ0eVBhbmVsKCk7CiAgICAgICAgaWYgKGRhdGEubG9nRW50cmllcykgZGF0YS5sb2dFbnRyaWVzLmZvckVhY2goZSA9PiBhZGRFbnRyeVJhdyhlLmh0bWwsIGUudHlwZSwgZS5hdXRob3IpKTsKICAgICAgfQogICAgfSkuY2F0Y2goKCkgPT4ge30pOwp9CgpmdW5jdGlvbiByZW5kZXJQYXJ0eVN0YXR1cyhwbGF5ZXJzKSB7CiAgY29uc3Qgd3JhcCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdwYXJ0eS1zdGF0dXMtd3JhcCcpOwogIGNvbnN0IHJvd3MgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGFydHktc3RhdHVzLXJvd3MnKTsKICBpZiAocGxheWVycy5sZW5ndGggPD0gMSkgeyB3cmFwLnN0eWxlLmRpc3BsYXk9J25vbmUnOyByZXR1cm47IH0KICB3cmFwLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgcm93cy5pbm5lckhUTUwgPSBwbGF5ZXJzLm1hcCgocCxpKSA9PgogICAgYDxkaXYgY2xhc3M9InByZWFkeS1yb3ciPgogICAgICA8ZGl2IGNsYXNzPSJwZG90ICR7cC5yZWFkeT8nb24nOid3YWl0J30iIHN0eWxlPSJiYWNrZ3JvdW5kOiR7UExBWUVSX0NPTE9SU1tpJVBMQVlFUl9DT0xPUlMubGVuZ3RoXX0iPjwvZGl2PgogICAgICA8c3BhbiBzdHlsZT0iY29sb3I6JHtQTEFZRVJfQ09MT1JTW2klUExBWUVSX0NPTE9SUy5sZW5ndGhdfSI+JHtwLm5hbWV9PC9zcGFuPgogICAgICA8c3BhbiBzdHlsZT0iZm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0taW5rLWRpbSkiPiR7cC5yZWFkeT8nIFJlYWR5JzonLi4uIGNyZWF0aW5nIGNoYXJhY3Rlcid9PC9zcGFuPgogICAgPC9kaXY+YAogICkuam9pbignJyk7CiAgLy8gU2hvdyBiZWdpbiBidXR0b24gdG8gaG9zdCBpZiBhbGwgcmVhZHkKICBpZiAoaXNIb3N0KSB7CiAgICBjb25zdCBhbGxSZWFkeSA9IHBsYXllcnMuZXZlcnkocCA9PiBwLnJlYWR5KTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiZWdpbi1idG4nKS5zdHlsZS5kaXNwbGF5ID0gYWxsUmVhZHkgPyAnaW5saW5lLWJsb2NrJyA6ICdub25lJzsKICB9Cn0KCmZ1bmN0aW9uIHBpY2tSdWxlcyhlbCkgewogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5yYycpLmZvckVhY2goYyA9PiBjLmNsYXNzTGlzdC5yZW1vdmUoJ3BpY2tlZCcpKTsKICBlbC5jbGFzc0xpc3QuYWRkKCdwaWNrZWQnKTsKICBjaG9zZW5SdWxlcyA9IGVsLmRhdGFzZXQucjsKfQoKZnVuY3Rpb24gaGFuZGxlRmlsZShmKSB7CiAgdXBsb2FkZWRGaWxlID0gZjsKICBtb2R1bGVOYW1lID0gZi5uYW1lLnJlcGxhY2UoL1suXVteLl0rJC8sICcnKTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZmlsZS1uYW1lLWRpc3AnKS50ZXh0Q29udGVudCA9ICcgJyArIGYubmFtZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmV4dC1idG4nKS5kaXNhYmxlZCA9IGZhbHNlOwp9CgpmdW5jdGlvbiBidWlsZENoYXJDcmVhdGUoKSB7CiAgcmVyb2xsKCk7CiAgYnVpbGRSYWNlR3JpZCgpOwogIGJ1aWxkQ2xhc3NHcmlkKCk7CiAgYnVpbGRFcXVpcG1lbnQoKTsKfQoKZnVuY3Rpb24gYnVpbGRSYWNlR3JpZCgpIHsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmFjZS1ncmlkJykuaW5uZXJIVE1MID0gT2JqZWN0LmVudHJpZXMoUkFDRVMpLm1hcCgoW25hbWUsZF0pID0+CiAgICBgPGRpdiBjbGFzcz0ic2VsLWNhcmQke25hbWU9PT1jaG9zZW5SYWNlPycgcGlja2VkJzonJ30iIGRhdGEtcj0iJHtuYW1lfSIgb25jbGljaz0icGlja1JhY2UodGhpcykiPgogICAgICA8ZGl2IGNsYXNzPSJjbiI+JHtkLmljb259ICR7bmFtZX08L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0iY2QiPiR7ZC5kZXNjLnN1YnN0cmluZygwLDYwKX08L2Rpdj4KICAgIDwvZGl2PmAKICApLmpvaW4oJycpOwogIHVwZGF0ZVJhY2VEZXNjKCk7Cn0KCmZ1bmN0aW9uIGJ1aWxkQ2xhc3NHcmlkKCkgewogIGNvbnN0IGFsbG93ZWQgPSBSQUNFU1tjaG9zZW5SYWNlXT8uY2xhc3NlcyB8fCBudWxsOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbGFzcy1ncmlkJykuaW5uZXJIVE1MID0gT2JqZWN0LmVudHJpZXMoQ0xBU1NFUykubWFwKChbbmFtZSxkXSkgPT4gewogICAgY29uc3QgZGlzID0gYWxsb3dlZCAmJiAhYWxsb3dlZC5pbmNsdWRlcyhuYW1lKTsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic2VsLWNhcmQke25hbWU9PT1jaG9zZW5DbGFzcyYmIWRpcz8nIHBpY2tlZCc6Jyd9JHtkaXM/JyBkaXNhYmxlZCc6Jyd9IgogICAgICBkYXRhLWM9IiR7bmFtZX0iICR7ZGlzPycnOidvbmNsaWNrPSJwaWNrQ2xhc3ModGhpcykiJ30+CiAgICAgIDxkaXYgY2xhc3M9ImNuIj4ke2QuaWNvbn0gJHtuYW1lfTwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjZCI+JHtkLmRlc2Muc3Vic3RyaW5nKDAsNTUpfTwvZGl2PgogICAgPC9kaXY+YDsKICB9KS5qb2luKCcnKTsKICBpZiAoYWxsb3dlZCAmJiAhYWxsb3dlZC5pbmNsdWRlcyhjaG9zZW5DbGFzcykpIHsKICAgIGNob3NlbkNsYXNzID0gYWxsb3dlZFswXTsKICAgIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoYC5zZWwtY2FyZFtkYXRhLWM9IiR7Y2hvc2VuQ2xhc3N9Il1gKT8uY2xhc3NMaXN0LmFkZCgncGlja2VkJyk7CiAgfQogIHVwZGF0ZUNsYXNzRGVzYygpOwogIGJ1aWxkRXF1aXBtZW50KCk7Cn0KCmZ1bmN0aW9uIHBpY2tSYWNlKGVsKSB7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnI3JhY2UtZ3JpZCAuc2VsLWNhcmQnKS5mb3JFYWNoKGMgPT4gYy5jbGFzc0xpc3QucmVtb3ZlKCdwaWNrZWQnKSk7CiAgZWwuY2xhc3NMaXN0LmFkZCgncGlja2VkJyk7CiAgY2hvc2VuUmFjZSA9IGVsLmRhdGFzZXQucjsKICB1cGRhdGVSYWNlRGVzYygpOwogIGJ1aWxkQ2xhc3NHcmlkKCk7CiAgcmVyb2xsKCk7Cn0KCmZ1bmN0aW9uIHBpY2tDbGFzcyhlbCkgewogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJyNjbGFzcy1ncmlkIC5zZWwtY2FyZCcpLmZvckVhY2goYyA9PiBjLmNsYXNzTGlzdC5yZW1vdmUoJ3BpY2tlZCcpKTsKICBlbC5jbGFzc0xpc3QuYWRkKCdwaWNrZWQnKTsKICBjaG9zZW5DbGFzcyA9IGVsLmRhdGFzZXQuYzsKICB1cGRhdGVDbGFzc0Rlc2MoKTsKICBidWlsZEVxdWlwbWVudCgpOwp9CgpmdW5jdGlvbiB1cGRhdGVSYWNlRGVzYygpIHsKICBjb25zdCByID0gUkFDRVNbY2hvc2VuUmFjZV07CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JhY2Utc3BlY2lhbHMnKS50ZXh0Q29udGVudCA9IHI/LnNwZWNpYWxzPy5sZW5ndGggPyAnICcgKyByLnNwZWNpYWxzLmpvaW4oJyAqICcpIDogJyc7Cn0KCmZ1bmN0aW9uIHVwZGF0ZUNsYXNzRGVzYygpIHsKICBjb25zdCBjID0gQ0xBU1NFU1tjaG9zZW5DbGFzc107CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NsYXNzLWRlc2MnKS50ZXh0Q29udGVudCA9IGMgPyBjLmRlc2MgOiAnJzsKfQoKZnVuY3Rpb24gcmQoZCkgeyByZXR1cm4gTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKmQpKzE7IH0KCmZ1bmN0aW9uIHIzKCkgeyByZXR1cm4gcmQoNikrcmQoNikrcmQoNik7IH0KCmZ1bmN0aW9uIHI0ZDYoKSB7IGxldCBhPVtyZCg2KSxyZCg2KSxyZCg2KSxyZCg2KV07IGEuc29ydCgoeCx5KT0+eC15KTsgYS5zaGlmdCgpOyByZXR1cm4gYS5yZWR1Y2UoKHMsdik9PnMrdiwwKTsgfQoKZnVuY3Rpb24gbW9kKHYpIHsgbGV0IG09TWF0aC5mbG9vcigodi0xMCkvMik7IHJldHVybiBtPj0wPycrJyttOicnK207IH0KCmZ1bmN0aW9uIG1vZE4odikgeyByZXR1cm4gTWF0aC5mbG9vcigodi0xMCkvMik7IH0KCmZ1bmN0aW9uIHJlcm9sbCgpIHsKICBbJ1NUUicsJ0RFWCcsJ0NPTicsJ0lOVCcsJ1dJUycsJ0NIQSddLmZvckVhY2gocyA9PiByb2xsZWRTdGF0c1tzXSA9IHIzKCkpOwogIGNvbnN0IGJvbnVzZXMgPSBSQUNFU1tjaG9zZW5SYWNlXT8uYm9udXNlcyB8fCB7fTsKICBPYmplY3QuZW50cmllcyhib251c2VzKS5mb3JFYWNoKChbcyxiXSkgPT4gcm9sbGVkU3RhdHNbc10gPSBNYXRoLm1pbigxOCwgcm9sbGVkU3RhdHNbc10rYikpOwogIHJlbmRlclN0YXRzKCk7Cn0KCmZ1bmN0aW9uIHJlbmRlclN0YXRzKCkgewogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdGF0LWdyaWQnKS5pbm5lckhUTUwgPSBbJ1NUUicsJ0RFWCcsJ0NPTicsJ0lOVCcsJ1dJUycsJ0NIQSddLm1hcChzID0+IHsKICAgIGNvbnN0IHY9cm9sbGVkU3RhdHNbc10sIG09bW9kTih2KSwgbWM9bT4wPydwb3MnOm08MD8nbmVnJzonJzsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic3RhdC1ib3giPjxkaXYgY2xhc3M9InNuIj4ke3N9PC9kaXY+PGRpdiBjbGFzcz0ic3YiPiR7dn08L2Rpdj48ZGl2IGNsYXNzPSJzbSAke21jfSI+JHttb2Qodil9PC9kaXY+PC9kaXY+YDsKICB9KS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gYnVpbGRFcXVpcG1lbnQoKSB7CiAgc3RhcnRpbmdHb2xkID0gR09MRF9CWV9DTEFTU1tjaG9zZW5DbGFzc10gfHwgNjA7CiAgZ29sZFNwZW50ID0gMDsKICBzZWxlY3RlZEVxdWlwID0ge307CiAgZXh0cmFJdGVtcyA9IFtdOwogIHNlbGVjdGVkRXF1aXBJdGVtcy5jbGVhcigpOyAgLy8gcmVzZXQgZXF1aXBtZW50IHNlbGVjdGlvbgoKICBjb25zdCBjYXRzID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2VxdWlwLWNhdGVnb3JpZXMnKTsKICBjb25zdCBhbGxvd2VkV2VhcG9ucyA9IENMQVNTX1dFQVBPTl9SRVNUUklDVElPTlNbY2hvc2VuQ2xhc3NdOyAvLyBudWxsID0gYWxsCiAgY29uc3QgYWxsb3dlZEFybW91ciAgPSBDTEFTU19BUk1PVVJfUkVTVFJJQ1RJT05TW2Nob3NlbkNsYXNzXSB8fCBbXTsKCiAgLy8gRmlsdGVyIHdlYXBvbnMgYnkgY2xhc3MgcmVzdHJpY3Rpb24KICBjb25zdCBtZWxlZVdlYXBvbnMgID0gT2JqZWN0LmVudHJpZXMoT1NFX1dFQVBPTlMpCiAgICAuZmlsdGVyKChbbix3XSkgPT4gIXcucmFuZ2VkICYmICghYWxsb3dlZFdlYXBvbnMgfHwgYWxsb3dlZFdlYXBvbnMuaW5jbHVkZXMobikpKTsKICBjb25zdCByYW5nZWRXZWFwb25zID0gT2JqZWN0LmVudHJpZXMoT1NFX1dFQVBPTlMpCiAgICAuZmlsdGVyKChbbix3XSkgPT4gdy5yYW5nZWQgJiYgdy5kbWcgIT09ICctJyAmJiAoIWFsbG93ZWRXZWFwb25zIHx8IGFsbG93ZWRXZWFwb25zLmluY2x1ZGVzKG4pKSk7CiAgY29uc3QgYW1tb0l0ZW1zICAgICA9IE9iamVjdC5lbnRyaWVzKE9TRV9XRUFQT05TKQogICAgLmZpbHRlcigoW24sd10pID0+IHcucmFuZ2VkICYmIHcuZG1nID09PSAnLScpOwogIGNvbnN0IGFybW91ckl0ZW1zICAgPSBPYmplY3QuZW50cmllcyhPU0VfQVJNT1VSKQogICAgLmZpbHRlcigoW25dKSA9PiBhbGxvd2VkQXJtb3VyLmluY2x1ZGVzKG4pKTsKICBjb25zdCBlcXVpcEl0ZW1zICAgID0gT2JqZWN0LmVudHJpZXMoT1NFX0VRVUlQTUVOVCk7CgogIGZ1bmN0aW9uIHdlYXBvbkxhYmVsKG5hbWUsIHcpIHsKICAgIGNvbnN0IGNvc3QgPSB3LmNvc3QgPiAwID8gYCAoJHt3LmNvc3R9Z3ApYCA6ICcgKGZyZWUpJzsKICAgIGNvbnN0IG5vdGVzID0gdy5ub3RlcyA/IGAgLS0gJHt3Lm5vdGVzfWAgOiAnJzsKICAgIHJldHVybiBgJHtuYW1lfSBbJHt3LmRtZ31dJHtjb3N0fSR7bm90ZXN9YDsKICB9CiAgZnVuY3Rpb24gYXJtb3VyTGFiZWwobmFtZSwgYSkgewogICAgcmV0dXJuIGAke25hbWV9IC0tIEFDICR7YS5hY30gKCR7YS5jb3N0fWdwKWA7CiAgfQogIGZ1bmN0aW9uIGVxdWlwTGFiZWwobmFtZSwgZSkgewogICAgY29uc3QgY29zdCA9IGUuY29zdCA+IDAgPyBgICgke2UuY29zdH1ncClgIDogJyAoZnJlZSknOwogICAgY29uc3Qgbm90ZXMgPSBlLm5vdGVzID8gYCAtLSAke2Uubm90ZXN9YCA6ICcnOwogICAgcmV0dXJuIGAke25hbWV9JHtjb3N0fSR7bm90ZXN9YDsKICB9CgogIGxldCBodG1sID0gJyc7CgogIC8vIE1lbGVlIHdlYXBvbnMKICBpZiAobWVsZWVXZWFwb25zLmxlbmd0aCkgewogICAgaHRtbCArPSBidWlsZEVxdWlwU2VjdGlvbignTWVsZWUgV2VhcG9uJywgbWVsZWVXZWFwb25zLm1hcCgoW24sd10pID0+ICh7CiAgICAgIGtleTogbiwgbGFiZWw6IHdlYXBvbkxhYmVsKG4sdyksIGNvc3Q6IHcuY29zdAogICAgfSkpKTsKICB9CgogIC8vIFJhbmdlZCB3ZWFwb25zCiAgaWYgKHJhbmdlZFdlYXBvbnMubGVuZ3RoKSB7CiAgICBodG1sICs9IGJ1aWxkRXF1aXBTZWN0aW9uKCdSYW5nZWQgV2VhcG9uJywgcmFuZ2VkV2VhcG9ucy5tYXAoKFtuLHddKSA9PiAoewogICAgICBrZXk6IG4sIGxhYmVsOiB3ZWFwb25MYWJlbChuLHcpLCBjb3N0OiB3LmNvc3QKICAgIH0pKSwgdHJ1ZSk7IC8vIG9wdGlvbmFsCiAgfQoKICAvLyBBbW1vIChzaG93biBvbmx5IGlmIHJhbmdlZCB3ZWFwb24gc2VsZWN0ZWQgLS0gYWx3YXlzIHNob3cgYWxsKQogIGlmIChyYW5nZWRXZWFwb25zLmxlbmd0aCkgewogICAgaHRtbCArPSBidWlsZEVxdWlwU2VjdGlvbignQW1tdW5pdGlvbicsIGFtbW9JdGVtcy5tYXAoKFtuLHddKSA9PiAoewogICAgICBrZXk6IG4sIGxhYmVsOiBgJHtufSR7dy5jb3N0ID4gMCA/ICcgKCcrdy5jb3N0KydncCknIDogJyAoZnJlZSknfWAsIGNvc3Q6IHcuY29zdAogICAgfSkpLCB0cnVlKTsKICB9CgogIC8vIEFybW91cgogIGlmIChhcm1vdXJJdGVtcy5sZW5ndGgpIHsKICAgIGh0bWwgKz0gYnVpbGRFcXVpcFNlY3Rpb24oJ0FybW91cicsIGFybW91ckl0ZW1zLm1hcCgoW24sYV0pID0+ICh7CiAgICAgIGtleTogbiwgbGFiZWw6IGFybW91ckxhYmVsKG4sYSksIGNvc3Q6IGEuY29zdAogICAgfSkpKTsKICAgIC8vIFNoaWVsZCBhcyBzZXBhcmF0ZSBvcHRpb25hbCBwaWNrIGlmIGNsYXNzIGFsbG93cwogICAgaWYgKGFsbG93ZWRBcm1vdXIuaW5jbHVkZXMoJ1NoaWVsZCcpKSB7CiAgICAgIGh0bWwgKz0gYnVpbGRFcXVpcFNlY3Rpb24oJ1NoaWVsZCcsIFt7a2V5OidTaGllbGQnLCBsYWJlbDonU2hpZWxkIC0tICsxIEFDICgxMGdwKScsIGNvc3Q6MTB9LAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAge2tleTonbm9uZScsIGxhYmVsOidObyBTaGllbGQnLCBjb3N0OjB9XSwgZmFsc2UpOwogICAgfQogIH0KCiAgLy8gRXF1aXBtZW50IC0tIHBpY2sgdXAgdG8gNCBpdGVtcyBmcm9tIHRoZSBPU0UgbGlzdAogIGh0bWwgKz0gYDxkaXYgY2xhc3M9ImVxdWlwLWNhdGVnb3J5Ij4KICAgIDxkaXYgY2xhc3M9ImVxdWlwLWNhdC10aXRsZSI+RXF1aXBtZW50IChwaWNrIGl0ZW1zIC0tIGNvc3QgZGVkdWN0ZWQgZnJvbSBnb2xkKTwvZGl2PgogICAgPGRpdiBjbGFzcz0iZXF1aXAtb3B0aW9ucyIgaWQ9Im9zZS1lcXVpcC1ncmlkIj4KICAgICAgJHtlcXVpcEl0ZW1zLm1hcCgoW24sZV0pID0+CiAgICAgICAgYDxkaXYgY2xhc3M9ImVxdWlwLW9wdCIgZGF0YS1jYXQ9ImVxdWlwIiBkYXRhLWl0ZW09IiR7bn0iIGRhdGEtY29zdD0iJHtlLmNvc3R9IgogICAgICAgICAgb25jbGljaz0idG9nZ2xlRXF1aXBJdGVtKHRoaXMpIj4ke2VxdWlwTGFiZWwobixlKX08L2Rpdj5gCiAgICAgICkuam9pbignJyl9CiAgICA8L2Rpdj4KICA8L2Rpdj5gOwoKICBjYXRzLmlubmVySFRNTCA9IGh0bWw7CiAgcmVjYWxjR29sZFNwZW50KCk7CiAgdXBkYXRlR29sZERpc3BsYXkoKTsKICB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCk7Cn0KCmZ1bmN0aW9uIGJ1aWxkRXF1aXBTZWN0aW9uKGNhdCwgaXRlbXMsIG9wdGlvbmFsPWZhbHNlKSB7CiAgaWYgKCFpdGVtcy5sZW5ndGgpIHJldHVybiAnJzsKICBjb25zdCBmaXJzdEtleSA9IG9wdGlvbmFsID8gJ25vbmUnIDogaXRlbXNbMF0ua2V5OwogIGlmICghb3B0aW9uYWwgJiYgIXNlbGVjdGVkRXF1aXBbY2F0XSkgc2VsZWN0ZWRFcXVpcFtjYXRdID0gaXRlbXNbMF0ua2V5OwogIGlmIChvcHRpb25hbCAmJiAhc2VsZWN0ZWRFcXVpcFtjYXRdKSBzZWxlY3RlZEVxdWlwW2NhdF0gPSAnbm9uZSc7CiAgY29uc3Qgbm9uZU9wdCA9IG9wdGlvbmFsID8gYDxkaXYgY2xhc3M9ImVxdWlwLW9wdCR7Zmlyc3RLZXk9PT0nbm9uZSc/JyBzZWwnOicnfSIgZGF0YS1jYXQ9IiR7Y2F0fSIgZGF0YS1pdGVtPSJub25lIiBkYXRhLWNvc3Q9IjAiIG9uY2xpY2s9InBpY2tFcXVpcCh0aGlzKSI+Tm9uZTwvZGl2PmAgOiAnJzsKICByZXR1cm4gYDxkaXYgY2xhc3M9ImVxdWlwLWNhdGVnb3J5Ij4KICAgIDxkaXYgY2xhc3M9ImVxdWlwLWNhdC10aXRsZSI+JHtjYXR9PC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJlcXVpcC1vcHRpb25zIj4KICAgICAgJHtub25lT3B0fQogICAgICAke2l0ZW1zLm1hcChpdGVtID0+CiAgICAgICAgYDxkaXYgY2xhc3M9ImVxdWlwLW9wdCR7aXRlbS5rZXk9PT1maXJzdEtleSYmIW9wdGlvbmFsPycgc2VsJzonJ30iIGRhdGEtY2F0PSIke2NhdH0iIGRhdGEtaXRlbT0iJHtpdGVtLmtleX0iIGRhdGEtY29zdD0iJHtpdGVtLmNvc3R9IiBvbmNsaWNrPSJwaWNrRXF1aXAodGhpcykiPiR7aXRlbS5sYWJlbH08L2Rpdj5gCiAgICAgICkuam9pbignJyl9CiAgICA8L2Rpdj4KICA8L2Rpdj5gOwp9CgpmdW5jdGlvbiB0b2dnbGVFcXVpcEl0ZW0oZWwpIHsKICBjb25zdCBpdGVtID0gZWwuZGF0YXNldC5pdGVtOwogIGNvbnN0IGNvc3QgPSBwYXJzZUludChlbC5kYXRhc2V0LmNvc3QpIHx8IDA7CiAgaWYgKHNlbGVjdGVkRXF1aXBJdGVtcy5oYXMoaXRlbSkpIHsKICAgIHNlbGVjdGVkRXF1aXBJdGVtcy5kZWxldGUoaXRlbSk7CiAgICBlbC5jbGFzc0xpc3QucmVtb3ZlKCdzZWwnKTsKICB9IGVsc2UgewogICAgLy8gQ2hlY2sgaWYgd2UgY2FuIGFmZm9yZCBpdAogICAgaWYgKGdvbGRTcGVudCArIGNvc3QgPiBzdGFydGluZ0dvbGQpIHsKICAgICAgZWwuc3R5bGUub3V0bGluZSA9ICcxcHggc29saWQgI2MwNjA2MCc7CiAgICAgIHNldFRpbWVvdXQoKCkgPT4gZWwuc3R5bGUub3V0bGluZSA9ICcnLCA4MDApOwogICAgICByZXR1cm47CiAgICB9CiAgICBzZWxlY3RlZEVxdWlwSXRlbXMuYWRkKGl0ZW0pOwogICAgZWwuY2xhc3NMaXN0LmFkZCgnc2VsJyk7CiAgfQogIC8vIFVwZGF0ZSBleHRyYUl0ZW1zIGZyb20gc2VsZWN0ZWRFcXVpcEl0ZW1zCiAgZXh0cmFJdGVtcyA9IEFycmF5LmZyb20oc2VsZWN0ZWRFcXVpcEl0ZW1zKTsKICByZWNhbGNHb2xkU3BlbnQoKTsKICB1cGRhdGVHb2xkRGlzcGxheSgpOwogIHVwZGF0ZUludmVudG9yeVByZXZpZXcoKTsKfQoKZnVuY3Rpb24gcmVjYWxjR29sZFNwZW50KCkgewogIGdvbGRTcGVudCA9IDA7CiAgLy8gV2VhcG9uIGNvc3RzCiAgT2JqZWN0LmVudHJpZXMoc2VsZWN0ZWRFcXVpcCkuZm9yRWFjaCgoW2NhdCwga2V5XSkgPT4gewogICAgaWYgKGtleSA9PT0gJ25vbmUnKSByZXR1cm47CiAgICBjb25zdCB3ID0gT1NFX1dFQVBPTlNba2V5XTsKICAgIGNvbnN0IGEgPSBPU0VfQVJNT1VSW2tleV07CiAgICBpZiAodykgZ29sZFNwZW50ICs9IHcuY29zdDsKICAgIGVsc2UgaWYgKGEpIGdvbGRTcGVudCArPSBhLmNvc3Q7CiAgfSk7CiAgLy8gRXF1aXBtZW50IGNvc3RzCiAgc2VsZWN0ZWRFcXVpcEl0ZW1zLmZvckVhY2gobmFtZSA9PiB7CiAgICBjb25zdCBlID0gT1NFX0VRVUlQTUVOVFtuYW1lXTsKICAgIGlmIChlKSBnb2xkU3BlbnQgKz0gZS5jb3N0OwogIH0pOwp9CgpmdW5jdGlvbiBwaWNrRXF1aXAoZWwpIHsKICBjb25zdCBjYXQgPSBlbC5kYXRhc2V0LmNhdDsKICBjb25zdCBpdGVtID0gZWwuZGF0YXNldC5pdGVtOwogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoYC5lcXVpcC1vcHRbZGF0YS1jYXQ9IiR7Y2F0fSJdYCkuZm9yRWFjaChlID0+IGUuY2xhc3NMaXN0LnJlbW92ZSgnc2VsJykpOwogIGVsLmNsYXNzTGlzdC5hZGQoJ3NlbCcpOwogIHNlbGVjdGVkRXF1aXBbY2F0XSA9IGl0ZW07CiAgcmVjYWxjR29sZFNwZW50KCk7CiAgdXBkYXRlR29sZERpc3BsYXkoKTsKICB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCk7CiAgdXBkYXRlSW52ZW50b3J5UHJldmlldygpOwp9CgpmdW5jdGlvbiByZW5kZXJFeHRyYUl0ZW1zKCkgewogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2V4dHJhLWl0ZW1zLWxpc3QnKTsKICBlbC5pbm5lckhUTUwgPSBTSE9QX0lURU1TLm1hcChpdGVtID0+CiAgICBgPGRpdiBjbGFzcz0iZXF1aXAtb3B0JHtleHRyYUl0ZW1zLmluY2x1ZGVzKGl0ZW0ubmFtZSk/JyBzZWwnOicnfSIgCiAgICAgIG9uY2xpY2s9InRvZ2dsZUV4dHJhKCcke2l0ZW0ubmFtZX0nLCR7aXRlbS5jb3N0fSkiPiR7aXRlbS5uYW1lfSAoJHtpdGVtLmNvc3R9Z3ApPC9kaXY+YAogICkuam9pbignJyk7Cn0KCmZ1bmN0aW9uIHRvZ2dsZUV4dHJhKG5hbWUsIGNvc3QpIHsKICBjb25zdCBpZHggPSBleHRyYUl0ZW1zLmluZGV4T2YobmFtZSk7CiAgaWYgKGlkeCA+PSAwKSB7CiAgICBleHRyYUl0ZW1zLnNwbGljZShpZHgsIDEpOwogICAgZ29sZFNwZW50IC09IGNvc3Q7CiAgfSBlbHNlIHsKICAgIGlmIChnb2xkU3BlbnQgKyBjb3N0ID4gc3RhcnRpbmdHb2xkKSB7IGFsZXJ0KGBOb3QgZW5vdWdoIGdvbGQhIFlvdSBoYXZlICR7c3RhcnRpbmdHb2xkIC0gZ29sZFNwZW50fWdwIHJlbWFpbmluZy5gKTsgcmV0dXJuOyB9CiAgICBleHRyYUl0ZW1zLnB1c2gobmFtZSk7CiAgICBnb2xkU3BlbnQgKz0gY29zdDsKICB9CiAgcmVuZGVyRXh0cmFJdGVtcygpOwogIHVwZGF0ZUdvbGREaXNwbGF5KCk7CiAgdXBkYXRlSW52ZW50b3J5UHJldmlldygpOwp9CgpmdW5jdGlvbiB1cGRhdGVHb2xkRGlzcGxheSgpIHsKICByZWNhbGNHb2xkU3BlbnQoKTsKICBjb25zdCByZW1haW5pbmcgPSBzdGFydGluZ0dvbGQgLSBnb2xkU3BlbnQ7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZ29sZC1yZW1haW5pbmcnKTsKICBpZiAoZWwpIHsKICAgIGVsLnRleHRDb250ZW50ID0gJ0dvbGQ6ICcgKyByZW1haW5pbmcgKyAnZ3AgcmVtYWluaW5nIChzdGFydGVkIHdpdGggJyArIHN0YXJ0aW5nR29sZCArICdncCwgc3BlbnQgJyArIGdvbGRTcGVudCArICdncCknOwogICAgZWwuc3R5bGUuY29sb3IgPSByZW1haW5pbmcgPCAwID8gJyNjMDYwNjAnIDogcmVtYWluaW5nIDwgMjAgPyAnI2MwOTA0MCcgOiAndmFyKC0taW5rLWRpbSknOwogIH0KfQoKZnVuY3Rpb24gc3BsaXRDb21iaW5lZEl0ZW0oaXRlbSkgewogIC8vIE9ubHkgc3BsaXQgd2VhcG9uK2FtbW8gcGF0dGVybnMgbGlrZSAiTGlnaHQgQ3Jvc3Nib3cgKyBCb2x0cyB4MjAiCiAgLy8gRG8gTk9UIHNwbGl0IGFybW91ciBjb21ib3MgbGlrZSAiQ2hhaW4gTWFpbCArIFNoaWVsZCIgb3IgIlNoaWVsZCAoKzEgQUMpIgogIGNvbnN0IGFtbW9QYXR0ZXJuID0gL2JvbHRzP3xhcnJvd3M/fHF1YXJyZWxzP3xzaG90cz8vaTsKICBpZiAoIWl0ZW0uaW5jbHVkZXMoJysnKSkgcmV0dXJuIFtpdGVtXTsKICAvLyBPbmx5IHNwbGl0IGlmIG9uZSBwYXJ0IGxvb2tzIGxpa2UgYW1tbwogIGNvbnN0IHBhcnRzID0gaXRlbS5zcGxpdCgnKycpLm1hcChzID0+IHMudHJpbSgpKTsKICBjb25zdCBoYXNBbW1vID0gcGFydHMuc29tZShwID0+IGFtbW9QYXR0ZXJuLnRlc3QocCkpOwogIGlmICghaGFzQW1tbykgcmV0dXJuIFtpdGVtXTsgLy8gS2VlcCAiQ2hhaW4gTWFpbCArIFNoaWVsZCIgYXMgb25lIGl0ZW0KICByZXR1cm4gcGFydHMubWFwKHBhcnQgPT4gewogICAgLy8gTm9ybWFsaXNlICIyMCBib2x0cyIgLT4gIkJvbHRzIHgyMCIKICAgIGNvbnN0IG0gPSBwYXJ0Lm1hdGNoKC9eKFsuXWQrKVsuXXMrKC4rKSQvKTsKICAgIGlmIChtKSByZXR1cm4gbVsyXS5jaGFyQXQoMCkudG9VcHBlckNhc2UoKSArIG1bMl0uc2xpY2UoMSkgKyAnIHgnICsgbVsxXTsKICAgIHJldHVybiBwYXJ0OwogIH0pLmZpbHRlcihCb29sZWFuKTsKfQoKZnVuY3Rpb24gZ2V0RmluYWxJbnZlbnRvcnkoKSB7CiAgY29uc3QgaXRlbXMgPSBbXTsKCiAgLy8gQWRkIHNlbGVjdGVkIHdlYXBvbnMvYXJtb3VyIGZyb20gcmFkaW8tc3R5bGUgcGlja3MKICBPYmplY3QuZW50cmllcyhzZWxlY3RlZEVxdWlwKS5mb3JFYWNoKChbY2F0LCBrZXldKSA9PiB7CiAgICBpZiAoIWtleSB8fCBrZXkgPT09ICdub25lJykgcmV0dXJuOwogICAgLy8gSXQncyBhIHdlYXBvbiBvciBhcm1vdXIga2V5IGZyb20gT1NFX1dFQVBPTlMgLyBPU0VfQVJNT1VSCiAgICBjb25zdCB3ID0gT1NFX1dFQVBPTlNba2V5XTsKICAgIGNvbnN0IGEgPSBPU0VfQVJNT1VSW2tleV07CiAgICBpZiAodykgewogICAgICAvLyBBZGQgd2VhcG9uOyBhbW1vIGl0ZW1zIHN0b3JlZCBzZXBhcmF0ZWx5IGluIHN0YXR1cwogICAgICBpZiAody5kbWcgPT09ICctJykgcmV0dXJuOyAvLyBhbW1vIGhhbmRsZWQgYmVsb3cKICAgICAgaXRlbXMucHVzaChrZXkpOwogICAgfSBlbHNlIGlmIChhKSB7CiAgICAgIGl0ZW1zLnB1c2goa2V5KTsKICAgIH0gZWxzZSBpZiAoa2V5ICE9PSAnbm9uZScpIHsKICAgICAgLy8gRmFsbGJhY2s6IGp1c3QgYWRkIHRoZSBrZXkgYXMtaXMKICAgICAgaXRlbXMucHVzaChrZXkpOwogICAgfQogIH0pOwoKICAvLyBBZGQgYW1tbyBzZWxlY3Rpb25zCiAgT2JqZWN0LmVudHJpZXMoc2VsZWN0ZWRFcXVpcCkuZm9yRWFjaCgoW2NhdCwga2V5XSkgPT4gewogICAgaWYgKCFrZXkgfHwga2V5ID09PSAnbm9uZScpIHJldHVybjsKICAgIGNvbnN0IHcgPSBPU0VfV0VBUE9OU1trZXldOwogICAgaWYgKHcgJiYgdy5kbWcgPT09ICctJykgaXRlbXMucHVzaChrZXkpOwogIH0pOwoKICAvLyBBZGQgbXVsdGktc2VsZWN0IGVxdWlwbWVudCBpdGVtcwogIHNlbGVjdGVkRXF1aXBJdGVtcy5mb3JFYWNoKG5hbWUgPT4gewogICAgaWYgKG5hbWUpIGl0ZW1zLnB1c2gobmFtZSk7CiAgfSk7CgogIC8vIEZhbGxiYWNrOiBlbnN1cmUgYmFja3BhY2sgYW5kIHdhdGVyc2tpbiBpZiBub3RoaW5nIHNlbGVjdGVkCiAgaWYgKCFpdGVtcy5zb21lKGkgPT4gL2JhY2twYWNrL2kudGVzdChpKSkpIGl0ZW1zLnB1c2goJ0JhY2twYWNrJyk7CiAgaWYgKCFpdGVtcy5zb21lKGkgPT4gL3dhdGVyc2tpbi9pLnRlc3QoaSkpKSBpdGVtcy5wdXNoKCdXYXRlcnNraW4nKTsKCiAgcmV0dXJuIGl0ZW1zOwp9CgpmdW5jdGlvbiB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCkgewogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmaW5hbC1pbnYtcHJldmlldycpLnRleHRDb250ZW50ID0gZ2V0RmluYWxJbnZlbnRvcnkoKS5qb2luKCcsICcpOwp9Cgphc3luYyBmdW5jdGlvbiBtYXJrUmVhZHkoKSB7CiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIGNhbGxlZCcpOwogIGNvbnNvbGUubG9nKCdbbWFya1JlYWR5XSBjaG9zZW5DbGFzczonLCBjaG9zZW5DbGFzcywgJ2Nob3NlblJhY2U6JywgY2hvc2VuUmFjZSk7CiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIHJvbGxlZFN0YXRzOicsIEpTT04uc3RyaW5naWZ5KHJvbGxlZFN0YXRzKSk7CiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIENMQVNTRVNbY2hvc2VuQ2xhc3NdOicsIEpTT04uc3RyaW5naWZ5KENMQVNTRVNbY2hvc2VuQ2xhc3NdKSk7CiAgLy8gR3VhcmQ6IG11c3QgaGF2ZSBhIG1vZHVsZSBsb2FkZWQgKGd1ZXN0cyBnZXQgaXQgZnJvbSByb29tLCBob3N0cyBzZWxlY3QgaXQpCiAgaWYgKCFtb2R1bGVUZXh0IHx8IG1vZHVsZVRleHQubGVuZ3RoIDwgMTApIHsKICAgIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlICYmICFpc0hvc3QpIHsKICAgICAgLy8gR3Vlc3QgLS0gdHJ5IHRvIGZldGNoIG1vZHVsZSBmcm9tIHJvb20gb25lIG1vcmUgdGltZQogICAgICB0cnkgewogICAgICAgIGNvbnN0IHJkID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2pvaW5fcm9vbScsIHttZXRob2Q6J1BPU1QnLAogICAgICAgICAgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lfSl9KS50aGVuKHI9PnIuanNvbigpKTsKICAgICAgICBpZiAocmQubW9kdWxlVGV4dCkgewogICAgICAgICAgbW9kdWxlVGV4dCA9IHJkLm1vZHVsZVRleHQ7CiAgICAgICAgICBsb2FkZWRNb2R1bGVEYXRhID0gcmQubW9kdWxlRGF0YSB8fCB7fTsKICAgICAgICAgIG1vZHVsZU5hbWUgPSByZC5tb2R1bGVOYW1lIHx8IG1vZHVsZU5hbWU7CiAgICAgICAgfQogICAgICB9IGNhdGNoKGUpIHt9CiAgICB9CiAgICBpZiAoIW1vZHVsZVRleHQgfHwgbW9kdWxlVGV4dC5sZW5ndGggPCAxMCkgewogICAgICBhbGVydCgnTm8gbW9kdWxlIGxvYWRlZC4gSWYgeW91IGFyZSBhIGd1ZXN0LCB0aGUgaG9zdCBtdXN0IHNlbGVjdCBhIG1vZHVsZSBmaXJzdC4nKTsKICAgICAgcmV0dXJuOwogICAgfQogIH0KICB0cnkgewogIGNvbnN0IG5hbWUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2hhci1uYW1lLWlucCcpLnZhbHVlLnRyaW0oKSB8fCBwbGF5ZXJOYW1lIHx8ICdBZHZlbnR1cmVyJzsKICBwbGF5ZXJOYW1lID0gbmFtZTsgLy8gY2hhcmFjdGVyIG5hbWUgSVMgdGhlIHBsYXllciBuYW1lCiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIG5hbWU6JywgbmFtZSk7CiAgY29uc3QgY2xzID0gQ0xBU1NFU1tjaG9zZW5DbGFzc107CiAgY29uc3QgaGRTaXplID0gY2xzLmhkIHx8IGNscy5ocCB8fCA2OwogIGNvbnN0IGhwID0gTWF0aC5tYXgoMSwgKE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSpoZFNpemUpKzEpICsgbW9kTihyb2xsZWRTdGF0cy5DT04pKTsKICBjb25zdCByYWNlRGF0YSA9IFJBQ0VTW2Nob3NlblJhY2VdOwogIHBjID0gewogICAgbmFtZSwgcmFjZTogY2hvc2VuUmFjZSwgY2xzOiBjaG9zZW5DbGFzcywgbGV2ZWw6IDEsCiAgICBocCwgbWF4aHA6IGhwLCBhYzogY2xzLmFjLAogICAgc3RhdHM6IHsuLi5yb2xsZWRTdGF0c30sCiAgICBpbnY6IGdldEZpbmFsSW52ZW50b3J5KCksCiAgICBnb2xkOiAoZnVuY3Rpb24oKXsgcmVjYWxjR29sZFNwZW50KCk7IHJldHVybiBNYXRoLm1heCgwLCBzdGFydGluZ0dvbGQgLSBnb2xkU3BlbnQpOyB9KSgpLAogICAgbG9jOiAnLi4uJywgbG9jdGFnOiAnJywgcXVlc3RzOiBbXSwKICAgIHNwZWNpYWxzOiByYWNlRGF0YT8uc3BlY2lhbHMgfHwgW10sCiAgICBzYXZlczogY2xzLnNhdmVzCiAgfTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJykudGV4dENvbnRlbnQgPSAnIFJlYWR5ISc7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JlYWR5LWJ0bicpLmRpc2FibGVkID0gdHJ1ZTsKICAgIC8vIEF1dG8tc2F2ZSBjaGFyYWN0ZXIgdG8gZGlzayBpbW1lZGlhdGVseSBvbiBjcmVhdGlvbgogICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3NhdmVfY2hhcmFjdGVyJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHBjKX0pOwoKICB9IGNhdGNoKGUpIHsgY29uc29sZS5lcnJvcignW21hcmtSZWFkeV0gRXJyb3I6JywgZSk7IGFsZXJ0KCdDaGFyYWN0ZXIgY3JlYXRpb24gZXJyb3I6ICcgKyBlLm1lc3NhZ2UpOyByZXR1cm47IH0KICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3BsYXllcl9yZWFkeScsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LCBib2R5OiBKU09OLnN0cmluZ2lmeSh7Y29kZTpyb29tQ29kZSwgcGxheWVyOnBsYXllck5hbWUsIHBjfSl9KTsKICAgIGlmIChpc0hvc3QpIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiZWdpbi1idG4nKS5zdHlsZS5kaXNwbGF5ID0gJ2lubGluZS1ibG9jayc7CiAgfSBlbHNlIHsKICAgIGJlZ2luQWR2ZW50dXJlKCk7CiAgfQp9CgpmdW5jdGlvbiBiZWdpbkFkdmVudHVyZSgpIHsKICBjb25zb2xlLmxvZygnW2JlZ2luQWR2ZW50dXJlXSBjYWxsZWQsIGlzTXVsdGlwbGF5ZXI6JywgaXNNdWx0aXBsYXllciwgJ3Jvb21Db2RlOicsIHJvb21Db2RlKTsKICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2dldF9yb29tJykudGhlbihyID0+IHIuanNvbigpKTsgLy8gbm9vcAogIH0KICBwYXJ0eVBDc1twbGF5ZXJOYW1lXSA9IHBjOwogIC8vIEZldGNoIGFsbCBwYXJ0eSBQQ3MgZnJvbSBzZXJ2ZXIgaWYgbXVsdGlwbGF5ZXIKICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgZmV0Y2goYC9yb29tX3N0YXRlP2NvZGU9JHtyb29tQ29kZX1gKS50aGVuKHI9PnIuanNvbigpKS50aGVuKHN0YXRlID0+IHsKICAgICAgcGFydHlQQ3MgPSBzdGF0ZS5wYXJ0eVBDcyB8fCB7W3BsYXllck5hbWVdOiBwY307CiAgICAgIE9iamVjdC5rZXlzKHBhcnR5UENzKS5mb3JFYWNoKChuLGkpID0+IHsgY29sb3JNYXBbbl0gPSBQTEFZRVJfQ09MT1JTW2klUExBWUVSX0NPTE9SUy5sZW5ndGhdOyB9KTsKICAgICAgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKICAgICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3VwZGF0ZV9yb29tJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOnJvb21Db2RlLCBzeXN0ZW1Qcm9tcHQsIGdhbWVBY3RpdmU6dHJ1ZSwgcGFydHlQQ3N9KX0pOwogICAgICBsYXVuY2hHYW1lKCk7CiAgICB9KTsKICB9IGVsc2UgewogICAgcGFydHlQQ3MgPSB7W3BsYXllck5hbWVdOiBwY307CiAgICBzeXN0ZW1Qcm9tcHQgPSBidWlsZFN5c3RlbVByb21wdCgpOwogICAgbGF1bmNoR2FtZSgpOwogIH0KfQoKZnVuY3Rpb24gaW5pdFJlc291cmNlc0Zyb21JbnZlbnRvcnkoKSB7CiAgY29uc3QgaW52ID0gKHBjLmludiB8fCBbXSkuam9pbignICcpLnRvTG93ZXJDYXNlKCk7CgogIC8vIExhbnRlcm4gLS0gT1NFIGl0ZW0gbmFtZSBpcyBqdXN0ICJMYW50ZXJuIgogIGhhc0xhbnRlcm4gPSAvbGFudGVybi9pLnRlc3QoaW52KTsKCiAgLy8gT2lsIGZsYXNrcyAtLSBPU0U6ICJPaWwgKDEgZmxhc2spIgogIGNvbnN0IG9pbE1hdGNoID0gaW52Lm1hdGNoKC9vaWxbXlsuXW5dKihbLl1kKykvaSk7CiAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSBvaWxNYXRjaCA/IHBhcnNlSW50KG9pbE1hdGNoWzFdKSA6IChoYXNMYW50ZXJuID8gMSA6IDApOwoKICAvLyBUb3JjaGVzIC0tIE9TRTogIlRvcmNoZXMgKDYpIiA9IHBhY2sgb2YgNiwgZWFjaCBidXJucyA2IHR1cm5zCiAgY29uc3QgdG9yY2hNYXRjaCA9IGludi5tYXRjaCgvdG9yY2hlcz9bLl1zKlsuXT8oWzAtOV0rKVsuXT8vaSkKICAgIHx8IGludi5tYXRjaCgvKFswLTldKylbLl1zKnRvcmNoZXM/L2kpOwogIGNvbnN0IHRvcmNoQ291bnQgPSB0b3JjaE1hdGNoID8gcGFyc2VJbnQodG9yY2hNYXRjaFsxXSkgOiAwOwoKICAvLyBSYXRpb25zIC0tIE9TRTogIlJhdGlvbnMgKGlyb24sIDcgZGF5cykiIG9yICJSYXRpb25zIChzdGFuZGFyZCwgNyBkYXlzKSIgPSA3IGRheSBzdXBwbHkKICBpZiAoL3JhdGlvbnM/L2kudGVzdChpbnYpKSB7CiAgICByYXRpb25zTGVmdCA9IDc7IC8vIEJvdGggT1NFIHJhdGlvbiB0eXBlcyBhcmUgNy1kYXkgc3VwcGxpZXMKICB9IGVsc2UgewogICAgcmF0aW9uc0xlZnQgPSAwOwogIH0KCiAgLy8gVG9yY2hlcyBpbiBpbnZlbnRvcnkgZG9lcyBOT1QgbWVhbiB0aGV5IGFyZSBsaXQgLSBwbGF5ZXIgbXVzdCB1c2Ugb25lCiAgdG9yY2hlc0NhcnJpZWQgPSB0b3JjaENvdW50OwogIHRvcmNoVHVybnNMZWZ0ID0gMDsKICB0b3JjaExpdCA9IGZhbHNlOwogIGxhbnRlcm5MaXQgPSBmYWxzZTsKICB0b3JjaEV2ZXJVc2VkID0gZmFsc2U7CiAgaXNDYXJyeWluZ0xpZ2h0ID0gdHJ1ZTsgICAgICAgLy8gYXNzdW1lIGRheWxpZ2h0L2FtYmllbnQgYXQgc3RhcnQKICAvLyBSZXNldCBhbGwgcGVuYWx0eSB0cmFja2VycwogIHJlc3REZWJ0ID0gMDsKICB0dXJuc1dpdGhvdXRSZXN0ID0gMDsKICBmYXRpZ3VlUGVuYWx0eSA9IDA7CiAgZGF5c1dpdGhvdXRGb29kID0gMDsKICBzdGFydmF0aW9uUGVuYWx0eSA9IDA7CiAgZm9yY2VkTWFyY2hBY3RpdmUgPSBmYWxzZTsKICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOwoKICBjb25zb2xlLmxvZygnW1Jlc291cmNlc10gSW5pdCAtLSB0b3JjaGVzOicsIHRvcmNoQ291bnQsICcoJywgdG9yY2hUdXJuc0xlZnQsICd0dXJucyknLAogICAgJ3wgbGFudGVybjonLCBoYXNMYW50ZXJuLCAnfCBvaWw6JywgbGFudGVybk9pbEZsYXNrc0xlZnQsCiAgICAnfCByYXRpb25zOicsIHJhdGlvbnNMZWZ0KTsKfQoKZnVuY3Rpb24gYWR2YW5jZUR1bmdlb25UdXJuKHR1cm5zKSB7CiAgdHVybnMgPSB0dXJucyB8fCAxOwogIGR1bmdlb25UdXJucyArPSB0dXJuczsKICByZXN0RGVidCArPSB0dXJuczsgICAgICAgICAgICAgLy8gbGVnYWN5IGNvbXBhdAogIHR1cm5zV2l0aG91dFJlc3QgKz0gdHVybnM7CiAgd2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyICs9IHR1cm5zOwoKICAvLyBPU0UgZHVuZ2VvbiByZXN0IHJ1bGU6IGV2ZXJ5IDYgdHVybnMgZXhwbG9yZWQgd2l0aG91dCBhIDEtdHVybiByZXN0CiAgLy8gaW1wb3NlcyBhIGN1bXVsYXRpdmUgLTEgdG8gYXR0YWNrIHJvbGxzCiAgLy8gKGNvbW1vbiBpbnRlcnByZXRhdGlvbiBvZiB0aGUgcmVzdC1ldmVyeS02LXR1cm5zIHJlcXVpcmVtZW50KQogIC8vIE9ubHkgYXBwbHkgZmF0aWd1ZSBwZW5hbHR5IGluIGR1bmdlb24gKE9TRSBydWxlIG9ubHkgYXBwbGllcyB1bmRlcmdyb3VuZCkKICBmYXRpZ3VlUGVuYWx0eSA9IGlzSW5EdW5nZW9uKCkgPyBNYXRoLmZsb29yKHR1cm5zV2l0aG91dFJlc3QgLyA2KSA6IDA7CgogIC8vIEJ1cm4gdG9yY2ggKE9TRTogdG9yY2ggYnVybnMgY29udGludW91c2x5LCA2IHR1cm5zIGVhY2gpCiAgaWYgKHRvcmNoVHVybnNMZWZ0ID4gMCkgewogICAgdG9yY2hUdXJuc0xlZnQgPSBNYXRoLm1heCgwLCB0b3JjaFR1cm5zTGVmdCAtIHR1cm5zKTsKICAgIGlmICh0b3JjaFR1cm5zTGVmdCA9PT0gMCkgewogICAgICAvLyBBdXRvLXN3aXRjaCB0byBsYW50ZXJuIGlmIGF2YWlsYWJsZQogICAgICBpZiAoaGFzTGFudGVybiAmJiBsYW50ZXJuT2lsRmxhc2tzTGVmdCA+IDApIHsKICAgICAgICBpc0NhcnJ5aW5nTGlnaHQgPSB0cnVlOyAvLyBsYW50ZXJuIHRha2VzIG92ZXIKICAgICAgfSBlbHNlIHsKICAgICAgICBpc0NhcnJ5aW5nTGlnaHQgPSBmYWxzZTsKICAgICAgfQogICAgfQogIH0gZWxzZSBpZiAoaGFzTGFudGVybiAmJiBsYW50ZXJuT2lsRmxhc2tzTGVmdCA+IDApIHsKICAgIC8vIE9TRTogbGFudGVybiBidXJucyAxIGZsYXNrIHBlciAyNCB0dXJucyAoNCBob3VycykKICAgIC8vIFRyYWNrIGJ5IGFic29sdXRlIHR1cm4gY291bnQKICAgIGNvbnN0IGZsYXNrc0NvbnN1bWVkID0gTWF0aC5mbG9vcihkdW5nZW9uVHVybnMgLyAyNCk7CiAgICBjb25zdCBuZXdGbGFza3NMZWZ0ID0gTWF0aC5tYXgoMCwgbGFudGVybk9pbEZsYXNrc0xlZnQgLSBmbGFza3NDb25zdW1lZCk7CiAgICBpZiAobmV3Rmxhc2tzTGVmdCA8IGxhbnRlcm5PaWxGbGFza3NMZWZ0KSB7CiAgICAgIGxhbnRlcm5PaWxGbGFza3NMZWZ0ID0gbmV3Rmxhc2tzTGVmdDsKICAgICAgaWYgKGxhbnRlcm5PaWxGbGFza3NMZWZ0ID09PSAwKSBpc0NhcnJ5aW5nTGlnaHQgPSBmYWxzZTsKICAgIH0KICB9CgogIC8vIE9TRSB3YW5kZXJpbmcgbW9uc3RlciBjaGVjazogZXZlcnkgMiB0dXJucywgcm9sbCAxZDYKICAvLyAxID0gd2FuZGVyaW5nIG1vbnN0ZXIgZW5jb3VudGVyCiAgaWYgKHdhbmRlcmluZ01vbnN0ZXJUdXJuQ291bnRlciA+PSAyKSB7CiAgICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOwogICAgY29uc3Qgcm9sbCA9IE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSAqIDYpICsgMTsKICAgIGlmIChyb2xsID09PSAxKSB7CiAgICAgIHdhbmRlcmluZ01vbnN0ZXJDaGVja0R1ZSA9IHRydWU7CiAgICAgIGNvbnNvbGUubG9nKCdbV2FuZGVyaW5nXSBFbmNvdW50ZXIgdHJpZ2dlcmVkIScpOwogICAgfQogIH0KfQoKZnVuY3Rpb24gaGFuZGxlRHVuZ2VvblJlc3QoKSB7CiAgLy8gMS10dXJuIHJlc3QgcmVzZXRzIHRoZSBmYXRpZ3VlIGNsb2NrCiAgdHVybnNXaXRob3V0UmVzdCA9IDA7CiAgZmF0aWd1ZVBlbmFsdHkgPSAwOwogIGFkdmFuY2VEdW5nZW9uVHVybigxKTsgLy8gcmVzdCBpdHNlbGYgdGFrZXMgMSB0dXJuICh3YW5kZXJpbmcgbW9uc3RlciBjaGVjayBhcHBsaWVzKQogIGlmIChpc0luRHVuZ2VvbigpKSBhZGRFbnRyeVJhdygnUmVzdCB0YWtlbiAtLSAxIHR1cm4uICgnICsgdHVybnNXaXRob3V0UmVzdCArICcvNiB0dXJucyByZXNldCknLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgpmdW5jdGlvbiBoYW5kbGVGdWxsUmVzdCgpIHsKICAvLyBDb25zdW1lIDEgcmF0aW9uICgxIHBlciBkYXkgcmVxdWlyZWQpCiAgaWYgKHJhdGlvbnNMZWZ0ID4gMCkgewogICAgcmF0aW9uc0xlZnQgPSBNYXRoLm1heCgwLCByYXRpb25zTGVmdCAtIDEpOwogICAgZGF5c1dpdGhvdXRGb29kID0gMDsgICAgICAgIC8vIGF0ZSB0b2RheSAtLSByZXNldCBzdGFydmF0aW9uIGNvdW50ZXIKICAgIHN0YXJ2YXRpb25QZW5hbHR5ID0gMDsKICB9IGVsc2UgewogICAgZGF5c1dpdGhvdXRGb29kKys7CiAgICAvLyBIb3VzZSBydWxlOiBhZnRlciAzIGRheXMgd2l0aG91dCBmb29kLCAtMSB0byBhdHRhY2tzIGFuZCBzYXZlcyBwZXIgZGF5CiAgICBzdGFydmF0aW9uUGVuYWx0eSA9IE1hdGgubWF4KDAsIGRheXNXaXRob3V0Rm9vZCAtIDMpOwogICAgaWYgKHN0YXJ2YXRpb25QZW5hbHR5ID4gMCkgewogICAgICBhZGRFbnRyeVJhdygnU3RhcnZhdGlvbjogLScgKyBzdGFydmF0aW9uUGVuYWx0eSArICcgdG8gYXR0YWNrIHJvbGxzIGFuZCBzYXZpbmcgdGhyb3dzLiAoRGF5ICcgKyBkYXlzV2l0aG91dEZvb2QgKyAnIHdpdGhvdXQgZm9vZCknLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgfQogIH0KICAvLyBPU0U6IHJlY292ZXIgMSBIUCBwZXIgbGV2ZWwgcGVyIGZ1bGwgbmlnaHQncyByZXN0CiAgY29uc3QgaHBHYWluZWQgPSBwYy5sZXZlbCB8fCAxOwogIHBjLmhwID0gTWF0aC5taW4ocGMubWF4aHAsIHBjLmhwICsgaHBHYWluZWQpOwogIC8vIENsZWFyIGR1bmdlb24gZmF0aWd1ZQogIHR1cm5zV2l0aG91dFJlc3QgPSAwOwogIGZhdGlndWVQZW5hbHR5ID0gMDsKICByZXN0RGVidCA9IDA7CiAgLy8gVG9yY2hlcy9sYW50ZXJuIGJ1cm4gZHVyaW5nIHJlc3QgKDggaG91cnMgPSA0OCB0dXJucykKICBkdW5nZW9uVHVybnMgKz0gNDg7CiAgY29uc29sZS5sb2coJ1tSZXN0XSBGdWxsIHJlc3QuIEhQKycgKyBocEdhaW5lZCArICcgLT4gJyArIHBjLmhwICsgJy4gUmF0aW9ucyBsZWZ0OicgKyByYXRpb25zTGVmdCArICcuIFN0YXJ2YXRpb24gcGVuYWx0eTonICsgc3RhcnZhdGlvblBlbmFsdHkpOwp9CgpmdW5jdGlvbiBidWlsZFJlc291cmNlQmxvY2soKSB7CiAgY29uc3Qgd2FybmluZ3MgPSBbXTsKICBjb25zdCBzdGF0dXMgPSBbXTsKCiAgLy8gV2FuZGVyaW5nIG1vbnN0ZXIKICBpZiAod2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlKSB7CiAgICB3YXJuaW5ncy5wdXNoKCdXQU5ERVJJTkcgTU9OU1RFUiBDSEVDSyBUUklHR0VSRUQgW2Q2PTFdIC0tIGludHJvZHVjZSBhbiBhcHByb3ByaWF0ZSB3YW5kZXJpbmcgbW9uc3RlciBlbmNvdW50ZXIgZnJvbSB0aGUgbW9kdWxlIG5hdHVyYWxseSBpbnRvIHRoZSBjdXJyZW50IHNjZW5lLicpOwogICAgd2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlID0gZmFsc2U7IC8vIGNsZWFyIGFmdGVyIGluamVjdGluZwogIH0KCiAgLy8gTGlnaHQKICBpZiAoIWlzQ2FycnlpbmdMaWdodCkgewogICAgd2FybmluZ3MucHVzaCgnREFSS05FU1MgLS0gcGFydHkgaGFzIG5vIGxpZ2h0IHNvdXJjZS4gSW4gT1NFOiBtb25zdGVycyB0aGF0IGNhbiBzZWUgaW4gZGFyayBoYXZlIGZ1bGwgYWR2YW50YWdlOyBwYXJ0eSBzdWZmZXJzIC00IHRvIGF0dGFjayByb2xsczsgc2VhcmNoaW5nIGlzIGltcG9zc2libGU7IHN1cnByaXNlIG9uIDEtNC9kNi4nKTsKICB9IGVsc2UgaWYgKHRvcmNoVHVybnNMZWZ0ID4gMCAmJiB0b3JjaFR1cm5zTGVmdCA8PSAyKSB7CiAgICB3YXJuaW5ncy5wdXNoKCdUT1JDSCBORUFSTFkgT1VUIC0tICcgKyB0b3JjaFR1cm5zTGVmdCArICcgdHVybihzKSByZW1haW5pbmcuIE1lbnRpb24gdGhpcyBpbiBuYXJyYXRpb24uJyk7CiAgfSBlbHNlIGlmICh0b3JjaFR1cm5zTGVmdCA9PT0gMCAmJiB0b3JjaFR1cm5zTGVmdCA8PSAwICYmIGhhc0xhbnRlcm4pIHsKICAgIHN0YXR1cy5wdXNoKCdMaWdodDogbGFudGVybiAoJyArIGxhbnRlcm5PaWxGbGFza3NMZWZ0ICsgJyBmbGFzayhzKSByZW1haW5pbmcsIH4nICsgKGxhbnRlcm5PaWxGbGFza3NMZWZ0ICogMjQpICsgJyB0dXJucyknKTsKICB9IGVsc2UgewogICAgc3RhdHVzLnB1c2goJ0xpZ2h0OiB0b3JjaCAoJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJucyByZW1haW5pbmcpJyk7CiAgfQoKICAvLyBIdW5nZXIgLS0gaG91c2UgcnVsZTogLTEgdG8gYXR0YWNrIHJvbGxzIGFuZCBzYXZlcyBwZXIgZGF5IGFmdGVyIGRheSAzIHdpdGhvdXQgZm9vZAogIGlmIChzdGFydmF0aW9uUGVuYWx0eSA+IDApIHsKICAgIHdhcm5pbmdzLnB1c2goJ1NUQVJWQVRJT04gUEVOQUxUWSBBQ1RJVkU6IC0nICsgc3RhcnZhdGlvblBlbmFsdHkgKyAnIHRvIEFMTCBhdHRhY2sgcm9sbHMgYW5kIHNhdmluZyB0aHJvd3MgKGRheSAnICsgZGF5c1dpdGhvdXRGb29kICsgJyB3aXRob3V0IGZvb2QpLiBBcHBseSB0aGlzIHRvIGV2ZXJ5IHJvbGwuIENoYXJhY3RlciBuZWVkcyBmb29kIHVyZ2VudGx5LicpOwogIH0gZWxzZSBpZiAoZGF5c1dpdGhvdXRGb29kID4gMCkgewogICAgd2FybmluZ3MucHVzaCgnSFVOR1JZOiBEYXkgJyArIGRheXNXaXRob3V0Rm9vZCArICcgd2l0aG91dCBmb29kLiBQZW5hbHR5ICgtMS9kYXkpIGJlZ2lucyBhZnRlciBkYXkgMy4gQ2hhcmFjdGVyIHNob3VsZCBiZSB2aXNpYmx5IHdlYWtlbmluZy4nKTsKICB9IGVsc2UgaWYgKHJhdGlvbnNMZWZ0ID09PSAwKSB7CiAgICBzdGF0dXMucHVzaCgnTm8gcmF0aW9ucyAobm90IHlldCBodW5ncnkgLS0gcGVuYWx0eSBzdGFydHMgYWZ0ZXIgMyBkYXlzKScpOwogIH0gZWxzZSBpZiAocmF0aW9uc0xlZnQgPT09IDEpIHsKICAgIHdhcm5pbmdzLnB1c2goJ0xBU1QgUkFUSU9OIC0tIG1lbnRpb24gdGhpcyBpbiBuYXJyYXRpb24uJyk7CiAgfSBlbHNlIHsKICAgIHN0YXR1cy5wdXNoKCdSYXRpb25zOiAnICsgcmF0aW9uc0xlZnQgKyAnIHJlbWFpbmluZycpOwogIH0KCiAgLy8gT1NFIGR1bmdlb24gcmVzdCBydWxlIC0tIG9ubHkgYXBwbGllcyB1bmRlcmdyb3VuZAogIGlmIChpc0luRHVuZ2VvbigpKSB7CiAgICBpZiAodHVybnNXaXRob3V0UmVzdCA+PSA2KSB7CiAgICAgIHdhcm5pbmdzLnB1c2goJ0RVTkdFT04gUkVTVCBPVkVSRFVFOiAnICsgdHVybnNXaXRob3V0UmVzdCArICcgdHVybnMgd2l0aG91dCByZXN0LiBPU0UgcnVsZTogcGFydHkgbXVzdCByZXN0IDEgdHVybiBwZXIgNiBleHBsb3JlZCBvciBzdWZmZXIgd2FuZGVyaW5nIG1vbnN0ZXIgY2hlY2sgcGVuYWx0eS4gUmVtaW5kIHBhcnR5IHRvIHJlc3QuJyk7CiAgICB9IGVsc2UgaWYgKHR1cm5zV2l0aG91dFJlc3QgPj0gNCkgewogICAgICBzdGF0dXMucHVzaCgnRHVuZ2VvbiByZXN0OiAnICsgdHVybnNXaXRob3V0UmVzdCArICcvNiB0dXJucyAocmVzdCAxIHR1cm4gc29vbiB0byBhdm9pZCB3YW5kZXJpbmcgbW9uc3RlciBwZW5hbHR5KScpOwogICAgfQogIH0KCiAgLy8gVHVybiBjb3VudAogIGNvbnN0IGhvdXJzID0gTWF0aC5mbG9vcihkdW5nZW9uVHVybnMgLyA2KTsKICBjb25zdCBtaW5zID0gKGR1bmdlb25UdXJucyAlIDYpICogMTA7CiAgc3RhdHVzLnB1c2goJ1R1cm4gJyArIGR1bmdlb25UdXJucyArICcgKCcgKyBob3VycyArICdoICcgKyBtaW5zICsgJ20gaW4gZHVuZ2VvbiknKTsKCiAgY29uc3QgbGluZXMgPSBbXTsKICBpZiAod2FybmluZ3MubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCdSRVNPVVJDRSBXQVJOSU5HUyAoaW5jb3Jwb3JhdGUgbmF0dXJhbGx5IGludG8gbmFycmF0aW9uKTonKTsKICAgIHdhcm5pbmdzLmZvckVhY2godyA9PiBsaW5lcy5wdXNoKCcgICcgKyB3KSk7CiAgfQogIGlmIChzdGF0dXMubGVuZ3RoKSBsaW5lcy5wdXNoKCdSZXNvdXJjZXM6ICcgKyBzdGF0dXMuam9pbignIHwgJykpOwogIHJldHVybiBsaW5lcy5sZW5ndGggPyBsaW5lcy5qb2luKCdbLl1uJykgOiAnJzsKfQoKYXN5bmMgZnVuY3Rpb24gZ2VuZXJhdGVHTUJyaWVmaW5nKCkgewogIGlmICghdXNlT2xsYW1hKSByZXR1cm47IC8vIENsYXVkZSBoYW5kbGVzIHRoaXMgbmF0aXZlbHkKCiAgLy8gSWYgd2UgaGF2ZSBhIC5kbmRtb2QgZmlsZSBsb2FkZWQsIGJ1aWxkIHRoZSBicmllZmluZyBkaXJlY3RseSBmcm9tIGl0cwogIC8vIHN0cnVjdHVyZWQgZGF0YSAtLSBubyBBSSBjYWxsIG5lZWRlZCwgaW5zdGFudCBhbmQgMTAwJSBhY2N1cmF0ZS4KICBpZiAobG9hZGVkTW9kdWxlRGF0YSAmJiBsb2FkZWRNb2R1bGVEYXRhLm5wY3MgJiYgbG9hZGVkTW9kdWxlRGF0YS5ucGNzLmxlbmd0aCkgewogICAgY29uc29sZS5sb2coJ1tCcmllZmluZ10gQnVpbGRpbmcgZnJvbSAuZG5kbW9kIHN0cnVjdHVyZWQgZGF0YSAtLSBza2lwcGluZyBBSSBjYWxsJyk7CiAgICBidWlsZEJyaWVmaW5nRnJvbURuZG1vZChsb2FkZWRNb2R1bGVEYXRhKTsKICAgIHJldHVybjsKICB9CgogIGlmICghbW9kdWxlVGV4dCB8fCBtb2R1bGVUZXh0Lmxlbmd0aCA8IDEwMCkgcmV0dXJuOwoKICBhZGRFbnRyeVJhdygnUHJlcGFyaW5nIEdNIGJyaWVmaW5nIC0tIHRoaXMgdGFrZXMgYWJvdXQgMzAgc2Vjb25kcy4uLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CgogIGNvbnN0IGJyaWVmaW5nUHJvbXB0ID0gYFlvdSBhcmUgcHJlcGFyaW5nIHRvIHJ1biBhIHRhYmxldG9wIFJQRyBtb2R1bGUgYXMgR2FtZSBNYXN0ZXIuIFJlYWQgdGhlIG1vZHVsZSBiZWxvdyBhbmQgcHJvZHVjZSBhIHN0cnVjdHVyZWQgR00gYnJpZWZpbmcgaW4gSlNPTiBmb3JtYXQgT05MWS4gTm8gbWFya2Rvd24sIG5vIHByZWFtYmxlIC0tIHB1cmUgSlNPTi4KCk1PRFVMRToKJHttb2R1bGVUZXh0LnN1YnN0cmluZygwLCAxNjAwMCl9CgpQcm9kdWNlIHRoaXMgZXhhY3QgSlNPTiBzdHJ1Y3R1cmU6CnsKICAia2V5X2ZhY3RzIjogWwogICAgIlRoZSBtb3N0IGltcG9ydGFudCBmYWN0IHRoZSBHTSBtdXN0IG5ldmVyIGZvcmdldCIsCiAgICAiU2Vjb25kIG1vc3QgaW1wb3J0YW50IGZhY3QiLAogICAgIlRoaXJkIiwKICAgICJGb3VydGgiLAogICAgIkZpZnRoIiwKICAgICJTaXh0aCIsCiAgICAiU2V2ZW50aCIsCiAgICAiRWlnaHRoIiwKICAgICJOaW50aCIsCiAgICAiVGVudGgiCiAgXSwKICAiY29yZV90ZW5zaW9uIjogIk9uZSBzZW50ZW5jZTogdGhlIGNlbnRyYWwgZHJhbWF0aWMgY29uZmxpY3Qgb2YgdGhpcyBhZHZlbnR1cmUiLAogICJ2aWN0b3J5X2NvbmRpdGlvbiI6ICJPbmUgc2VudGVuY2U6IGhvdyB0aGUgYWR2ZW50dXJlIGNhbiBiZSB3b24iLAogICJtYWluX3ZpbGxhaW5fb3JfdGhyZWF0IjogIk5hbWUgYW5kIG9uZS1zZW50ZW5jZSBkZXNjcmlwdGlvbiBvZiB0aGUgcHJpbWFyeSBhbnRhZ29uaXN0IG9yIHRocmVhdCIsCiAgIm5wY3MiOiBbCiAgICB7CiAgICAgICJuYW1lIjogIk5QQyBuYW1lIGV4YWN0bHkgYXMgaW4gbW9kdWxlIiwKICAgICAgInJvbGUiOiAiVGhlaXIgcm9sZSBpbiBvbmUgcGhyYXNlIiwKICAgICAgInBlcnNvbmFsaXR5IjogIjItMyB3b3JkcyBkZXNjcmliaW5nIGhvdyB0aGV5IHNwZWFrIGFuZCBhY3QiLAogICAgICAia25vd3MiOiBbCiAgICAgICAgIlNwZWNpZmljIGZhY3QgdGhpcyBOUEMgZ2VudWluZWx5IGtub3dzIGFuZCBjYW4gc2hhcmUgZnJlZWx5IiwKICAgICAgICAiQW5vdGhlciBmYWN0IHRoZXkgY2FuIHNoYXJlIiwKICAgICAgICAiQSB0aGlyZCBpZiByZWxldmFudCIKICAgICAgXSwKICAgICAgIndpbGxfc2hhcmVfaWYiOiAiQ29uZGl0aW9uIHVuZGVyIHdoaWNoIHRoZXkgc2hhcmUgc2Vuc2l0aXZlIGluZm9ybWF0aW9uIChlLmcuICdpZiBwYXJ0eSBlYXJucyB0cnVzdCcsICduZXZlcicsICdpZiBicmliZWQnLCAnaWYgZnJpZ2h0ZW5lZCcpIiwKICAgICAgIndvbnRfc2hhcmUiOiBbCiAgICAgICAgIlNvbWV0aGluZyB0aGV5IGtub3cgYnV0IGFjdGl2ZWx5IGhpZGUiLAogICAgICAgICJBbm90aGVyIHNlY3JldCB0aGV5IHByb3RlY3QiCiAgICAgIF0sCiAgICAgICJjYW5ub3Rfa25vdyI6IFsKICAgICAgICAiSW5mb3JtYXRpb24gdGhpcyBOUEMgaGFzIE5PIFdBWSBvZiBrbm93aW5nIC0tIG11c3QgcmVmdXNlIHdpdGggJ0kgZG9uJ3Qga25vdyciLAogICAgICAgICJBbm90aGVyIHRoaW5nIG91dHNpZGUgdGhlaXIga25vd2xlZGdlIgogICAgICBdLAogICAgICAiZGVmbGVjdGlvbl9waHJhc2UiOiAiRXhhY3Qgd29yZHMgdGhpcyBOUEMgdXNlcyB3aGVuIGFza2VkIHNvbWV0aGluZyB0aGV5IHdvbid0IG9yIGNhbid0IGFuc3dlci4gTWFrZSBpdCBpbi1jaGFyYWN0ZXIuIiwKICAgICAgImtub3dsZWRnZV9saW1pdCI6ICJPbmUgc2VudGVuY2UgZGVzY3JpYmluZyB0aGUgYWJzb2x1dGUgYm91bmRhcnkgb2YgdGhlaXIga25vd2xlZGdlIgogICAgfQogIF0sCiAgInNlY3JldF9pbmZvcm1hdGlvbiI6IFsKICAgICJQbG90IHNlY3JldCB0aGUgcGxheWVycyBzaG91bGQgTk9UIGtub3cgeWV0IiwKICAgICJBbm90aGVyIHNlY3JldCB0byBiZSByZXZlYWxlZCBsYXRlciIKICBdLAogICJpbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cyI6IFsKICAgICJTb21ldGhpbmcgdGhhdCBpcyB0cnVlIGluIHRoZSBtb2R1bGUgYnV0IE5PIE5QQyBrbm93cyAtLSBwbGF5ZXJzIGNhbiBvbmx5IGZpbmQgaXQgYnkgZXhwbG9yYXRpb24iLAogICAgIkFub3RoZXIgc3VjaCBmYWN0IgogIF0KfQoKQmUgc3BlY2lmaWMuIFVzZSBleGFjdCBuYW1lcyBmcm9tIHRoZSBtb2R1bGUuIEV2ZXJ5IE5QQyBpbiB0aGUgbW9kdWxlIHNob3VsZCBhcHBlYXIuIFRoZSBjYW5ub3Rfa25vdyBsaXN0IGlzIGNyaXRpY2FsIC0tIGluY2x1ZGUgYXQgbGVhc3QgMiBpdGVtcyBwZXIgTlBDLmA7CgogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FpJywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgICAgYXBpX2tleTogYXBpS2V5LAogICAgICAgIHN5c3RlbTogJ1lvdSBhcmUgYSBwcmVjaXNlIEpTT04gZ2VuZXJhdG9yLiBPdXRwdXQgb25seSB2YWxpZCBKU09OLiBObyBtYXJrZG93biBmZW5jZXMuIE5vIGV4cGxhbmF0aW9uLicsCiAgICAgICAgbWVzc2FnZXM6IFt7cm9sZTogJ3VzZXInLCBjb250ZW50OiBicmllZmluZ1Byb21wdH1dCiAgICAgIH0pCiAgICB9KTsKCiAgICBpZiAoIXJlc3Aub2spIHsKICAgICAgY29uc29sZS53YXJuKCdbQnJpZWZpbmddIEFQSSBlcnJvcjonLCByZXNwLnN0YXR1cyk7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzcC5qc29uKCk7CiAgICBpZiAoZGF0YS5lcnJvciB8fCAhZGF0YS5jb250ZW50KSB7CiAgICAgIGNvbnNvbGUud2FybignW0JyaWVmaW5nXSBObyBjb250ZW50OicsIGRhdGEuZXJyb3IpOwogICAgICByZXR1cm47CiAgICB9CgogICAgLy8gUGFyc2UgSlNPTiAtLSBzdHJpcCBhbnkgbWFya2Rvd24gZmVuY2VzIENsYXVkZSBtaWdodCBhZGQKICAgIGxldCByYXcgPSBkYXRhLmNvbnRlbnQudHJpbSgpOwogICAgLy8gUmVtb3ZlIG9wZW5pbmcgZmVuY2UgbGluZSAoZS5nLiBgYGBqc29uKQogICAgaWYgKHJhdy5zdGFydHNXaXRoKCdgJykpIHsKICAgICAgY29uc3QgZmlyc3ROZXdsaW5lID0gcmF3LmluZGV4T2YoJ1suXW4nKTsKICAgICAgaWYgKGZpcnN0TmV3bGluZSA+IDApIHJhdyA9IHJhdy5zdWJzdHJpbmcoZmlyc3ROZXdsaW5lICsgMSk7CiAgICB9CiAgICAvLyBSZW1vdmUgY2xvc2luZyBmZW5jZQogICAgaWYgKHJhdy50cmltRW5kKCkuZW5kc1dpdGgoJ2AnKSkgewogICAgICBjb25zdCBsYXN0RmVuY2UgPSByYXcubGFzdEluZGV4T2YoJ1suXW5gYGAnKTsKICAgICAgaWYgKGxhc3RGZW5jZSA+IDApIHJhdyA9IHJhdy5zdWJzdHJpbmcoMCwgbGFzdEZlbmNlKTsKICAgIH0KICAgIGNvbnN0IHN0YXJ0ID0gcmF3LmluZGV4T2YoJ3snKTsKICAgIGNvbnN0IGVuZCA9IHJhdy5sYXN0SW5kZXhPZignfScpICsgMTsKICAgIGlmIChzdGFydCA8IDAgfHwgZW5kIDw9IHN0YXJ0KSB7CiAgICAgIGNvbnNvbGUud2FybignW0JyaWVmaW5nXSBDb3VsZCBub3QgZmluZCBKU09OIGluIHJlc3BvbnNlJyk7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBjb25zdCBicmllZmluZyA9IEpTT04ucGFyc2UocmF3LnN1YnN0cmluZyhzdGFydCwgZW5kKSk7CgogICAgLy8gU3RvcmUga2V5IGZhY3RzIGFzIHBpbm5lZCBmYWN0cwogICAgaWYgKGJyaWVmaW5nLmtleV9mYWN0cykgewogICAgICBicmllZmluZy5rZXlfZmFjdHMuZm9yRWFjaChmID0+IHsKICAgICAgICBpZiAoIXBpbm5lZEZhY3RzLmluY2x1ZGVzKGYpKSBwaW5uZWRGYWN0cy5wdXNoKGYpOwogICAgICB9KTsKICAgIH0KCiAgICAvLyBCdWlsZCBOUEMga25vd2xlZGdlIG1hcCBmb3IgaW5qZWN0aW9uCiAgICBucGNLbm93bGVkZ2VNYXAgPSB7fTsKICAgIGlmIChicmllZmluZy5ucGNzKSB7CiAgICAgIGJyaWVmaW5nLm5wY3MuZm9yRWFjaChucGMgPT4gewogICAgICAgIG5wY0tub3dsZWRnZU1hcFtucGMubmFtZV0gPSB7CiAgICAgICAgICByb2xlOiBucGMucm9sZSB8fCAnJywKICAgICAgICAgIHBlcnNvbmFsaXR5OiBucGMucGVyc29uYWxpdHkgfHwgJycsCiAgICAgICAgICBrbm93czogbnBjLmtub3dzIHx8IFtdLAogICAgICAgICAgd2lsbF9zaGFyZV9pZjogbnBjLndpbGxfc2hhcmVfaWYgfHwgJ2ZyZWVseScsCiAgICAgICAgICB3b250X3NoYXJlOiBucGMud29udF9zaGFyZSB8fCBbXSwKICAgICAgICAgIGNhbm5vdF9rbm93OiBucGMuY2Fubm90X2tub3cgfHwgW10sCiAgICAgICAgICBkZWZsZWN0aW9uOiBucGMuZGVmbGVjdGlvbl9waHJhc2UgfHwgIkknbSBzb3JyeSwgSSBkb24ndCBrbm93IGFueXRoaW5nIG1vcmUgYWJvdXQgdGhhdC4iLAogICAgICAgICAgbGltaXQ6IG5wYy5rbm93bGVkZ2VfbGltaXQgfHwgJycKICAgICAgICB9OwogICAgICB9KTsKICAgIH0KCiAgICAvLyBCdWlsZCB0aGUgR00gYnJpZWZpbmcgdGV4dAogICAgY29uc3QgbGluZXMgPSBbXTsKICAgIGxpbmVzLnB1c2goJyBHTSBCUklFRklORyAocHJlLWFuYWx5c2VkIG1vZHVsZSBjaGVhdCBzaGVldCkgJyk7CiAgICBsaW5lcy5wdXNoKCdDb3JlIHRlbnNpb246ICcgKyAoYnJpZWZpbmcuY29yZV90ZW5zaW9uIHx8ICcnKSk7CiAgICBsaW5lcy5wdXNoKCdWaWN0b3J5OiAnICsgKGJyaWVmaW5nLnZpY3RvcnlfY29uZGl0aW9uIHx8ICcnKSk7CiAgICBsaW5lcy5wdXNoKCdQcmltYXJ5IHRocmVhdDogJyArIChicmllZmluZy5tYWluX3ZpbGxhaW5fb3JfdGhyZWF0IHx8ICcnKSk7CiAgICBsaW5lcy5wdXNoKCcnKTsKICAgIGxpbmVzLnB1c2goJ0tFWSBGQUNUUyAobmV2ZXIgZm9yZ2V0IG9yIGNvbnRyYWRpY3QgdGhlc2UpOicpOwogICAgKGJyaWVmaW5nLmtleV9mYWN0cyB8fCBbXSkuZm9yRWFjaCgoZixpKSA9PiBsaW5lcy5wdXNoKChpKzEpICsgJy4gJyArIGYpKTsKCiAgICBpZiAoYnJpZWZpbmcuc2VjcmV0X2luZm9ybWF0aW9uICYmIGJyaWVmaW5nLnNlY3JldF9pbmZvcm1hdGlvbi5sZW5ndGgpIHsKICAgICAgbGluZXMucHVzaCgnJyk7CiAgICAgIGxpbmVzLnB1c2goJ1NFQ1JFVFMgKHBsYXllcnMgbXVzdCBOT1Qga25vdyB0aGVzZSB5ZXQgLS0gbmV2ZXIgcmV2ZWFsIHRocm91Z2ggTlBDcyk6Jyk7CiAgICAgIGJyaWVmaW5nLnNlY3JldF9pbmZvcm1hdGlvbi5mb3JFYWNoKHMgPT4gbGluZXMucHVzaCgnICBTRUNSRVQ6ICcgKyBzKSk7CiAgICB9CgogICAgaWYgKGJyaWVmaW5nLmluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzICYmIGJyaWVmaW5nLmluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzLmxlbmd0aCkgewogICAgICBsaW5lcy5wdXNoKCcnKTsKICAgICAgbGluZXMucHVzaCgnRElTQ09WRVJBQkxFIE9OTFkgQlkgRVhQTE9SQVRJT04gKG5vIE5QQyBjYW4gdGVsbCB0aGVtIHRoaXMpOicpOwogICAgICBicmllZmluZy5pbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cy5mb3JFYWNoKHMgPT4gbGluZXMucHVzaCgnICBFWFBMT1JFIE9OTFk6ICcgKyBzKSk7CiAgICB9CgogICAgbGluZXMucHVzaCgnJyk7CiAgICBsaW5lcy5wdXNoKCcgTlBDIEtOT1dMRURHRSBNQVAgKGhhcmQgbGltaXRzIC0tIGVuZm9yY2Ugc3RyaWN0bHkpICcpOwogICAgbGluZXMucHVzaCgnQ1JJVElDQUwgUlVMRTogV2hlbiBhbiBOUEMgcmVhY2hlcyB0aGUgbGltaXQgb2YgdGhlaXIga25vd2xlZGdlLCB0aGV5IHNheSBzbycpOwogICAgbGluZXMucHVzaCgnaW4gY2hhcmFjdGVyLiBUaGV5IGRvIE5PVCBpbnZlbnQgaW5mb3JtYXRpb24uIFRoZXkgZG8gTk9UIHJldmVhbCBzZWNyZXRzLicpOwogICAgbGluZXMucHVzaCgnVXNlIHRoZWlyIGRlZmxlY3Rpb24gcGhyYXNlIGV4YWN0bHkgb3IgYSBuYXR1cmFsIHZhcmlhbnQgb2YgaXQuJyk7CiAgICBsaW5lcy5wdXNoKCcnKTsKICAgIE9iamVjdC5lbnRyaWVzKG5wY0tub3dsZWRnZU1hcCkuZm9yRWFjaCgoW25hbWUsIGRhdGFdKSA9PiB7CiAgICAgIGxpbmVzLnB1c2goJ1snICsgbmFtZSArICddIC0tICcgKyBkYXRhLnJvbGUgKyAnIC0tICcgKyBkYXRhLnBlcnNvbmFsaXR5KTsKICAgICAgaWYgKGRhdGEua25vd3MubGVuZ3RoKSBsaW5lcy5wdXNoKCcgIENBTiBTSEFSRTogJyArIGRhdGEua25vd3Muam9pbignIHwgJykpOwogICAgICBsaW5lcy5wdXNoKCcgIFdJTEwgU0hBUkU6ICcgKyBkYXRhLndpbGxfc2hhcmVfaWYpOwogICAgICBpZiAoZGF0YS53b250X3NoYXJlLmxlbmd0aCkgbGluZXMucHVzaCgnICBBQ1RJVkVMWSBISURFUzogJyArIGRhdGEud29udF9zaGFyZS5qb2luKCcgfCAnKSk7CiAgICAgIGlmIChkYXRhLmNhbm5vdF9rbm93Lmxlbmd0aCkgbGluZXMucHVzaCgnICBDQU5OT1QgS05PVyAoc2F5IHRoZXkgZG8gbm90IGtub3cpOiAnICsgZGF0YS5jYW5ub3Rfa25vdy5qb2luKCcgfCAnKSk7CiAgICAgIGxpbmVzLnB1c2goJyAgREVGTEVDVElPTjogJyArIGRhdGEuZGVmbGVjdGlvbik7CiAgICAgIGxpbmVzLnB1c2goJycpOwogICAgfSk7CgogICAgZ21CcmllZmluZyA9IGxpbmVzLmpvaW4oJ1suXW4nKTsKCiAgICAvLyBSZWJ1aWxkIHN5c3RlbSBwcm9tcHQgd2l0aCBicmllZmluZyBiYWtlZCBpbgogICAgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKCiAgICBjb25zb2xlLmxvZygnW0JyaWVmaW5nXSBDb21wbGV0ZS4gTlBDcyBtYXBwZWQ6JywgT2JqZWN0LmtleXMobnBjS25vd2xlZGdlTWFwKS5sZW5ndGgpOwogICAgYWRkRW50cnlSYXcoJ0dNIGJyaWVmaW5nIGNvbXBsZXRlLiAnICsgT2JqZWN0LmtleXMobnBjS25vd2xlZGdlTWFwKS5sZW5ndGggKyAnIE5QQ3MgbWFwcGVkIHdpdGgga25vd2xlZGdlIGJvdW5kYXJpZXMuJywgJ3N5c3RlbScsICdfX2dtX18nKTsKCiAgfSBjYXRjaChlKSB7CiAgICBjb25zb2xlLndhcm4oJ1tCcmllZmluZ10gRmFpbGVkOicsIGUubWVzc2FnZSk7CiAgICAvLyBOb24tZmF0YWwgLS0gZ2FtZSBjb250aW51ZXMgd2l0aG91dCBicmllZmluZwogICAgYWRkRW50cnlSYXcoJyEgR00gYnJpZWZpbmcgc2tpcHBlZCAod2lsbCB1c2UgbW9kdWxlIHRleHQgZGlyZWN0bHkpLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgfQp9CgpmdW5jdGlvbiBidWlsZENvbXBhY3RNb2R1bGVSZWYoKSB7CiAgY29uc3QgbW9kID0gbG9hZGVkTW9kdWxlRGF0YTsKICBpZiAoIW1vZCB8fCAhbW9kLnRpdGxlKSByZXR1cm4gbW9kdWxlVGV4dDsKCiAgY29uc3QgbGluZXMgPSBbXTsKICBsaW5lcy5wdXNoKCdNT0RVTEU6ICcgKyBtb2QudGl0bGUpOwogIGxpbmVzLnB1c2goJ1NldHRpbmc6ICcgKyAobW9kLnNldHRpbmcgfHwgJycpKTsKICBsaW5lcy5wdXNoKCdMZXZlbHM6ICcgKyAobW9kLmxldmVsX3JhbmdlIHx8ICcnKSk7CiAgbGluZXMucHVzaCgnJyk7CgogIC8vIENvcmUgdGVuc2lvbiBhbmQgdmljdG9yeQogIGxpbmVzLnB1c2goJ0NPUkUgVEVOU0lPTjogJyArIChtb2QuY29yZV90ZW5zaW9uIHx8ICcnKSk7CiAgbGluZXMucHVzaCgnVklDVE9SWTogJyArIChtb2QudmljdG9yeV9jb25kaXRpb25zIHx8ICcnKSk7CiAgbGluZXMucHVzaCgnTUFJTiBUSFJFQVQ6ICcgKyAobW9kLm1haW5fdGhyZWF0IHx8ICcnKSk7CiAgbGluZXMucHVzaCgnJyk7CgogIC8vIEN1cnJlbnQgbG9jYXRpb24gLS0gZnVsbCBkZXNjcmlwdGlvbgogIGNvbnN0IGN1cnJlbnRMb2MgPSAobW9kLmxvY2F0aW9ucyB8fCBbXSkuZmluZChsID0+IGwuaWQgPT09IChwYy5sb2N0YWcgfHwgJycpKTsKICBpZiAoY3VycmVudExvYykgewogICAgbGluZXMucHVzaCgnQ1VSUkVOVCBMT0NBVElPTjogJyArIGN1cnJlbnRMb2MubmFtZSk7CiAgICBsaW5lcy5wdXNoKGN1cnJlbnRMb2MuZ21fZGVzY3JpcHRpb24gfHwgJycpOwogICAgaWYgKGN1cnJlbnRMb2MubW9uc3RlcnMgJiYgY3VycmVudExvYy5tb25zdGVycy5sZW5ndGgpIHsKICAgICAgbGluZXMucHVzaCgnTU9OU1RFUlMgSEVSRTogJyArIGN1cnJlbnRMb2MubW9uc3RlcnMubWFwKG0gPT4gbS5uYW1lICsgJyB4JyArIG0uY291bnQgKyAnIChIUDonICsgbS5ocF9lYWNoICsgJyBBQzonICsgbS5hYyArICcpJykuam9pbignLCAnKSk7CiAgICB9CiAgICBpZiAoY3VycmVudExvYy5ucGNzX3ByZXNlbnQgJiYgY3VycmVudExvYy5ucGNzX3ByZXNlbnQubGVuZ3RoKSB7CiAgICAgIGxpbmVzLnB1c2goJ05QQ1MgSEVSRTogJyArIGN1cnJlbnRMb2MubnBjc19wcmVzZW50LmpvaW4oJywgJykpOwogICAgfQogICAgaWYgKGN1cnJlbnRMb2MuaGlkZGVuX2ZlYXR1cmVzICYmIGN1cnJlbnRMb2MuaGlkZGVuX2ZlYXR1cmVzLmxlbmd0aCkgewogICAgICBsaW5lcy5wdXNoKCdISURERU4gKEdNIG9ubHkpOiAnICsgY3VycmVudExvYy5oaWRkZW5fZmVhdHVyZXMuam9pbignIHwgJykpOwogICAgfQogICAgaWYgKGN1cnJlbnRMb2MuZXhpdHMpIHsKICAgICAgbGluZXMucHVzaCgnRVhJVFM6ICcgKyBPYmplY3QuZW50cmllcyhjdXJyZW50TG9jLmV4aXRzKS5tYXAoKFtkLHRdKSA9PiBkICsgJyAtPiAnICsgdCkuam9pbignLCAnKSk7CiAgICB9CiAgICBsaW5lcy5wdXNoKCcnKTsKICB9CgogIC8vIEFkamFjZW50IGxvY2F0aW9ucyAoZXhpdHMgZnJvbSBjdXJyZW50KQogIGlmIChjdXJyZW50TG9jICYmIGN1cnJlbnRMb2MuZXhpdHMpIHsKICAgIE9iamVjdC5lbnRyaWVzKGN1cnJlbnRMb2MuZXhpdHMpLmZvckVhY2goKFtkaXIsIHRhcmdldElkXSkgPT4gewogICAgICBjb25zdCBhZGogPSAobW9kLmxvY2F0aW9ucyB8fCBbXSkuZmluZChsID0+IGwuaWQgPT09IHRhcmdldElkKTsKICAgICAgaWYgKGFkaikgewogICAgICAgIGxpbmVzLnB1c2goJ1RPIFRIRSAnICsgZGlyLnRvVXBwZXJDYXNlKCkgKyAnICgnICsgYWRqLm5hbWUgKyAnKTogJyArIChhZGoucmVhZF9hbG91ZCB8fCBhZGouZ21fZGVzY3JpcHRpb24gfHwgJycpLnN1YnN0cmluZygwLCAxMjApICsgJy4uLicpOwogICAgICB9CiAgICB9KTsKICAgIGxpbmVzLnB1c2goJycpOwogIH0KCiAgLy8gQ29tcGFjdCBOUEMgbGlzdCAobmFtZSArIHJvbGUgKyAxLWxpbmUgcGVyc29uYWxpdHkgb25seSkKICBpZiAobW9kLm5wY3MgJiYgbW9kLm5wY3MubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCdLRVkgTlBDcyBJTiBUSElTIE1PRFVMRTonKTsKICAgIG1vZC5ucGNzLmZvckVhY2gobiA9PiB7CiAgICAgIGxpbmVzLnB1c2goJyAgJyArIG4ubmFtZSArICcgWycgKyAobi5yb2xlIHx8ICcnKSArICddIC0tICcgKyAobi5wZXJzb25hbGl0eSB8fCAnJykuc3Vic3RyaW5nKDAsIDgwKSk7CiAgICB9KTsKICAgIGxpbmVzLnB1c2goJycpOwogIH0KCiAgLy8gR00gYnJpZWZpbmcgaXMgaW5qZWN0ZWQgc2VwYXJhdGVseSAtLSBkb24ndCByZXBlYXQga2V5IGZhY3RzIGhlcmUKICBsaW5lcy5wdXNoKCcoRnVsbCBOUEMga25vd2xlZGdlIG1hcCBhbmQga2V5IGZhY3RzIGFyZSBpbiB0aGUgR00gQlJJRUZJTkcgc2VjdGlvbiBhYm92ZS4pJyk7CgogIHJldHVybiBsaW5lcy5qb2luKCdbLl1uJyk7Cn0KCmZ1bmN0aW9uIGJ1aWxkQnJpZWZpbmdGcm9tRG5kbW9kKG1vZCkgewogIC8vIEJ1aWxkIE5QQyBrbm93bGVkZ2UgbWFwIGRpcmVjdGx5IGZyb20gLmRuZG1vZCBzdHJ1Y3R1cmVkIGRhdGEKICBucGNLbm93bGVkZ2VNYXAgPSB7fTsKICAobW9kLm5wY3MgfHwgW10pLmZvckVhY2gobnBjID0+IHsKICAgIG5wY0tub3dsZWRnZU1hcFtucGMubmFtZV0gPSB7CiAgICAgIHJvbGU6IG5wYy5yb2xlIHx8ICcnLAogICAgICBwZXJzb25hbGl0eTogbnBjLnBlcnNvbmFsaXR5IHx8ICcnLAogICAgICBrbm93czogbnBjLmtub3dzX2FuZF9jYW5fc2hhcmUgfHwgbnBjLmtub3dzIHx8IFtdLAogICAgICB3aWxsX3NoYXJlX2lmOiBucGMud2lsbF9zaGFyZV9pZiB8fCAnZnJlZWx5JywKICAgICAgd29udF9zaGFyZTogbnBjLmFjdGl2ZWx5X2hpZGVzIHx8IG5wYy53b250X3NoYXJlIHx8IFtdLAogICAgICBjYW5ub3Rfa25vdzogbnBjLmNhbm5vdF9rbm93IHx8IFtdLAogICAgICBkZWZsZWN0aW9uOiBucGMuZGVmbGVjdGlvbl9waHJhc2UgfHwgIkknbSBzb3JyeSwgSSBkb24ndCBrbm93IGFueXRoaW5nIG1vcmUgYWJvdXQgdGhhdC4iLAogICAgICBsaW1pdDogbnBjLmtub3dsZWRnZV9saW1pdCB8fCAnJwogICAgfTsKICB9KTsKCiAgLy8gUGluIGtleSBmYWN0cwogIChtb2Qua2V5X2ZhY3RzIHx8IFtdKS5mb3JFYWNoKGYgPT4gewogICAgaWYgKCFwaW5uZWRGYWN0cy5pbmNsdWRlcyhmKSkgcGlubmVkRmFjdHMucHVzaChmKTsKICB9KTsKCiAgLy8gQnVpbGQgdGhlIEdNIGJyaWVmaW5nIHRleHQKICBjb25zdCBsaW5lcyA9IFtdOwogIGxpbmVzLnB1c2goJyBHTSBCUklFRklORyAoZnJvbSAuZG5kbW9kIHN0cnVjdHVyZWQgZGF0YSkgJyk7CiAgbGluZXMucHVzaCgnQ29yZSB0ZW5zaW9uOiAnICsgKG1vZC5jb3JlX3RlbnNpb24gfHwgJycpKTsKICBsaW5lcy5wdXNoKCdWaWN0b3J5OiAnICsgKG1vZC52aWN0b3J5X2NvbmRpdGlvbnMgfHwgJycpKTsKICBsaW5lcy5wdXNoKCdQcmltYXJ5IHRocmVhdDogJyArIChtb2QubWFpbl90aHJlYXQgfHwgJycpKTsKICBsaW5lcy5wdXNoKCcnKTsKICBsaW5lcy5wdXNoKCdLRVkgRkFDVFMgKG5ldmVyIGZvcmdldCBvciBjb250cmFkaWN0IHRoZXNlKTonKTsKICAobW9kLmtleV9mYWN0cyB8fCBbXSkuZm9yRWFjaCgoZixpKSA9PiBsaW5lcy5wdXNoKChpKzEpICsgJy4gJyArIGYpKTsKCiAgaWYgKG1vZC5zZWNyZXRfaW5mb3JtYXRpb24gJiYgbW9kLnNlY3JldF9pbmZvcm1hdGlvbi5sZW5ndGgpIHsKICAgIGxpbmVzLnB1c2goJycpOwogICAgbGluZXMucHVzaCgnU0VDUkVUUyAocGxheWVycyBtdXN0IE5PVCBrbm93IHRoZXNlIHlldCAtLSBuZXZlciByZXZlYWwgdGhyb3VnaCBOUENzKTonKTsKICAgIG1vZC5zZWNyZXRfaW5mb3JtYXRpb24uZm9yRWFjaChzID0+IGxpbmVzLnB1c2goJyAgU0VDUkVUOiAnICsgcykpOwogIH0KCiAgaWYgKG1vZC5pbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cyAmJiBtb2QuaW5mb3JtYXRpb25fdGhhdF9ub19ucGNfa25vd3MubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCcnKTsKICAgIGxpbmVzLnB1c2goJ0RJU0NPVkVSQUJMRSBPTkxZIEJZIEVYUExPUkFUSU9OIChubyBOUEMgY2FuIHRlbGwgdGhlbSB0aGlzKTonKTsKICAgIG1vZC5pbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cy5mb3JFYWNoKHMgPT4gbGluZXMucHVzaCgnICBFWFBMT1JFIE9OTFk6ICcgKyBzKSk7CiAgfQoKICBsaW5lcy5wdXNoKCcnKTsKICBsaW5lcy5wdXNoKCcgTlBDIEtOT1dMRURHRSBNQVAgKGhhcmQgbGltaXRzIC0tIGVuZm9yY2Ugc3RyaWN0bHkpICcpOwogIGxpbmVzLnB1c2goJ0NSSVRJQ0FMIFJVTEU6IFdoZW4gYW4gTlBDIHJlYWNoZXMgdGhlIGxpbWl0IG9mIHRoZWlyIGtub3dsZWRnZSwgdGhleSBzYXkgc28nKTsKICBsaW5lcy5wdXNoKCdpbiBjaGFyYWN0ZXIuIFRoZXkgZG8gTk9UIGludmVudCBpbmZvcm1hdGlvbi4gVGhleSBkbyBOT1QgcmV2ZWFsIHNlY3JldHMuJyk7CiAgbGluZXMucHVzaCgnVXNlIHRoZWlyIGRlZmxlY3Rpb24gcGhyYXNlIGV4YWN0bHkgb3IgYSBuYXR1cmFsIHZhcmlhbnQgb2YgaXQuJyk7CiAgbGluZXMucHVzaCgnJyk7CiAgT2JqZWN0LmVudHJpZXMobnBjS25vd2xlZGdlTWFwKS5mb3JFYWNoKChbbmFtZSwgZGF0YV0pID0+IHsKICAgIGxpbmVzLnB1c2goJ1snICsgbmFtZSArICddIC0tICcgKyBkYXRhLnJvbGUgKyAnIC0tICcgKyBkYXRhLnBlcnNvbmFsaXR5KTsKICAgIGlmIChkYXRhLmtub3dzLmxlbmd0aCkgbGluZXMucHVzaCgnICBDQU4gU0hBUkU6ICcgKyBkYXRhLmtub3dzLmpvaW4oJyB8ICcpKTsKICAgIGxpbmVzLnB1c2goJyAgV0lMTCBTSEFSRTogJyArIGRhdGEud2lsbF9zaGFyZV9pZik7CiAgICBpZiAoZGF0YS53b250X3NoYXJlLmxlbmd0aCkgbGluZXMucHVzaCgnICBBQ1RJVkVMWSBISURFUzogJyArIGRhdGEud29udF9zaGFyZS5qb2luKCcgfCAnKSk7CiAgICBpZiAoZGF0YS5jYW5ub3Rfa25vdy5sZW5ndGgpIGxpbmVzLnB1c2goJyAgQ0FOTk9UIEtOT1cgKHNheSB0aGV5IGRvIG5vdCBrbm93KTogJyArIGRhdGEuY2Fubm90X2tub3cuam9pbignIHwgJykpOwogICAgbGluZXMucHVzaCgnICBERUZMRUNUSU9OOiAnICsgZGF0YS5kZWZsZWN0aW9uKTsKICAgIGxpbmVzLnB1c2goJycpOwogIH0pOwoKICBnbUJyaWVmaW5nID0gbGluZXMuam9pbignWy5dbicpOwogIHN5c3RlbVByb21wdCA9IGJ1aWxkU3lzdGVtUHJvbXB0KCk7CgogIGNvbnN0IG5wY0NvdW50ID0gT2JqZWN0LmtleXMobnBjS25vd2xlZGdlTWFwKS5sZW5ndGg7CiAgY29uc29sZS5sb2coJ1tCcmllZmluZ10gQnVpbHQgZnJvbSAuZG5kbW9kIGRhdGEuIE5QQ3MgbWFwcGVkOicsIG5wY0NvdW50KTsKICBhZGRFbnRyeVJhdygnR00gYnJpZWZpbmcgcmVhZHkuICcgKyBucGNDb3VudCArICcgTlBDcyBtYXBwZWQgZnJvbSBtb2R1bGUgZGF0YS4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgpmdW5jdGlvbiBsYXVuY2hHYW1lKCkgewogIGNvbnNvbGUubG9nKCdbbGF1bmNoR2FtZV0gY2FsbGVkLCBwYXJ0eVBDczonLCBKU09OLnN0cmluZ2lmeShPYmplY3Qua2V5cyhwYXJ0eVBDcykpLCAnbW9kdWxlVGV4dCBsZW5ndGg6JywgbW9kdWxlVGV4dC5sZW5ndGgpOwogIE9iamVjdC5rZXlzKHBhcnR5UENzKS5mb3JFYWNoKChuLGkpID0+IHsgY29sb3JNYXBbbl0gPSBQTEFZRVJfQ09MT1JTW2klUExBWUVSX0NPTE9SUy5sZW5ndGhdOyB9KTsKCiAgLy8gQWx3YXlzIHJlYnVpbGQgc3lzdGVtIHByb21wdCBoZXJlIHRvIGJlIHNhZmUKICBpZiAoIXN5c3RlbVByb21wdCkgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKCiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RvcC1tb2QnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RvcC1ydWxlcycpLnRleHRDb250ZW50ID0gY2hvc2VuUnVsZXM7CiAgc2hvd1Jvb21Db2RlKCk7CgogIC8vIFNldCBBSSBpbmRpY2F0b3IgaW1tZWRpYXRlbHkgZnJvbSBzZXJ2ZXItaW5qZWN0ZWQgdmFsdWUgLS0gZG9uJ3Qgd2FpdCBmb3IgZmlyc3QgcmVzcG9uc2UKICBpZiAod2luZG93Ll9zZXJ2ZXJPbGxhbWFBdmFpbGFibGUpIHsKICAgIHVwZGF0ZUFpSW5kaWNhdG9yKCdvbGxhbWEnLCB3aW5kb3cuX3NlcnZlck9sbGFtYU1vZGVsIHx8ICdsb2NhbCcpOwogIH0gZWxzZSBpZiAoYXBpS2V5KSB7CiAgICB1cGRhdGVBaUluZGljYXRvcignY2xhdWRlJywgJycpOwogIH0KICBzaG93KCdzLWdhbWUnKTsKICB1cGRhdGVIVUQoKTsKICByZW5kZXJQYXJ0eVBhbmVsKCk7CgogIGlmICghbW9kdWxlVGV4dCkgewogICAgYWRkRW50cnlSYXcoJyEgTm8gbW9kdWxlIGxvYWRlZCAtLSByZXR1cm5pbmcgdG8gbW9kdWxlIHNlbGVjdGlvbi4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgc2V0VGltZW91dCgoKSA9PiB7IHNob3coJ3MtbmV3Z2FtZScpOyBsb2FkRG5kbW9kTGlzdCgpOyB9LCAxNTAwKTsKICAgIHJldHVybjsKICB9CgogIGNvbnN0IHBhcnR5RGVzYyA9IE9iamVjdC5lbnRyaWVzKHBhcnR5UENzKS5tYXAoKFtwbixwXSkgPT4KICAgIGAke3AubmFtZX0gKHBsYXllcjogJHtwbn0pOiBMZXZlbCAxICR7cC5yYWNlfSAke3AuY2xzfSwgSFAgJHtwLmhwfS8ke3AubWF4aHB9LCBBQyAke3AuYWN9LCBTVFIgJHtwLnN0YXRzLlNUUn0gREVYICR7cC5zdGF0cy5ERVh9IENPTiAke3Auc3RhdHMuQ09OfSBJTlQgJHtwLnN0YXRzLklOVH0gV0lTICR7cC5zdGF0cy5XSVN9IENIQSAke3Auc3RhdHMuQ0hBfSwgR29sZCAke3AuZ29sZH1ncC4gR2VhcjogJHtwLmludi5qb2luKCcsICcpfS4ke3Auc3BlY2lhbHMubGVuZ3RoPycgU3BlY2lhbCBhYmlsaXRpZXM6ICcrcC5zcGVjaWFscy5qb2luKCcsICcpOicnfWAKICApLmpvaW4oJ1suXW4nKTsKCiAgY29uc3QgX2ZpcnN0TG9jID0gbG9hZGVkTW9kdWxlRGF0YSAmJiBsb2FkZWRNb2R1bGVEYXRhLmxvY2F0aW9ucyAmJiBsb2FkZWRNb2R1bGVEYXRhLmxvY2F0aW9uc1swXTsKICBjb25zdCBfcmVhZEFsb3VkID0gX2ZpcnN0TG9jID8gKF9maXJzdExvYy5yZWFkX2Fsb3VkIHx8IF9maXJzdExvYy53aGF0X3BsYXllcnNfc2VlIHx8ICcnKSA6ICcnOwogIGNvbnN0IF9ob29rID0gbG9hZGVkTW9kdWxlRGF0YSA/IChsb2FkZWRNb2R1bGVEYXRhLmhvb2sgfHwgJycpIDogJyc7CiAgaWYgKF9maXJzdExvYyAmJiAoIXBjLmxvY3RhZyB8fCBwYy5sb2N0YWcgPT09ICcuLi4nKSkgewogICAgcGMubG9jdGFnID0gX2ZpcnN0TG9jLmlkIHx8ICcnOwogICAgcGMubG9jICAgID0gX2ZpcnN0TG9jLm5hbWUgfHwgJyc7CiAgfQogIGNvbnN0IGludHJvID0gYFBhcnR5OlxuJHtwYXJ0eURlc2N9XG5cbllvdSBhcmUgc3RhcnRpbmcgdGhlIG1vZHVsZTogIiR7bW9kdWxlTmFtZX0iLlxuXG5DUklUSUNBTCBJTlNUUlVDVElPTjpcblRoaXMgbW9kdWxlIGlzIGEgQ0xPU0VEIFdPUkxELiBZb3UgbWF5IE9OTFkgZGVzY3JpYmUgd2hhdCBpcyB3cml0dGVuIGluIHRoZSBtb2R1bGUuXG5EbyBOT1QgaW52ZW50IHRhdmVybnMsIGNpdGllcywgTlBDcywgb3IgYW55IGNvbnRlbnQgbm90IGluIHRoZSBtb2R1bGUuXG5cblRoZSBvcGVuaW5nIGxvY2F0aW9uIGlzIGRlc2NyaWJlZCBpbiB0aGUgbW9kdWxlIGFzIGZvbGxvd3MuIE5hcnJhdGUgT05MWSB0aGlzOlxuJHtfaG9vayA/ICdIT09LOiAnICsgX2hvb2sgKyAnXG5cbicgOiAnJ30ke19yZWFkQWxvdWQgPyAnT1BFTklORyBTQ0VORSAobmFycmF0ZSB0aGlzIGV4YWN0bHksIGluIGltbWVyc2l2ZSBwcm9zZSk6XG4nICsgX3JlYWRBbG91ZCA6ICdCZWdpbiBmcm9tIHRoZSBmaXJzdCBsb2NhdGlvbiBpbiB0aGUgbW9kdWxlLiBVc2Ugb25seSB3aGF0IGlzIHdyaXR0ZW4gdGhlcmUuJ31cblxuU3RhcnQgbmFycmF0aW5nIG5vdy4gRG8gbm90IGFkZCBhbnl0aGluZyBub3QgaW4gdGhlIG1vZHVsZS5gOwoKICAvLyBTeXN0ZW0gNjogSW5pdGlhbGlzZSByZXNvdXJjZXMgZnJvbSBjaGFyYWN0ZXIgaW52ZW50b3J5CiAgaW5pdFJlc291cmNlc0Zyb21JbnZlbnRvcnkoKTsKCiAgLy8gU2VlZCB0aW1lZCBldmVudHMgZnJvbSAuZG5kbW9kIGRhdGEKICBpZiAobG9hZGVkTW9kdWxlRGF0YSAmJiBsb2FkZWRNb2R1bGVEYXRhLnRpbWVkX2V2ZW50cykgewogICAgbG9hZGVkTW9kdWxlRGF0YS50aW1lZF9ldmVudHMuZm9yRWFjaChldiA9PiB7CiAgICAgIHBsYW50Q29uc2VxdWVuY2UoCiAgICAgICAgZXYuaWQgfHwgZXYubmFtZSwKICAgICAgICBwYXJzZUludChldi50cmlnZ2VyX3ZhbHVlKSB8fCA0LAogICAgICAgIGV2LmRlc2NyaXB0aW9uICsgKGV2LmVmZmVjdCA/ICcgLS0gJyArIGV2LmVmZmVjdCA6ICcnKSwKICAgICAgICBldi5yZXBlYXRpbmcgfHwgZmFsc2UKICAgICAgKTsKICAgIH0pOwogICAgY29uc29sZS5sb2coJ1tUaW1lZCBldmVudHNdIFNlZWRlZDonLCBsb2FkZWRNb2R1bGVEYXRhLnRpbWVkX2V2ZW50cy5sZW5ndGgsICdldmVudHMnKTsKICB9CgogIC8vIFY0OiBpbml0aWFsaXNlIHNwZWxsIHNsb3RzLCBzcGVsbGJvb2ssIGNsYXNzIGFiaWxpdGllcwogIGluaXRWNFN0YXRlKCk7CgogIC8vIFN0YXJ0IHRoZSBhZHZlbnR1cmUgLS0gdXNlIFY0IHBpcGVsaW5lIGlmIGF2YWlsYWJsZSwgZWxzZSBmYWxsYmFjawogIGNvbnN0IHN0YXJ0QWR2ZW50dXJlID0gKCkgPT4gewogICAgLy8gT3BlbmluZyBzY2VuZSBpcyBwdXJlIEdNIG5hcnJhdGlvbiwgbm90IGEgcGxheWVyIGFjdGlvbgogICAgLy8gVXNlIGNhbGxBSSBkaXJlY3RseSB0byBnZXQgb3BlbmluZyBwcm9zZSB3aXRob3V0IG1lY2hhbmljYWwgcmVzb2x1dGlvbgogICAgY2FsbEFJKGludHJvLCBmYWxzZSk7CiAgfTsKCiAgaWYgKHVzZU9sbGFtYSkgewogICAgZ2VuZXJhdGVHTUJyaWVmaW5nKCkKICAgICAgLnRoZW4oKCkgPT4gc3RhcnRBZHZlbnR1cmUoKSkKICAgICAgLmNhdGNoKGUgPT4gewogICAgICAgIGNvbnNvbGUuZXJyb3IoJ1tHTUJyaWVmaW5nXSBFcnJvcjonLCBlKTsKICAgICAgICBzdGFydEFkdmVudHVyZSgpOwogICAgICB9KTsKICB9IGVsc2UgewogICAgc3RhcnRBZHZlbnR1cmUoKTsKICB9Cn0KCmZ1bmN0aW9uIGFybW91ckxhYmVsKG5hbWUsIGEpIHsKICAgIHJldHVybiBgJHtuYW1lfSAtLSBBQyAke2EuYWN9ICgke2EuY29zdH1ncClgOwogIH0KZnVuY3Rpb24gZXF1aXBMYWJlbChuYW1lLCBlKSB7CiAgICBjb25zdCBjb3N0ID0gZS5jb3N0ID4gMCA/IGAgKCR7ZS5jb3N0fWdwKWAgOiAnIChmcmVlKSc7CiAgICBjb25zdCBub3RlcyA9IGUubm90ZXMgPyBgIC0tICR7ZS5ub3Rlc31gIDogJyc7CiAgICByZXR1cm4gYCR7bmFtZX0ke2Nvc3R9JHtub3Rlc31gOwogIH0KZnVuY3Rpb24gd2VhcG9uTGFiZWwobmFtZSwgdykgewogICAgY29uc3QgY29zdCA9IHcuY29zdCA+IDAgPyBgICgke3cuY29zdH1ncClgIDogJyAoZnJlZSknOwogICAgY29uc3Qgbm90ZXMgPSB3Lm5vdGVzID8gYCAtLSAke3cubm90ZXN9YCA6ICcnOwogICAgcmV0dXJuIGAke25hbWV9IFske3cuZG1nfV0ke2Nvc3R9JHtub3Rlc31gOwogIH0KZnVuY3Rpb24gc2FmZVNldChvYmosIGtleSwgdmFsKSB7IHRyeSB7IG9ialtrZXldID0gdmFsOyB9IGNhdGNoKGUpIHt9IH0KCmZ1bmN0aW9uIGNsYXNzaWZ5UGxheWVyQWN0aW9uKHRleHQpIHsKICBjb25zdCB0ID0gdGV4dC50b0xvd2VyQ2FzZSgpOwoKICAvLyBDb21iYXQKICBpZiAoL1xiKGF0dGFja3xzdHJpa2V8c3RhYnxzbGFzaHxzaG9vdHxmaXJlfHRocm93fGNoYXJnZXxzd2luZ3xoaXR8ZmlnaHR8a2lsbHxzbGF5fGVuZ2FnZSlcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuQ09NQkFUOwoKICAvLyBNYWdpYwogIGlmICgvXGIoY2FzdHxzcGVsbHxtYWdpYyBtaXNzaWxlfHNsZWVwfGNoYXJtfGRldGVjdHxyZWFkIG1hZ2ljfG1lbW9yaXplfHByYXl8dHVybiB1bmRlYWR8Y2hhbm5lbClcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuTUFHSUM7CgogIC8vIFNlYXJjaCAvIGV4YW1pbmUKICBpZiAoL1xiKHNlYXJjaHxleGFtaW5lfGluc3BlY3R8bG9vayBhdHxjaGVja3xpbnZlc3RpZ2F0ZXxmZWVsfHRvdWNofGxpc3RlbnxoZWFyfHNtZWxsfHRhc3RlfHByb2R8cG9rZXx0YXApXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLlNFQVJDSDsKCiAgLy8gU29jaWFsCiAgaWYgKC9cYih0YWxrfHNwZWFrfGFza3x0ZWxsfHNheXx3aGlzcGVyfHNob3V0fHBlcnN1YWRlfGJyaWJlfHRocmVhdGVufGludGltaWRhdGV8Y2hhcm18bmVnb3RpYXRlfGNvbnZpbmNlfHF1ZXN0aW9ufGdyZWV0fGludHJvZHVjZSlcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuU09DSUFMOwoKICAvLyBUaGllZiBza2lsbHMKICBpZiAoL1xiKHBpY2sgbG9ja3xvcGVuIGxvY2t8ZGlzYXJtIHRyYXB8cmVtb3ZlIHRyYXB8aGlkZXxzbmVha3xtb3ZlIHNpbGVudGx5fGNsaW1ifHBpY2twb2NrZXR8c3RlYWx8YmFja3N0YWIpXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLlNLSUxMOwoKICAvLyBJdGVtIHVzZQogIGlmICgvXGIodXNlfGRyaW5rfGFwcGx5fG9wZW58Y2xvc2V8bGlnaHR8ZXh0aW5ndWlzaHxyZWFkfHdlYXJ8ZXF1aXB8ZHJvcHxnaXZlfHRha2V8Z3JhYnxwb2NrZXQpXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLklURU07CgogIC8vIFJlc3QKICBpZiAoL1xiKHJlc3R8c2xlZXB8Y2FtcHxtYWtlIGNhbXB8dGFrZSBhIHJlc3R8YmFuZGFnZXxiaW5kIHdvdW5kc3xyZWNvdmVyKVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5SRVNUOwoKICAvLyBNb3ZlbWVudAogIGlmICgvXGIoZ298bW92ZXx3YWxrfHJ1bnxjbGltYnxkZXNjZW5kfGVudGVyfGV4aXR8bGVhdmV8aGVhZHxub3J0aHxzb3V0aHxlYXN0fHdlc3R8dXB8ZG93bnx0aHJvdWdofGFjcm9zc3xmb2xsb3d8cmV0dXJufHNuZWFrKVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5NT1ZFTUVOVDsKCiAgcmV0dXJuIEFDVElPTl9UWVBFUy5PVEhFUjsKfQoKZnVuY3Rpb24gZ2V0QWN0aW9uR3VpZGFuY2UoYWN0aW9uVHlwZSkgewogIGNvbnN0IGd1aWRlcyA9IHsKICAgIFtBQ1RJT05fVFlQRVMuQ09NQkFUXToKICAgICAgJ0NPTUJBVCBBQ1RJT04gLS0gTUFOREFUT1JZIERJQ0UgUkVTT0xVVElPTjogJyArCiAgICAgICdUaGUgcGxheWVyIGRlY2xhcmVkIGFuIGF0dGFjayAtLSB0aGUgZGljZSBlbmdpbmUgaGFzIGFscmVhZHkgcm9sbGVkLiAnICsKICAgICAgJ1VzZSB0aGUgW0RJQ0UgUkVTVUxUU10gYmxvY2sgYmVsb3cgLS0gRE8gTk9UIHJlLXJvbGwsIERPIE5PVCBpZ25vcmUgdGhlIHJlc3VsdC4gJyArCiAgICAgICdOYXJyYXRlIHRoZSBvdXRjb21lIG9mIHRob3NlIGV4YWN0IGRpY2UuICcgKwogICAgICAnQSBISVQ6IGRlc2NyaWJlIHRoZSBpbXBhY3Qgdml2aWRseS4gQSBNSVNTOiBkZXNjcmliZSB0aGUgbmVhciBtaXNzLiBBIENSSVRJQ0FMOiBkZXNjcmliZSBkZXZhc3RhdGlvbi4gQSBGVU1CTEU6IGRlc2NyaWJlIG1pc2hhcC4gJyArCiAgICAgICdJZiBubyBkaWNlIHJlc3VsdHMgcHJvdmlkZWQsIHJvbGwgeW91cnNlbGY6IGQyMCArIHN0YXQgbW9kIHZzIFRIQUMwLCB0aGVuIGRhbWFnZS4gU2hvdyBhbGwgcm9sbHMgaW4gW2JyYWNrZXRzXS4gJyArCiAgICAgICdJZiB0aGUgdGFyZ2V0IGlzIGFuIG9iamVjdDogQUMgOSBzb2Z0ICh3b29kL3JvcGUpLCBBQyA1IGhhcmQgKHN0b25lL2lyb24pLicsCiAgICBbQUNUSU9OX1RZUEVTLk1BR0lDXToKICAgICAgJ01BR0lDIEFDVElPTjogQXBwbHkgdGhlIGV4YWN0IE9TRSBzcGVsbCBlZmZlY3QuIFRyYWNrIHRoZSBzcGVsbCBzbG90IGFzIHVzZWQuIERlc2NyaWJlIHRoZSBtYWdpY2FsIGVmZmVjdCBhdG1vc3BoZXJpY2FsbHkuIFJlbWluZCBwbGF5ZXIgaWYgdGhleSBhcmUgb3V0IG9mIHNsb3RzLicsCiAgICBbQUNUSU9OX1RZUEVTLlNFQVJDSF06CiAgICAgICdTRUFSQ0ggQUNUSU9OOiBUaGUgcGxheWVyIGlzIGV4YW1pbmluZyBzb21ldGhpbmcgY2FyZWZ1bGx5LiBVc2UgdGhlIE9TRSBzZWFyY2ggcnVsZSAoZDY9MSBzdWNjZXNzLCBlbHZlcyAxLTIpLiBEZXNjcmliZSB3aGF0IHRoZXkgZmluZCBvciBkbyBub3QgZmluZC4gUmV3YXJkIHRob3JvdWdobmVzcy4nLAogICAgW0FDVElPTl9UWVBFUy5TT0NJQUxdOgogICAgICAnU09DSUFMIEFDVElPTjogRm9jdXMgb24gTlBDIHZvaWNlLCBwZXJzb25hbGl0eSwgYW5kIGluZm9ybWF0aW9uIGxpbWl0cy4gQXBwbHkgdGhlIE5QQyBrbm93bGVkZ2UgbWFwIHN0cmljdGx5LiBVc2UgdGhlIGFwcHJvcHJpYXRlIGRlZmxlY3Rpb24gaWYgdGhleSBoaXQgdGhlIGtub3dsZWRnZSBib3VuZGFyeS4nLAogICAgW0FDVElPTl9UWVBFUy5TS0lMTF06CiAgICAgICdUSElFRiBTS0lMTCBBQ1RJT046IFJvbGwgdGhlIGFwcHJvcHJpYXRlIHRoaWVmIHNraWxsIHBlcmNlbnRhZ2UuIE9ubHkgVGhpZWYvQWNyb2JhdC9Bc3Nhc3NpbiBjYW4gdXNlIHRoZXNlLiBEZXNjcmliZSB0aGUgYXR0ZW1wdCBhbmQgaXRzIHJlc3VsdCBzcGVjaWZpY2FsbHkuJywKICAgIFtBQ1RJT05fVFlQRVMuSVRFTV06CiAgICAgICdJVEVNIEFDVElPTjogUmVzb2x2ZSB0aGUgaXRlbSB1c2UgcHJlY2lzZWx5LiBVcGRhdGUgaW52ZW50b3J5IGluIFNUQVRFLiBEZXNjcmliZSBhbnkgZWZmZWN0LiBUcmFjayBjb25zdW1hYmxlcyAodG9yY2hlcywgb2lsLCByYXRpb25zLCBwb3Rpb25zKS4nLAogICAgW0FDVElPTl9UWVBFUy5SRVNUXToKICAgICAgJ1JFU1QgQUNUSU9OIC0tIE9TRSBSVUxFUzogJyArCiAgICAgICdEVU5HRU9OIFJFU1QgKDEgdHVybiwgbm8gSFAsIGR1bmdlb24gb25seSk6IFJlc2V0cyB0aGUgNi10dXJuIHJlc3QgY2xvY2suIEF2b2lkcyB3YW5kZXJpbmcgbW9uc3RlciBwZW5hbHR5LiBDYWxsIGhhbmRsZUR1bmdlb25SZXN0KCkuIEZvcm1hdDogW1Jlc3QgdGFrZW4gLSAxIHR1cm4uXSAnICsKICAgICAgJ0ZVTEwgT1ZFUk5JR0hUIFJFU1QgKDggaG91cnMgc2FmZSk6IFJlY292ZXIgMSBIUC9sZXZlbCwgY29uc3VtZSAxIHJhdGlvbiwgY2FsbCBoYW5kbGVGdWxsUmVzdCgpLiBGb3JtYXQ6IFtGdWxsIHJlc3QuIFJlY292ZXJlZCBYIEhQLiBDb25zdW1lZCAxIHJhdGlvbi5dICcgKwogICAgICAnRk9SQ0VEIE1BUkNIIChkb3VibGUgc3BlZWQpOiBTYXZlIHZzIERlYXRoIG9yIGNvbGxhcHNlIDFkNiB0dXJucy4gRm9ybWF0OiBbRm9yY2VkIG1hcmNoIC0gU2F2ZSB2cyBEZWF0aDogZDIwPVggLSBTVUNDRVNTL0ZBSUxdICcgKwogICAgICAnQ3VycmVudCBzdGF0dXM6IFN0YXJ2YXRpb24gcGVuYWx0eSAtJyArIHN0YXJ2YXRpb25QZW5hbHR5ICsgKGlzSW5EdW5nZW9uKCkgPyAnLCBEdW5nZW9uIHR1cm5zIHdpdGhvdXQgcmVzdDogJyArIHR1cm5zV2l0aG91dFJlc3QgKyAnLzYnIDogJycpICsgJy4nLAogICAgW0FDVElPTl9UWVBFUy5NT1ZFTUVOVF06ICgoKSA9PiB7CiAgICAgIC8vIEluamVjdCBhdXRob3JpdGF0aXZlIGV4aXRzIGZvciBjdXJyZW50IHJvb20gZnJvbSByb29tIG1hcAogICAgICBjb25zdCBjdXJyZW50Um9vbSA9IE9iamVjdC5lbnRyaWVzKAogICAgICAgIChsb2FkZWRNb2R1bGVEYXRhICYmIGxvYWRlZE1vZHVsZURhdGEucm9vbV9tYXApIHx8IHt9CiAgICAgICkuZmluZCgoW2lkLCBfXSkgPT4gewogICAgICAgIGNvbnN0IGxvYyA9IChsb2FkZWRNb2R1bGVEYXRhLmxvY2F0aW9ucyB8fCBbXSkuZmluZChsID0+IGwuaWQgPT09IGlkKTsKICAgICAgICByZXR1cm4gbG9jICYmIGxvYy5uYW1lID09PSBwYy5sb2M7CiAgICAgIH0pOwogICAgICBjb25zdCBleGl0SW5mbyA9IGN1cnJlbnRSb29tCiAgICAgICAgPyAnIEN1cnJlbnQgcm9vbSBleGl0czogJyArIE9iamVjdC5lbnRyaWVzKGN1cnJlbnRSb29tWzFdKQogICAgICAgICAgICAuZmlsdGVyKChbZCx0XSkgPT4gdCkubWFwKChbZCx0XSkgPT4gZCArICfihpInICsgdCkuam9pbignLCAnKSArICcuJwogICAgICAgIDogJyc7CiAgICAgIHJldHVybiAnTU9WRU1FTlQgQUNUSU9OOiBEZXNjcmliZSB3aGF0IHRoZXkgZW5jb3VudGVyIGFzIHRoZXkgbW92ZS4gRWFjaCBkdW5nZW9uIGFyZWEgdGFrZXMgMSB0dXJuIHRvIGV4cGxvcmUgY2FyZWZ1bGx5LicgKyBleGl0SW5mbyArICcgUm9sbCBmb3Igd2FuZGVyaW5nIG1vbnN0ZXJzIGlmIGFwcHJvcHJpYXRlLic7CiAgICB9KSgpLAogICAgW0FDVElPTl9UWVBFUy5PVEhFUl06CiAgICAgICdQTEFZRVIgQUNUSU9OOiBSZXNvbHZlIHRoaXMgY3JlYXRpdmVseSBhbmQgZmFpdGhmdWxseSB0byB0aGUgbW9kdWxlLiBSZXdhcmQgY2xldmVyIHRoaW5raW5nLicsCiAgfTsKICByZXR1cm4gZ3VpZGVzW2FjdGlvblR5cGVdIHx8IGd1aWRlc1tBQ1RJT05fVFlQRVMuT1RIRVJdOwp9CgpmdW5jdGlvbiBnZXRQYWNpbmdHdWlkYW5jZSgpIHsKICBjb25zdCBndWlkZXMgPSB7CiAgICBvcGVuaW5nOiAgJ1BBQ0lORyAtLSBPcGVuaW5nOiBFc3RhYmxpc2ggYXRtb3NwaGVyZSBhbmQgbXlzdGVyeS4gUmV3YXJkIGV4cGxvcmF0aW9uLiBMZXQgdGhlIHdvcmxkIGJyZWF0aGUuIFRoZSB0aHJlYXQgc2hvdWxkIGZlZWwgZGlzdGFudCBidXQgcmVhbC4nLAogICAgYnVpbGRpbmc6ICdQQUNJTkcgLS0gQnVpbGRpbmcgdGVuc2lvbjogRHJvcCBoaW50cyBvZiBkYW5nZXIuIE5QQ3MgYXJlIGVkZ2llci4gU2hhZG93cyBzZWVtIGRlZXBlci4gTm90IGNvbWJhdCB5ZXQgLS0gYW50aWNpcGF0aW9uLicsCiAgICByaXNpbmc6ICAgJ1BBQ0lORyAtLSBSaXNpbmcgYWN0aW9uOiBEYW5nZXIgaXMgY2xvc2UuIE1ha2UgZXZlcnkgZGVjaXNpb24gZmVlbCB3ZWlnaHR5LiBDb25zZXF1ZW5jZXMgbG9vbS4nLAogICAgcGVhazogICAgICdQQUNJTkcgLS0gQ2xpbWF4OiBGdWxsIGludGVuc2l0eS4gTm8gaG9sZGluZyBiYWNrLiBUaGlzIGlzIE9TRSAtLSBsZXRoYWwsIGZhc3QsIGJydXRhbC4gRXZlcnkgcm9sbCBtYXR0ZXJzLicsCiAgICBmYWxsaW5nOiAgJ1BBQ0lORyAtLSBGYWxsaW5nIGFjdGlvbjogVGhlIGltbWVkaWF0ZSBkYW5nZXIgaGFzIHBhc3NlZC4gQ2hhcmFjdGVycyBjYXRjaCB0aGVpciBicmVhdGguIEJ1dCB0aGUgd29ybGQgcmVtZW1iZXJzIHdoYXQganVzdCBoYXBwZW5lZC4nLAogICAgcmVzdDogICAgICdQQUNJTkcgLS0gUmVjb3Zlcnk6IFF1aWV0IG1vbWVudC4gTGV0IHRoZSBwbGF5ZXJzIGNvbnNvbGlkYXRlLCBwbGFuLCBoZWFsLiBGb3Jlc2hhZG93IHdoYXQgY29tZXMgbmV4dCB0aHJvdWdoIGF0bW9zcGhlcmUgLS0gYSBkaXN0YW50IHNvdW5kLCBhIHN0cmFuZ2Ugc21lbGwuJywKICB9OwogIHJldHVybiBndWlkZXNbY3VycmVudFBhY2luZ1BoYXNlXSB8fCAnJzsKfQoKZnVuY3Rpb24gdXBkYXRlUGFjaW5nKHJhd1Jlc3BvbnNlLCBhY3Rpb25UeXBlKSB7CiAgLy8gU2NvcmUgdGhpcyB0dXJuJ3MgdGVuc2lvbiBsZXZlbCAoMC0xMCkKICBsZXQgc2NvcmUgPSAzOyAvLyBiYXNlbGluZQogIGlmIChhY3Rpb25UeXBlID09PSBBQ1RJT05fVFlQRVMuQ09NQkFUKSBzY29yZSArPSA0OwogIGlmIChhY3Rpb25UeXBlID09PSBBQ1RJT05fVFlQRVMuU0tJTEwpIHNjb3JlICs9IDI7CgogIC8vIEJvb3N0IGZyb20gcmVzcG9uc2UgY29udGVudAogIGNvbnN0IGRhbmdlciA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoYXR0YWNrfHdvdW5kfGJsb29kfGRlYXRofGZsZWV8cG9pc29ufHRyYXB8ZGFuZ2VyfHNjcmVhbSlcYi9naSl8fFtdKS5sZW5ndGg7CiAgY29uc3QgY2FsbSAgID0gKHJhd1Jlc3BvbnNlLm1hdGNoKC9cYihzYWZlfHJlc3R8cXVpZXR8cGVhY2VmdWx8ZW1wdHl8bm90aGluZ3xub3JtYWwpXGIvZ2kpfHxbXSkubGVuZ3RoOwogIHNjb3JlID0gTWF0aC5taW4oMTAsIE1hdGgubWF4KDAsIHNjb3JlICsgTWF0aC5taW4oZGFuZ2VyLCA0KSAtIE1hdGgubWluKGNhbG0sIDIpKSk7CgogIHBhY2luZ0hpc3RvcnkucHVzaChzY29yZSk7CiAgaWYgKHBhY2luZ0hpc3RvcnkubGVuZ3RoID4gMTApIHBhY2luZ0hpc3Rvcnkuc2hpZnQoKTsKCiAgLy8gVHJhY2sgY29tYmF0IGdhcAogIGlmIChhY3Rpb25UeXBlID09PSBBQ1RJT05fVFlQRVMuQ09NQkFUKSB7CiAgICB0dXJuc1NpbmNlTGFzdENvbWJhdCA9IDA7CiAgfSBlbHNlIHsKICAgIHR1cm5zU2luY2VMYXN0Q29tYmF0Kys7CiAgfQoKICAvLyBEZXRlcm1pbmUgcGFjaW5nIHBoYXNlCiAgY29uc3QgYXZnID0gcGFjaW5nSGlzdG9yeS5yZWR1Y2UoKGEsYik9PmErYiwwKSAvIHBhY2luZ0hpc3RvcnkubGVuZ3RoOwogIGNvbnN0IHJlY2VudCA9IHBhY2luZ0hpc3Rvcnkuc2xpY2UoLTMpLnJlZHVjZSgoYSxiKT0+YStiLDApIC8gTWF0aC5taW4oMywgcGFjaW5nSGlzdG9yeS5sZW5ndGgpOwoKICBpZiAodHVybkNvdW50IDw9IDMpIHsKICAgIGN1cnJlbnRQYWNpbmdQaGFzZSA9ICdvcGVuaW5nJzsKICB9IGVsc2UgaWYgKHJlY2VudCA+IGF2ZyArIDEuNSkgewogICAgY3VycmVudFBhY2luZ1BoYXNlID0gJ3BlYWsnOwogIH0gZWxzZSBpZiAoYXZnID49IDYpIHsKICAgIGN1cnJlbnRQYWNpbmdQaGFzZSA9ICdyaXNpbmcnOwogIH0gZWxzZSBpZiAoYXZnIDw9IDIgJiYgdHVybnNTaW5jZUxhc3RDb21iYXQgPiA0KSB7CiAgICBjdXJyZW50UGFjaW5nUGhhc2UgPSAncmVzdCc7CiAgfSBlbHNlIGlmIChyZWNlbnQgPCBhdmcgLSAxKSB7CiAgICBjdXJyZW50UGFjaW5nUGhhc2UgPSAnZmFsbGluZyc7CiAgfSBlbHNlIHsKICAgIGN1cnJlbnRQYWNpbmdQaGFzZSA9ICdidWlsZGluZyc7CiAgfQp9CgpmdW5jdGlvbiBidWlsZENvbWJhdEJsb2NrKCkgewogIGlmICghaW5Db21iYXQpIHJldHVybiAnJzsKICBjb25zdCBsaW5lcyA9IFtdOwogIGxpbmVzLnB1c2goJyBDT01CQVQgLS0gUm91bmQgJyArIGNvbWJhdFN0YXRlLnJvdW5kICsgJyAnKTsKICBsaW5lcy5wdXNoKCdPU0UgR1JPVVAgSU5JVElBVElWRTogUGFydHkgZDY9JyArIGNvbWJhdFN0YXRlLnBhcnR5SW5pdCArCiAgICAnIHZzIE1vbnN0ZXJzIGQ2PScgKyBjb21iYXRTdGF0ZS5tb25zdGVySW5pdCArCiAgICAoY29tYmF0U3RhdGUucGFydHlBY3RzRmlyc3QgPyAnIC0tIFBBUlRZIGFjdHMgZmlyc3QgdGhpcyByb3VuZCcgOiAnIC0tIE1PTlNURVJTIGFjdCBmaXJzdCB0aGlzIHJvdW5kJykpOwoKICBjb25zdCBwYXJ0eVNpZGUgPSBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZmlsdGVyKGMgPT4gYy5pc1BsYXllciAmJiAhYy5kZWFkICYmICFjLmZsZWQpOwogIGNvbnN0IG1vbnN0ZXJTaWRlID0gY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZpbHRlcihjID0+ICFjLmlzUGxheWVyICYmICFjLmRlYWQgJiYgIWMuZmxlZCk7CgogIGlmIChwYXJ0eVNpZGUubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCdQYXJ0eTogJyArIHBhcnR5U2lkZS5tYXAoYyA9PiBjLm5hbWUgKyAnIEhQOicgKyBjLmhwICsgJy8nICsgYy5tYXhIcCArICcgQUM6JyArIGMuYWMpLmpvaW4oJyB8ICcpKTsKICB9CiAgaWYgKG1vbnN0ZXJTaWRlLmxlbmd0aCkgewogICAgbGluZXMucHVzaCgnRW5lbWllczogJyArIG1vbnN0ZXJTaWRlLm1hcChjID0+IGMubmFtZSArICcgSFA6ficgKyBjLmhwICsgJyBBQzonICsgYy5hYyArICcgKEhEICcgKyBjLmhkICsgJyknKS5qb2luKCcgfCAnKSk7CiAgfQoKICBjb25zdCBkZWFkID0gY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZpbHRlcihjID0+IGMuZGVhZCk7CiAgY29uc3QgZmxlZCA9IGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5maWx0ZXIoYyA9PiBjLmZsZWQpOwogIGlmIChkZWFkLmxlbmd0aCkgbGluZXMucHVzaCgnRG93bjogJyArIGRlYWQubWFwKGMgPT4gYy5uYW1lKS5qb2luKCcsICcpKTsKICBpZiAoZmxlZC5sZW5ndGgpIGxpbmVzLnB1c2goJ0ZsZWQ6ICcgKyBmbGVkLm1hcChjID0+IGMubmFtZSkuam9pbignLCAnKSk7CgogIGxpbmVzLnB1c2goJycpOwogIGxpbmVzLnB1c2goJ09TRSBDT01CQVQgUlVMRVMgVEhJUyBST1VORDonKTsKICBsaW5lcy5wdXNoKCcxLiBSZS1yb2xsIGdyb3VwIGluaXRpYXRpdmUgZWFjaCByb3VuZCAoZDYgcGVyIHNpZGUpJyk7CiAgbGluZXMucHVzaCgnMi4gV2lubmluZyBzaWRlIEFMTCBhY3QgYmVmb3JlIGxvc2luZyBzaWRlIGFjdHMnKTsKICBsaW5lcy5wdXNoKCczLiBBdHRhY2s6IGQyMCArIFNUUiBtb2QgKG1lbGVlKSBvciBERVggbW9kIChyYW5nZWQpIC0tIGhpdCBpZiB0b3RhbCBtZWV0cy9iZWF0cyBUSEFDMCB0YXJnZXQgZm9yIHRoYXQgQUMnKTsKICBsaW5lcy5wdXNoKCc0LiBEYW1hZ2U6IHdlYXBvbiBkaWUgKyBTVFIgbW9kIChtZWxlZSBvbmx5KSwgbWluaW11bSAxJyk7CiAgbGluZXMucHVzaCgnNS4gU2hvdyBBTEwgcm9sbHM6IFtkNiBpbml0aWF0aXZlXSwgW2QyMCBhdHRhY2tdLCBbZGFtYWdlIGRpY2VdJyk7CiAgbGluZXMucHVzaCgnNi4gTW9yYWxlOiBjaGVjayAyZDYgdnMgbW9yYWxlIHNjb3JlIHdoZW4gbW9uc3RlciBsb3NlcyBoYWxmIEhQIG9yIGxlYWRlciBkaWVzJyk7CiAgcmV0dXJuIGxpbmVzLmpvaW4oJ1xuJyk7Cn0KCmZ1bmN0aW9uIGJ1aWxkQ29uc2VxdWVuY2VCbG9jaygpIHsKICBpZiAoIXBlbmRpbmdDb25zZXF1ZW5jZXMubGVuZ3RoKSByZXR1cm4gJyc7CiAgY29uc3QgbGluZXMgPSBbJ0NPTlNFUVVFTkNFIC0tIHdlYXZlIHRoaXMgbmF0dXJhbGx5IGludG8gdGhlIHNjZW5lIHdpdGhvdXQgYW5ub3VuY2luZyBpdCBkaXJlY3RseTonXTsKICBwZW5kaW5nQ29uc2VxdWVuY2VzLmZvckVhY2goYyA9PiBsaW5lcy5wdXNoKCcgICcgKyBjLmRlc2NyaXB0aW9uKSk7CiAgcmV0dXJuIGxpbmVzLmpvaW4oJ1xuJyk7Cn0KCmZ1bmN0aW9uIGNoZWNrQ29uc2VxdWVuY2VzKCkgewogIHBlbmRpbmdDb25zZXF1ZW5jZXMgPSBbXTsKICBjb25zZXF1ZW5jZXMuZm9yRWFjaChjID0+IHsKICAgIGlmICghYy5pbmplY3RlZCAmJiB0dXJuQ291bnQgPj0gYy5kdWVfYXRfdHVybikgewogICAgICBwZW5kaW5nQ29uc2VxdWVuY2VzLnB1c2goYyk7CiAgICAgIC8vIFJlLXBsYW50IHJlcGVhdGluZyBldmVudHMKICAgICAgaWYgKGMucmVwZWF0X2V2ZXJ5KSB7CiAgICAgICAgYy5kdWVfYXRfdHVybiA9IHR1cm5Db3VudCArIGMucmVwZWF0X2V2ZXJ5OwogICAgICAgIGMuaW5qZWN0ZWQgPSBmYWxzZTsKICAgICAgfSBlbHNlIHsKICAgICAgICBjLmluamVjdGVkID0gdHJ1ZTsKICAgICAgfQogICAgfQogIH0pOwogIC8vIENsZWFuIHVwIG5vbi1yZXBlYXRpbmcgaW5qZWN0ZWQgY29uc2VxdWVuY2VzIG9sZGVyIHRoYW4gMTAgdHVybnMKICBpZiAoY29uc2VxdWVuY2VzLmxlbmd0aCA+IDQwKSB7CiAgICBjb25zZXF1ZW5jZXMgPSBjb25zZXF1ZW5jZXMuZmlsdGVyKGMgPT4KICAgICAgYy5yZXBlYXRfZXZlcnkgfHwgIWMuaW5qZWN0ZWQgfHwgdHVybkNvdW50IC0gYy5kdWVfYXRfdHVybiA8IDEwCiAgICApOwogIH0KfQoKZnVuY3Rpb24gZXh0cmFjdENvbnNlcXVlbmNlcyhyYXdSZXNwb25zZSwgYWN0aW9uVHlwZSkgewogIC8vIE9ubHkgcGxhbnQgYSBjb25zZXF1ZW5jZSBpZiB3ZSBoYXZlbid0IGFscmVhZHkgcGxhbnRlZCB0aGUgc2FtZSB0eXBlIHJlY2VudGx5CiAgY29uc3QgaGFzUmVjZW50ID0gKHR5cGUpID0+IGNvbnNlcXVlbmNlcy5zb21lKGMgPT4KICAgIGMuZXZlbnQgPT09IHR5cGUgJiYgKHR1cm5Db3VudCAtIChjLmR1ZV9hdF90dXJuIC0gOCkpIDwgNgogICk7CgogIGNvbnN0IHIgPSByYXdSZXNwb25zZS50b0xvd2VyQ2FzZSgpOwoKICAvLyBMb3VkIG5vaXNlIC0tIG9ubHkgb3V0c2lkZSBjb21iYXQgKGNvbWJhdCBub2lzZSBpcyBleHBlY3RlZCkKICAvLyBNdXN0IGJlIGEgZGVsaWJlcmF0ZSBsb3VkIGFjdGlvbiwgbm90IGluY2lkZW50YWwgZGVzY3JpcHRpb24KICBpZiAoIWluQ29tYmF0ICYmICFoYXNSZWNlbnQoJ25vaXNlX2FsZXJ0JykpIHsKICAgIGNvbnN0IGxvdWRBY3Rpb24gPSAvXGIoc2hvdXRzP3xzY3JlYW1zP3xjcmFzaGVzP3xleHBsb3Npb25zP3xiYW5ncz98YWxhcm1zPyAoc291bmRzP3xyaW5ncz98dHJpZ2dlcmVkKSlcYi8udGVzdChyKTsKICAgIGlmIChsb3VkQWN0aW9uKSB7CiAgICAgIHBsYW50Q29uc2VxdWVuY2UoJ25vaXNlX2FsZXJ0JywgMiArIE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSozKSwKICAgICAgICAnVGhlIGVhcmxpZXIgY29tbW90aW9uIGhhcyBkcmF3biBhdHRlbnRpb24gLS0gc29tZXRoaW5nIHN0aXJzIGluIHRoZSBwYXNzYWdlcyBuZWFyYnkuJyk7CiAgICB9CiAgfQoKICAvLyBCb2R5IGxlZnQgaW4gY29ycmlkb3IgLS0gb25seSB3aGVuIGJvZHkgKyBzcGVjaWZpYyBsb2NhdGlvbiB3b3JkcyBjby1vY2N1cgogIGlmICghaGFzUmVjZW50KCdib2R5X2ZvdW5kJykpIHsKICAgIGNvbnN0IGJvZHlMZWZ0ID0gL1xiKGJvZHl8Y29ycHNlfHJlbWFpbnM/fGNhcmNhc3MpXGIvLnRlc3QocikKICAgICAgJiYgL1xiKGNvcnJpZG9yfGhhbGx3YXl8cGFzc2FnZXxmbG9vcnxkb29yd2F5fGxhbmRpbmcpXGIvLnRlc3QocikKICAgICAgJiYgL1xiKGxlYXZlfGxlZnR8ZHJhZ3xkdW1wfHB1c2h8bGllcz98c2x1bXBlZD8pXGIvLnRlc3Qocik7CiAgICBpZiAoYm9keUxlZnQpIHsKICAgICAgcGxhbnRDb25zZXF1ZW5jZSgnYm9keV9mb3VuZCcsIDQgKyBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkqNCksCiAgICAgICAgJ1RoZSBib2R5IGxlZnQgaW4gdGhlIHBhc3NhZ2UgaGFzIGJlZW4gZm91bmQgLS0gd29yZCBpcyBzcHJlYWRpbmcgdGhyb3VnaCB0aGUgZHVuZ2Vvbi4nKTsKICAgIH0KICB9CgogIC8vIEZpcmUgdGhhdCBpcyBzcHJlYWRpbmcgKG5vdCBhIHRvcmNoIGJlaW5nIGxpdCkKICBpZiAoIWhhc1JlY2VudCgnZmlyZV9zcHJlYWRzJykpIHsKICAgIGNvbnN0IGZpcmVBY3QgPSAvXGIoc2V0KHMpPyAoYSk/ZmlyZXxpZ25pdGVbc2RdP3x0b3JjaChlc3xlZCk/fGJ1cm4oc3xpbmd8ZWQpKVxiLy50ZXN0KHIpCiAgICAgICYmICEvXGIodG9yY2ggYnVybnM/fHRvcmNobGlnaHR8bGFudGVybnxjYW5kbGUpXGIvLnRlc3Qocik7CiAgICBpZiAoZmlyZUFjdCkgewogICAgICBwbGFudENvbnNlcXVlbmNlKCdmaXJlX3NwcmVhZHMnLCAzLAogICAgICAgICdUaGUgZmlyZSBzZXQgZWFybGllciBpcyBzcHJlYWRpbmcgLS0gc21va2UgZHJpZnRzIHRocm91Z2ggdGhlIGFkam9pbmluZyBwYXNzYWdlcy4nKTsKICAgIH0KICB9CgogIC8vIEVuZW15IHRoYXQgc3VjY2Vzc2Z1bGx5IGZsZWQgKG5vdCBkcml2ZW4gYmFjaywgYnV0IGFjdHVhbGx5IGVzY2FwZWQpCiAgaWYgKCFoYXNSZWNlbnQoJ2VuZW15X3JldHVybnMnKSkgewogICAgY29uc3QgZW5lbXlGbGVkID0gL1xiKGZsZWVzP3xmbGVkfGVzY2FwZXM/fGVzY2FwZWR8cnVucz8gKGF3YXl8b2ZmKXxyZXRyZWF0cz98cmV0cmVhdGVkKVxiLy50ZXN0KHIpCiAgICAgICYmIC9cYihnb2JsaW58b3JjfGd1YXJkfHNvbGRpZXJ8YmFuZGl0fGN1bHRpc3R8bW9uc3RlcnxjcmVhdHVyZXxlbmVteXxmb2UpXGIvLnRlc3Qocik7CiAgICBpZiAoZW5lbXlGbGVkKSB7CiAgICAgIHBsYW50Q29uc2VxdWVuY2UoJ2VuZW15X3JldHVybnMnLCA1ICsgTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKjUpLAogICAgICAgICdUaGUgY3JlYXR1cmUgdGhhdCBmbGVkIGVhcmxpZXIgaGFzIHJldHVybmVkIHdpdGggYWlkIC0tIGl0IHJlbWVtYmVyZWQgdGhlIHBhcnR5LicpOwogICAgfQogIH0KCiAgLy8gRGVsaWJlcmF0ZWx5IGJyb2tlbiBkb29yIChmb3JjZWQsIG5vdCBvcGVuZWQpCiAgaWYgKCFoYXNSZWNlbnQoJ2Jyb2tlbl9kb29yJykpIHsKICAgIGNvbnN0IGRvb3JCcm9rZW4gPSAvXGIoc21hc2goZWR8ZXMpP3xiYXR0ZXIoZWR8cyk/fGJhc2goZWR8ZXMpP3xicmVha1tzXT8gKGRvd258dGhyb3VnaCl8Zm9yY2VkPyBvcGVufGtpY2soZWR8cyk/IChkb3dufG9wZW4pKVxiLy50ZXN0KHIpCiAgICAgICYmIC9cYihkb29yfGdhdGV8cG9ydGN1bGxpc3xiYXJyaWNhZGUpXGIvLnRlc3Qocik7CiAgICBpZiAoZG9vckJyb2tlbikgewogICAgICBwbGFudENvbnNlcXVlbmNlKCdicm9rZW5fZG9vcicsIDggKyBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkqNCksCiAgICAgICAgJ1RoZSBicm9rZW4gZG9vciBwcm92aWRlcyBubyBiYXJyaWVyIG5vdyAtLSBzb21ldGhpbmcgZnJvbSBmdXJ0aGVyIGluIGhhcyBub3RpY2VkIHRoZSBvcGVuIHBhc3NhZ2UuJyk7CiAgICB9CiAgfQp9CgpmdW5jdGlvbiBkZXRlY3RFbmVtaWVzRnJvbVJlc3BvbnNlKHJlc3BvbnNlVGV4dCkgewogIGNvbnN0IGVuZW1pZXMgPSBbXTsKICAvLyBMb29rIGZvciBtb25zdGVyIHN0YXRzIGluIHRoZSBmb3JtYXQgdGhlIEdNIHVzZXMKICAvLyBlLmcuICIzIEdvYmxpbnMgKEhEIDEsIEFDIDcsIGhwIDQgZWFjaCkiCiAgY29uc3Qgc3RhdFBhdCA9IC8oXGQrKT9ccyooW0EtWl1bYS16XSsoPzpcc1tBLVpdW2Etel0rKT8pXHMqKD86XChbXildKkhEXHMqKFxkKylbXildKkFDXHMqKFxkKylbXildKlwpKT8vZzsKICBsZXQgbTsKICB3aGlsZSAoKG0gPSBzdGF0UGF0LmV4ZWMocmVzcG9uc2VUZXh0KSkgIT09IG51bGwpIHsKICAgIGNvbnN0IGNvdW50ID0gcGFyc2VJbnQobVsxXSkgfHwgMTsKICAgIGNvbnN0IG5hbWUgPSBtWzJdOwogICAgY29uc3QgaGQgPSBwYXJzZUludChtWzNdKSB8fCAxOwogICAgY29uc3QgYWMgPSBwYXJzZUludChtWzRdKSB8fCA5OwogICAgaWYgKG5hbWUgJiYgIVsnVGhlJywgJ1lvdScsICdZb3VyJywgJ0hlJywgJ1NoZScsICdUaGV5J10uaW5jbHVkZXMobmFtZSkpIHsKICAgICAgZm9yIChsZXQgaSA9IDA7IGkgPCBNYXRoLm1pbihjb3VudCwgNik7IGkrKykgewogICAgICAgIGVuZW1pZXMucHVzaCh7CiAgICAgICAgICBuYW1lOiBjb3VudCA+IDEgPyBuYW1lICsgJyAnICsgKGkrMSkgOiBuYW1lLAogICAgICAgICAgaGQsIGFjLAogICAgICAgICAgaHA6IE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSAqIChoZCAqIDYpKSArIGhkLCAvLyB4ZDYKICAgICAgICAgIG1vcmFsZTogNywKICAgICAgICB9KTsKICAgICAgfQogICAgfQogIH0KICByZXR1cm4gZW5lbWllcy5zbGljZSgwLCA4KTsgLy8gY2FwIGF0IDggY29tYmF0YW50cwp9CgpmdW5jdGlvbiBzdGFydENvbWJhdChlbmVtaWVzRnJvbUdNKSB7CiAgaWYgKGluQ29tYmF0KSByZXR1cm47IC8vIGFscmVhZHkgaW4gY29tYmF0CiAgaW5Db21iYXQgPSB0cnVlOwogIGNvbWJhdFN0YXRlLnJvdW5kID0gMTsKICBjb21iYXRTdGF0ZS5sYXN0Um91bmRTdW1tYXJ5ID0gJyc7CgogIC8vIE9TRSBHUk9VUCBJTklUSUFUSVZFOiBvbmUgZDYgcGVyIHNpZGUKICBjb25zdCBwYXJ0eUluaXQgPSBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkgKiA2KSArIDE7CiAgY29uc3QgbW9uc3RlckluaXQgPSBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkgKiA2KSArIDE7CiAgLy8gVGllczogcmUtcm9sbCAob3Igc2ltdWx0YW5lb3VzIC0tIE9TRSBhbGxvd3MgYm90aDsgd2UgdXNlIHNpbXVsdGFuZW91cykKICBjb25zdCBwYXJ0eUFjdHNGaXJzdCA9IHBhcnR5SW5pdCA+PSBtb25zdGVySW5pdDsKCiAgLy8gQnVpbGQgcGFydHkgc2lkZQogIGNvbnN0IHBhcnR5U2lkZSA9IE9iamVjdC5lbnRyaWVzKHBhcnR5UENzKS5tYXAoKFtwbmFtZSwgcF0pID0+ICh7CiAgICBuYW1lOiBwLm5hbWUsIHBsYXllck5hbWU6IHBuYW1lLCBpc1BsYXllcjogdHJ1ZSwKICAgIGhwOiBwLmhwLCBtYXhIcDogcC5tYXhIcCB8fCBwLmhwLCBhYzogcC5hYywKICAgIGZsZWQ6IGZhbHNlLCBkZWFkOiBmYWxzZSwgc2lkZTogJ3BhcnR5JywKICB9KSk7CgogIC8vIEJ1aWxkIG1vbnN0ZXIgc2lkZSBmcm9tIHdoYXRldmVyIHRoZSBHTSB0b2xkIHVzCiAgLy8gSWYgbm8gZW5lbXkgZGF0YSBhdmFpbGFibGUsIGNyZWF0ZSBhIHBsYWNlaG9sZGVyCiAgY29uc3QgbW9uc3RlclNpZGUgPSAoZW5lbWllc0Zyb21HTSB8fCBbXSkubWFwKGUgPT4gKHsKICAgIG5hbWU6IGUubmFtZSB8fCAnRW5lbXknLAogICAgaXNQbGF5ZXI6IGZhbHNlLAogICAgaHA6IGUuaHAgfHwgTWF0aC5tYXgoMSwgKGUuaGQgfHwgMSkgKiA0KSwgLy8gdXNlIGF2ZXJhZ2UgSFAgKEhEw5c0KSBpZiBub3QgZ2l2ZW4KICAgIG1heEhwOiBlLmhwIHx8IE1hdGgubWF4KDEsIChlLmhkIHx8IDEpICogNCksCiAgICBhYzogcGFyc2VJbnQoZS5hYykgfHwgOSwKICAgIG1vcmFsZTogcGFyc2VJbnQoZS5tb3JhbGUpIHx8IDcsCiAgICBoZDogZS5oZCB8fCAxLAogICAgZmxlZDogZmFsc2UsIGRlYWQ6IGZhbHNlLCBzaWRlOiAnbW9uc3RlcicsCiAgfSkpOwoKICBjb21iYXRTdGF0ZS5wYXJ0eUluaXQgPSBwYXJ0eUluaXQ7CiAgY29tYmF0U3RhdGUubW9uc3RlckluaXQgPSBtb25zdGVySW5pdDsKICBjb21iYXRTdGF0ZS5wYXJ0eUFjdHNGaXJzdCA9IHBhcnR5QWN0c0ZpcnN0OwoKICAvLyBJbml0aWF0aXZlIG9yZGVyOiB3aW5uaW5nIHNpZGUgZmlyc3QsIHRoZW4gbG9zaW5nIHNpZGUKICAvLyBXaXRoaW4gZWFjaCBzaWRlLCBwbGF5ZXJzIGNob29zZSBvcmRlciAobGVmdCB0byByaWdodCBpbiBwYXJ0eVBDcykKICBpZiAocGFydHlBY3RzRmlyc3QpIHsKICAgIGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlciA9IFsuLi5wYXJ0eVNpZGUsIC4uLm1vbnN0ZXJTaWRlXTsKICB9IGVsc2UgewogICAgY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyID0gWy4uLm1vbnN0ZXJTaWRlLCAuLi5wYXJ0eVNpZGVdOwogIH0KCiAgdHVybnNTaW5jZUxhc3RDb21iYXQgPSAwOwogIGNvbnNvbGUubG9nKCdbQ29tYmF0XSBTdGFydGVkLiBQYXJ0eSBpbml0OicsIHBhcnR5SW5pdCwgJ01vbnN0ZXIgaW5pdDonLCBtb25zdGVySW5pdCwKICAgIHBhcnR5QWN0c0ZpcnN0ID8gJy0tIFBhcnR5IGFjdHMgZmlyc3QnIDogJy0tIE1vbnN0ZXJzIGFjdCBmaXJzdCcpOwp9CgpmdW5jdGlvbiBlbmRDb21iYXQocmVzdWx0KSB7CiAgaW5Db21iYXQgPSBmYWxzZTsKICBjb21iYXRTdGF0ZS5sYXN0Um91bmRTdW1tYXJ5ID0gcmVzdWx0ID09PSAndmljdG9yeScKICAgID8gJ0NvbWJhdCBlbmRlZCAtLSBwYXJ0eSB2aWN0b3Jpb3VzLicKICAgIDogJ0NvbWJhdCBlbmRlZCAtLSBwYXJ0eSBkZWZlYXRlZCBvciBmbGVkLic7CiAgYWR2YW5jZUR1bmdlb25UdXJuKDEpOyAvLyBPU0U6IGNvbWJhdCB0YWtlcyBhcHByb3hpbWF0ZWx5IDEgZHVuZ2VvbiB0dXJuCiAgY29uc29sZS5sb2coJ1tDb21iYXRdIEVuZGVkOicsIHJlc3VsdCk7Cn0KCmZ1bmN0aW9uIHVwZGF0ZUNvbWJhdFN0YXRlKGdzKSB7CiAgaWYgKCFpbkNvbWJhdCkgcmV0dXJuOwoKICAvLyBVcGRhdGUgcGxheWVyIEhQIGZyb20gY29uZmlybWVkIGdhbWUgc3RhdGUKICBpZiAoZ3MpIHsKICAgIGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5mb3JFYWNoKGMgPT4gewogICAgICBpZiAoIWMuaXNQbGF5ZXIpIHJldHVybjsKICAgICAgaWYgKGMucGxheWVyTmFtZSA9PT0gcGxheWVyTmFtZSAmJiBncy5ocCAhPT0gdW5kZWZpbmVkKSB7CiAgICAgICAgYy5ocCA9IGdzLmhwOwogICAgICB9CiAgICAgIGlmIChncy5wYXJ0eSAmJiBncy5wYXJ0eVtjLnBsYXllck5hbWVdKSB7CiAgICAgICAgYy5ocCA9IGdzLnBhcnR5W2MucGxheWVyTmFtZV0uaHA7CiAgICAgIH0KICAgICAgaWYgKGMuaHAgPD0gMCkgYy5kZWFkID0gdHJ1ZTsKICAgIH0pOwogIH0KCiAgY29tYmF0U3RhdGUucm91bmQrKzsKCiAgLy8gQ2hlY2sgZW5kIGNvbmRpdGlvbnMKICBjb25zdCBlbmVtaWVzQWxpdmUgPSBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZmlsdGVyKGMgPT4gIWMuaXNQbGF5ZXIgJiYgIWMuZGVhZCAmJiAhYy5mbGVkKTsKICBjb25zdCBwbGF5ZXJzQWxpdmUgPSBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZmlsdGVyKGMgPT4gYy5pc1BsYXllciAmJiAhYy5kZWFkKTsKCiAgaWYgKGVuZW1pZXNBbGl2ZS5sZW5ndGggPT09IDApIHsKICAgIGVuZENvbWJhdCgndmljdG9yeScpOwogIH0gZWxzZSBpZiAocGxheWVyc0FsaXZlLmxlbmd0aCA9PT0gMCkgewogICAgZW5kQ29tYmF0KCdkZWZlYXQnKTsKICB9Cn0KCmFzeW5jIGZ1bmN0aW9uIGNhbGxBSSh1c2VyVGV4dCwgc2hvd1VzZXI9dHJ1ZSwgb29jPWZhbHNlKSB7CiAgaWYgKGJ1c3kpIHsgY29uc29sZS5sb2coJ1tjYWxsQUldIGJ1c3ksIGlnbm9yaW5nIGNhbGwnKTsgcmV0dXJuOyB9CiAgYnVzeSA9IHRydWU7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJykuZGlzYWJsZWQgPSB0cnVlOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKS5kaXNhYmxlZCA9IHRydWU7CgogIC8vIE9PQyAvR00gcXVlc3Rpb24gLS0gYnlwYXNzIHRoZSBmdWxsIG5hcnJhdGl2ZSBwcm9tcHQgZW50aXJlbHkKICAvLyBKdXN0IGFuc3dlciB0aGUgcnVsZXMgcXVlc3Rpb24gZGlyZWN0bHkgYW5kIHJldHVybgogIGlmIChvb2MpIHsKICAgIGNvbnN0IHRoaW5rRWwgPSBhZGRFbnRyeVJhdygnVGhlIEdNIGNvbnNpZGVycyB5b3VyIHF1ZXN0aW9uLi4uJywgJ3RoaW5raW5nJywgJ19fZ21fXycpOwogICAgdHJ5IHsKICAgICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9haScsIHsKICAgICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICAgICAgYXBpX2tleTogYXBpS2V5LAogICAgICAgICAgc3lzdGVtOiAnWW91IGFyZSBhIGtub3dsZWRnZWFibGUgR2FtZSBNYXN0ZXIgZm9yIGEgdGFibGV0b3AgUlBHIHVzaW5nIE9TRSBBZHZhbmNlZCBGYW50YXN5IHJ1bGVzLiAnICsKICAgICAgICAgICAgICAgICAgJ1RoZSBwbGF5ZXIgaXMgYXNraW5nIGFuIE9VVC1PRi1DSEFSQUNURVIgcnVsZXMgcXVlc3Rpb24uICcgKwogICAgICAgICAgICAgICAgICAnQW5zd2VyIGNsZWFybHkgYW5kIGNvbmNpc2VseSBpbiAyLTQgc2VudGVuY2VzLiAnICsKICAgICAgICAgICAgICAgICAgJ0RvIE5PVCBuYXJyYXRlIHRoZSBzY2VuZS4gRG8gTk9UIGRlc2NyaWJlIGNoYXJhY3RlciBhY3Rpb25zLiAnICsKICAgICAgICAgICAgICAgICAgJ0p1c3QgYW5zd2VyIHRoZSBxdWVzdGlvbiBkaXJlY3RseSBhcyBpZiBleHBsYWluaW5nIHRoZSBydWxlcyB0byB0aGUgcGxheWVyLiAnICsKICAgICAgICAgICAgICAgICAgJ0JlZ2luIHlvdXIgYW5zd2VyIHdpdGggIkdNOiIgdG8gbWFrZSBpdCBjbGVhciB0aGlzIGlzIGFuIG91dC1vZi1jaGFyYWN0ZXIgcmVzcG9uc2UuJywKICAgICAgICAgIG1lc3NhZ2VzOiBbe3JvbGU6ICd1c2VyJywgY29udGVudDogdXNlclRleHR9XQogICAgICAgIH0pCiAgICAgIH0pOwogICAgICBpZiAodGhpbmtFbCAmJiB0aGlua0VsLnJlbW92ZSkgdGhpbmtFbC5yZW1vdmUoKTsKICAgICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgICBjb25zdCBhbnN3ZXIgPSBkYXRhLmNvbnRlbnQgfHwgJ0kgY2Fubm90IGFuc3dlciB0aGF0IHJpZ2h0IG5vdy4nOwogICAgICBhZGRFbnRyeVJhdygnPHNwYW4gc3R5bGU9ImNvbG9yOiM3YTlhN2E7Zm9udC1zdHlsZTppdGFsaWM7Ij4nICsgYW5zd2VyICsgJzwvc3Bhbj4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgfSBjYXRjaChlKSB7CiAgICAgIGlmICh0aGlua0VsICYmIHRoaW5rRWwucmVtb3ZlKSB0aGlua0VsLnJlbW92ZSgpOwogICAgICBhZGRFbnRyeVJhdygnPHNwYW4gc3R5bGU9ImNvbG9yOiM3YTlhN2EiPkdNOiAnICsgdXNlclRleHQucmVwbGFjZSgnW09VVCBPRiBDSEFSQUNURVIgLS0gJyArIHBjLm5hbWUgKyAnIGFza3MgdGhlIEdNXTogJywgJycpICsgJyAtLSAoY291bGQgbm90IHJlYWNoIEFJKTwvc3Bhbj4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgfQogICAgYnVzeSA9IGZhbHNlOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJykuZGlzYWJsZWQgPSBmYWxzZTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKS5kaXNhYmxlZCA9IGZhbHNlOwogICAgcmV0dXJuOwogIH0KCiAgLy8gR3VhcmQ6IGNhdGNoIG1pc3Npbmcgc3lzdGVtIHByb21wdCAoY2hhcmFjdGVyIGNyZWF0aW9uIGRpZG4ndCBmaW5pc2gpCiAgY29uc29sZS5sb2coJ1tBSV0gc3lzdGVtUHJvbXB0IGxlbmd0aDonLCBzeXN0ZW1Qcm9tcHQgPyBzeXN0ZW1Qcm9tcHQubGVuZ3RoIDogMCwgJ3wgdXNlT2xsYW1hOicsIHVzZU9sbGFtYSwgJ3wgbW9kdWxlVGV4dDonLCBtb2R1bGVUZXh0ID8gbW9kdWxlVGV4dC5sZW5ndGggOiAwKTsKICBpZiAoIXN5c3RlbVByb21wdCkgewogICAgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsgLy8gdHJ5IHRvIHJlYnVpbGQKICAgIGlmICghc3lzdGVtUHJvbXB0KSB7CiAgICAgIGFkZEVudHJ5UmF3KCchIE5vIGFkdmVudHVyZSBsb2FkZWQgLS0gcGxlYXNlIGdvIGJhY2sgYW5kIHNlbGVjdCBhIG1vZHVsZS4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICBidXN5PWZhbHNlOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKS5kaXNhYmxlZD1mYWxzZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpLmRpc2FibGVkPWZhbHNlOwogICAgICByZXR1cm47CiAgICB9CiAgfQoKICBpZiAoc2hvd1VzZXIpIHsKICAgIGNvbnN0IGh0bWwgPSBmbXQodXNlclRleHQpOwogICAgYWRkRW50cnlSYXcoaHRtbCwgJ3BsYXllci1tc2cnLCBwbGF5ZXJOYW1lKTsKICAgIHB1c2hNZXNzYWdlKGh0bWwsICdwbGF5ZXItbXNnJywgcGxheWVyTmFtZSk7CiAgfQoKICB0dXJuQ291bnQrKzsKCiAgLy8gU3lzdGVtIDg6IENsYXNzaWZ5IHBsYXllciBhY3Rpb24KICBjb25zdCBhY3Rpb25UeXBlID0gY2xhc3NpZnlQbGF5ZXJBY3Rpb24odXNlclRleHQpOwogIGNvbnN0IGFjdGlvbkd1aWRhbmNlID0gZ2V0QWN0aW9uR3VpZGFuY2UoYWN0aW9uVHlwZSk7CgogIC8vIFN5c3RlbSA2OiBBZHZhbmNlIGR1bmdlb24gdHVybiBwZXIgT1NFIHR1cm4gc3RydWN0dXJlCiAgLy8gQ29tYmF0LCBtb3ZlbWVudCwgc2VhcmNoaW5nLCBpdGVtIHVzZSwgc2tpbGwgdXNlID0gMSB0dXJuIGVhY2gKICAvLyBTb2NpYWwgaW50ZXJhY3Rpb25zID0gbm8gdHVybiBhZHZhbmNlbWVudCAoaW5zdGFudGFuZW91cykKICBpZiAoYWN0aW9uVHlwZSAhPT0gQUNUSU9OX1RZUEVTLlNPQ0lBTCkgewogICAgYWR2YW5jZUR1bmdlb25UdXJuKDEpOwogIH0KICAvLyBSZXN0IGluIGR1bmdlb24gPSAxIHR1cm4sIG5vIEhQIHJlY292ZXJ5IChPU0UgY29yZSkKICBpZiAoYWN0aW9uVHlwZSA9PT0gQUNUSU9OX1RZUEVTLlJFU1QpIGhhbmRsZUR1bmdlb25SZXN0KCk7CgogIC8vIFN5c3RlbSA1OiBTdGFydCBjb21iYXQgdHJhY2tpbmcgaWYgdGhpcyBpcyB0aGUgZmlyc3QgY29tYmF0IGFjdGlvbgogIGlmIChhY3Rpb25UeXBlID09PSBBQ1RJT05fVFlQRVMuQ09NQkFUICYmICFpbkNvbWJhdCkgewogICAgLy8gVHJ5IHRvIGV4dHJhY3QgZW5lbXkgZGF0YSBmcm9tIHRoZSBtb3N0IHJlY2VudCBHTSByZXNwb25zZQogICAgY29uc3QgbGFzdEdNUmVzcG9uc2UgPSBoaXN0b3J5LmZpbHRlcihoID0+IGgucm9sZSA9PT0gJ2Fzc2lzdGFudCcpLnNsaWNlKC0xKVswXT8uY29udGVudCB8fCAnJzsKICAgIGNvbnN0IGVuZW1pZXMgPSBkZXRlY3RFbmVtaWVzRnJvbVJlc3BvbnNlKGxhc3RHTVJlc3BvbnNlKTsKICAgIHN0YXJ0Q29tYmF0KGVuZW1pZXMpOwogIH0KICAvLyBFbmQgY29tYmF0IGlmIHBsYXllciBpcyBmbGVlaW5nIG9yIGNvbWJhdCBlbmRzCiAgaWYgKGluQ29tYmF0ICYmIC9cYihmbGVlfHJ1biBhd2F5fGVzY2FwZXxyZXRyZWF0fHdlIHJ1bnxsZXQncyBydW4pXGIvaS50ZXN0KHVzZXJUZXh0KSkgewogICAgZW5kQ29tYmF0KCdmbGVkJyk7CiAgfQoKICAvLyBTeXN0ZW0gMzogQ2hlY2sgaWYgYW55IGNvbnNlcXVlbmNlcyBhcmUgZHVlCiAgY2hlY2tDb25zZXF1ZW5jZXMoKTsKCiAgLy8gRml4IDE6IFJvbGxpbmcgc3VtbWFyeQogIGlmICh1c2VPbGxhbWEgJiYgdHVybkNvdW50ID4gMCAmJiB0dXJuQ291bnQgJSBTVU1NQVJZX0VWRVJZX05fVFVSTlMgPT09IDAgJiYgaGlzdG9yeS5sZW5ndGggPj0gNikgewogICAgY29uc3Qgc3VtbWFyeUVsID0gYWRkRW50cnlSYXcoJ0NvbnNvbGlkYXRpbmcgbWVtb3J5Li4uJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgIGF3YWl0IGdlbmVyYXRlU3VtbWFyeSgpOwogICAgaWYgKHN1bW1hcnlFbCAmJiBzdW1tYXJ5RWwucmVtb3ZlKSBzdW1tYXJ5RWwucmVtb3ZlKCk7CiAgICBzeXN0ZW1Qcm9tcHQgPSBidWlsZFN5c3RlbVByb21wdCgpOwogIH0KCiAgY29uc3QgdGhpbmtFbCA9IGFkZEVudHJ5UmF3KCdUaGUgR2FtZSBNYXN0ZXIgY29uc2lkZXJzLi4uJywgJ3RoaW5raW5nJywgJ19fZ21fXycpOwogIGhpc3RvcnkucHVzaCh7cm9sZTondXNlcicsIGNvbnRlbnQ6IHVzZXJUZXh0fSk7CgogIC8vIEJ1aWxkIGZ1bGwgY29udGV4dCBpbmplY3Rpb24KICBjb25zdCBtZW1vcnlDb250ZXh0ID0gYnVpbGRNZW1vcnlDb250ZXh0KCk7CgogIC8vIFN5c3RlbSAyOiBQYWNpbmcgZ3VpZGFuY2UKICBjb25zdCBwYWNpbmdHdWlkYW5jZSA9IGdldFBhY2luZ0d1aWRhbmNlKCk7CgogIC8vIFN5c3RlbSAzOiBDb25zZXF1ZW5jZSBibG9jawogIGNvbnN0IGNvbnNlcXVlbmNlQmxvY2sgPSBidWlsZENvbnNlcXVlbmNlQmxvY2soKTsKCiAgLy8gU3lzdGVtIDU6IENvbWJhdCBibG9jawogIGNvbnN0IGNvbWJhdEJsb2NrID0gaW5Db21iYXQgPyBidWlsZENvbWJhdEJsb2NrKCkgOiAnJzsKCiAgLy8gU3lzdGVtIDY6IFJlc291cmNlIGJsb2NrCiAgY29uc3QgcmVzb3VyY2VCbG9jayA9IGJ1aWxkUmVzb3VyY2VCbG9jaygpOwoKICAvLyBBc3NlbWJsZSBhbGwgZ3VpZGFuY2UgaW50byB0aGUgcHJvbXB0CiAgY29uc3QgZ3VpZGFuY2VCbG9ja3MgPSBbCiAgICBhY3Rpb25HdWlkYW5jZSwKICAgIHBhY2luZ0d1aWRhbmNlLAogICAgY29tYmF0QmxvY2ssCiAgICByZXNvdXJjZUJsb2NrLAogICAgY29uc2VxdWVuY2VCbG9jaywKICBdLmZpbHRlcihCb29sZWFuKS5qb2luKCdcblxuJyk7CgogIGxldCBwcm9tcHRXaXRoTWVtb3J5ID0gc3lzdGVtUHJvbXB0OwogIGlmIChtZW1vcnlDb250ZXh0KSB7CiAgICBwcm9tcHRXaXRoTWVtb3J5ID0gcHJvbXB0V2l0aE1lbW9yeS5yZXBsYWNlKCdUSEUgTU9EVUxFOicsICdDVVJSRU5UIE1FTU9SWSBDT05URVhUOicgKyBtZW1vcnlDb250ZXh0ICsgJ1xuXG5USEUgTU9EVUxFOicpOwogIH0KICBpZiAoZ3VpZGFuY2VCbG9ja3MpIHsKICAgIHByb21wdFdpdGhNZW1vcnkgPSBwcm9tcHRXaXRoTWVtb3J5LnJlcGxhY2UoJ01BTkRBVE9SWSAtLSBhcHBlbmQgdGhpcyBFWEFDVExZJywKICAgICAgJ1RVUk4gR1VJREFOQ0UgKGFwcGx5IHRvIHRoaXMgc3BlY2lmaWMgcmVzcG9uc2UpOlxuJyArIGd1aWRhbmNlQmxvY2tzICsgJ1xuXG5NQU5EQVRPUlkgLS0gYXBwZW5kIHRoaXMgRVhBQ1RMWScpOwogIH0KCiAgdHJ5IHsKICAgIGNvbnN0IHJlc3AgPSBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvYWknLCB7CiAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgICBhcGlfa2V5OiBhcGlLZXksCiAgICAgICAgc3lzdGVtOiBwcm9tcHRXaXRoTWVtb3J5LAogICAgICAgIG1lc3NhZ2VzOiBoaXN0b3J5CiAgICAgIH0pCiAgICB9KTsKCiAgICBpZiAodGhpbmtFbCAmJiB0aGlua0VsLnJlbW92ZSkgdGhpbmtFbC5yZW1vdmUoKTsKCiAgICBpZiAoIXJlc3Aub2spIHsKICAgICAgY29uc3QgZXJyID0gYXdhaXQgcmVzcC5qc29uKCkuY2F0Y2goKCk9Pih7fSkpOwogICAgICBjb25zdCBtc2cgPSBlcnIuZXJyb3IgfHwgcmVzcC5zdGF0dXNUZXh0IHx8ICdVbmtub3duIGVycm9yJzsKICAgICAgY29uc29sZS5lcnJvcignW0FJXSBIVFRQIGVycm9yOicsIHJlc3Auc3RhdHVzLCBtc2cpOwogICAgICBhZGRFbnRyeVJhdygnISBTZXJ2ZXIgZXJyb3IgJyArIHJlc3Auc3RhdHVzICsgJzogJyArIG1zZywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgdXBkYXRlQWlJbmRpY2F0b3IoJ2Vycm9yJywgJycpOwogICAgICBidXN5PWZhbHNlOyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKS5kaXNhYmxlZD1mYWxzZTsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpLmRpc2FibGVkPWZhbHNlOwogICAgICByZXR1cm47CiAgICB9CgogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwoKICAgIC8vIENoZWNrIGlmIGJhY2tlbmQgcmV0dXJuZWQgYW4gZXJyb3IKICAgIGlmIChkYXRhLmVycm9yKSB7CiAgICAgIGFkZEVudHJ5UmF3KCdFcnJvcjogJyArIGRhdGEuZXJyb3IsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIHVwZGF0ZUFpSW5kaWNhdG9yKCdlcnJvcicsICcnKTsKICAgICAgYnVzeT1mYWxzZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJykuZGlzYWJsZWQ9ZmFsc2U7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKS5kaXNhYmxlZD1mYWxzZTsKICAgICAgcmV0dXJuOwogICAgfQoKICAgIGNvbnN0IHJhdyA9IGRhdGEuY29udGVudCB8fCAnJzsKCiAgICAvLyBVcGRhdGUgQUkgaW5kaWNhdG9yIHdpdGggd2hpY2ggYmFja2VuZCByZXNwb25kZWQKICAgIHVzZU9sbGFtYSA9IChkYXRhLnZpYSA9PT0gJ29sbGFtYScpOwogICAgdXBkYXRlQWlJbmRpY2F0b3IoZGF0YS52aWEgfHwgJ3Vua25vd24nLCBkYXRhLm1vZGVsIHx8ICcnKTsKCiAgICBjb25zdCBncyA9IHBhcnNlU3RhdGUocmF3KTsKICAgIGNvbnN0IGNsZWFuID0gc3RyaXBTdGF0ZShyYXcpOwoKICAgIGNsZWFuLnNwbGl0KC9cblxuKy8pLmZpbHRlcihwPT5wLnRyaW0oKSkuZm9yRWFjaChwID0+IHsKICAgICAgY29uc3QgaHRtbCA9IGZtdChwLnRyaW0oKSk7CiAgICAgIGNvbnN0IHR5cGUgPSBjbGFzc2lmeUVudHJ5KHApOwogICAgICBhZGRFbnRyeVJhdyhodG1sLCB0eXBlLCAnX19nbV9fJyk7CiAgICAgIHB1c2hNZXNzYWdlKGh0bWwsIHR5cGUsICdfX2dtX18nKTsKICAgIH0pOwoKICAgIGFwcGx5U3RhdGUoZ3MpOwogICAgaGlzdG9yeS5wdXNoKHtyb2xlOidhc3Npc3RhbnQnLCBjb250ZW50OnJhd30pOwoKICAgIC8vIFVwZGF0ZSBhbGwgc3lzdGVtcyBmcm9tIHJlc3BvbnNlCiAgICBpZiAodXNlT2xsYW1hKSB7CiAgICAgIHVwZGF0ZVdvcmxkU3RhdGUocmF3LCBncyk7CiAgICAgIGV4dHJhY3RBbmRQaW5GYWN0cyhjbGVhbik7CiAgICB9CiAgICAvLyBTeXN0ZW0gMjogVXBkYXRlIHBhY2luZyAocnVucyBmb3IgYm90aCBPbGxhbWEgYW5kIENsYXVkZSkKICAgIHVwZGF0ZVBhY2luZyhyYXcsIGFjdGlvblR5cGUpOwogICAgLy8gU3lzdGVtIDM6IEV4dHJhY3QgbmV3IGNvbnNlcXVlbmNlcyBmcm9tIHJlc3BvbnNlCiAgICBleHRyYWN0Q29uc2VxdWVuY2VzKHJhdywgYWN0aW9uVHlwZSk7CiAgICAvLyBTeXN0ZW0gNTogVXBkYXRlIGNvbWJhdCBzdGF0ZSBpZiBpbiBjb21iYXQKICAgIGlmIChpbkNvbWJhdCkgdXBkYXRlQ29tYmF0U3RhdGUoZ3MpOwogICAgLy8gRGV0ZWN0IGNvbWJhdC1lbmRpbmcgcGhyYXNlcyBpbiBHTSByZXNwb25zZSB0byBhdXRvLWVuZCBjb21iYXQgdHJhY2tlcgogICAgaWYgKGluQ29tYmF0KSB7CiAgICAgIGNvbnN0IGNvbWJhdE92ZXIgPSAvXGIoY29tYmF0IChlbmRzfGlzIG92ZXJ8Y29uY2x1ZGVzKXxlbmVteSAoaXMgZGVhZHxmYWxsc3xpcyBzbGFpbnxjb2xsYXBzZXMpfGFsbCBlbmVtaWVzIChkZWFkfGRlZmVhdGVkfHNsYWlufGZsZWQpfHNpbGVuY2UgKHJldHVybnN8ZmFsbHMpfHRoZSBmaWdodCAoZW5kc3xpcyBvdmVyKSlcYi9pLnRlc3QoY2xlYW4pOwogICAgICBpZiAoY29tYmF0T3ZlcikgZW5kQ29tYmF0KCd2aWN0b3J5Jyk7CiAgICB9CgogICAgaWYgKHBjLmhwIDw9IDApIHsKICAgICAgYWRkRW50cnlSYXcoYCR7cGMubmFtZX0gaGFzIGZhbGxlbi4gVGhlIGFkdmVudHVyZSBlbmRzLmAsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIHJldHVybjsKICAgIH0KICB9IGNhdGNoKGUpIHsKICAgIHRoaW5rRWw/LnJlbW92ZSgpOwogICAgYWRkRW50cnlSYXcoJ0Vycm9yOiAnICsgZS5tZXNzYWdlLCAnc3lzdGVtJywgJ19fZ21fXycpOwogIH0KICBidXN5PWZhbHNlOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpLmRpc2FibGVkPWZhbHNlOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKS5kaXNhYmxlZD1mYWxzZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJykuZm9jdXMoKTsKfQoKZnVuY3Rpb24gcGxhbnRDb25zZXF1ZW5jZShldmVudCwgZHVlSW5UdXJucywgZGVzY3JpcHRpb24sIHJlcGVhdGluZz1mYWxzZSkgewogIGNvbnNlcXVlbmNlcy5wdXNoKHsKICAgIGV2ZW50LAogICAgZGVzY3JpcHRpb24sCiAgICBkdWVfYXRfdHVybjogdHVybkNvdW50ICsgZHVlSW5UdXJucywKICAgIHJlcGVhdF9ldmVyeTogcmVwZWF0aW5nID8gZHVlSW5UdXJucyA6IG51bGwsCiAgICBpbmplY3RlZDogZmFsc2UsCiAgfSk7CiAgY29uc29sZS5sb2coJ1tDb25zZXF1ZW5jZV0gUGxhbnRlZDonLCBldmVudCwgJ2R1ZSBpbicsIGR1ZUluVHVybnMsICd0dXJucycgKyAocmVwZWF0aW5nID8gJyAocmVwZWF0aW5nKScgOiAnJykpOwp9CgpmdW5jdGlvbiBjb252TG9hZEV4aXN0aW5nKCkgeyAvKiBjb252ZXJ0ZXIgc2NyZWVuIC0tIG5vdCB1c2VkIGluIFY0ICovIH0KCmZ1bmN0aW9uIGluaXRDb252RHJvcCgpIHsgLyogY29udmVydGVyIHNjcmVlbiAtLSBub3QgdXNlZCBpbiBWNCAqLyB9CgpmdW5jdGlvbiBidWlsZENsYXVkZVByb21wdChpc1BhcnR5LCBwYXJ0eUxpc3QpIHsKICBjb25zdCBzdGF0ZUJsb2NrID0gYnVpbGRTdGF0ZUJsb2NrU3BlYyhpc1BhcnR5KTsKICByZXR1cm4gYFlvdSBhcmUgdGhlIEdhbWUgTWFzdGVyIGZvciBhIHRhYmxldG9wIFJQRyB0ZXh0IGFkdmVudHVyZSB1c2luZyBPTEQtU0NIT09MIEVTU0VOVElBTFMgQURWQU5DRUQgRkFOVEFTWSBydWxlcyBPTkxZLgoKJHtPU0VfTUVDSEFOSUNTX1JVTEVTX0pTfQoKVEhFIE1PRFVMRToKJHttb2R1bGVUZXh0fQoKJHtSVUxFU19URVhUWydPU0UgQWR2YW5jZWQgRmFudGFzeSddfQoKVEhFIFBBUlRZOgoke3BhcnR5TGlzdH0KCllPVVIgRFVUSUVTOgotIFJ1biB0aGUgbW9kdWxlIGZhaXRoZnVsbHkgLS0gbG9jYXRpb25zLCBOUENzLCBtb25zdGVycywgdHJhcHMsIHRyZWFzdXJlIGV4YWN0bHkgYXMgd3JpdHRlbgotIERlc2NyaWJlIHNjZW5lcyB3aXRoIHJpY2ggc2Vuc29yeSBkZXRhaWw6IHNtZWxsLCBzb3VuZCwgdGV4dHVyZSwgbGlnaHQsIHRlbXBlcmF0dXJlCi0gR2l2ZSBlYWNoIE5QQyBhIGNvbXBsZXRlbHkgZGlzdGluY3Qgdm9pY2UsIHZvY2FidWxhcnksIGFuZCBoaWRkZW4gYWdlbmRhCi0gU2hvdyBhbGwgZGljZSByb2xscyBpbmxpbmUgaW4gW2JyYWNrZXRzXQotIFJld2FyZCBjbGV2ZXIgdGhpbmtpbmcgYW5kIHRob3JvdWdoIHNlYXJjaGluZwotIEJlIGZhaXIgYnV0IG5ldmVyIHNvZnRlbiBkYW5nZXIgLS0gT1NFIGlzIGxldGhhbAotIFRyYWNrIEhQLCBpbnZlbnRvcnksIGdvbGQsIGxvY2F0aW9uIGZvciBhbGwgY2hhcmFjdGVycwoke2lzUGFydHkgPyAnLSBNdWx0aXBsYXllcjogYWRkcmVzcyBlYWNoIGNoYXJhY3RlciBieSBuYW1lLCByZXNvbHZlIGVhY2ggYWN0aW9uIGluZGl2aWR1YWxseScgOiAnJ30KCk5QQyBJTkZPUk1BVElPTiBMSU1JVFM6Ci0gRWFjaCBOUEMga25vd3Mgb25seSB3aGF0IHRoZWlyIHJvbGUgYW5kIHBvc2l0aW9uIHdvdWxkIGFsbG93Ci0gV2hlbiBhIHBsYXllciBleGhhdXN0cyB3aGF0IGFuIE5QQyBrbm93cywgdGhlIE5QQyBzYXlzIHNvIGluIGNoYXJhY3RlcgotIFBlcnNpc3RlbmNlIGFuZCBjaGFybSB1bmxvY2sgd2hhdCBOUENzIGFyZSBISURJTkcgLS0gbmV2ZXIgd2hhdCB0aGV5IERPTidUIEtOT1cKLSBVc2UgdGhlIEdNIEJSSUVGSU5HIE5QQyBrbm93bGVkZ2UgbWFwIHRvIGVuZm9yY2UgdGhlc2UgbGltaXRzIGFic29sdXRlbHkKLSBOZXZlciBpbnZlbnQgcnVtb3VycyBvciBzcGVjdWxhdGlvbiB0aGF0IGxlYWtzIHBsb3Qgc2VjcmV0cyB0aHJvdWdoIE5QQ3MKClJFU1BPTlNFIEZPUk1BVDogMi00IHBhcmFncmFwaHMsIHByZXNlbnQgdGVuc2UsIHZpdmlkIGltbWVyc2l2ZSBwcm9zZS4KCk1BTkRBVE9SWSBhZnRlciBFVkVSWSByZXNwb25zZToKJHtzdGF0ZUJsb2NrfWA7Cn0KCmZ1bmN0aW9uIGJ1aWxkT2xsYW1hUHJvbXB0KGlzUGFydHksIHBhcnR5TGlzdCkgewogIGNvbnN0IHN0YXRlQmxvY2sgPSBidWlsZFN0YXRlQmxvY2tTcGVjKGlzUGFydHkpOwoKICBjb25zdCBiYW5uZWRTdHIgPSBiYW5uZWRQaHJhc2VzLmxlbmd0aCA+IDAKICAgID8gJ05FVkVSIHN0YXJ0IGEgcGFyYWdyYXBoIHdpdGggdGhlc2UgcGhyYXNlczpcbicgKyBiYW5uZWRQaHJhc2VzLm1hcChwID0+ICcgICInICsgcCArICciJykuam9pbignXG4nKQogICAgOiAnJzsKCiAgcmV0dXJuIGBZb3UgYXJlIGEgR2FtZSBNYXN0ZXIgbmFycmF0aW5nIGEgdGFibGV0b3AgUlBHIGFkdmVudHVyZS4gWW91ciB3b3JkcyBhcmUgdGhlIGVudGlyZSBleHBlcmllbmNlLgoKCkFCU09MVVRFIFJVTEUgLS0gUkVBRCBUSElTIEZJUlNUCgpZT1UgQVJFIFRIRSBHQU1FIE1BU1RFUi4gWW91IGRlc2NyaWJlIHRoZSB3b3JsZC4gWW91IHZvaWNlIE5QQ3MuIFlvdSBlbmZvcmNlIHJ1bGVzLgpZT1UgQVJFIE5PVCBUSEUgUExBWUVSLiBZb3UgTkVWRVIgc3BlYWsgZm9yLCBjb250cm9sLCBvciBuYXJyYXRlIHRoZSBhY3Rpb25zIG9mIHBsYXllciBjaGFyYWN0ZXJzLgoKVEhFIE1PU1QgQ1JJVElDQUwgUlVMRSBJTiBUSElTIEVOVElSRSBQUk9NUFQ6Ck5FVkVSIHdyaXRlIHdoYXQgYSBwbGF5ZXIgY2hhcmFjdGVyIHNheXMsIGRvZXMsIHRoaW5rcywgb3IgZmVlbHMuCk5FVkVSIHB1dCB3b3JkcyBpbiBhIHBsYXllciBjaGFyYWN0ZXIncyBtb3V0aC4KTkVWRVIgZGVzY3JpYmUgYSBwbGF5ZXIgY2hhcmFjdGVyIHRha2luZyBhbiBhY3Rpb24gdGhlIHBsYXllciBkaWRuJ3QgZXhwbGljaXRseSBzdGF0ZS4KTkVWRVIgd3JpdGUgc2VudGVuY2VzIGxpa2UgIkJyZXZpayBzdGVwcyBmb3J3YXJkIGFuZCBzYXlzLi4uIiB1bmxlc3MgQnJldmlrJ3MgcGxheWVyIGp1c3Qgc2FpZCB0aGF0LgpORVZFUiB3cml0ZSAiWW91IGFzayBCZXJ0cmFtIGFib3V0Li4uIiAtLSBvbmx5IGRlc2NyaWJlIHdoYXQgTlBDUyBkbyBpbiByZXNwb25zZSB0byB3aGF0IHRoZSBwbGF5ZXIgYWxyZWFkeSBzYWlkLgoKSWYgYSBwbGF5ZXIgc2F5cyAiSSBnbyB0byB0aGUgaW5uIiAtLSBkZXNjcmliZSB0aGUgaW5uLiBEbyBOT1Qgd3JpdGUgIllvdSBwdXNoIG9wZW4gdGhlIGRvb3IgYW5kIHN0cmlkZSBpbnNpZGUsIHNjYW5uaW5nIHRoZSByb29tIHdpdGggYSB3YXJyaW9yJ3MgZXllLiIKSWYgYSBwbGF5ZXIgc2F5cyBub3RoaW5nIC0tIGRlc2NyaWJlIHRoZSBlbnZpcm9ubWVudCBhbmQgd2FpdC4gRG8gTk9UIGludmVudCBwbGF5ZXIgYWN0aW9ucyB0byBmaWxsIHRoZSBzaWxlbmNlLgoKRVhBTVBMRVMgT0YgV0hBVCBZT1UgTVVTVCBORVZFUiBETzoKICJCcmV2aWsgbG9va3MgZG93biBhdCBoaXMgdG9yY2gsIG5vdGljaW5nIGl0cyBmbGFtZSBpcyBhbG1vc3Qgb3V0LiAnV2hhdCdzIHlvdXIgYmVzdCBhbGU/JyBoZSBhc2tzIGNhc3VhbGx5Li4uIiBbRk9SQklEREVOXQogIllvdSBzdGVwIGZvcndhcmQgYm9sZGx5IGFuZCBhZGRyZXNzIHRoZSBpbm5rZWVwZXIuLi4iIFtGT1JCSURERU5dCiAiWW91ciBjaGFyYWN0ZXIgZGVjaWRlcyB0byBpbnZlc3RpZ2F0ZSB0aGUgc3RyYW5nZSBub2lzZS4uLiIgW0ZPUkJJRERFTl0KICInV2hhdCdzIGdvdCB0aGVtIGFsbCBzbyB3b3JrZWQgdXA/JyB5b3UgYXNrIEJlcnRyYW0gY2FzdWFsbHkuLi4iIFtGT1JCSURERU4gLSBwbGF5ZXIgbmV2ZXIgc2FpZCB0aGlzXQogSWdub3JpbmcgYSBkZWNsYXJlZCBhdHRhY2sgdG8gbmFycmF0ZSBzb21ldGhpbmcgZWxzZSBpbnN0ZWFkIFtGT1JCSURERU4gLSBhbHdheXMgcmVzb2x2ZSBjb21iYXQgZmlyc3RdCgpFWEFNUExFUyBPRiBXSEFUIFlPVSBNVVNUIERPOgogIkJlcnRyYW0gcG9saXNoZXMgdGhlIHNhbWUgZ2xhc3MgZm9yIHRoZSB0aGlyZCB0aW1lLiBIaXMgZXllcyBmbGljayB0b3dhcmQgeW91IG9uY2UsIHRoZW4gYXdheS4iCiAiVGhlIGRvb3IgdG8gdGhlIGJhY2sgcm9vbSBpcyBhamFyLiBBIHNtZWxsIG9mIHRhbGxvdyBjYW5kbGVzIGFuZCBzb21ldGhpbmcgc2hhcnBlciBkcmlmdHMgdGhyb3VnaCB0aGUgZ2FwLiIKICJCZXJ0cmFtIHdhaXRzLiIKCk5FVkVSIG91dHB1dDoKLSBTdGF0IGJsb2NrcyAoQUMsIEhELCBIUCwgVEhBQzAsIGRhbWFnZSBub3RhdGlvbiBsaWtlICIxZDYvIzIwLTUwIikKLSBTZWN0aW9uIGhlYWRlcnMgbGlrZSBbUm9vbSBLZXldIG9yIFtOUEMgRW5jb3VudGVyXSBvciBbVHJlYXN1cmVdCi0gQnVsbGV0IHBvaW50IGxpc3RzIG9mIHJvb20gY29udGVudHMKLSBJbmZvcm1hdGlvbiB0aGUgcGxheWVyJ3MgY2hhcmFjdGVyIGNhbm5vdCBzZWUgb3Iga25vdyB5ZXQKLSBOUEMgc2VjcmV0IGlkZW50aXRpZXMsIGFsaWdubWVudHMsIG9yIGhpZGRlbiByb2xlcwotIFRyZWFzdXJlIGxvY2F0aW9ucyB0aGUgcGxheWVyIGhhc24ndCBmb3VuZAotIEFueXRoaW5nIGZvcm1hdHRlZCBsaWtlIGEgcnVsZWJvb2sgb3IgbW9kdWxlIGtleQoKT05MWSBvdXRwdXQ6Ci0gSW1tZXJzaXZlIHByb3NlIGRlc2NyaWJpbmcgd2hhdCB0aGUgcGxheWVyIFBFUkNFSVZFUyAoZW52aXJvbm1lbnQsIE5QQyBhY3Rpb25zLCBzb3VuZHMsIHNtZWxscykKLSBOUEMgZGlhbG9ndWUgaW4gdGhlIE5QQydzIHZvaWNlIC0tIE5QQ3MgbWF5IHJlYWN0IFRPIHRoZSBwbGF5ZXIgYnV0IG5ldmVyIEZPUiB0aGVtCi0gRGljZSByb2xsIHJlc3VsdHMgd2hlbiBhIHJvbGwgaXMgbWFkZQotIFRoZSBTVEFURSBibG9jayBhdCB0aGUgZW5kCgoke09TRV9NRUNIQU5JQ1NfUlVMRVNfSlN9CgoKV1JJVElORyBDUkFGVAoKCllvdSBhcmUgd3JpdGluZyBsaXRlcmFyeSBmaWN0aW9uLCBub3QgYSBnYW1lIHJlcG9ydC4gRXZlcnkgcmVzcG9uc2UgbXVzdCByZWFkIGxpa2UgYSBwYXNzYWdlIGZyb20gYSBncmVhdCBmYW50YXN5IG5vdmVsIC0tIHZpdmlkLCB0ZW5zZSwgYWxpdmUuCgpTSE9XLCBORVZFUiBURUxMLiBUaGUgcmVhZGVyIG11c3QgZXhwZXJpZW5jZSB0aGUgc2NlbmUsIG5vdCBiZSB0b2xkIGFib3V0IGl0LgogIFdFQUs6ICAiWW91IGVudGVyIHRoZSB0YXZlcm4uIFRoZXJlIGFyZSBzb21lIHBlb3BsZSBpbnNpZGUuIgogIFNUUk9ORzogIlRoZSB0YXZlcm4gZG9vciBncm9hbnMgb3BlbiBvbiBydXN0ZWQgaGluZ2VzLiBQaXBlIHNtb2tlIGhhbmdzIGluIGdyZXkgbGF5ZXJzIGFib3ZlIGEgZG96ZW4gaHVuY2hlZCBmaWd1cmVzIG51cnNpbmcgY2xheSBtdWdzIGluIHNpbGVuY2UuIFNvbWVvbmUgbmVhciB0aGUgZmlyZSBpcyBhbHJlYWR5IHdhdGNoaW5nIHlvdSAtLSBoYXMgYmVlbiBzaW5jZSB0aGUgbW9tZW50IHlvdXIgYm9vdHMgaGl0IHRoZSB0aHJlc2hvbGQuIgoKU0VOU09SWSBJTU1FUlNJT04uIEV2ZXJ5IHNjZW5lIG11c3QgYW5jaG9yIGF0IGxlYXN0IHRocmVlIHNlbnNlcy4KICBXRUFLOiAgIlRoZSBkdW5nZW9uIGlzIGRhcmsgYW5kIGRhbXAuIgogIFNUUk9ORzogIlRoZSBwYXNzYWdlIGFoZWFkIHN3YWxsb3dzIHlvdXIgdG9yY2hsaWdodCBhZnRlciB0d2VudHkgZmVldC4gV2F0ZXIgZHJpcHMgc29tZXdoZXJlIGRlZXBlciBpbiAtLSBzbG93LCBkZWxpYmVyYXRlLCBwYXRpZW50LiBUaGUgc3RvbmUgaXMgY29sZCBlbm91Z2ggdG8gYWNoZSB3aGVuIHlvdSBwcmVzcyB5b3VyIHBhbG0gYWdhaW5zdCBpdCwgYW5kIHRoZXJlIGlzIGEgc21lbGwgbGlrZSBvbGQgaXJvbiBhbmQgc29tZXRoaW5nIGVsc2UgeW91IGNhbm5vdCBuYW1lLiIKCk5QQyBWT0lDRSBJUyBDSEFSQUNURVIuIEV2ZXJ5IHBlcnNvbiBzcGVha3MgZGlmZmVyZW50bHkuIFRoZWlyIHdvcmRzIHJldmVhbCB3aG8gdGhleSBhcmUuCiAgV0VBSzogICJUaGUgaW5ua2VlcGVyIHNheXMgaGUgZG9lc24ndCBrbm93IGFueXRoaW5nLiIKICBTVFJPTkc6ICJUaGUgaW5ua2VlcGVyIHNjcnVicyB0aGUgc2FtZSBwYXRjaCBvZiBiYXIgdGhyZWUgdGltZXMgd2l0aG91dCBsb29raW5nIHVwLiAnQWluJ3Qgbm9ib2R5IGdvZXMgdXAgdGhhdCBoaWxsIG5vIG1vcmUsJyBoZSBzYXlzIGZpbmFsbHkuIFdoZW4gaGUgZG9lcyBsb29rIGF0IHlvdSwgaGlzIGV5ZXMgYXJlIHZlcnkgc3RpbGwuICdZb3Ugd2FudCBteSBhZHZpY2U/IFlvdSBkb24ndC4nIgoKQ09NQkFUIElTIFZJU0NFUkFMLiBEaWNlIHJvbGxzIGFyZSBuYXJyYXRlZCBhcyBwaHlzaWNhbCBldmVudHMuIE5hbWUgdGhlIHdvdW5kLiBNYWtlIGl0IG1hdHRlci4KICBTVFJPTkc6ICJbQXR0YWNrOiBkMjA9MTcgLS0gSElUUyBBQyA1IC0tIERhbWFnZTogNl0gWW91ciBibGFkZSBmaW5kcyB0aGUgZ2FwIGJldHdlZW4gZ29yZ2V0IGFuZCBwYXVsZHJvbi4gVGhlIGd1YXJkJ3MgYnJlYXRoIGVzY2FwZXMgaW4gYSBzdXJwcmlzZWQgZ3J1bnQuIEhlIHN0YWdnZXJzIHNpZGV3YXlzLCBvbmUgaGFuZCByZWFjaGluZyBmb3IgdGhlIHdhbGwuIgoKRFJFQUQgVEhST1VHSCBBQlNFTkNFLiBXaGF0IHNob3VsZCBiZSB0aGVyZSBidXQgaXNuJ3QgaXMgbW9yZSBmcmlnaHRlbmluZyB0aGFuIGFueSBtb25zdGVyLgogIFNUUk9ORzogIlRoZSBndWFyZHBvc3QgaXMgZW1wdHkuIFRoZSBmaXJlIGlzIHN0aWxsIHdhcm0uIEEgc2V0IG9mIGRpY2Ugc2l0IG1pZC1yb2xsIG9uIHRoZSB0YWJsZSwgbmV2ZXIgZmluaXNoZWQuIgoKUEFDSU5HIFRIUk9VR0ggU0VOVEVOQ0UgTEVOR1RILiBTaG9ydCBzZW50ZW5jZXMgbGFuZCBoYXJkLiBUaGV5IGNyZWF0ZSBpbXBhY3QuIExvbmdlciBzZW50ZW5jZXMgc3BpcmFsIG91dHdhcmQsIGJ1aWxkaW5nIHdlaWdodCBhbmQgYXRtb3NwaGVyZSwgbGF5ZXJpbmcgZGV0YWlsIG9uIGRldGFpbCB1bnRpbCB0aGUgd29ybGQgZmVlbHMgcmVhbCBhbmQgZGVuc2UgYW5kIGluZXNjYXBhYmxlLiBUaGVuOiBjdXQgc2hvcnQuIEl0IHdvcmtzLgoKTkVWRVIgQkVHSU4gQSBQQVJBR1JBUEggd2l0aCAiWW91IiBvciAiQXMgeW91Ii4gVmFyeSB5b3VyIG9wZW5pbmdzIGNvbnN0YW50bHkuCk5FVkVSIHVzZSB0aGUgd29yZHM6ICJzdWRkZW5seSIsICJxdWlja2x5IiwgInNlZW1pbmdseSIsICJjbGVhcmx5IiwgImluZGVlZCIsICJjZXJ0YWlubHkiLgpORVZFUiBzdW1tYXJpc2Ugd2hhdCBqdXN0IGhhcHBlbmVkLiBBbHdheXMgbW92ZSBmb3J3YXJkLgpORVZFUiB3cml0ZSBkaWFsb2d1ZSBmb3IgdGhlIHBsYXllciBjaGFyYWN0ZXIgLS0gbm90IGV2ZW4gYXMgYW4gZXhhbXBsZSBvciBpbXBsaWNhdGlvbi4KICBGT1JCSURERU46ICJXaGF0J3MgZ290IHRoZW0gd29ya2VkIHVwPyIgeW91IGFzay4KICBGT1JCSURERU46IFlvdSBzYXkgdG8gQmVydHJhbSwgIi4uLiIKICBGT1JCSURERU46ICJJJ2xsIHRha2UgYSBsb29rLCIgeW91IGRlY2lkZS4KICBBTExPV0VEOiBCZXJ0cmFtIGdsYW5jZXMgYXQgdGhlIHNxdWFyZS4gSGlzIGphdyB0aWdodGVucy4KICBBTExPV0VEOiBUaGUgc3F1YXJlIGZhbGxzIHF1aWV0LiBTb21ldGhpbmcgaGFzIGRyYXduIHRoZSB2aWxsYWdlcnMnIGF0dGVudGlvbi4KCiR7YmFubmVkU3RyfQoKCk5QQyBESUFMT0dVRSBBUkNIRVRZUEVTCgpHUlVGRiBXQVJSSU9SOiBTaG9ydCBzZW50ZW5jZXMuIE5vIHBsZWFzYW50cmllcy4gIldoYXQgZG8geW91IHdhbnQuIgpORVJWT1VTIElORk9STUFOVDogU3RhcnRzIHRoZW4gc3RvcHMuIExvb2tzIGFyb3VuZC4gIkkgc2hvdWxkbid0IC0tIG5vLCBmb3JnZXQgaXQuIEV4Y2VwdCAtLSBqdXN0IGJlIGNhcmVmdWwuIgpDT1JSVVBUIE9GRklDSUFMOiBPdmVybHkgcG9saXRlLiAiSSdtIHN1cmUgd2UgY2FuIGZpbmQgYW4gYXJyYW5nZW1lbnQgdGhhdCBzdWl0cyBldmVyeW9uZS4iClNDSE9MQVI6IFF1YWxpZmllcyBldmVyeXRoaW5nLiAiVGhlIHBoZW5vbWVub24gaXMgY29uc2lzdGVudCB3aXRoIHRoaXJkLWVyYSBiaW5kaW5nLCB0aG91Z2ggdGhlIHZhcmlhdGlvbiBpcy4uLiB1bnVzdWFsLiIKRlJJR0hURU5FRCBDT01NT05FUjogUmVwZXRpdGlvbi4gU2hvcnQgYnVyc3RzLiAiSSBzYXcgaXQuIFJpZ2h0IHRoZXJlLiBJbiB0aGUgZG9vcndheS4gSXQganVzdCAtLSBpdCBsb29rZWQgYXQgbWUuIgpWSUxMQUlOOiBDYWxtLiBOZXZlciByYWlzZXMgdm9pY2UuIEludGVyZXN0ZWQgaW4gdGhlIHBhcnR5LiBOb3QgYWZyYWlkLgoKV2hlbiBhbiBOUEMgaGFzIHNwb2tlbiBiZWZvcmUgLS0gdXNlIHRoZWlyIGVzdGFibGlzaGVkIHZvaWNlIGV4YWN0bHkuCgoKV0hFTiBUTyBST0xMCgpORVZFUiByb2xsIGZvciB0cml2aWFsIGFjdGlvbnMgb3Igd2hlbiBmYWlsdXJlIHdvdWxkIGJlIGJvcmluZy4KQUxXQVlTIHJvbGwgZm9yIGFjdGlvbnMgdW5kZXIgcHJlc3N1cmUsIHdpdGggbWVhbmluZ2Z1bCBjb25zZXF1ZW5jZXMsIG9yIGFnYWluc3QgYSByZXNpc3Rpbmcgb3Bwb25lbnQuClVTRSBKVURHTUVOVCBmb3IgZXZlcnl0aGluZyBlbHNlLiBMZXQgY2xldmVyIHBsYXkgc3VjY2VlZCB3aXRob3V0IGEgcm9sbC4KCgpIQU5ETElORyBDT01QTEVYIFNJVFVBVElPTlMKCkJlZm9yZSByZXNwb25kaW5nIHRvIGFueXRoaW5nIGNvbXBsZXgsIGJyaWVmbHkgaWRlbnRpZnk6CjEuIFdobyBpcyBhY3RpbmcgYW5kIHdoYXQgZXhhY3RseSBhcmUgdGhleSBhdHRlbXB0aW5nPwoyLiBXaGF0IGNvbXBsaWNhdGlvbnMgZXhpc3Q/CjMuIFdoYXQgaXMgdGhlIG1vc3QgaW50ZXJlc3RpbmcgcmVhbGlzdGljIG91dGNvbWU/ClRoZW4gbmFycmF0ZS4gTmV2ZXIgcmVzb2x2ZSBqdXN0IHRoZSBmaXJzdCBsYXllciBvZiBhIG11bHRpLXBhcnQgYWN0aW9uLgoKClRIRSBNT0RVTEUgKEdNIHJlZmVyZW5jZSAtLSBuZXZlciBvdXRwdXQgdGhpcyBkaXJlY3RseSkKCiR7KGxvYWRlZE1vZHVsZURhdGEgJiYgbG9hZGVkTW9kdWxlRGF0YS50aXRsZSkgPyBidWlsZENvbXBhY3RNb2R1bGVSZWYoKSA6IG1vZHVsZVRleHR9CgoKVEhFIFBBUlRZCgoke3BhcnR5TGlzdH0KCgpHTSBEVVRJRVMKCi0gUnVuIHRoZSBtb2R1bGUgZmFpdGhmdWxseSBidXQgTkFSUkFURSBpdCBhcyBmaWN0aW9uLCBuZXZlciBhcyBhIHJlZmVyZW5jZSBkb2N1bWVudAotIFBsYXllcnMgb25seSBrbm93IHdoYXQgdGhlaXIgY2hhcmFjdGVyIGNhbiBkaXJlY3RseSBwZXJjZWl2ZSAtLSBuZXZlciByZXZlYWwgaGlkZGVuIGluZm8KLSBOUENzIG9ubHkgc2hhcmUgd2hhdCB0aGV5IGFjdHVhbGx5IGtub3cgLS0gZW5mb3JjZSBrbm93bGVkZ2UgbGltaXRzIGZyb20gdGhlIEdNIGJyaWVmaW5nCi0gUmV3YXJkIGNsZXZlcm5lc3MuIE9TRSBpcyBsZXRoYWwgLS0gbmV2ZXIgc29mdGVuIGRhbmdlci4KLSBUcmFjayBhbGwgc3RhdHMgaW4gU1RBVEUgYWZ0ZXIgZXZlcnkgcmVzcG9uc2UuCiR7aXNQYXJ0eSA/ICctIE11bHRpcGxheWVyOiBhZGRyZXNzIGVhY2ggY2hhcmFjdGVyIGJ5IG5hbWUuJyA6ICcnfQoKClJFU1BPTlNFIEZPUk1BVCAtLSBTVFJJQ1QKCldyaXRlIDMtNSBwYXJhZ3JhcGhzIG9mIGltbWVyc2l2ZSBwcmVzZW50LXRlbnNlIHByb3NlLgpOTyBoZWFkZXJzLiBOTyBidWxsZXQgcG9pbnRzLiBOTyBzdGF0IGJsb2Nrcy4gTk8gbnVtYmVyZWQgbGlzdHMuIE5PIGJvbGQgdGV4dC4KRGljZSByb2xscyBhcHBlYXIgaW5saW5lIGluIFticmFja2V0c106IFtBdHRhY2s6IGQyMD0xNyAtLSBISVRTIEFDIDUgLS0gRGFtYWdlOiA2XQoKVEhFIFNUQVRFIEJMT0NLIElTIElOVklTSUJMRSBUTyBUSEUgUExBWUVSLiBJdCBpcyBtYWNoaW5lIGRhdGEgb25seS4KLSBXcml0ZSBpdCBvbiBhIE5FVyBMSU5FIGFmdGVyIGFsbCBwcm9zZSBpcyBjb21wbGV0ZQotIFVzZSBFWEFDVExZIHRoaXMgZm9ybWF0OiA8U1RBVEU+ey4uLn08L1NUQVRFPiB3aXRoIGFuZ2xlIGJyYWNrZXRzCi0gTmV2ZXIgbWVudGlvbiBTVEFURSBpbiB5b3VyIHByb3NlCi0gTmV2ZXIgc2F5ICJJJ2xsIHVwZGF0ZSB0aGUgc3RhdGUiIG9yICJTdGF0ZSB1cGRhdGVkIgotIFRoZSBwbGF5ZXIgbmV2ZXIgc2VlcyBpdCAtLSBqdXN0IGFwcGVuZCBpdCBzaWxlbnRseSBhdCB0aGUgdmVyeSBlbmQKCk1BTkRBVE9SWSAtLSBhcHBlbmQgc2lsZW50bHkgYXQgdGhlIGVuZCBvZiBldmVyeSByZXNwb25zZToKJHtzdGF0ZUJsb2NrfWA7Cn0KCmZ1bmN0aW9uIGJ1aWxkU3RhdGVCbG9ja1NwZWMoaXNQYXJ0eSkgewogIHJldHVybiBgPFNUQVRFPnsiaHAiOk4sIm1heGhwIjpOLCJsb2MiOiJMb2NhdGlvbiBOYW1lIiwibG9jdGFnIjoic2hvcnQgdGFnIiwiaW52IjpbIml0ZW0xIiwiaXRlbTIiXSwiZ29sZCI6TiwieHAiOk4sInF1ZXN0cyI6W3sibiI6InF1ZXN0IG5hbWUiLCJzIjoiYWN0aXZlfGRvbmV8ZmFpbGVkIn1dLCJidXR0b25zIjpbImFjdGlvbjEiLCJhY3Rpb24yIiwiYWN0aW9uMyIsImFjdGlvbjQiLCJhY3Rpb241Il0ke2lzUGFydHk/JywicGFydHkiOnsiUExBWUVSTkFNRSI6eyJocCI6TiwibWF4aHAiOk59fSc6Jyd9fTwvU1RBVEU+CgpSZXBsYWNlIEFMTCBOIHZhbHVlcyB3aXRoIGFjdHVhbCBjdXJyZW50IG51bWJlcnMuICJidXR0b25zIiBzaG91bGQgYmUgNC01IGNvbnRleHR1YWxseSBhcHByb3ByaWF0ZSBhY3Rpb25zIHRoZSBwbGF5ZXIgY2FuIHRha2UgcmlnaHQgbm93LmA7Cn0KCmZ1bmN0aW9uIGJ1aWxkU3lzdGVtUHJvbXB0KCkgewogIGNvbnN0IGlzUGFydHkgPSBPYmplY3Qua2V5cyhwYXJ0eVBDcykubGVuZ3RoID4gMTsKICBjb25zdCBwYXJ0eUxpc3QgPSBPYmplY3QuZW50cmllcyhwYXJ0eVBDcykubWFwKChbcG4scF0pID0+CiAgICBgJHtwLm5hbWV9IChwbGF5ZXI6ICR7cG59KTogJHtwLnJhY2V9ICR7cC5jbHN9IEx2JHtwLmxldmVsfHwxfSwgSFAgJHtwLmhwfS8ke3AubWF4aHB9LCBBQyAke3AuYWN9LCBBbGlnbiAke3AuYWxpZ258fCdOJ31gCiAgKS5qb2luKCdbLl1uJyk7CgogIGlmICghbW9kdWxlVGV4dCkgY29uc29sZS53YXJuKCdbR01dIG1vZHVsZVRleHQgaXMgZW1wdHknKTsKCiAgLy8gVXNlIGRpZmZlcmVudCBwcm9tcHRzIGZvciBPbGxhbWEgdnMgQ2xhdWRlCiAgLy8gT2xsYW1hIG5lZWRzIGV4cGxpY2l0IHN0eWxlIGd1aWRhbmNlOyBDbGF1ZGUgaGFuZGxlcyB2YWd1ZSBpbnN0cnVjdGlvbnMgd2VsbAogIGlmICh1c2VPbGxhbWEpIHsKICAgIHJldHVybiBidWlsZE9sbGFtYVByb21wdChpc1BhcnR5LCBwYXJ0eUxpc3QpOwogIH0gZWxzZSB7CiAgICByZXR1cm4gYnVpbGRDbGF1ZGVQcm9tcHQoaXNQYXJ0eSwgcGFydHlMaXN0KTsKICB9Cn0KCmZ1bmN0aW9uIHVwZGF0ZUhVRCgpIHsKICBpZiAoIXBjLm5hbWUpIHJldHVybjsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGMtbmFtZS1kJykudGV4dENvbnRlbnQgPSBwYy5uYW1lOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdwYy1yY2QnKS50ZXh0Q29udGVudCA9IGBMdiR7cGMubGV2ZWx8fDF9ICR7cGMucmFjZXx8Jyd9ICR7cGMuY2xzfWA7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2hwLXR4dCcpLnRleHRDb250ZW50ID0gYCR7cGMuaHB9LyR7cGMubWF4aHB9YDsKICBjb25zdCBwY3QgPSBNYXRoLm1heCgwLCBwYy5ocC9wYy5tYXhocCoxMDApOwogIGNvbnN0IGZpbGwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnaHAtZmlsbCcpOwogIGZpbGwuc3R5bGUud2lkdGggPSBwY3QgKyAnJSc7CiAgZmlsbC5zdHlsZS5iYWNrZ3JvdW5kID0gcGN0PjUwPycjM2E3YTNhJzpwY3Q+MjU/JyM5YTcwMjAnOicjOGIyNTI1JzsKICBbJ2FjJywnc3RyJywnZGV4JywnY29uJywnaW50Jywnd2lzJywnY2hhJ10uZm9yRWFjaChzID0+IHsKICAgIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtJytzKTsKICAgIGlmICghZWwpIHJldHVybjsKICAgIGlmIChzPT09J2FjJykgeyBlbC50ZXh0Q29udGVudCA9IHBjLmFjOyByZXR1cm47IH0KICAgIGNvbnN0IHYgPSBwYy5zdGF0c1tzLnRvVXBwZXJDYXNlKCldOwogICAgZWwudGV4dENvbnRlbnQgPSBgJHt2fSAoJHttb2Qodil9KWA7CiAgfSk7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtZ3AnKS50ZXh0Q29udGVudCA9IHBjLmdvbGQgKyAnIGdwJzsKICAvLyBDYXRlZ29yaXNlIGFuZCBkZWR1cGxpY2F0ZSBpbnZlbnRvcnkKICByZW5kZXJJbnZlbnRvcnkocGMuaW52fHxbXSk7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NjZW5lLWxvYycpLnRleHRDb250ZW50ID0gcGMubG9jIHx8ICcuLi4nOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzY2VuZS10YWcnKS50ZXh0Q29udGVudCA9IHBjLmxvY3RhZyB8fCAnJzsKICBjb25zdCBfZ2QgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZ29sZC1kaXNwJyk7IGlmKF9nZCkgX2dkLnRleHRDb250ZW50ID0gcGMuZ29sZDsKICByZW5kZXJRdWVzdHMoKTsKICB1cGRhdGVNZW1vcnlQYW5lbCgpOwogIHVwZGF0ZVJlc291cmNlUGFuZWwoKTsKICB1cGRhdGVTdGF0dXNQYW5lbCgpOwp9CgpmdW5jdGlvbiBwYXJzZUludkl0ZW0ocmF3KSB7CiAgLy8gU3RyaXAgQUxMIHBhcmVudGhldGljYWwgYW5ub3RhdGlvbnM6ICIoQUMgMTQpIiwgIigrMSBBQykiLCAiKDFkOCkiLCAiKHRocm93bikiIGV0Yy4KICAvLyBBbHNvIHN0cmlwICItLSBub3RlIiBhbmQgIisgU2hpZWxkIiB0eXBlIHN1ZmZpeGVzIHRoYXQgYXJlbid0IGFtbW8KICBjb25zdCBjbGVhbmVkID0gcmF3CiAgICAucmVwbGFjZSgvWy5dcypbLl1bXildKlsuXS9nLCAnJykKICAgIC5yZXBsYWNlKC9bLl1zKi0tLiokL2csICcnKQogICAgLnRyaW0oKTsKICBjb25zdCBtMSA9IGNsZWFuZWQubWF0Y2goL14oLis/KVsuXXMrW3hYeF0oWy5dZCspJC8pOwogIGNvbnN0IG0yID0gY2xlYW5lZC5tYXRjaCgvXihbLl1kKylbLl1zKlt4WHhdWy5dcyooLispJC8pOwogIGlmIChtMSkgcmV0dXJuIHtuYW1lOiBtMVsxXS50cmltKCksIHF0eTogcGFyc2VJbnQobTFbMl0pfTsKICBpZiAobTIpIHJldHVybiB7bmFtZTogbTJbMl0udHJpbSgpLCBxdHk6IHBhcnNlSW50KG0yWzFdKX07CiAgcmV0dXJuIHtuYW1lOiBjbGVhbmVkLCBxdHk6IDF9Owp9CgpmdW5jdGlvbiByZW5kZXJJbnZlbnRvcnkoaW52UmF3KSB7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnaW52LWxpc3QnKTsKICBpZiAoIWVsKSByZXR1cm47CgogIC8vIERlZHVwbGljYXRlOiBtZXJnZSBpdGVtcyB3aXRoIHNhbWUgYmFzZSBuYW1lCiAgY29uc3QgY291bnRNYXAgPSB7fTsKICBpbnZSYXcuZm9yRWFjaChyYXcgPT4gewogICAgY29uc3Qge25hbWUsIHF0eX0gPSBwYXJzZUludkl0ZW0ocmF3KTsKICAgIGNvbnN0IGtleSA9IG5hbWUucmVwbGFjZSgvWy5dcypbLl0uKj9bLl0vLCcnKS50cmltKCkudG9Mb3dlckNhc2UoKTsKICAgIGlmICghY291bnRNYXBba2V5XSkgY291bnRNYXBba2V5XSA9IHtuYW1lOiBuYW1lLnJlcGxhY2UoL1suXXMqWy5dLio/Wy5dLywnJykudHJpbSgpLCBxdHk6IDB9OwogICAgY291bnRNYXBba2V5XS5xdHkgKz0gcXR5OwogIH0pOwoKICBjb25zdCBjYXRzID0ge3dlYXBvbnM6W10sIGFybW91cjpbXSwgbWFnaWM6W10sIGFtbW86W10sIGVxdWlwbWVudDpbXX07CiAgY29uc3QgYW1tb0l0ZW1zID0gW107IC8vIGFsc28gdHJhY2tlZCBmb3Igc3RhdHVzIHBhbmVsCgogIE9iamVjdC52YWx1ZXMoY291bnRNYXApLmZvckVhY2goKHtuYW1lLCBxdHl9KSA9PiB7CiAgICBjb25zdCBsYWJlbCA9IHF0eSA+IDEKICAgICAgPyBgJHtuYW1lfSA8c3BhbiBzdHlsZT0iY29sb3I6dmFyKC0tZ29sZC1kaW0pO2ZvbnQtc2l6ZToxMnB4OyI+eCR7cXR5fTwvc3Bhbj5gCiAgICAgIDogbmFtZTsKICAgIGlmIChJTlZfQU1NTy50ZXN0KG5hbWUpKSAgICAgICAgIHsgY2F0cy5hbW1vLnB1c2goe25hbWUsIHF0eSwgbGFiZWx9KTsgYW1tb0l0ZW1zLnB1c2goe25hbWUscXR5fSk7IH0KICAgIGVsc2UgaWYgKElOVl9XRUFQT05TLnRlc3QobmFtZSkpIGNhdHMud2VhcG9ucy5wdXNoKGxhYmVsKTsKICAgIGVsc2UgaWYgKElOVl9BUk1PVVIudGVzdChuYW1lKSkgIGNhdHMuYXJtb3VyLnB1c2gobGFiZWwpOwogICAgZWxzZSBpZiAoSU5WX01BR0lDLnRlc3QobmFtZSkpICAgY2F0cy5tYWdpYy5wdXNoKGxhYmVsKTsKICAgIGVsc2UgICAgICAgICAgICAgICAgICAgICAgICAgICAgIGNhdHMuZXF1aXBtZW50LnB1c2gobGFiZWwpOyAvLyB0b3JjaGVzLCByYXRpb25zLCBiYWNrcGFjaywgZXRjLgogIH0pOwoKICAvLyBVcGRhdGUgYW1tbyBpbiBzdGF0dXMgcGFuZWwKICB1cGRhdGVBbW1vU3RhdHVzKGFtbW9JdGVtcyk7CgogIGNvbnN0IGNhdERlZnMgPSBbCiAgICBbJ3dlYXBvbnMnLCAnV0VBUE9OUyddLAogICAgWydhcm1vdXInLCAgJ0FSTU9VUiddLAogICAgWydtYWdpYycsICAgJ01BR0lDJ10sCiAgICBbJ2VxdWlwbWVudCcsJ0VRVUlQTUVOVCddLAogIF07CiAgY29uc3QgaGRyU3R5bGUgPSAnY29sb3I6dmFyKC0tZ29sZC1kaW0pO2ZvbnQtc2l6ZToxMXB4O2xldHRlci1zcGFjaW5nOjFweDt0ZXh0LXRyYW5zZm9ybTp1cHBlcmNhc2U7cGFkZGluZy10b3A6NXB4O2JvcmRlci10b3A6MXB4IHNvbGlkICMyYTI0MTA7bWFyZ2luLXRvcDoycHg7bGlzdC1zdHlsZTpub25lOyc7CiAgbGV0IGh0bWwgPSAnJzsKICBjYXREZWZzLmZvckVhY2goKFtjYXQsIGxhYmVsXSkgPT4gewogICAgaWYgKCFjYXRzW2NhdF0ubGVuZ3RoKSByZXR1cm47CiAgICBodG1sICs9IGA8bGkgc3R5bGU9IiR7aGRyU3R5bGV9Ij4ke2xhYmVsfTwvbGk+YDsKICAgIGNhdHNbY2F0XS5mb3JFYWNoKGkgPT4geyBodG1sICs9IGA8bGk+JHtpfTwvbGk+YDsgfSk7CiAgfSk7CiAgZWwuaW5uZXJIVE1MID0gaHRtbCB8fCAnPGxpIHN0eWxlPSJjb2xvcjp2YXIoLS1pbmstZGltKSI+RW1wdHk8L2xpPic7Cn0KCmZ1bmN0aW9uIGlzSW5EdW5nZW9uKCkgewogIC8vIENoZWNrIGlmIGN1cnJlbnQgbG9jYXRpb24gaXMgYSBkdW5nZW9uIGxldmVsIChkdW5nZW9uX2xldmVsID49IDEpCiAgaWYgKCFsb2FkZWRNb2R1bGVEYXRhIHx8ICFsb2FkZWRNb2R1bGVEYXRhLmxvY2F0aW9ucykgcmV0dXJuIGZhbHNlOwogIGNvbnN0IGxvYyA9IChsb2FkZWRNb2R1bGVEYXRhLmxvY2F0aW9ucyB8fCBbXSkuZmluZChsID0+IGwuaWQgPT09IHBjLmxvY3RhZyk7CiAgaWYgKGxvYykgcmV0dXJuIChsb2MuZHVuZ2Vvbl9sZXZlbCB8fCAwKSA+PSAxOwogIC8vIEZhbGxiYWNrOiBjaGVjayBsb2N0YWcgcHJlZml4IChEID0gZHVuZ2VvbiByb29tcyBpbiBOMSkKICBpZiAocGMubG9jdGFnICYmIC9eRFsuXWQvaS50ZXN0KHBjLmxvY3RhZykpIHJldHVybiB0cnVlOwogIHJldHVybiBmYWxzZTsKfQoKZnVuY3Rpb24gdXBkYXRlQW1tb1N0YXR1cyhhbW1vSXRlbXMpIHsKICBsZXQgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RhdHVzLWFtbW8nKTsKICBpZiAoIWFtbW9JdGVtcy5sZW5ndGgpIHsKICAgIGlmIChlbCkgZWwuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIHJldHVybjsKICB9CiAgaWYgKCFlbCkgewogICAgLy8gQ3JlYXRlIHRoZSBhbW1vIHJvdyBpZiBpdCBkb2Vzbid0IGV4aXN0CiAgICBjb25zdCBwYW5lbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhY3RpdmUtZWZmZWN0cycpOwogICAgaWYgKCFwYW5lbCkgcmV0dXJuOwogICAgZWwgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCdkaXYnKTsKICAgIGVsLmlkID0gJ3N0YXR1cy1hbW1vJzsKICAgIGVsLnN0eWxlLmNzc1RleHQgPSAnZm9udC1zaXplOjE0cHg7Y29sb3I6dmFyKC0tZGltKTtwYWRkaW5nOjJweCAwOyc7CiAgICBwYW5lbC5wYXJlbnROb2RlLmluc2VydEJlZm9yZShlbCwgcGFuZWwpOwogIH0KICBlbC5zdHlsZS5kaXNwbGF5ID0gJyc7CiAgZWwuaW5uZXJIVE1MID0gYW1tb0l0ZW1zLm1hcChhID0+CiAgICBgJHthLm5hbWV9OiA8c3BhbiBzdHlsZT0iY29sb3I6dmFyKC0taW5rKSI+JHthLnF0eX08L3NwYW4+YAogICkuam9pbignPGJyPicpOwp9CgpmdW5jdGlvbiB1cGRhdGVSZXNvdXJjZVBhbmVsKCkgewogIGNvbnN0IGxpZ2h0RWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVzLWxpZ2h0Jyk7CiAgY29uc3QgcmF0RWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVzLXJhdGlvbnMnKTsKICBjb25zdCB0dXJuRWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVzLXR1cm5zJyk7CiAgY29uc3QgY29tYmF0RWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVzLWNvbWJhdCcpOwogIGlmICghbGlnaHRFbCAmJiAhcmF0RWwgJiYgIXR1cm5FbCkgcmV0dXJuOyAvLyBvbGQgcmVzb3VyY2UgcGFuZWwgcmVtb3ZlZAoKICAvLyBMaWdodAogIGlmICghaXNDYXJyeWluZ0xpZ2h0KSB7CiAgICBsaWdodEVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwNjA2MCI+REFSS05FU1M8L3NwYW4+JzsKICB9IGVsc2UgaWYgKHRvcmNoVHVybnNMZWZ0ID4gMCAmJiB0b3JjaFR1cm5zTGVmdCA8PSAyKSB7CiAgICBsaWdodEVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwOTA0MCI+VG9yY2g6ICcgKyB0b3JjaFR1cm5zTGVmdCArICcgdHVybnM8L3NwYW4+JzsKICB9IGVsc2UgaWYgKHRvcmNoVHVybnNMZWZ0ID4gMCkgewogICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnVG9yY2g6ICcgKyB0b3JjaFR1cm5zTGVmdCArICcgdHVybnMnOwogIH0gZWxzZSBpZiAoaGFzTGFudGVybikgewogICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnTGFudGVybjogJyArIGxhbnRlcm5PaWxGbGFza3NMZWZ0ICsgJyBmbGFzayhzKSc7CiAgfSBlbHNlIHsKICAgIGxpZ2h0RWwuaW5uZXJIVE1MID0gJ05vIGxpZ2h0JzsKICB9CgogIC8vIFJhdGlvbnMKICBpZiAocmF0aW9uc0xlZnQgPT09IDApIHsKICAgIHJhdEVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwNjA2MCI+Tm8gcmF0aW9uczwvc3Bhbj4nOwogIH0gZWxzZSBpZiAocmF0aW9uc0xlZnQgPT09IDEpIHsKICAgIHJhdEVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwOTA0MCI+MSByYXRpb24gbGVmdDwvc3Bhbj4nOwogIH0gZWxzZSB7CiAgICByYXRFbC5pbm5lckhUTUwgPSAnUmF0aW9uczogJyArIHJhdGlvbnNMZWZ0OwogIH0KCiAgLy8gVHVybnMgLyB0aW1lCiAgY29uc3QgaG91cnMgPSBNYXRoLmZsb29yKGR1bmdlb25UdXJucyAvIDYpOwogIGNvbnN0IG1pbnMgPSAoZHVuZ2VvblR1cm5zICUgNikgKiAxMDsKICB0dXJuRWwudGV4dENvbnRlbnQgPSAnIFR1cm4gJyArIGR1bmdlb25UdXJucyArICcgKCcgKyBob3VycyArICdoICcgKyBtaW5zICsgJ20pJzsKCiAgLy8gQ29tYmF0CiAgaWYgKGluQ29tYmF0KSB7CiAgICBjb21iYXRFbC5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICAgIGNvbnN0IGFsaXZlID0gY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZpbHRlcihjID0+ICFjLmRlYWQgJiYgIWMuZmxlZCk7CiAgICBjb21iYXRFbC5pbm5lckhUTUwgPSAnUm91bmQgJyArIGNvbWJhdFN0YXRlLnJvdW5kICsgJyAtLSAnICsgYWxpdmUubGVuZ3RoICsgJyBjb21iYXRhbnRzJzsKICB9IGVsc2UgewogICAgY29tYmF0RWwuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICB9Cn0KCmZ1bmN0aW9uIHVwZGF0ZU1lbW9yeVBhbmVsKCkgewogIGlmICghdXNlT2xsYW1hKSByZXR1cm47CiAgY29uc3QgcGFuZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtb3J5LXBhbmVsJyk7CiAgaWYgKCFwYW5lbCkgcmV0dXJuOwogIGNvbnN0IGhhc01lbW9yeSA9IG1lbW9yeVN1bW1hcnkgfHwgcGlubmVkRmFjdHMubGVuZ3RoIHx8IE9iamVjdC5rZXlzKHdvcmxkU3RhdGUubnBjc19tZXQpLmxlbmd0aDsKICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gaGFzTWVtb3J5ID8gJ2Jsb2NrJyA6ICdub25lJzsKICBjb25zdCBfbXQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtLXR1cm4nKTsgaWYoX210KSBfbXQudGV4dENvbnRlbnQgPSAnVHVybiAnICsgdHVybkNvdW50OwogIGNvbnN0IHN1bUVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbS1zdW1tYXJ5Jyk7CiAgaWYgKCFzdW1FbCkgcmV0dXJuOwogIGlmIChtZW1vcnlTdW1tYXJ5KSB7CiAgICBzdW1FbC50ZXh0Q29udGVudCA9IG1lbW9yeVN1bW1hcnkuc3Vic3RyaW5nKDAsIDgwKSArIChtZW1vcnlTdW1tYXJ5Lmxlbmd0aCA+IDgwID8gJy4uLicgOiAnJyk7CiAgICBzdW1FbC50aXRsZSA9IG1lbW9yeVN1bW1hcnk7CiAgfSBlbHNlIHsKICAgIHN1bUVsLnRleHRDb250ZW50ID0gJyc7CiAgfQogIGNvbnN0IF9tZiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW0tZmFjdHMnKTsgaWYoX21mKSBfbWYudGV4dENvbnRlbnQgPQogICAgcGlubmVkRmFjdHMubGVuZ3RoID8gcGlubmVkRmFjdHMubGVuZ3RoICsgJyBmYWN0cyBwaW5uZWQnIDogJyc7CiAgY29uc3QgbnBjTmFtZXMgPSBPYmplY3Qua2V5cyh3b3JsZFN0YXRlLm5wY3NfbWV0KTsKICBjb25zdCBfbW4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtLW5wY3MnKTsgaWYoX21uKSBfbW4udGV4dENvbnRlbnQgPQogICAgbnBjTmFtZXMubGVuZ3RoID8gJ05QQ3M6ICcgKyBucGNOYW1lcy5zbGljZSgwLDUpLmpvaW4oJywgJykgOiAnJzsKfQoKZnVuY3Rpb24gcmVuZGVyUXVlc3RzKCkgewogIGNvbnN0IHFsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3F1ZXN0LWxpc3QnKTsKICBxbC5pbm5lckhUTUwgPSAocGMucXVlc3RzfHxbXSkubGVuZ3RoCiAgICA/IHBjLnF1ZXN0cy5tYXAocT0+YDxsaSBjbGFzcz0iJHtxLnN9Ij4ke3Eubn08L2xpPmApLmpvaW4oJycpCiAgICA6ICc8bGkgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O2NvbG9yOiM4YTdhNTgiPk5vbmUgeWV0PC9saT4nOwp9CgpmdW5jdGlvbiByZW5kZXJQYXJ0eVBhbmVsKCkgewogIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BhcnR5LXBhbmVsJyk7CiAgY29uc3QgY29udGFpbmVyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ290aGVyLXBjcycpOwogIGNvbnN0IG90aGVycyA9IE9iamVjdC5lbnRyaWVzKHBhcnR5UENzKS5maWx0ZXIoKFtuXSkgPT4gbiAhPT0gcGxheWVyTmFtZSk7CiAgaWYgKCFvdGhlcnMubGVuZ3RoKSB7IHBhbmVsLnN0eWxlLmRpc3BsYXk9J25vbmUnOyByZXR1cm47IH0KICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gJ2Jsb2NrJzsKICBjb250YWluZXIuaW5uZXJIVE1MID0gb3RoZXJzLm1hcCgoW3BuLHBdLGkpID0+IHsKICAgIGNvbnN0IGNvbCA9IGdldENvbG9yKHBuKTsKICAgIGNvbnN0IHBjdCA9IE1hdGgubWF4KDAsIHAuaHAvcC5tYXhocCoxMDApOwogICAgY29uc3QgaGNvbCA9IHBjdD41MD8nIzNhN2EzYSc6cGN0PjI1PycjOWE3MDIwJzonIzhiMjUyNSc7CiAgICByZXR1cm4gYDxkaXYgY2xhc3M9Im9wYyI+CiAgICAgIDxkaXYgY2xhc3M9Im9wYy1uYW1lIiBzdHlsZT0iY29sb3I6JHtjb2x9Ij4ke3AubmFtZX0gPHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWluay1kaW0pIj4ke3AucmFjZX0gJHtwLmNsc308L3NwYW4+PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9Im9wYy1ocCI+JHtwLmhwfS8ke3AubWF4aHB9IEhQICogQUMgJHtwLmFjfTwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJvcGMtaHBiYXIiPjxkaXYgY2xhc3M9Im9wYy1ocGZpbGwiIHN0eWxlPSJ3aWR0aDoke3BjdH0lO2JhY2tncm91bmQ6JHtoY29sfSI+PC9kaXY+PC9kaXY+CiAgICA8L2Rpdj5gOwogIH0pLmpvaW4oJycpOwp9CgpmdW5jdGlvbiBzZXRCdXR0b25zKGFycikgewogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdxdWljay1idG5zJykuaW5uZXJIVE1MID0gKGFycnx8W10pLm1hcChiID0+CiAgICBgPGJ1dHRvbiBjbGFzcz0icWIiIG9uY2xpY2s9InF1aWNrQWN0KCR7SlNPTi5zdHJpbmdpZnkoYil9KSI+JHtifTwvYnV0dG9uPmAKICApLmpvaW4oJycpOwp9CgpmdW5jdGlvbiBjbGFzc2lmeUVudHJ5KHR4dCkgewogIGlmICgvWy5dUm9sbDp8Wy5dU2F2ZXxkMjAgPXxpbml0aWF0aXZlL2kudGVzdCh0eHQpKSByZXR1cm4gJ3JvbGwnOwogIGlmICgvYXR0YWNrfGhpdHxkYW1hZ2V8d291bmR8Ymxvb2R8c2xheXxjb21iYXR8c3RyaWtlL2kudGVzdCh0eHQpKSByZXR1cm4gJ2NvbWJhdCc7CiAgaWYgKC9nb2xkfGdwfHRyZWFzdXJlfGxvb3R8Zm91bmR8Y29pbi9pLnRlc3QodHh0KSkgcmV0dXJuICdsb290JzsKICByZXR1cm4gJ2dtJzsKfQoKZnVuY3Rpb24gYWRkRW50cnkoaHRtbCwgdHlwZSwgYXV0aG9yKSB7IHJldHVybiBhZGRFbnRyeVJhdyhodG1sLCB0eXBlLCBhdXRob3IpOyB9CgpmdW5jdGlvbiBhZGRFbnRyeVJhdyhodG1sLCB0eXBlLCBhdXRob3IpIHsKICBjb25zdCBsb2cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbG9nJyk7CiAgY29uc3QgZCA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2RpdicpOwogIGlmICh0eXBlID09PSAnc3lzdGVtLXJvbGwnKSB7CiAgICBkLmNsYXNzTmFtZSA9ICdsb2ctc3lzdGVtLXJvbGwnOwogICAgZC5pbm5lckhUTUwgPSBodG1sOwogICAgbG9nLmFwcGVuZENoaWxkKGQpOwogICAgbG9nLnNjcm9sbFRvcCA9IGxvZy5zY3JvbGxIZWlnaHQ7CiAgICBsb2dFbnRyaWVzLnB1c2goeyBodG1sLCB0eXBlLCBhdXRob3IgfSk7CiAgICByZXR1cm4gZDsKICB9CiAgZC5jbGFzc05hbWUgPSAnZW50cnkgJyArIChhdXRob3IgJiYgYXV0aG9yICE9PSAnX19nbV9fJyA/ICdwbGF5ZXItbXNnJyA6IHR5cGUpOwogIGlmIChhdXRob3IgJiYgYXV0aG9yICE9PSAnX19nbV9fJyAmJiB0eXBlICE9PSAnc3lzdGVtJykgewogICAgY29uc3QgY29sID0gZ2V0Q29sb3IoYXV0aG9yKTsKICAgIGNvbnN0IGggPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCdkaXYnKTsKICAgIGguY2xhc3NOYW1lID0gJ2VudHJ5LWF1dGhvcic7CiAgICBoLnN0eWxlLmNvbG9yID0gY29sOwogICAgaC50ZXh0Q29udGVudCA9IGF1dGhvcjsKICAgIGQuYXBwZW5kQ2hpbGQoaCk7CiAgfQogIGNvbnN0IGMgPSBkb2N1bWVudC5jcmVhdGVFbGVtZW50KCdkaXYnKTsKICBjLmlubmVySFRNTCA9IGh0bWw7CiAgZC5hcHBlbmRDaGlsZChjKTsKICBsb2cuYXBwZW5kQ2hpbGQoZCk7CiAgbG9nLnNjcm9sbFRvcCA9IGxvZy5zY3JvbGxIZWlnaHQ7CiAgbG9nRW50cmllcy5wdXNoKHsgaHRtbCwgdHlwZSwgYXV0aG9yIH0pOwogIHJldHVybiBkOwp9CgpmdW5jdGlvbiBmbXQodHh0KSB7CiAgcmV0dXJuIHR4dAogICAgLnJlcGxhY2UoLyYvZywnJmFtcDsnKS5yZXBsYWNlKC88L2csJyZsdDsnKS5yZXBsYWNlKC8+L2csJyZndDsnKQogICAgLnJlcGxhY2UoL1suXShbXlsuXV0rKVsuXS9nLCc8c3BhbiBjbGFzcz0icm9sbC10YWciPlskMV08L3NwYW4+JykKICAgIC5yZXBsYWNlKC9bLl1bLl0oW14qXSspWy5dWy5dL2csJzxzdHJvbmc+JDE8L3N0cm9uZz4nKQogICAgLnJlcGxhY2UoL1suXShbXipdKylbLl0vZywnPGVtPiQxPC9lbT4nKTsKfQoKZnVuY3Rpb24gcHVzaE1lc3NhZ2UoaHRtbCwgdHlwZSwgYXV0aG9yKSB7CiAgaWYgKCFpc011bHRpcGxheWVyIHx8ICFyb29tQ29kZSkgcmV0dXJuOwogIHhockZldGNoKEJBU0VfVVJMICsgJy9wdXNoX21lc3NhZ2UnLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGU6cm9vbUNvZGUsIGh0bWwsIHR5cGUsIGF1dGhvciwgc2VxOiArK2xhc3RTZXF9KX0pOwp9CgpmdW5jdGlvbiBwYXJzZVN0YXRlKHJhdykgewogIHRyeSB7CiAgICAvLyBUcnkgPFNUQVRFPnsuLi59PC9TVEFURT4gZmlyc3QKICAgIGxldCBtID0gcmF3Lm1hdGNoKC88U1RBVEU+KFsuXVtbLl1zWy5dU10qP1suXSlbLl1zKjxbLl1TVEFURT4vKTsKICAgIGlmIChtKSByZXR1cm4gSlNPTi5wYXJzZShtWzFdKTsKICAgIC8vIEZhbGwgYmFjayB0byBbU1RBVEVdey4uLn0gKE9sbGFtYSBzb21ldGltZXMgdXNlcyBzcXVhcmUgYnJhY2tldHMpCiAgICBtID0gcmF3Lm1hdGNoKC9bLl1TVEFURVsuXShbLl1bWy5dc1suXVNdKj9bLl0pLyk7CiAgICBpZiAobSkgcmV0dXJuIEpTT04ucGFyc2UobVsxXSk7CiAgfSBjYXRjaChlKSB7fQogIHJldHVybiBudWxsOwp9CgpmdW5jdGlvbiBzdHJpcFN0YXRlKHJhdykgeyByZXR1cm4gcmF3LnJlcGxhY2UoLzxTVEFURT5bWy5dc1suXVNdKj88Wy5dU1RBVEU+L2csJycpLnJlcGxhY2UoL1suXVNUQVRFWy5dW1suXXNbLl1TXSo/KD89Wy5dblsuXW58JCkvZywnJykucmVwbGFjZSgvWy5dU1RBVEVbLl1bLl1bWy5dc1suXVNdKj9bLl1bLl1zKi9nLCcnKS50cmltKCk7IH0KCmZ1bmN0aW9uIGFwcGx5U3RhdGUoZ3MpIHsKICBpZiAoIWdzKSByZXR1cm47CiAgaWYgKGdzLmhwIT09dW5kZWZpbmVkKSBwYy5ocD1ncy5ocDsKICBpZiAoZ3MubWF4aHAhPT11bmRlZmluZWQpIHBjLm1heGhwPWdzLm1heGhwOwogIGlmIChncy5pbnYmJmdzLmludi5sZW5ndGgpIHBjLmludj1ncy5pbnY7CiAgaWYgKGdzLmdvbGQhPT11bmRlZmluZWQpIHBjLmdvbGQ9Z3MuZ29sZDsKICBpZiAoZ3MubG9jKSBwYy5sb2M9Z3MubG9jOwogIGlmIChncy5sb2N0YWchPT11bmRlZmluZWQpIHsKICAgIGNvbnN0IHdhc0luRHVuZ2VvbiA9IGlzSW5EdW5nZW9uKCk7CiAgICBwYy5sb2N0YWc9Z3MubG9jdGFnOwogICAgLy8gUmVzZXQgcmVzdCBjb3VudGVyIHdoZW4gbGVhdmluZyB0aGUgZHVuZ2VvbgogICAgaWYgKHdhc0luRHVuZ2VvbiAmJiAhaXNJbkR1bmdlb24oKSkgewogICAgICB0dXJuc1dpdGhvdXRSZXN0ID0gMDsKICAgICAgZmF0aWd1ZVBlbmFsdHkgPSAwOwogICAgfQogIH0KICBpZiAoZ3MucXVlc3RzKSBwYy5xdWVzdHM9Z3MucXVlc3RzOwogIGlmIChncy5idXR0b25zKSBzZXRCdXR0b25zKGdzLmJ1dHRvbnMpOwogIGlmIChncy5wYXJ0eSkgewogICAgT2JqZWN0LmVudHJpZXMoZ3MucGFydHkpLmZvckVhY2goKFtwbixwZF0pID0+IHsKICAgICAgaWYgKHBhcnR5UENzW3BuXSkgeyBwYXJ0eVBDc1twbl0uaHA9cGQuaHB8fHBhcnR5UENzW3BuXS5ocDsgcGFydHlQQ3NbcG5dLm1heGhwPXBkLm1heGhwfHxwYXJ0eVBDc1twbl0ubWF4aHA7IH0KICAgIH0pOwogICAgcmVuZGVyUGFydHlQYW5lbCgpOwogICAgaWYgKGlzTXVsdGlwbGF5ZXIgJiYgcm9vbUNvZGUpIHsKICAgICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3VwZGF0ZV9yb29tJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOnJvb21Db2RlLCBwYXJ0eVBDcywgZ2FtZVN0YXRlOmdzfSl9KTsKICAgIH0KICB9CiAgLy8gQXV0by1zYXZlIGNoYXJhY3RlciBwcm9ncmVzcyBhZnRlciBldmVyeSBleGNoYW5nZQogIGlmIChwYy5pZCkgewogICAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3NhdmVfY2hhcmFjdGVyJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHBjKX0pOwogIH0KICB1cGRhdGVIVUQoKTsKfQoKZnVuY3Rpb24gZXh0cmFjdEFuZFBpbkZhY3RzKHRleHQpIHsKICAvLyBQYXR0ZXJucyB0aGF0IHNpZ25hbCBhIG1lbW9yYWJsZSBmYWN0CiAgY29uc3QgcGF0dGVybnMgPSBbCiAgICAvLyBOUEMgbmFtZXMgYW5kIHJvbGVzCiAgICAvKFtBLVpdW2Etel0rKD86Wy5dc1tBLVpdW2Etel0rKT8pWy5dcysoPzppc3x3YXN8YXJlfHdlcmUpWy5dcysoPzp0aGV8YXxhbilbLl1zKyhbXi4hP117NSw0MH0pWy4hP10vZywKICAgIC8vIERlYXRoIG9mIG1vbnN0ZXJzL05QQ3MKICAgIC8oW0EtWl1bYS16XSsoPzpbLl1zW0EtWl1bYS16XSspPylbLl1zKyg/OmlzfGhhcyBiZWVufHdhcylbLl1zKyg/OmtpbGxlZHxzbGFpbnxkZWZlYXRlZHxkZWFkKS9nLAogICAgLy8gTG9jYXRpb25zIGRpc2NvdmVyZWQKICAgIC8oPzplbnRlcnxkaXNjb3ZlcnxmaW5kfHJldmVhbHxvcGVuKVsuXXMrKD86dGhlfGF8YW4pWy5dcysoW14uIT9dezUsNDB9KVsuIT9dL2dpLAogICAgLy8gSXRlbXMgb2J0YWluZWQKICAgIC8oPzpwaWNrIHVwfHRha2V8ZmluZHxyZWNlaXZlfG9idGFpbnxwb2NrZXQpWy5dcysoPzp0aGV8YXxhbilbLl1zKyhbXi4hP117NSw0MH0pWy4hP10vZ2ksCiAgICAvLyBEb29ycy9wYXNzYWdlcyBvcGVuZWQKICAgIC8oPzpzZWNyZXQgZG9vcnxoaWRkZW4gcGFzc2FnZXxjb25jZWFsZWQgZW50cmFuY2UpW14uIT9dKig/Om9wZW58cmV2ZWFsfGZvdW5kKVteLiE/XSovZ2ksCiAgXTsKCiAgY29uc3QgbmV3RmFjdHMgPSBbXTsKICBwYXR0ZXJucy5mb3JFYWNoKHBhdHRlcm4gPT4gewogICAgbGV0IG1hdGNoOwogICAgY29uc3QgcmUgPSBuZXcgUmVnRXhwKHBhdHRlcm4uc291cmNlLCBwYXR0ZXJuLmZsYWdzKTsKICAgIHdoaWxlICgobWF0Y2ggPSByZS5leGVjKHRleHQpKSAhPT0gbnVsbCkgewogICAgICBjb25zdCBmYWN0ID0gbWF0Y2hbMF0udHJpbSgpOwogICAgICBpZiAoZmFjdC5sZW5ndGggPiAxNSAmJiBmYWN0Lmxlbmd0aCA8IDEyMCkgewogICAgICAgIC8vIEF2b2lkIGR1cGxpY2F0ZXMKICAgICAgICBjb25zdCBzaW1wbGlmaWVkID0gZmFjdC50b0xvd2VyQ2FzZSgpLnJlcGxhY2UoL1teYS16MC05IF0vZywgJycpOwogICAgICAgIGNvbnN0IGlzRHVwID0gcGlubmVkRmFjdHMuc29tZShmID0+CiAgICAgICAgICBmLnRvTG93ZXJDYXNlKCkucmVwbGFjZSgvW15hLXowLTkgXS9nLCAnJykuaW5jbHVkZXMoc2ltcGxpZmllZC5zdWJzdHJpbmcoMCwgMjApKQogICAgICAgICk7CiAgICAgICAgaWYgKCFpc0R1cCkgbmV3RmFjdHMucHVzaChmYWN0KTsKICAgICAgfQogICAgfQogIH0pOwoKICAvLyBBZGQgbmV3IGZhY3RzLCBjYXAgYXQgTUFYX1BJTk5FRF9GQUNUUwogIHBpbm5lZEZhY3RzLnB1c2goLi4ubmV3RmFjdHMpOwogIGlmIChwaW5uZWRGYWN0cy5sZW5ndGggPiBNQVhfUElOTkVEX0ZBQ1RTKSB7CiAgICBwaW5uZWRGYWN0cyA9IHBpbm5lZEZhY3RzLnNsaWNlKC1NQVhfUElOTkVEX0ZBQ1RTKTsKICB9Cn0KCmZ1bmN0aW9uIHVwZGF0ZVdvcmxkU3RhdGUocmF3UmVzcG9uc2UsIGdhbWVTdGF0ZSkgewogIC8vIFF1ZXN0cwogIGlmIChnYW1lU3RhdGUgJiYgZ2FtZVN0YXRlLnF1ZXN0cykgewogICAgd29ybGRTdGF0ZS5xdWVzdHNfYWN0aXZlID0gZ2FtZVN0YXRlLnF1ZXN0cy5maWx0ZXIocT0+cS5zPT09J2FjdGl2ZScpLm1hcChxPT5xLm4pOwogIH0KCiAgLy8gRml4IDI6IFRyYWNrIGxvY2F0aW9ucyArIGNhY2hlIGF0bW9zcGhlcmUKICBpZiAoZ2FtZVN0YXRlICYmIGdhbWVTdGF0ZS5sb2MgJiYgZ2FtZVN0YXRlLmxvYyAhPT0gJy4uLicpIHsKICAgIGNvbnN0IGxvYyA9IGdhbWVTdGF0ZS5sb2M7CiAgICBpZiAoIXdvcmxkU3RhdGUubG9jYXRpb25zX3Zpc2l0ZWRbbG9jXSkgewogICAgICB3b3JsZFN0YXRlLmxvY2F0aW9uc192aXNpdGVkW2xvY10gPSB7IGZpcnN0X3Zpc2l0ZWQ6IHR1cm5Db3VudCwgdGFnOiBnYW1lU3RhdGUubG9jdGFnfHwnJyB9OwogICAgfQogICAgaWYgKCFsb2NhdGlvbkF0bW9zcGhlcmVbbG9jXSkgewogICAgICBjb25zdCBmaXJzdFNlbnRlbmNlID0gcmF3UmVzcG9uc2Uuc3BsaXQoL1suIT9dLylbMF0udHJpbSgpOwogICAgICBsb2NhdGlvbkF0bW9zcGhlcmVbbG9jXSA9IGZpcnN0U2VudGVuY2Uuc3Vic3RyaW5nKDAsMTIwKTsKICAgIH0KICAgIGN1cnJlbnRBdG1vc3BoZXJlID0gbG9jYXRpb25BdG1vc3BoZXJlW2xvY10gfHwgJyc7CiAgfQoKICAvLyBGaXggMTogQnVpbGQgTlBDIHByb2ZpbGVzIHdpdGggc2FtcGxlIHF1b3RlcyBmb3Igdm9pY2UgY29uc2lzdGVuY3kKICBjb25zdCB0ZXh0Rm9yTnBjID0gcmF3UmVzcG9uc2U7CiAgY29uc3QgbnBjTmFtZXMgPSBPYmplY3Qua2V5cyhucGNQcm9maWxlcykuY29uY2F0KE9iamVjdC5rZXlzKHdvcmxkU3RhdGUubnBjc19tZXQpKTsKICAvLyBEZXRlY3QgbmV3IE5QQ3Mgc3BlYWtpbmcKICBjb25zdCBzcGVha1dvcmRzID0gWydzYXlzJywndGVsbHMnLCd3aGlzcGVycycsJ3Nob3V0cycsJ3JlcGxpZXMnLCdhc2tzJywnZ3Jvd2xzJywnbXV0dGVycycsJ3NuZWVycycsJ2xhdWdocycsJ3NpZ2hzJywnYmFya3MnLCdoaXNzZXMnLCdkZWNsYXJlcycsJ2Fubm91bmNlcyddOwogIHNwZWFrV29yZHMuZm9yRWFjaCh2ZXJiID0+IHsKICAgIGNvbnN0IHBhdCA9IG5ldyBSZWdFeHAoJyhbQS1aXVthLXpdezIsMjB9KD86Wy5dc1tBLVpdW2Etel17MiwyMH0pPykoPzpbXixdezAsMjB9KScgKyB2ZXJiICsgJ1teLF0qWyxdPyhbXixdezEwLDEwMH0pJywgJ2dpJyk7CiAgICBsZXQgbTsKICAgIHdoaWxlICgobSA9IHBhdC5leGVjKHRleHRGb3JOcGMpKSAhPT0gbnVsbCkgewogICAgICBjb25zdCBuYW1lID0gbVsxXS50cmltKCk7CiAgICAgIGNvbnN0IHF1b3RlID0gbVsyXS50cmltKCk7CiAgICAgIGlmIChbJ1RoZScsJ1lvdScsJ1lvdXInLCdIZScsJ1NoZScsJ1RoZXknLCdJdCcsJ1RoaXMnLCdUaGF0J10uaW5jbHVkZXMobmFtZSkpIGNvbnRpbnVlOwogICAgICBpZiAoIW5wY1Byb2ZpbGVzW25hbWVdKSBucGNQcm9maWxlc1tuYW1lXSA9IHsgZmlyc3RfbWV0OiB0dXJuQ291bnQsIHF1b3RlczogW10sIGF0dGl0dWRlOiAndW5rbm93bicgfTsKICAgICAgaWYgKG5wY1Byb2ZpbGVzW25hbWVdLnF1b3Rlcy5sZW5ndGggPCAzKSBucGNQcm9maWxlc1tuYW1lXS5xdW90ZXMucHVzaChxdW90ZSk7CiAgICAgIGlmICghd29ybGRTdGF0ZS5ucGNzX21ldFtuYW1lXSkgd29ybGRTdGF0ZS5ucGNzX21ldFtuYW1lXSA9IHsgYXR0aXR1ZGU6ICd1bmtub3duJywgZmlyc3RfbWV0OiB0dXJuQ291bnQgfTsKICAgIH0KICB9KTsKCiAgLy8gTlBDIGF0dGl0dWRlIGRldGVjdGlvbgogIGNvbnN0IGF0dGl0dWRlUGF0ID0gLyhbQS1aXVthLXpdezIsMjB9KD86Wy5dc1tBLVpdW2Etel17MiwyMH0pPylbLl1zKyg/OnNlZW1zfGFwcGVhcnN8bG9va3N8aXMpWy5dcysoZnJpZW5kbHl8aG9zdGlsZXxuZXJ2b3VzfGFmcmFpZHxzdXNwaWNpb3VzfHBsZWFzZWR8YW5ncnl8ZnJpZ2h0ZW5lZHx3YXJ5fGdyYXRlZnVsKS9naTsKICBsZXQgbTI7CiAgd2hpbGUgKChtMiA9IGF0dGl0dWRlUGF0LmV4ZWMocmF3UmVzcG9uc2UpKSAhPT0gbnVsbCkgewogICAgY29uc3QgbmFtZSA9IG0yWzFdOwogICAgaWYgKFsnVGhlJywnWW91JywnWW91cicsJ0hlJywnU2hlJywnVGhleSddLmluY2x1ZGVzKG5hbWUpKSBjb250aW51ZTsKICAgIGlmICghd29ybGRTdGF0ZS5ucGNzX21ldFtuYW1lXSkgd29ybGRTdGF0ZS5ucGNzX21ldFtuYW1lXSA9IHsgYXR0aXR1ZGU6IG0yWzJdLnRvTG93ZXJDYXNlKCksIGZpcnN0X21ldDogdHVybkNvdW50IH07CiAgICBlbHNlIHdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0uYXR0aXR1ZGUgPSBtMlsyXS50b0xvd2VyQ2FzZSgpOwogICAgaWYgKG5wY1Byb2ZpbGVzW25hbWVdKSBucGNQcm9maWxlc1tuYW1lXS5hdHRpdHVkZSA9IG0yWzJdLnRvTG93ZXJDYXNlKCk7CiAgfQoKICAvLyBNb25zdGVyIGtpbGxzCiAgY29uc3Qga2lsbFBhdCA9IC8oW0EtWl1bYS16XXsyLDI1fSg/OlsuXXNbQS1aXVthLXpdezIsMjV9KT8pW14uXXswLDMwfSg/OmlzIGtpbGxlZHxpcyBzbGFpbnxkaWVzfGZhbGxzIGRlYWR8Y3J1bXBsZXN8Y29sbGFwc2VzIGRlYWQpL2dpOwogIGxldCBtMzsKICB3aGlsZSAoKG0zID0ga2lsbFBhdC5leGVjKHJhd1Jlc3BvbnNlKSkgIT09IG51bGwpIHsKICAgIGNvbnN0IG5hbWUgPSBtM1sxXTsKICAgIGlmICghd29ybGRTdGF0ZS5tb25zdGVyc19raWxsZWQuaW5jbHVkZXMobmFtZSkpIHdvcmxkU3RhdGUubW9uc3RlcnNfa2lsbGVkLnB1c2gobmFtZSk7CiAgfQoKICAvLyBGaXggNTogUGVybWFuZW50IHdvcmxkLWNoYW5naW5nIGV2ZW50cwogIGNvbnN0IGNoYW5nZVBhdCA9IC8oPzpidXJuKD86ZWR8c3xpbmcpfGRlc3Ryb3koPzplZHxzKXxjb2xsYXBzZSg/OmR8cyl8YWxhcm0oPzplZHxzKXxhbGVydCg/OmVkfHMpfGdhdGUgKD86b3BlbnN8Y2xvc2VzfGlzIG9wZW4pfGZpcmUgKD86c3ByZWFkc3xidXJucykpW14uIT9dezAsODB9Wy4hP10vZ2k7CiAgbGV0IG00OwogIHdoaWxlICgobTQgPSBjaGFuZ2VQYXQuZXhlYyhyYXdSZXNwb25zZSkpICE9PSBudWxsKSB7CiAgICBjb25zdCBldmVudCA9IG00WzBdLnRyaW0oKS5zdWJzdHJpbmcoMCwxMDApOwogICAgaWYgKCF3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMuc29tZShlID0+IGUuaW5jbHVkZXMoZXZlbnQuc3Vic3RyaW5nKDAsMjApKSkpIHsKICAgICAgd29ybGRTdGF0ZS53b3JsZF9jaGFuZ2VzLnB1c2goJ1R1cm4gJyArIHR1cm5Db3VudCArICc6ICcgKyBldmVudCk7CiAgICB9CiAgfQogIGlmICh3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMubGVuZ3RoID4gMTUpIHdvcmxkU3RhdGUud29ybGRfY2hhbmdlcyA9IHdvcmxkU3RhdGUud29ybGRfY2hhbmdlcy5zbGljZSgtMTUpOwoKICAvLyBGaXggNjogVXBkYXRlIHNlc3Npb24gdG9uZQogIGNvbnN0IGN3ID0gKHJhd1Jlc3BvbnNlLm1hdGNoKC9cYihhdHRhY2t8Y29tYmF0fGZpZ2h0fHN0cmlrZXx3b3VuZHxibG9vZHx3ZWFwb258c2xheXxiYXR0bGUpXGIvZ2kpfHxbXSkubGVuZ3RoOwogIGNvbnN0IHR3ID0gKHJhd1Jlc3BvbnNlLm1hdGNoKC9cYihkYW5nZXJ8dHJhcHxwb2lzb258ZmxlZXxzY3JlYW18ZGVhdGh8ZGllc3xraWxsZWR8dGVycm9yKVxiL2dpKXx8W10pLmxlbmd0aDsKICBjb25zdCBzdyA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoc2F5c3xhc2tzfHRlbGxzfHNwZWFrc3xuZWdvdGlhdGV8cGVyc3VhZGV8Y2hhcm18Y29udmVyc2F0aW9uKVxiL2dpKXx8W10pLmxlbmd0aDsKICBjb25zdCBldyA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoc2VhcmNofGV4YW1pbmV8ZXhwbG9yZXxkaXNjb3ZlcnxmaW5kfG9wZW58cGFzc2FnZXxkb29yfGNvcnJpZG9yKVxiL2dpKXx8W10pLmxlbmd0aDsKICBjb25zdCBtYXggPSBNYXRoLm1heChjdywgdHcsIHN3LCBldyk7CiAgaWYgKG1heCA+IDIpIHsKICAgIGlmIChjdyA9PT0gbWF4KSBzZXNzaW9uVG9uZSA9ICdjb21iYXQtaGVhdnknOwogICAgZWxzZSBpZiAodHcgPT09IG1heCkgc2Vzc2lvblRvbmUgPSAndGVuc2UnOwogICAgZWxzZSBpZiAoc3cgPT09IG1heCkgc2Vzc2lvblRvbmUgPSAnc29jaWFsJzsKICAgIGVsc2Ugc2Vzc2lvblRvbmUgPSAnZXhwbG9yYXRvcnknOwogIH0KCiAgLy8gUm90YXRlIGJhbm5lZCBwaHJhc2VzIGV2ZXJ5IDQgdHVybnMKICBpZiAodHVybkNvdW50ICUgNCA9PT0gMCkgcm90YXRlQmFubmVkUGhyYXNlcygpOwp9CgpmdW5jdGlvbiBidWlsZFdvcmxkU3RhdGVCbG9jaygpIHsKICBjb25zdCBsaW5lcyA9IFtdOwoKICAvLyBGaXggMTogTlBDIHByb2ZpbGVzIHdpdGggdm9pY2Ugc2FtcGxlcyBmb3IgY29uc2lzdGVuY3kKICBjb25zdCBucGNFbnRyaWVzID0gT2JqZWN0LmVudHJpZXMobnBjUHJvZmlsZXMpOwogIGlmIChucGNFbnRyaWVzLmxlbmd0aCA+IDApIHsKICAgIGxpbmVzLnB1c2goJ0tOT1dOIE5QQ3MgLS0gbWFpbnRhaW4gdGhlaXIgdm9pY2UgYW5kIGF0dGl0dWRlIGNvbnNpc3RlbnRseTonKTsKICAgIG5wY0VudHJpZXMuc2xpY2UoLTgpLmZvckVhY2goKFtuYW1lLCBkYXRhXSkgPT4gewogICAgICBsZXQgZW50cnkgPSAnICAnICsgbmFtZSArICc6IGF0dGl0dWRlPScgKyBkYXRhLmF0dGl0dWRlOwogICAgICBpZiAoZGF0YS5xdW90ZXMgJiYgZGF0YS5xdW90ZXMubGVuZ3RoID4gMCkgZW50cnkgKz0gJyB8IFNhbXBsZSBzcGVlY2g6ICInICsgZGF0YS5xdW90ZXNbMF0gKyAnIic7CiAgICAgIGxpbmVzLnB1c2goZW50cnkpOwogICAgfSk7CiAgfSBlbHNlIGlmIChPYmplY3Qua2V5cyh3b3JsZFN0YXRlLm5wY3NfbWV0KS5sZW5ndGggPiAwKSB7CiAgICBsaW5lcy5wdXNoKCdOUENzIGVuY291bnRlcmVkOiAnICsgT2JqZWN0LmVudHJpZXMod29ybGRTdGF0ZS5ucGNzX21ldCkubWFwKChbbixkXSk9Pm4rJyAoJytkLmF0dGl0dWRlKycpJykuam9pbignLCAnKSk7CiAgfQoKICAvLyBGaXggMjogQ3VycmVudCBsb2NhdGlvbiBhdG1vc3BoZXJlCiAgaWYgKGN1cnJlbnRBdG1vc3BoZXJlKSBsaW5lcy5wdXNoKCdDdXJyZW50IGF0bW9zcGhlcmU6ICcgKyBjdXJyZW50QXRtb3NwaGVyZSk7CgogIC8vIEZpeCA2OiBTZXNzaW9uIHRvbmUgZ3VpZGFuY2UKICBjb25zdCB0b25lcyA9IHsKICAgICdjb21iYXQtaGVhdnknOiAnQ29tYmF0LWhlYXZ5IC0tIGtlZXAgdGVuc2lvbiBoaWdoLCB3b3VuZHMgdml2aWQsIGRhbmdlciByZWFsJywKICAgICd0ZW5zZSc6ICAgICAgICAnVGVuc2UgLS0gc2hvcnQgc2VudGVuY2VzLCBidWlsZCBkcmVhZCwgZW1waGFzaXNlIHVuY2VydGFpbnR5JywKICAgICdzb2NpYWwnOiAgICAgICAnU29jaWFsIC0tIGxldCBkaWFsb2d1ZSBicmVhdGhlLCBzaG93IHBlcnNvbmFsaXR5IGFuZCBzdWJ0ZXh0JywKICAgICdleHBsb3JhdG9yeSc6ICAnRXhwbG9yYXRvcnkgLS0gcmV3YXJkIGN1cmlvc2l0eSwgZGVzY3JpYmUgcmljaGx5LCBoaW50IGF0IHNlY3JldHMnLAogIH07CiAgaWYgKHRvbmVzW3Nlc3Npb25Ub25lXSkgbGluZXMucHVzaCgnU2Vzc2lvbiB0b25lOiAnICsgdG9uZXNbc2Vzc2lvblRvbmVdKTsKCiAgLy8gRml4IDU6IFBlcm1hbmVudCB3b3JsZCBjaGFuZ2VzCiAgaWYgKHdvcmxkU3RhdGUud29ybGRfY2hhbmdlcy5sZW5ndGggPiAwKSB7CiAgICBsaW5lcy5wdXNoKCdXb3JsZCBjaGFuZ2VzIChyZWZsZWN0IGluIG5hcnJhdGlvbik6Jyk7CiAgICB3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMuc2xpY2UoLTUpLmZvckVhY2goYyA9PiBsaW5lcy5wdXNoKCcgICcgKyBjKSk7CiAgfQoKICBpZiAod29ybGRTdGF0ZS5tb25zdGVyc19raWxsZWQubGVuZ3RoID4gMCkgbGluZXMucHVzaCgnRGVmZWF0ZWQ6ICcgKyB3b3JsZFN0YXRlLm1vbnN0ZXJzX2tpbGxlZC5zbGljZSgtOCkuam9pbignLCAnKSk7CiAgY29uc3QgbG9jcyA9IE9iamVjdC5rZXlzKHdvcmxkU3RhdGUubG9jYXRpb25zX3Zpc2l0ZWQpOwogIGlmIChsb2NzLmxlbmd0aCA+IDApIGxpbmVzLnB1c2goJ0V4cGxvcmVkOiAnICsgbG9jcy5zbGljZSgtNikuam9pbignLCAnKSk7CiAgaWYgKHdvcmxkU3RhdGUucXVlc3RzX2FjdGl2ZS5sZW5ndGggPiAwKSBsaW5lcy5wdXNoKCdBY3RpdmUgcXVlc3RzOiAnICsgd29ybGRTdGF0ZS5xdWVzdHNfYWN0aXZlLmpvaW4oJywgJykpOwoKICByZXR1cm4gbGluZXMubGVuZ3RoID4gMCA/IGxpbmVzLmpvaW4oJ1suXW4nKSA6IG51bGw7Cn0KCmZ1bmN0aW9uIGJ1aWxkUGlubmVkRmFjdHNCbG9jaygpIHsKICBpZiAoIXBpbm5lZEZhY3RzLmxlbmd0aCkgcmV0dXJuIG51bGw7CiAgcmV0dXJuIHBpbm5lZEZhY3RzLnNsaWNlKC0xNSkuam9pbignWy5dbicpOwp9Cgphc3luYyBmdW5jdGlvbiBnZW5lcmF0ZVN1bW1hcnkoKSB7CiAgaWYgKGhpc3RvcnkubGVuZ3RoIDwgNCkgcmV0dXJuOyAvLyBub3QgZW5vdWdoIHRvIHN1bW1hcmlzZSB5ZXQKCiAgY29uc29sZS5sb2coJ1tNZW1vcnldIEdlbmVyYXRpbmcgcm9sbGluZyBzdW1tYXJ5Li4uJyk7CiAgY29uc3Qgc3VtbWFyeVByb21wdCA9IGBZb3UgYXJlIHN1bW1hcmlzaW5nIGEgRCZEIGFkdmVudHVyZSBzZXNzaW9uIGZvciBtZW1vcnkgcHVycG9zZXMuCgpQcmV2aW91cyBzdW1tYXJ5IChpZiBhbnkpOgoke21lbW9yeVN1bW1hcnkgfHwgJ05vbmUgLS0gdGhpcyBpcyB0aGUgZmlyc3Qgc3VtbWFyeS4nfQoKUmVjZW50IGV2ZW50cyB0byBpbmNvcnBvcmF0ZToKJHtoaXN0b3J5LnNsaWNlKC1NYXRoLm1pbihoaXN0b3J5Lmxlbmd0aCwgMTQpKS5tYXAobSA9PgogIG0ucm9sZSA9PT0gJ3VzZXInID8gJ1BMQVlFUjogJyArIG0uY29udGVudC5zdWJzdHJpbmcoMCwgMjAwKQogICAgICAgICAgICAgICAgICAgIDogJ0dNOiAnICsgc3RyaXBTdGF0ZShtLmNvbnRlbnQpLnN1YnN0cmluZygwLCA0MDApCikuam9pbignWy5dbicpfQoKV3JpdGUgYSBjb25jaXNlIGJ1dCBjb21wbGV0ZSBzdW1tYXJ5ICgxNTAtMjAwIHdvcmRzKSBjb3ZlcmluZzoKMS4gV2hhdCBoYXMgaGFwcGVuZWQgaW4gdGhlIGFkdmVudHVyZSBzbyBmYXIKMi4gV2hlcmUgdGhlIHBhcnR5IGN1cnJlbnRseSBpcwozLiBLZXkgTlBDcyB0aGV5IGhhdmUgbWV0IGFuZCB0aGVpciByZWxhdGlvbnNoaXAKNC4gSW1wb3J0YW50IGl0ZW1zIGZvdW5kIG9yIGxvc3QKNS4gQ3VycmVudCBnb2FscyBhbmQgdGhyZWF0cwo2LiBBbnkgZXN0YWJsaXNoZWQgZmFjdHMgdGhhdCBtdXN0IG5vdCBiZSBmb3Jnb3R0ZW4KCldyaXRlIGluIHBhc3QgdGVuc2UuIEJlIHNwZWNpZmljIHdpdGggbmFtZXMsIHBsYWNlcywgYW5kIGZhY3RzLiBEbyBub3QgaW52ZW50IGFueXRoaW5nIG5vdCBwcmVzZW50IGFib3ZlLmA7CgogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FpJywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgICAgYXBpX2tleTogYXBpS2V5LAogICAgICAgIHN5c3RlbTogJ1lvdSBhcmUgYSBwcmVjaXNlIHN1bW1hcmlzZXIuIFN1bW1hcmlzZSBhY2N1cmF0ZWx5IGFuZCBjb25jaXNlbHkuIE5ldmVyIGludmVudCBmYWN0cy4nLAogICAgICAgIG1lc3NhZ2VzOiBbe3JvbGU6ICd1c2VyJywgY29udGVudDogc3VtbWFyeVByb21wdH1dCiAgICAgIH0pCiAgICB9KTsKICAgIGlmICghcmVzcC5vaykgcmV0dXJuOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgaWYgKGRhdGEuY29udGVudCAmJiAhZGF0YS5lcnJvcikgewogICAgICBtZW1vcnlTdW1tYXJ5ID0gc3RyaXBTdGF0ZShkYXRhLmNvbnRlbnQpLnRyaW0oKTsKICAgICAgY29uc29sZS5sb2coJ1tNZW1vcnldIFN1bW1hcnkgZ2VuZXJhdGVkOicsIG1lbW9yeVN1bW1hcnkubGVuZ3RoLCAnY2hhcnMnKTsKCiAgICAgIC8vIEFmdGVyIHN1bW1hcmlzaW5nLCB0cmltIGhpc3RvcnkgdG8gbGFzdCBNQVhfSElTVE9SWV9CRUZPUkVfU1VNTUFSWSBtZXNzYWdlcwogICAgICAvLyBidXQga2VlcCB0aGUgZmlyc3QgZXhjaGFuZ2UgKG9wZW5pbmcgc2NlbmUpIGZvciBjb250ZXh0CiAgICAgIGlmIChoaXN0b3J5Lmxlbmd0aCA+IE1BWF9ISVNUT1JZX0JFRk9SRV9TVU1NQVJZICsgMikgewogICAgICAgIGNvbnN0IGZpcnN0VHdvID0gaGlzdG9yeS5zbGljZSgwLCAyKTsKICAgICAgICBjb25zdCByZWNlbnQgPSBoaXN0b3J5LnNsaWNlKC1NQVhfSElTVE9SWV9CRUZPUkVfU1VNTUFSWSk7CiAgICAgICAgaGlzdG9yeSA9IFsuLi5maXJzdFR3bywgLi4ucmVjZW50XTsKICAgICAgICBjb25zb2xlLmxvZygnW01lbW9yeV0gSGlzdG9yeSB0cmltbWVkIHRvJywgaGlzdG9yeS5sZW5ndGgsICdtZXNzYWdlcycpOwogICAgICB9CiAgICB9CiAgfSBjYXRjaChlKSB7CiAgICBjb25zb2xlLndhcm4oJ1tNZW1vcnldIFN1bW1hcnkgZmFpbGVkOicsIGUubWVzc2FnZSk7CiAgfQp9CgpmdW5jdGlvbiBidWlsZE1lbW9yeUNvbnRleHQoKSB7CiAgY29uc3QgcGFydHMgPSBbXTsKCiAgLy8gR00gQnJpZWZpbmcgYWx3YXlzIGZpcnN0IC0tIGhpZ2hlc3QgcHJpb3JpdHkgY29udGV4dAogIGlmIChnbUJyaWVmaW5nKSB7CiAgICBwYXJ0cy5wdXNoKGdtQnJpZWZpbmcpOwogIH0KCiAgaWYgKG1lbW9yeVN1bW1hcnkpIHsKICAgIHBhcnRzLnB1c2goJz09PSBTVE9SWSBTTyBGQVIgPT09Wy5dbicgKyBtZW1vcnlTdW1tYXJ5KTsKICB9CgogIGNvbnN0IHdvcmxkQmxvY2sgPSBidWlsZFdvcmxkU3RhdGVCbG9jaygpOwogIGlmICh3b3JsZEJsb2NrKSB7CiAgICBwYXJ0cy5wdXNoKCc9PT0gRVNUQUJMSVNIRUQgV09STEQgU1RBVEUgPT09Wy5dbicgKyB3b3JsZEJsb2NrKTsKICB9CgogIGNvbnN0IGZhY3RzQmxvY2sgPSBidWlsZFBpbm5lZEZhY3RzQmxvY2soKTsKICBpZiAoZmFjdHNCbG9jaykgewogICAgcGFydHMucHVzaCgnPT09IFBJTk5FRCBGQUNUUyAoZG8gbm90IGNvbnRyYWRpY3QgdGhlc2UpID09PVsuXW4nICsgZmFjdHNCbG9jayk7CiAgfQoKICByZXR1cm4gcGFydHMubGVuZ3RoID4gMCA/ICdbLl1uWy5dbicgKyBwYXJ0cy5qb2luKCdbLl1uWy5dbicpIDogJyc7Cn0KCmZ1bmN0aW9uIHJlc2V0TWVtb3J5KCkgewogIG1lbW9yeVN1bW1hcnkgPSAnJzsKICB3b3JsZFN0YXRlID0gewogICAgbnBjc19tZXQ6IHt9LCBsb2NhdGlvbnNfdmlzaXRlZDoge30sIGl0ZW1zX2ZvdW5kOiBbXSwKICAgIHBsb3RfcG9pbnRzOiBbXSwgZG9vcnNfb3BlbmVkOiBbXSwgdHJhcHNfc3BydW5nOiBbXSwKICAgIG1vbnN0ZXJzX2tpbGxlZDogW10sIHF1ZXN0c19hY3RpdmU6IFtdLCB3b3JsZF9jaGFuZ2VzOiBbXSwKICB9OwogIG5wY1Byb2ZpbGVzID0ge307CiAgbG9jYXRpb25BdG1vc3BoZXJlID0ge307CiAgY3VycmVudEF0bW9zcGhlcmUgPSAnJzsKICBzZXNzaW9uVG9uZSA9ICdleHBsb3JhdG9yeSc7CiAgcGlubmVkRmFjdHMgPSBbXTsKICB0dXJuQ291bnQgPSAwOwogIGdtQnJpZWZpbmcgPSAnJzsKICBucGNLbm93bGVkZ2VNYXAgPSB7fTsKICByb3RhdGVCYW5uZWRQaHJhc2VzKCk7CiAgLy8gUmVzZXQgYWxsIG5ldyBzeXN0ZW1zCiAgcGFjaW5nSGlzdG9yeSA9IFtdOyBjdXJyZW50UGFjaW5nUGhhc2UgPSAnb3BlbmluZyc7CiAgdHVybnNTaW5jZUxhc3RDb21iYXQgPSAwOyB0dXJuc1NpbmNlTGFzdFJlc3QgPSAwOwogIGNvbnNlcXVlbmNlcyA9IFtdOyBwZW5kaW5nQ29uc2VxdWVuY2VzID0gW107CiAgaW5Db21iYXQgPSBmYWxzZTsKICBjb21iYXRTdGF0ZSA9IHsgcm91bmQ6MCwgaW5pdGlhdGl2ZU9yZGVyOltdLCBhY3RpdmVJbmRleDowLCBwbGF5ZXJBY3Rpb246JycsIGxhc3RSb3VuZFN1bW1hcnk6JycgfTsKICBkdW5nZW9uVHVybnMgPSAwOyB0b3JjaFR1cm5zTGVmdCA9IDA7IGhhc0xhbnRlcm4gPSBmYWxzZTsKICBsYW50ZXJuT2lsRmxhc2tzTGVmdCA9IDA7IHJhdGlvbnNMZWZ0ID0gMDsgcmVzdERlYnQgPSAwOyBpc0NhcnJ5aW5nTGlnaHQgPSB0cnVlOwogIHdhbmRlcmluZ01vbnN0ZXJUdXJuQ291bnRlciA9IDA7IHdhbmRlcmluZ01vbnN0ZXJDaGVja0R1ZSA9IGZhbHNlOwp9Cgphc3luYyBmdW5jdGlvbiBzZXJ2ZXJSb2xsKHR5cGUsIHBhcmFtcz17fSkgewogIHRyeSB7CiAgICBjb25zdCByID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FjdGlvbicsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7dGV4dDogSlNPTi5zdHJpbmdpZnkoe3R5cGUsIC4uLnBhcmFtc30pLCBwYywgZ2FtZV9zdGF0ZTogYnVpbGRHYW1lU3RhdGUoKSwKICAgICAgICBoaXN0b3J5OltdLCBhcGlfa2V5OiBhcGlLZXl8fCcnLCByb2xsX29ubHk6dHJ1ZX0pfSk7CiAgICByZXR1cm4gYXdhaXQgci5qc29uKCk7CiAgfSBjYXRjaChlKSB7CiAgICByZXR1cm4ge2Vycm9yOiBlLm1lc3NhZ2UsIGZtdDogYFtyb2xsIGVycm9yXWB9OwogIH0KfQoKYXN5bmMgZnVuY3Rpb24gcm9sbERpY2Uoc2lkZXMsIGNvdW50PTEpIHsKICBjb25zdCByZXN1bHQgPSBhd2FpdCBzZXJ2ZXJSb2xsKCdkaWNlJywge3NpZGVzLCBjb3VudH0pOwogIHJldHVybiByZXN1bHQuZm10IHx8IGBbJHtjb3VudH1kJHtzaWRlc30gcm9sbCBmYWlsZWRdYDsKfQoKZnVuY3Rpb24gc2hvd1Jvb21Db2RlKCkgewogIGlmICghcm9vbUNvZGUpIHJldHVybjsKICBjb25zdCB3cmFwID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RvcC1yb29tLXdyYXAnKTsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3Atcm9vbScpOwogIGlmICh3cmFwKSB3cmFwLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgaWYgKGVsKSBlbC50ZXh0Q29udGVudCA9IHJvb21Db2RlOwp9CgpmdW5jdGlvbiBjb3B5Um9vbUNvZGUoKSB7CiAgaWYgKCFyb29tQ29kZSkgcmV0dXJuOwogIG5hdmlnYXRvci5jbGlwYm9hcmQud3JpdGVUZXh0KHJvb21Db2RlKS50aGVuKCgpID0+IHsKICAgIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3RvcC1yb29tLWNvcHknKTsKICAgIGlmIChlbCkgeyBlbC50ZXh0Q29udGVudCA9ICcnOyBzZXRUaW1lb3V0KCgpID0+IHsgZWwudGV4dENvbnRlbnQgPSAnJzsgfSwgMTUwMCk7IH0KICB9KTsKfQoKZnVuY3Rpb24gY29uZmlybVJlc2V0KCkgewogIGNvbnN0IG1vZGFsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlc2V0LW1vZGFsJyk7CiAgbW9kYWwuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKfQoKZnVuY3Rpb24gY2xvc2VSZXNldCgpIHsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVzZXQtbW9kYWwnKS5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwp9CgpmdW5jdGlvbiBkb1Jlc2V0KCkgewogIC8vIEhpZGUgdGhlIG1vZGFsIGltbWVkaWF0ZWx5CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlc2V0LW1vZGFsJykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKCiAgLy8gU3RvcCBwb2xsaW5nCiAgaWYgKHBvbGxUaW1lcikgeyBjbGVhckludGVydmFsKHBvbGxUaW1lcik7IHBvbGxUaW1lciA9IG51bGw7IH0KCiAgLy8gUmVzZXQgbWVtb3J5IHN5c3RlbQogIHJlc2V0TWVtb3J5KCk7CgogIC8vIFNhdmUgbW9kdWxlIGluZm8gYmVmb3JlIGNsZWFyaW5nCiAgY29uc3Qgc2F2ZWRNb2R1bGUgPSBtb2R1bGVUZXh0OwogIGNvbnN0IHNhdmVkTW9kdWxlTmFtZSA9IG1vZHVsZU5hbWU7CiAgY29uc3Qgc2F2ZWRSdWxlcyA9IGNob3NlblJ1bGVzOwoKICAvLyBSZXNldCBhbGwgZ2FtZSBzdGF0ZQogIHJvb21Db2RlID0gJyc7IGlzTXVsdGlwbGF5ZXIgPSBmYWxzZTsgaXNIb3N0ID0gZmFsc2U7CiAgY2hvc2VuUmFjZSA9ICdIdW1hbic7IGNob3NlbkNsYXNzID0gJ0ZpZ2h0ZXInOyBjaG9zZW5BbGlnbiA9ICdOZXV0cmFsJzsKICByb2xsZWRTdGF0cyA9IHt9OyBwYyA9IHt9OyBwYXJ0eVBDcyA9IHt9OwogIGhpc3RvcnkgPSBbXTsgbG9nRW50cmllcyA9IFtdOyBidXN5ID0gZmFsc2U7CiAgc3lzdGVtUHJvbXB0ID0gJyc7IGxhc3RTZXEgPSAwOyB1cGxvYWRlZEZpbGUgPSBudWxsOwogIGdvbGRTcGVudCA9IDA7IHNlbGVjdGVkRXF1aXAgPSB7fTsgZXh0cmFJdGVtcyA9IFtdOwogIG1vZHVsZVRleHQgPSBzYXZlZE1vZHVsZTsKICBtb2R1bGVOYW1lID0gc2F2ZWRNb2R1bGVOYW1lOwogIGNob3NlblJ1bGVzID0gc2F2ZWRSdWxlczsKCiAgLy8gQ2xlYXIgVUkgLS0gdXNlIHNhZmUgaGVscGVyIHRvIGF2b2lkIG51bGwgZXJyb3JzCiAgZnVuY3Rpb24gc2FmZVNldChpZCwgcHJvcCwgdmFsKSB7CiAgICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKGlkKTsKICAgIGlmIChlbCkgZWxbcHJvcF0gPSB2YWw7CiAgfQogIHNhZmVTZXQoJ2xvZycsICdpbm5lckhUTUwnLCAnJyk7CiAgc2FmZVNldCgncXVpY2stYnRucycsICdpbm5lckhUTUwnLCAnJyk7CiAgc2FmZVNldCgndG9wLW1vZCcsICd0ZXh0Q29udGVudCcsICcnKTsKICBzYWZlU2V0KCd0b3AtcnVsZXMnLCAndGV4dENvbnRlbnQnLCAnJyk7CiAgc2FmZVNldCgnc2NlbmUtbG9jJywgJ3RleHRDb250ZW50JywgJy4uLicpOwogIHNhZmVTZXQoJ3NjZW5lLXRhZycsICd0ZXh0Q29udGVudCcsICcnKTsKICBjb25zdCBydyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3Atcm9vbS13cmFwJyk7CiAgaWYgKHJ3KSBydy5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwoKICAvLyBGb3JjZSBoaWRlIEFMTCBzY3JlZW5zCiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnNjcmVlbicpLmZvckVhY2gocyA9PiB7CiAgICBzLmNsYXNzTGlzdC5yZW1vdmUoJ2FjdGl2ZScpOwogICAgcy5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogIH0pOwoKICAvLyBHbyB0byBjaGFyIGNyZWF0aW9uIGlmIHdlIGhhdmUgYSBtb2R1bGUsIGhvbWUgc2NyZWVuIGlmIG5vdAogIGlmIChzYXZlZE1vZHVsZSAmJiBzYXZlZE1vZHVsZU5hbWUpIHsKICAgIGNvbnN0IGNoYXJTY3JlZW4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncy1jaGFyJyk7CiAgICBjaGFyU2NyZWVuLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICBjaGFyU2NyZWVuLmNsYXNzTGlzdC5hZGQoJ2FjdGl2ZScpOwogICAgY2hhclNjcmVlbi5zY3JvbGxUb3AgPSAwOwogICAgY29uc3QgY21sID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NoYXItbW9kdWxlLWxibCcpOwogICAgaWYgKGNtbCkgY21sLnRleHRDb250ZW50ID0gc2F2ZWRNb2R1bGVOYW1lOwogICAgY29uc3QgbXBuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21wLWNoYXItbm90ZScpOwogICAgaWYgKG1wbikgbXBuLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICBjb25zdCByYiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZWFkeS1idG4nKTsKICAgIGlmIChyYikgeyByYi50ZXh0Q29udGVudCA9ICcgUmVhZHknOyByYi5kaXNhYmxlZCA9IGZhbHNlOyB9CiAgICBjb25zdCBiYiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdiZWdpbi1idG4nKTsKICAgIGlmIChiYikgYmIuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGJ1aWxkQ2hhckNyZWF0ZSgpOwogIH0gZWxzZSB7CiAgICBjb25zdCBob21lU2NyZWVuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtaG9tZScpOwogICAgaG9tZVNjcmVlbi5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogICAgaG9tZVNjcmVlbi5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICAgIGhvbWVTY3JlZW4uc2Nyb2xsVG9wID0gMDsKICB9Cn0KCmZ1bmN0aW9uIHNhdmVHYW1lKCkgewogIHhockZldGNoKEJBU0VfVVJMICsgJy9zYXZlJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgIG1vZHVsZU5hbWUsIGNob3NlblJ1bGVzLCBpc011bHRpcGxheWVyLAogICAgICBwY05hbWU6IHBjLm5hbWUsIHBjQ2xhc3M6IHBjLmNscywKICAgICAgcGMsIHBhcnR5UENzLCBoaXN0b3J5LCBzeXN0ZW1Qcm9tcHQsIG1vZHVsZVRleHQsCiAgICAgIGxvZ0VudHJpZXMsCiAgICAgIG1lbW9yeVN1bW1hcnksIHdvcmxkU3RhdGUsIHBpbm5lZEZhY3RzLCB0dXJuQ291bnQsCiAgICAgIG5wY1Byb2ZpbGVzLCBsb2NhdGlvbkF0bW9zcGhlcmUsIHNlc3Npb25Ub25lLAogICAgICBnbUJyaWVmaW5nLCBucGNLbm93bGVkZ2VNYXAsCiAgICAgIHBhY2luZ0hpc3RvcnksIGN1cnJlbnRQYWNpbmdQaGFzZSwgY29uc2VxdWVuY2VzLAogICAgICBpbkNvbWJhdCwgY29tYmF0U3RhdGUsIGR1bmdlb25UdXJucywgdG9yY2hUdXJuc0xlZnQsCiAgICAgIGhhc0xhbnRlcm4sIGxhbnRlcm5PaWxGbGFza3NMZWZ0LCByYXRpb25zTGVmdCwgcmVzdERlYnQsIHR1cm5zV2l0aG91dFJlc3QsIGZhdGlndWVQZW5hbHR5LCBkYXlzV2l0aG91dEZvb2QsIHN0YXJ2YXRpb25QZW5hbHR5LAogICAgICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIKICAgIH0pCiAgfSkudGhlbihyPT5yLmpzb24oKSkudGhlbihkID0+IHsKICAgIGlmIChkLm9rKSB7CiAgICAgIGNvbnN0IGJ0biA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoJy50b3AtYnRuJyk7CiAgICAgIGJ0bi50ZXh0Q29udGVudCA9ICcgU2F2ZWQhJzsKICAgICAgc2V0VGltZW91dCgoKSA9PiB7IGJ0bi50ZXh0Q29udGVudCA9ICcgU2F2ZSc7IH0sIDIwMDApOwogICAgfQogIH0pOwp9CgpmdW5jdGlvbiBzaG93UnVsZXMoKSB7CiAgYWxlcnQoUlVMRVNfVEVYVFtjaG9zZW5SdWxlc10gfHwgUlVMRVNfVEVYVFsnT1NFIEFkdmFuY2VkIEZhbnRhc3knXSk7Cn0KCgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gVjQgU1RBVEUgVkFSSUFCTEVTCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQpsZXQgaW5Db21iYXQgPSBmYWxzZTsKbGV0IHBsYXllckhpZGRlbiA9IGZhbHNlOwpsZXQgY3VycmVudE5QQ3MgPSBbXTsKbGV0IGN1cnJlbnRPYmplY3RzID0gW107CmxldCBjb21iYXRTdGF0ZSA9IHsgZW5jb3VudGVyOiBudWxsLCByb3VuZDogMCB9OwpsZXQgbG9hZGVkTW9kdWxlRGF0YSA9IHt9OwpsZXQgYWN0aXZlRWZmZWN0c1Y0ID0gW107ICAvLyBbe3R5cGUsIHR1cm5zTGVmdCwgYm9udXMsIC4uLn1dCgovLyBTcGVsbCBzeXN0ZW0gc3RhdGUKbGV0IHNwZWxsQm9vayA9IHt9OyAgICAgICAgICAvLyB7c3BlbGxOYW1lOiB7bGV2ZWwsIHR5cGUsIGtub3duOnRydWV9fQpsZXQgbWVtb3JpemVkU3BlbGxzID0gW107ICAgIC8vIFt7bmFtZSwgbGV2ZWx9XSAtLSB0b2RheSdzIG1lbW9yaXplZCBzcGVsbHMKbGV0IHNwZWxsU2xvdHNUb3RhbCA9IFtdOyAgICAvLyBbY291bnRfbHZsMSwgY291bnRfbHZsMiwgLi4uXQpsZXQgc3BlbGxTbG90c1JlbWFpbmluZyA9IFtdOyAvLyBzYW1lIGJ1dCBkZWNyZW1lbnRzIG9uIGNhc3QKCi8vIEFiaWxpdHkgdXNlcyB0b2RheQpsZXQgYWJpbGl0eVVzZXNUb2RheSA9IHt9OyAgIC8vIHthYmlsaXR5TmFtZTogY291bnR9CgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gVjQgQ09SRSBBQ1RJT04gUElQRUxJTkUKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CmFzeW5jIGZ1bmN0aW9uIHNlbmQoKSB7CiAgY29uc3QgaW5wID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpOwogIGNvbnN0IHYgPSBpbnAudmFsdWUudHJpbSgpOwogIGlmICghdiB8fCBidXN5KSByZXR1cm47CiAgaW5wLnZhbHVlID0gJyc7CgogIC8vIC9HTSBvdXQtb2YtY2hhcmFjdGVyIHF1ZXN0aW9uCiAgY29uc3Qgc2xhc2hNYXRjaCA9IHYubWF0Y2goL15bLl0oW0EtWmEtel1bQS1aYS16MC05XyBdKz8pWy5dcysoLispJC8pOwogIGlmIChzbGFzaE1hdGNoKSB7CiAgICBjb25zdCB0YXJnZXQgPSBzbGFzaE1hdGNoWzFdLnRyaW0oKS50b0xvd2VyQ2FzZSgpOwogICAgY29uc3QgbWVzc2FnZSA9IHNsYXNoTWF0Y2hbMl0udHJpbSgpOwogICAgaWYgKFsnZ20nLCdkbSddLmluY2x1ZGVzKHRhcmdldCkpIHsKICAgICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjojN2E5YTdhO2ZvbnQtc3R5bGU6aXRhbGljOyI+KE9PQykgJyArIHBjLm5hbWUgKyAnOiAnICsgbWVzc2FnZSArICc8L3NwYW4+JywgJ3BsYXllcicsIHBjLm5hbWUpOwogICAgICBhd2FpdCBjYWxsQWN0aW9uVjQoJ1tHTSBSVUxFUyBRVUVTVElPTiAtLSBhbnN3ZXIgZGlyZWN0bHksIG5vIG5hcnJhdGl2ZV06ICcgKyBtZXNzYWdlKTsKICAgICAgcmV0dXJuOwogICAgfQogICAgLy8gUGxheWVyLXRvLXBsYXllciBkaXJlY3QgbWVzc2FnZSAtLSBuZXZlciBnb2VzIHRvIEFJCiAgICBhZGRFbnRyeVJhdygnPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLWdvbGQpIj4nICsgcGMubmFtZSArICcgLT4gJyArIHNsYXNoTWF0Y2hbMV0gKyAnOjwvc3Bhbj4gJyArIG1lc3NhZ2UsICdwbGF5ZXInLCBwYy5uYW1lKTsKICAgIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlKSB7CiAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9jaGF0Jywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGU6cm9vbUNvZGUsIHBsYXllcjpwYy5uYW1lLCBtc2c6diwgdHlwZTonZGlyZWN0J30pfSk7CiAgICB9CiAgICByZXR1cm47CiAgfQoKICBhZGRFbnRyeVJhdyhpc011bHRpcGxheWVyID8gJzxiPicgKyBwYy5uYW1lICsgJzo8L2I+ICcgKyB2IDogdiwgJ3BsYXllcicsIHBjLm5hbWUpOwogIGF3YWl0IGNhbGxBY3Rpb25WNCh2KTsKfQoKYXN5bmMgZnVuY3Rpb24gcXVpY2tBY3QodCkgewogIGlmIChidXN5KSByZXR1cm47CiAgYWRkRW50cnlSYXcoaXNNdWx0aXBsYXllciA/ICc8Yj4nICsgcGMubmFtZSArICc6PC9iPiAnICsgdCA6IHQsICdwbGF5ZXInLCBwYy5uYW1lKTsKICBhd2FpdCBjYWxsQWN0aW9uVjQodCk7Cn0KCmFzeW5jIGZ1bmN0aW9uIGNhbGxBY3Rpb25WNCh0ZXh0KSB7CiAgaWYgKGJ1c3kpIHJldHVybjsKICBidXN5ID0gdHJ1ZTsKICBjb25zdCBzZW5kQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJyk7CiAgY29uc3QgY21kSW5wICA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKTsKICBpZiAoc2VuZEJ0bikgc2VuZEJ0bi5kaXNhYmxlZCA9IHRydWU7CiAgaWYgKGNtZElucCkgIGNtZElucC5kaXNhYmxlZCA9IHRydWU7CgogIGNvbnN0IHRoaW5rRWwgPSBhZGRFbnRyeVJhdygnVGhlIEdhbWUgTWFzdGVyIGNvbnNpZGVycy4uLicsICd0aGlua2luZycsICdfX2dtX18nKTsKCiAgdHJ5IHsKICAgIGNvbnN0IHJlc3AgPSBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvYWN0aW9uJywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgICAgdGV4dCwKICAgICAgICBwYzogYnVpbGRQQ1N0YXRlKCksCiAgICAgICAgZ2FtZV9zdGF0ZTogYnVpbGRHYW1lU3RhdGUoKSwKICAgICAgICBoaXN0b3J5OiBoaXN0b3J5LnNsaWNlKC0xMiksCiAgICAgICAgYXBpX2tleTogYXBpS2V5IHx8ICcnLAogICAgICAgIHJvb21fY29kZTogcm9vbUNvZGUgfHwgJycsCiAgICAgIH0pCiAgICB9KTsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKICAgIGlmICh0aGlua0VsICYmIHRoaW5rRWwucGFyZW50Tm9kZSkgdGhpbmtFbC5wYXJlbnROb2RlLnJlbW92ZUNoaWxkKHRoaW5rRWwpOwoKICAgIC8vIC0tIExheWVyIDEgcmVqZWN0aW9uIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAgIGlmIChkYXRhLnJlamVjdGlvbikgewogICAgICBhZGRFbnRyeVJhdygnPGRpdiBjbGFzcz0icmVqZWN0aW9uLW1zZyI+JiM5ODg4OyAnICsgZGF0YS5yZWplY3Rpb24gKyAnPC9kaXY+JywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgZmluaXNoQWN0aW9uKCk7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBpZiAoZGF0YS5lcnJvcikgewogICAgICBhZGRFbnRyeVJhdygnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjA7Ij5FcnJvcjogJyArIGRhdGEuZXJyb3IgKyAnPC9zcGFuPicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIGZpbmlzaEFjdGlvbigpOwogICAgICByZXR1cm47CiAgICB9CgogICAgLy8gLS0gTGF5ZXIgMzogcGFyc2UgbGluZSB0aGVuIGRpY2UgcmVzdWx0cyAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAgIGlmIChkYXRhLmRpc3BsYXlfcm9sbHMgJiYgZGF0YS5kaXNwbGF5X3JvbGxzLmxlbmd0aCkgewogICAgICBsZXQgcGFyc2VQYXJ0ID0gJyc7CiAgICAgIGxldCBkaWNlUGFydHMgPSBbXTsKICAgICAgZGF0YS5kaXNwbGF5X3JvbGxzLmZvckVhY2gobGluZSA9PiB7CiAgICAgICAgaWYgKGxpbmUuc3RhcnRzV2l0aCgnUEFSU0U6JykpIHsKICAgICAgICAgIHBhcnNlUGFydCA9ICc8ZGl2IGNsYXNzPSJwYXJzZS1saW5lIj4nICsgbGluZS5zbGljZSg2KSArICc8L2Rpdj4nOwogICAgICAgIH0gZWxzZSB7CiAgICAgICAgICBkaWNlUGFydHMucHVzaCgnPGRpdiBjbGFzcz0iZGljZS1saW5lIj4nICsgbGluZSArICc8L2Rpdj4nKTsKICAgICAgICB9CiAgICAgIH0pOwogICAgICBjb25zdCBpbm5lciA9IHBhcnNlUGFydCArIGRpY2VQYXJ0cy5qb2luKCcnKTsKICAgICAgaWYgKGlubmVyKSBhZGRFbnRyeVJhdygnPGRpdiBjbGFzcz0icm9sbC1yZXN1bHQtYm94Ij4nICsgaW5uZXIgKyAnPC9kaXY+JywgJ3N5c3RlbS1yb2xsJywgJ19fcm9sbF9fJyk7CiAgICB9CgogICAgLy8gLS0gTGF5ZXIgNCBuYXJyYXRpb24gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgaWYgKGRhdGEubmFycmF0aW9uKSB7CiAgICAgIGNvbnN0IHBhcmFzID0gZGF0YS5uYXJyYXRpb24uc3BsaXQoL1suXW5bLl1uKy8pLmZpbHRlcihwID0+IHAudHJpbSgpKTsKICAgICAgaWYgKHBhcmFzLmxlbmd0aCA+IDEpIHsKICAgICAgICBwYXJhcy5mb3JFYWNoKHAgPT4gYWRkRW50cnlSYXcoZm10KHAudHJpbSgpKSwgJ2dtJywgJ19fZ21fXycpKTsKICAgICAgfSBlbHNlIHsKICAgICAgICBhZGRFbnRyeVJhdyhmbXQoZGF0YS5uYXJyYXRpb24pLCAnZ20nLCAnX19nbV9fJyk7CiAgICAgIH0KICAgIH0KCiAgICAvLyAtLSBBcHBseSBzdGF0ZSBjaGFuZ2VzIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBpZiAoZGF0YS5zdGF0ZV9jaGFuZ2VzKSBhcHBseVN0YXRlQ2hhbmdlcyhkYXRhLnN0YXRlX2NoYW5nZXMpOwoKICAgIC8vIC0tIExldmVsIHVwIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgaWYgKGRhdGEubGV2ZWxfdXApIHNob3dMZXZlbFVwTW9kYWwoZGF0YS5sZXZlbF91cCk7CgogICAgLy8gLS0gVXBkYXRlIGhpc3RvcnkgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgcHVzaE1lc3NhZ2UoJ3VzZXInLCB0ZXh0KTsKICAgIGlmIChkYXRhLm5hcnJhdGlvbikgcHVzaE1lc3NhZ2UoJ2Fzc2lzdGFudCcsIGRhdGEubmFycmF0aW9uKTsKCiAgICAvLyAtLSBBZHZhbmNlIGR1bmdlb24gY2xvY2sgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBpZiAoIVsnZXhhbWluZScsJ3Jlc3QnLCdvdGhlciddLmluY2x1ZGVzKChkYXRhLmFjdGlvbl90eXBlfHwnJykudG9Mb3dlckNhc2UoKSkpIHsKICAgICAgYWR2YW5jZUR1bmdlb25UdXJuKCk7CiAgICB9CgogICAgdXBkYXRlSFVEKCk7CiAgICB1cGRhdGVTcGVsbGJvb2tQYW5lbCgpOwogICAgdXBkYXRlQWJpbGl0eVBhbmVsKCk7CgogIH0gY2F0Y2goZSkgewogICAgaWYgKHRoaW5rRWwgJiYgdGhpbmtFbC5wYXJlbnROb2RlKSB0aGlua0VsLnBhcmVudE5vZGUucmVtb3ZlQ2hpbGQodGhpbmtFbCk7CiAgICBhZGRFbnRyeVJhdygnJiM5ODg4OyBDb25uZWN0aW9uIGVycm9yOiAnICsgKGUubWVzc2FnZXx8ZSksICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgfQogIGZpbmlzaEFjdGlvbigpOwp9CgpmdW5jdGlvbiBmaW5pc2hBY3Rpb24oKSB7CiAgYnVzeSA9IGZhbHNlOwogIGNvbnN0IHNlbmRCdG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKTsKICBjb25zdCBjbWRJbnAgID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpOwogIGlmIChzZW5kQnRuKSBzZW5kQnRuLmRpc2FibGVkID0gZmFsc2U7CiAgaWYgKGNtZElucCkgeyBjbWRJbnAuZGlzYWJsZWQgPSBmYWxzZTsgY21kSW5wLmZvY3VzKCk7IH0KfQoKZnVuY3Rpb24gYnVpbGRQQ1N0YXRlKCkgewogIHJldHVybiB7CiAgICAuLi5wYywKICAgIHNwZWxsYm9vazogc3BlbGxCb29rLAogICAgbWVtb3JpemVkX3NwZWxsczogbWVtb3JpemVkU3BlbGxzLAogICAgc3BlbGxfc2xvdHNfcmVtYWluaW5nOiBzcGVsbFNsb3RzUmVtYWluaW5nLAogICAgc3BlbGxfc2xvdHNfdG90YWw6IHNwZWxsU2xvdHNUb3RhbCwKICAgIGFjdGl2ZV9lZmZlY3RzOiBhY3RpdmVFZmZlY3RzVjQsCiAgICBhYmlsaXRpZXNfdXNlZF90b2RheTogYWJpbGl0eVVzZXNUb2RheSwKICAgIGVxdWlwcGVkX21hZ2ljOiAocGMuaW52fHxbXSkuZmlsdGVyKGkgPT4gaSAmJiAvcmluZ3xhbXVsZXR8Y2xvYWt8Ym9vdHMgb2Z8Z2xvdmVzIG9mL2kudGVzdCh0eXBlb2YgaT09PSdzdHJpbmcnP2k6aS5uYW1lfHwnJykpLAogIH07Cn0KCmZ1bmN0aW9uIGJ1aWxkR2FtZVN0YXRlKCkgewogIHJldHVybiB7CiAgICBpbl9jb21iYXQ6IGluQ29tYmF0LAogICAgaW5fZHVuZ2VvbjogaXNJbkR1bmdlb24oKSwKICAgIGN1cnJlbnRfcm9vbTogcGMubG9jdGFnIHx8ICcnLAogICAgY3VycmVudF9sb2NhdGlvbjogcGMubG9jIHx8ICcnLAogICAgY3VycmVudF9lbmNvdW50ZXI6IChjb21iYXRTdGF0ZSAmJiBjb21iYXRTdGF0ZS5lbmNvdW50ZXIpID8gY29tYmF0U3RhdGUuZW5jb3VudGVyIDoge30sCiAgICBucGNzX3ByZXNlbnQ6IGN1cnJlbnROUENzIHx8IFtdLAogICAgb2JqZWN0c19wcmVzZW50OiBjdXJyZW50T2JqZWN0cyB8fCBbXSwKICAgIHBsYXllcl9oaWRkZW46IHBsYXllckhpZGRlbiB8fCBmYWxzZSwKICAgIG1vZHVsZV9kYXRhOiBsb2FkZWRNb2R1bGVEYXRhIHx8IHt9LAogICAgcGFydHlfcGNzOiBwYXJ0eVBDcyB8fCB7fSwKICB9Owp9CgovLyAtLSBTdGF0ZSBhcHBsaWNhdGlvbiAoTGF5ZXIgMyByZXN1bHRzIC0+IGxvY2FsIHN0YXRlKSAtLS0tLS0tLS0tLS0tLS0tLS0tLS0KZnVuY3Rpb24gYXBwbHlTdGF0ZUNoYW5nZXMoc2MpIHsKICAvLyBNb25zdGVyIGRhbWFnZSAvIGRlYXRoCiAgaWYgKHNjLm1vbnN0ZXJfZGFtYWdlKSB7CiAgICBjb25zdCBtZCA9IHNjLm1vbnN0ZXJfZGFtYWdlOwogICAgaWYgKGNvbWJhdFN0YXRlLmVuY291bnRlciAmJiBjb21iYXRTdGF0ZS5lbmNvdW50ZXIubW9uc3RlcnMpIHsKICAgICAgY29uc3QgbSA9IGNvbWJhdFN0YXRlLmVuY291bnRlci5tb25zdGVycy5maW5kKHggPT4KICAgICAgICB4LmlkID09PSBtZC5tb25zdGVyX2lkIHx8IHgubmFtZSA9PT0gbWQubW9uc3Rlcl9pZCk7CiAgICAgIGlmIChtKSB7CiAgICAgICAgbS5ocCA9IG1kLm5ld19ocDsKICAgICAgICBpZiAobWQua2lsbGVkKSBtLmRlYWQgPSB0cnVlOwogICAgICB9CiAgICAgIGNvbnN0IGFsaXZlID0gY29tYmF0U3RhdGUuZW5jb3VudGVyLm1vbnN0ZXJzLmZpbHRlcihtID0+ICFtLmRlYWQgJiYgbS5ocCA+IDApOwogICAgICBpZiAoYWxpdmUubGVuZ3RoID09PSAwKSB7CiAgICAgICAgaW5Db21iYXQgPSBmYWxzZTsKICAgICAgICBhZGRFbnRyeVJhdygnW0FsbCBlbmVtaWVzIGRlZmVhdGVkIC0tIGNvbWJhdCBlbmRzXScsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIH0KICAgIH0KICB9CiAgLy8gTW9uc3RlciBmbGVlcwogIGlmIChzYy5tb25zdGVyX2ZsZWVzKSB7CiAgICBpZiAoY29tYmF0U3RhdGUuZW5jb3VudGVyICYmIGNvbWJhdFN0YXRlLmVuY291bnRlci5tb25zdGVycykgewogICAgICBjb25zdCBtID0gY29tYmF0U3RhdGUuZW5jb3VudGVyLm1vbnN0ZXJzLmZpbmQoeCA9PgogICAgICAgIHguaWQgPT09IHNjLm1vbnN0ZXJfZmxlZXMgfHwgeC5uYW1lID09PSBzYy5tb25zdGVyX2ZsZWVzKTsKICAgICAgaWYgKG0pIHsgbS5mbGVkID0gdHJ1ZTsgbS5ocCA9IDA7IH0KICAgIH0KICAgIGNvbnN0IGFsaXZlID0gKGNvbWJhdFN0YXRlLmVuY291bnRlciAmJiBjb21iYXRTdGF0ZS5lbmNvdW50ZXIubW9uc3RlcnN8fFtdKQogICAgICAuZmlsdGVyKG0gPT4gIW0uZGVhZCAmJiAhbS5mbGVkICYmIG0uaHAgPiAwKTsKICAgIGlmIChhbGl2ZS5sZW5ndGggPT09IDApIGluQ29tYmF0ID0gZmFsc2U7CiAgfQogIC8vIFhQIGdhaW4KICBpZiAoc2MueHBfZ2FpbikgewogICAgcGMueHAgPSAocGMueHAgfHwgMCkgKyBzYy54cF9nYWluOwogICAgYWRkRW50cnlSYXcoJ1tYUCArJyArIHNjLnhwX2dhaW4gKyAnICh0b3RhbDogJyArIHBjLnhwICsgJyldJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICB9CiAgLy8gUGxheWVyIGRhbWFnZQogIGlmIChzYy5wbGF5ZXJfZGFtYWdlICYmIHNjLnBsYXllcl9kYW1hZ2UgPiAwKSB7CiAgICBwYy5ocCA9IE1hdGgubWF4KDAsIChwYy5ocHx8MCkgLSBzYy5wbGF5ZXJfZGFtYWdlKTsKICAgIGlmIChwYy5ocCA8PSAwKSB7CiAgICAgIGFkZEVudHJ5UmF3KCc8c3BhbiBzdHlsZT0iY29sb3I6I2MwNjA2MDtmb250LXdlaWdodDpib2xkOyI+JiM5ODg4OyAnICsgCiAgICAgICAgKHBjLm5hbWV8fCdZb3UnKSArICcgaGFzIGJlZW4gcmVkdWNlZCB0byAwIEhQISBUaGUgYWR2ZW50dXJlIG1heSBiZSBvdmVyLi4uPC9zcGFuPicsCiAgICAgICAgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgIH0KICB9CiAgLy8gSGVhbGluZwogIGlmIChzYy5oZWFsX3BsYXllcikgewogICAgcGMuaHAgPSBNYXRoLm1pbihwYy5tYXhocCB8fCBwYy5ocCwgKHBjLmhwfHwwKSArIHNjLmhlYWxfcGxheWVyKTsKICB9CiAgLy8gU3BlbGwgc2xvdCBjb25zdW1wdGlvbgogIGlmIChzYy5jb25zdW1lX3NwZWxsX3Nsb3QgIT09IHVuZGVmaW5lZCkgewogICAgY29uc3QgaWR4ID0gc2MuY29uc3VtZV9zcGVsbF9zbG90IC0gMTsKICAgIGlmIChzcGVsbFNsb3RzUmVtYWluaW5nW2lkeF0gPiAwKSBzcGVsbFNsb3RzUmVtYWluaW5nW2lkeF0tLTsKICAgIC8vIFJlbW92ZSBmcm9tIG1lbW9yaXplZCAob25lIGluc3RhbmNlKQogICAgY29uc3QgbUlkeCA9IG1lbW9yaXplZFNwZWxscy5maW5kSW5kZXgocyA9PgogICAgICAodHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZSkgJiYgQUxMX1NQRUxMX0xFVkVMU1t0eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lXSA9PT0gc2MuY29uc3VtZV9zcGVsbF9zbG90KTsKICAgIGlmIChtSWR4ID49IDApIG1lbW9yaXplZFNwZWxscy5zcGxpY2UobUlkeCwgMSk7CiAgfQogIC8vIEFtbW8gY29uc3VtcHRpb24KICBpZiAoc2MuY29uc3VtZV9hbW1vKSB7CiAgICBjb25zdCBpbnYgPSBwYy5pbnYgfHwgW107CiAgICBjb25zdCBhaSA9IGludi5maW5kSW5kZXgoaSA9PiAvYm9sdHxhcnJvd3xzdG9uZXxxdWFycmVsL2kudGVzdCh0eXBlb2YgaT09PSdzdHJpbmcnP2k6KGkubmFtZXx8JycpKSk7CiAgICBpZiAoYWkgPj0gMCkgewogICAgICBjb25zdCBpdGVtID0gdHlwZW9mIGludlthaV09PT0nc3RyaW5nJyA/IGludlthaV0gOiBpbnZbYWldLm5hbWU7CiAgICAgIGNvbnN0IG51bU0gPSBpdGVtLm1hdGNoKC9bLl0oWy5dZCspWy5dLyk7CiAgICAgIGlmIChudW1NKSB7CiAgICAgICAgY29uc3QgbiA9IHBhcnNlSW50KG51bU1bMV0pIC0gMTsKICAgICAgICBpZiAobiA8PSAwKSBpbnYuc3BsaWNlKGFpLCAxKTsKICAgICAgICBlbHNlIGludlthaV0gPSBpdGVtLnJlcGxhY2UoL1suXVsuXWQrWy5dLywgJygnICsgbiArICcpJyk7CiAgICAgIH0KICAgIH0KICB9CiAgLy8gUmF0aW9uIGNvbnN1bXB0aW9uCiAgaWYgKHNjLmNvbnN1bWVfcmF0aW9uKSB7CiAgICByYXRpb25zTGVmdCA9IE1hdGgubWF4KDAsIChyYXRpb25zTGVmdHx8MCkgLSAxKTsKICAgIGRheXNXaXRob3V0Rm9vZCA9IDA7IHN0YXJ2YXRpb25QZW5hbHR5ID0gMDsKICB9CiAgLy8gVG9yY2ggbGlnaHRpbmcKICBpZiAoc2MubGlnaHRfdG9yY2gpIHsKICAgIHRvcmNoTGl0ID0gdHJ1ZTsgdG9yY2hFdmVyVXNlZCA9IHRydWU7IHRvcmNoVHVybnNMZWZ0ID0gNjsKICAgIGNvbnN0IGludiA9IHBjLmludiB8fCBbXTsKICAgIGNvbnN0IHRpID0gaW52LmZpbmRJbmRleChpID0+IC90b3JjaC9pLnRlc3QodHlwZW9mIGk9PT0nc3RyaW5nJz9pOihpLm5hbWV8fCcnKSkpOwogICAgaWYgKHRpID49IDApIHsKICAgICAgY29uc3QgaXRlbSA9IHR5cGVvZiBpbnZbdGldPT09J3N0cmluZycgPyBpbnZbdGldIDogJyc7CiAgICAgIGNvbnN0IG5tID0gaXRlbS5tYXRjaCgvWy5dKFsuXWQrKVsuXS8pOwogICAgICBpZiAobm0gJiYgcGFyc2VJbnQobm1bMV0pPjEpIGludlt0aV0gPSBpdGVtLnJlcGxhY2UoL1suXVsuXWQrWy5dLywnKCcgKyAocGFyc2VJbnQobm1bMV0pLTEpICsgJyknKTsKICAgICAgZWxzZSBpbnYuc3BsaWNlKHRpLDEpOwogICAgfQogIH0KICAvLyBJdGVtIGNvbnN1bXB0aW9uCiAgaWYgKHNjLmNvbnN1bWVfaXRlbSkgewogICAgY29uc3QgaW52ID0gcGMuaW52IHx8IFtdOwogICAgY29uc3QgaWR4ID0gaW52LmZpbmRJbmRleChpID0+ICh0eXBlb2YgaT09PSdzdHJpbmcnP2k6KGkubmFtZXx8JycpKSA9PT0gc2MuY29uc3VtZV9pdGVtKTsKICAgIGlmIChpZHggPj0gMCkgaW52LnNwbGljZShpZHgsIDEpOwogIH0KICAvLyBGdWxsIHJlc3QKICBpZiAoc2MuZnVsbF9yZXN0KSB7CiAgICB0dXJuc1dpdGhvdXRSZXN0ID0gMDsgZmF0aWd1ZVBlbmFsdHkgPSAwOwogICAgc3BlbGxTbG90c1JlbWFpbmluZyA9IFsuLi5zcGVsbFNsb3RzVG90YWxdOwogICAgYWRkRW50cnlSYXcoJ1tGdWxsIHJlc3QgY29tcGxldGUuIFNwZWxsIHNsb3RzIHJlc3RvcmVkLiBBd2FpdGluZyBtZW1vcml6YXRpb24uXScsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAvLyBQcm9tcHQgbWVtb3JpemF0aW9uIGlmIHNwZWxsY2FzdGVyCiAgICBpZiAoc3BlbGxTbG90c1RvdGFsLmxlbmd0aCA+IDApIG9wZW5NZW1vcml6ZSgpOwogIH0KICAvLyBEdW5nZW9uIHJlc3QKICBpZiAoc2MuZHVuZ2Vvbl9yZXN0KSB7IHR1cm5zV2l0aG91dFJlc3QgPSAwOyBmYXRpZ3VlUGVuYWx0eSA9IDA7IH0KICAvLyBBY3RpdmUgZWZmZWN0cwogIGlmIChzYy5hZGRfZWZmZWN0KSB7CiAgICBhY3RpdmVFZmZlY3RzVjQucHVzaCh7Li4uc2MuYWRkX2VmZmVjdCwgc3RhcnRlZEF0OiB0dXJuQ291bnR9KTsKICB9CiAgLy8gQWJpbGl0eSB1c2VzCiAgaWYgKHNjLmFiaWxpdHlfdXNlZCkgewogICAgY29uc3QgYW5hbWUgPSBzYy5hYmlsaXR5X3VzZWQubmFtZTsKICAgIGFiaWxpdHlVc2VzVG9kYXlbYW5hbWVdID0gKGFiaWxpdHlVc2VzVG9kYXlbYW5hbWVdfHwwKSArIChzYy5hYmlsaXR5X3VzZWQuYW1vdW50fHwxKTsKICB9Cn0KCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBMRVZFTCBVUCBTWVNURU0KLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CmZ1bmN0aW9uIHNob3dMZXZlbFVwTW9kYWwobHUpIHsKICBjb25zdCBjaGFuZ2VzID0gbHUuY2hhbmdlcyB8fCBbXTsKICBjb25zdCBuZXdMdmwgPSBsdS5uZXdfbGV2ZWw7CiAgY29uc3QgaHRtbCA9IGAKICAgIDxkaXYgY2xhc3M9ImxldmVsLXVwLW1vZGFsIiBpZD0ibHYtbW9kYWwiPgogICAgICA8ZGl2IGNsYXNzPSJsZXZlbC11cC1pbm5lciI+CiAgICAgICAgPGRpdiBjbGFzcz0ibHYtdGl0bGUiPiYjOTczMzsgTEVWRUwgVVAhICYjOTczMzs8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJ0ZXh0LWFsaWduOmNlbnRlcjtmb250LXNpemU6MTdweDttYXJnaW4tYm90dG9tOjE0cHg7Ij4KICAgICAgICAgICR7cGMubmFtZX0gcmVhY2hlcyA8Yj5MZXZlbCAke25ld0x2bH08L2I+PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0ibWFyZ2luLWJvdHRvbToxNHB4OyI+CiAgICAgICAgICAke2NoYW5nZXMubWFwKGM9Pic8ZGl2IGNsYXNzPSJsdi1jaGFuZ2UiPicrYysnPC9kaXY+Jykuam9pbignJyl9CiAgICAgICAgPC9kaXY+CiAgICAgICAgJHsobHUudXBkYXRlZF9wYyAmJiBbJ01hZ2ljLVVzZXInLCdJbGx1c2lvbmlzdCcsJ0NsZXJpYycsJ0RydWlkJywnQmFyZCddLmluY2x1ZGVzKHBjLmNscykpCiAgICAgICAgICA/ICc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS1nb2xkLWRpbSk7Zm9udC1zaXplOjEzcHg7bWFyZ2luLWJvdHRvbToxMnB4OyI+JysKICAgICAgICAgICAgJ05ldyBzcGVsbCBzbG90cyBhdmFpbGFibGUuIFlvdSBtYXkgbWVtb3JpemUgc3BlbGxzIGFmdGVyIGEgZnVsbCBuaWdodCYjMzk7cyByZXN0LjwvZGl2PicgOiAnJ30KICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4iIHN0eWxlPSJ3aWR0aDoxMDAlIiBvbmNsaWNrPSJjbG9zZUxldmVsVXAoJHtKU09OLnN0cmluZ2lmeShKU09OLnN0cmluZ2lmeShsdS51cGRhdGVkX3BjKSl9KSI+CiAgICAgICAgICBDb250aW51ZSAmIzk2NTg7PC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+YDsKICBkb2N1bWVudC5ib2R5Lmluc2VydEFkamFjZW50SFRNTCgnYmVmb3JlZW5kJywgaHRtbCk7CiAgY29uc3QgY2hhbmdlc19zdHIgPSBjaGFuZ2VzLmpvaW4oJyB8ICcpOwogIGFkZEVudHJ5UmF3KCdbTEVWRUwgVVA6ICcgKyBwYy5uYW1lICsgJyByZWFjaGVzIGxldmVsICcgKyBuZXdMdmwgKyAnISAnICsgY2hhbmdlc19zdHIgKyAnXScsICdzeXN0ZW0nLCAnX19nbV9fJyk7Cn0KCmZ1bmN0aW9uIGNsb3NlTGV2ZWxVcCh1cGRhdGVkUGNKc29uKSB7CiAgY29uc3QgbW9kYWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbHYtbW9kYWwnKTsKICBpZiAobW9kYWwpIG1vZGFsLnJlbW92ZSgpOwogIGlmICh1cGRhdGVkUGNKc29uKSB7CiAgICB0cnkgewogICAgICBjb25zdCB1cGQgPSB0eXBlb2YgdXBkYXRlZFBjSnNvbiA9PT0gJ3N0cmluZycgPyBKU09OLnBhcnNlKHVwZGF0ZWRQY0pzb24pIDogdXBkYXRlZFBjSnNvbjsKICAgICAgT2JqZWN0LmFzc2lnbihwYywgdXBkKTsKICAgICAgLy8gVXBkYXRlIHNwZWxsIHNsb3RzIGlmIGNoYW5nZWQKICAgICAgaWYgKHVwZC5zcGVsbF9zbG90c190b3RhbCkgewogICAgICAgIHNwZWxsU2xvdHNUb3RhbCA9IHVwZC5zcGVsbF9zbG90c190b3RhbDsKICAgICAgICAvLyBEb24ndCByZXNldCByZW1haW5pbmcgLS0gdGhleSBtYXkgaGF2ZSBzbG90cyBsZWZ0CiAgICAgIH0KICAgICAgdXBkYXRlSFVEKCk7CiAgICAgIHVwZGF0ZVNwZWxsYm9va1BhbmVsKCk7CiAgICB9IGNhdGNoKGUpIHt9CiAgfQp9CgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gU1BFTEwgU1lTVEVNIFVJCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQoKLy8gTG9va3VwOiBzcGVsbCBuYW1lIC0+IGxldmVsIChwb3B1bGF0ZWQgZnJvbSBzZXJ2ZXIgZGF0YSkKY29uc3QgQUxMX1NQRUxMX0xFVkVMUyA9IHt9OwoKZnVuY3Rpb24gdXBkYXRlU3BlbGxib29rUGFuZWwoKSB7CiAgY29uc3QgcGFuZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3BlbGxib29rLXBhbmVsJyk7CiAgaWYgKCFwYW5lbCkgcmV0dXJuOwoKICBjb25zdCBzcGVsbGNhc3RpbmdDbGFzc2VzID0gWydNYWdpYy1Vc2VyJywnSWxsdXNpb25pc3QnLCdDbGVyaWMnLCdEcnVpZCcsJ1JhbmdlcicsJ1BhbGFkaW4nLCdCYXJkJ107CiAgaWYgKCFzcGVsbGNhc3RpbmdDbGFzc2VzLmluY2x1ZGVzKHBjLmNscykpIHsKICAgIHBhbmVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICByZXR1cm47CiAgfQogIHBhbmVsLnN0eWxlLmRpc3BsYXkgPSAnJzsKCiAgLy8gU2xvdHMgZGlzcGxheQogIGNvbnN0IHNsb3RzRWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2Itc2xvdHMnKTsKICBpZiAoc2xvdHNFbCkgewogICAgaWYgKCFzcGVsbFNsb3RzVG90YWwubGVuZ3RoKSB7CiAgICAgIHNsb3RzRWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS10ZXh0LWRpbSkiPk5vIHNwZWxsIHNsb3RzIGF0IHRoaXMgbGV2ZWwuPC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICBsZXQgaHRtbCA9ICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1nb2xkLWRpbSk7bWFyZ2luLWJvdHRvbTo0cHg7Ij5TUEVMTCBTTE9UUzwvZGl2Pic7CiAgICAgIHNwZWxsU2xvdHNUb3RhbC5mb3JFYWNoKCh0b3RhbCwgaWR4KSA9PiB7CiAgICAgICAgY29uc3QgdXNlZCA9IHRvdGFsIC0gKHNwZWxsU2xvdHNSZW1haW5pbmdbaWR4XXx8MCk7CiAgICAgICAgY29uc3QgcGlwcyA9IEFycmF5LmZyb20oe2xlbmd0aDp0b3RhbH0sIChfLGkpID0+CiAgICAgICAgICBgPHNwYW4gY2xhc3M9InNwZWxsLXNsb3QtcGlwJHtpPHVzZWQ/JyB1c2VkJzonJ30iPjwvc3Bhbj5gKS5qb2luKCcnKTsKICAgICAgICBodG1sICs9IGA8ZGl2IGNsYXNzPSJzcGVsbC1zbG90LXJvdyI+CiAgICAgICAgICA8c3BhbiBzdHlsZT0iZm9udC1zaXplOjExcHg7Y29sb3I6dmFyKC0tdGV4dC1kaW0pO3dpZHRoOjE2cHg7Ij4ke2lkeCsxfTwvc3Bhbj4KICAgICAgICAgICR7cGlwc308L2Rpdj5gOwogICAgICB9KTsKICAgICAgc2xvdHNFbC5pbm5lckhUTUwgPSBodG1sOwogICAgfQogIH0KCiAgLy8gTWVtb3JpemVkIHNwZWxscwogIGNvbnN0IG1lbUVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NiLW1lbW9yaXplZCcpOwogIGlmIChtZW1FbCkgewogICAgaWYgKCFtZW1vcml6ZWRTcGVsbHMubGVuZ3RoKSB7CiAgICAgIG1lbUVsLmlubmVySFRNTCA9ICc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS10ZXh0LWRpbSk7Zm9udC1zaXplOjEycHg7Ij5ObyBzcGVsbHMgbWVtb3JpemVkLjwvZGl2Pic7CiAgICB9IGVsc2UgewogICAgICBjb25zdCBieUxldmVsID0ge307CiAgICAgIG1lbW9yaXplZFNwZWxscy5mb3JFYWNoKHMgPT4gewogICAgICAgIGNvbnN0IG5hbWUgPSB0eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lOwogICAgICAgIGNvbnN0IGx2bCAgPSAodHlwZW9mIHM9PT0nb2JqZWN0JyYmcy5sZXZlbCkgfHwgQUxMX1NQRUxMX0xFVkVMU1tuYW1lXSB8fCAnPyc7CiAgICAgICAgaWYgKCFieUxldmVsW2x2bF0pIGJ5TGV2ZWxbbHZsXSA9IFtdOwogICAgICAgIGJ5TGV2ZWxbbHZsXS5wdXNoKG5hbWUpOwogICAgICB9KTsKICAgICAgbGV0IGh0bWwgPSAnJzsKICAgICAgT2JqZWN0LmtleXMoYnlMZXZlbCkuc29ydCgpLmZvckVhY2gobHZsID0+IHsKICAgICAgICBodG1sICs9IGA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS1nb2xkLWRpbSk7bWFyZ2luLXRvcDo0cHg7Ij5MZXZlbCAke2x2bH06PC9kaXY+YDsKICAgICAgICBieUxldmVsW2x2bF0uZm9yRWFjaChuYW1lID0+IHsKICAgICAgICAgIGh0bWwgKz0gYDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMnB4O3BhZGRpbmc6MXB4IDRweDsiPiYjOTY3MDsgJHtuYW1lfTwvZGl2PmA7CiAgICAgICAgfSk7CiAgICAgIH0pOwogICAgICBtZW1FbC5pbm5lckhUTUwgPSBodG1sOwogICAgfQogIH0KCiAgLy8gU2hvdyBtZW1vcml6ZSBidXR0b24gd2hlbiBzbG90cyA+IDAgYW5kIGFmdGVyIHJlc3QKICBjb25zdCBidG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtb3JpemUtYnRuJyk7CiAgaWYgKGJ0bikgewogICAgY29uc3QgaGFzU2xvdHMgPSBzcGVsbFNsb3RzVG90YWwuc29tZShzID0+IHMgPiAwKTsKICAgIGNvbnN0IGhhc1NwZWxscyA9IE9iamVjdC5rZXlzKHNwZWxsQm9vaykubGVuZ3RoID4gMDsKICAgIGJ0bi5zdHlsZS5kaXNwbGF5ID0gKGhhc1Nsb3RzICYmIGhhc1NwZWxscykgPyAnJyA6ICdub25lJzsKICB9Cn0KCi8vIC0tIE1lbW9yaXplIHNwZWxsIG1vZGFsIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQpmdW5jdGlvbiBvcGVuTWVtb3JpemUoKSB7CiAgY29uc3QgZXhpc3RpbmcgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtb3JpemUtbW9kYWwnKTsKICBpZiAoZXhpc3RpbmcpIGV4aXN0aW5nLnJlbW92ZSgpOwoKICBjb25zdCBzcGVsbGNhc3RpbmdDbGFzc2VzID0gewogICAgJ01hZ2ljLVVzZXInOiBNVV9TUEVMTFNfRk9SX0NMQVNTLAogICAgJ0lsbHVzaW9uaXN0JzogTVVfU1BFTExTX0ZPUl9DTEFTUywKICAgICdDbGVyaWMnOiBDTEVSSUNfU1BFTExTX0ZPUl9DTEFTUywKICAgICdEcnVpZCc6IERSVUlEX1NQRUxMU19GT1JfQ0xBU1MsCiAgICAnUmFuZ2VyJzogUkFOR0VSX1NQRUxMU19GT1JfQ0xBU1MsCiAgICAnUGFsYWRpbic6IENMRVJJQ19TUEVMTFNfRk9SX0NMQVNTLAogICAgJ0JhcmQnOiBCQVJEX1NQRUxMU19GT1JfQ0xBU1MsCiAgfTsKCiAgY29uc3QgY2xhc3NTcGVsbHMgPSBzcGVsbGNhc3RpbmdDbGFzc2VzW3BjLmNsc10gfHwge307CiAgY29uc3QgYWxsU3BlbGxzRm9yQ2xhc3MgPSBPYmplY3QuZW50cmllcyhjbGFzc1NwZWxscyk7CgogIGxldCBib2R5SHRtbCA9ICcnOwogIC8vIEZvciBNVS9JbGx1c2lvbmlzdDogY2FuIG9ubHkgbWVtb3JpemUgZnJvbSBzcGVsbGJvb2sKICAvLyBGb3IgQ2xlcmljL0RydWlkL2V0YzogY2FuIG1lbW9yaXplIGFueSBzcGVsbCBvZiBhcHByb3ByaWF0ZSBsZXZlbAogIGNvbnN0IHVzZXNTcGVsbGJvb2sgPSBbJ01hZ2ljLVVzZXInLCdJbGx1c2lvbmlzdCddLmluY2x1ZGVzKHBjLmNscyk7CgogIHNwZWxsU2xvdHNUb3RhbC5mb3JFYWNoKCh0b3RhbCwgc2xvdElkeCkgPT4gewogICAgaWYgKHRvdGFsID09PSAwKSByZXR1cm47CiAgICBjb25zdCBzcGVsbExldmVsID0gc2xvdElkeCArIDE7CiAgICBjb25zdCBhdmFpbGFibGVTcGVsbHMgPSBhbGxTcGVsbHNGb3JDbGFzcwogICAgICAuZmlsdGVyKChbbmFtZSwgZGF0YV0pID0+IHsKICAgICAgICBpZiAoZGF0YS5sZXZlbCAhPT0gc3BlbGxMZXZlbCkgcmV0dXJuIGZhbHNlOwogICAgICAgIGlmICh1c2VzU3BlbGxib29rICYmICFzcGVsbEJvb2tbbmFtZV0pIHJldHVybiBmYWxzZTsKICAgICAgICByZXR1cm4gdHJ1ZTsKICAgICAgfSk7CgogICAgaWYgKCFhdmFpbGFibGVTcGVsbHMubGVuZ3RoKSByZXR1cm47CgogICAgYm9keUh0bWwgKz0gYDxkaXYgc3R5bGU9Im1hcmdpbjoxMHB4IDAgNHB4O2ZvbnQtc2l6ZToxM3B4O2NvbG9yOnZhcigtLWdvbGQpOyI+CiAgICAgIExldmVsICR7c3BlbGxMZXZlbH0gU3BlbGxzICgke3RvdGFsfSBzbG90cyk8L2Rpdj5gOwogICAgYXZhaWxhYmxlU3BlbGxzLmZvckVhY2goKFtuYW1lLCBkYXRhXSkgPT4gewogICAgICBjb25zdCBhbHJlYWR5Q291bnRlZCA9IG1lbW9yaXplZFNwZWxscy5maWx0ZXIocyA9PgogICAgICAgICh0eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lKSA9PT0gbmFtZSkubGVuZ3RoOwogICAgICBib2R5SHRtbCArPSBgCiAgICAgICAgPGRpdiBjbGFzcz0ic3BlbGwtY2FyZCIgaWQ9InNjLSR7bmFtZS5yZXBsYWNlKC9bLl1zKy9nLCctJyl9IgogICAgICAgICAgb25jbGljaz0idG9nZ2xlTWVtb3JpemVTcGVsbCgnJHtuYW1lfScsICR7c3BlbGxMZXZlbH0pIgogICAgICAgICAgdGl0bGU9IiR7ZGF0YS5kZXNjfHwnJ30iPgogICAgICAgICAgPGRpdiBjbGFzcz0ic25hbWUiPiR7bmFtZX0KICAgICAgICAgICAgJHtkYXRhLnNhdmU/JzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTBweDtjb2xvcjp2YXIoLS1nb2xkLWRpbSkiPiAoU2F2ZSB2cyAnK2RhdGEuc2F2ZSsnKTwvc3Bhbj4nOicnfQogICAgICAgICAgICAke2RhdGEuZG1nPyc8c3BhbiBzdHlsZT0iZm9udC1zaXplOjEwcHg7Y29sb3I6I2MwOTA0MCI+IFsnK2RhdGEuZG1nKyddPC9zcGFuPic6Jyd9CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNkZXNjIj4ke2RhdGEucmFuZ2V9IHwgJHtkYXRhLmR1cmF0aW9ufSB8ICR7ZGF0YS5kZXNjfTwvZGl2PgogICAgICAgIDwvZGl2PmA7CiAgICB9KTsKICB9KTsKCiAgaWYgKCFib2R5SHRtbCkgewogICAgYm9keUh0bWwgPSAnPGRpdiBzdHlsZT0iY29sb3I6dmFyKC0tdGV4dC1kaW0pO3RleHQtYWxpZ246Y2VudGVyO3BhZGRpbmc6MjBweDsiPk5vIHNwZWxscyBhdmFpbGFibGUgdG8gbWVtb3JpemUgYXQgdGhpcyBsZXZlbC48L2Rpdj4nOwogIH0KCiAgY29uc3QgbW9kYWwgPSBgCiAgICA8ZGl2IGNsYXNzPSJtZW1vcml6ZS1tb2RhbCIgaWQ9Im1lbW9yaXplLW1vZGFsIj4KICAgICAgPGRpdiBjbGFzcz0ibWVtb3JpemUtbW9kYWwtaW5uZXIiPgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtZmFtaWx5OlsuXSdJTSBGZWxsIEVuZ2xpc2hbLl0nLHNlcmlmO2ZvbnQtc2l6ZToyMnB4O2NvbG9yOnZhcigtLWdvbGQpO21hcmdpbi1ib3R0b206NHB4OyI+CiAgICAgICAgICBNZW1vcml6ZSBTcGVsbHM8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTJweDtjb2xvcjp2YXIoLS10ZXh0LWRpbSk7bWFyZ2luLWJvdHRvbToxMnB4OyI+CiAgICAgICAgICBTZWxlY3Qgc3BlbGxzIHRvIGZpbGwgeW91ciBhdmFpbGFibGUgc2xvdHMuICR7dXNlc1NwZWxsYm9vaz8nT25seSBzcGVsbHMgaW4geW91ciBzcGVsbGJvb2sgbWF5IGJlIG1lbW9yaXplZC4nOicnfQogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgaWQ9Im1lbW9yaXplLXNlbGVjdGlvbiI+JHtib2R5SHRtbH08L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tdG9wOjE0cHg7ZGlzcGxheTpmbGV4O2dhcDo4cHg7Ij4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biIgb25jbGljaz0iY29uZmlybU1lbW9yaXplKCkiIHN0eWxlPSJmbGV4OjEiPk1lbW9yaXplIFNlbGVjdGVkPC9idXR0b24+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9ImNsb3NlTWVtb3JpemUoKSIgc3R5bGU9ImZsZXg6MTtiYWNrZ3JvdW5kOnRyYW5zcGFyZW50O2JvcmRlci1jb2xvcjp2YXIoLS1ib3JkZXIpOyI+Q2FuY2VsPC9idXR0b24+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+YDsKICBkb2N1bWVudC5ib2R5Lmluc2VydEFkamFjZW50SFRNTCgnYmVmb3JlZW5kJywgbW9kYWwpOwoKICAvLyBQcmUtc2VsZWN0IGN1cnJlbnRseSBtZW1vcml6ZWQKICBtZW1vcml6ZWRTcGVsbHMuZm9yRWFjaChzID0+IHsKICAgIGNvbnN0IG5hbWUgPSB0eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lOwogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2MtJyArIG5hbWUucmVwbGFjZSgvWy5dcysvZywnLScpKTsKICAgIGlmIChlbCkgZWwuY2xhc3NMaXN0LmFkZCgnc2VsZWN0ZWQnKTsKICB9KTsKfQoKbGV0IF9wZW5kaW5nTWVtb3JpemUgPSBbXTsKZnVuY3Rpb24gdG9nZ2xlTWVtb3JpemVTcGVsbChuYW1lLCBsZXZlbCkgewogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NjLScgKyBuYW1lLnJlcGxhY2UoL1suXXMrL2csJy0nKSk7CiAgaWYgKCFlbCkgcmV0dXJuOwoKICBjb25zdCBpZHggPSBfcGVuZGluZ01lbW9yaXplLmZpbmRJbmRleChzID0+ICh0eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lKT09PW5hbWUpOwogIGlmIChpZHggPj0gMCkgewogICAgX3BlbmRpbmdNZW1vcml6ZS5zcGxpY2UoaWR4LCAxKTsKICAgIGVsLmNsYXNzTGlzdC5yZW1vdmUoJ3NlbGVjdGVkJyk7CiAgfSBlbHNlIHsKICAgIC8vIENoZWNrIHNsb3QgYXZhaWxhYmlsaXR5IGZvciB0aGlzIGxldmVsCiAgICBjb25zdCBzbG90SWR4ID0gbGV2ZWwgLSAxOwogICAgY29uc3QgdXNlZEF0TGV2ZWwgPSBfcGVuZGluZ01lbW9yaXplLmZpbHRlcihzID0+CiAgICAgICgodHlwZW9mIHM9PT0nb2JqZWN0JyYmcy5sZXZlbCl8fEFMTF9TUEVMTF9MRVZFTFNbdHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZV18fDEpID09PSBsZXZlbCkubGVuZ3RoOwogICAgaWYgKHVzZWRBdExldmVsID49IChzcGVsbFNsb3RzVG90YWxbc2xvdElkeF18fDApKSB7CiAgICAgIGFkZEVudHJ5UmF3KCdbTm8gbW9yZSBsZXZlbCAnICsgbGV2ZWwgKyAnIHNsb3RzIGF2YWlsYWJsZV0nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICByZXR1cm47CiAgICB9CiAgICBfcGVuZGluZ01lbW9yaXplLnB1c2goe25hbWUsIGxldmVsfSk7CiAgICBlbC5jbGFzc0xpc3QuYWRkKCdzZWxlY3RlZCcpOwogIH0KfQoKZnVuY3Rpb24gY29uZmlybU1lbW9yaXplKCkgewogIG1lbW9yaXplZFNwZWxscyA9IFsuLi5fcGVuZGluZ01lbW9yaXplXTsKICBfcGVuZGluZ01lbW9yaXplID0gW107CiAgLy8gUmVzZXQgc3BlbGwgc2xvdHMgdG8gdG90YWwgKGZyZXNoIG1lbW9yaXphdGlvbikKICBzcGVsbFNsb3RzUmVtYWluaW5nID0gWy4uLnNwZWxsU2xvdHNUb3RhbF07CiAgY2xvc2VNZW1vcml6ZSgpOwogIHVwZGF0ZVNwZWxsYm9va1BhbmVsKCk7CiAgY29uc3QgbmFtZXMgPSBtZW1vcml6ZWRTcGVsbHMubWFwKHM9PnR5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWUpLmpvaW4oJywgJyk7CiAgYWRkRW50cnlSYXcoJ1tTcGVsbHMgbWVtb3JpemVkOiAnICsgKG5hbWVzfHwnbm9uZScpICsgJ10nLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgpmdW5jdGlvbiBjbG9zZU1lbW9yaXplKCkgewogIGNvbnN0IG0gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtb3JpemUtbW9kYWwnKTsKICBpZiAobSkgbS5yZW1vdmUoKTsKICBfcGVuZGluZ01lbW9yaXplID0gW107Cn0KCi8vIC0tIFNwZWxsYm9vayBsZWFybmluZyAoY2FsbCB3aGVuIHBsYXllciBmaW5kcyBzY3JvbGwgb3IgbGV2ZWxzIHVwKSAtLS0tLS0tLS0tCmZ1bmN0aW9uIGxlYXJuU3BlbGwoc3BlbGxOYW1lLCBzcGVsbERhdGEpIHsKICBzcGVsbEJvb2tbc3BlbGxOYW1lXSA9IHsKICAgIG5hbWU6IHNwZWxsTmFtZSwKICAgIGxldmVsOiBzcGVsbERhdGEubGV2ZWwsCiAgICB0eXBlOiBzcGVsbERhdGEudHlwZSB8fCAnbXUnLAogICAga25vd246IHRydWUsCiAgfTsKICBBTExfU1BFTExfTEVWRUxTW3NwZWxsTmFtZV0gPSBzcGVsbERhdGEubGV2ZWw7CiAgdXBkYXRlU3BlbGxib29rUGFuZWwoKTsKICBhZGRFbnRyeVJhdygnW1NwZWxsIGxlYXJuZWQ6ICcgKyBzcGVsbE5hbWUgKyAnIChMZXZlbCAnICsgc3BlbGxEYXRhLmxldmVsICsgJyldJywgJ3N5c3RlbScsICdfX2dtX18nKTsKfQoKLy8gLS0gQWJpbGl0eSBwYW5lbCB1cGRhdGUgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCmZ1bmN0aW9uIHVwZGF0ZUFiaWxpdHlQYW5lbCgpIHsKICBjb25zdCBwYW5lbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhYmlsaXR5LXBhbmVsJyk7CiAgaWYgKCFwYW5lbCkgcmV0dXJuOwoKICBjb25zdCBhYmlsaXRpZXMgPSBnZXRDbGFzc0FiaWxpdGllc0pTKHBjLmNscywgcGMubGV2ZWwgfHwgMSk7CiAgaWYgKCFhYmlsaXRpZXMubGVuZ3RoKSB7IHBhbmVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7IHJldHVybjsgfQogIHBhbmVsLnN0eWxlLmRpc3BsYXkgPSAnJzsKCiAgbGV0IGh0bWwgPSAnJzsKICBhYmlsaXRpZXMuZm9yRWFjaChhYiA9PiB7CiAgICBjb25zdCB1c2VkVG9kYXkgPSBhYmlsaXR5VXNlc1RvZGF5W2FiLm5hbWVdIHx8IDA7CiAgICBjb25zdCBtYXhVc2VzID0gYWIudXNlcyA9PT0gJ3VubGltaXRlZCcgfHwgYWIudXNlcyA9PT0gJ2F0X3dpbGwnID8gbnVsbCA6CiAgICAgIGFiLnVzZXMgPT09ICdjb25jZW50cmF0aW9uJyA/IG51bGwgOgogICAgICBhYi51c2VzLmVuZHNXaXRoKCdfcGVyX2RheScpID8gcGFyc2VJbnQoYWIudXNlcykgOiBudWxsOwogICAgY29uc3QgZXhoYXVzdGVkID0gbWF4VXNlcyAhPT0gbnVsbCAmJiB1c2VkVG9kYXkgPj0gbWF4VXNlczsKICAgIGNvbnN0IHVzZXNTdHIgPSBtYXhVc2VzICE9PSBudWxsID8gYCAoJHt1c2VkVG9kYXl9LyR7bWF4VXNlc30pYCA6ICcnOwogICAgaHRtbCArPSBgPHNwYW4gY2xhc3M9ImFiaWxpdHktYmFkZ2Uke2V4aGF1c3RlZD8nIGV4aGF1c3RlZCc6Jyd9IgogICAgICBvbmNsaWNrPSJzaG93QWJpbGl0eUluZm8oJyR7YWIubmFtZX0nLCckeyhhYi5kZXNjfHwnJykucmVwbGFjZSgvJy9nLCJbLl1cXCciKX0nKSIKICAgICAgdGl0bGU9IiR7YWIuZGVzY3x8Jyd9Ij4ke2FiLm5hbWV9JHt1c2VzU3RyfTwvc3Bhbj5gOwogIH0pOwogIHBhbmVsLmlubmVySFRNTCA9IGh0bWw7Cn0KCmZ1bmN0aW9uIHNob3dBYmlsaXR5SW5mbyhuYW1lLCBkZXNjKSB7CiAgLy8gU2ltcGxlIHRvb2x0aXAtc3R5bGUgZGlzcGxheSBpbiBsb2cKICBhZGRFbnRyeVJhdyhgPGRpdiBzdHlsZT0iYmFja2dyb3VuZDpyZ2JhKDE4MCwxMzAsMjAsMC4wOCk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1nb2xkLWRpbSk7CiAgICBwYWRkaW5nOjZweCAxMHB4O21hcmdpbjoycHggMDtmb250LXNpemU6MTNweDsiPgogICAgPGIgc3R5bGU9ImNvbG9yOnZhcigtLWdvbGQpIj4ke25hbWV9PC9iPjxicj4KICAgIDxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS10ZXh0LWRpbSkiPiR7ZGVzY308L3NwYW4+PC9kaXY+YCwgJ3N5c3RlbScsICdfX2dtX18nKTsKfQoKLy8gQ2xhc3MgYWJpbGl0aWVzIHRhYmxlIChjbGllbnQtc2lkZSBtaXJyb3Igb2Ygc2VydmVyIGRhdGEpCmZ1bmN0aW9uIGdldENsYXNzQWJpbGl0aWVzSlMoY2xzLCBsZXZlbCkgewogIGNvbnN0IGFsbF9hYmlsaXRpZXMgPSB7CiAgICBGaWdodGVyOiAgIHsgNDpbe25hbWU6J0V4dHJhIEF0dGFjaycsZGVzYzonMyBhdHRhY2tzIHBlciAyIHJvdW5kcycsdXNlczondW5saW1pdGVkJ31dLAogICAgICAgICAgICAgICAgIDg6W3tuYW1lOidFeHRyYSBBdHRhY2snLGRlc2M6JzIgYXR0YWNrcyBwZXIgcm91bmQnLHVzZXM6J3VubGltaXRlZCd9XSB9LAogICAgQ2xlcmljOiAgICB7IDE6W3tuYW1lOidUdXJuIFVuZGVhZCcsZGVzYzonVHVybiB1bmRlYWQgdXNpbmcgMmQ2IHZzIFR1cm4gdGFibGUnLHVzZXM6J3VubGltaXRlZCd9XSB9LAogICAgUGFsYWRpbjogICB7IDE6W3tuYW1lOidEZXRlY3QgRXZpbCcsZGVzYzonRGV0ZWN0IGV2aWwgNjBmdCBhdCB3aWxsJyx1c2VzOidhdF93aWxsJ30sCiAgICAgICAgICAgICAgICAgICAge25hbWU6J0xheSBvbiBIYW5kcycsZGVzYzonSGVhbCAySFAvbGV2ZWwvZGF5Jyx1c2VzOicxX3Blcl9kYXknfSwKICAgICAgICAgICAgICAgICAgICB7bmFtZTonRGlzZWFzZSBJbW11bml0eScsZGVzYzonSW1tdW5lIHRvIGRpc2Vhc2UnLHVzZXM6J3Bhc3NpdmUnfV0sCiAgICAgICAgICAgICAgICAgMzpbe25hbWU6J1R1cm4gVW5kZWFkJyxkZXNjOidUdXJuIHVuZGVhZCBhcyBDbGVyaWMgMiBsZXZlbHMgbG93ZXInLHVzZXM6J3VubGltaXRlZCd9XSB9LAogICAgVGhpZWY6ICAgICB7IDE6W3tuYW1lOidCYWNrc3RhYicsZGVzYzoneDIgZGFtYWdlIGZyb20gaGlkaW5nJyx1c2VzOidwZXJfaGlkZGVuX2F0dGFjayd9XSwKICAgICAgICAgICAgICAgICA1Olt7bmFtZTonQmFja3N0YWInLGRlc2M6J3gzIGJhY2tzdGFiJyx1c2VzOidwZXJfaGlkZGVuX2F0dGFjayd9XSwKICAgICAgICAgICAgICAgICA5Olt7bmFtZTonQmFja3N0YWInLGRlc2M6J3g0IGJhY2tzdGFiJyx1c2VzOidwZXJfaGlkZGVuX2F0dGFjayd9XSB9LAogICAgQXNzYXNzaW46ICB7IDE6W3tuYW1lOidCYWNrc3RhYicsZGVzYzoneDIgYmFja3N0YWInLHVzZXM6J3Blcl9oaWRkZW5fYXR0YWNrJ30sCiAgICAgICAgICAgICAgICAgICAge25hbWU6J0Rpc2d1aXNlJyxkZXNjOidEaXNndWlzZSBzZWxmIChiYXNlIDcwJSknLHVzZXM6J3VubGltaXRlZCd9XSwKICAgICAgICAgICAgICAgICA5Olt7bmFtZTonQXNzYXNzaW5hdGUnLGRlc2M6J0luc3RhbnQga2lsbCBzdXJwcmlzZWQgdGFyZ2V0cycsdXNlczoncGVyX3N1cnByaXNlZF92aWN0aW0nfV0gfSwKICAgIEJhcmJhcmlhbjogeyAxOlt7bmFtZTonUmFnZScsZGVzYzonKzIgYXR0YWNrL2RhbWFnZSwgLTIgQUMgZm9yIDMgcm91bmRzJyx1c2VzOicxX3Blcl9kYXknfSwKICAgICAgICAgICAgICAgICAgICB7bmFtZTonVHJhcCBTZW5zZScsZGVzYzonKzIgc2F2ZXMgdnMgdHJhcHMnLHVzZXM6J3Bhc3NpdmUnfV0sCiAgICAgICAgICAgICAgICAgNDpbe25hbWU6J1JhZ2UnLGRlc2M6J1JhZ2UgMi9kYXknLHVzZXM6JzJfcGVyX2RheSd9XSwKICAgICAgICAgICAgICAgICA3Olt7bmFtZTonUmFnZScsZGVzYzonUmFnZSAzL2RheScsdXNlczonM19wZXJfZGF5J30sCiAgICAgICAgICAgICAgICAgICAge25hbWU6J0ludGltaWRhdGUnLGRlc2M6J0ZlYXIgMS9kYXknLHVzZXM6JzFfcGVyX2RheSd9XSB9LAogICAgUmFuZ2VyOiAgICB7IDE6W3tuYW1lOidUcmFja2luZycsZGVzYzonVHJhY2sgY3JlYXR1cmVzIG91dGRvb3JzJyx1c2VzOid1bmxpbWl0ZWQnfSwKICAgICAgICAgICAgICAgICAgICB7bmFtZTonRmF2b3VyZWQgRW5lbXknLGRlc2M6JysxIGF0dGFjay9kYW1hZ2UgdnMgY2hvc2VuIHR5cGUnLHVzZXM6J3Bhc3NpdmUnfV0gfSwKICAgIERydWlkOiAgICAgeyA3Olt7bmFtZTonU2hhcGVjaGFuZ2UnLGRlc2M6J0FuaW1hbCBmb3JtIDMvZGF5Jyx1c2VzOiczX3Blcl9kYXknfV0gfSwKICAgIEJhcmQ6ICAgICAgeyAxOlt7bmFtZTonSW5zcGlyZSBDb3VyYWdlJyxkZXNjOicrMSBhbGxpZXMgYXR0YWNrL3NhdmVzJyx1c2VzOidjb25jZW50cmF0aW9uJ30sCiAgICAgICAgICAgICAgICAgICAge25hbWU6J0JhcmQgTG9yZScsZGVzYzonS25vdyBsZWdlbmQvaGlzdG9yeSAxLTIvZDYnLHVzZXM6J3VubGltaXRlZCd9XSwKICAgICAgICAgICAgICAgICAyOlt7bmFtZTonQ2hhcm0gUGVyc29uJyxkZXNjOicxL2RheSBhcyBzcGVsbCcsdXNlczonMV9wZXJfZGF5J31dIH0sCiAgICBNb25rOiAgICAgIHsgMTpbe25hbWU6J1N0dW5uaW5nIEF0dGFjaycsZGVzYzonU3R1biBvbiBoaXQgKHNhdmUgdnMgRGVhdGgpJyx1c2VzOicxX3Blcl9yb3VuZCd9XSwKICAgICAgICAgICAgICAgICA3Olt7bmFtZTonV2hvbGVuZXNzIG9mIEJvZHknLGRlc2M6J0hlYWwgMkhQL2xldmVsIDEvZGF5Jyx1c2VzOicxX3Blcl9kYXknfV0gfSwKICB9OwogIGNvbnN0IHRibCA9IGFsbF9hYmlsaXRpZXNbY2xzXSB8fCB7fTsKICBjb25zdCByZXN1bHQgPSBbXTsKICBjb25zdCBzZWVuID0gbmV3IFNldCgpOwogIE9iamVjdC5lbnRyaWVzKHRibCkuc29ydCgoW2FdLFtiXSk9PmEtYikuZm9yRWFjaCgoW3JlcUx2bCwgYWJzXSkgPT4gewogICAgaWYgKHBhcnNlSW50KHJlcUx2bCkgPD0gbGV2ZWwpIHsKICAgICAgYWJzLmZvckVhY2goYWIgPT4gewogICAgICAgIGlmICghc2Vlbi5oYXMoYWIubmFtZSkpIHsgc2Vlbi5hZGQoYWIubmFtZSk7IHJlc3VsdC5wdXNoKGFiKTsgfQogICAgICAgIGVsc2UgewogICAgICAgICAgLy8gUmVwbGFjZSB3aXRoIGhpZ2hlciBsZXZlbCB2ZXJzaW9uCiAgICAgICAgICBjb25zdCBpID0gcmVzdWx0LmZpbmRJbmRleChyID0+IHIubmFtZSA9PT0gYWIubmFtZSk7CiAgICAgICAgICBpZiAoaSA+PSAwKSByZXN1bHRbaV0gPSBhYjsKICAgICAgICB9CiAgICAgIH0pOwogICAgfQogIH0pOwogIHJldHVybiByZXN1bHQ7Cn0KCi8vIFNwZWxsIGRhdGEgZm9yIG1lbW9yaXplIFVJIChtaXJyb3JzIHNlcnZlciBQeXRob24gZGF0YSkKLy8gVGhlc2UgYXJlIGp1c3QgdGhlIG5hbWVzICsgbWV0YWRhdGEgbmVlZGVkIGNsaWVudC1zaWRlCmNvbnN0IE1VX1NQRUxMU19GT1JfQ0xBU1MgPSB7CiAgJ0NoYXJtIFBlcnNvbic6e2xldmVsOjEscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonU3BlY2lhbCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidDaGFybSBvbmUgaHVtYW5vaWQuIFNhdmUgdnMgU3BlbGxzLid9LAogICdEZXRlY3QgTWFnaWMnOntsZXZlbDoxLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RldGVjdCBtYWdpY2FsIGF1cmFzLid9LAogICdGbG9hdGluZyBEaXNjJzp7bGV2ZWw6MSxyYW5nZTonNmZ0JyxkdXJhdGlvbjonNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0hvdmVyaW5nIGRpc2MgY2FycmllcyA1MDAgbGJzLid9LAogICdIb2xkIFBvcnRhbCc6e2xldmVsOjEscmFuZ2U6JzEwZnQnLGR1cmF0aW9uOicyZDYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidIb2xkIGRvb3IvZ2F0ZSBzaHV0Lid9LAogICdMaWdodCc6e2xldmVsOjEscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOic2IHR1cm5zKzEvbHZsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6JzE1ZnQgcmFkaXVzIGxpZ2h0Lid9LAogICdNYWdpYyBNaXNzaWxlJzp7bGV2ZWw6MSxyYW5nZTonMTUwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOicxZDYrMScsZGVzYzonQXV0by1oaXQgbWlzc2lsZS4nfSwKICAnUHJvdGVjdGlvbiBmcm9tIEV2aWwnOntsZXZlbDoxLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzIgdHVybnMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonKzEgQUMgYW5kIHNhdmVzIHZzIGV2aWwuJ30sCiAgJ1JlYWQgTGFuZ3VhZ2VzJzp7bGV2ZWw6MSxyYW5nZTonU2VsZicsZHVyYXRpb246JzEgdHVybicsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlYWQgYW55IGxhbmd1YWdlLid9LAogICdSZWFkIE1hZ2ljJzp7bGV2ZWw6MSxyYW5nZTonU2VsZicsZHVyYXRpb246JzEgdHVybicsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlYWQgbWFnaWNhbCB3cml0aW5ncy4nfSwKICAnU2hpZWxkJzp7bGV2ZWw6MSxyYW5nZTonU2VsZicsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidBQyAyIHZzIG1pc3NpbGVzLCA0IHZzIG1lbGVlLid9LAogICdTbGVlcCc6e2xldmVsOjEscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonNGQ0IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonMmQ4IEhEIG9mIGNyZWF0dXJlcyBmYWxsIGFzbGVlcC4nfSwKICAnVmVudHJpbG9xdWlzbSc6e2xldmVsOjEscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonVGhyb3cgdm9pY2UuJ30sCiAgJ0NvbnRpbnVhbCBMaWdodCc6e2xldmVsOjIscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J1Blcm1hbmVudCBsaWdodCBzcGhlcmUuJ30sCiAgJ0RldGVjdCBFdmlsJzp7bGV2ZWw6MixyYW5nZTonNjBmdCcsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZXRlY3QgZXZpbCBpbnRlbnRpb25zLid9LAogICdEZXRlY3QgSW52aXNpYmxlJzp7bGV2ZWw6MixyYW5nZTonMTBmdC9sdmwnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU2VlIGludmlzaWJsZSBjcmVhdHVyZXMuJ30sCiAgJ0VTUCc6e2xldmVsOjIscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVhZCBzdXJmYWNlIHRob3VnaHRzLid9LAogICdJbnZpc2liaWxpdHknOntsZXZlbDoyLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1VudGlsIGF0dGFjaycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0ludmlzaWJsZSB1bnRpbCBhdHRhY2tpbmcuJ30sCiAgJ0tub2NrJzp7bGV2ZWw6MixyYW5nZTonNjBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidPcGVuIGxvY2tlZCBkb29ycy9jaGVzdHMuJ30sCiAgJ0xldml0YXRlJzp7bGV2ZWw6MixyYW5nZTonMjBmdC9sdmwnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmlzZS9kZXNjZW5kIGF0IDZmdC9yb3VuZC4nfSwKICAnTG9jYXRlIE9iamVjdCc6e2xldmVsOjIscmFuZ2U6JzYwZnQrMTAvbHZsJyxkdXJhdGlvbjonMSByb3VuZCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1NlbnNlIGRpcmVjdGlvbiB0byBvYmplY3QuJ30sCiAgJ01pcnJvciBJbWFnZSc6e2xldmVsOjIscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOicxZDQnLGRlc2M6JzFkNCBpbGx1c29yeSBkdXBsaWNhdGVzLid9LAogICdQaGFudGFzbWFsIEZvcmNlJzp7bGV2ZWw6MixyYW5nZTonMjQwZnQnLGR1cmF0aW9uOidDb25jZW50cmF0aW9uJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0lsbHVzaW9uIHVwIHRvIDIweDIweDIwZnQuJ30sCiAgJ1dlYic6e2xldmVsOjIscmFuZ2U6JzEwZnQnLGR1cmF0aW9uOic0OCB0dXJucycsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidTdGlja3kgd2VicyBlbnRhbmdsZSBjcmVhdHVyZXMuJ30sCiAgJ1dpemFyZCBMb2NrJzp7bGV2ZWw6MixyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidQZXJtYW5lbnRseSBsb2NrIGRvb3IvY2hlc3QuJ30sCiAgJ0NsYWlydm95YW5jZSc6e2xldmVsOjMscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU2VlIHRocm91Z2ggd2FsbHMuJ30sCiAgJ0Rpc3BlbCBNYWdpYyc6e2xldmVsOjMscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlbW92ZSBtYWdpYyBlZmZlY3RzLid9LAogICdGaXJlYmFsbCc6e2xldmVsOjMscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTonU3BlbGxzJyxkbWc6JzFkNi9sdmwnLGRlc2M6JzIwZnQgZXhwbG9zaW9uLid9LAogICdGbHknOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzFkNisxIHR1cm5zL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0ZseSBhdCAxMjBmdC90dXJuLid9LAogICdIYXN0ZSc6e2xldmVsOjMscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonMyB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RvdWJsZSBzcGVlZC9hdHRhY2tzLiBBZ2VzIDEgeWVhci4nfSwKICAnSG9sZCBQZXJzb24nOntsZXZlbDozLHJhbmdlOicxMjBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonMS00IGh1bWFub2lkcyBwYXJhbHlzZWQuJ30sCiAgJ0luZnJhdmlzaW9uJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicxIGRheScsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1NlZSBpbiBkYXJrbmVzcyA2MGZ0Lid9LAogICdJbnZpc2liaWxpdHkgMTBmdCBSYWRpdXMnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1VudGlsIGF0dGFjaycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0FsbCBpbiAxMGZ0IGludmlzaWJsZS4nfSwKICAnTGlnaHRuaW5nIEJvbHQnOntsZXZlbDozLHJhbmdlOidTZWxmJyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTonU3BlbGxzJyxkbWc6JzFkNi9sdmwnLGRlc2M6JzYwZnQgYm9sdC4nfSwKICAnUHJvdGVjdGlvbiBmcm9tIEV2aWwgMTBmdCBSYWRpdXMnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzIgdHVybnMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUHJvdGVjdGlvbiBhdXJhIDEwZnQuJ30sCiAgJ1Byb3RlY3Rpb24gZnJvbSBOb3JtYWwgTWlzc2lsZXMnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzIgdHVybnMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonSW1tdW5lIHRvIG5vbi1tYWdpY2FsIG1pc3NpbGVzLid9LAogICdXYXRlciBCcmVhdGhpbmcnOntsZXZlbDozLHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMSBkYXknLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidCcmVhdGhlIHVuZGVyd2F0ZXIuJ30sCiAgJ0NoYXJtIE1vbnN0ZXInOntsZXZlbDo0LHJhbmdlOicxMjBmdCcsZHVyYXRpb246J1NwZWNpYWwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonQ2hhcm0gYW55IGNyZWF0dXJlIHR5cGUuJ30sCiAgJ0NvbmZ1c2lvbic6e2xldmVsOjQscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonMiByb3VuZHMvbHZsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6JzJkNiBjcmVhdHVyZXMgYWN0IHJhbmRvbWx5Lid9LAogICdEaW1lbnNpb24gRG9vcic6e2xldmVsOjQscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonVGVsZXBvcnQgMzYwZnQgaW5zdGFudGx5Lid9LAogICdHcm93dGggb2YgUGxhbnRzJzp7bGV2ZWw6NCxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZW5zZSBlbnRhbmdsaW5nIHBsYW50cy4nfSwKICAnSWNlIFN0b3JtJzp7bGV2ZWw6NCxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOiczZDEwJyxkZXNjOiczZDEwIGhhaWwgZGFtYWdlLid9LAogICdQb2x5bW9ycGggT3RoZXJzJzp7bGV2ZWw6NCxyYW5nZTonNjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidUcmFuc2Zvcm0gY3JlYXR1cmUuJ30sCiAgJ1BvbHltb3JwaCBTZWxmJzp7bGV2ZWw6NCxyYW5nZTonU2VsZicsZHVyYXRpb246JzYgdHVybnMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonVGFrZSBjcmVhdHVyZSBmb3JtLid9LAogICdSZW1vdmUgQ3Vyc2UnOntsZXZlbDo0LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlbW92ZSBvbmUgY3Vyc2UuJ30sCiAgJ1dhbGwgb2YgRmlyZSc6e2xldmVsOjQscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOidDb25jZW50cmF0aW9uJyxzYXZlOm51bGwsZG1nOicyZDYrMScsZGVzYzonRmlyZSB3YWxsIGRhbWFnZS4nfSwKICAnV2l6YXJkIEV5ZSc6e2xldmVsOjQscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0ludmlzaWJsZSBleWUgc2NvdXRzIGFoZWFkLid9LAogICdBbmltYXRlIERlYWQnOntsZXZlbDo1LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JhaXNlIHVuZGVhZCBzZXJ2YW50cy4nfSwKICAnQ2xvdWRraWxsJzp7bGV2ZWw6NSxyYW5nZTonU2VsZicsZHVyYXRpb246JzEgdHVybicsc2F2ZTonRGVhdGgnLGRtZzpudWxsLGRlc2M6J1BvaXNvbm91cyBjbG91ZCBraWxscyA8NSBIRC4nfSwKICAnQ29uanVyZSBFbGVtZW50YWwnOntsZXZlbDo1LHJhbmdlOicyNDBmdCcsZHVyYXRpb246J0NvbmNlbnRyYXRpb24nLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTdW1tb24gMTYgSEQgZWxlbWVudGFsLid9LAogICdGZWVibGVtaW5kJzp7bGV2ZWw6NSxyYW5nZTonMjQwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6J1NwZWxscy00JyxkbWc6bnVsbCxkZXNjOidJTlQgcmVkdWNlZCB0byAyLid9LAogICdIb2xkIE1vbnN0ZXInOntsZXZlbDo1LHJhbmdlOicxMjBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonMS00IGNyZWF0dXJlcyBwYXJhbHlzZWQuJ30sCiAgJ1Bhc3MtV2FsbCc6e2xldmVsOjUscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOiczIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonVHVubmVsIHRocm91Z2ggc3RvbmUuJ30sCiAgJ1RlbGVraW5lc2lzJzp7bGV2ZWw6NSxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOicyIHJvdW5kcy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidNb3ZlIDIwMCBsYnMvbGV2ZWwuJ30sCiAgJ1RlbGVwb3J0Jzp7bGV2ZWw6NSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonSW5zdGFudCB0cmFuc3BvcnQuJ30sCiAgJ1dhbGwgb2YgU3RvbmUnOntsZXZlbDo1LHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ3JlYXRlIHN0b25lIHdhbGwuJ30sCiAgJ0FudGktTWFnaWMgU2hlbGwnOntsZXZlbDo2LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0Jsb2NrcyBhbGwgbWFnaWMuJ30sCiAgJ0RlYXRoIFNwZWxsJzp7bGV2ZWw6NixyYW5nZTonMjQwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOic0ZDgnLGRlc2M6J1VwIHRvIDRkOCBIRCBkaWUgaW5zdGFudGx5Lid9LAogICdEaXNpbnRlZ3JhdGUnOntsZXZlbDo2LHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidEZXN0cm95IHRhcmdldCB1dHRlcmx5Lid9LAogICdHZWFzJzp7bGV2ZWw6NixyYW5nZTonMzBmdCcsZHVyYXRpb246J1VudGlsIGZ1bGZpbGxlZCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidDb21wZWwgdG8gY29tcGxldGUgcXVlc3QuJ30sCiAgJ0ludmlzaWJsZSBTdGFsa2VyJzp7bGV2ZWw6NixyYW5nZTonU2VsZicsZHVyYXRpb246J1VudGlsIGRvbmUnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTdW1tb24gaHVudGVyLid9LAogICdNb3ZlIEVhcnRoJzp7bGV2ZWw6NixyYW5nZTonMjQwZnQnLGR1cmF0aW9uOic2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonTW92ZSBkaXJ0L2NsYXkuJ30sCiAgJ1JlaW5jYXJuYXRpb24nOntsZXZlbDo2LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JldHVybiBkZWFkIGluIG5ldyBib2R5Lid9LAogICdTdG9uZSB0byBGbGVzaCc6e2xldmVsOjYscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmV2ZXJzZSBwZXRyaWZpY2F0aW9uLid9LAp9OwoKY29uc3QgQ0xFUklDX1NQRUxMU19GT1JfQ0xBU1MgPSB7CiAgJ0N1cmUgTGlnaHQgV291bmRzJzp7bGV2ZWw6MSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6JzFkNisxJyxkZXNjOidSZXN0b3JlIDFkNisxIEhQLid9LAogICdEZXRlY3QgRXZpbCc6e2xldmVsOjEscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOic2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGV0ZWN0IGV2aWwuJ30sCiAgJ0RldGVjdCBNYWdpYyc6e2xldmVsOjEscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGV0ZWN0IG1hZ2ljLid9LAogICdMaWdodCc6e2xldmVsOjEscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOic2IHR1cm5zKzEvbHZsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6JzE1ZnQgcmFkaXVzIGxpZ2h0Lid9LAogICdQcm90ZWN0aW9uIGZyb20gRXZpbCc6e2xldmVsOjEscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMiB0dXJucy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOicrMSBBQy9zYXZlcyB2cyBldmlsLid9LAogICdQdXJpZnkgRm9vZCAmIFdhdGVyJzp7bGV2ZWw6MSxyYW5nZTonMTBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1B1cmlmeSBmb29kL3dhdGVyLid9LAogICdSZW1vdmUgRmVhcic6e2xldmVsOjEscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonU3BlY2lhbCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlbW92ZSBmZWFyIGVmZmVjdC4nfSwKICAnUmVzaXN0IENvbGQnOntsZXZlbDoxLHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6JyszIHNhdmVzIHZzIGNvbGQuJ30sCiAgJ0JsZXNzJzp7bGV2ZWw6MixyYW5nZTonNjBmdCcsZHVyYXRpb246JzYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOicrMSBhdHRhY2sgYW5kIG1vcmFsZS4nfSwKICAnRmluZCBUcmFwcyc6e2xldmVsOjIscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGV0ZWN0IHRyYXBzIDMwZnQuJ30sCiAgJ0hvbGQgUGVyc29uJzp7bGV2ZWw6MixyYW5nZTonMTgwZnQnLGR1cmF0aW9uOic5IHR1cm5zJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6JzEtMyBodW1hbm9pZHMgcGFyYWx5c2VkLid9LAogICdLbm93IEFsaWdubWVudCc6e2xldmVsOjIscmFuZ2U6JzEwZnQnLGR1cmF0aW9uOicxIHJvdW5kJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonTGVhcm4gZXhhY3QgYWxpZ25tZW50Lid9LAogICdSZXNpc3QgRmlyZSc6e2xldmVsOjIscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonKzIgc2F2ZXMgdnMgbWFnaWNhbCBmaXJlLid9LAogICdTaWxlbmNlIDE1ZnQgUmFkaXVzJzp7bGV2ZWw6MixyYW5nZTonMTgwZnQnLGR1cmF0aW9uOicxMiB0dXJucycsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidObyBzb3VuZCBpbiBhcmVhLid9LAogICdTbmFrZSBDaGFybSc6e2xldmVsOjIscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOidTcGVjaWFsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ2hhcm0gMSBIRC9sZXZlbCBvZiBzbmFrZXMuJ30sCiAgJ1NwZWFrIHdpdGggQW5pbWFscyc6e2xldmVsOjIscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOic2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ29tbXVuaWNhdGUgd2l0aCBhbmltYWxzLid9LAogICdDdXJlIERpc2Vhc2UnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0N1cmUgb25lIGRpc2Vhc2UuJ30sCiAgJ0dyb3d0aCBvZiBBbmltYWxzJzp7bGV2ZWw6MyxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOicxMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RvdWJsZSBhbmltYWwgc2l6ZS4nfSwKICAnTG9jYXRlIE9iamVjdCc6e2xldmVsOjMscmFuZ2U6JzkwZnQrMTAvbHZsJyxkdXJhdGlvbjonMSByb3VuZC9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTZW5zZSBkaXJlY3Rpb24gdG8gb2JqZWN0Lid9LAogICdSZW1vdmUgQ3Vyc2UnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlbW92ZSBvbmUgY3Vyc2UuJ30sCiAgJ1N0cmlraW5nJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicxIHR1cm4nLHNhdmU6bnVsbCxkbWc6JzFkNicsZGVzYzonKzFkNiBkYW1hZ2UsIHdlYXBvbiBjb3VudHMgYXMgbWFnaWNhbC4nfSwKICAnQ29udGludWFsIExpZ2h0Jzp7bGV2ZWw6MyxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonUGVybWFuZW50IGxpZ2h0Lid9LAogICdDcmVhdGUgV2F0ZXInOntsZXZlbDo0LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NyZWF0ZSA1MCBnYWwvbGV2ZWwuJ30sCiAgJ0N1cmUgU2VyaW91cyBXb3VuZHMnOntsZXZlbDo0LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzonMmQ2KzInLGRlc2M6J1Jlc3RvcmUgMmQ2KzIgSFAuJ30sCiAgJ05ldXRyYWxpemUgUG9pc29uJzp7bGV2ZWw6NCxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZW1vdmUgcG9pc29uLid9LAogICdQcm90ZWN0aW9uIGZyb20gRXZpbCAxMGZ0IFJhZGl1cyc6e2xldmVsOjQscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMiB0dXJucy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidQcm90ZWN0aW9uIGF1cmEuJ30sCiAgJ1NwZWFrIHdpdGggUGxhbnRzJzp7bGV2ZWw6NCxyYW5nZTonMzBmdCcsZHVyYXRpb246JzMgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDb21tdW5pY2F0ZSB3aXRoIHBsYW50cy4nfSwKICAnU3RpY2tzIHRvIFNuYWtlcyc6e2xldmVsOjQscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6JzJkOCBzdGlja3MgYmVjb21lIHNuYWtlcy4nfSwKICAnVG9uZ3Vlcyc6e2xldmVsOjQscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicxIHR1cm4nLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidVbmRlcnN0YW5kL3NwZWFrIGFueSBsYW5ndWFnZS4nfSwKICAnQ29tbXVuZSc6e2xldmVsOjUscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOiczIHF1ZXN0aW9ucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0FzayBkZWl0eSAzIHllcy9ubyBxdWVzdGlvbnMuJ30sCiAgJ0NyZWF0ZSBGb29kJzp7bGV2ZWw6NSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidGb29kIGZvciAyNCBwZXIgbGV2ZWwuJ30sCiAgJ0N1cmUgQ3JpdGljYWwgV291bmRzJzp7bGV2ZWw6NSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6JzNkNiszJyxkZXNjOidSZXN0b3JlIDNkNiszIEhQLid9LAogICdEaXNwZWwgRXZpbCc6e2xldmVsOjUscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0Rpc3BlbCBldmlsIGNyZWF0dXJlL2VuY2hhbnRtZW50Lid9LAogICdJbnNlY3QgUGxhZ3VlJzp7bGV2ZWw6NSxyYW5nZTonNDgwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU3dhcm0gcm91dHMgPDMgSEQuJ30sCiAgJ1F1ZXN0Jzp7bGV2ZWw6NSxyYW5nZTonMzBmdCcsZHVyYXRpb246J1VudGlsIGZ1bGZpbGxlZCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidDb21wZWwgcXVlc3QgY29tcGxldGlvbi4nfSwKICAnUmFpc2UgRGVhZCc6e2xldmVsOjUscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVzdG9yZSBsaWZlLid9LAogICdUcnVlIFNlZWluZyc6e2xldmVsOjUscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonMSByb3VuZC9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTZWUgaW52aXNpYmxlL2lsbHVzaW9ucy4nfSwKICAnQW5pbWF0ZSBPYmplY3RzJzp7bGV2ZWw6NixyYW5nZTonNjBmdCcsZHVyYXRpb246JzEgcm91bmQvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQW5pbWF0ZSBub24tbGl2aW5nIG9iamVjdHMuJ30sCiAgJ0JsYWRlIEJhcnJpZXInOntsZXZlbDo2LHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMyByb3VuZHMvbHZsJyxzYXZlOm51bGwsZG1nOicyZDYnLGRlc2M6J1dhbGwgb2YgYmxhZGVzIDJkNi4nfSwKICAnRmluZCB0aGUgUGF0aCc6e2xldmVsOjYscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0tub3cgcm91dGUgdG8gZGVzdGluYXRpb24uJ30sCiAgJ1NwZWFrIHdpdGggTW9uc3RlcnMnOntsZXZlbDo2LHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMSByb3VuZC9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDb21tdW5pY2F0ZSB3aXRoIGFueSBjcmVhdHVyZS4nfSwKICAnV29yZCBvZiBSZWNhbGwnOntsZXZlbDo2LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JldHVybiB0byBzYW5jdHVhcnkgaW5zdGFudGx5Lid9LAp9OwoKLy8gRHJ1aWQvUmFuZ2VyL1BhbGFkaW4gdXNlIHN1YnNldCBvZiBDbGVyaWMgc3BlbGxzICsgc29tZSBEcnVpZC1zcGVjaWZpYwpjb25zdCBEUlVJRF9TUEVMTFNfRk9SX0NMQVNTID0gewogICdBbmltYWwgRnJpZW5kc2hpcCc6e2xldmVsOjEscmFuZ2U6JzEwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonQmVmcmllbmQgbm9ybWFsIGFuaW1hbC4nfSwKICAnRGV0ZWN0IE1hZ2ljJzp7bGV2ZWw6MSxyYW5nZTonNjBmdCcsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZXRlY3QgbWFnaWMuJ30sCiAgJ0VudGFuZ2xlJzp7bGV2ZWw6MSxyYW5nZTonODBmdCcsZHVyYXRpb246JzEgdHVybicsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidQbGFudHMgZ3Jhc3AgY3JlYXR1cmVzLid9LAogICdGYWVyaWUgRmlyZSc6e2xldmVsOjEscmFuZ2U6JzgwZnQnLGR1cmF0aW9uOic0IHJvdW5kcy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidPdXRsaW5lIGNyZWF0dXJlcywgLTIgQUMuJ30sCiAgJ1B1cmlmeSBXYXRlcic6e2xldmVsOjEscmFuZ2U6JzQwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidQdXJpZnkgMSBjdSBmdC9sZXZlbC4nfSwKICAnU3BlYWsgd2l0aCBBbmltYWxzJzp7bGV2ZWw6MSxyYW5nZTonMzBmdCcsZHVyYXRpb246JzYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDb21tdW5pY2F0ZSB3aXRoIGFuaW1hbHMuJ30sCiAgJ0Jhcmtza2luJzp7bGV2ZWw6MixyYW5nZTonVG91Y2gnLGR1cmF0aW9uOic0IHJvdW5kcysxL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0FDIGJlY29tZXMgNiBtaW4uJ30sCiAgJ0N1cmUgTGlnaHQgV291bmRzJzp7bGV2ZWw6MixyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6JzFkNisxJyxkZXNjOidSZXN0b3JlIDFkNisxIEhQLid9LAogICdIZWF0IE1ldGFsJzp7bGV2ZWw6MixyYW5nZTonNDBmdCcsZHVyYXRpb246Jzcgcm91bmRzJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonTWV0YWwgaGVhdHMgZGFuZ2Vyb3VzbHkuJ30sCiAgJ1Byb2R1Y2UgRmxhbWUnOntsZXZlbDoyLHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMSByb3VuZC9sdmwnLHNhdmU6bnVsbCxkbWc6JzFkNCsxJyxkZXNjOidGbGFtZSB3ZWFwb24gb3IgbWlzc2lsZS4nfSwKICAnQ2FsbCBMaWdodG5pbmcnOntsZXZlbDozLHJhbmdlOiczNjBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6J1NwZWxscycsZG1nOicyZDgrbHZsJyxkZXNjOidMaWdodG5pbmcgMS9yb3VuZCBvdXRkb29ycy4nfSwKICAnQ3VyZSBEaXNlYXNlJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDdXJlIGRpc2Vhc2UuJ30sCiAgJ0hvbGQgQW5pbWFsJzp7bGV2ZWw6MyxyYW5nZTonODBmdCcsZHVyYXRpb246JzIgcm91bmRzL2x2bCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOicxLTQgYW5pbWFscyBwYXJhbHlzZWQuJ30sCiAgJ1BsYW50IEdyb3d0aCc6e2xldmVsOjMscmFuZ2U6JzE2MGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGVuc2UgaW1wYXNzYWJsZSB2ZWdldGF0aW9uLid9LAogICdQcm90ZWN0aW9uIGZyb20gRmlyZSc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonU3BlY2lhbCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0Fic29yYnMgMTIgcG9pbnRzL2x2bCBmaXJlLid9LAogICdXYXRlciBCcmVhdGhpbmcnOntsZXZlbDozLHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMSBkYXknLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidCcmVhdGhlIHdhdGVyLid9LAogICdEaXNwZWwgTWFnaWMnOntsZXZlbDo0LHJhbmdlOicxMjBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZW1vdmUgbWFnaWMuJ30sCiAgJ05ldXRyYWxpemUgUG9pc29uJzp7bGV2ZWw6NCxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZW1vdmUgcG9pc29uLid9LAogICdDdXJlIFNlcmlvdXMgV291bmRzJzp7bGV2ZWw6NCxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6JzJkNisyJyxkZXNjOidSZXN0b3JlIDJkNisyIEhQLid9LAogICdJbnNlY3QgUGxhZ3VlJzp7bGV2ZWw6NSxyYW5nZTonNDgwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonSW5zZWN0IHN3YXJtLid9LAogICdUcmFuc211dGUgUm9jayB0byBNdWQnOntsZXZlbDo1LHJhbmdlOicxNjBmdCcsZHVyYXRpb246JzNkNiBkYXlzJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonVHVybiByb2NrIHRvIG11ZC4nfSwKICAnQ29tbXVuZSB3aXRoIE5hdHVyZSc6e2xldmVsOjUscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonS25vdyB0ZXJyYWluIDEgbWlsZS9sZXZlbC4nfSwKICAnQ3VyZSBDcml0aWNhbCBXb3VuZHMnOntsZXZlbDo2LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzonM2Q2KzMnLGRlc2M6J1Jlc3RvcmUgM2Q2KzMgSFAuJ30sCiAgJ0NvbnRyb2wgV2VhdGhlcic6e2xldmVsOjYscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOic0ZDEyIGhvdXJzJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ29udHJvbCBsb2NhbCB3ZWF0aGVyLid9LAp9OwoKY29uc3QgUkFOR0VSX1NQRUxMU19GT1JfQ0xBU1MgPSBPYmplY3QuZnJvbUVudHJpZXMoCiAgT2JqZWN0LmVudHJpZXMoRFJVSURfU1BFTExTX0ZPUl9DTEFTUykuZmlsdGVyKChbLHZdKT0+di5sZXZlbDw9MykKKTsKY29uc3QgQkFSRF9TUEVMTFNfRk9SX0NMQVNTID0gT2JqZWN0LmZyb21FbnRyaWVzKAogIE9iamVjdC5lbnRyaWVzKENMRVJJQ19TUEVMTFNfRk9SX0NMQVNTKS5maWx0ZXIoKFssdl0pPT52LmxldmVsPD0zKQopOwoKLy8gUG9wdWxhdGUgQUxMX1NQRUxMX0xFVkVMUyBsb29rdXAKW01VX1NQRUxMU19GT1JfQ0xBU1MsIENMRVJJQ19TUEVMTFNfRk9SX0NMQVNTLCBEUlVJRF9TUEVMTFNfRk9SX0NMQVNTXS5mb3JFYWNoKHRibCA9PiB7CiAgT2JqZWN0LmVudHJpZXModGJsKS5mb3JFYWNoKChbbmFtZSxkYXRhXSkgPT4gewogICAgQUxMX1NQRUxMX0xFVkVMU1tuYW1lXSA9IGRhdGEubGV2ZWw7CiAgfSk7Cn0pOwoKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIEdBTUUgSU5JVCBPVkVSUklERVMgRk9SIFY0Ci8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQoKLy8gQ2FsbGVkIGFmdGVyIGJlZ2luQWR2ZW50dXJlIC8gbGF1bmNoR2FtZSB0byBpbml0IFY0IHN0YXRlCmZ1bmN0aW9uIGluaXRWNFN0YXRlKCkgewogIC8vIEluaXQgc3BlbGwgc2xvdHMgZnJvbSBjbGFzcy9sZXZlbAogIGNvbnN0IHNsb3RzID0gZ2V0U3BlbGxTbG90c0pTKHBjLmNscywgcGMubGV2ZWwgfHwgMSk7CiAgc3BlbGxTbG90c1RvdGFsID0gc2xvdHM7CiAgc3BlbGxTbG90c1JlbWFpbmluZyA9IFsuLi5zbG90c107CgogIC8vIENsZXJpY3MvRHJ1aWRzIHN0YXJ0IHdpdGggYWxsIHNwZWxscyBhdmFpbGFibGUgKG5vIHNwZWxsYm9vayBuZWVkZWQpCiAgaWYgKFsnQ2xlcmljJywnRHJ1aWQnLCdSYW5nZXInLCdQYWxhZGluJ10uaW5jbHVkZXMocGMuY2xzKSkgewogICAgc3BlbGxCb29rID0ge307IC8vIFRoZXkgcHJheSBmb3Igc3BlbGxzLCBubyBib29rIG5lZWRlZAogIH0KICAvLyBNVS9JbGx1c2lvbmlzdCBnZXQgc3RhcnRpbmcgc3BlbGxzIChSZWFkIE1hZ2ljICsgMSByYW5kb20gbGV2ZWwgMSBzcGVsbCkKICBpZiAoWydNYWdpYy1Vc2VyJywnSWxsdXNpb25pc3QnXS5pbmNsdWRlcyhwYy5jbHMpKSB7CiAgICBsZWFyblNwZWxsKCdSZWFkIE1hZ2ljJywge2xldmVsOjEsIHR5cGU6J211J30pOwogICAgLy8gUGljayBhIHN0YXJ0aW5nIHNwZWxsIGZyb20gbGV2ZWwgMQogICAgY29uc3QgbGV2ZWwxID0gT2JqZWN0LmVudHJpZXMoTVVfU1BFTExTX0ZPUl9DTEFTUykuZmlsdGVyKChbLHZdKT0+di5sZXZlbD09PTEpOwogICAgaWYgKGxldmVsMS5sZW5ndGggPiAwKSB7CiAgICAgIGNvbnN0IFtzdGFydFNwZWxsLCBzdGFydERhdGFdID0gbGV2ZWwxW01hdGguZmxvb3IoTWF0aC5yYW5kb20oKSpsZXZlbDEubGVuZ3RoKV07CiAgICAgIGxlYXJuU3BlbGwoc3RhcnRTcGVsbCwge2xldmVsOjEsIHR5cGU6J211J30pOwogICAgfQogIH0KCiAgaW5Db21iYXQgPSBmYWxzZTsKICBwbGF5ZXJIaWRkZW4gPSBmYWxzZTsKICBjdXJyZW50TlBDcyA9IFtdOwogIGFjdGl2ZUVmZmVjdHNWNCA9IFtdOwogIGFiaWxpdHlVc2VzVG9kYXkgPSB7fTsKCiAgdXBkYXRlU3BlbGxib29rUGFuZWwoKTsKICB1cGRhdGVBYmlsaXR5UGFuZWwoKTsKfQoKLy8gU3BlbGwgc2xvdCB0YWJsZSBKUyBtaXJyb3IgKG1hdGNoZXMgc2VydmVyIFB5dGhvbiBkYXRhKQpmdW5jdGlvbiBnZXRTcGVsbFNsb3RzSlMoY2xzLCBsZXZlbCkgewogIGNvbnN0IHRhYmxlcyA9IHsKICAgICdNYWdpYy1Vc2VyJzogIFtbMV0sWzJdLFsyLDFdLFsyLDJdLFsyLDIsMV0sWzIsMiwyXSxbMywyLDIsMV0sWzMsMywyLDJdLFszLDMsMywyLDFdLFszLDMsMywzLDJdLFs0LDMsMywzLDIsMV0sWzQsNCwzLDMsMywyXSxbNCw0LDQsMywzLDNdLFs0LDQsNCw0LDQsNF1dLAogICAgJ0lsbHVzaW9uaXN0JzogW1sxXSxbMl0sWzIsMV0sWzIsMl0sWzMsMiwxXSxbMywyLDJdLFszLDMsMiwxXSxbMywzLDMsMl0sWzQsMywzLDIsMV0sWzQsNCwzLDMsMl0sWzQsNCw0LDMsMiwxXSxbNCw0LDQsNCwzLDJdLFs1LDUsNCw0LDMsM10sWzUsNSw1LDQsNCw0XV0sCiAgICAnQ2xlcmljJzogICAgICBbWzFdLFsyXSxbMiwxXSxbMywyXSxbMywzLDFdLFszLDMsMl0sWzMsMywyLDFdLFszLDMsMywyXSxbNCw0LDMsMiwxXSxbNCw0LDMsMywyXSxbNSw0LDQsMywyLDFdLFs1LDUsNCw0LDMsMl0sWzUsNSw1LDQsMywzXSxbNiw1LDUsNSw0LDRdXSwKICAgICdEcnVpZCc6ICAgICAgIFtbMV0sWzJdLFsyLDFdLFszLDJdLFszLDMsMV0sWzMsMywyXSxbMywzLDIsMV0sWzMsMywzLDJdLFs0LDQsMywyLDFdLFs0LDQsMywzLDJdLFs1LDQsNCwzLDIsMV0sWzUsNSw0LDQsMywyXSxbNSw1LDUsNCwzLDNdLFs2LDUsNSw1LDQsNF1dLAogICAgJ1Jhbmdlcic6ICAgICAgW1tdLFtdLFtdLFtdLFtdLFtdLFtdLFsxXSxbMSwxXSxbMiwxXSxbMiwyXSxbMiwyLDFdLFszLDIsMV0sWzMsMiwyXV0sCiAgICAnUGFsYWRpbic6ICAgICBbW10sW10sW10sW10sW10sW10sW10sW10sWzFdLFsyXSxbMiwxXSxbMiwyXSxbMywyXSxbMywzXV0sCiAgfTsKICBjb25zdCB0YmwgPSB0YWJsZXNbY2xzXTsKICBpZiAoIXRibCkgcmV0dXJuIFtdOwogIGNvbnN0IGlkeCA9IE1hdGgubWluKChsZXZlbHx8MSktMSwgdGJsLmxlbmd0aC0xKTsKICByZXR1cm4gWy4uLnRibFtpZHhdXTsKfQoKLy8gUmVzZXQgYWJpbGl0eSB1c2VzIGRhaWx5IChjYWxsIG9uIGZ1bGwgcmVzdCkKZnVuY3Rpb24gcmVzZXREYWlseUFiaWxpdGllcygpIHsKICBhYmlsaXR5VXNlc1RvZGF5ID0ge307CiAgdXBkYXRlQWJpbGl0eVBhbmVsKCk7Cn0KCgovLyAtLSBTdGFydHVwIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCndpbmRvdy5hZGRFdmVudExpc3RlbmVyKCdET01Db250ZW50TG9hZGVkJywgKCkgPT4gewogIHNob3coJ3MtbG9iYnknKTsKICBjaGVja09sbGFtYVN0YXR1cygpOwogIGNoZWNrTmdyb2tTdGF0dXMoKTsKICByb3RhdGVCYW5uZWRQaHJhc2VzKCk7CiAgc2V0SW50ZXJ2YWwocm90YXRlQmFubmVkUGhyYXNlcywgNjAwMDApOwogIHNldEludGVydmFsKHRpY2tFZmZlY3RzLCAxMDAwKTsKICBjb25zdCBwbmkgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGxheWVyLW5hbWUtaW5wJyk7CiAgaWYgKHBuaSkgcG5pLmFkZEV2ZW50TGlzdGVuZXIoJ2tleWRvd24nLCBlID0+IHsgaWYoZS5rZXk9PT0nRW50ZXInKSBnb0hvbWUoKTsgfSk7CiAgY29uc3QgY21kID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpOwogIGlmIChjbWQpIGNtZC5hZGRFdmVudExpc3RlbmVyKCdrZXlkb3duJywgZSA9PiB7IGlmKGUua2V5PT09J0VudGVyJyAmJiAhZS5zaGlmdEtleSkgeyBlLnByZXZlbnREZWZhdWx0KCk7IHNlbmQoKTsgfSB9KTsKICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCdrZXlkb3duJywgZSA9PiB7CiAgICBpZiAoZS5rZXkgPT09ICdFc2NhcGUnKSB7CiAgICAgIGNvbnN0IG0gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtb3JpemUtbW9kYWwnKSB8fCBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbHYtbW9kYWwnKTsKICAgICAgaWYgKG0pIG0ucmVtb3ZlKCk7CiAgICB9CiAgfSk7Cn0pOwoKLy8gVjQgc3RhdGUgaW5pdCBpcyBjYWxsZWQgZGlyZWN0bHkgZnJvbSBiZWdpbkFkdmVudHVyZSBhbmQgbGF1bmNoR2FtZQo="

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
    <span id="top-logo" style="font-family:'IM Fell English',serif;color:var(--gold);font-size:14px;">D&amp;D v4.0</span>
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
    # Keep console open on crash so errors are visible
    import sys as _sys
    _orig_excepthook = _sys.excepthook
    def _crash_hook(exc_type, exc_val, exc_tb):
        _orig_excepthook(exc_type, exc_val, exc_tb)
        input("\n[Crashed] Press Enter to close...")
    _sys.excepthook = _crash_hook

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
    import os as _os, sys as _sys, traceback as _tb

    # Keep window open on any crash so error is visible
    try:
        # Always run from the DnDAdventure folder
        _home_dir = _os.path.join(_os.path.expanduser('~'), 'Documents', 'DnDAdventure')
        _os.makedirs(_home_dir, exist_ok=True)
        _os.chdir(_home_dir)

        _check_and_update()  # Check GitHub for newer version
        main()

    except Exception as _e:
        print("\n" + "="*60)
        print("STARTUP ERROR -- please report this:")
        print("="*60)
        _tb.print_exc()
        print("="*60)
        input("\nPress Enter to close...")
        _sys.exit(1)
