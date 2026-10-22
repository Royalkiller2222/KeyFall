"""
Build the Windows release of KeyFall: PyInstaller (one folder, no console) + game data.

    python build_release.py                    # build, then update dist/KeyFall for local play
    python build_release.py --zip --selftest   # also write the release zip and smoke-test the EXE
    python build_release.py --version v1.2.0 --zip --selftest --no-install    # what CI runs

The app is assembled cleanly in build/KeyFall (that is what gets zipped). dist/KeyFall is then
updated in place: KeyFall.exe and _internal/ are replaced, shipped songs/soundfonts/sfx are
refreshed, and anything you added there (savegame.json, extra songs or soundfonts) is kept.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
STAGE = BUILD / "KeyFall"
DIST = ROOT / "dist"
DATA_DIRS = ("songs", "fluidsynth", "sfx")
NOT_SHIPPED = (".setup_done", "_piano.*", "__pycache__", "*.pyc")
RUNTIME_FILES = ("keyfall_crash.txt", "keyfall_selftest.txt", "savegame.json", "cache")
BUILD_INFO = ROOT / "game" / "_build_info.py"
PIANO = ROOT / "fluidsynth" / "pianos" / "piano.sf2"


def log(msg):
    print(f"[build] {msg}", flush=True)


def default_version():
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.strip()
        return out or "dev"
    except (OSError, subprocess.CalledProcessError):
        return "dev"


def run_pyinstaller(version):
    BUILD_INFO.write_text(f"VERSION = {version!r}\n", encoding="utf-8")
    try:
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--log-level", "WARN",
            "--onedir", "--windowed", "--noupx", "--name", "KeyFall",
            "--distpath", str(BUILD / "pyinstaller"), "--workpath", str(BUILD / "work"),
            "--specpath", str(BUILD),
            # mido loads its MIDI backends by name at runtime
            "--hidden-import", "mido.backends.rtmidi", "--hidden-import", "mido.backends.pygame",
            "--hidden-import", "game._build_info",
            str(ROOT / "main.py"),
        ], check=True, cwd=ROOT)
    finally:
        BUILD_INFO.unlink(missing_ok=True)


def assemble():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    shutil.copytree(BUILD / "pyinstaller" / "KeyFall", STAGE)
    for d in DATA_DIRS:
        shutil.copytree(ROOT / d, STAGE / d, ignore=shutil.ignore_patterns(*NOT_SHIPPED))
    shutil.copy2(ROOT / "README.md", STAGE / "README.md")
    size = sum(p.stat().st_size for p in STAGE.rglob("*") if p.is_file())
    log(f"assembled {STAGE.relative_to(ROOT)} ({size / 2**20:.0f} MB)")


def make_zip(version):
    DIST.mkdir(exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", version)
    out = DIST / f"KeyFall-{safe}-windows.zip"
    out.unlink(missing_ok=True)
    files = sorted(p for p in STAGE.rglob("*") if p.is_file())
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in files:
            z.write(p, (Path("KeyFall") / p.relative_to(STAGE)).as_posix())
    log(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size / 2**20:.0f} MB, {len(files)} files)")
    return out


def clean_runtime_files(app_dir):
    for name in RUNTIME_FILES:
        p = app_dir / name
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()


def selftest(app_dir, timeout=300):
    """Run the built EXE headless through the scripted smoke test (game/selftest.py)."""
    clean_runtime_files(app_dir)
    env = dict(os.environ, KEYFALL_SELFTEST="1", KEYFALL_NO_MIDI="1",
               SDL_VIDEODRIVER="dummy", SDL_AUDIODRIVER="dummy")
    log("running self-test on the built EXE (headless, ~1 minute)...")
    started = time.time()
    try:
        code = subprocess.run([str(app_dir / "KeyFall.exe")], cwd=app_dir, env=env,
                              timeout=timeout).returncode
    except subprocess.TimeoutExpired:
        code = "timeout"
    for name in ("keyfall_selftest.txt", "keyfall_crash.txt"):
        p = app_dir / name
        if p.exists() and (code != 0 or name == "keyfall_selftest.txt"):
            print(f"----- {name} -----\n{p.read_text(encoding='utf-8', errors='replace').rstrip()}")
    clean_runtime_files(app_dir)
    if code != 0:
        sys.exit(f"[build] self-test FAILED (exit code {code})")
    log(f"self-test passed in {time.time() - started:.0f}s")


def install():
    target = DIST / "KeyFall"
    target.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(STAGE / "KeyFall.exe", target / "KeyFall.exe")
    except PermissionError:
        sys.exit("[build] dist/KeyFall/KeyFall.exe is in use - close KeyFall and build again.")
    shutil.rmtree(target / "_internal", ignore_errors=True)
    shutil.copytree(STAGE / "_internal", target / "_internal", dirs_exist_ok=True)
    for d in DATA_DIRS:
        shutil.copytree(STAGE / d, target / d, dirs_exist_ok=True)
    shutil.copy2(STAGE / "README.md", target / "README.md")
    log(f"updated {target.relative_to(ROOT)} (your savegame and added files were kept)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", help="version string shown in-game (default: git describe)")
    ap.add_argument("--zip", action="store_true", help="write dist/KeyFall-<version>-windows.zip")
    ap.add_argument("--selftest", action="store_true", help="smoke-test the built EXE headless")
    ap.add_argument("--no-install", action="store_true", help="don't update dist/KeyFall")
    args = ap.parse_args()

    if not PIANO.exists():
        sys.exit("[build] fluidsynth/pianos/piano.sf2 is missing - run setup_audio.py first.")
    version = args.version or default_version()
    log(f"building KeyFall {version} with Python {sys.version.split()[0]}")
    run_pyinstaller(version)
    assemble()
    if args.zip:
        make_zip(version)
    if args.selftest:
        selftest(STAGE)
    if not args.no_install:
        install()


if __name__ == "__main__":
    main()
