class_name Talk
## Words as weapons: Gilt's office hours, snobs, the notebook, duels (spec §9.2) and the trial (§9.3).
## Pure logic — it fills sim.duel / sim.trial with BBCode lines and asks the UI to redraw.

const GOLD := "[color=#e0b44c]"
const DIM := "[color=#a59f8f]"


static func b(s: String) -> String:
	return s.replace("[", "[lb]")    # escape BBCode in authored lines


static func learn_comeback(sim: Sim, topic: String, quiet: bool = false) -> bool:
	if sim.notebook["comebacks"].has(topic):
		return false
	sim.notebook["comebacks"].append(topic)
	if not quiet:
		sim.toast("Comeback logged (%s)." % topic, Color("a58bd8"))
	return true


static func learn_roast(sim: Sim, id: String, quiet: bool = false) -> bool:
	if sim.notebook["roasts"].has(id):
		return false
	sim.notebook["roasts"].append(id)
	if not quiet:
		sim.toast("Roast logged (%s)." % Content.roast(id)["topic"], Color("a58bd8"))
	return true


static func buy(sim: Sim, id: String) -> void:
	for s in Content.text["shop"]:
		if s["id"] == id and sim.merit >= int(s["price"]):
			sim.merit -= int(s["price"])
			sim.player.tools[s["tool"]] += int(s["amount"])
			sim.sfx.emit("buy", 0.0)
			return


# ---------- snobs ----------
static func talk_snob(sim: Sim, n: Entities.Npc) -> void:
	var sn: Dictionary = n.snob
	var first: bool = not sim.snobs_talked.has(n.id)
	sim.snobs_talked[n.id] = true
	if sn["teaches"].has("comeback"):
		learn_comeback(sim, sn["teaches"]["comeback"])
	else:
		learn_roast(sim, sn["teaches"]["roast"])
	if first:
		sim.merit += 2
	var text := "%sYou:[/color] \"%s\"\n%s%s:[/color] \"%s\"" % [GOLD, b(sn["you_say"]), GOLD, b(sn["name"]), b(sn["they_say"])]
	if first:
		text += "\n%s— logged in your notebook. (+2 merit for the exchange)[/color]" % DIM
	sim.talk_show.emit(text, 7.0)


# ---------- Gilt's office hours (non-pausing: she is a credibility-4 witness while she talks) ----------
static func start_convo(sim: Sim) -> void:
	if not sim.convo.is_empty():
		return
	sim.convo = {"i": 0, "t": 0.0, "incident": false, "reacted": false}
	_show_convo_line(sim, Content.text["gilt_office_lines"][0])


static func _show_convo_line(sim: Sim, line: String) -> void:
	sim.talk_show.emit("%sArchmage Gilt:[/color] \"%s\"\n%sShe is a credibility-4 witness while she talks at you. Walk away to leave.[/color]" % [GOLD, b(line), DIM], 0.0)


static func end_convo(sim: Sim, last_line: String) -> void:
	sim.convo = {}
	if last_line != "":
		sim.talk_show.emit("%sArchmage Gilt:[/color] \"%s\"" % [GOLD, b(last_line)], 4.0)
	else:
		sim.talk_hide.emit()


static func update_convo(sim: Sim) -> void:
	var c := sim.convo
	if c.is_empty():
		return
	var gn = HubNpcs.find(sim, "gilt")
	var p := sim.player
	if gn == null or p.map_id != "hub" or Vector2(gn.x - p.x, gn.y - p.y).length() > 3.5:
		end_convo(sim, "")
		sim.toast("You slip away mid-sentence. She does not notice.")
		return
	if c["incident"] and not c["reacted"]:
		c["reacted"] = true
		c["t"] = 0.0
		_show_convo_line(sim, Content.text["gilt_incident_line"])
		return
	c["t"] += C.DT
	if c["t"] >= 3.8:
		c["t"] = 0.0
		c["i"] += 1
		var lines: Array = Content.text["gilt_office_lines"]
		if c["i"] >= lines.size():
			end_convo(sim, "")
			return
		_show_convo_line(sim, lines[c["i"]])


# ---------- duels ----------
static func start_duel(sim: Sim, n: Entities.Npc) -> void:
	if not sim.convo.is_empty():
		end_convo(sim, "")
	var p := sim.player
	sim.duel = {"opp": n.duelist, "ex": 0, "pw": 0, "ow": 0, "turn": "opp", "cur": {}, "msg": [], "over": false, "can_flex": false}
	# gather a crowd — every spectator is a credibility-1 alibi witness
	var hub: GameMap = sim.maps["hub"]
	var spots: Array = []
	for k in 10:
		var a := k / 10.0 * TAU
		var x := floori(p.x + cos(a) * 2.6)
		var y := floori(p.y + sin(a) * 2.6)
		if Pathfinder.npc_passable(hub, x, y, null):
			spots.append(Vector2i(x, y))
	var studs: Array = sim.npcs.filter(func(s): return s.kind == "student")
	studs.sort_custom(func(a, bb): return Vector2(a.x - p.x, a.y - p.y).length() < Vector2(bb.x - p.x, bb.y - p.y).length())
	for k in mini(6, mini(studs.size(), spots.size())):
		studs[k].spectator_spot = spots[k]
		studs[k].goal = {}
	_duel_next(sim)


static func _duel_next(sim: Sim) -> void:
	var d := sim.duel
	if d["pw"] >= 3 or d["ow"] >= 3 or d["ex"] >= 5:
		_duel_end(sim)
		return
	d["can_flex"] = false
	if d["turn"] == "opp":
		var roasts: Array = d["opp"]["roasts"]
		d["cur"] = {"by": "opp", "roast": roasts[d["ex"] % roasts.size()]}
	else:
		d["cur"] = {"by": "player"}
		d["can_flex"] = sim.owns_phoenix() and sim.tower["act1_done"]
	sim.ui_request.emit("duel", {})


static func duel_answer(sim: Sim, topic: String) -> void:
	var d := sim.duel
	var r := Content.roast(d["cur"]["roast"])
	var was_relic: bool = d["cur"]["by"] == "relic"
	if topic == r["topic"]:
		d["pw"] += 1
		d["msg"].append("%sYou:[/color] “%s” — [i]the crowd gasps.[/i]" % [GOLD, b(Content.comeback(topic))])
		if was_relic:
			sim.standing += 5
	else:
		d["ow"] += 1
		if topic != "":
			d["msg"].append("%sYou:[/color] “%s” — [i]it lands nowhere.[/i]" % [GOLD, b(Content.comeback(topic))])
		else:
			d["msg"].append("[i]You open your mouth. Nothing arrives.[/i]")
		learn_roast(sim, d["cur"]["roast"], true)
		if learn_comeback(sim, r["topic"], true):
			d["msg"].append("%sYou think of the perfect comeback on the walk home: “%s” (logged)[/color]" % [DIM, b(Content.comeback(r["topic"]))])
			sim.log_note("Learned the %s comeback the hard way, from %s." % [r["topic"], d["opp"]["name"]])
	d["ex"] += 1
	d["turn"] = "opp" if was_relic else "player"
	_duel_next(sim)


static func duel_throw(sim: Sim, id: String) -> void:
	var d := sim.duel
	var r := Content.roast(id)
	d["msg"].append("%sYou:[/color] “%s”" % [GOLD, b(r["text"])])
	if d["opp"]["knows"].has(r["topic"]):
		d["ow"] += 1
		d["msg"].append("%s%s:[/color] “%s”" % [GOLD, b(d["opp"]["name"]), b(Content.comeback(r["topic"]))])
		if learn_comeback(sim, r["topic"], true):
			d["msg"].append("%s...annoyingly good. Logged.[/color]" % DIM)
	else:
		d["pw"] += 1
		d["msg"].append("[i]%s sputters. Point to you.[/i]" % b(d["opp"]["name"]))
	d["ex"] += 1
	d["turn"] = "opp"
	_duel_next(sim)


static func duel_flex(sim: Sim) -> void:
	var d := sim.duel
	if d.is_empty() or not d["can_flex"]:
		return
	sim.attuned = true
	d["can_flex"] = false
	phoenix_burst(sim, sim.player.map_id, sim.player.x, sim.player.y)
	d["msg"].append("[i]A roaring spectral phoenix erupts from your hands in a pillar of holy fire. It looks around. It cannot do anything, because you are alive. It leaves.[/i]")
	d["cur"] = {"by": "relic", "roast": "relic1"}
	learn_roast(sim, "relic1", true)
	sim.ui_request.emit("duel", {})


static func phoenix_burst(sim: Sim, map_id: String, x: float, y: float) -> void:
	sim.sfx.emit("phoenix", 0.0)
	for k in 120:
		var a := randf_range(0.0, TAU)
		var sp := randf_range(1.0, 7.0)
		sim.particles.append({"map": map_id, "x": x, "y": y, "vx": cos(a) * sp, "vy": sin(a) * sp - 3.0, "t": 0.0, "life": randf_range(0.8, 2.0), "kind": "fire"})


static func _duel_end(sim: Sim) -> void:
	var d := sim.duel
	d["over"] = true
	var opp: Dictionary = d["opp"]
	if d["pw"] > d["ow"]:
		var first: bool = not sim.duels_won.has(opp["id"])
		sim.duels_won[opp["id"]] = true
		sim.merit += 20 if first else 5
		sim.standing += 10
		d["msg"].append("[b]You win.[/b] %s: “%s” %s(+%d merit, +10 standing)[/color]" % [b(opp["name"]), b(opp["win_line"]), DIM, 20 if first else 5])
	else:
		d["msg"].append("[b]You lose.[/b] %s: “%s” %s(but you learned something)[/color]" % [b(opp["name"]), b(opp["lose_line"]), DIM])
	sim.ui_request.emit("duel", {})


static func end_duel(sim: Sim) -> void:
	for s in sim.npcs:
		if s.spectator_spot != null:
			s.spectator_spot = null
			s.path = []
			s.goal = {}
	sim.duel = {}
	sim.ui_request.emit("duel_close", {})


# ---------- the Council trial (spec §9.3; Visual Punctuation as built, §17.2) ----------
static func start_trial(sim: Sim) -> void:
	var q: Array = Content.text["gilt_roasts"].duplicate()
	if sim.tower["return_clean"]:
		q.insert(2, Content.text["gilt_flex"])
	sim.trial = {"ego": 100, "comp": 100, "q": q, "i": 0, "punct": 1 if sim.attuned else 0, "msg": [], "done": ""}
	sim.paused = true
	sim.ui_request.emit("trial", {})


static func trial_answer(sim: Sim, a: String) -> void:
	var t := sim.trial
	var r: Dictionary = t["q"][t["i"]]
	if a == "slam":
		t["punct"] -= 1
		t["ego"] -= 10
		t["msg"].append("[i]The phantom Phoenix screams down onto the bench in a column of holy fire. The chamber goes silent. Gilt's roast dies in her mouth.[/i] (roast cancelled, Ego −10)")
		sim.sfx.emit("phoenix", 0.0)
	elif a == "insider" and r.get("insider", false):
		t["ego"] -= 40
		t["msg"].append("%sYou:[/color] “%s” — [i]someone on the bench snorts. Gilt looks at the relic. She looks at you. She does not know how you know.[/i] (Ego −40)" % [GOLD, b(Content.text["insider_line"])])
	elif a != "" and a == r["topic"]:
		t["ego"] -= 20
		t["msg"].append("%sYou:[/color] “%s” — [i]a murmur along the bench.[/i] (Ego −20)" % [GOLD, b(Content.comeback(a))])
	else:
		t["comp"] -= 20
		if a != "":
			t["msg"].append("%sYou:[/color] “%s” — [i]it does not answer what she said.[/i] (Composure −20)" % [GOLD, b(Content.comeback(a))])
		else:
			t["msg"].append("[i]Silence. The bad kind.[/i] (Composure −20)")
	t["i"] += 1
	if t["ego"] <= 0:
		t["done"] = "shattered"
	elif t["comp"] <= 0:
		t["done"] = "lost"
	elif t["i"] >= t["q"].size():
		t["done"] = "cracked" if t["ego"] <= 40 else "against"
	sim.ui_request.emit("trial", {})


static func finish_chapter(sim: Sim) -> void:
	var t := sim.trial
	sim.seats["gilt"] = "for" if t["done"] == "shattered" else ("abstain" if t["done"] == "cracked" else "against")
	if t["done"] == "shattered":
		sim.standing += 20
	sim.stage = "end"
	sim.ui_request.emit("end", {})
