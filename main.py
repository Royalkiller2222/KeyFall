# NO IMPORTS YET - write crash file first using only builtins
import sys as _sys, os as _os
_base = (_os.path.dirname(_sys.executable) if getattr(_sys,"frozen",False)
         else _os.path.dirname(_os.path.abspath(__file__)))
_os.chdir(_base)  # Set working directory to game folder
_cf = open(_os.path.join(_base, "keyfall_crash.txt"), "w", encoding="utf-8")


def _log(msg):
    _cf.write(msg + "\n"); _cf.flush()


def _report_crash(tb):
    """Save the traceback, then tell the player - the windowed EXE has no console."""
    try:
        _log(f"\nCRASH:\n{tb}")
    except Exception:
        pass
    if _os.environ.get("KEYFALL_SELFTEST") == "1":
        return  # automated run: a dialog would block forever
    if getattr(_sys, "frozen", False) or _sys.stdin is None:
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None, f"KeyFall crashed. Details were saved to:\n{_cf.name}\n\n{tb[-1500:]}",
                "KeyFall", 0x10)
        except Exception:
            pass
    else:
        print(tb)
        try:
            input("Press Enter to close...")
        except Exception:
            pass


try:
    _log("main.py line 1 - Python is alive")
    import importlib, traceback
    for _name in ("pygame", "mido", "numpy", "game.constants", "game.midi_handler",
                  "game.song_library", "game.save_system", "game.gameplay",
                  "game.fluidsynth_engine", "game.audio", "game.renderer", "game.menus",
                  "game.settings_screen", "game.app"):
        _log(f"importing {_name}")
        _mod = importlib.import_module(_name)
        _log(f"{_name} OK" + (f": {_mod.__version__}" if _name == "pygame" else ""))
    from game.app import App
    _log("ALL IMPORTS DONE - creating App")
    app = App()
    _log("App created - running")
    app.run()
except SystemExit:
    raise
except Exception:
    import traceback
    _report_crash(traceback.format_exc())
    _sys.exit(1)
finally:
    try:
        _cf.close()
    except Exception:
        pass
