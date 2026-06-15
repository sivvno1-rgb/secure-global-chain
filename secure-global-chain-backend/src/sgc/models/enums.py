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


class DeviceState(str, Enum):
    provisioned = "Provisioned"
    online = "Online"
    transmitting = "Transmitting"
    offline = "Offline"
    quarantined = "Quarantined"
    decommissioned = "Decommissioned"


class FirmwareState(str, Enum):
    draft = "Draft"
    signed = "Signed"
    staged = "Staged"
    rolling = "Rolling"
    deployed = "Deployed"
    rolled_back = "Rolled back"


class StreamKind(str, Enum):
    temp = "temp"
    particle = "particle"
    biosignal = "biosignal"
    humidity = "humidity"


class ShipmentState(str, Enum):
    in_transit = "in_transit"
    delivered = "delivered"


class HypothesisState(str, Enum):
    open = "open"
    under_review = "under_review"
    supported = "supported"
    refuted = "refuted"


class EvidenceMethod(str, Enum):
    frequentist = "frequentist"
    bayesian = "bayesian"


class EvidenceState(str, Enum):
    pending = "pending"
    running = "running"
    complete = "complete"
    failed = "failed"


class ValidationReportState(str, Enum):
    draft = "draft"
    in_review = "in_review"
    approved = "approved"


class SolverStatus(str, Enum):
    optimal = "optimal"
    feasible = "feasible"
    infeasible = "infeasible"
    timeout = "timeout"


class ScheduleState(str, Enum):
    draft = "draft"
    solved = "solved"
    committed = "committed"
    failed = "failed"


class AgentRunStatus(str, Enum):
    running = "running"
    awaiting_human = "awaiting_human"
    accepted = "accepted"
    rejected = "rejected"
    failed = "failed"


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
