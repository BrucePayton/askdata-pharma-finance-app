"""Local Docker demo provisioning wrapper. Secrets stay in a mode-0600 state file.
Uses the dedicated finance MySQL container's generated initialization credential.
No existing finance tables are altered. Run from the repository root.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
STATE = Path.home() / ".local/state/askdata-pharma"
STATE.mkdir(parents=True, exist_ok=True)
os.chmod(STATE, 0o700)
IMAGE = os.getenv("PHARMA_BACKEND_IMAGE", "askdata-pharma-backend:demo-v1")


def run(script, extra=""):
    args = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "askdata-finance-platform_finance-net",
        "--env-file",
        str(ROOT / "deployments/deployment_finance/.env"),
        "-e",
        "KEYCLOAK_SERVICE=http://keycloak:8080/auth",
        "-e",
        "PHARMA_STATE_FILE=/state/resources.json",
        "-v",
        str(STATE) + ":/state",
        IMAGE,
        "python",
        "-",
    ]
    result = subprocess.run(
        args, input=extra + "\n" + script, text=True, capture_output=True
    )
    if result.returncode:
        log = STATE / "provision-error.log"
        log.write_text(result.stdout + "\n" + result.stderr)
        os.chmod(log, 0o600)
        print("Provision failed; private diagnostic:", log)
        sys.exit(result.returncode)
    # Only script-owned status lines are emitted; dependency logs may carry details.
    for line in result.stdout.splitlines():
        if line.startswith(
            (
                "Verified demo",
                "Dedicated demo",
                "Demo identity",
                "submitted",
                "indexed",
                "ready",
            )
        ):
            print(line)


if __name__ == "__main__":
    stage = sys.argv[1]
    if stage == "database":
        logs = subprocess.run(
            ["docker", "logs", "askdata-finance-platform-finance-mysql-1"],
            capture_output=True,
            text=True,
            check=True,
        )
        matches = re.findall(
            r"GENERATED ROOT PASSWORD:\s*(\S+)", logs.stdout + logs.stderr
        )
        if not matches:
            raise SystemExit(
                "Initialization root credential is not available; supply admin credentials via seed_database.py"
            )
        secret = dict(
            PHARMA_MYSQL_ADMIN_HOST="finance-mysql",
            PHARMA_MYSQL_ADMIN_USER="root",
            PHARMA_MYSQL_ADMIN_PASSWORD=matches[-1],
        )
        run(
            "from scripts.pharma.seed_database import seed\nseed()",
            "import os\nos.environ.update(" + repr(secret) + ")",
        )
    elif stage == "identity":
        run(
            "import asyncio\nfrom scripts.pharma.create_demo_user import main\nasyncio.run(main())"
        )
    elif stage == "access":
        run((ROOT / "scripts/pharma/assign_demo_access.py").read_text())
    elif stage == "platform":
        run(
            "from scripts.pharma.bootstrap import bootstrap\nbootstrap()",
            'import os\nos.environ["PHARMA_PLATFORM_API"]="http://askdata_backend:5555"',
        )
    else:
        raise SystemExit("Expected database, identity or platform")
