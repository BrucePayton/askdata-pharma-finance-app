"""Durable pharma workflows using the shared queue and report governance."""

import uuid
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text, or_, cast, String
from core.modules.application_center.run_models import ApplicationRun, now
from core.modules.application_center.finance_runs import current_principal
from core.modules.application_center.service import authorize_workspace
from .catalog import APPLICATION_ID, VERSION, APPS, digest, knowledge
from .source import load
from .engine import analyze, render_report

WORKFLOW_VERSION = "pharma-finance/v1"


class CalculationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    entity: str = Field(default="all", max_length=40)
    context_revision: str = Field(pattern=r"^[a-f0-9]{64}$")


class RunInput(CalculationInput):
    idempotency_key: str = Field(min_length=1, max_length=100)


def calculate(source, app_id, body):
    if body.context_revision != source["revision"]:
        raise HTTPException(409, "资源或指标口径已改变，请刷新空间")
    try:
        result = analyze(
            source["data"], app_id=app_id, period=body.period, entity=body.entity
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result["source_binding"] = {
        "workspace_id": source["runtime"]["workspace_id"],
        "datasource_id": source["datasource_id"],
        "context_revision": source["revision"],
    }
    result["evidence"] = [k for k in knowledge() if app_id in k["app_ids"]]
    result["warnings"].append("跨表读取不是事务快照；仅支持冻结的演示数据版本。")
    return result


async def submit(db, *, workspace_id, app_id, user, body):
    if app_id not in {a[0] for a in APPS}:
        raise HTTPException(404, "医药应用不存在")
    if user.get("application_service_key_id"):
        raise HTTPException(403, "医药应用暂不支持服务密钥")
    source = await load(db, workspace_id=workspace_id, user=user)
    calculate(source, app_id, body)
    from core.models.db.db_initial_models import User

    uid = str(user["user_id"])
    account = await db.scalar(
        select(User).where(or_(cast(User.uuid, String) == uid, User.name == uid))
    )
    await current_principal(db, uid, account.id if account else 0)
    params = body.model_dump(exclude={"idempotency_key"})
    params["data_fingerprint"] = digest(source["data"])
    hashed = digest(params)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {
            "key": f"{APPLICATION_ID}:{workspace_id}:{uid}:{app_id}:{body.idempotency_key}"
        },
    )
    row = await db.scalar(
        select(ApplicationRun).where(
            ApplicationRun.application_id == APPLICATION_ID,
            ApplicationRun.workspace_id == workspace_id,
            ApplicationRun.creator_id == uid,
            ApplicationRun.app_id == app_id,
            ApplicationRun.idempotency_key == body.idempotency_key,
        )
    )
    if row:
        if row.input_hash != hashed:
            raise HTTPException(409, "同一幂等标识不可用于不同参数或数据版本")
        return row.public()
    row = ApplicationRun(
        id=str(uuid.uuid4()),
        application_id=APPLICATION_ID,
        workspace_id=workspace_id,
        app_id=app_id,
        creator_id=uid,
        user_pk=account.id if account else 0,
        workflow_version=WORKFLOW_VERSION,
        parameters=params,
        idempotency_key=body.idempotency_key,
        input_hash=hashed,
    )
    db.add(row)
    await db.flush()
    result = row.public()
    await db.commit()
    return result


async def authorized(db, workspace_id, run_id, user):
    await authorize_workspace(db, workspace_id, user)
    row = await db.get(ApplicationRun, run_id)
    if (
        row is None
        or row.application_id != APPLICATION_ID
        or row.workspace_id != workspace_id
        or row.creator_id != str(user["user_id"])
    ):
        raise HTTPException(404, "医药运行不存在")
    return row


async def execute_workflow(db, run):
    if run.workflow_version != WORKFLOW_VERSION:
        raise HTTPException(409, "医药流程版本不一致")
    user = await current_principal(db, run.creator_id, run.user_pk)
    source = await load(db, workspace_id=run.workspace_id, user=user)
    if digest(source["data"]) != run.parameters["data_fingerprint"]:
        raise HTTPException(409, "演示数据版本已变更，请重新提交")
    body = CalculationInput(
        **{k: run.parameters[k] for k in CalculationInput.model_fields}
    )
    result = calculate(source, run.app_id, body)
    # Static reviewed method references remain distinguishable from retrieved evidence.
    result["knowledge_retrieval"] = {"status": "not_verified", "citations": []}
    try:
        from core.models.db.db_initial_models import KnowledgeBase
        from core.helpers.askdata_flow.knowledge_retrieval_service import (
            retrieve_knowledge_for_workspace,
        )

        ids = []
        for r in source["runtime"]["resources"]:
            if r["kind"] == "knowledge_base":
                kb = await db.get(KnowledgeBase, int(r["id"]))
                if kb and kb.dataset_id:
                    ids.append(kb.dataset_id)
        if not ids:
            raise ValueError("No bound datasets")
        bundle = await retrieve_knowledge_for_workspace(
            db, run.workspace_id, result["title"], top_k=3, dataset_id_allowlist=ids
        )
        result["knowledge_retrieval"] = {
            "status": "partial" if bundle.partial_errors else "completed",
            "citations": [
                {k: v for k, v in c.items() if k != "raw_record"} for c in bundle.chunks
            ],
        }
        if not bundle.chunks or bundle.partial_errors:
            result["warnings"].append(
                "知识召回不完整；仅引用已版本化方法文档，不能作政策适用结论。"
            )
    except Exception:
        result["warnings"].append("知识检索不可用；数值结果仍可复核，政策判断未完成。")
    return {
        "result": result,
        "runtime": source["runtime"],
        "html": render_report(result, result["evidence"]),
    }


async def persist_result(db, run, output):
    from core.models.db.db_initial_models import DashboardGenerationArtifact
    from core.helpers.askdata_flow.report_draft_registration import (
        register_html_report_draft,
    )
    from core.modules.application_center.runtime_context import (
        resolve_application_runtime_context,
    )
    from types import SimpleNamespace

    principal = await current_principal(db, run.creator_id, run.user_pk)
    current = await resolve_application_runtime_context(
        db,
        workspace_id=run.workspace_id,
        user=principal,
        requested=SimpleNamespace(
            application_id=APPLICATION_ID, installation_id=None, package_version=None
        ),
    )
    if (
        current["resource_snapshot_digest"]
        != output["runtime"]["resource_snapshot_digest"]
    ):
        raise HTTPException(409, "登记前资源已变化")
    result = output["result"]
    title = f"{result['period']} {result['title']}（模拟）"
    document = DashboardGenerationArtifact(
        workspace_id=run.workspace_id,
        user_id=run.creator_id,
        session_id=run.id,
        report_session_id=run.id,
        artifact_type="report_html",
        artifact_name=title,
        artifact_key=f"application-run:{run.id}",
        status="completed",
        is_latest=True,
        version=1,
        round_index=1,
        source_stage_name=WORKFLOW_VERSION,
        output_payload={
            "review_content": {"document_html": output["html"], "report_spec": result}
        },
        generation_metadata={
            "application_id": APPLICATION_ID,
            "workflow_version": WORKFLOW_VERSION,
            "run_id": run.id,
        },
    )
    db.add(document)
    await db.flush()
    url = f"/api/application-center/v1/workspaces/{run.workspace_id}/applications/{APPLICATION_ID}/runs/{run.id}/document"
    registered = await register_html_report_draft(
        db,
        html_artifact=document,
        report_url=url,
        creator_id=run.creator_id,
        title=title,
        canonical_question=None,
        source_session_id=run.id,
        application_context=output["runtime"],
        analysis_scope={
            "period_start": result["period"],
            "period_end": result["period"],
            "entities": [result["entity"]],
            "currency": "CNY",
        },
    )
    run.result = {
        "product_type": "report",
        "artifact_id": registered["production_artifact_id"],
        "html_artifact_id": document.id,
        "title": title,
        "review_status": "draft",
        "data_fingerprint": result["data_fingerprint"],
        "analysis": result,
    }
    run.status = "completed"
    run.updated_at = now()
