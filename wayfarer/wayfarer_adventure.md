# Wayfarer Adventure Mode — design/feasibility write-up

Speculative planning only, written on branch `wayfarer-adventure-mode`.
Nothing in this document has been built. If/when a session picks this up,
treat it the same as PROGRESS.MD's Known Limitations list: a menu to pull
from, not a locked spec — expect it to get revised as real sessions hit
real constraints.

## Premise

Take Wayfarer in the direction of LucasArts' *Indiana Jones and His Desktop
Adventures* (1996) / *Star Wars: Yoda Stories* (1997) — same engine, two
skins. Confirmed structure (Wikipedia, TV Tropes): each playthrough
randomly assembles a map from tile chunks, scatters NPCs/dungeons/enemies
across it, and drives progress through **item-for-item fetch/trade
chains** — NPC A wants item X, gives you item Y (or a key, or passage) in
return, which is what NPC B (or a locked gate) needs next, chaining until
a final goal artifact is assembled and the run resolves. Combat and
puzzles (sokoban blocks, colored key/gate pairs) are texture around that
trade-chain spine, not the point of the game the way they are in CotW.

**Decision already made: Wayfarer stays turn-based.** The bump-combat,
`_advance_turn`-gated engine is the CotW half of this project's DNA and
43 sessions of content already assume it (enemy AI, spells, status
effects, traps — all turn-locked). Desktop Adventures' real-time movement
is not being ported; only its *progression structure* (fetch/trade chains
across distinct regions toward one end goal) is being borrowed. That's
the part of those games actually worth adapting here — the real-time feel
is incidental to it.

## What this adds vs. what stays

Wayfarer today is one hub (`town_hub`, plus `armory`/`crypt`) feeding a
single endless procedurally-scaling dungeon (`Depths`,
`proc:<seed>:<level>:<gx>:<gy>`, unbounded in `level`). There is no win
condition anywhere in the engine.

**Adventure Mode is additive, not a replacement.** The Depths stay exactly
as they are — the existing endless-grind wing new characters can always
fall back into. A new second wing branches off the town hub: a small
**finite** set of biome regions, each a capped dungeon (not
level-unbounded), gated behind a fetch/trade quest chain, ending in a
final area with an actual win state. Reasoning for additive over
replace-in-place: nothing about the existing 43 sessions of Depths content
needs to die for this to exist, and it's a much smaller blast radius to
build a new wing than to retrofit the infinite-depth model into a finite
one and risk breaking every existing session's save-compat assumptions
(`_migrate_room_id`, room_flags/room_meta keyed by the `proc:` id scheme,
etc.).

## World structure

- **Hub**: `town_hub`, unchanged, gets one new NPC (a "Frontier Guide" or
  similar) and one new exit once the player is ready to start the
  adventure chain (or it's just always open — TBD, see Open Questions).
- **3-4 biome regions**, each a self-contained finite dungeon reached from
  the hub (or from each other in a line/light branch — see Quest Chain
  below), each with:
  - its own tileset (see Assets below)
  - its own enemy roster, pulled from `data/enemies.json`'s existing
    elemental families rather than inventing new ones from scratch
  - one **artifact fragment** as its dungeon's terminal reward (guarded by
    that biome's toughest existing enemy, used as a mini-boss)
  - one **fetch/trade NPC** gating entry to the *next* biome, wanting
    something found only in *this* one
- **Final area**: unlocked once every fragment is held: a short, dense
  final dungeon (or single boss room) culminating in a win screen.

### Biome ↔ existing content mapping

The elemental dragon family already gives this almost for free —
`data/enemies.json` already has `damage_type`/`resist_elements` fire, cold,
and lightning dragons, plus a poison-breath green dragon reusing the
Viper's poison fields. Four biomes falls out directly:

| Biome (working name) | Terrain flavor | Existing mini-boss | Existing elemental hook |
|---|---|---|---|
| Scorched Wastes | desert/canyon | Young Red Dragon | `fire` |
| Frostreach | ice/tundra | Young White Dragon | `cold` |
| Stormfell | ruins/highlands | Young Blue Dragon | `lightning` |
| Fenmire | swamp/jungle | Young Green Dragon | poison (Viper fields) |

This also gives the player's existing Resist Fire/Cold/Lightning spells
(session 34) and Neutralize Poison (session 23) real, biome-specific
reasons to exist beyond the Depths — a nice side benefit, not the point.

### Assets

`assets/sprites/overworld/` is 353 tiles, sliced since session 9 and
flagged in PROGRESS.MD's Known Limitations as "sliced but unused" — this
is the intended reuse target for at least one biome's outdoor tileset,
and the reason biome dungeons are pitched as achievable without a big new
art pass. Whether all four biomes can be visually distinguished from this
one sheet alone, or whether 1-2 of them need a small supplementary tile
set, needs an actual look at what's in that folder before committing to
four — safest to scope the first pass to however many biomes the existing
sheet can convincingly support (2-3), and treat a 4th as a stretch goal
once art coverage is confirmed.

## Quest chain / progression gating

This is the one genuinely new system — nothing today tracks a *sequence*
of dependent objectives. The existing quest ladder
(`data/quests.json`, `Game.quest_index`) is a flat, parallel kill-quota
list against a single global `depths_kills` counter — no fetch/trade
semantics, no cross-quest dependency, no "this unlocks that" gate.

Proposed shape, new and separate from the existing cull-quest ladder
(that ladder keeps working exactly as-is, unrelated system):

- **`data/adventure_quests.json`**: an ordered chain, each entry roughly
  `{id, giver_npc, biome, wants: {type: "artifact"|"item", id: ...},
  gives: {type: "unlock_biome"|"item", id: ...}, dialogue: {...}}`.
  A straight line (Fetch fragment A → trade for passage to biome B → …)
  is the MVP; a light branch (any 2 of 3 fragments unlock the final area)
  is a stretch goal, closer to how Desktop Adventures' *randomized*
  per-playthrough chains actually worked, but randomizing the chain order
  itself is explicitly out of scope for a first pass — a fixed, authored
  chain is the whole first build; randomization is a possible future
  layer once a fixed chain proves the mechanics work at all.
- **New persisted state**: which quests in this chain are complete and
  which biomes are unlocked. Simplest fit for the existing save schema: a
  new single-column table (`completed_adventure_quests(quest_id TEXT
  PRIMARY KEY)`), same shape as `known_spells` — a flat "have we ever
  crossed this line" set, no per-room scoping needed since these are
  world-progression facts, not room-local ones.
- **New NPC interaction type**: today's NPCs are single-purpose
  (`merchant`/`healer`/`scholar`/`quartermaster`, dispatched by `npc.type`
  in `handle_move`'s `"npc"` branch). A fetch/trade NPC needs a new
  branch: "do you have the item this quest wants in your bag?" → consume
  it, grant the trade item or flip the unlock flag, advance the chain.
  Structurally this is much closer to `claim_quest_reward` (checks a
  condition, grants a reward, advances an index) than to the shop/healer
  panels — likely the smallest-diff path is generalizing
  `claim_quest_reward`'s shape rather than inventing a fourth panel type.
- **Artifact fragments themselves**: non-stackable, world-quest items —
  closer to how `"key"` is auto-consumed by a locked door than to a
  regular potion stack. Likely their own small `data/artifacts.json`
  rather than overloading `data/items.json`'s stack-of-N model, since a
  fragment is "own exactly one, ever" not "own N of."

## New engine surface, roughly in build order

1. **Finite biome dungeon generation** — a capped variant of
   `procgen.py`'s room generator (reuse `generate_room`'s room-carving/
   corridor/vault machinery wholesale; cap grid extent instead of treating
   `level` as unbounded, and drop the infinite per-level HP/defense scaling
   since a biome dungeon is a fixed difficulty, not a bottomless well).
2. **Adventure quest chain data + persisted completion state** (the new
   table + JSON above).
3. **Fetch/trade NPC interaction** (the `claim_quest_reward`-shaped
   branch above).
4. **Biome unlock gating** — an exit that's only walkable/visible once its
   prerequisite quest is complete (closest existing precedent: gates/
   switches, session 10 — a biome entrance is conceptually a switch-gated
   gate at the world-map scale rather than the room scale).
5. **Final area + win state** — genuinely new: nothing in the engine has
   an ending today. Smallest version: a final dungeon room whose boss
   defeat sets a flag and swaps to a static "You Win" screen, reusing
   `run_menu`'s existing title-screen rendering infra rather than
   building a new screen system from scratch.

## What this reuses cleanly (the reason the estimate isn't scarier)

- Room/exit/NPC data model (`engine/room.py`, `data/rooms/*.json`) — a
  biome dungeon's entry room is just another hand-authored room file like
  `town_hub.json`/`armory.json`/`crypt.json`.
- Per-instance drop + persistence machinery (session 16's equipment
  drops, session 43's floor-item drops) — an artifact fragment lying in a
  dungeon is structurally another `ItemPickup`-family entity.
- Elemental damage/resistance system (sessions 22/31/32/33/34) — biome
  mini-bosses and the spells that counter them already exist.
- `room_flags`/`room_meta` per-room persistence pattern — a direct
  template for the new completed-quests/unlocked-biomes state.
- Fog of war, automap, chests, traps, locked doors/gates — all
  biome-agnostic already, no changes needed to reuse them in a new wing.

## Open questions (need a decision before or during a first build session)

- **How many biomes for v1?** Recommend starting at 2-3 (confirm art
  coverage first) rather than committing to 4 up front.
- **Gating philosophy**: strict linear chain (simplest, most
  Yoda-Stories-authentic to a single playthrough) vs. light branching
  (any-order-of-2-of-3)? Recommend linear for v1.
- **Is Adventure Mode reachable immediately from a fresh character, or
  gated behind some Depths milestone** (e.g. reaching dungeon level 3)?
  No strong opinion yet — leans toward "always open," since gating it
  behind Depths progress adds a dependency this write-up hasn't scoped.
- **Does the final area's difficulty scale with player level** the way
  Depths does, or is it a fixed, curated difficulty (more authentic to
  the source games, which were never about infinite scaling)? Leans
  fixed/curated.
- **Save-slot implications**: one character, one Adventure Mode
  progress track (simplest, matches the single-save-file model
  `engine/save.py` already assumes), or could a character finish the
  chain and it just... stays finished (no replay)? No strong opinion —
  worth deciding before the persisted-state schema (above) is locked in,
  since "can it be replayed/reset" affects whether completion state needs
  a reset path in `SaveManager.reset()`.

## Suggested phased build order (once the above is settled)

1. One finite biome dungeon end-to-end (room gen + one mini-boss + one
   fragment drop), reachable directly from town, no gating yet — proves
   the "finite capped dungeon" variant of procgen works at all.
2. Add the fetch/trade NPC + one complete two-step chain (biome 1 →
   unlocks biome 2) — proves the new progression-gating system.
3. Extend to the full biome count decided above.
4. Final area + win screen.

Each of these is a plausible single-session scope, same granularity as
the last ~10 PROGRESS.MD sessions — this reads as a multi-session arc, not
a rewrite.
