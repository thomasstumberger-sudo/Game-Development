/**
 * Creates the runnable skeleton before any agent touches anything.
 *
 * This exists because of a hard-won rule: verification must be possible from
 * task one. If the first agent has to invent the HTML entry point, the module
 * layout and the render loop before anything can be loaded in a browser, then
 * the first three tasks are unverifiable and errors compound silently.
 *
 * Libraries are vendored into the app via npm rather than loaded from a CDN, so
 * the whole run is same-origin and works with no internet once seeded.
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { log } from './logger.js';

const execFileAsync = promisify(execFile);

const INDEX_HTML = (title, importmap, entry) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<style>
  html, body { margin: 0; padding: 0; overflow: hidden; background: #000; height: 100%; }
  canvas { display: block; width: 100vw; height: 100vh; }
  #hud { position: fixed; inset: 0; pointer-events: none; font-family: system-ui, sans-serif; color: #fff; }
  #boot-error { position: fixed; inset: 0; background: #200; color: #f88; font: 13px/1.5 monospace;
                padding: 24px; white-space: pre-wrap; overflow: auto; display: none; z-index: 999; }
</style>
${importmap}
</head>
<body>
<div id="hud"></div>
<pre id="boot-error"></pre>
<script>
  // Surface module-level failures on the page as well as the console, so a
  // white screen is never a mystery.
  window.addEventListener('error', (e) => {
    const el = document.getElementById('boot-error');
    el.style.display = 'block';
    el.textContent += (e.message || e.error) + '\\n' + (e.error && e.error.stack || '') + '\\n\\n';
  });
  window.addEventListener('unhandledrejection', (e) => {
    const el = document.getElementById('boot-error');
    el.style.display = 'block';
    el.textContent += 'Unhandled rejection: ' + (e.reason && e.reason.stack || e.reason) + '\\n\\n';
  });
</script>
<script type="module" src="${entry}"></script>
</body>
</html>
`;

const THREE_IMPORTMAP = `<script type="importmap">
{
  "imports": {
    "three": "./node_modules/three/build/three.module.js",
    "three/addons/": "./node_modules/three/examples/jsm/"
  }
}
</script>`;

const THREE_MAIN = `import * as THREE from 'three';

/**
 * Minimal runnable skeleton. Agents build on top of this: they are expected to
 * replace the placeholder scene contents, not the bootstrapping.
 *
 * The renderer is parked on window so the verification harness can read
 * renderer.info for draw-call and triangle counts.
 */
const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.0;
document.body.appendChild(renderer.domElement);
window.renderer = renderer;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0b0d12);
scene.fog = new THREE.Fog(0x0b0d12, 20, 120);
window.scene = scene;

const camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, 0.1, 1000);
camera.position.set(0, 1.7, 6);
window.camera = camera;

const hemi = new THREE.HemisphereLight(0x9fb8ff, 0x30281f, 0.6);
scene.add(hemi);

const sun = new THREE.DirectionalLight(0xffe9c4, 2.2);
sun.position.set(8, 14, 6);
sun.castShadow = true;
sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.near = 0.5;
sun.shadow.camera.far = 80;
scene.add(sun);

const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(200, 200),
  new THREE.MeshStandardMaterial({ color: 0x3b3f45, roughness: 0.95, metalness: 0.0 })
);
ground.rotation.x = -Math.PI / 2;
ground.receiveShadow = true;
scene.add(ground);

const placeholder = new THREE.Mesh(
  new THREE.BoxGeometry(1.5, 1.5, 1.5),
  new THREE.MeshStandardMaterial({ color: 0x8899aa, roughness: 0.4, metalness: 0.3 })
);
placeholder.position.set(0, 0.75, 0);
placeholder.castShadow = true;
scene.add(placeholder);

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

const clock = new THREE.Clock();

/** Modules can register per-frame callbacks here instead of nesting rAF loops. */
window.updaters = [];

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.1);
  for (const fn of window.updaters) {
    try { fn(dt); } catch (err) { console.error('updater failed:', err); }
  }
  placeholder.rotation.y += dt * 0.4;
  renderer.render(scene, camera);
}
animate();
`;

const PLAIN_MAIN = `/** Minimal runnable entry point. Agents build on top of this. */
const root = document.getElementById('hud');
root.innerHTML = '<div style="padding:24px">Application booting…</div>';
`;

/**
 * 2D / 2.5D skeleton.
 *
 * Deliberately opinionated, because these are the decisions a 30B model gets
 * wrong when left to invent them: a fixed-timestep accumulator (not dt-scaled
 * physics), a camera with world/screen separation, depth-sorted layer drawing,
 * and nearest-neighbour scaling. Agents extend this rather than rebuilding it.
 */
const MAIN_2D = (iso) => `/**
 * Core loop and rendering scaffold. Build on top of this; do not replace it.
 *
 *   window.game.layers    - draw callbacks, rendered in ascending z order
 *   window.game.updaters  - fixed-timestep update callbacks (dt is constant)
 *   window.game.camera    - world-space camera; use worldToScreen() when drawing
 *   window.game.input     - live keyboard/mouse state
 */
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d', { alpha: false });

// Crisp pixels. Essential for pixel art; harmless otherwise.
ctx.imageSmoothingEnabled = false;

const game = {
  canvas,
  ctx,
  width: 0,
  height: 0,
  camera: { x: 0, y: 0, zoom: ${iso ? '1' : '1'} },
  input: { keys: new Set(), mouse: { x: 0, y: 0, down: false } },
  layers: [],   // { z, name, draw(ctx, game) }
  updaters: [], // { name, update(dt, game) }
  time: 0,
  frame: 0,
};
window.game = game;

function resize() {
  const dpr = Math.min(devicePixelRatio, 2);
  game.width = innerWidth;
  game.height = innerHeight;
  canvas.width = Math.floor(innerWidth * dpr);
  canvas.height = Math.floor(innerHeight * dpr);
  canvas.style.width = innerWidth + 'px';
  canvas.style.height = innerHeight + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.imageSmoothingEnabled = false;
}
addEventListener('resize', resize);
resize();

addEventListener('keydown', (e) => game.input.keys.add(e.code));
addEventListener('keyup', (e) => game.input.keys.delete(e.code));
addEventListener('mousemove', (e) => { game.input.mouse.x = e.clientX; game.input.mouse.y = e.clientY; });
addEventListener('mousedown', () => { game.input.mouse.down = true; });
addEventListener('mouseup', () => { game.input.mouse.down = false; });

/** World space -> screen space. Always draw through this. */
game.worldToScreen = (wx, wy) => {${iso ? `
  // Isometric projection: 2:1 diamond tiles.
  const sx = (wx - wy) * 0.5;
  const sy = (wx + wy) * 0.25;
  return {
    x: (sx - game.camera.x) * game.camera.zoom + game.width / 2,
    y: (sy - game.camera.y) * game.camera.zoom + game.height / 2,
  };` : `
  return {
    x: (wx - game.camera.x) * game.camera.zoom + game.width / 2,
    y: (wy - game.camera.y) * game.camera.zoom + game.height / 2,
  };`}
};

/**
 * Draw a sprite once onto an offscreen canvas and reuse it. Re-drawing vector
 * shapes every frame is the usual cause of a 2D game running at 15fps.
 */
game.makeSprite = (w, h, paint) => {
  const off = document.createElement('canvas');
  off.width = w;
  off.height = h;
  const c = off.getContext('2d');
  c.imageSmoothingEnabled = false;
  paint(c, w, h);
  return off;
};

game.addLayer = (z, name, draw) => {
  game.layers.push({ z, name, draw });
  game.layers.sort((a, b) => a.z - b.z);
};

// ---------------------------------------------------------------- placeholder
// Agents replace all of this with real content. It is written the way real
// content should be written: art pre-rendered once with makeSprite, drawn
// through worldToScreen, registered as z-ordered layers.

const TILE = 32;

// Two ground tiles with per-tile noise, so the grid never reads as one flat colour.
const groundTiles = ['#2f3d2a', '#36452f'].map((base) => game.makeSprite(TILE, TILE, (c, w, h) => {
  c.fillStyle = base;
  c.fillRect(0, 0, w, h);
  for (let i = 0; i < 40; i++) {
    c.fillStyle = 'rgba(255,255,255,' + (0.02 + Math.random() * 0.05).toFixed(3) + ')';
    c.fillRect(Math.random() * w | 0, Math.random() * h | 0, 2, 2);
  }
}));

game.addLayer(0, 'ground', (c, g) => {
  c.fillStyle = '#141a22';
  c.fillRect(0, 0, g.width, g.height);
  const cols = Math.ceil(g.width / TILE) + 2;
  const rows = Math.ceil(g.height / TILE) + 2;
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      const tile = groundTiles[(x + y) % 2];
      c.drawImage(tile, x * TILE - TILE, y * TILE - TILE);
    }
  }
});

const playerSprite = game.makeSprite(24, 24, (c, w, h) => {
  c.fillStyle = '#e8c48a';
  c.fillRect(4, 2, w - 8, h - 4);
  c.fillStyle = '#c79a5b';
  c.fillRect(4, h - 8, w - 8, 6);
  c.fillStyle = '#2b1d12';
  c.fillRect(8, 7, 3, 3);
  c.fillRect(w - 11, 7, 3, 3);
});

game.addLayer(10, 'placeholder', (c, g) => {
  const p = g.worldToScreen(0, 0);
  const bob = Math.round(2 * Math.sin(g.time * 3));

  // Contact shadow: anchors the sprite to the ground instead of floating.
  c.fillStyle = 'rgba(0,0,0,0.35)';
  c.beginPath();
  c.ellipse(p.x, p.y + 14, 12, 4, 0, 0, Math.PI * 2);
  c.fill();

  c.drawImage(playerSprite, p.x - 12, p.y - 12 + bob);

  c.fillStyle = '#9fb0c4';
  c.font = '13px system-ui, sans-serif';
  c.textAlign = 'center';
  c.fillText('scaffold ready — replace these layers', p.x, p.y + 48);
});

// --------------------------------------------------------------- the game loop
const STEP = 1 / 60;  // fixed timestep: deterministic physics, stable feel
let accumulator = 0;
let last = performance.now();

function frame(now) {
  requestAnimationFrame(frame);

  let elapsed = (now - last) / 1000;
  last = now;
  if (elapsed > 0.25) elapsed = 0.25; // don't spiral after a tab stall
  accumulator += elapsed;

  while (accumulator >= STEP) {
    game.time += STEP;
    for (const u of game.updaters) {
      try { u.update(STEP, game); } catch (err) { console.error('updater "' + u.name + '" failed:', err); }
    }
    accumulator -= STEP;
  }

  ctx.save();
  for (const layer of game.layers) {
    try { layer.draw(ctx, game); } catch (err) { console.error('layer "' + layer.name + '" failed:', err); }
  }
  ctx.restore();
  game.frame++;
}
requestAnimationFrame(frame);
`;

const INDEX_2D = (title) => `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${title}</title>
<style>
  html, body { margin: 0; padding: 0; overflow: hidden; background: #0b0d12; height: 100%; }
  canvas { display: block; image-rendering: pixelated; }
  #hud { position: fixed; inset: 0; pointer-events: none; font-family: system-ui, sans-serif; color: #fff; }
  #boot-error { position: fixed; inset: 0; background: #200; color: #f88; font: 13px/1.5 monospace;
                padding: 24px; white-space: pre-wrap; overflow: auto; display: none; z-index: 999; }
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="hud"></div>
<pre id="boot-error"></pre>
<script>
  window.addEventListener('error', (e) => {
    const el = document.getElementById('boot-error');
    el.style.display = 'block';
    el.textContent += (e.message || e.error) + '\\n' + (e.error && e.error.stack || '') + '\\n\\n';
  });
  window.addEventListener('unhandledrejection', (e) => {
    const el = document.getElementById('boot-error');
    el.style.display = 'block';
    el.textContent += 'Unhandled rejection: ' + (e.reason && e.reason.stack || e.reason) + '\\n\\n';
  });
</script>
<script type="module" src="./src/main.js"></script>
</body>
</html>
`;

export async function scaffoldApp({ appDir, directives }) {
  fs.mkdirSync(appDir, { recursive: true });

  // The domain decides the skeleton. An earlier version keyed off the word
  // "game" appearing anywhere in the goal, which handed every 2D RPG a three.js
  // 3D scene it then had to fight against.
  const domain = directives.visual_domain ?? '2d_game';
  const usesThree = domain === '3d_realtime' || /three/i.test(directives.stack ?? '');
  const uses2D = !usesThree && (domain === '2d_game' || domain === '2_5d');

  if (fs.existsSync(path.join(appDir, 'index.html'))) {
    log.info('scaffold', 'existing app detected, leaving it alone');
    return { usesThree, uses2D, fresh: false };
  }

  const kind = usesThree ? 'three.js 3D' : uses2D ? `${domain === '2_5d' ? 'isometric 2.5D' : '2D canvas'}` : 'plain web';
  log.step('scaffold', `creating ${kind} skeleton`);

  if (!fs.existsSync(path.join(appDir, 'package.json'))) {
    fs.writeFileSync(path.join(appDir, 'package.json'), JSON.stringify({
      name: (directives.project_name || 'app').toLowerCase().replace(/[^a-z0-9-]+/g, '-'),
      version: '0.1.0',
      type: 'module',
      private: true,
    }, null, 2));
  }

  if (usesThree) {
    try {
      log.info('scaffold', 'installing three.js locally (vendored, so the run works offline)');
      await execFileAsync('npm', ['install', 'three@0.170.0', '--no-audit', '--no-fund'], {
        cwd: appDir, timeout: 300000,
      });
      log.ok('scaffold', 'three.js installed');
    } catch (err) {
      log.warn('scaffold', `three.js install failed (${err.message.slice(0, 120)}); falling back to CDN import map`);
    }
  }

  fs.mkdirSync(path.join(appDir, 'src'), { recursive: true });

  if (uses2D) {
    fs.writeFileSync(path.join(appDir, 'index.html'), INDEX_2D(directives.project_name || 'Game'));
    fs.writeFileSync(path.join(appDir, 'src', 'main.js'), MAIN_2D(domain === '2_5d'));
  } else {
    const threeInstalled = fs.existsSync(path.join(appDir, 'node_modules', 'three'));
    const importmap = usesThree
      ? (threeInstalled ? THREE_IMPORTMAP : THREE_IMPORTMAP
        .replace(/\.\/node_modules\/three\/build\/three\.module\.js/, 'https://unpkg.com/three@0.170.0/build/three.module.js')
        .replace(/\.\/node_modules\/three\/examples\/jsm\//, 'https://unpkg.com/three@0.170.0/examples/jsm/'))
      : '';
    fs.writeFileSync(
      path.join(appDir, 'index.html'),
      INDEX_HTML(directives.project_name || 'App', importmap, './src/main.js'),
    );
    fs.writeFileSync(path.join(appDir, 'src', 'main.js'), usesThree ? THREE_MAIN : PLAIN_MAIN);
  }

  log.ok('scaffold', 'skeleton ready and loadable');
  return { usesThree, uses2D, fresh: true };
}
