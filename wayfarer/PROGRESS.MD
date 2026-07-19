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

## Known Limitations / Future Work

Roughly in likely-priority order — not committed to, just tracked:

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
- **Vault chests still only ever hold plain consumables (session 16)** —
  the per-instance equipment path floor loot uses doesn't extend to
  `generate_room()`'s chest-loot roll yet (`CHEST_ITEM_WEIGHTS_BY_TIER`
  deliberately excludes the `"equipment"` family — see session 16). A
  guarded chest holding a guaranteed piece of (possibly enchanted) gear
  would be a natural next step; the chest data shape (a single
  `item_type` key) would need to grow an equipment-instance variant
  first.
- **Only 5 gear slots** (weapon/shield/helmet/armor/boots) — no rings or
  amulet slots. Tier-based basic/fine/masterwork gear now also carries a
  continuous `-3..+3` enchant when found in the Depths (session 16, closer
  to CotW's prefix/suffix affixes than session 8's fixed tiers alone), but
  there's still no *named* affix system (no "of the Bear," no multiple
  stacked properties on one item) — enchant is a single number, not a
  set of independent modifiers.
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
- **Content breadth is better but still thin**: three enemy types, four
  item families (potion/whetstone/shield/gold, each with minor/normal/
  greater tiers, sessions 5 and 8) plus five equipment slots (session 8).
  Easy to extend further — just add entries to the relevant `data/*.json`
  and a sprite registration in `Game._load_assets`.
- **No drop mechanics for consumables** — items are consumed permanently
  on use, no way to drop one back onto the floor once picked up.
- **Spells only have one casting path** (session 12) — the Spellbook panel
  (`C`), which always costs a turn on a successful cast. There's no field
  quick-cast hotkey the way items have 1-8, a deliberate scope cut (see
  session 12) to avoid a second key namespace, not a technical limitation.
- **No purchasable/found spellbooks** — every spell is learned automatically
  by reaching its `unlock_level` (session 12); CotW's other half of the
  system (buy a spellbook to learn one out of level order) isn't built.
- **7 spells**, one per unlock tier (levels 1-5) plus two divination spells
  at 6/7 (session 15: Detect Monsters/Detect Treasure) — CotW's more
  freeform "misc" category still isn't represented. Easy to extend further:
  add an entry to `data/spells.json` and, if it's a new `effect` type, a
  branch in `Game.cast_selected_spell` (session 12).
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
