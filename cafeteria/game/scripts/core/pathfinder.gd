class_name Pathfinder
## Multi-floor BFS (guards chase you up stairs, spec §4.4). 8-way, no corner cutting.

const DIRS := [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1),
	Vector2i(1, 1), Vector2i(1, -1), Vector2i(-1, 1), Vector2i(-1, -1)]


static func guard_passable(m: GameMap, x: int, y: int, obj_tiles) -> bool:
	if not m.inb(x, y):
		return false
	var i := m.idx(x, y)
	var ch := m.tiles[i]
	if ch != "D" and C.SOLID_CH.contains(ch):
		return false
	if m.ice_block[i] > 0.0 or m.surface[i] == C.S_BURN:
		return false
	if obj_tiles != null and obj_tiles.has(i):
		return false
	return true


static func npc_passable(m: GameMap, x: int, y: int, _obj_tiles) -> bool:
	return m.inb(x, y) and not m.is_solid(x, y)


## Returns {"ok": bool, "path": [{"map","x","y"}, ...]} — path excludes start, includes goal.
static func find(sim, map_ids: Array, from: Dictionary, to: Dictionary, passable: Callable, use_links: bool) -> Dictionary:
	var mi := {}
	for i in map_ids.size():
		mi[map_ids[i]] = i
	if not mi.has(from["map"]) or not mi.has(to["map"]):
		return {"ok": false, "path": []}
	var obj_sets := {}
	for id in map_ids:
		obj_sets[id] = sim.maps[id].object_tiles()
	var start: int = mi[from["map"]] * 4096 + int(from["y"]) * 64 + int(from["x"])
	var goal: int = mi[to["map"]] * 4096 + int(to["y"]) * 64 + int(to["x"])
	if start == goal:
		return {"ok": true, "path": []}
	var prev := {start: -1}
	var q := PackedInt32Array([start])
	var head := 0
	var found := false
	while head < q.size():
		var cur := q[head]
		head += 1
		if cur == goal:
			found = true
			break
		var cm: String = map_ids[cur / 4096]
		var cy := (cur % 4096) / 64
		var cx := cur % 64
		var m: GameMap = sim.maps[cm]
		for d in DIRS:
			var nx: int = cx + d.x
			var ny: int = cy + d.y
			if d.x != 0 and d.y != 0 and (not passable.call(m, cx + d.x, cy, null) or not passable.call(m, cx, cy + d.y, null)):
				continue
			var k: int = mi[cm] * 4096 + ny * 64 + nx
			if prev.has(k):
				continue
			if not passable.call(m, nx, ny, null if k == goal else obj_sets[cm]):
				continue
			prev[k] = cur
			q.append(k)
		if use_links:
			var ch := m.tile(cx, cy)
			if C.is_link_ch(ch) and Content.world["links"].has(ch) and Content.world["links"][ch]["guards"]:
				var o: Dictionary = sim.link_other(ch, cm, cx, cy)
				if not o.is_empty() and mi.has(o["map"]):
					var k2: int = mi[o["map"]] * 4096 + int(o["y"]) * 64 + int(o["x"])
					var om: GameMap = sim.maps[o["map"]]
					if not prev.has(k2) and passable.call(om, int(o["x"]), int(o["y"]), null if k2 == goal else obj_sets[o["map"]]):
						prev[k2] = cur
						q.append(k2)
	if not found:
		return {"ok": false, "path": []}
	var path: Array = []
	var k3 := goal
	while k3 != start:
		path.append({"map": map_ids[k3 / 4096], "y": (k3 % 4096) / 64, "x": k3 % 64})
		k3 = prev[k3]
	path.reverse()
	return {"ok": true, "path": path}
