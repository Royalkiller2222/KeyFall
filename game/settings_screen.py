"""
KeyFall - settings screen.

Two panels, drawn with the shared kit in game.ui:
  left   VOLUME sliders, and the INSTRUMENT that plays the notes (soundfont, synth, MIDI out)
  right  the DEFAULT MODE, the HIGHWAY PERSPECTIVE, the keys you use during a song, and
         UPDATES (CHECK FOR UPDATES asks GitHub for a newer KeyFall; see game.update_check)

Volumes are heard live while you change them; everything is kept only when you SAVE (ENTER).
BACK / ESC leaves without saving and puts the volumes back the way they were.

Mouse: click, drag the sliders, scroll an open list (or the slider under the pointer).
Keys:  up/down pick a row, left/right change it, SPACE opens a list or presses a button,
       ENTER saves, ESC goes back (or closes an open list).
"""

from typing import Optional

import pygame

from game import ui
from game.constants import (MODE_TESTING, NEON_CYAN, NEON_GREEN, NEON_ORANGE, NEON_PINK,
                            NEON_PURPLE, NEON_YELLOW)

ENGINES = ["soundfont", "synth", "midi_out"]
ENGINE_LABEL = {"soundfont": "SOUNDFONT", "synth": "SYNTH", "midi_out": "MIDI OUT"}
ENGINE_DESC = {
    "soundfont": "Sampled instruments from .sf2 files. The most realistic sound.",
    "synth":     "The built-in synthesizer. Always works, no files needed.",
    "midi_out":  "Sends the notes to a MIDI device or music app instead.",
}
# How much the highway narrows toward the top (the renderer's vanish_frac)
PERSPECTIVES = [(0.0, "FLAT"), (0.33, "SHALLOW"), (0.67, "DEEP")]
# The computer keys that play a song's notes, lowest first (app.PLAY_KEYS)
PLAY_KEYS = tuple("ASDFGHJKLQWERT")


def _clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def _cap(name):
    return name[:1].upper() + name[1:]


def _cat_name(cat):
    return "Other" if cat == "uncategorized" else _cap(cat.replace("_", " "))


def _sf2_name(fname):
    return "No soundfonts found" if fname == "(none)" else _cap(ui.pretty_file(fname))


def _vel_text(v):
    n = int(round(v * 127))
    return "AS PLAYED" if n == 0 else str(n)


# ── Controls ──────────────────────────────────────────────────────
# Each control has .row: its whole area (label included), used for hover and the focus
# highlight. The screen places them in _layout().

class Slider:
    """Label and value on top, a track with a round knob below. Values run 0..1."""

    def __init__(self, label, value, color, fmt=None):
        self.label, self.color = label, color
        self.value = _clamp(float(value), 0.0, 1.0)
        self.fmt = fmt or (lambda v: f"{round(v * 100)}%")
        self.dragging = False
        self.enabled = True              # drawn dimmed when False (still adjustable)
        self.row = self.track = pygame.Rect(0, 0, 0, 0)
        self.knob_r = 8

    def place(self, rect, s):
        self.row = pygame.Rect(rect)
        self.knob_r = max(5, int(9 * s))
        th = max(4, int(6 * s))
        cy = self.row.bottom - self.knob_r - max(1, int(2 * s))
        self.track = pygame.Rect(self.row.x + self.knob_r, cy - th // 2,
                                 self.row.w - 2 * self.knob_r, th)

    def grab_rect(self):
        h = self.knob_r * 2 + 10
        return pygame.Rect(self.row.x, self.track.centery - h // 2, self.row.w, h)

    def press(self, pos):
        if self.grab_rect().collidepoint(pos):
            self.dragging = True
            self.drag(pos)
            return True
        return False

    def drag(self, pos):
        if self.track.w > 0:
            self.value = _clamp((pos[0] - self.track.x) / self.track.w, 0.0, 1.0)

    def step(self, d):
        """Keys and wheel: 5 % at a time, snapped to the 5 % grid. True if it changed."""
        v = _clamp(round(self.value * 20 + d) / 20, 0.0, 1.0)
        changed = abs(v - self.value) > 1e-9
        self.value = v
        return changed

    def draw(self, surf, s, hot):
        px = max(10, int(15 * s))
        col = self.color if self.enabled else ui.TEXT_DIM
        ui.draw_text(surf, self.label, px, ui.TEXT if hot else ui.TEXT_MUTED, self.row.topleft)
        ui.draw_text(surf, self.fmt(self.value), px, col, (self.row.right, self.row.y), bold=True,
                     anchor="topright")
        ui.bar(surf, self.track, self.value, ui.shade(col, 0.75))
        r = self.knob_r
        kx, ky = self.track.x + int(self.track.w * self.value), self.track.centery
        if hot or self.dragging:
            ui.glow(surf, (kx - r, ky - r, 2 * r, 2 * r), col, radius=r, spread=max(4, int(7 * s)),
                    strength=0.9 if self.dragging else 0.55)
        pygame.draw.circle(surf, col, (kx, ky), r)
        pygame.draw.circle(surf, (10, 10, 22), (kx, ky), max(2, int(r * 0.42)))


class Switch:
    """ON / OFF switch (sound effects)."""

    def __init__(self, value, color):
        self.value, self.color = bool(value), color
        self.rect = pygame.Rect(0, 0, 0, 0)

    def press(self, pos):
        if self.rect.inflate(10, 10).collidepoint(pos):
            self.value = not self.value
            return True
        return False

    def draw(self, surf, s, hot):
        r, on = self.rect, self.value
        rad = r.h // 2
        pygame.draw.rect(surf, ui.shade(self.color, 0.28) if on else ui.TRACK, r, border_radius=rad)
        pygame.draw.rect(surf, self.color if on else (ui.EDGE_HI if hot else ui.EDGE), r, 1,
                         border_radius=rad)
        kr = max(3, rad - max(2, int(3 * s)))
        kx = r.right - rad if on else r.x + rad
        pygame.draw.circle(surf, self.color if on else ui.TEXT_DIM, (kx, r.centery), kr)
        px = max(8, int(10 * s))
        if on:
            ui.draw_text(surf, "ON", px, self.color, ((r.x + kx - kr) // 2 + 1, r.centery),
                         bold=True, anchor="center")
        else:
            ui.draw_text(surf, "OFF", px, ui.TEXT_DIM, ((kx + kr + r.right) // 2, r.centery),
                         bold=True, anchor="center")


class SelectBox:
    """A value box that opens a scrollable list below it (or above, when there's no room)."""
    ROWS = 8

    def __init__(self, label, options, idx, color, fmt=str):
        self.label, self.color, self.fmt = label, color, fmt
        self.options = list(options) or ["(none)"]
        self.selected = _clamp(idx, 0, len(self.options) - 1)
        self._open = False
        self._scroll = 0
        self._hot = self.selected        # highlighted row while the list is open
        self.rect = self.row = pygame.Rect(0, 0, 0, 0)
        self._s = 1.0
        self._bounds = (0, 10 ** 6)      # the open list stays between these y values

    @property
    def value(self):
        return self.options[self.selected]

    def place(self, rect, label_h, s, bounds):
        self.rect = pygame.Rect(rect)
        self.row = pygame.Rect(rect.x, rect.y - label_h, rect.w, rect.h + label_h)
        self._s, self._bounds = s, bounds

    @property
    def rh(self):
        return max(18, int(28 * self._s))

    def _pad(self):
        return max(3, int(5 * self._s))

    def geom(self):
        """(rect of the open list, rows it shows)."""
        pad, gap = self._pad(), max(2, int(4 * self._s))
        top, bottom = self._bounds
        n = min(self.ROWS, len(self.options))
        fit_below = (bottom - (self.rect.bottom + gap) - 2 * pad) // self.rh
        fit_above = ((self.rect.y - gap) - top - 2 * pad) // self.rh
        if fit_below >= n or fit_below >= fit_above:
            n = max(1, min(n, fit_below))
            return pygame.Rect(self.rect.x, self.rect.bottom + gap, self.rect.w,
                               n * self.rh + 2 * pad), n
        n = max(1, min(n, fit_above))
        h = n * self.rh + 2 * pad
        return pygame.Rect(self.rect.x, self.rect.y - gap - h, self.rect.w, h), n

    def open(self):
        self._open = True
        self._hot = self.selected
        _, n = self.geom()
        self._scroll = _clamp(self.selected - n // 2, 0, max(0, len(self.options) - n))

    def close(self):
        self._open = False

    def index_at(self, pos):
        lr, n = self.geom()
        if not lr.collidepoint(pos):
            return None
        i = (pos[1] - lr.y - self._pad()) // self.rh
        if 0 <= i < n and self._scroll + i < len(self.options):
            return self._scroll + i
        return None

    def on_mouse_scroll(self, dy):
        if self._open:
            _, n = self.geom()
            self._scroll = _clamp(self._scroll - dy, 0, max(0, len(self.options) - n))

    def move_hot(self, d):
        _, n = self.geom()
        self._hot = _clamp(self._hot + d, 0, len(self.options) - 1)
        if self._hot < self._scroll:
            self._scroll = self._hot
        elif self._hot >= self._scroll + n:
            self._scroll = self._hot - n + 1

    def step(self, d):
        i = _clamp(self.selected + d, 0, len(self.options) - 1)
        changed = i != self.selected
        self.selected = i
        return changed

    def draw(self, surf, s, hot):
        r = self.rect
        ui.draw_text(surf, self.label, max(9, int(13 * s)), ui.TEXT if hot else ui.TEXT_MUTED,
                     (r.x, self.row.y))
        if self._open:
            border = self.color
        elif hot:
            border = ui.mix(self.color, ui.EDGE, 0.45)
        else:
            border = ui.EDGE
        ui.panel(surf, r, fill=ui.shade(self.color, 0.08) if hot else (14, 14, 32), alpha=235,
                 border=border, radius=max(4, int(7 * s)))
        px = max(10, int(15 * s))
        cpx = max(8, int(11 * s))
        caret = ui.text("▲" if self._open else "▼", cpx,
                        self.color if (hot or self._open) else ui.shade(self.color, 0.75))
        cx = r.right - int(12 * s) - caret.get_width()
        surf.blit(caret, (cx, r.centery - caret.get_height() // 2))
        txt = ui.fit(self.fmt(self.value), px, cx - r.x - int(22 * s))
        ui.draw_text(surf, txt, px, ui.TEXT, (r.x + int(12 * s), r.centery), anchor="midleft")

    def draw_list(self, surf, s):
        if not self._open:
            return
        lr, n = self.geom()
        pad = self._pad()
        ui.glow(surf, lr, self.color, radius=max(4, int(8 * s)), spread=int(10 * s), strength=0.35)
        ui.panel(surf, lr, fill=(9, 9, 22), alpha=250, border=self.color, radius=max(4, int(8 * s)))
        scroll = len(self.options) > n
        sbw = max(3, int(4 * s)) if scroll else 0
        px = max(10, int(14 * s))
        isz = max(8, int(11 * s))
        for i in range(n):
            idx = self._scroll + i
            if idx >= len(self.options):
                break
            rr = pygame.Rect(lr.x + pad, lr.y + pad + i * self.rh,
                             lr.w - 2 * pad - (sbw + pad if scroll else 0), self.rh)
            sel, hot = idx == self.selected, idx == self._hot
            if hot:
                ui.panel(surf, rr, fill=ui.shade(self.color, 0.22), alpha=240, border=None,
                         radius=max(3, int(5 * s)), top_hi=False)
            tx = rr.x + int(10 * s)
            label = ui.fit(self.fmt(self.options[idx]), px, rr.right - tx - isz - int(18 * s), sel)
            ui.draw_text(surf, label, px,
                         ui.TEXT if hot else (self.color if sel else ui.TEXT_MUTED),
                         (tx, rr.centery), bold=sel, anchor="midleft")
            if sel:
                ui.icon_check(surf, pygame.Rect(rr.right - int(10 * s) - isz,
                                                rr.centery - isz // 2, isz, isz), self.color)
        if scroll:
            track = pygame.Rect(lr.right - pad - sbw, lr.y + pad, sbw, lr.h - 2 * pad)
            pygame.draw.rect(surf, ui.TRACK, track, border_radius=sbw // 2)
            th = max(int(16 * s), track.h * n // len(self.options))
            ty = track.y + (track.h - th) * self._scroll // max(1, len(self.options) - n)
            pygame.draw.rect(surf, self.color, (track.x, ty, sbw, th), border_radius=sbw // 2)


class Segmented:
    """A row of options, one of them selected."""

    def __init__(self, options, idx, labels, colors):
        self.options, self.labels, self.colors = list(options), list(labels), list(colors)
        self.index = _clamp(idx, 0, len(self.options) - 1)
        self.rect = self.row = pygame.Rect(0, 0, 0, 0)
        self.cells = []

    @property
    def value(self):
        return self.options[self.index]

    def place(self, rect, s):
        self.rect = self.row = pygame.Rect(rect)
        self.cells = ui.split_row(self.rect, len(self.options), max(4, int(8 * s)))

    def cell_at(self, pos):
        for i, c in enumerate(self.cells):
            if c.collidepoint(pos):
                return i
        return None

    def step(self, d, wrap=False):
        n = len(self.options)
        i = (self.index + d) % n if wrap else _clamp(self.index + d, 0, n - 1)
        changed = i != self.index
        self.index = i
        return changed

    def draw(self, surf, s, mouse):
        for i, c in enumerate(self.cells):
            ui.segment(surf, c, self.labels[i], self.colors[i], s, selected=(i == self.index),
                       hovered=mouse is not None and c.collidepoint(mouse))


class Action:
    """A push button (TEST SOUND, CHECK FOR UPDATES, BACK, SAVE)."""

    def __init__(self, label, color, icon=None):
        self.label, self.color, self.icon = label, color, icon
        self.rect = self.row = pygame.Rect(0, 0, 0, 0)

    def place(self, rect):
        self.rect = self.row = pygame.Rect(rect)


# ── Settings screen ───────────────────────────────────────────────
class SettingsScreen:
    def __init__(self, screen, audio_manager, save_data, renderer=None, updates=None):
        self.screen, self.audio, self.save_data = screen, audio_manager, save_data
        self.renderer = renderer          # given when opened from the pause menu
        self.updates = updates            # the app's UpdateChecker (no UPDATES section if None)
        self._tick = 0.0
        self._flash = 0.0                 # time left on the SAVED badge
        self._lay_key = None
        self._mouse = pygame.mouse.get_pos() if pygame.mouse.get_focused() else None
        self._build()

    # ── controls ──────────────────────────────────────────────────
    def _build(self):
        st = self.save_data.get("settings", {})
        a = self.audio
        self.sl_master = Slider("Master", st.get("master_volume", 0.8), NEON_CYAN)
        self.sl_notes = Slider("Notes", st.get("note_volume", 0.9), NEON_GREEN)
        self.sl_music = Slider("Menu music", st.get("music_volume", 0.5), NEON_PURPLE)
        self.sl_sfx = Slider("Sound effects", st.get("sfx_volume", 0.7), NEON_YELLOW)
        self.sfx_switch = Switch(st.get("sfx_enabled", True), NEON_YELLOW)
        self.sliders = [self.sl_master, self.sl_notes, self.sl_music, self.sl_sfx]

        eng = st.get("note_sound_mode", "soundfont")
        self.engine_seg = Segmented(ENGINES, ENGINES.index(eng) if eng in ENGINES else 0,
                                    [ENGINE_LABEL[e] for e in ENGINES], [NEON_CYAN] * 3)

        # Soundfonts: category, then the file in it
        try:
            from game.fluidsynth_engine import list_sf2_categorized
            self._sf2_cats = list_sf2_categorized()
        except Exception:
            self._sf2_cats = {}
        cats = sorted(self._sf2_cats, key=lambda c: (c == "uncategorized", c)) or ["pianos"]
        self._sf2_saved = st.get("sf2_file", "pianos/piano.sf2")
        cat, fname = (self._sf2_saved.split("/", 1) if "/" in self._sf2_saved
                      else ("uncategorized", self._sf2_saved))
        self._sf2_saved_parts = (cat, fname)
        if cat not in cats:               # saved soundfont is gone: offer the default piano
            cat, fname = ("pianos", "piano.sf2") if "pianos" in cats else (cats[0], "")
        ci = cats.index(cat)
        self.sf2_cat_sel = SelectBox("Category", cats, ci, NEON_CYAN, _cat_name)
        files = self._sf2_cats.get(cats[ci]) or ["(none)"]
        self.sf2_file_sel = SelectBox("Instrument", files, files.index(fname) if fname in files
                                      else 0, NEON_YELLOW, _sf2_name)
        self.sf2_sel = self.sf2_file_sel             # older name
        self._sf2_cat_shown = cats[ci]

        # MIDI out
        refresh = getattr(a, "_refresh_midi_out", None)
        if callable(refresh):
            try:
                refresh()
            except Exception:
                pass
        ports = ["(none)"] + list(getattr(a, "available_out_ports", None) or [])
        none_label = "No devices found" if len(ports) == 1 else "Auto (first device)"
        port = st.get("midi_out_port", "(none)")
        self.port_sel = SelectBox("Output device", ports, ports.index(port) if port in ports else 0,
                                  NEON_PINK, lambda p: none_label if p == "(none)" else p)
        self.vel_sl = Slider("Velocity sent", st.get("midi_out_velocity", 100) / 127.0, NEON_PINK,
                             _vel_text)
        self.btn_test = Action("TEST SOUND", NEON_CYAN, ui.icon_note)

        gm = st.get("default_game_mode", MODE_TESTING)
        self.gm_seg = Segmented(ui.MODES, ui.MODES.index(gm) if gm in ui.MODES
                                else ui.MODES.index(MODE_TESTING),
                                [ui.mode_name(m) for m in ui.MODES],
                                [ui.mode_color(m) for m in ui.MODES])
        vf = st.get("vanish_frac", 0.67)
        vals = [v for v, _ in PERSPECTIVES]
        self.vp_seg = Segmented(vals, min(range(len(vals)), key=lambda i: abs(vals[i] - vf)),
                                [lab for _, lab in PERSPECTIVES], [NEON_CYAN] * len(vals))

        self.btn_update = Action("CHECK FOR UPDATES", NEON_CYAN, ui.icon_refresh)
        self.btn_back = Action("BACK", NEON_CYAN)
        self.btn_save = Action("SAVE", NEON_GREEN, ui.icon_check)
        self._focus = self.sl_master
        self._mode_at_open = gm
        self._clean = self._values()
        self._lay_key = None
        self._layout()

    def _rows(self):
        """The controls in keyboard order (the instrument rows depend on the engine)."""
        rows = [*self.sliders, self.engine_seg]
        eng = self.engine_seg.value
        if eng == "soundfont":
            rows += [self.sf2_cat_sel, self.sf2_file_sel]
        elif eng == "midi_out":
            rows += [self.port_sel, self.vel_sl]
        rows += [self.btn_test, self.gm_seg, self.vp_seg]
        if self.updates is not None:
            rows.append(self.btn_update)
        return rows + [self.btn_back, self.btn_save]

    def _boxes(self):
        eng = self.engine_seg.value
        if eng == "soundfont":
            return [self.sf2_cat_sel, self.sf2_file_sel]
        return [self.port_sel] if eng == "midi_out" else []

    def _open_box(self):
        for b in (self.sf2_cat_sel, self.sf2_file_sel, self.port_sel):
            if b._open:
                return b
        return None

    def _all_sliders(self):
        return (*self.sliders, self.vel_sl)

    # ── values ────────────────────────────────────────────────────
    def _sf2_entry(self):
        cat, fname = self.sf2_cat_sel.value, self.sf2_file_sel.value
        if fname == "(none)":
            return self._sf2_saved
        return fname if cat == "uncategorized" else f"{cat}/{fname}"

    def _values(self):
        """The settings this screen edits, as they would be saved."""
        return {
            "master_volume":     round(self.sl_master.value, 3),
            "music_volume":      round(self.sl_music.value, 3),
            "sfx_volume":        round(self.sl_sfx.value, 3),
            "note_volume":       round(self.sl_notes.value, 3),
            "sfx_enabled":       bool(self.sfx_switch.value),
            "note_sound_mode":   self.engine_seg.value,
            "midi_out_port":     self.port_sel.value,
            "default_game_mode": self.gm_seg.value,
            "midi_out_velocity": int(round(self.vel_sl.value * 127)),
            "vanish_frac":       self.vp_seg.value,
            "sf2_file":          self._sf2_entry(),
        }

    def _dirty(self):
        return self._values() != self._clean

    @property
    def default_mode_changed(self):
        """True once a new default mode has been saved here (the app then switches to it;
        otherwise the mode the player last picked stays)."""
        return self.save_data.get("settings", {}).get("default_game_mode",
                                                      MODE_TESTING) != self._mode_at_open

    def _live(self):
        """Volumes are heard right away, and the instrument list follows the category."""
        cat = self.sf2_cat_sel.value
        if cat != self._sf2_cat_shown:
            self._sf2_cat_shown = cat
            files = self._sf2_cats.get(cat) or ["(none)"]
            scat, sfile = self._sf2_saved_parts
            keep = sfile if cat == scat else self.sf2_file_sel.value
            self.sf2_file_sel.options = files
            self.sf2_file_sel.selected = files.index(keep) if keep in files else 0
            self.sf2_file_sel.close()
        a = self.audio
        a.master_volume = self.sl_master.value
        a.music_volume = self.sl_music.value
        a.sfx_volume = self.sl_sfx.value
        a.note_volume = self.sl_notes.value
        a.sfx_enabled = self.sfx_switch.value
        a.update_volumes()

    def _revert_live(self):
        """Leaving without saving: the volumes go back to their saved values."""
        st = self.save_data.get("settings", {})
        a = self.audio
        a.master_volume = st.get("master_volume", 0.8)
        a.music_volume = st.get("music_volume", 0.5)
        a.sfx_volume = st.get("sfx_volume", 0.7)
        a.note_volume = st.get("note_volume", 0.9)
        a.sfx_enabled = st.get("sfx_enabled", True)
        a.update_volumes()

    def _save(self):
        settings = dict(self.save_data.get("settings", {}))   # keep keys this screen doesn't edit
        settings.update(self._values())
        settings.pop("menu_music_file", None)   # menu music always comes from songs/_menu_music
        self.save_data["settings"] = settings
        # Reloads the soundfont (and re-renders the menu music) only if the soundfont changed
        self.audio.apply_settings(settings)
        if self.renderer:                       # opened from the pause menu: applies right away
            self.renderer._vanish_frac = settings.get("vanish_frac", 0.67)
        from game.save_system import save_game
        save_game(self.save_data)
        self._sf2_saved = settings["sf2_file"]
        self._sf2_saved_parts = (self.sf2_cat_sel.value, self.sf2_file_sel.value)
        self._clean = self._values()
        self._flash = 2.5

    # ── input ─────────────────────────────────────────────────────
    def handle_event(self, event) -> Optional[str]:
        disp = pygame.display.get_surface()
        if disp is not None:
            self.screen = disp
        self._layout()
        et = event.type
        if et in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP):
            self._mouse = event.pos
        elif et == pygame.WINDOWLEAVE:
            self._mouse = None                # no hover highlight while the pointer is away
        result = None
        if et == pygame.MOUSEMOTION:
            self._on_motion(event.pos)
        elif et == pygame.MOUSEBUTTONDOWN and event.button == 1:
            result = self._on_click(event.pos)
        elif et == pygame.MOUSEBUTTONUP and event.button == 1:
            self._on_release()
        elif et == pygame.MOUSEWHEEL:
            self._on_wheel(event.y)
        elif et == pygame.KEYDOWN:
            result = self._on_key(event.key)
        if result != "back":
            self._live()
        return result

    def _sfx(self, name):
        try:
            self.audio.play_sfx(name)
        except Exception:
            pass

    def _changed(self, sound="click"):
        self._live()          # apply first, so the sound plays at the new volume
        self._sfx(sound)

    def _on_motion(self, pos):
        for sl in self._all_sliders():
            if sl.dragging:
                sl.drag(pos)
                return
        box = self._open_box()
        if box:
            i = box.index_at(pos)
            if i is not None:
                box._hot = i
            return
        for c in self._rows():               # the row under the pointer gets the focus
            if c.row.collidepoint(pos):
                self._focus = c
                return

    def _on_click(self, pos):
        box = self._open_box()
        if box:                               # a click anywhere closes the list
            i = box.index_at(pos)
            box.close()
            if i is not None:
                self._pick(box, i)
            return None
        if self.sfx_switch.press(pos):
            self._focus = self.sl_sfx
            self._changed()
            return None
        for c in self._rows():
            if isinstance(c, Slider):
                if c.press(pos):
                    self._focus = c
                    return None
            elif isinstance(c, Segmented):
                i = c.cell_at(pos)
                if i is not None:
                    self._focus = c
                    if i != c.index:
                        c.index = i
                        self._changed()
                    return None
            elif isinstance(c, SelectBox):
                if c.rect.collidepoint(pos):
                    self._focus = c
                    c.open()
                    self._sfx("click")
                    return None
            elif c.rect.collidepoint(pos):    # Action
                self._focus = c
                return self._press(c)
        return None

    def _on_release(self):
        for sl in self._all_sliders():
            if sl.dragging:
                sl.dragging = False
                self._changed("hover")         # a tick at the new volume

    def _on_wheel(self, dy):
        box = self._open_box()
        if box:
            box.on_mouse_scroll(dy)
            return
        if self._mouse is None or not dy:
            return
        for c in self._rows():
            if isinstance(c, Slider) and c.row.collidepoint(self._mouse):
                if c.step(1 if dy > 0 else -1):
                    self._changed("hover")
                return

    def _on_key(self, key):
        box = self._open_box()
        if box:
            if key == pygame.K_UP:
                box.move_hot(-1)
            elif key == pygame.K_DOWN:
                box.move_hot(1)
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                box.close()
                self._pick(box, box._hot)
            elif key == pygame.K_ESCAPE:
                box.close()
                self._sfx("back")
            return None
        if key == pygame.K_ESCAPE:
            return self._back()
        rows = self._rows()
        f = self._focus if self._focus in rows else rows[0]
        if key in (pygame.K_UP, pygame.K_DOWN):
            self._focus = rows[(rows.index(f) + (-1 if key == pygame.K_UP else 1)) % len(rows)]
            self._sfx("hover")
        elif key in (pygame.K_LEFT, pygame.K_RIGHT):
            d = -1 if key == pygame.K_LEFT else 1
            if isinstance(f, Action):
                if f in (self.btn_back, self.btn_save):
                    self._focus = self.btn_save if d > 0 else self.btn_back
                    self._sfx("hover")
            elif f.step(d):
                self._changed("hover" if isinstance(f, Slider) else "click")
        elif key == pygame.K_SPACE:
            if isinstance(f, Action):
                return self._press(f)
            if isinstance(f, SelectBox):
                f.open()
                self._sfx("click")
            elif f is self.sl_sfx:
                self.sfx_switch.value = not self.sfx_switch.value
                self._changed()
            elif isinstance(f, Segmented):
                f.step(1, wrap=True)
                self._changed()
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            if isinstance(f, Action):
                return self._press(f)
            self._save_now()
        return None

    def _pick(self, box, i):
        changed = i != box.selected
        box.selected = i
        self._changed()                       # refreshes the instrument list on a new category
        if changed and box is self.sf2_cat_sel and len(self.sf2_file_sel.options) > 1:
            self.sf2_file_sel.open()           # next: the instrument in that category
            self._focus = self.sf2_file_sel

    def _press(self, b):
        if b is self.btn_test:
            self.audio.play_note(60, 90, 1.0)
            return None
        if b is self.btn_update:
            self._press_update()
            return None
        if b is self.btn_save:
            self._save_now()
            return None
        return self._back()

    def _press_update(self):
        """CHECK FOR UPDATES asks GitHub (in the background). Once a newer version is known,
        the button opens its download page instead."""
        u = self.updates
        if u is None or u.checking:
            return
        if u.available:
            self._sfx("confirm")
            u.open_page()
        else:
            self._sfx("click")
            u.check()

    def _save_now(self):
        self._live()
        self._save()
        self._sfx("confirm")

    def _back(self):
        if self._dirty():
            self._revert_live()
        self._sfx("back")
        return "back"

    def update(self, dt):
        self._tick += dt
        self._flash = max(0.0, self._flash - dt)

    # ── layout ────────────────────────────────────────────────────
    def _layout(self):
        W, H = self.screen.get_size()
        key = (W, H, self.engine_seg.value)
        if key == self._lay_key:
            return
        self._lay_key = key
        self._W, self._H = W, H
        s = self._s = ui.scale_for(W, H)
        m = int(24 * s)
        self.head_h = int(72 * s)
        foot = ui.footer_rect(W, H, s)
        top, bottom = self.head_h + int(14 * s), foot.y - int(14 * s)
        pw = (W - 3 * m) // 2
        L = self.p_left = pygame.Rect(m, top, pw, max(40, bottom - top))
        R = self.p_right = pygame.Rect(2 * m + pw, top, W - 3 * m - pw, L.h)
        pad = int(22 * s)
        small = max(9, int(13 * s))
        sec_h = ui.font(small, True).get_height()
        desc_h = ui.font(small).get_height()
        lab_h = desc_h + int(5 * s)
        seg_h, box_h, row_h, row_gap = int(34 * s), int(36 * s), int(44 * s), int(10 * s)
        bounds = (self.head_h + 4, foot.y - 4)
        pos = self._pos = {}

        # Left: VOLUME, INSTRUMENT
        x, w, y = L.x + pad, L.w - 2 * pad, L.y + pad
        pos["volume"] = (x, y, w)
        y += sec_h + int(12 * s)
        for sl in self.sliders:
            sl.place(pygame.Rect(x, y, w, row_h), s)
            y += row_h + row_gap
        vpx = max(10, int(15 * s))
        sw = self.sfx_switch.rect = pygame.Rect(0, 0, int(50 * s), int(22 * s))
        sw.midright = (x + w - ui.text_w("100%", vpx, True) - int(14 * s),
                       self.sl_sfx.row.y + ui.font(vpx).get_height() // 2)
        y += int(10 * s)
        pos["instrument"] = (x, y, w)
        y += sec_h + int(12 * s)
        self.engine_seg.place(pygame.Rect(x, y, w, seg_h), s)
        y += seg_h + int(8 * s)
        pos["engine_desc"] = (x, y, w)
        y += desc_h + int(16 * s)
        eng = self.engine_seg.value
        if eng == "soundfont":
            cw, g = int(w * 0.4), int(12 * s)
            self.sf2_cat_sel.place(pygame.Rect(x, y + lab_h, cw, box_h), lab_h, s, bounds)
            self.sf2_file_sel.place(pygame.Rect(x + cw + g, y + lab_h, w - cw - g, box_h),
                                    lab_h, s, bounds)
            y += lab_h + box_h + int(16 * s)
        elif eng == "midi_out":
            self.port_sel.place(pygame.Rect(x, y + lab_h, w, box_h), lab_h, s, bounds)
            y += lab_h + box_h + int(12 * s)
            self.vel_sl.place(pygame.Rect(x, y, w, row_h), s)
            y += row_h + int(14 * s)
        bpx = max(9, int(13 * s))
        bh = int(32 * s)
        bw = ui.text_w(self.btn_test.label, bpx, True) + int(bpx * 1.4) + int(32 * s)
        self.btn_test.place(pygame.Rect(x + w - bw, y, bw, bh))
        pos["status"] = pygame.Rect(x, y, w - bw - int(12 * s), bh)

        # Right: DEFAULT MODE, HIGHWAY PERSPECTIVE, KEYS, then BACK / SAVE at the bottom
        x, w, y = R.x + pad, R.w - 2 * pad, R.y + pad
        pos["mode"] = (x, y, w)
        y += sec_h + int(12 * s)
        self.gm_seg.place(pygame.Rect(x, y, w, seg_h), s)
        y += seg_h + int(8 * s)
        pos["mode_desc"] = (x, y, w)
        y += desc_h + int(22 * s)
        pos["highway"] = (x, y, w)
        y += sec_h + int(12 * s)
        self.vp_seg.place(pygame.Rect(x, y, w, int(80 * s)), s)
        y += int(80 * s) + int(8 * s)
        pos["highway_desc"] = (x, y, w)
        y += desc_h + int(22 * s)
        pos["keys"] = (x, y, w)
        # (KEYS is a heading, two rows of keycaps and a line of text: see _draw_right)
        cap_h = ui.hints_surface([("ESC", "Pause")], s).get_height()
        y += sec_h + int(12 * s) + cap_h + int(8 * s) + cap_h + int(6 * s) + desc_h
        bh, g = int(44 * s), int(12 * s)
        by = R.bottom - pad - bh
        half = (w - g) // 2
        self.btn_back.place(pygame.Rect(x, by, half, bh))
        self.btn_save.place(pygame.Rect(x + half + g, by, w - half - g, bh))
        pos["note"] = (x, by - int(10 * s), w)
        # UPDATES under KEYS: a heading, the status and CHECK FOR UPDATES, a line of text.
        # (A short window moves it up rather than into the note above BACK / SAVE.)
        ubh = int(32 * s)
        block = sec_h + int(12 * s) + ubh + int(8 * s) + desc_h
        y = min(y + int(22 * s), by - int(10 * s) - desc_h - int(14 * s) - block)
        pos["updates"] = (x, y, w)
        y += sec_h + int(12 * s)
        bpx = max(9, int(13 * s))
        bw = ui.text_w(self.btn_update.label, bpx, True) + int(bpx * 1.4) + int(32 * s)
        self.btn_update.place(pygame.Rect(x + w - bw, y, bw, ubh))
        pos["upd_status"] = pygame.Rect(x, y, w - bw - int(12 * s), ubh)
        pos["upd_line"] = (x, y + ubh + int(8 * s), w)

    # ── drawing ───────────────────────────────────────────────────
    def _hover(self, rect):
        return (self._mouse is not None and rect.collidepoint(self._mouse)
                and self._open_box() is None)

    def draw(self):
        self._layout()
        surf, s = self.screen, self._s
        ui.backdrop(surf, self._tick)
        dirty = self._dirty()
        self._draw_header(dirty)
        rad = max(6, int(12 * s))
        ui.panel(surf, self.p_left, radius=rad)
        ui.panel(surf, self.p_right, radius=rad)
        box = self._open_box()
        rows = self._rows()
        focus = self._focus if self._focus in rows else None
        if focus is not None and not isinstance(focus, Action) and box is None:
            self._draw_focus(focus.row)
        self._draw_left(focus)
        self._draw_right(focus, dirty)
        if box:
            box.draw_list(surf, s)              # last, so nothing covers the open list
        ui.footer(surf, s, self._hints(dirty))

    def _draw_header(self, dirty):
        surf, s, W = self.screen, self._s, self._W
        m = int(24 * s)
        cy = self.head_h // 2 + int(2 * s)
        tr = ui.draw_text(surf, "SETTINGS", int(30 * s), NEON_CYAN, (m, cy), bold=True,
                          anchor="midleft", shadow=True)
        x = tr.right + int(14 * s)
        if dirty:
            ui.pill(surf, "UNSAVED CHANGES", NEON_ORANGE, (x, cy), s, anchor="midleft", dot=True)
        elif self._flash > 0:
            ui.pill(surf, "SAVED", NEON_GREEN, (x, cy), s, anchor="midleft", dot=True)
        status = getattr(self.audio, "music_loading_status", "")
        if status:                              # e.g. the menu music re-rendering after a save
            px = max(9, int(13 * s))
            r = ui.draw_text(surf, status.replace("...", "…"), px, NEON_CYAN, (W - m, cy),
                             anchor="midright")
            ui.spinner(surf, (r.x - int(12 * s), cy), max(4, int(6 * s)), NEON_CYAN, self._tick)
        pygame.draw.line(surf, ui.EDGE, (m, self.head_h - 1), (W - m, self.head_h - 1))

    def _draw_focus(self, rect):
        s = self._s
        r = rect.inflate(int(28 * s), int(14 * s))
        ui.panel(self.screen, r, fill=ui.shade(NEON_CYAN, 0.07), alpha=200,
                 border=ui.mix(NEON_CYAN, ui.EDGE, 0.6), radius=max(4, int(9 * s)), top_hi=False)
        bw = max(2, int(3 * s))
        pygame.draw.rect(self.screen, NEON_CYAN,
                         (r.x + max(3, int(5 * s)), r.y + int(9 * s), bw, r.h - int(18 * s)),
                         border_radius=bw)

    def _draw_left(self, focus):
        surf, s = self.screen, self._s
        mouse = self._mouse if self._open_box() is None else None
        px = max(9, int(13 * s))
        x, y, w = self._pos["volume"]
        ui.section(surf, "VOLUME", x, y, w, s, right="heard as you change it")
        self.sl_sfx.enabled = self.sfx_switch.value
        for sl in self.sliders:
            sl.draw(surf, s, focus is sl or sl.dragging)
        self.sfx_switch.draw(surf, s, focus is self.sl_sfx)

        x, y, w = self._pos["instrument"]
        ui.section(surf, "INSTRUMENT", x, y, w, s, right="what plays the notes")
        self.engine_seg.draw(surf, s, mouse)
        eng = self.engine_seg.value
        x, y, w = self._pos["engine_desc"]
        ui.draw_text(surf, ui.fit(ENGINE_DESC[eng], px, w), px, ui.TEXT_MUTED, (x, y))
        for b in self._boxes():
            b.draw(surf, s, focus is b or b._open)
        if eng == "midi_out":
            self.vel_sl.draw(surf, s, focus is self.vel_sl or self.vel_sl.dragging)

        kind, txt, col = self._instrument_status()
        r = self._pos["status"]
        isz = max(8, int(12 * s))
        c = (r.x + isz // 2, r.centery)
        if kind == "spin":
            ui.spinner(surf, c, isz // 2, col, self._tick)
        else:
            ui.status_dot(surf, c, col, s)
        tx = r.x + isz + int(8 * s)
        ui.draw_text(surf, ui.fit(txt, px, r.right - tx), px, col, (tx, r.centery), anchor="midleft")
        b = self.btn_test
        ui.button(surf, b.rect, b.label, s, b.color, selected=focus is b, hovered=self._hover(b.rect),
                  t=self._tick, px=max(9, int(13 * s)), icon=b.icon,
                  idle_text=ui.shade(b.color, 0.85))

    def _draw_right(self, focus, dirty):
        surf, s, t = self.screen, self._s, self._tick
        mouse = self._mouse if self._open_box() is None else None
        px = max(9, int(13 * s))
        x, y, w = self._pos["mode"]
        ui.section(surf, "DEFAULT MODE", x, y, w, s, right="the mode KeyFall starts in")
        self.gm_seg.draw(surf, s, mouse)
        x, y, w = self._pos["mode_desc"]
        ui.draw_text(surf, ui.fit(ui.MODE_DESC.get(self.gm_seg.value, ""), px, w), px,
                     ui.TEXT_MUTED, (x, y))

        x, y, w = self._pos["highway"]
        ui.section(surf, "HIGHWAY PERSPECTIVE", x, y, w, s)
        self._draw_perspective(mouse)
        x, y, w = self._pos["highway_desc"]
        ui.draw_text(surf, ui.fit("How much the highway narrows toward the top. DEEP is the "
                                  "original look.", px, w), px, ui.TEXT_MUTED, (x, y))

        x, y, w = self._pos["keys"]
        y += ui.section(surf, "KEYS", x, y, w, s, right="during a song") + int(12 * s)
        r = ui.hints(surf, [("ESC", "Pause"), ("F5", "Restart"), ("F10", "End song"),
                            ("F11", "Fullscreen")], (x, y), s, anchor="topleft",
                     interactive=False)          # (a list of keys, not buttons)
        r = ui.hints(surf, [(PLAY_KEYS, "Play notes")], (x, r.bottom + int(8 * s)), s,
                     anchor="topleft", interactive=False)
        ui.draw_text(surf, ui.fit("Lowest note first. They work with or without a MIDI keyboard.",
                                  px, w), px, ui.TEXT_DIM, (x, r.bottom + int(6 * s)))
        if self.updates is not None:
            self._draw_updates(focus)

        x, yb, w = self._pos["note"]
        if dirty:
            txt, col = ("Unsaved changes: SAVE keeps them, BACK throws them away.",
                        ui.mix(NEON_ORANGE, ui.TEXT_MUTED, 0.35))
        else:
            txt, col = ("Volumes change as you drag. Everything else applies when you save.",
                        ui.TEXT_DIM)
        ui.draw_text(surf, ui.fit(txt, px, w), px, col, (x + w // 2, yb), anchor="midbottom")
        bpx = max(10, int(18 * s))
        b = self.btn_back
        ui.button(surf, b.rect, b.label, s, b.color, selected=focus is b,
                  hovered=self._hover(b.rect), t=t, px=bpx, idle_text=ui.shade(b.color, 0.85))
        b = self.btn_save          # lit up while there is something to save
        ui.button(surf, b.rect, b.label, s, b.color, selected=focus is b,
                  hovered=dirty or self._hover(b.rect), t=t, px=bpx, icon=b.icon,
                  idle_text=ui.shade(b.color, 0.8))

    def _draw_updates(self, focus):
        """UPDATES: what the last check found, CHECK FOR UPDATES (DOWNLOAD once there is a
        newer version) and when it last checked."""
        surf, s, t, u = self.screen, self._s, self._tick, self.updates
        px = max(9, int(13 * s))
        x, y, w = self._pos["updates"]
        rpx = max(9, int(12 * s))                 # (ui.section's size for the right text)
        ui.section(surf, "UPDATES", x, y, w, s, right=ui.fit(f"you have {u.current}", rpx, w // 2))
        kind, txt = u.status()
        col = {"busy": NEON_CYAN, "new": NEON_GREEN, "ok": NEON_GREEN,
               "warn": NEON_ORANGE}.get(kind, ui.TEXT_MUTED)
        r = self._pos["upd_status"]
        isz = max(8, int(12 * s))
        c = (r.x + isz // 2, r.centery)
        if kind == "busy":
            ui.spinner(surf, c, isz // 2, col, t)
        else:
            ui.status_dot(surf, c, col, s)
        tx = r.x + isz + int(8 * s)
        ui.draw_text(surf, ui.fit(txt, px, r.right - tx), px, col, (tx, r.centery), anchor="midleft")

        b, new = self.btn_update, u.available
        if u.checking:
            label, color, icon = "CHECKING…", NEON_CYAN, None
        elif new:
            label, color, icon = f"DOWNLOAD {new}", NEON_GREEN, ui.icon_download
            if ui.text_w(label, px, True) + int(px * 1.4) + int(20 * s) > b.rect.w:
                label = "DOWNLOAD"
        else:
            label, color, icon = b.label, NEON_CYAN, ui.icon_refresh
        ui.button(surf, b.rect, label, s, color, selected=focus is b, hovered=self._hover(b.rect),
                  t=t, px=px, enabled=not u.checking, icon=icon, idle_text=ui.shade(color, 0.85))
        x, y, w = self._pos["upd_line"]          # (the link is brighter: it's to be read)
        ui.draw_text(surf, ui.fit(u.detail_text(), px, w), px,
                     ui.TEXT_MUTED if u.open_failed else ui.TEXT_DIM, (x, y))

    def _draw_perspective(self, mouse):
        """Three cells, each with a small drawing of the highway at that perspective."""
        surf, s, seg = self.screen, self._s, self.vp_seg
        lab_px = max(9, int(14 * s))
        lab_h = ui.font(lab_px, True).get_height()
        rad = max(4, int(7 * s))
        col = NEON_CYAN
        for i, cell in enumerate(seg.cells):
            sel = i == seg.index
            hov = mouse is not None and cell.collidepoint(mouse)
            if sel:
                ui.panel(surf, cell, fill=ui.shade(col, 0.24), alpha=245, border=col, width=2,
                         radius=rad)
            elif hov:
                ui.panel(surf, cell, fill=ui.shade(col, 0.1), alpha=230,
                         border=ui.mix(col, ui.EDGE, 0.4), radius=rad)
            else:
                ui.panel(surf, cell, alpha=200, border=ui.EDGE, radius=rad)
            y0 = cell.y + int(9 * s)
            y1 = cell.bottom - lab_h - int(12 * s)
            bw = min(int(cell.w * 0.62), int((y1 - y0) * 1.9))
            tw = max(2, int(bw * (1.0 - seg.options[i] * 8.0 / 9.0)))   # as the renderer does
            cx = cell.centerx
            line = col if sel else (ui.TEXT_MUTED if hov else ui.TEXT_DIM)
            pts = [(cx - tw // 2, y0), (cx + tw // 2, y0), (cx + bw // 2, y1), (cx - bw // 2, y1)]
            pygame.draw.polygon(surf, ui.shade(col, 0.16) if sel else (16, 16, 34), pts)
            for k in range(1, 5):
                pygame.draw.line(surf, ui.shade(line, 0.45), (cx - tw // 2 + tw * k // 5, y0),
                                 (cx - bw // 2 + bw * k // 5, y1))
            for lane, d, nc in ((1, 0.62, NEON_PINK), (3, 0.25, NEON_YELLOW)):   # two notes
                wd = bw + (tw - bw) * d
                ny = y1 - (y1 - y0) * d
                lw = wd / 5
                nx = cx - wd / 2 + lw * lane
                nh = max(2, int(7 * s * (1 - 0.45 * d)))
                pygame.draw.rect(surf, nc if sel else ui.shade(nc, 0.45),
                                 (int(nx + 1), int(ny - nh), max(1, int(lw - 2)), nh),
                                 border_radius=max(1, int(2 * s)))
            pygame.draw.polygon(surf, line, pts, 1)
            ui.draw_text(surf, seg.labels[i], lab_px,
                         ui.TEXT if (sel or hov) else ui.shade(col, 0.85),
                         (cx, cell.bottom - int(7 * s)), bold=True, anchor="midbottom")

    def _pending(self):
        """What SAVE would switch the notes to, when that's not what plays them now."""
        a, eng = self.audio, self.engine_seg.value
        cur = getattr(a, "note_sound_mode", eng)
        if eng == "soundfont":
            if eng != cur or self._sf2_entry() != getattr(a, "sf2_entry", self._sf2_entry()):
                return f"SAVE to switch to {_sf2_name(self.sf2_file_sel.value)}"
        elif eng == "synth":
            if eng != cur:
                return "SAVE to switch to the built-in synth"
        elif len(self.port_sel.options) > 1:          # MIDI out, with devices to send to
            port = self.port_sel.value
            if port == "(none)":
                if eng != cur:
                    return "SAVE to send notes to the first MIDI device"
            elif eng != cur or port != getattr(a, "midi_out_name", None):
                return f"SAVE to send notes to {port}"
        return ""

    def _instrument_status(self):
        """(kind, text, colour) for the line under the instrument controls."""
        a = self.audio
        if getattr(a, "_loading", False):
            return "spin", "Loading the instrument…", NEON_CYAN
        pending = self._pending()
        if pending:
            return "dot", pending, NEON_ORANGE
        eng = self.engine_seg.value
        if eng == "soundfont":
            try:
                st = a.soundfont_status()
            except Exception:
                st = "Soundfont unavailable"
            if st.startswith("Ready"):
                return "dot", f"Ready: {_cap(ui.soundfont_name(a))}", NEON_GREEN
            return "dot", st, NEON_ORANGE
        if eng == "synth":
            return "dot", "Ready: built-in synth", NEON_GREEN
        if getattr(a, "midi_out_port", None) and getattr(a, "note_sound_mode", "") == "midi_out":
            return "dot", f"Sending notes to {getattr(a, 'midi_out_name', None) or 'MIDI out'}", \
                NEON_GREEN
        if len(self.port_sel.options) == 1:
            return "dot", "No MIDI devices. Plug one in and reopen Settings.", NEON_ORANGE
        return "dot", "No MIDI output connected", NEON_ORANGE

    def _hints(self, dirty):
        if self._open_box():
            return [(("↑", "↓"), "Choose"), ("ENTER", "Pick"), ("ESC", "Close")]
        f = self._focus
        items = [(("↑", "↓"), "Select")]
        if isinstance(f, Action):
            items.append(("ENTER", "Press"))
        else:
            items.append((("←", "→"), "Adjust" if isinstance(f, Slider) else "Change"))
            if isinstance(f, SelectBox):
                items.append(("SPACE", "Open list"))
            elif f is self.sl_sfx:
                items.append(("SPACE", "Sounds on/off"))
            items.append(("ENTER", "Save"))
        items.append(("ESC", "Discard & back" if dirty else "Back"))
        return items
