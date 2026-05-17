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
VERSION = "4.2"

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
    """Master validator. Runs all Layer 1 checks. Returns ValidationResult."""
    text_lower = text.lower().strip()

    # 0a. NPC CONTROL CHECK
    npc_control = _check_npc_control(text_lower, pc, game_state)
    if npc_control:
        return ValidationResult(False, rejection=npc_control)

    # 0b. PARSE CONFIDENCE CHECK
    parse_fail = _check_parse_confidence(text_lower)
    if parse_fail:
        return ValidationResult(False, rejection=parse_fail)

    # 1. SPELL CASTING CHECK
    spell_detected = _detect_spell_action(text_lower)
    if spell_detected:
        return _validate_spell(spell_detected, pc, game_state, text_lower)

    # 2. ATTACK CHECK
    attack_detected = _detect_attack_action(text_lower)
    if attack_detected:
        return _validate_attack(attack_detected, pc, game_state, text_lower)

    # 3. ITEM USE CHECK
    item_detected = _detect_item_action(text_lower)
    if item_detected:
        return _validate_item(item_detected, pc, game_state)

    # 4. THIEF SKILL CHECK
    skill_detected = _detect_skill_action(text_lower)
    if skill_detected:
        return _validate_skill(skill_detected, pc, game_state)

    # 5. CLASS ABILITY CHECK
    ability_detected = _detect_ability_action(text_lower, pc)
    if ability_detected:
        return _validate_ability(ability_detected, pc, game_state)

    # 6. LAYERED PHYSICS CHECK (A/B/C)
    physics_fail = _check_physics_layered(text_lower, pc, game_state)
    if physics_fail:
        return ValidationResult(False, rejection=physics_fail)

    # 7. PHYSICALLY IMPOSSIBLE ACTIONS (legacy list)
    impossible = _check_physically_impossible(text_lower, pc, game_state)
    if impossible:
        return ValidationResult(False, rejection=impossible)

    # 8. MODULE CLOSED WORLD CHECK
    world_violation = _check_closed_world(text_lower, game_state)
    if world_violation:
        return ValidationResult(False, rejection=world_violation)

    # 9. Default: pass to AI for classification
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
# ── NPC CONTROL CHECK ────────────────────────────────────────────────────────
def _check_npc_control(text, pc, game_state):
    """
    Reject inputs where the player is declaring what an NPC/monster does
    rather than what their own character does.
    Patterns: "the goblin runs", "goblin attacks", "the guard opens", etc.
    """
    pc_name = pc.get('name','').lower()

    # Build list of known entity names in this encounter/room
    enc = game_state.get('current_encounter',{})
    monster_names = [m.get('name','').lower() for m in enc.get('monsters',[])]
    npc_names = [n.get('name','').lower() if isinstance(n,dict) else n.lower()
                 for n in game_state.get('npcs_present',[])]
    known_entities = monster_names + npc_names

    # Generic creature/NPC subject patterns
    # Catches: "the goblin runs", "goblin attacks me", "the guard lets me in"
    import re as _re
    # Match "[the] <creature> <verb>" at start or after comma
    creature_subject_pat = _re.compile(
        r'(?:^|,\s*)'
        r'(?:the\s+)?'
        r'(goblin|orc|troll|guard|innkeeper|merchant|wizard|priest|bandit|'
        r'soldier|knight|peasant|farmer|thief|assassin|dragon|skeleton|'
        r'zombie|ghoul|ghost|vampire|werewolf|demon|devil|giant|ogre|gnoll|'
        r'hobgoblin|kobold|lizardman|minotaur|harpy|basilisk|creature|monster|'
        r'enemy|npc|man|woman|figure|person|villager)'
        r'\s+(?:runs?|flees?|fled|attacks?|attacked|moves?|moved|goes?|went|'
        r'opens?|opened|gives?|gave|drops?|dropped|falls?|fell|dies?|died|'
        r'surrenders?|surrendered|lets?\s+me|allows?|agrees?|agreed|tells?\s+me|'
        r'says?|said|picks?\s+up|takes?|took|runs?\s+away|escapes?|escaped)'
    )

    # Also check if any known entity name is the subject
    if known_entities:
        for ename in known_entities:
            if not ename: continue
            # Pattern: "[the] <name> <verb>"
            ename_pat = _re.compile(
                r'(?:^|,\s*)(?:the\s+)?' + _re.escape(ename) +
                r'\s+(?:runs?|flees?|fled|attacks?|attacked|moves?|moved|goes?|went|'
                r'opens?|opened|gives?|gave|drops?|dropped|falls?|fell|dies?|died|'
                r'surrenders?|surrendered|lets?\s+me|allows?|agrees?|agreed)'
            )
            if ename_pat.search(text):
                return (f"You can only control {pc.get('name','your character')}. "
                        f"Declare what you do — not what the {ename} does.")

    m = creature_subject_pat.search(text)
    if m:
        creature = m.group(1)
        # Make sure the PC name isn't the subject (e.g. "Brevik runs north" is fine)
        if creature.lower() != pc_name:
            return (f"You can only control {pc.get('name','your character')}. "
                    f"Declare what you do — not what the {creature} does.")

    return None


# ── PHYSICS / PLAUSIBILITY CHECK (Layers A/B/C) ───────────────────────────────
# Layer A: Can a normal human do this unaided?
# Layer B: Does character have equipment with the needed property + within limits?
# Layer C: Does character have a valid memorised spell/ability for this?


# ── NPC CONTROL CHECK ────────────────────────────────────────────────────────
import re as _re_val

NPC_SUBJECT_WORDS = [
    'goblin', 'orc', 'troll', 'dragon', 'skeleton', 'zombie', 'ghoul',
    'guard', 'soldier', 'bandit', 'brigand', 'thug', 'knight',
    'creature', 'monster', 'enemy', 'beast', 'demon', 'devil',
    'wizard', 'mage', 'priest', 'merchant', 'innkeeper', 'king', 'queen',
]

NPC_ACTION_VERBS = [
    'runs away', 'flees', 'attacks', 'surrenders', 'retreats', 'drops',
    'gives up', 'falls down', 'dies', 'walks away', 'backs off',
    'gives me', 'hands over', 'jumps', 'shoots', 'stabs', 'leaves',
]

def _check_npc_control(text, pc, game_state):
    """Reject if player declares actions for NPCs/monsters instead of their PC."""
    pc_name = pc.get('name', '').lower()
    stripped = text.strip()
    # Allow if starts with "I " or PC name
    if stripped.startswith('i ') or stripped.startswith("i'"):
        return None
    if pc_name and stripped.startswith(pc_name):
        return None
    # Check for "[npc] [action_verb]" pattern
    for npc_word in NPC_SUBJECT_WORDS:
        if stripped.startswith('the ' + npc_word + ' ') or stripped.startswith(npc_word + ' '):
            for verb in NPC_ACTION_VERBS:
                if verb in stripped:
                    return (f"You can only control {pc.get('name','your character')}. "
                            f"Declare what you do, not what other creatures do.")
    # Regex: "the <creature> <verb>s" at start of sentence
    m = _re_val.match(r'^the\s+(\w+(?:\s+\w+)?)\s+(runs?|flees?|attacks?|dies?|surrenders?|retreats?|drops?|falls?)', stripped)
    if m:
        return (f"You can only control {pc.get('name','your character')}. "
                f"Declare what you do, not what other creatures do.")
    return None


# ── PARSE CONFIDENCE CHECK ────────────────────────────────────────────────────
PARSE_WHITELIST = {
    'wait', 'do nothing', 'nothing', 'pass', 'hold', 'stand ground',
    'stand my ground', 'watch', 'watch and wait', 'hold my action',
    'hold action', 'stay', 'stay here', 'continue', 'look around',
    'look', 'listen', 'search', '...', 'ok', 'yes', 'no',
}

AMBIGUOUS_PHRASES = {
    'i go for it', 'i try', 'i do it', 'i do the thing', 'do it',
    'i use it', 'i grab it', 'i take it', 'i attack it', 'i hit it',
    'i get it', 'let us go', 'lets go', 'do something', 'i dunno',
    'i try something', 'something', 'anything', 'whatever',
}

KNOWN_SHORT_KEYWORDS = [
    'attack', 'cast', 'run', 'flee', 'hide', 'sneak', 'search',
    'rest', 'drink', 'use', 'open', 'close', 'north', 'south',
    'east', 'west', 'up', 'down', 'yes', 'no', 'ok', 'help',
    'shoot', 'throw', 'move', 'go', 'examine', 'look',
]

def _check_parse_confidence(text):
    """Return clarification request if input is too vague to parse."""
    stripped = text.strip().rstrip('.!?')
    if stripped in PARSE_WHITELIST:
        return None
    if stripped.startswith('i ') or stripped.startswith("i'"):
        return None
    if stripped in AMBIGUOUS_PHRASES:
        return ("Unable to parse your action. Please be more specific — e.g. "
                "'I attack the goblin with my axe', 'I move east', or 'I search the room'.")
    words = stripped.split()
    if len(words) <= 2 and stripped not in PARSE_WHITELIST:
        if not any(k in stripped for k in KNOWN_SHORT_KEYWORDS):
            return ("Unable to parse your action. Please be more specific about what you want to do.")
    return None


# ── LAYERED PHYSICS CHECK (A/B/C) ────────────────────────────────────────────
PHYSICS_CHECKS = [
    {
        'triggers': ['jump 40', 'jump 50', 'jump 60', 'jump 100', 'leap 40',
                     'leap 50', 'leap 100', 'soar through',
                     'land on the creature from', 'drop from 40', 'drop from 50',
                     'jump over the building', 'jump over the castle'],
        'human_ok': False,
        'equipment_fn': None,
        'spell_fn': lambda pc, gs: _has_flight(pc, gs),
        'rejection': ("That jump is far beyond human capability. "
                      "A normal person can jump roughly 5-6 feet. "
                      "Without a Fly or Levitate spell that is not possible."),
    },
    {
        'triggers': ['holy water grenade', 'make a grenade', 'make a bomb',
                     'explosive potion', 'create a bomb', 'alchemical bomb'],
        'human_ok': False,
        'equipment_fn': None,
        'spell_fn': None,
        'rejection': ("You cannot improvise explosives from your equipment. "
                      "Holy water damages undead on direct contact — it has no explosive property. "
                      "Alchemical explosives do not exist in OSE Advanced Fantasy."),
    },
    {
        'triggers': ['grow taller', 'shrink down', 'become tiny',
                     'change my size', 'make myself bigger', 'make myself smaller',
                     'grow to 50', 'grow to 100', 'grow 50 feet', 'grow 100 feet'],
        'human_ok': False,
        'equipment_fn': None,
        'spell_fn': lambda pc, gs: _has_polymorph(pc, gs),
        'rejection': ("You cannot change your size without a Polymorph Self spell "
                      "or a magical item granting that effect."),
    },
    {
        'triggers': ['scale the sheer wall without', 'climb the smooth stone wall',
                     'climb the cliff without rope', 'climb straight up the stone wall'],
        'human_ok': False,
        'equipment_fn': lambda pc, gs: _has_climb_equipment(pc),
        'spell_fn': lambda pc, gs: _has_climb_spell(pc, gs),
        'rejection': ("Climbing a sheer stone surface requires equipment "
                      "(rope and grappling hook, or iron spikes) or a Spider Climb spell. "
                      "You have neither."),
    },
]

def _has_climb_equipment(pc):
    inv_lower = [i.lower() if isinstance(i, str) else i.get('name','').lower()
                 for i in pc.get('inv', [])]
    return any(item in ' '.join(inv_lower) for item in
               ['grappling hook', 'iron spikes', 'rope'])

def _has_climb_spell(pc, gs):
    memorized = [s if isinstance(s, str) else s.get('name','')
                 for s in pc.get('memorized_spells', [])]
    return 'Spider Climb' in memorized

def _has_polymorph(pc, gs):
    memorized = [s if isinstance(s, str) else s.get('name','')
                 for s in pc.get('memorized_spells', [])]
    return any(s in memorized for s in ['Polymorph Self', 'Polymorph Others'])

def _check_physics_layered(text, pc, game_state):
    """Layer A/B/C physics plausibility check."""
    for check in PHYSICS_CHECKS:
        triggered = any(t in text for t in check['triggers'])
        if not triggered:
            continue
        if check['human_ok']:
            return None
        eq_fn = check.get('equipment_fn')
        if eq_fn and eq_fn(pc, game_state):
            return None
        sp_fn = check.get('spell_fn')
        if sp_fn and sp_fn(pc, game_state):
            return None
        return check['rejection']
    return None


IMPOSSIBLE_ACTIONS = [
    # Flight
    (['fly ','soar','float in air'],
     lambda pc,gs: not _has_flight(pc,gs),
     "cannot fly without a Fly spell, Levitate spell, Potion of Flying, or magical item granting flight."),
    # Levitate specifically (spell exists so check separately)
    (['levitate'],
     lambda pc,gs: not _has_flight(pc,gs),
     "cannot levitate without a Levitate spell or Potion of Flying."),
    # Water breathing
    (['breathe underwater','breathe water'],
     lambda pc,gs: not _has_water_breathing(pc,gs),
     "cannot breathe underwater without Water Breathing spell or a magical item."),
    # Invisibility
    (['become invisible','turn invisible','go invisible'],
     lambda pc,gs: not _has_invisibility(pc,gs),
     "cannot become invisible without an Invisibility spell, Potion of Invisibility, or Ring of Invisibility."),
    # Size change
    (['grow 50 feet','grow 100 feet','become giant','grow enormous',
      'grow 10 feet','grow 20 feet','shrink to','become tiny','become microscopic'],
     lambda pc,gs: True,
     "cannot change size. No spell or item with that effect is available."),
    # Superhuman jumps — Layer A fail, check Layer B/C via separate function
    (['jump 40','jump 50','jump 30','jump 20 feet','leap 40','leap 50',
      'jump over the wall','jump to the ceiling','jump to the roof',
      'leap across the chasm','jump the entire'],
     lambda pc,gs: not _has_superhuman_jump(pc,gs),
     "cannot jump that far. A normal human can jump roughly 10 feet horizontally "
     "or 3-4 feet vertically unaided. You have no spell or item that changes this."),
    # Summoning beyond scope
    (['summon a god','summon demon','summon devil','call upon god',
      'summon angel','invoke deity','meteor','call down fire from sky'],
     lambda pc,gs: True,
     "is not capable of that. Such powers are beyond mortal reach in OSE Advanced Fantasy."),
    # Teleport
    (['teleport','blink away','dimension hop'],
     lambda pc,gs: not _has_teleport(pc,gs),
     "cannot teleport without Dimension Door spell, Teleport spell, or a magical item granting teleportation."),
    # Walking through solid objects
    (['walk through the wall','phase through','pass through solid',
      'walk through solid','melt through'],
     lambda pc,gs: True,
     "cannot pass through solid matter. No spell or ability available grants that."),
]

# ── Inventory property helpers for Layer B ────────────────────────────────────
def _inv_has(pc, *keywords):
    """Check if inventory contains an item matching any keyword."""
    inv = [i.lower() if isinstance(i,str) else i.get('name','').lower()
           for i in pc.get('inv',[])]
    return any(any(kw in item for kw in keywords) for item in inv)

def _has_flight(pc, gs):
    effects = pc.get('active_effects',[])
    if any(e.get('type') in ('fly','levitate') for e in effects): return True
    # Layer B: Potion of Flying in inventory
    if _inv_has(pc,'potion of flying'): return True
    return False

def _has_water_breathing(pc, gs):
    effects = pc.get('active_effects',[])
    return any(e.get('type') == 'water_breathing' for e in effects)

def _has_invisibility(pc, gs):
    effects = pc.get('active_effects',[])
    equipped = pc.get('equipped_magic',[])
    if any(e.get('type') == 'invisible' for e in effects): return True
    if 'Ring of Invisibility' in equipped: return True
    if _inv_has(pc,'potion of invisibility'): return True
    return False

def _has_teleport(pc, gs):
    effects = pc.get('active_effects',[])
    return any(e.get('type') in ('teleport','dimension_door') for e in effects)

def _has_superhuman_jump(pc, gs):
    """Layer C: does character have a spell/effect granting enhanced movement?"""
    effects = pc.get('active_effects',[])
    return any(e.get('type') in ('haste','fly','levitate','spider_climb') for e in effects)


def _check_physically_impossible(text, pc, game_state):
    """
    Three-layer plausibility check.
    Layer A: Can a normal human do this?
    Layer B: Does inventory make it possible?
    Layer C: Does a memorised spell/active effect make it possible?
    """
    pc_name = pc.get('name','The character')

    # Run IMPOSSIBLE_ACTIONS table
    for triggers, condition_fn, rejection_msg in IMPOSSIBLE_ACTIONS:
        if any(t in text for t in triggers):
            if condition_fn(pc, game_state):
                return f"{pc_name} {rejection_msg}"

    # ── Improvised equipment checks ───────────────────────────────────────────
    # Detect attempts to use items beyond their physical limits
    import re as _re

    # Rope-like items for climbing/bridging
    # Waterskin strap: ~3 feet of leather cord — can tie small things, not scale cliffs
    if ('waterskin' in text and 'strap' in text and
        any(w in text for w in ['climb','scale','rope down','rappel','lower myself'])):
        return (f"{pc_name}'s waterskin strap is only a few feet of leather cord — "
                f"far too short for climbing.")

    # Holy water cannot be combined into explosives
    if ('holy water' in text and
        any(w in text for w in ['grenade','explosive','bomb','mix','combine','throw at area'])):
        return ("Holy water damages undead on direct contact. "
                "It has no explosive or alchemical properties.")

    # Torch: can provide light and fire, not weld/melt metal
    if ('torch' in text and
        any(w in text for w in ['weld','melt metal','forge','smelt'])):
        return ("A torch is not hot enough to melt or weld metal.")

    # Shield: cannot be used as a raft/boat
    if ('shield' in text and
        any(w in text for w in ['raft','sail across','float across','paddle across'])):
        return (f"{pc_name}'s shield is too small and not watertight to use as a raft.")

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

    # ── Parse confidence check ────────────────────────────────────────────────
    # If parser returned 'other' and it's not a whitelisted pass-through,
    # return a soft "please rephrase" rather than falling through to narration.
    first_action = action_chain[0] if action_chain else {}
    if first_action.get("type") == "other" and not validation.parsed.get("pass_turn"):
        raw = first_action.get("raw", text).strip()
        # Short inputs that are clearly just passing the turn
        PASS_TURN_WORDS = {'wait','hold','nothing','pass','continue','watch',
                           '...','ok','okay','yes','no','sure'}
        if raw.lower() not in PASS_TURN_WORDS and len(raw.split()) > 1:
            return {
                "rejection": None,
                "display_rolls": [],
                "narration": (f"⚠ Unable to parse: \"{raw[:80]}\". "
                              f"Please be more specific — e.g. "
                              f"\"I attack the goblin with my axe\", "
                              f"\"I move east\", or \"I search the room\"."),
                "state_changes": {},
                "error": None,
                "parse_fail": True,
            }

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

    # Prepend parse line ONLY when there are actual dice lines below it
    if _parse_line and all_display:
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
    """Find NPC profile; auto-generate minimal profile for monsters if needed."""
    module_data = game_state.get("module_data",{})
    npcs = module_data.get("npcs",[])
    npc_name_lower = npc_name.lower()
    for npc in npcs:
        if (npc.get("name","").lower() == npc_name_lower or
                npc_name_lower in npc.get("name","").lower()):
            return npc
    for npc in game_state.get("npcs_present",[]):
        if npc.get("name","").lower() == npc_name_lower:
            return npc
    # Auto-generate minimal NPC profile for monsters
    enc = game_state.get("current_encounter",{})
    for monster in enc.get("monsters",[]):
        mname = monster.get("name","").lower()
        if mname == npc_name_lower or npc_name_lower in mname:
            return {
                "name": monster.get("name",""),
                "role": "hostile creature",
                "motivation": "survive and fight",
                "attitude": "hostile",
                "will_never": ["willingly surrender", "give up its weapons",
                               "cooperate with adventurers"],
                "assets": [],
                "_auto_generated": True,
            }
    current_room = game_state.get("current_room","")
    for loc in module_data.get("locations",[]):
        if loc.get("id") == current_room:
            for monster in loc.get("monsters",[]):
                mname = monster.get("name","").lower()
                if mname == npc_name_lower or npc_name_lower in mname:
                    return {
                        "name": monster.get("name",""),
                        "role": "hostile creature",
                        "motivation": "survive and fight",
                        "attitude": "hostile",
                        "will_never": ["willingly cooperate", "give up weapons"],
                        "assets": [],
                        "_auto_generated": True,
                    }
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

JS_BUNDLE_B64 = "LyogdjE3Nzg5MDYxMTkgKi8KY29uc3QgT1NFX01FQ0hBTklDU19SVUxFU19KUyA9IGBPRkZJQ0lBTCBPU0UgQURWQU5DRUQgRkFOVEFTWSBNRUNIQU5JQ1MgLS0gVVNFIE9OTFkgVEhFU0U6CgpST0xMUyBBUkUgSEFORExFRCBCWSBUSEUgU0VSVkVSLiBXaGVuIHlvdSBzZWUgW1JvbGwgcmVzdWx0XSBpbiBjb250ZXh0LCByZXBvcnQgaXQgZmFpdGhmdWxseS4gRG8gTk9UIHJlLXJvbGwgb3Igb3ZlcnJpZGUuCgpPRkZJQ0lBTCBNRUNIQU5JQ1MgT05MWToKLSBBdHRhY2sgcm9sbHM6IGQyMCB2cyBUSEFDMC4gU1RSIG1vZCB0byBtZWxlZSBoaXQgJiBkYW1hZ2UuIERFWCBtb2QgdG8gcmFuZ2VkIGhpdCBvbmx5LiBNaW4gMSBkYW1hZ2Ugb24gYSBoaXQuCi0gU2F2aW5nIHRocm93czogT05MWSB0aGVzZSA1IGNhdGVnb3JpZXMgLS0gRGVhdGgvUG9pc29uLCBXYW5kcywgUGFyYWx5c2lzL1BldHJpZnksIEJyZWF0aCBBdHRhY2tzLCBTcGVsbHMvUm9kcy9TdGF2ZXMuCi0gVGhpZWYgc2tpbGxzIChkJSk6IE9wZW4gTG9ja3MsIEZpbmQgVHJhcHMsIFJlbW92ZSBUcmFwcywgQ2xpbWIgV2FsbHMsIE1vdmUgU2lsZW50bHksIEhpZGUgaW4gU2hhZG93cywgUGljayBQb2NrZXRzLiBPTkxZIGZvciBUaGllZi9BY3JvYmF0L0Fzc2Fzc2luIGNsYXNzZXMuCi0gSW5pdGlhdGl2ZTogZDYgcGVyIHNpZGUuIFRpZXMgZ28gdG8gcGxheWVycy4KLSBNb3JhbGU6IDJkNiB2cyBtb3JhbGUgc2NvcmUgd2hlbiBtb25zdGVyIGlzIHJlZHVjZWQgdG8gaGFsZiBIUCBvciBsZWFkZXIgZGllcy4KLSBSZWFjdGlvbiByb2xsczogMmQ2ICsgQ0hBIG1vZGlmaWVyIG9uIGZpcnN0IE5QQyBlbmNvdW50ZXIuCi0gU2VhcmNoaW5nOiBkNj0xIHN1Y2Nlc3MgKGQ2PTEtMiBmb3IgRWx2ZXMvSGFsZi1FbHZlcykuIEFOWSBjaGFyYWN0ZXIgY2FuIHNlYXJjaC4gVGFrZXMgMSB0dXJuLgotIEhlYXIgTm9pc2U6IGQ2PTEtMiBzdWNjZXNzIGZvciBub24tdGhpZXZlcy4gVGhpZXZlcyB1c2Ugc2tpbGwgdGFibGUuCi0gRm9yY2UgRG9vcjogZDY9MS0yIHN1Y2Nlc3MuCi0gQWJpbGl0eSBjaGVja3MgKG9wdGlvbmFsKTogZDIwIHVuZGVyIGFiaWxpdHkgc2NvcmUgZm9yIHVuY2VydGFpbiB0YXNrcy4KCkFCU09MVVRFTFkgRk9SQklEREVOIC0tIE5FVkVSIFNBWSBPUiBVU0U6Ci0gIk1ha2UgYSBQZXJjZXB0aW9uIGNoZWNrIiAobm90IGluIE9TRSAtLSB1c2Ugc2VhcmNoaW5nIHJ1bGVzKQotICJSb2xsIFN0ZWFsdGgiIChub3QgaW4gT1NFIC0tIHVzZSBIaWRlIGluIFNoYWRvd3Mgb3Igc3VycHJpc2UpCi0gIlJvbGwgSW5zaWdodC9BdGhsZXRpY3MvSW52ZXN0aWdhdGlvbi9BY3JvYmF0aWNzIiAoNWUgc2tpbGxzLCBub3QgaW4gT1NFKQotIFByb2ZpY2llbmN5IGJvbnVzLCBBZHZhbnRhZ2UsIERpc2FkdmFudGFnZSwgQ29uY2VudHJhdGlvbiwgQm9udXMgYWN0aW9ucyAoYWxsIDVlKQotICJSb2xsIERDIFgiIC0tIE9TRSB1c2VzIHRhcmdldCBudW1iZXJzIG5vdCBEQ3MKLSBBbnkgc2tpbGwgY2hlY2sgYnkgYSBub24tdGhpZWYgZm9yIHRhc2tzIG9ubHkgdGhpZXZlcyBjYW4gcGVyZm9ybSAocGljayBsb2NrcywgZmluZCB0cmFwcykKSWYgeW91IGFyZSB1bnN1cmUgd2hldGhlciBhIG1lY2hhbmljIGV4aXN0cyBpbiBPU0U6IGl0IHByb2JhYmx5IGRvZXNuJ3QuIFVzZSByZWZlcmVlIGp1ZGdtZW50IGluc3RlYWQuYDsKCmNvbnN0IFJVTEVTX1RFWFQgPSB7CiAgT1NFOmBSVUxFUzogT2xkLVNjaG9vbCBFc3NlbnRpYWxzIEFkdmFuY2VkIEZhbnRhc3kKLSBBdHRhY2s6IGQyMCArIFNUUiBtb2QgKG1lbGVlKSBvciBERVggbW9kIChyYW5nZWQpLiBGaWdodGVyICsxIHRvIGhpdC4gSGl0IGlmIHJlc3VsdCBtZWV0cy9iZWF0cyB0YXJnZXQgQUMuCi0gRGFtYWdlOiB3ZWFwb24gZGllICsgU1RSIG1vZCAobWVsZWUgb25seSkuIE5hdHVyYWwgMjAgPSBtYXhpbXVtIGRhbWFnZS4KLSBTYXZpbmcgdGhyb3dzIHZhcnkgYnkgY2xhc3MuIEZpZ2h0ZXI6IERlYXRoIDEyLCBXYW5kcyAxMywgUGFyYWx5c2lzIDE0LCBCcmVhdGggMTUsIFNwZWxscyAxNi4KLSBUaGllZiBza2lsbHMgKGQxMDApOiBGaW5kIFRyYXBzIDI1LCBPcGVuIExvY2tzIDI1LCBNb3ZlIFNpbGVudCAzMCwgSGlkZSBpbiBTaGFkb3dzIDIwLCBCYWNrc3RhYiDDlzIgZGFtYWdlIChtdXN0IGJlIGhpZGRlbiBmaXJzdCkuCi0gTWFnaWMtVXNlcjogMSBzcGVsbCBzbG90L2RheSBhdCBsZXZlbCAxLiBTbGVlcCA9IDJkOCBIRCBjcmVhdHVyZXMgc2xlZXAsIG5vIHNhdmUuIE1hZ2ljIE1pc3NpbGUgPSAxZDYrMSwgYXV0by1oaXRzLgotIENsZXJpYzogVHVybiBVbmRlYWQgMmQ2IHZzIHVuZGVhZCBIRCB0b3RhbC4gQ3VyZSBMaWdodCBXb3VuZHMgPSAxZDYrMSBIUC4gMSBzcGVsbC9kYXkgYXQgbGV2ZWwgMS4KLSBNb3JhbGU6IE1vbnN0ZXJzIGNoZWNrIDJkNiB3aGVuIHJlZHVjZWQgdG8gaGFsZiBIUCBvciBsZWFkZXIgZGllcy4KLSBSZXN0OiBSZWNvdmVyIDEgSFAgcGVyIGZ1bGwgbmlnaHQncyByZXN0LiBObyBoZWFsaW5nIHdpdGhvdXQgcmVzdCBvciBtYWdpYy5gLAogICdBRCZEIDFlJzpgUlVMRVM6IEFkdmFuY2VkIEQmRCAxc3QgRWRpdGlvbiBUSEFDMCBzeXN0ZW0uIEZpZ2h0ZXIgVEhBQzAgMjAsIHJvbGwgZDIwLCBzdWJ0cmFjdCBmcm9tIFRIQUMwID0gQUMgaGl0LiBXZWFwb24gc3BlZWQgZmFjdG9ycyBhcHBseS4gU2F2aW5nIHRocm93czogRGVhdGgsIFBldHJpZmljYXRpb24sIFJvZHMvU3RhdmVzLCBCcmVhdGgsIFNwZWxscy4gVmFuY2lhbiBzcGVsbGNhc3RpbmcuYCwKICAnRCZEIDVlJzpgUlVMRVM6IEQmRCA1ZS4gQXR0YWNrOiBkMjAgKyBhYmlsaXR5IG1vZCArIHByb2ZpY2llbmN5IGJvbnVzICgrMikgdnMgQUMuIEFkdmFudGFnZS9kaXNhZHZhbnRhZ2U6IHJvbGwgMmQyMC4gRGVhdGggc2F2ZXM6IDMgc3VjY2Vzc2VzIG9yIGZhaWx1cmVzLiBTaG9ydCByZXN0OiBzcGVuZCBIaXQgRGljZS4gTG9uZyByZXN0OiBmdWxsIHJlY292ZXJ5LmAsCiAgJ0IvWCc6YFJVTEVTOiBCL1ggRCZELiBBdHRhY2sgbWF0cml4IGJ5IGNsYXNzL2xldmVsLiBTYXZpbmcgdGhyb3dzOiBEZWF0aCwgV2FuZHMsIFBhcmFseXNpcywgQnJlYXRoLCBTcGVsbHMuIE1vcmFsZSAyZDYuIEZhc3QgYW5kIGRlYWRseS5gLAogICdQYXRoZmluZGVyIDFlJzpgUlVMRVM6IFBhdGhmaW5kZXIgMWUuIGQyMCArIEJBQiArIG1vZC4gQ01CL0NNRCBmb3IgbWFuZXV2ZXJzLiBGb3J0aXR1ZGUvUmVmbGV4L1dpbGwgc2F2ZXMuIEZ1bGwgYWN0aW9uIGVjb25vbXkuYCwKICAnQ2FsbCBvZiBDdGh1bGh1JzpgUlVMRVM6IENvQyA3ZS4gZDEwMCB1bmRlciBza2lsbCBmb3Igc3VjY2Vzcy4gSGFsZiA9IEhhcmQsIGZpZnRoID0gRXh0cmVtZS4gU2FuaXR5IHBvb2wuIENvbWJhdCBpcyBsZXRoYWwgLS0gYXZvaWQgaXQuIEludmVzdGlnYXRpb24gaXMgY29yZSBnYW1lcGxheS5gLAp9OwoKY29uc3QgQkFTRV9VUkwgPSAnaHR0cDovL2xvY2FsaG9zdDo4MDgwJzsKbGV0IHBsYXllck5hbWUgPSAnJzsKbGV0IGFwaUtleSA9ICcnOwpsZXQgaXNIb3N0ID0gZmFsc2U7CmxldCByb29tQ29kZSA9ICcnOwpsZXQgaXNNdWx0aXBsYXllciA9IGZhbHNlOwpsZXQgbW9kdWxlVGV4dCA9ICcnOwpsZXQgbW9kdWxlTmFtZSA9ICcnOwpsZXQgY2hvc2VuUnVsZXMgPSAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwpsZXQgY2hvc2VuUmFjZSAgPSAnSHVtYW4nOwpsZXQgY2hvc2VuQ2xhc3MgPSAnRmlnaHRlcic7CmxldCByb2xsZWRTdGF0cyAgPSB7fTsKbGV0IHN0YXJ0aW5nR29sZCA9IDA7CmxldCBzZWxlY3RlZEVxdWlwID0ge307CmxldCBleHRyYUl0ZW1zICAgPSBbXTsKbGV0IGdvbGRTcGVudCAgICA9IDA7CmNvbnN0IHNlbGVjdGVkRXF1aXBJdGVtcyA9IG5ldyBTZXQoKTsgIC8vIHRyYWNrcyB0b2dnbGVkIGV4dHJhIGVxdWlwbWVudApsZXQgcGMgPSB7fTsKbGV0IHBhcnR5UENzID0ge307CmxldCBoaXN0b3J5ICA9IFtdOwpsZXQgYnVzeSAgICAgPSBmYWxzZTsKbGV0IHN5c3RlbVByb21wdCA9ICcnOwpsZXQgcG9sbFRpbWVyICA9IG51bGw7CmxldCBsYXN0U2VxICAgID0gMDsKbGV0IHVwbG9hZGVkRmlsZSA9IG51bGw7CmxldCBtZW1vcnlTdW1tYXJ5ICAgPSAnJzsKbGV0IHdvcmxkU3RhdGUgPSB7IG5wY3NfbWV0Ont9LCBsb2NhdGlvbnNfdmlzaXRlZDp7fSwgaXRlbXNfZm91bmQ6W10sIHBsb3RfcG9pbnRzOltdLAogICAgICAgICAgICAgICAgICAgIGRvb3JzX29wZW5lZDpbXSwgdHJhcHNfc3BydW5nOltdLCBtb25zdGVyc19raWxsZWQ6W10sIHF1ZXN0c19hY3RpdmU6W10sIHdvcmxkX2NoYW5nZXM6W10gfTsKbGV0IGdtQnJpZWZpbmcgID0gJyc7CmxldCBucGNLbm93bGVkZ2VNYXAgPSB7fTsKbGV0IG5wY1Byb2ZpbGVzID0ge307CmxldCBsb2NhdGlvbkF0bW9zcGhlcmUgPSB7fTsKbGV0IGN1cnJlbnRBdG1vc3BoZXJlICA9ICcnOwpsZXQgc2Vzc2lvblRvbmUgPSAnZXhwbG9yYXRvcnknOwpsZXQgcGlubmVkRmFjdHMgID0gW107CmxldCB0dXJuQ291bnQgICAgPSAwOwpjb25zdCBTVU1NQVJZX0VWRVJZX05fVFVSTlMgPSA4Owpjb25zdCBNQVhfUElOTkVEX0ZBQ1RTID0gMjA7CmNvbnN0IE1BWF9ISVNUT1JZX0JFRk9SRV9TVU1NQVJZID0gMTY7CmNvbnN0IEJBTk5FRF9QSFJBU0VTX1BPT0wgPSBbCiAgJ1RoZSBhaXIgaXMgaGVhdnkgd2l0aCcsJ1lvdSBub3RpY2UnLCdTdWRkZW5seScsJ0FzIHlvdSBlbnRlcicsJ1RoZSBzbWVsbCBvZicsCiAgJ1lvdSBjYW4gc2VlJywnSXQgYmVjb21lcyBjbGVhcicsJ1lvdSByZWFsaXplJywnV2l0aG91dCB3YXJuaW5nJywnWW91IGZpbmQgeW91cnNlbGYnLAogICdZb3Ugb2JzZXJ2ZScsJ0FzIHlvdSBhcHByb2FjaCcsJ0FzIHlvdSBzdGVwJywnVGhlIGF0bW9zcGhlcmUgaXMnLCdJbmRlZWQnLAogICdDZXJ0YWlubHknLCdDbGVhcmx5JywnT2J2aW91c2x5JywnUXVpY2tseScsJ1NlZW1pbmdseScsCl07CmxldCBiYW5uZWRQaHJhc2VzID0gW107CmxldCBwYWNpbmdIaXN0b3J5ID0gW107CmxldCBjdXJyZW50UGFjaW5nUGhhc2UgPSAnb3BlbmluZyc7CmxldCB0dXJuc1NpbmNlTGFzdENvbWJhdCA9IDA7CmxldCB0dXJuc1NpbmNlTGFzdFJlc3QgICA9IDA7CmxldCBjb25zZXF1ZW5jZXMgPSBbXTsKbGV0IHBlbmRpbmdDb25zZXF1ZW5jZXMgID0gW107CmxldCBkdW5nZW9uVHVybnMgPSAwOwpsZXQgdG9yY2hUdXJuc0xlZnQgPSA2OwpsZXQgaGFzTGFudGVybiA9IGZhbHNlOwpsZXQgbGFudGVybk9pbEZsYXNrc0xlZnQgPSAwOwpsZXQgdG9yY2hMaXQgPSBmYWxzZTsKbGV0IHRvcmNoZXNDYXJyaWVkID0gMDsKbGV0IGxhbnRlcm5MaXQgPSBmYWxzZTsKbGV0IHRvcmNoRXZlclVzZWQgPSBmYWxzZTsKbGV0IHJhdGlvbnNMZWZ0ID0gMDsKbGV0IGRheXNXaXRob3V0Rm9vZCA9IDA7CmxldCB0dXJuc1dpdGhvdXRSZXN0ID0gMDsKbGV0IHJlc3REZWJ0ID0gMDsKbGV0IHN0YXJ2YXRpb25QZW5hbHR5ID0gMDsKbGV0IGZhdGlndWVQZW5hbHR5ID0gMDsKbGV0IGlzQ2FycnlpbmdMaWdodCA9IHRydWU7CmxldCB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOwpsZXQgd2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlID0gZmFsc2U7CmxldCBsb2dFbnRyaWVzID0gW107CmxldCBhY3RpdmVFZmZlY3RzID0gW107CmxldCBzZWxlY3RlZERuZG1vZEZpbGUgPSBudWxsOwpsZXQgb2xsYW1hQXZhaWxhYmxlID0gZmFsc2U7CmxldCB1c2VPbGxhbWEgPSBmYWxzZTsKbGV0IGxhc3RBaVZpYSA9ICcnOwpsZXQgY3NlbENoYXJzICA9IFtdOwpsZXQgY3NlbFNlbGVjdGVkSWQgID0gbnVsbDsKbGV0IGNzZWxQZW5kaW5nU2F2ZSA9IG51bGw7CmxldCBjc2VsUGVuZGluZ0pvaW4gPSBudWxsOwpsZXQgbmdyb2tQdWJsaWNVcmwgID0gJyc7CmxldCBjb252RmlsZVBhdGggPSBudWxsOwpsZXQgY29udlVwbG9hZGVkRmlsZSA9IG51bGw7Cgpjb25zdCBQTEFZRVJfQ09MT1JTID0gWycjN2FiYWZmJywnI2ZmYjA3YScsJyM3YWZmYjAnLCcjZmZkYTdhJywnI2Q5N2FmZicsJyNmZjdhYWEnLCcjN2FmZmZmJ107CmxldCBjb2xvck1hcCA9IHt9Owpjb25zdCBJTlZfV0VBUE9OUyA9IC9zd29yZHxkYWdnZXJ8KD88IWhhbmRccylheGV8KD86bG9uZ3xzaG9ydHxoYW5kKWJvd3xjcm9zc2Jvd3xzcGVhcnxtYWNlfGZsYWlsfHdhcmhhbW1lcnxjbHVifGtuaWZlfGJsYWRlL2k7CmNvbnN0IElOVl9BUk1PVVIgID0gL2FybW91P3J8Y2hhaW4gbWFpbHxwbGF0ZSBtYWlsfGxlYXRoZXIgYXJtb3J8c2hpZWxkfGhlbG1ldHxoZWxtfGdhdW50bGV0cz98Z3JlYXZlc3xicmFjZXJzfHJpbmcgbWFpbHxzY2FsZSBtYWlsfHNwbGludHxiYW5kZWQvaTsKY29uc3QgSU5WX0FNTU8gICAgPSAvXihib2x0cz98YXJyb3dzP3xxdWFycmVscz98c2hvdHM/fHNsaW5nIHN0b25lcz98Y3Jvc3Nib3cgYm9sdHM/KSQvaTsKY29uc3QgSU5WX01BR0lDICAgPSAvcG90aW9ufHNjcm9sbHx3YW5kfHJvZHxhbXVsZXR8Y2hhcm18ZW5jaGFudHxcK1swLTldL2k7CmNvbnN0IEFDVElPTl9UWVBFUyA9IHsKICBDT01CQVQ6ICAgJ2NvbWJhdCcsCiAgU0VBUkNIOiAgICdzZWFyY2gnLAogIFNPQ0lBTDogICAnc29jaWFsJywKICBNT1ZFTUVOVDogJ21vdmVtZW50JywKICBTS0lMTDogICAgJ3NraWxsJywKICBNQUdJQzogICAgJ21hZ2ljJywKICBJVEVNOiAgICAgJ2l0ZW0nLAogIFJFU1Q6ICAgICAncmVzdCcsCiAgT1RIRVI6ICAgICdvdGhlcicsCn07CgoKY29uc3QgT1NFX0FSTU9VUiA9IHsKICAnTGVhdGhlciBBcm1vdXInOiB7YWM6NywgY29zdDoyMCwgIG5vdGVzOicnfSwKICAnQ2hhaW4gTWFpbCc6ICAgICB7YWM6NSwgY29zdDo0MCwgIG5vdGVzOicnfSwKICAnUGxhdGUgTWFpbCc6ICAgICB7YWM6MywgY29zdDo2MCwgIG5vdGVzOidIZWF2eSAtLSBCYXJiYXJpYW5zIGNhbm5vdCB3ZWFyJ30sCiAgJ1NoaWVsZCc6ICAgICAgICAge2FjX2JvbnVzOjEsIGNvc3Q6MTAsIG5vdGVzOicnfSwKfTsKY29uc3QgR09MRF9CWV9DTEFTUyA9IHsKICBGaWdodGVyOjE4MCwnTWFnaWMtVXNlcic6MzAsQ2xlcmljOjEyMCxUaGllZjo5MCwKICBSYW5nZXI6MTUwLFBhbGFkaW46MTgwLERydWlkOjkwLElsbHVzaW9uaXN0OjMwLAogIEFzc2Fzc2luOjkwLEJhcmQ6MTIwLE1vbms6MzAsQmFyYmFyaWFuOjYwCn07Cgpjb25zdCBDTEFTU0VTID0gewogIEZpZ2h0ZXI6ICAgICB7IGljb246JycsICBocDo4LCAgYWM6MTQsIHNhdmVzOntkZWF0aDoxMix3YW5kczoxMyxwYXJhOjE0LGJyZWF0aDoxNSxzcGVsbHM6MTZ9LCBkZXNjOidCZXN0IGNvbWJhdCwgaGlnaGVzdCBIUC4gTXVsdGlwbGUgYXR0YWNrcyBhdCBoaWdoZXIgbGV2ZWxzLiBXZWFwb24gbWFzdGVyeS4nIH0sCiAgJ01hZ2ljLVVzZXInOnsgaWNvbjonJywgIGhwOjQsICBhYzoxMSwgc2F2ZXM6e2RlYXRoOjEzLHdhbmRzOjExLHBhcmE6MTMsYnJlYXRoOjE1LHNwZWxsczoxMn0sIGRlc2M6J1Bvd2VyZnVsIGFyY2FuZSBzcGVsbHMuIEZyYWdpbGUuIFNwZWxsYm9vayBtYWdpYzogU2xlZXAsIE1hZ2ljIE1pc3NpbGUsIERldGVjdCBNYWdpYy4nIH0sCiAgQ2xlcmljOiAgICAgIHsgaWNvbjonJywgIGhwOjYsICBhYzoxMywgc2F2ZXM6e2RlYXRoOjExLHdhbmRzOjEyLHBhcmE6MTQsYnJlYXRoOjE2LHNwZWxsczoxNX0sIGRlc2M6J1R1cm4gdW5kZWFkLCBoZWFsIHdvdW5kcy4gRGl2aW5lIHNwZWxsY2FzdGVyLiBIb2x5IHdhcnJpb3Igb2YgZmFpdGguJyB9LAogIFRoaWVmOiAgICAgICB7IGljb246JycsICBocDo0LCAgYWM6MTIsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxNCxwYXJhOjEzLGJyZWF0aDoxNixzcGVsbHM6MTV9LCBkZXNjOidQaWNrIGxvY2tzLCBmaW5kIHRyYXBzLCBiYWNrc3RhYiB4MiBkYW1hZ2UuIENsaW1iIHdhbGxzLCBoaWRlIGluIHNoYWRvd3MsIG1vdmUgc2lsZW50bHkuJyB9LAogIFJhbmdlcjogICAgICB7IGljb246JycsICBocDo4LCAgYWM6MTMsIHNhdmVzOntkZWF0aDoxMix3YW5kczoxMyxwYXJhOjE0LGJyZWF0aDoxNSxzcGVsbHM6MTZ9LCBkZXNjOidTa2lsbGVkIHRyYWNrZXIuIEJvbnVzIGRhbWFnZSB2cyBodW1hbm9pZHMuIER1YWwgd2llbGQuIFdpbGRlcm5lc3Mgc3Vydml2YWwgZXhwZXJ0LicgfSwKICBQYWxhZGluOiAgICAgeyBpY29uOicnLCAgaHA6OCwgIGFjOjE0LCBzYXZlczp7ZGVhdGg6MTAsd2FuZHM6MTEscGFyYToxMixicmVhdGg6MTMsc3BlbGxzOjE0fSwgZGVzYzonSG9seSB3YXJyaW9yLiBEZXRlY3QgZXZpbCBhdXJhLiBMYXkgb24gaGFuZHMuIEltbXVuZSB0byBkaXNlYXNlLiBBdXJhIG9mIHByb3RlY3Rpb24uJyB9LAogIERydWlkOiAgICAgICB7IGljb246JycsICBocDo2LCAgYWM6MTIsIHNhdmVzOntkZWF0aDoxMCx3YW5kczoxMSxwYXJhOjEzLGJyZWF0aDoxMixzcGVsbHM6MTR9LCBkZXNjOidOYXR1cmUgbWFnaWMuIFNoYXBlY2hhbmdlIGF0IGhpZ2hlciBsZXZlbHMuIFdvb2RsYW5kIGFsbGllcy4gUmVzaXN0IGZpcmUgJiBsaWdodG5pbmcuJyB9LAogIElsbHVzaW9uaXN0OiB7IGljb246JycsICBocDo0LCAgYWM6MTEsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxMSxwYXJhOjEzLGJyZWF0aDoxNSxzcGVsbHM6MTJ9LCBkZXNjOidJbGx1c2lvbiBtYWdpYyBzcGVjaWFsaXN0LiBDb2xvdXIgU3ByYXksIFBoYW50YXNtYWwgRm9yY2UsIEh5cG5vdGlzbSwgTWlycm9yIEltYWdlLicgfSwKICBBc3Nhc3NpbjogICAgeyBpY29uOicnLCAgaHA6NiwgIGFjOjEyLCBzYXZlczp7ZGVhdGg6MTMsd2FuZHM6MTQscGFyYToxMyxicmVhdGg6MTYsc3BlbGxzOjE1fSwgZGVzYzonTWFzdGVyIGtpbGxlci4gRGlzZ3Vpc2UsIHBvaXNvbiB1c2UuIEFzc2Fzc2luYXRpb24gc3RyaWtlIGZvciBpbnN0YW50IGtpbGwgY2hhbmNlLicgfSwKICBCYXJkOiAgICAgICAgeyBpY29uOicnLCAgaHA6NiwgIGFjOjEyLCBzYXZlczp7ZGVhdGg6MTMsd2FuZHM6MTQscGFyYToxMyxicmVhdGg6MTYsc3BlbGxzOjE1fSwgZGVzYzonSmFjayBvZiBhbGwgdHJhZGVzLiBJbnNwaXJlIGFsbGllcywgY2hhcm0uIExvcmUga25vd2xlZGdlLiBUaGllZiBza2lsbHMuJyB9LAogIE1vbms6ICAgICAgICB7IGljb246JycsICBocDo2LCAgYWM6MTAsIHNhdmVzOntkZWF0aDoxMyx3YW5kczoxNCxwYXJhOjEzLGJyZWF0aDoxNixzcGVsbHM6MTV9LCBkZXNjOidVbmFybWVkIGNvbWJhdCBtYXN0ZXIuIFVuYXJtb3VyZWQgQUMgYm9udXMuIFN0dW5uaW5nIHN0cmlrZS4gRmFzdCBtb3ZlbWVudC4nIH0sCiAgQmFyYmFyaWFuOiAgIHsgaWNvbjonJywgIGhwOjEwLCBhYzoxMiwgc2F2ZXM6e2RlYXRoOjEyLHdhbmRzOjEzLHBhcmE6MTQsYnJlYXRoOjE1LHNwZWxsczoxNn0sIGRlc2M6J1JhZ2UgZm9yIGJvbnVzIGRhbWFnZS4gSW5zdGluY3RpdmUgQUMgd2hlbiB1bmFybW91cmVkLiBXaWxkZXJuZXNzIHN1cnZpdmFsLiBCZXJzZXJrZXIuJyB9LAp9OwoKY29uc3QgUkFDRVMgPSB7CiAgSHVtYW46ICAgICB7IGljb246JycsIGRlc2M6J0FueSBjbGFzcywgaGlnaGVzdCBsZXZlbCBjYXBzLicsIHNwZWNpYWxzOltdIH0sCiAgRHdhcmY6ICAgICB7IGljb246JycsIGRlc2M6J0luZnJhdmlzaW9uIDYwZnQuICs0IHNhdmUgdnMgbWFnaWMgJiBwb2lzb24uIERldGVjdCBzdG9uZXdvcmsuJywgc3BlY2lhbHM6WydJbmZyYXZpc2lvbiA2MGZ0JywnKzQgc2F2ZSB2cyBtYWdpYy9wb2lzb24nLCdEZXRlY3Qgc3RvbmV3b3JrIHRyYXBzIDEtMi9kNiddLCBjbGFzc2VzOlsnRmlnaHRlcicsJ1RoaWVmJywnQXNzYXNzaW4nXSB9LAogIEVsZjogICAgICAgeyBpY29uOicnLCBkZXNjOidJbmZyYXZpc2lvbiA2MGZ0LiBEZXRlY3Qgc2VjcmV0IGRvb3JzLiBJbW11bmUgdG8gZ2hvdWwgcGFyYWx5c2lzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gNjBmdCcsJ0RldGVjdCBzZWNyZXQgZG9vcnMgMS0yL2Q2JywnSW1tdW5lIHRvIGdob3VsIHBhcmFseXNpcyddLCBjbGFzc2VzOlsnRmlnaHRlcicsJ01hZ2ljLVVzZXInLCdUaGllZicsJ1JhbmdlcicsJ0lsbHVzaW9uaXN0JywnQmFyZCddIH0sCiAgSGFsZmxpbmc6ICB7IGljb246JycsIGRlc2M6Jy0yIEFDIHZzIGxhcmdlIGZvZXMuIFN1cnByaXNlIG9ubHkgMS9kNi4gKzEgdG8gcmFuZ2VkLicsIHNwZWNpYWxzOlsnLTIgQUMgdnMgbGFyZ2UgY3JlYXR1cmVzJywnU3VycHJpc2Ugb24gMS9kNiBvbmx5JywnKzEgdG8gcmFuZ2VkIGF0dGFja3MnXSwgY2xhc3NlczpbJ0ZpZ2h0ZXInLCdUaGllZicsJ0RydWlkJ10gfSwKICAnSGFsZi1FbGYnOnsgaWNvbjonJywgZGVzYzonSW5mcmF2aXNpb24gNjBmdC4gRGV0ZWN0IHNlY3JldCBkb29ycyAxLTMvZDYuIFZlcnNhdGlsZSBjbGFzc2VzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gNjBmdCcsJ0RldGVjdCBzZWNyZXQgZG9vcnMgMS0zL2Q2J10sIGNsYXNzZXM6WydGaWdodGVyJywnTWFnaWMtVXNlcicsJ0NsZXJpYycsJ1RoaWVmJywnUmFuZ2VyJywnQmFyZCcsJ0RydWlkJywnSWxsdXNpb25pc3QnXSB9LAogIEdub21lOiAgICAgeyBpY29uOicnLCBkZXNjOidJbmZyYXZpc2lvbiA5MGZ0LiArNCBzYXZlIHZzIG1hZ2ljLiBTcGVhayB3aXRoIGJ1cnJvd2luZyBhbmltYWxzLicsIHNwZWNpYWxzOlsnSW5mcmF2aXNpb24gOTBmdCcsJys0IHNhdmUgdnMgbWFnaWMnLCdTcGVhayB3aXRoIGJ1cnJvd2luZyBhbmltYWxzJ10sIGNsYXNzZXM6WydGaWdodGVyJywnVGhpZWYnLCdJbGx1c2lvbmlzdCcsJ0Fzc2Fzc2luJ10gfSwKICAnSGFsZi1PcmMnOnsgaWNvbjonJywgZGVzYzonKzEgU1RSICYgQ09OLiBJbmZyYXZpc2lvbiA2MGZ0LiBJbnRpbWlkYXRpbmcuJywgc3BlY2lhbHM6WydJbmZyYXZpc2lvbiA2MGZ0JywnKzEgU1RSIGFuZCBDT04nXSwgYm9udXNlczp7U1RSOjEsQ09OOjF9LCBjbGFzc2VzOlsnRmlnaHRlcicsJ0NsZXJpYycsJ1RoaWVmJywnQXNzYXNzaW4nLCdCYXJiYXJpYW4nXSB9LAp9OwoKY29uc3QgQ0xBU1NfV0VBUE9OX1JFU1RSSUNUSU9OUyA9IHsKICBGaWdodGVyOiAgICAgIG51bGwsIC8vIGFsbCB3ZWFwb25zCiAgUmFuZ2VyOiAgICAgICBudWxsLAogIFBhbGFkaW46ICAgICAgbnVsbCwKICBCYXJiYXJpYW46ICAgIG51bGwsCiAgQ2xlcmljOiAgICAgICBbJ0NsdWInLCdNYWNlJywnU3RhZmYnLCdXYXIgSGFtbWVyJywnU2xpbmcnLCdTaG9ydCBCb3cnXSwgLy8gYmx1bnQgb25seQogIERydWlkOiAgICAgICAgWydDbHViJywnRGFnZ2VyJywnSGFuZCBBeGUnLCdTcGVhcicsJ1N0YWZmJywnU2xpbmcnLCdTaG9ydCBCb3cnXSwKICAnTWFnaWMtVXNlcic6IFsnRGFnZ2VyJywnU2lsdmVyIERhZ2dlcicsJ1N0YWZmJ10sCiAgSWxsdXNpb25pc3Q6ICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdTdGFmZiddLAogIFRoaWVmOiAgICAgICAgWydEYWdnZXInLCdTaWx2ZXIgRGFnZ2VyJywnQ2x1YicsJ1Nob3J0IFN3b3JkJywnSGFuZCBBeGUnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJ10sCiAgQXNzYXNzaW46ICAgICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdDbHViJywnU2hvcnQgU3dvcmQnLCdIYW5kIEF4ZScsJ01hY2UnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJ10sCiAgQmFyZDogICAgICAgICBbJ0RhZ2dlcicsJ1NpbHZlciBEYWdnZXInLCdDbHViJywnU2hvcnQgU3dvcmQnLCdIYW5kIEF4ZScsJ01hY2UnLCdDcm9zc2JvdycsJ1Nob3J0IEJvdycsJ1NsaW5nJywnU3dvcmQnLCdTdGFmZiddLAogIE1vbms6ICAgICAgICAgWydDbHViJywnRGFnZ2VyJywnSGFuZCBBeGUnLCdKYXZlbGluJywnU2hvcnQgU3dvcmQnLCdTdGFmZicsJ1NsaW5nJ10sCn07Cgpjb25zdCBDTEFTU19BUk1PVVJfUkVTVFJJQ1RJT05TID0gewogIEZpZ2h0ZXI6WydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdQbGF0ZSBNYWlsJywnU2hpZWxkJ10sCiAgUmFuZ2VyOiBbJ0xlYXRoZXIgQXJtb3VyJywnQ2hhaW4gTWFpbCcsJ1BsYXRlIE1haWwnLCdTaGllbGQnXSwKICBQYWxhZGluOlsnTGVhdGhlciBBcm1vdXInLCdDaGFpbiBNYWlsJywnUGxhdGUgTWFpbCcsJ1NoaWVsZCddLAogIEJhcmJhcmlhbjpbJ0xlYXRoZXIgQXJtb3VyJywnQ2hhaW4gTWFpbCcsJ1NoaWVsZCddLAogIENsZXJpYzogWydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdQbGF0ZSBNYWlsJywnU2hpZWxkJ10sCiAgRHJ1aWQ6ICBbJ0xlYXRoZXIgQXJtb3VyJywnU2hpZWxkJ10sCiAgVGhpZWY6ICBbJ0xlYXRoZXIgQXJtb3VyJ10sCiAgQXNzYXNzaW46WydMZWF0aGVyIEFybW91cicsJ1NoaWVsZCddLAogIEJhcmQ6ICAgWydMZWF0aGVyIEFybW91cicsJ0NoYWluIE1haWwnLCdTaGllbGQnXSwKICBNb25rOiAgIFtdLCAvLyBubyBhcm1vdXIKICAnTWFnaWMtVXNlcic6W10sCiAgSWxsdXNpb25pc3Q6W10sCn07Cgpjb25zdCBPU0VfV0VBUE9OUyA9IHsKICAvLyBNZWxlZSAtLSB7ZG1nLCBjb3N0IChncCksIGhhbmRzLCBub3Rlc30KICAnQmF0dGxlIEF4ZSc6ICAgICAgIHtkbWc6JzFkOCcsICBjb3N0OjcsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAnQ2x1Yic6ICAgICAgICAgICAgIHtkbWc6JzFkNCcsICBjb3N0OjAsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczonZnJlZSd9LAogICdEYWdnZXInOiAgICAgICAgICAge2RtZzonMWQ0JywgIGNvc3Q6MywgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2V9LAogICdIYW5kIEF4ZSc6ICAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6NCwgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOidjYW4gdGhyb3cnfSwKICAnTGFuY2UnOiAgICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjEwLCAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczonbW91bnRlZCBvbmx5J30sCiAgJ01hY2UnOiAgICAgICAgICAgICB7ZG1nOicxZDYnLCAgY29zdDo1LCAgIGhhbmRzOjEsIHJhbmdlZDpmYWxzZX0sCiAgJ1BvbGUgQXJtJzogICAgICAgICB7ZG1nOicxZDEwJywgY29zdDo3LCAgIGhhbmRzOjIsIHJhbmdlZDpmYWxzZSwgbm90ZXM6J3R3by1oYW5kZWQnfSwKICAnU2hvcnQgU3dvcmQnOiAgICAgIHtkbWc6JzFkNicsICBjb3N0OjcsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAnU2lsdmVyIERhZ2dlcic6ICAgIHtkbWc6JzFkNCcsICBjb3N0OjMwLCAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlLCBub3RlczondnMgbHljYW50aHJvcGVzL3VuZGVhZCd9LAogICdTcGVhcic6ICAgICAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6MywgICBoYW5kczoxLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOidjYW4gdGhyb3cnfSwKICAnU3RhZmYnOiAgICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjAsICAgaGFuZHM6MiwgcmFuZ2VkOmZhbHNlLCBub3RlczondHdvLWhhbmRlZCwgZnJlZSd9LAogICdTd29yZCc6ICAgICAgICAgICAge2RtZzonMWQ4JywgIGNvc3Q6MTAsICBoYW5kczoxLCByYW5nZWQ6ZmFsc2V9LAogICdUd28tSGFuZGVkIFN3b3JkJzoge2RtZzonMWQxMCcsIGNvc3Q6MTUsICBoYW5kczoyLCByYW5nZWQ6ZmFsc2UsIG5vdGVzOid0d28taGFuZGVkLCBubyBzaGllbGQnfSwKICAnV2FyIEhhbW1lcic6ICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjUsICAgaGFuZHM6MSwgcmFuZ2VkOmZhbHNlfSwKICAvLyBSYW5nZWQKICAnQ3Jvc3Nib3cnOiAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjMwLCAgaGFuZHM6MiwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgODAvMTYwLzI0MCwgc2xvdyByZWxvYWQnfSwKICAnSmF2ZWxpbic6ICAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjEsICAgaGFuZHM6MSwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgMzAvNjAvOTAnfSwKICAnTG9uZyBCb3cnOiAgICAgICAgIHtkbWc6JzFkNicsICBjb3N0OjYwLCAgaGFuZHM6MiwgcmFuZ2VkOnRydWUsICBub3RlczoncmFuZ2UgNzAvMTQwLzIxMCwgc3RyIHJlcSd9LAogICdTaG9ydCBCb3cnOiAgICAgICAge2RtZzonMWQ2JywgIGNvc3Q6MjUsICBoYW5kczoyLCByYW5nZWQ6dHJ1ZSwgIG5vdGVzOidyYW5nZSA1MC8xMDAvMTUwJ30sCiAgJ1NsaW5nJzogICAgICAgICAgICB7ZG1nOicxZDQnLCAgY29zdDoyLCAgIGhhbmRzOjEsIHJhbmdlZDp0cnVlLCAgbm90ZXM6J3JhbmdlIDQwLzgwLzE2MCd9LAogIC8vIEFtbW8KICAnQXJyb3dzICgyMCknOiAgICAgIHtkbWc6Jy0nLCAgICBjb3N0OjUsICAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZm9yIGJvd3MnfSwKICAnQ3Jvc3Nib3cgQm9sdHMgKDMwKSc6IHtkbWc6Jy0nLCBjb3N0OjEwLCAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZm9yIGNyb3NzYm93J30sCiAgJ1NpbHZlci1UaXBwZWQgQXJyb3dzICg2KSc6IHtkbWc6Jy0nLCBjb3N0OjMwLCBoYW5kczowLCByYW5nZWQ6dHJ1ZSwgbm90ZXM6J3ZzIGx5Y2FudGhyb3Blcy91bmRlYWQnfSwKICAnU2xpbmcgU3RvbmVzICgyMCknOntkbWc6Jy0nLCAgICBjb3N0OjAsICAgaGFuZHM6MCwgcmFuZ2VkOnRydWUsICBub3RlczonZnJlZSd9LAp9OwoKY29uc3QgT1NFX0VRVUlQTUVOVCA9IHsKICAnQmFja3BhY2snOiAgICAgICAgICAgICAgICAge2Nvc3Q6NX0sCiAgJ0Nyb3diYXInOiAgICAgICAgICAgICAgICAgIHtjb3N0OjEwfSwKICAnR2FybGljJzogICAgICAgICAgICAgICAgICAge2Nvc3Q6NSwgICBub3RlczoncGVyIGhlYWQnfSwKICAnR3JhcHBsaW5nIEhvb2snOiAgICAgICAgICAge2Nvc3Q6MjV9LAogICdIYW1tZXIgKHNtYWxsKSc6ICAgICAgICAgICB7Y29zdDoyfSwKICAnSG9seSBTeW1ib2wnOiAgICAgICAgICAgICAge2Nvc3Q6MjV9LAogICdIb2x5IFdhdGVyICh2aWFsKSc6ICAgICAgICB7Y29zdDoyNX0sCiAgJ0lyb24gU3Bpa2VzICgxMiknOiAgICAgICAgIHtjb3N0OjF9LAogICdMYW50ZXJuJzogICAgICAgICAgICAgICAgICB7Y29zdDoxMH0sCiAgJ01pcnJvciAoaGFuZC1zaXplZCwgc3RlZWwpJzp7Y29zdDo1fSwKICAnT2lsICgxIGZsYXNrKSc6ICAgICAgICAgICAge2Nvc3Q6Mn0sCiAgJ1BvbGUgKDEwZnQgd29vZGVuKSc6ICAgICAgIHtjb3N0OjF9LAogICdSYXRpb25zIChpcm9uLCA3IGRheXMpJzogICB7Y29zdDoxNSwgbm90ZXM6J3ByZXNlcnZlZCd9LAogICdSYXRpb25zIChzdGFuZGFyZCwgNyBkYXlzKSc6e2Nvc3Q6NX0sCiAgJ1JvcGUgKDUwZnQpJzogICAgICAgICAgICAgIHtjb3N0OjF9LAogICdTYWNrIChsYXJnZSknOiAgICAgICAgICAgICB7Y29zdDoyfSwKICAnU2FjayAoc21hbGwpJzogICAgICAgICAgICAge2Nvc3Q6MX0sCiAgJ1N0YWtlcyAoMykgYW5kIE1hbGxldCc6ICAgIHtjb3N0OjN9LAogICJUaGlldmVzJyBUb29scyI6ICAgICAgICAgICB7Y29zdDoyNX0sCiAgJ1RpbmRlciBCb3ggKGZsaW50ICYgc3RlZWwpJzp7Y29zdDozfSwKICAnVG9yY2hlcyAoNiknOiAgICAgICAgICAgICAge2Nvc3Q6MX0sCiAgJ1dhdGVyc2tpbic6ICAgICAgICAgICAgICAgIHtjb3N0OjF9LAogICdXaW5lICgyIHBpbnRzKSc6ICAgICAgICAgICB7Y29zdDoxfSwKICAnV29sZnNiYW5lICgxIGJ1bmNoKSc6ICAgICAge2Nvc3Q6MTB9LAp9OwoKCmZ1bmN0aW9uIHhockZldGNoKHVybCwgb3B0cykgewogIHJldHVybiBuZXcgUHJvbWlzZSgocmVzb2x2ZSwgcmVqZWN0KSA9PiB7CiAgICBjb25zdCB4aHIgPSBuZXcgWE1MSHR0cFJlcXVlc3QoKTsKICAgIGNvbnN0IG1ldGhvZCA9IChvcHRzICYmIG9wdHMubWV0aG9kKSB8fCAnR0VUJzsKICAgIHhoci5vcGVuKG1ldGhvZCwgdXJsLCB0cnVlKTsKICAgIGlmIChvcHRzICYmIG9wdHMuaGVhZGVycykgewogICAgICBPYmplY3QuZW50cmllcyhvcHRzLmhlYWRlcnMpLmZvckVhY2goKFtrLHZdKSA9PiB4aHIuc2V0UmVxdWVzdEhlYWRlcihrLHYpKTsKICAgIH0KICAgIHhoci50aW1lb3V0ID0gMTgwMDAwOwogICAgeGhyLm9ubG9hZCA9ICgpID0+IHJlc29sdmUoewogICAgICBvazogeGhyLnN0YXR1cyA+PSAyMDAgJiYgeGhyLnN0YXR1cyA8IDMwMCwKICAgICAgc3RhdHVzOiB4aHIuc3RhdHVzLAogICAgICBqc29uOiAoKSA9PiBQcm9taXNlLnJlc29sdmUoSlNPTi5wYXJzZSh4aHIucmVzcG9uc2VUZXh0KSksCiAgICAgIHRleHQ6ICgpID0+IFByb21pc2UucmVzb2x2ZSh4aHIucmVzcG9uc2VUZXh0KSwKICAgIH0pOwogICAgeGhyLm9uZXJyb3IgPSAoKSA9PiByZWplY3QobmV3IEVycm9yKCdOZXR3b3JrIHJlcXVlc3QgZmFpbGVkOiAnICsgbWV0aG9kICsgJyAnICsgdXJsKSk7CiAgICB4aHIub250aW1lb3V0ID0gKCkgPT4gcmVqZWN0KG5ldyBFcnJvcignUmVxdWVzdCB0aW1lZCBvdXQ6ICcgKyBtZXRob2QgKyAnICcgKyB1cmwpKTsKICAgIHhoci5zZW5kKChvcHRzICYmIG9wdHMuYm9keSkgfHwgbnVsbCk7CiAgfSk7Cn0KCmZ1bmN0aW9uIHNob3coaWQpIHsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcuc2NyZWVuJykuZm9yRWFjaChzID0+IHsKICAgIHMuY2xhc3NMaXN0LnJlbW92ZSgnYWN0aXZlJyk7CiAgICBzLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgfSk7CiAgY29uc3QgdGFyZ2V0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoaWQpOwogIGlmICghdGFyZ2V0KSB7IGNvbnNvbGUuZXJyb3IoJ1tzaG93XSBFbGVtZW50IG5vdCBmb3VuZDonLCBpZCk7IHJldHVybjsgfQogIHRhcmdldC5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICB0YXJnZXQuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKICBpZiAoaWQgIT09ICdzLWdhbWUnKSB0YXJnZXQuc2Nyb2xsVG9wID0gMDsKICBjb25zb2xlLmxvZygnW3Nob3ddIE5hdmlnYXRlZCB0bzonLCBpZCk7CiAgLy8gU2NyZWVuLXNwZWNpZmljIGluaXQKICBpZiAoaWQgPT09ICdzLWNvbnZlcnQnKSB7IGluaXRDb252RHJvcCgpOyBjb252TG9hZEV4aXN0aW5nKCk7IH0KfQoKYXN5bmMgZnVuY3Rpb24gY2hlY2tPbGxhbWFTdGF0dXMoKSB7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYWktc3RhdHVzJyk7CiAgY29uc3QgYXBpQm94ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktYm94Jyk7CiAgY29uc3QgYXBpTGluayA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzaG93LWFwaS1saW5rJyk7CiAgaWYgKCFlbCkgcmV0dXJuOwoKICAvLyBUaW1lb3V0IHdyYXBwZXIgLS0gbmV2ZXIgc3RheSBzdHVjayBvbiAiQ2hlY2tpbmcuLi4iCiAgY29uc3QgdGltZW91dCA9IG5ldyBQcm9taXNlKChfLCByZWplY3QpID0+CiAgICBzZXRUaW1lb3V0KCgpID0+IHJlamVjdChuZXcgRXJyb3IoJ3RpbWVvdXQnKSksIDUwMDApCiAgKTsKCiAgdHJ5IHsKICAgIGNvbnN0IHIgPSBhd2FpdCBQcm9taXNlLnJhY2UoW3hockZldGNoKEJBU0VfVVJMICsgJy9vbGxhbWFfc3RhdHVzJyksIHRpbWVvdXRdKTsKCiAgICAvLyBDaGVjayBpZiB0aGlzIGlzIGFjdHVhbGx5IHRoZSB2MyBzZXJ2ZXIgKG9sZCBzZXJ2ZXJzIHdvbid0IGhhdmUgdGhpcyBlbmRwb2ludCkKICAgIGlmICghci5vaykgewogICAgICB0aHJvdyBuZXcgRXJyb3IoJ1NlcnZlciByZXR1cm5lZCAnICsgci5zdGF0dXMgKyAnIC0tIG1heSBiZSBydW5uaW5nIG9sZCB2ZXJzaW9uLiBIYXJkIHJlZnJlc2ggd2l0aCBDdHJsK1NoaWZ0K1InKTsKICAgIH0KCiAgICBjb25zdCBkID0gYXdhaXQgci5qc29uKCk7CgogICAgLy8gVmVyaWZ5IHRoaXMgaXMgYWN0dWFsbHkgYW4gb2xsYW1hX3N0YXR1cyByZXNwb25zZSAobm90IHNvbWUgb3RoZXIgZW5kcG9pbnQncyByZXNwb25zZSkKICAgIGlmICh0eXBlb2YgZC5hdmFpbGFibGUgPT09ICd1bmRlZmluZWQnKSB7CiAgICAgIHRocm93IG5ldyBFcnJvcignVW5leHBlY3RlZCByZXNwb25zZSAtLSBvbGQgc2VydmVyIG1heSBiZSBydW5uaW5nLiBTdG9wIGl0IGFuZCByZXN0YXJ0IGRuZF9hZHZlbnR1cmVfdjQucHknKTsKICAgIH0KCiAgICBvbGxhbWFBdmFpbGFibGUgPSBkLmF2YWlsYWJsZTsKICAgIHVzZU9sbGFtYSA9IGQuYXZhaWxhYmxlOwoKICAgIGlmIChkLmF2YWlsYWJsZSkgewogICAgICBlbC5zdHlsZS5ib3JkZXIgPSAnMnB4IHNvbGlkICMzYTZhM2EnOwogICAgICBlbC5zdHlsZS5iYWNrZ3JvdW5kID0gJyMwYTFhMGEnOwogICAgICBlbC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsKICAgICAgZWwuaW5uZXJIVE1MID0gJ09sbGFtYSBydW5uaW5nICZtZGFzaDsgPHN0cm9uZz4nICsgKGQubW9kZWwgfHwgJ2xvY2FsJykgKyAnPC9zdHJvbmc+JwogICAgICAgICsgJzxicj48c3BhbiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Zm9udC13ZWlnaHQ6bm9ybWFsOyI+RnJlZSBsb2NhbCBBSSByZWFkeS4gTm8gQVBJIGtleSBuZWVkZWQgdG8gaG9zdC48L3NwYW4+JzsKICAgICAgaWYgKGFwaUxpbmspIGFwaUxpbmsuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICAgIGlmIChhcGlCb3gpIGFwaUJveC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgfSBlbHNlIHsKICAgICAgZWwuc3R5bGUuYm9yZGVyID0gJzJweCBzb2xpZCAjOGE1YTIwJzsKICAgICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICcjMWExMDAwJzsKICAgICAgZWwuc3R5bGUuY29sb3IgPSAnI2MwOTA2MCc7CiAgICAgIGVsLmlubmVySFRNTCA9ICchIE9sbGFtYSBub3QgcnVubmluZycKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+SW5zdGFsbCBmcm9tIDxhIGhyZWY9Imh0dHBzOi8vb2xsYW1hLmNvbSIgdGFyZ2V0PSJfYmxhbmsiIHN0eWxlPSJjb2xvcjojYzlhODRjIj5vbGxhbWEuY29tPC9hPiB0aGVuIHJ1bjogPGNvZGUgc3R5bGU9ImNvbG9yOiNjOWE4NGMiPm9sbGFtYSBwdWxsIG1pc3RyYWwtbmVtbzoxMmI8L2NvZGU+PC9zcGFuPicKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+T3IgZW50ZXIgYSBDbGF1ZGUgQVBJIGtleSBiZWxvdy48L3NwYW4+JzsKICAgICAgaWYgKGFwaUJveCkgYXBpQm94LnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICAgIGlmIChhcGlMaW5rKSBhcGlMaW5rLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICB9CiAgfSBjYXRjaChlKSB7CiAgICBlbC5zdHlsZS5ib3JkZXIgPSAnMnB4IHNvbGlkICM4YjI1MjUnOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICcjMWEwYTBhJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyNjMDYwNjAnOwogICAgaWYgKGUubWVzc2FnZSA9PT0gJ3RpbWVvdXQnKSB7CiAgICAgIGVsLmlubmVySFRNTCA9ICchIFNlcnZlciBub3QgcmVzcG9uZGluZycKICAgICAgICArICc8YnI+PHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxNnB4OyI+TWFrZSBzdXJlIGRuZF9hZHZlbnR1cmVfdjQucHkgaXMgcnVubmluZywgdGhlbiBoYXJkIHJlZnJlc2g6IDxzdHJvbmc+Q3RybCtTaGlmdCtSPC9zdHJvbmc+PC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICBlbC5pbm5lckhUTUwgPSAnISAnICsgZS5tZXNzYWdlCiAgICAgICAgKyAnPGJyPjxzcGFuIHN0eWxlPSJmb250LXNpemU6MTZweDsiPlRyeTogc3RvcCB0aGUgc2VydmVyLCBydW4gZG5kX2FkdmVudHVyZV92NC5weSBhZ2FpbiwgdGhlbiA8c3Ryb25nPkN0cmwrU2hpZnQrUjwvc3Ryb25nPjwvc3Bhbj4nOwogICAgfQogICAgLy8gU2hvdyBBUEkga2V5IGJveCBhcyBmYWxsYmFjawogICAgaWYgKGFwaUJveCkgYXBpQm94LnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICBpZiAoYXBpTGluaykgYXBpTGluay5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgY29uc29sZS5lcnJvcignW09sbGFtYSBjaGVja10nLCBlKTsKICB9Cn0KCmZ1bmN0aW9uIHVwZGF0ZUFpSW5kaWNhdG9yKHZpYSwgbW9kZWwpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtYWktaW5kaWNhdG9yJyk7CiAgaWYgKCFlbCkgcmV0dXJuOwogIGlmICh2aWEgPT09ICdvbGxhbWEnKSB7CiAgICBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICcjM2E2YTNhJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyM2YTlhNmEnOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICdyZ2JhKDU4LDEwNiw1OCwwLjEpJzsKICAgIGVsLmlubmVySFRNTCA9ICctIE9sbGFtYSAoJyArIChtb2RlbCB8fCAnbG9jYWwnKSArICcpJzsKICB9IGVsc2UgaWYgKHZpYSA9PT0gJ2NsYXVkZScpIHsKICAgIGVsLnN0eWxlLmJvcmRlckNvbG9yID0gJyM3YTYwMzAnOwogICAgZWwuc3R5bGUuY29sb3IgPSAnI2M5YTg0Yyc7CiAgICBlbC5zdHlsZS5iYWNrZ3JvdW5kID0gJ3JnYmEoMjAxLDE2OCw3NiwwLjA2KSc7CiAgICBlbC5pbm5lckhUTUwgPSAnLSBDbGF1ZGUgQVBJJzsKICB9IGVsc2UgaWYgKHZpYSA9PT0gJ2Vycm9yJykgewogICAgZWwuc3R5bGUuYm9yZGVyQ29sb3IgPSAnIzhiMjUyNSc7CiAgICBlbC5zdHlsZS5jb2xvciA9ICcjYzA2MDYwJzsKICAgIGVsLnN0eWxlLmJhY2tncm91bmQgPSAncmdiYSgxMzksMzcsMzcsMC4wNiknOwogICAgZWwuaW5uZXJIVE1MID0gJyEgQUkgRXJyb3InOwogIH0gZWxzZSB7CiAgICBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICcjM2EzMDIwJzsKICAgIGVsLnN0eWxlLmNvbG9yID0gJyM4YTdhNTgnOwogICAgZWwuaW5uZXJIVE1MID0gJy0gQUk6IGNoZWNraW5nLi4uJzsKICB9Cn0KCmZ1bmN0aW9uIHJvdGF0ZUJhbm5lZFBocmFzZXMoKSB7CiAgLy8gUGljayA1IHJhbmRvbSBwaHJhc2VzIGZyb20gdGhlIHBvb2wgZWFjaCB0aW1lIHRvIGtlZXAgaXQgZnJlc2gKICBjb25zdCBzaHVmZmxlZCA9IFsuLi5CQU5ORURfUEhSQVNFU19QT09MXS5zb3J0KCgpID0+IE1hdGgucmFuZG9tKCkgLSAwLjUpOwogIGJhbm5lZFBocmFzZXMgPSBzaHVmZmxlZC5zbGljZSgwLCA1KTsKfQoKZnVuY3Rpb24gZ2V0Q29sb3IobmFtZSkgewogIGlmICghY29sb3JNYXBbbmFtZV0pIHsKICAgIGNvbnN0IHVzZWQgPSBPYmplY3Qua2V5cyhjb2xvck1hcCkubGVuZ3RoOwogICAgY29sb3JNYXBbbmFtZV0gPSBQTEFZRVJfQ09MT1JTW3VzZWQgJSBQTEFZRVJfQ09MT1JTLmxlbmd0aF07CiAgfQogIHJldHVybiBjb2xvck1hcFtuYW1lXTsKfQoKZnVuY3Rpb24gZ2V0Q29sb3JGb3JDbGFzcyhjbHMpIHsKICBjb25zdCBtYXAgPSB7CiAgICAnRmlnaHRlcic6JyNjOWE4NGMnLCdNYWdpYy1Vc2VyJzonIzdhYmFmZicsJ0NsZXJpYyc6JyNmZmZmZmYnLAogICAgJ1RoaWVmJzonI2ZmYjA3YScsJ1Jhbmdlcic6JyM3YWZmYjAnLCdQYWxhZGluJzonI2ZmZmFhYScsCiAgICAnRHJ1aWQnOicjN2FmZjdhJywnSWxsdXNpb25pc3QnOicjZDk3YWZmJywnQXNzYXNzaW4nOicjZmY3YWFhJywKICAgICdCYXJkJzonI2ZmZGE3YScsJ01vbmsnOicjYWFmZmZmJywnQmFyYmFyaWFuJzonI2ZmOWE3YScsCiAgICAnQWNyb2JhdCc6JyNjMGMwZmYnLCdLbmlnaHQnOicjZmZlMGEwJywKICB9OwogIHJldHVybiBtYXBbY2xzXSB8fCAnI2M5YTg0Yyc7Cn0KCmZ1bmN0aW9uIHNob3dDaGFyU2VsZWN0KGNvbnRleHQsIGNvbnRleHRMYWJlbCwgcGVuZGluZ0RhdGEpIHsKICBjc2VsU2VsZWN0ZWRJZCA9IG51bGw7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NzZWwtdXNlLWJ0bicpLmRpc2FibGVkID0gdHJ1ZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1wcmV2aWV3Jykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1tb2R1bGUnKS50ZXh0Q29udGVudCA9IGNvbnRleHRMYWJlbDsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC1jb250ZXh0JykudGV4dENvbnRlbnQgPSBjb250ZXh0OwoKICBzaG93KCdzLWNoYXJzZWxlY3QnKTsKCiAgLy8gTG9hZCBjaGFyYWN0ZXJzIGZyb20gc2VydmVyCiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NoYXJhY3RlcnMnKS50aGVuKHI9PnIuanNvbigpKS50aGVuKGNoYXJzID0+IHsKICAgIGNzZWxDaGFycyA9IGNoYXJzOwogICAgY29uc3QgbGlzdCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjc2VsLWxpc3QnKTsKICAgIGlmICghY2hhcnMubGVuZ3RoKSB7CiAgICAgIGxpc3QuaW5uZXJIVE1MID0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2NvbG9yOnZhcigtLWRpbSk7Ym9yZGVyOjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpO3BhZGRpbmc6MTBweDtiYWNrZ3JvdW5kOnZhcigtLXBhbmVsKTsiPk5vIHNhdmVkIGNoYXJhY3RlcnMgeWV0LiBDcmVhdGUgYSBuZXcgb25lIGJlbG93LjwvZGl2Pic7CiAgICB9IGVsc2UgewogICAgICBsaXN0LmlubmVySFRNTCA9IGNoYXJzLm1hcChjID0+IHsKICAgICAgICBjb25zdCBjb2wgPSBnZXRDb2xvckZvckNsYXNzKGMuY2xzKTsKICAgICAgICByZXR1cm4gYDxkaXYgY2xhc3M9ImNzZWwtaXRlbSIgaWQ9ImNpLSR7Yy5pZH0iIG9uY2xpY2s9InByZXZpZXdDaGFyKCcke2MuaWR9JykiPgogICAgICAgICAgPGRpdj4KICAgICAgICAgICAgPGRpdiBjbGFzcz0iY2ktbmFtZSI+JHtjLm5hbWV9PC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9ImNpLXN1YiI+CiAgICAgICAgICAgICAgTGV2ZWwgJHtjLmxldmVsfSAke2MucmFjZX0gJHtjLmNsc30gJm5ic3A7KiZuYnNwOyAke2MuYWxpZ259CiAgICAgICAgICAgICAgJm5ic3A7KiZuYnNwOyBIUCAke2MuaHB9LyR7Yy5tYXhocH0gJm5ic3A7KiZuYnNwOyBBQyAke2MuYWN9ICZuYnNwOyombmJzcDsgJHtjLmdvbGR9Z3AKICAgICAgICAgICAgICA8YnI+TGFzdCBwbGF5ZWQ6ICR7bmV3IERhdGUoYy5zYXZlZEF0KS50b0xvY2FsZURhdGVTdHJpbmcoKX0KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxzcGFuIGNsYXNzPSJjaS1iYWRnZSIgc3R5bGU9ImJvcmRlci1jb2xvcjoke2NvbH07Y29sb3I6JHtjb2x9OyI+JHtjLmNsc308L3NwYW4+CiAgICAgICAgPC9kaXY+YDsKICAgICAgfSkuam9pbignJyk7CiAgICB9CiAgfSk7CgogIC8vIFN0b3JlIHBlbmRpbmcgYWN0aW9uCiAgaWYgKHBlbmRpbmdEYXRhICYmIHBlbmRpbmdEYXRhLnR5cGUgPT09ICdzYXZlJykgY3NlbFBlbmRpbmdTYXZlID0gcGVuZGluZ0RhdGE7CiAgaWYgKHBlbmRpbmdEYXRhICYmIHBlbmRpbmdEYXRhLnR5cGUgPT09ICdqb2luJykgY3NlbFBlbmRpbmdKb2luID0gcGVuZGluZ0RhdGE7Cn0KCmZ1bmN0aW9uIHByZXZpZXdDaGFyKGlkKSB7CiAgLy8gRGVzZWxlY3QgYWxsCiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLmNzZWwtaXRlbScpLmZvckVhY2goZWwgPT4gZWwuY2xhc3NMaXN0LnJlbW92ZSgnc2VsJykpOwogIGNvbnN0IGl0ZW0gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2ktJyArIGlkKTsKICBpZiAoaXRlbSkgaXRlbS5jbGFzc0xpc3QuYWRkKCdzZWwnKTsKCiAgY3NlbFNlbGVjdGVkSWQgPSBpZDsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3NlbC11c2UtYnRuJykuZGlzYWJsZWQgPSBmYWxzZTsKCiAgLy8gRmluZCBjaGFyIGRhdGEKICBjb25zdCBjID0gY3NlbENoYXJzLmZpbmQoeCA9PiB4LmlkID09PSBpZCk7CiAgaWYgKCFjKSByZXR1cm47CgogIC8vIExvYWQgZnVsbCBjaGFyYWN0ZXIgZnJvbSBzZXJ2ZXIKICB4aHJGZXRjaChCQVNFX1VSTCArICcvY2hhcmFjdGVyP2lkPScgKyBlbmNvZGVVUklDb21wb25lbnQoaWQpKS50aGVuKHI9PnIuanNvbigpKS50aGVuKGZ1bGwgPT4gewogICAgY29uc3QgcHJldiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjc2VsLXByZXZpZXcnKTsKICAgIHByZXYuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKCiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtbmFtZScpLnRleHRDb250ZW50ID0gZnVsbC5uYW1lOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWNsYXNzJykudGV4dENvbnRlbnQgPQogICAgICBgTGV2ZWwgJHtmdWxsLmxldmVsfSAke2Z1bGwucmFjZX0gJHtmdWxsLmNsc31gOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWFsaWduJykudGV4dENvbnRlbnQgPQogICAgICBgQWxpZ25tZW50OiAke2Z1bGwuYWxpZ24gfHwgJz8nfSAqIFNhdmVzOiBEZWF0aCAke2Z1bGwuc2F2ZXM/LmR8fCc/J30sIFdhbmRzICR7ZnVsbC5zYXZlcz8ud3x8Jz8nfSwgUGFyYWx5c2lzICR7ZnVsbC5zYXZlcz8ucHx8Jz8nfSwgQnJlYXRoICR7ZnVsbC5zYXZlcz8uYnx8Jz8nfSwgU3BlbGxzICR7ZnVsbC5zYXZlcz8uc3x8Jz8nfWA7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtaHAnKS50ZXh0Q29udGVudCA9IGAke2Z1bGwuaHB9LyR7ZnVsbC5tYXhocH1gOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWFjJykudGV4dENvbnRlbnQgPSBmdWxsLmFjOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NwcmV2LWdvbGQnKS50ZXh0Q29udGVudCA9IGZ1bGwuZ29sZDsKCiAgICAvLyBTdGF0cyBncmlkCiAgICBjb25zdCBzdGF0cyA9IGZ1bGwuc3RhdHMgfHwge307CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtc3RhdHMnKS5pbm5lckhUTUwgPQogICAgICBbJ1NUUicsJ0RFWCcsJ0NPTicsJ0lOVCcsJ1dJUycsJ0NIQSddLm1hcChzID0+IHsKICAgICAgICBjb25zdCB2ID0gc3RhdHNbc10gfHwgMTA7CiAgICAgICAgY29uc3QgbSA9IE1hdGguZmxvb3IoKHYtMTApLzIpOwogICAgICAgIGNvbnN0IG1jID0gbSA+IDAgPyAnY29sb3I6IzZhOWE2YScgOiBtIDwgMCA/ICdjb2xvcjojOWE0YTRhJyA6ICcnOwogICAgICAgIHJldHVybiBgPGRpdiBjbGFzcz0ic3RhdC1taW5pIj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNtbiI+JHtzfTwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0ic212Ij4ke3Z9PC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzbW0iIHN0eWxlPSIke21jfSI+JHttPj0wPycrJyttOm19PC9kaXY+CiAgICAgICAgPC9kaXY+YDsKICAgICAgfSkuam9pbignJyk7CgogICAgLy8gSW52ZW50b3J5CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY3ByZXYtaW52JykudGV4dENvbnRlbnQgPSAoZnVsbC5pbnYgfHwgW10pLmpvaW4oJywgJykgfHwgJ0VtcHR5JzsKCiAgICAvLyBSYWNpYWwgc3BlY2lhbHMKICAgIGNvbnN0IHNwZWNzID0gZnVsbC5zcGVjaWFscyB8fCBbXTsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjcHJldi1zcGVjaWFscycpLnRleHRDb250ZW50ID0KICAgICAgc3BlY3MubGVuZ3RoID8gJyAnICsgc3BlY3Muam9pbignICogJykgOiAnJzsKICB9KTsKfQoKZnVuY3Rpb24gdXNlU2VsZWN0ZWRDaGFyKCkgewogIGlmICghY3NlbFNlbGVjdGVkSWQpIHJldHVybjsKICBjb25zdCBjID0gY3NlbENoYXJzLmZpbmQoeCA9PiB4LmlkID09PSBjc2VsU2VsZWN0ZWRJZCk7CiAgaWYgKCFjKSByZXR1cm47CgogIC8vIExvYWQgdGhlIGZ1bGwgY2hhcmFjdGVyCiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NoYXJhY3Rlcj9pZD0nICsgZW5jb2RlVVJJQ29tcG9uZW50KGNzZWxTZWxlY3RlZElkKSkudGhlbihyPT5yLmpzb24oKSkudGhlbihmdWxsID0+IHsKICAgIHBjID0gZnVsbDsKCiAgICBpZiAoY3NlbFBlbmRpbmdTYXZlKSB7CiAgICAgIC8vIENvbWluZyBmcm9tIExvYWQgR2FtZSAtLSByZXN0b3JlIHRoZSBmdWxsIHNhdmUgd2l0aCB0aGlzIGNoYXJhY3RlcgogICAgICBjb25zdCBkYXRhID0gY3NlbFBlbmRpbmdTYXZlLmRhdGE7CiAgICAgIHBjID0gZnVsbDsgLy8gdXNlIHNlbGVjdGVkIGNoYXIsIG5vdCB0aGUgc2F2ZWQgb25lCiAgICAgIG1vZHVsZVRleHQgPSBkYXRhLm1vZHVsZVRleHQgfHwgJyc7CiAgICAgIG1vZHVsZU5hbWUgPSBkYXRhLm1vZHVsZU5hbWUgfHwgJyc7CiAgICAgIGNob3NlblJ1bGVzID0gZGF0YS5jaG9zZW5SdWxlcyB8fCAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwogICAgICBwYXJ0eVBDcyA9IGRhdGEucGFydHlQQ3MgfHwge307CiAgICAgIC8vIEluamVjdCBvdXIgc2VsZWN0ZWQgY2hhcmFjdGVyIGFzIHRoZSBwbGF5ZXIncyBQQwogICAgICBwYXJ0eVBDc1twbGF5ZXJOYW1lXSA9IHBjOwogICAgICBoaXN0b3J5ID0gZGF0YS5oaXN0b3J5IHx8IFtdOwogICAgICBzeXN0ZW1Qcm9tcHQgPSBkYXRhLnN5c3RlbVByb21wdCB8fCAnJzsKICAgICAgaXNNdWx0aXBsYXllciA9IGRhdGEuaXNNdWx0aXBsYXllciB8fCBmYWxzZTsKICAgICAgLy8gUmVzdG9yZSBtZW1vcnkgc3lzdGVtCiAgICAgIG1lbW9yeVN1bW1hcnkgPSBkYXRhLm1lbW9yeVN1bW1hcnkgfHwgJyc7CiAgICAgIHdvcmxkU3RhdGUgPSBkYXRhLndvcmxkU3RhdGUgfHwgeyBucGNzX21ldDp7fSwgbG9jYXRpb25zX3Zpc2l0ZWQ6e30sIGl0ZW1zX2ZvdW5kOltdLCBwbG90X3BvaW50czpbXSwgZG9vcnNfb3BlbmVkOltdLCB0cmFwc19zcHJ1bmc6W10sIG1vbnN0ZXJzX2tpbGxlZDpbXSwgcXVlc3RzX2FjdGl2ZTpbXSwgd29ybGRfY2hhbmdlczpbXSB9OwogICAgICBwaW5uZWRGYWN0cyA9IGRhdGEucGlubmVkRmFjdHMgfHwgW107CiAgICAgIHR1cm5Db3VudCA9IGRhdGEudHVybkNvdW50IHx8IDA7CiAgICAgIG5wY1Byb2ZpbGVzID0gZGF0YS5ucGNQcm9maWxlcyB8fCB7fTsKICAgICAgbG9jYXRpb25BdG1vc3BoZXJlID0gZGF0YS5sb2NhdGlvbkF0bW9zcGhlcmUgfHwge307CiAgICAgIHNlc3Npb25Ub25lID0gZGF0YS5zZXNzaW9uVG9uZSB8fCAnZXhwbG9yYXRvcnknOwogICAgICBnbUJyaWVmaW5nID0gZGF0YS5nbUJyaWVmaW5nIHx8ICcnOwogICAgICBucGNLbm93bGVkZ2VNYXAgPSBkYXRhLm5wY0tub3dsZWRnZU1hcCB8fCB7fTsKICAgICAgcGFjaW5nSGlzdG9yeSA9IGRhdGEucGFjaW5nSGlzdG9yeSB8fCBbXTsKICAgICAgY3VycmVudFBhY2luZ1BoYXNlID0gZGF0YS5jdXJyZW50UGFjaW5nUGhhc2UgfHwgJ29wZW5pbmcnOwogICAgICBjb25zZXF1ZW5jZXMgPSBkYXRhLmNvbnNlcXVlbmNlcyB8fCBbXTsKICAgICAgaW5Db21iYXQgPSBkYXRhLmluQ29tYmF0IHx8IGZhbHNlOwogICAgICBjb21iYXRTdGF0ZSA9IGRhdGEuY29tYmF0U3RhdGUgfHwgeyByb3VuZDowLCBpbml0aWF0aXZlT3JkZXI6W10sIGFjdGl2ZUluZGV4OjAsIHBsYXllckFjdGlvbjonJywgbGFzdFJvdW5kU3VtbWFyeTonJyB9OwogICAgICBkdW5nZW9uVHVybnMgPSBkYXRhLmR1bmdlb25UdXJucyB8fCAwOwogICAgICB0b3JjaFR1cm5zTGVmdCA9IGRhdGEudG9yY2hUdXJuc0xlZnQgIT09IHVuZGVmaW5lZCA/IGRhdGEudG9yY2hUdXJuc0xlZnQgOiAxODsKICAgICAgaGFzTGFudGVybiA9IGRhdGEuaGFzTGFudGVybiB8fCBmYWxzZTsKICAgICAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSBkYXRhLmxhbnRlcm5PaWxGbGFza3NMZWZ0IHx8IDA7CiAgICAgIHJhdGlvbnNMZWZ0ID0gZGF0YS5yYXRpb25zTGVmdCB8fCAwOwogICAgICByZXN0RGVidCA9IGRhdGEucmVzdERlYnQgfHwgMDsKICAgICAgd2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyID0gZGF0YS53YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgfHwgMDsKCiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtbW9kJykudGV4dENvbnRlbnQgPSBtb2R1bGVOYW1lOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgc2hvd1Jvb21Db2RlKCk7CiAgICAgIHNob3coJ3MtZ2FtZScpOwogICAgICB1cGRhdGVIVUQoKTsKICAgICAgcmVuZGVyUGFydHlQYW5lbCgpOwogICAgICBjb25zdCBsb2cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbG9nJyk7CiAgICAgIGxvZy5pbm5lckhUTUwgPSAnJzsKICAgICAgKGRhdGEubG9nRW50cmllcyB8fCBbXSkuZm9yRWFjaChlID0+IGFkZEVudHJ5UmF3KGUuaHRtbCwgZS50eXBlLCBlLmF1dGhvcikpOwogICAgICBsb2cuc2Nyb2xsVG9wID0gbG9nLnNjcm9sbEhlaWdodDsKICAgICAgYWRkRW50cnlSYXcoJyBBZHZlbnR1cmUgcmVzdG9yZWQuIFBsYXlpbmcgYXMgPHN0cm9uZz4nICsgcGMubmFtZSArICc8L3N0cm9uZz4uJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgaWYgKGlzTXVsdGlwbGF5ZXIgJiYgcm9vbUNvZGUpIHN0YXJ0UG9sbGluZygpOwogICAgICBjc2VsUGVuZGluZ1NhdmUgPSBudWxsOwoKICAgIH0gZWxzZSBpZiAoY3NlbFBlbmRpbmdKb2luKSB7CiAgICAgIC8vIENvbWluZyBmcm9tIEpvaW4gUm9vbSAtLSB1c2UgdGhpcyBjaGFyYWN0ZXIgaW4gdGhlIHJvb20KICAgICAgY29uc3QgZGF0YSA9IGNzZWxQZW5kaW5nSm9pbi5kYXRhOwogICAgICByb29tQ29kZSA9IGRhdGEuY29kZTsKICAgICAgaXNNdWx0aXBsYXllciA9IHRydWU7CiAgICAgIGlzSG9zdCA9IGZhbHNlOwogICAgICBtb2R1bGVOYW1lID0gZGF0YS5tb2R1bGVOYW1lIHx8ICcnOwogICAgICBjaG9zZW5SdWxlcyA9IGRhdGEuY2hvc2VuUnVsZXMgfHwgJ09TRSBBZHZhbmNlZCBGYW50YXN5JzsKICAgICAgbW9kdWxlVGV4dCA9IGRhdGEubW9kdWxlVGV4dCB8fCAnJzsKICAgICAgbG9hZGVkTW9kdWxlRGF0YSA9IGRhdGEubW9kdWxlRGF0YSB8fCB7fTsKICAgICAgc3lzdGVtUHJvbXB0ID0gZGF0YS5zeXN0ZW1Qcm9tcHQgfHwgJyc7CgogICAgICBpZiAoZGF0YS5nYW1lQWN0aXZlKSB7CiAgICAgICAgcGFydHlQQ3MgPSBkYXRhLnBhcnR5UENzIHx8IHt9OwogICAgICAgIHBhcnR5UENzW3BsYXllck5hbWVdID0gcGM7CiAgICAgICAgaGlzdG9yeSA9IGRhdGEuaGlzdG9yeSB8fCBbXTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLW1vZCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICAgICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgICBzaG93KCdzLWdhbWUnKTsKICAgICAgICB1cGRhdGVIVUQoKTsKICAgICAgICByZW5kZXJQYXJ0eVBhbmVsKCk7CiAgICAgICAgKGRhdGEubG9nRW50cmllcyB8fCBbXSkuZm9yRWFjaChlID0+IGFkZEVudHJ5UmF3KGUuaHRtbCwgZS50eXBlLCBlLmF1dGhvcikpOwogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsb2cnKS5zY3JvbGxUb3AgPSA5OTk5OTsKICAgICAgICAvLyBSZWdpc3RlciBjaGFyYWN0ZXIgaW4gcm9vbQogICAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9wbGF5ZXJfcmVhZHknLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lLCBwY30pfSk7CiAgICAgICAgc3RhcnRQb2xsaW5nKCk7CiAgICAgIH0gZWxzZSB7CiAgICAgICAgLy8gR2FtZSBub3Qgc3RhcnRlZCB5ZXQgLS0gZ28gdG8gY2hhciBzY3JlZW4gYnV0IHByZS1maWxsIHdpdGggc2VsZWN0ZWQgY2hhcgogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21wLWNoYXItbm90ZScpLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogICAgICAgIHNob3coJ3MtY2hhcicpOwogICAgICAgIGJ1aWxkQ2hhckNyZWF0ZSgpOwogICAgICAgIC8vIFByZS1wb3B1bGF0ZSBjaGFyIG5hbWUgYW5kIG1hcmsgYXMgcmVhZHkgd2l0aCB0aGlzIGNoYXJhY3RlcgogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbmFtZS1pbnAnKS52YWx1ZSA9IHBjLm5hbWU7CiAgICAgICAgLy8gUmVnaXN0ZXIgaW4gcm9vbQogICAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9wbGF5ZXJfcmVhZHknLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOiByb29tQ29kZSwgcGxheWVyOiBwbGF5ZXJOYW1lLCBwY30pfSk7CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3JlYWR5LWJ0bicpLnRleHRDb250ZW50ID0gJyBVc2luZyAnICsgcGMubmFtZTsKICAgICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJykuZGlzYWJsZWQgPSB0cnVlOwogICAgICAgIHN0YXJ0UG9sbGluZygpOwogICAgICB9CiAgICAgIGNzZWxQZW5kaW5nSm9pbiA9IG51bGw7CiAgICB9CiAgfSk7Cn0KCmZ1bmN0aW9uIHNob3dDaGFyQ3JlYXRlKCkgewogIC8vIEZyb20gY2hhciBzZWxlY3Qgc2NyZWVuLCBnbyB0byBmdWxsIGNoYXJhY3RlciBjcmVhdGlvbgogIGlmIChjc2VsUGVuZGluZ0pvaW4pIHsKICAgIGNvbnN0IGRhdGEgPSBjc2VsUGVuZGluZ0pvaW4uZGF0YTsKICAgIHJvb21Db2RlID0gZGF0YS5jb2RlOwogICAgaXNNdWx0aXBsYXllciA9IHRydWU7CiAgICBpc0hvc3QgPSBmYWxzZTsKICAgIG1vZHVsZU5hbWUgPSBkYXRhLm1vZHVsZU5hbWUgfHwgJyc7CiAgICBjaG9zZW5SdWxlcyA9IGRhdGEuY2hvc2VuUnVsZXMgfHwgJ09TRSBBZHZhbmNlZCBGYW50YXN5JzsKICAgIG1vZHVsZVRleHQgPSBkYXRhLm1vZHVsZVRleHQgfHwgJyc7CiAgICBsb2FkZWRNb2R1bGVEYXRhID0gZGF0YS5tb2R1bGVEYXRhIHx8IGxvYWRlZE1vZHVsZURhdGEgfHwge307CiAgICBzeXN0ZW1Qcm9tcHQgPSBkYXRhLnN5c3RlbVByb21wdCB8fCAnJzsKICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKS50ZXh0Q29udGVudCA9IG1vZHVsZU5hbWU7CiAgICBjb25zdCBtcE5vdGUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbXAtY2hhci1ub3RlJyk7CiAgICBpZiAobXBOb3RlKSBtcE5vdGUuc3R5bGUuZGlzcGxheSA9ICdibG9jayc7CiAgICBzdGFydFBvbGxpbmcoKTsKICB9IGVsc2UgaWYgKGNzZWxQZW5kaW5nU2F2ZSkgewogICAgLy8gQ3JlYXRpbmcgbmV3IGNoYXIgZm9yIGEgbG9hZGVkIHNhdmUgLS0gc3RpbGwgbG9hZCB0aGUgbW9kdWxlCiAgICBjb25zdCBkYXRhID0gY3NlbFBlbmRpbmdTYXZlLmRhdGE7CiAgICBtb2R1bGVOYW1lID0gZGF0YS5tb2R1bGVOYW1lIHx8ICcnOwogICAgbW9kdWxlVGV4dCA9IGRhdGEubW9kdWxlVGV4dCB8fCAnJzsKICAgIGNob3NlblJ1bGVzID0gZGF0YS5jaG9zZW5SdWxlcyB8fCAnT1NFIEFkdmFuY2VkIEZhbnRhc3knOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NoYXItbW9kdWxlLWxibCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICB9CiAgY3NlbFBlbmRpbmdTYXZlID0gbnVsbDsKICBjc2VsUGVuZGluZ0pvaW4gPSBudWxsOwogIHNob3coJ3MtY2hhcicpOwogIGJ1aWxkQ2hhckNyZWF0ZSgpOwp9Cgphc3luYyBmdW5jdGlvbiBsb2FkRG5kbW9kTGlzdCgpIHsKICBjb25zdCBsaXN0RWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZG5kbW9kLWxpc3QnKTsKICBjb25zdCBlbXB0eUVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2RuZG1vZC1lbXB0eScpOwogIGxpc3RFbC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogIGxpc3RFbC5pbm5lckhUTUwgPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Y29sb3I6dmFyKC0tZGltKSI+TG9hZGluZy4uLjwvZGl2Pic7CgogIGxldCBtb2RzOwogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2xpc3RfbW9kdWxlcycpOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgLy8gU2VydmVyIHJldHVybnMge21vZHVsZXM6Wy4uLl19IC0tIHVud3JhcCBpdAogICAgbW9kcyA9IEFycmF5LmlzQXJyYXkoZGF0YSkgPyBkYXRhIDogKGRhdGEubW9kdWxlcyB8fCBbXSk7CiAgfSBjYXRjaChlKSB7CiAgICBsaXN0RWwuaW5uZXJIVE1MID0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNnB4O2NvbG9yOiNjMDYwNjAiPkNvdWxkIG5vdCBsb2FkIG1vZHVsZSBsaXN0OiAnICsgZS5tZXNzYWdlICsgJzwvZGl2Pic7CiAgICByZXR1cm47CiAgfQoKICBpZiAoIW1vZHMubGVuZ3RoKSB7CiAgICBsaXN0RWwuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIGlmIChlbXB0eUVsKSBlbXB0eUVsLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICByZXR1cm47CiAgfQogIGlmIChlbXB0eUVsKSBlbXB0eUVsLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgbGlzdEVsLmlubmVySFRNTCA9IG1vZHMubWFwKG0gPT4gewogICAgLy8gTm9ybWFsaXNlIGZpZWxkIG5hbWVzIC0tIHNlcnZlciB1c2VzIHtmaWxlLCB0aXRsZSwgbGV2ZWwsIHN5c3RlbX0KICAgIGNvbnN0IGZuYW1lICAgID0gbS5maWxlIHx8IG0uZmlsZW5hbWUgfHwgJyc7CiAgICBjb25zdCB0aXRsZSAgICA9IG0udGl0bGUgfHwgZm5hbWU7CiAgICBjb25zdCBsZXZlbCAgICA9IG0ubGV2ZWwgfHwgbS5sZXZlbF9yYW5nZSB8fCAnJzsKICAgIGNvbnN0IHN5c3RlbSAgID0gbS5zeXN0ZW0gfHwgJ09TRSc7CiAgICBjb25zdCBzYWZlVGl0bGUgPSB0aXRsZS5yZXBsYWNlKC8nL2csICImIzM5OyIpOwogICAgcmV0dXJuIGAKICAgIDxkaXYgc3R5bGU9ImJhY2tncm91bmQ6dmFyKC0tYmcpO2JvcmRlcjoxcHggc29saWQgdmFyKC0tYm9yZGVyKTtwYWRkaW5nOjEwcHggMTJweDtjdXJzb3I6cG9pbnRlcjsKICAgICAgdHJhbnNpdGlvbjpib3JkZXItY29sb3IgLjE1czsiIGlkPSJtb2QtJHtmbmFtZX0iCiAgICAgIG9ubW91c2VlbnRlcj0idGhpcy5zdHlsZS5ib3JkZXJDb2xvcj0ndmFyKC0tZ29sZCknIgogICAgICBvbm1vdXNlbGVhdmU9InRoaXMuc3R5bGUuYm9yZGVyQ29sb3I9J3ZhcigtLWJvcmRlciknIgogICAgICBvbmNsaWNrPSJzZWxlY3REbmRtb2QoJyR7Zm5hbWV9JywnJHtzYWZlVGl0bGV9JykiPgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MThweDtjb2xvcjp2YXIoLS1pbmspO2ZvbnQtZmFtaWx5OidJTSBGZWxsIEVuZ2xpc2gnLHNlcmlmIj4ke3RpdGxlfTwvZGl2PgogICAgICA8ZGl2IHN0eWxlPSJmb250LXNpemU6MTNweDtjb2xvcjp2YXIoLS1kaW0pO21hcmdpbi10b3A6M3B4OyI+JHtzeXN0ZW19ICZuYnNwOyombmJzcDsgJHtsZXZlbCB8fCAnQW55IGxldmVsJ308L2Rpdj4KICAgIDwvZGl2PmA7CiAgfSkuam9pbignJyk7Cn0KCmFzeW5jIGZ1bmN0aW9uIHNlbGVjdERuZG1vZChmaWxlbmFtZSwgdGl0bGUpIHsKICAvLyBIaWdobGlnaHQgc2VsZWN0ZWQKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcjZG5kbW9kLWxpc3QgPiBkaXYnKS5mb3JFYWNoKGVsID0+IHsKICAgIGVsLnN0eWxlLmJvcmRlckNvbG9yID0gJ3ZhcigtLWJvcmRlciknOwogICAgZWwuc3R5bGUuYmFja2dyb3VuZCA9ICd2YXIoLS1iZyknOwogIH0pOwogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21vZC0nICsgZmlsZW5hbWUpOwogIGlmIChlbCkgeyBlbC5zdHlsZS5ib3JkZXJDb2xvciA9ICd2YXIoLS1nb2xkKSc7IGVsLnN0eWxlLmJhY2tncm91bmQgPSAncmdiYSgyMDEsMTY4LDc2LDAuMDgpJzsgfQoKICBzZWxlY3RlZERuZG1vZEZpbGUgPSBmaWxlbmFtZTsKICBtb2R1bGVOYW1lID0gdGl0bGU7CgogIC8vIFNob3cgbG9hZGluZyBzdGF0dXMgaW4gdGhlIG1vZHVsZSBjYXJkIGl0c2VsZgogIGNvbnN0IG1vZENhcmQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbW9kLScgKyBmaWxlbmFtZSk7CiAgaWYgKG1vZENhcmQpIG1vZENhcmQuaW5uZXJIVE1MICs9ICc8ZGl2IHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1nb2xkKTttYXJnaW4tdG9wOjRweDsiPkxvYWRpbmcuLi48L2Rpdj4nOwoKICAvLyBMb2FkIHRoZSBtb2R1bGUgZGF0YSBmcm9tIHNlcnZlcgogIGxldCByZXN1bHQ7CiAgdHJ5IHsKICAgIHJlc3VsdCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9sb2FkX21vZHVsZT9maWxlPScgKyBlbmNvZGVVUklDb21wb25lbnQoZmlsZW5hbWUpKS50aGVuKHI9PnIuanNvbigpKTsKICB9IGNhdGNoKGUpIHsKICAgIGlmIChtb2RDYXJkKSBtb2RDYXJkLmlubmVySFRNTCArPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE0cHg7Y29sb3I6I2MwNjA2MDsiPkVycm9yOiAnICsgZS5tZXNzYWdlICsgJzwvZGl2Pic7CiAgICByZXR1cm47CiAgfQoKICBpZiAocmVzdWx0LmVycm9yKSB7CiAgICBpZiAobW9kQ2FyZCkgbW9kQ2FyZC5pbm5lckhUTUwgKz0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O2NvbG9yOiNjMDYwNjA7Ij5FcnJvcjogJyArIHJlc3VsdC5lcnJvciArICc8L2Rpdj4nOwogICAgcmV0dXJuOwogIH0KCiAgbW9kdWxlVGV4dCA9IHJlc3VsdC50ZXh0IHx8ICcnOwogIG1vZHVsZU5hbWUgPSByZXN1bHQudGl0bGUgfHwgJyc7CiAgbG9hZGVkTW9kdWxlRGF0YSA9IHJlc3VsdC5kYXRhIHx8IHt9OwogIGNvbnNvbGUubG9nKCdbc2VsZWN0RG5kbW9kXSBtb2R1bGVUZXh0IGxlbmd0aDonLCBtb2R1bGVUZXh0Lmxlbmd0aCwgJ3wgbW9kdWxlTmFtZTonLCBtb2R1bGVOYW1lLCAnfCBkYXRhIGtleXM6JywgT2JqZWN0LmtleXMobG9hZGVkTW9kdWxlRGF0YSkubGVuZ3RoKTsKICBpZiAoIW1vZHVsZVRleHQpIHsKICAgIGlmIChtb2RDYXJkKSBtb2RDYXJkLmlubmVySFRNTCArPSAnPGRpdiBzdHlsZT0iY29sb3I6I2MwNjA2MDtmb250LXNpemU6MTRweDsiPldhcm5pbmc6IG1vZHVsZSB0ZXh0IGVtcHR5ITwvZGl2Pic7CiAgfQoKICAvLyBQdXNoIG1vZHVsZSB0byByb29tIHNvIGd1ZXN0cyBnZXQgaXQgdG9vCiAgaWYgKHJvb21Db2RlKSB7CiAgICBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvdXBkYXRlX3Jvb20nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGU6cm9vbUNvZGUsIG1vZHVsZVRleHQsIG1vZHVsZU5hbWUsIGNob3NlblJ1bGVzLCBtb2R1bGVEYXRhOiBsb2FkZWRNb2R1bGVEYXRhfSl9KTsKICB9CgogIC8vIEVuYWJsZSB0aGUgQ29udGludWUgYnV0dG9uIGFuZCBzaG93IGNvbmZpcm1hdGlvbgogIHNldFRpbWVvdXQoKCkgPT4gewogICAgY29uc3QgYnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ25leHQtYnRuJyk7CiAgICBpZiAoYnRuKSB7IGJ0bi5kaXNhYmxlZCA9IGZhbHNlOyBidG4uc3R5bGUub3BhY2l0eSA9ICcxJzsgYnRuLnRleHRDb250ZW50ID0gJyAnICsgbW9kdWxlTmFtZSArICcgLS0gQ3JlYXRlIENoYXJhY3RlciAnOyB9CiAgfSwgNDAwKTsKfQoKZnVuY3Rpb24gcHJvY2VlZFRvQ2hhckNyZWF0ZSgpIHsKICBpZiAoIW1vZHVsZVRleHQgfHwgbW9kdWxlVGV4dC5sZW5ndGggPCAxMCkgewogICAgYWxlcnQoJ1BsZWFzZSBzZWxlY3QgYSBtb2R1bGUgZmlyc3QuJyk7CiAgICByZXR1cm47CiAgfQogIGNvbnN0IGNtbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKTsKICBpZiAoY21sKSBjbWwudGV4dENvbnRlbnQgPSBtb2R1bGVOYW1lOwogIHNob3coJ3MtY2hhcicpOwogIGJ1aWxkQ2hhckNyZWF0ZSgpOwp9CgpmdW5jdGlvbiBnb1RvTmV3R2FtZSgpIHsKICAvLyBJbml0aWFsaXNlIHNlc3Npb24gc3RhdGUgc2lsZW50bHkgKG5vIG5hbWUgcmVxdWlyZWQgeWV0KQogIGlmICghcGxheWVyTmFtZSkgcGxheWVyTmFtZSA9ICdBZHZlbnR1cmVyJzsKICBpc0hvc3QgPSBvbGxhbWFBdmFpbGFibGUgfHwgISFhcGlLZXk7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBjaG9zZW5SdWxlcyA9ICdPU0UnOwogIC8vIEF1dG8tZ2VuZXJhdGUgcm9vbSBjb2RlCiAgaWYgKCFyb29tQ29kZSkgYXV0b0dlbmVyYXRlUm9vbSgpOwogIHNob3coJ3MtbmV3Z2FtZScpOwogIGxvYWREbmRtb2RMaXN0KCk7Cn0KCmZ1bmN0aW9uIGdvVG9Mb2FkKCkgewogIGlmICghcGxheWVyTmFtZSkgcGxheWVyTmFtZSA9ICdBZHZlbnR1cmVyJzsKICBpc0hvc3QgPSBvbGxhbWFBdmFpbGFibGUgfHwgISFhcGlLZXk7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBzaG93TG9hZCgpOwp9CgpmdW5jdGlvbiBqb2luUm9vbUZyb21Mb2JieSgpIHsKICBjb25zdCBjb2RlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpLnZhbHVlLnRyaW0oKS50b1VwcGVyQ2FzZSgpOwogIGlmICghY29kZSkgeyBhbGVydCgnRW50ZXIgYSByb29tIGNvZGUuJyk7IHJldHVybjsgfQogIC8vIEluaXRpYWxpc2Ugc3RhdGUgZm9yIGd1ZXN0CiAgaWYgKCFwbGF5ZXJOYW1lKSBwbGF5ZXJOYW1lID0gJ1BsYXllcic7CiAgaXNIb3N0ID0gZmFsc2U7CiAgdXNlT2xsYW1hID0gISF3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZTsKICBjaG9zZW5SdWxlcyA9ICdPU0UnOwogIC8vIFB1dCBjb2RlIGluIHRoZSBqb2luIGZpZWxkIGFuZCBjYWxsIGpvaW5Sb29tCiAgY29uc3Qgam9pbkZpZWxkID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpOwogIGlmIChqb2luRmllbGQpIGpvaW5GaWVsZC52YWx1ZSA9IGNvZGU7CiAgam9pblJvb20oKTsKfQoKYXN5bmMgZnVuY3Rpb24gYXV0b0dlbmVyYXRlUm9vbSgpIHsKICAvLyBTaWxlbnRseSBnZW5lcmF0ZSBhIHJvb20gY29kZSB3aXRob3V0IG5lZWRpbmcgYSBwbGF5ZXIgbmFtZSB5ZXQKICB0cnkgewogICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9jcmVhdGVfcm9vbScsIHttZXRob2Q6J1BPU1QnLAogICAgICBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7aG9zdDogcGxheWVyTmFtZSB8fCAnUm9vbSd9KX0pOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgaWYgKGRhdGEuY29kZSkgewogICAgICByb29tQ29kZSA9IGRhdGEuY29kZTsKICAgICAgaXNIb3N0ID0gdHJ1ZTsKICAgICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm9vbS1jb2RlLWRpc3AnKTsKICAgICAgaWYgKGVsKSBlbC50ZXh0Q29udGVudCA9IHJvb21Db2RlOwogICAgICBzaG93Um9vbUNvZGUoKTsKICAgICAgY2hlY2tOZ3Jva1N0YXR1cygpOwogICAgfQogIH0gY2F0Y2goZSkgeyBjb25zb2xlLmxvZygnYXV0b0dlbmVyYXRlUm9vbSBlcnJvcjonLCBlKTsgfQp9CgpmdW5jdGlvbiBjb3B5Um9vbUNvZGVOZXdHYW1lKCkgewogIGlmICghcm9vbUNvZGUpIHJldHVybjsKICBuYXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChyb29tQ29kZSkudGhlbigoKSA9PiB7CiAgICAvLyBicmllZiBmZWVkYmFjawogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncm9vbS1jb2RlLWRpc3AnKTsKICAgIGlmIChlbCkgeyBjb25zdCBvcmlnID0gZWwudGV4dENvbnRlbnQ7IGVsLnRleHRDb250ZW50ID0gJ0NvcGllZCEnOyBzZXRUaW1lb3V0KCgpPT5lbC50ZXh0Q29udGVudD1vcmlnLDEyMDApOyB9CiAgfSkuY2F0Y2goKCkgPT4gcHJvbXB0KCdSb29tIGNvZGU6Jywgcm9vbUNvZGUpKTsKfQoKZnVuY3Rpb24gdG9nZ2xlSW52ZW50b3J5KCkgewogIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ludi1wYW5lbCcpOwogIGNvbnN0IGFycm93ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ludi10b2dnbGUtYXJyb3cnKTsKICBpZiAoIXBhbmVsKSByZXR1cm47CiAgY29uc3Qgb3BlbiA9IHBhbmVsLnN0eWxlLmRpc3BsYXkgIT09ICdub25lJzsKICBwYW5lbC5zdHlsZS5kaXNwbGF5ID0gb3BlbiA/ICdub25lJyA6ICdibG9jayc7CiAgaWYgKGFycm93KSBhcnJvdy5pbm5lckhUTUwgPSBvcGVuID8gJycgOiAnJzsKfQoKZnVuY3Rpb24gdXBkYXRlU3RhdHVzUGFuZWwoKSB7CiAgLy8gSHVuZ2VyIC0tIGhvdXNlIHJ1bGU6IC0xIGF0dGFjay9zYXZlcyBwZXIgZGF5IGFmdGVyIGRheSAzIHdpdGhvdXQgZm9vZAogIGNvbnN0IGh1bmdlckVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2h1bmdlci1iYXInKTsKICBpZiAoaHVuZ2VyRWwpIHsKICAgIGlmIChzdGFydmF0aW9uUGVuYWx0eSA+PSAzKSB7CiAgICAgIGh1bmdlckVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwMjAyMCI+U3RhcnZpbmcgKC0nICsgc3RhcnZhdGlvblBlbmFsdHkgKyAnIGF0dGFja3Mvc2F2ZXMpPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHN0YXJ2YXRpb25QZW5hbHR5ID4gMCkgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPkh1bmdyeSAoLScgKyBzdGFydmF0aW9uUGVuYWx0eSArICcgYXR0YWNrcy9zYXZlcyk8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAoZGF5c1dpdGhvdXRGb29kID4gMCkgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPkh1bmdyeSAoZGF5ICcgKyBkYXlzV2l0aG91dEZvb2QgKyAnLCBwZW5hbHR5IHN0YXJ0cyBkYXkgNCk8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAocmF0aW9uc0xlZnQgPT09IDEpIHsKICAgICAgaHVuZ2VyRWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA5MDQwIj5GZWQgKDEgcmF0aW9uIGxlZnQpPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHJhdGlvbnNMZWZ0ID09PSAwKSB7CiAgICAgIGh1bmdlckVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwOTA0MCI+Tm8gcmF0aW9ucyAocGVuYWx0eSBhZnRlciAzIGRheXMpPC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICBodW5nZXJFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiM2YTlhNmEiPkZlZDwvc3Bhbj4nOwogICAgfQogIH0KICAvLyBEdW5nZW9uIHJlc3QgaW5kaWNhdG9yIC0tIG9ubHkgc2hvd24gd2hlbiBpbiBhIGR1bmdlb24gKGR1bmdlb25fbGV2ZWwgPj0gMSkKICBjb25zdCByZXN0Um93ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0YXR1cy1kdW5nZW9uLXJlc3QnKTsKICBjb25zdCByZXN0QmFyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2R1bmdlb24tcmVzdC1iYXInKTsKICBjb25zdCBpbkR1bmdlb24gPSBpc0luRHVuZ2VvbigpOwogIGlmIChyZXN0Um93KSByZXN0Um93LnN0eWxlLmRpc3BsYXkgPSBpbkR1bmdlb24gPyAnJyA6ICdub25lJzsKICBpZiAocmVzdEJhciAmJiBpbkR1bmdlb24pIHsKICAgIGlmICh0dXJuc1dpdGhvdXRSZXN0ID49IDYpIHsKICAgICAgcmVzdEJhci5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDYwNjAiPlJlc3QgbmVlZGVkISAoJyArIHR1cm5zV2l0aG91dFJlc3QgKyAnIHR1cm5zKTwvc3Bhbj4nOwogICAgfSBlbHNlIGlmICh0dXJuc1dpdGhvdXRSZXN0ID49IDQpIHsKICAgICAgcmVzdEJhci5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPicgKyB0dXJuc1dpdGhvdXRSZXN0ICsgJy82IHR1cm5zIChyZXN0IHNvb24pPC9zcGFuPic7CiAgICB9IGVsc2UgewogICAgICByZXN0QmFyLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6IzZhOWE2YSI+JyArIHR1cm5zV2l0aG91dFJlc3QgKyAnLzYgdHVybnM8L3NwYW4+JzsKICAgIH0KICB9CiAgLy8gTGlnaHQgLSBvbmx5IHNob3cgd2hlbiBhIGxpZ2h0IHNvdXJjZSBpcyBBQ1RJVkVMWSBMSVQgb3IgY2hhcmFjdGVyIGlzIGluIGRhcmtuZXNzCiAgY29uc3QgbGlnaHRSb3cgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc3RhdHVzLWxpZ2h0Jyk7CiAgY29uc3QgbGlnaHRFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsaWdodC1zdGF0dXMnKTsKICAvLyB0b3JjaExpdCA9IHRvcmNoIGhhcyBiZWVuIGRlbGliZXJhdGVseSB1c2VkIGFuZCBpcyBjb3VudGluZyBkb3duCiAgLy8gT25seSBzaG93IGRhcmtuZXNzIHdhcm5pbmcgaWYgdGhleSd2ZSBlbnRlcmVkIHNvbWV3aGVyZSBkYXJrICh0b3JjaFR1cm5zTGVmdCBldmVyIGNvdW50ZWQpCiAgY29uc3QgbGlnaHRBY3RpdmUgPSAodG9yY2hMaXQgJiYgdG9yY2hUdXJuc0xlZnQgPiAwKSB8fCAobGFudGVybkxpdCAmJiBoYXNMYW50ZXJuKSB8fCAodG9yY2hFdmVyVXNlZCAmJiAhaXNDYXJyeWluZ0xpZ2h0KTsKICBpZiAobGlnaHRSb3cpIGxpZ2h0Um93LnN0eWxlLmRpc3BsYXkgPSBsaWdodEFjdGl2ZSA/ICcnIDogJ25vbmUnOwogIGlmIChsaWdodEVsICYmIGxpZ2h0QWN0aXZlKSB7CiAgICBpZiAoIWlzQ2FycnlpbmdMaWdodCkgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICc8c3BhbiBzdHlsZT0iY29sb3I6I2MwNjA2MCI+REFSS05FU1M8L3NwYW4+JzsKICAgIH0gZWxzZSBpZiAodG9yY2hMaXQgJiYgdG9yY2hUdXJuc0xlZnQgPiAwICYmIHRvcmNoVHVybnNMZWZ0IDw9IDIpIHsKICAgICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOiNjMDkwNDAiPlRvcmNoOiAnICsgdG9yY2hUdXJuc0xlZnQgKyAnIHR1cm5zIGxlZnQhPC9zcGFuPic7CiAgICB9IGVsc2UgaWYgKHRvcmNoTGl0ICYmIHRvcmNoVHVybnNMZWZ0ID4gMCkgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICdUb3JjaDogJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJucyc7CiAgICB9IGVsc2UgaWYgKGxhbnRlcm5MaXQgJiYgaGFzTGFudGVybikgewogICAgICBsaWdodEVsLmlubmVySFRNTCA9ICdMYW50ZXJuOiAnICsgbGFudGVybk9pbEZsYXNrc0xlZnQgKyAnIGZsYXNrKHMpJzsKICAgIH0KICB9CiAgLy8gQWN0aXZlIGVmZmVjdHMgKGNoYXJtLCBwb2lzb24sIHNwZWxsIHRpbWVycyBldGMpCiAgdXBkYXRlQWN0aXZlRWZmZWN0cygpOwp9CgpmdW5jdGlvbiBhZGRFZmZlY3QobmFtZSwgdHVybnMsIGNvbG9yKSB7CiAgY29sb3IgPSBjb2xvciB8fCAnI2MwOTA0MCc7CiAgYWN0aXZlRWZmZWN0cyA9IGFjdGl2ZUVmZmVjdHMuZmlsdGVyKGUgPT4gZS5uYW1lICE9PSBuYW1lKTsKICBhY3RpdmVFZmZlY3RzLnB1c2goe25hbWUsIHR1cm5zTGVmdDogdHVybnMsIGNvbG9yfSk7CiAgdXBkYXRlQWN0aXZlRWZmZWN0cygpOwp9CgpmdW5jdGlvbiB0aWNrRWZmZWN0cygpIHsKICBhY3RpdmVFZmZlY3RzID0gYWN0aXZlRWZmZWN0cy5maWx0ZXIoZSA9PiB7CiAgICBlLnR1cm5zTGVmdC0tOwogICAgaWYgKGUudHVybnNMZWZ0IDw9IDApIHsKICAgICAgYWRkRW50cnlSYXcoJ0VmZmVjdCBlbmRlZDogPHN0cm9uZz4nICsgZS5uYW1lICsgJzwvc3Ryb25nPicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIHJldHVybiBmYWxzZTsKICAgIH0KICAgIHJldHVybiB0cnVlOwogIH0pOwogIHVwZGF0ZUFjdGl2ZUVmZmVjdHMoKTsKfQoKZnVuY3Rpb24gdXBkYXRlQWN0aXZlRWZmZWN0cygpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhY3RpdmUtZWZmZWN0cycpOwogIGlmICghZWwpIHJldHVybjsKICBpZiAoIWFjdGl2ZUVmZmVjdHMubGVuZ3RoKSB7IGVsLmlubmVySFRNTCA9ICcnOyByZXR1cm47IH0KICBlbC5pbm5lckhUTUwgPSBhY3RpdmVFZmZlY3RzLm1hcChlID0+CiAgICAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjEzcHg7Y29sb3I6JyArIGUuY29sb3IgKyAnO3BhZGRpbmc6MXB4IDA7Ij4nICsgZS5uYW1lICsgJzogJyArIGUudHVybnNMZWZ0ICsgJyB0dXJuczwvZGl2PicKICApLmpvaW4oJycpOwp9CgpmdW5jdGlvbiB0ZXN0Q29ubmVjdGlvbigpIHsKICAvLyBUZXN0IHRoZSBzYW1lIFVSTCBwYXR0ZXJuIHRoYXQgeGhyRmV0Y2ggdXNlcwogIGNvbnN0IHVybCA9IEJBU0VfVVJMICsgJy9waW5nJzsKICBhbGVydCgnVGVzdGluZyBVUkw6ICcgKyB1cmwpOwogIGNvbnN0IHhociA9IG5ldyBYTUxIdHRwUmVxdWVzdCgpOwogIHhoci5vcGVuKCdHRVQnLCB1cmwsIHRydWUpOwogIHhoci5vbmxvYWQgPSAoKSA9PiBhbGVydCgnT0s6ICcgKyB4aHIucmVzcG9uc2VUZXh0KTsKICB4aHIub25lcnJvciA9ICgpID0+IGFsZXJ0KCdGQUlMRUQgZm9yOiAnICsgdXJsKTsKICB4aHIuc2VuZCgpOwp9CgpmdW5jdGlvbiB0b2dnbGVBcGlLZXkoKSB7CiAgY29uc3QgYm94ICAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYXBpLWtleS1ib3gnKTsKICBjb25zdCBhcnJvdyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdhcGktYXJyb3cnKTsKICBjb25zdCBvcGVuICA9IGJveC5zdHlsZS5kaXNwbGF5ID09PSAnZmxleCc7CiAgYm94LnN0eWxlLmRpc3BsYXkgPSBvcGVuID8gJ25vbmUnIDogJ2ZsZXgnOwogIGlmIChhcnJvdykgYXJyb3cuaW5uZXJIVE1MID0gb3BlbiA/ICcmIzk2NjA7JyA6ICcmIzk2NTA7JzsKfQpmdW5jdGlvbiBvbkFwaUtleVR5cGVkKHZhbCkgewogIGNvbnN0IHN0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktc3RhdHVzJyk7CiAgaWYgKCFzdCkgcmV0dXJuOwogIGlmICghdmFsKSB7IHN0LnRleHRDb250ZW50ID0gJyc7IHJldHVybjsgfQogIGlmICh2YWwuc3RhcnRzV2l0aCgnc2stYW50LScpKSB7CiAgICBzdC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsgc3QudGV4dENvbnRlbnQgPSAnVmFsaWQga2V5IGZvcm1hdCc7CiAgfSBlbHNlIHsKICAgIHN0LnN0eWxlLmNvbG9yID0gJyNjMDkwNDAnOyBzdC50ZXh0Q29udGVudCA9ICdLZXkgc2hvdWxkIHN0YXJ0IHdpdGggc2stYW50LS4uLic7CiAgfQp9CmZ1bmN0aW9uIGFwcGx5QXBpS2V5KCkgewogIGNvbnN0IGlucCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdrZXktaW5wJyk7CiAgY29uc3Qgc3QgID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FwaS1rZXktc3RhdHVzJyk7CiAgaWYgKCFpbnApIHJldHVybjsKICBhcGlLZXkgPSBpbnAudmFsdWUudHJpbSgpOwogIGlmIChhcGlLZXkpIHsKICAgIGlmIChzdCkgeyBzdC5zdHlsZS5jb2xvciA9ICcjNmE5YTZhJzsgc3QudGV4dENvbnRlbnQgPSAnU2F2ZWQg4oCUIENsYXVkZSBIYWlrdSBwYXJzaW5nIGFjdGl2ZSc7IH0KICB9IGVsc2UgewogICAgaWYgKHN0KSB7IHN0LnN0eWxlLmNvbG9yID0gJ3ZhcigtLWluay1kaW0pJzsgc3QudGV4dENvbnRlbnQgPSAnQ2xlYXJlZCDigJQgT2xsYW1hIG9ubHknOyB9CiAgfQp9CmZ1bmN0aW9uIGdvSG9tZSgpIHsKICBjb25zdCBuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1uYW1lLWlucCcpLnZhbHVlLnRyaW0oKTsKICBjb25zdCBrID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2tleS1pbnAnKS52YWx1ZS50cmltKCk7CiAgY29uc29sZS5sb2coJ1tnb0hvbWVdIG5hbWU6JywgbiwgJ2tleTonLCAhIWssICdvbGxhbWE6Jywgb2xsYW1hQXZhaWxhYmxlLCAnX3NlcnZlcjonLCB3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZSk7CiAgcGxheWVyTmFtZSA9IG4gfHwgJ0FkdmVudHVyZXInOwogIGlmIChrKSB7IGFwaUtleSA9IGs7IH0KICBpc0hvc3QgPSAhIShrIHx8IG9sbGFtYUF2YWlsYWJsZSk7CiAgY29uc29sZS5sb2coJ1tnb0hvbWVdIGlzSG9zdDonLCBpc0hvc3QsICduYXZpZ2F0aW5nIHRvIHMtaG9tZScpOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdob21lLXdlbGNvbWUnKS50ZXh0Q29udGVudCA9ICdXZWxjb21lLCAnICsgcGxheWVyTmFtZSArICcuIFdoYXQgd291bGQgeW91IGxpa2UgdG8gZG8/JzsKICBzaG93KCdzLWhvbWUnKTsKICBjb25zb2xlLmxvZygnW2dvSG9tZV0gZG9uZScpOwp9CgpmdW5jdGlvbiBzaG93TmV3R2FtZSgpIHsKICBpZiAoIXJvb21Db2RlKSBhdXRvR2VuZXJhdGVSb29tKCk7CiAgc2hvdygncy1uZXdnYW1lJyk7CiAgbG9hZERuZG1vZExpc3QoKTsgLy8gYXV0by1wb3B1bGF0ZSBtb2R1bGUgbGlzdCBvbiBldmVyeSB2aXNpdAp9CgpmdW5jdGlvbiBzaG93TG9hZCgpIHsKICB4aHJGZXRjaChCQVNFX1VSTCArICcvc2F2ZXMnKS50aGVuKHI9PnIuanNvbigpKS50aGVuKHJlc3AgPT4gewogICAgY29uc3Qgc2F2ZXMgPSBBcnJheS5pc0FycmF5KHJlc3ApID8gcmVzcCA6IChyZXNwLnNhdmVzIHx8IFtdKTsKICAgIGNvbnN0IHdyYXAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbG9hZC13cmFwJyk7CiAgICBjb25zdCBsaXN0ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NhdmUtbGlzdC1lbCcpOwogICAgd3JhcC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogICAgaWYgKCFzYXZlcy5sZW5ndGgpIHsgbGlzdC5pbm5lckhUTUwgPSAnPGRpdiBzdHlsZT0iZm9udC1zaXplOjE2cHg7Y29sb3I6dmFyKC0taW5rLWRpbSkiPk5vIHNhdmVkIGdhbWVzIGZvdW5kLjwvZGl2Pic7IHJldHVybjsgfQogICAgbGlzdC5pbm5lckhUTUwgPSBzYXZlcy5tYXAocyA9PgogICAgICBgPGRpdiBjbGFzcz0ic2F2ZS1pdGVtIj4KICAgICAgICA8ZGl2IGNsYXNzPSJzaS1pbmZvIj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNpLW5hbWUiPiR7cy5tb2R1bGVOYW1lfHwnQWR2ZW50dXJlJ308L2Rpdj4KICAgICAgICAgIDxkaXYgY2xhc3M9InNpLW1ldGEiPiR7cy5wY05hbWV9ICogJHtzLnBjQ2xhc3N9ICogJHtuZXcgRGF0ZShzLnNhdmVkQXQpLnRvTG9jYWxlU3RyaW5nKCl9PC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT0iZGlzcGxheTpmbGV4O2dhcDo2cHg7Ij4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biIgb25jbGljaz0ibG9hZFNhdmUoJyR7cy5pZH0nKSIgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O3BhZGRpbmc6NHB4IDEwcHg7Ij5Mb2FkPC9idXR0b24+CiAgICAgICAgICA8YnV0dG9uIGNsYXNzPSJidG4iIG9uY2xpY2s9ImRlbGV0ZVNhdmUoJyR7cy5pZH0nKSIgc3R5bGU9ImZvbnQtc2l6ZToxNHB4O3BhZGRpbmc6NHB4IDEwcHg7Ym9yZGVyLWNvbG9yOiM2YTIwMjA7Y29sb3I6I2MwNjA2MDsiPjwvYnV0dG9uPgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj5gCiAgICApLmpvaW4oJycpOwogIH0pOwp9CgpmdW5jdGlvbiBsb2FkU2F2ZShpZCkgewogIHhockZldGNoKEJBU0VfVVJMICsgJy9sb2FkP2lkPScgKyBpZCkudGhlbihyPT5yLmpzb24oKSkudGhlbihkYXRhID0+IHsKICAgIGlmIChkYXRhLmVycm9yKSB7IGFsZXJ0KGRhdGEuZXJyb3IpOyByZXR1cm47IH0KICAgIC8vIFJvdXRlIHRocm91Z2ggY2hhcmFjdGVyIHNlbGVjdCBzY3JlZW4KICAgIGNvbnN0IG1vZExhYmVsID0gZGF0YS5tb2R1bGVOYW1lIHx8ICdBZHZlbnR1cmUnOwogICAgc2hvd0NoYXJTZWxlY3QoCiAgICAgICdTZWxlY3QgdGhlIGNoYXJhY3RlciB5b3Ugd2FudCB0byBwbGF5IHRoaXMgYWR2ZW50dXJlIHdpdGgsIG9yIGNyZWF0ZSBhIG5ldyBvbmUuJywKICAgICAgbW9kTGFiZWwsCiAgICAgIHt0eXBlOiAnc2F2ZScsIGRhdGE6IGRhdGF9CiAgICApOwogIH0pOwp9CgpmdW5jdGlvbiBkZWxldGVTYXZlKGlkKSB7CiAgaWYgKCFjb25maXJtKCdEZWxldGUgdGhpcyBzYXZlPycpKSByZXR1cm47CiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2RlbGV0ZV9zYXZlP2lkPScgKyBpZCwge21ldGhvZDonUE9TVCd9KS50aGVuKCgpID0+IHNob3dMb2FkKCkpOwp9Cgphc3luYyBmdW5jdGlvbiBjaGVja05ncm9rU3RhdHVzKCkgewogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL25ncm9rX3N0YXR1cycpOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmdyb2stc3RhdHVzLXR4dCcpOwogICAgaWYgKCFlbCkgcmV0dXJuOwogICAgaWYgKGRhdGEuYWN0aXZlICYmIGRhdGEudXJsKSB7CiAgICAgIG5ncm9rUHVibGljVXJsID0gZGF0YS51cmw7CiAgICAgIGVsLmlubmVySFRNTCA9CiAgICAgICAgJzxzdHJvbmcgc3R5bGU9ImNvbG9yOnZhcigtLWdvbGQpIj5JbnRlcm5ldCBhY2Nlc3MgYWN0aXZlITwvc3Ryb25nPjxicj4nICsKICAgICAgICAnRnJpZW5kcyBhbnl3aGVyZSBjYW4gam9pbi4gU2hhcmUgdGhpcyBsaW5rOjxicj4nICsKICAgICAgICAnPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLWluayk7Zm9udC1zaXplOjE2cHg7bGV0dGVyLXNwYWNpbmc6MC41cHg7Ij4nICsgZGF0YS51cmwgKyAnPC9zcGFuPicgKwogICAgICAgICcgPGJ1dHRvbiBvbmNsaWNrPSJjb3B5Tmdyb2tVcmwoKSIgc3R5bGU9ImJhY2tncm91bmQ6bm9uZTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWJvcmRlcik7Y29sb3I6dmFyKC0taW5rLWRpbSk7Y3Vyc29yOnBvaW50ZXI7cGFkZGluZzoycHggOHB4O2ZvbnQtc2l6ZToxNHB4O21hcmdpbi1sZWZ0OjZweDsiPkNvcHk8L2J1dHRvbj48YnI+JyArCiAgICAgICAgJzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+UGxheWVycyBvcGVuIHRoYXQgVVJMIGluIHRoZWlyIGJyb3dzZXIsIHRoZW4gZW50ZXIgdGhlIHJvb20gY29kZS48L3NwYW4+JzsKICAgIH0gZWxzZSB7CiAgICAgIGVsLmlubmVySFRNTCA9CiAgICAgICAgJ0xBTiBvbmx5IC0tIGZyaWVuZHMgb24gdGhlIHNhbWUgbmV0d29yayBjYW4gY29ubmVjdC48YnI+JyArCiAgICAgICAgJzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+Rm9yIGludGVybmV0IHBsYXk6IGluc3RhbGwgJyArCiAgICAgICAgJzxhIGhyZWY9Imh0dHBzOi8vbmdyb2suY29tIiBzdHlsZT0iY29sb3I6dmFyKC0tZ29sZCkiPm5ncm9rPC9hPiwgJyArCiAgICAgICAgJ3RoZW4gcnVuIDxjb2RlIHN0eWxlPSJiYWNrZ3JvdW5kOnZhcigtLXBhbmVsKTtwYWRkaW5nOjFweCA1cHg7Ij5uZ3JvayBodHRwIDgwODA8L2NvZGU+IGluIGEgdGVybWluYWwgYmVmb3JlIHN0YXJ0aW5nIHRoZSBnYW1lLjwvc3Bhbj4nOwogICAgfQogIH0gY2F0Y2goZSkgewogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbmdyb2stc3RhdHVzLXR4dCcpOwogICAgaWYgKGVsKSBlbC50ZXh0Q29udGVudCA9ICdMQU4gb25seSAoY291bGQgbm90IGNoZWNrIGludGVybmV0IHR1bm5lbCBzdGF0dXMpJzsKICB9Cn0KCmZ1bmN0aW9uIGNvcHlOZ3Jva1VybCgpIHsKICBpZiAoIW5ncm9rUHVibGljVXJsKSByZXR1cm47CiAgdHJ5IHsKICAgIG5hdmlnYXRvci5jbGlwYm9hcmQud3JpdGVUZXh0KG5ncm9rUHVibGljVXJsKS50aGVuKCgpID0+IHsKICAgICAgY29uc3QgYnRuID0gZXZlbnQudGFyZ2V0OwogICAgICBjb25zdCBvcmlnID0gYnRuLnRleHRDb250ZW50OwogICAgICBidG4udGV4dENvbnRlbnQgPSAnQ29waWVkISc7CiAgICAgIHNldFRpbWVvdXQoKCkgPT4gYnRuLnRleHRDb250ZW50ID0gb3JpZywgMTUwMCk7CiAgICB9KTsKICB9IGNhdGNoKGUpIHsKICAgIHByb21wdCgnQ29weSB0aGlzIFVSTDonLCBuZ3Jva1B1YmxpY1VybCk7CiAgfQp9CgpmdW5jdGlvbiBnZW5lcmF0ZVJvb20oKSB7CiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2NyZWF0ZV9yb29tJywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtob3N0OiBwbGF5ZXJOYW1lfSl9KQogICAgLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZGF0YSA9PiB7CiAgICAgIHJvb21Db2RlID0gZGF0YS5jb2RlOwogICAgICBpc011bHRpcGxheWVyID0gdHJ1ZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jvb20tY29kZS1kaXNwJykudGV4dENvbnRlbnQgPSByb29tQ29kZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jvb20tc2hhcmUtd3JhcCcpLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7CiAgICAgIHJlbmRlclBsYXllclNsb3RzKFt7bmFtZTpwbGF5ZXJOYW1lLCByZWFkeTpmYWxzZX1dKTsKICAgICAgc3RhcnRQb2xsaW5nKCk7CiAgICAgIGNoZWNrTmdyb2tTdGF0dXMoKTsgIC8vIFNob3cgbmdyb2sgVVJMIG9yIExBTiBpbnN0cnVjdGlvbnMKICAgIH0pOwp9CgpmdW5jdGlvbiBqb2luUm9vbSgpIHsKICBjb25zdCBjb2RlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2pvaW4tY29kZScpLnZhbHVlLnRyaW0oKS50b1VwcGVyQ2FzZSgpOwogIGlmICghY29kZSkgeyBhbGVydCgnRW50ZXIgYSByb29tIGNvZGUuJyk7IHJldHVybjsgfQogIHhockZldGNoKEJBU0VfVVJMICsgJy9qb2luX3Jvb20nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGUsIHBsYXllcjogcGxheWVyTmFtZX0pfSkKICAgIC50aGVuKGRhdGEgPT4gewogICAgICBpZiAoZGF0YS5lcnJvcikgeyBhbGVydChkYXRhLmVycm9yKTsgcmV0dXJuOyB9CiAgICAgIC8vIEFsd2F5cyByb3V0ZSB0aHJvdWdoIGNoYXJhY3RlciBzZWxlY3Qgc2NyZWVuCiAgICAgIGRhdGEuY29kZSA9IGNvZGU7CiAgICAgIGNvbnN0IG1vZExhYmVsID0gZGF0YS5tb2R1bGVOYW1lIHx8ICdBZHZlbnR1cmUnOwogICAgICBzaG93Q2hhclNlbGVjdCgKICAgICAgICAnU2VsZWN0IHRoZSBjaGFyYWN0ZXIgeW91IHdhbnQgdG8gYnJpbmcgaW50byB0aGlzIGFkdmVudHVyZSwgb3IgY3JlYXRlIGEgbmV3IG9uZS4nLAogICAgICAgIG1vZExhYmVsLAogICAgICAgIHt0eXBlOiAnam9pbicsIGRhdGE6IGRhdGF9CiAgICAgICk7CiAgICB9KTsKfQoKZnVuY3Rpb24gcmVuZGVyUGxheWVyU2xvdHMocGxheWVycykgewogIGNvbnN0IGVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1zbG90cy1saXN0Jyk7CiAgaWYgKCFlbCkgcmV0dXJuOwogIGVsLmlubmVySFRNTCA9IHBsYXllcnMubWFwKChwLGkpID0+CiAgICBgPGRpdiBjbGFzcz0icGxheWVyLXNsb3QiPgogICAgICA8ZGl2IGNsYXNzPSJwZG90ICR7cC5yZWFkeT8nb24nOid3YWl0J30iIHN0eWxlPSJiYWNrZ3JvdW5kOiR7UExBWUVSX0NPTE9SU1tpJVBMQVlFUl9DT0xPUlMubGVuZ3RoXX07JHtwLnJlYWR5PycnOicnfSI+PC9kaXY+CiAgICAgIDxzcGFuIHN0eWxlPSJmb250LXNpemU6MTdweDtjb2xvcjoke1BMQVlFUl9DT0xPUlNbaSVQTEFZRVJfQ09MT1JTLmxlbmd0aF19Ij4ke3AubmFtZX0ke3AubmFtZT09PXBsYXllck5hbWU/JyAoeW91KSc6Jyd9PC9zcGFuPgogICAgICAke3AucmVhZHk/JzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+PC9zcGFuPic6Jyd9CiAgICA8L2Rpdj5gCiAgKS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gc3RhcnRQb2xsaW5nKCkgewogIGlmIChwb2xsVGltZXIpIGNsZWFySW50ZXJ2YWwocG9sbFRpbWVyKTsKICBwb2xsVGltZXIgPSBzZXRJbnRlcnZhbChkb1BvbGwsIDIwMDApOwp9CgpmdW5jdGlvbiBkb1BvbGwoKSB7CiAgaWYgKCFyb29tQ29kZSkgcmV0dXJuOwogIGZldGNoKGAvcG9sbD9yb29tPSR7cm9vbUNvZGV9JnBsYXllcj0ke2VuY29kZVVSSUNvbXBvbmVudChwbGF5ZXJOYW1lKX0mc2VxPSR7bGFzdFNlcX1gKQogICAgLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZGF0YSA9PiB7CiAgICAgIGlmIChkYXRhLmVycm9yKSByZXR1cm47CiAgICAgIGxhc3RTZXEgPSBkYXRhLnNlcSB8fCBsYXN0U2VxOwoKICAgICAgLy8gVXBkYXRlIHBsYXllciBsaXN0CiAgICAgIGlmIChkYXRhLnBsYXllcnMgJiYgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BsYXllci1zbG90cy1saXN0JykpIHsKICAgICAgICByZW5kZXJQbGF5ZXJTbG90cyhkYXRhLnBsYXllcnMpOwogICAgICB9CgogICAgICAvLyBQYXJ0eSBzdGF0dXMgaW4gY2hhciBjcmVhdGUKICAgICAgaWYgKGRhdGEucGxheWVycyAmJiBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGFydHktc3RhdHVzLXdyYXAnKSkgewogICAgICAgIHJlbmRlclBhcnR5U3RhdHVzKGRhdGEucGxheWVycyk7CiAgICAgIH0KCiAgICAgIC8vIE5ldyBjaGF0L2dhbWUgbWVzc2FnZXMKICAgICAgaWYgKGRhdGEubmV3TWVzc2FnZXMpIHsKICAgICAgICBkYXRhLm5ld01lc3NhZ2VzLmZvckVhY2gobSA9PiB7CiAgICAgICAgICBpZiAobS5hdXRob3IgIT09IHBsYXllck5hbWUgfHwgbS50eXBlID09PSAnZ20nIHx8IG0udHlwZSA9PT0gJ3N5c3RlbScpIHsKICAgICAgICAgICAgYWRkRW50cnlSYXcobS5odG1sLCBtLnR5cGUsIG0uYXV0aG9yKTsKICAgICAgICAgIH0KICAgICAgICB9KTsKICAgICAgfQoKICAgICAgLy8gU3RhdGUgdXBkYXRlcwogICAgICBpZiAoZGF0YS5nYW1lU3RhdGUpIHsKICAgICAgICBjb25zdCBncyA9IGRhdGEuZ2FtZVN0YXRlOwogICAgICAgIGlmIChncy5sb2MpIHsgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NjZW5lLWxvYycpLnRleHRDb250ZW50ID0gZ3MubG9jOyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2NlbmUtdGFnJykudGV4dENvbnRlbnQgPSBncy5sb2N0YWd8fCcnOyB9CiAgICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3F1aWNrLWJ0bnMnKS5pbm5lckhUTUwgPSAnJzsKICAgICAgICBpZiAoZ3MucXVlc3RzICYmIHBjLnF1ZXN0cykgeyBwYy5xdWVzdHMgPSBncy5xdWVzdHM7IHJlbmRlclF1ZXN0cygpOyB9CiAgICAgICAgaWYgKGdzLnBhcnR5KSB7CiAgICAgICAgICBPYmplY3QuZW50cmllcyhncy5wYXJ0eSkuZm9yRWFjaCgoW3BuLCBwZF0pID0+IHsKICAgICAgICAgICAgaWYgKHBhcnR5UENzW3BuXSkgeyBwYXJ0eVBDc1twbl0uaHAgPSBwZC5ocDsgcGFydHlQQ3NbcG5dLm1heGhwID0gcGQubWF4aHA7IH0KICAgICAgICAgIH0pOwogICAgICAgICAgcmVuZGVyUGFydHlQYW5lbCgpOwogICAgICAgIH0KICAgICAgfQoKICAgICAgLy8gUGFydHkgUEMgdXBkYXRlcwogICAgICBpZiAoZGF0YS5wYXJ0eVBDcykgeyBwYXJ0eVBDcyA9IGRhdGEucGFydHlQQ3M7IHJlbmRlclBhcnR5UGFuZWwoKTsgfQoKICAgICAgLy8gR2FtZSBzdGFydGVkIHNpZ25hbCBmb3Igbm9uLWhvc3RzIGluIGNoYXIgY3JlYXRlCiAgICAgIGlmIChkYXRhLmdhbWVTdGFydGVkICYmIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzLWNoYXInKS5jbGFzc0xpc3QuY29udGFpbnMoJ2FjdGl2ZScpKSB7CiAgICAgICAgcGMgPSBkYXRhLm15UGMgfHwgcGM7CiAgICAgICAgcGFydHlQQ3MgPSBkYXRhLnBhcnR5UENzIHx8IHt9OwogICAgICAgIGhpc3RvcnkgPSBkYXRhLmhpc3RvcnkgfHwgW107CiAgICAgICAgc3lzdGVtUHJvbXB0ID0gZGF0YS5zeXN0ZW1Qcm9tcHQgfHwgc3lzdGVtUHJvbXB0OwogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtbW9kJykudGV4dENvbnRlbnQgPSBtb2R1bGVOYW1lOwogICAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3AtcnVsZXMnKS50ZXh0Q29udGVudCA9IGNob3NlblJ1bGVzOwogICAgICAgIHNob3dSb29tQ29kZSgpOwogICAgICAgIHNob3coJ3MtZ2FtZScpOwogICAgICAgIHVwZGF0ZUhVRCgpOwogICAgICAgIHJlbmRlclBhcnR5UGFuZWwoKTsKICAgICAgICBpZiAoZGF0YS5sb2dFbnRyaWVzKSBkYXRhLmxvZ0VudHJpZXMuZm9yRWFjaChlID0+IGFkZEVudHJ5UmF3KGUuaHRtbCwgZS50eXBlLCBlLmF1dGhvcikpOwogICAgICB9CiAgICB9KS5jYXRjaCgoKSA9PiB7fSk7Cn0KCmZ1bmN0aW9uIHJlbmRlclBhcnR5U3RhdHVzKHBsYXllcnMpIHsKICBjb25zdCB3cmFwID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BhcnR5LXN0YXR1cy13cmFwJyk7CiAgY29uc3Qgcm93cyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdwYXJ0eS1zdGF0dXMtcm93cycpOwogIGlmIChwbGF5ZXJzLmxlbmd0aCA8PSAxKSB7IHdyYXAuc3R5bGUuZGlzcGxheT0nbm9uZSc7IHJldHVybjsgfQogIHdyYXAuc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKICByb3dzLmlubmVySFRNTCA9IHBsYXllcnMubWFwKChwLGkpID0+CiAgICBgPGRpdiBjbGFzcz0icHJlYWR5LXJvdyI+CiAgICAgIDxkaXYgY2xhc3M9InBkb3QgJHtwLnJlYWR5Pydvbic6J3dhaXQnfSIgc3R5bGU9ImJhY2tncm91bmQ6JHtQTEFZRVJfQ09MT1JTW2klUExBWUVSX0NPTE9SUy5sZW5ndGhdfSI+PC9kaXY+CiAgICAgIDxzcGFuIHN0eWxlPSJjb2xvcjoke1BMQVlFUl9DT0xPUlNbaSVQTEFZRVJfQ09MT1JTLmxlbmd0aF19Ij4ke3AubmFtZX08L3NwYW4+CiAgICAgIDxzcGFuIHN0eWxlPSJmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1pbmstZGltKSI+JHtwLnJlYWR5PycgUmVhZHknOicuLi4gY3JlYXRpbmcgY2hhcmFjdGVyJ308L3NwYW4+CiAgICA8L2Rpdj5gCiAgKS5qb2luKCcnKTsKICAvLyBTaG93IGJlZ2luIGJ1dHRvbiB0byBob3N0IGlmIGFsbCByZWFkeQogIGlmIChpc0hvc3QpIHsKICAgIGNvbnN0IGFsbFJlYWR5ID0gcGxheWVycy5ldmVyeShwID0+IHAucmVhZHkpOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JlZ2luLWJ0bicpLnN0eWxlLmRpc3BsYXkgPSBhbGxSZWFkeSA/ICdpbmxpbmUtYmxvY2snIDogJ25vbmUnOwogIH0KfQoKZnVuY3Rpb24gcGlja1J1bGVzKGVsKSB7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnLnJjJykuZm9yRWFjaChjID0+IGMuY2xhc3NMaXN0LnJlbW92ZSgncGlja2VkJykpOwogIGVsLmNsYXNzTGlzdC5hZGQoJ3BpY2tlZCcpOwogIGNob3NlblJ1bGVzID0gZWwuZGF0YXNldC5yOwp9CgpmdW5jdGlvbiBoYW5kbGVGaWxlKGYpIHsKICB1cGxvYWRlZEZpbGUgPSBmOwogIG1vZHVsZU5hbWUgPSBmLm5hbWUucmVwbGFjZSgvWy5dW14uXSskLywgJycpOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdmaWxlLW5hbWUtZGlzcCcpLnRleHRDb250ZW50ID0gJyAnICsgZi5uYW1lOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCduZXh0LWJ0bicpLmRpc2FibGVkID0gZmFsc2U7Cn0KCmZ1bmN0aW9uIGJ1aWxkQ2hhckNyZWF0ZSgpIHsKICByZXJvbGwoKTsKICBidWlsZFJhY2VHcmlkKCk7CiAgYnVpbGRDbGFzc0dyaWQoKTsKICBidWlsZEVxdWlwbWVudCgpOwp9CgpmdW5jdGlvbiBidWlsZFJhY2VHcmlkKCkgewogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyYWNlLWdyaWQnKS5pbm5lckhUTUwgPSBPYmplY3QuZW50cmllcyhSQUNFUykubWFwKChbbmFtZSxkXSkgPT4KICAgIGA8ZGl2IGNsYXNzPSJzZWwtY2FyZCR7bmFtZT09PWNob3NlblJhY2U/JyBwaWNrZWQnOicnfSIgZGF0YS1yPSIke25hbWV9IiBvbmNsaWNrPSJwaWNrUmFjZSh0aGlzKSI+CiAgICAgIDxkaXYgY2xhc3M9ImNuIj4ke2QuaWNvbn0gJHtuYW1lfTwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJjZCI+JHtkLmRlc2Muc3Vic3RyaW5nKDAsNjApfTwvZGl2PgogICAgPC9kaXY+YAogICkuam9pbignJyk7CiAgdXBkYXRlUmFjZURlc2MoKTsKfQoKZnVuY3Rpb24gYnVpbGRDbGFzc0dyaWQoKSB7CiAgY29uc3QgYWxsb3dlZCA9IFJBQ0VTW2Nob3NlblJhY2VdPy5jbGFzc2VzIHx8IG51bGw7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NsYXNzLWdyaWQnKS5pbm5lckhUTUwgPSBPYmplY3QuZW50cmllcyhDTEFTU0VTKS5tYXAoKFtuYW1lLGRdKSA9PiB7CiAgICBjb25zdCBkaXMgPSBhbGxvd2VkICYmICFhbGxvd2VkLmluY2x1ZGVzKG5hbWUpOwogICAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJzZWwtY2FyZCR7bmFtZT09PWNob3NlbkNsYXNzJiYhZGlzPycgcGlja2VkJzonJ30ke2Rpcz8nIGRpc2FibGVkJzonJ30iCiAgICAgIGRhdGEtYz0iJHtuYW1lfSIgJHtkaXM/Jyc6J29uY2xpY2s9InBpY2tDbGFzcyh0aGlzKSInfT4KICAgICAgPGRpdiBjbGFzcz0iY24iPiR7ZC5pY29ufSAke25hbWV9PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImNkIj4ke2QuZGVzYy5zdWJzdHJpbmcoMCw1NSl9PC9kaXY+CiAgICA8L2Rpdj5gOwogIH0pLmpvaW4oJycpOwogIGlmIChhbGxvd2VkICYmICFhbGxvd2VkLmluY2x1ZGVzKGNob3NlbkNsYXNzKSkgewogICAgY2hvc2VuQ2xhc3MgPSBhbGxvd2VkWzBdOwogICAgZG9jdW1lbnQucXVlcnlTZWxlY3RvcihgLnNlbC1jYXJkW2RhdGEtYz0iJHtjaG9zZW5DbGFzc30iXWApPy5jbGFzc0xpc3QuYWRkKCdwaWNrZWQnKTsKICB9CiAgdXBkYXRlQ2xhc3NEZXNjKCk7CiAgYnVpbGRFcXVpcG1lbnQoKTsKfQoKZnVuY3Rpb24gcGlja1JhY2UoZWwpIHsKICBkb2N1bWVudC5xdWVyeVNlbGVjdG9yQWxsKCcjcmFjZS1ncmlkIC5zZWwtY2FyZCcpLmZvckVhY2goYyA9PiBjLmNsYXNzTGlzdC5yZW1vdmUoJ3BpY2tlZCcpKTsKICBlbC5jbGFzc0xpc3QuYWRkKCdwaWNrZWQnKTsKICBjaG9zZW5SYWNlID0gZWwuZGF0YXNldC5yOwogIHVwZGF0ZVJhY2VEZXNjKCk7CiAgYnVpbGRDbGFzc0dyaWQoKTsKICByZXJvbGwoKTsKfQoKZnVuY3Rpb24gcGlja0NsYXNzKGVsKSB7CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbCgnI2NsYXNzLWdyaWQgLnNlbC1jYXJkJykuZm9yRWFjaChjID0+IGMuY2xhc3NMaXN0LnJlbW92ZSgncGlja2VkJykpOwogIGVsLmNsYXNzTGlzdC5hZGQoJ3BpY2tlZCcpOwogIGNob3NlbkNsYXNzID0gZWwuZGF0YXNldC5jOwogIHVwZGF0ZUNsYXNzRGVzYygpOwogIGJ1aWxkRXF1aXBtZW50KCk7Cn0KCmZ1bmN0aW9uIHVwZGF0ZVJhY2VEZXNjKCkgewogIGNvbnN0IHIgPSBSQUNFU1tjaG9zZW5SYWNlXTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmFjZS1zcGVjaWFscycpLnRleHRDb250ZW50ID0gcj8uc3BlY2lhbHM/Lmxlbmd0aCA/ICcgJyArIHIuc3BlY2lhbHMuam9pbignICogJykgOiAnJzsKfQoKZnVuY3Rpb24gdXBkYXRlQ2xhc3NEZXNjKCkgewogIGNvbnN0IGMgPSBDTEFTU0VTW2Nob3NlbkNsYXNzXTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY2xhc3MtZGVzYycpLnRleHRDb250ZW50ID0gYyA/IGMuZGVzYyA6ICcnOwp9CgpmdW5jdGlvbiByZChkKSB7IHJldHVybiBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkqZCkrMTsgfQoKZnVuY3Rpb24gcjMoKSB7IHJldHVybiByZCg2KStyZCg2KStyZCg2KTsgfQoKZnVuY3Rpb24gcjRkNigpIHsgbGV0IGE9W3JkKDYpLHJkKDYpLHJkKDYpLHJkKDYpXTsgYS5zb3J0KCh4LHkpPT54LXkpOyBhLnNoaWZ0KCk7IHJldHVybiBhLnJlZHVjZSgocyx2KT0+cyt2LDApOyB9CgpmdW5jdGlvbiBtb2QodikgeyBsZXQgbT1NYXRoLmZsb29yKCh2LTEwKS8yKTsgcmV0dXJuIG0+PTA/JysnK206JycrbTsgfQoKZnVuY3Rpb24gbW9kTih2KSB7IHJldHVybiBNYXRoLmZsb29yKCh2LTEwKS8yKTsgfQoKZnVuY3Rpb24gcmVyb2xsKCkgewogIFsnU1RSJywnREVYJywnQ09OJywnSU5UJywnV0lTJywnQ0hBJ10uZm9yRWFjaChzID0+IHJvbGxlZFN0YXRzW3NdID0gcjMoKSk7CiAgY29uc3QgYm9udXNlcyA9IFJBQ0VTW2Nob3NlblJhY2VdPy5ib251c2VzIHx8IHt9OwogIE9iamVjdC5lbnRyaWVzKGJvbnVzZXMpLmZvckVhY2goKFtzLGJdKSA9PiByb2xsZWRTdGF0c1tzXSA9IE1hdGgubWluKDE4LCByb2xsZWRTdGF0c1tzXStiKSk7CiAgcmVuZGVyU3RhdHMoKTsKfQoKZnVuY3Rpb24gcmVuZGVyU3RhdHMoKSB7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3N0YXQtZ3JpZCcpLmlubmVySFRNTCA9IFsnU1RSJywnREVYJywnQ09OJywnSU5UJywnV0lTJywnQ0hBJ10ubWFwKHMgPT4gewogICAgY29uc3Qgdj1yb2xsZWRTdGF0c1tzXSwgbT1tb2ROKHYpLCBtYz1tPjA/J3Bvcyc6bTwwPyduZWcnOicnOwogICAgcmV0dXJuIGA8ZGl2IGNsYXNzPSJzdGF0LWJveCI+PGRpdiBjbGFzcz0ic24iPiR7c308L2Rpdj48ZGl2IGNsYXNzPSJzdiI+JHt2fTwvZGl2PjxkaXYgY2xhc3M9InNtICR7bWN9Ij4ke21vZCh2KX08L2Rpdj48L2Rpdj5gOwogIH0pLmpvaW4oJycpOwp9CgpmdW5jdGlvbiBidWlsZEVxdWlwbWVudCgpIHsKICBzdGFydGluZ0dvbGQgPSBHT0xEX0JZX0NMQVNTW2Nob3NlbkNsYXNzXSB8fCA2MDsKICBnb2xkU3BlbnQgPSAwOwogIHNlbGVjdGVkRXF1aXAgPSB7fTsKICBleHRyYUl0ZW1zID0gW107CiAgc2VsZWN0ZWRFcXVpcEl0ZW1zLmNsZWFyKCk7ICAvLyByZXNldCBlcXVpcG1lbnQgc2VsZWN0aW9uCgogIGNvbnN0IGNhdHMgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZXF1aXAtY2F0ZWdvcmllcycpOwogIGNvbnN0IGFsbG93ZWRXZWFwb25zID0gQ0xBU1NfV0VBUE9OX1JFU1RSSUNUSU9OU1tjaG9zZW5DbGFzc107IC8vIG51bGwgPSBhbGwKICBjb25zdCBhbGxvd2VkQXJtb3VyICA9IENMQVNTX0FSTU9VUl9SRVNUUklDVElPTlNbY2hvc2VuQ2xhc3NdIHx8IFtdOwoKICAvLyBGaWx0ZXIgd2VhcG9ucyBieSBjbGFzcyByZXN0cmljdGlvbgogIGNvbnN0IG1lbGVlV2VhcG9ucyAgPSBPYmplY3QuZW50cmllcyhPU0VfV0VBUE9OUykKICAgIC5maWx0ZXIoKFtuLHddKSA9PiAhdy5yYW5nZWQgJiYgKCFhbGxvd2VkV2VhcG9ucyB8fCBhbGxvd2VkV2VhcG9ucy5pbmNsdWRlcyhuKSkpOwogIGNvbnN0IHJhbmdlZFdlYXBvbnMgPSBPYmplY3QuZW50cmllcyhPU0VfV0VBUE9OUykKICAgIC5maWx0ZXIoKFtuLHddKSA9PiB3LnJhbmdlZCAmJiB3LmRtZyAhPT0gJy0nICYmICghYWxsb3dlZFdlYXBvbnMgfHwgYWxsb3dlZFdlYXBvbnMuaW5jbHVkZXMobikpKTsKICBjb25zdCBhbW1vSXRlbXMgICAgID0gT2JqZWN0LmVudHJpZXMoT1NFX1dFQVBPTlMpCiAgICAuZmlsdGVyKChbbix3XSkgPT4gdy5yYW5nZWQgJiYgdy5kbWcgPT09ICctJyk7CiAgY29uc3QgYXJtb3VySXRlbXMgICA9IE9iamVjdC5lbnRyaWVzKE9TRV9BUk1PVVIpCiAgICAuZmlsdGVyKChbbl0pID0+IGFsbG93ZWRBcm1vdXIuaW5jbHVkZXMobikpOwogIGNvbnN0IGVxdWlwSXRlbXMgICAgPSBPYmplY3QuZW50cmllcyhPU0VfRVFVSVBNRU5UKTsKCiAgZnVuY3Rpb24gd2VhcG9uTGFiZWwobmFtZSwgdykgewogICAgY29uc3QgY29zdCA9IHcuY29zdCA+IDAgPyBgICgke3cuY29zdH1ncClgIDogJyAoZnJlZSknOwogICAgY29uc3Qgbm90ZXMgPSB3Lm5vdGVzID8gYCAtLSAke3cubm90ZXN9YCA6ICcnOwogICAgcmV0dXJuIGAke25hbWV9IFske3cuZG1nfV0ke2Nvc3R9JHtub3Rlc31gOwogIH0KICBmdW5jdGlvbiBhcm1vdXJMYWJlbChuYW1lLCBhKSB7CiAgICByZXR1cm4gYCR7bmFtZX0gLS0gQUMgJHthLmFjfSAoJHthLmNvc3R9Z3ApYDsKICB9CiAgZnVuY3Rpb24gZXF1aXBMYWJlbChuYW1lLCBlKSB7CiAgICBjb25zdCBjb3N0ID0gZS5jb3N0ID4gMCA/IGAgKCR7ZS5jb3N0fWdwKWAgOiAnIChmcmVlKSc7CiAgICBjb25zdCBub3RlcyA9IGUubm90ZXMgPyBgIC0tICR7ZS5ub3Rlc31gIDogJyc7CiAgICByZXR1cm4gYCR7bmFtZX0ke2Nvc3R9JHtub3Rlc31gOwogIH0KCiAgbGV0IGh0bWwgPSAnJzsKCiAgLy8gTWVsZWUgd2VhcG9ucwogIGlmIChtZWxlZVdlYXBvbnMubGVuZ3RoKSB7CiAgICBodG1sICs9IGJ1aWxkRXF1aXBTZWN0aW9uKCdNZWxlZSBXZWFwb24nLCBtZWxlZVdlYXBvbnMubWFwKChbbix3XSkgPT4gKHsKICAgICAga2V5OiBuLCBsYWJlbDogd2VhcG9uTGFiZWwobix3KSwgY29zdDogdy5jb3N0CiAgICB9KSkpOwogIH0KCiAgLy8gUmFuZ2VkIHdlYXBvbnMKICBpZiAocmFuZ2VkV2VhcG9ucy5sZW5ndGgpIHsKICAgIGh0bWwgKz0gYnVpbGRFcXVpcFNlY3Rpb24oJ1JhbmdlZCBXZWFwb24nLCByYW5nZWRXZWFwb25zLm1hcCgoW24sd10pID0+ICh7CiAgICAgIGtleTogbiwgbGFiZWw6IHdlYXBvbkxhYmVsKG4sdyksIGNvc3Q6IHcuY29zdAogICAgfSkpLCB0cnVlKTsgLy8gb3B0aW9uYWwKICB9CgogIC8vIEFtbW8gKHNob3duIG9ubHkgaWYgcmFuZ2VkIHdlYXBvbiBzZWxlY3RlZCAtLSBhbHdheXMgc2hvdyBhbGwpCiAgaWYgKHJhbmdlZFdlYXBvbnMubGVuZ3RoKSB7CiAgICBodG1sICs9IGJ1aWxkRXF1aXBTZWN0aW9uKCdBbW11bml0aW9uJywgYW1tb0l0ZW1zLm1hcCgoW24sd10pID0+ICh7CiAgICAgIGtleTogbiwgbGFiZWw6IGAke259JHt3LmNvc3QgPiAwID8gJyAoJyt3LmNvc3QrJ2dwKScgOiAnIChmcmVlKSd9YCwgY29zdDogdy5jb3N0CiAgICB9KSksIHRydWUpOwogIH0KCiAgLy8gQXJtb3VyCiAgaWYgKGFybW91ckl0ZW1zLmxlbmd0aCkgewogICAgaHRtbCArPSBidWlsZEVxdWlwU2VjdGlvbignQXJtb3VyJywgYXJtb3VySXRlbXMubWFwKChbbixhXSkgPT4gKHsKICAgICAga2V5OiBuLCBsYWJlbDogYXJtb3VyTGFiZWwobixhKSwgY29zdDogYS5jb3N0CiAgICB9KSkpOwogICAgLy8gU2hpZWxkIGFzIHNlcGFyYXRlIG9wdGlvbmFsIHBpY2sgaWYgY2xhc3MgYWxsb3dzCiAgICBpZiAoYWxsb3dlZEFybW91ci5pbmNsdWRlcygnU2hpZWxkJykpIHsKICAgICAgaHRtbCArPSBidWlsZEVxdWlwU2VjdGlvbignU2hpZWxkJywgW3trZXk6J1NoaWVsZCcsIGxhYmVsOidTaGllbGQgLS0gKzEgQUMgKDEwZ3ApJywgY29zdDoxMH0sCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICB7a2V5Oidub25lJywgbGFiZWw6J05vIFNoaWVsZCcsIGNvc3Q6MH1dLCBmYWxzZSk7CiAgICB9CiAgfQoKICAvLyBFcXVpcG1lbnQgLS0gcGljayB1cCB0byA0IGl0ZW1zIGZyb20gdGhlIE9TRSBsaXN0CiAgaHRtbCArPSBgPGRpdiBjbGFzcz0iZXF1aXAtY2F0ZWdvcnkiPgogICAgPGRpdiBjbGFzcz0iZXF1aXAtY2F0LXRpdGxlIj5FcXVpcG1lbnQgKHBpY2sgaXRlbXMgLS0gY29zdCBkZWR1Y3RlZCBmcm9tIGdvbGQpPC9kaXY+CiAgICA8ZGl2IGNsYXNzPSJlcXVpcC1vcHRpb25zIiBpZD0ib3NlLWVxdWlwLWdyaWQiPgogICAgICAke2VxdWlwSXRlbXMubWFwKChbbixlXSkgPT4KICAgICAgICBgPGRpdiBjbGFzcz0iZXF1aXAtb3B0IiBkYXRhLWNhdD0iZXF1aXAiIGRhdGEtaXRlbT0iJHtufSIgZGF0YS1jb3N0PSIke2UuY29zdH0iCiAgICAgICAgICBvbmNsaWNrPSJ0b2dnbGVFcXVpcEl0ZW0odGhpcykiPiR7ZXF1aXBMYWJlbChuLGUpfTwvZGl2PmAKICAgICAgKS5qb2luKCcnKX0KICAgIDwvZGl2PgogIDwvZGl2PmA7CgogIGNhdHMuaW5uZXJIVE1MID0gaHRtbDsKICByZWNhbGNHb2xkU3BlbnQoKTsKICB1cGRhdGVHb2xkRGlzcGxheSgpOwogIHVwZGF0ZUludmVudG9yeVByZXZpZXcoKTsKfQoKZnVuY3Rpb24gYnVpbGRFcXVpcFNlY3Rpb24oY2F0LCBpdGVtcywgb3B0aW9uYWw9ZmFsc2UpIHsKICBpZiAoIWl0ZW1zLmxlbmd0aCkgcmV0dXJuICcnOwogIGNvbnN0IGZpcnN0S2V5ID0gb3B0aW9uYWwgPyAnbm9uZScgOiBpdGVtc1swXS5rZXk7CiAgaWYgKCFvcHRpb25hbCAmJiAhc2VsZWN0ZWRFcXVpcFtjYXRdKSBzZWxlY3RlZEVxdWlwW2NhdF0gPSBpdGVtc1swXS5rZXk7CiAgaWYgKG9wdGlvbmFsICYmICFzZWxlY3RlZEVxdWlwW2NhdF0pIHNlbGVjdGVkRXF1aXBbY2F0XSA9ICdub25lJzsKICBjb25zdCBub25lT3B0ID0gb3B0aW9uYWwgPyBgPGRpdiBjbGFzcz0iZXF1aXAtb3B0JHtmaXJzdEtleT09PSdub25lJz8nIHNlbCc6Jyd9IiBkYXRhLWNhdD0iJHtjYXR9IiBkYXRhLWl0ZW09Im5vbmUiIGRhdGEtY29zdD0iMCIgb25jbGljaz0icGlja0VxdWlwKHRoaXMpIj5Ob25lPC9kaXY+YCA6ICcnOwogIHJldHVybiBgPGRpdiBjbGFzcz0iZXF1aXAtY2F0ZWdvcnkiPgogICAgPGRpdiBjbGFzcz0iZXF1aXAtY2F0LXRpdGxlIj4ke2NhdH08L2Rpdj4KICAgIDxkaXYgY2xhc3M9ImVxdWlwLW9wdGlvbnMiPgogICAgICAke25vbmVPcHR9CiAgICAgICR7aXRlbXMubWFwKGl0ZW0gPT4KICAgICAgICBgPGRpdiBjbGFzcz0iZXF1aXAtb3B0JHtpdGVtLmtleT09PWZpcnN0S2V5JiYhb3B0aW9uYWw/JyBzZWwnOicnfSIgZGF0YS1jYXQ9IiR7Y2F0fSIgZGF0YS1pdGVtPSIke2l0ZW0ua2V5fSIgZGF0YS1jb3N0PSIke2l0ZW0uY29zdH0iIG9uY2xpY2s9InBpY2tFcXVpcCh0aGlzKSI+JHtpdGVtLmxhYmVsfTwvZGl2PmAKICAgICAgKS5qb2luKCcnKX0KICAgIDwvZGl2PgogIDwvZGl2PmA7Cn0KCmZ1bmN0aW9uIHRvZ2dsZUVxdWlwSXRlbShlbCkgewogIGNvbnN0IGl0ZW0gPSBlbC5kYXRhc2V0Lml0ZW07CiAgY29uc3QgY29zdCA9IHBhcnNlSW50KGVsLmRhdGFzZXQuY29zdCkgfHwgMDsKICBpZiAoc2VsZWN0ZWRFcXVpcEl0ZW1zLmhhcyhpdGVtKSkgewogICAgc2VsZWN0ZWRFcXVpcEl0ZW1zLmRlbGV0ZShpdGVtKTsKICAgIGVsLmNsYXNzTGlzdC5yZW1vdmUoJ3NlbCcpOwogIH0gZWxzZSB7CiAgICAvLyBDaGVjayBpZiB3ZSBjYW4gYWZmb3JkIGl0CiAgICBpZiAoZ29sZFNwZW50ICsgY29zdCA+IHN0YXJ0aW5nR29sZCkgewogICAgICBlbC5zdHlsZS5vdXRsaW5lID0gJzFweCBzb2xpZCAjYzA2MDYwJzsKICAgICAgc2V0VGltZW91dCgoKSA9PiBlbC5zdHlsZS5vdXRsaW5lID0gJycsIDgwMCk7CiAgICAgIHJldHVybjsKICAgIH0KICAgIHNlbGVjdGVkRXF1aXBJdGVtcy5hZGQoaXRlbSk7CiAgICBlbC5jbGFzc0xpc3QuYWRkKCdzZWwnKTsKICB9CiAgLy8gVXBkYXRlIGV4dHJhSXRlbXMgZnJvbSBzZWxlY3RlZEVxdWlwSXRlbXMKICBleHRyYUl0ZW1zID0gQXJyYXkuZnJvbShzZWxlY3RlZEVxdWlwSXRlbXMpOwogIHJlY2FsY0dvbGRTcGVudCgpOwogIHVwZGF0ZUdvbGREaXNwbGF5KCk7CiAgdXBkYXRlSW52ZW50b3J5UHJldmlldygpOwp9CgpmdW5jdGlvbiByZWNhbGNHb2xkU3BlbnQoKSB7CiAgZ29sZFNwZW50ID0gMDsKICAvLyBXZWFwb24gY29zdHMKICBPYmplY3QuZW50cmllcyhzZWxlY3RlZEVxdWlwKS5mb3JFYWNoKChbY2F0LCBrZXldKSA9PiB7CiAgICBpZiAoa2V5ID09PSAnbm9uZScpIHJldHVybjsKICAgIGNvbnN0IHcgPSBPU0VfV0VBUE9OU1trZXldOwogICAgY29uc3QgYSA9IE9TRV9BUk1PVVJba2V5XTsKICAgIGlmICh3KSBnb2xkU3BlbnQgKz0gdy5jb3N0OwogICAgZWxzZSBpZiAoYSkgZ29sZFNwZW50ICs9IGEuY29zdDsKICB9KTsKICAvLyBFcXVpcG1lbnQgY29zdHMKICBzZWxlY3RlZEVxdWlwSXRlbXMuZm9yRWFjaChuYW1lID0+IHsKICAgIGNvbnN0IGUgPSBPU0VfRVFVSVBNRU5UW25hbWVdOwogICAgaWYgKGUpIGdvbGRTcGVudCArPSBlLmNvc3Q7CiAgfSk7Cn0KCmZ1bmN0aW9uIHBpY2tFcXVpcChlbCkgewogIGNvbnN0IGNhdCA9IGVsLmRhdGFzZXQuY2F0OwogIGNvbnN0IGl0ZW0gPSBlbC5kYXRhc2V0Lml0ZW07CiAgZG9jdW1lbnQucXVlcnlTZWxlY3RvckFsbChgLmVxdWlwLW9wdFtkYXRhLWNhdD0iJHtjYXR9Il1gKS5mb3JFYWNoKGUgPT4gZS5jbGFzc0xpc3QucmVtb3ZlKCdzZWwnKSk7CiAgZWwuY2xhc3NMaXN0LmFkZCgnc2VsJyk7CiAgc2VsZWN0ZWRFcXVpcFtjYXRdID0gaXRlbTsKICByZWNhbGNHb2xkU3BlbnQoKTsKICB1cGRhdGVHb2xkRGlzcGxheSgpOwogIHVwZGF0ZUludmVudG9yeVByZXZpZXcoKTsKICB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCk7Cn0KCmZ1bmN0aW9uIHJlbmRlckV4dHJhSXRlbXMoKSB7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnZXh0cmEtaXRlbXMtbGlzdCcpOwogIGVsLmlubmVySFRNTCA9IFNIT1BfSVRFTVMubWFwKGl0ZW0gPT4KICAgIGA8ZGl2IGNsYXNzPSJlcXVpcC1vcHQke2V4dHJhSXRlbXMuaW5jbHVkZXMoaXRlbS5uYW1lKT8nIHNlbCc6Jyd9IiAKICAgICAgb25jbGljaz0idG9nZ2xlRXh0cmEoJyR7aXRlbS5uYW1lfScsJHtpdGVtLmNvc3R9KSI+JHtpdGVtLm5hbWV9ICgke2l0ZW0uY29zdH1ncCk8L2Rpdj5gCiAgKS5qb2luKCcnKTsKfQoKZnVuY3Rpb24gdG9nZ2xlRXh0cmEobmFtZSwgY29zdCkgewogIGNvbnN0IGlkeCA9IGV4dHJhSXRlbXMuaW5kZXhPZihuYW1lKTsKICBpZiAoaWR4ID49IDApIHsKICAgIGV4dHJhSXRlbXMuc3BsaWNlKGlkeCwgMSk7CiAgICBnb2xkU3BlbnQgLT0gY29zdDsKICB9IGVsc2UgewogICAgaWYgKGdvbGRTcGVudCArIGNvc3QgPiBzdGFydGluZ0dvbGQpIHsgYWxlcnQoYE5vdCBlbm91Z2ggZ29sZCEgWW91IGhhdmUgJHtzdGFydGluZ0dvbGQgLSBnb2xkU3BlbnR9Z3AgcmVtYWluaW5nLmApOyByZXR1cm47IH0KICAgIGV4dHJhSXRlbXMucHVzaChuYW1lKTsKICAgIGdvbGRTcGVudCArPSBjb3N0OwogIH0KICByZW5kZXJFeHRyYUl0ZW1zKCk7CiAgdXBkYXRlR29sZERpc3BsYXkoKTsKICB1cGRhdGVJbnZlbnRvcnlQcmV2aWV3KCk7Cn0KCmZ1bmN0aW9uIHVwZGF0ZUdvbGREaXNwbGF5KCkgewogIHJlY2FsY0dvbGRTcGVudCgpOwogIGNvbnN0IHJlbWFpbmluZyA9IHN0YXJ0aW5nR29sZCAtIGdvbGRTcGVudDsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdnb2xkLXJlbWFpbmluZycpOwogIGlmIChlbCkgewogICAgZWwudGV4dENvbnRlbnQgPSAnR29sZDogJyArIHJlbWFpbmluZyArICdncCByZW1haW5pbmcgKHN0YXJ0ZWQgd2l0aCAnICsgc3RhcnRpbmdHb2xkICsgJ2dwLCBzcGVudCAnICsgZ29sZFNwZW50ICsgJ2dwKSc7CiAgICBlbC5zdHlsZS5jb2xvciA9IHJlbWFpbmluZyA8IDAgPyAnI2MwNjA2MCcgOiByZW1haW5pbmcgPCAyMCA/ICcjYzA5MDQwJyA6ICd2YXIoLS1pbmstZGltKSc7CiAgfQp9CgpmdW5jdGlvbiBzcGxpdENvbWJpbmVkSXRlbShpdGVtKSB7CiAgLy8gT25seSBzcGxpdCB3ZWFwb24rYW1tbyBwYXR0ZXJucyBsaWtlICJMaWdodCBDcm9zc2JvdyArIEJvbHRzIHgyMCIKICAvLyBEbyBOT1Qgc3BsaXQgYXJtb3VyIGNvbWJvcyBsaWtlICJDaGFpbiBNYWlsICsgU2hpZWxkIiBvciAiU2hpZWxkICgrMSBBQykiCiAgY29uc3QgYW1tb1BhdHRlcm4gPSAvYm9sdHM/fGFycm93cz98cXVhcnJlbHM/fHNob3RzPy9pOwogIGlmICghaXRlbS5pbmNsdWRlcygnKycpKSByZXR1cm4gW2l0ZW1dOwogIC8vIE9ubHkgc3BsaXQgaWYgb25lIHBhcnQgbG9va3MgbGlrZSBhbW1vCiAgY29uc3QgcGFydHMgPSBpdGVtLnNwbGl0KCcrJykubWFwKHMgPT4gcy50cmltKCkpOwogIGNvbnN0IGhhc0FtbW8gPSBwYXJ0cy5zb21lKHAgPT4gYW1tb1BhdHRlcm4udGVzdChwKSk7CiAgaWYgKCFoYXNBbW1vKSByZXR1cm4gW2l0ZW1dOyAvLyBLZWVwICJDaGFpbiBNYWlsICsgU2hpZWxkIiBhcyBvbmUgaXRlbQogIHJldHVybiBwYXJ0cy5tYXAocGFydCA9PiB7CiAgICAvLyBOb3JtYWxpc2UgIjIwIGJvbHRzIiAtPiAiQm9sdHMgeDIwIgogICAgY29uc3QgbSA9IHBhcnQubWF0Y2goL14oWy5dZCspWy5dcysoLispJC8pOwogICAgaWYgKG0pIHJldHVybiBtWzJdLmNoYXJBdCgwKS50b1VwcGVyQ2FzZSgpICsgbVsyXS5zbGljZSgxKSArICcgeCcgKyBtWzFdOwogICAgcmV0dXJuIHBhcnQ7CiAgfSkuZmlsdGVyKEJvb2xlYW4pOwp9CgpmdW5jdGlvbiBnZXRGaW5hbEludmVudG9yeSgpIHsKICBjb25zdCBpdGVtcyA9IFtdOwoKICAvLyBBZGQgc2VsZWN0ZWQgd2VhcG9ucy9hcm1vdXIgZnJvbSByYWRpby1zdHlsZSBwaWNrcwogIE9iamVjdC5lbnRyaWVzKHNlbGVjdGVkRXF1aXApLmZvckVhY2goKFtjYXQsIGtleV0pID0+IHsKICAgIGlmICgha2V5IHx8IGtleSA9PT0gJ25vbmUnKSByZXR1cm47CiAgICAvLyBJdCdzIGEgd2VhcG9uIG9yIGFybW91ciBrZXkgZnJvbSBPU0VfV0VBUE9OUyAvIE9TRV9BUk1PVVIKICAgIGNvbnN0IHcgPSBPU0VfV0VBUE9OU1trZXldOwogICAgY29uc3QgYSA9IE9TRV9BUk1PVVJba2V5XTsKICAgIGlmICh3KSB7CiAgICAgIC8vIEFkZCB3ZWFwb247IGFtbW8gaXRlbXMgc3RvcmVkIHNlcGFyYXRlbHkgaW4gc3RhdHVzCiAgICAgIGlmICh3LmRtZyA9PT0gJy0nKSByZXR1cm47IC8vIGFtbW8gaGFuZGxlZCBiZWxvdwogICAgICBpdGVtcy5wdXNoKGtleSk7CiAgICB9IGVsc2UgaWYgKGEpIHsKICAgICAgaXRlbXMucHVzaChrZXkpOwogICAgfSBlbHNlIGlmIChrZXkgIT09ICdub25lJykgewogICAgICAvLyBGYWxsYmFjazoganVzdCBhZGQgdGhlIGtleSBhcy1pcwogICAgICBpdGVtcy5wdXNoKGtleSk7CiAgICB9CiAgfSk7CgogIC8vIEFkZCBhbW1vIHNlbGVjdGlvbnMKICBPYmplY3QuZW50cmllcyhzZWxlY3RlZEVxdWlwKS5mb3JFYWNoKChbY2F0LCBrZXldKSA9PiB7CiAgICBpZiAoIWtleSB8fCBrZXkgPT09ICdub25lJykgcmV0dXJuOwogICAgY29uc3QgdyA9IE9TRV9XRUFQT05TW2tleV07CiAgICBpZiAodyAmJiB3LmRtZyA9PT0gJy0nKSBpdGVtcy5wdXNoKGtleSk7CiAgfSk7CgogIC8vIEFkZCBtdWx0aS1zZWxlY3QgZXF1aXBtZW50IGl0ZW1zCiAgc2VsZWN0ZWRFcXVpcEl0ZW1zLmZvckVhY2gobmFtZSA9PiB7CiAgICBpZiAobmFtZSkgaXRlbXMucHVzaChuYW1lKTsKICB9KTsKCiAgLy8gRmFsbGJhY2s6IGVuc3VyZSBiYWNrcGFjayBhbmQgd2F0ZXJza2luIGlmIG5vdGhpbmcgc2VsZWN0ZWQKICBpZiAoIWl0ZW1zLnNvbWUoaSA9PiAvYmFja3BhY2svaS50ZXN0KGkpKSkgaXRlbXMucHVzaCgnQmFja3BhY2snKTsKICBpZiAoIWl0ZW1zLnNvbWUoaSA9PiAvd2F0ZXJza2luL2kudGVzdChpKSkpIGl0ZW1zLnB1c2goJ1dhdGVyc2tpbicpOwoKICByZXR1cm4gaXRlbXM7Cn0KCmZ1bmN0aW9uIHVwZGF0ZUludmVudG9yeVByZXZpZXcoKSB7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2ZpbmFsLWludi1wcmV2aWV3JykudGV4dENvbnRlbnQgPSBnZXRGaW5hbEludmVudG9yeSgpLmpvaW4oJywgJyk7Cn0KCmFzeW5jIGZ1bmN0aW9uIG1hcmtSZWFkeSgpIHsKICBjb25zb2xlLmxvZygnW21hcmtSZWFkeV0gY2FsbGVkJyk7CiAgY29uc29sZS5sb2coJ1ttYXJrUmVhZHldIGNob3NlbkNsYXNzOicsIGNob3NlbkNsYXNzLCAnY2hvc2VuUmFjZTonLCBjaG9zZW5SYWNlKTsKICBjb25zb2xlLmxvZygnW21hcmtSZWFkeV0gcm9sbGVkU3RhdHM6JywgSlNPTi5zdHJpbmdpZnkocm9sbGVkU3RhdHMpKTsKICBjb25zb2xlLmxvZygnW21hcmtSZWFkeV0gQ0xBU1NFU1tjaG9zZW5DbGFzc106JywgSlNPTi5zdHJpbmdpZnkoQ0xBU1NFU1tjaG9zZW5DbGFzc10pKTsKICAvLyBHdWFyZDogbXVzdCBoYXZlIGEgbW9kdWxlIGxvYWRlZCAoZ3Vlc3RzIGdldCBpdCBmcm9tIHJvb20sIGhvc3RzIHNlbGVjdCBpdCkKICBpZiAoIW1vZHVsZVRleHQgfHwgbW9kdWxlVGV4dC5sZW5ndGggPCAxMCkgewogICAgaWYgKGlzTXVsdGlwbGF5ZXIgJiYgcm9vbUNvZGUgJiYgIWlzSG9zdCkgewogICAgICAvLyBHdWVzdCAtLSB0cnkgdG8gZmV0Y2ggbW9kdWxlIGZyb20gcm9vbSBvbmUgbW9yZSB0aW1lCiAgICAgIHRyeSB7CiAgICAgICAgY29uc3QgcmQgPSBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvam9pbl9yb29tJywge21ldGhvZDonUE9TVCcsCiAgICAgICAgICBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGU6IHJvb21Db2RlLCBwbGF5ZXI6IHBsYXllck5hbWV9KX0pLnRoZW4ocj0+ci5qc29uKCkpOwogICAgICAgIGlmIChyZC5tb2R1bGVUZXh0KSB7CiAgICAgICAgICBtb2R1bGVUZXh0ID0gcmQubW9kdWxlVGV4dDsKICAgICAgICAgIGxvYWRlZE1vZHVsZURhdGEgPSByZC5tb2R1bGVEYXRhIHx8IHt9OwogICAgICAgICAgbW9kdWxlTmFtZSA9IHJkLm1vZHVsZU5hbWUgfHwgbW9kdWxlTmFtZTsKICAgICAgICB9CiAgICAgIH0gY2F0Y2goZSkge30KICAgIH0KICAgIGlmICghbW9kdWxlVGV4dCB8fCBtb2R1bGVUZXh0Lmxlbmd0aCA8IDEwKSB7CiAgICAgIGFsZXJ0KCdObyBtb2R1bGUgbG9hZGVkLiBJZiB5b3UgYXJlIGEgZ3Vlc3QsIHRoZSBob3N0IG11c3Qgc2VsZWN0IGEgbW9kdWxlIGZpcnN0LicpOwogICAgICByZXR1cm47CiAgICB9CiAgfQogIHRyeSB7CiAgY29uc3QgbmFtZSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW5hbWUtaW5wJykudmFsdWUudHJpbSgpIHx8IHBsYXllck5hbWUgfHwgJ0FkdmVudHVyZXInOwogIHBsYXllck5hbWUgPSBuYW1lOyAvLyBjaGFyYWN0ZXIgbmFtZSBJUyB0aGUgcGxheWVyIG5hbWUKICBjb25zb2xlLmxvZygnW21hcmtSZWFkeV0gbmFtZTonLCBuYW1lKTsKICBjb25zdCBjbHMgPSBDTEFTU0VTW2Nob3NlbkNsYXNzXTsKICBjb25zdCBoZFNpemUgPSBjbHMuaGQgfHwgY2xzLmhwIHx8IDY7CiAgY29uc3QgaHAgPSBNYXRoLm1heCgxLCAoTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKmhkU2l6ZSkrMSkgKyBtb2ROKHJvbGxlZFN0YXRzLkNPTikpOwogIGNvbnN0IHJhY2VEYXRhID0gUkFDRVNbY2hvc2VuUmFjZV07CiAgcGMgPSB7CiAgICBuYW1lLCByYWNlOiBjaG9zZW5SYWNlLCBjbHM6IGNob3NlbkNsYXNzLCBsZXZlbDogMSwKICAgIGhwLCBtYXhocDogaHAsIGFjOiBjbHMuYWMsCiAgICBzdGF0czogey4uLnJvbGxlZFN0YXRzfSwKICAgIGludjogZ2V0RmluYWxJbnZlbnRvcnkoKSwKICAgIGdvbGQ6IChmdW5jdGlvbigpeyByZWNhbGNHb2xkU3BlbnQoKTsgcmV0dXJuIE1hdGgubWF4KDAsIHN0YXJ0aW5nR29sZCAtIGdvbGRTcGVudCk7IH0pKCksCiAgICBsb2M6ICcuLi4nLCBsb2N0YWc6ICcnLCBxdWVzdHM6IFtdLAogICAgc3BlY2lhbHM6IHJhY2VEYXRhPy5zcGVjaWFscyB8fCBbXSwKICAgIHNhdmVzOiBjbHMuc2F2ZXMKICB9OwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZWFkeS1idG4nKS50ZXh0Q29udGVudCA9ICcgUmVhZHkhJzsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJykuZGlzYWJsZWQgPSB0cnVlOwogICAgLy8gQXV0by1zYXZlIGNoYXJhY3RlciB0byBkaXNrIGltbWVkaWF0ZWx5IG9uIGNyZWF0aW9uCiAgICB4aHJGZXRjaChCQVNFX1VSTCArICcvc2F2ZV9jaGFyYWN0ZXInLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwgYm9keTogSlNPTi5zdHJpbmdpZnkocGMpfSk7CgogIH0gY2F0Y2goZSkgeyBjb25zb2xlLmVycm9yKCdbbWFya1JlYWR5XSBFcnJvcjonLCBlKTsgYWxlcnQoJ0NoYXJhY3RlciBjcmVhdGlvbiBlcnJvcjogJyArIGUubWVzc2FnZSk7IHJldHVybjsgfQogIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlKSB7CiAgICB4aHJGZXRjaChCQVNFX1VSTCArICcvcGxheWVyX3JlYWR5Jywge21ldGhvZDonUE9TVCcsIGhlYWRlcnM6eydDb250ZW50LVR5cGUnOidhcHBsaWNhdGlvbi9qc29uJ30sIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOnJvb21Db2RlLCBwbGF5ZXI6cGxheWVyTmFtZSwgcGN9KX0pOwogICAgaWYgKGlzSG9zdCkgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2JlZ2luLWJ0bicpLnN0eWxlLmRpc3BsYXkgPSAnaW5saW5lLWJsb2NrJzsKICB9IGVsc2UgewogICAgYmVnaW5BZHZlbnR1cmUoKTsKICB9Cn0KCmZ1bmN0aW9uIGJlZ2luQWR2ZW50dXJlKCkgewogIGNvbnNvbGUubG9nKCdbYmVnaW5BZHZlbnR1cmVdIGNhbGxlZCwgaXNNdWx0aXBsYXllcjonLCBpc011bHRpcGxheWVyLCAncm9vbUNvZGU6Jywgcm9vbUNvZGUpOwogIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlKSB7CiAgICB4aHJGZXRjaChCQVNFX1VSTCArICcvZ2V0X3Jvb20nKS50aGVuKHIgPT4gci5qc29uKCkpOyAvLyBub29wCiAgfQogIHBhcnR5UENzW3BsYXllck5hbWVdID0gcGM7CiAgLy8gRmV0Y2ggYWxsIHBhcnR5IFBDcyBmcm9tIHNlcnZlciBpZiBtdWx0aXBsYXllcgogIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlKSB7CiAgICBmZXRjaChgL3Jvb21fc3RhdGU/Y29kZT0ke3Jvb21Db2RlfWApLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oc3RhdGUgPT4gewogICAgICBwYXJ0eVBDcyA9IHN0YXRlLnBhcnR5UENzIHx8IHtbcGxheWVyTmFtZV06IHBjfTsKICAgICAgT2JqZWN0LmtleXMocGFydHlQQ3MpLmZvckVhY2goKG4saSkgPT4geyBjb2xvck1hcFtuXSA9IFBMQVlFUl9DT0xPUlNbaSVQTEFZRVJfQ09MT1JTLmxlbmd0aF07IH0pOwogICAgICBzeXN0ZW1Qcm9tcHQgPSBidWlsZFN5c3RlbVByb21wdCgpOwogICAgICB4aHJGZXRjaChCQVNFX1VSTCArICcvdXBkYXRlX3Jvb20nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwgYm9keTogSlNPTi5zdHJpbmdpZnkoe2NvZGU6cm9vbUNvZGUsIHN5c3RlbVByb21wdCwgZ2FtZUFjdGl2ZTp0cnVlLCBwYXJ0eVBDc30pfSk7CiAgICAgIGxhdW5jaEdhbWUoKTsKICAgIH0pOwogIH0gZWxzZSB7CiAgICBwYXJ0eVBDcyA9IHtbcGxheWVyTmFtZV06IHBjfTsKICAgIHN5c3RlbVByb21wdCA9IGJ1aWxkU3lzdGVtUHJvbXB0KCk7CiAgICBsYXVuY2hHYW1lKCk7CiAgfQp9CgpmdW5jdGlvbiBpbml0UmVzb3VyY2VzRnJvbUludmVudG9yeSgpIHsKICBjb25zdCBpbnYgPSAocGMuaW52IHx8IFtdKS5qb2luKCcgJykudG9Mb3dlckNhc2UoKTsKCiAgLy8gTGFudGVybiAtLSBPU0UgaXRlbSBuYW1lIGlzIGp1c3QgIkxhbnRlcm4iCiAgaGFzTGFudGVybiA9IC9sYW50ZXJuL2kudGVzdChpbnYpOwoKICAvLyBPaWwgZmxhc2tzIC0tIE9TRTogIk9pbCAoMSBmbGFzaykiCiAgY29uc3Qgb2lsTWF0Y2ggPSBpbnYubWF0Y2goL29pbFteWy5dbl0qKFsuXWQrKS9pKTsKICBsYW50ZXJuT2lsRmxhc2tzTGVmdCA9IG9pbE1hdGNoID8gcGFyc2VJbnQob2lsTWF0Y2hbMV0pIDogKGhhc0xhbnRlcm4gPyAxIDogMCk7CgogIC8vIFRvcmNoZXMgLS0gT1NFOiAiVG9yY2hlcyAoNikiID0gcGFjayBvZiA2LCBlYWNoIGJ1cm5zIDYgdHVybnMKICBjb25zdCB0b3JjaE1hdGNoID0gaW52Lm1hdGNoKC90b3JjaGVzP1suXXMqWy5dPyhbMC05XSspWy5dPy9pKQogICAgfHwgaW52Lm1hdGNoKC8oWzAtOV0rKVsuXXMqdG9yY2hlcz8vaSk7CiAgY29uc3QgdG9yY2hDb3VudCA9IHRvcmNoTWF0Y2ggPyBwYXJzZUludCh0b3JjaE1hdGNoWzFdKSA6IDA7CgogIC8vIFJhdGlvbnMgLS0gT1NFOiAiUmF0aW9ucyAoaXJvbiwgNyBkYXlzKSIgb3IgIlJhdGlvbnMgKHN0YW5kYXJkLCA3IGRheXMpIiA9IDcgZGF5IHN1cHBseQogIGlmICgvcmF0aW9ucz8vaS50ZXN0KGludikpIHsKICAgIHJhdGlvbnNMZWZ0ID0gNzsgLy8gQm90aCBPU0UgcmF0aW9uIHR5cGVzIGFyZSA3LWRheSBzdXBwbGllcwogIH0gZWxzZSB7CiAgICByYXRpb25zTGVmdCA9IDA7CiAgfQoKICAvLyBUb3JjaGVzIGluIGludmVudG9yeSBkb2VzIE5PVCBtZWFuIHRoZXkgYXJlIGxpdCAtIHBsYXllciBtdXN0IHVzZSBvbmUKICB0b3JjaGVzQ2FycmllZCA9IHRvcmNoQ291bnQ7CiAgdG9yY2hUdXJuc0xlZnQgPSAwOwogIHRvcmNoTGl0ID0gZmFsc2U7CiAgbGFudGVybkxpdCA9IGZhbHNlOwogIHRvcmNoRXZlclVzZWQgPSBmYWxzZTsKICBpc0NhcnJ5aW5nTGlnaHQgPSB0cnVlOyAgICAgICAvLyBhc3N1bWUgZGF5bGlnaHQvYW1iaWVudCBhdCBzdGFydAogIC8vIFJlc2V0IGFsbCBwZW5hbHR5IHRyYWNrZXJzCiAgcmVzdERlYnQgPSAwOwogIHR1cm5zV2l0aG91dFJlc3QgPSAwOwogIGZhdGlndWVQZW5hbHR5ID0gMDsKICBkYXlzV2l0aG91dEZvb2QgPSAwOwogIHN0YXJ2YXRpb25QZW5hbHR5ID0gMDsKICBmb3JjZWRNYXJjaEFjdGl2ZSA9IGZhbHNlOwogIHdhbmRlcmluZ01vbnN0ZXJUdXJuQ291bnRlciA9IDA7CgogIGNvbnNvbGUubG9nKCdbUmVzb3VyY2VzXSBJbml0IC0tIHRvcmNoZXM6JywgdG9yY2hDb3VudCwgJygnLCB0b3JjaFR1cm5zTGVmdCwgJ3R1cm5zKScsCiAgICAnfCBsYW50ZXJuOicsIGhhc0xhbnRlcm4sICd8IG9pbDonLCBsYW50ZXJuT2lsRmxhc2tzTGVmdCwKICAgICd8IHJhdGlvbnM6JywgcmF0aW9uc0xlZnQpOwp9CgpmdW5jdGlvbiBhZHZhbmNlRHVuZ2VvblR1cm4odHVybnMpIHsKICB0dXJucyA9IHR1cm5zIHx8IDE7CiAgZHVuZ2VvblR1cm5zICs9IHR1cm5zOwogIHJlc3REZWJ0ICs9IHR1cm5zOyAgICAgICAgICAgICAvLyBsZWdhY3kgY29tcGF0CiAgdHVybnNXaXRob3V0UmVzdCArPSB0dXJuczsKICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgKz0gdHVybnM7CgogIC8vIE9TRSBkdW5nZW9uIHJlc3QgcnVsZTogZXZlcnkgNiB0dXJucyBleHBsb3JlZCB3aXRob3V0IGEgMS10dXJuIHJlc3QKICAvLyBpbXBvc2VzIGEgY3VtdWxhdGl2ZSAtMSB0byBhdHRhY2sgcm9sbHMKICAvLyAoY29tbW9uIGludGVycHJldGF0aW9uIG9mIHRoZSByZXN0LWV2ZXJ5LTYtdHVybnMgcmVxdWlyZW1lbnQpCiAgLy8gT25seSBhcHBseSBmYXRpZ3VlIHBlbmFsdHkgaW4gZHVuZ2VvbiAoT1NFIHJ1bGUgb25seSBhcHBsaWVzIHVuZGVyZ3JvdW5kKQogIGZhdGlndWVQZW5hbHR5ID0gaXNJbkR1bmdlb24oKSA/IE1hdGguZmxvb3IodHVybnNXaXRob3V0UmVzdCAvIDYpIDogMDsKCiAgLy8gQnVybiB0b3JjaCAoT1NFOiB0b3JjaCBidXJucyBjb250aW51b3VzbHksIDYgdHVybnMgZWFjaCkKICBpZiAodG9yY2hUdXJuc0xlZnQgPiAwKSB7CiAgICB0b3JjaFR1cm5zTGVmdCA9IE1hdGgubWF4KDAsIHRvcmNoVHVybnNMZWZ0IC0gdHVybnMpOwogICAgaWYgKHRvcmNoVHVybnNMZWZ0ID09PSAwKSB7CiAgICAgIC8vIEF1dG8tc3dpdGNoIHRvIGxhbnRlcm4gaWYgYXZhaWxhYmxlCiAgICAgIGlmIChoYXNMYW50ZXJuICYmIGxhbnRlcm5PaWxGbGFza3NMZWZ0ID4gMCkgewogICAgICAgIGlzQ2FycnlpbmdMaWdodCA9IHRydWU7IC8vIGxhbnRlcm4gdGFrZXMgb3ZlcgogICAgICB9IGVsc2UgewogICAgICAgIGlzQ2FycnlpbmdMaWdodCA9IGZhbHNlOwogICAgICB9CiAgICB9CiAgfSBlbHNlIGlmIChoYXNMYW50ZXJuICYmIGxhbnRlcm5PaWxGbGFza3NMZWZ0ID4gMCkgewogICAgLy8gT1NFOiBsYW50ZXJuIGJ1cm5zIDEgZmxhc2sgcGVyIDI0IHR1cm5zICg0IGhvdXJzKQogICAgLy8gVHJhY2sgYnkgYWJzb2x1dGUgdHVybiBjb3VudAogICAgY29uc3QgZmxhc2tzQ29uc3VtZWQgPSBNYXRoLmZsb29yKGR1bmdlb25UdXJucyAvIDI0KTsKICAgIGNvbnN0IG5ld0ZsYXNrc0xlZnQgPSBNYXRoLm1heCgwLCBsYW50ZXJuT2lsRmxhc2tzTGVmdCAtIGZsYXNrc0NvbnN1bWVkKTsKICAgIGlmIChuZXdGbGFza3NMZWZ0IDwgbGFudGVybk9pbEZsYXNrc0xlZnQpIHsKICAgICAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSBuZXdGbGFza3NMZWZ0OwogICAgICBpZiAobGFudGVybk9pbEZsYXNrc0xlZnQgPT09IDApIGlzQ2FycnlpbmdMaWdodCA9IGZhbHNlOwogICAgfQogIH0KCiAgLy8gT1NFIHdhbmRlcmluZyBtb25zdGVyIGNoZWNrOiBldmVyeSAyIHR1cm5zLCByb2xsIDFkNgogIC8vIDEgPSB3YW5kZXJpbmcgbW9uc3RlciBlbmNvdW50ZXIKICBpZiAod2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyID49IDIpIHsKICAgIHdhbmRlcmluZ01vbnN0ZXJUdXJuQ291bnRlciA9IDA7CiAgICBjb25zdCByb2xsID0gTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpICogNikgKyAxOwogICAgaWYgKHJvbGwgPT09IDEpIHsKICAgICAgd2FuZGVyaW5nTW9uc3RlckNoZWNrRHVlID0gdHJ1ZTsKICAgICAgY29uc29sZS5sb2coJ1tXYW5kZXJpbmddIEVuY291bnRlciB0cmlnZ2VyZWQhJyk7CiAgICB9CiAgfQp9CgpmdW5jdGlvbiBoYW5kbGVEdW5nZW9uUmVzdCgpIHsKICAvLyAxLXR1cm4gcmVzdCByZXNldHMgdGhlIGZhdGlndWUgY2xvY2sKICB0dXJuc1dpdGhvdXRSZXN0ID0gMDsKICBmYXRpZ3VlUGVuYWx0eSA9IDA7CiAgYWR2YW5jZUR1bmdlb25UdXJuKDEpOyAvLyByZXN0IGl0c2VsZiB0YWtlcyAxIHR1cm4gKHdhbmRlcmluZyBtb25zdGVyIGNoZWNrIGFwcGxpZXMpCiAgaWYgKGlzSW5EdW5nZW9uKCkpIGFkZEVudHJ5UmF3KCdSZXN0IHRha2VuIC0tIDEgdHVybi4gKCcgKyB0dXJuc1dpdGhvdXRSZXN0ICsgJy82IHR1cm5zIHJlc2V0KScsICdzeXN0ZW0nLCAnX19nbV9fJyk7Cn0KCmZ1bmN0aW9uIGhhbmRsZUZ1bGxSZXN0KCkgewogIC8vIENvbnN1bWUgMSByYXRpb24gKDEgcGVyIGRheSByZXF1aXJlZCkKICBpZiAocmF0aW9uc0xlZnQgPiAwKSB7CiAgICByYXRpb25zTGVmdCA9IE1hdGgubWF4KDAsIHJhdGlvbnNMZWZ0IC0gMSk7CiAgICBkYXlzV2l0aG91dEZvb2QgPSAwOyAgICAgICAgLy8gYXRlIHRvZGF5IC0tIHJlc2V0IHN0YXJ2YXRpb24gY291bnRlcgogICAgc3RhcnZhdGlvblBlbmFsdHkgPSAwOwogIH0gZWxzZSB7CiAgICBkYXlzV2l0aG91dEZvb2QrKzsKICAgIC8vIEhvdXNlIHJ1bGU6IGFmdGVyIDMgZGF5cyB3aXRob3V0IGZvb2QsIC0xIHRvIGF0dGFja3MgYW5kIHNhdmVzIHBlciBkYXkKICAgIHN0YXJ2YXRpb25QZW5hbHR5ID0gTWF0aC5tYXgoMCwgZGF5c1dpdGhvdXRGb29kIC0gMyk7CiAgICBpZiAoc3RhcnZhdGlvblBlbmFsdHkgPiAwKSB7CiAgICAgIGFkZEVudHJ5UmF3KCdTdGFydmF0aW9uOiAtJyArIHN0YXJ2YXRpb25QZW5hbHR5ICsgJyB0byBhdHRhY2sgcm9sbHMgYW5kIHNhdmluZyB0aHJvd3MuIChEYXkgJyArIGRheXNXaXRob3V0Rm9vZCArICcgd2l0aG91dCBmb29kKScsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICB9CiAgfQogIC8vIE9TRTogcmVjb3ZlciAxIEhQIHBlciBsZXZlbCBwZXIgZnVsbCBuaWdodCdzIHJlc3QKICBjb25zdCBocEdhaW5lZCA9IHBjLmxldmVsIHx8IDE7CiAgcGMuaHAgPSBNYXRoLm1pbihwYy5tYXhocCwgcGMuaHAgKyBocEdhaW5lZCk7CiAgLy8gQ2xlYXIgZHVuZ2VvbiBmYXRpZ3VlCiAgdHVybnNXaXRob3V0UmVzdCA9IDA7CiAgZmF0aWd1ZVBlbmFsdHkgPSAwOwogIHJlc3REZWJ0ID0gMDsKICAvLyBUb3JjaGVzL2xhbnRlcm4gYnVybiBkdXJpbmcgcmVzdCAoOCBob3VycyA9IDQ4IHR1cm5zKQogIGR1bmdlb25UdXJucyArPSA0ODsKICBjb25zb2xlLmxvZygnW1Jlc3RdIEZ1bGwgcmVzdC4gSFArJyArIGhwR2FpbmVkICsgJyAtPiAnICsgcGMuaHAgKyAnLiBSYXRpb25zIGxlZnQ6JyArIHJhdGlvbnNMZWZ0ICsgJy4gU3RhcnZhdGlvbiBwZW5hbHR5OicgKyBzdGFydmF0aW9uUGVuYWx0eSk7Cn0KCmZ1bmN0aW9uIGJ1aWxkUmVzb3VyY2VCbG9jaygpIHsKICBjb25zdCB3YXJuaW5ncyA9IFtdOwogIGNvbnN0IHN0YXR1cyA9IFtdOwoKICAvLyBXYW5kZXJpbmcgbW9uc3RlcgogIGlmICh3YW5kZXJpbmdNb25zdGVyQ2hlY2tEdWUpIHsKICAgIHdhcm5pbmdzLnB1c2goJ1dBTkRFUklORyBNT05TVEVSIENIRUNLIFRSSUdHRVJFRCBbZDY9MV0gLS0gaW50cm9kdWNlIGFuIGFwcHJvcHJpYXRlIHdhbmRlcmluZyBtb25zdGVyIGVuY291bnRlciBmcm9tIHRoZSBtb2R1bGUgbmF0dXJhbGx5IGludG8gdGhlIGN1cnJlbnQgc2NlbmUuJyk7CiAgICB3YW5kZXJpbmdNb25zdGVyQ2hlY2tEdWUgPSBmYWxzZTsgLy8gY2xlYXIgYWZ0ZXIgaW5qZWN0aW5nCiAgfQoKICAvLyBMaWdodAogIGlmICghaXNDYXJyeWluZ0xpZ2h0KSB7CiAgICB3YXJuaW5ncy5wdXNoKCdEQVJLTkVTUyAtLSBwYXJ0eSBoYXMgbm8gbGlnaHQgc291cmNlLiBJbiBPU0U6IG1vbnN0ZXJzIHRoYXQgY2FuIHNlZSBpbiBkYXJrIGhhdmUgZnVsbCBhZHZhbnRhZ2U7IHBhcnR5IHN1ZmZlcnMgLTQgdG8gYXR0YWNrIHJvbGxzOyBzZWFyY2hpbmcgaXMgaW1wb3NzaWJsZTsgc3VycHJpc2Ugb24gMS00L2Q2LicpOwogIH0gZWxzZSBpZiAodG9yY2hUdXJuc0xlZnQgPiAwICYmIHRvcmNoVHVybnNMZWZ0IDw9IDIpIHsKICAgIHdhcm5pbmdzLnB1c2goJ1RPUkNIIE5FQVJMWSBPVVQgLS0gJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJuKHMpIHJlbWFpbmluZy4gTWVudGlvbiB0aGlzIGluIG5hcnJhdGlvbi4nKTsKICB9IGVsc2UgaWYgKHRvcmNoVHVybnNMZWZ0ID09PSAwICYmIHRvcmNoVHVybnNMZWZ0IDw9IDAgJiYgaGFzTGFudGVybikgewogICAgc3RhdHVzLnB1c2goJ0xpZ2h0OiBsYW50ZXJuICgnICsgbGFudGVybk9pbEZsYXNrc0xlZnQgKyAnIGZsYXNrKHMpIHJlbWFpbmluZywgficgKyAobGFudGVybk9pbEZsYXNrc0xlZnQgKiAyNCkgKyAnIHR1cm5zKScpOwogIH0gZWxzZSB7CiAgICBzdGF0dXMucHVzaCgnTGlnaHQ6IHRvcmNoICgnICsgdG9yY2hUdXJuc0xlZnQgKyAnIHR1cm5zIHJlbWFpbmluZyknKTsKICB9CgogIC8vIEh1bmdlciAtLSBob3VzZSBydWxlOiAtMSB0byBhdHRhY2sgcm9sbHMgYW5kIHNhdmVzIHBlciBkYXkgYWZ0ZXIgZGF5IDMgd2l0aG91dCBmb29kCiAgaWYgKHN0YXJ2YXRpb25QZW5hbHR5ID4gMCkgewogICAgd2FybmluZ3MucHVzaCgnU1RBUlZBVElPTiBQRU5BTFRZIEFDVElWRTogLScgKyBzdGFydmF0aW9uUGVuYWx0eSArICcgdG8gQUxMIGF0dGFjayByb2xscyBhbmQgc2F2aW5nIHRocm93cyAoZGF5ICcgKyBkYXlzV2l0aG91dEZvb2QgKyAnIHdpdGhvdXQgZm9vZCkuIEFwcGx5IHRoaXMgdG8gZXZlcnkgcm9sbC4gQ2hhcmFjdGVyIG5lZWRzIGZvb2QgdXJnZW50bHkuJyk7CiAgfSBlbHNlIGlmIChkYXlzV2l0aG91dEZvb2QgPiAwKSB7CiAgICB3YXJuaW5ncy5wdXNoKCdIVU5HUlk6IERheSAnICsgZGF5c1dpdGhvdXRGb29kICsgJyB3aXRob3V0IGZvb2QuIFBlbmFsdHkgKC0xL2RheSkgYmVnaW5zIGFmdGVyIGRheSAzLiBDaGFyYWN0ZXIgc2hvdWxkIGJlIHZpc2libHkgd2Vha2VuaW5nLicpOwogIH0gZWxzZSBpZiAocmF0aW9uc0xlZnQgPT09IDApIHsKICAgIHN0YXR1cy5wdXNoKCdObyByYXRpb25zIChub3QgeWV0IGh1bmdyeSAtLSBwZW5hbHR5IHN0YXJ0cyBhZnRlciAzIGRheXMpJyk7CiAgfSBlbHNlIGlmIChyYXRpb25zTGVmdCA9PT0gMSkgewogICAgd2FybmluZ3MucHVzaCgnTEFTVCBSQVRJT04gLS0gbWVudGlvbiB0aGlzIGluIG5hcnJhdGlvbi4nKTsKICB9IGVsc2UgewogICAgc3RhdHVzLnB1c2goJ1JhdGlvbnM6ICcgKyByYXRpb25zTGVmdCArICcgcmVtYWluaW5nJyk7CiAgfQoKICAvLyBPU0UgZHVuZ2VvbiByZXN0IHJ1bGUgLS0gb25seSBhcHBsaWVzIHVuZGVyZ3JvdW5kCiAgaWYgKGlzSW5EdW5nZW9uKCkpIHsKICAgIGlmICh0dXJuc1dpdGhvdXRSZXN0ID49IDYpIHsKICAgICAgd2FybmluZ3MucHVzaCgnRFVOR0VPTiBSRVNUIE9WRVJEVUU6ICcgKyB0dXJuc1dpdGhvdXRSZXN0ICsgJyB0dXJucyB3aXRob3V0IHJlc3QuIE9TRSBydWxlOiBwYXJ0eSBtdXN0IHJlc3QgMSB0dXJuIHBlciA2IGV4cGxvcmVkIG9yIHN1ZmZlciB3YW5kZXJpbmcgbW9uc3RlciBjaGVjayBwZW5hbHR5LiBSZW1pbmQgcGFydHkgdG8gcmVzdC4nKTsKICAgIH0gZWxzZSBpZiAodHVybnNXaXRob3V0UmVzdCA+PSA0KSB7CiAgICAgIHN0YXR1cy5wdXNoKCdEdW5nZW9uIHJlc3Q6ICcgKyB0dXJuc1dpdGhvdXRSZXN0ICsgJy82IHR1cm5zIChyZXN0IDEgdHVybiBzb29uIHRvIGF2b2lkIHdhbmRlcmluZyBtb25zdGVyIHBlbmFsdHkpJyk7CiAgICB9CiAgfQoKICAvLyBUdXJuIGNvdW50CiAgY29uc3QgaG91cnMgPSBNYXRoLmZsb29yKGR1bmdlb25UdXJucyAvIDYpOwogIGNvbnN0IG1pbnMgPSAoZHVuZ2VvblR1cm5zICUgNikgKiAxMDsKICBzdGF0dXMucHVzaCgnVHVybiAnICsgZHVuZ2VvblR1cm5zICsgJyAoJyArIGhvdXJzICsgJ2ggJyArIG1pbnMgKyAnbSBpbiBkdW5nZW9uKScpOwoKICBjb25zdCBsaW5lcyA9IFtdOwogIGlmICh3YXJuaW5ncy5sZW5ndGgpIHsKICAgIGxpbmVzLnB1c2goJ1JFU09VUkNFIFdBUk5JTkdTIChpbmNvcnBvcmF0ZSBuYXR1cmFsbHkgaW50byBuYXJyYXRpb24pOicpOwogICAgd2FybmluZ3MuZm9yRWFjaCh3ID0+IGxpbmVzLnB1c2goJyAgJyArIHcpKTsKICB9CiAgaWYgKHN0YXR1cy5sZW5ndGgpIGxpbmVzLnB1c2goJ1Jlc291cmNlczogJyArIHN0YXR1cy5qb2luKCcgfCAnKSk7CiAgcmV0dXJuIGxpbmVzLmxlbmd0aCA/IGxpbmVzLmpvaW4oJ1suXW4nKSA6ICcnOwp9Cgphc3luYyBmdW5jdGlvbiBnZW5lcmF0ZUdNQnJpZWZpbmcoKSB7CiAgaWYgKCF1c2VPbGxhbWEpIHJldHVybjsgLy8gQ2xhdWRlIGhhbmRsZXMgdGhpcyBuYXRpdmVseQoKICAvLyBJZiB3ZSBoYXZlIGEgLmRuZG1vZCBmaWxlIGxvYWRlZCwgYnVpbGQgdGhlIGJyaWVmaW5nIGRpcmVjdGx5IGZyb20gaXRzCiAgLy8gc3RydWN0dXJlZCBkYXRhIC0tIG5vIEFJIGNhbGwgbmVlZGVkLCBpbnN0YW50IGFuZCAxMDAlIGFjY3VyYXRlLgogIGlmIChsb2FkZWRNb2R1bGVEYXRhICYmIGxvYWRlZE1vZHVsZURhdGEubnBjcyAmJiBsb2FkZWRNb2R1bGVEYXRhLm5wY3MubGVuZ3RoKSB7CiAgICBjb25zb2xlLmxvZygnW0JyaWVmaW5nXSBCdWlsZGluZyBmcm9tIC5kbmRtb2Qgc3RydWN0dXJlZCBkYXRhIC0tIHNraXBwaW5nIEFJIGNhbGwnKTsKICAgIGJ1aWxkQnJpZWZpbmdGcm9tRG5kbW9kKGxvYWRlZE1vZHVsZURhdGEpOwogICAgcmV0dXJuOwogIH0KCiAgaWYgKCFtb2R1bGVUZXh0IHx8IG1vZHVsZVRleHQubGVuZ3RoIDwgMTAwKSByZXR1cm47CgogIGFkZEVudHJ5UmF3KCdQcmVwYXJpbmcgR00gYnJpZWZpbmcgLS0gdGhpcyB0YWtlcyBhYm91dCAzMCBzZWNvbmRzLi4uJywgJ3N5c3RlbScsICdfX2dtX18nKTsKCiAgY29uc3QgYnJpZWZpbmdQcm9tcHQgPSBgWW91IGFyZSBwcmVwYXJpbmcgdG8gcnVuIGEgdGFibGV0b3AgUlBHIG1vZHVsZSBhcyBHYW1lIE1hc3Rlci4gUmVhZCB0aGUgbW9kdWxlIGJlbG93IGFuZCBwcm9kdWNlIGEgc3RydWN0dXJlZCBHTSBicmllZmluZyBpbiBKU09OIGZvcm1hdCBPTkxZLiBObyBtYXJrZG93biwgbm8gcHJlYW1ibGUgLS0gcHVyZSBKU09OLgoKTU9EVUxFOgoke21vZHVsZVRleHQuc3Vic3RyaW5nKDAsIDE2MDAwKX0KClByb2R1Y2UgdGhpcyBleGFjdCBKU09OIHN0cnVjdHVyZToKewogICJrZXlfZmFjdHMiOiBbCiAgICAiVGhlIG1vc3QgaW1wb3J0YW50IGZhY3QgdGhlIEdNIG11c3QgbmV2ZXIgZm9yZ2V0IiwKICAgICJTZWNvbmQgbW9zdCBpbXBvcnRhbnQgZmFjdCIsCiAgICAiVGhpcmQiLAogICAgIkZvdXJ0aCIsCiAgICAiRmlmdGgiLAogICAgIlNpeHRoIiwKICAgICJTZXZlbnRoIiwKICAgICJFaWdodGgiLAogICAgIk5pbnRoIiwKICAgICJUZW50aCIKICBdLAogICJjb3JlX3RlbnNpb24iOiAiT25lIHNlbnRlbmNlOiB0aGUgY2VudHJhbCBkcmFtYXRpYyBjb25mbGljdCBvZiB0aGlzIGFkdmVudHVyZSIsCiAgInZpY3RvcnlfY29uZGl0aW9uIjogIk9uZSBzZW50ZW5jZTogaG93IHRoZSBhZHZlbnR1cmUgY2FuIGJlIHdvbiIsCiAgIm1haW5fdmlsbGFpbl9vcl90aHJlYXQiOiAiTmFtZSBhbmQgb25lLXNlbnRlbmNlIGRlc2NyaXB0aW9uIG9mIHRoZSBwcmltYXJ5IGFudGFnb25pc3Qgb3IgdGhyZWF0IiwKICAibnBjcyI6IFsKICAgIHsKICAgICAgIm5hbWUiOiAiTlBDIG5hbWUgZXhhY3RseSBhcyBpbiBtb2R1bGUiLAogICAgICAicm9sZSI6ICJUaGVpciByb2xlIGluIG9uZSBwaHJhc2UiLAogICAgICAicGVyc29uYWxpdHkiOiAiMi0zIHdvcmRzIGRlc2NyaWJpbmcgaG93IHRoZXkgc3BlYWsgYW5kIGFjdCIsCiAgICAgICJrbm93cyI6IFsKICAgICAgICAiU3BlY2lmaWMgZmFjdCB0aGlzIE5QQyBnZW51aW5lbHkga25vd3MgYW5kIGNhbiBzaGFyZSBmcmVlbHkiLAogICAgICAgICJBbm90aGVyIGZhY3QgdGhleSBjYW4gc2hhcmUiLAogICAgICAgICJBIHRoaXJkIGlmIHJlbGV2YW50IgogICAgICBdLAogICAgICAid2lsbF9zaGFyZV9pZiI6ICJDb25kaXRpb24gdW5kZXIgd2hpY2ggdGhleSBzaGFyZSBzZW5zaXRpdmUgaW5mb3JtYXRpb24gKGUuZy4gJ2lmIHBhcnR5IGVhcm5zIHRydXN0JywgJ25ldmVyJywgJ2lmIGJyaWJlZCcsICdpZiBmcmlnaHRlbmVkJykiLAogICAgICAid29udF9zaGFyZSI6IFsKICAgICAgICAiU29tZXRoaW5nIHRoZXkga25vdyBidXQgYWN0aXZlbHkgaGlkZSIsCiAgICAgICAgIkFub3RoZXIgc2VjcmV0IHRoZXkgcHJvdGVjdCIKICAgICAgXSwKICAgICAgImNhbm5vdF9rbm93IjogWwogICAgICAgICJJbmZvcm1hdGlvbiB0aGlzIE5QQyBoYXMgTk8gV0FZIG9mIGtub3dpbmcgLS0gbXVzdCByZWZ1c2Ugd2l0aCAnSSBkb24ndCBrbm93JyIsCiAgICAgICAgIkFub3RoZXIgdGhpbmcgb3V0c2lkZSB0aGVpciBrbm93bGVkZ2UiCiAgICAgIF0sCiAgICAgICJkZWZsZWN0aW9uX3BocmFzZSI6ICJFeGFjdCB3b3JkcyB0aGlzIE5QQyB1c2VzIHdoZW4gYXNrZWQgc29tZXRoaW5nIHRoZXkgd29uJ3Qgb3IgY2FuJ3QgYW5zd2VyLiBNYWtlIGl0IGluLWNoYXJhY3Rlci4iLAogICAgICAia25vd2xlZGdlX2xpbWl0IjogIk9uZSBzZW50ZW5jZSBkZXNjcmliaW5nIHRoZSBhYnNvbHV0ZSBib3VuZGFyeSBvZiB0aGVpciBrbm93bGVkZ2UiCiAgICB9CiAgXSwKICAic2VjcmV0X2luZm9ybWF0aW9uIjogWwogICAgIlBsb3Qgc2VjcmV0IHRoZSBwbGF5ZXJzIHNob3VsZCBOT1Qga25vdyB5ZXQiLAogICAgIkFub3RoZXIgc2VjcmV0IHRvIGJlIHJldmVhbGVkIGxhdGVyIgogIF0sCiAgImluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzIjogWwogICAgIlNvbWV0aGluZyB0aGF0IGlzIHRydWUgaW4gdGhlIG1vZHVsZSBidXQgTk8gTlBDIGtub3dzIC0tIHBsYXllcnMgY2FuIG9ubHkgZmluZCBpdCBieSBleHBsb3JhdGlvbiIsCiAgICAiQW5vdGhlciBzdWNoIGZhY3QiCiAgXQp9CgpCZSBzcGVjaWZpYy4gVXNlIGV4YWN0IG5hbWVzIGZyb20gdGhlIG1vZHVsZS4gRXZlcnkgTlBDIGluIHRoZSBtb2R1bGUgc2hvdWxkIGFwcGVhci4gVGhlIGNhbm5vdF9rbm93IGxpc3QgaXMgY3JpdGljYWwgLS0gaW5jbHVkZSBhdCBsZWFzdCAyIGl0ZW1zIHBlciBOUEMuYDsKCiAgdHJ5IHsKICAgIGNvbnN0IHJlc3AgPSBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvYWknLCB7CiAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgICBhcGlfa2V5OiBhcGlLZXksCiAgICAgICAgc3lzdGVtOiAnWW91IGFyZSBhIHByZWNpc2UgSlNPTiBnZW5lcmF0b3IuIE91dHB1dCBvbmx5IHZhbGlkIEpTT04uIE5vIG1hcmtkb3duIGZlbmNlcy4gTm8gZXhwbGFuYXRpb24uJywKICAgICAgICBtZXNzYWdlczogW3tyb2xlOiAndXNlcicsIGNvbnRlbnQ6IGJyaWVmaW5nUHJvbXB0fV0KICAgICAgfSkKICAgIH0pOwoKICAgIGlmICghcmVzcC5vaykgewogICAgICBjb25zb2xlLndhcm4oJ1tCcmllZmluZ10gQVBJIGVycm9yOicsIHJlc3Auc3RhdHVzKTsKICAgICAgcmV0dXJuOwogICAgfQoKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKICAgIGlmIChkYXRhLmVycm9yIHx8ICFkYXRhLmNvbnRlbnQpIHsKICAgICAgY29uc29sZS53YXJuKCdbQnJpZWZpbmddIE5vIGNvbnRlbnQ6JywgZGF0YS5lcnJvcik7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICAvLyBQYXJzZSBKU09OIC0tIHN0cmlwIGFueSBtYXJrZG93biBmZW5jZXMgQ2xhdWRlIG1pZ2h0IGFkZAogICAgbGV0IHJhdyA9IGRhdGEuY29udGVudC50cmltKCk7CiAgICAvLyBSZW1vdmUgb3BlbmluZyBmZW5jZSBsaW5lIChlLmcuIGBgYGpzb24pCiAgICBpZiAocmF3LnN0YXJ0c1dpdGgoJ2AnKSkgewogICAgICBjb25zdCBmaXJzdE5ld2xpbmUgPSByYXcuaW5kZXhPZignWy5dbicpOwogICAgICBpZiAoZmlyc3ROZXdsaW5lID4gMCkgcmF3ID0gcmF3LnN1YnN0cmluZyhmaXJzdE5ld2xpbmUgKyAxKTsKICAgIH0KICAgIC8vIFJlbW92ZSBjbG9zaW5nIGZlbmNlCiAgICBpZiAocmF3LnRyaW1FbmQoKS5lbmRzV2l0aCgnYCcpKSB7CiAgICAgIGNvbnN0IGxhc3RGZW5jZSA9IHJhdy5sYXN0SW5kZXhPZignWy5dbmBgYCcpOwogICAgICBpZiAobGFzdEZlbmNlID4gMCkgcmF3ID0gcmF3LnN1YnN0cmluZygwLCBsYXN0RmVuY2UpOwogICAgfQogICAgY29uc3Qgc3RhcnQgPSByYXcuaW5kZXhPZigneycpOwogICAgY29uc3QgZW5kID0gcmF3Lmxhc3RJbmRleE9mKCd9JykgKyAxOwogICAgaWYgKHN0YXJ0IDwgMCB8fCBlbmQgPD0gc3RhcnQpIHsKICAgICAgY29uc29sZS53YXJuKCdbQnJpZWZpbmddIENvdWxkIG5vdCBmaW5kIEpTT04gaW4gcmVzcG9uc2UnKTsKICAgICAgcmV0dXJuOwogICAgfQoKICAgIGNvbnN0IGJyaWVmaW5nID0gSlNPTi5wYXJzZShyYXcuc3Vic3RyaW5nKHN0YXJ0LCBlbmQpKTsKCiAgICAvLyBTdG9yZSBrZXkgZmFjdHMgYXMgcGlubmVkIGZhY3RzCiAgICBpZiAoYnJpZWZpbmcua2V5X2ZhY3RzKSB7CiAgICAgIGJyaWVmaW5nLmtleV9mYWN0cy5mb3JFYWNoKGYgPT4gewogICAgICAgIGlmICghcGlubmVkRmFjdHMuaW5jbHVkZXMoZikpIHBpbm5lZEZhY3RzLnB1c2goZik7CiAgICAgIH0pOwogICAgfQoKICAgIC8vIEJ1aWxkIE5QQyBrbm93bGVkZ2UgbWFwIGZvciBpbmplY3Rpb24KICAgIG5wY0tub3dsZWRnZU1hcCA9IHt9OwogICAgaWYgKGJyaWVmaW5nLm5wY3MpIHsKICAgICAgYnJpZWZpbmcubnBjcy5mb3JFYWNoKG5wYyA9PiB7CiAgICAgICAgbnBjS25vd2xlZGdlTWFwW25wYy5uYW1lXSA9IHsKICAgICAgICAgIHJvbGU6IG5wYy5yb2xlIHx8ICcnLAogICAgICAgICAgcGVyc29uYWxpdHk6IG5wYy5wZXJzb25hbGl0eSB8fCAnJywKICAgICAgICAgIGtub3dzOiBucGMua25vd3MgfHwgW10sCiAgICAgICAgICB3aWxsX3NoYXJlX2lmOiBucGMud2lsbF9zaGFyZV9pZiB8fCAnZnJlZWx5JywKICAgICAgICAgIHdvbnRfc2hhcmU6IG5wYy53b250X3NoYXJlIHx8IFtdLAogICAgICAgICAgY2Fubm90X2tub3c6IG5wYy5jYW5ub3Rfa25vdyB8fCBbXSwKICAgICAgICAgIGRlZmxlY3Rpb246IG5wYy5kZWZsZWN0aW9uX3BocmFzZSB8fCAiSSdtIHNvcnJ5LCBJIGRvbid0IGtub3cgYW55dGhpbmcgbW9yZSBhYm91dCB0aGF0LiIsCiAgICAgICAgICBsaW1pdDogbnBjLmtub3dsZWRnZV9saW1pdCB8fCAnJwogICAgICAgIH07CiAgICAgIH0pOwogICAgfQoKICAgIC8vIEJ1aWxkIHRoZSBHTSBicmllZmluZyB0ZXh0CiAgICBjb25zdCBsaW5lcyA9IFtdOwogICAgbGluZXMucHVzaCgnIEdNIEJSSUVGSU5HIChwcmUtYW5hbHlzZWQgbW9kdWxlIGNoZWF0IHNoZWV0KSAnKTsKICAgIGxpbmVzLnB1c2goJ0NvcmUgdGVuc2lvbjogJyArIChicmllZmluZy5jb3JlX3RlbnNpb24gfHwgJycpKTsKICAgIGxpbmVzLnB1c2goJ1ZpY3Rvcnk6ICcgKyAoYnJpZWZpbmcudmljdG9yeV9jb25kaXRpb24gfHwgJycpKTsKICAgIGxpbmVzLnB1c2goJ1ByaW1hcnkgdGhyZWF0OiAnICsgKGJyaWVmaW5nLm1haW5fdmlsbGFpbl9vcl90aHJlYXQgfHwgJycpKTsKICAgIGxpbmVzLnB1c2goJycpOwogICAgbGluZXMucHVzaCgnS0VZIEZBQ1RTIChuZXZlciBmb3JnZXQgb3IgY29udHJhZGljdCB0aGVzZSk6Jyk7CiAgICAoYnJpZWZpbmcua2V5X2ZhY3RzIHx8IFtdKS5mb3JFYWNoKChmLGkpID0+IGxpbmVzLnB1c2goKGkrMSkgKyAnLiAnICsgZikpOwoKICAgIGlmIChicmllZmluZy5zZWNyZXRfaW5mb3JtYXRpb24gJiYgYnJpZWZpbmcuc2VjcmV0X2luZm9ybWF0aW9uLmxlbmd0aCkgewogICAgICBsaW5lcy5wdXNoKCcnKTsKICAgICAgbGluZXMucHVzaCgnU0VDUkVUUyAocGxheWVycyBtdXN0IE5PVCBrbm93IHRoZXNlIHlldCAtLSBuZXZlciByZXZlYWwgdGhyb3VnaCBOUENzKTonKTsKICAgICAgYnJpZWZpbmcuc2VjcmV0X2luZm9ybWF0aW9uLmZvckVhY2gocyA9PiBsaW5lcy5wdXNoKCcgIFNFQ1JFVDogJyArIHMpKTsKICAgIH0KCiAgICBpZiAoYnJpZWZpbmcuaW5mb3JtYXRpb25fdGhhdF9ub19ucGNfa25vd3MgJiYgYnJpZWZpbmcuaW5mb3JtYXRpb25fdGhhdF9ub19ucGNfa25vd3MubGVuZ3RoKSB7CiAgICAgIGxpbmVzLnB1c2goJycpOwogICAgICBsaW5lcy5wdXNoKCdESVNDT1ZFUkFCTEUgT05MWSBCWSBFWFBMT1JBVElPTiAobm8gTlBDIGNhbiB0ZWxsIHRoZW0gdGhpcyk6Jyk7CiAgICAgIGJyaWVmaW5nLmluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzLmZvckVhY2gocyA9PiBsaW5lcy5wdXNoKCcgIEVYUExPUkUgT05MWTogJyArIHMpKTsKICAgIH0KCiAgICBsaW5lcy5wdXNoKCcnKTsKICAgIGxpbmVzLnB1c2goJyBOUEMgS05PV0xFREdFIE1BUCAoaGFyZCBsaW1pdHMgLS0gZW5mb3JjZSBzdHJpY3RseSkgJyk7CiAgICBsaW5lcy5wdXNoKCdDUklUSUNBTCBSVUxFOiBXaGVuIGFuIE5QQyByZWFjaGVzIHRoZSBsaW1pdCBvZiB0aGVpciBrbm93bGVkZ2UsIHRoZXkgc2F5IHNvJyk7CiAgICBsaW5lcy5wdXNoKCdpbiBjaGFyYWN0ZXIuIFRoZXkgZG8gTk9UIGludmVudCBpbmZvcm1hdGlvbi4gVGhleSBkbyBOT1QgcmV2ZWFsIHNlY3JldHMuJyk7CiAgICBsaW5lcy5wdXNoKCdVc2UgdGhlaXIgZGVmbGVjdGlvbiBwaHJhc2UgZXhhY3RseSBvciBhIG5hdHVyYWwgdmFyaWFudCBvZiBpdC4nKTsKICAgIGxpbmVzLnB1c2goJycpOwogICAgT2JqZWN0LmVudHJpZXMobnBjS25vd2xlZGdlTWFwKS5mb3JFYWNoKChbbmFtZSwgZGF0YV0pID0+IHsKICAgICAgbGluZXMucHVzaCgnWycgKyBuYW1lICsgJ10gLS0gJyArIGRhdGEucm9sZSArICcgLS0gJyArIGRhdGEucGVyc29uYWxpdHkpOwogICAgICBpZiAoZGF0YS5rbm93cy5sZW5ndGgpIGxpbmVzLnB1c2goJyAgQ0FOIFNIQVJFOiAnICsgZGF0YS5rbm93cy5qb2luKCcgfCAnKSk7CiAgICAgIGxpbmVzLnB1c2goJyAgV0lMTCBTSEFSRTogJyArIGRhdGEud2lsbF9zaGFyZV9pZik7CiAgICAgIGlmIChkYXRhLndvbnRfc2hhcmUubGVuZ3RoKSBsaW5lcy5wdXNoKCcgIEFDVElWRUxZIEhJREVTOiAnICsgZGF0YS53b250X3NoYXJlLmpvaW4oJyB8ICcpKTsKICAgICAgaWYgKGRhdGEuY2Fubm90X2tub3cubGVuZ3RoKSBsaW5lcy5wdXNoKCcgIENBTk5PVCBLTk9XIChzYXkgdGhleSBkbyBub3Qga25vdyk6ICcgKyBkYXRhLmNhbm5vdF9rbm93LmpvaW4oJyB8ICcpKTsKICAgICAgbGluZXMucHVzaCgnICBERUZMRUNUSU9OOiAnICsgZGF0YS5kZWZsZWN0aW9uKTsKICAgICAgbGluZXMucHVzaCgnJyk7CiAgICB9KTsKCiAgICBnbUJyaWVmaW5nID0gbGluZXMuam9pbignWy5dbicpOwoKICAgIC8vIFJlYnVpbGQgc3lzdGVtIHByb21wdCB3aXRoIGJyaWVmaW5nIGJha2VkIGluCiAgICBzeXN0ZW1Qcm9tcHQgPSBidWlsZFN5c3RlbVByb21wdCgpOwoKICAgIGNvbnNvbGUubG9nKCdbQnJpZWZpbmddIENvbXBsZXRlLiBOUENzIG1hcHBlZDonLCBPYmplY3Qua2V5cyhucGNLbm93bGVkZ2VNYXApLmxlbmd0aCk7CiAgICBhZGRFbnRyeVJhdygnR00gYnJpZWZpbmcgY29tcGxldGUuICcgKyBPYmplY3Qua2V5cyhucGNLbm93bGVkZ2VNYXApLmxlbmd0aCArICcgTlBDcyBtYXBwZWQgd2l0aCBrbm93bGVkZ2UgYm91bmRhcmllcy4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwoKICB9IGNhdGNoKGUpIHsKICAgIGNvbnNvbGUud2FybignW0JyaWVmaW5nXSBGYWlsZWQ6JywgZS5tZXNzYWdlKTsKICAgIC8vIE5vbi1mYXRhbCAtLSBnYW1lIGNvbnRpbnVlcyB3aXRob3V0IGJyaWVmaW5nCiAgICBhZGRFbnRyeVJhdygnISBHTSBicmllZmluZyBza2lwcGVkICh3aWxsIHVzZSBtb2R1bGUgdGV4dCBkaXJlY3RseSkuJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICB9Cn0KCmZ1bmN0aW9uIGJ1aWxkQ29tcGFjdE1vZHVsZVJlZigpIHsKICBjb25zdCBtb2QgPSBsb2FkZWRNb2R1bGVEYXRhOwogIGlmICghbW9kIHx8ICFtb2QudGl0bGUpIHJldHVybiBtb2R1bGVUZXh0OwoKICBjb25zdCBsaW5lcyA9IFtdOwogIGxpbmVzLnB1c2goJ01PRFVMRTogJyArIG1vZC50aXRsZSk7CiAgbGluZXMucHVzaCgnU2V0dGluZzogJyArIChtb2Quc2V0dGluZyB8fCAnJykpOwogIGxpbmVzLnB1c2goJ0xldmVsczogJyArIChtb2QubGV2ZWxfcmFuZ2UgfHwgJycpKTsKICBsaW5lcy5wdXNoKCcnKTsKCiAgLy8gQ29yZSB0ZW5zaW9uIGFuZCB2aWN0b3J5CiAgbGluZXMucHVzaCgnQ09SRSBURU5TSU9OOiAnICsgKG1vZC5jb3JlX3RlbnNpb24gfHwgJycpKTsKICBsaW5lcy5wdXNoKCdWSUNUT1JZOiAnICsgKG1vZC52aWN0b3J5X2NvbmRpdGlvbnMgfHwgJycpKTsKICBsaW5lcy5wdXNoKCdNQUlOIFRIUkVBVDogJyArIChtb2QubWFpbl90aHJlYXQgfHwgJycpKTsKICBsaW5lcy5wdXNoKCcnKTsKCiAgLy8gQ3VycmVudCBsb2NhdGlvbiAtLSBmdWxsIGRlc2NyaXB0aW9uCiAgY29uc3QgY3VycmVudExvYyA9IChtb2QubG9jYXRpb25zIHx8IFtdKS5maW5kKGwgPT4gbC5pZCA9PT0gKHBjLmxvY3RhZyB8fCAnJykpOwogIGlmIChjdXJyZW50TG9jKSB7CiAgICBsaW5lcy5wdXNoKCdDVVJSRU5UIExPQ0FUSU9OOiAnICsgY3VycmVudExvYy5uYW1lKTsKICAgIGxpbmVzLnB1c2goY3VycmVudExvYy5nbV9kZXNjcmlwdGlvbiB8fCAnJyk7CiAgICBpZiAoY3VycmVudExvYy5tb25zdGVycyAmJiBjdXJyZW50TG9jLm1vbnN0ZXJzLmxlbmd0aCkgewogICAgICBsaW5lcy5wdXNoKCdNT05TVEVSUyBIRVJFOiAnICsgY3VycmVudExvYy5tb25zdGVycy5tYXAobSA9PiBtLm5hbWUgKyAnIHgnICsgbS5jb3VudCArICcgKEhQOicgKyBtLmhwX2VhY2ggKyAnIEFDOicgKyBtLmFjICsgJyknKS5qb2luKCcsICcpKTsKICAgIH0KICAgIGlmIChjdXJyZW50TG9jLm5wY3NfcHJlc2VudCAmJiBjdXJyZW50TG9jLm5wY3NfcHJlc2VudC5sZW5ndGgpIHsKICAgICAgbGluZXMucHVzaCgnTlBDUyBIRVJFOiAnICsgY3VycmVudExvYy5ucGNzX3ByZXNlbnQuam9pbignLCAnKSk7CiAgICB9CiAgICBpZiAoY3VycmVudExvYy5oaWRkZW5fZmVhdHVyZXMgJiYgY3VycmVudExvYy5oaWRkZW5fZmVhdHVyZXMubGVuZ3RoKSB7CiAgICAgIGxpbmVzLnB1c2goJ0hJRERFTiAoR00gb25seSk6ICcgKyBjdXJyZW50TG9jLmhpZGRlbl9mZWF0dXJlcy5qb2luKCcgfCAnKSk7CiAgICB9CiAgICBpZiAoY3VycmVudExvYy5leGl0cykgewogICAgICBsaW5lcy5wdXNoKCdFWElUUzogJyArIE9iamVjdC5lbnRyaWVzKGN1cnJlbnRMb2MuZXhpdHMpLm1hcCgoW2QsdF0pID0+IGQgKyAnIC0+ICcgKyB0KS5qb2luKCcsICcpKTsKICAgIH0KICAgIGxpbmVzLnB1c2goJycpOwogIH0KCiAgLy8gQWRqYWNlbnQgbG9jYXRpb25zIChleGl0cyBmcm9tIGN1cnJlbnQpCiAgaWYgKGN1cnJlbnRMb2MgJiYgY3VycmVudExvYy5leGl0cykgewogICAgT2JqZWN0LmVudHJpZXMoY3VycmVudExvYy5leGl0cykuZm9yRWFjaCgoW2RpciwgdGFyZ2V0SWRdKSA9PiB7CiAgICAgIGNvbnN0IGFkaiA9IChtb2QubG9jYXRpb25zIHx8IFtdKS5maW5kKGwgPT4gbC5pZCA9PT0gdGFyZ2V0SWQpOwogICAgICBpZiAoYWRqKSB7CiAgICAgICAgbGluZXMucHVzaCgnVE8gVEhFICcgKyBkaXIudG9VcHBlckNhc2UoKSArICcgKCcgKyBhZGoubmFtZSArICcpOiAnICsgKGFkai5yZWFkX2Fsb3VkIHx8IGFkai5nbV9kZXNjcmlwdGlvbiB8fCAnJykuc3Vic3RyaW5nKDAsIDEyMCkgKyAnLi4uJyk7CiAgICAgIH0KICAgIH0pOwogICAgbGluZXMucHVzaCgnJyk7CiAgfQoKICAvLyBDb21wYWN0IE5QQyBsaXN0IChuYW1lICsgcm9sZSArIDEtbGluZSBwZXJzb25hbGl0eSBvbmx5KQogIGlmIChtb2QubnBjcyAmJiBtb2QubnBjcy5sZW5ndGgpIHsKICAgIGxpbmVzLnB1c2goJ0tFWSBOUENzIElOIFRISVMgTU9EVUxFOicpOwogICAgbW9kLm5wY3MuZm9yRWFjaChuID0+IHsKICAgICAgbGluZXMucHVzaCgnICAnICsgbi5uYW1lICsgJyBbJyArIChuLnJvbGUgfHwgJycpICsgJ10gLS0gJyArIChuLnBlcnNvbmFsaXR5IHx8ICcnKS5zdWJzdHJpbmcoMCwgODApKTsKICAgIH0pOwogICAgbGluZXMucHVzaCgnJyk7CiAgfQoKICAvLyBHTSBicmllZmluZyBpcyBpbmplY3RlZCBzZXBhcmF0ZWx5IC0tIGRvbid0IHJlcGVhdCBrZXkgZmFjdHMgaGVyZQogIGxpbmVzLnB1c2goJyhGdWxsIE5QQyBrbm93bGVkZ2UgbWFwIGFuZCBrZXkgZmFjdHMgYXJlIGluIHRoZSBHTSBCUklFRklORyBzZWN0aW9uIGFib3ZlLiknKTsKCiAgcmV0dXJuIGxpbmVzLmpvaW4oJ1suXW4nKTsKfQoKZnVuY3Rpb24gYnVpbGRCcmllZmluZ0Zyb21EbmRtb2QobW9kKSB7CiAgLy8gQnVpbGQgTlBDIGtub3dsZWRnZSBtYXAgZGlyZWN0bHkgZnJvbSAuZG5kbW9kIHN0cnVjdHVyZWQgZGF0YQogIG5wY0tub3dsZWRnZU1hcCA9IHt9OwogIChtb2QubnBjcyB8fCBbXSkuZm9yRWFjaChucGMgPT4gewogICAgbnBjS25vd2xlZGdlTWFwW25wYy5uYW1lXSA9IHsKICAgICAgcm9sZTogbnBjLnJvbGUgfHwgJycsCiAgICAgIHBlcnNvbmFsaXR5OiBucGMucGVyc29uYWxpdHkgfHwgJycsCiAgICAgIGtub3dzOiBucGMua25vd3NfYW5kX2Nhbl9zaGFyZSB8fCBucGMua25vd3MgfHwgW10sCiAgICAgIHdpbGxfc2hhcmVfaWY6IG5wYy53aWxsX3NoYXJlX2lmIHx8ICdmcmVlbHknLAogICAgICB3b250X3NoYXJlOiBucGMuYWN0aXZlbHlfaGlkZXMgfHwgbnBjLndvbnRfc2hhcmUgfHwgW10sCiAgICAgIGNhbm5vdF9rbm93OiBucGMuY2Fubm90X2tub3cgfHwgW10sCiAgICAgIGRlZmxlY3Rpb246IG5wYy5kZWZsZWN0aW9uX3BocmFzZSB8fCAiSSdtIHNvcnJ5LCBJIGRvbid0IGtub3cgYW55dGhpbmcgbW9yZSBhYm91dCB0aGF0LiIsCiAgICAgIGxpbWl0OiBucGMua25vd2xlZGdlX2xpbWl0IHx8ICcnCiAgICB9OwogIH0pOwoKICAvLyBQaW4ga2V5IGZhY3RzCiAgKG1vZC5rZXlfZmFjdHMgfHwgW10pLmZvckVhY2goZiA9PiB7CiAgICBpZiAoIXBpbm5lZEZhY3RzLmluY2x1ZGVzKGYpKSBwaW5uZWRGYWN0cy5wdXNoKGYpOwogIH0pOwoKICAvLyBCdWlsZCB0aGUgR00gYnJpZWZpbmcgdGV4dAogIGNvbnN0IGxpbmVzID0gW107CiAgbGluZXMucHVzaCgnIEdNIEJSSUVGSU5HIChmcm9tIC5kbmRtb2Qgc3RydWN0dXJlZCBkYXRhKSAnKTsKICBsaW5lcy5wdXNoKCdDb3JlIHRlbnNpb246ICcgKyAobW9kLmNvcmVfdGVuc2lvbiB8fCAnJykpOwogIGxpbmVzLnB1c2goJ1ZpY3Rvcnk6ICcgKyAobW9kLnZpY3RvcnlfY29uZGl0aW9ucyB8fCAnJykpOwogIGxpbmVzLnB1c2goJ1ByaW1hcnkgdGhyZWF0OiAnICsgKG1vZC5tYWluX3RocmVhdCB8fCAnJykpOwogIGxpbmVzLnB1c2goJycpOwogIGxpbmVzLnB1c2goJ0tFWSBGQUNUUyAobmV2ZXIgZm9yZ2V0IG9yIGNvbnRyYWRpY3QgdGhlc2UpOicpOwogIChtb2Qua2V5X2ZhY3RzIHx8IFtdKS5mb3JFYWNoKChmLGkpID0+IGxpbmVzLnB1c2goKGkrMSkgKyAnLiAnICsgZikpOwoKICBpZiAobW9kLnNlY3JldF9pbmZvcm1hdGlvbiAmJiBtb2Quc2VjcmV0X2luZm9ybWF0aW9uLmxlbmd0aCkgewogICAgbGluZXMucHVzaCgnJyk7CiAgICBsaW5lcy5wdXNoKCdTRUNSRVRTIChwbGF5ZXJzIG11c3QgTk9UIGtub3cgdGhlc2UgeWV0IC0tIG5ldmVyIHJldmVhbCB0aHJvdWdoIE5QQ3MpOicpOwogICAgbW9kLnNlY3JldF9pbmZvcm1hdGlvbi5mb3JFYWNoKHMgPT4gbGluZXMucHVzaCgnICBTRUNSRVQ6ICcgKyBzKSk7CiAgfQoKICBpZiAobW9kLmluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzICYmIG1vZC5pbmZvcm1hdGlvbl90aGF0X25vX25wY19rbm93cy5sZW5ndGgpIHsKICAgIGxpbmVzLnB1c2goJycpOwogICAgbGluZXMucHVzaCgnRElTQ09WRVJBQkxFIE9OTFkgQlkgRVhQTE9SQVRJT04gKG5vIE5QQyBjYW4gdGVsbCB0aGVtIHRoaXMpOicpOwogICAgbW9kLmluZm9ybWF0aW9uX3RoYXRfbm9fbnBjX2tub3dzLmZvckVhY2gocyA9PiBsaW5lcy5wdXNoKCcgIEVYUExPUkUgT05MWTogJyArIHMpKTsKICB9CgogIGxpbmVzLnB1c2goJycpOwogIGxpbmVzLnB1c2goJyBOUEMgS05PV0xFREdFIE1BUCAoaGFyZCBsaW1pdHMgLS0gZW5mb3JjZSBzdHJpY3RseSkgJyk7CiAgbGluZXMucHVzaCgnQ1JJVElDQUwgUlVMRTogV2hlbiBhbiBOUEMgcmVhY2hlcyB0aGUgbGltaXQgb2YgdGhlaXIga25vd2xlZGdlLCB0aGV5IHNheSBzbycpOwogIGxpbmVzLnB1c2goJ2luIGNoYXJhY3Rlci4gVGhleSBkbyBOT1QgaW52ZW50IGluZm9ybWF0aW9uLiBUaGV5IGRvIE5PVCByZXZlYWwgc2VjcmV0cy4nKTsKICBsaW5lcy5wdXNoKCdVc2UgdGhlaXIgZGVmbGVjdGlvbiBwaHJhc2UgZXhhY3RseSBvciBhIG5hdHVyYWwgdmFyaWFudCBvZiBpdC4nKTsKICBsaW5lcy5wdXNoKCcnKTsKICBPYmplY3QuZW50cmllcyhucGNLbm93bGVkZ2VNYXApLmZvckVhY2goKFtuYW1lLCBkYXRhXSkgPT4gewogICAgbGluZXMucHVzaCgnWycgKyBuYW1lICsgJ10gLS0gJyArIGRhdGEucm9sZSArICcgLS0gJyArIGRhdGEucGVyc29uYWxpdHkpOwogICAgaWYgKGRhdGEua25vd3MubGVuZ3RoKSBsaW5lcy5wdXNoKCcgIENBTiBTSEFSRTogJyArIGRhdGEua25vd3Muam9pbignIHwgJykpOwogICAgbGluZXMucHVzaCgnICBXSUxMIFNIQVJFOiAnICsgZGF0YS53aWxsX3NoYXJlX2lmKTsKICAgIGlmIChkYXRhLndvbnRfc2hhcmUubGVuZ3RoKSBsaW5lcy5wdXNoKCcgIEFDVElWRUxZIEhJREVTOiAnICsgZGF0YS53b250X3NoYXJlLmpvaW4oJyB8ICcpKTsKICAgIGlmIChkYXRhLmNhbm5vdF9rbm93Lmxlbmd0aCkgbGluZXMucHVzaCgnICBDQU5OT1QgS05PVyAoc2F5IHRoZXkgZG8gbm90IGtub3cpOiAnICsgZGF0YS5jYW5ub3Rfa25vdy5qb2luKCcgfCAnKSk7CiAgICBsaW5lcy5wdXNoKCcgIERFRkxFQ1RJT046ICcgKyBkYXRhLmRlZmxlY3Rpb24pOwogICAgbGluZXMucHVzaCgnJyk7CiAgfSk7CgogIGdtQnJpZWZpbmcgPSBsaW5lcy5qb2luKCdbLl1uJyk7CiAgc3lzdGVtUHJvbXB0ID0gYnVpbGRTeXN0ZW1Qcm9tcHQoKTsKCiAgY29uc3QgbnBjQ291bnQgPSBPYmplY3Qua2V5cyhucGNLbm93bGVkZ2VNYXApLmxlbmd0aDsKICBjb25zb2xlLmxvZygnW0JyaWVmaW5nXSBCdWlsdCBmcm9tIC5kbmRtb2QgZGF0YS4gTlBDcyBtYXBwZWQ6JywgbnBjQ291bnQpOwogIGFkZEVudHJ5UmF3KCdHTSBicmllZmluZyByZWFkeS4gJyArIG5wY0NvdW50ICsgJyBOUENzIG1hcHBlZCBmcm9tIG1vZHVsZSBkYXRhLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7Cn0KCmZ1bmN0aW9uIGxhdW5jaEdhbWUoKSB7CiAgY29uc29sZS5sb2coJ1tsYXVuY2hHYW1lXSBjYWxsZWQsIHBhcnR5UENzOicsIEpTT04uc3RyaW5naWZ5KE9iamVjdC5rZXlzKHBhcnR5UENzKSksICdtb2R1bGVUZXh0IGxlbmd0aDonLCBtb2R1bGVUZXh0Lmxlbmd0aCk7CiAgT2JqZWN0LmtleXMocGFydHlQQ3MpLmZvckVhY2goKG4saSkgPT4geyBjb2xvck1hcFtuXSA9IFBMQVlFUl9DT0xPUlNbaSVQTEFZRVJfQ09MT1JTLmxlbmd0aF07IH0pOwoKICAvLyBBbHdheXMgcmVidWlsZCBzeXN0ZW0gcHJvbXB0IGhlcmUgdG8gYmUgc2FmZQogIGlmICghc3lzdGVtUHJvbXB0KSBzeXN0ZW1Qcm9tcHQgPSBidWlsZFN5c3RlbVByb21wdCgpOwoKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLW1vZCcpLnRleHRDb250ZW50ID0gbW9kdWxlTmFtZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJ1bGVzJykudGV4dENvbnRlbnQgPSBjaG9zZW5SdWxlczsKICBzaG93Um9vbUNvZGUoKTsKCiAgLy8gU2V0IEFJIGluZGljYXRvciBpbW1lZGlhdGVseSBmcm9tIHNlcnZlci1pbmplY3RlZCB2YWx1ZSAtLSBkb24ndCB3YWl0IGZvciBmaXJzdCByZXNwb25zZQogIGlmICh3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZSkgewogICAgdXBkYXRlQWlJbmRpY2F0b3IoJ29sbGFtYScsIHdpbmRvdy5fc2VydmVyT2xsYW1hTW9kZWwgfHwgJ2xvY2FsJyk7CiAgfSBlbHNlIGlmIChhcGlLZXkpIHsKICAgIHVwZGF0ZUFpSW5kaWNhdG9yKCdjbGF1ZGUnLCAnJyk7CiAgfQogIHNob3coJ3MtZ2FtZScpOwogIHVwZGF0ZUhVRCgpOwogIHJlbmRlclBhcnR5UGFuZWwoKTsKCiAgaWYgKCFtb2R1bGVUZXh0KSB7CiAgICBhZGRFbnRyeVJhdygnISBObyBtb2R1bGUgbG9hZGVkIC0tIHJldHVybmluZyB0byBtb2R1bGUgc2VsZWN0aW9uLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICBzZXRUaW1lb3V0KCgpID0+IHsgc2hvdygncy1uZXdnYW1lJyk7IGxvYWREbmRtb2RMaXN0KCk7IH0sIDE1MDApOwogICAgcmV0dXJuOwogIH0KCiAgY29uc3QgcGFydHlEZXNjID0gT2JqZWN0LmVudHJpZXMocGFydHlQQ3MpLm1hcCgoW3BuLHBdKSA9PgogICAgYCR7cC5uYW1lfSAocGxheWVyOiAke3BufSk6IExldmVsIDEgJHtwLnJhY2V9ICR7cC5jbHN9LCBIUCAke3AuaHB9LyR7cC5tYXhocH0sIEFDICR7cC5hY30sIFNUUiAke3Auc3RhdHMuU1RSfSBERVggJHtwLnN0YXRzLkRFWH0gQ09OICR7cC5zdGF0cy5DT059IElOVCAke3Auc3RhdHMuSU5UfSBXSVMgJHtwLnN0YXRzLldJU30gQ0hBICR7cC5zdGF0cy5DSEF9LCBHb2xkICR7cC5nb2xkfWdwLiBHZWFyOiAke3AuaW52LmpvaW4oJywgJyl9LiR7cC5zcGVjaWFscy5sZW5ndGg/JyBTcGVjaWFsIGFiaWxpdGllczogJytwLnNwZWNpYWxzLmpvaW4oJywgJyk6Jyd9YAogICkuam9pbignWy5dbicpOwoKICBjb25zdCBfZmlyc3RMb2MgPSBsb2FkZWRNb2R1bGVEYXRhICYmIGxvYWRlZE1vZHVsZURhdGEubG9jYXRpb25zICYmIGxvYWRlZE1vZHVsZURhdGEubG9jYXRpb25zWzBdOwogIGNvbnN0IF9yZWFkQWxvdWQgPSBfZmlyc3RMb2MgPyAoX2ZpcnN0TG9jLnJlYWRfYWxvdWQgfHwgX2ZpcnN0TG9jLndoYXRfcGxheWVyc19zZWUgfHwgJycpIDogJyc7CiAgY29uc3QgX2hvb2sgPSBsb2FkZWRNb2R1bGVEYXRhID8gKGxvYWRlZE1vZHVsZURhdGEuaG9vayB8fCAnJykgOiAnJzsKICBpZiAoX2ZpcnN0TG9jICYmICghcGMubG9jdGFnIHx8IHBjLmxvY3RhZyA9PT0gJy4uLicpKSB7CiAgICBwYy5sb2N0YWcgPSBfZmlyc3RMb2MuaWQgfHwgJyc7CiAgICBwYy5sb2MgICAgPSBfZmlyc3RMb2MubmFtZSB8fCAnJzsKICB9CiAgY29uc3QgaW50cm8gPSBgUGFydHk6XG4ke3BhcnR5RGVzY31cblxuWW91IGFyZSBzdGFydGluZyB0aGUgbW9kdWxlOiAiJHttb2R1bGVOYW1lfSIuXG5cbkNSSVRJQ0FMIElOU1RSVUNUSU9OOlxuVGhpcyBtb2R1bGUgaXMgYSBDTE9TRUQgV09STEQuIFlvdSBtYXkgT05MWSBkZXNjcmliZSB3aGF0IGlzIHdyaXR0ZW4gaW4gdGhlIG1vZHVsZS5cbkRvIE5PVCBpbnZlbnQgdGF2ZXJucywgY2l0aWVzLCBOUENzLCBvciBhbnkgY29udGVudCBub3QgaW4gdGhlIG1vZHVsZS5cblxuVGhlIG9wZW5pbmcgbG9jYXRpb24gaXMgZGVzY3JpYmVkIGluIHRoZSBtb2R1bGUgYXMgZm9sbG93cy4gTmFycmF0ZSBPTkxZIHRoaXM6XG4ke19ob29rID8gJ0hPT0s6ICcgKyBfaG9vayArICdcblxuJyA6ICcnfSR7X3JlYWRBbG91ZCA/ICdPUEVOSU5HIFNDRU5FIChuYXJyYXRlIHRoaXMgZXhhY3RseSwgaW4gaW1tZXJzaXZlIHByb3NlKTpcbicgKyBfcmVhZEFsb3VkIDogJ0JlZ2luIGZyb20gdGhlIGZpcnN0IGxvY2F0aW9uIGluIHRoZSBtb2R1bGUuIFVzZSBvbmx5IHdoYXQgaXMgd3JpdHRlbiB0aGVyZS4nfVxuXG5TdGFydCBuYXJyYXRpbmcgbm93LiBEbyBub3QgYWRkIGFueXRoaW5nIG5vdCBpbiB0aGUgbW9kdWxlLmA7CgogIC8vIFN5c3RlbSA2OiBJbml0aWFsaXNlIHJlc291cmNlcyBmcm9tIGNoYXJhY3RlciBpbnZlbnRvcnkKICBpbml0UmVzb3VyY2VzRnJvbUludmVudG9yeSgpOwoKICAvLyBTZWVkIHRpbWVkIGV2ZW50cyBmcm9tIC5kbmRtb2QgZGF0YQogIGlmIChsb2FkZWRNb2R1bGVEYXRhICYmIGxvYWRlZE1vZHVsZURhdGEudGltZWRfZXZlbnRzKSB7CiAgICBsb2FkZWRNb2R1bGVEYXRhLnRpbWVkX2V2ZW50cy5mb3JFYWNoKGV2ID0+IHsKICAgICAgcGxhbnRDb25zZXF1ZW5jZSgKICAgICAgICBldi5pZCB8fCBldi5uYW1lLAogICAgICAgIHBhcnNlSW50KGV2LnRyaWdnZXJfdmFsdWUpIHx8IDQsCiAgICAgICAgZXYuZGVzY3JpcHRpb24gKyAoZXYuZWZmZWN0ID8gJyAtLSAnICsgZXYuZWZmZWN0IDogJycpLAogICAgICAgIGV2LnJlcGVhdGluZyB8fCBmYWxzZQogICAgICApOwogICAgfSk7CiAgICBjb25zb2xlLmxvZygnW1RpbWVkIGV2ZW50c10gU2VlZGVkOicsIGxvYWRlZE1vZHVsZURhdGEudGltZWRfZXZlbnRzLmxlbmd0aCwgJ2V2ZW50cycpOwogIH0KCiAgLy8gVjQ6IGluaXRpYWxpc2Ugc3BlbGwgc2xvdHMsIHNwZWxsYm9vaywgY2xhc3MgYWJpbGl0aWVzCiAgaW5pdFY0U3RhdGUoKTsKCiAgLy8gU3RhcnQgdGhlIGFkdmVudHVyZSAtLSB1c2UgVjQgcGlwZWxpbmUgaWYgYXZhaWxhYmxlLCBlbHNlIGZhbGxiYWNrCiAgY29uc3Qgc3RhcnRBZHZlbnR1cmUgPSAoKSA9PiB7CiAgICAvLyBPcGVuaW5nIHNjZW5lIGlzIHB1cmUgR00gbmFycmF0aW9uLCBub3QgYSBwbGF5ZXIgYWN0aW9uCiAgICAvLyBVc2UgY2FsbEFJIGRpcmVjdGx5IHRvIGdldCBvcGVuaW5nIHByb3NlIHdpdGhvdXQgbWVjaGFuaWNhbCByZXNvbHV0aW9uCiAgICBjYWxsQUkoaW50cm8sIGZhbHNlKTsKICB9OwoKICBpZiAodXNlT2xsYW1hKSB7CiAgICBnZW5lcmF0ZUdNQnJpZWZpbmcoKQogICAgICAudGhlbigoKSA9PiBzdGFydEFkdmVudHVyZSgpKQogICAgICAuY2F0Y2goZSA9PiB7CiAgICAgICAgY29uc29sZS5lcnJvcignW0dNQnJpZWZpbmddIEVycm9yOicsIGUpOwogICAgICAgIHN0YXJ0QWR2ZW50dXJlKCk7CiAgICAgIH0pOwogIH0gZWxzZSB7CiAgICBzdGFydEFkdmVudHVyZSgpOwogIH0KfQoKZnVuY3Rpb24gYXJtb3VyTGFiZWwobmFtZSwgYSkgewogICAgcmV0dXJuIGAke25hbWV9IC0tIEFDICR7YS5hY30gKCR7YS5jb3N0fWdwKWA7CiAgfQpmdW5jdGlvbiBlcXVpcExhYmVsKG5hbWUsIGUpIHsKICAgIGNvbnN0IGNvc3QgPSBlLmNvc3QgPiAwID8gYCAoJHtlLmNvc3R9Z3ApYCA6ICcgKGZyZWUpJzsKICAgIGNvbnN0IG5vdGVzID0gZS5ub3RlcyA/IGAgLS0gJHtlLm5vdGVzfWAgOiAnJzsKICAgIHJldHVybiBgJHtuYW1lfSR7Y29zdH0ke25vdGVzfWA7CiAgfQpmdW5jdGlvbiB3ZWFwb25MYWJlbChuYW1lLCB3KSB7CiAgICBjb25zdCBjb3N0ID0gdy5jb3N0ID4gMCA/IGAgKCR7dy5jb3N0fWdwKWAgOiAnIChmcmVlKSc7CiAgICBjb25zdCBub3RlcyA9IHcubm90ZXMgPyBgIC0tICR7dy5ub3Rlc31gIDogJyc7CiAgICByZXR1cm4gYCR7bmFtZX0gWyR7dy5kbWd9XSR7Y29zdH0ke25vdGVzfWA7CiAgfQpmdW5jdGlvbiBzYWZlU2V0KG9iaiwga2V5LCB2YWwpIHsgdHJ5IHsgb2JqW2tleV0gPSB2YWw7IH0gY2F0Y2goZSkge30gfQoKZnVuY3Rpb24gY2xhc3NpZnlQbGF5ZXJBY3Rpb24odGV4dCkgewogIGNvbnN0IHQgPSB0ZXh0LnRvTG93ZXJDYXNlKCk7CgogIC8vIENvbWJhdAogIGlmICgvXGIoYXR0YWNrfHN0cmlrZXxzdGFifHNsYXNofHNob290fGZpcmV8dGhyb3d8Y2hhcmdlfHN3aW5nfGhpdHxmaWdodHxraWxsfHNsYXl8ZW5nYWdlKVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5DT01CQVQ7CgogIC8vIE1hZ2ljCiAgaWYgKC9cYihjYXN0fHNwZWxsfG1hZ2ljIG1pc3NpbGV8c2xlZXB8Y2hhcm18ZGV0ZWN0fHJlYWQgbWFnaWN8bWVtb3JpemV8cHJheXx0dXJuIHVuZGVhZHxjaGFubmVsKVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5NQUdJQzsKCiAgLy8gU2VhcmNoIC8gZXhhbWluZQogIGlmICgvXGIoc2VhcmNofGV4YW1pbmV8aW5zcGVjdHxsb29rIGF0fGNoZWNrfGludmVzdGlnYXRlfGZlZWx8dG91Y2h8bGlzdGVufGhlYXJ8c21lbGx8dGFzdGV8cHJvZHxwb2tlfHRhcClcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuU0VBUkNIOwoKICAvLyBTb2NpYWwKICBpZiAoL1xiKHRhbGt8c3BlYWt8YXNrfHRlbGx8c2F5fHdoaXNwZXJ8c2hvdXR8cGVyc3VhZGV8YnJpYmV8dGhyZWF0ZW58aW50aW1pZGF0ZXxjaGFybXxuZWdvdGlhdGV8Y29udmluY2V8cXVlc3Rpb258Z3JlZXR8aW50cm9kdWNlKVxiLy50ZXN0KHQpKQogICAgcmV0dXJuIEFDVElPTl9UWVBFUy5TT0NJQUw7CgogIC8vIFRoaWVmIHNraWxscwogIGlmICgvXGIocGljayBsb2NrfG9wZW4gbG9ja3xkaXNhcm0gdHJhcHxyZW1vdmUgdHJhcHxoaWRlfHNuZWFrfG1vdmUgc2lsZW50bHl8Y2xpbWJ8cGlja3BvY2tldHxzdGVhbHxiYWNrc3RhYilcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuU0tJTEw7CgogIC8vIEl0ZW0gdXNlCiAgaWYgKC9cYih1c2V8ZHJpbmt8YXBwbHl8b3BlbnxjbG9zZXxsaWdodHxleHRpbmd1aXNofHJlYWR8d2VhcnxlcXVpcHxkcm9wfGdpdmV8dGFrZXxncmFifHBvY2tldClcYi8udGVzdCh0KSkKICAgIHJldHVybiBBQ1RJT05fVFlQRVMuSVRFTTsKCiAgLy8gUmVzdAogIGlmICgvXGIocmVzdHxzbGVlcHxjYW1wfG1ha2UgY2FtcHx0YWtlIGEgcmVzdHxiYW5kYWdlfGJpbmQgd291bmRzfHJlY292ZXIpXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLlJFU1Q7CgogIC8vIE1vdmVtZW50CiAgaWYgKC9cYihnb3xtb3ZlfHdhbGt8cnVufGNsaW1ifGRlc2NlbmR8ZW50ZXJ8ZXhpdHxsZWF2ZXxoZWFkfG5vcnRofHNvdXRofGVhc3R8d2VzdHx1cHxkb3dufHRocm91Z2h8YWNyb3NzfGZvbGxvd3xyZXR1cm58c25lYWspXGIvLnRlc3QodCkpCiAgICByZXR1cm4gQUNUSU9OX1RZUEVTLk1PVkVNRU5UOwoKICByZXR1cm4gQUNUSU9OX1RZUEVTLk9USEVSOwp9CgpmdW5jdGlvbiBnZXRBY3Rpb25HdWlkYW5jZShhY3Rpb25UeXBlKSB7CiAgY29uc3QgZ3VpZGVzID0gewogICAgW0FDVElPTl9UWVBFUy5DT01CQVRdOgogICAgICAnQ09NQkFUIEFDVElPTiAtLSBNQU5EQVRPUlkgRElDRSBSRVNPTFVUSU9OOiAnICsKICAgICAgJ1RoZSBwbGF5ZXIgZGVjbGFyZWQgYW4gYXR0YWNrIC0tIHRoZSBkaWNlIGVuZ2luZSBoYXMgYWxyZWFkeSByb2xsZWQuICcgKwogICAgICAnVXNlIHRoZSBbRElDRSBSRVNVTFRTXSBibG9jayBiZWxvdyAtLSBETyBOT1QgcmUtcm9sbCwgRE8gTk9UIGlnbm9yZSB0aGUgcmVzdWx0LiAnICsKICAgICAgJ05hcnJhdGUgdGhlIG91dGNvbWUgb2YgdGhvc2UgZXhhY3QgZGljZS4gJyArCiAgICAgICdBIEhJVDogZGVzY3JpYmUgdGhlIGltcGFjdCB2aXZpZGx5LiBBIE1JU1M6IGRlc2NyaWJlIHRoZSBuZWFyIG1pc3MuIEEgQ1JJVElDQUw6IGRlc2NyaWJlIGRldmFzdGF0aW9uLiBBIEZVTUJMRTogZGVzY3JpYmUgbWlzaGFwLiAnICsKICAgICAgJ0lmIG5vIGRpY2UgcmVzdWx0cyBwcm92aWRlZCwgcm9sbCB5b3Vyc2VsZjogZDIwICsgc3RhdCBtb2QgdnMgVEhBQzAsIHRoZW4gZGFtYWdlLiBTaG93IGFsbCByb2xscyBpbiBbYnJhY2tldHNdLiAnICsKICAgICAgJ0lmIHRoZSB0YXJnZXQgaXMgYW4gb2JqZWN0OiBBQyA5IHNvZnQgKHdvb2Qvcm9wZSksIEFDIDUgaGFyZCAoc3RvbmUvaXJvbikuJywKICAgIFtBQ1RJT05fVFlQRVMuTUFHSUNdOgogICAgICAnTUFHSUMgQUNUSU9OOiBBcHBseSB0aGUgZXhhY3QgT1NFIHNwZWxsIGVmZmVjdC4gVHJhY2sgdGhlIHNwZWxsIHNsb3QgYXMgdXNlZC4gRGVzY3JpYmUgdGhlIG1hZ2ljYWwgZWZmZWN0IGF0bW9zcGhlcmljYWxseS4gUmVtaW5kIHBsYXllciBpZiB0aGV5IGFyZSBvdXQgb2Ygc2xvdHMuJywKICAgIFtBQ1RJT05fVFlQRVMuU0VBUkNIXToKICAgICAgJ1NFQVJDSCBBQ1RJT046IFRoZSBwbGF5ZXIgaXMgZXhhbWluaW5nIHNvbWV0aGluZyBjYXJlZnVsbHkuIFVzZSB0aGUgT1NFIHNlYXJjaCBydWxlIChkNj0xIHN1Y2Nlc3MsIGVsdmVzIDEtMikuIERlc2NyaWJlIHdoYXQgdGhleSBmaW5kIG9yIGRvIG5vdCBmaW5kLiBSZXdhcmQgdGhvcm91Z2huZXNzLicsCiAgICBbQUNUSU9OX1RZUEVTLlNPQ0lBTF06CiAgICAgICdTT0NJQUwgQUNUSU9OOiBGb2N1cyBvbiBOUEMgdm9pY2UsIHBlcnNvbmFsaXR5LCBhbmQgaW5mb3JtYXRpb24gbGltaXRzLiBBcHBseSB0aGUgTlBDIGtub3dsZWRnZSBtYXAgc3RyaWN0bHkuIFVzZSB0aGUgYXBwcm9wcmlhdGUgZGVmbGVjdGlvbiBpZiB0aGV5IGhpdCB0aGUga25vd2xlZGdlIGJvdW5kYXJ5LicsCiAgICBbQUNUSU9OX1RZUEVTLlNLSUxMXToKICAgICAgJ1RISUVGIFNLSUxMIEFDVElPTjogUm9sbCB0aGUgYXBwcm9wcmlhdGUgdGhpZWYgc2tpbGwgcGVyY2VudGFnZS4gT25seSBUaGllZi9BY3JvYmF0L0Fzc2Fzc2luIGNhbiB1c2UgdGhlc2UuIERlc2NyaWJlIHRoZSBhdHRlbXB0IGFuZCBpdHMgcmVzdWx0IHNwZWNpZmljYWxseS4nLAogICAgW0FDVElPTl9UWVBFUy5JVEVNXToKICAgICAgJ0lURU0gQUNUSU9OOiBSZXNvbHZlIHRoZSBpdGVtIHVzZSBwcmVjaXNlbHkuIFVwZGF0ZSBpbnZlbnRvcnkgaW4gU1RBVEUuIERlc2NyaWJlIGFueSBlZmZlY3QuIFRyYWNrIGNvbnN1bWFibGVzICh0b3JjaGVzLCBvaWwsIHJhdGlvbnMsIHBvdGlvbnMpLicsCiAgICBbQUNUSU9OX1RZUEVTLlJFU1RdOgogICAgICAnUkVTVCBBQ1RJT04gLS0gT1NFIFJVTEVTOiAnICsKICAgICAgJ0RVTkdFT04gUkVTVCAoMSB0dXJuLCBubyBIUCwgZHVuZ2VvbiBvbmx5KTogUmVzZXRzIHRoZSA2LXR1cm4gcmVzdCBjbG9jay4gQXZvaWRzIHdhbmRlcmluZyBtb25zdGVyIHBlbmFsdHkuIENhbGwgaGFuZGxlRHVuZ2VvblJlc3QoKS4gRm9ybWF0OiBbUmVzdCB0YWtlbiAtIDEgdHVybi5dICcgKwogICAgICAnRlVMTCBPVkVSTklHSFQgUkVTVCAoOCBob3VycyBzYWZlKTogUmVjb3ZlciAxIEhQL2xldmVsLCBjb25zdW1lIDEgcmF0aW9uLCBjYWxsIGhhbmRsZUZ1bGxSZXN0KCkuIEZvcm1hdDogW0Z1bGwgcmVzdC4gUmVjb3ZlcmVkIFggSFAuIENvbnN1bWVkIDEgcmF0aW9uLl0gJyArCiAgICAgICdGT1JDRUQgTUFSQ0ggKGRvdWJsZSBzcGVlZCk6IFNhdmUgdnMgRGVhdGggb3IgY29sbGFwc2UgMWQ2IHR1cm5zLiBGb3JtYXQ6IFtGb3JjZWQgbWFyY2ggLSBTYXZlIHZzIERlYXRoOiBkMjA9WCAtIFNVQ0NFU1MvRkFJTF0gJyArCiAgICAgICdDdXJyZW50IHN0YXR1czogU3RhcnZhdGlvbiBwZW5hbHR5IC0nICsgc3RhcnZhdGlvblBlbmFsdHkgKyAoaXNJbkR1bmdlb24oKSA/ICcsIER1bmdlb24gdHVybnMgd2l0aG91dCByZXN0OiAnICsgdHVybnNXaXRob3V0UmVzdCArICcvNicgOiAnJykgKyAnLicsCiAgICBbQUNUSU9OX1RZUEVTLk1PVkVNRU5UXTogKCgpID0+IHsKICAgICAgLy8gSW5qZWN0IGF1dGhvcml0YXRpdmUgZXhpdHMgZm9yIGN1cnJlbnQgcm9vbSBmcm9tIHJvb20gbWFwCiAgICAgIGNvbnN0IGN1cnJlbnRSb29tID0gT2JqZWN0LmVudHJpZXMoCiAgICAgICAgKGxvYWRlZE1vZHVsZURhdGEgJiYgbG9hZGVkTW9kdWxlRGF0YS5yb29tX21hcCkgfHwge30KICAgICAgKS5maW5kKChbaWQsIF9dKSA9PiB7CiAgICAgICAgY29uc3QgbG9jID0gKGxvYWRlZE1vZHVsZURhdGEubG9jYXRpb25zIHx8IFtdKS5maW5kKGwgPT4gbC5pZCA9PT0gaWQpOwogICAgICAgIHJldHVybiBsb2MgJiYgbG9jLm5hbWUgPT09IHBjLmxvYzsKICAgICAgfSk7CiAgICAgIGNvbnN0IGV4aXRJbmZvID0gY3VycmVudFJvb20KICAgICAgICA/ICcgQ3VycmVudCByb29tIGV4aXRzOiAnICsgT2JqZWN0LmVudHJpZXMoY3VycmVudFJvb21bMV0pCiAgICAgICAgICAgIC5maWx0ZXIoKFtkLHRdKSA9PiB0KS5tYXAoKFtkLHRdKSA9PiBkICsgJ+KGkicgKyB0KS5qb2luKCcsICcpICsgJy4nCiAgICAgICAgOiAnJzsKICAgICAgcmV0dXJuICdNT1ZFTUVOVCBBQ1RJT046IERlc2NyaWJlIHdoYXQgdGhleSBlbmNvdW50ZXIgYXMgdGhleSBtb3ZlLiBFYWNoIGR1bmdlb24gYXJlYSB0YWtlcyAxIHR1cm4gdG8gZXhwbG9yZSBjYXJlZnVsbHkuJyArIGV4aXRJbmZvICsgJyBSb2xsIGZvciB3YW5kZXJpbmcgbW9uc3RlcnMgaWYgYXBwcm9wcmlhdGUuJzsKICAgIH0pKCksCiAgICBbQUNUSU9OX1RZUEVTLk9USEVSXToKICAgICAgJ1BMQVlFUiBBQ1RJT046IFJlc29sdmUgdGhpcyBjcmVhdGl2ZWx5IGFuZCBmYWl0aGZ1bGx5IHRvIHRoZSBtb2R1bGUuIFJld2FyZCBjbGV2ZXIgdGhpbmtpbmcuJywKICB9OwogIHJldHVybiBndWlkZXNbYWN0aW9uVHlwZV0gfHwgZ3VpZGVzW0FDVElPTl9UWVBFUy5PVEhFUl07Cn0KCmZ1bmN0aW9uIGdldFBhY2luZ0d1aWRhbmNlKCkgewogIGNvbnN0IGd1aWRlcyA9IHsKICAgIG9wZW5pbmc6ICAnUEFDSU5HIC0tIE9wZW5pbmc6IEVzdGFibGlzaCBhdG1vc3BoZXJlIGFuZCBteXN0ZXJ5LiBSZXdhcmQgZXhwbG9yYXRpb24uIExldCB0aGUgd29ybGQgYnJlYXRoZS4gVGhlIHRocmVhdCBzaG91bGQgZmVlbCBkaXN0YW50IGJ1dCByZWFsLicsCiAgICBidWlsZGluZzogJ1BBQ0lORyAtLSBCdWlsZGluZyB0ZW5zaW9uOiBEcm9wIGhpbnRzIG9mIGRhbmdlci4gTlBDcyBhcmUgZWRnaWVyLiBTaGFkb3dzIHNlZW0gZGVlcGVyLiBOb3QgY29tYmF0IHlldCAtLSBhbnRpY2lwYXRpb24uJywKICAgIHJpc2luZzogICAnUEFDSU5HIC0tIFJpc2luZyBhY3Rpb246IERhbmdlciBpcyBjbG9zZS4gTWFrZSBldmVyeSBkZWNpc2lvbiBmZWVsIHdlaWdodHkuIENvbnNlcXVlbmNlcyBsb29tLicsCiAgICBwZWFrOiAgICAgJ1BBQ0lORyAtLSBDbGltYXg6IEZ1bGwgaW50ZW5zaXR5LiBObyBob2xkaW5nIGJhY2suIFRoaXMgaXMgT1NFIC0tIGxldGhhbCwgZmFzdCwgYnJ1dGFsLiBFdmVyeSByb2xsIG1hdHRlcnMuJywKICAgIGZhbGxpbmc6ICAnUEFDSU5HIC0tIEZhbGxpbmcgYWN0aW9uOiBUaGUgaW1tZWRpYXRlIGRhbmdlciBoYXMgcGFzc2VkLiBDaGFyYWN0ZXJzIGNhdGNoIHRoZWlyIGJyZWF0aC4gQnV0IHRoZSB3b3JsZCByZW1lbWJlcnMgd2hhdCBqdXN0IGhhcHBlbmVkLicsCiAgICByZXN0OiAgICAgJ1BBQ0lORyAtLSBSZWNvdmVyeTogUXVpZXQgbW9tZW50LiBMZXQgdGhlIHBsYXllcnMgY29uc29saWRhdGUsIHBsYW4sIGhlYWwuIEZvcmVzaGFkb3cgd2hhdCBjb21lcyBuZXh0IHRocm91Z2ggYXRtb3NwaGVyZSAtLSBhIGRpc3RhbnQgc291bmQsIGEgc3RyYW5nZSBzbWVsbC4nLAogIH07CiAgcmV0dXJuIGd1aWRlc1tjdXJyZW50UGFjaW5nUGhhc2VdIHx8ICcnOwp9CgpmdW5jdGlvbiB1cGRhdGVQYWNpbmcocmF3UmVzcG9uc2UsIGFjdGlvblR5cGUpIHsKICAvLyBTY29yZSB0aGlzIHR1cm4ncyB0ZW5zaW9uIGxldmVsICgwLTEwKQogIGxldCBzY29yZSA9IDM7IC8vIGJhc2VsaW5lCiAgaWYgKGFjdGlvblR5cGUgPT09IEFDVElPTl9UWVBFUy5DT01CQVQpIHNjb3JlICs9IDQ7CiAgaWYgKGFjdGlvblR5cGUgPT09IEFDVElPTl9UWVBFUy5TS0lMTCkgc2NvcmUgKz0gMjsKCiAgLy8gQm9vc3QgZnJvbSByZXNwb25zZSBjb250ZW50CiAgY29uc3QgZGFuZ2VyID0gKHJhd1Jlc3BvbnNlLm1hdGNoKC9cYihhdHRhY2t8d291bmR8Ymxvb2R8ZGVhdGh8ZmxlZXxwb2lzb258dHJhcHxkYW5nZXJ8c2NyZWFtKVxiL2dpKXx8W10pLmxlbmd0aDsKICBjb25zdCBjYWxtICAgPSAocmF3UmVzcG9uc2UubWF0Y2goL1xiKHNhZmV8cmVzdHxxdWlldHxwZWFjZWZ1bHxlbXB0eXxub3RoaW5nfG5vcm1hbClcYi9naSl8fFtdKS5sZW5ndGg7CiAgc2NvcmUgPSBNYXRoLm1pbigxMCwgTWF0aC5tYXgoMCwgc2NvcmUgKyBNYXRoLm1pbihkYW5nZXIsIDQpIC0gTWF0aC5taW4oY2FsbSwgMikpKTsKCiAgcGFjaW5nSGlzdG9yeS5wdXNoKHNjb3JlKTsKICBpZiAocGFjaW5nSGlzdG9yeS5sZW5ndGggPiAxMCkgcGFjaW5nSGlzdG9yeS5zaGlmdCgpOwoKICAvLyBUcmFjayBjb21iYXQgZ2FwCiAgaWYgKGFjdGlvblR5cGUgPT09IEFDVElPTl9UWVBFUy5DT01CQVQpIHsKICAgIHR1cm5zU2luY2VMYXN0Q29tYmF0ID0gMDsKICB9IGVsc2UgewogICAgdHVybnNTaW5jZUxhc3RDb21iYXQrKzsKICB9CgogIC8vIERldGVybWluZSBwYWNpbmcgcGhhc2UKICBjb25zdCBhdmcgPSBwYWNpbmdIaXN0b3J5LnJlZHVjZSgoYSxiKT0+YStiLDApIC8gcGFjaW5nSGlzdG9yeS5sZW5ndGg7CiAgY29uc3QgcmVjZW50ID0gcGFjaW5nSGlzdG9yeS5zbGljZSgtMykucmVkdWNlKChhLGIpPT5hK2IsMCkgLyBNYXRoLm1pbigzLCBwYWNpbmdIaXN0b3J5Lmxlbmd0aCk7CgogIGlmICh0dXJuQ291bnQgPD0gMykgewogICAgY3VycmVudFBhY2luZ1BoYXNlID0gJ29wZW5pbmcnOwogIH0gZWxzZSBpZiAocmVjZW50ID4gYXZnICsgMS41KSB7CiAgICBjdXJyZW50UGFjaW5nUGhhc2UgPSAncGVhayc7CiAgfSBlbHNlIGlmIChhdmcgPj0gNikgewogICAgY3VycmVudFBhY2luZ1BoYXNlID0gJ3Jpc2luZyc7CiAgfSBlbHNlIGlmIChhdmcgPD0gMiAmJiB0dXJuc1NpbmNlTGFzdENvbWJhdCA+IDQpIHsKICAgIGN1cnJlbnRQYWNpbmdQaGFzZSA9ICdyZXN0JzsKICB9IGVsc2UgaWYgKHJlY2VudCA8IGF2ZyAtIDEpIHsKICAgIGN1cnJlbnRQYWNpbmdQaGFzZSA9ICdmYWxsaW5nJzsKICB9IGVsc2UgewogICAgY3VycmVudFBhY2luZ1BoYXNlID0gJ2J1aWxkaW5nJzsKICB9Cn0KCmZ1bmN0aW9uIGJ1aWxkQ29tYmF0QmxvY2soKSB7CiAgaWYgKCFpbkNvbWJhdCkgcmV0dXJuICcnOwogIGNvbnN0IGxpbmVzID0gW107CiAgbGluZXMucHVzaCgnIENPTUJBVCAtLSBSb3VuZCAnICsgY29tYmF0U3RhdGUucm91bmQgKyAnICcpOwogIGxpbmVzLnB1c2goJ09TRSBHUk9VUCBJTklUSUFUSVZFOiBQYXJ0eSBkNj0nICsgY29tYmF0U3RhdGUucGFydHlJbml0ICsKICAgICcgdnMgTW9uc3RlcnMgZDY9JyArIGNvbWJhdFN0YXRlLm1vbnN0ZXJJbml0ICsKICAgIChjb21iYXRTdGF0ZS5wYXJ0eUFjdHNGaXJzdCA/ICcgLS0gUEFSVFkgYWN0cyBmaXJzdCB0aGlzIHJvdW5kJyA6ICcgLS0gTU9OU1RFUlMgYWN0IGZpcnN0IHRoaXMgcm91bmQnKSk7CgogIGNvbnN0IHBhcnR5U2lkZSA9IGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5maWx0ZXIoYyA9PiBjLmlzUGxheWVyICYmICFjLmRlYWQgJiYgIWMuZmxlZCk7CiAgY29uc3QgbW9uc3RlclNpZGUgPSBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZmlsdGVyKGMgPT4gIWMuaXNQbGF5ZXIgJiYgIWMuZGVhZCAmJiAhYy5mbGVkKTsKCiAgaWYgKHBhcnR5U2lkZS5sZW5ndGgpIHsKICAgIGxpbmVzLnB1c2goJ1BhcnR5OiAnICsgcGFydHlTaWRlLm1hcChjID0+IGMubmFtZSArICcgSFA6JyArIGMuaHAgKyAnLycgKyBjLm1heEhwICsgJyBBQzonICsgYy5hYykuam9pbignIHwgJykpOwogIH0KICBpZiAobW9uc3RlclNpZGUubGVuZ3RoKSB7CiAgICBsaW5lcy5wdXNoKCdFbmVtaWVzOiAnICsgbW9uc3RlclNpZGUubWFwKGMgPT4gYy5uYW1lICsgJyBIUDp+JyArIGMuaHAgKyAnIEFDOicgKyBjLmFjICsgJyAoSEQgJyArIGMuaGQgKyAnKScpLmpvaW4oJyB8ICcpKTsKICB9CgogIGNvbnN0IGRlYWQgPSBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZmlsdGVyKGMgPT4gYy5kZWFkKTsKICBjb25zdCBmbGVkID0gY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZpbHRlcihjID0+IGMuZmxlZCk7CiAgaWYgKGRlYWQubGVuZ3RoKSBsaW5lcy5wdXNoKCdEb3duOiAnICsgZGVhZC5tYXAoYyA9PiBjLm5hbWUpLmpvaW4oJywgJykpOwogIGlmIChmbGVkLmxlbmd0aCkgbGluZXMucHVzaCgnRmxlZDogJyArIGZsZWQubWFwKGMgPT4gYy5uYW1lKS5qb2luKCcsICcpKTsKCiAgbGluZXMucHVzaCgnJyk7CiAgbGluZXMucHVzaCgnT1NFIENPTUJBVCBSVUxFUyBUSElTIFJPVU5EOicpOwogIGxpbmVzLnB1c2goJzEuIFJlLXJvbGwgZ3JvdXAgaW5pdGlhdGl2ZSBlYWNoIHJvdW5kIChkNiBwZXIgc2lkZSknKTsKICBsaW5lcy5wdXNoKCcyLiBXaW5uaW5nIHNpZGUgQUxMIGFjdCBiZWZvcmUgbG9zaW5nIHNpZGUgYWN0cycpOwogIGxpbmVzLnB1c2goJzMuIEF0dGFjazogZDIwICsgU1RSIG1vZCAobWVsZWUpIG9yIERFWCBtb2QgKHJhbmdlZCkgLS0gaGl0IGlmIHRvdGFsIG1lZXRzL2JlYXRzIFRIQUMwIHRhcmdldCBmb3IgdGhhdCBBQycpOwogIGxpbmVzLnB1c2goJzQuIERhbWFnZTogd2VhcG9uIGRpZSArIFNUUiBtb2QgKG1lbGVlIG9ubHkpLCBtaW5pbXVtIDEnKTsKICBsaW5lcy5wdXNoKCc1LiBTaG93IEFMTCByb2xsczogW2Q2IGluaXRpYXRpdmVdLCBbZDIwIGF0dGFja10sIFtkYW1hZ2UgZGljZV0nKTsKICBsaW5lcy5wdXNoKCc2LiBNb3JhbGU6IGNoZWNrIDJkNiB2cyBtb3JhbGUgc2NvcmUgd2hlbiBtb25zdGVyIGxvc2VzIGhhbGYgSFAgb3IgbGVhZGVyIGRpZXMnKTsKICByZXR1cm4gbGluZXMuam9pbignXG4nKTsKfQoKZnVuY3Rpb24gYnVpbGRDb25zZXF1ZW5jZUJsb2NrKCkgewogIGlmICghcGVuZGluZ0NvbnNlcXVlbmNlcy5sZW5ndGgpIHJldHVybiAnJzsKICBjb25zdCBsaW5lcyA9IFsnQ09OU0VRVUVOQ0UgLS0gd2VhdmUgdGhpcyBuYXR1cmFsbHkgaW50byB0aGUgc2NlbmUgd2l0aG91dCBhbm5vdW5jaW5nIGl0IGRpcmVjdGx5OiddOwogIHBlbmRpbmdDb25zZXF1ZW5jZXMuZm9yRWFjaChjID0+IGxpbmVzLnB1c2goJyAgJyArIGMuZGVzY3JpcHRpb24pKTsKICByZXR1cm4gbGluZXMuam9pbignXG4nKTsKfQoKZnVuY3Rpb24gY2hlY2tDb25zZXF1ZW5jZXMoKSB7CiAgcGVuZGluZ0NvbnNlcXVlbmNlcyA9IFtdOwogIGNvbnNlcXVlbmNlcy5mb3JFYWNoKGMgPT4gewogICAgaWYgKCFjLmluamVjdGVkICYmIHR1cm5Db3VudCA+PSBjLmR1ZV9hdF90dXJuKSB7CiAgICAgIHBlbmRpbmdDb25zZXF1ZW5jZXMucHVzaChjKTsKICAgICAgLy8gUmUtcGxhbnQgcmVwZWF0aW5nIGV2ZW50cwogICAgICBpZiAoYy5yZXBlYXRfZXZlcnkpIHsKICAgICAgICBjLmR1ZV9hdF90dXJuID0gdHVybkNvdW50ICsgYy5yZXBlYXRfZXZlcnk7CiAgICAgICAgYy5pbmplY3RlZCA9IGZhbHNlOwogICAgICB9IGVsc2UgewogICAgICAgIGMuaW5qZWN0ZWQgPSB0cnVlOwogICAgICB9CiAgICB9CiAgfSk7CiAgLy8gQ2xlYW4gdXAgbm9uLXJlcGVhdGluZyBpbmplY3RlZCBjb25zZXF1ZW5jZXMgb2xkZXIgdGhhbiAxMCB0dXJucwogIGlmIChjb25zZXF1ZW5jZXMubGVuZ3RoID4gNDApIHsKICAgIGNvbnNlcXVlbmNlcyA9IGNvbnNlcXVlbmNlcy5maWx0ZXIoYyA9PgogICAgICBjLnJlcGVhdF9ldmVyeSB8fCAhYy5pbmplY3RlZCB8fCB0dXJuQ291bnQgLSBjLmR1ZV9hdF90dXJuIDwgMTAKICAgICk7CiAgfQp9CgpmdW5jdGlvbiBleHRyYWN0Q29uc2VxdWVuY2VzKHJhd1Jlc3BvbnNlLCBhY3Rpb25UeXBlKSB7CiAgLy8gT25seSBwbGFudCBhIGNvbnNlcXVlbmNlIGlmIHdlIGhhdmVuJ3QgYWxyZWFkeSBwbGFudGVkIHRoZSBzYW1lIHR5cGUgcmVjZW50bHkKICBjb25zdCBoYXNSZWNlbnQgPSAodHlwZSkgPT4gY29uc2VxdWVuY2VzLnNvbWUoYyA9PgogICAgYy5ldmVudCA9PT0gdHlwZSAmJiAodHVybkNvdW50IC0gKGMuZHVlX2F0X3R1cm4gLSA4KSkgPCA2CiAgKTsKCiAgY29uc3QgciA9IHJhd1Jlc3BvbnNlLnRvTG93ZXJDYXNlKCk7CgogIC8vIExvdWQgbm9pc2UgLS0gb25seSBvdXRzaWRlIGNvbWJhdCAoY29tYmF0IG5vaXNlIGlzIGV4cGVjdGVkKQogIC8vIE11c3QgYmUgYSBkZWxpYmVyYXRlIGxvdWQgYWN0aW9uLCBub3QgaW5jaWRlbnRhbCBkZXNjcmlwdGlvbgogIGlmICghaW5Db21iYXQgJiYgIWhhc1JlY2VudCgnbm9pc2VfYWxlcnQnKSkgewogICAgY29uc3QgbG91ZEFjdGlvbiA9IC9cYihzaG91dHM/fHNjcmVhbXM/fGNyYXNoZXM/fGV4cGxvc2lvbnM/fGJhbmdzP3xhbGFybXM/IChzb3VuZHM/fHJpbmdzP3x0cmlnZ2VyZWQpKVxiLy50ZXN0KHIpOwogICAgaWYgKGxvdWRBY3Rpb24pIHsKICAgICAgcGxhbnRDb25zZXF1ZW5jZSgnbm9pc2VfYWxlcnQnLCAyICsgTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKjMpLAogICAgICAgICdUaGUgZWFybGllciBjb21tb3Rpb24gaGFzIGRyYXduIGF0dGVudGlvbiAtLSBzb21ldGhpbmcgc3RpcnMgaW4gdGhlIHBhc3NhZ2VzIG5lYXJieS4nKTsKICAgIH0KICB9CgogIC8vIEJvZHkgbGVmdCBpbiBjb3JyaWRvciAtLSBvbmx5IHdoZW4gYm9keSArIHNwZWNpZmljIGxvY2F0aW9uIHdvcmRzIGNvLW9jY3VyCiAgaWYgKCFoYXNSZWNlbnQoJ2JvZHlfZm91bmQnKSkgewogICAgY29uc3QgYm9keUxlZnQgPSAvXGIoYm9keXxjb3Jwc2V8cmVtYWlucz98Y2FyY2FzcylcYi8udGVzdChyKQogICAgICAmJiAvXGIoY29ycmlkb3J8aGFsbHdheXxwYXNzYWdlfGZsb29yfGRvb3J3YXl8bGFuZGluZylcYi8udGVzdChyKQogICAgICAmJiAvXGIobGVhdmV8bGVmdHxkcmFnfGR1bXB8cHVzaHxsaWVzP3xzbHVtcGVkPylcYi8udGVzdChyKTsKICAgIGlmIChib2R5TGVmdCkgewogICAgICBwbGFudENvbnNlcXVlbmNlKCdib2R5X2ZvdW5kJywgNCArIE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSo0KSwKICAgICAgICAnVGhlIGJvZHkgbGVmdCBpbiB0aGUgcGFzc2FnZSBoYXMgYmVlbiBmb3VuZCAtLSB3b3JkIGlzIHNwcmVhZGluZyB0aHJvdWdoIHRoZSBkdW5nZW9uLicpOwogICAgfQogIH0KCiAgLy8gRmlyZSB0aGF0IGlzIHNwcmVhZGluZyAobm90IGEgdG9yY2ggYmVpbmcgbGl0KQogIGlmICghaGFzUmVjZW50KCdmaXJlX3NwcmVhZHMnKSkgewogICAgY29uc3QgZmlyZUFjdCA9IC9cYihzZXQocyk/IChhKT9maXJlfGlnbml0ZVtzZF0/fHRvcmNoKGVzfGVkKT98YnVybihzfGluZ3xlZCkpXGIvLnRlc3QocikKICAgICAgJiYgIS9cYih0b3JjaCBidXJucz98dG9yY2hsaWdodHxsYW50ZXJufGNhbmRsZSlcYi8udGVzdChyKTsKICAgIGlmIChmaXJlQWN0KSB7CiAgICAgIHBsYW50Q29uc2VxdWVuY2UoJ2ZpcmVfc3ByZWFkcycsIDMsCiAgICAgICAgJ1RoZSBmaXJlIHNldCBlYXJsaWVyIGlzIHNwcmVhZGluZyAtLSBzbW9rZSBkcmlmdHMgdGhyb3VnaCB0aGUgYWRqb2luaW5nIHBhc3NhZ2VzLicpOwogICAgfQogIH0KCiAgLy8gRW5lbXkgdGhhdCBzdWNjZXNzZnVsbHkgZmxlZCAobm90IGRyaXZlbiBiYWNrLCBidXQgYWN0dWFsbHkgZXNjYXBlZCkKICBpZiAoIWhhc1JlY2VudCgnZW5lbXlfcmV0dXJucycpKSB7CiAgICBjb25zdCBlbmVteUZsZWQgPSAvXGIoZmxlZXM/fGZsZWR8ZXNjYXBlcz98ZXNjYXBlZHxydW5zPyAoYXdheXxvZmYpfHJldHJlYXRzP3xyZXRyZWF0ZWQpXGIvLnRlc3QocikKICAgICAgJiYgL1xiKGdvYmxpbnxvcmN8Z3VhcmR8c29sZGllcnxiYW5kaXR8Y3VsdGlzdHxtb25zdGVyfGNyZWF0dXJlfGVuZW15fGZvZSlcYi8udGVzdChyKTsKICAgIGlmIChlbmVteUZsZWQpIHsKICAgICAgcGxhbnRDb25zZXF1ZW5jZSgnZW5lbXlfcmV0dXJucycsIDUgKyBNYXRoLmZsb29yKE1hdGgucmFuZG9tKCkqNSksCiAgICAgICAgJ1RoZSBjcmVhdHVyZSB0aGF0IGZsZWQgZWFybGllciBoYXMgcmV0dXJuZWQgd2l0aCBhaWQgLS0gaXQgcmVtZW1iZXJlZCB0aGUgcGFydHkuJyk7CiAgICB9CiAgfQoKICAvLyBEZWxpYmVyYXRlbHkgYnJva2VuIGRvb3IgKGZvcmNlZCwgbm90IG9wZW5lZCkKICBpZiAoIWhhc1JlY2VudCgnYnJva2VuX2Rvb3InKSkgewogICAgY29uc3QgZG9vckJyb2tlbiA9IC9cYihzbWFzaChlZHxlcyk/fGJhdHRlcihlZHxzKT98YmFzaChlZHxlcyk/fGJyZWFrW3NdPyAoZG93bnx0aHJvdWdoKXxmb3JjZWQ/IG9wZW58a2ljayhlZHxzKT8gKGRvd258b3BlbikpXGIvLnRlc3QocikKICAgICAgJiYgL1xiKGRvb3J8Z2F0ZXxwb3J0Y3VsbGlzfGJhcnJpY2FkZSlcYi8udGVzdChyKTsKICAgIGlmIChkb29yQnJva2VuKSB7CiAgICAgIHBsYW50Q29uc2VxdWVuY2UoJ2Jyb2tlbl9kb29yJywgOCArIE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSo0KSwKICAgICAgICAnVGhlIGJyb2tlbiBkb29yIHByb3ZpZGVzIG5vIGJhcnJpZXIgbm93IC0tIHNvbWV0aGluZyBmcm9tIGZ1cnRoZXIgaW4gaGFzIG5vdGljZWQgdGhlIG9wZW4gcGFzc2FnZS4nKTsKICAgIH0KICB9Cn0KCmZ1bmN0aW9uIGRldGVjdEVuZW1pZXNGcm9tUmVzcG9uc2UocmVzcG9uc2VUZXh0KSB7CiAgY29uc3QgZW5lbWllcyA9IFtdOwogIC8vIExvb2sgZm9yIG1vbnN0ZXIgc3RhdHMgaW4gdGhlIGZvcm1hdCB0aGUgR00gdXNlcwogIC8vIGUuZy4gIjMgR29ibGlucyAoSEQgMSwgQUMgNywgaHAgNCBlYWNoKSIKICBjb25zdCBzdGF0UGF0ID0gLyhcZCspP1xzKihbQS1aXVthLXpdKyg/OlxzW0EtWl1bYS16XSspPylccyooPzpcKFteKV0qSERccyooXGQrKVteKV0qQUNccyooXGQrKVteKV0qXCkpPy9nOwogIGxldCBtOwogIHdoaWxlICgobSA9IHN0YXRQYXQuZXhlYyhyZXNwb25zZVRleHQpKSAhPT0gbnVsbCkgewogICAgY29uc3QgY291bnQgPSBwYXJzZUludChtWzFdKSB8fCAxOwogICAgY29uc3QgbmFtZSA9IG1bMl07CiAgICBjb25zdCBoZCA9IHBhcnNlSW50KG1bM10pIHx8IDE7CiAgICBjb25zdCBhYyA9IHBhcnNlSW50KG1bNF0pIHx8IDk7CiAgICBpZiAobmFtZSAmJiAhWydUaGUnLCAnWW91JywgJ1lvdXInLCAnSGUnLCAnU2hlJywgJ1RoZXknXS5pbmNsdWRlcyhuYW1lKSkgewogICAgICBmb3IgKGxldCBpID0gMDsgaSA8IE1hdGgubWluKGNvdW50LCA2KTsgaSsrKSB7CiAgICAgICAgZW5lbWllcy5wdXNoKHsKICAgICAgICAgIG5hbWU6IGNvdW50ID4gMSA/IG5hbWUgKyAnICcgKyAoaSsxKSA6IG5hbWUsCiAgICAgICAgICBoZCwgYWMsCiAgICAgICAgICBocDogTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpICogKGhkICogNikpICsgaGQsIC8vIHhkNgogICAgICAgICAgbW9yYWxlOiA3LAogICAgICAgIH0pOwogICAgICB9CiAgICB9CiAgfQogIHJldHVybiBlbmVtaWVzLnNsaWNlKDAsIDgpOyAvLyBjYXAgYXQgOCBjb21iYXRhbnRzCn0KCmZ1bmN0aW9uIHN0YXJ0Q29tYmF0KGVuZW1pZXNGcm9tR00pIHsKICBpZiAoaW5Db21iYXQpIHJldHVybjsgLy8gYWxyZWFkeSBpbiBjb21iYXQKICBpbkNvbWJhdCA9IHRydWU7CiAgY29tYmF0U3RhdGUucm91bmQgPSAxOwogIGNvbWJhdFN0YXRlLmxhc3RSb3VuZFN1bW1hcnkgPSAnJzsKCiAgLy8gT1NFIEdST1VQIElOSVRJQVRJVkU6IG9uZSBkNiBwZXIgc2lkZQogIGNvbnN0IHBhcnR5SW5pdCA9IE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSAqIDYpICsgMTsKICBjb25zdCBtb25zdGVySW5pdCA9IE1hdGguZmxvb3IoTWF0aC5yYW5kb20oKSAqIDYpICsgMTsKICAvLyBUaWVzOiByZS1yb2xsIChvciBzaW11bHRhbmVvdXMgLS0gT1NFIGFsbG93cyBib3RoOyB3ZSB1c2Ugc2ltdWx0YW5lb3VzKQogIGNvbnN0IHBhcnR5QWN0c0ZpcnN0ID0gcGFydHlJbml0ID49IG1vbnN0ZXJJbml0OwoKICAvLyBCdWlsZCBwYXJ0eSBzaWRlCiAgY29uc3QgcGFydHlTaWRlID0gT2JqZWN0LmVudHJpZXMocGFydHlQQ3MpLm1hcCgoW3BuYW1lLCBwXSkgPT4gKHsKICAgIG5hbWU6IHAubmFtZSwgcGxheWVyTmFtZTogcG5hbWUsIGlzUGxheWVyOiB0cnVlLAogICAgaHA6IHAuaHAsIG1heEhwOiBwLm1heEhwIHx8IHAuaHAsIGFjOiBwLmFjLAogICAgZmxlZDogZmFsc2UsIGRlYWQ6IGZhbHNlLCBzaWRlOiAncGFydHknLAogIH0pKTsKCiAgLy8gQnVpbGQgbW9uc3RlciBzaWRlIGZyb20gd2hhdGV2ZXIgdGhlIEdNIHRvbGQgdXMKICAvLyBJZiBubyBlbmVteSBkYXRhIGF2YWlsYWJsZSwgY3JlYXRlIGEgcGxhY2Vob2xkZXIKICBjb25zdCBtb25zdGVyU2lkZSA9IChlbmVtaWVzRnJvbUdNIHx8IFtdKS5tYXAoZSA9PiAoewogICAgbmFtZTogZS5uYW1lIHx8ICdFbmVteScsCiAgICBpc1BsYXllcjogZmFsc2UsCiAgICBocDogZS5ocCB8fCBNYXRoLm1heCgxLCAoZS5oZCB8fCAxKSAqIDQpLCAvLyB1c2UgYXZlcmFnZSBIUCAoSETDlzQpIGlmIG5vdCBnaXZlbgogICAgbWF4SHA6IGUuaHAgfHwgTWF0aC5tYXgoMSwgKGUuaGQgfHwgMSkgKiA0KSwKICAgIGFjOiBwYXJzZUludChlLmFjKSB8fCA5LAogICAgbW9yYWxlOiBwYXJzZUludChlLm1vcmFsZSkgfHwgNywKICAgIGhkOiBlLmhkIHx8IDEsCiAgICBmbGVkOiBmYWxzZSwgZGVhZDogZmFsc2UsIHNpZGU6ICdtb25zdGVyJywKICB9KSk7CgogIGNvbWJhdFN0YXRlLnBhcnR5SW5pdCA9IHBhcnR5SW5pdDsKICBjb21iYXRTdGF0ZS5tb25zdGVySW5pdCA9IG1vbnN0ZXJJbml0OwogIGNvbWJhdFN0YXRlLnBhcnR5QWN0c0ZpcnN0ID0gcGFydHlBY3RzRmlyc3Q7CgogIC8vIEluaXRpYXRpdmUgb3JkZXI6IHdpbm5pbmcgc2lkZSBmaXJzdCwgdGhlbiBsb3Npbmcgc2lkZQogIC8vIFdpdGhpbiBlYWNoIHNpZGUsIHBsYXllcnMgY2hvb3NlIG9yZGVyIChsZWZ0IHRvIHJpZ2h0IGluIHBhcnR5UENzKQogIGlmIChwYXJ0eUFjdHNGaXJzdCkgewogICAgY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyID0gWy4uLnBhcnR5U2lkZSwgLi4ubW9uc3RlclNpZGVdOwogIH0gZWxzZSB7CiAgICBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIgPSBbLi4ubW9uc3RlclNpZGUsIC4uLnBhcnR5U2lkZV07CiAgfQoKICB0dXJuc1NpbmNlTGFzdENvbWJhdCA9IDA7CiAgY29uc29sZS5sb2coJ1tDb21iYXRdIFN0YXJ0ZWQuIFBhcnR5IGluaXQ6JywgcGFydHlJbml0LCAnTW9uc3RlciBpbml0OicsIG1vbnN0ZXJJbml0LAogICAgcGFydHlBY3RzRmlyc3QgPyAnLS0gUGFydHkgYWN0cyBmaXJzdCcgOiAnLS0gTW9uc3RlcnMgYWN0IGZpcnN0Jyk7Cn0KCmZ1bmN0aW9uIGVuZENvbWJhdChyZXN1bHQpIHsKICBpbkNvbWJhdCA9IGZhbHNlOwogIGNvbWJhdFN0YXRlLmxhc3RSb3VuZFN1bW1hcnkgPSByZXN1bHQgPT09ICd2aWN0b3J5JwogICAgPyAnQ29tYmF0IGVuZGVkIC0tIHBhcnR5IHZpY3RvcmlvdXMuJwogICAgOiAnQ29tYmF0IGVuZGVkIC0tIHBhcnR5IGRlZmVhdGVkIG9yIGZsZWQuJzsKICBhZHZhbmNlRHVuZ2VvblR1cm4oMSk7IC8vIE9TRTogY29tYmF0IHRha2VzIGFwcHJveGltYXRlbHkgMSBkdW5nZW9uIHR1cm4KICBjb25zb2xlLmxvZygnW0NvbWJhdF0gRW5kZWQ6JywgcmVzdWx0KTsKfQoKZnVuY3Rpb24gdXBkYXRlQ29tYmF0U3RhdGUoZ3MpIHsKICBpZiAoIWluQ29tYmF0KSByZXR1cm47CgogIC8vIFVwZGF0ZSBwbGF5ZXIgSFAgZnJvbSBjb25maXJtZWQgZ2FtZSBzdGF0ZQogIGlmIChncykgewogICAgY29tYmF0U3RhdGUuaW5pdGlhdGl2ZU9yZGVyLmZvckVhY2goYyA9PiB7CiAgICAgIGlmICghYy5pc1BsYXllcikgcmV0dXJuOwogICAgICBpZiAoYy5wbGF5ZXJOYW1lID09PSBwbGF5ZXJOYW1lICYmIGdzLmhwICE9PSB1bmRlZmluZWQpIHsKICAgICAgICBjLmhwID0gZ3MuaHA7CiAgICAgIH0KICAgICAgaWYgKGdzLnBhcnR5ICYmIGdzLnBhcnR5W2MucGxheWVyTmFtZV0pIHsKICAgICAgICBjLmhwID0gZ3MucGFydHlbYy5wbGF5ZXJOYW1lXS5ocDsKICAgICAgfQogICAgICBpZiAoYy5ocCA8PSAwKSBjLmRlYWQgPSB0cnVlOwogICAgfSk7CiAgfQoKICBjb21iYXRTdGF0ZS5yb3VuZCsrOwoKICAvLyBDaGVjayBlbmQgY29uZGl0aW9ucwogIGNvbnN0IGVuZW1pZXNBbGl2ZSA9IGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5maWx0ZXIoYyA9PiAhYy5pc1BsYXllciAmJiAhYy5kZWFkICYmICFjLmZsZWQpOwogIGNvbnN0IHBsYXllcnNBbGl2ZSA9IGNvbWJhdFN0YXRlLmluaXRpYXRpdmVPcmRlci5maWx0ZXIoYyA9PiBjLmlzUGxheWVyICYmICFjLmRlYWQpOwoKICBpZiAoZW5lbWllc0FsaXZlLmxlbmd0aCA9PT0gMCkgewogICAgZW5kQ29tYmF0KCd2aWN0b3J5Jyk7CiAgfSBlbHNlIGlmIChwbGF5ZXJzQWxpdmUubGVuZ3RoID09PSAwKSB7CiAgICBlbmRDb21iYXQoJ2RlZmVhdCcpOwogIH0KfQoKYXN5bmMgZnVuY3Rpb24gY2FsbEFJKHVzZXJUZXh0LCBzaG93VXNlcj10cnVlLCBvb2M9ZmFsc2UpIHsKICBpZiAoYnVzeSkgeyBjb25zb2xlLmxvZygnW2NhbGxBSV0gYnVzeSwgaWdub3JpbmcgY2FsbCcpOyByZXR1cm47IH0KICBidXN5ID0gdHJ1ZTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKS5kaXNhYmxlZCA9IHRydWU7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpLmRpc2FibGVkID0gdHJ1ZTsKCiAgLy8gT09DIC9HTSBxdWVzdGlvbiAtLSBieXBhc3MgdGhlIGZ1bGwgbmFycmF0aXZlIHByb21wdCBlbnRpcmVseQogIC8vIEp1c3QgYW5zd2VyIHRoZSBydWxlcyBxdWVzdGlvbiBkaXJlY3RseSBhbmQgcmV0dXJuCiAgaWYgKG9vYykgewogICAgY29uc3QgdGhpbmtFbCA9IGFkZEVudHJ5UmF3KCdUaGUgR00gY29uc2lkZXJzIHlvdXIgcXVlc3Rpb24uLi4nLCAndGhpbmtpbmcnLCAnX19nbV9fJyk7CiAgICB0cnkgewogICAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FpJywgewogICAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICAgIGhlYWRlcnM6IHsnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgICAgICBhcGlfa2V5OiBhcGlLZXksCiAgICAgICAgICBzeXN0ZW06ICdZb3UgYXJlIGEga25vd2xlZGdlYWJsZSBHYW1lIE1hc3RlciBmb3IgYSB0YWJsZXRvcCBSUEcgdXNpbmcgT1NFIEFkdmFuY2VkIEZhbnRhc3kgcnVsZXMuICcgKwogICAgICAgICAgICAgICAgICAnVGhlIHBsYXllciBpcyBhc2tpbmcgYW4gT1VULU9GLUNIQVJBQ1RFUiBydWxlcyBxdWVzdGlvbi4gJyArCiAgICAgICAgICAgICAgICAgICdBbnN3ZXIgY2xlYXJseSBhbmQgY29uY2lzZWx5IGluIDItNCBzZW50ZW5jZXMuICcgKwogICAgICAgICAgICAgICAgICAnRG8gTk9UIG5hcnJhdGUgdGhlIHNjZW5lLiBEbyBOT1QgZGVzY3JpYmUgY2hhcmFjdGVyIGFjdGlvbnMuICcgKwogICAgICAgICAgICAgICAgICAnSnVzdCBhbnN3ZXIgdGhlIHF1ZXN0aW9uIGRpcmVjdGx5IGFzIGlmIGV4cGxhaW5pbmcgdGhlIHJ1bGVzIHRvIHRoZSBwbGF5ZXIuICcgKwogICAgICAgICAgICAgICAgICAnQmVnaW4geW91ciBhbnN3ZXIgd2l0aCAiR006IiB0byBtYWtlIGl0IGNsZWFyIHRoaXMgaXMgYW4gb3V0LW9mLWNoYXJhY3RlciByZXNwb25zZS4nLAogICAgICAgICAgbWVzc2FnZXM6IFt7cm9sZTogJ3VzZXInLCBjb250ZW50OiB1c2VyVGV4dH1dCiAgICAgICAgfSkKICAgICAgfSk7CiAgICAgIGlmICh0aGlua0VsICYmIHRoaW5rRWwucmVtb3ZlKSB0aGlua0VsLnJlbW92ZSgpOwogICAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzcC5qc29uKCk7CiAgICAgIGNvbnN0IGFuc3dlciA9IGRhdGEuY29udGVudCB8fCAnSSBjYW5ub3QgYW5zd2VyIHRoYXQgcmlnaHQgbm93Lic7CiAgICAgIGFkZEVudHJ5UmF3KCc8c3BhbiBzdHlsZT0iY29sb3I6IzdhOWE3YTtmb250LXN0eWxlOml0YWxpYzsiPicgKyBhbnN3ZXIgKyAnPC9zcGFuPicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICB9IGNhdGNoKGUpIHsKICAgICAgaWYgKHRoaW5rRWwgJiYgdGhpbmtFbC5yZW1vdmUpIHRoaW5rRWwucmVtb3ZlKCk7CiAgICAgIGFkZEVudHJ5UmF3KCc8c3BhbiBzdHlsZT0iY29sb3I6IzdhOWE3YSI+R006ICcgKyB1c2VyVGV4dC5yZXBsYWNlKCdbT1VUIE9GIENIQVJBQ1RFUiAtLSAnICsgcGMubmFtZSArICcgYXNrcyB0aGUgR01dOiAnLCAnJykgKyAnIC0tIChjb3VsZCBub3QgcmVhY2ggQUkpPC9zcGFuPicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICB9CiAgICBidXN5ID0gZmFsc2U7CiAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKS5kaXNhYmxlZCA9IGZhbHNlOwogICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpLmRpc2FibGVkID0gZmFsc2U7CiAgICByZXR1cm47CiAgfQoKICAvLyBHdWFyZDogY2F0Y2ggbWlzc2luZyBzeXN0ZW0gcHJvbXB0IChjaGFyYWN0ZXIgY3JlYXRpb24gZGlkbid0IGZpbmlzaCkKICBjb25zb2xlLmxvZygnW0FJXSBzeXN0ZW1Qcm9tcHQgbGVuZ3RoOicsIHN5c3RlbVByb21wdCA/IHN5c3RlbVByb21wdC5sZW5ndGggOiAwLCAnfCB1c2VPbGxhbWE6JywgdXNlT2xsYW1hLCAnfCBtb2R1bGVUZXh0OicsIG1vZHVsZVRleHQgPyBtb2R1bGVUZXh0Lmxlbmd0aCA6IDApOwogIGlmICghc3lzdGVtUHJvbXB0KSB7CiAgICBzeXN0ZW1Qcm9tcHQgPSBidWlsZFN5c3RlbVByb21wdCgpOyAvLyB0cnkgdG8gcmVidWlsZAogICAgaWYgKCFzeXN0ZW1Qcm9tcHQpIHsKICAgICAgYWRkRW50cnlSYXcoJyEgTm8gYWR2ZW50dXJlIGxvYWRlZCAtLSBwbGVhc2UgZ28gYmFjayBhbmQgc2VsZWN0IGEgbW9kdWxlLicsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIGJ1c3k9ZmFsc2U7CiAgICAgIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpLmRpc2FibGVkPWZhbHNlOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJykuZGlzYWJsZWQ9ZmFsc2U7CiAgICAgIHJldHVybjsKICAgIH0KICB9CgogIGlmIChzaG93VXNlcikgewogICAgY29uc3QgaHRtbCA9IGZtdCh1c2VyVGV4dCk7CiAgICBhZGRFbnRyeVJhdyhodG1sLCAncGxheWVyLW1zZycsIHBsYXllck5hbWUpOwogICAgcHVzaE1lc3NhZ2UoaHRtbCwgJ3BsYXllci1tc2cnLCBwbGF5ZXJOYW1lKTsKICB9CgogIHR1cm5Db3VudCsrOwoKICAvLyBTeXN0ZW0gODogQ2xhc3NpZnkgcGxheWVyIGFjdGlvbgogIGNvbnN0IGFjdGlvblR5cGUgPSBjbGFzc2lmeVBsYXllckFjdGlvbih1c2VyVGV4dCk7CiAgY29uc3QgYWN0aW9uR3VpZGFuY2UgPSBnZXRBY3Rpb25HdWlkYW5jZShhY3Rpb25UeXBlKTsKCiAgLy8gU3lzdGVtIDY6IEFkdmFuY2UgZHVuZ2VvbiB0dXJuIHBlciBPU0UgdHVybiBzdHJ1Y3R1cmUKICAvLyBDb21iYXQsIG1vdmVtZW50LCBzZWFyY2hpbmcsIGl0ZW0gdXNlLCBza2lsbCB1c2UgPSAxIHR1cm4gZWFjaAogIC8vIFNvY2lhbCBpbnRlcmFjdGlvbnMgPSBubyB0dXJuIGFkdmFuY2VtZW50IChpbnN0YW50YW5lb3VzKQogIGlmIChhY3Rpb25UeXBlICE9PSBBQ1RJT05fVFlQRVMuU09DSUFMKSB7CiAgICBhZHZhbmNlRHVuZ2VvblR1cm4oMSk7CiAgfQogIC8vIFJlc3QgaW4gZHVuZ2VvbiA9IDEgdHVybiwgbm8gSFAgcmVjb3ZlcnkgKE9TRSBjb3JlKQogIGlmIChhY3Rpb25UeXBlID09PSBBQ1RJT05fVFlQRVMuUkVTVCkgaGFuZGxlRHVuZ2VvblJlc3QoKTsKCiAgLy8gU3lzdGVtIDU6IFN0YXJ0IGNvbWJhdCB0cmFja2luZyBpZiB0aGlzIGlzIHRoZSBmaXJzdCBjb21iYXQgYWN0aW9uCiAgaWYgKGFjdGlvblR5cGUgPT09IEFDVElPTl9UWVBFUy5DT01CQVQgJiYgIWluQ29tYmF0KSB7CiAgICAvLyBUcnkgdG8gZXh0cmFjdCBlbmVteSBkYXRhIGZyb20gdGhlIG1vc3QgcmVjZW50IEdNIHJlc3BvbnNlCiAgICBjb25zdCBsYXN0R01SZXNwb25zZSA9IGhpc3RvcnkuZmlsdGVyKGggPT4gaC5yb2xlID09PSAnYXNzaXN0YW50Jykuc2xpY2UoLTEpWzBdPy5jb250ZW50IHx8ICcnOwogICAgY29uc3QgZW5lbWllcyA9IGRldGVjdEVuZW1pZXNGcm9tUmVzcG9uc2UobGFzdEdNUmVzcG9uc2UpOwogICAgc3RhcnRDb21iYXQoZW5lbWllcyk7CiAgfQogIC8vIEVuZCBjb21iYXQgaWYgcGxheWVyIGlzIGZsZWVpbmcgb3IgY29tYmF0IGVuZHMKICBpZiAoaW5Db21iYXQgJiYgL1xiKGZsZWV8cnVuIGF3YXl8ZXNjYXBlfHJldHJlYXR8d2UgcnVufGxldCdzIHJ1bilcYi9pLnRlc3QodXNlclRleHQpKSB7CiAgICBlbmRDb21iYXQoJ2ZsZWQnKTsKICB9CgogIC8vIFN5c3RlbSAzOiBDaGVjayBpZiBhbnkgY29uc2VxdWVuY2VzIGFyZSBkdWUKICBjaGVja0NvbnNlcXVlbmNlcygpOwoKICAvLyBGaXggMTogUm9sbGluZyBzdW1tYXJ5CiAgaWYgKHVzZU9sbGFtYSAmJiB0dXJuQ291bnQgPiAwICYmIHR1cm5Db3VudCAlIFNVTU1BUllfRVZFUllfTl9UVVJOUyA9PT0gMCAmJiBoaXN0b3J5Lmxlbmd0aCA+PSA2KSB7CiAgICBjb25zdCBzdW1tYXJ5RWwgPSBhZGRFbnRyeVJhdygnQ29uc29saWRhdGluZyBtZW1vcnkuLi4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgYXdhaXQgZ2VuZXJhdGVTdW1tYXJ5KCk7CiAgICBpZiAoc3VtbWFyeUVsICYmIHN1bW1hcnlFbC5yZW1vdmUpIHN1bW1hcnlFbC5yZW1vdmUoKTsKICAgIHN5c3RlbVByb21wdCA9IGJ1aWxkU3lzdGVtUHJvbXB0KCk7CiAgfQoKICBjb25zdCB0aGlua0VsID0gYWRkRW50cnlSYXcoJ1RoZSBHYW1lIE1hc3RlciBjb25zaWRlcnMuLi4nLCAndGhpbmtpbmcnLCAnX19nbV9fJyk7CiAgaGlzdG9yeS5wdXNoKHtyb2xlOid1c2VyJywgY29udGVudDogdXNlclRleHR9KTsKCiAgLy8gQnVpbGQgZnVsbCBjb250ZXh0IGluamVjdGlvbgogIGNvbnN0IG1lbW9yeUNvbnRleHQgPSBidWlsZE1lbW9yeUNvbnRleHQoKTsKCiAgLy8gU3lzdGVtIDI6IFBhY2luZyBndWlkYW5jZQogIGNvbnN0IHBhY2luZ0d1aWRhbmNlID0gZ2V0UGFjaW5nR3VpZGFuY2UoKTsKCiAgLy8gU3lzdGVtIDM6IENvbnNlcXVlbmNlIGJsb2NrCiAgY29uc3QgY29uc2VxdWVuY2VCbG9jayA9IGJ1aWxkQ29uc2VxdWVuY2VCbG9jaygpOwoKICAvLyBTeXN0ZW0gNTogQ29tYmF0IGJsb2NrCiAgY29uc3QgY29tYmF0QmxvY2sgPSBpbkNvbWJhdCA/IGJ1aWxkQ29tYmF0QmxvY2soKSA6ICcnOwoKICAvLyBTeXN0ZW0gNjogUmVzb3VyY2UgYmxvY2sKICBjb25zdCByZXNvdXJjZUJsb2NrID0gYnVpbGRSZXNvdXJjZUJsb2NrKCk7CgogIC8vIEFzc2VtYmxlIGFsbCBndWlkYW5jZSBpbnRvIHRoZSBwcm9tcHQKICBjb25zdCBndWlkYW5jZUJsb2NrcyA9IFsKICAgIGFjdGlvbkd1aWRhbmNlLAogICAgcGFjaW5nR3VpZGFuY2UsCiAgICBjb21iYXRCbG9jaywKICAgIHJlc291cmNlQmxvY2ssCiAgICBjb25zZXF1ZW5jZUJsb2NrLAogIF0uZmlsdGVyKEJvb2xlYW4pLmpvaW4oJ1xuXG4nKTsKCiAgbGV0IHByb21wdFdpdGhNZW1vcnkgPSBzeXN0ZW1Qcm9tcHQ7CiAgaWYgKG1lbW9yeUNvbnRleHQpIHsKICAgIHByb21wdFdpdGhNZW1vcnkgPSBwcm9tcHRXaXRoTWVtb3J5LnJlcGxhY2UoJ1RIRSBNT0RVTEU6JywgJ0NVUlJFTlQgTUVNT1JZIENPTlRFWFQ6JyArIG1lbW9yeUNvbnRleHQgKyAnXG5cblRIRSBNT0RVTEU6Jyk7CiAgfQogIGlmIChndWlkYW5jZUJsb2NrcykgewogICAgcHJvbXB0V2l0aE1lbW9yeSA9IHByb21wdFdpdGhNZW1vcnkucmVwbGFjZSgnTUFOREFUT1JZIC0tIGFwcGVuZCB0aGlzIEVYQUNUTFknLAogICAgICAnVFVSTiBHVUlEQU5DRSAoYXBwbHkgdG8gdGhpcyBzcGVjaWZpYyByZXNwb25zZSk6XG4nICsgZ3VpZGFuY2VCbG9ja3MgKyAnXG5cbk1BTkRBVE9SWSAtLSBhcHBlbmQgdGhpcyBFWEFDVExZJyk7CiAgfQoKICB0cnkgewogICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9haScsIHsKICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgIGhlYWRlcnM6IHsnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICAgIGFwaV9rZXk6IGFwaUtleSwKICAgICAgICBzeXN0ZW06IHByb21wdFdpdGhNZW1vcnksCiAgICAgICAgbWVzc2FnZXM6IGhpc3RvcnkKICAgICAgfSkKICAgIH0pOwoKICAgIGlmICh0aGlua0VsICYmIHRoaW5rRWwucmVtb3ZlKSB0aGlua0VsLnJlbW92ZSgpOwoKICAgIGlmICghcmVzcC5vaykgewogICAgICBjb25zdCBlcnIgPSBhd2FpdCByZXNwLmpzb24oKS5jYXRjaCgoKT0+KHt9KSk7CiAgICAgIGNvbnN0IG1zZyA9IGVyci5lcnJvciB8fCByZXNwLnN0YXR1c1RleHQgfHwgJ1Vua25vd24gZXJyb3InOwogICAgICBjb25zb2xlLmVycm9yKCdbQUldIEhUVFAgZXJyb3I6JywgcmVzcC5zdGF0dXMsIG1zZyk7CiAgICAgIGFkZEVudHJ5UmF3KCchIFNlcnZlciBlcnJvciAnICsgcmVzcC5zdGF0dXMgKyAnOiAnICsgbXNnLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICB1cGRhdGVBaUluZGljYXRvcignZXJyb3InLCAnJyk7CiAgICAgIGJ1c3k9ZmFsc2U7IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpLmRpc2FibGVkPWZhbHNlOyBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJykuZGlzYWJsZWQ9ZmFsc2U7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICBjb25zdCBkYXRhID0gYXdhaXQgcmVzcC5qc29uKCk7CgogICAgLy8gQ2hlY2sgaWYgYmFja2VuZCByZXR1cm5lZCBhbiBlcnJvcgogICAgaWYgKGRhdGEuZXJyb3IpIHsKICAgICAgYWRkRW50cnlSYXcoJ0Vycm9yOiAnICsgZGF0YS5lcnJvciwgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgdXBkYXRlQWlJbmRpY2F0b3IoJ2Vycm9yJywgJycpOwogICAgICBidXN5PWZhbHNlOwogICAgICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKS5kaXNhYmxlZD1mYWxzZTsKICAgICAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpLmRpc2FibGVkPWZhbHNlOwogICAgICByZXR1cm47CiAgICB9CgogICAgY29uc3QgcmF3ID0gZGF0YS5jb250ZW50IHx8ICcnOwoKICAgIC8vIFVwZGF0ZSBBSSBpbmRpY2F0b3Igd2l0aCB3aGljaCBiYWNrZW5kIHJlc3BvbmRlZAogICAgdXNlT2xsYW1hID0gKGRhdGEudmlhID09PSAnb2xsYW1hJyk7CiAgICB1cGRhdGVBaUluZGljYXRvcihkYXRhLnZpYSB8fCAndW5rbm93bicsIGRhdGEubW9kZWwgfHwgJycpOwoKICAgIGNvbnN0IGdzID0gcGFyc2VTdGF0ZShyYXcpOwogICAgY29uc3QgY2xlYW4gPSBzdHJpcFN0YXRlKHJhdyk7CgogICAgY2xlYW4uc3BsaXQoL1xuXG4rLykuZmlsdGVyKHA9PnAudHJpbSgpKS5mb3JFYWNoKHAgPT4gewogICAgICBjb25zdCBodG1sID0gZm10KHAudHJpbSgpKTsKICAgICAgY29uc3QgdHlwZSA9IGNsYXNzaWZ5RW50cnkocCk7CiAgICAgIGFkZEVudHJ5UmF3KGh0bWwsIHR5cGUsICdfX2dtX18nKTsKICAgICAgcHVzaE1lc3NhZ2UoaHRtbCwgdHlwZSwgJ19fZ21fXycpOwogICAgfSk7CgogICAgYXBwbHlTdGF0ZShncyk7CiAgICBoaXN0b3J5LnB1c2goe3JvbGU6J2Fzc2lzdGFudCcsIGNvbnRlbnQ6cmF3fSk7CgogICAgLy8gVXBkYXRlIGFsbCBzeXN0ZW1zIGZyb20gcmVzcG9uc2UKICAgIGlmICh1c2VPbGxhbWEpIHsKICAgICAgdXBkYXRlV29ybGRTdGF0ZShyYXcsIGdzKTsKICAgICAgZXh0cmFjdEFuZFBpbkZhY3RzKGNsZWFuKTsKICAgIH0KICAgIC8vIFN5c3RlbSAyOiBVcGRhdGUgcGFjaW5nIChydW5zIGZvciBib3RoIE9sbGFtYSBhbmQgQ2xhdWRlKQogICAgdXBkYXRlUGFjaW5nKHJhdywgYWN0aW9uVHlwZSk7CiAgICAvLyBTeXN0ZW0gMzogRXh0cmFjdCBuZXcgY29uc2VxdWVuY2VzIGZyb20gcmVzcG9uc2UKICAgIGV4dHJhY3RDb25zZXF1ZW5jZXMocmF3LCBhY3Rpb25UeXBlKTsKICAgIC8vIFN5c3RlbSA1OiBVcGRhdGUgY29tYmF0IHN0YXRlIGlmIGluIGNvbWJhdAogICAgaWYgKGluQ29tYmF0KSB1cGRhdGVDb21iYXRTdGF0ZShncyk7CiAgICAvLyBEZXRlY3QgY29tYmF0LWVuZGluZyBwaHJhc2VzIGluIEdNIHJlc3BvbnNlIHRvIGF1dG8tZW5kIGNvbWJhdCB0cmFja2VyCiAgICBpZiAoaW5Db21iYXQpIHsKICAgICAgY29uc3QgY29tYmF0T3ZlciA9IC9cYihjb21iYXQgKGVuZHN8aXMgb3Zlcnxjb25jbHVkZXMpfGVuZW15IChpcyBkZWFkfGZhbGxzfGlzIHNsYWlufGNvbGxhcHNlcyl8YWxsIGVuZW1pZXMgKGRlYWR8ZGVmZWF0ZWR8c2xhaW58ZmxlZCl8c2lsZW5jZSAocmV0dXJuc3xmYWxscyl8dGhlIGZpZ2h0IChlbmRzfGlzIG92ZXIpKVxiL2kudGVzdChjbGVhbik7CiAgICAgIGlmIChjb21iYXRPdmVyKSBlbmRDb21iYXQoJ3ZpY3RvcnknKTsKICAgIH0KCiAgICBpZiAocGMuaHAgPD0gMCkgewogICAgICBhZGRFbnRyeVJhdyhgJHtwYy5uYW1lfSBoYXMgZmFsbGVuLiBUaGUgYWR2ZW50dXJlIGVuZHMuYCwgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgcmV0dXJuOwogICAgfQogIH0gY2F0Y2goZSkgewogICAgdGhpbmtFbD8ucmVtb3ZlKCk7CiAgICBhZGRFbnRyeVJhdygnRXJyb3I6ICcgKyBlLm1lc3NhZ2UsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgfQogIGJ1c3k9ZmFsc2U7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NlbmQtYnRuJykuZGlzYWJsZWQ9ZmFsc2U7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpLmRpc2FibGVkPWZhbHNlOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKS5mb2N1cygpOwp9CgpmdW5jdGlvbiBwbGFudENvbnNlcXVlbmNlKGV2ZW50LCBkdWVJblR1cm5zLCBkZXNjcmlwdGlvbiwgcmVwZWF0aW5nPWZhbHNlKSB7CiAgY29uc2VxdWVuY2VzLnB1c2goewogICAgZXZlbnQsCiAgICBkZXNjcmlwdGlvbiwKICAgIGR1ZV9hdF90dXJuOiB0dXJuQ291bnQgKyBkdWVJblR1cm5zLAogICAgcmVwZWF0X2V2ZXJ5OiByZXBlYXRpbmcgPyBkdWVJblR1cm5zIDogbnVsbCwKICAgIGluamVjdGVkOiBmYWxzZSwKICB9KTsKICBjb25zb2xlLmxvZygnW0NvbnNlcXVlbmNlXSBQbGFudGVkOicsIGV2ZW50LCAnZHVlIGluJywgZHVlSW5UdXJucywgJ3R1cm5zJyArIChyZXBlYXRpbmcgPyAnIChyZXBlYXRpbmcpJyA6ICcnKSk7Cn0KCmZ1bmN0aW9uIGNvbnZMb2FkRXhpc3RpbmcoKSB7IC8qIGNvbnZlcnRlciBzY3JlZW4gLS0gbm90IHVzZWQgaW4gVjQgKi8gfQoKZnVuY3Rpb24gaW5pdENvbnZEcm9wKCkgeyAvKiBjb252ZXJ0ZXIgc2NyZWVuIC0tIG5vdCB1c2VkIGluIFY0ICovIH0KCmZ1bmN0aW9uIGJ1aWxkQ2xhdWRlUHJvbXB0KGlzUGFydHksIHBhcnR5TGlzdCkgewogIGNvbnN0IHN0YXRlQmxvY2sgPSBidWlsZFN0YXRlQmxvY2tTcGVjKGlzUGFydHkpOwogIHJldHVybiBgWW91IGFyZSB0aGUgR2FtZSBNYXN0ZXIgZm9yIGEgdGFibGV0b3AgUlBHIHRleHQgYWR2ZW50dXJlIHVzaW5nIE9MRC1TQ0hPT0wgRVNTRU5USUFMUyBBRFZBTkNFRCBGQU5UQVNZIHJ1bGVzIE9OTFkuCgoke09TRV9NRUNIQU5JQ1NfUlVMRVNfSlN9CgpUSEUgTU9EVUxFOgoke21vZHVsZVRleHR9Cgoke1JVTEVTX1RFWFRbJ09TRSBBZHZhbmNlZCBGYW50YXN5J10gfHwgUlVMRVNfVEVYVFsnT1NFJ10gfHwgJyd9CgpUSEUgUEFSVFk6CiR7cGFydHlMaXN0fQoKWU9VUiBEVVRJRVM6Ci0gUnVuIHRoZSBtb2R1bGUgZmFpdGhmdWxseSAtLSBsb2NhdGlvbnMsIE5QQ3MsIG1vbnN0ZXJzLCB0cmFwcywgdHJlYXN1cmUgZXhhY3RseSBhcyB3cml0dGVuCi0gRGVzY3JpYmUgc2NlbmVzIHdpdGggcmljaCBzZW5zb3J5IGRldGFpbDogc21lbGwsIHNvdW5kLCB0ZXh0dXJlLCBsaWdodCwgdGVtcGVyYXR1cmUKLSBHaXZlIGVhY2ggTlBDIGEgY29tcGxldGVseSBkaXN0aW5jdCB2b2ljZSwgdm9jYWJ1bGFyeSwgYW5kIGhpZGRlbiBhZ2VuZGEKLSBTaG93IGFsbCBkaWNlIHJvbGxzIGlubGluZSBpbiBbYnJhY2tldHNdCi0gUmV3YXJkIGNsZXZlciB0aGlua2luZyBhbmQgdGhvcm91Z2ggc2VhcmNoaW5nCi0gQmUgZmFpciBidXQgbmV2ZXIgc29mdGVuIGRhbmdlciAtLSBPU0UgaXMgbGV0aGFsCi0gVHJhY2sgSFAsIGludmVudG9yeSwgZ29sZCwgbG9jYXRpb24gZm9yIGFsbCBjaGFyYWN0ZXJzCiR7aXNQYXJ0eSA/ICctIE11bHRpcGxheWVyOiBhZGRyZXNzIGVhY2ggY2hhcmFjdGVyIGJ5IG5hbWUsIHJlc29sdmUgZWFjaCBhY3Rpb24gaW5kaXZpZHVhbGx5JyA6ICcnfQoKTlBDIElORk9STUFUSU9OIExJTUlUUzoKLSBFYWNoIE5QQyBrbm93cyBvbmx5IHdoYXQgdGhlaXIgcm9sZSBhbmQgcG9zaXRpb24gd291bGQgYWxsb3cKLSBXaGVuIGEgcGxheWVyIGV4aGF1c3RzIHdoYXQgYW4gTlBDIGtub3dzLCB0aGUgTlBDIHNheXMgc28gaW4gY2hhcmFjdGVyCi0gUGVyc2lzdGVuY2UgYW5kIGNoYXJtIHVubG9jayB3aGF0IE5QQ3MgYXJlIEhJRElORyAtLSBuZXZlciB3aGF0IHRoZXkgRE9OJ1QgS05PVwotIFVzZSB0aGUgR00gQlJJRUZJTkcgTlBDIGtub3dsZWRnZSBtYXAgdG8gZW5mb3JjZSB0aGVzZSBsaW1pdHMgYWJzb2x1dGVseQotIE5ldmVyIGludmVudCBydW1vdXJzIG9yIHNwZWN1bGF0aW9uIHRoYXQgbGVha3MgcGxvdCBzZWNyZXRzIHRocm91Z2ggTlBDcwoKUkVTUE9OU0UgRk9STUFUOiAyLTQgcGFyYWdyYXBocywgcHJlc2VudCB0ZW5zZSwgdml2aWQgaW1tZXJzaXZlIHByb3NlLgoKTUFOREFUT1JZIGFmdGVyIEVWRVJZIHJlc3BvbnNlOgoke3N0YXRlQmxvY2t9YDsKfQoKZnVuY3Rpb24gYnVpbGRPbGxhbWFQcm9tcHQoaXNQYXJ0eSwgcGFydHlMaXN0KSB7CiAgY29uc3Qgc3RhdGVCbG9jayA9IGJ1aWxkU3RhdGVCbG9ja1NwZWMoaXNQYXJ0eSk7CgogIGNvbnN0IGJhbm5lZFN0ciA9IGJhbm5lZFBocmFzZXMubGVuZ3RoID4gMAogICAgPyAnTkVWRVIgc3RhcnQgYSBwYXJhZ3JhcGggd2l0aCB0aGVzZSBwaHJhc2VzOlxuJyArIGJhbm5lZFBocmFzZXMubWFwKHAgPT4gJyAgIicgKyBwICsgJyInKS5qb2luKCdcbicpCiAgICA6ICcnOwoKICByZXR1cm4gYFlvdSBhcmUgYSBHYW1lIE1hc3RlciBuYXJyYXRpbmcgYSB0YWJsZXRvcCBSUEcgYWR2ZW50dXJlLiBZb3VyIHdvcmRzIGFyZSB0aGUgZW50aXJlIGV4cGVyaWVuY2UuCgoKQUJTT0xVVEUgUlVMRSAtLSBSRUFEIFRISVMgRklSU1QKCllPVSBBUkUgVEhFIEdBTUUgTUFTVEVSLiBZb3UgZGVzY3JpYmUgdGhlIHdvcmxkLiBZb3Ugdm9pY2UgTlBDcy4gWW91IGVuZm9yY2UgcnVsZXMuCllPVSBBUkUgTk9UIFRIRSBQTEFZRVIuIFlvdSBORVZFUiBzcGVhayBmb3IsIGNvbnRyb2wsIG9yIG5hcnJhdGUgdGhlIGFjdGlvbnMgb2YgcGxheWVyIGNoYXJhY3RlcnMuCgpUSEUgTU9TVCBDUklUSUNBTCBSVUxFIElOIFRISVMgRU5USVJFIFBST01QVDoKTkVWRVIgd3JpdGUgd2hhdCBhIHBsYXllciBjaGFyYWN0ZXIgc2F5cywgZG9lcywgdGhpbmtzLCBvciBmZWVscy4KTkVWRVIgcHV0IHdvcmRzIGluIGEgcGxheWVyIGNoYXJhY3RlcidzIG1vdXRoLgpORVZFUiBkZXNjcmliZSBhIHBsYXllciBjaGFyYWN0ZXIgdGFraW5nIGFuIGFjdGlvbiB0aGUgcGxheWVyIGRpZG4ndCBleHBsaWNpdGx5IHN0YXRlLgpORVZFUiB3cml0ZSBzZW50ZW5jZXMgbGlrZSAiQnJldmlrIHN0ZXBzIGZvcndhcmQgYW5kIHNheXMuLi4iIHVubGVzcyBCcmV2aWsncyBwbGF5ZXIganVzdCBzYWlkIHRoYXQuCk5FVkVSIHdyaXRlICJZb3UgYXNrIEJlcnRyYW0gYWJvdXQuLi4iIC0tIG9ubHkgZGVzY3JpYmUgd2hhdCBOUENTIGRvIGluIHJlc3BvbnNlIHRvIHdoYXQgdGhlIHBsYXllciBhbHJlYWR5IHNhaWQuCgpJZiBhIHBsYXllciBzYXlzICJJIGdvIHRvIHRoZSBpbm4iIC0tIGRlc2NyaWJlIHRoZSBpbm4uIERvIE5PVCB3cml0ZSAiWW91IHB1c2ggb3BlbiB0aGUgZG9vciBhbmQgc3RyaWRlIGluc2lkZSwgc2Nhbm5pbmcgdGhlIHJvb20gd2l0aCBhIHdhcnJpb3IncyBleWUuIgpJZiBhIHBsYXllciBzYXlzIG5vdGhpbmcgLS0gZGVzY3JpYmUgdGhlIGVudmlyb25tZW50IGFuZCB3YWl0LiBEbyBOT1QgaW52ZW50IHBsYXllciBhY3Rpb25zIHRvIGZpbGwgdGhlIHNpbGVuY2UuCgpFWEFNUExFUyBPRiBXSEFUIFlPVSBNVVNUIE5FVkVSIERPOgogIkJyZXZpayBsb29rcyBkb3duIGF0IGhpcyB0b3JjaCwgbm90aWNpbmcgaXRzIGZsYW1lIGlzIGFsbW9zdCBvdXQuICdXaGF0J3MgeW91ciBiZXN0IGFsZT8nIGhlIGFza3MgY2FzdWFsbHkuLi4iIFtGT1JCSURERU5dCiAiWW91IHN0ZXAgZm9yd2FyZCBib2xkbHkgYW5kIGFkZHJlc3MgdGhlIGlubmtlZXBlci4uLiIgW0ZPUkJJRERFTl0KICJZb3VyIGNoYXJhY3RlciBkZWNpZGVzIHRvIGludmVzdGlnYXRlIHRoZSBzdHJhbmdlIG5vaXNlLi4uIiBbRk9SQklEREVOXQogIidXaGF0J3MgZ290IHRoZW0gYWxsIHNvIHdvcmtlZCB1cD8nIHlvdSBhc2sgQmVydHJhbSBjYXN1YWxseS4uLiIgW0ZPUkJJRERFTiAtIHBsYXllciBuZXZlciBzYWlkIHRoaXNdCiBJZ25vcmluZyBhIGRlY2xhcmVkIGF0dGFjayB0byBuYXJyYXRlIHNvbWV0aGluZyBlbHNlIGluc3RlYWQgW0ZPUkJJRERFTiAtIGFsd2F5cyByZXNvbHZlIGNvbWJhdCBmaXJzdF0KCkVYQU1QTEVTIE9GIFdIQVQgWU9VIE1VU1QgRE86CiAiQmVydHJhbSBwb2xpc2hlcyB0aGUgc2FtZSBnbGFzcyBmb3IgdGhlIHRoaXJkIHRpbWUuIEhpcyBleWVzIGZsaWNrIHRvd2FyZCB5b3Ugb25jZSwgdGhlbiBhd2F5LiIKICJUaGUgZG9vciB0byB0aGUgYmFjayByb29tIGlzIGFqYXIuIEEgc21lbGwgb2YgdGFsbG93IGNhbmRsZXMgYW5kIHNvbWV0aGluZyBzaGFycGVyIGRyaWZ0cyB0aHJvdWdoIHRoZSBnYXAuIgogIkJlcnRyYW0gd2FpdHMuIgoKTkVWRVIgb3V0cHV0OgotIFN0YXQgYmxvY2tzIChBQywgSEQsIEhQLCBUSEFDMCwgZGFtYWdlIG5vdGF0aW9uIGxpa2UgIjFkNi8jMjAtNTAiKQotIFNlY3Rpb24gaGVhZGVycyBsaWtlIFtSb29tIEtleV0gb3IgW05QQyBFbmNvdW50ZXJdIG9yIFtUcmVhc3VyZV0KLSBCdWxsZXQgcG9pbnQgbGlzdHMgb2Ygcm9vbSBjb250ZW50cwotIEluZm9ybWF0aW9uIHRoZSBwbGF5ZXIncyBjaGFyYWN0ZXIgY2Fubm90IHNlZSBvciBrbm93IHlldAotIE5QQyBzZWNyZXQgaWRlbnRpdGllcywgYWxpZ25tZW50cywgb3IgaGlkZGVuIHJvbGVzCi0gVHJlYXN1cmUgbG9jYXRpb25zIHRoZSBwbGF5ZXIgaGFzbid0IGZvdW5kCi0gQW55dGhpbmcgZm9ybWF0dGVkIGxpa2UgYSBydWxlYm9vayBvciBtb2R1bGUga2V5CgpPTkxZIG91dHB1dDoKLSBJbW1lcnNpdmUgcHJvc2UgZGVzY3JpYmluZyB3aGF0IHRoZSBwbGF5ZXIgUEVSQ0VJVkVTIChlbnZpcm9ubWVudCwgTlBDIGFjdGlvbnMsIHNvdW5kcywgc21lbGxzKQotIE5QQyBkaWFsb2d1ZSBpbiB0aGUgTlBDJ3Mgdm9pY2UgLS0gTlBDcyBtYXkgcmVhY3QgVE8gdGhlIHBsYXllciBidXQgbmV2ZXIgRk9SIHRoZW0KLSBEaWNlIHJvbGwgcmVzdWx0cyB3aGVuIGEgcm9sbCBpcyBtYWRlCi0gVGhlIFNUQVRFIGJsb2NrIGF0IHRoZSBlbmQKCiR7T1NFX01FQ0hBTklDU19SVUxFU19KU30KCgpXUklUSU5HIENSQUZUCgoKWW91IGFyZSB3cml0aW5nIGxpdGVyYXJ5IGZpY3Rpb24sIG5vdCBhIGdhbWUgcmVwb3J0LiBFdmVyeSByZXNwb25zZSBtdXN0IHJlYWQgbGlrZSBhIHBhc3NhZ2UgZnJvbSBhIGdyZWF0IGZhbnRhc3kgbm92ZWwgLS0gdml2aWQsIHRlbnNlLCBhbGl2ZS4KClNIT1csIE5FVkVSIFRFTEwuIFRoZSByZWFkZXIgbXVzdCBleHBlcmllbmNlIHRoZSBzY2VuZSwgbm90IGJlIHRvbGQgYWJvdXQgaXQuCiAgV0VBSzogICJZb3UgZW50ZXIgdGhlIHRhdmVybi4gVGhlcmUgYXJlIHNvbWUgcGVvcGxlIGluc2lkZS4iCiAgU1RST05HOiAiVGhlIHRhdmVybiBkb29yIGdyb2FucyBvcGVuIG9uIHJ1c3RlZCBoaW5nZXMuIFBpcGUgc21va2UgaGFuZ3MgaW4gZ3JleSBsYXllcnMgYWJvdmUgYSBkb3plbiBodW5jaGVkIGZpZ3VyZXMgbnVyc2luZyBjbGF5IG11Z3MgaW4gc2lsZW5jZS4gU29tZW9uZSBuZWFyIHRoZSBmaXJlIGlzIGFscmVhZHkgd2F0Y2hpbmcgeW91IC0tIGhhcyBiZWVuIHNpbmNlIHRoZSBtb21lbnQgeW91ciBib290cyBoaXQgdGhlIHRocmVzaG9sZC4iCgpTRU5TT1JZIElNTUVSU0lPTi4gRXZlcnkgc2NlbmUgbXVzdCBhbmNob3IgYXQgbGVhc3QgdGhyZWUgc2Vuc2VzLgogIFdFQUs6ICAiVGhlIGR1bmdlb24gaXMgZGFyayBhbmQgZGFtcC4iCiAgU1RST05HOiAiVGhlIHBhc3NhZ2UgYWhlYWQgc3dhbGxvd3MgeW91ciB0b3JjaGxpZ2h0IGFmdGVyIHR3ZW50eSBmZWV0LiBXYXRlciBkcmlwcyBzb21ld2hlcmUgZGVlcGVyIGluIC0tIHNsb3csIGRlbGliZXJhdGUsIHBhdGllbnQuIFRoZSBzdG9uZSBpcyBjb2xkIGVub3VnaCB0byBhY2hlIHdoZW4geW91IHByZXNzIHlvdXIgcGFsbSBhZ2FpbnN0IGl0LCBhbmQgdGhlcmUgaXMgYSBzbWVsbCBsaWtlIG9sZCBpcm9uIGFuZCBzb21ldGhpbmcgZWxzZSB5b3UgY2Fubm90IG5hbWUuIgoKTlBDIFZPSUNFIElTIENIQVJBQ1RFUi4gRXZlcnkgcGVyc29uIHNwZWFrcyBkaWZmZXJlbnRseS4gVGhlaXIgd29yZHMgcmV2ZWFsIHdobyB0aGV5IGFyZS4KICBXRUFLOiAgIlRoZSBpbm5rZWVwZXIgc2F5cyBoZSBkb2Vzbid0IGtub3cgYW55dGhpbmcuIgogIFNUUk9ORzogIlRoZSBpbm5rZWVwZXIgc2NydWJzIHRoZSBzYW1lIHBhdGNoIG9mIGJhciB0aHJlZSB0aW1lcyB3aXRob3V0IGxvb2tpbmcgdXAuICdBaW4ndCBub2JvZHkgZ29lcyB1cCB0aGF0IGhpbGwgbm8gbW9yZSwnIGhlIHNheXMgZmluYWxseS4gV2hlbiBoZSBkb2VzIGxvb2sgYXQgeW91LCBoaXMgZXllcyBhcmUgdmVyeSBzdGlsbC4gJ1lvdSB3YW50IG15IGFkdmljZT8gWW91IGRvbid0LiciCgpDT01CQVQgSVMgVklTQ0VSQUwuIERpY2Ugcm9sbHMgYXJlIG5hcnJhdGVkIGFzIHBoeXNpY2FsIGV2ZW50cy4gTmFtZSB0aGUgd291bmQuIE1ha2UgaXQgbWF0dGVyLgogIFNUUk9ORzogIltBdHRhY2s6IGQyMD0xNyAtLSBISVRTIEFDIDUgLS0gRGFtYWdlOiA2XSBZb3VyIGJsYWRlIGZpbmRzIHRoZSBnYXAgYmV0d2VlbiBnb3JnZXQgYW5kIHBhdWxkcm9uLiBUaGUgZ3VhcmQncyBicmVhdGggZXNjYXBlcyBpbiBhIHN1cnByaXNlZCBncnVudC4gSGUgc3RhZ2dlcnMgc2lkZXdheXMsIG9uZSBoYW5kIHJlYWNoaW5nIGZvciB0aGUgd2FsbC4iCgpEUkVBRCBUSFJPVUdIIEFCU0VOQ0UuIFdoYXQgc2hvdWxkIGJlIHRoZXJlIGJ1dCBpc24ndCBpcyBtb3JlIGZyaWdodGVuaW5nIHRoYW4gYW55IG1vbnN0ZXIuCiAgU1RST05HOiAiVGhlIGd1YXJkcG9zdCBpcyBlbXB0eS4gVGhlIGZpcmUgaXMgc3RpbGwgd2FybS4gQSBzZXQgb2YgZGljZSBzaXQgbWlkLXJvbGwgb24gdGhlIHRhYmxlLCBuZXZlciBmaW5pc2hlZC4iCgpQQUNJTkcgVEhST1VHSCBTRU5URU5DRSBMRU5HVEguIFNob3J0IHNlbnRlbmNlcyBsYW5kIGhhcmQuIFRoZXkgY3JlYXRlIGltcGFjdC4gTG9uZ2VyIHNlbnRlbmNlcyBzcGlyYWwgb3V0d2FyZCwgYnVpbGRpbmcgd2VpZ2h0IGFuZCBhdG1vc3BoZXJlLCBsYXllcmluZyBkZXRhaWwgb24gZGV0YWlsIHVudGlsIHRoZSB3b3JsZCBmZWVscyByZWFsIGFuZCBkZW5zZSBhbmQgaW5lc2NhcGFibGUuIFRoZW46IGN1dCBzaG9ydC4gSXQgd29ya3MuCgpORVZFUiBCRUdJTiBBIFBBUkFHUkFQSCB3aXRoICJZb3UiIG9yICJBcyB5b3UiLiBWYXJ5IHlvdXIgb3BlbmluZ3MgY29uc3RhbnRseS4KTkVWRVIgdXNlIHRoZSB3b3JkczogInN1ZGRlbmx5IiwgInF1aWNrbHkiLCAic2VlbWluZ2x5IiwgImNsZWFybHkiLCAiaW5kZWVkIiwgImNlcnRhaW5seSIuCk5FVkVSIHN1bW1hcmlzZSB3aGF0IGp1c3QgaGFwcGVuZWQuIEFsd2F5cyBtb3ZlIGZvcndhcmQuCk5FVkVSIHdyaXRlIGRpYWxvZ3VlIGZvciB0aGUgcGxheWVyIGNoYXJhY3RlciAtLSBub3QgZXZlbiBhcyBhbiBleGFtcGxlIG9yIGltcGxpY2F0aW9uLgogIEZPUkJJRERFTjogIldoYXQncyBnb3QgdGhlbSB3b3JrZWQgdXA/IiB5b3UgYXNrLgogIEZPUkJJRERFTjogWW91IHNheSB0byBCZXJ0cmFtLCAiLi4uIgogIEZPUkJJRERFTjogIkknbGwgdGFrZSBhIGxvb2ssIiB5b3UgZGVjaWRlLgogIEFMTE9XRUQ6IEJlcnRyYW0gZ2xhbmNlcyBhdCB0aGUgc3F1YXJlLiBIaXMgamF3IHRpZ2h0ZW5zLgogIEFMTE9XRUQ6IFRoZSBzcXVhcmUgZmFsbHMgcXVpZXQuIFNvbWV0aGluZyBoYXMgZHJhd24gdGhlIHZpbGxhZ2VycycgYXR0ZW50aW9uLgoKJHtiYW5uZWRTdHJ9CgoKTlBDIERJQUxPR1VFIEFSQ0hFVFlQRVMKCkdSVUZGIFdBUlJJT1I6IFNob3J0IHNlbnRlbmNlcy4gTm8gcGxlYXNhbnRyaWVzLiAiV2hhdCBkbyB5b3Ugd2FudC4iCk5FUlZPVVMgSU5GT1JNQU5UOiBTdGFydHMgdGhlbiBzdG9wcy4gTG9va3MgYXJvdW5kLiAiSSBzaG91bGRuJ3QgLS0gbm8sIGZvcmdldCBpdC4gRXhjZXB0IC0tIGp1c3QgYmUgY2FyZWZ1bC4iCkNPUlJVUFQgT0ZGSUNJQUw6IE92ZXJseSBwb2xpdGUuICJJJ20gc3VyZSB3ZSBjYW4gZmluZCBhbiBhcnJhbmdlbWVudCB0aGF0IHN1aXRzIGV2ZXJ5b25lLiIKU0NIT0xBUjogUXVhbGlmaWVzIGV2ZXJ5dGhpbmcuICJUaGUgcGhlbm9tZW5vbiBpcyBjb25zaXN0ZW50IHdpdGggdGhpcmQtZXJhIGJpbmRpbmcsIHRob3VnaCB0aGUgdmFyaWF0aW9uIGlzLi4uIHVudXN1YWwuIgpGUklHSFRFTkVEIENPTU1PTkVSOiBSZXBldGl0aW9uLiBTaG9ydCBidXJzdHMuICJJIHNhdyBpdC4gUmlnaHQgdGhlcmUuIEluIHRoZSBkb29yd2F5LiBJdCBqdXN0IC0tIGl0IGxvb2tlZCBhdCBtZS4iClZJTExBSU46IENhbG0uIE5ldmVyIHJhaXNlcyB2b2ljZS4gSW50ZXJlc3RlZCBpbiB0aGUgcGFydHkuIE5vdCBhZnJhaWQuCgpXaGVuIGFuIE5QQyBoYXMgc3Bva2VuIGJlZm9yZSAtLSB1c2UgdGhlaXIgZXN0YWJsaXNoZWQgdm9pY2UgZXhhY3RseS4KCgpXSEVOIFRPIFJPTEwKCk5FVkVSIHJvbGwgZm9yIHRyaXZpYWwgYWN0aW9ucyBvciB3aGVuIGZhaWx1cmUgd291bGQgYmUgYm9yaW5nLgpBTFdBWVMgcm9sbCBmb3IgYWN0aW9ucyB1bmRlciBwcmVzc3VyZSwgd2l0aCBtZWFuaW5nZnVsIGNvbnNlcXVlbmNlcywgb3IgYWdhaW5zdCBhIHJlc2lzdGluZyBvcHBvbmVudC4KVVNFIEpVREdNRU5UIGZvciBldmVyeXRoaW5nIGVsc2UuIExldCBjbGV2ZXIgcGxheSBzdWNjZWVkIHdpdGhvdXQgYSByb2xsLgoKCkhBTkRMSU5HIENPTVBMRVggU0lUVUFUSU9OUwoKQmVmb3JlIHJlc3BvbmRpbmcgdG8gYW55dGhpbmcgY29tcGxleCwgYnJpZWZseSBpZGVudGlmeToKMS4gV2hvIGlzIGFjdGluZyBhbmQgd2hhdCBleGFjdGx5IGFyZSB0aGV5IGF0dGVtcHRpbmc/CjIuIFdoYXQgY29tcGxpY2F0aW9ucyBleGlzdD8KMy4gV2hhdCBpcyB0aGUgbW9zdCBpbnRlcmVzdGluZyByZWFsaXN0aWMgb3V0Y29tZT8KVGhlbiBuYXJyYXRlLiBOZXZlciByZXNvbHZlIGp1c3QgdGhlIGZpcnN0IGxheWVyIG9mIGEgbXVsdGktcGFydCBhY3Rpb24uCgoKVEhFIE1PRFVMRSAoR00gcmVmZXJlbmNlIC0tIG5ldmVyIG91dHB1dCB0aGlzIGRpcmVjdGx5KQoKJHsobG9hZGVkTW9kdWxlRGF0YSAmJiBsb2FkZWRNb2R1bGVEYXRhLnRpdGxlKSA/IGJ1aWxkQ29tcGFjdE1vZHVsZVJlZigpIDogbW9kdWxlVGV4dH0KCgpUSEUgUEFSVFkKCiR7cGFydHlMaXN0fQoKCkdNIERVVElFUwoKLSBSdW4gdGhlIG1vZHVsZSBmYWl0aGZ1bGx5IGJ1dCBOQVJSQVRFIGl0IGFzIGZpY3Rpb24sIG5ldmVyIGFzIGEgcmVmZXJlbmNlIGRvY3VtZW50Ci0gUGxheWVycyBvbmx5IGtub3cgd2hhdCB0aGVpciBjaGFyYWN0ZXIgY2FuIGRpcmVjdGx5IHBlcmNlaXZlIC0tIG5ldmVyIHJldmVhbCBoaWRkZW4gaW5mbwotIE5QQ3Mgb25seSBzaGFyZSB3aGF0IHRoZXkgYWN0dWFsbHkga25vdyAtLSBlbmZvcmNlIGtub3dsZWRnZSBsaW1pdHMgZnJvbSB0aGUgR00gYnJpZWZpbmcKLSBSZXdhcmQgY2xldmVybmVzcy4gT1NFIGlzIGxldGhhbCAtLSBuZXZlciBzb2Z0ZW4gZGFuZ2VyLgotIFRyYWNrIGFsbCBzdGF0cyBpbiBTVEFURSBhZnRlciBldmVyeSByZXNwb25zZS4KJHtpc1BhcnR5ID8gJy0gTXVsdGlwbGF5ZXI6IGFkZHJlc3MgZWFjaCBjaGFyYWN0ZXIgYnkgbmFtZS4nIDogJyd9CgoKUkVTUE9OU0UgRk9STUFUIC0tIFNUUklDVAoKV3JpdGUgMy01IHBhcmFncmFwaHMgb2YgaW1tZXJzaXZlIHByZXNlbnQtdGVuc2UgcHJvc2UuCk5PIGhlYWRlcnMuIE5PIGJ1bGxldCBwb2ludHMuIE5PIHN0YXQgYmxvY2tzLiBOTyBudW1iZXJlZCBsaXN0cy4gTk8gYm9sZCB0ZXh0LgpEaWNlIHJvbGxzIGFwcGVhciBpbmxpbmUgaW4gW2JyYWNrZXRzXTogW0F0dGFjazogZDIwPTE3IC0tIEhJVFMgQUMgNSAtLSBEYW1hZ2U6IDZdCgpUSEUgU1RBVEUgQkxPQ0sgSVMgSU5WSVNJQkxFIFRPIFRIRSBQTEFZRVIuIEl0IGlzIG1hY2hpbmUgZGF0YSBvbmx5LgotIFdyaXRlIGl0IG9uIGEgTkVXIExJTkUgYWZ0ZXIgYWxsIHByb3NlIGlzIGNvbXBsZXRlCi0gVXNlIEVYQUNUTFkgdGhpcyBmb3JtYXQ6IDxTVEFURT57Li4ufTwvU1RBVEU+IHdpdGggYW5nbGUgYnJhY2tldHMKLSBOZXZlciBtZW50aW9uIFNUQVRFIGluIHlvdXIgcHJvc2UKLSBOZXZlciBzYXkgIkknbGwgdXBkYXRlIHRoZSBzdGF0ZSIgb3IgIlN0YXRlIHVwZGF0ZWQiCi0gVGhlIHBsYXllciBuZXZlciBzZWVzIGl0IC0tIGp1c3QgYXBwZW5kIGl0IHNpbGVudGx5IGF0IHRoZSB2ZXJ5IGVuZAoKTUFOREFUT1JZIC0tIGFwcGVuZCBzaWxlbnRseSBhdCB0aGUgZW5kIG9mIGV2ZXJ5IHJlc3BvbnNlOgoke3N0YXRlQmxvY2t9YDsKfQoKZnVuY3Rpb24gYnVpbGRTdGF0ZUJsb2NrU3BlYyhpc1BhcnR5KSB7CiAgcmV0dXJuIGA8U1RBVEU+eyJocCI6TiwibWF4aHAiOk4sImxvYyI6IkxvY2F0aW9uIE5hbWUiLCJsb2N0YWciOiJzaG9ydCB0YWciLCJpbnYiOlsiaXRlbTEiLCJpdGVtMiJdLCJnb2xkIjpOLCJ4cCI6TiwicXVlc3RzIjpbeyJuIjoicXVlc3QgbmFtZSIsInMiOiJhY3RpdmV8ZG9uZXxmYWlsZWQifV0ke2lzUGFydHk/JywicGFydHkiOnsiUExBWUVSTkFNRSI6eyJocCI6TiwibWF4aHAiOk59fSc6Jyd9fTwvU1RBVEU+CgpSZXBsYWNlIEFMTCBOIHZhbHVlcyB3aXRoIGFjdHVhbCBjdXJyZW50IG51bWJlcnMuYDsKfQoKZnVuY3Rpb24gYnVpbGRTeXN0ZW1Qcm9tcHQoKSB7CiAgY29uc3QgaXNQYXJ0eSA9IE9iamVjdC5rZXlzKHBhcnR5UENzKS5sZW5ndGggPiAxOwogIGNvbnN0IHBhcnR5TGlzdCA9IE9iamVjdC5lbnRyaWVzKHBhcnR5UENzKS5tYXAoKFtwbixwXSkgPT4KICAgIGAke3AubmFtZX0gKHBsYXllcjogJHtwbn0pOiAke3AucmFjZX0gJHtwLmNsc30gTHYke3AubGV2ZWx8fDF9LCBIUCAke3AuaHB9LyR7cC5tYXhocH0sIEFDICR7cC5hY30sIEFsaWduICR7cC5hbGlnbnx8J04nfWAKICApLmpvaW4oJ1suXW4nKTsKCiAgaWYgKCFtb2R1bGVUZXh0KSBjb25zb2xlLndhcm4oJ1tHTV0gbW9kdWxlVGV4dCBpcyBlbXB0eScpOwoKICAvLyBVc2UgZGlmZmVyZW50IHByb21wdHMgZm9yIE9sbGFtYSB2cyBDbGF1ZGUKICAvLyBPbGxhbWEgbmVlZHMgZXhwbGljaXQgc3R5bGUgZ3VpZGFuY2U7IENsYXVkZSBoYW5kbGVzIHZhZ3VlIGluc3RydWN0aW9ucyB3ZWxsCiAgaWYgKHVzZU9sbGFtYSkgewogICAgcmV0dXJuIGJ1aWxkT2xsYW1hUHJvbXB0KGlzUGFydHksIHBhcnR5TGlzdCk7CiAgfSBlbHNlIHsKICAgIHJldHVybiBidWlsZENsYXVkZVByb21wdChpc1BhcnR5LCBwYXJ0eUxpc3QpOwogIH0KfQoKZnVuY3Rpb24gdXBkYXRlSFVEKCkgewogIGlmICghcGMubmFtZSkgcmV0dXJuOwogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdwYy1uYW1lLWQnKS50ZXh0Q29udGVudCA9IHBjLm5hbWU7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3BjLXJjZCcpLnRleHRDb250ZW50ID0gYEx2JHtwYy5sZXZlbHx8MX0gJHtwYy5yYWNlfHwnJ30gJHtwYy5jbHN9YDsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnaHAtdHh0JykudGV4dENvbnRlbnQgPSBgJHtwYy5ocH0vJHtwYy5tYXhocH1gOwogIGNvbnN0IHBjdCA9IE1hdGgubWF4KDAsIHBjLmhwL3BjLm1heGhwKjEwMCk7CiAgY29uc3QgZmlsbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdocC1maWxsJyk7CiAgZmlsbC5zdHlsZS53aWR0aCA9IHBjdCArICclJzsKICBmaWxsLnN0eWxlLmJhY2tncm91bmQgPSBwY3Q+NTA/JyMzYTdhM2EnOnBjdD4yNT8nIzlhNzAyMCc6JyM4YjI1MjUnOwogIFsnYWMnLCdzdHInLCdkZXgnLCdjb24nLCdpbnQnLCd3aXMnLCdjaGEnXS5mb3JFYWNoKHMgPT4gewogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncy0nK3MpOwogICAgaWYgKCFlbCkgcmV0dXJuOwogICAgaWYgKHM9PT0nYWMnKSB7IGVsLnRleHRDb250ZW50ID0gcGMuYWM7IHJldHVybjsgfQogICAgY29uc3QgdiA9IHBjLnN0YXRzW3MudG9VcHBlckNhc2UoKV07CiAgICBlbC50ZXh0Q29udGVudCA9IGAke3Z9ICgke21vZCh2KX0pYDsKICB9KTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncy1ncCcpLnRleHRDb250ZW50ID0gcGMuZ29sZCArICcgZ3AnOwogIC8vIENhdGVnb3Jpc2UgYW5kIGRlZHVwbGljYXRlIGludmVudG9yeQogIHJlbmRlckludmVudG9yeShwYy5pbnZ8fFtdKTsKICBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2NlbmUtbG9jJykudGV4dENvbnRlbnQgPSBwYy5sb2MgfHwgJy4uLic7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3NjZW5lLXRhZycpLnRleHRDb250ZW50ID0gcGMubG9jdGFnIHx8ICcnOwogIGNvbnN0IF9nZCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdnb2xkLWRpc3AnKTsgaWYoX2dkKSBfZ2QudGV4dENvbnRlbnQgPSBwYy5nb2xkOwogIHJlbmRlclF1ZXN0cygpOwogIHVwZGF0ZU1lbW9yeVBhbmVsKCk7CiAgdXBkYXRlUmVzb3VyY2VQYW5lbCgpOwogIHVwZGF0ZVN0YXR1c1BhbmVsKCk7Cn0KCmZ1bmN0aW9uIHBhcnNlSW52SXRlbShyYXcpIHsKICAvLyBTdHJpcCBBTEwgcGFyZW50aGV0aWNhbCBhbm5vdGF0aW9uczogIihBQyAxNCkiLCAiKCsxIEFDKSIsICIoMWQ4KSIsICIodGhyb3duKSIgZXRjLgogIC8vIEFsc28gc3RyaXAgIi0tIG5vdGUiIGFuZCAiKyBTaGllbGQiIHR5cGUgc3VmZml4ZXMgdGhhdCBhcmVuJ3QgYW1tbwogIGNvbnN0IGNsZWFuZWQgPSByYXcKICAgIC5yZXBsYWNlKC9bLl1zKlsuXVteKV0qWy5dL2csICcnKQogICAgLnJlcGxhY2UoL1suXXMqLS0uKiQvZywgJycpCiAgICAudHJpbSgpOwogIGNvbnN0IG0xID0gY2xlYW5lZC5tYXRjaCgvXiguKz8pWy5dcytbeFh4XShbLl1kKykkLyk7CiAgY29uc3QgbTIgPSBjbGVhbmVkLm1hdGNoKC9eKFsuXWQrKVsuXXMqW3hYeF1bLl1zKiguKykkLyk7CiAgaWYgKG0xKSByZXR1cm4ge25hbWU6IG0xWzFdLnRyaW0oKSwgcXR5OiBwYXJzZUludChtMVsyXSl9OwogIGlmIChtMikgcmV0dXJuIHtuYW1lOiBtMlsyXS50cmltKCksIHF0eTogcGFyc2VJbnQobTJbMV0pfTsKICByZXR1cm4ge25hbWU6IGNsZWFuZWQsIHF0eTogMX07Cn0KCmZ1bmN0aW9uIHJlbmRlckludmVudG9yeShpbnZSYXcpIHsKICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdpbnYtbGlzdCcpOwogIGlmICghZWwpIHJldHVybjsKCiAgLy8gRGVkdXBsaWNhdGU6IG1lcmdlIGl0ZW1zIHdpdGggc2FtZSBiYXNlIG5hbWUKICBjb25zdCBjb3VudE1hcCA9IHt9OwogIGludlJhdy5mb3JFYWNoKHJhdyA9PiB7CiAgICBjb25zdCB7bmFtZSwgcXR5fSA9IHBhcnNlSW52SXRlbShyYXcpOwogICAgY29uc3Qga2V5ID0gbmFtZS5yZXBsYWNlKC9bLl1zKlsuXS4qP1suXS8sJycpLnRyaW0oKS50b0xvd2VyQ2FzZSgpOwogICAgaWYgKCFjb3VudE1hcFtrZXldKSBjb3VudE1hcFtrZXldID0ge25hbWU6IG5hbWUucmVwbGFjZSgvWy5dcypbLl0uKj9bLl0vLCcnKS50cmltKCksIHF0eTogMH07CiAgICBjb3VudE1hcFtrZXldLnF0eSArPSBxdHk7CiAgfSk7CgogIGNvbnN0IGNhdHMgPSB7d2VhcG9uczpbXSwgYXJtb3VyOltdLCBtYWdpYzpbXSwgYW1tbzpbXSwgZXF1aXBtZW50OltdfTsKICBjb25zdCBhbW1vSXRlbXMgPSBbXTsgLy8gYWxzbyB0cmFja2VkIGZvciBzdGF0dXMgcGFuZWwKCiAgT2JqZWN0LnZhbHVlcyhjb3VudE1hcCkuZm9yRWFjaCgoe25hbWUsIHF0eX0pID0+IHsKICAgIGNvbnN0IGxhYmVsID0gcXR5ID4gMQogICAgICA/IGAke25hbWV9IDxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS1nb2xkLWRpbSk7Zm9udC1zaXplOjEycHg7Ij54JHtxdHl9PC9zcGFuPmAKICAgICAgOiBuYW1lOwogICAgaWYgKElOVl9BTU1PLnRlc3QobmFtZSkpICAgICAgICAgeyBjYXRzLmFtbW8ucHVzaCh7bmFtZSwgcXR5LCBsYWJlbH0pOyBhbW1vSXRlbXMucHVzaCh7bmFtZSxxdHl9KTsgfQogICAgZWxzZSBpZiAoSU5WX1dFQVBPTlMudGVzdChuYW1lKSkgY2F0cy53ZWFwb25zLnB1c2gobGFiZWwpOwogICAgZWxzZSBpZiAoSU5WX0FSTU9VUi50ZXN0KG5hbWUpKSAgY2F0cy5hcm1vdXIucHVzaChsYWJlbCk7CiAgICBlbHNlIGlmIChJTlZfTUFHSUMudGVzdChuYW1lKSkgICBjYXRzLm1hZ2ljLnB1c2gobGFiZWwpOwogICAgZWxzZSAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY2F0cy5lcXVpcG1lbnQucHVzaChsYWJlbCk7IC8vIHRvcmNoZXMsIHJhdGlvbnMsIGJhY2twYWNrLCBldGMuCiAgfSk7CgogIC8vIFVwZGF0ZSBhbW1vIGluIHN0YXR1cyBwYW5lbAogIHVwZGF0ZUFtbW9TdGF0dXMoYW1tb0l0ZW1zKTsKCiAgY29uc3QgY2F0RGVmcyA9IFsKICAgIFsnd2VhcG9ucycsICdXRUFQT05TJ10sCiAgICBbJ2FybW91cicsICAnQVJNT1VSJ10sCiAgICBbJ21hZ2ljJywgICAnTUFHSUMnXSwKICAgIFsnZXF1aXBtZW50JywnRVFVSVBNRU5UJ10sCiAgXTsKICBjb25zdCBoZHJTdHlsZSA9ICdjb2xvcjp2YXIoLS1nb2xkLWRpbSk7Zm9udC1zaXplOjExcHg7bGV0dGVyLXNwYWNpbmc6MXB4O3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtwYWRkaW5nLXRvcDo1cHg7Ym9yZGVyLXRvcDoxcHggc29saWQgIzJhMjQxMDttYXJnaW4tdG9wOjJweDtsaXN0LXN0eWxlOm5vbmU7JzsKICBsZXQgaHRtbCA9ICcnOwogIGNhdERlZnMuZm9yRWFjaCgoW2NhdCwgbGFiZWxdKSA9PiB7CiAgICBpZiAoIWNhdHNbY2F0XS5sZW5ndGgpIHJldHVybjsKICAgIGh0bWwgKz0gYDxsaSBzdHlsZT0iJHtoZHJTdHlsZX0iPiR7bGFiZWx9PC9saT5gOwogICAgY2F0c1tjYXRdLmZvckVhY2goaSA9PiB7IGh0bWwgKz0gYDxsaT4ke2l9PC9saT5gOyB9KTsKICB9KTsKICBlbC5pbm5lckhUTUwgPSBodG1sIHx8ICc8bGkgc3R5bGU9ImNvbG9yOnZhcigtLWluay1kaW0pIj5FbXB0eTwvbGk+JzsKfQoKZnVuY3Rpb24gaXNJbkR1bmdlb24oKSB7CiAgLy8gQ2hlY2sgaWYgY3VycmVudCBsb2NhdGlvbiBpcyBhIGR1bmdlb24gbGV2ZWwgKGR1bmdlb25fbGV2ZWwgPj0gMSkKICBpZiAoIWxvYWRlZE1vZHVsZURhdGEgfHwgIWxvYWRlZE1vZHVsZURhdGEubG9jYXRpb25zKSByZXR1cm4gZmFsc2U7CiAgY29uc3QgbG9jID0gKGxvYWRlZE1vZHVsZURhdGEubG9jYXRpb25zIHx8IFtdKS5maW5kKGwgPT4gbC5pZCA9PT0gcGMubG9jdGFnKTsKICBpZiAobG9jKSByZXR1cm4gKGxvYy5kdW5nZW9uX2xldmVsIHx8IDApID49IDE7CiAgLy8gRmFsbGJhY2s6IGNoZWNrIGxvY3RhZyBwcmVmaXggKEQgPSBkdW5nZW9uIHJvb21zIGluIE4xKQogIGlmIChwYy5sb2N0YWcgJiYgL15EWy5dZC9pLnRlc3QocGMubG9jdGFnKSkgcmV0dXJuIHRydWU7CiAgcmV0dXJuIGZhbHNlOwp9CgpmdW5jdGlvbiB1cGRhdGVBbW1vU3RhdHVzKGFtbW9JdGVtcykgewogIGxldCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzdGF0dXMtYW1tbycpOwogIGlmICghYW1tb0l0ZW1zLmxlbmd0aCkgewogICAgaWYgKGVsKSBlbC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgcmV0dXJuOwogIH0KICBpZiAoIWVsKSB7CiAgICAvLyBDcmVhdGUgdGhlIGFtbW8gcm93IGlmIGl0IGRvZXNuJ3QgZXhpc3QKICAgIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FjdGl2ZS1lZmZlY3RzJyk7CiAgICBpZiAoIXBhbmVsKSByZXR1cm47CiAgICBlbCA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2RpdicpOwogICAgZWwuaWQgPSAnc3RhdHVzLWFtbW8nOwogICAgZWwuc3R5bGUuY3NzVGV4dCA9ICdmb250LXNpemU6MTRweDtjb2xvcjp2YXIoLS1kaW0pO3BhZGRpbmc6MnB4IDA7JzsKICAgIHBhbmVsLnBhcmVudE5vZGUuaW5zZXJ0QmVmb3JlKGVsLCBwYW5lbCk7CiAgfQogIGVsLnN0eWxlLmRpc3BsYXkgPSAnJzsKICBlbC5pbm5lckhUTUwgPSBhbW1vSXRlbXMubWFwKGEgPT4KICAgIGAke2EubmFtZX06IDxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS1pbmspIj4ke2EucXR5fTwvc3Bhbj5gCiAgKS5qb2luKCc8YnI+Jyk7Cn0KCmZ1bmN0aW9uIHVwZGF0ZVJlc291cmNlUGFuZWwoKSB7CiAgY29uc3QgbGlnaHRFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXMtbGlnaHQnKTsKICBjb25zdCByYXRFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXMtcmF0aW9ucycpOwogIGNvbnN0IHR1cm5FbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXMtdHVybnMnKTsKICBjb25zdCBjb21iYXRFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXMtY29tYmF0Jyk7CiAgaWYgKCFsaWdodEVsICYmICFyYXRFbCAmJiAhdHVybkVsKSByZXR1cm47IC8vIG9sZCByZXNvdXJjZSBwYW5lbCByZW1vdmVkCgogIC8vIExpZ2h0CiAgaWYgKCFpc0NhcnJ5aW5nTGlnaHQpIHsKICAgIGxpZ2h0RWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA2MDYwIj5EQVJLTkVTUzwvc3Bhbj4nOwogIH0gZWxzZSBpZiAodG9yY2hUdXJuc0xlZnQgPiAwICYmIHRvcmNoVHVybnNMZWZ0IDw9IDIpIHsKICAgIGxpZ2h0RWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA5MDQwIj5Ub3JjaDogJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJuczwvc3Bhbj4nOwogIH0gZWxzZSBpZiAodG9yY2hUdXJuc0xlZnQgPiAwKSB7CiAgICBsaWdodEVsLmlubmVySFRNTCA9ICdUb3JjaDogJyArIHRvcmNoVHVybnNMZWZ0ICsgJyB0dXJucyc7CiAgfSBlbHNlIGlmIChoYXNMYW50ZXJuKSB7CiAgICBsaWdodEVsLmlubmVySFRNTCA9ICdMYW50ZXJuOiAnICsgbGFudGVybk9pbEZsYXNrc0xlZnQgKyAnIGZsYXNrKHMpJzsKICB9IGVsc2UgewogICAgbGlnaHRFbC5pbm5lckhUTUwgPSAnTm8gbGlnaHQnOwogIH0KCiAgLy8gUmF0aW9ucwogIGlmIChyYXRpb25zTGVmdCA9PT0gMCkgewogICAgcmF0RWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA2MDYwIj5ObyByYXRpb25zPC9zcGFuPic7CiAgfSBlbHNlIGlmIChyYXRpb25zTGVmdCA9PT0gMSkgewogICAgcmF0RWwuaW5uZXJIVE1MID0gJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA5MDQwIj4xIHJhdGlvbiBsZWZ0PC9zcGFuPic7CiAgfSBlbHNlIHsKICAgIHJhdEVsLmlubmVySFRNTCA9ICdSYXRpb25zOiAnICsgcmF0aW9uc0xlZnQ7CiAgfQoKICAvLyBUdXJucyAvIHRpbWUKICBjb25zdCBob3VycyA9IE1hdGguZmxvb3IoZHVuZ2VvblR1cm5zIC8gNik7CiAgY29uc3QgbWlucyA9IChkdW5nZW9uVHVybnMgJSA2KSAqIDEwOwogIHR1cm5FbC50ZXh0Q29udGVudCA9ICcgVHVybiAnICsgZHVuZ2VvblR1cm5zICsgJyAoJyArIGhvdXJzICsgJ2ggJyArIG1pbnMgKyAnbSknOwoKICAvLyBDb21iYXQKICBpZiAoaW5Db21iYXQpIHsKICAgIGNvbWJhdEVsLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogICAgY29uc3QgYWxpdmUgPSBjb21iYXRTdGF0ZS5pbml0aWF0aXZlT3JkZXIuZmlsdGVyKGMgPT4gIWMuZGVhZCAmJiAhYy5mbGVkKTsKICAgIGNvbWJhdEVsLmlubmVySFRNTCA9ICdSb3VuZCAnICsgY29tYmF0U3RhdGUucm91bmQgKyAnIC0tICcgKyBhbGl2ZS5sZW5ndGggKyAnIGNvbWJhdGFudHMnOwogIH0gZWxzZSB7CiAgICBjb21iYXRFbC5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogIH0KfQoKZnVuY3Rpb24gdXBkYXRlTWVtb3J5UGFuZWwoKSB7CiAgaWYgKCF1c2VPbGxhbWEpIHJldHVybjsKICBjb25zdCBwYW5lbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW1vcnktcGFuZWwnKTsKICBpZiAoIXBhbmVsKSByZXR1cm47CiAgY29uc3QgaGFzTWVtb3J5ID0gbWVtb3J5U3VtbWFyeSB8fCBwaW5uZWRGYWN0cy5sZW5ndGggfHwgT2JqZWN0LmtleXMod29ybGRTdGF0ZS5ucGNzX21ldCkubGVuZ3RoOwogIHBhbmVsLnN0eWxlLmRpc3BsYXkgPSBoYXNNZW1vcnkgPyAnYmxvY2snIDogJ25vbmUnOwogIGNvbnN0IF9tdCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW0tdHVybicpOyBpZihfbXQpIF9tdC50ZXh0Q29udGVudCA9ICdUdXJuICcgKyB0dXJuQ291bnQ7CiAgY29uc3Qgc3VtRWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnbWVtLXN1bW1hcnknKTsKICBpZiAoIXN1bUVsKSByZXR1cm47CiAgaWYgKG1lbW9yeVN1bW1hcnkpIHsKICAgIHN1bUVsLnRleHRDb250ZW50ID0gbWVtb3J5U3VtbWFyeS5zdWJzdHJpbmcoMCwgODApICsgKG1lbW9yeVN1bW1hcnkubGVuZ3RoID4gODAgPyAnLi4uJyA6ICcnKTsKICAgIHN1bUVsLnRpdGxlID0gbWVtb3J5U3VtbWFyeTsKICB9IGVsc2UgewogICAgc3VtRWwudGV4dENvbnRlbnQgPSAnJzsKICB9CiAgY29uc3QgX21mID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ21lbS1mYWN0cycpOyBpZihfbWYpIF9tZi50ZXh0Q29udGVudCA9CiAgICBwaW5uZWRGYWN0cy5sZW5ndGggPyBwaW5uZWRGYWN0cy5sZW5ndGggKyAnIGZhY3RzIHBpbm5lZCcgOiAnJzsKICBjb25zdCBucGNOYW1lcyA9IE9iamVjdC5rZXlzKHdvcmxkU3RhdGUubnBjc19tZXQpOwogIGNvbnN0IF9tbiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW0tbnBjcycpOyBpZihfbW4pIF9tbi50ZXh0Q29udGVudCA9CiAgICBucGNOYW1lcy5sZW5ndGggPyAnTlBDczogJyArIG5wY05hbWVzLnNsaWNlKDAsNSkuam9pbignLCAnKSA6ICcnOwp9CgpmdW5jdGlvbiByZW5kZXJRdWVzdHMoKSB7CiAgY29uc3QgcWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncXVlc3QtbGlzdCcpOwogIHFsLmlubmVySFRNTCA9IChwYy5xdWVzdHN8fFtdKS5sZW5ndGgKICAgID8gcGMucXVlc3RzLm1hcChxPT5gPGxpIGNsYXNzPSIke3Euc30iPiR7cS5ufTwvbGk+YCkuam9pbignJykKICAgIDogJzxsaSBzdHlsZT0iZm9udC1zaXplOjE0cHg7Y29sb3I6IzhhN2E1OCI+Tm9uZSB5ZXQ8L2xpPic7Cn0KCmZ1bmN0aW9uIHJlbmRlclBhcnR5UGFuZWwoKSB7CiAgY29uc3QgcGFuZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncGFydHktcGFuZWwnKTsKICBjb25zdCBjb250YWluZXIgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnb3RoZXItcGNzJyk7CiAgY29uc3Qgb3RoZXJzID0gT2JqZWN0LmVudHJpZXMocGFydHlQQ3MpLmZpbHRlcigoW25dKSA9PiBuICE9PSBwbGF5ZXJOYW1lKTsKICBpZiAoIW90aGVycy5sZW5ndGgpIHsgcGFuZWwuc3R5bGUuZGlzcGxheT0nbm9uZSc7IHJldHVybjsgfQogIHBhbmVsLnN0eWxlLmRpc3BsYXkgPSAnYmxvY2snOwogIGNvbnRhaW5lci5pbm5lckhUTUwgPSBvdGhlcnMubWFwKChbcG4scF0saSkgPT4gewogICAgY29uc3QgY29sID0gZ2V0Q29sb3IocG4pOwogICAgY29uc3QgcGN0ID0gTWF0aC5tYXgoMCwgcC5ocC9wLm1heGhwKjEwMCk7CiAgICBjb25zdCBoY29sID0gcGN0PjUwPycjM2E3YTNhJzpwY3Q+MjU/JyM5YTcwMjAnOicjOGIyNTI1JzsKICAgIHJldHVybiBgPGRpdiBjbGFzcz0ib3BjIj4KICAgICAgPGRpdiBjbGFzcz0ib3BjLW5hbWUiIHN0eWxlPSJjb2xvcjoke2NvbH0iPiR7cC5uYW1lfSA8c3BhbiBzdHlsZT0iZm9udC1zaXplOjEzcHg7Y29sb3I6dmFyKC0taW5rLWRpbSkiPiR7cC5yYWNlfSAke3AuY2xzfTwvc3Bhbj48L2Rpdj4KICAgICAgPGRpdiBjbGFzcz0ib3BjLWhwIj4ke3AuaHB9LyR7cC5tYXhocH0gSFAgKiBBQyAke3AuYWN9PC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9Im9wYy1ocGJhciI+PGRpdiBjbGFzcz0ib3BjLWhwZmlsbCIgc3R5bGU9IndpZHRoOiR7cGN0fSU7YmFja2dyb3VuZDoke2hjb2x9Ij48L2Rpdj48L2Rpdj4KICAgIDwvZGl2PmA7CiAgfSkuam9pbignJyk7Cn0KCmZ1bmN0aW9uIHNldEJ1dHRvbnMoYXJyKSB7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3F1aWNrLWJ0bnMnKS5pbm5lckhUTUwgPSAoYXJyfHxbXSkubWFwKGIgPT4KICAgIGA8YnV0dG9uIGNsYXNzPSJxYiIgb25jbGljaz0icXVpY2tBY3QoJHtKU09OLnN0cmluZ2lmeShiKX0pIj4ke2J9PC9idXR0b24+YAogICkuam9pbignJyk7Cn0KCmZ1bmN0aW9uIGNsYXNzaWZ5RW50cnkodHh0KSB7CiAgaWYgKC9bLl1Sb2xsOnxbLl1TYXZlfGQyMCA9fGluaXRpYXRpdmUvaS50ZXN0KHR4dCkpIHJldHVybiAncm9sbCc7CiAgaWYgKC9hdHRhY2t8aGl0fGRhbWFnZXx3b3VuZHxibG9vZHxzbGF5fGNvbWJhdHxzdHJpa2UvaS50ZXN0KHR4dCkpIHJldHVybiAnY29tYmF0JzsKICBpZiAoL2dvbGR8Z3B8dHJlYXN1cmV8bG9vdHxmb3VuZHxjb2luL2kudGVzdCh0eHQpKSByZXR1cm4gJ2xvb3QnOwogIHJldHVybiAnZ20nOwp9CgpmdW5jdGlvbiBhZGRFbnRyeShodG1sLCB0eXBlLCBhdXRob3IpIHsgcmV0dXJuIGFkZEVudHJ5UmF3KGh0bWwsIHR5cGUsIGF1dGhvcik7IH0KCmZ1bmN0aW9uIGFkZEVudHJ5UmF3KGh0bWwsIHR5cGUsIGF1dGhvcikgewogIGNvbnN0IGxvZyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsb2cnKTsKICBjb25zdCBkID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnZGl2Jyk7CiAgaWYgKHR5cGUgPT09ICdzeXN0ZW0tcm9sbCcpIHsKICAgIGQuY2xhc3NOYW1lID0gJ2xvZy1zeXN0ZW0tcm9sbCc7CiAgICBkLmlubmVySFRNTCA9IGh0bWw7CiAgICBsb2cuYXBwZW5kQ2hpbGQoZCk7CiAgICBsb2cuc2Nyb2xsVG9wID0gbG9nLnNjcm9sbEhlaWdodDsKICAgIGxvZ0VudHJpZXMucHVzaCh7IGh0bWwsIHR5cGUsIGF1dGhvciB9KTsKICAgIHJldHVybiBkOwogIH0KICBkLmNsYXNzTmFtZSA9ICdlbnRyeSAnICsgKGF1dGhvciAmJiBhdXRob3IgIT09ICdfX2dtX18nID8gJ3BsYXllci1tc2cnIDogdHlwZSk7CiAgaWYgKGF1dGhvciAmJiBhdXRob3IgIT09ICdfX2dtX18nICYmIHR5cGUgIT09ICdzeXN0ZW0nKSB7CiAgICBjb25zdCBjb2wgPSBnZXRDb2xvcihhdXRob3IpOwogICAgY29uc3QgaCA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2RpdicpOwogICAgaC5jbGFzc05hbWUgPSAnZW50cnktYXV0aG9yJzsKICAgIGguc3R5bGUuY29sb3IgPSBjb2w7CiAgICBoLnRleHRDb250ZW50ID0gYXV0aG9yOwogICAgZC5hcHBlbmRDaGlsZChoKTsKICB9CiAgY29uc3QgYyA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2RpdicpOwogIGMuaW5uZXJIVE1MID0gaHRtbDsKICBkLmFwcGVuZENoaWxkKGMpOwogIGxvZy5hcHBlbmRDaGlsZChkKTsKICBsb2cuc2Nyb2xsVG9wID0gbG9nLnNjcm9sbEhlaWdodDsKICBsb2dFbnRyaWVzLnB1c2goeyBodG1sLCB0eXBlLCBhdXRob3IgfSk7CiAgcmV0dXJuIGQ7Cn0KCmZ1bmN0aW9uIGZtdCh0eHQpIHsKICByZXR1cm4gdHh0CiAgICAucmVwbGFjZSgvJi9nLCcmYW1wOycpLnJlcGxhY2UoLzwvZywnJmx0OycpLnJlcGxhY2UoLz4vZywnJmd0OycpCiAgICAucmVwbGFjZSgvWy5dKFteWy5dXSspWy5dL2csJzxzcGFuIGNsYXNzPSJyb2xsLXRhZyI+WyQxXTwvc3Bhbj4nKQogICAgLnJlcGxhY2UoL1suXVsuXShbXipdKylbLl1bLl0vZywnPHN0cm9uZz4kMTwvc3Ryb25nPicpCiAgICAucmVwbGFjZSgvWy5dKFteKl0rKVsuXS9nLCc8ZW0+JDE8L2VtPicpOwp9CgpmdW5jdGlvbiBwdXNoTWVzc2FnZShodG1sLCB0eXBlLCBhdXRob3IpIHsKICBpZiAoIWlzTXVsdGlwbGF5ZXIgfHwgIXJvb21Db2RlKSByZXR1cm47CiAgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL3B1c2hfbWVzc2FnZScsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LCBib2R5OiBKU09OLnN0cmluZ2lmeSh7Y29kZTpyb29tQ29kZSwgaHRtbCwgdHlwZSwgYXV0aG9yLCBzZXE6ICsrbGFzdFNlcX0pfSk7Cn0KCmZ1bmN0aW9uIHBhcnNlU3RhdGUocmF3KSB7CiAgdHJ5IHsKICAgIC8vIFRyeSA8U1RBVEU+ey4uLn08L1NUQVRFPiBmaXJzdAogICAgbGV0IG0gPSByYXcubWF0Y2goLzxTVEFURT4oWy5dW1suXXNbLl1TXSo/Wy5dKVsuXXMqPFsuXVNUQVRFPi8pOwogICAgaWYgKG0pIHJldHVybiBKU09OLnBhcnNlKG1bMV0pOwogICAgLy8gRmFsbCBiYWNrIHRvIFtTVEFURV17Li4ufSAoT2xsYW1hIHNvbWV0aW1lcyB1c2VzIHNxdWFyZSBicmFja2V0cykKICAgIG0gPSByYXcubWF0Y2goL1suXVNUQVRFWy5dKFsuXVtbLl1zWy5dU10qP1suXSkvKTsKICAgIGlmIChtKSByZXR1cm4gSlNPTi5wYXJzZShtWzFdKTsKICB9IGNhdGNoKGUpIHt9CiAgcmV0dXJuIG51bGw7Cn0KCmZ1bmN0aW9uIHN0cmlwU3RhdGUocmF3KSB7IHJldHVybiByYXcucmVwbGFjZSgvPFNUQVRFPltbLl1zWy5dU10qPzxbLl1TVEFURT4vZywnJykucmVwbGFjZSgvWy5dU1RBVEVbLl1bWy5dc1suXVNdKj8oPz1bLl1uWy5dbnwkKS9nLCcnKS5yZXBsYWNlKC9bLl1TVEFURVsuXVsuXVtbLl1zWy5dU10qP1suXVsuXXMqL2csJycpLnRyaW0oKTsgfQoKZnVuY3Rpb24gYXBwbHlTdGF0ZShncykgewogIGlmICghZ3MpIHJldHVybjsKICBpZiAoZ3MuaHAhPT11bmRlZmluZWQpIHBjLmhwPWdzLmhwOwogIGlmIChncy5tYXhocCE9PXVuZGVmaW5lZCkgcGMubWF4aHA9Z3MubWF4aHA7CiAgaWYgKGdzLmludiYmZ3MuaW52Lmxlbmd0aCkgcGMuaW52PWdzLmludjsKICBpZiAoZ3MuZ29sZCE9PXVuZGVmaW5lZCkgcGMuZ29sZD1ncy5nb2xkOwogIGlmIChncy5sb2MpIHBjLmxvYz1ncy5sb2M7CiAgaWYgKGdzLmxvY3RhZyE9PXVuZGVmaW5lZCkgewogICAgY29uc3Qgd2FzSW5EdW5nZW9uID0gaXNJbkR1bmdlb24oKTsKICAgIHBjLmxvY3RhZz1ncy5sb2N0YWc7CiAgICAvLyBSZXNldCByZXN0IGNvdW50ZXIgd2hlbiBsZWF2aW5nIHRoZSBkdW5nZW9uCiAgICBpZiAod2FzSW5EdW5nZW9uICYmICFpc0luRHVuZ2VvbigpKSB7CiAgICAgIHR1cm5zV2l0aG91dFJlc3QgPSAwOwogICAgICBmYXRpZ3VlUGVuYWx0eSA9IDA7CiAgICB9CiAgfQogIGlmIChncy5xdWVzdHMpIHBjLnF1ZXN0cz1ncy5xdWVzdHM7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3F1aWNrLWJ0bnMnKS5pbm5lckhUTUwgPSAnJzsKICBpZiAoZ3MucGFydHkpIHsKICAgIE9iamVjdC5lbnRyaWVzKGdzLnBhcnR5KS5mb3JFYWNoKChbcG4scGRdKSA9PiB7CiAgICAgIGlmIChwYXJ0eVBDc1twbl0pIHsgcGFydHlQQ3NbcG5dLmhwPXBkLmhwfHxwYXJ0eVBDc1twbl0uaHA7IHBhcnR5UENzW3BuXS5tYXhocD1wZC5tYXhocHx8cGFydHlQQ3NbcG5dLm1heGhwOyB9CiAgICB9KTsKICAgIHJlbmRlclBhcnR5UGFuZWwoKTsKICAgIGlmIChpc011bHRpcGxheWVyICYmIHJvb21Db2RlKSB7CiAgICAgIHhockZldGNoKEJBU0VfVVJMICsgJy91cGRhdGVfcm9vbScsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LCBib2R5OiBKU09OLnN0cmluZ2lmeSh7Y29kZTpyb29tQ29kZSwgcGFydHlQQ3MsIGdhbWVTdGF0ZTpnc30pfSk7CiAgICB9CiAgfQogIC8vIEF1dG8tc2F2ZSBjaGFyYWN0ZXIgcHJvZ3Jlc3MgYWZ0ZXIgZXZlcnkgZXhjaGFuZ2UKICBpZiAocGMuaWQpIHsKICAgIHhockZldGNoKEJBU0VfVVJMICsgJy9zYXZlX2NoYXJhY3RlcicsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LCBib2R5OiBKU09OLnN0cmluZ2lmeShwYyl9KTsKICB9CiAgdXBkYXRlSFVEKCk7Cn0KCmZ1bmN0aW9uIGV4dHJhY3RBbmRQaW5GYWN0cyh0ZXh0KSB7CiAgLy8gUGF0dGVybnMgdGhhdCBzaWduYWwgYSBtZW1vcmFibGUgZmFjdAogIGNvbnN0IHBhdHRlcm5zID0gWwogICAgLy8gTlBDIG5hbWVzIGFuZCByb2xlcwogICAgLyhbQS1aXVthLXpdKyg/OlsuXXNbQS1aXVthLXpdKyk/KVsuXXMrKD86aXN8d2FzfGFyZXx3ZXJlKVsuXXMrKD86dGhlfGF8YW4pWy5dcysoW14uIT9dezUsNDB9KVsuIT9dL2csCiAgICAvLyBEZWF0aCBvZiBtb25zdGVycy9OUENzCiAgICAvKFtBLVpdW2Etel0rKD86Wy5dc1tBLVpdW2Etel0rKT8pWy5dcysoPzppc3xoYXMgYmVlbnx3YXMpWy5dcysoPzpraWxsZWR8c2xhaW58ZGVmZWF0ZWR8ZGVhZCkvZywKICAgIC8vIExvY2F0aW9ucyBkaXNjb3ZlcmVkCiAgICAvKD86ZW50ZXJ8ZGlzY292ZXJ8ZmluZHxyZXZlYWx8b3BlbilbLl1zKyg/OnRoZXxhfGFuKVsuXXMrKFteLiE/XXs1LDQwfSlbLiE/XS9naSwKICAgIC8vIEl0ZW1zIG9idGFpbmVkCiAgICAvKD86cGljayB1cHx0YWtlfGZpbmR8cmVjZWl2ZXxvYnRhaW58cG9ja2V0KVsuXXMrKD86dGhlfGF8YW4pWy5dcysoW14uIT9dezUsNDB9KVsuIT9dL2dpLAogICAgLy8gRG9vcnMvcGFzc2FnZXMgb3BlbmVkCiAgICAvKD86c2VjcmV0IGRvb3J8aGlkZGVuIHBhc3NhZ2V8Y29uY2VhbGVkIGVudHJhbmNlKVteLiE/XSooPzpvcGVufHJldmVhbHxmb3VuZClbXi4hP10qL2dpLAogIF07CgogIGNvbnN0IG5ld0ZhY3RzID0gW107CiAgcGF0dGVybnMuZm9yRWFjaChwYXR0ZXJuID0+IHsKICAgIGxldCBtYXRjaDsKICAgIGNvbnN0IHJlID0gbmV3IFJlZ0V4cChwYXR0ZXJuLnNvdXJjZSwgcGF0dGVybi5mbGFncyk7CiAgICB3aGlsZSAoKG1hdGNoID0gcmUuZXhlYyh0ZXh0KSkgIT09IG51bGwpIHsKICAgICAgY29uc3QgZmFjdCA9IG1hdGNoWzBdLnRyaW0oKTsKICAgICAgaWYgKGZhY3QubGVuZ3RoID4gMTUgJiYgZmFjdC5sZW5ndGggPCAxMjApIHsKICAgICAgICAvLyBBdm9pZCBkdXBsaWNhdGVzCiAgICAgICAgY29uc3Qgc2ltcGxpZmllZCA9IGZhY3QudG9Mb3dlckNhc2UoKS5yZXBsYWNlKC9bXmEtejAtOSBdL2csICcnKTsKICAgICAgICBjb25zdCBpc0R1cCA9IHBpbm5lZEZhY3RzLnNvbWUoZiA9PgogICAgICAgICAgZi50b0xvd2VyQ2FzZSgpLnJlcGxhY2UoL1teYS16MC05IF0vZywgJycpLmluY2x1ZGVzKHNpbXBsaWZpZWQuc3Vic3RyaW5nKDAsIDIwKSkKICAgICAgICApOwogICAgICAgIGlmICghaXNEdXApIG5ld0ZhY3RzLnB1c2goZmFjdCk7CiAgICAgIH0KICAgIH0KICB9KTsKCiAgLy8gQWRkIG5ldyBmYWN0cywgY2FwIGF0IE1BWF9QSU5ORURfRkFDVFMKICBwaW5uZWRGYWN0cy5wdXNoKC4uLm5ld0ZhY3RzKTsKICBpZiAocGlubmVkRmFjdHMubGVuZ3RoID4gTUFYX1BJTk5FRF9GQUNUUykgewogICAgcGlubmVkRmFjdHMgPSBwaW5uZWRGYWN0cy5zbGljZSgtTUFYX1BJTk5FRF9GQUNUUyk7CiAgfQp9CgpmdW5jdGlvbiB1cGRhdGVXb3JsZFN0YXRlKHJhd1Jlc3BvbnNlLCBnYW1lU3RhdGUpIHsKICAvLyBRdWVzdHMKICBpZiAoZ2FtZVN0YXRlICYmIGdhbWVTdGF0ZS5xdWVzdHMpIHsKICAgIHdvcmxkU3RhdGUucXVlc3RzX2FjdGl2ZSA9IGdhbWVTdGF0ZS5xdWVzdHMuZmlsdGVyKHE9PnEucz09PSdhY3RpdmUnKS5tYXAocT0+cS5uKTsKICB9CgogIC8vIEZpeCAyOiBUcmFjayBsb2NhdGlvbnMgKyBjYWNoZSBhdG1vc3BoZXJlCiAgaWYgKGdhbWVTdGF0ZSAmJiBnYW1lU3RhdGUubG9jICYmIGdhbWVTdGF0ZS5sb2MgIT09ICcuLi4nKSB7CiAgICBjb25zdCBsb2MgPSBnYW1lU3RhdGUubG9jOwogICAgaWYgKCF3b3JsZFN0YXRlLmxvY2F0aW9uc192aXNpdGVkW2xvY10pIHsKICAgICAgd29ybGRTdGF0ZS5sb2NhdGlvbnNfdmlzaXRlZFtsb2NdID0geyBmaXJzdF92aXNpdGVkOiB0dXJuQ291bnQsIHRhZzogZ2FtZVN0YXRlLmxvY3RhZ3x8JycgfTsKICAgIH0KICAgIGlmICghbG9jYXRpb25BdG1vc3BoZXJlW2xvY10pIHsKICAgICAgY29uc3QgZmlyc3RTZW50ZW5jZSA9IHJhd1Jlc3BvbnNlLnNwbGl0KC9bLiE/XS8pWzBdLnRyaW0oKTsKICAgICAgbG9jYXRpb25BdG1vc3BoZXJlW2xvY10gPSBmaXJzdFNlbnRlbmNlLnN1YnN0cmluZygwLDEyMCk7CiAgICB9CiAgICBjdXJyZW50QXRtb3NwaGVyZSA9IGxvY2F0aW9uQXRtb3NwaGVyZVtsb2NdIHx8ICcnOwogIH0KCiAgLy8gRml4IDE6IEJ1aWxkIE5QQyBwcm9maWxlcyB3aXRoIHNhbXBsZSBxdW90ZXMgZm9yIHZvaWNlIGNvbnNpc3RlbmN5CiAgY29uc3QgdGV4dEZvck5wYyA9IHJhd1Jlc3BvbnNlOwogIGNvbnN0IG5wY05hbWVzID0gT2JqZWN0LmtleXMobnBjUHJvZmlsZXMpLmNvbmNhdChPYmplY3Qua2V5cyh3b3JsZFN0YXRlLm5wY3NfbWV0KSk7CiAgLy8gRGV0ZWN0IG5ldyBOUENzIHNwZWFraW5nCiAgY29uc3Qgc3BlYWtXb3JkcyA9IFsnc2F5cycsJ3RlbGxzJywnd2hpc3BlcnMnLCdzaG91dHMnLCdyZXBsaWVzJywnYXNrcycsJ2dyb3dscycsJ211dHRlcnMnLCdzbmVlcnMnLCdsYXVnaHMnLCdzaWdocycsJ2JhcmtzJywnaGlzc2VzJywnZGVjbGFyZXMnLCdhbm5vdW5jZXMnXTsKICBzcGVha1dvcmRzLmZvckVhY2godmVyYiA9PiB7CiAgICBjb25zdCBwYXQgPSBuZXcgUmVnRXhwKCcoW0EtWl1bYS16XXsyLDIwfSg/OlsuXXNbQS1aXVthLXpdezIsMjB9KT8pKD86W14sXXswLDIwfSknICsgdmVyYiArICdbXixdKlssXT8oW14sXXsxMCwxMDB9KScsICdnaScpOwogICAgbGV0IG07CiAgICB3aGlsZSAoKG0gPSBwYXQuZXhlYyh0ZXh0Rm9yTnBjKSkgIT09IG51bGwpIHsKICAgICAgY29uc3QgbmFtZSA9IG1bMV0udHJpbSgpOwogICAgICBjb25zdCBxdW90ZSA9IG1bMl0udHJpbSgpOwogICAgICBpZiAoWydUaGUnLCdZb3UnLCdZb3VyJywnSGUnLCdTaGUnLCdUaGV5JywnSXQnLCdUaGlzJywnVGhhdCddLmluY2x1ZGVzKG5hbWUpKSBjb250aW51ZTsKICAgICAgaWYgKCFucGNQcm9maWxlc1tuYW1lXSkgbnBjUHJvZmlsZXNbbmFtZV0gPSB7IGZpcnN0X21ldDogdHVybkNvdW50LCBxdW90ZXM6IFtdLCBhdHRpdHVkZTogJ3Vua25vd24nIH07CiAgICAgIGlmIChucGNQcm9maWxlc1tuYW1lXS5xdW90ZXMubGVuZ3RoIDwgMykgbnBjUHJvZmlsZXNbbmFtZV0ucXVvdGVzLnB1c2gocXVvdGUpOwogICAgICBpZiAoIXdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0pIHdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0gPSB7IGF0dGl0dWRlOiAndW5rbm93bicsIGZpcnN0X21ldDogdHVybkNvdW50IH07CiAgICB9CiAgfSk7CgogIC8vIE5QQyBhdHRpdHVkZSBkZXRlY3Rpb24KICBjb25zdCBhdHRpdHVkZVBhdCA9IC8oW0EtWl1bYS16XXsyLDIwfSg/OlsuXXNbQS1aXVthLXpdezIsMjB9KT8pWy5dcysoPzpzZWVtc3xhcHBlYXJzfGxvb2tzfGlzKVsuXXMrKGZyaWVuZGx5fGhvc3RpbGV8bmVydm91c3xhZnJhaWR8c3VzcGljaW91c3xwbGVhc2VkfGFuZ3J5fGZyaWdodGVuZWR8d2FyeXxncmF0ZWZ1bCkvZ2k7CiAgbGV0IG0yOwogIHdoaWxlICgobTIgPSBhdHRpdHVkZVBhdC5leGVjKHJhd1Jlc3BvbnNlKSkgIT09IG51bGwpIHsKICAgIGNvbnN0IG5hbWUgPSBtMlsxXTsKICAgIGlmIChbJ1RoZScsJ1lvdScsJ1lvdXInLCdIZScsJ1NoZScsJ1RoZXknXS5pbmNsdWRlcyhuYW1lKSkgY29udGludWU7CiAgICBpZiAoIXdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0pIHdvcmxkU3RhdGUubnBjc19tZXRbbmFtZV0gPSB7IGF0dGl0dWRlOiBtMlsyXS50b0xvd2VyQ2FzZSgpLCBmaXJzdF9tZXQ6IHR1cm5Db3VudCB9OwogICAgZWxzZSB3b3JsZFN0YXRlLm5wY3NfbWV0W25hbWVdLmF0dGl0dWRlID0gbTJbMl0udG9Mb3dlckNhc2UoKTsKICAgIGlmIChucGNQcm9maWxlc1tuYW1lXSkgbnBjUHJvZmlsZXNbbmFtZV0uYXR0aXR1ZGUgPSBtMlsyXS50b0xvd2VyQ2FzZSgpOwogIH0KCiAgLy8gTW9uc3RlciBraWxscwogIGNvbnN0IGtpbGxQYXQgPSAvKFtBLVpdW2Etel17MiwyNX0oPzpbLl1zW0EtWl1bYS16XXsyLDI1fSk/KVteLl17MCwzMH0oPzppcyBraWxsZWR8aXMgc2xhaW58ZGllc3xmYWxscyBkZWFkfGNydW1wbGVzfGNvbGxhcHNlcyBkZWFkKS9naTsKICBsZXQgbTM7CiAgd2hpbGUgKChtMyA9IGtpbGxQYXQuZXhlYyhyYXdSZXNwb25zZSkpICE9PSBudWxsKSB7CiAgICBjb25zdCBuYW1lID0gbTNbMV07CiAgICBpZiAoIXdvcmxkU3RhdGUubW9uc3RlcnNfa2lsbGVkLmluY2x1ZGVzKG5hbWUpKSB3b3JsZFN0YXRlLm1vbnN0ZXJzX2tpbGxlZC5wdXNoKG5hbWUpOwogIH0KCiAgLy8gRml4IDU6IFBlcm1hbmVudCB3b3JsZC1jaGFuZ2luZyBldmVudHMKICBjb25zdCBjaGFuZ2VQYXQgPSAvKD86YnVybig/OmVkfHN8aW5nKXxkZXN0cm95KD86ZWR8cyl8Y29sbGFwc2UoPzpkfHMpfGFsYXJtKD86ZWR8cyl8YWxlcnQoPzplZHxzKXxnYXRlICg/Om9wZW5zfGNsb3Nlc3xpcyBvcGVuKXxmaXJlICg/OnNwcmVhZHN8YnVybnMpKVteLiE/XXswLDgwfVsuIT9dL2dpOwogIGxldCBtNDsKICB3aGlsZSAoKG00ID0gY2hhbmdlUGF0LmV4ZWMocmF3UmVzcG9uc2UpKSAhPT0gbnVsbCkgewogICAgY29uc3QgZXZlbnQgPSBtNFswXS50cmltKCkuc3Vic3RyaW5nKDAsMTAwKTsKICAgIGlmICghd29ybGRTdGF0ZS53b3JsZF9jaGFuZ2VzLnNvbWUoZSA9PiBlLmluY2x1ZGVzKGV2ZW50LnN1YnN0cmluZygwLDIwKSkpKSB7CiAgICAgIHdvcmxkU3RhdGUud29ybGRfY2hhbmdlcy5wdXNoKCdUdXJuICcgKyB0dXJuQ291bnQgKyAnOiAnICsgZXZlbnQpOwogICAgfQogIH0KICBpZiAod29ybGRTdGF0ZS53b3JsZF9jaGFuZ2VzLmxlbmd0aCA+IDE1KSB3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMgPSB3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMuc2xpY2UoLTE1KTsKCiAgLy8gRml4IDY6IFVwZGF0ZSBzZXNzaW9uIHRvbmUKICBjb25zdCBjdyA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoYXR0YWNrfGNvbWJhdHxmaWdodHxzdHJpa2V8d291bmR8Ymxvb2R8d2VhcG9ufHNsYXl8YmF0dGxlKVxiL2dpKXx8W10pLmxlbmd0aDsKICBjb25zdCB0dyA9IChyYXdSZXNwb25zZS5tYXRjaCgvXGIoZGFuZ2VyfHRyYXB8cG9pc29ufGZsZWV8c2NyZWFtfGRlYXRofGRpZXN8a2lsbGVkfHRlcnJvcilcYi9naSl8fFtdKS5sZW5ndGg7CiAgY29uc3Qgc3cgPSAocmF3UmVzcG9uc2UubWF0Y2goL1xiKHNheXN8YXNrc3x0ZWxsc3xzcGVha3N8bmVnb3RpYXRlfHBlcnN1YWRlfGNoYXJtfGNvbnZlcnNhdGlvbilcYi9naSl8fFtdKS5sZW5ndGg7CiAgY29uc3QgZXcgPSAocmF3UmVzcG9uc2UubWF0Y2goL1xiKHNlYXJjaHxleGFtaW5lfGV4cGxvcmV8ZGlzY292ZXJ8ZmluZHxvcGVufHBhc3NhZ2V8ZG9vcnxjb3JyaWRvcilcYi9naSl8fFtdKS5sZW5ndGg7CiAgY29uc3QgbWF4ID0gTWF0aC5tYXgoY3csIHR3LCBzdywgZXcpOwogIGlmIChtYXggPiAyKSB7CiAgICBpZiAoY3cgPT09IG1heCkgc2Vzc2lvblRvbmUgPSAnY29tYmF0LWhlYXZ5JzsKICAgIGVsc2UgaWYgKHR3ID09PSBtYXgpIHNlc3Npb25Ub25lID0gJ3RlbnNlJzsKICAgIGVsc2UgaWYgKHN3ID09PSBtYXgpIHNlc3Npb25Ub25lID0gJ3NvY2lhbCc7CiAgICBlbHNlIHNlc3Npb25Ub25lID0gJ2V4cGxvcmF0b3J5JzsKICB9CgogIC8vIFJvdGF0ZSBiYW5uZWQgcGhyYXNlcyBldmVyeSA0IHR1cm5zCiAgaWYgKHR1cm5Db3VudCAlIDQgPT09IDApIHJvdGF0ZUJhbm5lZFBocmFzZXMoKTsKfQoKZnVuY3Rpb24gYnVpbGRXb3JsZFN0YXRlQmxvY2soKSB7CiAgY29uc3QgbGluZXMgPSBbXTsKCiAgLy8gRml4IDE6IE5QQyBwcm9maWxlcyB3aXRoIHZvaWNlIHNhbXBsZXMgZm9yIGNvbnNpc3RlbmN5CiAgY29uc3QgbnBjRW50cmllcyA9IE9iamVjdC5lbnRyaWVzKG5wY1Byb2ZpbGVzKTsKICBpZiAobnBjRW50cmllcy5sZW5ndGggPiAwKSB7CiAgICBsaW5lcy5wdXNoKCdLTk9XTiBOUENzIC0tIG1haW50YWluIHRoZWlyIHZvaWNlIGFuZCBhdHRpdHVkZSBjb25zaXN0ZW50bHk6Jyk7CiAgICBucGNFbnRyaWVzLnNsaWNlKC04KS5mb3JFYWNoKChbbmFtZSwgZGF0YV0pID0+IHsKICAgICAgbGV0IGVudHJ5ID0gJyAgJyArIG5hbWUgKyAnOiBhdHRpdHVkZT0nICsgZGF0YS5hdHRpdHVkZTsKICAgICAgaWYgKGRhdGEucXVvdGVzICYmIGRhdGEucXVvdGVzLmxlbmd0aCA+IDApIGVudHJ5ICs9ICcgfCBTYW1wbGUgc3BlZWNoOiAiJyArIGRhdGEucXVvdGVzWzBdICsgJyInOwogICAgICBsaW5lcy5wdXNoKGVudHJ5KTsKICAgIH0pOwogIH0gZWxzZSBpZiAoT2JqZWN0LmtleXMod29ybGRTdGF0ZS5ucGNzX21ldCkubGVuZ3RoID4gMCkgewogICAgbGluZXMucHVzaCgnTlBDcyBlbmNvdW50ZXJlZDogJyArIE9iamVjdC5lbnRyaWVzKHdvcmxkU3RhdGUubnBjc19tZXQpLm1hcCgoW24sZF0pPT5uKycgKCcrZC5hdHRpdHVkZSsnKScpLmpvaW4oJywgJykpOwogIH0KCiAgLy8gRml4IDI6IEN1cnJlbnQgbG9jYXRpb24gYXRtb3NwaGVyZQogIGlmIChjdXJyZW50QXRtb3NwaGVyZSkgbGluZXMucHVzaCgnQ3VycmVudCBhdG1vc3BoZXJlOiAnICsgY3VycmVudEF0bW9zcGhlcmUpOwoKICAvLyBGaXggNjogU2Vzc2lvbiB0b25lIGd1aWRhbmNlCiAgY29uc3QgdG9uZXMgPSB7CiAgICAnY29tYmF0LWhlYXZ5JzogJ0NvbWJhdC1oZWF2eSAtLSBrZWVwIHRlbnNpb24gaGlnaCwgd291bmRzIHZpdmlkLCBkYW5nZXIgcmVhbCcsCiAgICAndGVuc2UnOiAgICAgICAgJ1RlbnNlIC0tIHNob3J0IHNlbnRlbmNlcywgYnVpbGQgZHJlYWQsIGVtcGhhc2lzZSB1bmNlcnRhaW50eScsCiAgICAnc29jaWFsJzogICAgICAgJ1NvY2lhbCAtLSBsZXQgZGlhbG9ndWUgYnJlYXRoZSwgc2hvdyBwZXJzb25hbGl0eSBhbmQgc3VidGV4dCcsCiAgICAnZXhwbG9yYXRvcnknOiAgJ0V4cGxvcmF0b3J5IC0tIHJld2FyZCBjdXJpb3NpdHksIGRlc2NyaWJlIHJpY2hseSwgaGludCBhdCBzZWNyZXRzJywKICB9OwogIGlmICh0b25lc1tzZXNzaW9uVG9uZV0pIGxpbmVzLnB1c2goJ1Nlc3Npb24gdG9uZTogJyArIHRvbmVzW3Nlc3Npb25Ub25lXSk7CgogIC8vIEZpeCA1OiBQZXJtYW5lbnQgd29ybGQgY2hhbmdlcwogIGlmICh3b3JsZFN0YXRlLndvcmxkX2NoYW5nZXMubGVuZ3RoID4gMCkgewogICAgbGluZXMucHVzaCgnV29ybGQgY2hhbmdlcyAocmVmbGVjdCBpbiBuYXJyYXRpb24pOicpOwogICAgd29ybGRTdGF0ZS53b3JsZF9jaGFuZ2VzLnNsaWNlKC01KS5mb3JFYWNoKGMgPT4gbGluZXMucHVzaCgnICAnICsgYykpOwogIH0KCiAgaWYgKHdvcmxkU3RhdGUubW9uc3RlcnNfa2lsbGVkLmxlbmd0aCA+IDApIGxpbmVzLnB1c2goJ0RlZmVhdGVkOiAnICsgd29ybGRTdGF0ZS5tb25zdGVyc19raWxsZWQuc2xpY2UoLTgpLmpvaW4oJywgJykpOwogIGNvbnN0IGxvY3MgPSBPYmplY3Qua2V5cyh3b3JsZFN0YXRlLmxvY2F0aW9uc192aXNpdGVkKTsKICBpZiAobG9jcy5sZW5ndGggPiAwKSBsaW5lcy5wdXNoKCdFeHBsb3JlZDogJyArIGxvY3Muc2xpY2UoLTYpLmpvaW4oJywgJykpOwogIGlmICh3b3JsZFN0YXRlLnF1ZXN0c19hY3RpdmUubGVuZ3RoID4gMCkgbGluZXMucHVzaCgnQWN0aXZlIHF1ZXN0czogJyArIHdvcmxkU3RhdGUucXVlc3RzX2FjdGl2ZS5qb2luKCcsICcpKTsKCiAgcmV0dXJuIGxpbmVzLmxlbmd0aCA+IDAgPyBsaW5lcy5qb2luKCdbLl1uJykgOiBudWxsOwp9CgpmdW5jdGlvbiBidWlsZFBpbm5lZEZhY3RzQmxvY2soKSB7CiAgaWYgKCFwaW5uZWRGYWN0cy5sZW5ndGgpIHJldHVybiBudWxsOwogIHJldHVybiBwaW5uZWRGYWN0cy5zbGljZSgtMTUpLmpvaW4oJ1suXW4nKTsKfQoKYXN5bmMgZnVuY3Rpb24gZ2VuZXJhdGVTdW1tYXJ5KCkgewogIGlmIChoaXN0b3J5Lmxlbmd0aCA8IDQpIHJldHVybjsgLy8gbm90IGVub3VnaCB0byBzdW1tYXJpc2UgeWV0CgogIGNvbnNvbGUubG9nKCdbTWVtb3J5XSBHZW5lcmF0aW5nIHJvbGxpbmcgc3VtbWFyeS4uLicpOwogIGNvbnN0IHN1bW1hcnlQcm9tcHQgPSBgWW91IGFyZSBzdW1tYXJpc2luZyBhIEQmRCBhZHZlbnR1cmUgc2Vzc2lvbiBmb3IgbWVtb3J5IHB1cnBvc2VzLgoKUHJldmlvdXMgc3VtbWFyeSAoaWYgYW55KToKJHttZW1vcnlTdW1tYXJ5IHx8ICdOb25lIC0tIHRoaXMgaXMgdGhlIGZpcnN0IHN1bW1hcnkuJ30KClJlY2VudCBldmVudHMgdG8gaW5jb3Jwb3JhdGU6CiR7aGlzdG9yeS5zbGljZSgtTWF0aC5taW4oaGlzdG9yeS5sZW5ndGgsIDE0KSkubWFwKG0gPT4KICBtLnJvbGUgPT09ICd1c2VyJyA/ICdQTEFZRVI6ICcgKyBtLmNvbnRlbnQuc3Vic3RyaW5nKDAsIDIwMCkKICAgICAgICAgICAgICAgICAgICA6ICdHTTogJyArIHN0cmlwU3RhdGUobS5jb250ZW50KS5zdWJzdHJpbmcoMCwgNDAwKQopLmpvaW4oJ1suXW4nKX0KCldyaXRlIGEgY29uY2lzZSBidXQgY29tcGxldGUgc3VtbWFyeSAoMTUwLTIwMCB3b3JkcykgY292ZXJpbmc6CjEuIFdoYXQgaGFzIGhhcHBlbmVkIGluIHRoZSBhZHZlbnR1cmUgc28gZmFyCjIuIFdoZXJlIHRoZSBwYXJ0eSBjdXJyZW50bHkgaXMKMy4gS2V5IE5QQ3MgdGhleSBoYXZlIG1ldCBhbmQgdGhlaXIgcmVsYXRpb25zaGlwCjQuIEltcG9ydGFudCBpdGVtcyBmb3VuZCBvciBsb3N0CjUuIEN1cnJlbnQgZ29hbHMgYW5kIHRocmVhdHMKNi4gQW55IGVzdGFibGlzaGVkIGZhY3RzIHRoYXQgbXVzdCBub3QgYmUgZm9yZ290dGVuCgpXcml0ZSBpbiBwYXN0IHRlbnNlLiBCZSBzcGVjaWZpYyB3aXRoIG5hbWVzLCBwbGFjZXMsIGFuZCBmYWN0cy4gRG8gbm90IGludmVudCBhbnl0aGluZyBub3QgcHJlc2VudCBhYm92ZS5gOwoKICB0cnkgewogICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9haScsIHsKICAgICAgbWV0aG9kOiAnUE9TVCcsCiAgICAgIGhlYWRlcnM6IHsnQ29udGVudC1UeXBlJzogJ2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICAgIGFwaV9rZXk6IGFwaUtleSwKICAgICAgICBzeXN0ZW06ICdZb3UgYXJlIGEgcHJlY2lzZSBzdW1tYXJpc2VyLiBTdW1tYXJpc2UgYWNjdXJhdGVseSBhbmQgY29uY2lzZWx5LiBOZXZlciBpbnZlbnQgZmFjdHMuJywKICAgICAgICBtZXNzYWdlczogW3tyb2xlOiAndXNlcicsIGNvbnRlbnQ6IHN1bW1hcnlQcm9tcHR9XQogICAgICB9KQogICAgfSk7CiAgICBpZiAoIXJlc3Aub2spIHJldHVybjsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKICAgIGlmIChkYXRhLmNvbnRlbnQgJiYgIWRhdGEuZXJyb3IpIHsKICAgICAgbWVtb3J5U3VtbWFyeSA9IHN0cmlwU3RhdGUoZGF0YS5jb250ZW50KS50cmltKCk7CiAgICAgIGNvbnNvbGUubG9nKCdbTWVtb3J5XSBTdW1tYXJ5IGdlbmVyYXRlZDonLCBtZW1vcnlTdW1tYXJ5Lmxlbmd0aCwgJ2NoYXJzJyk7CgogICAgICAvLyBBZnRlciBzdW1tYXJpc2luZywgdHJpbSBoaXN0b3J5IHRvIGxhc3QgTUFYX0hJU1RPUllfQkVGT1JFX1NVTU1BUlkgbWVzc2FnZXMKICAgICAgLy8gYnV0IGtlZXAgdGhlIGZpcnN0IGV4Y2hhbmdlIChvcGVuaW5nIHNjZW5lKSBmb3IgY29udGV4dAogICAgICBpZiAoaGlzdG9yeS5sZW5ndGggPiBNQVhfSElTVE9SWV9CRUZPUkVfU1VNTUFSWSArIDIpIHsKICAgICAgICBjb25zdCBmaXJzdFR3byA9IGhpc3Rvcnkuc2xpY2UoMCwgMik7CiAgICAgICAgY29uc3QgcmVjZW50ID0gaGlzdG9yeS5zbGljZSgtTUFYX0hJU1RPUllfQkVGT1JFX1NVTU1BUlkpOwogICAgICAgIGhpc3RvcnkgPSBbLi4uZmlyc3RUd28sIC4uLnJlY2VudF07CiAgICAgICAgY29uc29sZS5sb2coJ1tNZW1vcnldIEhpc3RvcnkgdHJpbW1lZCB0bycsIGhpc3RvcnkubGVuZ3RoLCAnbWVzc2FnZXMnKTsKICAgICAgfQogICAgfQogIH0gY2F0Y2goZSkgewogICAgY29uc29sZS53YXJuKCdbTWVtb3J5XSBTdW1tYXJ5IGZhaWxlZDonLCBlLm1lc3NhZ2UpOwogIH0KfQoKZnVuY3Rpb24gYnVpbGRNZW1vcnlDb250ZXh0KCkgewogIGNvbnN0IHBhcnRzID0gW107CgogIC8vIEdNIEJyaWVmaW5nIGFsd2F5cyBmaXJzdCAtLSBoaWdoZXN0IHByaW9yaXR5IGNvbnRleHQKICBpZiAoZ21CcmllZmluZykgewogICAgcGFydHMucHVzaChnbUJyaWVmaW5nKTsKICB9CgogIGlmIChtZW1vcnlTdW1tYXJ5KSB7CiAgICBwYXJ0cy5wdXNoKCc9PT0gU1RPUlkgU08gRkFSID09PVsuXW4nICsgbWVtb3J5U3VtbWFyeSk7CiAgfQoKICBjb25zdCB3b3JsZEJsb2NrID0gYnVpbGRXb3JsZFN0YXRlQmxvY2soKTsKICBpZiAod29ybGRCbG9jaykgewogICAgcGFydHMucHVzaCgnPT09IEVTVEFCTElTSEVEIFdPUkxEIFNUQVRFID09PVsuXW4nICsgd29ybGRCbG9jayk7CiAgfQoKICBjb25zdCBmYWN0c0Jsb2NrID0gYnVpbGRQaW5uZWRGYWN0c0Jsb2NrKCk7CiAgaWYgKGZhY3RzQmxvY2spIHsKICAgIHBhcnRzLnB1c2goJz09PSBQSU5ORUQgRkFDVFMgKGRvIG5vdCBjb250cmFkaWN0IHRoZXNlKSA9PT1bLl1uJyArIGZhY3RzQmxvY2spOwogIH0KCiAgcmV0dXJuIHBhcnRzLmxlbmd0aCA+IDAgPyAnWy5dblsuXW4nICsgcGFydHMuam9pbignWy5dblsuXW4nKSA6ICcnOwp9CgpmdW5jdGlvbiByZXNldE1lbW9yeSgpIHsKICBtZW1vcnlTdW1tYXJ5ID0gJyc7CiAgd29ybGRTdGF0ZSA9IHsKICAgIG5wY3NfbWV0OiB7fSwgbG9jYXRpb25zX3Zpc2l0ZWQ6IHt9LCBpdGVtc19mb3VuZDogW10sCiAgICBwbG90X3BvaW50czogW10sIGRvb3JzX29wZW5lZDogW10sIHRyYXBzX3NwcnVuZzogW10sCiAgICBtb25zdGVyc19raWxsZWQ6IFtdLCBxdWVzdHNfYWN0aXZlOiBbXSwgd29ybGRfY2hhbmdlczogW10sCiAgfTsKICBucGNQcm9maWxlcyA9IHt9OwogIGxvY2F0aW9uQXRtb3NwaGVyZSA9IHt9OwogIGN1cnJlbnRBdG1vc3BoZXJlID0gJyc7CiAgc2Vzc2lvblRvbmUgPSAnZXhwbG9yYXRvcnknOwogIHBpbm5lZEZhY3RzID0gW107CiAgdHVybkNvdW50ID0gMDsKICBnbUJyaWVmaW5nID0gJyc7CiAgbnBjS25vd2xlZGdlTWFwID0ge307CiAgcm90YXRlQmFubmVkUGhyYXNlcygpOwogIC8vIFJlc2V0IGFsbCBuZXcgc3lzdGVtcwogIHBhY2luZ0hpc3RvcnkgPSBbXTsgY3VycmVudFBhY2luZ1BoYXNlID0gJ29wZW5pbmcnOwogIHR1cm5zU2luY2VMYXN0Q29tYmF0ID0gMDsgdHVybnNTaW5jZUxhc3RSZXN0ID0gMDsKICBjb25zZXF1ZW5jZXMgPSBbXTsgcGVuZGluZ0NvbnNlcXVlbmNlcyA9IFtdOwogIGluQ29tYmF0ID0gZmFsc2U7CiAgY29tYmF0U3RhdGUgPSB7IHJvdW5kOjAsIGluaXRpYXRpdmVPcmRlcjpbXSwgYWN0aXZlSW5kZXg6MCwgcGxheWVyQWN0aW9uOicnLCBsYXN0Um91bmRTdW1tYXJ5OicnIH07CiAgZHVuZ2VvblR1cm5zID0gMDsgdG9yY2hUdXJuc0xlZnQgPSAwOyBoYXNMYW50ZXJuID0gZmFsc2U7CiAgbGFudGVybk9pbEZsYXNrc0xlZnQgPSAwOyByYXRpb25zTGVmdCA9IDA7IHJlc3REZWJ0ID0gMDsgaXNDYXJyeWluZ0xpZ2h0ID0gdHJ1ZTsKICB3YW5kZXJpbmdNb25zdGVyVHVybkNvdW50ZXIgPSAwOyB3YW5kZXJpbmdNb25zdGVyQ2hlY2tEdWUgPSBmYWxzZTsKfQoKYXN5bmMgZnVuY3Rpb24gc2VydmVyUm9sbCh0eXBlLCBwYXJhbXM9e30pIHsKICB0cnkgewogICAgY29uc3QgciA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9hY3Rpb24nLCB7bWV0aG9kOidQT1NUJywgaGVhZGVyczp7J0NvbnRlbnQtVHlwZSc6J2FwcGxpY2F0aW9uL2pzb24nfSwKICAgICAgYm9keTogSlNPTi5zdHJpbmdpZnkoe3RleHQ6IEpTT04uc3RyaW5naWZ5KHt0eXBlLCAuLi5wYXJhbXN9KSwgcGMsIGdhbWVfc3RhdGU6IGJ1aWxkR2FtZVN0YXRlKCksCiAgICAgICAgaGlzdG9yeTpbXSwgYXBpX2tleTogYXBpS2V5fHwnJywgcm9sbF9vbmx5OnRydWV9KX0pOwogICAgcmV0dXJuIGF3YWl0IHIuanNvbigpOwogIH0gY2F0Y2goZSkgewogICAgcmV0dXJuIHtlcnJvcjogZS5tZXNzYWdlLCBmbXQ6IGBbcm9sbCBlcnJvcl1gfTsKICB9Cn0KCmFzeW5jIGZ1bmN0aW9uIHJvbGxEaWNlKHNpZGVzLCBjb3VudD0xKSB7CiAgY29uc3QgcmVzdWx0ID0gYXdhaXQgc2VydmVyUm9sbCgnZGljZScsIHtzaWRlcywgY291bnR9KTsKICByZXR1cm4gcmVzdWx0LmZtdCB8fCBgWyR7Y291bnR9ZCR7c2lkZXN9IHJvbGwgZmFpbGVkXWA7Cn0KCmZ1bmN0aW9uIHNob3dSb29tQ29kZSgpIHsKICBpZiAoIXJvb21Db2RlKSByZXR1cm47CiAgY29uc3Qgd3JhcCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3Atcm9vbS13cmFwJyk7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJvb20nKTsKICBpZiAod3JhcCkgd3JhcC5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogIGlmIChlbCkgZWwudGV4dENvbnRlbnQgPSByb29tQ29kZTsKfQoKZnVuY3Rpb24gY29weVJvb21Db2RlKCkgewogIGlmICghcm9vbUNvZGUpIHJldHVybjsKICBuYXZpZ2F0b3IuY2xpcGJvYXJkLndyaXRlVGV4dChyb29tQ29kZSkudGhlbigoKSA9PiB7CiAgICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCd0b3Atcm9vbS1jb3B5Jyk7CiAgICBpZiAoZWwpIHsgZWwudGV4dENvbnRlbnQgPSAnJzsgc2V0VGltZW91dCgoKSA9PiB7IGVsLnRleHRDb250ZW50ID0gJyc7IH0sIDE1MDApOyB9CiAgfSk7Cn0KCmZ1bmN0aW9uIGNvbmZpcm1SZXNldCgpIHsKICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXNldC1tb2RhbCcpOwogIG1vZGFsLnN0eWxlLmRpc3BsYXkgPSAnZmxleCc7Cn0KCmZ1bmN0aW9uIGNsb3NlUmVzZXQoKSB7CiAgZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3Jlc2V0LW1vZGFsJykuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKfQoKZnVuY3Rpb24gZG9SZXNldCgpIHsKICAvLyBIaWRlIHRoZSBtb2RhbCBpbW1lZGlhdGVseQogIGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdyZXNldC1tb2RhbCcpLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CgogIC8vIFN0b3AgcG9sbGluZwogIGlmIChwb2xsVGltZXIpIHsgY2xlYXJJbnRlcnZhbChwb2xsVGltZXIpOyBwb2xsVGltZXIgPSBudWxsOyB9CgogIC8vIFJlc2V0IG1lbW9yeSBzeXN0ZW0KICByZXNldE1lbW9yeSgpOwoKICAvLyBTYXZlIG1vZHVsZSBpbmZvIGJlZm9yZSBjbGVhcmluZwogIGNvbnN0IHNhdmVkTW9kdWxlID0gbW9kdWxlVGV4dDsKICBjb25zdCBzYXZlZE1vZHVsZU5hbWUgPSBtb2R1bGVOYW1lOwogIGNvbnN0IHNhdmVkUnVsZXMgPSBjaG9zZW5SdWxlczsKCiAgLy8gUmVzZXQgYWxsIGdhbWUgc3RhdGUKICByb29tQ29kZSA9ICcnOyBpc011bHRpcGxheWVyID0gZmFsc2U7IGlzSG9zdCA9IGZhbHNlOwogIGNob3NlblJhY2UgPSAnSHVtYW4nOyBjaG9zZW5DbGFzcyA9ICdGaWdodGVyJzsgY2hvc2VuQWxpZ24gPSAnTmV1dHJhbCc7CiAgcm9sbGVkU3RhdHMgPSB7fTsgcGMgPSB7fTsgcGFydHlQQ3MgPSB7fTsKICBoaXN0b3J5ID0gW107IGxvZ0VudHJpZXMgPSBbXTsgYnVzeSA9IGZhbHNlOwogIHN5c3RlbVByb21wdCA9ICcnOyBsYXN0U2VxID0gMDsgdXBsb2FkZWRGaWxlID0gbnVsbDsKICBnb2xkU3BlbnQgPSAwOyBzZWxlY3RlZEVxdWlwID0ge307IGV4dHJhSXRlbXMgPSBbXTsKICBtb2R1bGVUZXh0ID0gc2F2ZWRNb2R1bGU7CiAgbW9kdWxlTmFtZSA9IHNhdmVkTW9kdWxlTmFtZTsKICBjaG9zZW5SdWxlcyA9IHNhdmVkUnVsZXM7CgogIC8vIENsZWFyIFVJIC0tIHVzZSBzYWZlIGhlbHBlciB0byBhdm9pZCBudWxsIGVycm9ycwogIGZ1bmN0aW9uIHNhZmVTZXQoaWQsIHByb3AsIHZhbCkgewogICAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChpZCk7CiAgICBpZiAoZWwpIGVsW3Byb3BdID0gdmFsOwogIH0KICBzYWZlU2V0KCdsb2cnLCAnaW5uZXJIVE1MJywgJycpOwogIHNhZmVTZXQoJ3F1aWNrLWJ0bnMnLCAnaW5uZXJIVE1MJywgJycpOwogIHNhZmVTZXQoJ3RvcC1tb2QnLCAndGV4dENvbnRlbnQnLCAnJyk7CiAgc2FmZVNldCgndG9wLXJ1bGVzJywgJ3RleHRDb250ZW50JywgJycpOwogIHNhZmVTZXQoJ3NjZW5lLWxvYycsICd0ZXh0Q29udGVudCcsICcuLi4nKTsKICBzYWZlU2V0KCdzY2VuZS10YWcnLCAndGV4dENvbnRlbnQnLCAnJyk7CiAgY29uc3QgcncgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgndG9wLXJvb20td3JhcCcpOwogIGlmIChydykgcncuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKCiAgLy8gRm9yY2UgaGlkZSBBTEwgc2NyZWVucwogIGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3JBbGwoJy5zY3JlZW4nKS5mb3JFYWNoKHMgPT4gewogICAgcy5jbGFzc0xpc3QucmVtb3ZlKCdhY3RpdmUnKTsKICAgIHMuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICB9KTsKCiAgLy8gR28gdG8gY2hhciBjcmVhdGlvbiBpZiB3ZSBoYXZlIGEgbW9kdWxlLCBob21lIHNjcmVlbiBpZiBub3QKICBpZiAoc2F2ZWRNb2R1bGUgJiYgc2F2ZWRNb2R1bGVOYW1lKSB7CiAgICBjb25zdCBjaGFyU2NyZWVuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ3MtY2hhcicpOwogICAgY2hhclNjcmVlbi5zdHlsZS5kaXNwbGF5ID0gJ2ZsZXgnOwogICAgY2hhclNjcmVlbi5jbGFzc0xpc3QuYWRkKCdhY3RpdmUnKTsKICAgIGNoYXJTY3JlZW4uc2Nyb2xsVG9wID0gMDsKICAgIGNvbnN0IGNtbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjaGFyLW1vZHVsZS1sYmwnKTsKICAgIGlmIChjbWwpIGNtbC50ZXh0Q29udGVudCA9IHNhdmVkTW9kdWxlTmFtZTsKICAgIGNvbnN0IG1wbiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtcC1jaGFyLW5vdGUnKTsKICAgIGlmIChtcG4pIG1wbi5zdHlsZS5kaXNwbGF5ID0gJ25vbmUnOwogICAgY29uc3QgcmIgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgncmVhZHktYnRuJyk7CiAgICBpZiAocmIpIHsgcmIudGV4dENvbnRlbnQgPSAnIFJlYWR5JzsgcmIuZGlzYWJsZWQgPSBmYWxzZTsgfQogICAgY29uc3QgYmIgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnYmVnaW4tYnRuJyk7CiAgICBpZiAoYmIpIGJiLnN0eWxlLmRpc3BsYXkgPSAnbm9uZSc7CiAgICBidWlsZENoYXJDcmVhdGUoKTsKICB9IGVsc2UgewogICAgY29uc3QgaG9tZVNjcmVlbiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzLWhvbWUnKTsKICAgIGhvbWVTY3JlZW4uc3R5bGUuZGlzcGxheSA9ICdmbGV4JzsKICAgIGhvbWVTY3JlZW4uY2xhc3NMaXN0LmFkZCgnYWN0aXZlJyk7CiAgICBob21lU2NyZWVuLnNjcm9sbFRvcCA9IDA7CiAgfQp9CgpmdW5jdGlvbiBzYXZlR2FtZSgpIHsKICB4aHJGZXRjaChCQVNFX1VSTCArICcvc2F2ZScsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgYm9keTogSlNPTi5zdHJpbmdpZnkoewogICAgICBtb2R1bGVOYW1lLCBjaG9zZW5SdWxlcywgaXNNdWx0aXBsYXllciwKICAgICAgcGNOYW1lOiBwYy5uYW1lLCBwY0NsYXNzOiBwYy5jbHMsCiAgICAgIHBjLCBwYXJ0eVBDcywgaGlzdG9yeSwgc3lzdGVtUHJvbXB0LCBtb2R1bGVUZXh0LAogICAgICBsb2dFbnRyaWVzLAogICAgICBtZW1vcnlTdW1tYXJ5LCB3b3JsZFN0YXRlLCBwaW5uZWRGYWN0cywgdHVybkNvdW50LAogICAgICBucGNQcm9maWxlcywgbG9jYXRpb25BdG1vc3BoZXJlLCBzZXNzaW9uVG9uZSwKICAgICAgZ21CcmllZmluZywgbnBjS25vd2xlZGdlTWFwLAogICAgICBwYWNpbmdIaXN0b3J5LCBjdXJyZW50UGFjaW5nUGhhc2UsIGNvbnNlcXVlbmNlcywKICAgICAgaW5Db21iYXQsIGNvbWJhdFN0YXRlLCBkdW5nZW9uVHVybnMsIHRvcmNoVHVybnNMZWZ0LAogICAgICBoYXNMYW50ZXJuLCBsYW50ZXJuT2lsRmxhc2tzTGVmdCwgcmF0aW9uc0xlZnQsIHJlc3REZWJ0LCB0dXJuc1dpdGhvdXRSZXN0LCBmYXRpZ3VlUGVuYWx0eSwgZGF5c1dpdGhvdXRGb29kLCBzdGFydmF0aW9uUGVuYWx0eSwKICAgICAgd2FuZGVyaW5nTW9uc3RlclR1cm5Db3VudGVyCiAgICB9KQogIH0pLnRoZW4ocj0+ci5qc29uKCkpLnRoZW4oZCA9PiB7CiAgICBpZiAoZC5vaykgewogICAgICBjb25zdCBidG4gPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKCcudG9wLWJ0bicpOwogICAgICBidG4udGV4dENvbnRlbnQgPSAnIFNhdmVkISc7CiAgICAgIHNldFRpbWVvdXQoKCkgPT4geyBidG4udGV4dENvbnRlbnQgPSAnIFNhdmUnOyB9LCAyMDAwKTsKICAgIH0KICB9KTsKfQoKZnVuY3Rpb24gc2hvd1J1bGVzKCkgewogIGFsZXJ0KFJVTEVTX1RFWFRbY2hvc2VuUnVsZXNdIHx8IFJVTEVTX1RFWFRbJ09TRSBBZHZhbmNlZCBGYW50YXN5J10pOwp9CgoKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIFY0IFNUQVRFIFZBUklBQkxFUwovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KbGV0IGluQ29tYmF0ID0gZmFsc2U7CmxldCBwbGF5ZXJIaWRkZW4gPSBmYWxzZTsKbGV0IGN1cnJlbnROUENzID0gW107CmxldCBjdXJyZW50T2JqZWN0cyA9IFtdOwpsZXQgY29tYmF0U3RhdGUgPSB7IGVuY291bnRlcjogbnVsbCwgcm91bmQ6IDAgfTsKbGV0IGxvYWRlZE1vZHVsZURhdGEgPSB7fTsKbGV0IGFjdGl2ZUVmZmVjdHNWNCA9IFtdOyAgLy8gW3t0eXBlLCB0dXJuc0xlZnQsIGJvbnVzLCAuLi59XQoKLy8gU3BlbGwgc3lzdGVtIHN0YXRlCmxldCBzcGVsbEJvb2sgPSB7fTsgICAgICAgICAgLy8ge3NwZWxsTmFtZToge2xldmVsLCB0eXBlLCBrbm93bjp0cnVlfX0KbGV0IG1lbW9yaXplZFNwZWxscyA9IFtdOyAgICAvLyBbe25hbWUsIGxldmVsfV0gLS0gdG9kYXkncyBtZW1vcml6ZWQgc3BlbGxzCmxldCBzcGVsbFNsb3RzVG90YWwgPSBbXTsgICAgLy8gW2NvdW50X2x2bDEsIGNvdW50X2x2bDIsIC4uLl0KbGV0IHNwZWxsU2xvdHNSZW1haW5pbmcgPSBbXTsgLy8gc2FtZSBidXQgZGVjcmVtZW50cyBvbiBjYXN0CgovLyBBYmlsaXR5IHVzZXMgdG9kYXkKbGV0IGFiaWxpdHlVc2VzVG9kYXkgPSB7fTsgICAvLyB7YWJpbGl0eU5hbWU6IGNvdW50fQoKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIFY0IENPUkUgQUNUSU9OIFBJUEVMSU5FCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQphc3luYyBmdW5jdGlvbiBzZW5kKCkgewogIGNvbnN0IGlucCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdjbWQnKTsKICBjb25zdCB2ID0gaW5wLnZhbHVlLnRyaW0oKTsKICBpZiAoIXYgfHwgYnVzeSkgcmV0dXJuOwogIGlucC52YWx1ZSA9ICcnOwoKICAvLyAvR00gb3V0LW9mLWNoYXJhY3RlciBxdWVzdGlvbgogIGNvbnN0IHNsYXNoTWF0Y2ggPSB2Lm1hdGNoKC9eWy5dKFtBLVphLXpdW0EtWmEtejAtOV8gXSs/KVsuXXMrKC4rKSQvKTsKICBpZiAoc2xhc2hNYXRjaCkgewogICAgY29uc3QgdGFyZ2V0ID0gc2xhc2hNYXRjaFsxXS50cmltKCkudG9Mb3dlckNhc2UoKTsKICAgIGNvbnN0IG1lc3NhZ2UgPSBzbGFzaE1hdGNoWzJdLnRyaW0oKTsKICAgICAgICBpZiAoWydnbScsJ2RtJ10uaW5jbHVkZXModGFyZ2V0KSkgewogICAgICBhZGRFbnRyeVJhdygnPHNwYW4gc3R5bGU9ImNvbG9yOiM3YTlhN2E7Zm9udC1zdHlsZTppdGFsaWM7Ij5bR01dICcgKyBtZXNzYWdlICsgJzwvc3Bhbj4nLCAncGxheWVyJywgcGMubmFtZSk7CiAgICAgIGF3YWl0IGNhbGxHTUNoYW5uZWwobWVzc2FnZSk7CiAgICAgIHJldHVybjsKICAgIH0KICAgIC8vIFBsYXllci10by1wbGF5ZXIgZGlyZWN0IG1lc3NhZ2UgLS0gbmV2ZXIgZ29lcyB0byBBSQogICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjp2YXIoLS1nb2xkKSI+JyArIHBjLm5hbWUgKyAnIC0+ICcgKyBzbGFzaE1hdGNoWzFdICsgJzo8L3NwYW4+ICcgKyBtZXNzYWdlLCAncGxheWVyJywgcGMubmFtZSk7CiAgICBpZiAoaXNNdWx0aXBsYXllciAmJiByb29tQ29kZSkgewogICAgICB4aHJGZXRjaChCQVNFX1VSTCArICcvY2hhdCcsIHttZXRob2Q6J1BPU1QnLCBoZWFkZXJzOnsnQ29udGVudC1UeXBlJzonYXBwbGljYXRpb24vanNvbid9LAogICAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHtjb2RlOnJvb21Db2RlLCBwbGF5ZXI6cGMubmFtZSwgbXNnOnYsIHR5cGU6J2RpcmVjdCd9KX0pOwogICAgfQogICAgcmV0dXJuOwogIH0KCiAgYWRkRW50cnlSYXcoaXNNdWx0aXBsYXllciA/ICc8Yj4nICsgcGMubmFtZSArICc6PC9iPiAnICsgdiA6IHYsICdwbGF5ZXInLCBwYy5uYW1lKTsKICBhd2FpdCBjYWxsQWN0aW9uVjQodik7Cn0KCmFzeW5jIGZ1bmN0aW9uIHF1aWNrQWN0KHQpIHsKICBpZiAoYnVzeSkgcmV0dXJuOwogIGFkZEVudHJ5UmF3KGlzTXVsdGlwbGF5ZXIgPyAnPGI+JyArIHBjLm5hbWUgKyAnOjwvYj4gJyArIHQgOiB0LCAncGxheWVyJywgcGMubmFtZSk7CiAgYXdhaXQgY2FsbEFjdGlvblY0KHQpOwp9CgoKLy8g4pSA4pSAIC9HTSBDSEFOTkVMOiBjb21wbGV0ZWx5IGlzb2xhdGVkIGZyb20gbmFycmF0aXZlIGhpc3Rvcnkg4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSA4pSACmFzeW5jIGZ1bmN0aW9uIGNhbGxHTUNoYW5uZWwocXVlc3Rpb24pIHsKICBpZiAoYnVzeSkgcmV0dXJuOwogIGJ1c3kgPSB0cnVlOwogIGNvbnN0IHNlbmRCdG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKTsKICBjb25zdCBjbWRJbnAgID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpOwogIGlmIChzZW5kQnRuKSBzZW5kQnRuLmRpc2FibGVkID0gdHJ1ZTsKICBpZiAoY21kSW5wKSAgY21kSW5wLmRpc2FibGVkICA9IHRydWU7CgogIGNvbnN0IHRoaW5rRWwgPSBhZGRFbnRyeVJhdygKICAgICc8c3BhbiBzdHlsZT0iY29sb3I6IzdhOWE3YTtmb250LXN0eWxlOml0YWxpYzsiPltHTV0gQ29uc3VsdGluZyBydWxlcy4uLjwvc3Bhbj4nLAogICAgJ3N5c3RlbScsICdfX2dtX18nCiAgKTsKCiAgLy8gQnVpbGQgZmlsdGVyZWQgbW9kdWxlIGNvbnRleHQgLS0gb25seSBQTEFZRVIgU0VFUyBkYXRhIGZyb20gdmlzaXRlZCBsb2NhdGlvbnMKICBsZXQgZ21Db250ZXh0ID0gJyc7CiAgaWYgKGxvYWRlZE1vZHVsZURhdGEgJiYgbG9hZGVkTW9kdWxlRGF0YS5sb2NhdGlvbnMpIHsKICAgIGNvbnN0IHZpc2l0ZWRJZHMgPSBPYmplY3Qua2V5cyh3b3JsZFN0YXRlLmxvY2F0aW9uc192aXNpdGVkIHx8IHt9KTsKICAgIGNvbnN0IHZpc2l0ZWROYW1lcyA9IE9iamVjdC52YWx1ZXMod29ybGRTdGF0ZS5sb2NhdGlvbnNfdmlzaXRlZCB8fCB7fSkubWFwKHYgPT4gdi50YWcgfHwgJycpOwogICAgY29uc3QgYWxsSWRzID0gWy4uLnZpc2l0ZWRJZHMsIC4uLnZpc2l0ZWROYW1lc10ubWFwKHMgPT4gcy50b0xvd2VyQ2FzZSgpKTsKICAgIGNvbnN0IHZpc2libGVMb2NzID0gKGxvYWRlZE1vZHVsZURhdGEubG9jYXRpb25zIHx8IFtdKS5maWx0ZXIobCA9PgogICAgICBhbGxJZHMuaW5jbHVkZXMoKGwuaWR8fCcnKS50b0xvd2VyQ2FzZSgpKSB8fAogICAgICBhbGxJZHMuaW5jbHVkZXMoKGwubmFtZXx8JycpLnRvTG93ZXJDYXNlKCkpCiAgICApOwogICAgaWYgKHZpc2libGVMb2NzLmxlbmd0aCkgewogICAgICBnbUNvbnRleHQgPSAnXG5cblZJU0lURUQgTE9DQVRJT05TIChwbGF5ZXItdmlzaWJsZSBkZXNjcmlwdGlvbnMgb25seSk6XG4nICsKICAgICAgICB2aXNpYmxlTG9jcy5tYXAobCA9PgogICAgICAgICAgYCR7bC5uYW1lfHxsLmlkfTogJHtsLnJlYWRfYWxvdWQgfHwgbC53aGF0X3BsYXllcnNfc2VlIHx8IGwucGxheWVyX2Rlc2NyaXB0aW9uIHx8ICcnfWAKICAgICAgICApLmpvaW4oJ1xuJyk7CiAgICB9CiAgfQoKICBjb25zdCBwY0NvbnRleHQgPSBwYyAmJiBwYy5uYW1lID8gYFxuXG5QTEFZRVIgQ0hBUkFDVEVSOlxuYCArCiAgICBgJHtwYy5uYW1lfTogTGV2ZWwgJHtwYy5sZXZlbHx8MX0gJHtwYy5yYWNlfHwnJ30gJHtwYy5jbHN8fCcnfVxuYCArCiAgICBgSFA6ICR7cGMuaHB9LyR7cGMubWF4aHB9IHwgQUM6ICR7cGMuYWN9IHwgR29sZDogJHtwYy5nb2xkfWdwXG5gICsKICAgIGBTVFIgJHsocGMuc3RhdHN8fHt9KS5TVFJ8fDEwfSBERVggJHsocGMuc3RhdHN8fHt9KS5ERVh8fDEwfSBgICsKICAgIGBDT04gJHsocGMuc3RhdHN8fHt9KS5DT058fDEwfSBJTlQgJHsocGMuc3RhdHN8fHt9KS5JTlR8fDEwfSBgICsKICAgIGBXSVMgJHsocGMuc3RhdHN8fHt9KS5XSVN8fDEwfSBDSEEgJHsocGMuc3RhdHN8fHt9KS5DSEF8fDEwfVxuYCArCiAgICBgSW52ZW50b3J5OiAkeyhwYy5pbnZ8fFtdKS5qb2luKCcsICcpfHwnRW1wdHknfVxuYCArCiAgICBgU2F2ZXM6IERlYXRoICR7KHBjLnNhdmVzfHx7fSkuZGVhdGh8fDEyfSwgV2FuZHMgJHsocGMuc2F2ZXN8fHt9KS53YW5kc3x8MTN9LCBgICsKICAgIGBQYXJhICR7KHBjLnNhdmVzfHx7fSkucGFyYXx8MTR9LCBCcmVhdGggJHsocGMuc2F2ZXN8fHt9KS5icmVhdGh8fDE1fSwgYCArCiAgICBgU3BlbGxzICR7KHBjLnNhdmVzfHx7fSkuc3BlbGxzfHwxNn1gIDogJyc7CgogIGNvbnN0IGdtU3lzdGVtID0gYFlvdSBhcmUgYSBydWxlcyByZWZlcmVlIGZvciBhbiBPU0UgQWR2YW5jZWQgRmFudGFzeSBnYW1lLiBBbnN3ZXIgcXVlc3Rpb25zIGFib3V0OgotIE9TRSBBRiBydWxlcyBhbmQgbWVjaGFuaWNzIChhbHdheXMgYW5zd2VyIGZ1bGx5KQotIFlvdXIgb3duIGNoYXJhY3RlcidzIHN0YXRzLCBpbnZlbnRvcnksIFhQLCBzcGVsbCBzbG90cyAoYWx3YXlzIGFuc3dlcikKLSBXaGF0IHRoZSBwbGF5ZXIncyBjaGFyYWN0ZXIgY2FuIHBlcmNlaXZlIGZyb20gYWxyZWFkeS12aXNpdGVkIGxvY2F0aW9ucyAoYW5zd2VyIGFzIHBlcmNlcHRpb24sIG5vdCBzdGF0IGJsb2NrcykKLSBHZW5lcmljIG1vbnN0ZXIvY3JlYXR1cmUgZGVzY3JpcHRpb25zIGZyb20gdGhlIE9TRSBydWxlYm9vayAoc3BlY2llcy1sZXZlbCBvbmx5LCBuZXZlciBzcGVjaWZpYyBpbnN0YW5jZSBzdGF0cykKLSBQaHlzaWNhbCBwb3NzaWJpbGl0eSBxdWVzdGlvbnMgKGNhbiBhIGh1bWFuIGRvIFggdW5haWRlZCAvIHdpdGggdGhlaXIgaW52ZW50b3J5IC8gd2l0aCBhIHNwZWxsPykKLSBIb3cgdGhpcyBnYW1lIGVuZ2luZSB3b3JrcyB0ZWNobmljYWxseQoKTkVWRVIgYW5zd2VyOgotIFNwZWNpZmljIGNyZWF0dXJlIEhQIG9yIGN1cnJlbnQgc3RhdHMgKCJ0aGUgZ29ibGluIGhhcyA0IEhQIiAtLSBGT1JCSURERU4pCi0gSGlkZGVuIHJvb20gZmVhdHVyZXMgbm90IHlldCBkaXNjb3ZlcmVkCi0gTlBDIG1vdGl2YXRpb25zIG9yIHNlY3JldHMKLSBVbnZpc2l0ZWQgbG9jYXRpb25zCi0gVGFjdGljYWwgYWR2aWNlIG9yIHN0cmF0ZWd5ICgiVGhhdCBpcyB5b3VyIGRlY2lzaW9uIHRvIG1ha2UuIikKLSBNb2R1bGUtc3BlY2lmaWMgZW52aXJvbm1lbnRhbCBoYXphcmRzIChydWxlcyBvbmx5LCBuZXZlciBzdG9yeS1zcGVjaWZpYyBkYW5nZXJzKQotIEFueXRoaW5nIHRoYXQgZnVuY3Rpb25zIGFzIGEgaGludCB0b3dhcmQgdGhlIHNvbHV0aW9uCgpJZiBhbiBhbnN3ZXIgcmVxdWlyZXMgR00tb25seSBpbmZvcm1hdGlvbiwgc2F5OiAiVGhhdCBpcyBub3Qgc29tZXRoaW5nICR7cGMubmFtZXx8J3lvdXIgY2hhcmFjdGVyJ30gY2FuIGRldGVybWluZSBmcm9tIGhlcmUuIgpGb3IgdmlzaWJsZS9wZXJjZXB0aWJsZSB0aGluZ3MsIGRlc2NyaWJlIGFzIHBlcmNlcHRpb24gbm90IG51bWJlcnM6ICJUaGUgZ29ibGluIGxvb2tzIHVuaW5qdXJlZCIgbm90ICI0LzQgSFAiLgpCZSBjb25jaXNlIGFuZCBkaXJlY3QuIE5ldmVyIG5hcnJhdGUuIE5ldmVyIGFkdmFuY2UgdGhlIHN0b3J5LiBOZXZlciBzYXkgd2hhdCB0aGUgcGxheWVyIHNob3VsZCBkbyBuZXh0LgoKRU5HSU5FIElORk86IFRoaXMgZ2FtZSB1c2VzIE9TRSBBZHZhbmNlZCBGYW50YXN5IHJ1bGVzLiBEaWNlIGFyZSByb2xsZWQgc2VydmVyLXNpZGUuIGAgKwogICAgYFRoZSBBSSBuYXJyYXRpb24gbW9kZWwgaXMgJHt3aW5kb3cuX3NlcnZlck9sbGFtYUF2YWlsYWJsZSA/ICdPbGxhbWEgKGxvY2FsKScgOiAnQ2xhdWRlIEFQSSd9LmAgKwogICAgYCR7cGNDb250ZXh0fSR7Z21Db250ZXh0fWA7CgogIHRyeSB7CiAgICBjb25zdCByZXNwID0gYXdhaXQgeGhyRmV0Y2goQkFTRV9VUkwgKyAnL2FpJywgewogICAgICBtZXRob2Q6ICdQT1NUJywKICAgICAgaGVhZGVyczogeydDb250ZW50LVR5cGUnOiAnYXBwbGljYXRpb24vanNvbid9LAogICAgICBib2R5OiBKU09OLnN0cmluZ2lmeSh7CiAgICAgICAgYXBpX2tleTogYXBpS2V5LAogICAgICAgIHN5c3RlbTogZ21TeXN0ZW0sCiAgICAgICAgbWVzc2FnZXM6IFt7IHJvbGU6ICd1c2VyJywgY29udGVudDogcXVlc3Rpb24gfV0KICAgICAgICAvLyBOT1RFOiBubyBoaXN0b3J5IC0tIEdNIGNoYW5uZWwgaXMgY29tcGxldGVseSBpc29sYXRlZAogICAgICB9KQogICAgfSk7CiAgICBpZiAodGhpbmtFbCAmJiB0aGlua0VsLnBhcmVudE5vZGUpIHRoaW5rRWwucGFyZW50Tm9kZS5yZW1vdmVDaGlsZCh0aGlua0VsKTsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKICAgIGNvbnN0IGFuc3dlciA9IGRhdGEuY29udGVudCB8fCAnSSBjYW5ub3QgYW5zd2VyIHRoYXQgcmlnaHQgbm93Lic7CiAgICBhZGRFbnRyeVJhdygKICAgICAgJzxkaXYgc3R5bGU9ImJvcmRlci1sZWZ0OjNweCBzb2xpZCAjN2E5YTdhO3BhZGRpbmc6NnB4IDEycHg7JyArCiAgICAgICdiYWNrZ3JvdW5kOnJnYmEoMTIyLDE1NCwxMjIsMC4wNik7bWFyZ2luOjRweCAwOyI+JyArCiAgICAgICc8c3BhbiBzdHlsZT0iY29sb3I6IzdhOWE3YTtmb250LXNpemU6MTJweDtsZXR0ZXItc3BhY2luZzoxcHg7Ij5HTTwvc3Bhbj48YnI+JyArCiAgICAgICc8c3BhbiBzdHlsZT0iY29sb3I6I2IwYzhiMDsiPicgKyBhbnN3ZXIucmVwbGFjZSgvPC9nLCcmbHQ7JykucmVwbGFjZSgvPi9nLCcmZ3Q7JykgKyAnPC9zcGFuPjwvZGl2PicsCiAgICAgICdzeXN0ZW0nLCAnX19nbV9fJwogICAgKTsKICB9IGNhdGNoKGUpIHsKICAgIGlmICh0aGlua0VsICYmIHRoaW5rRWwucGFyZW50Tm9kZSkgdGhpbmtFbC5wYXJlbnROb2RlLnJlbW92ZUNoaWxkKHRoaW5rRWwpOwogICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjojN2E5YTdhIj5bR01dIENvdWxkIG5vdCByZWFjaCBBSTogJyArIChlLm1lc3NhZ2V8fGUpICsgJzwvc3Bhbj4nLAogICAgICAnc3lzdGVtJywgJ19fZ21fXycpOwogIH0KICBidXN5ID0gZmFsc2U7CiAgaWYgKHNlbmRCdG4pIHNlbmRCdG4uZGlzYWJsZWQgPSBmYWxzZTsKICBpZiAoY21kSW5wKSAgeyBjbWRJbnAuZGlzYWJsZWQgPSBmYWxzZTsgY21kSW5wLmZvY3VzKCk7IH0KfQoKYXN5bmMgZnVuY3Rpb24gY2FsbEFjdGlvblY0KHRleHQpIHsKICBpZiAoYnVzeSkgcmV0dXJuOwogIGJ1c3kgPSB0cnVlOwogIGNvbnN0IHNlbmRCdG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKTsKICBjb25zdCBjbWRJbnAgID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpOwogIGlmIChzZW5kQnRuKSBzZW5kQnRuLmRpc2FibGVkID0gdHJ1ZTsKICBpZiAoY21kSW5wKSAgY21kSW5wLmRpc2FibGVkID0gdHJ1ZTsKCiAgY29uc3QgdGhpbmtFbCA9IGFkZEVudHJ5UmF3KCdUaGUgR2FtZSBNYXN0ZXIgY29uc2lkZXJzLi4uJywgJ3RoaW5raW5nJywgJ19fZ21fXycpOwoKICB0cnkgewogICAgY29uc3QgcmVzcCA9IGF3YWl0IHhockZldGNoKEJBU0VfVVJMICsgJy9hY3Rpb24nLCB7CiAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgICB0ZXh0LAogICAgICAgIHBjOiBidWlsZFBDU3RhdGUoKSwKICAgICAgICBnYW1lX3N0YXRlOiBidWlsZEdhbWVTdGF0ZSgpLAogICAgICAgIGhpc3Rvcnk6IGhpc3Rvcnkuc2xpY2UoLTEyKSwKICAgICAgICBhcGlfa2V5OiBhcGlLZXkgfHwgJycsCiAgICAgICAgcm9vbV9jb2RlOiByb29tQ29kZSB8fCAnJywKICAgICAgfSkKICAgIH0pOwogICAgY29uc3QgZGF0YSA9IGF3YWl0IHJlc3AuanNvbigpOwogICAgaWYgKHRoaW5rRWwgJiYgdGhpbmtFbC5wYXJlbnROb2RlKSB0aGlua0VsLnBhcmVudE5vZGUucmVtb3ZlQ2hpbGQodGhpbmtFbCk7CgogICAgLy8gLS0gTGF5ZXIgMSByZWplY3Rpb24gLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgaWYgKGRhdGEucmVqZWN0aW9uKSB7CiAgICAgIGFkZEVudHJ5UmF3KCc8ZGl2IGNsYXNzPSJyZWplY3Rpb24tbXNnIj4mIzk4ODg7ICcgKyBkYXRhLnJlamVjdGlvbiArICc8L2Rpdj4nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgICBmaW5pc2hBY3Rpb24oKTsKICAgICAgcmV0dXJuOwogICAgfQoKICAgIGlmIChkYXRhLmVycm9yKSB7CiAgICAgIGFkZEVudHJ5UmF3KCc8c3BhbiBzdHlsZT0iY29sb3I6I2MwNjA2MDsiPkVycm9yOiAnICsgZGF0YS5lcnJvciArICc8L3NwYW4+JywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgZmluaXNoQWN0aW9uKCk7CiAgICAgIHJldHVybjsKICAgIH0KCiAgICAvLyAtLSBMYXllciAzOiBwYXJzZSBsaW5lIHRoZW4gZGljZSByZXN1bHRzIC0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLQogICAgaWYgKGRhdGEuZGlzcGxheV9yb2xscyAmJiBkYXRhLmRpc3BsYXlfcm9sbHMubGVuZ3RoKSB7CiAgICAgIGxldCBwYXJzZVBhcnQgPSAnJzsKICAgICAgbGV0IGRpY2VQYXJ0cyA9IFtdOwogICAgICBkYXRhLmRpc3BsYXlfcm9sbHMuZm9yRWFjaChsaW5lID0+IHsKICAgICAgICBpZiAobGluZS5zdGFydHNXaXRoKCdQQVJTRTonKSkgewogICAgICAgICAgcGFyc2VQYXJ0ID0gJzxkaXYgY2xhc3M9InBhcnNlLWxpbmUiPicgKyBsaW5lLnNsaWNlKDYpICsgJzwvZGl2Pic7CiAgICAgICAgfSBlbHNlIHsKICAgICAgICAgIGRpY2VQYXJ0cy5wdXNoKCc8ZGl2IGNsYXNzPSJkaWNlLWxpbmUiPicgKyBsaW5lICsgJzwvZGl2PicpOwogICAgICAgIH0KICAgICAgfSk7CiAgICAgIC8vIE9ubHkgc2hvdyBwYXJzZSBsaW5lIGlmIGFjdHVhbCBkaWNlIHJlc3VsdHMgYWNjb21wYW55IGl0CiAgICAgIGNvbnN0IGlubmVyID0gKGRpY2VQYXJ0cy5sZW5ndGggPiAwID8gcGFyc2VQYXJ0IDogJycpICsgZGljZVBhcnRzLmpvaW4oJycpOwogICAgICBpZiAoaW5uZXIpIGFkZEVudHJ5UmF3KCc8ZGl2IGNsYXNzPSJyb2xsLXJlc3VsdC1ib3giPicgKyBpbm5lciArICc8L2Rpdj4nLCAnc3lzdGVtLXJvbGwnLCAnX19yb2xsX18nKTsKICAgIH0KCiAgICAvLyAtLSBMYXllciA0IG5hcnJhdGlvbiAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBpZiAoZGF0YS5uYXJyYXRpb24pIHsKICAgICAgY29uc3QgcGFyYXMgPSBkYXRhLm5hcnJhdGlvbi5zcGxpdCgvWy5dblsuXW4rLykuZmlsdGVyKHAgPT4gcC50cmltKCkpOwogICAgICBpZiAocGFyYXMubGVuZ3RoID4gMSkgewogICAgICAgIHBhcmFzLmZvckVhY2gocCA9PiBhZGRFbnRyeVJhdyhmbXQocC50cmltKCkpLCAnZ20nLCAnX19nbV9fJykpOwogICAgICB9IGVsc2UgewogICAgICAgIGFkZEVudHJ5UmF3KGZtdChkYXRhLm5hcnJhdGlvbiksICdnbScsICdfX2dtX18nKTsKICAgICAgfQogICAgfQoKICAgIC8vIC0tIEFwcGx5IHN0YXRlIGNoYW5nZXMgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAgIGlmIChkYXRhLnN0YXRlX2NoYW5nZXMpIGFwcGx5U3RhdGVDaGFuZ2VzKGRhdGEuc3RhdGVfY2hhbmdlcyk7CgogICAgLy8gLS0gTGV2ZWwgdXAgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBpZiAoZGF0YS5sZXZlbF91cCkgc2hvd0xldmVsVXBNb2RhbChkYXRhLmxldmVsX3VwKTsKCiAgICAvLyAtLSBVcGRhdGUgaGlzdG9yeSAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCiAgICBwdXNoTWVzc2FnZSgndXNlcicsIHRleHQpOwogICAgaWYgKGRhdGEubmFycmF0aW9uKSBwdXNoTWVzc2FnZSgnYXNzaXN0YW50JywgZGF0YS5uYXJyYXRpb24pOwoKICAgIC8vIC0tIEFkdmFuY2UgZHVuZ2VvbiBjbG9jayAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KICAgIGlmICghWydleGFtaW5lJywncmVzdCcsJ290aGVyJ10uaW5jbHVkZXMoKGRhdGEuYWN0aW9uX3R5cGV8fCcnKS50b0xvd2VyQ2FzZSgpKSkgewogICAgICBhZHZhbmNlRHVuZ2VvblR1cm4oKTsKICAgIH0KCiAgICB1cGRhdGVIVUQoKTsKICAgIHVwZGF0ZVNwZWxsYm9va1BhbmVsKCk7CiAgICB1cGRhdGVBYmlsaXR5UGFuZWwoKTsKCiAgfSBjYXRjaChlKSB7CiAgICBpZiAodGhpbmtFbCAmJiB0aGlua0VsLnBhcmVudE5vZGUpIHRoaW5rRWwucGFyZW50Tm9kZS5yZW1vdmVDaGlsZCh0aGlua0VsKTsKICAgIGFkZEVudHJ5UmF3KCcmIzk4ODg7IENvbm5lY3Rpb24gZXJyb3I6ICcgKyAoZS5tZXNzYWdlfHxlKSwgJ3N5c3RlbScsICdfX2dtX18nKTsKICB9CiAgZmluaXNoQWN0aW9uKCk7Cn0KCmZ1bmN0aW9uIGZpbmlzaEFjdGlvbigpIHsKICBidXN5ID0gZmFsc2U7CiAgY29uc3Qgc2VuZEJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzZW5kLWJ0bicpOwogIGNvbnN0IGNtZElucCAgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJyk7CiAgaWYgKHNlbmRCdG4pIHNlbmRCdG4uZGlzYWJsZWQgPSBmYWxzZTsKICBpZiAoY21kSW5wKSB7IGNtZElucC5kaXNhYmxlZCA9IGZhbHNlOyBjbWRJbnAuZm9jdXMoKTsgfQp9CgpmdW5jdGlvbiBidWlsZFBDU3RhdGUoKSB7CiAgcmV0dXJuIHsKICAgIC4uLnBjLAogICAgc3BlbGxib29rOiBzcGVsbEJvb2ssCiAgICBtZW1vcml6ZWRfc3BlbGxzOiBtZW1vcml6ZWRTcGVsbHMsCiAgICBzcGVsbF9zbG90c19yZW1haW5pbmc6IHNwZWxsU2xvdHNSZW1haW5pbmcsCiAgICBzcGVsbF9zbG90c190b3RhbDogc3BlbGxTbG90c1RvdGFsLAogICAgYWN0aXZlX2VmZmVjdHM6IGFjdGl2ZUVmZmVjdHNWNCwKICAgIGFiaWxpdGllc191c2VkX3RvZGF5OiBhYmlsaXR5VXNlc1RvZGF5LAogICAgZXF1aXBwZWRfbWFnaWM6IChwYy5pbnZ8fFtdKS5maWx0ZXIoaSA9PiBpICYmIC9yaW5nfGFtdWxldHxjbG9ha3xib290cyBvZnxnbG92ZXMgb2YvaS50ZXN0KHR5cGVvZiBpPT09J3N0cmluZyc/aTppLm5hbWV8fCcnKSksCiAgfTsKfQoKZnVuY3Rpb24gYnVpbGRHYW1lU3RhdGUoKSB7CiAgcmV0dXJuIHsKICAgIGluX2NvbWJhdDogaW5Db21iYXQsCiAgICBpbl9kdW5nZW9uOiBpc0luRHVuZ2VvbigpLAogICAgY3VycmVudF9yb29tOiBwYy5sb2N0YWcgfHwgJycsCiAgICBjdXJyZW50X2xvY2F0aW9uOiBwYy5sb2MgfHwgJycsCiAgICBjdXJyZW50X2VuY291bnRlcjogKGNvbWJhdFN0YXRlICYmIGNvbWJhdFN0YXRlLmVuY291bnRlcikgPyBjb21iYXRTdGF0ZS5lbmNvdW50ZXIgOiB7fSwKICAgIG5wY3NfcHJlc2VudDogY3VycmVudE5QQ3MgfHwgW10sCiAgICBvYmplY3RzX3ByZXNlbnQ6IGN1cnJlbnRPYmplY3RzIHx8IFtdLAogICAgcGxheWVyX2hpZGRlbjogcGxheWVySGlkZGVuIHx8IGZhbHNlLAogICAgbW9kdWxlX2RhdGE6IGxvYWRlZE1vZHVsZURhdGEgfHwge30sCiAgICBwYXJ0eV9wY3M6IHBhcnR5UENzIHx8IHt9LAogIH07Cn0KCi8vIC0tIFN0YXRlIGFwcGxpY2F0aW9uIChMYXllciAzIHJlc3VsdHMgLT4gbG9jYWwgc3RhdGUpIC0tLS0tLS0tLS0tLS0tLS0tLS0tLQpmdW5jdGlvbiBhcHBseVN0YXRlQ2hhbmdlcyhzYykgewogIC8vIE1vbnN0ZXIgZGFtYWdlIC8gZGVhdGgKICBpZiAoc2MubW9uc3Rlcl9kYW1hZ2UpIHsKICAgIGNvbnN0IG1kID0gc2MubW9uc3Rlcl9kYW1hZ2U7CiAgICBpZiAoY29tYmF0U3RhdGUuZW5jb3VudGVyICYmIGNvbWJhdFN0YXRlLmVuY291bnRlci5tb25zdGVycykgewogICAgICBjb25zdCBtID0gY29tYmF0U3RhdGUuZW5jb3VudGVyLm1vbnN0ZXJzLmZpbmQoeCA9PgogICAgICAgIHguaWQgPT09IG1kLm1vbnN0ZXJfaWQgfHwgeC5uYW1lID09PSBtZC5tb25zdGVyX2lkKTsKICAgICAgaWYgKG0pIHsKICAgICAgICBtLmhwID0gbWQubmV3X2hwOwogICAgICAgIGlmIChtZC5raWxsZWQpIG0uZGVhZCA9IHRydWU7CiAgICAgIH0KICAgICAgY29uc3QgYWxpdmUgPSBjb21iYXRTdGF0ZS5lbmNvdW50ZXIubW9uc3RlcnMuZmlsdGVyKG0gPT4gIW0uZGVhZCAmJiBtLmhwID4gMCk7CiAgICAgIGlmIChhbGl2ZS5sZW5ndGggPT09IDApIHsKICAgICAgICBpbkNvbWJhdCA9IGZhbHNlOwogICAgICAgIGFkZEVudHJ5UmF3KCdbQWxsIGVuZW1pZXMgZGVmZWF0ZWQgLS0gY29tYmF0IGVuZHNdJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgICAgfQogICAgfQogIH0KICAvLyBNb25zdGVyIGZsZWVzCiAgaWYgKHNjLm1vbnN0ZXJfZmxlZXMpIHsKICAgIGlmIChjb21iYXRTdGF0ZS5lbmNvdW50ZXIgJiYgY29tYmF0U3RhdGUuZW5jb3VudGVyLm1vbnN0ZXJzKSB7CiAgICAgIGNvbnN0IG0gPSBjb21iYXRTdGF0ZS5lbmNvdW50ZXIubW9uc3RlcnMuZmluZCh4ID0+CiAgICAgICAgeC5pZCA9PT0gc2MubW9uc3Rlcl9mbGVlcyB8fCB4Lm5hbWUgPT09IHNjLm1vbnN0ZXJfZmxlZXMpOwogICAgICBpZiAobSkgeyBtLmZsZWQgPSB0cnVlOyBtLmhwID0gMDsgfQogICAgfQogICAgY29uc3QgYWxpdmUgPSAoY29tYmF0U3RhdGUuZW5jb3VudGVyICYmIGNvbWJhdFN0YXRlLmVuY291bnRlci5tb25zdGVyc3x8W10pCiAgICAgIC5maWx0ZXIobSA9PiAhbS5kZWFkICYmICFtLmZsZWQgJiYgbS5ocCA+IDApOwogICAgaWYgKGFsaXZlLmxlbmd0aCA9PT0gMCkgaW5Db21iYXQgPSBmYWxzZTsKICB9CiAgLy8gWFAgZ2FpbgogIGlmIChzYy54cF9nYWluKSB7CiAgICBwYy54cCA9IChwYy54cCB8fCAwKSArIHNjLnhwX2dhaW47CiAgICBhZGRFbnRyeVJhdygnW1hQICsnICsgc2MueHBfZ2FpbiArICcgKHRvdGFsOiAnICsgcGMueHAgKyAnKV0nLCAnc3lzdGVtJywgJ19fZ21fXycpOwogIH0KICAvLyBQbGF5ZXIgZGFtYWdlCiAgaWYgKHNjLnBsYXllcl9kYW1hZ2UgJiYgc2MucGxheWVyX2RhbWFnZSA+IDApIHsKICAgIHBjLmhwID0gTWF0aC5tYXgoMCwgKHBjLmhwfHwwKSAtIHNjLnBsYXllcl9kYW1hZ2UpOwogICAgaWYgKHBjLmhwIDw9IDApIHsKICAgICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjojYzA2MDYwO2ZvbnQtd2VpZ2h0OmJvbGQ7Ij4mIzk4ODg7ICcgKyAKICAgICAgICAocGMubmFtZXx8J1lvdScpICsgJyBoYXMgYmVlbiByZWR1Y2VkIHRvIDAgSFAhIFRoZSBhZHZlbnR1cmUgbWF5IGJlIG92ZXIuLi48L3NwYW4+JywKICAgICAgICAnc3lzdGVtJywgJ19fZ21fXycpOwogICAgfQogIH0KICAvLyBIZWFsaW5nCiAgaWYgKHNjLmhlYWxfcGxheWVyKSB7CiAgICBwYy5ocCA9IE1hdGgubWluKHBjLm1heGhwIHx8IHBjLmhwLCAocGMuaHB8fDApICsgc2MuaGVhbF9wbGF5ZXIpOwogIH0KICAvLyBTcGVsbCBzbG90IGNvbnN1bXB0aW9uCiAgaWYgKHNjLmNvbnN1bWVfc3BlbGxfc2xvdCAhPT0gdW5kZWZpbmVkKSB7CiAgICBjb25zdCBpZHggPSBzYy5jb25zdW1lX3NwZWxsX3Nsb3QgLSAxOwogICAgaWYgKHNwZWxsU2xvdHNSZW1haW5pbmdbaWR4XSA+IDApIHNwZWxsU2xvdHNSZW1haW5pbmdbaWR4XS0tOwogICAgLy8gUmVtb3ZlIGZyb20gbWVtb3JpemVkIChvbmUgaW5zdGFuY2UpCiAgICBjb25zdCBtSWR4ID0gbWVtb3JpemVkU3BlbGxzLmZpbmRJbmRleChzID0+CiAgICAgICh0eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lKSAmJiBBTExfU1BFTExfTEVWRUxTW3R5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWVdID09PSBzYy5jb25zdW1lX3NwZWxsX3Nsb3QpOwogICAgaWYgKG1JZHggPj0gMCkgbWVtb3JpemVkU3BlbGxzLnNwbGljZShtSWR4LCAxKTsKICB9CiAgLy8gQW1tbyBjb25zdW1wdGlvbgogIGlmIChzYy5jb25zdW1lX2FtbW8pIHsKICAgIGNvbnN0IGludiA9IHBjLmludiB8fCBbXTsKICAgIGNvbnN0IGFpID0gaW52LmZpbmRJbmRleChpID0+IC9ib2x0fGFycm93fHN0b25lfHF1YXJyZWwvaS50ZXN0KHR5cGVvZiBpPT09J3N0cmluZyc/aTooaS5uYW1lfHwnJykpKTsKICAgIGlmIChhaSA+PSAwKSB7CiAgICAgIGNvbnN0IGl0ZW0gPSB0eXBlb2YgaW52W2FpXT09PSdzdHJpbmcnID8gaW52W2FpXSA6IGludlthaV0ubmFtZTsKICAgICAgY29uc3QgbnVtTSA9IGl0ZW0ubWF0Y2goL1suXShbLl1kKylbLl0vKTsKICAgICAgaWYgKG51bU0pIHsKICAgICAgICBjb25zdCBuID0gcGFyc2VJbnQobnVtTVsxXSkgLSAxOwogICAgICAgIGlmIChuIDw9IDApIGludi5zcGxpY2UoYWksIDEpOwogICAgICAgIGVsc2UgaW52W2FpXSA9IGl0ZW0ucmVwbGFjZSgvWy5dWy5dZCtbLl0vLCAnKCcgKyBuICsgJyknKTsKICAgICAgfQogICAgfQogIH0KICAvLyBSYXRpb24gY29uc3VtcHRpb24KICBpZiAoc2MuY29uc3VtZV9yYXRpb24pIHsKICAgIHJhdGlvbnNMZWZ0ID0gTWF0aC5tYXgoMCwgKHJhdGlvbnNMZWZ0fHwwKSAtIDEpOwogICAgZGF5c1dpdGhvdXRGb29kID0gMDsgc3RhcnZhdGlvblBlbmFsdHkgPSAwOwogIH0KICAvLyBUb3JjaCBsaWdodGluZwogIGlmIChzYy5saWdodF90b3JjaCkgewogICAgdG9yY2hMaXQgPSB0cnVlOyB0b3JjaEV2ZXJVc2VkID0gdHJ1ZTsgdG9yY2hUdXJuc0xlZnQgPSA2OwogICAgY29uc3QgaW52ID0gcGMuaW52IHx8IFtdOwogICAgY29uc3QgdGkgPSBpbnYuZmluZEluZGV4KGkgPT4gL3RvcmNoL2kudGVzdCh0eXBlb2YgaT09PSdzdHJpbmcnP2k6KGkubmFtZXx8JycpKSk7CiAgICBpZiAodGkgPj0gMCkgewogICAgICBjb25zdCBpdGVtID0gdHlwZW9mIGludlt0aV09PT0nc3RyaW5nJyA/IGludlt0aV0gOiAnJzsKICAgICAgY29uc3Qgbm0gPSBpdGVtLm1hdGNoKC9bLl0oWy5dZCspWy5dLyk7CiAgICAgIGlmIChubSAmJiBwYXJzZUludChubVsxXSk+MSkgaW52W3RpXSA9IGl0ZW0ucmVwbGFjZSgvWy5dWy5dZCtbLl0vLCcoJyArIChwYXJzZUludChubVsxXSktMSkgKyAnKScpOwogICAgICBlbHNlIGludi5zcGxpY2UodGksMSk7CiAgICB9CiAgfQogIC8vIEl0ZW0gY29uc3VtcHRpb24KICBpZiAoc2MuY29uc3VtZV9pdGVtKSB7CiAgICBjb25zdCBpbnYgPSBwYy5pbnYgfHwgW107CiAgICBjb25zdCBpZHggPSBpbnYuZmluZEluZGV4KGkgPT4gKHR5cGVvZiBpPT09J3N0cmluZyc/aTooaS5uYW1lfHwnJykpID09PSBzYy5jb25zdW1lX2l0ZW0pOwogICAgaWYgKGlkeCA+PSAwKSBpbnYuc3BsaWNlKGlkeCwgMSk7CiAgfQogIC8vIEZ1bGwgcmVzdAogIGlmIChzYy5mdWxsX3Jlc3QpIHsKICAgIHR1cm5zV2l0aG91dFJlc3QgPSAwOyBmYXRpZ3VlUGVuYWx0eSA9IDA7CiAgICBzcGVsbFNsb3RzUmVtYWluaW5nID0gWy4uLnNwZWxsU2xvdHNUb3RhbF07CiAgICBhZGRFbnRyeVJhdygnW0Z1bGwgcmVzdCBjb21wbGV0ZS4gU3BlbGwgc2xvdHMgcmVzdG9yZWQuIEF3YWl0aW5nIG1lbW9yaXphdGlvbi5dJywgJ3N5c3RlbScsICdfX2dtX18nKTsKICAgIC8vIFByb21wdCBtZW1vcml6YXRpb24gaWYgc3BlbGxjYXN0ZXIKICAgIGlmIChzcGVsbFNsb3RzVG90YWwubGVuZ3RoID4gMCkgb3Blbk1lbW9yaXplKCk7CiAgfQogIC8vIER1bmdlb24gcmVzdAogIGlmIChzYy5kdW5nZW9uX3Jlc3QpIHsgdHVybnNXaXRob3V0UmVzdCA9IDA7IGZhdGlndWVQZW5hbHR5ID0gMDsgfQogIC8vIEFjdGl2ZSBlZmZlY3RzCiAgaWYgKHNjLmFkZF9lZmZlY3QpIHsKICAgIGFjdGl2ZUVmZmVjdHNWNC5wdXNoKHsuLi5zYy5hZGRfZWZmZWN0LCBzdGFydGVkQXQ6IHR1cm5Db3VudH0pOwogIH0KICAvLyBBYmlsaXR5IHVzZXMKICBpZiAoc2MuYWJpbGl0eV91c2VkKSB7CiAgICBjb25zdCBhbmFtZSA9IHNjLmFiaWxpdHlfdXNlZC5uYW1lOwogICAgYWJpbGl0eVVzZXNUb2RheVthbmFtZV0gPSAoYWJpbGl0eVVzZXNUb2RheVthbmFtZV18fDApICsgKHNjLmFiaWxpdHlfdXNlZC5hbW91bnR8fDEpOwogIH0KfQoKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09Ci8vIExFVkVMIFVQIFNZU1RFTQovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KZnVuY3Rpb24gc2hvd0xldmVsVXBNb2RhbChsdSkgewogIGNvbnN0IGNoYW5nZXMgPSBsdS5jaGFuZ2VzIHx8IFtdOwogIGNvbnN0IG5ld0x2bCA9IGx1Lm5ld19sZXZlbDsKICBjb25zdCBodG1sID0gYAogICAgPGRpdiBjbGFzcz0ibGV2ZWwtdXAtbW9kYWwiIGlkPSJsdi1tb2RhbCI+CiAgICAgIDxkaXYgY2xhc3M9ImxldmVsLXVwLWlubmVyIj4KICAgICAgICA8ZGl2IGNsYXNzPSJsdi10aXRsZSI+JiM5NzMzOyBMRVZFTCBVUCEgJiM5NzMzOzwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9InRleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxN3B4O21hcmdpbi1ib3R0b206MTRweDsiPgogICAgICAgICAgJHtwYy5uYW1lfSByZWFjaGVzIDxiPkxldmVsICR7bmV3THZsfTwvYj48L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPSJtYXJnaW4tYm90dG9tOjE0cHg7Ij4KICAgICAgICAgICR7Y2hhbmdlcy5tYXAoYz0+JzxkaXYgY2xhc3M9Imx2LWNoYW5nZSI+JytjKyc8L2Rpdj4nKS5qb2luKCcnKX0KICAgICAgICA8L2Rpdj4KICAgICAgICAkeyhsdS51cGRhdGVkX3BjICYmIFsnTWFnaWMtVXNlcicsJ0lsbHVzaW9uaXN0JywnQ2xlcmljJywnRHJ1aWQnLCdCYXJkJ10uaW5jbHVkZXMocGMuY2xzKSkKICAgICAgICAgID8gJzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLWdvbGQtZGltKTtmb250LXNpemU6MTNweDttYXJnaW4tYm90dG9tOjEycHg7Ij4nKwogICAgICAgICAgICAnTmV3IHNwZWxsIHNsb3RzIGF2YWlsYWJsZS4gWW91IG1heSBtZW1vcml6ZSBzcGVsbHMgYWZ0ZXIgYSBmdWxsIG5pZ2h0JiMzOTtzIHJlc3QuPC9kaXY+JyA6ICcnfQogICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biIgc3R5bGU9IndpZHRoOjEwMCUiIG9uY2xpY2s9ImNsb3NlTGV2ZWxVcCgke0pTT04uc3RyaW5naWZ5KEpTT04uc3RyaW5naWZ5KGx1LnVwZGF0ZWRfcGMpKX0pIj4KICAgICAgICAgIENvbnRpbnVlICYjOTY1ODs8L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj5gOwogIGRvY3VtZW50LmJvZHkuaW5zZXJ0QWRqYWNlbnRIVE1MKCdiZWZvcmVlbmQnLCBodG1sKTsKICBjb25zdCBjaGFuZ2VzX3N0ciA9IGNoYW5nZXMuam9pbignIHwgJyk7CiAgYWRkRW50cnlSYXcoJ1tMRVZFTCBVUDogJyArIHBjLm5hbWUgKyAnIHJlYWNoZXMgbGV2ZWwgJyArIG5ld0x2bCArICchICcgKyBjaGFuZ2VzX3N0ciArICddJywgJ3N5c3RlbScsICdfX2dtX18nKTsKfQoKZnVuY3Rpb24gY2xvc2VMZXZlbFVwKHVwZGF0ZWRQY0pzb24pIHsKICBjb25zdCBtb2RhbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsdi1tb2RhbCcpOwogIGlmIChtb2RhbCkgbW9kYWwucmVtb3ZlKCk7CiAgaWYgKHVwZGF0ZWRQY0pzb24pIHsKICAgIHRyeSB7CiAgICAgIGNvbnN0IHVwZCA9IHR5cGVvZiB1cGRhdGVkUGNKc29uID09PSAnc3RyaW5nJyA/IEpTT04ucGFyc2UodXBkYXRlZFBjSnNvbikgOiB1cGRhdGVkUGNKc29uOwogICAgICBPYmplY3QuYXNzaWduKHBjLCB1cGQpOwogICAgICAvLyBVcGRhdGUgc3BlbGwgc2xvdHMgaWYgY2hhbmdlZAogICAgICBpZiAodXBkLnNwZWxsX3Nsb3RzX3RvdGFsKSB7CiAgICAgICAgc3BlbGxTbG90c1RvdGFsID0gdXBkLnNwZWxsX3Nsb3RzX3RvdGFsOwogICAgICAgIC8vIERvbid0IHJlc2V0IHJlbWFpbmluZyAtLSB0aGV5IG1heSBoYXZlIHNsb3RzIGxlZnQKICAgICAgfQogICAgICB1cGRhdGVIVUQoKTsKICAgICAgdXBkYXRlU3BlbGxib29rUGFuZWwoKTsKICAgIH0gY2F0Y2goZSkge30KICB9Cn0KCi8vID09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PQovLyBTUEVMTCBTWVNURU0gVUkKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CgovLyBMb29rdXA6IHNwZWxsIG5hbWUgLT4gbGV2ZWwgKHBvcHVsYXRlZCBmcm9tIHNlcnZlciBkYXRhKQpjb25zdCBBTExfU1BFTExfTEVWRUxTID0ge307CgpmdW5jdGlvbiB1cGRhdGVTcGVsbGJvb2tQYW5lbCgpIHsKICBjb25zdCBwYW5lbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzcGVsbGJvb2stcGFuZWwnKTsKICBpZiAoIXBhbmVsKSByZXR1cm47CgogIGNvbnN0IHNwZWxsY2FzdGluZ0NsYXNzZXMgPSBbJ01hZ2ljLVVzZXInLCdJbGx1c2lvbmlzdCcsJ0NsZXJpYycsJ0RydWlkJywnUmFuZ2VyJywnUGFsYWRpbicsJ0JhcmQnXTsKICBpZiAoIXNwZWxsY2FzdGluZ0NsYXNzZXMuaW5jbHVkZXMocGMuY2xzKSkgewogICAgcGFuZWwuc3R5bGUuZGlzcGxheSA9ICdub25lJzsKICAgIHJldHVybjsKICB9CiAgcGFuZWwuc3R5bGUuZGlzcGxheSA9ICcnOwoKICAvLyBTbG90cyBkaXNwbGF5CiAgY29uc3Qgc2xvdHNFbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYi1zbG90cycpOwogIGlmIChzbG90c0VsKSB7CiAgICBpZiAoIXNwZWxsU2xvdHNUb3RhbC5sZW5ndGgpIHsKICAgICAgc2xvdHNFbC5pbm5lckhUTUwgPSAnPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLXRleHQtZGltKSI+Tm8gc3BlbGwgc2xvdHMgYXQgdGhpcyBsZXZlbC48L3NwYW4+JzsKICAgIH0gZWxzZSB7CiAgICAgIGxldCBodG1sID0gJzxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWdvbGQtZGltKTttYXJnaW4tYm90dG9tOjRweDsiPlNQRUxMIFNMT1RTPC9kaXY+JzsKICAgICAgc3BlbGxTbG90c1RvdGFsLmZvckVhY2goKHRvdGFsLCBpZHgpID0+IHsKICAgICAgICBjb25zdCB1c2VkID0gdG90YWwgLSAoc3BlbGxTbG90c1JlbWFpbmluZ1tpZHhdfHwwKTsKICAgICAgICBjb25zdCBwaXBzID0gQXJyYXkuZnJvbSh7bGVuZ3RoOnRvdGFsfSwgKF8saSkgPT4KICAgICAgICAgIGA8c3BhbiBjbGFzcz0ic3BlbGwtc2xvdC1waXAke2k8dXNlZD8nIHVzZWQnOicnfSI+PC9zcGFuPmApLmpvaW4oJycpOwogICAgICAgIGh0bWwgKz0gYDxkaXYgY2xhc3M9InNwZWxsLXNsb3Qtcm93Ij4KICAgICAgICAgIDxzcGFuIHN0eWxlPSJmb250LXNpemU6MTFweDtjb2xvcjp2YXIoLS10ZXh0LWRpbSk7d2lkdGg6MTZweDsiPiR7aWR4KzF9PC9zcGFuPgogICAgICAgICAgJHtwaXBzfTwvZGl2PmA7CiAgICAgIH0pOwogICAgICBzbG90c0VsLmlubmVySFRNTCA9IGh0bWw7CiAgICB9CiAgfQoKICAvLyBNZW1vcml6ZWQgc3BlbGxzCiAgY29uc3QgbWVtRWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2ItbWVtb3JpemVkJyk7CiAgaWYgKG1lbUVsKSB7CiAgICBpZiAoIW1lbW9yaXplZFNwZWxscy5sZW5ndGgpIHsKICAgICAgbWVtRWwuaW5uZXJIVE1MID0gJzxkaXYgc3R5bGU9ImNvbG9yOnZhcigtLXRleHQtZGltKTtmb250LXNpemU6MTJweDsiPk5vIHNwZWxscyBtZW1vcml6ZWQuPC9kaXY+JzsKICAgIH0gZWxzZSB7CiAgICAgIGNvbnN0IGJ5TGV2ZWwgPSB7fTsKICAgICAgbWVtb3JpemVkU3BlbGxzLmZvckVhY2gocyA9PiB7CiAgICAgICAgY29uc3QgbmFtZSA9IHR5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWU7CiAgICAgICAgY29uc3QgbHZsICA9ICh0eXBlb2Ygcz09PSdvYmplY3QnJiZzLmxldmVsKSB8fCBBTExfU1BFTExfTEVWRUxTW25hbWVdIHx8ICc/JzsKICAgICAgICBpZiAoIWJ5TGV2ZWxbbHZsXSkgYnlMZXZlbFtsdmxdID0gW107CiAgICAgICAgYnlMZXZlbFtsdmxdLnB1c2gobmFtZSk7CiAgICAgIH0pOwogICAgICBsZXQgaHRtbCA9ICcnOwogICAgICBPYmplY3Qua2V5cyhieUxldmVsKS5zb3J0KCkuZm9yRWFjaChsdmwgPT4gewogICAgICAgIGh0bWwgKz0gYDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMXB4O2NvbG9yOnZhcigtLWdvbGQtZGltKTttYXJnaW4tdG9wOjRweDsiPkxldmVsICR7bHZsfTo8L2Rpdj5gOwogICAgICAgIGJ5TGV2ZWxbbHZsXS5mb3JFYWNoKG5hbWUgPT4gewogICAgICAgICAgaHRtbCArPSBgPGRpdiBzdHlsZT0iZm9udC1zaXplOjEycHg7cGFkZGluZzoxcHggNHB4OyI+JiM5NjcwOyAke25hbWV9PC9kaXY+YDsKICAgICAgICB9KTsKICAgICAgfSk7CiAgICAgIG1lbUVsLmlubmVySFRNTCA9IGh0bWw7CiAgICB9CiAgfQoKICAvLyBTaG93IG1lbW9yaXplIGJ1dHRvbiB3aGVuIHNsb3RzID4gMCBhbmQgYWZ0ZXIgcmVzdAogIGNvbnN0IGJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW1vcml6ZS1idG4nKTsKICBpZiAoYnRuKSB7CiAgICBjb25zdCBoYXNTbG90cyA9IHNwZWxsU2xvdHNUb3RhbC5zb21lKHMgPT4gcyA+IDApOwogICAgY29uc3QgaGFzU3BlbGxzID0gT2JqZWN0LmtleXMoc3BlbGxCb29rKS5sZW5ndGggPiAwOwogICAgYnRuLnN0eWxlLmRpc3BsYXkgPSAoaGFzU2xvdHMgJiYgaGFzU3BlbGxzKSA/ICcnIDogJ25vbmUnOwogIH0KfQoKLy8gLS0gTWVtb3JpemUgc3BlbGwgbW9kYWwgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tCmZ1bmN0aW9uIG9wZW5NZW1vcml6ZSgpIHsKICBjb25zdCBleGlzdGluZyA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW1vcml6ZS1tb2RhbCcpOwogIGlmIChleGlzdGluZykgZXhpc3RpbmcucmVtb3ZlKCk7CgogIGNvbnN0IHNwZWxsY2FzdGluZ0NsYXNzZXMgPSB7CiAgICAnTWFnaWMtVXNlcic6IE1VX1NQRUxMU19GT1JfQ0xBU1MsCiAgICAnSWxsdXNpb25pc3QnOiBNVV9TUEVMTFNfRk9SX0NMQVNTLAogICAgJ0NsZXJpYyc6IENMRVJJQ19TUEVMTFNfRk9SX0NMQVNTLAogICAgJ0RydWlkJzogRFJVSURfU1BFTExTX0ZPUl9DTEFTUywKICAgICdSYW5nZXInOiBSQU5HRVJfU1BFTExTX0ZPUl9DTEFTUywKICAgICdQYWxhZGluJzogQ0xFUklDX1NQRUxMU19GT1JfQ0xBU1MsCiAgICAnQmFyZCc6IEJBUkRfU1BFTExTX0ZPUl9DTEFTUywKICB9OwoKICBjb25zdCBjbGFzc1NwZWxscyA9IHNwZWxsY2FzdGluZ0NsYXNzZXNbcGMuY2xzXSB8fCB7fTsKICBjb25zdCBhbGxTcGVsbHNGb3JDbGFzcyA9IE9iamVjdC5lbnRyaWVzKGNsYXNzU3BlbGxzKTsKCiAgbGV0IGJvZHlIdG1sID0gJyc7CiAgLy8gRm9yIE1VL0lsbHVzaW9uaXN0OiBjYW4gb25seSBtZW1vcml6ZSBmcm9tIHNwZWxsYm9vawogIC8vIEZvciBDbGVyaWMvRHJ1aWQvZXRjOiBjYW4gbWVtb3JpemUgYW55IHNwZWxsIG9mIGFwcHJvcHJpYXRlIGxldmVsCiAgY29uc3QgdXNlc1NwZWxsYm9vayA9IFsnTWFnaWMtVXNlcicsJ0lsbHVzaW9uaXN0J10uaW5jbHVkZXMocGMuY2xzKTsKCiAgc3BlbGxTbG90c1RvdGFsLmZvckVhY2goKHRvdGFsLCBzbG90SWR4KSA9PiB7CiAgICBpZiAodG90YWwgPT09IDApIHJldHVybjsKICAgIGNvbnN0IHNwZWxsTGV2ZWwgPSBzbG90SWR4ICsgMTsKICAgIGNvbnN0IGF2YWlsYWJsZVNwZWxscyA9IGFsbFNwZWxsc0ZvckNsYXNzCiAgICAgIC5maWx0ZXIoKFtuYW1lLCBkYXRhXSkgPT4gewogICAgICAgIGlmIChkYXRhLmxldmVsICE9PSBzcGVsbExldmVsKSByZXR1cm4gZmFsc2U7CiAgICAgICAgaWYgKHVzZXNTcGVsbGJvb2sgJiYgIXNwZWxsQm9va1tuYW1lXSkgcmV0dXJuIGZhbHNlOwogICAgICAgIHJldHVybiB0cnVlOwogICAgICB9KTsKCiAgICBpZiAoIWF2YWlsYWJsZVNwZWxscy5sZW5ndGgpIHJldHVybjsKCiAgICBib2R5SHRtbCArPSBgPGRpdiBzdHlsZT0ibWFyZ2luOjEwcHggMCA0cHg7Zm9udC1zaXplOjEzcHg7Y29sb3I6dmFyKC0tZ29sZCk7Ij4KICAgICAgTGV2ZWwgJHtzcGVsbExldmVsfSBTcGVsbHMgKCR7dG90YWx9IHNsb3RzKTwvZGl2PmA7CiAgICBhdmFpbGFibGVTcGVsbHMuZm9yRWFjaCgoW25hbWUsIGRhdGFdKSA9PiB7CiAgICAgIGNvbnN0IGFscmVhZHlDb3VudGVkID0gbWVtb3JpemVkU3BlbGxzLmZpbHRlcihzID0+CiAgICAgICAgKHR5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWUpID09PSBuYW1lKS5sZW5ndGg7CiAgICAgIGJvZHlIdG1sICs9IGAKICAgICAgICA8ZGl2IGNsYXNzPSJzcGVsbC1jYXJkIiBpZD0ic2MtJHtuYW1lLnJlcGxhY2UoL1suXXMrL2csJy0nKX0iCiAgICAgICAgICBvbmNsaWNrPSJ0b2dnbGVNZW1vcml6ZVNwZWxsKCcke25hbWV9JywgJHtzcGVsbExldmVsfSkiCiAgICAgICAgICB0aXRsZT0iJHtkYXRhLmRlc2N8fCcnfSI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJzbmFtZSI+JHtuYW1lfQogICAgICAgICAgICAke2RhdGEuc2F2ZT8nPHNwYW4gc3R5bGU9ImZvbnQtc2l6ZToxMHB4O2NvbG9yOnZhcigtLWdvbGQtZGltKSI+IChTYXZlIHZzICcrZGF0YS5zYXZlKycpPC9zcGFuPic6Jyd9CiAgICAgICAgICAgICR7ZGF0YS5kbWc/JzxzcGFuIHN0eWxlPSJmb250LXNpemU6MTBweDtjb2xvcjojYzA5MDQwIj4gWycrZGF0YS5kbWcrJ108L3NwYW4+JzonJ30KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0ic2Rlc2MiPiR7ZGF0YS5yYW5nZX0gfCAke2RhdGEuZHVyYXRpb259IHwgJHtkYXRhLmRlc2N9PC9kaXY+CiAgICAgICAgPC9kaXY+YDsKICAgIH0pOwogIH0pOwoKICBpZiAoIWJvZHlIdG1sKSB7CiAgICBib2R5SHRtbCA9ICc8ZGl2IHN0eWxlPSJjb2xvcjp2YXIoLS10ZXh0LWRpbSk7dGV4dC1hbGlnbjpjZW50ZXI7cGFkZGluZzoyMHB4OyI+Tm8gc3BlbGxzIGF2YWlsYWJsZSB0byBtZW1vcml6ZSBhdCB0aGlzIGxldmVsLjwvZGl2Pic7CiAgfQoKICBjb25zdCBtb2RhbCA9IGAKICAgIDxkaXYgY2xhc3M9Im1lbW9yaXplLW1vZGFsIiBpZD0ibWVtb3JpemUtbW9kYWwiPgogICAgICA8ZGl2IGNsYXNzPSJtZW1vcml6ZS1tb2RhbC1pbm5lciI+CiAgICAgICAgPGRpdiBzdHlsZT0iZm9udC1mYW1pbHk6Wy5dJ0lNIEZlbGwgRW5nbGlzaFsuXScsc2VyaWY7Zm9udC1zaXplOjIycHg7Y29sb3I6dmFyKC0tZ29sZCk7bWFyZ2luLWJvdHRvbTo0cHg7Ij4KICAgICAgICAgIE1lbW9yaXplIFNwZWxsczwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9ImZvbnQtc2l6ZToxMnB4O2NvbG9yOnZhcigtLXRleHQtZGltKTttYXJnaW4tYm90dG9tOjEycHg7Ij4KICAgICAgICAgIFNlbGVjdCBzcGVsbHMgdG8gZmlsbCB5b3VyIGF2YWlsYWJsZSBzbG90cy4gJHt1c2VzU3BlbGxib29rPydPbmx5IHNwZWxscyBpbiB5b3VyIHNwZWxsYm9vayBtYXkgYmUgbWVtb3JpemVkLic6Jyd9CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBpZD0ibWVtb3JpemUtc2VsZWN0aW9uIj4ke2JvZHlIdG1sfTwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9Im1hcmdpbi10b3A6MTRweDtkaXNwbGF5OmZsZXg7Z2FwOjhweDsiPgogICAgICAgICAgPGJ1dHRvbiBjbGFzcz0iYnRuIiBvbmNsaWNrPSJjb25maXJtTWVtb3JpemUoKSIgc3R5bGU9ImZsZXg6MSI+TWVtb3JpemUgU2VsZWN0ZWQ8L2J1dHRvbj4KICAgICAgICAgIDxidXR0b24gY2xhc3M9ImJ0biIgb25jbGljaz0iY2xvc2VNZW1vcml6ZSgpIiBzdHlsZT0iZmxleDoxO2JhY2tncm91bmQ6dHJhbnNwYXJlbnQ7Ym9yZGVyLWNvbG9yOnZhcigtLWJvcmRlcik7Ij5DYW5jZWw8L2J1dHRvbj4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj5gOwogIGRvY3VtZW50LmJvZHkuaW5zZXJ0QWRqYWNlbnRIVE1MKCdiZWZvcmVlbmQnLCBtb2RhbCk7CgogIC8vIFByZS1zZWxlY3QgY3VycmVudGx5IG1lbW9yaXplZAogIG1lbW9yaXplZFNwZWxscy5mb3JFYWNoKHMgPT4gewogICAgY29uc3QgbmFtZSA9IHR5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWU7CiAgICBjb25zdCBlbCA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdzYy0nICsgbmFtZS5yZXBsYWNlKC9bLl1zKy9nLCctJykpOwogICAgaWYgKGVsKSBlbC5jbGFzc0xpc3QuYWRkKCdzZWxlY3RlZCcpOwogIH0pOwp9CgpsZXQgX3BlbmRpbmdNZW1vcml6ZSA9IFtdOwpmdW5jdGlvbiB0b2dnbGVNZW1vcml6ZVNwZWxsKG5hbWUsIGxldmVsKSB7CiAgY29uc3QgZWwgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2MtJyArIG5hbWUucmVwbGFjZSgvWy5dcysvZywnLScpKTsKICBpZiAoIWVsKSByZXR1cm47CgogIGNvbnN0IGlkeCA9IF9wZW5kaW5nTWVtb3JpemUuZmluZEluZGV4KHMgPT4gKHR5cGVvZiBzPT09J3N0cmluZyc/czpzLm5hbWUpPT09bmFtZSk7CiAgaWYgKGlkeCA+PSAwKSB7CiAgICBfcGVuZGluZ01lbW9yaXplLnNwbGljZShpZHgsIDEpOwogICAgZWwuY2xhc3NMaXN0LnJlbW92ZSgnc2VsZWN0ZWQnKTsKICB9IGVsc2UgewogICAgLy8gQ2hlY2sgc2xvdCBhdmFpbGFiaWxpdHkgZm9yIHRoaXMgbGV2ZWwKICAgIGNvbnN0IHNsb3RJZHggPSBsZXZlbCAtIDE7CiAgICBjb25zdCB1c2VkQXRMZXZlbCA9IF9wZW5kaW5nTWVtb3JpemUuZmlsdGVyKHMgPT4KICAgICAgKCh0eXBlb2Ygcz09PSdvYmplY3QnJiZzLmxldmVsKXx8QUxMX1NQRUxMX0xFVkVMU1t0eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lXXx8MSkgPT09IGxldmVsKS5sZW5ndGg7CiAgICBpZiAodXNlZEF0TGV2ZWwgPj0gKHNwZWxsU2xvdHNUb3RhbFtzbG90SWR4XXx8MCkpIHsKICAgICAgYWRkRW50cnlSYXcoJ1tObyBtb3JlIGxldmVsICcgKyBsZXZlbCArICcgc2xvdHMgYXZhaWxhYmxlXScsICdzeXN0ZW0nLCAnX19nbV9fJyk7CiAgICAgIHJldHVybjsKICAgIH0KICAgIF9wZW5kaW5nTWVtb3JpemUucHVzaCh7bmFtZSwgbGV2ZWx9KTsKICAgIGVsLmNsYXNzTGlzdC5hZGQoJ3NlbGVjdGVkJyk7CiAgfQp9CgpmdW5jdGlvbiBjb25maXJtTWVtb3JpemUoKSB7CiAgbWVtb3JpemVkU3BlbGxzID0gWy4uLl9wZW5kaW5nTWVtb3JpemVdOwogIF9wZW5kaW5nTWVtb3JpemUgPSBbXTsKICAvLyBSZXNldCBzcGVsbCBzbG90cyB0byB0b3RhbCAoZnJlc2ggbWVtb3JpemF0aW9uKQogIHNwZWxsU2xvdHNSZW1haW5pbmcgPSBbLi4uc3BlbGxTbG90c1RvdGFsXTsKICBjbG9zZU1lbW9yaXplKCk7CiAgdXBkYXRlU3BlbGxib29rUGFuZWwoKTsKICBjb25zdCBuYW1lcyA9IG1lbW9yaXplZFNwZWxscy5tYXAocz0+dHlwZW9mIHM9PT0nc3RyaW5nJz9zOnMubmFtZSkuam9pbignLCAnKTsKICBhZGRFbnRyeVJhdygnW1NwZWxscyBtZW1vcml6ZWQ6ICcgKyAobmFtZXN8fCdub25lJykgKyAnXScsICdzeXN0ZW0nLCAnX19nbV9fJyk7Cn0KCmZ1bmN0aW9uIGNsb3NlTWVtb3JpemUoKSB7CiAgY29uc3QgbSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW1vcml6ZS1tb2RhbCcpOwogIGlmIChtKSBtLnJlbW92ZSgpOwogIF9wZW5kaW5nTWVtb3JpemUgPSBbXTsKfQoKLy8gLS0gU3BlbGxib29rIGxlYXJuaW5nIChjYWxsIHdoZW4gcGxheWVyIGZpbmRzIHNjcm9sbCBvciBsZXZlbHMgdXApIC0tLS0tLS0tLS0KZnVuY3Rpb24gbGVhcm5TcGVsbChzcGVsbE5hbWUsIHNwZWxsRGF0YSkgewogIHNwZWxsQm9va1tzcGVsbE5hbWVdID0gewogICAgbmFtZTogc3BlbGxOYW1lLAogICAgbGV2ZWw6IHNwZWxsRGF0YS5sZXZlbCwKICAgIHR5cGU6IHNwZWxsRGF0YS50eXBlIHx8ICdtdScsCiAgICBrbm93bjogdHJ1ZSwKICB9OwogIEFMTF9TUEVMTF9MRVZFTFNbc3BlbGxOYW1lXSA9IHNwZWxsRGF0YS5sZXZlbDsKICB1cGRhdGVTcGVsbGJvb2tQYW5lbCgpOwogIGFkZEVudHJ5UmF3KCdbU3BlbGwgbGVhcm5lZDogJyArIHNwZWxsTmFtZSArICcgKExldmVsICcgKyBzcGVsbERhdGEubGV2ZWwgKyAnKV0nLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgovLyAtLSBBYmlsaXR5IHBhbmVsIHVwZGF0ZSAtLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KZnVuY3Rpb24gdXBkYXRlQWJpbGl0eVBhbmVsKCkgewogIGNvbnN0IHBhbmVsID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2FiaWxpdHktcGFuZWwnKTsKICBpZiAoIXBhbmVsKSByZXR1cm47CgogIGNvbnN0IGFiaWxpdGllcyA9IGdldENsYXNzQWJpbGl0aWVzSlMocGMuY2xzLCBwYy5sZXZlbCB8fCAxKTsKICBpZiAoIWFiaWxpdGllcy5sZW5ndGgpIHsgcGFuZWwuc3R5bGUuZGlzcGxheSA9ICdub25lJzsgcmV0dXJuOyB9CiAgcGFuZWwuc3R5bGUuZGlzcGxheSA9ICcnOwoKICBsZXQgaHRtbCA9ICcnOwogIGFiaWxpdGllcy5mb3JFYWNoKGFiID0+IHsKICAgIGNvbnN0IHVzZWRUb2RheSA9IGFiaWxpdHlVc2VzVG9kYXlbYWIubmFtZV0gfHwgMDsKICAgIGNvbnN0IG1heFVzZXMgPSBhYi51c2VzID09PSAndW5saW1pdGVkJyB8fCBhYi51c2VzID09PSAnYXRfd2lsbCcgPyBudWxsIDoKICAgICAgYWIudXNlcyA9PT0gJ2NvbmNlbnRyYXRpb24nID8gbnVsbCA6CiAgICAgIGFiLnVzZXMuZW5kc1dpdGgoJ19wZXJfZGF5JykgPyBwYXJzZUludChhYi51c2VzKSA6IG51bGw7CiAgICBjb25zdCBleGhhdXN0ZWQgPSBtYXhVc2VzICE9PSBudWxsICYmIHVzZWRUb2RheSA+PSBtYXhVc2VzOwogICAgY29uc3QgdXNlc1N0ciA9IG1heFVzZXMgIT09IG51bGwgPyBgICgke3VzZWRUb2RheX0vJHttYXhVc2VzfSlgIDogJyc7CiAgICBodG1sICs9IGA8c3BhbiBjbGFzcz0iYWJpbGl0eS1iYWRnZSR7ZXhoYXVzdGVkPycgZXhoYXVzdGVkJzonJ30iCiAgICAgIG9uY2xpY2s9InNob3dBYmlsaXR5SW5mbygnJHthYi5uYW1lfScsJyR7KGFiLmRlc2N8fCcnKS5yZXBsYWNlKC8nL2csIlsuXVxcJyIpfScpIgogICAgICB0aXRsZT0iJHthYi5kZXNjfHwnJ30iPiR7YWIubmFtZX0ke3VzZXNTdHJ9PC9zcGFuPmA7CiAgfSk7CiAgcGFuZWwuaW5uZXJIVE1MID0gaHRtbDsKfQoKZnVuY3Rpb24gc2hvd0FiaWxpdHlJbmZvKG5hbWUsIGRlc2MpIHsKICAvLyBTaW1wbGUgdG9vbHRpcC1zdHlsZSBkaXNwbGF5IGluIGxvZwogIGFkZEVudHJ5UmF3KGA8ZGl2IHN0eWxlPSJiYWNrZ3JvdW5kOnJnYmEoMTgwLDEzMCwyMCwwLjA4KTtib3JkZXI6MXB4IHNvbGlkIHZhcigtLWdvbGQtZGltKTsKICAgIHBhZGRpbmc6NnB4IDEwcHg7bWFyZ2luOjJweCAwO2ZvbnQtc2l6ZToxM3B4OyI+CiAgICA8YiBzdHlsZT0iY29sb3I6dmFyKC0tZ29sZCkiPiR7bmFtZX08L2I+PGJyPgogICAgPHNwYW4gc3R5bGU9ImNvbG9yOnZhcigtLXRleHQtZGltKSI+JHtkZXNjfTwvc3Bhbj48L2Rpdj5gLCAnc3lzdGVtJywgJ19fZ21fXycpOwp9CgovLyBDbGFzcyBhYmlsaXRpZXMgdGFibGUgKGNsaWVudC1zaWRlIG1pcnJvciBvZiBzZXJ2ZXIgZGF0YSkKZnVuY3Rpb24gZ2V0Q2xhc3NBYmlsaXRpZXNKUyhjbHMsIGxldmVsKSB7CiAgY29uc3QgYWxsX2FiaWxpdGllcyA9IHsKICAgIEZpZ2h0ZXI6ICAgeyA0Olt7bmFtZTonRXh0cmEgQXR0YWNrJyxkZXNjOiczIGF0dGFja3MgcGVyIDIgcm91bmRzJyx1c2VzOid1bmxpbWl0ZWQnfV0sCiAgICAgICAgICAgICAgICAgODpbe25hbWU6J0V4dHJhIEF0dGFjaycsZGVzYzonMiBhdHRhY2tzIHBlciByb3VuZCcsdXNlczondW5saW1pdGVkJ31dIH0sCiAgICBDbGVyaWM6ICAgIHsgMTpbe25hbWU6J1R1cm4gVW5kZWFkJyxkZXNjOidUdXJuIHVuZGVhZCB1c2luZyAyZDYgdnMgVHVybiB0YWJsZScsdXNlczondW5saW1pdGVkJ31dIH0sCiAgICBQYWxhZGluOiAgIHsgMTpbe25hbWU6J0RldGVjdCBFdmlsJyxkZXNjOidEZXRlY3QgZXZpbCA2MGZ0IGF0IHdpbGwnLHVzZXM6J2F0X3dpbGwnfSwKICAgICAgICAgICAgICAgICAgICB7bmFtZTonTGF5IG9uIEhhbmRzJyxkZXNjOidIZWFsIDJIUC9sZXZlbC9kYXknLHVzZXM6JzFfcGVyX2RheSd9LAogICAgICAgICAgICAgICAgICAgIHtuYW1lOidEaXNlYXNlIEltbXVuaXR5JyxkZXNjOidJbW11bmUgdG8gZGlzZWFzZScsdXNlczoncGFzc2l2ZSd9XSwKICAgICAgICAgICAgICAgICAzOlt7bmFtZTonVHVybiBVbmRlYWQnLGRlc2M6J1R1cm4gdW5kZWFkIGFzIENsZXJpYyAyIGxldmVscyBsb3dlcicsdXNlczondW5saW1pdGVkJ31dIH0sCiAgICBUaGllZjogICAgIHsgMTpbe25hbWU6J0JhY2tzdGFiJyxkZXNjOid4MiBkYW1hZ2UgZnJvbSBoaWRpbmcnLHVzZXM6J3Blcl9oaWRkZW5fYXR0YWNrJ31dLAogICAgICAgICAgICAgICAgIDU6W3tuYW1lOidCYWNrc3RhYicsZGVzYzoneDMgYmFja3N0YWInLHVzZXM6J3Blcl9oaWRkZW5fYXR0YWNrJ31dLAogICAgICAgICAgICAgICAgIDk6W3tuYW1lOidCYWNrc3RhYicsZGVzYzoneDQgYmFja3N0YWInLHVzZXM6J3Blcl9oaWRkZW5fYXR0YWNrJ31dIH0sCiAgICBBc3Nhc3NpbjogIHsgMTpbe25hbWU6J0JhY2tzdGFiJyxkZXNjOid4MiBiYWNrc3RhYicsdXNlczoncGVyX2hpZGRlbl9hdHRhY2snfSwKICAgICAgICAgICAgICAgICAgICB7bmFtZTonRGlzZ3Vpc2UnLGRlc2M6J0Rpc2d1aXNlIHNlbGYgKGJhc2UgNzAlKScsdXNlczondW5saW1pdGVkJ31dLAogICAgICAgICAgICAgICAgIDk6W3tuYW1lOidBc3Nhc3NpbmF0ZScsZGVzYzonSW5zdGFudCBraWxsIHN1cnByaXNlZCB0YXJnZXRzJyx1c2VzOidwZXJfc3VycHJpc2VkX3ZpY3RpbSd9XSB9LAogICAgQmFyYmFyaWFuOiB7IDE6W3tuYW1lOidSYWdlJyxkZXNjOicrMiBhdHRhY2svZGFtYWdlLCAtMiBBQyBmb3IgMyByb3VuZHMnLHVzZXM6JzFfcGVyX2RheSd9LAogICAgICAgICAgICAgICAgICAgIHtuYW1lOidUcmFwIFNlbnNlJyxkZXNjOicrMiBzYXZlcyB2cyB0cmFwcycsdXNlczoncGFzc2l2ZSd9XSwKICAgICAgICAgICAgICAgICA0Olt7bmFtZTonUmFnZScsZGVzYzonUmFnZSAyL2RheScsdXNlczonMl9wZXJfZGF5J31dLAogICAgICAgICAgICAgICAgIDc6W3tuYW1lOidSYWdlJyxkZXNjOidSYWdlIDMvZGF5Jyx1c2VzOiczX3Blcl9kYXknfSwKICAgICAgICAgICAgICAgICAgICB7bmFtZTonSW50aW1pZGF0ZScsZGVzYzonRmVhciAxL2RheScsdXNlczonMV9wZXJfZGF5J31dIH0sCiAgICBSYW5nZXI6ICAgIHsgMTpbe25hbWU6J1RyYWNraW5nJyxkZXNjOidUcmFjayBjcmVhdHVyZXMgb3V0ZG9vcnMnLHVzZXM6J3VubGltaXRlZCd9LAogICAgICAgICAgICAgICAgICAgIHtuYW1lOidGYXZvdXJlZCBFbmVteScsZGVzYzonKzEgYXR0YWNrL2RhbWFnZSB2cyBjaG9zZW4gdHlwZScsdXNlczoncGFzc2l2ZSd9XSB9LAogICAgRHJ1aWQ6ICAgICB7IDc6W3tuYW1lOidTaGFwZWNoYW5nZScsZGVzYzonQW5pbWFsIGZvcm0gMy9kYXknLHVzZXM6JzNfcGVyX2RheSd9XSB9LAogICAgQmFyZDogICAgICB7IDE6W3tuYW1lOidJbnNwaXJlIENvdXJhZ2UnLGRlc2M6JysxIGFsbGllcyBhdHRhY2svc2F2ZXMnLHVzZXM6J2NvbmNlbnRyYXRpb24nfSwKICAgICAgICAgICAgICAgICAgICB7bmFtZTonQmFyZCBMb3JlJyxkZXNjOidLbm93IGxlZ2VuZC9oaXN0b3J5IDEtMi9kNicsdXNlczondW5saW1pdGVkJ31dLAogICAgICAgICAgICAgICAgIDI6W3tuYW1lOidDaGFybSBQZXJzb24nLGRlc2M6JzEvZGF5IGFzIHNwZWxsJyx1c2VzOicxX3Blcl9kYXknfV0gfSwKICAgIE1vbms6ICAgICAgeyAxOlt7bmFtZTonU3R1bm5pbmcgQXR0YWNrJyxkZXNjOidTdHVuIG9uIGhpdCAoc2F2ZSB2cyBEZWF0aCknLHVzZXM6JzFfcGVyX3JvdW5kJ31dLAogICAgICAgICAgICAgICAgIDc6W3tuYW1lOidXaG9sZW5lc3Mgb2YgQm9keScsZGVzYzonSGVhbCAySFAvbGV2ZWwgMS9kYXknLHVzZXM6JzFfcGVyX2RheSd9XSB9LAogIH07CiAgY29uc3QgdGJsID0gYWxsX2FiaWxpdGllc1tjbHNdIHx8IHt9OwogIGNvbnN0IHJlc3VsdCA9IFtdOwogIGNvbnN0IHNlZW4gPSBuZXcgU2V0KCk7CiAgT2JqZWN0LmVudHJpZXModGJsKS5zb3J0KChbYV0sW2JdKT0+YS1iKS5mb3JFYWNoKChbcmVxTHZsLCBhYnNdKSA9PiB7CiAgICBpZiAocGFyc2VJbnQocmVxTHZsKSA8PSBsZXZlbCkgewogICAgICBhYnMuZm9yRWFjaChhYiA9PiB7CiAgICAgICAgaWYgKCFzZWVuLmhhcyhhYi5uYW1lKSkgeyBzZWVuLmFkZChhYi5uYW1lKTsgcmVzdWx0LnB1c2goYWIpOyB9CiAgICAgICAgZWxzZSB7CiAgICAgICAgICAvLyBSZXBsYWNlIHdpdGggaGlnaGVyIGxldmVsIHZlcnNpb24KICAgICAgICAgIGNvbnN0IGkgPSByZXN1bHQuZmluZEluZGV4KHIgPT4gci5uYW1lID09PSBhYi5uYW1lKTsKICAgICAgICAgIGlmIChpID49IDApIHJlc3VsdFtpXSA9IGFiOwogICAgICAgIH0KICAgICAgfSk7CiAgICB9CiAgfSk7CiAgcmV0dXJuIHJlc3VsdDsKfQoKLy8gU3BlbGwgZGF0YSBmb3IgbWVtb3JpemUgVUkgKG1pcnJvcnMgc2VydmVyIFB5dGhvbiBkYXRhKQovLyBUaGVzZSBhcmUganVzdCB0aGUgbmFtZXMgKyBtZXRhZGF0YSBuZWVkZWQgY2xpZW50LXNpZGUKY29uc3QgTVVfU1BFTExTX0ZPUl9DTEFTUyA9IHsKICAnQ2hhcm0gUGVyc29uJzp7bGV2ZWw6MSxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidTcGVjaWFsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0NoYXJtIG9uZSBodW1hbm9pZC4gU2F2ZSB2cyBTcGVsbHMuJ30sCiAgJ0RldGVjdCBNYWdpYyc6e2xldmVsOjEscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOicyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRGV0ZWN0IG1hZ2ljYWwgYXVyYXMuJ30sCiAgJ0Zsb2F0aW5nIERpc2MnOntsZXZlbDoxLHJhbmdlOic2ZnQnLGR1cmF0aW9uOic2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonSG92ZXJpbmcgZGlzYyBjYXJyaWVzIDUwMCBsYnMuJ30sCiAgJ0hvbGQgUG9ydGFsJzp7bGV2ZWw6MSxyYW5nZTonMTBmdCcsZHVyYXRpb246JzJkNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0hvbGQgZG9vci9nYXRlIHNodXQuJ30sCiAgJ0xpZ2h0Jzp7bGV2ZWw6MSxyYW5nZTonNjBmdCcsZHVyYXRpb246JzYgdHVybnMrMS9sdmwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonMTVmdCByYWRpdXMgbGlnaHQuJ30sCiAgJ01hZ2ljIE1pc3NpbGUnOntsZXZlbDoxLHJhbmdlOicxNTBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6JzFkNisxJyxkZXNjOidBdXRvLWhpdCBtaXNzaWxlLid9LAogICdQcm90ZWN0aW9uIGZyb20gRXZpbCc6e2xldmVsOjEscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMiB0dXJucy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOicrMSBBQyBhbmQgc2F2ZXMgdnMgZXZpbC4nfSwKICAnUmVhZCBMYW5ndWFnZXMnOntsZXZlbDoxLHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMSB0dXJuJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVhZCBhbnkgbGFuZ3VhZ2UuJ30sCiAgJ1JlYWQgTWFnaWMnOntsZXZlbDoxLHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMSB0dXJuJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVhZCBtYWdpY2FsIHdyaXRpbmdzLid9LAogICdTaGllbGQnOntsZXZlbDoxLHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0FDIDIgdnMgbWlzc2lsZXMsIDQgdnMgbWVsZWUuJ30sCiAgJ1NsZWVwJzp7bGV2ZWw6MSxyYW5nZTonMjQwZnQnLGR1cmF0aW9uOic0ZDQgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOicyZDggSEQgb2YgY3JlYXR1cmVzIGZhbGwgYXNsZWVwLid9LAogICdWZW50cmlsb3F1aXNtJzp7bGV2ZWw6MSxyYW5nZTonNjBmdCcsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidUaHJvdyB2b2ljZS4nfSwKICAnQ29udGludWFsIExpZ2h0Jzp7bGV2ZWw6MixyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonUGVybWFuZW50IGxpZ2h0IHNwaGVyZS4nfSwKICAnRGV0ZWN0IEV2aWwnOntsZXZlbDoyLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RldGVjdCBldmlsIGludGVudGlvbnMuJ30sCiAgJ0RldGVjdCBJbnZpc2libGUnOntsZXZlbDoyLHJhbmdlOicxMGZ0L2x2bCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTZWUgaW52aXNpYmxlIGNyZWF0dXJlcy4nfSwKICAnRVNQJzp7bGV2ZWw6MixyYW5nZTonNjBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZWFkIHN1cmZhY2UgdGhvdWdodHMuJ30sCiAgJ0ludmlzaWJpbGl0eSc6e2xldmVsOjIscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonVW50aWwgYXR0YWNrJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonSW52aXNpYmxlIHVudGlsIGF0dGFja2luZy4nfSwKICAnS25vY2snOntsZXZlbDoyLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J09wZW4gbG9ja2VkIGRvb3JzL2NoZXN0cy4nfSwKICAnTGV2aXRhdGUnOntsZXZlbDoyLHJhbmdlOicyMGZ0L2x2bCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSaXNlL2Rlc2NlbmQgYXQgNmZ0L3JvdW5kLid9LAogICdMb2NhdGUgT2JqZWN0Jzp7bGV2ZWw6MixyYW5nZTonNjBmdCsxMC9sdmwnLGR1cmF0aW9uOicxIHJvdW5kJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU2Vuc2UgZGlyZWN0aW9uIHRvIG9iamVjdC4nfSwKICAnTWlycm9yIEltYWdlJzp7bGV2ZWw6MixyYW5nZTonU2VsZicsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6JzFkNCcsZGVzYzonMWQ0IGlsbHVzb3J5IGR1cGxpY2F0ZXMuJ30sCiAgJ1BoYW50YXNtYWwgRm9yY2UnOntsZXZlbDoyLHJhbmdlOicyNDBmdCcsZHVyYXRpb246J0NvbmNlbnRyYXRpb24nLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonSWxsdXNpb24gdXAgdG8gMjB4MjB4MjBmdC4nfSwKICAnV2ViJzp7bGV2ZWw6MixyYW5nZTonMTBmdCcsZHVyYXRpb246JzQ4IHR1cm5zJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J1N0aWNreSB3ZWJzIGVudGFuZ2xlIGNyZWF0dXJlcy4nfSwKICAnV2l6YXJkIExvY2snOntsZXZlbDoyLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1Blcm1hbmVudGx5IGxvY2sgZG9vci9jaGVzdC4nfSwKICAnQ2xhaXJ2b3lhbmNlJzp7bGV2ZWw6MyxyYW5nZTonNjBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTZWUgdGhyb3VnaCB3YWxscy4nfSwKICAnRGlzcGVsIE1hZ2ljJzp7bGV2ZWw6MyxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVtb3ZlIG1hZ2ljIGVmZmVjdHMuJ30sCiAgJ0ZpcmViYWxsJzp7bGV2ZWw6MyxyYW5nZTonMjQwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOidTcGVsbHMnLGRtZzonMWQ2L2x2bCcsZGVzYzonMjBmdCBleHBsb3Npb24uJ30sCiAgJ0ZseSc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMWQ2KzEgdHVybnMvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRmx5IGF0IDEyMGZ0L3R1cm4uJ30sCiAgJ0hhc3RlJzp7bGV2ZWw6MyxyYW5nZTonMjQwZnQnLGR1cmF0aW9uOiczIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRG91YmxlIHNwZWVkL2F0dGFja3MuIEFnZXMgMSB5ZWFyLid9LAogICdIb2xkIFBlcnNvbic6e2xldmVsOjMscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOicxLTQgaHVtYW5vaWRzIHBhcmFseXNlZC4nfSwKICAnSW5mcmF2aXNpb24nOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzEgZGF5JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonU2VlIGluIGRhcmtuZXNzIDYwZnQuJ30sCiAgJ0ludmlzaWJpbGl0eSAxMGZ0IFJhZGl1cyc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonVW50aWwgYXR0YWNrJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQWxsIGluIDEwZnQgaW52aXNpYmxlLid9LAogICdMaWdodG5pbmcgQm9sdCc6e2xldmVsOjMscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOidTcGVsbHMnLGRtZzonMWQ2L2x2bCcsZGVzYzonNjBmdCBib2x0Lid9LAogICdQcm90ZWN0aW9uIGZyb20gRXZpbCAxMGZ0IFJhZGl1cyc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMiB0dXJucy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidQcm90ZWN0aW9uIGF1cmEgMTBmdC4nfSwKICAnUHJvdGVjdGlvbiBmcm9tIE5vcm1hbCBNaXNzaWxlcyc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonMiB0dXJucy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidJbW11bmUgdG8gbm9uLW1hZ2ljYWwgbWlzc2lsZXMuJ30sCiAgJ1dhdGVyIEJyZWF0aGluZyc6e2xldmVsOjMscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOicxIGRheScsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0JyZWF0aGUgdW5kZXJ3YXRlci4nfSwKICAnQ2hhcm0gTW9uc3Rlcic6e2xldmVsOjQscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonU3BlY2lhbCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidDaGFybSBhbnkgY3JlYXR1cmUgdHlwZS4nfSwKICAnQ29uZnVzaW9uJzp7bGV2ZWw6NCxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOicyIHJvdW5kcy9sdmwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonMmQ2IGNyZWF0dXJlcyBhY3QgcmFuZG9tbHkuJ30sCiAgJ0RpbWVuc2lvbiBEb29yJzp7bGV2ZWw6NCxyYW5nZTonU2VsZicsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidUZWxlcG9ydCAzNjBmdCBpbnN0YW50bHkuJ30sCiAgJ0dyb3d0aCBvZiBQbGFudHMnOntsZXZlbDo0LHJhbmdlOicxMjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RlbnNlIGVudGFuZ2xpbmcgcGxhbnRzLid9LAogICdJY2UgU3Rvcm0nOntsZXZlbDo0LHJhbmdlOicxMjBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6JzNkMTAnLGRlc2M6JzNkMTAgaGFpbCBkYW1hZ2UuJ30sCiAgJ1BvbHltb3JwaCBPdGhlcnMnOntsZXZlbDo0LHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J1RyYW5zZm9ybSBjcmVhdHVyZS4nfSwKICAnUG9seW1vcnBoIFNlbGYnOntsZXZlbDo0LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonNiB0dXJucy9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidUYWtlIGNyZWF0dXJlIGZvcm0uJ30sCiAgJ1JlbW92ZSBDdXJzZSc6e2xldmVsOjQscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVtb3ZlIG9uZSBjdXJzZS4nfSwKICAnV2FsbCBvZiBGaXJlJzp7bGV2ZWw6NCxyYW5nZTonNjBmdCcsZHVyYXRpb246J0NvbmNlbnRyYXRpb24nLHNhdmU6bnVsbCxkbWc6JzJkNisxJyxkZXNjOidGaXJlIHdhbGwgZGFtYWdlLid9LAogICdXaXphcmQgRXllJzp7bGV2ZWw6NCxyYW5nZTonMjQwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonSW52aXNpYmxlIGV5ZSBzY291dHMgYWhlYWQuJ30sCiAgJ0FuaW1hdGUgRGVhZCc6e2xldmVsOjUscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmFpc2UgdW5kZWFkIHNlcnZhbnRzLid9LAogICdDbG91ZGtpbGwnOntsZXZlbDo1LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonMSB0dXJuJyxzYXZlOidEZWF0aCcsZG1nOm51bGwsZGVzYzonUG9pc29ub3VzIGNsb3VkIGtpbGxzIDw1IEhELid9LAogICdDb25qdXJlIEVsZW1lbnRhbCc6e2xldmVsOjUscmFuZ2U6JzI0MGZ0JyxkdXJhdGlvbjonQ29uY2VudHJhdGlvbicsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1N1bW1vbiAxNiBIRCBlbGVtZW50YWwuJ30sCiAgJ0ZlZWJsZW1pbmQnOntsZXZlbDo1LHJhbmdlOicyNDBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTonU3BlbGxzLTQnLGRtZzpudWxsLGRlc2M6J0lOVCByZWR1Y2VkIHRvIDIuJ30sCiAgJ0hvbGQgTW9uc3Rlcic6e2xldmVsOjUscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOicxLTQgY3JlYXR1cmVzIHBhcmFseXNlZC4nfSwKICAnUGFzcy1XYWxsJzp7bGV2ZWw6NSxyYW5nZTonMzBmdCcsZHVyYXRpb246JzMgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidUdW5uZWwgdGhyb3VnaCBzdG9uZS4nfSwKICAnVGVsZWtpbmVzaXMnOntsZXZlbDo1LHJhbmdlOicxMjBmdCcsZHVyYXRpb246JzIgcm91bmRzL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J01vdmUgMjAwIGxicy9sZXZlbC4nfSwKICAnVGVsZXBvcnQnOntsZXZlbDo1LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidJbnN0YW50IHRyYW5zcG9ydC4nfSwKICAnV2FsbCBvZiBTdG9uZSc6e2xldmVsOjUscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDcmVhdGUgc3RvbmUgd2FsbC4nfSwKICAnQW50aS1NYWdpYyBTaGVsbCc6e2xldmVsOjYscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQmxvY2tzIGFsbCBtYWdpYy4nfSwKICAnRGVhdGggU3BlbGwnOntsZXZlbDo2LHJhbmdlOicyNDBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6JzRkOCcsZGVzYzonVXAgdG8gNGQ4IEhEIGRpZSBpbnN0YW50bHkuJ30sCiAgJ0Rpc2ludGVncmF0ZSc6e2xldmVsOjYscmFuZ2U6JzYwZnQnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0Rlc3Ryb3kgdGFyZ2V0IHV0dGVybHkuJ30sCiAgJ0dlYXMnOntsZXZlbDo2LHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonVW50aWwgZnVsZmlsbGVkJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0NvbXBlbCB0byBjb21wbGV0ZSBxdWVzdC4nfSwKICAnSW52aXNpYmxlIFN0YWxrZXInOntsZXZlbDo2LHJhbmdlOidTZWxmJyxkdXJhdGlvbjonVW50aWwgZG9uZScsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1N1bW1vbiBodW50ZXIuJ30sCiAgJ01vdmUgRWFydGgnOntsZXZlbDo2LHJhbmdlOicyNDBmdCcsZHVyYXRpb246JzYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidNb3ZlIGRpcnQvY2xheS4nfSwKICAnUmVpbmNhcm5hdGlvbic6e2xldmVsOjYscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmV0dXJuIGRlYWQgaW4gbmV3IGJvZHkuJ30sCiAgJ1N0b25lIHRvIEZsZXNoJzp7bGV2ZWw6NixyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZXZlcnNlIHBldHJpZmljYXRpb24uJ30sCn07Cgpjb25zdCBDTEVSSUNfU1BFTExTX0ZPUl9DTEFTUyA9IHsKICAnQ3VyZSBMaWdodCBXb3VuZHMnOntsZXZlbDoxLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzonMWQ2KzEnLGRlc2M6J1Jlc3RvcmUgMWQ2KzEgSFAuJ30sCiAgJ0RldGVjdCBFdmlsJzp7bGV2ZWw6MSxyYW5nZTonNjBmdCcsZHVyYXRpb246JzYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZXRlY3QgZXZpbC4nfSwKICAnRGV0ZWN0IE1hZ2ljJzp7bGV2ZWw6MSxyYW5nZTonNjBmdCcsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZXRlY3QgbWFnaWMuJ30sCiAgJ0xpZ2h0Jzp7bGV2ZWw6MSxyYW5nZTonNjBmdCcsZHVyYXRpb246JzYgdHVybnMrMS9sdmwnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonMTVmdCByYWRpdXMgbGlnaHQuJ30sCiAgJ1Byb3RlY3Rpb24gZnJvbSBFdmlsJzp7bGV2ZWw6MSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicyIHR1cm5zL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6JysxIEFDL3NhdmVzIHZzIGV2aWwuJ30sCiAgJ1B1cmlmeSBGb29kICYgV2F0ZXInOntsZXZlbDoxLHJhbmdlOicxMGZ0JyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUHVyaWZ5IGZvb2Qvd2F0ZXIuJ30sCiAgJ1JlbW92ZSBGZWFyJzp7bGV2ZWw6MSxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidTcGVjaWFsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVtb3ZlIGZlYXIgZWZmZWN0Lid9LAogICdSZXNpc3QgQ29sZCc6e2xldmVsOjEscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonKzMgc2F2ZXMgdnMgY29sZC4nfSwKICAnQmxlc3MnOntsZXZlbDoyLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6JysxIGF0dGFjayBhbmQgbW9yYWxlLid9LAogICdGaW5kIFRyYXBzJzp7bGV2ZWw6MixyYW5nZTonMzBmdCcsZHVyYXRpb246JzIgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZXRlY3QgdHJhcHMgMzBmdC4nfSwKICAnSG9sZCBQZXJzb24nOntsZXZlbDoyLHJhbmdlOicxODBmdCcsZHVyYXRpb246JzkgdHVybnMnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonMS0zIGh1bWFub2lkcyBwYXJhbHlzZWQuJ30sCiAgJ0tub3cgQWxpZ25tZW50Jzp7bGV2ZWw6MixyYW5nZTonMTBmdCcsZHVyYXRpb246JzEgcm91bmQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidMZWFybiBleGFjdCBhbGlnbm1lbnQuJ30sCiAgJ1Jlc2lzdCBGaXJlJzp7bGV2ZWw6MixyYW5nZTonMzBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOicrMiBzYXZlcyB2cyBtYWdpY2FsIGZpcmUuJ30sCiAgJ1NpbGVuY2UgMTVmdCBSYWRpdXMnOntsZXZlbDoyLHJhbmdlOicxODBmdCcsZHVyYXRpb246JzEyIHR1cm5zJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J05vIHNvdW5kIGluIGFyZWEuJ30sCiAgJ1NuYWtlIENoYXJtJzp7bGV2ZWw6MixyYW5nZTonNjBmdCcsZHVyYXRpb246J1NwZWNpYWwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDaGFybSAxIEhEL2xldmVsIG9mIHNuYWtlcy4nfSwKICAnU3BlYWsgd2l0aCBBbmltYWxzJzp7bGV2ZWw6MixyYW5nZTonMzBmdCcsZHVyYXRpb246JzYgdHVybnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDb21tdW5pY2F0ZSB3aXRoIGFuaW1hbHMuJ30sCiAgJ0N1cmUgRGlzZWFzZSc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ3VyZSBvbmUgZGlzZWFzZS4nfSwKICAnR3Jvd3RoIG9mIEFuaW1hbHMnOntsZXZlbDozLHJhbmdlOicxMjBmdCcsZHVyYXRpb246JzEyIHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonRG91YmxlIGFuaW1hbCBzaXplLid9LAogICdMb2NhdGUgT2JqZWN0Jzp7bGV2ZWw6MyxyYW5nZTonOTBmdCsxMC9sdmwnLGR1cmF0aW9uOicxIHJvdW5kL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1NlbnNlIGRpcmVjdGlvbiB0byBvYmplY3QuJ30sCiAgJ1JlbW92ZSBDdXJzZSc6e2xldmVsOjMscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmVtb3ZlIG9uZSBjdXJzZS4nfSwKICAnU3RyaWtpbmcnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzEgdHVybicsc2F2ZTpudWxsLGRtZzonMWQ2JyxkZXNjOicrMWQ2IGRhbWFnZSwgd2VhcG9uIGNvdW50cyBhcyBtYWdpY2FsLid9LAogICdDb250aW51YWwgTGlnaHQnOntsZXZlbDozLHJhbmdlOicxMjBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidQZXJtYW5lbnQgbGlnaHQuJ30sCiAgJ0NyZWF0ZSBXYXRlcic6e2xldmVsOjQscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQ3JlYXRlIDUwIGdhbC9sZXZlbC4nfSwKICAnQ3VyZSBTZXJpb3VzIFdvdW5kcyc6e2xldmVsOjQscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOicyZDYrMicsZGVzYzonUmVzdG9yZSAyZDYrMiBIUC4nfSwKICAnTmV1dHJhbGl6ZSBQb2lzb24nOntsZXZlbDo0LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlbW92ZSBwb2lzb24uJ30sCiAgJ1Byb3RlY3Rpb24gZnJvbSBFdmlsIDEwZnQgUmFkaXVzJzp7bGV2ZWw6NCxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicyIHR1cm5zL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1Byb3RlY3Rpb24gYXVyYS4nfSwKICAnU3BlYWsgd2l0aCBQbGFudHMnOntsZXZlbDo0LHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonMyB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NvbW11bmljYXRlIHdpdGggcGxhbnRzLid9LAogICdTdGlja3MgdG8gU25ha2VzJzp7bGV2ZWw6NCxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOic2IHR1cm5zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonMmQ4IHN0aWNrcyBiZWNvbWUgc25ha2VzLid9LAogICdUb25ndWVzJzp7bGV2ZWw6NCxyYW5nZTonU2VsZicsZHVyYXRpb246JzEgdHVybicsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1VuZGVyc3RhbmQvc3BlYWsgYW55IGxhbmd1YWdlLid9LAogICdDb21tdW5lJzp7bGV2ZWw6NSxyYW5nZTonU2VsZicsZHVyYXRpb246JzMgcXVlc3Rpb25zJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQXNrIGRlaXR5IDMgeWVzL25vIHF1ZXN0aW9ucy4nfSwKICAnQ3JlYXRlIEZvb2QnOntsZXZlbDo1LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0Zvb2QgZm9yIDI0IHBlciBsZXZlbC4nfSwKICAnQ3VyZSBDcml0aWNhbCBXb3VuZHMnOntsZXZlbDo1LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzonM2Q2KzMnLGRlc2M6J1Jlc3RvcmUgM2Q2KzMgSFAuJ30sCiAgJ0Rpc3BlbCBFdmlsJzp7bGV2ZWw6NSxyYW5nZTonMzBmdCcsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6J1NwZWxscycsZG1nOm51bGwsZGVzYzonRGlzcGVsIGV2aWwgY3JlYXR1cmUvZW5jaGFudG1lbnQuJ30sCiAgJ0luc2VjdCBQbGFndWUnOntsZXZlbDo1LHJhbmdlOic0ODBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidTd2FybSByb3V0cyA8MyBIRC4nfSwKICAnUXVlc3QnOntsZXZlbDo1LHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonVW50aWwgZnVsZmlsbGVkJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J0NvbXBlbCBxdWVzdCBjb21wbGV0aW9uLid9LAogICdSYWlzZSBEZWFkJzp7bGV2ZWw6NSxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidSZXN0b3JlIGxpZmUuJ30sCiAgJ1RydWUgU2VlaW5nJzp7bGV2ZWw6NSxyYW5nZTonMTIwZnQnLGR1cmF0aW9uOicxIHJvdW5kL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1NlZSBpbnZpc2libGUvaWxsdXNpb25zLid9LAogICdBbmltYXRlIE9iamVjdHMnOntsZXZlbDo2LHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMSByb3VuZC9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidBbmltYXRlIG5vbi1saXZpbmcgb2JqZWN0cy4nfSwKICAnQmxhZGUgQmFycmllcic6e2xldmVsOjYscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOiczIHJvdW5kcy9sdmwnLHNhdmU6bnVsbCxkbWc6JzJkNicsZGVzYzonV2FsbCBvZiBibGFkZXMgMmQ2Lid9LAogICdGaW5kIHRoZSBQYXRoJzp7bGV2ZWw6NixyYW5nZTonVG91Y2gnLGR1cmF0aW9uOicxIHR1cm4vbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonS25vdyByb3V0ZSB0byBkZXN0aW5hdGlvbi4nfSwKICAnU3BlYWsgd2l0aCBNb25zdGVycyc6e2xldmVsOjYscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOicxIHJvdW5kL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NvbW11bmljYXRlIHdpdGggYW55IGNyZWF0dXJlLid9LAogICdXb3JkIG9mIFJlY2FsbCc6e2xldmVsOjYscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOidJbnN0YW50JyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonUmV0dXJuIHRvIHNhbmN0dWFyeSBpbnN0YW50bHkuJ30sCn07CgovLyBEcnVpZC9SYW5nZXIvUGFsYWRpbiB1c2Ugc3Vic2V0IG9mIENsZXJpYyBzcGVsbHMgKyBzb21lIERydWlkLXNwZWNpZmljCmNvbnN0IERSVUlEX1NQRUxMU19GT1JfQ0xBU1MgPSB7CiAgJ0FuaW1hbCBGcmllbmRzaGlwJzp7bGV2ZWw6MSxyYW5nZTonMTBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTonU3BlbGxzJyxkbWc6bnVsbCxkZXNjOidCZWZyaWVuZCBub3JtYWwgYW5pbWFsLid9LAogICdEZXRlY3QgTWFnaWMnOntsZXZlbDoxLHJhbmdlOic2MGZ0JyxkdXJhdGlvbjonMiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0RldGVjdCBtYWdpYy4nfSwKICAnRW50YW5nbGUnOntsZXZlbDoxLHJhbmdlOic4MGZ0JyxkdXJhdGlvbjonMSB0dXJuJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6J1BsYW50cyBncmFzcCBjcmVhdHVyZXMuJ30sCiAgJ0ZhZXJpZSBGaXJlJzp7bGV2ZWw6MSxyYW5nZTonODBmdCcsZHVyYXRpb246JzQgcm91bmRzL2x2bCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J091dGxpbmUgY3JlYXR1cmVzLCAtMiBBQy4nfSwKICAnUHVyaWZ5IFdhdGVyJzp7bGV2ZWw6MSxyYW5nZTonNDBmdCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1B1cmlmeSAxIGN1IGZ0L2xldmVsLid9LAogICdTcGVhayB3aXRoIEFuaW1hbHMnOntsZXZlbDoxLHJhbmdlOiczMGZ0JyxkdXJhdGlvbjonNiB0dXJucycsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0NvbW11bmljYXRlIHdpdGggYW5pbWFscy4nfSwKICAnQmFya3NraW4nOntsZXZlbDoyLHJhbmdlOidUb3VjaCcsZHVyYXRpb246JzQgcm91bmRzKzEvbHZsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQUMgYmVjb21lcyA2IG1pbi4nfSwKICAnQ3VyZSBMaWdodCBXb3VuZHMnOntsZXZlbDoyLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzonMWQ2KzEnLGRlc2M6J1Jlc3RvcmUgMWQ2KzEgSFAuJ30sCiAgJ0hlYXQgTWV0YWwnOntsZXZlbDoyLHJhbmdlOic0MGZ0JyxkdXJhdGlvbjonNyByb3VuZHMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidNZXRhbCBoZWF0cyBkYW5nZXJvdXNseS4nfSwKICAnUHJvZHVjZSBGbGFtZSc6e2xldmVsOjIscmFuZ2U6J1NlbGYnLGR1cmF0aW9uOicxIHJvdW5kL2x2bCcsc2F2ZTpudWxsLGRtZzonMWQ0KzEnLGRlc2M6J0ZsYW1lIHdlYXBvbiBvciBtaXNzaWxlLid9LAogICdDYWxsIExpZ2h0bmluZyc6e2xldmVsOjMscmFuZ2U6JzM2MGZ0JyxkdXJhdGlvbjonMSB0dXJuL2x2bCcsc2F2ZTonU3BlbGxzJyxkbWc6JzJkOCtsdmwnLGRlc2M6J0xpZ2h0bmluZyAxL3JvdW5kIG91dGRvb3JzLid9LAogICdDdXJlIERpc2Vhc2UnOntsZXZlbDozLHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0N1cmUgZGlzZWFzZS4nfSwKICAnSG9sZCBBbmltYWwnOntsZXZlbDozLHJhbmdlOic4MGZ0JyxkdXJhdGlvbjonMiByb3VuZHMvbHZsJyxzYXZlOidTcGVsbHMnLGRtZzpudWxsLGRlc2M6JzEtNCBhbmltYWxzIHBhcmFseXNlZC4nfSwKICAnUGxhbnQgR3Jvd3RoJzp7bGV2ZWw6MyxyYW5nZTonMTYwZnQnLGR1cmF0aW9uOidQZXJtYW5lbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidEZW5zZSBpbXBhc3NhYmxlIHZlZ2V0YXRpb24uJ30sCiAgJ1Byb3RlY3Rpb24gZnJvbSBGaXJlJzp7bGV2ZWw6MyxyYW5nZTonVG91Y2gnLGR1cmF0aW9uOidTcGVjaWFsJyxzYXZlOm51bGwsZG1nOm51bGwsZGVzYzonQWJzb3JicyAxMiBwb2ludHMvbHZsIGZpcmUuJ30sCiAgJ1dhdGVyIEJyZWF0aGluZyc6e2xldmVsOjMscmFuZ2U6JzMwZnQnLGR1cmF0aW9uOicxIGRheScsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J0JyZWF0aGUgd2F0ZXIuJ30sCiAgJ0Rpc3BlbCBNYWdpYyc6e2xldmVsOjQscmFuZ2U6JzEyMGZ0JyxkdXJhdGlvbjonSW5zdGFudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlbW92ZSBtYWdpYy4nfSwKICAnTmV1dHJhbGl6ZSBQb2lzb24nOntsZXZlbDo0LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzpudWxsLGRlc2M6J1JlbW92ZSBwb2lzb24uJ30sCiAgJ0N1cmUgU2VyaW91cyBXb3VuZHMnOntsZXZlbDo0LHJhbmdlOidUb3VjaCcsZHVyYXRpb246J1Blcm1hbmVudCcsc2F2ZTpudWxsLGRtZzonMmQ2KzInLGRlc2M6J1Jlc3RvcmUgMmQ2KzIgSFAuJ30sCiAgJ0luc2VjdCBQbGFndWUnOntsZXZlbDo1LHJhbmdlOic0ODBmdCcsZHVyYXRpb246JzEgdHVybi9sdmwnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidJbnNlY3Qgc3dhcm0uJ30sCiAgJ1RyYW5zbXV0ZSBSb2NrIHRvIE11ZCc6e2xldmVsOjUscmFuZ2U6JzE2MGZ0JyxkdXJhdGlvbjonM2Q2IGRheXMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidUdXJuIHJvY2sgdG8gbXVkLid9LAogICdDb21tdW5lIHdpdGggTmF0dXJlJzp7bGV2ZWw6NSxyYW5nZTonU2VsZicsZHVyYXRpb246J0luc3RhbnQnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidLbm93IHRlcnJhaW4gMSBtaWxlL2xldmVsLid9LAogICdDdXJlIENyaXRpY2FsIFdvdW5kcyc6e2xldmVsOjYscmFuZ2U6J1RvdWNoJyxkdXJhdGlvbjonUGVybWFuZW50JyxzYXZlOm51bGwsZG1nOiczZDYrMycsZGVzYzonUmVzdG9yZSAzZDYrMyBIUC4nfSwKICAnQ29udHJvbCBXZWF0aGVyJzp7bGV2ZWw6NixyYW5nZTonU2VsZicsZHVyYXRpb246JzRkMTIgaG91cnMnLHNhdmU6bnVsbCxkbWc6bnVsbCxkZXNjOidDb250cm9sIGxvY2FsIHdlYXRoZXIuJ30sCn07Cgpjb25zdCBSQU5HRVJfU1BFTExTX0ZPUl9DTEFTUyA9IE9iamVjdC5mcm9tRW50cmllcygKICBPYmplY3QuZW50cmllcyhEUlVJRF9TUEVMTFNfRk9SX0NMQVNTKS5maWx0ZXIoKFssdl0pPT52LmxldmVsPD0zKQopOwpjb25zdCBCQVJEX1NQRUxMU19GT1JfQ0xBU1MgPSBPYmplY3QuZnJvbUVudHJpZXMoCiAgT2JqZWN0LmVudHJpZXMoQ0xFUklDX1NQRUxMU19GT1JfQ0xBU1MpLmZpbHRlcigoWyx2XSk9PnYubGV2ZWw8PTMpCik7CgovLyBQb3B1bGF0ZSBBTExfU1BFTExfTEVWRUxTIGxvb2t1cApbTVVfU1BFTExTX0ZPUl9DTEFTUywgQ0xFUklDX1NQRUxMU19GT1JfQ0xBU1MsIERSVUlEX1NQRUxMU19GT1JfQ0xBU1NdLmZvckVhY2godGJsID0+IHsKICBPYmplY3QuZW50cmllcyh0YmwpLmZvckVhY2goKFtuYW1lLGRhdGFdKSA9PiB7CiAgICBBTExfU1BFTExfTEVWRUxTW25hbWVdID0gZGF0YS5sZXZlbDsKICB9KTsKfSk7CgovLyA9PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT0KLy8gR0FNRSBJTklUIE9WRVJSSURFUyBGT1IgVjQKLy8gPT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT09CgovLyBDYWxsZWQgYWZ0ZXIgYmVnaW5BZHZlbnR1cmUgLyBsYXVuY2hHYW1lIHRvIGluaXQgVjQgc3RhdGUKZnVuY3Rpb24gaW5pdFY0U3RhdGUoKSB7CiAgLy8gSW5pdCBzcGVsbCBzbG90cyBmcm9tIGNsYXNzL2xldmVsCiAgY29uc3Qgc2xvdHMgPSBnZXRTcGVsbFNsb3RzSlMocGMuY2xzLCBwYy5sZXZlbCB8fCAxKTsKICBzcGVsbFNsb3RzVG90YWwgPSBzbG90czsKICBzcGVsbFNsb3RzUmVtYWluaW5nID0gWy4uLnNsb3RzXTsKCiAgLy8gQ2xlcmljcy9EcnVpZHMgc3RhcnQgd2l0aCBhbGwgc3BlbGxzIGF2YWlsYWJsZSAobm8gc3BlbGxib29rIG5lZWRlZCkKICBpZiAoWydDbGVyaWMnLCdEcnVpZCcsJ1JhbmdlcicsJ1BhbGFkaW4nXS5pbmNsdWRlcyhwYy5jbHMpKSB7CiAgICBzcGVsbEJvb2sgPSB7fTsgLy8gVGhleSBwcmF5IGZvciBzcGVsbHMsIG5vIGJvb2sgbmVlZGVkCiAgfQogIC8vIE1VL0lsbHVzaW9uaXN0IGdldCBzdGFydGluZyBzcGVsbHMgKFJlYWQgTWFnaWMgKyAxIHJhbmRvbSBsZXZlbCAxIHNwZWxsKQogIGlmIChbJ01hZ2ljLVVzZXInLCdJbGx1c2lvbmlzdCddLmluY2x1ZGVzKHBjLmNscykpIHsKICAgIGxlYXJuU3BlbGwoJ1JlYWQgTWFnaWMnLCB7bGV2ZWw6MSwgdHlwZTonbXUnfSk7CiAgICAvLyBQaWNrIGEgc3RhcnRpbmcgc3BlbGwgZnJvbSBsZXZlbCAxCiAgICBjb25zdCBsZXZlbDEgPSBPYmplY3QuZW50cmllcyhNVV9TUEVMTFNfRk9SX0NMQVNTKS5maWx0ZXIoKFssdl0pPT52LmxldmVsPT09MSk7CiAgICBpZiAobGV2ZWwxLmxlbmd0aCA+IDApIHsKICAgICAgY29uc3QgW3N0YXJ0U3BlbGwsIHN0YXJ0RGF0YV0gPSBsZXZlbDFbTWF0aC5mbG9vcihNYXRoLnJhbmRvbSgpKmxldmVsMS5sZW5ndGgpXTsKICAgICAgbGVhcm5TcGVsbChzdGFydFNwZWxsLCB7bGV2ZWw6MSwgdHlwZTonbXUnfSk7CiAgICB9CiAgfQoKICBpbkNvbWJhdCA9IGZhbHNlOwogIHBsYXllckhpZGRlbiA9IGZhbHNlOwogIGN1cnJlbnROUENzID0gW107CiAgYWN0aXZlRWZmZWN0c1Y0ID0gW107CiAgYWJpbGl0eVVzZXNUb2RheSA9IHt9OwoKICB1cGRhdGVTcGVsbGJvb2tQYW5lbCgpOwogIHVwZGF0ZUFiaWxpdHlQYW5lbCgpOwp9CgovLyBTcGVsbCBzbG90IHRhYmxlIEpTIG1pcnJvciAobWF0Y2hlcyBzZXJ2ZXIgUHl0aG9uIGRhdGEpCmZ1bmN0aW9uIGdldFNwZWxsU2xvdHNKUyhjbHMsIGxldmVsKSB7CiAgY29uc3QgdGFibGVzID0gewogICAgJ01hZ2ljLVVzZXInOiAgW1sxXSxbMl0sWzIsMV0sWzIsMl0sWzIsMiwxXSxbMiwyLDJdLFszLDIsMiwxXSxbMywzLDIsMl0sWzMsMywzLDIsMV0sWzMsMywzLDMsMl0sWzQsMywzLDMsMiwxXSxbNCw0LDMsMywzLDJdLFs0LDQsNCwzLDMsM10sWzQsNCw0LDQsNCw0XV0sCiAgICAnSWxsdXNpb25pc3QnOiBbWzFdLFsyXSxbMiwxXSxbMiwyXSxbMywyLDFdLFszLDIsMl0sWzMsMywyLDFdLFszLDMsMywyXSxbNCwzLDMsMiwxXSxbNCw0LDMsMywyXSxbNCw0LDQsMywyLDFdLFs0LDQsNCw0LDMsMl0sWzUsNSw0LDQsMywzXSxbNSw1LDUsNCw0LDRdXSwKICAgICdDbGVyaWMnOiAgICAgIFtbMV0sWzJdLFsyLDFdLFszLDJdLFszLDMsMV0sWzMsMywyXSxbMywzLDIsMV0sWzMsMywzLDJdLFs0LDQsMywyLDFdLFs0LDQsMywzLDJdLFs1LDQsNCwzLDIsMV0sWzUsNSw0LDQsMywyXSxbNSw1LDUsNCwzLDNdLFs2LDUsNSw1LDQsNF1dLAogICAgJ0RydWlkJzogICAgICAgW1sxXSxbMl0sWzIsMV0sWzMsMl0sWzMsMywxXSxbMywzLDJdLFszLDMsMiwxXSxbMywzLDMsMl0sWzQsNCwzLDIsMV0sWzQsNCwzLDMsMl0sWzUsNCw0LDMsMiwxXSxbNSw1LDQsNCwzLDJdLFs1LDUsNSw0LDMsM10sWzYsNSw1LDUsNCw0XV0sCiAgICAnUmFuZ2VyJzogICAgICBbW10sW10sW10sW10sW10sW10sW10sWzFdLFsxLDFdLFsyLDFdLFsyLDJdLFsyLDIsMV0sWzMsMiwxXSxbMywyLDJdXSwKICAgICdQYWxhZGluJzogICAgIFtbXSxbXSxbXSxbXSxbXSxbXSxbXSxbXSxbMV0sWzJdLFsyLDFdLFsyLDJdLFszLDJdLFszLDNdXSwKICB9OwogIGNvbnN0IHRibCA9IHRhYmxlc1tjbHNdOwogIGlmICghdGJsKSByZXR1cm4gW107CiAgY29uc3QgaWR4ID0gTWF0aC5taW4oKGxldmVsfHwxKS0xLCB0YmwubGVuZ3RoLTEpOwogIHJldHVybiBbLi4udGJsW2lkeF1dOwp9CgovLyBSZXNldCBhYmlsaXR5IHVzZXMgZGFpbHkgKGNhbGwgb24gZnVsbCByZXN0KQpmdW5jdGlvbiByZXNldERhaWx5QWJpbGl0aWVzKCkgewogIGFiaWxpdHlVc2VzVG9kYXkgPSB7fTsKICB1cGRhdGVBYmlsaXR5UGFuZWwoKTsKfQoKCi8vIC0tIFN0YXJ0dXAgLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0tLS0KCi8vIOKUgOKUgCAvR00gQ0hBTk5FTCDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIDilIAKLy8gSXNvbGF0ZWQgZnJvbSB0aGUgbmFycmF0aXZlLiBObyBoaXN0b3J5LiBObyBzdGF0ZSBjaGFuZ2VzLiBObyBuYXJyYXRpb24uCmFzeW5jIGZ1bmN0aW9uIGNhbGxHTUNoYW5uZWwocXVlc3Rpb24pIHsKICBpZiAoYnVzeSkgcmV0dXJuOwogIGJ1c3kgPSB0cnVlOwogIGNvbnN0IHNlbmRCdG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnc2VuZC1idG4nKTsKICBjb25zdCBjbWRJbnAgID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoJ2NtZCcpOwogIGlmIChzZW5kQnRuKSBzZW5kQnRuLmRpc2FibGVkID0gdHJ1ZTsKICBpZiAoY21kSW5wKSAgY21kSW5wLmRpc2FibGVkICA9IHRydWU7CgogIGNvbnN0IHRoaW5rRWwgPSBhZGRFbnRyeVJhdygnVGhlIEdNIGNvbnNpZGVycyB5b3VyIHF1ZXN0aW9uLi4uJywgJ3RoaW5raW5nJywgJ19fZ21fXycpOwoKICBjb25zdCBwY1N1bW1hcnkgPSBgQ2hhcmFjdGVyOiAke3BjLm5hbWV9LCAke3BjLnJhY2V8fCcnfSAke3BjLmNsc30gTGV2ZWwgJHtwYy5sZXZlbHx8MX0KSFA6ICR7cGMuaHB9LyR7cGMubWF4aHB9IHwgQUM6ICR7cGMuYWN9IHwgR29sZDogJHtwYy5nb2xkfWdwClNUUiAke3BjLnN0YXRzPy5TVFJ8fDEwfSBERVggJHtwYy5zdGF0cz8uREVYfHwxMH0gQ09OICR7cGMuc3RhdHM/LkNPTnx8MTB9IElOVCAke3BjLnN0YXRzPy5JTlR8fDEwfSBXSVMgJHtwYy5zdGF0cz8uV0lTfHwxMH0gQ0hBICR7cGMuc3RhdHM/LkNIQXx8MTB9CkludmVudG9yeTogJHsocGMuaW52fHxbXSkuam9pbignLCAnKXx8J2VtcHR5J30KU2F2ZXM6IERlYXRoICR7cGMuc2F2ZXM/LmRlYXRofHwxMn0sIFdhbmRzICR7cGMuc2F2ZXM/LndhbmRzfHwxM30sIFBhcmFseXNpcyAke3BjLnNhdmVzPy5wYXJhfHwxNH0sIEJyZWF0aCAke3BjLnNhdmVzPy5icmVhdGh8fDE1fSwgU3BlbGxzICR7cGMuc2F2ZXM/LnNwZWxsc3x8MTZ9Ck1lbW9yaXplZCBzcGVsbHM6ICR7bWVtb3JpemVkU3BlbGxzLm1hcChzPT50eXBlb2Ygcz09PSdzdHJpbmcnP3M6cy5uYW1lKS5qb2luKCcsICcpfHwnbm9uZSd9YDsKCiAgY29uc3QgdmlzaXRlZExvY3MgPSBbXTsKICBpZiAobG9hZGVkTW9kdWxlRGF0YSAmJiBsb2FkZWRNb2R1bGVEYXRhLmxvY2F0aW9ucykgewogICAgbG9hZGVkTW9kdWxlRGF0YS5sb2NhdGlvbnMuZm9yRWFjaChsb2MgPT4gewogICAgICBpZiAod29ybGRTdGF0ZS5sb2NhdGlvbnNfdmlzaXRlZFtsb2MubmFtZV0gfHwgbG9jLmlkID09PSBwYy5sb2N0YWcpIHsKICAgICAgICBjb25zdCBkZXNjID0gbG9jLnJlYWRfYWxvdWQgfHwgbG9jLndoYXRfcGxheWVyc19zZWUgfHwgJyc7CiAgICAgICAgaWYgKGRlc2MpIHZpc2l0ZWRMb2NzLnB1c2gobG9jLm5hbWUgKyAnOiAnICsgZGVzYyk7CiAgICAgIH0KICAgIH0pOwogIH0KICBjb25zdCBsb2NhdGlvbkN0eCA9IHZpc2l0ZWRMb2NzLmxlbmd0aAogICAgPyAnVklTSVRFRCBMT0NBVElPTlMgKHBsYXllci12aXNpYmxlIG9ubHkpOlxuJyArIHZpc2l0ZWRMb2NzLmpvaW4oJ1xuJykKICAgIDogKHBjLmxvYyA/ICdDdXJyZW50IGxvY2F0aW9uOiAnICsgcGMubG9jIDogJycpOwoKICBjb25zdCBnbVN5c3RlbSA9IGBZb3UgYXJlIGEgcnVsZXMgcmVmZXJlZSBmb3IgYW4gT1NFIEFkdmFuY2VkIEZhbnRhc3kgUlBHLgpCZSBjb25jaXNlIGFuZCBkaXJlY3QuIE5FVkVSIG5hcnJhdGUuIE5FVkVSIGFkdmFuY2UgdGhlIHN0b3J5LiBORVZFUiBhZHZpc2Ugb24gc3RyYXRlZ3kuCgpFTkdJTkU6IEN1c3RvbSBPU0UgQUYgcnVsZXMgZW5naW5lLiBEaWNlIGFyZSBzZXJ2ZXItc2lkZS4gTmFycmF0aW9uIHZpYSAke3dpbmRvdy5fc2VydmVyT2xsYW1hQXZhaWxhYmxlID8gJ09sbGFtYScgOiAnQ2xhdWRlIEFQSSd9LgoKQU5TV0VSIFRIRVNFOgotIE9TRSBBRiBydWxlcywgbWVjaGFuaWNzLCBzYXZpbmcgdGhyb3dzLCBtb3ZlbWVudCwgc3BlbGxzLCBjbGFzc2VzCi0gUGxheWVyJ3Mgb3duIGNoYXJhY3RlciBzdGF0cywgaW52ZW50b3J5LCBzYXZlcywgc3BlbGwgc2xvdHMKLSBXaGF0IHRoZSBjaGFyYWN0ZXIgY2FuIHBlcmNlaXZlIGluIHZpc2l0ZWQgbG9jYXRpb25zIChlbnZpcm9ubWVudCwgbGlnaHRpbmcsIHRlcnJhaW4pCi0gR2VuZXJpYyBtb25zdGVyIGRlc2NyaXB0aW9ucyBmcm9tIHRoZSBPU0UgcnVsZWJvb2sgYXQgc3BlY2llcyBsZXZlbCBvbmx5IC0tIE5FVkVSIHNwZWNpZmljIGluc3RhbmNlIHN0YXRzCi0gUGh5c2ljYWwgcG9zc2liaWxpdHk6IGNhbiBhIGh1bWFuIGRvIFggdW5haWRlZD8gV2hhdCBlcXVpcG1lbnQvc3BlbGwgZW5hYmxlcyBpdD8KLSBFbnZpcm9ubWVudGFsIHJ1bGVzIChzd2ltbWluZywgY2xpbWJpbmcsIGxpZ2h0aW5nKSAtLSBPU0UgcnVsZXMgb25seSwgTkVWRVIgbW9kdWxlIGhhemFyZHMKLSBIb3cgdGhlIGdhbWUgZW5naW5lIHdvcmtzLCB3aGljaCBBSSBtb2RlbCBpcyBydW5uaW5nCgpORVZFUiBBTlNXRVI6Ci0gU3BlY2lmaWMgY3JlYXR1cmUgSFAsIEFDLCBvciBzdGF0cyBvZiBhbnkgY3JlYXR1cmUgaW4gdGhlIGVuY291bnRlcgotIEhpZGRlbiByb29tIGZlYXR1cmVzLCB0cmFwcywgc2VjcmV0cyBub3QgeWV0IGZvdW5kCi0gTlBDIG1vdGl2YXRpb25zIG9yIEdNLW9ubHkgaW5mbwotIFVudmlzaXRlZCBsb2NhdGlvbnMKLSBUYWN0aWNhbCBhZHZpY2UgKCJhdHRhY2sgZmlyc3QiLCAicnVuIGF3YXkiKSAtLSByZWZ1c2U6ICJUaGF0IGlzIHlvdXIgZGVjaXNpb24gdG8gbWFrZS4iCi0gTW9kdWxlLXNwZWNpZmljIGhhemFyZHMgKCJ0aGVyZSBpcyBhbiBhbGxpZ2F0b3IgaW4gdGhhdCBzdHJlYW0iKSAtLSBydWxlcyBvbmx5Ci0gQW55dGhpbmcgZnVuY3Rpb25pbmcgYXMgYSBoaW50IG9yIHdhbGt0aHJvdWdoCgpQSFlTSUNBTCBQT1NTSUJJTElUWTogQW5zd2VyIGFzOiAoMSkgY2FuIGEgbm9ybWFsIGh1bWFuIGRvIHRoaXM/ICgyKSB3aGF0IGVxdWlwbWVudCBoZWxwcz8gKDMpIHdoYXQgc3BlbGwgZW5hYmxlcyBpdD8KCk1PTlNURVJTOiBTcGVjaWVzIGxldmVsIG9ubHkgZnJvbSB0aGUgcnVsZWJvb2suIE5ldmVyIGRlc2NyaWJlIHRoaXMgc3BlY2lmaWMgY3JlYXR1cmUncyBzdGF0cy4KRXhhbXBsZSBPSzogIkdvYmxpbnMgYXJlIHNtYWxsLCBjb3dhcmRseSBodW1hbm9pZHMgbW90aXZhdGVkIGJ5IHNlbGYtcHJlc2VydmF0aW9uLiIKRXhhbXBsZSBXUk9ORzogIlRoaXMgZ29ibGluIGhhcyA0IEhQIGFuZCBtb3JhbGUgNywgaXQgd2lsbCBmbGVlIGF0IDIgSFAuIgoKSWYgR00tb25seSBpbmZvOiAiVGhhdCBpcyBub3Qgc29tZXRoaW5nICR7cGMubmFtZXx8J3lvdXIgY2hhcmFjdGVyJ30gY2FuIGRldGVybWluZSBmcm9tIGhlcmUuIgpEZXNjcmliZSBwZXJjZXB0aWJsZSB0aGluZ3MgYXMgcGVyY2VwdGlvbiwgbm90IG51bWJlcnMuCgoke09TRV9NRUNIQU5JQ1NfUlVMRVNfSlN9CgpQTEFZRVIgQ0hBUkFDVEVSOgoke3BjU3VtbWFyeX0KCiR7bG9jYXRpb25DdHh9YDsKCiAgdHJ5IHsKICAgIGNvbnN0IHJlc3AgPSBhd2FpdCB4aHJGZXRjaChCQVNFX1VSTCArICcvYWknLCB7CiAgICAgIG1ldGhvZDogJ1BPU1QnLAogICAgICBoZWFkZXJzOiB7J0NvbnRlbnQtVHlwZSc6ICdhcHBsaWNhdGlvbi9qc29uJ30sCiAgICAgIGJvZHk6IEpTT04uc3RyaW5naWZ5KHsKICAgICAgICBhcGlfa2V5OiBhcGlLZXksCiAgICAgICAgc3lzdGVtOiBnbVN5c3RlbSwKICAgICAgICBtZXNzYWdlczogW3sgcm9sZTogJ3VzZXInLCBjb250ZW50OiBxdWVzdGlvbiB9XQogICAgICB9KQogICAgfSk7CiAgICBpZiAodGhpbmtFbCAmJiB0aGlua0VsLnBhcmVudE5vZGUpIHRoaW5rRWwucGFyZW50Tm9kZS5yZW1vdmVDaGlsZCh0aGlua0VsKTsKICAgIGNvbnN0IGRhdGEgPSBhd2FpdCByZXNwLmpzb24oKTsKICAgIGNvbnN0IGFuc3dlciA9IGRhdGEuY29udGVudCB8fCAnSSBjYW5ub3QgYW5zd2VyIHRoYXQgcmlnaHQgbm93Lic7CiAgICBhZGRFbnRyeVJhdygKICAgICAgJzxkaXYgc3R5bGU9ImJhY2tncm91bmQ6cmdiYSg1OCwxMDYsNTgsMC4wOCk7Ym9yZGVyOjFweCBzb2xpZCAjM2E2YTNhO2JvcmRlci1sZWZ0OjNweCBzb2xpZCAjNWE5YTVhO3BhZGRpbmc6OHB4IDEycHg7Zm9udC1zaXplOjE1cHg7bWFyZ2luOjRweCAwOyI+JyArCiAgICAgICc8c3BhbiBzdHlsZT0iY29sb3I6IzVhOWE1YTtmb250LXNpemU6MTFweDtsZXR0ZXItc3BhY2luZzoxcHg7dGV4dC10cmFuc2Zvcm06dXBwZXJjYXNlOyI+R00gUmVmZXJlZTwvc3Bhbj48YnI+JyArCiAgICAgIGZtdChhbnN3ZXIpICsgJzwvZGl2PicsCiAgICAgICdzeXN0ZW0nLCAnX19nbV9fJwogICAgKTsKICB9IGNhdGNoKGUpIHsKICAgIGlmICh0aGlua0VsICYmIHRoaW5rRWwucGFyZW50Tm9kZSkgdGhpbmtFbC5wYXJlbnROb2RlLnJlbW92ZUNoaWxkKHRoaW5rRWwpOwogICAgYWRkRW50cnlSYXcoJzxzcGFuIHN0eWxlPSJjb2xvcjojN2E5YTdhIj5bR01dIENvdWxkIG5vdCByZWFjaCBBSSDigJQgY2hlY2sgY29ubmVjdGlvbi48L3NwYW4+JywgJ3N5c3RlbScsICdfX2dtX18nKTsKICB9CiAgYnVzeSA9IGZhbHNlOwogIGlmIChzZW5kQnRuKSBzZW5kQnRuLmRpc2FibGVkID0gZmFsc2U7CiAgaWYgKGNtZElucCkgeyBjbWRJbnAuZGlzYWJsZWQgPSBmYWxzZTsgY21kSW5wLmZvY3VzKCk7IH0KfQoKd2luZG93LmFkZEV2ZW50TGlzdGVuZXIoJ0RPTUNvbnRlbnRMb2FkZWQnLCAoKSA9PiB7CiAgc2hvdygncy1sb2JieScpOwogIGNoZWNrT2xsYW1hU3RhdHVzKCk7CiAgY2hlY2tOZ3Jva1N0YXR1cygpOwogIHJvdGF0ZUJhbm5lZFBocmFzZXMoKTsKICBzZXRJbnRlcnZhbChyb3RhdGVCYW5uZWRQaHJhc2VzLCA2MDAwMCk7CiAgc2V0SW50ZXJ2YWwodGlja0VmZmVjdHMsIDEwMDApOwogIGNvbnN0IHBuaSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdwbGF5ZXItbmFtZS1pbnAnKTsKICBpZiAocG5pKSBwbmkuYWRkRXZlbnRMaXN0ZW5lcigna2V5ZG93bicsIGUgPT4geyBpZihlLmtleT09PSdFbnRlcicpIGdvSG9tZSgpOyB9KTsKICBjb25zdCBjbWQgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgnY21kJyk7CiAgaWYgKGNtZCkgY21kLmFkZEV2ZW50TGlzdGVuZXIoJ2tleWRvd24nLCBlID0+IHsgaWYoZS5rZXk9PT0nRW50ZXInICYmICFlLnNoaWZ0S2V5KSB7IGUucHJldmVudERlZmF1bHQoKTsgc2VuZCgpOyB9IH0pOwogIGRvY3VtZW50LmFkZEV2ZW50TGlzdGVuZXIoJ2tleWRvd24nLCBlID0+IHsKICAgIGlmIChlLmtleSA9PT0gJ0VzY2FwZScpIHsKICAgICAgY29uc3QgbSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdtZW1vcml6ZS1tb2RhbCcpIHx8IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKCdsdi1tb2RhbCcpOwogICAgICBpZiAobSkgbS5yZW1vdmUoKTsKICAgIH0KICB9KTsKfSk7CgovLyBWNCBzdGF0ZSBpbml0IGlzIGNhbGxlZCBkaXJlY3RseSBmcm9tIGJlZ2luQWR2ZW50dXJlIGFuZCBsYXVuY2hHYW1lCg=="

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
        _sys.exit(1)
