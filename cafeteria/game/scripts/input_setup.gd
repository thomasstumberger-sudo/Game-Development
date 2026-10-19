class_name InputSetup
## Default key bindings, registered as InputMap actions so they can be rebound at runtime
## (a settings menu only has to call InputMap.action_erase_events / action_add_event).

const KEYS := {
	"move_up": [KEY_W, KEY_UP],
	"move_down": [KEY_S, KEY_DOWN],
	"move_left": [KEY_A, KEY_LEFT],
	"move_right": [KEY_D, KEY_RIGHT],
	"sneak": [KEY_C],             # not Ctrl: Ctrl+W closes browser tabs in the web export
	"sprint": [KEY_SHIFT],
	"interact": [KEY_E],
	"spell_1": [KEY_1],
	"spell_2": [KEY_2],
	"spell_3": [KEY_3],
	"spell_4": [KEY_4],
	"spell_5": [KEY_5],
	"tool_prev": [KEY_Q],
	"tool_next": [KEY_R],
	"timer_down": [KEY_BRACKETLEFT],
	"timer_up": [KEY_BRACKETRIGHT],
	"stash": [KEY_SPACE],
	"artifact": [KEY_F],
	"notebook": [KEY_TAB],
	"cancel": [KEY_ESCAPE],
}
const MOUSE := {
	"cast": MOUSE_BUTTON_LEFT,
	"drop": MOUSE_BUTTON_RIGHT,
}


static func register() -> void:
	for action in KEYS.keys():
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		for k in KEYS[action]:
			var ev := InputEventKey.new()
			ev.physical_keycode = k
			InputMap.action_add_event(action, ev)
	for action in MOUSE.keys():
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		var mb := InputEventMouseButton.new()
		mb.button_index = MOUSE[action]
		InputMap.action_add_event(action, mb)
