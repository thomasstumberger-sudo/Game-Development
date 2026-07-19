"""Spell definitions come from data/spells.json (a plain ordered list, not
keyed by id, since unlock order matters for the level-up scan below);
main.py loads it once and keeps a dict for O(1) lookup by id.

Session 12: the player gains a spell automatically when their level reaches
its `unlock_level` -- no spellbook items to find/buy, matching only the
"auto-learn on level" half of the Castle of the Winds spell system (see
PROGRESS.MD). Casting itself (targeting, mana spend, effect resolution)
needs live Room/Enemy state, so it lives on Game in main.py rather than
here, the same split combat.py/main.py already have for bump attacks.

Session 19 added the other half of the source material's system: a Scholar
NPC (see main.py's buy_spellbook) sells any not-yet-known spell for gold,
learned immediately regardless of level -- it adds straight to the same
known_spells set newly_learned() feeds, so nothing here needed to change.

Future work (out of scope for this pass): spellbooks as dungeon loot rather
than shop-only, more than one spell per category, quick-cast hotkey (today
casting only happens from the Spellbook panel).
"""


def newly_learned(spell_defs, level, known_ids):
    """Spells whose unlock_level is now <= level but aren't in known_ids
    yet, in spell_defs order. Pure/side-effect-free -- the caller adds the
    returned ids to its known set and reports them. Safe to call after
    every level-up (or once at boot to catch up an existing save) since
    it's a no-op scan when nothing new qualifies -- O(len(spell_defs)),
    trivial next to the per-turn budget."""
    return [s for s in spell_defs if s["unlock_level"] <= level and s["id"] not in known_ids]
