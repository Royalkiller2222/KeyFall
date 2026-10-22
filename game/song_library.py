"""
KeyFall - Song Library
Folder-based song organisation with difficulty variants.

Expected structure:
  songs/
    Song Title/
      easy.mid
      medium.mid
      hard.mid
      cover.png          (optional)
      info.txt           (optional: BPM override, author, etc.)
    Another Song/
      hard.mid
    # Legacy: flat .mid files still work too
    old_song.mid

Parsed songs are cached in cache/songs/ (keyed by file size + modification time), so a
big MIDI is only parsed once instead of on every launch and every Refresh.
"""

import hashlib
import os
import json
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Dict
from game.midi_handler import MidiParser, MidiNote, SongData, create_demo_song, PARSER_VERSION
from game.constants import BASE_DIR, SONGS_DIR, MODE_EASY, MODE_HARD, MODE_TESTING

CACHE_DIR = os.path.join(BASE_DIR, "cache", "songs")

DIFFICULTY_FILES = {
    "EASY":    ["easy.mid",    "easy.midi"],
    "MEDIUM":  ["medium.mid",  "medium.midi", "normal.mid", "normal.midi"],
    "HARD":    ["hard.mid",    "hard.midi",   "expert.mid", "expert.midi"],
    "EXTREME": ["extreme.mid", "extreme.midi","insane.mid", "insane.midi"],
}

DIFFICULTY_ORDER = ["EASY", "MEDIUM", "HARD", "EXTREME"]

DIFFICULTY_COLORS = {
    "EASY":    (0,  255, 120),   # bright lime green
    "MEDIUM":  (255, 220, 0),    # bright yellow
    "HARD":    (255,  40, 40),   # bright red
    "EXTREME": (220,  0, 255),   # bright purple/magenta
}


@dataclass
class SongEntry:
    """A song with potentially multiple difficulty variants."""
    title: str
    folder: str                          # absolute path to folder (or "" for flat files)
    difficulties: Dict[str, SongData]    # difficulty -> SongData
    has_cover: bool = False
    author: str = ""

    def __post_init__(self):
        for diff, song in self.difficulties.items():
            song.difficulty = diff   # lets results/leaderboards tell charts apart

    @property
    def available_difficulties(self) -> List[str]:
        return [d for d in DIFFICULTY_ORDER if d in self.difficulties]

    @property
    def best_difficulty(self) -> str:
        """Return the hardest available difficulty."""
        for d in reversed(DIFFICULTY_ORDER):
            if d in self.difficulties:
                return d
        return DIFFICULTY_ORDER[0]

    def get_song(self, difficulty: str = None) -> Optional[SongData]:
        if difficulty and difficulty in self.difficulties:
            return self.difficulties[difficulty]
        # Fallback chain
        for d in DIFFICULTY_ORDER:
            if d in self.difficulties:
                return self.difficulties[d]
        return None


# ── Parse cache ───────────────────────────────────────────────────
def _cache_path(path: str) -> str:
    digest = hashlib.sha1(os.path.abspath(path).lower().encode("utf-8")).hexdigest()[:16]
    return os.path.join(CACHE_DIR, digest + ".json")


def load_song(path: str) -> Optional[SongData]:
    """Parse a MIDI file, reusing the cached result while the file is unchanged."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = {"v": PARSER_VERSION, "size": st.st_size, "mtime": st.st_mtime_ns}
    cache = _cache_path(path)
    try:
        with open(cache, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("key") == key:
            notes = [MidiNote(p, t, d, v, tr) for p, t, d, v, tr in data["notes"]]
            song = SongData(title=os.path.splitext(os.path.basename(path))[0], filename=path,
                            notes=notes, bpm=data["bpm"])
            if notes:
                song.duration_sec = max(n.time_sec + n.duration_sec for n in notes)
                song.min_pitch = min(n.pitch for n in notes)
                song.max_pitch = max(n.pitch for n in notes)
            return song
    except (OSError, ValueError, KeyError, TypeError):
        pass   # missing, stale or unreadable cache: parse the file
    song = MidiParser.parse(path)
    if song and song.notes:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = cache + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"key": key, "bpm": song.bpm,
                           "notes": [[n.pitch, round(n.time_sec, 5), round(n.duration_sec, 5),
                                      n.velocity, n.track] for n in song.notes]},
                          f, separators=(",", ":"))
            os.replace(tmp, cache)
        except OSError:
            pass   # read-only install folder: just parse again next time
    return song


def _parse_info(folder: str) -> Dict[str, str]:
    """Parse optional info.txt in song folder."""
    info_path = os.path.join(folder, "info.txt")
    result = {}
    if os.path.exists(info_path):
        try:
            with open(info_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if ":" in line:
                        key, val = line.split(":", 1)
                        result[key.strip().lower()] = val.strip()
        except Exception:
            pass
    return result


def scan_songs_library(progress: Optional[Callable[[int, int, str], None]] = None) -> List[SongEntry]:
    """
    Scan the songs/ directory and return SongEntry list.
    Supports both flat .mid files and subfolder-based organisation.
    progress(done, total, name) is called before each item (e.g. to draw a loading screen).
    """
    entries: List[SongEntry] = []

    if not os.path.isdir(SONGS_DIR):
        os.makedirs(SONGS_DIR, exist_ok=True)

    items = [i for i in sorted(os.listdir(SONGS_DIR)) if not i.startswith("_")]  # skip system folders

    for n_done, item in enumerate(items):
        if progress:
            progress(n_done, len(items), item)
        item_path = os.path.join(SONGS_DIR, item)

        # ── Subfolder with difficulty variants ──────────────────────
        if os.path.isdir(item_path):
            difficulties: Dict[str, SongData] = {}
            info = _parse_info(item_path)

            for diff, filenames in DIFFICULTY_FILES.items():
                # Check flat files first (e.g. easy.mid directly in folder)
                for fname in filenames:
                    fpath = os.path.join(item_path, fname)
                    if os.path.exists(fpath):
                        song = load_song(fpath)
                        if song and song.notes:
                            song.title = item
                            difficulties[diff] = song
                            break
                if diff in difficulties:
                    continue
                # Also check inside a difficulty subfolder
                # e.g. songs/Song Name/medium/anything.mid
                diff_subfolder = os.path.join(item_path, diff.lower())
                if os.path.isdir(diff_subfolder):
                    for fname in sorted(os.listdir(diff_subfolder)):
                        if fname.lower().endswith((".mid", ".midi")):
                            fpath = os.path.join(diff_subfolder, fname)
                            song = load_song(fpath)
                            if song and song.notes:
                                song.title = item
                                difficulties[diff] = song
                                break

            # Also pick up any .mid not matching difficulty names
            # and treat them as MEDIUM if no difficulties found
            if not difficulties:
                for fname in os.listdir(item_path):
                    if fname.lower().endswith((".mid", ".midi")):
                        fpath = os.path.join(item_path, fname)
                        song = load_song(fpath)
                        if song and song.notes:
                            song.title = item
                            difficulties["MEDIUM"] = song
                            break

            if difficulties:
                has_cover = os.path.exists(os.path.join(item_path, "cover.png"))
                entry = SongEntry(
                    title=info.get("title", item),
                    folder=item_path,
                    difficulties=difficulties,
                    has_cover=has_cover,
                    author=info.get("author", ""),
                )
                entries.append(entry)

        # ── Flat .mid file (legacy) ──────────────────────────────────
        elif item.lower().endswith((".mid", ".midi")):
            song = load_song(item_path)
            if song and song.notes:
                title = os.path.splitext(item)[0]
                song.title = title
                entry = SongEntry(
                    title=title,
                    folder="",
                    difficulties={"MEDIUM": song},
                )
                entries.append(entry)

    if not entries:
        # Built-in demo
        demo = create_demo_song()
        entries.append(SongEntry(
            title=demo.title,
            folder="",
            difficulties={"MEDIUM": demo},
        ))

    return entries


def create_song_folder_template(title: str) -> str:
    """
    Create a new song folder with placeholder info and README.
    Returns the created folder path.
    """
    safe_title = "".join(c for c in title if c.isalnum() or c in " _-").strip()
    folder = os.path.join(SONGS_DIR, safe_title)
    os.makedirs(folder, exist_ok=True)

    readme = os.path.join(folder, "README.txt")
    if not os.path.exists(readme):
        with open(readme, "w") as f:
            f.write(f"Song: {title}\n\n")
            f.write("Place MIDI files in this folder:\n")
            f.write("  easy.mid    — Easy difficulty\n")
            f.write("  medium.mid  — Medium difficulty\n")
            f.write("  hard.mid    — Hard difficulty\n\n")
            f.write("Optional info.txt format:\n")
            f.write("  title: Display Title\n")
            f.write("  author: Composer Name\n")

    info = os.path.join(folder, "info.txt")
    if not os.path.exists(info):
        with open(info, "w") as f:
            f.write(f"title: {title}\n")
            f.write(f"author: Unknown\n")

    return folder
