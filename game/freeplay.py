"""
KeyFall - Free Play
A full interactive piano you can just play. No song, no scoring.
Shows key name labels, octave markers, sustain simulation.
"""

import math
import pygame
from game.constants import *

NOTE_NAMES  = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
BLACK_SEMI  = {1,3,6,8,10}

def is_black(p): return (p%12) in BLACK_SEMI
def pitch_name(p):
    n = NOTE_NAMES[p%12]
    oct_ = p//12 - 1
    return f"{n}{oct_}"

# Full 88-key piano: A0(21) → C8(108)
PIANO_LOW  = 21
PIANO_HIGH = 108


class FreePlay:
    """Fullscreen interactive piano — play any note, no rules."""

    # keyboard mapping: key → MIDI pitch (C4 = 60 layout)
    KB_MAP = {
        # Bottom row: Z=C4, X=D4 ... M=E5
        pygame.K_z: 60, pygame.K_s: 61, pygame.K_x: 62,
        pygame.K_d: 63, pygame.K_c: 64, pygame.K_v: 65,
        pygame.K_g: 66, pygame.K_b: 67, pygame.K_h: 68,
        pygame.K_n: 69, pygame.K_j: 70, pygame.K_m: 71,
        # Top row: Q=C5 ...
        pygame.K_q: 72, pygame.K_2: 73, pygame.K_w: 74,
        pygame.K_3: 75, pygame.K_e: 76, pygame.K_r: 77,
        pygame.K_5: 78, pygame.K_t: 79, pygame.K_6: 80,
        pygame.K_y: 81, pygame.K_7: 82, pygame.K_u: 83,
        pygame.K_i: 84, pygame.K_9: 85, pygame.K_o: 86,
        pygame.K_0: 87, pygame.K_p: 88,
    }

    def __init__(self, screen: pygame.Surface, audio_manager):
        self.screen  = screen
        self.audio   = audio_manager
        self._held        = set()   # pitches held by QWERTY/MIDI
        self._mouse_pitch = None   # pitch currently held by mouse click
        self._flashes     = {}     # pitch → timer (for visual flash)
        self._tick        = 0.0
        self._octave_shift = 0
        self._sustain      = False
        self._sustained    = set()
        self._mouse_moved  = False  # track if mouse moved since last click
        self._rebuild()

    def _rebuild(self):
        W, H = self.screen.get_width(), self.screen.get_height()
        self.W, self.H = W, H
        # Piano occupies bottom 22% of screen
        self.PIANO_Y = int(H * 0.78)
        self.PIANO_H = H - self.PIANO_Y
        self._build_key_rects()
        self._init_fonts()

    def _init_fonts(self):
        s = self.H / 720
        self.fn_title  = pygame.font.SysFont("consolas", max(18, int(36*s)), bold=True)
        self.fn_note   = pygame.font.SysFont("consolas", max(10, int(18*s)), bold=True)
        self.fn_small  = pygame.font.SysFont("consolas", max(9,  int(14*s)))
        self.fn_label  = pygame.font.SysFont("consolas", max(8,  int(12*s)))
        self.fn_hint   = pygame.font.SysFont("consolas", max(9,  int(13*s)))

    def _build_key_rects(self):
        """Build pixel rects for all 88 keys."""
        whites = [p for p in range(PIANO_LOW, PIANO_HIGH+1) if not is_black(p)]
        n_w = len(whites)
        ww  = self.W / n_w
        bw  = ww * 0.58
        bh  = self.PIANO_H * 0.60

        self._white_rects = {}
        self._black_rects = {}
        self._white_order = whites

        for i, p in enumerate(whites):
            x = int(i * ww)
            w = int((i+1)*ww) - x
            self._white_rects[p] = pygame.Rect(x, self.PIANO_Y, w, self.PIANO_H)

        for p in range(PIANO_LOW, PIANO_HIGH+1):
            if not is_black(p):
                continue
            # Find white neighbours
            lw = p-1 if p-1 >= PIANO_LOW and not is_black(p-1) else None
            rw = p+1 if p+1 <= PIANO_HIGH and not is_black(p+1) else None
            if lw and lw in self._white_rects:
                lr = self._white_rects[lw]
                cx = lr.right - int(bw*0.3)
            elif rw and rw in self._white_rects:
                rr = self._white_rects[rw]
                cx = rr.left + int(bw*0.3)
            else:
                continue
            bx = cx - int(bw//2)
            self._black_rects[p] = pygame.Rect(bx, self.PIANO_Y, int(bw), int(bh))

    def _active_pitches(self):
        return self._held | self._sustained

    def handle_event(self, event) -> str:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return "back"
            if event.key == pygame.K_F11:
                return "fullscreen"
            # Octave shift
            if event.key == pygame.K_LEFT:
                self._octave_shift = max(-3, self._octave_shift - 1)
                return None
            if event.key == pygame.K_RIGHT:
                self._octave_shift = min(3, self._octave_shift + 1)
                return None
            # Sustain pedal (space)
            if event.key == pygame.K_SPACE:
                self._sustain = True
                self._sustained = set(self._held)
                return None
            # Note on from keyboard
            pitch = self._kb_pitch(event.key)
            if pitch and pitch not in self._held:
                self._held.add(pitch)
                self._flashes[pitch] = 0.4
                self.audio.play_note(pitch, 90)

        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_SPACE:
                self._sustain = False
                self._sustained.clear()
                return None
            pitch = self._kb_pitch(event.key)
            if pitch:
                self._held.discard(pitch)

        elif event.type == pygame.MOUSEMOTION:
            # Mouse moved — always show cursor
            self._mouse_moved = True
            if self._mouse_pitch is not None:
                new_pitch = self._pitch_at(event.pos)
                if new_pitch != self._mouse_pitch:
                    # Release old key
                    self._held.discard(self._mouse_pitch)
                    # Trigger new key if dragged onto one
                    if new_pitch is not None:
                        self._mouse_pitch = new_pitch
                        self._held.add(new_pitch)
                        self._flashes[new_pitch] = 0.3
                        self.audio.play_note(new_pitch, 80)
                    else:
                        self._mouse_pitch = None

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pitch = self._pitch_at(event.pos)
            if pitch is not None:
                self._mouse_pitch = pitch
                self._held.add(pitch)
                self._flashes[pitch] = 0.4
                self.audio.play_note(pitch, 90)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            # Always release mouse pitch on mouse up, regardless of position
            if self._mouse_pitch is not None:
                self._held.discard(self._mouse_pitch)
                self._mouse_pitch = None

        return None

    def _kb_pitch(self, key):
        base = self.KB_MAP.get(key)
        if base is None:
            return None
        p = base + self._octave_shift * 12
        if PIANO_LOW <= p <= PIANO_HIGH:
            return p
        return None

    def _pitch_at(self, pos):
        """Return pitch under mouse position (black keys take priority)."""
        for p, r in self._black_rects.items():
            if r.collidepoint(pos):
                return p
        for p, r in self._white_rects.items():
            if r.collidepoint(pos):
                return p
        return None

    def _is_pitch_at(self, pos, pitch):
        """Check if a specific pitch is under the given position."""
        r = self._black_rects.get(pitch) or self._white_rects.get(pitch)
        return r is not None and r.collidepoint(pos)

    def update(self, dt):
        self._tick += dt
        # Decay flashes
        for p in list(self._flashes):
            self._flashes[p] -= dt
            if self._flashes[p] <= 0:
                del self._flashes[p]

    def draw(self):
        W, H = self.W, self.H
        # Rebuild on resize
        if W != self.screen.get_width() or H != self.screen.get_height():
            self.W, self.H = self.screen.get_width(), self.screen.get_height()
            self._rebuild()
            W, H = self.W, self.H

        active = self._active_pitches()

        # ── Background ───────────────────────────────────────────
        self.screen.fill(DARK_BG)
        for i in range(10):
            off = (self._tick*22 + i*85) % H
            pygame.draw.line(self.screen, (0,15,12), (0,int(off)), (W,int(off)), 1)

        # ── Title area ───────────────────────────────────────────
        title = self.fn_title.render("FREE PLAY", True, NEON_CYAN)
        self.screen.blit(title, (W//2 - title.get_width()//2, int(H*0.04)))

        # Show held note names
        if active:
            names = [pitch_name(p) for p in sorted(active)]
            chord = "  ".join(names)
            cs = self.fn_title.render(chord, True, (255,255,255))
            self.screen.blit(cs, (W//2 - cs.get_width()//2, int(H*0.13)))

        # Sustain indicator
        if self._sustain:
            ss = self.fn_small.render("SUSTAIN ON", True, NEON_YELLOW)
            self.screen.blit(ss, (W - ss.get_width() - 20, int(H*0.06)))

        # Octave indicator
        shift_txt = f"OCT  {'+'if self._octave_shift>=0 else ''}{self._octave_shift}"
        os_ = self.fn_small.render(shift_txt, True, NEON_PURPLE)
        self.screen.blit(os_, (20, int(H*0.06)))

        # ── Visualizer: floating circles for held notes ───────────
        vis_h = self.PIANO_Y - int(H*0.25)
        vis_y = int(H*0.25)
        if active and vis_h > 20:
            pygame.draw.rect(self.screen, (8,8,20),
                             pygame.Rect(0, vis_y, W, vis_h))
            all_whites = self._white_order
            n_w = len(all_whites)
            ww  = W / n_w
            for p in active:
                # x position from keyboard
                if p in self._white_rects:
                    px = self._white_rects[p].centerx
                elif p in self._black_rects:
                    px = self._black_rects[p].centerx
                else:
                    continue
                # y position based on pitch height
                frac = (p - PIANO_LOW) / (PIANO_HIGH - PIANO_LOW)
                py = vis_y + int((1-frac) * vis_h * 0.7) + int(vis_h*0.15)
                # Pulsing size
                fl = self._flashes.get(p, 0)
                sz = int(18 + fl * 20)
                # Color based on note
                hue = (p * 137) % 360
                r_ = int(128 + 127*math.sin(math.radians(hue)))
                g_ = int(128 + 127*math.sin(math.radians(hue+120)))
                b_ = int(128 + 127*math.sin(math.radians(hue+240)))
                col = (r_, g_, b_)
                # Glow rings
                for ring in range(3, 0, -1):
                    a = int(60 / ring)
                    gs = pygame.Surface((sz*2+ring*8, sz*2+ring*8), pygame.SRCALPHA)
                    pygame.draw.circle(gs, (*col, a),
                                       (sz+ring*4, sz+ring*4), sz+ring*4)
                    self.screen.blit(gs, (px-sz-ring*4, py-sz-ring*4),
                                     special_flags=pygame.BLEND_ADD)
                pygame.draw.circle(self.screen, col, (px, py), sz)
                # Note name inside circle
                lbl = self.fn_label.render(NOTE_NAMES[p%12], True, (0,0,0))
                self.screen.blit(lbl, (px-lbl.get_width()//2, py-lbl.get_height()//2))

        # ── Piano keyboard ────────────────────────────────────────
        # Background bar
        pygame.draw.rect(self.screen, (8,8,18),
                         pygame.Rect(0, self.PIANO_Y, W, self.PIANO_H))
        pygame.draw.line(self.screen, NEON_CYAN, (0, self.PIANO_Y), (W, self.PIANO_Y), 2)

        # White keys
        for p, rect in self._white_rects.items():
            pressed = p in active
            if pressed:
                fill = (100, 220, 255)
                border = (0, 200, 230)
            else:
                fill = (220, 220, 225)
                border = (60, 60, 80)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            if not pressed:
                # Subtle shadow at top
                sh = pygame.Surface((rect.w, 10), pygame.SRCALPHA)
                sh.fill((0,0,0,40))
                self.screen.blit(sh, (rect.x, rect.y))
            pygame.draw.rect(self.screen, border, rect, 1, border_radius=3)
            # C labels
            if p % 12 == 0:
                oct_ = p//12 - 1
                lbl = self.fn_label.render(f"C{oct_}", True,
                                           (0,40,60) if pressed else (80,80,100))
                self.screen.blit(lbl, (rect.centerx - lbl.get_width()//2,
                                       rect.bottom - lbl.get_height() - 3))
            # Highlight if mapped to keyboard key
            if self._is_kb_mapped(p) and not pressed:
                dot = pygame.Surface((6,6), pygame.SRCALPHA)
                pygame.draw.circle(dot, (0,180,200,140), (3,3), 3)
                self.screen.blit(dot, (rect.centerx-3, rect.bottom-18))

        # Black keys
        for p, rect in self._black_rects.items():
            pressed = p in active
            if pressed:
                fill = (0, 150, 200)
                border = (0, 220, 255)
            else:
                fill = (18, 18, 24)
                border = (45, 45,  60)
            pygame.draw.rect(self.screen, fill, rect, border_radius=3)
            pygame.draw.rect(self.screen, border, rect, 1, border_radius=3)

        # ── Hints ────────────────────────────────────────────────
        hints = [
            "Mouse: Click keys",
            "Z-M / Q-P: Play notes",
            "← →: Octave shift",
            "SPACE: Sustain",
            "ESC: Back",
        ]
        hx = 20
        hy = int(H * 0.38)
        for h in hints:
            hs = self.fn_hint.render(h, True, (50,50,70))
            self.screen.blit(hs, (hx, hy))
            hy += hs.get_height() + 3

    def _is_kb_mapped(self, pitch):
        """Check if this pitch (at current octave shift) is mapped to a key."""
        for key, base in self.KB_MAP.items():
            if base + self._octave_shift * 12 == pitch:
                return True
        return False
