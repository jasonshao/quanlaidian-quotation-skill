#!/usr/bin/env python3
import base64
import hashlib
import json
import os
from pathlib import Path
from secrets import token_bytes


OBFUSCATION_FORMAT = "pricing-baseline-obf-v1"
DEFAULT_KEY_ENV = "PRICING_BASELINE_KEY"
DEFAULT_STRICT_ENV = "PRICING_BASELINE_STRICT"


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _keystream(secret_key_bytes, nonce_bytes, size):
    buf = b""
    counter = 0
    while len(buf) < size:
        block = hashlib.sha256(
            secret_key_bytes + nonce_bytes + counter.to_bytes(4, "big")
        ).digest()
        buf += block
        counter += 1
    return buf[:size]


def _xor_bytes(left, right):
    return bytes(a ^ b for a, b in zip(left, right))


def encode_payload(plain_json_text, secret_key, nonce_hex=None):
    plain_bytes = plain_json_text.encode("utf-8")
    nonce = bytes.fromhex(nonce_hex) if nonce_hex else token_bytes(8)
    secret_key_bytes = secret_key.encode("utf-8")
    cipher_bytes = _xor_bytes(plain_bytes, _keystream(secret_key_bytes, nonce, len(plain_bytes)))
    return {
        "format": OBFUSCATION_FORMAT,
        "encoding": "base64",
        "nonce": nonce.hex(),
        "payload": base64.b64encode(cipher_bytes).decode("ascii"),
        "sha256": hashlib.sha256(plain_bytes).hexdigest(),
    }


def decode_payload(payload_obj, secret_key):
    if payload_obj.get("format") != OBFUSCATION_FORMAT:
        raise ValueError("不支持的混淆文件格式")
    if payload_obj.get("encoding") != "base64":
        raise ValueError("不支持的混淆编码")

    nonce = bytes.fromhex(str(payload_obj.get("nonce", "")))
    cipher_bytes = base64.b64decode(payload_obj.get("payload", ""))
    secret_key_bytes = secret_key.encode("utf-8")
    plain_bytes = _xor_bytes(cipher_bytes, _keystream(secret_key_bytes, nonce, len(cipher_bytes)))

    digest = hashlib.sha256(plain_bytes).hexdigest()
    if digest != payload_obj.get("sha256"):
        raise ValueError("混淆文件校验失败（sha256 不匹配）")
    return plain_bytes.decode("utf-8")


def load_baseline_from_files(
    json_path,
    obf_path=None,
    key_env=DEFAULT_KEY_ENV,
    strict_env=DEFAULT_STRICT_ENV,
):
    json_path = Path(json_path)
    obf_path = Path(obf_path) if obf_path else json_path.with_suffix(".obf")

    strict_mode = _as_bool(os.getenv(strict_env), default=False)
    secret_key = os.getenv(key_env)

    if obf_path.exists() and secret_key:
        payload_obj = json.loads(obf_path.read_text(encoding="utf-8"))
        decoded = decode_payload(payload_obj, secret_key)
        return json.loads(decoded)

    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))

    if obf_path.exists():
        if strict_mode:
            raise RuntimeError(
                f"检测到混淆基线文件 {obf_path}，但缺少环境变量 {key_env}，且 strict 模式已开启"
            )
        if secret_key:
            payload_obj = json.loads(obf_path.read_text(encoding="utf-8"))
            decoded = decode_payload(payload_obj, secret_key)
            return json.loads(decoded)
        raise RuntimeError(f"检测到混淆基线文件 {obf_path}，但缺少环境变量 {key_env}")

    if strict_mode:
        raise RuntimeError(
            f"未找到价格基线文件：{json_path} / {obf_path}，且 strict 模式已开启"
        )
    return {"items": []}
