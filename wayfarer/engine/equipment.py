"""Equipment: five gear slots (weapon/shield/helmet/armor/boots), each
holding at most one item from data/equipment.json.

Session 16 (Castle of the Winds-inspired): equipment is now per-instance
rather than a bare item_type string, so two Longswords can differ. Dungeon-
found gear (see engine/procgen.py's "equipment" loot family) rolls a random
enchantment (-3..+3, see ENCHANT_WEIGHTS) and is unidentified until it's
either equipped or paid-for identification at the Merchant reveals it first
-- CotW's classic "find out by wearing it" risk. Shop-bought gear is still
always a fresh +0, uncursed, already-identified instance (buying a known
quantity from a known merchant is no mystery) -- see main.py's
buy_or_upgrade/create_shop_instance.

player.equipment_instances holds every instance the player has ever owned,
keyed by instance_id -- both what's currently equipped and whatever's
sitting unequipped in the "Found Gear" bag (main.py's inventory panel).
player.equipment[slot] still holds just one thing per slot, same shape
session 8 originally gave it, but now an instance_id instead of a bare
item_type string -- save.py's schema needed no changes, only what's stored
in those columns changed meaning.

Curses: a negative enchant always means cursed (rolled that way, see
procgen.py -- there's no separate independent curse flag to drift out of
sync with it). A cursed item cannot be unequipped once worn, same as the
source material, until Remove Curse (also a Merchant service, paid -- see
main.py) lifts the curse; the item's enchant is untouched by that, only the
"stuck" behavior is -- "uncursed" isn't the same as "no longer a bad item."

Future work (out of scope for this pass): ring/amulet slots, chest loot
using this same per-instance path (vault chests still only ever hold plain
consumables, see procgen.py).
"""

SLOTS = ("weapon", "shield", "helmet", "armor", "boots")

# Weighted like a bell curve centered on 0 -- most found gear is
# unremarkable, strong enchantments and curses are both rare. Shared with
# procgen.py (imported from there) so the two files can't define
# conflicting odds.
ENCHANT_WEIGHTS = [(-3, 1), (-2, 3), (-1, 8), (0, 55), (1, 20), (2, 10), (3, 3)]


def roll_enchant(rng):
    total = sum(w for _, w in ENCHANT_WEIGHTS)
    roll = rng.random() * total
    upto = 0.0
    for value, weight in ENCHANT_WEIGHTS:
        upto += weight
        if roll <= upto:
            return value
    return ENCHANT_WEIGHTS[-1][0]


def create_instance(player, base_type, enchant=0, identified=True):
    """Registers a new owned instance (not yet equipped -- lands in the
    "Found Gear" bag until something equips it) and returns its id.
    Negative enchant is always cursed -- see module docstring."""
    player.next_equip_instance_num += 1
    instance_id = f"eq{player.next_equip_instance_num}"
    player.equipment_instances[instance_id] = {
        "instance_id": instance_id,
        "base_type": base_type,
        "enchant": enchant,
        "cursed": enchant < 0,
        "identified": identified,
    }
    return instance_id


def create_shop_instance(player, base_type):
    """Merchant purchases are always a fresh +0, uncursed, identified
    instance -- see module docstring."""
    return create_instance(player, base_type, enchant=0, identified=True)


def bag_instances(player):
    """Owned instances not currently equipped in any slot, in the order
    they were acquired -- what the inventory panel's "Found Gear" section
    lists."""
    equipped_ids = set(player.equipment.values())
    return [
        inst for iid, inst in player.equipment_instances.items()
        if iid not in equipped_ids
    ]


def display_name(equipment_defs, instance):
    if instance is None:
        return "--"
    base_name = equipment_defs[instance["base_type"]]["name"]
    if not instance["identified"]:
        return f"{base_name} (unidentified)"
    enchant = instance["enchant"]
    name = base_name if enchant == 0 else f"{base_name} {enchant:+d}"
    if instance["cursed"]:
        name += " [cursed]"
    return name


def _bonus(item_def, instance):
    atk, dfn = item_def.get("attack", 0), item_def.get("defense", 0)
    enchant = instance["enchant"]
    # Enchant modifies whichever stat(s) the base item already grants -- a
    # +2 sword hits harder, a +2 shield blocks more.
    if atk:
        atk += enchant
    if dfn:
        dfn += enchant
    return atk, dfn


def unequip(player, equipment_defs, slot):
    """Remove whatever's in `slot`, reversing its stat bonus. Returns the
    freed instance_id, None if the slot was already empty, or the string
    "cursed" if the currently-equipped instance refuses to come off (caller
    shows a message; nothing changes)."""
    instance_id = player.equipment.get(slot)
    if instance_id is None:
        return None
    instance = player.equipment_instances[instance_id]
    if instance["cursed"]:
        return "cursed"
    atk, dfn = _bonus(equipment_defs[instance["base_type"]], instance)
    player.attack -= atk
    player.defense -= dfn
    player.equipment[slot] = None
    return instance_id


def equip(player, equipment_defs, instance_id):
    """Equip `instance_id` (already registered via create_instance, whether
    just bought or found earlier and sitting in the bag), replacing
    whatever was in that slot. Equipping always identifies the instance --
    the moment a curse can lock the slot for good. Returns "ok", or
    "cursed" if the slot's current occupant refuses to come off."""
    instance = player.equipment_instances[instance_id]
    slot = equipment_defs[instance["base_type"]]["slot"]
    result = unequip(player, equipment_defs, slot)
    if result == "cursed":
        return "cursed"
    instance["identified"] = True
    atk, dfn = _bonus(equipment_defs[instance["base_type"]], instance)
    player.attack += atk
    player.defense += dfn
    player.equipment[slot] = instance_id
    return "ok"


def remove_curse(player, equipment_defs, slot):
    """Lifts the curse on whatever's equipped in `slot` (paid Merchant
    service -- see main.py) so it can be unequipped normally again. Leaves
    its enchant untouched. Returns False if the slot is empty or its
    occupant isn't actually cursed (nothing to do)."""
    instance_id = player.equipment.get(slot)
    if instance_id is None:
        return False
    instance = player.equipment_instances[instance_id]
    if not instance["cursed"]:
        return False
    instance["cursed"] = False
    return True


def next_offer(player, equipment_defs, slot):
    """The next purchasable item for `slot`: tier 1 if the slot is empty,
    else the def one tier above whatever's currently equipped, or None if
    already at the top tier. The shop shows exactly one offer per slot at
    a time -- buying it always means the next rung up the ladder."""
    instance_id = player.equipment.get(slot)
    if instance_id is not None:
        current_type = player.equipment_instances[instance_id]["base_type"]
        current_tier = equipment_defs[current_type]["tier"]
    else:
        current_tier = 0
    for item_type, item_def in equipment_defs.items():
        if item_def["slot"] == slot and item_def["tier"] == current_tier + 1:
            return item_type
    return None
