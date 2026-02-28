"""Disk cache for CFR text and translation outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_CACHE_DIR_ENV = os.getenv("CACHE_DIR", "data/")
# Resolve relative to the project root (parent of pipeline/).
_PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR: Path = (_PROJECT_ROOT / _CACHE_DIR_ENV).resolve()

CATEGORY_TO_DIR: dict[str, Path] = {
    "cfr_cache": DATA_DIR / "cfr_cache",
    "fact_graph_defs": DATA_DIR / "fact_graph_defs",
    "test_cases": DATA_DIR / "test_cases",
}


def _cache_path(category: str, key: str) -> Path:
    """Return the filesystem path for a cache entry."""
    if category not in CATEGORY_TO_DIR:
        raise ValueError(f"Unknown cache category: {category!r}. Choose from {list(CATEGORY_TO_DIR)}")
    # Sanitize key: replace path-unsafe characters.
    safe_key = key.replace("/", "_").replace("\\", "_").replace(" ", "_")
    return CATEGORY_TO_DIR[category] / f"{safe_key}.json"


def read_cache(category: str, key: str, force: bool = False) -> dict | None:  # type: ignore[type-arg]
    """
    Read a cached entry from disk.

    Args:
        category: One of "cfr_cache", "fact_graph_defs", "test_cases".
        key: Unique identifier for this entry (e.g. "title_44_section_206.113").
        force: If True, always return None (bypasses cache for --refresh runs).
    """
    if force:
        return None
    path = _cache_path(category, key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    return None


def write_cache(category: str, key: str, data: dict) -> None:  # type: ignore[type-arg]
    """Write data to a cache entry on disk."""
    path = _cache_path(category, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def clear_category(category: str) -> int:
    """Delete all .json files in a cache category. Returns count of deleted files."""
    if category not in CATEGORY_TO_DIR:
        raise ValueError(f"Unknown cache category: {category!r}")
    cat_dir = CATEGORY_TO_DIR[category]
    count = 0
    if cat_dir.exists():
        for f in cat_dir.glob("*.json"):
            f.unlink()
            count += 1
    return count
