extends Control
## Menus and dialogue panels, built from code with Godot Controls and one theme.
## Centre panels pause the Sim (title, shop, notebook, summaries, trial); the duel panel and the
## talk strip do not — the Alibi Engine needs the world to keep running while you talk.

var sim: Sim
var theme_main: Theme
var _center: PanelContainer
var _center_box: VBoxContainer
var _center_kind := ""
var _duel: PanelContainer
var _duel_box: VBoxContainer
var _talk: PanelContainer
var _talk_label: RichTextLabel
var _talk_timer := 0.0
var _notebook_tab := "comebacks"

const GOLD := "[color=#e0b44c]"
const DIM := "[color=#a59f8f]"
const CLOSABLE := ["notices", "shop", "notebook", "confirm_return"]


func setup(p_sim: Sim) -> void:
	sim = p_sim
	theme_main = _make_theme()
	theme = theme_main
	_talk = _make_panel()
	_talk.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_talk_label = RichTextLabel.new()
	_talk_label.bbcode_enabled = true
	_talk_label.fit_content = true
	_talk_label.custom_minimum_size = Vector2(680, 0)
	_talk_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_talk.get_node("Margin/Box").add_child(_talk_label)
	add_child(_talk)
	_center = _make_panel()
	_center.set_anchors_preset(Control.PRESET_CENTER)
	add_child(_center)
	_center_box = _center.get_node("Margin/Box")
	_duel = _make_panel()
	_duel.set_anchors_preset(Control.PRESET_CENTER_RIGHT)
	add_child(_duel)
	_duel_box = _duel.get_node("Margin/Box")
	_center.hide()
	_duel.hide()
	_talk.hide()
	sim.ui_request.connect(_on_ui_request)
	sim.talk_show.connect(_on_talk_show)
	sim.talk_hide.connect(func(): _talk.hide())


func _process(delta: float) -> void:
	if _talk_timer > 0.0 and sim.convo.is_empty():
		_talk_timer -= delta
		if _talk_timer <= 0.0:
			_talk.hide()
	var vs := get_viewport_rect().size
	if _talk.visible:
		_talk.position = Vector2(vs.x / 2.0 - _talk.size.x / 2.0, vs.y - _talk.size.y - 96)
	if _center.visible:
		_center.position = (vs - _center.size) / 2.0
	if _duel.visible:
		_duel.position = Vector2(vs.x - _duel.size.x - 16, vs.y - _duel.size.y - 90)


# ---------- theme & building blocks ----------
func _make_theme() -> Theme:
	var t := Theme.new()
	var base := ThemeDB.fallback_font
	var italic := FontVariation.new()
	italic.base_font = base
	italic.variation_transform = Transform2D(Vector2(1, 0), Vector2(0.2, 1), Vector2.ZERO)
	var bold := FontVariation.new()
	bold.base_font = base
	bold.variation_embolden = 0.8
	t.set_font("normal_font", "RichTextLabel", base)
	t.set_font("italics_font", "RichTextLabel", italic)
	t.set_font("bold_font", "RichTextLabel", bold)
	t.set_font_size("normal_font_size", "RichTextLabel", 16)
	t.set_font_size("italics_font_size", "RichTextLabel", 16)
	t.set_font_size("bold_font_size", "RichTextLabel", 16)
	t.set_color("default_color", "RichTextLabel", Color("e8e1cf"))
	var panel := StyleBoxFlat.new()
	panel.bg_color = Color(0.07, 0.07, 0.1, 0.95)
	panel.border_color = Color("5b4f3a")
	panel.set_border_width_all(2)
	panel.set_corner_radius_all(6)
	t.set_stylebox("panel", "PanelContainer", panel)
	var btn := StyleBoxFlat.new()
	btn.bg_color = Color("2a2419")
	btn.border_color = Color("5b4f3a")
	btn.set_border_width_all(1)
	btn.set_corner_radius_all(4)
	btn.content_margin_left = 12
	btn.content_margin_right = 12
	btn.content_margin_top = 7
	btn.content_margin_bottom = 7
	var hov := btn.duplicate()
	hov.bg_color = Color("3d331f")
	hov.border_color = Color("e0b44c")
	t.set_stylebox("normal", "Button", btn)
	t.set_stylebox("hover", "Button", hov)
	t.set_stylebox("pressed", "Button", hov)
	t.set_stylebox("focus", "Button", StyleBoxEmpty.new())
	var dis := btn.duplicate()
	dis.bg_color = Color(0.16, 0.14, 0.1, 0.5)
	t.set_stylebox("disabled", "Button", dis)
	t.set_color("font_color", "Button", Color("e8e1cf"))
	t.set_color("font_hover_color", "Button", Color("ffffff"))
	t.set_font_size("font_size", "Button", 15)
	return t


func _make_panel() -> PanelContainer:
	var p := PanelContainer.new()
	p.mouse_filter = Control.MOUSE_FILTER_STOP
	var mg := MarginContainer.new()
	mg.name = "Margin"
	for side in ["left", "right", "top", "bottom"]:
		mg.add_theme_constant_override("margin_" + side, 20)
	var box := VBoxContainer.new()
	box.name = "Box"
	box.add_theme_constant_override("separation", 8)
	mg.add_child(box)
	p.add_child(mg)
	return p


func _clear(box: VBoxContainer) -> void:
	for c in box.get_children():
		box.remove_child(c)
		c.queue_free()


func _rich(bbcode: String, width: float) -> RichTextLabel:
	var r := RichTextLabel.new()
	r.bbcode_enabled = true
	r.fit_content = true
	r.scroll_active = false
	r.custom_minimum_size = Vector2(width, 0)
	r.text = bbcode
	return r


func _button(label: String, fn: Callable, style := "", width := 0.0) -> Button:
	var b := Button.new()
	b.text = label
	b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	if width > 0.0:
		# wrapping only works with a known width; without one the button collapses to a sliver
		b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		b.custom_minimum_size = Vector2(width, 0)
	var col: Color = {"gold": Color("e0b44c"), "slam": Color("ffb3a8"), "insider": Color("d9c8ff")}.get(style, Color("e8e1cf"))
	b.add_theme_color_override("font_color", col)
	b.focus_mode = Control.FOCUS_NONE
	b.pressed.connect(fn)
	return b


## Opens the centre panel. buttons: [[label, Callable, style], ...]
func _open(kind: String, title: String, bbcode: String, buttons: Array, width := 760.0, pause := true) -> void:
	_center_kind = kind
	_clear(_center_box)
	var head := _rich("[font_size=26]%s%s[/color][/font_size]" % [GOLD, title], width)
	_center_box.add_child(head)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size = Vector2(width, 0)
	var body := _rich(bbcode, width - 16)
	scroll.add_child(body)
	_center_box.add_child(scroll)
	var maxh := get_viewport_rect().size.y - 190 - ceili(buttons.size() / 3.0) * 44
	scroll.custom_minimum_size.y = clampf(body.get_content_height() + 8, 40, maxf(120.0, maxh))
	body.finished.connect(func(): scroll.custom_minimum_size.y = clampf(body.get_content_height() + 8, 40, maxf(120.0, maxh)))
	var row := HFlowContainer.new()
	row.custom_minimum_size = Vector2(width, 0)
	for bdef in buttons:
		row.add_child(_button(bdef[0], bdef[1], bdef[2] if bdef.size() > 2 else ""))
	_center_box.add_child(row)
	_center.reset_size()
	_center.show()
	if sim.convo.is_empty():
		_talk.hide()
	if pause:
		sim.paused = true


func close_panel() -> void:
	_center.hide()
	_center_kind = ""
	_clear(_center_box)
	if sim.stage != "title" and sim.stage != "end" and sim.stage != "trial":
		sim.paused = false


func panel_open() -> bool:
	return _center.visible


func panel_kind() -> String:
	return _center_kind if _center.visible else ""


func handle_panel_key(event: InputEvent) -> void:
	if _center_kind == "notebook" and (event.is_action_pressed("notebook") or event.is_action_pressed("cancel")):
		close_panel()
	elif CLOSABLE.has(_center_kind) and event.is_action_pressed("cancel"):
		close_panel()


# ---------- routing ----------
func _on_ui_request(kind: String, data: Dictionary) -> void:
	match kind:
		"shop": show_shop()
		"notices": show_notices()
		"act1_summary": show_act1_summary()
		"confirm_return": show_confirm_return()
		"caught": show_caught(data.get("name", "Someone"))
		"death": show_death(data.get("phoenix", false))
		"trial": show_trial()
		"end": show_end()
		"duel": _render_duel()
		"duel_close": _duel.hide()


func _on_talk_show(bbcode: String, duration: float) -> void:
	_talk_label.text = bbcode
	_talk.reset_size()
	_talk.show()
	_talk_timer = duration if duration > 0.0 else 0.0


# ---------- panels ----------
func show_title() -> void:
	sim.stage = "title"
	_open("title", "Cafeteria Coup", "%s[i]Chapter 1 — The Sunspire[/i][/color]\n\n" % DIM +
		"At the Grand Arcane Academy, classes are optional because magic automates everything. The Archmages spend the budget on giant, useless relics. The students eat sludge. You have sworn an oath to win a seat on the Mage Council and fix the menu.\n\n" +
		"First target: [b]Archmage Ostentia Gilt[/b] and her [b]Radiant Resuscitation of the Eternal Sun[/b] — a phoenix that fully restores the caster in a pillar of holy fire. It can only be cast while dead.\n\n" +
		"%s[i]You already hold the Library logbook and the Clocktower master key (Library Intel and Key Extraction are cut from this slice).[/i][/color]\n\n" % DIM +
		"%sTHE PLAN[/color]\n[b]Act 1:[/b] steal the Phoenix.   [b]Intermission:[/b] duel, flex it, learn comebacks.   [b]Act 3:[/b] sneak it [i]back[/i] before dawn — Gilt will have bought security based on how you robbed her.   [b]Trial:[/b] out-talk her before the Council.\n\n" % GOLD +
		"%sCONTROLS[/color]\n[table=2][cell]WASD move · C (hold) sneak · Shift sprint   [/cell][cell]E interact · Space set relic down[/cell]" % GOLD +
		"[cell]1–5 spells (4/5 again: Freeze/Reveal)   [/cell][cell]Q/R tools · [ ] noisemaker timer[/cell]" +
		"[cell]Left click cast / use at cursor   [/cell][cell]F cast artifact · Tab notebook · Esc cancel[/cell][/table]\n\n" +
		"%s[i]Noise is drawn as rings. Vision cones go yellow → red as suspicion rises. Shadows hide you. Being seen is a resource, if somebody important is looking.[/i][/color]" % DIM,
		[["Begin", _begin, "gold"]])


func _begin() -> void:
	close_panel()
	Flow.new_game(sim)


func show_shop() -> void:
	var t: Dictionary = sim.player.tools
	var lines: Array = Content.text["ladle_lines"]
	var body := "%s[i]\"%s\"[/i][/color]\n\nMerit Points: %s%d[/color]\n\n" % [DIM, Talk.b(lines[randi() % lines.size()]), GOLD, sim.merit]
	var buttons: Array = []
	for s in Content.text["shop"]:
		body += "[b]%s[/b] — %d merit\n%s%s[/color]\n" % [s["name"], int(s["price"]), DIM, Talk.b(s["desc"])]
		var id: String = s["id"]
		buttons.append(["Buy %s (%d)" % [s["name"], int(s["price"])], func():
			Talk.buy(sim, id)
			show_shop()])
	body += "\n%sYou carry: %d smoke, %d noisemaker, %d ice-rune, %d snips, %d glass cutter, lockpicks, crowbar.[/color]" % [DIM, t["smoke"], t["noisemaker"], t["iceRune"], t["snips"], t["glassCutter"]]
	if sim.stage == "intermission":
		buttons.append(["\"Tonight, then. Put it back where it lives, love.\"", show_confirm_return, "gold"])
	buttons.append(["Leave", close_panel])
	_open("shop", "Mother Ladle's Counter", body, buttons)
	for b in _center_box.get_children()[-1].get_children():
		if b is Button and b.text.begins_with("Buy "):
			var price := int(b.text.get_slice("(", 1).trim_suffix(")"))
			b.disabled = sim.merit < price


func show_notices() -> void:
	var body := ""
	for n in sim.notices:
		body += "📜 %s\n\n" % Talk.b(n)
	_open("notices", "The Notice Board", body, [["Done", close_panel]])


func show_notebook(tab: String = "") -> void:
	if tab != "":
		_notebook_tab = tab
	var nb := sim.notebook
	var body := ""
	match _notebook_tab:
		"comebacks":
			for tp in Content.text["topics"]:
				if nb["comebacks"].has(tp):
					body += "“%s”  %s[%s][/color]\n" % [Talk.b(Content.comeback(tp)), DIM, tp]
				else:
					body += "%s— no %s comeback yet —[/color]\n" % [DIM, tp]
			body += "\n%s[i]Sources: roast the snobs in the quad; lose duel exchanges (you think of it on the walk home).[/i][/color]" % DIM
		"roasts":
			for id in nb["roasts"]:
				body += "“%s”  %s[%s][/color]\n" % [Talk.b(Content.roast(id)["text"]), DIM, Content.roast(id)["topic"]]
		"intel":
			body = "[b]From the Library logbook:[/b] Gilt keeps the Phoenix in the vault on the Sunspire's top floor. The Clocktower key (yours) opens the vault door.\n\n" + \
				"• Ward-lines cross the vault floor. [b]Reveal[/b] shows them; snipping the rune housing in the west wall kills them — it can be reached from the servant room next door.\n" + \
				"• Ways in: front door (sentry), servant door (south), the [b]dumbwaiter[/b] in the servant hall (to the pantry), the [b]ivy trellis[/b] on the north wall (to the gallery balcony), the [b]sewer vent[/b] in the southwest grounds (needs a crowbar).\n" + \
				"• The servant stair runs from the pantry to the top floor and comes out next to Gilt's study. Gilt is in her study except during [b]office hours (:00–:30)[/b], which she holds at the pavilion in the quad.\n" + \
				"• The Phoenix will not fit through trellises, dumbwaiters or vents. Plan the way out.\n\n" + \
				"[b]The Alibi Engine:[/b] plant a noisemaker inside the tower (set the timer with [lb] and ]), walk out, be seen (an Archmage talking at you counts 4, a prefect 2, each student 1; you need 3). When it fires, guards within %d tiles abandon their posts for %ds." % [int(C.VACUUM_RADIUS), int(C.VACUUM_TIME)]
		"ledger":
			body = "[table=2]"
			for k in sim.tower["ledger"].keys():
				body += "[cell]%s   [/cell][cell]%d[/cell]" % [k, sim.tower["ledger"][k]]
			body += "[/table]\n\n%s[i]The Archmage is keeping score. Act 1 habits buy Act 3 countermeasures.[/i][/color]" % DIM
			if not sim.tower["countermeasures"].is_empty():
				body += "\n\n%sBOUGHT[/color]\n" % GOLD
				for c in sim.tower["countermeasures"]:
					body += Content.text["countermeasures"][c]["name"] + "\n"
		"log":
			body = "\n".join(nb["log"].map(func(l): return Talk.b(l))) if not nb["log"].is_empty() else "%sNothing yet.[/color]" % DIM
	var buttons: Array = []
	for tb in ["comebacks", "roasts", "intel", "ledger", "log"]:
		var tab_id: String = tb
		buttons.append([("▸ " if tb == _notebook_tab else "") + tb.capitalize(), func(): show_notebook(tab_id), "gold" if tb == _notebook_tab else ""])
	buttons.append(["Close (Tab)", close_panel])
	_open("notebook", "Notebook", body, buttons)


func show_act1_summary() -> void:
	var l: Dictionary = sim.tower["ledger"]
	var cms: Array = sim.tower["countermeasures"]
	var rows := [["Crowbar takedowns", l["melee_ko"], "melee_ko ≥ 2", "helmets"], ["Alerts raised", l["alerts"], "alerts = 0", "trueSight"],
		["Grease casts", l["grease_casts"], "grease_casts ≥ 3", "heatRunes"], ["Locks picked by Mage Hand", l["magehand_locks"], "magehand_locks ≥ 2", "sap"],
		["Noise distractions", l["noise_distractions"], "noise_distractions ≥ 3", "earmuffs"]]
	var body := "%s[i]Archmage Gilt has not reported the theft. She cannot, without admitting the Sunspire was robbed. Instead, she has gone shopping.[/i][/color]\n\n%sTHE METHOD LEDGER[/color]\n[table=4]" % [DIM, GOLD]
	for r in rows:
		body += "[cell]%s   [/cell][cell]%d   [/cell][cell]%s%s[/color]   [/cell][cell]%s[/cell]" % [r[0], r[1], DIM, r[2], "[color=#ff9d7a][b]BOUGHT[/b][/color]" if cms.has(r[3]) else "—"]
	body += "[cell]Environmental knockouts   [/cell][cell]%d   [/cell][cell]%sno trigger[/color]   [/cell][cell]—[/cell][/table]\n\n%sTONIGHT'S SUNSPIRE[/color]\n" % [l["env_ko"], DIM, GOLD]
	for c in cms:
		body += "[b]%s[/b] — %s\n" % [Content.text["countermeasures"][c]["name"], Content.text["countermeasures"][c]["effect"]]
	body += "\n%s[i]The Return Trip happens tonight. Until then: duel in the quad, flex the Phoenix, collect comebacks. The trial is tomorrow morning.[/i][/color]" % DIM
	_open("act1_summary", "Act 1 complete — the Phoenix is yours (for now)", body, [["Back to the quad", close_panel, "gold"]])


func show_confirm_return() -> void:
	var body := "It is night. You carry the Phoenix back in, put it on its pedestal, and get out before dawn. If the vault floor goes loud, Gilt will be suspicious at the trial and will not flex the relic — and your best line goes with it.\n\n%sWAITING FOR YOU[/color]\n" % GOLD
	for c in sim.tower["countermeasures"]:
		body += "[b]%s[/b] — %s\n" % [Content.text["countermeasures"][c]["name"], Content.text["countermeasures"][c]["effect"]]
	var n: int = sim.notebook["comebacks"].size()
	body += "\n%s[i]Your notebook: %d comeback%s of 6. The trial needs answers for lineage, spellcraft, fashion, intellect and diet.[/i][/color]" % [DIM, n, "" if n == 1 else "s"]
	_open("confirm_return", "Begin the Return Trip?", body, [["Go tonight", func():
		close_panel()
		Flow.start_act3(sim), "gold"], ["Not yet", close_panel]])


func show_caught(guard_name: String) -> void:
	var lines := [
		"The Dean does not look up from his paperwork for a full minute. Then he says, \"Again?\" — which is unfair, because it is the first time.",
		"You are walked to the Dean's office by the ear. It is a long walk. The Dean has a lot of ears to get through today.",
		"The Dean reads your file aloud to a potted plant. The plant seems disappointed. You feel worse about the plant.",
	]
	_open("caught", "Caught", "%s has you by the collar.\n\n%s[i]%s[/i][/color]\n\nThe stage restarts. The Archmage still remembers what you did before you were caught — the Method Ledger is not wiped. Heat is set to at least 40." % [Talk.b(guard_name), DIM, lines[randi() % lines.size()]],
		[["Restart the stage", _restart, "gold"]])


func show_death(phoenix: bool) -> void:
	var body := "%s[i]Burning grease. A classic.[/i][/color]\n\n" % DIM
	if phoenix:
		body += "[color=#e0b44c][code][Press 'F' to cast Phoenix (Unavailable: You are dead)][/code][/color]\n\n"
	body += "The Academy's healers restore you for free. Magic automates everything; it just doesn't do it quickly. The stage restarts."
	_open("death", "You have died", body, [["Get up", _restart, "gold"]])


func _restart() -> void:
	close_panel()
	Flow.restart_stage(sim)


func show_trial() -> void:
	var t := sim.trial
	var bar := func(v: float, col: String) -> String:
		var n := clampi(int(round(v / 5.0)), 0, 20)
		return "[color=%s]%s[/color]%s%s[/color]" % [col, "█".repeat(n), "[color=#333333]", "█".repeat(20 - n)]
	var body := "%s[i]The Council chamber. Seven seats. Gilt's is the shiniest. %s[/i][/color]\n\n" % [DIM, "She has brought the Phoenix. She has no idea." if sim.tower["return_clean"] else "She keeps glancing at you. She did not bring the Phoenix."]
	body += "Gilt's Ego      %s  %d\nYour Composure  %s  %d\n\n" % [bar.call(float(t["ego"]), "#e0b44c"), t["ego"], bar.call(float(t["comp"]), "#a58bd8"), t["comp"]]
	var msgs: Array = t["msg"]
	for mline in msgs.slice(maxi(0, msgs.size() - 3)):
		body += mline + "\n\n"
	var buttons: Array = []
	if t["done"] != "":
		var outcome: Array = {"shattered": ["SHATTERED", "Gilt's seat votes with you — to save face."], "cracked": ["CRACKED", "Gilt abstains, in shame."],
			"against": ["UNMOVED", "Gilt votes against you."], "lost": ["COMPOSURE LOST", "You stammer. The Council moves on."]}[t["done"]]
		body += "%s%s[/color]\n%s" % [GOLD, outcome[0], outcome[1]]
		if t["done"] == "shattered" or t["done"] == "cracked":
			buttons.append(["Continue", func(): Talk.finish_chapter(sim), "gold"])
		else:
			buttons.append(["Request a retrial (notebook unchanged)", func(): Talk.start_trial(sim), "gold"])
			buttons.append(["Accept the result", func(): Talk.finish_chapter(sim)])
	else:
		var r: Dictionary = t["q"][t["i"]]
		body += "%sArchmage Gilt:[/color] “%s”" % [GOLD, Talk.b(r["text"])]
		if r.get("insider", false):
			buttons.append(["✦ Insider Knowledge: “%s”" % Content.text["insider_line"], func(): Talk.trial_answer(sim, "insider"), "insider"])
		for tp in sim.notebook["comebacks"]:
			var topic: String = tp
			buttons.append(["“%s”" % Content.comeback(topic), func(): Talk.trial_answer(sim, topic)])
		if t["punct"] > 0:
			buttons.append(["✦ VISUAL PUNCTUATION — call the phantom Phoenix down on the bench", func(): Talk.trial_answer(sim, "slam"), "slam"])
		buttons.append(["“...uh.”", func(): Talk.trial_answer(sim, "")])
	_open("trial", "The Council Trial — Archmage Ostentia Gilt", body, buttons)
	# one answer per line reads better than a flowing row
	var row: HFlowContainer = _center_box.get_children()[-1]
	for b in row.get_children():
		b.custom_minimum_size = Vector2(740, 0)


func show_end() -> void:
	var l: Dictionary = sim.tower["ledger"]
	var votes := 1 if sim.seats["gilt"] == "for" else 0
	var seat: String = {"for": "votes with you", "abstain": "abstains", "against": "votes against you"}[sim.seats["gilt"]]
	var body := "%s[i]The Sunspire[/i][/color]\n\nArchmage Gilt's seat: [b]%s[/b]. Council tally: [b]%d[/b] of the 4 votes you need. Standing: %d. Heat: %d.\n\n" % [DIM, seat, votes, sim.standing, int(round(sim.heat))]
	body += "Return Trip: %s Phantom Phoenix: %s. Takedowns %d, environmental KOs %d, alerts %d.\n\n" % [
		"clean — she flexed the relic, and you had the line." if sim.tower["return_clean"] else "loud — she kept the relic at home.",
		"attuned" if sim.attuned else "never flexed", l["melee_ko"], l["env_ko"], l["alerts"]]
	body += "[i]That evening, the student cafeteria. Mother Ladle sets a bowl down in front of you. It is sludge. It is beige.[/i]\n\n"
	body += "%sMother Ladle:[/color] \"Still sludge, love.\" [i]She pauses with the ladle in the air.[/i] \"For now.\"\n\n" % GOLD
	body += "%s[i]Three more towers. Three more relics. The Hothouse Spire, the Bulwark, the Ledger Tower. Somewhere, a lobster is being prepared for someone who has never been told no.[/i][/color]" % DIM
	_open("end", "Chapter 1 complete", body, [["Play again", func(): get_tree().reload_current_scene(), "gold"]])


# ---------- duel panel (non-pausing) ----------
func _render_duel() -> void:
	var d := sim.duel
	if d.is_empty():
		_duel.hide()
		return
	_clear(_duel_box)
	var w := 440.0
	var opp: Dictionary = d["opp"]
	var pips := func(n: int, col: String) -> String:
		var s := ""
		for i in 3:
			s += ("[color=%s]●[/color]" % col) if i < n else "[color=#444444]●[/color]"
		return s
	var head := "[font_size=22]%sDuel: %s[/color][/font_size]\n%s[i]%s[/i][/color]\nYou %s    %s %s" % [GOLD, Talk.b(opp["name"]), DIM, Talk.b(opp["title"]), pips.call(d["pw"], "#9fd89a"), Talk.b(opp["name"].get_slice(" ", opp["name"].get_slice_count(" ") - 1)), pips.call(d["ow"], "#d9534f")]
	_duel_box.add_child(_rich(head, w))
	var msgs: Array = d["msg"]
	var body := ""
	for mline in msgs.slice(maxi(0, msgs.size() - 3)):
		body += mline + "\n"
	if d["over"]:
		_duel_box.add_child(_rich(body, w))
		_duel_box.add_child(_button("Walk away", func(): Talk.end_duel(sim), "gold", w))
	elif d["cur"]["by"] == "opp" or d["cur"]["by"] == "relic":
		body += "%s%s:[/color] “%s”" % [GOLD, Talk.b(opp["name"]), Talk.b(Content.roast(d["cur"]["roast"])["text"])]
		_duel_box.add_child(_rich(body, w))
		for tp in sim.notebook["comebacks"]:
			var topic: String = tp
			_duel_box.add_child(_button("“%s”" % Content.comeback(topic), func(): Talk.duel_answer(sim, topic), "", w))
		_duel_box.add_child(_button("“...uh.”", func(): Talk.duel_answer(sim, ""), "", w))
	else:
		body += "%s[i]Your opening. Throw a roast%s.[/i][/color]" % [DIM, ", or flex the Phoenix (F)" if d["can_flex"] else ""]
		_duel_box.add_child(_rich(body, w))
		if d["can_flex"]:
			_duel_box.add_child(_button("✦ Flex the Radiant Resuscitation of the Eternal Sun", func(): Talk.duel_flex(sim), "gold", w))
		for id in sim.notebook["roasts"]:
			var rid: String = id
			_duel_box.add_child(_button("“%s”" % Content.roast(rid)["text"], func(): Talk.duel_throw(sim, rid), "", w))
	_duel.reset_size()
	_duel.show()
