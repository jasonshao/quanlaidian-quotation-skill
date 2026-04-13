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

## 飞书报价卡片 MVP

在飞书机器人场景，当前版本采用“静态卡片 + 文本回复”的引导模式，不依赖卡片回调。

- 每轮会发送一张卡片，展示当前问题、候选项和已选摘要
- 用户可回复 `数字`、`中文名称` 或 `混合输入`（例如 `1, 成本管理`）
- 门店增值模块和总部模块支持多选
- 服务端按 `chat_id + user_id` 保存 24 小时临时状态
- 套餐默认按餐饮类型映射为 `旗舰版`（轻餐/正餐基础版）
- `31 店及以上` 自动转人工，不进入自动报价

飞书多轮入口脚本：

```bash
python3 scripts/handle_feishu_quote_message.py \
  --chat-id oc_xxx \
  --user-id ou_xxx \
  --text "开始报价"
```

可选参数：

- `--session-dir`：会话状态目录，默认 `data/feishu_quote_sessions`
- `--output-dir`：报价文件输出目录，默认当前目录

## 价格基线与部署密钥

- 仓库仅保留混淆基线：`references/pricing_baseline_v5.obf`
- 已移除明文基线：`references/pricing_baseline_v5.json`（禁止入库）
- 运行时必须注入环境变量：`PRICING_BASELINE_KEY`
- 生产环境建议开启：`PRICING_BASELINE_STRICT=1`

示例：

```bash
export PRICING_BASELINE_KEY=请替换为部署密钥
export PRICING_BASELINE_STRICT=1
```

密钥请通过 CI/CD Secret、容器环境变量或密钥管理系统注入，不要写入仓库。

## 本地命令行验证

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

运行前请先设置密钥环境变量：

```bash
export PRICING_BASELINE_KEY=请替换为部署密钥
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
- 折扣超出动态带宽上限会被自动截断（截断记录写入 `auto_adjustments`）
- 餐饮类型与套餐/模块不匹配会报错
- 门店数量超过 30 店时，生成参考报价并标注 `pricing_info.large_segment_reference_only: true`，需人工审核确认后方可发客户

## 定价算法

当前版本：`small-segment-v2`，核心逻辑在 `scripts/build_quotation_config.py`。

### 1. 标准价计算

各商品分组的加价规则不同：

| 分组 | 标准价公式 |
|------|-----------|
| 门店套餐 | `底价 × 20`（底价占标准价 5%） |
| 门店增值模块 | `底价 × 1.10`（取整到 10 元） |
| 总部模块 | `底价 × 1.20`（取整到 10 元） |
| 实施服务 | `底价`（不加价） |
| 受保护商品（商管接口） | `底价`，且成交价系数固定为 1.0，不可打折 |

### 2. 成交价系数推荐

系统根据门店数量自动推荐成交价系数（即实付/标准价的比值），公式为连续线性递减：

```
系数 = 起步系数 − DISCOUNT_SLOPE_PER_STORE × (门店数 − 1)
```

- `DISCOUNT_SLOPE_PER_STORE = 0.05 / 19`（每增加 1 店的降幅，待 50+ 历史样本后回归校准）
- 起步锚点：轻餐 1800 元/店/年 → 系数 ≈ 0.237；正餐 3000 元/店/年 → 系数 ≈ 0.270

轻餐示例：

| 门店数 | 推荐系数 | 每店年费（元） |
|--------|---------|-------------|
| 1 | 0.2368 | 1,800 |
| 10 | 0.2132 | 1,620 |
| 20 | 0.1868 | 1,420 |
| 30 | 0.1605 | 1,220 |

最终实际价 = 标准价 × 系数，四舍五入到最近 100 元。

### 3. 折扣带宽约束

为防止极端折扣，系数会被限制在推荐值附近的带宽内：

- **静态带宽**（默认）：轻餐 ±0.02，正餐 ±0.015
- **动态带宽**（历史有效样本 ≥ 10 条时启用）：`1.5 × σ(历史成交系数)`，范围限制在 [0.01, 0.05]

超出带宽的系数会被自动截断，截断操作记入 `pricing_info.auto_adjustments`。

### 4. 历史样本修正

当 `factor_source == “auto”` 时，系统可利用历史成交数据对推荐系数做加权修正：

1. **过滤**：排除特殊审批单、赠品单、异常改价单、数据不完整、非标准套餐等
2. **时间衰减权重**：12 个月窗口，越新权重越高（最低 0.1）
3. **Winsorize**：裁剪 10–90 百分位外的离群值
4. **混合上限**（指数平滑，渐近于 25%）：

   ```
   cap = 0.25 × (1 − e^(−样本数 / 8))
   ```

   典型值：1 单 ≈ 3%，6 单 ≈ 13%，12 单 ≈ 19%，20 单 ≈ 23%

5. **最终系数**：`推荐系数 × (1 − cap) + 历史加权中位数 × cap`

### 5. 31 店以上处理

超过 30 店时，系统不报错，而是：
- 按相同线性公式外推系数，并以 `FACTOR_FLOOR = 0.08` 兜底
- 在 `pricing_info` 中标注 `large_segment_reference_only: true`
- 报价仅供参考，需人工审核后方可发客户

### 6. pricing_info 字段说明

报价配置的 `pricing_info` 字段记录完整定价过程：

| 字段 | 含义 |
|------|------|
| `algorithm_version` | 算法版本（当前 `small-segment-v2`） |
| `large_segment_reference_only` | 是否为 31 店以上参考报价 |
| `base_factor` | 推荐基础系数 |
| `bounded_range` | 允许的系数范围 `[low, high]` |
| `final_factor` | 最终采用的系数 |
| `deal_price_factor_source` | 来源：`auto` / 人工字段名 |
| `auto_adjustments` | 自动调整记录（历史修正、带宽截断等） |
| `history_sample_count` | 有效历史样本数 |
| `history_weight` | 历史数据实际混合权重 |
| `history_anchor` | 历史加权中位数 |
| `approval_required` | 是否需要审批 |
| `approval_reason` | 触发审批的原因列表 |
| `manual_override_audit` | 人工改价审计记录 |

## 常见问题

1. 运行时报缺少依赖
   - 执行 `python3 -m pip install -r requirements.txt`

2. 报错“未找到匹配产品”
   - 检查表单里的套餐/模块名称是否与 `references/product_catalog.md` 完全一致

3. 结果文件没有生成
   - 检查 `--form` 路径是否正确、字段是否齐全，或查看终端错误信息

4. 报错“检测到混淆基线文件但缺少 PRICING_BASELINE_KEY”
   - 在运行前注入 `PRICING_BASELINE_KEY`；生产建议同时开启 `PRICING_BASELINE_STRICT=1`

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

### main 自动递增版本（可选）

如需每次 `main` 有新提交就自动更新版本：

- 工作流：`.github/workflows/auto-bump-version.yml`
- 脚本：`scripts/bump_version.py`
- 触发：`push` 到 `main`（忽略仅修改 `VERSION`/`CHANGELOG.md` 的提交）
- 行为：默认按 `patch` 递增，并在 `CHANGELOG.md` 顶部追加当日记录

如需手动验证：

```bash
python3 scripts/bump_version.py
python3 scripts/bump_version.py --write
```

## 飞书文件消息下载（推荐）

建议OpenClaw在workspace新建files目录来存储生成的文件，并发送文件到飞书聊天消息中。

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
