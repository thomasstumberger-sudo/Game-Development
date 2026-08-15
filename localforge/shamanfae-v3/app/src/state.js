/** 
 * Game state management.
 * 
 * Pure module: no DOM, no side effects on import.
 */ 

import { PALETTE } from './palette.js';
import { hexToPixel, generateMap, MAP_RADIUS } from './hex.js';
import { addMovementEffect } from './render-map.js';
import { findPath, pathCost, updateMove } from './movement.js';

// Pre-rendered tile textures for different terrain types
let tileTextures = new Map();
let particleEffects = [];

/** 
 * Create a new game state.
 * 
 * @param {HTMLCanvasElement} canvas
 * @param {number} seed - For reproducible terrain generation
 * @returns {object} The initialized game state
 */
export function createState(canvas, seed) {
    // Initialize the state with default values
    const state = {
        width: canvas.width,
        height: canvas.height,
        camera: { x: 0, y: 0 },
        tiles: new Map(),
        unit: {
            q: 0,
            r: 0,
            pixel: { x: 0, y: 0 },
            health: 10,
            magic: 4,
            skill: 3,
            moving: false,
            path: null,
            pathIndex: 0,
            moveElapsed: 0,
            msPerStep: 300,
            moveStep: 0,
            scale: 1.0,
            rotation: 0,
            justMoved: false,
            ritualSuccess: false,
            ritualSuccessTimer: 0,
            castingRitual: false,
            maxMagic: 4
        },
        resources: {
            food: 20,
            water: 20,
            morale: 50,
            magic: 4,
            population: 4,
            materials: 10,
            health: 10,
            weirdness: 0
        },
        phase: 'decision', // decision, encounter, aftermath
        frame: 0,
        input: {
            mouse: { x: 0, y: 0, down: false },
            hoverHex: null,
            selectedHex: null,
            keys: new Set(),
        },
        // Add a flag to track if we're in a transition
        inTransition: false,
        canvas: canvas
    };
    
    // Generate terrain for the map using the hex.js generateMap function
    const generatedTiles = generateMap(MAP_RADIUS, seed); // Use MAP_RADIUS from hex.js
    state.tiles = generatedTiles;
    
    // Set up camera to center on the unit
    const unitPixel = hexToPixel(state.unit.q, state.unit.r);
    if (unitPixel && typeof unitPixel.x === 'number' && typeof unitPixel.y === 'number') {
        state.camera.x = -unitPixel.x + state.width / 2;
        state.camera.y = -unitPixel.y + state.height / 2;
        // Set the unit pixel in state
        state.unit.pixel = unitPixel;
    } else {
        // Fallback if we can't get a valid pixel position
        state.unit.pixel = { x: state.width / 2, y: state.height / 2 };
    }
    
    return state;
}

/** 
 * Generate terrain for the map.
 * 
 * @param {object} state - Game state
 * @param {number} seed - For reproducible terrain generation
 */
function generateTerrain(state, seed) {
    // This function is now replaced by using generateMap from hex.js directly
    // The actual implementation is in generateMap function in hex.js
}

/** 
 * Get movement cost for a terrain type.
 * 
 * @param {string} terrainType - Type of terrain
 * @returns {number} Movement cost
 */
function getTerrainMovementCost(terrainType) {
    switch (terrainType) {
        case 'GRASS': return 1;
        case 'FOREST': return 2;
        case 'WATER': return 3;
        case 'MOUNTAIN': return 4;
        case 'SWAMP': return 3;
        case 'FAE_LAND': return 2;
        default: return 1;
    }
}

/** 
 * Check if a terrain type is impassable.
 * 
 * @param {string} terrainType - Type of terrain
 * @returns {boolean} True if impassable
 */
function isImpassable(terrainType) {
    return false; // All terrains are passable for now
}

/** 
 * Apply a change to the game state.
 * 
 * @param {object} state - Game state
 * @param {object} delta - Changes to apply
 */
export function applyDelta(state, delta) {
    if (!state || !delta) return;
    
    for (const [key, value] of Object.entries(delta)) {
        if (typeof state.resources[key] !== 'undefined') {
            state.resources[key] += value;
            // Clamp values to reasonable bounds
            if (state.resources[key] < 0) state.resources[key] = 0;
            if (key === 'food' && state.resources[key] > 100) state.resources[key] = 100;
            if (key === 'water' && state.resources[key] > 100) state.resources[key] = 100;
            if (key === 'morale' && state.resources[key] > 100) state.resources[key] = 100;
            if (key === 'magic' && state.resources[key] > 20) state.resources[key] = 20;
            
            // Add resource change to feedback system
            addResourceChange(key, value);
        } else if (typeof state.unit[key] !== 'undefined') {
            state.unit[key] += value;
            // Clamp unit values
            if (key === 'health' && state.unit[key] < 0) state.unit[key] = 0;
            if (key === 'magic' && state.unit[key] < 0) state.unit[key] = 0;
        }
    }
}

/** 
 * Add a resource change to the feedback system.
 * 
 * @param {string} resource - Resource name
 * @param {number} amount - Amount changed
 */
export function addResourceChange(resource, amount) {
    RESOURCE_FEEDBACK.addChange(resource, amount);
}

/** 
 * Update the game state by one fixed timestep. 
 * 
 * @param {object} state - Game state
 * @param {number} dtMs - Time since last update in milliseconds
 */
export function update(state, dtMs = 1000 / 60) {
    if (!state) return;
    
    // Frame counter for animation effects
    state.frame++;
    
    // Ritual feedback timer
    if (state.unit && state.unit.ritualSuccessTimer > 0) {
        state.unit.ritualSuccessTimer--;
    }
}

// Resource feedback system for visual effects
export const RESOURCE_FEEDBACK = {
    changes: [],
    
    addChange(resource, amount) {
        this.changes.push({
            resource,
            amount,
            time: Date.now()
        });
    },
    
    getChanges(maxAge) {
        const now = Date.now();
        return this.changes.filter(change => now - change.time < maxAge);
    }
};