"""Bundled starter cases, frozen flows, scripts, and data files.

``mobiflow init`` copies this tree into a new project. In a git checkout the
repo-root ``cases/`` / ``flows/`` / ``data/`` trees win when they have at least
as many case files (so contributors are not editing a stale copy). After pip
or npm install, only this package directory exists.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

_TREE_SUFFIXES: dict[str, frozenset[str]] = {
    "cases": frozenset({".txt", ".md"}),
    "flows": frozenset({".yaml", ".yml", ".js"}),
    "data": frozenset({".json", ".example", ".md"}),
}


def _case_count(root: Path) -> int:
    cases = root / "cases"
    if not cases.is_dir():
        return 0
    return len(list(cases.glob("*.txt")))


def sample_library_root() -> Path:
    """Directory that contains ``cases/``, ``flows/``, and ``data/`` samples."""
    pkg_samples = Path(__file__).resolve().parent
    repo = Path(__file__).resolve().parents[3]
    pkg_n = _case_count(pkg_samples)
    repo_n = _case_count(repo)
    if repo_n > 0 and repo_n >= pkg_n:
        return repo
    if pkg_n > 0:
        return pkg_samples
    raise FileNotFoundError(
        "Bundled sample cases not found. Reinstall mobiflow or copy cases/ "
        "from the MobiFlow repository."
    )


def bundled_case_names() -> list[str]:
    """Sorted ``*.txt`` names from the sample library."""
    root = sample_library_root() / "cases"
    return sorted(p.name for p in root.glob("*.txt") if p.is_file())


def _iter_tree_files(src_dir: Path) -> Iterable[Path]:
    if not src_dir.is_dir():
        return
    for path in sorted(src_dir.rglob("*")):
        if path.is_file() and not path.name.startswith("."):
            yield path


def copy_sample_library(
    repo: Path,
    *,
    cases_dir: str = "cases",
    flow_dir: str = "flows",
    data_dir: str = "data",
) -> list[Path]:
    """Copy bundled samples into ``repo`` without overwriting existing files."""
    src_root = sample_library_root()
    dest_map = {
        "cases": repo / cases_dir,
        "flows": repo / flow_dir,
        "data": repo / data_dir,
    }
    written: list[Path] = []
    for tree, dest_root in dest_map.items():
        src_dir = src_root / tree
        allowed = _TREE_SUFFIXES[tree]
        dest_root.mkdir(parents=True, exist_ok=True)
        for src in _iter_tree_files(src_dir):
            if src.suffix.lower() not in allowed and not src.name.endswith(".json.example"):
                continue
            rel = src.relative_to(src_dir)
            dest = dest_root / rel
            if dest.exists():
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(src.read_bytes())
            written.append(dest)
    return written
