# Feishu Quote Card MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Feishu-friendly MVP quotation flow that uses static cards plus text replies to collect standard quote inputs, persist multi-turn session state, and generate/send quotation files through the existing 全来店 pricing engine.

**Architecture:** Add a small Feishu quote interaction layer around the existing pricing scripts. The new layer is split into focused modules for option loading, session persistence, input parsing, card rendering, and flow orchestration, then connected to the existing Feishu delivery utilities and quotation generator. The implementation stays transport-light: the inbound runtime only needs to pass `chat_id`, `user_id`, and message text into a single handler.

**Tech Stack:** Python 3, `unittest`, existing `urllib.request`-based Feishu client, existing quotation scripts, local JSON session files under `data/`

---

### Task 1: Extend Feishu Delivery To Support Static Cards

**Files:**
- Modify: `scripts/feishu_file_delivery.py`
- Create: `tests/test_feishu_file_delivery.py`

- [ ] **Step 1: Write the failing test**

```python
import json
import unittest
from unittest import mock

from scripts.feishu_file_delivery import FeishuClient


class FeishuFileDeliveryTests(unittest.TestCase):
    def test_send_card_message_posts_interactive_payload(self):
        client = FeishuClient("app_id", "app_secret", "oc_chat")
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "第 1 步：选择餐饮类型"}},
            "elements": [],
        }

        with mock.patch.object(
            client,
            "_request_json",
            return_value={"code": 0, "data": {"message_id": "om_xxx"}},
        ) as mocked:
            message_id = client.send_card_message("tenant_token", card)

        self.assertEqual(message_id, "om_xxx")
        payload = mocked.call_args.args[1]
        self.assertEqual(payload["msg_type"], "interactive")
        self.assertIsInstance(payload["content"], str)
        self.assertIn("第 1 步：选择餐饮类型", payload["content"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_feishu_file_delivery.FeishuFileDeliveryTests.test_send_card_message_posts_interactive_payload -v`

Expected: FAIL with `AttributeError: 'FeishuClient' object has no attribute 'send_card_message'`

- [ ] **Step 3: Write minimal implementation**

```python
class FeishuClient:
    ...

    @classmethod
    def from_env(cls, receive_id: str | None = None, receive_id_type: str | None = None) -> "FeishuClient":
        app_id = os.getenv("FEISHU_APP_ID", "").strip()
        app_secret = os.getenv("FEISHU_APP_SECRET", "").strip()
        final_receive_id = (receive_id or os.getenv("FEISHU_RECEIVE_ID", "")).strip()
        final_receive_id_type = receive_id_type or os.getenv("FEISHU_RECEIVE_ID_TYPE", "chat_id").strip() or "chat_id"
        missing = [
            name
            for name, value in (
                ("FEISHU_APP_ID", app_id),
                ("FEISHU_APP_SECRET", app_secret),
                ("FEISHU_RECEIVE_ID", final_receive_id),
            )
            if not value
        ]
        if missing:
            raise FeishuDeliveryError("飞书发送缺少环境变量: " + ", ".join(missing))
        return cls(app_id, app_secret, final_receive_id, final_receive_id_type)

    def _send_message(self, token: str, msg_type: str, content: dict | str) -> str:
        payload = {
            "receive_id": self.receive_id,
            "msg_type": msg_type,
            "content": content if isinstance(content, str) else json.dumps(content, ensure_ascii=False),
        }
        url = f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={self.receive_id_type}"
        data = self._request_json(url, payload, token=token)
        if data.get("code") != 0:
            raise FeishuDeliveryError(f"发送 {msg_type} 消息失败: {data}")
        return data["data"]["message_id"]

    def send_text_message(self, token: str, text: str) -> str:
        return self._send_message(
            token,
            "text",
            {"text": text},
        )

    def send_card_message(self, token: str, card: dict) -> str:
        return self._send_message(
            token,
            "interactive",
            card,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_feishu_file_delivery -v`

Expected: PASS for the new card-delivery test and no regression in existing file-delivery behavior

- [ ] **Step 5: Commit**

```bash
git add scripts/feishu_file_delivery.py tests/test_feishu_file_delivery.py
git commit -m "feat: add static feishu card delivery"
```

### Task 2: Add A Quote Option Catalog Helper Reusing Existing Product Rules

**Files:**
- Create: `scripts/feishu_quote_options.py`
- Create: `tests/test_feishu_quote_options.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from scripts.feishu_quote_options import (
    get_default_package_value,
    get_headquarter_module_options,
    get_package_options,
    get_store_module_options,
)


class FeishuQuoteOptionsTests(unittest.TestCase):
    def test_get_package_options_filters_by_meal_type(self):
        light_packages = get_package_options("轻餐")
        regular_packages = get_package_options("正餐")

        self.assertEqual(light_packages, [{"value": "轻餐连锁营销基础版", "label": "旗舰版"}])
        self.assertEqual(regular_packages, [{"value": "正餐连锁营销基础版", "label": "旗舰版"}])

    def test_get_default_package_value_maps_flagship_alias(self):
        self.assertEqual(get_default_package_value("轻餐"), "轻餐连锁营销基础版")
        self.assertEqual(get_default_package_value("正餐"), "正餐连锁营销基础版")

    def test_get_store_module_options_supports_dinner_kds(self):
        labels = [item["label"] for item in get_store_module_options("正餐")]
        self.assertIn("厨房KDS", labels)

    def test_get_headquarter_module_options_only_returns_supported_modules(self):
        labels = [item["label"] for item in get_headquarter_module_options("正餐")]
        self.assertIn("配送中心", labels)
        self.assertIn("生产加工", labels)
        self.assertNotIn("未定义总部模块", labels)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_feishu_quote_options -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.feishu_quote_options'`

- [ ] **Step 3: Write minimal implementation**

```python
from scripts.build_quotation_config import load_product_catalog


DEFAULT_PACKAGE_MAP = {
    "轻餐": "轻餐连锁营销基础版",
    "正餐": "正餐连锁营销基础版",
}


def _options_for(group: str, meal_type: str):
    products = load_product_catalog()
    options = []
    seen = set()
    for product in products:
        if product["group"] != group:
            continue
        if product["meal_type"] not in {meal_type, "通用"}:
            continue
        if product["name"] in seen:
            continue
        seen.add(product["name"])
        options.append({"value": product["name"], "label": product["name"]})
    return options


def get_default_package_value(meal_type: str):
    return DEFAULT_PACKAGE_MAP[meal_type]


def get_package_options(meal_type: str):
    return [{"value": get_default_package_value(meal_type), "label": "旗舰版"}]


def get_store_module_options(meal_type: str):
    return _options_for("门店增值模块", meal_type)


def get_headquarter_module_options(meal_type: str):
    supported = {"配送中心", "生产加工", "企业微信SCRM", "商家小程序号", "商家小程序号-品牌点位"}
    return [item for item in _options_for("总部模块", meal_type) if item["value"] in supported]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_feishu_quote_options -v`

Expected: PASS and option results align with `product_catalog.md` parsing

- [ ] **Step 5: Commit**

```bash
git add scripts/feishu_quote_options.py tests/test_feishu_quote_options.py
git commit -m "feat: add feishu quote option catalog"
```

### Task 3: Add Session Persistence For Multi-Turn Feishu Quote Flows

**Files:**
- Create: `scripts/feishu_quote_session.py`
- Create: `tests/test_feishu_quote_session.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.feishu_quote_session import FeishuQuoteSessionStore


class FeishuQuoteSessionStoreTests(unittest.TestCase):
    def test_save_and_load_round_trip(self):
        with TemporaryDirectory() as tmpdir:
            store = FeishuQuoteSessionStore(Path(tmpdir), ttl_hours=24)
            session = store.new_session("oc_chat", "ou_user")
            session["current_step"] = "await_meal_type"
            session["form_data"]["客户品牌名称"] = "黑马汇"

            store.save(session)
            loaded = store.load("oc_chat", "ou_user")

        self.assertEqual(loaded["current_step"], "await_meal_type")
        self.assertEqual(loaded["form_data"]["客户品牌名称"], "黑马汇")

    def test_load_returns_none_for_expired_session(self):
        with TemporaryDirectory() as tmpdir:
            store = FeishuQuoteSessionStore(Path(tmpdir), ttl_hours=24)
            session = store.new_session("oc_chat", "ou_user")
            session["expires_at"] = "2000-01-01T00:00:00"
            store.save(session)

            loaded = store.load("oc_chat", "ou_user")

        self.assertIsNone(loaded)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_feishu_quote_session -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.feishu_quote_session'`

- [ ] **Step 3: Write minimal implementation**

```python
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

    def new_session(self, chat_id: str, user_id: str) -> dict:
        now = datetime.utcnow()
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
        session["updated_at"] = datetime.utcnow().isoformat()
        self._path(session["chat_id"], session["user_id"]).write_text(
            json.dumps(session, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load(self, chat_id: str, user_id: str) -> dict | None:
        path = self._path(chat_id, user_id)
        if not path.exists():
            return None
        session = json.loads(path.read_text(encoding="utf-8"))
        if datetime.fromisoformat(session["expires_at"]) < datetime.utcnow():
            path.unlink()
            return None
        return session

    def clear(self, chat_id: str, user_id: str) -> None:
        path = self._path(chat_id, user_id)
        if path.exists():
            path.unlink()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_feishu_quote_session -v`

Expected: PASS for both round-trip and expiry behavior

- [ ] **Step 5: Commit**

```bash
git add scripts/feishu_quote_session.py tests/test_feishu_quote_session.py
git commit -m "feat: add feishu quote session store"
```

### Task 4: Add Step-Aware Input Parsing For Numeric, Chinese, And Mixed Replies

**Files:**
- Create: `scripts/feishu_quote_parser.py`
- Create: `tests/test_feishu_quote_parser.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from scripts.feishu_quote_parser import extract_prefill_fields, parse_multi_choice, parse_single_choice


OPTIONS = [
    {"value": "厨房KDS", "label": "厨房KDS"},
    {"value": "成本管理", "label": "成本管理"},
    {"value": "供应链基础-门店点位", "label": "供应链基础-门店点位"},
]


class FeishuQuoteParserTests(unittest.TestCase):
    def test_parse_single_choice_by_number(self):
        result = parse_single_choice("2", [{"value": "轻餐", "label": "轻餐"}, {"value": "正餐", "label": "正餐"}])
        self.assertEqual(result, "正餐")

    def test_parse_multi_choice_supports_mixed_input(self):
        result = parse_multi_choice("1, 成本管理", OPTIONS)
        self.assertEqual(result, ["厨房KDS", "成本管理"])

    def test_extract_prefill_fields_reads_store_count_and_meal_type(self):
        result = extract_prefill_fields("黑马汇 10店 正餐 旗舰版")
        self.assertEqual(result["餐饮类型"], "正餐")
        self.assertEqual(result["门店数量"], 10)
        self.assertEqual(result["门店套餐别名"], "旗舰版")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_feishu_quote_parser -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.feishu_quote_parser'`

- [ ] **Step 3: Write minimal implementation**

```python
import re


CONTROL_WORDS = {"重来": "restart", "取消": "cancel", "无": "skip", "不选": "skip"}


def _split_tokens(text: str):
    return [token.strip() for token in re.split(r"[，,、\\s]+", text) if token.strip()]


def parse_single_choice(text: str, options: list[dict]) -> str:
    text = text.strip()
    if text.isdigit():
        index = int(text) - 1
        if 0 <= index < len(options):
            return options[index]["value"]
    for option in options:
        if text.lower() in {option["label"].lower(), option["value"].lower()}:
            return option["value"]
    raise ValueError("未识别到有效选项")


def parse_multi_choice(text: str, options: list[dict]) -> list[str]:
    tokens = _split_tokens(text)
    if not tokens:
        return []
    if any(token in CONTROL_WORDS and CONTROL_WORDS[token] == "skip" for token in tokens):
        return []
    results = []
    for token in tokens:
        results.append(parse_single_choice(token, options))
    return list(dict.fromkeys(results))


def extract_prefill_fields(text: str) -> dict:
    result = {}
    normalized = text.strip()
    if "轻餐" in normalized:
        result["餐饮类型"] = "轻餐"
    if "正餐" in normalized:
        result["餐饮类型"] = "正餐"
    match = re.search(r"(\\d+)\\s*店", normalized)
    if match:
        result["门店数量"] = int(match.group(1))
    if "旗舰版" in normalized:
        result["门店套餐别名"] = "旗舰版"
    brand = re.sub(r"(\\d+\\s*店|轻餐|正餐|旗舰版)", "", normalized).strip(" ，,")
    if brand:
        result["客户品牌名称"] = brand
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_feishu_quote_parser -v`

Expected: PASS and parser accepts numeric, Chinese, and mixed replies

- [ ] **Step 5: Commit**

```bash
git add scripts/feishu_quote_parser.py tests/test_feishu_quote_parser.py
git commit -m "feat: add feishu quote input parser"
```

### Task 5: Add Static Feishu Card Builders For Each Quote Step

**Files:**
- Create: `scripts/feishu_quote_cards.py`
- Create: `tests/test_feishu_quote_cards.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from scripts.feishu_quote_cards import build_single_select_card, build_summary_markdown


class FeishuQuoteCardsTests(unittest.TestCase):
    def test_build_single_select_card_contains_options_and_examples(self):
        card = build_single_select_card(
            title="第 2 步：选择餐饮类型",
            prompt="餐饮类型是轻餐还是正餐？",
            options=[{"value": "轻餐", "label": "轻餐"}, {"value": "正餐", "label": "正餐"}],
            summary={"客户品牌名称": "黑马汇"},
            examples=["1", "正餐"],
        )

        self.assertEqual(card["header"]["title"]["content"], "第 2 步：选择餐饮类型")
        rendered = str(card)
        self.assertIn("轻餐", rendered)
        self.assertIn("正餐", rendered)
        self.assertIn("黑马汇", rendered)

    def test_build_summary_markdown_omits_empty_values(self):
        text = build_summary_markdown(
            {
                "客户品牌名称": "黑马汇",
                "餐饮类型": "正餐",
                "门店套餐": "",
            }
        )
        self.assertIn("黑马汇", text)
        self.assertIn("正餐", text)
        self.assertNotIn("门店套餐：", text)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_feishu_quote_cards -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.feishu_quote_cards'`

- [ ] **Step 3: Write minimal implementation**

```python
def build_summary_markdown(summary: dict) -> str:
    lines = []
    for key in ("客户品牌名称", "餐饮类型", "门店数量", "门店套餐", "门店增值模块", "总部模块"):
        value = summary.get(key)
        if value in (None, "", []):
            continue
        if isinstance(value, list):
            value = "、".join(value)
        lines.append(f"- {key}：{value}")
    return "\\n".join(lines) or "- 暂无已选信息"


def build_single_select_card(title: str, prompt: str, options: list[dict], summary: dict, examples: list[str]) -> dict:
    option_lines = [f"{idx}. {item['label']}" for idx, item in enumerate(options, start=1)]
    return {
        "config": {"wide_screen_mode": True},
        "header": {"title": {"tag": "plain_text", "content": title}},
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": prompt}},
            {"tag": "div", "text": {"tag": "lark_md", "content": "\\n".join(option_lines)}},
            {"tag": "div", "text": {"tag": "lark_md", "content": f"已选摘要\\n{build_summary_markdown(summary)}"}},
            {"tag": "note", "elements": [{"tag": "plain_text", "content": f"回复示例：{' / '.join(examples)}"}]},
        ],
    }


def build_multi_select_card(title: str, prompt: str, options: list[dict], summary: dict) -> dict:
    return build_single_select_card(
        title=title,
        prompt=prompt,
        options=options,
        summary=summary,
        examples=["1,3", "厨房KDS, 成本管理", "无"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_feishu_quote_cards -v`

Expected: PASS and card payload includes prompt, options, summary, and examples

- [ ] **Step 5: Commit**

```bash
git add scripts/feishu_quote_cards.py tests/test_feishu_quote_cards.py
git commit -m "feat: add feishu quote card builders"
```

### Task 6: Implement The Quote Flow Orchestrator And Inbound Message Handler

**Files:**
- Create: `scripts/feishu_quote_flow.py`
- Create: `scripts/handle_feishu_quote_message.py`
- Create: `tests/test_feishu_quote_flow.py`
- Modify: `scripts/run_openclaw_quotation.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from scripts.feishu_quote_flow import handle_quote_message


class FeishuQuoteFlowTests(unittest.TestCase):
    def test_full_flow_can_prefill_then_ask_for_store_modules(self):
        with TemporaryDirectory() as tmpdir:
            with mock.patch("scripts.feishu_quote_flow.send_step_card") as mocked_send:
                result = handle_quote_message(
                    chat_id="oc_chat",
                    user_id="ou_user",
                    text="黑马汇 10店 正餐 旗舰版",
                    session_dir=Path(tmpdir),
                    output_dir=Path(tmpdir),
                )

        self.assertEqual(result["current_step"], "await_store_modules")
        mocked_send.assert_called_once()

    def test_confirm_generate_calls_output_pipeline_and_clears_session(self):
        with TemporaryDirectory() as tmpdir:
            with mock.patch("scripts.feishu_quote_flow.generate_outputs", return_value=("a.json", "a.pdf", "a.xlsx")) as mocked_generate, \
                 mock.patch("scripts.feishu_quote_flow.send_quote_result") as mocked_send, \
                 mock.patch("scripts.feishu_quote_flow.send_step_card"):
                handle_quote_message("oc_chat", "ou_user", "黑马汇", Path(tmpdir), Path(tmpdir))
                handle_quote_message("oc_chat", "ou_user", "正餐", Path(tmpdir), Path(tmpdir))
                handle_quote_message("oc_chat", "ou_user", "10", Path(tmpdir), Path(tmpdir))
                handle_quote_message("oc_chat", "ou_user", "无", Path(tmpdir), Path(tmpdir))
                handle_quote_message("oc_chat", "ou_user", "无", Path(tmpdir), Path(tmpdir))
                result = handle_quote_message("oc_chat", "ou_user", "确认", Path(tmpdir), Path(tmpdir))

        mocked_generate.assert_called_once()
        mocked_send.assert_called_once()
        self.assertEqual(result["current_step"], "completed")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_feishu_quote_flow -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.feishu_quote_flow'`

- [ ] **Step 3: Write minimal implementation**

```python
import json
from pathlib import Path

from scripts.feishu_quote_cards import build_multi_select_card, build_single_select_card
from scripts.feishu_file_delivery import FeishuClient
from scripts.feishu_quote_options import (
    get_default_package_value,
    get_headquarter_module_options,
    get_package_options,
    get_store_module_options,
)
from scripts.feishu_quote_parser import extract_prefill_fields, parse_multi_choice, parse_single_choice
from scripts.feishu_quote_session import FeishuQuoteSessionStore
from scripts.run_openclaw_quotation import generate_outputs


STEP_ORDER = [
    "await_brand_name",
    "await_meal_type",
    "await_store_count",
    "await_store_modules",
    "await_hq_modules",
    "await_delivery_center_count",
    "await_production_center_count",
    "await_confirm_generate",
]


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


def build_step_card(step: str, form_data: dict) -> dict:
    if step == "await_meal_type":
        return build_single_select_card(
            title="第 2 步：选择餐饮类型",
            prompt="餐饮类型是轻餐还是正餐？",
            options=[{"value": "轻餐", "label": "轻餐"}, {"value": "正餐", "label": "正餐"}],
            summary=form_data,
            examples=["1", "正餐"],
        )
    if step == "await_store_modules":
        return build_multi_select_card(
            title="第 5 步：选择门店增值模块",
            prompt="门店增值模块需要哪些？回复序号、中文名称或混合输入都可以。",
            options=get_store_module_options(form_data["餐饮类型"]),
            summary=form_data,
        )
    if step == "await_hq_modules":
        return build_multi_select_card(
            title="第 6 步：选择总部模块",
            prompt="总部模块需要哪些？回复序号、中文名称或混合输入都可以。",
            options=get_headquarter_module_options(form_data["餐饮类型"]),
            summary=form_data,
        )
    return build_single_select_card(
        title="继续完善报价信息",
        prompt="请继续回复当前步骤所需信息。",
        options=[],
        summary=form_data,
        examples=["黑马汇", "10", "确认"],
    )


def send_step_card(session: dict) -> None:
    client = FeishuClient.from_env(receive_id=session["chat_id"], receive_id_type="chat_id")
    token = client.get_tenant_access_token()
    client.send_card_message(token, build_step_card(session["current_step"], session["form_data"]))


def send_quote_result(chat_id: str, form_data: dict, output_paths: tuple) -> None:
    client = FeishuClient.from_env(receive_id=chat_id, receive_id_type="chat_id")
    token = client.get_tenant_access_token()
    summary = f"报价已生成\\n品牌：{form_data['客户品牌名称']}\\n餐饮类型：{form_data['餐饮类型']}\\n门店数：{form_data['门店数量']}"
    client.send_text_message(token, summary)
    for path in output_paths:
        file_key = client.upload_file(token, Path(path))
        client.send_file_message(token, file_key)


def handle_quote_message(chat_id: str, user_id: str, text: str, session_dir: Path, output_dir: Path) -> dict:
    store = FeishuQuoteSessionStore(session_dir)
    session = store.load(chat_id, user_id) or store.new_session(chat_id, user_id)
    form_data = session["form_data"]
    prefill = extract_prefill_fields(text)
    form_data.update({k: v for k, v in prefill.items() if k != "门店套餐别名"})
    if prefill.get("门店套餐别名") == "旗舰版" and form_data.get("餐饮类型"):
        form_data["门店套餐"] = get_default_package_value(form_data["餐饮类型"])
    if form_data.get("餐饮类型") and not form_data.get("门店套餐"):
        form_data["门店套餐"] = get_default_package_value(form_data["餐饮类型"])

    step = _next_step(form_data)
    if step == "await_brand_name" and text.strip():
        form_data["客户品牌名称"] = text.strip()
    elif step == "await_meal_type":
        form_data["餐饮类型"] = parse_single_choice(text, [{"value": "轻餐", "label": "轻餐"}, {"value": "正餐", "label": "正餐"}])
    elif step == "await_store_count":
        form_data["门店数量"] = int(text.strip())
    elif step == "await_store_modules":
        options = get_store_module_options(form_data["餐饮类型"])
        form_data["门店增值模块"] = parse_multi_choice(text, options)
    elif step == "await_hq_modules":
        options = get_headquarter_module_options(form_data["餐饮类型"])
        form_data["总部模块"] = parse_multi_choice(text, options)
    elif step == "await_delivery_center_count":
        form_data["配送中心数量"] = int(text.strip())
    elif step == "await_production_center_count":
        form_data["生产加工中心数量"] = int(text.strip())
    elif step == "await_confirm_generate" and text.strip() in {"确认", "生成报价", "生成"}:
        form_path = output_dir / f"{chat_id}__{user_id}.form.json"
        form_path.write_text(json.dumps(form_data, ensure_ascii=False, indent=2), encoding="utf-8")
        output_paths = generate_outputs(str(form_path), str(output_dir))
        send_quote_result(chat_id, form_data, output_paths)
        store.clear(chat_id, user_id)
        return {"current_step": "completed", "form_data": form_data}

    session["current_step"] = _next_step(form_data)
    session["form_data"] = form_data
    store.save(session)
    send_step_card(session)
    return {"current_step": session["current_step"], "form_data": form_data}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_feishu_quote_flow -v`

Expected: PASS for prefill advancement and confirmation-triggered generation

- [ ] **Step 5: Commit**

```bash
git add scripts/feishu_quote_flow.py scripts/handle_feishu_quote_message.py scripts/run_openclaw_quotation.py tests/test_feishu_quote_flow.py
git commit -m "feat: add feishu quote flow orchestration"
```

### Task 7: Document The MVP Flow And Add End-To-End Regression Coverage

**Files:**
- Modify: `README.md`
- Modify: `SKILL.md`
- Modify: `agents/openai.yaml`
- Create: `tests/test_skill_docs.py`

- [ ] **Step 1: Write the failing regression test**

```python
import unittest
from pathlib import Path


class SkillDocsTests(unittest.TestCase):
    def test_skill_mentions_guided_feishu_quote_flow(self):
        skill_path = Path(__file__).resolve().parent.parent / "SKILL.md"
        content = skill_path.read_text(encoding="utf-8")
        self.assertIn("飞书", content)
        self.assertIn("数字、中文名称或混合方式", content)

    def test_readme_mentions_feishu_card_mvp_entrypoint(self):
        readme_path = Path(__file__).resolve().parent.parent / "README.md"
        content = readme_path.read_text(encoding="utf-8")
        self.assertIn("飞书报价卡片 MVP", content)
        self.assertIn("scripts/handle_feishu_quote_message.py", content)
```

- [ ] **Step 2: Run tests to verify the new expectation fails**

Run: `python3 -m unittest tests.test_skill_docs -v`

Expected: FAIL if the new documentation guidance is missing

- [ ] **Step 3: Write minimal implementation**

```markdown
<!-- README.md -->
## 飞书报价卡片 MVP

- 每轮发送一张静态卡片
- 用户可回复数字、中文名称或混合输入
- 服务端按 `chat_id + user_id` 保存 24 小时临时状态
- 套餐默认按对应餐饮类型映射到 `旗舰版`
- `31 店及以上` 自动转人工

运行入口示例：

```bash
python3 scripts/handle_feishu_quote_message.py \
  --chat-id oc_xxx \
  --user-id ou_xxx \
  --text "开始报价"
```
```

```yaml
# agents/openai.yaml
interface:
  short_description: "支持 OpenClaw 与飞书引导式报价交互"
```

```markdown
<!-- SKILL.md -->
- 在飞书环境中优先发送静态卡片，并允许用户以数字、中文名称或混合方式回复选择结果
```

- [ ] **Step 4: Run regression suite**

Run: `python3 -m unittest tests.test_skill_docs tests.test_feishu_file_delivery tests.test_feishu_quote_options tests.test_feishu_quote_session tests.test_feishu_quote_parser tests.test_feishu_quote_cards tests.test_feishu_quote_flow -v`

Expected: PASS for the full MVP regression suite

- [ ] **Step 5: Commit**

```bash
git add README.md SKILL.md agents/openai.yaml tests/test_skill_docs.py
git commit -m "docs: describe feishu quote card mvp flow"
```

### Task 8: Manual Verification On ECS With A Realistic Conversation Script

**Files:**
- Modify: none
- Test: `scripts/handle_feishu_quote_message.py`

- [ ] **Step 1: Run a start-to-finish dry run using a temp output directory**

Run:

```bash
tmpdir="$(mktemp -d)"
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo --user-id ou_demo --text "黑马汇"
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo --user-id ou_demo --text "正餐"
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo --user-id ou_demo --text "10"
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo --user-id ou_demo --text "厨房KDS, 成本管理"
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo --user-id ou_demo --text "配送中心"
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo --user-id ou_demo --text "1"
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo --user-id ou_demo --text "确认"
```

Expected: each turn emits a card/text response payload; the final turn emits quotation files

- [ ] **Step 2: Run a direct natural-language prefill case**

Run:

```bash
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo2 --user-id ou_demo2 --text "黑马汇 10店 正餐 旗舰版"
```

Expected: flow skips meal-type/store-count/package prompts and asks directly for store modules

- [ ] **Step 3: Run the boundary rejection case**

Run:

```bash
python3 scripts/handle_feishu_quote_message.py --chat-id oc_demo3 --user-id ou_demo3 --text "黑马汇 31店 正餐 旗舰版"
```

Expected: returns transfer-to-human response and does not attempt quotation generation

- [ ] **Step 4: Sanity-check Feishu delivery compatibility**

Run:

```bash
python3 -m unittest tests.test_feishu_file_delivery -v
```

Expected: PASS, confirming card payload serialization stays compatible with the delivery client abstraction

- [ ] **Step 5: Commit**

```bash
git status --short
```

Expected: clean worktree except any deliberate non-committed local-only files such as `references/discount_rules.json`
