"""
KeyFall - MIDI Handler
Parses MIDI files and handles live piano input
"""

import bisect
import os
import queue
import threading
import time
from collections import deque
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


PIANO_LOW, PIANO_HIGH = 21, 108   # notes outside an 88-key piano are skipped
MERGE_WINDOW_SEC = 0.03           # the same key struck twice this close together = one press
MIN_NOTE_SEC = 0.05
PARSER_VERSION = 2                # bump when parsing changes (invalidates the song cache)


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
            tpb = mid.ticks_per_beat

            # Tempo map from every track (the old parser used one tempo for the whole
            # song, so any file with tempo changes drifted out of sync)
            changes = []
            for track in mid.tracks:
                tick = 0
                for msg in track:
                    tick += msg.time
                    if msg.type == 'set_tempo':
                        changes.append((tick, msg.tempo))
            changes.sort(key=lambda c: c[0])
            seg_ticks, seg_secs, seg_tempos = [0], [0.0], [500000]   # default 120 BPM
            for tick, tempo in changes:
                if tick == seg_ticks[-1]:
                    seg_tempos[-1] = tempo
                    continue
                seg_secs.append(seg_secs[-1] + (tick - seg_ticks[-1]) * seg_tempos[-1] / (tpb * 1e6))
                seg_ticks.append(tick)
                seg_tempos.append(tempo)
            song.bpm = mido.tempo2bpm(seg_tempos[0])

            def ticks_to_sec(tick):
                k = bisect.bisect_right(seg_ticks, tick) - 1
                return seg_secs[k] + (tick - seg_ticks[k]) * seg_tempos[k] / (tpb * 1e6)

            # Pair note-on/off per (channel, pitch), first struck = first released. The old
            # parser keyed by pitch only, so re-striking a key before its note-off overwrote
            # the earlier note (15% of one song's notes were lost this way).
            raw = []   # (pitch, start_tick, end_tick, velocity, track)
            for track_idx, track in enumerate(mid.tracks):
                tick = 0
                held = {}
                for msg in track:
                    tick += msg.time
                    if msg.type not in ('note_on', 'note_off') or msg.channel == 9:
                        continue   # MIDI channel 10 is percussion, not piano
                    key = (msg.channel, msg.note)
                    if msg.type == 'note_on' and msg.velocity > 0:
                        held.setdefault(key, deque()).append((tick, msg.velocity))
                    elif held.get(key):
                        start, vel = held[key].popleft()
                        raw.append((msg.note, start, tick, vel, track_idx))
                for (_, pitch), starts in held.items():   # never released: end with the track
                    for start, vel in starts:
                        raw.append((pitch, start, tick, vel, track_idx))

            # One key can only sound once at a time: merge doubled parts (same key within
            # 30 ms) and let a re-strike end the previous note.
            by_pitch = {}
            for pitch, start, end, vel, track_idx in raw:
                if PIANO_LOW <= pitch <= PIANO_HIGH:
                    by_pitch.setdefault(pitch, []).append(
                        [ticks_to_sec(start), ticks_to_sec(end), vel, track_idx])
            notes = []
            for pitch, spans in by_pitch.items():
                spans.sort()
                merged = []
                for s, e, vel, track_idx in spans:
                    if merged and s - merged[-1][0] < MERGE_WINDOW_SEC:
                        merged[-1][1] = max(merged[-1][1], e)
                        merged[-1][2] = max(merged[-1][2], vel)
                        continue
                    if merged and merged[-1][1] > s:
                        merged[-1][1] = s
                    merged.append([s, e, vel, track_idx])
                notes.extend(MidiNote(pitch=pitch, time_sec=s, duration_sec=max(MIN_NOTE_SEC, e - s),
                                      velocity=vel, track=track_idx)
                             for s, e, vel, track_idx in merged)

            # Sort by time
            notes.sort(key=lambda n: (n.time_sec, n.pitch))
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
    """
    Handles live MIDI input from a connected piano.

    Messages arrive on the MIDI backend's thread (no polling). Each one is timestamped there
    and queued for the game loop, which drains it on the main thread with poll() - so game
    state is only ever touched by one thread. on_live(kind, a, b) is also called right away
    on the MIDI thread, so the note can sound without waiting for the next frame.
    Event kinds: ("on", pitch, velocity), ("off", pitch, 0), ("sustain", is_down, value).
    """

    def __init__(self):
        self.available_ports = []
        self.selected_port = None
        self.port = None
        self.events = queue.SimpleQueue()      # (perf_counter time, kind, a, b)
        self.on_live: Optional[Callable] = None
        self._pressed_keys = set()             # keys held down (updated by poll())

        self.refresh_ports()

    def refresh_ports(self):
        """Refresh the list of MIDI input ports."""
        if not MIDO_AVAILABLE:
            return
        try:
            self.available_ports = mido.get_input_names()
            if self.available_ports:
                print(f"[MIDI] {len(self.available_ports)} port(s): {self.available_ports}")
        except Exception as e:
            print(f"[MIDI] Could not list MIDI inputs: {e}")
            self.available_ports = []

    def connect(self, port_name: str = None) -> bool:
        """Connect to a MIDI input port (rtmidi, falling back to pygame's MIDI backend)."""
        if not MIDO_AVAILABLE:
            return False
        self.disconnect()
        for backend in (None, "mido.backends.pygame"):
            try:
                if backend:
                    mido.set_backend(backend, load=True)   # (was set_input_backend: doesn't exist)
                ports = mido.get_input_names()
                if ports:
                    self.available_ports = ports
                if not self.available_ports:
                    return False
                target = port_name if port_name in self.available_ports else self.available_ports[0]
                self._open(target)
                print(f"[MIDI Input] Connected: {target}")
                return True
            except Exception as e:
                print(f"[MIDI Input] {backend or 'rtmidi'} failed: {e}")
        return False

    def _open(self, target: str):
        try:
            self.port = mido.open_input(target, callback=self._on_message)
        except ValueError:
            # Backend without callback support (pygame): poll it on a small thread instead
            self.port = mido.open_input(target)
            threading.Thread(target=self._poll_port, args=(self.port,), daemon=True).start()
        self.selected_port = target

    def _poll_port(self, port):
        while self.port is port:
            try:
                for msg in port.iter_pending():
                    self._on_message(msg)
            except Exception as e:
                print(f"[MIDI Input] Error: {e}")
                return
            time.sleep(0.001)

    def disconnect(self):
        if self.port:
            try:
                self.port.close()
            except Exception:
                pass
            self.port = None
            self.selected_port = None
        self._pressed_keys.clear()

    def is_key_pressed(self, pitch: int) -> bool:
        return pitch in self._pressed_keys

    def _on_message(self, msg):
        """MIDI thread: timestamp, sound immediately (on_live), queue for the game loop."""
        t = time.perf_counter()
        try:
            if msg.type == 'note_on' and msg.velocity > 0:
                ev = ("on", msg.note, msg.velocity)
            elif msg.type in ('note_on', 'note_off'):
                ev = ("off", msg.note, 0)
            elif msg.type == 'control_change' and msg.control == 64:   # sustain pedal
                ev = ("sustain", msg.value >= 64, msg.value)
            else:
                return
            if self.on_live:
                self.on_live(*ev)
            self.events.put((t,) + ev)
        except Exception as e:
            print(f"[MIDI Input] Error: {e}")

    def poll(self) -> List[tuple]:
        """Main thread: everything received since the last call, oldest first."""
        out = []
        while True:
            try:
                ev = self.events.get_nowait()
            except queue.Empty:
                return out
            if ev[1] == "on":
                self._pressed_keys.add(ev[2])
            elif ev[1] == "off":
                self._pressed_keys.discard(ev[2])
            out.append(ev)


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
