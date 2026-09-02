/** 
 * Pathfinding and movement tweens.
 * 
 * The previous build shipped a "pathfinder" that returned [start, end] and
 * ignored the terrain entirely, so units walked through mountains and lakes.
 * This is a real cost-aware search over the actual grid.
 * 
 * Pure module: no DOM, no side effects on import.
 */

import { key, neighbors, hexToPixel } from './hex.js';

/** 
 * Uniform-cost search (Dijkstra) across the hex grid, honouring each terrain's
 * movementCost and refusing impassable tiles.
 * 
 * @returns {Array<{q:number,r:number}>} tiles from start to goal inclusive,
 *   or [] when no route exists.
 */
export function findPath(tiles, startQ, startR, goalQ, goalR) {
    // Guard on absence, not falsiness. `!startQ` is true when startQ is 0, and
    // the unit starts at (0,0) — so a falsy check here silently disabled every
    // path from the origin and killed click-to-move entirely.
    if (!tiles) return [];
    for (const v of [startQ, startR, goalQ, goalR]) {
        if (typeof v !== 'number' || !Number.isFinite(v)) return [];
    }


    const startKey = key(startQ, startR);
    const goalKey = key(goalQ, goalR);
    if (startKey === goalKey) return [{ q: startQ, r: startR }];
    
    const goal = tiles.get(goalKey);
    if (!goal || goal.terrain.impassable) return [];
    
    const frontier = [{ q: startQ, r: startR, cost: 0 }];
    const cameFrom = new Map([[startKey, null]]);
    const costSoFar = new Map([[startKey, 0]]);
    
    while (frontier.length) {
        // Small frontiers on a radius-7 map; a linear scan beats a heap here.
        let bestIdx = 0;
        for (let i = 1; i < frontier.length; i++) {
            if (frontier[i].cost < frontier[bestIdx].cost) bestIdx = i;
        }
        const current = frontier.splice(bestIdx, 1)[0];
        const currentKey = key(current.q, current.r);
        if (currentKey === goalKey) break;
        
        for (const n of neighbors(current.q, current.r)) {
            const tile = tiles.get(key(n.q, n.r));
            if (!tile || tile.terrain.impassable) continue;
            
            const newCost = costSoFar.get(currentKey) + tile.terrain.movementCost;
            const nKey = key(n.q, n.r);
            if (!costSoFar.has(nKey) || newCost < costSoFar.get(nKey)) {
                costSoFar.set(nKey, newCost);
                cameFrom.set(nKey, currentKey);
                frontier.push({ q: n.q, r: n.r, cost: newCost });
            }
        }
    }
    
    if (!cameFrom.has(goalKey)) return [];
    
    const path = [];
    for (let k = goalKey; k !== null; k = cameFrom.get(k)) {
        const [q, r] = k.split(',').map(Number);
        path.unshift({ q, r });
    }
    return path;
}

/** Total movement cost of a path, excluding the tile already stood on. */
export function pathCost(tiles, path) {
    return path.slice(1).reduce((sum, step) => {
        const tile = tiles.get(key(step.q, step.r));
        return sum + (tile ? tile.terrain.movementCost : 0);
    }, 0);
}

/** Ease-in-out, so a step starts and lands softly instead of snapping. */
function easeInOut(t) {
    // Using a smoother easing function for better movement animation
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

/**
 * Start a tween along a path. Movement state lives on the unit so that a
 * half-finished move survives a re-render and nothing else has to track it.
 */
export function beginMove(unit, path, msPerStep = 300) {
    if (!unit || !path || path.length < 2) return;
    unit.path = path;
    unit.pathIndex = 0;
    unit.moveElapsed = 0;
    unit.msPerStep = msPerStep;
    unit.moving = true;
    unit.moveStep = 0; // Initialize move step
    unit.moveStartPixel = { ...unit.pixel }; // Store start position for visual effects
}

/**
 * Advance any in-progress move. Returns the tile the unit just arrived on, or
 * null — callers use that to fire arrival effects exactly once per hex.
 */
export function updateMove(unit, dtMs) {
    if (!unit || !unit.moving) return null;

    // One guard covers every malformed-path case the five stacked checks used
    // to cover separately. A try/catch around the whole body only turned real
    // bugs into console noise, so it is gone.
    const from = unit.path?.[unit.pathIndex];
    const to = unit.path?.[unit.pathIndex + 1];
    if (!from || !to) {
        endMove(unit);
        return null;
    }

    unit.moveElapsed += dtMs;
    const t = Math.min(1, unit.moveElapsed / unit.msPerStep);

    const a = hexToPixel(from.q, from.r);
    const b = hexToPixel(to.q, to.r);
    const e = easeInOut(t);
    unit.pixel = { x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e };

    if (t < 1) return null;

    unit.pathIndex++;
    unit.moveElapsed = 0;
    unit.q = to.q;
    unit.r = to.r;
    unit.moveStep++;

    if (unit.pathIndex >= unit.path.length - 1) endMove(unit);
    return { q: to.q, r: to.r };
}

/** Clear all movement bookkeeping in one place, so no field is missed. */
function endMove(unit) {
    unit.moving = false;
    unit.path = null;
    unit.pathIndex = 0;
    unit.moveStep = 0;
    unit.moveElapsed = 0;
}

/**
 * Move the Shaman-Chief to a clicked hex if a valid path exists.
 * This is called from input.js when a hex is clicked.
 */
export function moveUnitToHex(state, targetQ, targetR) {
    // Ensure state and unit exist
    if (!state || !state.unit) {
        return false;
    }
    
    const unit = state.unit;
    
    // Don't move if already moving or if clicking on current position
    if (unit.moving || (unit.q === targetQ && unit.r === targetR)) {
        return false;
    }
    
    // Find a path to the clicked hex
    const path = findPath(state.tiles, unit.q, unit.r, targetQ, targetR);
    
    // If no path exists, don't move
    if (path.length === 0) {
        return false;
    }
    
    // Refuse the move if the tribe cannot pay the upkeep it will incur.
    // The charge itself happens in endTurn() on arrival — deducting here as
    // well would double-bill, and reporting it to RESOURCE_FEEDBACK here made
    // the HUD show a loss that had not actually been applied yet.
    const upkeep = Math.ceil(state.resources.population / 4);
    if (state.resources.food < upkeep || state.resources.water < upkeep) {
        return false;
    }

    beginMove(unit, path, 400);
    return true;
}