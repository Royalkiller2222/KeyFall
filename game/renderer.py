"""
KeyFall - Renderer v8
Highway lanes aligned to piano key widths.
Black key lanes narrower + darker. White key lanes wider + brighter.

Performance notes: the background + highway never change during a song, so they are drawn
once into a cached surface; notes are found with a binary search instead of scanning the
whole song; text labels and key shading are cached; particles are capped.
"""

import bisect, math, random
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import pygame
from game import ui
from game.fonts import sys_font
from typing import List, Tuple, Dict
from game.constants import *
from game.midi_handler import MidiNote, SongData

NOTE_NAMES      = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
BLACK_SEMITONES = {1, 3, 6, 8, 10}
MAX_PARTICLES   = 600          # dense songs used to spawn thousands (24 per PERFECT)
_rng = random.Random()

def pitch_name(p):   return NOTE_NAMES[p % 12]
def is_black(p):     return (p % 12) in BLACK_SEMITONES
def lerp(a,b,t):     return a + (b-a)*t
def lerpC(a,b,t):    return tuple(int(lerp(a[i],b[i],t)) for i in range(3))
def clamp(v,lo,hi):  return max(lo, min(hi, v))


# ── Build full chromatic range C-to-B ────────────────────────────
def build_keyboard_range(pitches: List[int]) -> List[int]:
    lo = min(pitches); hi = max(pitches)
    return list(range(lo - lo%12, hi + (11 - hi%12) + 1))


# ─────────────────────────────────────────────────────────────────
# Key layout engine — two separate coordinate systems:
#
#  KEYBOARD: standard piano proportions.
#    White keys: equal width. Black keys: 60% width, overlapping whites.
#
#  HIGHWAY: "piano roll" style — no gaps.
#    Each white key lane extends from the center of its left-neighbour
#    black key to the center of its right-neighbour black key.
#    Black key lanes sit exactly where the black key is.
#    This means white lanes fill ALL the empty space; nothing is blank.
# ─────────────────────────────────────────────────────────────────
BLACK_KB_FRAC = 0.60   # black key width as fraction of white key width

def compute_key_layout(all_pitches: List[int], x_left: int, total_w: int):
    """
    Returns two dicts:
      kb_layout[pitch]  = (lx, rx, cx)  — keyboard key bounds
      hwy_layout[pitch] = (lx, rx, cx)  — highway lane bounds (no gaps)
    """
    whites = [p for p in all_pitches if not is_black(p)]
    n_white = len(whites)
    if n_white == 0:
        d = {p: (x_left, x_left+total_w, x_left+total_w//2) for p in all_pitches}
        return d, d

    ww = total_w / n_white          # white key width
    bw = ww * BLACK_KB_FRAC         # black key width

    # ── Keyboard layout ─────────────────────────────────────────
    # White keys: evenly spaced
    # Black keys: centered over the boundary between their two white neighbours
    kb = {}
    for i, p in enumerate(whites):
        kx = x_left + i * ww
        kb[p] = (int(kx), int(kx + ww) - 1, int(kx + ww/2))

    for p in all_pitches:
        if not is_black(p):
            continue
        left_w  = p - 1   # white key immediately left  (always exists on piano)
        right_w = p + 1   # white key immediately right
        if left_w in kb:
            cx = kb[left_w][0] + ww   # right edge of left white key = boundary
        elif right_w in kb:
            cx = kb[right_w][0]
        else:
            cx = x_left + total_w / 2
        lx = int(cx - bw / 2)
        rx = int(cx + bw / 2)
        lx = max(x_left, min(x_left + total_w - int(bw), lx))
        kb[p] = (lx, rx, int(cx))

    # ── Highway layout ───────────────────────────────────────────
    # Gapless piano-roll: white lanes extend to the centres of the neighbouring
    # black keys, black lanes sit exactly where the black key is.
    hwy = {}

    # First pass: black keys copy directly from kb
    for p in all_pitches:
        if is_black(p):
            hwy[p] = kb[p]

    # Build ordered list for neighbour scanning
    ordered = all_pitches  # already sorted lowest→highest

    # Second pass: white keys fill the gap
    for idx, p in enumerate(ordered):
        if is_black(p):
            continue
        kb_lx, kb_rx, kb_cx = kb[p]

        # Find nearest black key to the LEFT in all_pitches
        left_blk_cx = float(x_left)
        for q in reversed(ordered[:idx]):
            if is_black(q):
                left_blk_cx = hwy[q][2]
                break

        # Find nearest black key to the RIGHT in all_pitches
        right_blk_cx = float(x_left + total_w)
        for q in ordered[idx+1:]:
            if is_black(q):
                right_blk_cx = hwy[q][2]
                break

        # Lane spans from midpoint-with-left-black to midpoint-with-right-black
        # but clamp to the actual keyboard left/right edges of this slot
        lane_lx = int((left_blk_cx + kb_lx) / 2) if left_blk_cx != float(x_left) else kb_lx
        lane_rx = int((right_blk_cx + kb_rx) / 2) if right_blk_cx != float(x_left+total_w) else kb_rx
        hwy[p] = (lane_lx, lane_rx, (lane_lx + lane_rx) // 2)

    return kb, hwy


def build_piano_key_rects(kb_layout: Dict[int, tuple],
                          all_pitches: List[int],
                          y_top: int, height: int):
    """
    Returns [(rect, is_blk, pitch), ...] — whites first, blacks on top.
    Uses keyboard layout (not highway) for visual piano appearance.
    """
    whites, blacks = [], []
    bh = int(height * 0.62)
    for p in all_pitches:
        lx, rx, cx = kb_layout[p]
        w = max(2, rx - lx)
        if is_black(p):
            blacks.append((pygame.Rect(lx, y_top, w, bh), True, p))
        else:
            whites.append((pygame.Rect(lx, y_top, w, height), False, p))
    return whites + blacks


# ── Particle ──────────────────────────────────────────────────────
class Particle:
    __slots__ = ('x','y','vx','vy','color','life','max_life','size')
    def __init__(self, x, y, color, vx, vy, life=0.7, size=4):
        self.x=float(x); self.y=float(y)
        self.vx=float(vx); self.vy=float(vy)
        self.color=color; self.life=self.max_life=life; self.size=size
    def update(self, dt):
        self.x+=self.vx*dt; self.y+=self.vy*dt
        self.vy+=280*dt;    self.life-=dt
    @property
    def alive(self): return self.life > 0
    def draw(self, surf):
        a=clamp(self.life/self.max_life,0,1); sz=int(self.size*a)
        if sz<1: return
        pygame.draw.circle(surf,tuple(int(v*a) for v in self.color),(int(self.x),int(self.y)),sz)


# ── Renderer ──────────────────────────────────────────────────────
class HighwayRenderer:
    PIANO_H    = 95   # at 720p; both grow with the window (see _init_geometry)
    HIT_ZONE_H = 28   # larger gap = highway appears higher up

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self._init_geometry()
        self.particles: List[Particle] = []
        self.hit_flashes: Dict[int, tuple] = {}
        self.miss_flashes: Dict[int, float] = {}
        self._glow_tick: float = 0.0
        # HUD state: what it saw last frame, to start the judgment / combo animations
        self._nums: Dict[str, tuple] = {}     # slot -> (key, surface) for fast-changing numbers
        self._judge_cache: Dict[tuple, tuple] = {}
        self._hud_judged = 0
        self._hud_combo = 0
        self._hud_misses = 0
        self._judge = ("", 0.0)               # (quality, age) of the judgment pop
        self._combo_pop = 9.0                 # seconds since the combo last grew
        self._combo_break = 9.0               # seconds since the combo last broke
        self._init_fonts()
        self._bg = self._build_bg()
        # layout cache — rebuilt when lane_pitch_map changes
        self._layout_pitches: List[int] = []
        self._kb_layout: Dict[int, tuple] = {}    # keyboard key positions
        self._hwy_layout: Dict[int, tuple] = {}   # highway lane positions (gap-free)
        self._kb_keys: list = []
        self._all_pitches: List[int] = []
        # draw caches
        self._static = None          # background + highway, drawn once per layout
        self._static_key = None
        self._edges: Dict[int, tuple] = {}       # pitch -> note edge lines (x at depth 0 and 1)
        self._labels: Dict[tuple, pygame.Surface] = {}
        self._shadows: Dict[tuple, pygame.Surface] = {}
        self._note_index = (None, [], 0.0)       # (song, start times, longest note)
        self.hud_left_bottom = 0                  # bottom of the HUD's score column (draw_hud)

    def _init_geometry(self):
        self.W = self.screen.get_width()
        self.H = self.screen.get_height()
        k = self.H / 720
        self.PIANO_H    = max(70, int(HighwayRenderer.PIANO_H * k))
        self.HIT_ZONE_H = max(20, int(HighwayRenderer.HIT_ZONE_H * k))
        self.PIANO_Y = self.H - self.PIANO_H
        self.HIT_Y   = self.PIANO_Y - self.HIT_ZONE_H
        self.HWY_BOT = self.HIT_Y
        self.HWY_TOP = int(self.H * 0.13)
        # Highway x bounds — same as keyboard bounds
        self.HWY_X0  = int(self.W * 0.05)
        self.HWY_X1  = int(self.W * 0.95)
        self.HWY_W   = self.HWY_X1 - self.HWY_X0
        # Vanish point
        self.VAN_X0  = self.W // 2 - int(self.HWY_W * 0.06)
        self.VAN_X1  = self.W // 2 + int(self.HWY_W * 0.06)

    def _init_fonts(self):
        s = self.H / 720
        self.fn_note    = sys_font("consolas", max(8, int(12*s)), bold=True)
        self.fn_key_lbl = sys_font("consolas", max(7, int(10*s)), bold=True)

    def _build_bg(self):
        surf = pygame.Surface((self.W, self.H))
        surf.fill((4,4,12))
        rng = random.Random(77)
        for _ in range(260):
            x=rng.randint(0,self.W); y=rng.randint(0,self.HWY_TOP+30); b=rng.randint(40,150)
            pygame.draw.circle(surf,(b//3,b//3,b),(x,y),1)
        return surf

    def on_resize(self, w, h):
        self.screen = pygame.display.get_surface()
        self.W, self.H = w, h
        self._init_geometry(); self._init_fonts()
        self._bg = self._build_bg()
        self._layout_pitches = []   # force rebuild
        self._static_key = None
        self._labels.clear(); self._shadows.clear()
        self._nums.clear(); self._judge_cache.clear()

    # ── Layout management ─────────────────────────────────────────
    def _ensure_layout(self, lane_pitch_map: List[int]):
        if self._layout_pitches != lane_pitch_map:
            self._layout_pitches = list(lane_pitch_map)
            self._all_pitches = build_keyboard_range(lane_pitch_map)
            self._kb_layout, self._hwy_layout = compute_key_layout(
                self._all_pitches, self.HWY_X0, self.HWY_W)
            self._kb_keys = build_piano_key_rects(
                self._kb_layout, self._all_pitches, self.PIANO_Y, self.PIANO_H)
            self._static_key = None
        key = (tuple(self._layout_pitches), getattr(self, '_vanish_frac', 0.67), self.W, self.H)
        if key != self._static_key:
            # The highway only changes with the lanes, perspective or window size
            self._static = pygame.Surface((self.W, self.H)).convert()
            self._static.blit(self._bg, (0, 0))
            self._draw_highway(self._static)
            self._edges.clear()
            self._static_key = key

    def _pitch_bounds(self, pitch: int) -> Tuple[int,int,int]:
        """Highway lane x_left, x_right, x_center — uses same bounds as keyboard."""
        if pitch in self._kb_layout:
            return self._kb_layout[pitch]
        return self.HWY_X0, self.HWY_X1, (self.HWY_X0+self.HWY_X1)//2

    def _project_x(self, x_bot: float, depth: float) -> int:
        """
        Project a bottom x-coordinate up toward the vanish band.
        vf=0.0 -> straight (top x = bottom x, no convergence)
        vf=0.67 -> default 2/3 perspective (original look)
        vf=1.0 -> tight convergence
        """
        bot_total = self.HWY_X1 - self.HWY_X0
        if bot_total == 0:
            return int(x_bot)
        vf = max(0.0, min(1.0, getattr(self, '_vanish_frac', 0.67)))
        if vf == 0.0:
            # Straight: no perspective at all — top equals bottom
            return int(x_bot)
        # Fraction across the highway
        frac = (x_bot - self.HWY_X0) / bot_total
        frac = max(0.0, min(1.0, frac))
        # Vanish band: shrinks the highway width at the top
        # vf=0.67 -> van_w = HWY_W / 3  (original)
        # vf=1.0  -> van_w = HWY_W / 9  (very tight)
        hwy_w = float(bot_total)
        min_frac = 1.0 / 9.0
        top_frac = 1.0 - vf * (1.0 - min_frac)   # 1.0 at vf=0 (not used), min_frac at vf=1
        van_w  = hwy_w * top_frac
        van_x0 = self.W / 2 - van_w / 2
        # Target x at depth=1
        x_top = van_x0 + frac * van_w
        return int(lerp(x_bot, x_top, depth))

    def _proj_lane(self, pitch: int, depth: float) -> Tuple[int,int,int]:
        """Returns (lx, rx, cx) for pitch at given depth (0=hit line, 1=vanish)."""
        lx_b, rx_b, cx_b = self._pitch_bounds(pitch)
        lx = self._project_x(lx_b, depth)
        rx = self._project_x(rx_b, depth)
        cx = self._project_x(cx_b, depth)
        return lx, rx, cx

    def _depth_to_y(self, depth: float) -> int:
        return int(lerp(self.HWY_BOT, self.HWY_TOP, depth))

    # ── Note colors: white for naturals, neutral dark grey for sharps ──
    @staticmethod
    def _lane_col(pitch: int, lane_idx: int) -> Tuple[int,int,int]:
        if is_black(pitch):
            return (45, 45, 55)   # neutral dark grey — no color at all
        else:
            return (240, 240, 255)  # bright white

    # ── Main draw ─────────────────────────────────────────────────
    def draw(self, song: SongData, current_time: float,
             num_lanes: int, lane_pitch_map: List[int], dt: float,
             pressed_keys: set = None, key_hints: Dict[int, str] = None,
             targets: set = None):
        """key_hints: pitch -> computer key that plays it (shown on the keys);
        targets: pitches EASY mode is waiting for (highlighted green)."""
        self._glow_tick += dt

        self._ensure_layout(lane_pitch_map)
        self.screen.blit(self._static, (0,0))   # background + highway (cached)
        self._draw_notes(song, current_time, lane_pitch_map)
        self._update_particles(dt)
        self._draw_hit_zone(lane_pitch_map, dt)
        self._draw_keyboard(lane_pitch_map, pressed_keys or set(), key_hints, targets)


    # ── Highway (static: drawn once into the cached layer) ─────────
    def _draw_highway(self, surf: pygame.Surface):
        # Lane background trapezoids. Projection is linear in depth, so each lane
        # edge is a straight line and four corners describe the whole lane.
        y_bot, y_top = self._depth_to_y(0.0), self._depth_to_y(1.0)
        for p in self._all_pitches:
            lx_b,rx_b,_ = self._pitch_bounds(p)
            bg = (6,6,14) if is_black(p) else (10,10,22)
            pygame.draw.polygon(surf, bg, [
                (self._project_x(lx_b, 0.0), y_bot), (self._project_x(lx_b, 1.0), y_top),
                (self._project_x(rx_b, 1.0), y_top), (self._project_x(rx_b, 0.0), y_bot)])

        # Draw divider lines between ALL adjacent lanes.
        # White-white boundaries (B-C, E-F) get a slightly brighter line so
        # the gap is visible. Sharp-natural boundaries get a subtle dark line.
        NO_BLACK_BETWEEN = {(4,5),(11,0)}  # E-F and B-C (semitone pairs)
        for i, p in enumerate(self._all_pitches[:-1]):
            next_p = self._all_pitches[i+1]
            _, rx_b, _ = self._pitch_bounds(p)
            tx = self._project_x(rx_b, 1.0); ty = self._depth_to_y(1.0)
            bx = self._project_x(rx_b, 0.0); by = self._depth_to_y(0.0)
            pair = (p%12, next_p%12)
            if pair in NO_BLACK_BETWEEN:
                # White-white boundary: brighter line so B and C look separate
                pygame.draw.line(surf, (40,40,65), (tx,ty),(bx,by), 2)
            else:
                pygame.draw.line(surf, (18,18,35), (tx,ty),(bx,by), 1)
        # Right edge of last key
        _, rx_b, _ = self._pitch_bounds(self._all_pitches[-1])
        tx=self._project_x(rx_b,1.0); bx=self._project_x(rx_b,0.0)
        pygame.draw.line(surf,(18,18,35),(tx,self._depth_to_y(1.0)),(bx,self._depth_to_y(0.0)),1)

        # Horizontal depth grid
        for g in range(20):
            d = g/19
            y = self._depth_to_y(d)
            lx_b,_,_ = self._pitch_bounds(self._all_pitches[0])
            _,rx_b,_ = self._pitch_bounds(self._all_pitches[-1])
            lx = self._project_x(lx_b, d)
            rx = self._project_x(rx_b, d)
            a = int(lerp(55,3,d))
            pygame.draw.line(surf,(a//4,a//4,a),(lx,y),(rx,y),1)

        # Outer neon edge glow
        p0 = self._all_pitches[0];  pN = self._all_pitches[-1]
        lx0_b,_,_ = self._pitch_bounds(p0);  _,rxN_b,_ = self._pitch_bounds(pN)
        for off in range(1,5):
            a = max(4,55-off*13)
            lt_x=self._project_x(lx0_b,1.0); lb_x=self._project_x(lx0_b,0.0)
            rt_x=self._project_x(rxN_b,1.0); rb_x=self._project_x(rxN_b,0.0)
            pygame.draw.line(surf,(0,a,a),
                (lt_x-off,self._depth_to_y(1.0)),(lb_x-off,self._depth_to_y(0.0)),1)
            pygame.draw.line(surf,(0,a,a),
                (rt_x+off,self._depth_to_y(1.0)),(rb_x+off,self._depth_to_y(0.0)),1)

    # ── Notes ─────────────────────────────────────────────────────
    def _draw_notes(self, song: SongData, t: float, lpm: List[int]):
        if self._note_index[0] is not song:   # index built once per song
            self._note_index = (song, [n.time_sec for n in song.notes],
                                max((n.duration_sec for n in song.notes), default=0.0))
        _, starts, longest = self._note_index
        in_song = set(lpm)
        end = t + NOTE_LOOKAHEAD_SECS
        notes = song.notes
        # First note that can still be on screen (a note ends at most `longest` after it starts)
        first = bisect.bisect_left(starts, t - 0.15 - longest)
        for i in range(first, len(notes)):
            note = notes[i]
            if note.time_sec > end: break
            if note.time_sec + note.duration_sec < t-0.15: continue
            if note.pitch not in in_song: continue

            df  = clamp((note.time_sec - t)/NOTE_LOOKAHEAD_SECS, 0.0, 1.0)
            db  = clamp((note.time_sec + note.duration_sec - t)/NOTE_LOOKAHEAD_SECS, 0.0, 1.0)
            if df>=1.0 and db>=1.0: continue
            if df<=0.0 and db<=0.0: continue
            self._draw_note_block(note.pitch, df, db, self._lane_col(note.pitch, 0))

    SNAP_ROWS = 3   # how far a gradient-strip corner may slide to sit on the true edge

    def _note_edges(self, pitch):
        """A lane's note edges as straight screen lines x = a + k*y, plus a corner table.

        Notes get anti-aliased sides: a 1px aaline along each edge, with the gradient fill
        ending exactly under it. pygame fills each polygon row from floor(left line) to
        floor(right line) between whole-pixel corners, so a corner only lands exactly on the
        edge on rows where the edge sits just right of a whole pixel. For every row the table
        holds the best such row within SNAP_ROWS, and the corner x there (left, then right)."""
        e = self._edges.get(pitch)
        if e is None:
            lx_b, rx_b, _ = self._pitch_bounds(pitch)
            mg = 0.5 if is_black(pitch) else 1.5
            l0, l1 = lx_b + mg, self._project_x(lx_b + mg, 1.0)
            r0, r1 = rx_b - mg, self._project_x(rx_b - mg, 1.0)
            y_bot, y_span = self.HWY_BOT, self.HWY_TOP - self.HWY_BOT
            kl = (l1 - l0) / y_span if y_span else 0.0
            kr = (r1 - r0) / y_span if y_span else 0.0
            al, ar = l0 - kl * y_bot, r0 - kr * y_bot
            m = self.SNAP_ROWS
            top = min(self.HWY_TOP, y_bot)
            ys = np.arange(top, max(self.HWY_TOP, y_bot) + 1)
            table = []
            for v in (al + kl * ys + 1.5, ar + kr * ys - 0.5):   # fill's first / last pixel
                x = np.floor(v)
                pad = np.concatenate([np.full(m, 9.0), v - x, np.full(m, 9.0)])
                best = np.arange(len(ys)) - m + sliding_window_view(pad, 2 * m + 1).argmin(1)
                table += [ys[best].tolist(), x[best].astype(int).tolist()]
            e = self._edges[pitch] = (al, kl, ar, kr, top, *table)
        return e

    def _draw_note_block(self, pitch, df, db, color):
        al, kl, ar, kr, top, LY, LX, RY, RX = self._note_edges(pitch)
        blk = is_black(pitch)
        scr, floor, poly = self.screen, math.floor, pygame.draw.polygon
        y_bot, y_span = self.HWY_BOT, self.HWY_TOP - self.HWY_BOT
        yt, yb = int(y_bot + y_span * db), int(y_bot + y_span * df)
        h = yb - yt
        dark = tuple(max(0,int(c*0.5)) for c in color)
        bright = tuple(min(255,int(c*1.7)) for c in color)
        edge_col = (200,200,220) if not blk else tuple(min(255,int(c*1.4)) for c in color)

        # Gradient strips (bounded: a long held note used to be ~100 polygons), filled up to
        # the edge lines drawn below. Inner corners slide a few rows to fit the edge exactly
        # (strips are >= 8 rows tall, so they keep their order).
        xl, xr = floor(al + kl * yb + 1.5), floor(ar + kr * yb - 0.5)
        bl, br = (xl, yb), (xr, yb)
        steps = max(2, min(24, h // 8))
        for s in range(steps):
            y = yb - (h * (s + 1)) // steps
            i = y - top
            if s < steps - 1 and h > 1 and yt < LY[i] < yb and yt < RY[i] < yb:
                tl, tr = (LX[i], LY[i]), (RX[i], RY[i])
            else:
                tl, tr = (floor(al + kl * y + 1.5), y), (floor(ar + kr * y - 0.5), y)
            poly(scr, lerpC(color, dark, s / steps), [tl, tr, br, bl])
            bl, br = tl, tr

        # Bright 3px base, then the anti-aliased sides (the left one in the edge colour)
        if xr >= xl:
            scr.fill(bright, (xl, yb - 1, xr - xl + 1, 3))
        pygame.draw.aaline(scr, bright, (ar + kr * yt - 0.5, yt), (ar + kr * (yb + 1) - 0.5, yb + 1))
        pygame.draw.aaline(scr, edge_col, (al + kl * yt + 0.5, yt), (al + kl * (yb + 1) + 0.5, yb + 1))

        lbl = self._labels.get((pitch % 12, blk))
        if lbl is None:
            lbl_color = (15,15,15) if not blk else (200,200,220)
            lbl = self._labels[(pitch % 12, blk)] = self.fn_note.render(pitch_name(pitch), True, lbl_color)
        dx = (xl + xr)//2 - lbl.get_width()//2
        dy = yb - 2 - lbl.get_height()
        if 0<=dx<self.W and 0<=dy<self.H:
            scr.blit(lbl,(dx,dy))

    # ── Hit zone ──────────────────────────────────────────────────
    def _draw_hit_zone(self, lpm: List[int], dt: float):
        p2i = {p:i for i,p in enumerate(lpm)}
        y = self.HIT_Y

        for p in self._all_pitches:
            lx_b,rx_b,cx_b = self._pitch_bounds(p)
            lx = self._project_x(lx_b, 0.0)
            rx = self._project_x(rx_b, 0.0)
            in_lane = p in p2i

            if in_lane:
                li  = p2i[p]
                col = self._lane_col(p, li)
            else:
                col = (30,30,50)

            pygame.draw.line(self.screen, col, (lx,y),(rx,y), 2)

            if in_lane:
                li = p2i[p]
                if li in self.hit_flashes:
                    fc,timer = self.hit_flashes[li]
                    timer -= dt
                    if timer<=0: del self.hit_flashes[li]
                    else:
                        self.hit_flashes[li]=(fc,timer)
                        a=timer/0.18; gh=int(44*a)
                        gs=pygame.Surface((rx-lx,gh),pygame.SRCALPHA)
                        gs.fill((*fc,int(190*a)))
                        self.screen.blit(gs,(lx,y-gh))

                if li in self.miss_flashes:
                    timer=self.miss_flashes[li]-dt
                    if timer<=0: del self.miss_flashes[li]
                    else:
                        self.miss_flashes[li]=timer
                        a=timer/0.22
                        ms=pygame.Surface((rx-lx,22),pygame.SRCALPHA)
                        ms.fill((210,20,20,int(155*a)))
                        self.screen.blit(ms,(lx,y-11))

        # Full glow below
        lx0_b,_,_ = self._pitch_bounds(self._all_pitches[0])
        _,rxN_b,_ = self._pitch_bounds(self._all_pitches[-1])
        lxf=self._project_x(lx0_b,0.0); rxf=self._project_x(rxN_b,0.0)
        for off in range(1,5):
            a=max(0,50-off*11)
            pygame.draw.line(self.screen,(0,a,a*2),(lxf,y+off),(rxf,y+off),1)

        # ── Trigger zone: dashed border lines, color shifts at x4/x8 ──
        tz_half = int(self.H * 0.018)
        seg, gap = 10, 14
        mult = getattr(self, '_last_multiplier', 1)
        if mult >= 8:
            col_dash = (0, 160, 255)   # bright cyan-blue at x8
        elif mult >= 4:
            col_dash = (0, 100, 200)   # medium blue at x4
        else:
            col_dash = (0, 40, 80)     # dim base
        for sx in range(lxf, rxf, seg + gap):
            ex = min(sx + seg, rxf)
            pygame.draw.line(self.screen, col_dash, (sx, y - tz_half), (ex, y - tz_half), 1)
            pygame.draw.line(self.screen, col_dash, (sx, y + tz_half), (ex, y + tz_half), 1)
        # Solid hit line
        pygame.draw.line(self.screen, (0, 200, 255), (lxf, y), (rxf, y), 2)

    # ── Piano keyboard ────────────────────────────────────────────
    def _key_shadow(self, w, h):
        """Top-edge shading for an unpressed white key (cached per key size)."""
        sh = self._shadows.get((w, h))
        if sh is None:
            sh = self._shadows[(w, h)] = pygame.Surface((w, h), pygame.SRCALPHA)
            for gg in range(h):
                a = int(45*(1-gg/h))
                pygame.draw.line(sh, (0,0,0,a), (0,gg), (w,gg))
        return sh

    def _key_label(self, text, color):
        lbl = self._labels.get(("key", text, color))
        if lbl is None:
            lbl = self._labels[("key", text, color)] = self.fn_key_lbl.render(text, True, color)
        return lbl

    def _key_cap(self, letter, black):
        """Small keycap with the computer key that plays a piano key."""
        cap = self._labels.get(("cap", letter, black))
        if cap is None:
            fg, bg, edge = (((214, 214, 230), (44, 44, 62), (96, 96, 122)) if black else
                            ((46, 46, 70), (206, 206, 218), (140, 140, 162)))
            t = self.fn_key_lbl.render(letter, True, fg)
            h = t.get_height() + 2
            cap = pygame.Surface((max(h, t.get_width() + 6), h), pygame.SRCALPHA)
            pygame.draw.rect(cap, bg, cap.get_rect(), border_radius=3)
            pygame.draw.rect(cap, edge, cap.get_rect(), 1, border_radius=3)
            cap.blit(t, t.get_rect(center=cap.get_rect().center))
            self._labels[("cap", letter, black)] = cap
        return cap

    def _draw_keyboard(self, lpm: List[int], pressed: set = None, key_hints=None, targets=None):
        """Held keys light up cyan and show their name with the octave (C4, F#3...). Keys
        EASY mode is waiting for pulse green. key_hints puts the computer key that plays each
        piano key on it (used when no MIDI keyboard is connected)."""
        if not self._kb_keys: return
        pressed = pressed or set()
        key_hints = key_hints or {}
        targets = targets or set()
        pulse = 0.5 + 0.5 * math.sin(self._glow_tick * 6.0)
        scr = self.screen

        # Use keyboard layout (not highway) for keyboard bounds
        lx0_b = self._kb_layout[self._all_pitches[0]][0]
        rxN_b = self._kb_layout[self._all_pitches[-1]][1]

        pygame.draw.rect(scr,(6,6,16),
            pygame.Rect(lx0_b, self.PIANO_Y, rxN_b-lx0_b, self.PIANO_H))

        for rect,blk,p in self._kb_keys:
            if blk: continue
            is_pressed = p in pressed
            is_target = p in targets and not is_pressed
            if is_pressed:
                fill, border, lcol = (120,240,255), (0,200,220), (0,40,60)
            elif is_target:
                fill = ui.mix((225,225,225), NEON_GREEN, 0.35 + 0.3 * pulse)
                border, lcol = (0,150,60), (0,60,24)
            else:
                fill, border, lcol = (225,225,225), (80,80,90), (70,70,80)
            pygame.draw.rect(scr, fill, rect, border_radius=3)
            if not is_pressed:
                scr.blit(self._key_shadow(rect.w, min(rect.h//3,18)), (rect.x, rect.y))
            pygame.draw.rect(scr, border, rect, 2 if (is_pressed or is_target) else 1,
                             border_radius=3)
            if rect.h > 30:
                # The octave number on every C (and on keys being played) keeps you oriented
                full = is_pressed or is_target or p % 12 == 0
                lbl = self._key_label(f"{pitch_name(p)}{p//12 - 1}" if full else pitch_name(p), lcol)
                if lbl.get_width() > rect.w - 2:
                    lbl = self._key_label(pitch_name(p), lcol)
                scr.blit(lbl, (rect.centerx - lbl.get_width()//2, rect.bottom - lbl.get_height() - 3))
                hint = key_hints.get(p)
                if hint:
                    cap = self._key_cap(hint, False)
                    if cap.get_width() <= rect.w - 2:
                        scr.blit(cap, cap.get_rect(center=(rect.centerx, rect.y + int(rect.h * 0.56))))

        for rect,blk,p in self._kb_keys:
            if not blk: continue
            is_pressed = p in pressed
            is_target = p in targets and not is_pressed
            if is_pressed:
                fill, border = (0,160,200), (0,230,255)
            elif is_target:
                fill, border = ui.mix((20,20,20), NEON_GREEN, 0.45 + 0.3 * pulse), (90,255,140)
            else:
                fill, border = (20,20,20), (50,50,50)
            pygame.draw.rect(scr, fill, rect, border_radius=3)
            if not (is_pressed or is_target):
                pygame.draw.line(scr,(55,55,55),(rect.x+1,rect.y+2),(rect.x+1,rect.bottom-3),1)
            pygame.draw.rect(scr, border, rect, 1, border_radius=3)
            if is_pressed or is_target:
                col = (0,30,46) if is_pressed else (0,40,16)
                for txt in (f"{pitch_name(p)}{p//12 - 1}", pitch_name(p)):
                    lbl = self._key_label(txt, col)
                    if lbl.get_width() <= rect.w - 2:
                        scr.blit(lbl, (rect.centerx - lbl.get_width()//2,
                                       rect.bottom - lbl.get_height() - 3))
                        break
            elif key_hints.get(p):
                cap = self._key_cap(key_hints[p], True)
                if cap.get_width() <= rect.w:
                    scr.blit(cap, cap.get_rect(midbottom=(rect.centerx, rect.bottom - 3)))

        pygame.draw.line(scr,NEON_CYAN,
            (lx0_b,self.PIANO_Y),(rxN_b,self.PIANO_Y),2)

    # ── Particles ─────────────────────────────────────────────────
    def _update_particles(self, dt):
        self.particles=[p for p in self.particles if (p.update(dt) or True) and p.alive]
        for p in self.particles: p.draw(self.screen)

    def spawn_hit_particles(self, li, n, color, quality):
        if li >= len(self._layout_pitches): return
        self.hit_flashes[li]=(color,0.18)
        room = MAX_PARTICLES - len(self.particles)
        if room <= 0: return
        pitch = self._layout_pitches[li]
        lx_b,rx_b,cx_b = self._pitch_bounds(pitch)
        cx = self._project_x(cx_b, 0.0); y = self.HIT_Y
        count = min(room, {"PERFECT":24,"GREAT":14,"GOOD":7,"GODLIKE":35}.get(quality,4))
        bright=tuple(min(255,int(c*1.5)) for c in color)
        for _ in range(count):
            ang=_rng.uniform(-math.pi,0); spd=_rng.uniform(80,310)
            self.particles.append(Particle(cx,y,bright,
                math.cos(ang)*spd,math.sin(ang)*spd,_rng.uniform(0.3,0.9),_rng.randint(3,8)))

    def spawn_miss_particles(self, li, n):
        if li >= len(self._layout_pitches): return
        self.miss_flashes[li]=0.22
        room = MAX_PARTICLES - len(self.particles)
        if room <= 0: return
        pitch = self._layout_pitches[li]
        lx_b,rx_b,cx_b = self._pitch_bounds(pitch)
        cx=self._project_x(cx_b,0.0)
        for _ in range(min(7, room)):
            ang=_rng.uniform(-math.pi,0); spd=_rng.uniform(35,130)
            self.particles.append(Particle(cx,self.HIT_Y,(215,20,20),
                math.cos(ang)*spd,math.sin(ang)*spd,0.4,3))


    # ── HUD ───────────────────────────────────────────────────────
    @staticmethod
    def _mult_color(m):
        if m >= COMBO_MULTIPLIER_MAX: return NEON_CYAN
        if m >= 4: return NEON_PINK
        if m >= 2: return NEON_YELLOW
        return ui.TEXT

    def _num(self, slot, text, px, color):
        """Text that changes often (score, combo, time): one cached surface per slot, so the
        numbers don't flood the shared text cache."""
        key = (text, px, color)
        c = self._nums.get(slot)
        if c is None or c[0] != key:
            c = self._nums[slot] = (key, ui.font(px, True).render(text, True, color))
        return c[1]

    def _judge_surfs(self, quality, px):
        """The judgment word and its shadow (private copies: their alpha is animated)."""
        c = self._judge_cache.get((quality, px))
        if c is None:
            f = ui.font(px, True)
            c = self._judge_cache[(quality, px)] = (
                f.render(quality, True, ui.JUDGE_COLOR.get(quality, ui.TEXT)),
                f.render(quality, True, (0, 0, 0)))
        return c

    def draw_hud(self, stats, mode, progress, elapsed, duration, speed=1.0, autoplay=False,
                 last_hit_quality="", waiting=False, dt=0.0):
        """Score (left), combo and multiplier (centre), accuracy and live grade (right), the
        song's progress along the far edge of the highway, and a judgment that pops up for
        every judged note. autoplay: the run is not scored, so its numbers are dimmed."""
        surf, W = self.screen, self.W
        s = ui.scale_for(W, self.H)
        m, top = int(18 * s), int(8 * s)
        lab_px, val_px, pill_px = max(9, int(12 * s)), max(16, int(30 * s)), max(9, int(12 * s))
        lab_h = ui.font(lab_px, True).get_height()
        val_h = ui.font(val_px, True).get_height()
        vy = top + lab_h              # top of the value row
        vcy = vy + val_h // 2         # and its centre

        # What changed since the last frame starts the animations
        judged = stats.hits_perfect + stats.hits_great + stats.hits_good + stats.misses
        if judged > self._hud_judged and last_hit_quality and mode != MODE_TESTING and not waiting:
            self._judge = (last_hit_quality, 0.0)     # (autoplay judges nothing: no pop)
        if stats.combo > self._hud_combo:
            self._combo_pop = 0.0
        if stats.misses > self._hud_misses:
            self._combo_break = 0.0
        self._hud_judged, self._hud_combo, self._hud_misses = judged, stats.combo, stats.misses
        self._combo_pop += dt
        self._combo_break += dt
        dim = autoplay

        # ── Score + run tags (left)
        ui.draw_text(surf, "SCORE", lab_px, ui.TEXT_MUTED, (m, top), bold=True)
        surf.blit(self._num("score", f"{stats.score:,}", val_px,
                            ui.TEXT_DIM if dim else NEON_CYAN), (m, vy))
        tags = [(ui.mode_name(mode), ui.mode_color(mode), False)]
        if abs(speed - 1.0) > 1e-3:
            tags.append((f"SPEED {round(speed * 100)}%", NEON_CYAN, False))
        if autoplay:
            tags.append(("NOT SCORED", NEON_ORANGE, True))
        x, bottom = m, vy + val_h
        for lab, col, filled in tags:
            r = ui.pill(surf, lab, col, (x, vy + val_h + int(3 * s)), s, px=pill_px,
                        filled=filled)
            x, bottom = r.right + int(6 * s), max(bottom, r.bottom)
        self.hud_left_bottom = bottom     # (the app shows the song's keys under it)

        # ── Combo + multiplier (centre). The meter fills up with every hit; ten in a row
        #    raise the multiplier (up to x8, when it stays full).
        cx = W // 2
        mult = stats.multiplier
        mc = self._mult_color(mult)
        ui.draw_text(surf, "COMBO", lab_px, ui.TEXT_MUTED, (cx, top), bold=True, anchor="midtop")
        combo_txt = str(stats.combo)
        if self._combo_break < 0.35:
            ccol = NEON_RED
        elif dim or stats.combo == 0:
            ccol = ui.TEXT_DIM
        else:
            ccol = mc
        pop = max(0.0, 1.0 - self._combo_pop / 0.14)
        cs = self._num("combo", combo_txt, val_px + int(val_px * 0.22 * pop) // 2 * 2, ccol)
        base_w = ui.font(val_px, True).size(combo_txt)[0]
        mtxt = f"×{mult}"
        gap = int(8 * s)
        x0 = cx - (base_w + gap + ui.pill_w(mtxt, s, pill_px)) // 2
        surf.blit(cs, cs.get_rect(center=(x0 + base_w // 2, vcy)))
        live = mult > 1 and not dim
        ui.pill(surf, mtxt, mc if live else ui.TEXT_DIM, (x0 + base_w + gap, vcy), s,
                px=pill_px, anchor="midleft", filled=live)
        lit = 10 if mult >= COMBO_MULTIPLIER_MAX else stats.combo % 10
        sw, sh, sg = max(5, int(9 * s)), max(3, int(4 * s)), max(2, int(3 * s))
        sx, sy = cx - (10 * sw + 9 * sg) // 2, vy + val_h + int(5 * s)
        on = ui.TEXT_DIM if dim else mc
        for i in range(10):
            pygame.draw.rect(surf, on if i < lit else (38, 38, 62),
                             (sx + i * (sw + sg), sy, sw, sh), border_radius=sh // 2)

        # ── Accuracy + live grade (right)
        rx = W - m
        ui.draw_text(surf, "ACCURACY", lab_px, ui.TEXT_MUTED, (rx, top), bold=True,
                     anchor="topright")
        acc = stats.accuracy
        if judged == 0:
            atxt, acol = "–", ui.TEXT_DIM
        else:
            atxt = f"{acc:.1f}%"
            acol = (ui.TEXT_DIM if dim else NEON_GREEN if acc >= 90 else
                    NEON_YELLOW if acc >= 78 else NEON_ORANGE if acc >= 62 else NEON_RED)
        a_s = self._num("acc", atxt, val_px, acol)
        ar = surf.blit(a_s, a_s.get_rect(topright=(rx, vy)))
        if judged and not autoplay:
            g = stats.get_grade()
            ui.pill(surf, g, ui.GRADE_COLOR.get(g, ui.TEXT), (ar.x - int(10 * s), vcy), s,
                    px=pill_px + 2, anchor="midright")

        # ── Song progress along the far edge of the highway, with the times at its ends
        hw = int(max(W * 0.2, min(W * 0.5, self._project_x(self.HWY_X1, 1.0)
                                  - self._project_x(self.HWY_X0, 1.0))))
        px0, px1 = W // 2 - hw // 2, W // 2 + hw // 2
        y = self.HWY_TOP - max(6, int(9 * s))
        bh = max(3, int(4 * s))
        prog = max(0.0, min(1.0, progress))
        ui.bar(surf, (px0, y - bh // 2, hw, bh), prog, ui.shade(NEON_CYAN, 0.7))
        hx = px0 + int(hw * prog)
        pygame.draw.circle(surf, NEON_CYAN, (hx, y), max(3, int(5 * s)))
        pygame.draw.circle(surf, ui.TEXT, (hx, y), max(1, int(2 * s)))
        tpx = max(9, int(12 * s))
        t_s = self._num("time", ui.fmt_time(elapsed), tpx, ui.TEXT_MUTED)
        surf.blit(t_s, t_s.get_rect(midright=(px0 - int(10 * s), y)))
        ui.draw_text(surf, ui.fmt_time(duration), tpx, ui.TEXT_DIM, (px1 + int(10 * s), y),
                     anchor="midleft")

        self._last_multiplier = mult  # the hit zone's dashes brighten at x4 and x8

        # ── Judgment pop: a quarter of the way down the highway, clear of the hit line
        q, age = self._judge
        if q:
            age += dt
            life = 0.6
            if age >= life:
                self._judge = ("", 0.0)
            else:
                self._judge = (q, age)
                k = min(1.0, age / 0.08)
                jpx = int(30 * s * (1.25 - 0.25 * k)) // 2 * 2
                a = 1.0 if age < life * 0.5 else max(0.0, 1.0 - (age - life * 0.5) / (life * 0.5))
                t, sh = self._judge_surfs(q, jpx)
                cy = self.HWY_TOP + int((self.HIT_Y - self.HWY_TOP) * 0.26) - int(8 * s * age / life)
                jr = t.get_rect(center=(W // 2, cy))
                sh.set_alpha(int(150 * a))
                t.set_alpha(int(255 * a))
                surf.blit(sh, (jr.x + 2, jr.y + 3))
                surf.blit(t, jr)
