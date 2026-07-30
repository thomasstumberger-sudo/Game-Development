"""Wayfarer -- entry point.

The single most important property of this loop: it is CPU-cheap at idle.
- The frame rate is hard-capped (never uncapped, never busy-waits).
- When the window loses focus, input is still polled but the loop throttles
  down to ~5Hz.
- The screen is only redrawn when something actually changed (dirty flag),
  except while the F3 debug overlay is on, where a live reading is the
  whole point of the feature.

Future work (explicitly out of scope for this pass): networking, controller
support, scrolling maps.
"""

import os
import sys
import json
import math
import random
import uuid

import pygame

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from engine.assets import AssetManager, BASE_DIR
from engine.room import Room
from engine.entity import Player, Enemy, ItemPickup, EquipmentDrop, SpellbookDrop, NPC
from engine.combat import resolve_bump_attack, resolve_spell_hit, resolve_ball_splash_to_player, enemy_attack, grant_xp, resolve_trap, resolve_disarm
from engine.inventory import Inventory
from engine.save import SaveManager, DEFAULT_ROOM, DEFAULT_SPAWN, DEFAULT_ROUTE
from engine.procgen import (
    generate_room, scale_stats_for_level, room_doors,
    BIOME_DEFS, COMBAT_DIFFICULTIES, DEFAULT_DIFFICULTY, difficulty_def,
)
from engine.equipment import (
    SLOTS, equip as equip_item, next_offer, create_instance,
    create_shop_instance, bag_instances, display_name as equip_display_name,
    remove_curse as remove_curse_item, discard_instance,
)
from engine.spells import newly_learned

# Session 9: switched from the original 64x64 placeholder/tileset art to a
# native-16px icon/character/dungeon set (see PROGRESS.MD). TILE_SIZE must
# match the source art's native size or sprites overlap their neighbors
# instead of tiling cleanly -- same rule as before, just a smaller number.
# Rooms grew from 10x8 to ROOM_TILES_W x ROOM_TILES_H (40x32, exactly 4x
# each dimension) so the *pixel* footprint of a room is unchanged
# (40*16=640, 32*16=512, identical to 10*64/8*64) -- more tiles visible on
# screen at the same window size and CPU/render cost, not a bigger window.
TILE_SIZE = 16
ROOM_TILES_W, ROOM_TILES_H = 40, 32
ROOM_PIXEL_W, ROOM_PIXEL_H = ROOM_TILES_W * TILE_SIZE, ROOM_TILES_H * TILE_SIZE

# Session 25 (UI pass): the window used to be a flat 800x600 with the
# 640x512 room viewport floating in the middle of it -- 80px of dead black
# margin on each side (nothing ever drawn there) and a message log jammed
# into the leftover 32px at the bottom, which clipped its own second line
# past the window edge. Sized from the room viewport outward instead of the
# other way around: a boxed top HUD bar and boxed bottom log bar, each full
# window width, sized to their own worst-case content (see TOP_BAR_H/LOG_H
# below) rather than an arbitrary guess, plus a thin fixed side margin
# (HUD_GAP) around the room itself so it isn't flush against the window
# edge. Total window area is within a few percent of the old 800x600 --
# this reshapes the waste into functional chrome, it doesn't grow the
# footprint.
HUD_GAP = 4
TOP_BAR_H = 84
LOG_H = 110
WINDOW_W = ROOM_PIXEL_W + HUD_GAP * 2
WINDOW_H = TOP_BAR_H + HUD_GAP + ROOM_PIXEL_H + HUD_GAP + LOG_H
ROOM_ORIGIN = (HUD_GAP, TOP_BAR_H + HUD_GAP)
LOG_ORIGIN = (HUD_GAP, ROOM_ORIGIN[1] + ROOM_PIXEL_H + HUD_GAP)
LOG_MAX_LINES = 5

ACTIVE_FPS = 30
IDLE_FPS = 5

# Session 18: most slot keys read fine through plain .title() (weapon ->
# "Weapon"), but ring1/ring2/amulet don't -- this is the one departure from
# that generic formatting, everything else about SLOTS stays untouched.
SLOT_LABELS = {"ring1": "Ring 1", "ring2": "Ring 2"}


def slot_label(slot):
    return SLOT_LABELS.get(slot, slot.title())


# Physical key -> single-step direction, shared by the initial KEYDOWN move
# and by held-key repeat (session 13) so both agree on what counts as a
# "movement key" without duplicating the mapping.
MOVE_KEYS = {
    pygame.K_LEFT: (-1, 0), pygame.K_a: (-1, 0),
    pygame.K_RIGHT: (1, 0), pygame.K_d: (1, 0),
    pygame.K_UP: (0, -1), pygame.K_w: (0, -1),
    pygame.K_DOWN: (0, 1), pygame.K_s: (0, 1),
}
# Session 13: holding a direction (keyboard) or the left mouse button
# (click-to-walk) keeps moving one tile at a time rather than needing a
# fresh tap/click per step -- DELAY is how long a key/button must be held
# before repeat kicks in (matches the first move that already happened on
# press/click), INTERVAL is the pace of each repeat step after that.
MOVE_REPEAT_DELAY_MS = 220
MOVE_REPEAT_INTERVAL_MS = 120

# Player actions (not wall-clock time -- this stays free at idle, matching
# the turn model) before a fully-cleared Depths room repopulates.
RESPAWN_THRESHOLD = 150

# Session 30: Castle of the Winds' free field-Rest command -- HP/mana trickle
# back a small amount per turn spent resting (each turn still ticks buffs/
# poison down and advances turn_count, same "costs turns not gold" trade-off
# as any other action, unlike the Healer's paid instant-full-heal service).
# Capped so a pathological state (poison outpacing regen) can't loop forever.
REST_HEAL_PER_TURN = 2
REST_MANA_PER_TURN = 1
REST_MAX_TURNS = 200

SAVE_PATH = os.path.join(BASE_DIR, "save.db")

COLOR_BG = (10, 10, 14)
COLOR_HP = (200, 40, 40)
COLOR_HP_BG = (50, 15, 15)
COLOR_MP = (60, 110, 220)
COLOR_MP_BG = (15, 20, 50)
COLOR_TEXT = (230, 230, 230)
COLOR_DEBUG = (0, 255, 0)
# Session 53: a journey's route decides how many fragments break the seal, so
# the victory lines can no longer hardcode "four" -- small enough a range that
# a lookup beats pulling in a number-to-words dependency.
NUMBER_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
COLOR_POISON = (120, 200, 90)
COLOR_DRAIN = (150, 150, 230)
COLOR_WEAKEN = (200, 150, 100)  # session 37: Wight attack drain, earthy tone to match its sprite tint
COLOR_LEVITATE = (140, 215, 235)
COLOR_RESIST_FIRE = (225, 120, 60)
COLOR_RESIST_COLD = (190, 225, 250)
COLOR_RESIST_LIGHTNING = (110, 150, 235)
COLOR_SLEEP = (180, 180, 255)  # session 40: Sleep Monster's "Zzz" tag over an asleep enemy
COLOR_PANEL_BG = (20, 20, 28, 235)
COLOR_PANEL_BORDER = (95, 95, 120)
COLOR_HUD_BG = (17, 17, 24)
COLOR_GOLD = (230, 190, 60)


def _capitalize_first(text):
    """Uppercase a string's first character and leave the rest alone --
    unlike str.capitalize(), which lowercases everything after it and would
    flatten the proper nouns these sentences are full of ("the Frostreach")."""
    return text[:1].upper() + text[1:]


def _wrap_text(font, text, max_width):
    """Greedy word-wrap shared by every panel/log that needs it (session 25
    -- previously duplicated as a local closure inside
    _draw_spellbook_panel). Splits purely on spaces and never breaks a
    single word, matching every current caller's content (prose sentences,
    not unbroken long tokens)."""
    words = text.split(" ")
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class Game:
    def __init__(self, screen, new_game=False):
        self.screen = screen
        # Placeholder full-viewport subsurface -- load_room() (called below,
        # once state/seed are ready) immediately replaces both of these via
        # _resize_room_surface() sized to whatever room is actually entered.
        self.room_draw_origin = ROOM_ORIGIN
        self.room_surface = screen.subsurface(
            pygame.Rect(*ROOM_ORIGIN, ROOM_PIXEL_W, ROOM_PIXEL_H)
        )

        self._load_assets()
        with open(os.path.join(BASE_DIR, "data", "items.json")) as f:
            self.item_defs = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "equipment.json")) as f:
            self.equipment_defs = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "enemies.json")) as f:
            self.enemy_defs = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "npcs.json")) as f:
            self.npc_defs = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "quests.json")) as f:
            self.quests = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "spells.json")) as f:
            self.spell_defs = json.load(f)  # ordered list -- unlock order matters, see engine/spells.py
        with open(os.path.join(BASE_DIR, "data", "traps.json")) as f:
            self.trap_defs = json.load(f)
        # Wayfarer Adventure Mode (see wayfarer/wayfarer_adventure.md):
        # artifact fragment definitions, resolved against ids
        # engine/procgen.py's generate_biome_room emits -- same "procgen
        # trusts a key string exists, main.py resolves it" split as
        # equipment/spellbook defs above.
        with open(os.path.join(BASE_DIR, "data", "artifacts.json")) as f:
            self.artifact_defs = json.load(f)
        # Session 45: the fetch/trade quest chain -- an ordered list, same
        # "scan from the front for the first not-yet-completed entry" shape
        # as self.quests/current_quest() below, just keyed by a persisted
        # id set (completed_adventure_quests) rather than a bare index,
        # per wayfarer_adventure.md's own proposed schema.
        #
        # Session 52: the file no longer *is* that list -- it's the authored
        # material the list is built from (per-biome phrases + templates),
        # because a journey can shuffle the biome order and a step's dialogue
        # therefore can't be authored against one fixed (source, target)
        # pair. _build_adventure_chain() below assembles the same list shape
        # every consumer already expects.
        with open(os.path.join(BASE_DIR, "data", "adventure_quests.json")) as f:
            self.adventure_quest_defs = json.load(f)

        self.save = SaveManager(SAVE_PATH)
        if new_game:
            self.save.reset()
        state = self.save.load_game() or self.save.new_game_defaults()

        self.player = Player(
            state["pos"][0], state["pos"][1], state["player"],
            state.get("equipment"), state.get("equipment_instances"),
        )
        self.inventory = Inventory(self.item_defs, state["inventory"])
        self.seed = state["seed"]
        self.turn_count = state["turn_count"]
        self.depths_kills = state["depths_kills"]
        self.quest_index = state["quest_index"]
        self.known_spells = set(state.get("known_spells", set()))
        # Wayfarer Adventure Mode: fragments ever claimed, flat/permanent
        # like known_spells (see engine/save.py).
        self.artifact_fragments = set(state.get("artifact_fragments", set()))
        # Session 45: which fetch/trade quests in the chain are complete --
        # same flat/permanent shape as the two sets above. Session 52: ids in
        # here are journey-scoped (see _journey_id), so this set accumulates
        # across journeys rather than being cleared by a new one -- a
        # permanent record of everything this character has ever finished,
        # and a completed journey's rows keep proving the old journey was
        # won even after a new one starts.
        self.completed_adventure_quests = set(state.get("completed_adventure_quests", set()))
        # Session 52 (Adventure Mode journeys, Yoda Stories' "New World"):
        # which journey this character is on, its chosen combat difficulty,
        # and how many have been won. self.adventure_chain is derived, not
        # persisted -- rebuilt from the journey index on every boot and every
        # time a new journey starts.
        self.journey_index = state.get("journey_index", 1)
        self.combat_difficulty = state.get("combat_difficulty", DEFAULT_DIFFICULTY)
        self.journeys_won = state.get("journeys_won", 0)
        # Session 53: the journey's ROUTE -- the shape of its chain, chosen
        # alongside the difficulty when it starts. "old_road" is the straight
        # line sessions 45-52 built and is what every pre-session-53 save
        # (and journey 1, always) is on; see route_def/_build_adventure_chain.
        self.adventure_route = state.get("adventure_route", DEFAULT_ROUTE)
        self.adventure_chain = self._build_adventure_chain()
        # Catches up a returning save to any spell it already qualifies for
        # (e.g. this session's new content, or simply level 1's starting
        # spell on a brand new character) -- silent, no message spam on boot.
        self._learn_new_spells(None)

        self.current_room_id = None
        self.room = None
        self.enemies = []
        self.items = []
        self.npcs = []
        self.dead_enemy_ids = set()
        self.taken_item_ids = set()
        # Session 10: interactive dungeon fixtures for the current room.
        # locked_doors/gates hold only the currently-CLOSED ones (mirrors
        # how self.enemies/self.items already only hold live/untaken ones);
        # chests/switches always hold ALL of them since they stay visible
        # (just change sprite) once resolved rather than disappearing.
        self.locked_doors = []
        self.gates = []
        self.switches = []
        self.chests = []
        self.unlocked_door_ids = set()
        self.open_gate_ids = set()
        self.opened_chest_ids = set()
        # Session 28: hidden dungeon traps. Like chests/switches, `traps`
        # always holds every trap in the room (sprung or not); which ones
        # have been sprung is separate persisted state (sprung_trap_ids,
        # same room_flags mechanism as opened_chest_ids), since a sprung
        # trap stays a harmless (but visible) fixture forever.
        self.traps = []
        self.sprung_trap_ids = set()
        # Session 48: push-block puzzles (see engine/room.py's module
        # docstring). `plates` mirrors switches (always holds every plate
        # in the room; state is which sprite it picks via open_gate_ids, no
        # separate tracking needed). `blocks` is the one fixture list here
        # whose *position* mutates in play -- loaded from the room's
        # template starting positions and overlaid with any persisted
        # pushed position (see load_room), flushed via
        # engine/save.py's block_positions table at the same three
        # call sites room_drops already flushes from (persist(), the
        # "exit" stairs/door branch, and Word of Recall).
        self.plates = []
        self.blocks = []
        # Room-based fog of war (session 10): region ids the player has
        # physically stood in, for the *current* room. Persisted via
        # room_flags like everything else above -- see load_room/persist.
        self.revealed_regions = set()
        # Divination (session 15): turns remaining that enemies/items+chests
        # bypass the fog check below and render regardless of
        # revealed_regions. Deliberately NOT persisted through save/reload
        # (unlike Stone Skin's buff_defense_turns) -- it's a purely visual
        # effect, so losing it on a save/quit is low-stakes and this avoids
        # a schema migration for it.
        self.detect_monsters_turns = 0
        self.detect_treasure_turns = 0
        # Session 28: Detect Traps -- same purely-visual, not-persisted
        # bypass-the-fog counter as the two above, gating trap fixture
        # rendering in _draw_fixtures alongside "already sprung."
        self.detect_traps_turns = 0
        # Depths-only: per-room repopulation state, keyed by room_id.
        # Lazily loaded from save.room_meta via _room_meta(), flushed back
        # in persist() -- same on-transition-only write discipline as
        # room_flags.
        self.room_epoch = {}
        self.room_cleared_turn = {}
        self.current_room_enemy_ids = set()
        # Depths automap (session 8): (gx, gy) sets of visited rooms, keyed
        # by dungeon level. Lazily loaded from save.discovered_rooms per
        # level (mirrors self.room_epoch's lazy-load pattern above), written
        # through immediately on first visit -- see load_room().
        self.discovered = {}

        self.message_log = []
        self.inventory_open = False
        self.inventory_cursor = 0
        self.quest_open = False
        self.shop_open = False
        self.shop_cursor = 0
        self.healer_open = False
        self.healer_cursor = 0
        self.bookshop_open = False
        self.bookshop_cursor = 0
        self.journal_open = False
        self.spellbook_open = False
        self.spellbook_cursor = 0
        # Session 45: the Frontier Guide's fetch/trade panel -- single
        # fixed-action shape, no cursor, same as the Quartermaster's quest
        # panel (see _draw_trade_panel/attempt_trade). Session 53 gave it a
        # cursor, because an Open Frontier journey can have several trades
        # on offer at once (the straight-line route still only ever has one,
        # and the panel keeps its original single-offer layout in that case).
        self.trade_open = False
        self.trade_cursor = 0
        # Session 47: the Final Area's one-time victory modal (see
        # _draw_win_screen/handle_key_down/handle_mouse_down). Deliberately
        # NOT persisted -- it's a celebratory toast the first time the final
        # chest opens, not a game state; whether the chest itself has
        # already been claimed is tracked the normal way, via
        # opened_chest_ids/completed_adventure_quests (both persisted), so a
        # reload after winning never re-shows the modal but the "already
        # won" fact is never lost either.
        self.win_screen_open = False
        # Session 52: the Guide's "set out on a new journey" panel (Yoda
        # Stories' New World dialog). journey_pending holds the difficulty
        # the cursor has *selected* but not yet confirmed -- the panel is a
        # single surface with two states (pick a difficulty / confirm the
        # discard) rather than two panels, since the second state is one
        # sentence and a yes.
        # Session 53: the same panel also picks the journey's route, so its
        # cursor now runs over a routes section followed by the difficulty
        # section (the Shop panel's own "append a section, share one cursor"
        # shape). journey_route_choice is the route the cursor has landed on;
        # only the difficulty rows arm/commit, since picking a route is not
        # itself destructive.
        self.journey_open = False
        self.journey_cursor = 0
        self.journey_pending = None
        self.journey_route_choice = self.adventure_route
        self.active_npc = None
        # Mouse support (session 13): whichever panel is currently drawn
        # re-populates these two just before it blits itself, so a click
        # can be hit-tested against the panel that's actually on screen
        # right now without main.py needing to know that panel's layout.
        self.panel_outer_rect = None
        self.panel_click_targets = []
        # Held-input continuous movement (session 13): see tick_move_repeat.
        # held_move_key tracks which *physical* key is driving the repeat so
        # handle_key_up only stops it when that specific key is released
        # (not some unrelated key going up), held_move_dir is the direction
        # it repeats; mouse_held is the click-and-hold equivalent, which has
        # no fixed direction since it's recomputed from the live cursor
        # position every repeat step (see handle_mouse_down).
        self.held_move_key = None
        self.held_move_dir = None
        self.mouse_held = False
        self.next_move_repeat_at = 0
        self.debug_overlay = False
        self.dirty = True

        self.load_room(state["current_room"], state["pos"][0], state["pos"][1])

    def _load_assets(self):
        """Session 9: real art, hand-picked from four user-supplied
        spritesheets (see PROGRESS.MD for the full curation notes) instead
        of the original 64px tileset + procedural placeholders. Sheets were
        pre-sliced to individual tile_<row>_<col>.png files by a one-off
        script (not checked in as a tool, mirrors the repo-root
        slice_spritesheet.py pattern) into assets/sprites/{dungeon_v2,
        characters,items16}/ -- dungeon_v2 was downscaled 32px->16px at
        slice time so every sheet here is already native TILE_SIZE, no
        runtime scaling.
        """
        D = "assets/sprites/dungeon_v2"
        C = "assets/sprites/characters"
        I = "assets/sprites/items16"
        O = "assets/sprites/overworld"

        # "_dungeon"/"_hub" suffixes match Room.tileset (session 10) so a
        # room can pick which wall/floor art it wants -- see engine/room.py.
        AssetManager.load_sprite("wall_dungeon", f"{D}/tile_4_1.png")
        AssetManager.load_sprite("floor_dungeon", f"{D}/tile_0_4.png")
        AssetManager.load_sprite("exit", f"{D}/tile_6_0.png")
        AssetManager.load_sprite("stairs_down", f"{D}/tile_8_3.png")
        # No second staircase graphic in the sheet -- tint the same one
        # violet for "up" rather than draw new art (see make_tint_variant).
        AssetManager.make_tint_variant("stairs_up", "stairs_down", (170, 140, 220))

        # Overworld hub (session 10): grass floor, hedge/tree border, plus
        # "building"/"cave" exit-kind markers (same mechanism Room.draw()
        # already uses for stairs_down/up -- a sprite registered under the
        # exact kind name wins over the generic "exit" arch).
        AssetManager.load_sprite("floor_hub", f"{O}/tile_1_3.png")
        AssetManager.load_sprite("wall_hub", f"{O}/tile_5_6.png")
        AssetManager.load_sprite("building", f"{O}/tile_2_16.png")
        AssetManager.load_sprite("cave", f"{O}/tile_3_13.png")
        # Wayfarer Adventure Mode's biome-dungeon entrance (see
        # wayfarer/wayfarer_adventure.md) -- same "cave" source art as the
        # Crypt, warm-tinted (make_tint_variant, same trick as gate/
        # locked_door below) so the two entrances read as different
        # destinations at a glance rather than reusing one sprite outright.
        AssetManager.make_tint_variant("wilds", "cave", (230, 150, 60))
        # Session 45: Frostreach's own town-exit marker -- same "cave" source
        # art, cool icy-blue tint instead of the Scorched Wastes' warm
        # orange, so the two biome entrances read as different destinations
        # from each other (and from the Crypt's own cave icon) at a glance.
        AssetManager.make_tint_variant("frost", "cave", (110, 170, 230))
        # Session 46: Stormfell's own town-exit marker -- same "cave" source
        # art. A first pass at (150, 120, 220) (a blue-leaning violet) read
        # as near-identical to "frost" once rendered -- confirmed by a
        # zoomed screenshot and a direct pixel sample of both tinted
        # surfaces (both landed on a near-identical dark blue-grey, since
        # BLEND_RGB_MULT can only ever darken the source's own channel
        # ratios, and the underlying cave art's shadow pixels are already
        # blue-dominant -- a wash color that's *also* blue-leaning can't pull
        # the result away from that). A magenta/violet wash (boosting red
        # over green, the opposite of frost's blue/green-leaning wash) plus a
        # higher strength (less blended toward white, more saturated) reads
        # as a distinct purple against both "wilds" (warm orange) and
        # "frost" (cool blue) -- reconfirmed the same way after the change.
        AssetManager.make_tint_variant("storm", "cave", (180, 70, 200), strength=0.85)
        # Session 47: Fenmire's own town-exit marker -- a swamp-green wash
        # boosting green over both red and blue, distinct in channel
        # relationship from every wash used above (wilds boosts red, frost
        # boosts blue, storm boosts red+blue together) so it can't collapse
        # toward any of them the way session 46's first storm attempt did.
        AssetManager.make_tint_variant("mire", "cave", (70, 150, 60))
        # Session 47: the Final Area's town-exit marker. First attempt used
        # a soft (230, 200, 110) gold at strength=0.5, reasoning (wrongly)
        # that a *lower* strength would read "brighter" -- a rendered
        # screenshot showed the opposite: make_tint_variant's `strength`
        # interpolates the wash color *toward white* as it drops (strength
        # 0 = an unmodified wash, i.e. no tint at all), so 0.5 produced a
        # muted, barely-there wash, nearly indistinguishable from "mire" in
        # a pixel sample. And per sessions 31/46's own established finding,
        # BLEND_RGB_MULT can only ever darken a channel relative to the
        # source art's own value -- there's no way to make a tint of the
        # same dark "cave" sprite read as literally brighter than the
        # others, so "radiant"/"brightest" was the wrong bar to aim for.
        # Fixed by aiming for a distinct *hue combination* instead (the same
        # standard the other four markers actually meet): a saturated
        # yellow-gold (roughly equal red+green boost, blue suppressed) at a
        # high strength for saturation, same as storm's own fix -- a
        # combination none of the other four washes use (wilds is
        # red-dominant, frost is blue-only, storm is red+blue, mire is
        # green-only).
        AssetManager.make_tint_variant("sanctum", "cave", (230, 210, 60), strength=0.8)

        # Interactive dungeon fixtures (session 10). Gate and locked_door
        # share one "iron bars" source image, tinted cool blue vs. warm gold
        # (make_tint_variant) so they read as different obstacles at a
        # glance despite being the same underlying art. Switches have no
        # matching sprite in either sheet -- small placeholders, same as
        # the slime -- and chests are real closed/open art.
        AssetManager.load_sprite("chest_closed", f"{D}/chest_closed.png")
        AssetManager.load_sprite("chest_open", f"{D}/chest_open.png")
        AssetManager.load_sprite("gate_bars", f"{D}/gate_bars.png")
        AssetManager.make_tint_variant("gate", "gate_bars", (120, 170, 220))
        AssetManager.make_tint_variant("locked_door", "gate_bars", (210, 160, 60))
        # Session 49: colored key/gate pairs (Yoda Stories/Desktop
        # Adventures -- wayfarer_adventure.md's other never-built "puzzles
        # as texture" mechanic, sokoban's sibling from the same doc line).
        # Same "iron bars" source, tinted distinctly from both the generic
        # amber locked_door above and each other -- copper leans red/orange
        # (no blue at all), jade leans green (no red) -- so a colored door
        # reads as visually different from a plain one and from its own
        # sibling color, not just a hue shift of the same lock.
        AssetManager.make_tint_variant("locked_door_copper", "gate_bars", (200, 90, 40))
        AssetManager.make_tint_variant("locked_door_jade", "gate_bars", (60, 170, 110))
        # Session 50: three more colors, wiring colored key/gate pairs into
        # Adventure Mode's own procedurally-generated biome vaults (see
        # BIOME_DEFS' new "lock_color" field in procgen.py) -- azure leans
        # blue with green suppressed (distinct from gate's own blue, which
        # has high green), violet is red+blue with green suppressed, gold
        # pushes green closer to red than the plain amber locked_door does
        # while dropping blue further -- all verified distinct from each
        # other and from the four existing gate_bars tints via a rendered
        # screenshot and direct pixel sample (see PROGRESS.MD session 50).
        AssetManager.make_tint_variant("locked_door_azure", "gate_bars", (50, 80, 210))
        AssetManager.make_tint_variant("locked_door_violet", "gate_bars", (170, 60, 200))
        AssetManager.make_tint_variant("locked_door_gold", "gate_bars", (230, 200, 40), strength=0.8)
        AssetManager.make_placeholder("switch_off", (150, 40, 40), shape="square")
        AssetManager.make_placeholder("switch_on", (50, 180, 70), shape="square")
        # Session 48: push-block puzzles (Yoda Stories/Desktop Adventures --
        # see wayfarer_adventure.md's "sokoban blocks" note). No crate/
        # boulder art in either sheet, same "no matching sprite" situation
        # as the switches above -- a warm brown-stone square (block) reads
        # as a physical obstacle distinct from the switch's own red/green,
        # and the plate's dim slate-blue/lit gold pair (mirroring
        # switch_off/on's own not-yet/triggered convention) reads as a
        # floor marking rather than an obstacle.
        AssetManager.make_placeholder("push_block", (140, 100, 60), shape="square")
        AssetManager.make_placeholder("plate_off", (90, 95, 115), shape="square")
        AssetManager.make_placeholder("plate_on", (210, 180, 60), shape="square")
        AssetManager.load_sprite("item_key", f"{I}/tile_30_9.png")
        # Session 49: the matching colored key items, tinted the same way
        # their doors are above -- picking up a copper key should visually
        # imply "this opens the copper door" before the player ever reads
        # the tooltip.
        AssetManager.make_tint_variant("item_key_copper", "item_key", (200, 90, 40))
        AssetManager.make_tint_variant("item_key_jade", "item_key", (60, 170, 110))
        # Session 50: matching key items for the three new biome-vault
        # colors above -- none tint cleanly off item_key the way copper/jade
        # did. A rendered screenshot and direct pixel sample showed two
        # separate flavors of the same underlying problem: item_key's source
        # pixels carry almost no blue channel at all (unlike gate_bars,
        # whose blue/violet door tints above read cleanly), so azure/violet
        # -- which need blue to read -- came out muddy brown, since
        # BLEND_RGB_MULT can only ever scale a channel down from what the
        # base already has, never invent one. Gold's failure is the mirror
        # case: item_key's own native coloring is already warm red/orange
        # with no blue, so a red+green/no-blue "gold" wash barely shifts it
        # at all -- an 8x side-by-side render showed gold landing
        # indistinguishable from both copper and the plain uncolored key.
        # Same class of base-art ceiling sessions 46/47 already hit for a
        # different sprite, just discovered here before it shipped rather
        # than after. Fixed the same way this codebase always resolves "no
        # matching art for the color/shape needed" (switches/blocks/plates/
        # spellbooks): a small diamond placeholder in the actual target hue
        # for all three, rather than a tint of unsuitable source art.
        AssetManager.make_placeholder("item_key_azure", (50, 90, 220), size=16, shape="diamond")
        AssetManager.make_placeholder("item_key_violet", (170, 60, 210), size=16, shape="diamond")
        AssetManager.make_placeholder("item_key_gold", (230, 200, 40), size=16, shape="diamond")
        # Session 39: dungeon-found spellbooks -- no readable/book art in
        # either sheet, same "no matching sprite" situation as the switches
        # above, so a placeholder (see AssetManager's new "book" shape) in a
        # violet distinct from every other item/potion tint used so far.
        AssetManager.make_placeholder("item_spellbook", (150, 90, 200), shape="book")
        # Wayfarer Adventure Mode: artifact fragments (data/artifacts.json)
        # -- no matching art in either sheet, same situation as the
        # spellbook above. Amber diamond, distinct from the Viper's olive
        # one and from the key's real sprite.
        AssetManager.make_placeholder("item_fragment", (255, 170, 40), shape="diamond")

        # Session 28: dungeon traps -- one caltrop-shaped placeholder per
        # type (see AssetManager's "spike" shape), colored to hint at each
        # trap's nature: grey steel for darts, earthy brown for a pit,
        # sickly green for gas (matches the poison-status color language
        # already established for the Viper/poison messaging).
        AssetManager.make_placeholder("dart_trap", (170, 170, 180), shape="spike")
        AssetManager.make_placeholder("pit_trap", (120, 80, 40), shape="spike")
        AssetManager.make_placeholder("poison_gas_trap", (90, 170, 70), shape="spike")

        AssetManager.load_sprite("enemy_skeleton", f"{C}/tile_24_0.png")
        AssetManager.load_sprite("enemy_cultist", f"{C}/tile_30_6.png")
        # Session 24: the Wraith -- no incorporeal/ghost sprite anywhere in
        # the (bipedal-humanoid) character sheet, so tint the skeleton's own
        # art a cold pale blue-violet (make_tint_variant, same trick as
        # stairs_up/gate/locked_door/mana potions) rather than force a bad
        # fit or add another shape placeholder -- an undead reusing an
        # undead's own silhouette, just ghostlier, reads correctly at a
        # glance next to the plain white Skeleton.
        AssetManager.make_tint_variant("enemy_wraith", "enemy_skeleton", (130, 150, 220), strength=0.8)
        # Session 35: Dark Wraith and Abyss Wraith -- same skeleton-silhouette
        # trick as the base Wraith above, just darker tints so the family
        # reads as an escalating series at a glance (pale blue-violet ->
        # deep violet -> near-black void) rather than three unrelated colors.
        # BLEND_RGB_MULT only darkens, which is exactly what a "deeper into
        # the abyss" progression needs -- no repeat of session 31's
        # can't-brighten problem here.
        AssetManager.make_tint_variant("enemy_dark_wraith", "enemy_skeleton", (80, 60, 130), strength=0.9)
        AssetManager.make_tint_variant("enemy_abyss_wraith", "enemy_skeleton", (35, 20, 55), strength=0.95)
        # Session 37: the Wight family -- same skeleton-silhouette tint
        # trick, but an earthy brown/grey/stone palette rather than the
        # Wraith family's blue-violet one, so the two undead-drain families
        # read as visually distinct at a glance (barrow-dweller vs. ghost)
        # even though both reuse the same base sprite. Escalating darkness
        # by tier, same "deeper -> darker" progression as the Wraiths.
        AssetManager.make_tint_variant("enemy_barrow_wight", "enemy_skeleton", (150, 120, 80), strength=0.7)
        AssetManager.make_tint_variant("enemy_tunnel_wight", "enemy_skeleton", (100, 85, 70), strength=0.85)
        AssetManager.make_tint_variant("enemy_castle_wight", "enemy_skeleton", (60, 50, 45), strength=0.95)
        # No slime/blob-shaped monster anywhere in the character sheet (it's
        # all bipedal humanoids) -- kept as the original procedural
        # placeholder rather than force a bad fit.
        AssetManager.make_placeholder("enemy_slime", (60, 170, 90))
        # Session 21: same reasoning as the slime above -- no matching
        # sprite exists, and a diamond silhouette keeps it visually distinct
        # from the slime's circle at a glance.
        AssetManager.make_placeholder("enemy_viper", (150, 170, 40), shape="diamond")
        # Session 22: same reasoning again -- no dragon anywhere in the
        # character sheet either. A red triangle reads as more aggressive
        # than the viper's diamond, distinct at a glance from every other
        # enemy silhouette in the game.
        AssetManager.make_placeholder("enemy_dragon", (200, 60, 30), shape="triangle")
        # Session 31: Young White Dragon -- CotW's cold-elemental mirror of
        # the Red Dragon line. No second dragon shape in the character sheet
        # either. Tried make_tint_variant first (the same trick session 24
        # used for the Wraith), but BLEND_RGB_MULT can only ever darken a
        # channel, never brighten one -- the red dragon's green/blue
        # channels (60, 30) are too low for any multiplicative wash to lift
        # them into a pale icy color, so the "tinted" result was still
        # visibly red (caught by rendering and comparing the two sprites
        # directly, not just diffing raw pixel bytes). A second
        # make_placeholder call with the same triangle shape but a genuinely
        # pale blue-white color reads as the intended icy mirror instead.
        AssetManager.make_placeholder("enemy_white_dragon", (225, 240, 255), shape="triangle")
        # Session 32: Young Blue Dragon -- CotW's lightning-elemental dragon
        # (Blue Dragons "breathe lightning" per the game's own bestiary), the
        # third leg of the fire/cold/lightning set alongside sessions 22/31.
        # Same triangle silhouette as its two mirror dragons, colored a
        # saturated electric blue -- distinct from the White Dragon's pale
        # near-white fill and from the Wraith's muted blue-violet tint (which
        # is on a different, humanoid silhouette anyway).
        AssetManager.make_placeholder("enemy_blue_dragon", (40, 100, 230), shape="triangle")
        # Session 33: Young Green Dragon -- CotW's poison-gas-breathing
        # dragon color (Red/fire, White/cold, Blue/lightning, Green/poison
        # gas is the game's actual four-color roster, confirmed via
        # research rather than assumed -- see PROGRESS.MD). Unlike the other
        # three, this isn't a new elemental damage_type: it reuses the
        # Viper's poison_chance/poison_damage/poison_duration mechanism
        # (session 21) as its breath weapon, so no combat.py changes were
        # needed here either. Same triangle silhouette, a saturated
        # forest/toxin green distinct from both the Slime's muted green
        # circle and the Viper's olive diamond.
        AssetManager.make_placeholder("enemy_green_dragon", (20, 150, 40), shape="triangle")
        # Session 47: the Elder Dragon -- the Final Area's guardian, a
        # deliberately tougher capstone fight rather than a rematch against
        # one of the four biome mini-bosses (see data/enemies.json). Same
        # triangle silhouette as its four younger kin (it reads as a dragon
        # at a glance, same reasoning as every other dragon placeholder
        # here), but a dark bronze/gold rather than any of the four
        # saturated elemental hues, so it's immediately distinct from all of
        # them rather than looking like a reused Red/White/Blue/Green.
        AssetManager.make_placeholder("enemy_elder_dragon", (140, 100, 30), shape="triangle")
        AssetManager.load_sprite("player", f"{C}/tile_12_6.png")
        AssetManager.load_sprite("npc_quartermaster", f"{C}/tile_12_12.png")
        AssetManager.load_sprite("npc_merchant", f"{C}/tile_12_27.png")
        AssetManager.load_sprite("npc_healer", f"{C}/tile_12_9.png")
        # Session 19: unarmored, no bow/helmet -- the one portrait in this
        # row that doesn't read as a fighter, picked (via a rendered/
        # labeled contact sheet, same discipline session 9 established) to
        # stand apart from the three already-placed NPCs at a glance.
        AssetManager.load_sprite("npc_scholar", f"{C}/tile_12_21.png")
        # Session 45: Frontier Guide -- no unused, distinct-enough portrait
        # left in the character sheet (session 9/19 already claimed the
        # readable ones for the other four town NPCs), so tint the
        # Quartermaster's own portrait an earthy frontier green rather than
        # reuse a portrait outright (same "no matching art, tint an
        # existing one" trick as the enemy sprites above).
        AssetManager.make_tint_variant("npc_guide", "npc_quartermaster", (110, 150, 90), strength=0.6)

        # Consumables: each minor/normal/greater tier is now real distinct
        # art (not a color-dot variant of one image like session 5's
        # placeholder-art era), picked for a visible size/quality
        # progression within the same item family.
        AssetManager.load_sprite("item_potion_minor", f"{I}/tile_37_11.png")
        AssetManager.load_sprite("item_potion", f"{I}/tile_40_6.png")
        AssetManager.load_sprite("item_potion_greater", f"{I}/tile_43_14.png")
        AssetManager.load_sprite("item_whetstone_minor", f"{I}/tile_2_9.png")
        AssetManager.load_sprite("item_whetstone", f"{I}/tile_2_5.png")
        AssetManager.load_sprite("item_whetstone_greater", f"{I}/tile_2_0.png")
        AssetManager.load_sprite("item_shield_minor", f"{I}/tile_72_9.png")
        AssetManager.load_sprite("item_shield", f"{I}/tile_71_4.png")
        AssetManager.load_sprite("item_shield_greater", f"{I}/tile_71_9.png")
        AssetManager.load_sprite("item_gold_minor", f"{I}/tile_32_2.png")
        AssetManager.load_sprite("item_gold", f"{I}/tile_32_1.png")
        AssetManager.load_sprite("item_gold_greater", f"{I}/tile_32_0.png")

        # Mana potions (session 12): no blue-potion art in the item sheet at
        # these tile coordinates, so derive them from the existing red health
        # potions the same way stairs_up/gate/locked_door already reuse one
        # base image via make_tint_variant, rather than hand-picking new
        # (unverified) sheet coordinates.
        AssetManager.make_tint_variant("item_mana_potion_minor", "item_potion_minor", (60, 110, 220))
        AssetManager.make_tint_variant("item_mana_potion", "item_potion", (60, 110, 220))
        AssetManager.make_tint_variant("item_mana_potion_greater", "item_potion_greater", (60, 110, 220))

        # Equipment: same "three real images per slot" approach.
        AssetManager.load_sprite("eq_weapon_basic", f"{I}/tile_108_9.png")
        AssetManager.load_sprite("eq_weapon", f"{I}/tile_107_1.png")
        AssetManager.load_sprite("eq_weapon_masterwork", f"{I}/tile_107_8.png")
        AssetManager.load_sprite("eq_shield_basic", f"{I}/tile_71_3.png")
        AssetManager.load_sprite("eq_shield", f"{I}/tile_71_6.png")
        AssetManager.load_sprite("eq_shield_masterwork", f"{I}/tile_71_12.png")
        AssetManager.load_sprite("eq_helmet_basic", f"{I}/tile_26_11.png")
        AssetManager.load_sprite("eq_helmet", f"{I}/tile_25_15.png")
        AssetManager.load_sprite("eq_helmet_masterwork", f"{I}/tile_25_7.png")
        AssetManager.load_sprite("eq_armor_basic", f"{I}/tile_3_11.png")
        AssetManager.load_sprite("eq_armor", f"{I}/tile_4_9.png")
        AssetManager.load_sprite("eq_armor_masterwork", f"{I}/tile_3_14.png")
        AssetManager.load_sprite("eq_boots_basic", f"{I}/tile_10_8.png")
        AssetManager.load_sprite("eq_boots", f"{I}/tile_11_8.png")
        AssetManager.load_sprite("eq_boots_masterwork", f"{I}/tile_10_12.png")
        # Session 18: ring/amulet slots. Sprites verified by rendering and
        # visually inspecting eval/_sheet.png before picking coordinates,
        # same discipline session 9 established -- rings live in the
        # sheet's dedicated jewelry rows (64/65/68), amulets in its pendant
        # row (0), both found by cropping and labeling candidate rows
        # rather than guessing from divisibility.
        AssetManager.load_sprite("eq_ring_might_basic", f"{I}/tile_65_6.png")
        AssetManager.load_sprite("eq_ring_might_fine", f"{I}/tile_64_10.png")
        AssetManager.load_sprite("eq_ring_might_masterwork", f"{I}/tile_68_15.png")
        AssetManager.load_sprite("eq_ring_warding_basic", f"{I}/tile_65_10.png")
        AssetManager.load_sprite("eq_ring_warding_fine", f"{I}/tile_64_7.png")
        AssetManager.load_sprite("eq_ring_warding_masterwork", f"{I}/tile_64_13.png")
        AssetManager.load_sprite("eq_amulet_basic", f"{I}/tile_0_3.png")
        AssetManager.load_sprite("eq_amulet_fine", f"{I}/tile_0_4.png")
        AssetManager.load_sprite("eq_amulet_masterwork", f"{I}/tile_0_5.png")

        for name in ("hit", "kill", "pickup", "levelup", "door"):
            AssetManager.load_sfx(name, f"assets/sfx/{name}.wav")

        AssetManager.get_font(14)
        AssetManager.get_font(16, bold=True)
        AssetManager.get_font(20, bold=True)

    # -- room lifecycle ----------------------------------------------------

    def _room_meta(self, room_id):
        """Lazily load (epoch, cleared_turn) for a Depths room from save,
        caching in memory so repeated lookups within a session don't hit
        the DB -- mutated in place by callers, flushed by persist()."""
        if room_id not in self.room_epoch:
            meta = self.save.get_room_meta(room_id)
            self.room_epoch[room_id] = meta["epoch"]
            self.room_cleared_turn[room_id] = meta["cleared_turn"]
        return self.room_epoch[room_id], self.room_cleared_turn[room_id]

    def _resize_room_surface(self):
        """Session 25 (UI pass): the room viewport is a fixed 640x512 box
        (the Depths' full ROOM_TILES_W x ROOM_TILES_H footprint), but every
        hand-authored room (Town Square, Armory, Crypt) is deliberately
        smaller than that -- session 10's Armory shrank to a "cozy 14x10
        shop interior" on purpose, for instance. Previously `room_surface`
        was one subsurface carved out at __init__ and never touched again,
        so a smaller room's undrawn tiles just stayed whatever
        draw()'s per-frame `fill((0, 0, 0))` left them: a solid black block
        in the bottom-right of the viewport, functionally identical to the
        dead window margins this session's other fix already removed, just
        one level down. Recreating the subsurface on every room transition
        (never per-frame -- consistent with everything else here that only
        recomputes on a room change) at exactly the room's own pixel size,
        centered in the fixed viewport, turns that into symmetric
        letterboxing against the frame border instead -- the actual
        playable area now fills its own bounds regardless of which room
        it's showing. self.room_draw_origin is the resulting screen-space
        offset; handle_room_click uses it (not the fixed ROOM_ORIGIN) to
        convert a click back to a room-local tile."""
        w = min(self.room.width * TILE_SIZE, ROOM_PIXEL_W)
        h = min(self.room.height * TILE_SIZE, ROOM_PIXEL_H)
        ox = ROOM_ORIGIN[0] + (ROOM_PIXEL_W - w) // 2
        oy = ROOM_ORIGIN[1] + (ROOM_PIXEL_H - h) // 2
        self.room_draw_origin = (ox, oy)
        self.room_surface = self.screen.subsurface(pygame.Rect(ox, oy, w, h))

    def load_room(self, room_id, spawn_x, spawn_y):
        self.current_room_id = room_id
        self.room = Room.load(room_id)
        self._resize_room_surface()

        flags = self.save.get_room_flags(room_id)
        dead_ids = set(flags.get("enemy_dead", set()))
        taken_ids = set(flags.get("item_taken", set()))
        # Session 10: region/door/gate/chest state is NOT epoch-suffixed
        # (see procgen.py's module docstring) -- once seen/solved, it
        # stays that way regardless of the room's enemy/item epoch below.
        self.revealed_regions = set(flags.get("region_seen", set()))
        self.unlocked_door_ids = set(flags.get("door_unlocked", set()))
        self.open_gate_ids = set(flags.get("gate_open", set()))
        self.opened_chest_ids = set(flags.get("chest_opened", set()))
        self.sprung_trap_ids = set(flags.get("trap_sprung", set()))

        if room_id.startswith("proc:"):
            _, _seed_str, level_str, gx_str, gy_str = room_id.split(":")
            level, gx, gy = int(level_str), int(gx_str), int(gy_str)

            if level not in self.discovered:
                self.discovered[level] = self.save.get_discovered_rooms(level)
            if (gx, gy) not in self.discovered[level]:
                self.discovered[level].add((gx, gy))
                self.save.mark_discovered(level, gx, gy)

            epoch, cleared_turn = self._room_meta(room_id)
            if cleared_turn is not None and self.turn_count - cleared_turn >= RESPAWN_THRESHOLD:
                epoch += 1
                cleared_turn = None
                dead_ids, taken_ids = set(), set()
                self.room_epoch[room_id] = epoch
                self.room_cleared_turn[room_id] = cleared_turn

            # Structure (layout/exits) is cached on self.room already;
            # this second generate_room call is only to fetch this epoch's
            # enemy/item rolls -- cheap (small fixed-size room), only runs
            # on room transitions, not the per-frame hot path.
            population = generate_room(self.seed, level, gx, gy, epoch)
            enemy_templates = population["enemies"]
            item_templates = population["items"]
            equipment_drop_templates = population["equipment_drops"]
            spellbook_drop_templates = population["spellbook_drops"]
        else:
            enemy_templates = self.room.enemy_templates
            item_templates = self.room.item_templates
            equipment_drop_templates = self.room.equipment_drop_templates
            spellbook_drop_templates = self.room.spellbook_drop_templates

        self.current_room_enemy_ids = {t["id"] for t in enemy_templates}
        self.dead_enemy_ids = dead_ids
        self.taken_item_ids = taken_ids

        # Structure (including locked_door/gate/switch/chest templates) is
        # cached on self.room and, like layout/exits, is never epoch-scoped
        # -- see procgen.py's module docstring -- so no second fetch is
        # needed here the way enemy/item population above needed one.
        self.locked_doors = [d for d in self.room.locked_door_templates if d["id"] not in self.unlocked_door_ids]
        self.gates = [g for g in self.room.gate_templates if g["id"] not in self.open_gate_ids]
        self.switches = list(self.room.switch_templates)
        self.chests = list(self.room.chest_templates)
        self.traps = list(self.room.trap_templates)
        self.plates = list(self.room.plate_templates)
        # Session 48: overlay any previously-pushed position on top of each
        # block's template starting position -- same "template is the
        # default, a per-room save table is the override" split room_drops
        # uses for taken/dropped items, just keyed by id instead of being a
        # simple add/remove list (a block always exists, it just may have
        # moved).
        pushed = self.save.get_block_positions(room_id)
        self.blocks = [
            {"id": t["id"], "x": t["x"], "y": t["y"]}
            for t in self.room.block_templates
        ]
        for block in self.blocks:
            if block["id"] in pushed:
                block["x"], block["y"] = pushed[block["id"]]

        self.enemies = []
        for t in enemy_templates:
            if t["id"] in self.dead_enemy_ids:
                continue
            stats = self.enemy_defs[t["type"]]
            if t.get("level", 1) > 1:
                stats = scale_stats_for_level(stats, t["level"])
            self.enemies.append(
                Enemy(t["id"], t["type"], t["x"], t["y"], stats, level=t.get("level", 1))
            )
        self.items = [
            ItemPickup(t["id"], t["type"], t["x"], t["y"], self.item_defs[t["type"]])
            for t in item_templates
            if t["id"] not in self.taken_item_ids
        ] + [
            # Session 16: dungeon-found gear lives on the floor the same way
            # a consumable does (walk onto it to pick it up -- see
            # Player.try_move's generic items collision check), just as a
            # distinct entity type so main.py's pickup handler can route it
            # to the per-instance equipment path instead of Inventory.
            EquipmentDrop(t["id"], t["base_type"], t["enchant"], t["x"], t["y"], self.equipment_defs[t["base_type"]])
            for t in equipment_drop_templates
            if t["id"] not in self.taken_item_ids
        ] + [
            # Session 39: dungeon-found spellbooks -- same floor-entity
            # split as EquipmentDrop above, just teaching a spell on pickup
            # instead of adding a per-instance gear record.
            SpellbookDrop(t["id"], t["spell_id"], t["x"], t["y"], self._spell_def(t["spell_id"]))
            for t in spellbook_drop_templates
            if t["id"] not in self.taken_item_ids
        ]
        # Session 43: consumables a player dropped from the Inventory panel
        # on a previous visit -- persisted per-room (see engine/save.py's
        # room_drops table) rather than a procgen template, so they survive
        # a room transition and back the same way taken/opened/sprung state
        # does. self.room_drops is the live in-memory copy this session
        # mutates on drop/pickup; flushed back alongside room_flags (see
        # persist() and the "exit"/Word of Recall room-transition sites).
        self.room_drops = self.save.get_room_drops(room_id)
        self.items += [
            ItemPickup(d["id"], d["type"], d["x"], d["y"], self.item_defs[d["type"]])
            for d in self.room_drops
        ]
        # NPCs never appear in proc rooms (self.room.npc_templates is
        # always [] there) and are never "dead" -- no flags to filter by.
        self.npcs = [
            NPC(t["id"], t["type"], t["x"], t["y"], self.npc_defs[t["type"]])
            for t in self.room.npc_templates
        ]

        self.player.x, self.player.y = spawn_x, spawn_y
        self._reveal_region_at_player()
        self.message_log = [f"Entered {self.room.name}."]
        self.dirty = True

    def _reveal_region_at_player(self):
        """Room-based fog of war (session 10): mark whichever region the
        player is physically standing on as seen. A no-op (region_at
        returns None) for any room with no `regions` defined, so simple
        hand-authored rooms are never fogged. Called on room entry and
        after every in-room move -- see handle_move."""
        region_id = self.room.region_at(self.player.x, self.player.y)
        if region_id is not None and region_id not in self.revealed_regions:
            self.revealed_regions.add(region_id)
            self.dirty = True

    def _is_visible(self, x, y, detect_turns=0):
        """Whether (x, y) is currently un-fogged -- used to gate rendering
        of enemies/items/npcs/fixtures the same way Room.draw() already
        gates tile rendering, so nothing in an unseen region is spoiled.
        detect_turns > 0 (session 15's Detect Monsters/Treasure) bypasses
        the fog check entirely -- callers pass the relevant counter only
        for the entity kinds that spell should reveal (enemies for
        detect_monsters_turns, items/chests for detect_treasure_turns);
        NPCs/switches/gates/locked doors always use the plain check."""
        if detect_turns > 0:
            return True
        if not self.room.regions:
            return True
        return self.room.is_revealed(x, y, self.revealed_regions)

    def _blocked_positions(self):
        """Currently-closed locked doors/gates, as a set of (x, y) --
        passed to Player.try_move/Room.is_walkable so a still-closed
        fixture blocks movement like a wall would. Session 48: also folds
        in every block's current position -- a block is a physical
        obstacle for enemy pathing, spell line-of-sight, and the player's
        own non-push movement, exactly like a locked gate, for every
        purpose *except* the player's own push (Player.try_move checks its
        own `blocks` list first, before ever consulting this set)."""
        return (
            {(d["x"], d["y"]) for d in self.locked_doors}
            | {(g["x"], g["y"]) for g in self.gates}
            | {(b["x"], b["y"]) for b in self.blocks}
        )

    def _locked_exits(self):
        """Session 45 (Wayfarer Adventure Mode biome-unlock gating): any
        exit in the current room tagged with a biome the current journey
        hasn't unlocked yet -- a world-map-scale switch-gated gate, per
        wayfarer_adventure.md's own framing. Deliberately separate from
        _blocked_positions() above: unlike a locked door, a gated exit tile
        is ordinary floor for every *other* purpose (enemy pathing, spell
        line-of-sight) -- only Player.try_move's own exit dispatch needs to
        know it isn't traversable yet.

        Session 52 swapped the tag from `requires_quest` (a hardcoded chain
        step id) to `requires_biome`, since a journey can now deal the
        biomes in any order and no single step id gates a given door
        anymore -- see unlocked_biomes()."""
        unlocked = self.unlocked_biomes()
        return [
            e for e in self.room.exits
            if e.get("requires_biome") and e["requires_biome"] not in unlocked
        ]

    def _current_room_flags(self):
        """All flag types tracked for the current room, in the generic
        {flag_type: {entity_id, ...}} shape save.set_room_flags expects."""
        return {
            "enemy_dead": self.dead_enemy_ids,
            "item_taken": self.taken_item_ids,
            "region_seen": self.revealed_regions,
            "door_unlocked": self.unlocked_door_ids,
            "gate_open": self.open_gate_ids,
            "chest_opened": self.opened_chest_ids,
            "trap_sprung": self.sprung_trap_ids,
        }

    def persist(self):
        """Full autosave: current room flags/meta + player + inventory.
        Called on room transition and on quit -- never per-frame."""
        self.save.set_room_flags(self.current_room_id, self._current_room_flags())
        self.save.set_room_drops(self.current_room_id, self.room_drops)
        self.save.set_block_positions(self.current_room_id, self.blocks)
        if self.current_room_id.startswith("proc:"):
            epoch, cleared_turn = self._room_meta(self.current_room_id)
            self.save.set_room_meta(self.current_room_id, epoch, cleared_turn)
        self.save.save_game(
            self.player, self.inventory, self.current_room_id, self.seed,
            self.turn_count, self.depths_kills, self.quest_index,
            self.known_spells, self.artifact_fragments,
            self.completed_adventure_quests,
            journey_index=self.journey_index,
            combat_difficulty=self.combat_difficulty,
            journeys_won=self.journeys_won,
            adventure_route=self.adventure_route,
        )

    # -- input handlers ------------------------------------------------

    def _advance_turn(self):
        """Every player action that counts as a turn (move, quick-use item,
        cast a spell) goes through here instead of touching turn_count
        directly, so the temporary-buff countdown (session 12) can never be
        threaded through only some of the call sites and drift out of sync.
        Returns any messages the tick itself generated (session 21's poison
        damage/wear-off) -- callers fold these into whatever message list
        they're building for this turn."""
        self.turn_count += 1
        if self.player.buff_defense_turns > 0:
            self.player.buff_defense_turns -= 1
            if self.player.buff_defense_turns == 0:
                self.player.buff_defense_bonus = 0
        if self.detect_monsters_turns > 0:
            self.detect_monsters_turns -= 1
        if self.detect_treasure_turns > 0:
            self.detect_treasure_turns -= 1
        if self.detect_traps_turns > 0:
            self.detect_traps_turns -= 1
        if self.player.levitation_turns > 0:
            self.player.levitation_turns -= 1
        if self.player.temp_resist_fire_turns > 0:
            self.player.temp_resist_fire_turns -= 1
            if self.player.temp_resist_fire_turns == 0:
                self.player.temp_resist_fire_bonus = 0
        if self.player.temp_resist_cold_turns > 0:
            self.player.temp_resist_cold_turns -= 1
            if self.player.temp_resist_cold_turns == 0:
                self.player.temp_resist_cold_bonus = 0
        if self.player.temp_resist_lightning_turns > 0:
            self.player.temp_resist_lightning_turns -= 1
            if self.player.temp_resist_lightning_turns == 0:
                self.player.temp_resist_lightning_bonus = 0

        messages = []
        if self.player.poison_turns > 0:
            self.player.poison_turns -= 1
            dmg = self.player.poison_damage
            self.player.hp = max(0, self.player.hp - dmg)
            messages.append(f"The poison saps {dmg} HP from you.")
            if self.player.poison_turns == 0:
                self.player.poison_damage = 0
                messages.append("The poison wears off.")
            if self.player.hp <= 0:
                messages.append("You succumb to the poison...")
        return messages

    def _learn_new_spells(self, messages):
        """Grants any spell whose unlock_level the player's current level
        now meets. Safe to call after any XP gain (or with messages=None at
        boot, to catch up silently) -- see engine.spells.newly_learned."""
        for spell in newly_learned(self.spell_defs, self.player.level, self.known_spells):
            self.known_spells.add(spell["id"])
            if messages is not None:
                messages.append(f"You have learned {spell['name']}!")

    def handle_move(self, dx, dy):
        if self.player.hp <= 0:
            return
        poison_msgs = self._advance_turn()
        if self.player.hp <= 0:
            # Poison finished the player off before the move itself ever
            # resolved -- don't also process an attack/npc-talk/exit this
            # turn, same "a dead player takes no further action" contract
            # the top-of-function guard above already enforces.
            self._handle_death(poison_msgs)
            return
        result = self.player.try_move(
            dx, dy, self.room, self.enemies, self.items, self.npcs,
            locked_doors=self.locked_doors, gates=self.gates,
            chests=self.chests, switches=self.switches, traps=self.traps,
            locked_exits=self._locked_exits(), blocks=self.blocks,
            blocked=self._blocked_positions(),
        )
        self._reveal_region_at_player()
        self.dirty = True
        kind = result["type"]
        messages = list(poison_msgs)

        if kind == "attack":
            enemy = result["enemy"]
            messages += resolve_bump_attack(self.player, enemy)
            self._learn_new_spells(messages)
            if not enemy.alive:
                self.dead_enemy_ids.add(enemy.id)
                self.enemies = [e for e in self.enemies if e.alive]
                if self.current_room_id.startswith("proc:"):
                    self.depths_kills += 1
                if (
                    self.current_room_id.startswith("proc:")
                    and self.current_room_enemy_ids
                    and self.current_room_enemy_ids <= self.dead_enemy_ids
                    and self.room_cleared_turn.get(self.current_room_id) is None
                ):
                    self.room_cleared_turn[self.current_room_id] = self.turn_count

        elif kind == "npc":
            npc = result["npc"]
            self.active_npc = npc
            self.message_log = messages + [npc.greeting]
            if npc.type == "merchant":
                self.shop_open = True
                self.shop_cursor = 0
            elif npc.type == "healer":
                self.healer_open = True
                self.healer_cursor = 0
            elif npc.type == "scholar":
                self.bookshop_open = True
                self.bookshop_cursor = 0
            elif npc.type == "guide":
                self.trade_open = True
                self.trade_cursor = 0
            else:
                self.quest_open = True
            return  # talking doesn't give nearby enemies a free turn

        elif kind == "pickup":
            item = result["item"]
            if isinstance(item, EquipmentDrop):
                # Session 16: lands in the bag unidentified -- the player
                # won't know its enchant/curse until it's equipped or paid
                # identification at the Merchant reveals it first. Never
                # stack/slot-limited by Inventory -- it's a separate bag,
                # see engine/equipment.py.
                create_instance(self.player, item.base_type, item.enchant, identified=False)
                self.taken_item_ids.add(item.id)
                self.items = [i for i in self.items if i.id != item.id]
                base_name = self.equipment_defs[item.base_type]["name"]
                messages.append(f"Found {base_name} (unidentified).")
                AssetManager.play_sfx("pickup")
            elif isinstance(item, SpellbookDrop):
                # Session 39: closes engine/spells.py's own "spellbooks as
                # dungeon loot" future-work note. Unlike EquipmentDrop, this
                # never enters an inventory/bag -- it teaches its spell
                # immediately, same as buy_spellbook, or (since procgen is a
                # pure function of seed/position with no live player state
                # to consult -- see procgen.py's SPELL_IDS_BY_BAND comment)
                # refunds half its book_cost in gold if the roll duplicated
                # an already-known spell rather than silently wasting it.
                self.taken_item_ids.add(item.id)
                self.items = [i for i in self.items if i.id != item.id]
                spell = self._spell_def(item.spell_id)
                if item.spell_id in self.known_spells:
                    refund = spell["book_cost"] // 2
                    self.player.gold += refund
                    messages.append(f"You already know {spell['name']} -- you sell the book for {refund} gold.")
                else:
                    self.known_spells.add(item.spell_id)
                    messages.append(f"You study a found spellbook and learn {spell['name']}!")
                AssetManager.play_sfx("pickup")
            else:
                item_def = self.item_defs[item.type]
                if item_def.get("effect") == "gold":
                    # Gold is never stack-limited by the 8-slot inventory --
                    # it's not a carried item, just a running total.
                    amount = item_def.get("value", 0)
                    self.player.gold += amount
                    self.taken_item_ids.add(item.id)
                    self.items = [i for i in self.items if i.id != item.id]
                    messages.append(f"Found {amount} gold.")
                    AssetManager.play_sfx("pickup")
                elif self.inventory.add_item(item.type):
                    self.taken_item_ids.add(item.id)
                    self.items = [i for i in self.items if i.id != item.id]
                    # Session 43: a no-op filter for a template item's id,
                    # but clears a player-dropped one back out of the
                    # persisted per-room drop list so it doesn't reappear
                    # after the room is left and re-entered.
                    self.room_drops = [d for d in self.room_drops if d["id"] != item.id]
                    messages.append(f"Picked up {item.name}.")
                    AssetManager.play_sfx("pickup")
                else:
                    # Session 54: session 53's Known Limitations note claimed
                    # this branch said nothing at all when the bag was full,
                    # which turned out to be wrong -- it has said "Inventory
                    # full." since session 1. What it didn't say is WHICH item
                    # it refused, which is the half of the complaint that
                    # survives verification: walking over a biome's colored
                    # vault key and reading a bare two-word status line does
                    # not connect the two. Named here, matching the chest
                    # branch's own wording two hundred lines below.
                    messages.append(f"Your pack is full -- no room for {item.name}.")

        elif kind == "locked_door":
            # Session 49 (Yoda Stories/Desktop Adventures -- see
            # wayfarer_adventure.md's "colored key/gate pairs" note, the
            # second half of the design doc's "puzzles as texture" line
            # left unbuilt after session 48's sokoban blocks): a door with
            # no "color" keeps the original session-10 behavior (any plain
            # "key" opens it). A colored door only accepts the
            # matching-colored key ("key_<color>") -- a wrong-colored key
            # stays in the bag, same as having no key at all.
            door = result["door"]
            color = door.get("color")
            needed_item = f"key_{color}" if color else "key"
            if self.inventory.remove_item(needed_item):
                self.unlocked_door_ids.add(door["id"])
                self.locked_doors = [d for d in self.locked_doors if d["id"] != door["id"]]
                if color:
                    messages.append(f"You unlock the {color} door with the matching key.")
                else:
                    messages.append("You unlock the door with a key.")
                AssetManager.play_sfx("door")
            elif color:
                messages.append(f"This door is banded in {color} -- you need a matching key.")
            else:
                messages.append("The door is locked. You need a key.")

        elif kind == "gate":
            # Session 48: a gate can now be triggered by either a switch
            # (step-on) or a plate (block-weight) -- kept generic rather
            # than naming "the switch" specifically, since bumping a closed
            # gate doesn't tell the player which kind of trigger it has.
            messages.append("An iron gate blocks the way. Something nearby must trigger it.")

        elif kind == "locked_exit":
            # Session 45 (Wayfarer Adventure Mode biome-unlock gating) --
            # same non-committal bump as a locked door/gate above, just
            # keyed by an adventure-quest id instead of an item/switch.
            messages.append("The way is sealed by old magic. Perhaps someone in town can help.")

        elif kind == "chest":
            chest = result["chest"]
            if chest["id"] in self.opened_chest_ids:
                pass  # already looted -- just a normal walk-through
            elif "artifact" in chest:
                # Wayfarer Adventure Mode (see wayfarer/wayfarer_adventure.md):
                # a biome dungeon's terminal reward. Never enters the
                # stackable Inventory or the equipment bag -- own exactly
                # one, ever, closer to how a spellbook teaches instantly
                # than to a regular chest item.
                fragment_id = chest["artifact"]["fragment_id"]
                self.opened_chest_ids.add(chest["id"])
                frag_name = self.artifact_defs[fragment_id]["name"]
                if fragment_id in self.artifact_fragments:
                    messages.append(f"The chest is empty -- you already claimed the {frag_name}.")
                else:
                    self.artifact_fragments.add(fragment_id)
                    messages.append(f"The chest holds {frag_name}!")
                    AssetManager.play_sfx("pickup")
            elif chest.get("final_reward"):
                # Session 47: the Final Area's win trigger (see
                # engine/procgen.py's BIOME_DEFS["final_area"] and
                # _vault_reward). "adventure_victory" is a synthetic id --
                # never an entry in data/adventure_quests.json -- added to
                # the same completed_adventure_quests set the fetch/trade
                # chain already uses purely so this fact persists without a
                # new save table; current_adventure_quest()'s own front-scan
                # only ever checks the real chain ids, so an extra id in the
                # set is otherwise inert.
                # Session 52: the id is journey-scoped (journey 1 still uses
                # the bare legacy "adventure_victory", so an already-won save
                # still reads as won), and winning bumps journeys_won -- the
                # one fact about a finished journey that has to outlive the
                # journey itself, since starting a new one is what makes the
                # frontier winnable again.
                self.opened_chest_ids.add(chest["id"])
                victory_id = self._journey_id("adventure_victory")
                if victory_id in self.completed_adventure_quests:
                    messages.append("The chest is empty -- you have already claimed your victory.")
                else:
                    self.completed_adventure_quests.add(victory_id)
                    self.journeys_won += 1
                    # Session 53: "all four" is only true on the straight-line
                    # route -- an Open Frontier journey breaks the seal with
                    # three, and may never have visited the fourth biome.
                    # Session 54: counted off what's actually in the bag
                    # rather than off the route, because the route only sets a
                    # floor -- a Short Road player who walked the optional
                    # last leg lays four on a route that asked for three, and
                    # the old wording called that three.
                    carried = len(self.artifact_fragments)
                    count_word = NUMBER_WORDS.get(carried, str(carried))
                    lay = "all four" if carried >= len(self.artifact_defs) else count_word
                    messages.append(f"You lay {lay} fragments together and the old seal finally breaks.")
                    self.win_screen_open = True
                    AssetManager.play_sfx("pickup")
            elif "equipment" in chest:
                # Session 17: a vault chest can hold a per-instance gear
                # drop, same as floor loot -- lands unidentified in the bag,
                # never slot-limited (see the pickup branch above, which
                # this mirrors exactly).
                eq = chest["equipment"]
                create_instance(self.player, eq["base_type"], eq["enchant"], identified=False)
                self.opened_chest_ids.add(chest["id"])
                base_name = self.equipment_defs[eq["base_type"]]["name"]
                messages.append(f"The chest holds {base_name} (unidentified)!")
                AssetManager.play_sfx("pickup")
            elif "spellbook" in chest:
                spell_id = chest["spellbook"]["spell_id"]
                spell = self._spell_def(spell_id)
                self.opened_chest_ids.add(chest["id"])
                if spell_id in self.known_spells:
                    refund = spell["book_cost"] // 2
                    self.player.gold += refund
                    messages.append(f"The chest holds a spellbook, but you already know {spell['name']} -- {refund} gold instead.")
                else:
                    self.known_spells.add(spell_id)
                    messages.append(f"The chest holds a spellbook! You learn {spell['name']}!")
                AssetManager.play_sfx("pickup")
            else:
                item_type = chest["item_type"]
                item_def = self.item_defs[item_type]
                if item_def.get("effect") == "gold":
                    amount = item_def.get("value", 0)
                    self.player.gold += amount
                    self.opened_chest_ids.add(chest["id"])
                    messages.append(f"The chest holds {amount} gold!")
                    AssetManager.play_sfx("pickup")
                elif self.inventory.add_item(item_type):
                    self.opened_chest_ids.add(chest["id"])
                    messages.append(f"The chest holds {item_def['name']}!")
                    AssetManager.play_sfx("pickup")
                else:
                    messages.append("The chest is full of treasure, but your pack is full.")

        elif kind == "switch":
            gate_id = result["switch"]["gate_id"]
            if gate_id not in self.open_gate_ids:
                self.open_gate_ids.add(gate_id)
                self.gates = [g for g in self.gates if g["id"] != gate_id]
                messages.append("You hear a distant mechanism unlock.")
                AssetManager.play_sfx("door")

        elif kind == "push_block":
            # Session 48 (Yoda Stories/Desktop Adventures' own "push/pull
            # blocks onto a marked square" puzzles -- see
            # wayfarer_adventure.md): the block itself already occupies the
            # tile the player just stepped into their own try_move call, so
            # only the block's *new* position needs updating here.
            # self.blocks is mutated here but only flushed to
            # engine/save.py's block_positions table at the same three
            # checkpoints self.room_drops already flushes at (persist(),
            # the "exit" stairs/door branch, Word of Recall) -- same
            # in-memory-first convention session 43 established.
            block = result["block"]
            to_x, to_y = result["to"]
            block["x"], block["y"] = to_x, to_y
            plate = next((p for p in self.plates if p["x"] == to_x and p["y"] == to_y), None)
            if plate is not None and plate["gate_id"] not in self.open_gate_ids:
                self.open_gate_ids.add(plate["gate_id"])
                self.gates = [g for g in self.gates if g["id"] != plate["gate_id"]]
                messages.append("The block settles onto the plate -- a distant mechanism unlocks.")
                AssetManager.play_sfx("door")
            else:
                messages.append("You shove the block forward.")

        elif kind == "trap":
            trap = result["trap"]
            if trap["id"] not in self.sprung_trap_ids:
                self.sprung_trap_ids.add(trap["id"])
                messages += resolve_trap(self.player, self.trap_defs[trap["type"]], [])
            # else: already sprung -- just a normal walk-through, same as
            # re-entering an opened chest's tile.

        elif kind == "exit":
            AssetManager.play_sfx("door")
            exit_data = result["exit"]
            target_room = exit_data["target_room"]
            if target_room == "proc:ENTRY":
                target_room = f"proc:{self.seed}:1:0:0"
            elif target_room.startswith("biome:ENTRY:"):
                # Wayfarer Adventure Mode: town_hub.json can't know the
                # per-save seed ahead of time, same "ENTRY" sentinel trick
                # as the Crypt's proc:ENTRY above. Session 52: it can't know
                # the journey's world seed or difficulty either, so the whole
                # id is built by biome_room_id().
                biome_id = target_room.split(":")[2]
                target_room = self.biome_room_id(biome_id)
            stairs_message = {
                "stairs_down": "You descend deeper into the dungeon.",
                "stairs_up": "You climb back up.",
            }.get(exit_data.get("kind"))
            # Flush the room we're leaving *before* load_room overwrites
            # this state with the destination's.
            self.save.set_room_flags(self.current_room_id, self._current_room_flags())
            self.save.set_room_drops(self.current_room_id, self.room_drops)
            self.save.set_block_positions(self.current_room_id, self.blocks)
            if self.current_room_id.startswith("proc:"):
                epoch, cleared_turn = self._room_meta(self.current_room_id)
                self.save.set_room_meta(self.current_room_id, epoch, cleared_turn)
            self.load_room(target_room, exit_data["target_x"], exit_data["target_y"])
            # load_room already set self.message_log to ["Entered <room>."];
            # prepend this turn's poison tick (if any) and the stairs
            # message (if any) in front of it, rather than replacing it.
            self.message_log = messages + ([stairs_message] if stairs_message else []) + self.message_log
            # Autosave now, with current_room_id/player pos already pointing
            # at the room we just entered -- reload should resume *there*,
            # not at the previous room's doorway.
            self.persist()
            return  # entering a room is its own turn; enemies there haven't seen us yet

        # "blocked" and "moved" fall through with no extra messages, but
        # still consume a turn -- monsters get to act on every player input.
        self._take_turn(messages)

    def attempt_disarm(self):
        """Session 29: Castle of the Winds' Disarm Trap command -- targets
        whatever's directly ahead of the player (`Player.facing`, the same
        "ahead of you" targeting a bolt spell already uses) rather than
        requiring the player to walk onto the trap the way an un-disarmed
        one is always sprung. Deliberately bound to a different key than the
        real game's 'd' -- that's already WASD-right movement here (see
        MOVE_KEYS). Only ever resolves against an already-*detected* trap
        (Detect Traps must be active): an undetected trap in front of the
        player must look identical to no trap at all, or the message itself
        would leak information the fog/detection system is built to hide."""
        if self.player.hp <= 0:
            return
        fx, fy = self.player.facing
        tx, ty = self.player.x + fx, self.player.y + fy
        target = None
        if self.detect_traps_turns > 0:
            target = next(
                (t for t in self.traps if t["x"] == tx and t["y"] == ty
                 and t["id"] not in self.sprung_trap_ids),
                None,
            )
        if target is None:
            self.message_log = ["There's nothing to disarm there."]
            self.dirty = True
            return

        poison_msgs = self._advance_turn()
        if self.player.hp <= 0:
            self._handle_death(poison_msgs)
            return
        messages = list(poison_msgs)
        self.sprung_trap_ids.add(target["id"])
        _, messages = resolve_disarm(self.player, self.trap_defs[target["type"]], messages)
        self._learn_new_spells(messages)
        self.dirty = True
        self._take_turn(messages)

    def field_rest(self):
        """Session 30: Castle of the Winds' free in-place Rest command --
        advance turns doing nothing but trickling back HP/mana until both
        are full, a safety cap is hit, or the player dies to poison mid-rest
        (poison still ticks every turn, same as any other action). Blocked
        outright while a living enemy shares the room: resting is turn-based
        and single-room, so nothing could wander in mid-rest that wasn't
        already here -- the check only needs to happen once, up front, not
        per simulated turn. Distinct from the Healer's rest_at_healer()
        (session 15/24), which is instant and full but costs gold instead of
        game time."""
        if self.player.hp <= 0:
            return
        if self.enemies:
            self.message_log = ["You can't rest with enemies nearby."]
            self.dirty = True
            return
        if self.player.hp >= self.player.max_hp and self.player.mana >= self.player.effective_max_mana():
            self.message_log = ["Already at full strength."]
            self.dirty = True
            return

        messages = []
        turns_rested = 0
        for _ in range(REST_MAX_TURNS):
            poison_msgs = self._advance_turn()
            turns_rested += 1
            messages += poison_msgs
            if self.player.hp <= 0:
                self._handle_death(messages)
                return
            self.player.hp = min(self.player.max_hp, self.player.hp + REST_HEAL_PER_TURN)
            self.player.mana = min(self.player.effective_max_mana(), self.player.mana + REST_MANA_PER_TURN)
            if self.player.hp >= self.player.max_hp and self.player.mana >= self.player.effective_max_mana():
                break

        messages.append(f"You rest for {turns_rested} turn{'s' if turns_rested != 1 else ''} and recover some strength.")
        self._learn_new_spells(messages)
        self.dirty = True
        self._take_turn(messages)

    def _take_turn(self, messages):
        """Common tail end of any player action that doesn't change rooms:
        run enemy AI, then either apply the result or handle player death."""
        if self.player.hp > 0:
            messages += self._run_enemy_turns()

        if self.player.hp <= 0:
            self._handle_death(messages)
        elif messages:
            # Trimmed to LOG_MAX_LINES raw messages -- generous now that
            # _draw_message_log has a box tall enough to show that many
            # (session 25); wrapping can still spread a single long message
            # across multiple visual lines, but that's handled at render
            # time, not here.
            self.message_log = messages[-LOG_MAX_LINES:]

    def _run_enemy_turns(self):
        messages = []
        blocked = self._blocked_positions()
        for enemy in list(self.enemies):
            if not enemy.alive:
                continue
            occupied = {(e.x, e.y) for e in self.enemies if e is not enemy and e.alive}
            occupied |= {(n.x, n.y) for n in self.npcs}
            occupied |= blocked
            action = enemy.take_turn(self.player, self.room, occupied)
            if action["type"] == "attack":
                messages += enemy_attack(enemy, self.player)
                if self.player.hp <= 0:
                    break
        return messages

    def _handle_death(self, prior_messages=None):
        saved = self.save.load_game()
        if saved is None:
            target_room, (target_x, target_y) = self.current_room_id, (self.player.x, self.player.y)
        else:
            target_room, (target_x, target_y) = saved["current_room"], saved["pos"]
        self.player.hp = self.player.max_hp
        # Session 21: a revive shouldn't leave the player still poisoned --
        # otherwise the very next tick could kill them again before they've
        # even taken a step, with no fight to have caused it.
        self.player.poison_turns = 0
        self.player.poison_damage = 0
        self.load_room(target_room, target_x, target_y)
        death_msg = "You have fallen. Reviving at your last save..."
        self.message_log = ((prior_messages or []) + [death_msg])[-LOG_MAX_LINES:]

    def toggle_inventory(self):
        self.inventory_open = not self.inventory_open
        self.inventory_cursor = 0
        self.dirty = True

    def _inventory_rows(self):
        """Combined list backing the Inventory panel's Up/Down cursor and
        U/click action (session 16): consumable stacks first (unchanged
        indices, so the existing 1-8 field hotkey range is untouched), then
        unequipped found gear appended after -- lets Up/Down/U reach both
        without a second keybinding namespace. Field quick-use (1-8, see
        quick_use_item) deliberately stays scoped to consumables only via
        _use_item_at_index below -- equipping (and risking a curse) is a
        panel-only action, never a stray field hotkey away."""
        rows = [("item", item_type, count, item_def) for item_type, count, item_def in self.inventory.as_list()]
        rows += [("gear", inst) for inst in bag_instances(self.player)]
        return rows

    def inventory_move_cursor(self, delta):
        rows = self._inventory_rows()
        if not rows:
            return
        self.inventory_cursor = (self.inventory_cursor + delta) % len(rows)
        self.dirty = True

    def _use_item_at_index(self, index):
        """Consumables only, bounded to Inventory's own list -- see
        quick_use_item, the field-hotkey path this feeds."""
        items = self.inventory.as_list()
        if index >= len(items):
            return None
        item_type, _count, _def = items[index]
        _success, message = self.inventory.use_item(item_type, self.player)
        return message

    def _activate_inventory_row(self, index):
        """Panel-only U/click/Enter action across the combined consumable +
        found-gear list (see _inventory_rows). Equipping unidentified gear
        reveals it on the spot -- and if it turns out cursed, whatever was
        in that slot before is what refuses to come off, not the new item."""
        rows = self._inventory_rows()
        if index >= len(rows):
            return None
        row = rows[index]
        if row[0] == "item":
            _, item_type, _count, _def = row
            _success, message = self.inventory.use_item(item_type, self.player)
            return message

        _, instance = row
        slot = self.equipment_defs[instance["base_type"]]["slot"]
        result = equip_item(self.player, self.equipment_defs, instance["instance_id"])
        if result == "cursed":
            stuck = self.player.equipment_instances[self.player.equipment[slot]]
            return f"Cannot remove {equip_display_name(self.equipment_defs, stuck)} -- it's cursed!"
        return f"Equipped {equip_display_name(self.equipment_defs, instance)}."

    def use_selected_item(self):
        message = self._activate_inventory_row(self.inventory_cursor)
        if message is None:
            return
        self.message_log = [message]
        remaining = self._inventory_rows()
        self.inventory_cursor = min(self.inventory_cursor, max(0, len(remaining) - 1))
        self.dirty = True

    def drop_selected_item(self):
        """Session 43: X in the Inventory panel drops one unit of the
        consumable under the cursor onto the player's own tile, closing
        out PROGRESS.MD's "No drop mechanics for consumables" future-work
        note. Scoped to consumables only, same line _use_item_at_index/
        _activate_inventory_row already draw -- found/equipped gear stays
        bag-only, no drop path for an EquipmentInstance. Persisted per-room
        (self.room_drops, flushed to engine/save.py's room_drops table
        alongside room_flags) so it's still on the floor after leaving the
        room and coming back, and picked back up the same way any other
        floor item is (see the "pickup" branch in handle_move)."""
        rows = self._inventory_rows()
        if self.inventory_cursor >= len(rows) or rows[self.inventory_cursor][0] != "item":
            return
        _, item_type, _count, item_def = rows[self.inventory_cursor]
        if not self.inventory.remove_item(item_type):
            return
        entity_id = f"drop:{uuid.uuid4().hex}"
        x, y = self.player.x, self.player.y
        self.room_drops.append({"id": entity_id, "type": item_type, "x": x, "y": y})
        self.items.append(ItemPickup(entity_id, item_type, x, y, item_def))
        self.message_log = [f"Dropped {item_def.get('name', item_type)}."]
        remaining = self._inventory_rows()
        self.inventory_cursor = min(self.inventory_cursor, max(0, len(remaining) - 1))
        self.dirty = True

    def select_inventory_slot(self, index):
        if index < len(self.inventory.as_list()):
            self.inventory_cursor = index
            self.dirty = True

    def quick_use_item(self, index):
        """Field hotkey (1-8): use an item without opening the inventory
        screen. Consumes a turn just like a move, so drinking a potion
        mid-fight still gives the enemy a chance to act."""
        if self.player.hp <= 0 or self.inventory_open:
            return
        message = self._use_item_at_index(index)
        if message is None:
            return
        poison_msgs = self._advance_turn()
        self.dirty = True
        self._take_turn(poison_msgs + [message])

    # -- quests ----------------------------------------------------------

    def current_quest(self):
        if self.quest_index < len(self.quests):
            return self.quests[self.quest_index]
        return None

    def close_quest_panel(self):
        self.quest_open = False
        self.dirty = True

    def claim_quest_reward(self):
        quest = self.current_quest()
        if quest is None or self.depths_kills < quest["target"]:
            return

        if quest["reward_type"] == "item":
            item_type = quest["reward_item"]
            if not self.inventory.add_item(item_type):
                self.message_log = ["Inventory full -- come back when you have room."]
                self.dirty = True
                return
            message = f"Quest complete! Received {self.item_defs[item_type]['name']}."
        else:
            log = []
            grant_xp(self.player, quest["reward_xp"], log)
            self._learn_new_spells(log)
            message = "Quest complete! " + " ".join(log)

        self.quest_index += 1
        self.message_log = [message]
        self.dirty = True

    # -- adventure quest chain (session 45, see wayfarer_adventure.md) ----
    #
    # A separate, ordered chain from the cull-quest ladder above -- ids in
    # data/adventure_quests.json are scanned front-to-back for the first
    # one not yet in self.completed_adventure_quests, same "index-shaped"
    # linear-chain MVP the design doc scopes for a first pass, just backed
    # by a persisted set (per the doc's own schema) rather than a bare int
    # so a future branching chain isn't blocked on this session's data
    # shape.

    # -- journeys (session 52, Yoda Stories' "New World" option) ----------
    #
    # A journey is one run through Adventure Mode: one shuffled biome order,
    # one world seed, one chosen combat difficulty. Journey 1 is the run
    # every existing save is already on, and is deliberately identical in
    # every respect to what sessions 44-51 shipped (see the three helpers
    # below, each of which special-cases 1 to a no-op) -- so this session
    # adds a replay path without retroactively changing anyone's in-progress
    # frontier. The Depths are untouched by all of this; a journey only ever
    # governs the biome wing.

    def _journey_id(self, base):
        """Namespace a quest id to the current journey. Journey 1 keeps the
        bare legacy id (`guide_frostreach`, `adventure_victory`, ...) so an
        existing save's completed_adventure_quests rows still match; every
        later journey prefixes, so the same four steps can be completed
        again without a destructive clear of the persisted set."""
        return base if self.journey_index <= 1 else f"j{self.journey_index}:{base}"

    def journey_world_seed(self):
        """The seed the current journey's biome dungeons generate from.
        Journey 1 is the character's own dungeon seed -- i.e. exactly the
        biome rooms an existing save already has, with the exact room ids it
        already has flags persisted against. Later journeys derive a fresh
        one, so their dungeons are genuinely new worlds (new layouts, new
        vaults, new push-block puzzles) whose entity ids can never collide
        with an abandoned journey's."""
        if self.journey_index <= 1:
            return self.seed
        return random.Random(f"{self.seed}:journey:{self.journey_index}").randrange(2 ** 31)

    def journey_enemy_level(self):
        return difficulty_def(self.combat_difficulty)["enemy_level"]

    def biome_room_id(self, biome_id):
        """"biome:<id>:<world_seed>[:<enemy_level>]" -- the level segment is
        omitted at difficulty 1 so journey-1 ids are byte-identical to the
        pre-session-52 format (see engine/room.py's own note)."""
        room_id = f"biome:{biome_id}:{self.journey_world_seed()}"
        enemy_level = self.journey_enemy_level()
        return room_id if enemy_level <= 1 else f"{room_id}:{enemy_level}"

    def journey_biome_order(self):
        """The biomes in the order this journey's chain visits them.
        Journey 1 uses the authored order (Scorched Wastes -> Frostreach ->
        Stormfell -> Fenmire), for two reasons: an in-progress save must not
        have its world resequenced underneath it on load, and a first
        playthrough is better as the curated one. Shuffling -- the design
        doc's own "randomized per-playthrough chains" stretch goal, and the
        "new story" half of Yoda Stories' New World -- starts at journey 2."""
        biomes = list(self.adventure_quest_defs["chain_biomes"])
        if self.journey_index > 1:
            random.Random(f"{self.seed}:chain:{self.journey_index}").shuffle(biomes)
        return biomes

    def route_def(self, route_id=None):
        """Look up a route row from data/adventure_quests.json, falling back
        to the first (the straight-line Old Road) rather than raising -- same
        degrade-don't-crash contract difficulty_def() already has for a save
        carrying an id this build no longer defines."""
        routes = self.adventure_quest_defs["routes"]
        wanted = route_id or self.adventure_route
        for entry in routes:
            if entry["id"] == wanted:
                return entry
        return routes[0]

    def _build_adventure_chain(self):
        """Assemble the ordered fetch/trade chain for the current journey,
        in exactly the shape sessions 45-47 hand-authored into
        adventure_quests.json (id/giver_npc/biome/wants/gives/dialogue), so
        current_adventure_quest/attempt_trade/_draw_trade_panel needed no
        changes to consume it.

        Step i wants the fragment guarded by biome i and unlocks biome i+1;
        the last step unlocks the Final Area. A step's id is named for the
        biome it *unlocks*, not its position -- which is what makes journey
        1's ids come out as the legacy `guide_frostreach`/`guide_stormfell`/
        `guide_fenmire`/`guide_final`, and what keeps an id meaningful when
        a later journey deals the same biomes in a different order.

        Session 53: that's the `old_road` route. On `open_frontier` the same
        four biome steps exist but none of them unlocks anything (every
        frontier is open from the start, see unlocked_biomes) and none of
        them is the final step -- a fifth, biome-less step wanting *any*
        three fragments is what opens the Final Area, which is what makes
        one biome genuinely optional. That's wayfarer_adventure.md's own
        never-built "any 2 of 3 fragments unlock the final area" branch,
        scaled to the four biomes that actually shipped. An open-route step
        is named for its SOURCE (`guide_from_fenmire`) rather than what it
        unlocks, since it unlocks nothing; only journeys >= 2 can ever be on
        this route, so `_journey_id` prefixes them all and they can never
        collide with a legacy id.

        Session 54: `chained` and `required_fragments` are independent knobs
        rather than two names for one shape. The single decision that used to
        entangle them is `seal_rides_last_step` below -- session 53 hung the
        Final Area off the last biome step for *every* chained route, which
        silently forces the seal to cost every fragment (you cannot reach the
        last step without having walked all the others). It now does that
        only when a chained route also wants every fragment, which is exactly
        the legacy Old Road and is why journey 1's chain is unchanged; any
        other combination gets the biome-less counting seal step instead. A
        biome step's dialogue follows from what it actually does rather than
        from the route's name: `step_*` when it opens another frontier,
        `final_*` for the legacy seal-bearing last step, `open_*` when it
        opens nothing and only counts toward the seal (which is the Short
        Road's last leg as much as any Open Frontier step)."""
        defs = self.adventure_quest_defs
        templates = defs["templates"]
        biome_text = defs["biomes"]
        order = self.journey_biome_order()
        final_biome = defs["final_biome"]
        giver = defs["giver_npc"]
        route = self.route_def()
        # Merged into every template's fields, so route-aware phrasing ("the
        # seal answers to three fragments, not all four") is authored in the
        # JSON rather than assembled in code. The old_road templates simply
        # don't reference them.
        counts = {
            "required_fragments": route["required_fragments"],
            "total_fragments": len(order),
            "final_name": BIOME_DEFS[final_biome]["name"],
        }

        def dialogue(prefix, fields):
            # Session 54: a template that opens on a spliced-in `{source_prose}`
            # ("the Frostreach still keeps what it keeps") starts its sentence
            # on a lowercase article, since the biome prose is authored to sit
            # mid-sentence everywhere else. Capitalizing the first character
            # here fixes every such line at once and is a no-op on every
            # template that already opens on authored prose -- including all
            # four of journey 1's, which is why its chain is unchanged.
            return {
                key: _capitalize_first(templates[f"{prefix}_{key}"].format(**fields, **counts))
                for key in ("intro", "incomplete", "success")
            }

        # Whether the last biome step is itself what opens the Final Area
        # (the Old Road's shape since session 45) or whether the seal is its
        # own biome-less step wanting a count. See the docstring: this is the
        # one line that used to read `route["chained"]` and thereby pinned
        # the seal's cost to the route's shape.
        seal_rides_last_step = route["chained"] and route["required_fragments"] >= len(order)

        chain = []
        for i, source in enumerate(order):
            fragment_id = BIOME_DEFS[source]["fragment_id"]
            fields = {
                "source_name": BIOME_DEFS[source]["name"],
                "fragment_name": self.artifact_defs[fragment_id]["name"],
                **{f"source_{k}": v for k, v in biome_text.get(source, {}).items()},
            }
            step = {
                "giver_npc": giver,
                "biome": source,
                "wants": {"type": "artifact", "id": fragment_id},
            }
            is_last = i == len(order) - 1
            if route["chained"] and (not is_last or seal_rides_last_step):
                is_final = is_last and seal_rides_last_step
                target = final_biome if is_final else order[i + 1]
                fields["target_name"] = BIOME_DEFS[target]["name"]
                fields.update({f"target_{k}": v for k, v in biome_text.get(target, {}).items()})
                step["id"] = self._journey_id("guide_final" if is_final else f"guide_{target}")
                step["gives"] = {"type": "unlock_biome", "id": target}
                step["dialogue"] = dialogue("final" if is_final else "step", fields)
            else:
                step["id"] = self._journey_id(f"guide_from_{source}")
                step["gives"] = None
                step["dialogue"] = dialogue("open", fields)
            chain.append(step)

        if not seal_rides_last_step:
            chain.append({
                "id": self._journey_id("guide_final"),
                "giver_npc": giver,
                # No source biome: this step is offered from the first day
                # (see available_adventure_quests) and is gated purely by
                # what's in the bag, so the player can see the finish line --
                # and how many fragments it costs -- before choosing which
                # frontiers to walk.
                "biome": None,
                "wants": {"type": "fragments", "count": route["required_fragments"]},
                "gives": {"type": "unlock_biome", "id": final_biome},
                # Session 54: "any 3 of 4" and "all 4" are different
                # sentences, not the same one with a number swapped -- an
                # openfinal line promising it's "yours to say which" is a lie
                # on a route that wants every fragment.
                "dialogue": dialogue(
                    "openfinal" if route["required_fragments"] < len(order) else "fullfinal",
                    {},
                ),
            })
        return chain

    def unlocked_biomes(self):
        """Which biome entrances the town hub will let the player through
        right now. The journey's first biome is always open (nothing gates
        the start of a chain); everything else opens when the step that
        `gives` it is complete. Session 45 gated exits on a hardcoded quest
        id instead -- that stopped working once a journey could deal the
        biomes in any order, since `to_frostreach` is only the second stop
        on journey 1.

        Session 53: on the Open Frontier route every biome starts unlocked
        -- the route's whole point is that the four frontiers are walked in
        whatever order the player likes -- and only the Final Area is still
        gated, by the biome-less step that wants three fragments."""
        order = self.journey_biome_order()
        unlocked = {order[0]} if self.route_def()["chained"] else set(order)
        for step in self.adventure_chain:
            if step["id"] in self.completed_adventure_quests and step.get("gives"):
                unlocked.add(step["gives"]["id"])
        return unlocked

    def journey_route_summary(self, with_final=False):
        """How this journey's frontiers are named in one line, for the
        Journal and the New Journey panel. Session 53: an Open Frontier
        journey has no fixed order to arrow through, so its biomes are joined
        with commas and flagged "any order" -- writing "A > B > C" for a route
        that doesn't work that way would be actively misleading, and the
        Journal is the only place a player reads their route off."""
        route = self.route_def()
        names = [BIOME_DEFS[b]["name"] for b in self.journey_biome_order()]
        if route["chained"]:
            # Session 54: on a chained route that wants fewer fragments than
            # there are biomes (the Short Road), the arrows alone claim every
            # leg is mandatory. The trailing legs the seal doesn't need are
            # marked, since the whole point of the route is that they're the
            # player's to skip -- the fragment count in the Journal's next
            # line says how many, but not which.
            for i in range(route["required_fragments"], len(names)):
                names[i] += " (optional)"
            summary = " > ".join(names)
        else:
            summary = ", ".join(names) + " (any order)"
        if with_final:
            summary += f" > {BIOME_DEFS[self.adventure_quest_defs['final_biome']]['name']}"
        return summary

    def journey_won(self):
        return self._journey_id("adventure_victory") in self.completed_adventure_quests

    def available_adventure_quests(self):
        """Every chain step the Guide can offer right now -- incomplete, and
        either biome-less (the Open Frontier's final step, always offered) or
        sourced from a biome the player can actually reach.

        Session 53: this replaces current_adventure_quest()'s original
        front-scan of the whole chain, and is what a genuine branch needed --
        several steps can be live at once. On the straight-line Old Road it
        still yields exactly one at a time and in the same order, because
        biome i+1 only unlocks when step i completes; that equivalence is
        why nothing about journey 1 changed."""
        unlocked = self.unlocked_biomes()
        return [
            quest for quest in self.adventure_chain
            if quest["id"] not in self.completed_adventure_quests
            and (quest["biome"] is None or quest["biome"] in unlocked)
        ]

    def current_adventure_quest(self):
        offers = self.available_adventure_quests()
        return offers[0] if offers else None

    def wants_satisfied(self, quest):
        """Whether the bag holds what a step asks for. Two want-types since
        session 53: a named `artifact` fragment (every biome step, and the
        Old Road's own final step) or a `fragments` COUNT -- any N of them,
        which is the Open Frontier's "it's yours to say which three." The
        count form only works because a trade never consumes the fragment it
        was shown (session 45's deliberate departure from the source games)."""
        wants = quest["wants"]
        if wants["type"] == "fragments":
            return len(self.artifact_fragments) >= wants["count"]
        return wants["id"] in self.artifact_fragments

    def wants_label(self, quest):
        wants = quest["wants"]
        if wants["type"] == "fragments":
            # Session 54: "any 4 fragments" is technically true of a route
            # that wants all four and reads as a bug -- there is nothing to
            # choose. The count-want covers both cases now, so the label has
            # to as well.
            if wants["count"] >= len(self.artifact_defs):
                return f"all {wants['count']} fragments"
            return f"any {wants['count']} fragments"
        return self.artifact_defs[wants["id"]]["name"]

    def _carry_line(self, quest):
        """The trade panel's "yes, you have it" line. Kept separate from
        wants_label because the count-want reads naturally as a noun phrase
        in a list row ("any 3 fragments") but not in this sentence."""
        wants = quest["wants"]
        if wants["type"] == "fragments":
            return f"You carry {len(self.artifact_fragments)} fragments -- enough."
        return f"You carry the {self.artifact_defs[wants['id']]['name']}."

    def start_new_journey(self, difficulty_id, route_id=None):
        """Yoda Stories' "New World -- builds a new world with a new story,
        which discards the current world." Discards, here, means: the biome
        wing is re-rolled (new world seed, new biome order, new difficulty)
        and the fragments in the bag are surrendered to the Guide. It does
        NOT touch the character (level/gear/gold/spells), the Depths, or the
        cull-quest ladder -- Adventure Mode has always been a wing of the
        game rather than the whole of it, and a journey resets that wing
        only.

        Nothing is deleted from the save. Past journeys' completed steps stay
        in completed_adventure_quests (their ids are journey-scoped, so they
        can't satisfy the new journey's steps) and past journeys' biome rooms
        keep their room_flags rows against ids the new journey will never
        generate -- orphaned, but a few dozen harmless rows beats a
        destructive delete pass over a save file."""
        self.journey_index += 1
        self.combat_difficulty = difficulty_def(difficulty_id)["id"]
        # Session 53: the route is picked in the same panel and is fixed for
        # the journey's length, exactly like the difficulty -- and for the
        # same reason it can't be changed mid-run: which biomes are open, and
        # what the seal costs, are facts the chain is built from on boot.
        self.adventure_route = self.route_def(route_id)["id"]
        self.adventure_chain = self._build_adventure_chain()
        # Fragment ids are global (`ember_fragment`, ...), not journey-scoped
        # the way quest ids are -- so unlike the quest set, this one has to
        # actually clear, or the new chain's first trade would be satisfiable
        # the moment it's offered.
        self.artifact_fragments.clear()
        # Word of Recall's anchor can point into the journey just abandoned
        # (session 26 persists whatever room it was last cast in). That id
        # still generates -- it just isn't part of this world anymore, so
        # recalling to it would drop the player into a dungeon no quest can
        # reference. Clear it rather than strand them there.
        if (self.player.recall_room or "").startswith("biome:"):
            self.player.recall_room = None
            self.player.recall_x = None
            self.player.recall_y = None
        self.journey_open = False
        self.journey_pending = None
        self.trade_open = False
        self.trade_cursor = 0
        route = self.route_def()
        self.message_log = [
            f"Journey {self.journey_index} begins "
            f"({route['name']}, {difficulty_def(self.combat_difficulty)['name']}).",
        ]
        # Session 54: both halves now also state the seal's cost when it's
        # less than every fragment, since that's the whole difference between
        # the Old Road and the Short Road (and it's the first thing a player
        # on a new route needs to know).
        total = len(self.journey_biome_order())
        required = route["required_fragments"]
        short = f" Any {required} of the {total} will break the seal." if required < total else ""
        if route["chained"]:
            first = BIOME_DEFS[self.journey_biome_order()[0]]["name"]
            self.message_log.append(
                f"The Guide takes back your fragments and points you toward the {first}.{short}"
            )
        else:
            asks = f"any {required}" if required < total else f"all {required}"
            self.message_log.append(
                "The Guide takes back your fragments. Every frontier stands open -- "
                f"bring back {asks}."
            )
        self.persist()
        self.dirty = True

    def close_trade_panel(self):
        self.trade_open = False
        self.dirty = True

    def open_journey_panel(self):
        """Opened from the Guide's trade panel (N / a click on its last
        row). Replaces the trade panel rather than stacking on top of it --
        this codebase has never had two panels open at once and the Esc
        chain in close_active_panel assumes it stays that way."""
        self.trade_open = False
        self.journey_open = True
        # Session 53: the cursor opens on the route the current journey is
        # running, so the panel's first state answers "what am I on now" for
        # the route the same way the `*` marker does for the difficulty.
        self.journey_route_choice = self.adventure_route
        self.journey_cursor = self._journey_route_index(self.adventure_route)
        self.journey_pending = None
        self.dirty = True

    def _journey_route_index(self, route_id):
        routes = self.adventure_quest_defs["routes"]
        for i, entry in enumerate(routes):
            if entry["id"] == route_id:
                return i
        return 0

    def close_journey_panel(self):
        """Esc backs out of the confirm step first, then out of the panel --
        so a mis-hit on Enter is one keystroke to undo, not a discarded
        frontier."""
        if self.journey_pending is not None:
            self.journey_pending = None
        else:
            self.journey_open = False
        self.dirty = True

    def _journey_row_count(self):
        return len(self.adventure_quest_defs["routes"]) + len(COMBAT_DIFFICULTIES)

    def journey_move_cursor(self, delta):
        self.journey_cursor = max(0, min(self._journey_row_count() - 1, self.journey_cursor + delta))
        self.dirty = True

    def activate_journey_row(self, index):
        """Session 53: the panel is two sections under one cursor (the Shop
        panel's own shape) -- routes first, then difficulties. Activating a
        route row just picks it, since choosing a chain shape isn't itself
        destructive; only a difficulty row arms and commits.

        First activation of a difficulty selects it and arms the confirm; the
        second (on the same row) commits. Discarding a frontier is the most
        destructive thing a player can do to their Adventure Mode progress
        with a single keypress, so it deliberately costs two -- and changing
        the route while a confirm is armed disarms it, so the journey that
        gets committed is always the one the panel is currently describing."""
        routes = self.adventure_quest_defs["routes"]
        if 0 <= index < len(routes):
            self.journey_route_choice = routes[index]["id"]
            self.journey_cursor = index
            self.journey_pending = None
            self.dirty = True
            return
        index -= len(routes)
        if not 0 <= index < len(COMBAT_DIFFICULTIES):
            return
        chosen = COMBAT_DIFFICULTIES[index]["id"]
        if self.journey_pending == chosen:
            self.start_new_journey(chosen, self.journey_route_choice)
        else:
            self.journey_cursor = index + len(routes)
            self.journey_pending = chosen
            self.dirty = True

    # -- the Guide's trade panel ------------------------------------------

    def trade_offers(self):
        """The steps the Guide will trade on right now, filtered to the NPC
        actually being talked to. A list rather than a single quest since
        session 53 -- see available_adventure_quests."""
        npc = self.active_npc
        if npc is None:
            return []
        return [q for q in self.available_adventure_quests() if q["giver_npc"] == npc.type]

    def selected_trade_offer(self):
        offers = self.trade_offers()
        if not offers:
            return None
        return offers[min(self.trade_cursor, len(offers) - 1)]

    def trade_move_cursor(self, delta):
        offers = self.trade_offers()
        if len(offers) < 2:
            return  # single-offer panel has no list to move through
        self.trade_cursor = max(0, min(len(offers) - 1, self.trade_cursor + delta))
        self.dirty = True

    def activate_trade_row(self, index):
        """A click on an offer row selects it and, if it can be traded on,
        trades immediately -- same one-click-does-the-thing contract the
        Shop/Healer rows already have."""
        self.trade_cursor = index
        self.dirty = True
        self.attempt_trade()

    def attempt_trade(self):
        """Fetch/trade with the Guide: proof of what the selected step wants
        (still held, not consumed -- see wayfarer_adventure.md's Final Area
        note that the win condition needs every fragment held at once, so
        trading it away here would make that check impossible to satisfy
        later) completes that step and, via the matching biome exit's own
        `requires_biome` field, unlocks whatever it gives."""
        quest = self.selected_trade_offer()
        if quest is None or not self.wants_satisfied(quest):
            return
        self.completed_adventure_quests.add(quest["id"])
        self.message_log = [quest["dialogue"]["success"]]
        self.trade_open = False
        self.trade_cursor = 0
        self.dirty = True

    # -- shop --------------------------------------------------------------

    def close_shop_panel(self):
        self.shop_open = False
        self.dirty = True

    def _shop_rows(self):
        """Combined list backing the shop panel's Up/Down cursor and
        U/click action (session 16): one row per gear slot (buy/upgrade,
        unchanged indices/order from before this session), then one row per
        unidentified Found Gear instance (pay to identify), then one row
        per cursed equipped slot (pay to remove the curse) -- same
        "append extra actions after the original list, one shared cursor"
        pattern this session gave the Inventory panel. Session 20 appends
        two more sections after that, same pattern again: one row per
        sellable consumable stack, then one row per bag (unequipped) gear
        instance -- selling never reaches an equipped slot, see
        engine/equipment.py's discard_instance docstring."""
        rows = [("slot", slot) for slot in SLOTS]
        rows += [("identify", inst["instance_id"]) for inst in self.unidentified_bag_instances()]
        rows += [("remove_curse", slot) for slot in self.cursed_equipped_slots()]
        rows += [
            ("sell_item", item_type) for item_type, _count, item_def in self.inventory.as_list()
            if item_def.get("value", 0) > 0
        ]
        rows += [("sell_gear", inst["instance_id"]) for inst in bag_instances(self.player)]
        return rows

    def shop_move_cursor(self, delta):
        self.shop_cursor = (self.shop_cursor + delta) % len(self._shop_rows())
        self.dirty = True

    def activate_shop_row(self, index):
        rows = self._shop_rows()
        if index >= len(rows):
            return
        kind, payload = rows[index]
        if kind == "slot":
            self.buy_or_upgrade(payload)
        elif kind == "identify":
            self.identify_instance(payload)
        elif kind == "remove_curse":
            self.remove_curse_from_slot(payload)
        elif kind == "sell_item":
            self.sell_item(payload)
        else:
            self.sell_gear(payload)
        # A row can vanish once acted on (the instance/slot/stack it named
        # no longer qualifies, or sold out entirely) -- keep the cursor in
        # range of whatever's left rather than pointing past the new list.
        self.shop_cursor = min(self.shop_cursor, max(0, len(self._shop_rows()) - 1))

    def buy_or_upgrade(self, slot):
        """Buy (or, if something's already equipped in the slot, upgrade
        to) the next tier for the selected slot. Always replaces whatever
        was worn there -- there's no way to buy a spare."""
        offer_type = next_offer(self.player, self.equipment_defs, slot)
        if offer_type is None:
            self.message_log = ["Already own the finest gear for that slot."]
            self.dirty = True
            return
        cost = self.equipment_defs[offer_type]["value"]
        if self.player.gold < cost:
            self.message_log = ["Not enough gold."]
            self.dirty = True
            return
        self.player.gold -= cost
        instance_id = create_shop_instance(self.player, offer_type)
        result = equip_item(self.player, self.equipment_defs, instance_id)
        name = self.equipment_defs[offer_type]["name"]
        if result == "cursed":
            # The gold's already spent -- same as the source material,
            # buying a replacement doesn't refund what you can't take off.
            # The new purchase sits in the Found Gear bag until it can be
            # equipped (see engine/equipment.py's unequip cursed-lock).
            slot = self.equipment_defs[offer_type]["slot"]
            stuck_id = self.player.equipment[slot]
            stuck = equip_display_name(self.equipment_defs, self.player.equipment_instances[stuck_id])
            self.message_log = [f"Purchased {name}, but {stuck} is cursed and won't come off!"]
        else:
            self.message_log = [f"Purchased {name} for {cost} gold."]
        self.dirty = True

    # -- identify / remove curse (session 16) -------------------------------

    IDENTIFY_COST = 15
    REMOVE_CURSE_COST = 30

    def unidentified_bag_instances(self):
        return [inst for inst in bag_instances(self.player) if not inst["identified"]]

    def cursed_equipped_slots(self):
        return [
            slot for slot in SLOTS
            if self.player.equipment.get(slot)
            and self.player.equipment_instances[self.player.equipment[slot]]["cursed"]
        ]

    def identify_instance(self, instance_id):
        instance = self.player.equipment_instances.get(instance_id)
        if instance is None or instance["identified"]:
            return
        if self.player.gold < self.IDENTIFY_COST:
            self.message_log = ["Not enough gold."]
            self.dirty = True
            return
        self.player.gold -= self.IDENTIFY_COST
        instance["identified"] = True
        name = equip_display_name(self.equipment_defs, instance)
        self.message_log = [f"Identified: {name}."]
        self.dirty = True

    def remove_curse_from_slot(self, slot):
        if self.player.gold < self.REMOVE_CURSE_COST:
            self.message_log = ["Not enough gold."]
            self.dirty = True
            return
        if not remove_curse_item(self.player, self.equipment_defs, slot):
            return
        self.player.gold -= self.REMOVE_CURSE_COST
        self.message_log = [f"The curse on your {slot_label(slot).lower()} lifts."]
        self.dirty = True

    # -- sell (session 20) --------------------------------------------------

    # Classic buy-high-sell-low economy -- CotW's shopkeepers pay well under
    # sticker price too. A flat rate rather than per-item haggling, same
    # "one number, not a system" scope call session 16 made for enchant.
    SELL_RATE = 0.4

    def _sell_price(self, value):
        return max(1, round(value * self.SELL_RATE))

    def sell_item(self, item_type):
        """Sells exactly one unit of a consumable stack -- pressing U/click
        again sells another, same one-action-per-row convention every other
        shop row already uses (buy one tier, identify one instance...).
        Items with no positive value (just the quest key today) never reach
        this method at all -- see _shop_rows's filter."""
        item_def = self.item_defs.get(item_type, {})
        value = item_def.get("value", 0)
        if value <= 0 or not self.inventory.remove_item(item_type, 1):
            return
        price = self._sell_price(value)
        self.player.gold += price
        self.message_log = [f"Sold {item_def.get('name', item_type)} for {price} gold."]
        self.dirty = True

    def sell_gear(self, instance_id):
        """Sells a bag (unequipped) gear instance outright -- see
        engine/equipment.py's discard_instance. Priced off the base type's
        shop value alone, same as an unidentified instance's display name
        never leaks its hidden enchant -- the enchant doesn't move the
        price either, identified or not."""
        instance = self.player.equipment_instances.get(instance_id)
        if instance is None:
            return
        price = self._sell_price(self.equipment_defs[instance["base_type"]]["value"])
        name = equip_display_name(self.equipment_defs, instance)
        discard_instance(self.player, instance_id)
        self.player.gold += price
        self.message_log = [f"Sold {name} for {price} gold."]
        self.dirty = True

    # -- healer (session 15) ------------------------------------------------

    HEAL_COST_PER_POINT = 0.5  # 1 gold restores 2 combined HP/mana points

    def close_healer_panel(self):
        self.healer_open = False
        self.dirty = True

    def rest_cost(self):
        """Gold to fully restore HP+mana right now -- 0 if already full.
        A pure function of current state so the panel can preview the
        exact price it's about to charge before the player commits."""
        missing = (self.player.max_hp - self.player.hp) + (self.player.effective_max_mana() - self.player.mana)
        return math.ceil(missing * self.HEAL_COST_PER_POINT)

    def rest_at_healer(self):
        """Fully restores HP and mana for gold, same insufficient-gold-is-
        a-no-op pattern buy_or_upgrade already uses. Free (no gold spent,
        no turn consumed) when already at full HP/mana -- resting doesn't
        need to punish a player who's already topped off. Doesn't consume
        a turn even when it does charge gold: unlike a spell cast, this
        can't affect combat outcomes, it's a pure convenience the player
        pays for in gold instead of Depths grinding."""
        cost = self.rest_cost()
        if cost == 0:
            self.message_log = ["Already at full strength."]
            self.dirty = True
            return
        if self.player.gold < cost:
            self.message_log = ["Not enough gold to rest."]
            self.dirty = True
            return
        self.player.gold -= cost
        self.player.hp = self.player.max_hp
        self.player.mana = self.player.effective_max_mana()
        self.message_log = [f"You rest and recover fully for {cost} gold."]
        self.dirty = True

    # Session 24: Restore Drained Mana -- the Healer's second service,
    # curing a Wraith's permanent mana_drain the same way the Merchant's
    # Remove Curse (session 16) reverses a different kind of permanent
    # affliction. Priced per drained point (steeper than resting's per-HP/
    # mana-point rate -- this is a rarer, worse affliction than being merely
    # low on HP/mana) rather than a flat fee, same "preview the exact price"
    # pattern rest_cost already established.
    DRAIN_CURE_COST_PER_POINT = 5

    def drain_cure_cost(self):
        return math.ceil(self.player.mana_drain * self.DRAIN_CURE_COST_PER_POINT)

    def cure_mana_drain(self):
        if self.player.mana_drain <= 0:
            return
        cost = self.drain_cure_cost()
        if self.player.gold < cost:
            self.message_log = ["Not enough gold to lift the drain."]
            self.dirty = True
            return
        self.player.gold -= cost
        self.player.mana_drain = 0
        self.message_log = [f"The wraith-touch fades. Your mana ceiling is restored for {cost} gold."]
        self.dirty = True

    # Session 37: Restore Sapped Strength -- the Wight family's attack-drain
    # counterpart to Restore Drained Mana above, same per-point gold pricing
    # and reversal shape (see Player.attack_drain's docstring for why this
    # engine drains attack rather than STR/DEX/CON directly).
    def attack_drain_cure_cost(self):
        return math.ceil(self.player.attack_drain * self.DRAIN_CURE_COST_PER_POINT)

    def cure_attack_drain(self):
        if self.player.attack_drain <= 0:
            return
        cost = self.attack_drain_cure_cost()
        if self.player.gold < cost:
            self.message_log = ["Not enough gold to lift the drain."]
            self.dirty = True
            return
        self.player.gold -= cost
        self.player.attack += self.player.attack_drain
        self.player.attack_drain = 0
        self.message_log = [f"The wight-touch fades. Your strength is restored for {cost} gold."]
        self.dirty = True

    def _healer_rows(self):
        """Rest is always present; Restore Drained Mana/Restore Sapped
        Strength only appear once there's actually a drain to cure -- same
        "append an extra action only when it applies" pattern session 16
        gave the Merchant panel's Identify/Remove Curse rows."""
        rows = ["rest"]
        if self.player.mana_drain > 0:
            rows.append("cure_drain")
        if self.player.attack_drain > 0:
            rows.append("cure_attack_drain")
        return rows

    def healer_move_cursor(self, delta):
        rows = self._healer_rows()
        self.healer_cursor = (self.healer_cursor + delta) % len(rows)
        self.dirty = True

    def activate_healer_row(self, index):
        rows = self._healer_rows()
        if index >= len(rows):
            return
        kind = rows[index]
        if kind == "rest":
            self.rest_at_healer()
        elif kind == "cure_drain":
            self.cure_mana_drain()
        else:
            self.cure_attack_drain()
        self.healer_cursor = min(self.healer_cursor, max(0, len(self._healer_rows()) - 1))

    # -- bookshop (session 19) ----------------------------------------------
    #
    # Castle of the Winds' other half of its spell system (session 12 only
    # built the auto-learn-by-level half): a spellbook lets a character
    # learn a spell before their level would otherwise grant it, for gold.
    # Deliberately doesn't touch engine/spells.py's newly_learned() at all --
    # a bought spell is just added to known_spells directly, the exact same
    # set a level-up already adds to, so casting/mana/targeting need zero
    # changes to support a spell learned this way instead of by leveling.

    def close_bookshop_panel(self):
        self.bookshop_open = False
        self.dirty = True

    def _bookshop_rows(self):
        """Every spell not yet known, in data/spells.json order (so the
        list reads as a fixed catalog, not one that reshuffles as spells
        are bought) -- once bought, a spell drops out of this list the same
        way a maxed-out gear slot drops out of the shop's offer, no
        separate "owned" bookkeeping needed."""
        return [s for s in self.spell_defs if s["id"] not in self.known_spells]

    def bookshop_move_cursor(self, delta):
        rows = self._bookshop_rows()
        if not rows:
            return
        self.bookshop_cursor = (self.bookshop_cursor + delta) % len(rows)
        self.dirty = True

    def activate_bookshop_row(self, index):
        rows = self._bookshop_rows()
        if index >= len(rows):
            return
        self.buy_spellbook(rows[index]["id"])
        self.bookshop_cursor = min(self.bookshop_cursor, max(0, len(self._bookshop_rows()) - 1))

    def _spell_def(self, spell_id):
        return next(s for s in self.spell_defs if s["id"] == spell_id)

    def buy_spellbook(self, spell_id):
        """Same insufficient-gold-is-a-silent-no-op pattern every other gold
        sink in this game uses. No mana/level check -- the whole point is
        buying past the level gate; a level-1 character with enough gold can
        walk out knowing Firebolt."""
        if spell_id in self.known_spells:
            return
        spell = self._spell_def(spell_id)
        cost = spell["book_cost"]
        if self.player.gold < cost:
            self.message_log = ["Not enough gold."]
            self.dirty = True
            return
        self.player.gold -= cost
        self.known_spells.add(spell_id)
        self.message_log = [f"Learned {spell['name']} for {cost} gold."]
        self.dirty = True

    # -- spells --------------------------------------------------------

    def toggle_spellbook(self):
        self.spellbook_open = not self.spellbook_open
        self.spellbook_cursor = 0
        self.dirty = True

    def close_spellbook_panel(self):
        self.spellbook_open = False
        self.dirty = True

    def spellbook_move_cursor(self, delta):
        spells = self._known_spell_list()
        if not spells:
            return
        self.spellbook_cursor = (self.spellbook_cursor + delta) % len(spells)
        self.dirty = True

    def _known_spell_list(self):
        return [s for s in self.spell_defs if s["id"] in self.known_spells]

    def _bolt_target(self, spell):
        """First live enemy along the player's facing direction, within the
        spell's range, with an unobstructed line (walls and closed locked
        doors/gates block it same as they block movement). Facing is set by
        Player.try_move on every move attempt -- even a blocked one -- so
        bumping a wall first is a free way to aim without actually moving."""
        dx, dy = self.player.facing
        if dx == 0 and dy == 0:
            return None
        blocked = self._blocked_positions()
        x, y = self.player.x, self.player.y
        for _ in range(spell.get("range", 5)):
            x, y = x + dx, y + dy
            if not self.room.is_walkable(x, y) or (x, y) in blocked:
                return None
            for enemy in self.enemies:
                if enemy.alive and enemy.x == x and enemy.y == y:
                    return enemy
        return None

    def _ball_impact_point(self, spell):
        """Where a ball spell (Fireball/Cold Ball/Ball Lightning) detonates.
        Source material: "Balls are so large that they always hit... may hit
        something and explode before reaching their targets, but this
        applies only to the center tile." A bolt fizzles entirely if its
        line is empty (see _bolt_target returning None); a ball still goes
        off somewhere -- this walks the same facing/range/wall-blocked line,
        stopping at the first enemy, the last walkable tile before a wall/
        closed door, or the max-range tile if the line is clear the whole
        way. Returns None only if the very first step is already blocked
        (nowhere at all to detonate)."""
        dx, dy = self.player.facing
        if dx == 0 and dy == 0:
            return None
        blocked = self._blocked_positions()
        x, y = self.player.x, self.player.y
        last = None
        for _ in range(spell.get("range", 5)):
            nx, ny = x + dx, y + dy
            if not self.room.is_walkable(nx, ny) or (nx, ny) in blocked:
                break
            x, y = nx, ny
            last = (x, y)
            if any(enemy.alive and enemy.x == x and enemy.y == y for enemy in self.enemies):
                break
        return last

    def _resolve_blink(self, spell):
        """Slide the player up to `range` tiles along their facing
        direction, stopping just short of a wall, a closed locked
        door/gate, or any enemy/NPC -- landing on an exit tile is fine, it
        just behaves like walking there normally would on the next move."""
        dx, dy = self.player.facing
        if dx == 0 and dy == 0:
            return False
        blocked = self._blocked_positions()
        x, y = self.player.x, self.player.y
        landed = False
        for _ in range(spell.get("range", 4)):
            nx, ny = x + dx, y + dy
            if not self.room.is_walkable(nx, ny) or (nx, ny) in blocked:
                break
            if any(e.alive and e.x == nx and e.y == ny for e in self.enemies):
                break
            if any(n.x == nx and n.y == ny for n in self.npcs):
                break
            x, y = nx, ny
            landed = True
        if landed:
            self.player.x, self.player.y = x, y
            self._reveal_region_at_player()
        return landed

    def cast_selected_spell(self):
        """Casting only happens from this panel (no field hotkey yet, see
        engine/spells.py) and always consumes a turn on a successful cast --
        unlike inventory items, a bolt spell directly damages an enemy, so
        letting it be spammed for free from a paused menu would let the
        player fight risk-free. The panel closes after a successful cast so
        the player immediately sees the room update (and any enemy
        retaliation); an insufficient-mana attempt is a no-op that leaves it
        open to try something else."""
        if self.player.hp <= 0:
            return
        spells = self._known_spell_list()
        if self.spellbook_cursor >= len(spells):
            return
        spell = spells[self.spellbook_cursor]
        if self.player.mana < spell["mana_cost"]:
            self.message_log = ["Not enough mana."]
            self.dirty = True
            return

        effect = spell["effect"]
        message = None
        if effect == "heal":
            # CotW's own Heal Minor/Medium/Major Wounds each restore a flat
            # amount OR a percent of max HP, whichever is more -- the flat
            # floor keeps a low-tier heal useful the moment it's learned
            # (this engine's leveling adds 10 max_hp/level, so the two
            # amounts cross over almost exactly at each spell's unlock
            # level), while the percent keeps it from falling off at high
            # level. Spells with no "percent" key (none currently) just fall
            # back to the flat value.
            pct_amount = round(self.player.max_hp * spell.get("percent", 0))
            heal_amount = max(spell.get("value", 0), pct_amount)
            healed = min(heal_amount, self.player.max_hp - self.player.hp)
            self.player.hp += healed
            message = f"You cast {spell['name']}. Restored {healed} HP."
        elif effect == "buff_defense":
            self.player.buff_defense_bonus = spell.get("value", 0)
            self.player.buff_defense_turns = spell.get("duration", 1)
            message = f"You cast {spell['name']}. Defense +{spell.get('value', 0)} for {spell.get('duration', 1)} turns."
        elif effect == "bolt":
            target = self._bolt_target(spell)
            if target is None:
                message = f"You cast {spell['name']}, but it finds no target."
            else:
                damage_type = spell.get("damage_type", "physical")
                # Session 22: an elemental bolt (Firebolt) bypasses defense
                # the same way an elemental enemy attack bypasses the
                # player's -- see combat.py's _enemy_damage_to_player and
                # its module-level note on why armor doesn't stop flame.
                if damage_type == "physical":
                    dmg = max(1, spell.get("value", 0) - target.defense)
                else:
                    dmg = max(1, spell.get("value", 0))
                spell_log = resolve_spell_hit(self.player, target, dmg, spell["name"], damage_type)
                self._learn_new_spells(spell_log)
                message = " ".join(spell_log)
                if not target.alive:
                    self.dead_enemy_ids.add(target.id)
                    self.enemies = [e for e in self.enemies if e.alive]
                    if self.current_room_id.startswith("proc:"):
                        self.depths_kills += 1
                    if (
                        self.current_room_id.startswith("proc:")
                        and self.current_room_enemy_ids
                        and self.current_room_enemy_ids <= self.dead_enemy_ids
                        and self.room_cleared_turn.get(self.current_room_id) is None
                    ):
                        self.room_cleared_turn[self.current_room_id] = self.turn_count
        elif effect == "ball":
            # Session 41: Castle of the Winds' Fireball/Cold Ball/Ball
            # Lightning -- "affect a 3x3 area. Do damage equivalent to the
            # corresponding bolt in the center square, and half as much
            # damage in the eight adjacent squares." There's deliberately no
            # ball spell for Spark (CotW's own directory: "no ball spell
            # corresponding to Magic Arrow"), so every damage_type here is
            # elemental -- always bypasses defense the same way the sibling
            # bolt spells already do, no physical branch needed.
            center = self._ball_impact_point(spell)
            if center is None:
                message = f"You cast {spell['name']}, but it finds no target."
            else:
                cx, cy = center
                damage_type = spell.get("damage_type", "physical")
                base = spell.get("value", 0)
                ring_dmg = max(1, round(base / 2))
                logs = []
                hit_any = False
                for enemy in list(self.enemies):
                    if not enemy.alive:
                        continue
                    dist = max(abs(enemy.x - cx), abs(enemy.y - cy))
                    if dist > 1:
                        continue
                    dmg = base if (enemy.x, enemy.y) == (cx, cy) else ring_dmg
                    logs.extend(resolve_spell_hit(self.player, enemy, dmg, spell["name"], damage_type))
                    hit_any = True
                    if not enemy.alive:
                        self.dead_enemy_ids.add(enemy.id)
                        if self.current_room_id.startswith("proc:"):
                            self.depths_kills += 1
                self.enemies = [e for e in self.enemies if e.alive]
                if (
                    self.current_room_id.startswith("proc:")
                    and self.current_room_enemy_ids
                    and self.current_room_enemy_ids <= self.dead_enemy_ids
                    and self.room_cleared_turn.get(self.current_room_id) is None
                ):
                    self.room_cleared_turn[self.current_room_id] = self.turn_count
                # Source material: balls "may hurt the player, but
                # nevertheless be worthwhile." In this engine's facing-line
                # aim (no free tile-cursor targeting), that happens whenever
                # the blast's center is adjacent to the player -- the 3x3
                # ring then covers the player's own tile too.
                if max(abs(self.player.x - cx), abs(self.player.y - cy)) <= 1:
                    splash = resolve_ball_splash_to_player(self.player, ring_dmg, damage_type)
                    self.player.hp -= splash
                    logs.append(f"The blast catches you for {splash}!")
                    if self.player.hp <= 0:
                        self.player.hp = 0
                        logs.append("You have fallen...")
                if not logs:
                    logs.append(f"You cast {spell['name']}. The blast finds nothing to hurt.")
                elif not hit_any:
                    logs.insert(0, f"You cast {spell['name']}.")
                self._learn_new_spells(logs)
                message = " ".join(logs)
        elif effect == "blink":
            landed = self._resolve_blink(spell)
            message = f"You cast {spell['name']}." if landed else f"You cast {spell['name']}, but nothing happens."
        elif effect == "detect_monsters":
            self.detect_monsters_turns = spell.get("duration", 1)
            message = f"You cast {spell['name']}. You sense the foes hidden nearby."
        elif effect == "detect_treasure":
            self.detect_treasure_turns = spell.get("duration", 1)
            message = f"You cast {spell['name']}. You sense the treasure hidden nearby."
        elif effect == "detect_traps":
            self.detect_traps_turns = spell.get("duration", 1)
            message = f"You cast {spell['name']}. Hidden mechanisms reveal themselves."
        elif effect == "levitation":
            self.player.levitation_turns = spell.get("duration", 1)
            message = f"You cast {spell['name']}. You drift above the floor, safe from mundane traps."
        elif effect == "cure_poison":
            # Session 23: matches Castle of the Winds' actual Neutralize
            # Poison spell -- purges the DoT outright rather than healing the
            # damage already taken. Cast resolves before _advance_turn below
            # ticks poison for this turn, so curing it here means that tick
            # sees none left and does no further damage/wear-off message.
            if self.player.poison_turns > 0:
                self.player.poison_turns = 0
                self.player.poison_damage = 0
                message = f"You cast {spell['name']}. The poison in your veins is purged."
            else:
                message = f"You cast {spell['name']}, but you weren't poisoned."
        elif effect == "identify":
            # Session 27: a mana-cost alternative to the Merchant's paid
            # Identify service (session 16) -- same target selection
            # (oldest unidentified Found Gear instance, the same list the
            # shop panel's identify rows already iterate) and the same
            # `identified = True` mutation, just no gold changes hands.
            targets = self.unidentified_bag_instances()
            if targets:
                instance = targets[0]
                instance["identified"] = True
                name = equip_display_name(self.equipment_defs, instance)
                message = f"You cast {spell['name']}. Identified: {name}."
            else:
                message = f"You cast {spell['name']}, but you have nothing unidentified to reveal."
        elif effect == "remove_curse":
            # Session 27: a mana-cost alternative to the Merchant's paid
            # Remove Curse service (session 16) -- same target selection
            # (first cursed equipped slot) and the same remove_curse_item
            # call, just no gold changes hands.
            slots = self.cursed_equipped_slots()
            if slots:
                slot = slots[0]
                remove_curse_item(self.player, self.equipment_defs, slot)
                message = f"You cast {spell['name']}. The curse on your {slot_label(slot).lower()} lifts."
            else:
                message = f"You cast {spell['name']}, but nothing you wear is cursed."
        elif effect == "resist_element":
            # Session 34: Castle of the Winds' Resist Fire/Cold/Lightning --
            # a temporary per-element buff, stacking additively with the
            # flat, always-on resist_elemental amulet stat (see
            # engine/combat.py's _enemy_damage_to_player). Re-casting the
            # same resist spell refreshes it to the new duration/bonus
            # rather than stacking, same "overwrite, don't compound"
            # reasoning buff_defense_turns already uses for Stone Skin.
            dtype = spell.get("damage_type")
            value = spell.get("value", 0)
            duration = spell.get("duration", 1)
            if dtype == "fire":
                self.player.temp_resist_fire_bonus = value
                self.player.temp_resist_fire_turns = duration
            elif dtype == "cold":
                self.player.temp_resist_cold_bonus = value
                self.player.temp_resist_cold_turns = duration
            elif dtype == "lightning":
                self.player.temp_resist_lightning_bonus = value
                self.player.temp_resist_lightning_turns = duration
            message = f"You cast {spell['name']}. {dtype.capitalize()} resistance +{value}% for {duration} turns."
        elif effect == "reveal_room":
            # Session 38: Castle of the Winds' Light -- "reveals a room...
            # including any monsters or objects that may be within it."
            # This engine already has a per-room fog-of-war (session 10/11)
            # that normally only lifts region-by-region as the player
            # physically walks into each one; Light just unions in every
            # region this room has at once, reusing revealed_regions/
            # _current_room_flags exactly as _reveal_region_at_player does
            # for a single region, so the reveal persists through
            # save/reload the same way. A room with no `regions` (every
            # hand-authored room except the Crypt) has nothing to reveal.
            if self.room.regions:
                region_ids = {r["id"] for r in self.room.regions}
                newly = region_ids - self.revealed_regions
                self.revealed_regions |= region_ids
                message = (
                    f"You cast {spell['name']}. The room is bathed in light."
                    if newly else
                    f"You cast {spell['name']}, but this room holds no more secrets."
                )
            else:
                message = f"You cast {spell['name']}, but there's nothing here to reveal."
        elif effect == "sleep":
            # Session 40: Castle of the Winds' Sleep Monster -- "puts one
            # target monster to sleep... some monsters and all bosses are
            # immune and all will wake in about ten minutes or when
            # attacked." Reuses _bolt_target's exact facing/range/line-of-
            # sight targeting (same single-enemy-ahead aim as the bolt
            # spells), but sets Enemy.sleep_turns instead of dealing damage
            # -- see engine/entity.py's Enemy.take_turn (skips its whole
            # turn while asleep) and engine/combat.py's resolve_bump_attack/
            # resolve_spell_hit (either kind of hit wakes it, forfeiting the
            # sleeping enemy's retaliation on a melee wake-up).
            target = self._bolt_target(spell)
            if target is None:
                message = f"You cast {spell['name']}, but it finds no target."
            elif target.sleep_immune:
                message = f"You cast {spell['name']}, but {target.name} is unaffected."
            else:
                target.sleep_turns = spell.get("duration", 20)
                message = f"You cast {spell['name']}. {target.name} slumps into a deep sleep."
        elif effect == "slow":
            # Session 42: Castle of the Winds' Slow Monster -- "slows the
            # target monster's movement and attacks to half... a second
            # cast reduces the speed to 1/3, a third to 1/4, etc." Same
            # single-enemy facing/range targeting as Sleep Monster above
            # and the same sleep_immune boss-immunity check (see
            # engine/entity.py's Enemy.slow_level docstring for why); unlike
            # Sleep there's no wear-off duration in the source text, so each
            # cast just increments slow_level and resets slow_tick so the
            # new, finer cadence starts clean rather than mid-cycle.
            target = self._bolt_target(spell)
            if target is None:
                message = f"You cast {spell['name']}, but it finds no target."
            elif target.sleep_immune:
                message = f"You cast {spell['name']}, but {target.name} is unaffected."
            else:
                target.slow_level += 1
                target.slow_tick = 0
                message = (
                    f"You cast {spell['name']}. {target.name} is slowed to "
                    f"1/{target.slow_level + 1} speed."
                )
        elif effect == "transmogrify":
            # Session 55: Castle of the Winds' Transmogrify Monster --
            # "turns the target monster into a random other monster." Same
            # single-enemy facing/range targeting and the same sleep_immune
            # boss-immunity check as Sleep/Slow above (sessions 40/42), so
            # this is the third spell riding _bolt_target without dealing
            # damage. Two adaptations worth naming:
            #
            # * The destination roster is the *non-boss* half of
            #   data/enemies.json (`sleep_immune` false), not every type.
            #   Bosses are already immune to being transmogrified, so
            #   allowing them as a destination would make the spell's worst
            #   outcome "your Slime is now a Young Red Dragon, and no spell
            #   in the book can undo it" -- a permanent, counterplay-free
            #   death sentence rather than a gamble. Within the seven normal
            #   types it's still a real gamble in both directions (a Viper
            #   can come back as a Tunnel Wight), which is the part of the
            #   source spell actually worth having.
            # * The re-roll is scaled to the depth the original spawned at
            #   (Enemy.level, session 55) rather than to base stats, so
            #   transmogrifying on dungeon level 9 can't be used to launder
            #   a scaled enemy into an unscaled one. The new type's own
            #   xp_reward/gold_reward come along with it -- rolling a
            #   tougher monster is worth more, which is the gamble's upside.
            target = self._bolt_target(spell)
            if target is None:
                message = f"You cast {spell['name']}, but it finds no target."
            elif target.sleep_immune:
                message = f"You cast {spell['name']}, but {target.name} is unaffected."
            else:
                candidates = sorted(
                    t for t, defn in self.enemy_defs.items()
                    if t != target.type and not defn.get("sleep_immune")
                )
                if not candidates:
                    message = f"You cast {spell['name']}, but nothing else stirs in its place."
                else:
                    old_name = target.name
                    new_type = random.choice(candidates)
                    new_stats = self.enemy_defs[new_type]
                    if target.level > 1:
                        new_stats = scale_stats_for_level(new_stats, target.level)
                    target.transmogrify_into(new_type, new_stats)
                    message = (
                        f"You cast {spell['name']}. The {old_name} twists and "
                        f"reshapes itself into a {target.name}!"
                    )
        elif effect == "reveal_map":
            # Session 38: Castle of the Winds' Clairvoyance -- "fills in the
            # player's map of a 10x10 area anywhere on the floor." Adapted to
            # this engine's room-grid automap (session 8): marks every Depths
            # room within `radius` grid-cells of the player's current room as
            # discovered, via the same save.mark_discovered/self.discovered
            # bookkeeping load_room already does on a physical visit -- so
            # the journal's automap and door-connection rendering
            # (room_doors is a pure function of coordinates, see procgen.py)
            # work identically for a room revealed by magic as one actually
            # walked into, no new state model needed. Only meaningful in the
            # Depths -- the three hand-authored town rooms have no room-grid
            # automap at all (see PROGRESS.MD's Known Limitations).
            if self.current_room_id.startswith("proc:"):
                _, _seed_str, level_str, gx_str, gy_str = self.current_room_id.split(":")
                level = int(level_str)
                cx, cy = int(gx_str), int(gy_str)
                radius = spell.get("radius", 2)
                if level not in self.discovered:
                    self.discovered[level] = self.save.get_discovered_rooms(level)
                newly = 0
                for dx in range(-radius, radius + 1):
                    for dy in range(-radius, radius + 1):
                        coord = (cx + dx, cy + dy)
                        if coord not in self.discovered[level]:
                            self.save.mark_discovered(level, *coord)
                            self.discovered[level].add(coord)
                            newly += 1
                message = (
                    f"You cast {spell['name']}. The dungeon's paths reveal themselves."
                    if newly else
                    f"You cast {spell['name']}, but you've already mapped everything nearby."
                )
            else:
                message = f"You cast {spell['name']}, but there is no dungeon floor to map here."

        recall_target = None
        if effect == "recall":
            # Session 26: Castle of the Winds' Word of Recall -- cast away
            # from town, it anchors the return trip and pulls the player
            # home; cast again in town, it pulls them right back to that
            # anchor. One spell, direction picked by where you're standing,
            # same as the real scroll (and the same "in town vs. not" split
            # main.py already uses for save.DEFAULT_ROOM elsewhere). The
            # anchor is deliberately NOT cleared after a return trip -- like
            # the real item, casting it again from the dungeon is what moves
            # the anchor, not reading it from town.
            if self.current_room_id == DEFAULT_ROOM:
                if self.player.recall_room:
                    recall_target = (self.player.recall_room, self.player.recall_x, self.player.recall_y)
                    message = f"You cast {spell['name']}. The dungeon pulls you back."
                else:
                    message = f"You cast {spell['name']}, but you have nowhere to recall to."
            else:
                self.player.recall_room = self.current_room_id
                self.player.recall_x, self.player.recall_y = self.player.x, self.player.y
                recall_target = (DEFAULT_ROOM, DEFAULT_SPAWN[0], DEFAULT_SPAWN[1])
                message = f"You cast {spell['name']}. The town pulls you home."

        self.player.mana -= spell["mana_cost"]
        poison_msgs = self._advance_turn()
        self.spellbook_open = False
        self.dirty = True

        if recall_target and self.player.hp > 0:
            # Mirrors handle_move's "exit" branch: flush the room being
            # left, load the destination, then autosave with position
            # already pointing at where the player landed -- and skip
            # _take_turn's enemy-turn pass, since entering a room is its
            # own turn and nothing there has seen the player yet.
            target_room, target_x, target_y = recall_target
            self.save.set_room_flags(self.current_room_id, self._current_room_flags())
            self.save.set_room_drops(self.current_room_id, self.room_drops)
            self.save.set_block_positions(self.current_room_id, self.blocks)
            if self.current_room_id.startswith("proc:"):
                epoch, cleared_turn = self._room_meta(self.current_room_id)
                self.save.set_room_meta(self.current_room_id, epoch, cleared_turn)
            self.load_room(target_room, target_x, target_y)
            self.message_log = poison_msgs + [message] + self.message_log
            self.persist()
        else:
            self._take_turn(poison_msgs + ([message] if message else []))

    # -- journal (quest log + dungeon automap) ------------------------------

    def toggle_journal(self):
        self.journal_open = not self.journal_open
        self.dirty = True

    # -- rendering -----------------------------------------------------

    def draw(self, fps_target, is_focused, actual_fps):
        screen = self.screen
        screen.fill(COLOR_BG)

        self.room_surface.fill((0, 0, 0))
        self.room.draw(self.room_surface, TILE_SIZE, self.revealed_regions)
        self._draw_fixtures()
        for item in self.items:
            if self._is_visible(item.x, item.y, self.detect_treasure_turns):
                item.draw(self.room_surface, TILE_SIZE)
        for npc in self.npcs:
            if self._is_visible(npc.x, npc.y):
                npc.draw(self.room_surface, TILE_SIZE)
        for enemy in self.enemies:
            if self._is_visible(enemy.x, enemy.y, self.detect_monsters_turns):
                enemy.draw(self.room_surface, TILE_SIZE)
                if enemy.sleep_turns > 0:
                    # Session 40: a translucent tint over a sleeping enemy's
                    # own tile -- visual confirmation Sleep Monster actually
                    # landed, same "don't just trust the log line" screenshot
                    # discipline every UI-touching session since 11 follows.
                    # A text tag was tried first and rejected: at a 16px tile
                    # (session 9's native scale) any label tall enough to
                    # read spills into the tile above, which is exactly where
                    # an adjacent player sprite sits during the common
                    # "walk up and melee the sleeper" case -- see PROGRESS.MD
                    # session 40 for the screenshot that caught this. A
                    # same-tile tint has no such spillover.
                    tint = pygame.Surface((TILE_SIZE, TILE_SIZE), pygame.SRCALPHA)
                    tint.fill((150, 150, 255, 110))
                    self.room_surface.blit(tint, (enemy.x * TILE_SIZE, enemy.y * TILE_SIZE))
        self.player.draw(self.room_surface, TILE_SIZE)
        pygame.draw.rect(
            screen, COLOR_PANEL_BORDER,
            (ROOM_ORIGIN[0] - 2, ROOM_ORIGIN[1] - 2, ROOM_PIXEL_W + 4, ROOM_PIXEL_H + 4), 2,
        )

        self._draw_hud()
        self._draw_message_log()
        if self.debug_overlay:
            self._draw_debug_overlay(fps_target, is_focused, actual_fps)
        if self.inventory_open:
            self._draw_inventory()
        if self.quest_open:
            self._draw_quest_panel()
        if self.shop_open:
            self._draw_shop_panel()
        if self.healer_open:
            self._draw_healer_panel()
        if self.bookshop_open:
            self._draw_bookshop_panel()
        if self.trade_open:
            self._draw_trade_panel()
        if self.journey_open:
            self._draw_journey_panel()
        if self.spellbook_open:
            self._draw_spellbook_panel()
        if self.journal_open:
            self._draw_journal_panel()
        if self.win_screen_open:
            self._draw_win_screen()

        pygame.display.flip()

    def _draw_fixtures(self):
        """Chests/switches/gates/locked doors (session 10) -- drawn as
        overlays on top of the floor tile Room.draw() already put there,
        same as items/NPCs/enemies below. Chests and switches always exist
        in their list (state is which sprite they pick); gates/locked_doors
        are removed from their list entirely once solved, so simply not
        being in the list is their "open" state -- nothing left to draw."""
        for chest in self.chests:
            if not self._is_visible(chest["x"], chest["y"], self.detect_treasure_turns):
                continue
            name = "chest_open" if chest["id"] in self.opened_chest_ids else "chest_closed"
            sprite = AssetManager.get_sprite(name)
            if sprite:
                self.room_surface.blit(sprite, (chest["x"] * TILE_SIZE, chest["y"] * TILE_SIZE))
        for switch in self.switches:
            if not self._is_visible(switch["x"], switch["y"]):
                continue
            name = "switch_on" if switch["gate_id"] in self.open_gate_ids else "switch_off"
            sprite = AssetManager.get_sprite(name)
            if sprite:
                self.room_surface.blit(sprite, (switch["x"] * TILE_SIZE, switch["y"] * TILE_SIZE))
        for plate in self.plates:
            # Session 48: drawn before blocks below so a block resting on
            # top of its plate still shows the block, not the floor marking
            # underneath -- same draw-order reasoning floor/wall tiles
            # already use for exit-kind overlays in Room.draw.
            if not self._is_visible(plate["x"], plate["y"]):
                continue
            name = "plate_on" if plate["gate_id"] in self.open_gate_ids else "plate_off"
            sprite = AssetManager.get_sprite(name)
            if sprite:
                self.room_surface.blit(sprite, (plate["x"] * TILE_SIZE, plate["y"] * TILE_SIZE))
        for block in self.blocks:
            if not self._is_visible(block["x"], block["y"]):
                continue
            sprite = AssetManager.get_sprite("push_block")
            if sprite:
                self.room_surface.blit(sprite, (block["x"] * TILE_SIZE, block["y"] * TILE_SIZE))
        for gate in self.gates:
            if not self._is_visible(gate["x"], gate["y"]):
                continue
            sprite = AssetManager.get_sprite("gate")
            if sprite:
                self.room_surface.blit(sprite, (gate["x"] * TILE_SIZE, gate["y"] * TILE_SIZE))
        for door in self.locked_doors:
            if not self._is_visible(door["x"], door["y"]):
                continue
            # Session 49: a colored door draws its own tint variant
            # (registered in _load_assets) instead of the generic amber
            # one, so the correct-colored key reads as an obvious match at
            # a glance.
            color = door.get("color")
            sprite_name = f"locked_door_{color}" if color else "locked_door"
            sprite = AssetManager.get_sprite(sprite_name)
            if sprite:
                self.room_surface.blit(sprite, (door["x"] * TILE_SIZE, door["y"] * TILE_SIZE))
        for trap in self.traps:
            # Session 28: unlike every other fixture here, a trap is hidden
            # by default even inside an already-explored (fog-revealed)
            # region -- that's the whole point of a trap. It only shows once
            # sprung (permanently, like an opened chest) or while Detect
            # Traps is active, on top of the usual fog check.
            detected = trap["id"] in self.sprung_trap_ids or self.detect_traps_turns > 0
            if not detected or not self._is_visible(trap["x"], trap["y"], self.detect_traps_turns):
                continue
            sprite = AssetManager.get_sprite(trap["type"])
            if sprite:
                self.room_surface.blit(sprite, (trap["x"] * TILE_SIZE, trap["y"] * TILE_SIZE))

    def _draw_hud(self):
        """Session 25 (UI pass): full window-width boxed bar, replacing the
        old cramped top-left cluster that shared the window with 80px of
        unused black margin on either side. Four stacked rows -- HP, MP,
        Lvl/XP, Status -- each gets its own line now that the bar is sized
        to fit them (TOP_BAR_H) rather than squeezed into a fixed 56px to
        match the old window height; this also removes the old design's
        biggest fragility (Lvl/XP and both status effects sharing one row,
        which measured to within 20px of the old 800px window's right edge
        at max level with both statuses active -- see the row-width check
        this session's screenshots re-verified). Room name/gold stay
        top-right, one per row, mirroring the left column's row heights."""
        font = AssetManager.get_font(16, bold=True)
        pygame.draw.rect(self.screen, COLOR_HUD_BG, (0, 0, WINDOW_W, TOP_BAR_H))
        pygame.draw.line(
            self.screen, COLOR_PANEL_BORDER, (0, TOP_BAR_H - 1), (WINDOW_W, TOP_BAR_H - 1)
        )

        eff_max_mana = self.player.effective_max_mana()
        bar_x, bar_w, bar_h = 12, 110, 12
        row1_y, row2_y, row3_y, row4_y = 8, 28, 48, 66

        hp_text = font.render(f"HP {self.player.hp}/{self.player.max_hp}", True, COLOR_TEXT)
        pygame.draw.rect(self.screen, COLOR_HP_BG, (bar_x, row1_y, bar_w, bar_h))
        fill_w = int(bar_w * max(0, self.player.hp) / self.player.max_hp)
        pygame.draw.rect(self.screen, COLOR_HP, (bar_x, row1_y, fill_w, bar_h))
        self.screen.blit(hp_text, (bar_x + bar_w + 8, row1_y - 3))

        # Session 24: shows the drained ceiling, not the raw stat, so a
        # Wraith-touched player sees their actual current cap (e.g. "MP
        # 5/17" rather than a misleading "MP 5/20") -- see
        # Player.effective_max_mana().
        mana_text = font.render(f"MP {self.player.mana}/{eff_max_mana}", True, COLOR_TEXT)
        pygame.draw.rect(self.screen, COLOR_MP_BG, (bar_x, row2_y, bar_w, bar_h))
        mana_fill_w = int(bar_w * max(0, self.player.mana) / eff_max_mana) if eff_max_mana else 0
        pygame.draw.rect(self.screen, COLOR_MP, (bar_x, row2_y, mana_fill_w, bar_h))
        self.screen.blit(mana_text, (bar_x + bar_w + 8, row2_y - 3))

        lvl_text = font.render(
            f"Lv {self.player.level}  XP {self.player.xp}/{self.player.level * 30}", True, COLOR_TEXT
        )
        self.screen.blit(lvl_text, (bar_x, row3_y))

        status_x = bar_x
        if self.player.poison_turns > 0:
            poison_text = font.render(f"Poisoned ({self.player.poison_turns})", True, COLOR_POISON)
            self.screen.blit(poison_text, (status_x, row4_y))
            status_x += poison_text.get_width() + 20
        if self.player.mana_drain > 0:
            # Session 24: no countdown (unlike Poisoned) -- drain doesn't
            # wear off on its own, only paying the Healer clears it (see
            # cure_mana_drain), so this shows the amount, not a timer.
            drain_text = font.render(f"Drained (-{self.player.mana_drain} MP)", True, COLOR_DRAIN)
            self.screen.blit(drain_text, (status_x, row4_y))
            status_x += drain_text.get_width() + 20
        if self.player.attack_drain > 0:
            # Session 37: same no-countdown reasoning as Drained above --
            # only paying the Healer (cure_attack_drain) clears a Wight's
            # touch.
            weaken_text = font.render(f"Weakened (-{self.player.attack_drain} ATK)", True, COLOR_WEAKEN)
            self.screen.blit(weaken_text, (status_x, row4_y))
            status_x += weaken_text.get_width() + 20
        if self.player.levitation_turns > 0:
            levitate_text = font.render(f"Levitating ({self.player.levitation_turns})", True, COLOR_LEVITATE)
            self.screen.blit(levitate_text, (status_x, row4_y))
            status_x += levitate_text.get_width() + 20
        if self.player.temp_resist_fire_turns > 0:
            fire_text = font.render(f"Resist Fire ({self.player.temp_resist_fire_turns})", True, COLOR_RESIST_FIRE)
            self.screen.blit(fire_text, (status_x, row4_y))
            status_x += fire_text.get_width() + 20
        if self.player.temp_resist_cold_turns > 0:
            cold_text = font.render(f"Resist Cold ({self.player.temp_resist_cold_turns})", True, COLOR_RESIST_COLD)
            self.screen.blit(cold_text, (status_x, row4_y))
            status_x += cold_text.get_width() + 20
        if self.player.temp_resist_lightning_turns > 0:
            lightning_text = font.render(
                f"Resist Lightning ({self.player.temp_resist_lightning_turns})", True, COLOR_RESIST_LIGHTNING
            )
            self.screen.blit(lightning_text, (status_x, row4_y))

        room_text = font.render(self.room.name, True, COLOR_TEXT)
        gold_text = font.render(f"Gold {self.player.gold}", True, COLOR_GOLD)
        self.screen.blit(room_text, (WINDOW_W - room_text.get_width() - 12, row1_y - 3))
        self.screen.blit(gold_text, (WINDOW_W - gold_text.get_width() - 12, row2_y - 3))

    def _draw_message_log(self):
        """Session 25 (UI pass): boxed panel spanning the full log bar
        (LOG_ORIGIN/LOG_H, see top of file) instead of bare text floating
        directly on the background with no boundary and no wrapping -- the
        reported bug was a long line running off the right edge of the
        window and a second line getting clipped by the bottom edge, since
        the old version had neither a wrap step nor a box tall enough for
        more than one line. Wraps every retained message to the box's
        width first, then shows however many wrapped lines fit in
        LOG_MAX_LINES, most recent last (so a short turn's single message
        still lands at a stable spot rather than jumping around)."""
        font = AssetManager.get_font(14)
        panel = pygame.Surface((WINDOW_W - HUD_GAP * 2, LOG_H), pygame.SRCALPHA)
        panel.fill(COLOR_PANEL_BG)
        pygame.draw.rect(panel, COLOR_PANEL_BORDER, panel.get_rect(), 2)

        max_line_w = panel.get_width() - 20
        wrapped_lines = []
        for line in self.message_log:
            wrapped_lines.extend(_wrap_text(font, line, max_line_w))

        y = 10
        for line in wrapped_lines[-LOG_MAX_LINES:]:
            panel.blit(font.render(line, True, COLOR_TEXT), (10, y))
            y += 18

        self.screen.blit(panel, LOG_ORIGIN)

    def _draw_debug_overlay(self, fps_target, is_focused, actual_fps):
        font = AssetManager.get_font(14)
        mode = "ACTIVE" if is_focused else "IDLE"
        lines = [
            f"FPS target: {fps_target}  actual: {actual_fps:.1f}",
            f"Mode: {mode}",
            f"Room: {self.current_room_id}  Pos: {self.player.x},{self.player.y}",
        ]
        panel = pygame.Surface((260, 18 * len(lines) + 8), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        for i, line in enumerate(lines):
            panel.blit(font.render(line, True, COLOR_DEBUG), (6, 6 + i * 18))
        self.screen.blit(panel, (WINDOW_W - panel.get_width() - 8, TOP_BAR_H + 8))

    def _panel_surface(self, panel_w, panel_h):
        """Shared background+border for every overlay panel (session 25 --
        previously each of the 7 panel draw methods duplicated
        `pygame.Surface(...); panel.fill(COLOR_PANEL_BG)` with no border,
        so a panel's edge was only ever implied by where its text stopped).
        The border is drawn on the panel surface itself, not the screen, so
        it moves with the panel and stays correct regardless of where
        _begin_panel_hitboxes ends up centering it."""
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill(COLOR_PANEL_BG)
        pygame.draw.rect(panel, COLOR_PANEL_BORDER, panel.get_rect(), 2)
        return panel

    def _begin_panel_hitboxes(self, panel_w, panel_h):
        """Call at the top of any panel's draw method, before laying out
        rows: records the panel's screen-space bounding rect (so clicking
        outside it can close it, see handle_panel_click) and resets the
        per-row click list for that method to append (row_rect, callback)
        pairs to as it lays out each row. Returns the panel's screen origin
        so the caller's own final `self.screen.blit(panel, origin)` and the
        hitboxes below are guaranteed to agree on where the panel actually
        is -- no separate copy of the centering math to drift out of sync."""
        origin = ((WINDOW_W - panel_w) // 2, (WINDOW_H - panel_h) // 2)
        self.panel_outer_rect = pygame.Rect(*origin, panel_w, panel_h)
        self.panel_click_targets = []
        return origin

    def _click_use_inventory(self, index):
        """Doesn't route through select_inventory_slot (that's bounded to
        consumables only, for the 1-8 field-hotkey contract -- see
        _inventory_rows) since a click can land on a Found Gear row past
        that range; activates the row directly instead."""
        message = self._activate_inventory_row(index)
        if message is None:
            return
        self.message_log = [message]
        remaining = self._inventory_rows()
        self.inventory_cursor = min(index, max(0, len(remaining) - 1))
        self.dirty = True

    def _click_cast_spell(self, index):
        self.spellbook_cursor = index
        self.cast_selected_spell()

    def _click_shop_slot(self, index):
        self.shop_cursor = index
        self.activate_shop_row(index)

    def _click_healer_row(self, index):
        self.healer_cursor = index
        self.activate_healer_row(index)

    def _click_buy_spellbook(self, index):
        self.bookshop_cursor = index
        self.activate_bookshop_row(index)

    def _any_panel_open(self):
        return (
            self.inventory_open or self.quest_open or self.shop_open
            or self.spellbook_open or self.journal_open or self.healer_open
            or self.bookshop_open or self.trade_open or self.journey_open
        )

    def handle_room_click(self, pos):
        """A single grid step toward the clicked tile, exactly as if the
        corresponding arrow key had been pressed -- reuses handle_move
        entirely, so every adjacent-tile interaction (attack/pickup/talk/
        door/chest/switch/exit) already works with zero new game logic. A
        tile more than one step away just takes one step along whichever
        axis is further off (this engine has no pathfinding or diagonal
        movement anywhere, on keyboard or otherwise, so a click isn't an
        exception to that). Called once per click and, while the button
        stays held, again on each held-repeat tick (see tick_move_repeat)
        with the *current* cursor position each time -- so holding and
        dragging follows the mouse, the same way a Diablo-style
        click-to-walk would, without this method needing to know whether
        it's being called from a fresh click or a repeat."""
        if self.player.hp <= 0:
            return
        # Session 25: rooms smaller than the full viewport are letterboxed
        # at self.room_draw_origin, not the fixed ROOM_ORIGIN (see
        # _resize_room_surface) -- a click has to be measured against
        # wherever the room is actually drawn, and bounds-checked against
        # its own (possibly smaller) pixel size, not the viewport's.
        origin_x, origin_y = self.room_draw_origin
        local_x, local_y = pos[0] - origin_x, pos[1] - origin_y
        room_w, room_h = self.room_surface.get_size()
        if not (0 <= local_x < room_w and 0 <= local_y < room_h):
            return
        tile_x, tile_y = local_x // TILE_SIZE, local_y // TILE_SIZE
        dx_raw, dy_raw = tile_x - self.player.x, tile_y - self.player.y
        if dx_raw == 0 and dy_raw == 0:
            return
        if abs(dx_raw) >= abs(dy_raw):
            dx, dy = (1 if dx_raw > 0 else -1), 0
        else:
            dx, dy = 0, (1 if dy_raw > 0 else -1)
        self.handle_move(dx, dy)

    def handle_panel_click(self, pos):
        """Left-click while a panel is open: hits a row's action if the
        click landed on one (set by whichever panel most recently drew
        itself), otherwise closes the panel if the click landed outside it
        -- clicking blank space inside the panel does nothing, same as
        clicking blank space in the room doesn't move the player."""
        for rect, callback in self.panel_click_targets:
            if rect.collidepoint(pos):
                callback()
                return
        if self.panel_outer_rect and not self.panel_outer_rect.collidepoint(pos):
            self.close_active_panel()

    def close_active_panel(self):
        """Closes whichever single panel is currently open (only one ever
        is -- see main.py's key/click guards) and reports whether one was,
        so both Esc and a click-outside-the-panel can share this."""
        if self.inventory_open:
            self.toggle_inventory()
        elif self.quest_open:
            self.close_quest_panel()
        elif self.shop_open:
            self.close_shop_panel()
        elif self.healer_open:
            self.close_healer_panel()
        elif self.bookshop_open:
            self.close_bookshop_panel()
        elif self.trade_open:
            self.close_trade_panel()
        elif self.journey_open:
            self.close_journey_panel()
        elif self.spellbook_open:
            self.close_spellbook_panel()
        elif self.journal_open:
            self.toggle_journal()
        else:
            return False
        return True

    # -- input dispatch (session 13) ----------------------------------
    #
    # Everything main.py's event loop used to inline directly now lives
    # here as methods on Game, taking a raw key/pos rather than a pygame
    # Event -- this is what makes it possible to unit-test the *actual*
    # dispatch logic (which key does what, in which mode) without spinning
    # up a live window and posting real SDL events, and it's also what
    # let held-key/held-click repeat slot in cleanly: KEYUP and a
    # once-per-frame repeat tick both need to share state with KEYDOWN,
    # which was awkward to thread through main()'s inline if/elif chain.

    def handle_mouse_down(self, pos):
        """Left mouse button pressed: panel clicks are one-shot (see
        handle_panel_click) but a room click also arms click-and-hold --
        holding the button repeats handle_room_click at the live cursor
        position via tick_move_repeat, exactly like a held movement key."""
        if self.win_screen_open:
            # Any click dismisses the one-time victory modal -- it has no
            # rows of its own, so it deliberately doesn't go through
            # panel_click_targets/_any_panel_open like every other panel.
            self.win_screen_open = False
            self.dirty = True
            return
        if self._any_panel_open():
            self.handle_panel_click(pos)
            return
        self.handle_room_click(pos)
        self.mouse_held = True
        self.next_move_repeat_at = pygame.time.get_ticks() + MOVE_REPEAT_DELAY_MS

    def handle_mouse_up(self):
        self.mouse_held = False

    def handle_key_down(self, key):
        """Dispatches one KEYDOWN. Returns True to request quitting the
        game (Esc pressed with no panel open to close instead) -- main.py
        still owns the actual `running` flag/event loop, everything else
        about what a keypress *means* lives here now."""
        if self.win_screen_open:
            # Any key (including Esc) dismisses the one-time victory modal
            # -- checked before Esc's own quit-if-nothing-to-close logic
            # below, same "consume this input, do nothing else this frame"
            # priority every other panel already gets.
            self.win_screen_open = False
            self.dirty = True
            return False
        if key == pygame.K_ESCAPE:
            return not self.close_active_panel()
        if key == pygame.K_F3:
            self.debug_overlay = not self.debug_overlay
            self.dirty = True
            return False
        if key == pygame.K_i and not (self.quest_open or self.shop_open or self.journal_open or self.spellbook_open or self.healer_open or self.bookshop_open or self.trade_open or self.journey_open):
            self.toggle_inventory()
            return False
        if key == pygame.K_m and not (self.quest_open or self.shop_open or self.inventory_open or self.spellbook_open or self.healer_open or self.bookshop_open or self.trade_open or self.journey_open):
            self.toggle_journal()
            return False
        if key == pygame.K_c and not (self.quest_open or self.shop_open or self.inventory_open or self.journal_open or self.healer_open or self.bookshop_open or self.trade_open or self.journey_open):
            self.toggle_spellbook()
            return False

        if self.quest_open:
            if key in (pygame.K_u, pygame.K_RETURN):
                self.claim_quest_reward()
            return False
        if self.trade_open:
            # Up/Down do nothing when there's only one offer (the straight-
            # line route, always) -- see trade_move_cursor.
            if key in (pygame.K_UP, pygame.K_w):
                self.trade_move_cursor(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.trade_move_cursor(1)
            elif key in (pygame.K_u, pygame.K_RETURN):
                self.attempt_trade()
            elif key == pygame.K_n:
                self.open_journey_panel()
            return False
        if self.journey_open:
            if key in (pygame.K_UP, pygame.K_w):
                self.journey_move_cursor(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.journey_move_cursor(1)
            elif key in (pygame.K_u, pygame.K_RETURN):
                self.activate_journey_row(self.journey_cursor)
            return False
        if self.healer_open:
            if key in (pygame.K_UP, pygame.K_w):
                self.healer_move_cursor(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.healer_move_cursor(1)
            elif key in (pygame.K_u, pygame.K_RETURN):
                self.activate_healer_row(self.healer_cursor)
            return False
        if self.bookshop_open:
            if key in (pygame.K_UP, pygame.K_w):
                self.bookshop_move_cursor(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.bookshop_move_cursor(1)
            elif key in (pygame.K_u, pygame.K_RETURN):
                self.activate_bookshop_row(self.bookshop_cursor)
            return False
        if self.shop_open:
            if key in (pygame.K_UP, pygame.K_w):
                self.shop_move_cursor(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.shop_move_cursor(1)
            elif key in (pygame.K_u, pygame.K_RETURN):
                self.activate_shop_row(self.shop_cursor)
            return False
        if self.spellbook_open:
            if key in (pygame.K_UP, pygame.K_w):
                self.spellbook_move_cursor(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.spellbook_move_cursor(1)
            elif key in (pygame.K_u, pygame.K_RETURN):
                self.cast_selected_spell()
            return False
        if self.journal_open:
            return False  # only Esc/M close it -- nothing else to interact with
        if self.inventory_open:
            if key in (pygame.K_UP, pygame.K_w):
                self.inventory_move_cursor(-1)
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.inventory_move_cursor(1)
            elif key in (pygame.K_u, pygame.K_RETURN):
                self.use_selected_item()
            elif key == pygame.K_x:
                self.drop_selected_item()
            elif pygame.K_1 <= key <= pygame.K_8:
                self.select_inventory_slot(key - pygame.K_1)
            return False

        # No panel open: movement (+ arms held-key repeat) and quick-use.
        if key in MOVE_KEYS:
            self.handle_move(*MOVE_KEYS[key])
            self.held_move_key = key
            self.held_move_dir = MOVE_KEYS[key]
            self.next_move_repeat_at = pygame.time.get_ticks() + MOVE_REPEAT_DELAY_MS
        elif key == pygame.K_t:
            self.attempt_disarm()
        elif key == pygame.K_r:
            self.field_rest()
        elif pygame.K_1 <= key <= pygame.K_8:
            self.quick_use_item(key - pygame.K_1)
        return False

    def handle_key_up(self, key):
        """Stops keyboard hold-repeat when the key driving it is released.
        If a different movement key is still physically held (checked live
        rather than tracked separately), switches the repeat to that
        direction instead of stopping -- releasing Right while still
        holding Down, say, keeps walking down rather than freezing."""
        if key != self.held_move_key:
            return
        pressed = pygame.key.get_pressed()
        for other_key, direction in MOVE_KEYS.items():
            if other_key != key and pressed[other_key]:
                self.held_move_key = other_key
                self.held_move_dir = direction
                return
        self.held_move_key = None
        self.held_move_dir = None

    def clear_held_input(self):
        """Releases any held-key/held-click movement state -- called on
        WINDOWFOCUSLOST, since alt-tabbing away can lose a KEYUP/
        MOUSEBUTTONUP the same way it would for any other app, which would
        otherwise leave the player walking on their own after the window
        loses focus (and, if `is_focused` throttles the loop to IDLE_FPS
        while that's happening, walking as a slow stutter instead of
        stopping)."""
        self.held_move_key = None
        self.held_move_dir = None
        self.mouse_held = False

    def tick_move_repeat(self):
        """Continuous movement while a direction key or the left mouse
        button is held (session 13: a single tap/click only ever advanced
        one tile, which is far too slow for actual play). A per-frame
        timestamp check, nothing more -- at most one extra handle_move/
        handle_room_click call per repeat interval, never per-frame
        busy-work, so this doesn't threaten the idle-cheap budget the rest
        of the loop is built around. Gating on `_any_panel_open()` fresh
        every call (rather than clearing held state when a panel opens)
        means a held-direction walk that bumps into an NPC and opens their
        panel just stops advancing immediately, with nothing extra to
        reset by hand."""
        if self.player.hp <= 0 or self._any_panel_open():
            return
        if self.held_move_dir is None and not self.mouse_held:
            return
        now = pygame.time.get_ticks()
        if now < self.next_move_repeat_at:
            return
        if self.held_move_dir is not None:
            self.handle_move(*self.held_move_dir)
        else:
            self.handle_room_click(pygame.mouse.get_pos())
        self.next_move_repeat_at = now + MOVE_REPEAT_INTERVAL_MS

    def _draw_inventory(self):
        """Panel height grows to fit the Found Gear section (session 16:
        variable-length, unlike the fixed 8-slot consumable list above it)
        -- same measure-content-then-build-surface approach session 15's
        spellbook panel established, rather than a hardcoded offset that a
        long enough gear bag could eventually clip past."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        # 400 (pre-session-16 width) clips the "U/click use/equip" hint
        # line added below -- measured directly with font.size(), same
        # discipline session 13 used for this exact class of bug, not
        # eyeballed. Session 24's dual "Elemental Resist NN%, Undead Ward
        # NN%" title measures 480px at this bold font -- widened again
        # (450 -> 500) rather than shortening the labels, same "widen the
        # panel, don't shrink the text" call sessions 13/16/18 already made
        # for this exact panel.
        panel_w = 500
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        items = self.inventory.as_list()
        gear = bag_instances(self.player)

        equip_y = 36 + max(1, len(items)) * 20 + 10
        gear_y = equip_y + 24 + len(SLOTS) * 18 + 14
        panel_h = gear_y + 24 + max(1, len(gear)) * 18 + 30

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        panel.blit(title_font.render("Inventory", True, COLOR_TEXT), (10, 8))

        if not items:
            panel.blit(font.render("(empty)", True, COLOR_TEXT), (10, 36))
        for i, (item_type, count, item_def) in enumerate(items):
            prefix = "> " if i == self.inventory_cursor else "  "
            label = f"{prefix}{item_def.get('name', item_type)} x{count}"
            row_y = 36 + i * 20
            panel.blit(font.render(label, True, COLOR_TEXT), (10, row_y))
            row_rect = pygame.Rect(origin[0], origin[1] + row_y, panel_w, 18)
            self.panel_click_targets.append((row_rect, lambda idx=i: self._click_use_inventory(idx)))

        # Equipped gear -- bought/upgraded at the Merchant or equipped from
        # Found Gear below (see _draw_shop_panel / _activate_inventory_row).
        # Session 22: resist_elemental has no HP-bar/attack-power equivalent
        # to make it visible through gameplay feel alone (unlike attack/
        # defense/max_hp), so it gets an explicit number here, on the
        # section title itself to avoid growing the panel's height math.
        equip_title = "Equipped"
        resist_bits = []
        if self.player.resist_elemental > 0:
            resist_bits.append(f"Elemental Resist {self.player.resist_elemental}%")
        if self.player.resist_undead > 0:
            resist_bits.append(f"Undead Ward {self.player.resist_undead}%")
        if resist_bits:
            equip_title += f" ({', '.join(resist_bits)})"
        panel.blit(title_font.render(equip_title, True, COLOR_TEXT), (10, equip_y))
        for i, slot in enumerate(SLOTS):
            instance_id = self.player.equipment.get(slot)
            instance = self.player.equipment_instances.get(instance_id) if instance_id else None
            line = f"{slot_label(slot)}: {equip_display_name(self.equipment_defs, instance)}"
            panel.blit(font.render(line, True, COLOR_TEXT), (10, equip_y + 24 + i * 18))

        # Found Gear -- unequipped instances (session 16), whether bought as
        # a spare or picked up in the Depths. Selecting one here equips it,
        # sharing the same combined cursor/row indices as the consumable
        # list above (see _inventory_rows) rather than a second cursor.
        panel.blit(title_font.render("Found Gear", True, COLOR_TEXT), (10, gear_y))
        if not gear:
            panel.blit(font.render("(none)", True, COLOR_TEXT), (10, gear_y + 24))
        consumable_count = len(items)
        for gi, instance in enumerate(gear):
            idx = consumable_count + gi
            prefix = "> " if idx == self.inventory_cursor else "  "
            label = f"{prefix}{equip_display_name(self.equipment_defs, instance)}"
            row_y = gear_y + 24 + gi * 18
            panel.blit(font.render(label, True, COLOR_TEXT), (10, row_y))
            row_rect = pygame.Rect(origin[0], origin[1] + row_y, panel_w, 16)
            self.panel_click_targets.append((row_rect, lambda idx=idx: self._click_use_inventory(idx)))

        hint = font.render("Up/Down or 1-8 select, U/click use/equip, X drop, I/Esc close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_quest_panel(self):
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w, panel_h = 340, 160
        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        npc_name = self.active_npc.name if self.active_npc else "Quartermaster"
        panel.blit(title_font.render(npc_name, True, COLOR_TEXT), (10, 8))

        quest = self.current_quest()
        if quest is None:
            body = ["No further tasks. You've proven yourself, adventurer."]
        else:
            progress = min(self.depths_kills, quest["target"])
            body = [
                quest["description"],
                f"Progress: {progress}/{quest['target']}",
            ]
            if self.depths_kills >= quest["target"]:
                body.append("Press U or click here to claim your reward.")

        for i, line in enumerate(body):
            row_y = 40 + i * 20
            panel.blit(font.render(line, True, COLOR_TEXT), (10, row_y))
            if quest is not None and self.depths_kills >= quest["target"] and i == len(body) - 1:
                row_rect = pygame.Rect(origin[0], origin[1] + row_y, panel_w, 18)
                self.panel_click_targets.append((row_rect, self.claim_quest_reward))

        hint = font.render("Esc to close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_trade_panel(self):
        """The Frontier Guide's fetch/trade panel (session 45). Same
        "measure-then-build wrapped lines" shape as the Shop panel, since
        the dialogue lines run longer than this panel's width at 14pt --
        unlike the plain fixed-height quest panel above, whose two lines
        were always short enough to not need wrapping."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w = 360
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        npc = self.active_npc
        offers = self.trade_offers()
        if len(offers) > 1:
            # Session 53: the Open Frontier route can have several trades
            # live at once, which the original single-action layout has no
            # room for. Drawn as its own list-with-cursor branch rather than
            # by generalizing the layout below, so a straight-line journey's
            # panel (every existing save's) renders byte-identically to what
            # sessions 45-52 shipped.
            self._draw_multi_trade_panel(offers, npc, panel_w, title_font, font)
            return

        quest = offers[0] if offers else None
        matches = quest is not None

        have = False
        if matches:
            have = self.wants_satisfied(quest)
            raw_lines = [quest["dialogue"]["intro"]]
            raw_lines.append(self._carry_line(quest) if have else quest["dialogue"]["incomplete"])
            if have:
                raw_lines.append("Press U or click here to trade.")
        elif self.journey_won():
            raw_lines = ["The seal is broken and the frontier is at peace. Rest, adventurer -- you've earned it."]
        else:
            raw_lines = ["Safe travels, adventurer. I've nothing more to ask of you."]
        # Session 52: the Guide is also where a new journey is started (Yoda
        # Stories keeps New World on its own menu; this game has no menu
        # during play, and the Guide is already the NPC who owns every
        # world-progression fact). Offered unconditionally, exactly like the
        # source game's own "discards the current world" option -- mid-chain
        # is a legitimate time to want a different frontier, and the panel
        # this opens makes the cost explicit before anything happens.
        trade_row_count = len(raw_lines)
        raw_lines.append("Press N for a new journey.")

        wrapped = [_wrap_text(font, line, panel_w - 20) for line in raw_lines]
        body_h = sum(16 * len(w) + 6 for w in wrapped)
        panel_h = 40 + body_h + 34

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        npc_name = npc.name if npc else "Frontier Guide"
        panel.blit(title_font.render(npc_name, True, COLOR_TEXT), (10, 8))

        y = 36
        for i, wrapped_line_group in enumerate(wrapped):
            row_top = y
            is_journey_row = i == len(wrapped) - 1
            color = (200, 190, 130) if is_journey_row else COLOR_TEXT
            for wl in wrapped_line_group:
                panel.blit(font.render(wl, True, color), (10, y))
                y += 16
            y += 6
            action = None
            if is_journey_row:
                action = self.open_journey_panel
            elif matches and have and i == trade_row_count - 1:
                action = self.attempt_trade
            if action is not None:
                row_rect = pygame.Rect(origin[0], origin[1] + row_top, panel_w, y - row_top)
                self.panel_click_targets.append((row_rect, action))

        hint = font.render("Esc to close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_multi_trade_panel(self, offers, npc, panel_w, title_font, font):
        """Session 53: the Guide's panel when more than one trade is live at
        once -- the Open Frontier route's whole point. One row per offer with
        a cursor, and only the selected row's dialogue spelled out underneath
        in grey (the Spellbook/journey panels' shape), so the panel's height
        stays bounded no matter how many frontiers are open.

        The Final Area's row is deliberately in the list from the first day
        even though it can't be traded on yet: seeing "The Sundering -- any 3
        fragments (0/4 carried)" sitting under four biomes is how a player
        learns the route is a branch and that one biome is optional."""
        offers = offers[:]
        self.trade_cursor = min(self.trade_cursor, len(offers) - 1)

        route = self.route_def()
        # Session 54: a chained route can reach this panel too, now that the
        # seal can be its own always-offered step on one (the Short Road: one
        # live biome trade plus the seal, so two offers). "Every frontier out
        # there stands open" is flatly false there, so the greeting follows
        # the route's shape.
        # ...and a route that wants every fragment needs its own sentence
        # rather than the same one with the number swapped: "4 fragments of
        # the 4 will break the seal" is a sentence nobody would write.
        total = len(self.journey_biome_order())
        greeting_key = "open_greeting" if not route["chained"] else "chained_greeting"
        if route["required_fragments"] >= total:
            greeting_key += "_all"
        greeting = self.adventure_quest_defs["templates"][greeting_key].format(
            required_fragments=route["required_fragments"],
            total_fragments=total,
        )

        rows = []
        for quest in offers:
            if quest["biome"] is None:
                name = BIOME_DEFS[self.adventure_quest_defs["final_biome"]]["name"]
                status = f"{len(self.artifact_fragments)}/{quest['wants']['count']} carried"
            else:
                name = BIOME_DEFS[quest["biome"]]["name"]
                status = "carried" if self.wants_satisfied(quest) else "not yet found"
            rows.append((f"{name} -- {self.wants_label(quest)} ({status})", quest))

        # An offer row is a single unwrapped line (a wrapped row would break
        # the one-row-one-hitbox mapping), so the panel is measured to fit its
        # longest one rather than given a guessed width -- the first draft
        # guessed 420 and a rendered screenshot caught "Scorched Wastes --
        # Ember-Charred Fragment (not ye" clipping off the edge, which is the
        # same lesson sessions 11/13/15/16/40/45/46/52 each learned the hard
        # way. Capped at the window, since nothing can be drawn past it.
        panel_w = min(
            WINDOW_W - 40,
            max(420, max(font.size(f"> {head}")[0] for head, _q in rows) + 20),
        )
        greeting_wrapped = _wrap_text(font, greeting, panel_w - 20)

        selected = offers[self.trade_cursor]
        detail = selected["dialogue"]["intro" if self.wants_satisfied(selected) else "incomplete"]
        detail_wrapped = _wrap_text(font, detail, panel_w - 46)

        action_line = (
            "Press U or click the row to trade."
            if self.wants_satisfied(selected)
            else "Nothing to trade on this one yet."
        )
        footer = [action_line, "Press N for a new journey."]
        footer_wrapped = [_wrap_text(font, line, panel_w - 20) for line in footer]

        body_h = (
            16 * len(greeting_wrapped) + 6
            + len(rows) * 18
            + 16 * len(detail_wrapped) + 8
            + sum(16 * len(w) + 6 for w in footer_wrapped)
        )
        panel_h = 40 + body_h + 34

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)
        panel.blit(title_font.render(npc.name if npc else "Frontier Guide", True, COLOR_TEXT), (10, 8))

        y = 36
        for wl in greeting_wrapped:
            panel.blit(font.render(wl, True, COLOR_TEXT), (10, y))
            y += 16
        y += 6

        for i, (head, quest) in enumerate(rows):
            prefix = "> " if i == self.trade_cursor else "  "
            color = (230, 200, 110) if self.wants_satisfied(quest) else COLOR_TEXT
            row_top = y
            panel.blit(font.render(f"{prefix}{head}", True, color), (10, y))
            y += 18
            row_rect = pygame.Rect(origin[0], origin[1] + row_top, panel_w, y - row_top)
            self.panel_click_targets.append((row_rect, lambda idx=i: self.activate_trade_row(idx)))

        for wl in detail_wrapped:
            panel.blit(font.render(wl, True, (170, 170, 170)), (36, y))
            y += 16
        y += 8

        for i, wrapped_line_group in enumerate(footer_wrapped):
            row_top = y
            color = (200, 190, 130) if i == len(footer_wrapped) - 1 else COLOR_TEXT
            for wl in wrapped_line_group:
                panel.blit(font.render(wl, True, color), (10, y))
                y += 16
            y += 6
            if i == len(footer_wrapped) - 1:
                row_rect = pygame.Rect(origin[0], origin[1] + row_top, panel_w, y - row_top)
                self.panel_click_targets.append((row_rect, self.open_journey_panel))

        hint = font.render("Up/Down select, U/Enter/click trade, Esc to close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_journey_panel(self):
        """Session 52: the Guide's New Journey panel -- this game's version
        of Yoda Stories' New Game dialog, which is where that game puts its
        world size and Combat Difficulty options. Same "list-with-cursor,
        dynamic height" shape as the Healer/Shop/Bookshop panels, plus a
        wrapped preamble (the trade panel's own technique) since the
        explanation and the confirm line both run past this width.

        Two states in one surface: pick a difficulty, then confirm. The
        confirm exists because this is the only action in the game that
        throws away progress, and the panel spells out exactly what goes and
        what stays rather than making the player remember."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w = 520
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        next_index = self.journey_index + 1
        preamble = [
            f"You're on journey {self.journey_index} ({self.route_def()['name']}): "
            f"{self.journey_route_summary()}.",
            "A new journey re-rolls the frontier -- new dungeon layouts, a new "
            "order to walk them in, and a road and a difficulty of your choosing.",
            "Your fragments are handed back to me. Your level, gear, gold, "
            "spells and the Depths all stay exactly as they are.",
        ]
        wrapped = [_wrap_text(font, line, panel_w - 20) for line in preamble]
        preamble_h = sum(16 * len(w) + 6 for w in wrapped)

        # Session 53: the route section, above the difficulty rungs and
        # sharing their cursor. Same two-part row shape (name + effect, then
        # a wrapped grey blurb) so the two sections read as one list.
        routes = self.adventure_quest_defs["routes"]
        route_rows = []
        total_fragments = len(self.adventure_quest_defs["chain_biomes"])
        for entry in routes:
            # The head carries the two knobs that actually decide the run --
            # how the frontiers open and what the seal costs -- and leaves
            # the flavor to the blurb. Session 53 kept the shape off the head
            # (a first draft clipped at "...4 fragments break th"), but with
            # four routes the numbers alone no longer tell two rows apart:
            # the Open Frontier and the Short Road both cost 3 of 4. Both
            # facts fit at this width in the compressed phrasing; verified by
            # a rendered screenshot, same as every panel session before it.
            shape = "one at a time" if entry["chained"] else "all open"
            route_rows.append((
                f"{entry['name']} -- {shape}, {entry['required_fragments']} of {total_fragments} fragments",
                _wrap_text(font, entry["blurb"], panel_w - 46),
            ))
        # Session 54: with four routes, spelling out every blurb pushed this
        # panel past the 600px window (the difficulty section below is four
        # rows of the same shape and the preamble is three wrapped lines).
        # Only the cursor's own route blurb is drawn, which bounds the
        # section's height at however many routes get authored -- the same
        # technique session 53's multi-offer trade panel already uses for its
        # per-offer dialogue. The difficulty rungs keep all four blurbs: they
        # aren't growing, and they're the rows a player most wants to compare
        # side by side.
        # Which route's blurb is spelled out: the row under the cursor while
        # the cursor is in this section, and otherwise the route the next
        # journey will actually run -- so the prose on screen always belongs
        # to the row the panel is currently talking about.
        route_cursor = (
            self.journey_cursor if self.journey_cursor < len(routes)
            else self._journey_route_index(self.journey_route_choice)
        )
        route_rows_h = sum(
            18 + (16 * len(blurb) + 6 if i == route_cursor else 0)
            for i, (_head, blurb) in enumerate(route_rows)
        )

        # A difficulty is a two-part row -- name + what it does to the
        # numbers, then its flavor blurb wrapped and indented underneath in
        # grey, the same shape the Spellbook panel already uses for spell
        # descriptions. (First pass put all of it on one line and a rendered
        # screenshot caught every rung clipping off the panel's right edge;
        # this project keeps re-learning that lesson -- see sessions 11, 13,
        # 15, 16, 40, 45, 46.)
        rows = []
        for entry in COMBAT_DIFFICULTIES:
            level = entry["enemy_level"]
            # Spell out the actual effect, not just flavor -- these rungs map
            # onto the Depths' own scale_stats_for_level, so a player who has
            # felt dungeon level 4 already knows what "Merciless" means.
            effect = "enemy stats as-is" if level == 1 else \
                f"enemy HP +{int(round((level - 1) * 20))}%, attack +{level - 1}, more XP"
            rows.append((
                f"{entry['name']} -- {effect}",
                _wrap_text(font, entry["blurb"], panel_w - 46),
            ))
        rows_h = sum(18 + 16 * len(blurb) + 6 for _head, blurb in rows)

        confirm_lines = []
        if self.journey_pending is not None:
            chosen = difficulty_def(self.journey_pending)
            confirm_lines = _wrap_text(
                font,
                f"Set out on journey {next_index} -- "
                f"{self.route_def(self.journey_route_choice)['name']}, {chosen['name']}? "
                "Press U/Enter again to confirm, Esc to back out.",
                panel_w - 20,
            )

        rows_top = 36 + preamble_h + 6
        panel_h = rows_top + route_rows_h + rows_h + 8 + len(confirm_lines) * 16 + 34

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        panel.blit(title_font.render(f"Set Out on Journey {next_index}", True, COLOR_TEXT), (10, 8))

        y = 36
        for wrapped_line_group in wrapped:
            for wl in wrapped_line_group:
                panel.blit(font.render(wl, True, COLOR_TEXT), (10, y))
                y += 16
            y += 6

        for i, (head, blurb) in enumerate(route_rows):
            entry = routes[i]
            prefix = "> " if i == self.journey_cursor else "  "
            # Same two markers as the difficulty rows below: `*` for what the
            # current journey runs, gold for what the next one will.
            marker = "* " if entry["id"] == self.adventure_route else "  "
            color = (230, 200, 110) if entry["id"] == self.journey_route_choice else COLOR_TEXT
            row_top = y
            panel.blit(font.render(f"{prefix}{marker}{head}", True, color), (10, y))
            y += 18
            if i == route_cursor:
                for wl in blurb:
                    panel.blit(font.render(wl, True, (170, 170, 170)), (36, y))
                    y += 16
                y += 6
            row_rect = pygame.Rect(origin[0], origin[1] + row_top, panel_w, y - row_top)
            self.panel_click_targets.append((row_rect, lambda idx=i: self.activate_journey_row(idx)))

        for i, (head, blurb) in enumerate(rows):
            entry = COMBAT_DIFFICULTIES[i]
            row_index = i + len(routes)
            prefix = "> " if row_index == self.journey_cursor else "  "
            # A star marks the rung the current journey is already running,
            # so "what am I on now" is answerable from this panel alone.
            marker = "* " if entry["id"] == self.combat_difficulty else "  "
            color = (230, 200, 110) if entry["id"] == self.journey_pending else COLOR_TEXT
            row_top = y
            panel.blit(font.render(f"{prefix}{marker}{head}", True, color), (10, y))
            y += 18
            for wl in blurb:
                panel.blit(font.render(wl, True, (170, 170, 170)), (36, y))
                y += 16
            y += 6
            row_rect = pygame.Rect(origin[0], origin[1] + row_top, panel_w, y - row_top)
            self.panel_click_targets.append((row_rect, lambda idx=row_index: self.activate_journey_row(idx)))

        y += 2
        for wl in confirm_lines:
            panel.blit(font.render(wl, True, (230, 200, 110)), (10, y))
            y += 16

        hint = font.render("Up/Down select, U/Enter/click choose, Esc close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_healer_panel(self):
        """Session 24: gained a cursor and a second row (Restore Drained
        Mana), same "list-with-cursor, dynamic height" shape the Shop/
        Bookshop panels already use, replacing the original single fixed-
        action layout (session 15) now that there's more than one thing to
        do here."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        # Session 25: was 360 -- the hint line ("Up/Down select, U/Enter/
        # click act, Esc close", shared verbatim with the Shop/Bookshop
        # panels) measures 352px at this font, which left it running to
        # within 2px of the panel's own edge even before this session added
        # a visible border there (see _panel_surface) to make that kind of
        # near-miss actually noticeable. Widened rather than shortened the
        # hint, same call already made for this exact class of bug
        # elsewhere in this file.
        panel_w = 390
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        rows = self._healer_rows()
        panel_h = 40 + 20 + len(rows) * 20 + 34

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        npc_name = self.active_npc.name if self.active_npc else "Healer"
        panel.blit(
            title_font.render(f"{npc_name} -- Gold: {self.player.gold}", True, COLOR_TEXT),
            (10, 8),
        )
        status = f"HP {self.player.hp}/{self.player.max_hp}  Mana {self.player.mana}/{self.player.effective_max_mana()}"
        panel.blit(font.render(status, True, COLOR_TEXT), (10, 36))

        rest_cost = self.rest_cost()
        for i, kind in enumerate(rows):
            prefix = "> " if i == self.healer_cursor else "  "
            if kind == "rest":
                line = f"{prefix}Rest (already at full strength)" if rest_cost == 0 \
                    else f"{prefix}Rest and recover fully ({rest_cost}g)"
            elif kind == "cure_drain":
                line = f"{prefix}Restore Drained Mana (-{self.player.mana_drain} MP) ({self.drain_cure_cost()}g)"
            else:
                line = f"{prefix}Restore Sapped Strength (-{self.player.attack_drain} ATK) ({self.attack_drain_cure_cost()}g)"
            row_y = 60 + i * 20
            panel.blit(font.render(line, True, COLOR_TEXT), (10, row_y))
            row_rect = pygame.Rect(origin[0], origin[1] + row_y, panel_w, 18)
            self.panel_click_targets.append((row_rect, lambda idx=i: self._click_healer_row(idx)))

        hint = font.render("Up/Down select, U/Enter/click act, Esc close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_bookshop_panel(self):
        """Same list-with-cursor shape as the shop/spellbook panels: one row
        per not-yet-known spell, dynamic height (session 15/16's pattern)
        since the catalog only grows as more spells are added to
        data/spells.json and a level-7+ character with an empty catalog
        needs to render sensibly too (see the empty-list line below)."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w = 380
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        rows = self._bookshop_rows()
        body_rows = max(1, len(rows))
        panel_h = 36 + body_rows * 20 + 34

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        npc_name = self.active_npc.name if self.active_npc else "Scholar"
        panel.blit(
            title_font.render(f"{npc_name} -- Gold: {self.player.gold}", True, COLOR_TEXT),
            (10, 8),
        )

        if not rows:
            panel.blit(
                font.render("You already know every spell in stock.", True, COLOR_TEXT),
                (10, 36),
            )
        for i, spell in enumerate(rows):
            prefix = "> " if i == self.bookshop_cursor else "  "
            line = f"{prefix}{spell['name']} ({spell['book_cost']}g)"
            row_y = 36 + i * 20
            panel.blit(font.render(line, True, COLOR_TEXT), (10, row_y))
            row_rect = pygame.Rect(origin[0], origin[1] + row_y, panel_w, 18)
            self.panel_click_targets.append((row_rect, lambda idx=i: self._click_buy_spellbook(idx)))

        hint = font.render("Up/Down select, U/Enter/click buy, Esc close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_shop_panel(self):
        """Session 16: gained two more row types past the original 5 (one
        per gear slot) -- Identify (pay to reveal a Found Gear instance's
        enchant/curse before risking equipping it blind) and Remove Curse
        (pay to free an equipped slot that's stuck, see engine/equipment.py)
        -- both only appear when there's actually something to act on, so a
        character who's never touched cursed/unidentified gear sees exactly
        the same 5-row panel session 8 shipped. Height grows to fit
        whichever of those rows are present, same pattern as the Inventory
        panel's Found Gear section above. Session 20 appends Sell rows
        (every sellable consumable stack, then every bag gear instance) the
        same way -- absent entirely on an empty inventory/bag, so a fresh
        character still sees the plain slot-row panel."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        # Session 25 (UI pass): was a fixed 700px-wide, single-line-per-row
        # panel -- the widest legitimate line, a "<current> -> <next tier>"
        # ring/amulet upgrade row (e.g. "Amulet of Greater Vitality -3
        # [cursed] -> Amulet of Supreme Vitality (155g)"), measures 680px at
        # this font, and session 18 widened the panel to fit it rather than
        # touch the text. That doesn't fit the new, narrower window (see
        # WINDOW_W at the top of the file -- it's sized around the 640px
        # room viewport, not this panel). Rather than re-widen the window
        # around one panel's one worst-case row, this wraps any row whose
        # rendered line doesn't fit -- same word-wrap every other panel's
        # long text already uses (_wrap_text) -- and measures each row's
        # actual line count before laying anything out, same
        # measure-then-build approach the Spellbook/Inventory panels already
        # use for their own variable-length content.
        panel_w = 480
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        rows = self._shop_rows()

        def row_line(kind, payload):
            if kind == "slot":
                slot = payload
                instance_id = self.player.equipment.get(slot)
                instance = self.player.equipment_instances.get(instance_id) if instance_id else None
                equipped_name = equip_display_name(self.equipment_defs, instance)
                offer_type = next_offer(self.player, self.equipment_defs, slot)
                if offer_type is None:
                    return f"{slot_label(slot)}: {equipped_name} (finest owned)"
                offer = self.equipment_defs[offer_type]
                return f"{slot_label(slot)}: {equipped_name} -> {offer['name']} ({offer['value']}g)"
            if kind == "identify":
                instance = self.player.equipment_instances[payload]
                base_name = self.equipment_defs[instance["base_type"]]["name"]
                return f"Identify {base_name} ({self.IDENTIFY_COST}g)"
            if kind == "remove_curse":
                return f"Remove curse: {slot_label(payload)} ({self.REMOVE_CURSE_COST}g)"
            if kind == "sell_item":
                item_def = self.item_defs.get(payload, {})
                count = self.inventory.stacks.get(payload, 0)
                price = self._sell_price(item_def.get("value", 0))
                return f"Sell {item_def.get('name', payload)} x{count} ({price}g)"
            instance = self.player.equipment_instances[payload]
            name = equip_display_name(self.equipment_defs, instance)
            price = self._sell_price(self.equipment_defs[instance["base_type"]]["value"])
            return f"Sell {name} ({price}g)"

        entries = [
            _wrap_text(font, row_line(kind, payload), panel_w - 30) for kind, payload in rows
        ]

        y = 36
        for wrapped in entries:
            y += 18 * max(1, len(wrapped)) + 4
        panel_h = max(120, y + 30)

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        npc_name = self.active_npc.name if self.active_npc else "Merchant"
        panel.blit(
            title_font.render(f"{npc_name} -- Gold: {self.player.gold}", True, COLOR_TEXT),
            (10, 8),
        )

        y = 36
        for i, wrapped in enumerate(entries):
            row_top = y
            prefix = "> " if i == self.shop_cursor else "  "
            for li, wrapped_line in enumerate(wrapped):
                text = f"{prefix}{wrapped_line}" if li == 0 else f"    {wrapped_line}"
                panel.blit(font.render(text, True, COLOR_TEXT), (10, y))
                y += 18
            y += 4
            row_rect = pygame.Rect(origin[0], origin[1] + row_top, panel_w, y - row_top)
            self.panel_click_targets.append((row_rect, lambda idx=i: self._click_shop_slot(idx)))

        hint = font.render("Up/Down select, U/Enter/click act, Esc close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_spellbook_panel(self):
        """Panel height is computed from the actual known-spell count
        (session 15: fixed at 340 since session 12, which fit the original
        5 spells -- adding divination pushed a 7th spell past that and
        garbled the hint line into the last description, the same class of
        clipping bug session 13's panel-width fix addressed). A fixed
        *width* is still fine (descriptions word-wrap to it); height grows
        with content up to the window's own height, at which point the
        content area scrolls to keep the cursor row visible instead of
        overflowing the screen top/bottom (session 29 -- the ladder
        reaching 13 entries at Levitation is exactly the "just add one more
        entry" growth this method's previous no-cap comment assumed would
        stay small forever; it didn't)."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w = 420
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)
        content_top, hint_h = 40, 34

        spells = self._known_spell_list()
        entries = [(spell, _wrap_text(font, spell["description"], panel_w - 36)) for spell in spells]

        row_tops, y = [], 0
        for _spell, wrapped_lines in entries:
            row_tops.append(y)
            y += 18 + 16 * len(wrapped_lines) + 8
        content_h = y if entries else 20

        max_panel_h = WINDOW_H - 40  # 20px breathing room top/bottom
        panel_h = max(160, min(max_panel_h, content_top + content_h + hint_h))
        viewport_h = panel_h - content_top - hint_h

        scroll = 0
        if entries and content_h > viewport_h:
            cursor_top = row_tops[self.spellbook_cursor]
            cursor_bottom = cursor_top + (
                18 + 16 * len(entries[self.spellbook_cursor][1]) + 8
            )
            scroll = max(0, cursor_bottom - viewport_h)
            scroll = min(scroll, content_h - viewport_h, cursor_top)

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        panel.blit(
            title_font.render(f"Spellbook -- Mana {self.player.mana}/{self.player.effective_max_mana()}", True, COLOR_TEXT),
            (10, 8),
        )

        if not entries:
            panel.blit(font.render("No spells known yet.", True, COLOR_TEXT), (10, content_top))
        panel.set_clip(pygame.Rect(0, content_top, panel_w, viewport_h))
        for i, (spell, wrapped_lines) in enumerate(entries):
            row_top = content_top + row_tops[i] - scroll
            row_h = 18 + 16 * len(wrapped_lines) + 8
            if row_top + row_h < content_top or row_top > content_top + viewport_h:
                continue  # fully outside the visible window -- skip drawing and hitboxing it
            prefix = "> " if i == self.spellbook_cursor else "  "
            line = f"{prefix}{spell['name']} ({spell['mana_cost']} MP)"
            ty = row_top
            panel.blit(font.render(line, True, COLOR_TEXT), (10, ty))
            ty += 18
            for wrapped_line in wrapped_lines:
                panel.blit(font.render(wrapped_line, True, (170, 170, 170)), (26, ty))
                ty += 16
            row_rect = pygame.Rect(origin[0], origin[1] + row_top, panel_w, row_h)
            self.panel_click_targets.append((row_rect, lambda idx=i: self._click_cast_spell(idx)))
        panel.set_clip(None)

        hint = font.render("Up/Down select, U/Enter/click cast, Esc close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _journal_adventure_lines(self):
        """The Journal's Adventure Mode block, as unwrapped lines. Split out
        of _draw_journal_panel (session 52) so the panel can measure the
        block before it builds a surface to draw it on.

        The journey line is new this session and is doing real work, not just
        reporting a counter: once a journey can shuffle the biome order, the
        route is no longer something a player can know from having played
        before, so the Journal is where they read it off."""
        lines = []
        route = self.route_def()
        difficulty = difficulty_def(self.combat_difficulty)["name"]
        won = f", {self.journeys_won} won" if self.journeys_won else ""
        lines.append(
            f"Journey {self.journey_index} ({route['name']}, {difficulty}{won}): "
            f"{self.journey_route_summary(with_final=True)}"
        )

        # Wrapped since session 46: a third biome/fragment pushed this past
        # the panel's 460px width -- confirmed by an actual rendered
        # screenshot clipping the line at "...Ember-Charred Fragment, Frost"
        # before the wrap was added, same clipping session 45 already caught
        # and fixed on the guide line below.
        have = sorted(self.artifact_defs[fid]["name"] for fid in self.artifact_fragments)
        # Session 53: on a route where three of four is enough, "2/4" alone
        # understates how close the player is, so the requirement is named.
        needed = "" if route["required_fragments"] >= len(self.artifact_defs) else \
            f" ({route['required_fragments']} needed)"
        lines.append(
            f"Artifact Fragments: {len(have)}/{len(self.artifact_defs)}{needed}"
            + (f" -- {', '.join(have)}" if have else "")
        )

        # Session 45: the fetch/trade quest chain's current step. Session 47:
        # the won case is distinguished from the plain "no further requests"
        # one -- current_adventure_quest() returns None the moment the last
        # step is traded (unlocking the Final Area exit), but that's not the
        # same moment as actually finishing it (opening the final vault
        # chest, tracked separately via the synthetic "adventure_victory" id
        # -- see handle_move's chest branch and journey_won()).
        #
        # Session 53: one line per live offer, since the Open Frontier route
        # can have several at once -- the Journal is the only place a player
        # can review the whole branch without walking back to the Guide.
        offers = self.available_adventure_quests()
        if self.journey_won():
            lines.append("The frontier is at peace -- the seal is broken and the realm saved.")
        elif not offers:
            lines.append("Frontier Guide: no further requests.")
        elif len(offers) == 1:
            quest = offers[0]
            status = "ready to trade" if self.wants_satisfied(quest) else "not yet found"
            lines.append(f"Frontier Guide wants: {self.wants_label(quest)} -- {status}")
        else:
            # Five repetitions of "Frontier Guide wants:" is noise, and each
            # one wraps to two lines at this width -- one heading and short
            # indented rows keeps the block scannable and the panel short.
            lines.append("Frontier Guide will take:")
            for quest in offers:
                status = "ready to trade" if self.wants_satisfied(quest) else "not yet found"
                lines.append(f"  {self.wants_label(quest)} -- {status}")
        return lines

    def _draw_journal_panel(self):
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w = 460
        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        # Session 52: this panel's height used to be the constant 470, which
        # exactly fitted the content sessions 45-47 left it holding. A new
        # journey line (which wraps to two lines at this width) pushed the
        # 9x26px automap grid past the bottom edge -- so the height is now
        # measured from the content the same "measure-then-build" way the
        # Shop/Spellbook/trade panels already size themselves, and can't be
        # clipped by a future line either. Everything below is laid out from
        # the same tops as before; only the surface it lands on grew.
        adventure_wrapped = [
            _wrap_text(font, line, panel_w - 20) for line in self._journal_adventure_lines()
        ]
        adventure_h = sum(18 * len(w) for w in adventure_wrapped)
        MAP_H = 24 + 9 * 26  # heading gap + _draw_dungeon_map's 9x9 grid of 26px cells
        panel_h = 32 + len(self.quests) * 18 + 8 + adventure_h + 8 + MAP_H + 34

        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        panel.blit(title_font.render("Quest Log", True, COLOR_TEXT), (10, 8))
        for i, quest in enumerate(self.quests):
            if i < self.quest_index:
                status = "Complete"
            elif i == self.quest_index:
                status = f"{min(self.depths_kills, quest['target'])}/{quest['target']}"
            else:
                status = "Locked"
            line = f"{quest['description']} -- {status}"
            panel.blit(font.render(line, True, COLOR_TEXT), (10, 32 + i * 18))

        # Wayfarer Adventure Mode (see wayfarer/wayfarer_adventure.md): the
        # journey/fragment/guide summary, measured above so the panel is
        # sized to hold it (session 52 -- the three lines used to be built
        # inline here against a fixed panel height).
        y = 32 + len(self.quests) * 18 + 8
        for wrapped_line_group in adventure_wrapped:
            for wl in wrapped_line_group:
                panel.blit(font.render(wl, True, COLOR_TEXT), (10, y))
                y += 18

        map_top = y + 8
        panel.blit(title_font.render("Dungeon Map", True, COLOR_TEXT), (10, map_top))
        self._draw_dungeon_map(panel, 10, map_top + 24)

        hint = font.render("M or Esc to close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, origin)

    def _draw_win_screen(self):
        """Session 47 (Wayfarer Adventure Mode's Final Area, see
        wayfarer_adventure.md): a one-time celebratory modal shown the
        instant the final vault chest opens, reusing run_menu's own
        panel-and-centered-text rendering style per the design doc's own
        suggestion ("reusing run_menu's existing title-screen rendering
        infra") rather than building a separate screen system. Unlike every
        other panel it takes no input beyond "dismiss" (see
        handle_key_down/handle_mouse_down) -- there's nothing to select,
        just a message to read -- and dismissing it drops straight back into
        ordinary play rather than any menu, since Adventure Mode is a wing
        of the game, not the whole of it (the Depths keep going)."""
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        title_font = AssetManager.get_font(28, bold=True)
        font = AssetManager.get_font(15)

        have = sorted(self.artifact_defs[fid]["name"] for fid in self.artifact_fragments)
        route = self.route_def()
        # Session 53: the opening line names all four elements, which is only
        # true of a journey that actually collected all four -- an Open
        # Frontier win can break the seal with three and never set foot in
        # the fourth biome.
        opening = (
            "Ember, frost, storm, and mire -- reunited at last."
            if len(have) >= len(self.artifact_defs)
            else f"{NUMBER_WORDS.get(len(have), len(have)).capitalize()} fragments, "
                 "laid side by side -- and the seal answers."
        )
        lines = [
            opening,
            "The Elder Dragon's seal is broken, and the frontier is at peace.",
            "",
            f"Fragments carried: {', '.join(have)}",
            "",
            # Session 52: which journey this was, and how to get another one.
            # Before journeys existed there was only ever one ending, so the
            # modal had nothing to number and nowhere to point.
            f"Journey {self.journey_index} complete "
            f"({route['name']}, {difficulty_def(self.combat_difficulty)['name']}) -- "
            f"{self.journeys_won} won in all.",
            "The Frontier Guide can set you on a new one whenever you're ready.",
        ]
        wrapped = [_wrap_text(font, line, 520) if line else [""] for line in lines]

        panel_w = 560
        panel_h = 70 + sum(18 * len(w) for w in wrapped) + 50
        panel = self._panel_surface(panel_w, panel_h)
        origin = ((WINDOW_W - panel_w) // 2, (WINDOW_H - panel_h) // 2)

        title = title_font.render("You Win!", True, (230, 200, 110))
        panel.blit(title, ((panel_w - title.get_width()) // 2, 16))

        y = 60
        for wrapped_line_group in wrapped:
            for wl in wrapped_line_group:
                text = font.render(wl, True, COLOR_TEXT)
                panel.blit(text, ((panel_w - text.get_width()) // 2, y))
                y += 18

        hint = font.render("Press any key or click to continue adventuring.", True, (160, 160, 160))
        panel.blit(hint, ((panel_w - hint.get_width()) // 2, panel_h - 32))

        self.screen.blit(panel, origin)

    def _draw_dungeon_map(self, panel, origin_x, origin_y):
        """A room-grid automap of the current Depths floor, centered on the
        player -- every dungeon level is an unbounded plane (see
        procgen.py), so there's no fixed level size to fit on screen, only
        a window around wherever the player currently is. Undiscovered
        cells are simply left blank; (0, 0) is always where both stairs
        live (see engine/save.py's get_discovered_rooms docstring)."""
        font = AssetManager.get_font(14)
        if not self.current_room_id.startswith("proc:"):
            panel.blit(
                font.render("Not in the Depths -- no floor map here.", True, (160, 160, 160)),
                (origin_x, origin_y),
            )
            return

        _, _seed_str, level_str, gx_str, gy_str = self.current_room_id.split(":")
        level, px, py = int(level_str), int(gx_str), int(gy_str)
        visited = self.discovered.get(level, set())

        cell = 26
        radius = 4  # a 9x9 window of rooms around the player
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                gx, gy = px + dx, py + dy
                if (gx, gy) not in visited:
                    continue
                cx = origin_x + (dx + radius) * cell
                cy = origin_y + (dy + radius) * cell
                rect = pygame.Rect(cx, cy, cell - 3, cell - 3)

                color = (220, 180, 40) if (gx, gy) == (0, 0) else (70, 70, 82)
                pygame.draw.rect(panel, color, rect)
                if (gx, gy) == (0, 0) and level > 1:
                    pygame.draw.rect(panel, (170, 140, 220), rect, 3)
                if (gx, gy) == (px, py):
                    pygame.draw.rect(panel, (255, 255, 255), rect, 2)

                doors = room_doors(self.seed, level, gx, gy)
                door_color = (130, 130, 145)
                if doors.get("N"):
                    pygame.draw.rect(panel, door_color, (cx + cell // 2 - 3, cy - 2, 6, 6))
                if doors.get("S"):
                    pygame.draw.rect(panel, door_color, (cx + cell // 2 - 3, cy + cell - 7, 6, 6))
                if doors.get("E"):
                    pygame.draw.rect(panel, door_color, (cx + cell - 7, cy + cell // 2 - 3, 6, 6))
                if doors.get("W"):
                    pygame.draw.rect(panel, door_color, (cx - 2, cy + cell // 2 - 3, 6, 6))


def _draw_menu(screen, options, cursor, confirming_new_game, hit_rects):
    """`hit_rects` is cleared and repopulated with (pygame.Rect, index)
    pairs for each clickable option, mirroring Game._begin_panel_hitboxes'
    pattern for the in-game panels -- run_menu hit-tests clicks against
    whatever this draw call actually put on screen. The Y/N confirmation
    step deliberately gets no hit rects (see run_menu's docstring): erasing
    a save is destructive enough to want a real keypress, not a stray
    click."""
    screen.fill(COLOR_BG)
    title_font = AssetManager.get_font(20, bold=True)
    option_font = AssetManager.get_font(16, bold=True)
    hint_font = AssetManager.get_font(14)

    # Session 25: anchored off WINDOW_H // 2 rather than fixed pixel
    # offsets (140/240/280) tuned for the old 600px-tall window -- those
    # left the menu stranded in the top third of the taller window this
    # session's layout rework produced (see WINDOW_H at the top of the
    # file). Every element still ends up in the same relative spot, just
    # scaled to whatever the window's actual height is.
    mid_y = WINDOW_H // 2
    title = title_font.render("Wayfarer", True, COLOR_TEXT)
    screen.blit(title, (WINDOW_W // 2 - title.get_width() // 2, mid_y - 140))

    hit_rects.clear()
    if confirming_new_game:
        lines = [
            "Erase your current save and start a new game?",
            "Y to confirm, N or Esc to cancel",
        ]
        for i, line in enumerate(lines):
            text = hint_font.render(line, True, COLOR_TEXT)
            screen.blit(text, (WINDOW_W // 2 - text.get_width() // 2, mid_y + i * 22))
    else:
        for i, label in enumerate(options):
            color = COLOR_TEXT if i == cursor else (140, 140, 140)
            prefix = "> " if i == cursor else "  "
            text = option_font.render(f"{prefix}{label}", True, color)
            pos = (WINDOW_W // 2 - 90, mid_y - 40 + i * 34)
            screen.blit(text, pos)
            hit_rects.append((pygame.Rect(pos[0], pos[1], 160, text.get_height()), i))
        hint = hint_font.render("Up/Down select, Enter/click confirm, Esc quit", True, (160, 160, 160))
        screen.blit(hint, (WINDOW_W // 2 - hint.get_width() // 2, WINDOW_H - 40))

    pygame.display.flip()


def run_menu(screen, has_save):
    """Title screen shown before a Game exists. Returns "continue",
    "new_game", or "quit". Same hard-capped, dirty-flag-redraw discipline
    as the main loop, just simpler (no idle throttling -- it's a transient
    screen, not something the game sits in for long). Mouse support
    (session 13) only covers the plain option list -- the New-Game-over-an-
    existing-save Y/N confirmation stays keyboard-only, deliberately: it's
    a destructive action (wipes the save), and a stray click shouldn't be
    able to trigger it the way a deliberate keypress can."""
    options = ["Continue", "New Game", "Quit"] if has_save else ["New Game", "Quit"]
    cursor = 0
    confirming_new_game = False
    clock = pygame.time.Clock()
    dirty = True
    hit_rects = []

    def activate(choice):
        """Resolves a selected option -- shared by Enter/Space and a mouse
        click on that option's row so the two input paths can't drift."""
        nonlocal confirming_new_game, dirty
        if choice == "Continue":
            return "continue"
        elif choice == "New Game":
            if has_save:
                confirming_new_game = True
                dirty = True
            else:
                return "new_game"
        elif choice == "Quit":
            return "quit"
        return None

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit"
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and not confirming_new_game:
                for rect, i in hit_rects:
                    if rect.collidepoint(event.pos):
                        cursor = i
                        dirty = True
                        result = activate(options[i])
                        if result is not None:
                            return result
                        break
            elif event.type == pygame.KEYDOWN:
                if confirming_new_game:
                    if event.key == pygame.K_y:
                        return "new_game"
                    elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                        confirming_new_game = False
                        dirty = True
                elif event.key in (pygame.K_UP, pygame.K_w):
                    cursor = (cursor - 1) % len(options)
                    dirty = True
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    cursor = (cursor + 1) % len(options)
                    dirty = True
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    result = activate(options[cursor])
                    if result is not None:
                        return result
                elif event.key == pygame.K_ESCAPE:
                    return "quit"

        if dirty:
            _draw_menu(screen, options, cursor, confirming_new_game, hit_rects)
            dirty = False
        clock.tick(ACTIVE_FPS)


def main():
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        AssetManager.disable_audio()

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Wayfarer")
    clock = pygame.time.Clock()

    save_probe = SaveManager(SAVE_PATH)
    has_save = save_probe.has_save()
    save_probe.close()

    action = run_menu(screen, has_save)
    if action == "quit":
        pygame.quit()
        sys.exit()

    game = Game(screen, new_game=(action == "new_game"))

    running = True
    is_focused = True
    fps_target = ACTIVE_FPS

    print("Wayfarer running. Arrows/WASD move (bump an NPC to talk; hold to keep walking), left-click an adjacent tile to do the same (hold and drag to keep walking toward the cursor), T disarm a detected trap ahead of you, R rest (free, costs turns, blocked with enemies nearby), 1-8 quick-use item, I inventory, C spellbook, M quest log/map, F3 debug, ESC quit. Panels: click a row to use/cast/buy it, click outside to close.")

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.WINDOWFOCUSLOST:
                is_focused = False
                fps_target = IDLE_FPS
                game.clear_held_input()
                game.dirty = True

            elif event.type == pygame.WINDOWFOCUSGAINED:
                is_focused = True
                fps_target = ACTIVE_FPS
                game.dirty = True

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                game.handle_mouse_down(event.pos)

            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                game.handle_mouse_up()

            elif event.type == pygame.KEYDOWN:
                if game.handle_key_down(event.key):
                    running = False

            elif event.type == pygame.KEYUP:
                game.handle_key_up(event.key)

        # Held-key/held-click continuous movement (session 13) is a timer
        # check, not an event -- ticked once per frame here so it fires at
        # a steady pace regardless of how many (or few) real input events
        # showed up this frame.
        game.tick_move_repeat()

        # The debug overlay redraws continuously so its FPS reading is live;
        # otherwise we only ever redraw on an actual state change.
        if game.dirty or game.debug_overlay:
            game.draw(fps_target, is_focused, clock.get_fps())
            game.dirty = False

        clock.tick(fps_target)

    game.persist()
    game.save.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
