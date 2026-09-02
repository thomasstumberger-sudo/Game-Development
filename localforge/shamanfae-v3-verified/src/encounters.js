/** 
 * Encounter data, triggering, and resolution.
 *
 * A representative sample, not the full 120 from the design document. The data
 * shape is what matters: terrain gating, options with costs and effects, and a
 * resolution that returns a plain delta the caller applies to state.
 *
 * Pure module: no DOM, no side effects on import. The class is exported rather
 * than an instance so nothing is constructed at import time.
 */

import { key } from './hex.js';

export const ENCOUNTERS = [
  {
    id: 'wild-plant',
    name: 'Wild Plant',
    description:
      'A plant with faintly glowing veins grows where nothing else will. The tribe watches it, and it seems to watch back.',
    type: 'resource',
    terrain: ['grass', 'forest', 'swamp'],
    options: [
      { text: 'Harvest it', effect: { food: 5 }, cost: {} },
      { text: 'Burn it where it stands', effect: { morale: 2, weirdness: -1 }, cost: {} },
      { text: 'Leave it alone', effect: {}, cost: {} },
    ],
  },
  {
    id: 'fae-spirit',
    name: 'Fae Spirit',
    description:
      'A small spirit unfolds itself from the air, courteous and far too interested in your people.',
    type: 'spirit',
    terrain: ['forest', 'swamp', 'fae_land'],
    options: [
      { text: 'Accept its blessing', effect: { magic: 10, weirdness: 2 }, cost: {} },
      { text: 'Bargain for safe passage', effect: { morale: 3 }, cost: { magic: 1 } },
      { text: 'Refuse and walk on', effect: { morale: -2 }, cost: {} },
    ],
  },
  {
    id: 'water-source',
    name: 'Hidden Spring',
    description:
      'Clear water rises from bare rock, shimmering slightly against the current.',
    type: 'resource',
    terrain: ['grass', 'forest', 'mountain'],
    options: [
      { text: 'Drink deeply and rest', effect: { water: 10, morale: 1 }, cost: {} },
      { text: 'Fill every skin the tribe carries', effect: { water: 5 }, cost: {} },
      { text: 'Study the source', effect: { magic: 1, weirdness: 1 }, cost: {} },
    ],
  },
  {
    id: 'fae-toll',
    name: 'The Toll',
    description:
      'Something tall and thin stands across the path. It does not speak, but the price is somehow understood.',
    type: 'challenge',
    terrain: ['fae_land', 'forest', 'mountain'],
    options: [
      { text: 'Pay in magic', effect: { weirdness: -1 }, cost: { magic: 2 } },
      { text: 'Pay in food', effect: {}, cost: { food: 8 } },
      { text: 'Refuse the toll', effect: { morale: -5, weirdness: 3 }, cost: {} },
    ],
  },
  {
    id: 'standing-stones',
    name: 'Standing Stones',
    description:
      'Nine stones in a ring, older than the Fae and indifferent to them. The magic here is quiet and deep.',
    type: 'spirit',
    terrain: ['grass', 'mountain'],
    options: [
      { text: 'Perform a rite', effect: { magic: 6, morale: 2 }, cost: {} },
      { text: 'Shelter here for the night', effect: { morale: 4 }, cost: { food: 2 } },
      { text: 'Pass without stopping', effect: {}, cost: {} },
    ],
  },
  {
    id: 'drowned-road',
    name: 'The Drowned Road',
    description:
      'A causeway runs under the water, paved and straight. It was not built by anyone the tribe knows of.',
    type: 'challenge',
    terrain: ['swamp', 'water'],
    options: [
      { text: 'Follow it', effect: { weirdness: 4, magic: 3 }, cost: { morale: 3 } },
      { text: 'Ford the shallows instead', effect: { water: 3 }, cost: { food: 2 } },
      { text: 'Turn back', effect: {}, cost: {} },
    ],
  },
  {
    id: 'fae-temple',
    name: 'Fae Temple',
    description:
      'A great archway of stone and bone stands where the Fae once built their sacred places.',
    type: 'spirit',
    terrain: ['fae_land', 'mountain'],
    options: [
      { text: 'Enter and pray', effect: { magic: 15, morale: 3 }, cost: {} },
      { text: 'Bargain with the spirits', effect: { magic: 5, weirdness: -2 }, cost: { magic: 2 } },
      { text: 'Leave it alone', effect: {}, cost: {} },
    ],
  },
  {
    id: 'ritual-bind',
    name: 'Binding Ritual',
    description:
      'The Fae realm responds to your binding. A chain encounter is triggered!',
    type: 'ritual',
    terrain: ['fae_land'],
    options: [
      { text: 'Bind the spirit', effect: {}, cost: { magic: 3 } },
      { text: 'Attempt to negotiate', effect: {}, cost: { magic: 2, morale: 1 } },
      { text: 'Leave it alone', effect: {}, cost: {} },
    ],
    chain: {
      trigger: 'bind_success',
      encounters: ['fae-temple', 'standing-stones']
    }
  },
  {
    id: 'ritual-bargain',
    name: 'Bargaining Ritual',
    description:
      'The Fae realm responds to your bargaining. A chain encounter is triggered!',
    type: 'ritual',
    terrain: ['fae_land'],
    options: [
      { text: 'Negotiate for magic', effect: {}, cost: { magic: 4 } },
      { text: 'Negotiate for resources', effect: {}, cost: { food: 3, water: 2 } },
      { text: 'Leave it alone', effect: {}, cost: {} },
    ],
    chain: {
      trigger: 'bargain_success',
      encounters: ['fae-spirit', 'wild-plant']
    }
  },
  {
    id: 'ritual-banish',
    name: 'Banishing Ritual',
    description:
      'The Fae realm responds to your banishing. A chain encounter is triggered!',
    type: 'ritual',
    terrain: ['fae_land'],
    options: [
      { text: 'Banish the threat', effect: {}, cost: { magic: 2 } },
      { text: 'Negotiate instead', effect: {}, cost: { magic: 1, morale: 2 } },
      { text: 'Leave it alone', effect: {}, cost: {} },
    ],
    chain: {
      trigger: 'banish_success',
      encounters: ['fae-temple', 'standing-stones']
    }
  },
  {
    id: 'ritual-blessing',
    name: 'Blessing Ritual',
    description:
      'The Fae realm responds to your blessing. A chain encounter is triggered!',
    type: 'ritual',
    terrain: ['fae_land'],
    options: [
      { text: 'Minor Blessing', effect: {}, cost: { magic: 1 } },
      { text: 'Major Blessing', effect: {}, cost: { magic: 3 } },
      { text: 'Leave it alone', effect: {}, cost: {} },
    ],
    chain: {
      trigger: 'blessing_success',
      encounters: ['water-source', 'wild-plant']
    }
  }
];

export class EncounterSystem {
  constructor(rng, onShake) {
    this.rng = rng;
    this.onShake = onShake;
    this.active = false;
    this.current = null;
    this.state = null;
    this.chainQueue = [];
    this.triggeredChains = new Set();
  }

  setState(state) {
    this.state = state;
  }

  /**
   * Roll for an encounter on the tile the unit is standing on.
   *
   * The old version required `tile.encounter` to already be set before it would
   * assign one, so it could never fire, and it read `this.state` which nothing
   * ever populated. It also called Math.random() directly, defeating the
   * injected rng.
   *
   * @param {object} state
   * @param {number} chance probability an eligible tile produces an encounter
   * @returns {boolean} whether an encounter was triggered
   */
  trigger(state, chance = 0.45) {
    if (this.active) return false;

    const target = state ?? this.state;
    if (!target) return false;

    const tile = target.tiles.get(key(target.unit.q, target.unit.r));
    // A tile that has already produced an encounter stays quiet until its
    // regeneration counter comes back around.
    if (!tile || tile.encounter) return false;
    if (this.rng() > chance) return false;

    const candidates = ENCOUNTERS.filter(
      (e) => e.terrain.includes(tile.terrain.id) && e.type !== 'ritual',
    );
    if (!candidates.length) return false;

    this.current = candidates[Math.floor(this.rng() * candidates.length)];
    this.active = true;
    tile.encounter = this.current.id;
    return true;
  }

  /** @returns {object} {delta, affordable} */
  choose(optionIndex) {
    if (!this.active || !this.current) return { delta: {}, affordable: false };
    
    const option = this.current.options[optionIndex];
    if (!option) return { delta: {}, affordable: false };
    
    const delta = { ...option.effect };
    for (const [res, amount] of Object.entries(option.cost ?? {})) {
      delta[res] = (delta[res] ?? 0) - amount;
    }
    
    // Handle ritual success/failure logic
    if (this.current.type === 'ritual' && this.state) {
      // Simulate ritual success/failure based on magic cost and available resources
      const magicCost = option.cost.magic || 0;
      if (magicCost > 0 && this.state.resources.magic >= magicCost) {
        // Ritual has a chance of success based on magic pool and skill
        const successChance = Math.min(0.8, (this.state.unit.magic / 10) + 0.2);
        const ritualSuccess = this.rng() < successChance;
        
        // Add ritual result to delta for visual feedback
        delta.ritualSuccess = ritualSuccess;
        
        // Set ritualCast flag on unit for visual feedback during casting
        delta.ritualCast = 30; // 30 frames of casting animation (about 0.5 seconds at 60fps)
        
        // Apply additional effects based on success/failure
        if (ritualSuccess) {
          // Success - add beneficial effects
          if (this.current.id === 'ritual-bind') {
            delta.weirdness = (delta.weirdness || 0) - 2; // Reduce weirdness
          } else if (this.current.id === 'ritual-bargain') {
            delta.morale = (delta.morale || 0) + 3; // Increase morale
          } else if (this.current.id === 'ritual-banish') {
            delta.weirdness = (delta.weirdness || 0) - 3; // Reduce weirdness significantly
          } else if (this.current.id === 'ritual-blessing') {
            delta.magic = (delta.magic || 0) + 5; // Add magic
          }
        } else {
          // Failure - add negative effects
          if (this.current.id === 'ritual-bind' || this.current.id === 'ritual-bargain') {
            delta.morale = (delta.morale || 0) - 2; // Decrease morale
          } else if (this.current.id === 'ritual-banish') {
            delta.weirdness = (delta.weirdness || 0) + 2; // Increase weirdness
          }
        }
      } else {
        // Not enough magic - ritual fails
        delta.ritualSuccess = false;
      }
    }
    
    // Check if this encounter triggers a chain
    if (this.current.chain) {
      // Add to chain queue for next turn
      this.chainQueue.push({
        trigger: this.current.chain.trigger,
        encounters: this.current.chain.encounters
      });
    }
    
    // Trigger screen shake on encounter resolution for impactful events
    if (this.onShake) {
      // More intense shake for significant encounters
      const isImpactful = this.current && (this.current.type === 'spirit' || this.current.type === 'challenge');
      const isMajorEncounter = this.current && (this.current.id === 'fae-spirit' || this.current.id === 'fae-temple' || this.current.id === 'standing-stones');
      
      let intensity = 3;
      let duration = 250;
      
      if (isMajorEncounter) {
        intensity = 6;
        duration = 400;
      } else if (isImpactful) {
        intensity = 5;
        duration = 350;
      }
      
      this.onShake(intensity, duration);
    }
    
    this.active = false;
    this.current = null;
    
    // Return the delta for applying to state
    return { delta: delta || {}, affordable: true };
  }

  dismiss() {
    this.active = false;
    this.current = null;
  }

  /** 
   * End the turn and process any chain encounters.
   * This is called at the end of each turn to handle chain encounters.
   */
  endTurn(state) {
    // Check for any chain encounters that should be triggered
    this.checkChainEncounters(state);
    
    // Clear the chain state for next turn
    this.clearChainState();
    
    // Return a proper object to avoid undefined issues
    return { delta: {} };
  }
  
  /**
   * Check if any chain encounters should be triggered based on previous actions.
   * This is called at the start of a turn after all actions are resolved.
   */
  checkChainEncounters(state) {
    // If there are chain encounters in the queue, trigger them
    if (this.chainQueue.length > 0) {
      const nextChain = this.chainQueue.shift();
      
      // Only trigger if we haven't already triggered this chain encounter in this turn
      const chainKey = `${nextChain.trigger}-${state.turn}`;
      if (!this.triggeredChains.has(chainKey)) {
        // Find a random encounter from the chain list that's appropriate for current terrain
        const tile = state.tiles.get(`${state.unit.q},${state.unit.r}`);
        if (tile) {
          const candidates = nextChain.encounters.map(id => ENCOUNTERS.find(e => e.id === id))
            .filter(Boolean)
            .filter(e => e.terrain.includes(tile.terrain.id));
          
          if (candidates.length > 0) {
            const encounter = candidates[Math.floor(this.rng() * candidates.length)];
            this.current = encounter;
            this.active = true;
            tile.encounter = encounter.id;
            
            // Mark this chain as triggered to prevent duplicate triggers in the same turn
            this.triggeredChains.add(chainKey);
          }
        }
      }
    }
  }

  clearChainState() {
    this.chainQueue = [];
    this.triggeredChains.clear();
  }
}

