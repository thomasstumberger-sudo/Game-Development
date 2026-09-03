/**
 * Deterministic checks that run before the vision critic.
 *
 * The critic is the only thing that measures quality, and it almost never
 * runs: one 16h run verified 322 rounds and judged 17 of them, because a round
 * is only judged if the build is healthy and 95% of rounds were not. Adding
 * vision calls would not have helped. What starves the signal is that rounds
 * stay broken, and they stay broken because the repair brief can only describe
 * symptoms a browser can see — "the screen is blank" — while the actual
 * defects are structural and invisible to any screenshot.
 *
 * Every rule here comes from a defect that really shipped in this project:
 *
 *   orphan-symbol            a function written, exported, and never called by
 *                            anything. Recorded as the dominant failure mode:
 *                            movement.updateMove, state.endTurn and an entire
 *                            EncounterSystem were each built and left unwired,
 *                            and no gate noticed any of them.
 *   canvas-zero-guard        `if (canvas.width === 0)` never fires. A <canvas>
 *                            with no width/height attributes reports 300x150,
 *                            never 0, so the resize guard is dead and the game
 *                            renders into a corner box. Regenerated twice
 *                            after being fixed.
 *   per-frame-allocation     building an offscreen canvas inside a draw
 *                            function, every frame. This is what destroyed the
 *                            Wizard Wars build: drawTerrainTextures() made a
 *                            full-canvas sprite each frame and painted it over
 *                            the entire world.
 *   falsy-coordinate-guard   `if (!startQ)` is true at the origin, so the guard
 *                            silently kills everything at coordinate 0. Killed
 *                            all pathfinding in one run.
 *   no-resize-listener       nothing ever re-sizes the canvas.
 *
 * Findings are advisory by default and go into every repair brief. Only
 * findings a round *introduced* can fail it — see newFindings. An absolute
 * gate would stall forever on a seed that already trips a rule, which is the
 * same reason the interactivity check is relative rather than a health tier.
 */
import fs from 'node:fs';
import path from 'node:path';

const SKIP = new Set(['node_modules', '.git', '.forge', '_stray']);

/** Names that are referenced by the platform, not by our code. */
const PLATFORM = new Set([
  'main', 'init', 'setup', 'draw', 'update', 'preload', 'onload',
  'requestAnimationFrame', 'module', 'exports', 'window', 'document',
]);

/** Coordinate-ish identifiers where 0 is a legitimate value and `!x` is a bug. */
// Bare coordinate names, or a camelCase/underscore coordinate suffix. The
// suffix must sit on a real word boundary: an earlier version accepted any
// identifier ending in q/r/x/y, which flagged `gameOver` — a boolean, where
// `if (!gameOver)` is exactly right.
const COORD = /^(q|r|s|x|y|z|i|j|k|col|row|idx|index|dx|dy|dq|dr|tx|ty|gx|gy|cx|cy|nx|ny|px|py)$|[a-z][QRSXYZ]$|_[qrsxyz]$|(Index|Col|Row)$/;

function walk(dir, prefix = '', out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith('.') || SKIP.has(e.name)) continue;
    const rel = prefix ? `${prefix}/${e.name}` : e.name;
    const abs = path.join(dir, e.name);
    if (e.isDirectory()) walk(abs, rel, out);
    else out.push({ rel, abs });
  }
  return out;
}

/**
 * Blank a matched span while keeping its newlines, so every line number after
 * it still refers to the line the agent will actually open. Collapsing a block
 * comment to a single space silently shifts the rest of the file.
 */
const blank = (text) => text.replace(/[^\n]/g, ' ');

/** Strip comments. String literals are preserved. */
function decomment(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|[^:])\/\/[^\n]*/g, (m, p1) => p1 + blank(m.slice(p1.length)));
}

/**
 * Strip comments AND string bodies.
 *
 * Only for counting references: a name inside a comment or a string is not a
 * call. Rules that search FOR a literal — `addEventListener('resize')`,
 * `createElement('canvas')` — must use decomment instead, or they can never
 * match anything. Getting that backwards reported a correct resize listener as
 * missing.
 */
function deliteral(src) {
  return decomment(src)
    .replace(/`(?:\\.|[^`\\])*`/g, (m) => '`' + blank(m.slice(2)) + '`')
    .replace(/'(?:\\.|[^'\\\n])*'/g, (m) => "'" + ' '.repeat(Math.max(0, m.length - 2)) + "'")
    .replace(/"(?:\\.|[^"\\\n])*"/g, (m) => '"' + ' '.repeat(Math.max(0, m.length - 2)) + '"');
}

function lineOf(src, index) {
  return src.slice(0, index).split('\n').length;
}

/**
 * Body of the function starting at `open` (index of its `{`), by brace match.
 * Returns '' if the braces never balance, which happens on a tree mid-edit.
 */
function bodyAt(src, open) {
  let depth = 0;
  for (let i = open; i < src.length; i++) {
    if (src[i] === '{') depth++;
    else if (src[i] === '}') {
      depth--;
      if (depth === 0) return src.slice(open, i + 1);
    }
  }
  return '';
}

const DECL = [
  /(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/g,
  /(?:^|\n)\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)/g,
  /(?:^|\n)\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\(|[A-Za-z_$][\w$]*\s*=>)/g,
];

/**
 * Analyse an app directory.
 *
 * @param {string} appDir
 * @returns {{findings: Array<{rule:string, severity:string, file:string, line:number,
 *   symbol:string, message:string, fix:string, key:string}>}}
 */
export function analyzeApp(appDir) {
  const files = walk(appDir).filter((f) => /\.(js|mjs|html)$/.test(f.rel));
  const sources = new Map();
  for (const f of files) {
    try { sources.set(f.rel, fs.readFileSync(f.abs, 'utf8')); } catch { /* mid-edit */ }
  }
  // Two views of every file.
  //
  // `refs` is for counting references and has strings blanked. `lit` keeps
  // string contents and is what the literal-matching rules search.
  //
  // HTML is never stripped in either: attribute values are quoted strings, and
  // `onclick="fireSp()"` is frequently the ONLY reference to a handler. An
  // earlier version blanked those and reported every button handler in a
  // working game as dead code.
  const isJs = (k) => /\.(js|mjs)$/.test(k);
  const refs = new Map([...sources].map(([k, v]) => [k, isJs(k) ? deliteral(v) : v]));
  const lit = new Map([...sources].map(([k, v]) => [k, isJs(k) ? decomment(v) : v]));
  const findings = [];
  const add = (o) => findings.push({ ...o, key: `${o.rule}:${o.file}:${o.symbol || o.line}` });

  const js = [...refs].filter(([rel]) => isJs(rel));
  const jsLit = [...lit].filter(([rel]) => isJs(rel));

  // ---- orphan symbols ------------------------------------------------------
  const allText = [...refs.values()].join('\n');
  for (const [rel, src] of js) {
    for (const re of DECL) {
      re.lastIndex = 0;
      for (const m of src.matchAll(re)) {
        const name = m[1];
        if (PLATFORM.has(name) || name.length < 3) continue;
        const uses = (allText.match(new RegExp(`\\b${name}\\b`, 'g')) ?? []).length;
        // One occurrence is the declaration itself.
        if (uses <= 1) {
          add({
            rule: 'orphan-symbol',
            severity: 'major',
            file: rel,
            line: lineOf(src, src.indexOf(name, m.index)),
            symbol: name,
            message: `"${name}" is defined in ${rel} and never referenced anywhere — not by another module, not by an inline handler, not even by itself.`,
            fix: `Either call ${name} from the code that is supposed to use it, or delete it. A function nobody calls is a feature that does not exist, and no screenshot will ever show the difference.`,
          });
        }
      }
    }
  }

  // ---- canvas zero guard ---------------------------------------------------
  for (const [rel, src] of js) {
    for (const m of src.matchAll(/([A-Za-z_$][\w$.]*)\.(width|height)\s*===?\s*0\b/g)) {
      // Only when the receiver is plausibly the canvas element itself. A
      // getBoundingClientRect() result CAN legitimately be 0 wide — a hidden
      // element — so `rect.width === 0` is a correct check, not the dead
      // 300x150 guard, and flagging it would send agents to rewrite working
      // code.
      const recv = m[1].split('.').pop();
      if (!/canvas/i.test(recv) && !/^(c|cv|cnv)$/.test(recv)) continue;
      add({
        rule: 'canvas-zero-guard',
        severity: 'critical',
        file: rel,
        line: lineOf(src, m.index),
        symbol: `${m[1]}.${m[2]}`,
        message: `"${m[1]}.${m[2]} === 0" can never be true for a <canvas>. One with no width/height attributes reports 300x150, not 0, so this guard never fires and the canvas is never resized.`,
        fix: `Compare against the element's layout size instead: read getBoundingClientRect() (or clientWidth/clientHeight) and resize when the backing store does not match it.`,
      });
    }
  }

  // ---- per-frame allocation ------------------------------------------------
  const ALLOC = /(?:document\.createElement\s*\(\s*["']canvas["']\s*\)|\bmakeSprite\s*\(|new\s+OffscreenCanvas\b)/;
  for (const [rel, src] of jsLit) {
    for (const m of src.matchAll(/(?:^|\n)\s*(?:export\s+)?(?:async\s+)?function\s+((?:draw|render|paint|frame|tick|update|loop|step)[\w$]*)\s*\([^)]*\)\s*\{/gi)) {
      const open = src.indexOf('{', m.index + m[0].length - 1);
      const body = bodyAt(src, open);
      if (body && ALLOC.test(body)) {
        add({
          rule: 'per-frame-allocation',
          severity: 'major',
          file: rel,
          line: lineOf(src, m.index),
          symbol: m[1],
          message: `"${m[1]}" allocates an offscreen canvas on every call, and its name says it runs every frame.`,
          fix: `Build the sprite once at load and cache it in a module-level variable. Allocating a full-canvas bitmap per frame is what let one build paint an opaque rectangle over its entire game world at 60fps.`,
        });
      }
    }
  }

  // ---- falsy coordinate guards ---------------------------------------------
  for (const [rel, src] of js) {
    for (const m of src.matchAll(/if\s*\(\s*!\s*([A-Za-z_$][\w$]*)\s*[)&|]/g)) {
      const name = m[1];
      if (!COORD.test(name)) continue;
      add({
        rule: 'falsy-coordinate-guard',
        severity: 'critical',
        file: rel,
        line: lineOf(src, m.index),
        symbol: name,
        message: `"if (!${name})" treats 0 as missing. If ${name} is a coordinate or index, this branch fires at the origin and silently discards everything there.`,
        fix: `Test for absence explicitly: "if (${name} == null)" or "if (${name} === undefined)".`,
      });
    }
  }

  // ---- no resize listener --------------------------------------------------
  const setsSize = jsLit.some(([, src]) => /\.(width|height)\s*=\s*[^=]/.test(src));
  const listens = [...lit.values()].some((src) => /addEventListener\s*\(\s*["']resize["']|onresize\s*=/.test(src));
  if (setsSize && !listens) {
    add({
      rule: 'no-resize-listener',
      severity: 'minor',
      file: 'index.html',
      line: 1,
      symbol: 'resize',
      message: 'The canvas is sized in code but nothing listens for window resize.',
      fix: `Add a resize listener that re-reads the element's layout size and updates the backing store.`,
    });
  }

  return { findings };
}

/**
 * Findings present now that were not present before.
 *
 * The comparison is what makes this safe to gate on. A seed that already trips
 * a rule must not fail every round forever — that failure mode is why the
 * interactivity check is relative too.
 */
export function newFindings(before, after) {
  const seen = new Set((before ?? []).map((f) => f.key));
  return (after ?? []).filter((f) => !seen.has(f.key));
}

/**
 * Findings serious enough to fail a round on their own — but only when the
 * round introduced them (see newFindings).
 *
 * `major` blocks as well as `critical`, because both major rules describe a
 * task that has not actually been done: an orphaned symbol is a feature the
 * agent wrote and never connected, and a per-frame canvas allocation is what
 * painted over an entire game world at 60fps. Neither is visible to the
 * critic, so if these do not fail the round nothing else will.
 *
 * `minor` is advisory: it still reaches the repair brief, it just cannot
 * revert a round on its own.
 */
export function blocking(findings) {
  return (findings ?? []).filter((f) => f.severity === 'critical' || f.severity === 'major');
}

/** Repair-brief section. Ordered worst-first and capped, so it cannot bury the task. */
export function describeFindings(findings, { limit = 12 } = {}) {
  if (!findings?.length) return '';
  const rank = { critical: 0, major: 1, minor: 2 };
  const sorted = [...findings].sort((a, b) => rank[a.severity] - rank[b.severity]);
  const lines = ['## Structural defects found by static analysis',
    'These are invisible in a screenshot. Fix them first — the build cannot be judged on how it looks until it is wired correctly.'];
  for (const f of sorted.slice(0, limit)) {
    lines.push(`\n- **[${f.severity}] ${f.file}:${f.line}** — ${f.message}\n  Fix: ${f.fix}`);
  }
  if (sorted.length > limit) lines.push(`\n- ...and ${sorted.length - limit} more.`);
  return lines.join('\n');
}
