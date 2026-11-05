"""Deterministic pharmaceutical metrics. Never executes generated SQL or model output."""

from collections import defaultdict
from datetime import date
from decimal import Decimal as D
from html import escape
from .catalog import APPS, SEMANTICS, VERSION, digest


def dec(value):
    value = D(str(value))
    if not value.is_finite():
        raise ValueError("金额必须为有限数值")
    return value


def total(rows, field):
    return sum((dec(row[field]) for row in rows), D(0))


def amount(value):
    return str(dec(value).quantize(D(".01")))


def ratio(n, d):
    return amount(n / d * 100) if d > 0 else None


def analyze(data, *, app_id, period, entity="all"):
    definition = next((a for a in APPS if a[0] == app_id), None)
    if definition is None:
        raise ValueError("未知医药应用")
    entities = {r["entity_id"] for r in data["entities"]}
    if entity != "all" and entity not in entities:
        raise ValueError("主体不在授权数据范围内")
    rows = {
        key: [
            r
            for r in values
            if r.get("period") == period
            and (entity == "all" or r.get("entity_id") == entity)
        ]
        for key, values in data.items()
        if key not in ("entities", "products")
    }
    monthly = rows["monthly"]
    if not monthly or (
        entity == "all" and {r["entity_id"] for r in monthly} != entities
    ):
        raise ValueError("期间缺失或主体覆盖不完整")
    if any(r["budget_version"] != "approved-v1" for r in monthly):
        raise ValueError("预算版本不匹配")
    revenue = total(monthly, "revenue")
    cost = total(monthly, "cost")
    expense = total(monthly, "expense")
    consolidated = entity == "all" and {"MFG", "DIST"}.issubset(entities)
    eliminated = total(monthly, "internal_revenue") if consolidated else D(0)
    # Assumption: intra-group goods all sold externally. Eliminate transfer revenue
    # and the same transfer cost, never eliminate the seller's original cost.
    external_revenue = revenue - eliminated
    external_cost = cost - eliminated
    metrics = {}
    tables = []
    warnings = [
        "模拟业务数据，仅供演示。",
        "分析草稿，需人工复核；不自动认定减值或资本化。",
    ]
    if any(dec(r["closing_cash"]) < 0 for r in monthly):
        warnings.append(
            "部分主体的模拟资金头寸为负，表示融资缺口，不作为真实资产负债表现金余额。"
        )
    if entity == "all" and not consolidated:
        warnings.append(
            "当前仅为授权范围内主体汇总，交易对手不在范围内时不抵销内部销售。"
        )

    def metric(key, label, value, unit="元"):
        metrics[key] = {
            "label": label,
            "value": None if value is None else amount(value),
            "unit": unit,
        }

    if app_id in ("pharma-overview", "pharma-monthly"):
        metric(
            "revenue", "抵销后收入" if consolidated else "范围收入", external_revenue
        )
        metric("elimination", "内部收入抵销", eliminated)
        metric("gross_profit", "毛利", external_revenue - external_cost)
        metric(
            "operating_profit", "经营利润", external_revenue - external_cost - expense
        )
        metric(
            "gross_margin",
            "毛利率",
            ratio(external_revenue - external_cost, external_revenue),
            "%",
        )
        tables = [{"title": "主体经营（抵销前）", "rows": monthly}]
    elif app_id == "pharma-budget":
        # Budgets are unconsolidated: no undocumented elimination allocation.
        br = total(monthly, "budget_revenue")
        bc = total(monthly, "budget_cost")
        be = total(monthly, "budget_expense")
        bridge = [
            {"因素": "收入", "影响": amount(revenue - br)},
            {"因素": "成本", "影响": amount(bc - cost)},
            {"因素": "费用", "影响": amount(be - expense)},
        ]
        metric("budget_profit", "预算经营利润（抵销前）", br - bc - be)
        metric("actual_profit", "实际经营利润（抵销前）", revenue - cost - expense)
        metric(
            "profit_variance", "经营利润差异", revenue - cost - expense - (br - bc - be)
        )
        tables = [{"title": "差异桥 · approved-v1", "rows": bridge}]
        warnings.append("预算按主体加总口径比较，未实施集团预算抵销。")
    elif app_id == "pharma-product":
        groups = defaultdict(lambda: {"quantity": D(0), "revenue": D(0), "cost": D(0)})
        for r in rows["sales"]:
            if consolidated and int(r["internal"]):
                continue
            g = groups[(r["product_id"], r["channel"])]
            for k in g:
                g[k] += dec(r[k])
        tables = [
            {
                "title": "产品渠道盈利",
                "rows": [
                    dict(
                        product_id=k[0],
                        channel=k[1],
                        **{n: amount(v) for n, v in g.items()},
                        gross_profit=amount(g["revenue"] - g["cost"]),
                    )
                    for k, g in sorted(groups.items())
                ],
            }
        ]
        metric(
            "revenue",
            "外部销售收入" if consolidated else "销售收入",
            sum((g["revenue"] for g in groups.values()), D(0)),
        )
        # Symmetric price/volume decomposition, plus explicit new/discontinued products.
        year, month = map(int, period.split("-"))
        prev = (
            f"{year - 1 if month == 1 else year}-{12 if month == 1 else month - 1:02}"
        )
        previous = defaultdict(lambda: [D(0), D(0)])
        for r in data["sales"]:
            if (
                r["period"] == prev
                and (entity == "all" or r["entity_id"] == entity)
                and not (consolidated and int(r["internal"]))
            ):
                g = previous[(r["product_id"], r["channel"])]
                g[0] += dec(r["quantity"])
                g[1] += dec(r["revenue"])
        if not previous:
            warnings.append("缺少上期销售，无法进行量价归因。")
        else:
            bridge = []
            for key in sorted(set(groups) | set(previous)):
                q0, r0 = previous.get(key, [D(0), D(0)])
                g = groups.get(key, {"quantity": D(0), "revenue": D(0)})
                q1, r1 = g["quantity"], g["revenue"]
                if q0 <= 0 or q1 <= 0:
                    bridge.append(
                        dict(
                            product_id=key[0],
                            channel=key[1],
                            price_effect="0.00",
                            volume_effect="0.00",
                            scope_effect=amount(r1 - r0),
                        )
                    )
                else:
                    p0, p1 = r0 / q0, r1 / q1
                    pe = (p1 - p0) * (q0 + q1) / 2
                    bridge.append(
                        dict(
                            product_id=key[0],
                            channel=key[1],
                            price_effect=amount(pe),
                            volume_effect=amount(r1 - r0 - dec(amount(pe))),
                            scope_effect="0.00",
                        )
                    )
            tables.append(
                {"title": "环比量价桥（逐产品渠道，不混合规格）", "rows": bridge}
            )
    elif app_id == "pharma-tender":
        agreed = total(rows["tenders"], "agreed_quantity")
        delivered = total(rows["tenders"], "delivered_quantity")
        metric("fulfilment", "约定量完成率", ratio(delivered, agreed), "%")
        metric(
            "price_exceptions",
            "合同价格差异数",
            sum(
                dec(r["actual_price"]) != dec(r["contract_price"])
                for r in rows["tenders"]
            ),
            "项",
        )
        tables = [{"title": "集采合同履约", "rows": rows["tenders"]}]
        warnings.append("模拟月度约定量；不能替代真实采购周期及省级执行规则。")
    elif app_id == "pharma-receivables":
        buckets = {
            "未逾期": D(0),
            "1–30天": D(0),
            "31–60天": D(0),
            "61–90天": D(0),
            "90天以上": D(0),
        }
        for r in rows["receivables"]:
            days = (
                date.fromisoformat(str(r["as_of"]))
                - date.fromisoformat(str(r["due_date"]))
            ).days
            k = (
                "未逾期"
                if days <= 0
                else "1–30天"
                if days <= 30
                else "31–60天"
                if days <= 60
                else "61–90天"
                if days <= 90
                else "90天以上"
            )
            buckets[k] += dec(r["outstanding"])
        metric("outstanding", "含税应收余额", sum(buckets.values()))
        metric(
            "overdue", "逾期余额", sum(v for k, v in buckets.items() if k != "未逾期")
        )
        tables = [
            {
                "title": "月末账龄",
                "rows": [{"账龄": k, "余额": amount(v)} for k, v in buckets.items()],
            },
            {"title": "回款明细", "rows": rows["receivables"]},
        ]
    elif app_id == "pharma-cash":
        opening = total(monthly, "closing_cash")
        receipts = defaultdict(lambda: D(0))
        payments = defaultdict(lambda: D(0))
        for r in rows["cash_schedule"]:
            receipts[int(r["week"])] += dec(r["receipts"])
            payments[int(r["week"])] += dec(r["payments"])
        if set(receipts) != set(range(1, 14)):
            raise ValueError("资金预测需完整13周收付计划")
        baseline = delayed = opening
        schedule = []
        for w in range(1, 14):
            baseline += receipts[w] - payments[w]
            delayed += (
                D(0) if w <= 4 else receipts[w] + (receipts[w - 4] if w <= 8 else D(0))
            ) - payments[w]
            schedule.append(
                {"week": w, "baseline": amount(baseline), "delayed": amount(delayed)}
            )
        metric("opening", "预测期初现金", opening)
        metric("minimum", "延迟情景最低余额", min(dec(r["delayed"]) for r in schedule))
        tables = [{"title": "13周资金情景", "rows": schedule}]
        warnings.append(SEMANTICS["forecast"])
    elif app_id == "pharma-inventory":
        risks = []
        value = near = expired = D(0)
        for r in rows["inventory"]:
            v = dec(r["value"])
            value += v
            days = (
                date.fromisoformat(str(r["expires_on"]))
                - date.fromisoformat(str(r["as_of"]))
            ).days
            if days < 0:
                expired += v
            elif days <= 90:
                near += v
            idle = (
                date.fromisoformat(str(r["as_of"]))
                - date.fromisoformat(str(r["last_sale_on"]))
            ).days
            if days <= 90 or idle >= 90:
                risks.append({**r, "days_to_expiry": days, "days_idle": idle})
        metric("inventory", "库存账面价值", value)
        metric("near_expiry", "90天内临期金额", near)
        metric("expired", "已过期金额", expired)
        tables = [{"title": "批次风险（不等于减值）", "rows": risks}]
    elif app_id == "pharma-cost":
        variance = sum(
            (
                dec(r["quantity"])
                * (dec(r["actual_unit_cost"]) - dec(r["standard_unit_cost"]))
                for r in rows["costs"]
            ),
            D(0),
        )
        metric("cost_variance", "同实际数量单位成本差异", variance)
        tables = [{"title": "采购生产成本", "rows": rows["costs"]}]
        warnings.append(
            "当前仅比较相同实际数量的单位成本；没有标准投入数量，不能推断生产耗用效率。"
        )
    elif app_id == "pharma-rd":
        metric("spend", "研发投入", total(rows["rd"], "spend"))
        metric(
            "over_budget",
            "研发预算差异",
            total(rows["rd"], "spend") - total(rows["rd"], "budget"),
        )
        metric("capitalized", "已登记资本化金额", total(rows["rd"], "capitalized"))
        metric(
            "missing_evidence",
            "资本化证据未完整项目数",
            sum(not int(r["evidence_complete"]) for r in rows["rd"]),
            "项",
        )
        tables = [{"title": "研发项目复核", "rows": rows["rd"]}]
    elif app_id == "pharma-expense":
        expected = sum(
            (dec(r["rebate_base"]) * dec(r["rebate_rate"]) for r in rows["expenses"]),
            D(0),
        )
        metric("expense", "销售管理费用", total(rows["expenses"], "amount"))
        metric(
            "rebate_gap",
            "返利合同测算与计提差额",
            expected - total(rows["expenses"], "rebate_accrued"),
        )
        tables = [{"title": "费用及返利", "rows": rows["expenses"]}]
    elif app_id == "pharma-quality":
        gaps = []
        for r in monthly:
            sales = [s for s in rows["sales"] if s["entity_id"] == r["entity_id"]]
            cash = (
                dec(r["closing_cash"])
                - dec(r["opening_cash"])
                - dec(r["operating_cash"])
                - dec(r["investing_cash"])
                - dec(r["financing_cash"])
            )
            ar = [s for s in rows["receivables"] if s["entity_id"] == r["entity_id"]]
            gaps.append(
                {
                    "entity_id": r["entity_id"],
                    "revenue_gap": amount(dec(r["revenue"]) - total(sales, "revenue")),
                    "cash_gap": amount(cash),
                    "ar_gap": amount(
                        total(ar, "invoice_amount")
                        - total(ar, "received")
                        - total(ar, "outstanding")
                    ),
                }
            )
        metric(
            "exceptions",
            "勾稽异常数",
            sum(
                abs(dec(v)) > D(".01")
                for r in gaps
                for k, v in r.items()
                if k != "entity_id"
            ),
            "项",
        )
        tables = [{"title": "总账与业务勾稽", "rows": gaps}]
    if app_id == "pharma-monthly":
        for sub in (
            "pharma-receivables",
            "pharma-inventory",
            "pharma-rd",
            "pharma-quality",
        ):
            result = analyze(data, app_id=sub, period=period, entity=entity)
            metrics.update({sub + ":" + k: v for k, v in result["metrics"].items()})
    if not metrics and not any(t["rows"] for t in tables):
        warnings.append("该主体期间没有此专题明细，不能作经营结论。")
    return {
        "schema_version": "pharma-analysis/v1",
        "application_id": "pharma-finance",
        "app_id": app_id,
        "title": definition[2],
        "period": period,
        "entity": entity,
        "currency": "CNY",
        "simulated": True,
        "semantic_version": VERSION,
        "metrics": metrics,
        "tables": tables,
        "warnings": warnings,
        "data_fingerprint": digest(data),
        "semantic_contract": SEMANTICS,
    }


def render_report(result, evidence):
    esc = lambda x: escape(str(x))
    parts = [
        '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>'
        + esc(result["title"])
        + "</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;padding:20px;color:#18352f}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border:1px solid #cadbd5}h1,h2{color:#07685d}.notice{background:#fff4cc;padding:12px}</style><h1>"
        + esc(result["title"])
        + "</h1>",
        '<p class="notice">模拟数据 · 冻结分析草稿 · 待人工复核</p>',
        "<p>" + esc(result["period"]) + " / " + esc(result["entity"]) + " / CNY元</p>",
    ]
    for m in result["metrics"].values():
        parts.append(
            "<p><strong>"
            + esc(m["label"])
            + "</strong> "
            + esc(m["value"] if m["value"] is not None else "不适用")
            + " "
            + esc(m["unit"])
            + "</p>"
        )
    for table in result["tables"]:
        parts.append("<h2>" + esc(table["title"]) + "</h2>")
        if not table["rows"]:
            parts.append("<p>该范围无明细</p>")
            continue
        keys = list(table["rows"][0])
        parts.append(
            "<table><thead><tr>"
            + "".join("<th>" + esc(k) + "</th>" for k in keys)
            + "</tr></thead><tbody>"
        )
        for row in table["rows"]:
            parts.append(
                "<tr>"
                + "".join("<td>" + esc(row.get(k, "")) + "</td>" for k in keys)
                + "</tr>"
            )
        parts.append("</tbody></table>")
    parts.append(
        "<h2>口径及限制</h2>"
        + "".join("<p>" + esc(w) + "</p>" for w in result["warnings"])
    )
    parts.append(
        "<h2>知识依据</h2>"
        + "".join(
            "<p>"
            + esc(e["title"])
            + " · "
            + esc(e["version"])
            + " · "
            + esc(e.get("source_url") or "内部模拟方法文档")
            + "</p>"
            for e in evidence
        )
    )
    parts.append("<p>数据指纹：" + esc(result["data_fingerprint"]) + "</p></html>")
    return "".join(parts)
