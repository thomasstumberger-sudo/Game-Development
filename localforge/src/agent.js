/**
 * The worker agent: a tool-calling ReAct loop.
 *
 * Everything here exists to compensate for a specific way local models fail:
 *
 *  - They emit tool calls as prose or fenced JSON instead of using the tools
 *    API  -> `salvageToolCall` parses those out.
 *  - They loop, re-reading the same file forever -> repetition detector nudges,
 *    then forces a stop.
 *  - They say "I've implemented it" without writing anything -> we refuse the
 *    finish call if no file was ever touched.
 *  - They blow the context window and start hallucinating -> we trim the middle
 *    of the transcript while pinning the system prompt and task statement.
 */
import { chat, estimateTokens } from './ollama.js';
import { TOOL_SCHEMAS } from './tools.js';
import { config } from './config.js';
import { log } from './logger.js';

export class Agent {
  constructor({ name, toolbelt, systemPrompt, role = 'coder', maxSteps, fileHints = [] }) {
    this.name = name;
    this.toolbelt = toolbelt;
    this.systemPrompt = systemPrompt;
    this.role = role;
    this.maxSteps = maxSteps ?? config.budgets.agentSteps;
    this.messages = [{ role: 'system', content: systemPrompt }];
    this.steps = 0;
    this.toolCallHistory = [];
    // Files the task said it would touch. Used to rescue a model that writes
    // code into the chat instead of calling write_file.
    this.fileHints = fileHints;
    this.proseStrikes = 0;
  }

  /**
   * Run until the agent calls finish(), exhausts its step budget, or stalls.
   * @returns {Promise<{status:string, summary:string, steps:number, filesTouched:string[]}>}
   */
  async run(task) {
    this.messages.push({ role: 'user', content: task });

    while (this.steps < this.maxSteps) {
      this.steps++;
      this.#trimContext();

      let msg;
      try {
        msg = await chat({
          role: this.role,
          messages: this.messages,
          tools: TOOL_SCHEMAS,
        });
      } catch (err) {
        log.error(this.name, `model call failed: ${err.message}`);
        return this.#result('model_error', `Model call failed: ${err.message}`);
      }

      let toolCalls = normaliseToolCalls(msg.tool_calls);
      let assistantContent = msg.content ?? '';
      let assistantToolCalls = msg.tool_calls;

      // Model answered in prose; try to recover a tool call from the text.
      if (!toolCalls.length && msg.content) {
        const salvaged = salvageToolCall(msg.content)
          // Writing the file into the chat is the single most common local-model
          // failure. If we can identify the target file, honour the intent
          // rather than burning a round arguing about protocol.
          || salvageCodeBlock(msg.content, this.fileHints);
        if (salvaged) {
          log.debug(this.name, `salvaged ${salvaged.name}(${salvaged.args?.path ?? ''}) from prose`);
          toolCalls = [salvaged];
          // Rewrite the turn as a proper tool call. Leaving the pasted file in
          // the transcript would both confuse the template and waste thousands
          // of tokens of context on content we already captured.
          assistantContent = '';
          assistantToolCalls = [{ function: { name: salvaged.name, arguments: salvaged.args } }];
        }
      }

      if (!toolCalls.length) {
        this.proseStrikes++;
        this.messages.push({ role: 'assistant', content: msg.content ?? '' });
        if (this.proseStrikes >= 3) {
          return this.#result('stalled', msg.content?.slice(0, 800) ?? 'agent stopped calling tools');
        }
        this.messages.push({ role: 'user', content: this.#proseNudge() });
        continue;
      }
      this.proseStrikes = 0;

      this.messages.push({ role: 'assistant', content: assistantContent, tool_calls: assistantToolCalls });

      for (const call of toolCalls) {
        if (call.name === 'finish') {
          const summary = call.args?.summary ?? 'task complete';
          if (!this.toolbelt.filesTouched.size) {
            // Claimed completion without producing anything.
            this.messages.push({
              role: 'tool',
              tool_name: 'finish',
              content: 'REJECTED: you called finish but have not created or edited a single file. '
                + 'Implement the task by calling write_file with the complete file content.',
            });
            log.warn(this.name, 'rejected empty finish');
            continue;
          }
          log.ok(this.name, `finished in ${this.steps} steps`);
          return this.#result('completed', summary);
        }

        const observation = await this.#invoke(call);
        // `tool_name` matters: several chat templates (qwen3-coder among them)
        // render tool results differently when the name is missing.
        this.messages.push({ role: 'tool', tool_name: call.name, content: observation });
      }

      if (this.#isRepeating()) {
        log.warn(this.name, 'repetition detected, forcing re-plan');
        this.messages.push({
          role: 'user',
          content: 'STOP. You have repeated the same tool call several times without progress. '
            + 'Do something different: either write the code that is missing, or call finish if it is done.',
        });
        this.toolCallHistory.length = 0;
      }
    }

    log.warn(this.name, `hit step budget (${this.maxSteps})`);
    return this.#result('budget_exhausted', `Ran out of steps after ${this.steps} tool calls.`);
  }

  async #invoke(call) {
    const fn = this.toolbelt[call.name];
    if (typeof fn !== 'function') {
      return JSON.stringify({ error: `unknown tool "${call.name}". Available: ${TOOL_SCHEMAS.map((t) => t.function.name).join(', ')}` });
    }
    this.toolCallHistory.push(`${call.name}:${JSON.stringify(call.args).slice(0, 120)}`);
    try {
      const out = await fn.call(this.toolbelt, call.args ?? {});
      return typeof out === 'string' ? out : JSON.stringify(out);
    } catch (err) {
      return JSON.stringify({ error: err.message });
    }
  }

  #result(status, summary) {
    return {
      status,
      summary,
      steps: this.steps,
      filesTouched: [...this.toolbelt.filesTouched],
    };
  }

  /** Escalating pressure to get back on the tool protocol. */
  #proseNudge() {
    const target = this.fileHints[0] ?? 'src/main.js';
    // Common tail behaviour: the work is done and the model narrates instead of
    // closing out. Point it at the exit rather than at write_file.
    if (this.toolbelt.filesTouched.size) {
      return 'Text replies are discarded. You have already written '
        + `${[...this.toolbelt.filesTouched].join(', ')}. If the task is complete, call check_syntax and then `
        + 'finish with a summary. If it is not complete, call write_file or edit_file now.';
    }
    if (this.proseStrikes === 1) {
      return 'Your reply was plain text, so it was discarded. Nothing you write in chat reaches the project. '
        + 'The ONLY way to change the code is a tool call. Call write_file or edit_file now.';
    }
    return 'You are still replying with text. Text is thrown away. Emit a tool call in exactly this shape, '
      + `with the complete file content in the "content" field:\n\n`
      + `{"name": "write_file", "arguments": {"path": "${target}", "content": "<the entire file>"}}\n\n`
      + 'Do it now. No explanation, no markdown, no commentary.';
  }

  #isRepeating() {
    const recent = this.toolCallHistory.slice(-4);
    return recent.length === 4 && new Set(recent).size === 1;
  }

  /**
   * Keep the transcript inside the context window by dropping the middle.
   * The system prompt and the original task statement are never dropped, and
   * neither are the most recent exchanges, which carry the live state.
   */
  #trimContext() {
    const limit = (config.contextTokens[this.role] ?? 32768) * 0.72;
    const total = () => this.messages.reduce((n, m) => n + estimateTokens(m.content) + 40, 0);
    if (total() < limit) return;

    const head = this.messages.slice(0, 2);       // system + original task
    let tail = this.messages.slice(2);
    let dropped = 0;
    while (tail.length > 8 && head.concat(tail).reduce((n, m) => n + estimateTokens(m.content) + 40, 0) > limit) {
      tail.shift();
      dropped++;
    }
    if (dropped) {
      this.messages = [
        ...head,
        { role: 'user', content: `[${dropped} earlier tool exchanges were dropped to save context. Files you have already touched: ${[...this.toolbelt.filesTouched].join(', ') || 'none'}. Re-read any file before editing it.]` },
        ...tail,
      ];
      log.debug(this.name, `trimmed ${dropped} messages from context`);
    }
  }
}

/** Ollama returns tool call args as an object; some builds return a JSON string. */
export function normaliseToolCalls(raw) {
  if (!Array.isArray(raw)) return [];
  return raw.map((c) => {
    const fn = c.function ?? c;
    let args = fn.arguments ?? fn.args ?? {};
    if (typeof args === 'string') {
      try { args = JSON.parse(args); } catch { args = { _raw: args }; }
    }
    return { name: fn.name, args };
  }).filter((c) => c.name);
}

/**
 * Rescue the most common local-model failure: the model writes the finished
 * file into the chat as a fenced code block instead of calling write_file.
 *
 * We only act when we can identify the target path with reasonable confidence,
 * from (in order) a path comment on the first line of the block, a filename
 * mentioned in the surrounding prose, or the task's own declared files.
 * Guessing wrong would overwrite the wrong file, so ambiguity means we decline
 * and let the nudge handle it.
 */
export function salvageCodeBlock(text, fileHints = []) {
  const block = text.match(/```(?:javascript|js|html|css|jsx|ts|typescript)?\s*\n([\s\S]*?)```/);
  if (!block) return null;
  const code = block[1];
  if (code.trim().length < 120) return null; // too short to be a real file

  const filePattern = /([\w./-]+\.(?:js|mjs|html|css|json|glsl|frag|vert))/;

  // 1. A path comment on the first line of the block.
  const firstLine = code.split('\n', 1)[0];
  const fromComment = firstLine.match(/^\s*(?:\/\/|\/\*|<!--|#)\s*([\w./-]+\.\w+)/);
  // 2. A filename named in the prose before the fence.
  const before = text.slice(0, block.index);
  const fromProse = before.match(new RegExp(`(?:file|create|write|update|in)\\s+\`?${filePattern.source}`, 'i'))
    ?? before.match(filePattern);
  // 3. The task's declared files, but only if there is exactly one candidate.
  const fromHints = fileHints.length === 1 ? fileHints[0] : null;

  const path = fromComment?.[1] ?? fromProse?.[1] ?? fromHints;
  if (!path) return null;

  return { name: 'write_file', args: { path, content: code } };
}

/**
 * Recover a tool call from a model that answered in prose. Handles the two
 * shapes small models produce most: a fenced JSON object with a tool name, and
 * an XML-ish <tool_call> block.
 */
export function salvageToolCall(text) {
  const known = new Set(TOOL_SCHEMAS.map((t) => t.function.name));

  const xml = text.match(/<tool_call>\s*([\s\S]*?)\s*<\/tool_call>/);
  const fence = text.match(/```(?:json|tool_call)?\s*([\s\S]*?)```/);
  for (const candidate of [xml?.[1], fence?.[1], text]) {
    if (!candidate) continue;
    let obj;
    try { obj = JSON.parse(candidate.trim()); } catch { continue; }
    const name = obj.name ?? obj.tool ?? obj.function?.name;
    if (name && known.has(name)) {
      let args = obj.arguments ?? obj.parameters ?? obj.args ?? obj.function?.arguments ?? {};
      if (typeof args === 'string') {
        try { args = JSON.parse(args); } catch { /* leave as-is */ }
      }
      return { name, args };
    }
  }
  return null;
}
