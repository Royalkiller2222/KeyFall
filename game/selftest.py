"""
KeyFall - automated smoke test, enabled with KEYFALL_SELFTEST=1.

build_release.py --selftest (and the GitHub build) runs the real game headless with SDL's
dummy video/audio drivers and this enabled. It drives the actual game loop by injecting input:
menus -> densest song (autoplay) -> pause -> settings + mouse wheel -> mode toggle + key presses
-> results -> hardest chart -> free play -> settings -> quit, and checks the game reached each
screen. The game exits with code 0 only if every check passed; a report is written next to the EXE.
"""

import os
import time

import pygame

ENABLED = os.environ.get("KEYFALL_SELFTEST") == "1"
TIMEOUT_SEC = 240


def _keys(*keys):
    events = []
    for k in keys:
        events.append(pygame.event.Event(pygame.KEYDOWN, key=k, mod=0, unicode="", scancode=0))
        events.append(pygame.event.Event(pygame.KEYUP, key=k, mod=0, unicode="", scancode=0))
    return events


def _click(pos):
    return [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos),
            pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)]


def _wheel():
    return [pygame.event.Event(pygame.MOUSEWHEEL, x=0, y=-1, flipped=False)]


class SelfTest:
    def __init__(self, app, report_path: str):
        self.app = app
        self.report_path = report_path
        self.results = []           # (label, ok, detail)
        self.info = []              # free-form measurements for the report
        self.finished = False
        self._started = time.perf_counter()
        self._next_at = 0.0
        self._pending = None
        self._i = 0
        self._mode_before = None
        self._steps = self._script()

    # ── the script ────────────────────────────────────────────────
    def _script(self):
        from game.constants import (STATE_MENU, STATE_SONG_SELECT, STATE_PLAYING,
                                    STATE_RESULTS, STATE_SETTINGS)
        from game.app import STATE_FREEPLAY, STATE_PAUSE_MENU
        a, K = self.app, pygame

        def at(state):
            return lambda: a.state == state

        # (seconds to wait before checking, label, make_events, check)
        return [
            (1.0, "main menu shown",            None,                                at(STATE_MENU)),
            (1.0, "open song select",           lambda: _keys(K.K_RETURN),           at(STATE_SONG_SELECT)),
            (0.5, "select densest song",        self._select_densest,                self._on_target_song),
            (7.0, "song plays (autoplay)",      lambda: _keys(K.K_RETURN),           self._song_advanced),
            (0.5, "pause menu",                 lambda: _keys(K.K_ESCAPE),           at(STATE_PAUSE_MENU)),
            (0.5, "settings from pause",        lambda: _keys(K.K_DOWN, K.K_DOWN, K.K_RETURN), at(STATE_SETTINGS)),
            (0.5, "mouse wheel in settings",    _wheel,                              at(STATE_SETTINGS)),
            (0.5, "back to pause menu",         lambda: _keys(K.K_ESCAPE),           at(STATE_PAUSE_MENU)),
            (0.5, "toggle mode",                self._toggle_mode,                   lambda: a.engine.mode != self._mode_before),
            (0.5, "resume",                     lambda: _keys(K.K_ESCAPE),           at(STATE_PLAYING)),
            (2.0, "play keys while judged",     lambda: _keys(K.K_a, K.K_s, K.K_d, K.K_f, K.K_g), at(STATE_PLAYING)),
            (1.5, "end song -> results",        lambda: _keys(K.K_F10),              at(STATE_RESULTS)),
            (0.5, "results -> main menu",       lambda: _keys(K.K_ESCAPE),           at(STATE_MENU)),
            (1.0, "song select again",          lambda: _keys(K.K_RETURN),           at(STATE_SONG_SELECT)),
            (0.5, "select hardest chart",       self._select_hardest,                self._on_target_song),
            (6.0, "hardest chart plays",        lambda: _keys(K.K_RETURN),           self._song_advanced),
            (1.5, "end hardest chart",          lambda: _keys(K.K_F10),              at(STATE_RESULTS)),
            (0.5, "back to main menu",          lambda: _keys(K.K_ESCAPE),           at(STATE_MENU)),
            (1.0, "open free play",             lambda: _keys(K.K_DOWN, K.K_RETURN), at(STATE_FREEPLAY)),
            (1.5, "free play keys + sustain",   self._free_play_input,               at(STATE_FREEPLAY)),
            (0.5, "free play -> main menu",     lambda: _keys(K.K_ESCAPE),           at(STATE_MENU)),
            (0.5, "settings from main menu",    lambda: _keys(K.K_DOWN, K.K_DOWN, K.K_RETURN), at(STATE_SETTINGS)),
            (0.5, "mouse wheel in settings",    _wheel,                              at(STATE_SETTINGS)),
            (0.5, "settings -> main menu",      lambda: _keys(K.K_ESCAPE),           at(STATE_MENU)),
        ]

    # ── step helpers ──────────────────────────────────────────────
    def _select_densest(self):
        """Pick the song whose default chart has the most notes."""
        menu = self.app.song_select
        counts = [len(e.get_song(menu._entry_diff(i)).notes) for i, e in enumerate(menu.entries)]
        self._target = (max(range(len(counts)), key=counts.__getitem__), None)
        return _keys(*[pygame.K_DOWN] * self._target[0])

    def _select_hardest(self):
        """Pick the single chart with the most notes in the whole library."""
        menu = self.app.song_select
        best = max(((len(e.get_song(d).notes), i, d) for i, e in enumerate(menu.entries)
                    for d in e.available_difficulties))
        _, idx, diff = best
        self._target = (idx, diff)
        avail = menu.entries[idx].available_difficulties
        steps = avail.index(diff) - avail.index(menu._entry_diff(idx))
        return _keys(*[pygame.K_DOWN] * idx) + _keys(*[pygame.K_RIGHT] * (steps % len(avail)))

    def _on_target_song(self):
        idx, diff = self._target
        menu = self.app.song_select
        return menu.selected == idx and (diff is None or menu._entry_diff(idx) == diff)

    def _song_advanced(self):
        a = self.app
        ok = a.engine is not None and a.engine.current_time > 1.0
        if a.engine is not None:
            self.info.append(f"{a.current_song.title}: {len(a.current_song.notes)} notes, "
                             f"t={a.engine.current_time:.1f}s, {a.clock.get_fps():.0f} FPS, "
                             f"{a.engine.stats.hit_count} hits")
        return ok

    def _toggle_mode(self):
        self._mode_before = self.app.engine.mode
        return _keys(pygame.K_DOWN, pygame.K_RETURN)   # pause menu: SETTINGS -> TOGGLE MODE

    def _free_play_input(self):
        w, h = self.app.screen.get_size()
        sustain_down = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" ", scancode=0)
        sustain_up = pygame.event.Event(pygame.KEYUP, key=pygame.K_SPACE, mod=0, unicode=" ", scancode=0)
        return ([sustain_down] + _keys(pygame.K_z, pygame.K_c, pygame.K_b) + [sustain_up]
                + _click((w // 2, int(h * 0.95))))

    # ── driver (called once per frame by App.run) ─────────────────
    def events(self):
        if self.finished:
            return []
        now = time.perf_counter()
        if now - self._started > TIMEOUT_SEC:
            self.results.append(("finished within time limit", False, f">{TIMEOUT_SEC}s"))
            return self._finish()
        if now < self._next_at:
            return []
        if self._pending:
            label, check = self._pending
            self._pending = None
            try:
                self.results.append((label, bool(check()), ""))
            except Exception as e:  # a broken check is a failure, not a crash
                self.results.append((label, False, repr(e)))
        if self._i >= len(self._steps):
            return self._finish()
        wait, label, make_events, check = self._steps[self._i]
        self._i += 1
        self._next_at = now + wait
        self._pending = (label, check)
        try:
            return make_events() if make_events else []
        except Exception as e:
            self.results.append((label + " (input)", False, repr(e)))
            return []

    @property
    def passed(self) -> bool:
        return self.finished and bool(self.results) and all(ok for _, ok, _ in self.results)

    def _finish(self):
        self.finished = True
        lines = [f"{'PASS' if ok else 'FAIL'}  {label}" + (f"  ({detail})" if detail else "")
                 for label, ok, detail in self.results]
        lines += [f"info  {x}" for x in self.info]
        lines.append(f"RESULT: {'PASSED' if self.passed else 'FAILED'} "
                     f"in {time.perf_counter() - self._started:.0f}s")
        try:
            with open(self.report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError:
            pass
        return [pygame.event.Event(pygame.QUIT)]
