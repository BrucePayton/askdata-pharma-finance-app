"""Create a non-admin, dedicated demo identity without revealing credentials."""

import asyncio
import json
import os
import secrets
from pathlib import Path
from utils.keycloak_utils import KeycloakUtils


async def main():
    path = Path(os.environ["PHARMA_STATE_FILE"])
    state = json.loads(path.read_text())
    if "demo_user" in state:
        print("Demo identity checkpoint exists")
        return
    token = await KeycloakUtils.get_system_access_token()
    username = "pharma-demo-" + secrets.token_hex(3)
    password = secrets.token_urlsafe(22) + "aA1!"
    result = await KeycloakUtils.add_user(
        token,
        username,
        "医药演示用户",
        password,
        username + "@example.invalid",
        "Pharmaceutical demo only",
        roles=[],
        group_infos=[],
    )
    state["demo_user"] = {"username": username, "password": password}
    with path.open("w") as f:
        json.dump(state, f, ensure_ascii=False)
    os.chmod(path, 0o600)
    print("Dedicated demo identity created")


if __name__ == "__main__":
    asyncio.run(main())
