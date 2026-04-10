#!/usr/bin/env python3
"""Use the OpenClaw-configured model to recommend a quote plan patch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.llm_client import invoke_structured_json


def load_schema() -> dict:
    schema_path = Path(__file__).resolve().parent.parent / "references" / "reasoning_schemas" / "recommended_quote_plan.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def build_system_prompt() -> str:
    return (
        "你是 OpenClaw 里的连锁餐饮售前报价助手。"
        "你的任务不是重新计算价格，而是参考历史报价案例，给出更像真实售前会选择的套餐、门店增值模块、总部模块与实施建议。"
        "请重点关注门店规模、轻餐/正餐、是否涉及供应链与总部模块、历史常见组合、是否存在漏配。"
        "不要改价格、不要发明产品、不要把硬件加入推荐方案。"
        "如果历史案例不足，请保守输出，并把 needs_human_review 设为 true。"
        "除了主推荐方案，请额外给出 alternative_options，方便销售根据预算切换。"
    )


def recommend_quote_plan(payload: dict) -> dict:
    return invoke_structured_json(
        system_prompt=build_system_prompt(),
        user_payload=payload,
        response_schema=load_schema(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recommend quote plan patch with OpenClaw model")
    parser.add_argument("--input", required=True, help="Recommendation payload JSON path")
    parser.add_argument("--output", required=True, help="Recommendation result JSON path")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = recommend_quote_plan(payload)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
