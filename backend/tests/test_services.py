from datetime import datetime, timezone
from copy import deepcopy
import json
import httpx
import pytest
from app.schemas import GenerationRequest, LearningEventInput
from app.services import ConfiguredGenerationProvider, ConfiguredKoreanDictionaryProvider, GenerationUnavailableError, GenerationValidationError, OpenAIGenerationProvider, StubGenerationProvider, is_romanization_of_lemma, normalize_lemma, validate_reading, vocabulary_lookup_lemmas

def test_normalize_lemma() -> None:
    assert normalize_lemma(" 도서관 ") == "도서관"
def test_vocabulary_lookup_lemmas_include_common_base_forms() -> None:
    assert vocabulary_lookup_lemmas("읽었어요") == ["읽었어요", "읽다"]


def test_vocabulary_lookup_lemmas_include_hae_seo_base_forms() -> None:
    assert vocabulary_lookup_lemmas("시작해서") == ["시작해서", "시작하다"]


@pytest.mark.parametrize(("word", "lemma"), [
    ("먹어서", "먹다"),
    ("먹으니까", "먹다"),
    ("먹으려고", "먹다"),
    ("먹으세요", "먹다"),
    ("시작하셨습니다", "시작하다"),
    ("공부하겠습니다", "공부하다"),
    ("읽지만", "읽다"),
    ("가는데", "가다"),
])
def test_vocabulary_lookup_lemmas_include_common_verb_endings(word: str, lemma: str) -> None:
    assert lemma in vocabulary_lookup_lemmas(word)


def test_vocabulary_lookup_lemmas_include_base_words_without_particles() -> None:
    assert vocabulary_lookup_lemmas("아침에") == ["아침에", "아침"]
def test_stub_reading_is_valid() -> None:
    reading = StubGenerationProvider().generate(GenerationRequest(), [])
    assert validate_reading(reading).questions[0].correct_option_id == "a"
    assert reading.english_title


def test_reading_validation_accepts_questions_with_shared_correct_answer_text() -> None:
    reading = StubGenerationProvider().generate(GenerationRequest(), [])
    first_correct = next(option for option in reading.questions[0].options if option.id == reading.questions[0].correct_option_id)
    second_correct = next(option for option in reading.questions[1].options if option.id == reading.questions[1].correct_option_id)
    second_correct.text = first_correct.text

    assert validate_reading(reading) is reading


def test_reading_validation_allows_missing_tokens_for_reader_fallback() -> None:
    reading = StubGenerationProvider().generate(GenerationRequest(), [])
    reading.tokens.pop()

    assert validate_reading(reading) is reading


def test_lookup_event_schema() -> None:
    event = LearningEventInput(id="123", type="lookup", lemma="비", provider="local", occurred_at=datetime.now(timezone.utc))
    assert event.lookup_before_answer is False

def test_configured_provider_sends_the_expected_request() -> None:
    expected = StubGenerationProvider().generate(GenerationRequest(), []).model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.url == httpx.URL("https://provider.example/readings")
        assert json.loads(request.content)["controls"]["model"] == "test-model"
        return httpx.Response(200, json=expected)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading = ConfiguredGenerationProvider("https://provider.example/readings", "test-token", 5, client).generate(GenerationRequest(model="test-model"), ["도서관"])

    assert reading.title == expected["title"]


def test_openai_provider_sends_the_requested_model_and_parses_json_output() -> None:
    expected = StubGenerationProvider().generate(GenerationRequest(), []).model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-openai-key"
        assert request.url == httpx.URL("https://api.openai.com/v1/responses")
        body = json.loads(request.content)
        assert body["model"] == "GPT5-mini-Studierende"
        assert "max_output_tokens" not in body
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["text"]["format"]["schema"]["additionalProperties"] is False
        assert "english_title" in body["text"]["format"]["schema"]["required"]
        assert set(body["text"]["format"]["schema"]["$defs"]["Question"]["required"]) >= {"target_lemmas", "target_grammar"}
        assert "Known learner vocabulary: 도서관" in body["input"]
        assert "close, complete English translation of the Korean text field" in body["input"]
        assert "concise, natural English translation of the Korean title field only" in body["input"]
        assert "do not summarize, introduce, label, explain" in body["input"]
        assert "learning goals, vocabulary or grammar commentary" in body["input"]
        assert "Create exactly three distinct questions" in body["input"]
        assert "Include a token for every Korean word in the text" in body["input"]
        assert "Use a varied, natural subset rather than forcing every listed term" in body["input"]
        assert "Recent reading titles: none" in body["input"]
        return httpx.Response(200, json={"output_text": json.dumps(expected)})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading = OpenAIGenerationProvider("test-openai-key", 5, client=client).generate(GenerationRequest(model="GPT5-mini-Studierende"), ["도서관"])

    assert reading.title == expected["title"]


def test_openai_compatible_provider_uses_configured_base_url() -> None:
    expected = StubGenerationProvider().generate(GenerationRequest(), []).model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("https://chat.kiconnect.nrw/api/v1/responses")
        return httpx.Response(200, json={"output_text": json.dumps(expected)})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        reading = OpenAIGenerationProvider("test-kiconnect-key", 5, "https://chat.kiconnect.nrw/api/v1", client).generate(GenerationRequest(), [])

    assert reading.title == expected["title"]


def test_korean_dictionary_provider_parses_an_exact_entry() -> None:
    payload = {"channel": {"item": [{"word": "비", "pos": "명사", "sense": [{"definition": "하늘에서 내리는 물방울.", "translation": [{"trans_lang": "영어", "trans_word": "rain"}]}]}]}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["q"] == "비"
        assert request.url.params["method"] == "exact"
        assert request.url.params["translated"] == "y"
        assert request.url.params["trans_lang"] == "1"
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        definition = ConfiguredKoreanDictionaryProvider("https://dictionary.example/search", "dictionary-key", 5, client).lookup("비")

    assert definition.gloss == "하늘에서 내리는 물방울."
    assert definition.english_translation == "rain"
    assert definition.part_of_speech == "명사"
    assert definition.source == "korean-dictionary-v2"


def test_korean_dictionary_provider_falls_back_to_an_english_definition_when_the_word_is_romanized() -> None:
    payload = {"channel": {"item": [{"word": "소설", "pos": "명사", "sense": [{"definition": "산문으로 이루어진 문학 작품.", "translation": [{"trans_lang": "영어", "trans_word": "soseol", "trans_dfn": "novel"}]}]}]}}

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        definition = ConfiguredKoreanDictionaryProvider("https://dictionary.example/search", "dictionary-key", 5, client).lookup("소설")

    assert definition.english_translation == "novel"
    assert is_romanization_of_lemma("soseol", "소설")


def test_korean_dictionary_provider_prefers_an_english_word_over_its_definition() -> None:
    payload = {"channel": {"item": [{"word": "냉장고", "pos": "명사", "sense": [{"definition": "음식을 차갑게 보관하는 상자 모양의 기계.", "translation": [{"trans_lang": "영어", "trans_word": "refrigerator", "trans_dfn": "A box-shaped machine used to store food at a low temperature."}]}]}]}}

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))) as client:
        definition = ConfiguredKoreanDictionaryProvider("https://dictionary.example/search", "dictionary-key", 5, client).lookup("냉장고")

    assert definition.english_translation == "refrigerator"


def test_korean_dictionary_provider_falls_back_to_xml() -> None:
    payload = """<channel><item><word>비</word><pos>명사</pos><sense><definition>하늘에서 내리는 물방울.</definition></sense></item></channel>"""

    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload, headers={"content-type": "application/xml"}))) as client:
        definition = ConfiguredKoreanDictionaryProvider("https://dictionary.example/search", "dictionary-key", 5, client).lookup("비")

    assert definition.gloss == "하늘에서 내리는 물방울."
    assert definition.part_of_speech == "명사"

def test_configured_provider_rejects_missing_configuration() -> None:
    try:
        ConfiguredGenerationProvider(None, None, 5).generate(GenerationRequest(), [])
    except GenerationUnavailableError as error:
        assert str(error) == "Generation provider is not configured"
    else:
        raise AssertionError("Expected an unconfigured provider to fail")


def test_openai_provider_reports_generation_timeouts() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("Request timed out")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GenerationUnavailableError, match="Generation timed out after 120 seconds; please try again"):
            OpenAIGenerationProvider("test-key", 120, client=client).generate(GenerationRequest(), [])


@pytest.mark.parametrize("mutate", [
    lambda reading: setattr(reading, "english_translation", " "),
    lambda reading: setattr(reading.questions[0], "explanation", " "),
    lambda reading: setattr(reading.questions[0], "english_translation", " "),
    lambda reading: setattr(reading.questions[0], "english_explanation", " "),
    lambda reading: setattr(reading.questions[0], "evidence_sentence_ids", ["missing"]),
    lambda reading: setattr(reading.questions[0], "correct_option_id", "missing"),
    lambda reading: setattr(reading.questions[1], "id", reading.questions[0].id),
    lambda reading: setattr(reading.tokens[0], "sentence_id", "missing"),
])
def test_reading_validation_rejects_invalid_generated_content(mutate) -> None:
    reading = deepcopy(StubGenerationProvider().generate(GenerationRequest(), []))
    mutate(reading)
    with pytest.raises(GenerationValidationError):
        validate_reading(reading)


def test_configured_provider_distinguishes_invalid_content() -> None:
    invalid = StubGenerationProvider().generate(GenerationRequest(), []).model_dump(mode="json")
    invalid["questions"][0]["explanation"] = ""
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=invalid))) as client:
        with pytest.raises(GenerationValidationError):
            ConfiguredGenerationProvider("https://provider.example/readings", "test-token", 5, client).generate(GenerationRequest(), [])
