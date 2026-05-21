"""JSON operation logging for audit trail and undo support.

Logs are stored at ~/.organize/history/YYYY-MM-DD-HHMM.json
with 30-day retention (configurable).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


LOG_BASE = Path.home() / ".organize" / "history"


@dataclass
class MoveRecord:
    """A single logged file operation."""

    source: str
    destination: str | None
    action: str  # "move", "trash", "cross_volume_move"
    rule_name: str
    timestamp: str
    size: int = 0
    source_hash: str = ""
    success: bool = True
    error: str = ""


@dataclass
class SessionLog:
    """All operations for one execution session."""

    session_id: str
    started_at: str
    completed_at: str = ""
    records: list[MoveRecord] = field(default_factory=list)
    total_moves: int = 0
    total_trash: int = 0
    total_errors: int = 0


def _ensure_log_dir() -> Path:
    LOG_BASE.mkdir(parents=True, exist_ok=True)
    return LOG_BASE


def create_session() -> SessionLog:
    """Create a new session log with a unique ID."""
    now = datetime.now()
    session_id = now.strftime("%Y-%m-%d-%H%M%S")
    return SessionLog(
        session_id=session_id,
        started_at=now.isoformat(),
    )


def add_record(session: SessionLog, record: MoveRecord) -> None:
    """Append a record to the session."""
    session.records.append(record)
    if record.success:
        if record.action in ("move", "cross_volume_move", "undo_move"):
            session.total_moves += 1
        elif record.action in ("trash", "undo_trash"):
            session.total_trash += 1
    else:
        session.total_errors += 1


def save_session(session: SessionLog) -> Path:
    """Write the session log to disk as JSON. Returns the log file path."""
    log_dir = _ensure_log_dir()
    session.completed_at = datetime.now().isoformat()

    filename = f"{session.session_id}.json"
    filepath = log_dir / filename

    data = asdict(session)
    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)

    return filepath


def load_session(filepath: Path) -> SessionLog:
    """Load a session log from a JSON file."""
    with open(filepath, encoding="utf-8") as fh:
        data = json.load(fh)

    records = [MoveRecord(**r) for r in data.get("records", [])]
    return SessionLog(
        session_id=data["session_id"],
        started_at=data["started_at"],
        completed_at=data.get("completed_at", ""),
        records=records,
        total_moves=data.get("total_moves", 0),
        total_trash=data.get("total_trash", 0),
        total_errors=data.get("total_errors", 0),
    )


def list_sessions(limit: int = 20) -> list[Path]:
    """Return recent session log paths, newest first."""
    log_dir = _ensure_log_dir()
    logs = sorted(log_dir.glob("*.json"), reverse=True)
    return logs[:limit]


def cleanup_old_logs(retention_days: int = 30) -> int:
    """Delete logs older than *retention_days*. Returns count deleted."""
    log_dir = _ensure_log_dir()
    cutoff = time.time() - (retention_days * 86400)
    deleted = 0
    for logfile in log_dir.glob("*.json"):
        try:
            if logfile.stat().st_mtime < cutoff:
                logfile.unlink()
                deleted += 1
        except OSError:
            pass
    return deleted
