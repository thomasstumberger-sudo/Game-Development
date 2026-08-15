/** 
 * HUD drawing functions for the game.
 * 
 * Pure module: no DOM, no side effects on import.
 */
import { PALETTE } from './palette.js';

// Cache for patterns to avoid recreating them every frame
const patternCache = new Map();

/** 
 * Get or create a cached pattern
 * @param {string} key - Pattern cache key
 * @param {Function} factory - Function to create the pattern if not cached
 * @returns {CanvasPattern} The cached or created pattern
 */
function cachedPattern(key, factory) {
    if (patternCache.has(key)) {
        return patternCache.get(key);
    }
    
    const pattern = factory();
    patternCache.set(key, pattern);
    return pattern;
}

/** 
 * Create a carved bone pattern for UI elements
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} width - Pattern width
 * @param {number} height - Pattern height
 * @returns {CanvasPattern} The created pattern
 */
function createCarvedBonePattern(ctx, width, height) {
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const patternCtx = canvas.getContext('2d');
    
    if (!patternCtx) return null;
    
    // Fill with parchment background
    patternCtx.fillStyle = PALETTE.PARCHMENT;
    patternCtx.fillRect(0, 0, width, height);
    
    // Add subtle texture lines for carved bone effect
    patternCtx.strokeStyle = PALETTE.BROWN_DARK;
    patternCtx.lineWidth = 1;
    
    // Draw horizontal lines
    for (let y = 0; y < height; y += 8) {
        patternCtx.beginPath();
        patternCtx.moveTo(0, y);
        patternCtx.lineTo(width, y);
        patternCtx.stroke();
    }
    
    // Draw vertical lines
    for (let x = 0; x < width; x += 8) {
        patternCtx.beginPath();
        patternCtx.moveTo(x, 0);
        patternCtx.lineTo(x, height);
        patternCtx.stroke();
    }
    
    return patternCtx.createPattern(canvas, 'repeat');
}

/** 
 * Draw a resource bar with proper styling
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {number} current - Current resource value
 * @param {number} max - Maximum resource value
 * @param {number} x - X position
 * @param {number} y - Y position
 * @param {number} width - Bar width
 * @param {number} height - Bar height
 * @param {string} color - Bar color
 * @param {string} label - Resource label
 * @param {object} state - Game state
 */
function drawResourceBar(ctx, current, max, x, y, width, height, color, label, state) {
    // Draw background
    ctx.fillStyle = PALETTE.BROWN_DARKER;
    ctx.fillRect(x, y, width, height);
    
    // Draw fill
    const fillWidth = (current / max) * width;
    ctx.fillStyle = color;
    ctx.fillRect(x, y, fillWidth, height);
    
    // Draw border
    ctx.strokeStyle = PALETTE.BROWN_DARK;
    ctx.lineWidth = 1;
    ctx.strokeRect(x, y, width, height);
    
    // Draw label
    ctx.fillStyle = PALETTE.BROWN_DARK;
    ctx.font = '12px Courier New';
    ctx.fillText(label, x - 30, y + height / 2 + 4);
    
    // Draw value
    ctx.fillStyle = PALETTE.BROWN_LIGHT;
    ctx.fillText(`${current}/${max}`, x + width + 5, y + height / 2 + 4);
}

/** 
 * Draw the tribe roster with woad stain styling
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} state - Game state
 * @param {number} x - X position
 * @param {number} y - Y position
 * @param {number} width - Roster width
 * @param {number} height - Roster height
 */
function drawTribeRoster(ctx, state, x, y, width, height) {
    // Draw background with woad stain effect
    const rosterPattern = cachedPattern('tribe_roster', () => createCarvedBonePattern(ctx, width, height));
    ctx.fillStyle = rosterPattern;
    ctx.fillRect(x, y, width, height);
    
    // Draw border
    ctx.strokeStyle = PALETTE.BROWN_DARK;
    ctx.lineWidth = 2;
    ctx.strokeRect(x, y, width, height);
    
    // Draw title
    ctx.fillStyle = PALETTE.BROWN_DARK;
    ctx.font = 'bold 14px Courier New';
    ctx.fillText('Tribe', x + 5, y + 20);
    
    // Draw population count
    ctx.fillStyle = PALETTE.BROWN_LIGHT;
    ctx.font = '12px Courier New';
    ctx.fillText(`Population: ${state.resources.population || 1}`, x + 5, y + 40);
    
    // Draw morale indicator
    const morale = state.resources.morale || 50;
    ctx.fillText(`Morale: ${morale}%`, x + 5, y + 60);
    
    // Draw magic indicator
    ctx.fillText(`Magic: ${state.unit.magic}/${state.unit.maxMagic}`, x + 5, y + 80);
}

/** 
 * Draw the HUD with carved bone and woad stain styling
 * @param {CanvasRenderingContext2D} ctx
 * @param {object} state
 */
export function drawHUD(ctx, state) {
    if (!ctx || !state) return;
    
    // Create a background pattern for the HUD using the carved bone texture
    const hudPattern = cachedPattern('hud_background', () => createCarvedBonePattern(ctx, ctx.canvas.width, 120));
    ctx.fillStyle = hudPattern;
    ctx.fillRect(0, 0, ctx.canvas.width, 120);
    
    // Draw a border around the HUD
    ctx.strokeStyle = PALETTE.BROWN_DARK;
    ctx.lineWidth = 3;
    ctx.strokeRect(0, 0, ctx.canvas.width, 120);
    
    // Draw a decorative border at the top
    ctx.strokeStyle = PALETTE.BROWN_LIGHT;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, 20);
    ctx.lineTo(ctx.canvas.width, 20);
    ctx.stroke();
    
    // Draw resource bars with proper styling
    const barHeight = 18;
    const barWidth = ctx.canvas.width * 0.7;
    const barSpacing = 8;
    const startX = (ctx.canvas.width - barWidth) / 2;
    const startY = 30;
    
    // Draw food bar
    drawResourceBar(ctx, state.resources.food, 100, 
                   startX, startY, barWidth, barHeight, PALETTE.FOOD_COLOR, 'Food', state);
    
    // Draw water bar
    drawResourceBar(ctx, state.resources.water, 100, 
                   startX, startY + barHeight + barSpacing, barWidth, barHeight, PALETTE.WATER_COLOR, 'Water', state);
    
    // Draw morale bar
    drawResourceBar(ctx, state.resources.morale, 100, 
                   startX, startY + (barHeight + barSpacing) * 2, barWidth, barHeight, PALETTE.MORALE, 'Morale', state);
    
    // Draw magic bar
    drawResourceBar(ctx, state.unit.magic, state.unit.maxMagic, 
                   startX, startY + (barHeight + barSpacing) * 3, barWidth, barHeight, PALETTE.MAGIC, 'Magic', state);
    
    // Draw tribe roster in the bottom right corner
    const rosterWidth = 150;
    const rosterHeight = 100;
    drawTribeRoster(ctx, state, ctx.canvas.width - rosterWidth - 10, ctx.canvas.height - rosterHeight - 10, rosterWidth, rosterHeight);
}