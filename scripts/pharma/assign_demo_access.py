"""Deployment-only ACL assignment for exact checkpoint-owned demo installations.
The legacy workspace API always assigns the caller as owner. This narrowly scoped
initializer sets the dedicated demo owner; it cannot edit unrelated workspaces.
"""

import asyncio
import json
import os
from pathlib import Path
from sqlalchemy import select
from storage.pgsql_storage import Database
from core.models.db.db_initial_models import WorkSpace, DomainApplicationInstallation


async def main():
    state = json.loads(Path(os.environ["PHARMA_STATE_FILE"]).read_text())
    owner = state["demo_user"]["username"]
    if not owner.startswith("pharma-demo-"):
        raise RuntimeError("Not a dedicated demo identity")
    async with Database.SessionLocal() as db:
        for item in state["spaces"].values():
            ws = await db.get(WorkSpace, item["workspace_id"], with_for_update=True)
            installation = await db.get(
                DomainApplicationInstallation, item["installation_id"]
            )
            if (
                not ws
                or ws.desc != "pharma-finance/demo/v1"
                or not installation
                or installation.application_id != "pharma-finance"
                or installation.workspace_id != ws.id
            ):
                raise RuntimeError("Refusing unrelated resource ACL modification")
            if ws.owner not in (owner, os.environ["KEYCLOAK_SYSTEM_USERNAME"]):
                raise RuntimeError("Workspace owner diverged; refusing overwrite")
            ws.owner = owner
            ws.visibility = "team"
            ws.linked_team_uuids = []
        await db.commit()
    print("Dedicated demo workspace ownership assigned")


if __name__ == "__main__":
    asyncio.run(main())
