/** 
 * Mouse and keyboard handling, and hex picking.
 * 
 * Exports a single `attachInput(canvas, state, handlers)`. Nothing is bound at
 * import time — the previous build called addEventListener at module scope on a
 * canvas reference that did not exist yet, which killed the entire boot.
 *
 * Pure module: no DOM access and no side effects until attachInput is called.
 */

import { pixelToHex, key } from './hex.js';
import { moveUnitToHex } from './movement.js';

/** 
 * Convert a mouse event to canvas-space coordinates, accounting for CSS
 * scaling — the canvas is often displayed at a different size than its
 * backing store, and ignoring that puts the cursor on the wrong hex.
 */
function toCanvasSpace(canvas, event) {
    const rect = canvas.getBoundingClientRect();
    return {
      x: (event.clientX - rect.left) * (canvas.width / rect.width),
      y: (event.clientY - rect.top) * (canvas.height / rect.height),
    };
}

/** Canvas space -> world space -> hex. */
function hexAt(state, canvasX, canvasY) {
    return pixelToHex(canvasX - state.camera.x, canvasY - state.camera.y);
}

/**
 * @param {HTMLCanvasElement} canvas
 * @param {object} state
 * @param {{onSelect?:Function, onOption?:Function, onEndTurn?:Function}} handlers
 * @returns {Function} detach
 */
export function attachInput(canvas, state, handlers = {}) {
    const onMouseMove = (event) => {
        const p = toCanvasSpace(canvas, event);
        state.input.mouse.x = p.x;
        state.input.mouse.y = p.y;

        const hex = hexAt(state, p.x, p.y);
        state.input.hoverHex = state.tiles.has(key(hex.q, hex.r)) ? hex : null;
    };

    const onMouseDown = () => { state.input.mouse.down = true; };

    const onMouseUp = (event) => {
        state.input.mouse.down = false;
        const p = toCanvasSpace(canvas, event);
        
        // An open encounter swallows the click — the map is not interactive
        // while a decision is pending.
        if (handlers.onOption?.(p.x, p.y)) return;
        
        const hex = hexAt(state, p.x, p.y);
        if (!state.tiles.has(key(hex.q, hex.r))) return;

        // A unit-click test used to live here comparing canvas coordinates
        // against the unit's world-space pixel. Those are different spaces, so
        // the branch could only ever be dead code. Selecting the hex the unit
        // stands on already expresses "select the unit".
        state.input.selectedHex = hex;

        if (!moveUnitToHex(state, hex.q, hex.r)) {
            handlers.onHexClick?.(hex);
        }
    };

    const onMouseLeave = () => {
        state.input.hoverHex = null;
        state.input.mouse.down = false;
    };

    const onKeyDown = (event) => {
        state.input.keys.add(event.key);

        if (event.key === ' ' || event.key === 'Enter') {
            event.preventDefault();
            handlers.onEndTurn?.();
            return;
        }
        // Number keys resolve an open encounter without needing the mouse.
        const n = Number(event.key);
        if (Number.isInteger(n) && n >= 1 && n <= 9) handlers.onOptionIndex?.(n - 1);
    };

    const onKeyUp = (event) => { state.input.keys.delete(event.key); };

    canvas.addEventListener('mousemove', onMouseMove);
    canvas.addEventListener('mousedown', onMouseDown);
    canvas.addEventListener('mouseup', onMouseUp);
    canvas.addEventListener('mouseleave', onMouseLeave);
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);

    return function detach() {
        canvas.removeEventListener('mousemove', onMouseMove);
        canvas.removeEventListener('mousedown', onMouseDown);
        canvas.removeEventListener('mouseup', onMouseUp);
        canvas.removeEventListener('mouseleave', onMouseLeave);
        window.removeEventListener('keydown', onKeyDown);
        window.removeEventListener('keyup', onKeyUp);
    };
}

// Encounter hit-testing lives in hud.js, next to the code that draws the
// window, so the two can never disagree about where the buttons are.