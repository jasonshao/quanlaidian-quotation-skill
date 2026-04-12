#!/usr/bin/env python3
"""CLI wrapper for Feishu quote conversational flow."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.feishu_quote_flow import handle_quote_message

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SESSION_DIR = ROOT_DIR / "data" / "feishu_quote_sessions"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Handle one Feishu quote message turn")
    parser.add_argument("--chat-id", required=True, help="Feishu chat_id")
    parser.add_argument("--user-id", required=True, help="Feishu user id")
    parser.add_argument("--text", required=True, help="Incoming message text")
    parser.add_argument("--session-dir", default=str(DEFAULT_SESSION_DIR), help="Session storage directory")
    parser.add_argument("--output-dir", default=".", help="Quotation output directory")
    args = parser.parse_args(argv)

    result = handle_quote_message(
        chat_id=args.chat_id,
        user_id=args.user_id,
        text=args.text,
        session_dir=Path(args.session_dir),
        output_dir=Path(args.output_dir),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
