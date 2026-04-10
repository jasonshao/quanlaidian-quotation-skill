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


def recommend_quote_plan(payload: dict) -> dict:
    return invoke_structured_json(
        system_prompt=(
            "You are an OpenClaw quote planning assistant. "
            "Use the retrieved historical cases to recommend a safer package/module "
            "combination, but do not invent prices or totals."
        ),
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
