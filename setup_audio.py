"""
KeyFall - First-run audio setup
Downloads the YDP Grand Piano soundfont (Yamaha Disklavier, FreePats project) and the
FluidSynth synthesizer DLLs (official Windows release, checked against a pinned SHA-256).
"""

import hashlib, os, sys, urllib.request, tarfile, shutil, zipfile

import sys as _sys
if getattr(_sys, "frozen", False):
    BASE = os.path.dirname(_sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))
FDIR    = os.path.join(BASE, "fluidsynth")
SF2     = os.path.join(FDIR, "pianos", "piano.sf2")
DONE    = os.path.join(FDIR, ".setup_done")

# YDP Grand Piano - Yamaha Disklavier, 36MB tar.bz2, real grand piano samples
# CC Attribution 3.0, FreePats project
YDP_URL  = "https://freepats.zenvoid.org/Piano/YDP-GrandPiano/YDP-GrandPiano-SF2-20160804.tar.bz2"
YDP_NAME = "YDP Grand Piano (Yamaha Disklavier)"

# FluidSynth: official GitHub release, pinned by version and SHA-256 of the zip.
# LGPL-2.1 (see licenses/). Only the DLLs the game loads are extracted.
FS_VERSION = "2.6.2"
FS_URL = (f"https://github.com/FluidSynth/fluidsynth/releases/download/v{FS_VERSION}/"
          f"fluidsynth-v{FS_VERSION}-win10-x64-cpp11.zip")
FS_SHA256 = "808295345d43c9c428f3fa87d29fbf97a9926f356df95559ff2689f3bd4072d7"
FS_DLLS = ("libfluidsynth-3.dll", "sndfile.dll", "SDL3.dll")
FS_DIR = os.path.join(BASE, "lib", "fluidsynth")
FS_STAMP = os.path.join(FS_DIR, "VERSION.txt")


def is_valid_sf2(path):
    try:
        with open(path, "rb") as f:
            h = f.read(12)
        return len(h) >= 12 and h[:4] == b"RIFF" and h[8:12] == b"sfbk"
    except Exception:
        return False


def download(url, dest, label):
    print(f"  Downloading {label}...", flush=True)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 KeyFall/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            total = int(r.headers.get("Content-Length", 0))
            done  = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = r.read(65536)
                    if not chunk: break
                    f.write(chunk)
                    done += len(chunk)
                    if total:
                        pct = int(done/total*30)
                        print(f"\r  [{('#'*pct).ljust(30)}] {done//1024}KB/{total//1024}KB",
                              end="", flush=True)
        print(f"\r  Downloaded {done//1024}KB                              ")
        return done
    except Exception as e:
        print(f"\r  Failed: {e}                                            ")
        return 0


def fluidsynth_ready():
    try:
        with open(FS_STAMP, encoding="utf-8") as f:
            stamped = f.read().strip()
    except OSError:
        return False
    return stamped == FS_VERSION and all(os.path.exists(os.path.join(FS_DIR, d)) for d in FS_DLLS)


def setup_fluidsynth():
    if fluidsynth_ready():
        print(f"  [OK] FluidSynth {FS_VERSION} already installed.")
        return True
    if sys.platform != "win32":
        print("  FluidSynth download is Windows-only - the built-in sample player will be used.")
        return False
    os.makedirs(FS_DIR, exist_ok=True)
    tmp = os.path.join(FS_DIR, "_fluidsynth.zip")
    try:
        if download(FS_URL, tmp, f"FluidSynth {FS_VERSION} (~3 MB)") < 100_000:
            return False
        with open(tmp, "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        if digest != FS_SHA256:
            print(f"  FluidSynth download has the wrong checksum ({digest}) - not installed.")
            return False
        with zipfile.ZipFile(tmp) as z:
            members = {os.path.basename(n): n for n in z.namelist() if "/bin/" in n}
            for dll in FS_DLLS:
                if dll not in members:
                    print(f"  {dll} missing from the FluidSynth archive - not installed.")
                    return False
            for dll in FS_DLLS:
                with z.open(members[dll]) as src, open(os.path.join(FS_DIR, dll), "wb") as dst:
                    shutil.copyfileobj(src, dst)
        with open(FS_STAMP, "w", encoding="utf-8") as f:
            f.write(FS_VERSION + "\n")
        print(f"  [OK] FluidSynth {FS_VERSION} installed in lib/fluidsynth.")
        return True
    except Exception as e:
        print(f"  FluidSynth setup failed: {e}")
        return False
    finally:
        try: os.remove(tmp)
        except OSError: pass


def setup():
    # piano.sf2 is the default — always check for it specifically
    if os.path.exists(DONE) and is_valid_sf2(SF2):
        print("  [OK] Soundfont already ready.")
        return True

    # Clean up invalid files
    for f in [SF2, DONE]:
        try:
            if os.path.exists(f): os.remove(f)
        except Exception: pass

    print("\n  ┌──────────────────────────────────────────────────┐")
    print("  │  Downloading YDP Grand Piano soundfont           │")
    print("  │  Yamaha Disklavier — real grand piano samples    │")
    print("  │  FreePats project (CC Attribution 3.0)           │")
    print("  │  ~36MB — this only happens once                  │")
    print("  └──────────────────────────────────────────────────┘\n")

    os.makedirs(os.path.join(FDIR, "pianos"), exist_ok=True)
    tmp_tar = os.path.join(FDIR, "_piano.tar.bz2")

    # ── Try YDP Grand Piano (tar.bz2) ────────────────────────────
    sz = download(YDP_URL, tmp_tar, YDP_NAME)
    if sz > 100_000:
        try:
            print("  Extracting...", flush=True)
            with tarfile.open(tmp_tar, "r:bz2") as tar:
                # Find the .sf2 inside
                sf2_members = [m for m in tar.getmembers()
                               if m.name.lower().endswith(".sf2")]
                if sf2_members:
                    m = sf2_members[0]
                    m.name = os.path.basename(m.name)  # strip path
                    tar.extract(m, FDIR)
                    extracted = os.path.join(FDIR, m.name)
                    shutil.move(extracted, SF2)
                    print(f"  Extracted: {sf2_members[0].name}")
                else:
                    print(f"  No SF2 in archive. Contents: {[m.name for m in tar.getmembers()[:5]]}")
        except Exception as e:
            print(f"  Extraction failed: {e}")
        finally:
            try: os.remove(tmp_tar)
            except: pass

    # ── Validate YDP result ───────────────────────────────────────
    if is_valid_sf2(SF2):
        open(DONE, 'w').write('ok\n')
        print(f"\n  [OK] YDP Grand Piano ready! ({os.path.getsize(SF2)//1024}KB)")
        print("  [OK] Audio setup complete!\n")
        return True

    # ── Download failed ───────────────────────────────────────────
    print("\n  ─────────────────────────────────────────────────────")
    print("  Auto-download failed. Manual setup:")
    print()
    print("  Option A — YDP Grand Piano (recommended, 36MB):")
    print("    1. Download from:")
    print("       https://freepats.zenvoid.org/Piano/YDP-GrandPiano/")
    print("       YDP-GrandPiano-SF2-20160804.tar.bz2")
    print("    2. Extract the .sf2 file from the archive")
    print("    3. Rename it piano.sf2")
    print(f"    4. Place in: {FDIR}")
    print()
    print("  Option B — Any SF2 piano soundfont:")
    print("    https://musical-artifacts.com/artifacts?formats=sf2&tags=piano")
    print()
    print("  Game works fine with built-in synth in the meantime.")
    print("  ─────────────────────────────────────────────────────\n")

    open(DONE, 'w').write('failed\n')
    return False


if __name__ == "__main__":
    piano_ok = setup()
    fs_ok = setup_fluidsynth()   # optional for playing: without it the sample player is used
    sys.exit(0 if piano_ok and fs_ok else 1)
