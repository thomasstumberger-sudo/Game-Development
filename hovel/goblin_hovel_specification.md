# Game Specification: The Froudian Goblin Hovel

## 1. Overview & System Design
* **Concept:** A lightweight, highly addictive idle clicker game inspired by the organic, whimsical, and grotesque fairy-tale art style of Brian Froud. Goblins are generated via user clicks or automated spawning. They swarm inside a dilapidated, living wooden hovel that distorts, bulges, and vibrates rhythmically based on the current structural capacity.
* **Core Philosophy:** Low system footprint, high immediate feedback, perfect for background desk-play.
* **Target Execution Environment:** Vanilla single-file web application (`index.html`) using raw HTML5, CSS3, and modern ECMAScript without external build steps, transpilers, or monolithic game frameworks (e.g., Phaser, Pixi, Unity).

---

## 2. Technical Stack & Architecture
* **Interface Layer:** Pure DOM nodes using CSS Custom Properties (Variables) paired with hardware-accelerated transforms (`translate3d`, `scale3d`, `rotate3d`).
* **Graphics:** Inline procedural SVGs. Goblins are structurally simplified as layered vector forms or particles rather than heavy PNG sprite sheets, keeping total project space under 100KB.
* **Runtime Loop:** 
  * A decoupled state processing ticker running at **10-15 Hz** via a thinned `setInterval` loop to handle currency accumulations, offline progression, and logic calculations.
  * A dedicated display tick running via `requestAnimationFrame` (60 FPS) to map mathematical state outputs to rendering transformations.
* **Resource Preservation:** Implements `document.addEventListener('visibilitychange')` to halt or throttle the drawing loop when the window/tab loses focus, preserving host CPU cycles.

---

## 3. Data Model & Mathematical Engine

### State Properties
```javascript
const gameState = {
  goblins: 0,            // Current integer count of inside occupants
  capacity: 100,         // Base structural capability limit
  pressure: 0.0,         // Float range [0.0 - 1.0+] evaluated as (goblins / capacity)
  resonance: 0.0,        // Accumulated core currency (Chaos / Resonance)
  glamour: 0.0,          // Permanent prestige/multiplier currency
  spawnRate: 1.0,        // Automated generation per second
  upgrades: {
    wallStrength: 0,
    sporeSpawners: 0,
    lunkGenes: 0
  }
};
```

### Visual Distortion Mapping
The physical behavior of the hovel uses non-linear interpolation based on the `pressure` scale:
* **Breathing State ($0.0 \le P \le 0.5$):** Low frequency, soft scale changes.
  $$\text{Scale} = 1.0 + 0.04 \cdot \sin(\text{time} \cdot 2.5)$$
* **Straining State ($0.5 < P \le 0.85$):** The base scaling expands linearly with pressure, and a light rotational wobble is injected.
  $$\text{Base Scale} = 1.0 + (P - 0.5) \cdot 0.3$$
* **Critical Mass State ($0.85 < P \le 1.0+$):** High-frequency chaotic positional jitter and structural shearing.
  $$\text{Jitter}_x = \text{Random}(-3, 3) \cdot P^2, \quad \text{Jitter}_y = \text{Random}(-3, 3) \cdot P^2$$

---

## 4. CSS Animation Architecture
The dynamic state transitions are fed directly into the DOM container wrapping the Hovel graphics element.

```css
:root {
  --goblin-pressure: 0.0;
  --wobble-speed: 2.0s;
}

#hovel-container {
  transform-origin: bottom center;
  transition: transform 0.1s linear, filter 0.3s ease;
  will-change: transform, filter;
}

/* Base structural breathing */
@keyframes hovel-breath {
  0% { transform: scale3d(1, 1, 1); }
  50% { transform: scale3d(1.03, 0.97, 1); }
  100% { transform: scale3d(1, 1, 1); }
}

/* Violent structural pressure agitation */
@keyframes hovel-spasm {
  0% { transform: translate3d(1px, 1px, 0) rotate(0.5deg); }
  20% { transform: translate3d(-1px, -2px, 0) rotate(-0.5deg); }
  40% { transform: translate3d(-3px, 0px, 0) rotate(1deg); }
  60% { transform: translate3d(0px, 2px, 0) rotate(0deg); }
  80% { transform: translate3d(2px, 1px, 0) rotate(-1deg); }
  100% { transform: translate3d(1px, -1px, 0) rotate(0.5deg); }
}
```

---

## 5. UI/UX Specifications
* **Aesthetic Layout:** Linear 2D canvas profile arranged vertically. Implements muted parchment (#e6dfd3) backgrounds, charcoal ink sketch colors (#2c2a29), and selective deep bog green (#4a533c) accents.
* **Component Framework:**
  * **Top Header:** Large numerical monitors detailing current `Resonance` and `Goblin Density Ratio`.
  * **Center Window:** The core procedural Hovel SVG element, fully reacting to pressure variables.
  * **Bottom HUD Deck:** Split into two operational controls:
    * **Action Command:** A dominant `[ Summon Fae ]` button configured for pointer events.
    * **The Crucible Action:** A distinct, glowing `[ Initiate Disenchantment ]` toggle that lights up once structural failure thresholds are reached ($P \ge 1.0$). Clicking triggers an explosive visual whiteout, wiping current counts while multiplying structural traits based on generated `Glamour`.