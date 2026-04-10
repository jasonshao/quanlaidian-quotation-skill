#!/usr/bin/env python3
"""Retrieve similar historical quote cases using lightweight rules."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def store_count_band(store_count: int | None) -> str | None:
    if store_count is None:
        return None
    if store_count <= 10:
        return "1-10"
    if store_count <= 50:
        return "11-50"
    if store_count <= 300:
        return "51-300"
    return "300+"


def load_casebase(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def score_case(form: dict, case: dict) -> float:
    score = 0.0
    if form.get("餐饮类型") and form.get("餐饮类型") == case.get("meal_type"):
        score += 0.5
    if store_count_band(form.get("门店数量")) == case.get("store_count_band"):
        score += 0.3
    if bool(form.get("总部模块")) == bool(case.get("hq_modules")):
        score += 0.2
    return round(score, 4)


def retrieve_similar_cases(form: dict, casebase: list[dict], top_k: int = 5) -> dict:
    ranked = []
    for case in casebase:
        score = score_case(form, case)
        if score <= 0:
            continue
        ranked.append(
            {
                "case_id": case.get("case_id"),
                "score": score,
                "brand_name": case.get("brand_name"),
                "selected_package": case.get("selected_package"),
                "store_modules": case.get("store_modules", []),
                "discounted_total": case.get("discounted_total"),
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {
        "query_features": {
            "meal_type": form.get("餐饮类型"),
            "store_count_band": store_count_band(form.get("门店数量")),
            "has_hq_module": bool(form.get("总部模块")),
        },
        "retrieved_cases": ranked[:top_k],
        "segment_stats": {
            "top_packages": [],
            "top_modules": [],
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Retrieve similar historical quote cases")
    parser.add_argument("--form", required=True, help="Input form JSON path")
    parser.add_argument("--casebase", required=True, help="JSONL casebase path")
    parser.add_argument("--output", required=True, help="Retrieval result JSON path")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args(argv)

    form = json.loads(Path(args.form).read_text(encoding="utf-8"))
    casebase = load_casebase(Path(args.casebase))
    result = retrieve_similar_cases(form, casebase, top_k=args.top_k)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
