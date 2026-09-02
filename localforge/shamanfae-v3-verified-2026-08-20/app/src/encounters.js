/** 
 * Encounter data and triggering.
 * 
 * Pure module: no DOM, no side effects on import.
 */ 

import { worldToScreen, hexToPixel } from './hex.js';
import { addEncounterEffect, addRitualCastEffect, addRitualResultEffect } from './render-map.js';

// Sample encounter data - in a full implementation this would be loaded from JSON
export const ENCOUNTERS = [
    {
        id: 'forest_encounter_1',
        name: 'Forest Guardian',
        type: 'hostile',
        terrain: 'forest',
        description: 'A guardian of the forest emerges from the shadows.',
        effects: {
            health: -2,
            magic: 0,
            morale: -5
        },
        options: [
            {
                text: 'Fight',
                effect: { health: -3, morale: -10 },
                successChance: 0.7
            },
            {
                text: 'Surrender',
                effect: { food: -2, water: -2 }
            },
            {
                text: 'Bargain',
                effect: { magic: -1, morale: 5 },
                requiresMagic: true
            }
        ]
    },
    {
        id: 'water_encounter_1',
        name: 'River Spirit',
        type: 'neutral',
        terrain: 'water',
        description: 'A spirit of the river offers a choice.',
        effects: {
            health: 0,
            magic: 2,
            morale: 3
        },
        options: [
            {
                text: 'Accept Blessing',
                effect: { magic: 3, morale: 5 }
            },
            {
                text: 'Take Resources',
                effect: { food: -1, water: -1 }
            }
        ]
    },
    {
        id: 'mountain_encounter_1',
        name: 'Mountain Echo',
        type: 'neutral',
        terrain: 'mountain',
        description: 'An echo of the mountain speaks to you.',
        effects: {
            health: 0,
            magic: 1,
            morale: 2
        },
        options: [
            {
                text: 'Listen',
                effect: { magic: 2, morale: 3 }
            },
            {
                text: 'Continue Journey',
                effect: { food: -1, water: -1 }
            }
        ]
    },
    {
        id: 'swamp_encounter_1',
        name: 'Swamp Warden',
        type: 'hostile',
        terrain: 'swamp',
        description: 'A warden of the swamp blocks your path.',
        effects: {
            health: -3,
            magic: 0,
            morale: -5
        },
        options: [
            {
                text: 'Find Alternative Route',
                effect: { food: -2, water: -2 }
            },
            {
                text: 'Use Magic',
                effect: { magic: -2, morale: 3 },
                requiresMagic: true
            }
        ]
    },
    {
        id: 'fae_encounter_1',
        name: 'Fae Trickster',
        type: 'neutral',
        terrain: 'fae_land',
        description: 'A mischievous fae appears before you.',
        effects: {
            health: 0,
            magic: 2,
            morale: 1
        },
        options: [
            {
                text: 'Play Along',
                effect: { magic: 3, morale: 5 }
            },
            {
                text: 'Ignore',
                effect: { food: -1, water: -1 }
            }
        ]
    },
    {
        id: 'grass_encounter_1',
        name: 'Wandering Herder',
        type: 'friendly',
        terrain: 'grass',
        description: 'A herder offers you some provisions.',
        effects: {
            health: 0,
            magic: 0,
            morale: 3
        },
        options: [
            {
                text: 'Accept Offer',
                effect: { food: 3, water: 3 }
            },
            {
                text: 'Decline',
                effect: { morale: -1 }
            }
        ]
    }
];

// Sample ritual data - in a full implementation this would be loaded from JSON
export const RITUALS = [
    {
        id: 'bind',
        name: 'Bind',
        type: 'minor',
        cost: 1,
        description: 'Temporarily control a Fae effect',
        effects: {
            magic: -1,
            successChance: 0.8
        }
    },
    {
        id: 'bargain',
        name: 'Bargain',
        type: 'minor',
        cost: 1,
        description: 'Negotiate with a Fae',
        effects: {
            magic: -1,
            successChance: 0.7
        }
    },
    {
        id: 'banish',
        name: 'Banish',
        type: 'major',
        cost: 2,
        description: 'Remove a threat',
        effects: {
            magic: -2,
            successChance: 0.6
        }
    },
    {
        id: 'blessing',
        name: 'Minor Blessing',
        type: 'minor',
        cost: 1,
        description: 'Heal or small resource gain',
        effects: {
            magic: -1,
            successChance: 0.9
        }
    },
    {
        id: 'major_blessing',
        name: 'Major Blessing',
        type: 'major',
        cost: 3,
        description: 'Substantial benefit',
        effects: {
            magic: -3,
            successChance: 0.7
        }
    }
];

// Function to trigger an encounter at a tile
export function triggerEncounter(state, tile) {
    if (!state || !tile) return;
    
    // Get a random encounter based on terrain type
    const encounters = ENCOUNTERS.filter(e => e.terrain === tile.terrain);
    if (encounters.length === 0) return;
    
    const encounter = encounters[Math.floor(Math.random() * encounters.length)];
    
    // Add encounter effect at the tile position
    const pixel = hexToPixel(tile.q, tile.r);
    const screenPos = worldToScreen(pixel.x, pixel.y, state.camera);
    if (screenPos) {
        addEncounterEffect(screenPos.x, screenPos.y);
    }
    
    return encounter;
}

// Function to resolve a ritual
export function resolveRitual(state, ritualType) {
    if (!state || !ritualType) return false;
    
    const ritual = RITUALS.find(r => r.id === ritualType);
    if (!ritual) return false;
    
    // Check if the player has enough magic
    if (state.resources.magic < ritual.cost) {
        return false;
    }
    
    // Deduct magic cost
    state.resources.magic -= ritual.cost;
    
    // Add ritual cast effect at the unit's position
    if (state.unit && state.unit.pixel) {
        addRitualCastEffect(state.unit.pixel.x, state.unit.pixel.y, ritualType);
    }
    
    // Simulate success/failure based on chance
    const success = Math.random() < ritual.effects.successChance;
    
    // Add ritual result effect
    if (state.unit && state.unit.pixel) {
        addRitualResultEffect(state.unit.pixel.x, state.unit.pixel.y, success);
    }
    
    return success;
}

// Helper function to get a random encounter
export function getRandomEncounter(terrainType) {
    const encounters = ENCOUNTERS.filter(e => e.terrain === terrainType);
    if (encounters.length === 0) return null;
    return encounters[Math.floor(Math.random() * encounters.length)];
}