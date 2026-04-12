# Feishu Quote Card MVP 手工验证记录（ECS）

验证日期：2026-04-12
验证环境：`/ai/openclaw-skills/quanlaidian-quotation-skill`（ECS）

## 背景

`handle_feishu_quote_message.py` 在 CLI 直跑时会调用飞书发送接口，依赖 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`。
为避免外部网络和凭据影响，本次采用 **mock 发送层**（仅替换 `send_card` / `send_quote_result`）进行同入口流程手工演练，覆盖会话推进、边界拦截、报价文件生成。

## 执行命令

```bash
cd /ai/openclaw-skills/quanlaidian-quotation-skill
export PRICING_BASELINE_KEY="$(cat /root/.quanlaidian_pricing_baseline.key)"
.venv/bin/python - <<PY
# 调用 scripts.feishu_quote_flow.handle_quote_message
# mock send_card/send_quote_result
# 顺序输入：黑马汇 -> 正餐 -> 10 -> 厨房KDS, 成本管理 -> 配送中心 -> 1 -> 确认
# 追加验证："黑马汇 10店 正餐 旗舰版"（预填）
# 追加验证："黑马汇 31店 正餐 旗舰版"（边界）
PY
```

## 结果摘要

- 主流程回合推进：
  - `黑马汇` -> `await_meal_type`
  - `正餐` -> `await_store_count`
  - `10` -> `await_store_modules`
  - `厨房KDS, 成本管理` -> `await_hq_modules`
  - `配送中心` -> `await_delivery_center_count`
  - `1` -> `await_confirm_generate`
  - `确认` -> `completed`
- 成功生成报价文件（JSON/PDF/XLSX），示例目录：`/tmp/feishu_output_8shxlr18`
- 预填验证：`黑马汇 10店 正餐 旗舰版` 直接进入 `await_store_modules`
- 边界验证：`黑马汇 31店 正餐 旗舰版` 返回 `unsupported`，`reason=store_count_gt_30`

## 回归验证

```bash
.venv/bin/python -m py_compile scripts/feishu_quote_flow.py scripts/handle_feishu_quote_message.py scripts/feishu_file_delivery.py
.venv/bin/python -m unittest tests.test_feishu_file_delivery tests.test_feishu_quote_flow tests.test_skill_docs -v
```

结果：`Ran 8 tests ... OK`

## 发现并修复

手工演练中发现：在 `await_store_count` 步骤输入纯数字（如 `10`）时，预填识别会把输入误当作品牌名，导致流程停留在门店数量步骤。
已在 `scripts/feishu_quote_flow.py` 修复：

- 增加 `applied_prefill` 标记，仅在**实际应用了预填字段**时才跳过当前步骤解析
- 对已存在字段（品牌/餐饮类型/门店数量）不再被预填覆盖

修复后上述主流程已验证通过。
