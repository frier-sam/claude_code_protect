---
name: uninstall
description: Uninstall the claude-code-protect plugin. Guides through removing the plugin reference from Claude Code settings, and optionally deletes the config file and backup cache.
allowed-tools: ["Read", "Write", "Bash"]
---

Uninstall the claude-code-protect plugin cleanly.

## Steps

### Step 1 — Confirm intent

Ask:
> You are about to uninstall **claude-code-protect** (the file deletion guard).
> After uninstalling, Claude Code will no longer intercept deletion commands.
>
> Proceed? [y/N]

If no: `Cancelled.` and stop.

### Step 2 — Remove plugin via CLI

Run:
```bash
claude plugin uninstall claude-code-protect
```

This removes the plugin from Claude Code's settings and plugin registry. If it fails or reports the plugin is not found, note it and continue.

### Step 3 — Handle config file

Ask:
> Delete the whitelist config at `~/.claude/claude-code-protect.json`? [y/N]

If yes: delete `~/.claude/claude-code-protect.json`. Confirm deleted.
If no: keep it (useful if reinstalling later).

### Step 4 — Handle backup cache

Read `~/.claude/claude-code-protect.json` (or default) to find `backup_root`.

Check if `{backup_root}/files/` exists and has content:
- If yes: count files and size, then ask:
  > Found N backed-up files (X MB) in `{backup_root}`.
  > Delete backup cache? [y/N]
  - If yes: `rm -rf "{backup_root}"` and confirm.
  - If no: keep it (files remain recoverable).

### Step 5 — Final instructions

Print:
```
✓ claude-code-protect uninstalled.

To complete uninstallation:
  1. Restart Claude Code — hooks are loaded at session start.
     After restart, no deletion commands will be intercepted.

To reinstall later:
  claude plugin marketplace add frier-sam/claude_code_protect
  claude plugin install claude-code-protect
```

If the backup cache was kept, also print:
```
Your backup cache is at: {backup_root}
You can delete it manually at any time:
  rm -rf "{backup_root}"
```
