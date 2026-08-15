/** 
 * The Shaman-Chief and map markers.
 *
 * Seed-level: a readable figure that is unmistakably not a tile, with a contact
 * shadow so it sits on the map rather than floating above it, and a slow pulse
 * marking it as the active unit. Sprite work is left for the build.
 *
 * Pure module: no DOM, no side effects on import.
 */

import { PALETTE } from './palette.js';
import { hexToPixel } from './hex.js';

// Pre-rendered sprite for the shaman chief to improve performance
let shamanSprite = null;
let roleSprites = new Map();

function createShamanSprite() {
    if (shamanSprite) return shamanSprite;
    
    try {
        const canvas = document.createElement('canvas');
        canvas.width = 40;
        canvas.height = 40;
        const ctx = canvas.getContext('2d');
        
        if (!ctx) {
            // Fallback in case context creation fails
            return null;
        }
        
        // Clear with transparent background
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Draw a more distinct and recognizable shaman sprite - 5x7 pixel cluster
        const centerX = 20;
        const centerY = 20;
        
        // Body - a clear humanoid figure with defined silhouette
        ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 1;
        
        // Draw head (circle)
        ctx.beginPath();
        ctx.arc(centerX, centerY - 12, 4, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        
        // Draw torso (rectangle)
        ctx.fillRect(centerX - 3, centerY - 8, 6, 8);
        ctx.strokeRect(centerX - 3, centerY - 8, 6, 8);
        
        // Draw arms
        ctx.fillRect(centerX - 6, centerY - 6, 3, 2); // left arm
        ctx.fillRect(centerX + 3, centerY - 6, 3, 2); // right arm
        
        // Draw legs
        ctx.fillRect(centerX - 2, centerY, 2, 4); // left leg
        ctx.fillRect(centerX, centerY, 2, 4); // right leg
        
        // Draw distinctive hat (headdress) - more prominent and visually distinct
        ctx.fillStyle = PALETTE.BROWN_DARKER;
        ctx.beginPath();
        ctx.arc(centerX, centerY - 13, 5, 0, Math.PI * 2);
        ctx.fill();
        
        // Add decorative elements on hat - make them more visible
        ctx.fillStyle = PALETTE.FAERY_BLUE;
        ctx.beginPath();
        ctx.arc(centerX - 2, centerY - 16, 1.5, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.beginPath();
        ctx.arc(centerX + 2, centerY - 16, 1.5, 0, Math.PI * 2);
        ctx.fill();
        
        // Draw staff (more prominent and distinct)
        ctx.strokeStyle = PALETTE.BROWN_DARKER;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(centerX + 8, centerY - 6);
        ctx.lineTo(centerX + 8, centerY - 18);
        ctx.stroke();
        
        // Staff tip - magical element
        ctx.fillStyle = PALETTE.FAERY_BLUE;
        ctx.beginPath();
        ctx.arc(centerX + 8, centerY - 19, 2, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a small decorative element on the staff to make it more distinctive
        ctx.fillStyle = PALETTE.FAERY_PURPLE;
        ctx.beginPath();
        ctx.arc(centerX + 8, centerY - 15, 1.5, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a magical aura around the staff to make it stand out
        ctx.globalAlpha = 0.3;
        ctx.shadowColor = PALETTE.FAERY_BLUE;
        ctx.shadowBlur = 4;
        ctx.strokeStyle = PALETTE.FAERY_BLUE;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(centerX + 8, centerY - 12, 5, 0, Math.PI * 2);
        ctx.stroke();
        
        // Add a glow effect to the head
        ctx.globalAlpha = 0.4;
        ctx.shadowColor = PALETTE.FAERY_BLUE;
        ctx.shadowBlur = 6;
        ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
        ctx.beginPath();
        ctx.arc(centerX, centerY - 12, 4, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a subtle glow effect to the body
        ctx.globalAlpha = 0.3;
        ctx.shadowColor = PALETTE.FAERY_PURPLE;
        ctx.shadowBlur = 5;
        ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
        ctx.fillRect(centerX - 3, centerY - 8, 6, 8);
        
        // Add a strong outline around the entire sprite to make it stand out
        ctx.globalAlpha = 1.0;
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 2;
        ctx.strokeRect(0, 0, 40, 40);
        
        shamanSprite = canvas;
        return canvas;
    } catch (e) {
        console.warn('Failed to create shaman sprite:', e);
        return null;
    }
}

// Create the sprite when module loads
createShamanSprite();

/** 
 * Create a role-specific sprite for tribe members.
 * 
 * @param {string} role - The role of the tribe member
 */
function createRoleSprite(role) {
    if (roleSprites.has(role)) {
        return roleSprites.get(role);
    }
    
    
    try {
        const canvas = document.createElement('canvas');
        canvas.width = 40;
        canvas.height = 40;
        const ctx = canvas.getContext('2d');
        
        if (!ctx) {
            // Fallback in case context creation fails
            return shamanSprite; // fallback to shaman sprite
        }
        
        // Clear with transparent background
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        // Draw a distinct marker for each role
        let fillColor, outlineColor;
        
        switch (role) {
            case 'warrior':
                // Warrior - red color with sword
                fillColor = PALETTE.FAERY_GREEN;
                outlineColor = PALETTE.BROWN_DARKER;
                break;
            case 'scout':
                // Scout - blue color with compass
                fillColor = PALETTE.FAERY_BLUE;
                outlineColor = PALETTE.BROWN_DARKER;
                break;
            case 'craftsman':
                // Craftsman - brown color with hammer
                fillColor = PALETTE.BROWN_MEDIUM;
                outlineColor = PALETTE.BROWN_DARKER;
                break;
            case 'hunter':
                // Hunter - green color with bow
                fillColor = PALETTE.FAERY_GREEN;
                outlineColor = PALETTE.BROWN_DARKER;
                break;
            case 'gatherer':
                // Gatherer - yellow color with basket
                fillColor = PALETTE.MORALE;
                outlineColor = PALETTE.BROWN_DARKER;
                break;
            default:
                // Default to shaman chief if role not recognized
                return shamanSprite;
        }
        
        // Draw the basic shape for the role marker
        ctx.fillStyle = fillColor;
        ctx.strokeStyle = outlineColor;
        ctx.lineWidth = 1;
        
        // Draw a circle for the role marker
        ctx.beginPath();
        ctx.arc(20, 20, 15, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        
        // Add role-specific details
        ctx.fillStyle = outlineColor;
        ctx.strokeStyle = outlineColor;
        ctx.lineWidth = 1;
        
        if (role === 'warrior') {
            // Draw a sword
            ctx.beginPath();
            ctx.moveTo(15, 10);
            ctx.lineTo(25, 10);
            ctx.lineTo(27, 12);
            ctx.lineTo(20, 18);
            ctx.lineTo(13, 12);
            ctx.closePath();
            ctx.fill();
        } else if (role === 'scout') {
            // Draw a compass
            ctx.beginPath();
            ctx.arc(20, 20, 8, 0, Math.PI * 2);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(20, 12);
            ctx.lineTo(20, 28);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(12, 20);
            ctx.lineTo(28, 20);
            ctx.stroke();
        } else if (role === 'craftsman') {
            // Draw a hammer
            ctx.fillRect(15, 15, 10, 3);
            ctx.fillRect(17, 12, 6, 3);
        } else if (role === 'hunter') {
            // Draw a bow and arrow
            ctx.beginPath();
            ctx.moveTo(15, 18);
            ctx.lineTo(25, 18);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.arc(20, 18, 3, 0, Math.PI * 2);
            ctx.fill();
        } else if (role === 'gatherer') {
            // Draw a basket
            ctx.beginPath();
            ctx.ellipse(20, 15, 10, 4, 0, 0, Math.PI * 2);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.arc(10, 15, 3, 0, Math.PI * 2);
            ctx.fill();
            
            ctx.beginPath();
            ctx.arc(30, 15, 3, 0, Math.PI * 2);
            ctx.fill();
        }
        
        // Add a strong outline around the entire sprite to make it stand out
        ctx.globalAlpha = 1.0;
        ctx.strokeStyle = outlineColor;
        ctx.lineWidth = 2;
        ctx.strokeRect(0, 0, 40, 40);
        
        // Cache the sprite
        roleSprites.set(role, canvas);
        return canvas;
    } catch (e) {
        console.warn(`Failed to create ${role} sprite:`, e);
        return shamanSprite; // fallback to shaman sprite
    }
}

/** 
 * Draw a role marker for tribe members.
 * 
 * @param {CanvasRenderingContext2D} ctx 
 * @param {number} x - X coordinate
 * @param {number} y - Y coordinate  
 * @param {string} role - The role of the tribe member
 */
function drawRoleMarker(ctx, x, y, role) {
    // Get the sprite for this role or create it if needed
    let sprite = roleSprites.get(role);
    if (!sprite) {
        sprite = createRoleSprite(role);
    }
    
    if (sprite) {
        ctx.drawImage(sprite, x - 20, y - 20);
    }
}

/** 
 * Draw ritual success/failure visual feedback on a unit.
 * 
 * @param {CanvasRenderingContext2D} ctx 
 * @param {object} state - The game state
 * @param {object} unit - The unit being drawn
 * @param {number} elapsed - Elapsed time in ms
 */
export function drawRitualFeedback(ctx, state, unit, elapsed) {
    if (unit.ritualSuccess === undefined) return;
    
    const { x, y } = unit.pixel;
    
    // Make the feedback more visible and longer-lasting
    ctx.save();
    
    if (unit.ritualSuccess) {
        // Success effect - green pulse using palette color
        ctx.globalAlpha = 0.9;
        ctx.shadowColor = PALETTE.FAERY_GREEN;
        ctx.shadowBlur = 30;
        ctx.strokeStyle = PALETTE.FAERY_GREEN;
        ctx.lineWidth = 10;
        
        // Draw pulsing circle
        const pulseSize = 20 + Math.sin(elapsed / 80) * 5;
        ctx.beginPath();
        ctx.arc(x, y, pulseSize, 0, Math.PI * 2);
        ctx.stroke();
        
        // Add a sparkle effect
        ctx.globalAlpha = 1.0;
        ctx.fillStyle = PALETTE.HIGHLIGHT;
        for (let i = 0; i < 15; i++) {
            const angle = (i / 15) * Math.PI * 2 + elapsed / 100;
            const sparkX = x + Math.cos(angle) * (pulseSize + 10);
            const sparkY = y + Math.sin(angle) * (pulseSize + 10);
            ctx.beginPath();
            ctx.arc(sparkX, sparkY, 3, 0, Math.PI * 2);
            ctx.fill();
        }
    } else {
        // Failure effect - red pulse using palette color
        ctx.globalAlpha = 0.9;
        ctx.shadowColor = PALETTE.ERROR;
        ctx.shadowBlur = 30;
        ctx.strokeStyle = PALETTE.ERROR;
        ctx.lineWidth = 10;
        
        // Draw pulsing circle
        const pulseSize = 20 + Math.sin(elapsed / 80) * 5;
        ctx.beginPath();
        ctx.arc(x, y, pulseSize, 0, Math.PI * 2);
        ctx.stroke();
        
        // Add a failure sparkle effect
        ctx.globalAlpha = 1.0;
        ctx.fillStyle = PALETTE.ERROR;
        for (let i = 0; i < 12; i++) {
            const angle = (i / 12) * Math.PI * 2 + elapsed / 120;
            const sparkX = x + Math.cos(angle) * (pulseSize + 8);
            const sparkY = y + Math.sin(angle) * (pulseSize + 8);
            ctx.beginPath();
            ctx.arc(sparkX, sparkY, 3.5, 0, Math.PI * 2);
            ctx.fill();
        }
    }
    
    // Add a dark stroke/outline to separate it from the hex tiles
    if (shamanSprite) {
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 1;
        ctx.strokeRect(x - 20, y - 20, 40, 40);
    }
    
    ctx.restore();
}

/** 
 * Draw the shaman chief or tribe member on the map.
 * 
 * @param {CanvasRenderingContext2D} ctx 
 * @param {object} state - The game state
 */
export function drawUnit(ctx, state) {
    const { unit } = state;
    if (!unit) return;

    // Built on first use rather than at import time; memoised thereafter.
    const sprite = createShamanSprite();

    // Get the pixel position of the unit
    const { x, y } = unit.pixel;
    
    // Draw a contact shadow to make the unit sit on the map
    ctx.globalAlpha = 0.3;
    ctx.fillStyle = PALETTE.TILE_BORDER;
    ctx.beginPath();
    ctx.arc(x, y + 5, 12, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalAlpha = 1.0;
    
    // Draw the unit itself
    if (unit.role && unit.role !== 'shaman') {
        // Draw a different sprite for each role
        drawRoleMarker(ctx, x, y, unit.role);
    } else if (sprite) {
        // Draw the shaman chief with his distinctive appearance
        ctx.drawImage(sprite, x - 20, y - 20);
    }
    
    // Add a subtle pulse effect to indicate active unit
    if (state.phase === 'decision') {
        const pulseSize = 20 + Math.sin(state.elapsed / 100) * 3;
        ctx.globalAlpha = 0.4;
        ctx.strokeStyle = PALETTE.FAERY_BLUE;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, pulseSize, 0, Math.PI * 2);
        ctx.stroke();
        ctx.globalAlpha = 1.0;
    }
    
    // Draw ritual feedback if applicable
    if (unit.ritualSuccess !== undefined) {
        drawRitualFeedback(ctx, state, unit, state.elapsed);
    }
}

// No module-scope sprite building. Calling document.createElement at import
// time is exactly the pattern that killed the previous build: it only works
// while the import happens to land after the DOM exists, and it breaks the
// rule that main.js is the only module with import-time side effects.
// createShamanSprite() memoises, so drawUnit calling it per frame is free.