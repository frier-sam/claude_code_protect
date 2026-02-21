---
name: whitelist-add
description: Add a folder to the claude-code-protect deletion guard whitelist. Whitelisted folders receive the same treatment as the workspace — files are auto-backed up before deletion with no user prompt required. In centralized mode (default) backups go to ~/.claude/claude-code-protect-backups/; in per-folder mode they go to .claude-backups/ inside the whitelisted folder.
argument-hint: "[absolute-folder-path]"
allowed-tools: ["Read", "Write", "Bash"]
---

Add a folder to the claude-code-protect whitelist stored in `~/.claude/claude-code-protect.json`.

## Config file

`~/.claude/claude-code-protect.json`

```json
{
  "whitelisted_folders": [
    "/path/to/folder"
  ]
}
```

## Steps

1. Determine the folder path:
   - If `$ARGUMENTS` is provided, use it as the folder path
   - Otherwise ask: "Which folder should I add to the deletion guard whitelist?"

2. Resolve to an absolute path using Bash: `realpath "$FOLDER_PATH"` (or `python3 -c "import os; print(os.path.realpath('$FOLDER_PATH'))"` on Windows)

3. Verify it is a directory: `test -d "$RESOLVED_PATH"` — if not, tell the user "That path is not a directory" and stop

4. Read `~/.claude/claude-code-protect.json` with the Read tool (if it exists)
   - If it does not exist, start with `{"whitelisted_folders": []}`

5. Parse the JSON. If `whitelisted_folders` already contains the resolved path, tell the user "Already whitelisted" and stop

6. Append the resolved path to `whitelisted_folders`

7. Write the updated JSON back to `~/.claude/claude-code-protect.json` with the Write tool (pretty-print with 2-space indent)

8. Read `backup_mode` from the config (default `"centralized"` if absent). Confirm to the user:

   **If centralized mode (default):**
   > ✓ Added `<path>` to the deletion guard whitelist.
   > Files deleted here will be auto-backed up to `~/.claude/claude-code-protect-backups/`.
   > No restart required — the guard reads this config on every invocation.

   **If per-folder mode:**
   > ✓ Added `<path>` to the deletion guard whitelist.
   > Files deleted here will be auto-backed up to `<path>/.claude-backups/` (up to 10MB per operation).
   > No restart required — the guard reads this config on every invocation.
