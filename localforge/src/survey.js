/**
 * A compact, factual description of the code that already exists.
 *
 * The planner used to decompose a goal with no idea what was on disk: its
 * whole input was the goal string and a template. Given a finished game and
 * the instruction "deepen and beautify it", it produced 26 cosmetic tasks —
 * screen shake, hit flash, damage numbers, trails, dust — and never once
 * touched gameplay, because it had never seen that the gameplay was already
 * there. Three hours went into juicing a renderer that did not need it.
 *
 * This is the cheapest possible fix: tell it what exists. Not the source (a
 * whole app blows the planner's context and buries the signal), but the shape
 * of it — files, sizes, load order, and the symbols each file defines. That is
 * enough to tell "there is no combat system" from "combat.js already exports
 * six functions".
 */
import fs from 'node:fs';
import path from 'node:path';

const SKIP = new Set(['node_modules', '.git', '.forge', '_stray']);

/** Total characters of digest we are willing to spend planner context on. */
const BUDGET = 6000;

/**
 * Top-level names a file defines.
 *
 * Deliberately regex, not a parser: this runs on trees that are mid-edit and
 * sometimes do not parse, and a survey that throws on a broken file is useless
 * exactly when it is most needed. Over-matching costs a few wasted tokens;
 * failing costs the whole digest.
 */
function declarations(source) {
  const names = new Set();
  const patterns = [
    /^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/gm,
    /^\s*(?:export\s+)?class\s+([A-Za-z_$][\w$]*)/gm,
    /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function|\(|[A-Za-z_$][\w$]*\s*=>)/gm,
    /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*[[{]/gm,
  ];
  for (const re of patterns) {
    for (const m of source.matchAll(re)) names.add(m[1]);
  }
  return [...names];
}

/** Script load order as the page actually declares it, which is not alphabetical. */
function scriptOrder(appDir) {
  const html = path.join(appDir, 'index.html');
  if (!fs.existsSync(html)) return [];
  const source = fs.readFileSync(html, 'utf8');
  return [...source.matchAll(/<script[^>]*\ssrc=["']([^"']+)["']/g)].map((m) => m[1]);
}

function walk(dir, prefix = '', out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith('.') || SKIP.has(entry.name)) continue;
    const rel = prefix ? `${prefix}/${entry.name}` : entry.name;
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, rel, out);
    else out.push({ rel, abs });
  }
  return out;
}

/**
 * Describe an app directory for the planner.
 *
 * @param {string} appDir
 * @returns {{empty: boolean, text: string, fileCount: number, lineCount: number}}
 */
export function surveyApp(appDir) {
  const files = walk(appDir).filter((f) => /\.(js|mjs|html|css)$/.test(f.rel));
  if (!files.length) {
    return { empty: true, text: 'The app directory is empty. This is a project from scratch.', fileCount: 0, lineCount: 0 };
  }

  const order = scriptOrder(appDir);
  const rank = (rel) => {
    const i = order.findIndex((s) => s.replace(/^\.?\//, '') === rel);
    return i === -1 ? order.length + 1 : i;
  };

  let lineCount = 0;
  const rows = [];
  for (const f of files.sort((a, b) => rank(a.rel) - rank(b.rel) || a.rel.localeCompare(b.rel))) {
    let source = '';
    try { source = fs.readFileSync(f.abs, 'utf8'); } catch { continue; }
    const lines = source.split('\n').length;
    lineCount += lines;
    if (!/\.(js|mjs)$/.test(f.rel)) {
      rows.push(`- ${f.rel} (${lines} lines)`);
      continue;
    }
    const names = declarations(source);
    // Cap per file: one enormous module must not crowd out every other file.
    const shown = names.slice(0, 18);
    const more = names.length > shown.length ? `, +${names.length - shown.length} more` : '';
    rows.push(`- ${f.rel} (${lines} lines) defines: ${shown.join(', ') || '(no top-level definitions found)'}${more}`);
  }

  let text = order.length
    ? `Script load order from index.html: ${order.join(' -> ')}\n\nFiles:\n`
    : 'Files:\n';
  for (const row of rows) {
    if (text.length + row.length > BUDGET) { text += `- ... ${rows.length - rows.indexOf(row)} more file(s) not listed\n`; break; }
    text += `${row}\n`;
  }

  return { empty: false, text: text.trimEnd(), fileCount: files.length, lineCount };
}
