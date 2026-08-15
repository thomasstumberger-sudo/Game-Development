/**
 * Run state, persisted after every meaningful transition.
 *
 * A local-model run of this size takes hours. Power cuts, OOM kills and Ctrl-C
 * all happen. Everything needed to resume lives in one JSON file.
 */
import fs from 'node:fs';
import path from 'node:path';

export class RunState {
  constructor(statePath, initial = {}) {
    this.path = statePath;
    this.data = {
      goal: '',
      directives: null,
      architecture: '',
      tasks: [],
      critiques: [],
      blindResults: [],
      round: 0,
      startedAt: new Date().toISOString(),
      finishedAt: null,
      status: 'running',
      ...initial,
    };
  }

  static load(statePath) {
    if (!fs.existsSync(statePath)) return null;
    try {
      const data = JSON.parse(fs.readFileSync(statePath, 'utf8'));
      const s = new RunState(statePath);
      s.data = data;
      return s;
    } catch {
      return null;
    }
  }

  save() {
    fs.mkdirSync(path.dirname(this.path), { recursive: true });
    // Write-then-rename so a crash mid-write can't corrupt the state file.
    const tmp = `${this.path}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(this.data, null, 2));
    fs.renameSync(tmp, this.path);
  }

  task(id) {
    return this.data.tasks.find((t) => t.id === id);
  }

  addTasks(tasks) {
    const existing = new Set(this.data.tasks.map((t) => t.id));
    const added = tasks.filter((t) => !existing.has(t.id));
    this.data.tasks.push(...added);
    this.save();
    return added.length;
  }

  recordCritique(c) {
    this.data.critiques.push({ ...c, at: new Date().toISOString() });
    this.save();
  }

  recordBlind(b) {
    this.data.blindResults.push({ ...b, at: new Date().toISOString() });
    this.save();
  }

  get stats() {
    const by = (s) => this.data.tasks.filter((t) => t.status === s).length;
    // "completed" alone is misleading: a task accepted below the quality bar
    // carries the same status as one that passed. Split them so the count
    // reported to the user means what it looks like it means.
    const belowBar = this.data.tasks.filter(
      (t) => t.status === 'completed' && t.note === 'accepted below the quality bar',
    ).length;
    const completed = by('completed');
    return {
      total: this.data.tasks.length,
      completed,
      passed: completed - belowBar,
      belowBar,
      failed: by('failed'),
      parked: by('parked'),
      pending: by('pending'),
      running: by('running'),
    };
  }
}
