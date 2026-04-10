#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_quotation_config import build_quotation_config
from scripts.feishu_file_delivery import (
    FeishuDeliveryError,
    deliver_files_to_feishu,
    should_send_to_feishu,
)
from scripts.llm_client import OpenClawLLMError
from scripts.retrieve_similar_cases import load_casebase, retrieve_similar_cases
from scripts.recommend_quote_plan import recommend_quote_plan
from scripts.audit_quote_config import audit_quote_config


def today_stamp():
    return datetime.now().strftime("%Y%m%d")


def sanitize_brand_name(name):
    return str(name).strip().replace("/", "-")


def build_output_paths(brand_name, output_dir):
    base_name = f"{sanitize_brand_name(brand_name)}-全来店"
    stamp = today_stamp()
    output_dir = Path(output_dir)
    return (
        output_dir / f"{base_name}-报价配置-{stamp}.json",
        output_dir / f"{base_name}-报价单-{stamp}.pdf",
        output_dir / f"{base_name}-报价单-{stamp}.xlsx",
    )


def build_reasoning_output_path(brand_name, output_dir):
    base_name = f"{sanitize_brand_name(brand_name)}-全来店"
    stamp = today_stamp()
    output_dir = Path(output_dir)
    return output_dir / f"{base_name}-推理结果-{stamp}.json"


def run_generator(config_path, pdf_path, xlsx_path):
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent / "generate_quotation.py"),
        "--config",
        str(config_path),
        "--output",
        str(pdf_path),
        "--output-xlsx",
        str(xlsx_path),
    ]
    subprocess.run(command, check=True)


def ensure_runtime_dependencies():
    missing = []
    for package_name in ("reportlab", "openpyxl", "fontTools"):
        try:
            importlib.import_module(package_name)
        except ModuleNotFoundError:
            missing.append(package_name)
    if missing:
        raise RuntimeError(
            "缺少运行依赖: "
            + ", ".join(missing)
            + "。请先运行: python3 -m pip install -r requirements.txt"
        )


def _calc_item_amount(item: dict):
    price = item.get("标准价", 0)
    if isinstance(price, str):
        return 0
    try:
        return float(price) * float(item.get("折扣", 1)) * float(item.get("数量", 0))
    except Exception:
        return 0


def build_preview_text(form: dict, config: dict) -> str:
    items = config.get("报价项目", [])
    total_amount = sum(_calc_item_amount(item) for item in items)
    lines = [
        "【全来店报价预览】",
        f"品牌：{form.get('客户品牌名称', '')}",
        f"餐饮类型：{form.get('餐饮类型', '')}",
        f"门店数量：{form.get('门店数量', '')}",
        f"门店套餐：{form.get('门店套餐', '')}",
        f"折扣：{form.get('折扣', '按规则推荐')}",
        f"报价项目数：{len(items)}",
        f"预估合计（折后）：{total_amount:.2f}",
        "",
        "主要费用项（最多 5 条）：",
    ]
    for idx, item in enumerate(items[:5], start=1):
        amount = _calc_item_amount(item)
        lines.append(
            f"{idx}. {item.get('商品名称', '')} | 数量={item.get('数量', '')}{item.get('单位', '')} | 折后小计={amount:.2f}"
        )
    return "\n".join(lines)


def merge_form_patch(form: dict, patch: Optional[dict]) -> dict:
    merged = dict(form)
    if not patch:
        return merged
    for key, value in patch.items():
        if value is None:
            continue
        merged[key] = value
    return merged


def build_recommendation_payload(form: dict, retrieval: dict) -> dict:
    return {
        "form": form,
        "retrieved_cases": retrieval,
    }


def build_audit_payload(final_form: dict, quote_config: dict, retrieval: dict) -> dict:
    return {
        "final_form": final_form,
        "quote_config": quote_config,
        "retrieved_cases": retrieval,
    }


def run_reasoning_pipeline(form: dict, casebase: Optional[list[dict]] = None) -> dict:
    retrieval = {
        "query_features": {
            "meal_type": form.get("餐饮类型"),
            "store_count_band": None,
            "has_hq_module": bool(form.get("总部模块")),
        },
        "retrieved_cases": [],
        "segment_stats": {"top_packages": [], "top_modules": []},
    }
    if casebase:
        retrieval = retrieve_similar_cases(form, casebase, top_k=5)

    recommendation = {
        "status": "skipped",
        "recommended_form_patch": {},
        "message": "reasoning not attempted",
    }
    final_form = dict(form)

    if retrieval.get("retrieved_cases"):
        try:
            recommend_result = recommend_quote_plan(build_recommendation_payload(form, retrieval))
            recommendation = dict(recommend_result)
            recommendation["status"] = "applied"
            final_form = merge_form_patch(form, recommend_result.get("recommended_form_patch", {}))
        except OpenClawLLMError as exc:
            recommendation = {
                "status": "skipped",
                "recommended_form_patch": {},
                "message": str(exc),
            }

    audit = {
        "status": "skipped",
        "issues": [],
        "suggested_adjustments": [],
        "chat_summary": "未启用模型审单。",
    }
    if recommendation.get("status") == "applied":
        try:
            audit = audit_quote_config(
                build_audit_payload(final_form, {"报价项目": []}, retrieval)
            )
        except OpenClawLLMError as exc:
            audit = {
                "status": "skipped",
                "issues": [],
                "suggested_adjustments": [],
                "chat_summary": f"模型审单未执行：{exc}",
            }
    return {
        "input_form": dict(form),
        "retrieval": retrieval,
        "recommendation": recommendation,
        "final_form": final_form,
        "audit": audit,
    }


def write_reasoning_result(brand_name: str, output_dir, reasoning_result: dict) -> Path:
    output_path = build_reasoning_output_path(brand_name, output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(reasoning_result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path


def generate_outputs(form_path, output_dir):
    ensure_runtime_dependencies()
    form = json.loads(Path(form_path).read_text(encoding="utf-8"))
    casebase_path = Path(__file__).resolve().parent.parent / "data" / "history_quote_cases.jsonl"
    casebase = load_casebase(casebase_path) if casebase_path.exists() else []
    reasoning_result = run_reasoning_pipeline(form, casebase)
    final_form = reasoning_result["final_form"]
    config = build_quotation_config(final_form)
    reasoning_result["quote_config"] = config

    if reasoning_result["recommendation"].get("status") == "applied":
        try:
            reasoning_result["audit"] = audit_quote_config(
                build_audit_payload(final_form, config, reasoning_result["retrieval"])
            )
        except OpenClawLLMError as exc:
            reasoning_result["audit"] = {
                "status": "skipped",
                "issues": [],
                "suggested_adjustments": [],
                "chat_summary": f"模型审单未执行：{exc}",
            }

    config_path, pdf_path, xlsx_path = build_output_paths(final_form["客户品牌名称"], output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    run_generator(config_path, pdf_path, xlsx_path)
    reasoning_path = write_reasoning_result(final_form["客户品牌名称"], output_dir, reasoning_result)
    return final_form, config, config_path, pdf_path, xlsx_path, reasoning_result, reasoning_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="OpenClaw 全来店报价主入口")
    parser.add_argument("--form", required=True, help="业务表单 JSON 路径")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    parser.add_argument(
        "--send-to-feishu",
        action="store_true",
        help="生成后自动上传到飞书并发送文件消息（也可通过 FEISHU_SEND_FILES=1 开启）",
    )
    args = parser.parse_args(argv)

    form, config, config_path, pdf_path, xlsx_path, reasoning_result, reasoning_path = generate_outputs(
        args.form,
        args.output_dir,
    )

    preview_text = build_preview_text(form, config)
    print(preview_text)
    print("\n文件下载入口（本地路径）：")
    print(f"- PDF报价单：{pdf_path}")
    print(f"- Excel报价单：{xlsx_path}")
    print(f"- JSON配置文件：{config_path}")
    print(f"- 推理结果JSON：{reasoning_path}")
    if reasoning_result["recommendation"].get("status") == "applied":
        print("\n方案推荐：已使用 OpenClaw 配置的模型进行推荐补全。")
    elif reasoning_result["recommendation"].get("message"):
        print(f"\n方案推荐：{reasoning_result['recommendation']['message']}")
    if reasoning_result["audit"].get("chat_summary"):
        print(f"审单结果：{reasoning_result['audit']['chat_summary']}")

    if should_send_to_feishu(explicit_flag=args.send_to_feishu):
        try:
            results = deliver_files_to_feishu(
                [pdf_path, xlsx_path, config_path],
                preview_text=preview_text,
            )
            print("\n飞书文件消息发送成功：")
            for item in results:
                print(
                    f"- {item['file_name']} | file_key={item['file_key']} | message_id={item['message_id']}"
                )
            print("用户可在飞书对话中直接点击文件消息下载。")
        except FeishuDeliveryError as exc:
            print(f"\n[警告] 飞书发送失败：{exc}")
            if args.send_to_feishu:
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
