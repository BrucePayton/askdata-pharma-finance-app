"""Independent SQL oracle for frozen deterministic demo cases; never calls engine."""

import json
import sqlite3
from decimal import Decimal
from core.modules.pharma.catalog import APPS, ROOT
from core.modules.pharma.demo import generate

queries = {
    "pharma-overview": (
        "revenue",
        "SELECT SUM(CAST(revenue AS REAL)-CASE WHEN :entity='all' THEN CAST(internal_revenue AS REAL) ELSE 0 END) FROM monthly WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-budget": (
        "profit_variance",
        "SELECT SUM(revenue-cost-expense-budget_revenue+budget_cost+budget_expense) FROM monthly WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-product": (
        "revenue",
        "SELECT SUM(CAST(revenue AS REAL)) FROM sales WHERE period=:period AND (:entity='all' OR entity_id=:entity) AND (:entity!='all' OR internal='0')",
    ),
    "pharma-tender": (
        "fulfilment",
        "SELECT 100.0*SUM(delivered_quantity)/NULLIF(SUM(agreed_quantity),0) FROM tenders WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-receivables": (
        "outstanding",
        "SELECT SUM(CAST(outstanding AS REAL)) FROM receivables WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-cash": (
        "opening",
        "SELECT SUM(CAST(closing_cash AS REAL)) FROM monthly WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-inventory": (
        "inventory",
        "SELECT SUM(CAST(value AS REAL)) FROM inventory WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-cost": (
        "cost_variance",
        "SELECT SUM(quantity*(actual_unit_cost-standard_unit_cost)) FROM costs WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-rd": (
        "spend",
        "SELECT SUM(CAST(spend AS REAL)) FROM rd WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-expense": (
        "expense",
        "SELECT SUM(CAST(amount AS REAL)) FROM expenses WHERE period=:period AND (:entity='all' OR entity_id=:entity)",
    ),
    "pharma-quality": (
        "exceptions",
        "SELECT COUNT(*) FROM monthly WHERE period=:period AND (:entity='all' OR entity_id=:entity) AND ABS(closing_cash-opening_cash-operating_cash-investing_cash-financing_cash)>0.01",
    ),
}
queries["pharma-monthly"] = queries["pharma-overview"]


def build():
    db = sqlite3.connect(":memory:")
    for table, rows in generate().items():
        cols = list(rows[0])
        db.execute(f"CREATE TABLE {table} ({','.join(k + ' TEXT' for k in cols)})")
        db.executemany(
            f"INSERT INTO {table} VALUES ({','.join('?' for k in cols)})",
            [tuple(r[k] for k in cols) for r in rows],
        )
    cases = []
    for app, _, name, question in APPS:
        key, sql = queries[app]
        for period, entity in [
            ("2024-10", "all"),
            ("2025-09", "MFG"),
            ("2025-10", "DIST"),
            ("2026-09", "RD"),
            ("2026-09", "all"),
        ]:
            value = db.execute(sql, {"period": period, "entity": entity}).fetchone()[0]
            expected = (
                None
                if value is None and key == "fulfilment"
                else str(Decimal(str(value or 0)).quantize(Decimal(".01")))
            )
            cases.append(
                dict(
                    id=f"{app}:{period}:{entity}",
                    question=f"{period}，主体{entity}：{question}",
                    app_id=app,
                    period=period,
                    entity=entity,
                    metric=key,
                    expected=expected,
                    oracle_sql=sql,
                )
            )
    (ROOT / "golden-cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n"
    )


if __name__ == "__main__":
    build()
