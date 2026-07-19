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

    dmg_to_player = max(1, enemy.attack - (player.defense + player.buff_defense_bonus))
    player.hp -= dmg_to_player
    log.append(f"{enemy.name} hits you for {dmg_to_player}.")

    if player.hp <= 0:
        player.hp = 0
        log.append("You have fallen...")

    return log


def resolve_spell_hit(player, enemy, damage, spell_name):
    """A ranged/bolt-type spell's damage against `enemy` (session 12) --
    like the first half of resolve_bump_attack, but the enemy is never
    adjacent so it never gets a retaliatory hit here; on-kill handling is
    identical (see _apply_defeat)."""
    log = [f"You cast {spell_name}. Hits {enemy.name} for {damage}."]
    enemy.hp -= damage
    AssetManager.play_sfx("hit")

    if enemy.hp <= 0:
        _apply_defeat(player, enemy, log)

    return log


def enemy_attack(enemy, player):
    """A single enemy-initiated hit (no counter -- it's the enemy's turn)."""
    dmg = max(1, enemy.attack - (player.defense + player.buff_defense_bonus))
    player.hp -= dmg
    log = [f"{enemy.name} hits you for {dmg}."]
    AssetManager.play_sfx("hit")

    if player.hp <= 0:
        player.hp = 0
        log.append("You have fallen...")

    return log


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
        player.mana = player.max_mana
        log.append(f"Level up! You are now level {player.level}.")
        AssetManager.play_sfx("levelup")
        threshold = player.level * XP_PER_LEVEL
