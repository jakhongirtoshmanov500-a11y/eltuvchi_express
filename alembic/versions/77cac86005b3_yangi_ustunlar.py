"""yangi_ustunlar

Revision ID: 77cac86005b3
Revises: 752b75562c8b
Create Date: 2026-09-01 15:38:16.578619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '77cac86005b3'
down_revision: Union[str, None] = '752b75562c8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('users', sa.Column('birth_date', sa.Date(), nullable=True))

def downgrade() -> None:
    op.drop_column('users', 'birth_date')