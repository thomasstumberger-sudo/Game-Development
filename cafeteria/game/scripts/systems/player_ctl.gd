class_name PlayerCtl
## Player movement, footsteps and tile triggers. Reads sim.input_* (set by Main or tests).


static func update(sim: Sim) -> void:
	var p := sim.player
	var m := sim.cur_map()
	if p.mana_delay > 0.0:
		p.mana_delay -= C.DT
	else:
		p.mana = minf(C.MANA_MAX, p.mana + C.MANA_REGEN * C.DT)
	if p.trip_cooldown > 0.0:
		p.trip_cooldown -= C.DT
	if not p.held.is_empty():
		p.mana -= 2.0 * C.DT
		p.mana_delay = C.MANA_REGEN_DELAY
		var hp := sim.hand_pos()
		if p.held["kind"] == "obj" and not m.is_solid(floori(hp.x), floori(hp.y)):
			p.held["obj"].x = hp.x
			p.held["obj"].y = hp.y
		if p.mana <= 0.0:
			p.mana = 0.0
			Spells.drop_held(sim, floori(hp.x), floori(hp.y))
			sim.toast("Mage Hand dissolves — out of mana.")
	if sim.dead or not sim.duel.is_empty() or sim.paused:
		p.vx = 0.0
		p.vy = 0.0
		return
	var input := sim.input_dir
	if not sim.lock.is_empty():
		if not sim.lock["magehand"] and input != Vector2.ZERO:
			sim.lock = {}
			sim.toast("Lockpicking abandoned.")
		else:
			p.vx = 0.0
			p.vy = 0.0
			return
	if input.length() > 1.0:
		input = input.normalized()
	var sneak := sim.input_sneak
	var sprint := sim.input_sprint and p.carrying == ""
	p.posture = "sneak" if sneak else ("sprint" if sprint else "walk")
	var speed := C.PLAYER_SPEED * (C.SNEAK_MULT if sneak else (C.SPRINT_MULT if sprint else 1.0)) * (C.CARRY_MULT if p.carrying != "" else 1.0)
	var surf := m.surface_at(p.x, p.y)
	if surf == C.S_GREASE or surf == C.S_ICE:
		p.vx = (p.vx + input.x * C.SLIDE_ACCEL * C.DT) * C.SLIDE_DRAG
		p.vy = (p.vy + input.y * C.SLIDE_ACCEL * C.DT) * C.SLIDE_DRAG
		var v := Vector2(p.vx, p.vy).length()
		var cap := speed * 1.25
		if v > cap:
			p.vx *= cap / v
			p.vy *= cap / v
	else:
		p.vx = input.x * speed
		p.vy = input.y * speed
	var ox := p.x
	var oy := p.y
	var h := PropPhysics.move_circle(m, p, C.PLAYER_R, p.vx * C.DT, p.vy * C.DT)
	if h.x:
		p.vx = 0.0
	if h.y:
		p.vy = 0.0
	# shove props
	for o in m.objects:
		if o.held:
			continue
		var d := Vector2(o.x - p.x, o.y - p.y).length()
		var mn := C.PLAYER_R + C.OBJ_R
		if d < mn and d > 0.001:
			var nx := (p.x - o.x) / d
			var ny := (p.y - o.y) / d
			PropPhysics.move_circle(m, p, C.PLAYER_R, nx * (mn - d), ny * (mn - d))
			if o.kind != "relic":
				o.vx -= nx * 1.6 / o.mass
				o.vy -= ny * 1.6 / o.mass
	p.face = atan2(sim.mouse_world.y - p.y, sim.mouse_world.x - p.x)
	# footsteps
	p.step_acc += Vector2(p.x - ox, p.y - oy).length()
	if p.step_acc > 0.9:
		p.step_acc = 0.0
		var r := 0.5 if p.posture == "sneak" else (5.0 if p.posture == "sprint" else 2.0)
		if surf == C.S_WET and p.posture == "sprint":
			r += 1.0
		Perception.emit_noise(sim, p.map_id, p.x, p.y, r, "step", "player")
	# tile triggers
	var tx := floori(p.x)
	var ty := floori(p.y)
	var ti := m.idx(tx, ty)
	var ch := m.tiles[ti]
	if ti != p.last_tile:
		if ch == "x" and not m.tripwires_off and p.trip_cooldown <= 0.0:
			p.trip_cooldown = 3.0
			sim.toast("A ward-line flares under your boot. ALARM!", Color("ff6b5b"), 4.0)
			Perception.emit_noise(sim, p.map_id, tx + 0.5, ty + 0.5, 14.0, "alarm", "env")
			if sim.in_tower_stage():
				sim.tower["ledger"]["alerts"] += 1
				if sim.stage == "act3" and p.map_id == "f2":
					sim.tower["vault_alert"] = true
		if ch == "-":
			m.wire_moved.erase(ti)
			sim.toast("*BRRRING* — you walked straight through a tripwire bell.", Color("ff9d7a"))
			Perception.emit_noise(sim, p.map_id, tx + 0.5, ty + 0.5, 8.0, "bell", "player")
		p.last_tile = ti
	if m.surface[ti] == C.S_BURN:
		p.burn_t += C.DT
		if p.burn_t >= 1.0:
			p.burn_t = 0.0
			p.hp -= 1
			Perception.emit_noise(sim, p.map_id, p.x, p.y, 4.0, "yelp", "player")
			sim.toast("You are on fire. Briefly, and then less briefly.", Color("ff9d7a"))
			if p.hp <= 0:
				Flow.die(sim)
	else:
		p.burn_t = 0.0
