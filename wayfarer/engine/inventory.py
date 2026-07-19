"""Slot-based inventory. Item definitions (name/sprite/effect/value) come
from data/items.json; the inventory itself only tracks type -> count.

Future work (out of scope for this pass): equippable gear, ranged items.
"""

MAX_SLOTS = 8


class Inventory:
    def __init__(self, item_defs, starting_counts=None):
        self.item_defs = item_defs
        self.slots = MAX_SLOTS
        # dict preserves insertion order -> stable display order in the UI
        self.stacks = dict(starting_counts or {})

    def add_item(self, item_type):
        if item_type in self.stacks:
            self.stacks[item_type] += 1
            return True
        if len(self.stacks) >= self.slots:
            return False
        self.stacks[item_type] = 1
        return True

    def use_item(self, item_type, player):
        count = self.stacks.get(item_type, 0)
        if count <= 0:
            return False, "You don't have that."

        item_def = self.item_defs.get(item_type, {})
        effect = item_def.get("effect")
        name = item_def.get("name", item_type)

        consumed = True
        if effect == "heal":
            healed = min(item_def.get("value", 0), player.max_hp - player.hp)
            player.hp += healed
            message = f"Used {name}. Restored {healed} HP."
        elif effect == "buff_attack":
            bonus = item_def.get("value", 0)
            player.attack += bonus
            message = f"Used {name}. Attack +{bonus} permanently."
        elif effect == "buff_defense":
            bonus = item_def.get("value", 0)
            player.defense += bonus
            message = f"Used {name}. Defense +{bonus} permanently."
        elif effect == "restore_mana":
            restored = min(item_def.get("value", 0), player.max_mana - player.mana)
            player.mana += restored
            message = f"Used {name}. Restored {restored} mana."
        else:
            # Items with no U-key effect (e.g. a "key", used automatically
            # by bumping a locked door -- see Inventory.remove_item) aren't
            # consumed by a stray press here, so one can't be wasted.
            message = f"{name} has no effect."
            consumed = False

        if consumed:
            self.stacks[item_type] -= 1
            if self.stacks[item_type] <= 0:
                del self.stacks[item_type]

        return True, message

    def remove_item(self, item_type, count=1):
        """Remove `count` of item_type outside the use_item() effect
        dispatch -- e.g. consuming a key to unlock a door, triggered by
        bumping the door rather than pressing U in the inventory screen."""
        have = self.stacks.get(item_type, 0)
        if have < count:
            return False
        self.stacks[item_type] -= count
        if self.stacks[item_type] <= 0:
            del self.stacks[item_type]
        return True

    def as_list(self):
        result = []
        for item_type, count in self.stacks.items():
            item_def = self.item_defs.get(item_type, {})
            result.append((item_type, count, item_def))
        return result

    def to_save_dict(self):
        return dict(self.stacks)
