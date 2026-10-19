class_name Interact
## The E key: relic, takedowns, links, hub people, doors, locks (spec §5.4), windows, wires, housings.
## find() returns {"label": String, "run": Callable} or {} — the HUD shows the label, E calls run.


static func _adjacent_tiles(sim: Sim) -> Array:
	var p := sim.player
	var px := floori(p.x)
	var py := floori(p.y)
	var out: Array = []
	for dy in range(-1, 2):
		for dx in range(-1, 2):
			if dx == 0 and dy == 0:
				continue
			var x := px + dx
			var y := py + dy
			out.append({"x": x, "y": y, "score": sim.mouse_world.distance_to(Vector2(x + 0.5, y + 0.5))})
	out.sort_custom(func(a, b): return a["score"] < b["score"])
	return out


static func _act(label: String, fn: Callable) -> Dictionary:
	return {"label": label, "run": fn}


static func find(sim: Sim) -> Dictionary:
	var p := sim.player
	var m := sim.cur_map()
	if sim.dead or not sim.duel.is_empty():
		return {}
	var px := floori(p.x)
	var py := floori(p.y)
	var near := _adjacent_tiles(sim)
	# the relic
	for t in near:
		if m.tile(t["x"], t["y"]) != "P":
			continue
		if p.carrying != "" and sim.tower["relic"] == "player":
			return _act("Place the Phoenix back on its pedestal", func(): place_relic(sim))
		if p.carrying == "" and sim.tower["relic"] == "pedestal":
			return _act("Take the Phoenix", func(): take_relic(sim))
	if p.carrying == "":
		for o in m.objects:
			if o.kind == "relic" and Vector2(o.x - p.x, o.y - p.y).length() < 1.4:
				return _act("Pick the Phoenix back up", func():
					m.objects.erase(o)
					p.carrying = "phoenix"
					sim.tower["relic"] = "player")
	# takedown
	for g in sim.guards:
		if g.map_id != p.map_id or g.archmage or g.away or g.ko > 0.0 or g.sliding:
			continue
		if Vector2(g.x - p.x, g.y - p.y).length() > 1.25 or g.state == "pursuit":
			continue
		var behind := absf(C.ang_diff(g.face, atan2(p.y - g.y, p.x - g.x))) > deg_to_rad(100.0)
		if behind or g.slip > 0.0:
			return _act("Crowbar takedown — " + g.display_name, func(): takedown(sim, g))
	# a link under the player
	var here := m.tile(px, py)
	if C.is_link_ch(here) and Content.world["links"].has(here):
		var link: Dictionary = Content.world["links"][here]
		var label: String = {"gate": "Go through the gate", "stairs": "Take the " + str(link["label"]).to_lower(),
			"dumbwaiter": "Squeeze into the dumbwaiter", "trellis": "Climb the ivy trellis", "vent": "Crawl through the sewer vent"}[link["kind"]]
		if link["kind"] == "vent" and sim.link_state.get(here, {}).get("locked", true):
			label = "Pry open the vent grate (crowbar)"
		return _act(label, func(): use_link(sim, here, p.map_id, px, py))
	# hub people
	if p.map_id == "hub":
		var best_n = null
		var bd := 1.7
		for n in sim.npcs:
			if not HubNpcs.present(sim, n):
				continue
			var d := Vector2(n.x - p.x, n.y - p.y).length() - (1.8 if n.kind == "ladle" else 0.0)   # she serves across the counter
			if d < bd:
				bd = d
				best_n = n
		if best_n != null:
			var n = best_n
			match n.kind:
				"ladle": return _act("Talk to Mother Ladle", func(): sim.ui_request.emit("shop", {}))
				"snob": return _act("Roast " + n.display_name, func(): Talk.talk_snob(sim, n))
				"duelist": return _act("Challenge %s to a duel" % n.display_name, func(): Talk.start_duel(sim, n))
				"gilt": return _act("Keep listening to Archmage Gilt" if not sim.convo.is_empty() else "Attend Archmage Gilt's office hours", func(): Talk.start_convo(sim))
				"student": return _act("Chat", func(): sim.toast("Student: \"%s\"" % n.line, Color("e8e1cf"), 5.0))
				"prefect": return _act("Greet the prefect", func(): sim.toast("Prefect Dunmore: \"I'm not following you. I'm walking near you, persistently.\"", Color("e8e1cf"), 5.0))
	# adjacent tiles
	for t in near:
		var tx: int = t["x"]
		var ty: int = t["y"]
		if not m.inb(tx, ty):
			continue
		var ch := m.tile(tx, ty)
		var i := m.idx(tx, ty)
		var door_r := 1.0 if p.posture == "sneak" else 3.0
		match ch:
			"n":
				return _act("Read the notice board", func(): sim.ui_request.emit("notices", {}))
			"D":
				return _act("Open door", func():
					m.set_tile(tx, ty, "O")
					Perception.emit_noise(sim, m.id, tx + 0.5, ty + 0.5, door_r, "door", "player"))
			"O":
				if not sim.entity_on_tile(m.id, tx, ty):
					return _act("Close door", func():
						m.set_tile(tx, ty, "D")
						Perception.emit_noise(sim, m.id, tx + 0.5, ty + 0.5, door_r, "door", "player"))
			"L":
				var sapped_label := "Pick the sapped lock (by hand)" if (m.sapped.has(i) and sim.is_revealed(m.id, tx, ty)) else "Pick the lock"
				return _act(sapped_label, func(): start_lock(sim, m, tx, ty, false))
			"K":
				return _act("Open the vault door (master key)", func():
					m.set_tile(tx, ty, "O")
					Perception.emit_noise(sim, m.id, tx + 0.5, ty + 0.5, 3.0, "door", "player")
					sim.toast("The Clocktower key turns. The vault door sighs open.", Color("e0b44c")))
			"H":
				if sim.is_revealed(m.id, tx, ty):
					return _act("Open the hidden door", func(): m.set_tile(tx, ty, "O"))
			"W":
				if p.tools["glassCutter"] > 0:
					return _act("Cut the window pane silently (%d left)" % p.tools["glassCutter"], func():
						p.tools["glassCutter"] -= 1
						m.set_tile(tx, ty, ".")
						sim.toast("A neat circle of glass, lifted out without a sound."))
				return _act("Smash the window", func():
					m.set_tile(tx, ty, ".")
					Perception.emit_noise(sim, m.id, tx + 0.5, ty + 0.5, 8.0, "glass", "player"))
			"h":
				if sim.is_revealed(m.id, tx, ty) and not m.tripwires_off:
					if p.tools["snips"] > 0:
						return _act("Snip the rune housing (disables this floor's ward-lines)", func():
							p.tools["snips"] -= 1
							m.tripwires_off = true
							m.revision += 1
							sim.toast("The housing sparks and dies. The ward-lines go dark.", Color("9fd89a")))
					return _act("Rune housing — you need wire-snips", func(): pass)
			"-":
				if p.tools["snips"] > 0:
					return _act("Cut the tripwire", func():
						p.tools["snips"] -= 1
						m.set_tile(tx, ty, ".")
						m.wire_moved.erase(i))
		if m.ice_block[i] > 0.0:
			return _act("Shatter the ice wall (crowbar)", func():
				m.ice_block[i] = 0.0
				m.light_dirty = true
				m.revision += 1
				Perception.emit_noise(sim, m.id, tx + 0.5, ty + 0.5, 6.0, "shatter", "player"))
	return {}


static func takedown(sim: Sim, g: Entities.Guard) -> void:
	if g.helmet:
		Perception.emit_noise(sim, g.map_id, g.x, g.y, 4.0, "clank", "player")
		g.face = atan2(sim.player.y - g.y, sim.player.x - g.x)
		g.suspicion = 100.0
		GuardAI.go_alert(sim, g, "player")
		sim.toast("CLONK. A bucket helmet. He turns around, slowly.", Color("ff9d7a"))
		return
	g.ko = C.KO_TIME
	GuardAI.clear_path(g)
	g.slip = 0.0
	if sim.in_tower_stage():
		sim.tower["ledger"]["melee_ko"] += 1
	Perception.emit_noise(sim, g.map_id, g.x, g.y, 4.0, "thud", "player")
	sim.toast("%s folds up quietly." % g.display_name, Color("9fd89a"))


static func take_relic(sim: Sim) -> void:
	sim.player.carrying = "phoenix"
	sim.tower["relic"] = "player"
	sim.toast("You lift the Radiant Resuscitation of the Eternal Sun. It is enormous. It is gold. It hums.", Color("e0b44c"), 5.0)


static func place_relic(sim: Sim) -> void:
	sim.player.carrying = ""
	sim.tower["relic"] = "pedestal"
	sim.toast("Back where it lives. Now get out.", Color("e0b44c"), 4.0)


static func stash_relic(sim: Sim) -> void:
	var p := sim.player
	if p.carrying == "":
		return
	var m := sim.cur_map()
	m.objects.append(WorldObject.new("relic", "the Phoenix", 8.0, p.x, p.y, m.id))
	p.carrying = ""
	sim.tower["relic"] = "stashed"
	sim.toast("You set the Phoenix down. Gently. It is still humming.")


static func use_link(sim: Sim, ch: String, map_id: String, x: int, y: int) -> void:
	var link: Dictionary = Content.world["links"][ch]
	var p := sim.player
	if link["kind"] == "vent" and sim.link_state.get(ch, {}).get("locked", true):
		if p.tools["crowbar"] <= 0:
			sim.toast("The grate is rusted shut.")
			return
		sim.link_state[ch] = {"locked": false}
		Perception.emit_noise(sim, map_id, x + 0.5, y + 0.5, 3.0, "pry", "player")
		sim.toast("The grate comes away with a wet scrape.")
		return
	if p.carrying != "" and ["trellis", "dumbwaiter", "vent"].has(link["kind"]):
		sim.toast("The Phoenix will not fit through the %s. Stairs and doors only, with a relic this size." % str(link["label"]).to_lower(), Color("e0b44c"), 4.0)
		return
	if link["kind"] == "gate" and not Flow.gate_allowed(sim, map_id):
		return
	var o := sim.link_other(ch, map_id, x, y)
	if o.is_empty():
		return
	var noise := float(link.get("noise", 0))
	if noise > 0.0:
		Perception.emit_noise(sim, map_id, x + 0.5, y + 0.5, noise, "creak", "player")
	if not p.held.is_empty():
		Spells.drop_held(sim, floori(p.x), floori(p.y))
	sim.lock = {}
	for g in sim.guards:
		if g.state == "pursuit" and g.lost_t < 1.0 and link["guards"] and g.map_id == map_id:
			g.last_seen = {"map": o["map"], "x": o["x"], "y": o["y"]}
	p.map_id = o["map"]
	p.x = o["x"] + 0.5
	p.y = o["y"] + 0.5
	p.vx = 0.0
	p.vy = 0.0
	p.last_tile = -1
	if noise > 0.0:
		Perception.emit_noise(sim, o["map"], p.x, p.y, noise, "creak", "player")
	sim.camera_snap.emit()
	sim.toast(sim.maps[o["map"]].display_name, Color("e0b44c"), 2.2)
	if link["kind"] == "gate":
		Flow.on_gate_passed(sim, map_id, o["map"])


# ---------- locks (spec §5.4) ----------
static func start_lock(sim: Sim, m: GameMap, x: int, y: int, magehand: bool) -> void:
	sim.lock = {"map": m.id, "x": x, "y": y, "pins": 3, "set": 0, "t": 0.0, "period": 1.2 * (1.5 if magehand else 1.0),
		"jam": 0.0, "magehand": magehand, "phase": [randf(), randf(), randf()]}
	sim.toast("Mage Hand works the lock. Press E as each pin glows brightest." if magehand else "Picking. Press E as each pin glows brightest. Moving cancels.")


static func lock_glow(sim: Sim) -> float:
	var l := sim.lock
	if l.is_empty():
		return 0.0
	return 0.5 - 0.5 * cos(TAU * (l["t"] / l["period"] + l["phase"][l["set"]]))


static func lock_press(sim: Sim) -> void:
	var l := sim.lock
	if l.is_empty() or l["jam"] > 0.0:
		return
	if lock_glow(sim) > 0.82:
		l["set"] += 1
		sim.sfx.emit("pin", 0.0)
		if l["set"] >= l["pins"]:
			var m: GameMap = sim.maps[l["map"]]
			m.set_tile(l["x"], l["y"], "O")
			if l["magehand"] and sim.in_tower_stage() and m.building == "sunspire":
				sim.tower["ledger"]["magehand_locks"] += 1
			sim.toast("Click. The lock gives.", Color("9fd89a"))
			sim.lock = {}
	else:
		l["jam"] = 1.0
		sim.sfx.emit("jam", 0.0)
		Perception.emit_noise(sim, l["map"], l["x"] + 0.5, l["y"] + 0.5, 1.0, "jam", "player")


static func update_lock(sim: Sim) -> void:
	var l := sim.lock
	if l.is_empty():
		return
	l["t"] += C.DT
	if l["jam"] > 0.0:
		l["jam"] -= C.DT
	if sim.player.map_id != l["map"]:
		sim.lock = {}
