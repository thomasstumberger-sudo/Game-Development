class_name Entities
## Plain data holders for everything that moves. Behaviour lives in scripts/systems/.


class Player:
	extends RefCounted
	var map_id := "hub"
	var x := 0.0
	var y := 0.0
	var vx := 0.0
	var vy := 0.0
	var face := 0.0
	var posture := "walk"            # sneak | walk | sprint
	var mana := C.MANA_MAX
	var mana_delay := 0.0
	var hp := 3
	var burn_t := 0.0
	var carrying := ""               # "" or "phoenix"
	var held: Dictionary = {}        # {} | {"kind": "obj", "obj": WorldObject} | {"kind": "wire"}
	var step_acc := 0.0
	var last_tile := -1
	var trip_cooldown := 0.0
	var tools := {"lockpicks": 1, "crowbar": 1, "snips": 3, "glassCutter": 2, "smoke": 2, "noisemaker": 1, "iceRune": 0}


class Guard:
	extends RefCounted
	var id := ""
	var display_name := ""
	var map_id := ""
	var home := ""                   # map the route lives on
	var x := 0.0
	var y := 0.0
	var vx := 0.0
	var vy := 0.0
	var face := 0.0
	var sweep_base := 0.0
	var sweep_t := 0.0
	var route: Array = []            # [[x, y], ...]; one point = sentry
	var wp := 0
	var wait_t := 0.0
	var state := "patrol"            # patrol | curious | search | pursuit | investigate | return
	var suspicion := 0.0
	var stim: Dictionary = {}        # {"map", "x", "y"}
	var path: Array = []             # [{"map","x","y"}, ...]
	var has_path := false
	var goal: Dictionary = {}
	var repath_t := 0.0
	var ko := 0.0
	var slip := 0.0
	var slip_immune := 0.0
	var sliding := false
	var blocked_t := 0.0
	var last_seen: Dictionary = {}
	var lost_t := 99.0
	var search_t := 0.0
	var search_phase := "goto"
	var inv_until := 0.0
	var curious_t := 0.0
	var body_seen := {}
	var alert_cooldown := 0.0
	var helmet := false
	var earmuffs := false
	var true_sight := false
	var cleats := false
	# archmage only
	var archmage := false
	var asleep := false
	var awake_t := 0.0
	var away := false


class Npc:
	extends RefCounted
	var id := ""
	var kind := ""                   # student | snob | duelist | ladle | gilt | prefect
	var display_name := ""
	var x := 0.0
	var y := 0.0
	var face := PI / 2
	var path: Array = []
	var goal: Dictionary = {}
	var repath_t := 0.0
	var wait_t := 0.0
	var home := Vector2i.ZERO
	var line := ""
	var hue := 0.0
	var snob: Dictionary = {}
	var duelist: Dictionary = {}
	var spectator_spot: Variant = null   # Vector2i or null
