"""Device & firmware PKI seam.

In production this is backed by **Vault PKI** (SECURITY.md §2-3): the firmware
signing key and device identity certs live in Vault and never touch Postgres.
For local/dev and tests we provide a deterministic stand-in so the human-gated,
audited flows can be exercised end-to-end without a Vault server.

Swap the implementation by overriding the ``get_firmware_signer`` /
``get_device_identity_provider`` dependencies; the rest of the code is unchanged.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SignedFirmware:
    digest: str  # "sha256:…"
    signature: str
    signing_key_ref: str


class FirmwareSigner(Protocol):
    def sign(self, version: str, artifact_ref: str | None) -> SignedFirmware: ...


class DeviceIdentityProvider(Protocol):
    def issue_pubkey(self, serial: str) -> str: ...


class LocalDevSigner:
    """Deterministic stand-in for Vault PKI firmware signing. NOT for production."""

    signing_key_ref = "vault:pki/dev/firmware-signing-key"

    def sign(self, version: str, artifact_ref: str | None) -> SignedFirmware:
        preimage = f"{version}:{artifact_ref or ''}".encode()
        digest = hashlib.sha256(preimage).hexdigest()
        signature = hashlib.sha256(f"sig:{self.signing_key_ref}:{digest}".encode()).hexdigest()
        return SignedFirmware(
            digest=f"sha256:{digest}",
            signature=signature,
            signing_key_ref=self.signing_key_ref,
        )


class LocalDevIdentityProvider:
    """Stand-in for Vault-issued device identity public keys. NOT for production."""

    def issue_pubkey(self, serial: str) -> str:
        material = hashlib.sha256(f"device:{serial}".encode()).hexdigest()
        return f"dev-pub:{material}"


def get_firmware_signer() -> FirmwareSigner:
    return LocalDevSigner()


def get_device_identity_provider() -> DeviceIdentityProvider:
    return LocalDevIdentityProvider()
