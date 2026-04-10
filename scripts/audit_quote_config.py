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


def audit_quote_config(payload: dict) -> dict:
    return invoke_structured_json(
        system_prompt=(
            "You are an OpenClaw quote auditor. Review the generated quote config "
            "against retrieved historical cases and return risks or suggested adjustments. "
            "Do not recalculate the official quote amount."
        ),
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
