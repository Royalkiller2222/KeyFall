"""
KeyFall - Constants & Configuration
"""

# Window
WINDOW_TITLE = "KEYFALL"
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
FPS = 120   # frame cap; leaves CPU for the audio and MIDI threads

# Colors (Neon Rocksmith palette)
BLACK       = (0, 0, 0)
DARK_BG     = (5, 5, 15)
NEON_CYAN   = (0, 255, 255)
NEON_PINK   = (255, 0, 180)
NEON_YELLOW = (255, 230, 0)
NEON_GREEN  = (0, 255, 80)
NEON_ORANGE = (255, 120, 0)
NEON_PURPLE = (180, 0, 255)
NEON_RED    = (255, 30, 30)
WHITE       = (255, 255, 255)
GRAY        = (80, 80, 100)
DARK_GRAY   = (20, 20, 35)

# Highway colors per lane (cycling for piano keys)
LANE_COLORS = [
    (0, 220, 255),    # cyan
    (255, 0, 180),    # pink
    (255, 220, 0),    # yellow
    (0, 255, 80),     # green
    (255, 80, 0),     # orange
    (180, 0, 255),    # purple
    (0, 180, 255),    # light blue
    (255, 0, 80),     # red-pink
]

# 3D Highway settings
HIGHWAY_WIDTH = 1100         # pixels wide at hit line
HIGHWAY_VANISH_WIDTH = 180   # pixels wide at vanish point
HIGHWAY_Y_BOTTOM = 680       # hit line Y position
HIGHWAY_Y_TOP = 160          # vanish point Y position
VANISH_X = SCREEN_WIDTH // 2 # center vanish point
HIT_LINE_Y = 630             # where you hit notes

# Note travel settings
NOTE_SCROLL_SPEED = 400      # pixels/sec at full size (at bottom)
NOTE_LOOKAHEAD_SECS = 3.0   # how far ahead to show notes (seconds)

# Hit timing windows (milliseconds)
HIT_PERFECT_MS = 40
HIT_GREAT_MS = 80
HIT_GOOD_MS = 130
HIT_MISS_MS = 200

# Scoring
SCORE_PERFECT = 100
SCORE_GREAT = 70
SCORE_GOOD = 40
SCORE_MISS = 0
COMBO_MULTIPLIER_MAX = 8

# XP
XP_PER_PERFECT = 10
XP_PER_GREAT = 7
XP_PER_GOOD = 3
XP_PER_MISS = 0

# Levels (XP thresholds)
LEVEL_THRESHOLDS = [
    0, 100, 250, 500, 900, 1400, 2000, 2800, 3800, 5000,
    6500, 8500, 11000, 14000, 18000, 23000, 30000, 40000, 55000, 75000
]

# Piano MIDI range to show
PIANO_MIDI_MIN = 21   # A0
PIANO_MIDI_MAX = 108  # C8
NUM_PIANO_KEYS = PIANO_MIDI_MAX - PIANO_MIDI_MIN + 1

# How many lanes to display (show range around active notes)
DISPLAY_LANES = 14   # show 14 keys wide by default (adjusts to song)

# Game modes
MODE_EASY = "EASY"   # wait for correct note
MODE_HARD = "HARD"   # punish wrong notes, keep going
MODE_TESTING = "TESTING"  # notes play automatically

# States
STATE_MENU = "menu"
STATE_SONG_SELECT = "song_select"
STATE_PLAYING = "playing"
STATE_RESULTS = "results"
STATE_LEADERBOARD = "leaderboard"
STATE_SETTINGS = "settings"
STATE_PAUSE_MENU = "pause_menu"

# Paths — resolved relative to EXE or script location
import os as _os, sys as _sys
_BASE = (_os.path.dirname(_sys.executable)
         if getattr(_sys, "frozen", False)
         else _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
BASE_DIR  = _BASE   # folder holding the EXE (or main.py) and the player-editable data
SONGS_DIR = _os.path.join(_BASE, "songs")
SFX_DIR   = _os.path.join(_BASE, "sfx")
SAVE_FILE  = _os.path.join(_BASE, "savegame.json")
