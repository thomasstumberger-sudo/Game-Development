/**
 * Console + file logging. Long autonomous runs are unwatchable in real time, so
 * everything also lands on disk as JSONL for later forensics.
 */
import fs from 'node:fs';
import path from 'node:path';

const C = {
  reset: '\x1b[0m', dim: '\x1b[2m', bold: '\x1b[1m',
  red: '\x1b[31m', green: '\x1b[32m', yellow: '\x1b[33m',
  blue: '\x1b[34m', magenta: '\x1b[35m', cyan: '\x1b[36m', grey: '\x1b[90m',
};

let logFile = null;
let quiet = false;

export function initLogger(logDir, { quiet: q = false } = {}) {
  quiet = q;
  if (logDir) {
    fs.mkdirSync(logDir, { recursive: true });
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    logFile = path.join(logDir, `run-${stamp}.jsonl`);
  }
}

function write(level, scope, msg, extra) {
  if (logFile) {
    try {
      fs.appendFileSync(logFile, JSON.stringify({
        t: new Date().toISOString(), level, scope, msg, ...extra,
      }) + '\n');
    } catch { /* logging must never crash the run */ }
  }
}

const ts = () => new Date().toTimeString().slice(0, 8);

function emit(color, level, scope, msg, extra = {}) {
  write(level, scope, msg, extra);
  if (quiet && level === 'debug') return;
  const tag = scope ? `${C.dim}[${scope}]${C.reset} ` : '';
  console.log(`${C.grey}${ts()}${C.reset} ${color}${level.toUpperCase().padEnd(5)}${C.reset} ${tag}${msg}`);
}

export const log = {
  info: (scope, msg, extra) => emit(C.cyan, 'info', scope, msg, extra),
  ok: (scope, msg, extra) => emit(C.green, 'ok', scope, msg, extra),
  warn: (scope, msg, extra) => emit(C.yellow, 'warn', scope, msg, extra),
  error: (scope, msg, extra) => emit(C.red, 'error', scope, msg, extra),
  debug: (scope, msg, extra) => emit(C.grey, 'debug', scope, msg, extra),
  step: (scope, msg, extra) => emit(C.magenta, 'step', scope, msg, extra),

  banner(title, lines = []) {
    const w = Math.max(title.length, ...lines.map((l) => l.length), 40) + 4;
    console.log(`\n${C.bold}${C.blue}╔${'═'.repeat(w)}╗${C.reset}`);
    console.log(`${C.bold}${C.blue}║${C.reset} ${C.bold}${title.padEnd(w - 2)}${C.reset} ${C.bold}${C.blue}║${C.reset}`);
    if (lines.length) {
      console.log(`${C.bold}${C.blue}╟${'─'.repeat(w)}╢${C.reset}`);
      for (const l of lines) console.log(`${C.bold}${C.blue}║${C.reset} ${l.padEnd(w - 2)} ${C.bold}${C.blue}║${C.reset}`);
    }
    console.log(`${C.bold}${C.blue}╚${'═'.repeat(w)}╝${C.reset}\n`);
    write('info', 'banner', title, { lines });
  },
};

export const colors = C;
