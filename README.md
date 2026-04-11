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

## 定价算法

当前规则引擎采用“两段式定价”：

1. 先按门店规模区间给出基础折扣。
   - `1-10店`：`0.25`
   - `11-20店`：`0.20`
   - `21-50店`：`0.18`
   - `51-100店`：`0.15`
   - `100店以上`：`0.10`
2. 如果本地存在 `data/history_quote_cases.jsonl`，会继续按“同套餐 + 同餐饮类型口径”提取历史案例里的折后单店软件价，用样本量、门店数量分布均匀度、加权均值和加权中位数对基础价做历史拟合。
3. 轻餐和正餐各自拥有独立的历史拟合参数，以及不同门店规模下的折扣下限/上限约束。
4. 如果表单里显式传入 `折扣`，则仍以人工传入值为准，不覆盖业务特批。

最终报价配置会在 `定价信息` 中保留：
- 基础折扣
- 历史拟合折扣
- 最终折扣
- 历史样本数
- 分布均匀度
- 拟合单价

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

## OpenClaw 推理架构

这个项目最终运行在 OpenClaw Skills 中，因此推理阶段不在仓库内单独绑定某一家模型服务。推理所使用的模型，依赖 OpenClaw 配置的模型，并由 OpenClaw 为当前 Skill 注入具体配置。

当前推荐的执行链路是：

1. OpenClaw 表单提交后，先进入历史案例抽取/检索链路。
2. `scripts/retrieve_similar_cases.py` 从历史报价案例库中找相似样本。
3. `scripts/recommend_quote_plan.py` 调用 OpenClaw 配置的模型，输出推荐的套餐/模块补丁。
4. 现有 `scripts/build_quotation_config.py` 继续作为规则定价引擎，负责精确计算。
5. `scripts/audit_quote_config.py` 再调用 OpenClaw 配置的模型，对最终报价做合理性审单。
6. `scripts/generate_quotation.py` 负责 PDF/Excel 渲染，`scripts/run_openclaw_quotation.py` 负责对话预览和文件输出。

第一版流水线已经接入 `scripts/run_openclaw_quotation.py`：

- 如果存在历史案例库，会先执行相似案例检索；
- 如果 OpenClaw 已注入模型配置，会执行推荐补全与审单；
- 如果未注入模型配置，会自动退化为“检索 + 规则定价”，不会阻断出单；
- 除了 PDF、Excel、报价配置 JSON 外，还会额外输出一份 `品牌名-全来店-推理结果-YYYYMMDD.json`。

### 新增脚本

- `scripts/extract_historical_quotes.py`
  作用：把历史 Excel 报价单抽成统一 JSONL 案例库，当前已支持解析套餐、门店增值模块、总部模块、实施服务、总价和说明文本，并默认忽略硬件行。
- `scripts/retrieve_similar_cases.py`
  作用：按餐饮类型、门店规模带宽、套餐相似度、门店/总部模块重合度、实施服务相似度做分层检索和排序，并输出高频套餐/模块统计。
- `scripts/recommend_quote_plan.py`
  作用：调用 OpenClaw 配置的模型，按售前语气输出推荐方案补丁和候选备选方案。
- `scripts/audit_quote_config.py`
  作用：调用 OpenClaw 配置的模型，输出报价合理性审查结果、风险摘要和建议调整项。
- `scripts/llm_client.py`
  作用：统一封装 OpenClaw 注入的模型配置与结构化 JSON 调用。

### JSON Schema

推理相关输入输出契约放在：

- `references/reasoning_schemas/history_quote_case.schema.json`
- `references/reasoning_schemas/retrieved_cases.schema.json`
- `references/reasoning_schemas/recommended_quote_plan.schema.json`
- `references/reasoning_schemas/quote_audit.schema.json`

### OpenClaw 模型配置约定

脚手架默认从 OpenClaw 运行时注入的环境变量读取模型配置：

- `OPENCLAW_MODEL_NAME`
- `OPENCLAW_MODEL_API_BASE`
- `OPENCLAW_MODEL_API_KEY`

这几个值应由 OpenClaw 根据当前 Skill 绑定的模型自动下发，而不是在仓库里写死。
