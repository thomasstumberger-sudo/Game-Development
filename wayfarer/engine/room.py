"""Room templates: hand-authored, loaded once from data/rooms/*.json and
cached for the rest of the process. A Room is static (the grid, exits, and
enemy/item/lock/chest *templates*) -- which enemies are dead, which items
are taken, which locks are solved, and which regions have been seen lives
in save.py's per-room flags, applied by the caller (main.py's Game) when it
spawns live entities/state for a visit.

Session 10: rooms can now define interior structure beyond wall/floor --
`regions` (fog-of-war chunks, see Game.revealed_regions), `locked_doors`/
`gates` (impassable until solved -- Room stays flag-agnostic here, the
caller passes in which ones are *currently* closed), `switches`/`chests`
(rendered and interacted with entirely in main.py, same as NPCs; Room only
needs to know about them at all for `is_walkable`'s exclusion set). A room
also picks a `tileset` (defaults to "dungeon") so hand-authored rooms can
use a different sprite set -- e.g. the overworld hub's grass/hedge tiles
instead of dungeon stone.
"""

import json
import os

from engine.assets import BASE_DIR

ROOMS_DIR = os.path.join(BASE_DIR, "data", "rooms")

WALL = 1
FLOOR = 0

COLOR_FOG = (4, 4, 6)

KIND_FALLBACK_COLORS = {
    "stairs_down": (200, 170, 40),
    "stairs_up": (170, 140, 200),
    "building": (150, 100, 60),
    "cave": (40, 70, 45),
    # Wayfarer Adventure Mode's biome-dungeon entrance -- see
    # wayfarer/wayfarer_adventure.md. Warm desert-orange, distinct from the
    # Depths' cool "cave" marker at a glance.
    "wilds": (200, 120, 40),
    # Session 45: Frostreach's own town-exit marker -- icy pale blue,
    # distinct from both "cave" and the Scorched Wastes' warm "wilds" tint
    # at a glance.
    "frost": (110, 170, 220),
    # Session 46: Stormfell's own town-exit marker -- magenta/violet,
    # distinct from "cave"/"wilds" (warm orange)/"frost" (cool blue). See
    # main.py's AssetManager.make_tint_variant("storm", ...) call for why
    # this landed on a red-leaning wash rather than the blue-leaning first
    # attempt.
    "storm": (180, 70, 200),
    # Session 47: Fenmire's own town-exit marker -- murky swamp green,
    # distinct from every warm/cool tint used by the first three biomes.
    "mire": (70, 110, 60),
    # Session 47: the Final Area's town-exit marker -- saturated
    # yellow-gold (red+green boosted, blue suppressed), a hue combination
    # none of the other four markers use (see main.py's make_tint_variant
    # call for why an earlier "just make it brighter" attempt didn't work).
    "sanctum": (220, 190, 60),
}

_ROOM_CACHE = {}


class Room:
    def __init__(self, room_id, data):
        self.id = room_id
        self.name = data.get("name", room_id)
        self.tileset = data.get("tileset", "dungeon")
        layout = data["layout"]
        self.height = len(layout)
        self.width = len(layout[0])
        self.grid = [
            [WALL if ch == "#" else FLOOR for ch in row]
            for row in layout
        ]
        self.exits = data.get("exits", [])
        self.enemy_templates = data.get("enemies", [])
        self.item_templates = data.get("items", [])
        # Session 16: per-instance gear lying on the floor -- see
        # engine/equipment.py and procgen.py's "equipment" loot family.
        # Structural template only (base_type/enchant/position); the actual
        # per-instance record is created on pickup (main.py).
        self.equipment_drop_templates = data.get("equipment_drops", [])
        # Session 39: spellbooks lying on the floor -- same structural-
        # template-only split as equipment_drop_templates above (spell_id/
        # position; the actual learn-or-refund happens on pickup, main.py).
        self.spellbook_drop_templates = data.get("spellbook_drops", [])
        self.npc_templates = data.get("npcs", [])
        # Session 10 additions -- all optional/empty by default so existing
        # simple hand-authored rooms (no interior structure) need no changes.
        self.regions = data.get("regions", [])
        self.locked_door_templates = data.get("locked_doors", [])
        self.gate_templates = data.get("gates", [])
        self.switch_templates = data.get("switches", [])
        self.chest_templates = data.get("chests", [])
        # Session 28: hidden dungeon traps (Castle of the Winds' dart/pit/
        # gas traps) -- structural template only, same "always in the list,
        # state lives in room_flags" convention chests/switches already use
        # (see main.py's Game.traps/sprung_trap_ids).
        self.trap_templates = data.get("traps", [])
        self._region_grid = self._build_region_grid()
        self._border_regions = self._build_border_regions()

    def _build_region_grid(self):
        """(x, y) -> region id, sparse dict (only floor tiles that belong to
        a defined region have an entry). Computed once and cached on the
        instance -- a room's regions never change shape after generation,
        same "structure is permanent, only visited-state changes" split
        procgen.py already keeps for everything else."""
        grid = {}
        for region in self.regions:
            rid = region["id"]
            if "cells" in region:
                for x, y in region["cells"]:
                    grid[(x, y)] = rid
            else:
                for yy in range(region["y"], region["y"] + region["h"]):
                    for xx in range(region["x"], region["x"] + region["w"]):
                        grid[(xx, yy)] = rid
        return grid

    def _build_border_regions(self):
        """(x, y) -> set of region ids, for tiles that have no region of
        their own -- walls, and door/exit gaps between regions. Regions are
        only ever defined over a room's floor rects/cells (see
        `_build_region_grid`), never the wall ring around them or the single-
        tile gaps hand-authored rooms cut through a border wall for a door.
        Without this, those tiles stayed permanently fogged black even after
        the room next to them was fully explored, since they never matched
        any revealed region id -- which is what made walls and doors visually
        indistinguishable (both just solid black) until you walked into them.
        A wall is visible the moment you can see the room beside it, so it
        borrows visibility from *any* neighboring revealed region, not one
        fixed owner."""
        borders = {}
        if not self.regions:
            return borders
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in self._region_grid:
                    continue
                neighbor_regions = set()
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    rid = self._region_grid.get((x + dx, y + dy))
                    if rid is not None:
                        neighbor_regions.add(rid)
                if neighbor_regions:
                    borders[(x, y)] = neighbor_regions
        return borders

    def region_at(self, x, y):
        return self._region_grid.get((x, y))

    def is_revealed(self, x, y, revealed_regions):
        """Whether (x, y) should render un-fogged given a set of revealed
        region ids -- true both for tiles directly inside a revealed region
        and for border tiles (walls, door gaps) that touch one. `Game.
        _is_visible` (main.py) uses this same check to gate entity/fixture
        rendering, so a locked door or gate sitting in a border gap (like
        Room.draw's floor/wall tiles) doesn't stay invisible after the room
        beside it has been revealed."""
        rid = self._region_grid.get((x, y))
        if rid is not None:
            return rid in revealed_regions
        border = self._border_regions.get((x, y))
        return bool(border) and not border.isdisjoint(revealed_regions)

    def is_walkable(self, x, y, blocked=None, ignore_walls=False):
        """`blocked` is an optional set of (x, y) currently-closed locked
        doors/gates -- Room itself has no notion of "solved," the caller
        (Game) computes that set from save-backed flags each visit.
        `ignore_walls` (session 24: the Wraith's wall-phasing) still enforces
        room bounds and `blocked` -- it only lets the WALL tile check itself
        pass. Castle of the Winds' wraiths pass through closed doors too;
        this engine's locked doors/gates are enforced by the caller's
        `occupied_positions` set instead (see Enemy.take_turn), not this
        method, so a Wraith still can't path through a still-closed one --
        a deliberate scope cut, see PROGRESS.MD session 24."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        if blocked and (x, y) in blocked:
            return False
        return ignore_walls or self.grid[y][x] == FLOOR

    def exit_at(self, x, y):
        for exit_data in self.exits:
            if exit_data["x"] == x and exit_data["y"] == y:
                return exit_data
        return None

    def draw(self, screen, tile_size, revealed_regions=None):
        """`revealed_regions` (a set of region ids) enables fog of war --
        omit it (or leave a room with no `regions` defined) and every tile
        just draws normally, so simple hand-authored rooms are unaffected."""
        from engine.assets import AssetManager
        wall_sprite = AssetManager.get_sprite(f"wall_{self.tileset}")
        floor_sprite = AssetManager.get_sprite(f"floor_{self.tileset}")
        exit_sprite = AssetManager.get_sprite("exit")
        exit_kinds = {(e["x"], e["y"]): e.get("kind") for e in self.exits}
        fog_active = bool(self.regions) and revealed_regions is not None

        for row in range(self.height):
            for col in range(self.width):
                pos = (col * tile_size, row * tile_size)

                if fog_active and not self.is_revealed(col, row, revealed_regions):
                    import pygame
                    pygame.draw.rect(screen, COLOR_FOG, (*pos, tile_size, tile_size))
                    continue

                if self.grid[row][col] == WALL:
                    if wall_sprite is not None:
                        screen.blit(wall_sprite, pos)
                    else:
                        import pygame
                        pygame.draw.rect(screen, (50, 50, 50), (*pos, tile_size, tile_size))
                    continue

                # Floor is always drawn first -- exit/kind sprites (archways,
                # stairs, town markers) are partially-transparent decorative
                # overlays meant to sit on top of a lit floor tile, not a
                # standalone replacement for one. Drawing only the overlay
                # directly on the (black-cleared) room surface was why doors
                # rendered as almost solid black even when correctly
                # revealed: most of that sprite's pixels are transparent.
                if floor_sprite is not None:
                    screen.blit(floor_sprite, pos)
                else:
                    import pygame
                    pygame.draw.rect(screen, (30, 30, 30), (*pos, tile_size, tile_size))

                if (col, row) in exit_kinds:
                    kind = exit_kinds[(col, row)]
                    overlay = AssetManager.get_sprite(kind) or exit_sprite
                    if overlay is not None:
                        screen.blit(overlay, pos)
                    else:
                        import pygame
                        fallback_color = KIND_FALLBACK_COLORS.get(kind, (80, 140, 80))
                        pygame.draw.rect(screen, fallback_color, (*pos, tile_size, tile_size))

    @classmethod
    def load(cls, room_id):
        if room_id in _ROOM_CACHE:
            return _ROOM_CACHE[room_id]

        if room_id.startswith("proc:"):
            from engine.procgen import generate_room
            _, seed_str, level_str, gx_str, gy_str = room_id.split(":")
            data = generate_room(int(seed_str), int(level_str), int(gx_str), int(gy_str))
        elif room_id.startswith("biome:"):
            # Wayfarer Adventure Mode (see wayfarer/wayfarer_adventure.md):
            # a single finite generated room, id "biome:<biome_id>:<seed>".
            # Unlike "proc:" rooms, main.py's load_room applies no epoch/
            # respawn machinery to these -- the population generated here is
            # cached forever by _ROOM_CACHE below, same as a hand-authored
            # room's fixed templates.
            from engine.procgen import generate_biome_room
            _, biome_id, seed_str = room_id.split(":")
            data = generate_biome_room(int(seed_str), biome_id)
        else:
            path = os.path.join(ROOMS_DIR, f"{room_id}.json")
            with open(path, "r") as f:
                data = json.load(f)

        room = cls(room_id, data)
        _ROOM_CACHE[room_id] = room
        return room
