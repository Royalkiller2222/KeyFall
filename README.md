# 🎹 KEYFALL

A Rocksmith-style 3D piano learning game with MIDI support.

---

## 🚀 Quick Start (Running from Python)

### 1. Install Python 3.10+
Download from https://python.org

### 2. Install dependencies
Open a terminal/command prompt in this folder and run:
```
pip install -r requirements.txt
```

### 3. Add your songs
Place `.mid` / `.midi` files into the `songs/` folder.
A demo song is built-in if the folder is empty.

### 4. Connect your MIDI piano
Plug in your USB MIDI piano **before** launching.

### 5. Run the game
```
python main.py
```

---

## 🎮 Controls

### Menus
| Key | Action |
|-----|--------|
| ↑ / ↓ | Navigate |
| ENTER | Select |
| ESC | Back |
| M | Toggle Easy/Hard mode (Song Select) |

### In-Game
| Key | Action |
|-----|--------|
| ESC | Pause/Resume |
| F1 | Toggle Easy ↔ Hard mode |
| F5 | Restart song |
| F10 | End song & see results |
| A S D F G H J K ... | Keyboard fallback (if no MIDI piano) |

---

## 🎯 Game Modes

### EASY MODE 🟢
Song pauses and waits until you play the correct note.
Great for learning new songs.

### HARD MODE 🔴
Song keeps playing. Wrong notes penalize your score.
Combo breaks on any miss.

---

## ⭐ Scoring System

| Hit Quality | Score | XP |
|-------------|-------|----|
| PERFECT (±40ms) | 100 × multiplier | 10 |
| GREAT (±80ms) | 70 × multiplier | 7 |
| GOOD (±130ms) | 40 × multiplier | 3 |
| MISS | 0 (Hard: -50) | 0 |

**Combo Multiplier:** Every 10 hits increases multiplier (max 8×)

---

## 🏆 Grades
| Grade | Accuracy |
|-------|----------|
| S+ | 98%+ with 0 misses |
| S | 95%+ |
| A | 88%+ |
| B | 75%+ |
| C | 60%+ |
| D | Below 60% |

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

## 🎵 Supported MIDI Files

Any standard `.mid` file works. Great sources:
- **Musescore.com** — free sheet music with MIDI export
- **ClassicPianoMidi.com** — classical pieces
- **midiworld.com** — huge library
- Export from **GarageBand**, **FL Studio**, **Musescore**

---

## 🔧 Troubleshooting

**MIDI piano not detected?**
- Connect piano before launching
- Install your piano's USB driver if required
- Check Device Manager to confirm it's recognized as MIDI device

**Low FPS?**
- Close other applications
- Reduce your display resolution in constants.py

**No sound?**
The game currently focuses on visual feedback.
Audio playback (backing track) is planned for Phase 2!
