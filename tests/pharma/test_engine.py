import copy
from decimal import Decimal as D
import pytest
from core.modules.pharma.demo import generate
from core.modules.pharma.engine import analyze, render_report
from core.modules.pharma.catalog import APPS, knowledge, ROOT


@pytest.fixture(scope="module")
def data():
    return generate()


@pytest.mark.parametrize("app", [a[0] for a in APPS])
@pytest.mark.parametrize(
    "period,entity",
    [
        ("2024-10", "all"),
        ("2025-09", "MFG"),
        ("2025-10", "DIST"),
        ("2026-09", "RD"),
        ("2026-09", "all"),
    ],
)
def test_sixty_scenarios(data, app, period, entity):
    result = analyze(data, app_id=app, period=period, entity=entity)
    assert result["simulated"] is True
    assert result["period"] == period and result["entity"] == entity
    assert result["warnings"] and result["data_fingerprint"]
    assert "模拟数据" in render_report(result, [])


def test_budget_independent_expected(data):
    r = analyze(data, app_id="pharma-budget", period="2026-09", entity="RD")
    assert D(r["metrics"]["actual_profit"]["value"]) == -91500
    assert D(r["metrics"]["budget_profit"]["value"]) == -86925
    assert D(r["metrics"]["profit_variance"]["value"]) == -4575
    assert sum(D(x["影响"]) for x in r["tables"][0]["rows"]) == -4575


def test_zero_denominator(data):
    r = analyze(data, app_id="pharma-overview", period="2026-09", entity="RD")
    assert r["metrics"]["gross_margin"]["value"] is None


def test_cash_and_revenue_reconcile(data):
    for period in ["2024-10", "2025-10", "2026-09"]:
        r = analyze(data, app_id="pharma-quality", period=period)
        assert D(r["metrics"]["exceptions"]["value"]) == 0


def test_detect_cancelling_errors(data):
    d = copy.deepcopy(data)
    for row in d["monthly"]:
        if row["period"] == "2026-09" and row["entity_id"] in ("HQ", "RD"):
            row["closing_cash"] = str(
                D(row["closing_cash"]) + (10 if row["entity_id"] == "HQ" else -10)
            )
    assert (
        D(
            analyze(d, app_id="pharma-quality", period="2026-09")["metrics"][
                "exceptions"
            ]["value"]
        )
        == 2
    )


def test_due_today_and_partial_payment(data):
    d = copy.deepcopy(data)
    d["receivables"] = [
        dict(
            period="2026-09",
            entity_id="DIST",
            as_of="2026-09-30",
            due_date="2026-09-30",
            invoice_amount="113",
            received="13",
            outstanding="100",
        )
    ]
    r = analyze(d, app_id="pharma-receivables", period="2026-09", entity="DIST")
    assert r["metrics"]["overdue"]["value"] == "0.00"
    assert r["metrics"]["outstanding"]["value"] == "100.00"


def test_period_entity_and_version_rejection(data):
    for kwargs in [dict(period="2027-01"), dict(period="2026-09", entity="UNKNOWN")]:
        with pytest.raises(ValueError):
            analyze(data, app_id="pharma-overview", **kwargs)
    d = copy.deepcopy(data)
    d["monthly"][0]["budget_version"] = "unapproved"
    with pytest.raises(ValueError):
        analyze(d, app_id="pharma-budget", period="2024-10")


def test_forecast_delayed_balance_catches_up(data):
    r = analyze(data, app_id="pharma-cash", period="2026-09")
    assert len(r["tables"][0]["rows"]) == 13
    assert (
        r["tables"][0]["rows"][-1]["baseline"] == r["tables"][0]["rows"][-1]["delayed"]
    )


def test_price_volume_bridge_reconciles(data):
    r = analyze(data, app_id="pharma-product", period="2025-10", entity="DIST")
    bridge = sum(
        D(x["price_effect"]) + D(x["volume_effect"]) + D(x["scope_effect"])
        for x in r["tables"][1]["rows"]
    )
    revenue = lambda p: sum(
        D(s["revenue"])
        for s in data["sales"]
        if s["period"] == p and s["entity_id"] == "DIST"
    )
    assert bridge == revenue("2025-10") - revenue("2025-09")


def test_documents_and_package():
    import hashlib

    docs = knowledge()
    assert len(docs) == 30
    for item in docs:
        assert (
            hashlib.sha256((ROOT / "knowledge" / item["path"]).read_bytes()).hexdigest()
            == item["sha256"]
        )
    package = json.loads(
        (ROOT.parent / "domain-applications" / "pharma-finance" / "manifest.json").read_text()
    )
    assert package["schema_version"] == "domain_application/v1"
    assert package["platform_contract"] == "v1"
    assert len(package["scenarios"]) == 12 and len(package["bindings"]) == 4


import json


@pytest.mark.parametrize(
    "case", json.loads((ROOT / "golden-cases.json").read_text()), ids=lambda c: c["id"]
)
def test_frozen_independent_sql_goldens(data, case):
    result = analyze(
        data, app_id=case["app_id"], period=case["period"], entity=case["entity"]
    )
    actual = result["metrics"][case["metric"]]["value"]
    if case["expected"] is None:
        assert actual is None
    else:
        assert abs(D(actual) - D(case["expected"])) <= D(".01")


def test_restricted_subgroup_never_eliminates_sales_to_outside_scope(data):
    restricted = {
        table: [
            r for r in rows if "entity_id" not in r or r["entity_id"] in ("MFG", "RD")
        ]
        for table, rows in data.items()
    }
    r = analyze(restricted, app_id="pharma-overview", period="2026-09")
    assert r["metrics"]["elimination"]["value"] == "0.00"
    assert r["metrics"]["revenue"]["value"] == "803484.00"
    p = analyze(restricted, app_id="pharma-product", period="2026-09")
    assert p["metrics"]["revenue"]["value"] == "803484.00"
