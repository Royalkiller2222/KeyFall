"""
KeyFall - Soundfont Engine
Pure-Python SF2 sample player for pygame.mixer (no FluidSynth DLL needed, despite the name).

It reads the SF2 sample headers, takes one sample per root pitch, and pre-renders one Sound
per piano key when the soundfont loads (in a background thread). Playing a note is then just
"pick a mixer channel and play it" - nothing is built while you play.
"""

import mmap, os, struct
import numpy as np
import pygame
from typing import Dict, Optional

# When frozen (PyInstaller EXE), __file__ is inside _internal — use sys.executable dir instead
import sys as _sys
if getattr(_sys, "frozen", False):
    BASE_DIR = os.path.dirname(_sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLUID_DIR = os.path.join(BASE_DIR, "fluidsynth")
SF2_PATH  = os.path.join(FLUID_DIR, "pianos", "piano.sf2")

KEY_RANGE    = range(21, 109)   # A0..C8, every key is pre-rendered
MAX_NOTE_SEC = 4.0              # longest a note rings; key release / sustain end it sooner
FADE_FRAC    = 0.35             # fade over the last 35% so the cut-off is never audible

def list_sf2_files() -> list:
    """Return flat list of 'category/file.sf2' and bare 'file.sf2' entries."""
    if not os.path.isdir(FLUID_DIR): return []
    results = []
    # Root-level sf2 files
    for f in sorted(os.listdir(FLUID_DIR)):
        if f.lower().endswith(".sf2"):
            results.append(f)
    # Subfolder categories
    for cat in sorted(os.listdir(FLUID_DIR)):
        cat_path = os.path.join(FLUID_DIR, cat)
        if not os.path.isdir(cat_path): continue
        for f in sorted(os.listdir(cat_path)):
            if f.lower().endswith(".sf2"):
                results.append(f"{cat}/{f}")
    return results

def list_sf2_categorized() -> dict:
    """Return {category: [filename, ...]} dict. Root files under "uncategorized"."""
    if not os.path.isdir(FLUID_DIR): return {}
    result = {}
    # Root-level
    root_files = [f for f in sorted(os.listdir(FLUID_DIR)) if f.lower().endswith(".sf2")]
    if root_files:
        result["uncategorized"] = root_files
    # Subfolders
    for cat in sorted(os.listdir(FLUID_DIR)):
        cat_path = os.path.join(FLUID_DIR, cat)
        if not os.path.isdir(cat_path): continue
        files = [f for f in sorted(os.listdir(cat_path)) if f.lower().endswith(".sf2")]
        if files:
            result[cat] = files
    return result

def resolve_sf2_path(entry: str) -> str:
    """Convert a 'category/file.sf2' or 'file.sf2' entry to a full path."""
    if "/" in entry:
        cat, fname = entry.split("/", 1)
        return os.path.join(FLUID_DIR, cat, fname)
    return os.path.join(FLUID_DIR, entry)

def find_fallback_sf2() -> Optional[str]:
    """Entry of the first usable soundfont, preferring the pianos folder."""
    entries = list_sf2_files()
    entries.sort(key=lambda e: not e.lower().startswith("pianos/"))
    for e in entries:
        if os.path.getsize(resolve_sf2_path(e)) >= 100_000:
            return e
    return None

def set_sf2_path(entry: str):
    global SF2_PATH, _current_sf2
    SF2_PATH = resolve_sf2_path(entry)
    _current_sf2 = entry

FLUID_AVAILABLE = False
_sounds: Dict[int, pygame.mixer.Sound] = {}   # key -> pre-rendered Sound
_pcm: Dict[int, np.ndarray] = {}              # key -> mono int16 samples (menu music renderer)
_current_sf2: str = "pianos/piano.sf2"


def sf2_exists() -> bool:
    return os.path.exists(SF2_PATH) and os.path.getsize(SF2_PATH) > 100_000

def is_available() -> bool:
    return FLUID_AVAILABLE


class SF2Reader:
    """Reads SF2 sample headers. The file is memory-mapped, not loaded into RAM."""

    def __init__(self, path: str):
        self._file = open(path, "rb")
        self.data = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        self.samples: Dict[int, dict] = {}
        self._smpl_start = 0
        self._smpl_size  = 0
        self._parse()

    def close(self):
        self.data.close()
        self._file.close()

    def _u32(self, o): return struct.unpack_from("<I", self.data, o)[0]
    def _u16(self, o): return struct.unpack_from("<H", self.data, o)[0]
    def _u8(self,  o): return self.data[o]

    def _find_chunk(self, tag: bytes, start: int, stop: int) -> Optional[tuple]:
        """Scan for a chunk with given 4-byte tag between start and stop."""
        i = start
        while i + 8 <= stop:
            ct = self.data[i:i+4]
            cs = self._u32(i+4)
            if ct == tag:
                return i+8, cs
            i += 8 + cs + (cs & 1)
        return None

    def _find_list(self, subtype: bytes, start: int, stop: int) -> Optional[tuple]:
        """Find a LIST chunk with a specific 4-byte subtype."""
        i = start
        while i + 12 <= stop:
            ct = self.data[i:i+4]
            cs = self._u32(i+4)
            if ct == b"LIST" and self.data[i+8:i+12] == subtype:
                return i+12, cs-4   # data starts after subtype
            i += 8 + cs + (cs & 1)
        return None

    def _parse(self):
        try:
            if self.data[:4] != b"RIFF":
                print(f"[SF2] Not a RIFF file (got {self.data[:4]})")
                return
            if self.data[8:12] != b"sfbk":
                print(f"[SF2] Not an SF2 file (got {self.data[8:12]})")
                return

            total = len(self.data)

            # Find sdta LIST (contains smpl)
            sdta = self._find_list(b"sdta", 12, total)
            if not sdta:
                print("[SF2] No sdta chunk found")
                return
            sdta_start, sdta_size = sdta

            # Find smpl inside sdta
            smpl = self._find_chunk(b"smpl", sdta_start, sdta_start + sdta_size)
            if not smpl:
                print("[SF2] No smpl chunk found inside sdta")
                return
            self._smpl_start, self._smpl_size = smpl
            print(f"[SF2] smpl: {self._smpl_size // 1024}KB of audio data")

            # Find pdta LIST (contains shdr)
            pdta = self._find_list(b"pdta", sdta_start + sdta_size, total)
            if not pdta:
                pdta = self._find_list(b"pdta", 12, total)
            if not pdta:
                print("[SF2] No pdta chunk found")
                return
            pdta_start, pdta_size = pdta

            # Find shdr inside pdta
            shdr = self._find_chunk(b"shdr", pdta_start, pdta_start + pdta_size)
            if not shdr:
                print("[SF2] No shdr chunk found")
                return
            shdr_start, shdr_size = shdr

            # Parse sample headers — 46 bytes each
            n = shdr_size // 46
            count = 0
            for i in range(n - 1):  # last entry is EOS sentinel
                off   = shdr_start + i * 46
                name  = self.data[off:off+20].rstrip(b'\x00').decode('ascii','ignore')
                start = self._u32(off+20)
                end   = self._u32(off+24)
                sr    = self._u32(off+36)
                pitch = self._u8(off+40)
                stype = self._u16(off+44) if off+46 <= total else 1

                # Skip ROM samples (stype bit 0x8000 set) and empty samples
                if stype & 0x8000:
                    continue
                if end <= start or (end - start) < 50:
                    continue
                # Keep only the first sample per pitch (usually the best one)
                if pitch not in self.samples:
                    self.samples[pitch] = {
                        "name": name, "start": start, "end": end,
                        "sample_rate": sr, "pitch": pitch,
                    }
                    count += 1

            print(f"[SF2] Loaded {count} unique pitch samples (range "
                  f"{min(self.samples) if self.samples else '?'}"
                  f"–{max(self.samples) if self.samples else '?'})")

        except Exception as e:
            import traceback
            print(f"[SF2] Parse error: {e}")
            traceback.print_exc()


def _render_key(sf2: SF2Reader, pitch: int, rate: int) -> Optional[np.ndarray]:
    """Mono int16 audio for one key: the nearest SF2 sample, pitch-shifted and resampled
    to the mixer rate in a single pass, trimmed to MAX_NOTE_SEC with a fade-out."""
    if not sf2.samples:
        return None
    closest = min(sf2.samples, key=lambda p: abs(p - pitch))
    info = sf2.samples[closest]
    start, end = info["start"], info["end"]
    if end * 2 > sf2._smpl_size:
        return None
    # Source samples consumed per output sample (pitch shift and rate change combined)
    step = 2.0 ** ((pitch - closest) / 12.0) * (info["sample_rate"] or rate) / rate
    n_out = min(int(MAX_NOTE_SEC * rate), int((end - start - 2) / step))
    if n_out <= 10:
        return None
    n_in = int(n_out * step) + 2          # only read the part of the sample we will use
    off = sf2._smpl_start + start * 2
    src = np.frombuffer(sf2.data[off:off + n_in * 2], dtype=np.int16).astype(np.float32)
    pos = np.arange(n_out, dtype=np.float64) * step
    i0 = np.minimum(pos.astype(np.int64), len(src) - 2)
    frac = (pos - i0).astype(np.float32)
    out = src[i0] + (src[i0 + 1] - src[i0]) * frac          # linear interpolation
    fade = max(1, int(n_out * FADE_FRAC))
    out[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    peak = float(np.max(np.abs(out)))
    if peak > 0:
        out *= 18000.0 / peak                  # ~55% of full scale: headroom for chords
    return np.clip(out, -32767, 32767).astype(np.int16)


# ── Public API ────────────────────────────────────────────────────
def init_fluidsynth(sf2_path: str = None) -> bool:
    """Load a soundfont and pre-render every key. Safe to call from a background thread;
    the new sounds replace the old ones in one step when ready."""
    global FLUID_AVAILABLE, _sounds, _pcm

    path = sf2_path or SF2_PATH
    if not os.path.exists(path):
        print(f"[SF2] File not found: {path}")
        return False
    sz = os.path.getsize(path)
    if sz < 100_000:
        print(f"[SF2] File too small: {os.path.basename(path)} ({sz} bytes) — likely corrupt")
        return False
    init = pygame.mixer.get_init()
    if not init:
        return False
    rate, _, channels = init

    try:
        print(f"[SF2] Loading {os.path.basename(path)} ({sz//1024}KB)...")
        reader = SF2Reader(path)
        try:
            if not reader.samples:
                print("[SF2] No usable samples — soundfont may be compressed/unsupported")
                return False
            sounds, pcm = {}, {}
            for p in KEY_RANGE:
                mono = _render_key(reader, p, rate)
                if mono is None:
                    continue
                pcm[p] = mono
                arr = np.repeat(mono[:, None], channels, axis=1) if channels > 1 else mono
                sounds[p] = pygame.sndarray.make_sound(arr)
        finally:
            reader.close()
        _sounds, _pcm = sounds, pcm
        FLUID_AVAILABLE = bool(sounds)
        print(f"[SF2] Ready: {len(sounds)} keys pre-rendered")
        return FLUID_AVAILABLE
    except Exception as e:
        print(f"[SF2] Init error: {e}")
        return False


def get_sound(pitch: int) -> Optional[pygame.mixer.Sound]:
    """Pre-rendered Sound for a key (pitches outside the piano use the nearest key)."""
    return _sounds.get(min(108, max(21, pitch)))


def get_pcm(pitch: int) -> Optional[np.ndarray]:
    return _pcm.get(min(108, max(21, pitch)))


def shutdown_fluidsynth():
    global FLUID_AVAILABLE, _sounds, _pcm
    FLUID_AVAILABLE = False
    _sounds, _pcm = {}, {}
