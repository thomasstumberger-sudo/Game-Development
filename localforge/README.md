# localforge

An autonomous multi-agent build system that runs entirely on your own hardware. You give it one ambitious prompt; it plans the work, fans out parallel coding agents, runs the result in a real browser, has a vision model tear the screenshots apart, and loops until the work clears a quality bar — or until it honestly reports that it couldn't.

Nothing leaves the machine. No API keys, no per-token cost, no rate limits.

---

## What it actually does

```
  your prompt
      │
      ▼
  ┌─────────┐   reads directives ("fan out", "/loop", "blind compare")
  │ PLANNER │   and decomposes into a dependency-ordered task graph
  └────┬────┘
       │
       ▼
  ┌──────────────────────────────────────────────────┐
  │  SCHEDULER — N workers in parallel, file-locked   │
  └───┬──────────────────┬──────────────────┬─────────┘
      ▼                  ▼                  ▼
  ┌────────┐         ┌────────┐         ┌────────┐
  │ CODER  │         │ CODER  │         │ CODER  │   qwen3-coder, tool-calling
  └───┬────┘         └───┬────┘         └───┬────┘
      │                  │                  │
      ▼                  ▼                  ▼
  ┌──────────────────────────────────────────────────┐
  │  OBJECTIVE GATE — real headless Chrome on the GPU │
  │  syntax · console errors · WebGL · fps · blank?   │
  └──────────────────────┬───────────────────────────┘
                         │ (only if it actually runs)
                         ▼
  ┌──────────────────────────────────────────────────┐
  │  VISION CRITIC — gemma4:26b grades the screenshot │
  │  6 weighted axes · must name defects + fixes      │
  └──────────────────────┬───────────────────────────┘
                         │
              PASS ──────┴────── FAIL → repair brief → new agent, clean context
                                          (this is the /loop)
```

When every task is done, the planner performs a **gap analysis** against the original goal and may queue another round. At the end, if you supplied reference images, the critic runs a genuine **blind A/B test** against them.

---

## Why it produces usable results from a 30B model

Ambitious prompts don't fail locally because the model is weak. They fail because nobody enforced structure. Six things do the heavy lifting here:

**1. Nothing is judged until it runs.** Every task is verified in real headless Chrome on your GPU before any opinion is collected: uncaught errors, console errors, failed requests, WebGL context health, a measured frame rate, and a blank-frame test that samples the canvas. A model cannot talk its way past this gate.

**2. The critic's score is computed in code.** The vision model scores six axes; the weighted total is calculated by `critic.js`, not accepted from the model. It can't hand-wave a number. Objective failures (blank screen, console errors, sub-30fps) force a FAIL regardless of what the critic thought.

**3. The critic is required to find defects.** Its system prompt fixes hard ceilings — grey untextured scene scores below 30 on materials, flat lighting below 35 — and demands a concrete technical fix for every defect. Those fixes become the next agent's brief.

**4. Failure rounds get a clean context.** Re-using a failed attempt's transcript makes models defend their earlier choices. Each repair round spawns a fresh agent whose entire brief is the measured failures.

**5. Structured output everywhere.** Planning, critique and comparison all constrain sampling to a JSON schema via Ollama's `format` parameter. This removes an entire category of parse failures that otherwise dominate local agent runs.

**6. The critic is domain-aware.** Rubrics live in `src/rubrics.js`, one per visual domain (`2d_game`, `2_5d`, `3d_realtime`, `ui_app`). Each carries weighted axes, calibration rules, *and explicit rules about what is not a defect* — the 2D rubric is told not to penalise a game for lacking 3D lighting, shadows or PBR materials. This matters because critic feedback becomes the next coder brief: a mis-set domain doesn't just misscore, it drives the build in the wrong direction. The domain also selects the scaffold and shapes the planner's tasks.

**7. It assumes the model will misbehave.** Agents that reply in prose get escalating nudges and, if they pasted a whole file into chat, that file is extracted and written for them. Agents that claim completion without touching a file are rejected. Agents that repeat a call four times are forced to re-plan. Context is trimmed from the middle while pinning the task statement.

---

## Requirements

| | |
|---|---|
| Ollama | running, with the models below |
| Node | 20+ |
| Chrome/Chromium | for headless verification |
| GPU | strongly recommended; CPU works but is painfully slow |

Models (override any of them with flags or env vars):

```bash
ollama pull qwen3-coder:30b     # coder + planner — needs tool-calling
ollama pull gemma4:26b          # critic — MUST have the vision capability
ollama pull gemma3:12b          # fast chores
```

The critic model **must** support vision. `forge doctor` verifies this explicitly.

---

## Quick start

```bash
cd localforge
npm install

node bin/forge.js doctor       # verifies models, capabilities, WebGL, GPU
node bin/forge.js selftest     # proves the whole pipeline in a few minutes

node bin/forge.js run "Build a first-person shooter in ThreeJS ..." --workspace ./build
```

Watch it work, then:

```bash
node bin/forge.js status --workspace ./build     # per-task progress and scores
npx serve ./build/app                            # play the result
```

Artifacts land in the workspace:

```
build/
├── app/                     the actual project the agents built
├── references/              drop comparison screenshots here
└── .forge/
    ├── state.json           full run state — resumable
    ├── screenshots/         every frame every critique was based on
    ├── reports/report.md    final report: scores, defects, blind results
    └── logs/*.jsonl         structured log of every model call
```

---

## Commands

| command | purpose |
|---|---|
| `forge run "<goal>"` | start a build (`--file goal.txt` to read from a file) |
| `forge resume` | continue an interrupted run from `state.json` |
| `forge status` | per-task status and visual scores |
| `forge doctor` | check models, capabilities, Chrome, WebGL, GPU |
| `forge selftest` | end-to-end proof: agent → browser → critic |
| `forge shoot <url\|dir>` | screenshot + health report for anything |
| `forge judge <image>` | run the harsh critic on a single image |
| `forge compare <ours> <ref>` | blind A/B two images |

The last three work standalone — `forge judge` on a screenshot of your own game is useful on its own.

### Options

| flag | default | meaning |
|---|---|---|
| `--workspace <dir>` | `./build` | where the build lives |
| `--concurrency <n>` | 2 | parallel worker agents |
| `--critique-rounds <n>` | 6 | max fix cycles per task (the `/loop` depth) |
| `--rounds <n>` | 3 | outer refinement passes |
| `--pass-score <0-100>` | 82 | visual bar a task must clear |
| `--wall-clock <min>` | off | hard stop for the whole run |
| `--coder/--critic/--planner <model>` | — | swap models per role |
| `--headed` | off | watch the browser work |

Everything is also settable by environment variable (`FORGE_MODEL_CODER`, `FORGE_PASS_SCORE`, `FORGE_CONCURRENCY`, …) — see `src/config.js`.

---

## Blind side-by-side comparison

Drop reference screenshots into `<workspace>/references/`. At the end of the run, the critic is shown your build and a reference **without being told which is which**, presented in an order that flips every round so positional bias cancels. Wins are counted in code after unmasking.

```bash
node bin/forge.js compare build/.forge/screenshots/final.png references/cod.jpg --rounds 5
```

```
BLIND A/B: won 1/5 — reference preferred
  round 1: REFERENCE (decisive) — Image B shows physically-based materials with
           layered surface wear, volumetric light shafts and filmic grading …
Gaps to close:
  - no ambient occlusion in corners
  - materials read as flat vertex-coloured plastic
  - no post-processing chain, image is raw framebuffer
```

Those gaps feed the next refinement round. This is honest: early rounds lose, decisively. That's the point — it's a measurement, not a participation trophy.

---

## Tuning for your box

**Parallelism.** Ollama serialises requests to the same model unless you tell it otherwise. For `--concurrency 2` to mean anything:

```bash
sudo systemctl edit ollama
# [Service]
# Environment="OLLAMA_NUM_PARALLEL=2"
# Environment="OLLAMA_MAX_LOADED_MODELS=2"
sudo systemctl restart ollama
```

With two GPUs, `OLLAMA_MAX_LOADED_MODELS=2` lets the coder and the critic stay resident simultaneously, which removes model-swap thrashing — the single biggest wall-clock win on a long run.

**Context.** `FORGE_CTX_CODER` defaults to 48k. Raising it costs VRAM; lowering it makes agents forget mid-task.

**Speed vs quality.** For a fast smoke run: `--concurrency 1 --critique-rounds 2 --rounds 1 --pass-score 60`.

---

## Honest limits

- **A 30B model is not Opus.** It writes competent, working code in small well-specified chunks. It does not invent a novel rendering architecture. The value here is the harness: decomposition, relentless verification, and a critic that won't accept a grey box.
- **Ambition is bounded by task granularity.** "A full Call of Duty" will not emerge. A coherent, textured, well-lit FPS prototype with recoil, hit feedback, and a HUD will — and each piece will have been screenshot-verified.
- **It is slow.** Expect several minutes per task round. A 20-task run with looping is an overnight job. It checkpoints after every transition; `forge resume` picks up exactly where it stopped.
- **The critic is a model, not an art director.** It is calibrated to be harsh and it is consistent, but it is not infallible. The objective gate is what makes the pipeline trustworthy; the critic is what makes it improve.
- **Parallel agents can still collide** on files they never declared. Tasks declare their files and the scheduler locks those, but an agent that wanders outside its declared set can conflict with a peer. Lower concurrency if you see churn.
