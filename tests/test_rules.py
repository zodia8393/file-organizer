"""Tests for rules module — loading, parsing, matching."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from organizer.rules import (
    MatchCondition,
    Rule,
    RuleSet,
    Settings,
    find_matching_rule,
    load_rules,
)


# ---------------------------------------------------------------------------
# MatchCondition tests
# ---------------------------------------------------------------------------

class TestMatchCondition:
    """Tests for the MatchCondition dataclass."""

    def test_extension_match(self, tmp_path: Path) -> None:
        mc = MatchCondition(extensions=[".pdf"])
        f = tmp_path / "report.pdf"
        f.touch()
        assert mc.matches(f) is True

    def test_extension_case_insensitive(self, tmp_path: Path) -> None:
        mc = MatchCondition(extensions=[".PDF"])
        f = tmp_path / "report.pdf"
        f.touch()
        assert mc.matches(f) is True

    def test_extension_no_match(self, tmp_path: Path) -> None:
        mc = MatchCondition(extensions=[".pdf"])
        f = tmp_path / "image.png"
        f.touch()
        assert mc.matches(f) is False

    def test_regex_match(self, tmp_path: Path) -> None:
        mc = MatchCondition(name_regex="^Screenshot")
        f = tmp_path / "Screenshot_2026.png"
        f.touch()
        assert mc.matches(f) is True

    def test_regex_no_match(self, tmp_path: Path) -> None:
        mc = MatchCondition(name_regex="^Screenshot")
        f = tmp_path / "photo.png"
        f.touch()
        assert mc.matches(f) is False

    def test_regex_case_insensitive(self, tmp_path: Path) -> None:
        mc = MatchCondition(name_regex="^screenshot")
        f = tmp_path / "Screenshot_2026.png"
        f.touch()
        assert mc.matches(f) is True

    def test_tar_gz_compound(self, tmp_path: Path) -> None:
        mc = MatchCondition(extensions=[".tar.gz"])
        f = tmp_path / "archive.tar.gz"
        f.touch()
        assert mc.matches(f) is True

    def test_empty_condition_matches_nothing(self, tmp_path: Path) -> None:
        mc = MatchCondition()
        f = tmp_path / "anything.txt"
        f.touch()
        assert mc.matches(f) is False

    def test_extension_normalizes_dot(self) -> None:
        mc = MatchCondition(extensions=["pdf"])
        assert mc.extensions == [".pdf"]


# ---------------------------------------------------------------------------
# Rule tests
# ---------------------------------------------------------------------------

class TestRule:
    """Tests for Rule.resolve_destination."""

    def test_resolve_with_year_placeholder(self, tmp_path: Path) -> None:
        import os, time
        f = tmp_path / "doc.pdf"
        f.write_text("hello")
        rule = Rule(
            name="PDF",
            match=MatchCondition(extensions=[".pdf"]),
            destination="Documents/{year}/",
        )
        dest = rule.resolve_destination(f, tmp_path)
        assert dest is not None
        assert "Documents" in str(dest)

    def test_trash_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "temp.txt"
        f.write_text("junk")
        rule = Rule(
            name="Trash",
            match=MatchCondition(name_regex="^temp"),
            action="trash",
        )
        assert rule.resolve_destination(f, tmp_path) is None


# ---------------------------------------------------------------------------
# load_rules tests
# ---------------------------------------------------------------------------

class TestLoadRules:
    """Tests for YAML loading."""

    def test_load_default_rules(self) -> None:
        default = Path(__file__).resolve().parent.parent / "config" / "default_rules.yaml"
        if not default.exists():
            pytest.skip("default_rules.yaml not found")
        rs = load_rules(default)
        assert isinstance(rs, RuleSet)
        assert len(rs.rules) > 0
        assert rs.settings.max_depth >= 1

    def test_load_custom_rules(self, tmp_path: Path) -> None:
        yaml_content = textwrap.dedent("""\
            settings:
              scopes: ["/tmp/test"]
              max_depth: 2
              cooldown_minutes: 10
              batch_limit: 100
              exclude_dirs: [".git"]
              log_retention_days: 7
            rules:
              - name: "Images"
                match:
                  extensions: [".png", ".jpg"]
                destination: "Images/"
        """)
        rule_file = tmp_path / "rules.yaml"
        rule_file.write_text(yaml_content)
        rs = load_rules(rule_file)
        assert len(rs.rules) == 1
        assert rs.rules[0].name == "Images"
        assert rs.settings.max_depth == 2

    def test_load_empty_rules(self, tmp_path: Path) -> None:
        rule_file = tmp_path / "empty.yaml"
        rule_file.write_text("settings:\nrules: []\n")
        rs = load_rules(rule_file)
        assert rs.rules == []


# ---------------------------------------------------------------------------
# find_matching_rule tests
# ---------------------------------------------------------------------------

class TestFindMatchingRule:
    """Tests for first-match-wins rule lookup."""

    def _make_ruleset(self) -> RuleSet:
        return RuleSet(
            settings=Settings(),
            rules=[
                Rule("Screenshots", MatchCondition(name_regex="^Screenshot"), "Screenshots/"),
                Rule("PNG", MatchCondition(extensions=[".png"]), "Images/"),
                Rule("PDF", MatchCondition(extensions=[".pdf"]), "Documents/"),
            ],
        )

    def test_first_match_wins(self, tmp_path: Path) -> None:
        rs = self._make_ruleset()
        f = tmp_path / "Screenshot_2026.png"
        f.touch()
        rule = find_matching_rule(f, rs)
        assert rule is not None
        assert rule.name == "Screenshots"  # Not "PNG"

    def test_extension_match(self, tmp_path: Path) -> None:
        rs = self._make_ruleset()
        f = tmp_path / "report.pdf"
        f.touch()
        rule = find_matching_rule(f, rs)
        assert rule is not None
        assert rule.name == "PDF"

    def test_no_match_returns_none(self, tmp_path: Path) -> None:
        rs = self._make_ruleset()
        f = tmp_path / "random.xyz"
        f.touch()
        rule = find_matching_rule(f, rs)
        assert rule is None
