"""Bump-combat resolution: the player and enemy simply trade one hit each.
No hitboxes, no timing windows -- matches the Desktop Adventures style
combat called for in the design brief."""

import random

from engine.assets import AssetManager

XP_PER_LEVEL = 30


def _apply_defeat(player, enemy, log):
    """Shared "enemy just died" handling -- gold roll, XP/level-up, kill sfx.
    Used by both a melee kill and a spell kill (engine/spells.py's bolt
    effect, resolved in main.py's Game.cast_selected_spell) so the two
    damage sources can't drift out of sync on rewards."""
    gold = random.randint(*enemy.gold_reward) if enemy.gold_reward[1] > 0 else 0
    player.gold += gold
    gold_note = f", +{gold} gold" if gold else ""
    log.append(f"{enemy.name} is defeated! +{enemy.xp_reward} XP{gold_note}")
    grant_xp(player, enemy.xp_reward, log)
    AssetManager.play_sfx("kill")


def _maybe_poison(enemy, player, log):
    """Session 21: a Viper-style bite that has a chance to inflict a
    damage-over-time status rather than (or alongside) its direct hit --
    see engine/entity.py's Enemy.poison_chance/poison_damage/poison_duration
    and Player.poison_turns/poison_damage. A no-op for every enemy that
    doesn't define poison_chance (i.e. every enemy type except Viper today).
    Refreshes rather than stacks -- keeps whichever of the current and new
    tick/duration is larger, so repeated bites don't compound into an
    ever-growing per-tick damage number."""
    if enemy.poison_chance <= 0 or random.random() >= enemy.poison_chance:
        return
    player.poison_turns = max(player.poison_turns, enemy.poison_duration)
    player.poison_damage = max(player.poison_damage, enemy.poison_damage)
    log.append(f"{enemy.name}'s bite poisons you!")


def _maybe_drain(enemy, player, log):
    """Session 24: a Wraith-style touch that has a chance to permanently
    lower the player's usable mana ceiling rather than (or alongside) its
    direct hit -- see engine/entity.py's Enemy.drain_chance/drain_amount and
    Player.mana_drain/resist_undead. A no-op for every enemy that doesn't
    define drain_chance (i.e. every enemy type except the Wraith/Wight
    families today), same shape as _maybe_poison above. Unlike poison, this
    never wears off on its own -- only paying the Healer (main.py's
    cure_mana_drain/cure_attack_drain) reverses it -- so each additional
    bite adds to the running total rather than refreshing a duration.

    Session 37: enemy.drain_stat picks which stat this particular touch
    lowers -- "mana" (Wraith family, unchanged from session 24) or "attack"
    (Wight family, Castle of the Winds' STR/DEX/CON drain -- see
    Player.attack_drain's docstring for why attack stands in for those).
    Both share the same resist_undead mitigation and running-total-not-
    duration persistence; only which field they touch differs."""
    if enemy.drain_chance <= 0 or random.random() >= enemy.drain_chance:
        return
    resist = min(RESIST_CAP, max(0, player.resist_undead))
    amount = max(1, round(enemy.drain_amount * (100 - resist) / 100))
    if enemy.drain_stat == "attack":
        amount = min(amount, player.attack - 1)  # never drain below 1 attack
        if amount <= 0:
            return
        player.attack -= amount
        player.attack_drain += amount
        log.append(f"{enemy.name}'s touch saps your strength!")
    else:
        player.mana_drain += amount
        player.mana = min(player.mana, player.effective_max_mana())
        log.append(f"{enemy.name}'s touch drains your mana away!")


RESIST_CAP = 90  # never let a single amulet reach true immunity


def _enemy_damage_to_player(enemy, player):
    """Session 22: a "physical" attack (every pre-existing enemy, the
    default) is mitigated by defense exactly as before. Anything else
    (Castle of the Winds' fire/cold/lightning) bypasses defense entirely --
    armor stops blows, not flame -- and is instead mitigated by the
    player's resist_elemental percentage, sourced from an equipped amulet
    (see engine/equipment.py). Shared by resolve_bump_attack's counter-hit
    and enemy_attack's initiated hit so the two paths can't drift apart."""
    if enemy.damage_type == "physical":
        return max(1, enemy.attack - (player.defense + player.buff_defense_bonus))
    # Session 34: a Resist Fire/Cold/Lightning spell stacks additively on
    # top of the flat, always-on amulet resist -- e.g. a player with a +20%
    # Amulet of Resistance who casts Resist Fire (+50%) mitigates 70% of an
    # incoming fire hit, not just whichever of the two is larger.
    resist = player.resist_elemental + player.temp_resist_bonus(enemy.damage_type)
    resist = min(RESIST_CAP, max(0, resist))
    return max(1, round(enemy.attack * (100 - resist) / 100))


def resolve_ball_splash_to_player(player, base_damage, damage_type):
    """Session 41: Fireball/Cold Ball/Ball Lightning's own source material
    notes the blast "may hurt the player" -- in this engine's facing-line
    targeting (no free tile-cursor aim like the real game's), that happens
    whenever the ball detonates adjacent to the player, since the 3x3 ring
    covers the player's own tile in that case (see main.py's
    cast_selected_spell "ball" branch). Same resist formula
    _enemy_damage_to_player uses -- the amulet's flat resist_elemental plus
    any active Resist spell -- just keyed off the spell's own damage_type/
    value instead of an attacking enemy's."""
    resist = player.resist_elemental + player.temp_resist_bonus(damage_type)
    resist = min(RESIST_CAP, max(0, resist))
    return max(1, round(base_damage * (100 - resist) / 100))


def resolve_bump_attack(player, enemy):
    """Player hits enemy; if the enemy survives, it hits back once.
    Returns a list of short log strings for the HUD."""
    log = []

    dmg_to_enemy = max(1, player.attack - enemy.defense)
    enemy.hp -= dmg_to_enemy
    log.append(f"You hit {enemy.name} for {dmg_to_enemy}.")
    AssetManager.play_sfx("hit")

    if enemy.hp <= 0:
        _apply_defeat(player, enemy, log)
        return log

    if enemy.sleep_turns > 0:
        # Session 40: Castle of the Winds' Sleep Monster wears off "when
        # attacked" -- waking mid-swing means the enemy doesn't get this
        # exchange's retaliation, the same "free hit" a sneak attack on a
        # sleeping target implies. A still-sleeping enemy never reaches
        # take_turn's own chase/attack branch either (see engine/entity.py),
        # so skipping the counter-hit here is the only place this needs to
        # be enforced.
        enemy.sleep_turns = 0
        log.append(f"{enemy.name} wakes with a start!")
        return log

    dmg_to_player = _enemy_damage_to_player(enemy, player)
    player.hp -= dmg_to_player
    log.append(f"{enemy.name} hits you for {dmg_to_player}.")
    _maybe_poison(enemy, player, log)
    _maybe_drain(enemy, player, log)

    if player.hp <= 0:
        player.hp = 0
        log.append("You have fallen...")

    return log


def resolve_spell_hit(player, enemy, damage, spell_name, damage_type="physical"):
    """A ranged/bolt-type spell's damage against `enemy` (session 12) --
    like the first half of resolve_bump_attack, but the enemy is never
    adjacent so it never gets a retaliatory hit here; on-kill handling is
    identical (see _apply_defeat).

    Session 22: `damage_type` looks up `enemy.resist_elements` -- a monster
    fully resistant to its own element (1.0, e.g. the Young Red Dragon's
    fire) takes no damage at all, matching Castle of the Winds' own
    "immune to fire, breathes fire" dragons; a partial value (not used by
    any enemy yet, but the same mechanism session 21's poison_chance-style
    zero-by-default fields already establish) would scale it down instead.
    A "physical" spell (every pre-existing one) is never looked up here at
    all, so this is a no-op for the existing Spark."""
    resist = enemy.resist_elements.get(damage_type, 0) if damage_type != "physical" else 0
    if resist >= 1:
        AssetManager.play_sfx("hit")
        return [f"You cast {spell_name}, but {enemy.name} is immune to it."]

    effective = max(1, round(damage * (1 - resist))) if resist else damage
    wake_note = ""
    if enemy.sleep_turns > 0:
        # Session 40: a bolt spell has no retaliation to skip (it's ranged,
        # see this function's own docstring), but a sleeping enemy hit by
        # one should still wake rather than staying asleep for a hit it
        # very much felt.
        enemy.sleep_turns = 0
        wake_note = f" {enemy.name} wakes with a start!"
    log = [f"You cast {spell_name}. Hits {enemy.name} for {effective}.{wake_note}"]
    enemy.hp -= effective
    AssetManager.play_sfx("hit")

    if enemy.hp <= 0:
        _apply_defeat(player, enemy, log)

    return log


def enemy_attack(enemy, player):
    """A single enemy-initiated hit (no counter -- it's the enemy's turn)."""
    dmg = _enemy_damage_to_player(enemy, player)
    player.hp -= dmg
    log = [f"{enemy.name} hits you for {dmg}."]
    AssetManager.play_sfx("hit")
    _maybe_poison(enemy, player, log)
    _maybe_drain(enemy, player, log)

    if player.hp <= 0:
        player.hp = 0
        log.append("You have fallen...")

    return log


def resolve_trap(player, trap_def, log):
    """Session 28: a sprung dungeon trap (Castle of the Winds' dart/pit/gas
    traps). Damage bypasses defense entirely -- it's an environmental
    mechanism, not a weapon blow, same "armor doesn't stop this" reasoning
    session 22 already applied to elemental damage, just for a different
    reason here (no incoming attack to parry, only a hazard to step in).
    A poison-gas trap also inflicts the same refreshes-rather-than-stacks
    DoT a Viper's bite does (see _maybe_poison) -- reuses Player.poison_turns/
    poison_damage directly rather than a separate trap-poison field.

    Session 29: Levitation makes the player "impervious to non-magical
    traps" (Castle of the Winds' own wording) -- every trap type this engine
    has is non-magical, so an active levitation_turns buff skips damage and
    the poison DoT outright rather than reducing them."""
    if player.levitation_turns > 0:
        log.append(f"{trap_def['trigger_message']} You drift over it, untouched.")
        return log
    dmg = random.randint(trap_def["damage_min"], trap_def["damage_max"])
    player.hp = max(0, player.hp - dmg)
    log.append(f"{trap_def['trigger_message']} You take {dmg} damage.")
    AssetManager.play_sfx("hit")

    if trap_def.get("poison_damage"):
        player.poison_turns = max(player.poison_turns, trap_def["poison_duration"])
        player.poison_damage = max(player.poison_damage, trap_def["poison_damage"])
        log.append("You feel sickly.")

    if player.hp <= 0:
        log.append("You have fallen...")

    return log


def resolve_disarm(player, trap_def, log):
    """Session 29: Castle of the Winds' Disarm Trap command, attempted
    against a *detected* trap directly ahead of the player (see main.py's
    Game.attempt_disarm) rather than a walk-onto. Chance is the trap's own
    base difficulty plus a small per-level bonus, capped so a tough trap is
    never a certainty. Success permanently neutralizes it (same "sprung and
    inert forever" state a walk-onto trigger leaves behind) and grants XP;
    failure springs it exactly like blundering onto it blind, including
    Levitation's damage immunity via resolve_trap above."""
    chance = min(0.95, trap_def.get("disarm_chance", 0.5) + player.level * 0.02)
    if random.random() < chance:
        log.append(f"You carefully disarm the {trap_def['name'].lower()}.")
        AssetManager.play_sfx("pickup")
        grant_xp(player, trap_def.get("disarm_xp", 5), log)
        return True, log
    log.append("Your fingers slip -- it triggers!")
    resolve_trap(player, trap_def, log)
    return False, log


def grant_xp(player, amount, log):
    player.xp += amount
    threshold = player.level * XP_PER_LEVEL
    while player.xp >= threshold:
        player.xp -= threshold
        player.level += 1
        player.max_hp += 10
        player.hp = player.max_hp
        player.attack += 2
        player.max_mana += 5
        # Session 24: refills to the *effective* (post-drain) ceiling, not
        # the raw stat -- leveling up still grows max_mana as always, but a
        # Wraith's drain isn't cured by leveling, matching CotW's own
        # "restore it at the Temple or with a potion" rule for drained stats.
        player.mana = player.effective_max_mana()
        log.append(f"Level up! You are now level {player.level}.")
        AssetManager.play_sfx("levelup")
        threshold = player.level * XP_PER_LEVEL
