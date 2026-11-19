"""
KeyFall - shared UI kit.

Every screen draws with these helpers, so they all share one look: dark translucent rounded
panels with neon borders, Consolas text, a scanline backdrop and keycap hints.

Everything costly is cached (rendered text, panels, glows, the backdrop), so screens can call
the helpers every frame and the game stays at its 120 FPS cap.

Consolas has no glyph for many symbols (they render as empty boxes), so icons are drawn as
vectors and text only uses characters the font has, e.g. ► ◄ ▲ ▼ ● ○ ♪ ↑ ↓ ← → × · — …
"""

import colorsys
import math
import random

import pygame

from game.constants import (DARK_BG, LANE_COLORS, MODE_EASY, MODE_HARD, MODE_TESTING,
                            NEON_CYAN, NEON_GREEN, NEON_ORANGE, NEON_PINK, NEON_RED,
                            NEON_YELLOW)
from game.fonts import sys_font

# ── Colour tokens ─────────────────────────────────────────────────
TEXT       = (232, 232, 245)   # primary text
TEXT_MUTED = (150, 150, 182)   # labels and secondary text
TEXT_DIM   = (106, 106, 138)   # hints and captions (still readable on the dark background)
PANEL      = (12, 12, 28)      # panel fill, drawn translucent
EDGE       = (46, 46, 76)      # panel border
EDGE_HI    = (82, 82, 124)     # hovered border
KEYCAP     = (26, 26, 46)
TRACK      = (22, 22, 42)      # empty part of bars and sliders

MODES      = [MODE_HARD, MODE_EASY, MODE_TESTING]
MODE_COLOR = {MODE_HARD: NEON_RED, MODE_EASY: NEON_GREEN, MODE_TESTING: NEON_ORANGE}
MODE_NAME  = {MODE_HARD: "HARD", MODE_EASY: "EASY", MODE_TESTING: "AUTOPLAY"}
MODE_DESC  = {
    MODE_HARD:    "The song keeps going. Missed notes break your combo.",
    MODE_EASY:    "The song waits until you play the right notes.",
    MODE_TESTING: "Notes play by themselves. Watch and listen, not scored.",
}

JUDGE_COLOR = {"PERFECT": NEON_CYAN, "GREAT": NEON_GREEN, "GOOD": NEON_YELLOW,
               "MISS": NEON_RED}

GRADE_COLOR = {"GODLIKE": (255, 220, 0), "SS": NEON_CYAN, "S": (0, 200, 255),
               "A": NEON_GREEN, "B": NEON_YELLOW, "C": NEON_ORANGE, "F": NEON_RED}
GRADE_DESC  = {
    "GODLIKE": "Every note PERFECT",
    "SS": "No misses, only PERFECT and GREAT",
    "S":  "No missed notes",
    "A":  "Hit 90% or more of the notes",
    "B":  "Hit 78% or more of the notes",
    "C":  "Hit 62% or more of the notes",
    "F":  "Under 62% of the notes hit",
}

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']


def mode_color(mode): return MODE_COLOR.get(mode, TEXT_MUTED)
def mode_name(mode):  return MODE_NAME.get(mode, str(mode))
def note_name(p):     return f"{NOTE_NAMES[p % 12]}{p // 12 - 1}"


def fmt_time(sec):
    sec = max(0, int(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def scale_for(w, h):
    """UI scale factor: 1.0 at 1280x720, grows with the window, never below 0.6."""
    return max(0.6, min(w / 1280, h / 720))


def mix(a, b, t):
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t),
            int(a[2] + (b[2] - a[2]) * t))


def shade(c, f):
    return (min(255, int(c[0] * f)), min(255, int(c[1] * f)), min(255, int(c[2] * f)))


_pc_colors = {}

def pitch_color(p):
    """A bright neon colour per pitch class (C red ... B magenta), used by Free Play."""
    pc = p % 12
    c = _pc_colors.get(pc)
    if c is None:
        r, g, b = colorsys.hsv_to_rgb(((pc * 7) % 12) / 12.0, 0.78, 1.0)
        c = _pc_colors[pc] = (int(r * 255), int(g * 255), int(b * 255))
    return c


# ── Text ──────────────────────────────────────────────────────────
def font(px, bold=False):
    return sys_font("consolas", max(9, int(px)), bold=bold)


_text = {}

def text(s, px, color, bold=False):
    """Rendered text surface (cached; colors must be tuples)."""
    key = (s, int(px), color, bold)
    surf = _text.get(key)
    if surf is None:
        if len(_text) > 2500:
            _text.clear()
        surf = _text[key] = font(px, bold).render(s, True, color)
    return surf


def draw_text(surf, s, px, color, pos, bold=False, anchor="topleft", shadow=False):
    """Blit cached text with its rect's `anchor` at pos; returns that rect."""
    t = text(s, px, color, bold)
    r = t.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    if shadow:
        surf.blit(text(s, px, (0, 0, 0), bold), (r.x + 2, r.y + 2))
    surf.blit(t, r)
    return r


_fit = {}

def fit(s, px, max_w, bold=False):
    """s, shortened with … so it is at most max_w pixels wide."""
    key = (s, int(px), int(max_w), bold)
    r = _fit.get(key)
    if r is None:
        f = font(px, bold)
        r = s
        if f.size(s)[0] > max_w:
            while r and f.size(r + "…")[0] > max_w:
                r = r[:-1]
            r = r.rstrip() + "…"
        if len(_fit) > 1500:
            _fit.clear()
        _fit[key] = r
    return r


def text_w(s, px, bold=False):
    return font(px, bold).size(s)[0]


_wraps = {}

def wrap(s, px, max_w, bold=False, max_lines=2):
    """Word-wrap s into at most max_lines lines no wider than max_w (the last one gets …)."""
    key = (s, int(px), int(max_w), bold, max_lines)
    lines = _wraps.get(key)
    if lines is None:
        f = font(px, bold)
        lines, cur = [], ""
        for word in s.split():
            trial = f"{cur} {word}" if cur else word
            if cur and f.size(trial)[0] > max_w:
                lines.append(cur)
                cur = word
            else:
                cur = trial
        if cur:
            lines.append(cur)
        if len(lines) > max_lines:
            lines = lines[:max_lines - 1] + [" ".join(lines[max_lines - 1:])]
        lines = [fit(ln, px, max_w, bold) for ln in lines] or [""]
        if len(_wraps) > 500:
            _wraps.clear()
        _wraps[key] = lines
    return lines


# ── Panels, glow, bars ────────────────────────────────────────────
_panels = {}

def panel(surf, rect, fill=PANEL, alpha=215, border=EDGE, width=1, radius=10, top_hi=True):
    """Rounded translucent panel with a border (cached per size and style)."""
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return rect
    radius = min(radius, rect.h // 2, rect.w // 2)
    key = (rect.w, rect.h, fill, alpha, border, width, radius, top_hi)
    p = _panels.get(key)
    if p is None:
        if len(_panels) > 400:
            _panels.clear()
        p = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(p, (*fill, alpha), p.get_rect(), border_radius=radius)
        if top_hi and rect.w > radius * 2 + 4:     # faint light along the top edge
            pygame.draw.line(p, (255, 255, 255, 16), (radius, 1), (rect.w - radius - 1, 1))
        if border is not None and width:
            pygame.draw.rect(p, (*border, 255), p.get_rect(), width, border_radius=radius)
        _panels[key] = p
    surf.blit(p, rect)
    return rect


_glows = {}

def glow(surf, rect, color, radius=10, spread=10, strength=1.0):
    """Soft neon halo around rect; strength 0..1 (cheap to animate)."""
    rect = pygame.Rect(rect)
    spread = max(2, int(spread))
    key = (rect.w, rect.h, color, radius, spread)
    g = _glows.get(key)
    if g is None:
        if len(_glows) > 200:
            _glows.clear()
        g = pygame.Surface((rect.w + spread * 2, rect.h + spread * 2), pygame.SRCALPHA)
        for i in range(spread, 0, -1):
            a = int(80 * (1 - i / (spread + 1)) ** 2)
            pygame.draw.rect(g, (*color, a),
                             (spread - i, spread - i, rect.w + 2 * i, rect.h + 2 * i), 2,
                             border_radius=radius + i)
        _glows[key] = g
    g.set_alpha(int(255 * max(0.0, min(1.0, strength))))
    surf.blit(g, (rect.x - spread, rect.y - spread))


def bar(surf, rect, frac, color, bg=TRACK, border=None):
    """Rounded progress bar."""
    rect = pygame.Rect(rect)
    rad = rect.h // 2
    pygame.draw.rect(surf, bg, rect, border_radius=rad)
    w = int(rect.w * max(0.0, min(1.0, frac)))
    if w > 0:
        pygame.draw.rect(surf, color, (rect.x, rect.y, max(w, min(rect.w, rect.h)), rect.h),
                         border_radius=rad)
    if border:
        pygame.draw.rect(surf, border, rect, 1, border_radius=rad)


def rounded(img, radius):
    """Copy of img with rounded (transparent) corners."""
    w, h = img.get_size()
    out = pygame.Surface((w, h), pygame.SRCALPHA)
    out.blit(img, (0, 0))
    mask = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    out.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return out


def footer_rect(W, H, s):
    h = max(24, int(34 * s))
    return pygame.Rect(0, H - h, W, h)


def footer(surf, s, hint_items=None):
    """Bottom bar shared by the menus: keycap hints on the left. The app draws the version
    and FPS on its right end (see footer_rect)."""
    W, H = surf.get_size()
    r = footer_rect(W, H, s)
    panel(surf, r, fill=(7, 7, 18), alpha=230, border=None, radius=0, top_hi=False)
    pygame.draw.line(surf, EDGE, (0, r.y), (W, r.y))
    if hint_items:
        hints(surf, hint_items, (int(16 * s), r.centery), s, anchor="midleft")
    return r


def section(surf, label, x, y, w, s, color=NEON_CYAN, right=None):
    """Small section heading with a hairline to the right (and an optional right-aligned hint)."""
    px = max(9, int(13 * s))
    t = text(label, px, color, True)
    surf.blit(t, (x, y))
    end = x + w
    if right:
        rt = text(right, max(9, int(12 * s)), TEXT_DIM)
        surf.blit(rt, (x + w - rt.get_width(), y + (t.get_height() - rt.get_height()) // 2))
        end = x + w - rt.get_width() - int(10 * s)
    ly = y + t.get_height() // 2
    if end > x + t.get_width() + int(20 * s):
        pygame.draw.line(surf, EDGE, (x + t.get_width() + int(10 * s), ly), (end, ly), 1)
    return t.get_height()


# ── Buttons, pills, segments ──────────────────────────────────────
def button(surf, rect, label, s, color=NEON_CYAN, selected=False, hovered=False, t=0.0,
           px=None, enabled=True, icon=None, markers=False, idle_text=None):
    """Neon button. selected = keyboard focus (glows), hovered = mouse over.
    icon: optional function(surf, rect, color) drawing a vector icon left of the label.
    idle_text: label colour when neither selected nor hovered (default: muted grey)."""
    rect = pygame.Rect(rect)
    rad = max(4, int(8 * s))
    px = px or max(10, int(20 * s))
    if not enabled:
        panel(surf, rect, alpha=140, border=(34, 34, 54), radius=rad)
        tc = (78, 78, 104)
    elif selected:
        glow(surf, rect, color, rad, int(10 * s), 0.55 + 0.35 * math.sin(t * 3.2))
        panel(surf, rect, fill=shade(color, 0.17), alpha=240, border=color, width=2, radius=rad)
        tc = TEXT
    elif hovered:
        panel(surf, rect, fill=shade(color, 0.08), alpha=230, border=mix(color, EDGE, 0.45),
              radius=rad)
        tc = TEXT
    else:
        panel(surf, rect, alpha=205, border=EDGE, radius=rad)
        tc = idle_text or TEXT_MUTED
    lt = text(label, px, tc, True)
    isz = int(px * 0.9) if icon else 0
    gap = int(px * 0.5) if icon else 0
    x = rect.centerx - (isz + gap + lt.get_width()) // 2
    if icon:
        ir = pygame.Rect(x, rect.centery - isz // 2, isz, isz)
        icon(surf, ir, color if (selected or hovered) and enabled else tc)
    surf.blit(lt, (x + isz + gap, rect.centery - lt.get_height() // 2))
    if markers and selected and enabled:
        mt = text("►", px, color, True)
        surf.blit(mt, (rect.x + int(18 * s), rect.centery - mt.get_height() // 2))
        mt = text("◄", px, color, True)
        surf.blit(mt, (rect.right - int(18 * s) - mt.get_width(), rect.centery - mt.get_height() // 2))
    return rect


def pill(surf, label, color, pos, s, px=None, anchor="topleft", filled=False, dot=False):
    """Rounded badge. Returns its rect."""
    px = px or max(9, int(13 * s))
    t = text(label, px, (8, 8, 16) if filled else color, True)
    padx = max(5, int(9 * s))
    h = t.get_height() + max(3, int(5 * s))
    dw = max(8, int(12 * s)) if dot else 0
    r = pygame.Rect(0, 0, t.get_width() + padx * 2 + dw, h)
    setattr(r, anchor, (int(pos[0]), int(pos[1])))
    if filled:
        panel(surf, r, fill=color, alpha=255, border=color, radius=h // 2, top_hi=False)
    else:
        panel(surf, r, fill=shade(color, 0.16), alpha=235, border=shade(color, 0.8),
              radius=h // 2, top_hi=False)
    x = r.x + padx
    if dot:
        pygame.draw.circle(surf, color, (x + dw // 2 - 1, r.centery), max(2, int(4 * s)))
        x += dw
    surf.blit(t, (x, r.centery - t.get_height() // 2))
    return r


def pill_w(label, s, px=None, dot=False):
    """Width pill() will use, for centring rows of pills before drawing them."""
    px = px or max(9, int(13 * s))
    return text_w(label, px, True) + max(5, int(9 * s)) * 2 + (max(8, int(12 * s)) if dot else 0)


def pill_row(surf, items, center, s, px=None, gap=None):
    """Centred row of pills: items = [(label, color, filled)]. Returns the row's rect."""
    gap = int(8 * s) if gap is None else gap
    widths = [pill_w(lab, s, px) for lab, _, _ in items]
    x = int(center[0] - (sum(widths) + gap * (len(items) - 1)) / 2)
    row = None
    for (lab, col, filled), w in zip(items, widths):
        r = pill(surf, lab, col, (x, center[1]), s, px=px, anchor="midleft", filled=filled)
        row = r if row is None else row.union(r)
        x += w + gap
    return row


def split_row(rect, n, gap):
    """n equal rects side by side inside rect."""
    rect = pygame.Rect(rect)
    w = (rect.w - gap * (n - 1)) / n
    return [pygame.Rect(int(rect.x + i * (w + gap)), rect.y,
                        int(rect.x + i * (w + gap) + w) - int(rect.x + i * (w + gap)), rect.h)
            for i in range(n)]


def segment(surf, rect, label, color, s, selected=False, hovered=False, enabled=True,
            px=None, idle_text=None):
    """One cell of a segmented control (difficulty, mode, speed)."""
    rect = pygame.Rect(rect)
    rad = max(4, int(7 * s))
    px = px or max(9, int(14 * s))
    if not enabled:
        panel(surf, rect, alpha=110, border=(34, 34, 54), radius=rad, top_hi=False)
        tc = (70, 70, 96)
    elif selected:
        panel(surf, rect, fill=shade(color, 0.24), alpha=245, border=color, width=2, radius=rad)
        tc = TEXT
    elif hovered:
        panel(surf, rect, fill=shade(color, 0.1), alpha=230, border=mix(color, EDGE, 0.4),
              radius=rad)
        tc = TEXT
    else:
        panel(surf, rect, alpha=200, border=EDGE, radius=rad)
        tc = idle_text or shade(color, 0.85)
    draw_text(surf, fit(label, px, rect.w - 6, True), px, tc, rect.center, bold=True,
              anchor="center")
    if not enabled:   # strike through: clearly "not available"
        y = rect.centery
        pygame.draw.line(surf, (54, 54, 78), (rect.x + int(8 * s), y), (rect.right - int(8 * s), y), 1)


# ── Keycap hints ──────────────────────────────────────────────────
# The hints are buttons too: every keycap drawn this frame is remembered with its key, and the
# app turns a click on one into that key press (key_event), so each screen can be used with
# the mouse alone. A hint item is (caps, label) or (caps, label, keys): keys gives the key of
# each cap, or None for a cap that only explains something (e.g. "CLICK", the letter keys).
CAP_KEYS = {
    "ESC": pygame.K_ESCAPE, "ENTER": pygame.K_RETURN, "SPACE": pygame.K_SPACE,
    "TAB": pygame.K_TAB, "↑": pygame.K_UP, "↓": pygame.K_DOWN, "←": pygame.K_LEFT,
    "→": pygame.K_RIGHT, "[": pygame.K_LEFTBRACKET, "]": pygame.K_RIGHTBRACKET,
    "-": pygame.K_MINUS, "+": pygame.K_PLUS, "PGUP": pygame.K_PAGEUP,
    "PGDN": pygame.K_PAGEDOWN, "HOME": pygame.K_HOME, "END": pygame.K_END,
}
CAP_KEYS.update({f"F{i}": getattr(pygame, f"K_F{i}") for i in range(1, 13)})
CAP_KEYS.update({c: getattr(pygame, f"K_{c.lower()}") for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})

_hint_cache = {}
_hint_hits = []          # (rect, key) of the clickable keycaps drawn this frame
_hint_mouse = None       # pointer position for the hover highlight (set by begin_frame)


def begin_frame(mouse_pos=None):
    """The app calls this before drawing a frame: forget the last frame's keycaps."""
    global _hint_mouse
    _hint_hits.clear()
    _hint_mouse = mouse_pos


def hint_key_at(pos):
    """Key of the keycap hint at pos in the last frame drawn, or None."""
    for r, key in reversed(_hint_hits):
        if r.collidepoint(pos):
            return key
    return None


def key_event(key):
    """The KEYDOWN a click on a keycap hint stands for (event.clicked is True)."""
    return pygame.event.Event(pygame.KEYDOWN, key=key, mod=0, unicode="", scancode=0,
                              clicked=True)


def _norm_hints(items):
    out = []
    for item in items:
        caps, lab = item[0], item[1]
        caps = (caps,) if isinstance(caps, str) else tuple(caps)
        if len(item) > 2:
            keys = item[2]
            keys = (tuple(keys) if isinstance(keys, (tuple, list))
                    else (keys,) * len(caps))
        else:
            keys = tuple(CAP_KEYS.get(c) for c in caps)
        out.append((caps, lab, keys))
    return tuple(out)


def _hint_layout(items, s, label_color=TEXT_MUTED):
    """(surface, zones) for a row of keycap hints. zones = [(rect, key, cap rects)]: an item
    with one key is clickable as a whole, an item with several (↑ ↓) per keycap."""
    norm = _norm_hints(items)
    ck = (norm, round(s, 3), label_color)
    hit = _hint_cache.get(ck)
    if hit is not None:
        return hit
    fcap, flab = font(max(9, int(12 * s)), True), font(max(9, int(13 * s)))
    cap_h = max(16, int(22 * s))
    pad = max(4, int(6 * s))
    gk, gl, gi = max(2, int(4 * s)), max(4, int(7 * s)), max(10, int(20 * s))
    rad = max(3, int(5 * s))

    def cap_w(c): return max(cap_h, fcap.size(c)[0] + pad * 2)
    width = 0
    for n, (caps, lab, _) in enumerate(norm):
        width += (gi if n else 0) + sum(cap_w(c) for c in caps) + gk * (len(caps) - 1)
        if lab:
            width += gl + flab.size(lab)[0]
    surf = pygame.Surface((max(1, width), cap_h), pygame.SRCALPHA)
    zones = []
    x = 0
    for n, (caps, lab, keys) in enumerate(norm):
        x += gi if n else 0
        x0, rects = x, []
        for j, c in enumerate(caps):
            x += gk if j else 0
            r = pygame.Rect(x, 0, cap_w(c), cap_h)
            pygame.draw.rect(surf, (*KEYCAP, 255), r, border_radius=rad)
            pygame.draw.rect(surf, (88, 88, 126, 255), r, 1, border_radius=rad)
            ct = fcap.render(c, True, TEXT)
            surf.blit(ct, ct.get_rect(center=r.center))
            rects.append(r)
            x += r.w
        if lab:
            x += gl
            lt = flab.render(lab, True, label_color)
            surf.blit(lt, (x, (cap_h - lt.get_height()) // 2))
            x += lt.get_width()
        live = [(r, k) for r, k in zip(rects, keys) if k is not None]
        if len(set(k for _, k in live)) == 1 and len(live) == len(rects):
            zones.append((pygame.Rect(x0, 0, x - x0, cap_h), live[0][1], rects))
        else:
            zones.extend((r, k, [r]) for r, k in live)
    if len(_hint_cache) > 64:
        _hint_cache.clear()
    _hint_cache[ck] = (surf, zones)
    return surf, zones


def hints_surface(items, s, label_color=TEXT_MUTED):
    """A row of keycap hints, e.g. [(("↑", "↓"), "Navigate"), ("ENTER", "Select")]."""
    return _hint_layout(items, s, label_color)[0]


def hints(surf, items, pos, s, anchor="midbottom", label_color=TEXT_MUTED, interactive=True,
          alpha=255):
    """Draw a row of keycap hints. interactive: clicking a keycap presses its key, and the
    one under the pointer lights up (False for rows that only list keys)."""
    h, zones = _hint_layout(items, s, label_color)
    r = h.get_rect(**{anchor: (int(pos[0]), int(pos[1]))})
    hover = None
    if interactive and alpha >= 160:
        mx, my = max(2, int(5 * s)), max(3, int(6 * s))
        for zr, key, caps in zones:
            area = zr.move(r.topleft).inflate(mx * 2, my * 2)
            _hint_hits.append((area, key))
            if _hint_mouse is not None and area.collidepoint(_hint_mouse):
                hover = (area, caps)
    if hover:   # lit like a hovered button: a tinted plate behind, neon keycap borders
        panel(surf, hover[0], fill=shade(NEON_CYAN, 0.14), alpha=235,
              border=mix(NEON_CYAN, EDGE, 0.35), radius=max(4, int(7 * s)), top_hi=False)
    if alpha < 255:
        h.set_alpha(alpha)
        surf.blit(h, r)
        h.set_alpha(255)
    else:
        surf.blit(h, r)
    if hover:
        for cr in hover[1]:
            pygame.draw.rect(surf, NEON_CYAN, cr.move(r.topleft), 1,
                             border_radius=max(3, int(5 * s)))
    return r


# ── Background ────────────────────────────────────────────────────
class _Backdrop:
    """Dark gradient (a little brighter at the top centre) with scanlines, drawn once per size."""
    def __init__(self):
        self.size = None
        self.surf = None

    def get(self, W, H):
        if self.size != (W, H):
            gw, gh = 32, 18
            g = pygame.Surface((gw, gh))
            for yy in range(gh):
                for xx in range(gw):
                    u = (xx + 0.5) / gw - 0.5
                    v = (yy + 0.5) / gh
                    k = max(0.0, 1.0 - math.hypot(u * 1.5, v) * 1.2) ** 2      # top-centre glow
                    e = min(1.0, math.hypot(u * 2, (v - 0.5) * 2) / 1.42)    # edge darkening
                    f = 1.0 - 0.45 * e * e
                    g.set_at((xx, yy), (int((DARK_BG[0] + 7 * k) * f),
                                        int((DARK_BG[1] + 11 * k) * f),
                                        int((DARK_BG[2] + 26 * k) * f)))
            surf = pygame.transform.smoothscale(g, (W, H))
            for y in range(0, H, 4):
                pygame.draw.line(surf, (0, 0, 0), (0, y), (W, y))
            try:
                surf = surf.convert()
            except pygame.error:
                pass
            self.surf, self.size = surf, (W, H)
        return self.surf


_backdrop = _Backdrop()


def backdrop(surf, t, lines=True):
    """The shared menu background: gradient + scanlines + slowly drifting grid lines."""
    W, H = surf.get_size()
    surf.blit(_backdrop.get(W, H), (0, 0))
    if lines:
        n = 12
        for i in range(n):
            off = int((t * 28 + i * H / n) % H)
            a = int(18 + 8 * math.sin(t + i))
            pygame.draw.line(surf, (0, a, a // 2), (0, off), (W, off), 1)


class FallingNotes:
    """Dim neon notes drifting down behind a menu: the game's motif, kept subtle."""
    def __init__(self, count=18, seed=11):
        rng = random.Random(seed)
        lanes = list(range(28))
        rng.shuffle(lanes)
        self.notes = [(lanes[i % 28], rng.random(), rng.uniform(0.03, 0.07),
                       rng.uniform(0.05, 0.15), LANE_COLORS[i % len(LANE_COLORS)])
                      for i in range(count)]

    def draw(self, surf, t, s=1.0, dim=0.2):
        W, H = surf.get_size()
        lw = W / 28
        w = max(4, int(lw * 0.62))
        rad = max(2, int(4 * s))
        for lane, y0, spd, ln, col in self.notes:
            h = int(ln * H)
            y = int(((y0 + t * spd) % 1.0) * (H + h)) - h
            x = int(lane * lw + (lw - w) / 2)
            pygame.draw.rect(surf, shade(col, dim), (x, y, w, h), border_radius=rad)
            pygame.draw.line(surf, shade(col, dim * 2.3), (x + 1, y + h - 2), (x + w - 2, y + h - 2), 2)


# ── Title ─────────────────────────────────────────────────────────
_logo_glow = {}

def logo(surf, cx, y, px, t):
    """The KEYFALL title: cyan letters with a slow colour wave over a soft neon glow.
    Returns its height."""
    f = font(px, True)
    letters = "KEYFALL"
    gap = max(2, int(px * 0.05))
    widths = [f.size(ch)[0] for ch in letters]
    total = sum(widths) + gap * (len(letters) - 1)
    x0 = int(cx - total / 2)
    g = _logo_glow.get(px)
    if g is None:
        pad = px // 2
        word = pygame.Surface((total + pad * 2, f.get_height() + pad * 2))
        x = pad
        for ch, w in zip(letters, widths):
            word.blit(f.render(ch, True, (0, 120, 150)), (x, pad))
            x += w + gap
        small = pygame.transform.smoothscale(
            word, (max(1, word.get_width() // 10), max(1, word.get_height() // 10)))
        g = _logo_glow[px] = pygame.transform.smoothscale(small, word.get_size())
    surf.blit(g, (x0 - px // 2, y - px // 2), special_flags=pygame.BLEND_RGB_ADD)
    x = x0
    for i, (ch, w) in enumerate(zip(letters, widths)):
        ph = t * 2.2 + i * 0.45
        col = (0, int(200 + 55 * math.sin(ph)) & ~7, int(220 + 35 * math.sin(ph + 1.2)) & ~7)
        surf.blit(text(ch, px, (0, 30, 40), True), (x + 3, y + 3))
        surf.blit(text(ch, px, col, True), (x, y))
        x += w + gap
    return f.get_height()


# ── Vector icons (Consolas has no glyphs for these) ───────────────
def icon_folder(surf, rect, color, w=2):
    r = pygame.Rect(rect)
    def P(fx, fy): return (r.x + int(r.w * fx), r.y + int(r.h * fy))
    pygame.draw.lines(surf, color, True,
                      [P(0, .12), P(.4, .12), P(.52, .3), P(1, .3), P(1, .95), P(0, .95)], w)
    pygame.draw.line(surf, color, P(0, .46), P(1, .46), 1)


def icon_refresh(surf, rect, color, w=2):
    r = pygame.Rect(rect)
    rad = max(3, min(r.w, r.h) // 2 - 1)
    box = pygame.Rect(0, 0, rad * 2, rad * 2)
    box.center = r.center
    a0 = math.radians(65)
    pygame.draw.arc(surf, color, box, a0, math.radians(345), w)
    # arrowhead at the arc's upper-right end, pointing clockwise into the gap
    px, py = r.centerx + rad * math.cos(a0), r.centery - rad * math.sin(a0)
    dx, dy = math.sin(a0), math.cos(a0)
    nx, ny = math.cos(a0), -math.sin(a0)
    a = max(3.0, rad * 0.6)
    pygame.draw.polygon(surf, color, [(px + dx * a, py + dy * a),
                                      (px + nx * a * 0.75, py + ny * a * 0.75),
                                      (px - nx * a * 0.75, py - ny * a * 0.75)])


def icon_play(surf, rect, color):
    r = pygame.Rect(rect)
    pygame.draw.polygon(surf, color, [(r.x + int(r.w * .18), r.y), (r.x + int(r.w * .18), r.bottom),
                                      (r.right, r.centery)])


def icon_note(surf, rect, color):
    """Eighth note: head, stem and flag."""
    r = pygame.Rect(rect)
    hw, hh = max(4, int(r.w * .5)), max(3, int(r.h * .36))
    head = pygame.Rect(r.x, r.bottom - hh, hw, hh)
    pygame.draw.ellipse(surf, color, head)
    sx = head.right - 1
    pygame.draw.line(surf, color, (sx, head.centery), (sx, r.y), max(1, r.w // 9))
    pygame.draw.line(surf, color, (sx, r.y), (r.right, r.y + int(r.h * .32)), max(1, r.w // 9))


def icon_check(surf, rect, color, w=2):
    r = pygame.Rect(rect)
    pygame.draw.lines(surf, color, False, [(r.x, r.y + int(r.h * .55)),
                                           (r.x + int(r.w * .38), r.bottom - 1), (r.right, r.y)], w)


def spinner(surf, center, radius, color, t, w=2):
    box = pygame.Rect(0, 0, radius * 2, radius * 2)
    box.center = (int(center[0]), int(center[1]))
    pygame.draw.circle(surf, shade(color, 0.3), box.center, radius, 1)
    a = -t * 6.0
    pygame.draw.arc(surf, color, box, a, a + 1.9, w)


def ring(surf, center, radius, width, frac, color, bg=TRACK):
    """Progress ring: a full track circle plus an arc covering frac (0..1), clockwise from
    12 o'clock."""
    cx, cy = int(center[0]), int(center[1])
    pygame.draw.circle(surf, bg, (cx, cy), radius, width)
    frac = max(0.0, min(0.999, frac))
    if frac <= 0.0:
        return
    n = max(2, int(72 * frac))
    ri = radius - width
    outer, inner = [], []
    for i in range(n + 1):
        a = -math.pi / 2 + 2 * math.pi * frac * i / n
        ca, sa = math.cos(a), math.sin(a)
        outer.append((cx + radius * ca, cy + radius * sa))
        inner.append((cx + ri * ca, cy + ri * sa))
    pygame.draw.polygon(surf, color, outer + inner[::-1])


def status_dot(surf, center, color, s, ring=False):
    r = max(3, int(4 * s))
    pygame.draw.circle(surf, color, (int(center[0]), int(center[1])), r)
    if ring:
        pygame.draw.circle(surf, shade(color, 0.5), (int(center[0]), int(center[1])), r + 3, 1)


# ── Cursor ────────────────────────────────────────────────────────
_halos = {}

def cursor(surf, pos, t, s=1.0, color=NEON_CYAN):
    """The game's mouse cursor: pulsing neon ring, centre dot, soft halo."""
    x, y = int(pos[0]), int(pos[1])
    R = max(12, int(20 * s))
    halo = _halos.get((R, color))
    if halo is None:
        halo = pygame.Surface((R * 2, R * 2), pygame.SRCALPHA)
        for i in range(R, 0, -1):
            pygame.draw.circle(halo, (*color, int(34 * (1 - i / R) ** 1.6)), (R, R), i)
        _halos[(R, color)] = halo
    surf.blit(halo, (x - R, y - R))
    r = max(6, int((9 + 3 * abs(math.sin(t * 3.5))) * s))
    pygame.draw.circle(surf, color, (x, y), r, 2)
    pygame.draw.circle(surf, color, (x, y), max(2, int(2 * s)))


# ── Status helpers shared by the menus ────────────────────────────
def sound_summary(audio):
    """(text, colour, busy) describing what plays the notes right now."""
    if audio is None:
        return "", TEXT_DIM, False
    if getattr(audio, "_loading", False):
        return "Loading sound…", NEON_CYAN, True
    backend = getattr(audio, "backend", "synth")
    if backend == "midi_out":
        return f"MIDI out: {getattr(audio, 'midi_out_name', None) or 'device'}", NEON_PINK, False
    if backend in ("fluidsynth", "sampler"):
        return f"Sound: {soundfont_name(audio)}", NEON_GREEN, False
    return "Sound: built-in synth", NEON_YELLOW, False


def soundfont_name(audio):
    """'piano', 'Cambridge Concert Flute', ... from the loaded soundfont's file name."""
    try:
        st = audio.soundfont_status()
        if st.startswith("Ready (") and st.endswith(")"):
            base = st[7:-1].split(",")[0]
            return pretty_file(base)
    except Exception:
        pass
    return "soundfont"


def pretty_file(name):
    """'Cambridge_Concert_Flute.SF2' -> 'Cambridge Concert Flute'."""
    base = name.rsplit("/", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    return base.replace("_", " ").strip() or name
