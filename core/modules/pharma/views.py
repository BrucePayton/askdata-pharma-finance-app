"""Authenticated pharmaceutical API over canonical workspace and artifact resources."""

from fastapi import Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from core.modules.workspace import workspace_router
from storage.pgsql_storage import Database
from core.models.common.response import success
from core.modules.application_center.service import identity, authorize_workspace
from core.modules.application_center.run_models import ApplicationRun
from .catalog import APPLICATION_ID
from .source import load, context
from .runs import CalculationInput, RunInput, calculate, submit, authorized

BASE = "/application-center/workspaces/{workspace_id}/applications/pharma-finance"


def response(value, status=200):
    result = success(data=jsonable_encoder(value))
    result.status_code = status
    result.headers["Cache-Control"] = "no-store"
    return result


@workspace_router.get(BASE + "/context")
async def get_context(
    workspace_id: int, request: Request, db: AsyncSession = Depends(Database.get_db)
):
    return response(
        context(await load(db, workspace_id=workspace_id, user=identity(request)))
    )


@workspace_router.post(BASE + "/apps/{app_id}/calculation")
async def calculation(
    workspace_id: int,
    app_id: str,
    body: CalculationInput,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    return response(
        calculate(
            await load(db, workspace_id=workspace_id, user=identity(request)),
            app_id,
            body,
        )
    )


@workspace_router.post(BASE + "/apps/{app_id}/runs")
async def start(
    workspace_id: int,
    app_id: str,
    body: RunInput,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    return response(
        await submit(
            db,
            workspace_id=workspace_id,
            app_id=app_id,
            user=identity(request),
            body=body,
        ),
        202,
    )


@workspace_router.get(BASE + "/runs")
async def history(
    workspace_id: int, request: Request, db: AsyncSession = Depends(Database.get_db)
):
    user = identity(request)
    await authorize_workspace(db, workspace_id, user)
    rows = (
        await db.scalars(
            select(ApplicationRun)
            .where(
                ApplicationRun.application_id == APPLICATION_ID,
                ApplicationRun.workspace_id == workspace_id,
                ApplicationRun.creator_id == str(user["user_id"]),
            )
            .order_by(ApplicationRun.created_at.desc())
            .limit(50)
        )
    ).all()
    return response({"items": [r.public() for r in rows]})


@workspace_router.get(BASE + "/runs/{run_id}")
async def get_run(
    workspace_id: int,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    return response(
        (await authorized(db, workspace_id, run_id, identity(request))).public()
    )


@workspace_router.get(BASE + "/runs/{run_id}/document")
async def document(
    workspace_id: int,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    from core.models.db.db_initial_models import (
        ProductionArtifact,
        DashboardGenerationArtifact,
    )

    row = await authorized(db, workspace_id, run_id, identity(request))
    if row.status != "completed":
        raise HTTPException(409, "报告尚未完成")
    artifact = await db.get(ProductionArtifact, row.result["artifact_id"])
    source = await db.get(DashboardGenerationArtifact, row.result["html_artifact_id"])
    if (
        not artifact
        or artifact.workspace_id != workspace_id
        or artifact.gmt_deleted
        or artifact.status != "active"
        or not source
        or source.workspace_id != workspace_id
        or source.gmt_deleted
    ):
        raise HTTPException(404, "报告不可用")
    return response(
        {"document_html": source.output_payload["review_content"]["document_html"]}
    )


@workspace_router.get("/application-center/pharma/workspaces")
async def pharma_workspaces(
    request: Request, db: AsyncSession = Depends(Database.get_db)
):
    from core.models.db.db_initial_models import (
        DomainApplicationInstallation,
        WorkSpace,
    )

    user = identity(request)
    rows = (
        await db.scalars(
            select(DomainApplicationInstallation).where(
                DomainApplicationInstallation.application_id == APPLICATION_ID
            )
        )
    ).all()
    items = []
    for installation in rows:
        try:
            ws = await authorize_workspace(db, installation.workspace_id, user)
        except HTTPException:
            continue
        items.append({"id": ws.id, "name": ws.name})
    return response({"workspaces": items})


from core.modules.askdata.request_model import AskDataChatStreamRequest
from core.modules.application_center.review_contracts import ReviewRequest


@workspace_router.post(BASE + "/analysis")
async def start_analysis(
    workspace_id: int,
    body: AskDataChatStreamRequest,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    from core.modules.askdata.views import askdata_chat_stream_view

    # Journal execution is already detached from its SSE response by the platform.
    # Return only its handle so Quick Tunnel clients can poll without SSE.
    await authorize_workspace(db, workspace_id, identity(request))
    if (
        body.workspace_id != workspace_id
        or not body.application_context
        or body.application_context.application_id != APPLICATION_ID
    ):
        raise HTTPException(422, "问数空间或应用上下文不匹配")
    body.stream_protocol = "analysis.v1"
    result = await askdata_chat_stream_view(request, body, db)
    run_id = result.headers.get("X-Analysis-Run-ID")
    if not run_id:
        return result
    return response({"run_id": run_id, "thread_id": body.thread_id}, 202)


async def journal_for(workspace_id, run_id, request, db):
    from core.modules.askdata.stream_journal_views import authorized_journal

    journal, metadata, _ = await authorized_journal(run_id, request, db)
    if (
        metadata["workspace_id"] != workspace_id
        or (metadata.get("context", {}).get("application_context") or {}).get(
            "application_id"
        )
        != APPLICATION_ID
    ):
        raise HTTPException(404, "医药分析不存在")
    return journal


@workspace_router.get(BASE + "/analysis/{run_id}")
async def analysis_status(
    workspace_id: int,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    from core.modules.askdata.stream_journal_views import stream_status

    await journal_for(workspace_id, run_id, request, db)
    return response(await stream_status(run_id, request, db))


@workspace_router.post(BASE + "/analysis/{run_id}/cancel")
async def analysis_cancel(
    workspace_id: int,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    journal = await journal_for(workspace_id, run_id, request, db)
    return response({"status": await journal.request_cancel()})


@workspace_router.get(BASE + "/runs/{run_id}/review-state")
async def review_state(
    workspace_id: int,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    from core.models.db.db_initial_models import ProductionArtifact

    row = await authorized(db, workspace_id, run_id, identity(request))
    if row.status != "completed":
        raise HTTPException(409, "报告尚未完成")
    artifact = await db.get(ProductionArtifact, row.result["artifact_id"])
    if not artifact or artifact.workspace_id != workspace_id or artifact.gmt_deleted:
        raise HTTPException(404, "报告不可用")
    return response(artifact.payload_ref)


@workspace_router.get(BASE + "/runs/{run_id}/review-document")
async def review_document(
    workspace_id: int,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    from core.modules.askdata.report_lifecycle_views import review_document as canonical

    row = await authorized(db, workspace_id, run_id, identity(request))
    if row.status != "completed":
        raise HTTPException(409, "报告尚未完成")
    return await canonical(row.result["artifact_id"], workspace_id, request, db)


@workspace_router.post(BASE + "/runs/{run_id}/review")
async def review(
    workspace_id: int,
    run_id: str,
    body: ReviewRequest,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    from core.modules.askdata.report_lifecycle_views import review_report

    row = await authorized(db, workspace_id, run_id, identity(request))
    if row.status != "completed" or body.workspace_id != workspace_id:
        raise HTTPException(422, "报告范围不匹配")
    return await review_report(row.result["artifact_id"], body, request, db)


@workspace_router.post(BASE + "/runs/{run_id}/revision")
async def revision(
    workspace_id: int,
    run_id: str,
    request: Request,
    db: AsyncSession = Depends(Database.get_db),
):
    from core.modules.askdata.report_lifecycle_views import create_report_revision

    row = await authorized(db, workspace_id, run_id, identity(request))
    if row.status != "completed":
        raise HTTPException(409, "报告尚未完成")
    return await create_report_revision(
        row.result["artifact_id"], workspace_id, request, db
    )
