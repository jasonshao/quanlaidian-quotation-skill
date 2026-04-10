#!/usr/bin/env python3
"""Check whether this skill has a newer GitHub release and optionally update local checkout.

Usage:
  python3 scripts/check_openclaw_update.py
  python3 scripts/check_openclaw_update.py --apply

Environment variables:
  SKILL_REPO        default: jasonshao/quanlaidian-quotation-skill
  SKILL_LOCAL_DIR   default: current repo root (auto-detected)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path


def _run(cmd: list[str], cwd: Path) -> str:
    return subprocess.check_output(cmd, cwd=str(cwd), text=True).strip()


def _parse_version(text: str) -> tuple[int, int, int]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    if not m:
        raise ValueError(f"invalid version: {text}")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _get_repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _read_local_version(repo_root: Path) -> str:
    version_file = repo_root / "VERSION"
    if not version_file.exists():
        return "0.0.0"
    return version_file.read_text(encoding="utf-8").strip()


def _latest_release_tag(repo: str) -> str | None:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-skill-updater"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return payload.get("tag_name")
    except Exception:
        return None


def _latest_tag(repo: str) -> str | None:
    url = f"https://api.github.com/repos/{repo}/tags?per_page=1"
    req = urllib.request.Request(url, headers={"User-Agent": "openclaw-skill-updater"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
        if not payload:
            return None
        return payload[0].get("name")


def _normalize_tag(tag: str) -> str:
    return tag[1:] if tag.startswith("v") else tag


def check_and_optionally_update(repo_root: Path, repo: str, apply_update: bool) -> int:
    local_version = _read_local_version(repo_root)
    latest = _latest_release_tag(repo) or _latest_tag(repo)
    if not latest:
        print("[update-check] 未获取到远端版本信息")
        return 1

    latest_version = _normalize_tag(latest)
    print(f"[update-check] local={local_version} remote={latest_version}")

    if _parse_version(local_version) >= _parse_version(latest_version):
        print("[update-check] 当前已是最新版本")
        return 0

    print("[update-check] 检测到新版本")
    if not apply_update:
        print("[update-check] 仅检查模式，未执行更新。可加 --apply 自动更新")
        return 2

    # Safe update path: fast-forward pull from main.
    _run(["git", "fetch", "origin", "main"], cwd=repo_root)
    _run(["git", "pull", "--ff-only", "origin", "main"], cwd=repo_root)
    print("[update-check] 已更新到最新 main，请按需重载 OpenClaw 技能")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Check and update OpenClaw skill from GitHub")
    parser.add_argument("--apply", action="store_true", help="apply update when newer version exists")
    args = parser.parse_args()

    repo_root = Path(os.getenv("SKILL_LOCAL_DIR", str(_get_repo_root()))).resolve()
    repo = os.getenv("SKILL_REPO", "jasonshao/quanlaidian-quotation-skill")

    try:
        return check_and_optionally_update(repo_root, repo, args.apply)
    except subprocess.CalledProcessError as e:
        print(f"[update-check] git command failed: {e}")
        return 1
    except Exception as e:
        print(f"[update-check] failed: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
