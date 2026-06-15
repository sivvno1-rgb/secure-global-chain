"""Identity kernel: JWT validation (Keycloak/OIDC) and RBAC dependencies."""

from .deps import get_current_principal, get_jwt_validator, require_role
from .jwt import JwtValidator, TokenValidationError
from .principal import Principal

__all__ = [
    "Principal",
    "JwtValidator",
    "TokenValidationError",
    "get_current_principal",
    "get_jwt_validator",
    "require_role",
]
