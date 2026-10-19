class_name Spells
## Spells (spec §5.2), thief tools (spec §5.3) and timed plants.


static func use_selected(sim: Sim) -> void:
	if sim.sel["type"] == "spell":
		cast(sim)
	else:
		use_tool(sim)


static func _tile_target(sim: Sim) -> Vector2i:
	return Vector2i(floori(sim.mouse_world.x), floori(sim.mouse_world.y))


static func cast(sim: Sim) -> void:
	var p := sim.player
	var m := sim.cur_map()
	var s := sim.current_spell()
	var t := _tile_target(sim)
	if s == "magehand" and not p.held.is_empty():
		var hp := sim.hand_pos()
		drop_held(sim, floori(hp.x), floori(hp.y))
		return
	var cost: float = C.SPELL_COST[s]
	if p.mana < cost:
		sim.toast("Not enough mana.")
		return
	if s == "magehand" and p.carrying != "":
		sim.toast("Both hands are full of Phoenix.")
		return
	if s != "reveal" and s != "gust":
		var rng: float = C.SPELL_RANGE[s]
		if Vector2(p.x - (t.x + 0.5), p.y - (t.y + 0.5)).length() > rng + 0.5:
			sim.toast("Out of range.")
			return
		if not m.ray_clear(p.x, p.y, t.x + 0.5, t.y + 0.5, false):
			sim.toast("No line of sight.")
			return
	var ok := true
	match s:
		"magehand": ok = _mage_hand(sim, m, t.x, t.y)
		"grease": grease(sim, m, t.x, t.y)
		"gust": gust(sim, m)
		"douse": douse(m, t.x, t.y)
		"freeze": freeze(sim, m, t.x, t.y)
		"silence": sim.silences.append({"map": m.id, "x": t.x + 0.5, "y": t.y + 0.5, "t": C.SILENCE_TIME})
		"reveal": sim.reveal_t = C.REVEAL_TIME
	if not ok:
		return
	p.mana -= cost
	p.mana_delay = C.MANA_REGEN_DELAY
	sim.sfx.emit("cast_" + s, 0.0)
	for g in sim.guards:
		if g.map_id == p.map_id and not g.away and g.ko <= 0.0 and not g.asleep and Perception.can_see(sim, g, p.x, p.y, p.map_id) >= 0.0:
			g.suspicion = minf(120.0, g.suspicion + 40.0)


static func _mage_hand(sim: Sim, m: GameMap, tx: int, ty: int) -> bool:
	var p := sim.player
	var o := m.object_at(tx + 0.5, ty + 0.5, 0.7)
	if o != null and o.kind != "relic":
		if o.mass <= 2.0:
			p.held = {"kind": "obj", "obj": o}
			o.held = true
			o.vx = 0.0
			o.vy = 0.0
			sim.toast("Mage Hand lifts the %s." % o.display_name)
		else:
			var d := maxf(0.01, Vector2(p.x - o.x, p.y - o.y).length())
			o.vx += (o.x - p.x) / d * 6.0 / o.mass
			o.vy += (o.y - p.y) / d * 6.0 / o.mass
			sim.toast("Too heavy to lift. The hand gives the %s a nudge." % o.display_name)
		return true
	var ch := m.tile(tx, ty)
	var i := m.idx(tx, ty)
	if ch == "-":
		m.set_tile(tx, ty, ".")
		m.wire_moved.erase(i)
		p.held = {"kind": "wire"}
		sim.toast("Mage Hand unhooks the tripwire. Click to re-string it somewhere... useful.")
		return true
	if ch == "L":
		if m.sapped.has(i):
			sim.toast("Mage Hand fizzles on contact with the sap.", Color("e0b44c"))
			return true
		Interact.start_lock(sim, m, tx, ty, true)
		return true
	if ch == "D":
		m.set_tile(tx, ty, "O")
		Perception.emit_noise(sim, m.id, tx + 0.5, ty + 0.5, 2.0, "door", "player")
		return true
	if ch == "O" and not sim.entity_on_tile(m.id, tx, ty):
		m.set_tile(tx, ty, "D")
		Perception.emit_noise(sim, m.id, tx + 0.5, ty + 0.5, 2.0, "door", "player")
		return true
	if ch == "H" and sim.is_revealed(m.id, tx, ty):
		m.set_tile(tx, ty, "O")
		sim.toast("The hand finds the seam. A hidden door swings open.")
		return true
	sim.toast("Nothing for the hand to do there.")
	return false


static func drop_held(sim: Sim, tx: int, ty: int) -> void:
	var p := sim.player
	var m := sim.cur_map()
	if p.held.is_empty():
		return
	if p.held["kind"] == "obj":
		var o: WorldObject = p.held["obj"]
		if m.is_solid(tx, ty):
			o.x = p.x
			o.y = p.y
		else:
			o.x = tx + 0.5
			o.y = ty + 0.5
		o.held = false
		o.vx = 0.0
		o.vy = 0.0
	else:
		var ch := m.tile(tx, ty)
		if ".,:=".contains(ch):
			m.set_tile(tx, ty, "-")
			m.wire_moved[m.idx(tx, ty)] = true
			sim.toast("Wire re-strung. The guards walk this way without looking down.")
		else:
			sim.toast("The wire slithers away. It needs open floor.")
	p.held = {}


static func _area(m: GameMap, cx: int, cy: int) -> Array[Vector2i]:
	var out: Array[Vector2i] = []
	for y in range(cy - 1, cy + 2):
		for x in range(cx - 1, cx + 2):
			if m.inb(x, y):
				out.append(Vector2i(x, y))
	return out


static func grease(sim: Sim, m: GameMap, tx: int, ty: int) -> void:
	for c in _area(m, tx, ty):
		if m.is_solid(c.x, c.y):
			continue
		var i := m.idx(c.x, c.y)
		if m.rune_hot(i):
			m.surface[i] = C.S_BURN
			m.s_timer[i] = C.BURN_TIME
			m.burn_spread[i] = C.BURN_SPREAD
		else:
			m.surface[i] = C.S_GREASE
			m.s_timer[i] = C.GREASE_TIME
	if sim.in_tower_stage() and m.building == "sunspire":
		sim.tower["ledger"]["grease_casts"] += 1


static func _in_cone(px: float, py: float, ang: float, x: float, y: float, rng: float, half: float) -> bool:
	var d := Vector2(x - px, y - py).length()
	if d > rng or d < 0.01:
		return false
	return absf(C.ang_diff(ang, atan2(y - py, x - px))) <= half


static func gust(sim: Sim, m: GameMap) -> void:
	var p := sim.player
	var ang := atan2(sim.mouse_world.y - p.y, sim.mouse_world.x - p.x)
	for o in m.objects:
		if o.held or o.kind == "relic" or not _in_cone(p.x, p.y, ang, o.x, o.y, C.GUST_RANGE, C.GUST_HALF):
			continue
		if not m.ray_clear(p.x, p.y, o.x, o.y, false):
			continue
		var d := Vector2(o.x - p.x, o.y - p.y).length()
		o.vx += (o.x - p.x) / d * C.GUST_IMPULSE / o.mass
		o.vy += (o.y - p.y) / d * C.GUST_IMPULSE / o.mass
	for g in sim.guards:
		if g.map_id != m.id or g.away or g.archmage or g.ko > 0.0 or not _in_cone(p.x, p.y, ang, g.x, g.y, C.GUST_RANGE, C.GUST_HALF):
			continue
		if not m.ray_clear(p.x, p.y, g.x, g.y, false):
			continue
		var s := m.surface_at(g.x, g.y)
		var d := Vector2(g.x - p.x, g.y - p.y).length()
		if not g.cleats and (s == C.S_GREASE or s == C.S_ICE):
			g.sliding = true
			g.vx = (g.x - p.x) / d * C.GUST_IMPULSE / 3.0
			g.vy = (g.y - p.y) / d * C.GUST_IMPULSE / 3.0
			GuardAI.clear_path(g)
		elif g.state != "pursuit":
			g.suspicion = minf(120.0, g.suspicion + 15.0)
			g.state = "curious"
			g.stim = {"map": m.id, "x": floori(p.x), "y": floori(p.y)}
			g.curious_t = 1.6
			GuardAI.clear_path(g)
	var r := C.GUST_RANGE
	for y in range(floori(p.y - r), floori(p.y + r) + 1):
		for x in range(floori(p.x - r), floori(p.x + r) + 1):
			if not m.inb(x, y) or not _in_cone(p.x, p.y, ang, x + 0.5, y + 0.5, r, C.GUST_HALF):
				continue
			if not m.ray_clear(p.x, p.y, x + 0.5, y + 0.5, false):
				continue
			if m.tile(x, y) == "T":
				m.set_tile(x, y, "Y")
			m.cloud[m.idx(x, y)] = C.C_NONE
	for k in 26:
		var a := ang + randf_range(-C.GUST_HALF, C.GUST_HALF)
		var sp := randf_range(5.0, 9.0)
		sim.particles.append({"map": m.id, "x": p.x, "y": p.y, "vx": cos(a) * sp, "vy": sin(a) * sp, "t": 0.0, "life": randf_range(0.4, 0.8), "kind": "wind"})
	Perception.emit_noise(sim, m.id, p.x, p.y, 3.0, "whoosh", "player")


static func _snuff_torches_around(m: GameMap, tx: int, ty: int) -> void:
	for c in _area(m, tx, ty):
		if m.tile(c.x, c.y) == "T":
			m.set_tile(c.x, c.y, "Y")


static func douse(m: GameMap, tx: int, ty: int) -> void:
	for c in _area(m, tx, ty):
		if m.is_solid(c.x, c.y):
			continue
		var i := m.idx(c.x, c.y)
		if m.surface[i] == C.S_BURN:
			m.surface[i] = C.S_DRY
		elif m.surface[i] == C.S_DRY:
			m.surface[i] = C.S_WET
			m.s_timer[i] = C.DRY_TIME
		if m.cloud[i] == C.C_SMOKE:
			m.cloud[i] = C.C_FOG
			m.c_timer[i] = C.FOG_TIME
		if m.rune_hot(i):
			m.cloud[i] = C.C_STEAM
			m.c_timer[i] = C.STEAM_TIME
	_snuff_torches_around(m, tx, ty)


static func freeze(sim: Sim, m: GameMap, tx: int, ty: int) -> void:
	var blocks := 0
	for c in _area(m, tx, ty):
		if m.is_solid(c.x, c.y):
			continue
		var i := m.idx(c.x, c.y)
		if m.surface[i] == C.S_WET:
			m.surface[i] = C.S_ICE
			m.s_timer[i] = C.ICE_MELT_TIME
		if m.cloud[i] == C.C_FOG and not sim.entity_on_tile(m.id, c.x, c.y):
			m.ice_block[i] = C.ICE_BLOCK_TIME
			m.cloud[i] = C.C_NONE
			blocks += 1
		if m.rune[i] == 1:
			m.cool[i] = C.COOL_TIME
	if blocks > 0:
		m.light_dirty = true
		m.revision += 1
		sim.toast("The fog locks solid: %d tile%s of ice wall." % [blocks, "s" if blocks > 1 else ""], Color("8fd3e8"))


static func use_tool(sim: Sim) -> void:
	var p := sim.player
	var m := sim.cur_map()
	var tl: String = sim.sel["id"]
	var t := _tile_target(sim)
	if p.tools[tl] <= 0:
		sim.toast("No %ss left. Mother Ladle sells more." % C.TOOL_NAMES[tl])
		return
	var d := Vector2(p.x - (t.x + 0.5), p.y - (t.y + 0.5)).length()
	if tl == "smoke":
		if d > C.THROW_RANGE + 0.5 or not m.ray_clear(p.x, p.y, t.x + 0.5, t.y + 0.5, false):
			sim.toast("Can't throw it there.")
			return
		for c in _area(m, t.x, t.y):
			if not m.is_solid(c.x, c.y):
				var i := m.idx(c.x, c.y)
				m.cloud[i] = C.C_SMOKE
				m.c_timer[i] = C.SMOKE_TIME
		Perception.emit_noise(sim, m.id, t.x + 0.5, t.y + 0.5, 2.0, "pop", "player")
	else:
		if d > C.PLACE_RANGE + 0.5 or m.is_solid(t.x, t.y) or C.is_link_ch(m.tile(t.x, t.y)):
			sim.toast("Place it on open floor next to you.")
			return
		if tl == "noisemaker":
			sim.plants.append({"map": m.id, "x": t.x + 0.5, "y": t.y + 0.5, "kind": "noisemaker", "timer": float(sim.noise_timer), "total": float(sim.noise_timer)})
			sim.toast("Noisemaker set: %s. Go be seen somewhere." % C.fmt_time(sim.noise_timer), Color("e0b44c"))
		else:
			sim.plants.append({"map": m.id, "x": t.x + 0.5, "y": t.y + 0.5, "kind": "iceRune", "timer": C.ICE_RUNE_MELT, "total": C.ICE_RUNE_MELT})
			sim.toast("Ice-rune placed. It goes when it melts.", Color("8fd3e8"))
	p.tools[tl] -= 1


static func update_plants(sim: Sim) -> void:
	var k := sim.plants.size() - 1
	while k >= 0:
		var pl: Dictionary = sim.plants[k]
		k -= 1
		var m: GameMap = sim.maps[pl["map"]]
		var rate := 1.0
		if pl["kind"] == "iceRune":
			for c in _area(m, floori(pl["x"]), floori(pl["y"])):
				if m.rune_hot(m.idx(c.x, c.y)):
					rate = C.ICE_RUNE_MELT / C.ICE_RUNE_MELT_HOT
					break
		pl["timer"] -= C.DT * rate
		if pl["timer"] <= 0.0:
			sim.plants.erase(pl)
			Perception.emit_noise(sim, pl["map"], pl["x"], pl["y"], 10.0, "plant", "player")
			if pl["map"] == sim.player.map_id:
				sim.toast("*CLANG-A-LANG-A-LANG*" if pl["kind"] == "noisemaker" else "*crack* — the ice-rune goes off.", Color("e0b44c"))
			if m.building == "sunspire" and sim.in_tower_stage():
				Alibi.create_incident(sim, pl["map"], pl["x"], pl["y"])
