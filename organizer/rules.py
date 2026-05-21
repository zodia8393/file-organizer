"""Rule loading, parsing, and matching logic.

Rules are loaded from YAML and evaluated top-to-bottom (first match wins).
Each rule has a match condition (extensions and/or name_regex) and a
destination template or action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MatchCondition:
    """Conditions for matching a file to a rule."""

    extensions: list[str] = field(default_factory=list)
    name_regex: str | None = None
    _compiled_regex: re.Pattern[str] | None = field(
        default=None, init=False, repr=False
    )

    def __post_init__(self) -> None:
        # Normalise extensions to lowercase with leading dot
        self.extensions = [
            ext.lower() if ext.startswith(".") else f".{ext.lower()}"
            for ext in self.extensions
        ]
        if self.name_regex:
            self._compiled_regex = re.compile(self.name_regex, re.IGNORECASE)

    def matches(self, filepath: Path) -> bool:
        """Return True if *filepath* satisfies this condition."""
        name = filepath.name
        suffix = filepath.suffix.lower()

        # Handle compound extensions like .tar.gz
        if name.lower().endswith(".tar.gz"):
            suffix = ".tar.gz"

        if self.extensions and suffix in self.extensions:
            return True
        if self._compiled_regex and self._compiled_regex.search(name):
            return True
        return False


@dataclass
class Rule:
    """A single classification rule."""

    name: str
    match: MatchCondition
    destination: str | None = None  # Template like "Documents/PDF/{year}/"
    action: str | None = None  # "trash" or None (default = move)

    def resolve_destination(
        self, filepath: Path, base_dir: Path
    ) -> Path | None:
        """Expand template placeholders and return the absolute destination dir.

        Returns None when the action is "trash" (no destination needed).
        """
        if self.action == "trash":
            return None
        if not self.destination:
            return None

        stat = filepath.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        dest = self.destination.format(
            year=mtime.strftime("%Y"),
            month=mtime.strftime("%m"),
            day=mtime.strftime("%d"),
        )
        return base_dir / dest


@dataclass
class Settings:
    """Global settings parsed from the YAML config."""

    scopes: list[Path] = field(default_factory=list)
    max_depth: int = 3
    cooldown_minutes: int = 30
    batch_limit: int = 5000
    exclude_dirs: list[str] = field(default_factory=list)
    exclude_files: list[str] = field(default_factory=list)
    log_retention_days: int = 30


@dataclass
class RuleSet:
    """Complete rule configuration: settings + ordered rules."""

    settings: Settings
    rules: list[Rule]


def _parse_match(raw: dict[str, Any]) -> MatchCondition:
    return MatchCondition(
        extensions=raw.get("extensions", []),
        name_regex=raw.get("name_regex"),
    )


def _parse_rule(raw: dict[str, Any]) -> Rule:
    return Rule(
        name=raw["name"],
        match=_parse_match(raw.get("match", {})),
        destination=raw.get("destination"),
        action=raw.get("action"),
    )


def _parse_settings(raw: dict[str, Any] | None) -> Settings:
    if raw is None:
        return Settings()
    scopes = [Path(p).expanduser() for p in raw.get("scopes", [])]
    return Settings(
        scopes=scopes,
        max_depth=raw.get("max_depth", 3),
        cooldown_minutes=raw.get("cooldown_minutes", 30),
        batch_limit=raw.get("batch_limit", 5000),
        exclude_dirs=raw.get("exclude_dirs", []),
        exclude_files=raw.get("exclude_files", []),
        log_retention_days=raw.get("log_retention_days", 30),
    )


def load_rules(path: Path) -> RuleSet:
    """Load and parse a YAML rules file into a RuleSet."""
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    settings = _parse_settings(data.get("settings"))
    rules = [_parse_rule(r) for r in data.get("rules", [])]
    return RuleSet(settings=settings, rules=rules)


def find_matching_rule(filepath: Path, ruleset: RuleSet) -> Rule | None:
    """Return the first rule that matches *filepath*, or None."""
    for rule in ruleset.rules:
        if rule.match.matches(filepath):
            return rule
    return None
