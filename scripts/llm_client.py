#!/usr/bin/env python3
"""OpenClaw-hosted LLM client wrapper.

This module does not hardcode a model vendor. In production, the surrounding
OpenClaw runtime is expected to inject model configuration through environment
variables based on the model selected for the Skill.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from typing import Any


class OpenClawLLMError(RuntimeError):
    """Raised when the OpenClaw-provided model runtime is unavailable."""


@dataclass
class OpenClawModelConfig:
    model_name: str
    api_base: str
    api_key: str

    @classmethod
    def from_env(cls) -> "OpenClawModelConfig":
        """Load model configuration injected by the OpenClaw runtime."""
        model_name = os.getenv("OPENCLAW_MODEL_NAME", "").strip()
        api_base = os.getenv("OPENCLAW_MODEL_API_BASE", "").strip()
        api_key = os.getenv("OPENCLAW_MODEL_API_KEY", "").strip()
        missing = [
            name
            for name, value in (
                ("OPENCLAW_MODEL_NAME", model_name),
                ("OPENCLAW_MODEL_API_BASE", api_base),
                ("OPENCLAW_MODEL_API_KEY", api_key),
            )
            if not value
        ]
        if missing:
            raise OpenClawLLMError(
                "OpenClaw model config is missing: " + ", ".join(missing)
            )
        return cls(model_name=model_name, api_base=api_base, api_key=api_key)


def invoke_structured_json(
    *,
    system_prompt: str,
    user_payload: dict[str, Any],
    response_schema: dict[str, Any],
) -> dict[str, Any]:
    """Ask the OpenClaw-configured model for a structured JSON response.

    The API shape here is intentionally thin and vendor-neutral. It assumes the
    OpenClaw runtime exposes a JSON endpoint compatible with:
    POST {api_base}/v1/responses
    """
    cfg = OpenClawModelConfig.from_env()
    request_body = {
        "model": cfg.model_name,
        "input": [
            {"role": "system", "content": [{"type": "text", "text": system_prompt}]},
            {
                "role": "user",
                "content": [{"type": "text", "text": json.dumps(user_payload, ensure_ascii=False)}],
            },
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "structured_response", "schema": response_schema},
        },
    }
    req = urllib.request.Request(
        f"{cfg.api_base.rstrip('/')}/v1/responses",
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise OpenClawLLMError(f"OpenClaw model invocation failed: {exc}") from exc

    if "output_text" in payload:
        return json.loads(payload["output_text"])
    raise OpenClawLLMError(f"Unexpected OpenClaw model response: {payload}")
