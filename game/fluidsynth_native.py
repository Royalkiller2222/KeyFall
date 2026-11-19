"""
KeyFall - real FluidSynth (libfluidsynth) through ctypes.

The DLLs come from FluidSynth's official Windows release and live in lib/fluidsynth/ next to
the game (setup_audio.py downloads them; release builds bundle them). If they are missing or
fail to load, available() is False and the game uses its built-in sample player instead.

FluidSynth plays a soundfont the way it was designed: velocity layers, loops, envelopes,
stereo samples, reverb/chorus and up to 256 voices. Its API is thread-safe, so notes can be
started straight from the MIDI input thread.
"""

import ctypes as C
import os
import sys
import threading
from typing import Optional

import numpy as np

from game.constants import BASE_DIR

LIB_DIR = os.path.join(BASE_DIR, "lib", "fluidsynth")
DLL_NAME = "libfluidsynth-3.dll"

PLAYER_CHAN = 0      # keys the player presses (sustain pedal applies)
AUTO_CHAN = 1        # one-shots: autoplay, test note
QUIET_CHAN = 2       # one-shots at reduced volume (song previews)
CHANNELS = (PLAYER_CHAN, AUTO_CHAN, QUIET_CHAN)

_lib = None
_load_error = ""
_load_lock = threading.Lock()

_P = C.c_void_p
_SIGS = {
    # name: (restype, argtypes)
    "fluid_version":                     (None,  [C.POINTER(C.c_int)] * 3),
    "new_fluid_settings":                (_P,    []),
    "delete_fluid_settings":             (None,  [_P]),
    "fluid_settings_setstr":             (C.c_int, [_P, C.c_char_p, C.c_char_p]),
    "fluid_settings_setint":             (C.c_int, [_P, C.c_char_p, C.c_int]),
    "fluid_settings_setnum":             (C.c_int, [_P, C.c_char_p, C.c_double]),
    "new_fluid_synth":                   (_P,    [_P]),
    "delete_fluid_synth":                (None,  [_P]),
    "fluid_synth_sfload":                (C.c_int, [_P, C.c_char_p, C.c_int]),
    "fluid_synth_get_sfont_by_id":       (_P,    [_P, C.c_int]),
    "fluid_sfont_iteration_start":       (None,  [_P]),
    "fluid_sfont_iteration_next":        (_P,    [_P]),
    "fluid_preset_get_banknum":          (C.c_int, [_P]),
    "fluid_preset_get_num":              (C.c_int, [_P]),
    "fluid_synth_program_select":        (C.c_int, [_P, C.c_int, C.c_int, C.c_int, C.c_int]),
    "fluid_synth_noteon":                (C.c_int, [_P, C.c_int, C.c_int, C.c_int]),
    "fluid_synth_noteoff":               (C.c_int, [_P, C.c_int, C.c_int]),
    "fluid_synth_cc":                    (C.c_int, [_P, C.c_int, C.c_int, C.c_int]),
    "fluid_synth_all_notes_off":         (C.c_int, [_P, C.c_int]),
    "fluid_synth_all_sounds_off":        (C.c_int, [_P, C.c_int]),
    "fluid_synth_set_gain":              (None,  [_P, C.c_float]),
    "fluid_synth_get_active_voice_count": (C.c_int, [_P]),
    "fluid_synth_write_s16":             (C.c_int, [_P, C.c_int, _P, C.c_int, C.c_int,
                                                    _P, C.c_int, C.c_int]),
    "new_fluid_audio_driver":            (_P,    [_P, _P]),
    "delete_fluid_audio_driver":         (None,  [_P]),
    "fluid_set_log_function":            (_P,    [C.c_int, _P, _P]),
}
# Reverb control (FluidSynth 2.2+). Optional: without them CC 91 sets the reverb instead.
_OPT_SIGS = {
    "fluid_synth_reverb_on":              (C.c_int, [_P, C.c_int, C.c_int]),
    "fluid_synth_set_reverb_group_level": (C.c_int, [_P, C.c_int, C.c_double]),
    "fluid_synth_set_gen":                (C.c_int, [_P, C.c_int, C.c_int, C.c_float]),
}
_has_fx = False
GEN_REVERBSEND = 16          # SoundFont generator: reverb send, in 0.1 % (0..1000)
_FLUID_WARN, _FLUID_INFO, _FLUID_DBG = 2, 3, 4


def _load():
    """Load libfluidsynth once. Returns the library or None."""
    global _lib, _load_error, _has_fx
    with _load_lock:
        if _lib is not None or _load_error:
            return _lib
        path = os.path.join(LIB_DIR, DLL_NAME)
        if not os.path.exists(path):
            _load_error = f"{DLL_NAME} not found in lib/fluidsynth"
            return None
        try:
            if sys.platform == "win32":
                os.add_dll_directory(LIB_DIR)    # its sndfile/SDL3 dependencies live there too
            lib = C.CDLL(path)
            for name, (res, args) in _SIGS.items():
                fn = getattr(lib, name)
                fn.restype, fn.argtypes = res, args
            fx = [getattr(lib, name, None) for name in _OPT_SIGS]
            if all(fx):
                for fn, (res, args) in zip(fx, _OPT_SIGS.values()):
                    fn.restype, fn.argtypes = res, args
                _has_fx = True
            # quiet: every soundfont without drums warns "no preset on channel 9"; errors still print
            for level in (_FLUID_WARN, _FLUID_INFO, _FLUID_DBG):
                lib.fluid_set_log_function(level, None, None)
            _lib = lib
            print(f"[FluidSynth] Loaded {version()}")
        except Exception as e:
            _load_error = f"could not load FluidSynth: {e}"
            print(f"[FluidSynth] {_load_error}")
        return _lib


def available() -> bool:
    return _load() is not None


def load_error() -> str:
    _load()
    return _load_error


def version() -> str:
    if _lib is None:
        return "FluidSynth (not loaded)"
    a, b, c = C.c_int(), C.c_int(), C.c_int()
    _lib.fluid_version(C.byref(a), C.byref(b), C.byref(c))
    return f"FluidSynth {a.value}.{b.value}.{c.value}"


def _first_preset(lib, synth, sfid):
    """(bank, program) of the soundfont's first preset: not every soundfont has piano 0:0."""
    sfont = lib.fluid_synth_get_sfont_by_id(synth, sfid)
    if not sfont:
        return 0, 0
    lib.fluid_sfont_iteration_start(sfont)
    best = None
    while True:
        preset = lib.fluid_sfont_iteration_next(sfont)
        if not preset:
            break
        key = (lib.fluid_preset_get_banknum(preset), lib.fluid_preset_get_num(preset))
        if best is None or key < best:
            best = key
    return best or (0, 0)


class Synth:
    """One FluidSynth instance with a soundfont loaded on CHANNELS.

    With audio=True it plays live through its own audio driver (WASAPI, falling back to
    DirectSound/SDL3); with audio=False nothing is opened and write_s16() renders offline."""

    DRIVERS = ("wasapi", "dsound", "sdl3")

    def __init__(self, sf2_path: str, sample_rate: int = 48000, audio: bool = True,
                 gain: float = 0.5, low_memory: bool = False):
        lib = _load()
        if lib is None:
            raise RuntimeError(_load_error)
        self._lib = lib
        self._lock = threading.Lock()
        self.driver_name = None
        self.settings = lib.new_fluid_settings()
        s = self.settings
        lib.fluid_settings_setnum(s, b"synth.sample-rate", float(sample_rate))
        lib.fluid_settings_setnum(s, b"synth.gain", float(gain))
        lib.fluid_settings_setint(s, b"synth.polyphony", 256)
        lib.fluid_settings_setint(s, b"synth.midi-channels", 16)
        lib.fluid_settings_setint(s, b"synth.threadsafe-api", 1)
        if low_memory:   # offline renders: only the samples the song actually uses are loaded
            lib.fluid_settings_setint(s, b"synth.dynamic-sample-loading", 1)
        self.synth = lib.new_fluid_synth(s)
        if not self.synth:
            lib.delete_fluid_settings(s)
            raise RuntimeError("new_fluid_synth failed")
        self.driver = None
        try:
            self.sfid = lib.fluid_synth_sfload(self.synth, os.fsencode(sf2_path), 1)
            if self.sfid < 0:
                raise RuntimeError(f"could not load {os.path.basename(sf2_path)}")
            bank, prog = _first_preset(lib, self.synth, self.sfid)
            for ch in CHANNELS:
                lib.fluid_synth_program_select(self.synth, ch, self.sfid, bank, prog)
            if audio:
                self._open_driver()
        except Exception:
            self.close()
            raise

    def _open_driver(self):
        lib, s = self._lib, self.settings
        # Low latency for a played instrument: 2 periods (WASAPI shared mode uses the device's
        # ~10 ms period; other drivers use 256 frames). Float output matches Windows' mix format.
        lib.fluid_settings_setint(s, b"audio.period-size", 256)
        lib.fluid_settings_setint(s, b"audio.periods", 2)
        lib.fluid_settings_setstr(s, b"audio.sample-format", b"float")
        for name in self.DRIVERS:
            if lib.fluid_settings_setstr(s, b"audio.driver", name.encode()) != 0:
                continue   # driver not compiled into this build
            drv = lib.new_fluid_audio_driver(s, self.synth)
            if drv:
                self.driver, self.driver_name = drv, name
                print(f"[FluidSynth] Audio driver: {name}")
                return
        raise RuntimeError("no FluidSynth audio driver could be opened")

    # ── playing (thread-safe) ─────────────────────────────────────
    def noteon(self, chan: int, key: int, vel: int):
        if self.synth:
            self._lib.fluid_synth_noteon(self.synth, chan, key, max(1, min(127, int(vel))))

    def noteoff(self, chan: int, key: int):
        if self.synth:
            self._lib.fluid_synth_noteoff(self.synth, chan, key)

    def cc(self, chan: int, ctrl: int, val: int):
        if self.synth:
            self._lib.fluid_synth_cc(self.synth, chan, ctrl, max(0, min(127, int(val))))

    def all_notes_off(self, immediate: bool = False):
        if not self.synth:
            return
        for ch in CHANNELS:
            self._lib.fluid_synth_cc(self.synth, ch, 64, 0)   # a held pedal would keep them ringing
        if immediate:
            self._lib.fluid_synth_all_sounds_off(self.synth, -1)
        else:
            self._lib.fluid_synth_all_notes_off(self.synth, -1)

    def set_gain(self, gain: float):
        if self.synth:
            self._lib.fluid_synth_set_gain(self.synth, float(max(0.0, min(10.0, gain))))

    def set_reverb(self, amount: float):
        """Reverb from 0 (off) to 1. Every channel sends all of its sound to the reverb (the
        generator offset adds to the soundfont's own send, which is capped at 100 %), so the
        amount is simply the reverb's level and sounds the same with any soundfont.
        At 0.25 the reverb is about 9 dB under the notes."""
        if not self.synth:
            return
        amount = max(0.0, min(1.0, float(amount)))
        lib = self._lib
        if _has_fx:
            lib.fluid_synth_reverb_on(self.synth, -1, 1 if amount > 0 else 0)
            lib.fluid_synth_set_reverb_group_level(self.synth, -1, amount)
            for ch in CHANNELS:
                lib.fluid_synth_set_gen(self.synth, ch, GEN_REVERBSEND, 1000.0)
        else:
            for ch in CHANNELS:
                lib.fluid_synth_cc(self.synth, ch, 91, round(127 * amount))

    def active_voices(self) -> int:
        return self._lib.fluid_synth_get_active_voice_count(self.synth) if self.synth else 0

    def write_s16(self, frames: int) -> np.ndarray:
        """Render `frames` stereo frames offline (only for synths without an audio driver)."""
        out = np.zeros((frames, 2), dtype=np.int16)
        if frames > 0:
            base = out.ctypes.data
            # interleaved: left at sample 0, 2, 4...; right at 1, 3, 5...
            self._lib.fluid_synth_write_s16(self.synth, frames, base, 0, 2, base, 1, 2)
        return out

    def close(self):
        with self._lock:
            lib = self._lib
            if self.driver:
                lib.delete_fluid_audio_driver(self.driver)   # stops the audio thread first
                self.driver = None
            if self.synth:
                lib.delete_fluid_synth(self.synth)
                self.synth = None
            if self.settings:
                lib.delete_fluid_settings(self.settings)
                self.settings = None


def render_song(sf2_path: str, song, sample_rate: int = 44100, max_sec: float = 300.0,
                gain: float = 0.5, cancelled=lambda: False) -> Optional[np.ndarray]:
    """Render a parsed song offline into a stereo int16 array (menu music)."""
    dur = min(song.duration_sec + 2.0, max_sec)
    total = int(sample_rate * dur)
    events = []          # (frame, order, is_on, pitch, velocity): note-offs before note-ons
    for n in song.notes:
        if n.time_sec >= dur:
            break
        on = int(n.time_sec * sample_rate)
        off = int((n.time_sec + max(0.05, n.duration_sec)) * sample_rate)
        events.append((on, 1, True, n.pitch, n.velocity))
        events.append((off, 0, False, n.pitch, 0))
    if not events:
        return None
    events.sort()
    syn = Synth(sf2_path, sample_rate, audio=False, gain=gain, low_memory=True)
    try:
        chunks, pos = [], 0
        for frame, _, is_on, pitch, vel in events:
            frame = min(frame, total)
            if frame > pos:
                chunks.append(syn.write_s16(frame - pos))
                pos = frame
                if cancelled():
                    return None
            if is_on:
                syn.noteon(AUTO_CHAN, pitch, vel)
            else:
                syn.noteoff(AUTO_CHAN, pitch)
        if total > pos:
            chunks.append(syn.write_s16(total - pos))
    finally:
        syn.close()
    return np.concatenate(chunks) if chunks else None
