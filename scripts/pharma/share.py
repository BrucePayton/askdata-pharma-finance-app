"""Start/stop a temporary Cloudflare Tunnel for the restricted demo gateway."""

import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

state = Path.home() / ".local/state/askdata-pharma"
state.mkdir(parents=True, exist_ok=True)
record = state / "tunnel.json"
if len(sys.argv) > 1 and sys.argv[1] == "stop":
    if record.exists():
        old = json.loads(record.read_text())
        command = subprocess.run(
            ["ps", "-p", str(old["pid"]), "-o", "command="],
            capture_output=True,
            text=True,
        ).stdout
        if "cloudflared" in command and "18190" in command:
            os.kill(old["pid"], signal.SIGTERM)
        record.unlink()
    print("Demo tunnel stopped")
    raise SystemExit(0)
if record.exists():
    old = json.loads(record.read_text())
    command = subprocess.run(
        ["ps", "-p", str(old["pid"]), "-o", "command="], capture_output=True, text=True
    ).stdout
    if "cloudflared" in command and "18190" in command:
        print(old["url"])
        raise SystemExit(0)
with urllib.request.urlopen(
    "http://127.0.0.1:18190/pharma-finance/", timeout=5
) as response:
    if response.status != 200:
        raise SystemExit("Local demo is not ready")
binary = shutil.which("cloudflared")
if not binary:
    raise SystemExit("Install cloudflared first")
log = state / "tunnel.log"
fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as out:
    process = subprocess.Popen(
        [
            binary,
            "tunnel",
            "--no-autoupdate",
            "--protocol",
            "http2",
            "--url",
            "http://127.0.0.1:18190",
        ],
        stdout=out,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
for attempt in range(60):
    if process.poll() is not None:
        raise SystemExit("Tunnel exited; inspect private tunnel.log")
    match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", log.read_text())
    if match:
        value = {
            "pid": process.pid,
            "url": match.group(0),
            "local": "http://127.0.0.1:18190",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        record.write_text(json.dumps(value, indent=2))
        os.chmod(record, 0o600)
        print(value["url"])
        break
    time.sleep(1)
else:
    process.terminate()
    raise SystemExit("Tunnel allocation timed out; inspect private tunnel.log")
