"""
KeyFall - First-run audio setup
Downloads the YDP Grand Piano soundfont (Yamaha Disklavier, FreePats project).
"""

import os, sys, urllib.request, tarfile, shutil

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

# Fallback: UprightPianoKW SF2, 27MB 7z - skip if 7z not available
# Fallback 2: FluidR3 zip
FALLBACK_URL  = "https://keymusician01.s3.amazonaws.com/FluidR3_GM.zip"
FALLBACK_NAME = "FluidR3 GM"


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
    tmp_zip = os.path.join(FDIR, "_piano.zip")
    tmp_sf2 = os.path.join(FDIR, "_piano.sf2")

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

    # ── Fallback: FluidR3 GM zip ──────────────────────────────────
    print(f"\n  Trying fallback: {FALLBACK_NAME}...")
    import zipfile
    sz = download(FALLBACK_URL, tmp_zip, FALLBACK_NAME)
    if sz > 100_000:
        try:
            with zipfile.ZipFile(tmp_zip, 'r') as z:
                sf2s = [n for n in z.namelist() if n.lower().endswith('.sf2')]
                if sf2s:
                    with z.open(sf2s[0]) as zf, open(tmp_sf2, 'wb') as out:
                        shutil.copyfileobj(zf, out)
                    shutil.move(tmp_sf2, SF2)
        except Exception as e:
            print(f"  Fallback failed: {e}")
        finally:
            try: os.remove(tmp_zip)
            except: pass

    if is_valid_sf2(SF2):
        open(DONE, 'w').write('ok\n')
        print(f"\n  [OK] Fallback soundfont ready ({os.path.getsize(SF2)//1024}KB)")
        return True

    # ── All failed ────────────────────────────────────────────────
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
    setup()
