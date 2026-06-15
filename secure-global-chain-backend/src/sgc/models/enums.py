"""Domain enums — single source of truth (DOMAIN_MODEL.md §Enums).

Values are the exact strings the screens render, so the frontend binds with zero
remapping. Stored as VARCHAR + CHECK (``native_enum=False``) so the same models
run on PostgreSQL (prod) and SQLite (tests) without a DB-side enum type.
"""

from __future__ import annotations

from enum import Enum

import sqlalchemy as sa


class BatchStatus(str, Enum):
    in_process = "In process"
    hold = "Hold"
    inspection = "Inspection"
    released = "Released"
    quarantine = "Quarantine"
    rejected = "Rejected"


class QualityState(str, Enum):
    compliant = "Compliant"
    review = "Review"
    quarantine = "Quarantine"
    verified = "Verified"
    escalated = "Escalated"
    watch = "Watch"


class Severity(str, Enum):
    critical = "Critical"
    major = "Major"
    minor = "Minor"


class RiskLevel(str, Enum):
    critical = "Critical"
    high = "High"
    watch = "Watch"


class StatusToken(str, Enum):
    """The StatusDot/Badge vocabulary."""

    pass_ = "pass"
    warn = "warn"
    fail = "fail"
    info = "info"
    neutral = "neutral"


class Sourcing(str, Enum):
    single = "single"
    dual = "dual"


class MaterialKind(str, Enum):
    ds = "DS"
    excipient = "excipient"
    component = "component"


class TaskKind(str, Enum):
    clearance = "Clearance"
    monitoring = "Monitoring"
    ipc = "IPC"
    sign_off = "Sign-off"
    calibration = "Calibration"


class Framework(str, Enum):
    gmp = "GMP"
    glp = "GLP"
    gxp = "GxP"


def sa_enum(enum_cls: type[Enum]) -> sa.Enum:
    """Build a portable SQLAlchemy Enum that persists the enum *value* strings."""
    return sa.Enum(
        enum_cls,
        name=enum_cls.__name__.lower(),
        native_enum=False,
        create_constraint=True,  # emit a CHECK so values are enforced in-DB
        length=32,
        values_callable=lambda e: [member.value for member in e],
    )
