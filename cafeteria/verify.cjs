// Headless verification for cafeteria/index.html (spec §15 verification plan).
// Run:  NODE_PATH=$(npm root -g) node cafeteria/verify.cjs [--shots]
// Drives the real page in Chromium, checks map integrity, the canon combos, the Alibi Engine,
// the Method Ledger → countermeasure path, duels and the trial. Exits non-zero on any failure.
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const SHOTS = process.argv.includes('--shots');
const shotDir = path.join(__dirname, 'shots');
const url = 'file://' + path.join(__dirname, 'index.html');
let failures = 0;
const ok = (cond, msg) => { console.log(`${cond ? 'PASS' : 'FAIL'}  ${msg}`); if (!cond) failures++; };

(async () => {
  const launchOpts = fs.existsSync('/opt/pw-browsers/chromium') ? {} : {};
  const browser = await chromium.launch(launchOpts);
  const page = await browser.newPage({ viewport: { width: 1280, height: 860 } });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(url);
  await page.waitForTimeout(300);
  if (SHOTS) { fs.mkdirSync(shotDir, { recursive: true }); }
  const shot = async name => { if (SHOTS) await page.screenshot({ path: path.join(shotDir, name + '.png') }); };
  await shot('00-title');

  // --- boot (real click on the title's Begin button) ---
  await page.click('text=Begin');
  await page.waitForTimeout(200);
  ok(await page.evaluate(() => CC.G.stage === 'act1' && !CC.G.paused), 'game starts in Act 1, unpaused');

  // --- map integrity ---
  const integrity = await page.evaluate(() => {
    const out = { links: {}, badRoutes: [], unreachable: [] };
    for (const [ch, ends] of Object.entries(CC.G.links)) out.links[ch] = ends.length;
    for (const g of CC.G.guards) {
      if (g.archmage) continue;
      for (const [x, y] of g.route) {
        const m = CC.G.maps[g.home];
        if (!guardPassable(m, x, y, null)) out.badRoutes.push(`${g.id}@${x},${y}`);
        const p = findPath(TOWER_MAPS, { map: g.map, x: Math.floor(g.x), y: Math.floor(g.y) }, { map: g.home, x, y }, guardPassable, true);
        if (!p) out.unreachable.push(`${g.id}->${x},${y}`);
      }
    }
    // player reachability: hub start → a tile next to the vault pedestal, treating doors as passable and all links usable
    const pass = (m, x, y) => inb(m, x, y) && (!SOLID_CH.has(m.tiles[y][x]) || 'DLKH'.includes(m.tiles[y][x]));
    const ids = ['hub', 'f0', 'f1', 'f2'];
    const seen = new Set(), q = [['hub', HUB_START.x, HUB_START.y]];
    seen.add(`hub,${HUB_START.x},${HUB_START.y}`);
    let reached = false;
    while (q.length) {
      const [mi, x, y] = q.shift(); const m = CC.G.maps[mi];
      if (mi === 'f2' && Math.abs(x - 37) <= 1 && Math.abs(y - 24) <= 1) { reached = true; break; }
      const nb = [[1, 0], [-1, 0], [0, 1], [0, -1]].map(([dx, dy]) => [mi, x + dx, y + dy]);
      const ch = m.tiles[y][x];
      if (isLinkCh(ch)) { const o = linkOther(ch, mi, x, y); if (o) nb.push([o.map, o.x, o.y]); }
      for (const [nm, nx, ny] of nb) {
        const k = `${nm},${nx},${ny}`; if (seen.has(k)) continue;
        if (!pass(CC.G.maps[nm], nx, ny)) continue;
        seen.add(k); q.push([nm, nx, ny]);
      }
    }
    out.vaultReachable = reached;
    return out;
  });
  ok(Object.values(integrity.links).every(n => n === 2) && Object.keys(integrity.links).length === 7, `every link digit pairs exactly once (${JSON.stringify(integrity.links)})`);
  ok(integrity.badRoutes.length === 0, `all guard waypoints walkable ${integrity.badRoutes.join(' ')}`);
  ok(integrity.unreachable.length === 0, `all guard waypoints reachable ${integrity.unreachable.join(' ')}`);
  ok(integrity.vaultReachable, 'the vault pedestal is reachable from the quad');

  // --- free run: 30 s of sim ---
  const moved = await page.evaluate(() => {
    const before = CC.G.guards.map(g => [g.x, g.y, g.map].join());
    for (let i = 0; i < 600; i++) CC.tick();
    const after = CC.G.guards.map(g => [g.x, g.y, g.map].join());
    return before.filter((b, i) => b !== after[i]).length;
  });
  ok(moved >= 5, `guards patrol during 30 s of sim (${moved} moved)`);
  await shot('01-quad');

  // --- walking with real key input ---
  const walk = await page.evaluate(() => [CC.G.player.x, CC.G.player.y]);
  await page.keyboard.down('KeyD'); await page.waitForTimeout(500); await page.keyboard.up('KeyD');
  const walk2 = await page.evaluate(() => [CC.G.player.x, CC.G.player.y]);
  ok(walk2[0] > walk[0] + 0.5, `D key walks the player east (${walk[0].toFixed(2)} → ${walk2[0].toFixed(2)})`);

  // --- real input: Tab notebook, E at Mother Ladle's counter ---
  await page.keyboard.press('Tab');
  ok(await page.evaluate(() => $('ovp').innerHTML.startsWith('<h2>Notebook') && CC.G.paused), 'Tab opens the notebook and pauses');
  await page.keyboard.press('Tab');
  ok(await page.evaluate(() => !overlayOpen() && !CC.G.paused), 'Tab closes it again');
  await page.evaluate(() => { CC.G.player.map = 'hub'; CC.G.player.x = 5.5; CC.G.player.y = 21.5; CC.mouse.wx = 4.5; CC.mouse.wy = 21.5; });
  await page.keyboard.press('KeyE');
  ok(await page.evaluate(() => /Mother Ladle/.test($('ovp').innerHTML)), 'E across the counter opens Mother Ladle\'s shop');
  await page.locator('#ovp button', { hasText: 'Buy' }).first().click();
  ok(await page.evaluate(() => CC.G.merit === 15 && CC.G.player.tools.smoke === 3), 'buying a smoke bomb spends 10 merit');
  await page.locator('#ovp button', { hasText: 'Leave' }).click();

  // --- canon combo: Grease + Gust curls a bust into a guard (env KO) ---
  const curl = await page.evaluate(() => {
    const G = CC.G, m = G.maps.f1;
    G.player.map = 'f1'; G.player.x = 18.5; G.player.y = 12.5; G.player.mana = 100;
    for (const g of G.guards) if (g.map === 'f1') { g.x = 40.5; g.y = 25.5; g.state = 'patrol'; g.path = null; g.route = [[40, 25]]; }
    const tgt = G.guards.find(g => g.id === 'g6');
    tgt.x = 24.5; tgt.y = 12.5; tgt.route = [[24, 12]]; tgt.face = 0; tgt.suspicion = 0;
    castGrease(m, 21, 12); castGrease(m, 23, 12);
    CC.mouse.wx = 21; CC.mouse.wy = 12.5;
    const before = G.tower.ledger.env_ko;
    castGust(m);
    for (let i = 0; i < 60; i++) CC.tick();
    return { ko: tgt.ko > 0, env: G.tower.ledger.env_ko - before, grease: G.tower.ledger.grease_casts };
  });
  ok(curl.ko && curl.env === 1, `Grease + Gust: bust curls into a guard → environmental KO (env_ko +${curl.env})`);
  ok(curl.grease === 2, `grease casts are counted in the Method Ledger (${curl.grease})`);
  await page.evaluate(() => { CC.G.player.x = 21.5; CC.G.player.y = 13.5; });
  await page.waitForTimeout(250);
  await shot('02-gallery-grease');

  // --- canon combo: smoke + douse + freeze = ice-block door seal ---
  const seal = await page.evaluate(() => {
    const m = CC.G.maps.f1;
    forArea(m, 26, 17, (x, y, i) => { if (!isSolid(m, x, y)) { m.cloud[i] = C_SMOKE; m.cTimer[i] = SMOKE_TIME; } });
    castDouse(m, 26, 17);
    const fog = m.cloud[idx(m, 26, 17)] === C_FOG;
    castFreeze(m, 26, 17);
    return { fog, solid: isSolid(m, 26, 17), opaque: isOpaque(m, 26, 17, true) };
  });
  ok(seal.fog && seal.solid && seal.opaque, 'Smoke → Douse = wet fog → Freeze = solid, opaque ice block');

  // --- heat rune reactions (Act 3 surfaces) ---
  const runes = await page.evaluate(() => {
    const m = CC.G.maps.f1, i = idx(m, 30, 13);
    m.rune[i] = 1; m.cool[i] = 0;
    castGrease(m, 30, 13);
    const burn = m.surface[i] === S_BURN;
    castDouse(m, 30, 13);
    const steam = m.cloud[i] === C_STEAM;
    castFreeze(m, 30, 13);
    const cooled = m.cool[i] > 0;
    m.rune[i] = 0; m.cloud[i] = C_NONE;
    return { burn, steam, cooled };
  });
  ok(runes.burn && runes.steam && runes.cooled, 'heat rune: Grease → burning slick, Douse → steam, Freeze → cooled');

  // --- Silence swallows noise ---
  const silent = await page.evaluate(() => {
    const G = CC.G;
    G.silences.push({ map: 'f1', x: 33.5, y: 13.5, t: 5 });
    const g = G.guards.find(g => g.id === 'g8'); g.map = 'f1'; g.x = 33.5; g.y = 9.5; g.state = 'patrol'; g.ko = 0;
    const heard = emitNoise('f1', 33.5, 13.5, 8, 'glass', 'player');
    G.silences = [];
    return heard;
  });
  ok(silent === false, 'glass broken inside a Silence dome is not heard');

  // --- Alibi Engine: cleared with witnesses, Vacuum pulls guards ---
  const alibi = await page.evaluate(() => {
    const G = CC.G;
    G.player.map = 'hub'; G.player.x = 24.5; G.player.y = 18.5; G.heat = 30;
    const studs = G.npcs.filter(n => n.kind === 'student').slice(0, 3);
    studs.forEach((s, k) => { s.x = 22.5 + k; s.y = 16.5; s.path = null; s.waitT = 999; });
    for (let i = 0; i < 240; i++) CC.tick();   // let earlier teleports age out of the ±10 s window
    G.heat = 30;
    const g9 = G.guards.find(g => g.id === 'g9');
    g9.map = 'f2'; g9.x = 35.5; g9.y = 12.5; g9.state = 'patrol'; g9.ko = 0; g9.earmuffs = false;
    const heatBefore = G.heat;
    createIncident('f1', 35.5, 13.5);
    const investigating = g9.state === 'investigate';
    for (let i = 0; i < 230; i++) CC.tick();
    return { heatBefore, heatAfter: G.heat, investigating, log: G.notebook.log.slice(0, 3) };
  });
  ok(alibi.investigating, 'the Vacuum pulls the vault warden down a floor to investigate');
  ok(alibi.heatAfter < alibi.heatBefore - 10 && alibi.log.some(l => l.startsWith('✔ ALIBI')), `three student witnesses clear the incident (heat ${alibi.heatBefore.toFixed(1)} → ${alibi.heatAfter.toFixed(1)})`);

  const noAlibi = await page.evaluate(() => {
    const G = CC.G;
    G.player.map = 'f0'; G.player.x = 3.5; G.player.y = 3.5; G.heat = 10;
    for (let i = 0; i < 20; i++) CC.tick();
    const nd = G.tower.ledger.noise_distractions;
    createIncident('f0', 8.5, 4.5);
    for (let i = 0; i < 230; i++) CC.tick();
    return { heat: G.heat, nd: G.tower.ledger.noise_distractions - nd, log: G.notebook.log[0] };
  });
  ok(noAlibi.heat >= 29 && noAlibi.nd === 2 && noAlibi.log.startsWith('✘'), `no witnesses → Heat +20 and an extra ledger mark (heat ${noAlibi.heat.toFixed(1)}, +${noAlibi.nd} marks)`);

  // --- office hours move Gilt between tower and pavilion ---
  const office = await page.evaluate(() => {
    const G = CC.G;
    G.hubClock = 10 * 60 + 5; CC.tick();
    const a = { hub: npcPresent(G.npcs.find(n => n.kind === 'gilt')), towerAway: G.gilt.away };
    G.hubClock = 10 * 60 + 40; CC.tick();
    const b = { hub: npcPresent(G.npcs.find(n => n.kind === 'gilt')), towerAway: G.gilt.away };
    return { a, b };
  });
  ok(office.a.hub && office.a.towerAway && !office.b.hub && !office.b.towerAway, 'office hours (:00–:30) put Gilt at the pavilion and empty her study');

  // --- Gilt's conversation is a credibility-4 witness ---
  const convo = await page.evaluate(() => {
    const G = CC.G;
    G.hubClock = 11 * 60 + 2; CC.tick();
    const gn = G.npcs.find(n => n.kind === 'gilt');
    G.player.map = 'hub'; G.player.x = gn.x + 1; G.player.y = gn.y;
    startConvo();
    for (let i = 0; i < 10; i++) CC.tick();
    const e = G.witnessLog[G.witnessLog.length - 1];
    const cred = e.wits.filter(w => w.kind === 'archmage').reduce((a, w) => a + w.cred, 0);
    endConvo();
    return cred;
  });
  ok(convo === 4, `an Archmage talking at you counts as credibility 4 (${convo})`);

  // --- lock minigame: Mage Hand success counts toward sap ---
  const lock = await page.evaluate(() => {
    const G = CC.G, m = G.maps.f1;
    G.player.map = 'f1'; G.player.x = 26.5; G.player.y = 23.5;
    const before = G.tower.ledger.magehand_locks;
    startLock(m, 24, 23, true);
    let guard = 0;
    while (G.lock && guard++ < 400) { CC.tick(); if (lockGlow() > 0.9) lockPress(); }
    return { opened: m.tiles[23][24] === 'O', counted: G.tower.ledger.magehand_locks - before };
  });
  ok(lock.opened && lock.counted === 1, 'Mage Hand lockpicking opens the pantry door and is logged');

  // --- relic carry rules ---
  const carry = await page.evaluate(() => {
    const G = CC.G;
    G.player.map = 'f0'; G.player.x = 18.5; G.player.y = 25.5; G.player.carrying = 'phoenix'; G.tower.relic = 'player';
    useLink('3', 'f0', 18, 25);
    const blocked = G.player.map === 'f0';
    G.player.carrying = null; G.tower.relic = 'pedestal';
    return blocked;
  });
  ok(carry, 'the Phoenix will not fit in the dumbwaiter');

  // --- Act 1 → ledger → countermeasures → Act 3 ---
  const act3 = await page.evaluate(() => {
    const G = CC.G;
    Object.assign(G.tower.ledger, { melee_ko: 2, alerts: 1, grease_casts: 3, magehand_locks: 2, noise_distractions: 3 });
    G.player.carrying = 'phoenix';
    completeAct1();
    const cms = G.tower.countermeasures.slice();
    closeOverlay();
    startAct3();
    const gs = G.guards.filter(g => !g.archmage);
    return {
      cms, stage: G.stage, night: G.night, carrying: G.player.carrying,
      helmets: gs.every(g => g.helmet), muffs: gs.every(g => g.earmuffs), cleats: gs.every(g => g.cleats),
      runes: G.maps.f1.rune.reduce((a, b) => a + b, 0) + G.maps.f2.rune.reduce((a, b) => a + b, 0),
      sap: G.maps.f1.sapped.size + G.maps.f2.sapped.size, giltAsleep: G.gilt.asleep,
      notices: G.notices.length,
    };
  });
  ok(act3.cms.join() === 'helmets,heatRunes,sap,earmuffs', `ledger buys the right countermeasures (${act3.cms.join(', ')})`);
  ok(act3.stage === 'act3' && act3.night && act3.carrying === 'phoenix' && act3.giltAsleep, 'Act 3 starts at night, carrying the relic, Gilt asleep');
  ok(act3.helmets && act3.muffs && act3.cleats && act3.runes === 9 && act3.sap === 2, `countermeasures applied (runes ${act3.runes}, sapped locks ${act3.sap})`);
  ok(act3.notices > 3, 'the notice board carries the Pride Cover-Up announcements');
  await page.evaluate(() => { for (let i = 0; i < 40; i++) CC.tick(); });
  await shot('03-act3-night-grounds');

  const helmet = await page.evaluate(() => {
    const G = CC.G, g = G.guards.find(g => g.id === 'g3');
    G.player.map = g.map; G.player.x = g.x - Math.cos(g.face) * 0.9; G.player.y = g.y - Math.sin(g.face) * 0.9;
    takedown(g);
    return { ko: g.ko > 0, state: g.state };
  });
  ok(!helmet.ko && helmet.state === 'pursuit', 'bucket helmets: crowbar takedown fails and the guard turns on you');

  const muffs = await page.evaluate(() => {
    const G = CC.G, g = G.guards.find(g => g.id === 'g6');
    g.state = 'patrol'; g.path = null;
    const heard = emitNoise(g.map, g.x + 1, g.y, 10, 'plant', 'player');
    return heard;
  });
  ok(muffs === false, 'earmuffs: guards are deaf to a noisemaker right next to them');

  // vault floor going loud spoils the return
  const loud = await page.evaluate(() => {
    const G = CC.G;
    G.player.map = 'f2'; G.player.x = 37.5; G.player.y = 22.5;
    G.maps.f2.tiles[18][37] = 'O';
    G.tower.relic = 'player'; G.player.carrying = 'phoenix';
    G.guards.forEach(g => { if (!g.archmage) { g.x = 40.5; g.y = 12.5; g.map = 'f1'; } });
    placeRelic();
    const vaultAlertBefore = G.tower.vaultAlert;
    G.player.x = 37.5; G.player.y = 20.5; G.player.lastTile = -1; CC.tick();   // step on a ward-line
    return { before: vaultAlertBefore, after: G.tower.vaultAlert, relic: G.tower.relic };
  });
  ok(loud.relic === 'pedestal' && !loud.before && loud.after, 'tripping a vault ward-line in Act 3 marks the Return Trip as loud');
  await page.evaluate(() => { CC.G.revealT = 8; for (let i = 0; i < 4; i++) CC.tick(); });
  await shot('04-vault-reveal');

  // --- duel: losing teaches the counter, flexing the Phoenix attunes ---
  const duel = await page.evaluate(() => {
    const G = CC.G;
    G.night = false; G.stage = 'intermission'; G.tower.relic = 'owned'; G.player.carrying = null;
    G.player.map = 'hub'; G.player.x = 20.5; G.player.y = 19.5;
    G.notebook.comebacks = ['diet']; G.notebook.roasts = ['int1', 'fash1'];
    startDuel(G.npcs.find(n => n.id === 'percival'));
    duelAnswer(null);                       // spell1 — lose, learn spellcraft
    const learned = G.notebook.comebacks.includes('spellcraft');
    duelFlex();
    duelAnswer('diet');                     // wrong vs relic roast — learn relic
    duelAnswer('fashion');                  // fash1 — fashion not known yet → wrong → learn fashion
    const res = { learned, attuned: G.attuned, relic: G.notebook.comebacks.includes('relic'), over: G.duel.over || G.duel.ow >= 3 };
    return res;
  });
  ok(duel.learned && duel.attuned && duel.relic, 'duels teach counters on a loss; flexing the Phoenix attunes it');
  await page.waitForTimeout(150);
  await shot('05-duel');
  await page.evaluate(() => endDuel());

  // --- trial: insider line + visual punctuation ---
  const trial = await page.evaluate(() => {
    const G = CC.G;
    G.notebook.comebacks = ['spellcraft', 'fashion', 'intellect', 'lineage', 'diet', 'relic'];
    G.tower.returnClean = true; G.attuned = true;
    startTrial();
    const q = G.trial.q.map(r => r.insider ? 'insider' : r.topic);
    trialAnswer('lineage'); trialAnswer('slam'); trialAnswer('insider');
    return { q, ego: G.trial.ego, done: G.trial.done };
  });
  ok(trial.q[2] === 'insider', 'a clean Return Trip puts Gilt\'s Phoenix flex into the trial');
  ok(trial.done === 'shattered' || trial.ego <= 30, `insider line + punctuation hit hard (ego ${trial.ego}, ${trial.done || 'ongoing'})`);
  await shot('06-trial');

  const trialFull = await page.evaluate(() => {
    const G = CC.G;
    G.notebook.comebacks = ['spellcraft', 'fashion', 'intellect', 'lineage', 'diet'];
    G.tower.returnClean = false; G.attuned = false;
    startTrial();
    for (const r of G.trial.q.slice()) { if (G.trial.done) break; trialAnswer(r.topic); }
    return G.trial.done;
  });
  ok(trialFull === 'shattered', 'five right comebacks shatter Gilt without insider help');

  ok(errors.length === 0, `no console or page errors${errors.length ? ': ' + errors.slice(0, 5).join(' | ') : ''}`);
  await browser.close();
  console.log(failures ? `\n${failures} check(s) failed` : '\nAll checks passed');
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
