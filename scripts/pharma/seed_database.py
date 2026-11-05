"""Create isolated demo schemas. Existing data is verified, never overwritten.
Use PHARMA_MYSQL_ADMIN_* only for this initialization; runtime users receive SELECT.
Writes generated reader credentials to PHARMA_STATE_FILE with mode 0600.
"""

import json
import os
from pathlib import Path
import secrets
import pymysql
from core.modules.pharma.demo import generate
from core.modules.pharma.catalog import TABLES, digest

SCOPES = {
    "group": ("pharma_finance_demo", None),
    "manufacturing": ("pharma_manufacturing_demo", ["MFG", "RD"]),
    "distribution": ("pharma_distribution_demo", ["DIST"]),
}


def seed():
    path = Path(os.environ.get("PHARMA_STATE_FILE", "/tmp/pharma-resources.json"))
    state = (
        json.loads(path.read_text())
        if path.exists()
        else {"schema_version": 1, "databases": {}}
    )
    data = generate()
    connection = pymysql.connect(
        host=os.environ["PHARMA_MYSQL_ADMIN_HOST"],
        port=int(os.getenv("PHARMA_MYSQL_ADMIN_PORT", "3306")),
        user=os.environ["PHARMA_MYSQL_ADMIN_USER"],
        password=os.environ["PHARMA_MYSQL_ADMIN_PASSWORD"],
        charset="utf8mb4",
        autocommit=False,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS pharma_finance_demo CHARACTER SET utf8mb4"
        )
        cursor.execute("USE pharma_finance_demo")
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS pharma_manifest (id INT PRIMARY KEY, fingerprint CHAR(64) NOT NULL)"
        )
        cursor.execute("SELECT fingerprint FROM pharma_manifest WHERE id=1")
        existing = cursor.fetchone()
        if existing and existing[0] != digest(data):
            raise RuntimeError(
                "Existing demo fingerprint differs; explicit new version required"
            )
        for table, cols in TABLES.items():
            keys = cols.split(",")
            rows = data[table]
            numeric = {k for k in keys if isinstance(rows[0][k], int)}
            money = {
                "revenue",
                "cost",
                "expense",
                "net_profit",
                "budget_revenue",
                "budget_cost",
                "budget_expense",
                "opening_cash",
                "operating_cash",
                "investing_cash",
                "financing_cash",
                "closing_cash",
                "internal_revenue",
                "internal_cost",
                "unit_price",
                "invoice_amount",
                "received",
                "outstanding",
                "unit_cost",
                "value",
                "contract_price",
                "actual_price",
                "actual_unit_cost",
                "standard_unit_cost",
                "spend",
                "budget",
                "capitalized",
                "amount",
                "rebate_base",
                "rebate_rate",
                "rebate_accrued",
                "receipts",
                "payments",
            }
            pk = (
                "period,entity_id"
                if table == "monthly"
                else "entity_id"
                if table == "entities"
                else "product_id"
                if table == "products"
                else "id"
            )
            definitions = ",".join(
                f"`{k}` "
                + (
                    "BIGINT"
                    if k in numeric
                    else "DECIMAL(20,4)"
                    if k == "rebate_rate"
                    else "DECIMAL(20,2)"
                    if k in money
                    else "VARCHAR(160)"
                )
                + " NOT NULL"
                for k in keys
            )
            cursor.execute(
                f"CREATE TABLE IF NOT EXISTS pharma_{table} ({definitions}, PRIMARY KEY ({pk}))"
            )
            cursor.execute(f"SELECT COUNT(*) FROM pharma_{table}")
            count = cursor.fetchone()[0]
            if count and count != len(rows):
                raise RuntimeError(f"Partial demo table {table}: refusing overwrite")
            if count == 0:
                cursor.executemany(
                    f"INSERT INTO pharma_{table} ({cols}) VALUES ({','.join(['%s'] * len(keys))})",
                    [tuple(r[k] for k in keys) for r in rows],
                )
        cursor.execute(
            "INSERT IGNORE INTO pharma_manifest VALUES (1,%s)", (digest(data),)
        )
        connection.commit()
        for scope, (database, entities) in SCOPES.items():
            credential = state["databases"].get(scope)
            if not credential:
                credential = dict(
                    database=database,
                    username="pharma_" + scope,
                    password=secrets.token_urlsafe(32),
                )
                state["databases"][scope] = credential
                # Save before issuing DDL; a retry must use the same credentials.
                path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(state, f)
                os.chmod(path, 0o600)
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS {database} CHARACTER SET utf8mb4"
            )
            if entities:
                for table in TABLES:
                    condition = (
                        ""
                        if table == "products"
                        else " WHERE entity_id IN ("
                        + ",".join("%s" for e in entities)
                        + ")"
                    )
                    cursor.execute(
                        f"CREATE OR REPLACE SQL SECURITY DEFINER VIEW {database}.pharma_{table} AS SELECT * FROM pharma_finance_demo.pharma_{table}"
                        + condition,
                        tuple(entities) if condition else (),
                    )
            cursor.execute(
                "CREATE USER IF NOT EXISTS %s@'%%' IDENTIFIED BY %s",
                (credential["username"], credential["password"]),
            )
            cursor.execute(
                f"GRANT SELECT ON {database}.* TO %s@'%%'", (credential["username"],)
            )
        connection.commit()
    connection.close()
    print(
        "Verified demo schemas:",
        ",".join(s[0] for s in SCOPES.values()),
        "rows:",
        sum(map(len, data.values())),
    )


if __name__ == "__main__":
    seed()
