#!/usr/bin/env python3
import argparse
import json
import re
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = ROOT_DIR / "references"
PRODUCT_CATALOG_PATH = REFERENCES_DIR / "product_catalog.md"
DISCOUNT_RULES_PATH = REFERENCES_DIR / "discount_rules.json"


def parse_money(value):
    text = str(value).strip().replace(",", "")
    if text == "赠送":
        return "赠送"
    return int(float(text))


def parse_markdown_table(lines):
    table_lines = [line.strip() for line in lines if line.strip()]
    headers = [cell.strip() for cell in table_lines[0].strip("|").split("|")]
    rows = []
    for line in table_lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != len(headers):
            continue
        rows.append(dict(zip(headers, cells)))
    return rows


def load_product_catalog(path=PRODUCT_CATALOG_PATH):
    meal_type = None
    group = None
    table_lines = []
    products = []

    def flush_table():
        nonlocal table_lines, products, meal_type, group
        if not table_lines:
            return
        for row in parse_markdown_table(table_lines):
            name_key = next(
                (key for key in row.keys() if key in {"套餐名称", "模块名称", "设备名称", "服务名称"}),
                None,
            )
            price_key = next((key for key in row.keys() if "标准售价" in key), None)
            if name_key is None or price_key is None or "单位" not in row:
                continue
            products.append({
                "meal_type": meal_type,
                "group": group,
                "name": row[name_key],
                "unit": row["单位"],
                "price": parse_money(row[price_key]),
            })
        table_lines = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## 一、轻餐产品线"):
            flush_table()
            meal_type = "轻餐"
            group = None
            continue
        if line.startswith("## 二、正餐产品线"):
            flush_table()
            meal_type = "正餐"
            group = None
            continue
        if line.startswith("## 三、硬件设备"):
            flush_table()
            meal_type = "通用"
            group = "硬件设备"
            continue
        if line.startswith("## 四、实施服务"):
            flush_table()
            meal_type = "通用"
            group = "实施服务"
            continue
        if line.startswith("### 1. 门店套餐"):
            flush_table()
            group = "门店套餐"
            continue
        if line.startswith("### 2. 门店增值模块"):
            flush_table()
            group = "门店增值模块"
            continue
        if line.startswith("### 3. 总部模块"):
            flush_table()
            group = "总部模块"
            continue
        if line.startswith("|"):
            table_lines.append(line)
            continue
        if table_lines:
            flush_table()

    flush_table()
    return products


def load_discount_rules(path=DISCOUNT_RULES_PATH):
    return json.loads(path.read_text(encoding="utf-8"))


def parse_store_scale(scale_text):
    if scale_text == "300店以上":
        return 301, None
    matched = re.match(r"(\d+)-(\d+)店", scale_text)
    if not matched:
        raise ValueError(f"无法解析门店规模规则: {scale_text}")
    return int(matched.group(1)), int(matched.group(2))


def recommend_discount(store_count, rules=None):
    rules = rules or load_discount_rules()
    for rule in rules["折扣规则"]["按门店规模"]:
        start, end = parse_store_scale(rule["规模"])
        if end is None and store_count >= start:
            return rule["建议折扣"]
        if start <= store_count <= end:
            return rule["建议折扣"]
    return 0


def build_product_index(products):
    index = {}
    for product in products:
        index.setdefault(product["name"], []).append(product)
    return index


def normalize_discount(form, rules):
    store_count = int(form["门店数量"])
    recommended = recommend_discount(store_count, rules=rules)
    discount = form.get("折扣", recommended)
    discount = float(discount)
    if not 0 <= discount <= rules["折扣上限"]["软件套餐最大折扣"]:
        raise ValueError("折扣超出系统允许上限")
    return recommended, discount


def lookup_product(index, name, meal_type=None, group=None):
    candidates = index.get(name, [])
    if group is not None:
        candidates = [item for item in candidates if item["group"] == group]
    if meal_type is not None:
        candidates = [item for item in candidates if item["meal_type"] in {meal_type, "通用"}]
    if not candidates:
        raise ValueError(f"未找到匹配产品: {name}")
    return candidates[0]


def validate_form(form, product_index, rules):
    required = ["客户品牌名称", "餐饮类型", "门店数量", "门店套餐"]
    missing = [key for key in required if form.get(key) in (None, "", [])]
    if missing:
        raise ValueError(f"缺少必填字段: {', '.join(missing)}")

    meal_type = form["餐饮类型"]
    if meal_type not in {"轻餐", "正餐"}:
        raise ValueError("餐饮类型必须为轻餐或正餐")

    if int(form["门店数量"]) <= 0:
        raise ValueError("门店数量必须大于 0")

    _, discount = normalize_discount(form, rules)

    package = lookup_product(product_index, form["门店套餐"], group="门店套餐")
    if package["meal_type"] != meal_type:
        raise ValueError("餐饮类型与门店套餐不匹配")

    for module_name in form.get("门店增值模块", []):
        module = lookup_product(product_index, module_name, group="门店增值模块")
        if module["meal_type"] != meal_type:
            raise ValueError("餐饮类型与门店增值模块不匹配")

    headquarter_modules = form.get("总部模块", [])
    if headquarter_modules:
        for field in ("配送中心数量", "生产加工中心数量"):
            if field in form and int(form[field]) < 0:
                raise ValueError(f"{field} 必须大于等于 0")
        for module_name in headquarter_modules:
            lookup_product(product_index, module_name, meal_type=meal_type, group="总部模块")

    return discount


def build_quote_item(product, quantity, discount, category, module_category):
    return {
        "商品分类": category,
        "商品名称": product["name"],
        "单位": product["unit"],
        "标准价": product["price"],
        "折扣": discount,
        "数量": quantity,
        "模块分类": module_category,
    }


def default_terms():
    return [
        "以上报价金额均为含税金额，税率为6%",
        "报价有效期为30个工作日，自报价单生成之日起",
        "具体折扣金额按签订合同（或销售订单）时具体数量确定价格",
        "涉及短信、小程序授权、外卖平台接口调用等第三方机构收费部分，需单独计费",
        "如需要三方代仓对接，需要一事一议",
    ]


def build_tier_config(enabled, rules):
    if not enabled:
        return []
    candidates = [30, 50, 100]
    tiers = []
    for count in candidates:
        discount = recommend_discount(count, rules=rules)
        tiers.append({
            "标签": f"{count}店方案",
            "门店数": count,
            "折扣": discount,
        })
    return tiers


def build_quotation_config(form, quote_date=None):
    products = load_product_catalog()
    product_index = build_product_index(products)
    rules = load_discount_rules()
    discount = validate_form(form, product_index, rules)

    meal_type = form["餐饮类型"]
    store_count = int(form["门店数量"])
    quote_date = quote_date or datetime.now().strftime("%Y年%m月%d日")
    items = []

    package = lookup_product(product_index, form["门店套餐"], meal_type=meal_type, group="门店套餐")
    items.append(build_quote_item(package, store_count, discount, "门店套餐", "门店软件套餐"))

    for module_name in form.get("门店增值模块", []):
        module = lookup_product(product_index, module_name, meal_type=meal_type, group="门店增值模块")
        items.append(build_quote_item(module, store_count, discount, "门店增值模块", "门店增值模块"))

    for module_name in form.get("总部模块", []):
        quantity_field = {
            "配送中心": "配送中心数量",
            "生产加工": "生产加工中心数量",
        }.get(module_name)
        quantity = int(form.get(quantity_field, 0)) if quantity_field else 0
        if quantity <= 0:
            continue
        module = lookup_product(product_index, module_name, meal_type=meal_type, group="总部模块")
        items.append(build_quote_item(module, quantity, discount, "总部模块", "总部模块"))

    implementation_type = form.get("实施服务类型")
    implementation_days = int(form.get("实施服务人天", 0) or 0)
    if implementation_type and implementation_days > 0:
        service = lookup_product(product_index, implementation_type, group="实施服务")
        items.append(build_quote_item(service, implementation_days, discount, "实施服务", "实施服务"))

    config = {
        "客户信息": {
            "公司名称": form["客户品牌名称"],
        },
        "报价日期": quote_date,
        "报价有效期": "30个工作日",
        "门店数量": store_count,
        "报价项目": items,
        "条款": default_terms(),
    }

    tiers = build_tier_config(form.get("是否启用阶梯报价"), rules)
    if tiers:
        config["阶梯配置"] = tiers
    return config


def main(argv=None):
    parser = argparse.ArgumentParser(description="从业务表单生成全来店报价 JSON")
    parser.add_argument("--form", required=True, help="业务表单 JSON 文件")
    parser.add_argument("--output", required=True, help="标准报价 JSON 输出路径")
    args = parser.parse_args(argv)

    form = json.loads(Path(args.form).read_text(encoding="utf-8"))
    config = build_quotation_config(form)
    Path(args.output).write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
