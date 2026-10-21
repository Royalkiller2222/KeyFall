"""
KeyFall - Renderer v8
Highway lanes aligned to piano key widths.
Black key lanes narrower + darker. White key lanes wider + brighter.
"""

import math, random
import pygame
from typing import List, Tuple, Dict
from game.constants import *
from game.midi_handler import MidiNote, SongData

NOTE_NAMES      = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
BLACK_SEMITONES = {1, 3, 6, 8, 10}

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
    # The highway is a gapless piano-roll:
    #   Each lane spans from the LEFT edge of the keyboard slot for
    #   that pitch to the RIGHT edge — i.e. exactly what compute_key_layout
    #   already assigned as the keyboard slot width, but for white keys
    #   we extend to fill the space under adjacent black keys.
    #
    #   Strategy: work in keyboard-slot space.
    #   White key lane left  = midpoint between this key's left edge
    #                          and the center of the black key to its left
    #                          (or the absolute left if no black key there).
    #   White key lane right = midpoint between this key's right edge
    #                          and the center of the black key to its right
    #                          (or the absolute right if no black key there).
    #   Black key lane       = same as keyboard position.
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
    PIANO_H    = 95
    HIT_ZONE_H = 28   # larger gap = highway appears higher up

    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self._init_geometry()
        self.particles: List[Particle] = []
        self.hit_flashes: Dict[int, tuple] = {}
        self.miss_flashes: Dict[int, float] = {}
        self._glow_tick: float = 0.0
        self._init_fonts()
        self._bg = self._build_bg()
        # layout cache — rebuilt when lane_pitch_map changes
        self._layout_pitches: List[int] = []
        self._kb_layout: Dict[int, tuple] = {}    # keyboard key positions
        self._hwy_layout: Dict[int, tuple] = {}   # highway lane positions (gap-free)
        self._kb_keys: list = []
        self._all_pitches: List[int] = []

    def _init_geometry(self):
        self.W = self.screen.get_width()
        self.H = self.screen.get_height()
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
        self.fn_hud_lg  = pygame.font.SysFont("consolas", max(22,int(44*s)), bold=True)
        self.fn_hud_md  = pygame.font.SysFont("consolas", max(13,int(24*s)), bold=True)
        self.fn_hud_sm  = pygame.font.SysFont("consolas", max(10,int(16*s)))
        self.fn_note    = pygame.font.SysFont("consolas", max(8, int(12*s)), bold=True)
        self.fn_key_lbl = pygame.font.SysFont("consolas", max(7, int(10*s)), bold=True)
        self.fn_quality = pygame.font.SysFont("consolas", max(26,int(52*s)), bold=True)

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

    # ── Layout management ─────────────────────────────────────────
    def _ensure_layout(self, lane_pitch_map: List[int]):
        if self._layout_pitches == lane_pitch_map:
            return
        self._layout_pitches = list(lane_pitch_map)
        self._all_pitches = build_keyboard_range(lane_pitch_map)
        self._kb_layout, self._hwy_layout = compute_key_layout(
            self._all_pitches, self.HWY_X0, self.HWY_W)
        self._kb_keys = build_piano_key_rects(
            self._kb_layout, self._all_pitches, self.PIANO_Y, self.PIANO_H)

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
             pressed_keys: set = None):
        self._glow_tick += dt

        self._ensure_layout(lane_pitch_map)
        self.screen.blit(self._bg, (0,0))
        self._draw_highway(lane_pitch_map)
        self._draw_notes(song, current_time, lane_pitch_map)
        self._update_particles(dt)
        self._draw_hit_zone(lane_pitch_map, dt)
        self._draw_keyboard(lane_pitch_map, pressed_keys or set())



    # ── Highway ───────────────────────────────────────────────────
    def _draw_highway(self, lpm: List[int]):
        p2i = {p:i for i,p in enumerate(lpm)}

        for p in self._all_pitches:
            blk = is_black(p)
            in_lane = p in p2i

            # Lane background trapezoid
            lx_b,rx_b,_ = self._pitch_bounds(p)
            d_steps = 30
            pts_l, pts_r = [], []
            for s in range(d_steps+1):
                d = s/d_steps
                y = self._depth_to_y(d)
                lx = self._project_x(lx_b, d)
                rx = self._project_x(rx_b, d)
                pts_l.append((lx, y))
                pts_r.append((rx, y))

            # Fill
            if blk:
                bg = (6,6,14)
            else:
                bg = (10,10,22)
            poly = pts_l + list(reversed(pts_r))
            pygame.draw.polygon(self.screen, bg, poly)

        # Vertical lane dividers — only between adjacent pitches
        for i, p in enumerate(self._all_pitches):
            lx_b, _, _ = self._pitch_bounds(p)
            for d in [0.0, 1.0]:
                pass  # drawn as lines below

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
                pygame.draw.line(self.screen, (40,40,65), (tx,ty),(bx,by), 2)
            else:
                pygame.draw.line(self.screen, (18,18,35), (tx,ty),(bx,by), 1)
        # Right edge of last key
        _, rx_b, _ = self._pitch_bounds(self._all_pitches[-1])
        tx=self._project_x(rx_b,1.0); bx=self._project_x(rx_b,0.0)
        pygame.draw.line(self.screen,(18,18,35),(tx,self._depth_to_y(1.0)),(bx,self._depth_to_y(0.0)),1)

        # Horizontal depth grid
        for g in range(20):
            d = g/19
            y = self._depth_to_y(d)
            lx_b,_,_ = self._pitch_bounds(self._all_pitches[0])
            _,rx_b,_ = self._pitch_bounds(self._all_pitches[-1])
            lx = self._project_x(lx_b, d)
            rx = self._project_x(rx_b, d)
            a = int(lerp(55,3,d))
            pygame.draw.line(self.screen,(a//4,a//4,a),(lx,y),(rx,y),1)

        # Outer neon edge glow
        p0 = self._all_pitches[0];  pN = self._all_pitches[-1]
        lx0_b,_,_ = self._pitch_bounds(p0);  _,rxN_b,_ = self._pitch_bounds(pN)
        for off in range(1,5):
            a = max(4,55-off*13)
            lt_x=self._project_x(lx0_b,1.0); lb_x=self._project_x(lx0_b,0.0)
            rt_x=self._project_x(rxN_b,1.0); rb_x=self._project_x(rxN_b,0.0)
            pygame.draw.line(self.screen,(0,a,a),
                (lt_x-off,self._depth_to_y(1.0)),(lb_x-off,self._depth_to_y(0.0)),1)
            pygame.draw.line(self.screen,(0,a,a),
                (rt_x+off,self._depth_to_y(1.0)),(rb_x+off,self._depth_to_y(0.0)),1)

    # ── Notes ─────────────────────────────────────────────────────
    def _draw_notes(self, song: SongData, t: float, lpm: List[int]):
        p2i = {p:i for i,p in enumerate(lpm)}
        end = t + NOTE_LOOKAHEAD_SECS
        # Fade in over first 1.5 seconds of song


        for note in song.notes:
            if note.time_sec > end: break
            if note.time_sec + note.duration_sec < t-0.15: continue
            if note.pitch not in p2i: continue

            li  = p2i[note.pitch]
            col = self._lane_col(note.pitch, li)
            df  = clamp((note.time_sec - t)/NOTE_LOOKAHEAD_SECS, 0.0, 1.0)
            db  = clamp((note.time_sec + note.duration_sec - t)/NOTE_LOOKAHEAD_SECS, 0.0, 1.0)
            if df>=1.0 and db>=1.0: continue
            if df<=0.0 and db<=0.0: continue
            self._draw_note_block(note.pitch, df, db, col)

    def _draw_note_block(self, pitch, df, db, color):
        lx_b, rx_b, cx_b = self._pitch_bounds(pitch)
        blk = is_black(pitch)
        mg = 0.5 if blk else 1.5

        def corners(d):
            y  = self._depth_to_y(d)
            lx = self._project_x(lx_b + mg, d)
            rx = self._project_x(rx_b - mg, d)
            cx = self._project_x(cx_b, d)
            return (lx,y),(rx,y),(cx,y)

        lt,rt,_ = corners(db)
        lb,rb,_ = corners(df)

        dark = tuple(max(0,int(c*0.5)) for c in color)
        pygame.draw.polygon(self.screen, dark, [lt,rt,rb,lb])

        # Gradient strips
        steps = max(2,(lb[1]-lt[1])//5)
        for s in range(steps):
            t0,t1 = s/steps,(s+1)/steps
            l0,r0,_ = corners(lerp(df,db,t0))
            l1,r1,_ = corners(lerp(df,db,t1))
            pygame.draw.polygon(self.screen, lerpC(color,dark,t0),[l1,r1,r0,l0])

        bright = tuple(min(255,int(c*1.7)) for c in color)
        pygame.draw.line(self.screen, bright, lb, rb, 3)
        pygame.draw.line(self.screen, bright, lt, lb, 1)
        pygame.draw.line(self.screen, bright, rt, rb, 1)

        if not blk:
            edge_col = (200,200,220)
        else:
            edge_col = tuple(min(255,int(c*1.4)) for c in color)
        pygame.draw.line(self.screen, edge_col, lt, lb, 1)

        tip_cx = (lb[0]+rb[0])//2
        tip_cy = lb[1] - 2
        lbl_color = (15,15,15) if not blk else (200,200,220)
        lbl = self.fn_note.render(pitch_name(pitch), True, lbl_color)
        dx = tip_cx - lbl.get_width()//2
        dy = tip_cy - lbl.get_height()
        if 0<=dx<self.W and 0<=dy<self.H:
            self.screen.blit(lbl,(dx,dy))

    # ── Hit zone ──────────────────────────────────────────────────
    def _draw_hit_zone(self, lpm: List[int], dt: float):
        p2i = {p:i for i,p in enumerate(lpm)}
        y = self.HIT_Y

        for p in self._all_pitches:
            lx_b,rx_b,cx_b = self._pitch_bounds(p)
            lx = self._project_x(lx_b, 0.0)
            rx = self._project_x(rx_b, 0.0)
            cx = self._project_x(cx_b, 0.0)
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
    def _draw_keyboard(self, lpm: List[int], pressed: set = None):
        if not self._kb_keys: return
        pressed = pressed or set()
        active = set(lpm)
        p2i = {p:i for i,p in enumerate(lpm)}

        # Use keyboard layout (not highway) for keyboard bounds
        lx0_b = self._kb_layout[self._all_pitches[0]][0]
        rxN_b = self._kb_layout[self._all_pitches[-1]][1]

        pygame.draw.rect(self.screen,(6,6,16),
            pygame.Rect(lx0_b, self.PIANO_Y, rxN_b-lx0_b, self.PIANO_H))

        # White keys — cyan highlight when pressed
        for rect,blk,p in self._kb_keys:
            if blk: continue
            is_pressed = p in pressed
            fill = (120,240,255) if is_pressed else (225,225,225)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            if not is_pressed:
                sh=pygame.Surface((rect.w,min(rect.h//3,18)),pygame.SRCALPHA)
                for gg in range(sh.get_height()):
                    a=int(45*(1-gg/sh.get_height()))
                    pygame.draw.line(sh,(0,0,0,a),(0,gg),(sh.get_width(),gg))
                self.screen.blit(sh,(rect.x,rect.y))
            border = (0,200,220) if is_pressed else (80,80,90)
            pygame.draw.rect(self.screen, border, rect, 2 if is_pressed else 1, border_radius=3)
            if rect.h>30:
                lbl_col = (0,40,60) if is_pressed else (70,70,80)
                lbl=self.fn_key_lbl.render(pitch_name(p),True,lbl_col)
                self.screen.blit(lbl,(rect.centerx-lbl.get_width()//2,
                                     rect.bottom-lbl.get_height()-3))

        # Black keys — cyan when pressed
        for rect,blk,p in self._kb_keys:
            if not blk: continue
            is_pressed = p in pressed
            fill = (0,160,200) if is_pressed else (20,20,20)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            if not is_pressed:
                pygame.draw.line(self.screen,(55,55,55),(rect.x+1,rect.y+2),(rect.x+1,rect.bottom-3),1)
            border = (0,230,255) if is_pressed else (50,50,50)
            pygame.draw.rect(self.screen, border, rect, 1, border_radius=3)

        pygame.draw.line(self.screen,NEON_CYAN,
            (lx0_b,self.PIANO_Y),(rxN_b,self.PIANO_Y),2)

        # Show pressed key names above keyboard
        if pressed:
            NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
            names = []
            for p in sorted(pressed):
                if p in self._kb_layout:
                    oct_ = p//12 - 1
                    names.append(f"{NOTE_NAMES[p%12]}{oct_}")
            if names:
                label = "  ".join(names)
                ks = self.fn_hud_md.render(label, True, NEON_CYAN)
                kx = (lx0_b+rxN_b)//2 - ks.get_width()//2
                ky = self.PIANO_Y - ks.get_height() - 6
                bg = pygame.Surface((ks.get_width()+16, ks.get_height()+4), pygame.SRCALPHA)
                bg.fill((0,0,0,170))
                self.screen.blit(bg, (kx-8, ky-2))
                self.screen.blit(ks, (kx, ky))

    # ── Particles ─────────────────────────────────────────────────
    def _update_particles(self, dt):
        self.particles=[p for p in self.particles if (p.update(dt) or True) and p.alive]
        for p in self.particles: p.draw(self.screen)

    def spawn_hit_particles(self, li, n, color, quality):
        if li >= len(self._layout_pitches): return
        pitch = self._layout_pitches[li]
        lx_b,rx_b,cx_b = self._pitch_bounds(pitch)
        cx = self._project_x(cx_b, 0.0); y = self.HIT_Y
        count={"PERFECT":24,"GREAT":14,"GOOD":7,"GODLIKE":35}.get(quality,4)
        rng=random.Random()
        for _ in range(count):
            ang=rng.uniform(-math.pi,0); spd=rng.uniform(80,310)
            bright=tuple(min(255,int(c*1.5)) for c in color)
            self.particles.append(Particle(cx,y,bright,
                math.cos(ang)*spd,math.sin(ang)*spd,rng.uniform(0.3,0.9),rng.randint(3,8)))
        self.hit_flashes[li]=(color,0.18)

    def spawn_miss_particles(self, li, n):
        if li >= len(self._layout_pitches): return
        pitch = self._layout_pitches[li]
        lx_b,rx_b,cx_b = self._pitch_bounds(pitch)
        cx=self._project_x(cx_b,0.0); rng=random.Random()
        for _ in range(7):
            ang=rng.uniform(-math.pi,0); spd=rng.uniform(35,130)
            self.particles.append(Particle(cx,self.HIT_Y,(215,20,20),
                math.cos(ang)*spd,math.sin(ang)*spd,0.4,3))
        self.miss_flashes[li]=0.22

    def _draw_multiplier_glow(self, multiplier: int):
        """Dashed bright border lines on strike zone at x4/x8."""
        if not self._all_pitches: return
        lx_b,_,_ = self._pitch_bounds(self._all_pitches[0])
        _,rx_b,_ = self._pitch_bounds(self._all_pitches[-1])
        lxf = self._project_x(lx_b, 0.0); rxf = self._project_x(rx_b, 0.0)
        y   = self.HIT_Y
        col = (0,200,255) if multiplier >= 8 else (60,100,220)
        tz_half = int(self.H * 0.018)
        seg, gap = 10, 14
        for sx in range(lxf, rxf, seg + gap):
            ex = min(sx + seg, rxf)
            pygame.draw.line(self.screen, col, (sx, y - tz_half), (ex, y - tz_half), 2)
            pygame.draw.line(self.screen, col, (sx, y + tz_half), (ex, y + tz_half), 2)


    # ── HUD ───────────────────────────────────────────────────────
    def draw_hud(self, score, combo, multiplier, accuracy, streak,
                 xp, level, xp_progress, song_progress, mode, last_hit_quality=""):
        W,H = self.W,self.H
        hud_y_bottom = self.PIANO_Y - self.PIANO_H - 8   # above keyboard

        sc=self.fn_hud_lg.render(f"{score:,}",True,NEON_CYAN)
        self.screen.blit(sc,(16,28))
        self.screen.blit(self.fn_hud_sm.render("SCORE",True,GRAY),(18,28+sc.get_height()))

        if combo>1:
            cc=NEON_YELLOW if combo<10 else (NEON_PINK if combo<25 else NEON_GREEN)
            cs=self.fn_hud_lg.render(f"x{combo}",True,cc)
            self.screen.blit(cs,(W//2-cs.get_width()//2,10))
            ms=self.fn_hud_sm.render(f"MULT x{multiplier}",True,cc)
            self.screen.blit(ms,(W//2-ms.get_width()//2,10+cs.get_height()))

        ac=NEON_GREEN if accuracy>=90 else (NEON_YELLOW if accuracy>=70 else NEON_ORANGE)
        as_=self.fn_hud_lg.render(f"{accuracy:.1f}%",True,ac)
        self.screen.blit(as_,(W-as_.get_width()-16,10))
        self.screen.blit(self.fn_hud_sm.render("ACCURACY",True,GRAY),
                         (W-self.fn_hud_sm.size("ACCURACY")[0]-16,10+as_.get_height()))

        if streak>=5:
            ss=self.fn_hud_sm.render(f"STREAK  {streak}",True,NEON_ORANGE)
            self.screen.blit(ss,(W-ss.get_width()-16,10+as_.get_height()+18))

        # Song progress bar — between bottom tz line and piano roll top
        bar_h = 7
        tz_half = int(self.H * 0.018)
        gap_top    = self.HIT_Y + tz_half      # bottom of strike zone
        gap_bottom = self.PIANO_Y              # top of piano roll
        gap_mid    = (gap_top + gap_bottom) // 2
        bar_y = gap_mid - bar_h // 2           # centered in the gap
        pw=int(W*0.55); px=W//2-pw//2

        # Background
        pygame.draw.rect(self.screen, (8,8,20), (px,bar_y,pw,bar_h), border_radius=3)

        # Fill (song progress in cyan)
        fw=int(pw*song_progress)
        if fw>0: pygame.draw.rect(self.screen,NEON_CYAN,(px,bar_y,fw,bar_h),border_radius=3)

        pygame.draw.rect(self.screen,GRAY,(px,bar_y,pw,bar_h),1,border_radius=3)

        # Red line = fixed F-grade threshold at 62% of bar
        f_threshold = 0.62
        f_x = px + int(pw * f_threshold)
        pygame.draw.line(self.screen, (220,30,30),
                         (f_x, bar_y-2), (f_x, bar_y+bar_h+2), 2)

        # Accuracy line = current accuracy mapped to bar width (0-100% -> 0-pw)
        # At 62% accuracy it exactly meets the red line; above it passes, below stays behind
        acc_x = px + int(pw * min(accuracy / 100.0, 1.0))
        pip_col = NEON_GREEN if accuracy >= f_threshold*100 else (255,80,80)
        pygame.draw.line(self.screen, (0,0,0),
                         (acc_x, bar_y-1), (acc_x, bar_y+bar_h+1), 3)
        pygame.draw.line(self.screen, pip_col,
                         (acc_x, bar_y), (acc_x, bar_y+bar_h), 1)

        # Mode badge bottom-right
        mc={MODE_EASY:NEON_GREEN,MODE_HARD:NEON_RED,MODE_TESTING:NEON_ORANGE}.get(mode,GRAY)
        ms2=self.fn_hud_md.render(f"◆ {mode}",True,mc)
        self.screen.blit(ms2,(W-ms2.get_width()-12, bar_y - ms2.get_height() - 2))

        self._last_multiplier = multiplier  # cache for hit zone color

        if last_hit_quality:
            qc={"PERFECT":NEON_CYAN,"GREAT":NEON_GREEN,"GOOD":NEON_YELLOW,
                "MISS":NEON_RED,"GODLIKE":(255,220,0)}.get(last_hit_quality,WHITE)
            qs=self.fn_quality.render(last_hit_quality,True,qc)
            qx=W//2-qs.get_width()//2; qy=int(H*0.36)
            sh=self.fn_quality.render(last_hit_quality,True,(0,0,0))
            self.screen.blit(sh,(qx+2,qy+2)); self.screen.blit(qs,(qx,qy))
