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
        # Session 21: a bite/sting chance that inflicts the player with a
        # damage-over-time status (Castle of the Winds' Viper) -- zero for
        # every enemy type that doesn't define these keys, so existing
        # enemies (data/enemies.json) needed no changes.
        self.poison_chance = stats.get("poison_chance", 0)
        self.poison_damage = stats.get("poison_damage", 0)
        self.poison_duration = stats.get("poison_duration", 0)
        # Session 22: elemental damage (Castle of the Winds' fire/cold/
        # lightning) -- "physical" (the default, every pre-existing enemy)
        # is mitigated by the player's defense as always; anything else
        # bypasses defense entirely and is mitigated by resist_elemental
        # instead (see combat.py). resist_elements is the reverse case: how
        # much *this* enemy resists an incoming elemental spell of a given
        # type (1.0 = immune, matching CotW's dragons being immune to their
        # own breath element), keyed by damage_type, empty for everything
        # that doesn't define it.
        self.damage_type = stats.get("damage_type", "physical")
        self.resist_elements = stats.get("resist_elements", {})
        # Session 24: the Wraith (Castle of the Winds' mana/intelligence-
        # draining undead) -- a bite/touch chance that permanently lowers
        # the player's usable mana ceiling rather than a wears-off-on-its-
        # own DoT like the Viper's poison (see Player.mana_drain, cured only
        # by paying the Healer, not by time). Zero for every enemy that
        # doesn't define these, same convention as poison_chance above.
        self.drain_chance = stats.get("drain_chance", 0)
        self.drain_amount = stats.get("drain_amount", 0)
        # Session 37: which player stat a drain touch lowers -- "mana"
        # (default, every existing drain-capable enemy, i.e. the Wraith
        # family) or "attack" (Castle of the Winds' Wight family, which
        # drains STR/DEX/CON rather than intelligence/mana; this engine has
        # no separate attributes, so -- same adaptation session 24 already
        # made for the Wraith's INT drain standing in as a mana drain --
        # Wight drain stands in as an attack drain, see combat._maybe_drain
        # and Player.attack_drain below).
        self.drain_stat = stats.get("drain_stat", "mana")
        # CotW's wraiths "pass through walls and doors" -- take_turn below
        # skips the wall check (not the closed-door/gate one, still folded
        # into occupied_positions by the caller) when this is set.
        self.phases_walls = stats.get("phases_walls", False)
        # Session 40: whether Sleep Monster can affect this type at all --
        # CotW's own wording is "some monsters and all bosses are immune";
        # only the "all bosses" half is sourced concretely, so this is set
        # true only for the mini-boss-tier rarities data/enemies.json and
        # engine/procgen.py's ENEMY_WEIGHTS_BY_TIER already single out as
        # weight-1 rare (the four young dragons, Dark/Abyss Wraith, Castle
        # Wight) rather than guessing at which "some monsters" the real
        # game means. sleep_turns itself is pure runtime combat state, not
        # spawn data -- like hp, it isn't loaded from `stats` and doesn't
        # need a save.py column, since Depths enemies are regenerated fresh
        # from epoch on every room visit rather than persisted individually.
        self.sleep_immune = stats.get("sleep_immune", False)
        self.sleep_turns = 0
        # Session 42: Slow Monster (Castle of the Winds' "slows the target
        # monster's movement and attacks to half... a second cast reduces
        # the speed to 1/3, a third to 1/4, etc."). Unlike sleep_turns this
        # has no wear-off timer in the source text -- it's runtime combat
        # state that stacks per re-cast rather than counting down, reset
        # only by the same fresh-per-room-visit regeneration every other
        # per-enemy runtime field already relies on (see sleep_immune's own
        # note above). slow_level 0 means unaffected; N means every Nth+1
        # take_turn call is a real turn (1/(N+1) speed) and the rest are
        # skipped, reusing the same single per-player-action call cadence
        # sleep_turns already counts against. Boss immunity ("Bosses are
        # immune") reuses sleep_immune rather than a near-duplicate flag --
        # this engine has no separate boss concept, and session 40 already
        # established sleep_immune as the mini-boss-tier stand-in for it.
        self.slow_level = 0
        self.slow_tick = 0

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

        if self.sleep_turns > 0:
            # Session 40: a sleeping enemy neither chases nor wanders --
            # counts down here since this is only ever called once per
            # player action (see main.py's Game._run_enemy_turns), the same
            # "one call = one turn" cadence every other per-turn countdown
            # in this engine relies on.
            self.sleep_turns -= 1
            return {"type": "asleep"}

        if self.slow_level > 0:
            # Every (slow_level + 1)th call is a real turn; the rest are
            # skipped outright -- "movement and attacks" both come from the
            # same take_turn call, so skipping the whole call halves (or
            # thirds, etc.) both at once with no separate attack-rate field.
            self.slow_tick += 1
            if self.slow_tick % (self.slow_level + 1) != 0:
                return {"type": "slowed"}

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
                if room.is_walkable(nx, ny, ignore_walls=self.phases_walls) and (nx, ny) not in occupied_positions:
                    self.x, self.y = nx, ny
                    return {"type": "moved"}
            return {"type": "idle"}

        if random.random() < self.wander_chance:
            step_dx, step_dy = random.choice([(1, 0), (-1, 0), (0, 1), (0, -1)])
            nx, ny = self.x + step_dx, self.y + step_dy
            if room.is_walkable(nx, ny, ignore_walls=self.phases_walls) and (nx, ny) not in occupied_positions:
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


class SpellbookDrop(Entity):
    """A spellbook lying on a Depths floor (session 39) -- Castle of the
    Winds' other spellbook source (session 19 built the Scholar's paid
    catalog; see engine/spells.py's "future work" note this closes out).
    Distinct from ItemPickup for the same reason EquipmentDrop is: picking
    one up needs a live known_spells check main.py's generic Inventory path
    doesn't have, not a stackable data/items.json type -- it teaches its
    spell (or, if already known, crumbles for a gold refund) rather than
    occupying an inventory slot."""

    def __init__(self, entity_id, spell_id, x, y, spell_def):
        super().__init__(x, y, "item_spellbook")
        self.id = entity_id
        self.spell_id = spell_id
        self.name = f"Spellbook: {spell_def.get('name', spell_id)}"


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
        # Session 21: poison (Castle of the Winds' Viper/Giant Scorpion bite)
        # -- a damage-over-time status, same "separate persisted field, not a
        # mutate-then-reverse stat" reasoning as the buff above (it has to
        # expire/tick on its own schedule, see main.py's Game._advance_turn).
        self.poison_turns = stats.get("poison_turns", 0)
        self.poison_damage = stats.get("poison_damage", 0)
        # Session 29: Levitation (Castle of the Winds' "impervious to
        # non-magical traps" buff) -- same countdown-buff shape as
        # buff_defense_turns above, persisted for the same reason (a
        # save/quit mid-flight shouldn't let a player dodge the eventual
        # trap check for free). See engine/combat.py's resolve_trap.
        self.levitation_turns = stats.get("levitation_turns", 0)
        # Session 22: elemental resistance (a percentage, 0-100), sourced
        # entirely from an equipped amulet -- see engine/equipment.py, which
        # replaces amulets' old flat max_hp bonus with this. Baked in and
        # reversed the same permanent way attack/defense's equipment bonuses
        # already are (equip()/unequip() add/subtract it directly), so it
        # survives a save/reload without re-deriving it from gear.
        self.resist_elemental = stats.get("resist_elemental", 0)
        # Session 24: Castle of the Winds' other amulet-worthy resistance --
        # "resistance to an element or undead stat draining" (session 18's
        # own docstring note). Mitigates a Wraith's drain the same way
        # resist_elemental mitigates fire/cold/lightning, sourced from the
        # same Amulet line (see engine/equipment.py) rather than a second
        # item line -- this engine keeps one amulet slot doing double duty.
        self.resist_undead = stats.get("resist_undead", 0)
        # Session 34: Resist Fire/Cold/Lightning -- Castle of the Winds' own
        # temporary per-element resistance spells (see engine/spells.py's
        # "resist_element" effect), stacking additively with the flat,
        # always-on resist_elemental above rather than replacing it. Same
        # countdown-buff pair shape as buff_defense_bonus/turns, just one
        # pair per element since more than one can be active at once.
        self.temp_resist_fire_bonus = stats.get("temp_resist_fire_bonus", 0)
        self.temp_resist_fire_turns = stats.get("temp_resist_fire_turns", 0)
        self.temp_resist_cold_bonus = stats.get("temp_resist_cold_bonus", 0)
        self.temp_resist_cold_turns = stats.get("temp_resist_cold_turns", 0)
        self.temp_resist_lightning_bonus = stats.get("temp_resist_lightning_bonus", 0)
        self.temp_resist_lightning_turns = stats.get("temp_resist_lightning_turns", 0)
        # Permanent (until paid off at the Healer, see main.py's
        # cure_mana_drain) reduction to the *usable* mana ceiling -- a
        # separate field rather than mutating max_mana directly, same
        # "needs its own reversal path, can't just subtract and forget"
        # reasoning buff_defense_bonus/poison already established, except
        # this one doesn't wear off on a timer at all, it has to be paid
        # off. See effective_max_mana() below and main.py's Game._advance_turn
        # callers, all of which now cap `mana` against that instead of the
        # raw stat.
        self.mana_drain = stats.get("mana_drain", 0)
        self.mana = min(self.mana, self.effective_max_mana())
        # Session 37: a Wight's touch (see drain_stat above) permanently
        # subtracts from `attack` directly instead -- the same "mutate the
        # base stat, keep a running total to reverse later" pattern
        # equipment's bonuses already use (see engine/equipment.py's
        # equip()/unequip()), rather than mana_drain's separate-ceiling
        # approach, since attack has no natural current/max split to layer
        # a ceiling onto. attack_drain is just the reversal record -- only
        # paying the Healer (main.py's cure_attack_drain) zeroes it.
        self.attack_drain = stats.get("attack_drain", 0)
        # Session 26: Word of Recall's anchor point -- set the moment the
        # spell is cast away from town, read back the moment it's cast
        # *in* town. Persisted (unlike the detect-spell timers) for the
        # same reason mana_drain/poison are: it should survive a save/quit,
        # matching Castle of the Winds' own recall (a scroll effect you can
        # act on much later). None until the player has cast it at least
        # once away from town.
        self.recall_room = stats.get("recall_room")
        self.recall_x = stats.get("recall_x")
        self.recall_y = stats.get("recall_y")
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

    def effective_max_mana(self):
        """The mana ceiling after a Wraith's drain (session 24) -- every
        place that used to cap against max_mana directly (level-up refill,
        mana potions, resting at the Healer, the HUD bar/text) now caps
        against this instead, so a drained player can't be topped back up
        past what they're actually able to hold right now."""
        return max(0, self.max_mana - self.mana_drain)

    def temp_resist_bonus(self, damage_type):
        """Session 34: the active Resist Fire/Cold/Lightning bonus for a
        given elemental damage_type, or 0 if that spell isn't currently up
        (or damage_type is "physical"/anything with no matching spell).
        Read by engine/combat.py's _enemy_damage_to_player alongside the
        flat resist_elemental stat."""
        if damage_type == "fire":
            return self.temp_resist_fire_bonus if self.temp_resist_fire_turns > 0 else 0
        if damage_type == "cold":
            return self.temp_resist_cold_bonus if self.temp_resist_cold_turns > 0 else 0
        if damage_type == "lightning":
            return self.temp_resist_lightning_bonus if self.temp_resist_lightning_turns > 0 else 0
        return 0

    def try_move(self, dx, dy, room, enemies, items, npcs=(),
                 locked_doors=(), gates=(), chests=(), switches=(), traps=(),
                 locked_exits=(), blocked=None):
        """Resolve a single grid step: attack > npc > locked_door/gate
        (closed only -- caller filters) > locked_exit (Adventure Mode biome
        gating, see wayfarer_adventure.md -- caller filters to whichever
        exits aren't unlocked yet) > blocked > exit > pickup > chest/
        switch/trap > move. Does not mutate enemies/items/chests/switches/
        traps -- caller applies combat/pickup/unlock/trigger effects.

        Session 10: locked doors and gates are non-committal bumps (like
        attacking or talking -- the player doesn't step onto them), while
        chests and switches are walk-onto (like item pickup -- the player
        does step onto them, same as walking over a coin pile). Session 28:
        traps are walk-onto the same way -- stepping on one doesn't block
        the move, the hazard just happens to you mid-step, same as a real
        dungeon trap. `traps` always holds every trap in the room (sprung or
        not, mirroring chests/switches) -- the caller decides whether one
        has already been sprung."""
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

        for locked_exit in locked_exits:
            if locked_exit["x"] == new_x and locked_exit["y"] == new_y:
                return {"type": "locked_exit", "exit": locked_exit}

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

        for trap in traps:
            if trap["x"] == new_x and trap["y"] == new_y:
                self.x, self.y = new_x, new_y
                return {"type": "trap", "trap": trap}

        self.x, self.y = new_x, new_y
        return {"type": "moved"}
