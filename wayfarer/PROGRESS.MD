# Wayfarer — Progress Log

Living document. Update this as work happens so a new chat session can pick
up with full context without re-deriving it. Treat each `## Session N`
entry as a breakpoint you can safely start a fresh conversation from.

## What This Is

A low-footprint desktop dungeon-crawler (Python 3.11+, Pygame-CE) inspired
by Castle of the Winds, Desktop Adventures, and Yoda Stories. Meant to run
in the background while the system does other work — CPU/RAM footprint is a
hard constraint, not a nice-to-have.

## Design Plan (original spec, condensed)

**Performance budget (non-negotiable):**
- Game loop hard-capped at 30 FPS (`clock.tick(30)`), never uncapped.
- On focus loss: throttle to ~5 FPS, keep polling input, skip rendering
  when nothing changed.
- Dirty-flag rendering — only redraw on actual state change.
- No per-frame allocation in the hot loop — cache everything at load time.
- Target: <3% CPU idle, <15% CPU in combat, <150MB resident.
- Window 640x480 or 800x600, unscaled pixel art, no shaders.
- Sound: load once, no re-decoding; music off by default.

**Game design:**
- Single-screen "rooms" (not scrolling maps), fixed grid, instant transitions.
- Top-down grid movement, bump-to-attack melee combat.
- Slot-based inventory, items used via hotkey or inventory screen (which
  pauses the sim).
- Stats: HP, mana (spent on spells, session 12 -- originally an unused
  "stamina" placeholder), XP/leveling.
- Hand-authored rooms first; procedural generation was originally a stretch
  goal, explicitly deferred in the first pass, then greenlit in session 2.

**Save/load:** single SQLite file, autosave on room transition only (never
per-frame/per-tick).

**Explicitly out of scope (still true):** networking, controller support,
scrolling maps.

## Architecture Notes

```
wayfarer/
  main.py              # Game class + idle-aware capped loop, HUD, input
  engine/
    assets.py           # sprite/font/sfx cache, procedural placeholder sprites
    room.py              # Room class, JSON loading, dispatches "proc:" ids to procgen
    procgen.py           # deterministic seed-based room generator (the Depths)
    entity.py            # Entity/Player/Enemy/ItemPickup/NPC, Enemy.take_turn() AI
    combat.py            # bump-attack resolution, leveling, enemy_attack(), grant_xp()
    inventory.py         # slot inventory, item effects (heal, buff_attack)
    equipment.py          # gear slots, buy/upgrade logic (session 8);
                           # per-instance enchant/curse (session 16)
    spells.py             # newly_learned() level-gate scan (session 12)
    save.py              # SQLite save/load, room_flags/room_meta/discovered_rooms tables
  data/
    items.json, equipment.json, enemies.json, npcs.json, quests.json, spells.json
    rooms/town_hub.json, armory.json, crypt.json  # hand-authored (session 10:
                                                    # replaced start_hall.json)
  assets/sprites/...    # 16x16 tiles (session 9), pre-sliced from four
                         # user-supplied sheets into characters/items16/
                         # dungeon_v2/overworld subfolders -- overworld is
                         # now used (session 10, town_hub's tileset).
                         # dungeon_v2 also holds a few hand-cropped fixture
                         # sprites (chest_closed/open.png, gate_bars.png)
                         # pulled directly from source pixel coordinates
                         # rather than the row/col slice grid -- see session
                         # 10's notes on the sheet's mixed 16px/32px regions.
                         # Original 64x64 dungeon_tileset_1/2 folders are
                         # still on disk but no longer referenced by code.
  assets/sfx/...         # synthesized .wav files, see tools/gen_sfx.py
  tools/
    gen_sfx.py            # one-off sfx synthesizer (stdlib wave/math, no deps)
```

Key decisions worth knowing before touching this code:

- **Turn model:** movement is discrete/grid-stepped, driven by KEYDOWN
  events (not held-key polling). Enemies act once per player action
  (`Game._run_enemy_turns`, called from `Game._take_turn`), not on a timer —
  this is what keeps combat CPU-cheap and is why there's no per-frame AI
  tick anywhere.
- **No humanoid sprite exists** in the source tileset. The player is a
  procedurally-drawn placeholder circle (`AssetManager.make_placeholder`,
  drawn once and cached like any other sprite). The skeleton enemy reuses a
  skull-face decoration tile.
- **Tile size is 64px, matching the source art exactly** — window is
  800x600 to fit a 10x8 room at native scale plus HUD margins. (This was
  originally mismatched at 48px/640x480 and caused visible sprite overlap;
  fixed in session 2.)
- **Procedural dungeon ("the Depths"):** reached via the Crypt's east exit.
  Rooms are addressed by `(seed, level, gx, gy)` (room id
  `proc:{seed}:{level}:{gx}:{gy}`) and *regenerated deterministically every
  time* — no room geometry is ever written to the save file, only the run's
  `dungeon_seed`, per-room `room_flags` (which enemies/items in *visited*
  rooms are gone), and per-room `room_meta` (epoch + cleared_turn, see the
  respawn note below). Neighboring rooms on the same level agree on shared
  doorways via a canonical edge hash (`procgen._edge_open`), so
  connectivity is guaranteed without any cross-room bookkeeping. Room id
  `"proc:ENTRY"` is a sentinel the Crypt's JSON uses (it can't know the
  per-save seed ahead of time); `main.py` resolves it to
  `proc:{seed}:1:0:0` at transition time. Every level's `(0, 0)` room has
  guaranteed stairs down (and, `level > 1`, stairs up) at fixed interior
  cells — see session 4 below. Layout/exits (including stairs) are a pure
  function of `(seed, level, gx, gy)` alone; only enemy/item rolls depend
  on `epoch`, which is what lets a cleared room repopulate without its
  shape ever changing. `Room.load()` structure-caches a proc room forever
  under any epoch — `Game.load_room()` re-fetches that room's *current*
  epoch's population itself on every visit rather than trusting the cached
  copy (see session 4).
- **Autosave ordering matters.** On a room transition, the OLD room's
  flags must be flushed to DB *before* `load_room()` overwrites the
  in-memory `dead_enemy_ids`/`taken_item_ids` tracking sets, and the player
  row must be saved *after* `load_room()` so `current_room`/position reflect
  where the player actually ended up. (Session 2 found and fixed a bug
  where this was backwards — autosave was recording the room being left and
  its exit-tile position, so death/reload teleported players one room
  backward. See `Game.handle_move`'s `"exit"` branch.)

## Completed

### Session 1 — initial scaffold
- Full directory structure, idle-aware capped game loop (30 FPS active /
  5 FPS on focus loss), dirty-flag rendering.
- Room/Entity/Player/Enemy classes, JSON room loading (ascii wall/floor
  grid + exits/enemies/items lists).
- Bump combat resolution + XP/leveling.
- Basic inventory: pick up, view, use one consumable type (potion).
- SQLite save/load: player stats, inventory, current room/pos, per-room
  flags (dead enemies, taken items).
- Three hand-authored rooms (Entry Hall → Armory → Crypt), one enemy type
  (skeleton), one item type (potion).
- F3 debug overlay (FPS target/actual, active/idle mode, room, position).
- Verified headless (SDL dummy driver): move/collide, fight, level up,
  pick up/use item, room transition, save→quit→reload round-trip.

### Session 2 — AI, deeper inventory, procedural wing, bug fixes
- **Fixed tile/window size mismatch**: TILE_SIZE 48→64 (matches native
  sprite size), window 640x480→800x600.
- **Enemy AI**: `Enemy.take_turn()` — chases player within an aggro radius
  via greedy grid stepping, bump-attacks when adjacent, idle-wanders
  otherwise. Turn-based (see Architecture Notes above), so it's free at
  idle. Added `combat.enemy_attack()` for enemy-initiated hits.
- **Inventory expansion**: second item type (`whetstone`, permanent +2
  attack) to prove multi-effect support; number-key (1-8) quick-use both
  during normal play (consumes a turn) and inside the inventory screen.
- **Procedural dungeon wing** (`engine/procgen.py`): deterministic
  seed-based room generation reached through a new Crypt exit. Verified:
  multi-room traversal, exact coordinate/connectivity correctness between
  neighboring rooms, and full determinism (clearing the room cache and
  regenerating produces an identical layout).
- **Bug fix**: autosave-on-transition ordering (see Architecture Notes).
- Verified headless with screenshots: tile alignment, HUD, debug overlay,
  inventory screen, enemy chase behavior, hotkey item use, the Depths room
  rendering and connectivity.

### Session 3 — sfx, content breadth, depth-scaled Depths
- **Sound effects exist now.** `tools/gen_sfx.py` synthesizes five short
  `.wav` files (hit, kill, pickup, levelup, door) directly with stdlib
  `wave`/`math` — no external audio assets, consistent with the
  load-once/no-streaming performance budget. It's a one-off generator, not
  something that runs at game startup; the `.wav` files it produced are
  checked into `assets/sfx/` like any other asset. Wired up:
  `Game._load_assets` now calls `AssetManager.load_sfx` for all five;
  `play_sfx("pickup")` fires on item pickup and `play_sfx("door")` on room
  exit (both previously silent), `play_sfx("levelup")` fires from
  `combat._grant_xp`. `hit`/`kill` were already wired in session 1/2, just
  had no files to play.
- **Two new enemy types**: `slime` (weak, `hp10/atk2`, reuses the green
  orb decoration tile from tileset 1 as `enemy_slime`) and `cultist`
  (strong, `hp30/atk6/def2`, no matching tile in either source tileset so
  it's a procedural placeholder like the player — `make_placeholder`,
  magenta rounded-square so it reads as distinct from the player's blue
  circle). Both in `data/enemies.json`.
- **One new item type**: `shield` (reuses the skull-emblem shield tile as
  `item_shield`), effect `buff_defense` — permanent +2 defense, mirrors
  `whetstone`'s `buff_attack`. Required adding the `buff_defense` branch to
  `Inventory.use_item` (`engine/inventory.py`); no other code needed
  changes since item defs are fully data-driven.
- **Depth-scaled Depths** (`engine/procgen.py`): `_depth(gx, gy)` is
  Manhattan distance from the Crypt entrance `(0, 0)`; `_tier()` buckets
  that into shallow/mid/deep, and `ENEMY_WEIGHTS_BY_TIER`/
  `ITEM_WEIGHTS_BY_TIER` weight `_weighted_choice()` per tier — shallow
  rooms skew slime/potions, deep rooms skew cultist/permanent buffs. Deep
  rooms can also spawn one more enemy (`max_enemies` 2→3 at tier 2) and
  roll for loot more often (0.6→0.75). Still a pure function of
  `(seed, gx, gy)` — determinism is unaffected and was re-verified.
- **Hand-authored rooms got a light touch** to introduce the new content
  in-fiction: `start_hall`'s skeleton is now a slime (gentler first fight),
  `armory` got a shield pickup alongside its existing potion.
- Verified headless (SDL dummy driver): all five sfx load without error,
  new sprites resolve, slime dies in the expected number of hits and
  grants XP, shield pickup + use raises `player.defense` by exactly 2,
  `enemy_defs` ordering (`cultist.hp > skeleton.hp > slime.hp`) holds,
  procgen determinism holds (`generate_room` called twice with the same
  args is byte-identical), and weighted sampling across 200 seeds at fixed
  shallow (depth 1) vs. deep (depth 20) coordinates shows the expected
  skew (shallow: slime 151/skeleton 47/no cultist; deep: cultist 169/
  skeleton 93/slime 49). Also booted the real `main()` loop end-to-end
  (queued an immediate `QUIT` event under the dummy driver) to confirm no
  import/init regressions; confirmed the pre-existing `save.db` (a live
  level-9 save from prior manual testing) was untouched by using a
  scratch DB path for all of the above.

### Session 4 — "living dungeon": dungeon levels, stairs, depth scaling, respawn

Goal (user-driven): Wayfarer felt like static rooms that only got *easier*
as stats went up — nothing was actually happening. Session 4 is phase 1 of
a 3-phase roadmap toward a *Castle of the Winds* feel (phase 2: randomized
item affixes; phase 3: town hub + NPC/quest layer — both future work, not
started).

- **The Depths gained real verticality.** Room ids are now
  `proc:{seed}:{level}:{gx}:{gy}` (previously `proc:{seed}:{gx}:{gy}`,
  flat/infinite). Every floor's `(0, 0)` room has two guaranteed interior
  tiles — a `stairs_down` at local `(2, 1)` (always present) and, for
  `level > 1`, a `stairs_up` at `(7, 1)` back to `level - 1`. Level 1's
  `(0, 0)` keeps the original hardcoded west link to the Crypt; deeper
  levels don't touch the Crypt at all. Both are just regular `exits` list
  entries with a `"kind"` field — `Room.exit_at`/`Player.try_move` needed
  no changes, they're already coordinate-generic. `Room.draw` picks a
  distinct sprite by `kind` (new gold/violet placeholders,
  `stairs_down`/`stairs_up`, since neither source tileset has stairs
  tiles). **Breaking change**: old `save.db` entries pointing at the old
  3-coordinate proc room id format are no longer parseable — this is a
  local gitignored dev save, so no migration was written; a fresh save is
  needed after this lands.
- **Enemies actually get tougher with depth now**, not just more
  cultist-weighted: `procgen.scale_stats_for_level()` boosts hp/xp by 20%
  and attack by +1 per dungeon level (defense +1 every 3 levels), identity
  at level 1 so floor-1 balance is unchanged. Baked in via a `"level"`
  field on each generated enemy template; `main.py`'s `load_room` applies
  the scaling when present, so hand-authored rooms (no `"level"` key) are
  untouched.
- **Cleared Depths rooms repopulate over time instead of staying dead
  forever.** New `room_meta(room_id, epoch, cleared_turn)` save table plus
  a `turn_count` column on `player` (global count of player actions —
  turns, not wall-clock time, so this stays free at idle same as
  everything else). `procgen.generate_room()` now takes an `epoch` param
  that seeds *only* the enemy/item RNG stream (`pop_rng`) — layout/exits
  stay a pure function of `(seed, level, gx, gy)` alone, so a room's shape
  never changes across a respawn, only its contents, and enemy/item ids
  are epoch-suffixed so a new cycle can't collide with old `dead_enemy_ids`.
  When a Depths room's enemies are all dead, `Game` records
  `cleared_turn`; on re-entry, if `turn_count - cleared_turn >=
  RESPAWN_THRESHOLD` (150 player actions), the epoch bumps and that room's
  `dead_enemy_ids`/`taken_item_ids` flags reset. Hand-authored rooms
  (Entry Hall/Armory/Crypt) are untouched by any of this — they're the
  safe hub layer and stay cleared-once-forever, matching genre convention.
  Writes still only happen on room transition/quit (`persist()` and the
  early flush in `handle_move`'s `"exit"` branch both gained a
  `set_room_meta` call alongside the existing `set_room_flags` call) —
  never per-frame.
- Verified headless (SDL dummy driver, scripted smoke tests, no pytest
  suite exists yet): `generate_room` determinism per
  `(seed, level, gx, gy, epoch)`, level-based stat scaling (slime hp 10->18
  attack 2->6 at level 5), layout/exits identical across epochs at a fixed
  room while enemy/item ids differ, stairs presence/absence exactly where
  expected (level 1 `(0,0)`: down + Crypt link, no up; level 2 `(0,0)`:
  both; other rooms: neither), a full in-game stairs round trip (Crypt →
  Depths L1 → down to L2 → up back to L1), a full clear-respawn cycle
  (kill everything in a room, fast-forward `turn_count` past
  `RESPAWN_THRESHOLD`, leave and re-enter, confirm epoch bumped and flags
  reset), save/load round trip for `turn_count`/`room_meta`, and a full
  `main()` boot under a queued immediate `QUIT` event. All runs used a
  scratch DB path; confirmed the real `save.db` (pre-existing from prior
  manual testing) was untouched (mtime check before/after).

### Session 5 — loot tiers: minor/normal/greater magnitude, depth-weighted

Phase 2 of the Castle-of-the-Winds roadmap (see session 4's context).
Every item was a single fixed-value entry — a potion was always +15hp
forever. This session gives each of the three item families three
magnitude tiers, matching CotW's actual convention for consumables
(it really does name potions "Minor"/plain/"Greater" — continuous
prefix/suffix affix rolls in CotW apply to equipment, which this game
still deliberately doesn't have, so tiered magnitude is the right scope,
not a compromise).

- **`data/items.json`** split `potion`/`whetstone`/`shield` into
  `{family}_minor` / `{family}` (unchanged key + value, so hand-authored
  rooms need no changes) / `{family}_greater`, each with its own
  name/value/description and a new `"family"` field. Roughly minor ≈ 0.5×
  and greater ≈ 1.7× the original value (potion heal 8/15/26, whetstone
  attack +1/+2/+4, shield defense +1/+2/+4).
- **Zero changes to `Inventory` or `Inventory.use_item`** — this was the
  key design win. Since each tier is just a distinct `item_type` string,
  the existing dict-of-counts stacking model and the generic
  value/name/effect lookup in `use_item` handle tiers automatically; a
  Health Potion and a Potion of Greater Healing simply occupy separate
  stacks. No save schema change, no per-instance item tracking.
  Verified directly (picking up `potion` + `potion_greater` yields two
  separate `as_list()` entries).
- **`engine/procgen.py`**: after a Depths item roll picks a family (as
  before, via `ITEM_WEIGHTS_BY_TIER`), a second weighted roll
  (`MAGNITUDE_WEIGHTS_BY_TIER`, keyed by the same depth/level `tier` enemy
  scaling already uses) picks minor/normal/greater — tier 0 never rolls
  greater, tier 2 favors it. Both rolls share the existing epoch-scoped
  `pop_rng` stream from session 4, so a respawned room re-rolls magnitude
  too. Hand-authored rooms keep referencing the plain family keys, so town
  loot stays curated/unchanged.
- **Visual tier indicator**: `AssetManager.make_tier_variant()` (new,
  `engine/assets.py`) copies a base item sprite once and stamps a small
  corner dot — grey for minor, gold for greater, no dot for normal — cached
  forever like `make_placeholder`, nothing per-frame. Registered in
  `Game._load_assets`.
- Verified headless (SDL dummy driver): every family has exactly 3 tiers
  with strictly increasing value; magnitude distribution across 300 seeds
  each at tier 0 and tier 2 confirms the intended skew (tier 0: 0 greater
  rolls, minor > normal; tier 2: greater > minor); normal/greater potions
  stack separately in `Inventory`; `use_item` applies each tier's own
  value (minor potion heals 8, greater heals 26, greater whetstone gives
  +4 attack); full `main()` boot with all 9 item defs resolving a sprite,
  scratch DB, real `save.db` confirmed untouched (mtime check).

### Session 6 — town quest-giver: NPC + kill-quota quest ladder

Phase 3 of the Castle-of-the-Winds roadmap (session 4's context) — and the
last of the three originally agreed phases. There was no reason to
explore beyond raw combat/loot; this gives runs a goal. Deliberately kept
to one NPC and a short authored ladder rather than a full dialogue/quest
subsystem — see the scope note below.

- **New `NPC` entity** (`engine/entity.py`) — stationary, no `take_turn`
  (unlike `Enemy`). `Player.try_move` gained an `npcs` param and a new
  check between the enemy-attack check and the walkability check: bumping
  an NPC returns `{"type": "npc", ...}` without moving onto its tile, same
  non-committal-bump pattern as attacking an enemy. `Room.npc_templates`
  reads a room's `"npcs"` list (new, optional, defaults to `[]` — proc
  rooms never define one, so NPCs only ever exist in hand-authored rooms).
  A single **Quartermaster** (`data/npcs.json`, amber placeholder circle —
  no townsfolk tile in either source tileset, same reasoning as the
  player/cultist placeholders) lives in the Entry Hall at `(7, 2)`
  (`data/rooms/start_hall.json`), clear of the existing slime/potion/exit.
  `Game._run_enemy_turns`'s `occupied` set now includes NPC tiles so a
  wandering slime can't path onto the Quartermaster. Bumping the NPC opens
  the quest panel and returns before `_take_turn` (like the `"exit"`
  branch already does) — talking never gives a nearby enemy a free hit.
- **Quest ladder** (`data/quests.json`): 5 authored tiers, all keyed off
  one cumulative counter, `Game.depths_kills` — every enemy kill inside a
  `proc:` room increments it (hand-authored-room kills don't count); this
  also means phase 1's room-respawn mechanic feeds it directly, since a
  repopulated room is more kills toward the next quest. Targets 5/15/30
  get phase 2's tiered items as rewards (`potion_greater`/
  `whetstone_greater`/`shield_greater` — no new item types needed);
  targets 50/75 grant flat XP via `combat.grant_xp` (renamed from the
  module-private `_grant_xp`, since it's now called from outside
  `combat.py` too). Once all 5 are claimed, the Quartermaster has nothing
  further to offer — open-ended/procedural quest generation beyond the
  authored ladder is future work, not built now (see below).
- **Save schema**: `player` gained `depths_kills`/`quest_index`
  (`engine/save.py`, same `ALTER TABLE ... ADD COLUMN` try/except
  migration pattern as `turn_count` in session 4), threaded through
  `load_game`/`new_game_defaults`/`save_game` alongside it.
- **Quest panel UI** (`main.py` `_draw_quest_panel`/`quest_open`/
  `close_quest_panel`/`claim_quest_reward`/`current_quest`) mirrors the
  existing inventory overlay's visual style and input-blocking pattern —
  `K_u`/`K_RETURN` claims when the target's met, `K_ESCAPE` closes it,
  `K_i` is guarded not to open the inventory over it. Claiming an item
  reward with a full inventory fails gracefully (message, `quest_index`
  does *not* advance, matching the existing pickup-when-full behavior) so
  the player can come back once they've made room.
- Verified headless (SDL dummy driver): quest/NPC data loads and
  cross-references cleanly (targets strictly increasing, every
  `reward_item` exists in `items.json`); `Player.try_move` returns `"npc"`
  without moving the player; bumping the Quartermaster opens the panel
  *and* leaves the Entry Hall's slime at full HP (confirming no enemy
  turn fired); claiming below target and past the exhausted ladder are
  both no-ops; all 5 tiers claim correctly in order (items land in
  inventory, XP tiers level the player up); a forced-full inventory
  blocks an item claim without advancing `quest_index`; a kill in
  `start_hall` (hand-authored) leaves `depths_kills` unchanged while a
  kill after walking to the Depths increments it; full `main()` boot
  under a queued immediate `QUIT` event, scratch DB, real `save.db`
  confirmed untouched (mtime check).

This closes out the 3-phase Castle-of-the-Winds roadmap agreed at the
start of session 4. Genuinely open follow-on work, not yet scoped into a
session: open-ended/infinite quest generation beyond the 5 authored
tiers, additional NPCs (a healer, a blacksmith who *upgrades* rather than
just sells tiered items), and — the biggest one — actual equipment with
slots, which the game has deliberately avoided so far (see "No
equip/drop mechanics" below) and would be a prerequisite for real
Diablo/CotW-style prefix+suffix item affixes rather than the discrete
minor/normal/greater tiers session 5 shipped.

### Session 7 — main menu (Continue / New Game), and a live save-compat crash fix

Not part of the original 3-phase roadmap — user-reported bug plus a
follow-on request. The session 4 room-id format change
(`proc:seed:gx:gy` -> `proc:seed:level:gx:gy`) crashed on load for a
save file created before that change (`Room.load` unpacking 5 values
from a 4-part id). Fixed with a narrow, non-destructive migration rather
than requiring a fresh save:

- **`engine/save.py`**: `_migrate_room_id()` upgrades any stored
  old-format proc room id to level 1 (where that flat plane always was)
  the moment it's read back in `load_game()` — the single place state
  comes off disk, so both `Game.__init__` and `_handle_death`'s fresh
  reload get it automatically. Self-healing: the first autosave after
  load writes the upgraded id back, so this only ever runs once per save.
  Verified against a *copy* of the user's actual save (a real level-10
  character stuck at the old-format id) before shipping the fix, then
  confirmed live: the user re-ran the game and it resumed correctly
  (since verified further at level 14, 160/160 hp, 53 Depths kills, all
  in the new format).
- **The actual follow-on request**: launching always resumed the last
  save with no way to start over, which is what surfaced the crash in
  the first place. Added a title screen (`run_menu()` in `main.py`,
  shown before any `Game` exists) offering **Continue** (only shown if
  `SaveManager.has_save()`) and **New Game**, plus **Quit**. Selecting
  New Game over an existing save requires a Y/N confirmation (it's
  destructive) before wiping progress via a new `SaveManager.reset()`
  (deletes all rows from `player`/`inventory`/`room_flags`/`room_meta`,
  schema untouched) — `Game.__init__` gained a `new_game` param that
  calls `reset()` before the existing `load_game() or
  new_game_defaults()` fallback, so a wiped save falls through to
  `new_game_defaults()` with zero duplicated reset logic. Same
  hard-capped-loop/dirty-flag-redraw discipline as the main game loop,
  just simpler (no idle throttling — it's a screen you pass through
  quickly, not one the game idles in).
- Verified headless (SDL dummy driver): `has_save()` false on a fresh DB
  and true after a first persist; menu options are exactly
  `["New Game", "Quit"]` with no save and `["Continue", "New Game",
  "Quit"]` with one; keyboard navigation (Up/Down/Enter) selects the
  right action; New Game's confirm step correctly no-ops on N/Esc
  (returns to the menu, doesn't wipe) and wipes+resets on Y; a
  `new_game=True` boot actually resets level/inventory/room even when a
  leveled-up, item-holding prior save exists; full `main()` boot under a
  queued immediate `QUIT` (now resolved from the menu, before a `Game` is
  even constructed) with the real `save.db` confirmed untouched by the
  test run itself (its mtime changes were from the user's own play
  session in between, not from any script here — checked read-only,
  never operated on the live file directly, only copies/scratch DBs).

### Session 8 — gold economy, equipment slots, and a quest/map journal screen

User-driven request, guided by *Castle of the Winds*: "a full equipment
inventory system, gold to buy/upgrade gear, and a quest tracking screen
with a map of the current dungeon floor." Three coupled features, each
built to reuse an existing pattern rather than invent a new one.

- **Gold.** `Player.gold` (new, starts at 15). Enemies grant it on kill
  alongside XP — `data/enemies.json` gained a `gold_reward: [min, max]`
  range per type (skeleton 3-6, slime 1-3, cultist 8-15),
  `combat.resolve_bump_attack` rolls it in and folds it into the same
  defeat log line. `procgen.scale_stats_for_level` scales it with dungeon
  level the same way it already scales hp/xp. Gold can also be found on
  the ground: a **new `"gold"` item family** in `data/items.json`
  (minor/normal/greater = 5/12/25) rides the *existing* session-5
  family+magnitude weighted-roll system in `procgen.py` (just added to
  `ITEM_WEIGHTS_BY_TIER`) — zero new procgen mechanism needed. The one
  special case is in `main.py`'s pickup handling: an item whose def has
  `"effect": "gold"` adds straight to `player.gold` and is removed from
  the room without ever touching `Inventory` — gold isn't slot-limited.
- **Equipment** (`engine/equipment.py`, new, + `data/equipment.json`, new).
  Five slots — weapon/shield/helmet/armor/boots — each holding at most one
  item. **Scoping decision**: gear is bought and upgraded from a new
  Merchant NPC with gold, *not* found as dungeon loot or dropped by
  enemies. This mirrors session 5's affix-scoping call for the same
  reason: real per-instance gear (find a sword, it might roll differently
  from another sword) would need item-instance tracking this codebase has
  deliberately avoided everywhere else. Shop-only gear keeps every
  equipment item a fixed, data-driven `item_type` string exactly like the
  tiered consumables — `sword`/`shield`/etc. tiers are named
  basic/fine/masterwork (e.g. `shortsword` -> `longsword` -> `greatsword`)
  and reuse the *exact* tier-dot sprite convention from session 5
  (`AssetManager.make_tier_variant`, grey/gold corner dot) rather than new
  art. Equipping/unequipping mutates `player.attack`/`defense` directly
  and reversibly (`equip()` always unequips-then-equips so a slot's bonus
  is never double-counted), the same "permanently mutate the base stat"
  mechanism whetstone/shield consumables already use — so **combat.py and
  the HUD needed zero changes** to respect equipped gear. Since the bonus
  is baked into the saved attack/defense values, reloading a save never
  re-applies it; `player.equipment` is persisted purely so the shop UI
  knows what's worn and `unequip()` has a bonus to reverse.
- **Merchant NPC** (`data/npcs.json`, placed in the Armory at (7, 2) —
  thematically the "gear" room). `Player.try_move`'s existing NPC-bump
  branch (session 6) now dispatches on `npc.type`: bumping the
  Quartermaster still opens the quest panel, bumping the Merchant opens a
  new shop panel (`Game.shop_open`, `_draw_shop_panel`). The shop shows
  one row per slot — currently equipped item and the *next* purchasable
  tier and its cost (`equipment.next_offer`), or "finest owned" once
  maxed — so there's never more than 5 choices and no separate buy/sell/
  upgrade menus to navigate. `U`/Enter buys-or-upgrades the selected slot;
  insufficient gold or an already-maxed slot are silent no-ops with a
  message, no crash/negative-gold path.
- **Quest/map journal screen** (`M` key, `Game.journal_open`,
  `_draw_journal_panel`). Two things the user asked for in one screen:
  a full quest-ladder overview (all 5 tiers with Complete/progress/Locked
  status, unlike the NPC dialogue panel which only ever showed the
  *current* quest), and a room-grid automap of the current Depths floor
  centered on the player. The automap needed a new save-backed fact:
  `discovered_rooms(level, gx, gy)` (new table, `SaveManager.
  get_discovered_rooms`/`mark_discovered`), populated the moment
  `Game.load_room` enters a `proc:` room — written through immediately
  (not batched), matching the existing "write on room transition, never
  per-frame" discipline `set_room_flags`/`set_room_meta` already use.
  Door connections between visited rooms are drawn via a **new public
  `procgen.room_doors()`** — a thin wrapper around the already-existing
  `_edge_open()` hash check, four cheap RNG rolls, no full room layout
  built just to look at it. Stairs need no separate "discovered" flag at
  all: every level's `(0, 0)` room is *always* the first room entered on
  that level (guaranteed by how the stairs-down exit's target coordinates
  work, see `procgen.py`), so "visited" and "stairs discovered" are
  provably the same fact — documented on `get_discovered_rooms` so a
  future session doesn't reinvent separate tracking for it. Outside the
  Depths (the three hand-authored town rooms), the map panel just says so
  — see Known Limitations.
- **Save schema**: `player` gained `gold` and five `equip_<slot>` columns
  (same `ALTER TABLE ... ADD COLUMN` migration pattern as every prior
  session's additions); new `discovered_rooms` table. `SaveManager.reset()`
  (New Game wipe) now also clears it.
- Verified headless (SDL dummy driver, scratch DB, no pytest suite yet):
  fresh-game defaults (15 gold, all slots empty); buying a slot's item
  applies exactly that item's attack/defense bonus; upgrading a slot
  replaces rather than stacks (longsword's +4 only, not shortsword's +2
  *plus* longsword's +4); insufficient gold and already-maxed-tier
  purchases are no-ops that don't touch gold or equipment; bumping the
  Merchant opens the shop (not the quest panel) and vice versa for the
  Quartermaster, and neither bump moves the player onto the NPC's tile;
  a gold-effect item pickup increases `player.gold` without consuming an
  inventory slot; killing an enemy increases gold; entering a Depths room
  marks it discovered and `procgen.room_doors` returns all four cardinal
  directions; all four overlay panels (inventory incl. new Equipped
  section, shop, quest, journal/automap both inside and outside the
  Depths) render without exception; a full save->reload round trip
  preserves gold, equipment, and discovered rooms, with the reloaded
  player's `attack` matching exactly (confirming the baked-in-bonus
  approach doesn't double-apply); a full `main()` boot through the actual
  title menu (Enter to start a new game) to a `QUIT` posted on a real
  short timer (rather than pre-queued, which a first pass found gets
  silently dropped by `run_menu`'s own `pygame.event.get()` — a testing-
  harness gotcha, not a game bug) exits cleanly. Real `save.db` confirmed
  untouched (mtime check) throughout, all runs used a scratch DB path.

### Session 9 — real art: four user-supplied spritesheets, native 16px tiles

User-driven request ("can you use spritesheets to improve the appearance of
the game?"), followed by four sheets dropped in `wayfarer/eval/` (a
PC/NPC/monster character sheet, an item/equipment icon sheet, a dungeon
tileset, and an overworld tileset) plus a large pre-sliced UI kit. This
replaced every procedural placeholder the game could replace and, at the
user's explicit choice, changed the engine's tile resolution rather than
just reskinning at the old scale.

- **Sheet analysis, done before any code changed**: native tile size for
  each sheet was *verified*, not assumed from divisibility — grid-line
  overlays were rendered at candidate sizes and checked for content
  bleeding across cell boundaries (a coherent shape getting cut down the
  middle means the wrong size). Result: `sprite_sheet.png` (characters) and
  `_sheet.png` (items/equipment) and `world.png` (overworld) are native
  16x16; `tiles_dungeon_v1.1.png` is native 32x32. All four were sliced
  into individual `tile_<row>_<col>.png` files (a one-off script, same
  naming convention `slice_spritesheet.py` at the repo root already
  established) into `assets/sprites/{characters,items16,overworld,
  dungeon_v2}/` — `dungeon_v2` was downscaled 32px->16px *at slice time*
  (Lanczos) so every sheet the game actually uses is pre-normalized to one
  size, no runtime scaling anywhere. `overworld` was sliced but is **not
  wired into the game** — Wayfarer has no outdoor/hub map concept to use
  it for; it's available if that's ever wanted.
- **The resolution decision** (asked of the user directly, since it
  changes gameplay pacing and requires reauthoring hand-built content —
  not a call to make silently): keep the existing 64px/10x8 room grid and
  upscale the new (smaller) art to fit it, meet in the middle at 32px to
  match the dungeon set natively, or go full native 16px for the biggest
  "more on screen" payoff at the cost of the most rework. **User chose
  full native 16px.**
- **`TILE_SIZE` 64 -> 16.** New `ROOM_TILES_W/H` constants (40x32, exactly
  4x the old 10x8) replace the hardcoded `10 * TILE_SIZE`/`8 * TILE_SIZE`
  in `main.py`. This keeps `ROOM_PIXEL_W/H` at exactly 640x512 either way
  (40*16 = 10*64, 32*16 = 8*64) — same window, same `ROOM_ORIGIN`, same HUD
  layout; only the number of tiles visible in that same pixel footprint
  changed. This is the whole point of the ask and was checked directly
  (`ROOM_PIXEL_W, ROOM_PIXEL_H == (640, 512)`).
- **`engine/procgen.py`**: `WIDTH, HEIGHT` 10,8 -> 40,32; `MID_X, MID_Y`
  20,16; `STAIRS_DOWN_CELL`/`STAIRS_UP_CELL` repositioned to stay clear of
  doors in the bigger room. The hand-authored Crypt<->Depths link
  (`target_room, target_x, target_y = "crypt", 8, 4`) was hardcoded to the
  *old* Crypt size and had to be updated by hand to `38, 16` (one step in
  from Crypt's new east door) — everything else in the file already
  derived its numbers from `WIDTH`/`HEIGHT`/`MID_X`/`MID_Y` and needed no
  changes beyond the constants. **Enemy/item density was bumped to match**:
  a 40x32 room has ~24x the interior floor space of the old 10x8 one, so
  `max_enemies` (8/12 by tier, was 2/3) and item rolls (now up to 3-4
  independent rolls per room instead of a single one-or-nothing roll) were
  scaled up too — otherwise the bigger room would just look emptier, not
  "more on screen." These multipliers are a first-pass judgment call, not
  a tuned balance number; easy to retune, still a pure function of
  `(seed, level, gx, gy, epoch)`.
- **`data/enemies.json`**: every `aggro_range` scaled 4x (skeleton 4->16,
  slime 2->8, cultist 5->20) so a given enemy notices the player from the
  same *actual* on-screen distance as before — aggro_range is in tile
  units, and a tile is now a quarter the size, so leaving the numbers
  alone would have quietly quadrupled each enemy's effective sight range
  relative to the room.
- **The three hand-authored rooms** (`start_hall`/`armory`/`crypt`) were
  regenerated at 40x32 (simple bordered rectangle, same shape convention
  as before, generated via a script rather than hand-edited to avoid
  transcription errors across 32-line layout strings). Exit coordinates
  were *not* naively multiplied by 4 — each door/landing pair was
  rederived from the same "near = door cell on this room's own border,
  far = one step in from the border you're crossing" convention
  `procgen._exit_point` already uses, since a couple of the old numbers
  (e.g. the Crypt<->Depths landing) were constants (always "1 step in"),
  not proportional to room width. `save.DEFAULT_SPAWN` moved from (2, 4)
  to (8, 16) to stay in the same relative spot (west side, mid-height) in
  the bigger Entry Hall.
- **Sprite curation** (`Game._load_assets`, `engine/assets.py`): every
  entity that had a plausible match got real art —
  - Player: a blue-clad archer (character sheet), chosen to echo the
    original placeholder's blue.
  - Skeleton, Cultist: a bony white warrior and a dark hooded robed
    figure, both found by scanning labeled contact-sheet crops of the
    character sheet's monster rows.
  - Quartermaster, Merchant: two more character-sheet portraits (silver
    knight, gold-trimmed trader), visually distinct from each other and
    from the player/enemies.
  - **Slime deliberately kept as the original procedural placeholder** —
    the character sheet is exclusively bipedal humanoids, no blob/round
    monster anywhere in it. Forcing a humanoid sprite onto "slime" would
    have been a worse result than the clean placeholder circle.
  - Wall/floor/exit/stairs-down: picked from the dungeon sheet's brick,
    plain-floor, archway, and stone-steps tiles respectively.
  - **`stairs_up` has no second matching graphic in the sheet** — solved
    with a new `AssetManager.make_tint_variant()` (multiplies a violet
    color wash over a copy of the `stairs_down` sprite via
    `BLEND_RGB_MULT`, which leaves the alpha channel — and so the
    silhouette — untouched). Same "derive a variant from one base image"
    spirit as session 5's tier-dot trick, different technique because a
    corner dot doesn't read at 16px the way it did at 64px.
  - Every consumable tier (potion/whetstone/shield/gold, each
    minor/normal/greater) and every equipment tier (5 slots x
    basic/fine/masterwork) got **three genuinely distinct pieces of art**
    from the item sheet, picked for a visible quality progression (e.g.
    plain gray sword -> silver longsword -> gold ornate greatsword) —
    this replaces session 5's color-dot-on-one-image tier convention
    entirely for these items, since the new sheet has real art variety to
    draw on. `AssetManager.make_tier_variant` (the dot-stamping helper)
    is consequently dead code and was removed along with its last
    callers; `make_tint_variant` is the only sprite-derivation helper left
    besides `make_placeholder`.
  - `AssetManager.make_placeholder`'s default size and internal
    proportions (outline width, facing-notch radius, corner radius) were
    all rescaled from a size-64 assumption to be proportional to whatever
    `size` is passed (still defaults to 16 now) — the slime placeholder
    and the load-failure fallback surface (also resized 64->16) are the
    only two placeholders left standing.
- Verified headless (SDL dummy driver, scratch DB): `TILE_SIZE`/
  `ROOM_TILES_W/H`/`ROOM_PIXEL_W/H` have the expected values; a full game
  boot produces **zero** `[ASSET WARNING]` output (every hand-picked
  `tile_<row>_<col>.png` path actually exists — a real risk given how many
  coordinates were picked by hand off labeled contact sheets); every
  swapped-in sprite loads at exactly 16x16; `stairs_up` is pixel-distinct
  from `stairs_down`; the full equipment buy/upgrade/persist suite from
  session 8 still passes unchanged; a room-to-room walk of the entire town
  chain (Entry Hall -> Armory -> Crypt -> Depths, both directions) lands
  the player at the exact expected tile each time; sampling 25 Depths rooms
  confirms the bumped enemy/item density actually shows up (max 11
  enemies / 4 items seen in the sample, vs. the old 2-3 / 0-1 ceiling); a
  Depths room is confirmed 40x32; all four overlay panels render without
  exception. **Also visually inspected** (not just asserted in test code)
  by rendering real screenshots of the Entry Hall, Armory, a Depths room,
  the shop panel, the inventory panel, and the journal/automap panel under
  the SDL dummy driver — confirmed sprites tile cleanly with no seams/
  overlap, entities are visually distinct from each other and from the
  floor, and panel text stays legible against the new tile background.
  Real `save.db` confirmed untouched (mtime check).

### Session 10 — dynamic Depths rooms (sub-rooms/corridors/locks/chests), room-based fog of war, overworld hub

User-driven request, building directly on session 9's resolution bump:
"since the rooms are so much bigger, can we make them more dynamic" (walls,
doors, switches, gates, locked doors, chests, big rooms holding smaller
rooms and corridors) plus a room-based fog of war ("revealing the entire
small room and leaving them revealed"), and separately, using the
session-9-sliced-but-unwired `overworld` sheet for an actual town hub. Two
builds in one pass — see the approved plan at the time
(`typed-spinning-comet.md`) for the full design rationale; this entry
covers what actually shipped and what changed from that plan during
implementation.

- **`engine/procgen.py`'s `generate_room()` no longer floods the whole
  40x32 interior as one open rectangle.** Each cell is now a fixed 2x2
  grid of "core" rooms (`GRID_COLS/GRID_ROWS`), each carved at a random
  size/position within its grid cell (`_carve_room_in_cell`), connected by
  a **randomized spanning tree** of L-shaped corridors (`_spanning_tree`,
  shuffle + union-find) plus the leftover graph edges as extra plain
  shortcuts. A new `layout_rng` stream (`f"{seed}:layout:{level}:{gx}:{gy}"`,
  no epoch) drives all of this — kept strictly separate from the existing
  epoch-scoped `pop_rng`, preserving the pre-existing invariant that a
  room's shape survives a respawn.
- **Solvability guarantee, and why it's a vault, not a gated tree edge.**
  The approved plan's original design gated one of the spanning tree's
  redundant ("loop") edges. Implementing it exposed a real flaw: a loop
  edge only ever reconnects two rooms *already* reachable via the tree, so
  locking one gates nothing — the player could just take the tree path
  instead. The shipped design instead attaches an optional **vault**
  (`_place_vault`) to one core room via exactly one connector cell, which
  becomes either a locked door or a switch-gated gate. Because the vault's
  *only* connection point is that lock, every core room, every open edge
  door, and the stairs cell stay reachable using zero locks, unconditionally,
  by construction — not something that needs checking room-by-room, it
  falls out of the topology. Verified anyway (see below), since a
  construction argument is only as good as its implementation.
  `VAULT_CHANCE_BY_TIER` (0.3/0.5/0.7) controls how often one appears.
- **Locked doors need a key; gates need a switch.** Exactly one `key` item
  (new, `data/items.json`, effect `"none"` so pressing U in the inventory
  screen can't waste it — see the `Inventory.use_item` fix below) is
  generated per locked door, placed in a core room reachable without any
  lock. Gates instead get a paired `switch` placed the same way, permanent
  once triggered (walking onto it opens its gate forever, no toggle back).
  **Vault/lock/gate/switch/chest/region ids are deliberately *not*
  epoch-suffixed**, unlike enemies/items/plain-floor-loot — a solved vault
  stays solved, and seen map territory stays seen, across a room's
  150-turn repopulation cycle. This is the same "structural vs. epoch-
  scoped" split the codebase already had for layout/exits vs. population;
  it just now also covers this new state. A key, being a normal item a
  player carries, *does* keep the usual epoch-suffixed id — only the lock
  it opens is permanent.
- **Room-based fog of war** (`Game.revealed_regions`, `Room.region_at`).
  `generate_room()` additionally returns a `regions` list — one entry per
  core room, vault, and corridor segment, each either a rect or an
  explicit cell list (corridors aren't rectangles) — and `Room` compiles
  that once into a sparse `(x, y) -> region id` dict at load time.
  `Room.draw()` takes a `revealed_regions` set and renders solid black for
  any tile whose region isn't in it; `Game._is_visible()` gates
  enemy/item/NPC/fixture rendering the same way, so nothing in an unseen
  region spoils itself in the corner of the screen. A region is revealed
  the moment the player's own tile resolves to it
  (`Game._reveal_region_at_player`, called on room entry and after every
  move) and, like the lock state above, persists forever via `room_flags`
  — "leaving them revealed" was a literal requirement, not just "while in
  the room." **Hand-authored rooms with no `regions` field are simply
  never fogged** (`Room.draw`'s fog path is skipped entirely when
  `self.regions` is empty) — zero effect on the hub or Armory.
- **`save.py`'s `get_room_flags`/`set_room_flags` were generalized** from
  two hardcoded flag types (`enemy_dead`/`item_taken`) to a fully generic
  `{flag_type: {entity_id, ...}}` shape. This is a **zero-migration**
  change — same table, same columns, just no longer special-casing which
  flag types exist — and is what let `region_seen`/`door_unlocked`/
  `gate_open`/`chest_opened` ride in without touching the schema at all.
  All three existing callers in `main.py` (`load_room`, `persist`, the
  `"exit"` branch) were updated to the new dict shape; a new
  `Game._current_room_flags()` builds it in one place so those three
  callers can't drift out of sync with each other.
- **`Inventory.use_item` no longer consumes an item that had no effect.**
  Found while wiring up keys: pressing U on an item with no `heal`/
  `buff_attack`/`buff_defense` effect used to silently consume it anyway
  (just printing "has no effect"). That would have let a stray U-press
  waste a key from the inventory screen instead of it only ever being
  consumed by bumping the matching locked door. Small, generally-correct
  fix, not key-specific. New `Inventory.remove_item()` is the actual path
  a key gets consumed through.
- **Interactive fixtures are drawn by `Game`, not baked into `Room`'s
  grid.** Chests and switches always exist in their list and just change
  which sprite they pick (closed/open, off/on); locked doors and gates are
  removed from `Game.locked_doors`/`Game.gates` entirely once solved, so
  "not in the list" doubles as their open state — nothing extra to track.
  `Player.try_move` grew matching branches: locked doors/gates are
  non-committal bumps (like attacking or talking), chests/switches are
  walk-onto (like picking up an item) — see `engine/entity.py`'s updated
  docstring for the full priority order.
- **Overworld hub** (`data/rooms/town_hub.json`, new `DEFAULT_ROOM`,
  replaces `start_hall`). Uses the `world.png` sheet sliced back in
  session 9: grass floor, hedge-tree border, plus a building marker
  (-> Armory) and a cave-mouth marker (-> Crypt), both just regular
  `exits` entries with new `kind` values reusing the exact mechanism
  `stairs_down`/`stairs_up` already established for a kind-specific
  sprite. **`Room` gained a `tileset` field** (default `"dungeon"`) so
  `Room.draw()` picks `wall_<tileset>`/`floor_<tileset>` — the only engine
  change this needed. The Quartermaster now stands in the hub itself
  (quest-giving happens in the open square); the Merchant stays inside
  Armory, which shrank from a full 40x32 dungeon room down to a cozy
  14x10 shop interior (no monsters — it's a shop) now that it's reached
  through a building rather than being a waypoint on a linear room chain.
  **Crypt got the "light touch" from the approved plan**: hand-placed
  (not procedurally generated) into two regions connected by a passage,
  plus one hand-placed locked door guarding a small vault with a chest
  (`shield_greater`) — using the exact same region/lock/chest machinery
  Part 1 built, as a low-stakes hand-authored demonstration of the
  mechanic before the player reaches the Depths proper. This is a
  breaking change to old local saves' room references (`start_hall` is
  gone, Armory/Crypt coordinates changed) — no migration, same precedent
  session 4 already set for local gitignored dev saves.
- Verified headless (SDL dummy driver, scratch DB): the BSP output is
  deterministic per `(seed, level, gx, gy)` and provably unaffected by
  epoch (layout/exits/regions/locks byte-identical across epochs sampled,
  only enemies/items differ); a lock-free BFS from each sampled room's
  landing point reaches every core room, every open edge door, and every
  locked door's key / gate's switch (146 rooms sampled in the final
  regression pass, 0 failures — the solvability guarantee actually holds,
  not just by argument); the full hub -> Armory -> hub -> Crypt -> Depths
  chain lands the player at the exact expected tile at every hop; the
  Crypt's fog reveals `entry_hall` on entry and `back_hall`/`vault` only
  after the player physically reaches them; a locked door blocks without
  a key, unlocks and consumes exactly one key when the player has one, and
  the unlock survives a save/reload; a chest grants its loot exactly once
  and re-visiting an opened one is a no-op; a switch opens exactly its
  linked gate and nothing else; both the Quartermaster (in the hub) and
  Merchant (in Armory) are still reachable and open the right panel; every
  new sprite (hub tiles, chest/gate/door states, key icon) loads at 16x16
  with zero `[ASSET WARNING]`s; a full `main()` boot through the real
  title menu to a `QUIT` exits cleanly. **Also visually inspected** via
  real rendered screenshots: the hub (grass, hedge border, building/cave
  markers, both NPCs), the Crypt with fog partially revealed vs. fully
  solved (chest message included), and a Depths room with an unrevealed
  corridor rendering as solid black next to a visible locked door/gate —
  confirmed fog reads as fog rather than a rendering bug, and no sprite
  seams/overlap anywhere. Real `save.db` confirmed untouched throughout.

### Session 11 — fog-of-war bug fix: walls/doors near region edges rendered as solid black

User-reported ("in the crypt the walls are just black and the doors are black,
so I can't tell where the doors or other passages and rooms are except by
trying to walk into them"). Root-caused to two separate bugs in the
session-10 region/fog system and the exit-tile rendering, both fixed in
`engine/room.py` (plus one call site in `main.py`); no data files changed,
so every existing room (hand-authored and procedural) is fixed for free.

- **Bug 1 — region rects never covered wall tiles or door gaps.**
  `regions` (session 10) are defined purely over floor extents — a core
  room's rect, a corridor's cell list — never the wall ring around them.
  `Room.draw`'s fog check was a strict `region_at(x, y) in
  revealed_regions`, so any tile with no region of its own (which is *every*
  wall tile in the game, plus every hand-authored door gap cut through a
  border wall) rendered `COLOR_FOG` solid black forever, regardless of how
  thoroughly the room next to it had been explored. This is what made walls
  and doors visually identical — both were just black. Fixed with a new
  one-time-computed `Room._border_regions` (`(x, y) -> set of neighboring
  region ids`, built alongside `_region_grid` in `__init__`) and a new public
  `Room.is_revealed(x, y, revealed_regions)`: a tile with its own region
  checks membership as before, a tile with none is revealed the moment *any*
  neighboring region is (a wall is visible from the room beside it; it
  doesn't need its own region). `main.py`'s `Game._is_visible` (gates
  enemy/item/NPC/fixture rendering) called the old strict check directly —
  switched to the same `Room.is_revealed` so a locked door or gate sitting
  in a border gap doesn't stay invisible after the room beside it is
  revealed (this was a second, independent instance of the exact same
  strict-membership bug, caught after the first fix only made the
  *background* tile under a locked door visible, not the door fixture
  drawn on top of it in `main.py`'s `_draw_fixtures`).
  Solid multi-tile-thick rock with no floor tile adjacent on any side
  (e.g. the slab hand-guarding the Crypt's vault) correctly stays black —
  there's no vantage point that would ever see it, same as any roguelike's
  fog convention; this is expected, not a residual bug.
- **Bug 2 — the generic door/exit overlay sprites were drawn *instead of*
  the floor tile, not on top of it.** `dungeon_v2`'s archway graphic
  (`tile_6_0.png`, used for any exit with no specific `kind`, which is every
  plain doorway in the Crypt and every unlabeled procedural room-edge exit)
  and several `kind`-specific sprites (`stairs_down`, the hub's `building`
  marker) are partially-transparent decorative overlays — most of each
  sprite's pixels are meant to let the floor underneath show through. Since
  `Room.draw` picked *either* the floor sprite *or* the exit/kind sprite per
  cell and the room surface is cleared to pure black every frame
  (`Game.draw`'s `room_surface.fill((0, 0, 0))`), an exit tile's mostly-
  transparent overlay was composited straight onto black, reading as almost
  solid black itself. Fixed by always drawing the floor sprite first for
  any non-wall cell, then blitting the exit/kind overlay on top if present
  — matches how this art was evidently authored to be used. `cave` (fully
  opaque) is unaffected either way; the harmless extra floor blit under it
  is free since `Room.draw` only ever runs on a dirty-flag redraw, not
  per-frame.
- Verified: rendered the Crypt via `Room.draw` directly at several
  `revealed_regions` states (none/partial/all) and confirmed walls read as
  wall texture once their neighboring region is revealed, door gaps show a
  visible archway breaking the wall silhouette, and still-unexplored areas
  stay solid black; same check against a generated Depths room (previously
  every corridor wall rendered black even fully revealed — now the whole
  layout reads clearly) and the town hub (no `regions` defined, confirmed
  still entirely unfogged, zero behavior change). Then booted the real
  `main()` `Game` end-to-end (scratch DB) and walked the hub -> Crypt path
  in-process (`Game.handle_move`, not just `Room.draw` in isolation): the
  Crypt's west/east doors render as a visible archway notch in the wall,
  and the hand-placed locked door guarding the vault renders as a
  distinct gold-tinted lattice at the edge of the revealed back hall,
  clearly distinguishable from the plain wall beside it, confirmed via
  cropped/zoomed screenshots. Timed 500 `Game.draw` calls on a live game
  instance post-fix (0.32ms average) to confirm the new per-tile border
  lookup doesn't threaten the 30 FPS budget. Real `save.db` untouched
  throughout (every run used a monkeypatched `SAVE_PATH`/scratch DB, mtime
  confirmed unchanged).

**Follow-on same-session bug, user-reported**: "a door I went through took
me to a room with nothing in it... couldn't move up, left, or right, but
moving down put me on the previous screen in a wall next to the door" —
walking through it again looped back to the original wall. Root-caused to
a bug in `engine/procgen.py`'s `generate_room()`, in the loop that carves
each open edge exit — pre-existing since session 10's sub-room rework, not
something session 11's fog fix touched.

- **Every single north/south room transition in the Depths landed the
  player on a wall tile.** Confirmed by generating ~4300 rooms across many
  seeds/levels/coordinates and checking every N/S exit's target coordinate
  against the actual neighboring room's layout: 100% landed on a wall (`#`),
  0% on floor. East/west exits were unaffected (100% landed on floor) —
  the bug was direction-specific, not a general regression.
  Root cause: the door-to-interior corridor was carved from the door tile
  itself to the nearest core room via `_carve_corridor`, whose L-shape
  always runs its horizontal leg first (along the *door's own row*) and
  its vertical leg second (along the *core room's own column*). For an
  east/west door, the landing point a neighboring room computes
  (`_exit_point(direction, "far")`) sits one column in from the door but on
  the *same row* — exactly the row the mandatory horizontal leg sweeps
  across on its way to the core room, so it was carved as floor by sheer
  construction. For a north/south door, the equivalent landing point sits
  one *row* in from the door but on the *same column* as the door — and
  the corridor's horizontal leg runs along the door's row (not the
  landing point's), only reaching that column later via the vertical leg,
  which travels down the *core room's* column instead, not the door's.
  So the landing tile was floor only when a core room coincidentally
  centered itself exactly on the door's column — vanishingly rare. Landing
  on that wall tile, the only adjacent floor was the door tile itself one
  step back (the only way out was retracing your steps), and the
  symmetric bug on the room you'd just left meant walking back through
  landed you on an equally isolated wall tile there too — the exact
  two-room ping-pong the user hit.
- **Fix**: carve *and* connect the "one step in from the door" cell
  explicitly, rather than assuming the corridor to the nearest core room
  would pass through it. `in_x, in_y = near_x - ddx, near_y - ddy` (one
  step inward along the direction vector already in scope) is set to floor
  alongside the door tile, and the corridor to the nearest core room now
  starts from `(in_x, in_y)` instead of the door tile — guaranteeing the
  exact cell a neighboring room's "far" landing point resolves to is
  always floor and always connected to that room's interior, regardless of
  which border it sits on.
- Verified: re-ran the same ~4300-room exhaustive check post-fix — 0
  failures on all four directions (previously 100% failure on N/S alone).
  Re-confirmed layout/region/exit determinism is unaffected by `epoch`
  (session 10's core invariant) and re-ran the session-10-style BFS
  solvability sweep (every exit and every locked door reachable from a
  room's own entry point, no room geometry changes) across the same
  sample with 0 failures, so the fix doesn't compromise either existing
  guarantee. Then reproduced the exact user scenario live through the real
  `Game` class (scratch DB): loaded a room with a generated south exit,
  walked onto the door, confirmed the landing tile in the neighboring room
  is walkable and has more than one open direction (back through the door,
  *and* further into that room's interior) rather than being a dead end.

### Session 12 — spell system (Castle of the Winds' auto-learned magic)

User-driven request, explicitly Castle-of-the-Winds-inspired: given a choice
between wiring up spells/mana or building CotW's randomized cursed/enchanted
item loot, the user picked spells — the smaller architectural lift, since it
plugs into the existing "mutate a base stat" and "data-driven effect string"
patterns rather than needing the per-instance item tracking this codebase
has deliberately avoided since session 5 (still true, still future work).

- **Mana replaces the session-1 "stamina" placeholder.** `stamina`/
  `max_stamina` (tracked since session 1, never consumed by anything) are
  gone; `Player.mana`/`max_mana` take their place, same role (a resource
  pool on the player), now with an actual consumer. **Breaking change to
  the local save schema** — same precedent as session 4's room-id format
  change and session 10's `start_hall` removal: `save.db` is a local
  gitignored dev save with no migration promised, so the DB columns were
  renamed outright rather than carrying two names forward. `max_mana`
  grows +5 and refills on level-up in `combat.grant_xp`, mirroring how
  `max_hp`/`attack` already grow there.
- **Spells are learned automatically by level, not bought or found** — the
  auto-learn half of CotW's spell system (the other half, buying a
  spellbook to learn out of order, is explicitly not built — see Known
  Limitations). `data/spells.json` is a plain ordered list (5 spells:
  Spark/attack, Minor Heal/healing, Stone Skin/defense, Firebolt/attack,
  Blink/movement, unlocking at levels 1/2/3/4/5) rather than keyed by id,
  since `engine/spells.py`'s `newly_learned(spell_defs, level, known_ids)`
  scans it in order looking for any `unlock_level <= level` not yet in the
  known set — a pure, side-effect-free function, same split `equipment.py`
  already has between "pure rule" (there) and "needs live Room/Entity
  state, lives on Game" (targeting/casting, in `main.py`). `Game.
  _learn_new_spells` is called after every attack (melee or spell-kill) and
  after an XP-reward quest claim, and once silently at boot so a returning
  save catches up to any level it already qualifies for — cheap (a
  5-element scan) and safe to call unconditionally since it's a no-op when
  nothing new qualifies.
- **Casting only happens from the Spellbook panel** (new `C` key, mirrors
  the Inventory/Shop/Quest/Journal panel family exactly — cursor, `U`/Enter
  to act, Esc to close, guarded against opening over another panel).
  Unlike inventory items (which are free to use from the paused Inventory
  screen — see session-1 notes — and only cost a turn via the 1-8 field
  hotkey), **every spell cast always costs a turn**, including from the
  panel. Deliberate: a bolt spell directly damages an enemy, so a
  free-from-a-paused-menu cast would let the player fight risk-free in a
  way using a healing potion never could. No field quick-cast hotkey was
  added this session (numbers 1-8 are already item slots) — see Known
  Limitations.
- **Targeting reuses `Player.facing`**, already tracked and updated on
  every move attempt (even a blocked one, i.e. bumping a wall) since
  session 1 — no new aiming UI needed. `Game._bolt_target` walks tile by
  tile along the facing direction up to the spell's `range`, stopping at
  the first wall/closed locked-door-or-gate (blocks line of sight, not
  just movement) or the first live enemy found, whichever comes first.
  `Game._resolve_blink` does the same walk but for the player's own
  movement — slides up to `range` tiles, stopping just short of a wall,
  closed lock, or any enemy/NPC tile (landing exactly on an exit tile is
  fine; it just behaves like a normal step onto it next turn).
- **A spell kill needed to reuse melee's on-defeat handling, not
  reimplement it** — gold roll, XP grant/level-up, kill sfx were pulled out
  of `combat.resolve_bump_attack` into a shared `combat._apply_defeat`, and
  a new `combat.resolve_spell_hit` (damage + `_apply_defeat` on death, no
  counter-hit since the enemy was never adjacent) is what
  `Game.cast_selected_spell`'s bolt branch calls. Missing this on the first
  pass silently gave zero XP/gold for a spell kill — caught by the headless
  verification below, not inspection, which is exactly the kind of
  duplicated-logic bug the shared helper now prevents by construction.
- **Stone Skin's temporary +defense is a separate additive field, not a
  mutate-then-reverse stat** like whetstone/shield/equipment's *permanent*
  bonuses use. Session 8's equipment module is explicit that its
  mutate-the-base-stat pattern only works because the bonus never needs to
  un-apply itself without help; a timed buff does, and doing that via
  mutation would silently strand the bonus forever on a save/reload that
  happens mid-buff (no countdown would survive to know when to reverse
  it). Instead `Player.buff_defense_bonus`/`buff_defense_turns` are plain
  persisted fields, read additively by `combat.py`'s two damage formulas
  (`enemy.attack - (player.defense + player.buff_defense_bonus)`) and
  ticked down once per player turn by a new `Game._advance_turn` (now the
  single place `turn_count` increments — `handle_move`, `quick_use_item`,
  and spellcasting all route through it, replacing three separate raw
  `turn_count += 1` sites, specifically so the buff countdown can't be
  wired into only some of them and drift). One consequence worth knowing:
  the cast's own turn-consumption tick fires *after* the buff is set, so a
  `duration: 12` buff shows 11 turns remaining immediately after casting
  (12 turns of total existence including the cast turn itself, 11 more
  after it returns) — confirmed intentional and covered by the
  verification below, not an off-by-one bug.
- **Mana potions** (`mana_potion_minor`/`mana_potion`/`mana_potion_greater`,
  `data/items.json`) ride the exact family+magnitude weighted-loot system
  session 5 built and session 8 already extended once for `gold` — just
  another entry in `procgen.ITEM_WEIGHTS_BY_TIER` and a new `restore_mana`
  branch in `Inventory.use_item` (mirrors the existing `heal` branch,
  capped at `max_mana`). No sprite art in the source sheets reads as a
  mana potion, so they're derived the same way session 9's `stairs_up`/
  session 10's `gate`/`locked_door` already are — `make_tint_variant` blue-
  tinting the existing health-potion art per tier, rather than hand-picking
  unverified new sheet coordinates. One of each is also placed by hand in
  the Armory and the Crypt (alongside their existing curated pickups) so a
  new character can reach one without depending on Depths RNG.
- **HUD gained a mana bar** (blue, under the HP bar) and the room viewport
  shifted down 16px (`ROOM_ORIGIN` y: 40 -> 56) to make room for it without
  crowding the level/XP line — window size, room pixel footprint, and
  message-log position are otherwise unchanged.
- Verified headless (SDL dummy driver, scratch DB, no pytest suite yet): a
  fresh character knows exactly `{spark}` at level 1 with full mana; a
  large XP grant levels the player up several times and `known_spells`
  matches the full set of `unlock_level <= player.level` spells afterward,
  with mana refilled; casting Spark deducts its mana cost, damages an
  enemy standing in the player's facing direction, and consumes a turn; a
  bolt kill removes the enemy, grants XP/gold (and, confirmed separately,
  does *not* increment `depths_kills` when the kill happens outside a
  `proc:` room, matching melee's existing behavior); casting with
  insufficient mana is a full no-op (turn not consumed, "Not enough mana."
  shown); Minor Heal restores exactly its value capped at max HP; Stone
  Skin's bonus is present immediately, still present after 10 further
  turns (11 total ticks, 1 remaining), and cleared exactly on the 12th
  tick; a direct combat.py check confirms `buff_defense_bonus` actually
  reduces incoming damage (5 -> 1 against a cultist in the same scenario
  with/without the buff), not just that the field gets set; Blink moves
  the player strictly along the facing axis and only as far as the nearest
  obstruction; a mana potion picked up and used restores exactly its
  value; a full save-perist/reload round trip preserves `known_spells`,
  `mana`, and both buff fields exactly; sampling 300 procgen seeds at a
  fixed depth confirms `mana_potion` rolls actually occur and every rolled
  item type resolves against `data/items.json` (no `KeyError` risk from
  the new procgen entry); `Game.draw()` does not raise with the Spellbook
  panel open or closed; a full `main()` boot through the real title menu
  to a `QUIT` posted on a real short timer exits cleanly. **Also visually
  inspected** via rendered screenshots: the HUD's new mana bar sits cleanly
  under the HP bar with no overlap into the room viewport, and the
  Spellbook panel (word-wrapped descriptions, added after the first render
  showed Spark's description clipped past the panel edge) reads cleanly
  with the cursor, mana costs, and hint line all legible. Real `save.db`
  confirmed untouched (mtime check) throughout, all runs used a scratch DB
  path.

### Session 13 — mouse controls

User-driven request ("add mouse controls"). Scoped deliberately around this
engine's existing discrete, turn-per-input-event model (see Architecture
Notes) rather than adding pathfinding, click-and-hold, or hover state --
every click just does whatever the equivalent keypress would have, so no
new game logic was needed anywhere, only new ways to reach the same calls.

- **Room clicks move/act exactly like an arrow key.** `Game.
  handle_room_click` converts a click's screen position to a room-local
  tile, then reduces it to a single-step direction toward that tile
  (whichever axis has the larger offset; ties/adjacent tiles resolve the
  same way) and calls the *existing* `handle_move(dx, dy)` unchanged --
  every interaction an adjacent tile can trigger (attack, pickup, talk to
  an NPC, open a door, step on a chest/switch, take an exit) already
  worked through that function, so clicking one just works too, with zero
  new interaction logic. Clicking a tile more than one step away takes one
  step toward it, same as holding the matching arrow key would -- there is
  still no pathfinding or diagonal movement anywhere in this engine, on
  keyboard or mouse. Clicking the player's own tile, or anywhere outside
  the room viewport (HUD, message log, letterboxed margins), is a no-op.
  No click-and-hold/continuous-move support either: every action here is
  one discrete turn per input event, which is what keeps the loop
  idle-cheap, and continuous mouse-held movement would need a per-frame
  poll that breaks that.
- **Panel clicks reuse each panel's own draw pass to know what's
  clickable**, rather than main.py maintaining a second copy of every
  panel's layout math. New `Game._begin_panel_hitboxes(panel_w, panel_h)`,
  called at the top of all five `_draw_*_panel` methods, computes the
  panel's centered screen rect once (`self.panel_outer_rect`, also now
  what each method's final `self.screen.blit(panel, origin)` uses, so the
  rect used for hit-testing and the rect actually drawn to can't drift
  apart) and resets `self.panel_click_targets` for that method to append
  `(row_rect, callback)` pairs to as it lays out each row -- Inventory,
  Shop, and Spellbook append one per row (select-and-immediately-act, e.g.
  `_click_cast_spell` sets the cursor and calls the exact same
  `cast_selected_spell` a keyboard Enter press would); the Quest panel
  appends one only over its "claim your reward" line, only when a reward
  is actually claimable; the read-only Journal panel appends none (its
  `_begin_panel_hitboxes` call still exists, purely for the outer rect
  below). Since layout is recomputed by the same code every redraw
  (Spellbook's rows are variable-height due to word-wrapped descriptions,
  session 12 -- the cached-rect approach sidesteps needing to duplicate
  that wrapping logic just to find a click target), stale hitboxes from a
  previous frame are never a concern.
- **Clicking outside an open panel closes it**, and Esc now goes through
  the same path: `Game.close_active_panel()` (closes whichever single
  panel is open, since only one ever is) replaced the four-way
  if/elif chain main.py's Esc handler used to duplicate, and
  `handle_panel_click` calls it too when a click lands outside
  `panel_outer_rect` but doesn't hit a row. One shared implementation
  instead of two copies that could silently drift (e.g. a future new
  panel type added to one chain and not the other).
- **The title menu got the same treatment, with one deliberate
  exception.** `_draw_menu` now also builds `hit_rects` (same pattern,
  passed in and repopulated rather than stashed on an object since the
  menu runs before any `Game` exists) for the plain Continue/New Game/Quit
  list, and a small nested `activate(choice)` closure in `run_menu` is
  shared by both Enter/Space and a mouse click so the two input paths
  resolve a selection identically. **The New-Game-over-an-existing-save
  Y/N confirmation stays keyboard-only** -- no hit rects are built for it
  at all. That screen exists specifically to gate a destructive action
  (wiping the save), and a misclick shouldn't be able to trigger what a
  deliberate keypress guards.
- **Two panel hint lines had to widen their panel to fit**, not shrink
  their text: adding "/click" to the Inventory and Shop hint strings
  pushed them past their panel's width (measured directly with
  `font.size()`, not eyeballed) -- `_draw_inventory`/`_draw_shop_panel`'s
  `panel_w` grew 340->400 and 400->460 respectively rather than trimming
  the hint to something less clear. Caught by rendering and inspecting
  real screenshots before/after, the same discipline prior sessions
  (9-11) already established for this codebase's visual work.
- Verified headless (SDL dummy driver, scratch DB, no pytest suite yet): a
  click on the player's immediate-east tile moves them exactly one step
  east and consumes exactly one turn; a click five tiles east and one tile
  south steps only east (the dominant axis); clicking the player's own
  tile and clicking outside the room viewport are both confirmed no-ops
  (no turn consumed, no position change); clicking an adjacent enemy
  attacks it via the existing bump-combat path without the player
  stepping onto its tile; clicking an Inventory row uses that item
  (confirmed via the resulting HP change); clicking outside an open
  panel's rect closes it; clicking a Spellbook row casts that spell (mana
  spent) and closes the panel; clicking a Shop row spends gold and
  equips the offered item in the right slot; a full `main()` boot through
  the real title menu to a `QUIT` posted on a real short timer exits
  cleanly with all the new mouse plumbing in place. **Also visually
  inspected** via rendered screenshots: the widened Inventory and Shop
  panels' hint lines both read fully on-screen with no clipping (the bug
  the width bump above fixes), and the Spellbook/Journal panels still
  render correctly with the new hitbox bookkeeping active. Real `save.db`
  confirmed untouched (mtime check) throughout, all runs used a scratch DB
  path. The existing session-12 spell-system headless suite was re-run
  unchanged afterward and still passes in full, confirming none of this
  touched spell resolution itself.

### Session 14 — user-reported "keyboard stopped working" + held-input movement

User report right after session 13: keyboard controls stopped working,
plus a follow-on request for held-input continuous movement (both
click-and-hold toward the cursor, and holding a direction key) since
one tap/click per tile was too slow to actually play with.

- **Root cause of the keyboard report was never conclusively reproduced**
  -- session 13's inline `main()` KEYDOWN dispatch was re-read line by
  line and is logically sound (confirmed again by the new tests below,
  which now drive keyboard input through the *exact* method the live loop
  calls, not just the underlying `Game` methods in isolation the way
  session 12/13's suites did -- a wiring bug specifically in event-to-
  dispatch code would not have been caught by either prior suite, only by
  calling `handle_move`/`cast_selected_spell`/etc. directly, which are a
  layer removed from what a real keypress actually triggers). The leading
  suspect, worth knowing even though it isn't a bug: **any open panel
  captures ALL keyboard input**, including arrow keys -- always true, not
  new this session -- and session 13's click-to-move made it much easier
  to open one by accident (clicking one tile from an NPC talks to them,
  same as a keyboard bump). A player testing the new click-to-move who
  clicked near the Quartermaster or Merchant without noticing the panel
  open would find every arrow key "dead" until Esc, which reads exactly
  like "keyboard stopped working." This session's refactor doesn't change
  that panels-capture-input behavior (removing it would break the actual
  panels) but does make Esc's behavior more robustly correct (see below),
  and the new held-input work below happened to require restructuring
  this exact code path anyway.
- **Input dispatch moved off `main()`'s inline event loop and onto `Game`
  as real methods** (`handle_mouse_down`/`handle_mouse_up`/
  `handle_key_down`/`handle_key_up`/`tick_move_repeat`), each taking a raw
  key/pos rather than a pygame `Event`. `handle_key_down` reproduces
  session 13's exact if/elif shape (Esc -> F3 -> I/M/C -> per-panel cursor
  nav -> movement/quick-use), just as a method returning `True` when it
  means "quit" so `main()` still owns the `running` flag; nothing about
  *what a key does* changed, only *where that logic lives*. The concrete
  win: this is now something a headless test can drive directly and
  exhaustively (see verification below) instead of only being exercisable
  by posting real SDL events into a live window -- if a wiring regression
  like the reported one recurs, there's now a test layer positioned to
  catch it.
- **Holding a direction key keeps walking.** `MOVE_KEYS` (new, module
  level) maps every movement key to its `(dx, dy)` once, shared by the
  initial `handle_key_down` press and by repeat, instead of the two
  needing to agree independently. On a movement keydown (no panel open),
  `Game` now also records which physical key is driving movement
  (`held_move_key`) and its direction (`held_move_dir`) plus a
  `next_move_repeat_at` timestamp `MOVE_REPEAT_DELAY_MS` (220ms) out.
  `handle_key_up` clears that -- unless a *different* movement key is
  still physically down (checked live via `pygame.key.get_pressed()`
  rather than tracked by hand), in which case repeat switches to that
  direction instead of stopping, so swapping Right for Down mid-hold keeps
  walking rather than freezing for a frame.
- **Click-and-hold walks toward the cursor, Diablo-style.**
  `handle_mouse_down` arms the same `held_move_dir`-shaped repeat state
  (as `mouse_held`, no fixed direction) after firing the existing single
  click-step; each repeat tick re-reads `pygame.mouse.get_pos()` live and
  re-runs the *existing* `handle_room_click` against wherever the cursor
  currently is, so dragging the mouse while holding the button redirects
  the walk instead of marching toward a stale click point. `MOVE_KEYS`
  reuse aside, no new movement resolution logic was needed for this --
  same one-step-toward-target reduction session 13 already built.
- **Repeat is a once-per-frame timestamp check, not OS key-repeat.**
  Deliberately not `pygame.key.set_repeat()`, which would apply to *every*
  key, not just movement -- holding U in the shop panel would rapid-fire
  purchases, holding a number key would rapid-fire item use, holding I
  would flicker the inventory open/closed at the repeat rate. Polling
  `held_move_dir`/`mouse_held` once per frame in `main()`'s loop
  (`Game.tick_move_repeat`, gated on `not self._any_panel_open()` and the
  player being alive, both re-checked every call so nothing needs to be
  cleared by hand when a panel opens mid-hold) keeps the repeat scoped to
  movement alone, at the cost of one timestamp comparison per frame --
  free next to the existing 30 FPS budget, and zero cost at idle since
  `tick_move_repeat` no-ops immediately when nothing is held.
- **Focus loss now clears any held input** (`Game.clear_held_input`,
  called from `WINDOWFOCUSLOST`). Alt-tabbing away can lose a KEYUP or
  MOUSEBUTTONUP the same way it would for any other application, which
  would otherwise leave `held_move_dir`/`mouse_held` stuck set -- the
  character would keep "walking" once focus returned (or, since
  `is_focused` also throttles the loop to `IDLE_FPS` while unfocused,
  visibly stutter-walk during that window instead of just sitting still).
  Not something session 13 could have hit (no held-repeat existed yet),
  but exactly the kind of gap this session's held-input work needed to
  close proactively rather than leave for a future report.
- **`debug_overlay` moved from a local variable in `main()` onto
  `Game.debug_overlay`**, and `Game.draw()`'s signature dropped the
  now-redundant parameter. Pure follow-on of moving F3's dispatch into
  `handle_key_down`, which no longer has a `main()`-local variable to
  mutate -- `Game` already owns every other piece of "what overlay/panel
  is currently showing" state, so this was a gap, not a new pattern.
- Verified headless (SDL dummy driver, scratch DB, no pytest suite yet),
  this time explicitly through `Game.handle_key_down`/`handle_key_up`/
  `handle_mouse_down`/`handle_mouse_up`/`tick_move_repeat` rather than the
  lower-level methods those call, to actually exercise the dispatch layer
  the bug report implicated: a single arrow keydown (and each of the four
  WASD aliases) moves exactly one tile through this exact path; Esc
  requests quit only when nothing is open and instead closes an open panel
  (and does not request quit) otherwise; I/M/C open/close their panels and
  Down-arrow inside an open panel moves its cursor rather than the player;
  F3 toggles `Game.debug_overlay` directly; holding a key (one real
  keydown followed by repeated `tick_move_repeat` calls with the repeat
  timer forced due, rather than actually sleeping in a test) advances
  several further tiles with no additional keydowns, and stops the instant
  the driving key's KEYUP arrives, while a KEYUP for an unrelated key
  leaves an active repeat untouched; click-and-hold similarly advances
  several tiles toward a monkeypatched live cursor position (needed since
  the SDL dummy driver has no real OS mouse to move) and stops on
  MOUSEBUTTONUP; a held direction that bumps into an NPC opens its panel
  and repeat stops on the very next tick with no separate state to clear;
  `clear_held_input` drops both held-key and held-mouse state; a dead
  player blocks both a fresh keydown move and a forced repeat tick; a full
  `main()` boot through the real title menu to a `QUIT` posted on a real
  short timer exits cleanly with the refactored dispatch in place. The
  session-12 and session-13 suites were both re-run unchanged afterward
  (after updating their calls to `Game.draw()`'s new, shorter signature)
  and still pass in full. Real `save.db` confirmed untouched (mtime check)
  throughout, all runs used a scratch DB path. Also rendered and inspected
  a screenshot with the debug overlay on to confirm `Game.debug_overlay`
  actually drives the on-screen overlay post-refactor, not just the
  underlying flag.

### Session 15 — divination spells, a Healer NPC, and closing the locked-door AI gap

User-driven request: "look up Castle of the Winds and continue development."
Scoped around CotW's actual divination school (Detect Monsters/Detect
Objects) and this codebase's own "additional NPCs (a healer...)" note under
Known Limitations, rather than the much larger per-instance cursed/enchanted
item system CotW also has -- that one's been deliberately deferred every
session it's come up since session 5 (needs per-instance item tracking this
engine has never built) and stays future work, not attempted here. Also
fixed a real latent bug flagged since session 10.

- **Two new spells close out CotW's divination school**: Detect Monsters
  (unlock level 6) and Detect Treasure (unlock level 7), `data/spells.json`,
  auto-learned the same way every spell has been since session 12 -- no new
  mechanism needed there. Both are temporary, room-scoped "see through fog"
  effects (40 turns) rather than a permanent level-wide reveal: this engine
  only ever has one room loaded at a time (see Architecture Notes), so
  scoping the effect to "the room you're standing in" is the honest
  translation of CotW's mechanic here, not a cut-down version of it.
  **New `Game.detect_monsters_turns`/`detect_treasure_turns`**, ticked down
  in `_advance_turn` alongside Stone Skin's existing buff countdown (same
  off-by-one-on-cast behavior, documented and verified the same way session
  12 did for Stone Skin). `Game._is_visible` gained an optional
  `detect_turns` param that bypasses the fog check entirely when > 0; the
  enemy render loop passes `detect_monsters_turns`, the item and chest
  render loops pass `detect_treasure_turns`, and NPCs/switches/gates/locked
  doors are deliberately left on the plain fog check in every call site --
  a detect spell reveals monsters and loot, not the dungeon's fixtures.
  **Deliberately not persisted through save/reload** (unlike Stone Skin's
  buff fields) -- it's a purely visual effect, so losing an active detect on
  quit/reload is low-stakes and this avoids a schema migration for it;
  documented inline where the fields are initialized so a future session
  doesn't wonder why they're missing from `save.py`.
- **New Healer NPC** (`data/npcs.json`, `town_hub.json` at (12, 18), sprite
  `tile_12_9.png` off the character sheet -- picked by rendering and
  visually comparing every unused row-12 portrait against the
  already-placed Quartermaster/Merchant, same "verified, not assumed"
  sprite-selection discipline session 9 established, landing on a
  warm blonde/white/red portrait that reads distinctly as a cleric next to
  the Quartermaster's grey armor and the Merchant's tan headwrap). Bumping
  it opens a new `healer_open` panel (`_draw_healer_panel`, modeled directly
  on the quest panel's single-info-block-plus-one-action-row layout) that
  fully restores HP and mana for gold -- `Game.rest_cost()` is a pure
  function of current HP/mana deficit (1 gold per 2 combined points
  missing, rounded up) so the panel can preview the exact price before the
  player commits, and `rest_at_healer()` mirrors `buy_or_upgrade`'s
  insufficient-gold-is-a-silent-no-op pattern. Resting is free (no gold
  charged) when already at full HP/mana, and deliberately **doesn't consume
  a turn** even when it does charge gold -- unlike a spell cast, it can't
  affect combat outcomes, so there's no risk-free-action concern the way
  session 12 had for bolt spells; it's a pure gold sink. `npc.type`
  dispatch in `handle_move`'s NPC-bump branch, `_any_panel_open`,
  `close_active_panel`, and the I/M/C panel-guard conditions in
  `handle_key_down` all gained the same `healer_open` branch every other
  panel already has -- no new pattern, just extending the existing one to a
  third case (previously only ever `merchant` vs. "everything else").
- **Fixed the session-10-flagged latent bug**: `Enemy.take_turn`'s chase/
  wander stepping only ever checked the `occupied_positions` set it was
  given, which `Game._run_enemy_turns` built from other enemies' and NPCs'
  tiles only -- never the currently-closed locked doors/gates
  `Game._blocked_positions()` already tracks for the player and for spell
  targeting/blink. `_run_enemy_turns` now folds `self._blocked_positions()`
  into that set before calling `take_turn`, one line, no changes needed in
  `entity.py` itself since `occupied_positions` was already a generic
  "don't step here" collision set -- this was a gap in what got fed into
  it, not a gap in the stepping logic. Still a non-issue in practice today
  for the same reason session 10 noted (enemies never spawn inside a
  vault), but it closes the gap before enemies are ever placed near one.
- **Incidental fix, caught by visual inspection, not by the logic above**:
  the Spellbook panel's height was hardcoded to 340px back in session 12,
  sized for the original 5 spells. Adding two more pushed a level-7
  character's known-spell list to 7 entries, and the fixed height clipped
  Detect Treasure's wrapped description and garbled it directly into the
  "Up/Down select..." hint line -- the same class of bug session 13 fixed
  for panel *width*, just never hit for height until content grew past one
  screenful. `_draw_spellbook_panel` now measures each known spell's
  word-wrapped line count first, then sizes the panel surface to exactly
  the content height needed (floor of 160px for the empty/one-spell case),
  before doing the actual blit pass -- no arbitrary cap, since the spell
  list only grows by one small entry per future session. Verified both ends
  visually: a fresh level-1 character's single-spell panel is unchanged at
  160px, and a level-7 character's 7-spell panel now renders full
  descriptions with the hint line clear of them at 432px, still comfortably
  inside the 800x600 window.
- Verified headless (SDL dummy driver, scratch DB, no pytest suite yet):
  both new spells appear at the correct unlock levels and
  `engine.spells.newly_learned` picks them up exactly at level 6/7; casting
  either sets its counter (confirmed off-by-one-on-cast, matching Stone
  Skin's documented convention) and an `_is_visible` check against a
  fully-fogged fake room confirms the bypass is scoped to the right entity
  kind (detect_monsters does *not* leak into detect_treasure's check or
  vice versa) and clears exactly on schedule after ticking the full
  duration via `_advance_turn`; insufficient mana blocks both new spells as
  a full no-op (no turn consumed), matching every other spell; bumping the
  Healer opens `healer_open` exclusively (not quest/shop) and bumping the
  Quartermaster/Merchant still open only their own panels (regression
  check); `rest_cost()`/`rest_at_healer()` charge the exact expected gold
  and fully restore HP/mana, insufficient gold and already-full both no-op
  correctly (the latter charging zero gold), and resting never advances
  `turn_count`; I/M/C are correctly captured (refused) while the healer
  panel is open and Esc closes it without requesting quit; a direct
  `Enemy.take_turn` call against a synthetic blocked tile confirms it
  refuses to step onto anything in `occupied_positions`, and a probe enemy
  dropped into a real `Game` with a synthetic locked door confirms
  `_run_enemy_turns` actually folds `_blocked_positions()` into what gets
  passed in (both the unit-level contract and the real wiring, since either
  alone wouldn't have caught session 10's original gap); sampled generated
  Depths rooms to confirm locked doors/gates still actually occur post-fix
  (unrelated to the fix itself, just confirming the fixture-placement code
  path wasn't accidentally touched). Regression pass re-confirmed existing
  behavior is untouched: Minor Heal/Stone Skin still resolve correctly,
  Quartermaster/Merchant panels are unaffected, a save/reload round trip
  still preserves gold and `known_spells` (with the new detect counters
  confirmed absent/zeroed on reload, as designed), and a full `main()` boot
  through the real title menu to a `QUIT` exits cleanly (exit code 0).
  **Also visually inspected** via rendered screenshots: the Healer panel
  reads cleanly with live HP/mana/cost text, and the Spellbook panel fix
  was confirmed by screenshot at both the 1-spell and 7-spell extremes (the
  overlap bug was only visible this way -- none of the assertions above
  would have caught a purely visual clipping regression). Real `save.db`
  confirmed untouched (mtime unchanged across the whole session); all runs
  used a scratch DB path.

### Session 16 — cursed/enchanted equipment (Castle of the Winds' item curse system)

User-driven request: "look up the game Castle of the Winds and continue
development." CotW's items are, per its own documentation, "almost always
normal, cursed, or enchanted, with curses and enchantments working the same
way as in NetHack" -- an unidentified item's status is hidden until it's
either equipped (risking a curse locking it on) or identified in town for a
fee, and a cursed item cannot be removed until a paid Remove Curse service
lifts it. This was the single most-repeatedly-deferred CotW mechanic in this
codebase (flagged as future work every session since session 5, blocked each
time on "needs per-instance item tracking this codebase has deliberately
avoided") and is also what session 8's "equipment is shop-only" limitation
was explicitly waiting on. Scoped tightly to equipment only (not
consumables, which stay session-5's tiered `item_type` strings) and to
floor loot only (not chest loot, which stays plain consumables -- see
below) to keep the lift contained to one session.

- **Equipment is now per-instance, not a bare item_type string.**
  `engine/equipment.py` was rewritten around instance dicts (`instance_id`,
  `base_type`, `enchant`, `cursed`, `identified`) stored in a new
  `player.equipment_instances` dict -- every instance the player has ever
  owned, keyed by id. `player.equipment[slot]` still holds exactly one
  thing per slot, same shape session 8 gave it, but an instance_id now
  instead of a bare item_type -- **zero save-schema change** to the
  existing `equip_<slot>` columns, only what's stored in them changed
  meaning. A new `equipment_instances` table (instance_id/base_type/
  enchant/cursed/identified) holds the full pool, written/read the same
  full-replace-on-save pattern `inventory`/`known_spells` already use.
  `Player.next_equip_instance_num` (fresh `"eqN"` ids) resumes past
  whatever's already in a loaded save's `equipment_instances` rather than
  restarting at 1, so a returning character can't mint a colliding id.
- **Dungeon-found gear is the only source of enchant/curse** -- shop
  purchases (`Game.buy_or_upgrade`) are still always a fresh `+0`,
  uncursed, already-identified instance via `equipment.
  create_shop_instance`, matching the source material (buying a known
  quantity from a known merchant is no mystery there either). Depths floor
  loot gained a new `"equipment"` family in `procgen.
  ITEM_WEIGHTS_BY_TIER` (tier 0/shallow never rolls it, deeper tiers
  slightly more; rarer than consumables at every tier it appears in) --
  when picked, `generate_room()` rolls a random slot, a basic/fine/
  masterwork base_type via the *existing* session-5 magnitude-weight
  table (reused exactly, mapped 0/1/2 to tier index), and an enchant via
  `equipment.roll_enchant()` (`ENCHANT_WEIGHTS`, a bell curve centered on
  0 -- `[-3,-2,-1,0,1,2,3]` weighted `[1,3,8,55,20,10,3]`). **Negative
  enchant always means cursed** -- a deliberate simplification over
  tracking curse as an independent flag (which CotW does, e.g. a cursed
  `+0` item exists there) that keeps this codebase's single-source-of-
  truth discipline: no separate boolean that could drift from the number
  it's describing. Emitted into a new `equipment_drops` list, parallel to
  (not merged into) procgen's existing `items` list, since a floor drop
  needs a `base_type`/`enchant` pair rather than a single items.json key.
  Vault chests deliberately **don't** roll equipment -- `CHEST_ITEM_WEIGHTS_BY_TIER`
  (derived once from `ITEM_WEIGHTS_BY_TIER` with the `"equipment"` entry
  filtered out) is what the existing chest-loot roll uses instead, since a
  chest's `item_type` field is a plain items.json key with nowhere to put
  an enchant -- picking "equipment" there would have `KeyError`'d the
  first time a vault chest tried to resolve it. Chest-loot equipment is
  explicitly future work, not attempted this session (see Known
  Limitations).
- **New `EquipmentDrop` entity** (`engine/entity.py`), parallel to
  `ItemPickup` but carrying `base_type`/`enchant` instead of a stackable
  `item_type`. `Room` gained `equipment_drop_templates` (mirrors
  `item_templates`, both hand-authored-room-json and procgen-populated).
  `Game.load_room` merges `EquipmentDrop` entities into the *same*
  `self.items` list `ItemPickup`s already live in -- both are "walk onto
  it to collect" entities and `Player.try_move`'s pickup collision check
  was already generic over whatever's in that list, so **zero changes**
  were needed there. `Game.handle_move`'s "pickup" branch gained one
  `isinstance(item, EquipmentDrop)` check up front: routes to
  `equipment.create_instance(..., identified=False)` (lands in the bag,
  unidentified -- message shows only the base name, e.g. "Found Longsword
  (unidentified).", never the hidden enchant/curse) instead of
  `Inventory.add_item`. Never slot-limited by the 8-slot consumable
  inventory, same "separate bag, not a carried stack" precedent session
  8's gold pickup already set.
- **Equipping always identifies** -- CotW's classic "find out by wearing
  it" risk, and the exact moment a curse can lock a slot for good.
  `equipment.equip()` reveals the instance's true name/enchant/curse
  status the instant it's worn; if what's *already* in that slot is
  cursed, `equip()`/`unequip()` both return the sentinel `"cursed"` and
  change nothing -- callers (Inventory panel's equip-from-bag, shop
  purchases, Remove Curse) all check for it and show a message rather
  than silently swapping gear out from under a curse. `equipment.
  remove_curse(player, defs, slot)` (paid Merchant service, see below)
  clears just the `cursed` flag, leaving `enchant` untouched -- "uncursed"
  isn't "no longer a bad item," the same distinction CotW itself makes,
  and it's what gives a stuck player an actual way out rather than a soft
  lock.
- **Inventory panel gained a "Found Gear" section** (`main.py`
  `_draw_inventory`) listing every owned-but-unequipped instance
  (`equipment.bag_instances`) below the existing Equipped section, dynamic-
  height like session 15's Spellbook panel rather than a hardcoded offset
  a long bag could eventually clip past. Reachable through the panel's
  *existing* Up/Down/U-or-click flow with **zero new keybindings**:
  `Game._inventory_rows()` is a combined list (consumable stacks first,
  unchanged indices so the 1-8 field hotkey range is untouched, then bag
  instances appended after) and `_activate_inventory_row` dispatches on
  which kind of row the cursor's on. Field quick-use (number keys 1-8
  outside the panel) deliberately still resolves only against the plain
  consumable list (`_use_item_at_index`, unchanged) -- equipping (and
  risking a curse) stays a panel-only, deliberate action, never a stray
  field hotkey away.
- **Merchant panel gained Identify and Remove Curse rows**, appended after
  the original 5 gear-slot rows the exact same way (`Game._shop_rows()`,
  same combined-list-one-cursor pattern as the Inventory panel above) --
  one "Identify <name> (15g)" row per unidentified bag instance, one
  "Remove curse: <slot> (30g)" row per cursed equipped slot, both only
  appearing when there's actually something to act on, so a character
  who's never touched cursed/unidentified gear still sees exactly the
  5-row panel session 8 shipped. Panel height grows to fit however many
  extra rows are present (same measure-then-build pattern as the
  Spellbook/Inventory panels). `buy_or_upgrade` was reworked to take an
  explicit `slot` argument (previously read `SLOTS[self.shop_cursor]`
  directly, which no longer holds for the new row kinds) and to run
  purchases through `create_shop_instance` + `equip` like any other
  equip path -- including handling the (rare but real) case where the
  slot being bought into is already stuck on a cursed item: the gold is
  still spent (matching the source material -- buying a replacement
  doesn't refund what you can't take off) and the freshly-bought instance
  simply lands in the bag instead of getting worn.
- Verified headless (SDL dummy driver, scratch DB): sampling 400 deep-tier
  generated rooms confirms equipment drops actually occur and cover both
  negative and positive enchant rolls, tier-0/shallow rooms never roll one,
  and vault chests' family roll never produces `"equipment"` (would have
  raised `KeyError` on open, pre-fix); direct `engine.equipment` unit-level
  checks confirm instance creation/identification/enchant-to-stat math
  (including that the enchant is folded into whichever of attack/defense
  the base item actually grants), unequip-then-equip reverses the exact
  bonus applied, a cursed equipped item refuses both a direct unequip
  *and* being swapped out by equipping something else in the same slot,
  `remove_curse` lifts the curse without touching the enchant and the item
  becomes removable immediately after, and shop-created instances are
  always `+0`/uncursed/identified; a full live-`Game` pass locates a real
  generated Depths room with an equipment drop, simulates the walk-onto
  pickup (lands in the bag, unidentified, correct base_type), equips it
  through the actual `_activate_inventory_row` panel path (message
  confirms, instance flips to identified), and round-trips a save/reload
  confirming `equipment_instances` persists and the reloaded player's
  baked-in attack/defense matches exactly (no double-application); the
  Merchant's new row list starts as exactly the original 5 slots and
  `buy_or_upgrade` still equips correctly through the new instance flow;
  a full `main()` boot through the real title menu to a `QUIT` (posted on
  a real short timer, not pre-queued -- `main()`'s own
  `pygame.display.set_mode()` call flushes anything queued before it
  runs, a testing-harness gotcha sessions 7/8 already hit) exits cleanly.
  **Also visually inspected** via rendered screenshots: the Inventory
  panel's Equipped section correctly shows "Longsword +2" and "Buckler -2
  [cursed]", Found Gear lists two "(unidentified)" entries with no enchant
  leaked; the Merchant panel shows "Identify Iron Helm (15g)", "Identify
  Leather Boots (15g)", and "Remove curse: Shield (30g)" cleanly below the
  5 slot rows. The first render caught a real clipping bug (the
  Inventory panel's hint line grew past its 400px width once "/equip" was
  added to it, the exact class of bug session 13 first fixed for this
  panel) -- measured directly with `font.size()` (424px needed vs. 400px
  available) and fixed by widening to 450, then re-rendered to confirm.
  Real `save.db` was never touched by any of the above -- all runs used a
  scratch DB path.

### Session 17 — vault chests can hold enchanted gear

User-driven request: "look up the game Castle of the Winds and continue
development." Rather than opening a new CotW mechanic, this closes out the
single most concrete next step session 16 itself flagged: vault chests
could only ever hold a plain consumable `item_type`, since the chest data
shape had nowhere to put an enchant. This session grows that shape and
wires the reward through the exact per-instance equipment path session 16
already built for floor loot — no new subsystem, no new UI.

- **`engine/procgen.py`**: the vault section's chest-building code now rolls
  a family the same way floor loot does (`_weighted_choice` against
  `ITEM_WEIGHTS_BY_TIER[tier]` — previously a separately-derived
  `CHEST_ITEM_WEIGHTS_BY_TIER` that filtered `"equipment"` out entirely;
  removed, since the branch below now handles it and tier 0's own weight
  table already has no `"equipment"` entry to roll, so shallow vaults still
  never produce one, for free). When the roll lands on `"equipment"`, a
  slot/magnitude/enchant are rolled (mirrors the floor-loot `"equipment"`
  branch immediately above it exactly — same `EQUIPMENT_BASE_TYPES_BY_SLOT`/
  `_MAGNITUDE_TO_GEAR_TIER`/`roll_enchant` calls) and stored as
  `chest["equipment"] = {"base_type": ..., "enchant": ...}` instead of
  `chest["item_type"]` — the two keys are mutually exclusive, a chest dict
  never has both. **Deliberately rolled off `layout_rng`, not `pop_rng`**,
  same as the rest of a vault's contents (its lock, its position) — a
  chest's reward is structural and permanent, so it must never change
  across the room's epoch-scoped respawn cycle the way floor loot does;
  using `pop_rng` here would have been the actual bug, since a respawned
  room would re-roll what a solved vault contains, but the chest was
  already flagged opened. `magnitude` still rolls off
  `MAGNITUDE_WEIGHTS_BY_TIER[2]` regardless of the room's actual tier,
  unchanged from session 10's original chest behavior (a vault's reward
  skews toward the best tier available as a reward for solving it, not
  scaled down to match a shallow room).
- **`main.py`'s chest-opening branch** (`handle_move`'s `kind == "chest"`
  case) gained an `"equipment" in chest` check ahead of the existing
  `item_type` path: routes to `create_instance(player, base_type, enchant,
  identified=False)` — the *exact* call the floor-loot pickup branch two
  cases above it already makes — landing the drop unidentified in the
  "Found Gear" bag, never slot-limited by the 8-slot consumable inventory
  (same precedent as floor equipment drops and gold). Message mirrors the
  floor-pickup phrasing ("The chest holds Leather Cap (unidentified)!").
  **Zero new UI** — the Inventory panel's session-16 "Found Gear" section
  and the Merchant's Identify/Remove Curse rows already handle any owned
  instance regardless of where it came from, so a chest-found item is
  immediately equippable/identifiable through the exact same flow a
  floor-found one already used.
- **`engine/equipment.py`'s docstring updated** to drop this from its
  "future work" list (the only remaining item there is ring/amulet slots).
- Verified headless (SDL dummy driver, scratch DB): chest generation is
  deterministic per `(seed, level, gx, gy, epoch)` and unaffected by epoch
  (structural, matching the rest of the vault); sampling ~900 generated
  rooms across many seeds/levels/coordinates found both equipment and
  plain-consumable chests, every equipment chest's `base_type` resolves in
  `data/equipment.json`, every enchant falls in `-3..3`, and tier-0
  (shallow) rooms never produce one; still at most one chest per room
  (the pre-existing single-vault-attempt invariant is untouched); a real
  `Game` instance located a live generated room with an equipment chest,
  walked onto it through the actual `handle_move` path, and confirmed
  exactly one new `equipment_instances` entry appears with the chest's
  exact `base_type`/`enchant`, `identified=False`, and `cursed` matching
  `enchant < 0`; re-walking onto an already-opened equipment chest is a
  no-op (no duplicate instance); the new instance shows up in
  `bag_instances`; a regression pass confirmed a plain (non-equipment)
  chest still grants gold or a consumable exactly as before, unaffected by
  the new branch; a full `main()` boot through the real title menu (Enter
  posted on a real short timer, not pre-queued — the session 7/8-established
  gotcha) to a `QUIT` (also posted on a real short timer) exits cleanly
  (exit code 0). **Also visually inspected** via rendered screenshots: the
  message log shows "The chest holds Leather Cap (unidentified)!" with no
  clipping, and the Inventory panel's Found Gear section lists it correctly
  below the (empty, for a level-10 test character with no consumables)
  Inventory and Equipped sections — confirming session 16's dynamic-height
  panel machinery needed no changes to accommodate a chest-sourced entry.
  Real `save.db` confirmed untouched (mtime unchanged across the whole
  session); all runs used a scratch DB path.

### Session 18 — ring/amulet slots (Castle of the Winds' actual jewelry loadout)

User-driven request: "look up the game Castle of the Winds and continue
development." Research (StrategyWiki's items page, see citation in the
session's own notes) confirmed CotW's exact loadout: one amulet and *two*
ring slots worn simultaneously, rings raising "one attribute or armor
class," amulets raising "resistance to an element or undead stat draining."
This closes the equipment module's own docstring, which has named
ring/amulet slots as its last open item since session 16. Scoped tightly
to the slots themselves, reusing session 8/16's per-instance equipment
machinery exactly rather than inventing anything new for them.

- **Three new slots**: `ring1`, `ring2`, `amulet` appended to
  `engine/equipment.py`'s `SLOTS` tuple (5 -> 8 entries). This was the
  whole trick of the session -- `save.py`'s `equip_<slot>` column
  generation, `Player.equipment`'s dict comprehension, every panel that
  iterates `SLOTS` generically (Shop's per-slot rows, Inventory's Equipped
  section, `cursed_equipped_slots()`), and even the dynamic panel-height
  math (`len(SLOTS) * 18`) all already derived themselves from `SLOTS`
  rather than hardcoding five -- extending the tuple was the only change
  needed in every one of those places. Verified directly: zero lines
  touched in `engine/save.py` or `engine/entity.py`'s `Player.__init__`.
- **Rings are a plain attack or defense bonus**, no new stat concept --
  `ring1` carries the "Ring of Might" line (attack, mirrors a weapon's
  bonus), `ring2` carries "Ring of Warding" (defense, mirrors armor).
  Deliberately two *separate*, fixed slot keys rather than one shared
  "ring" item type either finger could hold -- teaching `next_offer`/
  `save.py`/every SLOTS-iterating panel a second concept (an item pool
  spanning two slots) would have been real new mechanism; two independent
  tier ladders is zero.
- **Amulets are the one real design call this session**: CotW's amulets
  raise elemental resistance or undead-drain resistance, and this engine
  has neither elemental damage types nor undead-specific mechanics to hang
  that on (still true, see Known Limitations). Rather than bolt on a
  resistance system just to give amulets something to do, "Amulet of
  Vitality" grants a flat `max_hp` bonus instead -- the closest existing
  survivability resource, same spirit as session 15 scoping the divination
  spells to "the room you're standing in" rather than a full level reveal
  when the honest translation of a CotW mechanic didn't fit this engine's
  actual scope.
- **`engine/equipment.py`'s `_bonus()`/`equip()`/`unequip()` extended for a
  third stat kind.** `_bonus()` now also returns an hp delta (enchant
  applies to it exactly like attack/defense: `+2 sword hits harder` / `+2
  amulet is hardier`). Equipping adds the delta to *both* `max_hp` and
  `hp` (an immediate boost, not something that only matters next time
  you're hurt); unequipping subtracts the delta from *both*, floored at 1
  hp. That symmetry matters: an earlier draft instead clamped `hp` down to
  the new (lower) `max_hp` on unequip rather than subtracting the delta,
  which silently healed the player for free any time they were above the
  new max but below the old one (e.g. take 5 damage under a +8 amulet, then
  swap it for a different one -- clamping would round the deficit down to
  whatever the intermediate max happened to be instead of preserving the
  actual 5 points missing). Caught by this session's own verification, not
  inspection -- see below -- and fixed to plain symmetric +=/-= before
  shipping.
- **`engine/procgen.py`**: `EQUIPMENT_BASE_TYPES_BY_SLOT` gained `ring1`/
  `ring2`/`amulet` entries (each a 3-tier base_type list, same shape as the
  original five); `EQUIPMENT_SLOTS` is derived from that dict's keys, so
  both the floor-loot roll (`pop_rng.choice(EQUIPMENT_SLOTS)`) and the
  vault-chest roll (`layout_rng.choice(EQUIPMENT_SLOTS)`) picked up the
  three new slots automatically, no logic changes in either branch.
- **Sprites**: found by rendering `eval/_sheet.png` (the items/equipment
  source sheet) to a scratch PNG, cropping and column-labeling candidate
  rows, and visually inspecting before picking coordinates -- same
  discipline session 9 established, not assumed from a naming convention.
  Rings live in the sheet's dedicated jewelry block (rows 64/65/68 of 112);
  amulets in its pendant row (row 0, alongside collars and belt icons the
  sheet groups nearby). Three tiers per line, picked for a visible
  simple-to-ornate progression the same way session 9's weapon/armor tiers
  were: Ring of Might basic/fine/masterwork = plain-red-gem -> silver-gold
  band -> ornate gold cluster; Ring of Warding = plain-blue-gem -> emerald
  silver band -> ornate gold band; Amulet of Vitality = plain silver heart
  pendant -> gold-trimmed -> gem-set gold.
- **Shop panel widened 460 -> 700px.** The new "`<equipped>` -> `<next
  tier>`" rows measure up to 680px at the panel's font (e.g. "Amulet of
  Greater Vitality -3 [cursed] -> Amulet of Supreme Vitality (155g)") --
  the multi-word CotW-style names ("Ring of Supreme Warding") are simply
  longer than the original five slots' mostly single/double-word gear
  names ("Buckler", "Greatsword"). Same "widen the panel, don't shrink the
  text" call sessions 13 and 16 already made for this exact panel, just a
  bigger jump this time; measured directly with `font.size()` against
  every real slot/tier/enchant/curse combination the game can actually
  produce (not eyeballed) before picking 700. The Inventory panel's
  Equipped section needed no width change (its lines have no "-> next
  tier" suffix, so even the worst case measures well under its existing
  450px).
- **New `main.py` `slot_label()` helper** (`SLOT_LABELS = {"ring1": "Ring
  1", "ring2": "Ring 2"}`, falls back to the existing `slot.title()` for
  every other slot) -- the one spot the generic-SLOTS-iteration story
  above didn't hold for free, since `"ring1".title()` reads as "Ring1" with
  no space. Replaces every `slot.title()` call site (Inventory's Equipped
  section, both Shop panel row formats, the Remove Curse confirmation
  message).
- Verified headless (SDL dummy driver, scratch DB): `SLOTS` has exactly the
  8 expected entries and every new `data/equipment.json` entry resolves
  with a valid slot; all 9 new sprites load as real images (checked
  against the fallback-magenta pixel, not just dict presence); a fresh
  character's `equipment` dict has all 8 keys empty; equipping a ring1
  raises attack, a ring2 raises defense independently, and an amulet
  raises both `max_hp` and current `hp` together; unequipping reverses
  each exactly; the free-heal clamp bug above is directly regression-
  tested (damage the player under a basic amulet, swap to a fine one,
  confirm the pre-swap deficit survives the swap rather than getting
  rounded away); a cursed amulet (negative enchant) still grants its
  (reduced) bonus, refuses to unequip, and `remove_curse` lifts it and
  restores normal unequip behavor with the max_hp bonus reversing
  correctly; `next_offer` walks the tier ladder correctly for all three
  new slots independently of each other and of the original five;
  sampling 3000 generated deep-tier rooms confirms floor drops *and* vault
  chests actually roll all three new slots and every rolled `base_type`
  resolves in `data/equipment.json`, while 1500 shallow-tier rooms never
  roll any equipment slot at all (unchanged pre-existing rule); a live
  `Game` instance located a real generated room with a ring/amulet floor
  drop, walked onto it through the actual `handle_move` path, and
  confirmed exactly one new unidentified `equipment_instances` entry with
  the right `base_type` lands in the bag (not auto-equipped), and that
  re-visiting the now-empty tile is a no-op; a full save/reload round trip
  preserves all three new `equip_<slot>` columns and their
  `equipment_instances` rows, with the reloaded player's baked-in
  attack/defense/max_hp matching exactly (no double-application); the
  widened Shop panel and unwidened Inventory panel were checked against
  every real worst-case row string with `font.size()` before and after the
  width fix; a full `main()` boot through the real title menu to a `QUIT`
  (both posted on real short timers, not pre-queued -- the session
  7/8-established gotcha) exits cleanly. **Also visually inspected** via
  rendered screenshots: the Shop panel's widened layout shows all 8 slot
  rows plus Identify/Remove-curse rows with zero clipping, including the
  Amulet upgrade row that motivated the width change; the Inventory
  panel's Equipped section reads "Ring 1: Ring of Supreme Might", "Ring 2:
  Ring of Supreme Warding -3 [cursed]", "Amulet: Amulet of Greater
  Vitality" cleanly with the new `slot_label()` formatting; a cropped/
  zoomed screenshot of a live Depths room floor confirms the ring and
  amulet sprites read clearly as jewelry (a banded gem ring, a gold-
  trimmed pendant) and are visually distinct from every other pickup type
  already on the floor (gold, potions, other equipment). Real `save.db`
  confirmed untouched (mtime unchanged across the whole session); all runs
  used a scratch DB path via a monkeypatched `main.SAVE_PATH`.

### Session 19 — purchasable spellbooks (Castle of the Winds' other half of its spell system)

User-driven request: "look up the game Castle of the Winds and continue
development." Session 12 built only the auto-learn-by-level half of CotW's
spell system and explicitly flagged the other half -- buying a spellbook in
town to learn a spell out of level order -- as future work every session
since. This closes that out. Scoped tightly to the purchase mechanism itself,
reusing session 12's `known_spells` set and casting pipeline completely
unchanged, rather than opening any new spell mechanic.

- **New Scholar NPC** (`data/npcs.json`, `town_hub.json` at `(20, 18)` --
  mirrors the Healer's placement at `(12, 18)` on the opposite side of the
  Quartermaster at `(16, 14)`, keeping the hub's NPC layout roughly
  symmetric). Sprite picked the same way session 9/15/18 picked every prior
  NPC portrait: rendered a labeled contact sheet of the character sheet's
  row 12 (the row every other town NPC's portrait already comes from) and
  visually compared candidates rather than guessing from a naming
  convention. Landed on `tile_12_21.png` -- the one portrait in that row
  with no bow, helmet, or armor (every other column in the row is a
  recolored archer), which reads as the row's only plausible non-fighter
  and is visually distinct at a glance from the Healer's warm blonde/white,
  the Quartermaster's silver helm, and the Merchant's tan headwrap (see the
  cropped/zoomed comparison screenshot from this session's verification).
- **Bumping the Scholar opens a new `bookshop_open` panel**
  (`_draw_bookshop_panel`), built on the exact same list-with-cursor
  shape the Shop/Spellbook panels already established: `Game._bookshop_rows()`
  returns every `data/spells.json` entry not yet in `known_spells`, in
  file order (a fixed catalog that only ever shrinks as spells are bought,
  never reshuffles), `bookshop_move_cursor`/`activate_bookshop_row` mirror
  `shop_move_cursor`/`activate_shop_row` exactly, and `handle_key_down`
  gained a `bookshop_open` branch (Up/Down/U/Enter) plus a slot in the
  I/M/C guard conditions, `_any_panel_open`, and `close_active_panel` --
  the same three or four places every one of sessions 12/15/16's new panels
  already had to extend, no new pattern. Row clicks reuse `_begin_panel_hitboxes`
  and a `_click_buy_spellbook` callback, same as every other panel since
  session 13. Panel height is measured from the live catalog size (empty
  catalog still renders a one-line "already know every spell in stock"
  message rather than a zero-height panel).
- **`buy_spellbook(spell_id)`** is the entire mechanism: insufficient gold
  is a silent no-op message (same pattern `buy_or_upgrade`/`rest_at_healer`/
  `identify_instance` already use), otherwise it deducts `book_cost` and
  adds the id straight to `self.known_spells` -- the *exact* set
  `_learn_new_spells` already adds to on level-up, so casting, mana cost,
  targeting, the Spellbook panel, and save/load all handle a bought spell
  with **zero changes**, verified directly (a bought Firebolt shows up in
  `_known_spell_list()` immediately and survives a save/reload). No
  level or mana check on the purchase itself -- the entire point is
  skipping the level gate, matching CotW's own out-of-order learning.
- **`data/spells.json` gained a `book_cost` field per spell**: `15 +
  unlock_level * 20` (35/55/75/95/115/135/155 for Spark through Detect
  Treasure), landing in the same gold range session 8/18's tier-3 equipment
  already established (70-155g) rather than inventing a separate economy
  scale. Spark's cost is defined for completeness even though a fresh
  character already knows it at level 1 (it simply never appears in
  `_bookshop_rows()` for a new character) -- consistent should a future
  session ever add a spell with no unlock level or a respec mechanic that
  un-learns one.
- Verified headless (SDL dummy driver, scratch DB): `npc_scholar` resolves
  to a real 16x16 sprite (not the load-failure fallback); the Scholar NPC
  loads into `town_hub` at the exact configured position; a fresh level-1
  character knows only `spark` and the bookshop catalog is exactly the
  other 6 spells in `spells.json` order; bumping the Scholar sets
  `bookshop_open` and *only* that flag (not shop/quest/healer), and the
  player does not step onto the NPC's tile (same non-committal-bump
  contract every NPC/locked-door/gate bump already has); I/M/C are all
  correctly swallowed while the panel is open (regression check against
  session 12/15/19's shared guard-condition pattern); insufficient gold
  blocks a purchase with no state change; buying Firebolt at character
  level 1 deducts exactly 95 gold, adds it to `known_spells`, and the
  purchase message matches; re-buying an already-known spell is a no-op;
  the purchased spell immediately appears in the Spellbook panel's own
  list (proving the shared-set design actually holds, not just that the
  purchase function sets a flag); the cursor clamps correctly as the
  catalog shrinks after a purchase; `activate_bookshop_row` (the
  keyboard/click action path, as opposed to calling `buy_spellbook`
  directly) correctly buys whatever row the cursor is on; a full
  save/reload round trip preserves both the post-purchase gold total and
  the bought spell; a full `main()` boot through the real title menu to a
  `QUIT` (both posted on real short timers from background threads, not
  pre-queued -- the session 7/8-established gotcha) exits cleanly. **Also
  visually inspected** via rendered screenshots: the Town Square shows all
  four NPCs at a glance with the Scholar reading clearly distinct from the
  Healer/Quartermaster/Merchant (cropped/zoomed comparison, see above); the
  bookshop panel itself renders its full 6-spell catalog with no clipping;
  buying Firebolt mid-panel correctly drops it from the list, updates the
  gold total in the title bar, and shows the purchase message below; the
  insufficient-gold path shows its own message with the catalog unchanged.
  Real `save.db` confirmed untouched (mtime check) throughout; all runs
  used a scratch DB path.

### Session 20 — sell items and gear back to the Merchant (Castle of the Winds' buy-high-sell-low shop economy)

User-driven request: "look up the game Castle of the Winds and continue
development." CotW's shops always buy back unwanted loot, not just sell it --
this codebase had no sell path anywhere (`grep -ri sell` across `engine/`
and `main.py` came back empty before this session), so it was pure gold
sink with no way to convert unwanted potions or Found Gear into currency.
Scoped to the Merchant only (the existing gold-economy NPC, session 8) and
reuses every piece of machinery sessions 8/16 already built -- no new
subsystem, just two more row kinds on a panel that already knows how to grow
to fit whatever's on offer.

- **`engine/equipment.py` gained `discard_instance(player, instance_id)`** --
  pops an owned instance out of `equipment_instances` entirely, the
  complement to `create_instance`. Deliberately simpler than `unequip()`:
  it's only ever called on a *bag* (unequipped) instance (see `_shop_rows`
  below), so there's no stat bonus or curse-lock to reverse the way
  `unequip` has to.
- **`Game._shop_rows()` gained two more sections**, same "append after the
  existing list, one shared cursor" pattern sessions 16/16 already used
  twice for Identify and Remove Curse: one `("sell_item", item_type)` row
  per consumable stack whose `data/items.json` entry has `value > 0`
  (excludes the quest `key`, which is `value: 0` for exactly this reason --
  no special-casing by item id needed), then one `("sell_gear",
  instance_id)` row per **bag-only** gear instance from `bag_instances()`.
  **An equipped item is never reachable through this list at all** -- the
  filter is the same one the Inventory panel's Found Gear section already
  uses, so there's no risk of a stray U-press selling off a worn weapon
  (equipped gear would need to be unequipped -- i.e. replaced by something
  else in the same slot -- before it could ever appear here, and even then
  a cursed one still refuses to come off, same as always).
- **`Game.sell_item`/`sell_gear`, `SELL_RATE = 0.4`.** A flat 40%-of-value
  sell-back rate, not per-item haggling -- same "one number, not a system"
  scope call session 16 made for enchant. `sell_item` sells exactly one
  unit of a stack per activation (consistent with every other shop row
  being a single discrete action) via `Inventory.remove_item` (already
  existed, session 10 built it for key-consumption); `sell_gear` prices
  off the base type's `data/equipment.json` value alone, deliberately
  **ignoring the instance's enchant** -- the same simplification that
  already applies to display: an unidentified item's true enchant is never
  leaked by its sell price either, since the price is identical whether or
  not the player has paid to identify it. `_sell_price` rounds and floors
  at 1 gold so even a `value: 1` item (e.g. minor whetstone) is never worth
  literally nothing to sell.
- **`_draw_shop_panel`** grew a `kind ==` branch for each new row
  ("Sell Health Potion x3 (6g)" / "Sell Longsword +2 (22g)"), no width
  change needed (these lines measure shorter than the existing "-> next
  tier" rows that already sized the panel to 700px in session 18) and no
  new hitbox mechanism (rides the same per-row `panel_click_targets`
  pattern via the existing `_click_shop_slot`).
- Verified headless (SDL dummy driver, scratch DB): sell rows are entirely
  absent with an empty inventory and bag (a character who's never touched
  loot still sees the plain 8-slot panel); a `potion` (value 15) sells for
  exactly 6 gold via both the direct method and the `activate_shop_row`
  dispatch path (the keyboard/click entry point, not just the underlying
  call); selling one of a stack of 2 leaves exactly 1, selling the last
  unit removes the row entirely; the `key` item never appears as a
  sell_item row and `sell_item("key")` is a confirmed no-op; a bag gear
  instance appears in `sell_gear` rows while a same-type *equipped*
  instance does not, and selling the bag one leaves the equipped one
  completely untouched (still equipped, stats unaffected); an
  unidentified/cursed bag instance sells without crashing and at the same
  base-value price as an identified one (no identity leak via price);
  selling an already-gone instance id is a safe no-op; emptying the bag via
  repeated sells removes the sell_gear section entirely; a full shop panel
  render with 17 rows (8 slots + 4 consumable stacks + 5 bag gear
  instances) drew without exception and stayed comfortably within the
  800x600 window with the hint line clear of the last row; `persist()`
  after a sell spree doesn't raise; a full `main()` boot through the real
  title menu to a `QUIT` (both posted on real short timers, not
  pre-queued -- the session 7/8-established gotcha) exits cleanly. **Also
  visually inspected** via a rendered screenshot (see above): every new row
  reads clearly with correct name/count/price, and the message log
  confirms an actual sale ("Sold Whetstone for 1 gold."). Real `save.db`
  confirmed untouched (mtime unchanged) throughout, including across the
  full `main()` boot; all runs used a scratch DB path via a monkeypatched
  `main.SAVE_PATH`.
- **Not addressed, same unbounded-growth characteristic the Inventory and
  Spellbook panels already have** (sessions 15/16): the shop panel's height
  still isn't capped or scrollable, so a bag hoarded well past what a
  player would realistically carry between visits (dozens of unsold
  instances) would eventually push the panel taller than the window. Not
  new to this session and not fixed here -- consistent with how every other
  dynamic-height panel in this codebase already behaves, and selling is
  precisely the tool that keeps a bag from growing that large in practice.

### Session 21 — poison status effect (Castle of the Winds' Viper)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's monster roster specifically for status-
effect mechanics (elemental damage/resistance, paralysis, stat drain,
poison — see citations in this session's own work) rather than picking
blind. Elemental damage types/resistance was the obvious next amulet-related
item (session 18 explicitly flagged this as what a real resistance system
would need), but scoped that out as too big a lift for one session — it
would mean growing `combat.py` a whole damage-type axis. Poison is CotW's
other status mechanic, sourced to two actual low-level monsters (Viper,
Giant Scorpion — RPGClassics' monster list), and fits the codebase's
existing "separate persisted countdown field" pattern (Stone Skin, session
12) almost exactly, so it was the right-sized next step.

- **New `Player.poison_turns`/`poison_damage` fields** (`engine/entity.py`),
  same reasoning as `buff_defense_bonus`/`buff_defense_turns`: a *separate*
  additive-over-time field, not a mutate-then-reverse stat, because it has
  to expire on its own schedule and a save/quit mid-poison has to resume
  correctly. Ticked in `Game._advance_turn` (`main.py`) alongside the
  existing buff/detect countdowns — poison damage is applied there (clamped
  at 0, never negative), and the field now *returns* any messages the tick
  generated ("The poison saps N HP from you.", "The poison wears off.")
  instead of silently mutating state, since (unlike the buff countdown,
  which has no user-facing text at all) a DoT that can kill the player
  needs to actually say so. Persisted via two new `poison_turns`/
  `poison_damage` columns on `player` (`engine/save.py`, same
  `ALTER TABLE ... ADD COLUMN` migration pattern as every prior session's
  additions) — poison deliberately *does* survive a save/reload, unlike
  session 15's divination timers, because CotW's own poison persists
  through saves/rest too (it's what makes it dangerous) rather than being
  a purely cosmetic effect.
- **New `Enemy.poison_chance`/`poison_damage`/`poison_duration` fields**,
  defaulted to 0 so every pre-existing enemy type is unaffected without any
  `data/enemies.json` changes. `combat._maybe_poison(enemy, player, log)`
  (new, shared) rolls the chance and, on a hit, sets the player's poison
  fields to `max(current, new)` rather than stacking additively — a second
  bite while already poisoned refreshes duration/potency instead of
  compounding into an ever-growing per-tick number. Wired into both places
  an enemy can land a hit on the player: `resolve_bump_attack` (the
  counter-hit after a player's melee swing) and `enemy_attack` (an
  enemy-initiated hit from `Game._run_enemy_turns`) — a spell-killed enemy
  (`resolve_spell_hit`) never gets to poison the player at all, correctly,
  since the enemy is never adjacent there in the first place.
- **New `viper` enemy type** (`data/enemies.json`) — CotW's actual weakest
  poison monster (5 XP, matching the source material) rather than an
  invented one: 6 hp/1 attack (weaker in a straight fight than even the
  slime) but a 50% bite chance to inflict 2 damage/turn for 6 turns, so
  ignoring it is the actual danger, same spirit as the real game. Added to
  `procgen.ENEMY_WEIGHTS_BY_TIER`'s shallow and mid tiers only (omitted at
  the deepest tier, mirroring how the slime already tapers off there) —
  `scale_stats_for_level` now also scales `poison_damage` by the same
  depth multiplier as hp/xp (a no-op for every enemy without the field, via
  the same `dict(stats)`-copy-then-overwrite shape every other scaled stat
  already uses). **No matching sprite exists** — session 9 already
  confirmed the character sheet is exclusively bipedal humanoids, re-checked
  directly this session (rendered a labeled contact sheet of rows 18-35, no
  snake/reptile anywhere) rather than assumed. `AssetManager.make_placeholder`
  gained a `shape="diamond"` option (a simple rhombus polygon) so the Viper
  reads as a distinct silhouette from the slime's circle and the switch
  fixtures' squares, olive-yellow to read as "creature," not "gear."
- **HUD gained a "Poisoned (N)" indicator** sharing the level/XP line rather
  than adding a fourth HUD row — a first-pass fourth row collided visually
  with the room viewport (`ROOM_ORIGIN` starts at y=56, right where a naive
  fourth line would land), caught by rendering and inspecting a real
  screenshot before shipping, not assumed to fit. Checked against a level-12
  XP string (the widest realistic case) to confirm no overlap with the
  room-name/gold column on the right.
- **`_handle_death` clears poison on revive** — otherwise a player who dies
  while poisoned would respawn at full HP only to take another poison tick
  on their very next action with no fight having caused it. **A death
  caused by the poison tick itself** (rather than a melee/spell hit) is a
  new path: `Game._advance_turn` can now bring `player.hp` to 0 on its own,
  so `handle_move` checks for it immediately after calling `_advance_turn`
  and routes straight to `_handle_death` *before* resolving the attempted
  move at all (mirroring the existing top-of-function "a dead player takes
  no action" guard) — without this, a poison-killed player could still
  complete an attack, start a conversation, or take a flight of stairs on
  the same input that killed them. `quick_use_item`/`cast_selected_spell`
  needed no equivalent guard: both already funnel into `_take_turn`
  unconditionally, and `_take_turn` already re-checks `hp <= 0` before
  running enemy turns and correctly calls `_handle_death` regardless of
  *why* hp hit zero.
- **Poison tick messages had to be threaded through three different
  "turn just happened" call sites** (`handle_move`, `quick_use_item`,
  `cast_selected_spell`), each of which builds its own message list
  differently. `_advance_turn` now returns whatever it generated instead of
  applying it silently, and each caller folds it in. The `"exit"` branch of
  `handle_move` needed a real fix here, caught by this session's own
  verification, not inspection: `load_room()` already resets
  `self.message_log` to `["Entered <room>."]`, and a first-pass edit
  *replaced* that with just the poison message when poisoned (silently
  discarding "Entered X." on a poisoned player's every room transition) —
  fixed by prepending poison/stairs messages onto the post-`load_room`
  `self.message_log` instead of assigning over it, and re-verified against
  both a plain exit and a stairs exit, poisoned and not.
- Verified headless (SDL dummy driver, scratch DB, no pytest suite yet):
  `_maybe_poison` applies at the enemy's configured rate across 200 trials
  (~101/200 at a 50% chance) and never fires for an enemy with
  `poison_chance` absent/0 (regression-checked against a skeleton kill);
  `enemy_attack` and `resolve_bump_attack`'s counter-hit both correctly
  invoke it; `_advance_turn` ticks damage down to exactly 0 floor, expires
  on schedule with a "wears off" message, and a lethal tick brings hp to
  exactly 0; a poisoned player's `handle_move` routes to `_handle_death`
  before the attempted move resolves (no attack/npc-talk/exit happens on
  the killing turn) and revival clears both poison fields; a save/reload
  round trip preserves `poison_turns`/`poison_damage` exactly; sampling 300
  seeds at tier 0/1/2 coordinates confirms Viper spawns at the first two
  tiers and never the third, and `scale_stats_for_level` scales its
  `poison_damage` upward with dungeon level while leaving every non-poison
  enemy's scaled stats untouched; regression-checked Stone Skin's buff
  countdown, a skeleton kill, `quick_use_item`, and `cast_selected_spell`
  all still behave identically post-refactor; a full `main()` boot through
  the real title menu to a `QUIT` (both posted on real short timers from a
  background thread, not pre-queued — the session 7/8-established gotcha)
  exits cleanly. **Also visually inspected** via rendered screenshots: the
  Viper's diamond placeholder reads as a distinct creature silhouette next
  to the player and an NPC portrait in the same shot, and the HUD's new
  "Poisoned (N)" text sits cleanly on the level/XP line with no clipping
  at both a fresh level-1 and a synthetic level-12 XP string. Real
  `save.db` confirmed untouched (mtime unchanged, verified both before and
  after this session's work) throughout; all runs used a scratch DB path.

### Session 22 — elemental damage/resistance (Castle of the Winds' fire/cold/lightning)

User-driven request: "look up the game Castle of the Winds and continue
development." This is the gap sessions 18 and 21 both explicitly flagged
and deferred: session 18 gave amulets a flat max_hp bonus as a stand-in for
CotW's real "resistance to an element," and session 21 picked poison over
elemental damage specifically because typing a whole damage axis into
combat.py was too big a lift for that session. Researched CotW's actual
resistance model (RPGClassics/StrategyWiki: "resistant" halves damage,
"immune" ~ zero, monsters commonly resist or are immune to their own breath
element) before scoping this, and sourced the new enemy from CotW's real
early-dragon roster (Young Red Dragon, 20 XP, "immune to fire, breathes
fire") rather than inventing one.

- **`damage_type` on enemies and spells** (`data/enemies.json`,
  `data/spells.json`; new fields on `Enemy`/read at cast time in main.py).
  `"physical"` is the default and every pre-existing enemy/Spark are
  unaffected. A non-physical attack **bypasses defense entirely** rather
  than being mitigated by it — armor stops blows, not flame, matching how
  CotW itself never lets AC reduce elemental damage. This is symmetric:
  it's true both when a monster hits the player (`combat.
  _enemy_damage_to_player`, shared by `resolve_bump_attack`'s counter and
  `enemy_attack`, replacing the duplicated defense-subtraction formula both
  used to inline separately) and when the player's Firebolt hits a monster
  (`main.py`'s `cast_selected_spell`, the bolt branch).
- **`player.resist_elemental`** (a flat percentage, capped at 90 in combat
  so no single item can reach true immunity) mitigates incoming elemental
  damage the way defense mitigates physical. Sourced entirely from an
  equipped amulet, baked in and reversed the same permanent way weapon
  attack/shield defense bonuses already are (`engine/equipment.py`'s
  `equip()`/`unequip()`), and persisted the same way (`engine/save.py`, new
  `resist_elemental` column, same `ALTER TABLE ADD COLUMN` pattern every
  prior session's additions used).
- **Amulets were fully re-scoped, not extended**: `data/equipment.json`'s
  `amulet_vitality_*` ladder (flat +8/+16/+28 max_hp) is replaced by
  `amulet_resist_*` (Amulet of Resistance / Greater / Supreme Resistance,
  15%/30%/45% elemental resist) — the real mechanic amulets were always
  meant to grant per sessions 18/21's own notes, not a stand-in bolted on
  next to it. Since no equipment def anywhere still sets `"max_hp"` after
  this change, the now-fully-dead hp-bonus branch in `equipment.py`'s
  `_bonus`/`equip`/`unequip` was deleted outright (confirmed via grep
  before removing) rather than left unreferenced — `_bonus` returns a
  3-tuple again instead of 4. `engine/procgen.py`'s
  `EQUIPMENT_BASE_TYPES_BY_SLOT["amulet"]` updated to the new key names;
  same sprites (`eq_amulet_basic/fine/masterwork`) reused since only the
  mechanic changed, not the art.
- **Enemy-side resistance, the reverse case**: `Enemy.resist_elements`
  (a `{damage_type: fraction}` dict, empty for everything that doesn't
  define it) lets a monster resist or be immune to a *matching* elemental
  spell — `combat.resolve_spell_hit` gained a `damage_type` param, looks
  the caster's element up against the target's `resist_elements`, and
  either halves damage (a fraction between 0 and 1, not used by any enemy
  yet but the same zero-by-default-field convention session 21's
  poison_chance already established), fully negates it and logs "is immune
  to it" (fraction >= 1), or is a no-op passthrough for every existing
  enemy and for Spark (which stayed `"physical"` — CotW's base attack spell
  is non-elemental and always hits full regardless of resistance, which is
  exactly what leaving it untyped already does here for free).
- **New `young_red_dragon` enemy** (`data/enemies.json`) exercises both
  sides of the mechanic in one placement: `damage_type: "fire"` (its bite
  bypasses the player's defense, mitigated only by resist_elemental) and
  `resist_elements: {"fire": 1.0}` (immune to the player's own Firebolt,
  so a player who only prepared fire damage has to fall back to melee or
  Spark — real emergent tactical texture, not just a stat bump). Deep-tier
  only and rare (`procgen.ENEMY_WEIGHTS_BY_TIER[2]`, weight 1 against the
  other three's combined 6) — a mini-boss-flavor threat, not a regular
  encounter. hp45/atk9/def3/xp40/gold15-25, tougher than the previous
  strongest enemy (cultist) across the board, consistent with being the
  rarest thing in the tier. No matching sprite exists (session 9's
  bipedal-only character sheet, re-confirmed for session 21's Viper and
  true again here) — `AssetManager.make_placeholder` gained a `"triangle"`
  shape (a simple spiked silhouette, red-orange) alongside the existing
  circle/diamond/square, visually distinct from every other enemy at a
  glance.
- **New "Elemental Resist N%" line** on the Inventory panel's "Equipped"
  section title (only shown when > 0) — unlike attack/defense/(the old)
  max_hp, resist_elemental has no other visible gameplay tell (no bar, no
  power difference the player would notice in melee), so it needed an
  explicit number the same way session 21 added a "Poisoned (N)" HUD
  indicator for poison. Folded into the existing title line rather than a
  new row, so the panel's height math (already computed from item/gear
  counts) didn't need touching.
- **Found and deliberately did not fix, out of scope for this session**: a
  pre-existing (not new) turn-economy quirk, confirmed by reading (not
  guessed) `handle_move`/`_run_enemy_turns` — when the player bump-attacks
  an adjacent enemy that survives, that enemy both counters immediately
  (`resolve_bump_attack`) *and* gets an independent attack action from
  `_run_enemy_turns` the same turn (it's still adjacent when its AI turn
  runs), landing two hits per one player attack. This was caught by this
  session's own combat-formula verification (a synthetic single-hit
  assertion failed until the math was checked against the actual double
  hit) and confirmed present for every enemy type, not something session
  22 introduced — noted below rather than silently patched, since it
  wasn't what this session was asked to do and changes base melee balance
  for every existing enemy.
- Verified headless (SDL dummy driver, scratch DB, no pytest suite yet):
  `Enemy`/`Player` pick up the new fields with correct defaults for every
  pre-existing enemy type (`damage_type` "physical", `resist_elements`
  `{}`, `resist_elemental` 0); `_enemy_damage_to_player` ignores a
  synthetic 50-defense player entirely for the Dragon's fire attack but
  respects it normally for a Skeleton's physical one; resist_elemental at
  50% and at a saturating 1000% both compute against the 90%-cap formula
  correctly; `resolve_spell_hit` against the Dragon does zero damage and
  logs "immune," against a Skeleton with the same fire type does full
  damage, and Spark (`"physical"`) is unaffected by any enemy's
  `resist_elements`; equipping each amulet tier grants exactly its listed
  resist_elemental, unequipping reverses it exactly, an enchanted (+3)
  masterwork amulet grants 45 + 3*3 = 54, and swapping amulets leaves no
  stale bonus behind; confirmed no equipment def anywhere still sets
  `max_hp` post-change; `young_red_dragon` only ever rolls at tier 2 across
  500 samples and never at tiers 0/1; `scale_stats_for_level` carries
  `damage_type`/`resist_elements` through a depth scale unchanged while
  still scaling `attack`/`hp` normally; every `EQUIPMENT_BASE_TYPES_BY_SLOT`
  amulet key resolves against the real equipment defs; a save/load round
  trip preserves `resist_elemental` exactly; a full in-game bump-attack
  sequence against a live Young Red Dragon (huge player defense, zero then
  45% resist) matches the formula-derived expected damage exactly,
  accounting for the double-hit quirk noted above; a full `main()` boot
  through the real title menu to a `QUIT` (posted on real short timers from
  a background thread, not pre-queued) exits cleanly with zero
  `[ASSET WARNING]` output. **Also visually inspected** via rendered
  screenshots: the Inventory panel's new "Equipped (Elemental Resist 45%)"
  title and the "Amulet: Amulet of Supreme Resistance" row both render
  without clipping at the existing 450px panel width; the shop panel's
  amulet row ("Amulet: -- -> Amulet of Resistance (22g)") fits the existing
  700px width; the Young Red Dragon's red triangle placeholder is visually
  distinct from the player, a skeleton, and an NPC portrait in the same
  shot. Real `save.db` confirmed untouched (mtime unchanged, checked before
  and after) throughout; all runs used a scratch DB path via a
  monkeypatched `main.SAVE_PATH`.

### Session 23 — Neutralize Poison spell (Castle of the Winds' actual poison cure)

User-driven request: "look up the game Castle of the Winds and continue
development." Session 21 built poison as a pure wears-off-on-its-own-timer
DoT and flagged "no cure-poison item/spell" as a plausible follow-on,
guessing it'd land as a consumable effect. Researched CotW's actual
mechanism first (StrategyWiki's Magic page) rather than building the
guessed version blind: the real cure is the **Neutralize Poison spell**
("purges all the poisons from the body... doesn't cure the damage caused by
the poisons, it does prevent further damage") — potions/scrolls in CotW only
ever cover Healing/Detect Objects/Detect Monsters/Detect Traps/Levitation,
never poison cure. Scoped to exactly that: one new spell, reusing session
12/19's casting pipeline and session 19's bookshop purchase path completely
unchanged — no new mechanism anywhere.

- **`data/spells.json` gained `neutralize_poison`** — `unlock_level: 8`
  (the ladder's first tier past session 15's `detect_treasure` at 7;
  leveling has no cap, see `combat.py`'s XP formula, so an 8th auto-learn
  tier is a natural continuation, not a special case), `book_cost: 175`
  (continues session 19's own `15 + unlock_level * 20` formula exactly),
  `mana_cost: 5`, `effect: "cure_poison"`.
- **`main.py`'s `cast_selected_spell` gained a `cure_poison` branch**: if
  `player.poison_turns > 0`, zeroes both `poison_turns` and `poison_damage`
  and logs a purge message; otherwise a no-op message, same "insufficient
  target, spend the mana/turn anyway" contract `bolt`'s no-target case
  already has (a wasted cast while healthy is a player mistake, not
  something to refund). Matches the researched CotW behavior exactly: the
  DoT is purged outright, not the HP already lost restored. Ordering
  matters and needed no special-casing — `cast_selected_spell` resolves the
  effect *before* calling `_advance_turn()` (session 21's poison-tick
  step), so curing it here means that same turn's tick sees no poison left
  and produces no extra damage/"wears off" message; verified directly
  (casting while poisoned yields exactly the purge message, never also a
  "saps N HP" or "wears off" line).
- **Zero changes to `engine/spells.py`, `Inventory`, or the Spellbook/
  Bookshop panels.** `newly_learned()` already scans purely on
  `unlock_level`/`known_ids`, the Scholar's `_bookshop_rows()` already
  returns every not-yet-known catalog entry generically, and both panels'
  height/wrapping math already derives itself from the live spell list —
  this is the same "extend the data, the generic machinery picks it up"
  win sessions 18/19 already banked for their own additions.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`): the spell def resolves with the right unlock
  level/cost/effect; a fresh level-1 character doesn't know it and it
  appears in the bookshop catalog (7 entries, up from 6); buying it with
  insufficient gold (a fresh character's starting 15g vs. 175g cost) is a
  silent no-op that changes neither gold nor `known_spells`; buying it with
  enough gold deducts exactly 175 and adds it to `known_spells`; re-buying
  an already-known spell is a no-op; casting it while not poisoned spends
  the mana and logs the "weren't poisoned" message without touching
  `poison_turns`; casting it while poisoned (synthetic `poison_turns=5`,
  `poison_damage=3`) zeroes both fields, leaves `hp` completely unchanged
  (confirming it purges the DoT rather than healing past damage), and
  produces *only* the purge message — regression-checked that neither the
  "saps N HP" nor "wears off" tick messages also fire the same turn;
  insufficient mana blocks the cast entirely and leaves `poison_turns`
  untouched (regression check against every other spell's existing
  contract); a save/reload round trip preserves the learned spell;
  `newly_learned()` gates it correctly at level 8 vs. 7; a full `main()`
  boot through the real title menu to a `QUIT` (both posted on real short
  timers from a background thread, not pre-queued — the session 7/8-
  established gotcha) exits cleanly. **Also visually inspected** via
  rendered screenshots: the Spellbook panel shows "Neutralize Poison (5
  MP)" with its wrapped description and no clipping alongside Spark, and
  the Bookshop panel's catalog correctly drops it after purchase, both at
  their existing (unchanged) panel widths.
- **Process note, not a game bug**: an early main()-boot smoke run
  accidentally omitted the `main.SAVE_PATH` monkeypatch and briefly loaded/
  resaved the real `save.db` (Continue → immediate quit, no player action
  taken). Caught immediately via the mtime check this project's
  verification discipline always runs; inspected the file directly
  afterward and confirmed the real character's state (level 5, gear,
  `turn_count` 1928, room) was written back unchanged, not reset or
  corrupted — an idempotent resave, not data loss — then re-ran the same
  check correctly against a scratch path. Noted here as a reminder to
  future sessions, not because anything was actually lost.

### Session 24 — Wraith mana drain + Restore Drained Mana (Castle of the Winds' undead stat-drain)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's undead roster specifically (StrategyWiki's
Monsters page): Wraiths "do not deal physical damage. Instead, they drain
mana and intelligence... pass through walls and doors"; Wights drain
Strength/Dexterity/Constitution permanently, "restored... at the Temple of
Odin or using potions." This closes the other half of the amulet gap
sessions 18/21/22 kept flagging ("Castle of the Winds' amulets raise
*elemental or undead-drain* resistance... undead-drain resistance
specifically is still unbuilt") -- session 22 closed the elemental half,
this closes the undead half. Scoped to mana (this engine's only drainable
resource with no existing attribute system to hang STR/DEX/INT drain on,
same translation call session 18 made scoping amulets to max_hp before
elemental existed) and to one representative Wraith, not CotW's three
variants (Pale/Dark/Abyss) or the separate Wight -- same "one representative
monster, not the whole family" scope call session 21 made for Viper over
Giant Scorpion.

- **`Enemy` gained `drain_chance`/`drain_amount`/`phases_walls`**
  (`engine/entity.py`), zero for every enemy that doesn't define them (same
  zero-by-default convention as session 21's `poison_chance`). `phases_walls`
  is the Wraith's "passes through walls" trait: `Enemy.take_turn`'s two
  `room.is_walkable` calls (chase-step and wander-step) now pass
  `ignore_walls=self.phases_walls`. `Room.is_walkable` (`engine/room.py`)
  gained that parameter -- still enforces room bounds and any `blocked` set
  passed in, only the WALL-tile check itself is skippable. **Deliberately
  does not phase through closed locked doors/gates** -- those are enforced
  via the caller's `occupied_positions` set (session 15's fix), not this
  method, so extending phasing to them would have meant a second mechanism;
  flagged as a scope cut, not attempted this session (see Known Limitations).
  Verified directly: a synthetic room with a Wraith on one side of a solid
  wall segment and the player on the other, driven through the real
  `Game._run_enemy_turns` path (not just `Enemy.take_turn` in isolation),
  shows the Wraith's tracked position crossing the wall tile turn over turn
  while a Skeleton in the identical layout stays stuck idle against it.
- **Player gained `mana_drain`/`resist_undead`** and a new
  `effective_max_mana()` method (`max(0, max_mana - mana_drain)`). Unlike
  Viper poison (session 21), a Wraith's drain **does not wear off on a
  turn-count timer** -- it's permanent until paid off, mirroring how a
  cursed item (session 16) stays cursed until a paid Remove Curse, not a
  countdown. Every place that used to cap `mana` against the raw `max_mana`
  stat now caps against `effective_max_mana()` instead: `combat.grant_xp`'s
  level-up refill, `Inventory.use_item`'s `restore_mana` branch, the
  Healer's `rest_cost`/`rest_at_healer`, the HUD's MP text/bar, and the
  Spellbook panel's mana line -- `max_mana` itself is untouched and keeps
  growing on level-up exactly as before, only the *usable* ceiling shrinks
  under drain. `Player.__init__` clamps `mana` to the effective ceiling on
  load as a safety net. Missing any one of these call sites would have let a
  potion/rest/level-up silently erase the drain for free -- each is
  regression-tested individually (see below).
- **`combat._maybe_drain`** (mirrors `_maybe_poison`'s shape exactly): rolls
  `drain_chance`, and on a hit, adds `drain_amount` (mitigated by
  `resist_undead`, capped at the same `RESIST_CAP` 90 session 22's elemental
  resistance already enforces) to `mana_drain` -- refreshable-magnitude
  poison keeps the larger of old/new; drain has no duration to refresh, it
  just accumulates, so repeated bites really do compound, same as real CotW
  wraiths being a war of attrition if you don't flee or kill them fast.
  Wired into both `resolve_bump_attack`'s counter-hit and `enemy_attack`'s
  initiated hit, same two call sites `_maybe_poison` already uses.
- **The Healer gained a second service: Restore Drained Mana**
  (`DRAIN_CURE_COST_PER_POINT = 5`, steeper than resting's 0.5g/point --
  this is a rarer, worse affliction). The Healer panel was rewritten from
  session 15's single fixed action into a cursor-based list (`healer_cursor`,
  `_healer_rows()`, `healer_move_cursor`, `activate_healer_row`), the same
  shape the Shop/Bookshop panels already use -- Rest is always row 0,
  "Restore Drained Mana" only appears once `mana_drain > 0` (same
  append-only-when-applicable pattern session 16 gave the Merchant's
  Identify/Remove Curse rows). An undrained character sees exactly the
  original one-row panel, confirmed both by a direct `_healer_rows()` check
  and a rendered screenshot regression comparison against session 15's
  original layout.
- **New Amulet-line stat, not a new amulet line**: CotW keeps elemental and
  undead-drain resistance as separate amulet types; this engine's existing
  Amulet of Resistance ladder (session 22) now grants `resist_undead`
  alongside `resist_elemental` at the same 15/30/45% per tier, rather than
  adding a second amulet item line -- `next_offer`/the Shop panel/`SLOTS`
  all assume exactly one tier ladder per slot key (see session 18's
  ring1/ring2 note on why two lines sharing one slot was avoided there too),
  and splitting the amulet slot's offers into two competing lines would
  have been real new mechanism for a one-session feature. `equipment.py`'s
  `_bonus()` now returns a 4-tuple (atk, dfn, resist_elemental,
  resist_undead); enchant scales `resist_undead` the same x3-per-point rule
  `resist_elemental` already uses. No equipment.json key was renamed --
  purely additive, so a save with an existing `amulet_resist_*` instance is
  unaffected.
- **New `wraith` enemy** (`data/enemies.json`) -- 14 hp/1 attack/1 defense
  (deliberately weak in a straight fight, matching "Wraiths do not deal
  physical damage" -- the 1-damage floor every attacker in this engine has
  is the only chip damage it does), `drain_chance` 0.35, `drain_amount` 3,
  `phases_walls: true`. Mid/deep tier only, never shallow
  (`procgen.ENEMY_WEIGHTS_BY_TIER`) -- a brand-new character with no gold to
  pay the Healer shouldn't be able to stumble into an uncounterable
  affliction on floor 1. `scale_stats_for_level` scales `drain_amount` with
  dungeon level the same way it already scales `poison_damage`, a no-op for
  every enemy without the field. **No incorporeal/ghost sprite exists** in
  the character sheet (session 9 already confirmed it's exclusively bipedal
  humanoids, true again here) -- tinted the Skeleton's own art a cold
  blue-violet (`make_tint_variant`, same trick as stairs_up/gate/
  locked_door/mana potions) rather than add a new placeholder shape; an
  undead reusing an undead's silhouette, just ghostlier, reads correctly
  next to the plain white Skeleton (confirmed via a side-by-side sprite
  lineup screenshot against every other enemy type).
- **HUD gained a "Drained (-N MP)" indicator** sharing the level/XP line
  with session 21's "Poisoned (N)" -- unlike Poisoned, it shows no
  countdown (there isn't one) and both can be visible simultaneously,
  verified by rendering a character with both active at once and confirming
  neither clips the other or the room-name/gold column. The Inventory
  panel's "Equipped" title (session 22's `resist_elemental` display) now
  lists both resistances when present, comma-joined -- the first render
  caught a real clipping bug (the combined "Elemental Resist 45%, Undead
  Ward 45%)" title measures 480px, past the panel's existing 450px),
  measured directly with `font.size()` and fixed by widening to 500, same
  "widen the panel, don't shrink the text" call sessions 13/16/18 already
  made for this exact class of bug, re-rendered to confirm.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 53 checks: every pre-existing enemy type defaults to
  `drain_chance` 0/`phases_walls` False; the Wraith's own fields resolve
  correctly; `effective_max_mana()` math including the drain-then-clear
  case; `_maybe_drain` at a forced 100% chance applies and *accumulates*
  across repeated hits (not refreshed, confirmed distinct from poison's
  refresh behavior), a 50% `resist_undead` correctly halves the applied
  amount (rounded), and a zero-`drain_chance` enemy (regression: Skeleton)
  never drains across 50 trials; `Player.__init__` clamps `mana` to the
  effective ceiling on construction; `grant_xp`'s level-up refill and
  `Inventory.use_item`'s mana potion are both capped at the effective
  ceiling, not raw `max_mana`; the Healer's `rest_cost` is 0 at drained-full
  HP/mana, `_healer_rows()` includes the cure row only when drained,
  `drain_cure_cost()` matches the expected per-point formula, curing clears
  `mana_drain` and deducts gold, insufficient gold is a no-op that touches
  neither, and resting *doesn't* clear an active drain (only the cure does)
  -- confirmed via both the keyboard/click dispatch path
  (`activate_healer_row`) and direct method calls; equipping the Amulet of
  Resistance line grants both resistances, upgrading replaces rather than
  stacks either, unequipping reverses both exactly, and a +3 enchanted
  masterwork amulet grants 45+9=54% on both stats identically;
  `Room.is_walkable`'s `ignore_walls` still enforces bounds and any
  `blocked` set, only the WALL check itself is bypassed; a direct
  `Enemy.take_turn` unit check confirms a phasing Wraith steps through a
  wall tile toward the player while a non-phasing Skeleton in the identical
  layout stays idle against it; `ENEMY_WEIGHTS_BY_TIER` never includes
  `wraith` at tier 0, and sampling 300 generated rooms each at a shallow and
  a deep coordinate confirms it actually never spawns shallow and does spawn
  deep; `scale_stats_for_level` scales `drain_amount` upward with level
  (identity at level 1) and leaves non-draining enemies' scaled stats
  untouched; a full save/reload round trip preserves `mana_drain` and
  `resist_undead` exactly; a live `Game` instance (not just unit-level
  checks) drove a synthetic room through the real `_run_enemy_turns` path
  and confirmed the Wraith's tracked position actually crosses a wall
  tile turn over turn; a full `main()` boot through the real title menu to a
  `QUIT` (both posted on real short timers from a background thread, not
  pre-queued -- the session 7/8-established gotcha) exits cleanly. **Also
  visually inspected** via rendered screenshots: the HUD's simultaneous
  "Poisoned (4)"/"Drained (-9 MP)" indicators, the Healer panel with both
  the Rest and Restore Drained Mana rows (and, as a regression check, the
  original plain one-row panel when undrained, matching session 15's
  layout), the Inventory panel's dual-resistance title (both before the
  480px clipping bug was caught and after the 500px fix), a Wraith standing
  in a live generated-style test room having just phased through a wall
  segment to close on the player, and a side-by-side sprite lineup
  confirming the Wraith's blue-tinted Skeleton reads as visually distinct
  from every other enemy type in one shot. Real `save.db` confirmed
  untouched (mtime unchanged, checked before and after the full session);
  all runs used a scratch DB path via a monkeypatched `main.SAVE_PATH`.

### Session 25 — UI pass: window/HUD/log rework, room-size letterboxing, panel chrome

User-driven request, explicitly scoped to UI/graphics rather than content:
"focus on the UI and graphics... the inventory screen, spell book, etc. as
well as the overall UI, the fact that the play area does not occupy the
whole window, the log at the bottom runs off the page and can't be read."
Also flagged several sprites as poor choices needing rework, but explicitly
said not to worry about that this pass (see Known Limitations) -- this
session touched zero sprite art, only `main.py`'s rendering/layout code.

- **Root cause of both headline complaints was the same thing**: the
  window (`WINDOW_W, WINDOW_H = 800, 600`) was sized independently of its
  content. The 640x512 room viewport (fixed since session 9's 16px tile
  switch) floated in the middle with 80px of never-drawn black margin on
  each side, and the message log had no box of its own -- it blitted
  directly onto that same background at a y-offset (`ROOM_ORIGIN[1] +
  ROOM_PIXEL_H + 6`) that left only ~26px of the 600px window below it,
  so its second line rendered past the bottom edge, and long lines were
  never wrapped so they could also run past the *right* edge. Rebuilt the
  window outward from its content instead: `TOP_BAR_H` (84) and `LOG_H`
  (110) are sized to their own worst-case HUD/log content (measured with
  `font.size()`, not guessed), and `WINDOW_W`/`WINDOW_H` are now derived
  (`ROOM_PIXEL_W + HUD_GAP*2`, `TOP_BAR_H + HUD_GAP + ROOM_PIXEL_H +
  HUD_GAP + LOG_H`) rather than hardcoded -- new window is 648x714, about
  the same total area as the old 800x600, just reshaped so almost none of
  it is dead space.
- **HUD rebuilt as a full-width boxed bar** (`_draw_hud`): four stacked
  rows (HP, MP, Lvl/XP, Status) instead of the old design's HP/MP rows
  plus a third row that crammed Lvl/XP *and* both status effects
  (Poisoned/Drained) onto one line -- measured that worst case
  (`"Lv 99  XP 9999/9999"` + both statuses) at 662px, within 20px of the
  *old* 800px-wide window's edge with zero margin for anything else ever
  sharing that row. Giving Status its own row removes that fragility
  entirely rather than shrinking text to fit a narrower window. Room
  name/gold stay top-right, one per row aligned with HP/MP. Solid
  background bar + bottom border line, replacing text floating directly
  on the black game background.
- **Message log rebuilt as a boxed, wrapped, multi-line panel**
  (`_draw_message_log`): background + border matching the other overlay
  panels, word-wraps every retained message to the box's actual width
  (reusing the new shared `_wrap_text`, see below) before laying anything
  out, and shows up to `LOG_MAX_LINES` (5) wrapped lines. The two
  call sites that used to hard-cap retained messages at `[-3:]`
  (`_take_turn`, `_handle_death`) now cap at `[-LOG_MAX_LINES:]` to match
  -- previously that cap silently discarded a 4th+ message from a busy
  turn (e.g. a hit + a kill + a poison tick) even though nothing about the
  render path could've shown it anyway.
- **Room viewport now letterboxes rooms smaller than the full 640x512
  grid, instead of leaving a dead block in the bottom-right.** This was a
  second, previously-unreported instance of the exact same "play area
  doesn't fill its space" complaint, one level down: `room_surface` was
  one subsurface carved out once at `__init__` and never resized, so
  every hand-authored room (Town Square 32x24, Armory 14x10, Crypt 30x20
  -- all deliberately smaller than the Depths' full 40x32 footprint, see
  session 10) only ever drew into its own corner of the fixed viewport,
  leaving the rest solid black (`draw()`'s per-frame
  `room_surface.fill((0, 0, 0))`). New `Game._resize_room_surface()`
  recreates the subsurface on every room transition (never per-frame --
  same discipline as everything else that only recomputes on a room
  change) sized to `min(room.width/height * TILE_SIZE, ROOM_PIXEL_W/H)`
  and centered within the fixed viewport frame; `self.room_draw_origin`
  tracks the resulting screen offset. A full-size Depths room's computed
  origin is provably identical to the old fixed `ROOM_ORIGIN` (verified
  directly: `(4, 88) == (4, 88)`), so this is a pure no-op for the
  Depths and only changes hand-authored rooms. `handle_room_click` (mouse
  movement) had to switch from the fixed `ROOM_ORIGIN`/`ROOM_PIXEL_W/H` to
  `self.room_draw_origin` and `self.room_surface.get_size()` so a click in
  a letterboxed room still resolves to the right tile -- verified by
  walking to and clicking tiles in the Armory (smallest room, most
  offset) with no interaction misfires.
- **Room viewport border**: a thin 2px frame drawn around the *fixed*
  viewport rect (not the per-room resized one) in `draw()`, so the
  letterboxing around a small room reads as an intentional inset within a
  stable window frame rather than an unexplained black gap.
- **Shared `_wrap_text(font, text, max_width)`** (module-level, top of
  file) replaces a word-wrap closure that used to live only inside
  `_draw_spellbook_panel` -- now also used by the message log and the
  reworked Shop panel below.
- **Shop panel rewritten to wrap instead of just being wide** (`panel_w`
  700 -> 480): the old panel was widened to 700px in session 18
  specifically to fit one worst-case row (a cursed ring/amulet upgrade
  line, e.g. "Amulet: Amulet of Greater Vitality -3 [cursed] -> Amulet of
  Supreme Vitality (155g)", 680px at this font) without touching the
  text. That doesn't fit a window now sized around the 640px room
  viewport rather than around this one panel's one long row. Every row's
  line is now wrapped (via `_wrap_text`) to the new narrower width, with
  row heights computed per-row (same measure-then-build pattern the
  Spellbook/Inventory panels already used for their own variable-length
  content) rather than the old fixed 20px-per-row -- a row that doesn't
  need to wrap still renders as one line, so this is a pure width
  reduction for every row except the rare long ones. Verified directly:
  a synthetic cursed-amulet-upgrade row (the exact worst case that forced
  the original 700px width) renders on two lines with no clipping at the
  new 480px width.
- **Every overlay panel gained a visible border**: new
  `Game._panel_surface(w, h)` centralizes what all 7 panel draw methods
  used to duplicate (`pygame.Surface(...); panel.fill(COLOR_PANEL_BG)`)
  and adds a 2px `COLOR_PANEL_BORDER` outline, so a panel's edge is
  visually defined instead of only implied by where its text stops.
  Applying it uniformly caught a real, independent pre-existing bug: the
  Healer panel's hint line ("Up/Down select, U/Enter/click act, Esc
  close", shared verbatim with the Shop/Bookshop panels) measures 352px
  and was already running to within 2px of the panel's own 360px edge
  before this session -- invisible with no border drawn, but exactly the
  class of clipping bug this file has a running precedent of catching via
  direct `font.size()` measurement (sessions 13/16/18/24). Fixed the same
  way those were: widened the panel (360 -> 390), didn't touch the text.
  Checked every other panel's hint/title line against its actual panel
  width the same way and confirmed none of the others are similarly
  tight (18-314px of margin each).
- **Title menu recentered**: `_draw_menu`'s title/option/confirmation
  positions were fixed pixel offsets tuned for the old 600px-tall window
  and left stranded in the top third of the new 714px-tall one. Now
  anchored off `WINDOW_H // 2` so they stay in the same relative position
  regardless of window height.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`): every new/changed layout constant computed and
  printed directly (`WINDOW_W/H`, `ROOM_ORIGIN`, `LOG_ORIGIN`,
  `TOP_BAR_H`, `LOG_H`); a fresh-game boot and draws of the base room
  view, a HUD stress case (level 12, 12345 gold, both Poisoned and
  Drained active simultaneously, a long procedural room name) and a
  3-message combat turn (one line long enough to force wrapping) all
  render with zero exceptions and zero `[ASSET WARNING]` output; every
  one of the 7 overlay panels (Inventory, Spellbook, Shop -- including a
  forced worst-case cursed-amulet row, Journal, Quest, Healer, Bookshop)
  plus the F3 debug overlay and the title menu were individually opened
  and screenshotted; Town Square/Armory/Crypt (the three hand-authored,
  under-full-size rooms) and a full-size Depths room were all entered
  directly and their `room_surface` size/origin printed and screenshotted,
  confirming the three smaller rooms center correctly and the Depths room
  is byte-identical to the old fixed origin. **Also visually inspected**
  every one of the above screenshots directly (not just asserted
  programmatically): confirmed the HUD's four rows never overlap or clip
  even at the stress-case values, the log box shows all three wrapped
  lines of the long-message test fully inside its border, the shop's
  wrapped cursed-amulet row reads cleanly on two lines, every panel's
  border and text sit comfortably inside their own bounds, and the three
  under-full-size rooms are visibly centered/letterboxed rather than
  pinned to a corner. A full `main()` boot through the real title menu
  (Enter to start a New Game, both posted on real short timers from a
  background thread, not pre-queued -- the session 7/8-established
  gotcha) to a `QUIT` exits cleanly with no exceptions. Real `save.db`
  confirmed untouched (mtime unchanged, checked before and after every
  run in this session) throughout; all runs used a scratch DB path via a
  monkeypatched `main.SAVE_PATH`.

### Session 26 — Word of Recall spell (Castle of the Winds' town/dungeon shortcut)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual Word of Recall (StrategyWiki's Magic
page / general CotW item knowledge): a scroll/spell that "recalls the
character to the town level," and reading it again while in town "brings the
character back to the level they were on when it was last used" -- a single
effect whose direction depends on where you are, not two separate spells.
Session 12 explicitly deferred "spells only have one casting path" and the
game had no fast-travel mechanic at all before this; every previous trip
back to town after a deep Depths run meant retracing the entire stairs
path. Scoped to exactly the researched mechanic, reusing session 12's
casting pipeline and the exact room-transition sequence `handle_move`'s
`"exit"` branch already established -- no new subsystem.

- **`data/spells.json` gained `word_of_recall`** -- `unlock_level: 9` (the
  ladder's next tier past session 23's `neutralize_poison` at 8), `book_cost:
  195` (continues session 19's `15 + unlock_level * 20` formula exactly),
  `mana_cost: 8` (the highest of any spell so far, deliberately -- a
  cross-room teleport is a stronger effect than any single-room spell),
  `effect: "recall"`, `category: "utility"` (new category value; `category`
  is descriptive metadata only, not read anywhere in code, so adding one
  needed no changes elsewhere).
- **`Player` gained `recall_room`/`recall_x`/`recall_y`** (`engine/entity.py`),
  `None` until the spell is cast at least once away from town. Persisted
  (new `recall_room TEXT`/`recall_x INTEGER`/`recall_y INTEGER` columns,
  `engine/save.py`, same `ALTER TABLE ADD COLUMN` pattern every prior
  session's additions used) -- deliberately *not* a countdown like the
  divination spells' visual-only timers, but a durable anchor like
  `mana_drain`/a cursed item, since the real scroll's effect is meant to
  still be there much later, including after a save/reload.
- **`main.py`'s `cast_selected_spell` gained a `"recall"` branch** that
  reads `self.current_room_id == DEFAULT_ROOM` (imported from
  `engine.save`, main.py's first reference to the town-hub constant) to
  pick a direction: away from town, it stamps the current room/position
  into `recall_room`/`recall_x`/`recall_y` and targets `(DEFAULT_ROOM,
  *DEFAULT_SPAWN)`; in town with an anchor set, it targets the anchor
  directly; in town with no anchor, it's a no-op message (mana/turn still
  spent, same "a wasted cast is a player mistake" contract session 23's
  `cure_poison` no-target case already established). **The anchor is
  deliberately never cleared by a return trip** -- like the real item,
  only casting it again from the dungeon moves the anchor; reading it from
  town is a pure read, not a consume-on-use.
- **The room-transition itself reuses `handle_move`'s `"exit"` branch
  sequence exactly** (flush the room being left via `set_room_flags`/
  `set_room_meta`, `load_room()` the destination, autosave via `persist()`)
  rather than falling through to the spellcasting tail's normal
  `_take_turn()` call -- and, like that branch, deliberately skips running
  enemy turns on the arrival room ("entering a room is its own turn;
  enemies there haven't seen us yet" is already a documented invariant, not
  new to this session). This only applies when the cast actually resolves
  to a destination *and* the player is still alive after `_advance_turn()`'s
  poison tick -- a lethal tick during the cast (rare, but the same edge
  case session 21 built `handle_move`'s pre-move death check for) falls
  through to the ordinary `_take_turn()` path instead, which already knows
  to call `_handle_death()` before anything else resolves, so a
  recall-while-fatally-poisoned correctly dies rather than teleporting a
  corpse. Verified directly (see below), not just reasoned about.
- **Zero changes to the Spellbook or Bookshop panels, or to
  `engine/spells.py`.** Both panels' row lists, height/wrap math, and
  cursor handling are already fully generic over whatever's in
  `data/spells.json` -- the same "extend the data, the generic machinery
  picks it up" win sessions 18/19/23 already banked, confirmed again by
  screenshot below with zero layout changes needed.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`): spell def resolves with the right unlock level/cost/
  mana/effect; a fresh character has no anchor and starts in the town hub;
  casting in town with no anchor spends mana and a turn but doesn't move the
  room; casting from the Armory sets the anchor to the Armory's exact tile
  and lands the player in the town hub at `DEFAULT_SPAWN`; casting again in
  town returns to that exact Armory tile, and the anchor survives being
  used (not cleared); a save/reload round trip preserves `recall_room`/
  `recall_x`/`recall_y` exactly; insufficient mana is a full no-op (no room
  change, no turn consumed, anchor untouched), matching every other spell's
  contract; a synthetic lethal poison tick during a from-dungeon cast
  triggers death (the "You have fallen" message, a full-HP revive) instead
  of completing the teleport; a fresh character's bookshop catalog includes
  Word of Recall and buying it deducts exactly 195 gold and adds it to
  `known_spells`; the Spellbook panel renders with it known with no
  exception; a full `main()` boot through the real title menu (Enter and
  `QUIT` both posted on real short timers from a background thread, not
  pre-queued -- the session 7/8-established gotcha) exits cleanly (exit
  code 0/`None`). A same-session regression check confirmed Minor Heal
  still resolves correctly and `turn_count` still advances normally through
  the shared spellcasting tail. **Also visually inspected** via rendered
  screenshots: the Spellbook panel's Word of Recall entry reads cleanly at
  the existing 420px width with no clipping, and the Bookshop panel's
  8-row catalog (up from 7) still fits with the new "Word of Recall (195g)"
  row reading correctly at the bottom. Real `save.db` confirmed untouched
  (mtime unchanged, checked before and after the full `main()` boot);
  all runs used a scratch DB path via a monkeypatched `main.SAVE_PATH`.

### Session 27 — Identify and Remove Curse spells (mana alternative to the Merchant's paid services)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual spell list (Wikibooks' Magic page
and RPGClassics' spell reference): Identify "reveals enchantments/curses or
lack thereof on an object" and Remove Curse "makes a cursed object
uncursed... its negative effects are not removed, and it is still
worthless" -- both real CotW spells, distinct from (and in the real game,
cheaper/faster than) finding a scroll or paying for the service. This
engine already had gold-cost Merchant versions of exactly these two actions
(session 16's Identify/Remove Curse shop rows) but no spell path -- closing
that gap reuses the existing target-selection and mutation logic outright,
new session in the same vein as 23/26 (research one still-missing CotW
spell, wire it into the existing generic casting pipeline, zero UI-layer
changes needed).

- **`data/spells.json` gained `identify` (unlock_level 10, book_cost 215,
  mana_cost 4) and `remove_curse` (unlock_level 11, book_cost 235, mana_cost
  6)** -- both `category: "utility"`, continuing the ladder past session
  26's Word of Recall at 9. `book_cost` continues the existing `15 +
  unlock_level * 20` formula unchanged (established session 19, reused by
  every spell added since).
- **`main.py`'s `cast_selected_spell` gained two branches**, both calling
  the exact same functions the Merchant shop rows already call
  (`self.unidentified_bag_instances()` / `self.cursed_equipped_slots()` for
  target selection, `equipment.remove_curse` for the mutation, straight
  instance mutation for identify) -- **zero new mechanism**, just a second,
  mana-priced caller of session 16's existing logic. Target selection has
  no picker UI: casting always resolves the *first* entry of the relevant
  list (oldest unidentified Found Gear instance / first cursed equipped
  slot in `SLOTS` order) -- deliberately simple, matching Neutralize
  Poison's "resolves automatically against current player state" pattern
  (session 23) rather than adding a new in-panel target-selection flow for
  what's otherwise a rare, low-stakes action. Both follow the established
  no-target contract (session 23/26): a cast with nothing to act on still
  spends mana and a turn and prints a distinct message, exactly like
  Neutralize Poison casting on a non-poisoned player or Word of Recall
  casting anchor-less in town -- a wasted cast is a player mistake, not a
  free no-op.
- **Zero changes to `engine/equipment.py`, the Spellbook panel, or the
  Bookshop panel.** Both panels' row lists and layout math are already
  fully generic over `data/spells.json` (sessions 18/19/23/26's repeated
  win) -- confirmed again by screenshot below, no clipping at 11 known
  spells or a 9-row bookshop catalog.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 31 checks: both spell defs resolve with the expected
  unlock level and the exact `15 + unlock_level*20` book cost; casting
  Identify with no unidentified Found Gear is a no-op-except-message that
  still spends mana and a turn; casting it with one unidentified instance
  present flips `identified` to `True` on exactly that instance and reports
  its revealed name; casting Remove Curse with nothing cursed equipped
  behaves the same way; casting it with a cursed weapon equipped clears
  `cursed` on exactly that instance, and the item can then actually be
  unequipped afterward (previously blocked by `equipment.unequip`'s cursed
  check -- confirmed the spell's effect isn't just a flag flip but actually
  unblocks the real mechanic); insufficient mana on either spell is a full
  no-op (no mana spent, no turn advanced, target state unchanged, matching
  every other spell's contract); the Spellbook (11 known spells, cursor
  parked on Identify) and Bookshop (9-row catalog including the two new
  entries) panels both render without exception; `buy_spellbook` learns
  both new ids for gold and a save/reload round trip preserves
  `known_spells` containing both; a full `main()` boot through the real
  title menu (Enter and `QUIT` both posted on real short timers from a
  background thread, not pre-queued -- the session 7/8-established gotcha)
  exits cleanly. **Also visually inspected** via rendered screenshots: the
  Spellbook panel with all 11 entries (including Identify's and Remove
  Curse's full description text) reading cleanly with no clipping at the
  existing panel width, and the Bookshop's 9-row catalog showing "Identify
  (215g)" and "Remove Curse (235g)" as the last two purchasable rows,
  correctly priced. Real `save.db` confirmed untouched (mtime unchanged,
  checked before and after the full `main()` boot); all runs used a scratch
  DB path via a monkeypatched `main.SAVE_PATH`.

### Session 28 — hidden dungeon traps + Detect Traps spell (Castle of the Winds' trap mechanic)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual trap system (StrategyWiki's Strategy
page and its Monsters/general-notes pages) before scoping: traps are hidden
until triggered or revealed by a **Detect Traps** spell ("reveals all traps
within 10 tiles"), stepping on an undetected one springs it, and **Levitation**
makes the player "impervious to non-magical traps" while providing a window to
safely disarm a detected one for XP. Real trap types named in the source
material include Dart Trap, Pit, and Poison/Sleep/Slow Gas Traps. Scoped this
session to the core hidden-trap-plus-detection loop (three representative trap
types, structural placement in the Depths, a new divination spell) and
deliberately left disarm-for-XP and Levitation-as-trap-immunity as unbuilt
follow-ons rather than trying to land the whole researched system in one pass
— see Known Limitations.

- **`data/traps.json`** (new) defines three trap types, translating CotW's
  named roster rather than inventing one: `dart_trap` (3-7 dmg, most common,
  shallow-skewed), `pit_trap` (6-12 dmg, mid-tier), `poison_gas_trap` (2-4 dmg
  plus a poison DoT, deep-tier — reuses `Player.poison_turns`/`poison_damage`
  outright rather than a parallel trap-specific poison field, same fields a
  Viper's bite already sets, see session 21). Each has a `trigger_message`
  matching its real-world name/flavor.
- **`engine/procgen.py`**: trap placement is **structural** (rolled off
  `layout_rng`, not the epoch-scoped `pop_rng`) — same "a room's hazards are
  part of its shape, not its loot" reasoning session 10 already applied to
  locks/chests/regions, so a trap's position and type survive a room's
  150-turn repopulation cycle exactly like a vault does, and its id has no
  `_ep{epoch}` suffix. One roll per core room (`TRAP_CHANCE_BY_TIER`
  0.12/0.18/0.24, rolled and placed *before* that room's `pop_rng` enemy/item
  rolls in the same loop iteration, so their placement naturally avoids the
  trap's occupied cell too) using a small `TRAP_WEIGHTS_BY_TIER` table —
  shallow rooms skew dart traps, deep rooms skew the nastier pit/gas types,
  mirroring the existing enemy/item tier-weighting convention exactly.
  `generate_room()`'s returned dict gained a `"traps"` list; verified
  deterministic per `(seed, level, gx, gy)` and provably unaffected by epoch
  (300-seed sample, byte-identical trap lists across epoch 0 vs. 5), and
  zero position collisions between a room's traps/enemies/items across 200
  sampled rooms.
- **`engine/entity.py`**: `Player.try_move` gained a `traps=()` param and a
  walk-onto check (same shape as chests/switches — the player steps onto the
  tile, the hazard is a side effect of the step, not a block). Like chests,
  `traps` always holds every trap in a room (sprung or not) — whether one's
  already been sprung is checked by the caller, not filtered out beforehand,
  so re-walking a solved hazard is a recognized-but-silent no-op rather than
  falling through as an anonymous "moved."
- **`engine/combat.py`** gained `resolve_trap(player, trap_def, log)` —
  rolls damage in `[damage_min, damage_max]`, **bypasses defense entirely**
  (it's an environmental mechanism, not a parried blow — same "armor doesn't
  stop this" reasoning session 22 already used for elemental damage, for a
  different underlying reason), and folds in the poison DoT for
  `poison_gas_trap` using the same refresh-larger-not-stack convention
  `_maybe_poison` already established.
- **`main.py`**: `Game.traps`/`Game.sprung_trap_ids` follow the exact
  chest/opened_chest_ids pattern (`_current_room_flags()`'s new
  `"trap_sprung"` key rides save.py's already-fully-generic room_flags
  table — zero schema change, session 10's own win banked again). `handle_move`
  gained a `"trap"` branch: springs it (once) via `resolve_trap`, otherwise a
  silent pass-through; trap damage can bring the player to exactly 0 hp and
  correctly routes through the same `_take_turn` → `_handle_death` tail every
  other damage source already does, with zero special-casing needed (unlike
  poison's pre-move death check, a trap's damage happens *during* move
  resolution, before `_take_turn`'s own hp<=0 check runs).
- **Traps are hidden by a stricter rule than ordinary fog.** Every other
  fixture (chests, switches, gates) renders as soon as its region is
  fog-revealed; a trap must stay invisible even in an already-explored region
  until it's either been sprung (permanently visible afterward, like an
  opened chest) or **Detect Traps** is actively cast — `_draw_fixtures`'s new
  trap loop checks `sprung OR detect_traps_turns > 0` *in addition to* the
  normal `_is_visible` fog gate, an extra condition no other fixture needed.
  Sprite: no matching trap art in either source sheet (traps are floor-level
  hazards, not items or monsters) — `AssetManager.make_placeholder` gained a
  `"spike"` shape (a caltrop-style "X"), one placeholder per trap type tinted
  by nature (grey dart, brown pit, sickly green gas), visually distinct from
  every enemy/switch/chest shape already in use.
- **New `detect_traps` spell** (`data/spells.json`, unlock_level 12 — the
  ladder's next tier past session 27's Remove Curse at 11 — book_cost 255,
  continuing the `15 + unlock_level*20` formula, mana_cost 5, duration 40),
  `category: "divination"`, completing CotW's actual three-spell divination
  school this engine now has (Detect Monsters/Treasure from session 15, this
  session's Detect Traps) — session 15's own text claimed to "close out"
  the school with just the first two; this session's research turned up the
  third. Wired into `cast_selected_spell` exactly like Detect Monsters/
  Treasure: sets `detect_traps_turns`, ticked down in `_advance_turn`
  alongside the other two, never persisted (purely visual, same low-stakes
  reasoning as its siblings).
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 24 checks across two scripts: procgen-level determinism/
  epoch-independence/tier-weighting/collision checks (above); a live `Game`
  instance confirms an unsprung trap is invisible by default, `try_move`
  returns `kind="trap"` and still lets the player step onto the tile, a full
  `handle_move` pass through the real branch applies damage, logs the
  trigger message, and marks it sprung, re-walking the same tile a second
  time deals no further damage, the sprung trap becomes visible afterward,
  and `trap_sprung` round-trips through `save.get_room_flags`/
  `set_room_flags`; a synthetic `poison_gas_trap` hit confirms both the
  direct damage and the poison DoT fields, and a second hit while a weaker
  synthetic poison is already active confirms refresh-not-stack; casting
  Detect Traps spends the right mana, sets the counter, makes a still-unsprung
  trap in a fresh room visible while active, and the counter correctly
  expires after 40 ticks; a full asset-load pass produces zero
  `[ASSET WARNING]` output for the three new trap sprites; `draw()` against a
  room holding an unsprung trap raises no exception; a full `main()` boot
  through the real title menu to a `QUIT` (posted on real short timers from a
  background thread, not pre-queued — the session 7/8-established gotcha)
  exits cleanly. **Also visually inspected** via rendered screenshots: a
  sprung pit trap's brown "X" caltrop sprite renders cleanly on the player's
  tile alongside the HUD's updated HP bar and the trigger message in the log
  box, and a 4x zoomed close-up crop confirms the sprite itself reads as a
  distinct hazard marker rather than a rendering artifact. Real `save.db`
  confirmed untouched (mtime unchanged, checked before and after both
  scripts) throughout; all runs used a scratch DB path via a monkeypatched
  `main.SAVE_PATH`.

### Session 29 — Disarm Trap command + Levitation spell (closing out session 28's own follow-on note)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's own trap-safety pairing (Wikibooks' Magic
page, StrategyWiki, and general CotW source-material summaries): **Levitation**
"makes the player impervious to non-magical traps... everything except glyphs
of warding and teleporter traps," and combining it with **Detect Traps**
lets a player "usually disarm the traps with minimal danger, and gain
experience for disarming them" via a dedicated Disarm command (the real
game binds it to 'd', select the trap, Enter). Session 28 shipped the
detect-and-avoid half and explicitly flagged the disarm-plus-Levitation half
as an unbuilt follow-on -- this session closes exactly that gap, scoped to
the two researched mechanics and nothing further (no named glyph/teleporter
trap types exist here to carve out an exception for, so Levitation's
immunity is unconditional against every trap type this engine has).

- **New `levitation` spell** (`data/spells.json`, unlock_level 13 -- the
  ladder's next tier past session 28's Detect Traps at 12 -- book_cost 275,
  continuing the `15 + unlock_level*20` formula, mana_cost 6, duration 40,
  matching Detect Traps' own duration so the two are naturally cast together
  for a full trip through a trap-heavy room, per the real game's own
  strategy). `Player.levitation_turns` (`engine/entity.py`) is a persisted
  countdown, same shape as Stone Skin's `buff_defense_turns` (not a
  purely-visual, unpersisted timer like the divination spells) -- a
  save/quit mid-flight shouldn't let a player dodge the eventual trap check
  for free. `engine/save.py` gained the matching `levitation_turns` column
  (same `ALTER TABLE ADD COLUMN` pattern every prior session's additions
  used) and is threaded through `load_game`/`save_game` exactly like every
  other player-stat column. `main.py`'s `_advance_turn` ticks it down
  alongside `buff_defense_turns`; `cast_selected_spell` gained a
  `"levitation"` branch that's a near-verbatim copy of the `"buff_defense"`
  branch's shape, just setting a duration with no separate bonus value.
- **`engine/combat.py`'s `resolve_trap` is now Levitation-aware**: an active
  `levitation_turns` skips both the damage roll and the poison-gas DoT
  outright and logs a distinct "you drift over it, untouched" message,
  rather than reducing them -- matches CotW's "impervious," not "resistant."
  This one change covers *every* way a trap can fire (blind walk-onto, a
  failed disarm attempt below) since they all route through this same
  function, so Levitation didn't need to be checked at each call site
  separately.
- **New Disarm Trap command**, bound to **`T`** rather than the real game's
  `d` -- `d` is already WASD-right movement in this engine (`MOVE_KEYS`), so
  the literal keybind couldn't be reused; picked for the "disarm Trap"
  mnemonic instead. `Game.attempt_disarm()` (`main.py`) targets whatever's
  directly in `Player.facing` (the same "ahead of you" adjacent-tile
  targeting a bolt spell already uses -- no new aim/targeting UI needed) and
  only ever resolves against an **already-detected** trap (`detect_traps_turns
  > 0`): an undetected trap in front of the player has to look *identical* to
  no trap at all (same generic "There's nothing to disarm there." message
  either way, and no turn consumed), or the command itself would leak
  "something's there" information the fog/detection system exists to hide.
  A detected-and-targeted attempt always consumes a turn (enemies act), win
  or lose, mirroring every other deliberate player action.
- **`engine/combat.py`'s new `resolve_disarm(player, trap_def, log)`**
  resolves the attempt itself: chance is `trap_def["disarm_chance"]` (new
  per-trap-type field in `data/traps.json` -- 0.65/0.5/0.4 for dart/pit/gas,
  easier traps are easier to disarm) plus a small `0.02 * player.level` bonus,
  capped at 0.95 so a trap is never a guaranteed disarm. Success marks the
  trap permanently inert (`sprung_trap_ids`, the same "solved forever" state
  a walk-onto spring already leaves) and grants a new `trap_def["disarm_xp"]`
  (4/8/12 by type -- the nastier the trap, the more XP for neutralizing it)
  via the existing `grant_xp`. Failure calls `resolve_trap` itself --
  springing the trap exactly like blundering onto it blind, including
  Levitation's damage immunity, so "cast both spells together to disarm with
  minimal danger" falls out of composing two already-correct mechanisms
  rather than needing a third special case.
- **Incidental bugfix found while screenshotting this session's work**:
  Levitation becoming the Spellbook panel's 13th entry pushed the panel's
  *actual* total content height (title + 13 wrapped descriptions + hint)
  past the window's own height for the first time -- `_draw_spellbook_panel`
  had never had a height ceiling (its own docstring, since session 15,
  explicitly assumed "the spell list is small and only grows by one entry
  per future session" and would therefore never need one). The panel's top
  and bottom both rendered clipped off-window. Fixed by capping `panel_h` at
  `WINDOW_H - 40` and adding a scroll-to-cursor viewport (a `panel.set_clip`
  region plus a `scroll` offset recomputed each frame from the cursor's row
  position -- no persisted scroll state needed since Up/Down only ever moves
  the cursor one row at a time) -- rows fully outside the visible window are
  skipped for both drawing and click-hitboxing. This is a general fix, not
  Levitation-specific: it'll keep the panel usable as the spell ladder keeps
  growing session over session, the exact growth this method's own comment
  had bet against. The Bookshop panel (single-line rows, no wrapped
  descriptions) was checked and still fits comfortably at 13 entries -- not
  touched, since it isn't broken yet.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 35 checks: the spell def resolves with the right
  unlock level/book cost/effect; both new `traps.json` fields exist on all
  three trap types; `resolve_trap` deals zero damage and logs the
  drift-over message while `levitation_turns > 0`, and deals damage normally
  once it's back to 0; `resolve_disarm` forced (via a monkeypatched
  `random.random`) to succeed returns `True` and grants XP, forced to fail
  returns `False` and damages the player; `attempt_disarm` against an
  *undetected* trap consumes no turn, leaves it unsprung, and shows the
  generic message; against a *detected* trap it consumes exactly one turn,
  marks it sprung, deals no damage and grants XP on a forced success;
  re-attempting an already-sprung trap is a no-op; a real `handle_move`
  walk-onto while levitating takes no damage and still marks the trap sprung
  (informational/visible from then on); casting Levitation sets the
  countdown and spends the right mana; a save/reload round trip preserves
  `levitation_turns` exactly; the Spellbook panel renders without exception
  at every one of its 13 cursor positions (the scroll-fix regression guard);
  a full `main()` boot through the real title menu (Enter and `QUIT` both
  posted on real short timers from a background thread, not pre-queued --
  the session 7/8-established gotcha) exits cleanly. **Also visually
  inspected** via rendered screenshots: the HUD's new "Levitating (N)" status
  text (cyan, alongside the existing Poisoned/Drained row) reads cleanly
  next to a disarm-success message in the log box; the Spellbook panel with
  the cursor on Levitation (the last entry) shows its full description with
  no clipping top or bottom, and with the cursor back on Spark (the first
  entry) the top of the list is equally clean -- both confirm the scroll fix
  actually works at both ends of the list, not just in the middle. Real
  `save.db` confirmed untouched (mtime unchanged, checked before and after
  the full `main()` boot); all runs used a scratch DB path via a
  monkeypatched `main.SAVE_PATH`.

### Session 30 — free field-Rest command (Castle of the Winds' turn-costing HP/mana recovery)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's own rest mechanic: pressing Rest lets the
character recover HP and mana gradually, turn by turn, for free -- distinct
from (and the far more commonly used counterpart to) any gold-based
full-heal service, and blocked/interrupted by nearby danger rather than
usable anywhere. Wayfarer already had a *paid* instant-full-heal via the
Healer (`rest_at_healer`, session 15) but nothing free -- without gold on
hand, or below spell level 2 for Minor Heal, a damaged player's only option
was to keep fighting hurt or trek back to town. This session adds the other
half: a genuinely CotW-flavored, engine-only mechanic (no new art, no new
save columns -- it only ever moves existing `hp`/`mana` toward existing
ceilings) that was a clear gap once actually looked for.

- **New `Game.field_rest()` (`main.py`), bound to `R`** (unclaimed --
  confirmed no existing keybind used it; distinct from `T`'s Disarm Trap and
  every panel key). Blocked outright with a message if any living enemy is
  in the current room (`self.enemies` is already exactly that set -- session
  6's NPC-bump precedent and every enemy-tracking call site already keep it
  filtered to alive-and-present) or if the player is already at full HP and
  mana (`effective_max_mana()`, session 24's drain-aware ceiling). Otherwise
  loops calling the existing `_advance_turn()` (so buffs/poison/detection
  timers and `turn_count` all tick down exactly as they would for any other
  action -- resting spends real game time, including toward Depths
  repopulation, same trade-off CotW's own rest has) and adds
  `REST_HEAL_PER_TURN`/`REST_MANA_PER_TURN` (2 HP / 1 mana per turn, new
  constants near `RESPAWN_THRESHOLD`) each tick, stopping the moment both are
  full. **`REST_MAX_TURNS` (200) is a safety cap**, not a gameplay limit --
  it exists purely so a pathological state (poison damage outpacing the
  fixed heal-per-turn) can't spin the loop forever; ordinary poison still
  wears off and heals fine within the cap, and if poison actually kills the
  player mid-rest, `field_rest()` routes through the exact same
  `_handle_death()` path `handle_move`/`attempt_disarm` already use, no new
  death handling needed. Since the room can't gain an enemy mid-rest (no
  timer-based spawns, single room, checked once up front), `_take_turn`'s
  `_run_enemy_turns()` tail call is a guaranteed no-op here -- kept anyway
  for the same "every non-room-changing action ends the same way" consistency
  every other handler already follows, not a wasted special case.
- **Zero interaction with `resolve_disarm`/traps**: resting doesn't move the
  player, so a trap underfoot (already sprung, since you can't stand on an
  undetected one without having walked there) is simply inert during rest,
  same as it is for any other stationary moment.
- Verified headless (SDL dummy driver, scratch DB), 14 checks: resting from
  partial HP/mana with no enemies present restores both and advances
  `turn_count`; resting at full HP/mana is a free no-op (no turn spent,
  distinct message); resting with a living enemy in `self.enemies` is
  blocked (no turn spent, no HP change, distinct message); a pathological
  heavy-poison state terminates within `REST_MAX_TURNS` rather than hanging;
  a lethal-poison-during-rest death correctly revives at full HP with poison
  cleared, matching every other death path; a full `main()` boot through the
  real title menu to a real-timer `QUIT` (session 8's established
  pre-queued-events-get-dropped-by-the-menu gotcha, avoided the same way
  every session since has) exits cleanly. **Also visually inspected** via
  rendered screenshots: a damaged/mana-drained player's HP/MP bars read full
  after resting with the exact "You rest for N turns and recover some
  strength." log line, and a second screenshot with an enemy placed nearby
  shows the HP bar unchanged and the "You can't rest with enemies nearby."
  block message instead. Real `save.db` confirmed untouched (mtime
  unchanged, checked before and after); all runs used a scratch DB path.

### Session 31 — Cold Bolt spell + Young White Dragon (CotW's cold-elemental mirror of Firebolt/the Red Dragon)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual elemental roster (StrategyWiki's
Magic and Monsters pages, RPGClassics' Lifthransir's Bane spell/monster
references): the real game has **Cold Bolt** and **Cold Ball** spells and a
full **White Dragon** family ("Immune to Cold, Breathes Ice"), the direct
cold-elemental counterpart to session 22's Firebolt/Young Red Dragon —
Wikibooks also notes CotW's own relative elemental power ordering (fire >
lightning > cold), which set this spell's mana/damage numbers below
Firebolt's. Session 22's elemental system (`damage_type` string dispatch,
`enemy.resist_elements` dict) was confirmed generic before writing anything
(researched via a read-only pass first) — this session is a pure
data/content addition, zero engine-code changes to `combat.py`/`entity.py`/
`equipment.py`.

- **`data/spells.json` gained `cold_bolt`** — unlock_level 14 (the ladder's
  next tier past session 29's Levitation at 13), `book_cost: 295` (continues
  the `15 + unlock_level*20` formula unchanged), `mana_cost: 5` and
  `value: 9` (both below Firebolt's 7/12, reflecting CotW's own fire > cold
  power ordering), `effect: "bolt"`, `damage_type: "cold"`. **Zero changes
  needed to `cast_selected_spell`'s `"bolt"` branch** — it already dispatches
  generically on whatever `damage_type` string a spell def carries (verified
  by reading the branch before writing the entry), so Cold Bolt rides the
  exact same code path Firebolt and Spark already use.
- **`data/enemies.json` gained `young_white_dragon`** — hp 40/attack
  8/defense 4/xp_reward 40/gold_reward [15,25] (comparable to the Young Red
  Dragon's own stats, no power skew intended between the two mirror
  enemies), `damage_type: "cold"`, `resist_elements: {"cold": 1.0}` (immune
  to its own breath, matching the Red Dragon's fire-immunity and CotW's own
  "immune to cold" White Dragon). **`scale_stats_for_level` needed no
  changes** — confirmed by reading it first, it shallow-copies the whole
  stats dict so `damage_type`/`resist_elements` pass through untouched while
  hp/attack/defense/xp/gold scale with dungeon level exactly like every
  other enemy.
- **`engine/procgen.py`'s `ENEMY_WEIGHTS_BY_TIER`**: `young_white_dragon`
  joins tier 2 (deepest) alongside `young_red_dragon` at the identical
  weight (1, against the tier's now-9-strong combined weight) — same
  deep-tier-only, deliberately-rare mini-boss treatment, no reason to make
  one dragon rarer than the other. Absent from tiers 0/1, same as the red
  dragon.
- **Sprite: a real lesson in why `make_tint_variant` isn't universal.**
  First attempt copied session 24's Wraith-from-Skeleton trick verbatim —
  `make_tint_variant("enemy_white_dragon", "enemy_dragon", (215, 235, 255))`
  — and it *passed* an initial pixel-equality assertion (rounding made the
  tinted pixel technically different from the source). But `BLEND_RGB_MULT`
  can only ever **darken** a channel (`dest = dest * src / 255`), never
  brighten one past its own value — the Wraith tint worked because the
  Skeleton's base sprite is already pale/white (high R/G/B to darken toward
  blue-violet), while the Red Dragon triangle's green/blue channels (60, 30)
  are too low for any multiplicative wash to lift them into a pale icy
  color. Rendering and visually comparing the two sprites side by side
  (not just diffing raw bytes) caught this immediately — the "tinted"
  triangle still read as solid red. Fixed by using a second
  `make_placeholder("enemy_white_dragon", (225, 240, 255), shape="triangle")`
  call instead — same triangle silhouette as the Red Dragon (both are
  dragons; shape parity is fine, CotW's own dragon sprites differ only by
  color too), genuinely pale blue-white fill this time. This is now the
  documented reason `make_tint_variant` is a good fit only when the *source*
  sprite is already light enough to darken into the target hue, not a
  general-purpose recolor tool.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 36 checks: the spell def resolves with the right
  unlock level, the exact `15 + unlock_level*20` book cost, and a
  mana/value below Firebolt's; the enemy def resolves with the right
  `damage_type`/immunity; a live `resolve_spell_hit` confirms the White
  Dragon takes zero damage and gets the "immune to it" message from Cold
  Bolt but takes normal damage from Firebolt (no fire resist entry), and a
  same-shape regression check confirms the Red Dragon is still immune to
  fire but now takes normal damage from Cold Bolt (no cold resist entry —
  the two mirror enemies don't accidentally cross-resist); `young_white_dragon`
  is present in tier 2 only (absent from tiers 0/1) at the same weight as
  `young_red_dragon`; `scale_stats_for_level` scales hp/attack upward at
  level 5 while leaving `damage_type`/`resist_elements` untouched; sampling
  400 seeds at a fixed deep coordinate confirms it actually spawns
  procedurally; a full game boot produces zero `[ASSET WARNING]` output and
  the new sprite resolves at 16x16; casting Cold Bolt in a live `Game`
  instance spends exactly its mana cost and damages a real target through
  the actual `cast_selected_spell` path (not just the lower-level combat
  function); the Spellbook panel renders at all 14 cursor positions
  (session 29's scroll-viewport fix holding up again) and the Bookshop's
  14-row catalog renders with Cold Bolt priced correctly at the bottom; a
  full `main()` boot through the real title menu (Enter and `QUIT` both
  posted on real short timers from a background thread, not pre-queued —
  the session 7/8-established gotcha) exits cleanly. **Also visually
  inspected** via rendered screenshots: the Spellbook panel with the cursor
  parked on Cold Bolt (the new 14th/last entry) shows its full description
  with no clipping top or bottom; the Bookshop's 14-row catalog shows
  "Cold Bolt (295g)" as the correctly-priced last row; a direct 4x-scaled
  side-by-side render of the Red Dragon and White Dragon sprites confirms
  they're genuinely color-distinct (this is what caught the broken
  first-attempt tint above — the pre-fix comparison screenshot still showed
  two visually-identical red triangles despite the code technically running
  without error); and a live in-room screenshot with a real
  `young_white_dragon` `Enemy` instance placed near the player/town NPCs
  confirms the pale triangle renders correctly at actual game scale, not
  just in an isolated sprite-sheet crop. Real `save.db` confirmed untouched
  (mtime unchanged, checked before and after the full `main()` boot); all
  runs used a scratch DB path via a monkeypatched `main.SAVE_PATH`.

### Session 32 — Lightning Bolt spell + Young Blue Dragon (the third leg of the fire/cold/lightning elemental set)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual Lightning Bolt/Ball spells and its
elemental dragon roster (StrategyWiki's Magic page, which spells out the
game's own effectiveness ordering as fire > lightning > cold, and confirms
Blue Dragons specifically "breathe lightning"). Sessions 22 and 31 already
built fire (Firebolt/Young Red Dragon) and cold (Cold Bolt/Young White
Dragon) as the first two legs of this set and left a documented gap:
"'lightning' and 'acid' are still just names nothing uses yet." This
session closes the lightning half of that gap the same way the first two
were closed — confirmed the `damage_type`/`resist_elements` dispatch in
`combat.py` is fully generic (re-read `resolve_spell_hit` and
`scale_stats_for_level` before writing anything) and shipped a pure
data/content addition, zero engine-code changes.

- **`data/spells.json` gained `lightning_bolt`** — unlock_level 15 (next
  tier past session 31's Cold Bolt at 14), `book_cost: 315` (continues the
  `15 + unlock_level*20` formula unchanged), `mana_cost: 6` and `value: 11`
  — deliberately placed between Firebolt's 7/12 and Cold Bolt's 5/9 so the
  mana-cost/damage ordering matches CotW's own fire > lightning > cold
  power ranking rather than being a new high or low outlier. **Zero changes
  needed to `cast_selected_spell`'s `"bolt"` branch** — same generic
  `damage_type`-string dispatch Firebolt/Cold Bolt already ride.
- **`data/enemies.json` gained `young_blue_dragon`** — hp 42/attack
  8/defense 3/xp_reward 40/gold_reward [15,25] (in line with the other two
  mirror dragons, no power skew intended between the three), `damage_type:
  "lightning"`, `resist_elements: {"lightning": 1.0}` (immune to its own
  breath, matching the Red/White Dragons' fire/cold immunity).
  `scale_stats_for_level` needed no changes (re-confirmed by reading it: it
  shallow-copies the stats dict, so `damage_type`/`resist_elements` pass
  through untouched).
- **`engine/procgen.py`'s `ENEMY_WEIGHTS_BY_TIER`**: `young_blue_dragon`
  joins tier 2 (deepest) at the same weight (1) as the other two dragons —
  same rare mini-boss treatment, absent from tiers 0/1.
- **Sprite**: `AssetManager.make_placeholder("enemy_blue_dragon", (40, 100,
  230), shape="triangle")` — same triangle silhouette as the other two
  dragons, a saturated electric blue chosen to read as distinct from the
  White Dragon's pale near-white fill and from the Wraith's muted
  blue-violet tint (a different, humanoid silhouette anyway, so the color
  proximity there was never a real collision risk). No `make_tint_variant`
  attempted this time — session 31 already established that trick only
  works when the source sprite is light enough to darken into the target
  hue, and neither existing dragon is a good source for a saturated blue.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 21 checks: the spell def resolves with the right
  unlock level, exact `15 + unlock_level*20` book cost, and mana/value
  strictly between Cold Bolt's and Firebolt's; the enemy def resolves with
  the right `damage_type`/immunity; a live `resolve_spell_hit` confirms the
  Blue Dragon takes zero damage and gets the "immune to it" message from
  Lightning Bolt but takes normal damage from Firebolt, and a same-shape
  regression check confirms the Red and White Dragons both still take
  normal damage from Lightning Bolt (no accidental cross-resist between any
  of the three); `young_blue_dragon` is present in tier 2 only at the same
  weight as its two siblings, and sampling 400 rolls at tier 2 confirms it
  actually spawns; `scale_stats_for_level` scales hp upward at level 5 while
  leaving `damage_type`/`resist_elements` untouched; a full game boot
  produces zero `[ASSET WARNING]` output and the new sprite resolves at
  16x16; casting Lightning Bolt in a live `Game` instance (spell added to
  `known_spells`, cursor moved to it) spends exactly 6 mana and deals
  exactly 11 damage to a real target through the actual
  `cast_selected_spell` path; the Bookshop's now-14-row not-yet-known
  catalog (a fresh level-1 character knows only Spark) shows Lightning Bolt
  correctly priced at 315g as the last row; the Spellbook panel renders
  cleanly with the cursor on Lightning Bolt and the post-cast mana readout
  correct; a full `main()` boot through the real title menu (Enter and
  `QUIT` posted from a background thread on real short timers, not
  pre-queued — the session 7/8 gotcha) exits cleanly. **Also visually
  inspected** via rendered screenshots: the Spellbook panel with Lightning
  Bolt selected (44/50 mana after the live test cast, no clipping); the
  Bookshop's 14-row catalog with "Lightning Bolt (315g)" as the correctly
  priced last row; and a live in-room screenshot with a real
  `young_blue_dragon` `Enemy` placed next to the player in the town square,
  confirming the electric-blue triangle is visually distinct from the
  player, the two NPCs, and (by construction) the other two dragon colors.
  Real `save.db` confirmed byte-identical (md5 checked before and after the
  full `main()` boot, not just mtime); all runs used a scratch DB path via
  a monkeypatched `main.SAVE_PATH`.

## Known Limitations / Future Work

Roughly in likely-priority order — not committed to, just tracked:

- **Several sprite choices are poor and need to be re-done (flagged
  session 25)** — the user explicitly called this out while scoping
  session 25 to UI/layout only ("I am not worried about the sprites
  themselves, although several are poor choices") -- no specific sprites
  were named, and session 25 touched zero art, so this is a placeholder
  for a future session to actually audit the current roster (session 9's
  curation, plus every placeholder/tint-variant added since) against what
  reads poorly in practice and swap or redraw the worst offenders.
- ~~**Enemy AI doesn't check locked doors/gates (session 10)**~~ — fixed
  session 15: `Game._run_enemy_turns` now folds `_blocked_positions()` into
  the occupied set passed to `Enemy.take_turn`.
- **Depths vault density (0.3/0.5/0.7 by tier) is a first-pass guess**,
  same caveat as session 9's enemy/item density bump — not played and
  tuned, just a reasonable-looking starting point.
- **Only one vault per generated room, at most** — `generate_room()` stops
  after the first successful placement. Deeper tiers could plausibly
  support two without solvability risk (each vault is independently
  optional), just not built.
- **Armory and the hub are never fogged** (no `regions` field) and Crypt's
  fog is hand-authored rather than procedural — a deliberate scope line
  (see session 10), not a limitation of the mechanism itself, which works
  identically wherever `regions` is defined.
- ~~**Equipment is shop-only (session 8)**~~ — closed out session 16:
  equipment is now also found as Depths floor loot, per-instance
  (enchant/curse/identified), with a Merchant-run Identify/Remove Curse
  service. Shop purchases are still always a plain `+0` instance by
  design (see session 16) — that half of session 8's original note is
  intentional, not a residual gap.
- ~~**Vault chests still only ever hold plain consumables (session 16)**~~
  — closed out session 17: a vault chest can now roll a per-instance
  equipment drop (enchant/curse/identified, same as floor loot) alongside
  its existing plain-consumable loot.
- ~~**Only 5 gear slots (weapon/shield/helmet/armor/boots) — no rings or
  amulet slots (session 8/16)**~~ — closed out session 18: `ring1`/
  `ring2`/`amulet` slots added, same per-instance enchant/curse machinery
  as the original five. Tier-based basic/fine/masterwork gear (every slot,
  including the three new ones) carries a continuous `-3..+3` enchant when
  found in the Depths (session 16, closer to CotW's prefix/suffix affixes
  than session 8's fixed tiers alone), but there's still no *named* affix
  system (no "of the Bear," no multiple stacked properties on one item) —
  enchant is a single number, not a set of independent modifiers. Also
  still true: CotW's amulets raise *elemental or undead-drain* resistance;
  ~~this engine has no elemental damage types~~ closed out session 22 for
  the elemental half (amulets now grant real `resist_elemental`, see
  below) — ~~undead-drain resistance specifically is still unbuilt~~ closed
  out session 24: the same Amulet of Resistance line also grants
  `resist_undead`, mitigating a new Wraith enemy's permanent mana-drain
  touch (see below), rather than a second amulet item line.
- ~~**No elemental damage types or resistance system** (session 21)~~ —
  closed out session 22: `damage_type` (fire/cold/lightning-capable)
  bypasses defense and is mitigated by a new `resist_elemental` stat
  sourced from a reworked Amulet line; enemies can independently
  resist/be immune to a matching elemental spell via `resist_elements`.
  Session 31 added the second element: `"cold"` via Cold Bolt and the
  Young White Dragon, mirroring session 22's fire pairing. Session 32 added
  the third: `"lightning"` via Lightning Bolt and the Young Blue Dragon,
  CotW's own third elemental-dragon breath type. `"acid"` is still just a
  name nothing uses yet — easy to add a matching enemy/spell the same way
  the other three were, no new mechanism needed. Also still true:
  `resist_elemental` (the player-side Amulet stat)
  is one flat percentage generic across every element, not per-element the
  way CotW's own separate Resist Fire/Resist Cold/Resist Lightning items
  are (confirmed via session 31's research) — splitting it would need real
  engine work in `equipment.py`, not attempted since nothing has needed it
  yet (a player mitigates cold exactly as well as fire today).
- ~~**Still no cure-poison item/spell** (session 22)~~ — closed out session
  23: a new Neutralize Poison spell purges poison outright. This session's
  own research confirmed CotW's actual mechanism is the spell, not a
  potion (session 22's own note guessed at an item-based `effect:
  "cure_poison"` branch in `Inventory.use_item` — the real game's
  Neutralize Poison is spell-only, so that's what shipped; no consumable
  changed).
- **A player bump-attack against a surviving adjacent enemy lands two hits,
  not one** (pre-existing, found and documented but deliberately not fixed
  in session 22 — see that session's notes for how it was confirmed and
  why it was left alone): `resolve_bump_attack`'s counter-hit and the same
  enemy's own `_run_enemy_turns` attack action both fire off one player
  input. Fixing it would rebalance every enemy's effective damage output,
  not just this session's new elemental one, so it's flagged rather than
  silently changed.
- **No Remove Curse or Identify for consumables** — session 16's
  identify/curse system is equipment-only; consumables (potions,
  whetstones, etc.) stay session-5's plain tiered `item_type` strings,
  never hidden or cursed. CotW applies the same unidentified/cursed
  treatment to potions and scrolls too; out of scope here since
  consumables have no per-instance tracking to hang that state on.
- **The dungeon automap only covers the Depths** — the journal's map panel
  shows "not in the Depths" for the three hand-authored town rooms
  (Entry Hall/Armory/Crypt), since those are small and fixed rather than
  an explorable unbounded plane. A simple static town map would be cheap
  to add if wanted.
- **Quest ladder is finite (5 tiers)** — session 6. No open-ended/
  procedural quest generation once it's exhausted.
- **Procedural rooms are still plain open rectangles** — no interior
  obstacles/varied shapes yet (kept simple originally to guarantee
  reachability without a maze-solver). Difficulty now scales with depth
  *and* dungeon level (sessions 3-4), but room geometry itself doesn't.
- **Content breadth is better but still thin**: eight enemy types (session
  21 added the Viper, session 22 the Young Red Dragon, session 24 the
  Wraith, session 31 the Young White Dragon, session 32 the Young Blue
  Dragon), four item families
  (potion/whetstone/shield/gold, each with minor/normal/greater tiers,
  sessions 5 and 8) plus eight equipment slots (session 8/18). Easy to
  extend further — just add entries to the relevant `data/*.json` and a
  sprite registration in `Game._load_assets`.
- **The Wraith (session 24) phases through walls but not closed locked
  doors/gates** — `Room.is_walkable`'s new `ignore_walls` param only skips
  the WALL-tile check; a still-closed lock/gate is enforced by the caller's
  `occupied_positions` set instead (session 15's fix), a separate mechanism
  `phases_walls` doesn't touch. CotW's own wraiths pass through doors too;
  extending phasing there would need occupied_positions itself to know
  about a per-enemy phasing flag, not attempted this session. Also still
  true: only one Wraith variant exists (CotW has Pale/Dark/Abyss tiers plus
  the separate stat-draining Wight) and the drain only ever targets mana —
  this engine has no STR/DEX/INT/CON attributes to drain the way Wights do.
- **No drop mechanics for consumables** — items are consumed permanently
  on use, no way to drop one back onto the floor once picked up.
- **Spells only have one casting path** (session 12) — the Spellbook panel
  (`C`), which always costs a turn on a successful cast. There's no field
  quick-cast hotkey the way items have 1-8, a deliberate scope cut (see
  session 12) to avoid a second key namespace, not a technical limitation.
- ~~**No purchasable/found spellbooks (session 12)**~~ — closed out session
  19: a new Scholar NPC in the town hub sells every not-yet-known spell for
  gold (`book_cost` in `data/spells.json`), learned immediately regardless
  of level. Still true: spellbooks are bought, never found as dungeon loot
  the way CotW's sometimes are — not attempted, would ride the same
  per-instance-drop machinery equipment already uses (session 16/17) if
  ever wanted.
- **15 spells**: one per unlock tier (levels 1-5), three divination spells at
  6/7/12 (session 15: Detect Monsters/Detect Treasure; session 28: Detect
  Traps), Neutralize Poison at 8 (session 23), Word of Recall at 9 (session
  26, CotW's "misc"-category town/dungeon shortcut), Identify/Remove
  Curse at 10/11 (session 27, mana-cost alternatives to the Merchant's paid
  versions of the same two actions), Levitation at 13 (session 29,
  trap-damage immunity paired with Detect Traps' own duration), Cold
  Bolt at 14 (session 31, the second attack-spell element alongside
  session 12's original Spark and session 22's Firebolt), and Lightning
  Bolt at 15 (session 32, the third element). Easy to
  extend further: add an entry to `data/spells.json` and, if it's a new
  `effect` type, a branch in `Game.cast_selected_spell` (session 12) --
  the Spellbook panel now scrolls to fit whatever the ladder grows to
  (session 29), so a 15th entry won't reintroduce the clipping this
  session found and fixed.
~~**No trap disarm mechanic or Levitation spell (session 28)**~~ — closed
  out session 29: a new Disarm Trap command (`T`, since `d` is already
  WASD-right movement) targets a detected trap directly ahead of the player
  for a chance at permanently neutralizing it for XP, and a new Levitation
  spell makes every trap harmless (damage and poison DoT alike) whether
  walked onto blind or sprung by a failed disarm. Still true: disarm only
  targets the single tile directly ahead (`Player.facing`), not a
  free-standing target picker the way the real game's "press d, select the
  trap" implies for a trap that isn't adjacent — not attempted, since this
  engine's grid-bump input model has no cursor-based targeting to reuse
  (the same reasoning bolt spells already accepted for enemy targeting).
- **No hover highlighting** of the tile/row under the cursor (session 13,
  still true) — deliberate, to avoid a MOUSEMOTION-driven redraw eating
  into the idle-cheap budget. Click-and-hold movement *was* added in
  session 14 (both keyboard-hold and mouse-hold-and-drag); what's still
  out of scope is click-to-pathfind to a distant tile — held movement
  steps one tile at a time toward the current cursor/held key, same
  4-directional-only model the keyboard has always had, not a route
  around obstacles.
- **No automated test suite** — verification so far has been scripted
  headless smoke tests (SDL dummy driver) run ad hoc, not a checked-in
  pytest suite.
- **Explicitly out of scope per the original design brief**: networking,
  controller support, scrolling maps.
- **Depths room population density (session 9) is a first-pass guess**,
  not a tuned balance number — `max_enemies`/item-roll counts in
  `procgen.py` were scaled up roughly in proportion to the new room's
  larger interior area, but nobody has played it yet to confirm it feels
  right rather than just "more."
- **The `overworld` sheet is sliced but unused** — Wayfarer has no
  outdoor/town-exterior map today; it's available in
  `assets/sprites/overworld/` if that's ever wanted as a future hub area.
- **Old 64px `dungeon_tileset_1`/`dungeon_tileset_2` sprite folders are
  now dead weight** — nothing in the code references them post-session-9,
  but they weren't deleted (pre-existing assets, not this session's to
  remove unasked).

## How to Run / Test

```bash
# from the repo root
venv/bin/python wayfarer/main.py

# headless smoke test (no display needed)
cd wayfarer
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ../venv/bin/python3 main.py
```

pygame-ce is already installed in the repo's `venv/`. `save.db` and
`__pycache__/` are gitignored inside `wayfarer/`.
