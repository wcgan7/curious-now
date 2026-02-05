from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from curious_now.api.deps import AuthedUser, get_db, optional_user, require_admin
from curious_now.api.schemas import (
    AdminClusterMergeRequest,
    AdminClusterMergeResponse,
    AdminClusterPatchRequest,
    AdminClusterQuarantineRequest,
    AdminClusterSplitRequest,
    AdminClusterSplitResponse,
    AdminFeedbackListResponse,
    AdminFeedbackPatchRequest,
    AdminLineageEdgeCreateRequest,
    AdminLineageNodeCreateRequest,
    AdminSetClusterTopicsRequest,
    AdminTopicCreateRequest,
    AdminTopicMergeRequest,
    AdminTopicMergeResponse,
    AdminTopicPatchRequest,
    ClusterDetail,
    FeedbackIn,
    FeedbackReport,
    FeedbackResponse,
    LineageEdge,
    LineageNode,
    SimpleOkResponse,
    Topic,
)
from curious_now.rate_limit import enforce_rate_limit
from curious_now.repo_stage5 import simple_ok
from curious_now.repo_stage8 import (
    admin_create_lineage_edge,
    admin_create_lineage_node,
    admin_create_topic,
    admin_merge_cluster,
    admin_merge_topic,
    admin_patch_cluster,
    admin_patch_topic,
    admin_set_cluster_status,
    admin_set_cluster_topics,
    admin_split_cluster,
    create_feedback,
    list_feedback,
    patch_feedback,
)

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, status_code=202)
def post_feedback(
    payload: FeedbackIn,
    request: Request,
    user: AuthedUser | None = Depends(optional_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> FeedbackResponse:
    enforce_rate_limit(request, key="feedback_post", limit=30, window_seconds=60)
    fid = create_feedback(conn, user_id=user.user_id if user else None, req=payload)
    return FeedbackResponse(status="accepted", feedback_id=fid)


@router.get(
    "/admin/feedback",
    dependencies=[Depends(require_admin)],
    response_model=AdminFeedbackListResponse,
)
def get_admin_feedback(
    status: Literal["new", "triaged", "resolved", "ignored"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> AdminFeedbackListResponse:
    return list_feedback(conn, status=status, page=page, page_size=page_size)


@router.patch(
    "/admin/feedback/{id}",
    dependencies=[Depends(require_admin)],
    response_model=FeedbackReport,
)
def patch_admin_feedback(
    id: UUID,  # noqa: A002
    patch: AdminFeedbackPatchRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> FeedbackReport:
    try:
        return patch_feedback(conn, feedback_id=id, patch=patch)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/admin/clusters/{id}/merge",
    dependencies=[Depends(require_admin)],
    response_model=AdminClusterMergeResponse,
)
def post_admin_cluster_merge(
    id: UUID,  # noqa: A002
    req: AdminClusterMergeRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> AdminClusterMergeResponse:
    try:
        return admin_merge_cluster(conn, from_cluster_id=id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/admin/clusters/{id}/split",
    dependencies=[Depends(require_admin)],
    response_model=AdminClusterSplitResponse,
)
def post_admin_cluster_split(
    id: UUID,  # noqa: A002
    req: AdminClusterSplitRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> AdminClusterSplitResponse:
    try:
        return admin_split_cluster(conn, source_cluster_id=id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/admin/clusters/{id}/quarantine",
    dependencies=[Depends(require_admin)],
    response_model=SimpleOkResponse,
)
def post_admin_cluster_quarantine(
    id: UUID,  # noqa: A002
    req: AdminClusterQuarantineRequest | None = None,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    admin_set_cluster_status(
        conn,
        cluster_id=id,
        status="quarantined",
        change_type="quarantine",
        notes=req.notes if req else None,
    )
    return simple_ok()


@router.post(
    "/admin/clusters/{id}/unquarantine",
    dependencies=[Depends(require_admin)],
    response_model=SimpleOkResponse,
)
def post_admin_cluster_unquarantine(
    id: UUID,  # noqa: A002
    req: AdminClusterQuarantineRequest | None = None,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    admin_set_cluster_status(
        conn,
        cluster_id=id,
        status="active",
        change_type="unquarantine",
        notes=req.notes if req else None,
    )
    return simple_ok()


@router.patch(
    "/admin/clusters/{id}",
    dependencies=[Depends(require_admin)],
    response_model=ClusterDetail,
)
def patch_admin_cluster(
    id: UUID,  # noqa: A002
    patch: AdminClusterPatchRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> ClusterDetail:
    # Citation enforcement (v0): if text is set, require non-empty supporting_item_ids.
    if patch.takeaway is not None and not patch.takeaway_supporting_item_ids:
        raise HTTPException(status_code=400, detail="takeaway_supporting_item_ids required")
    if patch.summary_intuition is not None and not patch.summary_intuition_supporting_item_ids:
        raise HTTPException(
            status_code=400,
            detail="summary_intuition_supporting_item_ids required",
        )
    if patch.summary_deep_dive is not None and not patch.summary_deep_dive_supporting_item_ids:
        raise HTTPException(
            status_code=400,
            detail="summary_deep_dive_supporting_item_ids required",
        )

    try:
        return admin_patch_cluster(conn, cluster_id=id, patch=patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.put(
    "/admin/clusters/{id}/topics",
    dependencies=[Depends(require_admin)],
    response_model=SimpleOkResponse,
)
def put_admin_cluster_topics(
    id: UUID,  # noqa: A002
    req: AdminSetClusterTopicsRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    admin_set_cluster_topics(conn, cluster_id=id, req=req)
    return simple_ok()


@router.post(
    "/admin/topics",
    dependencies=[Depends(require_admin)],
    response_model=Topic,
)
def post_admin_topic(
    req: AdminTopicCreateRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> Topic:
    return admin_create_topic(conn, req=req)


@router.patch(
    "/admin/topics/{id}",
    dependencies=[Depends(require_admin)],
    response_model=Topic,
)
def patch_admin_topic(
    id: UUID,  # noqa: A002
    req: AdminTopicPatchRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> Topic:
    try:
        return admin_patch_topic(conn, topic_id=id, req=req)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/admin/topics/{id}/merge",
    dependencies=[Depends(require_admin)],
    response_model=AdminTopicMergeResponse,
)
def post_admin_topic_merge(
    id: UUID,  # noqa: A002
    req: AdminTopicMergeRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> AdminTopicMergeResponse:
    try:
        return admin_merge_topic(conn, from_topic_id=id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/admin/lineage/nodes",
    dependencies=[Depends(require_admin)],
    response_model=LineageNode,
)
def post_admin_lineage_node(
    req: AdminLineageNodeCreateRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> LineageNode:
    return admin_create_lineage_node(conn, req=req)


@router.post(
    "/admin/lineage/edges",
    dependencies=[Depends(require_admin)],
    response_model=LineageEdge,
)
def post_admin_lineage_edge(
    req: AdminLineageEdgeCreateRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> LineageEdge:
    try:
        return admin_create_lineage_edge(conn, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
