"""
KeyFall - Save System
Persists player XP, level, and song leaderboards
"""

import json
import os
from game.constants import SAVE_FILE


DEFAULT_SAVE = {
    "total_xp": 0,
    "leaderboard": {},  # song_title -> [{"score", "accuracy", "grade", "combo"}]
}


def load_save() -> dict:
    if os.path.exists(SAVE_FILE):
        try:
            with open(SAVE_FILE, "r") as f:
                data = json.load(f)
            # Merge with defaults
            for key, val in DEFAULT_SAVE.items():
                if key not in data:
                    data[key] = val
            return data
        except Exception as e:
            print(f"[Save] Load failed: {e}, using defaults")
    return dict(DEFAULT_SAVE)


def save_game(data: dict):
    try:
        with open(SAVE_FILE, "w") as f:
            json.dump(data, f, indent=2)
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
