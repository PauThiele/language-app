from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field

MAX_IMPORT_CONTENT_LENGTH = 25_000_000

class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
class RefreshRequest(BaseModel):
    refresh_token: str
class ImportPreviewRequest(BaseModel):
    content: str = Field(max_length=MAX_IMPORT_CONTENT_LENGTH)
    delimiter: Literal[",", "\t"] | None = None
class ImportMapping(BaseModel):
    content: str = Field(max_length=MAX_IMPORT_CONTENT_LENGTH)
    delimiter: Literal[",", "\t"] = ","
    filename: str = Field(default="anki-export", min_length=1, max_length=255)
    term_column: str
    meaning_column: str
    tags_column: str | None = None
    note_type_column: str | None = None
    note_type: str | None = None
class ImportPreviewResponse(BaseModel):
    headers: list[str]
    rows: list[dict[str, str]]
    column_values: dict[str, list[str]] = {}
class ImportResponse(BaseModel):
    imported: int
    updated: int
    skipped: int
class VocabularyInput(BaseModel):
    term: str = Field(min_length=1, max_length=255)
    meaning: str | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list)
class VocabularyResponse(VocabularyInput):
    id: str
    normalized_term: str
class GenerationRequest(BaseModel):
    genre: str = "daily life"
    length: Literal["short", "medium", "long"] = "short"
    new_word_intensity: int = Field(default=2, ge=0, le=5)
    grammar_intensity: int = Field(default=2, ge=0, le=5)
    model: str | None = Field(default=None, max_length=160)
    recent_reading_titles: list[str] = Field(default_factory=list, exclude=True)
class GeneratedReadingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Sentence(GeneratedReadingItem): id: str; text: str
class Token(GeneratedReadingItem): id: str; surface: str; lemma: str; sentence_id: str
class Option(GeneratedReadingItem): id: str; text: str
class Question(BaseModel):
    id: str; prompt: str; options: list[Option]; correct_option_id: str
    evidence_sentence_ids: list[str]; target_lemmas: list[str]; target_grammar: list[str]; explanation: str; english_translation: str; english_explanation: str
    model_config = ConfigDict(extra="forbid")
class GeneratedReading(GeneratedReadingItem):
    id: str; title: str; text: str; sentences: list[Sentence]; tokens: list[Token]
    target_lemmas: list[str]; target_grammar: list[str]; questions: list[Question]; rationale: str; english_translation: str
    english_title: str
class ReadingSummary(BaseModel): id: str; title: str; completed: bool; created_at: datetime
class ReadingProgressPatch(BaseModel): completed: bool
class DictionaryResponse(BaseModel):
    lemma: str; gloss: str; english_translation: str | None = None; part_of_speech: str | None; forms: list[str]; source: str; encounters: int = 0; lookups: int = 0
class LearnerWordStateResponse(BaseModel):
    lemma: str
    confidence: float
    encounters: int
    lookups: int
    correct_answers: int
    incorrect_answers: int
class AnnotationInput(BaseModel):
    note: str = Field(min_length=1, max_length=2000)
class AnnotationResponse(AnnotationInput):
    id: str
    reading_id: str
    token_id: str
    updated_at: datetime
class LearningEventInput(BaseModel):
    id: str; type: Literal["lookup", "encounter", "question_answer", "reading_opened", "reading_completed"]; occurred_at: datetime
    reading_id: str | None = None; sentence_id: str | None = None; lemma: str | None = None
    provider: Literal["local", "naver", "papago", "google"] | None = None; correct: bool | None = None
    target_lemmas: list[str] = []; lookup_before_answer: bool = False
class EventBatchRequest(BaseModel): events: list[LearningEventInput] = Field(min_length=1, max_length=500)
class EventBatchResponse(BaseModel): accepted: int; duplicates: int
