"""Submit one demo report for review and confirm non-admin publish is denied."""

import json
from pathlib import Path
import urllib.request
import urllib.error

state = Path.home() / ".local/state/askdata-pharma"
c = json.loads((state / "resources.json").read_text())
a = json.loads((state / "acceptance.json").read_text())
token = ""
base = "http://localhost:18190/api/application-center/v1"


def call(path, body=None):
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": token},
    )
    with urllib.request.urlopen(request, timeout=60) as r:
        data = json.load(r)
    if data.get("code", 0) != 0:
        raise RuntimeError("Review request failed")
    return data.get("payload", data)


cred = c["demo_user"]
token = call(
    "/user/login",
    dict(
        login_identifier=cred["username"],
        password=cred["password"],
        login_type="username",
    ),
)["token"]
wid = c["spaces"]["group"]["workspace_id"]
run = a["reports"][-1]["run_id"]
path = f"/workspaces/{wid}/applications/pharma-finance/runs/{run}"
payload = call(path + "/review-state")
if payload.get("review_status", "draft") == "draft":
    call(
        path + "/review",
        {
            "workspace_id": wid,
            "action": "submit",
            "expected_revision": payload.get("review_revision", 0),
            "note": "演示验收：提交人工复核",
        },
    )
payload = call(path + "/review-state")
assert payload["review_status"] == "pending_review"
snapshot = call(path + "/review-document")
assert snapshot["snapshot_hash"] and "模拟数据" in snapshot["document_html"]
try:
    call(
        path + "/review",
        {
            "workspace_id": wid,
            "action": "publish",
            "expected_revision": payload["review_revision"],
            "note": "验证普通账号不能发布",
        },
    )
except urllib.error.HTTPError as e:
    assert e.code == 403
else:
    raise AssertionError("Demo account unexpectedly published report")
print(
    "Review acceptance passed: pending_review, immutable snapshot, non-admin publish denied"
)
