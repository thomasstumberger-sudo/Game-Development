/** 
 * Entry point and fixed-timestep loop.
 * 
 * The boot sequence:
 * 1. Get the canvas from index.html
 * 2. Size it to the window
 * 3. Build state with that canvas
 * 4. Wire up subsystems in dependency order
 * 5. Start the render loop
 * 
 * Pure module: no DOM access and no side effects until init is called.
 */
import { createState, addLayer, endTurn, applyDelta } from './state.js';
import { updateVisibility } from './hex.js';
import { drawMap } from './render-map.js';
import { drawUnit } from './render-unit.js';
import { drawHud, drawEncounter, encounterOptionAt } from './hud.js';
import { attachInput } from './input.js';
import { updateMove } from './movement.js';
import { EncounterSystem } from './encounters.js';
import { PALETTE } from './palette.js';

/** Layers at or above this z are drawn in screen space, not world space. */
const SCREEN_SPACE_Z = 2;

let gameLoop;
let state;
let detachInput;
let encounterSystem;

export function init(canvas) {
  try {
    // Initialize game state with canvas
    state = createState(canvas);
    
    // Register draw layers in z-order
    addLayer(state, 0, 'map', (ctx) => drawMap(ctx, state));
    addLayer(state, 1, 'unit', (ctx) => drawUnit(ctx, state));
    addLayer(state, 2, 'hud', (ctx) => drawHud(ctx, state));
    
    // The encounter system was previously constructed and then never connected
    // to anything: no state, no trigger call, no window drawn, no way to click
    // an option. All four ends are wired here.
    encounterSystem = new EncounterSystem(Math.random, () => {});
    encounterSystem.setState(state);

    // Screen space, above the HUD.
    addLayer(state, 3, 'encounter', (ctx) => drawEncounter(ctx, state, encounterSystem));

    const resolveOption = (index) => {
      if (index < 0 || !encounterSystem.active) return false;
      const { delta } = encounterSystem.choose(index);
      applyDelta(state, delta);
      return true;
    };

    detachInput = attachInput(canvas, state, {
      // An open encounter swallows the click, so the map is inert while a
      // decision is pending.
      onOption: (x, y) => resolveOption(encounterOptionAt(state, encounterSystem, x, y)),
      onOptionIndex: (index) => resolveOption(index),
      onHexClick: () => {},
      onEndTurn: () => {
        if (encounterSystem.active || state.unit.moving) return;
        endTurn(state);
      },
    });


    // Start the game loop
    gameLoop = requestAnimationFrame(render);
  } catch (error) {
    console.error('Failed to initialize game:', error);
    // Draw error message directly to canvas
    const ctx = canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = '#ff0000';
      ctx.font = '16px sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Initialization failed. See console for details.', canvas.width / 2, canvas.height / 2);
    }
  }
}

let lastFrameMs = 0;

function render(now = 0) {
  if (!state) return;

  // Real elapsed time, clamped so a backgrounded tab does not resume with one
  // enormous step. state.elapsed drives every pulse and fade in the renderers,
  // and nothing was incrementing it before, so all of them sat frozen.
  const dt = lastFrameMs ? Math.min(now - lastFrameMs, 250) : 1000 / 60;
  lastFrameMs = now;
  state.elapsed += dt;
  state.frame++;

  const { ctx, width, height } = state;

  ctx.fillStyle = PALETTE.BACKGROUND;
  ctx.fillRect(0, 0, width, height);
  ctx.imageSmoothingEnabled = false;

  // Movement, and everything arriving on a new hex sets off.
  const arrived = updateMove(state.unit, dt);
  if (arrived) {
    updateVisibility(state.tiles, arrived.q, arrived.r);
    if (!state.unit.moving) {
      endTurn(state);
      encounterSystem.trigger(state);
    }
  }


  // World-space layers draw inside the camera transform; screen-space layers
  // (the HUD) draw outside it. Omitting this translate is what pushed the map
  // off the top-left corner of the canvas while the HUD kept rendering fine.
  ctx.save();
  ctx.translate(state.camera.x, state.camera.y);
  for (const layer of state.layers) {
    if (layer.z < SCREEN_SPACE_Z) layer.draw(ctx, state);
  }
  ctx.restore();

  for (const layer of state.layers) {
    if (layer.z >= SCREEN_SPACE_Z) layer.draw(ctx, state);
  }

  // Continue the loop
  gameLoop = requestAnimationFrame(render);
}

// Handle window resize
window.addEventListener('resize', () => {
  if (!state || !state.canvas) return;
  
  const { canvas } = state;
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;

  // state.width/height are what every screen-space renderer measures against.
  // Resizing the canvas without updating them left the HUD laying itself out
  // for the old viewport.
  state.width = canvas.width;
  state.height = canvas.height;

  state.camera.x = canvas.width / 2;
  state.camera.y = canvas.height / 2;
});

// Initialize the game when the page loads
window.addEventListener('load', () => {
  const canvas = document.querySelector('canvas');
  if (!canvas) {
    console.error('No canvas element found in index.html');
    return;
  }
  
  // Size the canvas to the window
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  
  init(canvas);
  
  // Remove loading overlay after successful initialization
  const loadingElement = document.getElementById('loading');
  if (loadingElement) {
    loadingElement.style.display = 'none';
  }
});