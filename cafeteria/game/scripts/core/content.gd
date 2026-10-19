class_name Content
## Loads the editable game data once: data/content.json (writing), data/world.json (layout),
## data/maps/*.txt (ASCII maps, one character per tile — legend in the spec, §17).

static var text: Dictionary = {}
static var world: Dictionary = {}
static var maps: Dictionary = {}
static var _loaded := false


static func ensure_loaded() -> void:
	if _loaded:
		return
	text = _read_json("res://data/content.json")
	world = _read_json("res://data/world.json")
	for id in world["maps"].keys():
		maps[id] = _read_map("res://data/maps/%s.txt" % id)
	_loaded = true


static func _read_json(path: String) -> Dictionary:
	var f := FileAccess.open(path, FileAccess.READ)
	assert(f != null, "missing data file " + path)
	var parsed = JSON.parse_string(f.get_as_text())
	assert(parsed is Dictionary, "bad JSON in " + path)
	return parsed


## Rows are padded to the widest row, so editors that strip trailing spaces can't break a map.
static func _read_map(path: String) -> PackedStringArray:
	var f := FileAccess.open(path, FileAccess.READ)
	assert(f != null, "missing map " + path)
	var rows := PackedStringArray()
	var width := 0
	for line in f.get_as_text().split("\n"):
		rows.append(line.trim_suffix("\r"))
	while rows.size() > 0 and rows[rows.size() - 1] == "":
		rows.remove_at(rows.size() - 1)
	for l in rows:
		width = maxi(width, l.length())
	for i in rows.size():
		rows[i] = rows[i].rpad(width, " ")
	return rows


static func roast(id: String) -> Dictionary:
	return text["roasts"][id]


static func comeback(topic: String) -> String:
	return text["comebacks"][topic]
