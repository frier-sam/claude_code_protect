---
name: whitelist-list
description: Show all folders currently in the claude-code-protect deletion guard whitelist, along with the active workspace and /tmp (which are always allowed).
allowed-tools: ["Read", "Bash"]
---

Display the current deletion guard whitelist from `~/.claude/claude-code-protect.json`.

## Steps

1. Read `~/.claude/claude-code-protect.json` with the Read tool
   - If it does not exist, treat `whitelisted_folders` as empty and `backup_mode` as `"centralized"`

2. Get the current workspace with Bash: `echo "$CLAUDE_PROJECT_DIR"`

3. Get the system temp dir with Bash: `python3 -c "import tempfile; print(tempfile.gettempdir())"`

4. Determine backup destination based on `backup_mode`:
   - `centralized` (default): `~/.claude/claude-code-protect-backups/` for all zones
   - `per-folder`: each zone backs up to its own `.claude-backups/` subfolder

5. Display a formatted summary:

   **Centralized mode:**
   ```
   Deletion Guard — Allowed Zones
   ═══════════════════════════════════════

   Always allowed (built-in):
     • Workspace:  <CLAUDE_PROJECT_DIR>  → backups in ~/.claude/claude-code-protect-backups/
     • Temp:       <tempfile.gettempdir()> (and /tmp, /var/tmp)  → no backup

   Whitelisted folders:
     • /path/to/folder1  → backups in ~/.claude/claude-code-protect-backups/
     • /path/to/folder2  → backups in ~/.claude/claude-code-protect-backups/

   Everything else: requires your confirmation before deletion.

   Backup mode: centralized  (use /claude-code-protect:backup-mode to change)
   Config file: ~/.claude/claude-code-protect.json
   ```

   **Per-folder mode:**
   ```
   Deletion Guard — Allowed Zones
   ═══════════════════════════════════════

   Always allowed (built-in):
     • Workspace:  <CLAUDE_PROJECT_DIR>  → backups in <workspace>/.claude-backups/
     • Temp:       <tempfile.gettempdir()> (and /tmp, /var/tmp)  → no backup

   Whitelisted folders:
     • /path/to/folder1  → backups in /path/to/folder1/.claude-backups/
     • /path/to/folder2  → backups in /path/to/folder2/.claude-backups/

   Everything else: requires your confirmation before deletion.

   Backup mode: per-folder  (use /claude-code-protect:backup-mode to change)
   Config file: ~/.claude/claude-code-protect.json
   ```

6. If `whitelisted_folders` is empty or the file doesn't exist, show:
   ```
   No extra folders are whitelisted.
   Only the workspace and /tmp are allowed without confirmation.

   To add a folder: /claude-code-protect:whitelist-add /path/to/folder
   ```
