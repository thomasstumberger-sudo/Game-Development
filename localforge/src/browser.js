/**
 * Headless Chrome harness.
 *
 * This is the objective half of the quality gate. Before any model is asked for
 * an opinion, the app has to survive being actually run: no console errors, no
 * failed asset loads, a live WebGL context, and a measured frame rate. A model
 * cannot talk its way past this.
 */
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';
import { config } from './config.js';
import { log } from './logger.js';

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript',
  '.css': 'text/css', '.json': 'application/json', '.png': 'image/png',
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.svg': 'image/svg+xml', '.webp': 'image/webp', '.glb': 'model/gltf-binary',
  '.gltf': 'model/gltf+json', '.hdr': 'application/octet-stream',
  '.exr': 'application/octet-stream', '.bin': 'application/octet-stream',
  '.ktx2': 'application/octet-stream', '.wasm': 'application/wasm',
  '.mp3': 'audio/mpeg', '.ogg': 'audio/ogg', '.wav': 'audio/wav',
  '.ttf': 'font/ttf', '.woff2': 'font/woff2',
};

/** Static file server rooted at the app directory. */
export function startStaticServer(rootDir, port = config.browser.port) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      try {
        const urlPath = decodeURIComponent(new URL(req.url, 'http://localhost').pathname);
        let filePath = path.join(rootDir, urlPath);
        // Never serve outside the app root.
        if (!path.resolve(filePath).startsWith(path.resolve(rootDir))) {
          res.writeHead(403).end('forbidden');
          return;
        }
        if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
          filePath = path.join(filePath, 'index.html');
        }
        // Chrome requests /favicon.ico unprompted. Left as a 404 it shows up as
        // a console error and fails the verification gate on every single task.
        if (!fs.existsSync(filePath)) {
          if (urlPath === '/favicon.ico') { res.writeHead(204).end(); return; }
          res.writeHead(404).end('not found');
          return;
        }
        const ext = path.extname(filePath).toLowerCase();
        const headers = {
          'Content-Type': MIME[ext] || 'application/octet-stream',
          'Cache-Control': 'no-store',
        };
        // Cross-origin isolation unlocks SharedArrayBuffer, but it also blocks
        // plain CDN script tags, so it stays opt-in.
        if (process.env.FORGE_CROSS_ORIGIN_ISOLATED === '1') {
          headers['Cross-Origin-Opener-Policy'] = 'same-origin';
          headers['Cross-Origin-Embedder-Policy'] = 'require-corp';
        }
        res.writeHead(200, headers);
        fs.createReadStream(filePath).pipe(res);
      } catch (err) {
        res.writeHead(500).end(String(err));
      }
    });
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

let browserSingleton = null;

export async function getBrowser() {
  if (browserSingleton?.connected) return browserSingleton;
  browserSingleton = await puppeteer.launch({
    executablePath: config.browser.executablePath,
    headless: config.browser.headless ? 'shell' : false,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--enable-unsafe-swiftshader',
      // Force real GPU rasterisation so what we screenshot matches what a
      // player would see, rather than a software-rendered approximation.
      '--use-gl=angle',
      '--use-angle=gl',
      '--enable-gpu-rasterization',
      '--ignore-gpu-blocklist',
      '--enable-webgl',
      '--hide-scrollbars',
      '--mute-audio',
      `--window-size=${config.browser.width},${config.browser.height}`,
    ],
  });
  return browserSingleton;
}

export async function closeBrowser() {
  if (browserSingleton?.connected) {
    await browserSingleton.close().catch(() => {});
  }
  browserSingleton = null;
}

/**
 * Load the app and report on its health.
 *
 * @returns {Promise<{ok:boolean, screenshot:Buffer|null, consoleErrors:string[],
 *   pageErrors:string[], failedRequests:string[], fps:number|null,
 *   webgl:object|null, blankScreen:boolean, drawCalls:number|null}>}
 */
/**
 * Default interaction used to get past an entry screen.
 *
 * Games routinely gate themselves behind "click to start" / "press any key".
 * Without this, every screenshot after a title screen lands grades a title
 * card, and the critic scores the menu instead of the game.
 */
export const ENTRY_ACTIONS = [
  { type: 'click' },
  { type: 'wait', ms: 350 },
  { type: 'key', key: 'Space' },
  { type: 'keyup', key: 'Space' },
  { type: 'wait', ms: 250 },
  { type: 'key', key: 'Enter' },
  { type: 'keyup', key: 'Enter' },
  { type: 'wait', ms: 250 },
  { type: 'click' },
  { type: 'wait', ms: 900 },
];

export async function inspectApp({ url, shotPath, actions = [], settleMs, fpsSampleMs, bootShotPath }) {
  const browser = await getBrowser();
  const page = await browser.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];

  // Noise that says nothing about build quality. Left unfiltered, any one of
  // these permanently fails every task and the run never converges.
  const BENIGN = [
    /favicon\.ico/i,
    /Failed to load resource.*\bfavicon/i,
    /Download the React DevTools/i,
    /\[Violation\]/i,
    /WebGL.*deprecated.*extension/i,
  ];
  const benign = (s) => BENIGN.some((re) => re.test(s));

  page.on('console', (m) => {
    if (m.type() !== 'error') return;
    const text = m.text().slice(0, 500);
    // A bare "404" console line is only meaningful alongside the request that
    // caused it, so correlate with the failed-request list before counting it.
    if (benign(text)) return;
    if (/404/.test(text) && failedRequests.every((r) => benign(r))) return;
    consoleErrors.push(text);
  });
  page.on('pageerror', (e) => pageErrors.push(String(e.message ?? e).slice(0, 500)));
  page.on('requestfailed', (r) => {
    const line = `${r.url().slice(0, 200)} (${r.failure()?.errorText ?? 'failed'})`;
    if (!benign(line)) failedRequests.push(line);
  });

  const result = {
    ok: false, screenshot: null, consoleErrors, pageErrors, failedRequests,
    fps: null, webgl: null, blankScreen: false, loadError: null, drawCalls: null,
    bootScreenshot: null, entered: false, deadPlayfield: false, interactive: null,
    errorScreen: null,
  };

  try {
    await page.setViewport({
      width: config.browser.width,
      height: config.browser.height,
      deviceScaleFactor: 1,
    });

    await page.goto(url, { waitUntil: 'networkidle2', timeout: 60000 });
    await new Promise((r) => setTimeout(r, settleMs ?? config.browser.settleMs));

    // Two-shot capture. The boot frame is what proves the app loads; the frame
    // after the entry actions is what the critic should actually be judging.
    // Keeping both means a mis-click can never hide a load failure.
    if (actions.length) {
      const bootBuf = await page.screenshot({ type: 'png' }).catch(() => null);
      if (bootBuf) {
        result.bootScreenshot = Buffer.from(bootBuf);
        if (bootShotPath) {
          fs.mkdirSync(path.dirname(bootShotPath), { recursive: true });
          fs.writeFileSync(bootShotPath, result.bootScreenshot);
        }
      }
    }

    // Optional scripted interaction: lets the critic judge gameplay states,
    // not just the title screen.
    for (const act of actions) {
      try {
        if (act.type === 'key') await page.keyboard.down(act.key);
        if (act.type === 'keyup') await page.keyboard.up(act.key);
        if (act.type === 'click') await page.mouse.click(act.x ?? 800, act.y ?? 450);
        if (act.type === 'move') await page.mouse.move(act.x ?? 800, act.y ?? 450);
        if (act.type === 'wait') await new Promise((r) => setTimeout(r, act.ms ?? 500));
        if (act.type === 'eval') await page.evaluate(act.code);
      } catch (err) {
        log.debug('browser', `action ${act.type} failed: ${err.message}`);
      }
    }

    // Frame-rate sample. Runs in page context over a real animation window.
    result.fps = await page.evaluate(async (sampleMs) => {
      return await new Promise((resolve) => {
        let frames = 0;
        const start = performance.now();
        const tick = () => {
          frames++;
          if (performance.now() - start < sampleMs) requestAnimationFrame(tick);
          else resolve(Math.round((frames * 1000) / (performance.now() - start)));
        };
        requestAnimationFrame(tick);
      });
    }, fpsSampleMs ?? config.browser.fpsSampleMs).catch(() => null);

    // Canvas/context introspection. A 2D game has no WebGL context and that is
    // not a fault, so we report the context type rather than pass/fail.
    result.webgl = await page.evaluate(() => {
      const canvas = document.querySelector('canvas');
      if (!canvas) return null;
      // getContext returns the existing context if one was already created, so
      // asking for '2d' first is a safe way to detect a 2D game.
      let is2d = false;
      try { is2d = Boolean(canvas.getContext('2d')); } catch { is2d = false; }
      if (is2d) {
        return { present: true, type: '2d', width: canvas.width, height: canvas.height, contextLost: false };
      }
      const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
      if (!gl) return { present: false, type: 'none' };
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      return {
        present: true,
        type: 'webgl',
        version: gl.getParameter(gl.VERSION),
        renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'unknown',
        contextLost: gl.isContextLost(),
        width: canvas.width,
        height: canvas.height,
        // three.js exposes render stats on the renderer if the app parks it on window.
        drawCalls: window.renderer?.info?.render?.calls ?? null,
        triangles: window.renderer?.info?.render?.triangles ?? null,
      };
    }).catch(() => null);
    result.drawCalls = result.webgl?.drawCalls ?? null;

    const buf = await page.screenshot({ type: 'png' });
    result.screenshot = Buffer.from(buf);
    if (shotPath) {
      fs.mkdirSync(path.dirname(shotPath), { recursive: true });
      fs.writeFileSync(shotPath, result.screenshot);
    }

    // Did the entry actions actually change anything? If not, either there was
    // no gate or we failed to get past it — worth knowing before trusting the
    // score. Animated scenes differ frame to frame, so only a big delta counts.
    if (result.bootScreenshot) {
      const a = result.bootScreenshot, b = result.screenshot;
      const delta = Math.abs(a.length - b.length) / Math.max(a.length, b.length);
      result.entered = delta > 0.02 || !a.equals(b);
    }

    // Cheap "is it just a black rectangle" check, so a crashed renderer can't
    // sneak past a vision model that hallucinates detail into darkness.
    result.blankScreen = await isNearlyUniform(page);

    // A HUD is enough non-uniform pixel data to pass the whole-canvas blank
    // test while the play area behind it is empty. A twelve-hour run shipped
    // exactly that: textured resource bar, tribe roster, and a black void where
    // the map should have been. So check the middle of the frame separately.
    result.deadPlayfield = await isPlayfieldDead(page);

    // Does the thing respond to input at all? Screenshots cannot tell a
    // playable game from a still life, and a run once spent twelve hours
    // polishing a build whose click-to-move had been dead the whole time.
    result.interactive = await probeInteraction(page);

    // Is the app displaying its own crash handler? A build that wraps init in
    // try/catch and paints the exception on the canvas renders plenty of
    // non-uniform pixels, keeps requestAnimationFrame ticking at 60 fps, and
    // reports a live play area — an eight-hour run graded every task against
    // exactly that red card and never noticed.
    result.errorScreen = await detectErrorScreen(page, { consoleErrors, pageErrors });

    result.ok = pageErrors.length === 0
      && consoleErrors.length === 0
      && !result.blankScreen
      && !result.deadPlayfield
      && !result.errorScreen
      && Boolean(result.webgl?.present ?? true);
  } catch (err) {
    result.loadError = err.message;
  } finally {
    await page.close().catch(() => {});
  }
  return result;
}

/**
 * Detect a genuinely dead frame.
 *
 * The naive version (count distinct colours in a 64x36 downsample) produced
 * false positives on legitimate 2D scenes: a dark background with a small
 * sprite downsamples to one colour, and the task gets failed for "blank screen"
 * even though it rendered correctly.
 *
 * So we sample finer and use two signals together — a frame is only blank when
 * it has almost no colour variety AND almost no pixels deviate from the modal
 * colour. Real content trips at least one of those.
 */
/**
 * Is the middle of the frame empty?
 *
 * Samples only the central 60% of the canvas, which excludes the edges where
 * HUDs, toolbars and status bars live. A build whose chrome renders over a dead
 * play area passes `isNearlyUniform` and fails here — that is the whole point.
 */
async function isPlayfieldDead(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('canvas');
    if (!canvas || !canvas.width || !canvas.height) return false;
    try {
      const sx = canvas.width * 0.2;
      const sy = canvas.height * 0.2;
      const sw = canvas.width * 0.6;
      const sh = canvas.height * 0.6;

      const W = 96, H = 54;
      const off = document.createElement('canvas');
      off.width = W; off.height = H;
      const ctx = off.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(canvas, sx, sy, sw, sh, 0, 0, W, H);
      const { data } = ctx.getImageData(0, 0, W, H);

      const counts = new Map();
      const total = W * H;
      for (let i = 0; i < data.length; i += 4) {
        const key = `${data[i] >> 3},${data[i + 1] >> 3},${data[i + 2] >> 3}`;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      let modal = 0;
      for (const n of counts.values()) if (n > modal) modal = n;

      // Deliberately more forgiving than the full-frame test: a legitimate
      // scene can be sparse. Only a play area that is essentially one colour
      // counts as dead.
      return counts.size <= 3 && (total - modal) / total < 0.01;
    } catch {
      return false;
    }
  }).catch(() => false);
}

/**
 * Is the app showing a crash screen instead of running?
 *
 * The failure this exists for: init() throws, the app's own try/catch catches
 * it, paints "Game initialization failed: <message>" on the canvas, and stops.
 * Every other objective signal reads healthy — the frame is not uniform, the
 * play area is not one colour, rAF still runs so fps is 60 — and the vision
 * critic scores a screenshot of the error text somewhere in the teens without
 * ever reporting why.
 *
 * Two independent signals, either of which is conclusive on its own:
 *
 *   1. Text. An error overlay rendered into the DOM can simply be read. Canvas
 *      text cannot, so the console is read instead: a message matching the
 *      fatal-init vocabulary means the app told us it failed to start.
 *   2. Stillness. A crashed build stops animating. Two canvas samples ~400ms
 *      apart that are byte-identical mean nothing is being drawn any more.
 *
 * Requiring signal 1 keeps this quiet on legitimately static scenes (a paused
 * puzzle board, a title card), which is why stillness alone is never enough.
 *
 * @returns {Promise<string|null>} a short reason, or null when the app is fine
 */
async function detectErrorScreen(page, { consoleErrors = [], pageErrors = [] } = {}) {
  const FATAL = [
    /(initiali[sz]ation|init)\s+(failed|error)/i,
    /failed to (initiali[sz]e|start|boot|load the game)/i,
    /(game|app|engine)\s+(crashed|failed to start)/i,
    /fatal error/i,
    /uncaught (type|reference|syntax|range)error/i,
  ];
  const fatalLine = [...pageErrors, ...consoleErrors].find((line) => FATAL.some((re) => re.test(line)));

  // An error painted into the DOM is readable directly, and is conclusive on
  // its own — no stillness check needed, the words are right there.
  const domError = await page.evaluate((patterns) => {
    const res = patterns.map((p) => new RegExp(p.source, p.flags));
    const text = (document.body?.innerText ?? '').slice(0, 4000);
    const hit = res.find((re) => re.test(text));
    if (!hit) return null;
    return text.match(hit)[0].slice(0, 120);
  }, FATAL.map((re) => ({ source: re.source, flags: re.flags }))).catch(() => null);

  if (domError) return `crash text on page: "${domError}"`;
  if (!fatalLine) return null;

  // The app said it failed to start. Confirm it actually stopped drawing
  // before failing the gate — a recoverable startup complaint that the build
  // then renders past is not a crash screen.
  const still = await isCanvasStill(page);
  if (!still) return null;

  return `app reported a fatal error and stopped drawing: "${fatalLine.slice(0, 120)}"`;
}

/** Are two canvas samples ~400ms apart byte-identical? */
async function isCanvasStill(page) {
  const sample = () => page.evaluate(() => {
    const canvas = document.querySelector('canvas');
    if (!canvas || !canvas.width || !canvas.height) return null;
    try {
      const W = 64, H = 36;
      const off = document.createElement('canvas');
      off.width = W; off.height = H;
      const ctx = off.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(canvas, 0, 0, W, H);
      return [...ctx.getImageData(0, 0, W, H).data].join(',');
    } catch {
      return null;
    }
  }).catch(() => null);

  const a = await sample();
  if (a === null) return false;
  await new Promise((r) => setTimeout(r, 400));
  const b = await sample();
  return b !== null && a === b;
}

/**
 * Does the build respond to input?
 *
 * Compares how much the canvas changes on its own against how much it changes
 * after clicks. An idle baseline is essential: an animated scene differs frame
 * to frame regardless of input, so "the pixels changed" alone proves nothing.
 *
 * @returns {Promise<boolean|null>} null when it cannot be determined
 */
async function probeInteraction(page) {
  const fingerprint = () => page.evaluate(() => {
    const canvas = document.querySelector('canvas');
    if (!canvas || !canvas.width) return null;
    try {
      const W = 128, H = 72;
      const off = document.createElement('canvas');
      off.width = W; off.height = H;
      const ctx = off.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(canvas, 0, 0, W, H);
      const { data } = ctx.getImageData(0, 0, W, H);
      const out = [];
      for (let i = 0; i < data.length; i += 4) {
        out.push((data[i] + data[i + 1] + data[i + 2]) / 3);
      }
      return out;
    } catch {
      return null;
    }
  }).catch(() => null);

  /**
   * Fraction of sampled pixels that changed meaningfully.
   *
   * Mean absolute difference was the obvious metric and it is the wrong one: a
   * unit crossing a few hexes moves well under two luminance levels averaged
   * over the whole frame, so a genuinely responsive 2D game read as inert
   * unless a full-screen modal happened to open. Counting *how many* pixels
   * moved, rather than by how much on average, is what separates a local state
   * change from noise.
   */
  const diff = (a, b) => {
    if (!a || !b || a.length !== b.length) return 0;
    let changed = 0;
    for (let i = 0; i < a.length; i++) if (Math.abs(a[i] - b[i]) > 10) changed++;
    return changed / a.length;
  };

  /**
   * The most concentrated change anywhere in the frame.
   *
   * The frame-wide fraction is resolution-invariant and therefore hopeless for
   * small sprites: a 48px unit on a 1600x900 canvas is ~0.2% of the frame, so a
   * turn-based game whose click-to-move worked perfectly reported NOT
   * INTERACTIVE for an entire 5-hour run. A sprite moving is *locally* dramatic
   * even when it is globally invisible, so scan overlapping blocks and keep the
   * densest one. Same >10 luminance rule, so noise stays excluded.
   */
  const BLOCK = 8, STRIDE = 4, FP_W = 128, FP_H = 72;
  const localDiff = (a, b) => {
    if (!a || !b || a.length !== b.length) return 0;
    let best = 0;
    for (let by = 0; by + BLOCK <= FP_H; by += STRIDE) {
      for (let bx = 0; bx + BLOCK <= FP_W; bx += STRIDE) {
        let changed = 0;
        for (let y = by; y < by + BLOCK; y++) {
          for (let x = bx; x < bx + BLOCK; x++) {
            const i = y * FP_W + x;
            if (Math.abs(a[i] - b[i]) > 10) changed++;
          }
        }
        const frac = changed / (BLOCK * BLOCK);
        if (frac > best) best = frac;
      }
    }
    return best;
  };

  const pause = (ms) => new Promise((r) => setTimeout(r, ms));

  try {
    const box = await page.evaluate(() => {
      const c = document.querySelector('canvas');
      if (!c) return null;
      const r = c.getBoundingClientRect();
      return { x: r.left, y: r.top, w: r.width, h: r.height };
    });
    if (!box || box.w < 10 || box.h < 10) return null;

    // Idle baseline: how much does it move with nobody touching it?
    const idleA = await fingerprint();
    await pause(250);
    const idleB = await fingerprint();
    await pause(250);
    const idleC = await fingerprint();
    if (!idleA || !idleB || !idleC) return null;
    const idle = Math.max(diff(idleA, idleB), diff(idleB, idleC));
    const idleLocal = Math.max(localDiff(idleA, idleB), localDiff(idleB, idleC));

    const before = idleC;

    // Click a few places likely to hit something interactive: just off centre,
    // where a game normally puts the player, and two nearby offsets. The pause
    // after each click has to outlast a movement tween, or the probe samples
    // mid-animation and the click before it looks like it did nothing.
    const cx = box.x + box.w / 2;
    const cy = box.y + box.h / 2;
    for (const [dx, dy] of [[box.w * 0.08, box.h * 0.06], [-box.w * 0.09, box.h * 0.05], [0, -box.h * 0.09]]) {
      await page.mouse.move(cx + dx, cy + dy);
      await pause(100);
      await page.mouse.click(cx + dx, cy + dy);
      await pause(900);
    }
    await pause(400);

    const after = await fingerprint();
    const changed = diff(before, after);
    const changedLocal = localDiff(before, after);

    // Two ways to prove a response, both of which must beat the idle churn so
    // a busy animation cannot pass itself off as responsiveness:
    //   - frame-wide: a menu opens, the board redraws, the camera pans.
    //   - localized: a small sprite moves. Globally negligible, locally stark.
    const globalHit = changed > Math.max(idle * 2 + 0.004, 0.01);
    const localHit = changedLocal > Math.max(idleLocal * 2, 0.08);
    return globalHit || localHit;
  } catch {
    return null;
  }
}

async function isNearlyUniform(page) {
  return page.evaluate(() => {
    const canvas = document.querySelector('canvas');
    if (!canvas) return false;
    try {
      const W = 128, H = 72;
      const off = document.createElement('canvas');
      off.width = W; off.height = H;
      const ctx = off.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(canvas, 0, 0, W, H);
      const { data } = ctx.getImageData(0, 0, W, H);

      const counts = new Map();
      const total = W * H;
      for (let i = 0; i < data.length; i += 4) {
        // Quantise to 5 bits per channel: tolerant of gradients and dithering.
        const key = `${data[i] >> 3},${data[i + 1] >> 3},${data[i + 2] >> 3}`;
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }

      let modal = 0;
      for (const n of counts.values()) if (n > modal) modal = n;
      const deviating = (total - modal) / total;

      // Uniform enough to be dead only if BOTH signals agree.
      return counts.size <= 3 && deviating < 0.005;
    } catch {
      return false; // tainted or unreadable canvas: don't fail the build over it
    }
  }).catch(() => false);
}
