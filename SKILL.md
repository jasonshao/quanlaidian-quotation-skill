---
name: quanlaidian-quotation-skill
description: "全来店报价技能：当用户需要根据品牌名称、餐饮类型、门店数量、套餐和模块勾选来生成全来店报价单时触发。适用于 OpenClaw 表单输入后，一次性输出 PDF、Excel 和 JSON 三份报价文件。"
---

# 全来店报价技能

本技能用于把 OpenClaw 业务表单转换为全来店标准报价文件。

## 触发场景

当用户需要以下能力时使用本技能：

- 为餐饮客户生成全来店报价单
- 根据品牌名、门店数、套餐、增值模块生成报价
- 输出对客 PDF、内部 Excel 和留档 JSON
- 让销售或售前通过业务表单一键出报价

## 输入方式

本技能默认接收业务表单字段，而不是完整报价 JSON。

核心字段：

- 客户品牌名称
- 餐饮类型
- 门店数量
- 门店套餐
- 门店增值模块
- 总部模块
- 配送中心数量
- 生产加工中心数量
- 折扣
- 是否启用阶梯报价
- 实施服务类型
- 实施服务人天

## 工作流程

1. 读取业务表单输入
2. 调用 `scripts/build_quotation_config.py` 生成标准报价 JSON
3. 调用 `scripts/run_openclaw_quotation.py` 输出文件
4. 在当前工作目录生成三份结果文件
5. 在 OpenClaw 对话中返回“报价内容预览 + 文件下载入口”

## 输出结果

OpenClaw 对话输出：

- 对话中展示报价内容预览（关键字段与主要费用项）
- 对话中提供 PDF、Excel、JSON 三个文件的下载入口（或可点击文件引用）

默认文件输出：

- `品牌名-全来店-报价配置-YYYYMMDD.json`
- `品牌名-全来店-报价单-YYYYMMDD.pdf`
- `品牌名-全来店-报价单-YYYYMMDD.xlsx`

用途说明：

- PDF：对外发送客户
- Excel：内部调整与复核
- JSON：内部留档与再次生成

## 读取参考资料

必要时读取以下文件：

- `references/product_catalog.md`
- `references/cost_prices.md`
- `references/sales_guide.md`
- `references/openclaw_form_schema.json`

## 调用脚本

仅生成标准报价 JSON：

```bash
python3 scripts/build_quotation_config.py \
  --form 表单.json \
  --output 报价配置.json
```

生成完整报价文件：

```bash
python3 scripts/run_openclaw_quotation.py \
  --form 表单.json \
  --output-dir .
```

## OpenClaw 对话输出规范

生成报价文件后，必须在对话中同时返回以下两类结果：

1. 报价内容预览（直接可读）
- 使用清晰的小结展示关键字段，例如：品牌名称、餐饮类型、门店数量、门店套餐、折扣、总部模块、实施服务。
- 至少给出“本次配置摘要 + 主要费用项”两部分，避免只返回“已生成成功”。

2. 文件下载入口（直接可点）
- 在对话中给出 3 个文件的可下载链接或可点击文件引用：PDF、Excel、JSON。
- 链接文字应明确区分文件类型，例如：`下载报价单 PDF`、`下载报价单 Excel`、`下载报价配置 JSON`。
- 如果运行环境不支持超链接，至少返回完整文件路径，保证用户可以在对话中直接拿到文件位置。

失败时返回规则：

- 若生成失败，先用一句话说明失败原因，再给出可执行的修复建议。
- 不允许只返回堆栈信息。

## 约束

- 报价单抬头仅展示品牌名称
- 本期不包含硬件报价
- 若折扣超出建议范围，需要明确提示风险
- 若配置或依赖异常，优先返回清晰错误，而不是静默失败

## 飞书下载实现要求

当运行环境提供飞书凭据（`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_RECEIVE_ID`）时：

- 生成完成后，先在对话中发送报价预览文本；
- 再发送 3 条飞书文件消息（PDF、Excel、JSON）；
- 对话中明确告知“请直接点击飞书文件消息下载”。

推荐命令：

```bash
python3 scripts/run_openclaw_quotation.py \
  --form 表单.json \
  --output-dir . \
  --send-to-feishu
```
