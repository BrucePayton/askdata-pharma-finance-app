"""Exercise journal-backed non-SSE analysis through the demo gateway."""

import json
import os
from pathlib import Path
import time
import urllib.request
import uuid

state = Path.home() / ".local/state/askdata-pharma"
config = json.loads((state / "resources.json").read_text())
cred = config["demo_user"]
base = os.getenv("PHARMA_BASE_URL", "http://localhost:18190")
token = ""


def call(path, body=None):
    r = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": token},
    )
    with urllib.request.urlopen(r, timeout=120) as result:
        data = json.load(result)
    if data.get("code", 0) != 0:
        raise RuntimeError(data.get("message", "API failure"))
    return data.get("payload", data)


token = call(
    "/api/application-center/v1/user/login",
    dict(
        login_identifier=cred["username"],
        password=cred["password"],
        login_type="username",
    ),
)["token"]
wid = config["spaces"]["group"]["workspace_id"]
path = f"/api/application-center/v1/workspaces/{wid}/applications/pharma-finance"
body = {
    "thread_id": str(uuid.uuid4()),
    "workspace_id": wid,
    "application_context": {"application_id": "pharma-finance"},
    "messages": [
        {
            "role": "user",
            "content": "在医药财务知识库中，临期库存风险金额能否直接作为存货减值金额？请引用资料并说明限制，不查询数据库。",
        }
    ],
    "locale": "zh-CN",
    "enable_web_search": False,
    "auto_accepted_plan": False,
    "session_outcome_goals": ["knowledge_qa"],
}
start = call(path + "/analysis", body)
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    status = call(path + "/analysis/" + start["run_id"])
    if status["status"] != "running":
        break
    time.sleep(2)
else:
    call(path + "/analysis/" + start["run_id"] + "/cancel", {})
    raise RuntimeError("Live question timed out and was cancelled")
result = {
    "run_id": start["run_id"],
    "status": status["status"],
    "message_count": len((status.get("snapshot") or {}).get("messages", {})),
    "has_interrupt": bool(
        (status.get("snapshot") or {}).get("latest", {}).get("interrupt")
    ),
}
(state / "analysis-acceptance.json").write_text(json.dumps(result, indent=2))
print(json.dumps(result))
assert result["status"] not in ("failed", "abandoned"), result
assert result["message_count"] or result["has_interrupt"], result
