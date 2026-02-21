---
name: Whitelist Management
description: This skill should be used when the user asks to "add a folder to the whitelist", "whitelist a folder", "allow deletion in this folder", "trust this folder", "remove from whitelist", "show the whitelist", "list whitelisted folders", "what's whitelisted", "configure the deletion guard", "change backup mode", "switch to centralized backup", "switch to per-folder backup", or asks why a folder keeps prompting for deletion confirmation. Provides guidance for managing the claude-code-protect whitelist and backup configuration.
version: 1.0.0
---

# Whitelist Management

The `claude-code-protect` plugin controls which folders Claude can delete files in without prompting. The whitelist extends this permission to additional folders beyond the workspace and `/tmp`.

## Config File

All configuration lives in one file:

```
~/.claude/claude-code-protect.json
```

**Full format:**
```json
{
  "backup_mode": "centralized",
  "backup_root": "/custom/backup/path",
  "whitelisted_folders": [
    "/Users/sam/shared-data",
    "/Users/sam/Documents/external-assets"
  ]
}
```

**No restart required.** The guard reads this file on every hook invocation.

## Zone Policy

| Zone | How it's determined | Prompt? |
|------|---------------------|---------|
| Workspace | `$CLAUDE_PROJECT_DIR` | Never |
| Whitelisted | In `~/.claude/claude-code-protect.json` | Never |
| `/tmp` | System temp dirs | Never |
| Everything else | Not in any of the above | **Always** |

## Backup Modes

Backups for workspace and whitelisted zones go to one of two places depending on `backup_mode`:

### Centralized (default)

All backups in `~/.claude/claude-code-protect-backups/` (or custom `backup_root`):
- Flat structure with 6-char hex suffix to avoid name clashes
- JSONL manifest at `manifest.jsonl` tracking origin of every file
- 500 MB warning when cache grows large
- Clear with `/claude-code-protect:backup-clear`

### Per-folder

Backups in `.claude-backups/` inside each workspace or whitelisted folder:
- `{workspace}/.claude-backups/{timestamp}/` — relative paths preserved
- `{whitelisted_folder}/.claude-backups/{timestamp}/` — relative paths preserved
- `.claude-backups/` automatically added to `.gitignore`

### Switching modes

```
/claude-code-protect:backup-mode centralized
/claude-code-protect:backup-mode per-folder
```

No restart required.

## Managing the Whitelist

### Via slash commands (fastest)

```
/claude-code-protect:whitelist-add /path/to/folder
/claude-code-protect:whitelist-remove /path/to/folder
/claude-code-protect:whitelist-list
```

### Via natural language

Users can ask directly:
- "Add `/shared/data` to the whitelist"
- "Stop prompting me for deletions in `/Users/sam/scratch`"
- "Remove `/old/path` from the whitelist"

To handle these requests:
1. Identify the folder path from the user's message
2. Read `~/.claude/claude-code-protect.json` (create if missing with `{}`)
3. Add or remove the path from `whitelisted_folders`
4. Write the updated JSON back (2-space indent)
5. Confirm the change to the user

### Via direct editing

The user can open and edit `~/.claude/claude-code-protect.json` in any editor. The JSON is human-readable and the change takes effect immediately on the next deletion.

## Backup Behaviour in Whitelisted Folders

When a file in a whitelisted folder is deleted:

1. The guard checks whether the target contains skip directories (`node_modules`, `.git`, `venv`, `dist`, `build`, etc.)
2. In **per-folder mode**: checks if total size ≤ 10MB; skips if over
3. Backs up automatically without prompting
4. Always allows the deletion

Example (centralized mode): deleting `/shared/data/reports/jan.csv` (whitelisted at `/shared/data`):
→ backed up to `~/.claude/claude-code-protect-backups/files/jan_b71d4e.csv`
→ manifest records original path `/shared/data/reports/jan.csv`

Example (per-folder mode): same deletion:
→ backed up to `/shared/data/.claude-backups/2026-02-21_10-30-00_1234/reports/jan.csv`

## Troubleshooting

**"Why is Claude still prompting for a folder I whitelisted?"**
- Verify the exact path is in `whitelisted_folders` (use `whitelist-list`)
- Check for symlinks — the guard resolves paths, so use the real path (`realpath /my/folder`)
- The config file path must be exactly `~/.claude/claude-code-protect.json`

**"The backup wasn't created even though the folder is whitelisted"**
- In per-folder mode: file may exceed 10MB per-operation limit
- File may be inside a skipped directory (`node_modules`, `.git`, `venv`, `dist`, etc.)
- Check stdout from the hook for skip messages

**"Where are my backups?"**
- Run `/claude-code-protect:backup-mode` to see the current mode and backup location
- In centralized mode: `~/.claude/claude-code-protect-backups/files/`
- In per-folder mode: `.claude-backups/` inside the workspace or whitelisted folder root

## Config File Location

| Platform | Path |
|----------|------|
| macOS / Linux | `~/.claude/claude-code-protect.json` |
| Windows | `C:\Users\<name>\.claude\claude-code-protect.json` |
