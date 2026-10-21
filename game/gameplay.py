"""
KeyFall - Gameplay Engine
Handles hit detection, scoring, XP, streaks, and game state
"""

import time
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from game.constants import *
from game.midi_handler import MidiNote, SongData


@dataclass
class HitResult:
    note: MidiNote
    quality: str        # PERFECT / GREAT / GOOD / MISS
    time_offset_ms: float
    score_earned: int
    xp_earned: int


@dataclass
class GameStats:
    score: int = 0
    combo: int = 0
    max_combo: int = 0
    streak: int = 0
    max_streak: int = 0
    multiplier: int = 1
    total_notes: int = 0
    hits_perfect: int = 0
    hits_great: int = 0
    hits_good: int = 0
    misses: int = 0
    xp_earned: int = 0

    @property
    def accuracy(self) -> float:
        total = self.hits_perfect + self.hits_great + self.hits_good + self.misses
        if total == 0:
            return 100.0
        hits = self.hits_perfect + self.hits_great + self.hits_good
        return (hits / total) * 100.0

    @property
    def hit_count(self) -> int:
        return self.hits_perfect + self.hits_great + self.hits_good

    def get_grade(self) -> str:
        acc = self.accuracy
        total = self.hits_perfect + self.hits_great + self.hits_good + self.misses
        all_perfect = (self.hits_perfect == total and total > 0)
        all_pg      = (self.hits_perfect + self.hits_great == total and total > 0)
        no_miss     = (self.misses == 0 and total > 0)

        if all_perfect:
            return "GODLIKE"
        if all_pg and no_miss:
            return "SS"
        if no_miss:
            return "S"
        if acc >= 90:
            return "A"
        if acc >= 78:
            return "B"
        if acc >= 62:
            return "C"
        if acc >= 40:
            return "F"
        return "F"


class XPSystem:
    """Manages player XP and level progression."""

    def __init__(self, current_xp: int = 0):
        self.total_xp = current_xp

    @property
    def level(self) -> int:
        for i in range(len(LEVEL_THRESHOLDS) - 1, -1, -1):
            if self.total_xp >= LEVEL_THRESHOLDS[i]:
                return i + 1
        return 1

    @property
    def xp_in_level(self) -> int:
        lv = self.level
        if lv <= 1:
            return self.total_xp
        return self.total_xp - LEVEL_THRESHOLDS[lv - 1]

    @property
    def xp_for_next_level(self) -> int:
        lv = self.level
        if lv >= len(LEVEL_THRESHOLDS):
            return 99999
        return LEVEL_THRESHOLDS[lv] - LEVEL_THRESHOLDS[lv - 1]

    @property
    def level_progress(self) -> float:
        """0.0 to 1.0 progress through current level."""
        needed = self.xp_for_next_level
        if needed == 0:
            return 1.0
        return min(1.0, self.xp_in_level / needed)

    def add_xp(self, amount: int) -> bool:
        """Returns True if leveled up."""
        old_level = self.level
        self.total_xp += amount
        return self.level > old_level


class GameplayEngine:
    """
    Manages gameplay: timing, hit detection, scoring, modes.
    """

    def __init__(self, song: SongData, mode: str = MODE_HARD):
        self.song = song
        self.mode = mode
        self.stats = GameStats(total_notes=len(song.notes))
        
        self.is_playing = False
        self.is_paused = False
        self.song_complete = False
        
        self._start_wall_time: float = 0.0
        self._pause_start: float = 0.0
        self._total_pause: float = 0.0
        self.current_time: float = 0.0
        
        # Track which notes have been processed
        self._pending_notes: List[MidiNote] = list(song.notes)
        self._note_idx: int = 0  # next note to check
        self._hit_note_ids: Set[int] = set()   # id(note) for hit notes
        self._missed_note_ids: Set[int] = set()
        
        # For easy mode: which note we're waiting on
        self._easy_mode_waiting: Optional[MidiNote] = None
        self._easy_mode_paused: bool = False
        
        # Recent hits for feedback
        self.recent_hits: List[HitResult] = []
        self.last_hit_quality: str = ""
        self.last_hit_timer: float = 0.0
        
        # Testing mode: track auto-played notes
        self._testing_played_ids: Set[int] = set()
        # Callback for when a note should be auto-played (testing mode)
        self.on_auto_note = None  # fn(pitch, velocity)

        # Compute lane mapping
        self._lane_pitch_map: List[int] = self._compute_lanes()

    def _compute_lanes(self) -> List[int]:
        """Determine which pitches appear in song and map to lanes."""
        pitches = sorted(set(n.pitch for n in self.song.notes))
        return pitches

    @property
    def lane_pitch_map(self) -> List[int]:
        return self._lane_pitch_map

    @property
    def num_lanes(self) -> int:
        return len(self._lane_pitch_map)

    @property
    def playback_speed(self) -> float:
        return getattr(self, '_playback_speed', 1.0)

    @playback_speed.setter
    def playback_speed(self, v: float):
        self._playback_speed = max(0.1, min(2.0, v))

    def start(self, time_offset: float = 0.0):
        """Start the engine. time_offset makes current_time begin negative
        so notes start at the top of the highway."""
        self.is_playing = True
        self._start_wall_time = time.perf_counter()
        self._total_pause = 0.0
        self._time_offset = time_offset  # subtracted from wall time calc

    def pause(self):
        if self.is_playing and not self.is_paused:
            self.is_paused = True
            self._pause_start = time.perf_counter()

    def resume(self):
        if self.is_paused:
            self.is_paused = False
            self._total_pause += time.perf_counter() - self._pause_start

    def toggle_pause(self):
        if self.is_paused:
            self.resume()
        else:
            self.pause()

    def toggle_mode(self):
        modes = [MODE_HARD, MODE_EASY, MODE_TESTING]
        idx = modes.index(self.mode) if self.mode in modes else 0
        self.mode = modes[(idx + 1) % len(modes)]
        # If we just left EASY mode, clear any pending easy-mode pause
        if self.mode != MODE_EASY and self._easy_mode_paused:
            self._easy_mode_paused = False
            self._easy_mode_waiting = None
            self.resume()
        print(f"[Game] Switched to {self.mode}")

    def update(self, dt: float) -> List[HitResult]:
        """Update game state. Returns list of new HitResults this frame."""
        if not self.is_playing or self.is_paused:
            return []

        if self._easy_mode_paused:
            return []

        # Advance time (scaled by playback speed, with optional negative start offset)
        raw = time.perf_counter() - self._start_wall_time - self._total_pause
        offset = getattr(self, '_time_offset', 0.0)
        self.current_time = raw * self.playback_speed - offset

        # Decay hit quality popup
        self.last_hit_timer -= dt
        if self.last_hit_timer <= 0:
            self.last_hit_quality = ""

        # Testing mode: auto-play notes at the right time
        if self.mode == MODE_TESTING:
            for note in self.song.notes:
                nid = id(note)
                if nid in self._hit_note_ids or nid in self._testing_played_ids:
                    continue
                if abs(self.current_time - note.time_sec) <= 0.02:
                    self._testing_played_ids.add(nid)
                    self._hit_note_ids.add(nid)
                    if self.on_auto_note:
                        self.on_auto_note(note.pitch, note.velocity)
                    # Auto-score as PERFECT
                    self.stats.score += SCORE_PERFECT * self.stats.multiplier
                    self.stats.combo += 1
                    self.stats.streak += 1
                    self.stats.max_combo = max(self.stats.max_combo, self.stats.combo)
                    self.stats.multiplier = min(COMBO_MULTIPLIER_MAX, 1 + self.stats.combo // 10)
                    self.stats.hits_perfect += 1
                    self.stats.xp_earned += XP_PER_PERFECT
                    self.last_hit_quality = "PERFECT"
                    self.last_hit_timer = 0.3

        # Check for missed notes (past the hit window)
        new_results = []
        cutoff = self.current_time - (HIT_MISS_MS / 1000.0)
        
        for note in self.song.notes:
            nid = id(note)
            if nid in self._hit_note_ids or nid in self._missed_note_ids:
                continue
            if self.mode == MODE_TESTING:
                # In testing mode, mark overdue notes as hit (not miss)
                if note.time_sec < cutoff:
                    self._missed_note_ids.add(nid)
                continue
            if note.time_sec < cutoff:
                # Missed!
                result = self._register_miss(note)
                new_results.append(result)
                self._missed_note_ids.add(nid)

        # Check song complete
        if self.current_time >= self.song.duration_sec + 1.0:
            self.song_complete = True

        return new_results

    def on_midi_note(self, pitch: int, velocity: int, is_on: bool) -> Optional[HitResult]:
        """Called when player presses/releases a piano key. Returns HitResult if hit."""
        if not is_on or not self.is_playing:
            return None

        # Easy mode: if paused waiting for a note, accept it here
        if self._easy_mode_paused and self._easy_mode_waiting:
            if pitch == self._easy_mode_waiting.pitch:
                # Hit it — resume and score it
                self._easy_mode_paused = False
                self._easy_mode_waiting = None
                self.resume()
                result = self._check_hit(pitch)
                if result is None:
                    # Force score it as GOOD even if window expired
                    note = self._easy_mode_waiting or next(
                        (n for n in self.song.notes
                         if n.pitch == pitch and id(n) not in self._hit_note_ids), None)
                    if note:
                        self._hit_note_ids.add(id(note))
                        self.stats.hits_good += 1
                        self.stats.score += SCORE_GOOD
                        self.stats.combo += 1
                        self.last_hit_quality = "GOOD"
                        self.last_hit_timer = 0.5
                        result = HitResult(note=note, quality="GOOD",
                                           time_offset_ms=0, score_earned=SCORE_GOOD, xp_earned=XP_PER_GOOD)
                return result
            else:
                # Wrong note in easy mode — just ignore, keep waiting
                return None

        if self.is_paused:
            return None

        if pitch not in self._lane_pitch_map:
            return None  # note not in this song

        result = self._check_hit(pitch)

        if result is None:
            # No note within the hit window — this is a miss press
            # Only penalise if there IS an upcoming note for this pitch soon
            upcoming = next(
                (n for n in self.song.notes
                 if n.pitch == pitch
                 and id(n) not in self._hit_note_ids
                 and id(n) not in self._missed_note_ids
                 and (n.time_sec - self.current_time) < 2.0   # within 2s
                 and (n.time_sec - self.current_time) > -0.5), # not too far past
                None)
            if upcoming is not None:
                # Pressed too early or slightly too late — register as miss
                return self._register_miss_press(pitch)
            # No relevant note at all — silent ignore
            return None

        return result

    def _check_hit(self, pitch: int) -> Optional[HitResult]:
        """Find the closest unhit note for this pitch within the hit window."""
        best_note = None
        best_offset = float('inf')
        hit_window = HIT_MISS_MS * 5 if self.mode == MODE_EASY else HIT_MISS_MS

        for note in self.song.notes:
            nid = id(note)
            if nid in self._hit_note_ids or nid in self._missed_note_ids:
                continue
            if note.pitch != pitch:
                continue

            delta_ms = (self.current_time - note.time_sec) * 1000.0
            # delta_ms > 0: note is in the past (late press)
            # delta_ms < 0: note is in the future (early press)

            # Only allow hitting notes that are close — not far in the future
            if delta_ms < -hit_window:
                continue  # too early
            if delta_ms > hit_window:
                continue  # too late (will be caught by miss system)

            offset_ms = abs(delta_ms)
            if offset_ms < best_offset:
                best_offset = offset_ms
                best_note = note

        if best_note is None:
            return None

        # Determine quality
        if best_offset <= HIT_PERFECT_MS:
            quality = "PERFECT"
            score = SCORE_PERFECT
            xp = XP_PER_PERFECT
        elif best_offset <= HIT_GREAT_MS:
            quality = "GREAT"
            score = SCORE_GREAT
            xp = XP_PER_GREAT
        else:
            quality = "GOOD"
            score = SCORE_GOOD
            xp = XP_PER_GOOD

        self._hit_note_ids.add(id(best_note))
        
        # Apply multiplier
        score_earned = score * self.stats.multiplier

        # Update stats
        self.stats.score += score_earned
        self.stats.combo += 1
        self.stats.streak += 1
        self.stats.max_combo = max(self.stats.max_combo, self.stats.combo)
        self.stats.max_streak = max(self.stats.max_streak, self.stats.streak)
        self.stats.xp_earned += xp

        # Update multiplier
        self.stats.multiplier = min(COMBO_MULTIPLIER_MAX, 1 + self.stats.combo // 10)

        if quality == "PERFECT":
            self.stats.hits_perfect += 1
        elif quality == "GREAT":
            self.stats.hits_great += 1
        else:
            self.stats.hits_good += 1

        self.last_hit_quality = quality
        self.last_hit_timer = 0.5

        result = HitResult(
            note=best_note,
            quality=quality,
            time_offset_ms=best_offset,
            score_earned=score_earned,
            xp_earned=xp
        )
        self.recent_hits.append(result)

        # Easy mode: resume if waiting
        if self._easy_mode_paused:
            self._easy_mode_paused = False
            self.resume()

        return result

    def _register_miss_press(self, pitch: int) -> HitResult:
        """Player pressed a key but there was no note to hit — counts as a miss press."""
        self.stats.misses += 1
        self.stats.combo = 0
        self.stats.streak = 0
        self.stats.multiplier = 1
        self.last_hit_quality = "MISS"
        self.last_hit_timer = 0.4
        # Return a fake HitResult with no note so app.py can play miss sound
        # We use a dummy note so the result is non-None
        dummy = MidiNote(pitch=pitch, time_sec=self.current_time,
                        duration_sec=0, velocity=0)
        return HitResult(note=dummy, quality="MISS",
                        time_offset_ms=999, score_earned=0, xp_earned=0)

    def _register_miss(self, note: MidiNote) -> HitResult:
        """Register a missed note."""
        self.stats.misses += 1
        self.stats.combo = 0
        self.stats.streak = 0
        self.stats.multiplier = 1

        if self.mode == MODE_EASY:
            # Pause and wait for correct note
            self._easy_mode_paused = True
            self._easy_mode_waiting = note
            self.pause()
        else:
            # Hard mode: lose points
            penalty = SCORE_PERFECT // 2
            self.stats.score = max(0, self.stats.score - penalty)

        self.last_hit_quality = "MISS"
        self.last_hit_timer = 0.4

        result = HitResult(
            note=note,
            quality="MISS",
            time_offset_ms=0,
            score_earned=0,
            xp_earned=0
        )
        self.recent_hits.append(result)
        return result

    def get_display_notes(self) -> List[MidiNote]:
        """Get all notes that should currently be visible on highway."""
        end_time = self.current_time + NOTE_LOOKAHEAD_SECS
        return [
            n for n in self.song.notes
            if n.time_sec <= end_time and
               n.time_sec + n.duration_sec >= self.current_time - 0.5 and
               id(n) not in self._hit_note_ids
        ]

    def get_song_progress(self) -> float:
        if self.song.duration_sec <= 0:
            return 0.0
        return min(1.0, self.current_time / self.song.duration_sec)

    def get_waiting_pitch(self) -> Optional[int]:
        """In easy mode, the pitch we're waiting for."""
        if self._easy_mode_paused and self._easy_mode_waiting:
            return self._easy_mode_waiting.pitch
        return None
