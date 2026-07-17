"""Bump-combat resolution: the player and enemy simply trade one hit each.
No hitboxes, no timing windows -- matches the Desktop Adventures style
combat called for in the design brief."""

from engine.assets import AssetManager

XP_PER_LEVEL = 30


def resolve_bump_attack(player, enemy):
    """Player hits enemy; if the enemy survives, it hits back once.
    Returns a list of short log strings for the HUD."""
    log = []

    dmg_to_enemy = max(1, player.attack - enemy.defense)
    enemy.hp -= dmg_to_enemy
    log.append(f"You hit {enemy.name} for {dmg_to_enemy}.")
    AssetManager.play_sfx("hit")

    if enemy.hp <= 0:
        log.append(f"{enemy.name} is defeated! +{enemy.xp_reward} XP")
        _grant_xp(player, enemy.xp_reward, log)
        AssetManager.play_sfx("kill")
        return log

    dmg_to_player = max(1, enemy.attack - player.defense)
    player.hp -= dmg_to_player
    log.append(f"{enemy.name} hits you for {dmg_to_player}.")

    if player.hp <= 0:
        player.hp = 0
        log.append("You have fallen...")

    return log


def enemy_attack(enemy, player):
    """A single enemy-initiated hit (no counter -- it's the enemy's turn)."""
    dmg = max(1, enemy.attack - player.defense)
    player.hp -= dmg
    log = [f"{enemy.name} hits you for {dmg}."]
    AssetManager.play_sfx("hit")

    if player.hp <= 0:
        player.hp = 0
        log.append("You have fallen...")

    return log


def _grant_xp(player, amount, log):
    player.xp += amount
    threshold = player.level * XP_PER_LEVEL
    while player.xp >= threshold:
        player.xp -= threshold
        player.level += 1
        player.max_hp += 10
        player.hp = player.max_hp
        player.attack += 2
        log.append(f"Level up! You are now level {player.level}.")
        threshold = player.level * XP_PER_LEVEL
