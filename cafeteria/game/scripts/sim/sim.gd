class_name Sim
extends Node
## The whole game state and the fixed 20 Hz tick (spec §12). Views read it; they never own logic.
## Systems live in scripts/systems/ as static functions that take this node.

signal ui_request(kind: String, data: Dictionary)
signal talk_show(bbcode: String, duration: float)
signal talk_hide
signal sfx(kind: String, value: float)
signal camera_snap

# --- stage & clocks ---
var stage := "title"                    # title | act1 | intermission | act3 | trial | end
var paused := true
var time := 0.0
var hub_clock := 9.0 * 60.0 + 40.0      # campus minutes
var night := false
var dawn := false
var night_clock := C.RETURN_CLOCK
# --- meta ---
var heat := 0.0
var standing := 0
var merit := 25
# --- world ---
var maps := {}                          # id -> GameMap
var links := {}                         # digit -> [{"map","x","y"}, {"map","x","y"}]
var link_state := {}                    # digit -> {"locked": bool}
var player := Entities.Player.new()
var guards: Array[Entities.Guard] = []  # Gilt included (archmage = true)
var gilt: Entities.Guard
var npcs: Array[Entities.Npc] = []
var noise_rings: Array = []
var toasts: Array = []
var particles: Array = []
var plants: Array = []
var silences: Array = []
var incidents: Array = []
var witness_log: Array = []
var witness_t := 0.0
var reveal_t := 0.0
# --- selection & input (written by Main each frame, or by tests) ---
var sel := {"type": "spell", "id": "magehand"}
var spell_toggle := {"douse": false, "silence": false}
var tool_idx := 0
var noise_timer := 60
var mouse_world := Vector2.ZERO
var input_dir := Vector2.ZERO
var input_sneak := false
var input_sprint := false
# --- story state ---
var tower := {
	"ledger": {"melee_ko": 0, "env_ko": 0, "alerts": 0, "grease_casts": 0, "magehand_locks": 0, "noise_distractions": 0},
	"countermeasures": [], "relic": "pedestal", "return_clean": null, "vault_alert": false, "act1_done": false, "act3_done": false,
}
var notebook := {"roasts": ["int1", "fash1"], "comebacks": ["diet"], "log": []}
var snobs_talked := {}
var duels_won := {}
var attuned := false
var convo: Dictionary = {}
var duel: Dictionary = {}
var lock: Dictionary = {}
var trial: Dictionary = {}
var dead := false
var notices: Array = []
var seats := {"gilt": "against"}


func _ready() -> void:
	Content.ensure_loaded()
	notices = Content.text["notices_base"].duplicate()


# ---------- world building ----------
func init_world() -> void:
	maps["hub"] = GameMap.build("hub")
	player = Entities.Player.new()
	var hs: Dictionary = Content.world["hub_start"]
	player.x = hs["x"] + 0.5
	player.y = hs["y"] + 0.5
	HubNpcs.build(self)
	build_tower(false)
	set_day_flags()


func build_tower(is_night: bool) -> void:
	var cms: Array = tower["countermeasures"] if is_night else []
	var opts := {"heat_runes": is_night and cms.has("heatRunes"), "sap": is_night and cms.has("sap"), "wanted": heat >= 60.0}
	for id in Content.world["tower_maps"]:
		maps[id] = GameMap.build(id, opts)
	guards.clear()
	for d in Content.world["guards"]:
		if d.has("cm") and not (is_night and cms.has(d["cm"])):
			continue
		guards.append(GuardAI.make_guard(d, is_night, cms))
	if heat >= 60.0:
		for g in guards:
			g.suspicion = 20.0
	gilt = GuardAI.make_gilt(is_night)
	guards.append(gilt)
	link_state = {}
	plants = plants.filter(func(p): return not Content.world["tower_maps"].has(p["map"]))
	silences = []
	incidents = []
	reveal_t = 0.0
	index_links()
	set_day_flags()


func index_links() -> void:
	links = {}
	for id in maps.keys():
		var m: GameMap = maps[id]
		for y in m.h:
			for x in m.w:
				var ch := m.tiles[y * m.w + x]
				if C.is_link_ch(ch):
					if not links.has(ch):
						links[ch] = []
					links[ch].append({"map": id, "x": x, "y": y})


func link_other(ch: String, map_id: String, x: int, y: int) -> Dictionary:
	if not links.has(ch) or links[ch].size() != 2:
		return {}
	var ends: Array = links[ch]
	var a: Dictionary = ends[0]
	if a["map"] == map_id and a["x"] == x and a["y"] == y:
		return ends[1]
	return a


func set_day_flags() -> void:
	var day := (not night) or dawn
	for id in maps.keys():
		var m: GameMap = maps[id]
		if m.day != day:
			m.day = day
			m.light_dirty = true


func cur_map() -> GameMap:
	return maps[player.map_id]


# ---------- shared helpers ----------
func in_tower_stage() -> bool:
	return stage == "act1" or stage == "act3"


func toast(msg: String, color: Color = Color("e8e1cf"), duration: float = 3.2) -> void:
	toasts.append({"text": msg, "color": color, "t": 0.0, "dur": duration})


func log_note(msg: String) -> void:
	notebook["log"].push_front(msg)
	if notebook["log"].size() > 40:
		notebook["log"].pop_back()


func add_heat(v: float, why: String = "") -> void:
	heat = clampf(heat + v, 0.0, 100.0)
	if why != "":
		if v > 0:
			toast("Heat +%d: %s" % [int(v), why], Color("ff9d7a"))
		elif v < 0:
			toast("Heat %d: %s" % [int(v), why], Color("9fd89a"))


static func heat_band(h: float) -> Dictionary:
	if h < 20: return {"name": "Cold", "color": Color("7fb4d8")}
	if h < 40: return {"name": "Noticed", "color": Color("d8d27f")}
	if h < 60: return {"name": "Watched", "color": Color("e0a64c")}
	if h < 80: return {"name": "Wanted", "color": Color("e0704c")}
	return {"name": "Hunted", "color": Color("e04c4c")}


func is_office_hours() -> bool:
	if night or not (stage == "act1" or stage == "intermission"):
		return false
	return (int(floor(hub_clock)) % 60) < 30


func clock_text() -> String:
	var mins := int(floor(hub_clock))
	return "%d:%02d" % [(mins / 60) % 24, mins % 60]


func current_spell() -> String:
	var id: String = sel["id"]
	if id == "douse" and spell_toggle["douse"]:
		return "freeze"
	if id == "silence" and spell_toggle["silence"]:
		return "reveal"
	return id


func owns_phoenix() -> bool:
	return player.carrying == "phoenix" or ["owned", "stashed", "player"].has(tower["relic"]) or attuned


func entity_on_tile(map_id: String, x: int, y: int) -> bool:
	if player.map_id == map_id and floori(player.x) == x and floori(player.y) == y:
		return true
	for g in guards:
		if g.map_id == map_id and not g.away and floori(g.x) == x and floori(g.y) == y:
			return true
	return false


func is_revealed(map_id: String, x: int, y: int) -> bool:
	return reveal_t > 0.0 and player.map_id == map_id and Vector2(player.x - (x + 0.5), player.y - (y + 0.5)).length() <= C.REVEAL_R


func hand_pos() -> Vector2:
	var p := Vector2(player.x, player.y)
	var d := mouse_world - p
	var r: float = C.SPELL_RANGE["magehand"]
	if d.length() > r:
		d = d.normalized() * r
	return p + d


# ---------- the tick ----------
func _physics_process(_delta: float) -> void:
	if not paused and stage != "title":
		tick()


func tick() -> void:
	time += C.DT
	Flow.update_clock(self)
	PlayerCtl.update(self)
	Interact.update_lock(self)
	for id in maps.keys():
		PropPhysics.update_surfaces(maps[id])
		PropPhysics.update_objects(self, maps[id])
	for g in guards:
		GuardAI.update(self, g)
		if paused:
			break
	HubNpcs.update(self)
	Spells.update_plants(self)
	for inc in incidents:
		if not inc["checked"] and time >= inc["t"] + C.ALIBI_WINDOW:
			Alibi.run(self, inc)
	witness_t -= C.DT
	if witness_t <= 0.0:
		witness_t = C.WITNESS_SAMPLE
		Alibi.sample_witnesses(self)
	for s in silences:
		s["t"] -= C.DT
	silences = silences.filter(func(s): return s["t"] > 0.0)
	if reveal_t > 0.0:
		reveal_t -= C.DT
	if player.map_id == "hub":
		heat = maxf(0.0, heat - C.HEAT_DECAY_HUB * C.DT)
	for r in noise_rings:
		r["t"] += C.DT
	noise_rings = noise_rings.filter(func(r): return r["t"] < (1.4 if r["kind"] == "alarm" else 0.9))
	for pt in particles:
		pt["t"] += C.DT
		pt["x"] += pt["vx"] * C.DT
		pt["y"] += pt["vy"] * C.DT
		pt["vx"] *= 0.94
		pt["vy"] *= 0.94
	particles = particles.filter(func(pt): return pt["t"] < pt["life"])
	Talk.update_convo(self)


## Toasts age in real time (called from the frame loop) so they fade even behind a paused panel.
func age_toasts(delta: float) -> void:
	for t in toasts:
		t["t"] += delta
	toasts = toasts.filter(func(t): return t["t"] < t["dur"])
