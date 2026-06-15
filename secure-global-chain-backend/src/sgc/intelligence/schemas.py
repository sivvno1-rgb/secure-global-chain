"""Pydantic v2 schemas for the Intelligence / Systems Map context."""

from __future__ import annotations

from pydantic import BaseModel


class NodeOut(BaseModel):
    id: str
    label: str
    category: str
    status: str
    type: str


class EdgeOut(BaseModel):
    source: str
    target: str
    rel: str


class GraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class NodeDetailOut(BaseModel):
    node: NodeOut
    connection_count: int
    signal: str
