import csv
import json
import logging
import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass
from html import unescape
from itertools import zip_longest
from random import SystemRandom
from uuid import uuid4
from xml.etree import ElementTree
import httpx
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AnkiImport, LearnerWordState, VocabularyItem
from app.schemas import GeneratedReading, GenerationRequest, ImportMapping, ImportPreviewResponse, ImportResponse, Option, Question, Sentence, Token, LearningEventInput

HANGUL = re.compile(r'[\u1100-\u11ff\uac00-\ud7af]')
LATIN = re.compile(r'[A-Za-z]')
SENTENCE_PUNCTUATION = re.compile(r'[.!?;:\u3002\uff01\uff1f]')
HTML_BREAK = re.compile(r'<br\s*/?>', re.IGNORECASE)
HTML_TAG = re.compile(r'<[^>]+>')
ROMANIZATION_INITIALS = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
ROMANIZATION_VOWELS = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu", "ui", "i")
ROMANIZATION_FINALS = ("", "k", "k", "ks", "n", "nj", "nh", "t", "l", "lk", "lm", "lb", "ls", "lt", "lp", "lh", "m", "p", "ps", "t", "t", "ng", "t", "t", "k", "t", "p", "t")
option_randomizer = SystemRandom()
logger = logging.getLogger(__name__)

def import_text(value: str) -> str:
    value = HTML_BREAK.sub('\n', value)
    value = HTML_TAG.sub('', value)
    return ' '.join(unescape(value).replace('\u00a0', ' ').split())

def is_korean_vocabulary(value: str, max_words: int = 2) -> bool:
    punctuation_candidate = value.replace("...", "")
    return bool(HANGUL.search(value)) and not SENTENCE_PUNCTUATION.search(punctuation_candidate) and len(punctuation_candidate.split()) <= max_words

def is_english_translation(value: str) -> bool:
    return bool(LATIN.search(value)) and not HANGUL.search(value)

def is_vocabulary_pair(term: str, meaning: str, max_term_words: int = 2) -> bool:
    return is_korean_vocabulary(term, max_term_words) and is_english_translation(meaning)

def extract_import_vocabulary_pair(raw_term: str, raw_meaning: str) -> tuple[str, str, bool]:
    term = import_text(raw_term)
    meaning = import_text(raw_meaning)
    if is_vocabulary_pair(term, meaning):
        return term, meaning, True

    term_parts = re.split(r'\s{2,}', raw_term)
    meaning_parts = re.split(r'\s{2,}', raw_meaning)
    if len(term_parts) < 2 and len(meaning_parts) < 2:
        return term, meaning, False

    extracted_term = import_text(term_parts[0])
    extracted_meaning = next(
        (candidate for part in meaning_parts if is_english_translation(candidate := import_text(part))),
        "",
    )
    return extracted_term, extracted_meaning, is_vocabulary_pair(extracted_term, extracted_meaning, max_term_words=4)

def prune_invalid_vocabulary(session: Session, user_id: str) -> int:
    invalid_items = [
        item for item in session.scalars(select(VocabularyItem).where(VocabularyItem.user_id == user_id))
        if item.meaning is not None and not is_vocabulary_pair(item.term, item.meaning)
    ]
    for item in invalid_items:
        session.delete(item)
    return len(invalid_items)

def normalize_lemma(value: str) -> str: return unicodedata.normalize("NFC", value).strip().casefold()


def romanize_korean(value: str) -> str:
    syllables: list[str] = []
    for character in normalize_lemma(value):
        codepoint = ord(character) - 0xAC00
        if not 0 <= codepoint < 11172:
            return ""
        initial, remainder = divmod(codepoint, 588)
        vowel, final = divmod(remainder, 28)
        syllables.append(f"{ROMANIZATION_INITIALS[initial]}{ROMANIZATION_VOWELS[vowel]}{ROMANIZATION_FINALS[final]}")
    return "".join(syllables)


def is_romanization_of_lemma(value: str | None, lemma: str) -> bool:
    if not value or not lemma:
        return False
    if value != value.casefold():
        return False
    normalized_value = re.sub(r"[^a-z]", "", value.casefold())
    return bool(normalized_value) and normalized_value == romanize_korean(lemma)


def vocabulary_lookup_lemmas(value: str) -> list[str]:
    normalized = normalize_lemma(value)
    candidates = [normalized]

    def add_candidate(candidate: str) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    ending_replacements = (
        ("으셨습니다", "다"), ("셨습니다", "다"), ("었습니다", "다"), ("았습니다", "다"), ("겠습니다", "다"),
        ("으셨어요", "다"), ("셨어요", "다"), ("었어요", "다"), ("았어요", "다"), ("겠어요", "다"),
        ("으시는데", "다"), ("시는데", "다"), ("으시지만", "다"), ("시지만", "다"), ("으시면", "다"), ("시면", "다"),
        ("으시고", "다"), ("시고", "다"), ("으세요", "다"), ("세요", "다"),
        ("했습니다", "하다"), ("했어요", "하다"), ("해서", "하다"), ("해요", "하다"), ("합니다", "하다"),
        ("이었어요", "이다"), ("였어요", "이다"), ("이에요", "이다"), ("예요", "이다"),
        ("으려고", "다"), ("려고", "다"), ("으니까", "다"), ("니까", "다"), ("으면서", "다"), ("면서", "다"),
        ("었는데", "다"), ("았는데", "다"), ("는데", "다"), ("었지만", "다"), ("았지만", "다"), ("지만", "다"),
        ("으면", "다"), ("면", "다"), ("으러", "다"), ("러", "다"), ("어서", "다"), ("아서", "다"), ("서", "다"),
        ("었다", "다"), ("았다", "다"), ("습니다", "다"), ("어요", "다"), ("아요", "다"),
        ("고", "다"), ("는", "다"), ("은", "다"), ("을", "다"),
    )
    for ending, replacement in ending_replacements:
        if normalized.endswith(ending) and len(normalized) > len(ending):
            add_candidate(normalize_lemma(normalized[:-len(ending)] + replacement))
            break
    particle_endings = ("에게서", "에서는", "에게", "에서", "으로", "에는", "에도", "부터", "까지", "은", "는", "이", "가", "을", "를", "의", "도", "와", "과", "만", "에", "로")
    for ending in particle_endings:
        if normalized.endswith(ending) and len(normalized) > len(ending):
            add_candidate(normalize_lemma(normalized[:-len(ending)]))
            break
    return candidates

def parse_import_content(content: str, delimiter: str | None) -> tuple[list[str], list[dict[str, str]]]:
    lines = content.lstrip("\ufeff").splitlines()
    directives: dict[str, str] = {}
    while lines and lines[0].startswith("#"):
        key, separator, value = lines.pop(0)[1:].partition(":")
        if separator:
            directives[key.strip().casefold()] = value.strip().casefold()
    if not lines:
        raise ValueError("The import file has no vocabulary rows")
    detected_delimiter = {"tab": "\t", "comma": ","}.get(directives.get("separator", ""), delimiter or ("\t" if "\t" in lines[0] else ","))
    try:
        parsed_rows = list(csv.reader(lines, delimiter=detected_delimiter))
    except csv.Error as error:
        raise ValueError("The import file is not valid CSV or TSV text") from error
    if not parsed_rows:
        raise ValueError("The import file has no vocabulary rows")
    if directives:
        column_count = max(len(row) for row in parsed_rows)
        headers = [f"Field {index}" for index in range(1, column_count + 1)]
        metadata_columns = {
            "guid column": "GUID",
            "notetype column": "Note type",
            "deck column": "Deck",
            "tags column": "Tags",
        }
        for directive, header in metadata_columns.items():
            column = directives.get(directive)
            if column and column.isdigit() and 1 <= int(column) <= column_count:
                headers[int(column) - 1] = header
        rows = [dict(zip_longest(headers, row, fillvalue="")) for row in parsed_rows]
    else:
        headers, parsed_rows = parsed_rows[0], parsed_rows[1:]

        # Heuristic: if the header row contains CJK/Hangul characters, assume the
        # file has no header row (Anki exports commonly omit headers). In that
        # case synthesize generic Field names and treat the original header row
        # as a data row.
        def contains_cjk(text: str) -> bool:
            for ch in text:
                code = ord(ch)
                # Hangul Jamo and Hangul Syllables
                if 0x1100 <= code <= 0x11FF or 0xAC00 <= code <= 0xD7AF:
                    return True
                # CJK Unified Ideographs
                if 0x4E00 <= code <= 0x9FFF:
                    return True
                # Hiragana / Katakana
                if 0x3040 <= code <= 0x30FF:
                    return True
            return False

        if any(contains_cjk(h) for h in headers):
            all_rows = [headers] + parsed_rows
            column_count = max(len(row) for row in all_rows)
            headers = [f"Field {index}" for index in range(1, column_count + 1)]
            rows = [dict(zip_longest(headers, row, fillvalue="")) for row in all_rows]
        else:
            if not headers or any(not header.strip() for header in headers):
                raise ValueError("The CSV or TSV file needs a non-empty header row")
            if len(set(headers)) != len(headers):
                raise ValueError("The CSV or TSV file has duplicate header names")
            if any(len(row) > len(headers) for row in parsed_rows):
                raise ValueError("An import row has more columns than the header row")
            rows = [dict(zip_longest(headers, row, fillvalue="")) for row in parsed_rows]
    return headers, rows

def preview_csv(content: str, delimiter: str | None) -> ImportPreviewResponse:
    headers, rows = parse_import_content(content, delimiter)
    column_values = {}
    if "Note type" in headers:
        column_values["Note type"] = sorted({value.strip() for row in rows if (value := row.get("Note type", "")).strip()})
    return ImportPreviewResponse(headers=headers, rows=rows[:10], column_values=column_values)
def import_csv(session: Session, user_id: str, request: ImportMapping) -> ImportResponse:
    imported = updated = skipped = 0
    prune_invalid_vocabulary(session, user_id)
    vocabulary_by_normalized = {item.normalized_term: item for item in session.scalars(select(VocabularyItem).where(VocabularyItem.user_id == user_id))}
    learner_state_lemmas = set(session.scalars(select(LearnerWordState.lemma).where(LearnerWordState.user_id == user_id)))
    headers, rows = parse_import_content(request.content, request.delimiter)
    missing = [column for column in (request.term_column, request.meaning_column, request.tags_column, request.note_type_column) if column and column not in headers]
    if missing:
        raise ValueError(f"Unknown import columns: {', '.join(missing)}")
    for row in rows:
        if request.note_type and (row.get(request.note_type_column or "") or "").strip() != request.note_type:
            continue
        term, meaning, valid_pair = extract_import_vocabulary_pair(
            row.get(request.term_column) or "",
            row.get(request.meaning_column) or "" if request.meaning_column else "",
        )
        if not term: skipped += 1; continue
        normalized = normalize_lemma(term)
        item = vocabulary_by_normalized.get(normalized)
        tags = [tag.strip() for tag in (row.get(request.tags_column) or "").replace(";", ",").split(",") if tag.strip()] if request.tags_column else []
        if not valid_pair:
            skipped += 1; continue
        if item:
            item.term, item.meaning, item.tags, updated = term, meaning or item.meaning, tags or item.tags, updated + 1
        else:
            item = VocabularyItem(user_id=user_id, term=term, normalized_term=normalized, meaning=meaning, tags=tags)
            session.add(item); vocabulary_by_normalized[normalized] = item; imported += 1
        if normalized not in learner_state_lemmas:
            session.add(LearnerWordState(user_id=user_id, lemma=normalized, confidence=.55))
            learner_state_lemmas.add(normalized)
    session.add(AnkiImport(user_id=user_id, filename=request.filename, delimiter=request.delimiter, column_mapping={"term": request.term_column, "meaning": request.meaning_column, "tags": request.tags_column, "note_type_column": request.note_type_column, "note_type": request.note_type}, imported_count=imported, updated_count=updated, skipped_count=skipped))
    session.commit(); return ImportResponse(imported=imported, updated=updated, skipped=skipped)
def state(session: Session, user_id: str, lemma: str) -> LearnerWordState:
    lemma = normalize_lemma(lemma); value = session.scalar(select(LearnerWordState).where(LearnerWordState.user_id == user_id, LearnerWordState.lemma == lemma))
    if value is None: value = LearnerWordState(user_id=user_id, lemma=lemma); session.add(value); session.flush()
    return value
def apply_learning_event(session: Session, user_id: str, event: LearningEventInput) -> None:
    if event.type == "encounter" and event.lemma:
        value = state(session, user_id, event.lemma)
        value.encounters += 1
        value.confidence = min(1, value.confidence + .02)
    if event.type == "lookup" and event.lemma:
        value = state(session, user_id, event.lemma)
        value.lookups += 1
        value.confidence = max(0, value.confidence - .10)
    if event.type == "question_answer":
        for lemma in event.target_lemmas:
            value = state(session, user_id, lemma)
            if event.correct:
                value.correct_answers += 1
                value.confidence = min(1, value.confidence + (.05 if event.lookup_before_answer else .12))
            else:
                value.incorrect_answers += 1
                value.confidence = max(0, value.confidence - .12)
class GenerationProvider(ABC):
    @abstractmethod
    def generate(self, request: GenerationRequest, known_terms: list[str]) -> GeneratedReading: ...
class GenerationUnavailableError(RuntimeError):
    pass
class GenerationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DictionaryDefinition:
    gloss: str
    part_of_speech: str | None
    forms: list[str]
    source: str
    english_translation: str | None = None


class DictionaryProvider(ABC):
    @abstractmethod
    def lookup(self, lemma: str) -> DictionaryDefinition: ...


class DictionaryUnavailableError(RuntimeError):
    pass


class KoreanDictionaryNotFoundError(DictionaryUnavailableError):
    pass


class ConfiguredKoreanDictionaryProvider(DictionaryProvider):
    """Adapter for the National Institute of Korean Language dictionary API."""

    def __init__(
        self,
        url: str | None,
        api_key: str | None,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self.url, self.api_key, self.timeout_seconds, self.client = url, api_key, timeout_seconds, client

    def lookup(self, lemma: str) -> DictionaryDefinition:
        if not self.url or not self.api_key:
            raise DictionaryUnavailableError("Dictionary provider is not configured")
        params = {"key": self.api_key, "q": lemma, "req_type": "json", "part": "word", "advanced": "y", "translated": "y", "trans_lang": "1", "method": "exact"}
        try:
            if self.client:
                response = self.client.get(self.url, params=params)
            else:
                with httpx.Client() as client:
                    response = client.get(self.url, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
            items = self._response_items(response)
            entry = next((item for item in items if isinstance(item, dict) and item.get("word", "").replace("-", "") == lemma), None)
            if entry is None:
                raise KoreanDictionaryNotFoundError("No Korean dictionary entry was found")
            senses = entry.get("sense", [])
            if isinstance(senses, dict):
                senses = [senses]
            gloss = next((str(sense.get("definition", "")).strip() for sense in senses if isinstance(sense, dict) and str(sense.get("definition", "")).strip()), "")
            if not gloss:
                raise ValueError("Dictionary response has no definition")
            part_of_speech = str(entry.get("pos") or "").strip() or None
            english_translation = next((translation for sense in senses if isinstance(sense, dict) and (translation := self._english_translation(sense, lemma))), None)
            return DictionaryDefinition(gloss=gloss, english_translation=english_translation, part_of_speech=part_of_speech, forms=[lemma], source="korean-dictionary-v2")
        except KoreanDictionaryNotFoundError:
            raise
        except (httpx.HTTPError, AttributeError, ElementTree.ParseError, TypeError, ValueError) as error:
            raise DictionaryUnavailableError("Dictionary provider failed to return a valid definition") from error

    @classmethod
    def _response_items(cls, response: httpx.Response) -> list[dict[str, object]]:
        try:
            items = response.json().get("channel", {}).get("item", [])
            return [items] if isinstance(items, dict) else items
        except ValueError:
            root = ElementTree.fromstring(response.content)
            return [
                {
                    "word": cls._xml_text(item, "word"),
                    "pos": cls._xml_text(item, "pos"),
                    "sense": [{"definition": cls._xml_text(sense, "definition"), "translation": [{"trans_lang": cls._xml_text(translation, "trans_lang"), "trans_word": cls._xml_text(translation, "trans_word"), "trans_dfn": cls._xml_text(translation, "trans_dfn")} for translation in cls._xml_elements(sense, "translation")]} for sense in cls._xml_elements(item, "sense")],
                }
                for item in cls._xml_elements(root, "item")
            ]

    @staticmethod
    def _english_translation(sense: dict[str, object], lemma: str) -> str | None:
        translations = sense.get("translation", [])
        if isinstance(translations, dict):
            translations = [translations]
        if not isinstance(translations, list):
            return None
        for translation in translations:
            if not isinstance(translation, dict):
                continue
            language = str(translation.get("trans_lang") or "").strip().casefold()
            if language not in {"1", "en", "eng", "english", "영어"}:
                continue
            for field in ("trans_word", "trans_dfn"):
                value = str(translation.get(field) or "").strip()
                if value and not is_romanization_of_lemma(value, lemma):
                    return value
        return None

    @staticmethod
    def _xml_elements(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
        return [child for child in element.iter() if child.tag.rsplit("}", 1)[-1] == name]

    @classmethod
    def _xml_text(cls, element: ElementTree.Element, name: str) -> str:
        return next((child.text.strip() for child in cls._xml_elements(element, name) if child.text and child.text.strip()), "")
class ConfiguredGenerationProvider(GenerationProvider):
    """Adapter for a server-side provider endpoint that returns a GeneratedReading JSON object."""

    def __init__(
        self,
        url: str | None,
        token: str | None,
        timeout_seconds: float,
        client: httpx.Client | None = None,
    ) -> None:
        self.url, self.token, self.timeout_seconds, self.client = url, token, timeout_seconds, client

    def generate(self, request: GenerationRequest, known_terms: list[str]) -> GeneratedReading:
        if not self.url or not self.token:
            raise GenerationUnavailableError("Generation provider is not configured")
        try:
            request_body = {
                "controls": request.model_dump(),
                "known_terms": known_terms,
                "response_schema": GeneratedReading.model_json_schema(),
            }
            if self.client:
                response = self.client.post(self.url, headers={"Authorization": f"Bearer {self.token}"}, json=request_body)
            else:
                response = httpx.post(
                    self.url,
                    headers={"Authorization": f"Bearer {self.token}"},
                    json=request_body,
                    timeout=self.timeout_seconds,
                )
            response.raise_for_status()
            return validate_reading(GeneratedReading.model_validate(response.json()))
        except httpx.TimeoutException as error:
            raise GenerationUnavailableError(f"Generation timed out after {self.timeout_seconds:g} seconds; please try again") from error
        except httpx.HTTPError as error:
            raise GenerationUnavailableError("Generation provider failed to return a valid reading") from error
        except (ValueError, ValidationError) as error:
            raise GenerationValidationError("Generation provider returned invalid reading content") from error


class OpenAIGenerationProvider(GenerationProvider):
    """Adapter for OpenAI-compatible Responses APIs, including KI:connect."""

    def __init__(
        self,
        api_key: str | None,
        timeout_seconds: float,
        base_url: str = "https://api.openai.com/v1",
        client: httpx.Client | None = None,
    ) -> None:
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.url = f"{base_url.rstrip('/')}/responses"
        self.client = client

    def generate(self, request: GenerationRequest, known_terms: list[str]) -> GeneratedReading:
        if not self.api_key:
            raise GenerationUnavailableError("OpenAI is not configured; set OPENAI_API_KEY on the backend")
        prompt = (
            "Create a new Korean graded reading. Return only data matching the supplied JSON schema. "
            "Do not reuse a canned sample reading. "
            "Include every field in the schema, including empty target_lemmas and target_grammar arrays when they do not apply. "
            "Use unique sentence, token, question, and option IDs. Each token and each question evidence_sentence_id must reference a sentence ID from sentences. "
            "Create exactly three distinct questions, each with two or three options and a correct_option_id that matches one of its options. "
            "Include a token for every Korean word in the text. Each token surface must exactly match its word in the text, and lemma must be its dictionary form. "
            "Keep the rationale and every explanation to one concise sentence. "
            "Give every question a non-empty Korean explanation, English question translation, and English explanation. "
            "The english_title field must be a concise, natural English translation of the Korean title field only. "
            "The english_translation field must be a close, complete English translation of the Korean text field. "
            "Translate only the text: do not summarize, introduce, label, explain, or include rationale, "
            "learning goals, vocabulary or grammar commentary, or any other extra information. "
            "Preserve the text's meaning and all concrete details, including people, places, timing, sequence, conditions, and actions. "
            f"Genre: {request.genre}. Length: {request.length}. "
            f"New-word intensity: {request.new_word_intensity}/5. Grammar intensity: {request.grammar_intensity}/5. "
            f"Known learner vocabulary: {', '.join(known_terms) if known_terms else 'none'}. Use a varied, natural subset rather than forcing every listed term. "
            f"Recent reading titles: {', '.join(request.recent_reading_titles) if request.recent_reading_titles else 'none'}. Avoid repeating their setting, protagonist, or plot."
        )
        request_body = {
            "model": request.model,
            "input": prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "generated_reading",
                    "schema": GeneratedReading.model_json_schema(),
                    "strict": True,
                }
            },
        }
        try:
            if self.client:
                response = self.client.post(self.url, headers={"Authorization": f"Bearer {self.api_key}"}, json=request_body)
            else:
                response = httpx.post(self.url, headers={"Authorization": f"Bearer {self.api_key}"}, json=request_body, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            output_text = payload.get("output_text") or self._output_text(payload)
            return validate_reading(GeneratedReading.model_validate(json.loads(output_text)))
        except httpx.TimeoutException as error:
            raise GenerationUnavailableError(f"Generation timed out after {self.timeout_seconds:g} seconds; please try again") from error
        except httpx.HTTPError as error:
            raise GenerationUnavailableError("OpenAI failed to return a reading") from error
        except GenerationValidationError:
            raise
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            logger.warning("OpenAI returned invalid reading content: %s", error)
            raise GenerationValidationError("OpenAI returned invalid reading content; see backend log for details") from error

    @staticmethod
    def _output_text(payload: dict) -> str:
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    return content["text"]
        raise ValueError("OpenAI response did not include output text")


class StubGenerationProvider(GenerationProvider):
    def generate(self, request: GenerationRequest, known_terms: list[str]) -> GeneratedReading:
        sentences = [Sentence(id="s1", text="민지는 토요일 아침에 동네 도서관에 갔어요."), Sentence(id="s2", text="새 한국 소설을 빌리고 조용한 창가 자리에 앉았어요."), Sentence(id="s3", text="비가 오기 시작해서 민지는 오후까지 책을 읽었어요.")]
        questions = [
            Question(id="q1", prompt="민지는 언제 도서관에 갔어요?", options=[Option(id="a", text="토요일 아침"), Option(id="b", text="월요일 저녁"), Option(id="c", text="일요일 밤")], correct_option_id="a", evidence_sentence_ids=["s1"], target_lemmas=[], target_grammar=[], explanation="첫 번째 문장에 토요일 아침이라고 나와요.", english_translation="When did Minji go to the library?", english_explanation="The first sentence says that she went on Saturday morning."),
            Question(id="q2", prompt="민지는 도서관에서 무엇을 했어요?", options=[Option(id="a", text="새 소설을 빌렸어요"), Option(id="b", text="친구를 만났어요"), Option(id="c", text="운동을 했어요")], correct_option_id="a", evidence_sentence_ids=["s2"], target_lemmas=["소설", "빌리다"], target_grammar=[], explanation="두 번째 문장에 새 소설을 빌렸다고 나와요.", english_translation="What did Minji do at the library?", english_explanation="The second sentence says that she borrowed a new novel."),
            Question(id="q3", prompt="민지가 오후까지 책을 읽은 이유는 무엇이에요?", options=[Option(id="a", text="비가 왔기 때문이에요"), Option(id="b", text="도서관이 문을 닫았기 때문이에요"), Option(id="c", text="숙제가 있었기 때문이에요")], correct_option_id="a", evidence_sentence_ids=["s3"], target_lemmas=["비"], target_grammar=["-기 때문에"], explanation="세 번째 문장에서 비가 오기 시작했다고 설명해요.", english_translation="Why did Minji read until the afternoon?", english_explanation="The third sentence explains that it started to rain.")]
        token_specs = [("민지는", "민지", "s1"), ("토요일", "토요일", "s1"), ("아침에", "아침", "s1"), ("동네", "동네", "s1"), ("도서관에", "도서관", "s1"), ("갔어요", "가다", "s1"), ("새", "새", "s2"), ("한국", "한국", "s2"), ("소설을", "소설", "s2"), ("빌리고", "빌리다", "s2"), ("조용한", "조용하다", "s2"), ("창가", "창가", "s2"), ("자리에", "자리", "s2"), ("앉았어요", "앉다", "s2"), ("비가", "비", "s3"), ("오기", "오다", "s3"), ("시작해서", "시작하다", "s3"), ("민지는", "민지", "s3"), ("오후까지", "오후", "s3"), ("책을", "책", "s3"), ("읽었어요", "읽다", "s3")]
        tokens = [Token(id=f"t{index}", surface=surface, lemma=lemma, sentence_id=sentence_id) for index, (surface, lemma, sentence_id) in enumerate(token_specs, start=1)]
        return GeneratedReading(id=str(uuid4()), title=f"{request.genre} 도서관의 오후", text=" ".join(item.text for item in sentences), sentences=sentences, tokens=tokens, target_lemmas=["도서관", "소설", "빌리다", "비"], target_grammar=["-고", "-기 때문에"], questions=questions, rationale="Short daily-life reading; replace this provider with an LLM adapter.", english_translation="Minji went to the neighborhood library on Saturday morning. She borrowed a new Korean novel and sat by a quiet window. When it began to rain, Minji read until the afternoon.", english_title=f"An Afternoon at the {request.genre.title()} Library")
def validate_reading(reading: GeneratedReading) -> GeneratedReading:
    sentence_ids = {item.id for item in reading.sentences}
    if not reading.title.strip() or not reading.english_title.strip() or not reading.text.strip() or not reading.english_translation.strip():
        raise GenerationValidationError("Reading title, English title, text, and English translation are required")
    if not reading.sentences or len(sentence_ids) != len(reading.sentences) or any(not item.id.strip() or not item.text.strip() for item in reading.sentences):
        raise GenerationValidationError("Reading sentences must have unique IDs and text")
    if len(reading.questions) < 3:
        raise GenerationValidationError("Need at least three questions")
    token_ids = {token.id for token in reading.tokens}
    if len(token_ids) != len(reading.tokens) or any(not token.id.strip() or not token.surface.strip() or not token.lemma.strip() or token.sentence_id not in sentence_ids for token in reading.tokens):
        raise GenerationValidationError("Reading tokens must have unique IDs and valid sentences")
    prompts, question_ids = set(), set()
    for question in reading.questions:
        option_ids = {option.id for option in question.options}
        if (
            not question.id.strip()
            or question.id in question_ids
            or not question.prompt.strip()
            or question.prompt in prompts
            or len(question.options) < 2
            or len(option_ids) != len(question.options)
            or any(not option.id.strip() or not option.text.strip() for option in question.options)
            or question.correct_option_id not in option_ids
            or not question.evidence_sentence_ids
            or not set(question.evidence_sentence_ids) <= sentence_ids
            or not question.explanation.strip()
            or not question.english_translation.strip()
            or not question.english_explanation.strip()
        ):
            raise GenerationValidationError("Invalid question structure")
        question_ids.add(question.id)
        prompts.add(question.prompt)
    return reading


def shuffle_question_options(reading: GeneratedReading) -> GeneratedReading:
    for question in reading.questions:
        option_randomizer.shuffle(question.options)
    return reading
