extends Node
## Headless test suite (port of the web build's verify.cjs, plus the end-to-end playthrough).
## Run: tools/run_tests.sh   (or: godot --headless --path cafeteria/game -- --test)
## `-- --shots` (needs a renderer, e.g. under xvfb-run) also writes screenshots to cafeteria/game/shots/.

var main
var sim: Sim
var ui
var failures := 0
var passes := 0
var shots := false


func ok(cond: bool, msg: String) -> void:
	print(("PASS  " if cond else "FAIL  ") + msg)
	if cond:
		passes += 1
	else:
		failures += 1


func run(p_main, p_shots: bool) -> void:
	main = p_main
	sim = main.sim
	ui = main.ui
	shots = p_shots
	main.feed_input = false
	_run_all.call_deferred()


func ticks(n: int) -> void:
	for i in n:
		sim.tick()


func frames(n: int) -> void:
	for i in n:
		await get_tree().process_frame


func shot(name: String) -> void:
	if not shots:
		return
	main.update_camera(true)
	await frames(4)
	var dir := ProjectSettings.globalize_path("res://shots")
	DirAccess.make_dir_recursive_absolute(dir)
	get_viewport().get_texture().get_image().save_png(dir + "/" + name + ".png")


func key(code: Key) -> void:
	var ev := InputEventKey.new()
	ev.physical_keycode = code
	ev.keycode = code
	ev.pressed = true
	Input.parse_input_event(ev)
	var up := ev.duplicate()
	up.pressed = false
	Input.parse_input_event(up)


func press_button(prefix: String) -> bool:
	for b in _all_buttons(ui):
		if b.visible and b.text.begins_with(prefix):
			b.pressed.emit()
			return true
	return false


func _all_buttons(n: Node) -> Array:
	var out: Array = []
	for c in n.get_children():
		if c is Button:
			out.append(c)
		out.append_array(_all_buttons(c))
	return out


func at(map_id: String, x: int, y: int, mx: float = -1, my: float = -1) -> void:
	var p := sim.player
	p.map_id = map_id
	p.x = x + 0.5
	p.y = y + 0.5
	p.last_tile = -1
	sim.mouse_world = Vector2((x if mx < 0 else mx) + 0.5, (y if my < 0 else my) + 0.5)


func _run_all() -> void:
	ui.show_title()
	await frames(2)
	await shot("00-title")
	ok(sim.stage == "title" and ui.panel_kind() == "title", "the title screen shows on boot")
	ok(press_button("Begin"), "the Begin button exists")
	await frames(2)
	ok(sim.stage == "act1" and not sim.paused, "Begin starts Act 1, unpaused")

	_map_integrity()

	# --- free run: 30 s ---
	var before := sim.guards.map(func(g): return "%s,%s,%s" % [g.x, g.y, g.map_id])
	var t0 := Time.get_ticks_usec()
	ticks(600)
	var per_tick_ms := (Time.get_ticks_usec() - t0) / 600.0 / 1000.0
	print("INFO  sim tick: %.2f ms average over 600 ticks (budget at 20 Hz: 50 ms)" % per_tick_ms)
	ok(per_tick_ms < 10.0, "the 20 Hz sim tick stays well inside budget (%.2f ms)" % per_tick_ms)
	var moved := 0
	for i in sim.guards.size():
		var g: Entities.Guard = sim.guards[i]
		if "%s,%s,%s" % [g.x, g.y, g.map_id] != before[i]:
			moved += 1
	ok(moved >= 5, "guards patrol during 30 s of sim (%d moved)" % moved)
	await shot("01-quad")

	# --- real input through the InputMap ---
	main.feed_input = true
	var x0 := sim.player.x
	Input.action_press("move_right")
	await get_tree().create_timer(0.5).timeout
	Input.action_release("move_right")
	main.feed_input = false
	ok(sim.player.x > x0 + 0.5, "the move_right action walks the player east (%.2f → %.2f)" % [x0, sim.player.x])
	key(KEY_TAB)
	await frames(2)
	ok(ui.panel_kind() == "notebook" and sim.paused, "Tab opens the notebook and pauses")
	key(KEY_TAB)
	await frames(2)
	ok(not ui.panel_open() and not sim.paused, "Tab closes it again")
	at("hub", 5, 21, 4, 21)
	key(KEY_E)
	await frames(2)
	ok(ui.panel_kind() == "shop", "E across the counter opens Mother Ladle's shop")
	ok(press_button("Buy Smoke Bomb"), "the shop lists a smoke bomb")
	ok(sim.merit == 15 and sim.player.tools["smoke"] == 3, "buying a smoke bomb spends 10 merit")
	press_button("Leave")
	await frames(1)

	_canon_combos()
	await shot("02-gallery-grease")
	_alibi_engine()
	_office_hours()
	_locks_and_relic()
	_act3()
	await shot("03-act3-night")
	_act3_countermeasures()
	sim.reveal_t = 8.0
	ticks(4)
	await shot("04-vault-reveal")
	_duel()
	await shot("05-duel")
	Talk.end_duel(sim)
	_trial()
	await shot("06-trial")
	ui.close_panel()
	await _playthrough()

	print("\n%d passed, %d failed" % [passes, failures])
	print("TESTS_OK" if failures == 0 else "TESTS_FAILED")
	get_tree().quit(1 if failures > 0 else 0)


func _map_integrity() -> void:
	var pairs_ok := sim.links.size() == 7
	for ch in sim.links.keys():
		if sim.links[ch].size() != 2:
			pairs_ok = false
	ok(pairs_ok, "every link digit pairs exactly once (%d links)" % sim.links.size())
	var bad: Array = []
	var unreachable: Array = []
	for g in sim.guards:
		if g.archmage:
			continue
		for pt in g.route:
			var m: GameMap = sim.maps[g.home]
			if not Pathfinder.guard_passable(m, int(pt[0]), int(pt[1]), null):
				bad.append("%s@%s" % [g.id, pt])
			var res := Pathfinder.find(sim, Content.world["tower_maps"], {"map": g.map_id, "x": floori(g.x), "y": floori(g.y)}, {"map": g.home, "x": int(pt[0]), "y": int(pt[1])}, Pathfinder.guard_passable, true)
			if not res["ok"]:
				unreachable.append("%s->%s" % [g.id, pt])
	ok(bad.is_empty(), "all guard waypoints are walkable %s" % [bad])
	ok(unreachable.is_empty(), "all guard waypoints are reachable %s" % [unreachable])
	# the player can reach the vault pedestal from the quad (doors passable, every link usable)
	var hs: Dictionary = Content.world["hub_start"]
	var start := "hub,%d,%d" % [hs["x"], hs["y"]]
	var seen := {start: true}
	var q: Array = [["hub", int(hs["x"]), int(hs["y"])]]
	var reached := false
	while not q.is_empty():
		var cur: Array = q.pop_front()
		var m: GameMap = sim.maps[cur[0]]
		if cur[0] == "f2" and absi(cur[1] - 37) <= 1 and absi(cur[2] - 24) <= 1:
			reached = true
			break
		var nb: Array = []
		for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
			nb.append([cur[0], cur[1] + d.x, cur[2] + d.y])
		var ch := m.tile(cur[1], cur[2])
		if C.is_link_ch(ch):
			var o := sim.link_other(ch, cur[0], cur[1], cur[2])
			if not o.is_empty():
				nb.append([o["map"], int(o["x"]), int(o["y"])])
		for n in nb:
			var k := "%s,%d,%d" % n
			var nm: GameMap = sim.maps[n[0]]
			if seen.has(k) or not nm.inb(n[1], n[2]):
				continue
			var t := nm.tile(n[1], n[2])
			if C.SOLID_CH.contains(t) and not "DLKH".contains(t):
				continue
			seen[k] = true
			q.append(n)
	ok(reached, "the vault pedestal is reachable from the quad")


func _canon_combos() -> void:
	# Grease + Gust curls a bust into a guard (environmental KO)
	var m: GameMap = sim.maps["f1"]
	at("f1", 18, 12, 20.5, 12)
	sim.player.mana = 100.0
	for g in sim.guards:
		if g.map_id == "f1":
			g.x = 40.5
			g.y = 25.5
			g.state = "patrol"
			GuardAI.clear_path(g)
			g.route = [[40, 25]]
	var tgt: Entities.Guard = sim.guards.filter(func(g): return g.id == "g6")[0]
	tgt.x = 24.5
	tgt.y = 12.5
	tgt.route = [[24, 12]]
	tgt.face = 0.0
	tgt.suspicion = 0.0
	Spells.grease(sim, m, 21, 12)
	Spells.grease(sim, m, 23, 12)
	sim.mouse_world = Vector2(21, 12.5)
	var env0: int = sim.tower["ledger"]["env_ko"]
	Spells.gust(sim, m)
	ticks(60)
	ok(tgt.ko > 0.0 and sim.tower["ledger"]["env_ko"] - env0 == 1, "Grease + Gust: a bust curls into a guard → environmental KO")
	ok(sim.tower["ledger"]["grease_casts"] == 2, "grease casts are counted in the Method Ledger (%d)" % sim.tower["ledger"]["grease_casts"])
	at("f1", 21, 13)
	# smoke + douse + freeze = ice-block seal
	for yy in range(16, 19):
		for xx in range(25, 28):
			if not m.is_solid(xx, yy):
				m.cloud[m.idx(xx, yy)] = C.C_SMOKE
				m.c_timer[m.idx(xx, yy)] = C.SMOKE_TIME
	Spells.douse(m, 26, 17)
	var fog: bool = m.cloud[m.idx(26, 17)] == C.C_FOG
	Spells.freeze(sim, m, 26, 17)
	ok(fog and m.is_solid(26, 17) and m.is_opaque(26, 17, true), "Smoke → Douse = wet fog → Freeze = solid, opaque ice block")
	# heat runes
	var i := m.idx(30, 13)
	m.rune[i] = 1
	m.cool[i] = 0.0
	Spells.grease(sim, m, 30, 13)
	var burn: bool = m.surface[i] == C.S_BURN
	Spells.douse(m, 30, 13)
	var steam: bool = m.cloud[i] == C.C_STEAM
	Spells.freeze(sim, m, 30, 13)
	var cooled: bool = m.cool[i] > 0.0
	m.rune[i] = 0
	m.cloud[i] = C.C_NONE
	ok(burn and steam and cooled, "heat rune: Grease → burning slick, Douse → steam, Freeze → cooled")
	# Silence
	sim.silences.append({"map": "f1", "x": 33.5, "y": 13.5, "t": 5.0})
	var g8: Entities.Guard = sim.guards.filter(func(g): return g.id == "g8")[0]
	g8.map_id = "f1"
	g8.x = 33.5
	g8.y = 9.5
	g8.state = "patrol"
	g8.ko = 0.0
	var heard := Perception.emit_noise(sim, "f1", 33.5, 13.5, 8.0, "glass", "player")
	sim.silences.clear()
	ok(not heard, "glass broken inside a Silence dome is not heard")


func _alibi_engine() -> void:
	at("hub", 24, 18)
	var studs: Array = sim.npcs.filter(func(n): return n.kind == "student").slice(0, 3)
	for k in studs.size():
		studs[k].x = 22.5 + k
		studs[k].y = 16.5
		studs[k].path = []
		studs[k].wait_t = 999.0
	ticks(240)   # let earlier teleports age out of the ±10 s window
	sim.heat = 30.0
	var g9: Entities.Guard = sim.guards.filter(func(g): return g.id == "g9")[0]
	g9.map_id = "f2"
	g9.x = 35.5
	g9.y = 12.5
	g9.state = "patrol"
	g9.ko = 0.0
	Alibi.create_incident(sim, "f1", 35.5, 13.5)
	ok(g9.state == "investigate", "the Vacuum pulls the vault warden down a floor to investigate")
	ticks(230)
	ok(sim.heat < 20.0 and str(sim.notebook["log"][0]).begins_with("✔ ALIBI"), "three student witnesses clear the incident (heat %.1f)" % sim.heat)
	at("f0", 3, 3)
	sim.heat = 10.0
	ticks(20)
	var nd: int = sim.tower["ledger"]["noise_distractions"]
	Alibi.create_incident(sim, "f0", 8.5, 4.5)
	ticks(230)
	ok(sim.heat >= 29.0 and sim.tower["ledger"]["noise_distractions"] - nd == 2 and str(sim.notebook["log"][0]).begins_with("✘"),
		"no witnesses → Heat +20 and an extra ledger mark (heat %.1f)" % sim.heat)


func _office_hours() -> void:
	sim.hub_clock = 10 * 60 + 5
	ticks(1)
	var gn := HubNpcs.find(sim, "gilt")
	var a := [HubNpcs.present(sim, gn), sim.gilt.away]
	sim.hub_clock = 10 * 60 + 40
	ticks(1)
	var b := [HubNpcs.present(sim, gn), sim.gilt.away]
	ok(a[0] and a[1] and not b[0] and not b[1], "office hours (:00–:30) put Gilt at the pavilion and empty her study")
	sim.hub_clock = 11 * 60 + 2
	ticks(1)
	at("hub", floori(gn.x) + 1, floori(gn.y))
	Talk.start_convo(sim)
	ticks(10)
	var e: Dictionary = sim.witness_log[sim.witness_log.size() - 1]
	var cred := 0
	for w in e["wits"]:
		if w["kind"] == "archmage":
			cred += int(w["cred"])
	Talk.end_convo(sim, "")
	ok(cred == 4, "an Archmage talking at you counts as credibility 4 (%d)" % cred)


func _locks_and_relic() -> void:
	var m: GameMap = sim.maps["f1"]
	at("f1", 26, 23)
	var before: int = sim.tower["ledger"]["magehand_locks"]
	Interact.start_lock(sim, m, 24, 23, true)
	var guard := 0
	while not sim.lock.is_empty() and guard < 400:
		guard += 1
		sim.tick()
		if Interact.lock_glow(sim) > 0.9:
			Interact.lock_press(sim)
	ok(m.tile(24, 23) == "O" and sim.tower["ledger"]["magehand_locks"] - before == 1, "Mage Hand lockpicking opens the pantry door and is logged")
	at("f0", 18, 25)
	sim.player.carrying = "phoenix"
	sim.tower["relic"] = "player"
	Interact.use_link(sim, "3", "f0", 18, 25)
	ok(sim.player.map_id == "f0", "the Phoenix will not fit in the dumbwaiter")
	sim.player.carrying = ""
	sim.tower["relic"] = "pedestal"


func _act3() -> void:
	sim.tower["ledger"].merge({"melee_ko": 2, "alerts": 1, "grease_casts": 3, "magehand_locks": 2, "noise_distractions": 3}, true)
	sim.player.carrying = "phoenix"
	Flow.complete_act1(sim)
	var cms: Array = sim.tower["countermeasures"].duplicate()
	ok(ui.panel_kind() == "act1_summary", "the Act 1 summary panel opens")
	ui.close_panel()
	Flow.start_act3(sim)
	var gs: Array = sim.guards.filter(func(g): return not g.archmage)
	var runes := 0
	for id in ["f1", "f2"]:
		for v in sim.maps[id].rune:
			runes += v
	ok(", ".join(cms) == "helmets, heatRunes, sap, earmuffs", "the ledger buys the right countermeasures (%s)" % ", ".join(cms))
	ok(sim.stage == "act3" and sim.night and sim.player.carrying == "phoenix" and sim.gilt.asleep, "Act 3 starts at night, carrying the relic, Gilt asleep")
	ok(gs.all(func(g): return g.helmet and g.earmuffs and g.cleats) and runes == 9 and sim.maps["f1"].sapped.size() + sim.maps["f2"].sapped.size() == 2,
		"countermeasures applied (runes %d)" % runes)
	ok(sim.notices.size() > 3, "the notice board carries the Pride Cover-Up announcements")
	ticks(40)


func _act3_countermeasures() -> void:
	var g3: Entities.Guard = sim.guards.filter(func(g): return g.id == "g3")[0]
	sim.player.map_id = g3.map_id
	sim.player.x = g3.x - cos(g3.face) * 0.9
	sim.player.y = g3.y - sin(g3.face) * 0.9
	Interact.takedown(sim, g3)
	ok(g3.ko <= 0.0 and g3.state == "pursuit", "bucket helmets: the crowbar fails and the guard turns on you")
	var g6: Entities.Guard = sim.guards.filter(func(g): return g.id == "g6")[0]
	g6.state = "patrol"
	ok(not Perception.emit_noise(sim, g6.map_id, g6.x + 1, g6.y, 10.0, "plant", "player"), "earmuffs: guards are deaf to a noisemaker right next to them")
	sim.paused = false
	at("f2", 37, 22)
	sim.maps["f2"].set_tile(37, 18, "O")
	sim.tower["relic"] = "player"
	sim.player.carrying = "phoenix"
	for g in sim.guards:
		if not g.archmage:
			g.x = 40.5
			g.y = 12.5
			g.map_id = "f1"
	Interact.place_relic(sim)
	var before: bool = sim.tower["vault_alert"]
	at("f2", 37, 20)
	sim.tick()
	ok(sim.tower["relic"] == "pedestal" and not before and sim.tower["vault_alert"], "tripping a vault ward-line in Act 3 marks the Return Trip as loud")


func _duel() -> void:
	sim.night = false
	sim.set_day_flags()
	sim.stage = "intermission"
	sim.tower["relic"] = "owned"
	sim.player.carrying = ""
	at("hub", 20, 19)
	sim.notebook["comebacks"] = ["diet"]
	sim.notebook["roasts"] = ["int1", "fash1"]
	var perc: Entities.Npc = sim.npcs.filter(func(n): return n.id == "percival")[0]
	Talk.start_duel(sim, perc)
	Talk.duel_answer(sim, "")
	var learned: bool = sim.notebook["comebacks"].has("spellcraft")
	Talk.duel_flex(sim)
	Talk.duel_answer(sim, "diet")
	ok(learned and sim.attuned and sim.notebook["comebacks"].has("relic"), "duels teach counters on a loss; flexing the Phoenix attunes it")


func _trial() -> void:
	sim.notebook["comebacks"] = ["spellcraft", "fashion", "intellect", "lineage", "diet", "relic"]
	sim.tower["return_clean"] = true
	sim.attuned = true
	Talk.start_trial(sim)
	var q: Array = sim.trial["q"].map(func(r): return "insider" if r.get("insider", false) else r["topic"])
	ok(q[2] == "insider", "a clean Return Trip puts Gilt's Phoenix flex into the trial")
	ok(press_button("“At least mine apologizes"), "trial answers are buttons")
	Talk.trial_answer(sim, "slam")
	Talk.trial_answer(sim, "insider")
	ok(sim.trial["ego"] <= 30, "insider line + punctuation hit hard (ego %d)" % sim.trial["ego"])
	sim.notebook["comebacks"] = ["spellcraft", "fashion", "intellect", "lineage", "diet"]
	sim.tower["return_clean"] = false
	sim.attuned = false
	Talk.start_trial(sim)
	for r in sim.trial["q"].duplicate():
		if sim.trial["done"] != "":
			break
		Talk.trial_answer(sim, r["topic"])
	ok(sim.trial["done"] == "shattered", "five right comebacks shatter Gilt without insider help")


## The whole chapter through the real E prompts, guards disabled (port of the web e2e run).
func _playthrough() -> void:
	sim.init_world()
	sim.stage = "act1"
	sim.paused = false
	sim.night = false
	sim.dawn = false
	sim.tower = {"ledger": {"melee_ko": 0, "env_ko": 0, "alerts": 0, "grease_casts": 0, "magehand_locks": 0, "noise_distractions": 0},
		"countermeasures": [], "relic": "pedestal", "return_clean": null, "vault_alert": false, "act1_done": false, "act3_done": false}
	sim.notebook = {"roasts": ["int1", "fash1"], "comebacks": ["diet"], "log": []}
	sim.attuned = false
	sim.merit = 25
	sim.set_day_flags()
	var log: Array = []
	var neuter := func():
		for g in sim.guards:
			if not g.archmage:
				g.ko = 1e9
	var e := func(expect: String) -> void:
		var it := Interact.find(sim)
		var label: String = it.get("label", "NONE")
		log.append(label)
		if not label.to_lower().contains(expect.to_lower()):
			ok(false, "playthrough expected '%s', got '%s'" % [expect, label])
		if not it.is_empty():
			it["run"].call()
		sim.tick()
	var pick := func():
		var n := 0
		while not sim.lock.is_empty() and n < 500:
			n += 1
			sim.tick()
			if Interact.lock_glow(sim) > 0.9:
				Interact.lock_press(sim)
	neuter.call()
	at("hub", 42, 12); e.call("gate")
	at("f0", 8, 27); e.call("pry"); e.call("vent")
	ok(sim.player.map_id == "f0" and floori(sim.player.x) == 28, "the sewer vent leads into the servant hall")
	at("f0", 18, 25); e.call("dumbwaiter")
	at("f1", 22, 25); e.call("servant stair")
	sim.hub_clock = 10 * 60 + 2
	ticks(1)
	at("f2", 29, 21, 30, 21); sim.reveal_t = 8.0; e.call("snip")
	at("f2", 25, 19, 25, 18); e.call("pick the lock"); pick.call()
	at("f2", 30, 12, 31, 12); e.call("open door")
	at("f2", 37, 17, 37, 18); e.call("vault door")
	at("f2", 37, 23, 37, 24); e.call("take the phoenix")
	at("f2", 22, 25); e.call("servant stair")
	at("f1", 25, 23, 24, 23); e.call("pick the lock"); pick.call()
	at("f1", 26, 21, 26, 20); e.call("open door")
	at("f1", 26, 16, 26, 15); e.call("open door")
	at("f1", 27, 13); e.call("main stairs")
	at("f0", 17, 16, 16, 16); e.call("open door")
	at("f0", 1, 16); e.call("gate")
	ok(sim.stage == "intermission" and sim.tower["countermeasures"] == ["trueSight"], "a ghost run ends Act 1 and buys only true-sight (%s)" % [sim.tower["countermeasures"]])
	ui.close_panel()
	for n in sim.npcs.filter(func(n): return n.kind == "snob"):
		at("hub", floori(n.x) + 1, floori(n.y)); e.call("roast")
	for id in ["percival", "cressida"]:
		var n: Entities.Npc = sim.npcs.filter(func(x): return x.id == id)[0]
		at("hub", floori(n.x) + 1, floori(n.y)); e.call("duel")
		var guard := 0
		while not sim.duel.is_empty() and not sim.duel["over"] and guard < 20:
			guard += 1
			if sim.duel["cur"]["by"] == "player":
				if sim.duel["can_flex"]:
					Talk.duel_flex(sim)
				else:
					Talk.duel_throw(sim, sim.notebook["roasts"][0])
			else:
				var r := Content.roast(sim.duel["cur"]["roast"])
				Talk.duel_answer(sim, r["topic"] if sim.notebook["comebacks"].has(r["topic"]) else "")
		Talk.end_duel(sim)
	ok(sim.notebook["comebacks"].size() == 6 and sim.attuned, "snobs and duels fill the notebook (%s)" % [sim.notebook["comebacks"]])
	at("hub", 42, 12); e.call("gate")
	ok(ui.panel_kind() == "confirm_return", "the Sunspire gate offers the Return Trip")
	ok(press_button("Go tonight"), "Go tonight starts Act 3")
	neuter.call()
	at("f0", 17, 16, 16, 16); e.call("open door")
	at("f0", 27, 13); e.call("main stairs")
	at("f1", 42, 13); e.call("upper stairs")
	at("f2", 37, 17, 37, 18); e.call("vault door")
	sim.maps["f2"].tripwires_off = true
	at("f2", 37, 23, 37, 24); e.call("place")
	at("f2", 42, 13); e.call("upper stairs")
	at("f1", 27, 13); e.call("main stairs")
	at("f0", 1, 16); e.call("gate")
	ok(sim.stage == "trial" and sim.tower["return_clean"] == true and ui.panel_kind() == "trial", "a clean return opens the trial")
	var guard2 := 0
	while sim.trial["done"] == "" and guard2 < 10:
		guard2 += 1
		var r: Dictionary = sim.trial["q"][sim.trial["i"]]
		Talk.trial_answer(sim, "insider" if r.get("insider", false) else (r["topic"] if sim.notebook["comebacks"].has(r["topic"]) else ""))
	ok(sim.trial["done"] == "shattered", "the trial shatters Gilt (ego %d)" % sim.trial["ego"])
	ok(press_button("Continue"), "Continue leaves the trial")
	ok(sim.stage == "end" and sim.seats["gilt"] == "for" and ui.panel_kind() == "end", "the chapter ends with Gilt's seat won")
	await shot("07-end")
