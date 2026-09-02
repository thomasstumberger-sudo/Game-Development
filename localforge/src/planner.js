/**
 * Turns one enormous ambition ("build Call of Duty, make it perfect") into a
 * dependency-ordered graph of tasks small enough that a 30B model can actually
 * finish each one.
 *
 * The single most important constraint here: every task must be completable by
 * one agent, in one context window, touching a handful of files. Ambitious
 * prompts fail locally not because the model is dumb but because nobody split
 * the work small enough.
 */
import { chatJSON } from './ollama.js';
import { log } from './logger.js';
import { DOMAIN_KEYS, detectDomain, getRubric, assetGuidance } from './rubrics.js';
import { surveyApp } from './survey.js';

/** Schema for the directives we lift out of the user's phrasing. */
const DIRECTIVE_SCHEMA = {
  type: 'object',
  properties: {
    project_name: { type: 'string' },
    one_line_goal: { type: 'string' },
    stack: { type: 'string', description: 'e.g. "three.js", "vanilla canvas 2d", "react"' },
    visual_domain: {
      type: 'string',
      enum: DOMAIN_KEYS,
      description: 'How the result should be judged visually. "2d_game" for sprite/tile games (RPG, puzzle, '
        + 'adventure, action, strategy). "2_5d" for isometric or parallax-layered games. "3d_realtime" ONLY for '
        + 'true 3D with a camera in a 3D world. "ui_app" for interfaces, dashboards and tools.',
    },
    quality_bar: { type: 'string', description: 'What "done" looks like, in the user\'s own terms' },
    reference_targets: {
      type: 'array',
      items: { type: 'string' },
      description: 'Named products the result is being compared against',
    },
    fan_out: { type: 'boolean', description: 'User asked for parallel sub-agents' },
    loop_until_perfect: { type: 'boolean', description: 'User asked to loop/iterate until quality is met' },
    blind_compare: { type: 'boolean', description: 'User asked for blind side-by-side comparison against references' },
    harsh_critic: { type: 'boolean', description: 'User asked for a harsh/adversarial reviewer' },
    visual_priority: { type: 'boolean', description: 'Visual fidelity is a primary success criterion' },
  },
  required: ['project_name', 'one_line_goal', 'stack', 'visual_domain', 'quality_bar', 'fan_out',
    'loop_until_perfect', 'blind_compare', 'harsh_critic', 'visual_priority'],
};

const PLAN_SCHEMA = {
  type: 'object',
  properties: {
    architecture: {
      type: 'string',
      minLength: 120,
      description: 'Two or three full sentences on how the app is structured: the module breakdown, '
        + 'what owns state, and how the pieces talk to each other. This is handed to every coder agent '
        + 'as their map of the project. NOT the stack name — "vanilla canvas" is a useless answer.',
    },
    tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'kebab-case unique id, e.g. "weapon-recoil"' },
          title: { type: 'string' },
          description: {
            type: 'string',
            description: 'Precise implementation brief: what to build, which files, which techniques',
          },
          category: {
            type: 'string',
            enum: ['foundation', 'rendering', 'gameplay', 'physics', 'audio', 'ui', 'content', 'performance', 'polish'],
          },
          files: { type: 'array', items: { type: 'string' }, description: 'Files this task will create or edit' },
          depends_on: { type: 'array', items: { type: 'string' }, description: 'ids of tasks that must finish first' },
          acceptance_criteria: {
            type: 'array',
            items: { type: 'string' },
            description: 'Concrete, checkable statements. Avoid vague words like "good".',
          },
          visual: { type: 'boolean', description: 'True if the result is judged by looking at a screenshot' },
        },
        required: ['id', 'title', 'description', 'category', 'files', 'depends_on', 'acceptance_criteria', 'visual'],
      },
    },
  },
  required: ['architecture', 'tasks'],
};

const GAP_SCHEMA = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['ship', 'more_work'] },
    reasoning: { type: 'string' },
    new_tasks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          title: { type: 'string' },
          description: { type: 'string' },
          category: { type: 'string' },
          files: { type: 'array', items: { type: 'string' } },
          depends_on: { type: 'array', items: { type: 'string' } },
          acceptance_criteria: { type: 'array', items: { type: 'string' } },
          visual: { type: 'boolean' },
        },
        required: ['id', 'title', 'description', 'category', 'acceptance_criteria', 'visual'],
      },
    },
  },
  required: ['verdict', 'reasoning', 'new_tasks'],
};

export async function parseDirectives(goal) {
  log.step('planner', 'reading intent and directives from the prompt');
  const directives = await chatJSON({
    role: 'planner',
    schema: DIRECTIVE_SCHEMA,
    temperature: 0.1,
    messages: [
      {
        role: 'system',
        content: 'You extract build directives from a user request. The user may use shorthand from agentic '
          + 'coding tools: "fan out sub-agents" means parallel workers, "/loop" means iterate until a quality '
          + 'bar is met, "ultracode" means maximum effort, "blind side by side" means compare screenshots '
          + 'against reference images without knowing which is which. Report exactly what was asked for. '
          + 'Respond with JSON only.',
      },
      { role: 'user', content: goal },
    ],
  });

  // Never let a mislabelled domain through: it decides both the scaffold and
  // the entire critique rubric. Keyword detection on the raw prompt is a more
  // reliable tiebreaker than the model's own guess when the two disagree.
  const detected = detectDomain(goal);
  if (!DOMAIN_KEYS.includes(directives.visual_domain)) {
    directives.visual_domain = detected;
  } else if (directives.visual_domain === '3d_realtime' && detected !== '3d_realtime') {
    log.warn('planner', `model said 3d_realtime but the prompt reads as ${detected}; using ${detected}`);
    directives.visual_domain = detected;
  }

  log.ok('planner', `intent: ${directives.one_line_goal} [stack: ${directives.stack}, judged as: ${directives.visual_domain}]`);
  return directives;
}

const PLANNER_SYSTEM = `You are the lead architect of an autonomous build system. You break an ambitious software goal into a sequence of tasks that will be executed by separate AI agents working in parallel.

Hard rules for the tasks you emit:
1. Each task must be finishable by one agent editing at most 3 files. If a task feels big, split it.
2. Tasks must be ordered by dependency. The first tasks establish the runnable skeleton: an index.html that loads, a main entry module, a render loop. NOTHING can be verified until something runs in a browser.
3. Every task must name the concrete files it creates or edits.
4. Acceptance criteria must be checkable by looking at a screenshot or reading the code. "Looks great" is banned. "Muzzle flash light illuminates nearby surfaces for 60ms and casts a visible dynamic shadow" is correct.
5. Mark visual=true only when a screenshot could reveal whether it worked.
6. Prefer procedural/generated assets over downloading files. The agents have no asset store and no internet asset budget; art and audio must be generated in code unless a library provides them.
7. Assume the stack the user asked for. Load third-party libraries from a CDN via an import map or bundled npm install.

Emit 12 to 26 tasks. Front-load the ones that make the app runnable and visible. Respond with JSON only.`;

/** Domain-specific planning guidance, so a 2D game never gets 3D tasks. */
function domainPlanningNotes(domain) {
  switch (domain) {
    case '2d_game':
      return `This is a 2D sprite/tile game. Plan tasks accordingly:
- Use a 2D canvas context (or a 2D library). Do NOT plan any three.js, WebGL, lighting, shadow, PBR material or post-processing tasks.
- Early tasks must cover: a fixed-timestep game loop, a camera/viewport with scrolling, a tilemap renderer with a real tileset, a sprite/animation system, and input.
- Art tasks mean drawing sprites and tiles procedurally to offscreen canvases: a deliberate limited palette, tile variation, transition tiles between terrain types, and multi-frame animations.
- Include tasks for game feel: hit/impact feedback, particles, screen shake, transitions.`;
    case '2_5d':
      return `This is a 2.5D / isometric game. Plan tasks accordingly:
- Faked depth in 2D, not real 3D. Do NOT plan three.js, WebGL or PBR material tasks.
- Early tasks must cover: a fixed-timestep loop, an isometric or layered coordinate system with correct depth sorting, a camera, and a tile/prop renderer.
- Art tasks must keep one consistent projection angle and one light direction, and must give every sprite a contact shadow.
- Include parallax background layers and height/elevation variation.`;
    case '3d_realtime':
      return `This is a real-time 3D scene. Plan renderer, lighting, material, geometry and post-processing tasks. Textures must be generated procedurally onto a canvas and used as textures.`;
    default:
      return `This is an interface/application, not a game. Plan layout, component, state, typography and interaction tasks. Do NOT plan game loops, sprites or rendering tasks.`;
  }
}

/**
 * Is this text just the stack description handed back to us?
 *
 * Compared on word overlap rather than equality: the model paraphrases, pads
 * and reflows, so a substring test misses almost every real case.
 */
/**
 * Does this read as written prose, or as a model that came off the rails?
 *
 * A live re-plan returned
 * `task_graph_v1.0.0_2024-05-21T...jsonld.jsonld.jsonld.jsonld` as the
 * architecture: 120 characters, so the length check passed it, and not an echo
 * of anything, so the echo check passed it too. It would have gone to every
 * coder agent as their map of the project. Degenerate output is long and
 * confident and has almost no spaces in it.
 */
export function looksLikeProse(text) {
  const t = String(text ?? '').trim();
  if (t.length < 80) return false;
  const words = t.split(/\s+/);
  if (words.length < 15) return false;
  // A repetition loop stacks one enormous token; real prose does not.
  const longest = Math.max(...words.map((w) => w.length));
  if (longest > 45) return false;
  // Sentences, not identifiers.
  if (!/[a-z]\s+[a-z]/i.test(t)) return false;
  // Padding out the length with filler clears every check above while saying
  // nothing. Real prose averages four to five characters a word.
  const mean = words.reduce((a, w) => a + w.length, 0) / words.length;
  if (mean < 3) return false;
  return true;
}

/**
 * Does this architecture description actually describe THIS project?
 *
 * Both models tried so far answer the question with a title. qwen3-coder
 * returned a repetition loop; qwen3:32b returned "Wizard Wars Deepening &
 * Beautification Plan (12 tasks, 1200ms total estimate...)" — grammatical,
 * confident, prose by every earlier test, and containing not one fact about
 * how the code is organised.
 *
 * A real description of an existing project names its modules. If the survey
 * found files and symbols and the description mentions none of them, it is
 * about nothing.
 *
 * @param {string} text
 * @param {{empty:boolean, text:string}} survey
 */
export function mentionsProject(text, survey) {
  if (!survey || survey.empty) return true; // nothing to ground against
  const known = new Set();
  for (const m of survey.text.matchAll(/^- (\S+?)(?:\.[a-z]+)? \(/gm)) {
    known.add(m[1].split('/').pop().toLowerCase());
  }
  for (const m of survey.text.matchAll(/defines: ([^\n]+)/g)) {
    for (const raw of m[1].split(',')) {
      const name = raw.trim().replace(/,.*$/, '');
      if (/^[A-Za-z_$][\w$]*$/.test(name) && name.length > 3) known.add(name.toLowerCase());
    }
  }
  if (known.size < 2) return true;
  const words = new Set(String(text).toLowerCase().match(/[a-z_$][\w$]*/g) ?? []);
  let hits = 0;
  for (const k of known) if (words.has(k)) hits++;
  return hits >= 2;
}

export function isEchoOf(text, stack) {
  if (!stack) return false;
  const words = (t) => new Set(String(t).toLowerCase().match(/[a-z0-9]+/g) ?? []);
  const a = words(text);
  const b = words(stack);
  if (!b.size || !a.size) return false;
  let shared = 0;
  for (const w of a) if (b.has(w)) shared++;
  return shared / a.size > 0.7;
}

/** Rough classifier for the plan-balance warning. Advisory only, never a filter. */
export function looksCosmetic(task) {
  return /\b(shake|flash|particle|trail|glow|dust|debris|juice|polish|palette|shading|lighting|silhouette|animation|anim|parallax|strata|screen[- ]?space|damage numbers?|vfx|sfx|sound|audio)\b/i
    .test(`${task.id} ${task.title} ${task.description ?? ''}`);
}

export async function planProject(goal, directives, { appDir = null } = {}) {
  log.step('planner', 'decomposing the goal into a task graph');

  // What already exists, in the planner's own context.
  //
  // Without this the planner decomposes the goal in a vacuum. Handed a
  // finished artillery game and told to "deepen and beautify" it, it planned
  // 26 juice tasks and no gameplay, because nothing in its input said the
  // gameplay was already written.
  const survey = appDir ? surveyApp(appDir) : { empty: true, text: '', fileCount: 0, lineCount: 0 };
  if (!survey.empty) {
    log.info('planner', `surveyed ${survey.fileCount} existing file(s), ${survey.lineCount} lines`);
  }
  const existingBlock = survey.empty
    ? 'EXISTING CODE: none. This is a new project.\n'
    : `EXISTING CODE — this project is ALREADY BUILT to the state below. Read it before planning.\n`
      + `${survey.text}\n\n`
      + `PLAN AGAINST WHAT IS THERE:\n`
      + `- Do NOT plan a task for something these files already define. Check the symbol lists above first.\n`
      + `- Prefer tasks that deepen or connect existing systems over tasks that add new decoration.\n`
      + `- If the goal is already largely met, plan FEWER, larger tasks rather than padding the graph with cosmetic effects.\n`
      + `- AT LEAST HALF the tasks must change what the game DOES — mechanics, rules, systems, opponent\n`
      + `  behaviour, match flow, failure states. The rest may change how it looks.\n`
      + `- A graph made mostly of screen shake, hit flashes, damage numbers, particle trails, dust and\n`
      + `  lighting is a failed plan, however well the goal is phrased. Those are finishing touches on\n`
      + `  systems that must exist first.\n`;

  const plan = await chatJSON({
    role: 'planner',
    schema: PLAN_SCHEMA,
    messages: [
      { role: 'system', content: PLANNER_SYSTEM },
      {
        role: 'user',
        content: `GOAL:\n${goal}\n\n`
          + `${existingBlock}\n`
          + `PROJECT: ${directives.project_name}\n`
          + `STACK: ${directives.stack}\n`
          + `QUALITY BAR: ${directives.quality_bar}\n`
          + `REFERENCE TARGETS: ${(directives.reference_targets ?? []).join(', ') || 'none given'}\n\n`
          + `${domainPlanningNotes(directives.visual_domain)}\n\n`
          + `ASSET POLICY: ${assetGuidance(directives.visual_domain)}\n\n`
          + 'Produce the task graph.',
      },
    ],
  });

  const tasks = sanitiseTasks(plan.tasks ?? []);
  log.ok('planner', `planned ${tasks.length} tasks (${tasks.filter((t) => t.visual).length} visually judged)`);

  // A one-word "architecture" (the model echoing the stack name) is worse than
  // nothing: it fills the coder's map-of-the-project slot with noise.
  let architecture = (plan.architecture ?? '').trim();
  if (architecture.length < 80) {
    log.warn('planner', `architecture came back as "${architecture}" — too thin to be useful, dropping it`);
    architecture = '';
  }

  // The length check above is not enough. Asked to describe the architecture,
  // the model will happily paste the stack description back — it is long, it
  // is on-topic, and it says nothing about how the code is organised. Every
  // coder agent then gets that as its map of the project.
  if (architecture && isEchoOf(architecture, directives.stack)) {
    log.warn('planner', 'architecture is just the stack description echoed back — dropping it');
    architecture = '';
  }
  if (architecture && !looksLikeProse(architecture)) {
    log.warn('planner', `architecture is not prose ("${architecture.slice(0, 60)}...") — dropping it`);
    architecture = '';
  }
  if (architecture && !mentionsProject(architecture, survey)) {
    log.warn('planner', 'architecture names none of this project\'s modules — dropping it');
    architecture = '';
  }

  // Whatever the model produced, append what is actually on disk. The survey
  // is measured rather than described, so it cannot be wrong, and a coder that
  // knows the load order and the symbol table does not have to spend a third
  // of its steps grepping for them.
  if (!survey.empty) {
    architecture = [architecture, `CURRENT FILE MAP (measured, authoritative):\n${survey.text}`]
      .filter(Boolean).join('\n\n');
  }

  // Say plainly how the plan is balanced. A run that spends its whole budget
  // on polish should be visible at planning time, not inferred afterwards from
  // a log full of juice tasks.
  const cosmetic = tasks.filter((t) => looksCosmetic(t)).length;
  const share = tasks.length ? Math.round((100 * cosmetic) / tasks.length) : 0;
  const line = `plan balance: ${tasks.length - cosmetic} behavioural, ${cosmetic} cosmetic (${share}%)`;
  if (share > 60) log.warn('planner', `${line} — this graph is mostly polish`);
  else log.info('planner', line);

  return { architecture, tasks };
}

/**
 * After a full pass, look at what exists and decide whether to keep going.
 * This is the outer /loop: the planner itself gets to say "not good enough".
 */
export async function gapAnalysis({ goal, directives, tasks, critiques, fileList, round }) {
  log.step('planner', `gap analysis, round ${round}`);
  const summary = tasks.map((t) => `- [${t.status}] ${t.id}: ${t.title}${t.lastScore != null ? ` (visual score ${t.lastScore})` : ''}`).join('\n');
  const issues = critiques.slice(-14).map((c) => `- ${c.taskId}: ${c.issues?.slice(0, 3).join('; ')}`).join('\n');

  const res = await chatJSON({
    role: 'planner',
    schema: GAP_SCHEMA,
    messages: [
      {
        role: 'system',
        content: 'You audit an autonomous build against its original goal and decide whether it is finished. '
          + 'You are demanding but practical: only ask for more work that meaningfully closes the gap to the '
          + 'stated quality bar. If the remaining gap is cosmetic and the bar is met, say ship. New tasks must '
          + 'follow the same rules: small, file-specific, checkable. Respond with JSON only.',
      },
      {
        role: 'user',
        content: `ORIGINAL GOAL:\n${goal}\n\nQUALITY BAR: ${directives.quality_bar}\n\n`
          + `TASK STATUS:\n${summary}\n\n`
          + `RECENT CRITIC COMPLAINTS:\n${issues || '(none)'}\n\n`
          + `FILES IN PROJECT:\n${fileList.join('\n')}\n\n`
          + `This is refinement round ${round}. Decide: ship, or emit up to 6 new tasks that close the biggest gaps.`,
      },
    ],
  });

  res.new_tasks = sanitiseTasks(res.new_tasks ?? []);
  log.ok('planner', `gap analysis: ${res.verdict}${res.new_tasks.length ? ` (+${res.new_tasks.length} tasks)` : ''}`);
  return res;
}

/** Defensive cleanup: models emit duplicate ids, dangling deps, missing arrays. */
function sanitiseTasks(raw) {
  const seen = new Set();
  const tasks = [];
  for (const t of raw) {
    if (!t?.id || !t?.title) continue;
    const slug = (s) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
    let id = slug(t.id);
    // Models routinely ignore the "descriptive kebab-case id" instruction and
    // emit positional ids instead: task-1, step-2, 001, 7. Those make the
    // status view and the report useless, so derive one from the title.
    if (!id || /^(task|step|item|t|n)?-?\d+$/.test(id)) {
      id = slug(t.title).split('-').slice(0, 4).join('-');
    }
    if (!id) continue;
    while (seen.has(id)) id = `${id}-2`;
    seen.add(id);
    tasks.push({
      id,
      title: String(t.title),
      description: String(t.description ?? t.title),
      category: String(t.category ?? 'gameplay'),
      files: Array.isArray(t.files) ? t.files : [],
      dependsOn: Array.isArray(t.depends_on) ? t.depends_on : [],
      acceptanceCriteria: Array.isArray(t.acceptance_criteria) ? t.acceptance_criteria : [],
      visual: Boolean(t.visual),
      status: 'pending',
      attempts: 0,
      lastScore: null,
    });
  }
  // Drop dependencies on tasks that were never emitted, or the scheduler deadlocks.
  const ids = new Set(tasks.map((t) => t.id));
  for (const t of tasks) t.dependsOn = t.dependsOn.filter((d) => ids.has(d) && d !== t.id);
  return tasks;
}

/** Ready tasks = pending with all dependencies satisfied. */
export function readyTasks(tasks) {
  const done = new Set(tasks.filter((t) => t.status === 'completed').map((t) => t.id));
  return tasks.filter((t) => t.status === 'pending' && t.dependsOn.every((d) => done.has(d)));
}

/**
 * If nothing is ready but work remains, dependencies are blocked behind parked
 * tasks. Release the least-blocked one rather than deadlocking the run.
 */
export function breakDeadlock(tasks) {
  const pending = tasks.filter((t) => t.status === 'pending');
  if (!pending.length) return null;
  const unmet = (t) => t.dependsOn.filter((d) => tasks.find((x) => x.id === d)?.status !== 'completed').length;
  pending.sort((a, b) => unmet(a) - unmet(b));
  const victim = pending[0];
  log.warn('planner', `deadlock: releasing "${victim.id}" with unmet dependencies`);
  victim.dependsOn = [];
  return victim;
}
