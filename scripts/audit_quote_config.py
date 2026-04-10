#!/usr/bin/env python3
"""Use the OpenClaw-configured model to audit the final quote config."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.llm_client import invoke_structured_json


def load_schema() -> dict:
    schema_path = Path(__file__).resolve().parent.parent / "references" / "reasoning_schemas" / "quote_audit.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def build_system_prompt() -> str:
    return (
        "你是 OpenClaw 里的连锁餐饮售前审单助手。"
        "请审查最终报价方案是否存在漏配、错配、折扣风险、说明不足或与历史相似案例明显偏离。"
        "不要改官方计算价格，但要指出业务风险和建议调整项。"
        "忽略硬件，不要把硬件作为必须项。"
        "输出要面向销售同事，结论清晰，优先发现风险。"
    )


def audit_quote_config(payload: dict) -> dict:
    return invoke_structured_json(
        system_prompt=build_system_prompt(),
        user_payload=payload,
        response_schema=load_schema(),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit quote config with OpenClaw model")
    parser.add_argument("--input", required=True, help="Audit payload JSON path")
    parser.add_argument("--output", required=True, help="Audit result JSON path")
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = audit_quote_config(payload)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
