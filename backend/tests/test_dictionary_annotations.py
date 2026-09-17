from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.main import annotations, dictionary, save_annotation
from app.models import Annotation, DictionaryEntry, LearnerWordState, Reading, User, VocabularyItem
from app.schemas import AnnotationInput
from app.services import DictionaryDefinition, DictionaryProvider, DictionaryUnavailableError, KoreanDictionaryNotFoundError


class Provider(DictionaryProvider):
    def lookup(self, lemma: str) -> DictionaryDefinition:
        assert lemma == "민지"
        return DictionaryDefinition(gloss="a Korean feminine given name", part_of_speech="proper noun", forms=["민지는"], source="korean-dictionary-v2", english_translation="Minji")


class ParticleProvider(DictionaryProvider):
    def __init__(self) -> None:
        self.lookups: list[str] = []

    def lookup(self, lemma: str) -> DictionaryDefinition:
        self.lookups.append(lemma)
        if lemma == "아침에":
            raise KoreanDictionaryNotFoundError("No Korean dictionary entry was found")
        assert lemma == "아침"
        return DictionaryDefinition(gloss="하루의 처음이나 이른 시간.", part_of_speech="명사", forms=["아침"], source="korean-dictionary", english_translation="morning")


class UnavailableProvider(DictionaryProvider):
    def lookup(self, lemma: str) -> DictionaryDefinition:
        raise DictionaryUnavailableError("offline")


class RefreshedProvider(DictionaryProvider):
    def lookup(self, lemma: str) -> DictionaryDefinition:
        assert lemma == "냉장고"
        return DictionaryDefinition(gloss="음식을 차갑게 보관하는 상자 모양의 기계.", part_of_speech="명사", forms=["냉장고"], source="korean-dictionary-v2", english_translation="refrigerator")


def test_dictionary_returns_normalized_entry_and_learner_state() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="dictionary@example.com", password_hash="hash")
            session.add_all([user, DictionaryEntry(lemma="비", gloss="rain", english_translation="rain", part_of_speech="noun", forms=["비가"], source="seed")]); session.commit()
            session.add(LearnerWordState(user_id=user.id, lemma="비", encounters=3, lookups=2)); session.commit()
            result = dictionary(" 비 ", user, session)
            assert result.lemma == "비" and result.gloss == "rain"
            assert result.english_translation == "rain"
            assert result.encounters == 3 and result.lookups == 2
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_dictionary_fetches_and_replaces_placeholder_entry() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="lookup@example.com", password_hash="hash")
            session.add_all([user, DictionaryEntry(lemma="민지", gloss="Definition not cached yet", source="placeholder")]); session.commit()
            result = dictionary("민지", user, session, Provider())
            assert result.gloss == "a Korean feminine given name"
            assert result.english_translation == "Minji"
            assert result.source == "korean-dictionary-v2"
            assert session.get(DictionaryEntry, "민지").source == "korean-dictionary-v2"
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_dictionary_returns_a_users_saved_vocabulary_meaning_first() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="vocabulary-definition@example.com", password_hash="hash")
            session.add(user); session.flush()
            session.add(VocabularyItem(user_id=user.id, term="민지", normalized_term="민지", meaning="Minji", tags=[])); session.commit()
            result = dictionary("민지", user, session, Provider())
            assert result.gloss == "Minji"
            assert result.english_translation == "Minji"
            assert result.source == "vocabulary"
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_dictionary_matches_common_conjugations_to_saved_base_forms() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="conjugation@example.com", password_hash="hash")
            session.add(user); session.flush()
            session.add(VocabularyItem(user_id=user.id, term="읽다", normalized_term="읽다", meaning="to read", tags=[])); session.commit()
            result = dictionary("읽었어요", user, session, Provider())
            assert result.lemma == "읽다"
            assert result.gloss == "to read"
            assert result.source == "vocabulary"
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_dictionary_falls_back_from_particle_to_base_word() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="particle@example.com", password_hash="hash")
            session.add(user); session.commit()
            provider = ParticleProvider()
            result = dictionary("아침에", user, session, provider)
            assert provider.lookups == ["아침에", "아침"]
            assert result.lemma == "아침"
            assert result.english_translation == "morning"
            assert session.get(DictionaryEntry, "아침") is not None
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_dictionary_hides_a_cached_romanization() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="romanization@example.com", password_hash="hash")
            session.add_all([user, DictionaryEntry(lemma="소설", gloss="산문으로 이루어진 문학 작품.", english_translation="soseol", source="korean-dictionary", forms=["소설"])])
            session.commit()

            result = dictionary("소설", user, session, UnavailableProvider())

            assert result.english_translation is None
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_dictionary_refreshes_legacy_english_definition_cache_entries() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="legacy-dictionary@example.com", password_hash="hash")
            session.add_all([user, DictionaryEntry(lemma="냉장고", gloss="음식을 차갑게 보관하는 상자 모양의 기계.", english_translation="A box-shaped machine used to store food at a low temperature.", source="korean-dictionary", forms=["냉장고"])])
            session.commit()

            result = dictionary("냉장고", user, session, RefreshedProvider())

            assert result.english_translation == "refrigerator"
            assert result.source == "korean-dictionary-v2"
            assert session.get(DictionaryEntry, "냉장고").english_translation == "refrigerator"
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_annotations_upsert_once_per_user_reading_and_token() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="annotation@example.com", password_hash="hash")
            session.add(user); session.flush()
            reading = Reading(user_id=user.id, title="A reading", content={})
            session.add(reading); session.commit()
            first = save_annotation(reading.id, "t1", AnnotationInput(note="first note"), user, session)
            second = save_annotation(reading.id, "t1", AnnotationInput(note="updated note"), user, session)
            assert first.id == second.id and second.note == "updated note"
            assert len(session.scalars(select(Annotation)).all()) == 1
            assert annotations(reading.id, user, session)[0].token_id == "t1"
    finally:
        Base.metadata.drop_all(engine); engine.dispose()
