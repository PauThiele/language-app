from datetime import datetime, timezone
import logging
from uuid import uuid4

import jwt
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.auth import current_user, hashing, token_pair
from app.config import settings
from app.database import get_session
from app.models import Annotation, DictionaryEntry, LearnerWordState, LearningEvent, Reading, RefreshToken, User, VocabularyItem
from app.schemas import *
from app.services import ConfiguredGenerationProvider, ConfiguredKoreanDictionaryProvider, DictionaryProvider, DictionaryUnavailableError, GenerationProvider, GenerationUnavailableError, GenerationValidationError, KoreanDictionaryNotFoundError, OpenAIGenerationProvider, apply_learning_event, import_csv, is_romanization_of_lemma, normalize_lemma, preview_csv, prune_invalid_vocabulary, shuffle_question_options, validate_reading, vocabulary_lookup_lemmas

app = FastAPI(title="Korean Graded Reader API", version="0.1.0")
logger = logging.getLogger(__name__)
provider = ConfiguredGenerationProvider(settings.generation_provider_url, settings.generation_provider_token, settings.generation_timeout_seconds)
openai_provider = OpenAIGenerationProvider(settings.openai_api_key, settings.generation_timeout_seconds, settings.openai_responses_base_url)
dictionary_provider = ConfiguredKoreanDictionaryProvider(settings.korean_dictionary_url, settings.korean_dictionary_api_key, settings.dictionary_timeout_seconds)

def get_generation_provider() -> GenerationProvider:
    if settings.openai_api_key:
        return openai_provider
    return provider


def get_dictionary_provider() -> DictionaryProvider:
    return dictionary_provider

@app.get("/health")
def health() -> dict[str, str]: return {"status": "ok"}
@app.post("/auth/register", response_model=TokenResponse, status_code=201)
def register(request: Credentials, session: Session = Depends(get_session)) -> TokenResponse:
    if session.scalar(select(User).where(User.email == request.email.lower())): raise HTTPException(409, "Email is already registered")
    user = User(email=request.email.lower(), password_hash=hashing.hash(request.password)); session.add(user); session.commit()
    access, refresh = token_pair(session, user.id); return TokenResponse(access_token=access, refresh_token=refresh)
@app.post("/auth/login", response_model=TokenResponse)
def login(request: Credentials, session: Session = Depends(get_session)) -> TokenResponse:
    user = session.scalar(select(User).where(User.email == request.email.lower()))
    if not user or not hashing.verify(request.password, user.password_hash): raise HTTPException(401, "Invalid email or password")
    access, refresh = token_pair(session, user.id); return TokenResponse(access_token=access, refresh_token=refresh)
@app.post("/auth/refresh", response_model=TokenResponse)
def refresh(request: RefreshRequest, session: Session = Depends(get_session)) -> TokenResponse:
    try: claims = jwt.decode(request.refresh_token, settings.jwt_secret, algorithms=["HS256"])
    except (jwt.PyJWTError, KeyError) as error: raise HTTPException(401, "Invalid refresh token") from error
    token = session.scalar(select(RefreshToken).where(RefreshToken.token_id == claims.get("jti"), RefreshToken.user_id == claims.get("sub")))
    expires_at = token.expires_at.replace(tzinfo=timezone.utc) if token and token.expires_at.tzinfo is None else token.expires_at if token else None
    if claims.get("kind") != "refresh" or not token or token.revoked_at is not None or expires_at <= datetime.now(timezone.utc): raise HTTPException(401, "Invalid refresh token")
    token.revoked_at = datetime.now(timezone.utc); session.commit()
    access, refresh_token = token_pair(session, claims["sub"]); return TokenResponse(access_token=access, refresh_token=refresh_token)
@app.post("/auth/logout", status_code=204)
def logout(request: RefreshRequest, session: Session = Depends(get_session)) -> None:
    try: claims = jwt.decode(request.refresh_token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as error: raise HTTPException(401, "Invalid refresh token") from error
    token = session.scalar(select(RefreshToken).where(RefreshToken.token_id == claims.get("jti"), RefreshToken.user_id == claims.get("sub")))
    if claims.get("kind") != "refresh" or not token or token.revoked_at is not None:
        raise HTTPException(401, "Invalid refresh token")
    token.revoked_at = datetime.now(timezone.utc); session.commit()
@app.post("/imports/anki/preview", response_model=ImportPreviewResponse)
def preview(request: ImportPreviewRequest, _: User = Depends(current_user)) -> ImportPreviewResponse:
    try:
        return preview_csv(request.content, request.delimiter)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
@app.post("/imports/anki", response_model=ImportResponse)
def import_anki(request: ImportMapping, user: User = Depends(current_user), session: Session = Depends(get_session)) -> ImportResponse:
    try:
        return import_csv(session, user.id, request)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
@app.get("/vocabulary", response_model=list[VocabularyResponse])
def vocabulary(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[VocabularyResponse]:
    if prune_invalid_vocabulary(session, user.id):
        session.commit()
    items = session.scalars(select(VocabularyItem).where(VocabularyItem.user_id == user.id).order_by(VocabularyItem.normalized_term)).all()
    return [VocabularyResponse(id=item.id, term=item.term, normalized_term=item.normalized_term, meaning=item.meaning, tags=item.tags) for item in items]
@app.post("/vocabulary", response_model=VocabularyResponse, status_code=201)
def create_vocabulary(request: VocabularyInput, user: User = Depends(current_user), session: Session = Depends(get_session)) -> VocabularyResponse:
    normalized = normalize_lemma(request.term)
    if not normalized:
        raise HTTPException(422, "Term must contain non-whitespace characters")
    if session.scalar(select(VocabularyItem).where(VocabularyItem.user_id == user.id, VocabularyItem.normalized_term == normalized)):
        raise HTTPException(409, "Vocabulary term already exists")
    item = VocabularyItem(user_id=user.id, term=request.term.strip(), normalized_term=normalized, meaning=request.meaning.strip() if request.meaning else None, tags=[tag.strip() for tag in request.tags if tag.strip()])
    session.add(item); session.commit()
    return VocabularyResponse(id=item.id, term=item.term, normalized_term=item.normalized_term, meaning=item.meaning, tags=item.tags)
@app.put("/vocabulary/{vocabulary_id}", response_model=VocabularyResponse)
def update_vocabulary(vocabulary_id: str, request: VocabularyInput, user: User = Depends(current_user), session: Session = Depends(get_session)) -> VocabularyResponse:
    item = session.scalar(select(VocabularyItem).where(VocabularyItem.id == vocabulary_id, VocabularyItem.user_id == user.id))
    if item is None:
        raise HTTPException(404, "Vocabulary item not found")
    normalized = normalize_lemma(request.term)
    if not normalized:
        raise HTTPException(422, "Term must contain non-whitespace characters")
    duplicate = session.scalar(select(VocabularyItem).where(VocabularyItem.user_id == user.id, VocabularyItem.normalized_term == normalized, VocabularyItem.id != vocabulary_id))
    if duplicate:
        raise HTTPException(409, "Vocabulary term already exists")
    item.term, item.normalized_term = request.term.strip(), normalized
    item.meaning = request.meaning.strip() if request.meaning else None
    item.tags = [tag.strip() for tag in request.tags if tag.strip()]
    session.commit()
    return VocabularyResponse(id=item.id, term=item.term, normalized_term=item.normalized_term, meaning=item.meaning, tags=item.tags)
@app.post("/readings/generate", response_model=GeneratedReading)
def generate(request: GenerationRequest, user: User = Depends(current_user), session: Session = Depends(get_session), generation_provider: GenerationProvider = Depends(get_generation_provider)) -> GeneratedReading:
    from datetime import date
    if user.generation_quota_date != date.today(): user.generation_quota_date, user.generated_today = date.today(), 0
    if user.generated_today >= user.generation_quota: raise HTTPException(429, "Daily generation quota reached")
    known_terms = list(session.scalars(
        select(VocabularyItem.term)
        .where(VocabularyItem.user_id == user.id)
        .order_by(func.random())
        .limit(100)
    ))
    recent_titles = list(session.scalars(
        select(Reading.title)
        .where(Reading.user_id == user.id)
        .order_by(Reading.created_at.desc())
        .limit(5)
    ))
    try:
        request = request.model_copy(update={
            "model": request.model or settings.generation_default_model,
            "recent_reading_titles": recent_titles,
        })
        generated = shuffle_question_options(validate_reading(generation_provider.generate(request, known_terms)))
        generated = generated.model_copy(update={"id": str(uuid4())})
    except GenerationUnavailableError as error:
        raise HTTPException(503, str(error)) from error
    except GenerationValidationError as error:
        logger.warning("Generated reading failed validation: %s", error)
        raise HTTPException(422, str(error)) from error
    session.add(Reading(id=generated.id, user_id=user.id, title=generated.title, content=generated.model_dump())); user.generated_today += 1; session.commit(); return generated
@app.get("/readings", response_model=list[ReadingSummary])
def readings(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[ReadingSummary]:
    return [ReadingSummary(id=item.id, title=item.title, completed=item.completed, created_at=item.created_at) for item in session.scalars(select(Reading).where(Reading.user_id == user.id).order_by(Reading.created_at.desc()))]
@app.get("/readings/{reading_id}", response_model=GeneratedReading)
def reading(reading_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> GeneratedReading:
    item = session.get(Reading, reading_id)
    if not item or item.user_id != user.id: raise HTTPException(404, "Reading not found")
    return GeneratedReading.model_validate({"english_title": "", **item.content})
@app.patch("/readings/{reading_id}/progress", response_model=ReadingSummary)
def progress(reading_id: str, patch: ReadingProgressPatch, user: User = Depends(current_user), session: Session = Depends(get_session)) -> ReadingSummary:
    item = session.get(Reading, reading_id)
    if not item or item.user_id != user.id: raise HTTPException(404, "Reading not found")
    item.completed = patch.completed; session.commit(); return ReadingSummary(id=item.id, title=item.title, completed=item.completed, created_at=item.created_at)
@app.get("/learner-state", response_model=list[LearnerWordStateResponse])
def learner_state(user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[LearnerWordStateResponse]:
    values = session.scalars(select(LearnerWordState).where(LearnerWordState.user_id == user.id).order_by(LearnerWordState.lemma)).all()
    return [LearnerWordStateResponse(lemma=value.lemma, confidence=value.confidence, encounters=value.encounters, lookups=value.lookups, correct_answers=value.correct_answers, incorrect_answers=value.incorrect_answers) for value in values]
@app.get("/dictionary/{lemma}", response_model=DictionaryResponse)
def dictionary(lemma: str, user: User = Depends(current_user), session: Session = Depends(get_session), lookup_provider: DictionaryProvider = Depends(get_dictionary_provider)) -> DictionaryResponse:
    lemma = normalize_lemma(lemma)
    lookup_candidates = vocabulary_lookup_lemmas(lemma)
    vocabulary_by_lemma = {item.normalized_term: item for item in session.scalars(select(VocabularyItem).where(VocabularyItem.user_id == user.id, VocabularyItem.normalized_term.in_(lookup_candidates)))}
    vocabulary = next((vocabulary_by_lemma[candidate] for candidate in lookup_candidates if candidate in vocabulary_by_lemma), None)
    if vocabulary and vocabulary.meaning:
        return DictionaryResponse(lemma=vocabulary.normalized_term, gloss=vocabulary.meaning, english_translation=vocabulary.meaning, part_of_speech=None, forms=[vocabulary.term], source="vocabulary", encounters=0, lookups=0)
    entries_by_lemma = {item.lemma: item for item in session.scalars(select(DictionaryEntry).where(DictionaryEntry.lemma.in_(lookup_candidates)))}
    entry = next((entries_by_lemma[candidate] for candidate in lookup_candidates if candidate in entries_by_lemma and entries_by_lemma[candidate].source != "placeholder"), None)
    if entry is None or entry.source in {"placeholder", "ki-connect", "korean-dictionary"} or (entry.source == "korean-dictionary-v2" and (entry.english_translation is None or is_romanization_of_lemma(entry.english_translation, entry.lemma))):
        definition = None
        lookup_error = None
        resolved_lemma = lemma
        try:
            for candidate in lookup_candidates:
                try:
                    definition = lookup_provider.lookup(candidate)
                    resolved_lemma = candidate
                    break
                except KoreanDictionaryNotFoundError as error:
                    lookup_error = error
            if definition is None:
                raise lookup_error or KoreanDictionaryNotFoundError("No Korean dictionary entry was found")
        except KoreanDictionaryNotFoundError as error:
            raise HTTPException(404, str(error)) from error
        except DictionaryUnavailableError:
            if entry is None:
                entry = DictionaryEntry(lemma=lemma, gloss="Korean dictionary is not configured yet", source="placeholder")
                session.add(entry); session.commit()
        else:
            entry = session.get(DictionaryEntry, resolved_lemma)
            if entry is None:
                entry = DictionaryEntry(lemma=resolved_lemma, gloss=definition.gloss, english_translation=definition.english_translation, part_of_speech=definition.part_of_speech, forms=definition.forms, source=definition.source)
                session.add(entry)
            else:
                entry.gloss, entry.english_translation, entry.part_of_speech, entry.forms, entry.source = definition.gloss, definition.english_translation, definition.part_of_speech, definition.forms, definition.source
            session.commit()
    value = session.scalar(select(LearnerWordState).where(LearnerWordState.user_id == user.id, LearnerWordState.lemma == lemma))
    english_translation = None if is_romanization_of_lemma(entry.english_translation, entry.lemma) else entry.english_translation
    return DictionaryResponse(lemma=entry.lemma, gloss=entry.gloss, english_translation=english_translation, part_of_speech=entry.part_of_speech, forms=entry.forms, source=entry.source, encounters=value.encounters if value else 0, lookups=value.lookups if value else 0)
@app.get("/readings/{reading_id}/annotations", response_model=list[AnnotationResponse])
def annotations(reading_id: str, user: User = Depends(current_user), session: Session = Depends(get_session)) -> list[AnnotationResponse]:
    item = session.get(Reading, reading_id)
    if not item or item.user_id != user.id: raise HTTPException(404, "Reading not found")
    values = session.scalars(select(Annotation).where(Annotation.user_id == user.id, Annotation.reading_id == reading_id).order_by(Annotation.updated_at)).all()
    return [AnnotationResponse(id=value.id, reading_id=value.reading_id, token_id=value.token_id, note=value.note, updated_at=value.updated_at) for value in values]
@app.put("/readings/{reading_id}/annotations/{token_id}", response_model=AnnotationResponse)
def save_annotation(reading_id: str, token_id: str, request: AnnotationInput, user: User = Depends(current_user), session: Session = Depends(get_session)) -> AnnotationResponse:
    item = session.get(Reading, reading_id)
    if not item or item.user_id != user.id: raise HTTPException(404, "Reading not found")
    annotation = session.scalar(select(Annotation).where(Annotation.user_id == user.id, Annotation.reading_id == reading_id, Annotation.token_id == token_id))
    if annotation is None:
        annotation = Annotation(user_id=user.id, reading_id=reading_id, token_id=token_id, note=request.note.strip())
        session.add(annotation)
    else:
        annotation.note, annotation.updated_at = request.note.strip(), datetime.now(timezone.utc)
    session.commit()
    return AnnotationResponse(id=annotation.id, reading_id=annotation.reading_id, token_id=annotation.token_id, note=annotation.note, updated_at=annotation.updated_at)
@app.post("/learning-events", response_model=EventBatchResponse)
def events(request: EventBatchRequest, user: User = Depends(current_user), session: Session = Depends(get_session)) -> EventBatchResponse:
    event_ids = {event.id for event in request.events}
    existing_ids = set(session.scalars(select(LearningEvent.id).where(LearningEvent.id.in_(event_ids))))
    accepted = duplicates = 0
    for event in request.events:
        if event.id in existing_ids:
            duplicates += 1
            continue
        session.add(LearningEvent(id=event.id, user_id=user.id, event_type=event.type, payload=event.model_dump(mode="json"), occurred_at=event.occurred_at))
        apply_learning_event(session, user.id, event)
        existing_ids.add(event.id)
        accepted += 1
    session.commit()
    return EventBatchResponse(accepted=accepted, duplicates=duplicates)
