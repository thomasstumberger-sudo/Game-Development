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
- Stats: HP, a secondary resource (stamina, currently unused placeholder),
  XP/leveling.
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
    entity.py            # Entity/Player/Enemy/ItemPickup, Enemy.take_turn() AI
    combat.py            # bump-attack resolution, leveling, enemy_attack()
    inventory.py         # slot inventory, item effects (heal, buff_attack)
    save.py              # SQLite save/load, room_flags table
  data/
    items.json, enemies.json, rooms/*.json
  assets/sprites/...    # 64x64 tiles, pre-sliced from two dungeon tilesets
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
  Rooms are addressed by `(seed, gx, gy)` and *regenerated deterministically
  every time* — no room geometry is ever written to the save file, only the
  run's `dungeon_seed` and which enemies/items in *visited* rooms are
  gone (reuses the same `room_flags` table hand-authored rooms use).
  Neighboring rooms agree on shared doorways via a canonical edge hash
  (`procgen._edge_open`), so connectivity is guaranteed without any
  cross-room bookkeeping. Room id `"proc:ENTRY"` is a sentinel the Crypt's
  JSON uses (it can't know the per-save seed ahead of time); `main.py`
  resolves it to `proc:{seed}:0:0` at transition time.
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

## Known Limitations / Future Work

Roughly in likely-priority order — not committed to, just tracked:

- **No sound assets exist yet.** The sfx loading path (`AssetManager.load_sfx`/
  `play_sfx`) is wired and fails gracefully on missing files, but there are
  no actual `.wav` files in `assets/sfx/` yet, so combat is silent.
  Music is spec'd as optional/off-by-default and not implemented.
- **Procedural rooms are plain open rectangles** — no interior obstacles/
  varied shapes yet (kept simple originally to guarantee reachability
  without a maze-solver). No depth-scaled difficulty either — every
  procedural room uses the same skeleton/potion/whetstone tables regardless
  of how far from the Crypt it is.
- **Only one enemy type and two item types exist.** Easy to extend — just
  add entries to `data/enemies.json`/`data/items.json` — but content
  breadth hasn't been a focus yet.
- **No equip/drop mechanics** — items are consumed permanently on use, no
  way to drop an item back onto the floor once picked up.
- **Stamina stat is an unused placeholder** — tracked on the player, not
  consumed or regenerated anywhere. Was left in for a future
  dash/ranged-item mechanic.
- **No automated test suite** — verification so far has been scripted
  headless smoke tests (SDL dummy driver) run ad hoc, not a checked-in
  pytest suite.
- **Explicitly out of scope per the original design brief**: networking,
  controller support, scrolling maps.

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
