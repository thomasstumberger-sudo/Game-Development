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

/** Map radius - exported for use in other modules */
export const MAP_RADIUS = 7;

/**
 * Convert world pixel coordinates to hex coordinates (flat-top layout).
 *
 * This is the exact algebraic inverse of hexToPixel below. It used to be a
 * copy of the textbook pointy-top formula, which does not describe this
 * layout and ignored hexToPixel's HEX_SIZE origin offset — so every click
 * resolved to a hex the map did not contain and the board ignored the mouse.
 *
 * Coordinates are WORLD space: subtract state.camera before calling.
 */
export function pixelToHex(x, y) {
    const q = (x - HEX_SIZE) / COL_STEP;
    const r = (y - HEX_SIZE) / ROW_STEP - q / 2;
    return axialRound(q, r);
}

/** Round axial coordinates to the nearest hex. */
function axialRound(q, r) {
    let s = -q - r;
    let rq = Math.round(q);
    let rr = Math.round(r);
    let rs = Math.round(s);
    
    const qDiff = Math.abs(rq - q);
    const rDiff = Math.abs(rr - r);
    const sDiff = Math.abs(rs - s);
    
    if (qDiff > rDiff && qDiff > sDiff) {
        rq = -rr - rs;
    } else if (rDiff > sDiff) {
        rr = -rq - rs;
    } else {
        rs = -rq - rr;
    }
    
    return { q: rq, r: rr };
}

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

/**
 * Get adjacent hexes
 * @param {number} q - Q coordinate
 * @param {number} r - R coordinate
 * @returns {Array<{q: number, r: number}>} Array of adjacent hex coordinates
 */
export function getAdjacentHexes(q, r) {
    return neighbors(q, r);
}

/** Axial distance between two hexes. */
export function distance(aq, ar, bq, br) {
    return (Math.abs(aq - bq) + Math.abs(aq + ar - bq - br) + Math.abs(ar - br)) / 2;
}

/** Hex centre in world pixels. Flat-top layout. */
export function hexToPixel(q, r) {
    return {
        x: COL_STEP * q + HEX_SIZE,
        y: ROW_STEP * (r + q / 2) + HEX_SIZE,
    };
}

/**
 * Get the six corners of a hex in world pixels.
 * @param {number} q - Hex q coordinate
 * @param {number} r - Hex r coordinate
 * @returns {Array<{x: number, y: number}>} Array of 6 corner points
 */
export function hexCorners(q, r) {
    const center = hexToPixel(q, r);
    const corners = [];
    
    for (let i = 0; i < 6; i++) {
        const angle = Math.PI / 3 * i;
        corners.push({
            x: center.x + HEX_SIZE * Math.cos(angle),
            y: center.y + HEX_SIZE * Math.sin(angle)
        });
    }
    
    return corners;
}

/** 
 * Generate a hex map with the specified radius and seed.
 * 
 * @param {number} radius - The radius of the hex grid
 * @param {number} seed - Random seed for reproducible maps
 * @returns {Map<string, object>} Map of tiles indexed by key
 */
export function generateMap(radius, seed) {
    const tiles = new Map();
    
    // Simple seeded random number generator
    function seededRandom(seed) {
        return function() {
            seed = (seed * 9301 + 49297) % 233280;
            return seed / 233280;
        };
    }
    
    const rand = seededRandom(seed);
    
    // Generate hexes in a ring pattern
    for (let q = -radius; q <= radius; q++) {
        const r1 = Math.max(-radius, -q - radius);
        const r2 = Math.min(radius, -q + radius);
        
        for (let r = r1; r <= r2; r++) {
            // Create a tile with random terrain
            const terrainTypes = Object.values(TERRAIN);
            const terrain = terrainTypes[Math.floor(rand() * terrainTypes.length)];
            
            // Generate a unique key for this hex
            const key = `${q},${r}`;
            
            // Create the tile - make sure we use the correct structure to match what render-map.js expects
            tiles.set(key, {
                q,
                r,
                terrain: {
                    id: terrain.id,
                    name: terrain.name,
                    color: terrain.color,
                    variations: terrain.variations,
                    movementCost: terrain.movementCost,
                    resourceBonus: terrain.resourceBonus,
                    impassable: terrain.impassable
                },
                visibility: 'unseen',
                encounter: null,
                regenerationCounter: 0,
                courtInfluence: { seelie: 0, unseelie: 0, wild: 0 }
            });
        }
    }
    
    return tiles;
}

/**
 * Update visibility for a hex and its neighbors.
 * 
 * @param {Map<string, object>} tiles - Map of all tiles
 * @param {number} q - Q coordinate of center hex
 * @param {number} r - R coordinate of center hex
 */
export function updateVisibility(tiles, q, r) {
    // Mark the center hex as explored
    const centerKey = key(q, r);
    const centerTile = tiles.get(centerKey);
    if (centerTile) {
      centerTile.visibility = 'explored';
      
      // Mark adjacent hexes as adjacent hint
      for (const neighbor of neighbors(q, r)) {
        const neighborKey = key(neighbor.q, neighbor.r);
        const neighborTile = tiles.get(neighborKey);
        if (neighborTile && neighborTile.visibility === 'unseen') {
          neighborTile.visibility = 'adjacent';
        }
      }
      
      // Mark outer ring as visible
      for (const neighbor of neighbors(q, r)) {
        for (const outer of neighbors(neighbor.q, neighbor.r)) {
          const outerKey = key(outer.q, outer.r);
          const outerTile = tiles.get(outerKey);
          if (outerTile && outerTile.visibility === 'unseen') {
            outerTile.visibility = 'outer';
          }
        }
      }
    }
}

/**
 * Convert world coordinates to screen coordinates.
 * @param {number} x - World x coordinate
 * @param {number} y - World y coordinate
 * @param {object} camera - Camera position {x, y}
 * @returns {object} Screen coordinates {x, y}
 */
export function worldToScreen(x, y, camera) {
    // Convert world coordinates to screen coordinates using camera offset
    if (camera) {
      return { x: x + camera.x, y: y + camera.y };
    }
    return { x: x, y: y };
}