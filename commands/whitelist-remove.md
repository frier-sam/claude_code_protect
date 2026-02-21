---
name: whitelist-remove
description: Remove a folder from the claude-code-protect deletion guard whitelist. After removal, deletions in that folder will prompt for user confirmation (same as any path outside the workspace).
argument-hint: "[absolute-folder-path]"
allowed-tools: ["Read", "Write"]
---

Remove a folder from the claude-code-protect whitelist stored in `~/.claude/claude-code-protect.json`.

## Config file

`~/.claude/claude-code-protect.json`

## Steps

1. Determine the folder path:
   - If `$ARGUMENTS` is provided, use it
   - Otherwise, first run the `whitelist-list` command to show the current list, then ask: "Which folder should I remove?"

2. Read `~/.claude/claude-code-protect.json` with the Read tool
   - If it does not exist or `whitelisted_folders` is empty, tell the user "The whitelist is already empty" and stop

3. Parse the JSON. Look for the path in `whitelisted_folders` — match both exact string and resolved form (e.g. `~/foo` and `/Users/sam/foo` are the same). If not found, tell the user "That path is not in the whitelist" and stop

4. Remove the matching entry from `whitelisted_folders`

5. Write the updated JSON back to `~/.claude/claude-code-protect.json` with the Write tool

6. Confirm to the user:
   > ✓ Removed `<path>` from the whitelist.
   > Deletions in that folder will now require your confirmation.
   > No restart required.
