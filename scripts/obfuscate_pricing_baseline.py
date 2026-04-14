#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.pricing_baseline_codec import DEFAULT_KEY_ENV, encode_payload


def main(argv=None):
    parser = argparse.ArgumentParser(description="将 pricing baseline JSON 混淆为 .obf 文件")
    parser.add_argument("--input", required=True, help="明文 baseline JSON 路径")
    parser.add_argument("--output", required=True, help="输出 obf 路径")
    parser.add_argument("--key", help=f"混淆密钥（可选；不传则读环境变量 {DEFAULT_KEY_ENV}）")
    args = parser.parse_args(argv)

    secret_key = args.key or os.getenv(DEFAULT_KEY_ENV)
    if not secret_key:
        raise RuntimeError(f"缺少密钥：请传 --key 或设置环境变量 {DEFAULT_KEY_ENV}")

    src = Path(args.input)
    dst = Path(args.output)
    plain = src.read_text(encoding="utf-8")
    payload = encode_payload(plain, secret_key=secret_key)
    dst.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
