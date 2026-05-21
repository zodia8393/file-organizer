# Risk Analysis — organizer

## Risk Matrix

| # | Risk | Severity | Likelihood | Mitigation |
|---|------|----------|-----------|------------|
| R1 | Accidental file overwrite | Critical | Low | `safe_dest_path()` appends (2), (3). NEVER overwrites. |
| R2 | Data loss from failed cross-volume move | Critical | Low | Copy + hash verify before deleting original. On hash mismatch, both copies preserved. |
| R3 | Mid-operation power failure | High | Low | Same-volume: atomic `rename()`. Cross-volume: copy completes before delete. File always exists in at least one location. |
| R4 | .git or system directory corruption | Critical | Very Low | Hardcoded `SYSTEM_DIRS` exclusion set + configurable `exclude_dirs`. Checked before every operation. |
| R5 | Accidental silent execution | High | Medium | Dry-run is default. `apply` requires explicit `--confirm` flag. |
| R6 | Recently edited file moved mid-work | Medium | Medium | Cooldown mechanism (default 30 min). Files modified within window are skipped. |
| R7 | Symlink dereference causes unexpected moves | Medium | Low | Symlinks are detected and skipped (process neither target nor link). |
| R8 | Cloud sync conflict | High | Low | Cloud sync folders (Dropbox, iCloud, OneDrive, Google Drive) are in default exclusion list. |
| R9 | Unmatched file moved to wrong location | Medium | Very Low | Unmatched files are NEVER moved. Only explicit rule matches trigger action. |
| R10 | Undo fails due to modified/deleted file | Medium | Low | Hash verification before undo. If hash mismatch, operation skipped with error log. |
| R11 | Runaway batch processing | Low | Low | `batch_limit` setting (default 5000 files per run). |
| R12 | Log directory fills disk | Low | Very Low | Auto-cleanup of logs older than `log_retention_days` (default 30). |

## Design Decisions

### Why no file deletion

All "cleanup" actions use `.archive/` subfolders or `send2trash`. Direct `os.remove` / `os.unlink` is never called on user files. This makes every operation reversible.

### Why first-match-wins

Deterministic, easy to reason about. Users can order rules by specificity (e.g., "Screenshot*.png" before "*.png"). No ambiguity about which rule applies.

### Why SHA-256 hash verification

Cross-volume moves (copy + delete) carry inherent risk. Hash verification catches silent corruption from filesystem errors, bad blocks, or interrupted writes. Cost is negligible for typical file sizes.

### Why cooldown

Editors and applications may have files open for writing. Moving a file being actively written could cause data loss or application errors. The 30-minute default is conservative.

### Why atomic rename for same-volume

`Path.rename()` on the same filesystem is atomic at the kernel level. No intermediate state where the file doesn't exist.

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| Source file locked by another process | Preflight check detects, file skipped |
| Destination disk full | `shutil.copy2` raises OSError, source preserved, error logged |
| Permission denied on destination dir | `mkdir` raises OSError, source preserved, error logged |
| Hash mismatch after cross-volume copy | Both copies kept, IOError logged, original NOT deleted |
| YAML rule file malformed | Error on startup, no operations attempted |
| Empty scope directory | Plan has 0 actions, no harm done |

## Assumptions

1. The tool runs as the same user who owns the files
2. Filesystem supports standard POSIX operations (rename, stat, chmod)
3. No other process is simultaneously reorganizing the same directories
4. Clock drift is negligible for cooldown calculations
