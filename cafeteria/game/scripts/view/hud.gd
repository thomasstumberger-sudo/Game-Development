extends Control
## Heads-up display: location & objective, Heat, mana, hearts, clock, hotbar, E prompt, toasts, lock UI.

var sim: Sim

const PANEL := Color(0.055, 0.055, 0.08, 0.84)
const EDGE := Color("5b4f3a")
const INK := Color("e8e1cf")
const DIM := Color("9a9384")
const GOLD := Color("e0b44c")


func _process(_delta: float) -> void:
	queue_redraw()


func _panel(r: Rect2) -> void:
	draw_rect(r, PANEL)
	draw_rect(r, EDGE, false, 1.0)


func _draw() -> void:
	if sim == null or sim.maps.is_empty() or sim.stage == "title":
		return
	var vs := get_viewport_rect().size
	var p := sim.player
	var m := sim.cur_map()
	# --- status panel ---
	_panel(Rect2(12, 12, 400, 136))
	DrawUtil.text(self, Vector2(24, 36), m.display_name, 17, GOLD)
	DrawUtil.text(self, Vector2(330, 36), "Merit %d" % sim.merit, 14, DIM)
	draw_multiline_string(ThemeDB.fallback_font, Vector2(24, 58), Flow.objective_text(sim), HORIZONTAL_ALIGNMENT_LEFT, 376, 14, 2, Color("cfc8b8"))
	var y := 96.0
	var band := Sim.heat_band(sim.heat)
	DrawUtil.text(self, Vector2(24, y + 10), "Heat", 14, DIM)
	draw_rect(Rect2(72, y, 210, 11), Color(0.13, 0.13, 0.13))
	draw_rect(Rect2(72, y, 210 * sim.heat / 100.0, 11), band["color"])
	DrawUtil.text(self, Vector2(292, y + 10), band["name"], 14, band["color"])
	y += 18
	DrawUtil.text(self, Vector2(24, y + 10), "Mana", 14, DIM)
	draw_rect(Rect2(72, y, 210, 11), Color(0.13, 0.13, 0.13))
	draw_rect(Rect2(72, y, 210 * p.mana / C.MANA_MAX, 11), Color("8b6fd0"))
	DrawUtil.text(self, Vector2(292, y + 11), "♥".repeat(maxi(0, p.hp)), 15, Color("e88b8b"))
	y += 22
	var clock := ""
	if sim.stage == "act3":
		clock = "Dawn — the Sunspire is awake" if sim.dawn else "Night — dawn in %s" % C.fmt_time(sim.night_clock)
	else:
		clock = "Campus %s · Gilt: %s" % [sim.clock_text(), "office hours at the pavilion" if sim.is_office_hours() else "in her study"]
	DrawUtil.text(self, Vector2(24, y + 6), clock, 14, Color("cfc8b8"))

	# --- hotbar ---
	var slots := C.SPELLS.size() + C.TOOLS_ACTIVE.size()
	var sw := 112.0
	var bx := vs.x / 2.0 - slots * sw / 2.0
	var by := vs.y - 66.0
	for k in C.SPELLS.size():
		var s: String = C.SPELLS[k]
		var info: Dictionary = C.SPELL_INFO[s]
		var alt: bool = sim.spell_toggle.get(s, false)
		var nm: String = info["alt_name"] if alt else info["name"]
		var cost: int = info["alt_cost"] if alt else info["cost"]
		var r := Rect2(bx + k * sw, by, sw - 6, 54)
		_panel(r)
		if sim.sel["type"] == "spell" and sim.sel["id"] == s:
			draw_rect(r.grow(-1), GOLD, false, 2.0)
		DrawUtil.text(self, r.position + Vector2(8, 21), "%d %s" % [k + 1, nm], 14, INK if p.mana >= cost else Color("776f60"))
		DrawUtil.text(self, r.position + Vector2(8, 42), "%d mana%s" % [cost, " ⇄" if info.has("alt") else ""], 12, DIM)
	for k in C.TOOLS_ACTIVE.size():
		var t: String = C.TOOLS_ACTIVE[k]
		var r := Rect2(bx + (C.SPELLS.size() + k) * sw, by, sw - 6, 54)
		_panel(r)
		if sim.sel["type"] == "tool" and sim.sel["id"] == t:
			draw_rect(r.grow(-1), GOLD, false, 2.0)
		DrawUtil.text(self, r.position + Vector2(8, 21), C.TOOL_NAMES[t], 14, INK if p.tools[t] > 0 else Color("776f60"))
		var sub := "×%d · [%s]" % [p.tools[t], C.fmt_time(sim.noise_timer)] if t == "noisemaker" else "×%d  (Q/R)" % p.tools[t]
		DrawUtil.text(self, r.position + Vector2(8, 42), sub, 12, DIM)
	DrawUtil.text(self, Vector2(bx, by - 8), "Snips %d · Glass cutter %d · Lockpicks · Crowbar · Master key" % [p.tools["snips"], p.tools["glassCutter"]], 12, DIM)

	# --- prompt / lock ---
	if not sim.lock.is_empty():
		_lock_ui(vs)
	elif not sim.paused and sim.duel.is_empty():
		var it := Interact.find(sim)
		if not it.is_empty():
			var txt := "E — " + str(it["label"])
			var w := DrawUtil.text_width(txt, 16) + 28
			_panel(Rect2(vs.x / 2.0 - w / 2.0, by - 50, w, 30))
			DrawUtil.text_centered(self, Vector2(vs.x / 2.0, by - 29), txt, 16, GOLD)
	if p.carrying != "":
		var txt := "CARRYING THE PHOENIX — slow, no sprint, no Mage Hand · Space to set it down"
		var w := DrawUtil.text_width(txt, 14) + 24
		_panel(Rect2(vs.x - w - 12, 12, w, 30))
		DrawUtil.text(self, Vector2(vs.x - w, 32), txt, 14, Color("f2c04e"))

	# --- toasts ---
	var ty := 72.0
	var shown: Array = sim.toasts.slice(maxi(0, sim.toasts.size() - 5))
	for t in shown:
		var a := 1.0
		if t["t"] < 0.2:
			a = t["t"] / 0.2
		elif t["t"] > t["dur"] - 0.5:
			a = maxf(0.0, (t["dur"] - t["t"]) / 0.5)
		var w := DrawUtil.text_width(t["text"], 15) + 28
		var cx := vs.x / 2.0 + 140
		var bg := PANEL
		bg.a *= a
		draw_rect(Rect2(cx - w / 2.0, ty - 19, w, 27), bg)
		var col: Color = t["color"]
		col.a = a
		DrawUtil.text_centered(self, Vector2(cx, ty), t["text"], 15, col)
		ty += 31


func _lock_ui(vs: Vector2) -> void:
	var l := sim.lock
	var r := Rect2(vs.x / 2.0 - 150, vs.y - 170, 300, 78)
	_panel(r)
	DrawUtil.text(self, r.position + Vector2(12, 20), "Mage Hand lockpicking" if l["magehand"] else "Lockpicking", 14, GOLD)
	DrawUtil.text(self, r.position + Vector2(160, 20), "E at peak glow · Esc stops", 12, DIM)
	var glow := Interact.lock_glow(sim)
	for k in int(l["pins"]):
		var col := Color(0.27, 0.27, 0.27)
		if k < l["set"]:
			col = Color("9fd89a")
		elif k == l["set"]:
			col = Color("d9534f") if l["jam"] > 0.0 else Color(1.0, (180.0 + 75.0 * glow) / 255.0, (80.0 + 120.0 * glow) / 255.0, 0.3 + 0.7 * glow)
		draw_rect(Rect2(r.position.x + 20 + k * 92, r.position.y + 32, 72, 34), col)
