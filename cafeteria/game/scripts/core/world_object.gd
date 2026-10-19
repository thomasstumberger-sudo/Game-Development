class_name WorldObject
extends RefCounted
## A movable prop: bust, armor, crate, bookcart, fern — or the Phoenix when set down.

var kind: String
var display_name: String
var mass: float
var x: float
var y: float
var vx := 0.0
var vy := 0.0
var map_id: String
var held := false


func _init(p_kind: String, p_name: String, p_mass: float, px: float, py: float, p_map: String) -> void:
	kind = p_kind
	display_name = p_name
	mass = p_mass
	x = px
	y = py
	map_id = p_map
