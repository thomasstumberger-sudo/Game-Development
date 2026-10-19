class_name Flow
## Stage flow: Act 1 → Intermission → Act 3 → Trial (spec §2.1, §11), the campus clock, caught & death.


static func new_game(sim: Sim) -> void:
	sim.init_world()
	sim.stage = "act1"
	sim.paused = false
	sim.camera_snap.emit()
	sim.toast("Act 1 — steal the Phoenix. The Sunspire gate is east of the pavilion.", Color("e0b44c"), 6.0)


static func objective_text(sim: Sim) -> String:
	match sim.stage:
		"act1":
			if sim.player.carrying != "":
				return "Get the Phoenix out through the Sunspire gate (west edge of the grounds)."
			return "Act 1 — Steal the Phoenix from the Sunspire vault (top floor). Bring it out through the gate."
		"intermission":
			return "Intermission — Duel, gather comebacks, read the notice board. Begin the Return Trip at the Sunspire gate."
		"act3":
			if sim.tower["relic"] == "pedestal":
				return "Get out through the gate before dawn."
			return "Act 3 — Put the Phoenix back on its pedestal before dawn. Don't let the vault floor go loud."
	return ""


static func gate_allowed(sim: Sim, from: String) -> bool:
	if sim.stage == "act3":
		if from == "f0" and sim.tower["relic"] != "pedestal":
			sim.toast("Not until it's back on its pedestal.", Color("e0b44c"))
			return false
		return true
	if sim.stage == "intermission" and from == "hub":
		sim.ui_request.emit("confirm_return", {})
		return false
	return true


static func on_gate_passed(sim: Sim, from: String, _to: String) -> void:
	if sim.stage == "act1" and from == "f0" and sim.player.carrying != "":
		complete_act1(sim)
	elif sim.stage == "act3" and from == "f0":
		complete_act3(sim)


static func complete_act1(sim: Sim) -> void:
	var l: Dictionary = sim.tower["ledger"]
	var cms: Array = []
	if l["melee_ko"] >= 2: cms.append("helmets")
	if l["alerts"] == 0: cms.append("trueSight")
	if l["grease_casts"] >= 3: cms.append("heatRunes")
	if l["magehand_locks"] >= 2: cms.append("sap")
	if l["noise_distractions"] >= 3: cms.append("earmuffs")
	sim.tower["countermeasures"] = cms
	sim.tower["act1_done"] = true
	sim.player.carrying = ""
	sim.tower["relic"] = "owned"
	for c in cms:
		sim.notices.push_front(Content.text["countermeasures"][c]["notice"])
	sim.plants = sim.plants.filter(func(p): return not Content.world["tower_maps"].has(p["map"]))
	sim.stage = "intermission"
	sim.ui_request.emit("act1_summary", {})


static func start_act3(sim: Sim, retry: bool = false) -> void:
	sim.night = true
	sim.dawn = false
	sim.night_clock = C.RETURN_CLOCK
	sim.tower["vault_alert"] = false
	if not sim.convo.is_empty():
		Talk.end_convo(sim, "")
	sim.dead = false
	sim.player.hp = 3
	sim.lock = {}
	sim.build_tower(true)
	var p := sim.player
	var gate: Dictionary = Content.world["f0_gate"]
	p.map_id = "f0"
	p.x = gate["x"] + 1.5
	p.y = gate["y"] + 0.5
	p.vx = 0.0
	p.vy = 0.0
	p.held = {}
	p.carrying = "phoenix"
	sim.tower["relic"] = "player"
	sim.stage = "act3"
	sim.paused = false
	sim.camera_snap.emit()
	sim.toast("Again. Quieter this time." if retry else "Act 3 — the Return Trip. Dawn in 12 minutes.", Color("e0b44c"), 5.0)


static func complete_act3(sim: Sim) -> void:
	sim.tower["act3_done"] = true
	sim.tower["return_clean"] = not sim.tower["vault_alert"]
	sim.stage = "trial"
	Talk.start_trial(sim)


static func update_clock(sim: Sim) -> void:
	if sim.stage == "act1" or sim.stage == "intermission":
		var was_office := sim.is_office_hours()
		sim.hub_clock += C.HUB_MIN_PER_SEC * C.DT
		var now := sim.is_office_hours()
		if now != was_office:
			if now:
				sim.toast("Archmage Gilt descends to the pavilion for office hours. Her study is empty.", Color("e0b44c"), 5.0)
			else:
				sim.toast("Gilt's office hours end. She returns to her study.", Color("e0b44c"), 5.0)
				if not sim.convo.is_empty():
					Talk.end_convo(sim, "My hour is up. You may treasure this.")
	if sim.stage == "act3" and not sim.dawn:
		sim.night_clock -= C.DT
		if sim.night_clock <= 0.0:
			sim.dawn = true
			sim.night_clock = 0.0
			if sim.gilt != null:
				sim.gilt.asleep = false
				sim.gilt.awake_t = 0.0
			sim.set_day_flags()
			sim.toast("Dawn. Shift change. Archmage Gilt is awake.", Color("ff9d7a"), 6.0)


static func caught(sim: Sim, g: Entities.Guard) -> void:
	sim.sfx.emit("alert", 0.0)
	sim.paused = true
	sim.ui_request.emit("caught", {"name": g.display_name if g != null else "Someone"})


static func die(sim: Sim) -> void:
	sim.dead = true
	sim.paused = true
	sim.ui_request.emit("death", {"phoenix": sim.owns_phoenix()})


static func restart_stage(sim: Sim) -> void:
	sim.dead = false
	sim.player.hp = 3
	sim.lock = {}
	if not sim.convo.is_empty():
		Talk.end_convo(sim, "")
	if not sim.duel.is_empty():
		Talk.end_duel(sim)
	sim.heat = maxf(sim.heat, 40.0)
	var p := sim.player
	if sim.stage == "act3":
		start_act3(sim, true)
		return
	if sim.stage == "act1":
		sim.tower["relic"] = "pedestal"
		p.carrying = ""
		sim.build_tower(false)
	var hs: Dictionary = Content.world["hub_start"]
	p.held = {}
	p.map_id = "hub"
	p.x = hs["x"] + 0.5
	p.y = hs["y"] + 0.5
	p.vx = 0.0
	p.vy = 0.0
	sim.paused = false
	sim.camera_snap.emit()


static func press_artifact(sim: Sim) -> void:
	if sim.dead:
		sim.toast("Unavailable: You are dead.", Color("e0b44c"))
		return
	if not sim.duel.is_empty() and sim.duel.get("can_flex", false):
		Talk.duel_flex(sim)
		return
	if sim.owns_phoenix():
		sim.toast("The Phoenix Paradox can only be cast while dead. You are, regrettably, alive.", Color("e0b44c"), 4.0)
	else:
		sim.toast("You have no artifact to cast. Yet.")
