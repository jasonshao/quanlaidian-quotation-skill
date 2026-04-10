# quanlaidian-quotation-skill

面向 OpenClaw 的全来店报价技能。

该技能用于把业务表单输入自动转换为三份标准报价产物：
- 对客 PDF 报价单
- 内部 Excel 报价单
- 结构化 JSON 报价配置

适用场景：销售/售前在 OpenClaw 中填写品牌、门店规模、套餐与模块后，一键生成可发客户的报价文件。

## OpenClaw 交互目标

用户安装技能后，每次执行应同时满足：
- 在对话中直接展示报价内容预览（而不是只提示“已生成”）
- 在对话中提供 PDF、Excel、JSON 三个文件的下载入口

建议的对话返回结构：
- 报价摘要：品牌、餐饮类型、门店数量、套餐、折扣、总部模块、实施服务
- 费用预览：主要费用项与关键金额
- 文件下载：`下载报价单 PDF`、`下载报价单 Excel`、`下载报价配置 JSON`

## 目录结构

- `SKILL.md`：技能定义与触发说明
- `agents/openai.yaml`：OpenClaw 入口元数据
- `scripts/build_quotation_config.py`：表单 -> 标准报价 JSON
- `scripts/run_openclaw_quotation.py`：主入口，生成 JSON + PDF + XLSX
- `references/`：产品目录、折扣规则、表单配置与销售说明

## OpenClaw 如何使用

在 OpenClaw 中调用技能名：`quanlaidian-quotation-skill`。

核心输入字段（业务表单）：
- 客户品牌名称
- 餐饮类型（轻餐/正餐）
- 门店数量
- 门店套餐
- 门店增值模块（可选）
- 总部模块（可选）
- 配送中心数量（可选）
- 生产加工中心数量（可选）
- 折扣（可选，不填则按规则推荐）
- 是否启用阶梯报价（可选）
- 实施服务类型/实施服务人天（可选）

## 本地命令行验证

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

仅生成报价配置 JSON：

```bash
python3 scripts/build_quotation_config.py \
  --form references/openclaw_form_submission.example.json \
  --output 输出报价配置.json
```

生成完整报价文件（JSON + PDF + XLSX）：

```bash
python3 scripts/run_openclaw_quotation.py \
  --form references/openclaw_form_submission.example.json \
  --output-dir ./mount_test_output
```

## 输出文件命名

默认命名格式（按当天日期）：
- `品牌名-全来店-报价配置-YYYYMMDD.json`
- `品牌名-全来店-报价单-YYYYMMDD.pdf`
- `品牌名-全来店-报价单-YYYYMMDD.xlsx`

## 规则与约束

- 报价单抬头仅展示品牌名称
- 当前版本不包含硬件报价
- 折扣超出规则上限会报错
- 餐饮类型与套餐/模块不匹配会报错

## 常见问题

1. 运行时报缺少依赖
   - 执行 `python3 -m pip install -r requirements.txt`

2. 报错“未找到匹配产品”
   - 检查表单里的套餐/模块名称是否与 `references/product_catalog.md` 完全一致

3. 结果文件没有生成
   - 检查 `--form` 路径是否正确、字段是否齐全，或查看终端错误信息

## 版本说明

当前仓库主分支：`main`
远程仓库：[jasonshao/quanlaidian-quotation-skill](https://github.com/jasonshao/quanlaidian-quotation-skill)

## 版本发布与 OpenClaw 自动感知

本仓库已内置两层更新机制：

1. 发布通知（GitHub -> OpenClaw）
- 工作流文件：`.github/workflows/release-notify-openclaw.yml`
- 触发条件：发布 Release（`published`）
- 行为：向 `OPENCLAW_UPDATE_WEBHOOK` 发送 JSON 通知

2. 节点自检更新（OpenClaw 节点本地）
- 脚本：`scripts/check_openclaw_update.py`
- 检查模式：`python3 scripts/check_openclaw_update.py`
- 自动更新：`python3 scripts/check_openclaw_update.py --apply`

### 配置步骤

1. 在 GitHub 仓库 Secrets 中新增：`OPENCLAW_UPDATE_WEBHOOK`
2. 每次版本发布时创建 Tag + Release（推荐 `vX.Y.Z`）
3. OpenClaw 节点通过定时任务执行：

```bash
cd /ai/openclaw-skills/quanlaidian-quotation-skill
python3 scripts/check_openclaw_update.py --apply
```

### 建议发布流程

1. 更新 `VERSION`（例如 `0.1.0` -> `0.2.0`）
2. 更新 `CHANGELOG.md`
3. 合并到 `main` 后发布 GitHub Release（tag 建议为 `v0.2.0`）

## 飞书文件消息下载（推荐）

为了解决“本地路径在飞书不可下载”的问题，主脚本已支持生成后自动上传并发送飞书文件消息。

### 需要的环境变量

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_RECEIVE_ID`
- `FEISHU_RECEIVE_ID_TYPE`（可选，默认 `chat_id`）
- `FEISHU_SEND_FILES`（可选，设为 `1/true` 时自动发送）

### 使用方式

显式开启发送：

```bash
.venv/bin/python scripts/run_openclaw_quotation.py \
  --form references/openclaw_form_submission.example.json \
  --output-dir ./mount_test_output \
  --send-to-feishu
```

说明：
- 脚本会先发一条报价预览文本，再发送 PDF/Excel/JSON 三个飞书文件消息。
- 用户可在飞书聊天窗口直接点击文件消息下载。
