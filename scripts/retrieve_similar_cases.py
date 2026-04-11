#!/usr/bin/env python3
"""Retrieve similar historical quote cases using lightweight rules."""

from __future__ import annotations

import argparse
import json
from collections import Counter
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


def _normalize_list(values) -> list[str]:
    if not values:
        return []
    return [str(value).strip() for value in values if str(value).strip()]


def _adjacent_store_band(target_band: str | None, case_band: str | None) -> bool:
    order = ["1-10", "11-50", "51-300", "300+"]
    if target_band not in order or case_band not in order:
        return False
    return abs(order.index(target_band) - order.index(case_band)) == 1


def _text_similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    left_text = str(left).strip()
    right_text = str(right).strip()
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0
    if left_text in right_text or right_text in left_text:
        return 0.7
    left_tokens = {token for token in left_text.replace("+", " ").split() if token}
    right_tokens = {token for token in right_text.replace("+", " ").split() if token}
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = left_tokens & right_tokens
    return len(overlap) / max(len(left_tokens), len(right_tokens))


def _overlap_ratio(left_values, right_values) -> float:
    left = set(_normalize_list(left_values))
    right = set(_normalize_list(right_values))
    if not left or not right:
        return 0.0
    return len(left & right) / max(len(left), len(right))


def score_case(form: dict, case: dict) -> float:
    score = 0.0
    if case.get("raw_extract_status") != "parsed":
        return 0.0

    form_meal_type = form.get("餐饮类型")
    if form_meal_type and form_meal_type == case.get("meal_type"):
        score += 0.35

    form_store_band = store_count_band(form.get("门店数量"))
    case_store_band = case.get("store_count_band")
    if form_store_band and form_store_band == case_store_band:
        score += 0.25
    elif _adjacent_store_band(form_store_band, case_store_band):
        score += 0.12

    package_similarity = _text_similarity(form.get("门店套餐"), case.get("selected_package"))
    score += round(package_similarity * 0.2, 4)

    store_module_overlap = _overlap_ratio(form.get("门店增值模块"), case.get("store_modules"))
    score += round(store_module_overlap * 0.1, 4)

    hq_module_overlap = _overlap_ratio(form.get("总部模块"), case.get("hq_modules"))
    score += round(hq_module_overlap * 0.05, 4)

    if bool(_normalize_list(form.get("总部模块"))) == bool(_normalize_list(case.get("hq_modules"))):
        score += 0.03

    implementation_similarity = _text_similarity(
        form.get("实施服务类型"),
        case.get("implementation_service"),
    )
    score += round(implementation_similarity * 0.02, 4)

    return round(score, 4)


def _build_segment_stats(ranked_cases: list[dict]) -> dict:
    package_counter = Counter()
    module_counter = Counter()
    for item in ranked_cases:
        if item.get("selected_package"):
            package_counter[item["selected_package"]] += 1
        for module_name in item.get("store_modules", []):
            module_counter[module_name] += 1
    return {
        "top_packages": [
            {"name": name, "count": count}
            for name, count in package_counter.most_common(5)
        ],
        "top_modules": [
            {"name": name, "count": count}
            for name, count in module_counter.most_common(8)
        ],
    }


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
                "hq_modules": case.get("hq_modules", []),
                "implementation_service": case.get("implementation_service"),
                "discounted_total": case.get("discounted_total"),
            }
        )
    ranked.sort(
        key=lambda item: (
            item["score"],
            bool(item.get("hq_modules")),
            len(item.get("store_modules", [])),
            item.get("discounted_total") or 0,
        ),
        reverse=True,
    )
    top_ranked = ranked[:top_k]
    return {
        "query_features": {
            "meal_type": form.get("餐饮类型"),
            "store_count_band": store_count_band(form.get("门店数量")),
            "has_hq_module": bool(form.get("总部模块")),
        },
        "retrieved_cases": top_ranked,
        "segment_stats": _build_segment_stats(top_ranked),
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
