#!/usr/bin/env python3
"""Extract normalized quote cases from historical Excel files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator


def iter_excel_files(history_root: Path) -> Iterator[Path]:
    for path in sorted(history_root.rglob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        yield path


def infer_brand_name(path: Path) -> str:
    stem = path.stem
    for token in ("报价单", "对客报价", "报价", "确认单", "供应链"):
        stem = stem.replace(token, "")
    return stem.strip("-_（）() ") or path.parent.name


def build_case_stub(path: Path) -> dict:
    return {
        "case_id": path.stem,
        "source_file": str(path),
        "brand_name": infer_brand_name(path),
        "meal_type": None,
        "quote_kind": None,
        "store_count": None,
        "store_count_band": None,
        "selected_package": None,
        "store_modules": [],
        "hq_modules": [],
        "implementation_service": None,
        "discounted_total": None,
        "line_items": [],
        "notes": [],
        "raw_extract_status": "stub_only",
    }


def extract_history_casebase(history_root: Path) -> list[dict]:
    return [build_case_stub(path) for path in iter_excel_files(history_root)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Extract historical quote casebase")
    parser.add_argument("--history-root", required=True, help="Root directory of historical quotes")
    parser.add_argument("--output", required=True, help="JSONL output path")
    args = parser.parse_args(argv)

    history_root = Path(args.history_root).resolve()
    cases = extract_history_casebase(history_root)
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as fh:
        for item in cases:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
