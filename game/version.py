"""KeyFall version string. Release builds override it with the git tag (see build_release.py)."""

VERSION = "Alpha 1.0"

try:
    from game._build_info import VERSION  # written by build_release.py, not tracked in git
except ImportError:
    pass
