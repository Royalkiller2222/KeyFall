"""
KeyFall - App
Owns the window and the main loop and switches between the screens (menus, gameplay, pause,
results, settings, free play). The gameplay overlays (countdown, EASY wait prompt) and the
pause menu live here. Everything is drawn with the shared UI kit in game.ui.
"""

import os, sys, math, time
import pygame
from typing import Optional, List

from game import ui
from game.constants import *
from game.midi_handler import MidiParser, MidiInputHandler, SongData, create_demo_song
from game.song_library import scan_songs_library, SongEntry, DIFFICULTY_COLORS
from game.renderer import HighwayRenderer
from game.gameplay import GameplayEngine, XPSystem
from game.menus import MainMenu, SongSelectMenu, ResultsScreen
from game.settings_screen import SettingsScreen
from game.freeplay import FreePlay
from game.audio import AudioManager
from game.save_system import load_save, save_game, add_leaderboard_entry, leaderboard_key
from game.song_organizer import organize_flat_midis
from game.version import VERSION
from game import selftest

STATE_PAUSE_MENU = "pause_menu"
STATE_FREEPLAY   = "freeplay"

# QWERTY keys that play the song's lanes, lowest lane first
PLAY_KEYS = [pygame.K_a, pygame.K_s, pygame.K_d, pygame.K_f, pygame.K_g,
             pygame.K_h, pygame.K_j, pygame.K_k, pygame.K_l,
             pygame.K_q, pygame.K_w, pygame.K_e, pygame.K_r, pygame.K_t]


class PauseMenu:
    """In-game pause menu: one panel over the dimmed highway, with the run's details."""
    OPTIONS = ["RESUME", "RESTART", "SETTINGS", "MODE", "MAIN MENU"]
    RETURNS = ["resume", "restart", "settings", "toggle_mode", "menu"]
    COLORS  = [NEON_CYAN, NEON_CYAN, NEON_CYAN, None, NEON_PURPLE]   # None: the mode's colour

    def __init__(self, screen: pygame.Surface, current_mode: str, info: Optional[dict] = None,
                 audio=None):
        self.screen = screen
        self.mode = current_mode
        self.info = info or {}      # title, difficulty, speed, time, duration, autoplay
        self.audio = audio
        self.selected = 0
        self._tick = 0.0
        self._mouse = None
        self._ov = None

    @property
    def s(self):
        return ui.scale_for(*self.screen.get_size())

    def update(self, dt):
        self._tick += dt

    def _geom(self):
        """(panel rect, padding, y of the first button, button height, button step)"""
        W, H = self.screen.get_size()
        s = self.s
        pad = int(22 * s)
        bh, step = max(28, int(44 * s)), max(33, int(54 * s))
        head_h, foot_h = int(150 * s), int(62 * s)
        n = len(self.OPTIONS)
        box = pygame.Rect(0, 0, min(W - int(32 * s), int(440 * s)),
                          pad + head_h + step * (n - 1) + bh + foot_h)
        box.center = (W // 2, H // 2 - int(14 * s))
        return box, pad, box.y + pad + head_h, bh, step

    def _btn_rect(self, i):
        box, pad, top, bh, step = self._geom()
        return pygame.Rect(box.x + pad, top + i * step, box.w - 2 * pad, bh)

    def _btn_at(self, pos):
        for i in range(len(self.OPTIONS)):
            if self._btn_rect(i).collidepoint(pos):
                return i
        return None

    def _next_mode(self):
        modes = ui.MODES
        return modes[(modes.index(self.mode) + 1) % len(modes)] if self.mode in modes else modes[0]

    def handle_event(self, event) -> Optional[str]:
        if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
            self._mouse = event.pos
        if event.type == pygame.MOUSEMOTION:
            i = self._btn_at(event.pos)
            if i is not None and i != self.selected:
                self.selected = i
                if self.audio:
                    self.audio.play_sfx("hover")
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            i = self._btn_at(event.pos)
            if i is not None:
                self.selected = i
                return self.RETURNS[i]
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(self.OPTIONS)
                if self.audio:
                    self.audio.play_sfx("hover")
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(self.OPTIONS)
                if self.audio:
                    self.audio.play_sfx("hover")
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                return self.RETURNS[self.selected]
            elif event.key == pygame.K_ESCAPE:
                return "resume"
        return None

    def draw(self):
        surf, s, t = self.screen, self.s, self._tick
        W, H = surf.get_size()
        if self._ov is None or self._ov.get_size() != (W, H):   # built once per window size
            self._ov = pygame.Surface((W, H), pygame.SRCALPHA)
            self._ov.fill((3, 3, 12, 185))
        surf.blit(self._ov, (0, 0))

        box, pad, btn_top, bh, step = self._geom()
        rad = max(6, int(14 * s))
        ui.glow(surf, box, NEON_CYAN, rad, int(14 * s), 0.22)
        ui.panel(surf, box, alpha=238, radius=rad)
        cx, inner = box.centerx, box.w - 2 * pad
        info = self.info

        y = ui.draw_text(surf, "PAUSED", int(34 * s), NEON_CYAN, (cx, box.y + pad), bold=True,
                         anchor="midtop", shadow=True).bottom + int(6 * s)
        title = info.get("title", "")
        if title:
            y = ui.draw_text(surf, ui.fit(title, int(18 * s), inner, True), int(18 * s), ui.TEXT,
                             (cx, y), bold=True, anchor="midtop").bottom + int(10 * s)
        tags = []
        d = info.get("difficulty")
        if d:
            tags.append((d, DIFFICULTY_COLORS.get(d, ui.TEXT_MUTED), False))
        if info.get("speed"):
            tags.append((f"SPEED {round(info['speed'] * 100)}%", NEON_CYAN, False))
        if info.get("autoplay"):
            tags.append(("NOT SCORED", NEON_ORANGE, True))
        pill_h = ui.font(max(9, int(13 * s)), True).get_height() + max(3, int(5 * s))
        if tags:
            ui.pill_row(surf, tags, (cx, y + pill_h // 2), s)
        y += pill_h + int(14 * s)

        dur = info.get("duration") or 0.0
        if dur > 0:     # where the song was paused
            cur = max(0.0, min(dur, info.get("time", 0.0)))
            px = max(9, int(12 * s))
            label = f"{ui.fmt_time(cur)} / {ui.fmt_time(dur)}"
            tw = ui.text_w(label, px) + int(10 * s)
            bar = pygame.Rect(box.x + pad, y, inner - tw, max(4, int(6 * s)))
            ui.bar(surf, bar, cur / dur, NEON_CYAN)
            ui.draw_text(surf, label, px, ui.TEXT_MUTED, (box.right - pad, bar.centery),
                         anchor="midright")

        for i, opt in enumerate(self.OPTIONS):
            r = self._btn_rect(i)
            col = self.COLORS[i] or ui.mode_color(self.mode)
            label = f"MODE: {ui.mode_name(self.mode)}" if opt == "MODE" else opt
            hov = self._mouse is not None and r.collidepoint(self._mouse)
            ui.button(surf, r, label, s, col, selected=(i == self.selected), hovered=hov, t=t,
                      px=int(19 * s), markers=True)

        # What the current mode does - and, while MODE is focused, what ENTER switches to
        y = self._btn_rect(len(self.OPTIONS) - 1).bottom + int(14 * s)
        px = max(9, int(13 * s))
        y = ui.draw_text(surf, ui.fit(ui.MODE_DESC.get(self.mode, ""), px, inner), px,
                         ui.TEXT_MUTED, (cx, y), anchor="midtop").bottom + int(5 * s)
        if self.OPTIONS[self.selected] == "MODE":
            nxt = self._next_mode()
            msg = f"ENTER switches to {ui.mode_name(nxt)}"
            if nxt == MODE_TESTING and not info.get("autoplay"):
                msg += " - this run will no longer be scored"
            ui.draw_text(surf, ui.fit(msg, px, inner), px,
                         NEON_ORANGE if nxt == MODE_TESTING else ui.TEXT_DIM, (cx, y),
                         anchor="midtop")

        ui.hints(surf, [(("↑", "↓"), "Select"), ("ENTER", "Confirm"), ("ESC", "Resume")],
                 (cx, min(H - int(8 * s), box.bottom + int(18 * s))), s,
                 anchor="midtop" if box.bottom + int(48 * s) < H else "midbottom")


class App:
    def __init__(self):
        # Must come before pygame.init(), which opens the mixer with default settings
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.init()
        pygame.display.set_caption(WINDOW_TITLE)
        self._fullscreen = False
        self.screen = pygame.display.set_mode(
            (SCREEN_WIDTH, SCREEN_HEIGHT),
            pygame.DOUBLEBUF | pygame.RESIZABLE)
        self.clock = pygame.time.Clock()

        # Hide system cursor — we draw our own in menus, hide in-game
        pygame.mouse.set_visible(False)
        self._mouse_pos = pygame.mouse.get_pos()
        self._mouse_in = bool(pygame.mouse.get_focused())

        self.save_data = load_save()
        self.xp_system = XPSystem(self.save_data.get("total_xp", 0))

        self.state = STATE_MENU
        self.audio = AudioManager()
        # Only allow auto-play of menu music when in a menu state
        self.audio._music_allowed_cb = lambda: self.state in (STATE_MENU, STATE_SETTINGS)
        # Loads the saved soundfont, then renders and starts the menu music - all in one
        # background thread (this used to start the 118 MB soundfont load twice)
        self.audio.apply_settings(self.save_data.get("settings", {}))

        self.midi_input = MidiInputHandler()
        self.midi_input.on_live = self._on_live_midi
        self.midi_input.connect()

        organize_flat_midis()  # auto-organize any flat .mid files
        self.songs: List[SongEntry] = self._load_songs()

        # Default to TESTING mode (#3)
        self.current_mode = self.save_data.get("settings",{}).get("default_game_mode", MODE_TESTING)

        self.state = STATE_MENU
        self.engine: Optional[GameplayEngine] = None
        self.renderer: Optional[HighwayRenderer] = None
        self.current_song: Optional[SongData] = None
        self.pause_menu: Optional[PauseMenu] = None
        self._kb_pitch_map = {}
        self._key_hints = {}    # pitch -> computer key letter, shown on the in-game keyboard
        self._kb_down = set()   # QWERTY keys held in-game (highlighted on the keyboard)

        self._build_main_menu()
        self.audio.start_menu_music()

        self._selftest = (selftest.SelfTest(self, os.path.join(BASE_DIR, "keyfall_selftest.txt"))
                          if selftest.ENABLED else None)

    def _W(self): return self.screen.get_width()
    def _H(self): return self.screen.get_height()

    def _load_songs(self):
        return scan_songs_library(progress=self._draw_loading)

    def _draw_loading(self, done, total, name):
        """Shown while songs are scanned; new or changed MIDIs are parsed (then cached)."""
        pygame.event.pump()   # keeps Windows from marking the window "Not Responding"
        surf = self.screen
        W, H = surf.get_size()
        s, t = ui.scale_for(W, H), time.perf_counter()
        ui.backdrop(surf, t)
        y = int(H * 0.30)
        y += ui.logo(surf, W // 2, y, int(80 * s), t) + int(34 * s)
        bar = pygame.Rect(0, 0, int(min(W * 0.5, 560 * s)), max(6, int(10 * s)))
        bar.midtop = (W // 2, y)
        frac = (done + 1) / max(1, total)
        ui.glow(surf, (bar.x, bar.y, max(bar.h, int(bar.w * frac)), bar.h), NEON_CYAN,
                bar.h // 2, int(8 * s), 0.5)
        ui.bar(surf, bar, frac, NEON_CYAN, border=ui.EDGE)
        y = ui.draw_text(surf, f"Loading songs  {done + 1}/{total}", int(16 * s), ui.TEXT,
                         (W // 2, bar.bottom + int(16 * s)), bold=True, anchor="midtop").bottom
        ui.draw_text(surf, ui.fit(name, int(14 * s), int(W * 0.7)), int(14 * s), ui.TEXT_MUTED,
                     (W // 2, y + int(6 * s)), anchor="midtop")
        ui.draw_text(surf, VERSION, max(9, int(12 * s)), ui.TEXT_DIM,
                     (W - int(14 * s), H - int(10 * s)), anchor="bottomright")
        pygame.display.flip()

    def _refresh_songs(self):
        """Rescan the songs folder (REFRESH / F5 in song select)."""
        organize_flat_midis()  # organize any newly dropped files
        self.songs = self._load_songs()
        if getattr(self, "song_select", None):
            self.song_select.set_entries(self.songs)

    def _build_main_menu(self):
        self.main_menu = MainMenu(
            self.screen,
            self.midi_input.available_ports,
            self.xp_system.level,
            self.xp_system.total_xp,
            self.xp_system.level_progress,
            audio=self.audio,
            song_count=len(self.songs))

    def _open_song_select(self):
        """A fresh song select (from the main menu)."""
        self.song_select = SongSelectMenu(
            self.screen, self.songs, self.current_mode,
            bool(self.midi_input.selected_port), audio=self.audio,
            pb_lookup=lambda song, mode, speed:
                self._get_personal_best(leaderboard_key(song, mode, speed)))
        self.song_select._refresh_cb = self._refresh_songs
        self.audio.stop_menu_music(500)    # so the song preview can be heard
        self.state = STATE_SONG_SELECT

    def _run_info(self):
        """The current run's details, for the pause menu and the results screen."""
        song, e = self.current_song, self.engine
        return {"title": song.title, "difficulty": getattr(song, "difficulty", "") or "",
                "mode": e.mode, "speed": e.playback_speed, "time": max(0.0, e.current_time),
                "duration": song.duration_sec, "autoplay": e.used_autoplay}

    def _toggle_fullscreen(self):
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.screen = pygame.display.set_mode(
                (0,0), pygame.FULLSCREEN|pygame.DOUBLEBUF)
        else:
            self.screen = pygame.display.set_mode(
                (SCREEN_WIDTH,SCREEN_HEIGHT),
                pygame.DOUBLEBUF|pygame.RESIZABLE)
        if self.renderer:
            self.renderer.screen = self.screen
            self.renderer.on_resize(self._W(), self._H())

    def _start_song(self, song: SongData, mode: str, speed: float = 1.0):
        self.audio.play_sfx("song_start")
        self.current_song = song
        self.current_mode = mode
        self._current_speed = speed   # restarts keep the chosen practice speed
        self.engine   = GameplayEngine(song, mode)
        self.renderer = HighwayRenderer(self.screen)
        # Apply vanishing point AFTER renderer is created
        vf = self.save_data.get("settings",{}).get("vanish_frac", 0.67)
        self.renderer._vanish_frac = vf
        self.audio.all_notes_off(120)   # cut song-preview / previous-run notes
        self.engine.on_auto_note = self._on_auto_note
        self._kb_pitch_map = {PLAY_KEYS[i]: p for i, p in
                              enumerate(self.engine.lane_pitch_map[:len(PLAY_KEYS)])}
        self._key_hints = {p: pygame.key.name(k).upper() for k, p in self._kb_pitch_map.items()}
        self._kb_down = set()
        self.audio.stop_menu_music(300)
        self.engine.playback_speed = speed
        # Start engine immediately with a negative time offset equal to lookahead
        # so notes begin at the very top of the highway
        lookahead = NOTE_LOOKAHEAD_SECS / speed
        self._countdown = lookahead
        self._countdown_active = True
        self.engine.start(time_offset=lookahead)  # current_time starts negative
        self.state = STATE_PLAYING

    def _restart_song(self):
        mode = self.engine.mode if self.engine else self.current_mode
        self._start_song(self.current_song, mode, getattr(self, "_current_speed", 1.0))

    def _on_auto_note(self, pitch, velocity, duration=0.5):
        self.audio.play_note(pitch, velocity, duration)
        if self.renderer and self.engine and pitch in self.engine.lane_pitch_map:
            li = self.engine.lane_pitch_map.index(pitch)
            self.renderer.spawn_hit_particles(li, self.engine.num_lanes,
                                              LANE_COLORS[li%len(LANE_COLORS)], "PERFECT")

    def _apply_result(self, result):
        """Visual + SFX feedback for a judged key press."""
        if result is None or not self.renderer or not self.engine:
            return
        lpm = self.engine.lane_pitch_map
        if result.note.pitch not in lpm:
            return
        li = lpm.index(result.note.pitch)
        if result.quality == "MISS":
            self.renderer.spawn_miss_particles(li, self.engine.num_lanes)
            self.audio.play_sfx("miss")
        else:
            self.renderer.spawn_hit_particles(li, self.engine.num_lanes,
                                              LANE_COLORS[li % len(LANE_COLORS)], result.quality)
            self.audio.play_sfx(result.quality.lower())

    def _on_live_midi(self, kind, a, b):
        """MIDI thread: sound right away, without waiting for the next frame."""
        if self.state not in (STATE_PLAYING, STATE_FREEPLAY):
            return
        if kind == "on":
            self.audio.note_on(a, b)        # always hear what you play
        elif kind == "off":
            self.audio.note_off(a)
        elif kind == "sustain":
            self.audio.set_sustain(a)

    def _on_midi_event(self, t, kind, a, b):
        """Main thread: the game's reaction to a MIDI event (its sound already played).
        Presses are judged by `t`, the moment the MIDI message arrived."""
        if self.state == STATE_FREEPLAY and self.free_play:
            if kind == "on":
                self.free_play.press(a, b, flash=0.5, sound=False)
            elif kind == "off":
                self.free_play.release(a, sound=False)
            elif kind == "sustain":
                self.free_play.set_sustain(a, sound=False)
        elif self.state == STATE_PLAYING and self.engine and kind == "on":
            self._apply_result(self.engine.on_midi_note(a, b, True, t))

    def _leaderboard_key(self):
        """Personal bests compare like with like: same chart, mode and speed."""
        return leaderboard_key(self.current_song, self.engine.mode, self.engine.playback_speed)

    def _get_personal_best(self, key):
        entries = self.save_data.get("leaderboard",{}).get(key,[])
        return max(entries, key=lambda e:e["score"]) if entries else None

    def _end_song(self):
        if not self.engine or not self.current_song: return
        stats = self.engine.stats
        autoplay = self.engine.used_autoplay
        judged = stats.hits_perfect + stats.hits_great + stats.hits_good + stats.misses
        pb = None
        if not autoplay:   # autoplay (TESTING) runs earn no XP and no leaderboard entry
            key = self._leaderboard_key()
            pb  = self._get_personal_best(key)
            if judged:     # a song ended before any note was played saves nothing
                self.xp_system.add_xp(stats.xp_earned)
                self.save_data["total_xp"] = self.xp_system.total_xp
                add_leaderboard_entry(self.save_data, key, stats)
                save_game(self.save_data)
        self.results_screen = ResultsScreen(
            self.screen, stats, self.current_song.title, self.xp_system, pb, autoplay=autoplay,
            info=self._run_info())
        self.state = STATE_RESULTS
        self.audio.all_notes_off(400)
        self.audio.play_sfx("song_complete")

    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS)/1000.0, 0.02)  # tighter cap at 240fps
            events = pygame.event.get()
            if self._selftest:
                events += self._selftest.events()
            for event in events:
                if event.type == pygame.QUIT: running = False
                if event.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN,
                                  pygame.MOUSEBUTTONUP):
                    self._mouse_pos, self._mouse_in = event.pos, True
                elif event.type == pygame.WINDOWLEAVE:
                    self._mouse_in = False
                if event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self._toggle_fullscreen(); continue
                if event.type == pygame.VIDEORESIZE and not self._fullscreen:
                    self.screen = pygame.display.set_mode(
                        (event.w,event.h),
                        pygame.DOUBLEBUF|pygame.RESIZABLE)
                    if self.renderer:
                        self.renderer.screen=self.screen
                        self.renderer.on_resize(event.w,event.h)
                if self._handle_event(event) == "quit": running = False
            for midi_event in self.midi_input.poll():
                self._on_midi_event(*midi_event)
            self._update(dt)
            self.audio.update()
            self._draw(dt)
            self._draw_fps()
            pygame.display.flip()

        self.audio.shutdown()
        self.midi_input.disconnect()
        exit_code = 0 if self._selftest is None or self._selftest.passed else 1
        pygame.quit(); sys.exit(exit_code)

    def _draw_fps(self):
        """Version + FPS, placed per screen so they never cover anything."""
        surf = self.screen
        W, H = surf.get_size()
        s = ui.scale_for(W, H)
        fps = self.clock.get_fps()
        px = max(9, int(12 * s))
        if self.state in (STATE_PLAYING, STATE_PAUSE_MENU):
            ui.draw_text(surf, f"{fps:.0f} FPS", px, ui.TEXT_DIM,
                         (W - int(8 * s), H - int(4 * s)), anchor="bottomright")
        elif self.state == STATE_FREEPLAY:
            ui.draw_text(surf, f"{VERSION} · {fps:.0f} FPS", px, ui.TEXT_DIM,
                         (W - int(10 * s), int(8 * s)), anchor="topright")
        else:   # menus: right end of the footer bar
            ui.draw_text(surf, f"{VERSION} · {fps:.0f} FPS", px, ui.TEXT_DIM,
                         (W - int(16 * s), ui.footer_rect(W, H, s).centery), anchor="midright")

    def _handle_event(self, event):
        if self.state == STATE_MENU:
            action = self.main_menu.handle_event(event)
            if action == "play":
                self.audio.play_sfx("confirm")
                self._open_song_select()
            elif action == "free play":
                self.audio.play_sfx("confirm")
                self.audio.stop_menu_music(500)
                self.free_play = FreePlay(self.screen, self.audio)
                self.state = STATE_FREEPLAY
            elif action == "settings":
                self.audio.play_sfx("confirm")
                self.settings_screen = SettingsScreen(self.screen,self.audio,self.save_data)
                self._paused_state = STATE_MENU
                self.state = STATE_SETTINGS
            elif action == "quit":
                return "quit"

        elif self.state == STATE_SONG_SELECT:
            result = self.song_select.handle_event(event)
            if result:
                action = result[0]; song = result[1]; mode = result[2]
                speed = result[3] if len(result) > 3 else 1.0
                if action == "play":
                    self.audio.play_sfx("confirm")
                    self._start_song(song, mode, speed=speed)
                elif action == "back":
                    self.audio.play_sfx("back")
                    self.audio.all_notes_off()      # stop the song preview
                    self.state = STATE_MENU
                    self.audio.start_menu_music()   # restart music when going back

        elif self.state == STATE_PLAYING:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Open pause menu instead of just pausing
                    self.engine.pause()
                    self.pause_menu = PauseMenu(self.screen, self.engine.mode,
                                                info=self._run_info(), audio=self.audio)
                    self.state = STATE_PAUSE_MENU
                elif event.key == pygame.K_F5:
                    self._restart_song()
                elif event.key == pygame.K_F10:
                    self._end_song()
                elif event.key in self._kb_pitch_map:
                    pitch = self._kb_pitch_map[event.key]
                    self._kb_down.add(pitch)
                    self.audio.note_on(pitch, 80)   # always hear what you play
                    self._apply_result(self.engine.on_midi_note(pitch, 80, True))
            elif event.type == pygame.KEYUP and event.key in self._kb_pitch_map:
                pitch = self._kb_pitch_map[event.key]
                self._kb_down.discard(pitch)
                self.audio.note_off(pitch)

        elif self.state == STATE_PAUSE_MENU:
            action = self.pause_menu.handle_event(event)
            if action == "resume":
                self.audio.play_sfx("click")
                self.engine.resume()
                self.state = STATE_PLAYING
            elif action == "restart":
                self.audio.play_sfx("confirm")
                self._restart_song()
            elif action == "settings":
                self.audio.play_sfx("confirm")
                self.settings_screen = SettingsScreen(self.screen, self.audio, self.save_data, renderer=self.renderer)
                self._paused_state = self.state
                self.state = STATE_SETTINGS
            elif action == "toggle_mode":
                self.audio.play_sfx("click")
                self.engine.toggle_mode()
                self.pause_menu.mode = self.engine.mode
                self.pause_menu.info["autoplay"] = self.engine.used_autoplay
            elif action == "menu":
                self.audio.play_sfx("back")
                self.audio.all_notes_off()
                self.engine = None; self.renderer = None
                self._build_main_menu()
                self.state = STATE_MENU
                self.audio.start_menu_music()

        elif self.state == STATE_RESULTS:
            action = self.results_screen.handle_event(event)
            if action in ("retry", "songs", "menu"):
                self.audio.stop_sfx("song_complete")
            if action == "retry":
                self.audio.play_sfx("confirm")
                self._restart_song()
            elif action == "songs":
                self.audio.play_sfx("back")
                if getattr(self, "song_select", None):
                    self.song_select._prev_idx = -1     # restarts the song preview
                    self.state = STATE_SONG_SELECT
                else:
                    self._open_song_select()
            elif action == "menu":
                self.audio.play_sfx("back")
                self._build_main_menu()
                self.state = STATE_MENU            # (before starting music: it checks the state)
                self.audio.start_menu_music()

        elif self.state == STATE_FREEPLAY:
            if self.free_play:
                action = self.free_play.handle_event(event)
                if action == "back":
                    self.audio.play_sfx("back")
                    self.audio.all_notes_off()
                    self.free_play = None
                    self._build_main_menu()
                    self.state = STATE_MENU
                    self.audio.start_menu_music()
                elif action == "fullscreen":
                    self._toggle_fullscreen()

        elif self.state == STATE_SETTINGS:
            action = self.settings_screen.handle_event(event)
            if action == "back":
                self.current_mode = self.save_data.get("settings",{}).get(
                    "default_game_mode", MODE_TESTING)
                prev = getattr(self, '_paused_state', STATE_MENU)
                self._paused_state = None
                if prev == STATE_MENU:
                    self._build_main_menu()
                    self.state = STATE_MENU
                    self.audio.start_menu_music()
                elif prev in (STATE_PAUSE_MENU,):
                    # Return to pause menu (song is still paused)
                    self.state = STATE_PAUSE_MENU
                elif prev == STATE_SONG_SELECT:
                    self.state = STATE_SONG_SELECT
                else:
                    self._build_main_menu()
                    self.state = STATE_MENU
                    self.audio.start_menu_music()
        return None

    def _update(self, dt):
        self._cursor_tick = getattr(self, '_cursor_tick', 0.0) + dt
        if self.state == STATE_MENU:
            self.main_menu.update(dt)
        elif self.state == STATE_FREEPLAY and self.free_play:
            self.free_play.update(dt)
            # Try to reconnect MIDI keyboard every 3 seconds if not connected
            if not self.midi_input.selected_port:
                self._midi_retry = getattr(self, '_midi_retry', 0) + dt
                if self._midi_retry > 3.0:
                    self._midi_retry = 0.0
                    self.midi_input.connect()
        elif self.state == STATE_SONG_SELECT:
            self.song_select.update(dt)
        elif self.state == STATE_PLAYING and self.engine:
            if getattr(self, '_countdown_active', False):
                self._countdown -= dt
                if self._countdown <= 0:
                    self._countdown_active = False
            misses = self.engine.update(dt)
            for r in misses:
                if r.quality=="MISS" and self.renderer and r.note.pitch in self.engine.lane_pitch_map:
                    li=self.engine.lane_pitch_map.index(r.note.pitch)
                    self.renderer.spawn_miss_particles(li,self.engine.num_lanes)
                    self.audio.play_sfx("miss")
            if self.engine.song_complete: self._end_song()
        elif self.state == STATE_PAUSE_MENU and self.pause_menu:
            self.pause_menu.update(dt)
        elif self.state == STATE_RESULTS:
            self.results_screen.update(dt)
        elif self.state == STATE_SETTINGS:
            self.settings_screen.update(dt)

    def _draw(self, dt):
        W,H = self._W(),self._H()
        in_menu = self.state in (STATE_MENU, STATE_SONG_SELECT,
                                 STATE_RESULTS, STATE_SETTINGS, STATE_PAUSE_MENU)

        if self.state == STATE_MENU:
            self.main_menu.screen=self.screen
            self.main_menu.W,self.main_menu.H=W,H
            self.main_menu.draw()

        elif self.state == STATE_SONG_SELECT:
            self.song_select.screen=self.screen
            self.song_select.W,self.song_select.H=W,H
            self.song_select.draw()

        elif self.state in (STATE_PLAYING, STATE_PAUSE_MENU):
            if self.engine and self.renderer:
                e = self.engine
                waiting = e.is_waiting
                self.renderer.draw(
                    self.current_song, e.current_time, e.num_lanes, e.lane_pitch_map, dt,
                    pressed_keys=self.midi_input._pressed_keys | self._kb_down,
                    # Without a MIDI keyboard, show which computer key plays which piano key
                    key_hints=None if self.midi_input.selected_port else self._key_hints,
                    targets=set(e.get_waiting_pitches()) if waiting else None)
                self.renderer.draw_hud(
                    e.stats, e.mode, e.get_song_progress(), max(0.0, e.current_time),
                    self.current_song.duration_sec, speed=e.playback_speed,
                    autoplay=e.used_autoplay, last_hit_quality=e.last_hit_quality,
                    waiting=waiting, dt=dt)

                if getattr(self, '_countdown_active', False):
                    self._draw_countdown(W, H)
                elif waiting:
                    self._overlay_easy_wait(W, H)

            if self.state == STATE_PAUSE_MENU and self.pause_menu:
                self.pause_menu.screen = self.screen
                self.pause_menu.draw()

        elif self.state == STATE_FREEPLAY and self.free_play:
            self.free_play.draw()

        elif self.state == STATE_RESULTS:
            self.results_screen.screen=self.screen
            self.results_screen.W,self.results_screen.H=W,H
            self.results_screen.draw()

        elif self.state == STATE_SETTINGS:
            self.settings_screen.screen=self.screen
            self.settings_screen.draw()

        # The game's own cursor (the system one stays hidden); none while a song plays
        show_cursor = in_menu
        if self.state == STATE_FREEPLAY and self.free_play:
            fp = self.free_play
            # Only hide cursor if QWERTY or MIDI keys are held (not mouse clicks)
            # Mouse movement always shows cursor
            qwerty_or_midi_held = bool(fp._held - ({fp._mouse_pitch} if fp._mouse_pitch else set()))
            show_cursor = not qwerty_or_midi_held
            # If mouse moved recently, always show cursor
            if fp._mouse_moved:
                show_cursor = True
                fp._mouse_moved = False  # consume the flag

        pygame.mouse.set_visible(False)
        if show_cursor and self._mouse_in:
            ui.cursor(self.screen, self._mouse_pos, self._cursor_tick, ui.scale_for(W, H))

    def _draw_countdown(self, W, H):
        """3-2-1 before the first note (a draining ring), over a card with the run's details.
        It all sits in the far half of the highway, and the card fades out during the last
        number, so the first notes are in clear view as they arrive."""
        s = ui.scale_for(W, H)
        third = NOTE_LOOKAHEAD_SECS / self.engine.playback_speed / 3.0
        left = max(0.0, self._countdown)
        n = max(1, min(3, math.ceil(left / third)))
        frac = max(0.0, min(1.0, (left - (n - 1) * third) / third))   # 1 -> 0 per number
        col = (NEON_GREEN, NEON_YELLOW, NEON_RED)[n - 1]              # 3 red, 2 yellow, 1 green
        R, rw = int(44 * s), max(4, int(7 * s))
        size = 2 * R + 4
        ring = getattr(self, "_cd_ring", None)
        if ring is None or ring.get_width() != size:
            ring = self._cd_ring = pygame.Surface((size, size), pygame.SRCALPHA)
        ring.fill((0, 0, 0, 0))
        c = (size // 2, size // 2)
        pygame.draw.circle(ring, (6, 6, 16, 220), c, R - 1)
        ui.ring(ring, c, R, rw, frac, col)
        px = int(54 * s * (1 + 0.3 * max(0.0, (frac - 0.85) / 0.15))) // 2 * 2   # pop in
        ui.draw_text(ring, str(n), px, col, c, bold=True, anchor="center")
        ring.set_alpha(int(255 * min(1.0, left / 0.25)))
        top = self.renderer.HWY_TOP + int(16 * s)
        self.screen.blit(ring, (W // 2 - size // 2, top))
        card = self._countdown_card(W, H)
        a = 1.0 if n > 1 else max(0.0, (frac - 0.5) / 0.5)
        if a > 0:
            card.set_alpha(int(255 * a))
            self.screen.blit(card, (W // 2 - card.get_width() // 2, top + size + int(14 * s)))

    def _countdown_card(self, W, H):
        """The run's details shown under the countdown (cached; changes only with the run)."""
        song, e = self.current_song, self.engine
        key = (W, H, song.title, getattr(song, "difficulty", ""), e.mode, e.playback_speed)
        if getattr(self, "_cd_key", None) == key:
            return self._cd_card
        s = ui.scale_for(W, H)
        pad = int(18 * s)
        cw = min(W - int(40 * s), int(560 * s))
        hs = ui.hints_surface([("ESC", "Pause"), ("F5", "Restart"), ("F10", "End song"),
                               ("F11", "Fullscreen")], s)
        head_px, title_px, desc_px = max(9, int(14 * s)), int(22 * s), max(9, int(14 * s))
        pill_h = ui.font(max(9, int(13 * s)), True).get_height() + max(3, int(5 * s))
        ch = (pad + ui.font(head_px, True).get_height() + int(6 * s)
              + ui.font(title_px, True).get_height() + int(10 * s) + pill_h + int(12 * s)
              + ui.font(desc_px).get_height() + int(16 * s) + hs.get_height() + pad)
        card = pygame.Surface((cw, ch), pygame.SRCALPHA)
        ui.panel(card, card.get_rect(), alpha=228, radius=max(6, int(12 * s)))
        cx = cw // 2
        y = ui.draw_text(card, "GET READY", head_px, NEON_CYAN, (cx, pad), bold=True,
                         anchor="midtop").bottom + int(6 * s)
        y = ui.draw_text(card, ui.fit(song.title, title_px, cw - 2 * pad, True), title_px,
                         ui.TEXT, (cx, y), bold=True, anchor="midtop").bottom + int(10 * s)
        tags = []
        d = getattr(song, "difficulty", "")
        if d:
            tags.append((d, DIFFICULTY_COLORS.get(d, ui.TEXT_MUTED), False))
        tags.append((ui.mode_name(e.mode), ui.mode_color(e.mode), False))
        tags.append((f"SPEED {round(e.playback_speed * 100)}%", NEON_CYAN, False))
        ui.pill_row(card, tags, (cx, y + pill_h // 2), s)
        y += pill_h + int(12 * s)
        y = ui.draw_text(card, ui.fit(ui.MODE_DESC.get(e.mode, ""), desc_px, cw - 2 * pad),
                         desc_px, ui.TEXT_MUTED, (cx, y), anchor="midtop").bottom + int(16 * s)
        card.blit(hs, hs.get_rect(midtop=(cx, y)))
        self._cd_key, self._cd_card = key, card
        return card

    def _overlay_easy_wait(self, W, H):
        """EASY mode: the song holds until these notes are played."""
        pitches = self.engine.get_waiting_pitches()
        if not pitches:
            return
        surf, s, t = self.screen, ui.scale_for(W, H), self._cursor_tick
        names = [ui.note_name(p) for p in pitches]
        gap, pad = int(8 * s), int(16 * s)
        px = int(20 * s)
        def row_w(px):
            return sum(ui.pill_w(n, s, px) for n in names) + gap * (len(names) - 1)
        while px > 10 and row_w(px) > W * 0.75:     # big chords: smaller chips so they fit
            px -= 2
        lab_px, cap_px = int(18 * s), max(9, int(13 * s))
        lab_w = ui.text_w("PLAY", lab_px, True) + int(14 * s)
        cap = "EASY mode: the song waits until you play these notes"
        pill_h = ui.font(px, True).get_height() + max(3, int(5 * s))
        box = pygame.Rect(0, 0, min(W - int(24 * s),
                                    max(lab_w + row_w(px), ui.text_w(cap, cap_px)) + 2 * pad),
                          pad + pill_h + int(8 * s) + ui.font(cap_px).get_height() + int(12 * s))
        box.midtop = (W // 2, self.renderer.HWY_TOP + int(12 * s))
        ui.glow(surf, box, NEON_GREEN, int(12 * s), int(12 * s), 0.35 + 0.3 * math.sin(t * 4))
        ui.panel(surf, box, alpha=232, border=ui.shade(NEON_GREEN, 0.7), radius=int(12 * s))
        cy = box.y + pad + pill_h // 2
        x = box.centerx - (lab_w + row_w(px)) // 2
        ui.draw_text(surf, "PLAY", lab_px, NEON_GREEN, (x, cy), bold=True, anchor="midleft")
        ui.pill_row(surf, [(n, NEON_GREEN, True) for n in names],
                    (x + lab_w + row_w(px) // 2, cy), s, px=px, gap=gap)
        ui.draw_text(surf, ui.fit(cap, cap_px, box.w - 2 * pad), cap_px, ui.TEXT_MUTED,
                     (box.centerx, box.bottom - int(10 * s)), anchor="midbottom")
