# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

`claude-code-protect` is a Claude Code plugin that intercepts Bash tool calls and enforces zone-based policies for file deletion commands. It works across the main session and all Task subagents.

## Plugin Architecture

The plugin is structured per the Claude Code plugin spec:

- **`.claude-plugin/plugin.json`** — plugin manifest (name, version, description)
- **`.claude-plugin/marketplace.json`** — marketplace listing metadata
- **`hooks/hooks.json`** — registers the single `PreToolUse` hook on `Bash` tool calls
- **`scripts/deletion-guard.py`** — the entire runtime logic (one self-contained Python script)
- **`commands/`** — slash command definitions as markdown files with YAML frontmatter
- **`skills/`** — skill markdown files for natural-language interaction

## How the Hook Works

`hooks/hooks.json` fires `deletion-guard.py` before every Bash tool use. The script receives a JSON payload on stdin:
```json
{"tool_name": "Bash", "tool_input": {"command": "..."}, "cwd": "..."}
```

The script exits `0` to allow the command or `2` to block it. It **fails open** — any unhandled exception exits `0` so a bug never prevents Claude from running commands.

### Detection tiers in `deletion-guard.py`

1. **Tier 1 (direct parse)**: `rm`, `rmdir`, `unlink`, `shred`, `trash`, `rimraf`, `del`, etc. — `shlex`-parsed to extract explicit path args
2. **Tier 2 (dry-run)**: `find ... -delete` / `find ... -exec rm` and `git clean -f*` — re-run without the deletion flag to enumerate targets
3. **Tier 3 (unresolvable)**: `$(...)`, backticks, `eval`, `base64 | bash`, Python/Node inline deletes — prompt user immediately

### Zone classification

After targets are identified, each path is classified:
- **workspace**: inside `$CLAUDE_PROJECT_DIR` (or cwd fallback) → auto-backup + allow
- **whitelist**: in `whitelisted_folders` from config → auto-backup + allow
- **tmp**: `/tmp`, `/var/tmp`, `/private/tmp`, platform temp → allow silently
- **outside**: everything else → prompt `[y/N]` on `/dev/tty`, block on deny or 30s timeout

## Configuration

Runtime config lives at `~/.claude/claude-code-protect.json` (not in repo). The script re-reads it on every invocation — no restart required.

```json
{
  "backup_mode": "centralized",
  "backup_root": "/optional/custom/path",
  "whitelisted_folders": ["/path/to/trusted/folder"]
}
```

## Backup Modes

**Centralized** (default): all backups in `~/.claude/claude-code-protect-backups/files/` with a `manifest.jsonl` tracking origin. JSONL format is safe for concurrent writes from parallel subagents.

**Per-folder**: backups in `.claude-backups/<timestamp_pid>/` inside the workspace/whitelisted folder root. Limited to 10MB per operation. The script adds `.claude-backups/` to `.gitignore` automatically.

Directories in `SKIP_NAMES` (`.git`, `node_modules`, `venv`, `dist`, `build`, etc.) are never backed up.

## Testing the Hook Manually

```bash
echo '{"tool_name":"Bash","tool_input":{"command":"rm /tmp/test.txt"},"cwd":"/tmp"}' | python3 scripts/deletion-guard.py
echo '{"tool_name":"Bash","tool_input":{"command":"rm ~/important.txt"},"cwd":"/tmp"}' | python3 scripts/deletion-guard.py
```

Exit code 0 = allowed, exit code 2 = blocked. Backup output prints to stdout; block reason prints to stderr.

## Slash Commands

Each file in `commands/` is a slash command. Frontmatter fields: `name`, `description`, `argument-hint`, `allowed-tools`. All commands operate on `~/.claude/claude-code-protect.json` directly using Read/Write tools.

## Adding a New Slash Command

Create `commands/<name>.md` with YAML frontmatter:
```markdown
---
name: command-name
description: What it does
argument-hint: "[optional-arg]"
allowed-tools: ["Read", "Write", "Bash"]
---

Instructions for Claude...
```

## Development vs Production

- **Dev/local**: `claude --plugin-dir /path/to/claude_code_protect` (session-only, no install)
- **Installed**: `claude plugin marketplace add frier-sam/claude_code_protect && claude plugin install claude-code-protect`

After any hook or script changes, restart Claude Code for changes to take effect.
