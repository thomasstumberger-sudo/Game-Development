extends Node2D
## The gameplay light map drawn as darkness: one pixel per tile, scaled up with linear filtering
## (texture_filter = Linear on this node) so shadows fall off softly. Torches add a warm glow.

var sim: Sim
var _img: Image
var _tex: ImageTexture
var _glow: Node2D
var _glow_tex: GradientTexture2D


func _ready() -> void:
	_glow = Node2D.new()
	_glow.name = "TorchGlow"
	var mat := CanvasItemMaterial.new()
	mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	_glow.material = mat
	_glow.draw.connect(_draw_glow)
	var grad := Gradient.new()
	grad.set_color(0, Color(1.0, 0.67, 0.31, 0.17))
	grad.set_color(1, Color(1.0, 0.67, 0.31, 0.0))
	_glow_tex = GradientTexture2D.new()
	_glow_tex.gradient = grad
	_glow_tex.fill = GradientTexture2D.FILL_RADIAL
	_glow_tex.fill_from = Vector2(0.5, 0.5)
	_glow_tex.fill_to = Vector2(1.0, 0.5)
	_glow_tex.width = 128
	_glow_tex.height = 128
	add_child(_glow)


func _process(_delta: float) -> void:
	queue_redraw()
	_glow.queue_redraw()


func _draw() -> void:
	if sim == null or sim.maps.is_empty():
		return
	var m := sim.cur_map()
	if m.light_dirty:
		m.recompute_light()
	if _img == null or _img.get_width() != m.w or _img.get_height() != m.h:
		_img = Image.create(m.w, m.h, false, Image.FORMAT_RGBA8)
		_tex = null
	for y in m.h:
		for x in m.w:
			_img.set_pixel(x, y, Color(0.024, 0.024, 0.063, (1.0 - m.light[y * m.w + x]) * 0.84))
	if _tex == null:
		_tex = ImageTexture.create_from_image(_img)
	else:
		_tex.update(_img)
	draw_texture_rect(_tex, Rect2(0, 0, m.w * C.TILE, m.h * C.TILE), false)


func _draw_glow() -> void:
	if sim == null or sim.maps.is_empty():
		return
	var m := sim.cur_map()
	var r := DrawUtil.visible_tiles(self, m, 6)
	for y in range(r.position.y, r.end.y + 1):
		for x in range(r.position.x, r.end.x + 1):
			if m.tiles[y * m.w + x] != "T":
				continue
			var c := Vector2(x * C.TILE + 16, y * C.TILE + 18)
			_glow.draw_texture_rect(_glow_tex, Rect2(c - Vector2(90, 90), Vector2(180, 180)), false)
