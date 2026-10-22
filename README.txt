# 🎹 KEYFALL — Quick Start

## Easiest — download the game
Get the latest KeyFall-...-windows.zip from
**https://github.com/Royalkiller2222/KeyFall/releases**, unzip it and run **KeyFall.exe**.
No Python needed. (If Windows SmartScreen warns you: More info → Run anyway.)

---

## Or run from source

### Step 1 — Install Python 3.12 (one time only)
Download and install Python from: **https://www.python.org/downloads/**

> ⚠️ During install, check the box that says **"Add Python to PATH"**

### Step 2 — Double-click to play
Double-click **`PLAY_KEYFALL.bat`**

The first launch installs everything automatically (~1 minute) and downloads the piano
sound (~35 MB). Every launch after that starts instantly.

---

## Add your songs
Drop any `.mid` or `.midi` files into the **`songs\`** folder.
A built-in demo song plays if the folder is empty.

---

## 🎮 Controls

| Key | Action |
|-----|--------|
| ↑ ↓ | Navigate menus |
| ENTER | Select |
| ESC | Back / in-game pause menu (change mode there) |
| M | Change mode in Song Select |
| F5 | Restart song |
| F10 | End song |
| A S D F G H J... | Play notes (if no MIDI piano) |

---

## 🎯 Modes
- **EASY** 🟢 — The song waits until you play the notes at the hit line
- **HARD** 🔴 — The song keeps going; misses cost points and break your combo
- **TESTING** 🟠 — Autoplay: watch and listen (not scored)

---

## ❓ Troubleshooting
- **MIDI piano not detected** → Plug in your piano, then re-launch
- **"Python not found"** → Reinstall Python and check "Add to PATH"
- **Game closed by itself** → Open `keyfall_crash.txt` next to the game for details
