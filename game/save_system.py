"""
KeyFall - Save System
Persists player XP, level, and song leaderboards
"""

import copy
import json
import os
from game.constants import SAVE_FILE, DEFAULT_REVERB


DEFAULT_SAVE = {
    "total_xp": 0,
    "leaderboard": {},  # song_title -> [{"score", "accuracy", "grade", "combo"}]
    "song_options": {},  # song title -> {"reverb": %, "sustain": bool}; only songs changed
}


def load_save() -> dict:
    if os.environ.get("KEYFALL_SELFTEST") == "1":
        return copy.deepcopy(DEFAULT_SAVE)  # deterministic defaults for automated runs
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError("save file does not contain an object")
            # Merge with defaults
            for key, val in DEFAULT_SAVE.items():
                data.setdefault(key, copy.deepcopy(val))
            return data
        except Exception as e:
            # Keep the unreadable file so progress can be recovered by hand,
            # instead of overwriting it with defaults on the next save.
            backup = SAVE_FILE + ".corrupt"
            try:
                os.replace(SAVE_FILE, backup)
            except OSError:
                pass
            print(f"[Save] Load failed: {e}, using defaults (old file kept as {backup})")
    return copy.deepcopy(DEFAULT_SAVE)


def save_game(data: dict):
    if os.environ.get("KEYFALL_SELFTEST") == "1":
        return  # automated smoke tests never touch the player's save
    tmp = SAVE_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, SAVE_FILE)  # atomic: a crash mid-write can't corrupt the save
    except Exception as e:
        print(f"[Save] Save failed: {e}")


def song_options(save_data: dict, title: str) -> dict:
    """A song's sound options: {"reverb": 0..100 (%), "sustain": bool}."""
    saved = save_data.get("song_options")
    opt = saved.get(title) if isinstance(saved, dict) else None
    if not isinstance(opt, dict):
        opt = {}
    try:
        reverb = int(round(float(opt.get("reverb", DEFAULT_REVERB))))
    except (TypeError, ValueError):
        reverb = DEFAULT_REVERB
    return {"reverb": max(0, min(100, reverb)), "sustain": opt.get("sustain") is True}


def set_song_options(save_data: dict, title: str, reverb: int, sustain: bool):
    """Store a song's sound options (the caller saves). A song back at the defaults is
    dropped from the save."""
    saved = save_data.get("song_options")
    if not isinstance(saved, dict):
        saved = save_data["song_options"] = {}
    reverb = max(0, min(100, int(round(reverb))))
    if reverb == DEFAULT_REVERB and not sustain:
        saved.pop(title, None)
    else:
        saved[title] = {"reverb": reverb, "sustain": bool(sustain)}


def leaderboard_key(song, mode: str, speed: float) -> str:
    """Personal bests compare like with like: same chart (song + difficulty), mode and speed."""
    return (f"{song.title} | {getattr(song, 'difficulty', '') or '-'} | "
            f"{mode} | {round(speed * 100)}%")


def add_leaderboard_entry(save_data: dict, song_title: str, stats):
    """Add a result to the leaderboard for a song (the caller saves)."""
    lb = save_data.setdefault("leaderboard", {})
    entries = lb.setdefault(song_title, [])

    entry = {
        "score": stats.score,
        "accuracy": round(stats.accuracy, 1),
        "grade": stats.get_grade(),
        "combo": stats.max_combo,
        "streak": stats.max_streak,
    }

    entries.append(entry)
    # Keep top 10 only
    entries.sort(key=lambda e: e["score"], reverse=True)
    lb[song_title] = entries[:10]
