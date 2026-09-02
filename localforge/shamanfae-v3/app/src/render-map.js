/** 
 * Draw all active particle effects
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 */
import { PALETTE, VISIBILITY_ALPHA } from './palette.js';
import { HEX_SIZE, hexToPixel, hexCorners, TERRAIN } from './hex.js';

// Pre-rendered tile textures for different terrain types
let tileTextures = new Map();
let particleEffects = [];

export { particleEffects };
export { tileTextures };

// Fade effect state
let fadeEffect = {
    active: false,
    color: '#000000',
    progress: 0,
    speed: 0
};

/** 
 * Initialize terrain textures for rendering
 */
export function initializeTerrainTextures() {
    // Pre-render tile textures with variations for each terrain type
    const size = 64; // Size of each tile texture
    
    // Create a simple tile texture for each terrain type - use the actual IDs from TERRAIN object
    const terrainTypes = ['grass', 'forest', 'water', 'mountain', 'swamp', 'fae_land'];
    
    for (const terrainId of terrainTypes) {
        // Create a canvas for this terrain type
        const textureCanvas = document.createElement('canvas');
        textureCanvas.width = size;
        textureCanvas.height = size;
        const textureCtx = textureCanvas.getContext('2d');
        
        if (!textureCtx) continue;
        
        textureCtx.imageSmoothingEnabled = false;
        
        // Find the actual color from PALETTE using the terrain ID
        let color = null;
        switch(terrainId) {
            case 'grass': color = PALETTE.GRASS; break;
            case 'forest': color = PALETTE.FOREST; break;
            case 'water': color = PALETTE.WATER; break;
            case 'mountain': color = PALETTE.MOUNTAIN; break;
            case 'swamp': color = PALETTE.SWAMP; break;
            case 'fae_land': color = PALETTE.FAE_LAND; break;
        }
        
        if (!color) continue;
        
        // Draw the base terrain color
        textureCtx.fillStyle = color;
        textureCtx.fillRect(0, 0, size, size);
        
        // Add some variation to make tiles more visually distinct
        switch(terrainId) {
            case 'grass':
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.GRASS_V1;
                textureCtx.fillRect(0, 0, size, size);
                break;
            case 'forest':
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.FOREST_V1;
                textureCtx.fillRect(0, 0, size, size);
                break;
            case 'water':
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.WATER_V1;
                textureCtx.fillRect(0, 0, size, size);
                break;
            case 'mountain':
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.MOUNTAIN_V1;
                textureCtx.fillRect(0, 0, size, size);
                break;
            case 'swamp':
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.SWAMP_V1;
                textureCtx.fillRect(0, 0, size, size);
                break;
            case 'fae_land':
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.FAE_V1;
                textureCtx.fillRect(0, 0, size, size);
                break;
        }
        
        // Add a subtle highlight effect
        textureCtx.globalAlpha = 0.2;
        textureCtx.fillStyle = PALETTE.TILE_BORDER;
        textureCtx.fillRect(0, 0, size, size);
        
        // Store the texture using the actual terrain ID
        tileTextures.set(terrainId, textureCanvas);
    }
    
    // Make sure we're setting it in the global window object too for access from main.js
    if (typeof window !== 'undefined') {
        window.game = window.game || {};
        window.game.tileTextures = tileTextures;
    }
}

/** 
 * Draw a single hex tile with proper rendering
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} tile - Tile data
 * @param {number} screenX - Screen X coordinate
 * @param {number} screenY - Screen Y coordinate
 */
export function drawHexTile(ctx, tile, screenX, screenY) {
    if (!tile || !tile.terrain) return;
    
    const corners = hexCorners(tile.q, tile.r);
    
    // Draw the hex with proper fill and stroke
    ctx.beginPath();
    
    // Move to first corner
    ctx.moveTo(corners[0].x, corners[0].y);
    
    // Draw lines to remaining corners
    for (let i = 1; i < 6; i++) {
        ctx.lineTo(corners[i].x, corners[i].y);
    }
    
    // Close the path
    ctx.closePath();
    
    // Set fill color with visibility alpha
    let alpha = 1.0;
    switch(tile.visibility) {
        case 'explored':
            alpha = VISIBILITY_ALPHA.explored;
            break;
        case 'adjacent':
            alpha = VISIBILITY_ALPHA.adjacent;
            break;
        case 'outer':
            alpha = VISIBILITY_ALPHA.outer;
            break;
        case 'unseen':
            alpha = VISIBILITY_ALPHA.unseen;
            break;
    }
    
    // Check if we have a pre-rendered texture for this terrain type
    const texture = tileTextures.get(tile.terrain.id);
    if (texture) {
        // Use the texture instead of drawing directly
        ctx.globalAlpha = alpha;
        ctx.drawImage(texture, screenX - 32, screenY - 32, 64, 64);
    } else {
        // Fallback to direct drawing with variation
        console.log('No texture for terrain:', tile.terrain.id, 'using fallback');
        const baseColor = tile.terrain.color;
        ctx.fillStyle = baseColor;
        ctx.globalAlpha = alpha;
        ctx.fill();
        
        // Add a subtle border to make edges clean and prevent hard seams
        ctx.strokeStyle = PALETTE.TILE_BORDER;
        ctx.lineWidth = 1;
        ctx.stroke();
    }
    
    // Draw the hex border with visibility consideration
    if (tile.visibility !== 'unseen') {
        ctx.strokeStyle = PALETTE.TILE_BORDER;
        ctx.lineWidth = 1;
        ctx.stroke();
    }
}

/** 
 * Draw the map with effects
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} state - Game state
 */
export function drawMapWithEffects(ctx, state) {
    if (!ctx || !state || !state.tiles) return;
    
    // Draw fade effect if active
    if (fadeEffect && fadeEffect.active) {
        drawFade(ctx, state);
    }
    
    // Draw the tiles
    for (const [key, tile] of state.tiles.entries()) {
        const pixel = hexToPixel(tile.q, tile.r);
        if (!pixel) continue;
        
        // Skip drawing off-screen tiles
        if (pixel.x < -100 || pixel.x > state.width + 100 || 
            pixel.y < -100 || pixel.y > state.height + 100) {
            continue;
        }
        
        const screenX = pixel.x + state.camera.x;
        const screenY = pixel.y + state.camera.y;
        
        // Draw the hex tile
        drawHexTile(ctx, tile, screenX, screenY);
    }
}

/** 
 * Update particles
 */
export function updateParticles() {
    for (let i = particleEffects.length - 1; i >= 0; i--) {
        const effect = particleEffects[i];
        effect.x += effect.speedX;
        effect.y += effect.speedY;
        effect.life--;
        
        if (effect.life <= 0) {
            particleEffects.splice(i, 1);
        }
    }
}

/** 
 * Draw all active particle effects
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} state - Game state
 */
export function drawParticles(ctx, state) {
    if (!ctx || !state) return;
    
    for (const effect of particleEffects) {
        // Skip effects that are not visible
        if (effect.life <= 0) continue;
        
        ctx.globalAlpha = effect.life / effect.maxLife;
        ctx.fillStyle = effect.color;
        
        // Draw different types of particles
        switch(effect.type) {
            case 'movement':
                ctx.beginPath();
                ctx.arc(effect.x, effect.y, effect.size, 0, Math.PI * 2);
                ctx.fill();
                break;
            case 'ritual_cast':
                ctx.beginPath();
                ctx.arc(effect.x, effect.y, effect.size, 0, Math.PI * 2);
                ctx.fill();
                break;
            case 'ritual_result':
                ctx.beginPath();
                ctx.arc(effect.x, effect.y, effect.size, 0, Math.PI * 2);
                ctx.fill();
                break;
            case 'ritual_pulse':
                // Draw a pulsing circle
                ctx.beginPath();
                ctx.arc(effect.x, effect.y, effect.size, 0, Math.PI * 2);
                ctx.fill();
                break;
            case 'encounter':
                ctx.beginPath();
                ctx.arc(effect.x, effect.y, effect.size, 0, Math.PI * 2);
                ctx.fill();
                break;
            case 'magic':
                ctx.beginPath();
                ctx.arc(effect.x, effect.y, effect.size, 0, Math.PI * 2);
                ctx.fill();
                break;
        }
    }
    
    ctx.globalAlpha = 1.0;
}

/** 
 * Update fade effects
 */
export function updateFade() {
    // Fade effect logic would go here
    if (fadeEffect && fadeEffect.active) {
        fadeEffect.progress += fadeEffect.speed;
        if (fadeEffect.progress >= 1.0) {
            fadeEffect.active = false;
        }
    }
}

/** 
 * Start a fade effect
 */
export function startFade(color, duration = 30) {
    // Create a new fade effect
    fadeEffect = {
        active: true,
        color: color,
        progress: 0,
        speed: 1 / duration
    };
}

/** 
 * Add a movement effect at a position
 * @param {number} x - Screen X coordinate
 * @param {number} y - Screen Y coordinate
 */
export function addMovementEffect(x, y) {
    // Create multiple particle effects for movement
    for (let i = 0; i < 5; i++) {
        particleEffects.push({
            x: x,
            y: y,
            size: Math.random() * 4 + 2,
            speedX: (Math.random() - 0.5) * 2,
            speedY: (Math.random() - 0.5) * 2,
            life: 25,
            maxLife: 25,
            color: PALETTE.SHAMAN_CHIEF,
            type: 'movement'
        });
    }
}

/** 
 * Add a ritual cast effect at a position
 * @param {number} x - Screen X coordinate
 * @param {number} y - Screen Y coordinate
 */
export function addRitualCastEffect(x, y) {
    // Create multiple particle effects for the ritual casting
    for (let i = 0; i < 15; i++) {
        particleEffects.push({
            x: x,
            y: y,
            size: Math.random() * 8 + 4,
            speedX: (Math.random() - 0.5) * 4,
            speedY: (Math.random() - 0.5) * 4,
            life: 30,
            maxLife: 30,
            color: PALETTE.MAGIC,
            type: 'ritual_cast'
        });
    }
}

/** 
 * Add a ritual result effect at a position
 * @param {number} x - Screen X coordinate
 * @param {number} y - Screen Y coordinate
 * @param {boolean} success - Whether the ritual was successful
 */
export function addRitualResultEffect(x, y, success) {
    // Create particle effects for ritual result
    const color = success ? PALETTE.SUCCESS : PALETTE.FAILURE;
    const count = success ? 20 : 15;
    
    for (let i = 0; i < count; i++) {
        particleEffects.push({
            x: x,
            y: y,
            size: Math.random() * 6 + 2,
            speedX: (Math.random() - 0.5) * 3,
            speedY: (Math.random() - 0.5) * 3,
            life: 40,
            maxLife: 40,
            color: color,
            type: 'ritual_result'
        });
    }
    
    // Add a large pulse effect
    particleEffects.push({
        x: x,
        y: y,
        size: 0,
        speedX: 0,
        speedY: 0,
        life: 20,
        maxLife: 20,
        color: success ? PALETTE.SUCCESS : PALETTE.FAILURE,
        type: 'ritual_pulse',
        pulse: true
    });
}

/** 
 * Add an encounter effect at a position
 * @param {number} x - Screen X coordinate
 * @param {number} y - Screen Y coordinate
 */
export function addEncounterEffect(x, y) {
    // Create particle effects for encounters
    for (let i = 0; i < 10; i++) {
        particleEffects.push({
            x: x,
            y: y,
            size: Math.random() * 6 + 3,
            speedX: (Math.random() - 0.5) * 3,
            speedY: (Math.random() - 0.5) * 3,
            life: 30,
            maxLife: 30,
            color: PALETTE.ENCOUNTER,
            type: 'encounter'
        });
    }
}

/** 
 * Add a magic effect at a position
 * @param {number} x - Screen X coordinate
 * @param {number} y - Screen Y coordinate
 */
export function addMagicEffect(x, y) {
    // Create magic particle effects
    for (let i = 0; i < 8; i++) {
        particleEffects.push({
            x: x,
            y: y,
            size: Math.random() * 4 + 2,
            speedX: (Math.random() - 0.5) * 2,
            speedY: (Math.random() - 0.5) * 2,
            life: 25,
            maxLife: 25,
            color: PALETTE.MAGIC,
            type: 'magic'
        });
    }
}

/** 
 * Trigger a screen fade for transitions
 * @param {string} color - Color to fade to (default is black)
 * @param {number} duration - Fade duration in frames (default is 30)
 */
export function triggerTransitionFade(color = PALETTE.BACKGROUND, duration = 30) {
    startFade(color, duration);
}

/** 
 * Draw a screen fade effect
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} state - Game state
 */
export function drawFade(ctx, state) {
    if (!fadeEffect || !fadeEffect.active) return;
    
    // Draw the fade overlay
    ctx.globalAlpha = fadeEffect.progress;
    ctx.fillStyle = fadeEffect.color;
    ctx.fillRect(0, 0, state.width, state.height);
    ctx.globalAlpha = 1.0;
}