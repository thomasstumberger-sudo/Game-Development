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
    // Draw background with carved bone effect
    const barPattern = cachedPattern('resource_bar', () => createCarvedBonePattern(ctx, width, height));
    ctx.fillStyle = barPattern;
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
    try {
        // Draw background with woad stain effect
        const rosterPattern = cachedPattern('tribe_roster', () => createCarvedBonePattern(ctx, width, height));
        ctx.fillStyle = rosterPattern;
        ctx.fillRect(x, y, width, height);
        
        // Draw border
        ctx.strokeStyle = PALETTE.BROWN_DARK;
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, width, height);
        
        // Draw title with carved effect
        ctx.fillStyle = PALETTE.BROWN_DARK;
        ctx.font = 'bold 14px Courier New';
        ctx.fillText('Tribe', x + 5, y + 20);
        
        // Draw population count
        ctx.fillStyle = PALETTE.BROWN_LIGHT;
        ctx.font = '12px Courier New';
        const population = state.resources?.population || 1;
        ctx.fillText(`Population: ${population}`, x + 5, y + 40);
        
        // Draw tribe members with woad-stain styling
        const memberCount = Math.min(population, 5);
        for (let i = 0; i < memberCount; i++) {
            ctx.fillStyle = PALETTE.BROWN_LIGHT;
            ctx.fillText(`Member ${i + 1}`, x + 5, y + 60 + i * 15);
        }
    } catch (error) {
        console.error('Error drawing tribe roster:', error);
    }
}

/** 
 * Draw the main resource HUD
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} state - Game state
 */
export function drawHUD(ctx, state) {
    try {
        if (!state || !ctx) return;
        
        // Draw background for HUD area with carved bone effect
        const hudPattern = cachedPattern('hud_background', () => createCarvedBonePattern(ctx, ctx.canvas.width, 120));
        ctx.fillStyle = hudPattern;
        ctx.fillRect(0, 0, ctx.canvas.width, 120);
        
        // Draw a decorative border around the HUD
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
        const food = state.resources?.food || 0;
        drawResourceBar(ctx, food, 100, 
                       startX, startY, barWidth, barHeight, PALETTE.FOOD, 'Food', state);
        
        // Draw water bar
        const water = state.resources?.water || 0;
        drawResourceBar(ctx, water, 100, 
                       startX, startY + barHeight + barSpacing, barWidth, barHeight, PALETTE.WATER_RES, 'Water', state);
        
        // Draw morale bar
        const morale = state.resources?.morale || 0;
        drawResourceBar(ctx, morale, 100, 
                       startX, startY + (barHeight + barSpacing) * 2, barWidth, barHeight, PALETTE.MORALE, 'Morale', state);
        
        // Draw magic bar
        const magic = state.unit?.magic || 0;
        const maxMagic = state.unit?.maxMagic || 4;
        drawResourceBar(ctx, magic, maxMagic, 
                       startX, startY + (barHeight + barSpacing) * 3, barWidth, barHeight, PALETTE.MAGIC, 'Magic', state);
        
        // Draw additional resources that are not in the bar system
        const additionalY = startY + (barHeight + barSpacing) * 4 + 10;
        
        // Draw population
        ctx.fillStyle = PALETTE.BROWN_LIGHT;
        ctx.font = '12px Courier New';
        const population = state.resources?.population || 1;
        ctx.fillText(`Population: ${population}`, startX - 30, additionalY);
        ctx.fillText(`${population}`, startX + barWidth + 5, additionalY);
        
        // Draw materials
        const materials = state.resources?.materials || 10;
        ctx.fillStyle = PALETTE.MATERIALS;
        ctx.fillText(`Materials: ${materials}`, startX - 30, additionalY + 15);
        ctx.fillText(`${materials}`, startX + barWidth + 5, additionalY + 15);
        
        // Draw health
        const health = state.unit?.health || 10;
        ctx.fillStyle = PALETTE.HEALTH;
        ctx.fillText(`Health: ${health}`, startX - 30, additionalY + 30);
        ctx.fillText(`${health}`, startX + barWidth + 5, additionalY + 30);
        
        // Draw weirdness
        const weirdness = state.resources?.weirdness || 0;
        ctx.fillStyle = PALETTE.BROWN_LIGHT;
        ctx.fillText(`Weirdness: ${weirdness}`, startX - 30, additionalY + 45);
        ctx.fillText(`${weirdness}`, startX + barWidth + 5, additionalY + 45);
        
        // Draw tribe roster in the bottom right corner
        const rosterWidth = 150;
        const rosterHeight = 100;
        drawTribeRoster(ctx, state, ctx.canvas.width - rosterWidth - 10, ctx.canvas.height - rosterHeight - 10, rosterWidth, rosterHeight);
    } catch (error) {
        console.error('Error drawing HUD:', error);
        // Draw a fallback error message
        ctx.fillStyle = '#ff0000';
        ctx.font = '24px Arial';
        ctx.fillText('HUD ERROR', 50, 50);
    }
}