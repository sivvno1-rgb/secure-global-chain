"""Intelligence / Systems Map API. Prefix ``/api/v1/intel``.

Read-only graph views: map, node detail, chain-of-custody trace, blast-radius
impact, and the live signal feed. Backed by the GraphStore seam.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..errors import NotFoundError
from ..security import Principal, get_current_principal
from .deps import get_graph_store
from .graph import CATEGORIES, GraphStore, GraphView
from .schemas import EdgeOut, GraphOut, NodeDetailOut, NodeOut

router = APIRouter(prefix="/api/v1/intel", tags=["intelligence"])


def _to_graph_out(view: GraphView) -> GraphOut:
    return GraphOut(
        nodes=[NodeOut(**vars(n)) for n in view.nodes],
        edges=[EdgeOut(**vars(e)) for e in view.edges],
    )


@router.get("/graph", response_model=GraphOut)
async def get_graph(
    filter: str | None = Query(None, description="supply|mfg|quality|compliance"),
    store: GraphStore = Depends(get_graph_store),
    _: Principal = Depends(get_current_principal),
):
    if filter is not None and filter not in CATEGORIES:
        raise HTTPException(
            status_code=422, detail=f"filter must be one of {CATEGORIES}"
        )
    return _to_graph_out(await store.graph(category=filter))


@router.get("/node/{node_id}", response_model=NodeDetailOut)
async def get_node(
    node_id: str,
    store: GraphStore = Depends(get_graph_store),
    _: Principal = Depends(get_current_principal),
):
    detail = await store.node(node_id)
    if detail is None:
        raise NotFoundError(f"Node {node_id} not found")
    return NodeDetailOut(
        node=NodeOut(**vars(detail.node)),
        connection_count=detail.connection_count,
        signal=detail.signal,
    )


@router.get("/trace/{batch_code}", response_model=GraphOut)
async def trace(
    batch_code: str,
    store: GraphStore = Depends(get_graph_store),
    _: Principal = Depends(get_current_principal),
):
    view = await store.trace(batch_code)
    if not view.nodes:
        raise NotFoundError(f"No chain of custody for {batch_code}")
    return _to_graph_out(view)


@router.get("/impact/{node_id}", response_model=GraphOut)
async def impact(
    node_id: str,
    store: GraphStore = Depends(get_graph_store),
    _: Principal = Depends(get_current_principal),
):
    if await store.node(node_id) is None:
        raise NotFoundError(f"Node {node_id} not found")
    return _to_graph_out(await store.impact(node_id))


@router.get("/signals", response_model=list[NodeOut])
async def signals(
    range: str | None = Query(None, description="daily|weekly|monthly|yearly"),
    store: GraphStore = Depends(get_graph_store),
    _: Principal = Depends(get_current_principal),
):
    return [NodeOut(**vars(n)) for n in await store.signals()]
