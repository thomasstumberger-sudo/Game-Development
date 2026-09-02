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
    GRASS: '#4a5d2f',
    FOREST: '#2d6b22',
    WATER: '#1e70c0',
    MOUNTAIN: '#607080',
    SWAMP: '#3b4d20',
    FAE_LAND: '#7400a3',
    
    // --- terrain variation, for per-tile noise ------------------------------
    GRASS_V1: '#3a5d2f',
    GRASS_V2: '#2d6b22',
    FOREST_V1: '#2d6b22',
    FOREST_V2: '#004d00',
    MOUNTAIN_V1: '#596979',
    MOUNTAIN_V2: '#455565',
    SWAMP_V1: '#3a5d2f',
    SWAMP_V2: '#2e4d2d',
    WATER_V1: '#2670c0',
    WATER_V2: '#0000c0',
    FAE_V1: '#7932a3',
    FAE_V2: '#6a2be2',
    
    // --- terrain highlights for texture variation --------------------------
    GRASS_HIGHLIGHT: '#5a7d4f',
    FOREST_HIGHLIGHT: '#3d7b32',
    MOUNTAIN_HIGHLIGHT: '#708090',
    SWAMP_HIGHLIGHT: '#4b5d30',
    WATER_HIGHLIGHT: '#2e80d0',
    FAE_HIGHLIGHT: '#8410b3',
    
    // --- the tribe ----------------------------------------------------------
    SHAMAN_CHIEF: '#8b4513',  // Brown for the shaman chief
    SHAMAN_ACCENT: '#a0522d', // Slightly lighter brown for details
    UNIT_OUTLINE: '#000000',   // Black outline to make it stand out clearly against any background
    UNIT_HIGHLIGHT: '#ffff00', // Yellow highlight for better visibility
    
    // --- the Fae, cold and unnatural ---------------------------------------
    FAERY_GREEN: '#228b22',
    FAERY_BLUE: '#0090ff',
    FAERY_PURPLE: '#7050c0',
    
    // --- UI: carved bone and woad stain ------------------------------------
    PARCHMENT: '#d2b48c',     // Carved bone background
    BROWN_DARK: '#5c4033',   // Dark brown for borders and details
    BROWN_MEDIUM: '#8b4513', // Medium brown for UI elements
    BROWN_LIGHT: '#a0522d',  // Light brown for highlights
    BROWN_DARKER: '#3e2723', // Darkest brown for texture details
    UI_BORDER: '#5c4033',    // Border color for UI elements
    UI_SHADOW: '#000000',    // Shadow effect for depth
    
    // --- resources ----------------------------------------------------------
    FOOD: '#8B4513', 
    WATER_RES: '#4682B4',
    MORALE: '#DAA520',
    MAGIC: '#9370DB',
    POPULATION: '#A52A2A',
    MATERIALS: '#8B4513',
    HEALTH: '#FF69B4',
    
    // --- resource bar colors ------------------------------------------------
    FOOD_COLOR: '#8B4513',
    WATER_COLOR: '#4682B4',
    ENERGY_COLOR: '#DAA520',
    
    // --- feedback -----------------------------------------------------------
    HIGHLIGHT: '#ffff00',
    SELECTED: '#f87171',
    ADJACENT: '#a78bfa',
    ENCOUNTER: '#ffd700',
    SUCCESS: '#00ff00',   // Green for success
    FAILURE: '#ff0000',   // Red for failure
    
    // --- background and structure ------------------------------------------
    BACKGROUND: '#141018',
    TILE_BORDER: '#241d29',
    TRANSITION: '#ffffff',
    ERROR: '#ff6b6b',
    
    // --- visibility colors --------------------------------------------------
    EXPLORED: '#3e2723',
    ADJACENT: '#5c4033',
    OUTER: '#8b4513'
};

/** Fog tiers. Multiplied into a tile's fill so visibility reads at a glance. */
export const VISIBILITY_ALPHA = {
    explored: 1.0,
    adjacent: 0.55,
    outer: 0.28,
    unseen: 0.0
};

export const MAGIC_GLOW = '#d8bfd8';