"""Rename the stored recipe source "other" to "unknown".

Updates ``recipes.source`` and the ``source`` field of recipes saved inside the
recipe-state JSON (edited and custom recipes). When the JSON changes its
revision is bumped so a tab still holding the old values gets a conflict on its
next save instead of writing "other" back.

Revision ID: 20260919_03
Revises: 20260919_02
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "20260919_03"
down_revision = "20260919_02"
branch_labels = None
depends_on = None


def _rename(old: str, new: str) -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text("UPDATE recipes SET source = :new WHERE source = :old"), {"old": old, "new": new}
    )
    states = sa.table("recipe_states", sa.column("id", sa.Integer), sa.column("revision", sa.Integer),
                      sa.column("payload", sa.JSON))
    for row in connection.execute(sa.select(states.c.id, states.c.revision, states.c.payload)).fetchall():
        payload: dict[str, Any] = row.payload
        recipes = [*payload.get("overrides", {}).values(), *payload.get("custom", [])]
        changed = [recipe for recipe in recipes if recipe.get("source") == old]
        if not changed:
            continue
        for recipe in changed:
            recipe["source"] = new
        connection.execute(
            sa.update(states).where(states.c.id == row.id).values(payload=payload, revision=row.revision + 1)
        )


def upgrade() -> None:
    _rename("other", "unknown")


def downgrade() -> None:
    _rename("unknown", "other")
