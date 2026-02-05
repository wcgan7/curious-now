from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends

from curious_now.api.deps import AuthedUser, get_db, require_user
from curious_now.api.schemas import SimpleOkResponse, UserWatchesResponse
from curious_now.repo_stage5 import simple_ok
from curious_now.repo_stage6 import list_watches, unwatch_cluster, watch_cluster

router = APIRouter()


@router.post("/user/watches/clusters/{cluster_id}", response_model=SimpleOkResponse)
def post_watch_cluster(
    cluster_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    watch_cluster(conn, user_id=user.user_id, cluster_id=cluster_id)
    return simple_ok()


@router.delete("/user/watches/clusters/{cluster_id}", response_model=SimpleOkResponse)
def delete_watch_cluster(
    cluster_id: UUID,
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> SimpleOkResponse:
    unwatch_cluster(conn, user_id=user.user_id, cluster_id=cluster_id)
    return simple_ok()


@router.get("/user/watches/clusters", response_model=UserWatchesResponse)
def get_watches(
    user: AuthedUser = Depends(require_user),
    conn: psycopg.Connection[Any] = Depends(get_db),
) -> UserWatchesResponse:
    return list_watches(conn, user_id=user.user_id)

