#!/usr/bin/env python3
"""Input parsing helpers for Feishu quote flow."""

from __future__ import annotations

import re

CONTROL_WORDS = {
    "重来": "restart",
    "取消": "cancel",
    "无": "skip",
    "不选": "skip",
}


_ALIAS_MAP = {
    "kds": "厨房KDS",
    "scrm": "企业微信SCRM",
}


def parse_control(text: str) -> str | None:
    token = text.strip()
    return CONTROL_WORDS.get(token)


def _split_tokens(text: str) -> list[str]:
    return [token.strip() for token in re.split(r"[，,、\s]+", text) if token.strip()]


def _normalize_token(token: str) -> str:
    return re.sub(r"\s+", "", token).lower()


def parse_single_choice(text: str, options: list[dict[str, str]]) -> str:
    if not options:
        raise ValueError("当前步骤无可选项")

    token = text.strip()
    if token.isdigit():
        idx = int(token) - 1
        if 0 <= idx < len(options):
            return options[idx]["value"]
        raise ValueError("序号超出可选范围")

    normalized = _normalize_token(token)
    normalized = _normalize_token(_ALIAS_MAP.get(normalized, token))

    for option in options:
        if normalized in {_normalize_token(option["label"]), _normalize_token(option["value"])}:
            return option["value"]

    raise ValueError("未识别到有效选项")


def parse_multi_choice(text: str, options: list[dict[str, str]]) -> list[str]:
    tokens = _split_tokens(text)
    if not tokens:
        return []

    if any(CONTROL_WORDS.get(token) == "skip" for token in tokens):
        return []

    parsed: list[str] = []
    for token in tokens:
        parsed.append(parse_single_choice(token, options))

    # 去重并保持顺序
    return list(dict.fromkeys(parsed))


def extract_prefill_fields(text: str) -> dict:
    result: dict = {}
    content = text.strip()

    if "轻餐" in content:
        result["餐饮类型"] = "轻餐"
    elif "正餐" in content:
        result["餐饮类型"] = "正餐"

    store_match = re.search(r"(\d+)\s*店", content)
    if store_match:
        result["门店数量"] = int(store_match.group(1))

    if "旗舰版" in content:
        result["门店套餐别名"] = "旗舰版"

    # 尽量抽取品牌名称：去掉识别词后保留剩余短语
    brand = re.sub(
        r"(\d+\s*店|轻餐|正餐|旗舰版|开始报价|报价|确认|生成报价|生成|开始生成|无|不选|重来|取消)",
        "",
        content,
    )
    brand = re.sub(r"[，,、\s]+", " ", brand).strip()
    if brand:
        result["客户品牌名称"] = brand

    return result
