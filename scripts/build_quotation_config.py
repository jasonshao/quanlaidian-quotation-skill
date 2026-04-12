#!/usr/bin/env python3
import argparse
import json
import math
import statistics
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
REFERENCES_DIR = ROOT_DIR / "references"
PRODUCT_CATALOG_PATH = REFERENCES_DIR / "product_catalog.md"
PRICING_BASELINE_PATH = REFERENCES_DIR / "pricing_baseline_v5.json"
SMALL_SEGMENT_MAX_STORES = 30
SMALL_SEGMENT_ALGORITHM_VERSION = "small-segment-v2"
HISTORY_WINDOW_MONTHS = 12
SMALL_SEGMENT_START_UNIT_PRICE = {
    "轻餐": 1800,
    "正餐": 3000,
}
# 每增加 1 店的成交价系数降幅。
# 当前值由 1 店/30 店锚点线性拟合得出，累计历史成交样本 ≥ 50 单后应重新回归校准。
DISCOUNT_SLOPE_PER_STORE = 0.05 / 19
# 31 店以上延伸推算时的系数下限，防止极端外推
FACTOR_FLOOR = 0.08
# 31 店以上仅提供参考报价，需人工确认
LARGE_SEGMENT_REFERENCE_ONLY_THRESHOLD = 30
# 动态带宽：至少需要这么多有效样本才启用标准差驱动
DYNAMIC_BANDWIDTH_MIN_SAMPLES = 10
DYNAMIC_BANDWIDTH_MIN = 0.01
DYNAMIC_BANDWIDTH_MAX = 0.05

PROTECTED_PRODUCT_NAMES = {
    "商管接口",
}


def is_protected_product(product_name):
    return any(keyword in str(product_name) for keyword in PROTECTED_PRODUCT_NAMES)


def as_bool(value, default=True):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def now_dt():
    return datetime.now()


def parse_date_maybe(value):
    if value in (None, ""):
        return None
    text = str(value).strip()
    patterns = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
    ]
    for p in patterns:
        try:
            return datetime.strptime(text, p)
        except ValueError:
            continue
    return None


def parse_money(value):
    text = str(value).strip().replace(",", "")
    if text == "赠送":
        return "赠送"
    return int(float(text))


def round_to_10(value):
    d = Decimal(str(value))
    return int((d / Decimal("10")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("10"))


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


def load_pricing_baseline(path=PRICING_BASELINE_PATH):
    if not path.exists():
        return {"items": []}
    return json.loads(path.read_text(encoding="utf-8"))


def build_pricing_baseline_index(baseline):
    exact = {}
    by_name = {}
    for item in baseline.get("items", []):
        meal_type = item.get("meal_type")
        group = item.get("group")
        name = item.get("name")
        cost_price = item.get("cost_price")
        if meal_type is None or group is None or name is None or cost_price is None:
            continue
        exact[(str(meal_type), str(group), str(name))] = float(cost_price)
        by_name.setdefault(str(name), float(cost_price))
    return {"exact": exact, "by_name": by_name}


def classify_catalog_group(group):
    return group


def compute_standard_price_by_group(group, product_name, cost_price):
    if group == "门店套餐":
        return int(round(float(cost_price) / 0.05))
    if group == "门店增值模块":
        if product_name == "商管接口":
            return int(round(float(cost_price)))
        return round_to_10(float(cost_price) * 1.10)
    if group == "总部模块":
        return round_to_10(float(cost_price) * 1.20)
    if group == "实施服务":
        return int(round(float(cost_price)))
    return int(round(float(cost_price)))


def resolve_product_pricing(product, quote_meal_type, baseline_index):
    group = classify_catalog_group(product["group"])
    name = product["name"]

    cost_price = baseline_index["exact"].get((quote_meal_type, group, name))
    if cost_price is None:
        cost_price = baseline_index["by_name"].get(name)

    if cost_price is None:
        # 缺失时回退旧目录价格，保证不中断
        fallback = product["price"]
        return int(fallback), int(fallback), "catalog_fallback"

    standard_price = compute_standard_price_by_group(group, name, cost_price)
    return int(standard_price), float(cost_price), "baseline_v5"


def _small_segment_bucket(store_count):
    if 1 <= store_count <= 10:
        return "small-1-10"
    # 21-30 延续 11-20 同桶规则，避免小样本分裂
    if 11 <= store_count <= 30:
        return "small-11-20"
    return None


def recommend_base_deal_price_factor_smooth(store_count, meal_type):
    # 起步锚点：轻餐 1 店 1800 元，正餐 1 店 3000 元
    start_factor_map = {
        "轻餐": SMALL_SEGMENT_START_UNIT_PRICE["轻餐"] / 7600,
        "正餐": SMALL_SEGMENT_START_UNIT_PRICE["正餐"] / 11120,
    }
    start_factor = start_factor_map[meal_type]
    # 统一线性公式（1-30 店连续，无折点）
    factor = start_factor - DISCOUNT_SLOPE_PER_STORE * (store_count - 1)
    # 31 店以上：延伸外推，但加 FACTOR_FLOOR 兜底，避免极端值
    return max(FACTOR_FLOOR, factor)


def small_segment_bounds(store_count, meal_type, sample_factors=None):
    center = recommend_base_deal_price_factor_smooth(store_count, meal_type)
    static_bandwidth = 0.02 if meal_type == "轻餐" else 0.015
    if sample_factors and len(sample_factors) >= DYNAMIC_BANDWIDTH_MIN_SAMPLES:
        # 用历史成交系数的标准差驱动带宽，减少人工审批频率
        dynamic_bw = round(1.5 * statistics.stdev(sample_factors), 4)
        bandwidth = min(DYNAMIC_BANDWIDTH_MAX, max(DYNAMIC_BANDWIDTH_MIN, dynamic_bw))
    else:
        bandwidth = static_bandwidth
    low = max(0.01, center - bandwidth)
    high = min(1.0, center + bandwidth)
    return round(low, 6), round(high, 6)


def percentile(sorted_values, q):
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def weighted_median(values, weights):
    if not values:
        return None
    pairs = sorted(zip(values, weights), key=lambda x: x[0])
    total_w = sum(w for _, w in pairs)
    if total_w <= 0:
        return pairs[len(pairs) // 2][0]
    acc = 0.0
    half = total_w / 2
    for value, weight in pairs:
        acc += weight
        if acc >= half:
            return value
    return pairs[-1][0]


def get_history_samples(form):
    samples = form.get("history_samples")
    if samples is None:
        samples = form.get("历史样本")
    if samples is None:
        return []
    if not isinstance(samples, list):
        raise ValueError("history_samples/历史样本 必须是数组")
    return samples


def extract_sample_factor(sample):
    if sample.get("deal_price_factor") is not None:
        return float(sample["deal_price_factor"])
    if sample.get("成交价系数") is not None:
        return float(sample["成交价系数"])
    if sample.get("折扣") is not None:
        return 1 - float(sample["折扣"])
    return None


def should_filter_history_sample(sample, meal_type, sample_bucket):
    if as_bool(sample.get("special_approval") or sample.get("特殊审批单"), False):
        return "special_approval"
    if as_bool(sample.get("is_gift") or sample.get("赠送单"), False):
        return "gift"
    if as_bool(sample.get("abnormal_manual_override") or sample.get("人工异常改价单"), False):
        return "abnormal_manual_override"
    if as_bool(sample.get("incomplete") or sample.get("数据不完整"), False):
        return "incomplete_data"
    if as_bool(sample.get("non_standard_package") or sample.get("非标准套餐"), False):
        return "non_standard_package"
    if sample.get("meal_type") and str(sample.get("meal_type")) != meal_type:
        return "cross_meal_type"

    sc = sample.get("store_count") or sample.get("门店数量")
    if sc is None:
        return "missing_store_count"
    sc = int(sc)
    if sc <= 0:
        return "invalid_store_count"
    if sc > SMALL_SEGMENT_MAX_STORES:
        return "out_of_small_segment"

    bucket = _small_segment_bucket(sc)
    if sample_bucket and bucket != sample_bucket:
        return "cross_bucket"

    dt = parse_date_maybe(
        sample.get("date")
        or sample.get("deal_date")
        or sample.get("quote_date")
        or sample.get("成交日期")
    )
    if dt is None:
        return "missing_date"
    days = (now_dt().date() - dt.date()).days
    if days < 0:
        return "future_date"

    factor = extract_sample_factor(sample)
    if factor is None:
        return "missing_factor"
    if not 0 < factor <= 1:
        return "invalid_factor"
    return None


def time_decay_weight(sample):
    dt = parse_date_maybe(
        sample.get("date")
        or sample.get("deal_date")
        or sample.get("quote_date")
        or sample.get("成交日期")
    )
    if dt is None:
        return 0.0
    age_days = (now_dt().date() - dt.date()).days
    # 12 个月线性衰减，保留最小权重避免完全失声
    base = max(0.1, 1 - age_days / float(HISTORY_WINDOW_MONTHS * 31))
    return round(base, 6)


def summarize_reasons(reason_list):
    counter = {}
    for reason in reason_list:
        counter[reason] = counter.get(reason, 0) + 1
    return [{"reason": k, "count": v} for k, v in sorted(counter.items(), key=lambda x: x[0])]


def history_weight_cap(sample_count):
    # 平滑指数曲线，避免"5 单 vs 6 单"的阶梯跳变。
    # 公式：0.25 × (1 − e^(−n/8))，渐近线为 0.25（即最多 25% 历史权重）。
    # 典型值：1 单≈3%，6 单≈13%，12 单≈22%，20 单≈24%，∞→25%。
    return round(0.25 * (1 - math.exp(-sample_count / 8)), 6)


def apply_history_adjustment(form, meal_type, sample_bucket, base_factor):
    raw_samples = get_history_samples(form)
    if not raw_samples:
        return {
            "final_factor": round(base_factor, 6),
            "history_sample_count": 0,
            "history_weight": 0.0,
            "history_anchor": None,
            "history_filtered_reason_summary": [],
            "accepted_sample_factors": [],
        }

    accepted = []
    filtered_reasons = []
    for sample in raw_samples:
        reason = should_filter_history_sample(sample, meal_type, sample_bucket)
        if reason is not None:
            filtered_reasons.append(reason)
            continue
        accepted.append(sample)

    sample_count = len(accepted)
    cap = history_weight_cap(sample_count)
    factors = [extract_sample_factor(s) for s in accepted]
    if cap == 0.0:
        return {
            "final_factor": round(base_factor, 6),
            "history_sample_count": sample_count,
            "history_weight": 0.0,
            "history_anchor": None,
            "history_filtered_reason_summary": summarize_reasons(filtered_reasons),
            "accepted_sample_factors": factors,
        }

    factors_sorted = sorted(factors)
    lo = percentile(factors_sorted, 0.1)
    hi = percentile(factors_sorted, 0.9)
    # 轻量 winsorize，降低极端低价/高价噪声影响
    winsorized = [min(hi, max(lo, f)) for f in factors]
    weights = [time_decay_weight(s) for s in accepted]
    anchor = weighted_median(winsorized, weights)

    final = base_factor * (1 - cap) + anchor * cap
    return {
        "final_factor": round(final, 6),
        "history_sample_count": sample_count,
        "history_weight": round(cap, 6),
        "history_anchor": round(anchor, 6),
        "history_filtered_reason_summary": summarize_reasons(filtered_reasons),
        "accepted_sample_factors": factors,
    }


def build_product_index(products):
    index = {}
    for product in products:
        index.setdefault(product["name"], []).append(product)
    return index


def _normalize_manual_reason(form):
    return str(
        form.get("人工改价原因")
        or form.get("manual_override_reason")
        or form.get("manual_override_reason_text")
        or ""
    ).strip()


def _extract_deal_price_factor_input(form):
    if form.get("deal_price_factor") is not None:
        return float(form["deal_price_factor"]), "deal_price_factor"
    if form.get("成交价系数") is not None:
        return float(form["成交价系数"]), "成交价系数"
    if form.get("折扣") is not None:
        # 兼容旧字段语义：折扣是减免比例，转换为成交价系数
        return 1 - float(form["折扣"]), "折扣(兼容转换)"
    return None, None


def normalize_deal_price_factor(form):
    store_count = int(form["门店数量"])
    meal_type = form["餐饮类型"]
    recommended_factor = recommend_base_deal_price_factor_smooth(store_count, meal_type)
    provided_factor, source = _extract_deal_price_factor_input(form)

    if provided_factor is None:
        return round(recommended_factor, 6), round(recommended_factor, 6), "auto"

    reason = _normalize_manual_reason(form)
    if not reason:
        raise ValueError("人工改价必须填写原因")
    if not 0 < provided_factor <= 1:
        raise ValueError("成交价系数必须在 (0, 1] 区间")
    return round(recommended_factor, 6), round(float(provided_factor), 6), source


def lookup_product(index, name, meal_type=None, group=None):
    candidates = index.get(name, [])
    if group is not None:
        candidates = [item for item in candidates if item["group"] == group]
    if meal_type is not None:
        candidates = [item for item in candidates if item["meal_type"] in {meal_type, "通用"}]
    if not candidates:
        raise ValueError(f"未找到匹配产品: {name}")
    return candidates[0]


def validate_form(form, product_index):
    required = ["客户品牌名称", "餐饮类型", "门店数量", "门店套餐"]
    missing = [key for key in required if form.get(key) in (None, "", [])]
    if missing:
        raise ValueError(f"缺少必填字段: {', '.join(missing)}")

    meal_type = form["餐饮类型"]
    if meal_type not in {"轻餐", "正餐"}:
        raise ValueError("餐饮类型必须为轻餐或正餐")

    if int(form["门店数量"]) <= 0:
        raise ValueError("门店数量必须大于 0")
    large_segment_reference_only = int(form["门店数量"]) > LARGE_SEGMENT_REFERENCE_ONLY_THRESHOLD

    recommended_factor, chosen_factor, factor_source = normalize_deal_price_factor(form)

    package = lookup_product(product_index, form["门店套餐"], group="门店套餐")
    if package["meal_type"] != meal_type:
        raise ValueError("餐饮类型与门店套餐不匹配")

    module_names = form.get("门店增值模块", [])
    for module_name in module_names:
        module = lookup_product(product_index, module_name, meal_type=meal_type, group="门店增值模块")
        if module["meal_type"] != meal_type:
            raise ValueError("餐饮类型与门店增值模块不匹配")

    protected_overrides = form.get("保护类商品改价", {}) or {}
    if not isinstance(protected_overrides, dict):
        raise ValueError("保护类商品改价字段必须为对象")
    for item_name in protected_overrides.keys():
        if is_protected_product(item_name):
            raise ValueError("保护类商品不允许人工改价")

    headquarter_modules = form.get("总部模块", [])
    if headquarter_modules:
        quantity_field_map = {
            "配送中心": "配送中心数量",
            "生产加工": "生产加工中心数量",
        }
        for module_name in headquarter_modules:
            quantity_field = quantity_field_map.get(module_name)
            if quantity_field is None:
                raise ValueError(f"总部模块不支持: {module_name}")
            if quantity_field not in form:
                raise ValueError(f"勾选总部模块后必须填写 {quantity_field}")
            if int(form.get(quantity_field, 0)) <= 0:
                raise ValueError(f"勾选总部模块后 {quantity_field} 必须大于 0")
            lookup_product(product_index, module_name, meal_type=meal_type, group="总部模块")
    for field in ("配送中心数量", "生产加工中心数量"):
        if field in form and int(form[field]) < 0:
            raise ValueError(f"{field} 必须大于等于 0")

    implementation_type = (form.get("实施服务类型") or "").strip()
    implementation_days = int(form.get("实施服务人天", 0) or 0)
    if implementation_type and implementation_days <= 0:
        raise ValueError("选择实施服务后必须填写实施服务人天")
    if implementation_days > 0 and not implementation_type:
        raise ValueError("填写实施服务人天时必须选择实施服务类型")

    return {
        "recommended_factor": recommended_factor,
        "deal_price_factor": chosen_factor,
        "factor_source": factor_source,
        "large_segment_reference_only": large_segment_reference_only,
    }


def build_quote_item(product, standard_price, quantity, deal_price_factor, category, module_category):
    protected = is_protected_product(product["name"])
    item_factor = 1.0 if protected else deal_price_factor
    return {
        "商品分类": category,
        "商品名称": product["name"],
        "单位": product["unit"],
        "标准价": standard_price,
        "成交价系数": item_factor,
        "deal_price_factor": item_factor,
        # 兼容旧渲染字段，语义为折扣减免比例
        "折扣": round(1 - item_factor, 6),
        "数量": quantity,
        "模块分类": module_category,
        "protected_item_bypass": protected,
    }


def default_terms():
    return [
        "以上报价金额均为含税金额，税率为6%",
        "报价有效期为30个工作日，自报价单生成之日起",
        "具体折扣金额按签订合同（或销售订单）时具体数量确定价格",
        "涉及短信、小程序授权、外卖平台接口调用等第三方机构收费部分，需单独计费",
        "如需要三方代仓对接，需要一事一议",
    ]


def build_tier_config(enabled, meal_type):
    if not enabled:
        return []
    candidates = [10, 20, 30]
    tiers = []
    for count in candidates:
        factor = round(recommend_base_deal_price_factor_smooth(count, meal_type), 6)
        tiers.append({
            "标签": f"{count}店方案",
            "门店数": count,
            "成交价系数": factor,
            "deal_price_factor": factor,
        })
    return tiers


def build_manual_override_audit(form, recommended_factor, final_factor, bounded_range, factor_source):
    reason = _normalize_manual_reason(form)
    is_manual = factor_source != "auto"
    if not is_manual:
        return {
            "manual_override": False,
            "manual_override_reason": None,
            "manual_override_before_factor": None,
            "manual_override_after_factor": None,
            "manual_override_operator": None,
            "manual_override_time": None,
            "manual_override_outside_band": False,
        }
    operator = (
        form.get("operator")
        or form.get("操作人")
        or form.get("sales_name")
        or form.get("销售")
        or "unknown"
    )
    op_time = (
        form.get("manual_override_time")
        or form.get("操作时间")
        or form.get("override_time")
        or now_dt().strftime("%Y-%m-%d %H:%M:%S")
    )
    out_of_band = False
    if bounded_range:
        out_of_band = final_factor < bounded_range[0] or final_factor > bounded_range[1]
    return {
        "manual_override": True,
        "manual_override_reason": reason,
        "manual_override_before_factor": round(recommended_factor, 6),
        "manual_override_after_factor": round(final_factor, 6),
        "manual_override_operator": str(operator),
        "manual_override_time": str(op_time),
        "manual_override_outside_band": out_of_band,
    }


def build_approval_decision(
    base_factor,
    final_factor,
    history_sample_count,
    manual_override,
    protected_item_bypass,
):
    reasons = []
    if final_factor < (base_factor - 0.02):
        reasons.append("final_factor_below_base_minus_0.02:director_approval")
    elif final_factor < (base_factor - 0.01):
        reasons.append("final_factor_below_base_minus_0.01:manager_approval")

    if manual_override and history_sample_count < 6:
        reasons.append("manual_override_without_sufficient_history")

    # 保护类商品已硬保护；这里保留审计提示，便于监控拦截链路
    if protected_item_bypass:
        reasons.append("protected_item_bypass_applied")

    return {
        "approval_required": len(reasons) > 0,
        "approval_reason": reasons,
    }


def build_quotation_config(form, quote_date=None):
    products = load_product_catalog()
    baseline = load_pricing_baseline()
    baseline_index = build_pricing_baseline_index(baseline)
    product_index = build_product_index(products)
    meal_type = form["餐饮类型"]
    store_count = int(form["门店数量"])
    normalized = validate_form(form, product_index)
    deal_price_factor = normalized["deal_price_factor"]
    recommended_factor = normalized["recommended_factor"]
    sample_bucket = _small_segment_bucket(store_count)

    # 仅在自动推荐时启用历史拟合，人工改价保持显式输入优先
    if normalized["factor_source"] == "auto":
        history_adjusted = apply_history_adjustment(
            form=form,
            meal_type=meal_type,
            sample_bucket=sample_bucket,
            base_factor=deal_price_factor,
        )
        deal_price_factor = history_adjusted["final_factor"]
        accepted_sample_factors = history_adjusted["accepted_sample_factors"]
        history_meta = {
            "history_sample_count": history_adjusted["history_sample_count"],
            "history_weight": history_adjusted["history_weight"],
            "history_anchor": history_adjusted["history_anchor"],
            "history_filtered_reason_summary": history_adjusted["history_filtered_reason_summary"],
        }
    else:
        accepted_sample_factors = []
        history_meta = {
            "history_sample_count": 0,
            "history_weight": 0.0,
            "history_anchor": None,
            "history_filtered_reason_summary": [{"reason": "manual_override_skip_history", "count": 1}],
        }

    auto_adjustments = []
    if history_meta["history_weight"] > 0:
        auto_adjustments.append({
            "name": "history_adjustment",
            "weight": history_meta["history_weight"],
            "anchor": history_meta["history_anchor"],
        })

    lower, upper = small_segment_bounds(store_count, meal_type, accepted_sample_factors)
    pre_bound_factor = deal_price_factor
    deal_price_factor = round(min(upper, max(lower, deal_price_factor)), 6)
    bounded_range = [lower, upper]
    if round(pre_bound_factor, 6) != round(deal_price_factor, 6):
        auto_adjustments.append({
            "name": "bounded_clamp",
            "before": round(pre_bound_factor, 6),
            "after": round(deal_price_factor, 6),
            "range": bounded_range,
        })

    quote_date = quote_date or datetime.now().strftime("%Y年%m月%d日")
    items = []

    package = lookup_product(product_index, form["门店套餐"], meal_type=meal_type, group="门店套餐")
    package_standard_price, _, _ = resolve_product_pricing(package, meal_type, baseline_index)
    items.append(build_quote_item(package, package_standard_price, store_count, deal_price_factor, "标准软件套餐", "门店软件套餐"))

    for module_name in form.get("门店增值模块", []):
        module = lookup_product(product_index, module_name, meal_type=meal_type, group="门店增值模块")
        item_factor = min(1.0, round(deal_price_factor + 0.03, 6))
        category = "保护类商品" if is_protected_product(module["name"]) else "增值模块"
        standard_price, _, _ = resolve_product_pricing(module, meal_type, baseline_index)
        items.append(build_quote_item(module, standard_price, store_count, item_factor, category, "门店增值模块"))

    for module_name in form.get("总部模块", []):
        quantity_field = {
            "配送中心": "配送中心数量",
            "生产加工": "生产加工中心数量",
        }.get(module_name)
        quantity = int(form.get(quantity_field, 0)) if quantity_field else 0
        if quantity <= 0:
            continue
        module = lookup_product(product_index, module_name, meal_type=meal_type, group="总部模块")
        category = "保护类商品" if is_protected_product(module["name"]) else "总部模块"
        standard_price, _, _ = resolve_product_pricing(module, meal_type, baseline_index)
        items.append(build_quote_item(module, standard_price, quantity, deal_price_factor, category, "总部模块"))

    implementation_type = form.get("实施服务类型")
    implementation_days = int(form.get("实施服务人天", 0) or 0)
    if implementation_type and implementation_days > 0:
        service = lookup_product(product_index, implementation_type, group="实施服务")
        standard_price, _, _ = resolve_product_pricing(service, meal_type, baseline_index)
        items.append(build_quote_item(service, standard_price, implementation_days, 1.0, "实施服务", "实施服务"))

    protected_bypass_count = sum(1 for item in items if item.get("protected_item_bypass"))
    if protected_bypass_count > 0:
        auto_adjustments.append({
            "name": "protected_item_bypass",
            "count": protected_bypass_count,
        })

    manual_audit = build_manual_override_audit(
        form=form,
        recommended_factor=recommended_factor,
        final_factor=deal_price_factor,
        bounded_range=bounded_range,
        factor_source=normalized["factor_source"],
    )
    approval = build_approval_decision(
        base_factor=recommended_factor,
        final_factor=deal_price_factor,
        history_sample_count=history_meta["history_sample_count"],
        manual_override=manual_audit["manual_override"],
        protected_item_bypass=protected_bypass_count > 0,
    )

    config = {
        "客户信息": {
            "公司名称": form["客户品牌名称"],
        },
        "报价日期": quote_date,
        "报价有效期": "30个工作日",
        "餐饮类型": meal_type,
        "门店数量": store_count,
        "报价项目": items,
        "条款": default_terms(),
        "pricing_info": {
            "algorithm_version": SMALL_SEGMENT_ALGORITHM_VERSION,
            "large_segment_reference_only": normalized["large_segment_reference_only"],
            "sample_bucket": sample_bucket,
            "base_factor": round(recommended_factor, 6),
            "auto_adjustments": auto_adjustments,
            "bounded_range": bounded_range,
            "final_factor": round(deal_price_factor, 6),
            "deal_price_factor_source": normalized["factor_source"],
            "protected_item_bypass": protected_bypass_count > 0,
            "history_sample_count": history_meta["history_sample_count"],
            "history_weight": history_meta["history_weight"],
            "history_anchor": history_meta["history_anchor"],
            "history_window_months": HISTORY_WINDOW_MONTHS,
            "history_filtered_reason_summary": history_meta["history_filtered_reason_summary"],
            "approval_required": approval["approval_required"],
            "approval_reason": approval["approval_reason"],
            "manual_override_reason": manual_audit["manual_override_reason"],
            "manual_override_audit": {
                "enabled": manual_audit["manual_override"],
                "before_factor": manual_audit["manual_override_before_factor"],
                "after_factor": manual_audit["manual_override_after_factor"],
                "operator": manual_audit["manual_override_operator"],
                "time": manual_audit["manual_override_time"],
                "outside_band": manual_audit["manual_override_outside_band"],
            },
        },
    }

    tiers = build_tier_config(form.get("是否启用阶梯报价"), meal_type)
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
