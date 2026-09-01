"""add_new_columns

Revision ID: 752b75562c8b
Revises: b2cc642095b6
Create Date: 2026-09-01 15:27:39.519910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '752b75562c8b'
down_revision: Union[str, None] = 'b2cc642095b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
