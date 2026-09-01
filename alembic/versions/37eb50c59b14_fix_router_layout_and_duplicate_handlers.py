"""Fix router layout and duplicate handlers

Revision ID: 37eb50c59b14
Revises: 77cac86005b3
Create Date: 2026-09-01 19:37:26.364091

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '37eb50c59b14'
down_revision: Union[str, None] = '77cac86005b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
