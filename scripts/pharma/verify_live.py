"""Authenticated live acceptance. Uses private demo credentials, prints no secrets."""

import json
import os
from pathlib import Path
import time
import urllib.request
import urllib.error
import uuid

STATE = Path.home() / ".local/state/askdata-pharma"
BASE = os.getenv("PHARMA_BASE_URL", "http://127.0.0.1:18190")


def main():
    state = json.loads((STATE / "resources.json").read_text())
    token = ""

    def call(path, body=None):
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Content-Type": "application/json",
                **({"Authorization": token} if token else {}),
            },
        )
        with urllib.request.urlopen(req, timeout=90) as r:
            result = json.load(r)
        if result.get("code", 0) != 0:
            raise RuntimeError(result.get("message", "API failed"))
        return result.get("payload", result)

    cred = state["demo_user"]
    token = call(
        "/api/application-center/v1/user/login",
        dict(
            login_identifier=cred["username"],
            password=cred["password"],
            login_type="username",
        ),
    )["token"]
    spaces = call("/api/application-center/v1/apps/pharma/workspaces")["workspaces"]
    assert len(spaces) == 3
    result = {"spaces": [], "calculations": 0, "reports": [], "checks": []}
    for scope, resource in state["spaces"].items():
        base = f"/api/application-center/v1/workspaces/{resource['workspace_id']}/applications/pharma-finance"
        ctx = call(base + "/context")
        entities = {e["entity_id"] for e in ctx["entities"]}
        assert entities == (
            {"HQ", "MFG", "DIST", "RD"}
            if scope == "group"
            else {"MFG", "RD"}
            if scope == "manufacturing"
            else {"DIST"}
        )
        result["spaces"].append(
            {
                "scope": scope,
                "entities": sorted(entities),
                "workspace_id": resource["workspace_id"],
            }
        )
        for app in ctx["apps"]:
            body = {
                "period": "2026-09",
                "entity": "all",
                "context_revision": ctx["context_revision"],
            }
            calculated = call(base + f"/apps/{app['app_id']}/calculation", body)
            assert calculated["simulated"] and calculated["app_id"] == app["app_id"]
            result["calculations"] += 1
            if app["app_id"] == "pharma-quality":
                assert calculated["metrics"]["exceptions"]["value"] == "0.00"
        if scope == "distribution":
            try:
                call(
                    base + "/apps/pharma-overview/calculation",
                    {**body, "entity": "MFG"},
                )
            except urllib.error.HTTPError as e:
                assert e.code == 422
            else:
                raise AssertionError("Cross-entity access was admitted")
        if scope == "group":
            for app in ("pharma-overview", "pharma-monthly"):
                key = "live-" + uuid.uuid4().hex
                run = call(base + f"/apps/{app}/runs", {**body, "idempotency_key": key})
                same = call(
                    base + f"/apps/{app}/runs", {**body, "idempotency_key": key}
                )
                assert same["id"] == run["id"]
                deadline = time.monotonic() + 300
                while time.monotonic() < deadline:
                    current = call(base + "/runs/" + run["id"])
                    if current["status"] in ("completed", "failed"):
                        break
                    time.sleep(2)
                assert current["status"] == "completed", current.get(
                    "error", current["status"]
                )
                html = call(base + "/runs/" + run["id"] + "/document")["document_html"]
                assert "模拟数据" in html
                result["reports"].append(
                    {
                        "run_id": run["id"],
                        "artifact_id": current["result"]["artifact_id"],
                        "knowledge_retrieval": current["result"]["analysis"][
                            "knowledge_retrieval"
                        ]["status"],
                    }
                )
    for path in [
        "/api/config/llm/providers",
        "/api/application-center/v1/datasource/options",
        "/finance/",
    ]:
        try:
            call(path)
        except urllib.error.HTTPError as e:
            assert e.code == 404
        else:
            raise AssertionError("Share gateway exposed " + path)
    result["checks"] = [
        "database_scope",
        "36_calculations",
        "idempotency",
        "frozen_reports",
        "share_route_allowlist",
    ]
    (STATE / "acceptance.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
