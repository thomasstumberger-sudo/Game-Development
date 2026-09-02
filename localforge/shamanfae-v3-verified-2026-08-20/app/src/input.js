/** 
 * Input handling for the game.
 * 
 * Pure module: no DOM, no side effects on import.
 */ 
import { pixelToHex, hexToPixel, worldToScreen } from './hex.js';
import { applyDelta } from './state.js';
import { addHoverEffect } from './render-map.js'; // Import hover effect function
import { addRitualCastEffect, addEncounterEffect, addMagicEffect, addParticle, addRitualResultEffect } from './render-map.js'; // Import ritual effects and particle system
// import { castRitual } from './rituals.js'; // This will be imported in main.js instead to avoid circular dependency

/** 
 * Convert a mouse event to canvas-space coordinates, accounting for CSS
 * scaling — the canvas is often displayed at a different size than its
 * backing store, and ignoring that puts the cursor on the wrong hex.
 */ 
function toCanvasSpace(canvas, event) {
    // Make sure we have a valid canvas
    if (!canvas || !canvas.getBoundingClientRect) {
        console.warn('Invalid canvas in toCanvasSpace');
        return { x: event.clientX, y: event.clientY };
    }
    
    const rect = canvas.getBoundingClientRect();
    // Make sure we have valid dimensions before calculating
    if (rect.width === 0 || rect.height === 0) {
        console.warn('Canvas has invalid dimensions');
        // Try to use the canvas's actual dimensions
        if (canvas.width > 0 && canvas.height > 0) {
            return { 
                x: (event.clientX - rect.left) * (canvas.width / rect.width),
                y: (event.clientY - rect.top) * (canvas.height / rect.height)
            };
        }
        return { x: event.clientX, y: event.clientY };
    }
    return {
        x: (event.clientX - rect.left) * (canvas.width / rect.width),
        y: (event.clientY - rect.top) * (canvas.height / rect.height)
    };
}

/**
* Convert canvas coordinates to hex coordinates.
*
* The renderer draws every tile at hexToPixel(q,r) + state.camera, so picking
* has to undo that offset before asking hex.js which hex a point falls in.
*/
function hexAt(state, x, y) {
    // Make sure we have valid coordinates before converting
    if (typeof x !== 'number' || typeof y !== 'number' || !isFinite(x) || !isFinite(y)) {
        return { q: 0, r: 0 };
    }
    
    // Canvas space -> world space, then world space -> hex.
    const camera = state?.camera ?? { x: 0, y: 0 };
    const result = pixelToHex(x - camera.x, y - camera.y);
    
    // Ensure we have valid hex coordinates
    if (typeof result.q !== 'number' || typeof result.r !== 'number') {
        return { q: 0, r: 0 };
    }
    
    return result;
}

/** 
 * Find the tile at a given screen position
 * @param {object} state - Game state
 * @param {number} x - Screen x coordinate
 * @param {number} y - Screen y coordinate
 * @returns {object|null} Tile or null if not found
 */ 
export function tileAt(state, x, y) {
    // Make sure we have valid coordinates before converting
    if (typeof x !== 'number' || typeof y !== 'number' || !isFinite(x) || !isFinite(y)) {
        return null;
    }
    
    const hex = hexAt(state, x, y);
    const keyStr = `${hex.q},${hex.r}`;
    return state.tiles && state.tiles.get(keyStr) || null;
}

/** 
 * @param {HTMLCanvasElement} canvas
 * @param {object} state
 * @param {{onSelect?:Function, onOption?:Function, onEndTurn?:Function, onHexClick?:Function, onRitualCast?:Function}} handlers
 * @returns {Function} detach
 */ 
export function attachInput(canvas, state, handlers = {}) {
    // Ensure the canvas has valid dimensions first
    if (canvas.width === 0 || canvas.height === 0) {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    
    // Make sure state has correct dimensions
    if (state && !state.width) {
        state.width = canvas.width;
        state.height = canvas.height;
    }
    
    // Double-check that state has width and height
    if (state) {
        if (typeof state.width !== 'number' || isNaN(state.width)) {
            state.width = canvas.width;
        }
        if (typeof state.height !== 'number' || isNaN(state.height)) {
            state.height = canvas.height;
        }
    }
    
    // Ensure state.input exists with proper structure
    if (!state.input) {
        state.input = {
            mouse: { x: 0, y: 0, down: false },
            hoverHex: null,
            selectedHex: null,
            keys: new Set(),
        };
    } else {
        // Initialize missing properties in input object
        if (!state.input.mouse) state.input.mouse = { x: 0, y: 0, down: false };
        if (!state.input.hoverHex) state.input.hoverHex = null;
        if (!state.input.selectedHex) state.input.selectedHex = null;
        if (!state.input.keys) state.input.keys = new Set();
    }
    
    // Make sure window.game is available for the input system
    if (typeof window !== 'undefined') {
        // Ensure window.game exists and properly initialized
        if (!window.game) {
            window.game = {};
        }
        window.game.state = state; // Ensure state is accessible globally
    }
    
    const onMouseMove = (event) => {
        if (!canvas || !canvas.getBoundingClientRect) {
            return;
        }
        
        const p = toCanvasSpace(canvas, event);
        state.input.mouse.x = p.x;
        state.input.mouse.y = p.y;

        const hex = hexAt(state, p.x, p.y);
        // Only set hoverHex if it's a valid tile
        const keyStr = `${hex.q},${hex.r}`;
        if (state.tiles && state.tiles.has(keyStr)) {
            state.input.hoverHex = hex;
            
            // Add hover effect particles
            const pixel = hexToPixel(hex.q, hex.r);
            const screenPos = worldToScreen(pixel.x, pixel.y, state.camera);
            if (screenPos) {
                addHoverEffect(screenPos.x, screenPos.y);
            }
        } else {
            state.input.hoverHex = null;
        }
    };
    
    const onMouseDown = () => { state.input.mouse.down = true; };
    
    const onMouseUp = (event) => {
        state.input.mouse.down = false;
        const p = toCanvasSpace(canvas, event);
        
        // An open encounter swallows the click — the map is not interactive
        // while a decision is pending.
        if (handlers.onOption?.(p.x, p.y)) return;
        
        const hex = hexAt(state, p.x, p.y);
        const keyStr = `${hex.q},${hex.r}`;
        if (!state.tiles || !state.tiles.has(keyStr)) return;
        
        // Check if clicked on the unit itself
        const unit = state.unit;
        if (unit && unit.pixel) {
            // Convert world coordinates to screen coordinates for comparison
            const unitScreenX = unit.pixel.x + state.camera.x;
            const unitScreenY = unit.pixel.y + state.camera.y;
            
            const distance = Math.sqrt((p.x - unitScreenX) ** 2 + (p.y - unitScreenY) ** 2);
            if (distance < 24) { // Unit is roughly 48px wide, so 24px radius
                // Clicked on the unit itself - for now just ignore and let it fall through to normal behavior
                console.log('Clicked on unit');
                return;
            }
        }
        
        // A unit-click test used to live here comparing canvas coordinates
        // against the unit's world-space pixel. Those are different spaces, so
        // the branch could only ever be dead code. Selecting the hex the unit
        // stands on already expresses "select the unit".
        state.input.selectedHex = hex;
        
        if (state && state.phase === 'decision') {
            // Dispatch only. This module reports *what was clicked*; deciding
            // what that means is main.js's job.
            //
            // This used to call moveUnitToHex() itself and then also invoke the
            // handler, so every click ran the move twice -- the second call
            // always returning false because unit.moving was already true, and
            // logging "Move result: Failed" over a move that had just started.
            handlers.onHexClick?.(hex);
        }
    };
    
    const onMouseLeave = () => { state.input.mouse.down = false; };
    
    const onKeyDown = (event) => {
        // Add key to the set
        state.input.keys.add(event.key);
        
        // Number keys resolve an open encounter without needing the mouse.
        if (event.key >= '1' && event.key <= '9') {
            handlers.onOptionIndex?.(parseInt(event.key) - 1);
        }
        
        // Space key ends the turn
        if (event.key === ' ') {
            event.preventDefault();
            handlers.onEndTurn?.();
        }
        
        // R key for ritual casting (bind)
        if (event.key === 'r' || event.key === 'R') {
            event.preventDefault();
            handlers.onRitualCast?.('bind');
            
            // Add a ritual cast effect at the unit's position
            if (state && state.unit && state.unit.pixel) {
                addRitualCastEffect(state.unit.pixel.x, state.unit.pixel.y, 'bind');
                
                // Set casting flag to show visual effect
                state.unit.castingRitual = true;
                setTimeout(() => {
                    state.unit.castingRitual = false;
                }, 1000); // Reset after 1 second
            }
        }
    };
    
    const onKeyUp = (event) => {
        // Remove key from the set
        state.input.keys.delete(event.key);
    };
    
    // Make sure canvas is properly attached to window.game before adding listeners
    if (typeof window !== 'undefined') {
        if (!window.game) {
            window.game = {};
        }
        window.game.canvas = canvas;
    }
    
    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('mouseleave', onMouseLeave);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    
    // Return a function to detach all event listeners
    return () => {
        canvas.removeEventListener('mousemove', onMouseMove);
        canvas.removeEventListener('mousedown', onMouseDown);
        canvas.removeEventListener('mouseup', onMouseUp);
        canvas.removeEventListener('mouseleave', onMouseLeave);
        window.removeEventListener('keydown', onKeyDown);
        window.removeEventListener('keyup', onKeyUp);
    };
}