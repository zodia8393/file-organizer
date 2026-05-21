"""Undo support — reverse operations from a session log.

Reads a JSON log file and moves every file back to its original
location.  Only successful move/cross_volume_move records are undoable.
Trash actions are undone by moving from .archive/ back to original path.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .logger import (
    MoveRecord,
    SessionLog,
    add_record,
    create_session,
    load_session,
    save_session,
)
from .safety import file_hash, is_same_volume, safe_dest_path


def undo_session(log_path: Path) -> tuple[SessionLog, Path]:
    """Reverse all operations in the given session log.

    Returns a new undo session log and its file path.
    """
    original = load_session(log_path)
    undo_log = create_session()
    undo_log.session_id = f"undo-{original.session_id}"

    # Process in reverse order for safety
    for record in reversed(original.records):
        undo_record = _undo_record(record)
        add_record(undo_log, undo_record)

    log_path = save_session(undo_log)
    return undo_log, log_path


def _undo_record(record: MoveRecord) -> MoveRecord:
    """Reverse a single logged operation."""
    timestamp = datetime.now().isoformat()

    if not record.success:
        # Failed records don't need undoing
        return MoveRecord(
            source=record.source,
            destination=record.destination,
            action="skip",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=True,
            error="Original operation failed, nothing to undo",
        )

    if record.action in ("move", "cross_volume_move"):
        return _undo_move(record, timestamp)
    elif record.action == "trash":
        return _undo_trash(record, timestamp)
    else:
        return MoveRecord(
            source=record.source,
            destination=record.destination,
            action="skip",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=True,
            error=f"Cannot undo action type: {record.action}",
        )


def _undo_move(record: MoveRecord, timestamp: str) -> MoveRecord:
    """Reverse a move: destination -> source."""
    if not record.destination:
        return MoveRecord(
            source=record.source,
            destination=None,
            action="undo_move",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=False,
            error="No destination in log record",
        )

    dst = Path(record.destination)
    src = Path(record.source)

    if not dst.exists():
        return MoveRecord(
            source=str(dst),
            destination=str(src),
            action="undo_move",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=False,
            error=f"File not found at destination: {dst}",
        )

    try:
        # Verify hash if available
        if record.source_hash:
            current_hash = file_hash(dst)
            if current_hash != record.source_hash:
                return MoveRecord(
                    source=str(dst),
                    destination=str(src),
                    action="undo_move",
                    rule_name=f"undo({record.rule_name})",
                    timestamp=timestamp,
                    success=False,
                    error="Hash mismatch — file may have been modified since move",
                )

        # Ensure original parent exists
        src.parent.mkdir(parents=True, exist_ok=True)
        restore_dest = safe_dest_path(src)

        if is_same_volume(dst, restore_dest):
            dst.rename(restore_dest)
        else:
            import shutil

            shutil.copy2(str(dst), str(restore_dest))
            # Verify copy
            if record.source_hash:
                if file_hash(restore_dest) != record.source_hash:
                    raise IOError("Hash mismatch after undo copy")
            dst.unlink()

        return MoveRecord(
            source=str(dst),
            destination=str(restore_dest),
            action="undo_move",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            size=record.size,
            source_hash=record.source_hash,
            success=True,
        )
    except Exception as exc:
        return MoveRecord(
            source=str(dst),
            destination=str(src),
            action="undo_move",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=False,
            error=str(exc),
        )


def _undo_trash(record: MoveRecord, timestamp: str) -> MoveRecord:
    """Reverse a trash: .archive/file -> original location."""
    if not record.destination:
        return MoveRecord(
            source=record.source,
            destination=None,
            action="undo_trash",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=False,
            error="No archive path in log record (send2trash used — cannot undo)",
        )

    archive_path = Path(record.destination)
    original_path = Path(record.source)

    if not archive_path.exists():
        return MoveRecord(
            source=str(archive_path),
            destination=str(original_path),
            action="undo_trash",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=False,
            error=f"Archived file not found: {archive_path}",
        )

    try:
        original_path.parent.mkdir(parents=True, exist_ok=True)
        restore_dest = safe_dest_path(original_path)
        archive_path.rename(restore_dest)

        return MoveRecord(
            source=str(archive_path),
            destination=str(restore_dest),
            action="undo_trash",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            size=record.size,
            success=True,
        )
    except Exception as exc:
        return MoveRecord(
            source=str(archive_path),
            destination=str(original_path),
            action="undo_trash",
            rule_name=f"undo({record.rule_name})",
            timestamp=timestamp,
            success=False,
            error=str(exc),
        )
