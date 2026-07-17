"""Procedurally generated rooms -- "the Depths", reached through the Crypt's
east exit. Each room is addressed by grid coordinates (gx, gy) on an
infinite plane and regenerated deterministically from (seed, gx, gy): no
room geometry is ever written to the save file, only the run's seed and
which enemies/items in already-visited rooms have been consumed (via the
same room_flags table the hand-authored rooms use). Because a room is a
pure function of its own coordinates, two neighboring rooms independently
agree on whether the wall between them has a doorway -- both derive that
from the same canonical edge key -- so the dungeon is always fully
connected without any cross-room bookkeeping.

Future work: varied room shapes/interior obstacles, depth-scaled difficulty.
"""

import random

WIDTH, HEIGHT = 10, 8
MID_X, MID_Y = 5, 4
EDGE_OPEN_CHANCE = 0.55
ENEMY_TYPES = ["skeleton"]
ITEM_TYPES = ["potion", "potion", "whetstone"]  # weighted toward potions

DIRECTIONS = {
    "N": (0, -1),
    "S": (0, 1),
    "E": (1, 0),
    "W": (-1, 0),
}


def _edge_open(seed, gx, gy, direction):
    if (gx, gy) == (0, 0) and direction == "W":
        return True  # guaranteed link back to the Crypt
    ddx, ddy = DIRECTIONS[direction]
    neighbor = (gx + ddx, gy + ddy)
    edge_key = tuple(sorted([(gx, gy), neighbor]))
    rng = random.Random(f"{seed}:edge:{edge_key}")
    return rng.random() < EDGE_OPEN_CHANCE


def _exit_point(direction, side):
    """side='near': the door cell on this room's own border.
    side='far': the landing cell one step inside the neighboring room."""
    if direction == "N":
        return (MID_X, 0) if side == "near" else (MID_X, HEIGHT - 2)
    if direction == "S":
        return (MID_X, HEIGHT - 1) if side == "near" else (MID_X, 1)
    if direction == "E":
        return (WIDTH - 1, MID_Y) if side == "near" else (1, MID_Y)
    if direction == "W":
        return (0, MID_Y) if side == "near" else (WIDTH - 2, MID_Y)
    raise ValueError(direction)


def generate_room(seed, gx, gy):
    rng = random.Random(f"{seed}:room:{gx}:{gy}")

    layout = [["#"] * WIDTH for _ in range(HEIGHT)]
    for y in range(1, HEIGHT - 1):
        for x in range(1, WIDTH - 1):
            layout[y][x] = "."

    exits = []
    door_cells = set()
    for direction, (ddx, ddy) in DIRECTIONS.items():
        if not _edge_open(seed, gx, gy, direction):
            continue

        near_x, near_y = _exit_point(direction, "near")
        layout[near_y][near_x] = "."
        door_cells.add((near_x, near_y))

        if (gx, gy) == (0, 0) and direction == "W":
            target_room, target_x, target_y = "crypt", 8, 4
        else:
            ngx, ngy = gx + ddx, gy + ddy
            target_room = f"proc:{seed}:{ngx}:{ngy}"
            target_x, target_y = _exit_point(direction, "far")

        exits.append({
            "id": f"to_{direction}",
            "x": near_x, "y": near_y,
            "target_room": target_room,
            "target_x": target_x, "target_y": target_y,
        })

    interior = [
        (x, y)
        for y in range(1, HEIGHT - 1)
        for x in range(1, WIDTH - 1)
        if (x, y) not in door_cells
    ]
    rng.shuffle(interior)

    enemies = []
    for i in range(rng.randint(0, 2)):
        if not interior:
            break
        x, y = interior.pop()
        enemies.append({
            "id": f"proc_{seed}_{gx}_{gy}_e{i}",
            "type": rng.choice(ENEMY_TYPES),
            "x": x, "y": y,
        })

    items = []
    if interior and rng.random() < 0.6:
        x, y = interior.pop()
        items.append({
            "id": f"proc_{seed}_{gx}_{gy}_i0",
            "type": rng.choice(ITEM_TYPES),
            "x": x, "y": y,
        })

    return {
        "name": f"The Depths ({gx}, {gy})",
        "layout": ["".join(row) for row in layout],
        "exits": exits,
        "enemies": enemies,
        "items": items,
    }
