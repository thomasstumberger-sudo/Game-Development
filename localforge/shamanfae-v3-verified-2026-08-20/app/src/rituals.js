/** 
 * Ritual system for the game.
 * 
 * Pure module: no DOM, no side effects on import.
 */
import { PALETTE } from './palette.js';
import { addRitualCastEffect, addRitualResultEffect, addMagicEffect } from './render-map.js';
import { applyDelta } from './state.js';
import { RESOURCE_FEEDBACK } from './resource-feedback.js';

// Ritual types and their properties
export const RITUALS = {
    BIND: {
        name: 'Bind',
        cost: 1,
        description: 'Temporarily control Fae effect',
        type: 'control'
    },
    BARGAIN: {
        name: 'Bargain',
        cost: 1,
        description: 'Negotiate with Fae',
        type: 'negotiation'
    },
    BANISH: {
        name: 'Banish',
        cost: 2,
        description: 'Remove threat',
        type: 'removal'
    },
    MINOR_BLESSING: {
        name: 'Minor Blessing',
        cost: 1,
        description: 'Heal or small resource gain',
        type: 'healing'
    },
    MAJOR_BLESSING: {
        name: 'Major Blessing',
        cost: 2,
        description: 'Substantial benefit',
        type: 'benefit'
    }
};

/** 
 * Cast a ritual.
 * @param {object} state - Game state
 * @param {string} ritualType - Type of ritual to cast
 * @returns {boolean} True if ritual was successfully cast
 */
export function castRitual(state, ritualType) {
    if (!state || !ritualType) return false;
    
    const ritual = RITUALS[ritualType.toUpperCase()];
    if (!ritual) {
        console.warn(`Unknown ritual type: ${ritualType}`);
        return false;
    }
    
    // Check if the unit has enough magic
    if (state.resources.magic < ritual.cost) {
        console.log(`Not enough magic to cast ${ritual.name}`);
        return false;
    }
    
    // Deduct magic cost
    applyDelta(state, { magic: -ritual.cost });
    
    // Add visual effects for casting
    const unit = state.unit;
    if (unit && unit.pixel) {
        addRitualCastEffect(unit.pixel.x, unit.pixel.y);
    }
    
    // Simulate ritual success/failure with some randomness for demonstration
    // In a real game this would be more complex based on various factors
    const success = Math.random() > 0.3; // 70% chance of success for demo purposes
    
    // Apply ritual effects based on type
    applyRitualEffects(state, ritualType, success);
    
    // Add visual feedback for result
    if (unit && unit.pixel) {
        addRitualResultEffect(unit.pixel.x, unit.pixel.y, success);
    }
    
    // Set ritual success state for visual feedback
    if (unit) {
        unit.castingRitual = false;
        unit.ritualSuccess = success;
        unit.ritualSuccessTimer = 60; // Show success/failure for 1 second (60 frames)
    }
    
    console.log(`Successfully cast ${ritual.name}`);
    return true;
}

/** 
 * Apply effects of a ritual.
 * @param {object} state - Game state
 * @param {string} ritualType - Type of ritual cast
 * @param {boolean} success - Whether the ritual was successful
 */
function applyRitualEffects(state, ritualType, success) {
    if (!state || !ritualType) return;
    
    const unit = state.unit;
    if (!unit) return;
    
    switch (ritualType.toUpperCase()) {
        case 'BIND':
            // Bind ritual - temporary control of Fae effect
            if (success) {
                applyDelta(state, { magic: 1 }); // Gain 1 magic on success
                console.log('Bind ritual succeeded - gained 1 magic');
            } else {
                console.log('Bind ritual failed');
            }
            break;
            
        case 'BARGAIN':
            // Bargain ritual - negotiate with Fae
            if (success) {
                applyDelta(state, { food: 2, water: 2 }); // Gain resources on success
                console.log('Bargain ritual succeeded - gained 2 food and 2 water');
            } else {
                console.log('Bargain ritual failed');
            }
            break;
            
        case 'BANISH':
            // Banish ritual - remove threat
            if (success) {
                applyDelta(state, { magic: 1 }); // Gain 1 magic on success
                console.log('Banish ritual succeeded - gained 1 magic');
            } else {
                console.log('Banish ritual failed');
            }
            break;
            
        case 'MINOR_BLESSING':
            // Minor blessing - heal or small resource gain
            if (success) {
                applyDelta(state, { health: 2 }); // Heal 2 points
                console.log('Minor Blessing succeeded - healed 2 health');
            } else {
                console.log('Minor Blessing failed');
            }
            break;
            
        case 'MAJOR_BLESSING':
            // Major blessing - substantial benefit
            if (success) {
                applyDelta(state, { food: 5, water: 5, magic: 1 }); // Gain resources and magic
                console.log('Major Blessing succeeded - gained 5 food, 5 water, and 1 magic');
            } else {
                console.log('Major Blessing failed');
            }
            break;
            
        default:
            console.warn(`Unknown ritual type for effects: ${ritualType}`);
    }
    
    // Add magic effect visual feedback
    if (unit && unit.pixel) {
        addMagicEffect(unit.pixel.x, unit.pixel.y);
    }
}