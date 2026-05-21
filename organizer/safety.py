"""Safety checks — all guards that prevent data loss.

Every destructive operation must pass through the checks here
before proceeding.  Functions return (ok: bool, reason: str).
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

# Directories that must never be touched
SYSTEM_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        "venv",
        ".venv",
        "__pycache__",
        ".cache",
        ".Trash",
        ".trash",
        "Library",
        ".local",
        ".config",
        "Dropbox",
        "Google Drive",
        "OneDrive",
        "iCloud",
    }
)


def is_excluded_path(filepath: Path, exclude_dirs: list[str]) -> bool:
    """Return True if any path component matches an exclusion pattern.

    Supports both exact match and prefix match (e.g. "prj_" matches "prj_cctv").
    """
    parts = filepath.parts
    all_excluded = list(SYSTEM_DIRS) + exclude_dirs
    for part in parts:
        for exc in all_excluded:
            if part == exc or part.startswith(exc):
                return True
    return False


def is_within_cooldown(filepath: Path, cooldown_minutes: int) -> bool:
    """Return True if the file was modified within the cooldown window."""
    if cooldown_minutes <= 0:
        return False
    try:
        mtime = filepath.stat().st_mtime
        age_minutes = (time.time() - mtime) / 60.0
        return age_minutes < cooldown_minutes
    except OSError:
        return True  # If we can't stat, treat as unsafe


def is_locked(filepath: Path) -> bool:
    """Return True if the file is not readable or not writable."""
    return not os.access(filepath, os.R_OK | os.W_OK)


def is_symlink(filepath: Path) -> bool:
    """Return True if filepath is a symlink."""
    return filepath.is_symlink()


def is_same_volume(src: Path, dst: Path) -> bool:
    """Return True if src and dst reside on the same filesystem/device."""
    try:
        return os.stat(src).st_dev == os.stat(dst.parent).st_dev
    except OSError:
        # If dst parent doesn't exist yet, walk up until we find one
        parent = dst.parent
        while not parent.exists():
            parent = parent.parent
            if parent == parent.parent:
                return False
        return os.stat(src).st_dev == os.stat(parent).st_dev


def file_hash(filepath: Path, algorithm: str = "sha256") -> str:
    """Compute hex digest of a file for integrity verification."""
    h = hashlib.new(algorithm)
    with open(filepath, "rb") as fh:
        while True:
            chunk = fh.read(1024 * 1024)  # 1 MB chunks
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def safe_dest_path(dest: Path) -> Path:
    """Return a non-conflicting destination path.

    If *dest* already exists, append (2), (3), ... before the extension.
    NEVER overwrites.
    """
    if not dest.exists():
        return dest

    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    counter = 2
    while True:
        candidate = parent / f"{stem} ({counter}){suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def is_excluded_file(filepath: Path, exclude_files: list[str]) -> bool:
    """Return True if the file's name is in the exclusion list."""
    return filepath.name in exclude_files


def preflight_checks(
    filepath: Path,
    cooldown_minutes: int,
    exclude_dirs: list[str],
    exclude_files: list[str] | None = None,
) -> tuple[bool, str]:
    """Run all safety checks on a file before planning a move.

    Returns (ok, reason).  When ok is False, *reason* explains why.
    """
    if not filepath.exists():
        return False, "File does not exist"

    if is_excluded_path(filepath, exclude_dirs):
        return False, "File is in an excluded directory"

    if exclude_files and is_excluded_file(filepath, exclude_files):
        return False, "File is in the exclusion list"

    if is_symlink(filepath):
        return False, "File is a symlink (skipped)"

    if is_locked(filepath):
        return False, "File is locked (no read/write access)"

    if is_within_cooldown(filepath, cooldown_minutes):
        return False, f"File modified within {cooldown_minutes}-minute cooldown"

    return True, "OK"
