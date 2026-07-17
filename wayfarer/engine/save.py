"""SQLite save/load. A single connection is opened once at startup and
reused; writes only happen on room transitions and on quit -- never inside
the per-frame render/update path (see main.py's Game.transition_to_room and
the QUIT handler)."""

import random
import sqlite3

DEFAULT_ROOM = "start_hall"
DEFAULT_SPAWN = (2, 4)


class SaveManager:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS player (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                hp INTEGER, max_hp INTEGER,
                stamina INTEGER, max_stamina INTEGER,
                xp INTEGER, level INTEGER,
                attack INTEGER, defense INTEGER,
                current_room TEXT, pos_x INTEGER, pos_y INTEGER,
                dungeon_seed INTEGER
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS inventory (
                item_type TEXT PRIMARY KEY,
                count INTEGER
            )"""
        )
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS room_flags (
                room_id TEXT, flag_type TEXT, entity_id TEXT,
                PRIMARY KEY (room_id, flag_type, entity_id)
            )"""
        )
        self.conn.commit()

    def has_save(self):
        cur = self.conn.execute("SELECT 1 FROM player WHERE id = 1")
        return cur.fetchone() is not None

    def load_game(self):
        cur = self.conn.execute(
            """SELECT hp, max_hp, stamina, max_stamina, xp, level,
                      attack, defense, current_room, pos_x, pos_y, dungeon_seed
               FROM player WHERE id = 1"""
        )
        row = cur.fetchone()
        if row is None:
            return None

        player_stats = {
            "hp": row[0], "max_hp": row[1],
            "stamina": row[2], "max_stamina": row[3],
            "xp": row[4], "level": row[5],
            "attack": row[6], "defense": row[7],
        }
        current_room = row[8]
        pos = (row[9], row[10])
        seed = row[11]

        inv_rows = self.conn.execute("SELECT item_type, count FROM inventory")
        inventory = {item_type: count for item_type, count in inv_rows}

        return {
            "player": player_stats,
            "inventory": inventory,
            "current_room": current_room,
            "pos": pos,
            "seed": seed,
        }

    def new_game_defaults(self):
        return {
            "player": {},  # Player() fills in its own defaults
            "inventory": {},
            "current_room": DEFAULT_ROOM,
            "pos": DEFAULT_SPAWN,
            "seed": random.randint(0, 2**31 - 1),
        }

    def save_game(self, player, inventory, current_room_id, seed):
        self.conn.execute(
            """INSERT INTO player (id, hp, max_hp, stamina, max_stamina, xp,
                                    level, attack, defense, current_room,
                                    pos_x, pos_y, dungeon_seed)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 hp=excluded.hp, max_hp=excluded.max_hp,
                 stamina=excluded.stamina, max_stamina=excluded.max_stamina,
                 xp=excluded.xp, level=excluded.level,
                 attack=excluded.attack, defense=excluded.defense,
                 current_room=excluded.current_room,
                 pos_x=excluded.pos_x, pos_y=excluded.pos_y,
                 dungeon_seed=excluded.dungeon_seed""",
            (
                player.hp, player.max_hp, player.stamina, player.max_stamina,
                player.xp, player.level, player.attack, player.defense,
                current_room_id, player.x, player.y, seed,
            ),
        )
        self.conn.execute("DELETE FROM inventory")
        self.conn.executemany(
            "INSERT INTO inventory (item_type, count) VALUES (?, ?)",
            list(inventory.to_save_dict().items()),
        )
        self.conn.commit()

    def get_room_flags(self, room_id):
        rows = self.conn.execute(
            "SELECT flag_type, entity_id FROM room_flags WHERE room_id = ?",
            (room_id,),
        )
        dead_enemies, taken_items = set(), set()
        for flag_type, entity_id in rows:
            if flag_type == "enemy_dead":
                dead_enemies.add(entity_id)
            elif flag_type == "item_taken":
                taken_items.add(entity_id)
        return {"dead_enemies": dead_enemies, "taken_items": taken_items}

    def set_room_flags(self, room_id, dead_enemies, taken_items):
        self.conn.execute("DELETE FROM room_flags WHERE room_id = ?", (room_id,))
        rows = [(room_id, "enemy_dead", eid) for eid in dead_enemies]
        rows += [(room_id, "item_taken", iid) for iid in taken_items]
        self.conn.executemany(
            "INSERT INTO room_flags (room_id, flag_type, entity_id) VALUES (?, ?, ?)",
            rows,
        )
        self.conn.commit()

    def close(self):
        self.conn.close()
