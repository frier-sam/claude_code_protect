# claude-code-protect

A Claude Code plugin that intercepts all Bash-based file deletion commands and enforces zone-based policies. Works with the main Claude Code session **and all Task subagents**.

## Zone Policy

| Zone | Condition | Action |
|------|-----------|--------|
| **workspace** | Inside `$CLAUDE_PROJECT_DIR` | Auto-backup, allow silently |
| **whitelisted** | In `~/.claude/claude-code-protect.json` | Auto-backup, allow silently |
| **tmp** | Inside `/tmp`, `/var/tmp`, `$TEMP`, etc. | Allow silently, no backup |
| **outside** | Everywhere else | Prompt `[y/N]`, **block on deny or 30s timeout** |
| **unresolvable** | Command uses `$(...)`, backticks, `eval`, `base64\|bash` | Prompt `[y/N]`, **block on deny or 30s timeout** |

Backup behaviour for workspace and whitelisted zones:
- Files/directories ≤ 10MB per-operation (per-folder mode) or no hard limit (centralized mode) are backed up automatically
- Files inside `node_modules`, `.git`, `venv`, `.venv`, `dist`, `build`, and similar generated directories are skipped
- Backups go to the **centralized folder** (default) or a **per-folder `.claude-backups/`** — see [Backup Modes](#backup-modes) below

---
## Installation

### Prerequisites
- Python 3.8+ in PATH as `python3`
- Claude Code with plugin support

### Install (recommended)

```bash
claude plugin marketplace add frier-sam/claude_code_protect
claude plugin install claude-code-protect
```

Then **restart Claude Code**. Hooks load at session start.

### Windows

If `python3` is not in PATH as `python3`, after installing edit `~/.claude/plugins/cache/.../hooks/hooks.json` and change:
```json
"command": "python3 \"$CLAUDE_PLUGIN_ROOT/scripts/deletion-guard.py\""
```
to:
```json
"command": "python \"$CLAUDE_PLUGIN_ROOT/scripts/deletion-guard.py\""
```

### Development (load from local directory)

```bash
claude --plugin-dir /path/to/claude_code_protect
```

> Note: `--plugin-dir` is session-only. Use the install method above for persistent installation.

---

## Updating

```bash
claude plugin update claude-code-protect
```

Then restart Claude Code.

---

## Uninstalling

```bash
claude plugin uninstall claude-code-protect
```

Then restart Claude Code.

For guided cleanup of the config file and backup cache, run the slash command instead:

```
/claude-code-protect:uninstall
```

This will:
1. Run `claude plugin uninstall claude-code-protect`
2. Optionally delete `~/.claude/claude-code-protect.json`
3. Optionally delete the backup cache
4. Remind you to restart Claude Code

---
<details>
<summary>Backup Modes</summary>

## Backup Modes
### Centralized (default, recommended)

All backups go to one folder: `~/.claude/claude-code-protect-backups/`

```
~/.claude/claude-code-protect-backups/
  files/
    deleted-file_a3f9c2.tsx          ← original name + 6-char hex suffix
    jan_b71d4e.csv
    my-component_0c8a1f/             ← directory copy (whole dir preserved inside)
  manifest.jsonl                     ← one JSON record per backed-up item
```

Each manifest line contains:
```json
{"id": "a3f9c2", "backup_filename": "deleted-file_a3f9c2.tsx", "original_path": "/Users/sam/project/src/deleted-file.tsx", "backed_up_at": "2026-02-21T10:30:45", "workspace": "/Users/sam/project", "is_dir": false, "size_bytes": 4096, "command": "rm src/deleted-file.tsx"}
```

**Benefits:**
- One place to find all backups
- Clear everything with `/claude-code-protect:backup-clear`
- Clear by workspace with `/claude-code-protect:backup-clear /path/to/project`
- 500 MB warning triggered when cache grows large
- JSONL format is safe for concurrent writes from parallel subagents

### Per-folder (optional)

Backups stored in `.claude-backups/` inside each workspace or whitelisted folder:

```
/your-workspace/
  .claude-backups/
    2026-02-21_10-30-45_1234/     ← timestamp + PID
      src/deleted-file.tsx        ← relative path preserved

/whitelisted-folder/
  .claude-backups/
    2026-02-21_10-30-45_1234/
      reports/jan.csv
```

`.claude-backups/` is automatically added to `.gitignore` in each root.

### Switching modes

```
/claude-code-protect:backup-mode centralized
/claude-code-protect:backup-mode per-folder
```

No restart required — takes effect on the next deletion.

---
</details>

<details>
<summary>Whitelist</summary>

## Whitelist

Add any folder to the whitelist to give it the same treatment as your workspace — files backed up automatically, no prompts needed.

### Three ways to manage the whitelist

**1. Slash commands:**
```
/claude-code-protect:whitelist-add /path/to/folder
/claude-code-protect:whitelist-remove /path/to/folder
/claude-code-protect:whitelist-list
```

**2. Natural language** (Claude reads the skill and handles it):
```
"Add /shared/data to the deletion guard whitelist"
"Stop prompting me for /Users/sam/scratch"
"Show the whitelist"
```

**3. Edit the config file directly:**

`~/.claude/claude-code-protect.json`
```json
{
  "whitelisted_folders": [
    "/Users/sam/shared-data",
    "/Users/sam/Documents/external-assets"
  ]
}
```

No restart needed — the guard reads this file on every invocation.

---
</details>


## Config File

All configuration lives in `~/.claude/claude-code-protect.json`:

```json
{
  "backup_mode": "centralized",
  "backup_root": "/custom/path/to/backups",
  "whitelisted_folders": [
    "/Users/sam/shared-data"
  ]
}
```

| Field | Default | Description |
|-------|---------|-------------|
| `backup_mode` | `"centralized"` | `"centralized"` or `"per-folder"` |
| `backup_root` | `~/.claude/claude-code-protect-backups/` | Custom centralized backup folder (centralized mode only) |
| `whitelisted_folders` | `[]` | Folders treated like the workspace |

No restart required — read on every hook invocation.

---

## Slash Commands

| Command | Description |
|---------|-------------|
| `/claude-code-protect:whitelist-add <path>` | Add a folder to the whitelist |
| `/claude-code-protect:whitelist-remove <path>` | Remove a folder from the whitelist |
| `/claude-code-protect:whitelist-list` | Show all whitelisted folders |
| `/claude-code-protect:backup-clear [path\|--all]` | Clear backup cache (all or by workspace) |
| `/claude-code-protect:backup-mode [centralized\|per-folder]` | Show or change backup mode |
| `/claude-code-protect:uninstall` | Guided uninstall walkthrough |

---

## What Gets Intercepted

**Direct commands (paths parsed):** `rm`, `rmdir`, `unlink`, `shred`, `trash`, `rimraf`, `del`, `erase`, `rd`, `Remove-Item`, `ri`

**Via dry-run discovery:** `find ... -delete`, `find ... -exec rm`, `git clean -f*`

**Cannot enumerate targets (prompts for confirmation):** `find ... | xargs rm`, scripted API calls (`os.remove()`, `os.unlink()`, `shutil.rmtree()`, `fs.unlinkSync()`, `fs.rmdirSync()`, `fs.rmSync()`, `fs.promises.unlink()`) `os.remove()`, `os.unlink()`, `shutil.rmtree()`, `fs.unlinkSync()`, `fs.rmdirSync()`, `fs.rmSync()`, `fs.promises.unlink()`

---



## How It Works With Subagents

The plugin registers hooks via the Claude Code plugin system. When Claude Code spawns a Task subagent, the subagent process also loads the same plugin hooks. This means **all deletion operations by all agents are guarded** — not just the main session.

---

## Known Limitations

- **Multi-command chains** (`rm a && rm b`): only the first deletion in a chain is fully analyzed.
- **Obfuscated commands** using `base64 | bash` (or backticks, `eval`, `$(…)`): user is prompted [y/N]; blocked on deny or 30-second timeout.
- **Compiled binaries** run via Bash that internally delete files cannot be intercepted.
- **Concurrent backups** from parallel subagents may race on `.gitignore` writes in per-folder mode (cosmetically harmless — may produce a duplicate entry).
