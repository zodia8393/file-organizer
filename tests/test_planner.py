"""Tests for planner module — dry-run plan generation."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from organizer.planner import Plan, PlannedAction, format_plan, generate_plan
from organizer.rules import MatchCondition, Rule, RuleSet, Settings


def _make_ruleset(
    rules: list[Rule] | None = None,
    cooldown_minutes: int = 0,
    max_depth: int = 3,
    exclude_dirs: list[str] | None = None,
    batch_limit: int = 5000,
) -> RuleSet:
    return RuleSet(
        settings=Settings(
            scopes=[],
            max_depth=max_depth,
            cooldown_minutes=cooldown_minutes,
            batch_limit=batch_limit,
            exclude_dirs=exclude_dirs or [],
            log_retention_days=30,
        ),
        rules=rules or [],
    )


def _age_file(path: Path, seconds: int = 3600) -> None:
    """Set file mtime to *seconds* ago."""
    t = time.time() - seconds
    os.utime(path, (t, t))


class TestGeneratePlan:
    def test_empty_scope(self, tmp_path: Path) -> None:
        rs = _make_ruleset()
        plan = generate_plan([tmp_path], rs)
        assert len(plan.actions) == 0

    def test_unmatched_files_not_planned(self, tmp_path: Path) -> None:
        (tmp_path / "mystery.xyz").write_text("data")
        _age_file(tmp_path / "mystery.xyz")
        rs = _make_ruleset(rules=[
            Rule("PDF", MatchCondition(extensions=[".pdf"]), "Docs/"),
        ])
        plan = generate_plan([tmp_path], rs)
        assert len(plan.actions) == 0  # .xyz not matched

    def test_matched_file_planned_for_move(self, tmp_path: Path) -> None:
        f = tmp_path / "report.pdf"
        f.write_text("pdf content")
        _age_file(f)
        rs = _make_ruleset(rules=[
            Rule("PDF", MatchCondition(extensions=[".pdf"]), "Documents/{year}/"),
        ])
        plan = generate_plan([tmp_path], rs)
        assert len(plan.actions) == 1
        assert plan.actions[0].action == "move"
        assert plan.actions[0].rule_name == "PDF"

    def test_trash_action_planned(self, tmp_path: Path) -> None:
        f = tmp_path / "temp_junk.txt"
        f.write_text("junk")
        _age_file(f)
        rs = _make_ruleset(rules=[
            Rule("Temp", MatchCondition(name_regex="^temp"), action="trash"),
        ])
        plan = generate_plan([tmp_path], rs)
        assert len(plan.actions) == 1
        assert plan.actions[0].action == "trash"

    def test_cooldown_skips_recent_files(self, tmp_path: Path) -> None:
        f = tmp_path / "new.pdf"
        f.write_text("new")
        # File is fresh (within cooldown)
        rs = _make_ruleset(
            rules=[Rule("PDF", MatchCondition(extensions=[".pdf"]), "Docs/")],
            cooldown_minutes=60,
        )
        plan = generate_plan([tmp_path], rs)
        assert len(plan.actions) == 0
        assert len(plan.skipped) == 1
        assert "cooldown" in plan.skipped[0].skip_reason.lower()

    def test_excluded_dirs_skipped(self, tmp_path: Path) -> None:
        git = tmp_path / ".git"
        git.mkdir()
        f = git / "HEAD"
        f.write_text("ref: refs/heads/main")
        rs = _make_ruleset(rules=[
            Rule("All", MatchCondition(extensions=[""]), "Out/"),
        ])
        plan = generate_plan([tmp_path], rs)
        # .git files should be in skipped, not in actions
        assert all(a.source.parent.name != ".git" for a in plan.actions)

    def test_batch_limit_respected(self, tmp_path: Path) -> None:
        for i in range(10):
            f = tmp_path / f"file{i}.pdf"
            f.write_text(f"content {i}")
            _age_file(f)
        rs = _make_ruleset(
            rules=[Rule("PDF", MatchCondition(extensions=[".pdf"]), "Docs/")],
            batch_limit=5,
        )
        plan = generate_plan([tmp_path], rs)
        # Total processed (actions + skipped) should not exceed batch_limit
        assert len(plan.actions) <= 5

    def test_first_match_wins(self, tmp_path: Path) -> None:
        f = tmp_path / "Screenshot_2026.png"
        f.write_bytes(b"\x89PNG")
        _age_file(f)
        rs = _make_ruleset(rules=[
            Rule("Screenshots", MatchCondition(name_regex="^Screenshot"), "Screenshots/"),
            Rule("Images", MatchCondition(extensions=[".png"]), "Images/"),
        ])
        plan = generate_plan([tmp_path], rs)
        assert len(plan.actions) == 1
        assert plan.actions[0].rule_name == "Screenshots"

    def test_nonexistent_scope_empty_plan(self, tmp_path: Path) -> None:
        rs = _make_ruleset()
        plan = generate_plan([tmp_path / "nonexistent"], rs)
        assert len(plan.actions) == 0

    def test_symlink_skipped(self, tmp_path: Path) -> None:
        target = tmp_path / "real.pdf"
        target.write_text("real")
        _age_file(target)
        link = tmp_path / "link.pdf"
        link.symlink_to(target)
        rs = _make_ruleset(rules=[
            Rule("PDF", MatchCondition(extensions=[".pdf"]), "Docs/"),
        ])
        plan = generate_plan([tmp_path], rs)
        # The symlink should be skipped; the real file should be planned
        sources = [a.source.name for a in plan.actions]
        assert "real.pdf" in sources
        skip_sources = [a.source.name for a in plan.skipped]
        assert "link.pdf" in skip_sources


class TestFormatPlan:
    def test_dry_run_message_present(self) -> None:
        plan = Plan(
            actions=[], skipped=[], scope_dirs=[Path("/tmp")],
            created_at="2026-05-21T00:00:00",
        )
        output = format_plan(plan)
        assert "DRY RUN" in output

    def test_move_shown(self) -> None:
        plan = Plan(
            actions=[
                PlannedAction(
                    source=Path("/tmp/a.pdf"),
                    destination=Path("/tmp/Docs/a.pdf"),
                    rule_name="PDF",
                    action="move",
                    size=1024,
                ),
            ],
            skipped=[],
            scope_dirs=[Path("/tmp")],
            created_at="2026-05-21T00:00:00",
        )
        output = format_plan(plan)
        assert "a.pdf" in output
        assert "PDF" in output
