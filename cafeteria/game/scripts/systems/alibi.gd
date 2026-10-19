class_name Alibi
## The Alibi Engine (spec §6, rules as built in §17.2): witness ledger, incidents, the Vacuum.


static func sample_witnesses(sim: Sim) -> void:
	var p := sim.player
	var m := sim.cur_map()
	var wits: Array = []
	if p.map_id == "hub" and not sim.dead:
		var in_cafeteria: bool = m.interior[m.idx(floori(p.x), floori(p.y))] == 1
		for n in sim.npcs:
			if not HubNpcs.present(sim, n) or (n.kind == "ladle" and not in_cafeteria):
				continue
			var d := Vector2(n.x - p.x, n.y - p.y).length()
			if d > C.WITNESS_RANGE or not m.ray_clear(n.x, n.y, p.x, p.y, true):
				continue
			var cred := 1
			var kind := "student"
			if n.kind == "prefect":
				cred = 2
				kind = "prefect"
			elif n.kind == "gilt":
				if sim.convo.is_empty():
					continue
				cred = 4
				kind = "archmage"
			elif n.kind == "ladle":
				cred = 2
				kind = "faculty"
			elif n.spectator_spot != null:
				kind = "spectator"
			wits.append({"id": n.id, "name": n.display_name, "kind": kind, "cred": cred})
	sim.witness_log.append({"t": sim.time, "map": p.map_id, "x": p.x, "y": p.y, "building": m.building, "floor": m.floor_index, "wits": wits})
	while not sim.witness_log.is_empty() and sim.witness_log[0]["t"] < sim.time - C.WITNESS_KEEP:
		sim.witness_log.pop_front()


static func create_incident(sim: Sim, map_id: String, x: float, y: float) -> void:
	var m: GameMap = sim.maps[map_id]
	sim.incidents.append({"t": sim.time, "map": map_id, "x": x, "y": y, "building": m.building, "floor": m.floor_index, "checked": false})
	sim.tower["ledger"]["noise_distractions"] += 1      # a distraction was used (spec §7.1)
	if not sim.convo.is_empty():
		sim.convo["incident"] = true
	var pulled := 0
	for g in sim.guards:
		if g.archmage or g.ko > 0.0 or g.sliding or g.earmuffs or g.away:
			continue
		var gm: GameMap = sim.maps[g.map_id]
		if gm.building != m.building:
			continue
		var d := Vector2(g.x - x, g.y - y).length() + C.FLOOR_DIST * absi(gm.floor_index - m.floor_index)
		if d > C.VACUUM_RADIUS:
			continue
		g.state = "investigate"
		g.inv_until = sim.time + C.VACUUM_TIME
		GuardAI.set_goal(sim, g, {"map": map_id, "x": floori(x), "y": floori(y)})
		pulled += 1
	sim.log_note("Incident on %s — %d guard%s pulled off post (the Vacuum)." % [m.display_name, pulled, "" if pulled == 1 else "s"])


static func run(sim: Sim, inc: Dictionary) -> void:
	inc["checked"] = true
	var best := 0
	var best_wits: Array = []
	var at_scene := false
	for e in sim.witness_log:
		if absf(e["t"] - inc["t"]) > C.ALIBI_WINDOW:
			continue
		var far: bool = e["building"] != inc["building"] or \
			Vector2(e["x"] - inc["x"], e["y"] - inc["y"]).length() + C.FLOOR_DIST * absi(e["floor"] - inc["floor"]) >= C.ALIBI_MIN_DIST
		if not far:
			at_scene = true
			continue
		var seen := {}
		for w in e["wits"]:
			seen[w["id"]] = w
		var score := 0
		for w in seen.values():
			score += int(w["cred"])
		if score > best:
			best = score
			best_wits = seen.values()
	# being placed near the scene at any point inside the window voids the alibi — you can't be in two places
	if at_scene:
		best = 0
		best_wits = []
	var names := ", ".join(best_wits.map(func(w): return "%s (%s, %d)" % [w["name"], w["kind"], w["cred"]]))
	if best >= C.ALIBI_CLEAR:
		sim.add_heat(-15.0, "ALIBI — cleared")
		sim.toast("✔ ALIBI: %d witness%s swear you were elsewhere." % [best_wits.size(), "es" if best_wits.size() > 1 else ""], Color("9fd89a"), 5.0)
		sim.log_note("✔ ALIBI (score %d): %s." % [best, names])
	elif best > 0:
		sim.add_heat(5.0, "shaky alibi")
		sim.log_note("~ SHAKY ALIBI (score %d): %s. Somebody saw you, but nobody important." % [best, names])
	else:
		sim.add_heat(20.0, "no alibi for the incident")
		if sim.in_tower_stage():
			sim.tower["ledger"]["noise_distractions"] += 1
		sim.log_note("✘ NO ALIBI. Nobody can place you anywhere else.")
