/** 
 * The single source of colour for the whole game.
 *
 * Every colour used anywhere must come from here. No hard-coded hex strings
 * in any other module — that is what keeps the palette deliberate and limited
 * rather than drifting into 40 slightly different greens.
 *
 * Direction: earthy Bronze Age tones for the tribe, cold unnatural tones for
 * the Fae, everything slightly muted so the two families read as different
 * worlds sitting on the same map.
 */

export const PALETTE = {
    // --- terrain, earthy and muted -----------------------------------------
    GRASS: '#556b2f',
    FOREST: '#228b22',
    WATER: '#1e90ff',
    MOUNTAIN: '#708090',
    SWAMP: '#4b5320',
    FAE_LAND: '#9400d3',
    
    // --- terrain variation, for per-tile noise ------------------------------
    GRASS_V1: '#3cb371',
    GRASS_V2: '#228b22',
    FOREST_V1: '#228b22',
    FOREST_V2: '#004d00',
    MOUNTAIN_V1: '#696969',
    MOUNTAIN_V2: '#555555',
    SWAMP_V1: '#556b2f',
    SWAMP_V2: '#3e5d2d',
    WATER_V1: '#4682b4',
    WATER_V2: '#0000ff',
    FAE_V1: '#9932cc',
    FAE_V2: '#8a2be2',
    
    // --- the tribe ----------------------------------------------------------
    SHAMAN_CHIEF: '#8b4513',
    SHAMAN_ACCENT: '#a0522d',
    UNIT_OUTLINE: '#654321',
    
    // --- the Fae, cold and unnatural ---------------------------------------
    FAERY_GREEN: '#32cd32',
    FAERY_BLUE: '#00bfff',
    FAERY_PURPLE: '#9370db',
    
    // --- UI: carved bone and woad stain ------------------------------------
    PARCHMENT: '#d2b48c',
    BROWN_DARK: '#5c4033',
    BROWN_MEDIUM: '#8b4513',
    BROWN_LIGHT: '#a0522d',
    BROWN_DARKER: '#3e2723',
    UI_BORDER: '#5c4033',
    UI_SHADOW: '#000000',
    
    // --- resources ----------------------------------------------------------
    FOOD: '#ff6347',
    WATER_RES: '#1e90ff',
    MORALE: '#ffd700',
    MAGIC: '#9370db',
    POPULATION: '#ff4500',
    MATERIALS: '#8b4513',
    
    // --- feedback -----------------------------------------------------------
    HIGHLIGHT: '#ffffff',
    SELECTED: '#f87171',
    ADJACENT: '#a78bfa',
    ENCOUNTER: '#ffd700',
    
    // --- background and structure ------------------------------------------
    BACKGROUND: '#141018',
    TILE_BORDER: '#241d29',
    ERROR: '#ff6b6b',
};

/** Fog tiers. Multiplied into a tile's fill so visibility reads at a glance. */
export const VISIBILITY_ALPHA = {
    explored: 1.0,
    adjacent: 0.55,
    outer: 0.28,
    unseen: 0.0,
};