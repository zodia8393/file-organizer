"""Tests for safety module — all guards that prevent data loss."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from organizer.safety import (
    file_hash,
    is_excluded_path,
    is_locked,
    is_same_volume,
    is_symlink,
    is_within_cooldown,
    preflight_checks,
    safe_dest_path,
)


class TestIsExcludedPath:
    def test_git_dir_excluded(self) -> None:
        p = Path("/home/user/.git/config")
        assert is_excluded_path(p, []) is True

    def test_node_modules_excluded(self) -> None:
        p = Path("/project/node_modules/pkg/index.js")
        assert is_excluded_path(p, []) is True

    def test_normal_path_not_excluded(self) -> None:
        p = Path("/home/user/Downloads/file.pdf")
        assert is_excluded_path(p, []) is False

    def test_custom_exclude_dir(self) -> None:
        p = Path("/project/build/output.js")
        assert is_excluded_path(p, ["build"]) is True

    def test_pycache_excluded(self) -> None:
        p = Path("/project/__pycache__/mod.cpython.pyc")
        assert is_excluded_path(p, []) is True


class TestIsWithinCooldown:
    def test_fresh_file_in_cooldown(self, tmp_path: Path) -> None:
        f = tmp_path / "new.txt"
        f.write_text("fresh")
        assert is_within_cooldown(f, cooldown_minutes=5) is True

    def test_old_file_not_in_cooldown(self, tmp_path: Path) -> None:
        f = tmp_path / "old.txt"
        f.write_text("old")
        old_time = time.time() - 3600  # 1 hour ago
        os.utime(f, (old_time, old_time))
        assert is_within_cooldown(f, cooldown_minutes=5) is False

    def test_zero_cooldown_never_triggers(self, tmp_path: Path) -> None:
        f = tmp_path / "new.txt"
        f.write_text("fresh")
        assert is_within_cooldown(f, cooldown_minutes=0) is False

    def test_nonexistent_file_treated_unsafe(self, tmp_path: Path) -> None:
        f = tmp_path / "ghost.txt"
        assert is_within_cooldown(f, cooldown_minutes=5) is True


class TestIsLocked:
    def test_normal_file_not_locked(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.txt"
        f.write_text("fine")
        assert is_locked(f) is False

    def test_readonly_file_is_locked(self, tmp_path: Path) -> None:
        f = tmp_path / "ro.txt"
        f.write_text("locked")
        f.chmod(0o444)
        assert is_locked(f) is True
        # Restore permission for cleanup
        f.chmod(0o644)


class TestIsSymlink:
    def test_regular_file_not_symlink(self, tmp_path: Path) -> None:
        f = tmp_path / "real.txt"
        f.write_text("real")
        assert is_symlink(f) is False

    def test_symlink_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "target.txt"
        f.write_text("target")
        link = tmp_path / "link.txt"
        link.symlink_to(f)
        assert is_symlink(link) is True


class TestIsSameVolume:
    def test_same_dir_same_volume(self, tmp_path: Path) -> None:
        f = tmp_path / "a.txt"
        f.write_text("a")
        dest = tmp_path / "sub" / "b.txt"
        (tmp_path / "sub").mkdir()
        assert is_same_volume(f, dest) is True


class TestFileHash:
    def test_consistent_hash(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"hello world")
        h1 = file_hash(f)
        h2 = file_hash(f)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.txt"
        f1.write_text("alpha")
        f2 = tmp_path / "b.txt"
        f2.write_text("beta")
        assert file_hash(f1) != file_hash(f2)


class TestSafeDestPath:
    def test_no_conflict(self, tmp_path: Path) -> None:
        dest = tmp_path / "file.txt"
        assert safe_dest_path(dest) == dest

    def test_conflict_appends_counter(self, tmp_path: Path) -> None:
        dest = tmp_path / "file.txt"
        dest.write_text("existing")
        result = safe_dest_path(dest)
        assert result == tmp_path / "file (2).txt"

    def test_multiple_conflicts(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("1")
        (tmp_path / "file (2).txt").write_text("2")
        result = safe_dest_path(tmp_path / "file.txt")
        assert result == tmp_path / "file (3).txt"

    def test_preserves_extension(self, tmp_path: Path) -> None:
        (tmp_path / "doc.pdf").write_text("1")
        result = safe_dest_path(tmp_path / "doc.pdf")
        assert result.suffix == ".pdf"
        assert "(2)" in result.name


class TestPreflightChecks:
    def test_normal_file_passes(self, tmp_path: Path) -> None:
        f = tmp_path / "ok.txt"
        f.write_text("ok")
        old = time.time() - 3600
        os.utime(f, (old, old))
        ok, reason = preflight_checks(f, cooldown_minutes=5, exclude_dirs=[])
        assert ok is True

    def test_nonexistent_fails(self, tmp_path: Path) -> None:
        f = tmp_path / "ghost.txt"
        ok, reason = preflight_checks(f, cooldown_minutes=5, exclude_dirs=[])
        assert ok is False
        assert "exist" in reason.lower()

    def test_excluded_dir_fails(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        f = git_dir / "config"
        f.write_text("x")
        ok, reason = preflight_checks(f, cooldown_minutes=0, exclude_dirs=[])
        assert ok is False
        assert "excluded" in reason.lower()

    def test_cooldown_fails(self, tmp_path: Path) -> None:
        f = tmp_path / "fresh.txt"
        f.write_text("new")
        ok, reason = preflight_checks(f, cooldown_minutes=60, exclude_dirs=[])
        assert ok is False
        assert "cooldown" in reason.lower()

    def test_symlink_fails(self, tmp_path: Path) -> None:
        target = tmp_path / "target.txt"
        target.write_text("real")
        link = tmp_path / "link.txt"
        link.symlink_to(target)
        old = time.time() - 3600
        os.utime(target, (old, old))
        ok, reason = preflight_checks(link, cooldown_minutes=0, exclude_dirs=[])
        assert ok is False
        assert "symlink" in reason.lower()
