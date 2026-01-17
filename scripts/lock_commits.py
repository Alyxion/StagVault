#!/usr/bin/env python3
"""Lock git commit IDs for all sources to ensure reproducible data.

This script fetches the current HEAD commit for each configured git source
and updates the source config YAML files with the exact commit hash.

Usage:
    python scripts/lock_commits.py                    # Lock all sources
    python scripts/lock_commits.py --source phosphor  # Lock specific source
    python scripts/lock_commits.py --verify           # Verify locks match remote
    python scripts/lock_commits.py --update           # Update to latest commits
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

CONFIGS_DIR = Path(__file__).parent.parent / "configs" / "sources"


def get_remote_commit(repo: str, branch: str) -> str | None:
    """Fetch the current HEAD commit from GitHub without cloning."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", f"https://github.com/{repo}.git", f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            commit = result.stdout.split()[0]
            return commit
        return None
    except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
        print(f"  Error fetching {repo}: {e}", file=sys.stderr)
        return None


def load_config(path: Path) -> dict:
    """Load a YAML config file."""
    with open(path) as f:
        return yaml.safe_load(f)


def save_config(path: Path, config: dict) -> None:
    """Save a YAML config file preserving order."""
    with open(path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


def lock_source(config_path: Path, update: bool = False) -> tuple[str, str | None, str | None]:
    """Lock a single source config.

    Returns: (source_id, old_commit, new_commit)
    """
    config = load_config(config_path)
    source_id = config.get("id", config_path.stem)

    if config.get("type") != "git":
        return source_id, None, None

    git_config = config.get("git", {})
    repo = git_config.get("repo")
    branch = git_config.get("branch", "main")
    old_commit = git_config.get("commit")

    if not repo:
        return source_id, old_commit, None

    # Skip if already locked and not updating
    if old_commit and not update:
        return source_id, old_commit, old_commit

    new_commit = get_remote_commit(repo, branch)
    if new_commit:
        git_config["commit"] = new_commit
        config["git"] = git_config
        save_config(config_path, config)

    return source_id, old_commit, new_commit


def verify_source(config_path: Path) -> tuple[str, bool, str]:
    """Verify a source's locked commit matches remote.

    Returns: (source_id, matches, message)
    """
    config = load_config(config_path)
    source_id = config.get("id", config_path.stem)

    if config.get("type") != "git":
        return source_id, True, "Not a git source"

    git_config = config.get("git", {})
    repo = git_config.get("repo")
    branch = git_config.get("branch", "main")
    locked_commit = git_config.get("commit")

    if not locked_commit:
        return source_id, False, "No commit locked"

    remote_commit = get_remote_commit(repo, branch)
    if not remote_commit:
        return source_id, False, "Could not fetch remote"

    if locked_commit == remote_commit:
        return source_id, True, f"Up to date: {locked_commit[:8]}"
    else:
        return source_id, False, f"Outdated: {locked_commit[:8]} -> {remote_commit[:8]}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Lock git commit IDs for sources")
    parser.add_argument("--source", "-s", help="Specific source to process")
    parser.add_argument("--verify", "-v", action="store_true", help="Verify locks match remote")
    parser.add_argument("--update", "-u", action="store_true", help="Update to latest commits")
    parser.add_argument("--list", "-l", action="store_true", help="List current locks")
    args = parser.parse_args()

    if not CONFIGS_DIR.exists():
        print(f"Config directory not found: {CONFIGS_DIR}", file=sys.stderr)
        sys.exit(1)

    config_files = sorted(CONFIGS_DIR.glob("*.yaml"))
    if args.source:
        config_files = [f for f in config_files if f.stem == args.source]
        if not config_files:
            print(f"Source not found: {args.source}", file=sys.stderr)
            sys.exit(1)

    if args.list:
        print("Current commit locks:\n")
        for config_path in config_files:
            config = load_config(config_path)
            source_id = config.get("id", config_path.stem)
            commit = config.get("git", {}).get("commit", "not locked")
            print(f"  {source_id}: {commit[:12] if len(commit) > 12 else commit}")
        return

    if args.verify:
        print("Verifying commit locks...\n")
        all_ok = True
        for config_path in config_files:
            source_id, ok, message = verify_source(config_path)
            status = "✓" if ok else "✗"
            print(f"  {status} {source_id}: {message}")
            if not ok:
                all_ok = False
        sys.exit(0 if all_ok else 1)

    # Lock or update commits
    action = "Updating" if args.update else "Locking"
    print(f"{action} commit IDs...\n")

    for config_path in config_files:
        source_id, old_commit, new_commit = lock_source(config_path, update=args.update)

        if new_commit is None:
            if old_commit:
                print(f"  {source_id}: keeping {old_commit[:8]}")
            else:
                print(f"  {source_id}: skipped (not git or error)")
        elif old_commit == new_commit:
            print(f"  {source_id}: unchanged {new_commit[:8]}")
        elif old_commit:
            print(f"  {source_id}: {old_commit[:8]} -> {new_commit[:8]}")
        else:
            print(f"  {source_id}: locked to {new_commit[:8]}")

    print("\nDone! Commit IDs are now locked in source configs.")
    print("Run with --verify to check if locks match current remote HEAD.")


if __name__ == "__main__":
    main()
