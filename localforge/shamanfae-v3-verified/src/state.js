/** 
 * Game state and the canvas wiring.
 *
 * Everything mutable lives in the object `createState` returns. It is passed
 * explicitly to whoever needs it — there is no `window.game`. The last build
 * died because one module read `window.game.canvas` that nothing ever assigned;
 * a value passed as an argument cannot go missing that way.
 *
 * Pure module: no DOM access and no side effects until createState is called.
 */

import { generateMap, updateVisibility, hexToPixel, key } from './hex.js';

export const MAP_RADIUS = 7;

/**
 * Recent resource changes, for the HUD to float above the resource bar.
 *
 * Lives here rather than in its own module: it is game state, and the fixed
 * file layout has no slot for a thirteenth file.
 */
export const RESOURCE_FEEDBACK = {
  changes: [],

  addChange(res, amount) {
    this.changes.push({ resource: res, amount, time: Date.now() });
    if (this.changes.length > 5) this.changes.shift();
  },

  /** Changes newer than `maxAgeMs`, so entries expire instead of piling up. */
  getChanges(maxAgeMs = 2000) {
    const now = Date.now();
    return this.changes.filter((c) => now - c.time < maxAgeMs);
  },

  clear() {
    this.changes = [];
  },
};

/**
 * Build the whole game state around an already-existing canvas element.
 *
 * @param {HTMLCanvasElement} canvas
 * @param {number} seed deterministic map seed
 */
export function createState(canvas, seed = 20260805) {
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas context unavailable');

  const tiles = generateMap(MAP_RADIUS, seed);

  const state = {
    canvas,
    ctx,
    width: canvas.width,
    height: canvas.height,

    tiles,
    seed,

    // Camera is a world-space offset; the renderer translates by it so that
    // hex (0,0) sits in the middle of the viewport.
    camera: { x: canvas.width / 2, y: canvas.height / 2 },

    unit: {
      q: 0,
      r: 0,
      pixel: hexToPixel(0, 0),
      moving: false,
      path: null,
      pathIndex: 0,
      moveElapsed: 0,
      msPerStep: 260,
      health: 10,
      maxHealth: 10,
      magic: 4,
      maxMagic: 10,
      skill: 3,
      ritualCast: 0,
      moveStep: 0,
      role: 'shaman',
    },

    resources: {
      food: 24,
      water: 20,
      morale: 12,
      magic: 4,
      population: 8,
      materials: 5,
      weirdness: 0,
    },

    courtFavor: { seelie: 0, unseelie: 0, wild: 0 },

    turn: 1,
    phase: 'decision',

    input: {
      mouse: { x: 0, y: 0, down: false },
      hoverHex: null,
      selectedHex: null,
      keys: new Set(),
    },

    // Draw layers, sorted by z once at registration. main.js walks this every
    // frame; nothing else needs to know the draw order.
    layers: [],
    frame: 0,
    elapsed: 0,

    // Set by main.js when init fails, so the render loop can show the reason
    // instead of a black rectangle.
    fatalError: null,
  };

  updateVisibility(state.tiles, 0, 0);
  return state;
}

/** Register a draw layer. Lower z draws first. */
export function addLayer(state, z, name, draw) {
  state.layers.push({ z, name, draw });
  state.layers.sort((a, b) => a.z - b.z);
}

/** The tile the unit is standing on, or undefined off-map. */
export function currentTile(state) {
  return state.tiles.get(key(state.unit.q, state.unit.r));
}

/** 
 * Apply a flat resource delta, clamping at zero so nothing goes negative and
 * silently breaks the HUD.
 */
export function applyDelta(state, delta) {
  for (const [res, amount] of Object.entries(delta ?? {})) {
    if (!(res in state.resources)) continue;
    // Add visual feedback when resources are consumed
    if (amount < 0) {
      RESOURCE_FEEDBACK.addChange(res, amount);
    }
    state.resources[res] = Math.max(0, state.resources[res] + amount);
  }
  if ('magic' in (delta ?? {})) {
    state.unit.magic = Math.max(0, Math.min(state.unit.maxMagic, state.resources.magic));
  }
  
  // Handle ritual success/failure flag
  if ('ritualSuccess' in (delta ?? {})) {
    state.unit.ritualSuccess = delta.ritualSuccess;
  }
  
  // Handle ritual casting flag
  if ('ritualCast' in (delta ?? {})) {
    state.unit.ritualCast = delta.ritualCast;
  }
}

/**
 * End of turn: consume upkeep, advance the counter. Upkeep scales with the
 * population, per the design document's move/rest costs.
 */
export function endTurn(state) {
  const upkeep = Math.ceil(state.resources.population / 4);
  applyDelta(state, { food: -upkeep, water: -upkeep });
  
  if (state.resources.food === 0 || state.resources.water === 0) {
    applyDelta(state, { morale: -2 });
  }
  state.turn++;
  state.phase = 'decision';
}