# Game Specification: The Weather Balance Engine

> **Status:** A working single-file prototype exists at `weather/index.html`. Open it directly in a browser — no build step, no server required. This document has been updated to describe what was actually built (constants, mechanics, and visuals sometimes diverged from the original design as they got tuned/iterated), plus open threads for continuing the work.

## 1. Overview & System Design
* **Concept:** A systemic, resource-efficient simulation game where the player serves as a weather deity maintaining stability over a small isolated island ecosystem. Four local human factions occupy separate quadrants of the environment, each continuously praying to steer the microclimate toward their preferred extreme.
* **Core Philosophy:** **Control the Wobble, Do Not Stop It.** Complete, static equilibrium is designed to be impossible. The game loops through dynamic oscillations; survival is measured by modulating demographic sizes to buffer chaotic shifts.
* **Target Execution Environment:** Single-file HTML5 canvas + vanilla JS, zero dependencies. Confirmed working in this form.

---

## 2. Mathematical Vector Core ("The Wobble Engine")
The environment is governed by a 2D coordinate system $(x, y)$ tracking the global climate deviation. The coordinate center $(0,0)$ indicates perfect, calm balance.

```
                   +Y : SUNSHINE (Drought)
                        ^
                        |
-X : BLIZZARD (Snow) <--+--> +X : DELUGE (Rain)
                        |
                        v
                   -Y : MAELSTROM (Storm)
```

### Motion Equations
Every simulation tick, the new position vector $\vec{W}_{t+1}$ is computed via the sum of force attraction weights exerted by the factions, mixed with damping and environmental brownian noise:

$$\vec{W}_{t+1} = \vec{W}_t + \sum_{i=1}^{4} \left( P_i \cdot I_i \cdot \vec{D}_i \right) \cdot k_{force} - \gamma \vec{W}_t + \vec{\mathcal{N}}$$

Where:
* $P_i$: Population count of faction $i$.
* $I_i$: Base prayer intensity/weight coefficient of faction $i$.
* $\vec{D}_i$: Direction unit vector assigned to faction $i$ (Sunshine $(0,1)$, Deluge $(1,0)$, Maelstrom $(0,-1)$, Blizzard $(-1,0)$).
* $k_{force}$: A scaling constant (`FORCE_SCALE`) needed because raw `pop * weight` sums (hundreds) would otherwise dwarf the threshold. **Not in the original spec** — added during implementation once it became clear the raw equation needed a knob to keep the vector in a sane numeric range relative to `threshold`.
* $\gamma$: Global climate restorative friction/inertia factor, pulling variables slowly back inward.
* $\vec{\mathcal{N}}$: A randomized Gaussian noise vector (Box-Muller transform), independent per axis per tick.

### Tuned constants (as shipped, `index.html`)
The original spec's example values (`γ = 0.05`, small implicit noise) produced a wobble that stayed within ~4% of the threshold radius — visually static. These were retuned by simulating the physics headlessly in Node and checking the steady-state distribution before settling on:

| Constant | Value | Notes |
|---|---|---|
| `FORCE_SCALE` | `0.0045` | scales `Σ(pop·weight·dir)` into vector-space units |
| `NOISE_STD` | `1.1` | Gaussian std-dev per axis per tick |
| `BASE_GAMMA` | `0.05` | restorative friction (matches original spec) |
| `threshold` | `15.0` | matches original spec |
| `TICK_MS` | `150` | one simulation tick per 150ms of real time at 1x speed |

Rule of thumb if retuning further: for an Ornstein-Uhlenbeck-like process, steady-state std ≈ `NOISE_STD / sqrt(2·γ)`. Solve for the `NOISE_STD` that gives you the fraction of `threshold` you want the "resting" wobble to occupy before you even factor in the growth feedback loops below.

---

## 3. Dynamic Feedback Loops & Asymmetry
To ensure intrinsic instability, demographic growth functions change based on the *current position* of the weather vector:
* **The Deluge Faction (Rain)** multiplies when the weather points toward $+Y$ (Sunshine), as intense heat accelerates their devotion to water: `rain.pop *= (1 + RAIN_GROWTH * min(W.y/threshold, 3))` when `W.y > 0`.
* **The Sunshine Faction** multiplies when the weather slides into $-X$ (Blizzard), desperate for warmth: `sun.pop *= (1 + SUN_GROWTH * min(-W.x/threshold, 3))` when `W.x < 0`.
* **Storm and Snow** were left without a triggered growth loop (matching the spec's implication that the asymmetry is the point — only two of four factions runaway). They instead get a constant tiny `BASELINE_GROWTH` every tick, as does whichever of Rain/Sun is *not* currently triggered, so no faction is ever fully static.
* Tuned values: `RAIN_GROWTH = SUN_GROWTH = 0.020`, `BASELINE_GROWTH = 0.0012`.
* Verified behavior (headless simulation, no player input): early wobble sits around ~30% of the threshold radius, climbing as population imbalance compounds; unmanaged runs reach cataclysm in roughly 400 ticks (~1 minute at 1x speed). A naive periodic-rebalancing strategy roughly doubles that survival time but does not prevent the eventual cataclysm — the growth is exponential, so any fixed strategy is eventually outpaced. This matches "control the wobble, do not stop it": skilled play delays the end, it doesn't cancel it.

---

## 4. System Implementation & Constraints
The core engine object, as actually implemented (`index.html`, top of the `<script>` block):

```javascript
const climateEngine = {
  vector: { x: 0.0, y: 0.0 },
  threshold: 15.0,
  factions: {
    sun:   { pop: 50, weight: 1.0, dir: { x: 0,  y: 1  } },
    rain:  { pop: 50, weight: 1.1, dir: { x: 1,  y: 0  } },
    storm: { pop: 50, weight: 0.9, dir: { x: 0,  y: -1 } },
    snow:  { pop: 50, weight: 1.0, dir: { x: -1, y: 0  } }
  },
  devotion: 0.0
};
```

The simulation runs on a **fixed-timestep accumulator loop** decoupled from render rate (`requestAnimationFrame` drives rendering every frame; `tick()` only fires when enough real time has accumulated, capped at 20 catch-up ticks per frame to avoid a spiral of death after e.g. a backgrounded tab). Rendering reads the live `climateEngine` state each frame; it does not own any simulation logic.

### Cataclysm / prestige
Unchanged from the original design: crossing `|W| ≥ threshold` freezes the sim, shows a summary banner, and grants a permanent upgrade scaled to `floor(ticksSurvived / 50)` points — `+0.0015 friction` and `-0.02 noise` per point, applied to `BASE_GAMMA`/`NOISE_STD` for the next generation via a `permanent` bonus object. "Begin Next Generation" resets vector, devotion, and populations to the 50/50/50/50 baseline but keeps the permanent bonuses.

---

## 5. Player Gameplay Loop & UI Actions — **diverged significantly from the original spec**

### What changed and why
The original spec called for a **radar plot** (abstract dot-on-a-grid) and an **exact demographic toggle** (`Convert 10 [A] to [B]`, precise source/target/amount). Both were built first, then reworked based on direct feedback during playtesting:

1. *"it doesn't show weather, it shows a squiggly line moving around"* → replaced the radar/trail view with an actual **2.5D tilted island scene**.
2. *"it kept too close to stable"* → retuned the physics constants (see §2).
3. *"let's try a different converting method, something sloppier, less precise"* → replaced the exact convert UI with a **Rally** mechanic (delayed, randomized, imprecise).
4. *"can we move it so you just click on the faction population bar instead"* → removed the separate Rally button grid; clicking a faction's card in the population panel **is** the rally action now.

### The Island Scene (canvas rendering, replaces "The Radar Array")
* An organic, non-perfect-ellipse coastline: a base ellipse (`islandRx = 196, islandRy = 132` — a gentler squash than earlier drafts, i.e. a shallower camera tilt) is perturbed by summed sine harmonics (`outlineFactors`, seeded deterministically) and traced as a smoothed blob via `quadraticCurveTo` through per-point midpoints.
* A sand "beach" ring between the ocean and the inset grass/terrain fill.
* Deterministic (seeded-random, generated once at boot) texture: tree icons, coastal rocks, drought cracks, and per-faction settlement "hut" clusters placed by polar coordinates matching the compass mapping (N=Sunshine, E=Deluge, S=Maelstrom, W=Blizzard). Settlement hut count scales with that faction's current population.
* **Weather is global, not per-quadrant** — matches the spec's "global climate deviation" framing. The current vector is converted into four independent weights (`sunW, rainW, stormW, snowW`, each `clamp(component, 0, threshold) / threshold`), and every visual effect below reads from those weights, blended across the whole island, not localized to one quadrant.
* Four elemental effects, one per faction/direction:
  * **Rain** (Deluge, +X) — falling-drop particle pool.
  * **Snow** (Blizzard, -X) — drifting flake particle pool.
  * **Gusts** (Maelstrom, -Y) — drifting storm clouds + wind-streak particles + occasional lightning bolt/flash + a subtle camera-shake on the whole scene when `stormW` is high.
  * **Bright light** (Sunshine, +Y) — an additive-blended (`globalCompositeOperation = 'lighter'`) glow/bloom overlay plus rotating rays, replacing an earlier, too-subtle "small sun icon" treatment.
* Terrain color itself blends toward parched/wet/stormy/snow-covered based on the same four weights (`blendTerrainColor`).
* A small **compass inset** (bottom-right corner, not shaken by gusts) retains the precise numeric readout (x/y/magnitude dot on a mini dial with a short trail) — kept because precision feedback was still useful even after the main view went impressionistic.
* A pulsing red ring traces the coastline once `|W|/threshold > 0.6`.

### Demographic Modulation — the Rally mechanic (replaces `Convert 10 [A] to [B]`)
The player no longer picks an exact source/target/amount. Instead:
* Each faction's card in the population panel (`#factionList`) **is** the button — click it to rally toward that faction. (There is no separate button grid; this was explicitly requested after an interim version had both a card display and a redundant button grid below it.)
* Clicking costs `RALLY_COST = 8` devotion immediately, and queues an order with `RALLY_LAG_TICKS = 3` — the effect does **not** land immediately.
* On resolution (3 ticks later), the order pulls a randomized total between `RALLY_MIN = 8` and `RALLY_MAX = 20` from the *other three* factions, split by random per-source weights (not evenly, not player-chosen), with `RALLY_MIN_LEFT = 5` as a floor no source faction is drained below. The actual amount added to the target can therefore be less than requested if sources are already low.
* Multiple orders can be queued and pending simultaneously; a small list under the population panel shows each with a live tick countdown.
* Cards visually disable (`.disabled` class, dimmed + `cursor: not-allowed`) whenever `devotion < RALLY_COST` or the run has crashed.
* Devotion accrues passively at `DEVOTION_RATE = 0.6` per tick — no other source or sink exists yet.

### The Cataclysm (Prestige Trigger) — unchanged from original spec
If $\sqrt{x^2+y^2} \ge \text{threshold}$, the run ends, the banner shows ticks survived and points earned, and "Begin Next Generation" resets the island with permanent stability bonuses carried forward. See §4.

---

## 6. Verification approach used so far
No browser automation tool was available during development. Verification was done by:
1. Headless simulation of the physics-only math in plain Node (no DOM) to tune constants and sanity-check long-run behavior (no NaNs, expected crash timing, growth asymmetry visible).
2. A hand-rolled DOM/canvas mock in Node that `new Function()`-evaluates the actual `<script>` contents from `index.html` against fake `document`/`canvas`/`requestAnimationFrame` objects, driving the real fixed-timestep loop for hundreds to thousands of simulated frames. This caught real bugs (e.g., `innerHTML`-created child elements not being registered in the mock, `classList.add` needing to be non-trivial) and confirmed every render function executes without throwing, that the cataclysm/reset lifecycle works, and that Rally orders resolve with the expected randomized/imprecise math.
3. **Not yet done:** an actual visual/manual check in a real browser (open `weather/index.html` directly). Worth doing before further iteration — the harness can confirm code paths execute and numbers move correctly, but not whether the rain/snow/gusts/bright-light effects *read* well at a glance, whether particle counts/sizes feel right, or whether the organic island shape looks convincing. If Claude in Chrome (or similar) is connected in a future session, prefer that for a real screenshot pass.

---

## 7. Open threads / ideas for continuing
Nothing here is committed to — just things that came up but weren't asked for yet:
* **Devotion economy is currently one-note**: it only accrues passively and only spends on Rally orders. Could introduce other sinks (e.g., a "dampen noise for N ticks" ability) or other sources (e.g., small reward for surviving milestones) if the single-resource loop feels thin in play.
* **No sound design** — the prototype is silent. Lightning flashes and gusts in particular might benefit from audio cues.
* **No difficulty/generation scaling beyond the permanent friction/noise bonuses** — later generations get easier indefinitely; consider whether there should be a counter-pressure (e.g., faction weights or threshold also shifting) to keep runs interesting long-term.
* **Mobile/touch and accessibility** have not been considered — canvas click targets, hover-dependent affordances (`.faction-card:hover`), and small text sizes would need a pass if this needs to run beyond a desktop browser prototype.
* **Balance is tuned around one playstyle** (headless simulation with a dumb periodic-rebalance bot). A real human playtester may find it too punishing or too easy — the constants table in §2 and §3 is the place to adjust first.
