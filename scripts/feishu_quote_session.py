#!/usr/bin/env python3
"""Session persistence for Feishu quote flow."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path


class FeishuQuoteSessionStore:
    def __init__(self, root_dir: Path, ttl_hours: int = 24):
        self.root_dir = Path(root_dir)
        self.ttl_hours = ttl_hours
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, chat_id: str, user_id: str) -> Path:
        safe_name = f"{chat_id}__{user_id}".replace("/", "_")
        return self.root_dir / f"{safe_name}.json"

    def _now(self) -> datetime:
        return datetime.utcnow()

    def new_session(self, chat_id: str, user_id: str) -> dict:
        now = self._now()
        return {
            "session_id": f"{chat_id}__{user_id}",
            "chat_id": chat_id,
            "user_id": user_id,
            "current_step": "await_brand_name",
            "form_data": {},
            "last_card_type": None,
            "updated_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=self.ttl_hours)).isoformat(),
        }

    def save(self, session: dict) -> None:
        now = self._now()
        session["updated_at"] = now.isoformat()
        if "expires_at" not in session:
            session["expires_at"] = (now + timedelta(hours=self.ttl_hours)).isoformat()
        self._path(session["chat_id"], session["user_id"]).write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, chat_id: str, user_id: str) -> dict | None:
        path = self._path(chat_id, user_id)
        if not path.exists():
            return None
        session = json.loads(path.read_text(encoding="utf-8"))
        expires_at = session.get("expires_at")
        if expires_at and datetime.fromisoformat(expires_at) < self._now():
            path.unlink(missing_ok=True)
            return None
        return session

    def clear(self, chat_id: str, user_id: str) -> None:
        self._path(chat_id, user_id).unlink(missing_ok=True)

    def cleanup_expired(self) -> int:
        removed = 0
        now = self._now()
        for path in self.root_dir.glob("*.json"):
            try:
                session = json.loads(path.read_text(encoding="utf-8"))
                expires_at = session.get("expires_at")
                if expires_at and datetime.fromisoformat(expires_at) < now:
                    path.unlink(missing_ok=True)
                    removed += 1
            except Exception:
                continue
        return removed
