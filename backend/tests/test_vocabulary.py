from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.database import Base
from app.main import create_vocabulary, import_anki, update_vocabulary, vocabulary
from app.models import AnkiImport, LearnerWordState, User, VocabularyItem
from app.schemas import MAX_IMPORT_CONTENT_LENGTH, ImportMapping, VocabularyInput
from app.services import preview_csv


def test_vocabulary_crud_and_normalized_duplicates() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="vocabulary@example.com", password_hash="hash")
        session.add(user); session.commit()
        created = create_vocabulary(VocabularyInput(term=" 단어 ", meaning="word", tags=["core"]), user, session)
        assert created.normalized_term == "단어"
        assert [item.term for item in vocabulary(user, session)] == ["단어"]
        try:
            create_vocabulary(VocabularyInput(term="단어"), user, session)
            assert False, "expected duplicate rejection"
        except Exception as error:
            assert getattr(error, "status_code", None) == 409
        updated = update_vocabulary(created.id, VocabularyInput(term="어휘", meaning="vocabulary", tags=[]), user, session)
        assert updated.term == "어휘"


def test_anki_import_records_mapping_and_updates_normalized_terms() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="import@example.com", password_hash="hash")
        session.add(user); session.commit()
        result = import_anki(ImportMapping(content="Front\tBack\tTags\n단어\tword\tcore; noun\n 단어 \tupdated\tcommon\n\tmissing\t", delimiter="\t", filename="deck.txt", term_column="Front", meaning_column="Back", tags_column="Tags"), user, session)
        assert result.imported == 1 and result.updated == 1 and result.skipped == 1
        item = vocabulary(user, session)[0]
        assert item.meaning == "updated" and item.tags == ["common"]
        audit = session.query(AnkiImport).one()
        assert audit.filename == "deck.txt" and audit.column_mapping["term"] == "Front"


def test_anki_text_export_with_metadata_and_uneven_rows_imports() -> None:
    content = "#separator:tab\n#html:false\n#tags column:3\n나\tI\tcore\n저\tI\n"
    preview = preview_csv(content, None)
    assert preview.headers == ["Field 1", "Field 2", "Tags"]
    assert preview.rows[1] == {"Field 1": "저", "Field 2": "I", "Tags": ""}

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="anki-text@example.com", password_hash="hash")
        session.add(user); session.commit()
        result = import_anki(ImportMapping(content=content, delimiter=",", filename="Selected Notes.txt", term_column="Field 1", meaning_column="Field 2", tags_column="Tags"), user, session)
        assert result.imported == 2 and result.updated == 0 and result.skipped == 0


def test_anki_import_filters_to_selected_note_type() -> None:
    content = "#separator:tab\n#notetype column:1\n#tags column:4\nSentence\t나중에 나중에 다시 전화할게요.\tI'll call you again later.\tsentence\nWord\t나이\tage\tword\n"
    preview = preview_csv(content, None)
    assert preview.headers == ["Note type", "Field 2", "Field 3", "Tags"]
    assert preview.column_values["Note type"] == ["Sentence", "Word"]

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="note-type@example.com", password_hash="hash")
        session.add(user); session.commit()
        result = import_anki(ImportMapping(content=content, delimiter="\t", filename="mixed.txt", term_column="Field 2", meaning_column="Field 3", tags_column="Tags", note_type_column="Note type", note_type="Word"), user, session)
        assert result.imported == 1 and result.skipped == 0
        assert vocabulary(user, session)[0].term == "나이"


def test_anki_import_skips_sentences_but_keeps_detailed_glosses() -> None:
    content = (
        "Front,Back\n"
        "나이,age\n"
        "나중에 다시 전화할게요,I will call you again later\n"
        "공부하다,to study (as a subject)\n"
        "오래 전,a long time ago\n"
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="filtered-import@example.com", password_hash="hash")
        session.add(user); session.commit()

        result = import_anki(ImportMapping(content=content, delimiter=",", filename="mixed.csv", term_column="Front", meaning_column="Back"), user, session)

        assert result.imported == 3 and result.updated == 0 and result.skipped == 1
        assert [item.term for item in vocabulary(user, session)] == ["공부하다", "나이", "오래 전"]


def test_anki_text_export_imports_multi_word_and_parenthetical_glosses() -> None:
    content = "#separator:tab\n#html:false\n일어나다\tto wake up, to get up\n누나\tOlder sister(male)\n"
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="detailed-glosses@example.com", password_hash="hash")
        session.add(user); session.commit()

        result = import_anki(ImportMapping(content=content, delimiter=",", filename="Selected Notes.txt", term_column="Field 1", meaning_column="Field 2"), user, session)

        assert result.imported == 2 and result.updated == 0 and result.skipped == 0


def test_anki_import_extracts_words_from_flattened_example_notes() -> None:
    content = (
        "#separator:tab\n"
        "이야기  할머니가 재미있는 이야기를 해 줬어요.\t이야기    story; talk    할머니가 재미있는 이야기를 해 줬어요.\n"
        "절대 ... 안 ...\tnever\n"
        "어쩔 수 없다  어쩔 수 없었어요.\t어쩔 수 없다    to have no choice    어쩔 수 없었어요.\n"
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="flattened-notes@example.com", password_hash="hash")
        session.add(user); session.commit()

        result = import_anki(ImportMapping(content=content, delimiter=",", filename="Selected Notes.txt", term_column="Field 1", meaning_column="Field 2"), user, session)

        assert result.imported == 3 and result.updated == 0 and result.skipped == 0

def test_vocabulary_removes_legacy_sentence_entries_but_keeps_detailed_glosses() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="legacy-vocabulary@example.com", password_hash="hash")
        session.add(user); session.commit()
        session.add_all([
            VocabularyItem(user_id=user.id, term="가르치다", normalized_term="가르치다", meaning="to teach", tags=[]),
            VocabularyItem(user_id=user.id, term="가리다 모자로 얼굴을 가렸어요.", normalized_term="legacy-sentence", meaning="to cover", tags=[]),
            VocabularyItem(user_id=user.id, term="공부하다", normalized_term="legacy-explanation", meaning="to study (as a subject)", tags=[]),
        ])
        session.commit()

        items = vocabulary(user, session)

        assert [item.term for item in items] == ["공부하다", "가르치다"]
        assert len(session.scalars(select(VocabularyItem).where(VocabularyItem.user_id == user.id)).all()) == 2

def test_anki_import_accepts_large_text_exports() -> None:
    content = "a" * 5_000_001
    request = ImportMapping(content=content, delimiter=",", filename="large-export.txt", term_column="Field 1", meaning_column="Field 2")

    assert len(request.content) == len(content)
    assert len(request.content) <= MAX_IMPORT_CONTENT_LENGTH


def test_anki_import_creates_one_learner_state_for_duplicate_terms() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="duplicate-states@example.com", password_hash="hash")
        session.add(user); session.commit()

        result = import_anki(ImportMapping(content="Front,Back\n단어,word\n 단어 ,updated\n단어,latest\n", delimiter=",", filename="duplicates.csv", term_column="Front", meaning_column="Back"), user, session)

        assert result.imported == 1 and result.updated == 2
        assert session.scalars(select(LearnerWordState).where(LearnerWordState.user_id == user.id)).all()[0].lemma == "단어"
        assert len(session.scalars(select(LearnerWordState).where(LearnerWordState.user_id == user.id)).all()) == 1

def test_anki_import_updates_duplicate_vocabulary_rows_without_constraint_errors() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        user = User(email="duplicate-vocabulary@example.com", password_hash="hash")
        session.add(user); session.commit()

        result = import_anki(ImportMapping(content="Front,Back\n단어,word\n 단어 ,updated\n단어,latest\n", delimiter=",", filename="duplicates.csv", term_column="Front", meaning_column="Back"), user, session)

        assert result.imported == 1 and result.updated == 2
        items = vocabulary(user, session)
        assert len(items) == 1 and items[0].meaning == "latest"
