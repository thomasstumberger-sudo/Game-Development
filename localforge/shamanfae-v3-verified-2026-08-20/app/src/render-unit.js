/** 
 * Unit drawing and visual effects.
 * 
 * Pure module: no DOM, no side effects on import.
 */ 
import { PALETTE } from './palette.js';
import { hexToPixel } from './hex.js';

// Pre-rendered sprites for different units
let shamanSprite = null;
let tribeMemberSprites = new Map();

export { shamanSprite, tribeMemberSprites };

function createShamanChiefSprite() {
    try {
        // Pre-render the shaman chief sprite with distinct visual elements
        const canvas = document.createElement('canvas');
        const size = 48; // Size for better visibility
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        
        if (!ctx) {
            console.error('Failed to get 2D context for shaman chief sprite');
            return null;
        }
        
        // Clear with transparent background
        ctx.clearRect(0, 0, size, size);
        
        // Set up nearest neighbor scaling for pixel art
        ctx.imageSmoothingEnabled = false;
        
        // Create a more distinct and visually appealing shaman chief sprite
        const glowRadius = size/2 - 4;
        
        // Add a strong outline to make it stand out against any terrain
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 4; // Make the outline thicker for better visibility
        ctx.beginPath();
        ctx.arc(size/2, size/2, glowRadius, 0, Math.PI * 2);
        ctx.stroke();
        
        // Draw the main body with distinct silhouette - make it more visually distinct
        ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
        ctx.beginPath();
        ctx.ellipse(size/2, size/2, glowRadius, glowRadius * 1.3, 0, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a distinctive head shape
        ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
        ctx.beginPath();
        ctx.arc(size/2, size/2 - 10, glowRadius * 0.8, 0, Math.PI * 2);
        ctx.fill();
        
        // Add facial features for better recognition
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = PALETTE.UNIT_OUTLINE; // Dark outline for facial features
        ctx.beginPath();
        ctx.arc(size/2 - 4, size/2 - 12, 2.5, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.beginPath();
        ctx.arc(size/2 + 4, size/2 - 12, 2.5, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a simple mouth
        ctx.beginPath();
        ctx.arc(size/2, size/2 - 6, 3.5, 0, Math.PI); // Smile
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 1.5;
        ctx.stroke();
        
        // Add a distinctive accent - a small magical symbol or pattern on the chest
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = PALETTE.SHAMAN_ACCENT;
        ctx.beginPath();
        ctx.arc(size/2, size/2 + 7, glowRadius * 0.4, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a magical symbol pattern on the chest
        ctx.globalAlpha = 1.0;
        ctx.strokeStyle = PALETTE.MAGIC;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(size/2, size/2 + 7, glowRadius * 0.5, 0, Math.PI * 2);
        ctx.stroke();
        
        // Add a small magical rune-like symbol
        ctx.globalAlpha = 1.0;
        ctx.fillStyle = PALETTE.MAGIC;
        ctx.beginPath();
        ctx.arc(size/2, size/2 + 7, glowRadius * 0.2, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a staff or magical item to distinguish the unit - make it more prominent
        ctx.globalAlpha = 1.0;
        ctx.strokeStyle = PALETTE.SHAMAN_ACCENT;
        ctx.lineWidth = 4; // Make staff thicker for better visibility
        ctx.beginPath();
        ctx.moveTo(size/2 - 5, size/2 + 10);
        ctx.lineTo(size/2 - 5, size/2 + 30); // Staff
        ctx.stroke();
        
        // Add a magical orb at the top of the staff - make it more visible
        ctx.fillStyle = PALETTE.MAGIC;
        ctx.beginPath();
        ctx.arc(size/2 - 5, size/2 + 30, 5, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a subtle glow effect for magical properties
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = PALETTE.MAGIC_GLOW;
        ctx.beginPath();
        ctx.arc(size/2, size/2, glowRadius + 5, 0, Math.PI * 2);
        ctx.fill();
        
        // Reset global alpha
        ctx.globalAlpha = 1.0;
        
        return canvas;
    } catch (e) {
        console.error('Error creating shaman chief sprite:', e);
        return null;
    }
}

/** 
 * Initialize unit sprites
 */
export function initUnitSprites() {
    try {
        // Create the shaman chief sprite
        shamanSprite = createShamanChiefSprite();
        
        // Create tribe member sprites if needed
        // For now, we'll just use the same sprite for simplicity
        // In a full implementation, these would be different
        
        // Make sure the sprite was created successfully
        if (!shamanSprite) {
            console.error('Failed to create shaman chief sprite');
        }
    } catch (e) {
        console.error('Error initializing unit sprites:', e);
        // Create a fallback sprite in case of error
        const fallbackCanvas = document.createElement('canvas');
        fallbackCanvas.width = 48;
        fallbackCanvas.height = 48;
        const ctx = fallbackCanvas.getContext('2d');
        if (ctx) {
            ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
            ctx.fillRect(0, 0, 48, 48);
            shamanSprite = fallbackCanvas;
        }
    }
}

export function drawUnitWithEffects(ctx, state) {
    if (!state || !state.unit) return;
    
    // If we don't have a valid sprite, create a fallback
    if (!shamanSprite) {
        // Create a simple fallback sprite if needed
        const fallbackCanvas = document.createElement('canvas');
        fallbackCanvas.width = 48;
        fallbackCanvas.height = 48;
        const fallbackCtx = fallbackCanvas.getContext('2d');
        if (fallbackCtx) {
            fallbackCtx.imageSmoothingEnabled = false;
            fallbackCtx.fillStyle = PALETTE.SHAMAN_CHIEF;
            fallbackCtx.beginPath();
            fallbackCtx.arc(24, 24, 20, 0, Math.PI * 2);
            fallbackCtx.fill();
            shamanSprite = fallbackCanvas;
        } else {
            return; // Can't draw without context
        }
    }
    
    const unit = state.unit;
    
    // Draw the unit sprite at its current position
    let pixel = unit.pixel;
    
    // If we don't have a valid pixel, try to compute it from q,r coordinates
    if (!pixel || typeof pixel.x !== 'number' || typeof pixel.y !== 'number') {
        const computedPixel = hexToPixel(unit.q, unit.r);
        if (computedPixel && typeof computedPixel.x === 'number' && typeof computedPixel.y === 'number') {
            pixel = computedPixel;
        } else {
            // If we still can't compute a valid pixel, return early
            return;
        }
    }
    
    // Save context for transformations
    ctx.save();
    
    // Apply transformations (scale, rotation)
    ctx.translate(pixel.x, pixel.y);
    
    // Add a subtle pulse effect to the active unit
    if (state.phase === 'decision') {
        const pulse = Math.sin(state.frame * 0.1) * 0.1 + 1;
        ctx.scale(pulse, pulse);
    }
    
    // Apply ritual casting visual effects
    if (unit.castingRitual) {
        // Draw a glowing aura around the unit when casting a ritual
        const auraRadius = 30;
        const pulse = Math.sin(state.frame * 0.2) * 0.3 + 1;
        const glowAlpha = 0.4 * pulse;
        
        ctx.globalAlpha = glowAlpha;
        ctx.fillStyle = PALETTE.MAGIC;
        ctx.beginPath();
        ctx.arc(0, 0, auraRadius, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a more intense glow for the ritual effect
        ctx.globalAlpha = glowAlpha * 0.7;
        ctx.fillStyle = PALETTE.FAERY_GREEN;
        ctx.beginPath();
        ctx.arc(0, 0, auraRadius * 0.8, 0, Math.PI * 2);
        ctx.fill();
        
        // Reset alpha
        ctx.globalAlpha = 1.0;
    }
    
    // Apply ritual success/failure visual effects
    if (unit.ritualSuccessTimer > 0) {
        const pulse = Math.sin(state.frame * 0.3) * 0.2 + 1;
        ctx.scale(pulse, pulse);
        
        // Draw a more prominent success/failure indicator around the unit
        const indicatorRadius = 30;
        if (unit.ritualSuccess) {
            // Green success effect - draw multiple rings for better visibility
            ctx.globalAlpha = 0.7;
            ctx.strokeStyle = PALETTE.SUCCESS;
            ctx.lineWidth = 4;
            
            // Draw outer ring
            ctx.beginPath();
            ctx.arc(0, 0, indicatorRadius, 0, Math.PI * 2);
            ctx.stroke();
            
            // Draw inner ring
            ctx.beginPath();
            ctx.arc(0, 0, indicatorRadius * 0.7, 0, Math.PI * 2);
            ctx.stroke();
            
            // Add a star symbol for success
            ctx.fillStyle = PALETTE.SUCCESS;
            ctx.globalAlpha = 0.9;
            ctx.beginPath();
            ctx.moveTo(0, -indicatorRadius * 0.8);
            ctx.lineTo(5, 0);
            ctx.lineTo(0, indicatorRadius * 0.8);
            ctx.lineTo(-5, 0);
            ctx.closePath();
            ctx.fill();
        } else {
            // Red failure effect - draw multiple rings for better visibility
            ctx.globalAlpha = 0.7;
            ctx.strokeStyle = PALETTE.FAILURE;
            ctx.lineWidth = 4;
            
            // Draw outer ring
            ctx.beginPath();
            ctx.arc(0, 0, indicatorRadius, 0, Math.PI * 2);
            ctx.stroke();
            
            // Draw inner ring (X pattern)
            ctx.beginPath();
            ctx.moveTo(-indicatorRadius * 0.7, -indicatorRadius * 0.7);
            ctx.lineTo(indicatorRadius * 0.7, indicatorRadius * 0.7);
            ctx.stroke();
            
            ctx.beginPath();
            ctx.moveTo(indicatorRadius * 0.7, -indicatorRadius * 0.7);
            ctx.lineTo(-indicatorRadius * 0.7, indicatorRadius * 0.7);
            ctx.stroke();
        }
        ctx.globalAlpha = 1.0;
    }
    
    // Apply movement-specific transformations
    if (unit.moving) {
        ctx.scale(unit.scale, unit.scale);
        ctx.rotate(unit.rotation);
    }
    
    // Draw the sprite
    ctx.drawImage(shamanSprite, -shamanSprite.width/2, -shamanSprite.height/2);
    
    // Restore context
    ctx.restore();
}