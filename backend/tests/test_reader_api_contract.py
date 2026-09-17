from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app, get_generation_provider
from app.services import StubGenerationProvider


def test_authenticated_reader_api_contract_supports_deferred_event_replay() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def test_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    app.dependency_overrides[get_generation_provider] = lambda: StubGenerationProvider()
    try:
        with TestClient(app) as client:
            unauthenticated = client.post("/readings/generate", json={
                "genre": "daily life",
                "length": "short",
                "new_word_intensity": 2,
                "grammar_intensity": 2,
            })
            assert unauthenticated.status_code == 401

            registered = client.post("/auth/register", json={"email": "android@example.com", "password": "safe-password"})
            assert registered.status_code == 201
            tokens = registered.json()
            assert set(tokens) >= {"access_token", "refresh_token", "token_type"}
            headers = {"Authorization": f"Bearer {tokens['access_token']}"}

            generated = client.post("/readings/generate", headers=headers, json={
                "genre": "daily life",
                "length": "short",
                "new_word_intensity": 2,
                "grammar_intensity": 2,
            })
            assert generated.status_code == 200
            reading = generated.json()
            assert {"id", "title", "text", "tokens", "questions", "target_lemmas", "target_grammar"} <= set(reading)
            assert {"id", "sentence_id", "lemma"} <= set(reading["tokens"][0])
            assert {"correct_option_id", "explanation", "english_translation", "english_explanation", "target_lemmas", "target_grammar"} <= set(reading["questions"][0])

            dictionary = client.get(f"/dictionary/{reading['tokens'][0]['lemma']}", headers=headers)
            assert dictionary.status_code == 200
            assert {"lemma", "gloss", "forms", "encounters", "lookups"} <= set(dictionary.json())

            event = {
                "id": str(uuid4()),
                "type": "question_answer",
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "reading_id": reading["id"],
                "target_lemmas": reading["questions"][0]["target_lemmas"],
                "correct": True,
                "lookup_before_answer": True,
            }
            first_sync = client.post("/learning-events", headers=headers, json={"events": [event]})
            retry_sync = client.post("/learning-events", headers=headers, json={"events": [event]})
            assert first_sync.json() == {"accepted": 1, "duplicates": 0}
            assert retry_sync.json() == {"accepted": 0, "duplicates": 1}
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()
