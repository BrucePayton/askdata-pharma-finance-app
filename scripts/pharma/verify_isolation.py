"""Run inside backend network: real second-user and database-privilege checks."""

import asyncio
import json
import os
from pathlib import Path
import secrets
import requests
import pymysql
from utils.keycloak_utils import KeycloakUtils


async def main():
    path = Path(os.environ["PHARMA_STATE_FILE"])
    state = json.loads(path.read_text())
    token = await KeycloakUtils.get_system_access_token()
    if "negative_test_user" not in state:
        username = "pharma-negative-" + secrets.token_hex(3)
        password = secrets.token_urlsafe(22) + "aA1!"
        uid = await KeycloakUtils.add_user(
            token,
            username,
            "隔离测试用户",
            password,
            username + "@example.invalid",
            "Pharma isolation test",
            roles=[],
            group_infos=[],
        )
        state["negative_test_user"] = {
            "username": username,
            "password": password,
            "id": uid,
        }
        path.write_text(json.dumps(state))
        os.chmod(path, 0o600)
    c = state["negative_test_user"]
    session = requests.Session()
    session.trust_env = False
    base = "http://askdata_backend:5555"
    r = session.post(
        base + "/api/user/login",
        json={
            "login_identifier": c["username"],
            "password": c["password"],
            "login_type": "username",
        },
        timeout=30,
    )
    r.raise_for_status()
    session.headers["Authorization"] = r.json()["payload"]["token"]
    for item in state["spaces"].values():
        r = session.get(
            base
            + f"/api/application-center/v1/workspaces/{item['workspace_id']}/applications/pharma-finance/context",
            timeout=30,
        )
        assert r.status_code == 403, r.status_code
    for scope in ("manufacturing", "distribution"):
        c = state["databases"][scope]
        connection = pymysql.connect(
            host="finance-mysql",
            user=c["username"],
            password=c["password"],
            database=c["database"],
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM pharma_monthly")
            assert cursor.fetchone()[0] == (48 if scope == "manufacturing" else 24)
            for sql in [
                "SELECT * FROM pharma_finance_demo.pharma_monthly LIMIT 1",
                "UPDATE pharma_monthly SET revenue=0 WHERE 1=0",
            ]:
                try:
                    cursor.execute(sql)
                except pymysql.MySQLError as exc:
                    assert exc.args[0] in (1142, 1143, 1356), exc.args[0]
                else:
                    raise AssertionError("Readonly scope escaped")
        connection.close()
    print(
        "Dedicated demo isolation verified: second user denied 3 spaces; readers cannot cross database or write"
    )


if __name__ == "__main__":
    asyncio.run(main())
