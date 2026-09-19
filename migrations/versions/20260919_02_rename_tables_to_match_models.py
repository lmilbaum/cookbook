"""Name each table after its model: the snake_case plural of the class name.

types -> recipe_types (RecipeType), shopping_list -> shopping_list_items
(ShoppingListItem), recipe_state -> recipe_states (RecipeState) and
shopping_list_state -> shopping_list_states (ShoppingListState). Data is kept;
PostgreSQL's primary-key and unique constraint names keep their old names.

Revision ID: 20260919_02
Revises: 20260919_01
"""

from __future__ import annotations

from alembic import op

revision = "20260919_02"
down_revision = "20260919_01"
branch_labels = None
depends_on = None

_RENAMES = {
    "types": "recipe_types",
    "shopping_list": "shopping_list_items",
    "recipe_state": "recipe_states",
    "shopping_list_state": "shopping_list_states",
}


def upgrade() -> None:
    for old, new in _RENAMES.items():
        op.rename_table(old, new)


def downgrade() -> None:
    for old, new in _RENAMES.items():
        op.rename_table(new, old)
