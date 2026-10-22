"""
KeyFall - Save System
Persists player XP, level, and song leaderboards
"""

import copy
import json
import os
from game.constants import SAVE_FILE


DEFAULT_SAVE = {
    "total_xp": 0,
    "leaderboard": {},  # song_title -> [{"score", "accuracy", "grade", "combo"}]
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


def add_leaderboard_entry(save_data: dict, song_title: str, stats):
    """Add a result to the leaderboard for a song."""
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
    save_game(save_data)
