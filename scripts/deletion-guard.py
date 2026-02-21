from __future__ import annotations

"""
deletion-guard.py — PreToolUse hook for Claude Code's Bash tool.

Intercepts file-deletion commands and enforces zone-based policies:
  workspace  → auto-backup (≤10 MB/op in per-folder mode; no limit in centralized mode), then allow
  tmp        → allow silently
  outside    → prompt user [y/N] on /dev/tty, block on deny/timeout
  unresolvable → prompt user [y/N] on /dev/tty, block on deny/timeout
"""

import glob
import json
import os
import re
import secrets
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path

CONFIG_PATH = Path.home() / ".claude" / "claude-code-protect.json"

def load_config() -> dict:
    """Load global whitelist config from ~/.claude/claude-code-protect.json."""
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open() as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def get_whitelisted_roots(config: dict) -> list[Path]:
    """Resolve whitelisted folder paths from config."""
    result = []
    for raw in config.get("whitelisted_folders", []):
        try:
            result.append(Path(os.path.expanduser(str(raw))).resolve())
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BACKUP_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB

SKIP_NAMES = frozenset({
    # VCS
    ".git", ".svn", ".hg",
    # Python environments & caches
    "venv", ".venv", "env", "__pypackages__",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    # Node
    "node_modules",
    # Build outputs
    "dist", "build", "out", "target", ".output",
    ".next", ".nuxt", ".svelte-kit", ".astro",
    # Mobile / JVM
    "Pods", ".gradle",
    # Coverage
    "coverage", ".nyc_output",
    # Temp
    "tmp", "temp", ".tmp",
})

# Tier-1 deletion commands (parsed for explicit path args)
UNIX_DELETE_CMDS = {"rm", "rmdir", "unlink", "shred", "trash", "rimraf"}
WIN_DELETE_CMDS = {"del", "erase", "rd"}
PS_DELETE_CMDS = {"remove-item", "ri"}
ALL_DELETE_CMDS = UNIX_DELETE_CMDS | WIN_DELETE_CMDS | PS_DELETE_CMDS

# Shell operators that terminate a simple command's argument list
SHELL_OPERATORS = {";", "&&", "||", "|", "&"}

# Tier-3 unresolvable patterns (regex applied to the raw command string)
UNRESOLVABLE_PATTERNS = [
    re.compile(r"\$\("),                    # $(...) subshell
    re.compile(r"`"),                       # backtick subshell
    re.compile(r"\beval\b"),                # eval keyword
    re.compile(r"base64.*\|\s*(ba)?sh"),    # base64 | bash/sh
    re.compile(r"os\.remove\("),            # Python inline
    re.compile(r"os\.unlink\("),
    re.compile(r"shutil\.rmtree\("),
    re.compile(r"\.unlink\(\)"),
    re.compile(r"fs\.unlinkSync\("),        # Node inline
    re.compile(r"fs\.rmdirSync\("),
    re.compile(r"fs\.rmSync\("),
    re.compile(r"fs\.promises\.unlink\("),
]

# Tier-2 patterns (detected separately, handled with dry-run)
FIND_DELETE_RE = re.compile(r"\bfind\b.*(-delete|-exec\s+rm\b)")
GIT_CLEAN_RE = re.compile(r"\bgit\s+clean\b.*(?:(?<!\-)-[a-z]*f[a-z]*\b|--force\b)")

DEFAULT_BACKUP_ROOT = Path.home() / ".claude" / "claude-code-protect-backups"
BACKUP_WARN_BYTES   = 500 * 1024 * 1024  # 500 MB

# ---------------------------------------------------------------------------
# Helpers — workspace & temp directory resolution
# ---------------------------------------------------------------------------

def get_workspace(cwd: str) -> Path:
    """Return the workspace root (CLAUDE_PROJECT_DIR → cwd → os.getcwd())."""
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if env_dir:
        return Path(env_dir).resolve()
    if cwd:
        return Path(cwd).resolve()
    return Path(os.getcwd()).resolve()


def get_tmp_dirs() -> list[Path]:
    """Return a list of resolved temp-directory roots for this platform."""
    candidates: list[str] = []
    if sys.platform == "win32":
        for var in ("TEMP", "TMP", "TMPDIR"):
            val = os.environ.get(var, "")
            if val:
                candidates.append(val)
    else:
        candidates.extend(["/tmp", "/var/tmp", "/private/tmp"])
    candidates.append(tempfile.gettempdir())
    resolved: list[Path] = []
    for c in candidates:
        try:
            resolved.append(Path(c).resolve())
        except Exception:
            pass
    return resolved


def is_inside(path: Path, root: Path) -> bool:
    """Return True if *path* is equal to or inside *root*."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def classify(
    path: Path,
    workspace: Path,
    tmp_dirs: list[Path],
    whitelisted: list[Path],
) -> tuple[str, Path]:
    """
    Classify a path into a zone and return its backup root.

    Returns (zone, backup_root):
      'workspace'  → backup_root = workspace
      'whitelist'  → backup_root = the matching whitelisted folder root
      'tmp'        → backup_root = workspace (unused, no backup)
      'outside'    → backup_root = workspace (unused, no backup)
    """
    resolved = path.resolve()
    if resolved == workspace:
        return "outside", workspace
    if is_inside(resolved, workspace):
        return "workspace", workspace
    for wl in whitelisted:
        if is_inside(resolved, wl):
            return "whitelist", wl
    for tmp in tmp_dirs:
        if is_inside(resolved, tmp):
            return "tmp", workspace
    return "outside", workspace

# ---------------------------------------------------------------------------
# Helpers — detection
# ---------------------------------------------------------------------------

def has_deletion(command: str) -> bool:
    """Return True if the command contains any deletion verb."""
    if FIND_DELETE_RE.search(command):
        return True
    if GIT_CLEAN_RE.search(command):
        return True
    if re.search(r"\bxargs\s+(?:sudo\s+)?(?:rm|unlink)\b", command):
        return True
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = shlex.split(command, posix=False)
    for token in tokens:
        base = os.path.basename(token).lower()
        if base in ALL_DELETE_CMDS:
            return True
    return False


def has_unresolvable(command: str) -> bool:
    """Return True if the command contains patterns we cannot safely parse."""
    for pat in UNRESOLVABLE_PATTERNS:
        if pat.search(command):
            return True
    return False

# ---------------------------------------------------------------------------
# Helpers — path parsing (Tier 1)
# ---------------------------------------------------------------------------

def parse_targets(command: str, cwd: str) -> list[Path]:
    """
    Parse explicit path arguments from a deletion command.

    Stops at shell operators. Skips flags. Handles '--' end-of-flags.
    Returns resolved Path objects for all targets (globs expanded).
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        tokens = shlex.split(command, posix=False)

    paths: list[Path] = []
    in_paths = False       # seen the delete verb
    end_of_flags = False   # seen '--'
    skip_next = False      # skip value of a flag that takes an arg (e.g. -t)

    for token in tokens:
        # shlex may attach ';' to the preceding token (e.g. "foo.txt;" from "rm foo.txt; rm bar.txt")
        has_semi = token.endswith(";")
        token = token.rstrip(";")
        if not token:
            if has_semi:
                break  # bare ';' — end of this command
            continue
        if skip_next:
            skip_next = False
            if has_semi:
                break
            continue
        if token in SHELL_OPERATORS:
            break
        base = os.path.basename(token).lower()
        if not in_paths:
            if base in ALL_DELETE_CMDS:
                in_paths = True
            if has_semi:
                break
            continue
        # inside argument list of the delete verb
        if token == "--":
            end_of_flags = True
            if has_semi:
                break
            continue
        if not end_of_flags:
            if token.startswith("-") or (sys.platform == "win32" and token.startswith("/")):
                # Some flags take a value argument — common ones:
                if token in {"-t", "--target-directory"}:
                    skip_next = True
                if has_semi:
                    break
                continue
        # It's a path argument
        expanded = os.path.expandvars(os.path.expanduser(token))
        # Resolve relative to cwd
        candidate = Path(cwd) / expanded if not os.path.isabs(expanded) else Path(expanded)
        # Expand globs
        matched = glob.glob(str(candidate), recursive=True)
        if matched:
            paths.extend(Path(m).resolve() for m in matched)
        else:
            # Include non-existent paths so we can still classify/block them
            paths.append(candidate.resolve())
        if has_semi:
            break  # ';' ended this command — don't parse the next command's args

    return paths

# ---------------------------------------------------------------------------
# Helpers — Tier-2 dry-run discovery
# ---------------------------------------------------------------------------

def dry_run_find(command: str, cwd: str) -> list[Path] | None:
    """
    Strip -delete / -exec rm and re-run find to discover targets.
    Returns list of paths or None on failure.
    """
    if not FIND_DELETE_RE.search(command):
        return None
    # Remove -delete flag
    stripped = re.sub(r"\s+-delete\b", "", command)
    # Remove -exec rm ... ; or -exec rm ... \; or -exec rm ... +
    stripped = re.sub(r"\s+-exec\s+rm\b[^;+]*[;+]", "", stripped)
    stripped = stripped.strip()
    if not stripped or stripped == command:
        return None
    try:
        result = subprocess.run(
            stripped, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=10
        )
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip()]
        return [Path(cwd) / l if not os.path.isabs(l) else Path(l) for l in lines]
    except Exception:
        return None


def dry_run_git_clean(command: str, cwd: str) -> list[Path] | None:
    """Replace -f with -n to get a dry-run list from git clean."""
    if not GIT_CLEAN_RE.search(command):
        return None
    # Replace all -f variants (-f, -fd, -df, -xfd) and --force with their -n equivalents
    dry = command.replace("--force", "-n")
    dry = re.sub(r"(?<!\-)-([a-z]*)f([a-z]*)\b", lambda m: f"-{m.group(1)}n{m.group(2)}", dry)
    if dry == command:
        return None
    try:
        result = subprocess.run(
            dry, shell=True, cwd=cwd,
            capture_output=True, text=True, timeout=10
        )
        paths: list[Path] = []
        for line in result.stdout.splitlines():
            # git clean -n outputs lines like "Would remove path/to/file"
            match = re.match(r"Would remove (.+)", line.strip())
            if match:
                rel = match.group(1)
                paths.append(Path(cwd) / rel)
        return paths if paths else None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Helpers — user prompt
# ---------------------------------------------------------------------------

def prompt_user(message: str) -> bool:
    """
    Write *message* to the terminal and read a y/N response.
    Returns True if user confirms (y/Y), False on deny or 30-second timeout.
    Cross-platform: uses /dev/tty on Unix, CONIN$/CONOUT$ on Windows.
    """
    tty_write = "CONOUT$" if sys.platform == "win32" else "/dev/tty"
    tty_read  = "CONIN$"  if sys.platform == "win32" else "/dev/tty"

    try:
        with open(tty_write, "w") as tty_out:
            tty_out.write(message)
            tty_out.flush()
    except OSError:
        # No terminal available — deny by default
        return False

    try:
        # Timeout via SIGALRM (Unix) or threading (Windows)
        if sys.platform != "win32":
            def _timeout_handler(signum, frame):  # noqa: ANN001
                raise TimeoutError

            old = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(30)
            try:
                with open(tty_read) as tty_in:
                    answer = tty_in.readline().strip()
            finally:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old)
        else:
            import threading
            answer_holder: list[str] = []

            def _read() -> None:
                try:
                    with open(tty_read) as tty_in:
                        answer_holder.append(tty_in.readline().strip())
                except OSError:
                    pass

            t = threading.Thread(target=_read, daemon=True)
            t.start()
            t.join(timeout=30)
            answer = answer_holder[0] if answer_holder else ""

        return answer.lower() == "y"
    except (TimeoutError, OSError):
        return False

# ---------------------------------------------------------------------------
# Backup logic
# ---------------------------------------------------------------------------

def ensure_gitignore(workspace: Path) -> None:
    """Append .claude-backups/ to .gitignore if not already present."""
    gitignore = workspace / ".gitignore"
    entry = ".claude-backups/"
    try:
        if gitignore.exists():
            content = gitignore.read_text()
            if any(line.strip() == entry.strip("/") or line.strip() == entry
                   for line in content.splitlines()):
                return
            gitignore.write_text(content.rstrip("\n") + "\n" + entry + "\n")
        else:
            gitignore.write_text(entry + "\n")
    except OSError:
        pass


def backup_targets(targets: list[Path], workspace: Path) -> None:
    """Back up workspace-zone targets, then print results to stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_root = workspace / ".claude-backups" / f"{timestamp}_{os.getpid()}"
    ensure_gitignore(workspace)

    # Check total size first
    total_size = 0
    for target in targets:
        if not target.exists():
            continue
        if _has_skip_component(target):
            continue
        try:
            if target.is_file():
                total_size += target.stat().st_size
            elif target.is_dir():
                for f in target.rglob("*"):
                    if f.is_file() and not _has_skip_component(f):
                        total_size += f.stat().st_size
        except OSError:
            pass

    if total_size > BACKUP_SIZE_LIMIT:
        print(f"  Skip (>10MB): total backup size {total_size // (1024*1024)} MB — skipping backup")
        return

    for target in targets:
        if not target.exists():
            continue
        if _has_skip_component(target):
            print(f"  Skip (node_modules/.git): {target}")
            continue
        try:
            rel = target.relative_to(workspace)
        except ValueError:
            rel = Path(target.name)
        dest = backup_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if target.is_file():
                shutil.copy2(target, dest)
            elif target.is_dir():
                shutil.copytree(
                    target, dest,
                    ignore=shutil.ignore_patterns("node_modules", ".git"),
                    dirs_exist_ok=True,
                )
            print(f"  Backed up: {rel}  \u2192  {dest.relative_to(workspace)}")
        except OSError as exc:
            print(f"  Backup failed for {rel}: {exc}")


def _has_skip_component(path: Path) -> bool:
    """Return True if any component of *path* should be skipped."""
    for part in path.parts:
        if part in SKIP_NAMES:
            return True
        # Match Python dist metadata dirs: foo.egg-info, foo.dist-info
        if part.endswith((".egg-info", ".dist-info")):
            return True
    return False


def _make_backup_name(path: Path) -> str:
    """Return a collision-safe backup filename: stem_<6hexchars><ext>."""
    suffix = secrets.token_hex(3)          # 6 hex chars, e.g. "a3b7c9"
    if path.is_dir():
        return f"{path.name}_{suffix}"
    ext  = path.suffix                     # e.g. ".tsx"  (empty string if none)
    stem = path.stem                       # e.g. "Button"
    return f"{stem}_{suffix}{ext}"


def backup_centralized(
    targets: list[Path],
    backup_root: Path,
    workspace: Path,
    command: str,
) -> None:
    """
    Copy each target to backup_root/files/ with a collision-safe name.
    Append one JSONL record per target to backup_root/manifest.jsonl.
    Warn if the total backup folder exceeds 500 MB.
    """
    files_dir    = backup_root / "files"
    manifest_path = backup_root / "manifest.jsonl"
    files_dir.mkdir(parents=True, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for target in targets:
        if not target.exists():
            continue
        if _has_skip_component(target):
            print(f"  ⏭ Skip (skip list): {target}")
            continue

        backup_name = _make_backup_name(target)
        dest = files_dir / backup_name

        # Avoid collision (extremely unlikely but be safe)
        while dest.exists():
            backup_name = _make_backup_name(target)
            dest = files_dir / backup_name

        try:
            if target.is_dir():
                shutil.copytree(
                    target, dest,
                    ignore=shutil.ignore_patterns(*SKIP_NAMES),
                    dirs_exist_ok=False,
                )
                size_bytes = sum(
                    f.stat().st_size for f in dest.rglob("*") if f.is_file()
                )
            else:
                shutil.copy2(target, dest)
                size_bytes = dest.stat().st_size

            # Append JSONL record
            record = {
                "id":              backup_name.rsplit("_", 1)[-1].split(".")[0],
                "backup_filename": backup_name,
                "original_path":   str(target),
                "backed_up_at":    now,
                "workspace":       str(workspace),
                "is_dir":          target.is_dir(),
                "size_bytes":      size_bytes,
                "command":         command,
            }
            with manifest_path.open("a") as mf:
                mf.write(json.dumps(record) + "\n")

            print(f"  ✓ Backed up: {target.name}  →  {backup_root}/files/{backup_name}")

        except OSError as exc:
            print(f"  ✗ Backup failed ({exc}): {target}")

    # Warn if total backup folder exceeds 500 MB
    _check_backup_size(backup_root)


def _check_backup_size(backup_root: Path) -> None:
    """Print a warning if the backup folder exceeds 500 MB."""
    try:
        total = sum(
            f.stat().st_size
            for f in backup_root.rglob("*")
            if f.is_file()
        )
        if total > BACKUP_WARN_BYTES:
            mb = total / (1024 * 1024)
            print(
                f"\n  ⚠️  Backup folder is {mb:.0f}MB "
                f"(~/.claude/claude-code-protect-backups/).\n"
                "  Run /claude-code-protect:backup-clear to free space."
            )
    except OSError:
        pass

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- Parse stdin JSON --------------------------------------------------
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    command: str = data.get("tool_input", {}).get("command", "")
    cwd: str = data.get("cwd", "") or os.getcwd()

    if not command:
        sys.exit(0)

    # ---- Workspace & temp dirs --------------------------------------------
    workspace = get_workspace(cwd)
    tmp_dirs = get_tmp_dirs()
    config = load_config()
    whitelisted = get_whitelisted_roots(config)
    backup_mode = config.get("backup_mode", "centralized")
    backup_root = Path(
        os.path.expanduser(config.get("backup_root", str(DEFAULT_BACKUP_ROOT)))
    ).resolve()

    # ---- Step 1: Does the command delete anything? -------------------------
    if not has_deletion(command):
        sys.exit(0)

    # ---- Step 2: Unresolvable patterns ------------------------------------
    if has_unresolvable(command):
        confirmed = prompt_user(
            f"\nDeletion guard: Command contains unresolvable paths:\n  {command}\n"
            "Allow this deletion? [y/N] "
        )
        if not confirmed:
            print(
                "Deletion guard: Unable to verify whether target paths are inside the "
                "workspace or /tmp. Rewrite using explicit file paths (avoid $(...), "
                "backtick subshells, eval, or base64-piped commands).",
                file=sys.stderr,
            )
            sys.exit(2)
        sys.exit(0)

    # ---- Step 3: Parse explicit targets ------------------------------------
    targets = parse_targets(command, cwd)

    # ---- Step 4: Tier-2 dry-run if no targets found -----------------------
    if not targets:
        if FIND_DELETE_RE.search(command):
            found = dry_run_find(command, cwd)
            if found is not None:
                targets = found
        elif GIT_CLEAN_RE.search(command):
            found = dry_run_git_clean(command, cwd)
            if found is not None:
                targets = found

    # Still no targets — prompt (implicit deletion we cannot enumerate)
    if not targets:
        confirmed = prompt_user(
            f"\nDeletion guard: Cannot enumerate deletion targets for:\n  {command}\n"
            "Allow this deletion? [y/N] "
        )
        if not confirmed:
            print(
                "Deletion guard: Unable to verify whether target paths are inside the "
                "workspace or /tmp. Rewrite using explicit file paths.",
                file=sys.stderr,
            )
            sys.exit(2)
        sys.exit(0)

    # ---- Step 5: Classify targets -----------------------------------------
    outside_targets: list[Path] = []

    # Map from backup_root → list of targets for that root
    backup_groups: dict[Path, list[Path]] = defaultdict(list)

    for t in targets:
        zone, folder_root = classify(t, workspace, tmp_dirs, whitelisted)
        if zone in ("workspace", "whitelist"):
            backup_groups[folder_root].append(t)
        elif zone == "outside":
            outside_targets.append(t)
        # tmp → allow silently

    # ---- Step 6: Prompt for outside targets --------------------------------
    if outside_targets:
        paths_str = "\n".join(f"  {p}" for p in outside_targets)
        confirmed = prompt_user(
            f"\nDeletion guard: The following paths are outside the workspace:\n"
            f"{paths_str}\nAllow deletion? [y/N] "
        )
        if not confirmed:
            blocked = ", ".join(str(p) for p in outside_targets)
            print(
                "Deletion guard: Deleting files outside the workspace or /tmp is not "
                "allowed and the user has not confirmed this operation.\n"
                f"Blocked: {blocked}",
                file=sys.stderr,
            )
            sys.exit(2)

    # ---- Step 7: Back up workspace targets ---------------------------------
    if backup_mode == "centralized":
        # Call per group so each manifest record stores the correct zone root
        # (workspace root for workspace files, whitelisted folder root for whitelisted files)
        for folder_root, group in backup_groups.items():
            if group:
                backup_centralized(group, backup_root, folder_root, command)
    else:
        # per-folder mode: backup to each folder's own .claude-backups/
        for folder_root, group in backup_groups.items():
            if group:
                backup_targets(group, folder_root)

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Fail open — never block Claude due to a bug in this script
        sys.stderr.write(f"[deletion-guard] unhandled error (failing open): {exc}\n")
        sys.exit(0)
