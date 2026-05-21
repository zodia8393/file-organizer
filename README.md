# organizer

![CI](https://github.com/zodia8393/file-organizer/actions/workflows/ci.yml/badge.svg)

Directory file organization automation tool with safety-first design.

## Quick Start

```bash
cd /workspace/app_organizer
pip install -e .

# 1. Analyze a directory (read-only)
organizer analyze --scope ~/Downloads

# 2. Preview what would be moved (DEFAULT, dry-run)
organizer plan --scope ~/Downloads

# 3. Execute moves (requires --confirm)
organizer apply --scope ~/Downloads --confirm
```

## Commands

| Command | Description |
|---------|-------------|
| `analyze` | Read-only analysis: file counts, sizes, extensions, old/temp files |
| `plan` | Dry-run: show planned moves without touching any file |
| `apply` | Execute moves. **Requires `--confirm` flag.** |
| `undo <log_file>` | Reverse all operations from a session log |
| `history` | List recent session logs |
| `version` | Show version |

## Options

| Flag | Description |
|------|-------------|
| `--scope`, `-s` | Directory to scan (repeatable). Overrides YAML config. |
| `--rule-file`, `-r` | Custom YAML rules file. Default: `config/default_rules.yaml` |
| `--confirm` | Required for `apply` to actually execute moves |
| `--limit`, `-n` | Number of history entries to show (default: 20) |

## Safety Guarantees

1. **Dry-run is DEFAULT** — `plan` shows intent, `apply` requires explicit `--confirm`
2. **No overwrites** — name conflicts get `(2)`, `(3)` suffixes
3. **No deletions** — "trash" action moves to `.archive/` or system trash
4. **Full audit trail** — every operation logged as JSON in `~/.organize/history/`
5. **Undo support** — reverse any session with `organizer undo <log.json>`
6. **Exclusions** — `.git`, `node_modules`, `__pycache__`, cloud sync folders are never touched
7. **Cooldown** — recently modified files (default 30 min) are skipped
8. **Cross-volume safety** — copy, verify hash, then delete original
9. **Mid-failure safety** — files exist in at least one location at all times
10. **Unmatched files stay** — only files matching rules are moved

## Rule Configuration

Rules are defined in YAML. See `config/default_rules.yaml` for the full default set.

```yaml
rules:
  - name: "PDF Documents"
    match:
      extensions: [".pdf"]
    destination: "Documents/PDF/{year}/"

  - name: "Screenshots"
    match:
      name_regex: "^(Screenshot|screen)"
    destination: "Images/Screenshots/{year}-{month}/"

  - name: "Temp Files"
    match:
      name_regex: "^(temp|tmp)"
    action: "trash"
```

### Placeholders

| Placeholder | Expands to |
|-------------|-----------|
| `{year}` | File modification year (e.g., `2026`) |
| `{month}` | File modification month, zero-padded (`05`) |
| `{day}` | File modification day, zero-padded (`21`) |

### Match Conditions

- `extensions`: list of file extensions (case-insensitive, with or without dot)
- `name_regex`: Python regex matched against the filename (case-insensitive)

Rules are evaluated top-to-bottom. First match wins. Unmatched files are never moved.

## Undo

Every `apply` session creates a JSON log at `~/.organize/history/YYYY-MM-DD-HHMMSS.json`.

```bash
# List recent sessions
organizer history

# Undo a specific session
organizer undo ~/.organize/history/2026-05-21-143000.json
```

The undo verifies file integrity via SHA-256 hash before restoring.

## Scheduling (cron)

```bash
# Run daily at midnight
0 0 * * * cd /workspace/app_organizer && python -m organizer.cli apply --scope ~/Downloads --confirm
```

## Testing

```bash
cd /workspace/app_organizer
pytest -v
```

## Project Structure

```
app_organizer/
  config/default_rules.yaml   # Default classification rules
  docs/risks.md               # Risk analysis
  organizer/
    __init__.py                # Package metadata
    cli.py                     # Typer CLI entry point
    analyzer.py                # Read-only analysis
    planner.py                 # Dry-run plan generation
    executor.py                # Actual file operations
    rules.py                   # Rule loading and matching
    logger.py                  # JSON session logging
    undo.py                    # Operation reversal
    safety.py                  # Safety checks and guards
  tests/                       # pytest test suite
  pyproject.toml               # Packaging
```
