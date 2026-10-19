extends Node2D
## Placeholder art for the world: tiles, surfaces, props, people, clouds, particles.
## Everything here reads the Sim; replacing it with TileMapLayer + sprites touches no game logic.

var sim: Sim

const T := C.TILE
const FLOOR_COL := {
	".": [Color("3a3d47"), Color("363944")], ",": [Color("5a2b35"), Color("552832")],
	":": [Color("3e5b3b"), Color("3a5638")], "=": [Color("5d5b55"), Color("57554f")],
}
const LINE_W := 1.0


func _process(_delta: float) -> void:
	queue_redraw()


func _draw() -> void:
	if sim == null or sim.maps.is_empty():
		return
	var m := sim.cur_map()
	var r := DrawUtil.visible_tiles(self, m)
	for y in range(r.position.y, r.end.y + 1):
		for x in range(r.position.x, r.end.x + 1):
			_draw_tile(m, x, y)
	for y in range(r.position.y, r.end.y + 1):
		for x in range(r.position.x, r.end.x + 1):
			_draw_surface(m, x, y)
	for s in sim.silences:
		if s["map"] == m.id:
			draw_circle(Vector2(s["x"], s["y"]) * T, C.SILENCE_R * T, Color(0.65, 0.55, 0.85, 0.12))
			draw_arc(Vector2(s["x"], s["y"]) * T, C.SILENCE_R * T, 0, TAU, 48, Color(0.65, 0.55, 0.85, 0.6), 1.5)
	for pl in sim.plants:
		if pl["map"] == m.id:
			_draw_plant(pl)
	for o in m.objects:
		_draw_object(o)
	if m.id == "hub":
		for n in sim.npcs:
			_draw_npc(n)
	for g in sim.guards:
		if g.map_id == m.id and not g.away:
			_draw_guard(g)
	_draw_player()
	for y in range(r.position.y, r.end.y + 1):
		for x in range(r.position.x, r.end.x + 1):
			_draw_cloud(m, x, y)
	for pt in sim.particles:
		if pt["map"] != m.id:
			continue
		var a: float = 1.0 - pt["t"] / pt["life"]
		var pos := Vector2(pt["x"], pt["y"]) * T
		if pt["kind"] == "fire":
			draw_rect(Rect2(pos, Vector2(3, 3)), Color(1.0, (150.0 + 100.0 * a) / 255.0, 0.24, a))
		else:
			draw_rect(Rect2(pos, Vector2(6, 1.5)), Color(0.9, 0.9, 0.94, a * 0.6))


# ---------- tiles ----------
func _floor(m: GameMap, ch: String, x: int, y: int, px: float, py: float) -> void:
	var base := ch
	if C.is_link_ch(ch) or "POx-".contains(ch):
		base = "."
		for c in [m.tile(x - 1, y), m.tile(x + 1, y), m.tile(x, y - 1), m.tile(x, y + 1)]:
			if FLOOR_COL.has(c):
				base = c
				break
	var cols: Array = FLOOR_COL.get(base, FLOOR_COL["."])
	draw_rect(Rect2(px, py, T, T), cols[(x + y) & 1])
	var h := DrawUtil.tile_hash(x, y)
	if base == ":":
		draw_rect(Rect2(px + h * 26, py + (1 - h) * 26, 2, 3), Color(0.47, 0.67, 0.39, 0.25))
		draw_rect(Rect2(px + fmod(h * 13.0, 1.0) * 28, py + h * 20, 2, 2), Color(0.47, 0.67, 0.39, 0.25))
	elif base == "=":
		draw_rect(Rect2(px + 1, py + 1, 15, 14), Color(0, 0, 0, 0.25), false, LINE_W)
		draw_rect(Rect2(px + 16, py + 16, 15, 14), Color(0, 0, 0, 0.25), false, LINE_W)
	elif base == ",":
		draw_rect(Rect2(px + 3, py + 3, T - 6, T - 6), Color(0.88, 0.71, 0.3, 0.12), false, LINE_W)
	else:
		draw_rect(Rect2(px, py + T - 1, T, 1), Color(0, 0, 0, 0.08))


func _wall(m: GameMap, x: int, y: int, px: float, py: float) -> void:
	draw_rect(Rect2(px, py, T, T), Color("1e2129"))
	var below := m.tile(x, y + 1)
	if not C.WALLISH_CH.contains(below):
		draw_rect(Rect2(px, py + 14, T, 18), Color("4a4f5e"))
		var dark := Color(0, 0, 0, 0.25)
		draw_rect(Rect2(px, py + 22, T, 1), dark)
		draw_rect(Rect2(px + (8 if y & 1 else 20), py + 14, 1, 8), dark)
		draw_rect(Rect2(px + (22 if y & 1 else 6), py + 23, 1, 9), dark)
		draw_rect(Rect2(px, py + 12, T, 2), Color("2a2e38"))


func _draw_tile(m: GameMap, x: int, y: int) -> void:
	var i := m.idx(x, y)
	var ch := m.tiles[i]
	var px := float(x * T)
	var py := float(y * T)
	if ch == " ":
		draw_rect(Rect2(px, py, T, T), Color("0d1119") if (m.id == "f1" or m.id == "f2") else Color("07070b"))
		return
	if FLOOR_COL.has(ch) or C.is_link_ch(ch) or "POx-".contains(ch):
		_floor(m, ch, x, y, px, py)
	var t := sim.time
	match ch:
		"#", "H":
			_wall(m, x, y, px, py)
		"T", "Y":
			_wall(m, x, y, px, py)
			draw_rect(Rect2(px + 13, py + 16, 6, 10), Color("2b2218"))
			if ch == "T":
				var f := 0.8 + 0.2 * sin(t * 13.0 + x * 3) + 0.1 * sin(t * 31.0 + y)
				DrawUtil.ellipse(self, Vector2(px + 16, py + 13), 4 * f, 7 * f, Color("ffb347"))
				DrawUtil.ellipse(self, Vector2(px + 16, py + 14), 2, 3.5 * f, Color("fff2b0"))
		"W":
			_wall(m, x, y, px, py)
			draw_rect(Rect2(px + 5, py + 5, 22, 20), Color("9cc7e0") if m.day else Color("25344d"))
			draw_rect(Rect2(px + 15, py + 5, 2, 20), Color("1e2129"))
			draw_rect(Rect2(px + 5, py + 14, 22, 2), Color("1e2129"))
		"h":
			_wall(m, x, y, px, py)
			draw_rect(Rect2(px + 7, py + 8, 18, 18), Color("333333") if m.tripwires_off else Color("3c2d58"))
			draw_rect(Rect2(px + 9, py + 10, 14, 14), Color("555555") if m.tripwires_off else Color("8b6fd0"), false, LINE_W)
		"D", "L", "K", "Z":
			var col: Color = {"D": Color("6b4a2b"), "L": Color("5e3f22"), "K": Color("596170"), "Z": Color("3a2c20")}[ch]
			draw_rect(Rect2(px, py, T, T), Color("2a2e38"))
			draw_rect(Rect2(px + 2, py + 2, T - 4, T - 4), col)
			draw_rect(Rect2(px + 10, py + 2, 1, T - 4), Color(0, 0, 0, 0.25))
			draw_rect(Rect2(px + 21, py + 2, 1, T - 4), Color(0, 0, 0, 0.25))
			if ch == "L":
				draw_circle(Vector2(px + 24, py + 17), 3, Color("e0b44c"))
			elif ch == "K":
				draw_rect(Rect2(px + 2, py + 8, T - 4, 3), Color("e0b44c"))
				draw_rect(Rect2(px + 2, py + 21, T - 4, 3), Color("e0b44c"))
			elif ch == "Z":
				draw_rect(Rect2(px + 2, py + 10, T - 4, 4), Color("7a6040"))
				draw_rect(Rect2(px + 2, py + 19, T - 4, 4), Color("7a6040"))
		"O":
			if C.WALLISH_CH.contains(m.tile(x, y - 1)):
				draw_rect(Rect2(px, py, 5, T), Color("6b4a2b"))
			else:
				draw_rect(Rect2(px, py, T, 5), Color("6b4a2b"))
		"B":
			draw_rect(Rect2(px, py, T, T), Color("3a3d47"))
			draw_rect(Rect2(px + 2, py + 6, T - 4, T - 12), Color("6b4a2b"))
			draw_rect(Rect2(px + 2, py + 6, T - 4, 4), Color("7d5a37"))
		"m":
			draw_rect(Rect2(px, py, T, T), Color("3a3d47"))
			draw_rect(Rect2(px + 4, py, T - 8, T), Color("7a5a3a"))
			draw_rect(Rect2(px + 4, py, 6, T), Color("a07a4e"))
		"I":
			_floor(m, ":", x, y, px, py)
			draw_circle(Vector2(px + 16, py + 16), 11, Color("cfc8b8"))
			draw_circle(Vector2(px + 16, py + 16), 6, Color("a9a291"))
		"n":
			_floor(m, ":", x, y, px, py)
			draw_rect(Rect2(px + 2, py + 4, 28, 22), Color("6b4a2b"))
			for rr in [Rect2(px + 5, py + 7, 9, 7), Rect2(px + 17, py + 8, 10, 9), Rect2(px + 7, py + 16, 8, 7)]:
				draw_rect(rr, Color("e8e1cf"))
		"t":
			_floor(m, ":", x, y, px, py)
			draw_rect(Rect2(px + 13, py + 18, 6, 12), Color("4a3a28"))
			draw_circle(Vector2(px + 16, py + 13), 14, Color("24402a"))
			draw_circle(Vector2(px + 12, py + 10), 7, Color("2f5535"))
		"~":
			draw_rect(Rect2(px, py, T, T), Color("2a4c6a"))
			draw_rect(Rect2(px + fmod(t * 8.0 + x * 9, 28.0), py + fmod(y * 7.0, 24.0) + 4, 6, 2), Color(0.7, 0.86, 1.0, 0.18))
		"P":
			draw_circle(Vector2(px + 16, py + 17), 12, Color("8c8577"))
			draw_circle(Vector2(px + 16, py + 15), 10, Color("b5ad9c"))
			if sim.tower["relic"] == "pedestal" and m.id == "f2":
				phoenix_icon(self, Vector2(px + 16, py + 12), 1.0)
		"-":
			var col := Color("c79bff") if m.wire_moved.has(i) else Color("c9b27a")
			var vertical := not (m.is_solid(x - 1, y) or m.is_solid(x + 1, y))
			if vertical:
				draw_line(Vector2(px + 16, py), Vector2(px + 16, py + T), col, 1.5)
			else:
				draw_line(Vector2(px, py + 16), Vector2(px + T, py + 16), col, 1.5)
			draw_rect(Rect2(px + 14, py + 14, 4, 4), Color("e0b44c"))
	if C.is_link_ch(ch) and Content.world["links"].has(ch):
		_draw_link(ch, px, py)
	if m.rune[i] == 1:
		var hot := m.cool[i] <= 0.0
		var col := Color(1.0, (90.0 + 40.0 * sin(t * 4.0 + x)) / 255.0, 0.24, 0.85) if hot else Color(0.47, 0.78, 1.0, 0.8)
		var c := Vector2(px + 16, py + 16)
		draw_arc(c, 9, 0, TAU, 24, col, 2.0)
		draw_line(c + Vector2(-7, 0), c + Vector2(7, 0), col, 2.0)
		draw_line(c + Vector2(0, -7), c + Vector2(0, 7), col, 2.0)


func _draw_link(ch: String, px: float, py: float) -> void:
	var kind: String = Content.world["links"][ch]["kind"]
	match kind:
		"stairs":
			draw_rect(Rect2(px + 3, py + 3, 26, 26), Color("5b5f6c"))
			for k in 5:
				draw_rect(Rect2(px + 3, py + 6 + k * 5, 26, 2), Color("2a2e38"))
		"trellis":
			for k in 3:
				draw_line(Vector2(px + 4 + k * 10, py + 2), Vector2(px + 10 + k * 10, py + 30), Color("4f7d3c"), 2.0)
			draw_rect(Rect2(px + 4, py + 2, 24, 28), Color("7a5a3a"), false, 2.0)
		"vent":
			draw_rect(Rect2(px + 5, py + 5, 22, 22), Color("16181d"))
			if sim.link_state.get(ch, {}).get("locked", true):
				for k in 4:
					draw_rect(Rect2(px + 7 + k * 5, py + 5, 2, 22), Color("7a5a3a"))
		"dumbwaiter":
			draw_rect(Rect2(px + 6, py + 6, 20, 20), Color("4a3a28"))
			draw_rect(Rect2(px + 9, py + 9, 14, 14), Color("1e2129"))
			draw_line(Vector2(px + 16, py), Vector2(px + 16, py + 9), Color("c9b27a"), 1.0)
		"gate":
			for k in 5:
				draw_rect(Rect2(px + 3 + k * 6, py + 2, 3, 28), Color("2b2e36"))
			draw_rect(Rect2(px + 2, py + 2, 28, 3), Color("e0b44c"))


static func phoenix_icon(ci: CanvasItem, c: Vector2, s: float) -> void:
	ci.draw_circle(c, 16 * s, Color(1.0, 0.78, 0.35, 0.22))
	ci.draw_circle(c, 9 * s, Color(1.0, 0.86, 0.47, 0.25))
	var pts := PackedVector2Array([Vector2(0, -7), Vector2(10, -2), Vector2(3, 0), Vector2(6, 7), Vector2(0, 3), Vector2(-6, 7), Vector2(-3, 0), Vector2(-10, -2)])
	for k in pts.size():
		pts[k] = c + pts[k] * s
	ci.draw_colored_polygon(pts, Color("f2c04e"))
	ci.draw_circle(c + Vector2(0, -4) * s, 2 * s, Color("fff4c8"))


func _draw_surface(m: GameMap, x: int, y: int) -> void:
	var i := m.idx(x, y)
	var s := m.surface[i]
	var px := float(x * T)
	var py := float(y * T)
	var h := DrawUtil.tile_hash(x, y)
	if s == C.S_WET:
		draw_rect(Rect2(px, py, T, T), Color(0.31, 0.55, 0.86, 0.28))
	elif s == C.S_ICE:
		draw_rect(Rect2(px, py, T, T), Color(0.8, 0.94, 1.0, 0.55))
		draw_polyline(PackedVector2Array([Vector2(px + 4, py + 8 + h * 10), Vector2(px + 18, py + 16), Vector2(px + 28, py + 10 + DrawUtil.tile_hash(y, x) * 14)]), Color(1, 1, 1, 0.7), 1.0)
	elif s == C.S_GREASE:
		draw_rect(Rect2(px, py, T, T), Color(0.88, 0.65, 0.18, 0.38))
		DrawUtil.ellipse(self, Vector2(px + 10 + h * 12, py + 12), 7, 3, Color(1.0, 0.92, 0.67, 0.35), 0.4)
	elif s == C.S_BURN:
		draw_rect(Rect2(px, py, T, T), Color(1.0, (100.0 + 50.0 * sin(sim.time * 9.0 + x)) / 255.0, 0.12, 0.6))
		for k in 3:
			var fx := px + 6 + k * 9
			var fh := 8.0 + 6.0 * absf(sin(sim.time * 10.0 + k + x))
			draw_colored_polygon(PackedVector2Array([Vector2(fx - 4, py + 26), Vector2(fx, py + 26 - fh), Vector2(fx + 4, py + 26)]), Color("ffd36b"))
	if m.ice_block[i] > 0.0:
		draw_rect(Rect2(px + 1, py + 1, T - 2, T - 2), Color(0.75, 0.92, 1.0, 0.92))
		draw_rect(Rect2(px + 4, py + 4, 8, 3), Color(1, 1, 1, 0.9))
		draw_rect(Rect2(px + 1, py + 1, T - 2, T - 2), Color(0.47, 0.7, 0.82, 0.9), false, 1.0)


func _draw_cloud(m: GameMap, x: int, y: int) -> void:
	var c := m.cloud[m.idx(x, y)]
	if c == C.C_NONE:
		return
	var col := Color(0.45, 0.45, 0.49, 0.78) if c == C.C_SMOKE else (Color(0.59, 0.73, 0.84, 0.72) if c == C.C_FOG else Color(0.93, 0.93, 0.95, 0.72))
	var p := Vector2(x * T + 16, y * T + 16)
	var t := sim.time
	draw_circle(p + Vector2(sin(t + x) * 3, cos(t * 1.3 + y) * 3), 15, col)
	draw_circle(p + Vector2(7 + cos(t * 0.8 + y) * 2, -6), 11, col)


# ---------- props & people ----------
func _draw_object(o: WorldObject) -> void:
	var p := Vector2(o.x, o.y) * T
	if o.held:
		draw_arc(p, 15, 0, TAU, 32, Color(0.75, 0.63, 1.0, 0.9), 2.0)
	match o.kind:
		"bust":
			draw_circle(p + Vector2(0, 3), 10, Color("77736b"))
			DrawUtil.ellipse(self, p + Vector2(0, 1), 7, 5, Color("e9e4d8"))
			draw_circle(p + Vector2(0, -5), 5.5, Color("e9e4d8"))
		"armor":
			draw_rect(Rect2(p.x - 8, p.y - 6, 16, 16), Color("5c636f"))
			draw_circle(p + Vector2(0, -8), 6, Color("8b939f"))
			draw_rect(Rect2(p.x - 4, p.y - 9, 8, 2), Color("1e2129"))
		"crate":
			draw_rect(Rect2(p.x - 11, p.y - 11, 22, 22), Color("7a5a3a"))
			draw_rect(Rect2(p.x - 11, p.y - 11, 22, 22), Color("4a3420"), false, 1.0)
			draw_line(p + Vector2(-11, -11), p + Vector2(11, 11), Color("4a3420"), 1.0)
			draw_line(p + Vector2(11, -11), p + Vector2(-11, 11), Color("4a3420"), 1.0)
		"bookcart":
			draw_rect(Rect2(p.x - 12, p.y - 6, 24, 14), Color("4a3420"))
			var cols := [Color("aa3333"), Color("3366aa"), Color("33aa66"), Color("aaaa33"), Color("883399")]
			for k in 5:
				draw_rect(Rect2(p.x - 11 + k * 4.5, p.y - 10, 4, 8), cols[k])
		"fern":
			draw_rect(Rect2(p.x - 6, p.y, 12, 9), Color("8a5a3a"))
			for k in range(-2, 3):
				draw_line(p, p + Vector2(k * 7, -12 + absi(k) * 3), Color("5ea35a"), 2.0)
		"relic":
			phoenix_icon(self, p, 1.2)


func _body(p: Vector2, r: float, col: Color, face = null) -> void:
	DrawUtil.ellipse(self, p + Vector2(0, r * 0.8), r, r * 0.45, Color(0, 0, 0, 0.3))
	draw_circle(p, r, col)
	draw_arc(p, r, 0, TAU, 24, Color(0, 0, 0, 0.45), 1.0)
	if face != null:
		draw_circle(p + Vector2(cos(face), sin(face)) * r * 0.6, r * 0.25, Color(1, 1, 1, 0.55))


func _draw_guard(g) -> void:
	var p := Vector2(g.x, g.y) * T
	if g.archmage:
		_draw_gilt(p, g.face, g.asleep)
		return
	if g.ko > 0.0 or g.slip > 0.0:
		DrawUtil.ellipse(self, p + Vector2(0, 4), 13, 7, Color("5a6272"), 0.3)
		DrawUtil.text(self, p + Vector2(10, -8 + sin(sim.time * 3.0) * 2), "z" if g.ko > 0.0 else "*", 13, Color("e8e1cf"))
		return
	_body(p, 10, Color("6d7787"), g.face)
	draw_line(p + Vector2(cos(g.face + 1.2), sin(g.face + 1.2)) * 9, p + Vector2(cos(g.face + 0.5), sin(g.face + 0.5)) * 18, Color("b9c0cc"), 2.0)
	if g.helmet:
		draw_rect(Rect2(p.x - 7, p.y - 9, 14, 10), Color("8f949c"))
		draw_rect(Rect2(p.x - 7, p.y - 3, 14, 2), Color("3a3d44"))
	if g.earmuffs:
		draw_circle(p + Vector2(-9, -2), 3.5, Color("e88bb0"))
		draw_circle(p + Vector2(9, -2), 3.5, Color("e88bb0"))
	if g.true_sight:
		var lens := p + Vector2(cos(g.face), sin(g.face)) * 7
		draw_circle(lens, 5, Color(1.0, 0.95, 0.63, 0.35))
		draw_circle(lens, 3, Color("fff3a0"))
	if g.cleats:
		for k in 3:
			draw_rect(Rect2(p.x - 6 + k * 5, p.y + 9, 2, 3), Color("cccccc"))


func _draw_gilt(p: Vector2, face: float, asleep: bool) -> void:
	_body(p, 15, Color("d9a93a"), face)
	draw_circle(p, 9, Color("f2d27a"))
	draw_colored_polygon(PackedVector2Array([p + Vector2(-8, -6), p + Vector2(0, -26), p + Vector2(8, -6)]), Color("5b2d83"))
	draw_circle(p + Vector2(0, -26), 2.5, Color("e0b44c"))
	if asleep:
		DrawUtil.text(self, p + Vector2(14, -14 + sin(sim.time * 2.0) * 3), "Zzz", 13, Color("e8e1cf"))


func _draw_npc(n) -> void:
	if not HubNpcs.present(sim, n):
		return
	var p := Vector2(n.x, n.y) * T
	match n.kind:
		"gilt":
			_draw_gilt(p, n.face, false)
			return
		"ladle":
			_body(p, 11, Color("e8e4dc"), n.face)
			draw_arc(p + Vector2(0, -3), 7, PI, TAU, 12, Color("c9c2b4"), 4.0)
			draw_line(p + Vector2(8, -4), p + Vector2(16, -14), Color("9aa0a8"), 2.0)
			draw_arc(p + Vector2(17, -15), 3, 0, TAU, 12, Color("9aa0a8"), 2.0)
			return
	_body(p, 9, Color("3b2f2f") if n.kind == "prefect" else Color("2f3b66"), n.face)
	match n.kind:
		"prefect":
			draw_rect(Rect2(p.x - 9, p.y - 1, 18, 3), Color("c0392b"))
		"snob":
			draw_arc(p + Vector2(3, -2), 3, 0, TAU, 12, Color("e0b44c"), 1.0)
			draw_rect(Rect2(p.x - 6, p.y - 11, 12, 3), Color.from_hsv(n.hue / 360.0, 0.55, 0.8))
		"duelist":
			draw_rect(Rect2(p.x - 9, p.y + 2, 18, 3), Color.from_hsv(n.hue / 360.0, 0.65, 0.85))
			DrawUtil.text_centered(self, p + Vector2(0, -12), "x", 12, Color("e0b44c"))
		_:
			draw_circle(p + Vector2(-5, -6), 2.5, Color.from_hsv(n.hue / 360.0, 0.55, 0.8))


func _draw_player() -> void:
	var pl := sim.player
	var p := Vector2(pl.x, pl.y) * T
	_body(p, 10, Color("6a4fa0"), pl.face)
	draw_colored_polygon(PackedVector2Array([p + Vector2(-8, -4), p + Vector2(cos(pl.face) * 4, -20 + sin(pl.face) * 2), p + Vector2(8, -4)]), Color("2c2142"))
	if pl.carrying != "":
		phoenix_icon(self, p + Vector2(0, -24), 1.1)
	if pl.posture == "sneak":
		draw_arc(p, 14, 0, TAU, 24, Color(0.65, 0.55, 0.85, 0.6), 1.0)


func _draw_plant(pl: Dictionary) -> void:
	var p := Vector2(pl["x"], pl["y"]) * T
	if pl["kind"] == "noisemaker":
		draw_circle(p, 8, Color("b8892f"))
		draw_line(p, p + Vector2(cos(sim.time * 4.0), sin(sim.time * 4.0)) * 6, Color("2a2015"), 1.0)
	else:
		draw_colored_polygon(PackedVector2Array([p + Vector2(0, -9), p + Vector2(7, 0), p + Vector2(0, 9), p + Vector2(-7, 0)]), Color("8fd3e8"))
	DrawUtil.text_centered(self, p + Vector2(0, -12), C.fmt_time(pl["timer"]), 11, Color("e8e1cf"))
