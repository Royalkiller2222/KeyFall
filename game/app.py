"""
KeyFall - App v9
Fixes: cursor hidden in-game, pause menu with back-to-menu,
hint text above keyboard, default testing mode, preview stops music.
"""

import os, sys, math, time
import pygame
from game.fonts import sys_font
from typing import Optional, List

from game.constants import *
from game.midi_handler import MidiParser, MidiInputHandler, SongData, create_demo_song
from game.song_library import scan_songs_library, SongEntry
from game.renderer import HighwayRenderer
from game.gameplay import GameplayEngine, XPSystem
from game.menus import MainMenu, SongSelectMenu, ResultsScreen
from game.settings_screen import SettingsScreen
from game.freeplay import FreePlay
from game.audio import AudioManager
from game.save_system import load_save, save_game, add_leaderboard_entry
from game.song_organizer import organize_flat_midis
from game.version import VERSION
from game import selftest

STATE_PAUSE_MENU = "pause_menu"
STATE_FREEPLAY   = "freeplay"


class PauseMenu:
    """Clickable in-game pause menu."""
    OPTIONS = ["RESUME", "RESTART", "SETTINGS", "TOGGLE MODE", "MAIN MENU"]
    RETURNS = ["resume", "restart", "settings", "toggle_mode", "menu"]

    def __init__(self, screen: pygame.Surface, current_mode: str):
        self.screen = screen
        self.mode = current_mode
        self.selected = 0
        self.fn_title = sys_font("consolas", 52, bold=True)
        self.fn_opt   = sys_font("consolas", 30, bold=True)
        self.fn_hint  = sys_font("consolas", 15)

    def _btn_rect(self, i):
        W, H = self.screen.get_size()
        bw, bh = 320, 52
        y = H//2 - 150 + i * 60
        return pygame.Rect(W//2 - bw//2, y, bw, bh)

    def handle_event(self, event) -> Optional[str]:
        if event.type == pygame.MOUSEMOTION:
            for i in range(len(self.OPTIONS)):
                if self._btn_rect(i).collidepoint(event.pos):
                    self.selected = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.OPTIONS)):
                if self._btn_rect(i).collidepoint(event.pos):
                    return self.RETURNS[i]
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected-1) % len(self.OPTIONS)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected+1) % len(self.OPTIONS)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                return self.RETURNS[self.selected]
            elif event.key == pygame.K_ESCAPE:
                return "resume"
        return None

    def draw(self):
        W, H = self.screen.get_size()
        import math
        # Dim overlay (built once per window size, not every frame)
        if getattr(self, "_ov", None) is None or self._ov.get_size() != (W, H):
            self._ov = pygame.Surface((W, H), pygame.SRCALPHA)
            self._ov.fill((0,0,0,165))
        self.screen.blit(self._ov, (0,0))

        # Title — moved up
        title = self.fn_title.render("PAUSED", True, NEON_CYAN)
        self.screen.blit(title, (W//2-title.get_width()//2, H//2-260))

        # Mode indicator
        mc = {MODE_EASY:NEON_GREEN,MODE_HARD:NEON_RED,MODE_TESTING:NEON_ORANGE}.get(self.mode,GRAY)
        ms = self.fn_hint.render(f"Current mode: {self.mode}", True, mc)
        self.screen.blit(ms, (W//2-ms.get_width()//2, H//2-200))

        # Black rounded backdrop behind all buttons
        pad = 18
        first_r = self._btn_rect(0)
        last_r  = self._btn_rect(len(self.OPTIONS)-1)
        box = pygame.Rect(first_r.x - pad, first_r.y - pad,
                          first_r.w + pad*2,
                          last_r.bottom - first_r.y + pad*2)
        pygame.draw.rect(self.screen, (0,0,0), box, border_radius=12)
        pygame.draw.rect(self.screen, (40,40,60), box, 1, border_radius=12)

        for i, opt in enumerate(self.OPTIONS):
            r = self._btn_rect(i)
            sel = (i == self.selected)
            col = NEON_CYAN if sel else GRAY
            if sel:
                bg_s = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
                bg_s.fill((*col, 40))
                self.screen.blit(bg_s, (r.x, r.y))
            pygame.draw.rect(self.screen, col, r, 2, border_radius=6)
            prefix = "►  " if sel else "   "
            lbl = self.fn_opt.render(prefix + opt, True, WHITE if sel else (180,180,180))
            self.screen.blit(lbl, (r.x+16, r.y+(r.h-lbl.get_height())//2))

        hint = self.fn_hint.render("↑↓ Navigate  ·  ENTER Select  ·  ESC Resume", True, GRAY)
        self.screen.blit(hint, (W//2-hint.get_width()//2, H//2+260))

        # Draw custom cursor inside pause menu
        mx,my = pygame.mouse.get_pos()
        pygame.draw.line(self.screen,NEON_CYAN,(mx-8,my),(mx+8,my),2)
        pygame.draw.line(self.screen,NEON_CYAN,(mx,my-8),(mx,my+8),2)
        pygame.draw.circle(self.screen,NEON_CYAN,(mx,my),4,1)


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

        self._build_main_menu()
        self.audio.start_menu_music()

        self._selftest = (selftest.SelfTest(self, os.path.join(BASE_DIR, "keyfall_selftest.txt"))
                          if selftest.ENABLED else None)

    def _W(self): return self.screen.get_width()
    def _H(self): return self.screen.get_height()

    def _load_songs(self):
        return scan_songs_library()

    def _refresh_songs(self):
        """Reload song library and update song select menu."""
        organize_flat_midis()  # organize any newly dropped files
        self.songs = self._load_songs()
        if hasattr(self, 'song_select') and self.song_select:
            self.song_select.entries = self.songs
            self.song_select.selected = 0
            self.song_select.scroll_offset = 0
            self.song_select._anim_scales = {}
            self.song_select._anim_vels   = {}

    def _build_main_menu(self):
        self.main_menu = MainMenu(
            self.screen,
            self.midi_input.available_ports,
            self.xp_system.level,
            self.xp_system.total_xp,
            self.xp_system.level_progress,
            audio=self.audio)

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
        self.midi_input._callbacks.clear()
        self.midi_input.add_callback(self._on_midi_note)
        keys = [pygame.K_a,pygame.K_s,pygame.K_d,pygame.K_f,pygame.K_g,
                pygame.K_h,pygame.K_j,pygame.K_k,pygame.K_l,
                pygame.K_q,pygame.K_w,pygame.K_e,pygame.K_r,pygame.K_t]
        self._kb_pitch_map = {keys[i]:p for i,p in
                              enumerate(self.engine.lane_pitch_map[:len(keys)])}
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

    def _on_midi_note(self, pitch, velocity, is_on):
        if self.state == STATE_FREEPLAY and self.free_play:
            if is_on and velocity > 0:
                self.free_play.press(pitch, velocity, flash=0.5)
            else:
                self.free_play.release(pitch)
            return
        if self.state == STATE_PLAYING and self.engine:
            if not (is_on and velocity > 0):
                self.audio.note_off(pitch)
                return
            t_press = time.perf_counter()
            self.audio.note_on(pitch, velocity)   # always hear what you play
            self._apply_result(self.engine.on_midi_note(pitch, velocity, True, t_press))

    def _leaderboard_key(self):
        """Personal bests compare like with like: same chart, mode and speed."""
        song = self.current_song
        return (f"{song.title} | {getattr(song, 'difficulty', '') or '-'} | "
                f"{self.engine.mode} | {round(self.engine.playback_speed * 100)}%")

    def _get_personal_best(self, key):
        entries = self.save_data.get("leaderboard",{}).get(key,[])
        return max(entries, key=lambda e:e["score"]) if entries else None

    def _end_song(self):
        if not self.engine or not self.current_song: return
        stats = self.engine.stats
        autoplay = self.engine.used_autoplay
        pb = None
        if not autoplay:   # autoplay (TESTING) runs earn no XP and no leaderboard entry
            key = self._leaderboard_key()
            pb  = self._get_personal_best(key)
            self.xp_system.add_xp(stats.xp_earned)
            self.save_data["total_xp"] = self.xp_system.total_xp
            add_leaderboard_entry(self.save_data, key, stats)
            save_game(self.save_data)
        self.results_screen = ResultsScreen(
            self.screen, stats, self.current_song.title, self.xp_system, pb, autoplay=autoplay)
        self.state = STATE_RESULTS
        self.midi_input._callbacks.clear()
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
            self._update(dt)
            self.audio.update()
            self._draw(dt)
            # Version + FPS — position depends on state
            fps = self.clock.get_fps()
            if not hasattr(self, '_fps_font'):
                self._fps_font = sys_font("consolas", 13)
            W2 = self.screen.get_width()
            H2 = self.screen.get_height()
            if self.state == STATE_FREEPLAY:
                # Top right — version + fps together
                txt = self._fps_font.render(f"{VERSION}  {fps:.0f} FPS", True, (0,160,255))
                self.screen.blit(txt, (W2 - txt.get_width() - 8, 6))
            elif self.state in (STATE_PLAYING, STATE_PAUSE_MENU):
                # Version top left, FPS bottom right
                ver = self._fps_font.render(VERSION, True, (0,160,255))
                self.screen.blit(ver, (8, 6))
                fps_s = self._fps_font.render(f"{fps:.0f} FPS", True, (0,160,255))
                self.screen.blit(fps_s, (W2 - fps_s.get_width() - 8,
                                         H2 - fps_s.get_height() - 4))
            else:
                # All other screens — bottom right as before
                txt = self._fps_font.render(f"{VERSION}  {fps:.0f} FPS", True, (0,160,255))
                self.screen.blit(txt, (W2 - txt.get_width() - 8,
                                       H2 - txt.get_height() - 4))
            pygame.display.flip()

        self.audio.shutdown()
        self.midi_input.disconnect()
        exit_code = 0 if self._selftest is None or self._selftest.passed else 1
        pygame.quit(); sys.exit(exit_code)

    def _handle_event(self, event):
        if self.state == STATE_MENU:
            action = self.main_menu.handle_event(event)
            if action == "play":
                self.audio.play_sfx("confirm")
                self.song_select = SongSelectMenu(
                    self.screen, self.songs, self.current_mode,
                    bool(self.midi_input.selected_port), audio=self.audio)
                self.song_select._refresh_cb = self._refresh_songs
                # songs is now List[SongEntry]
                # Stop menu music so preview can be heard clearly
                self.audio.stop_menu_music(500)
                self.state = STATE_SONG_SELECT
            elif action == "free play":
                self.audio.play_sfx("confirm")
                self.audio.stop_menu_music(500)
                self.free_play = FreePlay(self.screen, self.audio)
                # Ensure MIDI callback is registered for freeplay
                self.midi_input._callbacks.clear()
                self.midi_input.add_callback(self._on_midi_note)
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
                    self.pause_menu = PauseMenu(self.screen, self.engine.mode)
                    self.state = STATE_PAUSE_MENU
                elif event.key == pygame.K_F5:
                    self._restart_song()
                elif event.key == pygame.K_F10:
                    self._end_song()
                elif event.key in self._kb_pitch_map:
                    pitch = self._kb_pitch_map[event.key]
                    self.audio.note_on(pitch, 80)   # always hear what you play
                    self._apply_result(self.engine.on_midi_note(pitch, 80, True))
            elif event.type == pygame.KEYUP and event.key in self._kb_pitch_map:
                self.audio.note_off(self._kb_pitch_map[event.key])

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
            elif action == "menu":
                self.audio.play_sfx("back")
                self.audio.all_notes_off()
                self.midi_input._callbacks.clear()
                self.engine = None; self.renderer = None
                self._build_main_menu()
                self.state = STATE_MENU
                self.audio.start_menu_music()

        elif self.state == STATE_RESULTS:
            action = self.results_screen.handle_event(event)
            if action in ("retry", "menu", "escape"):
                self.audio.stop_sfx("song_complete")
            if action == "retry":
                self.audio.play_sfx("confirm")
                self._restart_song()
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
                    self.midi_input._callbacks.clear()
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
                self.renderer.draw(
                    self.current_song, self.engine.current_time,
                    self.engine.num_lanes, self.engine.lane_pitch_map, dt,
                    pressed_keys=self.midi_input._pressed_keys)
                stats = self.engine.stats
                self.renderer.draw_hud(
                    score=stats.score, combo=stats.combo,
                    multiplier=stats.multiplier, accuracy=stats.accuracy,
                    streak=stats.streak, xp=self.xp_system.total_xp+stats.xp_earned,
                    level=self.xp_system.level, xp_progress=self.xp_system.level_progress,
                    song_progress=self.engine.get_song_progress(),
                    mode=self.engine.mode,
                    last_hit_quality=self.engine.last_hit_quality)

                if getattr(self, '_countdown_active', False):
                    self._draw_countdown(W, H)
                elif self.engine.is_waiting:
                    self._overlay_easy_wait(W,H)
                if self.engine.mode == MODE_TESTING:
                    self._overlay_testing(W,H)

                # Hint bar — sits between HUD and keyboard, clear of both
                hbar_y = self.renderer.PIANO_Y - self.renderer.PIANO_H - 22
                hint = sys_font("consolas",12).render(
                    "ESC: Pause Menu  ·  F5: Restart  ·  F10: End Song  ·  F11: Fullscreen",
                    True, (38,38,58))
                self.screen.blit(hint,(W//2-hint.get_width()//2, hbar_y))

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

        # Animated pulsing circle cursor
        show_cursor = (in_menu and self.state != STATE_PAUSE_MENU)
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
        if show_cursor:
            mx, my = pygame.mouse.get_pos()
            ct = self._cursor_tick
            r_outer = int(10 + 4 * abs(math.sin(ct * 3.5)))
            pygame.draw.circle(self.screen, NEON_CYAN, (mx, my), r_outer, 2)

    def _draw_countdown(self, W, H):
        # Show 3..2..1 based on remaining countdown time
        # Map lookahead seconds to 3-2-1 display
        lookahead = NOTE_LOOKAHEAD_SECS / self.engine.playback_speed
        thirds = lookahead / 3.0
        n = max(1, min(3, math.ceil(self._countdown / thirds)))
        frac = (self._countdown % thirds) / thirds
        scale = 1.0 + 0.35 * frac
        size = int(100 * scale)
        f = sys_font("consolas", max(40, size), bold=True)
        col = [(255,80,80),(255,200,0),(0,220,100)][n-1]
        txt = f.render(str(n), True, col)
        sh  = f.render(str(n), True, (0,0,0))
        x = W//2 - txt.get_width()//2
        y = int(H*0.38) - txt.get_height()//2
        self.screen.blit(sh, (x+3, y+3))
        self.screen.blit(txt, (x, y))
        gf = sys_font("consolas", 22, bold=True)
        gs = gf.render("GET READY", True, GRAY)
        self.screen.blit(gs, (W//2 - gs.get_width()//2, y + txt.get_height() + 8))

    def _overlay_easy_wait(self, W, H):
        if getattr(self, "_wait_ov", None) is None or self._wait_ov.get_size() != (W, H):
            self._wait_ov = pygame.Surface((W,H),pygame.SRCALPHA); self._wait_ov.fill((0,0,0,110))
        self.screen.blit(self._wait_ov,(0,0))
        names=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
        chord = "  ".join(names[p%12]+str(p//12-1) for p in self.engine.get_waiting_pitches()) or "?"
        s=sys_font("consolas",46,bold=True).render(f"Play:  {chord}",True,NEON_GREEN)
        if s.get_width() > W*0.9:   # big chords: smaller text so it fits
            s=sys_font("consolas",28,bold=True).render(f"Play:  {chord}",True,NEON_GREEN)
        self.screen.blit(s,(W//2-s.get_width()//2,H//2-28))
        h=sys_font("consolas",19).render(
            "EASY MODE — play the waiting notes to continue",True,NEON_YELLOW)
        self.screen.blit(h,(W//2-h.get_width()//2,H//2+28))

    def _overlay_testing(self, W, H):
        f=sys_font("consolas",17,bold=True)
        s=f.render("◆ TESTING MODE — Notes play automatically (not scored) ◆",True,NEON_ORANGE)
        bg=pygame.Surface((s.get_width()+22,s.get_height()+8),pygame.SRCALPHA)
        bg.fill((20,10,0,170))
        self.screen.blit(bg,(W//2-bg.get_width()//2,88))
        self.screen.blit(s,(W//2-s.get_width()//2,92))
