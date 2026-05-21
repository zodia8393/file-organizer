"""Read-only directory analysis — the 'analyze' command.

Scans target directories and produces a structured report:
- File counts by extension
- Size distribution
- Large / old / temp file identification
- Naming convention detection
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from .rules import RuleSet
from .safety import is_excluded_path


@dataclass
class FileInfo:
    """Lightweight file metadata."""

    path: Path
    size: int
    mtime: float
    extension: str


@dataclass
class AnalysisResult:
    """Aggregated analysis of a directory scope."""

    scope: Path
    total_files: int = 0
    total_size: int = 0
    extension_counts: dict[str, int] = field(default_factory=dict)
    extension_sizes: dict[str, int] = field(default_factory=dict)
    large_files: list[FileInfo] = field(default_factory=list)
    old_files: list[FileInfo] = field(default_factory=list)
    recent_files: list[FileInfo] = field(default_factory=list)
    temp_candidates: list[FileInfo] = field(default_factory=list)
    dir_count: int = 0
    errors: list[str] = field(default_factory=list)


def _scan_files(
    scope: Path,
    max_depth: int,
    exclude_dirs: list[str],
) -> list[FileInfo]:
    """Walk *scope* up to *max_depth* levels, returning FileInfo list."""
    files: list[FileInfo] = []
    scope_depth = len(scope.parts)

    for dirpath, dirnames, filenames in os.walk(scope, followlinks=False):
        current = Path(dirpath)
        depth = len(current.parts) - scope_depth

        if depth >= max_depth:
            dirnames.clear()
            continue

        # Prune excluded directories in-place
        dirnames[:] = [
            d
            for d in dirnames
            if not is_excluded_path(current / d, exclude_dirs)
        ]

        for fname in filenames:
            fpath = current / fname
            if is_excluded_path(fpath, exclude_dirs):
                continue
            try:
                stat = fpath.stat()
                ext = fpath.suffix.lower() or "(no ext)"
                # Handle .tar.gz compound
                if fpath.name.lower().endswith(".tar.gz"):
                    ext = ".tar.gz"
                files.append(
                    FileInfo(
                        path=fpath,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        extension=ext,
                    )
                )
            except OSError:
                pass  # Skip inaccessible files silently

    return files


# Thresholds
LARGE_FILE_MB = 100
OLD_FILE_DAYS = 365
TEMP_PREFIXES = ("temp", "tmp", "untitled", "~$", "._")


def analyze_scope(scope: Path, ruleset: RuleSet) -> AnalysisResult:
    """Perform read-only analysis of a single scope directory."""
    result = AnalysisResult(scope=scope)

    if not scope.exists():
        result.errors.append(f"Scope directory does not exist: {scope}")
        return result

    settings = ruleset.settings
    files = _scan_files(scope, settings.max_depth, settings.exclude_dirs)
    result.total_files = len(files)

    ext_counts: Counter[str] = Counter()
    ext_sizes: defaultdict[str, int] = defaultdict(int)
    now = datetime.now()

    for fi in files:
        result.total_size += fi.size
        ext_counts[fi.extension] += 1
        ext_sizes[fi.extension] += fi.size

        if fi.size > LARGE_FILE_MB * 1024 * 1024:
            result.large_files.append(fi)

        age = now - datetime.fromtimestamp(fi.mtime)
        if age > timedelta(days=OLD_FILE_DAYS):
            result.old_files.append(fi)
        elif age < timedelta(minutes=settings.cooldown_minutes):
            result.recent_files.append(fi)

        if fi.path.name.lower().startswith(TEMP_PREFIXES):
            result.temp_candidates.append(fi)

    result.extension_counts = dict(ext_counts.most_common())
    result.extension_sizes = dict(ext_sizes)

    # Count subdirectories
    result.dir_count = sum(
        1
        for _ in scope.rglob("*")
        if _.is_dir() and not is_excluded_path(_, settings.exclude_dirs)
    )

    return result


def _human_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"


def format_report(results: list[AnalysisResult]) -> str:
    """Render analysis results as a Markdown report."""
    lines: list[str] = ["# Directory Analysis Report", ""]
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    for r in results:
        lines.append(f"## Scope: `{r.scope}`")
        lines.append("")

        if r.errors:
            for err in r.errors:
                lines.append(f"> **Error**: {err}")
            lines.append("")
            continue

        lines.append(f"- **Total files**: {r.total_files:,}")
        lines.append(f"- **Total size**: {_human_size(r.total_size)}")
        lines.append(f"- **Subdirectories**: {r.dir_count:,}")
        lines.append("")

        # Extension breakdown
        if r.extension_counts:
            lines.append("### Extension Distribution")
            lines.append("")
            lines.append("| Extension | Count | Total Size |")
            lines.append("|-----------|------:|------------|")
            for ext, count in sorted(
                r.extension_counts.items(), key=lambda x: -x[1]
            ):
                sz = _human_size(r.extension_sizes.get(ext, 0))
                lines.append(f"| `{ext}` | {count:,} | {sz} |")
            lines.append("")

        # Large files
        if r.large_files:
            lines.append(f"### Large Files (>{LARGE_FILE_MB} MB)")
            lines.append("")
            for fi in sorted(r.large_files, key=lambda f: -f.size)[:20]:
                lines.append(
                    f"- `{fi.path.name}` — {_human_size(fi.size)}"
                )
            lines.append("")

        # Old files
        if r.old_files:
            lines.append(f"### Old Files (>{OLD_FILE_DAYS} days)")
            lines.append("")
            lines.append(f"Found **{len(r.old_files)}** files older than {OLD_FILE_DAYS} days.")
            lines.append("")

        # Temp candidates
        if r.temp_candidates:
            lines.append("### Temp/Cache Candidates")
            lines.append("")
            for fi in r.temp_candidates[:20]:
                lines.append(f"- `{fi.path.name}`")
            lines.append("")

        # Recently modified (cooldown)
        if r.recent_files:
            lines.append("### Recently Modified (in cooldown)")
            lines.append("")
            lines.append(
                f"**{len(r.recent_files)}** files will be skipped due to cooldown."
            )
            lines.append("")

    return "\n".join(lines)
