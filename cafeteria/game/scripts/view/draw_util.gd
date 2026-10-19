class_name DrawUtil
## Small drawing helpers shared by the placeholder-art views.


static func ellipse(ci: CanvasItem, c: Vector2, rx: float, ry: float, col: Color, rot: float = 0.0, segments: int = 20) -> void:
	var pts := PackedVector2Array()
	for k in segments:
		var a := TAU * k / segments
		pts.append(c + Vector2(cos(a) * rx, sin(a) * ry).rotated(rot))
	ci.draw_colored_polygon(pts, col)


static func text(ci: CanvasItem, pos: Vector2, s: String, size: int, col: Color, align := HORIZONTAL_ALIGNMENT_LEFT, width := -1.0) -> void:
	ci.draw_string(ThemeDB.fallback_font, pos, s, align, width, size, col)


static func text_centered(ci: CanvasItem, pos: Vector2, s: String, size: int, col: Color) -> void:
	var w := ThemeDB.fallback_font.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x
	ci.draw_string(ThemeDB.fallback_font, pos - Vector2(w / 2.0, 0), s, HORIZONTAL_ALIGNMENT_LEFT, -1, size, col)


static func text_width(s: String, size: int) -> float:
	return ThemeDB.fallback_font.get_string_size(s, HORIZONTAL_ALIGNMENT_LEFT, -1, size).x


## World-space rectangle currently on screen (for culling), in tiles.
static func visible_tiles(ci: CanvasItem, m: GameMap, pad: int = 1) -> Rect2i:
	var inv := ci.get_viewport().get_canvas_transform().affine_inverse()
	var vr := ci.get_viewport().get_visible_rect()
	var a := inv * vr.position
	var b := inv * (vr.position + vr.size)
	var x0 := maxi(0, floori(a.x / C.TILE) - pad)
	var y0 := maxi(0, floori(a.y / C.TILE) - pad)
	var x1 := mini(m.w - 1, floori(b.x / C.TILE) + pad)
	var y1 := mini(m.h - 1, floori(b.y / C.TILE) + pad)
	return Rect2i(x0, y0, x1 - x0, y1 - y0)


static func tile_hash(x: int, y: int) -> float:
	var h: int = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
	h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
	return float((h ^ (h >> 16)) & 0xFFFFFFFF) / 4294967295.0
