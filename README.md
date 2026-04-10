# quanlaidian-quotation-skill

面向 OpenClaw 的全来店报价技能。

该技能用于把业务表单输入自动转换为三份标准报价产物：
- 对客 PDF 报价单
- 内部 Excel 报价单
- 结构化 JSON 报价配置

适用场景：销售/售前在 OpenClaw 中填写品牌、门店规模、套餐与模块后，一键生成可发客户的报价文件。

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
