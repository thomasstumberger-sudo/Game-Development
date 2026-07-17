"""Room templates: hand-authored, loaded once from data/rooms/*.json and
cached for the rest of the process. A Room is static (the grid, exits, and
enemy/item *templates*) -- which enemies are dead and which items have been
taken lives in save.py's per-room flags, applied by the caller when it spawns
live entities for a visit.

Future work (explicitly out of scope for this pass): procedural room
generation, scrolling/streamed maps.
"""

import json
import os

from engine.assets import BASE_DIR

ROOMS_DIR = os.path.join(BASE_DIR, "data", "rooms")

WALL = 1
FLOOR = 0

_ROOM_CACHE = {}


class Room:
    def __init__(self, room_id, data):
        self.id = room_id
        self.name = data.get("name", room_id)
        layout = data["layout"]
        self.height = len(layout)
        self.width = len(layout[0])
        self.grid = [
            [WALL if ch == "#" else FLOOR for ch in row]
            for row in layout
        ]
        self.exits = data.get("exits", [])
        self.enemy_templates = data.get("enemies", [])
        self.item_templates = data.get("items", [])

    def is_walkable(self, x, y):
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        return self.grid[y][x] == FLOOR

    def exit_at(self, x, y):
        for exit_data in self.exits:
            if exit_data["x"] == x and exit_data["y"] == y:
                return exit_data
        return None

    def draw(self, screen, tile_size):
        from engine.assets import AssetManager
        wall_sprite = AssetManager.get_sprite("wall")
        floor_sprite = AssetManager.get_sprite("floor")
        exit_sprite = AssetManager.get_sprite("exit")

        exit_coords = {(e["x"], e["y"]) for e in self.exits}

        for row in range(self.height):
            for col in range(self.width):
                pos = (col * tile_size, row * tile_size)
                if self.grid[row][col] == WALL:
                    sprite = wall_sprite
                    fallback_color = (50, 50, 50)
                elif (col, row) in exit_coords and exit_sprite is not None:
                    sprite = exit_sprite
                    fallback_color = (80, 140, 80)
                else:
                    sprite = floor_sprite
                    fallback_color = (30, 30, 30)

                if sprite is not None:
                    screen.blit(sprite, pos)
                else:
                    import pygame
                    pygame.draw.rect(screen, fallback_color, (*pos, tile_size, tile_size))

    @classmethod
    def load(cls, room_id):
        if room_id in _ROOM_CACHE:
            return _ROOM_CACHE[room_id]
        path = os.path.join(ROOMS_DIR, f"{room_id}.json")
        with open(path, "r") as f:
            data = json.load(f)
        room = cls(room_id, data)
        _ROOM_CACHE[room_id] = room
        return room
