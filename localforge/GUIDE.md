# localforge — User Guide

Everything you need to launch a run and read the results correctly.

`README.md` explains *how the system works*. This document is about *operating it*.

---

## 1. One-time setup

You already have everything installed. This is just the confirmation sequence.

```bash
cd "/home/user/Game Development/localforge"
node bin/forge.js doctor
```

You want to see `all systems go`. The important lines:

```
OK  [models]  coder: qwen3-coder:30b-64k [completion, tools]
OK  [models]  critic: gemma4:26b [completion, vision, tools, thinking]
OK  [webgl]   context OK — renderer: ANGLE (NVIDIA ... RTX 3090 ...)
```

The critic **must** report `vision`. Without it there is no visual quality gate and the whole loop is pointless. And the WebGL line must name your RTX 3090 — if it says `SwiftShader`, Chrome fell back to software rendering and your frame-rate numbers will be meaningless.

### Enable real parallelism (recommended, one time)

Ollama serialises requests to the same model by default, so `--concurrency 2` gains you very little until you do this:

```bash
sudo systemctl edit ollama
```

Add:

```
[Service]
Environment="OLLAMA_NUM_PARALLEL=2"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
```

Then:

```bash
sudo systemctl restart ollama
```

`OLLAMA_MAX_LOADED_MODELS=2` is the bigger win on your two 3090s: the coder (18GB) and the critic (17GB) each get their own card and stay resident. Without it, every single critique evicts the coder from VRAM and reloads it afterwards — that alone can double the wall clock of a long run.

---

## 2. Prove it works before you trust it

```bash
node bin/forge.js selftest
```

Takes about 3 minutes. It runs one agent end to end: write code → load in real Chrome → measure → critique.

Healthy output looks like this:

```
DEBUG [tool]     write_file main.js (2273 bytes)
WARN  [selftest] browser: 60 fps, 0 console errors, blank=false
INFO  [critic]   selftest: 11/100 tier=programmer_art FAIL — "A low-fidelity,
                 untextured prototype of a particle system test."
```

**A low score here is correct and expected.** The critic is calibrated against shipped commercial titles, and the selftest scene is a deliberately simple particle demo. What you are checking is that all four layers fired:

| line | proves |
|---|---|
| `write_file` | the agent used tools and produced a real file |
| `60 fps, 0 console errors, blank=false` | the browser gate ran and the app genuinely works |
| a critic score + named defects | the vision model judged the actual pixels |

If you see `blank=true` or `files: none`, stop and check `doctor` before starting a real run.

---

## 3. Visual domains — the setting that matters most

Before anything else, know this: **localforge judges different kinds of project by different standards.** The domain it picks decides three things — the code skeleton it scaffolds, the tasks the planner writes, and the rubric the critic scores against.

| domain | for | scaffold you get |
|---|---|---|
| `2d_game` | RPG, puzzle, adventure, action, strategy, platformer, roguelike | 2D canvas: fixed-timestep loop, camera, layers, sprite helper |
| `2_5d` | isometric, axonometric, parallax-layered | as above, with isometric projection and depth sorting |
| `3d_realtime` | true 3D with a camera in a 3D world | three.js: renderer, lights, shadows, tone mapping |
| `ui_app` | dashboards, tools, sites | plain DOM |

It's inferred from your prompt, and the inference is deliberately biased toward 2D — the word "game" on its own resolves to `2d_game`, never 3D. You'll see the choice echoed at startup:

```
judged as   : 2d_game
```

Force it when you need to:

```bash
node bin/forge.js run "an isometric colony sim" --workspace ./colony --domain 2_5d
```

### Why this matters more than it sounds

The rubrics don't just weight things differently — they carry explicit rules about what is **not** a defect. The 2D rubric is told, in as many words, not to penalise a game for lacking 3D lighting, shadows, ambient occlusion, PBR materials or post-processing.

That's not cosmetic. The critic's fixes feed directly into the next coder brief, so a mis-set domain doesn't just produce a wrong score — it actively drives your game in the wrong direction. Judged as `3d_realtime`, a perfectly good tile RPG gets told to *"implement a directional light source with shadow mapping"* and *"introduce 3D geometry"*. Judged as `2d_game`, the same screenshot gets *"implement a distinct sprite with high-contrast outlines and unique shape language"*.

**If the startup banner shows the wrong domain, stop and restart with `--domain`.** It's the one setting worth checking every time.

### The 2D scaffold you're building on

For `2d_game` and `2_5d`, agents are told to build on a global `game` object rather than reinvent it — this keeps 20 tasks from producing 20 competing render loops:

| API | purpose |
|---|---|
| `game.addLayer(z, name, draw)` | register a render layer, drawn in ascending z |
| `game.updaters.push({name, update})` | fixed-timestep update; `dt` is always 1/60 |
| `game.worldToScreen(x, y)` | world → screen (isometric projection in `2_5d`) |
| `game.makeSprite(w, h, paint)` | pre-render art to an offscreen canvas, once |
| `game.input.keys` / `.mouse` | live input state |

The fixed timestep is deliberate: it gives you deterministic physics and consistent game feel, which is exactly what local models get wrong when left to invent a loop themselves.

---

## 4. Launching a run

### The short form

```bash
node bin/forge.js run "A 2D top-down pixel-art RPG with a village, NPCs, real-time combat and a hearts HUD" \
  --workspace ./rpg
```

### The realistic form (long prompts belong in a file)

```bash
node bin/forge.js run --file examples/rpg-goal.txt --workspace ./rpg
```

Two example goals ship with it:

- `examples/rpg-goal.txt` — a 2D top-down RPG. **Start here.** It's written the way prompts for this system should be written (see section 5).
- `examples/fps-goal.txt` — your original Call of Duty prompt verbatim, if you ever want to exercise the 3D path.

### Run it detached so a closed terminal doesn't kill it

```bash
nohup node bin/forge.js run --file examples/rpg-goal.txt --workspace ./rpg > rpg.log 2>&1 &
tail -f rpg.log
```

Ctrl-C on the `tail` is safe — it only detaches your view, not the run.

---

## 5. Writing a good goal, and choosing your settings

### How to write the prompt

The planner turns your prompt into 12–26 tasks. Vague prompts produce vague tasks, and vague tasks are what a 30B model fails at. `examples/rpg-goal.txt` is the template — the pattern is:

- **Name concrete systems**, not vibes. "Transition tiles between terrain types, no hard grid seams" beats "beautiful world".
- **Say what the player does.** Movement, collision, camera behaviour, combat verbs, UI screens.
- **State the art direction explicitly.** Palette, readability, style. The critic scores against your stated bar, so give it one.
- **Ask for game feel by name.** Hit flash, knockback, damage numbers, screen shake, particles, idle animation. These are small, well-specified tasks — exactly what local models do well, and exactly what separates a prototype from something that feels good.
- **Don't ask for content volume.** "100 levels" wastes the whole run. Ask for one excellent area.

### Settings

**First real run — see the whole pipeline in ~1 hour**

```bash
node bin/forge.js run --file examples/rpg-goal.txt --workspace ./rpg \
  --rounds 1 --critique-rounds 2 --pass-score 65 --wall-clock 60
```

**Overnight, quality-first**

```bash
node bin/forge.js run --file examples/rpg-goal.txt --workspace ./rpg \
  --rounds 3 --critique-rounds 6 --concurrency 2
```

**Debugging a specific behaviour — watch the browser live**

```bash
node bin/forge.js run "..." --workspace ./tmp --concurrency 1 --headed
```

### What each dial actually does

| flag | default | raise it when | cost |
|---|---|---|---|
| `--critique-rounds` | 6 | tasks are being accepted too ugly | linear time per task |
| `--rounds` | 3 | the whole build needs more passes | multiplies total time |
| `--pass-score` | 82 | you want a stricter bar | may never pass; wastes rounds |
| `--concurrency` | 2 | you enabled `OLLAMA_NUM_PARALLEL` | more file collisions |
| `--wall-clock` | off | you need it to stop by morning | hard cutoff mid-task |

**Be careful with `--pass-score`.** 82 is already demanding for a local model. Setting it to 95 means tasks burn all six rounds, fail anyway, and get accepted below the bar — you spend 3× the time for the same result. If nothing is passing, *lower* it to 70 and let the outer refinement rounds do the improving instead.

---

## 6. Watching a run

In a second terminal:

```bash
node bin/forge.js status --workspace ./rpg
```

```
tasks   : 7 done / 9 pending / 1 parked / 17 total
  ✓ scene-skeleton           completed   88/100
  ✓ weapon-viewmodel         completed   84/100
  ✗ volumetric-fog           parked
  ▸ muzzle-flash             running
  · hud-ammo-counter         pending
```

### Reading the live log

| line | meaning | do something? |
|---|---|---|
| `round 2 rejected at 61/100` | the loop is working as designed | no — this is the point |
| `rejected empty finish` | agent claimed done without writing; harness caught it | no |
| `salvaged write_file(...) from prose` | model pasted code into chat; harness rescued it | no |
| `repetition detected, forcing re-plan` | agent was stuck in a cycle; harness broke it | no |
| `BLANK FRAME` | renderer is broken, repair round incoming | only if it persists 3+ rounds |
| `parking "<task>" after 3 attempts` | task gave up; run continues without it | check it in the report |
| `deadlock: releasing "<task>"` | dependency knot broken automatically | no |

The healthy rhythm is roughly **3–8 minutes per task round**. If a single task sits for 20+ minutes, check `nvidia-smi` — the usual cause is model thrashing between the two GPUs, which `OLLAMA_MAX_LOADED_MODELS=2` fixes.

---

## 7. Stopping, resuming, restarting

State is saved after **every** transition, so interruption is cheap.

```bash
# stop:      Ctrl-C, or kill the process
# continue exactly where it stopped:
node bin/forge.js resume --workspace ./rpg

# start over from scratch, discarding history:
node bin/forge.js run --file examples/fps-goal.txt --workspace ./rpg --fresh
```

Resume re-queues anything that was mid-flight when you stopped. Completed tasks are never redone.

---

## 8. Blind side-by-side against reference art

This needs one manual step: **the system has no reference images until you give it some.**

```bash
mkdir -p ./rpg/references
# drop 2-5 screenshots of games you're aiming at, e.g. stardew.png, ff6.png
```

Use actual gameplay frames, not cinematics or key art — you want to compare like with like. Pick references in the same domain as your project; comparing a 2D RPG against a 3D shooter tells you nothing.

At the end of the run the critic is shown your build and one reference at a time, **without being told which is which**, with the presentation order flipped each round so position bias cancels out. The comparison uses the same domain rubric as the critique, so a 2D game is compared on 2D craft.

Run it any time on demand:

```bash
node bin/forge.js compare ./rpg/.forge/screenshots/final.png ./rpg/references/stardew.png \
  --domain 2d_game --rounds 5
```

```
BLIND A/B: won 1/5 — reference preferred
  round 1: REFERENCE (decisive) — Image B has cohesive palette discipline,
           varied tile detail and clear character silhouettes …
Gaps to close:
  - tilemap repeats one grass tile with no variation
  - player sprite has no outline, reads as background noise
```

**Expect to lose the early rounds decisively.** That is the measurement working. Those "gaps to close" are the most valuable output the system produces — they feed the next refinement round automatically, and they tell you exactly where to point a follow-up run.

---

## 9. Looking at the results

```bash
# play it
npx serve ./rpg/app

# the full report: scores, defects, blind results
cat ./rpg/.forge/reports/report.md

# every frame every critique was based on, in order
ls ./rpg/.forge/screenshots/
```

The screenshots directory is the best debugging tool in the system. Files are named `<task-id>-r<round>.png`, so flipping through `muzzle-flash-r1.png` → `-r2.png` → `-r3.png` shows you exactly what each repair round changed. If the loop is spinning without improving, you will see it there immediately.

### Standalone tools you'll keep using

These work on anything, unrelated to a run — including your other projects in this repo:

```bash
# harsh critique of any screenshot
node bin/forge.js judge ~/screenshot.png "a moody dungeon crawler"

# screenshot + health report for any local app or URL
node bin/forge.js shoot ./wayfarer --out wayfarer.png
node bin/forge.js shoot http://localhost:3000
```

`forge judge` on your own Wayfarer screenshots is a genuinely useful art-direction pass on its own.

---

## 10. Troubleshooting

**Everything fails with `0 files touched`**
The coder model isn't tool-calling. Confirm `doctor` shows `tools` for the coder, then try `--coder qwen3-coder:30b` (the non-64k build).

**Every task fails with console errors**
Look at the actual error in the log. If it's a 404 for an asset the model invented, that's expected in early rounds and the repair brief will fix it — agents cannot download art, so all textures must be generated in code.

**Tasks pass but the result looks bad**
Your `--pass-score` is too low, or the tasks were planned too vaguely. Check `report.md` for what the critic said it accepted. Re-run with `--rounds 3` to let gap analysis add sharper tasks.

**Nothing ever passes, everything hits `completed_below_bar`**
`--pass-score` is too high for what a 30B model produces in this domain. Drop to 70.

**Run is unbearably slow**
Check `OLLAMA_MAX_LOADED_MODELS=2` is set (section 1). Then `nvidia-smi` during a run — you should see both cards busy, not one card repeatedly loading and unloading.

**Out of VRAM**
Lower `FORGE_CTX_CODER` (default 48k):

```bash
FORGE_CTX_CODER=24576 node bin/forge.js run ...
```

**Two agents fighting over the same file**
Drop to `--concurrency 1`. Tasks declare their files and the scheduler locks them, but an agent that wanders outside its declared set can still collide with a peer.

---

## 11. What to expect, honestly

A 30B local model is not Opus. It writes solid, working code in small well-specified chunks; it does not invent novel architecture. What this harness adds is decomposition, relentless objective verification, and a critic that refuses to accept placeholder art.

**2D is where this system is strongest, and that's genuinely lucky for you.** A tile RPG, a puzzle game, a top-down action game — these decompose into exactly the kind of small, well-specified, individually-verifiable tasks a local model handles well. Procedural sprite generation on a canvas is far more tractable than convincing PBR materials. The gap between "local model output" and "shipped commercial quality" is much narrower in 2D than in 3D.

From `examples/rpg-goal.txt`, a realistic overnight outcome is a **playable tile RPG** — a walkable world with varied terrain and transition tiles, animated 4-direction player movement with collision, a following camera, a few NPCs with dialogue, real-time combat with hit flash and knockback and damage numbers, and a hearts HUD — where every piece was screenshot-verified at 60fps with a clean console. Some tasks will be parked. Early blind comparisons against Stardew Valley will lose.

That is a good result, and the report tells you the truth about it either way. The system is built so its failures are visible rather than hidden behind a model's cheerful summary.

### Where it will still disappoint you

- **Cohesive art direction across 20 independently-built tasks.** Each agent sees its own task, so styles drift. The outer refinement rounds partly correct this; a final "unify the palette across every sprite" run helps more.
- **Anything needing real level design.** It will build the systems; hand-authoring a world that's fun to move through is still yours.
- **Long-range game design.** It implements what you specify. It does not decide what would make your game good.
