"""The authenticated caller, derived from validated JWT claims."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Principal:
    """A validated identity. ``sub`` maps to ``users.keycloak_sub``."""

    sub: str
    email: str | None
    name: str | None
    roles: frozenset[str]
    # Whether this is a human (vs a Keycloak service account). Consequential
    # actions require ``is_human`` per SECURITY.md §1.
    is_human: bool = True
    raw_claims: dict = field(default_factory=dict, repr=False)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    @classmethod
    def from_claims(cls, claims: dict) -> "Principal":
        realm_roles = (claims.get("realm_access") or {}).get("roles") or []
        # Keycloak service accounts carry a `clientId` and no human identity.
        is_human = "clientId" not in claims
        return cls(
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name") or claims.get("preferred_username"),
            roles=frozenset(realm_roles),
            is_human=is_human,
            raw_claims=claims,
        )
