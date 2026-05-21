"""Tests for analyzer module — read-only directory analysis."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from organizer.analyzer import AnalysisResult, analyze_scope, format_report
from organizer.rules import RuleSet, Settings


def _make_ruleset(**overrides) -> RuleSet:
    defaults = dict(
        scopes=[],
        max_depth=3,
        cooldown_minutes=5,
        batch_limit=5000,
        exclude_dirs=[],
        log_retention_days=30,
    )
    defaults.update(overrides)
    return RuleSet(settings=Settings(**defaults), rules=[])


class TestAnalyzeScope:
    def test_empty_directory(self, tmp_path: Path) -> None:
        rs = _make_ruleset()
        result = analyze_scope(tmp_path, rs)
        assert result.total_files == 0
        assert result.total_size == 0

    def test_counts_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.pdf").write_bytes(b"pdf content")
        (tmp_path / "c.txt").write_text("world")
        rs = _make_ruleset()
        result = analyze_scope(tmp_path, rs)
        assert result.total_files == 3

    def test_extension_distribution(self, tmp_path: Path) -> None:
        for i in range(3):
            (tmp_path / f"file{i}.txt").write_text("x")
        (tmp_path / "img.png").write_bytes(b"\x89PNG")
        rs = _make_ruleset()
        result = analyze_scope(tmp_path, rs)
        assert result.extension_counts.get(".txt") == 3
        assert result.extension_counts.get(".png") == 1

    def test_excludes_git_dir(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git stuff")
        (tmp_path / "real.txt").write_text("real")
        rs = _make_ruleset()
        result = analyze_scope(tmp_path, rs)
        assert result.total_files == 1

    def test_respects_max_depth(self, tmp_path: Path) -> None:
        # depth 0: top-level only
        sub = tmp_path / "deep" / "nested"
        sub.mkdir(parents=True)
        (tmp_path / "top.txt").write_text("top")
        (sub / "deep.txt").write_text("deep")
        rs = _make_ruleset(max_depth=1)
        result = analyze_scope(tmp_path, rs)
        # Only the top-level file + files in 'deep/' (depth 1), not 'deep/nested/'
        assert result.total_files == 1

    def test_detects_old_files(self, tmp_path: Path) -> None:
        f = tmp_path / "ancient.txt"
        f.write_text("old")
        old_time = time.time() - (400 * 86400)  # 400 days ago
        os.utime(f, (old_time, old_time))
        rs = _make_ruleset(cooldown_minutes=0)
        result = analyze_scope(tmp_path, rs)
        assert len(result.old_files) == 1

    def test_detects_temp_candidates(self, tmp_path: Path) -> None:
        (tmp_path / "temp_notes.txt").write_text("temp")
        (tmp_path / "real.pdf").write_bytes(b"pdf")
        rs = _make_ruleset()
        result = analyze_scope(tmp_path, rs)
        assert len(result.temp_candidates) == 1

    def test_nonexistent_scope(self, tmp_path: Path) -> None:
        rs = _make_ruleset()
        result = analyze_scope(tmp_path / "nonexistent", rs)
        assert len(result.errors) > 0

    def test_total_size_correct(self, tmp_path: Path) -> None:
        data = b"x" * 1024
        (tmp_path / "file.bin").write_bytes(data)
        rs = _make_ruleset()
        result = analyze_scope(tmp_path, rs)
        assert result.total_size == 1024


class TestFormatReport:
    def test_renders_markdown(self, tmp_path: Path) -> None:
        result = AnalysisResult(
            scope=tmp_path,
            total_files=5,
            total_size=1024,
            extension_counts={".txt": 3, ".pdf": 2},
            extension_sizes={".txt": 300, ".pdf": 724},
        )
        report = format_report([result])
        assert "# Directory Analysis Report" in report
        assert ".txt" in report
        assert ".pdf" in report

    def test_empty_results(self) -> None:
        report = format_report([])
        assert "# Directory Analysis Report" in report
