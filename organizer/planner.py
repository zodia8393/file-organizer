"""Plan generation — the 'plan' (dry-run) command.

Scans files, matches rules, and produces a list of planned actions
without touching the filesystem.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .rules import RuleSet, find_matching_rule
from .safety import (
    is_excluded_path,
    preflight_checks,
    safe_dest_path,
)


@dataclass
class PlannedAction:
    """A single planned file operation."""

    source: Path
    destination: Path | None  # None when action is 'trash'
    rule_name: str
    action: str  # "move" or "trash"
    size: int = 0
    skipped: bool = False
    skip_reason: str = ""


@dataclass
class Plan:
    """Complete execution plan for one or more scopes."""

    actions: list[PlannedAction]
    skipped: list[PlannedAction]
    scope_dirs: list[Path]
    created_at: str  # ISO timestamp


def generate_plan(
    scopes: list[Path],
    ruleset: RuleSet,
) -> Plan:
    """Walk scopes, match rules, and build a Plan without side effects.

    Files that fail safety checks are recorded in plan.skipped.
    """
    settings = ruleset.settings
    actions: list[PlannedAction] = []
    skipped: list[PlannedAction] = []
    seen = 0

    for scope in scopes:
        if not scope.exists():
            continue

        scope_depth = len(scope.parts)

        for dirpath, dirnames, filenames in os.walk(scope, followlinks=False):
            current = Path(dirpath)
            depth = len(current.parts) - scope_depth

            if depth >= settings.max_depth:
                dirnames.clear()
                continue

            # Prune excluded dirs
            dirnames[:] = [
                d
                for d in dirnames
                if not is_excluded_path(current / d, settings.exclude_dirs)
            ]

            for fname in filenames:
                if seen >= settings.batch_limit:
                    break

                filepath = current / fname

                # Safety preflight
                ok, reason = preflight_checks(
                    filepath,
                    settings.cooldown_minutes,
                    settings.exclude_dirs,
                    settings.exclude_files,
                )
                if not ok:
                    skipped.append(
                        PlannedAction(
                            source=filepath,
                            destination=None,
                            rule_name="(preflight)",
                            action="skip",
                            skipped=True,
                            skip_reason=reason,
                        )
                    )
                    seen += 1
                    continue

                # Match rules
                rule = find_matching_rule(filepath, ruleset)
                if rule is None:
                    # Unmatched files stay in place — never moved
                    continue

                seen += 1

                if rule.action == "trash":
                    actions.append(
                        PlannedAction(
                            source=filepath,
                            destination=None,
                            rule_name=rule.name,
                            action="trash",
                            size=filepath.stat().st_size,
                        )
                    )
                else:
                    dest_dir = rule.resolve_destination(filepath, scope)
                    if dest_dir is None:
                        continue
                    dest_file = safe_dest_path(dest_dir / filepath.name)
                    actions.append(
                        PlannedAction(
                            source=filepath,
                            destination=dest_file,
                            rule_name=rule.name,
                            action="move",
                            size=filepath.stat().st_size,
                        )
                    )

    return Plan(
        actions=actions,
        skipped=skipped,
        scope_dirs=scopes,
        created_at=datetime.now().isoformat(),
    )


def _human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"


def format_plan(plan: Plan) -> str:
    """Render a plan as a human-readable report for dry-run output."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  FILE ORGANIZATION PLAN (dry-run)")
    lines.append("=" * 60)
    lines.append(f"  Generated: {plan.created_at}")
    lines.append(
        f"  Scopes: {', '.join(str(s) for s in plan.scope_dirs)}"
    )
    lines.append("")

    moves = [a for a in plan.actions if a.action == "move"]
    trashes = [a for a in plan.actions if a.action == "trash"]

    lines.append(f"  Actions planned: {len(plan.actions)}")
    lines.append(f"    Move:  {len(moves)}")
    lines.append(f"    Trash: {len(trashes)}")
    lines.append(f"    Skipped: {len(plan.skipped)}")
    lines.append("")

    if moves:
        lines.append("-" * 60)
        lines.append("  MOVES")
        lines.append("-" * 60)
        for a in moves:
            lines.append(f"  [{a.rule_name}]")
            lines.append(f"    {a.source}")
            lines.append(f"    -> {a.destination}")
            lines.append(f"    ({_human_size(a.size)})")
            lines.append("")

    if trashes:
        lines.append("-" * 60)
        lines.append("  TRASH")
        lines.append("-" * 60)
        for a in trashes:
            lines.append(f"  [{a.rule_name}]")
            lines.append(f"    {a.source} ({_human_size(a.size)})")
        lines.append("")

    if plan.skipped:
        lines.append("-" * 60)
        lines.append("  SKIPPED")
        lines.append("-" * 60)
        for a in plan.skipped:
            lines.append(f"    {a.source}")
            lines.append(f"      Reason: {a.skip_reason}")
        lines.append("")

    lines.append("=" * 60)
    lines.append(
        "  This is a DRY RUN. No files were moved."
    )
    lines.append(
        "  To apply: organizer apply --confirm"
    )
    lines.append("=" * 60)

    return "\n".join(lines)
