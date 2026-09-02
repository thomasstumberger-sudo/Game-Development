/** 
 * Initialize terrain textures for rendering with improved visual distinction
 */
import { hexToPixel, worldToScreen, hexCorners } from './hex.js';
import { PALETTE, VISIBILITY_ALPHA } from './palette.js';

// Particle effects system for visual feedback
let particles = [];

export function initializeParticles() {
    // Initialize the particles array if needed
    if (typeof window !== 'undefined') {
        if (!window.game) {
            window.game = {};
        }
        if (!window.game.particles) {
            window.game.particles = [];
        }
        particles = window.game.particles;
    } else {
        // Fallback for non-browser environments
        particles = [];
    }
    
    // Ensure the global particles array is properly set up
    if (typeof window !== 'undefined' && window.game && window.game.particles) {
        particles = window.game.particles;
    }
}

export function getParticles() {
    return particles;
}

export function addParticle(x, y, color, size = 2, life = 30) {
    if (!particles) return;
    
    particles.push({
        x: x,
        y: y,
        life: life,
        maxLife: life,
        size: size,
        color: color,
        vx: (Math.random() - 0.5) * 2,
        vy: (Math.random() - 0.5) * 2
    });
}

export function updateParticles() {
    if (!particles || !Array.isArray(particles)) return;
    
    for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.life--;
        
        if (p.life <= 0) {
            particles.splice(i, 1);
        } else {
            if (p.vx !== undefined && p.vy !== undefined) {
                p.x += p.vx;
                p.y += p.vy;
                
                // Add some gravity effect to make particles fall
                p.vy += 0.05;
            }
        }
    }
}

export function drawParticles(ctx, state) {
    if (!particles || !Array.isArray(particles)) return;
    
    for (const p of particles) {
        const alpha = p.life / p.maxLife;
        ctx.globalAlpha = alpha;
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fill();
    }
    ctx.globalAlpha = 1.0;
}

/** 
 * Initialize terrain textures for the map.
 * This function creates pre-rendered tile textures with variations to make them visually distinct.
 */
export function initializeTerrainTextures() {
    // Pre-render tile textures with variations for each terrain type
    const size = 64; // Size of each tile texture
    
    // Create a global map to store tile textures
    if (typeof window !== 'undefined') {
        if (!window.game) {
            window.game = {};
        }
        if (!window.game.tileTextures) {
            window.game.tileTextures = new Map();
        }
    }
    
    const tileTextures = window.game.tileTextures;
    
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
                // Add grass-like texture with per-tile variation
                textureCtx.globalAlpha = 0.25;
                textureCtx.strokeStyle = PALETTE.GRASS_HIGHLIGHT;
                for (let i = 0; i < 20; i++) {
                    const x = Math.random() * size;
                    const y = Math.random() * size;
                    const len = Math.random() * 3 + 1;
                    textureCtx.beginPath();
                    textureCtx.moveTo(x, y);
                    textureCtx.lineTo(x + len, y + len/2);
                    textureCtx.stroke();
                }
                // Add some small pebbles or grass tufts
                textureCtx.globalAlpha = 0.3;
                for (let i = 0; i < 15; i++) {
                    const x = Math.random() * size;
                    const y = Math.random() * size;
                    textureCtx.beginPath();
                    textureCtx.arc(x, y, Math.random() * 1.5 + 0.5, 0, Math.PI * 2);
                    textureCtx.fill();
                }
                break;
            case 'forest':
                // Add tree-like texture
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.FOREST_HIGHLIGHT;
                for (let i = 0; i < 15; i++) {
                    const x = Math.random() * size;
                    const y = Math.random() * size;
                    const radius = Math.random() * 2 + 1;
                    textureCtx.beginPath();
                    textureCtx.arc(x, y, radius, 0, Math.PI * 2);
                    textureCtx.fill();
                }
                break;
            case 'water':
                // Add water-like ripples
                textureCtx.globalAlpha = 0.2;
                textureCtx.strokeStyle = PALETTE.WATER_HIGHLIGHT;
                for (let i = 0; i < 10; i++) {
                    const x = Math.random() * size;
                    const y = Math.random() * size;
                    const len = Math.random() * 5 + 3;
                    textureCtx.beginPath();
                    textureCtx.moveTo(x, y);
                    textureCtx.lineTo(x + len, y + Math.random() * 2 - 1);
                    textureCtx.stroke();
                }
                break;
            case 'mountain':
                // Add mountain-like texture with peaks
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.MOUNTAIN_HIGHLIGHT;
                for (let i = 0; i < 10; i++) {
                    const x = Math.random() * size;
                    const y = Math.random() * size;
                    const width = Math.random() * 3 + 1;
                    const height = Math.random() * 2 + 1;
                    textureCtx.fillRect(x, y, width, height);
                }
                break;
            case 'swamp':
                // Add swamp-like texture with muck
                textureCtx.globalAlpha = 0.25;
                textureCtx.fillStyle = PALETTE.SWAMP_HIGHLIGHT;
                for (let i = 0; i < 20; i++) {
                    const x = Math.random() * size;
                    const y = Math.random() * size;
                    const radius = Math.random() * 1.5 + 0.5;
                    textureCtx.beginPath();
                    textureCtx.arc(x, y, radius, 0, Math.PI * 2);
                    textureCtx.fill();
                }
                break;
            case 'fae_land':
                // Add fae-like texture with glowing elements
                textureCtx.globalAlpha = 0.3;
                textureCtx.fillStyle = PALETTE.FAE_HIGHLIGHT;
                for (let i = 0; i < 15; i++) {
                    const x = Math.random() * size;
                    const y = Math.random() * size;
                    const radius = Math.random() * 2 + 1;
                    textureCtx.beginPath();
                    textureCtx.arc(x, y, radius, 0, Math.PI * 2);
                    textureCtx.fill();
                }
                break;
        }
        
        // Store the texture in our global map
        tileTextures.set(terrainId, textureCanvas);
    }
}

/**
 * Draw a single hex tile with its texture and effects.
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} tile - Tile data
 * @param {number} x - Screen x position
 * @param {number} y - Screen y position
 */
export function drawHexTile(ctx, tile, x, y) {
    if (!tile || !ctx) return;
    
    // tile.terrain is a terrain object; the texture map is keyed by its string id.
    const terrainId = (tile.terrain && tile.terrain.id) || tile.terrain;
    const texture = window.game.tileTextures.get(terrainId);
    if (texture) {
        ctx.drawImage(texture, x - 32, y - 32);
    } else {
        // Fallback to simple drawing if no texture
        ctx.fillStyle = (tile.terrain && tile.terrain.color) || PALETTE.BACKGROUND;
        ctx.fillRect(x - 32, y - 32, 64, 64);
    }
    
    // Draw tile border if needed
    ctx.strokeStyle = PALETTE.TILE_BORDER;
    ctx.lineWidth = 1;
    ctx.strokeRect(x - 32, y - 32, 64, 64);
}

/**
 * Draw the map with all effects including visibility and transitions.
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 * @param {object} state - Game state
 */
export function drawMapWithEffects(ctx, state) {
    if (!state || !ctx) return;
    
    // Clear the canvas with background color
    ctx.fillStyle = PALETTE.BACKGROUND;
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    
    // Draw tiles in a grid pattern
    const tiles = Array.from(state.tiles.values());
    
    for (const tile of tiles) {
        const pixel = hexToPixel(tile.q, tile.r);
        const screenPos = worldToScreen(pixel.x, pixel.y, state.camera);
        
        if (screenPos) {
            // Determine visibility alpha - use the visibility property that's set in the tile
            let alpha = 1.0;
            if (tile.visibility === 'explored') {
                alpha = VISIBILITY_ALPHA.explored;
            } else if (tile.visibility === 'adjacent') {
                alpha = VISIBILITY_ALPHA.adjacent;
            } else if (tile.visibility === 'outer') {
                alpha = VISIBILITY_ALPHA.outer;
            } else {
                alpha = VISIBILITY_ALPHA.unseen;
            }
            
            // Save context for alpha
            ctx.save();
            ctx.globalAlpha = alpha;
            
            drawHexTile(ctx, tile, screenPos.x, screenPos.y);
            
            // Restore context
            ctx.restore();
        }
    }
}

export function addMovementEffect(x, y) {
    // Add a particle effect at the given position when movement occurs
    for (let i = 0; i < 5; i++) {
        particles.push({
            x: x,
            y: y,
            life: 20,
            maxLife: 20,
            size: Math.random() * 2 + 1,
            color: PALETTE.HIGHLIGHT,
            vx: (Math.random() - 0.5) * 1,
            vy: (Math.random() - 0.5) * 1
        });
    }
}

export function addRitualCastEffect(x, y, ritualType) {
    // Add a particle effect at the given position when a ritual is cast
    let color = PALETTE.MAGIC;
    
    switch(ritualType) {
        case 'bind':
            color = PALETTE.FAERY_GREEN;
            break;
        case 'bargain':
            color = PALETTE.FAERY_BLUE;
            break;
        case 'banish':
            color = PALETTE.FAERY_PURPLE;
            break;
        default:
            color = PALETTE.MAGIC;
    }
    
    for (let i = 0; i < 15; i++) {
        particles.push({
            x: x,
            y: y,
            life: 40,
            maxLife: 40,
            size: Math.random() * 3 + 1,
            color: color,
            vx: (Math.random() - 0.5) * 2,
            vy: (Math.random() - 0.5) * 2
        });
    }
}

export function addEncounterEffect(x, y) {
    // Add a particle effect at the given position when an encounter occurs
    for (let i = 0; i < 10; i++) {
        particles.push({
            x: x,
            y: y,
            life: 30,
            maxLife: 30,
            size: Math.random() * 4 + 2,
            color: PALETTE.ENCOUNTER
        });
    }
}

export function addMagicEffect(x, y) {
    // Add a particle effect at the given position for magic effects
    for (let i = 0; i < 8; i++) {
        particles.push({
            x: x,
            y: y,
            life: 25,
            maxLife: 25,
            size: Math.random() * 3 + 1,
            color: PALETTE.MAGIC,
            vx: (Math.random() - 0.5) * 3,
            vy: (Math.random() - 0.5) * 3
        });
    }
}

export function addRitualResultEffect(x, y, success) {
    // Add a particle effect at the given position when a ritual result occurs
    const color = success ? PALETTE.SUCCESS : PALETTE.FAILURE;
    
    for (let i = 0; i < 12; i++) {
        particles.push({
            x: x,
            y: y,
            life: 35,
            maxLife: 35,
            size: Math.random() * 4 + 2,
            color: color,
            vx: (Math.random() - 0.5) * 3,
            vy: (Math.random() - 0.5) * 3
        });
    }
}

export function addHoverEffect(x, y) {
    // Add a particle effect at the given position when hovering over a hex
    particles.push({
        x: x,
        y: y,
        life: 20,
        maxLife: 20,
        size: Math.random() * 3 + 1,
        color: PALETTE.HOVER_HIGHLIGHT,
        vx: (Math.random() - 0.5) * 1,
        vy: (Math.random() - 0.5) * 1
    });
}

// Add a simple test to make sure we're drawing something
export function drawTestMap(ctx, state) {
    // Simple test - draw a background color to ensure the canvas is being drawn
    ctx.fillStyle = '#141018';
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    
    if (state && state.tiles) {
        // Draw a simple tile to make sure rendering works
        const testTile = Array.from(state.tiles.values())[0];
        if (testTile) {
            const pixel = hexToPixel(testTile.q, testTile.r);
            const screenPos = worldToScreen(pixel.x, pixel.y, state.camera);
            if (screenPos) {
                drawHexTile(ctx, testTile, screenPos.x, screenPos.y);
            }
        }
    }
}

// Fade state tracking
let fadeState = {
    active: false,
    alpha: 0,
    direction: 'in', // 'in' or 'out'
    duration: 0,
    startTime: 0
};

/**
 * Start a screen fade transition
 * @param {string} direction - 'in' for fade in, 'out' for fade out
 * @param {number} duration - Duration of the fade in milliseconds
 */
export function startFade(direction = 'out', duration = 500) {
    // Set up fade state
    fadeState.active = true;
    fadeState.direction = direction;
    fadeState.duration = duration;
    fadeState.startTime = Date.now();
    
    // Set the inTransition flag in game state if available
    if (typeof window !== 'undefined' && window.game && window.game.state) {
        window.game.state.inTransition = true;
    }
}

/**
 * Update fade state
 */
export function updateFade() {
    if (!fadeState.active) return;
    
    const now = Date.now();
    const elapsed = now - fadeState.startTime;
    
    if (elapsed >= fadeState.duration) {
        // Fade complete
        fadeState.active = false;
        if (typeof window !== 'undefined' && window.game && window.game.state) {
            window.game.state.inTransition = false;
        }
        fadeState.alpha = fadeState.direction === 'out' ? 1 : 0;
    } else {
        // Calculate fade progress
        const progress = elapsed / fadeState.duration;
        if (fadeState.direction === 'out') {
            fadeState.alpha = progress; // Fade out: 0 -> 1
        } else {
            fadeState.alpha = 1 - progress; // Fade in: 1 -> 0
        }
    }
}

/**
 * Draw the current fade overlay
 * @param {CanvasRenderingContext2D} ctx - Canvas context
 */
export function drawFade(ctx) {
    if (!fadeState.active || fadeState.alpha <= 0) return;
    
    ctx.globalAlpha = fadeState.alpha;
    ctx.fillStyle = PALETTE.BACKGROUND;
    ctx.fillRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.globalAlpha = 1.0;
}