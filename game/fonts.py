"""
KeyFall - font cache.

pygame.font.SysFont() opens the font file again on every call (~0.3 ms), and many draw()
functions used to call it every frame. sys_font() returns one shared Font per
(name, size, bold, italic) instead.
"""

import pygame

_cache = {}


def sys_font(name, size, bold=False, italic=False):
    key = (name, int(size), bool(bold), bool(italic))
    font = _cache.get(key)
    if font is None:
        font = _cache[key] = pygame.font.SysFont(name, int(size), bold=bold, italic=italic)
    return font
