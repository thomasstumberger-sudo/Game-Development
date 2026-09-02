/** 
 * Encounter system for the game.
 * 
 * Pure module: no DOM, no side effects on import.
 */
import { PALETTE } from './palette.js';
import { hexToPixel } from './hex.js';
import { addRitualCastEffect, addRitualResultEffect } from './render-map.js';

// Encounter data - simplified version with just ritual encounters
const ENCOUNTERS = {
    // Ritual encounters
    'ritual-bind': {
        id: 'ritual-bind',
        type: 'ritual',
        title: 'Bind the Fae',
        description: 'Attempt to bind a Fae spirit to your will.',
        options: [
            {
                text: 'Cast Bind Ritual (1 Magic)',
                effect: { magic: -1 }
            }
        ],
        success: {
            // Success effects
            delta: {
                magic: 2, // Gain magic
                morale: 1, // Gain morale
                weirdness: -1 // Reduce weirdness slightly
            },
            text: 'The Fae spirit is bound to your will! Magic and morale increase.'
        },
        failure: {
            // Failure effects  
            delta: {
                morale: -2, // Lose morale
                weirdness: 1 // Increase weirdness
            },
            text: 'The ritual fails. The Fae spirit resists your control!'
        }
    },
    
    'ritual-bargain': {
        id: 'ritual-bargain',
        type: 'ritual',
        title: 'Bargain with the Fae',
        description: 'Negotiate with a Fae spirit for resources.',
        options: [
            {
                text: 'Cast Bargain Ritual (1 Magic)',
                effect: { magic: -1 }
            }
        ],
        success: {
            delta: {
                food: 2,
                water: 2
            },
            text: 'The Fae spirits agree to share their resources!'
        },
        failure: {
            delta: {
                morale: -1
            },
            text: 'The Fae spirits are unimpressed by your offer.'
        }
    },
    
    'ritual-banish': {
        id: 'ritual-banish',
        type: 'ritual',
        title: 'Banish the Fae',
        description: 'Remove a threatening Fae spirit from the area.',
        options: [
            {
                text: 'Cast Banish Ritual (2 Magic)',
                effect: { magic: -2 }
            }
        ],
        success: {
            delta: {
                weirdness: -3,
                morale: 1
            },
            text: 'The Fae spirit is banished! The area feels safer.'
        },
        failure: {
            delta: {
                morale: -2,
                weirdness: 2
            },
            text: 'The ritual backfires. The Fae spirit grows stronger!'
        }
    },
    
    // Regular encounters for testing
    'fae-spirit': {
        id: 'fae-spirit',
        type: 'spirit',
        title: 'Fae Spirit',
        description: 'A mysterious Fae spirit appears before you.',
        options: [
            {
                text: 'Approach the spirit',
                effect: { }
            },
            {
                text: 'Avoid the spirit',
                effect: { }
            }
        ],
        success: {
            delta: {
                magic: 1
            },
            text: 'The spirit grants you a small gift of magic.'
        },
        failure: {
            delta: {
                morale: -1
            },
            text: 'The spirit seems displeased with your approach.'
        }
    },
    
    'forest-path': {
        id: 'forest-path',
        type: 'path',
        title: 'Forest Path',
        description: 'You find a path through the forest.',
        options: [
            {
                text: 'Take the path',
                effect: { }
            }
        ],
        success: {
            delta: {
                food: 1
            },
            text: 'The path leads to a small clearing with edible plants.'
        },
        failure: {
            delta: {
                water: -1
            },
            text: 'You get lost in the dense forest.'
        }
    }
};

export class EncounterSystem {
    constructor(state) {
        this.state = state;
        this.active = false;
        this.current = null;
        this.chainQueue = [];
    }
    
    /**
     * Set the game state for this encounter system
     */
    setState(state) {
        this.state = state;
    }
    
    /**
     * Trigger an encounter at the current tile
     */
    trigger(state) {
        // For now, just trigger a ritual encounter if we're on a ritual tile
        if (state.tile && state.tile.encounterType && state.tile.encounterType.startsWith('ritual-')) {
            this.current = ENCOUNTERS[state.tile.encounterType];
            this.active = true;
            
            // Process the encounter immediately for testing purposes
            if (this.current.options && this.current.options.length > 0) {
                this.resolve(0);
            }
        } else {
            // If no specific ritual tile, trigger a random encounter
            const ritualTypes = Object.keys(ENCOUNTERS).filter(key => key.startsWith('ritual-'));
            if (ritualTypes.length > 0) {
                const randomType = ritualTypes[Math.floor(Math.random() * ritualTypes.length)];
                this.current = ENCOUNTERS[randomType];
                this.active = true;
                
                // Process the encounter immediately for testing purposes
                this.resolve(0);
            }
        }
        
        // Add visual effect for the encounter
        this.triggerEffect();
    }
    
    /**
     * End of turn: process chain encounters and update state
     */
    endTurn(state) {
        if (this.chainQueue.length > 0) {
            const next = this.chainQueue.shift();
            // For simplicity, we'll just trigger the first chain encounter
            if (next && next.encounters && next.encounters.length > 0) {
                const randomEncounter = next.encounters[Math.floor(Math.random() * next.encounters.length)];
                if (ENCOUNTERS[randomEncounter]) {
                    this.current = ENCOUNTERS[randomEncounter];
                    this.active = true;
                    
                    // Process the encounter immediately for testing purposes
                    this.resolve(0);
                }
            }
        }
    }
    
    /**
     * Check if a position is over an option
     */
    optionAt(state, x, y) {
        if (!this.active || !this.current) return -1;
        
        // Simple hit test - in a real game this would be more sophisticated
        const optionCount = this.current.options ? this.current.options.length : 0;
        if (optionCount > 0) {
            // For simplicity, just return first option for now
            return 0;
        }
        
        return -1;
    }
    
    /**
     * Resolve an encounter option
     */
    resolve(optionIndex) {
        if (!this.active || !this.current) return { delta: {}, affordable: true };
        
        const option = this.current.options[optionIndex];
        if (!option) return { delta: {}, affordable: false };
        
        // Check if player can afford the ritual cost
        let affordable = true;
        const effect = option.effect || {};
        if (effect.magic && this.state.unit.magic < Math.abs(effect.magic)) {
            affordable = false;
        }
        
        if (!affordable) {
            return { delta: {}, affordable: false };
        }
        
        // Apply the ritual cost
        const delta = { ...effect };
        
        // Determine success/failure based on magic and skill
        let success = false;
        const baseChance = 0.6; // Base 60% chance of success
        const skillBonus = this.state.unit.skill * 0.1; // Skill adds 10% per point
        const magicBonus = (this.state.unit.magic > 0) ? 0.2 : 0; // Magic bonus if available
        
        const chance = Math.min(0.9, baseChance + skillBonus + magicBonus);
        
        // For testing purposes, we'll make it random but with bias
        success = Math.random() < chance;
        
        // Apply success/failure effects
        if (success) {
            delta.ritualSuccess = true;
            Object.assign(delta, this.current.success.delta);
            
            // Add visual feedback for successful ritual
            const pixelPos = hexToPixel(this.state.unit.q, this.state.unit.r);
            addRitualResultEffect(pixelPos.x, pixelPos.y, true);
            
            // Set success feedback in state
            this.state.unit.ritualSuccess = true;
            this.state.unit.ritualSuccessTimer = 120; // 2 seconds at 60fps
        } else {
            delta.ritualSuccess = false;
            Object.assign(delta, this.current.failure.delta);
            
            // Add visual feedback for failed ritual
            const pixelPos = hexToPixel(this.state.unit.q, this.state.unit.r);
            addRitualResultEffect(pixelPos.x, pixelPos.y, false);
            
            // Set success feedback in state
            this.state.unit.ritualSuccess = false;
            this.state.unit.ritualSuccessTimer = 120; // 2 seconds at 60fps
        }
        
        // Reset encounter state
        this.active = false;
        this.current = null;
        
        return { delta, affordable: true };
    }
    
    /**
     * Add a screen shake effect for impactful encounters
     */
    onShake(intensity, duration) {
        // In a real implementation, this would trigger camera shake
        console.log(`Screen shake: intensity ${intensity}, duration ${duration}`);
    }
    
    /**
     * Trigger visual effects for the encounter
     */
    triggerEffect() {
        if (this.current && this.state && this.state.tile) {
            const pixelPos = hexToPixel(this.state.tile.q, this.state.tile.r);
            addRitualCastEffect(pixelPos.x, pixelPos.y, this.current.type);
        }
    }
}

// Simple ritual casting function for testing
export function castRitual(state, ritualType) {
    if (!state || !state.unit) return false;
    
    // For now, just simulate a ritual effect
    switch(ritualType) {
        case 'bind':
            if (state.unit.magic >= 1) {
                state.unit.magic -= 1;
                return true;
            }
            break;
        case 'bargain':
            if (state.unit.magic >= 1) {
                state.unit.magic -= 1;
                return true;
            }
            break;
        case 'banish':
            if (state.unit.magic >= 2) {
                state.unit.magic -= 2;
                return true;
            }
            break;
    }
    return false;
}

// Add a function to trigger an encounter at the current tile
export function triggerEncounterAtTile(state, tile) {
    if (!state || !tile) return;
    
    // Set the tile in state for reference
    state.tile = tile;
    
    // For now, just trigger a ritual encounter if we're on a ritual tile
    if (tile.encounterType && tile.encounterType.startsWith('ritual-')) {
        // This would be handled by the EncounterSystem class
        return true;
    }
    
    return false;
}