/**
 * Domain-specific critique rubrics.
 *
 * A single fixed rubric was the biggest flaw in the first version of the critic:
 * it judged everything as if it were a real-time 3D renderer. Pointed at a 2D
 * RPG it would complain about missing volumetric lighting and surface wear, and
 * because the critic's fixes feed straight into the next coder brief, that
 * feedback actively drove good 2D art toward being worse.
 *
 * Each rubric therefore carries three things:
 *   - axes with weights, so scoring reflects what actually matters in the domain
 *   - calibration rules that pin what a low score means, so the critic can't drift
 *   - explicit NEGATIVE rules telling it what NOT to penalise
 *
 * That last part is what keeps a 2D game from being marked down for not being
 * Call of Duty.
 */

export const RUBRICS = {
  // ---------------------------------------------------------------- 2D games
  '2d_game': {
    label: '2D sprite / tile game',
    tiers: ['broken', 'placeholder_art', 'early_indie', 'indie', 'polished_indie', 'commercial_2d'],
    axes: [
      { key: 'readability', weight: 0.22, desc: 'Instant legibility: can you tell player, enemies, terrain, interactables and hazards apart at a glance? Silhouette clarity, foreground/background separation, no visual noise swallowing gameplay-critical elements.' },
      { key: 'art_cohesion', weight: 0.20, desc: 'Consistency of style, pixel density and resolution across every element. No mismatched placeholder shapes beside finished art. Consistent outline, shading and perspective conventions.' },
      { key: 'color_palette', weight: 0.16, desc: 'Deliberate, limited palette with harmonious hues and clear value separation between layers. Evidence of colour design rather than defaults.' },
      { key: 'environment_detail', weight: 0.16, desc: 'Tile and prop variety, decorative detail, transition/edge tiles between terrain types, absence of large repeated empty regions.' },
      { key: 'game_feel', weight: 0.14, desc: 'Visible evidence of life: animation states, particles, feedback effects, accent lighting, screen-space juice. A frozen static grid scores low.' },
      { key: 'ui_hud', weight: 0.12, uiOnly: true, desc: 'HUD craft: typography, spacing, hierarchy, restraint, and how well it integrates with the art style.' },
    ],
    rules: [
      'Flat untextured rectangles or default CSS colours standing in for sprites is placeholder art: art_cohesion below 30.',
      'A tilemap built from one repeated tile, with no variation and no transition tiles between terrain types, scores below 30 on environment_detail.',
      'If the player character cannot be identified at a glance, readability is below 30.',
      'Default saturated primaries (pure #ff0000, #00ff00, #0000ff) indicate no palette design: color_palette below 25.',
      'A scene with no animation, particles or state feedback of any kind scores below 35 on game_feel.',
    ],
    negativeRules: [
      'Do NOT penalise this for lacking 3D lighting, real-time shadows, ambient occlusion, volumetric effects, ray tracing, PBR materials or a post-processing chain. None of those belong in a 2D game.',
      'Do NOT ask for photorealism, higher polygon counts, or "more depth". Judge it purely as 2D craft.',
      'Deliberate pixel art, flat colour and limited palettes are legitimate style choices, not defects. Judge execution within the chosen style.',
    ],
  },

  // -------------------------------------------------------------- 2.5D games
  '2_5d': {
    label: '2.5D / isometric game',
    tiers: ['broken', 'placeholder_art', 'early_indie', 'indie', 'polished_indie', 'commercial_2d'],
    axes: [
      { key: 'depth_layering', weight: 0.20, desc: 'Convincing depth without true 3D: parallax between layers, correct overlap and draw order, scale cues, clear foreground/midground/background separation.' },
      { key: 'readability', weight: 0.20, desc: 'Gameplay legibility: player, enemies, walkable ground and obstacles instantly distinguishable despite the layered depth.' },
      { key: 'art_cohesion', weight: 0.18, desc: 'Consistent projection angle, pixel density and style across all sprites and tiles. Nothing drawn at a conflicting perspective.' },
      { key: 'lighting_shading', weight: 0.16, desc: 'Faked lighting done well: consistent light direction across all elements, contact shadows anchoring sprites to the ground, believable ambient shading.' },
      { key: 'environment_detail', weight: 0.14, desc: 'Prop and tile variety, decorative layering, height variation, absence of large flat repeated areas.' },
      { key: 'ui_hud', weight: 0.12, uiOnly: true, desc: 'HUD craft: typography, spacing, hierarchy, restraint, integration with the art style.' },
    ],
    rules: [
      'Sprites that float without a contact shadow or any ground anchoring score below 35 on lighting_shading.',
      'Inconsistent light direction between props and characters scores below 30 on lighting_shading.',
      'A single flat background layer with no parallax or depth separation scores below 30 on depth_layering.',
      'Incorrect draw order, where a sprite behind an object renders in front of it, is a critical defect.',
      'Mixed projection angles across tiles or props scores below 30 on art_cohesion.',
    ],
    negativeRules: [
      'Do NOT penalise this for lacking real 3D geometry, true dynamic shadows, PBR materials or ray tracing. Faked depth done convincingly is the goal.',
      'Do NOT ask for photorealism. Judge it as stylised 2.5D craft.',
    ],
  },

  // ---------------------------------------------------------- real-time 3D
  '3d_realtime': {
    label: 'real-time 3D scene',
    tiers: ['broken', 'programmer_art', 'indie', 'polished_indie', 'AA', 'AAA'],
    axes: [
      { key: 'lighting', weight: 0.24, desc: 'Lighting and shadows: direction, softness, contact shadows, ambient occlusion, bounce, exposure.' },
      { key: 'materials', weight: 0.24, desc: 'Materials and textures: surface detail, roughness/metalness variation, absence of flat untextured plastic.' },
      { key: 'composition', weight: 0.14, desc: 'Composition and framing: silhouette readability, depth cues, scene staging, sense of scale.' },
      { key: 'detail_density', weight: 0.20, desc: 'Detail density: geometric and texture richness, props, wear, absence of empty flat regions.' },
      { key: 'post_processing', weight: 0.13, desc: 'Post-processing: tone mapping, colour grading, bloom, motion blur, anti-aliasing quality.' },
      { key: 'ui_polish', weight: 0.05, uiOnly: true, desc: 'UI/HUD craft: typography, spacing, hierarchy, restraint.' },
    ],
    rules: [
      'A grey or untextured scene is programmer art and scores below 30 on materials, regardless of how clean the geometry is.',
      'Flat uniform lighting with no shadow gradient scores below 35 on lighting.',
      'An empty scene with a handful of primitives scores below 25 on detail_density.',
    ],
    negativeRules: [
      'Do NOT reward intent or effort you cannot see. Score only what is visible in the frame.',
    ],
  },

  // ------------------------------------------------------ interfaces / tools
  ui_app: {
    label: 'user interface / application',
    tiers: ['broken', 'unstyled', 'functional', 'polished', 'product_grade'],
    axes: [
      { key: 'typography', weight: 0.22, desc: 'Type craft: a deliberate typeface, a consistent size scale, comfortable line length and line height, no default Times New Roman.' },
      { key: 'layout_spacing', weight: 0.22, desc: 'Layout and rhythm: a consistent spacing scale, deliberate alignment, balanced density, no cramped or randomly-spaced elements.' },
      { key: 'hierarchy', weight: 0.20, desc: 'Visual hierarchy: the most important thing reads first, clear grouping, obvious primary action.' },
      { key: 'color_contrast', weight: 0.18, desc: 'Colour system and accessible contrast: a restrained palette, legible text contrast, meaningful use of accent colour.' },
      { key: 'restraint', weight: 0.18, desc: 'Restraint and finish: absence of gratuitous gradients, shadows, emoji and decoration; considered empty states and edges.' },
    ],
    rules: [
      'Default unstyled browser controls and default fonts score below 25 on typography.',
      'No consistent spacing scale, or elements touching container edges, scores below 30 on layout_spacing.',
      'Body text below roughly 4.5:1 contrast against its background is a critical defect.',
      'Everything at the same visual weight, with no clear entry point, scores below 30 on hierarchy.',
    ],
    negativeRules: [
      'Do NOT ask for game art, lighting, shadows, textures or 3D effects. This is an interface.',
      'Restraint is a virtue here. Do not request more decoration, animation or visual richness for its own sake.',
    ],
  },
};

export const DOMAIN_KEYS = Object.keys(RUBRICS);

/**
 * Infer the visual domain from free text when the planner didn't declare one.
 * Ordering matters: the 3D signals are checked before the generic game signals,
 * because "game" alone must never imply 3D.
 */
export function detectDomain(text = '') {
  const t = text.toLowerCase();

  if (/\b(fps|first[- ]person|third[- ]person|3d|three\.?js|webgl|raytrac|voxel|flight sim|racing sim)\b/.test(t)) {
    return '3d_realtime';
  }
  if (/\b(2\.5d|isometric|iso|axonometric|parallax|diablo-like|hades-like)\b/.test(t)) {
    return '2_5d';
  }
  if (/\b(2d|pixel art|sprite|tile|tilemap|top[- ]down|side[- ]scroll|platformer|roguelike|rpg|jrpg|puzzle|match[- ]3|adventure|metroidvania|shmup|bullet hell|strategy|4x|tower defense|turn[- ]based|card game|board game)\b/.test(t)) {
    return '2d_game';
  }
  if (/\b(dashboard|admin|crm|landing page|website|web app|form|table|report|analytics|tool|editor|client)\b/.test(t)) {
    return 'ui_app';
  }
  if (/\bgame\b/.test(t)) return '2d_game'; // a plain "game" is far more often 2D
  return 'ui_app';
}

export function getRubric(domain) {
  return RUBRICS[domain] ?? RUBRICS['2d_game'];
}

/** Axes that apply to this critique, dropping UI-only axes when no UI is shown. */
export function activeAxes(rubric, { hasUI }) {
  return rubric.axes.filter((a) => !a.uiOnly || hasUI);
}

/** JSON schema for a critique in this domain. */
export function buildCritiqueSchema(rubric, { hasUI }) {
  const axes = activeAxes(rubric, { hasUI });
  return {
    type: 'object',
    properties: {
      axis_scores: {
        type: 'object',
        properties: Object.fromEntries(axes.map((a) => [a.key, { type: 'integer', minimum: 0, maximum: 100 }])),
        required: axes.map((a) => a.key),
      },
      reads_as: { type: 'string', description: 'What this screenshot honestly looks like, in one blunt sentence' },
      tier: { type: 'string', enum: rubric.tiers },
      defects: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            issue: { type: 'string', description: 'A specific visible flaw' },
            severity: { type: 'string', enum: ['critical', 'major', 'minor'] },
            fix: { type: 'string', description: 'Concrete technical change that would fix it' },
          },
          required: ['issue', 'severity', 'fix'],
        },
      },
      strengths: { type: 'array', items: { type: 'string' } },
      criteria_met: {
        type: 'array',
        items: {
          type: 'object',
          properties: {
            criterion: { type: 'string' },
            met: { type: 'boolean' },
            note: { type: 'string' },
          },
          required: ['criterion', 'met'],
        },
      },
    },
    required: ['axis_scores', 'reads_as', 'tier', 'defects', 'strengths', 'criteria_met'],
  };
}

/** The critic's persona and calibration, specialised for the domain. */
export function buildCriticSystem(rubric) {
  return `You are a hostile art director reviewing a build for shipping approval. You are reviewing a ${rubric.label}. You have rejected work from people far more experienced than whoever made this, and your reputation rests on never letting mediocre work ship.

Rules you follow without exception:
- You score what is ACTUALLY VISIBLE in the image, not what you assume the code intends.
- You always list defects. If you can name fewer than three real defects, you are not looking hard enough.
- Every defect must come with a technically concrete fix that names the actual technique.
- You never award a tier above your evidence. The top tier means indistinguishable from a shipped commercial title in this category.

Calibration for a ${rubric.label}:
${rubric.rules.map((r) => `- ${r}`).join('\n')}

What is NOT a defect here:
${rubric.negativeRules.map((r) => `- ${r}`).join('\n')}

Respond with JSON only.`;
}

/** Weighted total, computed in code so the model cannot inflate a summary number. */
export function computeScore(rubric, axisScores, { hasUI }) {
  const axes = activeAxes(rubric, { hasUI });
  let total = 0;
  let weightUsed = 0;
  for (const axis of axes) {
    const v = Number(axisScores?.[axis.key]);
    if (!Number.isFinite(v)) continue;
    total += Math.max(0, Math.min(100, v)) * axis.weight;
    weightUsed += axis.weight;
  }
  return weightUsed ? Math.round(total / weightUsed) : 0;
}

/** Guidance handed to coder agents about how to produce assets in this domain. */
export function assetGuidance(domain) {
  switch (domain) {
    case '2d_game':
      return 'Assets are generated in code. Draw sprites and tiles procedurally onto offscreen canvases at load time '
        + '(document.createElement("canvas")), then blit them. Build a real tileset with variation and transition tiles '
        + 'rather than one repeated tile. Commit to a deliberate limited palette defined in one place. Use nearest-neighbour '
        + 'scaling (imageSmoothingEnabled = false) for pixel art.';
    case '2_5d':
      return 'Assets are generated in code. Draw sprites and tiles procedurally onto offscreen canvases. Keep one consistent '
        + 'projection angle and one consistent light direction across everything you draw. Always give sprites a contact '
        + 'shadow so they sit on the ground. Sort draw order by depth (y or z) every frame.';
    case '3d_realtime':
      return 'Assets are generated in code: procedural textures painted to a canvas and used as THREE.CanvasTexture, '
        + 'generated geometry, and Web Audio synthesis. You cannot download art.';
    default:
      return 'Assets are generated in code. Use system fonts, CSS gradients and inline SVG rather than downloading files.';
  }
}
