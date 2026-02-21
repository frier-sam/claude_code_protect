---
name: backup-clear
description: Clear the claude-code-protect backup cache. Without arguments clears everything. Pass a workspace path to clear only backups originating from that workspace. Shows stats before and after.
argument-hint: "[workspace-path | --all]"
allowed-tools: ["Read", "Write", "Bash"]
---

Clear backup files from the centralized backup folder managed by claude-code-protect.

## Config

Read `~/.claude/claude-code-protect.json` to get `backup_root` (default: `~/.claude/claude-code-protect-backups/`).

## Two modes

### Clear all backups (default, no argument or `--all`)

1. Check that `{backup_root}/files/` exists. If not, say "No backups found." and stop.
2. Count files and total size in `{backup_root}/files/` using Bash:
   ```bash
   find "{backup_root}/files" -type f | wc -l
   du -sh "{backup_root}/files"
   ```
3. Confirm with user:
   > Found N files totalling X MB in backup cache.
   > Delete all? [y/N]
4. If yes:
   - Remove all contents of `{backup_root}/files/` (not the dir itself): `rm -rf "{backup_root}/files/"* 2>/dev/null; true`
   - Truncate `{backup_root}/manifest.jsonl` to empty: `> "{backup_root}/manifest.jsonl"`
   - Confirm: `✓ Cleared N files (X MB) from backup cache.`
5. If no: `Cancelled.`

### Clear by workspace (`$ARGUMENTS` is a path)

1. Read `{backup_root}/manifest.jsonl` line by line.
2. Filter lines where `"workspace"` field matches the given path (exact or prefix match).
3. If no matching entries: `No backups found for that workspace.` and stop.
4. List matched backup filenames and their original paths.
5. Confirm:
   > Found N files from <workspace>. Delete them? [y/N]
6. If yes:
   - Delete each matched file from `{backup_root}/files/`
   - Rewrite `manifest.jsonl` keeping only lines that did NOT match
   - Confirm: `✓ Cleared N files from <workspace>.`
7. If no: `Cancelled.`

## Notes

- Never delete `manifest.jsonl` itself, only truncate or rewrite it
- The `files/` directory itself should remain after clearing
- Inform the user the centralized backup folder location after clearing
