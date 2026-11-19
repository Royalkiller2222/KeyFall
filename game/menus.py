"""
KeyFall - menus: main menu, song select and results.

Everything is drawn with the shared kit in game.ui, so all screens share one look:
translucent rounded panels, neon accents, Consolas text and keycap hints.
"""

import math
import os
import subprocess
import sys
import zlib
from typing import List, Optional

import pygame

from game import ui
from game.constants import (DEFAULT_REVERB, LANE_COLORS, MODE_TESTING, NEON_CYAN, NEON_GREEN,
                            NEON_ORANGE, NEON_PINK, NEON_PURPLE, NEON_RED, NEON_YELLOW,
                            SONGS_DIR)
from game.song_library import DIFFICULTY_COLORS, DIFFICULTY_ORDER, SongEntry

COVER_NAMES = ("cover.png", "cover.jpg", "cover.jpeg", "art.png", "art.jpg")


def _ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


def _sfx(audio, name):
    if audio:
        audio.play_sfx(name)


class MenuBase:
    def __init__(self, screen):
        self.screen = screen
        self.W, self.H = screen.get_size()
        self._tick = 0.0
        self._mouse = None        # last mouse position this screen saw (for hover)

    @property
    def s(self):
        return ui.scale_for(self.W, self.H)

    def update(self, dt):
        self._tick += dt

    def _sync_size(self):
        self.W, self.H = self.screen.get_size()

    def track_mouse(self, event):
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self._mouse = event.pos

    def hovering(self, rect):
        return self._mouse is not None and rect.collidepoint(self._mouse)

    def draw_bg(self):
        self._sync_size()
        ui.backdrop(self.screen, self._tick)


# ── Main menu ─────────────────────────────────────────────────────
class MainMenu(MenuBase):
    OPTIONS = ["PLAY", "FREE PLAY", "SETTINGS", "QUIT"]
    DESCRIPTIONS = {
        "PLAY":      "Pick a song and learn it on the falling-note highway",
        "FREE PLAY": "Play the piano freely - nothing is scored",
        "SETTINGS":  "Volume, instrument sound, game mode and highway view",
        "QUIT":      "Close KeyFall",
    }

    def __init__(self, screen, midi_ports, level, total_xp, level_progress, audio=None,
                 song_count=None):
        super().__init__(screen)
        self.midi_ports = midi_ports or []
        self.level, self.total_xp, self.level_progress = level, total_xp, level_progress
        self.audio = audio
        self.song_count = song_count
        self.selected = 0
        self.options = list(self.OPTIONS)
        self._notes = ui.FallingNotes(18, seed=11)

    def _btn_rect(self, i):
        s = self.s
        bw, bh, step = int(360 * s), max(30, int(56 * s)), max(36, int(70 * s))
        return pygame.Rect(self.W // 2 - bw // 2, int(self.H * 0.40) + i * step, bw, bh)

    def _btn_at(self, pos):
        for i in range(len(self.options)):
            if self._btn_rect(i).collidepoint(pos):
                return i
        return None

    def _move(self, d):
        self.selected = (self.selected + d) % len(self.options)
        _sfx(self.audio, "hover")

    def handle_event(self, event) -> Optional[str]:
        self.track_mouse(event)
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self._move(-1)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._move(1)
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self.options[self.selected].lower()
        elif event.type == pygame.MOUSEMOTION:
            i = self._btn_at(event.pos)
            if i is not None and i != self.selected:
                self.selected = i
                _sfx(self.audio, "hover")
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            i = self._btn_at(event.pos)
            if i is not None:
                self.selected = i
                return self.options[i].lower()
        return None

    def draw(self):
        self.draw_bg()
        surf, W, H, s, t = self.screen, self.W, self.H, self.s, self._tick
        self._notes.draw(surf, t, s)

        y = int(H * 0.10)
        lh = ui.logo(surf, W // 2, y, int(96 * s), t)
        self._subtitle(W // 2, y + lh + int(4 * s))

        for i, opt in enumerate(self.options):
            r = self._btn_rect(i)
            ui.button(surf, r, opt, s, NEON_RED if opt == "QUIT" else NEON_CYAN,
                      selected=(i == self.selected), hovered=self.hovering(r), t=t,
                      px=int(24 * s), markers=True)
        last = self._btn_rect(len(self.options) - 1)
        ui.draw_text(surf, self.DESCRIPTIONS.get(self.options[self.selected], ""), int(15 * s),
                     ui.TEXT_MUTED, (W // 2, last.bottom + int(20 * s)), anchor="midtop")

        foot = ui.footer(surf, s, [(("↑", "↓"), "Select"), ("ENTER", "Open"),
                                   ("F11", "Fullscreen")])
        self._status_row(foot.y - int(24 * s))

    def _subtitle(self, cx, y):
        surf, s = self.screen, self.s
        px = max(11, int(20 * s))
        words = ["MIDI", "KEYBOARD", "LEARNING", "GAME"]
        sep = ui.text_w("  ", px, True)
        widths = [ui.text_w(w, px, True) for w in words]
        total = sum(widths) + sep * (len(words) - 1)
        band = pygame.Rect(0, 0, total + int(32 * s), ui.font(px, True).get_height() + int(8 * s))
        band.midtop = (cx, y - int(4 * s))
        ui.panel(surf, band, fill=(70, 0, 52), alpha=60, border=None, radius=band.h // 2,
                 top_hi=False)
        x = cx - total // 2
        for i, (word, ww) in enumerate(zip(words, widths)):
            ui.draw_text(surf, word, px, NEON_PINK if i % 2 == 0 else (200, 80, 255), (x, y),
                         bold=True, shadow=True)
            x += ww + sep

    def _status_items(self, px):
        items = []    # (kind, text, colour); kind: dot / spin / note
        s = self.s
        if self.midi_ports:
            items.append(("dot", ui.fit(f"MIDI: {self.midi_ports[0]}", px, int(280 * s)),
                          NEON_GREEN))
        else:
            items.append(("dot", "No MIDI keyboard - computer keys work too", NEON_ORANGE))
        if self.song_count is not None:
            n = self.song_count
            items.append(("note", f"{n} song{'s' if n != 1 else ''}", ui.TEXT_MUTED))
        snd, col, busy = ui.sound_summary(self.audio)
        if snd:
            items.append(("spin" if busy else "dot", snd, col))
        music = self.audio.music_loading_status if self.audio else ""
        if music:
            items.append(("spin", music.replace("...", "…"), NEON_CYAN))
        return items

    def _status_row(self, cy):
        """MIDI, library and sound status in one centred row, split by hairlines."""
        surf, s = self.screen, self.s
        px = max(9, int(13 * s))
        isz = max(8, int(12 * s))
        ig = max(4, int(7 * s))
        sep = max(8, int(16 * s))
        items = self._status_items(px)
        widths = [isz + ig + ui.text_w(txt, px) for _, txt, _ in items]
        x = self.W // 2 - (sum(widths) + sep * 2 * (len(items) - 1)) // 2
        for n, ((kind, txt, col), w) in enumerate(zip(items, widths)):
            if n:
                x += sep
                pygame.draw.line(surf, ui.EDGE, (x, cy - isz // 2 - 2), (x, cy + isz // 2 + 2))
                x += sep
            c = (x + isz // 2, cy)
            if kind == "dot":
                ui.status_dot(surf, c, col, s)
            elif kind == "spin":
                ui.spinner(surf, c, isz // 2, col, self._tick)
            else:
                ui.icon_note(surf, pygame.Rect(x, cy - isz // 2, isz, isz), col)
            ui.draw_text(surf, txt, px, col, (x + isz + ig, cy), anchor="midleft")
            x += w


# ── Song select ───────────────────────────────────────────────────
class SongSelectMenu(MenuBase):
    """Song list on the left, the chosen song's details and play options on the right."""
    PREVIEW_DELAY = 0.5

    def __init__(self, screen, entries: List[SongEntry], current_mode: str,
                 midi_connected: bool, audio=None, pb_lookup=None, fx_lookup=None,
                 fx_store=None):
        super().__init__(screen)
        self.entries = entries
        self.selected = 0
        self.mode = current_mode
        self.midi_connected = midi_connected
        self.audio = audio
        self.pb_lookup = pb_lookup        # (song, mode, speed) -> best leaderboard entry or None
        self.fx_lookup = fx_lookup        # song key -> {"reverb": %, "sustain": bool}
        self.fx_store = fx_store          # (song key, reverb %, sustain): keeps a song's sound
        self._fx_drag = False             # dragging the REVERB knob
        self._reverb_box = None           # REVERB slider and its track, from the last draw
        self._reverb_track = None
        self._fit = (None, None)          # (key, sizes) of the details column
        self.VISIBLE = 7                  # cards that fit; recomputed from the window size
        self.scroll_offset = 0
        self._diff_sel = {}               # entry index -> chosen difficulty
        self._speeds = [0.25, 0.5, 0.75, 1.0]
        self._speed_idx = 3
        # song preview
        self._prev_idx = -1
        self._prev_diff = None
        self._prev_timer = 0.0
        self._prev_note_i = 0
        self._prev_t = 0.0
        # drawing state
        self._cover_cache = {}
        self._roll_cache = {}
        self._hl_y = None                 # animated y of the selection frame
        self._dt = 1 / 120
        self._hits = []                   # (rect, action, arg) clickable areas from the last draw
        self._head_free = (0, 0)          # free x-range in the header (for the toast)
        self._refresh_cb = None           # set by the app: rescans the songs folder
        self._notif = ""
        self._notif_timer = 0.0

    # ── state helpers ─────────────────────────────────────────────
    def _entry_diff(self, idx: int) -> str:
        d = self._diff_sel.get(idx)
        if d is None:
            avail = self.entries[idx].available_difficulties
            d = self._diff_sel[idx] = avail[0] if avail else "MEDIUM"   # easiest available
        return d

    def set_entries(self, entries: List[SongEntry]):
        """New library after a rescan: keep the selected song when it is still there."""
        cur = (self.entries[self.selected]
               if self.entries and 0 <= self.selected < len(self.entries) else None)
        self.entries = entries
        self._diff_sel = {}
        self._cover_cache.clear()
        self._roll_cache.clear()
        self.selected = 0
        if cur is not None:
            for i, e in enumerate(entries):
                if e.folder == cur.folder and e.title == cur.title:
                    self.selected = i
                    break
        self.scroll_offset = 0
        self._ensure_visible()
        self._prev_idx = -1               # restarts the preview
        self._hl_y = None

    def _ensure_visible(self):
        vis = max(1, self.VISIBLE)
        if self.selected < self.scroll_offset:
            self.scroll_offset = self.selected
        elif self.selected >= self.scroll_offset + vis:
            self.scroll_offset = self.selected - vis + 1
        self.scroll_offset = max(0, min(self.scroll_offset, max(0, len(self.entries) - vis)))

    def _select(self, idx):
        if not self.entries:
            return
        idx = max(0, min(len(self.entries) - 1, idx))
        if idx != self.selected:
            self.selected = idx
            _sfx(self.audio, "hover")
        self._ensure_visible()

    def _step_diff(self, d):
        avail = self.entries[self.selected].available_difficulties
        if len(avail) < 2:
            return
        cur = self._entry_diff(self.selected)
        i = avail.index(cur) if cur in avail else 0
        self._diff_sel[self.selected] = avail[(i + d) % len(avail)]
        _sfx(self.audio, "click")

    def _step_mode(self, d):
        modes = ui.MODES
        i = modes.index(self.mode) if self.mode in modes else 0
        self.mode = modes[(i + d) % len(modes)]
        _sfx(self.audio, "click")

    def _step_speed(self, d):
        i = max(0, min(len(self._speeds) - 1, self._speed_idx + d))
        if i != self._speed_idx:
            self._speed_idx = i
            _sfx(self.audio, "click")

    # ── the song's sound: reverb and sustain, saved per song ──────
    def _fx_key(self):
        """Every difficulty of a song shares its options. They are kept under the title its
        charts carry (the folder name), like the leaderboard."""
        e = self.entries[self.selected]
        song = next(iter(e.difficulties.values()), None)
        return song.title if song else e.title

    def _fx(self):
        if self.entries and self.fx_lookup:
            return self.fx_lookup(self._fx_key())
        return {"reverb": DEFAULT_REVERB, "sustain": False}

    def _set_fx(self, reverb=None, sustain=None, sound=True):
        if not self.entries:
            return
        cur = self._fx()
        r = cur["reverb"] if reverb is None else max(0, min(100, int(round(reverb))))
        su = cur["sustain"] if sustain is None else bool(sustain)
        if (r, su) == (cur["reverb"], cur["sustain"]):
            return
        if self.fx_store:
            self.fx_store(self._fx_key(), r, su)
        if self.audio:
            self.audio.set_song_fx(r / 100, su)   # the preview plays with it right away
        if sound:
            _sfx(self.audio, "click")

    def _step_reverb(self, d):
        """Keys and wheel: to the next 5 % mark that way."""
        r = self._fx()["reverb"]
        self._set_fx(reverb=(r // 5 + 1) * 5 if d > 0 else (r - 1) // 5 * 5)

    def _drag_reverb(self, pos):
        tr = self._reverb_track
        if tr and tr.w > 0:
            self._set_fx(reverb=(pos[0] - tr.x) / tr.w * 100, sound=False)

    def _reverb_note(self):
        """Why the reverb isn't heard with the instrument in use (None when it is)."""
        a = self.audio
        if a is None or a.has_reverb:
            return None
        if a.note_sound_mode == "midi_out":
            return "no output device"
        return "needs FluidSynth" if a.note_sound_mode == "soundfont" else "needs SOUNDFONT"

    def _play(self):
        if not self.entries:
            return None
        song = self.entries[self.selected].get_song(self._entry_diff(self.selected))
        if song:
            return ("play", song, self.mode, self._speeds[self._speed_idx])
        return None

    def _toast(self, msg):
        self._notif, self._notif_timer = msg, 2.5

    def _refresh(self):
        if self._refresh_cb:
            self._refresh_cb()            # the app rescans and calls set_entries()
        n = len(self.entries)
        self._toast(f"Library refreshed - {n} song{'s' if n != 1 else ''}")
        _sfx(self.audio, "confirm")

    def _open_folder(self):
        try:
            os.makedirs(SONGS_DIR, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(SONGS_DIR)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", SONGS_DIR])
            else:
                subprocess.Popen(["xdg-open", SONGS_DIR])
            self._toast("Songs folder opened - add songs, then press REFRESH")
        except Exception:
            self._toast("Songs folder: " + SONGS_DIR)
        _sfx(self.audio, "click")

    # ── input ─────────────────────────────────────────────────────
    def handle_event(self, event) -> Optional[tuple]:
        self.track_mouse(event)
        n = len(self.entries)
        if event.type == pygame.KEYDOWN:
            k = event.key
            if k == pygame.K_ESCAPE:
                return ("back", None, None)
            if k == pygame.K_F5:
                self._refresh()
                return None
            if not n:
                return None
            if k in (pygame.K_UP, pygame.K_w):
                self._select(self.selected - 1)
            elif k in (pygame.K_DOWN, pygame.K_s):
                self._select(self.selected + 1)
            elif k == pygame.K_PAGEUP:
                self._select(self.selected - self.VISIBLE)
            elif k == pygame.K_PAGEDOWN:
                self._select(self.selected + self.VISIBLE)
            elif k == pygame.K_HOME:
                self._select(0)
            elif k == pygame.K_END:
                self._select(n - 1)
            elif k in (pygame.K_LEFT, pygame.K_a):
                self._step_diff(-1)
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self._step_diff(1)
            elif k == pygame.K_m:
                self._step_mode(1)
            elif k == pygame.K_LEFTBRACKET:
                self._step_speed(-1)
            elif k == pygame.K_RIGHTBRACKET:
                self._step_speed(1)
            elif k in (pygame.K_MINUS, pygame.K_KP_MINUS):
                self._step_reverb(-1)
            elif k in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self._step_reverb(1)
            elif k == pygame.K_p:
                self._set_fx(sustain=not self._fx()["sustain"])
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self._play()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for rect, action, arg in reversed(self._hits):
                if rect.collidepoint(event.pos):
                    if action == "reverb":
                        self._fx_drag = True
                        self._drag_reverb(event.pos)
                        return None
                    return self._click(action, arg)
        elif event.type == pygame.MOUSEMOTION and self._fx_drag:
            self._drag_reverb(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._fx_drag:
            self._fx_drag = False
            _sfx(self.audio, "click")
        elif event.type == pygame.MOUSEWHEEL and n:
            if self._reverb_box and self.hovering(self._reverb_box):
                self._step_reverb(1 if event.y > 0 else -1)
            else:
                self.scroll_offset = max(0, min(max(0, n - self.VISIBLE),
                                                self.scroll_offset - event.y))
        return None

    def _click(self, action, arg):
        if action == "card":
            if arg == self.selected:
                return self._play()        # second click on the selected song plays it
            self._select(arg)
        elif action == "diff":
            if arg != self._entry_diff(self.selected):
                self._diff_sel[self.selected] = arg
                _sfx(self.audio, "click")
        elif action == "mode":
            if arg != self.mode:
                self.mode = arg
                _sfx(self.audio, "click")
        elif action == "speed":
            if arg != self._speed_idx:
                self._speed_idx = arg
                _sfx(self.audio, "click")
        elif action == "sustain":
            self._set_fx(sustain=arg)
        elif action == "play":
            return self._play()
        elif action == "folder":
            self._open_folder()
        elif action == "refresh":
            self._refresh()
        return None

    # ── update: song preview ──────────────────────────────────────
    def update(self, dt: float):
        super().update(dt)
        self._dt = dt
        if self._notif_timer > 0:
            self._notif_timer = max(0.0, self._notif_timer - dt)
        self._prev_timer += dt
        cur_diff = self._entry_diff(self.selected) if self.entries else None
        if self._prev_idx != self.selected or self._prev_diff != cur_diff:
            self._prev_idx = self.selected
            self._prev_diff = cur_diff
            self._prev_timer = 0.0
            self._prev_note_i = 0
            self._prev_t = 0.0
            if self.audio:
                self.audio.all_notes_off(150)   # stop the previous song's preview
        if self._fx_drag and not pygame.mouse.get_pressed()[0]:
            self._fx_drag = False               # (button released outside the window)
        if self.audio and self.entries:         # the preview plays with the song's sound
            fx = self._fx()
            self.audio.set_song_fx(fx["reverb"] / 100, fx["sustain"])
        if (self.audio and self._prev_timer >= self.PREVIEW_DELAY
                and self.entries and 0 <= self.selected < len(self.entries)):
            song = self.entries[self.selected].get_song(cur_diff)
            if song:
                self._prev_t += dt
                while self._prev_note_i < len(song.notes):
                    note = song.notes[self._prev_note_i]
                    if note.time_sec > self._prev_t:
                        break
                    self.audio.play_note(note.pitch, min(80, note.velocity),
                                         note.duration_sec, volume_scale=0.45)
                    self._prev_note_i += 1
                if song.notes and self._prev_t > song.notes[-1].time_sec + 1.0:
                    self._prev_note_i = 0        # loop the preview
                    self._prev_t = 0.0

    # ── layout ────────────────────────────────────────────────────
    def _layout(self):
        W, H, s = self.W, self.H, self.s
        m = int(24 * s)
        head_h = int(72 * s)
        foot = ui.footer_rect(W, H, s)
        top, bottom = head_h + int(6 * s), foot.y - int(14 * s)
        list_w = int((W - 3 * m) * 0.57)
        lst = pygame.Rect(m, top, list_w, max(20, bottom - top))
        det = pygame.Rect(lst.right + m, top, max(20, W - m - lst.right - m), lst.h)
        card_h, gap = max(36, int(62 * s)), max(4, int(6 * s))
        self.VISIBLE = max(1, (lst.h + gap) // (card_h + gap))
        return m, head_h, lst, det, card_h, gap

    # ── drawing ───────────────────────────────────────────────────
    def draw(self):
        self.draw_bg()
        s = self.s
        m, head_h, lst, det, card_h, gap = self._layout()
        self._hits = []
        self._draw_header(m, head_h)
        if self.entries:
            self.selected = max(0, min(self.selected, len(self.entries) - 1))
            self.scroll_offset = max(0, min(self.scroll_offset,
                                            max(0, len(self.entries) - self.VISIBLE)))
            self._draw_list(lst, card_h, gap)
            self._draw_details(det)
        else:
            self._draw_empty(lst.union(det))
        ui.footer(self.screen, s, [(("↑", "↓"), "Song"), (("←", "→"), "Difficulty"),
                                   ("M", "Mode"), (("[", "]"), "Speed"), (("-", "+"), "Reverb"),
                                   ("P", "Sustain"), ("ENTER", "Play"), ("ESC", "Back")])
        if self._notif_timer > 0:
            self._draw_toast(head_h)

    def _draw_header(self, m, head_h):
        surf, s = self.screen, self.s
        cy = head_h // 2 + int(2 * s)
        tr = ui.draw_text(surf, "SELECT SONG", int(30 * s), NEON_CYAN, (m, cy), bold=True,
                          anchor="midleft", shadow=True)
        n = len(self.entries)
        pr = ui.pill(surf, f"{n} SONG{'S' if n != 1 else ''}", ui.TEXT_MUTED,
                     (tr.right + int(14 * s), cy), s, anchor="midleft")
        px = max(9, int(13 * s))
        bh = max(22, int(34 * s))
        x = self.W - m
        for label, icon, action in (("REFRESH", ui.icon_refresh, "refresh"),
                                    ("SONGS FOLDER", ui.icon_folder, "folder")):
            bw = ui.text_w(label, px, True) + int(px * 1.4) + int(30 * s)
            r = pygame.Rect(x - bw, cy - bh // 2, bw, bh)
            ui.button(surf, r, label, s, NEON_CYAN, hovered=self.hovering(r), px=px, icon=icon)
            self._hits.append((r, action, None))
            x = r.x - int(10 * s)
        col = NEON_GREEN if self.midi_connected else NEON_ORANGE
        mr = ui.pill(surf, "MIDI CONNECTED" if self.midi_connected else "NO MIDI KEYBOARD", col,
                     (x - int(6 * s), cy), s, anchor="midright", dot=True)
        self._head_free = (pr.right + int(16 * s), mr.x - int(16 * s))
        pygame.draw.line(surf, ui.EDGE, (m, head_h - 1), (self.W - m, head_h - 1))

    def _draw_toast(self, head_h):
        s = self.s
        x0, x1 = self._head_free
        w = ui.pill_w(self._notif, s, dot=True)
        if x1 - x0 >= w:
            pos, anchor = ((x0 + x1) // 2, head_h // 2 + int(2 * s)), "center"
        else:
            pos, anchor = (self.W // 2, head_h + int(10 * s)), "midtop"
        ui.pill(self.screen, self._notif, NEON_GREEN, pos, s, anchor=anchor, dot=True)

    def _draw_empty(self, area):
        surf, s = self.screen, self.s
        box = pygame.Rect(0, 0, min(area.w, int(660 * s)), int(210 * s))
        box.center = area.center
        ui.panel(surf, box)
        isz = int(30 * s)
        ui.icon_note(surf, pygame.Rect(box.centerx - isz // 2, box.y + int(26 * s), isz, isz),
                     NEON_CYAN)
        ui.draw_text(surf, "No songs found", int(24 * s), ui.TEXT,
                     (box.centerx, box.y + int(72 * s)), bold=True, anchor="midtop")
        ui.draw_text(surf, "Put .mid files or song folders into the songs folder,", int(15 * s),
                     ui.TEXT_MUTED, (box.centerx, box.y + int(116 * s)), anchor="midtop")
        ui.draw_text(surf, "then press REFRESH (F5).", int(15 * s), ui.TEXT_MUTED,
                     (box.centerx, box.y + int(140 * s)), anchor="midtop")

    def _draw_list(self, lst, card_h, gap):
        surf, s, t = self.screen, self.s, self._tick
        n = len(self.entries)
        step = card_h + gap
        rad = max(4, int(10 * s))
        target = lst.y + (self.selected - self.scroll_offset) * step
        if self._hl_y is None:
            self._hl_y = float(target)
        self._hl_y += (target - self._hl_y) * min(1.0, self._dt * 18)
        if abs(target - self._hl_y) < 0.5:
            self._hl_y = float(target)

        cards = []
        for i in range(self.VISIBLE):
            idx = self.scroll_offset + i
            if idx >= n:
                break
            r = pygame.Rect(lst.x, lst.y + i * step, lst.w, card_h)
            cards.append((r, idx))
            self._hits.append((r, "card", idx))

        old_clip = surf.get_clip()
        surf.set_clip(pygame.Rect(lst.x - int(14 * s), lst.y - int(3 * s),
                                  lst.w + int(28 * s), lst.h + int(6 * s)))
        for r, idx in cards:
            hov = idx != self.selected and self.hovering(r)
            ui.panel(surf, r, alpha=175, border=ui.EDGE_HI if hov else ui.EDGE, radius=rad)
        fr = pygame.Rect(lst.x, int(self._hl_y), lst.w, card_h)
        ui.glow(surf, fr, NEON_CYAN, rad, int(10 * s), 0.45 + 0.3 * math.sin(t * 3.2))
        ui.panel(surf, fr, fill=ui.shade(NEON_CYAN, 0.13), alpha=235, border=NEON_CYAN, width=2,
                 radius=rad)
        for r, idx in cards:
            self._draw_card(r, idx)
        surf.set_clip(old_clip)

        if n > self.VISIBLE:          # scrollbar in the gutter between list and details
            track = pygame.Rect(lst.right + int(9 * s), lst.y, max(3, int(4 * s)), lst.h)
            pygame.draw.rect(surf, ui.TRACK, track, border_radius=track.w // 2)
            th = max(int(24 * s), int(track.h * self.VISIBLE / n))
            ty = track.y + int((track.h - th) * self.scroll_offset / max(1, n - self.VISIBLE))
            pygame.draw.rect(surf, ui.EDGE_HI, (track.x, ty, track.w, th),
                             border_radius=track.w // 2)

    def _draw_card(self, r, idx):
        surf, s = self.screen, self.s
        entry = self.entries[idx]
        sel = idx == self.selected
        diff = self._entry_diff(idx)
        song = entry.get_song(diff)

        th = int(r.h * 0.74)
        thumb = pygame.Rect(r.x + int(8 * s), r.centery - th // 2, th, th)
        self._draw_thumb(entry, thumb)

        dot_r = max(3, int(5 * s))
        dstep = max(10, int(16 * s))
        dx0 = r.right - int(18 * s) - dstep * (len(DIFFICULTY_ORDER) - 1)
        for j, d in enumerate(DIFFICULTY_ORDER):
            c = (dx0 + j * dstep, r.centery)
            if d in entry.difficulties:
                pygame.draw.circle(surf, DIFFICULTY_COLORS[d], c, dot_r)
                if d == diff:
                    pygame.draw.circle(surf, ui.TEXT if sel else ui.TEXT_MUTED, c,
                                       dot_r + max(2, int(3 * s)), 1)
            else:
                pygame.draw.circle(surf, ui.EDGE, c, dot_r, 1)

        tx = thumb.right + int(12 * s)
        tw = dx0 - dot_r - int(16 * s) - tx
        p1, p2 = int(17 * s), int(13 * s)
        h1, h2 = ui.font(p1, True).get_height(), ui.font(p2).get_height()
        y = r.y + (r.h - h1 - h2 - int(3 * s)) // 2
        ui.draw_text(surf, ui.fit(entry.title, p1, tw, True), p1,
                     ui.TEXT if sel else (196, 196, 218), (tx, y), bold=True)
        dur = ui.fmt_time(song.duration_sec) if song else "-"
        if entry.author:
            sub = f"{entry.author} · {dur}"
        else:
            sub = f"{dur} · {len(song.notes):,} notes" if song else dur
        ui.draw_text(surf, ui.fit(sub, p2, tw), p2, ui.TEXT_MUTED if sel else ui.TEXT_DIM,
                     (tx, y + h1 + int(3 * s)))

    def _cover(self, entry, size):
        key = (entry.folder, entry.title, size)
        if key in self._cover_cache:
            return self._cover_cache[key]
        img = None
        if entry.folder:
            for name in COVER_NAMES:
                path = os.path.join(entry.folder, name)
                if os.path.exists(path):
                    try:
                        raw = pygame.image.load(path)
                        raw = raw.convert_alpha() if raw.get_alpha() is not None else raw.convert()
                        w, h = raw.get_size()
                        side = min(w, h)
                        raw = raw.subsurface(((w - side) // 2, (h - side) // 2, side, side))
                        img = ui.rounded(pygame.transform.smoothscale(raw, (size, size)),
                                         max(3, size // 10))
                    except Exception:
                        img = None
                    break
        if len(self._cover_cache) > 64:
            self._cover_cache.clear()
        self._cover_cache[key] = img
        return img

    def _draw_thumb(self, entry, rect):
        surf = self.screen
        rad = max(3, rect.w // 10)
        img = self._cover(entry, rect.w)
        if img:
            surf.blit(img, rect)
            pygame.draw.rect(surf, ui.EDGE_HI, rect, 1, border_radius=rad)
            return
        col = LANE_COLORS[zlib.crc32(entry.title.encode("utf-8")) % len(LANE_COLORS)]
        ui.panel(surf, rect, fill=ui.shade(col, 0.16), alpha=255, border=ui.shade(col, 0.55),
                 radius=rad, top_hi=False)
        ui.draw_text(surf, "♪", int(rect.h * 0.55), ui.shade(col, 0.95), rect.center, bold=True,
                     anchor="center")

    def _roll_img(self, song, w, h):
        """The whole song as a tiny piano roll (cached per song and size)."""
        key = (id(song), w, h)
        img = self._roll_cache.get(key)
        if img is None:
            img = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
            dur = max(0.1, song.duration_sec)
            lo, hi = song.min_pitch, song.max_pitch
            span = max(12, hi - lo)
            lo = (lo + hi) / 2 - span / 2
            nh = max(2, min(4, h // 14))
            for n in song.notes:
                x = int(n.time_sec / dur * (w - 1))
                nw = max(1, int(n.duration_sec / dur * w))
                y = int((1 - (n.pitch - lo) / span) * (h - nh))
                img.fill(ui.shade(ui.pitch_color(n.pitch), 0.85), (x, y, nw, nh))
            if len(self._roll_cache) > 24:
                self._roll_cache.clear()
            self._roll_cache[key] = img
        return img

    def _draw_roll(self, song, r):
        surf, s = self.screen, self.s
        ui.panel(surf, r, fill=(6, 6, 16), alpha=235, radius=max(3, int(6 * s)), top_hi=False)
        if not song or not song.notes:
            return
        inner = r.inflate(-int(12 * s), -int(10 * s))
        surf.blit(self._roll_img(song, inner.w, inner.h), inner)
        if self._prev_idx == self.selected and self._prev_timer >= self.PREVIEW_DELAY:
            x = inner.x + int(min(1.0, self._prev_t / max(0.1, song.duration_sec)) * inner.w)
            pygame.draw.line(surf, ui.TEXT, (x, r.y + 3), (x, r.bottom - 4), 2)

    def _fit_details(self, det, entry, song):
        """Sizes for the details column: the natural ones when there is room, otherwise the
        cover, roll, gaps and PLAY button shrink just enough to fit (and in a very short
        window the roll goes)."""
        s = self.s
        key = (det.size, s, entry.title, entry.author, id(song))
        if self._fit[0] == key:
            return self._fit[1]
        pad = int(18 * s)
        sec_h = ui.font(max(9, int(13 * s)), True).get_height()
        seg_h, head_gap = max(20, int(32 * s)), int(8 * s)
        desc_h = ui.font(int(13 * s)).get_height()
        pb_h = ui.font(max(9, int(13 * s)), True).get_height() + max(3, int(5 * s))

        def text_h(cover):
            tw = det.w - 2 * pad - cover - int(16 * s)
            h = (len(ui.wrap(entry.title, int(22 * s), tw, True, 2))
                 * ui.font(int(22 * s), True).get_height() + int(8 * s))
            if entry.author:
                h += int(2 * s) + ui.font(int(15 * s)).get_height()
            if song:
                h += 2 * ui.font(int(13 * s)).get_height() + int(4 * s)
            return h

        def lerp(a, b, f):
            return int(round((a + (b - a) * f) * s))

        for roll in (True, False):
            for i in range(11):
                f = i / 10
                z = {"cover": lerp(120, 84, f), "cover_gap": lerp(14, 10, f),
                     "roll": lerp(46, 30, f) if roll else 0, "gap": lerp(16, 11, f),
                     "desc_gap": lerp(14, 10, f), "play": max(30, lerp(50, 42, f))}
                z["head"] = max(z["cover"], text_h(z["cover"]))
                total = (2 * pad + z["head"] + z["cover_gap"]
                         + (z["roll"] + z["gap"] if roll else 0)
                         + 3 * (sec_h + head_gap + seg_h + z["gap"])    # difficulty, speed, sound
                         + sec_h + head_gap + seg_h + int(6 * s) + desc_h + z["desc_gap"]  # mode
                         + sec_h + head_gap + pb_h + int(10 * s) + z["play"])
                if total <= det.h:
                    self._fit = (key, z)
                    return z
        self._fit = (key, z)
        return z

    def _draw_details(self, det):
        surf, s, t = self.screen, self.s, self._tick
        ui.panel(surf, det, alpha=200)
        entry = self.entries[self.selected]
        diff = self._entry_diff(self.selected)
        song = entry.get_song(diff)
        z = self._fit_details(det, entry, song)
        pad = int(18 * s)
        x, y, w = det.x + pad, det.y + pad, det.w - 2 * pad

        # cover, title, facts
        cover = pygame.Rect(x, y, z["cover"], z["cover"])
        self._draw_thumb(entry, cover)
        tx = cover.right + int(16 * s)
        tw = det.right - pad - tx
        ty = cover.y - int(2 * s)
        for line in ui.wrap(entry.title, int(22 * s), tw, True, 2):
            ty = ui.draw_text(surf, line, int(22 * s), ui.TEXT, (tx, ty), bold=True).bottom
        if entry.author:
            ty = ui.draw_text(surf, ui.fit(entry.author, int(15 * s), tw), int(15 * s),
                              ui.TEXT_MUTED, (tx, ty + int(2 * s))).bottom
        ty += int(10 * s)
        if song:
            facts = (f"♪ {song.bpm:.0f} BPM · {ui.fmt_time(song.duration_sec)} · "
                     f"{len(song.notes):,} notes")
            ty = ui.draw_text(surf, ui.fit(facts, int(13 * s), tw), int(13 * s), (196, 160, 255),
                              (tx, ty)).bottom + int(4 * s)
            ui.draw_text(surf, f"Keys {ui.note_name(song.min_pitch)} – {ui.note_name(song.max_pitch)}",
                         int(13 * s), ui.TEXT_DIM, (tx, ty))

        y += z["head"] + z["cover_gap"]
        if z["roll"]:
            roll = pygame.Rect(x, y, w, z["roll"])
            self._draw_roll(song, roll)
            y = roll.bottom + z["gap"]

        seg_h = max(20, int(32 * s))
        seg_px = max(9, int(13 * s))
        cell_gap = max(3, int(6 * s))
        head_gap = int(8 * s)

        y += ui.section(surf, "DIFFICULTY", x, y, w, s, right="← →") + head_gap
        cells = ui.split_row((x, y, w, seg_h), len(DIFFICULTY_ORDER), cell_gap)
        for cell, d in zip(cells, DIFFICULTY_ORDER):
            ok = d in entry.difficulties
            ui.segment(surf, cell, d, DIFFICULTY_COLORS[d], s, selected=(d == diff),
                       hovered=ok and self.hovering(cell), enabled=ok, px=seg_px)
            if ok:
                self._hits.append((cell, "diff", d))
        y += seg_h + z["gap"]

        y += ui.section(surf, "MODE", x, y, w, s, right="M") + head_gap
        cells = ui.split_row((x, y, w, seg_h), len(ui.MODES), cell_gap)
        for cell, md in zip(cells, ui.MODES):
            ui.segment(surf, cell, ui.mode_name(md), ui.mode_color(md), s,
                       selected=(md == self.mode), hovered=self.hovering(cell), px=seg_px)
            self._hits.append((cell, "mode", md))
        y += seg_h + int(6 * s)
        y = ui.draw_text(surf, ui.fit(ui.MODE_DESC.get(self.mode, ""), int(13 * s), w),
                         int(13 * s), ui.TEXT_MUTED, (x, y)).bottom + z["desc_gap"]

        y += ui.section(surf, "SPEED", x, y, w, s, right="[ ]") + head_gap
        cells = ui.split_row((x, y, w, seg_h), len(self._speeds), cell_gap)
        for i, (cell, sp) in enumerate(zip(cells, self._speeds)):
            ui.segment(surf, cell, f"{int(sp * 100)}%", NEON_CYAN, s,
                       selected=(i == self._speed_idx), hovered=self.hovering(cell), px=seg_px)
            self._hits.append((cell, "speed", i))
        y += seg_h + z["gap"]

        # The song's sound (saved per song): REVERB slider, SUSTAIN pedal held for the song
        fx = self._fx()
        col_gap = int(16 * s)
        rw = int((w - col_gap) * 0.6)
        sx, sw = x + rw + col_gap, w - rw - col_gap
        note = self._reverb_note()
        sec_h = ui.section(surf, "REVERB", x, y, rw, s, right=note or "- +")
        ui.section(surf, "SUSTAIN", sx, y, sw, s, right="P")
        y += sec_h + head_gap
        box = pygame.Rect(x, y, rw, seg_h)
        self._draw_reverb(box, fx["reverb"], note is None)
        self._hits.append((box, "reverb", None))
        cells = ui.split_row((sx, y, sw, seg_h), 2, cell_gap)
        for cell, on in zip(cells, (False, True)):
            ui.segment(surf, cell, "ON" if on else "OFF", NEON_YELLOW if on else ui.TEXT_MUTED, s,
                       selected=(fx["sustain"] == on), hovered=self.hovering(cell), px=seg_px)
            self._hits.append((cell, "sustain", on))
        y += seg_h + z["gap"]

        y += ui.section(surf, "PERSONAL BEST", x, y, w, s) + head_gap
        self._draw_pb(song, x, y, w)

        bh = z["play"]
        play = pygame.Rect(x, det.bottom - pad - bh, w, bh)
        ui.button(surf, play, "PLAY", s, NEON_GREEN, selected=True, hovered=self.hovering(play),
                  t=t, px=int(22 * s), icon=ui.icon_play)
        self._hits.append((play, "play", None))

    def _draw_reverb(self, box, value, live):
        """REVERB: a slider with its value at the right end. When the instrument in use has no
        reverb it is drawn dimmed, but it can still be set (it is saved with the song)."""
        surf, s = self.screen, self.s
        col = NEON_PURPLE if live else ui.TEXT_DIM
        hot = self._fx_drag or self.hovering(box)
        rad = max(4, int(7 * s))
        if hot:
            ui.panel(surf, box, fill=ui.shade(col, 0.1), alpha=230,
                     border=ui.mix(col, ui.EDGE, 0.4), radius=rad)
        else:
            ui.panel(surf, box, alpha=200, border=ui.EDGE, radius=rad)
        px = max(9, int(13 * s))
        inset = int(12 * s)
        ui.draw_text(surf, f"{value}%", px, ui.TEXT if live else ui.TEXT_DIM,
                     (box.right - inset, box.centery), bold=True, anchor="midright")
        kr = max(5, int(9 * s))
        th = max(4, int(6 * s))
        x0 = box.x + inset + kr
        x1 = box.right - inset - ui.text_w("100%", px, True) - inset - kr
        track = pygame.Rect(x0, box.centery - th // 2, max(1, x1 - x0), th)
        self._reverb_box, self._reverb_track = box, track
        ui.bar(surf, track, value / 100, ui.shade(col, 0.75))
        kx, ky = track.x + int(track.w * value / 100), track.centery
        if hot and live:
            ui.glow(surf, (kx - kr, ky - kr, 2 * kr, 2 * kr), col, radius=kr,
                    spread=max(4, int(7 * s)), strength=0.9 if self._fx_drag else 0.55)
        pygame.draw.circle(surf, col, (kx, ky), kr)
        pygame.draw.circle(surf, (10, 10, 22), (kx, ky), max(2, int(kr * 0.42)))

    def _draw_pb(self, song, x, y, w):
        surf, s = self.screen, self.s
        px = max(9, int(14 * s))
        if self.mode == MODE_TESTING:
            ui.draw_text(surf, ui.fit("Autoplay runs are not scored", px, w), px, ui.TEXT_DIM,
                         (x, y))
            return
        pb = (self.pb_lookup(song, self.mode, self._speeds[self._speed_idx])
              if self.pb_lookup and song else None)
        if pb:
            g = pb.get("grade", "-")
            pr = ui.pill(surf, g, ui.GRADE_COLOR.get(g, ui.TEXT_MUTED), (x, y), s,
                         px=max(9, int(13 * s)), filled=True)
            txt = f"{pb.get('score', 0):,} pts · {pb.get('accuracy', 0):.1f}% accuracy"
            ui.draw_text(surf, ui.fit(txt, px, w - pr.w - int(10 * s)), px, ui.TEXT,
                         (pr.right + int(10 * s), pr.centery), anchor="midleft")
        else:
            ui.draw_text(surf, ui.fit("Not played yet at this difficulty, mode and speed", px, w),
                         px, ui.TEXT_DIM, (x, y))


# ── Results ───────────────────────────────────────────────────────
_soft = {}

def _soft_glow(label, px, color, level):
    """Blurred copy of big text for an additive neon glow; `level` 0..5 sets its strength."""
    key = (label, px, color, level)
    g = _soft.get(key)
    if g is None:
        base = _soft.get((label, px, color, -1))
        if base is None:
            t = ui.font(px, True).render(label, True, color)
            pad = px // 3
            canvas = pygame.Surface((t.get_width() + pad * 2, t.get_height() + pad * 2))
            canvas.blit(t, (pad, pad))
            small = pygame.transform.smoothscale(
                canvas, (max(1, canvas.get_width() // 9), max(1, canvas.get_height() // 9)))
            base = _soft[(label, px, color, -1)] = pygame.transform.smoothscale(small,
                                                                                canvas.get_size())
        if len(_soft) > 60:
            _soft.clear()
            _soft[(label, px, color, -1)] = base
        g = base.copy()
        f = int(255 * level / 5)
        g.fill((f, f, f), special_flags=pygame.BLEND_RGB_MULT)
        _soft[key] = g
    return g


class ResultsScreen(MenuBase):
    BUTTONS = [("RETRY", "retry", NEON_GREEN), ("SONG LIST", "songs", NEON_CYAN),
               ("MAIN MENU", "menu", NEON_PURPLE)]
    LADDER = ["F", "C", "B", "A", "S", "SS", "GODLIKE"]
    NEXT = {
        "F":  "Next: C needs 62% of notes hit",
        "C":  "Next: B needs 78% of notes hit",
        "B":  "Next: A needs 90% of notes hit",
        "A":  "Next: S needs no missed notes",
        "S":  "Next: SS needs only PERFECT and GREAT hits",
        "SS": "Next: GODLIKE needs every note PERFECT",
        "GODLIKE": "Top grade!",
    }
    KEY_DELAY = 0.5     # ignore keys at first, so notes played as the song ends don't click

    def __init__(self, screen, stats, song_title: str, xp_system, personal_best: Optional[dict],
                 autoplay: bool = False, info: Optional[dict] = None):
        super().__init__(screen)
        self.stats = stats
        self.song_title = song_title
        self.xp_system = xp_system
        self.pb = personal_best
        self.autoplay = autoplay        # autoplay was used: shown, but not saved
        self.info = info or {}
        self.judged = stats.hits_perfect + stats.hits_great + stats.hits_good + stats.misses
        self.grade = stats.get_grade() if self.judged else "-"
        self.selected = 0
        self._show_timer = 0.0

    def update(self, dt):
        super().update(dt)
        self._show_timer += dt

    def _btn_rects(self):
        s = self.s
        bw, bh, gap = int(200 * s), max(30, int(50 * s)), int(18 * s)
        n = len(self.BUTTONS)
        x0 = self.W // 2 - (n * bw + (n - 1) * gap) // 2
        y = ui.footer_rect(self.W, self.H, s).y - int(16 * s) - bh
        return [pygame.Rect(x0 + i * (bw + gap), y, bw, bh) for i in range(n)]

    def handle_event(self, event) -> Optional[str]:
        self.track_mouse(event)
        # (a click on a footer keycap is meant, so it skips the delay)
        if event.type == pygame.KEYDOWN and (self._show_timer >= self.KEY_DELAY
                                             or getattr(event, "clicked", False)):
            k = event.key
            if k in (pygame.K_LEFT, pygame.K_a):
                self.selected = (self.selected - 1) % len(self.BUTTONS)
            elif k in (pygame.K_RIGHT, pygame.K_d):
                self.selected = (self.selected + 1) % len(self.BUTTONS)
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self.BUTTONS[self.selected][1]
            elif k == pygame.K_r:
                return "retry"
            elif k == pygame.K_ESCAPE:
                return "menu"
        elif event.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self._btn_rects()):
                if r.collidepoint(event.pos):
                    self.selected = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self._btn_rects()):
                if r.collidepoint(event.pos):
                    return self.BUTTONS[i][1]
        return None

    # ── drawing ───────────────────────────────────────────────────
    def draw(self):
        self.draw_bg()
        surf, W, s, t = self.screen, self.W, self.s, self._tick
        m = int(24 * s)

        y = int(14 * s)
        ui.draw_text(surf, "RESULTS", max(10, int(14 * s)), NEON_CYAN, (W // 2, y), bold=True,
                     anchor="midtop")
        y += int(20 * s)
        y = ui.draw_text(surf, ui.fit(self.song_title, int(28 * s), W - 2 * m, True), int(28 * s),
                         ui.TEXT, (W // 2, y), bold=True, anchor="midtop", shadow=True).bottom
        tags = []
        d = self.info.get("difficulty")
        if d:
            tags.append((d, DIFFICULTY_COLORS.get(d, ui.TEXT_MUTED), False))
        md = self.info.get("mode")
        if md:
            tags.append((ui.mode_name(md), ui.mode_color(md), False))
        sp = self.info.get("speed")
        if sp:
            tags.append((f"SPEED {round(sp * 100)}%", NEON_CYAN, False))
        if self.autoplay:
            tags.append(("NOT SCORED", NEON_ORANGE, True))
        pill_h = ui.font(max(9, int(13 * s)), True).get_height() + max(3, int(5 * s))
        if tags:
            ui.pill_row(surf, tags, (W // 2, y + int(10 * s) + pill_h // 2), s)
        top = y + int(10 * s) + pill_h + int(18 * s)

        btns = self._btn_rects()
        bottom = btns[0].y - int(18 * s)
        gap = max(6, int(12 * s))
        info_h, brk_h = max(28, int(44 * s)), max(70, int(104 * s))
        avail = bottom - top
        card_h = max(int(84 * s), min(int(120 * s), (avail - info_h - brk_h - 3 * gap) // 2))
        need = 2 * card_h + 3 * gap + brk_h + info_h
        y0 = top + max(0, (avail - need) // 2)

        gw = int((W - 3 * m) * 0.34)
        grade_r = pygame.Rect(m, y0, gw, need)
        rx = grade_r.right + m
        rw = W - m - rx
        self._draw_grade(grade_r)
        cw = (rw - gap) // 2
        cards = [pygame.Rect(rx + (i % 2) * (cw + gap), y0 + (i // 2) * (card_h + gap), cw, card_h)
                 for i in range(4)]
        self._draw_cards(cards)
        brk = pygame.Rect(rx, y0 + 2 * card_h + 2 * gap, rw, brk_h)
        self._draw_breakdown(brk)
        self._draw_info(pygame.Rect(rx, brk.bottom + gap, rw, info_h))

        for i, ((label, _, col), r) in enumerate(zip(self.BUTTONS, btns)):
            ui.button(surf, r, label, s, col, selected=(i == self.selected),
                      hovered=self.hovering(r), t=t, px=int(18 * s))
        ui.footer(surf, s, [(("←", "→"), "Select"), ("ENTER", "Confirm"), ("R", "Retry"),
                            ("ESC", "Main menu")])

    def _draw_grade(self, r):
        surf, s, t = self.screen, self.s, self._tick
        ui.panel(surf, r, alpha=205)
        g = self.grade
        col = ui.GRADE_COLOR.get(g, ui.TEXT_DIM)
        pad = int(18 * s)
        sec_h = ui.section(surf, "GRADE", r.x + pad, r.y + pad, r.w - 2 * pad, s,
                           right="autoplay used" if self.autoplay else None)

        px = max(24, min(int(150 * s), int((r.w - 2 * pad) / (0.56 * max(1, len(g))))))
        fh = ui.font(px, True).get_height()
        lad_px = max(9, int(12 * s))
        lad_h = ui.font(lad_px, True).get_height() + max(3, int(5 * s))
        desc_px, hint_px = max(9, int(15 * s)), max(9, int(13 * s))
        block = (fh - int(px * 0.2) + int(6 * s) + ui.font(desc_px).get_height() + int(18 * s)
                 + lad_h + int(12 * s) + ui.font(hint_px).get_height())
        area_top = r.y + pad + sec_h
        y = area_top + max(0, (r.bottom - pad - area_top - block) // 2)

        tr = ui.text(g, px, col, True).get_rect(midtop=(r.centerx, y))
        if self.judged:
            pulse = 0.5 + 0.5 * math.sin(t * 2.6)
            level = 2 + int(round(pulse * 3))                       # 2..5
            glow = _soft_glow(g, px, col, level)
            surf.blit(glow, (tr.x - px // 3, tr.y - px // 3), special_flags=pygame.BLEND_RGB_ADD)
        ui.draw_text(surf, g, px, col, tr.topleft, bold=True, shadow=True)
        y = tr.bottom - int(px * 0.2) + int(6 * s)
        desc = ui.GRADE_DESC.get(g, "No notes were played")
        y = ui.draw_text(surf, ui.fit(desc, desc_px, r.w - 2 * pad), desc_px, ui.TEXT_MUTED,
                         (r.centerx, y), anchor="midtop").bottom + int(18 * s)

        items = [(x, ui.GRADE_COLOR[x] if x == g else ui.shade(ui.GRADE_COLOR[x], 0.5), x == g)
                 for x in self.LADDER]
        ui.pill_row(surf, items, (r.centerx, y + lad_h // 2), s, px=lad_px, gap=max(3, int(6 * s)))
        y += lad_h + int(12 * s)
        hint = self.NEXT.get(g)
        if hint:
            ui.draw_text(surf, ui.fit(hint, hint_px, r.w - 2 * pad), hint_px,
                         NEON_YELLOW if g == "GODLIKE" else ui.TEXT_DIM, (r.centerx, y),
                         anchor="midtop")

    def _delta(self, cur, best, fmt, tol):
        if best is None or self.autoplay:
            return None
        diff = cur - best
        if diff > tol:
            return "▲ +" + fmt.format(diff), NEON_GREEN
        if diff < -tol:
            return "▼ -" + fmt.format(-diff), NEON_RED
        return "= same", ui.TEXT_DIM

    def _draw_cards(self, cards):
        surf, s = self.screen, self.s
        st, pb = self.stats, self.pb or {}
        shown = int(round(st.score * _ease_out(self._show_timer / 0.9)))
        new_best = (not self.autoplay and self.pb is not None and st.score > pb.get("score", 0))
        total = max(st.total_notes, self.judged)
        items = [
            ("SCORE", f"{shown:,}", NEON_CYAN,
             self._delta(st.score, pb.get("score"), "{:,.0f}", 0.5), new_best),
            ("ACCURACY", f"{st.accuracy:.1f}%" if self.judged else "-", NEON_GREEN,
             self._delta(st.accuracy, pb.get("accuracy"), "{:.1f}%", 0.05) if self.judged else None,
             False),
            ("MAX COMBO", f"{st.max_combo:,}", NEON_YELLOW,
             self._delta(st.max_combo, pb.get("combo"), "{:,.0f}", 0.5), False),
            ("NOTES HIT", f"{st.hit_count:,} / {total:,}", NEON_PINK, None, False),
        ]
        pad = int(16 * s)
        for i, (r, (label, value, col, delta, best)) in enumerate(zip(cards, items)):
            k = _ease_out((self._show_timer - 0.08 * i) / 0.35)
            if k <= 0:
                continue
            rr = r.move(0, int((1 - k) * 16 * s))
            ui.panel(surf, rr, alpha=205)
            pygame.draw.rect(surf, col, (rr.x + 1, rr.y + int(14 * s), max(2, int(3 * s)),
                                         rr.h - int(28 * s)), border_radius=2)
            lr = ui.draw_text(surf, label, max(9, int(13 * s)), ui.TEXT_MUTED,
                              (rr.x + pad, rr.y + int(12 * s)), bold=True)
            if best:
                ui.pill(surf, "NEW BEST", NEON_YELLOW, (lr.right + int(10 * s), lr.centery), s,
                        px=max(9, int(11 * s)), anchor="midleft", filled=True)
            ui.draw_text(surf, value, int(32 * s), col, (rr.x + pad, rr.bottom - int(10 * s)),
                         bold=True, anchor="bottomleft")
            if delta:
                ui.draw_text(surf, delta[0], max(9, int(14 * s)), delta[1],
                             (rr.right - pad, rr.bottom - int(14 * s)), bold=True,
                             anchor="bottomright")

    def _draw_breakdown(self, r):
        surf, s = self.screen, self.s
        st = self.stats
        ui.panel(surf, r, alpha=205)
        pad = int(16 * s)
        ui.section(surf, "HIT BREAKDOWN", r.x + pad, r.y + int(12 * s), r.w - 2 * pad, s,
                   right=f"{self.judged:,} notes judged")
        parts = [("PERFECT", st.hits_perfect), ("GREAT", st.hits_great),
                 ("GOOD", st.hits_good), ("MISS", st.misses)]
        total = max(1, self.judged)
        bar = pygame.Rect(r.x + pad, r.y + int(40 * s), r.w - 2 * pad, max(8, int(16 * s)))
        rad = bar.h // 2
        pygame.draw.rect(surf, ui.TRACK, bar, border_radius=rad)
        full = bar.w * _ease_out((self._show_timer - 0.25) / 0.6)
        drawn = [(name, n) for name, n in parts if n > 0]
        acc = 0
        for j, (name, n) in enumerate(drawn):
            x0 = bar.x + int(full * acc / total)
            acc += n
            x1 = bar.x + int(full * acc / total)
            if x1 > x0:
                pygame.draw.rect(surf, ui.JUDGE_COLOR[name], (x0, bar.y, x1 - x0, bar.h),
                                 border_top_left_radius=rad if j == 0 else 0,
                                 border_bottom_left_radius=rad if j == 0 else 0,
                                 border_top_right_radius=rad if j == len(drawn) - 1 else 0,
                                 border_bottom_right_radius=rad if j == len(drawn) - 1 else 0)
        cells = ui.split_row((bar.x, bar.bottom + int(12 * s), bar.w, int(22 * s)), 4, int(8 * s))
        for cell, (name, n) in zip(cells, parts):
            c = ui.JUDGE_COLOR[name]
            pygame.draw.circle(surf, c, (cell.x + int(5 * s), cell.centery), max(3, int(5 * s)))
            lr = ui.draw_text(surf, name, max(9, int(12 * s)), ui.TEXT_MUTED,
                              (cell.x + int(16 * s), cell.centery), bold=True, anchor="midleft")
            nr = ui.draw_text(surf, f"{n:,}", max(9, int(15 * s)), ui.TEXT,
                              (lr.right + int(8 * s), cell.centery), bold=True, anchor="midleft")
            if self.judged:
                ui.draw_text(surf, f"{n * 100 / total:.0f}%", max(9, int(12 * s)), ui.TEXT_DIM,
                             (nr.right + int(6 * s), cell.centery), anchor="midleft")

    def _draw_info(self, r):
        surf, s = self.screen, self.s
        ui.panel(surf, r, alpha=190)
        pad = int(16 * s)
        px = max(9, int(14 * s))
        pb = self.pb
        if self.autoplay:
            txt, col = "Autoplay run - score and XP were not saved.", NEON_ORANGE
        elif pb:
            txt = (f"Previous best: {pb.get('score', 0):,} · {pb.get('accuracy', 0):.1f}% · "
                   f"{pb.get('grade', '-')} · combo {pb.get('combo', 0):,}")
            col = ui.TEXT_MUTED
        elif self.judged:
            txt, col = "First score on this chart at this mode and speed!", NEON_GREEN
        else:
            txt, col = "No notes were played, so nothing was saved.", ui.TEXT_DIM
        ui.status_dot(surf, (r.x + pad + int(4 * s), r.centery), col, s)
        ui.draw_text(surf, ui.fit(txt, px, r.w - 2 * pad - int(16 * s)), px, col,
                     (r.x + pad + int(16 * s), r.centery), anchor="midleft")
