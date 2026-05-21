"""Executor — the 'apply' command that performs actual file operations.

Moves/trashes files according to a Plan, with full logging, hash
verification for cross-volume moves, and mid-failure safety.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .logger import MoveRecord, SessionLog, add_record, create_session, save_session
from .planner import Plan, PlannedAction
from .safety import file_hash, is_same_volume, safe_dest_path


def _move_same_volume(src: Path, dst: Path) -> None:
    """Move file within the same filesystem (atomic rename)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    src.rename(dst)


def _move_cross_volume(src: Path, dst: Path) -> None:
    """Copy to destination, verify hash, then remove original.

    On any failure, both copies are preserved (no data loss).
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    src_hash = file_hash(src)

    shutil.copy2(str(src), str(dst))

    dst_hash = file_hash(dst)
    if src_hash != dst_hash:
        # Hash mismatch — keep both copies, raise error
        raise IOError(
            f"Hash mismatch after cross-volume copy: "
            f"src={src_hash[:12]}... dst={dst_hash[:12]}..."
        )

    # Both copies exist and match — safe to remove original
    src.unlink()


def _trash_file(src: Path) -> Path:
    """Move file to .archive/ in the same directory (no real deletion).

    Falls back to send2trash if available, otherwise uses .archive/.
    """
    try:
        import send2trash

        send2trash.send2trash(str(src))
        return src  # send2trash handles the rest
    except Exception:
        # Fallback: move to .archive/ sibling directory
        archive_dir = src.parent / ".archive"
        archive_dir.mkdir(exist_ok=True)
        dest = safe_dest_path(archive_dir / src.name)
        src.rename(dest)
        return dest


def execute_plan(plan: Plan) -> tuple[SessionLog, Path]:
    """Execute all actions in *plan*, logging every operation.

    Returns (session_log, log_file_path).
    """
    session = create_session()

    for action in plan.actions:
        record = _execute_action(action)
        add_record(session, record)

    log_path = save_session(session)
    return session, log_path


def _execute_action(action: PlannedAction) -> MoveRecord:
    """Execute a single planned action and return the log record."""
    timestamp = datetime.now().isoformat()

    if action.action == "trash":
        return _execute_trash(action, timestamp)
    elif action.action == "move":
        return _execute_move(action, timestamp)
    else:
        return MoveRecord(
            source=str(action.source),
            destination=None,
            action=action.action,
            rule_name=action.rule_name,
            timestamp=timestamp,
            success=False,
            error=f"Unknown action: {action.action}",
        )


def _execute_trash(action: PlannedAction, timestamp: str) -> MoveRecord:
    """Execute a trash action."""
    try:
        archive_dest = _trash_file(action.source)
        return MoveRecord(
            source=str(action.source),
            destination=str(archive_dest),
            action="trash",
            rule_name=action.rule_name,
            timestamp=timestamp,
            size=action.size,
            success=True,
        )
    except Exception as exc:
        return MoveRecord(
            source=str(action.source),
            destination=None,
            action="trash",
            rule_name=action.rule_name,
            timestamp=timestamp,
            size=action.size,
            success=False,
            error=str(exc),
        )


def _execute_move(action: PlannedAction, timestamp: str) -> MoveRecord:
    """Execute a move action (same-volume or cross-volume)."""
    if action.destination is None:
        return MoveRecord(
            source=str(action.source),
            destination=None,
            action="move",
            rule_name=action.rule_name,
            timestamp=timestamp,
            success=False,
            error="No destination specified",
        )

    try:
        # Re-check destination for conflicts at execution time
        dest = safe_dest_path(action.destination)
        src = action.source

        src_hash = ""
        if is_same_volume(src, dest):
            src_hash = file_hash(src)
            _move_same_volume(src, dest)
            move_type = "move"
        else:
            src_hash = file_hash(src)
            _move_cross_volume(src, dest)
            move_type = "cross_volume_move"

        return MoveRecord(
            source=str(action.source),
            destination=str(dest),
            action=move_type,
            rule_name=action.rule_name,
            timestamp=timestamp,
            size=action.size,
            source_hash=src_hash,
            success=True,
        )
    except Exception as exc:
        return MoveRecord(
            source=str(action.source),
            destination=str(action.destination),
            action="move",
            rule_name=action.rule_name,
            timestamp=timestamp,
            size=action.size,
            success=False,
            error=str(exc),
        )
