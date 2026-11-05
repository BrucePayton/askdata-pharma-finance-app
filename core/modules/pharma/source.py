"""Read only the database bound to an authorized pharmaceutical installation."""

from types import SimpleNamespace
from fastapi import HTTPException
from .catalog import APPLICATION_ID, TABLES, SEMANTICS, definitions, digest, knowledge


async def load(db, *, workspace_id, user):
    from core.modules.application_center.runtime_context import (
        resolve_application_runtime_context,
    )
    from core.modules.datasource.helper import DataSourceHelper
    from core.modules.datasource.views import _build_connection_config_from_datasource
    from core.modules.datasource.dsc_gateway import get_dsc_datasource_gateway

    runtime = await resolve_application_runtime_context(
        db,
        workspace_id=workspace_id,
        user=user,
        requested=SimpleNamespace(
            application_id=APPLICATION_ID, installation_id=None, package_version=None
        ),
    )
    bindings = [
        r
        for r in runtime["resources"]
        if r["key"] == "pharma_database" and r["kind"] == "database"
    ]
    if len(bindings) != 1:
        raise HTTPException(409, "医药数据库绑定不唯一")
    datasource = await DataSourceHelper.get_datasource_by_id(db, int(bindings[0]["id"]))
    if (
        datasource is None
        or datasource.gmt_deleted is not None
        or not datasource.is_active
    ):
        raise HTTPException(409, "医药数据库不可用")
    profile = (datasource.config or {}).get("pharma_semantic_profile")
    if (
        not isinstance(profile, dict)
        or profile.get("version") != SEMANTICS["version"]
        or profile.get("simulated") is not True
    ):
        raise HTTPException(409, "医药模拟数据口径未配置或版本不一致")
    config = _build_connection_config_from_datasource(datasource)
    gateway = get_dsc_datasource_gateway()
    data = {}
    try:
        import json

        # Two bounded gateway calls instead of 22 per page. This respects the
        # platform's per-user SQL rate budget without bypassing its limiter.
        if config.db_type != "mysql":
            raise ValueError("Demo package requires MySQL")
        selections = []
        for name, columns in TABLES.items():
            pairs = ",".join(
                "'" + key + "',`" + key + "`" for key in columns.split(",")
            )
            selections.append(
                f"SELECT '{name}' AS table_name, JSON_OBJECT({pairs}) AS row_data FROM pharma_{name}"
            )
        query = " UNION ALL ".join(selections) + " LIMIT 10001"
        payload = (
            await gateway.execute_sql(config, query, user_id=str(user["user_id"]))
        )["data"]
        rows = payload.get("data")
        if not isinstance(rows, list) or len(rows) > 10000 or payload.get("truncated"):
            raise ValueError("Incomplete data")
        data = {name: [] for name in TABLES}
        for row in rows:
            item = row["row_data"]
            data[row["table_name"]].append(
                json.loads(item, parse_float=str) if isinstance(item, str) else item
            )
        counts = " UNION ALL ".join(
            f"SELECT '{name}' AS table_name, COUNT(*) AS n FROM pharma_{name}"
            for name in TABLES
        )
        expected = (
            await gateway.execute_sql(config, counts, user_id=str(user["user_id"]))
        )["data"]["data"]
        if len(expected) != len(TABLES):
            raise ValueError("Incomplete counts")
        for row in expected:
            if len(data[row["table_name"]]) != int(row["n"]):
                raise ValueError("Incomplete data")
        for rows in data.values():
            rows.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
    except Exception as exc:
        raise HTTPException(
            503, "医药数据读取失败或被截断，请检查已绑定数据源"
        ) from exc
    revision = digest(
        {
            "resources": runtime["resource_snapshot_digest"],
            "profile": profile,
            "semantics": SEMANTICS,
        }
    )
    return dict(
        data=data, runtime=runtime, revision=revision, datasource_id=bindings[0]["id"]
    )


def context(source):
    data = source["data"]
    return dict(
        application_id=APPLICATION_ID,
        workspace_id=source["runtime"]["workspace_id"],
        context_revision=source["revision"],
        apps=definitions(),
        entities=data["entities"],
        periods=sorted({r["period"] for r in data["monthly"]}),
        knowledge=knowledge(),
        semantics=SEMANTICS,
        simulated=True,
        resources=source["runtime"]["resources"],
        limitations=["模拟数据；跨表有界读取不是数据库事务快照，数据需保持冻结。"],
    )
