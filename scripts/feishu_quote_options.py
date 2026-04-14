#!/usr/bin/env python3
"""Feishu quote option helpers."""

from __future__ import annotations

from scripts.build_quotation_config import load_product_catalog

DEFAULT_PACKAGE_MAP = {
    "轻餐": "轻餐连锁营销基础版",
    "正餐": "正餐连锁营销基础版",
}

SUPPORTED_HQ_MODULES = {
    "配送中心",
    "生产加工",
    "企业微信SCRM",
    "商家小程序号",
    "商家小程序号-品牌点位",
}


def _validate_meal_type(meal_type: str) -> None:
    if meal_type not in {"轻餐", "正餐"}:
        raise ValueError("餐饮类型必须为轻餐或正餐")


def _options_for(group: str, meal_type: str) -> list[dict[str, str]]:
    _validate_meal_type(meal_type)
    products = load_product_catalog()
    options: list[dict[str, str]] = []
    seen: set[str] = set()

    for product in products:
        if product["group"] != group:
            continue
        if product["meal_type"] not in {meal_type, "通用"}:
            continue
        name = product["name"]
        if name in seen:
            continue
        seen.add(name)
        options.append({"value": name, "label": name})
    return options


def get_default_package_value(meal_type: str) -> str:
    _validate_meal_type(meal_type)
    return DEFAULT_PACKAGE_MAP[meal_type]


def get_package_options(meal_type: str) -> list[dict[str, str]]:
    value = get_default_package_value(meal_type)
    return [{"value": value, "label": "旗舰版"}]


def get_store_module_options(meal_type: str) -> list[dict[str, str]]:
    return _options_for("门店增值模块", meal_type)


def get_headquarter_module_options(meal_type: str) -> list[dict[str, str]]:
    raw = _options_for("总部模块", meal_type)
    return [item for item in raw if item["value"] in SUPPORTED_HQ_MODULES]
