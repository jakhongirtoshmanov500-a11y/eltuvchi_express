"""banner va korinish sozlamalari

Revision ID: 54173b963ada
Revises: 37eb50c59b14
Create Date: 2026-09-09 11:04:35.423571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54173b963ada'
down_revision: Union[str, None] = '37eb50c59b14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
