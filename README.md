# 🎹 KEYFALL

A Rocksmith-style 3D piano learning game with MIDI support.

---

## 🚀 Quick Start

### Option A: Download the game (no Python needed)
Get the latest `KeyFall-…-windows.zip` from the
[Releases page](https://github.com/Royalkiller2222/KeyFall/releases), unzip it anywhere and
run **KeyFall.exe**. Windows may show a SmartScreen warning because the EXE isn't signed:
click **More info → Run anyway**.

### Option B: Run from source
1. Install Python 3.12 from https://python.org
2. Double-click **PLAY_KEYFALL.bat**. The first launch installs the packages from
   `requirements.txt` and downloads the piano soundfont (about 35 MB, once).

Or by hand: `pip install -r requirements.txt`, `python setup_audio.py`, `python main.py`.

### Your MIDI piano
Plug it in **before** launching. Velocity (how hard you play) and the sustain pedal are
supported. If no piano is connected you can use the computer keyboard.

---

## 🎮 Controls

### Menus
| Key | Action |
|-----|--------|
| ↑ / ↓ or mouse | Navigate |
| ENTER | Select |
| ESC | Back |
| ← / → | Change difficulty (Song Select) |
| M | Cycle mode Hard → Easy → Testing (Song Select) |
| F11 | Fullscreen |

Song Select also has practice speed buttons (100 / 75 / 50 / 25 %) and **Open Folder** /
**Refresh** buttons for adding songs.

### In-Game
| Key | Action |
|-----|--------|
| ESC | Pause menu: Resume · Restart · Settings · Toggle Mode · Main Menu |
| F5 | Restart (keeps the practice speed) |
| F10 | End song & see results |
| A S D F G H J K L Q W E R T | Keyboard fallback for the song's lowest 14 notes |

### Free Play
| Key | Action |
|-----|--------|
| Z … M (and S D G H J) | C4 – B4 |
| Q … P (and 2 3 5 6 7 9 0) | C5 – E6 |
| ← / → | Octave down / up |
| SPACE | Sustain pedal |
| Mouse | Click or drag across keys |

---

## 🎯 Game Modes

### HARD 🔴
The song keeps going. Notes you don't play in time are misses, and so is pressing a key too
early for its next note. Each miss costs 50 points and breaks your combo.

### EASY 🟢 (wait mode)
The song stops when a note or chord reaches the hit line and continues once you've played
every note of it. Wrong keys are ignored, nothing counts as a miss, and notes played up to
a second early are accepted. Great for learning new songs.

### TESTING 🟠 (autoplay)
The song plays itself so you can watch and listen. Autoplay runs earn no XP and no
leaderboard entries. This is the default mode until you change it in Settings.

---

## ⭐ Scoring

| Hit Quality | Timing | Score | XP |
|-------------|--------|-------|----|
| PERFECT | within 40 ms | 100 × multiplier | 10 |
| GREAT | within 80 ms | 70 × multiplier | 7 |
| GOOD | within 200 ms (EASY waits: always GOOD) | 40 × multiplier | 3 |
| MISS | — | Hard: −50 | 0 |

**Combo Multiplier:** +1 every 10 notes in a row (max 8×).

Personal bests are kept per song, difficulty, mode and speed.

## 🏆 Grades
| Grade | Requirement |
|-------|-------------|
| GODLIKE | Every note PERFECT |
| SS | Only PERFECT and GREAT, no misses |
| S | No misses |
| A | 90%+ accuracy |
| B | 78%+ |
| C | 62%+ |
| F | Below 62% |

---

## 🔊 Sound

Settings → **Note Sound Mode**:
- **soundfont** (default): plays the `.sf2` chosen under *Soundfont Category / File*. Drop
  extra soundfonts into `fluidsynth/<category>/`. The status line shows which one is loaded.
- **synth**: built-in synthesized piano, no soundfont needed.
- **midi_out**: sends notes to an external synth or digital piano (*MIDI Output Port*).
  *MIDI Out Velocity* overrides the velocity sent (0 = as played).

**Menu music:** put one MIDI file in `songs/_menu_music/`.
**Custom sound effects:** replace the WAV files in `sfx/` (see `sfx/README.txt`).

---

## 🎵 Adding Songs

See `songs/HOW_TO_ADD_SONGS.txt`. In short: drop `.mid` files into `songs/` (they are sorted
into folders automatically), or make a folder per song with `easy.mid`, `medium.mid`,
`hard.mid` and `extreme.mid`. Good sources: MuseScore.com, ClassicPianoMidi.com,
midiworld.com, or export from any DAW.

---

## 📦 Build Windows EXE

Double-click **BUILD_EXE.bat** (or run `python build_release.py`). It installs the pinned
build tools, builds with PyInstaller and updates `dist/KeyFall/`. Your savegame and any songs
you added there are kept. `python build_release.py --zip --selftest` also writes the release
zip and runs the automated smoke test against the built EXE.

## 🚀 Publishing a Release

Double-click **RELEASE.bat** and enter a version (e.g. `1.1.0`). It pushes your commits and a
`v1.1.0` tag. GitHub Actions then builds the EXE on a clean Windows machine, runs the
self-test, and publishes `KeyFall-v1.1.0-windows.zip` on the
[Releases page](https://github.com/Royalkiller2222/KeyFall/releases).
Versions with a hyphen (`1.1.0-beta.1`) are published as pre-releases.

Without the .bat: `git tag v1.1.0` then `git push origin v1.1.0`.

Every push that changes the game also runs the same build + self-test (the **Build**
workflow); the zip can be downloaded from that run for 7 days.

---

## 🔧 Troubleshooting

**MIDI piano not detected?**
- Connect the piano before launching (Free Play also retries every few seconds)
- Install your piano's USB driver if required
- Check Device Manager to confirm it's recognized as a MIDI device

**No sound, or the wrong instrument?**
Settings → Note Sound Mode = *soundfont*, then check the status line under it. If the
selected soundfont is missing, KeyFall falls back to another installed one (pianos first).

**The game closed unexpectedly?**
Details are saved in `keyfall_crash.txt` next to the game. Please include it when
reporting a bug.
