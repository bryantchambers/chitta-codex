#!/usr/bin/env python3
"""Reproducible Codex bootstrap for CHITTA.

This repo is intentionally thin:
- it checks out pinned revisions of the existing repos,
- invokes the existing installers,
- adds a Codex-only zellij-mcp config block,
- validates with Codex CLI smoke checks,
- and can roll back config changes from a saved backup.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


MANAGED_BEGIN = "# BEGIN chitta-codex-bootstrap zellij-mcp (auto-managed, do not edit)"
MANAGED_END = "# END chitta-codex-bootstrap zellij-mcp"
MANAGED_RE = re.compile(r"\n?" + re.escape(MANAGED_BEGIN) + r".*?" + re.escape(MANAGED_END) + r"\n?", re.DOTALL)


@dataclass(frozen=True)
class RepoSpec:
    name: str
    url: str
    ref: str
    path: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def load_manifest() -> dict:
    return json.loads((repo_root() / "manifest.json").read_text())


def load_repos() -> list[RepoSpec]:
    manifest = load_manifest()
    repos: list[RepoSpec] = []
    for item in manifest["repos"]:
        repos.append(
            RepoSpec(
                name=item["name"],
                url=item["url"],
                ref=item["ref"],
                path=repo_root() / item["path"],
            )
        )
    return repos


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def codex_config() -> Path:
    return codex_home() / "config.toml"


def state_path() -> Path:
    return repo_root() / ".bootstrap-state.json"


def backups_dir() -> Path:
    return repo_root() / "backups"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def print_cmd(cmd: Iterable[str], cwd: Optional[Path] = None) -> None:
    rendered = " ".join(subprocess.list2cmdline([part]) if " " in part else part for part in cmd)
    if cwd:
        print(f"$ (cd {cwd} && {rendered})")
    else:
        print(f"$ {rendered}")


def run_cmd(cmd: list[str], *, cwd: Optional[Path] = None, dry_run: bool = False, env: Optional[dict] = None) -> None:
    print_cmd(cmd, cwd)
    if dry_run:
        return
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, env=env)


def run_output(cmd: list[str], *, cwd: Optional[Path] = None, dry_run: bool = False) -> str:
    print_cmd(cmd, cwd)
    if dry_run:
        return ""
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True, capture_output=True, text=True)
    return result.stdout


def clone_or_update(repo: RepoSpec, dry_run: bool = False) -> Path:
    if repo.path.exists() and not (repo.path / ".git").is_dir():
        raise RuntimeError(f"{repo.path} exists but is not a git checkout")

    if not repo.path.exists():
        ensure_parent(repo.path)
        run_cmd(["git", "clone", repo.url, str(repo.path)], dry_run=dry_run)
    else:
        run_cmd(["git", "-C", str(repo.path), "fetch", "--tags", "--prune", "origin"], dry_run=dry_run)

    run_cmd(["git", "-C", str(repo.path), "checkout", "--detach", repo.ref], dry_run=dry_run)
    run_cmd(["git", "-C", str(repo.path), "reset", "--hard", repo.ref], dry_run=dry_run)
    return repo.path


def backup_codex_files(dry_run: bool = False) -> dict:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = {
        "config": str(backups_dir() / f"config.toml.{stamp}"),
        "hooks": str(backups_dir() / f"hooks.json.{stamp}"),
    }
    if dry_run:
        print(f"Would back up Codex config to {backup['config']}")
        print(f"Would back up Codex hooks to {backup['hooks']}")
        return backup

    backups_dir().mkdir(parents=True, exist_ok=True)
    if codex_config().is_file():
        shutil.copy2(codex_config(), backup["config"])
    if (codex_home() / "hooks.json").is_file():
        shutil.copy2(codex_home() / "hooks.json", backup["hooks"])
    return backup


def restore_backup(backup: dict, dry_run: bool = False) -> None:
    config_backup = Path(backup.get("config", ""))
    hooks_backup = Path(backup.get("hooks", ""))
    if config_backup.is_file():
        print(f"Restoring {codex_config()} from {config_backup}")
        if not dry_run:
            shutil.copy2(config_backup, codex_config())
    if hooks_backup.is_file():
        hooks_dest = codex_home() / "hooks.json"
        print(f"Restoring {hooks_dest} from {hooks_backup}")
        if not dry_run:
            shutil.copy2(hooks_backup, hooks_dest)


def choose_python() -> str:
    return sys.executable


def manifest_codex() -> dict:
    return load_manifest()["codex"]


def apply_zellij_block(repos: dict[str, Path], dry_run: bool = False) -> None:
    server = repos["zellij-mcp"] / "server.py"
    python_bin = choose_python()
    if not server.is_file():
        raise RuntimeError(f"zellij server not found at {server}")

    block = (
        f"{MANAGED_BEGIN}\n"
        f"[mcp_servers.\"zellij-mcp\"]\n"
        f"command = \"{python_bin}\"\n"
        f"args = [\"{server}\"]\n"
        f"startup_timeout_sec = {manifest_codex()['startup_timeout_sec']}\n"
        f"{MANAGED_END}\n"
    )

    config = codex_config()
    config.parent.mkdir(parents=True, exist_ok=True)
    if not config.exists():
        config.write_text("")

    raw = config.read_text()
    stripped = MANAGED_RE.sub("\n", raw)
    new_text = stripped.rstrip()
    if new_text:
        new_text += "\n\n"
    new_text += block

    print(f"Updating {config} with managed zellij-mcp block")
    if not dry_run:
        config.write_text(new_text)


def cc_soul_repos_root(repos: dict[str, Path]) -> Path:
    return repos["cc-soul"]


def install_cc_soul(repos: dict[str, Path], dry_run: bool = False) -> None:
    script = cc_soul_repos_root(repos) / "scripts" / "smart-install.sh"
    if not script.is_file():
        raise RuntimeError(f"cc-soul install script not found at {script}")
    run_cmd(["bash", str(script)], cwd=cc_soul_repos_root(repos), dry_run=dry_run)


def install_cc_soul_codex(repos: dict[str, Path], dry_run: bool = False) -> None:
    script = cc_soul_repos_root(repos) / "chitta-mcp" / "install.py"
    if not script.is_file():
        raise RuntimeError(f"cc-soul codex installer not found at {script}")
    run_cmd([sys.executable, str(script), "codex"], cwd=cc_soul_repos_root(repos), dry_run=dry_run)


def install_bridge(repos: dict[str, Path], dry_run: bool = False) -> None:
    script = repos["chitta-bridge"] / "chitta_bridge" / "install.py"
    if not script.is_file():
        raise RuntimeError(f"chitta-bridge installer not found at {script}")
    run_cmd([sys.executable, str(script), "codex"], cwd=repos["chitta-bridge"], dry_run=dry_run)


def verify_installed() -> None:
    for cmd in (
        ["codex", "doctor"],
        ["codex", "mcp", "list"],
        ["codex", "mcp", "get", "chitta"],
        ["codex", "mcp", "get", "chitta-bridge"],
        ["codex", "mcp", "get", "zellij-mcp"],
    ):
        run_cmd(cmd)


def install(dry_run: bool = False) -> None:
    repos = load_repos()
    resolved: dict[str, Path] = {}
    print("Bootstrap plan:")
    for repo in repos:
        print(f"  {repo.name}: {repo.url} @ {repo.ref} -> {repo.path}")

    if dry_run:
        print("\nDry run only. No changes were made.")
        return

    backup = backup_codex_files()
    state = {"backup": backup, "repos": {}, "created_at": datetime.now(timezone.utc).isoformat()}

    try:
        for repo in repos:
            resolved[repo.name] = clone_or_update(repo, dry_run=False)
            state["repos"][repo.name] = {"path": str(resolved[repo.name]), "ref": repo.ref, "url": repo.url}

        install_cc_soul(resolved, dry_run=False)
        install_cc_soul_codex(resolved, dry_run=False)
        install_bridge(resolved, dry_run=False)
        apply_zellij_block(resolved, dry_run=False)

        state_path().write_text(json.dumps(state, indent=2) + "\n")
        verify_installed()
        print("\nInstall complete.")
    except Exception:
        restore_backup(backup)
        raise


def rollback(dry_run: bool = False) -> None:
    if not state_path().is_file():
        print("No bootstrap state file found; removing managed zellij-mcp block only.")
        config = codex_config()
        if config.is_file():
            raw = config.read_text()
            cleaned = MANAGED_RE.sub("\n", raw)
            if cleaned != raw:
                print(f"Removing managed zellij block from {config}")
                if not dry_run:
                    config.write_text(cleaned.rstrip() + "\n")
        return

    state = json.loads(state_path().read_text())
    restore_backup(state.get("backup", {}), dry_run=dry_run)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="chitta-codex-bootstrap")
    sub = parser.add_subparsers(dest="command", required=True)

    install_p = sub.add_parser("install", help="Clone pinned repos and apply Codex configuration")
    install_p.add_argument("--dry-run", action="store_true", help="Print planned actions without changing anything")

    verify_p = sub.add_parser("verify", help="Run Codex and MCP smoke checks")
    verify_p.add_argument("--dry-run", action="store_true", help="Print planned actions without changing anything")

    rollback_p = sub.add_parser("rollback", help="Restore saved Codex config backup")
    rollback_p.add_argument("--dry-run", action="store_true", help="Print planned actions without changing anything")

    args = parser.parse_args(argv)

    if args.command == "install":
        install(dry_run=args.dry_run)
    elif args.command == "verify":
        if args.dry_run:
            print("Would run: codex doctor, codex mcp list, codex mcp get {chitta,chitta-bridge,zellij-mcp}")
        else:
            verify_installed()
    elif args.command == "rollback":
        rollback(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
