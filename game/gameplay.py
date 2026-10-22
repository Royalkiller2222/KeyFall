"""
KeyFall - Gameplay Engine
Handles hit detection, scoring, XP, streaks, and game state

Notes are processed with cursors and per-pitch queues, so a frame or a key press costs the
same whether a song has 300 notes or 300,000 (the old engine rescanned the whole song every
frame and on every key press).
"""

import bisect
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from game.constants import *
from game.midi_handler import MidiNote, SongData

CHORD_WINDOW_SEC = 0.035   # notes starting this close together form one chord (EASY wait)
PENDING, HIT, MISSED = 0, 1, 2
_QUALITY = {"PERFECT": (SCORE_PERFECT, XP_PER_PERFECT),
            "GREAT":   (SCORE_GREAT,   XP_PER_GREAT),
            "GOOD":    (SCORE_GOOD,    XP_PER_GOOD)}


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

    HARD     song keeps going; late notes and badly timed presses are misses.
    EASY     wait mode: the song stops when a chord reaches the hit line and continues once
             every note of it has been played. Nothing is counted as a miss.
    TESTING  autoplay. Every note is played automatically; the run is not scored.
    """

    def __init__(self, song: SongData, mode: str = MODE_HARD):
        self.song = song
        self.mode = mode
        self.stats = GameStats(total_notes=len(song.notes))

        self.is_playing = False
        self.song_complete = False
        self.used_autoplay = (mode == MODE_TESTING)   # autoplayed runs earn no XP/leaderboard

        # Song clock: (wall - start - paused) * speed - offset, frozen while paused.
        self._start_wall_time: float = 0.0
        self._total_pause: float = 0.0
        self._pause_start: float = 0.0
        self._pause_reasons: Set[str] = set()   # "menu" = pause menu, "wait" = EASY waiting
        self._time_offset: float = 0.0
        self._playback_speed: float = 1.0
        self.current_time: float = 0.0

        notes = song.notes
        self._starts = [n.time_sec for n in notes]
        self._state = bytearray(len(notes))      # PENDING / HIT / MISSED per note
        self._play_cursor = 0                    # TESTING: next note to auto-play
        self._miss_cursor = 0                    # next note that can still become a miss
        self._wait_cursor = 0                    # EASY: next chord to wait for
        self._by_pitch: Dict[int, List[int]] = {}
        for i, n in enumerate(notes):
            self._by_pitch.setdefault(n.pitch, []).append(i)
        self._pitch_ptr = {p: 0 for p in self._by_pitch}
        self._waiting: Dict[int, int] = {}       # EASY: pitch -> note index still to play

        self.last_hit_quality: str = ""
        self.last_hit_timer: float = 0.0
        # Callback for when a note should be auto-played (testing mode)
        self.on_auto_note = None  # fn(pitch, velocity, duration_sec)

        self._lane_pitch_map: List[int] = sorted(self._by_pitch)

    @property
    def lane_pitch_map(self) -> List[int]:
        return self._lane_pitch_map

    @property
    def num_lanes(self) -> int:
        return len(self._lane_pitch_map)

    @property
    def playback_speed(self) -> float:
        return self._playback_speed

    @playback_speed.setter
    def playback_speed(self, v: float):
        self._playback_speed = max(0.1, min(2.0, v))

    # ── Clock ─────────────────────────────────────────────────────
    def song_time_at(self, wall: float) -> float:
        """Song position at wall-clock time `wall` (time.perf_counter())."""
        if self._pause_reasons:
            wall = min(wall, self._pause_start)
        raw = wall - self._start_wall_time - self._total_pause
        return raw * self._playback_speed - self._time_offset

    def start(self, time_offset: float = 0.0):
        """Start the engine. time_offset makes current_time begin negative
        so notes start at the top of the highway."""
        self.is_playing = True
        self._start_wall_time = time.perf_counter()
        self._total_pause = 0.0
        self._pause_reasons.clear()
        self._time_offset = time_offset
        self.current_time = -time_offset

    @property
    def is_paused(self) -> bool:
        return bool(self._pause_reasons)

    def pause(self, reason: str = "menu"):
        if not self.is_playing:
            return
        if not self._pause_reasons:
            self._pause_start = time.perf_counter()
        self._pause_reasons.add(reason)

    def resume(self, reason: str = "menu"):
        if reason not in self._pause_reasons:
            return
        self._pause_reasons.discard(reason)
        if not self._pause_reasons:
            self._total_pause += time.perf_counter() - self._pause_start

    def _freeze_at(self, song_t: float):
        """While paused: set the frozen clock to exactly song_t."""
        raw = (song_t + self._time_offset) / self._playback_speed
        self._total_pause = self._pause_start - self._start_wall_time - raw
        self.current_time = song_t

    # ── Modes ─────────────────────────────────────────────────────
    def toggle_mode(self):
        modes = [MODE_HARD, MODE_EASY, MODE_TESTING]
        idx = modes.index(self.mode) if self.mode in modes else 0
        self.set_mode(modes[(idx + 1) % len(modes)])

    def set_mode(self, mode: str):
        if self._waiting and mode != MODE_EASY:
            self._waiting.clear()
            self.resume("wait")       # only the wait; a pause-menu pause stays in effect
        self.mode = mode
        if mode == MODE_TESTING:
            self.used_autoplay = True
        # Never replay or wait for notes that are already behind the playhead
        t = self.current_time
        self._play_cursor = max(self._play_cursor, bisect.bisect_left(self._starts, t))
        self._wait_cursor = max(self._wait_cursor,
                                bisect.bisect_left(self._starts, t - HIT_MISS_MS / 1000.0))
        print(f"[Game] Switched to {self.mode}")

    @property
    def is_waiting(self) -> bool:
        return bool(self._waiting)

    def get_waiting_pitches(self) -> List[int]:
        """EASY mode: pitches still to play before the song continues."""
        return sorted(self._waiting)

    def get_waiting_pitch(self) -> Optional[int]:
        return min(self._waiting) if self._waiting else None

    # ── Per frame ─────────────────────────────────────────────────
    def update(self, dt: float) -> List[HitResult]:
        """Update game state. Returns list of new HitResults (misses) this frame."""
        if not self.is_playing:
            return []
        self.current_time = self.song_time_at(time.perf_counter())

        # Decay hit quality popup
        self.last_hit_timer -= dt
        if self.last_hit_timer <= 0:
            self.last_hit_quality = ""

        if self.is_paused:
            return []
        t = self.current_time
        notes, state, n = self.song.notes, self._state, len(self.song.notes)

        if self.mode == MODE_TESTING:
            # Auto-play every note that has reached the hit line, however long the frame was
            while self._play_cursor < n and notes[self._play_cursor].time_sec <= t:
                i = self._play_cursor
                self._play_cursor += 1
                if state[i] == PENDING:
                    state[i] = HIT
                    note = notes[i]
                    if self.on_auto_note:
                        self.on_auto_note(note.pitch, note.velocity, note.duration_sec)
                    self._score(note, "PERFECT", 0.0)
        elif self.mode == MODE_EASY:
            self._update_wait(t)
            if self.is_paused:
                return []

        # Notes that passed the hit window without being played
        new_results = []
        cutoff = t - HIT_MISS_MS / 1000.0
        while self._miss_cursor < n and notes[self._miss_cursor].time_sec < cutoff:
            i = self._miss_cursor
            self._miss_cursor += 1
            if state[i] != PENDING:
                continue
            state[i] = MISSED
            if self.mode == MODE_HARD:
                new_results.append(self._register_miss(notes[i]))
            # (TESTING: notes skipped by a mode switch are dropped silently)

        # Check song complete
        if t >= self.song.duration_sec + 1.0:
            self.song_complete = True

        return new_results

    def _update_wait(self, t: float):
        """EASY: when the next chord reaches the hit line, stop the clock until it is played."""
        notes, state, n = self.song.notes, self._state, len(self.song.notes)
        while self._wait_cursor < n and state[self._wait_cursor] != PENDING:
            self._wait_cursor += 1
        if self._wait_cursor >= n or notes[self._wait_cursor].time_sec > t:
            return
        first = notes[self._wait_cursor].time_sec
        j = self._wait_cursor
        while j < n and notes[j].time_sec - first <= CHORD_WINDOW_SEC:
            if state[j] == PENDING:
                self._waiting[notes[j].pitch] = j
            j += 1
        self.pause("wait")
        self._freeze_at(first)   # keep the chord exactly on the hit line

    # ── Input ─────────────────────────────────────────────────────
    def on_midi_note(self, pitch: int, velocity: int, is_on: bool,
                     t_event: Optional[float] = None) -> Optional[HitResult]:
        """A key was pressed/released. t_event = time.perf_counter() when it happened
        (defaults to now), so timing is judged from the press itself, not the last frame."""
        if not is_on or not self.is_playing or self.mode == MODE_TESTING:
            return None
        if "menu" in self._pause_reasons:
            return None

        if self._waiting:                       # EASY: the song is stopped on a chord
            i = self._waiting.pop(pitch, None)
            if i is None:
                return None                     # wrong key while waiting: ignored
            self._state[i] = HIT
            result = self._score(self.song.notes[i], "GOOD", 0.0)
            if not self._waiting:
                self.resume("wait")
            return result

        if self.is_paused:
            return None
        idxs = self._by_pitch.get(pitch)
        if not idxs:
            return None  # note not in this song

        t = self.song_time_at(time.perf_counter() if t_event is None else t_event)
        early = (HIT_MISS_MS * 5 if self.mode == MODE_EASY else HIT_MISS_MS) / 1000.0
        late = HIT_MISS_MS / 1000.0
        k = self._advance_pitch_ptr(pitch)
        best, best_off = None, 0.0
        for j in range(k, len(idxs)):
            i = idxs[j]
            ahead = self._starts[i] - t          # > 0: note still coming (early press)
            if ahead > early:
                break
            if self._state[i] != PENDING or ahead < -late:
                continue
            if best is None or abs(ahead) < best_off:
                best, best_off = i, abs(ahead)

        if best is not None:
            self._state[best] = HIT
            off_ms = best_off * 1000.0
            quality = ("PERFECT" if off_ms <= HIT_PERFECT_MS else
                       "GREAT" if off_ms <= HIT_GREAT_MS else "GOOD")
            return self._score(self.song.notes[best], quality, off_ms)

        if self.mode == MODE_HARD:
            # No note in the window: a miss press, but only if this key has a note coming up
            for j in range(k, len(idxs)):
                i = idxs[j]
                if self._state[i] == PENDING:
                    if -0.5 < self._starts[i] - t < 2.0:
                        return self._register_miss_press(pitch)
                    break
        return None

    def _advance_pitch_ptr(self, pitch: int) -> int:
        idxs, k = self._by_pitch[pitch], self._pitch_ptr[pitch]
        while k < len(idxs) and self._state[idxs[k]] != PENDING:
            k += 1
        self._pitch_ptr[pitch] = k
        return k

    # ── Scoring ───────────────────────────────────────────────────
    def _score(self, note: MidiNote, quality: str, offset_ms: float) -> HitResult:
        base, xp = _QUALITY[quality]
        s = self.stats
        score_earned = base * s.multiplier
        s.score += score_earned
        s.combo += 1
        s.streak += 1
        s.max_combo = max(s.max_combo, s.combo)
        s.max_streak = max(s.max_streak, s.streak)
        s.multiplier = min(COMBO_MULTIPLIER_MAX, 1 + s.combo // 10)
        s.xp_earned += xp
        if quality == "PERFECT":
            s.hits_perfect += 1
        elif quality == "GREAT":
            s.hits_great += 1
        else:
            s.hits_good += 1
        self.last_hit_quality = quality
        self.last_hit_timer = 0.3 if self.mode == MODE_TESTING else 0.5
        return HitResult(note=note, quality=quality, time_offset_ms=offset_ms,
                         score_earned=score_earned, xp_earned=xp)

    def _break_combo(self):
        s = self.stats
        s.misses += 1
        s.combo = 0
        s.streak = 0
        s.multiplier = 1
        self.last_hit_quality = "MISS"
        self.last_hit_timer = 0.4

    def _register_miss_press(self, pitch: int) -> HitResult:
        """Player pressed a key with no note to hit — counts as a miss press."""
        self._break_combo()
        # A dummy note so app.py can place the miss feedback in the right lane
        dummy = MidiNote(pitch=pitch, time_sec=self.current_time,
                        duration_sec=0, velocity=0)
        return HitResult(note=dummy, quality="MISS",
                        time_offset_ms=999, score_earned=0, xp_earned=0)

    def _register_miss(self, note: MidiNote) -> HitResult:
        """Register a missed note (HARD mode: also costs points)."""
        self._break_combo()
        self.stats.score = max(0, self.stats.score - SCORE_PERFECT // 2)
        return HitResult(note=note, quality="MISS", time_offset_ms=0,
                         score_earned=0, xp_earned=0)

    def get_song_progress(self) -> float:
        if self.song.duration_sec <= 0:
            return 0.0
        return max(0.0, min(1.0, self.current_time / self.song.duration_sec))
