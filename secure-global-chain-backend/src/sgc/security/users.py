"""Mirror the authenticated principal into the ``users`` table.

Keycloak is the credential/role authority; this keeps a local row so
``released_by`` / ``signed_by`` / ``actor_id`` FKs resolve (SECURITY.md §1).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.user import User
from .principal import Principal


async def sync_user(session: AsyncSession, principal: Principal) -> User:
    """Get-or-create the local mirror for ``principal`` and refresh its fields."""
    result = await session.execute(
        select(User).where(User.keycloak_sub == principal.sub)
    )
    user = result.scalar_one_or_none()
    roles = sorted(principal.roles)
    if user is None:
        user = User(
            keycloak_sub=principal.sub,
            email=principal.email,
            display_name=principal.name,
            roles=roles,
        )
        session.add(user)
        await session.flush()
    else:
        user.email = principal.email
        user.display_name = principal.name
        user.roles = roles
    return user
