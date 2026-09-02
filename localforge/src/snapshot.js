/**
 * The round ratchet: keep a round only if it did not make the build worse.
 *
 * Before this existed the harness was a hill-climber with no fitness
 * comparison. A round that broke the tree left the breakage on disk, the next
 * round started from it, and the next task after that inherited it without
 * ever being told. Measured over one 16h run: 304 of 322 verified rounds were
 * broken, the vision critic therefore ran on only 17 of 334 rounds, and the
 * pass ended with four fewer completed tasks than it started with.
 *
 * The fix is the smallest thing that turns a random walk into a search: take a
 * copy before each round, score the result, and revert if the score dropped.
 *
 * The app is a dozen small text files, so an in-memory copy is cheaper and far
 * more reliable than shelling out to git in a directory the agents also write
 * to.
 */
import fs from 'node:fs';
import path from 'node:path';

/** Directories never worth snapshotting. */
const SKIP = new Set(['node_modules', '.git', '.forge']);

/**
 * Take a detached copy of every file under an app directory.
 * @param {string} appDir
 * @returns {{files: Map<string, Buffer>, takenAt: string}}
 */
export function captureApp(appDir) {
  const files = new Map();
  const walk = (dir, prefix = '') => {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.name.startsWith('.') || SKIP.has(entry.name)) continue;
      const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
      const abs = path.join(dir, entry.name);
      if (entry.isDirectory()) walk(abs, rel);
      // readFileSync returns a fresh Buffer, so the snapshot cannot be mutated
      // by whatever the next agent does to the file on disk.
      else files.set(rel, fs.readFileSync(abs));
    }
  };
  walk(appDir);
  return { files, takenAt: new Date().toISOString() };
}

/**
 * Put an app directory back exactly as it was when the snapshot was taken.
 *
 * Files created since the snapshot are deleted. That matters more than it
 * sounds: the agents' habit under pressure is to write `main-fixed.js` beside
 * a file they could not repair, and leaving those behind would let a reverted
 * round still poison the module graph.
 *
 * @param {string} appDir
 * @param {{files: Map<string, Buffer>}} snap
 * @returns {{restored: number, removed: number}}
 */
export function restoreApp(appDir, snap) {
  if (!snap?.files) throw new Error('restoreApp called without a snapshot');

  const current = captureApp(appDir);
  let removed = 0;
  for (const rel of current.files.keys()) {
    if (!snap.files.has(rel)) {
      fs.rmSync(path.join(appDir, rel), { force: true });
      removed++;
    }
  }

  let restored = 0;
  for (const [rel, buf] of snap.files) {
    const abs = path.join(appDir, rel);
    // Only write what actually differs, so mtimes stay meaningful for anything
    // watching the tree.
    if (fs.existsSync(abs) && fs.readFileSync(abs).equals(buf)) continue;
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, buf);
    restored++;
  }

  pruneEmptyDirs(appDir);
  return { restored, removed };
}

function pruneEmptyDirs(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!entry.isDirectory() || entry.name.startsWith('.') || SKIP.has(entry.name)) continue;
    const abs = path.join(dir, entry.name);
    pruneEmptyDirs(abs);
    if (fs.readdirSync(abs).length === 0) fs.rmdirSync(abs);
  }
}

/**
 * Health tiers, worst to best. The gap between tiers is wider than the whole
 * critic range, which encodes the rule that broke the old runs: no amount of
 * art-direction score can outrank a build that does not work.
 */
const TIER = {
  // Distinct values, not just distinct names: describeFitness resolves a tier
  // back to its label by value, so sharing one would mislabel it in the log.
  syntaxError: 0,
  loadError: 1,
  errorScreen: 2,
  pageErrors: 3,
  consoleErrors: 4,
  blankScreen: 5,
  deadPlayfield: 6,
  healthy: 7,
};

/**
 * Score a round's result so two rounds can be compared.
 *
 * Higher is better. The value is `tier * 1000` plus the critic score, so
 * ordering is health first, art second, always.
 *
 * @param {object|null} health   result of inspectApp, or a syntax-failure stub
 * @param {{score:number}|null} critique  vision critic result, if one ran
 * @returns {number}
 */
export function fitness(health, critique) {
  if (!health) return TIER.loadError * 1000;

  let tier;
  if (health.syntaxError) tier = TIER.syntaxError;
  else if (health.loadError) tier = TIER.loadError;
  else if (health.errorScreen) tier = TIER.errorScreen;
  else if (health.pageErrors?.length) tier = TIER.pageErrors;
  else if (health.consoleErrors?.length) tier = TIER.consoleErrors;
  else if (health.blankScreen) tier = TIER.blankScreen;
  else if (health.deadPlayfield) tier = TIER.deadPlayfield;
  else tier = TIER.healthy;

  // An unjudged round scores 0 on art, so it can never beat a judged one at the
  // same health tier. It still beats every lower tier, which is what lets a
  // clean-but-unscored round replace a broken one.
  const art = typeof critique?.score === 'number' ? critique.score : 0;
  return tier * 1000 + art;
}

/**
 * The floor for keeping a task's work at all: the tree parses, loads, and
 * throws nothing uncaught. Below this the round produced a corpse and the task
 * is recorded as failed rather than "accepted below the bar".
 */
export const SALVAGEABLE_FITNESS = TIER.consoleErrors * 1000;

/** Human-readable form of a fitness value, for the round log. */
export function describeFitness(value) {
  const tier = Math.floor(value / 1000);
  const art = value % 1000;
  const name = Object.entries(TIER).find(([, v]) => v === tier)?.[0] ?? 'unknown';
  const label = name === 'healthy' ? 'clean' : name;
  return art ? `${label} @ ${art}/100` : label;
}
