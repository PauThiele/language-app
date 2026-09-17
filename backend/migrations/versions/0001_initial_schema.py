"""Initial graded-reader schema.

Revision ID: 0001_initial_schema
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(320), nullable=False), sa.Column("password_hash", sa.String(512), nullable=False), sa.Column("generation_quota", sa.Integer(), nullable=False, server_default="20"), sa.Column("generated_today", sa.Integer(), nullable=False, server_default="0"), sa.Column("generation_quota_date", sa.Date(), nullable=True))
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("refresh_tokens", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("token_id", sa.String(36), nullable=False), sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_refresh_tokens_token_id", "refresh_tokens", ["token_id"], unique=True)
    op.create_table("vocabulary_items", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("term", sa.String(255), nullable=False), sa.Column("meaning", sa.String(1000)), sa.Column("tags", sa.JSON(), nullable=False), sa.Column("normalized_term", sa.String(255), nullable=False), sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "term", name="uq_vocabulary_user_term"))
    op.create_index("ix_vocabulary_items_user_id", "vocabulary_items", ["user_id"])
    op.create_index("ix_vocabulary_items_normalized_term", "vocabulary_items", ["normalized_term"])
    op.create_table("anki_imports", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("filename", sa.String(255), nullable=False), sa.Column("delimiter", sa.String(1), nullable=False), sa.Column("column_mapping", sa.JSON(), nullable=False), sa.Column("imported_count", sa.Integer(), nullable=False), sa.Column("updated_count", sa.Integer(), nullable=False), sa.Column("skipped_count", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("dictionary_entries", sa.Column("lemma", sa.String(255), primary_key=True), sa.Column("gloss", sa.String(1000), nullable=False), sa.Column("part_of_speech", sa.String(64)), sa.Column("forms", sa.JSON(), nullable=False), sa.Column("source", sa.String(64), nullable=False))
    op.create_table("learner_word_states", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("lemma", sa.String(255), nullable=False), sa.Column("confidence", sa.Float(), nullable=False), sa.Column("encounters", sa.Integer(), nullable=False), sa.Column("lookups", sa.Integer(), nullable=False), sa.Column("correct_answers", sa.Integer(), nullable=False), sa.Column("incorrect_answers", sa.Integer(), nullable=False), sa.UniqueConstraint("user_id", "lemma", name="uq_learner_state_user_lemma"))
    op.create_table("readings", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("title", sa.String(500), nullable=False), sa.Column("content", sa.JSON(), nullable=False), sa.Column("completed", sa.Boolean(), nullable=False, server_default=sa.false()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("annotations", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("reading_id", sa.String(36), sa.ForeignKey("readings.id"), nullable=False), sa.Column("token_id", sa.String(128), nullable=False), sa.Column("note", sa.String(2000), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "reading_id", "token_id", name="uq_annotation_token"))
    op.create_table("learning_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False), sa.Column("event_type", sa.String(64), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))

def downgrade() -> None:
    for table in ["learning_events", "annotations", "readings", "learner_word_states", "dictionary_entries", "anki_imports", "vocabulary_items", "refresh_tokens", "users"]:
        op.drop_table(table)
