class_name GuardAI
## Guard state machine (spec §4.4) and Archmage Gilt (spec §11.3).


static func make_guard(d: Dictionary, is_night: bool, cms: Array) -> Entities.Guard:
	var g := Entities.Guard.new()
	var route: Array = d["night"] if (is_night and d.has("night")) else d["route"]
	g.id = d["id"]
	g.display_name = d["name"]
	g.map_id = d["map"]
	g.home = d["map"]
	g.route = route
	g.x = route[0][0] + 0.5
	g.y = route[0][1] + 0.5
	g.face = float(d["night_face"]) if (is_night and d.has("night_face")) else float(d.get("face", 0.0))
	g.sweep_base = g.face
	g.sweep_t = randf() * 6.0
	g.helmet = is_night and cms.has("helmets")
	g.earmuffs = is_night and cms.has("earmuffs")
	g.true_sight = is_night and cms.has("trueSight")
	g.cleats = is_night and cms.has("heatRunes")
	return g


static func make_gilt(is_night: bool) -> Entities.Guard:
	var p: Dictionary = Content.world["gilt_tower_pos"]
	var g := Entities.Guard.new()
	g.id = "gilt"
	g.display_name = "Archmage Ostentia Gilt"
	g.archmage = true
	g.map_id = p["map"]
	g.home = p["map"]
	g.x = p["x"] + 0.5
	g.y = p["y"] + 0.5
	g.face = float(p["face"])
	g.sweep_base = g.face
	g.state = "sentry"
	g.asleep = is_night
	g.route = [[p["x"], p["y"]]]
	return g


static func clear_path(g) -> void:
	g.has_path = false
	g.path = []


static func set_goal(sim: Sim, g, goal: Dictionary) -> void:
	g.goal = goal
	var res := Pathfinder.find(sim, Content.world["tower_maps"], {"map": g.map_id, "x": floori(g.x), "y": floori(g.y)}, goal, Pathfinder.guard_passable, true)
	g.has_path = res["ok"]
	g.path = res["path"]
	g.repath_t = 1.0


static func start_search(sim: Sim, g, at: Dictionary, loud: bool = false) -> void:
	g.state = "search"
	g.stim = at
	g.search_t = C.SEARCH_TIME if loud else C.SEARCH_TIME * 0.75
	g.search_phase = "goto"
	set_goal(sim, g, at)


static func start_return(sim: Sim, g) -> void:
	g.state = "return"
	set_goal(sim, g, {"map": g.home, "x": int(g.route[g.wp][0]), "y": int(g.route[g.wp][1])})


static func go_alert(sim: Sim, g, why: String) -> void:
	if g.alert_cooldown > 0.0:
		return
	g.alert_cooldown = 5.0
	Perception.emit_noise(sim, g.map_id, g.x, g.y, 8.0 if g.archmage else 6.0, "shout", "guard")
	if sim.in_tower_stage():
		sim.tower["ledger"]["alerts"] += 1
		if sim.stage == "act3" and g.map_id == "f2":
			sim.tower["vault_alert"] = true
	if why == "player":
		sim.add_heat(30.0 if g.archmage else 10.0, "Archmage Gilt saw you" if g.archmage else "identified by a guard")
		if not g.archmage:
			g.state = "pursuit"
			g.lost_t = 0.0
			clear_path(g)
			g.repath_t = 0.0
		else:
			g.suspicion = 50.0
		sim.sfx.emit("alert", 0.0)


## Move along the path; true when the path is exhausted (or there is none).
static func step_along_path(sim: Sim, g, speed: float) -> bool:
	if not g.has_path or g.path.is_empty():
		return true
	var n: Dictionary = g.path[0]
	var m: GameMap = sim.maps[n["map"]]
	if n["map"] != g.map_id:   # crossing a link (stairs)
		g.map_id = n["map"]
		g.x = n["x"] + 0.5
		g.y = n["y"] + 0.5
		g.path.pop_front()
		return g.path.is_empty()
	var nx: int = n["x"]
	var ny: int = n["y"]
	if m.tile(nx, ny) == "D":
		m.set_tile(nx, ny, "O")
		Perception.emit_noise(sim, n["map"], nx + 0.5, ny + 0.5, 2.0, "door", "guard")
	if not Pathfinder.guard_passable(m, nx, ny, null):
		g.blocked_t += C.DT
		if g.repath_t <= 0.0:
			set_goal(sim, g, g.goal)
		_try_shatter_adjacent_ice(sim, g)
		return false
	var tx := nx + 0.5
	var ty := ny + 0.5
	var dx: float = tx - g.x
	var dy: float = ty - g.y
	var d := sqrt(dx * dx + dy * dy)
	var step := speed * C.DT
	if d > 0.01:
		g.face = C.turn_toward(g.face, atan2(dy, dx), 9.0)
	if d <= step:
		g.x = tx
		g.y = ty
		g.path.pop_front()
		g.blocked_t = 0.0
		_on_enter_tile(sim, g, m, nx, ny)
	else:
		g.x += dx / d * step
		g.y += dy / d * step
	return g.path.is_empty()


static func _try_shatter_adjacent_ice(sim: Sim, g) -> void:
	if g.blocked_t < 8.0:
		return
	var m: GameMap = sim.maps[g.map_id]
	var gx := floori(g.x)
	var gy := floori(g.y)
	for dy in range(-1, 2):
		for dx in range(-1, 2):
			var x := gx + dx
			var y := gy + dy
			if m.inb(x, y) and m.ice_block[m.idx(x, y)] > 0.0:
				m.ice_block[m.idx(x, y)] = 0.0
				m.light_dirty = true
				Perception.emit_noise(sim, g.map_id, x + 0.5, y + 0.5, 6.0, "shatter", "guard")
				g.blocked_t = 0.0
				clear_path(g)
				g.repath_t = 0.0
				return


static func _on_enter_tile(sim: Sim, g, m: GameMap, x: int, y: int) -> void:
	var i := m.idx(x, y)
	if m.tiles[i] == "-" and m.wire_moved.has(i):
		m.wire_moved.erase(i)
		Perception.emit_noise(sim, m.id, x + 0.5, y + 0.5, 8.0, "movedwire", "player")
		sim.toast("A guard trips your relocated wire. *BRRRING*", Color("a58bd8"))


static func speed_for(g) -> float:
	match g.state:
		"pursuit": return C.GUARD_SPEED["pursuit"]
		"investigate": return C.GUARD_SPEED["investigate"]
		"search": return C.GUARD_SPEED["search"]
		"return": return C.GUARD_SPEED["return"]
	return C.GUARD_SPEED["patrol"]


static func _here(g) -> Dictionary:
	return {"map": g.map_id, "x": floori(g.x), "y": floori(g.y)}


static func update(sim: Sim, g) -> void:
	if g.archmage:
		_update_archmage(sim, g)
		return
	if g.alert_cooldown > 0.0:
		g.alert_cooldown -= C.DT
	if g.ko > 0.0:
		g.ko -= C.DT
		if g.ko <= 0.0:
			g.ko = 0.0
			g.suspicion = 40.0
			start_search(sim, g, _here(g))
		return
	if g.slip > 0.0:
		g.slip -= C.DT
		if g.slip <= 0.0:
			g.slip = 0.0
			g.slip_immune = 3.0
			g.suspicion = maxf(g.suspicion, 35.0)
			start_search(sim, g, _here(g))
		return
	if g.sliding:
		_update_slide(sim, g)
		return
	if g.slip_immune > 0.0:
		g.slip_immune -= C.DT
	g.repath_t -= C.DT
	var m: GameMap = sim.maps[g.map_id]
	var p := sim.player
	var gi := m.idx(floori(g.x), floori(g.y))
	var moving: bool = g.has_path and not g.path.is_empty()
	if not g.cleats and g.slip_immune <= 0.0 and moving and (m.surface[gi] == C.S_GREASE or m.surface[gi] == C.S_ICE):
		g.slip = C.SLIP_TIME
		clear_path(g)
		Perception.emit_noise(sim, g.map_id, g.x, g.y, 3.0, "thud", "env")
		if g.map_id == p.map_id:
			sim.toast("%s slips and goes down hard." % g.display_name, Color("e0b44c"))
		return

	# --- perception: the player ---
	var d := Perception.can_see(sim, g, p.x, p.y, p.map_id)
	if d >= 0.0 and not sim.dead:
		var rate := C.SUSPICION_RATE * Perception.player_visibility(sim, g) * Perception.posture_mult(sim) * (1.0 - (d / C.VISION_RANGE) * 0.6)
		g.suspicion = minf(120.0, g.suspicion + rate)
		g.last_seen = {"map": p.map_id, "x": floori(p.x), "y": floori(p.y)}
		g.lost_t = 0.0
		if g.state != "pursuit":
			if g.suspicion >= 100.0:
				go_alert(sim, g, "player")
			elif g.suspicion >= C.SEARCH_AT and g.state != "search" and g.state != "investigate":
				start_search(sim, g, g.last_seen)
			elif g.suspicion >= C.CURIOUS_AT and ["patrol", "return", "curious"].has(g.state):
				g.state = "curious"
				g.stim = g.last_seen
				g.curious_t = 1.6
				clear_path(g)
	else:
		g.lost_t += C.DT
		if g.state != "pursuit":
			g.suspicion = maxf(0.0, g.suspicion - C.SUSPICION_DECAY)
	# --- perception: a floating Mage Hand glows faintly (spec §5.2) ---
	if not p.held.is_empty() and p.map_id == g.map_id:
		var hp := sim.hand_pos()
		if Perception.can_see(sim, g, hp.x, hp.y, p.map_id) >= 0.0:
			g.suspicion = minf(C.SEARCH_AT - 1.0, g.suspicion + 1.0)
			if g.suspicion >= C.CURIOUS_AT and (g.state == "patrol" or g.state == "return"):
				g.state = "curious"
				g.stim = {"map": p.map_id, "x": floori(hp.x), "y": floori(hp.y)}
				g.curious_t = 1.6
				clear_path(g)
	# --- perception: downed colleagues ---
	for o in sim.guards:
		if o == g or o.map_id != g.map_id or o.ko <= 0.0 or g.body_seen.has(o.id):
			continue
		if Perception.can_see(sim, g, o.x, o.y, o.map_id) >= 0.0:
			g.body_seen[o.id] = true
			g.suspicion = maxf(g.suspicion, 80.0)
			go_alert(sim, g, "body")
			start_search(sim, g, {"map": o.map_id, "x": floori(o.x), "y": floori(o.y)}, true)
			if g.map_id == p.map_id:
				sim.toast("%s finds a downed colleague!" % g.display_name, Color("ff9d7a"))
	# --- noisemakers left lying around ---
	if g.state == "patrol" or g.state == "return":
		for pl in sim.plants:
			if pl["kind"] != "noisemaker" or pl["map"] != g.map_id or Vector2(pl["x"] - g.x, pl["y"] - g.y).length() > 1.0:
				continue
			if randf() < C.NOISEMAKER_SPOT_CHANCE:
				sim.plants.erase(pl)
				if sim.in_tower_stage():
					sim.tower["ledger"]["noise_distractions"] += 1
				g.suspicion = 50.0
				start_search(sim, g, _here(g))
				sim.toast("%s found and disarmed a noisemaker." % g.display_name, Color("ff9d7a"))
				break

	# --- state machine ---
	match g.state:
		"patrol":
			if g.route.size() == 1:
				var home := {"map": g.home, "x": int(g.route[0][0]), "y": int(g.route[0][1])}
				if floori(g.x) != home["x"] or floori(g.y) != home["y"] or g.map_id != home["map"]:
					if not g.has_path and g.repath_t <= 0.0:
						set_goal(sim, g, home)
					step_along_path(sim, g, speed_for(g))
				else:
					g.sweep_t += C.DT
					g.face = g.sweep_base + sin(g.sweep_t * 0.6) * 1.05
				return
			if g.wait_t > 0.0:
				g.wait_t -= C.DT
				g.face += C.DT * 1.4 * sin(g.wait_t * 3.0)
				return
			var wp_pt := {"map": g.home, "x": int(g.route[g.wp][0]), "y": int(g.route[g.wp][1])}
			var goal_off: bool = not g.goal.is_empty() and (g.goal["x"] != wp_pt["x"] or g.goal["y"] != wp_pt["y"] or g.goal["map"] != wp_pt["map"])
			if (not g.has_path and g.repath_t <= 0.0) or goal_off:
				set_goal(sim, g, wp_pt)
			if step_along_path(sim, g, speed_for(g)):
				g.wp = (g.wp + 1) % g.route.size()
				g.wait_t = 1.2
				clear_path(g)
		"curious":
			if not g.stim.is_empty():
				g.face = C.turn_toward(g.face, atan2(g.stim["y"] + 0.5 - g.y, g.stim["x"] + 0.5 - g.x), 6.0)
			g.curious_t -= C.DT
			if g.curious_t <= 0.0:
				if g.suspicion >= C.CURIOUS_AT and not g.stim.is_empty():
					start_search(sim, g, g.stim)
				else:
					start_return(sim, g)
		"search":
			if g.search_phase == "goto":
				if not g.has_path and g.repath_t <= 0.0:
					set_goal(sim, g, g.stim)
				if step_along_path(sim, g, speed_for(g)) or not g.has_path:
					g.search_phase = "sweep"
					clear_path(g)
					g.wait_t = 0.8
			else:
				g.search_t -= C.DT
				if g.search_t <= 0.0:
					start_return(sim, g)
					return
				if g.wait_t > 0.0:
					g.wait_t -= C.DT
					g.face += C.DT * 2.2
					return
				if not g.has_path or step_along_path(sim, g, speed_for(g)):
					var t := _random_nearby_tile(sim, g, 4.0)
					if not t.is_empty():
						set_goal(sim, g, t)
					g.wait_t = 0.6
		"pursuit":
			if d >= 0.0 and Vector2(g.x - p.x, g.y - p.y).length() < C.CATCH_DIST and g.map_id == p.map_id:
				Flow.caught(sim, g)
				return
			if not g.last_seen.is_empty() and (g.repath_t <= 0.0 or not g.has_path):
				set_goal(sim, g, g.last_seen)
			var arrived := step_along_path(sim, g, speed_for(g))
			if (arrived or not g.has_path) and g.lost_t > C.LOST_SIGHT_TIME:
				g.suspicion = 70.0
				start_search(sim, g, g.last_seen if not g.last_seen.is_empty() else _here(g), true)
			if d >= 0.0:
				g.repath_t = minf(g.repath_t, 0.4)
		"investigate":
			if g.has_path and not g.path.is_empty():
				step_along_path(sim, g, speed_for(g))
			else:
				g.face += C.DT * 1.6
			if sim.time > g.inv_until:
				g.state = "search"
				g.stim = _here(g)
				g.search_phase = "sweep"
				g.search_t = 6.0
				clear_path(g)
		"return":
			if not g.has_path:
				if g.repath_t <= 0.0:
					start_return(sim, g)
			elif step_along_path(sim, g, speed_for(g)):
				g.state = "patrol"
				clear_path(g)
				g.wait_t = 0.5


static func _random_nearby_tile(sim: Sim, g, r: float) -> Dictionary:
	var m: GameMap = sim.maps[g.map_id]
	for tries in 12:
		var x := floori(g.x + randf_range(-r, r))
		var y := floori(g.y + randf_range(-r, r))
		if Pathfinder.guard_passable(m, x, y, null) and m.ray_clear(g.x, g.y, x + 0.5, y + 0.5, false):
			return {"map": g.map_id, "x": x, "y": y}
	return {}


static func _update_slide(sim: Sim, g) -> void:
	var m: GameMap = sim.maps[g.map_id]
	var res := PropPhysics.slide_body(m, g, C.GUARD_R)
	if res["hit_wall"] and res["speed"] * 3.0 >= C.KO_MOMENTUM:
		g.sliding = false
		g.ko = C.KO_TIME
		clear_path(g)
		if sim.in_tower_stage():
			sim.tower["ledger"]["env_ko"] += 1
		Perception.emit_noise(sim, g.map_id, g.x, g.y, 6.0, "impact", "player")
		sim.toast("%s slides into a wall. Out cold." % g.display_name, Color("9fd89a"))
		return
	if Vector2(g.vx, g.vy).length() < 0.4:
		g.sliding = false
		g.slip = C.SLIP_TIME * 0.5


static func _update_archmage(sim: Sim, g) -> void:
	g.away = sim.is_office_hours()
	if g.away:
		return
	if g.alert_cooldown > 0.0:
		g.alert_cooldown -= C.DT
	if g.asleep:
		return
	if g.awake_t > 0.0:
		g.awake_t -= C.DT
		if g.awake_t <= 0.0 and sim.night and not sim.dawn:
			g.asleep = true
			g.suspicion = 0.0
			g.face = g.sweep_base
			return
	g.sweep_t += C.DT
	g.face = g.sweep_base + sin(g.sweep_t * 0.35) * 1.2
	var p := sim.player
	var d := Perception.can_see(sim, g, p.x, p.y, p.map_id)
	if d >= 0.0 and not sim.dead:
		var rate := C.SUSPICION_RATE * C.ARCHMAGE_SUSPICION_MULT * Perception.player_visibility(sim, g) * Perception.posture_mult(sim) * (1.0 - (d / C.ARCHMAGE_RANGE) * 0.6)
		g.suspicion = minf(120.0, g.suspicion + rate)
		if g.suspicion >= 100.0:
			if g.alert_cooldown <= 0.0:
				sim.toast("ARCHMAGE GILT: \"GUARDS!\"", Color("ff6b5b"), 4.0)
			go_alert(sim, g, "player")
			for o in sim.guards:
				if not o.archmage and o.ko <= 0.0 and not o.sliding:
					o.last_seen = {"map": p.map_id, "x": floori(p.x), "y": floori(p.y)}
					if o.map_id == g.map_id:
						o.state = "pursuit"
						o.lost_t = 0.0
						clear_path(o)
						o.repath_t = 0.0
	else:
		g.suspicion = maxf(0.0, g.suspicion - C.SUSPICION_DECAY)
