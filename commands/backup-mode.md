---
name: backup-mode
description: Show or change the backup mode for claude-code-protect. Two modes available — centralized (default, all backups in one folder with JSON manifest) or per-folder (backups in .claude-backups/ inside each workspace/whitelisted folder).
argument-hint: "[centralized | per-folder]"
allowed-tools: ["Read", "Write"]
---

Show or change the `backup_mode` setting in `~/.claude/claude-code-protect.json`.

## No argument — show current mode

1. Read `~/.claude/claude-code-protect.json` (default mode is `"centralized"` if file absent).
2. Display current configuration:

```
Backup Mode: centralized  ← current
────────────────────────────────────────────────────
  centralized (default, recommended)
    All backups go to one folder: ~/.claude/claude-code-protect-backups/
    • Flat structure with random suffix to avoid name clashes
    • JSONL manifest tracks origin of every file
    • Clear everything with /claude-code-protect:backup-clear

  per-folder
    Backups stored in .claude-backups/ inside each workspace/whitelisted folder
    • Traditional approach, backups stay near the project
    • Must clear per-project

To switch: /claude-code-protect:backup-mode [centralized | per-folder]
```

## With argument — switch mode

1. Validate argument is `centralized` or `per-folder`. If not, show usage and stop.
2. Read `~/.claude/claude-code-protect.json` (create if missing with `{}`).
3. Set `"backup_mode"` to the given value.
4. Write updated JSON back (2-space indent).
5. Confirm:
   > ✓ Backup mode set to **<mode>**.
   >
   > For centralized: backups will go to `~/.claude/claude-code-protect-backups/`
   > For per-folder: backups will go to `.claude-backups/` inside each workspace/whitelisted folder
   >
   > No restart required — takes effect on the next deletion.

## Tip

To also change the centralized backup root folder, edit `~/.claude/claude-code-protect.json` directly:
```json
{
  "backup_mode": "centralized",
  "backup_root": "/Volumes/external-drive/claude-backups"
}
```
