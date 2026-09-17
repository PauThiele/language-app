from datetime import date, datetime, timezone
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON
from app.database import Base

def now() -> datetime: return datetime.now(timezone.utc)
def identifier() -> str: return str(uuid4())

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    generation_quota: Mapped[int] = mapped_column(Integer, default=20)
    generated_today: Mapped[int] = mapped_column(Integer, default=0)
    generation_quota_date: Mapped[date | None] = mapped_column(nullable=True)

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class VocabularyItem(Base):
    __tablename__ = "vocabulary_items"
    __table_args__ = (UniqueConstraint("user_id", "normalized_term", name="uq_vocabulary_user_normalized_term"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    term: Mapped[str] = mapped_column(String(255), index=True)
    meaning: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    normalized_term: Mapped[str] = mapped_column(String(255), index=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class AnkiImport(Base):
    __tablename__ = "anki_imports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    delimiter: Mapped[str] = mapped_column(String(1))
    column_mapping: Mapped[dict] = mapped_column(JSON)
    imported_count: Mapped[int] = mapped_column(Integer)
    updated_count: Mapped[int] = mapped_column(Integer)
    skipped_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class DictionaryEntry(Base):
    __tablename__ = "dictionary_entries"
    lemma: Mapped[str] = mapped_column(String(255), primary_key=True)
    gloss: Mapped[str] = mapped_column(String(1000))
    english_translation: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    part_of_speech: Mapped[str | None] = mapped_column(String(64), nullable=True)
    forms: Mapped[list[str]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(64), default="seed")

class LearnerWordState(Base):
    __tablename__ = "learner_word_states"
    __table_args__ = (UniqueConstraint("user_id", "lemma"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    lemma: Mapped[str] = mapped_column(String(255), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=.35)
    encounters: Mapped[int] = mapped_column(Integer, default=0)
    lookups: Mapped[int] = mapped_column(Integer, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_answers: Mapped[int] = mapped_column(Integer, default=0)

class Reading(Base):
    __tablename__ = "readings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(500))
    content: Mapped[dict] = mapped_column(JSON)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (UniqueConstraint("user_id", "reading_id", "token_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    reading_id: Mapped[str] = mapped_column(ForeignKey("readings.id"), index=True)
    token_id: Mapped[str] = mapped_column(String(128))
    note: Mapped[str] = mapped_column(String(2000))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class LearningEvent(Base):
    __tablename__ = "learning_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
