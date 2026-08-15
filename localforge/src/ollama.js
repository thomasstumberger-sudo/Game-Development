/**
 * Ollama client.
 *
 * Three things matter for driving a local model hard for hours:
 *   1. Structured output. Small models freestyle JSON badly, so anywhere we need
 *      machine-readable output we hand Ollama a JSON schema via `format` and it
 *      constrains sampling to match. This removes an entire class of failure.
 *   2. Retries. A 12-hour run will hit transient socket errors; a crash there
 *      costs hours of work.
 *   3. keep_alive. Reloading 18GB of weights between every call would dominate
 *      the wall clock.
 */
import { config } from './config.js';
import { log } from './logger.js';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export class OllamaError extends Error {}

async function post(endpoint, body, { timeoutMs } = {}) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs ?? config.ollama.requestTimeoutMs);
  try {
    const res = await fetch(`${config.ollama.host}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctl.signal,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new OllamaError(`${endpoint} -> HTTP ${res.status}: ${text.slice(0, 500)}`);
    }
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

/** Rough token estimate. Only used for budgeting/trimming, not billing. */
export const estimateTokens = (text) => Math.ceil((text || '').length / 3.6);

/**
 * One chat completion.
 *
 * @param {object}   opts
 * @param {string}   opts.role      - key into config.models / contextTokens
 * @param {Array}    opts.messages  - Ollama chat messages
 * @param {Array}    [opts.tools]   - tool definitions (OpenAI-style function schema)
 * @param {object}   [opts.schema]  - JSON schema; forces structured output
 * @param {number}   [opts.temperature]
 * @param {string}   [opts.model]   - override the role's model
 */
export async function chat({ role = 'coder', messages, tools, schema, temperature, model, numCtx }) {
  const chosenModel = model || config.models[role] || config.models.coder;
  const body = {
    model: chosenModel,
    messages,
    stream: false,
    keep_alive: config.ollama.keepAlive,
    options: {
      temperature: temperature ?? config.temperature[role] ?? 0.3,
      num_ctx: numCtx ?? config.contextTokens[role] ?? 16384,
    },
  };
  if (tools?.length) body.tools = tools;
  if (schema) body.format = schema;

  let lastErr;
  for (let attempt = 1; attempt <= config.ollama.maxRetries; attempt++) {
    const started = Date.now();
    try {
      const json = await post('/api/chat', body);
      const secs = ((Date.now() - started) / 1000).toFixed(1);
      log.debug('ollama', `${chosenModel} ${secs}s in=${json.prompt_eval_count ?? '?'} out=${json.eval_count ?? '?'}`);
      return json.message ?? {};
    } catch (err) {
      lastErr = err;
      const aborted = err.name === 'AbortError';
      log.warn('ollama', `attempt ${attempt}/${config.ollama.maxRetries} failed on ${chosenModel}: ${aborted ? 'timeout' : err.message}`);
      if (attempt < config.ollama.maxRetries) await sleep(2000 * attempt);
    }
  }
  throw new OllamaError(`chat failed after ${config.ollama.maxRetries} attempts: ${lastErr?.message}`);
}

/**
 * Chat constrained to a JSON schema, returning the parsed object.
 * Falls back to brace-matching extraction if the model wraps output in prose.
 */
export async function chatJSON({ role, messages, schema, temperature, model, numCtx }) {
  const msg = await chat({ role, messages, schema, temperature, model, numCtx });
  const raw = (msg.content || '').trim();
  const parsed = extractJSON(raw);
  if (!parsed) throw new OllamaError(`model did not return parseable JSON: ${raw.slice(0, 400)}`);
  return parsed;
}

/** Pull the first balanced JSON object/array out of a blob of text. */
export function extractJSON(text) {
  if (!text) return null;
  try { return JSON.parse(text); } catch { /* keep digging */ }

  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/);
  if (fence) {
    try { return JSON.parse(fence[1].trim()); } catch { /* keep digging */ }
  }

  for (const [open, close] of [['{', '}'], ['[', ']']]) {
    const start = text.indexOf(open);
    if (start === -1) continue;
    let depth = 0, inStr = false, esc = false;
    for (let i = start; i < text.length; i++) {
      const ch = text[i];
      if (inStr) {
        if (esc) esc = false;
        else if (ch === '\\') esc = true;
        else if (ch === '"') inStr = false;
        continue;
      }
      if (ch === '"') inStr = true;
      else if (ch === open) depth++;
      else if (ch === close) {
        depth--;
        if (depth === 0) {
          try { return JSON.parse(text.slice(start, i + 1)); } catch { break; }
        }
      }
    }
  }
  return null;
}

/** Vision call: images are base64 strings (no data: prefix). */
export async function chatVision({ role = 'critic', system, prompt, images, schema, temperature }) {
  const messages = [];
  if (system) messages.push({ role: 'system', content: system });
  messages.push({ role: 'user', content: prompt, images });
  if (schema) {
    const msg = await chat({ role, messages, schema, temperature });
    const parsed = extractJSON(msg.content || '');
    if (!parsed) throw new OllamaError(`vision model returned unparseable JSON: ${(msg.content || '').slice(0, 300)}`);
    return parsed;
  }
  return chat({ role, messages, temperature });
}

export async function listModels() {
  const res = await fetch(`${config.ollama.host}/api/tags`);
  if (!res.ok) throw new OllamaError(`/api/tags -> HTTP ${res.status}`);
  const json = await res.json();
  return json.models ?? [];
}

export async function modelInfo(name) {
  return post('/api/show', { model: name });
}

/** Load a model into VRAM ahead of time so the first real call isn't slow. */
export async function warmUp(modelName) {
  try {
    await post('/api/chat', {
      model: modelName,
      messages: [{ role: 'user', content: 'ok' }],
      stream: false,
      keep_alive: config.ollama.keepAlive,
      options: { num_predict: 1 },
    }, { timeoutMs: 10 * 60 * 1000 });
    return true;
  } catch (err) {
    log.warn('ollama', `warm-up failed for ${modelName}: ${err.message}`);
    return false;
  }
}
