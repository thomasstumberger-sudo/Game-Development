extends Node
## Root of the game scene: wires the Sim to its views, feeds input, drives the camera.
## Command-line: `-- --test` runs the headless test suite, `-- --shots` also saves screenshots.

@onready var sim: Sim = $Sim
@onready var world: Node2D = $World
@onready var cam: Camera2D = $Camera
@onready var ui = $UI/UiRoot
@onready var hud = $HUD/HudView
@onready var sfx = $Sfx

var feed_input := true      # tests switch this off and drive sim.input_* themselves


func _ready() -> void:
	InputSetup.register()
	sim.init_world()
	world.sim = sim
	$Darkness.sim = sim
	$Above.sim = sim
	hud.sim = sim
	ui.setup(sim)
	sfx.setup(sim)
	sim.camera_snap.connect(func(): update_camera(true))
	var args := OS.get_cmdline_user_args()
	if args.has("--test") or args.has("--shots"):
		var runner = load("res://scripts/tests/test_runner.gd").new()
		add_child(runner)
		runner.run(self, args.has("--shots"))
		return
	ui.show_title()
	update_camera(true)


func _process(delta: float) -> void:
	sim.age_toasts(delta)
	if feed_input:
		sim.mouse_world = world.get_global_mouse_position() / C.TILE
		sim.input_dir = Input.get_vector("move_left", "move_right", "move_up", "move_down")
		sim.input_sneak = Input.is_action_pressed("sneak")
		sim.input_sprint = Input.is_action_pressed("sprint")
	update_camera(false)


func update_camera(snap: bool) -> void:
	var p := sim.player
	var m := sim.cur_map()
	var vp := get_viewport().get_visible_rect().size
	var target := Vector2(p.x, p.y) * C.TILE
	var off := (get_viewport().get_mouse_position() - vp / 2.0) * 0.15
	target += off.clamp(Vector2(-90, -70), Vector2(90, 70))
	cam.limit_left = 0
	cam.limit_top = 0
	cam.limit_right = m.w * C.TILE
	cam.limit_bottom = m.h * C.TILE
	cam.position = target
	if snap:
		cam.reset_smoothing()


func _unhandled_input(event: InputEvent) -> void:
	if event.is_action_pressed("artifact"):
		Flow.press_artifact(sim)
		return
	if ui.panel_open():
		ui.handle_panel_key(event)
		return
	if sim.stage == "title" or sim.stage == "end":
		return
	if event is InputEventKey and event.is_echo():
		return
	for k in 5:
		if event.is_action_pressed("spell_%d" % (k + 1)):
			var s: String = C.SPELLS[k]
			if sim.sel["type"] == "spell" and sim.sel["id"] == s and C.SPELL_INFO[s].has("alt"):
				sim.spell_toggle[s] = not sim.spell_toggle[s]
			sim.sel = {"type": "spell", "id": s}
			return
	if event.is_action_pressed("tool_prev") or event.is_action_pressed("tool_next"):
		if sim.sel["type"] == "tool":
			var step := -1 if event.is_action_pressed("tool_prev") else 1
			sim.tool_idx = posmod(sim.tool_idx + step, C.TOOLS_ACTIVE.size())
		sim.sel = {"type": "tool", "id": C.TOOLS_ACTIVE[sim.tool_idx]}
	elif event.is_action_pressed("interact"):
		if not sim.lock.is_empty():
			Interact.lock_press(sim)
		elif not sim.paused and sim.duel.is_empty():
			var it := Interact.find(sim)
			if not it.is_empty():
				it["run"].call()
	elif event.is_action_pressed("stash"):
		if not sim.paused:
			Interact.stash_relic(sim)
	elif event.is_action_pressed("notebook"):
		ui.show_notebook()
	elif event.is_action_pressed("timer_down"):
		sim.noise_timer = maxi(15, sim.noise_timer - 15)
	elif event.is_action_pressed("timer_up"):
		sim.noise_timer = mini(300, sim.noise_timer + 15)
	elif event.is_action_pressed("cancel"):
		if not sim.lock.is_empty():
			sim.lock = {}
			sim.toast("Lockpicking abandoned.")
		elif not sim.player.held.is_empty():
			var hp := sim.hand_pos()
			Spells.drop_held(sim, floori(hp.x), floori(hp.y))
		elif not sim.duel.is_empty() and sim.duel["over"]:
			Talk.end_duel(sim)
	elif event.is_action_pressed("cast"):
		if sim.paused or not sim.duel.is_empty() or sim.dead:
			return
		if not sim.lock.is_empty() and sim.lock["magehand"]:
			return
		Spells.use_selected(sim)
	elif event.is_action_pressed("drop"):
		if not sim.player.held.is_empty():
			var hp := sim.hand_pos()
			Spells.drop_held(sim, floori(hp.x), floori(hp.y))
		sim.lock = {}
