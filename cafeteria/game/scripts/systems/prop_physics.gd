class_name PropPhysics
## Sliding bodies, props, surfaces and clouds (spec §5.1). Friction comes from the tile underneath.


## Axis-separated circle-vs-tile collision. `e` needs x/y fields.
static func move_circle(m: GameMap, e, r: float, dx: float, dy: float) -> Vector2i:
	var hit := Vector2i.ZERO
	if dx != 0.0:
		if _blocked(m, e.x + dx, e.y, r):
			hit.x = 1
		else:
			e.x += dx
	if dy != 0.0:
		if _blocked(m, e.x, e.y + dy, r):
			hit.y = 1
		else:
			e.y += dy
	return hit


static func _blocked(m: GameMap, x: float, y: float, r: float) -> bool:
	return m.is_solid(floori(x - r), floori(y - r)) or m.is_solid(floori(x + r), floori(y - r)) \
		or m.is_solid(floori(x - r), floori(y + r)) or m.is_solid(floori(x + r), floori(y + r))


## Moves a body with vx/vy, applies surface friction. Returns {"hit_wall", "speed"} (speed before impact).
static func slide_body(m: GameMap, b, r: float) -> Dictionary:
	var speed := Vector2(b.vx, b.vy).length()
	var sub := maxi(1, ceili(speed * C.DT / 0.2))
	var hit_wall := false
	for s in sub:
		var h := move_circle(m, b, r, b.vx * C.DT / sub, b.vy * C.DT / sub)
		if h.x:
			b.vx = 0.0
			hit_wall = true
		if h.y:
			b.vy = 0.0
			hit_wall = true
	var f: float = C.SURFACE_FRICTION[m.surface_at(b.x, b.y)]
	b.vx *= f
	b.vy *= f
	return {"hit_wall": hit_wall, "speed": speed}


static func update_objects(sim: Sim, m: GameMap) -> void:
	var k := m.objects.size() - 1
	while k >= 0:
		var o: WorldObject = m.objects[k]
		k -= 1
		if o.held:
			continue
		if Vector2(o.vx, o.vy).length() < 0.05:
			o.vx = 0.0
			o.vy = 0.0
			continue
		var res := slide_body(m, o, C.OBJ_R)
		var spd: float = res["speed"]
		if res["hit_wall"] and spd > 1.5:
			if o.kind == "fern":
				m.objects.erase(o)
				Perception.emit_noise(sim, m.id, o.x, o.y, 4.0, "shatter", "player")
				continue
			Perception.emit_noise(sim, m.id, o.x, o.y, 7.0 if o.kind == "armor" else 6.0, "clank" if o.kind == "armor" else "impact", "player")
		for g in sim.guards:
			if g.map_id != m.id or g.ko > 0.0 or g.archmage or g.away:
				continue
			if Vector2(g.x - o.x, g.y - o.y).length() < C.OBJ_R + C.GUARD_R:
				if spd * o.mass >= C.KO_MOMENTUM and o.kind != "fern":
					g.ko = C.KO_TIME
					GuardAI.clear_path(g)
					g.sliding = false
					g.slip = 0.0
					if sim.in_tower_stage():
						sim.tower["ledger"]["env_ko"] += 1
					Perception.emit_noise(sim, m.id, g.x, g.y, 6.0, "impact", "player")
					sim.toast("%s meets a %s at speed. Out cold." % [g.display_name, o.display_name], Color("9fd89a"))
				elif g.state != "pursuit":
					g.state = "curious"
					g.stim = {"map": m.id, "x": floori(o.x), "y": floori(o.y)}
					g.curious_t = 2.0
					GuardAI.clear_path(g)
				o.vx *= -0.2
				o.vy *= -0.2
		var p := sim.player
		if p.map_id == m.id and Vector2(p.x - o.x, p.y - o.y).length() < C.OBJ_R + C.PLAYER_R:
			o.vx *= -0.2
			o.vy *= -0.2


static func update_surfaces(m: GameMap) -> void:
	var n := m.w * m.h
	for i in n:
		if m.cool[i] > 0.0:
			m.cool[i] -= C.DT
		var s := m.surface[i]
		if s != C.S_DRY:
			var rate := 4.0 if (s == C.S_ICE and m.rune_hot(i)) else 1.0
			m.s_timer[i] -= C.DT * rate
			if s == C.S_BURN:
				m.burn_spread[i] -= C.DT
				if m.burn_spread[i] <= 0.0:
					m.burn_spread[i] = C.BURN_SPREAD
					var x := i % m.w
					var y := i / m.w
					for d in [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]:
						if not m.inb(x + d.x, y + d.y):
							continue
						var j := m.idx(x + d.x, y + d.y)
						if m.surface[j] == C.S_GREASE:
							m.surface[j] = C.S_BURN
							m.s_timer[j] = C.BURN_TIME
							m.burn_spread[j] = C.BURN_SPREAD
			if m.s_timer[i] <= 0.0:
				if s == C.S_ICE:
					m.surface[i] = C.S_WET
					m.s_timer[i] = C.DRY_TIME
				else:
					m.surface[i] = C.S_DRY
		if m.cloud[i] != C.C_NONE:
			m.c_timer[i] -= C.DT
			if m.c_timer[i] <= 0.0:
				m.cloud[i] = C.C_NONE
		if m.ice_block[i] > 0.0:
			m.ice_block[i] -= C.DT * (4.0 if m.rune_hot(i) else 1.0)
			if m.ice_block[i] <= 0.0:
				m.ice_block[i] = 0.0
				m.surface[i] = C.S_WET
				m.s_timer[i] = C.DRY_TIME
				m.light_dirty = true
