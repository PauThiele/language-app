from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.main import events
from app.models import LearnerWordState, LearningEvent, User
from app.schemas import EventBatchRequest, LearningEventInput


def event(event_type: str, **values) -> LearningEventInput:
    return LearningEventInput(id=str(uuid4()), type=event_type, occurred_at=datetime.now(timezone.utc), **values)


def test_learning_events_are_idempotent_and_update_only_the_owner() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            first = User(email="events-first@example.com", password_hash="hash")
            second = User(email="events-second@example.com", password_hash="hash")
            session.add_all([first, second]); session.commit()
            batch = EventBatchRequest(events=[
                event("encounter", lemma=" 단어 "),
                event("lookup", lemma="단어"),
                event("question_answer", target_lemmas=["단어", "문법"], correct=True, lookup_before_answer=True),
                event("question_answer", target_lemmas=["문법"], correct=False),
            ])

            accepted = events(batch, first, session)
            assert accepted.accepted == 4 and accepted.duplicates == 0
            word = session.scalar(select(LearnerWordState).where(LearnerWordState.user_id == first.id, LearnerWordState.lemma == "단어"))
            grammar = session.scalar(select(LearnerWordState).where(LearnerWordState.user_id == first.id, LearnerWordState.lemma == "문법"))
            assert (word.encounters, word.lookups, word.correct_answers, word.incorrect_answers) == (1, 1, 1, 0)
            assert (grammar.encounters, grammar.lookups, grammar.correct_answers, grammar.incorrect_answers) == (0, 0, 1, 1)

            replay = events(batch, first, session)
            assert replay.accepted == 0 and replay.duplicates == 4
            word_after_replay = session.scalar(select(LearnerWordState).where(LearnerWordState.user_id == first.id, LearnerWordState.lemma == "단어"))
            assert (word_after_replay.encounters, word_after_replay.lookups, word_after_replay.correct_answers) == (1, 1, 1)

            second_batch = EventBatchRequest(events=[event("lookup", lemma="단어")])
            assert events(second_batch, second, session).accepted == 1
            other_word = session.scalar(select(LearnerWordState).where(LearnerWordState.user_id == second.id, LearnerWordState.lemma == "단어"))
            assert (other_word.encounters, other_word.lookups, other_word.correct_answers, other_word.incorrect_answers) == (0, 1, 0, 0)
            assert session.scalars(select(LearningEvent)).all().__len__() == 5
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()