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
        
        // Add a subtle glow effect to make it stand out
        ctx.globalAlpha = 0.4;
        ctx.fillStyle = PALETTE.MAGIC;
        ctx.beginPath();
        ctx.arc(size/2, size/2, glowRadius + 8, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a highlight to make it more visually distinct
        ctx.globalAlpha = 0.6;
        ctx.fillStyle = PALETTE.UNIT_HIGHLIGHT;
        ctx.beginPath();
        ctx.arc(size/2 - 8, size/2 - 8, glowRadius * 0.3, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a pulse effect for the active unit
        ctx.globalAlpha = 0.3;
        ctx.fillStyle = PALETTE.MAGIC;
        ctx.beginPath();
        ctx.arc(size/2, size/2, glowRadius + 12, 0, Math.PI * 2);
        ctx.fill();
        
        return canvas;
    } catch (e) {
        console.error('Error creating shaman chief sprite:', e);
        return null;
    }
}

// Create a sprite for tribe members with role-specific visual distinctions
function createTribeMemberSprite(role) {
    try {
        const canvas = document.createElement('canvas');
        const size = 32; // Smaller for tribe members
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        
        if (!ctx) {
            console.error(`Failed to get 2D context for tribe member sprite (${role})`);
            return null;
        }
        
        // Clear with transparent background
        ctx.clearRect(0, 0, size, size);
        
        // Set up nearest neighbor scaling for pixel art
        ctx.imageSmoothingEnabled = false;
        
        // Create a distinct visual style for each role
        const glowRadius = size/2 - 3;
        
        // Draw the main body with role-specific color
        let roleColor;
        switch (role) {
            case 'HUNTER':
                roleColor = PALETTE.FOOD;
                break;
            case 'SCOUT':
                roleColor = PALETTE.WATER_RES;
                break;
            case 'WARRIOR':
                roleColor = PALETTE.HEALTH;
                break;
            case 'CRAFTSMAN':
                roleColor = PALETTE.MATERIALS;
                break;
            default:
                roleColor = PALETTE.SHAMAN_CHIEF;
        }
        
        // Add a strong outline
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 3; // Make the outline thicker for better visibility
        ctx.beginPath();
        ctx.arc(size/2, size/2, glowRadius, 0, Math.PI * 2);
        ctx.stroke();
        
        // Draw the main body with role-specific color
        ctx.fillStyle = roleColor;
        ctx.beginPath();
        ctx.arc(size/2, size/2, glowRadius, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a distinctive visual marker for each role to make them clearly distinguishable
        switch (role) {
            case 'HUNTER':
                // Add a small bow or hunting tool - make it prominent and recognizable
                ctx.globalAlpha = 0.9;
                ctx.fillStyle = PALETTE.SHAMAN_ACCENT;
                ctx.beginPath();
                ctx.arc(size/2 - 10, size/2, 3, 0, Math.PI * 2);
                ctx.fill();
                
                // Add a small quiver or bag element
                ctx.globalAlpha = 0.7;
                ctx.fillStyle = PALETTE.FOOD_COLOR;
                ctx.beginPath();
                ctx.arc(size/2 - 15, size/2 + 3, 2, 0, Math.PI * 2);
                ctx.fill();
                break;
            case 'SCOUT':
                // Add a compass or map element - make it clearly visible
                ctx.globalAlpha = 0.9;
                ctx.fillStyle = PALETTE.SHAMAN_ACCENT;
                ctx.beginPath();
                ctx.arc(size/2, size/2 - 10, 3, 0, Math.PI * 2);
                ctx.fill();
                
                // Add a compass rose for better recognition
                ctx.globalAlpha = 0.8;
                ctx.strokeStyle = PALETTE.MAGIC;
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(size/2, size/2 - 13);
                ctx.lineTo(size/2, size/2 - 10);
                ctx.stroke();
                
                ctx.beginPath();
                ctx.moveTo(size/2 - 3, size/2 - 11);
                ctx.lineTo(size/2 + 3, size/2 - 11);
                ctx.stroke();
                break;
            case 'WARRIOR':
                // Add a weapon or shield element - make it clearly visible
                ctx.globalAlpha = 0.9;
                ctx.fillStyle = PALETTE.SHAMAN_ACCENT;
                ctx.beginPath();
                ctx.arc(size/2 + 10, size/2, 3, 0, Math.PI * 2);
                ctx.fill();
                
                // Add a small shield or armor element
                ctx.globalAlpha = 0.7;
                ctx.strokeStyle = PALETTE.MAGIC;
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(size/2 + 10, size/2, 5, 0, Math.PI * 2);
                ctx.stroke();
                break;
            case 'CRAFTSMAN':
                // Add a tool or hammer element - make it clearly visible
                ctx.globalAlpha = 0.9;
                ctx.fillStyle = PALETTE.SHAMAN_ACCENT;
                ctx.beginPath();
                ctx.arc(size/2, size/2 + 10, 3, 0, Math.PI * 2);
                ctx.fill();
                
                // Add a small anvil or construction element
                ctx.globalAlpha = 0.7;
                ctx.fillStyle = PALETTE.FOREST;
                ctx.beginPath();
                ctx.rect(size/2 - 2, size/2 + 13, 4, 2);
                ctx.fill();
                break;
            default:
                // Add a simple distinctive element for unknown roles
                ctx.globalAlpha = 0.8;
                ctx.fillStyle = PALETTE.SHAMAN_ACCENT;
                ctx.beginPath();
                ctx.arc(size/2, size/2, 3, 0, Math.PI * 2);
                ctx.fill();
        }
        
        // Add a simple facial feature to distinguish tribe members
        ctx.globalAlpha = 0.9;
        ctx.fillStyle = PALETTE.UNIT_OUTLINE;
        ctx.beginPath();
        ctx.arc(size/2 - 3, size/2 - 3, 1.5, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.beginPath();
        ctx.arc(size/2 + 3, size/2 - 3, 1.5, 0, Math.PI * 2);
        ctx.fill();
        
        // Add a simple mouth
        ctx.globalAlpha = 0.9;
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(size/2, size/2 + 2, 2, 0, Math.PI); // Smile
        ctx.stroke();
        
        return canvas;
    } catch (e) {
        console.error(`Error creating tribe member sprite (${role}):`, e);
        return null;
    }
}

export function initUnitSprites() {
    shamanSprite = createShamanChiefSprite();
    
    // Create sprites for different tribe member roles
    const roles = ['HUNTER', 'SCOUT', 'WARRIOR', 'CRAFTSMAN'];
    roles.forEach(role => {
        tribeMemberSprites.set(role, createTribeMemberSprite(role));
    });
}

export function drawUnit(ctx, state) {
    if (!state || !state.unit) return;
    
    const unit = state.unit;
    const pixel = unit.pixel;
    
    // Skip drawing if off-screen
    if (pixel.x < -50 || pixel.x > state.width + 50 || 
        pixel.y < -50 || pixel.y > state.height + 50) {
        return;
    }
    
    ctx.save();
    ctx.translate(pixel.x + state.camera.x, pixel.y + state.camera.y);
    
    // Draw the shaman chief sprite
    if (shamanSprite) {
        ctx.globalAlpha = 1.0;
        ctx.drawImage(shamanSprite, -24, -24, 48, 48);
        
        // Add a pulse effect for active units
        if (unit.moving || unit.justMoved) {
            const pulseSize = 30 + Math.sin(state.frame * 0.1) * 5;
            ctx.globalAlpha = 0.3;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, pulseSize, 0, Math.PI * 2);
            ctx.fill();
        }
        
        // Add a more prominent visual effect when unit is moving to make it clearly visible
        if (unit.moving) {
            // Draw an additional glow around the unit during movement
            const glowRadius = 35;
            ctx.globalAlpha = 0.2;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, glowRadius, 0, Math.PI * 2);
            ctx.fill();
        }
        
        // Add ritual casting effect when unit is casting a ritual
        if (unit.castingRitual) {
            const pulseSize = 35 + Math.sin(state.frame * 0.2) * 8;
            ctx.globalAlpha = 0.4;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, pulseSize, 0, Math.PI * 2);
            ctx.fill();
            
            // Add a more intense glow effect during ritual casting
            ctx.globalAlpha = 0.3;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, pulseSize + 10, 0, Math.PI * 2);
            ctx.fill();
        }
    } else {
        // Fallback to simple drawing
        ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
        ctx.beginPath();
        ctx.arc(0, 0, 15, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 2;
        ctx.stroke();
    }
    
    ctx.restore();
}

export function drawUnitWithEffects(ctx, state) {
    if (!state || !state.unit) return;
    
    const unit = state.unit;
    const pixel = unit.pixel;
    
    // Skip drawing if off-screen
    if (pixel.x < -50 || pixel.x > state.width + 50 || 
        pixel.y < -50 || pixel.y > state.height + 50) {
        return;
    }
    
    // Draw the unit with scaling and rotation effects
    ctx.save();
    ctx.translate(pixel.x + state.camera.x, pixel.y + state.camera.y);
    
    // Apply scaling effect during movement
    if (unit.scale !== undefined) {
        ctx.scale(unit.scale, unit.scale);
    }
    
    // Apply rotation effect during movement
    if (unit.rotation !== undefined) {
        ctx.rotate(unit.rotation);
    }
    
    // Draw the shaman chief sprite
    if (shamanSprite) {
        ctx.globalAlpha = 1.0;
        ctx.drawImage(shamanSprite, -24, -24, 48, 48);
        
        // Add a pulse effect for active units
        if (unit.moving || unit.justMoved) {
            const pulseSize = 30 + Math.sin(state.frame * 0.1) * 5;
            ctx.globalAlpha = 0.3;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, pulseSize, 0, Math.PI * 2);
            ctx.fill();
        }
        
        // Add a more prominent visual effect when unit is moving to make it clearly visible
        if (unit.moving) {
            // Draw an additional glow around the unit during movement
            const glowRadius = 35;
            ctx.globalAlpha = 0.2;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, glowRadius, 0, Math.PI * 2);
            ctx.fill();
        }
        
        // Add ritual casting effect when unit is casting a ritual
        if (unit.castingRitual) {
            const pulseSize = 35 + Math.sin(state.frame * 0.2) * 8;
            ctx.globalAlpha = 0.4;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, pulseSize, 0, Math.PI * 2);
            ctx.fill();
            
            // Add a more intense glow effect during ritual casting
            ctx.globalAlpha = 0.3;
            ctx.fillStyle = PALETTE.MAGIC;
            ctx.beginPath();
            ctx.arc(0, 0, pulseSize + 10, 0, Math.PI * 2);
            ctx.fill();
        }
        
        // Add visual feedback for successful/failed rituals
        if (unit.ritualSuccessTimer > 0) {
            const success = unit.ritualSuccess;
            const pulseSize = 40 + Math.sin(state.frame * 0.3) * 10;
            ctx.globalAlpha = 0.5;
            
            if (success) {
                // Green glow for successful ritual
                ctx.fillStyle = PALETTE.SUCCESS;
            } else {
                // Red glow for failed ritual
                ctx.fillStyle = PALETTE.FAILURE;
            }
            
            ctx.beginPath();
            ctx.arc(0, 0, pulseSize, 0, Math.PI * 2);
            ctx.fill();
        }
    } else {
        // Fallback to simple drawing - ensure we have a visible unit even if sprite creation fails
        ctx.fillStyle = PALETTE.SHAMAN_CHIEF;
        ctx.beginPath();
        ctx.arc(0, 0, 15, 0, Math.PI * 2);
        ctx.fill();
        
        ctx.strokeStyle = PALETTE.UNIT_OUTLINE;
        ctx.lineWidth = 3; // Make the outline more visible
        ctx.stroke();
    }
    
    ctx.restore();
}