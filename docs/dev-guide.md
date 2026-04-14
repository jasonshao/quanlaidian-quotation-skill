# 本地开发与调试指南

## 环境准备

```bash
git clone https://github.com/jasonshao/quanlaidian-quotation-skill.git
cd quanlaidian-quotation-skill
python3 -m pip install -r requirements.txt
```

## 配置密钥

```bash
export PRICING_BASELINE_KEY=请替换为部署密钥
export PRICING_BASELINE_STRICT=1   # 生产环境建议开启
```

密钥请通过 CI/CD Secret、容器环境变量或密钥管理系统注入，不要写入仓库。

## 常用命令

### 仅生成报价配置 JSON

```bash
python3 scripts/build_quotation_config.py \
  --form references/openclaw_form_submission.example.json \
  --output 输出报价配置.json
```

### 生成完整报价文件（JSON + PDF + XLSX）

```bash
python3 scripts/run_openclaw_quotation.py \
  --form references/openclaw_form_submission.example.json \
  --output-dir ./mount_test_output
```

输出文件在 `mount_test_output/` 目录：

- `品牌名-全来店-报价配置-YYYYMMDD.json`
- `品牌名-全来店-报价单-YYYYMMDD.pdf`
- `品牌名-全来店-报价单-YYYYMMDD.xlsx`

### 利润测算

```bash
python3 scripts/generate_quotation.py \
  --config 报价配置.json \
  --output 报价单.pdf \
  --profit \
  --cost-data references/pricing_baseline_v5.json
```

### 提取价格基线（从 Excel 底价单）

```bash
python3 scripts/extract_pricing_baseline_v5.py \
  --xlsx 底价单V5.xlsx \
  --output references/pricing_baseline_v5.json
```

提取后混淆：

```bash
python3 scripts/obfuscate_pricing_baseline.py \
  --input references/pricing_baseline_v5.json \
  --output references/pricing_baseline_v5.obf
```

### 版本递增

```bash
# 预览
python3 scripts/bump_version.py

# 应用（默认按 patch 递增）
python3 scripts/bump_version.py --write

# 指定递增级别
python3 scripts/bump_version.py --part minor --write
```

## 版本发布流程

1. 更新 `VERSION`（例如 `0.1.0` → `0.2.0`）
2. 更新 `CHANGELOG.md`
3. 合并到 `main` 后创建 GitHub Release（tag 建议为 `v0.2.0`）

自动化：`main` 每次有新提交会触发 `.github/workflows/auto-bump-version.yml`，按 `patch` 自动递增版本并追加 CHANGELOG。

## 常见问题

**运行时报缺少依赖**
- 执行 `python3 -m pip install -r requirements.txt`

**报错"未找到匹配产品"**
- 检查表单里的套餐/模块名称是否与 `references/product_catalog.md` 完全一致

**结果文件没有生成**
- 检查 `--form` 路径是否正确、字段是否齐全，或查看终端错误信息

**报错"检测到混淆基线文件但缺少 PRICING_BASELINE_KEY"**
- 运行前注入 `PRICING_BASELINE_KEY`；生产建议同时开启 `PRICING_BASELINE_STRICT=1`
