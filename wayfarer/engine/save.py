"""SQLite save/load. A single connection is opened once at startup and
reused; writes only happen on room transitions and on quit -- never inside
the per-frame render/update path (see main.py's Game.transition_to_room and
the QUIT handler)."""

import random
import sqlite3

from engine.equipment import SLOTS

DEFAULT_ROOM = "town_hub"  # session 10: replaces start_hall, see PROGRESS.MD
DEFAULT_SPAWN = (16, 18)


def _migrate_room_id(room_id):
    """Pre-session-4 saves addressed the Depths as "proc:<seed>:<gx>:<gy>"
    -- a flat plane with no dungeon level. Session 4 added levels
    ("proc:<seed>:<level>:<gx>:<gy>"); upgrade any old-format id in place
    by treating the flat plane it came from as level 1, so an existing
    character resumes where they were instead of crashing on load."""
    if room_id and room_id.startswith("proc:"):
        parts = room_id.split(":")
        if len(parts) == 4:
            _, seed_str, gx_str, gy_str = parts
            return f"proc:{seed_str}:1:{gx_str}:{gy_str}"
    return room_id


class SaveManager:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS player (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                hp INTEGER, max_hp INTEGER,
                xp INTEGER, level INTEGER,
                attack INTEGER, defense INTEGER,
                current_room TEXT, pos_x INTEGER, pos_y INTEGER,
                dungeon_seed INTEGER
            )"""
        )
        for column_def in (
            "turn_count INTEGER DEFAULT 0",
            "depths_kills INTEGER DEFAULT 0",
            "quest_index INTEGER DEFAULT 0",
            "gold INTEGER DEFAULT 0",
            # Session 12: replaces the never-consumed "stamina"/"max_stamina"
            # columns from session 1 -- a breaking rename, not an addition,
            # for the same reason session 4/10's room-id/room-set changes
            # were: save.db is a local gitignored dev save with no migration
            # path promised (see PROGRESS.MD session 12).
            "mana INTEGER DEFAULT 20",
            "max_mana INTEGER DEFAULT 20",
            "buff_defense_bonus INTEGER DEFAULT 0",
            "buff_defense_turns INTEGER DEFAULT 0",
            # Session 21: poison status (Viper bite) -- persisted so a
            # save/quit mid-poison doesn't let a player dodge the DoT for
            # free, same reasoning as the buff pair above.
            "poison_turns INTEGER DEFAULT 0",
            "poison_damage INTEGER DEFAULT 0",
            # Session 22: baked-in permanent bonus from an equipped amulet,
            # same persistence reasoning as attack/defense (see
            # engine/equipment.py's equip()/unequip()).
            "resist_elemental INTEGER DEFAULT 0",
            # Session 24: a Wraith's drain and the Amulet-of-Resistance-line
            # stat that mitigates it -- same persistence reasoning as
            # resist_elemental (mana_drain survives a save/quit on purpose,
            # same as poison, since it's only cured by paying the Healer).
            "mana_drain INTEGER DEFAULT 0",
            "resist_undead INTEGER DEFAULT 0",
            # Session 37: the Wight family's attack-drain counterpart to
            # mana_drain above -- same "persists indefinitely, only the
            # Healer clears it" reasoning, see Player.attack_drain.
            "attack_drain INTEGER DEFAULT 0",
            # Session 26: Word of Recall's anchor -- where to return the
            # player when the spell is cast from town. NULL until it's been
            # cast at least once away from town, same "persists indefinitely,
            # not a countdown" reasoning as mana_drain above.
            "recall_room TEXT",
            "recall_x INTEGER",
            "recall_y INTEGER",
            # Session 29: Levitation's countdown -- same persistence
            # reasoning as buff_defense_turns above.
            "levitation_turns INTEGER DEFAULT 0",
            # Session 34: Resist Fire/Cold/Lightning -- Castle of the Winds'
            # own per-element temporary resistance spells, distinct from the
            # flat, generic-across-every-element resist_elemental amulet
            # stat above. Same bonus+turns countdown-buff pair as
            # buff_defense_bonus/turns, just one pair per element since a
            # player can have all three running at once (e.g. before a
            # multi-dragon vault fight).
            "temp_resist_fire_bonus INTEGER DEFAULT 0",
            "temp_resist_fire_turns INTEGER DEFAULT 0",
            "temp_resist_cold_bonus INTEGER DEFAULT 0",
            "temp_resist_cold_turns INTEGER DEFAULT 0",
            "temp_resist_lightning_bonus INTEGER DEFAULT 0",
            "temp_resist_lightning_turns INTEGER DEFAULT 0",
            *(f"equip_{slot} TEXT" for slot in SLOTS),
        ):
            try:
                self.conn.execute(f"ALTER TABLE player ADD COLUMN {column_def}")
            except sqlite3.OperationalError:
                pass  # column already exists from a prior run
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS inventory (
                item_type TEXT PRIMARY KEY,
                count INTEGER
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS known_spells (
                spell_id TEXT PRIMARY KEY
            )"""
        )
        # Session 16: per-instance equipment (enchant/curse/identified) --
        # equip_<slot> columns on `player` now store instance_id values that
        # point in here, rather than bare item_type strings. No change to
        # those columns' own schema, only what's stored in them.
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS equipment_instances (
                instance_id TEXT PRIMARY KEY,
                base_type TEXT NOT NULL,
                enchant INTEGER NOT NULL DEFAULT 0,
                cursed INTEGER NOT NULL DEFAULT 0,
                identified INTEGER NOT NULL DEFAULT 1
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS room_flags (
                room_id TEXT, flag_type TEXT, entity_id TEXT,
                PRIMARY KEY (room_id, flag_type, entity_id)
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS room_meta (
                room_id TEXT PRIMARY KEY,
                epoch INTEGER NOT NULL DEFAULT 0,
                cleared_turn INTEGER
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS discovered_rooms (
                level INTEGER, gx INTEGER, gy INTEGER,
                PRIMARY KEY (level, gx, gy)
            )"""
        )
        # Session 43: consumables dropped back onto the floor from the
        # Inventory panel -- distinct from room_flags because a drop needs
        # its own type/position remembered, not just a boolean per
        # entity_id. Full-replace per room, same semantics as room_flags,
        # flushed at the same call sites (see main.py's persist()/"exit"/
        # Word of Recall, all three of which already flush room_flags).
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS room_drops (
                room_id TEXT, entity_id TEXT, item_type TEXT,
                x INTEGER, y INTEGER,
                PRIMARY KEY (room_id, entity_id)
            )"""
        )
        # Wayfarer Adventure Mode (see wayfarer/wayfarer_adventure.md): a
        # flat "have we ever claimed this fragment" set, same shape/
        # persistence reasoning as known_spells -- a world-progression fact,
        # not something that can be un-owned.
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS artifact_fragments (
                fragment_id TEXT PRIMARY KEY
            )"""
        )
        # Session 45: the fetch/trade quest chain's own persisted state --
        # same flat "have we ever crossed this line" shape as known_spells/
        # artifact_fragments, per wayfarer_adventure.md's own proposed
        # schema. Biome-unlock gating (main.py's _locked_exits) reads this
        # directly rather than a separate unlocked-biomes table, since each
        # quest id already maps to exactly one biome unlock.
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS completed_adventure_quests (
                quest_id TEXT PRIMARY KEY
            )"""
        )
        # Session 48: push-block puzzles (researched via Yoda Stories/
        # Desktop Adventures -- see wayfarer_adventure.md's "sokoban blocks"
        # note) -- a block's live position after being pushed around, same
        # full-replace-per-room shape/reasoning as room_drops (a block needs
        # its position remembered, not just a boolean per entity_id).
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS block_positions (
                room_id TEXT, entity_id TEXT, x INTEGER, y INTEGER,
                PRIMARY KEY (room_id, entity_id)
            )"""
        )
        self.conn.commit()

    def has_save(self):
        cur = self.conn.execute("SELECT 1 FROM player WHERE id = 1")
        return cur.fetchone() is not None

    def reset(self):
        """Wipe all persisted progress (menu's "New Game" over an existing
        save). Leaves the schema in place -- load_game() returns None
        afterward, so the caller's usual `load_game() or new_game_defaults()`
        fallback naturally produces a fresh character/seed."""
        for table in (
            "player", "inventory", "room_flags", "room_meta",
            "discovered_rooms", "known_spells", "equipment_instances",
            "room_drops", "artifact_fragments", "completed_adventure_quests",
            "block_positions",
        ):
            self.conn.execute(f"DELETE FROM {table}")
        self.conn.commit()

    def load_game(self):
        equip_cols = ", ".join(f"equip_{slot}" for slot in SLOTS)
        cur = self.conn.execute(
            f"""SELECT hp, max_hp, xp, level,
                       attack, defense, current_room, pos_x, pos_y, dungeon_seed,
                       turn_count, depths_kills, quest_index, gold,
                       mana, max_mana, buff_defense_bonus, buff_defense_turns,
                       poison_turns, poison_damage, resist_elemental,
                       mana_drain, resist_undead,
                       recall_room, recall_x, recall_y, levitation_turns,
                       temp_resist_fire_bonus, temp_resist_fire_turns,
                       temp_resist_cold_bonus, temp_resist_cold_turns,
                       temp_resist_lightning_bonus, temp_resist_lightning_turns,
                       attack_drain,
                       {equip_cols}
                FROM player WHERE id = 1"""
        )
        row = cur.fetchone()
        if row is None:
            return None

        player_stats = {
            "hp": row[0], "max_hp": row[1],
            "xp": row[2], "level": row[3],
            "attack": row[4], "defense": row[5],
            "gold": row[13] or 0,
            "mana": row[14], "max_mana": row[15],
            "buff_defense_bonus": row[16] or 0,
            "buff_defense_turns": row[17] or 0,
            "poison_turns": row[18] or 0,
            "poison_damage": row[19] or 0,
            "resist_elemental": row[20] or 0,
            "mana_drain": row[21] or 0,
            "resist_undead": row[22] or 0,
            "recall_room": row[23],
            "recall_x": row[24],
            "recall_y": row[25],
            "levitation_turns": row[26] or 0,
            "temp_resist_fire_bonus": row[27] or 0,
            "temp_resist_fire_turns": row[28] or 0,
            "temp_resist_cold_bonus": row[29] or 0,
            "temp_resist_cold_turns": row[30] or 0,
            "temp_resist_lightning_bonus": row[31] or 0,
            "temp_resist_lightning_turns": row[32] or 0,
            "attack_drain": row[33] or 0,
        }
        current_room = _migrate_room_id(row[6])
        pos = (row[7], row[8])
        seed = row[9]
        turn_count = row[10] or 0
        depths_kills = row[11] or 0
        quest_index = row[12] or 0
        equipment = dict(zip(SLOTS, row[34:34 + len(SLOTS)]))

        inv_rows = self.conn.execute("SELECT item_type, count FROM inventory")
        inventory = {item_type: count for item_type, count in inv_rows}

        spell_rows = self.conn.execute("SELECT spell_id FROM known_spells")
        known_spells = {spell_id for (spell_id,) in spell_rows}

        fragment_rows = self.conn.execute("SELECT fragment_id FROM artifact_fragments")
        artifact_fragments = {fragment_id for (fragment_id,) in fragment_rows}

        quest_rows = self.conn.execute("SELECT quest_id FROM completed_adventure_quests")
        completed_adventure_quests = {quest_id for (quest_id,) in quest_rows}

        instance_rows = self.conn.execute(
            "SELECT instance_id, base_type, enchant, cursed, identified FROM equipment_instances"
        )
        equipment_instances = {
            instance_id: {
                "instance_id": instance_id,
                "base_type": base_type,
                "enchant": enchant,
                "cursed": bool(cursed),
                "identified": bool(identified),
            }
            for instance_id, base_type, enchant, cursed, identified in instance_rows
        }

        return {
            "player": player_stats,
            "equipment": equipment,
            "equipment_instances": equipment_instances,
            "inventory": inventory,
            "known_spells": known_spells,
            "artifact_fragments": artifact_fragments,
            "completed_adventure_quests": completed_adventure_quests,
            "current_room": current_room,
            "pos": pos,
            "seed": seed,
            "turn_count": turn_count,
            "depths_kills": depths_kills,
            "quest_index": quest_index,
        }

    def new_game_defaults(self):
        return {
            "player": {},  # Player() fills in its own defaults
            "equipment": {},
            "equipment_instances": {},
            "inventory": {},
            "known_spells": set(),
            "artifact_fragments": set(),
            "completed_adventure_quests": set(),
            "current_room": DEFAULT_ROOM,
            "pos": DEFAULT_SPAWN,
            "seed": random.randint(0, 2**31 - 1),
            "turn_count": 0,
            "depths_kills": 0,
            "quest_index": 0,
        }

    def save_game(self, player, inventory, current_room_id, seed, turn_count,
                   depths_kills, quest_index, known_spells, artifact_fragments=(),
                   completed_adventure_quests=()):
        equip_cols = ", ".join(f"equip_{slot}" for slot in SLOTS)
        equip_placeholders = ", ".join("?" for _ in SLOTS)
        equip_updates = ", ".join(f"equip_{slot}=excluded.equip_{slot}" for slot in SLOTS)
        self.conn.execute(
            f"""INSERT INTO player (id, hp, max_hp, xp,
                                     level, attack, defense, current_room,
                                     pos_x, pos_y, dungeon_seed, turn_count,
                                     depths_kills, quest_index, gold,
                                     mana, max_mana, buff_defense_bonus,
                                     buff_defense_turns, poison_turns,
                                     poison_damage, resist_elemental,
                                     mana_drain, resist_undead,
                                     recall_room, recall_x, recall_y,
                                     levitation_turns,
                                     temp_resist_fire_bonus, temp_resist_fire_turns,
                                     temp_resist_cold_bonus, temp_resist_cold_turns,
                                     temp_resist_lightning_bonus, temp_resist_lightning_turns,
                                     attack_drain,
                                     {equip_cols})
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, {equip_placeholders})
                ON CONFLICT(id) DO UPDATE SET
                  hp=excluded.hp, max_hp=excluded.max_hp,
                  xp=excluded.xp, level=excluded.level,
                  attack=excluded.attack, defense=excluded.defense,
                  current_room=excluded.current_room,
                  pos_x=excluded.pos_x, pos_y=excluded.pos_y,
                  dungeon_seed=excluded.dungeon_seed,
                  turn_count=excluded.turn_count,
                  depths_kills=excluded.depths_kills,
                  quest_index=excluded.quest_index,
                  gold=excluded.gold,
                  mana=excluded.mana, max_mana=excluded.max_mana,
                  buff_defense_bonus=excluded.buff_defense_bonus,
                  buff_defense_turns=excluded.buff_defense_turns,
                  poison_turns=excluded.poison_turns,
                  poison_damage=excluded.poison_damage,
                  resist_elemental=excluded.resist_elemental,
                  mana_drain=excluded.mana_drain,
                  resist_undead=excluded.resist_undead,
                  recall_room=excluded.recall_room,
                  recall_x=excluded.recall_x,
                  recall_y=excluded.recall_y,
                  levitation_turns=excluded.levitation_turns,
                  temp_resist_fire_bonus=excluded.temp_resist_fire_bonus,
                  temp_resist_fire_turns=excluded.temp_resist_fire_turns,
                  temp_resist_cold_bonus=excluded.temp_resist_cold_bonus,
                  temp_resist_cold_turns=excluded.temp_resist_cold_turns,
                  temp_resist_lightning_bonus=excluded.temp_resist_lightning_bonus,
                  temp_resist_lightning_turns=excluded.temp_resist_lightning_turns,
                  attack_drain=excluded.attack_drain,
                  {equip_updates}""",
            (
                player.hp, player.max_hp, player.xp, player.level,
                player.attack, player.defense,
                current_room_id, player.x, player.y, seed, turn_count,
                depths_kills, quest_index, player.gold,
                player.mana, player.max_mana,
                player.buff_defense_bonus, player.buff_defense_turns,
                player.poison_turns, player.poison_damage,
                player.resist_elemental,
                player.mana_drain, player.resist_undead,
                player.recall_room, player.recall_x, player.recall_y,
                player.levitation_turns,
                player.temp_resist_fire_bonus, player.temp_resist_fire_turns,
                player.temp_resist_cold_bonus, player.temp_resist_cold_turns,
                player.temp_resist_lightning_bonus, player.temp_resist_lightning_turns,
                player.attack_drain,
                *(player.equipment.get(slot) for slot in SLOTS),
            ),
        )
        self.conn.execute("DELETE FROM inventory")
        self.conn.executemany(
            "INSERT INTO inventory (item_type, count) VALUES (?, ?)",
            list(inventory.to_save_dict().items()),
        )
        self.conn.execute("DELETE FROM known_spells")
        self.conn.executemany(
            "INSERT INTO known_spells (spell_id) VALUES (?)",
            [(spell_id,) for spell_id in known_spells],
        )
        self.conn.execute("DELETE FROM artifact_fragments")
        self.conn.executemany(
            "INSERT INTO artifact_fragments (fragment_id) VALUES (?)",
            [(fragment_id,) for fragment_id in artifact_fragments],
        )
        self.conn.execute("DELETE FROM completed_adventure_quests")
        self.conn.executemany(
            "INSERT INTO completed_adventure_quests (quest_id) VALUES (?)",
            [(quest_id,) for quest_id in completed_adventure_quests],
        )
        self.conn.execute("DELETE FROM equipment_instances")
        self.conn.executemany(
            """INSERT INTO equipment_instances
                (instance_id, base_type, enchant, cursed, identified)
                VALUES (?, ?, ?, ?, ?)""",
            [
                (
                    inst["instance_id"], inst["base_type"], inst["enchant"],
                    int(inst["cursed"]), int(inst["identified"]),
                )
                for inst in player.equipment_instances.values()
            ],
        )
        self.conn.commit()

    def get_room_flags(self, room_id):
        """Returns {flag_type: {entity_id, ...}} for every flag type ever
        recorded against this room -- generalized (session 10) beyond the
        original two hardcoded types (enemy_dead/item_taken) so newer flag
        types (region_seen/door_unlocked/gate_open/chest_opened) ride the
        exact same table/column with zero schema change. Callers use
        `.get(flag_type, set())` for any type that may not be present yet."""
        rows = self.conn.execute(
            "SELECT flag_type, entity_id FROM room_flags WHERE room_id = ?",
            (room_id,),
        )
        flags = {}
        for flag_type, entity_id in rows:
            flags.setdefault(flag_type, set()).add(entity_id)
        return flags

    def set_room_flags(self, room_id, flags):
        """flags: {flag_type: {entity_id, ...}} -- a full replace of every
        flag type for this room in one write, same semantics as before,
        just generalized to however many flag types the caller tracks."""
        self.conn.execute("DELETE FROM room_flags WHERE room_id = ?", (room_id,))
        rows = [
            (room_id, flag_type, entity_id)
            for flag_type, ids in flags.items()
            for entity_id in ids
        ]
        self.conn.executemany(
            "INSERT INTO room_flags (room_id, flag_type, entity_id) VALUES (?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def get_room_drops(self, room_id):
        """Returns [{"id", "type", "x", "y"}, ...] for every consumable a
        player has dropped in this room and not yet picked back up."""
        rows = self.conn.execute(
            "SELECT entity_id, item_type, x, y FROM room_drops WHERE room_id = ?",
            (room_id,),
        )
        return [
            {"id": entity_id, "type": item_type, "x": x, "y": y}
            for entity_id, item_type, x, y in rows
        ]

    def set_room_drops(self, room_id, drops):
        """drops: [{"id", "type", "x", "y"}, ...] -- a full replace, same
        semantics as set_room_flags."""
        self.conn.execute("DELETE FROM room_drops WHERE room_id = ?", (room_id,))
        rows = [
            (room_id, drop["id"], drop["type"], drop["x"], drop["y"])
            for drop in drops
        ]
        self.conn.executemany(
            """INSERT INTO room_drops (room_id, entity_id, item_type, x, y)
               VALUES (?, ?, ?, ?, ?)""",
            rows,
        )
        self.conn.commit()

    def get_block_positions(self, room_id):
        """Returns {block_id: (x, y), ...} for every block that's been
        pushed at least once in this room -- a block never in this dict
        just stays at its template-defined starting position (see main.py's
        load_room, which overlays this on top of self.room.block_templates
        the same way get_room_drops' results overlay item templates)."""
        rows = self.conn.execute(
            "SELECT entity_id, x, y FROM block_positions WHERE room_id = ?",
            (room_id,),
        )
        return {entity_id: (x, y) for entity_id, x, y in rows}

    def set_block_positions(self, room_id, blocks):
        """blocks: [{"id", "x", "y"}, ...] (main.py's Game.blocks, its live
        in-memory copy) -- a full replace, same semantics as
        set_room_drops. Every block is written every time (not just moved
        ones) since a full replace is cheaper than diffing and this table
        is small."""
        self.conn.execute("DELETE FROM block_positions WHERE room_id = ?", (room_id,))
        rows = [(room_id, b["id"], b["x"], b["y"]) for b in blocks]
        self.conn.executemany(
            "INSERT INTO block_positions (room_id, entity_id, x, y) VALUES (?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def get_room_meta(self, room_id):
        cur = self.conn.execute(
            "SELECT epoch, cleared_turn FROM room_meta WHERE room_id = ?",
            (room_id,),
        )
        row = cur.fetchone()
        if row is None:
            return {"epoch": 0, "cleared_turn": None}
        return {"epoch": row[0], "cleared_turn": row[1]}

    def set_room_meta(self, room_id, epoch, cleared_turn):
        self.conn.execute(
            """INSERT INTO room_meta (room_id, epoch, cleared_turn)
               VALUES (?, ?, ?)
               ON CONFLICT(room_id) DO UPDATE SET
                 epoch=excluded.epoch, cleared_turn=excluded.cleared_turn""",
            (room_id, epoch, cleared_turn),
        )
        self.conn.commit()

    def get_discovered_rooms(self, level):
        """(gx, gy) set of every Depths room visited on `level` -- feeds the
        automap (main.py's Game._draw_dungeon_map). Since every level's
        (0, 0) is where the stairs live and is always the first room
        entered on that level (see procgen.py), "visited" and "stairs
        discovered" are the same fact -- no separate stairs-seen tracking
        is needed."""
        rows = self.conn.execute(
            "SELECT gx, gy FROM discovered_rooms WHERE level = ?", (level,)
        )
        return {(gx, gy) for gx, gy in rows}

    def mark_discovered(self, level, gx, gy):
        self.conn.execute(
            "INSERT OR IGNORE INTO discovered_rooms (level, gx, gy) VALUES (?, ?, ?)",
            (level, gx, gy),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
