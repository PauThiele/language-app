"""Make vocabulary uniqueness use normalized terms.

Revision ID: 0002_normalize_vocabulary_unique
Revises: 0001_initial_schema
"""
from alembic import op

revision = "0002_normalize_vocabulary_unique"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("vocabulary_items") as batch:
            batch.drop_constraint("uq_vocabulary_user_term", type_="unique")
            batch.create_unique_constraint("uq_vocabulary_user_normalized_term", ["user_id", "normalized_term"])
    else:
        op.drop_constraint("uq_vocabulary_user_term", "vocabulary_items", type_="unique")
        op.create_unique_constraint("uq_vocabulary_user_normalized_term", "vocabulary_items", ["user_id", "normalized_term"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("vocabulary_items") as batch:
            batch.drop_constraint("uq_vocabulary_user_normalized_term", type_="unique")
            batch.create_unique_constraint("uq_vocabulary_user_term", ["user_id", "term"])
    else:
        op.drop_constraint("uq_vocabulary_user_normalized_term", "vocabulary_items", type_="unique")
        op.create_unique_constraint("uq_vocabulary_user_term", "vocabulary_items", ["user_id", "term"])
