/** 
 * Main game loop and initialization.
 * 
 * Pure module: no DOM, no side effects on import.
 */
import { PALETTE } from './palette.js';
import { HEX_SIZE, MAP_RADIUS, generateMap, updateVisibility, pixelToHex, hexToPixel } from './hex.js';
import { initializeTerrainTextures, drawMapWithEffects, addMovementEffect, addRitualCastEffect, addRitualResultEffect, addEncounterEffect, addMagicEffect, updateParticles, drawParticles, triggerTransitionFade, updateFade, startFade } from './render-map.js';
import { initUnitSprites, drawUnitWithEffects } from './render-unit.js';
import { attachInput, tileAt } from './input.js';
import { createState, update, applyDelta, RESOURCE_FEEDBACK } from './state.js';
import { moveUnitToHex, updateMove } from './movement.js';
import { drawHUD } from './hud.js';
import { EncounterSystem, castRitual } from './encounters.js';

// Game state and rendering
let gameLoopId = null;
let lastTime = 0;
let encounterSystem = null; // Make encounter system globally accessible

// Debug: Check if we have a valid canvas early on
console.log('Main.js loaded, checking canvas availability');

/**
 * Main game loop.
 * @param {number} timestamp - Animation frame timestamp
 */
function gameLoop(timestamp) {
    // Check if we have a valid game state and canvas
    if (!window.game || !window.game.canvas || !window.game.state) {
        // Try to wait for initialization
        console.warn('Game not properly initialized, retrying in 100ms...');
        setTimeout(() => {
            gameLoopId = requestAnimationFrame(gameLoop);
        }, 100);
        return;
    }
    
    const canvas = window.game.canvas;
    const state = window.game.state;
    
    // Make sure canvas is valid
    if (!canvas || !canvas.getContext) {
        console.warn('Canvas not available');
        gameLoopId = requestAnimationFrame(gameLoop);
        return;
    }
    
    // Calculate delta time
    const dt = timestamp - lastTime;
    lastTime = timestamp;
    
    const ctx = canvas.getContext('2d');
    if (!ctx) {
        console.warn('Failed to get canvas context');
        gameLoopId = requestAnimationFrame(gameLoop);
        return;
    }
    
    // Clear the canvas
    ctx.fillStyle = PALETTE.BACKGROUND;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    // Update game state
    update(state, dt);
    
    // Update movement if needed - add safety check for unit existence
    if (state && state.unit && state.unit.moving) {
        updateMove(state.unit, dt);
    }
    
    // Update particles
    updateParticles();
    
    // Draw the map with effects
    drawMapWithEffects(ctx, state);
    
    // Draw particles
    drawParticles(ctx, state);
    
    // Draw the unit
    drawUnitWithEffects(ctx, state);
    
    // Draw HUD
    drawHUD(ctx, state);
    
    // Continue the game loop
    gameLoopId = requestAnimationFrame(gameLoop);
}

/**
 * Initialize the game.
 * @param {HTMLCanvasElement} canvas - The game canvas
 */
function initGame(canvas) {
    try {
        console.log('Initializing game with canvas:', canvas);
        console.log('Canvas width:', canvas.width, 'height:', canvas.height);
        
        // Create game state first
        const state = createState(canvas, 42); // Use a fixed seed for reproducibility
        
        console.log('Created game state');
        console.log('State tiles:', state.tiles ? 'Found' : 'Missing');
        console.log('State unit:', state.unit ? 'Found' : 'Missing');
        
        // Initialize terrain textures - make sure this is called before any drawing
        try {
            console.log('About to initialize terrain textures');
            initializeTerrainTextures();
            console.log('Terrain textures initialized successfully');
            // Check if we have tile textures properly set up
            if (typeof window !== 'undefined' && window.game && window.game.tileTextures) {
                console.log('Tile textures count:', window.game.tileTextures.size);
            } else {
                console.log('Tile textures not available in window.game');
            }
        } catch (e) {
            console.error('Failed to initialize terrain textures:', e);
            // Fallback to simple drawing
            console.log('Falling back to simple drawing');
        }
        
        // Initialize unit sprites
        try {
            console.log('About to initialize unit sprites');
            initUnitSprites();
            console.log('Unit sprites initialized successfully');
        } catch (e) {
            console.error('Failed to initialize unit sprites:', e);
        }
        
        // Update visibility for the starting position
        updateVisibility(state.tiles, state.unit.q, state.unit.r);
        console.log('Updated visibility');
        
        // Make sure the unit pixel is properly set
        const unitPixel = hexToPixel(state.unit.q, state.unit.r);
        if (unitPixel && typeof unitPixel.x === 'number' && typeof unitPixel.y === 'number') {
            state.unit.pixel = unitPixel;
            console.log('Unit pixel set to:', unitPixel);
        } else {
            console.warn('Could not set unit pixel');
        }
        
        // Set up input handling
        const detachInput = attachInput(canvas, state, {
            onHexClick: (hex) => {
                console.log('Hex clicked in main:', hex.q, hex.r);
                if (state && state.phase === 'decision') {
                    console.log('Attempting to move unit to hex:', hex.q, hex.r);
                    const success = moveUnitToHex(state, hex.q, hex.r);
                    console.log('Move result:', success ? 'Success' : 'Failed');
                }
            },
            onRitualCast: (ritualType) => {
                console.log('Casting ritual:', ritualType);
                // Use the castRitual function that's already imported at the top
                if (typeof castRitual !== 'undefined') {
                    const success = castRitual(state, ritualType);
                    if (success) {
                        console.log(`Successfully cast ${ritualType}`);
                    } else {
                        console.log(`Failed to cast ${ritualType}`);
                    }
                }
            }
        });
        
        // Set up the global game state reference AFTER attaching input
        if (typeof window !== 'undefined') {
            // Make sure we have a valid canvas reference
            if (!window.game.canvas) {
                window.game.canvas = canvas;
            }
            // Make sure we have a valid state reference  
            if (!window.game.state) {
                window.game.state = state;
            }
            window.game.detachInput = detachInput;
        }
        console.log('Attached input handlers');
        
        // Start the game loop after everything is initialized
        if (!gameLoopId) {
            gameLoopId = requestAnimationFrame(gameLoop);
            console.log('Started game loop');
        }
        
        // Remove loading overlay - this was missing in the original code
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
        
        console.log('Game initialized successfully');
    } catch (error) {
        console.error('Failed to initialize game:', error);
        if (canvas && canvas.getContext) {
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = PALETTE.BACKGROUND;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#ff0000';
            ctx.font = '16px Arial';
            ctx.fillText('Game initialization failed. Check console for details.', 10, 30);
        }
        // Make sure to remove the loading overlay even on failure
        const loadingOverlay = document.getElementById('loading-overlay');
        if (loadingOverlay) {
            loadingOverlay.style.display = 'none';
        }
    }
}

// Initialize the game when the page loads
window.addEventListener('load', () => {
    console.log('Page loaded, initializing game');
    
    const canvas = document.getElementById('game');
    if (!canvas) {
        console.error('Canvas element not found');
        return;
    }
    
    // Set canvas size to match window
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    
    // Make sure we have a valid canvas before proceeding
    if (canvas.width <= 0 || canvas.height <= 0) {
        console.warn('Canvas has invalid dimensions, setting default');
        canvas.width = 800;
        canvas.height = 600;
    }
    
    try {
        console.log('Starting initGame with canvas:', canvas);
        console.log('Canvas width:', canvas.width, 'height:', canvas.height);
        
        // Initialize window.game early to prevent undefined errors
        if (typeof window !== 'undefined') {
            window.game = window.game || {};
            // Make sure canvas is set here - this was the main issue!
            window.game.canvas = canvas;
        }
        
        initGame(canvas);
    } catch (error) {
        console.error('Failed to initialize game:', error);
        if (canvas && canvas.getContext) {
            const ctx = canvas.getContext('2d');
            ctx.fillStyle = PALETTE.BACKGROUND;
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.fillStyle = '#ff0000';
            ctx.font = '16px Arial';
            ctx.fillText('Game initialization failed. Check console for details.', 10, 30);
        }
    }
});

// Make sure we're properly handling errors during initialization
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    
    // If we have a canvas, try to draw an error message
    if (window.game && window.game.canvas && window.game.canvas.getContext) {
        const ctx = window.game.canvas.getContext('2d');
        if (ctx) {
            ctx.fillStyle = '#ff0000';
            ctx.fillRect(0, 0, window.game.canvas.width, window.game.canvas.height);
            ctx.fillStyle = '#ffffff';
            ctx.font = '16px Arial';
            ctx.fillText('Game error occurred. Check console for details.', 10, 30);
        }
    }
});

// Handle window resize
window.addEventListener('resize', () => {
    if (window.game && window.game.canvas) {
        const canvas = window.game.canvas;
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
        
        // Update state dimensions if needed
        if (window.game.state) {
            window.game.state.width = canvas.width;
            window.game.state.height = canvas.height;
        }
    }
});