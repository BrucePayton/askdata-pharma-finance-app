"""Idempotent platform registration and real indexing; run in configured backend.
PHARMA_STATE_FILE is a private checkpoint including generated reader credentials.
No secret or login token is printed. Existing unrelated resources are never adopted.
"""

import json
import os
from pathlib import Path
import time
import requests
from core.modules.pharma.catalog import ROOT, VERSION, knowledge

NAMES = {
    "group": "医药集团财务分析空间",
    "manufacturing": "制药经营与研发分析空间",
    "distribution": "医药流通与回款分析空间",
}


def bootstrap():
    path = Path(os.environ["PHARMA_STATE_FILE"])
    state = json.loads(path.read_text())
    session = requests.Session()
    session.trust_env = False
    base = os.getenv("PHARMA_PLATFORM_API", "http://127.0.0.1:5555")

    def call(route, body=None):
        r = session.request(
            "GET" if body is None else "POST", base + route, json=body, timeout=180
        )
        r.raise_for_status()
        v = r.json()
        if v.get("code", 0) != 0:
            raise RuntimeError("Platform resource request failed: " + route)
        return v.get("payload", v)

    def checkpoint():
        with path.open("w") as f:
            json.dump(state, f, ensure_ascii=False)
        os.chmod(path, 0o600)

    token = call(
        "/api/user/login",
        dict(
            login_identifier=os.environ["KEYCLOAK_SYSTEM_USERNAME"],
            password=os.environ["KEYCLOAK_SYSTEM_PASSWORD"],
            login_type="username",
        ),
    )["token"]
    session.headers["Authorization"] = token
    marker = "pharma-finance/demo/v1"
    kb_bindings = {}
    for key, title, kinds in [
        ("pharma_policy", "医药政策与会计依据", {"public"}),
        ("pharma_methods", "医药指标与分析方法", {"method", "scenario"}),
        ("pharma_demo_policy", "模拟医药集团管理制度", {"demo_policy"}),
    ]:
        resources = state.setdefault("knowledge", {})
        if key not in resources:
            existing = call("/api/kb/knowledgebases?page=1&page_size=100")[
                "knowledgebases"
            ]
            found = [
                k for k in existing if k["name"] == title and k.get("desc") == marker
            ]
            if len(found) > 1:
                raise RuntimeError("Ambiguous existing knowledge resources")
            kb = (
                found[0]
                if found
                else call(
                    "/api/kb/knowledgebases",
                    dict(name=title, desc=marker, source="Manual"),
                )["knowledgebase"]
            )
            resources[key] = dict(id=kb["id"], dataset_id=kb["dataset_id"])
            checkpoint()
        kb = resources[key]
        kb_bindings[key] = kb["id"]
        dataset = kb["dataset_id"]
        docs = [d for d in knowledge() if d["kind"] in kinds]
        status_path = f"/api/kb/document/embedding/status?dataset_id={dataset}"
        existing = {d["name"]: d for d in call(status_path).get("data", [])}
        for doc in docs:
            name = doc["path"]
            if name in existing:
                if existing[name].get("indexing_status") == "error":
                    raise RuntimeError(f"Index failed: {name}")
                continue
            r = session.post(
                base + "/api/kb/document/upload",
                data={"dataset_id": dataset, "process_format": "md"},
                files={
                    "files": (
                        name,
                        (ROOT / "knowledge" / name).read_bytes(),
                        "text/markdown",
                    )
                },
                timeout=180,
            )
            r.raise_for_status()
            result = r.json()
            if result.get("code", 0) != 0:
                raise RuntimeError("Document upload failed")
            names = [f["file_name"] for f in result["payload"]["processed_files_list"]]
            call(
                "/api/kb/document/vectoring",
                dict(
                    dataset_id=dataset,
                    file_name_list=names,
                    max_tokens=300,
                    chunk_overlap=30,
                    search_method="semantic_search",
                    reranking_enable=False,
                ),
            )
            print("submitted", name, flush=True)
        deadline = time.monotonic() + 300
        while True:
            existing = {d["name"]: d for d in call(status_path).get("data", [])}
            if all(
                existing.get(d["path"], {}).get("indexing_status") == "completed"
                for d in docs
            ):
                break
            if any(
                existing.get(d["path"], {}).get("indexing_status") == "error"
                for d in docs
            ):
                raise RuntimeError("Knowledge indexing failed")
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Knowledge indexing timeout; rerun resumes verification"
                )
            time.sleep(2)
        print("indexed", key, len(docs), flush=True)
    for scope, name in NAMES.items():
        credential = state["databases"][scope]
        resource = state.setdefault("spaces", {}).setdefault(scope, {})
        if "workspace_id" not in resource:
            spaces = call("/api/wp/workspaces?page=1&page_size=100")["workspaces"]
            matches = [
                w for w in spaces if w["name"] == name and w.get("desc") == marker
            ]
            if len(matches) > 1:
                raise RuntimeError("Ambiguous workspace")
            ws = (
                matches[0]
                if matches
                else call(
                    "/api/wp/workspaces",
                    dict(
                        name=name,
                        desc=marker,
                        is_active=True,
                        visibility="team",
                        linked_team_uuids=[],
                        owner=state["demo_user"]["username"],
                    ),
                )["workspace"]
            )
            resource["workspace_id"] = ws["id"]
            checkpoint()
        if "datasource_id" not in resource:
            body = dict(
                name=f"医药模拟数据-{scope}",
                desc=marker,
                db_type="mysql",
                host=os.getenv("PHARMA_MYSQL_HOST", "finance-mysql"),
                port=3306,
                **credential,
                config={
                    "pharma_semantic_profile": {
                        "version": VERSION,
                        "simulated": True,
                        "scope": scope,
                    }
                },
            )
            tested = call("/api/datasource/datasources/test-connection", body)
            if tested.get("success") is False or tested.get("connected") is False:
                raise RuntimeError("Datasource connection failed")
            datasource = call("/api/datasource/datasources/add", body)["datasource"]
            resource["datasource_id"] = datasource["id"]
            checkpoint()
        body = dict(
            workspace_id=resource["workspace_id"],
            bindings={"pharma_database": resource["datasource_id"], **kb_bindings},
            dry_run=False,
        )
        installed = call(
            "/api/wp/application-center/packages/pharma-finance/install", body
        )
        resource["installation_id"] = installed["installation_id"]
        checkpoint()
        context = call(
            f"/api/wp/application-center/workspaces/{resource['workspace_id']}/applications/pharma-finance/context"
        )
        if len(context["apps"]) != 12:
            raise RuntimeError("Application catalogue mismatch")
        print("ready", scope, "workspace", resource["workspace_id"], flush=True)
    state["status"] = "ready"
    checkpoint()


if __name__ == "__main__":
    bootstrap()
