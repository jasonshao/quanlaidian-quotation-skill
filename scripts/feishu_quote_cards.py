#!/usr/bin/env python3
"""Static Feishu cards for quote wizard."""

from __future__ import annotations


def build_summary_markdown(summary: dict) -> str:
    lines: list[str] = []
    ordered_keys = [
        "客户品牌名称",
        "餐饮类型",
        "门店数量",
        "门店套餐",
        "门店增值模块",
        "总部模块",
        "配送中心数量",
        "生产加工中心数量",
    ]
    for key in ordered_keys:
        value = summary.get(key)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = "、".join(value)
        lines.append(f"- {key}：{value}")
    return "\n".join(lines) if lines else "- 暂无已选信息"


def _options_markdown(options: list[dict[str, str]]) -> str:
    if not options:
        return "- 直接回复文本输入"
    lines = [f"{idx}. {item['label']}" for idx, item in enumerate(options, start=1)]
    return "\n".join(lines)


def _build_card(title: str, prompt: str, options: list[dict[str, str]], summary: dict, examples: list[str]) -> dict:
    example_text = " / ".join(examples)
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": prompt}},
            {"tag": "div", "text": {"tag": "lark_md", "content": _options_markdown(options)}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"**已选摘要**\n{build_summary_markdown(summary)}"}},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": f"回复示例：{example_text}"}]},
        ],
    }


def build_single_select_card(
    title: str,
    prompt: str,
    options: list[dict[str, str]],
    summary: dict,
    examples: list[str],
) -> dict:
    return _build_card(title, prompt, options, summary, examples)


def build_multi_select_card(
    title: str,
    prompt: str,
    options: list[dict[str, str]],
    summary: dict,
    examples: list[str] | None = None,
) -> dict:
    final_examples = examples or ["1,3", "厨房KDS, 成本管理", "1, 成本管理", "无"]
    return _build_card(title, prompt, options, summary, final_examples)


def build_input_card(title: str, prompt: str, summary: dict, examples: list[str]) -> dict:
    return _build_card(title, prompt, [], summary, examples)


def build_confirm_card(summary: dict) -> dict:
    return _build_card(
        title="确认生成报价",
        prompt="请确认当前配置，回复 `确认` 或 `生成报价` 开始出单。",
        options=[],
        summary=summary,
        examples=["确认", "生成报价", "重来"],
    )


def build_error_card(reason: str, options: list[dict[str, str]], summary: dict) -> dict:
    return _build_card(
        title="输入未识别",
        prompt=f"{reason}\n请按候选项重新回复。",
        options=options,
        summary=summary,
        examples=["1", "1,3", "无"],
    )
