"""
KeyFall - MIDI Handler
Parses MIDI files and handles live piano input
"""

import os
import threading
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable

try:
    import mido
    MIDO_AVAILABLE = True
except ImportError:
    mido = None
    MIDO_AVAILABLE = False
    print("[MIDI] mido not installed - MIDI input disabled")

# Automated/headless runs (self-test, CI) must not grab the player's MIDI devices
if os.environ.get("KEYFALL_NO_MIDI") == "1":
    MIDO_AVAILABLE = False


@dataclass
class MidiNote:
    """A single note event parsed from a MIDI file."""
    pitch: int          # MIDI pitch (21-108 for piano)
    time_sec: float     # when note starts (seconds from song start)
    duration_sec: float # how long note is held
    velocity: int       # 0-127
    track: int = 0

    @property
    def note_name(self) -> str:
        names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
        octave = (self.pitch // 12) - 1
        name = names[self.pitch % 12]
        return f"{name}{octave}"

    @property
    def is_black_key(self) -> bool:
        return (self.pitch % 12) in [1, 3, 6, 8, 10]


@dataclass 
class SongData:
    """Parsed song ready for gameplay."""
    title: str
    filename: str
    notes: List[MidiNote] = field(default_factory=list)
    duration_sec: float = 0.0
    bpm: float = 120.0
    time_signature: tuple = (4, 4)
    min_pitch: int = 60
    max_pitch: int = 72
    difficulty: str = ""     # EASY / MEDIUM / HARD / EXTREME, set by the song library

    def get_notes_in_window(self, start_sec: float, end_sec: float) -> List[MidiNote]:
        return [n for n in self.notes if start_sec <= n.time_sec <= end_sec]

    def get_active_notes(self, current_sec: float) -> List[MidiNote]:
        """Notes that are currently being held at given time."""
        return [n for n in self.notes 
                if n.time_sec <= current_sec <= n.time_sec + n.duration_sec]


class MidiParser:
    """Parses MIDI files into SongData."""

    @staticmethod
    def parse(filepath: str) -> Optional[SongData]:
        if mido is None:
            print("[MIDI] Cannot parse: mido not installed")
            return None
        
        if not os.path.exists(filepath):
            print(f"[MIDI] File not found: {filepath}")
            return None

        try:
            mid = mido.MidiFile(filepath)
            title = os.path.splitext(os.path.basename(filepath))[0]
            song = SongData(title=title, filename=filepath)

            # Get tempo (default 500000 = 120 BPM)
            tempo = 500000
            for track in mid.tracks:
                for msg in track:
                    if msg.type == 'set_tempo':
                        tempo = msg.tempo
                        break

            song.bpm = mido.tempo2bpm(tempo)
            ticks_per_beat = mid.ticks_per_beat

            def ticks_to_sec(ticks):
                return mido.tick2second(ticks, ticks_per_beat, tempo)

            # Parse all tracks
            notes = []
            for track_idx, track in enumerate(mid.tracks):
                current_time_ticks = 0
                active = {}  # pitch -> (start_ticks, velocity)
                
                for msg in track:
                    current_time_ticks += msg.time
                    
                    if msg.type == 'note_on' and msg.velocity > 0:
                        active[msg.note] = (current_time_ticks, msg.velocity)
                    
                    elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
                        if msg.note in active:
                            start_ticks, vel = active.pop(msg.note)
                            start_sec = ticks_to_sec(start_ticks)
                            end_sec = ticks_to_sec(current_time_ticks)
                            duration = max(0.05, end_sec - start_sec)
                            
                            notes.append(MidiNote(
                                pitch=msg.note,
                                time_sec=start_sec,
                                duration_sec=duration,
                                velocity=vel,
                                track=track_idx
                            ))

            # Sort by time
            notes.sort(key=lambda n: n.time_sec)
            song.notes = notes

            if notes:
                song.duration_sec = max(n.time_sec + n.duration_sec for n in notes)
                song.min_pitch = min(n.pitch for n in notes)
                song.max_pitch = max(n.pitch for n in notes)
            
            print(f"[MIDI] Parsed '{title}': {len(notes)} notes, {song.duration_sec:.1f}s, {song.bpm:.1f} BPM")
            return song

        except Exception as e:
            print(f"[MIDI] Parse error: {e}")
            return None


class MidiInputHandler:
    """Handles live MIDI input from a connected piano."""

    def __init__(self):
        self.available_ports = []
        self.selected_port = None
        self.port = None
        self._thread = None
        self._running = False
        self._callbacks: List[Callable] = []  # fn(pitch, velocity, is_on)
        self._pressed_keys = set()
        
        self.refresh_ports()

    def refresh_ports(self):
        """Refresh available ports. Only sets backend if not already working."""
        if not MIDO_AVAILABLE:
            return
        # Try current backend first
        try:
            ports = mido.get_input_names()
            self.available_ports = ports
            if ports:
                print(f"[MIDI] {len(ports)} port(s): {ports}")
            return
        except Exception:
            pass
        # Backend not set — try rtmidi then pygame
        for backend in ["mido.backends.rtmidi", "mido.backends.pygame"]:
            try:
                mido.set_input_backend(backend)
                ports = mido.get_input_names()
                self.available_ports = ports
                if ports:
                    print(f"[MIDI] {len(ports)} port(s) via {backend.split('.')[-1]}: {ports}")
                return
            except Exception:
                continue
        self.available_ports = []

    def connect(self, port_name: str = None) -> bool:
        """Connect to a MIDI input port."""
        if not MIDO_AVAILABLE:
            return False
        
        self.disconnect()
        # Refresh port list without resetting backend
        try:
            ports = mido.get_input_names()
            if ports:
                self.available_ports = ports
        except Exception:
            pass
        
        if not self.available_ports:
            return False

        target = port_name or self.available_ports[0]

        # Try rtmidi first, fall back to pygame backend
        for attempt in range(2):
            try:
                if attempt == 1:
                    # Switch to pygame backend as fallback
                    try:
                        mido.set_input_backend("mido.backends.pygame")
                        ports = mido.get_input_names()
                        if ports:
                            self.available_ports = ports
                            target = port_name or ports[0]
                    except Exception:
                        return False
                self.port = mido.open_input(target)
                self.selected_port = target
                self._running = True
                self._thread = threading.Thread(target=self._listen_loop, daemon=True)
                self._thread.start()
                print(f"[MIDI Input] Connected: {target}")
                return True
            except Exception as e:
                if attempt == 0:
                    print(f"[MIDI Input] rtmidi failed ({e}), trying pygame backend...")
                else:
                    print(f"[MIDI Input] All backends failed: {e}")
        return False

    def disconnect(self):
        self._running = False
        if self.port:
            try:
                self.port.close()
            except:
                pass
            self.port = None
        self._pressed_keys.clear()

    def add_callback(self, fn: Callable):
        """Register a callback: fn(pitch, velocity, is_note_on)"""
        self._callbacks.append(fn)

    def remove_callback(self, fn: Callable):
        self._callbacks.remove(fn)

    def is_key_pressed(self, pitch: int) -> bool:
        return pitch in self._pressed_keys

    def _listen_loop(self):
        while self._running and self.port:
            try:
                for msg in self.port.iter_pending():
                    if msg.type == 'note_on':
                        is_on = msg.velocity > 0
                        if is_on:
                            self._pressed_keys.add(msg.note)
                        else:
                            self._pressed_keys.discard(msg.note)
                        for cb in self._callbacks:
                            cb(msg.note, msg.velocity, is_on)
                    
                    elif msg.type == 'note_off':
                        self._pressed_keys.discard(msg.note)
                        for cb in self._callbacks:
                            cb(msg.note, 0, False)
                
                time.sleep(0.001)  # 1ms polling
            except Exception as e:
                if self._running:
                    print(f"[MIDI Input] Error: {e}")
                break


def create_demo_song() -> SongData:
    """Creates a built-in demo song (C major scale) when no MIDI files exist."""
    notes = []
    pitches = [60, 62, 64, 65, 67, 69, 71, 72,  # C4-C5 up
               72, 71, 69, 67, 65, 64, 62, 60]   # C5-C4 down
    
    t = 1.0
    for i, p in enumerate(pitches):
        notes.append(MidiNote(
            pitch=p, time_sec=t, duration_sec=0.4, velocity=90
        ))
        t += 0.5
    
    # Add some chords
    chord_times = [8.0, 9.0, 10.0, 11.0]
    chord_notes = [
        [60, 64, 67],  # C major
        [62, 65, 69],  # D minor
        [64, 67, 71],  # E minor
        [60, 64, 67],  # C major
    ]
    for ct, chord in zip(chord_times, chord_notes):
        for p in chord:
            notes.append(MidiNote(pitch=p, time_sec=ct, duration_sec=0.8, velocity=85))

    notes.sort(key=lambda n: n.time_sec)

    song = SongData(
        title="Demo Song (C Major Scale)",
        filename="demo",
        notes=notes,
        duration_sec=13.0,
        bpm=120.0,
        min_pitch=60,
        max_pitch=72
    )
    return song
