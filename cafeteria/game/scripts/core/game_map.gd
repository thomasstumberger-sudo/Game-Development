class_name GameMap
extends RefCounted
## One floor: tiles plus every per-tile simulation layer (surfaces, clouds, ice, runes, light).

var id: String
var display_name: String
var building: String
var floor_index: int
var w: int
var h: int
var tiles := PackedStringArray()        # flat, one character per tile
var surface := PackedByteArray()
var s_timer := PackedFloat32Array()
var cloud := PackedByteArray()
var c_timer := PackedFloat32Array()
var ice_block := PackedFloat32Array()
var rune := PackedByteArray()
var cool := PackedFloat32Array()
var burn_spread := PackedFloat32Array()
var interior := PackedByteArray()
var light := PackedFloat32Array()
var light_dirty := true
var day := true
var objects: Array[WorldObject] = []
var wire_moved := {}                    # tile index -> true (wires the player re-strung)
var sapped := {}                        # tile index -> true (anti-magic sap on a lock)
var tripwires_off := false
var spawns: Array[Dictionary] = []
var revision := 0                       # bumps on any tile change, for views


static func build(map_id: String, opts: Dictionary = {}) -> GameMap:
	Content.ensure_loaded()
	var m := GameMap.new()
	var rows: PackedStringArray = Content.maps[map_id]
	var meta: Dictionary = Content.world["maps"][map_id]
	var kinds: Dictionary = Content.world["object_kinds"]
	m.id = map_id
	m.display_name = meta["name"]
	m.building = meta["building"]
	m.floor_index = int(meta["floor"])
	m.h = rows.size()
	m.w = rows[0].length()
	var n := m.w * m.h
	# packed arrays are value types — resize each one directly, never through a loop variable
	m.tiles.resize(n)
	m.surface.resize(n)
	m.cloud.resize(n)
	m.rune.resize(n)
	m.interior.resize(n)
	m.s_timer.resize(n)
	m.c_timer.resize(n)
	m.ice_block.resize(n)
	m.cool.resize(n)
	m.burn_spread.resize(n)
	m.light.resize(n)
	for y in m.h:
		for x in m.w:
			var ch := rows[y][x]
			var i := y * m.w + x
			if kinds.has(ch):
				var k: Dictionary = kinds[ch]
				m.objects.append(WorldObject.new(k["kind"], k["name"], float(k["mass"]), x + 0.5, y + 0.5, map_id))
				ch = _base_floor_for(rows, x, y)
			elif "@MsSdgG".contains(ch):
				m.spawns.append({"ch": ch, "x": x, "y": y})
				if map_id == "hub":
					ch = "." if (ch == "M" or ch == "g") else _base_floor_for(rows, x, y)
				else:
					ch = ","
			elif ch == "r":
				ch = "."
				if opts.get("heat_runes", false):
					m.rune[i] = 1
			elif ch == "L" and opts.get("sap", false):
				m.sapped[i] = true
			m.tiles[i] = ch
	# Wanted (Heat ≥ 60): the servant door is locked down (spec §4.5)
	if map_id == "f0" and opts.get("wanted", false):
		m.tiles[27 * m.w + 22] = "L"
	for r in meta["interior"]:
		for y in range(int(r[1]), int(r[3]) + 1):
			for x in range(int(r[0]), int(r[2]) + 1):
				m.interior[y * m.w + x] = 1
	return m


static func _base_floor_for(rows: PackedStringArray, x: int, y: int) -> String:
	var n := [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]
	for d in n:
		var c := _row_ch(rows, x + d.x, y + d.y)
		if c == ",":
			return ","
	for d in n:
		var c := _row_ch(rows, x + d.x, y + d.y)
		if c == ":" or c == "=":
			return ":"
	return "."


static func _row_ch(rows: PackedStringArray, x: int, y: int) -> String:
	if y < 0 or y >= rows.size() or x < 0 or x >= rows[y].length():
		return " "
	return rows[y][x]


# ---------- tile access ----------
func idx(x: int, y: int) -> int:
	return y * w + x


func inb(x: int, y: int) -> bool:
	return x >= 0 and y >= 0 and x < w and y < h


func tile(x: int, y: int) -> String:
	return tiles[y * w + x] if inb(x, y) else " "


func set_tile(x: int, y: int, ch: String) -> void:
	tiles[y * w + x] = ch
	light_dirty = true
	revision += 1


func is_solid(x: int, y: int) -> bool:
	if not inb(x, y):
		return true
	var i := y * w + x
	return C.SOLID_CH.contains(tiles[i]) or ice_block[i] > 0.0


func is_opaque(x: int, y: int, vision: bool) -> bool:
	if not inb(x, y):
		return true
	var i := y * w + x
	if C.OPAQUE_CH.contains(tiles[i]):
		return true
	if vision and (ice_block[i] > 0.0 or cloud[i] != C.C_NONE):
		return true
	return false


func surface_at(px: float, py: float) -> int:
	var tx := floori(px)
	var ty := floori(py)
	return surface[ty * w + tx] if inb(tx, ty) else C.S_DRY


func rune_hot(i: int) -> bool:
	return rune[i] == 1 and cool[i] <= 0.0


## Stepping ray between two continuous points; the start and end tiles themselves are ignored.
func ray_clear(x0: float, y0: float, x1: float, y1: float, vision: bool) -> bool:
	var dx := x1 - x0
	var dy := y1 - y0
	var steps := ceili(sqrt(dx * dx + dy * dy) / 0.2)
	var sx := floori(x0)
	var sy := floori(y0)
	var ex := floori(x1)
	var ey := floori(y1)
	for s in range(1, steps):
		var t := float(s) / steps
		var tx := floori(x0 + dx * t)
		var ty := floori(y0 + dy * t)
		if (tx == sx and ty == sy) or (tx == ex and ty == ey):
			continue
		if is_opaque(tx, ty, vision):
			return false
	return true


# ---------- light (spec §4.1) ----------
func ambient_for(i: int) -> float:
	if interior[i] == 1:
		if id == "hub":
			return 0.62 if day else 0.4      # the cafeteria is the one warm room
		return 0.14 if day else 0.05
	return 0.8 if day else 0.13


func recompute_light() -> void:
	var sources: Array[Vector4] = []        # x, y, radius, intensity
	for y in h:
		for x in w:
			var ch := tiles[y * w + x]
			if ch == "T":
				sources.append(Vector4(x + 0.5, y + 0.5, 5.5, 1.0))
			elif ch == "W" and day:
				sources.append(Vector4(x + 0.5, y + 0.5, 3.5, 0.6))
	for y in h:
		for x in w:
			var i := y * w + x
			var lv := ambient_for(i)
			if not C.WALLISH_CH.contains(tiles[i]):
				for s in sources:
					var d := Vector2(s.x - (x + 0.5), s.y - (y + 0.5)).length()
					if d >= s.z:
						continue
					var v := s.w * (1.0 - d / s.z)
					if v > lv and ray_clear(s.x, s.y, x + 0.5, y + 0.5, false):
						lv = v
			light[i] = minf(1.0, lv)
	# walls take the brightest neighbouring floor so the darkness overlay reads cleanly
	var copy := light.duplicate()
	for y in h:
		for x in w:
			var i := y * w + x
			if not C.WALLISH_CH.contains(tiles[i]):
				continue
			var lv := copy[i]
			for dy in range(-1, 2):
				for dx in range(-1, 2):
					var nx := x + dx
					var ny := y + dy
					if inb(nx, ny) and not C.WALLISH_CH.contains(tiles[ny * w + nx]):
						lv = maxf(lv, copy[ny * w + nx])
			light[i] = lv
	light_dirty = false


func light_at(px: float, py: float) -> float:
	if light_dirty:
		recompute_light()
	var tx := floori(px)
	var ty := floori(py)
	return light[ty * w + tx] if inb(tx, ty) else 0.0


func object_at(px: float, py: float, r: float) -> WorldObject:
	var best: WorldObject = null
	var bd := r
	for o in objects:
		var d := Vector2(o.x - px, o.y - py).length()
		if d < bd:
			bd = d
			best = o
	return best


func object_tiles() -> Dictionary:
	var s := {}
	for o in objects:
		s[idx(floori(o.x), floori(o.y))] = true
	return s
