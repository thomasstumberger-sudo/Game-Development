"""Wayfarer -- entry point.

The single most important property of this loop: it is CPU-cheap at idle.
- The frame rate is hard-capped (never uncapped, never busy-waits).
- When the window loses focus, input is still polled but the loop throttles
  down to ~5Hz.
- The screen is only redrawn when something actually changed (dirty flag),
  except while the F3 debug overlay is on, where a live reading is the
  whole point of the feature.

Future work (explicitly out of scope for this pass): procedural rooms,
networking, controller support, scrolling maps.
"""

import os
import sys
import json

import pygame

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from engine.assets import AssetManager, BASE_DIR
from engine.room import Room
from engine.entity import Player, Enemy, ItemPickup
from engine.combat import resolve_bump_attack
from engine.inventory import Inventory
from engine.save import SaveManager

WINDOW_W, WINDOW_H = 640, 480
TILE_SIZE = 48
ROOM_PIXEL_W, ROOM_PIXEL_H = 10 * TILE_SIZE, 8 * TILE_SIZE
ROOM_ORIGIN = ((WINDOW_W - ROOM_PIXEL_W) // 2, 40)

ACTIVE_FPS = 30
IDLE_FPS = 5

SAVE_PATH = os.path.join(BASE_DIR, "save.db")

COLOR_BG = (10, 10, 14)
COLOR_HP = (200, 40, 40)
COLOR_HP_BG = (50, 15, 15)
COLOR_TEXT = (230, 230, 230)
COLOR_DEBUG = (0, 255, 0)
COLOR_PANEL_BG = (20, 20, 28, 235)


class Game:
    def __init__(self, screen):
        self.screen = screen
        self.room_surface = screen.subsurface(
            pygame.Rect(*ROOM_ORIGIN, ROOM_PIXEL_W, ROOM_PIXEL_H)
        )

        self._load_assets()
        with open(os.path.join(BASE_DIR, "data", "items.json")) as f:
            self.item_defs = json.load(f)
        with open(os.path.join(BASE_DIR, "data", "enemies.json")) as f:
            self.enemy_defs = json.load(f)

        self.save = SaveManager(SAVE_PATH)
        state = self.save.load_game() or self.save.new_game_defaults()

        self.player = Player(state["pos"][0], state["pos"][1], state["player"])
        self.inventory = Inventory(self.item_defs, state["inventory"])

        self.current_room_id = None
        self.room = None
        self.enemies = []
        self.items = []
        self.dead_enemy_ids = set()
        self.taken_item_ids = set()

        self.message_log = []
        self.inventory_open = False
        self.inventory_cursor = 0
        self.dirty = True

        self.load_room(state["current_room"], state["pos"][0], state["pos"][1])

    def _load_assets(self):
        AssetManager.load_sprite("wall", "assets/sprites/dungeon_tileset_1/tile_1_0.png")
        AssetManager.load_sprite("floor", "assets/sprites/dungeon_tileset_1/tile_0_2.png")
        AssetManager.load_sprite("exit", "assets/sprites/dungeon_tileset_1/tile_12_6.png")
        AssetManager.load_sprite("item_potion", "assets/sprites/dungeon_tileset_1/tile_0_11.png")
        AssetManager.load_sprite("enemy_skeleton", "assets/sprites/dungeon_tileset_1/tile_0_7.png")
        # No humanoid tile exists in the source tileset -- draw the player
        # once and cache it, same as any other sprite.
        AssetManager.make_placeholder("player", (70, 130, 220))
        AssetManager.get_font(14)
        AssetManager.get_font(16, bold=True)
        AssetManager.get_font(20, bold=True)

    # -- room lifecycle ----------------------------------------------------

    def load_room(self, room_id, spawn_x, spawn_y):
        self.current_room_id = room_id
        self.room = Room.load(room_id)

        flags = self.save.get_room_flags(room_id)
        self.dead_enemy_ids = set(flags["dead_enemies"])
        self.taken_item_ids = set(flags["taken_items"])

        self.enemies = [
            Enemy(t["id"], t["type"], t["x"], t["y"], self.enemy_defs[t["type"]])
            for t in self.room.enemy_templates
            if t["id"] not in self.dead_enemy_ids
        ]
        self.items = [
            ItemPickup(t["id"], t["type"], t["x"], t["y"], self.item_defs[t["type"]])
            for t in self.room.item_templates
            if t["id"] not in self.taken_item_ids
        ]

        self.player.x, self.player.y = spawn_x, spawn_y
        self.message_log = [f"Entered {self.room.name}."]
        self.dirty = True

    def persist(self):
        """Full autosave: current room flags + player + inventory.
        Called on room transition and on quit -- never per-frame."""
        self.save.set_room_flags(self.current_room_id, self.dead_enemy_ids, self.taken_item_ids)
        self.save.save_game(self.player, self.inventory, self.current_room_id)

    # -- input handlers ------------------------------------------------

    def handle_move(self, dx, dy):
        if self.player.hp <= 0:
            return
        result = self.player.try_move(dx, dy, self.room, self.enemies, self.items)
        self.dirty = True
        kind = result["type"]

        if kind == "attack":
            enemy = result["enemy"]
            log = resolve_bump_attack(self.player, enemy)
            self.message_log = log[-3:]
            if not enemy.alive:
                self.dead_enemy_ids.add(enemy.id)
                self.enemies = [e for e in self.enemies if e.alive]
            if self.player.hp <= 0:
                self._handle_death()

        elif kind == "pickup":
            item = result["item"]
            if self.inventory.add_item(item.type):
                self.taken_item_ids.add(item.id)
                self.items = [i for i in self.items if i.id != item.id]
                self.message_log = [f"Picked up {item.name}."]
            else:
                self.message_log = ["Inventory full."]

        elif kind == "exit":
            exit_data = result["exit"]
            self.persist()
            self.load_room(exit_data["target_room"], exit_data["target_x"], exit_data["target_y"])

        # "blocked" and "moved" need no further handling beyond the redraw.

    def _handle_death(self):
        saved = self.save.load_game()
        if saved is None:
            target_room, (target_x, target_y) = self.current_room_id, (self.player.x, self.player.y)
        else:
            target_room, (target_x, target_y) = saved["current_room"], saved["pos"]
        self.player.hp = self.player.max_hp
        self.load_room(target_room, target_x, target_y)
        self.message_log = ["You have fallen. Reviving at your last save..."]

    def toggle_inventory(self):
        self.inventory_open = not self.inventory_open
        self.inventory_cursor = 0
        self.dirty = True

    def inventory_move_cursor(self, delta):
        items = self.inventory.as_list()
        if not items:
            return
        self.inventory_cursor = (self.inventory_cursor + delta) % len(items)
        self.dirty = True

    def use_selected_item(self):
        items = self.inventory.as_list()
        if not items:
            return
        item_type, _count, _def = items[self.inventory_cursor]
        _success, message = self.inventory.use_item(item_type, self.player)
        self.message_log = [message]
        remaining = self.inventory.as_list()
        self.inventory_cursor = min(self.inventory_cursor, max(0, len(remaining) - 1))
        self.dirty = True

    # -- rendering -----------------------------------------------------

    def draw(self, fps_target, is_focused, actual_fps, debug_overlay):
        screen = self.screen
        screen.fill(COLOR_BG)

        self.room_surface.fill((0, 0, 0))
        self.room.draw(self.room_surface, TILE_SIZE)
        for item in self.items:
            item.draw(self.room_surface, TILE_SIZE)
        for enemy in self.enemies:
            enemy.draw(self.room_surface, TILE_SIZE)
        self.player.draw(self.room_surface, TILE_SIZE)

        self._draw_hud()
        self._draw_message_log()
        if debug_overlay:
            self._draw_debug_overlay(fps_target, is_focused, actual_fps)
        if self.inventory_open:
            self._draw_inventory()

        pygame.display.flip()

    def _draw_hud(self):
        font = AssetManager.get_font(16, bold=True)
        hp_text = font.render(f"HP {self.player.hp}/{self.player.max_hp}", True, COLOR_TEXT)
        lvl_text = font.render(
            f"Lv {self.player.level}  XP {self.player.xp}/{self.player.level * 30}", True, COLOR_TEXT
        )
        room_text = font.render(self.room.name, True, COLOR_TEXT)

        bar_x, bar_y, bar_w, bar_h = 10, 10, 140, 14
        pygame.draw.rect(self.screen, COLOR_HP_BG, (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * max(0, self.player.hp) / self.player.max_hp)
        pygame.draw.rect(self.screen, COLOR_HP, (bar_x, bar_y, fill_w, bar_h))

        self.screen.blit(hp_text, (bar_x + bar_w + 10, 6))
        self.screen.blit(lvl_text, (bar_x + bar_w + 10, 22))
        self.screen.blit(room_text, (WINDOW_W - room_text.get_width() - 10, 10))

    def _draw_message_log(self):
        font = AssetManager.get_font(14)
        y = ROOM_ORIGIN[1] + ROOM_PIXEL_H + 6
        for line in self.message_log[-2:]:
            text = font.render(line, True, COLOR_TEXT)
            self.screen.blit(text, (10, y))
            y += 18

    def _draw_debug_overlay(self, fps_target, is_focused, actual_fps):
        font = AssetManager.get_font(14)
        mode = "ACTIVE" if is_focused else "IDLE"
        lines = [
            f"FPS target: {fps_target}  actual: {actual_fps:.1f}",
            f"Mode: {mode}",
            f"Room: {self.current_room_id}  Pos: {self.player.x},{self.player.y}",
        ]
        panel = pygame.Surface((260, 18 * len(lines) + 8), pygame.SRCALPHA)
        panel.fill((0, 0, 0, 160))
        for i, line in enumerate(lines):
            panel.blit(font.render(line, True, COLOR_DEBUG), (6, 6 + i * 18))
        self.screen.blit(panel, (WINDOW_W - panel.get_width() - 8, 34))

    def _draw_inventory(self):
        overlay = pygame.Surface((WINDOW_W, WINDOW_H), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.screen.blit(overlay, (0, 0))

        panel_w, panel_h = 300, 220
        panel = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        panel.fill(COLOR_PANEL_BG)

        title_font = AssetManager.get_font(16, bold=True)
        font = AssetManager.get_font(14)

        panel.blit(title_font.render("Inventory", True, COLOR_TEXT), (10, 8))

        items = self.inventory.as_list()
        if not items:
            panel.blit(font.render("(empty)", True, COLOR_TEXT), (10, 36))
        for i, (item_type, count, item_def) in enumerate(items):
            prefix = "> " if i == self.inventory_cursor else "  "
            label = f"{prefix}{item_def.get('name', item_type)} x{count}"
            panel.blit(font.render(label, True, COLOR_TEXT), (10, 36 + i * 20))

        hint = font.render("Up/Down select, U use, I/Esc close", True, (160, 160, 160))
        panel.blit(hint, (10, panel_h - 24))

        self.screen.blit(panel, ((WINDOW_W - panel_w) // 2, (WINDOW_H - panel_h) // 2))


def main():
    pygame.init()
    try:
        pygame.mixer.init()
    except pygame.error:
        AssetManager.disable_audio()

    screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
    pygame.display.set_caption("Wayfarer")
    clock = pygame.time.Clock()

    game = Game(screen)

    running = True
    is_focused = True
    fps_target = ACTIVE_FPS
    debug_overlay = False

    print("Wayfarer running. Arrows/WASD move, I inventory, F3 debug, ESC quit.")

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.WINDOWFOCUSLOST:
                is_focused = False
                fps_target = IDLE_FPS
                game.dirty = True

            elif event.type == pygame.WINDOWFOCUSGAINED:
                is_focused = True
                fps_target = ACTIVE_FPS
                game.dirty = True

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if game.inventory_open:
                        game.toggle_inventory()
                    else:
                        running = False
                elif event.key == pygame.K_F3:
                    debug_overlay = not debug_overlay
                    game.dirty = True
                elif event.key == pygame.K_i:
                    game.toggle_inventory()
                elif game.inventory_open:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        game.inventory_move_cursor(-1)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        game.inventory_move_cursor(1)
                    elif event.key in (pygame.K_u, pygame.K_RETURN):
                        game.use_selected_item()
                else:
                    if event.key in (pygame.K_LEFT, pygame.K_a):
                        game.handle_move(-1, 0)
                    elif event.key in (pygame.K_RIGHT, pygame.K_d):
                        game.handle_move(1, 0)
                    elif event.key in (pygame.K_UP, pygame.K_w):
                        game.handle_move(0, -1)
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        game.handle_move(0, 1)

        # The debug overlay redraws continuously so its FPS reading is live;
        # otherwise we only ever redraw on an actual state change.
        if game.dirty or debug_overlay:
            game.draw(fps_target, is_focused, clock.get_fps(), debug_overlay)
            game.dirty = False

        clock.tick(fps_target)

    game.persist()
    game.save.close()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
