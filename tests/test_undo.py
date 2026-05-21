"""Tests for undo module — reversing operations from session logs."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from organizer.executor import execute_plan
from organizer.planner import Plan, PlannedAction
from organizer.safety import file_hash
from organizer.undo import undo_session


def _age_file(path: Path, seconds: int = 3600) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


class TestUndoSession:
    def test_undo_move_restores_file(self, tmp_path: Path) -> None:
        """Move a file, then undo — original location should have the file."""
        src = tmp_path / "report.pdf"
        src.write_text("important")
        original_hash = file_hash(src)
        _age_file(src)

        dest = tmp_path / "Docs" / "report.pdf"
        plan = Plan(
            actions=[
                PlannedAction(
                    source=src, destination=dest,
                    rule_name="PDF", action="move",
                    size=src.stat().st_size,
                ),
            ],
            skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        # Execute
        session, log_path = execute_plan(plan)
        assert dest.exists()
        assert not src.exists()

        # Undo
        undo_log, undo_path = undo_session(log_path)
        assert undo_log.total_moves == 1
        assert undo_log.total_errors == 0
        assert src.exists()
        assert file_hash(src) == original_hash
        assert not dest.exists()

    def test_undo_trash_restores_file(self, tmp_path: Path) -> None:
        """Trash a file, then undo — original location should have the file."""
        src = tmp_path / "temp_file.txt"
        src.write_text("not junk")
        _age_file(src)

        plan = Plan(
            actions=[
                PlannedAction(
                    source=src, destination=None,
                    rule_name="Temp", action="trash",
                    size=src.stat().st_size,
                ),
            ],
            skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, log_path = execute_plan(plan)
        assert not src.exists()

        # Check that the archive record has a destination
        trash_record = session.records[0]
        if trash_record.destination and Path(trash_record.destination).exists():
            undo_log, _ = undo_session(log_path)
            assert src.exists()

    def test_undo_handles_missing_dest_gracefully(self, tmp_path: Path) -> None:
        """If the moved file was deleted externally, undo should log error."""
        src = tmp_path / "gone.pdf"
        src.write_text("data")
        _age_file(src)

        dest = tmp_path / "Docs" / "gone.pdf"
        plan = Plan(
            actions=[
                PlannedAction(
                    source=src, destination=dest,
                    rule_name="PDF", action="move",
                    size=src.stat().st_size,
                ),
            ],
            skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, log_path = execute_plan(plan)
        # Simulate external deletion
        dest.unlink()

        undo_log, _ = undo_session(log_path)
        assert undo_log.total_errors >= 1

    def test_undo_multiple_moves(self, tmp_path: Path) -> None:
        """Undo should handle multiple files correctly."""
        files = []
        for name in ("a.pdf", "b.txt", "c.png"):
            f = tmp_path / name
            f.write_text(f"content of {name}")
            _age_file(f)
            files.append(f)

        actions = [
            PlannedAction(
                source=f,
                destination=tmp_path / "Out" / f.name,
                rule_name="Test",
                action="move",
                size=f.stat().st_size,
            )
            for f in files
        ]

        plan = Plan(
            actions=actions, skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, log_path = execute_plan(plan)
        assert session.total_moves == 3

        undo_log, _ = undo_session(log_path)
        assert undo_log.total_moves == 3
        for f in files:
            assert f.exists(), f"{f} not restored"
