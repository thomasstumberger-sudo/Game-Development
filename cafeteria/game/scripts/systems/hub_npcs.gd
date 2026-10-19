class_name HubNpcs
## The Quad's people: wandering students, snobs, duelists, Mother Ladle, Gilt at office hours,
## and the prefect who tails you once Heat reaches Watched (spec §4.5).


static func build(sim: Sim) -> void:
	var hub: GameMap = sim.maps["hub"]
	var t: Dictionary = Content.text
	sim.npcs = []
	var snob_i := 0
	var duel_i := 0
	var s_i := 0
	for s in hub.spawns:
		var n := Entities.Npc.new()
		n.x = s["x"] + 0.5
		n.y = s["y"] + 0.5
		n.wait_t = randf_range(0.0, 3.0)
		n.home = Vector2i(s["x"], s["y"])
		match s["ch"]:
			"S":
				n.kind = "student"
				n.id = "st%d" % s_i
				n.display_name = "Student"
				n.line = t["student_lines"][s_i % t["student_lines"].size()]
				s_i += 1
				n.hue = fmod(s_i * 67.0, 360.0)
			"s":
				var sn: Dictionary = t["snobs"][snob_i]
				snob_i += 1
				n.kind = "snob"
				n.id = "sn%d" % snob_i
				n.display_name = sn["name"]
				n.snob = sn
				n.hue = fmod(snob_i * 97.0 + 20.0, 360.0)
			"d":
				var du: Dictionary = t["duelists"][duel_i]
				duel_i += 1
				n.kind = "duelist"
				n.id = du["id"]
				n.display_name = du["name"]
				n.duelist = du
				n.hue = 210.0 if du["id"] == "percival" else 320.0
			"M":
				n.kind = "ladle"
				n.id = "ladle"
				n.display_name = "Mother Ladle"
				n.face = 0.0
			"g":
				n.kind = "gilt"
				n.id = "gilt-hub"
				n.display_name = "Archmage Ostentia Gilt"
			_:
				continue
		sim.npcs.append(n)


static func present(sim: Sim, n: Entities.Npc) -> bool:
	if n.kind == "gilt":
		return sim.is_office_hours()
	if n.kind == "prefect":
		return sim.heat >= 40.0
	return true


static func find(sim: Sim, kind: String) -> Entities.Npc:
	for n in sim.npcs:
		if n.kind == kind:
			return n
	return null


static func update(sim: Sim) -> void:
	var p := sim.player
	var hub: GameMap = sim.maps["hub"]
	var pref := find(sim, "prefect")
	if sim.heat >= 40.0 and pref == null and p.map_id == "hub" and not sim.night:
		var n := Entities.Npc.new()
		n.kind = "prefect"
		n.id = "prefect"
		n.display_name = "Prefect Dunmore"
		n.x = 21.5
		n.y = 1.5
		n.home = Vector2i(21, 1)
		sim.npcs.append(n)
		sim.toast("A prefect has started following you. (Heat: Watched)", Color("e0a64c"))
	elif pref != null and sim.heat < 40.0:
		sim.npcs.erase(pref)

	for n in sim.npcs:
		if n.kind == "ladle" or n.kind == "gilt":
			continue
		var target: Variant = null
		var speed := 1.4
		if n.kind == "prefect":
			if p.map_id != "hub":
				continue
			if Vector2(n.x - p.x, n.y - p.y).length() > 3.2:
				target = Vector2i(floori(p.x), floori(p.y))
			speed = 2.6
			n.face = atan2(p.y - n.y, p.x - n.x)
		elif n.spectator_spot != null:
			target = n.spectator_spot
			speed = 2.4
		elif n.kind == "student":
			n.wait_t -= C.DT
			if n.path.is_empty() and n.wait_t <= 0.0:
				for tries in 8:
					var x := floori(n.home.x + randf_range(-7.0, 7.0))
					var y := floori(n.home.y + randf_range(-6.0, 6.0))
					if Pathfinder.npc_passable(hub, x, y, null) and hub.interior[hub.idx(x, y)] == 0:
						target = Vector2i(x, y)
						break
				n.wait_t = randf_range(2.0, 6.0)
		else:
			continue
		n.repath_t -= C.DT
		if target != null:
			var tv: Vector2i = target
			var goal_changed: bool = n.goal.is_empty() or n.goal["x"] != tv.x or n.goal["y"] != tv.y
			if goal_changed or n.repath_t <= 0.0:
				n.goal = {"map": "hub", "x": tv.x, "y": tv.y}
				n.repath_t = 1.0
				var res := Pathfinder.find(sim, ["hub"], {"map": "hub", "x": floori(n.x), "y": floori(n.y)}, n.goal, Pathfinder.npc_passable, false)
				n.path = res["path"]
		if not n.path.is_empty():
			if n.kind == "prefect" and Vector2(n.x - p.x, n.y - p.y).length() <= 3.0:
				n.path = []
				continue
			var s: Dictionary = n.path[0]
			var tx: float = s["x"] + 0.5
			var ty: float = s["y"] + 0.5
			var dx := tx - n.x
			var dy := ty - n.y
			var d := sqrt(dx * dx + dy * dy)
			if n.kind != "prefect":
				n.face = atan2(dy, dx)
			if d <= speed * C.DT:
				n.x = tx
				n.y = ty
				n.path.pop_front()
			else:
				n.x += dx / d * speed * C.DT
				n.y += dy / d * speed * C.DT
		elif n.spectator_spot != null:
			n.face = atan2(p.y - n.y, p.x - n.x)
