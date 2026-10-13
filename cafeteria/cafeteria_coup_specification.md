# Game Specification: Cafeteria Coup

> **Status:** A playable **Chapter 1 vertical slice** now exists at `cafeteria/index.html`. Open it directly in a browser; there's no build step and no server. §1–§16 are the design as written. **§17 describes what was actually built**, including where the build had to settle something the design left open or contradictory. The source pitch is `localforge/examples/cafeteria_coup_game_design.md`, and everything in it stays **canon**. Additions on top of it are tagged **(new)**.

---

## 1. Concept

A real-time, top-down stealth-heist game where the stealth is **proactive, not patient**. You don't wait in a closet for a patrol to pass — you grease the hallway, gust a marble bust down it like a curling stone, and walk through the gap you made.

You play a Thief/Wizard at the Grand Arcane Academy, where classes are optional because magic automates everything and the Mage Council runs a vanity hierarchy on titles and merit points. The Archmages hoard the budget for giant, useless relics. The students eat cold gruel and magic sludge. You have sworn an oath to get onto the Council and vote through cafeteria reform.

The method: rob the Archmages, learn to out-talk them, put their relics back before anyone notices, then humiliate them in open session.

### Design pillars (new)
1. **Chaos is a tool, not a failure state.** Getting seen is a resource you can spend (Alibi Engine). Breaking things is how you make paths.
2. **Every system feeds the next stage.** How you rob a tower in Act 1 rewrites that tower in Act 3. What you steal is what you flex in duels. What you learn in duels is what you fire in the trial. Nothing is a side-mode.
3. **The joke is played straight.** The Phoenix Paradox is presented with full orchestral sincerity. The UI never winks. The world is petty and it takes itself completely seriously.
4. **The petty cause is the real cause.** Nobody is saving the world. The stakes are lunch. The game treats lunch as the most important thing in the world, because to the people eating it, it is.

---

## 2. Structure

### 2.1 The Chapter (one per Archmage)
Each Archmage is a **chapter**. Each chapter runs the canon loop exactly:

```
[ 1. Library Intel ] ➔ [ 2. Key Extraction ] ➔ [ 3. Tower Heist (Act 1) ]
                                                            │
[ 5. Council Trial ] ⇦ [ 4. The Return Trip (Act 3) ] ⇦ [ Intermission: Duels ]
```

Between stages the player returns to the **Campus Hub** (new) — the quad, the library steps, and the student cafeteria — where Heat decays, tools are bought, and duels are picked.

### 2.2 The Council and the win condition (new)
* The Mage Council has **7 seats**. The player needs **4 votes** at the final session to be seated and pass the reform.
* Each chapter ends in a **Council Trial** against that chapter's Archmage. Shattering their ego in the trial flips their seat: they either **abstain in shame** (seat neutralized) or, at a full shatter, **vote with you to save face** (seat won).
* 4 chapters are planned (one per key site, below). Seats 5–7 belong to Archmages who are never robbed — their votes swing on your **Standing** (§9.4), which rises with every public humiliation you deliver. Four shattered egos and decent Standing gets you seated.
* The final session is a fifth trial against the full bench. See §9.5.

### 2.3 Chapter roster (new names; key sites are canon)

| # | Archmage | Tower | Key site (canon) | Artifact |
|---|---|---|---|---|
| 1 | **Ostentia Gilt**, Archmage of Perpetual Dawn | The Sunspire | The Clocktower | **Radiant Resuscitation of the Eternal Sun** (canon — the Phoenix Paradox) |
| 2 | **Brumble Hogsworth the Vast** | The Bulwark | The Grand Kitchens | **Titan's Majestic Stature** (canon — the Human Doorstop) |
| 3 | **Verdigrise Thornwhistle** | The Hothouse Spire | The Botanical Gardens | **The Thousandfold Bloom of Verdance** (new — see §8) |
| 4 | **Provost Quillan Ashmark** | The Ledger Tower | ___ (maybe the Bursar's Vault, or something like that) | **The All-Seeing Eye of Introspection** (new — see §8) |
| 5–7 | unrobbed bench | — | — | — |

Chapter order is fixed for the prototype (1 → 4). The Grand Kitchens being the **faculty** kitchens — where the Archmages eat lobster while students eat sludge, two floors above the student cafeteria — is a deliberate irony anchor (new).

### 2.4 Pacing targets (new)
| Stage | Target play time |
|---|---|
| Library Intel | 4–6 min |
| Key Extraction | 5–8 min |
| Tower Heist (Act 1) | 10–15 min |
| Intermission Duels | 3–6 min (1–3 duels) |
| Return Trip (Act 3) | 8–12 min |
| Council Trial | 4–6 min |
| **Chapter total** | **~35–50 min** |

---

## 3. Perspective, Controls, Feel

### 3.1 View (new)
* Top-down, slight 3/4 tilt (walls drawn with a front face, Streets of Rogue–style). One floor visible at a time.
* Tile grid: **32 px** tiles, rooms authored as JSON-in-script tile maps. Towers are stacks of floors linked by stairs, ladders, vents, dumbwaiters, and exterior balconies (the canon "balcony entries, sewer vents, servant halls").
* Camera follows with slight lag, clamps to floor bounds, and **pans ahead toward the mouse** a short distance so the player can scout a corridor without walking into it.

### 3.2 Controls (new)

| Input | Action |
|---|---|
| WASD | Move |
| Ctrl (hold) | Sneak — 50% speed, near-silent footsteps |
| Shift (hold) | Sprint — 160% speed, loud footsteps |
| Mouse | Aim spells / tools; cursor scouts camera |
| 1–5 | Select spell from the hotbar |
| Left click | Cast selected spell / use selected tool at cursor |
| Q / R | Cycle thief tool |
| E | Interact (doors, locks, pick up, place, talk) |
| **F** | **Cast equipped artifact** — the canon death-screen prompt is `[Press 'F' to cast Phoenix]`, so F is the artifact key everywhere |
| Tab | Notebook (roasts, comebacks, intel, ledger) |
| Space | Drop / stash carried artifact |

### 3.3 Feel
* Every spell has a visible area and a visible consequence. Grease leaves a glossy sheen. Ice reads blue-white and cracked. Silence draws a faint dome where the sound-ripple particles die at the edge.
* **Noise is drawn**, not hidden: every noise emits an expanding ring in world space, colored by loudness. The player always knows what they just broadcast.
* Guard vision cones are drawn as soft translucent wedges and tint yellow → orange → red as their suspicion rises.

---

## 4. The Stealth Model (new — the pitch names the genre; this is the machinery)

### 4.1 Light
Each tile has a light value `0.0–1.0` baked from authored light sources (torches, windows, glowing runes). Spells and events can modify it (a doused torch drops its radius to 0).
* Player visibility multiplier = `0.25 + 0.75 × light` at the player's tile.
* **Lantern-eye true-sight** (Act 3 countermeasure) forces the multiplier to `1.0` for that guard — shadows stop mattering to them.

### 4.2 Vision
* Guards see in a cone: `VISION_RANGE = 7` tiles, `VISION_HALF_ANGLE = 40°`, blocked by walls and solid objects (raycast on the tile grid, every tick).
* While the player is in-cone and unoccluded, guard **Suspicion** fills at
  `SUSPICION_RATE × visibility × postureMult × (1 − dist/VISION_RANGE × 0.6)` per tick,
  where `postureMult` = sneak `0.6`, walk `1.0`, sprint `1.4`, carrying an artifact `+0.5` (giant relics are hard to hide).
* Suspicion drains at `SUSPICION_DECAY` per tick when not seeing the player.

### 4.3 Noise
Every action emits a noise event `{x, y, radius, kind, t}`. Guards inside the radius (walls halve the effective radius through them) receive it.

| Source | Radius (tiles) |
|---|---|
| Sneak footstep | 0.5 |
| Walk footstep | 2 |
| Sprint footstep | 5 |
| Door (normal / slammed) | 3 / 7 |
| Glass breaking | 8 |
| Object slide (greased, per tick in motion) | 2 |
| Object impact (bust into wall / guard) | 6 |
| Noisemaker (clockwork) | 10 |
| Melee knockout | 4 |
| Ice block shatter | 6 |

* **Silence** zones swallow any noise *originating* inside them (canon combo: break glass inside a Silence right behind a guard's head).
* **Enchanted earmuffs** (Act 3 countermeasure) make a guard ignore all noise events — including the player's sprint footsteps, per canon ("can't hear you sprinting behind them").

### 4.4 Guard states
```
PATROL ──(noise / suspicion ≥ 30)──► CURIOUS ──(walks to stimulus)──► SEARCH
   ▲                                    │                               │
   │                          (suspicion ≥ 100 / sees player clearly)    │
   │                                    ▼                               │
RETURN ◄──(search timer ends)──── ALERT ──► PURSUIT ──(loses player)──► SEARCH
```
* **PATROL** — walks authored waypoints, pauses, looks around.
* **CURIOUS** — stops, turns toward the stimulus, a `?` pops.
* **SEARCH** — walks to the last known stimulus, sweeps nearby tiles for `SEARCH_TIME = 12 s`.
* **ALERT** — `!` pops, shouts (noise radius 6 — nearby guards go CURIOUS toward the shout).
* **PURSUIT** — chases at sprint speed. Catching the player = **Caught** (§4.6).
* **RETURN** — walks back to their post / route. *This is the window the Alibi Engine's Vacuum exploits.*
* **KNOCKED OUT** — down for `KO_TIME = 90 s`, then wakes into SEARCH. A guard who finds a downed guard goes ALERT.
* **INVESTIGATING (incident)** — a special high-priority state for Alibi-Engine incidents: every guard inside `VACUUM_RADIUS` abandons their post and converges on the incident for `VACUUM_TIME`. See §6.

### 4.5 Heat (campus-wide, canon term)
The pitch says to walk into the courtyard "while Heat is low." Heat is the **player's** suspicion level across the whole campus, not a single guard's.
* Range `0–100`. Five bands: **Cold (0–19)**, **Noticed (20–39)**, **Watched (40–59)**, **Wanted (60–79)**, **Hunted (80–100)**.
* Heat rises when the player is **identified** doing something illicit (a guard reaches ALERT on you, a witness sees a spell cast at a lock, you're seen carrying a relic), and when an incident fires with **no alibi** (§6).
* Heat decays slowly in the Hub (`HEAT_DECAY_HUB` per second), not at all inside a tower.
* Effects by band (new): Noticed — prefects glance at you. Watched — a prefect tails you in the Hub. Wanted — tower side-entrances are locked down and guards start each stage in PATROL with +20 suspicion. Hunted — the next stage begins with a prefect sweep; getting caught at Hunted is a full chapter restart instead of a stage restart.

### 4.6 Getting caught (new)
Caught inside a stage = hauled to the Dean's office, a short humiliating cutscene, and **restart the current stage** with Heat set to `max(Heat, 40)`. The stage's Method Ledger (§7.1) is **not** wiped — the Archmage still remembers what you did before you got caught. Your mistakes count.

### 4.7 The Pride Cover-Up, as a rule (canon, made mechanical)
Archmages cannot report a theft without admitting their security failed. So:
* **Stealing an artifact never raises campus Heat by itself.** Only being *witnessed* raises Heat.
* Instead, every theft raises that Archmage's private **Paranoia** and spends it on upgrades for the Return Trip (§7).
* Flavor surface: after each Act 1, the Hub notice board carries an unrelated, overly specific announcement — *"The Sunspire is pleased to announce the acquisition of forty iron bucket helmets for no particular reason."*

---

## 5. Thief Tools & Low-Level Utility Spells

### 5.1 The surface/material system (new — the engine under the canon combos)
Every floor tile carries a **surface state**. Every movable object carries **mass** and **friction**. All spells and tools are verbs on these two things. This is what makes the canon combos fall out of the simulation instead of being scripted.

**Surface states and transitions:**

```
            Douse              Freeze
   DRY ───────────► WET ───────────────► ICE ──(melts, ICE_MELT_TIME)──► WET ──(dries, DRY_TIME)──► DRY
    │                                     ▲
    │ Grease                              │ Freeze on SMOKE+Douse (= wet fog) → ICE BLOCK (solid wall)
    ▼
 GREASED ──(on a HEAT RUNE)──► BURNING SLICK (damages, spreads 1 tile/2s, burns out in 10s)

 HEAT RUNE + Douse  ► STEAM CLOUD (blocks vision 6s)
 HEAT RUNE + Freeze ► COOLED (rune inert for 15s)
```

**Friction by surface** (velocity multiplier per tick on sliding objects and on the player):

| Surface | Object friction | Player effect |
|---|---|---|
| DRY | 0.70 | normal |
| WET | 0.85 | sprint footsteps +1 radius (splashing) |
| GREASED | 0.98 | player slides — momentum carries, can't stop instantly |
| ICE | 0.97 | player slides; sneak still possible |
| BURNING SLICK | 0.98 | damage per tick |

**Objects** (new, small authored set): marble bust (mass 3), suit of armor (mass 5, clanks on impact), bookcart (mass 2, rolls even on DRY), crate (mass 4), potted fern (mass 1, shatters). A sliding object that hits a guard above `KO_SPEED` knocks them out (**environmental KO**, tracked separately from melee KO — this matters for §7).

### 5.2 Spells (canon list, numbers new)
Spells cost **Mana** (`MANA_MAX = 100`, regen `MANA_REGEN` per second, regen paused for 3s after any cast). Low-level cantrips — the point is they are small, cheap, and combinable.

| Hotbar | Spell | Cost | Range | Effect |
|---|---|---|---|---|
| 1 | **Mage Hand** | 10 + 2/s held | 6 tiles | A spectral hand you steer with the mouse. Picks up light objects, drags tripwires, works locks remotely (×1.5 slower than in person), pulls levers, flips pages. Visible as a faint glow to anyone looking at it. |
| 2 | **Grease** | 15 | 5 tiles | 3×3 tiles → GREASED for 60s. |
| 3 | **Gust** | 12 | 6 tiles, cone | Pushes all objects and the player in a cone; impulse scales inversely with mass. Snuffs torches in the cone (light → 0 until relit). Disperses smoke. |
| 4 | **Douse / Freeze** (toggle with second press) | 10 / 14 | 5 tiles | Douse: 3×3 → WET, extinguishes torches and burning slick, turns smoke into wet fog. Freeze: WET → ICE, wet fog → solid ICE BLOCK, cools heat runes. |
| 5 | **Silence / Reveal** (toggle) | 18 / 8 | 4 tiles / self radius 6 | Silence: 2-tile-radius dome for 10s, swallows all noise originating inside. Reveal: 8s, highlights magic tripwires, rune housings, hidden doors, and the edges of anti-magic sap. |

Five slots, seven verbs — Douse/Freeze and Silence/Reveal share slots because canon pairs them in the pitch table.

### 5.3 Thief tools (canon list, numbers new)
Tools are consumables or durable kit, bought in the Hub with **Merit Points** (canon currency; see §10).

| Tool | Type | Use |
|---|---|---|
| **Lockpicks** | durable | Manual lock minigame (§5.4). Can be handed to Mage Hand for remote picking. |
| **Crowbar** | durable | Melee knockout from behind (3-tile noise, counts as **melee KO**). Pries vents and crates. |
| **Wire-snips** | 3 uses | Disables a Revealed rune housing or a physical tripwire. |
| **Glass Cutter** | 2 uses | Silently removes a window pane (a balcony entry without breaking glass). |
| **Smoke Bomb** | consumable | 3×3 smoke cloud, blocks vision for 8s. Douse it for wet fog, Freeze it for an ice-block door seal (canon combo). |
| **Clockwork Noisemaker** | consumable | Set timer 15s–5 min. Fires a radius-10 noise. The Alibi Engine's main plant. |
| **Ice-Rune Charge** (new) | consumable | A rune sealed in ice. Fires a radius-10 noise when the ice melts. Melt time depends on the room: 3 min normal, 45s on a heated floor (same ×0.25 as `ICE_MELT_TIME`), never in a cold room. Untimed but un-tamperable — guards ignore it until it pops. |

### 5.4 Lock minigame (new)
Short and readable. A lock is 3–5 pins; each pin has a sweet spot on a horizontal track. The player holds the pick in a sliding zone and taps E when the pin's glow peaks. A miss jams that pin for 1s and emits a 1-tile noise. Mage Hand picking uses the same minigame with a slower glow cycle (×1.5).
* **Anti-magic sap** (Act 3 countermeasure) on a keyhole: Mage Hand fizzles on contact, sap glows under Reveal, and the lock must be picked in person.
* Archmage **vault locks** are unpickable by design (canon) — they need the chapter's stolen master key from Stage 2.

### 5.5 Canon combos, traced through the system
Every row of the pitch's combo column should work *without special-case code*:

| Canon combo | How the simulation produces it |
|---|---|
| Mage Hand deploys lockpicks / drags tripwires from hiding | Mage Hand can hold any light item; tripwires are light items anchored at one end; dragging moves the trigger line off the walk path. |
| Grease + Gust: slide busts like curling stones into guards | Bust on GREASED has friction 0.98; Gust impulse carries it; collision with a guard above `KO_SPEED` = environmental KO. |
| Smoke + Douse + Freeze = ice-block doorway seal | Smoke → (Douse) wet fog → (Freeze) ICE BLOCK, a solid tile that blocks movement and vision until it melts (`ICE_BLOCK_TIME = 40s`) or is shattered (noise 6). |
| Noisemaker timers; Silence to break glass behind a guard's head | Noise events originating inside a Silence dome are discarded. |
| Reveal highlights magic tripwires; snips disable housings | Reveal sets a `revealed` flag for 8s; snips are only usable on revealed housings (or physical wires, which are always visible). |

---

## 6. The Alibi Engine (canon steps, mechanized)

The five canon beats — **Plant → Position → Witness → Trigger & Check → Vacuum** — run on two data structures.

### 6.1 The Witness Ledger (new)
Every tick, the game records which NPCs can see the player:
```javascript
witnessLog.push({ t, playerTile, witnesses: [ { id, kind, dist } ] })   // ring buffer, last 6 minutes
```
Witness credibility by kind:

| Witness kind | Credibility |
|---|---|
| Student | 1 |
| Duel spectator (each) | 1 |
| Prefect | 2 |
| Faculty / tutor | 2 |
| **Archmage** (in conversation) | 4 |

Canon's three Witness options all map here: forcing eye-contact (one student), starting a public duel (a crowd of spectators), or engaging an Archmage in a lengthy conversation (the single best alibi in the game).

### 6.2 Incidents
When a plant fires (noisemaker or ice-rune), the game creates an **Incident** `{t, tile, building}` and runs the **alibi check**:
```
witnessed = witnessLog entries in [t − ALIBI_WINDOW, t + ALIBI_WINDOW]
            where dist(playerTile, incident.tile) ≥ ALIBI_MIN_DIST
            or player is in a different building
score = max over those entries of Σ credibility of witnesses in that entry
```
* `score ≥ ALIBI_CLEAR (3)` → **Cleared**: Heat −15, a little "✔ ALIBI" stamp in the notebook.
* `0 < score < 3` → **Shaky**: Heat +5. Somebody saw you, but nobody important.
* `score = 0` → **No alibi**: Heat +20, and the tower's Paranoia ledger gets a `noise_distraction` mark (§7).

### 6.3 The Vacuum
Independent of the alibi result, every guard in the incident's building within `VACUUM_RADIUS = 18` tiles enters INVESTIGATING and converges on the incident tile, staying for `VACUUM_TIME = 45s` before RETURN.
* A tower's vault floor is authored so that a good plant on the right floor empties it. That's the clean break-in window.
* Archmages themselves never leave their study for an incident. They send someone. (They are far too important.)

### 6.4 Why it isn't a free win
* Plants have to be placed *inside* the target building, which means a first, shallow infiltration before the real one.
* The Hub has a clock (new): the Archmage's daily schedule. Conversation alibis with an Archmage only exist during their **office hours** window. Long timers (5 min) let you reach a far witness but give guards five minutes to stumble onto the device — a guard who walks within 1 tile of an armed noisemaker in PATROL has a 25%/tick chance to spot and disarm it (and add a `noise_distraction` mark). Ice-runes can't be disarmed but can't be timed either.

---

## 7. Adaptive Security — the Return Trip (canon table, mechanized)

### 7.1 The Method Ledger (new)
Every Act 1 run fills a per-tower ledger:
```javascript
ledger = {
  melee_ko: 0,          // crowbar takedowns
  env_ko: 0,            // busts, armor, falling things
  alerts: 0,            // times any guard reached ALERT
  grease_casts: 0,
  magehand_locks: 0,    // locks picked remotely
  noise_distractions: 0 // noisemakers/ice-runes/thrown objects used to pull guards
}
```

### 7.2 Paranoia purchases
At the end of Act 1, the Archmage "panic-buys" countermeasures. Each canon row has a trigger threshold:

| Canon trigger | Ledger rule (new) | Canon countermeasure |
|---|---|---|
| Knocked out guards with crowbars | `melee_ko ≥ 2` | Iron bucket helmets & neck collars — melee KO fails. |
| Ghosted the level without alerts | `alerts = 0` | Lantern-eye true-sight over-patrol — shadows stop hiding you. |
| Used Grease on floorboards | `grease_casts ≥ 3` | Heated floor runes + spiked cleats — grease becomes burning slick. |
| Used Mage Hand on locks | `magehand_locks ≥ 2` | Anti-magic sap on keyholes — Mage Hand fizzles. |
| Used sound distractions / traps | `noise_distractions ≥ 3` | Enchanted noise-canceling earmuffs — guards deaf to noise, including your sprinting. |

* Every triggered row applies. A sloppy player might face three countermeasures. A ghost faces exactly one — and it's the one that punishes ghosting. **There is no clean way through Act 1 that leaves Act 3 unchanged.** That's the point.
* Patrol routes are also re-authored per countermeasure: each tower floor has a base route set plus a variant route set per countermeasure, so "the layout remaps" without needing procedural generation.

### 7.3 Design rule: every countermeasure has an answer in the kit (new)
The pitch gives each row a "tactical shift." The simulation must make each shift possible:

| Countermeasure | Intended answer(s) |
|---|---|
| Bucket helmets | Environmental KOs still work (helmets stop crowbars, not marble busts). Ice-block seals. |
| Lantern-eye true-sight | Loud chaos instead of shadows — Gust out torches anyway (true-sight ignores darkness but **steam and smoke still block vision**), noisemakers, Vacuum. |
| Heated runes + cleats | Douse a rune → steam cloud (cover). Freeze a rune → inert for 15s. Cleats mean guards don't slip on ice, but **ice blocks still wall them**. Ice-runes melt fast here — a heated floor is the fastest timer in the game. |
| Anti-magic sap | Pick in person (minigame), use Reveal to find which locks are sapped. |
| Earmuffs | Sprint freely behind them. Vision is now the only threat — Smoke, Silence is pointless, light matters double. |

### 7.4 The relic in your arms (new)
* In Act 1 you carry the artifact **out**; in Act 3 you carry it **in**. Same object, same penalty: `+0.5` posture suspicion, 70% move speed, cannot sprint, cannot cast Mage Hand (both hands full).
* Space stashes it on the current tile. Stashing behind a curtain or in a dumbwaiter is how you scout ahead.
* **Act 3 success** = artifact placed back on its pedestal, player escapes the tower, and the Archmage never reached ALERT on the vault floor. If they did, the trial still happens but the Archmage starts it suspicious (§9.3).

---

## 8. Useless Legendary Artifacts

Each chapter's artifact is a giant, absurdly over-engineered vanity spell with zero practical value — and each one has exactly **one** narrow, ridiculous tactical use. Equipped to F.

### Canon
* **Radiant Resuscitation of the Eternal Sun** (The Phoenix Paradox) — summons a roaring spectral phoenix that fully restores health in a pillar of holy fire. **Only castable while dead.** Death-screen prompt: `[Press 'F' to cast Phoenix (Unavailable: You are dead)]`. Use: flex bait in duels.
* **Titan's Majestic Stature** (The Human Doorstop) — expands you 800% with a dramatic bass drop. Move speed 0. You wedge solid against walls and ceiling for the duration. Use: a giant cork in narrow corridors so pursuing guards stall while Mage Hand picks the door behind you.
  * Mechanically (new): occupies a 3×3 footprint, blocks movement and vision through it, lasts `TITAN_TIME = 20s`, and **Mage Hand is castable while titanic** (the hand is magic, not your hands).

### New, proposed (keep, cut, or rename)
* **The Thousandfold Bloom of Verdance** — a sweeping choir and a burst of petals as a single potted plant somewhere on campus grows one leaf. Not the plant in front of you. A random one. *Tactical use:* the leaf growth makes a tiny rustle **somewhere random within 40 tiles** — the least reliable distraction in the game, and occasionally exactly the right one.
* **The All-Seeing Eye of Introspection** — a vast crystal eye opens above you and grants perfect, flawless scrying… of your own face, from the front, for 30 seconds. *Tactical use:* while it's open, you can see your own visibility multiplier as a precise number and every vision cone that currently touches you. It is the most accurate stealth readout in the game, and it is mounted on a glowing eight-foot eyeball over your head (`light = 1.0` in a 3-tile radius).

Rule for any future artifact: **lavish presentation, one absurd catch, one narrow legitimate use, and the use must cost you something.**

---

## 9. Insult Systems — Notebook, Duels, Trial

### 9.1 The Notebook (canon, structured)
Two linked lists:
```javascript
notebook = {
  roasts:     [ { id, text, topic } ],        // things people have said to you
  comebacks:  [ { id, text, answers: [topic, ...] } ],
  insider:    [ { id, text, target: archmageId } ]   // new — see §9.3
}
```
* Every roast carries a **topic** tag (new): `lineage`, `spellcraft`, `fashion`, `intellect`, `diet`, `posture`, `tenure`, `relic`.
* A comeback **answers** one or more topics. Monkey Island rules: the right comeback to a roast's topic wins the exchange; anything else loses it.
* **Sources:** roast snobby students in the library stacks (canon) and the quad; lose a duel exchange to learn the roast *and* its counter-comeback (canon: "logs the roast and its counter-comeback").

### 9.2 Campus Duels (canon intermission)
* Challenge a student in the quad. A duel is **best of 5 exchanges**, alternating who opens.
* **When they open:** they deliver a roast; you pick a comeback from your notebook.
* **When you open:** you **flex your stolen artifact** (F — canon). The spectacle is enormous, the spell is useless, and the student, unimpressed, drops a top-tier academic roast at it (canon). Whether you can answer it decides the exchange. *This is the main way to farm new roasts: the more absurd your relic, the better the material people throw at you.*
* Win: Merit Points + Standing. Lose: you still log what they said. Losing is how you learn.
* A duel is also a **crowd** — every spectator is a credibility-1 witness for the Alibi Engine (§6.1). The ideal Act 1 has a noisemaker ticking in the Sunspire while you lose a duel in the quad in front of twenty people.

### 9.3 Arcane Filibustering — the Council Trial (canon climax)
* Each trial is a debate against that chapter's Archmage in front of the Council. The Archmage has an **Ego** bar (new, 100). You have **Composure** (new, 100).
* **Exchanges:** the Archmage roasts, you comeback. Correct: their Ego −20. Wrong: your Composure −20. Composure 0 = trial lost (retry from the start of the trial; your notebook is unchanged).
* **The Sword Master twist (new):** Archmages don't use student roasts. They use **elevated variants** with different wording on the same topic. A comeback still answers the topic — the player has to recognize what's actually being said under the vocabulary.
* **Visual Punctuation (canon):** once per artifact you own, slam it down on the bench. The room is forced silent: the Archmage's current roast is **cancelled** (no Composure loss) and they lose their next turn. Owning more relics = more punctuation in later trials. You are literally using their stolen property to shut them up.
* **Insider Knowledge (new — the payoff of the Return Trip):** if the Return Trip succeeded, the Archmage, not knowing their relic was ever gone, **flexes it at the trial**. Because you've cast it, you know its catch. You gain one unblockable **insider comeback** (Ego −40) — e.g. against Gilt: *"Wonderful. Do let us know how it works after you die."* This is the reason Act 3 exists in the system, not just the story: returning the relic is what arms your best line.
  * If the Return Trip went loud (Archmage reached ALERT on the vault floor), the Archmage is suspicious, does **not** flex the relic, and the insider comeback is unavailable.
* **Ego outcomes:** Ego 0 = **shattered** → seat won (votes with you to save face). Ego ≤ 40 at trial end = **cracked** → seat abstains. Otherwise the seat votes against.

### 9.4 Standing (new)
A Council-wide reputation number fed by duels won, trials shattered, and very public Visual Punctuation. Seats 5–7 (unrobbed Archmages) vote with you if Standing ≥ their threshold (`40 / 60 / 80`).

### 9.5 The Final Session (new)
* All seven seats sit. Robbed Archmages' votes are locked from their trials.
* A last filibuster against the **full bench**: each unrobbed Archmage takes one roast turn each round. Every Visual Punctuation you have left is available. Every insider line you earned can be fired once more.
* Pass with ≥ 4 votes: **you are seated**, the budget motion carries, and the game ends on a short, quiet scene in the student cafeteria — the first real meal served — no fanfare, just the noise of a room eating something good.

---

## 10. The Campus Hub & Economy (new)

* **Merit Points** (canon term) are the only currency. Earned from duels, library roasts, and "anonymous academic contributions" (the rare intel you sell back to students). Spent on tools.
* **The Fence** is **Mother Ladle**, the head cook of the student cafeteria, who runs a black market out from behind the sludge counter. She has been ladling gruel for thirty years. She does not ask what the tools are for. She knows.
  * Her kitchen staff are the found-family thread: each chapter you clear, one more of them joins the counter crew and unlocks a stock item (Gristle the porter brings ice-rune charges, the twins Pip & Spoon bring smoke bombs, etc.). The cafeteria fills up as the game goes on.
* **The Library steps** host the notice board (Pride Cover-Up announcements, §4.7), office-hours schedules for each Archmage (Alibi timing, §6.4), and the duel ladder.
* **Heat decays in the Hub** only. You can't hide from it in a tower.

---

## 11. Stage Specifications

### 11.1 Library Intel (canon Stage 1)
* Single floor + mezzanine, open stacks, a Restricted Section behind a ward gate.
* **Goal:** steal the logbook that names where the Archmage's master key is kept.
* **Guards:** librarian-wardens (slow, wide 60° cones, very sensitive to noise — the library is *quiet*: all noise radii ×1.5 in here).
* **Social layer:** 3–5 snobby students in the stacks. Talk to them (E) to trade roasts — some will roast you unprompted if you walk past while Heat ≥ Noticed. Each new roast is logged.
* **Teaching function:** introduces light, vision cones, sneak, Mage Hand, and Reveal on the ward gate.

### 11.2 Key Extraction (canon Stage 2)
One per chapter, each teaching one combo. The key is the only way through the Archmage's unpickable vault lock.

| Site | Teaches | Hook |
|---|---|---|
| **The Clocktower** (Ch.1) | Timers, Alibi basics | The gears move on a cycle — platforms and walkways open on the clock's tick. A noisemaker set to go off with the hourly bell is *masked by it*; set it a minute off the bell instead. |
| **The Grand Kitchens** (Ch.2) | Grease + Gust physics | Faculty kitchens, lobster on silver. Floors are already greasy near the fryers. Rolling carts, hanging pots, cooks who scream. The key is in the head chef's walk-in freezer (a cold room — ice-runes never melt here). |
| **The Botanical Gardens** (Ch.3) | Douse / Freeze, wet/ice | Glasshouses, sprinklers on timers, a pond. Douse and Freeze over the pond to make your own bridge. |
| **Ch.4 site** | ___ | ___ maybe something with the Ledger Tower's paperwork. Unfinished on purpose. |

### 11.3 Tower Heist — Act 1 (canon Stage 3)
* **3–4 floors** per tower for the prototype target (Sunspire: 3). Vertical, non-linear: front door (locked, guarded), servant halls (dumbwaiter, laundry chute), sewer vent (crowbar), balcony (Glass Cutter or Mage Hand on the latch).
* **The vault** is on the top or bottom floor. It holds the artifact on a pedestal under a magic tripwire array.
* **The Archmage** is present in their study on one floor. Archmages are not guards — they don't patrol — but walking into their line of sight is an instant ALERT and a large Heat spike. They are the one thing you never fight.
* Exit = leave the tower grounds carrying the relic. The Method Ledger closes.

### 11.4 Return Trip — Act 3 (canon Stage 4)
* Same tower, same floors, rerouted patrols, active countermeasures (§7).
* **Goal:** place the relic back on the pedestal, re-arm (or at least not break) the tripwire array, get out.
* **Timer (new):** the trial is tomorrow morning. The Return Trip runs on a night clock (`RETURN_CLOCK = 12 min`); dawn = guards' shift change, everything resets to day patrols and the Archmage wakes up. Not a fail state, just a very much harder state.

### 11.5 Intermission Duels and Council Trial
See §9.2 and §9.3.

---

## 12. Data Model (new)

Top of the `<script>` block, single source of truth, rendering only reads it — same separation as the other prototypes in this repo.

```javascript
const game = {
  chapter: 1,
  stage: 'library',               // library | key | heist | duels | return | trial | hub | final
  heat: 0,                        // 0–100, campus-wide
  standing: 0,
  merit: 0,
  player: {
    x: 0, y: 0, vx: 0, vy: 0,
    floor: 0,
    posture: 'walk',              // sneak | walk | sprint
    mana: 100,
    hotbar: ['magehand', 'grease', 'gust', 'douse', 'silence'],
    toggles: { douse: 'douse', silence: 'silence' },  // second-press variants
    tools: { lockpicks: true, crowbar: true, snips: 3, glassCutter: 2, smoke: 2, noisemaker: 1, iceRune: 0 },
    carrying: null,               // artifact id or null
    artifacts: [],                // owned relics (for F and Visual Punctuation)
    equippedArtifact: null,
    composure: 100
  },
  map: {
    floors: [ /* { w, h, tiles: Uint8Array, surface: Uint8Array, light: Float32Array, objects: [], guards: [], plants: [] } */ ]
  },
  noiseEvents: [],                // cleared every tick after dispatch
  witnessLog: [],                 // ring buffer, 6 minutes
  incidents: [],
  towers: {
    sunspire: { ledger: { melee_ko: 0, env_ko: 0, alerts: 0, grease_casts: 0, magehand_locks: 0, noise_distractions: 0 },
                countermeasures: [], relicHome: true, returnClean: null }
  },
  notebook: { roasts: [], comebacks: [], insider: [] },
  council: { seats: [ /* { id, name, robbed, ego, vote: 'against' | 'abstain' | 'for', threshold } */ ] }
};
```

Loop: **fixed-timestep accumulator** (`TICK_MS = 50`, 20 Hz sim), `requestAnimationFrame` render, catch-up capped at 10 ticks per frame — identical pattern to `weather/` and `capsize/`.

---

## 13. Starting Constants (new — all untuned)

| Constant | Value | Notes |
|---|---|---|
| `TICK_MS` | 50 | 20 Hz simulation |
| `TILE` | 32 | px |
| `PLAYER_SPEED` | 3.2 tiles/s | sneak ×0.5, sprint ×1.6, carrying ×0.7 |
| `VISION_RANGE` | 7 tiles | |
| `VISION_HALF_ANGLE` | 40° | librarians 60° |
| `SUSPICION_RATE` | 6 /tick | ~0.8s to ALERT at point-blank in full light, walking |
| `SUSPICION_DECAY` | 1.5 /tick | |
| `SEARCH_TIME` | 12 s | |
| `KO_TIME` | 90 s | |
| `KO_SPEED` | 4 tiles/s | sliding object vs. guard |
| `MANA_MAX` / `MANA_REGEN` | 100 / 6 per s | |
| `ICE_MELT_TIME` | 30 s | heated floor ×0.25, cold room never |
| `ICE_BLOCK_TIME` | 40 s | |
| `DRY_TIME` | 20 s | WET → DRY |
| `ALIBI_WINDOW` | 10 s | either side of the incident |
| `ALIBI_MIN_DIST` | 25 tiles | or a different building |
| `ALIBI_CLEAR` | 3 | credibility needed |
| `VACUUM_RADIUS` / `VACUUM_TIME` | 18 tiles / 45 s | |
| `HEAT_DECAY_HUB` | 1 per 2 s | |
| `TITAN_TIME` | 20 s | |
| `RETURN_CLOCK` | 12 min | Act 3 night |

These are guesses picked for "seems right on paper." First job in a prototype is to run the guard/vision/noise code headlessly (the Node-sim approach used for `weather/`) to make sure an un-noticed walk past a patrol in shadow is possible and a sprint past one in light is not.

---

## 14. Art & Audio Direction (new)

* **Palette:** limited and slightly muted — academy stone greys, ink blues, aged-parchment creams, with the magic in saturated accents: grease = amber sheen, ice = pale cyan, silence = violet dome, reveal = green-white outlines, alert = red. The student cafeteria is the only warm-lit room in the game. The faculty kitchens are lit like a cathedral.
* **Characters:** chunky readable sprites, 24×32 on the 32 grid. Archmages are drawn **too big** for their rooms — robes that drag, hats that clip doorframes. Students wear the same uniform with one vanity accessory each.
* **Artifacts:** absurdly over-rendered relative to everything else. The Phoenix gets more particles than any combat effect in the game. That's the joke, and it's never pointed at.
* **Audio:** a library-quiet base mix so noise reads; every noise ring has a matching sound. Artifact casts get full orchestral stings and bass drops. Trials use a courtroom gavel for Visual Punctuation. The ending scene has no music — just cutlery.

---

## 15. Prototype Scope & Build Order (new)

The full game is four chapters. The first single-file prototype should prove the **three systems nobody else in this repo has built**: the surface simulation, the alibi check, and the Act 1 → Act 3 ledger. Chapter 1 vertical slice:

1. **Core sim** — tile map, player movement, sneak/walk/sprint, light, vision cones, noise rings, guard state machine. One test floor. Headless Node pass on the detection math.
2. **Surface system** — Grease, Gust, Douse/Freeze, the bust-curling KO, the ice-block seal. Verify each canon combo row in §5.5 works with no special-casing.
3. **The Sunspire, Act 1** — 3 floors, vault, Archmage Gilt in her study, the Phoenix Paradox on a pedestal. Method Ledger recording.
4. **Hub + Alibi Engine** — quad with students, one duel crowd, Gilt's office hours, the noisemaker, the witness log and alibi check, Vacuum.
5. **The Sunspire, Act 3** — countermeasures applied from the ledger, rerouted patrols, carry-in, night clock.
6. **One duel + one trial** — small notebook (~8 roasts, ~6 comebacks, 1 insider line), Visual Punctuation with the Phoenix, Gilt's Ego bar.

Library Intel and the Clocktower key site are cuttable from the first slice (start the player already holding the logbook and the key) if the six items above run long.

**Verification plan** (matching the approach already used in `weather/` and `capsize/`): headless Node simulation for detection and alibi math; the DOM/canvas mock harness that `new Function()`-evaluates the real `<script>` block; then a headless Playwright Chromium pass for screenshots and zero console errors (Chromium is available at `/opt/pw-browsers/chromium`).

---

## 16. Open Threads

* **Chapter 4's key site and Archmage** are deliberately unfinished (§2.3, §11.2). Ledger Tower / Provost Ashmark is a placeholder name.
* **Artifacts 3 and 4** (§8) are proposals, not canon. Keep the rule, swap the specifics freely.
* **Roast/comeback writing** is the single largest content cost in the game. Chapter 1's set is written (§17.4); the rest is not. Needs ~40 student roasts, ~25 comebacks, ~4 elevated variants per Archmage, and one insider line per relic. This is where the game's voice lives — worth writing by hand, not generating.
* **What happens if you just… don't return a relic?** Currently Act 3 is mandatory. A harder, meaner branch where you keep it — the Archmage can't flex, no insider line, but you hold an extra Visual Punctuation forever — would make the return an actual choice. Unbuilt, undecided.
* **Combat** is intentionally absent. You never win a fight; you only cause them, avoid them, or end them with a marble bust. Worth holding that line.
* **Mother Ladle's crew** (§10) is a found-family thread with one sentence of design behind it. It could carry a lot more — each cook with a reason they've stayed thirty years ladling sludge.

---

## 17. Chapter 1 Slice — As Built

`cafeteria/index.html` is a single file of about 2,900 lines: vanilla canvas plus a little DOM for the panels. It has the same separation as `weather/` and `capsize/`. A fixed 20 Hz simulation (`tick()`) owns all state in one `G` object, and `render()` only reads it. `cafeteria/verify.cjs` drives it headlessly (§17.6).

### 17.1 What's in, what's cut
* **In:**
  * **The Quad hub:** students, 4 snobs, 2 duelists, Mother Ladle's counter, the notice board, and Gilt's pavilion.
  * **The Sunspire:** 3 floors plus grounds. There are 5 ways in: front door, servant door, dumbwaiter, ivy trellis to the balcony, and sewer vent. There are 2 ways up: the main stairs, and the servant stair, reached through a locked pantry door or a hidden library door.
  * **The vault:** ward-lines and a rune housing.
  * **Act 1, Intermission, Act 3 and the Council Trial,** run end to end.
* **Cut, as §15 allowed:**
  * Library Intel and the Clocktower. You start holding the logbook and the master key, and the logbook's contents are in the notebook's *Intel* tab.
  * Chapters 2–4, seats 5–7, the Final Session, and Mother Ladle's crew.
  * Titan's Majestic Stature, which belongs to Chapter 2.

### 17.2 Where the build had to decide something
* **Visual Punctuation vs. the Return Trip.** §9.3 says punctuation uses relics you *own*. §7.4 makes you give the Phoenix back before the trial. **Resolution:** flexing a relic in a duel *attunes* it. At the trial you call down its **phantom**: once per attuned relic, the roast is cancelled and Ego takes −10. (This replaces "loses their next turn", which had no clear effect in a debate.) Keeping a relic instead of returning it, as in §16, would still be the way to get a *second* use.
* **Alibis can't be split across places.** §6.2 scores the best sighting in the ±10 s window. As built, *any* sighting inside the window that puts you near the scene voids the alibi. Without that rule, being seen in the quad nine seconds before an incident still cleared you after you'd run into the tower.
* **Insider Knowledge and the relic comeback stack.** On a clean Return Trip, Gilt's Phoenix flex goes into the trial as her third roast. The insider line deals −40. The ordinary relic comeback also answers it, for −20.
* **The Phoenix is too big for back routes.** While carrying it you can't use the trellis, the dumbwaiter or the vent. You come in and go out by stairs and doors. That turns "how do I get out" into its own puzzle, and Act 3 starts at the gate already carrying it.
* **Guards slip.** A guard without cleats who walks onto grease or ice goes down for 6 s. Gust shoves a guard standing on a slippery tile, and a wall hit at speed knocks them out (an environmental KO). Spiked cleats, from the heat-rune countermeasure, make guards immune to all of this, which is why §7.3's "ice blocks still wall them" matters.
* **Knockouts use momentum, not speed.** `speed × mass ≥ KO_MOMENTUM (12)`. That equals the spec's 4 tiles/s for a bust and holds for heavier objects too. Gust is a fixed impulse, so every object leaves at the same momentum; a bust on grease stays dangerous for about 5 tiles. Ferns shatter instead.
* **How `noise_distractions` counts:**
  * +1 per incident fired (noisemaker or ice-rune).
  * +1 more on a failed alibi, as §6.2 specifies.
  * +1 per player-caused impact, shatter, smashed window or relocated wire that pulls a guard.
  * +1 per noisemaker a guard finds and disarms.
* **What counts as the vault floor going loud:** any ALERT on F2 during Act 3, whether from a guard, Gilt or a tripped ward-line. Any of those voids the clean return. Gilt sleeps at night and wakes for 30 s when a noise reaches her. Dawn is not a fail state: she simply wakes up and stays up.
* **Heat bands, as built:**
  * *Watched* (40+): a prefect tails you in the quad. He is also a credibility-2 witness, which is funny.
  * *Wanted* (60+): when a stage is (re)built, the servant door is locked and guards start at suspicion 20.
  * *Hunted*: nothing extra yet. Getting caught always restarts the stage, never the chapter.
* **Death exists, so the canon prompt can.** Burning slick costs a heart per second, with 3 hearts. At 0 you see the death screen, which shows `[Press 'F' to cast Phoenix (Unavailable: You are dead)]` if you've ever held the Phoenix. Pressing F there says so again.
* **Other numbers:**
  * Office hours run :00–:30. The campus clock moves 0.5 game-minutes per real second and starts at 9:40.
  * Gilt's office-hours monologue (14 lines) does not pause the game, and she reacts if the tower goes off mid-sentence.
  * Mother Ladle counts as a credibility-2 faculty witness inside the cafeteria.
  * The cafeteria is the only warm-lit interior.
* **Sneak is on C, not Ctrl** (§3.2). Ctrl+W, sneaking while walking up, closes the browser tab, and a page can't intercept it.
* **Night routes:** only the vault warden and the entrance-hall guard have Act 3 variants, both sentry posts. True-sight adds three wardens: corridor, library, and servant room.

### 17.3 Constants that differ from §13
| Constant | §13 | As built | Why |
|---|---|---|---|
| `KO_SPEED` | 4 tiles/s | `KO_MOMENTUM = 12` | See §17.2 |
| Exterior ambient light | — | day 0.80 / night 0.13 | Grounds read as night, while daytime approaches stay possible |
| Interior ambient light | — | day 0.14 / night 0.05 (cafeteria 0.62) | |
| `ARCHMAGE_*` | — | range 8, ±50°, suspicion ×3 | "Walking into their sight is an instant ALERT" (§11.3) |

### 17.4 Chapter 1 notebook
* **Comebacks:** six, one per topic: spellcraft, fashion, intellect, lineage, diet, relic.
* **Roasts:** nine.
* **Gilt's trial material:** five elevated variants plus the Phoenix flex.
* **The insider line:** *"Wonderful. Do let us know how it works after you die."*
* **Where comebacks come from:**
  * You start knowing **diet**.
  * Two snobs teach **intellect** and **fashion** when you roast them.
  * Percival's duel teaches **spellcraft**, the hard way.
  * Cressida's duel teaches **lineage**.
  * Flexing the Phoenix in a duel teaches **relic**.

Every trial answer has exactly one source in the slice. When you lose an exchange you "think of the perfect comeback on the walk home", and it's logged.

### 17.5 Playability probe (blind bot, 12–16 randomized runs per route)
A bot walked each route at a fixed pace, with no waiting and no hiding. "Spotted" means some guard reached suspicion 60.

| Route | Spotted | Alert or caught |
|---|---|---|
| Gate → vent / trellis (sneak, day) | 0% | 0% |
| F2 servant stair → vault, **Gilt at office hours** | 0% | 0% |
| F2 servant stair → vault, **Gilt home** | 75% | 58% |
| F2 vault → upper stairs, carrying | 42% | 42% |
| … same, with a noisemaker Vacuum on F1 | **0%** | **0%** |
| F1 gallery end to end, carrying | 75–88% | 67–81% |
| F1 pantry → library → main stairs, carrying | 33% | 0% |
| F0 main stairs → front door → gate, carrying | 100% | 100% |
| F0 main stairs → servant door → gate, carrying | 75% | 50% |

That is the intended shape. The approach is readable. Gilt's study is a timing puzzle set by office hours. Getting the relic *out* is the hard part, and the tools the design built for it work: the Vacuum, the library route, and timing the gallery patrol (or knocking him out). The ground-floor exit is still the hardest leg against a bot that won't wait. That is the first thing to watch in a human playtest.

### 17.6 Verification
`NODE_PATH=$(npm root -g) node cafeteria/verify.cjs [--shots]` runs 35 checks in headless Chromium:
* **Map integrity:** links pair up, every guard waypoint is walkable and reachable across floors, and the vault can be reached from the quad.
* **Real input:** title click, WASD, Tab, E, and the shop.
* **Every combo in the §5.5 table,** plus the heat-rune reactions.
* **The Alibi Engine:** a clean alibi, a missing alibi, the at-scene rule, and the Vacuum crossing floors.
* **Office hours,** and Gilt counting as a credibility-4 witness.
* **Ledger → countermeasures → Act 3:** helmets block the crowbar, earmuffs block noise, runes and sap are placed, and a ward-line in the vault spoils the return.
* **Duels:** learning on a loss, and attunement.
* **The trial:** insider line, punctuation, and a clean shatter.
* **No console errors.**

`--shots` writes screenshots to `cafeteria/shots/`, which git ignores.

### 17.7 Open threads (slice)
* **Balance is untested against a human.** §17.5 is a blind bot. Start with the ground-floor exit and the gallery patrol.
* **Guards path around objects but don't collide with them in motion.** A sliding crate can overlap a walking guard without a KO if it's slow.
* **Things guards ignore:** doors you leave open, an emptied pedestal, and a cut window. Only people, bodies, noise and ward-lines alert them. "The vault door is open" should probably make a guard curious.
* **No hiding bodies, no saving, no minimap,** and no touch controls.
* **Audio is minimal:** synthesized blips that follow noise loudness.
