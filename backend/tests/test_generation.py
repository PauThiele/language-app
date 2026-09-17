from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.main import generate
from app.models import Reading, User, VocabularyItem
from app.schemas import GenerationRequest
import app.services as services
from app.services import GenerationProvider, GenerationUnavailableError, StubGenerationProvider


class Provider(GenerationProvider):
    def __init__(self, reading=None, error: Exception | None = None) -> None:
        self.reading, self.error = reading, error
        self.request: GenerationRequest | None = None
        self.known_terms: list[str] | None = None

    def generate(self, request: GenerationRequest, known_terms: list[str]):
        self.request, self.known_terms = request, known_terms
        if self.error:
            raise self.error
        return self.reading


def test_generation_persists_valid_reading_and_resets_prior_day_quota() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="generation@example.com", password_hash="hash", generation_quota=1, generated_today=1, generation_quota_date=date.today() - timedelta(days=1))
            session.add(user); session.commit()
            result = generate(GenerationRequest(genre="travel", length="long", new_word_intensity=5, grammar_intensity=4), user, session, Provider(StubGenerationProvider().generate(GenerationRequest(), [])))
            assert result.id
            assert user.generated_today == 1 and user.generation_quota_date == date.today()
            assert session.scalar(select(Reading).where(Reading.id == result.id)).content["title"] == result.title
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_generation_assigns_unique_ids_when_provider_reuses_an_id() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="unique-ids@example.com", password_hash="hash")
            provider = Provider(StubGenerationProvider().generate(GenerationRequest(), []))
            session.add(user); session.commit()

            first = generate(GenerationRequest(), user, session, provider)
            second = generate(GenerationRequest(), user, session, provider)

            assert first.id != second.id
            assert session.query(Reading).count() == 2
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_generation_uses_the_configured_default_model_when_none_is_requested() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="default-model@example.com", password_hash="hash")
            provider = Provider(StubGenerationProvider().generate(GenerationRequest(), []))
            session.add(user); session.commit()

            generate(GenerationRequest(), user, session, provider)

            assert provider.request is not None
            assert provider.request.model == "GPT5-mini-Studierende"
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_generation_preserves_a_requested_model() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="requested-model@example.com", password_hash="hash")
            provider = Provider(StubGenerationProvider().generate(GenerationRequest(), []))
            session.add(user); session.commit()

            generate(GenerationRequest(model="another-model"), user, session, provider)

            assert provider.request is not None
            assert provider.request.model == "another-model"
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_generation_uses_a_random_vocabulary_sample_and_avoids_recent_titles() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="varied-reading@example.com", password_hash="hash")
            session.add(user); session.commit()
            session.add(Reading(user_id=user.id, title="A Rainy Day at the Library", content={}))
            session.add_all([
                VocabularyItem(user_id=user.id, term=f"term-{index}", normalized_term=f"term-{index}")
                for index in range(101)
            ])
            session.commit()
            provider = Provider(StubGenerationProvider().generate(GenerationRequest(), []))

            generate(GenerationRequest(), user, session, provider)

            assert provider.request is not None
            assert provider.request.recent_reading_titles == ["A Rainy Day at the Library"]
            assert provider.known_terms is not None
            assert len(provider.known_terms) == 100
            assert set(provider.known_terms) <= {f"term-{index}" for index in range(101)}
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


def test_generation_shuffles_question_options_before_persisting(monkeypatch: pytest.MonkeyPatch) -> None:
    class ReverseRandomizer:
        @staticmethod
        def shuffle(options) -> None:
            options.reverse()

    monkeypatch.setattr(services, "option_randomizer", ReverseRandomizer())
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email="shuffled-options@example.com", password_hash="hash")
            session.add(user); session.commit()

            result = generate(GenerationRequest(), user, session, Provider(StubGenerationProvider().generate(GenerationRequest(), [])))
            saved = session.get(Reading, result.id)

            assert all(question.options[0].id != question.correct_option_id for question in result.questions)
            assert saved is not None
            assert all(question["options"][0]["id"] != question["correct_option_id"] for question in saved.content["questions"])
    finally:
        Base.metadata.drop_all(engine); engine.dispose()


@pytest.mark.parametrize("provider", [
    Provider(error=GenerationUnavailableError("Generation provider is not configured")),
    Provider(StubGenerationProvider().generate(GenerationRequest(), [])),
])
def test_generation_unavailable_or_over_quota_never_persists(provider: Provider) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            user = User(email=f"quota-{id(provider)}@example.com", password_hash="hash", generation_quota=0 if provider.reading else 20)
            session.add(user); session.commit()
            expected_status = 429 if provider.reading else 503
            with pytest.raises(HTTPException) as error:
                generate(GenerationRequest(), user, session, provider)
            assert error.value.status_code == expected_status
            assert session.scalars(select(Reading)).all() == []
    finally:
        Base.metadata.drop_all(engine); engine.dispose()
