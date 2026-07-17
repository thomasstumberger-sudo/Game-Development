"""Entity classes. These hold plain state; the game loop and combat.py
decide what movement/attack results mean. No per-frame allocation here --
draw() only blits already-cached surfaces from AssetManager.

Future work (out of scope for this pass): enemy AI/pathing, ranged
attacks, controller input.
"""

import pygame


class Entity:
    def __init__(self, x, y, sprite_name):
        self.x = x
        self.y = y
        self.sprite_name = sprite_name

    def draw(self, screen, tile_size):
        from engine.assets import AssetManager
        sprite = AssetManager.get_sprite(self.sprite_name)
        if sprite:
            screen.blit(sprite, (self.x * tile_size, self.y * tile_size))


class Enemy(Entity):
    def __init__(self, entity_id, enemy_type, x, y, stats):
        super().__init__(x, y, stats.get("sprite", "enemy"))
        self.id = entity_id
        self.type = enemy_type
        self.name = stats.get("name", enemy_type)
        self.max_hp = stats["hp"]
        self.hp = self.max_hp
        self.attack = stats["attack"]
        self.defense = stats["defense"]
        self.xp_reward = stats["xp_reward"]

    @property
    def alive(self):
        return self.hp > 0


class ItemPickup(Entity):
    def __init__(self, entity_id, item_type, x, y, item_def):
        super().__init__(x, y, item_def.get("sprite", "item"))
        self.id = entity_id
        self.type = item_type
        self.name = item_def.get("name", item_type)


class Player(Entity):
    def __init__(self, x, y, stats=None):
        super().__init__(x, y, "player")
        stats = stats or {}
        self.max_hp = stats.get("max_hp", 30)
        self.hp = stats.get("hp", self.max_hp)
        self.max_stamina = stats.get("max_stamina", 20)
        self.stamina = stats.get("stamina", self.max_stamina)
        self.xp = stats.get("xp", 0)
        self.level = stats.get("level", 1)
        self.attack = stats.get("attack", 5)
        self.defense = stats.get("defense", 1)
        self.facing = (0, 1)

    def try_move(self, dx, dy, room, enemies, items):
        """Resolve a single grid step: attack > exit > pickup > move > blocked.
        Does not mutate enemies/items -- caller applies combat/pickup effects."""
        self.facing = (dx, dy)
        new_x, new_y = self.x + dx, self.y + dy

        for enemy in enemies:
            if enemy.alive and enemy.x == new_x and enemy.y == new_y:
                return {"type": "attack", "enemy": enemy}

        if not room.is_walkable(new_x, new_y):
            return {"type": "blocked"}

        exit_data = room.exit_at(new_x, new_y)
        if exit_data is not None:
            self.x, self.y = new_x, new_y
            return {"type": "exit", "exit": exit_data}

        for item in items:
            if item.x == new_x and item.y == new_y:
                self.x, self.y = new_x, new_y
                return {"type": "pickup", "item": item}

        self.x, self.y = new_x, new_y
        return {"type": "moved"}
