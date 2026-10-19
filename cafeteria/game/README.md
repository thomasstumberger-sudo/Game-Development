# Cafeteria Coup — Chapter 1: The Sunspire

A proactive stealth-heist. Rob Archmage Gilt of her useless Phoenix, out-talk her before the Council, fix the cafeteria. The design lives in `../cafeteria_coup_specification.md`. §17 is what's built and §18 is this project's layout.

## Play it
1. Install **Godot 4.7** or newer (the standard build; no .NET needed).
2. In the Project Manager choose **Import**, then pick `cafeteria/game/project.godot`.
3. Press **F5**.

**Controls**

| Keys | Action |
|---|---|
| WASD | Move |
| C (hold) | Sneak |
| Shift | Sprint |
| E | Interact |
| Space | Set the relic down |
| 1–5 | Spells (press 4 or 5 again to toggle Freeze or Reveal) |
| Left click | Cast at the cursor |
| Right click | Drop what Mage Hand is holding |
| Q / R | Cycle tools |
| [ / ] | Noisemaker timer |
| F | Cast artifact |
| Tab | Notebook |
| Esc | Cancel |

Bindings are InputMap actions (`scripts/input_setup.gd`), so they can be changed at runtime.

## Edit it without code
* **Maps:** `data/maps/*.txt`, one character per tile. The legend is in the spec, §17 and §18.2.
* **Writing:** `data/content.json` holds every roast, comeback, line of dialogue, notice and shop item.
* **Layout:** `data/world.json` holds guard routes (with night variants), links between floors, spawn points and prop masses.
* **Tuning:** `scripts/core/consts.gd`.

## Test it
```
GODOT=/path/to/godot tools/run_tests.sh           # 49 checks, headless
GODOT=/path/to/godot tools/run_tests.sh --shots   # same, plus screenshots in shots/ (needs a display or xvfb-run)
```
The run fails on any failed check **or** any engine or script error. It covers map integrity, real input, every spell combo, the Alibi Engine, Act 1 → Act 3 countermeasures, duels, the trial, a performance budget, and a full playthrough of the chapter through the in-game prompts.

## Export it
Install the export templates (Editor → Manage Export Templates), then use Project → Export to add presets. **Windows Desktop**, **Linux** and **macOS** cover Steam; **Web** suits an itch.io demo, and the GL Compatibility renderer already supports it. Commit the resulting `export_presets.cfg` (it holds no secrets unless you add signing keys).

## How it's built
* `Sim` (`scripts/sim/sim.gd`) owns all state and ticks at a fixed 20 Hz.
* The rules are static modules in `scripts/systems/` that take the `Sim`.
* Everything under `scripts/view/` only reads the `Sim` and draws placeholder art. Swap it for real art without touching the rules.
