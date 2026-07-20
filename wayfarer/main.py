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

import pygame

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from engine.assets import AssetManager, BASE_DIR
from engine.room import Room
from engine.entity import Player, Enemy, ItemPickup, EquipmentDrop, NPC
from engine.combat import resolve_bump_attack, resolve_spell_hit, enemy_attack, grant_xp, resolve_trap, resolve_disarm
from engine.inventory import Inventory
from engine.save import SaveManager, DEFAULT_ROOM, DEFAULT_SPAWN
from engine.procgen import generate_room, scale_stats_for_level, room_doors
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
COLOR_POISON = (120, 200, 90)
COLOR_DRAIN = (150, 150, 230)
COLOR_LEVITATE = (140, 215, 235)
COLOR_PANEL_BG = (20, 20, 28, 235)
COLOR_PANEL_BORDER = (95, 95, 120)
COLOR_HUD_BG = (17, 17, 24)
COLOR_GOLD = (230, 190, 60)


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
        AssetManager.make_placeholder("switch_off", (150, 40, 40), shape="square")
        AssetManager.make_placeholder("switch_on", (50, 180, 70), shape="square")
        AssetManager.load_sprite("item_key", f"{I}/tile_30_9.png")

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
        AssetManager.load_sprite("player", f"{C}/tile_12_6.png")
        AssetManager.load_sprite("npc_quartermaster", f"{C}/tile_12_12.png")
        AssetManager.load_sprite("npc_merchant", f"{C}/tile_12_27.png")
        AssetManager.load_sprite("npc_healer", f"{C}/tile_12_9.png")
        # Session 19: unarmored, no bow/helmet -- the one portrait in this
        # row that doesn't read as a fighter, picked (via a rendered/
        # labeled contact sheet, same discipline session 9 established) to
        # stand apart from the three already-placed NPCs at a glance.
        AssetManager.load_sprite("npc_scholar", f"{C}/tile_12_21.png")

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
        else:
            enemy_templates = self.room.enemy_templates
            item_templates = self.room.item_templates
            equipment_drop_templates = self.room.equipment_drop_templates

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

        self.enemies = []
        for t in enemy_templates:
            if t["id"] in self.dead_enemy_ids:
                continue
            stats = self.enemy_defs[t["type"]]
            if t.get("level", 1) > 1:
                stats = scale_stats_for_level(stats, t["level"])
            self.enemies.append(Enemy(t["id"], t["type"], t["x"], t["y"], stats))
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
        fixture blocks movement like a wall would."""
        return {(d["x"], d["y"]) for d in self.locked_doors} | {(g["x"], g["y"]) for g in self.gates}

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
        if self.current_room_id.startswith("proc:"):
            epoch, cleared_turn = self._room_meta(self.current_room_id)
            self.save.set_room_meta(self.current_room_id, epoch, cleared_turn)
        self.save.save_game(
            self.player, self.inventory, self.current_room_id, self.seed,
            self.turn_count, self.depths_kills, self.quest_index,
            self.known_spells,
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
                    messages.append(f"Picked up {item.name}.")
                    AssetManager.play_sfx("pickup")
                else:
                    messages.append("Inventory full.")

        elif kind == "locked_door":
            door = result["door"]
            if self.inventory.remove_item("key"):
                self.unlocked_door_ids.add(door["id"])
                self.locked_doors = [d for d in self.locked_doors if d["id"] != door["id"]]
                messages.append("You unlock the door with a key.")
                AssetManager.play_sfx("door")
            else:
                messages.append("The door is locked. You need a key.")

        elif kind == "gate":
            messages.append("An iron gate blocks the way. Find the switch.")

        elif kind == "chest":
            chest = result["chest"]
            if chest["id"] in self.opened_chest_ids:
                pass  # already looted -- just a normal walk-through
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
            stairs_message = {
                "stairs_down": "You descend deeper into the dungeon.",
                "stairs_up": "You climb back up.",
            }.get(exit_data.get("kind"))
            # Flush the room we're leaving *before* load_room overwrites
            # this state with the destination's.
            self.save.set_room_flags(self.current_room_id, self._current_room_flags())
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

    def _healer_rows(self):
        """Rest is always present; Restore Drained Mana only appears once
        there's actually a drain to cure -- same "append an extra action
        only when it applies" pattern session 16 gave the Merchant panel's
        Identify/Remove Curse rows."""
        rows = ["rest"]
        if self.player.mana_drain > 0:
            rows.append("cure_drain")
        return rows

    def healer_move_cursor(self, delta):
        rows = self._healer_rows()
        self.healer_cursor = (self.healer_cursor + delta) % len(rows)
        self.dirty = True

    def activate_healer_row(self, index):
        rows = self._healer_rows()
        if index >= len(rows):
            return
        if rows[index] == "rest":
            self.rest_at_healer()
        else:
            self.cure_mana_drain()
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

    def buy_spellbook(self, spell_id):
        """Same insufficient-gold-is-a-silent-no-op pattern every other gold
        sink in this game uses. No mana/level check -- the whole point is
        buying past the level gate; a level-1 character with enough gold can
        walk out knowing Firebolt."""
        if spell_id in self.known_spells:
            return
        spell = next(s for s in self.spell_defs if s["id"] == spell_id)
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
            healed = min(spell.get("value", 0), self.player.max_hp - self.player.hp)
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
        if self.spellbook_open:
            self._draw_spellbook_panel()
        if self.journal_open:
            self._draw_journal_panel()

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
        for gate in self.gates:
            if not self._is_visible(gate["x"], gate["y"]):
                continue
            sprite = AssetManager.get_sprite("gate")
            if sprite:
                self.room_surface.blit(sprite, (gate["x"] * TILE_SIZE, gate["y"] * TILE_SIZE))
        for door in self.locked_doors:
            if not self._is_visible(door["x"], door["y"]):
                continue
            sprite = AssetManager.get_sprite("locked_door")
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
        if self.player.levitation_turns > 0:
            levitate_text = font.render(f"Levitating ({self.player.levitation_turns})", True, COLOR_LEVITATE)
            self.screen.blit(levitate_text, (status_x, row4_y))

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
            or self.bookshop_open
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
        if key == pygame.K_ESCAPE:
            return not self.close_active_panel()
        if key == pygame.K_F3:
            self.debug_overlay = not self.debug_overlay
            self.dirty = True
            return False
        if key == pygame.K_i and not (self.quest_open or self.shop_open or self.journal_open or self.spellbook_open or self.healer_open or self.bookshop_open):
            self.toggle_inventory()
            return False
        if key == pygame.K_m and not (self.quest_open or self.shop_open or self.inventory_open or self.spellbook_open or self.healer_open or self.bookshop_open):
            self.toggle_journal()
            return False
        if key == pygame.K_c and not (self.quest_open or self.shop_open or self.inventory_open or self.journal_open or self.healer_open or self.bookshop_open):
            self.toggle_spellbook()
            return False

        if self.quest_open:
            if key in (pygame.K_u, pygame.K_RETURN):
                self.claim_quest_reward()
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

        hint = font.render("Up/Down or 1-8 select, U/click use/equip, I/Esc close", True, (160, 160, 160))
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
            else:
                line = f"{prefix}Restore Drained Mana (-{self.player.mana_drain} MP) ({self.drain_cure_cost()}g)"
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

    def _draw_journal_panel(self):
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w, panel_h = 460, 470
        panel = self._panel_surface(panel_w, panel_h)
        origin = self._begin_panel_hitboxes(panel_w, panel_h)

        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

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

        map_top = 32 + len(self.quests) * 18 + 16
        panel.blit(title_font.render("Dungeon Map", True, COLOR_TEXT), (10, map_top))
        self._draw_dungeon_map(panel, 10, map_top + 24)

        hint = font.render("M or Esc to close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

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
