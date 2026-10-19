extends Node
## Placeholder sound: tiny synthesized tones, generated once and cached, keyed to noise loudness.
## Swap for real samples by replacing _stream_for(); the Sim only ever emits sfx(kind, value).

const RATE := 22050
const VOICES := 8

var sim: Sim
var _players: Array[AudioStreamPlayer] = []
var _cache := {}
var _next := 0


func setup(p_sim: Sim) -> void:
	sim = p_sim
	for i in VOICES:
		var p := AudioStreamPlayer.new()
		add_child(p)
		_players.append(p)
	sim.sfx.connect(_on_sfx)


func _on_sfx(kind: String, value: float) -> void:
	match kind:
		"step":
			if value >= 5.0:
				_play("tri", 90.0, 0.05, 0.25)
		"alarm":
			_play("saw", 980.0, 0.5, 0.35, 600.0)
		"bell", "movedwire", "plant":
			_play("tri", 1320.0, 0.4, 0.4)
			_play("tri", 1660.0, 0.4, 0.25)
		"alert":
			_play("square", 440.0, 0.12, 0.35)
			_play("square", 660.0, 0.2, 0.35, 0.0, 0.11)
		"phoenix":
			var notes := [523.0, 659.0, 784.0, 1046.0, 1318.0]
			for i in notes.size():
				_play("saw", notes[i], 0.5, 0.25, 0.0, i * 0.09)
		"pin", "buy":
			_play("square", 880.0, 0.05, 0.2)
		"jam":
			_play("square", 140.0, 0.12, 0.25)
		_:
			if kind.begins_with("cast_"):
				var f: float = {"cast_magehand": 520.0, "cast_grease": 300.0, "cast_gust": 200.0, "cast_douse": 400.0,
					"cast_freeze": 900.0, "cast_silence": 260.0, "cast_reveal": 760.0}.get(kind, 500.0)
				_play("sine", f, 0.18, 0.3)
			elif value > 0.0:
				_play("tri", 120.0 + value * 30.0, 0.12 + value * 0.02, minf(0.45, 0.08 + value * 0.04))


func _play(wave: String, freq: float, dur: float, vol: float, slide_to: float = 0.0, delay: float = 0.0) -> void:
	if delay > 0.0:
		get_tree().create_timer(delay).timeout.connect(func(): _play(wave, freq, dur, vol, slide_to))
		return
	var p := _players[_next]
	_next = (_next + 1) % VOICES
	p.stream = _stream_for(wave, freq, dur, slide_to)
	p.volume_db = linear_to_db(vol)
	p.play()


func _stream_for(wave: String, freq: float, dur: float, slide_to: float) -> AudioStreamWAV:
	var key := "%s|%d|%d|%d" % [wave, int(freq), int(dur * 1000), int(slide_to)]
	if _cache.has(key):
		return _cache[key]
	var n := int(RATE * dur)
	var data := PackedByteArray()
	data.resize(n * 2)
	var phase := 0.0
	for i in n:
		var t := float(i) / n
		var f := freq if slide_to <= 0.0 else freq * pow(slide_to / freq, t)
		phase += f / RATE
		var x := fmod(phase, 1.0)
		var s := 0.0
		match wave:
			"sine": s = sin(TAU * x)
			"square": s = 1.0 if x < 0.5 else -1.0
			"saw": s = 2.0 * x - 1.0
			_: s = 4.0 * absf(x - 0.5) - 1.0
		var env := pow(1.0 - t, 2.0)
		data.encode_s16(i * 2, int(clampf(s * env * 0.6, -1.0, 1.0) * 32767.0))
	var st := AudioStreamWAV.new()
	st.format = AudioStreamWAV.FORMAT_16_BITS
	st.mix_rate = RATE
	st.stereo = false
	st.data = data
	_cache[key] = st
	return st
