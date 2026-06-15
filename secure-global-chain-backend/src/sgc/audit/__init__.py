"""Append-only, hash-chained audit trail (SECURITY.md §5)."""

from .chain import (
    GENESIS_HASH,
    AuditPayload,
    append_audit_event,
    canonical_json,
    compute_hash,
    verify_chain,
)

__all__ = [
    "GENESIS_HASH",
    "AuditPayload",
    "append_audit_event",
    "canonical_json",
    "compute_hash",
    "verify_chain",
]
