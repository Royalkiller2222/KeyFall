"""
KeyFall - Soundfont Engine
Pure Python SF2 reader using pygame mixer. No external DLLs needed.
"""

import os, struct, threading
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
print(f"[SF2] Base dir: {BASE_DIR}")
print(f"[SF2] Fluid dir: {FLUID_DIR}")

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

def set_sf2_path(filename: str):
    global SF2_PATH, _current_sf2
    SF2_PATH = os.path.join(FLUID_DIR, filename)
    _current_sf2 = filename

FLUID_AVAILABLE = False
_sample_cache: Dict[int, Optional[pygame.mixer.Sound]] = {}
_current_sf2: str = "piano.sf2"
_sf2_reader = None
_sample_rate = 44100


def sf2_exists() -> bool:
    return os.path.exists(SF2_PATH) and os.path.getsize(SF2_PATH) > 100_000

def fluidsynth_dll_exists() -> bool:
    return True

def is_available() -> bool:
    return FLUID_AVAILABLE


class SF2Reader:
    """Robust SF2 soundfont parser."""

    def __init__(self, path: str):
        with open(path, "rb") as f:
            self.data = f.read()
        self.samples: Dict[int, dict] = {}
        self._smpl_start = 0
        self._smpl_size  = 0
        self._parse()

    def _u32(self, o): return struct.unpack_from("<I", self.data, o)[0]
    def _u16(self, o): return struct.unpack_from("<H", self.data, o)[0]
    def _u8(self,  o): return self.data[o]
    def _tag(self, o): return self.data[o:o+4]

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
            print(f"[SF2] Parsing {n} sample headers")
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


def _build_sound(sf2: SF2Reader, pitch: int) -> Optional[pygame.mixer.Sound]:
    try:
        if not sf2.samples:
            return None

        # Find nearest sample
        closest = min(sf2.samples.keys(), key=lambda p: abs(p - pitch))
        info = sf2.samples[closest]

        # Extract raw PCM (16-bit signed)
        byte_start = info["start"] * 2
        byte_end   = info["end"]   * 2
        if byte_end > sf2._smpl_size or byte_end <= byte_start:
            return None

        raw = sf2.data[sf2._smpl_start + byte_start :
                       sf2._smpl_start + byte_end]
        pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32)

        # Pitch shift
        semitones = pitch - closest
        if semitones != 0:
            ratio = 2.0 ** (semitones / 12.0)
            n_out = int(len(pcm) / ratio)
            if n_out > 10:
                idx = np.linspace(0, len(pcm)-1, n_out)
                pcm = np.interp(idx, np.arange(len(pcm)), pcm)

        # Resample to pygame rate
        src_sr = info["sample_rate"]
        if src_sr > 0 and src_sr != _sample_rate:
            ratio = _sample_rate / src_sr
            n_out = int(len(pcm) * ratio)
            if n_out > 10:
                idx = np.linspace(0, len(pcm)-1, n_out)
                pcm = np.interp(idx, np.arange(len(pcm)), pcm)

        # Decay envelope — 2 second max
        max_samples = _sample_rate * 2
        if len(pcm) > max_samples:
            pcm = pcm[:max_samples]
        n = len(pcm)
        if n > 0:
            fade_start = int(n * 0.6)
            fade_len   = n - fade_start
            if fade_len > 0:
                pcm[fade_start:] *= np.linspace(1.0, 0.0, fade_len)

        # Normalize to ~70% of int16 range
        peak = np.max(np.abs(pcm))
        if peak > 0:
            pcm = pcm / peak * 18000.0  # 55% of int16 — more headroom for mixing

        pcm = np.clip(pcm, -32767, 32767).astype(np.int16)
        stereo = np.column_stack([pcm, pcm])
        return pygame.sndarray.make_sound(stereo)

    except Exception as e:
        print(f"[SF2] build_sound error pitch={pitch}: {e}")
        return None


# ── Public API ────────────────────────────────────────────────────
def init_fluidsynth(sf2_path: str = None, gain: float = 0.8) -> bool:
    global FLUID_AVAILABLE, _sf2_reader, _sample_cache

    path = sf2_path or SF2_PATH
    if not os.path.exists(path):
        print(f"[SF2] File not found: {path}")
        return False
    sz = os.path.getsize(path)
    if sz < 100_000:
        print(f"[SF2] File too small: {os.path.basename(path)} ({sz} bytes) — likely corrupt")
        return False

    try:
        print(f"[SF2] Loading {os.path.basename(path)} ({sz//1024}KB)...")
        reader = SF2Reader(path)
        if not reader.samples:
            print("[SF2] No usable samples — soundfont may be compressed/unsupported")
            return False
        _sf2_reader = reader
        _sample_cache = {}
        FLUID_AVAILABLE = True
        print(f"[SF2] Ready")
        return True
    except Exception as e:
        print(f"[SF2] Init error: {e}")
        return False


def fluid_note_on(pitch: int, velocity: int, channel: int = 0):
    if not FLUID_AVAILABLE or _sf2_reader is None:
        return
    if pitch not in _sample_cache:
        _sample_cache[pitch] = _build_sound(_sf2_reader, pitch)
    snd = _sample_cache[pitch]
    if snd:
        snd.set_volume(max(0.0, min(1.0, velocity / 127.0)))
        snd.play()


def fluid_note_off(pitch: int, channel: int = 0):
    pass   # decay handled by envelope

def fluid_all_notes_off():
    try: pygame.mixer.stop()
    except: pass

def fluid_set_gain(gain: float): pass

def shutdown_fluidsynth():
    global FLUID_AVAILABLE, _sf2_reader, _sample_cache
    FLUID_AVAILABLE = False
    _sf2_reader = None
    _sample_cache = {}
