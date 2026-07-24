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

### Session 33 — Young Green Dragon (poison gas breath), completing CotW's actual four-color dragon set

User-driven request: "look up the game Castle of the Winds and continue
development." Sessions 22/31/32 built three of what the prior session's
own Known Limitations note assumed was a fire/cold/lightning/**acid**
elemental quartet ("`'lightning' and 'acid' are still just names nothing
uses yet`"). This session researched that assumption directly before
building anything and found it was wrong: Wikibooks' Castle of the Winds
monster reference states the game's actual four dragon colors and breaths
are "Red (breathe fire), Blue (breathe lightning), White (breathe cold),
Green (breathe poison gas)" — there is no acid-breathing dragon in CotW.
A separate AI-summarized web search had suggested acid as lightning's
"opposing element," but that claim wasn't traceable to a primary CotW
source and contradicts the Wikibooks bestiary, so it was discarded in
favor of the sourced material. The real next dragon to complete the set is
**Green, breathing poison gas** — and this engine already has a fully
generic poison mechanism (session 21's Viper `poison_chance`/
`poison_damage`/`poison_duration`), so this shipped as a second pure-data
addition, not a new elemental `damage_type` the way fire/cold/lightning
each needed.

- **`data/enemies.json` gained `young_green_dragon`** — hp 44/attack
  7/defense 3/xp_reward 40/gold_reward [15,25], in line with its three
  mirror dragons (no power skew intended between any of the four). No
  `damage_type` override (stays the "physical" default — its claws/bite,
  not its breath) and no `resist_elements` (poison is never inflicted
  *onto* an enemy anywhere in this engine, so there's nothing for it to
  resist). Its breath weapon is instead `poison_chance: 0.6`,
  `poison_damage: 4`, `poison_duration: 8` — reusing `_maybe_poison` in
  `engine/combat.py` exactly as the Viper does, just rolled into a
  much more dangerous bite/breath than the Viper's 0.5/2/6 to match a
  mini-boss dragon rather than an early nuisance snake. **Zero engine
  changes needed** — confirmed by re-reading `combat._maybe_poison` and
  `procgen.scale_stats_for_level` first, same discipline sessions 22/31/32
  applied before touching data.
- **`engine/procgen.py`'s `ENEMY_WEIGHTS_BY_TIER`**: `young_green_dragon`
  joins tier 2 (deepest) at the same weight (1) as its three siblings —
  identical rare mini-boss treatment, absent from tiers 0/1.
- **Sprite**: `AssetManager.make_placeholder("enemy_green_dragon", (20,
  150, 40), shape="triangle")` — same triangle silhouette as the other
  three dragons, a saturated forest/toxin green chosen to read as
  distinct from both the Slime's muted green circle and the Viper's olive
  diamond (different shapes anyway, but a different color family too).
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 22 checks: the enemy def resolves with hp in the
  sibling dragons' range, no `damage_type`/`resist_elements` override, and
  a poison bite/breath strictly stronger than the Viper's on all three
  poison fields; `young_green_dragon` is present in tier 2 only at the
  same weight as its three siblings, and sampling 400 rolls at tier 2
  confirms it actually spawns; a live `resolve_bump_attack` loop confirms
  the dragon's bite can poison the player and, when it does, applies
  exactly *its own* `poison_damage`/`poison_duration` (not the Viper's); a
  regression check confirms the Blue Dragon is still immune to its own
  Lightning Bolt (no accidental interaction between this session's poison
  addition and the existing elemental-immunity system); a full game boot
  produces zero `[ASSET WARNING]` output, the new sprite resolves at
  16x16, and is pixel-distinct from both the Slime's and Viper's sprite
  fill colors; `scale_stats_for_level` scales hp upward and — confirmed by
  actually reading the function rather than assuming — also scales
  `poison_damage` deeper the same way it already does for the Viper
  (session 21's existing generic behavior, inherited for free), while
  `poison_chance`/`poison_duration` correctly pass through unscaled (no
  such branch exists for them); a full `main()` boot through real asset
  loading with a live `young_green_dragon` `Enemy` placed next to the
  player renders without exception. **Also visually inspected** via a
  rendered screenshot: the green triangle reads as clearly distinct from
  the player, both NPCs, and (by construction) the other dragon colors.
  Real `save.db` confirmed byte-identical (md5 checked before and after),
  all runs used a scratch DB path via a monkeypatched `main.SAVE_PATH`.

### Session 34 — Resist Fire/Cold/Lightning spells (Castle of the Winds' per-element resistance magic)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched the real game's spell roster directly (Wikibooks'
Castle of the Winds/Magic page, plus a corroborating fan spell list) rather
than assuming, same discipline session 33 applied to the dragon set. That
page groups CotW's defense spells as Shield (+armor) and **Resist Cold /
Resist Fire / Resist Lightning, each "temporarily decreasing by half the
damage the player sustains from these elemental attacks"** — a real,
sourced spell trio this engine had never built, and a direct fix for a
limitation this file has flagged since session 22: `resist_elemental` (the
Amulet-of-Resistance stat) is "one flat percentage generic across every
element... not per-element the way CotW's own separate Resist Fire/Resist
Cold/Resist Lightning items are." Confirmed from the source that in the
real game these are temporary *spells*, not permanent equipment — so the
fix is new magic, not a rework of `equipment.py`'s existing amulet stat.

- **`data/spells.json`** gained three new entries, continuing the existing
  unlock-level ladder (16/17/18, book costs 335/355/375, mirroring session
  27-33's pacing): `resist_fire`, `resist_cold`, `resist_lightning`. Each is
  `effect: "resist_element"`, `damage_type` matching its element, `value: 50`
  (the sourced "halves damage" -- 50% mitigation) and `duration: 20`. New
  `category: "defense"` value, same field Stone Skin/Levitation already use,
  no schema change needed.
- **`engine/entity.py`**: `Player` gained three bonus/turns field pairs
  (`temp_resist_fire_bonus/turns`, `temp_resist_cold_bonus/turns`,
  `temp_resist_lightning_bonus/turns`) -- the same countdown-buff shape
  `buff_defense_bonus/turns` (Stone Skin) already established, just one pair
  per element since more than one resist spell can be active at once (e.g.
  before a mixed dragon fight). New `Player.temp_resist_bonus(damage_type)`
  helper looks up the right pair (0 for `"physical"` or an element with no
  matching spell).
- **`engine/combat.py`**'s `_enemy_damage_to_player` now adds
  `player.temp_resist_bonus(enemy.damage_type)` on top of the existing flat
  `resist_elemental` before applying `RESIST_CAP` (90) -- the two stack
  additively (a +20% amulet plus an active Resist Fire mitigates 70%, not
  just 50%), matching how a player would expect two different sources of
  the same kind of protection to combine, and confirmed the 90% ceiling
  still holds even when the stacked total would exceed it. Shared by both
  `resolve_bump_attack`'s counter-hit and `enemy_attack`'s initiated hit
  (same function both already called), so a dragon's melee bite is
  mitigated identically regardless of which path landed it.
- **`main.py`**: new `elif effect == "resist_element":` branch in
  `cast_selected_spell` (same explicit per-element `if/elif` shape
  `Player.temp_resist_bonus` already uses, not a generic `setattr` --
  matches this file's existing preference for explicit branches over
  dynamic attribute dispatch even though the data would allow the shorter
  form). `_advance_turn` ticks all three countdown pairs down and zeroes
  the bonus at 0, same pattern as `buff_defense_turns`/`levitation_turns`.
  Casting the same resist spell again refreshes rather than stacks (verified
  below) -- overwrite semantics, same as Stone Skin. Three new HUD colors
  (`COLOR_RESIST_FIRE`/`COLD`/`LIGHTNING`, picked to echo the matching
  dragon sprites' fill colors from sessions 22/31/32) and three new status-row
  entries next to the existing Poisoned/Drained/Levitating indicators,
  each only shown while its `_turns > 0`.
- **`engine/save.py`**: six new `INTEGER DEFAULT 0` columns (the three
  bonus/turns pairs), same `ALTER TABLE ... ADD COLUMN` migration pattern
  every prior session's additions used -- threaded through `load_game`'s
  positional `SELECT`/row-index unpacking and `save_game`'s `INSERT ...
  ON CONFLICT DO UPDATE`, both carefully re-indexed since these are
  positional columns (the six new ones sit between `levitation_turns` and
  the `equip_<slot>` columns, so every equipment-slot row index shifted by
  6 and was updated accordingly).
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 31 checks: all three spells load with the right
  `effect`/`damage_type` and the unlock-level ladder (now 18 entries) stays
  strictly increasing; fresh `Player` defaults are inactive and
  `temp_resist_bonus` returns 0 for every element; a fire hit is mitigated
  to exactly half once `temp_resist_fire_bonus` is set and unaffected for
  cold (no cross-element bleed); the flat `resist_elemental` and an active
  Resist Fire stack additively (20% + 50% -> 30% damage taken, not 50%);
  `RESIST_CAP` still holds when the stacked total would otherwise exceed
  90%; a real `cast_selected_spell()` call against a level-20 character
  (all three spells known) sets the right bonus/turns and deducts the right
  mana, and the buff correctly ticks down and clears after its duration
  elapses; recasting refreshes to 50 rather than stacking to 100; a
  save/reload round trip preserves all three elements' bonus/turns
  mid-buff; the bookshop panel (17 not-yet-known spells at a fresh
  character) and the spellbook panel (18 known spells for the level-20 test
  character) both render without exception or clipping -- the spellbook's
  session-29 scroll fix and the bookshop's uncapped-height layout both have
  comfortable headroom left at this count (410px needed of 714px available
  window height); the HUD renders correctly with all three resist buffs
  active simultaneously. **Also visually inspected** via a rendered
  screenshot: "Resist Fire (5)", "Resist Cold (7)", "Resist Lightning (3)"
  render left-to-right on the status row in three visually distinct
  colors, no overlap or clipping against the existing HP/MP/level rows. A
  full `main()` boot through the real title menu to a `QUIT` exits cleanly.
  Real `save.db` confirmed byte-identical (md5 checked before and after),
  all runs used a scratch DB path.

### Session 35 — Dark Wraith and Abyss Wraith (rounding out CotW's Wraith family)

User-driven request: "look up the game Castle of the Winds and continue
development." Picked directly off this file's own Known Limitations note
(session 24's Wraith entry): "only one Wraith variant exists (CotW has
Pale/Dark/Abyss tiers plus the separate stat-draining Wight)." Researched
CotW's actual undead roster before building anything (Wikibooks' *Castle of
the Winds/Monsters* page plus a corroborating search) rather than assuming —
confirmed the real game has **Wraith, Pale Wraith, Dark Wraith, and Abyss
Wraith**, all of which "steal stats, mana, and health," with Dark/Pale/Abyss
specifically noted to "drain intelligence and mana irreversibly" (Wraith and
Pale Wraith both rate 4/10 difficulty, Dark Wraith 5/10, Abyss Wraith
uncosted on the page but flagged as possibly boss-tier). The existing
`wraith` entry (session 24) already fills the difficulty-4 role Wraith/Pale
Wraith occupy, so this session added the two tiers above it — **Dark
Wraith** and **Abyss Wraith** — rather than a fourth, redundant weak-tier
entry; a distinct Pale Wraith with no mechanical difference from the
existing Wraith wasn't worth adding. The stat-draining Wight family
(Tunnel/Barrow/Castle Wight, draining STR/DEX/CON) is still out of scope —
this engine has no such attributes to drain, same limitation session 24
already flagged and still true.

- **`data/enemies.json`** gained `dark_wraith` (hp 22/atk 3/def 2,
  `drain_chance` 0.4, `drain_amount` 5) and `abyss_wraith` (hp 32/atk 5/def
  3, `drain_chance` 0.5, `drain_amount` 7) — both `phases_walls: true`, same
  as the base Wraith, and both use the exact same `drain_chance`/
  `drain_amount` fields `combat._maybe_drain` (session 24) already reads, so
  **zero changes to `engine/combat.py` or `engine/entity.py`** were needed;
  the drain mechanism was already generic across any enemy def with those
  keys, this just added two more.
- **`engine/procgen.py`**: Dark Wraith joins `ENEMY_WEIGHTS_BY_TIER`'s
  mid tier at weight 1 (rarer than the base Wraith's weight 2, matching its
  one-step-up difficulty rating) and the deep tier at weight 1 alongside it;
  Abyss Wraith is deep-tier only, weight 1, grouped with the mini-boss
  dragons (session 22/31/32/33) rather than the regular roster — the
  Wikibooks page's note that wraiths might belong in a "Bosses" category was
  the basis for that call. `scale_stats_for_level`'s existing
  `drain_amount` scaling branch (session 24) needed no changes — it already
  applies to any enemy def carrying that key, verified directly against
  both new types.
- **Sprites**: no incorporeal/ghost art exists in the character sheet (same
  gap session 24 hit for the base Wraith), so both reuse the exact
  `make_tint_variant`-over-`enemy_skeleton` trick from session 24, just with
  progressively darker tints — Dark Wraith a deep violet
  (`(80, 60, 130)`, strength 0.9), Abyss Wraith a near-black void indigo
  (`(35, 20, 55)`, strength 0.95) — so the three-tier family reads as a
  visual escalation (pale blue-violet → deep violet → near-black) rather
  than three unrelated colors on the same silhouette. `BLEND_RGB_MULT` can
  only darken (session 31 already hit and worked around this limit for the
  White Dragon), which is exactly what a "deeper/darker" progression needs,
  so no repeat of that workaround was necessary here.
- Verified headless (SDL dummy driver, scratch DB, 20 checks): both new
  defs load with strictly increasing hp/attack/drain_amount across
  Wraith → Dark Wraith → Abyss Wraith; Dark Wraith appears in the mid tier
  but not the shallow tier, Abyss Wraith appears in the deep tier only;
  `scale_stats_for_level` scales both new types' `drain_amount` upward at
  level 5; sampling 60 deep-tier generated rooms confirms both actually
  appear (21 Dark Wraith, 19 Abyss Wraith, 47 base Wraith in the sample);
  `generate_room` determinism is unaffected; a full asset load produces
  zero `[ASSET WARNING]`s and both new sprites resolve at 16x16; a
  brightness comparison of the three tint variants confirms the intended
  darkening progression holds pixel-for-pixel, not just by eye; a live
  `Enemy("dark_wraith", ...)` instance drains a test `Player`'s mana via the
  existing, unmodified `combat._maybe_drain` path. **Also visually
  inspected** via a rendered screenshot comparing all three Wraith tiers
  plus the base Skeleton side by side against the actual dungeon floor
  tile (not just a black background) — confirmed all three stay visually
  distinct from each other and readable against real floor art, including
  the near-black Abyss Wraith. A full `main()` boot through the real title
  menu to a `QUIT` exits cleanly via `sys.exit()`. Real `save.db` was
  read (md5'd) before this session's changes and confirmed the later
  difference in its hash/mtime came from the user's own play session in
  between, not from any script here — every verification script in this
  session set `main.SAVE_PATH` to a scratch path before touching a
  `SaveManager`/`Game`.

### Session 36 — Heal Medium/Major Wounds: completing CotW's three-tier healing spell ladder

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual healing spells directly (Wikibooks'
*Castle of the Winds/Magic* page) rather than assuming, same discipline
sessions 33-35 applied. That page states the healing category is **Heal
Minor Wounds, Heal Medium Wounds, Heal Major Wounds**, respectively
restoring "20%, 40%, and 60% of the user's max health or 8/16/24 hp,
whichever is higher" — a real, sourced three-tier ladder this engine only
had the bottom rung of (`minor_heal`, added session 12, was a flat 12hp with
no percent component and no medium/major siblings).

- **`data/spells.json`**: `minor_heal` renamed to its exact CotW name "Heal
  Minor Wounds" and retrofitted with a new `"percent": 0.2` field (value
  dropped from its old made-up 12 to the sourced flat floor, 8) rather than
  left as a flat number now known to be wrong. Two new entries continue the
  existing unlock-level ladder at 19/20 (book costs 395/415, confirmed to
  keep following the exact `15 + unlock_level*20` formula every prior
  session's entries have used without exception since it was first noticed
  in session 32): `heal_medium` ("Heal Medium Wounds", percent 0.4, value
  16, mana 7) and `heal_major` ("Heal Major Wounds", percent 0.6, value 24,
  mana 9).
- **`main.py`'s `cast_selected_spell`**: the `effect == "heal"` branch now
  computes `max(value, round(max_hp * percent))` instead of just `value` —
  the sourced "whichever is higher" rule, applied generically so all three
  tiers (and any future heal spell with a `percent` field) share one code
  path. A spell with no `percent` key falls back to the old flat-value
  behavior (none currently exist, but nothing requires every heal spell to
  set one). Turned out to land cleanly on this engine's own leveling curve
  without further tuning: `grant_xp` adds a flat 10 max_hp per level, so
  Heal Minor Wounds' 20%-vs-8-flat crossover falls almost exactly at its own
  level-2 unlock point (max_hp 40 at level 2, 20% = 8) — the percent and
  flat floor agree at the moment the spell is learned and the percent
  gradually overtakes it every level after, rather than either amount being
  irrelevant at some point in the level range.
- **No other engine changes needed** — `_known_spell_list()`, the
  Spellbook/Bookshop panels, and the Scholar NPC's catalog are all already
  generic over `data/spells.json`'s contents (confirmed by re-reading them
  first, same discipline sessions 22 onward have applied before touching
  data), so the two new spells and the renamed existing one just appeared
  correctly with zero UI code touched.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 20 checks: 20 total spells with a strictly increasing
  unlock-level ladder and the book-cost formula holding for all of them;
  `minor_heal`/`heal_medium`/`heal_major` each resolve with the right
  percent/value/unlock_level; a live `cast_selected_spell()` call against a
  level-20 test character (max_hp 220) confirms all three tiers heal exactly
  the percent-based amount (44/88/132) since it exceeds each spell's flat
  floor at that max_hp; a separate low-max_hp (30) character confirms
  `minor_heal`'s flat floor (8) wins when the percent (6) would be lower;
  healing never overheals past `max_hp`; a real cast deducts exactly the
  right mana cost; an insufficient-mana attempt is a no-op (no heal, no
  mana spent); the Scholar's bookshop catalog lists both new spells,
  correctly priced at 395g/415g as the last two rows for a fresh
  not-yet-learned character; both the 20-entry Spellbook panel (cursor on
  the new last row, "Heal Major Wounds") and the 19-not-yet-known-spell
  Bookshop panel render without exception or clipping; a full `main()` boot
  through the real title menu to a `QUIT` exits cleanly. **Also visually
  inspected** via rendered screenshots: the Spellbook scrolled to its new
  bottom entry (Heal Major Wounds selected, description fully visible, no
  clipping against the existing 18-entry layout's headroom) and the
  Bookshop's 19-row not-yet-known catalog with "Heal Medium Wounds (395g)"
  and "Heal Major Wounds (415g)" as the correctly priced final two rows.
  Real `save.db` confirmed byte-identical (md5 checked before and after);
  all runs used a scratch DB path via a monkeypatched `main.SAVE_PATH`.

### Session 37 — Barrow/Tunnel/Castle Wight: Castle of the Winds' second undead-drain family

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual monster roster directly (StrategyWiki's
*Castle of the Winds/Monsters* page, Wikibooks' bestiary and battle-mechanics
pages) rather than assuming, same discipline sessions 22 onward have applied.
Found the Wight family named but explicitly flagged unbuilt in session 35's
own notes ("this engine has no STR/DEX/INT/CON attributes to drain the way
CotW's separate stat-draining Wight family does") — confirmed via research
that Wights are real, distinct from Wraiths (three tiers, Barrow/Tunnel/
Castle, weakest to strongest) and drain STR/DEX/CON permanently rather than
Wraiths' intelligence, cured only at a Temple or with a potion in the source
game.

- **Adaptation, not a Wraith reskin.** This engine has no separate STR/DEX/
  CON/INT attributes (session 35 already noted this gap and left it open).
  Rather than build a full attribute system just for one monster family, one
  representative existing stat stands in for the drain — `attack` — the same
  scoping call session 24 already made for the Wraith (mana standing in for
  intelligence). This is a genuinely separate resource from the Wraith's
  mana drain, not the same mechanic reskinned: a character can be drained of
  mana *and* attack independently, cured independently, by two different
  undead families.
- **`engine/entity.py`**: `Enemy.drain_stat` (new, default `"mana"`) picks
  which player stat a `drain_chance`/`drain_amount` touch lowers — every
  existing drain-capable enemy (the Wraith family) is unaffected since it
  defaults to the pre-existing mana behavior. `Player.attack_drain` (new,
  mirrors `mana_drain`'s persistence) is a running total of how much has
  been drained, restored by the Healer for gold. **Different reversal
  mechanism than mana_drain's, deliberately**: mana_drain works by lowering
  a *ceiling* (`effective_max_mana()`) that every mana-spending/refilling
  path already caps against, because mana has a natural current/max split to
  layer a ceiling onto. Attack doesn't — it's a single number every combat
  formula reads directly — so attack_drain instead directly mutates
  `player.attack` at drain time and reverses it by adding the total back,
  the exact "mutate the base stat, keep a running total to reverse later"
  pattern equipment's own bonuses already use (`equip()`/`unequip()` in
  `engine/equipment.py`, session 8). Floored so a drain can never take
  `attack` below 1 (no permanently-disarmed player).
- **`engine/combat.py`**: `_maybe_drain` (session 24) now branches on
  `enemy.drain_stat` — the existing mana path is untouched (verified
  directly: a Wraith still only ever drains mana, never attack), the new
  attack path applies the same `resist_undead` mitigation and floor, with
  its own log line ("saps your strength" vs. "drains your mana away").
  `procgen.scale_stats_for_level`'s existing `drain_amount` depth-scaling
  needed **zero changes** — it was already generic over which stat the
  amount eventually lowers.
- **Three new enemies** (`data/enemies.json`): Barrow Wight (hp 24/atk 5,
  weakest), Tunnel Wight (hp 34/atk 7), Castle Wight (hp 46/atk 10,
  strongest) — names and relative ordering sourced directly from the
  research above, not invented. None phase through walls (`phases_walls`
  unset) — confirmed the source game's phasing undead are Wraiths/ghosts
  specifically, not Wights, so this family is a real ground-bound melee
  threat rather than a second phasing enemy. Placed in
  `procgen.ENEMY_WEIGHTS_BY_TIER`: Barrow Wight joins the Wraith at mid-tier,
  Tunnel Wight becomes more common at the deepest tier, Castle Wight is
  deep-tier-only at the same mini-boss-rare weight as Abyss Wraith and the
  four dragon lines.
- **Sprites**: no ghoul/wight-shaped art in the character sheet (same gap
  session 24 hit for the Wraith), so all three reuse
  `make_tint_variant("enemy_skeleton", ...)` like the Wraith family did —
  but with an earthy brown/grey/stone palette instead of the Wraiths'
  blue-violet one, so the two undead-drain families read as visually
  distinct at a glance despite sharing a base silhouette. Escalating
  darkness by tier, same "deeper → darker" progression sessions 24/35 used.
- **UI**: HUD status row gained "Weakened (-N ATK)" (new `COLOR_WEAKEN`,
  earthy to match the sprite tint) alongside the existing "Drained (-N MP)",
  both no-countdown (neither wears off on its own). The Healer panel's row
  list (`_healer_rows`/`activate_healer_row`) gained a third conditional row,
  "Restore Sapped Strength", appearing only once `attack_drain > 0`, same
  per-point gold pricing (`DRAIN_CURE_COST_PER_POINT`) as Restore Drained
  Mana.
- **`engine/save.py`**: `attack_drain INTEGER DEFAULT 0` column, same
  `ALTER TABLE ADD COLUMN` migration pattern as every prior session's
  additions, threaded through `load_game`/`save_game` alongside the existing
  `mana_drain`/`resist_undead` pair.
- Verified headless (SDL dummy driver, scratch DB, monkeypatched
  `main.SAVE_PATH`), 53 checks: all three Wights defined with `drain_stat:
  "attack"` and no `phases_walls`; strictly increasing hp/attack/xp across
  the tier; every enemy type referenced anywhere in
  `ENEMY_WEIGHTS_BY_TIER` actually exists in `enemies.json` (all three
  tiers checked); Castle Wight absent from tiers 0/1 and present in tier 2;
  Barrow Wight absent from tier 0; a fresh player has `attack_drain == 0`
  and unmodified `attack`; a forced Barrow Wight touch reduces `attack` by
  the exact drain amount and records it in `attack_drain`, with the
  expected log line; repeated touches never drain `attack` below 1;
  `resist_undead` mitigates the attack-drain amount by the same percentage
  formula as mana drain; a Wraith touch (regression) still only affects
  `mana_drain`, never `attack_drain`; `scale_stats_for_level` scales a
  Wight's `drain_amount` with dungeon level and preserves `drain_stat`
  across the copy; a save→load round trip preserves both the reduced
  `attack` value and the `attack_drain` counter exactly; a full `main()`
  boot through the real title menu to a `QUIT` posted on a real short timer
  (session 8's own workaround for a pre-queued QUIT getting dropped by
  `run_menu`'s event loop) exits cleanly. **Also visually inspected** via
  rendered screenshots: all three new sprites next to the full Wraith
  family (confirmed visually distinct earthy-vs-violet families, correct
  per-tier darkness escalation); the HUD showing "Weakened (-4 ATK)"
  alongside "Poisoned" with no overlap/clipping; the Healer panel with all
  three rows visible at once (Rest, Restore Drained Mana, Restore Sapped
  Strength) at the correct dynamic panel height. Confirmed **zero**
  `[ASSET WARNING]` output during a full asset load. Real `save.db`
  confirmed byte-identical (md5 checked before and after); all runs used a
  scratch DB path.

### Session 38 — Light and Clairvoyance: instant map-reveal magic (Castle of the Winds' Divination/Miscellaneous spells)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW's actual spell roster directly (Wikibooks'
*Castle of the Winds/Magic* page) rather than assuming, same discipline
sessions 22 onward have applied. Confirmed the real game's full spell list
against `data/spells.json`'s existing 20 entries and found two sourced,
unbuilt spells whose real-game effect ("reveal an area instantly") maps
cleanly onto machinery this engine already has and had never pointed magic
at: **Light** ("reveals a room... including any monsters or objects that
may be within it") and **Clairvoyance** ("fills in the player's map of a
10x10 area anywhere on the floor, including any traps and secret doors").
Both are adaptations, not literal ports — Light's real-game "reveal a room"
maps onto session 10/11's per-region fog of war (a mechanic CotW itself
doesn't have, since Wayfarer's rooms are much bigger than the original
game's), and Clairvoyance's "10x10 tile area" maps onto session 8's
room-grid automap (Wayfarer's rooms *are* CotW's map cells, just far
larger) rather than a literal tile count.

- **`data/spells.json`** gained `light` (effect `reveal_room`, unlock level
  21, mana 5, no duration/value — an instant one-shot) and `clairvoyance`
  (effect `reveal_map`, unlock level 22, mana 10, new `radius: 2` field).
  Both continue the existing unlock-level ladder and the `15 +
  unlock_level*20` book-cost formula every prior session's additions have
  followed without exception (435g/455g). 22 spells total now (was 20 as of
  session 36).
- **`main.py`'s `cast_selected_spell`** gained two new effect branches:
  - `reveal_room` unions every region id in `self.room.regions` into
    `self.revealed_regions` at once (vs. the existing
    `_reveal_region_at_player`, which only ever adds the single region the
    player is physically standing in). Persists through the exact same
    `_current_room_flags()`/`region_seen` path every other region reveal
    already uses — no new persistence code. A room with no `regions` (every
    hand-authored room except the Crypt) is a clean no-op with its own
    message rather than a crash on an empty set.
  - `reveal_map` marks every `(gx, gy)` within `radius` (2, so a 5x5 block
    of rooms) of the player's current Depths room as discovered, reusing
    `self.discovered`/`save.mark_discovered` exactly as `load_room` already
    does on a physical first visit — so the journal's automap and its
    `procgen.room_doors()`-drawn connections (a pure function of
    coordinates, session 8) render identically for a room revealed by magic
    as one actually walked into. Written through immediately, matching
    session 8's "discovered_rooms is never batched" discipline. Only
    meaningful in the Depths (parses `current_room_id`'s `proc:` prefix);
    a clean no-op message in town, where there's no room-grid automap at
    all (see Known Limitations).
- Both effects are idempotent and reported as such: recasting either over
  ground already fully revealed/mapped gives a distinct "nothing left to
  reveal here" / "already mapped everything nearby" message rather than
  silently no-opping or re-showing the success text.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 22 checks: 22 total spells with the unlock-level ladder
  still strictly increasing and the book-cost formula holding for both new
  entries; a live `cast_selected_spell()` call in a real generated Depths
  room reveals every region in that room's `regions` list in one cast
  (confirmed against the full region-id set, not just "some got added");
  recasting gives the no-more-secrets message; casting Light in the hub
  (`regions == []`) gives the nothing-to-reveal message without touching
  `revealed_regions`; casting Clairvoyance in town gives the
  no-dungeon-floor message; casting it in the Depths marks the exact
  expected 5x5 `(gx, gy)` block discovered both in `self.discovered` and
  (immediately, no save/quit needed) in the DB via
  `save.get_discovered_rooms`; recasting over the same area gives the
  already-mapped message; mana is deducted by exactly each spell's cost; a
  save→reload round trip preserves both the revealed regions and the
  discovered rooms; the Spellbook panel renders correctly at the new full
  22-entry count with the cursor on the new last row (Clairvoyance), no
  clipping. **Also visually inspected** via rendered screenshots: the
  Spellbook scrolled to its new bottom entries; a Depths room's fog fully
  black before Light and fully lit (revealing enemies, loot, and a chest
  previously hidden in unexplored regions) immediately after; the journal's
  Dungeon Map panel empty before Clairvoyance and showing a filled-in 5x5
  block of connected rooms centered on the player (yellow marker) 
  immediately after, with no travel in between. A full `main()` boot
  through the real title menu to a `QUIT` posted on a real 1-second timer
  exits cleanly via `sys.exit()`. Real `save.db` confirmed byte-identical
  (md5 checked before and after); all runs used a scratch DB path via a
  monkeypatched `main.SAVE_PATH`.

### Session 39 — spellbooks as dungeon loot (Castle of the Winds' other spellbook source)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW directly (Wikibooks' *Items* page and
supporting summaries) rather than assuming, same discipline recent sessions
have applied: confirmed the source game's spellbooks "each contain a spell
that the player can learn" and are found or purchased, not shop-only — a
gap `engine/spells.py`'s own docstring and PROGRESS.MD's Known Limitations
had flagged since session 19 ("Still true: spellbooks are bought, never
found as dungeon loot... would ride the same per-instance-drop machinery
equipment already uses if ever wanted"). That's exactly what this session
built.

- **`engine/procgen.py`** gained `SPELL_IDS_BY_BAND`, a new parallel table
  (same "procgen trusts a key string exists, main.py resolves it against
  the real defs" split as `EQUIPMENT_BASE_TYPES_BY_SLOT`) splitting all 22
  `data/spells.json` ids into three unlock-level-ordered bands (7/8/7). A
  new `"spellbook"` family joins `ITEM_WEIGHTS_BY_TIER` at tier 1/2 only
  (never tier 0, mirroring `"equipment"`'s own tier-0 exclusion) at a flat
  weight of 1 rather than scaling to 2 like equipment does at tier 2 — a
  permanent spell unlock is a bigger power spike than a gear enchant range,
  so it stays rarer-growing by design. Floor loot rolls a `spellbook_drops`
  entry (`spell_id` chosen from the depth-banded table via the same
  magnitude roll gear tiers already use); vault chests gained a parallel
  `chest["spellbook"]` branch alongside the existing `chest["equipment"]`
  one. Procgen is a pure function of `(seed, level, gx, gy, epoch)` with no
  player state, so — unlike CotW's own text implying a duplicate is never
  offered — a roll *can* land on a spell the player already knows; that's
  handled at pickup time instead (see below), not by making generation
  player-aware.
- **`engine/entity.py`** gained `SpellbookDrop`, a new floor-entity class
  alongside `EquipmentDrop` — same reasoning (`ItemPickup`'s stackable
  `data/items.json` path doesn't fit something that needs a live
  `known_spells` check on pickup instead of an inventory slot).
- **`engine/room.py`** gained `spellbook_drop_templates` (from
  `data.get("spellbook_drops", [])`), the same structural-template-only
  split `equipment_drop_templates` already has.
- **`main.py`**:
  - `load_room` fetches `spellbook_drop_templates` from `generate_room`'s
    population (Depths) or `self.room` (cached structure) exactly like the
    equipment-drop fetch beside it, and folds `SpellbookDrop` instances into
    `self.items` — no new collision-detection code needed, since
    `Player.try_move`'s item-pickup loop is already generic over any
    `self.items` entity by position.
  - New `Game._spell_def(spell_id)` helper (also adopted by the pre-existing
    `buy_spellbook`, which had the same `next(s for s in self.spell_defs...)`
    lookup inline) backs two new branches in `handle_move`: a
    `SpellbookDrop` pickup and a `chest["spellbook"]` open. Both add the
    spell straight to `known_spells` — unknown case — or, if the roll
    duplicated an already-known spell, refund half its `book_cost` in gold
    rather than silently wasting the drop or crashing on a no-op. Both play
    the existing `"pickup"` sfx and post a distinct message for each case.
  - `_load_assets` registers a new `item_spellbook` placeholder sprite (see
    below) — one fixed sprite for every spell's book, matching how a single
    `chest_closed`/`chest_open` graphic already stands in for every chest's
    contents regardless of what's inside.
- **`engine/assets.py`**: `AssetManager.make_placeholder` gained a new
  `"book"` shape — a closed-book silhouette (rounded rect + a spine line
  offset from center) distinct from the plain-square switches use, since
  neither sprite sheet has any readable/tome art (session 9 already
  confirmed the item sheet is potions/gear/coins only). Colored violet
  (`(150, 90, 200)`), distinct from every other item tint used so far
  (mana potions are blue, gold/potions use their own family colors).
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`), 17 checks: `SPELL_IDS_BY_BAND` covers exactly the 22
  real spell ids with no duplicates; scanning `generate_room` across 200
  seeds × multiple levels/coordinates finds both floor spellbook drops and
  chest spellbook contents; a tier-0 room (level 1, depth ≤ 1) never rolls
  one across 300 seeds, matching equipment's own tier-0 exclusion; against
  the actual save's real dungeon seed, walking onto a live floor spellbook
  for an unknown spell adds it to `known_spells` immediately and removes the
  entity from the room; force-placing a second spellbook for an
  already-known spell refunds gold and posts the "already know" message
  instead of erroring; opening a live chest with a `spellbook` field teaches
  its spell and marks the chest opened; a save→reload round trip preserves
  `known_spells` gained either way; the `item_spellbook` sprite resolves to
  a real `Surface`. **Also visually inspected** via rendered screenshots: a
  floor spellbook's violet book-with-spine placeholder next to the switch
  placeholder it sits near (confirming the two read as distinct shapes, not
  just distinct colors); the pickup message ("You study a found spellbook
  and learn Resist Fire!"); the Spellbook panel afterward showing both Spark
  and the newly learned Resist Fire with no clipping. A full `main()` boot
  through the real title menu to a `QUIT` posted on a real 1-second timer
  exits cleanly via `sys.exit()`. Real `save.db` confirmed byte-identical
  (md5 checked before and after) across every run, all of which used a
  scratch DB path via a monkeypatched `main.SAVE_PATH`.

### Session 40 — Sleep Monster spell (Castle of the Winds' single-target crowd control)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW directly (Wikibooks' *Magic* page) rather than
guessing: confirmed the real game has three monster-affecting spells this
engine had none of — Sleep Monster ("puts one target monster to sleep. Some
monsters and all bosses are immune and all will wake in about ten minutes or
when attacked"), Slow Monster (halves speed, stacks further per re-cast), and
Transmogrify Monster (randomizes the target's species). Scoped this session
to Sleep Monster alone — one coherent feature, not all three — since it
maps cleanly onto this engine's existing single-target bolt-spell aiming
with no new targeting code, while Slow's "half speed" has no clean analog in
a one-action-per-turn AI model (there's no existing notion of a monster
acting less than once per player turn to halve) and Transmogrify would need
a live re-roll-into-any-monster-type path nothing here has. Both are left as
open follow-ons below rather than attempted partially.

- **`engine/entity.py`**: `Enemy` gained `sleep_immune` (from
  `data/enemies.json`, default `False`) and `sleep_turns` (pure runtime
  combat state, defaulting to `0` and never read from `stats` — like `hp`
  itself, it isn't persisted, since Depths enemies already regenerate fresh
  from their room's epoch on every visit rather than being saved
  individually; see the Architecture Notes' respawn section). `take_turn`
  checks `sleep_turns` first: a sleeping enemy neither chases nor wanders,
  decrementing the counter once (this method is only ever called once per
  player action, the same cadence every other per-turn countdown in this
  engine already relies on) and returning a new `{"type": "asleep"}` action
  that `main.py`'s `_run_enemy_turns` silently ignores, the same way it
  already ignores `"idle"`/`"moved"`.
- **`engine/combat.py`**: both `resolve_bump_attack` and `resolve_spell_hit`
  now clear `sleep_turns` to `0` the moment a sleeping enemy takes any hit,
  matching CotW's own "wakes... when attacked." `resolve_bump_attack`
  specifically returns immediately after waking it, *skipping that
  exchange's retaliation* — the enemy was asleep when the swing landed, so
  it doesn't get the usual "if it survives, it hits back" counter-hit this
  turn, giving Sleep Monster real tactical payoff beyond just skipped enemy
  turns. `resolve_spell_hit` has no retaliation to skip (bolts are already
  one-sided) but still wakes the target and notes it in the log.
- **`data/enemies.json`**: `sleep_immune: true` added to exactly the seven
  enemy types `engine/procgen.py`'s own `ENEMY_WEIGHTS_BY_TIER` comments
  already single out as weight-1 "mini-boss" rarities — the four young
  dragons, Dark Wraith, Abyss Wraith, and Castle Wight. This is a deliberate
  narrow reading of "some monsters and all bosses are immune": only the
  "all bosses" half is a concrete, sourced fact, so only the enemies this
  codebase already treats as boss-tier got the flag: no guess was made at
  which ordinary monsters (if any) CotW's "some monsters" refers to, so
  every regular enemy (skeleton, slime, cultist, Viper, base Wraith, the two
  weaker Wights) can be put to sleep.
- **`data/spells.json`**: new `sleep_monster` entry, unlock level 23
  (continuing the ladder past session 38's Clairvoyance at 22), `book_cost`
  475 (continuing the existing +20-per-level pattern), `mana_cost` 8,
  `effect: "sleep"`, `range: 5` (matching Spark's bolt range), `duration: 20`
  turns (matching the Resist spells' duration — CotW's own "about ten
  minutes" has no exact turn-count equivalent in a discrete-step engine, so
  this borrows an existing precedent rather than inventing a new number).
- **`main.py`**: new `"sleep"` branch in `cast_selected_spell`, reusing
  `_bolt_target` verbatim for targeting (same facing/range/line-of-sight
  aim every bolt spell already uses) but setting `target.sleep_turns`
  instead of dealing damage; a `sleep_immune` target gets a distinct "is
  unaffected" message instead. Like every other spell branch, mana is spent
  and the enemy turn still runs regardless of whether the cast found/
  affected a target, matching the existing "a bolt spell that finds no
  target still costs a turn" precedent. Also added a small translucent
  blue tint drawn over any enemy with `sleep_turns > 0` (`draw`, new
  `COLOR_SLEEP`) so a sleeping enemy is visually obvious, not just inferable
  from the log line.
- A text "Zzz" tag was tried first for the visual and rejected after an
  actual screenshot caught the problem: at this engine's native 16px tile
  size (session 9), a label tall enough to read spills upward into the tile
  above — exactly where an adjacent player sprite sits in the common "walk
  up and melee the sleeping target" case, since Sleep Monster's whole
  wake-on-attack mechanic assumes the player closes to melee range. Switched
  to a same-tile translucent tint, which has no such spillover; re-verified
  with a second screenshot.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`): casting Sleep Monster at a facing skeleton sets
  `sleep_turns` to the spell's duration; `take_turn` on a sleeping enemy
  returns `"asleep"` and decrements the counter without moving/attacking; a
  melee hit on a sleeping enemy wakes it, logs "wakes with a start," and
  skips its retaliation (player HP unchanged); a ranged spell hit on a
  sleeping enemy also wakes it (no retaliation to skip, but the log/state
  change both confirmed); casting at a `sleep_immune` Young Red Dragon
  leaves `sleep_turns` at `0` and posts the "unaffected" message, and the
  dragon's own subsequent turn still runs normally (mana/turn cost isn't
  waived by immunity); casting with no enemy in the facing direction posts
  the existing "finds no target" message; both spellbook-open and
  inventory-open full `draw()` passes complete with no exception. **Also
  visually inspected** via rendered screenshots: the initial "Zzz" text
  attempt's overlap bug (caught only by looking at the image, not the
  assertions — the same "screenshot catches what asserts miss" pattern
  sessions 11/13/15/16/39 already documented) and the corrected same-tile
  tint reading cleanly around a skeleton standing directly below the player
  with no clipping into neighboring tiles. A full `main()` boot through the
  real title menu to a `QUIT` posted on a real 1-second timer exits cleanly.
  **Process note, logged for future sessions**: one earlier ad hoc `main()`
  smoke-test invocation this session forgot to monkeypatch `SAVE_PATH` before
  running and hit the real `save.db` directly -- caught immediately via the
  routine before/after md5 check, which came back different. Inspected the
  file's actual rows (`player`/`inventory`/`known_spells` tables) before
  concluding anything: every value was internally consistent with a real,
  in-progress level-2 character (turn_count 186, gold 33, known spells
  matching a level-2 unlock set, sensible inventory), not the reset-to-
  defaults state a `new_game` path would have produced -- so nothing was
  lost, most likely just a benign SQLite page rewrite from opening/closing a
  connection against it (the `has_save()` probe and/or one autosave of
  identical values), not a semantic change. Re-ran the same boot check with
  `SAVE_PATH` correctly redirected and confirmed byte-identical before/after
  on the *real* file this second time. Flagged transparently rather than
  silently moving on, per this project's verification discipline.

### Session 41 — Fireball/Cold Ball/Ball Lightning (Castle of the Winds' area-effect elemental attacks)

User-driven request: "look up the game Castle of the Winds and continue
development... look at the ball spells." Researched CotW directly (the raw
Wikibooks *Magic* source, not just the rendered page, to get the exact
mechanic text): the game has three "ball" spells -- **Cold Ball**, **Ball
Lightning**, **Fireball** -- each the AoE sibling of an existing bolt spell
this engine already has (Cold Bolt/Lightning Bolt/Firebolt, sessions 22/31/
32). Source text: "Affect a 3x3 area. Do damage equivalent to the
corresponding bolt in the center square, and half as much damage in the
eight adjacent squares... Balls are so large that they always hit... may
hurt the player, but nevertheless be worthwhile." Also confirmed "there is
no ball spell corresponding to Magic Arrow" -- so no non-elemental ball was
built, matching this engine's own Spark having no AoE counterpart either.

- **`data/spells.json`**: three new entries, `effect: "ball"`, continuing
  the ladder past session 40's Sleep Monster at 23 -- Fireball (24, 495
  gold, 13 mana), Cold Ball (25, 515 gold, 9 mana), Ball Lightning (26, 535
  gold, 11 mana). Introduced in the same fire/cold/lightning order their
  bolt counterparts originally shipped in (sessions 22/31/32), not the
  wiki's own listed order (cold/lightning/fire) -- an arbitrary source
  ordering, so this engine's own established progression order was kept
  instead. Each carries the same `value`/`range`/`damage_type` as its bolt
  sibling (e.g. Fireball's `value: 12` matches Firebolt's), since the
  source material defines the ball's damage *as* "equivalent to the
  corresponding bolt," not as its own independent number. Mana cost is
  roughly double the sibling bolt's, reflecting the up-to-5x total damage
  a fully-surrounded cast can deal (source gives no real numbers to copy --
  CotW's own mana costs "depend on the caster's level," not fixed values).
- **`main.py`**: new `_ball_impact_point(spell)`, sitting next to
  `_bolt_target` -- walks the same facing/range/wall-blocked line, but
  where a bolt fizzles entirely and returns `None` if its line is empty,
  a ball always detonates *somewhere* (source: "so large that they always
  hit"), stopping at the first enemy, the last walkable tile before a
  wall/closed door, or the max-range tile if the line is clear the whole
  way. Only returns `None` if the very first step out of the player's tile
  is already blocked (nowhere at all to go off). New `"ball"` branch in
  `cast_selected_spell`: finds the impact point, then iterates every live
  enemy and applies Chebyshev distance from it (`max(|dx|, |dy|) <= 1` for
  "3x3 area") -- the enemy standing exactly on the impact tile takes the
  full `value`, everything else caught in the ring takes
  `max(1, round(value / 2))`, reusing `resolve_spell_hit` per enemy so
  resist/immunity/sleep-wake/defeat-XP-gold all stay in lockstep with the
  existing bolt spells rather than duplicating that logic. Every ball's
  `damage_type` is elemental (no ball exists for a physical spell, per the
  source note above), so unlike the "bolt" branch there's no physical/
  defense-mitigated fork -- always bypasses defense, matching the sibling
  bolts' own elemental branch.
- **Player splash damage** ("may hurt the player, but nevertheless be
  worthwhile"): this engine has no free tile-cursor targeting the way CotW
  does (aim is always the player's facing direction, reused verbatim from
  every prior bolt/sleep spell) -- so a ball can only ever detonate ahead
  of the player, never behind or beside them. The 3x3 ring still covers the
  player's own tile whenever the impact point is directly adjacent (the
  common case: casting at a bumping-range enemy one tile away), which is
  exactly when the real game's own risk applies. New
  `resolve_ball_splash_to_player` in `engine/combat.py` mirrors
  `_enemy_damage_to_player`'s resist formula (flat `resist_elemental` plus
  any active Resist Fire/Cold/Lightning buff, session 34) but keyed off the
  spell's own `damage_type`/half-value instead of an attacking enemy's
  stats, so a player standing in their own blast takes the same ring
  damage an adjacent enemy would, mitigated the same way an incoming
  elemental attack already is.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`, confirmed byte-identical on the real `save.db` before
  and after): all three ball spells load with `effect: "ball"`; casting
  Fireball at a 3x3 cluster (one enemy on the impact tile, one one tile
  away, one five tiles away) dealt exactly the full value to the center
  enemy, half (rounded) to the ring enemy, and left the far enemy
  untouched; mana was spent exactly once regardless of how many enemies
  were caught; casting with no enemies anywhere still detonated (no
  "finds no target" fizzle the way a bolt gives), spent mana, and advanced
  the turn; casting at a fire-immune enemy correctly dealt it zero damage
  via the existing `resolve_spell_hit` immunity branch while the player's
  own splash damage from the same cast still landed, confirming immunity
  is per-enemy and doesn't leak into the player's own resist math; casting
  at an enemy one tile away (the common bump-range case) confirmed the
  player takes ring splash damage, and casting with no adjacent target
  confirmed they don't. A full `main()` boot through the real title menu to
  a posted `QUIT` exits cleanly. **Also visually inspected** via rendered
  screenshots of the Spellbook panel: the cursor on the newly-added
  Ball Lightning entry (bottom of a now-26-spell ladder) scrolls correctly
  into view with its full description and the "Up/Down select..." hint
  line both intact below it -- no clipping, continuing to confirm session
  29's scroll-to-cursor logic holds at every ladder length it's been
  re-checked against since.

### Session 42 — Slow Monster (Castle of the Winds' speed-reducing curse)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW directly (Wikibooks' *Magic* page, fetched
both the rendered page and a raw export to cross-check the exact wording)
looking specifically at the two monster-affecting spells session 40 sourced
but deliberately left unbuilt, Slow Monster and Transmogrify Monster.
Source text for Slow Monster: "Slows the target monster's movement and
attacks to half. Bosses are immune. A second cast reduces the speed to
1/3, a third to 1/4, etc. Some monsters, like devils, will never move at
less than half the player's speed." Picked Slow over Transmogrify -- same
reasoning session 40 already gave for skipping both: Transmogrify still
needs a live re-roll-into-any-enemy-type path (fresh stats, sprite swap,
re-applying HP%) nothing in `engine/entity.py` does, while Slow only needed
a way to make an enemy act less than once per player turn, a smaller and
more contained addition. Confirmed no "devil" enemy type exists in this
engine (`data/enemies.json`), so that clause has nothing to apply to and
was left unbuilt, same as it not mattering.

- **`data/spells.json`**: one new entry, `slow_monster` (unlock level 27,
  555 gold, 10 mana, `effect: "slow"`), continuing the ladder immediately
  past session 41's Ball Lightning at 26. No `duration` field -- unlike
  Sleep Monster's "wakes in about ten minutes," the source text for Slow
  gives no wear-off at all, only escalation on re-cast, so this is modeled
  as permanent runtime state rather than a countdown buff (see below).
- **`engine/entity.py`**: `Enemy` gained `slow_level` (0 = unaffected,
  otherwise how many times Slow has stacked on this enemy) and `slow_tick`
  (a running counter). In `take_turn`, right after the existing sleep
  check: if `slow_level > 0`, increment `slow_tick` and, unless it's a
  multiple of `slow_level + 1`, return `{"type": "slowed"}` without
  chasing/wandering/attacking -- i.e. only 1 out of every `slow_level + 1`
  calls is a real turn. Since movement and attack both come from the same
  `take_turn` call in this engine (there's no separate attack-rate field),
  skipping the whole call halves (or thirds, etc.) both at once, matching
  the source's "movement *and* attacks to half" in one mechanism rather
  than two. Boss immunity ("Bosses are immune") reuses the existing
  `sleep_immune` flag rather than a new near-duplicate one -- this engine
  has no separate boss concept, and session 40 already established
  `sleep_immune` as the mini-boss-tier (four young dragons, Dark/Abyss
  Wraith, Castle Wight) stand-in for CotW's boss immunity, so the same
  enemies that resist Sleep now also resist Slow.
- **`main.py`**: new `"slow"` branch in `cast_selected_spell`, sitting
  right after the `"sleep"` branch and reusing `_bolt_target` for the exact
  same single-enemy facing/range/line-of-sight targeting Sleep Monster and
  every bolt spell already use. A successful cast increments the target's
  `slow_level` and resets `slow_tick` to 0, so a re-cast's finer interval
  (1/3, then 1/4, ...) starts its cadence clean rather than continuing
  mid-cycle from the old one. Message reports the new fraction (e.g.
  "Skeleton is slowed to 1/2 speed.", then "...to 1/3 speed." on a second
  cast). A `sleep_immune` target gets the same "unaffected" message Sleep
  Monster's immunity branch already produces; no target in range/line gets
  the same "finds no target" message every other targeted spell uses.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`, confirmed byte-identical on the real `save.db` before
  and after): casting Slow Monster on a fresh enemy set `slow_level` to 1
  and produced the "1/2 speed" message; driving that enemy's `take_turn`
  across repeated calls showed real turns spaced exactly 2 apart (1 real
  turn per 2 calls) with every other call returning `"slowed"`; re-casting
  on the same enemy bumped `slow_level` to 2 and re-spaced real turns
  exactly 3 apart (1/3 speed), confirming the re-cast escalation and the
  tick-reset both work; casting at a `sleep_immune` enemy (Young Red
  Dragon) left `slow_level` at 0 and produced the "unaffected" message
  while the dragon's own counter-attack still landed, confirming immunity
  doesn't block its normal turn; casting with no enemies in the room
  produced the "finds no target" message and still consumed mana exactly
  once (10, matching `mana_cost`) same as every other targeted spell's
  no-target case. A full `main()` boot through the real title menu to a
  posted `QUIT` on a timer exits cleanly. **Also visually inspected** via a
  rendered screenshot of the Spellbook panel with the full 27-spell ladder
  known: the cursor on the new bottom entry, Slow Monster, scrolls
  correctly into view with its full description and the "Up/Down
  select..." hint line both intact below it -- no clipping, continuing to
  confirm session 29's scroll-to-cursor logic at yet another ladder length.

### Session 44 — Adventure Mode begins: Scorched Wastes, the first finite biome dungeon (Yoda Stories / Desktop Adventures-inspired)

User-driven request: read `wayfarer/PROGRESS.MD` and `wayfarer/wayfarer_adventure.md`
(a speculative design writeup already sitting on this branch, written but
never built), look up LucasArts' *Star Wars: Yoda Stories* and *Indiana
Jones and His Desktop Adventures*, and begin development. Researched both
directly (Wikipedia, MobyGames, Fandom wikis, TV Tropes via web search) and
confirmed the design doc's own premise: both games are the same engine
wearing two skins, structured around **item-for-item fetch/trade chains**
across procedurally-assembled regions toward a single end goal, with combat/
puzzles as texture around that spine rather than the point (matching CotW's
existing role in this codebase). This session builds exactly step 1 of the
design doc's own phased build order: one finite biome dungeon end-to-end
(room gen + one mini-boss + one fragment drop), reachable directly from
town, no unlock gating yet. The fetch/trade quest chain, biome unlock
gating, additional biomes, and the final win-state area are explicitly
*not* attempted this session -- each is its own session-sized step in the
design doc's plan, same granularity as this project's usual practice.

Also per this session's own instruction: art is intentionally left alone
(the existing `dungeon_v2` tileset, same as the Depths) -- resizing sprites
larger is scoped for a separate future pass on this branch, not mixed into
this one.

- **`engine/procgen.py`**: new `generate_biome_room(seed, biome_id)`,
  alongside the existing `generate_room()` (the Depths' unbounded (level,
  gx, gy) plane) rather than replacing anything. A biome dungeon is exactly
  **one** room, id `biome:<biome_id>:<seed>` -- finite by construction, no
  gx/gy neighbors, no stairs, no per-level difficulty scaling, no epoch/
  respawn (main.py's `load_room` only applies that machinery to `"proc:"`-
  prefixed ids, so a biome room's population generates once and is cached
  forever by `Room.load`, same as a hand-authored room). Reuses
  `generate_room`'s core-room/corridor/vault carving helpers (`_grid_cells`,
  `_carve_room_in_cell`, `_spanning_tree`, `_carve_corridor`,
  `_place_vault`, `_random_free_point`, the weighted-loot tables) wholesale,
  per the design doc's own reasoning -- only the top-level assembly differs:
  one fixed exit back to town instead of the four-directional edge-hash
  dance, `BIOME_TIER = 1` (fixed/curated difficulty, matching the design
  doc's Open Questions leaning) instead of depth/level scaling, and a
  **guaranteed** vault (never chance-gated) whose chest always holds the
  biome's artifact fragment, its mini-boss standing guard in the same
  chamber. `BIOME_DEFS["scorched_wastes"]` (desert/canyon terrain, Young Red
  Dragon mini-boss, `ember_fragment`) is the only biome built this session
  -- the design doc's other three (Frostreach/Stormfell/Fenmire) are future
  sessions, not attempted.
  - **Found and fixed a latent bug in the shared vault-carving machinery
    while building this**, not introduced by this session's new code:
    `generate_room()`'s existing vault placement carves the vault *after*
    the spanning-tree/loop corridors and only checks the vault's footprint
    against the grid cell's own bounds -- never against corridor cells
    already carved through that same space. When a corridor's straight
    L-shaped path happens to cross where the vault lands, it silently
    breaches the vault's other three walls, leaving the "locked" door
    decorative. Confirmed by instrumenting `generate_room()` directly with a
    flood-fill reachability check across a 300-seed sample at tier 2: ~40%
    of seeded Depths vaults are reachable without ever picking up the key.
    Left unfixed in `generate_room()` itself (bigger blast radius touching
    43 sessions of existing Depths content, and a bypassable Depths vault is
    low-stakes -- bonus loot, not mandatory progression) but **fixed in
    `generate_biome_room`**, where it isn't optional: the fragment behind
    the lock is the entire point of the dungeon. Fix: after carving the
    vault interior, force every tile in its 1-tile-thick outer ring to `#`
    except the connector cell, guaranteeing the door is the only entrance
    regardless of what a corridor carved there first; every attempt is then
    verified with a full reachability flood from the entry landing (every
    core room center + the exit must still be mutually reachable) before
    being accepted, undoing (via a snapshot) and trying the next host
    candidate otherwise -- protects against the fix's own inverse failure
    mode (the forced ring severing some unrelated room's only path through
    that space). If every host fails both checks (rare -- ~7% of seeds in a
    1000-seed sample), falls back to an unlocked boss chamber in the
    biggest core room rather than ever shipping an unreachable fragment.
  - `BIOME_ENTRY_LANDING`/`BIOME_EXIT_CELL` reuse the existing
    `MID_X`/`MID_Y` constants (same 40x32 room dimensions as the Depths) --
    no new size constants needed.
- **`engine/room.py`**: `Room.load` gains a third dispatch branch (alongside
  `"proc:"` and hand-authored) for `"biome:"`-prefixed ids, calling
  `generate_biome_room` and caching the result exactly like a hand-authored
  room. `KIND_FALLBACK_COLORS` gains a `"wilds"` entry (warm desert-orange)
  for the new town exit's fallback rendering.
- **`data/rooms/town_hub.json`**: one new exit, `to_scorched_wastes` at
  (16, 4), `kind: "wilds"`, `target_room: "biome:ENTRY:scorched_wastes"` --
  the same `"proc:ENTRY"` sentinel trick the Crypt's exit already uses,
  since town_hub.json can't know the per-save seed ahead of time.
  `target_x/y` point at `BIOME_ENTRY_LANDING` (20, 16) directly, since that
  landing cell's coordinates are fixed regardless of seed.
- **`data/artifacts.json`**: new file, artifact fragment definitions
  (name/sprite/biome) -- `generate_biome_room` only ever emits a bare
  `fragment_id` string (same "procgen trusts a key exists, main.py resolves
  it" split `EQUIPMENT_BASE_TYPES_BY_SLOT`/`SPELL_IDS_BY_BAND` already use).
  One entry this session: `ember_fragment`.
- **`main.py`**:
  - Loads `data/artifacts.json` into `self.artifact_defs`; new
    `self.artifact_fragments` set, loaded from save state alongside
    `known_spells` (same flat "ever claimed" shape and reasoning).
  - `"exit"` handling: resolves the new `"biome:ENTRY:<biome_id>"` sentinel
    to `f"biome:{biome_id}:{self.seed}"`, mirroring the existing
    `"proc:ENTRY"` resolution immediately above it.
  - Chest-open handling gains an `"artifact" in chest` branch (checked
    alongside the existing equipment/spellbook/plain-item branches): awards
    the fragment into `self.artifact_fragments` -- never the stackable
    Inventory or the equipment bag, same "own exactly one, ever" reasoning
    the design doc gives for treating a fragment like a key rather than a
    potion stack. Already-opened is the same silent `pass`-through every
    other chest content type gets once its id is in `opened_chest_ids`.
  - `persist()`'s `save.save_game` call now also passes
    `self.artifact_fragments`.
  - `_load_assets()`: `item_fragment` (amber diamond placeholder, no
    matching art in either sheet, same situation as the spellbook
    placeholder) and `wilds` (the existing `cave` sprite warm-tinted via
    `make_tint_variant`, same trick as gate/locked_door -- reads as a
    different destination from the Crypt's own cave icon at a glance
    without needing new art).
  - Journal panel (`_draw_journal_panel`): one new summary line, "Artifact
    Fragments: N/total -- <names>", between the Quest Log and the Dungeon
    Map section. Confirmed by rendered screenshot it fits inside the
    existing fixed 470px panel height alongside the full quest list and the
    9x9 automap grid with no clipping.
- **`engine/save.py`**: new `artifact_fragments` table (`fragment_id TEXT
  PRIMARY KEY`), same shape/persistence reasoning as `known_spells` --
  wired through `load_game`/`new_game_defaults`/`save_game` (new optional
  `artifact_fragments=()` parameter) and added to `reset()`'s wiped-table
  list.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`): walked the real `try_move`/`handle_move` dispatch path
  from town_hub through the new exit into `biome:scorched_wastes:<seed>`;
  confirmed exactly one Young Red Dragon and one artifact chest generated;
  confirmed the locked vault door blocks movement before the key is held,
  the key pickup and door-unlock both fire through the real pickup/
  locked_door dispatch, and the vault is inaccessible before that; defeated
  the mini-boss and claimed the fragment through the real chest-open
  dispatch; confirmed re-opening the same chest is a silent no-op with the
  fragment set unchanged; walked back through the biome room's own return
  exit into `town_hub`; ran `persist()` then booted a **second** fresh
  `Game` instance against the same save file and confirmed fragment
  ownership survived the round-trip. Separately stress-tested
  `generate_biome_room` directly (bypassing pygame) across 500 seeds with a
  flood-fill reachability checker: zero failures post-fix (boss/chest always
  reachable, vault interior never reachable without the key when one
  exists, nothing ever disconnected by the ring-forcing fix) -- confirmed
  the pre-fix version failed the "reachable without the key" check on ~40%
  of the same seed range before the ring-isolation fix landed. Also ran a
  regression pass confirming the pre-existing armory/crypt/Depths exits
  still work unchanged. **Also visually inspected** via rendered
  screenshots: town_hub with the new warm-tinted `wilds` exit icon visually
  distinct from the Crypt's cool-toned `cave` icon at a glance; the
  Scorched Wastes room itself rendering correctly with fog of war, the
  `dungeon_v2` tileset (unchanged, per this session's own "art stays as-is"
  scope), and the room name "Scorched Wastes" in the HUD; and the Journal
  panel showing "Artifact Fragments: 1/1 -- Ember-Charred Fragment" cleanly
  laid out alongside the existing Quest Log and Dungeon Map sections.

### Session 43 — drop consumables back onto the floor (closing the "no drop mechanics" future-work note)

User-driven request: "look up the game Castle of the Winds and continue
development." Researched CotW directly (Wikibooks' *Interface & Controls*,
StrategyWiki's *Controls* page via search snippets since the page itself
403s to a direct fetch, and a general web search) specifically for how the
real game drops an item back to the ground. Found CotW's own drop mechanic
is drag-and-drop only -- drag an inventory item onto the dungeon view (or
the "Free Hand" slot) with the mouse -- with no dedicated keyboard command
documented anywhere sourced. This engine has no drag-and-drop (session 8's
inventory is a list-cursor panel, not a mouse-driven grid), so the natural
adaptation, same "keep the mechanic, translate the input model" call
sessions 12 (spell targeting) and 29 (trap disarm) already made, is a new
panel hotkey rather than a drag gesture: X in the Inventory panel drops one
unit of the consumable under the cursor onto the player's own tile. Scoped
to consumables only, matching the Known Limitations note's own wording
("no drop mechanics for consumables") -- found/equipped gear stays bag-only,
no drop path added for an EquipmentInstance (same line
`_use_item_at_index`/`_activate_inventory_row` already draw between
consumables and gear).

- **`engine/save.py`**: new `room_drops` table (`room_id, entity_id,
  item_type, x, y`), full-replace semantics via `set_room_drops`/
  `get_room_drops`, same pattern as the existing `room_flags` table --
  needed its own table rather than riding `room_flags` because a drop has
  to remember a type and a position, not just a boolean per entity_id.
  Added to `reset()`'s wiped-table list alongside the others.
- **`main.py`**: `load_room` now also fetches `self.save.get_room_drops`
  for whichever room is being entered into `self.room_drops` (the live
  in-memory copy this session mutates) and folds a matching `ItemPickup`
  for each into `self.items`, same as the three existing template-based
  item sources. New `drop_selected_item()` (bound to `X` in the Inventory
  panel, `handle_key_down`'s `inventory_open` branch): no-ops unless the
  cursor is on a plain consumable row, otherwise removes one unit from
  `self.inventory`, mints a `f"drop:{uuid4().hex}"` id, appends a record to
  `self.room_drops` and a live `ItemPickup` to `self.items` at the
  player's current position. Picking a dropped item back up (the existing
  "pickup" branch of `handle_move`) now also filters it back out of
  `self.room_drops` -- a no-op for a template item's id, real for a
  dropped one. `self.save.set_room_drops(self.current_room_id,
  self.room_drops)` is flushed at exactly the same three call sites that
  already flush `set_room_flags` (`persist()`, the "exit" stairs/door
  branch, and Word of Recall's town/dungeon jump) so a drop survives a
  room transition and back, a save/quit, and a recall round-trip alike.
  Inventory panel hint line updated to "...U/click use/equip, X drop,
  I/Esc close".
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`, confirmed byte-identical on the real `save.db` before
  and after): dropped a stacked consumable from a fresh inventory --
  stack count decremented, `room_drops` gained the record at the player's
  exact tile, and a live `ItemPickup` appeared in `self.items`; called
  `persist()` then `load_room()` back into the same room (simulating a
  full leave-and-return) and confirmed the drop was still there, fetched
  fresh from `room_drops` rather than surviving only in memory; stepped
  off the drop's tile and back onto it and confirmed the "pickup" branch
  restored the stack count, emptied `room_drops`, and removed the
  `ItemPickup` from `self.items`; equipped a `shortsword` into Found Gear
  and confirmed pressing X with the cursor on that gear row is a total
  no-op (inventory/`room_drops` both byte-for-byte unchanged) -- gear
  truly has no drop path. **Also visually inspected** via a rendered
  screenshot of the Inventory panel with a consumable stack, an empty
  Equipped section, and a Found Gear entry all present at once: the new
  "X drop" hint fits inside the existing 500px panel width with no
  clipping (measured 374px at the panel's own font before the screenshot,
  same discipline session 13 established for this exact panel).

### Session 45 — Frostreach + the fetch/trade quest chain (step 2 of Adventure Mode's phased build order)

User-driven request, same framing as session 44: read `PROGRESS.MD` and
`wayfarer_adventure.md`, look up *Yoda Stories*/*Desktop Adventures* again,
and continue development. Re-confirmed via a fresh web search (Fandom's
Yoda Stories wiki, TV Tropes) the design doc's own premise on the specific
piece this session builds: the source games' progression is a **chain of
deals** -- trade proof of one region's conquest to an NPC for passage into
the next, repeating until every step resolves. This session builds exactly
step 2 of the design doc's suggested phased build order: a second biome
(Frostreach) plus the fetch/trade NPC and a complete two-step chain
(Scorched Wastes fragment -> unlocks Frostreach), proving the
progression-gating system the design doc flagged as "the one genuinely new
system." The remaining biomes (Stormfell/Fenmire), the final area/win
screen, and the sprite resize are still explicitly out of scope, each its
own future session per the doc's own plan.

- **`engine/procgen.py`**: `BIOME_DEFS` gains `"frostreach"` (Young White
  Dragon mini-boss, `frost_fragment`, cold-elemental hook per the design
  doc's biome table) -- `generate_biome_room` needed zero other changes,
  confirming session 44's own claim that it's fully generic per-biome.
  Also generalized `BIOME_DEFS`' hardcoded `"to_town"` landing tile (was a
  literal `(16, 6)` for every biome, i.e. right for Scorched Wastes only)
  into a per-biome `town_return` field, so Frostreach's own return trip
  lands near its own town door rather than reappearing next to the
  Scorched Wastes one.
- **`data/artifacts.json`**: new `frost_fragment` entry ("Frost-Bound
  Fragment").
- **`data/adventure_quests.json`**: new file, the design doc's own proposed
  schema (`id`/`giver_npc`/`biome`/`wants`/`gives`/`dialogue`) -- one entry
  this session, `guide_frostreach` (wants `ember_fragment`, gives
  `unlock_biome: frostreach`). `Game.current_adventure_quest()` scans this
  list front-to-back for the first id not yet in
  `completed_adventure_quests`, same "linear chain, index-shaped" MVP the
  doc scopes for a first pass -- just backed by a persisted id *set* rather
  than a bare int, per the doc's own reasoning (keeps a future branching
  chain from being blocked on this session's data shape).
- **`data/npcs.json`** / **`data/rooms/town_hub.json`**: new `guide` NPC
  type ("Frontier Guide"), placed at (16, 10); new `to_frostreach` exit at
  (26, 4) carrying a new `requires_quest: "guide_frostreach"` field.
- **Fetch/trade NPC interaction**: `npc.type == "guide"` opens a new
  `trade_open` panel (`_draw_trade_panel`) -- structurally the
  `claim_quest_reward`-shaped branch the design doc predicted, not a
  reinvented shop/healer-style panel. `Game.attempt_trade()` checks the
  current chain entry's `wants` against `self.artifact_fragments` and, if
  held, adds the quest id to `completed_adventure_quests`. **Deliberate
  departure from the source games' own mechanic, flagged rather than
  silently changed**: real Yoda Stories/Desktop Adventures consume the
  traded item permanently (it's gone, replaced by what you get back) --
  this engine's fragments stay in `self.artifact_fragments` after a trade
  instead, because wayfarer_adventure.md's own Final Area section already
  commits to "unlocked once every fragment is **held**" as the eventual win
  condition, which would be impossible to satisfy if trading consumed the
  proof. The trade here is "show proof," not "hand it over" -- same class
  of source-mechanic adaptation as session 29's trap-disarm-by-hotkey or
  session 43's drop-by-hotkey, both already accepted departures from a
  mouse-driven/inventory-consuming original.
- **Biome-unlock gating** — the design doc's "an exit that's only
  walkable/visible once its prerequisite quest is complete," built as a new
  non-committal bump type rather than folding it into
  `_blocked_positions()`: `Player.try_move` gains a `locked_exits` param
  (checked right after gates, before the walkability check, same
  non-committal "bump, don't step" shape as a locked door/gate) and a new
  `"locked_exit"` result kind. `Game._locked_exits()` computes which of the
  current room's exits carry an unsatisfied `requires_quest` field, fresh
  every move (not cached) -- deliberately kept separate from
  `_blocked_positions()` (which *does* feed enemy pathing and spell
  line-of-sight) since a gated exit tile is ordinary floor for every
  purpose except the player's own room transition; merging it into the
  enemy-facing blocked set would have wrongly stopped enemies walking
  across it and bolts/balls from passing over it.
- **`engine/save.py`**: new `completed_adventure_quests` table
  (`quest_id TEXT PRIMARY KEY`), same flat-set shape/persistence reasoning
  as `known_spells`/`artifact_fragments` -- wired through
  `load_game`/`new_game_defaults`/`save_game` (new optional
  `completed_adventure_quests=()` parameter) and added to `reset()`'s
  wiped-table list.
- Journal panel (`_draw_journal_panel`): one new line, "Frontier Guide
  wants: `<name>` -- ready to trade / not yet found," between the Artifact
  Fragments line and the Dungeon Map section -- wrapped via the same
  `_wrap_text` helper the Shop/Spellbook panels already use, after an
  actual rendered screenshot caught the unwrapped version clipping the
  word "trade" past the panel's 460px width.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`): confirmed the Frontier Guide NPC spawns in town_hub
  and the Frostreach exit is present but returns `"locked_exit"` (not
  `"exit"`) on bump before the chain quest is complete, with the expected
  "sealed by old magic" message and no room change; walked the real
  `try_move`/`handle_move` path from town through Scorched Wastes, granted
  `ember_fragment` (the actual claim path is unchanged from session 44 and
  already covered by that session's own verification), walked back to
  town, bumped the Guide to open the real trade panel, confirmed
  `current_adventure_quest()` returns `guide_frostreach`, called the real
  `attempt_trade()` and confirmed `completed_adventure_quests` gained the
  id **and** `artifact_fragments` was untouched (confirming the
  no-consumption departure above actually holds in code, not just in this
  note); confirmed `_locked_exits()` now returns empty and the player can
  walk the real dispatch path into `biome:frostreach:<seed>`, landing a
  Young White Dragon mini-boss among the room's enemies. Ran `persist()`
  then booted a **second** fresh `Game` instance against the same save file
  and confirmed `completed_adventure_quests` and `artifact_fragments` both
  survived the round-trip. Separately stress-tested `generate_biome_room`
  directly for `"frostreach"` (bypassing pygame) across 200 seeds with the
  same flood-fill reachability checker session 44 used: zero failures
  (boss/chest/locked-door-tile always reachable from the entry landing),
  confirming the shared vault-ring fix generalizes to a second biome
  without changes. Also ran a regression pass confirming armory/crypt
  entry+return still work unchanged. **Also visually inspected** via
  rendered screenshots: town_hub's two biome-exit arches (warm-orange
  Scorched Wastes vs. new icy-blue Frostreach) reading as distinct
  destinations at a glance from a zoomed crop; both trade-panel states
  (fragment not yet found vs. held, showing the "Press U or click here to
  trade" prompt only in the latter) wrapping cleanly inside the 360px
  panel; and the Journal panel's new wrapped Frontier Guide line sitting
  cleanly between the Artifact Fragments line and the Dungeon Map section
  with no clipping or overlap, still inside the existing fixed 470px panel
  height.

### Session 46 — Stormfell (step 3 of Adventure Mode's phased build order: extending to the full biome count)

User-driven request, same framing as sessions 44/45: read `PROGRESS.MD` and
`wayfarer_adventure.md`, look up *Yoda Stories*/*Desktop Adventures* again,
continue development, and (explicitly deferred by the user to a later
session) resize the art assets larger on this branch. Re-confirmed via a
fresh web search (MobyGames/TV Tropes for Yoda Stories, Wikipedia/TV Tropes/
Fandom for Desktop Adventures) the design doc's core premise once more:
both games chain fetch/trade deals across distinct regions toward one goal.
This session builds exactly step 3 of the design doc's phased order: a
third biome (Stormfell) plus the third link in the fetch/trade chain
(Frostreach fragment -> unlocks Stormfell), proving the whole
generate_biome_room/adventure-quest-chain/locked-exit system generalizes to
N biomes, not just 2, with zero changes to any of that shared machinery.
The remaining biome (Fenmire), the final area/win screen, and the sprite
resize are all still explicitly out of scope, each its own future session.

- **`engine/procgen.py`**: `BIOME_DEFS` gains `"stormfell"` (Young Blue
  Dragon mini-boss, `storm_fragment`, lightning-elemental hook, ruins/
  highlands terrain flavor per the design doc's biome table) --
  `generate_biome_room` needed zero other changes, reconfirming sessions
  44/45's own claim that it's fully generic per-biome; adding a third biome
  really was just one new dict entry.
- **`data/artifacts.json`**: new `storm_fragment` entry ("Storm-Cloven
  Fragment").
- **`data/adventure_quests.json`**: new `guide_stormfell` entry (wants
  `frost_fragment`, gives `unlock_biome: stormfell`) -- `current_adventure_
  quest()` needed zero changes, since it already scans the whole list
  front-to-back for the first incomplete id; appending a second link was
  the entire diff.
- **`data/npcs.json`**: unchanged -- the Frontier Guide is a single NPC
  serving the whole chain, not one NPC per biome, so no new NPC was needed
  for a third link (confirmed by grep: nothing in the codebase hardcodes a
  biome count or a per-biome NPC assumption).
- **`data/rooms/town_hub.json`**: new `to_stormfell` exit (kind `"storm"`,
  at (6, 4), west side of the hub, mirroring Frostreach's east-side (26, 4)
  placement with Scorched Wastes centered at (16, 4)) carrying
  `requires_quest: "guide_stormfell"`.
- **`main.py`/`engine/room.py`**: new `"storm"` town-exit marker, same
  tint-the-shared-"cave"-sprite trick as `"wilds"`/`"frost"`. First attempt
  used a blue-leaning violet (150, 120, 220) -- looked fine as a color
  swatch on paper, but a zoomed rendered screenshot showed it reading as
  near-identical to `"frost"` in practice, and a direct pixel sample of
  both tinted surfaces confirmed why: `BLEND_RGB_MULT` can only ever darken
  the source art's own existing channel ratios, and the shared "cave"
  sprite's shadow pixels are already blue-dominant, so a wash color that's
  *also* blue-leaning can't pull the multiplied result away from blue no
  matter which blue-ish hue is picked. Fixed by switching to a magenta/
  violet wash (180, 70, 200) that boosts red over green -- the *opposite*
  channel relationship from frost's blue/green-leaning wash -- at a higher
  strength (0.85 vs. the others' default 0.6, i.e. less blended toward
  white) for more saturation to carry through the multiply. Re-rendered and
  re-sampled after the change: reads as a distinct dark magenta/crimson
  arch next to frost's icy teal-blue and wilds' warm orange. Worth
  remembering for any future biome-marker tint: colors that look distinct
  as raw RGB triples can still collapse together under `BLEND_RGB_MULT`
  against a shared dark source image -- verify by rendering and sampling
  actual pixels, not just by eyeballing the tint_color tuples.
- **Bug found and fixed by the same screenshot discipline**: the Journal
  panel's "Artifact Fragments" summary line (`_draw_journal_panel`) was
  never wrapped, unlike the Frontier Guide line directly below it (which
  session 45 already wrapped after catching its own clipping). At 2
  fragments it happened to fit; a rendered screenshot after this session's
  third fragment landed showed it clipping mid-name ("...Ember-Charred
  Fragment, Frost" then cut off). Fixed by wrapping it with the same
  `_wrap_text` helper the guide line already uses, and rederiving `guide_
  top`/`map_top` from the wrapped line count instead of a hardcoded `+18`
  so the rest of the panel's layout still cascades correctly regardless of
  how many lines the fragment summary needs.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`, confirmed real `save.db` untouched before/after --
  there was in fact no real `save.db` present in the working tree this
  session, confirmed via `ls`/`md5sum` before starting): stress-tested
  `generate_biome_room("stormfell")` directly (bypassing pygame) across 200
  seeds with the same flood-fill reachability checker sessions 44/45 used
  -- zero failures (boss/chest/locked-door tile always reachable from the
  entry landing). Booted a real `Game` instance and confirmed the new
  `to_stormfell` exit starts in `_locked_exits()`'s return and bumping it
  is a no-op (`"locked_exit"`, stays in `town_hub`); drove the real chain
  end-to-end -- granted `ember_fragment`, called the real `attempt_trade()`
  twice (`guide_frostreach` then `guide_stormfell`), confirmed `current_
  adventure_quest()` returns `None` once both links are complete and
  `_locked_exits()` no longer includes the Stormfell exit; walked the real
  `try_move`/`handle_move` dispatch path from town into
  `biome:stormfell:<seed>` and confirmed a Young Blue Dragon spawns among
  the room's enemies. Ran `persist()` then booted a **second** fresh `Game`
  instance against the same scratch save file and confirmed `completed_
  adventure_quests` and `artifact_fragments` both survived the round-trip.
  Regression-checked `town_hub`'s exit set is exactly the expected five
  (`to_armory`/`to_crypt`/`to_scorched_wastes`/`to_frostreach`/
  `to_stormfell`) via a direct `Room.load("town_hub")`, unaffected by
  anything this session touched. **Also visually inspected** via rendered
  screenshots (see the tint-color note above for the door-marker fix, and
  the wrapping note above for the journal-panel fix): the three biome-exit
  arches reading as three distinct destinations at a glance in a zoomed
  crop; the Journal panel's fragment/guide/map sections all correctly
  cascading with the new wrap; and the trade panel's longer Stormfell
  dialogue (the longest of the three intro lines so far) still wrapping
  cleanly inside the existing 360px panel with no clipping.

### Session 47 — Fenmire, the Final Area, and Adventure Mode's win screen (steps 3 and 4 of the phased build order, closing out the arc)

User-driven request, same framing as sessions 44-46: read `PROGRESS.MD` and
`wayfarer_adventure.md`, look up *Yoda Stories*/*Desktop Adventures* again,
begin development, and (again explicitly deferred to a later session) resize
the art assets larger on this branch. Re-confirmed the design doc's core
premise once more via a fresh web search (Fandom/MobyGames/TV Tropes for
both games): fetch/trade chains across distinct regions toward one end goal,
with a final assembled-artifact payoff. This session finishes what sessions
44-46 started: the fourth and last biome from the doc's own table (Fenmire),
*and* the doc's step 4 (final area + win state) in the same session, since
by this point adding a biome is proven trivial (session 46's own note: "one
new dict entry") and finishing the whole arc felt like better use of a
session than another single-biome increment. The sprite resize is still the
only explicitly out-of-scope item left on this branch.

- **`engine/procgen.py`**: `BIOME_DEFS` gains two entries.
  - `"fenmire"` (swamp/jungle terrain, Young Green Dragon mini-boss reusing
    the poison mechanism per session 33, `mire_fragment`) -- zero changes
    needed to `generate_biome_room` itself, reconfirming sessions 45/46's
    own claim a third time.
  - `"final_area"` ("The Sundering") -- no `fragment_id`; a new
    `final_reward: True` key instead. `generate_biome_room`'s two chest-
    building call sites (the normal vault placement and the no-room-for-
    a-vault fallback) both now go through a new small `_vault_reward(biome)`
    helper that returns either `{"artifact": {...}}` or `{"final_reward":
    True}`, so the two payload sites can't drift out of sync with each
    other. `boss_type` is a new `elder_dragon` (see data/enemies.json) --
    deliberately a fresh, tougher guardian rather than reusing one of the
    four biome mini-bosses a second time, since the doc's own "short, dense
    final dungeon" framing implies a genuine capstone fight, not a rematch.
    Still tier 1 (`BIOME_TIER`) like every other biome -- no per-biome tier
    override added, keeping this session's diff to the same shape as
    44-46's rather than introducing a new difficulty knob for one room.
  - Unlock gating for the Final Area reuses the existing fetch/trade chain
    unchanged: `guide_final`'s `wants` is just `mire_fragment` (the last
    fragment in the chain), not a new "wants all four" schema. This works
    because session 45's own departure from the source games (a traded
    fragment is never consumed, since the doc's Final Area section needs
    every fragment *held*, not handed over) means that by the time a player
    holds the last fragment in a strictly linear chain, they already hold
    every fragment before it -- so "wants the last one" and "wants all of
    them" are equivalent for this chain's shape, with no new want-type
    needed.
- **`data/artifacts.json`**: new `mire_fragment` entry ("Mire-Bound
  Fragment").
- **`data/adventure_quests.json`**: two new entries, `guide_fenmire` (wants
  `storm_fragment`, gives `unlock_biome: fenmire`) and `guide_final` (wants
  `mire_fragment`, gives `unlock_biome: final_area`) --
  `current_adventure_quest()` needed zero changes yet again, extending the
  chain is still just appending entries.
- **`data/enemies.json`**: new `elder_dragon` (hp 70/attack 12/defense
  6/xp 100/gold 40-60) -- deliberately no `damage_type`/`resist_elements`,
  plain physical stats well above any single dragon's, on the reasoning that
  the four biome dragons already cover fire/cold/lightning/poison and a
  fifth elemental gimmick wasn't needed for the difficulty to read as a real
  step up.
- **`data/rooms/town_hub.json`**: two new exits, `to_fenmire` (kind `"mire"`,
  (11, 2), `requires_quest: "guide_fenmire"`) and `to_final_area` (kind
  `"sanctum"`, (21, 2), `requires_quest: "guide_final"`) -- placed on a new
  row above the three existing biome doors (which share y=4) rather than
  extending that same row, since the existing three already evenly space
  the hub's width; town_hub's exit set is now armory/crypt/Depths (unchanged)
  plus all five biome doors.
- **`main.py`/`engine/room.py`**: `"mire"`/`"sanctum"` town-exit tint
  variants and `KIND_FALLBACK_COLORS` entries, plus a placeholder
  `enemy_elder_dragon` sprite (same triangle silhouette as the four biome
  dragons, dark bronze/gold instead of any of their four saturated hues).
  **Sanctum's tint needed a second pass**: the first attempt reasoned that a
  *lower* `strength` (0.5, vs. the other markers' 0.6-0.85) would read
  "brighter," on the theory that less blending would let more of the raw
  tint color through -- backwards. `make_tint_variant`'s own math
  interpolates the wash color *toward white* as strength drops (strength 0
  is a no-op wash), so 0.5 produced a muted result that a rendered
  screenshot showed sitting almost on top of "mire" in a direct pixel
  sample ((51, 58, 52) vs. mire's (30, 49, 40) -- too close). Also, per
  sessions 31/46's own already-established finding, `BLEND_RGB_MULT` can
  only ever darken a channel relative to the source art's own value, so
  "make the capstone door read as literally brighter than the others" was
  never achievable against the same dark "cave" source sprite regardless of
  tint choice -- the wrong bar to aim for. Refixed by aiming for a distinct
  *hue combination* instead (the standard the other four markers actually
  meet): a saturated yellow-gold (red+green boosted, blue suppressed) at
  strength 0.8, a red+green/no-blue combination none of the other four use
  (wilds is red-dominant, frost is blue-only, storm is red+blue, mire is
  green-only). Re-rendered and re-sampled (now (49, 56, 29), clearly lower
  blue than every other marker) and visually confirmed via a zoomed
  screenshot: mire reads as a cool dark green-teal arch, sanctum as a warm
  brown-gold one right next to it, distinct at a glance.
- **Win screen** (the doc's step 4, "nothing in the engine has an ending
  today"): `Game.win_screen_open`, a transient (not persisted) flag set the
  instant the Final Area's vault chest opens (`handle_move`'s new
  `chest.get("final_reward")` branch), alongside a new synthetic
  `"adventure_victory"` id added to the existing `completed_adventure_quests`
  set -- deliberately *not* a new save table: `"adventure_victory"` is never
  an entry in `data/adventure_quests.json`, so `current_adventure_quest()`'s
  own front-scan (which only ever checks real chain ids) is unaffected by
  the extra id riding along in the same set, and the "has this save already
  won" fact persists for free through machinery that already exists. Per the
  design doc's own suggestion ("reusing run_menu's existing title-screen
  rendering infra"), `_draw_win_screen()` reuses the same panel/font/overlay
  style every other panel already uses, but takes no input beyond "dismiss"
  -- checked at the very top of both `handle_key_down` and `handle_mouse_down`
  (ahead of Esc's own quit-if-nothing-to-close logic, and ahead of the
  `_any_panel_open()` panel-click dispatch, since the win screen deliberately
  isn't part of that family -- it has no rows, nothing to select). Dismissing
  it drops straight back into ordinary play, never a menu: Adventure Mode is
  a wing of the game, not the whole of it, and the Depths keep going
  afterward, matching the design doc's own "additive, not a replacement"
  framing from session 44. Re-opening the same chest afterward is the same
  silent no-op every other chest-content branch already gets once its id is
  in `opened_chest_ids` -- confirmed the modal never re-fires on a second
  open. The Journal panel's Frontier Guide line also gained a third state
  (session 45 built two: "not yet found" / "ready to trade"; session 46
  implicitly kept "no further requests" once the chain empties) --
  `"adventure_victory"` in `completed_adventure_quests` now shows "The
  frontier is at peace -- the seal is broken and the realm saved" instead,
  distinguishing "traded away every fetch/trade step" (true the moment
  `guide_final` completes) from "actually finished the Final Area" (true
  only once its chest opens), which aren't the same moment.
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`, confirmed real `save.db`'s mtime unchanged before and
  after every run this session): drove the *entire* five-biome chain
  end-to-end through the real dispatch path -- town_hub's exit set is
  exactly the expected seven
  (`to_armory`/`to_crypt`/`to_scorched_wastes`/`to_frostreach`/
  `to_stormfell`/`to_fenmire`/`to_final_area`); walked
  Scorched Wastes -> Frostreach -> Stormfell -> Fenmire -> Final Area,
  confirming each new biome exit returns `"locked_exit"` before its chain
  quest completes and a real `"exit"` transition after; confirmed all four
  fragments (`ember`/`frost`/`storm`/`mire`) are claimed through the real
  chest-open dispatch and `attempt_trade()` un-gates each next door in turn;
  confirmed the Elder Dragon spawns in `biome:final_area:<seed>` and
  defeating it and opening its chest sets `win_screen_open` **and**
  `"adventure_victory"`; confirmed re-opening that same chest afterward is a
  no-op that does *not* re-open the win screen; confirmed Esc, any other
  key, and a click anywhere (including well outside the panel) all dismiss
  the win screen without leaking through to movement or quitting the game;
  ran `persist()` then booted a **second** fresh `Game` instance against the
  same scratch save file and confirmed `"adventure_victory"` and all four
  fragments survived the round-trip. Ran this whole sequence (fresh
  random seed each time, since a new game's seed isn't fixed) 20+ times
  back-to-back with zero failures after fixing a string of bugs in the
  *verification script itself*, not the game code -- worth recording since
  they're exactly the kind of mistake a future session's own verification
  script could repeat: (1) a hand-rolled BFS pathfinder that refused to
  terminate when the player's start position was already adjacent to the
  target, incorrectly reporting "no path" and skipping combat entirely; (2)
  the same pathfinder routing *through* unrelated town exits as if they were
  plain floor, since stepping onto an exit tile is committal and silently
  teleported the walk into the wrong room mid-path; (3) assuming every
  biome dungeon always has a locked vault door, when session 44's own
  ~7%-of-seeds fallback (no room for a separate vault, an unlocked boss
  chamber instead) is a real, already-shipped code path the script needed
  to handle too. Separately stress-tested `generate_biome_room` directly
  (bypassing pygame) for both `"fenmire"` and `"final_area"` across 200
  seeds each with the same flood-fill reachability checker sessions 44-46
  used, plus an explicit lock-isolation check (the vault interior must be
  provably unreachable with the door forced shut) -- zero failures for
  either biome. **Also visually inspected** via rendered screenshots: the
  five town-hub exit markers reading as five distinct destinations at a
  glance (see the sanctum tint note above); Fenmire and The Sundering both
  rendering correctly with fog of war, the room name in the HUD, and (for
  The Sundering) the new Elder Dragon sprite; the win screen's centered
  panel with no clipping at any font; and the Journal panel's new victory
  line cascading correctly above the Dungeon Map section alongside the
  now-4-fragment-wrapped Artifact Fragments line.

### Session 48 — push-block (sokoban) puzzles, closing one half of wayfarer_adventure.md's own "puzzles as texture" note

User-driven request, same framing as sessions 44-47: read `PROGRESS.MD` and
`wayfarer_adventure.md`, look up *Yoda Stories*/*Desktop Adventures* again,
and continue development. With the design doc's own four-session phased
build order (finite biome dungeons, the fetch/trade chain, all four biomes,
the final area/win screen) fully closed out as of session 47, this session
went back to the doc's premise section instead of the phased plan, which
already named a second, never-built mechanic in passing: "Combat and
puzzles (**sokoban blocks**, colored key/gate pairs) are texture around
that trade-chain spine." A repo-wide grep (`sokoban|push_block|pushable`)
confirmed neither push-blocks nor colored keys exist anywhere in the
engine -- only a single generic `"key"` item and one-color switch/gate
pairs (session 10). Re-researched both games directly (a fresh web search:
MobyGames/GameFAQs/the Desktop Corner fansite for Yoda Stories, TV Tropes/
Fandom for Desktop Adventures) specifically for this mechanic and confirmed
it's real and central, not a doc-writer's guess: Yoda Stories' own manual
describes pushing/pulling blocks (Shift+Arrow) onto a marked square to
trigger an event (the "arrange 4 objects on the green square" Ben Kenobi
puzzle is the sourced example), and Desktop Adventures' own puzzle
mix explicitly includes "pushing around blocks and furniture" and "pressing
switches" alongside item-fetch puzzles. This session builds the
push-block half of that note; colored key/gate pairs (today's lock/gate
system is still single-color/generic) are still unbuilt, flagged below
rather than attempted in the same session.

- **`engine/room.py`**: `Room` gains `block_templates`/`plate_templates`
  (from a new `"blocks"`/`"plates"` key in room data, both default-empty so
  every existing room needs zero changes) -- structural starting positions
  only, same split every other fixture list here already keeps between
  "Room holds the template, Game owns the live/mutated state."  A `plate`
  is shaped exactly like a `switch` (`id`/`x`/`y`/`gate_id`) but is
  triggered by a block's weight instead of the player's own footstep.
- **`engine/entity.py`**: `Player.try_move` gains a `blocks=()` param and a
  new branch, checked after `locked_exits` and before the generic `blocked`
  walkability check (same reasoning locked_door/gate already sit ahead of
  that check) -- necessarily so, since a block's tile is itself folded into
  `_blocked_positions()` (see below), and without this branch running
  first every block would just read as an unmovable wall. On a bump into a
  block, computes the push destination one tile further in the same
  direction and validates it against `room.is_walkable` (walls/closed
  gates-doors) plus every other list `try_move` already receives (enemies,
  npcs, chests, switches, items, and every *other* block) -- a landing tile
  occupied by anything returns `{"type": "blocked"}` (the push simply
  fails, same as bumping a wall) rather than ever silently clipping through
  or displacing something. A legal push is committal in one input, same as
  a chest/switch walk-on: the player steps into the block's old tile *and*
  the block moves, both in the same `try_move` call -- the caller (Game)
  only needs to update the block's own position afterward, not re-derive
  where the player ended up.
- **`main.py`**:
  - `_blocked_positions()` now also folds in every block's current
    position, alongside locked doors/gates -- a block is a real physical
    obstacle for enemy pathing and spell line-of-sight (both already
    consume this set) exactly like a closed gate, for every purpose
    *except* the player's own push (which checks `self.blocks` directly in
    `try_move`, ahead of ever consulting this set).
  - `load_room`: `self.plates = list(self.room.plate_templates)` (plates
    never move, so no override needed, same as switches). `self.blocks` is
    built from `self.room.block_templates`' starting positions, then
    overlaid with `self.save.get_block_positions(room_id)` for any block
    that's been pushed on a previous visit -- same "template is the
    default, a save-backed table is the override" split `room_drops`
    already established for dropped items, just keyed by id instead of
    being an add/remove list (a block always exists, it just may have
    moved).
  - `handle_move`'s new `"push_block"` branch: updates the block dict's
    `x`/`y` in place, then checks whether its new position matches any
    plate; if so and that plate's `gate_id` isn't already open, opens it
    (removes the gate from `self.gates`, same as the existing `"switch"`
    branch) -- gates stay open permanently once triggered by a plate,
    identical semantics to a switch, so there's no "re-close if the block
    is later pushed off" logic to write. `self.blocks` is mutated in
    memory only and flushed to the new table at the same three checkpoints
    `self.room_drops` already flushes at (`persist()`, the `"exit"`
    stairs/door branch, Word of Recall) -- same in-memory-first convention
    session 43 established, not a new pattern.
  - The existing `"gate"` bump message ("Find the switch") was generic
    enough to imply every gate has a switch specifically, which is no
    longer true -- reworded to "Something nearby must trigger it" so it
    stays accurate for either trigger kind without the player having
    guessed which one a given gate uses.
  - `_load_assets`: `push_block` (warm brown-stone square placeholder,
    `make_placeholder(..., shape="square")`, same shape switches already
    use but a color distinct from their red/green) and `plate_off`/
    `plate_on` (dim slate-blue vs. lit gold, mirroring switch_off/on's own
    not-yet/triggered convention) -- no crate/boulder/pressure-plate art in
    either sheet, same "no matching sprite" situation sessions 21/28/39
    already hit for the Viper/traps/spellbooks.
  - `_draw_fixtures`: plates draw before blocks (so a block resting on its
    plate shows the block, not the floor marking underneath -- same
    draw-order reasoning Room.draw already uses for floor tiles under
    exit-kind overlays), both fog-gated through the same `_is_visible`
    check every other fixture already uses.
- **`engine/save.py`**: new `block_positions` table
  (`room_id, entity_id, x, y`, `PRIMARY KEY(room_id, entity_id)`), full-
  replace via `get_block_positions`/`set_block_positions`, identical shape/
  semantics to `room_drops`. Added to `reset()`'s wiped-table list.
- **`data/rooms/crypt.json`**: the mechanic's first (and so far only) real
  use, added to the existing hand-authored Crypt room rather than into
  procedurally-generated content (Depths `generate_room`/Adventure Mode
  `generate_biome_room`) -- deliberately scoped down from an earlier plan
  to wire this into procgen directly. Reasoning: a procedurally-placed
  puzzle needs its own solvability guarantee (the block must be reachable,
  the push path must be straight and clear, and the walled-off reward
  pocket must not accidentally sever some *other* room's only path through
  that space -- exactly the class of bug session 44 already found and had
  to fix for the vault-ring case) -- a real but separately-scoped problem,
  not attempted this session. A hand-authored room sidesteps all of that:
  the geometry is fixed and fully inspectable by hand, so this session
  could build and verify the mechanic itself end-to-end without also
  re-deriving generate_room's reachability-proof machinery for a second
  fixture type. Extending push-blocks into procgen is flagged below as
  follow-on work, not silently dropped.
  - Carved a small sealed pocket into the existing `back_hall` region's own
    open interior (no new room, exit, or fog region needed -- the pocket's
    three cells already fall inside `back_hall`'s existing region
    rectangle): walled off `(27,1)` and `(27,3)` and `(28,4)`, leaving
    `(27,2)` as the pocket's sole opening (the `gate` fixture sits there)
    and `(28,1)/(28,2)/(28,3)` as the enclosed interior holding a new bonus
    chest (`crypt_chest1`, `gold_greater` -- deliberately gold rather than
    gear/a spellbook, since a chest that can't fail to have room for its
    reward was one less thing to verify this session). Confirmed by direct
    grid inspection (not just visual inspection) that all three sealed
    cells were previously plain unused `back_hall` floor -- no item/enemy/
    region boundary sat on any of them -- and that `back_hall`'s only real
    connections (the row 8-10 bridge to `entry_hall`/`hall_passage`, and
    the vault door at row 11-12) are nowhere near this corner, so sealing
    three tiles here can't disconnect anything else in the room.
  - `crypt_block0` starts at `(21,2)`, three tiles west of a new
    `crypt_plate0` at `(24,2)` (linked to a new `crypt_gate0` at `(27,2)`)
    -- reaching the plate takes three separate pushes along the same row,
    not one, since the block only moves one tile per bump. Deliberately
    *not* a trivial one-push puzzle: once the block settles on the plate,
    it's a real (permanent) obstacle sitting in the same row as the now-
    open gate, so reaching the gate/chest afterward requires detouring
    around the player's own block via row 1 or row 3 for one tile and
    dropping back into row 2 -- an emergent side effect of "the block you
    just placed is still a solid object," not something hand-scripted, and
    a nice match for how the real games' own block puzzles work (the
    solution can put an obstacle in your own way).
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`, confirmed the real `save.db`'s mtime unchanged
  before/after): booted a real `Game`, loaded `crypt`, confirmed
  `crypt_block0` starts at `(21,2)` and `crypt_gate0` starts closed;
  drove three real `handle_move(1, 0)` calls and confirmed the block
  advanced one tile per push (`22,2` -> `23,2` -> `24,2`) while the player
  advanced into each of the block's vacated tiles in turn, landing on
  `(24,2)` opened `crypt_gate0` (added to `open_gate_ids`, removed from
  `self.gates`) via the real plate-match check in `handle_move`; confirmed
  a further bump into the now-settled block returns `"push_block"` again
  (it's a legal, if pointless, push against clear floor) rather than
  `"blocked"`, proving the block is a real obstacle and not just a one-
  time trigger that vanishes; walked the real detour (north/east/east/
  south/east/east) around the settled block and through the open gate,
  confirmed the chest opens through the real chest-dispatch path and
  grants `gold_greater`'s gold, and confirmed re-bumping the same spot
  doesn't re-fire (same `opened_chest_ids` no-op every other chest gets).
  Ran `persist()` then booted a **second** fresh `Game` instance against
  the same scratch save file and confirmed the block's pushed position,
  the open gate, and the opened chest all survived the round-trip;
  separately booted a **third** fresh instance against a brand-new
  (never-persisted) save and confirmed the block starts back at its
  template position `(21,2)`, proving the override-on-top-of-template
  logic only ever applies when there's actually persisted state to apply.
  Regression-checked `town_hub`/`armory`/a biome room/a Depths `proc:` room
  all still load with empty `blocks`/`plates` lists and no errors, since
  none of those rooms define either key. **Also visually inspected** via
  rendered screenshots: before the push, the brown block, dim slate plate,
  blue gate bars, and closed chest all reading as four distinct fixtures in
  a row; after three pushes, the block sitting visibly on the plate's tile
  (block drawn on top, per the plate-then-block draw order) and the gate
  bars gone entirely from the render (confirming it actually opened,
  not just logically).

### Session 49 — colored key/gate pairs, closing the other half of wayfarer_adventure.md's "puzzles as texture" note

Same recurring framing as sessions 44-48: read `PROGRESS.MD` and
`wayfarer_adventure.md`, look up *Yoda Stories*/*Desktop Adventures* again,
continue development. Session 48's own Known Limitations left exactly one
named, sourced, never-built mechanic on the table: "Colored key/gate pairs
are still unbuilt... this half is still just a single generic `"key"` item
unlocking any `locked_door`, no color/type matching." This session builds
that half.

Re-researched both games directly (fresh web search) specifically for this
mechanic before touching code, same discipline session 48 used for
sokoban: Yoda Stories' own Fandom wiki (`Mission`/`Locator Map` pages)
confirms Key Cards are explicitly color-coded ("keys come in many shapes,
sizes and colors, but all serve the same purpose: opening doors & chests"),
that they gate `Blockade Cell`/`Gate Cell` puzzles, and that the game's
hint system deliberately generalizes to an item's *group* (Tools/Key
Cards/Parts/Valuables) rather than naming the exact required item --
confirming the real mechanic is "the right key for the right lock," not a
single universal key. Desktop Adventures sources didn't surface a distinct
colored-key description in this pass, but wayfarer_adventure.md's premise
section already pairs the two games as "same engine, two skins," and this
engine's own existing generic `"key"`/`locked_door` pair (session 10) is
the mechanic being specialized here, not something invented fresh.

- **`data/items.json`**: two new item defs, `key_copper`/`key_jade`,
  shaped identically to the existing `"key"` (effect `"none"`, value 0,
  auto-consumed on bump -- see below) -- flavor text names which door
  color each opens. No `key_color` field or lookup table: the matching
  item type is derived directly from the door's color (`f"key_{color}"`),
  same "the string is the join key" convention `push_block`/`plate_off`
  already use for their own sprite names, rather than adding a second
  source of truth that could drift out of sync with the door data.
- **`engine/room.py`**: zero changes needed. `locked_door_templates` are
  raw dicts straight from `data/rooms/*.json` (confirmed by reading the
  module before touching it) -- an optional `"color"` key on a
  `locked_doors` entry just rides along for free, the same way `plates`'
  `gate_id` already does, with no schema change and zero risk to every
  room that doesn't define one.
- **`main.py`**'s `"locked_door"` branch (`handle_move`): now reads
  `door.get("color")`. No color -> exactly the original session-10
  behavior (`"key"` opens it, unchanged, so `crypt_door0` needed zero
  edits). A color -> the needed item becomes `f"key_{color}"`; a
  wrong-colored key (or no key at all) leaves the door locked and prints a
  color-naming message ("This door is banded in copper -- you need a
  matching key") instead of the generic one, without ever touching (let
  alone consuming) whatever *is* in the player's bag -- confirmed by
  headless test, see below.
- **`_load_assets`**: two new door tint variants (`locked_door_copper`,
  `locked_door_jade`, both `make_tint_variant` off the same `gate_bars`
  source art gate/locked_door already share) and two new key-item tint
  variants (`item_key_copper`, `item_key_jade`, off `item_key`). Picked
  copper (200, 90, 40, no blue at all) and jade (60, 170, 110, no red at
  all) specifically to sit far apart from each other *and* from the two
  colors already claimed on this same source art (gate's blue (120, 170,
  220), the original locked_door's amber (210, 160, 60)) -- same "hue
  combination, not just brightness" lesson sessions 46/47 already learned
  the hard way for the biome tint markers, applied proactively here rather
  than re-discovered.
- **`_draw_fixtures`**: a locked door now draws `locked_door_{color}` if
  it has one, else the plain `locked_door` sprite it always drew before --
  one conditional, same pattern the trap loop already uses for
  per-type sprite names (`AssetManager.get_sprite(trap["type"])`).
- **`data/rooms/crypt.json`**: two new alcoves in the existing hand-authored
  Crypt, same scoping call session 48 made for push-blocks and for the
  same reason -- a procedurally-placed colored lock needs its own
  solvability guarantee (the matching key must be placed somewhere
  actually reachable *before* the door, not just anywhere in the seed),
  which is a real but separately-scoped problem, not attempted this
  session. Both new alcoves reuse the exact "seal a 1-tile pocket into an
  existing region's own open interior, one wall-gap doorway" shape session
  48 already established for the crypt_chest1 push-block reward, just
  carved into `entry_hall` (a mostly-empty 13x18 rectangle with only three
  pre-existing entities in it) instead of `back_hall`:
  - Copper alcove: interior `(11,2)` (new `crypt_chest2`, `potion_greater`),
    sealed by walling `(10,2)`/`(12,2)`/`(11,1)`, door (`crypt_door1`,
    `color: "copper"`) at `(11,3)`, approached from the already-open
    `(11,4)`.
  - Jade alcove: interior `(11,15)` (new `crypt_chest3`,
    `whetstone_greater`), sealed by walling `(10,15)`/`(12,15)`/`(11,14)`,
    door (`crypt_door2`, `color: "jade"`) at `(11,16)`, approached from the
    already-open `(11,17)`.
  - The matching keys themselves (`crypt_key_copper` at `(3,2)`,
    `crypt_key_jade` at `(3,17)`) are placed elsewhere in `entry_hall`,
    both confirmed clear of every pre-existing item/enemy coordinate by
    direct grid inspection before editing (not just eyeballed) -- same
    discipline session 48 used before carving its own pocket.
  - Deliberately **two** colors, not one: a single colored pair would only
    ever prove "a key now has a name," not the actual discriminating
    behavior the source games' own color-coding exists for (a key that
    *doesn't* match still fails). Two independent color/door/chest triples
    sitting in the same dungeon, verified cross-wise (a jade key bumping
    the copper door, and vice versa, both correctly refused, see below),
    is the smallest build that actually demonstrates the mechanic rather
    than just renaming the existing one.
- Verified via a standalone flood-fill script (same technique sessions
  44/46/48 used for their own vault/pocket isolation proofs) before ever
  touching game code: with all three locked doors (`crypt_door0`,
  `crypt_door1`, `crypt_door2`) treated as closed, none of their three
  interiors are reachable from the room's main corridor; opening any *one*
  door makes only its own interior reachable, the other two staying
  sealed; with all three open, all 405 floor tiles in the room are
  reachable (unchanged from before this session's wall edits, confirming
  nothing else in the room was accidentally disconnected).
- Verified headless (SDL dummy driver, scratch DB via monkeypatched
  `main.SAVE_PATH`, confirmed the real `save.db`'s mtime/md5 unchanged
  before and after): booted a real `Game`, loaded `crypt`, confirmed all
  three locked doors present with the expected `color` values (or `None`
  for the original `crypt_door0`); bumped the copper door with an empty
  inventory and confirmed it stays locked; gave the player a **jade** key
  and confirmed bumping the copper door still refuses to open *and* the
  jade key is not consumed by the failed attempt (`inventory.stacks` count
  unchanged); gave the player the copper key and confirmed the copper door
  opens and the key is consumed; walked into the copper alcove and
  confirmed its chest opens through the real chest-dispatch path; repeated
  the same sequence for the jade door/alcove (using the jade key already
  in the bag from the earlier mismatch test); ran `persist()` then booted
  a **second** fresh `Game` instance against the same scratch save and
  confirmed both colored doors' unlocked state survived the round trip
  while the untouched `crypt_door0` was still locked; as a regression
  check, confirmed the plain `"key"` item still opens `crypt_door0`
  exactly as it did before this session's changes. **Also visually
  inspected** via rendered screenshots (a fresh, never-persisted save so
  both colored doors render in their still-locked state): the copper and
  jade doors reading as clearly distinct tinted-bars fixtures from each
  other and from the room's original amber `locked_door`/blue `gate`, each
  sitting correctly in its own small recessed wall alcove above its
  reward chest; the copper and jade key items on the entry_hall floor
  reading as distinctly orange-red vs. yellow-green at a glance, matching
  their respective doors.

## Known Limitations / Future Work

Roughly in likely-priority order — not committed to, just tracked:

- **Push-block puzzles (session 48) exist in exactly one hand-authored
  room (Crypt)** — not yet wired into either procedurally-generated
  system (Depths `generate_room` or Adventure Mode's `generate_biome_room`).
  Doing so needs its own solvability guarantee (block reachable, push path
  straight/clear, the sealed reward pocket provably not severing some other
  room's only path through that space) -- the same class of problem session
  44 already solved once for the vault-ring case, just for a second fixture
  type; deliberately not attempted this session, scoped down to a hand-
  authored room specifically to avoid re-deriving that proof in the same
  session the mechanic itself was first built.
- ~~**Colored key/gate pairs are still unbuilt**~~ — closed out session 49:
  `locked_doors` entries can now carry an optional `"color"`, matched
  against a `key_<color>` item (`key_copper`/`key_jade` so far, two colors
  built end-to-end in Crypt), with the original uncolored `"key"`/
  `locked_door` pair (session 10) completely unchanged as the no-color
  default. This closes wayfarer_adventure.md's premise-section pairing of
  colored keys with sokoban blocks as the two puzzle types "texture around
  the trade-chain spine" — both halves are now built. Same limitation as
  push-block above, and for the identical reason: **colored doors exist in
  exactly one hand-authored room (Crypt), not wired into either
  procedurally-generated system** — a procedurally-placed colored lock
  needs its matching key provably reachable *before* the door in the same
  generated seed, a solvability question deliberately not attempted this
  session.
- ~~**Adventure Mode is three biomes and two quest-chain steps into a
  multi-session arc (sessions 44-46)**~~ — closed out session 47: all four
  of the design doc's biomes now exist (Scorched Wastes/Young Red Dragon/
  Ember-Charred Fragment, Frostreach/Young White Dragon/Frost-Bound
  Fragment, Stormfell/Young Blue Dragon/Storm-Cloven Fragment, Fenmire/
  Young Green Dragon/Mire-Bound Fragment), the fetch/trade chain now runs
  all the way to a Final Area ("The Sundering," guarded by a new Elder
  Dragon mini-boss) whose vault chest is Adventure Mode's actual win
  trigger, and a one-time victory modal (`Game.win_screen_open`/
  `_draw_win_screen`) closes the design doc's own "nothing in the engine
  has an ending today" gap. See `wayfarer/wayfarer_adventure.md` for the
  full original plan (now fully built) and session 47's own PROGRESS.MD
  entry for exactly how the win state is wired and persisted (via a
  synthetic `"adventure_victory"` id riding the existing
  `completed_adventure_quests` set, no new save table). Still true: sprite
  art for every biome dungeon (including the Final Area) is unchanged from
  the Depths' own `dungeon_v2` tileset -- resizing sprites larger on this
  branch (separately requested, reconfirmed as still deferred every session
  from 46 through 47) still hasn't happened, and is now the only explicitly
  deferred item left on this branch. Also still true: the fetch/trade
  mechanic deliberately does *not* consume the traded fragment (see session
  45's own notes) -- this turned out to be exactly what made `guide_final`'s
  single-fragment `wants` clause work as an implicit "holds every fragment"
  check (session 47), so this departure is now load-bearing for the win
  condition, not just a design choice to revisit. Also flagged (sessions 46
  and 47 both hit variants of this): a `BLEND_RGB_MULT` color tint's
  `strength` parameter interpolates *toward white* as it drops (0 = no tint
  at all), the opposite of what "lower strength, less blended, more
  saturated" sounds like at a glance -- and separately, the technique can
  never make a tinted marker read as literally *brighter* than its own dark
  source sprite, only differently-hued, since the blend mode only ever
  darkens. Both are worth remembering before reaching for this trick again:
  verify via an actual rendered screenshot and pixel sample, not
  reasoning about the tuple/strength numbers on paper.
- **Adventure Mode's Final Area difficulty is fixed/curated, not
  level-scaled** (session 47, per the design doc's own "leans fixed/
  curated" Open Questions note) — the Elder Dragon and every biome's
  regular encounter roster use the same fixed `BIOME_TIER = 1` as the first
  three sessions established, unplayed and untuned the same way session 9's
  original Depths density was; a level 1 and a level 20 character currently
  face an identical Final Area fight.
- **No branching/replayability in the adventure quest chain** — the design
  doc's own stretch goal ("any 2 of 3 fragments," randomized per-playthrough
  chains closer to the real Desktop Adventures games) was explicitly scoped
  out of every session's build in favor of a fixed linear chain; once a
  save's `completed_adventure_quests` contains `"adventure_victory"` there's
  no reset path short of a full `SaveManager.reset()` (which wipes
  everything, not just Adventure Mode progress).
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
  CotW's own third elemental-dragon breath type. ~~`"acid"` is still just a
  name nothing uses yet~~ — session 33 researched this directly (Wikibooks'
  CotW bestiary) and found the premise was wrong: CotW's actual four dragon
  colors/breaths are Red/fire, White/cold, Blue/lightning, Green/poison
  gas — there is no acid dragon in the real game, and the fourth slot is
  poison, not a fourth `damage_type`. Session 33 closed that slot with the
  Young Green Dragon reusing the *existing* poison mechanism (session 21's
  Viper fields) rather than adding an `"acid"` elemental type nothing in
  CotW actually calls for. `damage_type` support for a real `"acid"` is
  still just unused plumbing if ever wanted, but there's no CotW-sourced
  reason to build content for it. Also still true:
  ~~`resist_elemental` (the player-side Amulet stat) is one flat percentage
  generic across every element, not per-element the way CotW's own separate
  Resist Fire/Resist Cold/Resist Lightning items are~~ — session 34
  researched this directly (Wikibooks' CotW Magic page) and found the
  "items" framing in session 31's note was itself slightly off: in the real
  game, Resist Fire/Cold/Lightning are **spells** (temporary, halve
  elemental damage for a duration), not equipment. Session 34 built exactly
  that — three new spells stacking additively on top of the still-flat,
  still-generic `resist_elemental` amulet stat. Whether CotW's own amulets
  are themselves per-element or generic wasn't re-researched this session
  (out of scope — session 34 only sourced the spell page); `equipment.py`'s
  flat amulet stat is unchanged either way, so this is still a real
  (smaller) gap if amulets turn out to be per-element in the source game.
  What's confirmed is the *spell* trio, and a player now has a real tool to
  out-mitigate a specific dragon's breath (e.g. Resist Cold before a Young
  White Dragon fight) that they didn't have before.
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
- **Content breadth is better but still thin**: fourteen enemy types (session
  21 added the Viper, session 22 the Young Red Dragon, session 24 the
  Wraith, session 31 the Young White Dragon, session 32 the Young Blue
  Dragon, session 33 the Young Green Dragon, session 35 the Dark Wraith and
  Abyss Wraith, session 37 the Barrow/Tunnel/Castle Wight), four item families
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
  about a per-enemy phasing flag, not attempted this session. ~~Also still
  true: only one Wraith variant exists (CotW has Pale/Dark/Abyss tiers~~ —
  closed out session 35: Dark Wraith and Abyss Wraith joined the base Wraith
  as two tougher, deeper-only tiers, same drain mechanism. ~~The drain only
  ever targets mana (all three tiers) — this engine has no STR/DEX/INT/CON
  attributes to drain the way CotW's separate stat-draining Wight family
  does; Wight itself is still unbuilt (see session 35)~~ — closed out
  session 37: Barrow/Tunnel/Castle Wight now drain `attack` instead (the
  same "one representative stat stands in for the un-modeled attribute"
  adaptation session 24 already made for the Wraith's INT/mana drain), a
  second, separately-cured undead-drain resource alongside the Wraith
  family's mana drain rather than a Wraith reskin.
- ~~**No drop mechanics for consumables**~~ — closed out session 43: `X` in
  the Inventory panel drops one unit of the selected consumable onto the
  player's own tile, persisted per-room (`engine/save.py`'s new
  `room_drops` table) so it's still there after a room transition and
  back, picked back up the same way any floor item is. Still true: gear
  (equipped or Found Gear) has no drop path -- scoped to consumables only,
  same line session 8/16 already drew between the two systems.
- **Spells only have one casting path** (session 12) — the Spellbook panel
  (`C`), which always costs a turn on a successful cast. There's no field
  quick-cast hotkey the way items have 1-8, a deliberate scope cut (see
  session 12) to avoid a second key namespace, not a technical limitation.
- ~~**No purchasable/found spellbooks (session 12)**~~ — closed out session
  19: a new Scholar NPC in the town hub sells every not-yet-known spell for
  gold (`book_cost` in `data/spells.json`), learned immediately regardless
  of level. ~~Still true: spellbooks are bought, never found as dungeon loot
  the way CotW's sometimes are~~ — closed out session 39: spellbooks now
  also drop as Depths floor loot and vault chest contents, riding the same
  per-instance-drop machinery equipment already uses (session 16/17), same
  as this note predicted.
- **27 spells** (this note had drifted stale as of session 36 -- last
  updated at session 32's "15 spells" and not revised when sessions 34/36
  each added three more; corrected here, and again for sessions 38/40/41/42's
  additions): one per unlock tier (levels 1-5),
  three divination spells at 6/7/12 (session 15: Detect Monsters/Detect
  Treasure; session 28: Detect Traps), Neutralize Poison at 8 (session 23),
  Word of Recall at 9 (session 26, CotW's "misc"-category town/dungeon
  shortcut), Identify/Remove Curse at 10/11 (session 27, mana-cost
  alternatives to the Merchant's paid versions of the same two actions),
  Levitation at 13 (session 29, trap-damage immunity paired with Detect
  Traps' own duration), Cold Bolt at 14 (session 31, the second
  attack-spell element alongside session 12's original Spark and session
  22's Firebolt), Lightning Bolt at 15 (session 32, the third element),
  Resist Fire/Cold/Lightning at 16/17/18 (session 34, additive with the
  flat `resist_elemental` amulet stat), and Heal Medium/Major Wounds at
  19/20 (session 36, completing the Heal Minor Wounds ladder with CotW's
  own sourced percent-of-max-hp-or-flat-whichever-is-higher formula), and
  Light/Clairvoyance at 21/22 (session 38, instant region-fog and
  automap-room reveals), Sleep Monster at 23 (session 40, single-target
  crowd control), and Fireball/Cold Ball/Ball Lightning at 24/25/26
  (session 41, 3x3-area siblings of Firebolt/Cold Bolt/Lightning Bolt,
  full damage center + half-damage ring, "always hit," and can splash the
  player if cast at an adjacent target), and Slow Monster at 27 (session
  42, halves a target's action rate per cast, stacking to 1/3, 1/4, etc.
  on re-cast, boss-immune via the same `sleep_immune` flag Sleep Monster
  uses). Now 27 spells total. Easy to extend further: add an entry to
  `data/spells.json` and, if it's a new `effect` type, a branch in
  `Game.cast_selected_spell` (session 12) -- the Spellbook panel scrolls to
  fit whatever the ladder grows to (session 29), confirmed again at 27
  entries in session 42.
- ~~**Slow Monster and Transmogrify Monster are still unbuilt** (session
  40)~~ — half closed out session 42: Slow Monster shipped, giving
  `Enemy.take_turn` a `slow_level`/`slow_tick` pair that skips all but 1 in
  every `slow_level + 1` calls, so "acting less than once per turn" (this
  note's original blocker) turned out to just need a modulo counter, not a
  deeper AI-timing model. ~~Transmogrify (turns the target into a random
  other monster, preserving its HP percentage) would need a live
  re-roll-into-any-enemy-type path (fresh stats block, sprite swap,
  re-applying whatever HP% it had) nothing in `engine/entity.py` currently
  does~~ — still true and still unbuilt, the bigger lift of the original
  pair; not attempted this session, deliberately scoped to Slow alone.
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
