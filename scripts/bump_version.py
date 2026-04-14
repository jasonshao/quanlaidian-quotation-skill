#!/usr/bin/env python3
"""Auto bump VERSION and prepend CHANGELOG entry."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path


def parse_version(version: str) -> tuple[int, int, int]:
    parts = version.strip().split('.')
    if len(parts) != 3:
        raise ValueError(f"invalid version: {version}")
    return tuple(int(p) for p in parts)


def format_version(parts: tuple[int, int, int]) -> str:
    return f"{parts[0]}.{parts[1]}.{parts[2]}"


def bump(parts: tuple[int, int, int], part: str) -> tuple[int, int, int]:
    major, minor, patch = parts
    if part == "major":
        return major + 1, 0, 0
    if part == "minor":
        return major, minor + 1, 0
    return major, minor, patch + 1


def update_changelog(changelog_path: Path, new_version: str, message: str, today: str) -> None:
    original = changelog_path.read_text(encoding="utf-8")
    header = "# Changelog\n\n"
    if not original.startswith(header):
        raise ValueError("CHANGELOG.md format not supported")

    entry = (
        f"## {new_version} - {today}\n\n"
        f"- {message}\n\n"
    )

    if f"## {new_version} - {today}" in original:
        return

    updated = original.replace(header, header + entry, 1)
    changelog_path.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump semantic version and update changelog")
    parser.add_argument("--part", choices=["major", "minor", "patch"], default="patch")
    parser.add_argument(
        "--message",
        default="自动版本更新：main 分支有新提交",
        help="changelog bullet message",
    )
    parser.add_argument("--write", action="store_true", help="apply file changes")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    version_path = repo_root / "VERSION"
    changelog_path = repo_root / "CHANGELOG.md"

    old_version = version_path.read_text(encoding="utf-8").strip()
    new_version = format_version(bump(parse_version(old_version), args.part))
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    print(f"old_version={old_version}")
    print(f"new_version={new_version}")

    if not args.write:
        print("dry_run=true")
        return 0

    version_path.write_text(new_version + "\n", encoding="utf-8")
    update_changelog(changelog_path, new_version, args.message, today)
    print("updated=VERSION,CHANGELOG.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
