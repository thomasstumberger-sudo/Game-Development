/**
 * The adversarial reviewer.
 *
 * Two independent judgements:
 *
 *  1. critique()      - scores a screenshot against a rubric and the task's own
 *                       acceptance criteria, and must produce actionable fixes.
 *  2. blindCompare()  - shows the critic our frame and a reference frame with
 *                       the presentation order randomised, and asks which is
 *                       better. The critic is never told which is which. Order
 *                       is flipped across rounds so positional bias cancels.
 *
 * A vision model will flatter you if you let it. Three countermeasures:
 *  - The rubric forces per-axis scores, and the total is computed in code from
 *    those axes rather than accepted from the model, so it cannot hand-wave a
 *    high number.
 *  - The prompt demands a minimum number of concrete defects. "Nothing wrong"
 *    is not an accepted answer while the score is below the bar.
 *  - The blind comparison is scored by counting wins in code after unmasking.
 */
import fs from 'node:fs';
import path from 'node:path';
import { chatVision } from './ollama.js';
import { config } from './config.js';
import { log } from './logger.js';
import {
  getRubric, detectDomain, activeAxes, buildCritiqueSchema, buildCriticSystem, computeScore,
} from './rubrics.js';

const COMPARE_SCHEMA = {
  type: 'object',
  properties: {
    better: { type: 'string', enum: ['A', 'B'] },
    margin: { type: 'string', enum: ['decisive', 'clear', 'slight'] },
    reasoning: { type: 'string' },
    what_the_loser_lacks: { type: 'array', items: { type: 'string' } },
  },
  required: ['better', 'margin', 'reasoning', 'what_the_loser_lacks'],
};

const toBase64 = (buf) => Buffer.from(buf).toString('base64');

/**
 * Decide whether the UI-only axis applies. A HUD is nearly universal in games,
 * so we look for evidence in the task rather than assuming either way.
 */
function taskShowsUI(task, domain) {
  if (domain === 'ui_app') return true;
  return /ui|hud|menu|interface|inventory|dialog|overlay|score|health/i.test(
    `${task.title ?? ''} ${task.category ?? ''} ${task.description ?? ''}`,
  );
}

/**
 * Grade one screenshot.
 * @returns {Promise<{score:number, verdict:'PASS'|'FAIL', tier:string, issues:string[],
 *   fixes:string[], axisScores:object, readsAs:string, unmetCriteria:string[]}>}
 */
export async function critique({ screenshot, task, directives, health, domain, goal }) {
  const chosenDomain = domain
    ?? directives?.visual_domain
    ?? detectDomain(`${directives?.one_line_goal ?? ''} ${directives?.stack ?? ''} ${task.title ?? ''}`);
  const rubric = getRubric(chosenDomain);
  const hasUI = taskShowsUI(task, chosenDomain);

  const criteria = (task.acceptanceCriteria ?? []).map((c, i) => `${i + 1}. ${c}`).join('\n') || '(none specified)';
  const axisList = activeAxes(rubric, { hasUI }).map((a) => `- ${a.key}: ${a.desc}`).join('\n');

  const healthNote = health
    ? `\nMEASURED RUNTIME FACTS (these are ground truth, not opinion):\n`
      + `- frame rate: ${health.fps ?? 'unknown'} fps\n`
      + `- console errors: ${health.consoleErrors?.length ?? 0}\n`
      + `- draw calls: ${health.drawCalls ?? 'unknown'}\n`
    : '';

  // The one-line summary throws away the art direction the user actually wrote,
  // which is the only thing that makes this critique specific rather than generic.
  const goalBlock = goal
    ? `THE USER'S BRIEF, VERBATIM — judge against these specifics:\n${goal}\n`
    : `PROJECT GOAL: ${directives.one_line_goal}\n`;

  const prompt = `Review this frame from a work-in-progress build.

${goalBlock}
QUALITY BAR: ${directives.quality_bar}
REFERENCE TARGETS: ${(directives.reference_targets ?? []).join(', ') || 'current-generation commercial titles'}

TASK UNDER REVIEW: ${task.title}
${task.description}

ACCEPTANCE CRITERIA:
${criteria}
${healthNote}
This is a ${rubric.label}. Score each axis 0-100, where 100 is a shipped commercial title in this category and 20 is an unfinished placeholder:
${axisList}

State plainly what the image reads as. List every defect you can see with a concrete fix. Judge each acceptance criterion as met or not, based only on what is visible.`;

  const raw = await chatVision({
    role: 'critic',
    system: buildCriticSystem(rubric),
    prompt,
    images: [toBase64(screenshot)],
    schema: buildCritiqueSchema(rubric, { hasUI }),
  });

  const score = computeScore(rubric, raw.axis_scores, { hasUI });

  const defects = Array.isArray(raw.defects) ? raw.defects : [];
  const unmetCriteria = (raw.criteria_met ?? []).filter((c) => !c.met).map((c) => c.criterion);

  // Objective health overrides opinion. A model cannot pass a broken build.
  let verdict = score >= config.critic.passScore && unmetCriteria.length === 0 ? 'PASS' : 'FAIL';
  const overrides = [];
  if (health?.blankScreen) { verdict = 'FAIL'; overrides.push('screen is blank or a single flat colour'); }
  if (health?.pageErrors?.length) { verdict = 'FAIL'; overrides.push(`${health.pageErrors.length} uncaught page error(s)`); }
  if (health?.consoleErrors?.length) { verdict = 'FAIL'; overrides.push(`${health.consoleErrors.length} console error(s)`); }
  if (health?.fps != null && health.fps < 30) { verdict = 'FAIL'; overrides.push(`frame rate ${health.fps} fps is below the 30 fps floor`); }
  if (defects.some((d) => d.severity === 'critical')) verdict = 'FAIL';

  const issues = [
    ...overrides.map((o) => `[objective] ${o}`),
    ...defects.map((d) => `[${d.severity}] ${d.issue}`),
    ...unmetCriteria.map((c) => `[unmet criterion] ${c}`),
  ];

  log.info('critic', `${task.id}: ${score}/100 tier=${raw.tier} ${verdict} [${chosenDomain}] — "${raw.reads_as}"`);

  return {
    taskId: task.id,
    domain: chosenDomain,
    score,
    verdict,
    tier: raw.tier,
    readsAs: raw.reads_as,
    axisScores: raw.axis_scores,
    issues,
    fixes: defects.map((d) => d.fix).filter(Boolean),
    strengths: raw.strengths ?? [],
    unmetCriteria,
  };
}

/**
 * Blind side-by-side against a reference image.
 *
 * The critic sees two images labelled only A and B, in an order we randomise
 * per round and record privately. It does not know which is the build and which
 * is the reference. We unmask afterwards and count wins.
 */
export async function blindCompare({ screenshot, referencePath, directives, domain, rounds = config.critic.blindRounds }) {
  const refBuf = fs.readFileSync(referencePath);
  const refName = path.basename(referencePath);
  const results = [];
  const rubric = getRubric(domain ?? directives?.visual_domain ?? detectDomain(directives?.quality_bar ?? ''));
  const criteria = rubric.axes.map((a) => a.key.replace(/_/g, ' ')).join(', ');

  for (let i = 0; i < rounds; i++) {
    // Alternate ordering deterministically, then jitter, so bias cancels.
    const oursIsA = i % 2 === 0;
    const images = oursIsA
      ? [toBase64(screenshot), toBase64(refBuf)]
      : [toBase64(refBuf), toBase64(screenshot)];

    const prompt = `Two frames are shown: IMAGE A first, then IMAGE B. Both are ${rubric.label}s.

You are not told which is which, and you must not speculate about their origin. Judge only the craft on screen, on these criteria: ${criteria}.

${rubric.negativeRules.map((r) => `- ${r}`).join('\n')}

Context for what matters: ${directives.quality_bar}

Which image is the higher-production-value image? Answer A or B, state the margin, and list specifically what the weaker image lacks.`;

    try {
      const res = await chatVision({
        role: 'critic',
        system: 'You are a blind-test judge for game visual quality. You compare two frames on craft alone and '
          + 'always pick one as better. You never refuse to choose. Respond with JSON only.',
        prompt,
        images,
        schema: COMPARE_SCHEMA,
        temperature: 0.3,
      });

      const oursWon = (res.better === 'A') === oursIsA;
      results.push({
        round: i + 1,
        oursWon,
        margin: res.margin,
        reasoning: res.reasoning,
        gaps: oursWon ? [] : (res.what_the_loser_lacks ?? []),
      });
      log.info('critic', `blind round ${i + 1} vs ${refName}: ${oursWon ? 'OUR BUILD WINS' : 'reference wins'} (${res.margin})`);
    } catch (err) {
      log.warn('critic', `blind round ${i + 1} failed: ${err.message}`);
    }
  }

  const wins = results.filter((r) => r.oursWon).length;
  const gaps = [...new Set(results.flatMap((r) => r.gaps))];
  return {
    reference: refName,
    rounds: results.length,
    wins,
    winRate: results.length ? wins / results.length : 0,
    passed: results.length > 0 && wins > results.length / 2,
    gaps,
    detail: results,
  };
}

/** Reference images the user has dropped in for comparison. */
export function loadReferences(referencesDir) {
  if (!fs.existsSync(referencesDir)) return [];
  return fs.readdirSync(referencesDir)
    .filter((f) => /\.(png|jpe?g|webp)$/i.test(f))
    .map((f) => path.join(referencesDir, f));
}
