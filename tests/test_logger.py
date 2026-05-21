"""Tests for logger module — JSON session logging."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from organizer.logger import (
    MoveRecord,
    SessionLog,
    add_record,
    create_session,
    list_sessions,
    load_session,
    save_session,
)


class TestSessionLog:
    def test_create_session(self) -> None:
        session = create_session()
        assert session.session_id
        assert session.started_at
        assert session.records == []

    def test_add_record_move(self) -> None:
        session = create_session()
        record = MoveRecord(
            source="/tmp/a.pdf",
            destination="/tmp/Docs/a.pdf",
            action="move",
            rule_name="PDF",
            timestamp="2026-01-01T00:00:00",
            size=1024,
            success=True,
        )
        add_record(session, record)
        assert session.total_moves == 1
        assert len(session.records) == 1

    def test_add_record_trash(self) -> None:
        session = create_session()
        record = MoveRecord(
            source="/tmp/junk.txt",
            destination=None,
            action="trash",
            rule_name="Temp",
            timestamp="2026-01-01T00:00:00",
            success=True,
        )
        add_record(session, record)
        assert session.total_trash == 1

    def test_add_record_error(self) -> None:
        session = create_session()
        record = MoveRecord(
            source="/tmp/locked.pdf",
            destination="/tmp/Docs/locked.pdf",
            action="move",
            rule_name="PDF",
            timestamp="2026-01-01T00:00:00",
            success=False,
            error="Permission denied",
        )
        add_record(session, record)
        assert session.total_errors == 1
        assert session.total_moves == 0

    def test_save_and_load_roundtrip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Redirect LOG_BASE to tmp_path
        import organizer.logger as logger_mod
        monkeypatch.setattr(logger_mod, "LOG_BASE", tmp_path / "history")

        session = create_session()
        add_record(session, MoveRecord(
            source="/tmp/a.pdf",
            destination="/tmp/Docs/a.pdf",
            action="move",
            rule_name="PDF",
            timestamp="2026-01-01T00:00:00",
            size=512,
            source_hash="abc123",
            success=True,
        ))

        log_path = save_session(session)
        assert log_path.exists()

        loaded = load_session(log_path)
        assert loaded.session_id == session.session_id
        assert len(loaded.records) == 1
        assert loaded.records[0].source == "/tmp/a.pdf"
        assert loaded.records[0].source_hash == "abc123"
        assert loaded.total_moves == 1

    def test_save_creates_valid_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import organizer.logger as logger_mod
        monkeypatch.setattr(logger_mod, "LOG_BASE", tmp_path / "history")

        session = create_session()
        log_path = save_session(session)

        with open(log_path) as fh:
            data = json.load(fh)
        assert "session_id" in data
        assert "records" in data

    def test_list_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import organizer.logger as logger_mod
        monkeypatch.setattr(logger_mod, "LOG_BASE", tmp_path / "history")

        for i in range(3):
            session = create_session()
            session.session_id = f"2026-01-0{i+1}-120000"
            save_session(session)

        logs = list_sessions(limit=10)
        assert len(logs) == 3
