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
4. 在当前工作目录返回三份结果文件

## 输出结果

默认输出：

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
- `references/discount_rules.json`
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

## 约束

- 报价单抬头仅展示品牌名称
- 本期不包含硬件报价
- 若折扣超出建议范围，需要明确提示风险
- 若配置或依赖异常，优先返回清晰错误，而不是静默失败
