"""
KeyFall - Free Play
An 88-key piano to play freely: no song, no score.

Play it with the mouse, with the computer keys marked on the piano, or with a MIDI keyboard.
Every note rises from its key as a neon bar (dimmer while only the sustain pedal holds it),
the notes that are sounding and the chord they make are named at the top, and the header
shows the octave the computer keys play, the sustain pedal, what plays the sound and whether
a MIDI keyboard is connected.

Drawing stays cheap however many notes sound at once: the keyboard at rest, every lit key
and each bar's fade and rounded ends are pre-rendered sprites, and the note names are laid
out only when the notes change.
"""

import math

import pygame

from game import ui
from game.constants import NEON_CYAN, NEON_GREEN, NEON_ORANGE, NEON_YELLOW

NOTE_NAMES = ui.NOTE_NAMES
BLACK_SEMI = {1, 3, 6, 8, 10}

# Full 88-key piano: A0 (21) .. C8 (108)
PIANO_LOW = 21
PIANO_HIGH = 108

MAX_BARS = 256        # rising note bars kept at once (the oldest finished ones go first)
BAR_SECONDS = 3.0     # time a bar takes to rise from the keys to where it has faded out
LEVELS = 20           # brightness steps of the bars (each step has its own cached sprites)
FLASH_STEPS = 4       # brightness steps of the flash on a key that was just pressed
OCTAVE_COLOR = (190, 110, 255)
KB_BG = (6, 6, 16)    # the gaps between the keys

# Black keys sit off-centre like on a real piano: C# and F# left of the gap between their
# white neighbours, D# and A# right of it, G# in the middle (in white-key widths).
_BLACK_OFFSET = {1: -0.10, 3: 0.10, 6: -0.14, 8: 0.0, 10: 0.14}

# Computer keys and the pitch each plays at octave shift 0: the bottom row is C4-B4 and the
# top row C5-E6, with the black keys on the row above each (S D G H J and 2 3 5 6 7 9 0).
_KB = (
    ("Z", pygame.K_z, 60), ("S", pygame.K_s, 61), ("X", pygame.K_x, 62),
    ("D", pygame.K_d, 63), ("C", pygame.K_c, 64), ("V", pygame.K_v, 65),
    ("G", pygame.K_g, 66), ("B", pygame.K_b, 67), ("H", pygame.K_h, 68),
    ("N", pygame.K_n, 69), ("J", pygame.K_j, 70), ("M", pygame.K_m, 71),
    ("Q", pygame.K_q, 72), ("2", pygame.K_2, 73), ("W", pygame.K_w, 74),
    ("3", pygame.K_3, 75), ("E", pygame.K_e, 76), ("R", pygame.K_r, 77),
    ("5", pygame.K_5, 78), ("T", pygame.K_t, 79), ("6", pygame.K_6, 80),
    ("Y", pygame.K_y, 81), ("7", pygame.K_7, 82), ("U", pygame.K_u, 83),
    ("I", pygame.K_i, 84), ("9", pygame.K_9, 85), ("O", pygame.K_o, 86),
    ("0", pygame.K_0, 87), ("P", pygame.K_p, 88),
)

# (the first two only explain: they're not buttons. A click on SPACE turns the pedal on/off)
HINTS = [("CLICK", "Play", None), (("Z", "X", "C"), "Letters on the piano", None),
         (("←", "→"), "Octave"), ("SPACE", "Sustain pedal"), ("ESC", "Back")]


def is_black(p):
    return (p % 12) in BLACK_SEMI


def pitch_name(p):
    """'C4', 'F#3', ..."""
    return ui.note_name(p)


# ── Naming what is played ─────────────────────────────────────────
# Chord shapes as intervals above the root, most common first (the first match wins)
_CHORDS = (
    ((0, 4, 7), "{} MAJOR"),
    ((0, 3, 7), "{} MINOR"),
    ((0, 4, 7, 10), "{}7"),
    ((0, 4, 7, 11), "{} MAJOR 7"),
    ((0, 3, 7, 10), "{} MINOR 7"),
    ((0, 3, 6), "{} DIMINISHED"),
    ((0, 4, 8), "{} AUGMENTED"),
    ((0, 2, 7), "{} SUS2"),
    ((0, 5, 7), "{} SUS4"),
    ((0, 4, 10), "{}7"),                 # sevenths are often played without the fifth
    ((0, 4, 11), "{} MAJOR 7"),
    ((0, 3, 10), "{} MINOR 7"),
    ((0, 3, 6, 10), "{} HALF-DIMINISHED"),
    ((0, 3, 6, 9), "{} DIMINISHED 7"),
    ((0, 4, 7, 9), "{}6"),
    ((0, 3, 7, 9), "{} MINOR 6"),
    ((0, 5, 7, 10), "{}7 SUS4"),
    ((0, 2, 4, 7), "{} ADD9"),
    ((0, 2, 3, 7), "{} MINOR ADD9"),
    ((0, 3, 7, 11), "{} MINOR-MAJOR 7"),
    ((0, 2, 4, 7, 10), "{}9"),
    ((0, 2, 4, 7, 11), "{} MAJOR 9"),
    ((0, 2, 3, 7, 10), "{} MINOR 9"),
)
_SHAPES = {}
for _rank, (_shape, _name) in enumerate(_CHORDS):
    _SHAPES.setdefault(frozenset(_shape), _rank)

_SIMPLE = ("UNISON", "MINOR 2ND", "MAJOR 2ND", "MINOR 3RD", "MAJOR 3RD", "PERFECT 4TH",
           "TRITONE", "PERFECT 5TH", "MINOR 6TH", "MAJOR 6TH", "MINOR 7TH", "MAJOR 7TH")
_COMPOUND = ("MINOR 9TH", "MAJOR 9TH", "MINOR 10TH", "MAJOR 10TH", "PERFECT 11TH",
             "AUGMENTED 11TH", "PERFECT 12TH", "MINOR 13TH", "MAJOR 13TH")


def interval_name(d):
    """The interval between two notes d semitones apart."""
    if d % 12 == 0:
        return "UNISON" if d == 0 else "OCTAVE" if d == 12 else f"{d // 12} OCTAVES"
    if d < 12:
        return _SIMPLE[d]
    if d <= 21:
        return _COMPOUND[d - 13]
    n = d // 12
    return f"{_SIMPLE[d % 12]} + {'OCTAVE' if n == 1 else f'{n} OCTAVES'}"


def chord_name(pitches):
    """What the sounding notes make: an interval for two notes, a chord for three or more
    (with the bass note after a slash when it isn't the root), or '' when it has no name."""
    ps = sorted(pitches)
    if len(ps) < 2:
        return ""
    pcs = {p % 12 for p in ps}
    bass = ps[0] % 12
    if len(pcs) == 1:
        return interval_name(ps[1] - ps[0]) if len(ps) == 2 else "OCTAVES"
    if len(pcs) == 2:
        if len(ps) == 2:
            return interval_name(ps[1] - ps[0])
        return _SIMPLE[((pcs - {bass}).pop() - bass) % 12]
    best = None
    for root in pcs:
        rank = _SHAPES.get(frozenset((pc - root) % 12 for pc in pcs))
        if rank is not None:
            cand = (root != bass, rank, root)     # a root in the bass wins, then commonness
            if best is None or cand < best:
                best = cand
    if best is None:
        return ""
    _, rank, root = best
    name = _CHORDS[rank][1].format(NOTE_NAMES[root])
    return name if root == bass else f"{name} / {NOTE_NAMES[bass]}"


class FreePlay:
    """Fullscreen interactive piano: play any note, no rules."""

    KB_MAP = {key: pitch for _, key, pitch in _KB}       # computer key -> pitch at shift 0

    def __init__(self, screen: pygame.Surface, audio_manager, midi_connected=False):
        self.screen = screen
        self.audio = audio_manager
        self.midi_connected = midi_connected   # the app keeps this up to date
        self._held = set()          # pitches held down (computer keys, mouse or MIDI)
        self._sustained = set()     # let go while the sustain pedal is down: still ringing
        self._mouse_pitch = None    # pitch held by the mouse button
        self._key_pitch = {}        # computer key -> the pitch it started (the octave may
                                    # change before the key comes up)
        self._flashes = {}          # pitch -> seconds of extra brightness after a press
        self._octave_shift = 0
        self._sustain = False
        self._space_sustain = False  # the pedal is down because SPACE is held
        self._typing = False        # playing on computer keys or MIDI: the pointer hides
        self._played = False        # the "how to play" card shows until the first note
        self._prompt = 1.0          # that card's opacity (fades out after the first note)
        self._tick = 0.0
        self._bars = []             # [pitch, t_on, t_key_up, t_end, level, tail level],
                                    # oldest first
        self._open = {}             # pitch -> its bar while the note sounds
        self._mouse_pos = None
        self._map_shift = None
        self._size = None
        self._rebuild()

    # ── Layout ────────────────────────────────────────────────────
    def _rebuild(self):
        W, H = self.screen.get_size()
        self._size = (W, H)
        self.W, self.H = W, H
        s = self.s = ui.scale_for(W, H)
        self.m = int(24 * s)
        self.head_h = int(72 * s)
        self.foot = ui.footer_rect(W, H, s)
        self.PIANO_H = max(60, min(int(150 * s), int(H * 0.3)))
        self.PIANO_Y = self.foot.y - self.PIANO_H
        self._build_key_rects()
        # Bars rise from the keys and fade out before they reach the names at the top
        self._fade_top = min(self.head_h + int(104 * s), self.PIANO_Y - int(60 * s))
        self._fade_bot = max(self._fade_top + 1,
                             min(self._fade_top + int(130 * s), self.PIANO_Y - int(30 * s)))
        self._speed = max(30.0, (self.PIANO_Y - self._fade_top) / BAR_SECONDS)
        self._bar_rad = max(2, int(4 * s))
        self._lbl_px = max(9, int(10 * s))
        self._glow_size = (max(8, int(self._ww * 3.2)), max(8, int(72 * s)))
        # Sprites for this size (made as they are first needed)
        self._caps, self._shadows, self._glows = {}, {}, {}
        self._fades, self._ends, self._bar_cols, self._key_sprites = {}, {}, {}, {}
        self._fade_cols, self._end_shapes = {}, {}
        self._guide = None
        self._kb_surf = self._kb_key = None
        self._np = (None, None)     # (notes, layout) of the names shown at the top

    def _build_key_rects(self):
        """Pixel rects for all 88 keys, edge to edge across the window."""
        whites = [p for p in range(PIANO_LOW, PIANO_HIGH + 1) if not is_black(p)]
        ww = self.W / len(whites)
        bw = max(3, int(ww * 0.58))
        self._bh = int(self.PIANO_H * 0.62)
        y, h = self.PIANO_Y, self.PIANO_H
        self._ww = ww
        self._white_rects, self._black_rects = {}, {}
        for i, p in enumerate(whites):
            x = int(i * ww)
            self._white_rects[p] = pygame.Rect(x, y, int((i + 1) * ww) - x, h)
        for p in range(PIANO_LOW, PIANO_HIGH + 1):
            if is_black(p):     # p - 1 is always its white neighbour on the left
                cx = self._white_rects[p - 1].right + _BLACK_OFFSET[p % 12] * ww
                self._black_rects[p] = pygame.Rect(int(round(cx - bw / 2)), y, bw, self._bh)
        # Where each note's bar rises: over the middle of its key, a little narrower
        self._bar_x = {}
        for p, r in self._white_rects.items():
            w = max(2, int(ww * 0.56))
            self._bar_x[p] = (r.centerx - w // 2, w)
        for p, r in self._black_rects.items():
            w = max(2, int(bw * 0.78))
            self._bar_x[p] = (r.centerx - w // 2, w)
        self._c_lines = [r.x for p, r in self._white_rects.items() if p % 12 == 0]

    # ── Input ─────────────────────────────────────────────────────
    def handle_event(self, event):
        et = event.type
        if et == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_ESCAPE:
                self.set_sustain(False)
                return "back"
            if k == pygame.K_F11:
                return "fullscreen"
            if k in (pygame.K_LEFT, pygame.K_RIGHT):       # which octave the letters play
                step = -1 if k == pygame.K_LEFT else 1
                self._octave_shift = max(-3, min(3, self._octave_shift + step))
                return None
            if k == pygame.K_SPACE:                        # sustain pedal
                if getattr(event, "clicked", False):       # the SPACE hint: on / off
                    self._space_sustain = not self._space_sustain
                    self.set_sustain(self._space_sustain)
                elif not self._space_sustain:
                    self._space_sustain = True
                    self.set_sustain(True)
                return None
            pitch = self._kb_pitch(k)
            if pitch is not None and k not in self._key_pitch:
                self._key_pitch[k] = pitch
                self._typing = True
                self.press(pitch, 90)

        elif et == pygame.KEYUP:
            if event.key == pygame.K_SPACE:
                if self._space_sustain:
                    self._space_sustain = False
                    self.set_sustain(False)
                return None
            pitch = self._key_pitch.pop(event.key, None)   # the pitch this key started
            if pitch is not None:
                self.release(pitch)

        elif et == pygame.MOUSEMOTION:
            self._mouse_pos = event.pos
            self._typing = False
            if self._mouse_pitch is not None:   # dragging across the keys plays each one
                new = self._pitch_at(event.pos)
                if new != self._mouse_pitch:
                    self.release(self._mouse_pitch)
                    self._mouse_pitch = new
                    if new is not None:
                        self.press(new, 80, flash=0.3)

        elif et == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._mouse_pos = event.pos
            self._typing = False
            pitch = self._pitch_at(event.pos)
            if pitch is not None:
                self._mouse_pitch = pitch
                self.press(pitch, 90)

        elif et == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._mouse_pitch is not None:     # wherever the pointer is now
                self.release(self._mouse_pitch)
                self._mouse_pitch = None

        elif et == pygame.WINDOWLEAVE:
            self._mouse_pos = None

        elif et == pygame.WINDOWFOCUSLOST:
            # Key-ups don't arrive once the window loses focus: let go of what it held
            for pitch in self._key_pitch.values():
                self.release(pitch)
            self._key_pitch.clear()
            if self._mouse_pitch is not None:
                self.release(self._mouse_pitch)
                self._mouse_pitch = None
            if self._space_sustain:
                self._space_sustain = False
                self.set_sustain(False)
        return None

    @property
    def cursor_visible(self):
        """The pointer hides while you play on the computer keys or a MIDI keyboard and
        comes back as soon as the mouse moves."""
        return not self._typing

    # ── Key state (computer keys, mouse and MIDI all go through these) ──
    def press(self, pitch, velocity, flash=0.4, sound=True):
        """A key goes down. MIDI notes have already sounded, so they come with sound=False."""
        self._held.add(pitch)
        self._sustained.discard(pitch)
        self._flashes[pitch] = flash
        self._played = True
        if not sound:
            self._typing = True
        self._end_bar(pitch)
        vel = max(1, min(127, int(velocity or 90)))
        lvl = int((0.6 + 0.4 * vel / 127) * LEVELS + 0.5)     # harder hits glow brighter
        bar = [pitch, self._tick, None, None, lvl, max(1, int(lvl * 0.45 + 0.5))]
        self._bars.append(bar)
        self._open[pitch] = bar
        if len(self._bars) > MAX_BARS:
            for i, b in enumerate(self._bars):
                if b[3] is not None:
                    del self._bars[i]
                    break
        if sound:
            self.audio.note_on(pitch, velocity)

    def release(self, pitch, sound=True):
        was_held = pitch in self._held
        self._held.discard(pitch)
        if not self._sustain:
            self._end_bar(pitch)
        elif was_held:
            self._sustained.add(pitch)     # keeps ringing (and lit) until the pedal goes up
            bar = self._open.get(pitch)
            if bar is not None and bar[2] is None:
                bar[2] = self._tick
        if sound:
            self.audio.note_off(pitch)

    def set_sustain(self, down, sound=True):
        """The sustain pedal: SPACE or a MIDI keyboard's pedal."""
        self._sustain = down
        if not down:
            for p in self._sustained:
                if p not in self._held:
                    self._end_bar(p)
            self._sustained.clear()
        if sound:
            self.audio.set_sustain(down)

    def _end_bar(self, pitch):
        bar = self._open.pop(pitch, None)
        if bar is not None:
            if bar[2] is None:
                bar[2] = self._tick
            bar[3] = self._tick

    def _kb_pitch(self, key):
        base = self.KB_MAP.get(key)
        if base is None:
            return None
        p = base + self._octave_shift * 12
        return p if PIANO_LOW <= p <= PIANO_HIGH else None

    def _mapped(self):
        """pitch -> computer key letter, for the current octave shift."""
        if self._map_shift != self._octave_shift:
            self._map = {}
            for label, _, base in _KB:
                p = base + self._octave_shift * 12
                if PIANO_LOW <= p <= PIANO_HIGH:
                    self._map[p] = label
            keys = sorted(self._map)
            self._map_label = f"OCTAVE {self._octave_shift:+d}" + (
                f" · {pitch_name(keys[0])}–{pitch_name(keys[-1])}" if keys else "")
            self._map_shift = self._octave_shift
        return self._map

    def _pitch_at(self, pos):
        """Pitch under a point (black keys first: they lie on top)."""
        if pos is None or not (self.PIANO_Y <= pos[1] < self.PIANO_Y + self.PIANO_H):
            return None
        for p, r in self._black_rects.items():
            if r.collidepoint(pos):
                return p
        for p, r in self._white_rects.items():
            if r.collidepoint(pos):
                return p
        return None

    def _active_pitches(self):
        return self._held | self._sustained

    def update(self, dt):
        self._tick += dt
        if self._flashes:
            for p in list(self._flashes):
                self._flashes[p] -= dt
                if self._flashes[p] <= 0:
                    del self._flashes[p]
        if self._played and self._prompt > 0:
            self._prompt = max(0.0, self._prompt - dt / 0.35)

    # ── Drawing ───────────────────────────────────────────────────
    def draw(self):
        if self.screen.get_size() != self._size:
            self._rebuild()
        surf = self.screen
        active = self._active_pitches()
        ui.backdrop(surf, self._tick)
        self._draw_guides(surf)
        if active:
            self._draw_glows(surf, active)
        self._draw_bars(surf)
        self._draw_keyboard(surf, active)
        if active:
            self._draw_now_playing(surf, active)
        if self._prompt > 0:
            self._draw_prompt(surf)
        self._draw_header(surf)
        ui.footer(surf, self.s, HINTS)

    def _draw_header(self, surf):
        s, m, W = self.s, self.m, self.W
        cy = self.head_h // 2 + int(2 * s)
        tr = ui.draw_text(surf, "FREE PLAY", int(30 * s), NEON_CYAN, (m, cy), bold=True,
                          anchor="midleft", shadow=True)
        self._mapped()
        r = ui.pill(surf, self._map_label, OCTAVE_COLOR, (tr.right + int(14 * s), cy), s,
                    anchor="midleft")
        x = r.right + int(8 * s)
        if self._sustain:
            r = ui.pill(surf, "SUSTAIN ON", NEON_YELLOW, (x, cy), s, anchor="midleft",
                        filled=True)
        else:
            r = ui.pill(surf, "SUSTAIN OFF", ui.TEXT_DIM, (x, cy), s, anchor="midleft")
        left_end = r.right + int(16 * s)

        col = NEON_GREEN if self.midi_connected else NEON_ORANGE
        mr = ui.pill(surf, "MIDI CONNECTED" if self.midi_connected else "NO MIDI KEYBOARD", col,
                     (W - m, cy), s, anchor="midright", dot=True)
        txt, scol, busy = ui.sound_summary(self.audio)
        px = max(9, int(13 * s))
        x1 = mr.x - int(16 * s)
        dot = int(16 * s)
        if txt and x1 - dot - left_end > int(70 * s):
            tr = ui.draw_text(surf, ui.fit(txt, px, x1 - dot - left_end), px, ui.TEXT_MUTED,
                              (x1, cy), anchor="midright")
            if busy:
                ui.spinner(surf, (tr.x - int(10 * s), cy), max(4, int(6 * s)), scol, self._tick)
            else:
                ui.status_dot(surf, (tr.x - int(10 * s), cy), scol, s)
        pygame.draw.line(surf, ui.EDGE, (m, self.head_h - 1), (W - m, self.head_h - 1))

    def _draw_guides(self, surf):
        """Faint lines up from every C, so a bar is easy to trace back to its key."""
        top, h = self._fade_top, self.PIANO_Y - self._fade_top
        if h <= 0:
            return
        g = self._guide
        if g is None:
            g = self._guide = pygame.Surface((1, h), pygame.SRCALPHA)
            fz = max(1, self._fade_bot - top)
            for y in range(h):
                g.set_at((0, y), (90, 90, 150, int(44 * min(1.0, y / fz))))
        for x in self._c_lines:
            surf.blit(g, (x, top))

    def _glow(self, col):
        """Soft light above a sounding key (added onto the background)."""
        g = self._glows.get(col)
        if g is None:
            sw, sh = 16, 8
            small = pygame.Surface((sw, sh))
            for yy in range(sh):
                for xx in range(sw):
                    u = (xx + 0.5) / sw * 2 - 1
                    v = 1 - (yy + 0.5) / sh
                    k = max(0.0, 1 - math.hypot(u, v)) ** 2 * 0.5
                    small.set_at((xx, yy), (int(col[0] * k), int(col[1] * k), int(col[2] * k)))
            g = self._glows[col] = pygame.transform.smoothscale(small, self._glow_size)
        return g

    def _draw_glows(self, surf, active):
        gw, gh = self._glow_size
        y = self.PIANO_Y - gh
        for p in active:
            x, w = self._bar_x[p]
            surf.blit(self._glow(ui.pitch_color(p)), (x + w // 2 - gw // 2, y),
                      special_flags=pygame.BLEND_RGB_ADD)

    # ── Rising bars ───────────────────────────────────────────────
    def _draw_bars(self, surf):
        """Each note as a bar rising from its key: bright while the key is held, dimmer
        while only the pedal holds it, brighter for harder hits; fading out near the top."""
        if not self._bars:
            return
        base, top, now, v = self.PIANO_Y, self._fade_top, self._tick, self._speed
        keep, blacks = [], []
        for b in self._bars:
            y_end = base if b[3] is None else base - (now - b[3]) * v
            if y_end > top:                  # (otherwise it has risen out of sight)
                keep.append(b)
                if b[0] % 12 in BLACK_SEMI:
                    blacks.append((b, y_end))
                else:
                    self._draw_bar(surf, b, y_end)
        self._bars = keep
        for b, y_end in blacks:              # black keys' bars on top, like the keys
            self._draw_bar(surf, b, y_end)

    def _draw_bar(self, surf, b, y_end):
        p, t0, t1, _, lvl, tail_lvl = b
        x, w = self._bar_x[p]
        col = ui.pitch_color(p)
        base, now, v = self.PIANO_Y, self._tick, self._speed
        y0 = base - (now - t0) * v
        detached = y_end < base - 0.5
        if t1 is not None:
            y1 = base - (now - t1) * v
            if y1 < y_end - 1:               # the pedal kept it ringing after the key-up
                self._bar_part(surf, x, w, y0, y1, col, lvl, True, False)
                self._bar_part(surf, x, w, y1, y_end, col, tail_lvl, False, detached)
                return
        self._bar_part(surf, x, w, y0, y_end, col, lvl, True, detached)

    def _bar_part(self, surf, x, w, ya, yb, col, lvl, cap_top, cap_bottom):
        """One stretch of a bar from ya (top) down to yb. cap_top / cap_bottom: that end is
        an end of the whole bar (rounded); otherwise the stretch runs on seamlessly into the
        next one or into the key. Across the fade band it is a slice of a pre-faded sprite."""
        top, fb = self._fade_top, self._fade_bot
        if ya < top:                           # its top has risen out of sight
            ya, cap_top = top, False
        ia, ib = int(ya), int(yb)
        if ib <= ia:
            return
        edge = False                           # a capped stretch a pixel or two high
        caps = cap_top + cap_bottom
        if caps:
            # Rounded ends: smaller on a very short stretch, square on one a pixel high
            rad = min(self._end_rad(w), (ib - ia - 1) // caps)
            if rad > 0:
                if cap_top:
                    self._draw_end(surf, x, w, ia, col, lvl, rad, True)
                    ia += rad
                if cap_bottom:
                    ib -= rad
                    self._draw_end(surf, x, w, ib, col, lvl, rad, False)
            else:
                edge = True
        if ia < fb:                                    # fading out toward the top
            b = min(ib, fb)
            surf.blit(self._fade_sprite(col, w, lvl), (x, ia), (0, ia - top, w, b - ia))
            ia = b
        if ib > ia:
            rim, body = self._bar_style(col, lvl)
            surf.fill(rim, (x, ia, w, ib - ia))
            if w > 2 and not edge:
                surf.fill(body, (x + 1, ia, w - 2, ib - ia))

    def _end_rad(self, w):
        return max(1, min(self._bar_rad, w // 2))

    def _bar_style(self, col, lvl):
        """(rim, body) colours of a bar at brightness level lvl."""
        key = (col, lvl)
        st = self._bar_cols.get(key)
        if st is None:
            k = lvl / LEVELS
            st = self._bar_cols[key] = (ui.shade(col, k), ui.shade(col, k * 0.55))
        return st

    def _fade_rows(self, col, lvl):
        """(rim, body) colours of each row of the fade band, darkening toward the top, then
        full brightness for a few rows below it (a rounded end can reach past the band)."""
        key = (col, lvl)
        rows = self._fade_cols.get(key)
        if rows is None:
            rim, body = self._bar_style(col, lvl)
            h = self._fade_bot - self._fade_top
            more = self._bar_rad + 1
            rows = self._fade_cols[key] = (
                [ui.shade(rim, (y + 0.5) / h) for y in range(h)] + [rim] * more,
                [ui.shade(body, (y + 0.5) / h) for y in range(h)] + [body] * more)
        return rows

    def _fade_sprite(self, col, w, lvl):
        """A bar's stretch across the fade band, darkening smoothly toward the top."""
        key = (col, w, lvl)
        spr = self._fades.get(key)
        if spr is None:
            rims, bodies = self._fade_rows(col, lvl)
            h = self._fade_bot - self._fade_top
            spr = pygame.Surface((w, h))
            for y in range(h):
                spr.fill(rims[y], (0, y, w, 1))
                if w > 2:
                    spr.fill(bodies[y], (1, y, w - 2, 1))
            self._fades[key] = spr
        return spr

    def _end_shape(self, w, rad):
        """A bar's rounded top end row by row: ((rim from, to), (body from, to) or None), as
        pygame draws a rounded rect. The end sprites and the ends drawn row by row inside
        the fade band both follow it, so an end keeps its shape as it rises into the band."""
        key = (w, rad)
        shape = self._end_shapes.get(key)
        if shape is None:
            full = pygame.Surface((w, 2 * rad + 2), pygame.SRCALPHA)
            r = full.get_rect()
            pygame.draw.rect(full, (255, 0, 0), r, border_radius=rad)
            if w > 2:
                pygame.draw.rect(full, (0, 255, 0), r.inflate(-2, -2),
                                 border_radius=max(0, rad - 1))
            shape = []
            for y in range(rad):
                rim = [x for x in range(w) if full.get_at((x, y)).a]
                body = [x for x in range(w) if full.get_at((x, y)).g]
                shape.append(((rim[0], rim[-1] + 1) if rim else (0, 0),
                              (body[0], body[-1] + 1) if body else None))
            self._end_shapes[key] = shape
        return shape

    def _end_sprite(self, col, w, lvl, rad, top):
        """A bar's rounded top or bottom end (see-through outside the curve)."""
        key = (col, w, lvl, rad, top)
        spr = self._ends.get(key)
        if spr is None:
            rim, body = self._bar_style(col, lvl)
            spr = pygame.Surface((w, rad), pygame.SRCALPHA)
            for i, ((a, b), bs) in enumerate(self._end_shape(w, rad)):
                y = i if top else rad - 1 - i
                spr.fill(rim, (a, y, b - a, 1))
                if bs:
                    spr.fill(body, (bs[0], y, bs[1] - bs[0], 1))
            self._ends[key] = spr
        return spr

    def _draw_end(self, surf, x, w, y, col, lvl, rad, top):
        """A bar's rounded top or bottom end, rad rows from y down."""
        if y >= self._fade_bot:
            surf.blit(self._end_sprite(col, w, lvl, rad, top), (x, y))
            return
        rims, bodies = self._fade_rows(col, lvl)      # inside the fade band: row by row
        shape = self._end_shape(w, rad)
        r = y - self._fade_top
        for i in range(rad):
            (a, b), bs = shape[i] if top else shape[rad - 1 - i]
            surf.fill(rims[r + i], (x + a, y + i, b - a, 1))
            if bs:
                surf.fill(bodies[r + i], (x + bs[0], y + i, bs[1] - bs[0], 1))

    # ── Keyboard ──────────────────────────────────────────────────
    def _shadow(self, w, h):
        """Top-edge shading for a white key at rest (cached per size)."""
        sh = self._shadows.get((w, h))
        if sh is None:
            sh = self._shadows[(w, h)] = pygame.Surface((w, h), pygame.SRCALPHA)
            for yy in range(h):
                pygame.draw.line(sh, (0, 0, 0, int(45 * (1 - yy / h))), (0, yy), (w, yy))
        return sh

    def _cap(self, letter, black):
        """Small keycap with the computer key that plays a piano key."""
        key = (letter, black)
        cap = self._caps.get(key)
        if cap is None:
            fg, bg, edge = (((214, 214, 230), (44, 44, 62), (96, 96, 122)) if black else
                            ((46, 46, 70), (206, 206, 218), (140, 140, 162)))
            t = ui.font(self._lbl_px, True).render(letter, True, fg)
            h = t.get_height() + 2
            cap = pygame.Surface((max(h, t.get_width() + 6), h), pygame.SRCALPHA)
            pygame.draw.rect(cap, bg, cap.get_rect(), border_radius=3)
            pygame.draw.rect(cap, edge, cap.get_rect(), 1, border_radius=3)
            cap.blit(t, t.get_rect(center=cap.get_rect().center))
            self._caps[key] = cap
        return cap

    def _draw_white(self, surf, p, r, col=None, hovered=False, flash=0.0):
        if col is not None:                                  # sounding
            fill = ui.mix((225, 225, 225), col, 0.5 + 0.3 * flash)
            border, lcol, bw = ui.shade(col, 0.7), ui.shade(col, 0.25), 2
        elif hovered:                                        # under the pointer
            fill, border, lcol, bw = (196, 232, 238), (40, 170, 200), (40, 70, 80), 2
        else:
            fill, border, lcol, bw = (225, 225, 225), (80, 80, 90), (70, 70, 80), 1
        pygame.draw.rect(surf, fill, r, border_radius=3)
        if col is None:
            surf.blit(self._shadow(r.w, max(1, min(r.h // 3, int(18 * self.s)))), r.topleft)
        pygame.draw.rect(surf, border, r, bw, border_radius=3)
        if col is not None or p % 12 == 0:      # every C keeps its octave number
            lbl = ui.text(pitch_name(p), self._lbl_px, lcol, True)
            if lbl.get_width() > r.w - 2:
                lbl = ui.text(NOTE_NAMES[p % 12], self._lbl_px, lcol, True)
            surf.blit(lbl, (r.centerx - lbl.get_width() // 2, r.bottom - lbl.get_height() - 3))
        letter = self._mapped().get(p)
        if letter:
            cap = self._cap(letter, False)
            if cap.get_width() <= r.w - 2:
                low = r.bottom - ui.font(self._lbl_px, True).get_height() - 4
                cy = (r.y + self._bh + low) // 2       # below the black keys, above the name
                surf.blit(cap, cap.get_rect(center=(r.centerx, cy)))

    def _draw_black(self, surf, p, r, col=None, hovered=False, flash=0.0):
        if col is not None:
            fill, border = ui.shade(col, 0.72 + 0.25 * flash), col
        elif hovered:
            fill, border = (30, 62, 74), (40, 170, 200)
        else:
            fill, border = (20, 20, 20), (50, 50, 50)
        pygame.draw.rect(surf, fill, r, border_radius=3)
        if col is None and not hovered:
            pygame.draw.line(surf, (55, 55, 55), (r.x + 1, r.y + 2), (r.x + 1, r.bottom - 3), 1)
        pygame.draw.rect(surf, border, r, 1, border_radius=3)
        if col is not None:
            for txt in (pitch_name(p), NOTE_NAMES[p % 12]):
                lbl = ui.text(txt, self._lbl_px, (10, 10, 22), True)
                if lbl.get_width() <= r.w - 2:
                    surf.blit(lbl, (r.centerx - lbl.get_width() // 2,
                                    r.bottom - lbl.get_height() - 3))
                    break
        else:
            letter = self._mapped().get(p)
            if letter:
                cap = self._cap(letter, True)
                if cap.get_width() <= r.w + 2:
                    surf.blit(cap, cap.get_rect(midbottom=(r.centerx, r.bottom - 3)))

    def _keyboard(self):
        """The keyboard at rest, with its labels and keycaps (redrawn when they change)."""
        key = (self._size, self._octave_shift)
        if self._kb_key != key:
            surf = pygame.Surface((self.W, self.PIANO_H))
            surf.fill(KB_BG)
            dy = -self.PIANO_Y
            for p, r in self._white_rects.items():
                self._draw_white(surf, p, r.move(0, dy))
            for p, r in self._black_rects.items():
                self._draw_black(surf, p, r.move(0, dy))
            self._kb_surf, self._kb_key = surf, key
        return self._kb_surf

    def _key_sprite(self, p, flash=None):
        """A key as drawn: sounding (flash = 0..FLASH_STEPS) or at rest (None), with its
        keycap. White keys are opaque; black ones stay see-through outside their corners."""
        letter = self._mapped().get(p)
        key = (p, flash, letter)
        spr = self._key_sprites.get(key)
        if spr is None:
            if len(self._key_sprites) > 400:
                self._key_sprites.clear()
            col = None if flash is None else ui.pitch_color(p)
            f = 0.0 if flash is None else flash / FLASH_STEPS
            r = self._black_rects.get(p)
            if r is not None:
                spr = pygame.Surface(r.size, pygame.SRCALPHA)
                self._draw_black(spr, p, spr.get_rect(), col, False, f)
            else:
                spr = pygame.Surface(self._white_rects[p].size)
                spr.fill(KB_BG)
                self._draw_white(spr, p, spr.get_rect(), col, False, f)
            self._key_sprites[key] = spr
        return spr

    def _flash_step(self, p):
        f = self._flashes.get(p)
        return 0 if f is None else min(FLASH_STEPS, int(f / 0.4 * FLASH_STEPS + 0.5))

    def _draw_keyboard(self, surf, active):
        y = self.PIANO_Y
        surf.blit(self._keyboard(), (0, y))
        hover = self._pitch_at(self._mouse_pos) if self.cursor_visible else None
        if hover in active:
            hover = None
        whites, blacks = self._white_rects, self._black_rects
        redo = set()                 # black keys to draw again over the redrawn white keys
        for p in active:
            r = whites.get(p)
            if r is None:
                redo.add(p)
            else:
                surf.blit(self._key_sprite(p, self._flash_step(p)), r)
                redo.update((p - 1, p + 1))
        if hover is not None:
            r = whites.get(hover)
            if r is None:
                redo.add(hover)
            else:
                self._draw_white(surf, hover, r, hovered=True)
                redo.update((hover - 1, hover + 1))
        for p in redo:
            r = blacks.get(p)
            if r is None:
                continue
            if p in active:
                surf.blit(self._key_sprite(p, self._flash_step(p)), r)
            elif p == hover:
                self._draw_black(surf, p, r, hovered=True)
            else:
                surf.blit(self._key_sprite(p), r)
        # Neon edge along the top, lit in each sounding key's colour
        pygame.draw.line(surf, NEON_CYAN, (0, y), (self.W, y), 2)
        for p in active:
            r = blacks.get(p) or whites[p]
            surf.fill(ui.pitch_color(p), (r.x, y - 1, r.w, 3))

    # ── Names of what is playing / first-time help ────────────────
    def _draw_now_playing(self, surf, active):
        held = self._held
        notes = tuple([(p, p in held) for p in sorted(active)])
        if self._np[0] != notes:
            self._np = (notes, self._layout_names(notes))
        px, y, items, more, chord, pill_y = self._np[1]
        for name, col, x in items:
            ui.draw_text(surf, name, px, col, (x, y), bold=True, shadow=True)
        if more:
            ui.draw_text(surf, more[0], px, ui.TEXT_MUTED, (more[1], y), bold=True)
        if chord:
            ui.pill(surf, chord, NEON_CYAN, (self.W // 2, pill_y), self.s,
                    px=max(9, int(15 * self.s)), anchor="midtop")

    def _layout_names(self, notes):
        """Where the sounding notes' names go: the biggest size that fits, then '+N' for
        any that still don't; dimmer when only the pedal holds a note. Also the chord they
        make. Worked out only when the notes change."""
        s, W = self.s, self.W
        n = len(notes)
        names = [pitch_name(p) for p, _ in notes]
        max_w = W - 2 * self.m
        for px in (int(34 * s), int(26 * s), int(20 * s)):
            gap = ui.text_w("  ", px, True)
            widths = [ui.text_w(nm, px, True) for nm in names]
            if sum(widths) + gap * (n - 1) <= max_w:
                k = n
                break
        else:
            k, run = 1, widths[0]
            for i in range(1, n):            # as many as fit next to "+N" for the rest
                run += gap + widths[i]
                if run + gap + ui.text_w(f"+{n - i - 1}", px, True) > max_w:
                    break
                k = i + 1
        row = sum(widths[:k]) + gap * (k - 1)
        if k < n:
            row += gap + ui.text_w(f"+{n - k}", px, True)
        y = self.head_h + int(18 * s)
        x = W // 2 - row // 2
        items = []
        for i in range(k):
            p, is_held = notes[i]
            col = ui.pitch_color(p)
            items.append((names[i], col if is_held else ui.shade(col, 0.55), x))
            x += widths[i] + gap
        more = (f"+{n - k}", x) if k < n else None
        pill_y = y + ui.font(px, True).get_height() + int(8 * s)
        return px, y, items, more, chord_name([p for p, _ in notes]), pill_y

    def _draw_prompt(self, surf):
        """How to play, until the first note (then it fades away)."""
        s = self.s
        a = round(self._prompt * 6) / 6        # a few steps keep the text cache small
        if a <= 0:
            return
        px1, px2 = int(24 * s), max(9, int(15 * s))
        line = "Click a key, type the letters shown on the piano, or use a MIDI keyboard."
        lines = ui.wrap(line, px2, self.W - 4 * self.m, max_lines=2)
        lh2 = ui.font(px2).get_linesize()
        isz = int(26 * s)
        h = int(22 * s) + isz + int(12 * s) + ui.font(px1, True).get_height() + int(8 * s) \
            + lh2 * len(lines) + int(22 * s)
        w = max(ui.text_w(ln, px2) for ln in lines) + int(64 * s)
        box = pygame.Rect(0, 0, min(self.W - 2 * self.m, w), h)
        box.center = (self.W // 2, (self.head_h + self.PIANO_Y) // 2)
        ui.panel(surf, box, alpha=int(215 * a), border=ui.mix(ui.PANEL, ui.EDGE, a))
        y = box.y + int(22 * s)
        ui.icon_note(surf, pygame.Rect(box.centerx - isz // 2, y, isz, isz),
                     ui.mix(ui.PANEL, NEON_CYAN, a))
        y += isz + int(12 * s)
        r = ui.draw_text(surf, "Play anything", px1, ui.mix(ui.PANEL, ui.TEXT, a),
                         (box.centerx, y), bold=True, anchor="midtop")
        y = r.bottom + int(8 * s)
        for ln in lines:
            ui.draw_text(surf, ln, px2, ui.mix(ui.PANEL, ui.TEXT_MUTED, a), (box.centerx, y),
                         anchor="midtop")
            y += lh2
