"""
KeyFall - Audio Engine
Piano notes (soundfont or synthesized), MIDI output routing, menu music and SFX.

Notes play on their own pool of mixer channels, handed out least-recently-used, so a dense
passage takes over the oldest voice instead of silently dropping the new note (the old
32-channel setup dropped 16 of 48 simultaneous notes). SFX and music use the remaining
channels. A released key fades out (or keeps ringing while the sustain pedal is down) and
re-striking a key damps its previous note. Nothing is built, and no thread is started,
when a note plays: all key sounds are rendered once in a background thread.
"""

import heapq
import math
import os
import threading
import time
from collections import deque
from typing import Dict, Optional

import numpy as np
import pygame
from game.constants import *

try:
    import mido
    MIDO_AVAILABLE = os.environ.get("KEYFALL_NO_MIDI") != "1"   # headless runs skip MIDI out
except ImportError:
    MIDO_AVAILABLE = False

# Soundfont engine (never crashes on import)
try:
    from game import fluidsynth_engine as _fluid_eng
    FLUID_ENGINE_AVAILABLE = True
except Exception:
    _fluid_eng = None
    FLUID_ENGINE_AVAILABLE = False

NOTE_VOICES = 88            # mixer channels reserved for piano notes
FX_CHANNELS = 16            # channels left for SFX and menu music
RETRIGGER_FADE_MS = 40      # re-striking a key damps the previous note this fast
RELEASE_FADE_MS = 220       # key-up release, like a piano damper
STREAM_SFX_BYTES = 5_000_000  # longer SFX files stream from disk (song_complete.wav is 30 MB)


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
    - Piano notes: pre-rendered soundfont keys, or synthesized tones as a fallback
    - MIDI output routing (external piano/VST)
    - Menu music (rendered once from songs/_menu_music, or generated)
    - SFX (click, confirm, back, hit feedback; custom files from sfx/)

    note_on / note_off / set_sustain are safe to call from the MIDI input thread.
    """

    def __init__(self):
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 2, 512)
            pygame.mixer.set_num_channels(NOTE_VOICES + FX_CHANNELS)
            pygame.mixer.set_reserved(NOTE_VOICES)   # Sound.play() (SFX/music) never takes a note voice
            self._voices = [pygame.mixer.Channel(i) for i in range(NOTE_VOICES)]
            self._mixer_ok = True
        except Exception as e:
            print(f"[Audio] Mixer init failed: {e}")
            self._voices = []
            self._mixer_ok = False
        self._rate = pygame.mixer.get_init()[0] if self._mixer_ok else 44100

        # Settings (loaded from save by apply_settings)
        self.master_volume: float = 0.8
        self.music_volume: float = 0.5
        self.sfx_volume: float = 0.7
        self.note_volume: float = 0.9
        self.sfx_enabled: bool = True
        self.note_sound_mode: str = "soundfont"  # soundfont default, synth backup
        self.sf2_entry: str = "pianos/piano.sf2"
        self.midi_out_velocity: int = 100   # MIDI out only: 0=use played velocity, 1-127=override

        # Voices (shared between the MIDI thread and the main thread)
        self._lock = threading.RLock()
        self._next_voice = 0
        self._held: Dict[int, pygame.mixer.Channel] = {}   # key -> channel sounding it
        self.sustain = False
        self._sustained = set()       # keys released while the sustain pedal is down
        self._recent = deque()        # start times of recent notes (dense-passage gain)
        self._midi_offs = []          # heap of (due time, pitch) for MIDI-out one-shots

        # Instrument loading (background thread)
        self._fluid_ready: bool = False
        self._loading: bool = False
        self._load_gen = 0
        self._loaded_once = False
        self._music_status: str = ""

        # MIDI output
        self.midi_out_port = None
        self.midi_out_name: Optional[str] = None
        self._available_out_ports = []
        self._refresh_midi_out()

        # Synth tone fallback (pitch -> Sound / mono samples)
        self._tone_cache: Dict[int, pygame.mixer.Sound] = {}
        self._tone_pcm: Dict[int, np.ndarray] = {}
        self._sfx: Dict[str, pygame.mixer.Sound] = {}
        self._sfx_stream: Dict[str, str] = {}
        self._streaming: Optional[str] = None
        self._menu_music: Optional[pygame.mixer.Sound] = None
        self._music_channel: Optional[pygame.mixer.Channel] = None
        self._music_fading = False
        self._music_allowed_cb = None

        # Pre-generate SFX immediately (fast)
        self._prebuild_sfx()

    # ── MIDI output ───────────────────────────────────────────────
    def _refresh_midi_out(self):
        if not MIDO_AVAILABLE:
            return
        try:
            self._available_out_ports = mido.get_output_names()
        except Exception:
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
            except Exception:
                pass
            self.midi_out_port = None
            self.midi_out_name = None

    @property
    def available_out_ports(self):
        return self._available_out_ports

    def _midi_out_active(self) -> bool:
        return self.note_sound_mode == "midi_out" and self.midi_out_port is not None

    def _midi_send(self, kind: str, **fields):
        with self._lock:
            try:
                self.midi_out_port.send(mido.Message(kind, channel=0, **fields))
            except Exception:
                pass

    def _out_velocity(self, velocity: int) -> int:
        v = self.midi_out_velocity if self.midi_out_velocity > 0 else velocity
        return max(1, min(127, int(v)))

    # ── SFX ───────────────────────────────────────────────────────
    def _find_sfx_file(self, name: str) -> Optional[str]:
        """Custom SFX file in the sfx/ folder next to the game, if any."""
        for ext in [".wav", ".WAV", ".ogg", ".mp3"]:
            path = os.path.join(SFX_DIR, name + ext)
            if os.path.exists(path):
                return path
        return None

    def reload_sfx(self):
        """Reload all SFX from disk — call after user replaces files."""
        self._sfx.clear()
        self._sfx_stream.clear()
        self._prebuild_sfx()

    def _prebuild_sfx(self):
        if not self._mixer_ok:
            return
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
            snd = None
            path = self._find_sfx_file(name)
            if path and os.path.getsize(path) > STREAM_SFX_BYTES:
                self._sfx_stream[name] = path     # a whole music track: stream, don't load
                print(f"[SFX] Streaming custom: {os.path.basename(path)}")
                continue
            if path:
                try:
                    snd = pygame.mixer.Sound(path)
                    print(f"[SFX] Loaded custom: {os.path.basename(path)}")
                except Exception as e:
                    print(f"[SFX] Failed to load {path}: {e}")
            try:
                self._sfx[name] = snd or pygame.sndarray.make_sound(fn())
            except Exception as e:
                print(f"[Audio] SFX build failed ({name}): {e}")

    def play_sfx(self, name: str):
        """Play a UI sound effect. One instance per effect, so rapid repeats (menu
        scrolling, a 10-note chord of hits) don't stack up and clip."""
        if not self.sfx_enabled or not self._mixer_ok:
            return
        vol = self.sfx_volume * self.master_volume
        path = self._sfx_stream.get(name)
        if path:
            try:
                pygame.mixer.music.load(path)
                pygame.mixer.music.set_volume(vol)
                pygame.mixer.music.play()
                self._streaming = name
            except Exception as e:
                print(f"[SFX] Could not stream {path}: {e}")
            return
        snd = self._sfx.get(name)
        if snd:
            snd.stop()
            snd.set_volume(vol)
            snd.play()

    def stop_sfx(self, name: str):
        """Stop a named SFX if it is currently playing."""
        if not self._mixer_ok:
            return
        if name in self._sfx_stream:
            if self._streaming == name:
                pygame.mixer.music.stop()
                self._streaming = None
            return
        snd = self._sfx.get(name)
        if snd:
            snd.stop()

    # ── Instrument loading ────────────────────────────────────────
    def _resolve_sf2(self) -> Optional[str]:
        """Path of the selected soundfont, or the first installed one if it is missing."""
        path = _fluid_eng.resolve_sf2_path(self.sf2_entry)
        if not os.path.exists(path):
            fallback = _fluid_eng.find_fallback_sf2()
            if not fallback:
                return None
            print(f"[Audio] {self.sf2_entry} not found - using {fallback}")
            path = _fluid_eng.resolve_sf2_path(fallback)
        _fluid_eng.set_sf2_path(os.path.relpath(path, _fluid_eng.FLUID_DIR).replace(os.sep, "/"))
        return path

    def reload_instrument(self):
        """(Re)load the note instrument and re-render the menu music in one background
        thread. A newer call supersedes an older one that is still running."""
        self._load_gen += 1
        self._loaded_once = True
        self._loading = True
        threading.Thread(target=self._load_worker, args=(self._load_gen,), daemon=True).start()

    def _load_worker(self, gen: int):
        try:
            ready = False
            if FLUID_ENGINE_AVAILABLE and self._mixer_ok:
                path = self._resolve_sf2()
                if path:
                    self._music_status = f"Loading {os.path.basename(path)}..."
                    ready = _fluid_eng.init_fluidsynth(path)
            if gen != self._load_gen:
                return
            self._fluid_ready = ready
            if self._mixer_ok and (self.note_sound_mode == "synth" or not ready):
                self._music_status = "Preparing piano tones..."
                for p in range(21, 109):
                    self.get_tone(p)
            if gen == self._load_gen:
                self._render_menu_music(gen)
        except Exception as e:
            print(f"[Audio] Instrument load failed: {e}")
        finally:
            if gen == self._load_gen:
                self._loading = False
                self._music_status = ""

    def get_tone(self, pitch: int) -> Optional[pygame.mixer.Sound]:
        """Get (or generate and cache) a synthesized tone for a pitch."""
        if not self._mixer_ok:
            return None
        snd = self._tone_cache.get(pitch)
        if snd is None:
            try:
                arr = synthesize_piano_tone(pitch, duration_sec=1.8, sample_rate=self._rate, velocity=90)
                snd = pygame.sndarray.make_sound(arr)
                self._tone_pcm[pitch] = arr[:, 0].copy()
                self._tone_cache[pitch] = snd
            except Exception as e:
                print(f"[Audio] Tone gen failed pitch={pitch}: {e}")
                return None
        return snd

    def _note_sound(self, pitch: int) -> Optional[pygame.mixer.Sound]:
        if self.note_sound_mode != "synth" and self._fluid_ready:
            snd = _fluid_eng.get_sound(pitch)
            if snd is not None:
                return snd
        return self.get_tone(pitch)

    def _note_pcm(self, pitch: int) -> Optional[np.ndarray]:
        if self._fluid_ready:
            pcm = _fluid_eng.get_pcm(pitch)
            if pcm is not None:
                return pcm
        if self.get_tone(pitch) is not None:
            return self._tone_pcm.get(pitch)
        return None

    def soundfont_status(self) -> str:
        """Human-readable soundfont status string for UI."""
        if not FLUID_ENGINE_AVAILABLE:
            return "Module unavailable"
        if self._loading:
            return "Loading..."
        if self._fluid_ready:
            return f"Ready ({os.path.basename(_fluid_eng.SF2_PATH)})"
        path = _fluid_eng.resolve_sf2_path(self.sf2_entry)
        if not os.path.exists(path):
            return f"{os.path.basename(path)} not found"
        if os.path.getsize(path) < 100_000:
            return f"{os.path.basename(path)} is corrupt (too small)"
        return "Could not load - using built-in synth"

    @property
    def music_loading_status(self) -> str:
        """Status string for menu music loading — for UI display."""
        return self._music_status

    # ── Notes ─────────────────────────────────────────────────────
    def _start_voice(self, pitch: int, velocity: int, volume_scale: float, held: bool):
        snd = self._note_sound(pitch)
        if snd is None or not self._voices:
            return
        with self._lock:
            now = time.perf_counter()
            self._recent.append(now)
            while now - self._recent[0] > 1.5:
                self._recent.popleft()
            # Many overlapping notes add up and clip: ease off in very dense passages
            gain = 1.0 if len(self._recent) <= 8 else math.sqrt(8 / len(self._recent))
            vol = (self.note_volume * self.master_volume * volume_scale * gain
                   * (max(1, min(127, velocity)) / 127.0) ** 0.8)
            old = self._held.get(pitch)
            if old is not None and old.get_sound() is snd:
                old.fadeout(RETRIGGER_FADE_MS)   # re-striking a key damps its previous note
            ch = self._voices[self._next_voice]  # least recently used voice
            self._next_voice = (self._next_voice + 1) % len(self._voices)
            ch.set_volume(min(1.0, vol))          # per voice: never changes other notes
            ch.play(snd)
            if held:
                self._held[pitch] = ch
                self._sustained.discard(pitch)
            elif old is not None:
                # the held note was just damped by this one-shot; its key-up must not cut it
                self._held.pop(pitch, None)
                self._sustained.discard(pitch)

    def note_on(self, pitch: int, velocity: int = 90, volume_scale: float = 1.0):
        """A key went down (MIDI keyboard, QWERTY, mouse). note_off() should follow."""
        if self._midi_out_active():
            self._midi_send('note_on', note=pitch, velocity=self._out_velocity(velocity))
            return
        self._start_voice(pitch, velocity, volume_scale, held=True)

    def note_off(self, pitch: int):
        """A key came up: fade the note, or keep it ringing while the sustain pedal is down."""
        if self._midi_out_active():
            self._midi_send('note_off', note=pitch, velocity=0)
            return
        with self._lock:
            if self.sustain:
                if pitch in self._held:
                    self._sustained.add(pitch)
                return
            self._release(pitch)

    def _release(self, pitch: int):
        ch = self._held.pop(pitch, None)
        if ch is not None and ch.get_sound() is self._note_sound(pitch):
            ch.fadeout(RELEASE_FADE_MS)   # (skipped if that voice now plays another note)

    def set_sustain(self, down: bool):
        """Sustain pedal (MIDI CC 64, or Space in Free Play)."""
        if self._midi_out_active():
            self._midi_send('control_change', control=64, value=127 if down else 0)
            return
        with self._lock:
            self.sustain = down
            if not down:
                for p in list(self._sustained):
                    self._release(p)
                self._sustained.clear()

    def play_note(self, pitch: int, velocity: int = 90, duration: Optional[float] = None,
                  volume_scale: float = 1.0):
        """A one-shot note (autoplay, song previews, test note): rings out naturally."""
        if self._midi_out_active():
            self._midi_send('note_on', note=pitch, velocity=self._out_velocity(velocity))
            with self._lock:
                heapq.heappush(self._midi_offs, (time.perf_counter() + max(0.1, duration or 1.0), pitch))
            return
        self._start_voice(pitch, velocity, volume_scale, held=False)

    def all_notes_off(self, fade_ms: int = 150):
        """Silence every note (leaving a song, changing the previewed song)."""
        with self._lock:
            for ch in self._voices:
                ch.fadeout(fade_ms)
            self._held.clear()
            self._sustained.clear()
            self.sustain = False
            pending, self._midi_offs = self._midi_offs, []
        if self.midi_out_port:
            for _, pitch in pending:
                self._midi_send('note_off', note=pitch, velocity=0)
            self._midi_send('control_change', control=123, value=0)

    def update(self):
        """Per-frame housekeeping (main thread): due MIDI-out note-offs."""
        if not self._midi_offs:
            return
        now = time.perf_counter()
        due = []
        with self._lock:
            while self._midi_offs and self._midi_offs[0][0] <= now:
                due.append(heapq.heappop(self._midi_offs)[1])
        for pitch in due:
            self._midi_send('note_off', note=pitch, velocity=0)

    # ── Menu music ────────────────────────────────────────────────
    def _menu_midi_path(self) -> Optional[str]:
        """First MIDI in songs/_menu_music, if any."""
        folder = os.path.join(SONGS_DIR, "_menu_music")
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.lower().endswith((".mid", ".midi")):
                    return os.path.join(folder, f)
        return None

    def _render_menu_music(self, gen: int):
        if not self._mixer_ok:
            return
        path = self._menu_midi_path()
        arr = None
        if path:
            self._music_status = f"Loading: {os.path.basename(path)}..."
            from game.midi_handler import MidiParser
            song = MidiParser.parse(path)
            if song and song.notes:
                arr = self._render_song(song)
        if arr is None:
            self._music_status = "Generating music..."
            arr = generate_menu_music(32.0, self._rate)
        if gen != self._load_gen:
            return
        self._menu_music = pygame.sndarray.make_sound(arr)
        print("[Audio] Menu music ready.")
        self._do_start_music()

    def _render_song(self, song, max_sec: float = 300.0) -> Optional[np.ndarray]:
        """Mix a parsed song from the per-key samples (each key is rendered once, not per note)."""
        sr = self._rate
        dur = min(song.duration_sec + 2.0, max_sec)
        total = int(sr * dur)
        out = np.zeros(total, dtype=np.float32)
        for note in song.notes:
            if note.time_sec >= dur:
                break
            pcm = self._note_pcm(note.pitch)
            if pcm is None:
                continue
            s = int(note.time_sec * sr)
            n = min(len(pcm), int((note.duration_sec + 1.0) * sr), total - s)
            if n <= 0:
                continue
            seg = pcm[:n].astype(np.float32) * (note.velocity / 127.0)
            fade = min(n, int(0.3 * sr))
            seg[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)   # damper release
            out[s:s + n] += seg
        peak = float(np.max(np.abs(out)))
        if peak <= 0:
            return None
        out *= 0.72 * 32767.0 / peak
        fade = min(total // 4, int(sr * 1.5))
        out[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
        out[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
        mono = out.astype(np.int16)
        channels = pygame.mixer.get_init()[2]
        return np.repeat(mono[:, None], channels, axis=1) if channels > 1 else mono

    def start_menu_music(self):
        """Start looping menu music (if it is still loading, it starts when ready)."""
        if not self._mixer_ok or self._menu_music is None:
            return
        ch = self._music_channel
        if (ch is not None and not self._music_fading and ch.get_busy()
                and ch.get_sound() is self._menu_music):
            return   # already playing (e.g. coming back from Settings): don't restart it
        self._do_start_music()

    def _do_start_music(self):
        # Don't auto-play if the game says we're not in a menu state
        if callable(self._music_allowed_cb) and not self._music_allowed_cb():
            return
        try:
            if not self._menu_music:
                return
            if self._music_channel:
                try: self._music_channel.stop()
                except Exception: pass
            vol = self.music_volume * self.master_volume
            self._menu_music.set_volume(vol)
            self._music_channel = self._menu_music.play(loops=-1, fade_ms=800)
            self._music_fading = False
        except Exception as e:
            print(f"[Audio] Music play failed: {e}")

    def stop_menu_music(self, fade_ms: int = 800):
        if self._music_channel:
            try:
                self._music_channel.fadeout(fade_ms)
                self._music_fading = True
            except Exception:
                pass

    # ── Settings ──────────────────────────────────────────────────
    def update_volumes(self):
        """Apply current volume settings to music and all SFX sounds."""
        if self._menu_music:
            self._menu_music.set_volume(self.music_volume * self.master_volume)
        # Update volume on all pre-loaded SFX so slider takes effect immediately
        sfx_vol = self.sfx_volume * self.master_volume
        for snd in self._sfx.values():
            try:
                snd.set_volume(sfx_vol)
            except Exception:
                pass
        if self._streaming and self._mixer_ok:
            pygame.mixer.music.set_volume(sfx_vol)

    def apply_settings(self, settings: dict):
        """Apply saved settings. Reloads the instrument only when the soundfont changed
        (or on first call), so pressing SAVE no longer re-renders everything."""
        self.master_volume = settings.get("master_volume", 0.8)
        self.music_volume  = settings.get("music_volume", 0.5)
        self.sfx_volume    = settings.get("sfx_volume", 0.7)
        self.note_volume   = settings.get("note_volume", 0.9)
        self.sfx_enabled   = settings.get("sfx_enabled", True)
        self.midi_out_velocity = int(settings.get("midi_out_velocity", 100))
        mode = settings.get("note_sound_mode", "soundfont")
        sf2 = settings.get("sf2_file", "pianos/piano.sf2")

        if mode == "midi_out":
            port = settings.get("midi_out_port")
            port = None if port in (None, "(none)") else port
            if not self.midi_out_port or (port and port != self.midi_out_name):
                self.connect_midi_out(port)
        elif self.midi_out_port:
            self._disconnect_midi_out()   # leaving MIDI-out mode frees the port

        needs_tones = mode == "synth" and len(self._tone_cache) < 88
        changed = sf2 != self.sf2_entry
        self.note_sound_mode = mode
        self.sf2_entry = sf2
        self.update_volumes()
        if changed or needs_tones or not self._loaded_once:
            self.reload_instrument()

    def shutdown(self):
        self.all_notes_off(0)
        self._disconnect_midi_out()
        if FLUID_ENGINE_AVAILABLE:
            try: _fluid_eng.shutdown_fluidsynth()
            except Exception: pass
        if self._mixer_ok:
            pygame.mixer.stop()
