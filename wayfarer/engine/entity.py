"""Entity classes. These hold plain state; the game loop and combat.py
decide what movement/attack results mean. No per-frame allocation here --
draw() only blits already-cached surfaces from AssetManager.

Enemies act once per player action rather than on a timer (see
Enemy.take_turn and main.py's Game._run_enemy_turns) -- movement in this
game is already discrete/grid-stepped and driven entirely by KEYDOWN
events, so a classic "you move, then they move" turn model costs nothing
extra at idle: there's simply no enemy computation between player inputs.

Future work (out of scope for this pass): ranged attacks, controller
input.
"""

import random

import pygame

from engine.equipment import SLOTS


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
        self.gold_reward = stats.get("gold_reward", [0, 0])
        self.aggro_range = stats.get("aggro_range", 4)
        self.wander_chance = stats.get("wander_chance", 0.15)

    @property
    def alive(self):
        return self.hp > 0

    def take_turn(self, player, room, occupied_positions):
        """One step of simple chase-or-wander AI. Mutates self.x/y directly
        on a successful move. occupied_positions is the set of tiles held
        by other living enemies (collision, not the player) plus any
        closed locked door/gate tile (session 15) -- callers fold
        Game._blocked_positions() in so an enemy can never path through a
        still-closed fixture."""
        if not self.alive:
            return {"type": "idle"}

        dist = max(abs(player.x - self.x), abs(player.y - self.y))
        if dist <= self.aggro_range:
            dx = (player.x > self.x) - (player.x < self.x)
            dy = (player.y > self.y) - (player.y < self.y)
            steps = []
            if dx != 0:
                steps.append((dx, 0))
            if dy != 0:
                steps.append((0, dy))
            if abs(player.y - self.y) > abs(player.x - self.x):
                steps.reverse()

            for step_dx, step_dy in steps:
                nx, ny = self.x + step_dx, self.y + step_dy
                if (nx, ny) == (player.x, player.y):
                    return {"type": "attack"}
                if room.is_walkable(nx, ny) and (nx, ny) not in occupied_positions:
                    self.x, self.y = nx, ny
                    return {"type": "moved"}
            return {"type": "idle"}

        if random.random() < self.wander_chance:
            step_dx, step_dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            nx, ny = self.x + step_dx, self.y + step_dy
            if room.is_walkable(nx, ny) and (nx, ny) not in occupied_positions:
                self.x, self.y = nx, ny
                return {"type": "moved"}

        return {"type": "idle"}


class ItemPickup(Entity):
    def __init__(self, entity_id, item_type, x, y, item_def):
        super().__init__(x, y, item_def.get("sprite", "item"))
        self.id = entity_id
        self.type = item_type
        self.name = item_def.get("name", item_type)


class EquipmentDrop(Entity):
    """A piece of gear lying on a Depths floor (session 16) -- distinct from
    ItemPickup because gear needs per-instance enchant/curse data attached
    the moment it's picked up, not a stackable data/items.json type. See
    engine/equipment.py and main.py's pickup handling (Game.handle_move's
    "pickup" branch)."""

    def __init__(self, entity_id, base_type, enchant, x, y, equipment_def):
        super().__init__(x, y, equipment_def.get("sprite", "item"))
        self.id = entity_id
        self.base_type = base_type
        self.enchant = enchant
        self.name = equipment_def.get("name", base_type)


class NPC(Entity):
    """Stationary, non-hostile -- no take_turn, unlike Enemy. Bumping one
    opens a dialogue/quest panel instead of combat (see Player.try_move
    and main.py's Game.handle_move)."""

    def __init__(self, entity_id, npc_type, x, y, npc_def):
        super().__init__(x, y, npc_def.get("sprite", "npc"))
        self.id = entity_id
        self.type = npc_type
        self.name = npc_def.get("name", npc_type)
        self.greeting = npc_def.get("greeting", "...")


class Player(Entity):
    def __init__(self, x, y, stats=None, equipment=None, equipment_instances=None):
        super().__init__(x, y, "player")
        stats = stats or {}
        self.max_hp = stats.get("max_hp", 30)
        self.hp = stats.get("hp", self.max_hp)
        # Session 12: repurposed from the session-1 "stamina" placeholder
        # (never consumed by anything) into a real mana pool for spells --
        # see engine/spells.py and PROGRESS.MD session 12.
        self.max_mana = stats.get("max_mana", 20)
        self.mana = stats.get("mana", self.max_mana)
        self.xp = stats.get("xp", 0)
        self.level = stats.get("level", 1)
        self.attack = stats.get("attack", 5)
        self.defense = stats.get("defense", 1)
        self.gold = stats.get("gold", 15)
        # Temporary spell buff (e.g. Stone Skin) -- kept as a separate
        # additive field rather than mutated into `defense` directly (unlike
        # whetstone/shield/equipment's permanent bonuses) so it can expire
        # cleanly without needing a reversal path on load. Persisted as-is
        # (see save.py) so a buff survives a save/quit mid-fight.
        self.buff_defense_bonus = stats.get("buff_defense_bonus", 0)
        self.buff_defense_turns = stats.get("buff_defense_turns", 0)
        # Equipment bonuses are already baked into attack/defense above (see
        # engine/equipment.py) -- this dict only records what's worn (an
        # instance_id since session 16, a bare item_type before it), for the
        # shop/inventory UI and so unequip() knows what to reverse.
        self.equipment = {slot: (equipment or {}).get(slot) for slot in SLOTS}
        # Session 16: every equipment instance ever owned (equipped, or
        # unequipped and sitting in the inventory panel's "Found Gear"
        # bag), keyed by instance_id -- see engine/equipment.py.
        self.equipment_instances = dict(equipment_instances or {})
        # Counter for fresh "eqN" instance ids, resumed past whatever's
        # already in equipment_instances (loaded from a save) so a returning
        # character can't mint an id that collides with one it already owns.
        existing_nums = [
            int(iid[2:]) for iid in self.equipment_instances
            if iid.startswith("eq") and iid[2:].isdigit()
        ]
        self.next_equip_instance_num = max(existing_nums, default=0)
        self.facing = (0, 1)

    def try_move(self, dx, dy, room, enemies, items, npcs=(),
                 locked_doors=(), gates=(), chests=(), switches=(), blocked=None):
        """Resolve a single grid step: attack > npc > locked_door/gate
        (closed only -- caller filters) > blocked > exit > pickup > chest/
        switch > move. Does not mutate enemies/items/chests/switches --
        caller applies combat/pickup/unlock/trigger effects.

        Session 10: locked doors and gates are non-committal bumps (like
        attacking or talking -- the player doesn't step onto them), while
        chests and switches are walk-onto (like item pickup -- the player
        does step onto them, same as walking over a coin pile)."""
        self.facing = (dx, dy)
        new_x, new_y = self.x + dx, self.y + dy

        for enemy in enemies:
            if enemy.alive and enemy.x == new_x and enemy.y == new_y:
                return {"type": "attack", "enemy": enemy}

        for npc in npcs:
            if npc.x == new_x and npc.y == new_y:
                return {"type": "npc", "npc": npc}

        for door in locked_doors:
            if door["x"] == new_x and door["y"] == new_y:
                return {"type": "locked_door", "door": door}

        for gate in gates:
            if gate["x"] == new_x and gate["y"] == new_y:
                return {"type": "gate", "gate": gate}

        if not room.is_walkable(new_x, new_y, blocked):
            return {"type": "blocked"}

        exit_data = room.exit_at(new_x, new_y)
        if exit_data is not None:
            self.x, self.y = new_x, new_y
            return {"type": "exit", "exit": exit_data}

        for item in items:
            if item.x == new_x and item.y == new_y:
                self.x, self.y = new_x, new_y
                return {"type": "pickup", "item": item}

        for chest in chests:
            if chest["x"] == new_x and chest["y"] == new_y:
                self.x, self.y = new_x, new_y
                return {"type": "chest", "chest": chest}

        for switch in switches:
            if switch["x"] == new_x and switch["y"] == new_y:
                self.x, self.y = new_x, new_y
                return {"type": "switch", "switch": switch}

        self.x, self.y = new_x, new_y
        return {"type": "moved"}
