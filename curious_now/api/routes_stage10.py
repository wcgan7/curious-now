from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from curious_now.api.deps import get_db, require_admin
from curious_now.api.schemas import (
    AdminEntityCreateRequest,
    AdminEntityMergeRequest,
    AdminEntityMergeResponse,
    AdminEntityPatchRequest,
    AdminExperimentCreateRequest,
    AdminExperimentPatchRequest,
    AdminFeatureFlagUpsertRequest,
    AdminSetClusterEntitiesRequest,
    EntitiesResponse,
    Entity,
    EntityDetail,
    EntityRedirectResponse,
    EntityType,
    Experiment,
    FeatureFlag,
    SimpleOkResponse,
    simple_ok,
)
from curious_now.repo_stage10 import (
    admin_create_entity,
    admin_create_experiment,
    admin_merge_entity,
    admin_patch_entity,
    admin_patch_experiment,
    admin_set_cluster_entities,
    admin_upsert_feature_flag,
    get_entity_detail_or_redirect,
    list_entities,
)

router = APIRouter()


@router.get("/entities", response_model=EntitiesResponse)
def get_entities(
    q: str | None = None,
    entity_type: EntityType | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> EntitiesResponse:
    return list_entities(
        conn,
        q=q,
        entity_type=entity_type.value if entity_type else None,
        page=page,
        page_size=page_size,
        user_id=None,
    )


@router.get("/entities/{id}", response_model=EntityDetail)
def get_entity(
    id: UUID,  # noqa: A002
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> EntityDetail:
    try:
        result = get_entity_detail_or_redirect(
            conn,
            entity_id=id,
            user_id=None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if isinstance(result, UUID):
        return JSONResponse(  # type: ignore[return-value]
            status_code=301,
            content=EntityRedirectResponse(redirect_to_entity_id=result).model_dump(mode="json"),
        )
    return result


@router.post(
    "/admin/entities",
    dependencies=[Depends(require_admin)],
    response_model=Entity,
)
def post_admin_entity(
    req: AdminEntityCreateRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> Entity:
    return admin_create_entity(conn, req=req)


@router.patch(
    "/admin/entities/{id}",
    dependencies=[Depends(require_admin)],
    response_model=Entity,
)
def patch_admin_entity(
    id: UUID,  # noqa: A002
    req: AdminEntityPatchRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> Entity:
    try:
        return admin_patch_entity(conn, entity_id=id, req=req)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post(
    "/admin/entities/{id}/merge",
    dependencies=[Depends(require_admin)],
    response_model=AdminEntityMergeResponse,
)
def post_admin_entity_merge(
    id: UUID,  # noqa: A002
    req: AdminEntityMergeRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> AdminEntityMergeResponse:
    try:
        return admin_merge_entity(conn, from_entity_id=id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.put(
    "/admin/clusters/{id}/entities",
    dependencies=[Depends(require_admin)],
    response_model=SimpleOkResponse,
)
def put_admin_cluster_entities(
    id: UUID,  # noqa: A002
    req: AdminSetClusterEntitiesRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    admin_set_cluster_entities(conn, cluster_id=id, req=req)
    return simple_ok()


@router.post(
    "/admin/experiments",
    dependencies=[Depends(require_admin)],
    response_model=Experiment,
)
def post_admin_experiment(
    req: AdminExperimentCreateRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> Experiment:
    return admin_create_experiment(conn, req=req)


@router.patch(
    "/admin/experiments/{id}",
    dependencies=[Depends(require_admin)],
    response_model=Experiment,
)
def patch_admin_experiment(
    id: UUID,  # noqa: A002
    req: AdminExperimentPatchRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> Experiment:
    try:
        return admin_patch_experiment(conn, experiment_id=id, req=req)
    except KeyError:
        raise HTTPException(status_code=404, detail="Not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.put(
    "/admin/feature_flags/{key}",
    dependencies=[Depends(require_admin)],
    response_model=FeatureFlag,
)
def put_admin_feature_flag(
    key: str,
    req: AdminFeatureFlagUpsertRequest,
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> FeatureFlag:
    try:
        return admin_upsert_feature_flag(conn, key=key, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
