"""Add English translations to dictionary entries.

Revision ID: 0003_add_dictionary_english_translation
Revises: 0002_normalize_vocabulary_unique
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_add_dictionary_english_translation"
down_revision = "0002_normalize_vocabulary_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dictionary_entries", sa.Column("english_translation", sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column("dictionary_entries", "english_translation")
