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
   `requirements.txt` and downloads the piano soundfont (about 35 MB) and FluidSynth
   (about 3 MB, checksum-verified), once.

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
| PgUp / PgDn, Home / End | Jump through the song list (Song Select) |
| ← / → | Change difficulty (Song Select) |
| M | Cycle mode Hard → Easy → Autoplay (Song Select) |
| [ / ] | Practice speed 25 / 50 / 75 / 100 % (Song Select) |
| - / + | Reverb for the selected song (Song Select) |
| P | Sustain on / off for the selected song (Song Select) |
| F5 | Refresh the song list (Song Select) |
| F11 | Fullscreen |
| Mouse back button | Back (same as ESC) |

The menus work with the mouse alone. The bar at the bottom of each menu lists the keys it
uses, and each key in it is a button: click **ESC Back** to go back, **ENTER Play** to play,
and so on. Everything in Song Select can also be clicked, and its **Open Folder** /
**Refresh** buttons are there for adding songs.

**Song sound:** Song Select also sets each song's **REVERB** (0–100 %, default 25 %: drag
the slider, scroll over it or press - / +) and **SUSTAIN** (holds the sustain pedal down
for the whole song, default OFF; press P). Both are saved with the song and apply whenever
you play it. The reverb is heard with the SOUNDFONT instrument and through MIDI OUT; with
SYNTH it's still saved, and the slider says what it needs.

### In-Game
| Key | Action |
|-----|--------|
| ESC | Pause menu: Resume · Restart · Settings · Mode · Main Menu |
| F5 | Restart (keeps the practice speed) |
| F10 | End song & see results |
| A S D F G H J K L Q W E R T | Keyboard fallback for the song's lowest 14 notes (the letters are shown on the piano when no MIDI piano is connected) |

A countdown card shows the song, difficulty, mode and speed before the first notes arrive;
its keys can be clicked. While you play, the top of the screen shows your score (with the
mode and speed under it), your combo with the multiplier and a meter that fills toward the
next one, and your accuracy with the grade you're on track for. The song's progress runs
along the far edge of the highway, the notes fall with smooth (anti-aliased) edges, and
every judged note pops up as PERFECT, GREAT, GOOD or MISS. In EASY mode a panel names the
notes the song is waiting for. Move the mouse during a song and the pointer appears with
**ESC Pause**, **F5 Restart** and **F10 End song** as buttons under the score; they fade
out when the mouse rests.

### Free Play
An 88-key piano with nothing scored: click or drag across the keys, type the letters shown on
them, or play a MIDI keyboard. Every note rises from its key as a neon bar, and the notes you
play are named at the top with the chord or interval they make (C MAJOR, G7, PERFECT 5TH…).
The header shows the octave the letters play, the sustain pedal, the instrument, and whether
a MIDI keyboard is connected.

| Key | Action |
|-----|--------|
| Z … M (and S D G H J) | C4 – B4 |
| Q … P (and 2 3 5 6 7 9 0) | C5 – E6 |
| ← / → | Octave down / up (up to 3 each way) |
| SPACE | Sustain pedal (hold it; clicking SPACE in the bottom bar turns it on / off) |
| Mouse | Click or drag across keys |
| ESC | Back to the main menu |

---

## 🎯 Game Modes

### HARD 🔴
The song keeps going. Notes you don't play in time are misses, and so is pressing a key too
early for its next note. Each miss costs 50 points and breaks your combo.

### EASY 🟢 (wait mode)
The song stops when a note or chord reaches the hit line and continues once you've played
every note of it. Wrong keys are ignored, nothing counts as a miss, and notes played up to
a second early are accepted. Great for learning new songs.

### AUTOPLAY 🟠 (formerly Testing)
The song plays itself so you can watch and listen. Autoplay runs earn no XP and no
leaderboard entries, and switching to it from the pause menu stops that run from being
scored. This is the default mode until you pick another under Settings → DEFAULT MODE.

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

Settings → **INSTRUMENT** picks what plays the notes:
- **SOUNDFONT** (default): plays the `.sf2` picked under *Category* and *Instrument* through
  the [FluidSynth](https://www.fluidsynth.org/) synthesizer, with the soundfont's velocity
  layers, loops, release and reverb. Drop extra soundfonts into `fluidsynth/<category>/`.
  If the FluidSynth DLLs in `lib/fluidsynth/` are missing, a simpler built-in sample player
  is used.
- **SYNTH**: the built-in synthesized piano, no soundfont needed.
- **MIDI OUT**: sends the notes to an external synth, digital piano or music app (*Output
  device*). *Velocity sent* overrides the velocity (AS PLAYED sends it as you played it).

The status line under it says what is playing the notes (*Ready: …*) or, after you pick
another, what SAVE will switch to. **TEST SOUND** plays a note on the instrument in use. The
volumes (Master, Notes, Menu music, Sound effects) are on the same screen and change as you
move them. Nothing is kept until you press **SAVE**; BACK or ESC puts the volumes back and
drops the other changes.

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
- Connect the piano before launching (Free Play also retries every few seconds; its header
  says MIDI CONNECTED once it finds one)
- Install your piano's USB driver if required
- Check Device Manager to confirm it's recognized as a MIDI device

**No sound, or the wrong instrument?**
Settings → INSTRUMENT = **SOUNDFONT** (press SAVE if you changed it), then check the status
line under it and press TEST SOUND. If the selected soundfont is missing, KeyFall falls back
to another installed one (pianos first).

**The game closed unexpectedly?**
Details are saved in `keyfall_crash.txt` next to the game. Please include it when
reporting a bug.
