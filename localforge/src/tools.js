/**
 * The toolbelt handed to worker agents.
 *
 * Design notes:
 *  - Every path is resolved and confined to the workspace. A local model will
 *    absolutely try to write to /etc if you let it phrase things badly.
 *  - Tool results are truncated hard. One `cat` of a 3MB bundle otherwise
 *    evicts the whole task context and the agent forgets what it was doing.
 *  - Errors come back as normal results, not exceptions. Agents recover from a
 *    readable error string; they cannot recover from a crashed process.
 */
import fs from 'node:fs';
import path from 'node:path';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { config } from './config.js';
import { log } from './logger.js';

const execFileAsync = promisify(execFile);

const truncate = (s, limit = config.budgets.toolOutputChars) => {
  const str = String(s ?? '');
  if (str.length <= limit) return str;
  const half = Math.floor(limit / 2);
  return `${str.slice(0, half)}\n\n... [${str.length - limit} chars elided] ...\n\n${str.slice(-half)}`;
};

export class Toolbelt {
  constructor({ workspace, appDir }) {
    this.workspace = path.resolve(workspace);
    this.appDir = path.resolve(appDir);
    this.filesTouched = new Set();
    this.commandLog = [];
  }

  /** Resolve a model-supplied path against the app dir, refusing escapes. */
  resolve(p) {
    if (!p || typeof p !== 'string') throw new Error('path is required');
    let cleaned = p.replace(/^\.\//, '').replace(/^\/+/, '');

    // Models are told "the app directory" and helpfully prefix it, producing
    // app/app/main.js. Strip a leading segment that just repeats the app dir's
    // own name, unless a real subdirectory of that name already exists.
    const appName = path.basename(this.appDir);
    if (cleaned.startsWith(`${appName}/`) && !fs.existsSync(path.join(this.appDir, appName))) {
      cleaned = cleaned.slice(appName.length + 1);
    }

    const abs = path.isAbsolute(p) ? path.resolve(p) : path.resolve(this.appDir, cleaned);
    if (!abs.startsWith(this.workspace)) {
      throw new Error(`path escapes the workspace sandbox: ${p}`);
    }
    return abs;
  }

  rel(abs) {
    return path.relative(this.appDir, abs) || path.basename(abs);
  }

  /**
   * Every JavaScript file the app actually ships, for the whole-app syntax
   * gate. Skips dependency and build directories, and the .bak/.backup/.orig
   * copies agents habitually leave behind — those are not loaded by the page,
   * and failing a round over a stale backup would stall the run for nothing.
   */
  allAppScripts() {
    const SKIP = new Set(['node_modules', '.git', '.forge', 'dist', 'build', 'vendor']);
    const out = [];
    const walk = (dir) => {
      let entries;
      try {
        entries = fs.readdirSync(dir, { withFileTypes: true });
      } catch {
        return;
      }
      for (const entry of entries) {
        if (entry.name.startsWith('.') || SKIP.has(entry.name)) continue;
        const abs = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(abs);
        else if (/\.(js|mjs)$/.test(entry.name)) out.push(abs);
      }
    };
    walk(this.appDir);
    return out;
  }

  // ---------------------------------------------------------------- file I/O

  async read_file({ path: p, offset, limit }) {
    const abs = this.resolve(p);
    if (!fs.existsSync(abs)) return { error: `no such file: ${p}` };
    if (fs.statSync(abs).isDirectory()) return { error: `${p} is a directory; use list_dir` };
    const lines = fs.readFileSync(abs, 'utf8').split('\n');
    const start = Math.max(0, (offset ?? 1) - 1);
    const end = limit ? start + limit : lines.length;
    const slice = lines.slice(start, end)
      .map((l, i) => `${String(start + i + 1).padStart(5)}  ${l}`)
      .join('\n');
    return {
      path: this.rel(abs),
      totalLines: lines.length,
      content: truncate(slice),
    };
  }

  async write_file({ path: p, content }) {
    const abs = this.resolve(p);
    if (typeof content !== 'string') return { error: 'content must be a string' };
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, content);
    this.filesTouched.add(this.rel(abs));
    log.debug('tool', `write_file ${this.rel(abs)} (${content.length} bytes)`);
    return { ok: true, path: this.rel(abs), bytes: content.length, lines: content.split('\n').length };
  }

  async edit_file({ path: p, old_string, new_string, replace_all }) {
    const abs = this.resolve(p);
    if (!fs.existsSync(abs)) return { error: `no such file: ${p}` };
    const before = fs.readFileSync(abs, 'utf8');
    if (typeof old_string !== 'string' || !old_string.length) {
      return { error: 'old_string is required and must be non-empty' };
    }
    const count = before.split(old_string).length - 1;
    if (count === 0) {
      return { error: `old_string not found in ${p}. Read the file again and copy the exact text, including whitespace.` };
    }
    if (count > 1 && !replace_all) {
      return { error: `old_string appears ${count} times in ${p}. Add more surrounding context to make it unique, or pass replace_all=true.` };
    }
    const after = replace_all ? before.split(old_string).join(new_string ?? '') : before.replace(old_string, new_string ?? '');
    fs.writeFileSync(abs, after);
    this.filesTouched.add(this.rel(abs));
    log.debug('tool', `edit_file ${this.rel(abs)} (${count} replacement${count > 1 ? 's' : ''})`);
    return { ok: true, path: this.rel(abs), replacements: replace_all ? count : 1 };
  }

  async list_dir({ path: p = '.' }) {
    const abs = this.resolve(p);
    if (!fs.existsSync(abs)) return { error: `no such directory: ${p}` };
    const entries = fs.readdirSync(abs, { withFileTypes: true })
      .filter((e) => !e.name.startsWith('.') && e.name !== 'node_modules')
      .map((e) => {
        const full = path.join(abs, e.name);
        const size = e.isFile() ? fs.statSync(full).size : null;
        return e.isDirectory() ? `${e.name}/` : `${e.name} (${size} bytes)`;
      });
    return { path: this.rel(abs) || '.', entries: truncate(entries.join('\n')) };
  }

  async search({ pattern, glob, path: p = '.' }) {
    const abs = this.resolve(p);
    const args = ['--line-number', '--no-heading', '--color=never', '--max-count=40', pattern];
    if (glob) args.push('--glob', glob);
    args.push(abs);
    try {
      const { stdout } = await execFileAsync('rg', args, { maxBuffer: 8 * 1024 * 1024 });
      return { matches: truncate(stdout.split('\n').map((l) => l.replace(`${this.appDir}/`, '')).join('\n')) };
    } catch (err) {
      if (err.code === 1) return { matches: '(no matches)' };
      // ripgrep missing: degrade to a JS walk rather than failing the task.
      return { matches: truncate(this.#fallbackSearch(abs, pattern, glob)) };
    }
  }

  #fallbackSearch(dir, pattern, glob) {
    const re = new RegExp(pattern);
    const out = [];
    const walk = (d) => {
      for (const e of fs.readdirSync(d, { withFileTypes: true })) {
        if (e.name.startsWith('.') || e.name === 'node_modules') continue;
        const full = path.join(d, e.name);
        if (e.isDirectory()) { walk(full); continue; }
        if (glob && !full.endsWith(glob.replace(/^\*/, ''))) continue;
        try {
          fs.readFileSync(full, 'utf8').split('\n').forEach((line, i) => {
            if (re.test(line)) out.push(`${path.relative(this.appDir, full)}:${i + 1}:${line.trim().slice(0, 200)}`);
          });
        } catch { /* binary file */ }
        if (out.length > 200) return;
      }
    };
    walk(dir);
    return out.join('\n') || '(no matches)';
  }

  // ------------------------------------------------------------------- shell

  async run_command({ command, timeout_ms }) {
    if (typeof command !== 'string' || !command.trim()) return { error: 'command is required' };
    for (const pattern of config.bannedCommandPatterns) {
      if (pattern.test(command)) {
        return { error: `command blocked by safety policy (matched ${pattern}). Choose a different approach.` };
      }
    }
    this.commandLog.push(command);
    log.debug('tool', `run_command: ${command.slice(0, 160)}`);
    try {
      const { stdout, stderr } = await execFileAsync('bash', ['-lc', command], {
        cwd: this.appDir,
        timeout: Math.min(timeout_ms ?? 120000, 600000),
        maxBuffer: 16 * 1024 * 1024,
        env: { ...process.env, NO_COLOR: '1', CI: '1' },
      });
      return { exitCode: 0, stdout: truncate(stdout), stderr: truncate(stderr) };
    } catch (err) {
      return {
        exitCode: err.code ?? 1,
        stdout: truncate(err.stdout ?? ''),
        stderr: truncate(err.stderr ?? err.message),
        timedOut: err.killed === true,
      };
    }
  }

  // ------------------------------------------------------------ verification

  /** Syntax-check every JS file the agent has touched. Fast, objective, cheap. */
  /**
   * Syntax-check JavaScript.
   *
   * `all: true` sweeps every .js in the app instead of only what this agent
   * touched. Touched-files-only has a hole big enough to lose a run through: a
   * file corrupted by a shell redirect, or left broken by the other worker in a
   * parallel pass, is not in this agent's filesTouched, so the round is graded
   * as if the module graph still loaded. The gate in worker.js uses `all`.
   */
  async check_syntax({ path: p, all = false } = {}) {
    const targets = p
      ? [this.resolve(p)]
      : all
        ? this.allAppScripts()
        : [...this.filesTouched].map((f) => this.resolve(f)).filter((f) => /\.(js|mjs)$/.test(f));
    if (!targets.length) return { ok: true, note: 'no JavaScript files to check' };
    const problems = [];
    for (const file of targets) {
      if (!fs.existsSync(file)) continue;
      try {
        await execFileAsync('node', ['--check', file], { timeout: 20000 });
      } catch (err) {
        problems.push(`${this.rel(file)}: ${(err.stderr || err.message).split('\n').slice(0, 4).join(' ')}`);
      }
    }
    return problems.length ? { ok: false, problems } : { ok: true, checked: targets.length };
  }
}

/**
 * Tool schemas advertised to the model. Descriptions are written for a 30B
 * model: blunt, imperative, and explicit about failure modes.
 */
export const TOOL_SCHEMAS = [
  {
    type: 'function',
    function: {
      name: 'read_file',
      description: 'Read a file from the project. ALWAYS read a file before editing it. Returns numbered lines.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path relative to the app directory, e.g. "src/weapons.js"' },
          offset: { type: 'integer', description: 'First line to read (1-based). Optional.' },
          limit: { type: 'integer', description: 'How many lines to read. Optional.' },
        },
        required: ['path'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'write_file',
      description: 'Create a new file or completely overwrite an existing one. Provide the ENTIRE file content, never a fragment or a placeholder comment.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'Path relative to the app directory' },
          content: { type: 'string', description: 'Complete file contents' },
        },
        required: ['path', 'content'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'edit_file',
      description: 'Replace an exact substring in an existing file. old_string must match the file byte-for-byte including indentation, and must be unique unless replace_all is true. Prefer this over write_file for small changes.',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string' },
          old_string: { type: 'string', description: 'Exact existing text to replace' },
          new_string: { type: 'string', description: 'Replacement text' },
          replace_all: { type: 'boolean', description: 'Replace every occurrence' },
        },
        required: ['path', 'old_string', 'new_string'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'list_dir',
      description: 'List files and folders at a path in the project.',
      parameters: {
        type: 'object',
        properties: { path: { type: 'string', description: 'Directory, defaults to the app root' } },
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'search',
      description: 'Regex search across project files. Use this to find where something is defined before changing it.',
      parameters: {
        type: 'object',
        properties: {
          pattern: { type: 'string', description: 'Regular expression' },
          glob: { type: 'string', description: 'Optional file filter, e.g. "*.js"' },
          path: { type: 'string', description: 'Optional subdirectory to search' },
        },
        required: ['pattern'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'run_command',
      description: 'Run a shell command in the app directory (npm install, node script.js, ls). Destructive commands are blocked.',
      parameters: {
        type: 'object',
        properties: {
          command: { type: 'string' },
          timeout_ms: { type: 'integer', description: 'Defaults to 120000' },
        },
        required: ['command'],
      },
    },
  },
  {
    type: 'function',
    function: {
      name: 'check_syntax',
      description: 'Syntax-check the JavaScript files you have edited. Run this before finishing.',
      parameters: { type: 'object', properties: { path: { type: 'string' } } },
    },
  },
  {
    type: 'function',
    function: {
      name: 'finish',
      description: 'Call this ONLY when the assigned task is fully implemented and syntax-checked. Summarise what you changed.',
      parameters: {
        type: 'object',
        properties: {
          summary: { type: 'string', description: 'What you built and which files you changed' },
        },
        required: ['summary'],
      },
    },
  },
];
