/** 
 * @param {CanvasRenderingContext2D} ctx 
 * @param {object} state
 */
import { key, hexToPixel, hexCorners } from './hex.js';
import { PALETTE, VISIBILITY_ALPHA } from './palette.js';
import { ENCOUNTERS } from './encounters.js';

/** Slightly darken or lighten a hex colour without pulling in a colour lib. */
function shade(hex, amount) {
    const n = parseInt(hex.slice(1), 16);
    const clamp = (v) => Math.max(0, Math.min(255, Math.round(v)));
    const r = clamp(((n >> 16) & 255) + amount);
    const g = clamp(((n >> 8) & 255) + amount);
    const b = clamp((n & 255) + amount);
    return `rgb(${r},${g},${b})`;
}

/** 
 * @param {CanvasRenderingContext2D} ctx 
 * @param {object} state
 */
export function drawMap(ctx, state) {
    // Draw all tiles that are visible (explored or adjacent)
    for (const tile of state.tiles.values()) {
        if (tile.visibility !== 'unseen') {
            drawTileInternal(ctx, tile, state);
        }
    }
    
    // Draw encounter markers on explored tiles that have encounters
    for (const tile of state.tiles.values()) {
        if (tile.visibility === 'explored' && tile.encounter) {
            // Get the encounter type to determine marker appearance
            try {
                const encounter = ENCOUNTERS.find(e => e.id === tile.encounter);
                if (encounter) {
                    const { x, y } = hexToPixel(tile.q, tile.r);
                    ctx.save();
                    ctx.translate(x, y);
                    const corners = hexCorners(0, 0);
                    drawEncounterMarker(ctx, corners, encounter.type);
                    ctx.restore();
                }
            } catch (e) {
                // If ENCOUNTERS is not properly loaded or encounter not found, skip
                // This prevents the whole rendering from failing due to one missing piece
            }
        }
    }
    
    // No transition pass. Stacking a translucent gradient hex over every
    // terrain boundary washed the palette into one undifferentiated green and
    // buried the hex edges — the terrain stopped reading, which is the one
    // thing the map has to do.

    const hover = state.input.hoverHex;
    if (hover && state.tiles.has(key(hover.q, hover.r))) {
        // Add a solid highlight effect to the hover hex with enhanced visibility
        drawHighlight(ctx, hover, PALETTE.HIGHLIGHT, 5);
        
        // Draw an additional bright overlay for better visibility on all terrains
        ctx.save();
        const { x, y } = hexToPixel(hover.q, hover.r);
        const corners = hexCorners(x, y);
        
        // Create a bright overlay with pulsing effect
        const pulse = Math.sin(Date.now() / 200) * 0.3 + 0.7; // Pulsing between 0.4 and 1.0
        ctx.globalAlpha = 0.3 * pulse;
        ctx.fillStyle = '#ffffff';
        tracePath(ctx, corners);
        ctx.fill();
        ctx.restore();
    }
    drawHighlight(ctx, state.input.selectedHex, PALETTE.SELECTED, 3);
}

function drawTileInternal(ctx, tile, state) {
    const { x, y } = hexToPixel(tile.q, tile.r);
    
    // Draw the hex with its terrain color
    ctx.save();
    ctx.translate(x, y);
    
    // Apply visibility alpha directly to the context
    ctx.globalAlpha = VISIBILITY_ALPHA[tile.visibility];
    
    // Draw the main tile
    const corners = hexCorners(0, 0);
    ctx.fillStyle = tile.variation;
    tracePath(ctx, corners);
    ctx.fill();

    // A band in the terrain's own colour keeps neighbouring tiles of the same
    // type from fusing into one flat mass, without muddying the palette the
    // way a cross-terrain gradient does.
    tracePath(ctx, corners);
    ctx.strokeStyle = shade(tile.terrain.color, -22);
    ctx.lineWidth = 2;
    ctx.stroke();

    // Explored tiles carry a terrain glyph, so the map reads by shape and not
    // by colour alone.
    if (tile.visibility === 'explored') {
        ctx.fillStyle = shade(tile.terrain.color, 34);
        ctx.strokeStyle = ctx.fillStyle;
        drawTerrainMark(ctx, tile);
    }

    ctx.restore();
}

/** A small procedural glyph per terrain, drawn at the tile's local origin. */
function drawTerrainMark(ctx, tile) {
    switch (tile.terrain.id) {
        case 'forest':
            for (const dx of [-8, 0, 8]) {
                ctx.beginPath();
                ctx.moveTo(dx, 7);
                ctx.lineTo(dx - 4, 1);
                ctx.lineTo(dx + 4, 1);
                ctx.closePath();
                ctx.fill();
            }
            break;
        case 'mountain':
            ctx.beginPath();
            ctx.moveTo(-10, 7);
            ctx.lineTo(-1, -7);
            ctx.lineTo(8, 7);
            ctx.closePath();
            ctx.fill();
            break;
        case 'water':
            ctx.lineWidth = 1.5;
            for (const dy of [-3, 3]) {
                ctx.beginPath();
                ctx.moveTo(-9, dy);
                ctx.quadraticCurveTo(0, dy - 4, 9, dy);
                ctx.stroke();
            }
            break;
        case 'swamp':
            for (const [dx, dy] of [[-6, 2], [5, -2], [0, 6]]) {
                ctx.beginPath();
                ctx.arc(dx, dy, 2.4, 0, Math.PI * 2);
                ctx.fill();
            }
            break;
        case 'fae_land':
            ctx.beginPath();
            for (let i = 0; i < 5; i++) {
                const a = (Math.PI * 2 * i) / 5 - Math.PI / 2;
                const px = Math.cos(a) * 8;
                const py = Math.sin(a) * 8;
                i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py);
            }
            ctx.closePath();
            ctx.fill();
            break;
        default:
            // Grassland stays bare; the absence of a mark is itself legible.
            break;
    }
}

/** 
 * Convert hex color to RGB object
 */
function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : { r: 0, g: 0, b: 0 };
}

/**
 * Draw a highlight around a hex
 */
export function drawHighlight(ctx, hex, color, lineWidth) {
    if (!hex) return;
    
    const { x, y } = hexToPixel(hex.q, hex.r);
    const corners = hexCorners(x, y);
    
    ctx.save();
    ctx.globalAlpha = 0.8;
    ctx.strokeStyle = color;
    ctx.lineWidth = lineWidth;
    tracePath(ctx, corners);
    ctx.stroke();
    ctx.restore();
}

/**
 * Draw an encounter marker on a hex
 */
export function drawEncounterMarker(ctx, corners, type) {
    // Simple marker - in a full implementation this would be more detailed
    ctx.save();
    ctx.globalAlpha = 0.8;
    ctx.fillStyle = PALETTE.ENCOUNTER;
    
    // Draw a simple triangle marker based on encounter type
    if (type === 'threat') {
        // Draw a triangle for threat encounters - more visually distinct
        ctx.beginPath();
        ctx.moveTo(corners[0].x, corners[0].y);
        ctx.lineTo(corners[2].x, corners[2].y);
        ctx.lineTo(corners[4].x, corners[4].y);
        ctx.closePath();
        ctx.fill();
        
        // Add a border to make it more visible
        ctx.strokeStyle = PALETTE.BACKGROUND;
        ctx.lineWidth = 1;
        ctx.stroke();
    } else if (type === 'resource') {
        // Draw a circle for resource encounters - more visually distinct
        const centerX = (corners[0].x + corners[1].x + corners[2].x + corners[3].x + corners[4].x + corners[5].x) / 6;
        const centerY = (corners[0].y + corners[1].y + corners[2].y + corners[3].y + corners[4].y + corners[5].y) / 6;
        ctx.beginPath();
        ctx.arc(centerX, centerY, 8, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a border to make it more visible
        ctx.strokeStyle = PALETTE.BACKGROUND;
        ctx.lineWidth = 1;
        ctx.stroke();
    } else {
        // Default to a diamond shape - more visually distinct
        ctx.beginPath();
        ctx.moveTo(corners[0].x, corners[0].y);
        ctx.lineTo(corners[1].x, corners[1].y);
        ctx.lineTo(corners[2].x, corners[2].y);
        ctx.lineTo(corners[3].x, corners[3].y);
        ctx.closePath();
        ctx.fill();
        
        // Add a border to make it more visible
        ctx.strokeStyle = PALETTE.BACKGROUND;
        ctx.lineWidth = 1;
        ctx.stroke();
    }
    
    ctx.restore();
}

/**
 * Trace a path around the hex corners
 */
export function tracePath(ctx, corners) {
    ctx.beginPath();
    ctx.moveTo(corners[0].x, corners[0].y);
    for (let i = 1; i < corners.length; i++) {
        ctx.lineTo(corners[i].x, corners[i].y);
    }
    ctx.closePath();
}

// Removed: initParticleSystem() was an empty stub "for compatibility" with
// nothing, and drawFadeOverlay() read state.fade, a property that does not
// exist — it would have thrown the moment anything called it. Neither had a
// caller.