"""Signed-telemetry verification seam (AGENTS_AND_COMPUTE.md §5).

Device telemetry arrives **signed** with the device hardware identity key (issued
by Vault PKI). The ingest worker verifies the signature and quarantines devices
that fail. In production this verifies against the device's public key / Vault;
for local/dev/tests a deterministic stand-in is provided. Swap by overriding the
``get_telemetry_verifier`` dependency.
"""

from __future__ import annotations

import hashlib
from typing import Protocol


def reading_payload(serial: str, kind: str, ts_iso: str, value: float | None) -> str:
    """Canonical signed payload for one reading."""
    return f"{serial}|{kind}|{ts_iso}|{value}"


def _expected_signature(pubkey: str, payload: str) -> str:
    return hashlib.sha256(f"{pubkey}|{payload}".encode()).hexdigest()


class TelemetryVerifier(Protocol):
    def verify(self, pubkey: str | None, payload: str, signature: str) -> bool: ...


class LocalDevTelemetryVerifier:
    """Deterministic stand-in for Vault-backed signature verification."""

    def verify(self, pubkey: str | None, payload: str, signature: str) -> bool:
        if not pubkey:
            return False
        return signature == _expected_signature(pubkey, payload)

    def sign(self, pubkey: str, payload: str) -> str:
        """Device-side analogue used by tests to produce a valid signature."""
        return _expected_signature(pubkey, payload)


def get_telemetry_verifier() -> TelemetryVerifier:
    return LocalDevTelemetryVerifier()
