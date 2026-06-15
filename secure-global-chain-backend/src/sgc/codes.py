"""Human business-key generation (e.g. ``DEV-1182``, ``CAPA-0441``).

Preserves the handoff ID formats (zero-padded numeric suffix). Computes the next
value from the current max; the unique constraint is the final guard.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def next_code(
    session: AsyncSession, model, prefix: str, *, pad: int = 4, start: int = 1
) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    result = await session.execute(select(model.code))
    max_n = start - 1
    for (code,) in result.all():
        match = pattern.match(code or "")
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f"{prefix}-{max_n + 1:0{pad}d}"
