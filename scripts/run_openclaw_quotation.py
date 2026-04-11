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

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_COST_DATA_PATH = ROOT_DIR / "references" / "pricing_baseline_v5.json"


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
        str(DEFAULT_COST_DATA_PATH),
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
    args = parser.parse_args(argv)

    generate_outputs(args.form, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
