"""add_feedback_table

Revision ID: 9ebf069fb624
Revises: 
Create Date: 2026-01-23 00:54:45.527861

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '9ebf069fb624'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Создаем таблицу feedback
    op.create_table(
        'feedback',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('was_helpful', sa.Boolean(), nullable=False),
        sa.Column('helped_decision', sa.Boolean(), nullable=False),
        sa.Column('rating', sa.Integer(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ondelete='CASCADE'),
    )
    
    # Создаем индексы для оптимизации запросов
    op.create_index('ix_feedback_session_id', 'feedback', ['session_id'])
    op.create_index('ix_feedback_created_at', 'feedback', ['created_at'])


def downgrade() -> None:
    # Удаляем индексы
    op.drop_index('ix_feedback_created_at', table_name='feedback')
    op.drop_index('ix_feedback_session_id', table_name='feedback')
    
    # Удаляем таблицу
    op.drop_table('feedback')
