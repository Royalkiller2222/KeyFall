KeyFall - Custom Sound Effects
==============================

Drop replacement WAV files here to customize sounds.
The game loads these at startup — replace any file and relaunch.

Files:
  miss.wav         — plays when you press a wrong key or miss a note
  hover.wav        — plays when hovering over a song in the selector
  song_start.wav   — plays when a song begins (after the countdown)
  song_complete.wav — plays when you finish a song

Requirements:
  - WAV format (.wav)
  - Stereo or mono (both work)
  - Any sample rate (resampled automatically by pygame)
  - Keep volumes reasonable — the game respects your SFX volume setting

If a file is missing or corrupt, the game falls back to its built-in
synthesized version automatically.
