"""
KeyFall - Song Organizer
Watches the songs/ folder for flat .mid files and automatically
organizes them into a proper folder structure:

  songs/
    Song Name/
      easy/      (empty)
      medium/
        Song Name.mid   ← moved here
      hard/      (empty)
      extreme/   (empty)
"""

import os
import shutil


SONGS_DIR = "songs"
DIFFICULTIES = ["easy", "medium", "hard", "extreme"]


def organize_flat_midis() -> list:
    """
    Scan songs/ for any .mid/.midi files sitting directly in the root
    (not inside a subfolder). Move each one into:
        songs/<Song Name>/medium/<Song Name>.mid
    and create the other difficulty folders empty.
    Returns list of song names that were organized.
    """
    if not os.path.exists(SONGS_DIR):
        return []

    organized = []

    for fname in sorted(os.listdir(SONGS_DIR)):
        fpath = os.path.join(SONGS_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if not fname.lower().endswith((".mid", ".midi")):
            continue

        # Strip extension to get song name
        song_name = os.path.splitext(fname)[0]

        # Create the folder structure
        song_folder = os.path.join(SONGS_DIR, song_name)
        os.makedirs(song_folder, exist_ok=True)

        for diff in DIFFICULTIES:
            diff_folder = os.path.join(song_folder, diff)
            os.makedirs(diff_folder, exist_ok=True)

        # Move the midi into the medium folder
        dest = os.path.join(song_folder, "medium", fname)
        try:
            shutil.move(fpath, dest)
            organized.append(song_name)
            print(f"[Organizer] Organized: {fname} → {song_name}/medium/")
        except Exception as e:
            print(f"[Organizer] Failed to move {fname}: {e}")

    return organized


def ensure_difficulty_folders(song_folder: str):
    """Ensure all 4 difficulty folders exist for a song folder."""
    for diff in DIFFICULTIES:
        os.makedirs(os.path.join(song_folder, diff), exist_ok=True)
