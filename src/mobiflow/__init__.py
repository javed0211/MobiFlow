"""mobiflow — NL → Maestro mobile automation in the terminal."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mobiflow")
except PackageNotFoundError:  # pragma: no cover - editable / source tree
    __version__ = "0.9.1"

