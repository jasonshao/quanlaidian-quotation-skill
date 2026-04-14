#!/usr/bin/env python3
import argparse
import importlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.build_quotation_config import build_quotation_config
from scripts.feishu_file_delivery import (
    FeishuCredentialMissing,
    FeishuDeliveryError,
    deliver_files_to_feishu,
    should_send_to_feishu,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_COST_DATA_PATH = ROOT_DIR / "references" / "pricing_baseline_v5.json"
DEFAULT_COST_DATA_OBF_PATH = ROOT_DIR / "references" / "pricing_baseline_v5.obf"


def resolve_cost_data_path():
    if DEFAULT_COST_DATA_OBF_PATH.exists():
        return DEFAULT_COST_DATA_OBF_PATH
    return DEFAULT_COST_DATA_PATH


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


def run_generator(config_path, pdf_path, xlsx_path):
    cost_data_path = resolve_cost_data_path()
    command = [
        sys.executable,
        str(Path(__file__).resolve().parent / "generate_quotation.py"),
        "--config",
        str(config_path),
        "--output",
        str(pdf_path),
        "--output-xlsx",
        str(xlsx_path),
        "--profit",
        "--cost-data",
        str(cost_data_path),
    ]
    subprocess.run(command, check=True)


def _extract_item_factor(item: dict) -> float:
    if item.get("deal_price_factor") is not None:
        return float(item.get("deal_price_factor"))
    if item.get("成交价系数") is not None:
        return float(item.get("成交价系数"))
    if item.get("折扣") is not None:
        return 1 - float(item.get("折扣"))
    return 1.0


def _calc_item_subtotal(item: dict) -> float:
    if item.get("报价小计") is not None:
        return float(item.get("报价小计"))
    unit_price = item.get("商品单价")
    qty = float(item.get("数量", 0))
    if unit_price is not None:
        return float(unit_price) * qty
    std_price = item.get("标准价")
    if std_price is None:
        return 0.0
    return float(std_price) * _extract_item_factor(item) * qty


def build_preview_text(form: dict, config: dict) -> str:
    modules = form.get("门店增值模块") or []
    hq_modules = form.get("总部模块") or []
    hq_text_parts = []
    if "配送中心" in hq_modules:
        hq_text_parts.append(f"配送中心（{int(form.get('配送中心数量', 0) or 0)}个）")
    if "生产加工" in hq_modules:
        hq_text_parts.append(f"生产加工（{int(form.get('生产加工中心数量', 0) or 0)}个）")
    for module in hq_modules:
        if module not in {"配送中心", "生产加工"}:
            hq_text_parts.append(module)
    hq_text = "、".join(hq_text_parts) if hq_text_parts else "无"

    items = config.get("报价项目", [])
    total_amount = sum(_calc_item_subtotal(item) for item in items)
    lines = [
        "报价单生成成功！",
        "配置摘要：",
        f"客户品牌：{form.get('客户品牌名称', '')}",
        f"餐饮类型：{form.get('餐饮类型', '')}",
        f"门店数量：{form.get('门店数量', '')}",
        f"门店套餐：{form.get('门店套餐', '')}",
        f"门店增值模块：{'、'.join(modules) if modules else '无'}",
        f"总部模块：{hq_text}",
        f"报价项目数：{len(items)}",
        f"预估合计：{total_amount:.2f}",
    ]
    return "\n".join(lines)


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


def generate_outputs(form_path, output_dir):
    ensure_runtime_dependencies()
    form = json.loads(Path(form_path).read_text(encoding="utf-8"))
    config = build_quotation_config(form)
    config_path, pdf_path, xlsx_path = build_output_paths(form["客户品牌名称"], output_dir)
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    run_generator(config_path, pdf_path, xlsx_path)
    return config_path, pdf_path, xlsx_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="OpenClaw 全来店报价主入口")
    parser.add_argument("--form", required=True, help="业务表单 JSON 路径")
    parser.add_argument("--output-dir", default=".", help="输出目录")
    parser.add_argument(
        "--send-to-feishu",
        action="store_true",
        help="生成后发送到飞书文件消息（也可通过 FEISHU_SEND_FILES=1 开启）",
    )
    parser.add_argument(
        "--feishu-chat-id",
        default="",
        help="飞书聊天 chat_id（优先于 FEISHU_RECEIVE_ID）",
    )
    parser.add_argument(
        "--feishu-receive-id-type",
        default="chat_id",
        help="飞书 receive_id_type，默认 chat_id",
    )
    args = parser.parse_args(argv)

    form = json.loads(Path(args.form).read_text(encoding="utf-8"))
    config_path, pdf_path, xlsx_path = generate_outputs(args.form, args.output_dir)
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    preview_text = build_preview_text(form, config)

    feishu_chat_id = args.feishu_chat_id.strip()
    send_mode = should_send_to_feishu(
        explicit_flag=args.send_to_feishu,
        receive_id=feishu_chat_id,
    )
    if send_mode:
        strict_mode = args.send_to_feishu or bool(feishu_chat_id)
        try:
            results = deliver_files_to_feishu(
                [pdf_path, xlsx_path, config_path],
                preview_text=preview_text
                + "\n\n报价文件将以飞书文件消息发送，请直接点击文件下载。",
                receive_id=feishu_chat_id or None,
                receive_id_type=args.feishu_receive_id_type,
            )
            print("报价文件已发送到飞书，请直接点击文件消息下载。")
            for item in results:
                print(f"- {item['file_name']} | message_id={item['message_id']}")
            return 0
        except FeishuCredentialMissing as exc:
            # 飞书凭据缺失，复制文件到 OpenClaw 可访问的目录，优雅降级
            import shutil
            accessible_dir = Path("/home/gem/workspace/agent/workspace/files")
            accessible_dir.mkdir(parents=True, exist_ok=True)
            accessible_paths = []
            for p in [pdf_path, xlsx_path, config_path]:
                dest = accessible_dir / p.name
                shutil.copy2(p, dest)
                accessible_paths.append(dest)
            print(f"[警告] 飞书发送凭据未配置（{exc})，文件已复制到 OpenClaw 可访问目录。")
            print(preview_text)
            print("\n生成的文件（OpenClaw 飞书工具可直接发送）：")
            for p in accessible_paths:
                print(f"  {p}")
            print("\n请使用 OpenClaw 飞书消息工具发送以上文件。")
            return 0
        except FeishuDeliveryError as exc:
            print(f"[错误] 飞书发送失败：{exc}")
            if strict_mode:
                return 1
            print("已回落为本地文件输出，请在输出目录查看。")

    print(preview_text)
    print("\n生成的文件（本地路径）：")
    print(f"📄 PDF报价单：{pdf_path}")
    print(f"📊 Excel报价单：{xlsx_path}")
    print(f"⚙️ 配置JSON：{config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
