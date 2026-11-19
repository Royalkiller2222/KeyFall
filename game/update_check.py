"""
KeyFall - update check.

Asks GitHub which KeyFall release is the newest and compares it with this copy's version.
That is one HTTPS request to GitHub's public releases API: nothing about the player or their
computer is sent (no account, no ID, a generic User-Agent), and nothing is downloaded or
installed. When there is a newer version, the game offers to open its release page, where
the zip can be downloaded.

Settings -> UPDATES has a CHECK FOR UPDATES button. While the game is open it also checks by
itself once a week. The time of the last check and the newest version found are kept in the
save (save_data["update_check"]), so the main menu keeps offering an update between checks.
The request runs on a background thread, so the game never waits on the network. Automated
runs (KEYFALL_SELFTEST=1) never go online and never open a browser.
"""

import http.client
import json
import os
import re
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

try:                                    # Mozilla's root certificates: see ssl_context()
    import certifi
except ImportError:                     # (a source install from before it was required)
    certifi = None

from game.version import VERSION

REPO = "Royalkiller2222/KeyFall"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases"
RELEASES_SHORT = f"github.com/{REPO}/releases"  # (as written for the player to type in)
USER_AGENT = "KeyFall-update-check"     # GitHub's API requires one; generic on purpose
TIMEOUT = 10                            # s for the request
WEEK = 7 * 24 * 3600                    # s between automatic checks
RETRY_AFTER = 3600                      # s after a failed automatic check before the next try
FIRST_DELAY = 8                         # s after the game starts before an automatic check
OPENED_SHOW = 6                         # s the "opened in your browser" note stays up
FAILED_SHOW = 30                        # s "couldn't open a browser" (and the link) stays up
SELFTEST = os.environ.get("KEYFALL_SELFTEST") == "1"

_VERSION_RE = re.compile(r"v?(\d+)\.(\d+)(?:\.(\d+))?((?:-[0-9A-Za-z.]+)*)", re.ASCII)
_DESCRIBE_RE = re.compile(r"-(\d+)-g[0-9a-f]+", re.ASCII)


class UpdateError(Exception):
    """A check that failed, with a message for the player."""


# ── Versions ──────────────────────────────────────────────────────
def version_key(v):
    """A sortable key for a version like 'v1.2.0', or None if v isn't one ('Alpha 1.0').

    Builds made between releases are named by git describe: v1.2.0-3-g0ce5fae is 3 commits
    after v1.2.0, so newer than it. A pre-release such as v1.3.0-beta.1 comes before v1.3.0.
    A -dirty ending (built with uncommitted changes) doesn't change the order."""
    m = _VERSION_RE.fullmatch(v.strip()) if isinstance(v, str) else None
    if not m:
        return None
    key = (int(m[1]), int(m[2]), int(m[3] or 0))
    rest = m[4]
    if rest.endswith("-dirty"):
        rest = rest[:-len("-dirty")]
    if not rest:
        return key + (1, 0)                     # the release itself
    d = _DESCRIBE_RE.fullmatch(rest)
    if d:
        return key + (2, int(d[1]))             # n commits after it
    return key + (0, 0)                         # a pre-release of it


def is_newer(a, b):
    """True if version a is newer than version b (False if either isn't a version)."""
    ka, kb = version_key(a), version_key(b)
    return ka is not None and kb is not None and ka > kb


def _git_version():
    """A copy run from source has no build version: ask git, as build_release.py does."""
    if getattr(sys, "frozen", False):
        return None
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(root, ".git")):
        return None
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=root,
                             capture_output=True, text=True, timeout=3,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError, UnicodeError):
        return None
    out = (out or "").strip()
    return out if version_key(out) else None


def current_version():
    """This copy's version: the release build's tag, or for a git checkout what git says."""
    if version_key(VERSION) is not None:
        return VERSION
    return _git_version() or VERSION


def ago(seconds):
    """'just now', '5 minutes ago', '3 hours ago', 'yesterday', '4 days ago'."""
    s = max(0, int(seconds))
    if s < 60:
        return "just now"
    if s < 3600:
        n, unit = s // 60, "minute"
    elif s < 86400:
        n, unit = s // 3600, "hour"
    else:
        n = s // 86400
        if n == 1:
            return "yesterday"
        unit = "day"
    return f"{n} {unit}{'s' if n != 1 else ''} ago"


# ── The request ───────────────────────────────────────────────────
def ssl_context():
    """Checks GitHub's certificate against Windows' root certificates plus Mozilla's list
    (certifi). Windows only keeps the roots it has needed so far and fetches a missing one
    when a browser asks for it; Python can't. So on a PC that hasn't met GitHub's root
    (Sectigo) yet, Windows' alone fail with 'unable to get issuer certificate'."""
    ctx = ssl.create_default_context()
    if certifi is not None:
        try:
            ctx.load_verify_locations(certifi.where())
        except (OSError, ValueError, ssl.SSLError):
            pass
    return ctx


def fetch_latest(timeout=TIMEOUT):
    """The tag of the newest KeyFall release on GitHub, e.g. 'v1.3.0'. Raises UpdateError."""
    req = urllib.request.Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                                   "User-Agent": USER_AGENT})
    try:
        ctx = ssl_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read(1 << 20).decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("No release has been published yet") from None
        if e.code in (403, 429):
            raise UpdateError("GitHub is busy. Try again in an hour.") from None
        raise UpdateError(f"GitHub answered with error {e.code}") from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, ssl.SSLCertVerificationError):
            raise UpdateError("Couldn't verify GitHub's certificate") from None
        if isinstance(e.reason, TimeoutError):
            raise UpdateError("GitHub didn't answer. Try again later.") from None
        raise UpdateError("Couldn't reach GitHub. Are you online?") from None
    except TimeoutError:
        raise UpdateError("GitHub didn't answer. Try again later.") from None
    except (OSError, http.client.HTTPException):
        raise UpdateError("Couldn't reach GitHub. Are you online?") from None
    except ValueError:
        raise UpdateError("Unexpected answer from GitHub") from None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    if not isinstance(tag, str) or version_key(tag) is None:
        raise UpdateError("Unexpected answer from GitHub")
    return tag.strip()


# ── The checker ───────────────────────────────────────────────────
class UpdateChecker:
    """Knows the newest release and asks GitHub for it: on request (Settings) and by itself
    once a week while the game runs. The app calls tick() every frame; a finished check is
    applied there, on the main thread (the background thread only does the request)."""

    def __init__(self, save_data, on_change=None, auto=None):
        self.save_data = save_data
        self.on_change = on_change          # called after save_data["update_check"] changed
        self.auto = (not SELFTEST) if auto is None else auto
        self.current = current_version()
        saved = save_data.get("update_check")
        saved = saved if isinstance(saved, dict) else {}
        tag = saved.get("latest")
        self.latest = tag if isinstance(tag, str) and version_key(tag) else None
        last = saved.get("last")
        self.last_check = (float(last) if isinstance(last, (int, float))
                           and not isinstance(last, bool) else None)
        self.checking = False
        self.error = ""                     # why the last check started from Settings failed
        self.opened_at = None               # when the release page was opened (time.time())
        self.opened_ok = True               # ...and whether a browser took it
        self.fetch = fetch_latest           # (the self-test swaps in a canned answer)
        self._lock = threading.Lock()
        self._result = None                 # handed over by the thread: (kind, value)
        self._manual = False
        self._next_auto = max(time.time() + FIRST_DELAY, self._due())

    # ── state ────────────────────────────────────────────────────
    @property
    def available(self):
        """The newer release to offer (e.g. 'v1.4.0'), or None."""
        return self.latest if is_newer(self.latest, self.current) else None

    @property
    def known(self):
        """False when this copy's version can't be compared (e.g. an unnumbered build)."""
        return version_key(self.current) is not None

    def _due(self):
        """When the weekly check is due (a time.time())."""
        last = self.last_check
        if last is None or last > time.time() + 3600:   # never, or the clock was turned back
            return 0.0
        return last + WEEK

    def status(self):
        """(kind, text) for Settings; kind is busy / new / ok / warn / info."""
        if self.checking:
            return "busy", "Checking GitHub for a new version…"
        new = self.available
        opened = self.opened_text()
        if opened:
            return ("new" if self.opened_ok else "warn"), opened
        if self.error:
            return "warn", self.error
        if new:
            return "new", f"Update available: {new}"
        if self.latest is None:
            return "info", "Not checked yet"
        if not self.known:
            return "info", f"The newest release is {self.latest}"
        return "ok", "Up to date: this is the newest version"

    def detail_text(self):
        """The line under the status: where to get the update when no browser could be
        opened, otherwise when it last checked and that it checks weekly."""
        if self.open_failed:
            return f"Get it from {RELEASES_SHORT}"
        weekly = "KeyFall checks once a week while it's open."
        if self.last_check is None:
            return weekly
        return f"Last checked {ago(time.time() - self.last_check)}. {weekly}"

    # ── checking ─────────────────────────────────────────────────
    def check(self, manual=True):
        """Ask GitHub now, in the background. False if a check is already running."""
        if self.checking:
            return False
        self.checking, self._manual = True, manual
        if manual:
            self.error = ""
        with self._lock:
            self._result = None
        try:
            threading.Thread(target=self._run, args=(self.fetch,), name="update-check",
                             daemon=True).start()
        except RuntimeError:                # (no thread to be had: treat it as a failed check)
            self._finish("error", "Couldn't check for updates")
            return False
        return True

    def _run(self, fetch):
        try:
            res = ("ok", fetch())
        except UpdateError as e:
            res = ("error", str(e))
        except Exception:                   # a failed check must never take the game down
            res = ("error", "Couldn't check for updates")
        with self._lock:
            self._result = res

    def tick(self, auto_ok=True):
        """Every frame: applies a finished check, and starts the weekly one when it's due
        (only where auto_ok, i.e. not during a song)."""
        if self.checking:
            with self._lock:
                res, self._result = self._result, None
            if res is not None:
                self._finish(*res)
        elif self.auto and auto_ok and time.time() >= self._next_auto:
            self.check(manual=False)

    def _finish(self, kind, value):
        self.checking = False
        now = time.time()
        if kind == "ok":
            self.latest, self.last_check, self.error = value, now, ""
            self.save_data["update_check"] = {"last": int(now), "latest": value}
            self._next_auto = now + WEEK
            if self.on_change:
                self.on_change()
        else:
            if self._manual:                # automatic checks fail quietly
                self.error = value
            self._next_auto = max(self._due(), now + RETRY_AFTER)

    # ── the download page ────────────────────────────────────────
    def page_url(self):
        """The newest release's page (its zip is listed there)."""
        if self.latest:                     # (version_key only lets [v0-9A-Za-z.-] through)
            return f"{RELEASES_URL}/tag/{self.latest}"
        return f"{RELEASES_URL}/latest"

    def open_page(self):
        """Open the newest release's page in the browser. False if that failed."""
        ok = True
        if not SELFTEST:                    # automated runs never open a browser
            try:
                ok = bool(webbrowser.open(self.page_url(), new=2))
            except Exception:
                ok = False
        self.opened_at, self.opened_ok = time.time(), ok
        return ok

    def opened_text(self):
        """What happened when the page was opened just now, or "" (shown for a few seconds;
        a failure stays up longer, next to RELEASES_SHORT, so the link can be typed in)."""
        if self.opened_at is None:
            return ""
        if time.time() - self.opened_at >= (OPENED_SHOW if self.opened_ok else FAILED_SHOW):
            return ""
        return ("Opened the download page in your browser" if self.opened_ok
                else "Couldn't open a browser")

    @property
    def open_failed(self):
        """True while the 'couldn't open a browser' note is up."""
        return not self.opened_ok and bool(self.opened_text())
