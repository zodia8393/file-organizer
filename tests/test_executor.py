"""Tests for executor module — actual file operations with logging."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from organizer.executor import execute_plan
from organizer.planner import Plan, PlannedAction
from organizer.safety import file_hash


def _age_file(path: Path, seconds: int = 3600) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


class TestExecutePlan:
    def test_move_single_file(self, tmp_path: Path) -> None:
        src = tmp_path / "report.pdf"
        src.write_text("pdf data")
        _age_file(src)

        dest_dir = tmp_path / "Documents"
        dest = dest_dir / "report.pdf"

        plan = Plan(
            actions=[
                PlannedAction(
                    source=src,
                    destination=dest,
                    rule_name="PDF",
                    action="move",
                    size=src.stat().st_size,
                ),
            ],
            skipped=[],
            scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, log_path = execute_plan(plan)
        assert session.total_moves == 1
        assert session.total_errors == 0
        assert dest.exists()
        assert not src.exists()
        assert log_path.exists()

    def test_move_creates_parent_dirs(self, tmp_path: Path) -> None:
        src = tmp_path / "photo.jpg"
        src.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG header
        _age_file(src)

        dest = tmp_path / "Images" / "2026" / "photo.jpg"
        plan = Plan(
            actions=[
                PlannedAction(
                    source=src, destination=dest,
                    rule_name="Photo", action="move",
                    size=src.stat().st_size,
                ),
            ],
            skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, _ = execute_plan(plan)
        assert dest.exists()
        assert session.total_moves == 1

    def test_trash_moves_to_archive(self, tmp_path: Path) -> None:
        src = tmp_path / "temp_junk.txt"
        src.write_text("junk")
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

        session, _ = execute_plan(plan)
        assert session.total_trash == 1
        assert not src.exists()
        # File should be in .archive/ or system trash
        archive = tmp_path / ".archive"
        if archive.exists():
            assert len(list(archive.iterdir())) >= 1

    def test_conflict_resolution_no_overwrite(self, tmp_path: Path) -> None:
        src = tmp_path / "doc.pdf"
        src.write_text("new content")
        _age_file(src)

        dest_dir = tmp_path / "Docs"
        dest_dir.mkdir()
        existing = dest_dir / "doc.pdf"
        existing.write_text("old content")

        plan = Plan(
            actions=[
                PlannedAction(
                    source=src,
                    destination=dest_dir / "doc.pdf",
                    rule_name="PDF", action="move",
                    size=src.stat().st_size,
                ),
            ],
            skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, _ = execute_plan(plan)
        assert session.total_moves == 1
        # Original should still be intact
        assert existing.read_text() == "old content"
        # New file should be renamed
        renamed = dest_dir / "doc (2).pdf"
        assert renamed.exists()
        assert renamed.read_text() == "new content"

    def test_nonexistent_source_logged_as_error(self, tmp_path: Path) -> None:
        plan = Plan(
            actions=[
                PlannedAction(
                    source=tmp_path / "ghost.pdf",
                    destination=tmp_path / "Docs" / "ghost.pdf",
                    rule_name="PDF", action="move", size=0,
                ),
            ],
            skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, _ = execute_plan(plan)
        assert session.total_errors == 1

    def test_hash_recorded_in_log(self, tmp_path: Path) -> None:
        src = tmp_path / "data.bin"
        content = b"important data"
        src.write_bytes(content)
        _age_file(src)
        expected_hash = file_hash(src)

        dest = tmp_path / "Archive" / "data.bin"
        plan = Plan(
            actions=[
                PlannedAction(
                    source=src, destination=dest,
                    rule_name="Data", action="move",
                    size=len(content),
                ),
            ],
            skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )

        session, _ = execute_plan(plan)
        assert session.records[0].source_hash == expected_hash

    def test_empty_plan_no_errors(self, tmp_path: Path) -> None:
        plan = Plan(
            actions=[], skipped=[], scope_dirs=[tmp_path],
            created_at="2026-01-01T00:00:00",
        )
        session, log_path = execute_plan(plan)
        assert session.total_moves == 0
        assert session.total_errors == 0
