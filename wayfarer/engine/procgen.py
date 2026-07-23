"""Procedurally generated rooms -- "the Depths", reached through the Crypt's
east exit. Each room is addressed by (seed, level, gx, gy): level is which
dungeon floor you're on (1 = the floor reached directly from the Crypt),
gx/gy are grid coordinates on that floor's own infinite plane. A room is
regenerated deterministically from those four values -- no room geometry is
ever written to the save file, only the run's seed and which enemies/items
in already-visited rooms have been consumed (via the room_flags table) plus
a per-room "epoch" counter (via room_meta) that lets cleared rooms
repopulate over time without changing their shape.

Difficulty scales two ways: `_depth()` (Manhattan distance from a floor's
own (0, 0) entrance) as before, and now also by `level` itself -- both feed
into `_tier()`, and `scale_stats_for_level()` additionally boosts an
individual enemy's raw stats the deeper the floor. This keeps the game from
going one-directional (player gets stronger, world stays the same).

Layout and exits (including the two guaranteed stairs -- see below) are a
pure function of (seed, level, gx, gy) alone, never the epoch, so a room's
shape never changes across a respawn cycle -- only which enemies/items are
in it. Neighboring rooms independently agree on doorways via the same
canonical edge-key hash as before, now keyed additionally by level.

Every floor's (0, 0) room is special: it guarantees a "stairs down" tile to
`level + 1` at a fixed interior cell, and (for level > 1) a "stairs up"
tile back to `level - 1` at another fixed cell -- level 1's (0, 0) instead
keeps the original hardcoded link back to the Crypt. These are just regular
exits.py-style dicts with an extra "kind" field; the existing generic
exit-at-a-coordinate handling in Room/Player needs no changes to support
them.

Session 10: rooms are no longer a single open rectangle. Each 40x32 cell is
now divided into a small grid of "core" rooms carved within a fixed
GRID_COLS x GRID_ROWS layout, connected by corridors along a randomized
spanning tree (every core room, every open edge door, and the stairs cell
are always reachable using only these tree corridors -- no lock ever sits
on one). A minority of rooms additionally grow one optional *vault*: a
small side-room attached to a core room via exactly one locked door or
switch-gated gate. Because a vault's only connection point IS the lock,
locking/gating it can never disconnect anything else -- it only ever gates
itself. See `generate_room()` for where this is assembled and
PROGRESS.MD's session 10 entry for why this design was chosen over gating
one of the spanning tree's redundant ("loop") edges instead (a loop edge
only ever reconnects two rooms that are already reachable through the
tree, which makes locking it pointless -- nothing is actually gated).

Fog of war (main.py's Game.revealed_regions) is keyed off the `regions`
list this module returns -- one entry per core room, vault, and corridor
segment. Region ids are deliberately *not* epoch-suffixed (unlike
enemy/item ids): which parts of a room the player has physically seen is
permanent knowledge, not "loot" that should reset when the room
repopulates. Locked doors/gates/switches/chests are the same way -- once
solved, a vault stays solved forever, so their ids aren't epoch-suffixed
either (contrast with the key that opens a locked door, which *is* a
normal item and rides the usual epoch-suffixed item-id convention -- if a
key is never picked up, a later epoch's item roll doesn't care, but the
lock it opens was already generated once and stays exactly as solvable).
"""

import random

from engine.equipment import roll_enchant

# Session 9: 10x8 -> 40x32 (exactly 4x each dimension) to match the switch
# to native-16px art (main.py's TILE_SIZE 64->16) at an unchanged pixel
# footprint -- see PROGRESS.MD. Every (near, far) door/landing pair below
# is still derived from WIDTH/HEIGHT/MID_X/MID_Y, so this is the only
# place room size lives; nothing else in this file hardcodes the old 10x8.
WIDTH, HEIGHT = 40, 32
MID_X, MID_Y = 20, 16
EDGE_OPEN_CHANCE = 0.55

# Fixed interior cells in every floor's (0, 0) room -- never randomized,
# always excluded from enemy/item placement so nothing can spawn on top.
STAIRS_DOWN_CELL = (4, 2)
STAIRS_UP_CELL = (35, 2)
LEVEL_ENTRY_LANDING = (MID_X, MID_Y)

LEVEL_HP_STEP = 0.2  # +20% enemy hp/xp per dungeon level beyond 1
LEVEL_DEFENSE_STEP = 3  # +1 defense every 3 levels

# Session 10: fixed grid of "core" rooms carved into every generated cell --
# see the module docstring. 2x2 (rather than something denser) keeps each
# cell roomy enough that a core room and an optional vault reliably fit
# side by side with no packing edge cases.
GRID_COLS, GRID_ROWS = 2, 2
ROOM_MARGIN = 3  # min gap kept between a carved room and its grid cell's edge
MIN_ROOM_W, MIN_ROOM_H = 7, 7
MAX_ROOM_W, MAX_ROOM_H = 14, 12
VAULT_SIZE = 5
VAULT_CHANCE_BY_TIER = [0.3, 0.5, 0.7]

# (type, weight) tables keyed by depth tier -- see _tier()/_weighted_choice().
ENEMY_WEIGHTS_BY_TIER = [
    [("slime", 3), ("skeleton", 1), ("viper", 2)],
    # Session 24: the Wraith is mid/deep-tier only, never shallow -- CotW's
    # own undead-drain monsters (Wraiths, Wights) show up well past the
    # earliest levels, and this engine has no cure for the drain except
    # gold, so a brand-new character shouldn't be able to stumble into one.
    # Session 35: Dark Wraith joins at mid-tier too, rarer than the base
    # Wraith -- CotW rates it one difficulty step up (5/10 vs. Wraith/Pale
    # Wraith's 4/10, confirmed via research, see PROGRESS.MD session 35), so
    # it's a real but uncommon step-up encounter here rather than deep-only.
    # Session 37: Barrow Wight joins at mid-tier too, alongside the Wraith --
    # CotW's own Wight family (confirmed via research, see PROGRESS.MD
    # session 37: Barrow/Tunnel/Castle, weakest to strongest) is a second,
    # unrelated undead-drain family, not a Wraith recolor -- it drains
    # STR/DEX/CON (adapted here as an attack drain, see
    # engine/entity.py's Player.attack_drain) rather than intelligence/mana,
    # and doesn't phase through walls the way Wraiths/ghosts do.
    [("slime", 1), ("skeleton", 3), ("cultist", 1), ("viper", 1), ("wraith", 2), ("dark_wraith", 1), ("barrow_wight", 2), ("tunnel_wight", 1)],
    # Session 22: Young Red Dragon is deep-tier only and deliberately rare
    # (weight 1 against the other three's combined 6) -- a mini-boss-flavor
    # threat, not a regular encounter, matching how cultist was already the
    # strongest thing in this tier before it arrived.
    # Session 31: Young White Dragon (cold) joins it at the same rarity --
    # CotW's own White Dragon line is the direct cold-elemental mirror of
    # the Red Dragon line, so it gets the identical weight-1 mini-boss
    # treatment rather than being tuned as more/less common than its
    # fire-breathing counterpart.
    # Session 32: Young Blue Dragon (lightning) joins at the same weight --
    # CotW's Blue Dragons breathe lightning, the third leg of the
    # fire/cold/lightning elemental set this engine now covers; no reason to
    # make it rarer or commoner than its two mirror dragons.
    # Session 33: Young Green Dragon (poison gas) joins at the same weight,
    # completing CotW's actual four-color dragon roster (Red/fire, White/
    # cold, Blue/lightning, Green/poison gas -- confirmed via research, see
    # PROGRESS.MD session 33). It's a mini-boss like its three siblings, not
    # a new elemental damage_type -- see data/enemies.json for why.
    # Session 35: Dark Wraith and Abyss Wraith join here, deep-tier only --
    # CotW's actual wraith family (confirmed via Wikibooks research, see
    # PROGRESS.MD session 35) is Wraith, Pale Wraith, Dark Wraith, and Abyss
    # Wraith, all draining intelligence/mana irreversibly. Dark Wraith gets
    # the same weight-1 step-up rarity it has at mid-tier; Abyss Wraith is
    # the strongest of the three built here and only ever appears this deep,
    # weighted the same as the mini-boss dragons rather than more common.
    # Session 37: the full Wight family shows up here -- Barrow Wight
    # continues at the same weight as mid-tier, Tunnel Wight gets more
    # common, and Castle Wight (the strongest of the three, see
    # data/enemies.json) is deep-tier only, weighted the same mini-boss-rare
    # 1 as Abyss Wraith and the four dragon lines rather than a regular
    # encounter.
    [("slime", 1), ("skeleton", 2), ("cultist", 3), ("young_red_dragon", 1), ("young_white_dragon", 1), ("young_blue_dragon", 1), ("young_green_dragon", 1), ("wraith", 2), ("dark_wraith", 1), ("abyss_wraith", 1), ("barrow_wight", 1), ("tunnel_wight", 2), ("castle_wight", 1)],
]
ITEM_WEIGHTS_BY_TIER = [
    [("potion", 5), ("whetstone", 1), ("gold", 3), ("mana_potion", 2)],
    [("potion", 4), ("whetstone", 2), ("shield", 2), ("gold", 3), ("mana_potion", 3), ("equipment", 1), ("spellbook", 1)],
    [("potion", 3), ("whetstone", 3), ("shield", 3), ("gold", 3), ("mana_potion", 3), ("equipment", 2), ("spellbook", 1)],
]
# Session 17: chests (vault loot) reuse ITEM_WEIGHTS_BY_TIER directly,
# including "equipment" -- a chest can now hold a per-instance gear drop the
# same way floor loot can (see the "equipment" branch in the vault section
# of generate_room()). Tier 0 still never rolls equipment since
# ITEM_WEIGHTS_BY_TIER's own tier-0 entry has no "equipment" weight at all,
# same as floor loot.
# Session 16: dungeon-found equipment -- rarer than consumables (see the
# "equipment" weight above, tier 0 never rolls it at all) and the only
# source of cursed/enchanted gear; shop purchases are always a plain +0
# instance (see engine/equipment.py). Slot -> [basic, fine, masterwork]
# base_type keys mirror data/equipment.json's own tier field per slot --
# kept as a small parallel table rather than reading the json file from
# here, the same "procgen trusts a key string exists, main.py resolves it
# against the real defs" split every other loot family in this file
# already uses.
EQUIPMENT_BASE_TYPES_BY_SLOT = {
    "weapon": ["shortsword", "longsword", "greatsword"],
    "shield": ["buckler", "kite_shield", "tower_shield"],
    "helmet": ["leather_cap", "iron_helm", "great_helm"],
    "armor": ["leather_armor", "chainmail", "plate_armor"],
    "boots": ["worn_boots", "leather_boots", "steel_greaves"],
    # Session 18: ring/amulet slots -- same "equipment" loot family, zero
    # new procgen mechanism, just three more slot -> tier-ladder entries.
    "ring1": ["ring_might_basic", "ring_might_fine", "ring_might_masterwork"],
    "ring2": ["ring_warding_basic", "ring_warding_fine", "ring_warding_masterwork"],
    "amulet": ["amulet_resist_basic", "amulet_resist_fine", "amulet_resist_masterwork"],
}
EQUIPMENT_SLOTS = list(EQUIPMENT_BASE_TYPES_BY_SLOT.keys())
# Session 39: dungeon-found spellbooks (Castle of the Winds' other
# spellbook source alongside the Scholar's paid catalog -- see
# engine/spells.py's "future work" note this closes out). Same "procgen
# trusts a key string exists, main.py resolves it against the real defs"
# split as EQUIPMENT_BASE_TYPES_BY_SLOT above: three bands mirroring
# data/spells.json's own unlock_level order (low/mid/high thirds, 7+8+7 of
# the 22 spells) rather than reading the json file from here. Deeper tiers
# skew toward the later band via the same magnitude roll gear tiers use,
# so a found spellbook's power tracks depth the same way gear enchant does
# -- but unlike gear (deterministic per-room, no player state), the band
# only bounds *which* spell can roll; whether the player already knows it
# is a live check main.py's pickup handler makes, not this pure generator.
SPELL_IDS_BY_BAND = [
    ["spark", "minor_heal", "stone_skin", "firebolt", "blink", "detect_monsters", "detect_treasure"],
    ["neutralize_poison", "word_of_recall", "identify", "remove_curse", "detect_traps", "levitation", "cold_bolt", "lightning_bolt"],
    ["resist_fire", "resist_cold", "resist_lightning", "heal_medium", "heal_major", "light", "clairvoyance"],
]
_MAGNITUDE_TO_GEAR_TIER = {"minor": 0, "normal": 1, "greater": 2}
# Once a family (potion/whetstone/shield) is picked, roll its magnitude --
# "normal" keeps the item's plain, pre-existing type key (e.g. "potion");
# deeper tiers skew toward "greater" so loot quality tracks dungeon depth
# same as enemy difficulty does.
MAGNITUDE_WEIGHTS_BY_TIER = [
    [("minor", 5), ("normal", 3), ("greater", 0)],
    [("minor", 2), ("normal", 5), ("greater", 2)],
    [("minor", 1), ("normal", 3), ("greater", 4)],
]

# Session 28: hidden dungeon traps (Castle of the Winds' dart/pit/poison-gas
# traps, see data/traps.json). One roll per core room, structural (rolled off
# layout_rng, not pop_rng -- like locks/chests, a trap's placement and type
# must never change across a room's epoch-scoped enemy/item respawn cycle;
# only whether it's already been sprung is per-save state, tracked in
# main.py via room_flags same as an opened chest). Deeper tiers place traps
# more often and skew toward the nastier pit/gas types.
TRAP_CHANCE_BY_TIER = [0.12, 0.18, 0.24]
TRAP_WEIGHTS_BY_TIER = [
    [("dart_trap", 3), ("pit_trap", 1)],
    [("dart_trap", 2), ("pit_trap", 2), ("poison_gas_trap", 2)],
    [("dart_trap", 1), ("pit_trap", 2), ("poison_gas_trap", 3)],
]

DIRECTIONS = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}


def _depth(gx, gy):
    return abs(gx) + abs(gy)


def _tier(level, depth):
    base = 0 if depth <= 1 else 1 if depth <= 3 else 2
    return min(2, base + (level - 1) // 2)


def _weighted_choice(rng, weighted):
    total = sum(w for _, w in weighted)
    roll = rng.random() * total
    upto = 0.0
    for value, weight in weighted:
        upto += weight
        if roll <= upto:
            return value
    return weighted[-1][0]


def scale_stats_for_level(stats, level):
    """Boost a base enemy-def stats dict for how deep it's spawning.
    level 1 is a no-op (identity) so floor 1 matches pre-existing balance."""
    mult = 1 + LEVEL_HP_STEP * (level - 1)
    scaled = dict(stats)
    scaled["hp"] = max(1, round(stats["hp"] * mult))
    scaled["attack"] = stats["attack"] + (level - 1)
    scaled["defense"] = stats["defense"] + (level - 1) // LEVEL_DEFENSE_STEP
    scaled["xp_reward"] = max(1, round(stats["xp_reward"] * mult))
    scaled["gold_reward"] = [
        max(0, round(v * mult)) for v in stats.get("gold_reward", [0, 0])
    ]
    # Session 21: a Viper's bite should sting harder deeper in, same as its
    # direct attack already does above -- a no-op for every enemy type with
    # no poison_damage key (dict(stats) above already carried a bare 0/absent
    # value through unscaled otherwise).
    if stats.get("poison_damage"):
        scaled["poison_damage"] = max(1, round(stats["poison_damage"] * mult))
    # Session 24: a Wraith's drain should also bite harder deeper in, same
    # depth-scaling reasoning as poison_damage above -- a no-op for every
    # enemy type with no drain_amount key.
    if stats.get("drain_amount"):
        scaled["drain_amount"] = max(1, round(stats["drain_amount"] * mult))
    return scaled


def _edge_open(seed, level, gx, gy, direction):
    if (gx, gy) == (0, 0) and direction == "W" and level == 1:
        return True  # guaranteed link back to the Crypt
    ddx, ddy = DIRECTIONS[direction]
    neighbor = (gx + ddx, gy + ddy)
    edge_key = tuple(sorted([(gx, gy), neighbor]))
    rng = random.Random(f"{seed}:edge:{level}:{edge_key}")
    return rng.random() < EDGE_OPEN_CHANCE


def room_doors(seed, level, gx, gy):
    """Which cardinal directions have an open door out of (gx, gy) -- a
    cheap (four hash-seeded RNG rolls, no layout array built) read used by
    the automap (main.py's Game._draw_dungeon_map) to draw room-to-room
    connections without regenerating full room layouts just to look at
    them."""
    return {d: _edge_open(seed, level, gx, gy, d) for d in DIRECTIONS}


def _exit_point(direction, side):
    """side='near': the door cell on this room's own border.
    side='far': the landing cell one step inside the neighboring room."""
    if direction == "N":
        return (MID_X, 0) if side == "near" else (MID_X, HEIGHT - 2)
    if direction == "S":
        return (MID_X, HEIGHT - 1) if side == "near" else (MID_X, 1)
    if direction == "E":
        return (WIDTH - 1, MID_Y) if side == "near" else (1, MID_Y)
    if direction == "W":
        return (0, MID_Y) if side == "near" else (WIDTH - 2, MID_Y)
    raise ValueError(direction)


# -- sub-room / corridor structure (session 10) -----------------------------

def _grid_cells():
    """(col, row) -> (x, y, w, h) bounds of each grid cell within the
    interior [1, WIDTH-2] x [1, HEIGHT-2]. The cells themselves are never
    drawn -- they just keep carved core rooms spatially separated so
    corridors between them read as corridors, not one merged room."""
    interior_w, interior_h = WIDTH - 2, HEIGHT - 2
    cell_w, cell_h = interior_w // GRID_COLS, interior_h // GRID_ROWS
    cells = {}
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            x0 = 1 + col * cell_w
            y0 = 1 + row * cell_h
            w = cell_w if col < GRID_COLS - 1 else interior_w - col * cell_w
            h = cell_h if row < GRID_ROWS - 1 else interior_h - row * cell_h
            cells[(col, row)] = (x0, y0, w, h)
    return cells


def _carve_room_in_cell(rng, bounds):
    x0, y0, w, h = bounds
    max_w = min(MAX_ROOM_W, w - ROOM_MARGIN * 2)
    max_h = min(MAX_ROOM_H, h - ROOM_MARGIN * 2)
    rw = rng.randint(MIN_ROOM_W, max(MIN_ROOM_W, max_w))
    rh = rng.randint(MIN_ROOM_H, max(MIN_ROOM_H, max_h))
    rx = x0 + rng.randint(ROOM_MARGIN, max(ROOM_MARGIN, w - rw - ROOM_MARGIN))
    ry = y0 + rng.randint(ROOM_MARGIN, max(ROOM_MARGIN, h - rh - ROOM_MARGIN))
    return (rx, ry, rw, rh)


def _rect_center(rect):
    x, y, w, h = rect
    return (x + w // 2, y + h // 2)


def _rect_contains(rect, point):
    x, y, w, h = rect
    px, py = point
    return x <= px < x + w and y <= py < y + h


def _carve_rect(layout, rect):
    x, y, w, h = rect
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            layout[yy][xx] = "."


def _carve_corridor(layout, p1, p2):
    """L-shaped 1-wide corridor between two points -- horizontal leg first,
    then vertical. Returns every (x, y) cell carved, for region tracking."""
    x1, y1 = p1
    x2, y2 = p2
    cells = []
    for x in range(min(x1, x2), max(x1, x2) + 1):
        layout[y1][x] = "."
        cells.append((x, y1))
    for y in range(min(y1, y2), max(y1, y2) + 1):
        layout[y][x2] = "."
        cells.append((x2, y))
    return cells


def _spanning_tree(rng, nodes, adjacency):
    """Randomized spanning tree over `adjacency` (candidate (a, b) edges)
    via shuffle + union-find. Returns (tree_edges, extra_edges) -- every
    node is reachable from every other using tree_edges alone; extra_edges
    are redundant (both endpoints already connected), safe to also carve as
    plain shortcuts but never meaningful to lock (see module docstring)."""
    parent = {n: n for n in nodes}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    edges = list(adjacency)
    rng.shuffle(edges)
    tree, extra = [], []
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
            tree.append((a, b))
        else:
            extra.append((a, b))
    return tree, extra


def _place_vault(rng, host_rect, cell_bounds):
    """Try to attach a small vault room to one side of host_rect, staying
    within cell_bounds. Returns (vault_rect, connector_point) or
    (None, None) if there's no room for one -- callers just skip the vault
    in that case, never forced."""
    hx, hy, hw, hh = host_rect
    cx0, cy0, cw, ch = cell_bounds
    sides = ["E", "W", "S", "N"]
    rng.shuffle(sides)
    for side in sides:
        if side == "E":
            vx, vy = hx + hw + 1, hy + hh // 2 - VAULT_SIZE // 2
            if vx + VAULT_SIZE <= cx0 + cw and cy0 <= vy and vy + VAULT_SIZE <= cy0 + ch:
                return (vx, vy, VAULT_SIZE, VAULT_SIZE), (hx + hw, hy + hh // 2)
        elif side == "W":
            vx, vy = hx - 1 - VAULT_SIZE, hy + hh // 2 - VAULT_SIZE // 2
            if vx >= cx0 and cy0 <= vy and vy + VAULT_SIZE <= cy0 + ch:
                return (vx, vy, VAULT_SIZE, VAULT_SIZE), (hx - 1, hy + hh // 2)
        elif side == "S":
            vx, vy = hx + hw // 2 - VAULT_SIZE // 2, hy + hh + 1
            if vy + VAULT_SIZE <= cy0 + ch and cx0 <= vx and vx + VAULT_SIZE <= cx0 + cw:
                return (vx, vy, VAULT_SIZE, VAULT_SIZE), (hx + hw // 2, hy + hh)
        else:  # N
            vx, vy = hx + hw // 2 - VAULT_SIZE // 2, hy - 1 - VAULT_SIZE
            if vy >= cy0 and cx0 <= vx and vx + VAULT_SIZE <= cx0 + cw:
                return (vx, vy, VAULT_SIZE, VAULT_SIZE), (hx + hw // 2, hy - 1)
    return None, None


def _reachable_floor(layout, start):
    """BFS over every '.' tile connected to `start`. Used by
    generate_biome_room to verify a guaranteed vault's isolating wall ring
    (see below) didn't accidentally sever some unrelated corridor."""
    h, w = len(layout), len(layout[0])
    seen = {start}
    stack = [start]
    while stack:
        x, y = stack.pop()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and layout[ny][nx] == "." and (nx, ny) not in seen:
                seen.add((nx, ny))
                stack.append((nx, ny))
    return seen


def _random_free_point(rng, rect, occupied, tries=12):
    x, y, w, h = rect
    for _ in range(tries):
        pt = (rng.randint(x, x + w - 1), rng.randint(y, y + h - 1))
        if pt not in occupied:
            return pt
    return None


def generate_room(seed, level, gx, gy, epoch=0):
    # Structure (rooms/corridors/doors/gates/locks/vault placement) is a
    # pure function of (seed, level, gx, gy) alone via layout_rng -- never
    # epoch. Only which enemies/items spawn, via pop_rng, is epoch-scoped,
    # so a respawned room keeps its shape (and stays solved if its vault
    # was already solved) but gets fresh monsters/loot.
    layout_rng = random.Random(f"{seed}:layout:{level}:{gx}:{gy}")
    pop_rng = random.Random(f"{seed}:pop:{level}:{gx}:{gy}:{epoch}")
    tier = _tier(level, _depth(gx, gy))

    layout = [["#"] * WIDTH for _ in range(HEIGHT)]
    regions = []

    # -- core rooms, one per grid cell -----------------------------------
    cell_bounds = _grid_cells()
    nodes = list(cell_bounds.keys())
    core_rooms = {node: _carve_room_in_cell(layout_rng, cell_bounds[node]) for node in nodes}
    for rect in core_rooms.values():
        _carve_rect(layout, rect)
    for i, node in enumerate(nodes):
        x, y, w, h = core_rooms[node]
        regions.append({"id": f"room{i}", "x": x, "y": y, "w": w, "h": h})

    adjacency = []
    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            if col + 1 < GRID_COLS:
                adjacency.append(((col, row), (col + 1, row)))
            if row + 1 < GRID_ROWS:
                adjacency.append(((col, row), (col, row + 1)))
    tree_edges, loop_edges = _spanning_tree(layout_rng, nodes, adjacency)

    corridor_i = 0

    def _add_corridor(p1, p2):
        nonlocal corridor_i
        cells = _carve_corridor(layout, p1, p2)
        regions.append({"id": f"corridor{corridor_i}", "cells": cells})
        corridor_i += 1

    # Tree edges are the guaranteed-reachable backbone; loop edges are
    # extra plain shortcuts for variety -- both always walkable, never
    # gated (see module docstring for why a lock never goes on either).
    for a, b in tree_edges + loop_edges:
        _add_corridor(_rect_center(core_rooms[a]), _rect_center(core_rooms[b]))

    core_rects = list(core_rooms.values())

    def _nearest_core_room(point):
        px, py = point
        return min(core_rects, key=lambda r: abs(_rect_center(r)[0] - px) + abs(_rect_center(r)[1] - py))

    # -- edges to neighboring grid cells (contract unchanged from before) --
    exits = []
    for direction, (ddx, ddy) in DIRECTIONS.items():
        if not _edge_open(seed, level, gx, gy, direction):
            continue
        near_x, near_y = _exit_point(direction, "near")
        # One step in from the door, along the direction you'd walk entering
        # this room -- this is the exact cell a neighboring room's "far"
        # landing point (_exit_point(opposite_direction, "far")) resolves to,
        # so it must always be floor and connected to the interior. Carving
        # a corridor from the door tile itself isn't enough to guarantee
        # that: _carve_corridor's first (horizontal) leg runs along the
        # door's own row, which only happens to pass through this cell when
        # the door sits on a vertical border (E/W, where the landing cell
        # shares the door's row). For a horizontal border (N/S) the landing
        # cell is one row *off* the door, and the corridor's second
        # (vertical) leg travels down the nearest core room's own column,
        # not the door's -- so the landing cell was only ever carved by
        # coincidence, when a core room happened to be centered exactly on
        # it. That gap is what let every N/S transition in the Depths drop
        # the player onto a wall tile with no way out except back through
        # the same broken door on the other side.
        in_x, in_y = near_x - ddx, near_y - ddy
        layout[near_y][near_x] = "."
        layout[in_y][in_x] = "."
        _add_corridor((in_x, in_y), _rect_center(_nearest_core_room((in_x, in_y))))

        if (gx, gy) == (0, 0) and direction == "W" and level == 1:
            # Crypt is a hand-authored room (its own WIDTH/HEIGHT, see
            # data/rooms/crypt.json), not this module's -- landing spot is
            # one step in from its east door, hardcoded there the same way.
            # Session 10: Crypt resized to 30x20, east door at (29, 9).
            target_room, target_x, target_y = "crypt", 28, 9
        else:
            ngx, ngy = gx + ddx, gy + ddy
            target_room = f"proc:{seed}:{level}:{ngx}:{ngy}"
            target_x, target_y = _exit_point(direction, "far")

        exits.append({
            "id": f"to_{direction}",
            "x": near_x, "y": near_y,
            "target_room": target_room,
            "target_x": target_x, "target_y": target_y,
        })

    if (gx, gy) == (0, 0):
        down_x, down_y = STAIRS_DOWN_CELL
        layout[down_y][down_x] = "."
        _add_corridor((down_x, down_y), _rect_center(_nearest_core_room((down_x, down_y))))
        exits.append({
            "id": "stairs_down",
            "kind": "stairs_down",
            "x": down_x, "y": down_y,
            "target_room": f"proc:{seed}:{level + 1}:0:0",
            "target_x": LEVEL_ENTRY_LANDING[0], "target_y": LEVEL_ENTRY_LANDING[1],
        })
        if level > 1:
            up_x, up_y = STAIRS_UP_CELL
            layout[up_y][up_x] = "."
            _add_corridor((up_x, up_y), _rect_center(_nearest_core_room((up_x, up_y))))
            exits.append({
                "id": "stairs_up",
                "kind": "stairs_up",
                "x": up_x, "y": up_y,
                "target_room": f"proc:{seed}:{level - 1}:0:0",
                "target_x": LEVEL_ENTRY_LANDING[0], "target_y": LEVEL_ENTRY_LANDING[1],
            })
        landing = LEVEL_ENTRY_LANDING
        layout[landing[1]][landing[0]] = "."
        _add_corridor(landing, _rect_center(_nearest_core_room(landing)))

    # -- enemies/items, rolled per core room (session 10: replaces the old
    # flat scatter across the whole interior) -----------------------------
    max_enemies_per_room = 3 if tier == 2 else 2
    item_chance = 0.6 if tier == 0 else 0.75
    enemies, items, equipment_drops, spellbook_drops, traps = [], [], [], [], []
    e_i = i_i = eq_i = sb_i = tr_i = 0
    room_occupied = {i: set() for i in range(len(core_rects))}
    for i, rect in enumerate(core_rects):
        occupied = room_occupied[i]
        # Trap placement is structural (layout_rng), rolled before this
        # room's enemies/items (pop_rng) so their placement avoids it too --
        # see the module docstring and TRAP_CHANCE_BY_TIER above.
        if layout_rng.random() < TRAP_CHANCE_BY_TIER[tier]:
            pt = _random_free_point(layout_rng, rect, occupied)
            if pt is not None:
                occupied.add(pt)
                traps.append({
                    "id": f"proc_{seed}_{level}_{gx}_{gy}_trap{tr_i}",
                    "type": _weighted_choice(layout_rng, TRAP_WEIGHTS_BY_TIER[tier]),
                    "x": pt[0], "y": pt[1],
                })
                tr_i += 1
        for _ in range(pop_rng.randint(0, max_enemies_per_room)):
            pt = _random_free_point(pop_rng, rect, occupied)
            if pt is None:
                break
            occupied.add(pt)
            enemies.append({
                "id": f"proc_{seed}_{level}_{gx}_{gy}_e{e_i}_ep{epoch}",
                "type": _weighted_choice(pop_rng, ENEMY_WEIGHTS_BY_TIER[tier]),
                "x": pt[0], "y": pt[1],
                "level": level,
            })
            e_i += 1
        if pop_rng.random() < item_chance:
            pt = _random_free_point(pop_rng, rect, occupied)
            if pt is not None:
                occupied.add(pt)
                family = _weighted_choice(pop_rng, ITEM_WEIGHTS_BY_TIER[tier])
                if family == "equipment":
                    slot = pop_rng.choice(EQUIPMENT_SLOTS)
                    magnitude = _weighted_choice(pop_rng, MAGNITUDE_WEIGHTS_BY_TIER[tier])
                    gear_tier = _MAGNITUDE_TO_GEAR_TIER[magnitude]
                    base_type = EQUIPMENT_BASE_TYPES_BY_SLOT[slot][gear_tier]
                    equipment_drops.append({
                        "id": f"proc_{seed}_{level}_{gx}_{gy}_eq{eq_i}_ep{epoch}",
                        "base_type": base_type,
                        "enchant": roll_enchant(pop_rng),
                        "x": pt[0], "y": pt[1],
                    })
                    eq_i += 1
                elif family == "spellbook":
                    magnitude = _weighted_choice(pop_rng, MAGNITUDE_WEIGHTS_BY_TIER[tier])
                    band = _MAGNITUDE_TO_GEAR_TIER[magnitude]
                    spellbook_drops.append({
                        "id": f"proc_{seed}_{level}_{gx}_{gy}_sb{sb_i}_ep{epoch}",
                        "spell_id": pop_rng.choice(SPELL_IDS_BY_BAND[band]),
                        "x": pt[0], "y": pt[1],
                    })
                    sb_i += 1
                else:
                    magnitude = _weighted_choice(pop_rng, MAGNITUDE_WEIGHTS_BY_TIER[tier])
                    item_type = family if magnitude == "normal" else f"{family}_{magnitude}"
                    items.append({
                        "id": f"proc_{seed}_{level}_{gx}_{gy}_i{i_i}_ep{epoch}",
                        "type": item_type,
                        "x": pt[0], "y": pt[1],
                    })
                    i_i += 1

    # -- optional vault: the only place a lock/gate can appear ------------
    # Structural (layout_rng) and permanent -- see module docstring on why
    # vault/lock/chest ids below deliberately have no epoch suffix, unlike
    # everything above this point.
    locked_doors, gates, switches, chests = [], [], [], []
    if layout_rng.random() < VAULT_CHANCE_BY_TIER[tier]:
        host_order = list(range(len(nodes)))
        layout_rng.shuffle(host_order)
        for host_i in host_order:
            host_node = nodes[host_i]
            vault_rect, connector = _place_vault(layout_rng, core_rooms[host_node], cell_bounds[host_node])
            if vault_rect is None:
                continue
            _carve_rect(layout, vault_rect)
            cx, cy = connector
            layout[cy][cx] = "."
            vx, vy, vw, vh = vault_rect
            regions.append({"id": "vault0", "x": vx, "y": vy, "w": vw, "h": vh})

            key_room_i = layout_rng.randrange(len(core_rects))
            key_pt = _random_free_point(pop_rng, core_rects[key_room_i], room_occupied[key_room_i])

            if layout_rng.random() < 0.5:
                door_id = f"proc_{seed}_{level}_{gx}_{gy}_door0"
                locked_doors.append({"id": door_id, "x": cx, "y": cy})
                if key_pt is not None:
                    room_occupied[key_room_i].add(key_pt)
                    items.append({
                        "id": f"proc_{seed}_{level}_{gx}_{gy}_key0_ep{epoch}",
                        "type": "key",
                        "x": key_pt[0], "y": key_pt[1],
                    })
            else:
                gate_id = f"proc_{seed}_{level}_{gx}_{gy}_gate0"
                switch_id = f"proc_{seed}_{level}_{gx}_{gy}_switch0"
                gates.append({"id": gate_id, "x": cx, "y": cy, "switch_id": switch_id})
                if key_pt is not None:
                    room_occupied[key_room_i].add(key_pt)
                    switches.append({"id": switch_id, "x": key_pt[0], "y": key_pt[1], "gate_id": gate_id})
                else:
                    # No free spot to place the switch -- don't ship a gate
                    # nobody can ever open.
                    gates.pop()

            chest_x, chest_y = _rect_center(vault_rect)
            family = _weighted_choice(layout_rng, ITEM_WEIGHTS_BY_TIER[tier])
            magnitude = _weighted_choice(layout_rng, MAGNITUDE_WEIGHTS_BY_TIER[2])
            chest = {
                "id": f"proc_{seed}_{level}_{gx}_{gy}_chest0",
                "x": chest_x, "y": chest_y,
            }
            if family == "equipment":
                # Same "equipment" branch as floor loot above, but rolled
                # off layout_rng (not pop_rng) -- a chest's contents are
                # structural/permanent, same as its lock, and must never
                # change across a room's epoch-scoped respawn cycle.
                gear_slot = layout_rng.choice(EQUIPMENT_SLOTS)
                gear_tier = _MAGNITUDE_TO_GEAR_TIER[magnitude]
                chest["equipment"] = {
                    "base_type": EQUIPMENT_BASE_TYPES_BY_SLOT[gear_slot][gear_tier],
                    "enchant": roll_enchant(layout_rng),
                }
            elif family == "spellbook":
                # Same "spellbook" branch as floor loot above, but rolled
                # off layout_rng (not pop_rng) -- a chest's contents are
                # structural/permanent, same reasoning as the equipment
                # branch above.
                band = _MAGNITUDE_TO_GEAR_TIER[magnitude]
                chest["spellbook"] = {"spell_id": layout_rng.choice(SPELL_IDS_BY_BAND[band])}
            else:
                chest["item_type"] = family if magnitude == "normal" else f"{family}_{magnitude}"
            chests.append(chest)
            break  # one vault attempt is enough once it succeeds

    return {
        "name": f"The Depths — Level {level} ({gx}, {gy})",
        "layout": ["".join(row) for row in layout],
        "exits": exits,
        "enemies": enemies,
        "items": items,
        "equipment_drops": equipment_drops,
        "spellbook_drops": spellbook_drops,
        "regions": regions,
        "locked_doors": locked_doors,
        "gates": gates,
        "switches": switches,
        "chests": chests,
        "traps": traps,
    }


# -- Wayfarer Adventure Mode: finite biome dungeons -------------------------
# See wayfarer/wayfarer_adventure.md for the full design writeup. Unlike the
# Depths above (an unbounded (level, gx, gy) plane, regenerated per room),
# a biome dungeon is exactly ONE room, id'd "biome:<biome_id>:<seed>" --
# finite by construction, no gx/gy neighbors, no stairs, no level scaling,
# no epoch/respawn (main.py's load_room only applies that machinery to
# "proc:"-prefixed ids, so a biome room's population is generated once and
# cached forever by Room.load, same as a hand-authored room). It reuses
# generate_room's core-room/corridor/vault carving helpers wholesale --
# only the top-level assembly differs: a single fixed exit back to town
# instead of the four-directional edge-hash dance, a fixed difficulty tier
# instead of depth/level scaling, and a *guaranteed* vault (not chance-
# gated) whose chest always holds the biome's artifact fragment, guarded by
# its mini-boss standing in the same room. Reachable directly from
# town_hub, no unlock gating yet -- that's a later session (see the design
# doc's phased build order, step 2).
BIOME_ENTRY_LANDING = (MID_X, MID_Y)
BIOME_EXIT_CELL = (0, MID_Y)
# Fixed, curated difficulty (see wayfarer_adventure.md's Open Questions --
# "leans fixed/curated" over scaling with player level): tier 1 is the
# Depths' own mid-difficulty band, reused as-is rather than inventing a
# parallel table.
BIOME_TIER = 1

BIOME_DEFS = {
    # Terrain flavor (per wayfarer_adventure.md's biome table): desert/
    # canyon. Mini-boss and fragment id below are the only two facts
    # generate_biome_room needs -- display name/sprite for the fragment
    # itself lives in data/artifacts.json (main.py resolves it), same
    # "procgen trusts a key string exists" split as
    # EQUIPMENT_BASE_TYPES_BY_SLOT/SPELL_IDS_BY_BAND above.
    # `town_return`: which town_hub tile a "to_town" exit drops the player
    # at -- session 44 hardcoded this to (16, 6), the tile just south of
    # the Scorched Wastes' own door (16, 4). Session 45 (Frostreach)
    # parameterizes it per biome so a second town door doesn't silently
    # reuse the first door's landing spot.
    "scorched_wastes": {
        "name": "Scorched Wastes",
        "boss_type": "young_red_dragon",
        "fragment_id": "ember_fragment",
        "town_return": (16, 6),
    },
    # Session 45 (Wayfarer Adventure Mode, see wayfarer_adventure.md):
    # second biome, ice/tundra terrain flavor, cold-elemental mini-boss --
    # the design doc's Frostreach entry. Terrain art is still the shared
    # dungeon_v2 tileset (art resize/re-skin is explicitly a separate,
    # later pass on this branch), same "art stays as-is" scope session 44
    # already drew for Scorched Wastes.
    "frostreach": {
        "name": "Frostreach",
        "boss_type": "young_white_dragon",
        "fragment_id": "frost_fragment",
        "town_return": (26, 6),
    },
    # Session 46 (Wayfarer Adventure Mode, see wayfarer_adventure.md): third
    # biome, ruins/highlands terrain flavor, lightning-elemental mini-boss --
    # the design doc's Stormfell entry, third link in the fetch/trade chain
    # (Frostreach -> Stormfell). Same "art stays as-is" scope as the first
    # two biomes -- interior is still the shared dungeon_v2 tileset, only
    # the town door gets a new tint (see AssetManager's "storm" variant).
    "stormfell": {
        "name": "Stormfell",
        "boss_type": "young_blue_dragon",
        "fragment_id": "storm_fragment",
        "town_return": (6, 6),
    },
    # Session 47 (Wayfarer Adventure Mode, see wayfarer_adventure.md):
    # fourth and last of the design doc's own biome table -- swamp/jungle
    # terrain flavor, poison-elemental mini-boss (the Young Green Dragon,
    # reusing the Viper's poison-field mechanism per session 33's own
    # research, not a real "poison" damage_type). Closes out the doc's
    # phased-build step 3 ("extend to the full biome count").
    "fenmire": {
        "name": "Fenmire",
        "boss_type": "young_green_dragon",
        "fragment_id": "mire_fragment",
        "town_return": (11, 4),
    },
    # Session 47: the design doc's Final Area -- unlocked once every
    # fragment is held (see data/adventure_quests.json's guide_final, whose
    # `wants` is just the last fragment in the chain; since the fetch/trade
    # mechanic never consumes a traded fragment -- session 45's own
    # deliberate departure from the source games -- holding the last one
    # implies holding all four, so a single-fragment want correctly encodes
    # the doc's "every fragment held" condition without a new want-type
    # schema). No `fragment_id`: `final_reward` instead marks this biome's
    # guaranteed vault chest as the win trigger rather than another
    # fragment drop -- see `_vault_reward()` below and main.py's matching
    # `chest.get("final_reward")` branch. `boss_type` is a new, deliberately
    # tougher-than-any-single-dragon guardian (`elder_dragon`, see
    # data/enemies.json) rather than reusing one of the four biome
    # mini-bosses a second time -- the doc's own "short, dense final
    # dungeon" framing implies a genuine capstone fight, not a rematch.
    "final_area": {
        "name": "The Sundering",
        "boss_type": "elder_dragon",
        "final_reward": True,
        "town_return": (21, 4),
    },
}


def _vault_reward(biome):
    """What the guaranteed vault chest holds -- an artifact fragment for
    every regular biome, or the win trigger for the Final Area. Shared by
    both the normal-placement and no-room-for-a-vault fallback paths below
    so the two chest payloads can never drift out of sync with each other."""
    if biome.get("final_reward"):
        return {"final_reward": True}
    return {"artifact": {"fragment_id": biome["fragment_id"]}}


def generate_biome_room(seed, biome_id):
    biome = BIOME_DEFS[biome_id]
    layout_rng = random.Random(f"{seed}:biome:{biome_id}:layout")
    pop_rng = random.Random(f"{seed}:biome:{biome_id}:pop")
    tier = BIOME_TIER

    layout = [["#"] * WIDTH for _ in range(HEIGHT)]
    regions = []

    cell_bounds = _grid_cells()
    nodes = list(cell_bounds.keys())
    core_rooms = {node: _carve_room_in_cell(layout_rng, cell_bounds[node]) for node in nodes}
    for rect in core_rooms.values():
        _carve_rect(layout, rect)
    for i, node in enumerate(nodes):
        x, y, w, h = core_rooms[node]
        regions.append({"id": f"room{i}", "x": x, "y": y, "w": w, "h": h})

    adjacency = []
    for col in range(GRID_COLS):
        for row in range(GRID_ROWS):
            if col + 1 < GRID_COLS:
                adjacency.append(((col, row), (col + 1, row)))
            if row + 1 < GRID_ROWS:
                adjacency.append(((col, row), (col, row + 1)))
    tree_edges, loop_edges = _spanning_tree(layout_rng, nodes, adjacency)

    corridor_i = 0

    def _add_corridor(p1, p2):
        nonlocal corridor_i
        cells = _carve_corridor(layout, p1, p2)
        regions.append({"id": f"corridor{corridor_i}", "cells": cells})
        corridor_i += 1

    for a, b in tree_edges + loop_edges:
        _add_corridor(_rect_center(core_rooms[a]), _rect_center(core_rooms[b]))

    core_rects = list(core_rooms.values())

    def _nearest_core_room(point):
        px, py = point
        return min(core_rects, key=lambda r: abs(_rect_center(r)[0] - px) + abs(_rect_center(r)[1] - py))

    # -- single fixed exit back to town -- always open, no edge-hash
    # negotiation needed since this room has no neighbors on any plane.
    exit_x, exit_y = BIOME_EXIT_CELL
    layout[exit_y][exit_x] = "."
    in_x, in_y = exit_x + 1, exit_y
    layout[in_y][in_x] = "."
    _add_corridor((in_x, in_y), _rect_center(_nearest_core_room((in_x, in_y))))
    town_return_x, town_return_y = biome.get("town_return", (16, 6))
    exits = [{
        "id": "to_town",
        "x": exit_x, "y": exit_y,
        "target_room": "town_hub",
        "target_x": town_return_x, "target_y": town_return_y,
    }]

    landing = BIOME_ENTRY_LANDING
    layout[landing[1]][landing[0]] = "."
    _add_corridor(landing, _rect_center(_nearest_core_room(landing)))

    # -- regular population (every core room except wherever the vault ends
    # up) -- same weighted tables as the Depths, just fixed-tier rather than
    # depth/level-scaled.
    max_enemies_per_room = 3 if tier == 2 else 2
    item_chance = 0.6 if tier == 0 else 0.75
    enemies, items, equipment_drops, spellbook_drops, traps = [], [], [], [], []
    e_i = i_i = eq_i = sb_i = tr_i = 0
    room_occupied = {i: set() for i in range(len(core_rects))}
    for i, rect in enumerate(core_rects):
        occupied = room_occupied[i]
        if layout_rng.random() < TRAP_CHANCE_BY_TIER[tier]:
            pt = _random_free_point(layout_rng, rect, occupied)
            if pt is not None:
                occupied.add(pt)
                traps.append({
                    "id": f"biome_{biome_id}_{seed}_trap{tr_i}",
                    "type": _weighted_choice(layout_rng, TRAP_WEIGHTS_BY_TIER[tier]),
                    "x": pt[0], "y": pt[1],
                })
                tr_i += 1
        for _ in range(pop_rng.randint(0, max_enemies_per_room)):
            pt = _random_free_point(pop_rng, rect, occupied)
            if pt is None:
                break
            occupied.add(pt)
            enemies.append({
                "id": f"biome_{biome_id}_{seed}_e{e_i}",
                "type": _weighted_choice(pop_rng, ENEMY_WEIGHTS_BY_TIER[tier]),
                "x": pt[0], "y": pt[1],
                "level": 1,
            })
            e_i += 1
        if pop_rng.random() < item_chance:
            pt = _random_free_point(pop_rng, rect, occupied)
            if pt is not None:
                occupied.add(pt)
                family = _weighted_choice(pop_rng, ITEM_WEIGHTS_BY_TIER[tier])
                if family == "equipment":
                    slot = pop_rng.choice(EQUIPMENT_SLOTS)
                    magnitude = _weighted_choice(pop_rng, MAGNITUDE_WEIGHTS_BY_TIER[tier])
                    gear_tier = _MAGNITUDE_TO_GEAR_TIER[magnitude]
                    base_type = EQUIPMENT_BASE_TYPES_BY_SLOT[slot][gear_tier]
                    equipment_drops.append({
                        "id": f"biome_{biome_id}_{seed}_eq{eq_i}",
                        "base_type": base_type,
                        "enchant": roll_enchant(pop_rng),
                        "x": pt[0], "y": pt[1],
                    })
                    eq_i += 1
                elif family == "spellbook":
                    magnitude = _weighted_choice(pop_rng, MAGNITUDE_WEIGHTS_BY_TIER[tier])
                    band = _MAGNITUDE_TO_GEAR_TIER[magnitude]
                    spellbook_drops.append({
                        "id": f"biome_{biome_id}_{seed}_sb{sb_i}",
                        "spell_id": pop_rng.choice(SPELL_IDS_BY_BAND[band]),
                        "x": pt[0], "y": pt[1],
                    })
                    sb_i += 1
                else:
                    magnitude = _weighted_choice(pop_rng, MAGNITUDE_WEIGHTS_BY_TIER[tier])
                    item_type = family if magnitude == "normal" else f"{family}_{magnitude}"
                    items.append({
                        "id": f"biome_{biome_id}_{seed}_i{i_i}",
                        "type": item_type,
                        "x": pt[0], "y": pt[1],
                    })
                    i_i += 1

    # -- guaranteed vault: the mini-boss chamber. Unlike the Depths' chance-
    # gated vault, this always exists -- it's the whole point of the
    # dungeon (fragment guarded by the biome's toughest enemy), so unlike
    # generate_room() above, a lock that turns out to be bypassable isn't an
    # acceptable outcome here.
    #
    # generate_room()'s own vault placement has a latent gap worth noting:
    # it carves the vault AFTER the spanning-tree/loop corridors, and
    # _place_vault only checks the vault's own footprint against the grid
    # cell's bounds -- never against corridor cells already carved through
    # that same space. When a corridor's straight L-shaped path happens to
    # cross where the vault ends up, it silently breaches the vault's other
    # three walls, leaving the "locked" door decorative (confirmed by
    # instrumenting generate_room() directly: ~40% of seeded Depths vaults
    # across a 300-seed sample are reachable without ever picking up the
    # key). Fixing that in generate_room() itself is out of scope here
    # (bigger blast radius, and a bypassable Depths vault is low-stakes --
    # bonus loot, not mandatory progression); Adventure Mode's fragment
    # being trivially skippable in ~40% of playthroughs would defeat the
    # whole point, so the fix below is scoped to generate_biome_room only.
    #
    # The fix: after carving the vault interior, force every tile in its
    # 1-tile-thick outer ring to '#' except the connector cell -- this
    # guarantees the door is the vault's only entrance regardless of what a
    # corridor happened to carve there first. The only remaining risk is
    # the reverse problem (the ring-force itself severing some *other*
    # room's only path through that space), so every attempt is verified by
    # a full reachability flood from the entry landing before being
    # accepted; a placement that would disconnect anything is undone (via
    # the snapshot) and the next host is tried instead.
    locked_doors, gates, switches, chests = [], [], [], []
    host_order = list(range(len(nodes)))
    layout_rng.shuffle(host_order)
    placed = False
    for host_i in host_order:
        host_node = nodes[host_i]
        vault_rect, connector = _place_vault(layout_rng, core_rooms[host_node], cell_bounds[host_node])
        if vault_rect is None:
            continue
        key_room_i = layout_rng.randrange(len(core_rects))
        key_pt = _random_free_point(pop_rng, core_rects[key_room_i], room_occupied[key_room_i])
        if key_pt is None:
            continue

        vx, vy, vw, vh = vault_rect
        cx, cy = connector
        touched = [
            (x, y)
            for y in range(vy - 1, vy + vh + 1)
            for x in range(vx - 1, vx + vw + 1)
            if 0 <= x < WIDTH and 0 <= y < HEIGHT
        ]
        snapshot = {(x, y): layout[y][x] for x, y in touched}

        _carve_rect(layout, vault_rect)
        for x, y in touched:
            on_ring = x in (vx - 1, vx + vw) or y in (vy - 1, vy + vh)
            if on_ring and (x, y) != (cx, cy):
                layout[y][x] = "#"
        layout[cy][cx] = "."

        other_centers = [_rect_center(r) for r in core_rects] + [(exit_x, exit_y)]
        reach = _reachable_floor(layout, landing)
        if not all(pt in reach for pt in other_centers):
            # The forced ring severed some other room's only path through
            # this space -- undo and try the next host.
            for (x, y), ch in snapshot.items():
                layout[y][x] = ch
            continue

        regions.append({"id": "vault0", "x": vx, "y": vy, "w": vw, "h": vh})

        room_occupied[key_room_i].add(key_pt)
        door_id = f"biome_{biome_id}_{seed}_door0"
        locked_doors.append({"id": door_id, "x": cx, "y": cy})
        items.append({
            "id": f"biome_{biome_id}_{seed}_key0",
            "type": "key",
            "x": key_pt[0], "y": key_pt[1],
        })

        boss_pt = _random_free_point(pop_rng, vault_rect, set()) or _rect_center(vault_rect)
        enemies.append({
            "id": f"biome_{biome_id}_{seed}_boss",
            "type": biome["boss_type"],
            "x": boss_pt[0], "y": boss_pt[1],
            "level": 1,
        })

        chest_x, chest_y = _rect_center(vault_rect)
        if (chest_x, chest_y) == boss_pt:
            chest_x = min(vx + vw - 2, chest_x + 1)
        chests.append({
            "id": f"biome_{biome_id}_{seed}_chest0",
            "x": chest_x, "y": chest_y,
            **_vault_reward(biome),
        })
        placed = True
        break

    if not placed:
        # No geometric room for a separate locked vault (rare, given the
        # 2x2 grid's generous per-cell sizing) -- fall back to an unlocked
        # boss chamber in the biggest core room rather than ever shipping a
        # dungeon whose fragment can't be reached. Still guards the
        # fragment behind the mini-boss fight, just without the lock/key
        # puzzle on top.
        fallback_i = max(range(len(core_rects)), key=lambda i: core_rects[i][2] * core_rects[i][3])
        rect = core_rects[fallback_i]
        occupied = room_occupied[fallback_i]
        boss_pt = _random_free_point(pop_rng, rect, occupied) or _rect_center(rect)
        occupied.add(boss_pt)
        enemies.append({
            "id": f"biome_{biome_id}_{seed}_boss",
            "type": biome["boss_type"],
            "x": boss_pt[0], "y": boss_pt[1],
            "level": 1,
        })
        chest_pt = _random_free_point(pop_rng, rect, occupied) or _rect_center(rect)
        occupied.add(chest_pt)
        chests.append({
            "id": f"biome_{biome_id}_{seed}_chest0",
            "x": chest_pt[0], "y": chest_pt[1],
            **_vault_reward(biome),
        })

    return {
        "name": biome["name"],
        "layout": ["".join(row) for row in layout],
        "exits": exits,
        "enemies": enemies,
        "items": items,
        "equipment_drops": equipment_drops,
        "spellbook_drops": spellbook_drops,
        "regions": regions,
        "locked_doors": locked_doors,
        "gates": gates,
        "switches": switches,
        "chests": chests,
        "traps": traps,
    }
