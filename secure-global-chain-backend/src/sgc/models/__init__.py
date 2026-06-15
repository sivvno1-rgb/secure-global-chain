"""ORM models.

Importing this package registers every table on ``Base.metadata`` so Alembic
autogenerate and ``create_all`` (tests) both see them.
"""

from .audit import AuditEvent, GENESIS_HASH
from .manufacturing import (
    Batch,
    BatchStep,
    Equipment,
    IpcCheck,
    Line,
    Material,
    Product,
    Site,
    Supplier,
    Task,
)
from .devices import (
    Device,
    DeviceAttestation,
    FirmwareBuild,
    FirmwareRollout,
    ProvisionRequest,
)
from .quality import (
    Audit,
    AuditFinding,
    Capa,
    ComplianceItem,
    Deviation,
)
from .telemetry import (
    ColdchainLane,
    Excursion,
    Reading,
    SensorStream,
    Shipment,
)
from .user import User

__all__ = [
    "User",
    "AuditEvent",
    "GENESIS_HASH",
    "Supplier",
    "Material",
    "Site",
    "Line",
    "Product",
    "Batch",
    "BatchStep",
    "IpcCheck",
    "Task",
    "Equipment",
    "Deviation",
    "Capa",
    "ComplianceItem",
    "Audit",
    "AuditFinding",
    "FirmwareBuild",
    "Device",
    "FirmwareRollout",
    "DeviceAttestation",
    "ProvisionRequest",
    "SensorStream",
    "Reading",
    "ColdchainLane",
    "Shipment",
    "Excursion",
]
