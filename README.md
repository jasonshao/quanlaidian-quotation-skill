# quanlaidian-quotation-skill

面向 OpenClaw Agent 的全来店报价技能。根据业务表单输入，自动生成三份标准报价文件：

| 文件 | 用途 |
|------|------|
| `品牌名-全来店-报价单-YYYYMMDD.pdf` | 对外发送客户 |
| `品牌名-全来店-报价单-YYYYMMDD.xlsx` | 内部调整与复核 |
| `品牌名-全来店-报价配置-YYYYMMDD.json` | 结构化留档，可重复生成 |

> 技能触发规则与 Agent 交互策略详见 [`SKILL.md`](SKILL.md)。

---

## 安装技能

### 1. 克隆仓库

```bash
git clone https://github.com/jasonshao/quanlaidian-quotation-skill.git
cd quanlaidian-quotation-skill
```

### 2. 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

### 3. 配置环境变量

| 变量 | 说明 | 是否必须 |
|------|------|---------|
| `PRICING_BASELINE_KEY` | 价格基线解密密钥 | **必须** |
| `PRICING_BASELINE_STRICT` | 设为 `1` 时强制校验密钥 | 推荐（生产） |
| `FEISHU_APP_ID` | 飞书应用 ID | 仅飞书场景 |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | 仅飞书场景 |

通过 CI/CD Secret 或密钥管理系统注入，**不要写入仓库**。

---

## 使用技能

### 生成报价文件

```bash
export PRICING_BASELINE_KEY=<部署密钥>

python3 scripts/run_openclaw_quotation.py \
  --form 表单.json \
  --output-dir /home/gem/workspace/agent/workspace/files
```

生成后由 OpenClaw 原生飞书消息工具直接发送文件到对话。

---

## 输入表单字段

表单示例见 [`references/openclaw_form_submission.example.json`](references/openclaw_form_submission.example.json)，字段定义见 [`references/openclaw_form_schema.json`](references/openclaw_form_schema.json)。

| 字段 | 类型 | 说明 |
|------|------|------|
| `客户品牌名称` | string | 报价单抬头，必填 |
| `餐饮类型` | `"轻餐"` / `"正餐"` | 决定可选套餐与模块，必填 |
| `门店数量` | int | 1–30，31 及以上自动转人工，必填 |
| `门店套餐` | string | 必选 1 种，见 `references/product_catalog.md` |
| `门店增值模块` | string[] | 可多选，可选 |
| `总部模块` | string[] | 可多选，可选 |
| `配送中心数量` | int | 选了"配送中心"时填写 |
| `生产加工中心数量` | int | 选了"生产加工"时填写 |
| `成交价系数` | float | 0.01–1.0，不填自动按门店数推荐 |
| `是否启用阶梯报价` | bool | 默认 false |
| `实施服务类型` | string | 可选 |
| `实施服务人天` | int | 非负整数，可选 |

---

## 自动更新

OpenClaw 节点应配置定时任务，**每日凌晨 1 点**自动检查 GitHub 是否有新版本并更新。

### 设置 cron

```bash
crontab -e
```

添加以下行（将 `/ai/openclaw-skills/quanlaidian-quotation-skill` 替换为实际安装路径）：

```cron
0 1 * * * cd /ai/openclaw-skills/quanlaidian-quotation-skill && python3 scripts/check_openclaw_update.py --apply >> /var/log/quanlaidian-skill-update.log 2>&1
```

### 手动检查与更新

```bash
# 仅检查版本，不更新
python3 scripts/check_openclaw_update.py

# 检查并自动拉取最新版本
python3 scripts/check_openclaw_update.py --apply
```

更新机制：对比本地 `VERSION` 与 GitHub 最新 Release tag，有新版本时执行 `git pull --ff-only origin main`，更新后需重载 OpenClaw 技能。

可通过环境变量覆盖默认配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SKILL_REPO` | `jasonshao/quanlaidian-quotation-skill` | GitHub 仓库地址 |
| `SKILL_LOCAL_DIR` | 脚本所在仓库根目录 | 本地安装路径 |

---

## 目录结构

```
quanlaidian-quotation-skill/
├── agents/openai.yaml                         # OpenClaw 技能入口元数据
├── scripts/
│   ├── run_openclaw_quotation.py              # 主入口：表单 → JSON+PDF+XLSX
│   ├── build_quotation_config.py              # 生成报价配置 JSON
│   ├── generate_quotation.py                  # 生成 PDF + Excel
│   ├── handle_feishu_quote_message.py         # 飞书多轮引导入口
│   ├── feishu_file_delivery.py                # 飞书文件消息发送
│   └── check_openclaw_update.py              # 版本检查与自动更新
├── references/
│   ├── product_catalog.md                     # 产品目录与标准售价
│   ├── sales_guide.md                         # 销售引导话术
│   ├── openclaw_form_schema.json              # 表单字段定义
│   ├── openclaw_form_config.json              # 表单 UI 配置
│   ├── openclaw_form_submission.example.json  # 表单提交示例
│   └── pricing_baseline_v5.obf               # 混淆价格基线（生产用）
├── docs/
│   ├── pricing-algorithm.md                   # 定价算法详细说明
│   └── dev-guide.md                           # 本地开发与调试
├── SKILL.md                                   # 技能触发规则与 Agent 交互策略
├── CHANGELOG.md                               # 版本变更记录
├── VERSION                                    # 当前版本号
└── requirements.txt                           # Python 依赖
```

---

## 更多文档

- [`SKILL.md`](SKILL.md) — 技能触发场景、Agent 交互策略、飞书下载实现要求
- [`docs/pricing-algorithm.md`](docs/pricing-algorithm.md) — 定价算法（small-segment-v2）详解
- [`docs/dev-guide.md`](docs/dev-guide.md) — 本地开发、版本发布、常见问题
- [`references/product_catalog.md`](references/product_catalog.md) — 产品目录与标准售价
- [`CHANGELOG.md`](CHANGELOG.md) — 版本变更记录
