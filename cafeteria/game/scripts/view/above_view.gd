extends Node2D
## Readability layer above the darkness: vision cones, guard state marks, noise rings,
## Reveal highlights and the spell/tool targeting preview. The player always knows what they broadcast.

var sim: Sim
const T := C.TILE


func _process(_delta: float) -> void:
	queue_redraw()


func _draw() -> void:
	if sim == null or sim.maps.is_empty():
		return
	var m := sim.cur_map()
	for g in sim.guards:
		if g.map_id == m.id and not g.away and g.ko <= 0.0 and g.slip <= 0.0 and not g.sliding and not g.asleep:
			_cone(m, g)
	for g in sim.guards:
		if g.map_id == m.id and not g.away and g.ko <= 0.0:
			_indicator(g)
	for r in sim.noise_rings:
		if r["map"] == m.id:
			_ring(r)
	_reveal(m)
	_targeting(m)


func _cone(m: GameMap, g) -> void:
	var rng := C.ARCHMAGE_RANGE if g.archmage else C.VISION_RANGE
	var half := C.ARCHMAGE_HALF_ANGLE if g.archmage else C.VISION_HALF_ANGLE
	var n := 30
	var pts := PackedVector2Array([Vector2(g.x, g.y) * T])
	for k in n + 1:
		var a: float = g.face - half + (2.0 * half) * k / n
		var d := 0.3
		while d < rng:
			if m.is_opaque(floori(g.x + cos(a) * d), floori(g.y + sin(a) * d), true):
				break
			d += 0.2
		pts.append(Vector2(g.x + cos(a) * d, g.y + sin(a) * d) * T)
	var s: float = g.suspicion
	var fill := Color(1, 0.24, 0.24, 0.26) if g.state == "pursuit" else (Color(1, 0.47, 0.24, 0.22) if s >= 60 else (Color(1, 0.75, 0.31, 0.17) if s >= 30 else Color(1, 0.94, 0.59, 0.10)))
	draw_colored_polygon(pts, fill)
	var edge := Color(0.63, 0.94, 1.0, 0.5) if g.true_sight else (Color(0.88, 0.71, 0.3, 0.45) if g.archmage else Color(1, 0.94, 0.59, 0.18))
	pts.append(pts[0])
	draw_polyline(pts, edge, 1.0)


func _indicator(g) -> void:
	var p := Vector2(g.x * T, g.y * T - (34 if g.archmage else 20))
	var txt := ""
	var col := Color.WHITE
	if g.state == "pursuit":
		txt = "!"
		col = Color("ff5b4b")
	elif g.state == "investigate":
		txt = "..."
		col = Color("a58bd8")
	elif g.state == "search" or g.state == "curious":
		txt = "?"
		col = Color("ffd36b")
	if g.suspicion > 0.0 and g.state != "pursuit":
		var c := p + Vector2(0, 6)
		draw_arc(c, 8, 0, TAU, 24, Color(0, 0, 0, 0.5), 4.0)
		draw_arc(c, 8, -PI / 2, -PI / 2 + TAU * minf(1.0, g.suspicion / 100.0), 24, Color("ff7b4b") if g.suspicion >= 60 else Color("ffd36b"), 3.0)
	if txt != "":
		DrawUtil.text_centered(self, p, txt, 18, col)


func _ring(r: Dictionary) -> void:
	var life := 1.4 if r["kind"] == "alarm" else 0.9
	var k: float = r["t"] / life
	var rad: float = r["r"]
	var base := Color(0.65, 0.55, 0.85) if r["kind"] == "silenced" else (Color(1, 0.27, 0.27) if r["kind"] == "alarm" else \
		(Color(0.78, 0.78, 0.78) if rad <= 1 else (Color(0.86, 0.83, 0.75) if rad <= 3 else (Color(0.88, 0.71, 0.3) if rad <= 6 else Color(1, 0.42, 0.36)))))
	base.a = (1.0 - k) * 0.8
	draw_arc(Vector2(r["x"], r["y"]) * T, maxf(2.0, rad * T * minf(1.0, k * 1.3)), 0, TAU, 48, base, 3.0 if r["kind"] == "alarm" else 2.0)


func _reveal(m: GameMap) -> void:
	if sim.reveal_t <= 0.0:
		return
	var p := sim.player
	var a := minf(1.0, sim.reveal_t) * (0.7 + 0.3 * sin(sim.time * 6.0))
	draw_arc(Vector2(p.x, p.y) * T, C.REVEAL_R * T, 0, TAU, 64, Color(0.63, 1.0, 0.75, 0.25 * a), 1.0)
	for y in range(floori(p.y - C.REVEAL_R), floori(p.y + C.REVEAL_R) + 1):
		for x in range(floori(p.x - C.REVEAL_R), floori(p.x + C.REVEAL_R) + 1):
			if not sim.is_revealed(m.id, x, y):
				continue
			var ch := m.tile(x, y)
			var px := float(x * T)
			var py := float(y * T)
			if ch == "x" and not m.tripwires_off:
				draw_rect(Rect2(px, py + 13, T, 6), Color(0.55, 1.0, 0.67, 0.35 * a))
				draw_rect(Rect2(px + 13, py, 6, T), Color(0.55, 1.0, 0.67, 0.35 * a))
			if (ch == "h" and not m.tripwires_off) or ch == "H":
				draw_rect(Rect2(px + 2, py + 2, T - 4, T - 4), Color(0.63, 1.0, 0.75, a), false, 2.0)
			if ch == "L" and m.sapped.has(m.idx(x, y)):
				draw_circle(Vector2(px + 24, py + 17), 7, Color(1.0, 0.7, 0.16, 0.55 * a))


func _targeting(m: GameMap) -> void:
	if sim.paused or not sim.duel.is_empty() or sim.dead or sim.stage == "title":
		return
	var p := sim.player
	var tx := floori(sim.mouse_world.x)
	var ty := floori(sim.mouse_world.y)
	var tc := Vector2(tx + 0.5, ty + 0.5)
	if sim.sel["type"] == "spell":
		var s := sim.current_spell()
		var ok := Vector2(p.x, p.y).distance_to(tc) <= float(C.SPELL_RANGE[s]) + 0.5
		var col: Color = {"grease": Color(0.88, 0.65, 0.18), "douse": Color(0.31, 0.55, 0.86), "freeze": Color(0.75, 0.92, 1.0),
			"silence": Color(0.65, 0.55, 0.85), "magehand": Color(0.75, 0.63, 1.0), "gust": Color(0.86, 0.86, 0.9), "reveal": Color(0.63, 1.0, 0.75)}[s]
		var c := col if ok else Color(1, 0.31, 0.31)
		c.a = 0.8
		match s:
			"grease", "douse", "freeze":
				draw_rect(Rect2((tx - 1) * T, (ty - 1) * T, T * 3, T * 3), c, false, 2.0)
			"silence":
				draw_arc(tc * T, C.SILENCE_R * T, 0, TAU, 48, c, 2.0)
			"gust":
				var a := atan2(sim.mouse_world.y - p.y, sim.mouse_world.x - p.x)
				var o := Vector2(p.x, p.y) * T
				col.a = 0.5
				draw_arc(o, C.GUST_RANGE * T, a - C.GUST_HALF, a + C.GUST_HALF, 24, col, 2.0)
				draw_line(o, o + Vector2(cos(a - C.GUST_HALF), sin(a - C.GUST_HALF)) * C.GUST_RANGE * T, col, 2.0)
				draw_line(o, o + Vector2(cos(a + C.GUST_HALF), sin(a + C.GUST_HALF)) * C.GUST_RANGE * T, col, 2.0)
			"magehand":
				var h := sim.hand_pos()
				draw_circle(h * T, 9 + sin(sim.time * 5.0) * 1.5, Color(0.75, 0.63, 1.0, 0.35))
				if not p.held.is_empty():
					draw_arc(Vector2(p.x, p.y) * T, C.SPELL_RANGE["magehand"] * T, 0, TAU, 64, Color(0.75, 0.63, 1.0, 0.18), 1.0)
			"reveal":
				col.a = 0.4
				draw_arc(Vector2(p.x, p.y) * T, C.REVEAL_R * T, 0, TAU, 64, col, 2.0)
	else:
		var t: String = sim.sel["id"]
		var d := Vector2(p.x, p.y).distance_to(tc)
		var ok := d <= (C.THROW_RANGE if t == "smoke" else C.PLACE_RANGE) + 0.5
		var c := Color(0.88, 0.71, 0.3, 0.8) if ok else Color(1, 0.31, 0.31, 0.8)
		if t == "smoke":
			draw_rect(Rect2((tx - 1) * T, (ty - 1) * T, T * 3, T * 3), c, false, 2.0)
		else:
			draw_rect(Rect2(tx * T + 2, ty * T + 2, T - 4, T - 4), c, false, 2.0)
