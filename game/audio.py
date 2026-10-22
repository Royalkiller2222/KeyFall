"""
KeyFall - Audio Engine
Synthesized piano tones + MIDI output routing + menu music + SFX
"""

import os
import pygame
import numpy as np
import threading
import time
import math
from typing import Optional, Dict
from game.constants import *

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    MIDO_AVAILABLE = False

# FluidSynth engine (loaded lazily, never crashes on import)
try:
    from game import fluidsynth_engine as _fluid_eng
    FLUID_ENGINE_AVAILABLE = True
except Exception:
    _fluid_eng = None
    FLUID_ENGINE_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────
# Tone Synthesis
# ─────────────────────────────────────────────────────────────────

def midi_to_freq(pitch: int) -> float:
    return 440.0 * (2.0 ** ((pitch - 69) / 12.0))


def synthesize_piano_tone(pitch: int, duration_sec: float = 1.5,
                           sample_rate: int = 44100, velocity: int = 90) -> np.ndarray:
    """
    Synthesize a realistic piano-like tone using additive synthesis
    with velocity-sensitive amplitude and natural decay envelope.
    """
    freq = midi_to_freq(pitch)
    t = np.linspace(0, duration_sec, int(sample_rate * duration_sec), False)
    vol = (velocity / 127.0) ** 1.2

    # Additive harmonics (piano-like overtone series)
    # Each tuple: (harmonic_multiple, amplitude, decay_rate)
    harmonics = [
        (1.0,   1.00, 3.5),
        (2.0,   0.50, 5.0),
        (3.0,   0.25, 7.0),
        (4.0,   0.15, 9.0),
        (5.0,   0.08, 12.0),
        (6.0,   0.05, 15.0),
        (7.0,   0.03, 18.0),
        (8.0,   0.015, 22.0),
    ]

    signal = np.zeros_like(t)
    for mult, amp, decay in harmonics:
        h_freq = freq * mult
        if h_freq < sample_rate / 2:  # below Nyquist
            envelope = np.exp(-decay * t)
            signal += amp * envelope * np.sin(2 * np.pi * h_freq * t)

    # Overall ADSR envelope
    attack = min(0.01, duration_sec * 0.05)
    decay_t = min(0.08, duration_sec * 0.15)
    sustain_level = 0.6
    release = min(0.3, duration_sec * 0.4)

    envelope = np.ones_like(t)
    a_samples = int(attack * sample_rate)
    d_samples = int(decay_t * sample_rate)
    r_start = max(a_samples + d_samples, len(t) - int(release * sample_rate))

    if a_samples > 0:
        envelope[:a_samples] = np.linspace(0, 1, a_samples)
    if d_samples > 0 and a_samples + d_samples < len(t):
        envelope[a_samples:a_samples + d_samples] = np.linspace(1, sustain_level, d_samples)
    if a_samples + d_samples < len(t):
        envelope[a_samples + d_samples:r_start] = sustain_level
    if r_start < len(t):
        r_len = len(t) - r_start
        envelope[r_start:] = np.linspace(sustain_level, 0, r_len)

    signal *= envelope * vol * 0.35
    signal = np.clip(signal, -1.0, 1.0)

    # Stereo with slight pitch-based panning
    pan = (pitch - 60) / 48.0  # -1 (low) to +1 (high)
    pan = max(-0.8, min(0.8, pan))
    left  = signal * (1.0 - max(0, pan) * 0.4)
    right = signal * (1.0 + min(0, pan) * 0.4)
    stereo = np.stack([left, right], axis=1)

    return (stereo * 32767).astype(np.int16)


def synthesize_menu_click() -> np.ndarray:
    """Short click sound for menu navigation."""
    sr = 44100
    dur = 0.06
    t = np.linspace(0, dur, int(sr * dur), False)
    freq = 880.0
    env = np.exp(-30 * t)
    sig = env * np.sin(2 * np.pi * freq * t) * 0.4
    stereo = np.stack([sig, sig], axis=1)
    return (stereo * 32767).astype(np.int16)


def synthesize_menu_confirm() -> np.ndarray:
    """Two-note confirm sound."""
    sr = 44100
    dur = 0.18
    t = np.linspace(0, dur, int(sr * dur), False)
    mid = len(t) // 2
    sig = np.zeros(len(t))
    env1 = np.exp(-20 * t[:mid])
    env2 = np.exp(-20 * t[:mid])
    sig[:mid] = env1 * np.sin(2 * np.pi * 880 * t[:mid]) * 0.4
    sig[mid:] = env2 * np.sin(2 * np.pi * 1320 * t[:mid]) * 0.4
    stereo = np.stack([sig, sig], axis=1)
    return (stereo * 32767).astype(np.int16)


def synthesize_menu_back() -> np.ndarray:
    """Descending back sound."""
    sr = 44100
    dur = 0.12
    t = np.linspace(0, dur, int(sr * dur), False)
    env = np.exp(-15 * t)
    sig = env * np.sin(2 * np.pi * 440 * t) * 0.35
    stereo = np.stack([sig, sig], axis=1)
    return (stereo * 32767).astype(np.int16)


def synthesize_hit_sfx(quality: str) -> np.ndarray:
    """Hit feedback sound."""
    sr = 44100
    if quality == "MISS":
        # Tinny, detuned clunk — low volume, unpleasant but not piercing
        dur = 0.18
        t = np.linspace(0, dur, int(sr * dur), False)
        env = np.exp(-18 * t)
        # Two slightly detuned sawtooth partials for a harsh tinny texture
        saw1 = np.sign(np.sin(2 * np.pi * 185 * t))   # buzzy low tone
        saw2 = np.sign(np.sin(2 * np.pi * 277 * t))   # slightly detuned
        noise = np.random.RandomState(42).uniform(-1, 1, len(t)) * 0.15
        sig = env * (saw1 * 0.35 + saw2 * 0.25 + noise) * 0.22
        stereo = np.stack([sig, sig], axis=1)
        return (stereo * 32767).astype(np.int16)
    freqs = {"PERFECT": 1760, "GREAT": 1320, "GOOD": 880}
    freq = freqs.get(quality, 880)
    dur = 0.08
    t = np.linspace(0, dur, int(sr * dur), False)
    env = np.exp(-25 * t)
    sig = env * np.sin(2 * np.pi * freq * t) * 0.3
    stereo = np.stack([sig, sig], axis=1)
    return (stereo * 32767).astype(np.int16)


def generate_menu_music(duration_sec: float = 30.0, sample_rate: int = 44100) -> np.ndarray:
    """
    Upbeat looping menu theme — inspired by public domain ragtime/stride style.
    Bouncy melody over walking bass, C major.
    """
    bpm = 108
    beat = 60.0 / bpm
    eighth = beat / 2
    sixteenth = beat / 4

    # Catchy 8-bar melody pattern (pitches, durations in beats)
    melody = [
        (72,0.5),(74,0.5),(72,0.5),(69,0.5),  # bar 1
        (67,1.0),(64,0.5),(65,0.5),             # bar 2
        (67,0.5),(69,0.5),(67,0.5),(65,0.5),   # bar 3
        (64,1.5),(60,0.5),                      # bar 4
        (65,0.5),(67,0.5),(69,0.5),(71,0.5),   # bar 5
        (72,0.5),(71,0.5),(69,0.5),(67,0.5),   # bar 6
        (65,0.5),(64,0.5),(62,0.5),(60,0.5),   # bar 7
        (60,2.0),                               # bar 8
    ]

    # Walking bass: alternating root and fifth
    bass_pattern = [
        (48,60),(52,55),(48,60),(52,55),  # C chord
        (53,60),(57,55),(53,60),(57,55),  # F chord
        (55,60),(59,55),(55,60),(59,55),  # G chord
        (48,60),(52,55),(48,60),(52,55),  # C chord
    ]

    total_samples = int(sample_rate * duration_sec)
    output = np.zeros((total_samples, 2), dtype=np.float32)

    def place(pitch, vel, start_beat, dur_beats):
        tone = synthesize_piano_tone(pitch, dur_beats * beat * 0.9, sample_rate, vel)
        s = int(start_beat * beat * sample_rate)
        e = min(s + len(tone), total_samples)
        if s < total_samples:
            chunk = tone[:e-s].astype(np.float32) / 32767.0
            output[s:e] += chunk

    t_pos = 0.0
    while t_pos < duration_sec / beat - 16:
        # Melody
        t = t_pos
        for pitch, dur in melody:
            place(pitch + 12, 68, t, dur)
            t += dur
        # Bass
        for i, (root, fifth) in enumerate(bass_pattern):
            place(root, 52, t_pos + i * 0.5, 0.45)
            place(fifth, 48, t_pos + i * 0.5 + 0.25, 0.2)
        t_pos += 16  # 8 bars of 2 beats each

    # Normalize and fade ends
    peak = np.max(np.abs(output))
    if peak > 0:
        output = output / peak * 0.7

    # Fade in/out
    fade = int(sample_rate * 1.5)
    output[:fade] *= np.linspace(0, 1, fade).reshape(-1, 1)
    output[-fade:] *= np.linspace(1, 0, fade).reshape(-1, 1)

    return (output * 32767).astype(np.int16)


# ─────────────────────────────────────────────────────────────────
# Audio Manager
# ─────────────────────────────────────────────────────────────────

class AudioManager:
    """
    Central audio manager.
    - Synthesized piano tones (always available)
    - MIDI output routing (if piano/VST connected)
    - Menu music (generated, looping)
    - SFX (click, confirm, back, hit feedback)
    """

    def __init__(self):
        # Init pygame mixer
        try:
            pygame.mixer.pre_init(44100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(32)
            self._mixer_ok = True
        except Exception as e:
            print(f"[Audio] Mixer init failed: {e}")
            self._mixer_ok = False

        # Settings (loaded from save later)
        self.master_volume: float = 0.8
        self.music_volume: float = 0.5
        self.sfx_volume: float = 0.7
        self.note_volume: float = 0.9
        self.sfx_enabled: bool = True
        self.note_sound_mode: str = "soundfont"  # soundfont default, synth backup
        self._fluid_ready: bool = False
        self._current_music_file: str = "[Default Synth]"
        self.midi_out_velocity: int = 100   # 0=use file velocity, 1-127=override

        # MIDI output
        self.midi_out_port = None
        self.midi_out_name: Optional[str] = None
        self._available_out_ports = []
        self._refresh_midi_out()

        # Cache synthesized tones (pitch -> Sound)
        self._tone_cache: Dict[int, pygame.mixer.Sound] = {}
        self._sfx: Dict[str, Optional[pygame.mixer.Sound]] = {}
        self._menu_music: Optional[pygame.mixer.Sound] = None
        self._music_channel: Optional[pygame.mixer.Channel] = None

        # Background generation thread
        self._generating = False
        self._gen_thread: Optional[threading.Thread] = None

        # Pre-generate SFX immediately (fast)
        self._prebuild_sfx()

        # Generate menu music in background
        # Check _menu_music folder before starting synth generation
        # If a MIDI is found there, it will be loaded instead
        _mm_dir = os.path.join(SONGS_DIR, "_menu_music")
        _found_midi = False
        if os.path.isdir(_mm_dir):
            for _f in sorted(os.listdir(_mm_dir)):
                if _f.lower().endswith((".mid", ".midi")):
                    _found_midi = True
                    break
        if not _found_midi:
            self._start_music_generation()
        # else: _auto_load_menu_music() in app.py will load it synchronously before start_menu_music()

    def _refresh_midi_out(self):
        if not MIDO_AVAILABLE:
            return
        try:
            self._available_out_ports = mido.get_output_names()
        except:
            self._available_out_ports = []

    def connect_midi_out(self, port_name: str = None) -> bool:
        if not MIDO_AVAILABLE:
            return False
        self._disconnect_midi_out()
        try:
            target = port_name or (self._available_out_ports[0] if self._available_out_ports else None)
            if not target:
                return False
            self.midi_out_port = mido.open_output(target)
            self.midi_out_name = target
            print(f"[Audio] MIDI out connected: {target}")
            return True
        except Exception as e:
            print(f"[Audio] MIDI out failed: {e}")
            return False

    def _disconnect_midi_out(self):
        if self.midi_out_port:
            try:
                # All notes off
                for ch in range(16):
                    self.midi_out_port.send(mido.Message('control_change', channel=ch, control=123, value=0))
                self.midi_out_port.close()
            except:
                pass
            self.midi_out_port = None

    @property
    def available_out_ports(self):
        return self._available_out_ports

    def _load_sfx_file(self, name: str) -> Optional[pygame.mixer.Sound]:
        """Try to load a WAV from the sfx/ folder. Returns None if not found."""
        for ext in [".wav", ".WAV", ".ogg", ".mp3"]:
            path = os.path.join(SFX_DIR, name + ext)
            if os.path.exists(path):
                try:
                    snd = pygame.mixer.Sound(path)
                    print(f"[SFX] Loaded custom: {name}{ext}")
                    return snd
                except Exception as e:
                    print(f"[SFX] Failed to load {path}: {e}")
        return None

    def reload_sfx(self):
        """Reload all SFX from disk — call after user replaces files."""
        self._sfx.clear()
        self._prebuild_sfx()

    def _prebuild_sfx(self):
        if not self._mixer_ok:
            return
        try:
            sfx_map = {
                "click":         synthesize_menu_click,
                "confirm":       synthesize_menu_confirm,
                "back":          synthesize_menu_back,
                "perfect":       lambda: synthesize_hit_sfx("PERFECT"),
                "great":         lambda: synthesize_hit_sfx("GREAT"),
                "good":          lambda: synthesize_hit_sfx("GOOD"),
                "miss":          lambda: synthesize_hit_sfx("MISS"),
                "hover":         synthesize_menu_click,   # synth fallback
                "song_start":    synthesize_menu_confirm, # synth fallback
                "song_complete": synthesize_menu_confirm, # synth fallback
            }
            for name, fn in sfx_map.items():
                # Try custom file first
                file_snd = self._load_sfx_file(name)
                if file_snd:
                    self._sfx[name] = file_snd
                else:
                    arr = fn()
                    snd = pygame.sndarray.make_sound(arr)
                    self._sfx[name] = snd
        except Exception as e:
            print(f"[Audio] SFX build failed: {e}")

    def _start_music_generation(self):
        self._gen_thread = threading.Thread(target=self._generate_music_bg, daemon=True)
        self._gen_thread.start()

    def _generate_music_bg(self):
        try:
            self._music_status = "Generating music..."
            print("[Audio] Generating menu music...")
            arr = generate_menu_music(32.0)
            if self._mixer_ok:
                snd = pygame.sndarray.make_sound(arr)
                self._menu_music = snd
                self._music_status = ""  # ready
        except Exception as e:
            print(f"[Audio] Music generation failed: {e}")

    def get_tone(self, pitch: int) -> Optional[pygame.mixer.Sound]:
        """Get (or generate and cache) a synthesized tone for a pitch."""
        if not self._mixer_ok:
            return None
        if pitch not in self._tone_cache:
            try:
                arr = synthesize_piano_tone(pitch, duration_sec=1.8, velocity=90)
                snd = pygame.sndarray.make_sound(arr)
                self._tone_cache[pitch] = snd
            except Exception as e:
                print(f"[Audio] Tone gen failed pitch={pitch}: {e}")
                return None
        return self._tone_cache[pitch]

    def precache_tones(self, pitches: list):
        """Pre-generate tones for a song's pitches in background."""
        def _cache():
            for p in pitches:
                if p not in self._tone_cache:
                    self.get_tone(p)
        threading.Thread(target=_cache, daemon=True).start()

    # ── Playback ──────────────────────────────────────────────────

    def play_note(self, pitch: int, velocity: int = 90):
        """Play a piano note — synth, soundfont, or MIDI out."""
        # Equal-loudness compensation: scale each new voice by 1/sqrt(N+1)
        # Prevents clipping when many notes play simultaneously without capping voices
        if self._mixer_ok and self.note_sound_mode != "midi_out":
            import math as _m
            n_ch = pygame.mixer.get_num_channels()
            busy = sum(1 for i in range(2, n_ch) if pygame.mixer.Channel(i).get_busy())
            _loudness_scale = 1.0 / _m.sqrt(max(1, busy + 1))
        else:
            _loudness_scale = 1.0
        vol = self.note_volume * self.master_volume * _loudness_scale

        if self.note_sound_mode == "midi_out" and self.midi_out_port:
            try:
                out_vel = self.midi_out_velocity if self.midi_out_velocity > 0 else velocity
                out_vel = max(1, min(127, out_vel))
                self.midi_out_port.send(mido.Message('note_on', note=pitch, velocity=out_vel, channel=0))
                def _off():
                    time.sleep(1.2)
                    try:
                        self.midi_out_port.send(mido.Message('note_off', note=pitch, velocity=0, channel=0))
                    except:
                        pass
                threading.Thread(target=_off, daemon=True).start()
            except:
                pass

        elif self.note_sound_mode == "soundfont" and FLUID_ENGINE_AVAILABLE and self._fluid_ready:
            try:
                out_vel = self.midi_out_velocity if self.midi_out_velocity > 0 else velocity
                out_vel = max(1, min(127, int(out_vel * vol)))
                _fluid_eng.fluid_note_on(pitch, out_vel)
                def _off_fluid():
                    time.sleep(1.4)
                    _fluid_eng.fluid_note_off(pitch)
                threading.Thread(target=_off_fluid, daemon=True).start()
            except:
                # Fall back to synth
                snd = self.get_tone(pitch)
                if snd:
                    snd.set_volume(vol)
                    snd.play()

        else:
            snd = self.get_tone(pitch)
            if snd:
                snd.set_volume(vol)
                snd.play()

    def play_note_isolated(self, pitch: int, velocity: int = 90):
        """Play a note on a dedicated channel so it doesn't affect other sounds."""
        if not self._mixer_ok:
            return
        try:
            snd = self.get_tone(pitch)
            if snd:
                # Use channel 60 as dedicated "test" channel
                ch = pygame.mixer.Channel(60)
                vol = self.note_volume * self.master_volume
                snd.set_volume(vol)
                ch.play(snd)
        except Exception as e:
            print(f"[Audio] play_note_isolated failed: {e}")
            self.play_note(pitch, velocity)

    def init_soundfont(self, sf2_path: str = None) -> bool:
        """Initialise SF2 soundfont engine. Falls back to synth if unavailable."""
        if not FLUID_ENGINE_AVAILABLE:
            self._fluid_ready = False
            return False
        gain = (self.note_volume * self.master_volume) * 1.2
        ok = _fluid_eng.init_fluidsynth(sf2_path, gain=gain)
        self._fluid_ready = ok
        if not ok:
            # Silently fall back to synth mode
            pass
        return ok

    def soundfont_status(self) -> str:
        """Human-readable soundfont status string for UI."""
        if not FLUID_ENGINE_AVAILABLE:
            return "Module unavailable"
        if self._fluid_ready:
            return "Ready"
        # Check the currently selected SF2 file
        import game.fluidsynth_engine as _fe
        sf2_path = _fe.SF2_PATH
        sf2_name = os.path.basename(sf2_path)
        if not os.path.exists(sf2_path):
            return f"{sf2_name} not found"
        if os.path.getsize(sf2_path) < 100_000:
            return f"{sf2_name} is corrupt (too small)"
        return "Loading..."

    @property
    def music_loading_status(self) -> str:
        """Status string for menu music loading — for UI display."""
        return getattr(self, "_music_status", "")

    def play_sfx(self, name: str):
        """Play a UI sound effect."""
        if not self.sfx_enabled or not self._mixer_ok:
            return
        snd = self._sfx.get(name)
        if snd:
            # Volume already kept current by update_volumes; set here too for safety
            snd.set_volume(self.sfx_volume * self.master_volume)
            snd.play()

    def stop_sfx(self, name: str):
        """Stop a named SFX if it is currently playing."""
        if not self._mixer_ok:
            return
        snd = self._sfx.get(name)
        if snd:
            snd.stop()

    def start_menu_music(self):
        """Start looping menu music."""
        if not self._mixer_ok:
            return
        if self._menu_music is None:
            # Not ready yet, try again shortly
            def _delayed():
                for _ in range(30):
                    time.sleep(0.5)
                    if self._menu_music:
                        self._do_start_music()
                        return
            threading.Thread(target=_delayed, daemon=True).start()
            return
        self._do_start_music()

    def _do_start_music(self):
        # Don't auto-play if the game says we're not in a menu state
        if callable(getattr(self, "_music_allowed_cb", None)):
            if not self._music_allowed_cb():
                return
        try:
            if not self._menu_music:
                return
            if self._music_channel:
                try: self._music_channel.stop()
                except: pass
            vol = self.music_volume * self.master_volume
            self._menu_music.set_volume(vol)
            self._music_channel = self._menu_music.play(loops=-1, fade_ms=800)
            pass  # menu music started
        except Exception as e:
            print(f"[Audio] Music play failed: {e}")

    def stop_menu_music(self, fade_ms: int = 800):
        if self._music_channel:
            try:
                self._music_channel.fadeout(fade_ms)
            except:
                pass

    def update_volumes(self):
        """Apply current volume settings to music and all SFX sounds."""
        if self._music_channel and self._menu_music:
            self._menu_music.set_volume(self.music_volume * self.master_volume)
        # Update volume on all pre-loaded SFX so slider takes effect immediately
        sfx_vol = self.sfx_volume * self.master_volume
        for snd in self._sfx.values():
            try:
                snd.set_volume(sfx_vol)
            except Exception:
                pass

    def apply_settings(self, settings: dict):
        self.master_volume = settings.get("master_volume", 0.8)
        self.music_volume  = settings.get("music_volume", 0.5)
        self.sfx_volume    = settings.get("sfx_volume", 0.7)
        self.note_volume   = settings.get("note_volume", 0.9)
        self.sfx_enabled   = settings.get("sfx_enabled", True)
        mode = settings.get("note_sound_mode", "soundfont")
        self.note_sound_mode = mode
        if mode == "midi_out" and not self.midi_out_port:
            self.connect_midi_out(settings.get("midi_out_port"))
        elif mode == "soundfont" and not self._fluid_ready:
            threading.Thread(target=self.init_soundfont, daemon=True).start()
        self.midi_out_velocity = int(settings.get("midi_out_velocity", 100))
        self.update_volumes()
        # Reload music whenever the setting changes
        new_file = settings.get("menu_music_file", "[Default Synth]")
        if new_file != self._current_music_file:
            self._current_music_file = new_file
            if new_file == "[Default Synth]":
                def _regen():
                    import time as _t; _t.sleep(0.1)
                    self.stop_menu_music(400)
                    self._menu_music = None
                    # Check _menu_music folder before starting synth generation
        # If a MIDI is found there, it will be loaded instead
        _mm_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "songs", "_menu_music")
        _found_midi = False
        if os.path.isdir(_mm_dir):
            for _f in sorted(os.listdir(_mm_dir)):
                if _f.lower().endswith((".mid", ".midi")):
                    _found_midi = True
                    break
        if not _found_midi:
            self._start_music_generation()
        # else: _auto_load_menu_music() in app.py will load it before start_menu_music()

    def get_settings(self) -> dict:
        return {
            "master_volume":   self.master_volume,
            "music_volume":    self.music_volume,
            "sfx_volume":      self.sfx_volume,
            "note_volume":     self.note_volume,
            "sfx_enabled":     self.sfx_enabled,
            "note_sound_mode": self.note_sound_mode,
            "midi_out_port":   self.midi_out_name,
        }

    def shutdown(self):
        self._disconnect_midi_out()
        if FLUID_ENGINE_AVAILABLE:
            try: _fluid_eng.shutdown_fluidsynth()
            except: pass
        if self._mixer_ok:
            pygame.mixer.stop()


    def load_menu_music_from_midi(self, midi_path: str):
        """
        Load a MIDI file and synthesize it as menu music.
        Call after apply_settings if menu_music_file is set.
        """
        if not os.path.exists(midi_path):
            print(f"[Audio] Menu music file not found: {midi_path}")
            return
        # Cancel any in-progress synth generation so MIDI wins
        self._menu_music = None
        self._current_music_file = midi_path   # mark as loading
        try:
            self._music_status = f"Loading: {os.path.basename(midi_path)}..."
            print(f"[Audio] Loading menu music from MIDI: {midi_path}")
            from game.midi_handler import MidiParser
            song = MidiParser.parse(midi_path)
            if not song or not song.notes:
                print("[Audio] Could not parse menu music MIDI")
                return

            def _gen():
                sr = 44100
                duration = min(song.duration_sec, 300.0)  # up to 5 minutes
                total = int(sr * duration)
                output = np.zeros((total, 2), dtype=np.float32)

                for note in song.notes:
                    if note.time_sec >= duration:
                        break
                    note_dur = min(note.duration_sec + 0.3, 2.5)
                    # Use SF2 if soundfont mode is active
                    tone_written = False
                    if (self.note_sound_mode == "soundfont"
                            and FLUID_ENGINE_AVAILABLE and self._fluid_ready):
                        try:
                            from game.fluidsynth_engine import _build_sound, _sf2_reader
                            if _sf2_reader is not None:
                                snd = _build_sound(_sf2_reader, note.pitch)
                                if snd:
                                    arr2 = pygame.sndarray.array(snd)
                                    mono = arr2[:,0].astype(np.float32)/32767.0
                                    s2 = int(note.time_sec * sr)
                                    e2 = min(s2+len(mono), total)
                                    if s2 < total:
                                        ch = mono[:e2-s2]
                                        output[s2:e2,0] += ch
                                        output[s2:e2,1] += ch
                                    tone_written = True
                        except Exception:
                            pass
                    if not tone_written:
                        tone = synthesize_piano_tone(note.pitch, note_dur, sr, note.velocity)
                        start = int(note.time_sec * sr)
                        end = min(start + len(tone), total)
                        if start < total:
                            chunk = tone[:end-start].astype(np.float32) / 32767.0
                            output[start:end] += chunk

                peak = np.max(np.abs(output))
                if peak > 0:
                    output = output / peak * 0.72
                fade = int(sr * 1.5)
                output[:fade] *= np.linspace(0, 1, fade).reshape(-1, 1)
                output[-fade:] *= np.linspace(1, 0, fade).reshape(-1, 1)

                arr = (output * 32767).astype(np.int16)
                if self._mixer_ok:
                    snd = pygame.sndarray.make_sound(arr)
                    self._menu_music = snd
                    self._music_status = ""
                    print("[Audio] Custom menu music ready.")
                    self._do_start_music()

            self.stop_menu_music(0)
            self._menu_music = None
            t = threading.Thread(target=_gen, daemon=True)
            t.start()

        except Exception as e:
            print(f"[Audio] load_menu_music_from_midi failed: {e}")
