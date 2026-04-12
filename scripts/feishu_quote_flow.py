#!/usr/bin/env python3
"""Feishu quote conversational flow orchestration."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.feishu_file_delivery import FeishuClient
from scripts.feishu_quote_cards import (
    build_confirm_card,
    build_error_card,
    build_input_card,
    build_multi_select_card,
    build_single_select_card,
)
from scripts.feishu_quote_options import (
    get_default_package_value,
    get_headquarter_module_options,
    get_store_module_options,
)
from scripts.feishu_quote_parser import (
    extract_prefill_fields,
    parse_control,
    parse_multi_choice,
    parse_single_choice,
)
from scripts.feishu_quote_session import FeishuQuoteSessionStore
from scripts.run_openclaw_quotation import generate_outputs

START_WORDS = {"开始", "开始报价", "报价", "我要报价", "生成报价单"}
CONFIRM_WORDS = {"确认", "生成", "生成报价", "开始生成"}


def _parse_positive_int(text: str, field_name: str) -> int:
    value = int(str(text).strip())
    if value <= 0:
        raise ValueError(f"{field_name}必须大于0")
    return value


def _ensure_default_package(form_data: dict) -> None:
    meal_type = form_data.get("餐饮类型")
    if meal_type and not form_data.get("门店套餐"):
        form_data["门店套餐"] = get_default_package_value(meal_type)


def _next_step(form_data: dict) -> str:
    if not form_data.get("客户品牌名称"):
        return "await_brand_name"
    if not form_data.get("餐饮类型"):
        return "await_meal_type"
    if not form_data.get("门店数量"):
        return "await_store_count"
    if "门店增值模块" not in form_data:
        return "await_store_modules"
    if "总部模块" not in form_data:
        return "await_hq_modules"
    if "配送中心" in form_data.get("总部模块", []) and not form_data.get("配送中心数量"):
        return "await_delivery_center_count"
    if "生产加工" in form_data.get("总部模块", []) and not form_data.get("生产加工中心数量"):
        return "await_production_center_count"
    return "await_confirm_generate"


def _step_options(step: str, form_data: dict) -> list[dict[str, str]]:
    if step == "await_meal_type":
        return [{"value": "轻餐", "label": "轻餐"}, {"value": "正餐", "label": "正餐"}]
    if step == "await_store_modules":
        return get_store_module_options(form_data["餐饮类型"])
    if step == "await_hq_modules":
        return get_headquarter_module_options(form_data["餐饮类型"])
    return []


def build_step_card(step: str, form_data: dict) -> dict:
    if step == "await_brand_name":
        return build_input_card(
            title="第1步：品牌名称",
            prompt="请回复客户品牌名称。",
            summary=form_data,
            examples=["黑马汇"],
        )
    if step == "await_meal_type":
        return build_single_select_card(
            title="第2步：餐饮类型",
            prompt="餐饮类型是轻餐还是正餐？",
            options=_step_options(step, form_data),
            summary=form_data,
            examples=["1", "正餐"],
        )
    if step == "await_store_count":
        return build_input_card(
            title="第3步：门店数量",
            prompt="请回复门店数量（1~30）。",
            summary=form_data,
            examples=["10"],
        )
    if step == "await_store_modules":
        return build_multi_select_card(
            title="第4步：门店增值模块",
            prompt="门店增值模块需要哪些？支持数字、中文或混合回复。",
            options=_step_options(step, form_data),
            summary=form_data,
        )
    if step == "await_hq_modules":
        return build_multi_select_card(
            title="第5步：总部模块",
            prompt="总部模块需要哪些？支持数字、中文或混合回复。",
            options=_step_options(step, form_data),
            summary=form_data,
        )
    if step == "await_delivery_center_count":
        return build_input_card(
            title="第6步：配送中心数量",
            prompt="你选择了配送中心，请回复配送中心数量。",
            summary=form_data,
            examples=["1"],
        )
    if step == "await_production_center_count":
        return build_input_card(
            title="第7步：生产加工中心数量",
            prompt="你选择了生产加工，请回复生产加工中心数量。",
            summary=form_data,
            examples=["1"],
        )
    if step == "await_confirm_generate":
        return build_confirm_card(form_data)

    return build_input_card(
        title="报价向导",
        prompt="请继续回复当前步骤所需信息。",
        summary=form_data,
        examples=["确认"],
    )


def send_card(chat_id: str, card: dict) -> str:
    client = FeishuClient.from_env(receive_id=chat_id, receive_id_type="chat_id")
    token = client.get_tenant_access_token()
    return client.send_card_message(token, card)


def send_step_card(session: dict) -> str:
    card = build_step_card(session["current_step"], session["form_data"])
    return send_card(session["chat_id"], card)


def send_quote_result(chat_id: str, form_data: dict, output_paths: tuple) -> None:
    client = FeishuClient.from_env(receive_id=chat_id, receive_id_type="chat_id")
    token = client.get_tenant_access_token()
    summary = (
        "报价已生成\n"
        f"品牌：{form_data.get('客户品牌名称')}\n"
        f"餐饮类型：{form_data.get('餐饮类型')}\n"
        f"门店数量：{form_data.get('门店数量')}\n"
        f"门店套餐：{form_data.get('门店套餐')}"
    )
    client.send_text_message(token, summary)
    for path in output_paths:
        file_key = client.upload_file(token, Path(path))
        client.send_file_message(token, file_key)


def _apply_step_input(step: str, text: str, form_data: dict) -> None:
    if step == "await_brand_name":
        if text not in START_WORDS:
            form_data["客户品牌名称"] = text
        return

    if step == "await_meal_type":
        form_data["餐饮类型"] = parse_single_choice(text, _step_options(step, form_data))
        _ensure_default_package(form_data)
        return

    if step == "await_store_count":
        form_data["门店数量"] = _parse_positive_int(text, "门店数量")
        return

    if step == "await_store_modules":
        form_data["门店增值模块"] = parse_multi_choice(text, _step_options(step, form_data))
        return

    if step == "await_hq_modules":
        form_data["总部模块"] = parse_multi_choice(text, _step_options(step, form_data))
        return

    if step == "await_delivery_center_count":
        form_data["配送中心数量"] = _parse_positive_int(text, "配送中心数量")
        return

    if step == "await_production_center_count":
        form_data["生产加工中心数量"] = _parse_positive_int(text, "生产加工中心数量")
        return


def _normalize_form_data(form_data: dict) -> dict:
    payload = dict(form_data)
    payload.setdefault("门店增值模块", [])
    payload.setdefault("总部模块", [])
    return payload


def handle_quote_message(
    chat_id: str,
    user_id: str,
    text: str,
    session_dir: Path,
    output_dir: Path,
) -> dict:
    incoming = str(text or "").strip()
    store = FeishuQuoteSessionStore(Path(session_dir))

    control = parse_control(incoming)
    if control == "cancel":
        store.clear(chat_id, user_id)
        card = build_input_card("报价已取消", "已取消当前报价流程。回复 `开始报价` 可重新开始。", {}, ["开始报价"])
        send_card(chat_id, card)
        return {"current_step": "cancelled", "form_data": {}}
    if control == "restart":
        store.clear(chat_id, user_id)

    session = store.load(chat_id, user_id) or store.new_session(chat_id, user_id)
    form_data = session.get("form_data", {})

    prefill = extract_prefill_fields(incoming)
    applied_prefill = False
    for key, value in prefill.items():
        if key == "门店套餐别名":
            continue
        if key == "客户品牌名称":
            if incoming in START_WORDS:
                continue
            if form_data.get("客户品牌名称"):
                continue
        if key in {"餐饮类型", "门店数量"} and form_data.get(key):
            continue
        form_data[key] = value
        applied_prefill = True

    if prefill.get("门店套餐别名") == "旗舰版" and form_data.get("餐饮类型"):
        form_data["门店套餐"] = get_default_package_value(form_data["餐饮类型"])

    _ensure_default_package(form_data)

    step = _next_step(form_data)

    if incoming and not applied_prefill:
        try:
            _apply_step_input(step, incoming, form_data)
        except Exception as exc:
            error_card = build_error_card(str(exc), _step_options(step, form_data), form_data)
            send_card(chat_id, error_card)
            session["current_step"] = step
            session["form_data"] = form_data
            session["last_card_type"] = "error"
            store.save(session)
            return {"current_step": step, "form_data": form_data, "error": str(exc)}

    _ensure_default_package(form_data)

    if form_data.get("门店数量", 0) > 30:
        store.clear(chat_id, user_id)
        card = build_input_card(
            title="超出自动报价范围",
            prompt="31店及以上暂不受理自动报价，请转人工定价。",
            summary=form_data,
            examples=["开始报价"],
        )
        send_card(chat_id, card)
        return {"current_step": "unsupported", "reason": "store_count_gt_30", "form_data": form_data}

    next_step = _next_step(form_data)

    if next_step == "await_confirm_generate" and incoming in CONFIRM_WORDS:
        payload = _normalize_form_data(form_data)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        form_path = out_dir / f"{chat_id}__{user_id}.form.json"
        form_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        output_paths = generate_outputs(str(form_path), str(out_dir))
        send_quote_result(chat_id, payload, output_paths)
        store.clear(chat_id, user_id)
        return {
            "current_step": "completed",
            "form_data": payload,
            "outputs": [str(p) for p in output_paths],
        }

    session["current_step"] = next_step
    session["form_data"] = form_data
    session["last_card_type"] = next_step
    store.save(session)
    send_step_card(session)
    return {"current_step": next_step, "form_data": form_data}
