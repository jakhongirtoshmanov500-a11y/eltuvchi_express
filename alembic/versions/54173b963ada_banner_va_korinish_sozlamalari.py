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
    # Bazaga yetishmayotgan ustunlarni qo'shish
    op.add_column('system_settings', sa.Column('referral_visible', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('system_settings', sa.Column('cashback_visible', sa.Boolean(), server_default='true', nullable=True))
    op.add_column('system_settings', sa.Column('banner_image_url', sa.String(), nullable=True))
    op.add_column('system_settings', sa.Column('banner_link_url', sa.String(), nullable=True))
    op.add_column('system_settings', sa.Column('banner_is_active', sa.Boolean(), server_default='false', nullable=True))
    op.add_column('system_settings', sa.Column('courier_terms', sa.Text(), nullable=True))
    op.add_column('system_settings', sa.Column('partner_terms', sa.Text(), nullable=True))
    op.add_column('system_settings', sa.Column('client_terms', sa.Text(), nullable=True))


def downgrade() -> None:
    # Qaytarish holati uchun
    op.drop_column('system_settings', 'client_terms')
    op.drop_column('system_settings', 'partner_terms')
    op.drop_column('system_settings', 'courier_terms')
    op.drop_column('system_settings', 'banner_is_active')
    op.drop_column('system_settings', 'banner_link_url')
    op.drop_column('system_settings', 'banner_image_url')
    op.drop_column('system_settings', 'cashback_visible')
    op.drop_column('system_settings', 'referral_visible')