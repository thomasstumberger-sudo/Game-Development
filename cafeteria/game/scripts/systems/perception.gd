class_name Perception
## Noise (spec §4.3) and vision (spec §4.2).


static func inside_silence(sim: Sim, map_id: String, x: float, y: float) -> bool:
	for s in sim.silences:
		if s["map"] == map_id and Vector2(s["x"] - x, s["y"] - y).length() <= C.SILENCE_R:
			return true
	return false


## Emits a noise ring and lets guards react. Returns true if any guard was pulled.
static func emit_noise(sim: Sim, map_id: String, x: float, y: float, r: float, kind: String, src: String) -> bool:
	if inside_silence(sim, map_id, x, y):
		sim.noise_rings.append({"map": map_id, "x": x, "y": y, "r": 0.6, "t": 0.0, "kind": "silenced"})
		return false
	sim.noise_rings.append({"map": map_id, "x": x, "y": y, "r": r, "t": 0.0, "kind": kind})
	if map_id == sim.player.map_id:
		sim.sfx.emit(kind, r)
	var m: GameMap = sim.maps[map_id]
	var pulled := false
	for g in sim.guards:
		if g.map_id != map_id or g.ko > 0.0 or g.away:
			continue
		if src == "guard" and kind != "shout":
			continue
		if g.earmuffs:
			continue    # deaf to everything — including your sprinting (canon)
		var d := Vector2(g.x - x, g.y - y).length()
		var eff := r if m.ray_clear(x, y, g.x, g.y, false) else r * 0.5
		if d > eff:
			continue
		if hear(sim, g, map_id, x, y, r, kind):
			pulled = true
	if pulled and src == "player" and C.DISTRACTION_KINDS.has(kind) and sim.in_tower_stage() and m.building == "sunspire":
		sim.tower["ledger"]["noise_distractions"] += 1
	return pulled


static func hear(sim: Sim, g, map_id: String, x: float, y: float, r: float, kind: String) -> bool:
	if g.archmage:
		if g.asleep:
			g.asleep = false
			g.awake_t = 30.0
			sim.toast("Archmage Gilt stirs in her sleep...", Color("e0b44c"))
		g.face = atan2(y - g.y, x - g.x)
		g.sweep_base = g.face
		return true
	if g.sliding:
		return false
	var stim := {"map": map_id, "x": floori(x), "y": floori(y)}
	if kind == "alarm":
		g.suspicion = maxf(g.suspicion, C.SEARCH_AT)
		GuardAI.start_search(sim, g, stim, true)
		return true
	if g.state == "pursuit" or g.state == "investigate":
		return false
	if g.state == "search":
		g.stim = stim
		GuardAI.set_goal(sim, g, stim)
		g.search_phase = "goto"
		return true
	if r >= 6.0 or kind == "shout":
		GuardAI.start_search(sim, g, stim, kind == "shout")
		return true
	g.state = "curious"
	g.stim = stim
	g.curious_t = 1.6
	g.has_path = false
	return true


## Distance to the target if the guard can see it, else -1.
static func can_see(sim: Sim, g, tx: float, ty: float, tmap: String) -> float:
	if g.map_id != tmap:
		return -1.0
	var rng := C.ARCHMAGE_RANGE if g.archmage else C.VISION_RANGE
	var half := C.ARCHMAGE_HALF_ANGLE if g.archmage else C.VISION_HALF_ANGLE
	var d := Vector2(g.x - tx, g.y - ty).length()
	if d > rng:
		return -1.0
	if d > 0.6 and absf(C.ang_diff(g.face, atan2(ty - g.y, tx - g.x))) > half:
		return -1.0
	var m: GameMap = sim.maps[g.map_id]
	var ti := m.idx(floori(tx), floori(ty))
	if m.inb(floori(tx), floori(ty)) and m.cloud[ti] != C.C_NONE and d > 1.2:
		return -1.0   # standing inside smoke/steam
	if not m.ray_clear(g.x, g.y, tx, ty, true):
		return -1.0
	return d


static func player_visibility(sim: Sim, g) -> float:
	if g.true_sight:
		return 1.0
	return 0.25 + 0.75 * sim.cur_map().light_at(sim.player.x, sim.player.y)


static func posture_mult(sim: Sim) -> float:
	var p := sim.player
	var mult := 0.6 if p.posture == "sneak" else (1.4 if p.posture == "sprint" else 1.0)
	if p.carrying != "":
		mult += 0.5
	return mult
