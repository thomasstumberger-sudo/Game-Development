"""Asset cache. Everything is loaded once (at startup or on first use) and
reused for the lifetime of the process -- nothing in here should be called
from inside the per-frame render path."""

import os
import pygame

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class AssetManager:
    _sprites = {}
    _sfx = {}
    _fonts = {}
    _sfx_enabled = True

    @classmethod
    def load_sprite(cls, name, relative_path):
        if name not in cls._sprites:
            full_path = os.path.join(BASE_DIR, relative_path)
            if os.path.exists(full_path):
                cls._sprites[name] = pygame.image.load(full_path).convert_alpha()
            else:
                print(f"[ASSET WARNING] Missing sprite file: '{full_path}'. Using fallback.")
                fallback = pygame.Surface((16, 16), pygame.SRCALPHA)
                fallback.fill((255, 0, 255, 255))
                cls._sprites[name] = fallback
        return cls._sprites[name]

    @classmethod
    def make_placeholder(cls, name, color, size=16, shape="circle", outline=(20, 20, 20)):
        """Procedurally draw a simple placeholder sprite once and cache it.
        Used for entities (e.g. the player) that have no matching tile in
        the source tilesets -- drawn a single time, never per-frame."""
        if name not in cls._sprites:
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pad = max(1, size // 8)
            outline_w = max(1, size // 32)
            if shape == "circle":
                pygame.draw.circle(surf, color, (size // 2, size // 2), size // 2 - pad)
                pygame.draw.circle(surf, outline, (size // 2, size // 2), size // 2 - pad, outline_w)
                # facing notch so the player has a sense of "front"
                pygame.draw.circle(surf, outline, (size // 2, pad + 1), max(1, size // 8))
            else:
                rect = pygame.Rect(pad, pad, size - pad * 2, size - pad * 2)
                pygame.draw.rect(surf, color, rect, border_radius=max(1, size // 10))
                pygame.draw.rect(surf, outline, rect, outline_w, border_radius=max(1, size // 10))
            cls._sprites[name] = surf
        return cls._sprites[name]

    @classmethod
    def make_tint_variant(cls, variant_name, base_name, tint_color, strength=0.6):
        """Copy an already-loaded sprite and multiply a color wash over it
        -- used to give a single source image (e.g. one staircase graphic)
        a second, visually distinct meaning (stairs up vs. stairs down)
        without needing two matching pieces of art. BLEND_RGB_MULT leaves
        the destination's own alpha channel alone (transparent stays
        transparent, opaque stays opaque) and only multiplies color, so the
        sprite's silhouette is preserved -- only its shading shifts.
        `strength` blends the wash color toward white so it reads as a
        tint rather than a hard recolor."""
        if variant_name not in cls._sprites:
            base = cls.get_sprite(base_name)
            surf = base.copy()
            wash_color = tuple(int(255 - (255 - c) * strength) for c in tint_color)
            wash = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            wash.fill((*wash_color, 255))
            surf.blit(wash, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            cls._sprites[variant_name] = surf
        return cls._sprites[variant_name]

    @classmethod
    def get_sprite(cls, name):
        return cls._sprites.get(name)

    @classmethod
    def load_sfx(cls, name, relative_path):
        if not cls._sfx_enabled or name in cls._sfx:
            return cls._sfx.get(name)
        full_path = os.path.join(BASE_DIR, relative_path)
        if not os.path.exists(full_path):
            print(f"[ASSET WARNING] Missing sfx file: '{full_path}'. Skipping.")
            return None
        try:
            cls._sfx[name] = pygame.mixer.Sound(full_path)
        except pygame.error as exc:
            print(f"[ASSET WARNING] Could not load sfx '{full_path}': {exc}")
            cls._sfx[name] = None
        return cls._sfx[name]

    @classmethod
    def play_sfx(cls, name):
        sound = cls._sfx.get(name)
        if sound is not None:
            sound.play()

    @classmethod
    def get_font(cls, size, bold=False):
        key = (size, bold)
        if key not in cls._fonts:
            font = pygame.font.SysFont("monospace", size, bold=bold)
            cls._fonts[key] = font
        return cls._fonts[key]

    @classmethod
    def disable_audio(cls):
        cls._sfx_enabled = False
