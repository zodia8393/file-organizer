"""Tests for CLI entry points via typer testing utilities."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from organizer.cli import app

runner = CliRunner()


def _age_file(path: Path, seconds: int = 3600) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


class TestCLIAnalyze:
    def test_analyze_with_scope(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        result = runner.invoke(app, ["analyze", "--scope", str(tmp_path)])
        assert result.exit_code == 0
        assert "Analysis Report" in result.stdout or "Total files" in result.stdout

    def test_analyze_no_scope_exits(self) -> None:
        # With an empty custom rules file that has no scopes
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("settings:\n  scopes: []\nrules: []\n")
            f.flush()
            result = runner.invoke(app, ["analyze", "--rule-file", f.name])
        os.unlink(f.name)
        assert result.exit_code == 1


class TestCLIPlan:
    def test_plan_dry_run(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.write_text("pdf data")
        _age_file(f)

        result = runner.invoke(app, ["plan", "--scope", str(tmp_path)])
        assert result.exit_code == 0
        assert "DRY RUN" in result.stdout
        # File should still be in original location
        assert f.exists()


class TestCLIApply:
    def test_apply_without_confirm_rejects(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["apply", "--scope", str(tmp_path)])
        assert result.exit_code == 1
        assert "confirm" in result.stdout.lower() or "Confirmation" in result.stdout

    def test_apply_with_confirm_runs(self, tmp_path: Path) -> None:
        f = tmp_path / "report.pdf"
        f.write_text("pdf data")
        _age_file(f)

        result = runner.invoke(app, [
            "apply", "--scope", str(tmp_path), "--confirm"
        ])
        assert result.exit_code == 0


class TestCLIHistory:
    def test_history_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import organizer.logger as logger_mod
        monkeypatch.setattr(logger_mod, "LOG_BASE", tmp_path / "empty_history")
        result = runner.invoke(app, ["history"])
        assert result.exit_code == 0


class TestCLIVersion:
    def test_version(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout
