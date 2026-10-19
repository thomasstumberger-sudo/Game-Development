class_name C
## Tuning constants (spec §13, as shipped in §17.3). Sim units are tiles and seconds.

const TICK_RATE := 20
const DT := 1.0 / TICK_RATE
const TILE := 32

const PLAYER_SPEED := 3.2
const SNEAK_MULT := 0.5
const SPRINT_MULT := 1.6
const CARRY_MULT := 0.7
const PLAYER_R := 0.3
const OBJ_R := 0.35
const GUARD_R := 0.32
const SLIDE_ACCEL := 7.0
const SLIDE_DRAG := 0.97

const VISION_RANGE := 7.0
const VISION_HALF_ANGLE := deg_to_rad(40.0)
const ARCHMAGE_RANGE := 8.0
const ARCHMAGE_HALF_ANGLE := deg_to_rad(50.0)
const ARCHMAGE_SUSPICION_MULT := 3.0
const SUSPICION_RATE := 6.0
const SUSPICION_DECAY := 1.5
const CURIOUS_AT := 30.0
const SEARCH_AT := 60.0
const SEARCH_TIME := 12.0
const KO_TIME := 90.0
const SLIP_TIME := 6.0
const KO_MOMENTUM := 12.0
const CATCH_DIST := 0.7
const LOST_SIGHT_TIME := 4.0
const GUARD_SPEED := {"patrol": 1.8, "search": 2.2, "investigate": 2.6, "pursuit": 4.4, "return": 1.8}

const MANA_MAX := 100.0
const MANA_REGEN := 6.0
const MANA_REGEN_DELAY := 3.0

const ICE_MELT_TIME := 30.0
const ICE_BLOCK_TIME := 40.0
const DRY_TIME := 20.0
const GREASE_TIME := 60.0
const BURN_TIME := 10.0
const BURN_SPREAD := 2.0
const SMOKE_TIME := 8.0
const FOG_TIME := 12.0
const STEAM_TIME := 6.0
const COOL_TIME := 15.0
const SILENCE_TIME := 10.0
const SILENCE_R := 2.0
const REVEAL_TIME := 8.0
const REVEAL_R := 6.0
const GUST_IMPULSE := 18.0
const GUST_RANGE := 6.0
const GUST_HALF := deg_to_rad(35.0)
const SPELL_RANGE := {"magehand": 6.0, "grease": 5.0, "gust": 6.0, "douse": 5.0, "freeze": 5.0, "silence": 4.0, "reveal": 4.0}
const SPELL_COST := {"magehand": 10.0, "grease": 15.0, "gust": 12.0, "douse": 10.0, "freeze": 14.0, "silence": 18.0, "reveal": 8.0}
const THROW_RANGE := 6.0
const PLACE_RANGE := 1.6

const ALIBI_WINDOW := 10.0
const ALIBI_MIN_DIST := 25.0
const ALIBI_CLEAR := 3
const VACUUM_RADIUS := 18.0
const VACUUM_TIME := 45.0
const FLOOR_DIST := 10.0
const HEAT_DECAY_HUB := 0.5
const RETURN_CLOCK := 12.0 * 60.0
const HUB_MIN_PER_SEC := 0.5
const NOISEMAKER_SPOT_CHANCE := 0.05
const WITNESS_RANGE := 8.0
const WITNESS_SAMPLE := 0.25
const WITNESS_KEEP := 360.0
const ICE_RUNE_MELT := 180.0
const ICE_RUNE_MELT_HOT := 45.0

# surfaces (spec §5.1)
const S_DRY := 0
const S_WET := 1
const S_ICE := 2
const S_GREASE := 3
const S_BURN := 4
const SURFACE_FRICTION := [0.70, 0.85, 0.97, 0.98, 0.98]
# clouds — vision blockers
const C_NONE := 0
const C_SMOKE := 1
const C_FOG := 2
const C_STEAM := 3

const SPELLS := ["magehand", "grease", "gust", "douse", "silence"]
const SPELL_INFO := {
	"magehand": {"name": "Mage Hand", "cost": 10},
	"grease": {"name": "Grease", "cost": 15},
	"gust": {"name": "Gust", "cost": 12},
	"douse": {"name": "Douse", "cost": 10, "alt": "freeze", "alt_name": "Freeze", "alt_cost": 14},
	"silence": {"name": "Silence", "cost": 18, "alt": "reveal", "alt_name": "Reveal", "alt_cost": 8},
}
const TOOLS_ACTIVE := ["smoke", "noisemaker", "iceRune"]
const TOOL_NAMES := {"smoke": "Smoke Bomb", "noisemaker": "Noisemaker", "iceRune": "Ice-Rune"}
const DISTRACTION_KINDS := ["impact", "shatter", "glass", "clank", "movedwire"]

# tile classes (map characters — see data/maps/*.txt)
const SOLID_CH := "#TYWhPBmInZt~DLKH "
const OPAQUE_CH := "#TYhInZtDLKH "
const WALLISH_CH := "#TYWhHZDLK "


static func is_link_ch(ch: String) -> bool:
	return ch.length() == 1 and ch >= "1" and ch <= "9"


static func ang_diff(a: float, b: float) -> float:
	return wrapf(b - a, -PI, PI)


static func turn_toward(cur: float, target: float, rate: float) -> float:
	return cur + clampf(ang_diff(cur, target), -rate * DT, rate * DT)


static func fmt_time(s: float) -> String:
	var t := maxi(0, ceili(s))
	return "%d:%02d" % [t / 60, t % 60]
