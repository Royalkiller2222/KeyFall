# NO IMPORTS YET - write crash file first using only builtins
import sys as _sys, os as _os
_base = (_os.path.dirname(_sys.executable) if getattr(_sys,"frozen",False)
         else _os.path.dirname(_os.path.abspath(__file__)))
_os.chdir(_base)  # Set working directory to game folder
_cf = open(_os.path.join(_base, "keyfall_crash.txt"), "w")
_cf.write("main.py line 1 - Python is alive\n")
_cf.flush()

_cf.write("importing sys\n"); _cf.flush()
import sys

_cf.write("importing os\n"); _cf.flush()
import os

_cf.write("importing traceback\n"); _cf.flush()
import traceback

_cf.write("importing pygame\n"); _cf.flush()
import pygame
_cf.write(f"pygame OK: {pygame.__version__}\n"); _cf.flush()

_cf.write("importing mido\n"); _cf.flush()
import mido
_cf.write("mido OK\n"); _cf.flush()

_cf.write("importing numpy\n"); _cf.flush()
import numpy
_cf.write("numpy OK\n"); _cf.flush()

_cf.write("importing game.constants\n"); _cf.flush()
from game.constants import *
_cf.write("constants OK\n"); _cf.flush()

_cf.write("importing game.midi_handler\n"); _cf.flush()
from game.midi_handler import MidiParser, MidiInputHandler, SongData, create_demo_song
_cf.write("midi_handler OK\n"); _cf.flush()

_cf.write("importing game.song_library\n"); _cf.flush()
from game.song_library import scan_songs_library, SongEntry
_cf.write("song_library OK\n"); _cf.flush()

_cf.write("importing game.save_system\n"); _cf.flush()
from game.save_system import load_save, save_game, add_leaderboard_entry
_cf.write("save_system OK\n"); _cf.flush()

_cf.write("importing game.gameplay\n"); _cf.flush()
from game.gameplay import GameplayEngine, XPSystem
_cf.write("gameplay OK\n"); _cf.flush()

_cf.write("importing game.fluidsynth_engine\n"); _cf.flush()
from game import fluidsynth_engine
_cf.write("fluidsynth_engine OK\n"); _cf.flush()

_cf.write("importing game.audio\n"); _cf.flush()
from game.audio import AudioManager
_cf.write("audio OK\n"); _cf.flush()

_cf.write("importing game.renderer\n"); _cf.flush()
from game.renderer import HighwayRenderer
_cf.write("renderer OK\n"); _cf.flush()

_cf.write("importing game.menus\n"); _cf.flush()
from game.menus import MainMenu, SongSelectMenu, ResultsScreen
_cf.write("menus OK\n"); _cf.flush()

_cf.write("importing game.settings_screen\n"); _cf.flush()
from game.settings_screen import SettingsScreen
_cf.write("settings_screen OK\n"); _cf.flush()

_cf.write("importing game.app\n"); _cf.flush()
from game.app import App
_cf.write("app OK\n"); _cf.flush()

_cf.write("ALL IMPORTS DONE - creating App\n"); _cf.flush()

try:
    app = App()
    _cf.write("App created - running\n"); _cf.flush()
    _cf.close()
    app.run()
except Exception as e:
    tb = traceback.format_exc()
    _cf.write(f"\nCRASH IN APP:\n{tb}\n")
    _cf.flush(); _cf.close()
    print(tb)
    input("Press Enter to close...")
    sys.exit(1)
