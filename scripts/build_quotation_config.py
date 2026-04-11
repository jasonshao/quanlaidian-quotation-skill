#!/usr/bin/env python3
import argparse
import json
import math
import re
import statistics
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = ROOT_DIR / "references"
PRODUCT_CATALOG_PATH = REFERENCES_DIR / "product_catalog.md"
DISCOUNT_RULES_PATH = REFERENCES_DIR / "discount_rules.json"
HISTORY_CASEBASE_PATH = ROOT_DIR / "data" / "history_quote_cases.jsonl"


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


def load_history_casebase(path=HISTORY_CASEBASE_PATH):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def parse_store_scale(scale_text):
    match = re.match(r"(\d+)店以上", scale_text)
    if match:
        return int(match.group(1)) + 1, None
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


def clamp_discount(discount, rules):
    upper = rules["折扣上限"]["软件套餐最大折扣"]
    return max(0.0, min(round(float(discount), 4), upper))


def clamp_discount_range(discount, lower_bound, upper_bound):
    return round(max(float(lower_bound), min(float(discount), float(upper_bound))), 4)


def get_history_fit_params(meal_type, rules):
    defaults = {
        "最大历史权重": 0.75,
        "样本饱和值": 6,
        "样本置信权重": 0.55,
        "均匀度置信权重": 0.45,
        "均值权重基础": 0.35,
        "均值权重均匀度增益": 0.35,
    }
    params = dict(defaults)
    params.update(rules.get("历史拟合参数", {}).get(meal_type, {}))
    return params


def get_history_fit_bounds(store_count, meal_type, rules):
    meal_bounds = rules.get("历史拟合折扣约束", {}).get(meal_type, [])
    for row in meal_bounds:
        start, end = parse_store_scale(row["规模"])
        if end is None and store_count >= start:
            return float(row["最小折扣"]), float(row["最大折扣"])
        if start <= store_count <= end:
            return float(row["最小折扣"]), float(row["最大折扣"])
    upper = float(rules["折扣上限"]["软件套餐最大折扣"])
    return 0.0, upper


def _extract_package_unit_price(case, package_name):
    for item in case.get("line_items", []):
        if item.get("product_name") != package_name:
            continue
        quantity = item.get("quantity")
        subtotal = item.get("subtotal")
        if isinstance(quantity, (int, float)) and quantity > 0 and isinstance(subtotal, (int, float)):
            per_unit = float(subtotal) / float(quantity)
            if per_unit > 0:
                return per_unit
        unit_price = item.get("discounted_unit_price")
        if isinstance(unit_price, (int, float)) and unit_price > 0:
            return float(unit_price)
    return None


def collect_package_price_samples(package_name, meal_type, casebase):
    samples = []
    for case in casebase or []:
        if case.get("raw_extract_status") != "parsed":
            continue
        if case.get("selected_package") != package_name:
            continue
        if meal_type and case.get("meal_type") not in (meal_type, None):
            continue
        store_count = case.get("store_count")
        if not isinstance(store_count, int) or store_count <= 0:
            continue
        unit_price = _extract_package_unit_price(case, package_name)
        if unit_price is None:
            continue
        samples.append({
            "store_count": store_count,
            "unit_price": round(unit_price, 2),
        })
    return samples


def _sample_weight(target_store_count, sample_store_count):
    if target_store_count <= 0 or sample_store_count <= 0:
        return 0.0
    distance = abs(math.log1p(target_store_count) - math.log1p(sample_store_count))
    return 1.0 / (1.0 + distance)


def _weighted_mean(samples, target_store_count):
    weighted_total = 0.0
    weight_sum = 0.0
    for sample in samples:
        weight = _sample_weight(target_store_count, sample["store_count"])
        weighted_total += sample["unit_price"] * weight
        weight_sum += weight
    if weight_sum == 0:
        return 0.0
    return weighted_total / weight_sum


def _weighted_median(samples, target_store_count):
    weighted = []
    for sample in samples:
        weight = _sample_weight(target_store_count, sample["store_count"])
        weighted.append((sample["unit_price"], weight))
    weighted.sort(key=lambda item: item[0])
    total_weight = sum(weight for _, weight in weighted)
    if total_weight == 0:
        return 0.0
    threshold = total_weight / 2
    running = 0.0
    for value, weight in weighted:
        running += weight
        if running >= threshold:
            return value
    return weighted[-1][0]


def _distribution_uniformity(samples):
    if not samples:
        return 0.0
    counter = Counter(sample["store_count"] for sample in samples)
    unique_factor = min(1.0, len(counter) / 5.0)
    if len(counter) == 1:
        entropy_factor = 0.0
    else:
        total = sum(counter.values())
        entropy = -sum((count / total) * math.log(count / total) for count in counter.values())
        entropy_factor = entropy / math.log(len(counter))
    return round(0.5 * unique_factor + 0.5 * entropy_factor, 4)


def recommend_discount_from_history(store_count, package, meal_type, rules=None, casebase=None):
    rules = rules or load_discount_rules()
    base_discount = recommend_discount(store_count, rules=rules)
    standard_price = float(package["price"])
    base_unit_price = standard_price * base_discount
    samples = collect_package_price_samples(package["name"], meal_type, casebase or [])
    fit_params = get_history_fit_params(meal_type, rules)
    lower_bound, upper_bound = get_history_fit_bounds(store_count, meal_type, rules)
    pricing_info = {
        "基础折扣": round(base_discount, 4),
        "建议折扣": round(base_discount, 4),
        "历史拟合折扣": round(base_discount, 4),
        "最终折扣": round(base_discount, 4),
        "历史样本数": len(samples),
        "历史拟合已启用": False,
        "历史均值单价": None,
        "历史中位数单价": None,
        "拟合单价": round(base_unit_price, 2),
        "历史权重": 0.0,
        "分布均匀度": 0.0,
        "历史拟合参数体系": meal_type,
        "历史拟合折扣下限": round(lower_bound, 4),
        "历史拟合折扣上限": round(upper_bound, 4),
    }
    if len(samples) < 2:
        return pricing_info

    weighted_mean = _weighted_mean(samples, store_count)
    weighted_median = _weighted_median(samples, store_count)
    uniformity = _distribution_uniformity(samples)
    sample_factor = min(1.0, len(samples) / float(fit_params["样本饱和值"]))
    confidence = min(
        1.0,
        float(fit_params["样本置信权重"]) * sample_factor
        + float(fit_params["均匀度置信权重"]) * uniformity,
    )
    mean_weight = float(fit_params["均值权重基础"]) + float(fit_params["均值权重均匀度增益"]) * uniformity
    history_anchor = weighted_mean * mean_weight + weighted_median * (1.0 - mean_weight)
    history_weight = min(float(fit_params["最大历史权重"]), float(fit_params["最大历史权重"]) * confidence)
    fitted_unit_price = base_unit_price * (1.0 - history_weight) + history_anchor * history_weight
    fitted_discount = clamp_discount(fitted_unit_price / standard_price, rules)
    fitted_discount = clamp_discount_range(fitted_discount, lower_bound, upper_bound)

    pricing_info.update({
        "建议折扣": fitted_discount,
        "历史拟合折扣": fitted_discount,
        "历史拟合已启用": True,
        "历史均值单价": round(weighted_mean, 2),
        "历史中位数单价": round(weighted_median, 2),
        "拟合单价": round(fitted_unit_price, 2),
        "历史权重": round(history_weight, 4),
        "分布均匀度": round(uniformity, 4),
    })
    return pricing_info


def resolve_discount(form, package, rules, casebase=None):
    store_count = int(form["门店数量"])
    pricing_info = recommend_discount_from_history(
        store_count,
        package=package,
        meal_type=form["餐饮类型"],
        rules=rules,
        casebase=casebase,
    )
    recommended = pricing_info["建议折扣"]
    discount = form.get("折扣", recommended)
    discount = float(discount)
    if not 0 <= discount <= rules["折扣上限"]["软件套餐最大折扣"]:
        raise ValueError("折扣超出系统允许上限")
    discount = round(discount, 4)
    pricing_info["最终折扣"] = discount
    return pricing_info, discount


def lookup_product(index, name, meal_type=None, group=None):
    candidates = index.get(name, [])
    if group is not None:
        candidates = [item for item in candidates if item["group"] == group]
    if meal_type is not None:
        candidates = [item for item in candidates if item["meal_type"] in {meal_type, "通用"}]
    if not candidates:
        raise ValueError(f"未找到匹配产品: {name}")
    return candidates[0]


def validate_form(form, product_index, rules, casebase=None):
    required = ["客户品牌名称", "餐饮类型", "门店数量", "门店套餐"]
    missing = [key for key in required if form.get(key) in (None, "", [])]
    if missing:
        raise ValueError(f"缺少必填字段: {', '.join(missing)}")

    meal_type = form["餐饮类型"]
    if meal_type not in {"轻餐", "正餐"}:
        raise ValueError("餐饮类型必须为轻餐或正餐")

    if int(form["门店数量"]) <= 0:
        raise ValueError("门店数量必须大于 0")

    package = lookup_product(product_index, form["门店套餐"], group="门店套餐")
    if package["meal_type"] != meal_type:
        raise ValueError("餐饮类型与门店套餐不匹配")

    pricing_info, discount = resolve_discount(form, package, rules, casebase=casebase)

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

    return package, pricing_info, discount


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


def build_tier_config(enabled, rules, package=None, meal_type=None, casebase=None):
    if not enabled:
        return []
    candidates = [30, 50, 100]
    tiers = []
    for count in candidates:
        discount = recommend_discount(count, rules=rules)
        if package and meal_type:
            discount = recommend_discount_from_history(
                count,
                package=package,
                meal_type=meal_type,
                rules=rules,
                casebase=casebase,
            )["建议折扣"]
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
    history_casebase = load_history_casebase()
    package, pricing_info, discount = validate_form(form, product_index, rules, casebase=history_casebase)

    meal_type = form["餐饮类型"]
    store_count = int(form["门店数量"])
    quote_date = quote_date or datetime.now().strftime("%Y年%m月%d日")
    items = []

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
        "定价信息": pricing_info,
        "条款": default_terms(),
    }

    tiers = build_tier_config(
        form.get("是否启用阶梯报价"),
        rules,
        package=package,
        meal_type=meal_type,
        casebase=history_casebase,
    )
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
