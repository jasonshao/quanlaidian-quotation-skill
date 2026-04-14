#!/usr/bin/env python3
"""Feishu message + file delivery utilities."""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
import urllib.request
from pathlib import Path


class FeishuDeliveryError(RuntimeError):
    pass


class FeishuCredentialMissing(FeishuDeliveryError):
    """飞书凭据缺失，但不影响文件生成（优雅降级用）。"""
    pass


def _as_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_multipart_form(fields: dict[str, str], file_path: Path) -> tuple[bytes, str]:
    boundary = f"----OpenClawBoundary{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    data = bytearray()

    for key, value in fields.items():
        data.extend(f"--{boundary}\r\n".encode("utf-8"))
        data.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode("utf-8"))
        data.extend(value.encode("utf-8"))
        data.extend(b"\r\n")

    file_bytes = file_path.read_bytes()
    data.extend(f"--{boundary}\r\n".encode("utf-8"))
    data.extend(
        (
            f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
    )
    data.extend(file_bytes)
    data.extend(b"\r\n")
    data.extend(f"--{boundary}--\r\n".encode("utf-8"))

    return bytes(data), f"multipart/form-data; boundary={boundary}"


class FeishuClient:
    def __init__(self, app_id: str, app_secret: str, receive_id: str, receive_id_type: str = "chat_id"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.receive_id = receive_id
        self.receive_id_type = receive_id_type

    @classmethod
    def from_env(
        cls,
        receive_id: str | None = None,
        receive_id_type: str | None = None,
    ) -> "FeishuClient":
        app_id = os.getenv("FEISHU_APP_ID", "").strip()
        app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
        final_receive_id = (receive_id or os.getenv("FEISHU_RECEIVE_ID", "")).strip()
        final_receive_id_type = receive_id_type or os.getenv("FEISHU_RECEIVE_ID_TYPE", "chat_id").strip() or "chat_id"

        missing = []
        if not app_id:
            missing.append("FEISHU_APP_ID")
        if not app_secret:
            missing.append("FEISHU_APP_SECRET")
        if missing:
            raise FeishuCredentialMissing("飞书发送缺少环境变量: " + ", ".join(missing))
        if not final_receive_id:
            raise FeishuDeliveryError("飞书发送缺少接收目标：请传入 chat_id 或设置 FEISHU_RECEIVE_ID")
        return cls(app_id, app_secret, final_receive_id, final_receive_id_type)

    def _request_json(self, url: str, payload: dict, token: str | None = None) -> dict:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_tenant_access_token(self) -> str:
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}
        data = self._request_json(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            payload,
        )
        if data.get("code") != 0 or not data.get("tenant_access_token"):
            raise FeishuDeliveryError(f"获取 tenant_access_token 失败: {data}")
        return data["tenant_access_token"]

    def _send_message(self, token: str, msg_type: str, content: dict) -> str:
        payload = {
            "receive_id": self.receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
        }
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={self.receive_id_type}"
        data = self._request_json(url, payload, token=token)
        if data.get("code") != 0:
            raise FeishuDeliveryError(f"发送{msg_type}消息失败: {data}")
        return data["data"]["message_id"]

    def upload_file(self, token: str, file_path: Path) -> str:
        body, content_type = _build_multipart_form(
            fields={"file_type": "stream", "file_name": file_path.name},
            file_path=file_path,
        )
        req = urllib.request.Request(
            "https://open.feishu.cn/open-apis/im/v1/files",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": content_type,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("code") != 0:
            raise FeishuDeliveryError(f"上传文件失败({file_path.name}): {data}")
        return data["data"]["file_key"]

    def send_file_message(self, token: str, file_key: str) -> str:
        return self._send_message(token, "file", {"file_key": file_key})

    def send_text_message(self, token: str, text: str) -> str:
        return self._send_message(token, "text", {"text": text})

    def send_card_message(self, token: str, card: dict) -> str:
        return self._send_message(token, "interactive", card)


def should_send_to_feishu(explicit_flag: bool = False, receive_id: str | None = None) -> bool:
    if explicit_flag:
        return True
    if receive_id and str(receive_id).strip():
        return True
    if _as_bool(os.getenv("FEISHU_SEND_FILES")):
        return True
    return bool(os.getenv("FEISHU_RECEIVE_ID", "").strip())


def deliver_files_to_feishu(
    file_paths: list[Path],
    preview_text: str | None = None,
    receive_id: str | None = None,
    receive_id_type: str = "chat_id",
) -> list[dict]:
    client = FeishuClient.from_env(receive_id=receive_id, receive_id_type=receive_id_type)
    token = client.get_tenant_access_token()

    results = []
    if preview_text:
        client.send_text_message(token, preview_text)

    for path in file_paths:
        file_key = client.upload_file(token, path)
        message_id = client.send_file_message(token, file_key)
        results.append(
            {
                "file_name": path.name,
                "local_path": str(path),
                "file_key": file_key,
                "message_id": message_id,
            }
        )
    return results


def deliver_card_to_feishu(card: dict, chat_id: str | None = None, receive_id_type: str = "chat_id") -> str:
    client = FeishuClient.from_env(receive_id=chat_id, receive_id_type=receive_id_type)
    token = client.get_tenant_access_token()
    return client.send_card_message(token, card)
