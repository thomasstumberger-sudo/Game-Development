/**
 * Hex math, the grid model, and procedural terrain generation.
 *
 * Flat-top hexes on axial (q, r) coordinates. All the geometry lives here so
 * that no other module ever recomputes a corner or a centre and drifts out of
 * agreement with the renderer — a mismatch between the drawing math and the
 * picking math is invisible in code review and obvious on screen.
 *
 * Pure module: no DOM, no side effects on import.
 */

import { PALETTE } from './palette.js';

/** Hex circumradius in pixels (centre to corner). */
export const HEX_SIZE = 32;

/** Flat-top spacing derived from the circumradius. */
export const HEX_W = HEX_SIZE * 2;
export const HEX_H = Math.sqrt(3) * HEX_SIZE;
export const COL_STEP = HEX_SIZE * 1.5;
export const ROW_STEP = HEX_H;

export const TERRAIN = {
  GRASS: {
    id: 'grass',
    name: 'Grassland',
    color: PALETTE.GRASS,
    variations: [PALETTE.GRASS_V1, PALETTE.GRASS_V2],
    movementCost: 1,
    resourceBonus: { food: 1, water: 0 },
  },
  FOREST: {
    id: 'forest',
    name: 'Forest',
    color: PALETTE.FOREST,
    variations: [PALETTE.FOREST_V1, PALETTE.FOREST_V2],
    movementCost: 2,
    resourceBonus: { food: 0, water: 1 },
  },
  MOUNTAIN: {
    id: 'mountain',
    name: 'Mountain',
    color: PALETTE.MOUNTAIN,
    variations: [PALETTE.MOUNTAIN_V1, PALETTE.MOUNTAIN_V2],
    movementCost: 3,
    resourceBonus: { food: 0, water: 0 },
  },
  SWAMP: {
    id: 'swamp',
    name: 'Swamp',
    color: PALETTE.SWAMP,
    variations: [PALETTE.SWAMP_V1, PALETTE.SWAMP_V2],
    movementCost: 3,
    resourceBonus: { food: -1, water: 0 },
  },
  WATER: {
    id: 'water',
    name: 'Water',
    color: PALETTE.WATER,
    variations: [PALETTE.WATER_V1, PALETTE.WATER_V2],
    movementCost: 4,
    resourceBonus: { food: 0, water: 2 },
    impassable: true,
  },
  FAE_LAND: {
    id: 'fae_land',
    name: 'Fae Land',
    color: PALETTE.FAE_LAND,
    variations: [PALETTE.FAE_V1, PALETTE.FAE_V2],
    movementCost: 1,
    resourceBonus: { food: 0, water: 0 },
  },
};

/** The six axial neighbour directions, in clockwise order. */
export const DIRECTIONS = [
  { dq: 1, dr: 0 }, { dq: 1, dr: -1 }, { dq: 0, dr: -1 },
  { dq: -1, dr: 0 }, { dq: -1, dr: 1 }, { dq: 0, dr: 1 },
];

export function key(q, r) {
  return `${q},${r}`;
}

export function neighbors(q, r) {
  return DIRECTIONS.map((d) => ({ q: q + d.dq, r: r + d.dr }));
}

/** Axial distance between two hexes. */
export function distance(aq, ar, bq, br) {
  return (Math.abs(aq - bq) + Math.abs(aq + ar - bq - br) + Math.abs(ar - br)) / 2;
}

/** Hex centre in world pixels. Flat-top layout. */
export function hexToPixel(q, r) {
  return {
    x: COL_STEP * q,
    y: ROW_STEP * (r + q / 2),
  };
}

/** World pixels back to the nearest hex. Inverse of hexToPixel, then rounded. */
export function pixelToHex(x, y) {
  const q = (2 / 3) * x / HEX_SIZE;
  const r = (-1 / 3) * x / HEX_SIZE + (Math.sqrt(3) / 3) * y / HEX_SIZE;
  return roundHex(q, r);
}

/** Round fractional axial coordinates to the nearest real hex, via cube. */
export function roundHex(q, r) {
  const s = -q - r;
  let rq = Math.round(q);
  let rr = Math.round(r);
  const rs = Math.round(s);

  const dq = Math.abs(rq - q);
  const dr = Math.abs(rr - r);
  const ds = Math.abs(rs - s);

  if (dq > dr && dq > ds) rq = -rr - rs;
  else if (dr > ds) rr = -rq - rs;

  return { q: rq, r: rr };
}

/** The six corners of a hex centred at (cx, cy). Flat-top: first corner east. */
export function hexCorners(cx, cy) {
  const corners = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    corners.push({
      x: cx + HEX_SIZE * Math.cos(angle),
      y: cy + HEX_SIZE * Math.sin(angle),
    });
  }
  return corners;
}

function makeTile(q, r, terrain, rng) {
  return {
    q,
    r,
    terrain,
    variation: terrain.variations[Math.floor(rng() * terrain.variations.length)],
    visited: false,
    visibility: 'unseen',
    encounter: null,
    regenCounter: 0,
    courtInfluence: { seelie: 50, unseelie: 50, wild: 50 },
    roughness: rng() * 0.3 + 0.1,
  };
}

/**
 * Deterministic PRNG so a seed reproduces a map exactly. Debugging a terrain
 * bug against a map that changes every reload is not debugging.
 */
export function makeRng(seed = 1) {
  let s = seed >>> 0;
  return function rng() {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/**
 * Generate a hex-shaped map of the given radius.
 *
 * Terrain comes from layered trig noise rather than true Perlin — it is cheap,
 * dependency-free, and produces coherent bands of terrain instead of the
 * salt-and-pepper mess that per-tile random() gives.
 *
 * @returns {Map<string, object>} keyed by `${q},${r}`
 */
export function generateMap(radius = 7, seed = 1) {
  const rng = makeRng(seed);
  const tiles = new Map();

  for (let q = -radius; q <= radius; q++) {
    const rMin = Math.max(-radius, -q - radius);
    const rMax = Math.min(radius, -q + radius);
    for (let r = rMin; r <= rMax; r++) {
      const noise =
        Math.sin(q * 0.45) * Math.cos(r * 0.4) +
        Math.sin((q + r) * 0.3) * 0.6 +
        Math.cos(q * 0.18 - r * 0.22) * 0.4;

      let terrain;
      if (noise < -1.0) terrain = TERRAIN.WATER;
      else if (noise < -0.5) terrain = TERRAIN.SWAMP;
      else if (noise < 0.1) terrain = TERRAIN.FOREST;
      else if (noise < 0.75) terrain = TERRAIN.GRASS;
      else terrain = TERRAIN.MOUNTAIN;

      // Fae land is rare and never at the origin, so the tribe never starts on it.
      if (rng() < 0.06 && distance(q, r, 0, 0) > 2) terrain = TERRAIN.FAE_LAND;

      tiles.set(key(q, r), makeTile(q, r, terrain, rng));
    }
  }

  // The tribe starts on solid ground whatever the noise said.
  const origin = tiles.get(key(0, 0));
  if (origin && origin.terrain.impassable) {
    origin.terrain = TERRAIN.GRASS;
    origin.variation = TERRAIN.GRASS.variations[0];
  }

  return tiles;
}

/**
 * Recompute visibility tiers around a position.
 *   explored — visited, fully visible
 *   adjacent — one ring out, terrain plus an encounter hint
 *   outer    — two rings out, terrain only
 */
export function updateVisibility(tiles, q, r) {
  const here = tiles.get(key(q, r));
  if (here) here.visited = true;

  for (const tile of tiles.values()) {
    const d = distance(tile.q, tile.r, q, r);
    if (tile.visited) tile.visibility = 'explored';
    else if (d <= 1) tile.visibility = 'adjacent';
    else if (d <= 2) tile.visibility = 'outer';
    // Otherwise leave it as it is. A tile that has fallen out of range keeps
    // the tier it was last seen at, so scouted ground stays on the map instead
    // of being swallowed by fog the moment you turn your back.
  }
}
