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
import { addMovementEffect, startFade, triggerTransitionFade } from './render-map.js';
import { RESOURCE_FEEDBACK } from './state.js';
import { applyDelta } from './state.js';
import { PALETTE } from './palette.js';

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
export function beginMove(unit, path, msPerStep = 250) {
    if (!unit || !path || path.length < 2) return;
    
    unit.path = path;
    unit.pathIndex = 0;
    unit.moveElapsed = 0;
    unit.msPerStep = msPerStep;
    unit.moving = true;
    unit.moveStep = 0;
    unit.moveStartPixel = { ...unit.pixel };
    unit.scale = 1.0;
    unit.rotation = 0;
    unit.justMoved = false;
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
    
    // Make sure we have valid coordinates before setting
    if (a && b && typeof a.x === 'number' && typeof a.y === 'number' && 
        typeof b.x === 'number' && typeof b.y === 'number') {
        unit.pixel = { x: a.x + (b.x - a.x) * e, y: a.y + (b.y - a.y) * e };
    }
    
    // Add scaling effect during movement for momentum simulation
    if (t < 1) {
        // Create a more natural scaling effect with a bounce
        const scale = 0.95 + Math.sin(t * Math.PI) * 0.1;
        unit.scale = scale;
    } else {
        unit.scale = 1.0;
    }
    
    // Add a subtle floating effect during movement to make it feel more alive
    if (t < 1 && typeof unit.pixel.y === 'number') {
        const floatOffset = Math.sin(t * Math.PI * 2) * 2;
        unit.pixel.y += floatOffset;
    }
    
    // Add rotation effect for dynamic movement
    if (t < 1) {
        const rotation = Math.sin(t * Math.PI * 3) * 0.1;
        unit.rotation = rotation;
    } else {
        unit.rotation = 0;
    }
    
    // Add particle effects during movement
    if (t < 1 && unit.moveStep > 0 && typeof unit.pixel.x === 'number' && typeof unit.pixel.y === 'number') {
        // Create a particle effect at the unit's current position
        addMovementEffect(unit.pixel.x, unit.pixel.y);
    }
    
    if (t < 1) return null;
    
    unit.pathIndex++;
    unit.moveElapsed = 0;
    unit.q = to.q;
    unit.r = to.r;
    unit.moveStep++;
    
    // Update the pixel position to match the new hex
    const newPixel = hexToPixel(to.q, to.r);
    if (newPixel && typeof newPixel.x === 'number' && typeof newPixel.y === 'number') {
        unit.pixel.x = newPixel.x;
        unit.pixel.y = newPixel.y;
    }
    
    if (unit.pathIndex >= unit.path.length - 1) {
        endMove(unit);
        // Mark that the unit just moved to trigger encounter
        if (unit && typeof unit === 'object') {
            unit.justMoved = true;
        }
    }
    
    return { q: to.q, r: to.r };
}

/** Clear all movement bookkeeping in one place, so no field is missed. */
export function endMove(unit) {
    unit.moving = false;
    unit.path = null;
    unit.pathIndex = 0;
    unit.moveStep = 0;
    unit.moveElapsed = 0;
    unit.scale = 1.0;
}

/** 
 * Start moving the unit to a hex.
 * @param {object} state - Game state
 * @param {number} q - Target hex q coordinate
 * @param {number} r - Target hex r coordinate
 * @returns {boolean} True if movement started successfully
 */
export function moveUnitToHex(state, q, r) {
    if (!state || !state.unit) return false;
    
    // Check if unit is already moving
    if (state.unit.moving) {
        return false;
    }
    
    // Find a path to the target hex
    const path = findPath(state.tiles, state.unit.q, state.unit.r, q, r);
    
    if (path.length < 2) {
        console.log('No valid path found');
        return false; 
    }
    
    console.log('Found path with', path.length, 'steps');
    
    // Consume resources for movement
    const cost = pathCost(state.tiles, path);
    if (cost > 0) {
        applyDelta(state, { food: -cost, water: -cost });
    }
    
    // Start the movement
    beginMove(state.unit, path);
    
    // Update unit's position to start at the first step of the path
    const firstStep = path[0];
    if (firstStep) {
        state.unit.q = firstStep.q;
        state.unit.r = firstStep.r;
        const pixel = hexToPixel(firstStep.q, firstStep.r);
        if (pixel && typeof pixel.x === 'number' && typeof pixel.y === 'number') {
            state.unit.pixel = pixel;
        }
    }
    
    // Trigger a fade effect when starting movement (for visual transition)
    if (typeof triggerTransitionFade === 'function') {
        triggerTransitionFade(PALETTE.BACKGROUND, 20); 
    }
    
    return true;
}