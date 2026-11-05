"""Deterministic, entirely fictional group dataset. No network or credentials."""

import calendar
from datetime import date, timedelta
from decimal import Decimal as D
from .catalog import TABLES


def money(value):
    return str(D(value).quantize(D("0.01")))


def generate():
    data = {key: [] for key in TABLES}
    data["entities"] = [
        dict(entity_id=e, name=n, segment=s)
        for e, n, s in [
            ("HQ", "华澄医药集团（模拟）", "总部"),
            ("MFG", "华澄制药（模拟）", "制药"),
            ("DIST", "华澄配送（模拟）", "流通"),
            ("RD", "华澄研发（模拟）", "研发"),
        ]
    ]
    data["products"] = [
        dict(
            product_id=f"P{i:02}",
            name=f"模拟药品{i:02}",
            specification="10mg×20片",
            therapy="模拟治疗领域",
        )
        for i in range(1, 13)
    ]
    balances = {e["entity_id"]: D(1500000) for e in data["entities"]}
    for month in range(24):
        year, m = 2024 + (9 + month) // 12, (9 + month) % 12 + 1
        period = f"{year}-{m:02}"
        as_of = date(year, m, calendar.monthrange(year, m)[1])
        for ei, entity in enumerate(data["entities"]):
            e = entity["entity_id"]
            revenue = D(0)
            cost = D(0)
            internal_revenue = D(0)
            internal_cost = D(0)
            if e in ("MFG", "DIST"):
                for i, product in enumerate(data["products"], 1):
                    qty = (1000 + month * 35 + i * 25) * (2 if e == "DIST" else 1)
                    price = D(20 + i * 2) * (
                        D(".78") if month >= 12 and i <= 4 else D(1)
                    )
                    if month >= 12 and i <= 4:
                        qty = qty * 14 // 10
                    unit_cost = D(12 + i) * (D("1.12") if month >= 18 else D(1))
                    internal = int(e == "MFG" and i <= 3)
                    r = D(qty) * price
                    c = D(qty) * unit_cost
                    if e == "DIST" and i <= 3:
                        c = D(qty // 2) * price + D(qty - qty // 2) * unit_cost
                    revenue += r
                    cost += c
                    if internal:
                        internal_revenue += r
                        internal_cost += r
                    sid = f"{period}-{e}-{i}"
                    data["sales"].append(
                        dict(
                            id=sid,
                            period=period,
                            entity_id=e,
                            product_id=product["product_id"],
                            customer="集团配送公司" if internal else f"模拟医院{i:02}",
                            channel="内部" if internal else "医院",
                            region="模拟华东区",
                            quantity=qty,
                            unit_price=money(price),
                            revenue=money(r),
                            cost=money(c),
                            internal=internal,
                            tender_id=f"T-{sid}" if i <= 4 else "",
                        )
                    )
                    data["inventory"].append(
                        dict(
                            id=sid,
                            period=period,
                            entity_id=e,
                            product_id=product["product_id"],
                            batch=f"B{month:02}{i:02}",
                            quantity=qty // 2,
                            unit_cost=money(unit_cost),
                            value=money(D(qty // 2) * unit_cost),
                            expires_on=str(
                                as_of + timedelta(days=(30 if i <= 2 else 365))
                            ),
                            last_sale_on=str(
                                as_of - timedelta(days=120 if i == 2 else 10)
                            ),
                            as_of=str(as_of),
                        )
                    )
                    data["costs"].append(
                        dict(
                            id=sid,
                            period=period,
                            entity_id=e,
                            product_id=product["product_id"],
                            kind="生产" if e == "MFG" else "采购",
                            quantity=qty,
                            actual_unit_cost=money(unit_cost),
                            standard_unit_cost=money(D(12 + i)),
                        )
                    )
                    if i <= 4:
                        data["tenders"].append(
                            dict(
                                id=f"T-{sid}",
                                period=period,
                                entity_id=e,
                                product_id=product["product_id"],
                                region="模拟华东区",
                                agreed_quantity=qty + 100,
                                delivered_quantity=qty,
                                contract_price=money(price),
                                actual_price=money(price),
                            )
                        )
                    if not internal:
                        gross = (r * D("1.13")).quantize(D(".01"))
                        received = (gross * D(".6")).quantize(D(".01"))
                        data["receivables"].append(
                            dict(
                                id=sid,
                                period=period,
                                entity_id=e,
                                customer=f"模拟医院{i:02}",
                                invoice_amount=money(gross),
                                received=money(received),
                                outstanding=money(gross - received),
                                due_date=str(as_of - timedelta(days=i * 12 - 40)),
                                as_of=str(as_of),
                                settlement="普通账期" if i % 2 else "模拟直接结算",
                            )
                        )
            expense = (revenue * D(".08") + D(20000)).quantize(D(".01"))
            if e == "RD":
                expense = sum(
                    (D(10000 + i * 2000 + month * 100) for i in range(1, 6)), D(0)
                )
            operating = ((revenue - cost - expense) * D(".8")).quantize(D(".01"))
            opening = balances[e]
            investing = D(-30000)
            financing = D(10000)
            balances[e] = opening + operating + investing + financing
            data["monthly"].append(
                dict(
                    period=period,
                    entity_id=e,
                    revenue=money(revenue),
                    cost=money(cost),
                    expense=money(expense),
                    net_profit=money((revenue - cost - expense) * D(".75")),
                    budget_revenue=money(revenue * D("1.05")),
                    budget_cost=money(cost * D(".98")),
                    budget_expense=money(expense * D(".95")),
                    opening_cash=money(opening),
                    operating_cash=money(operating),
                    investing_cash=money(investing),
                    financing_cash=money(financing),
                    closing_cash=money(opening + operating + investing + financing),
                    internal_revenue=money(internal_revenue),
                    internal_cost=money(internal_cost),
                    budget_version="approved-v1",
                )
            )
            data["expenses"].append(
                dict(
                    id=f"{period}-{e}",
                    period=period,
                    entity_id=e,
                    category="销售及管理费用",
                    amount=money(expense),
                    rebate_base=money(revenue),
                    rebate_rate="0.02",
                    rebate_accrued=money(revenue * D(".018")),
                )
            )
            for week in range(1, 14):
                data["cash_schedule"].append(
                    dict(
                        id=f"{period}-{e}-{week}",
                        period=period,
                        entity_id=e,
                        week=week,
                        receipts=money(revenue / D(13)),
                        payments=money((cost + expense) / D(13)),
                    )
                )
            if e == "RD":
                for i in range(1, 6):
                    spend = D(10000 + i * 2000 + month * 100)
                    data["rd"].append(
                        dict(
                            id=f"{period}-{i}",
                            period=period,
                            entity_id=e,
                            project=f"模拟管线{i}",
                            stage="研究" if i <= 3 else "开发",
                            spend=money(spend),
                            budget="18000.00",
                            capitalized="0.00",
                            evidence_complete=0,
                        )
                    )
    return data
