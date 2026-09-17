# Korean Graded Reader

Korean Graded Reader is an Android-first, AI-assisted language-learning project for learners who want reading material that can be connected to their vocabulary and learning activity. It combines a Kotlin/Jetpack Compose client with a FastAPI backend to generate, store, annotate, and revisit Korean graded readings.

The project is designed as a full-stack mobile application: it demonstrates Android UI and offline data handling, a typed Python API, authentication, relational persistence and migrations, and an optional integration boundary for AI-assisted content generation. It is an independent project and should not be treated as a production-ready language-learning service.

## Features

- **Graded reading workflow** — request Korean readings with controls for genre, length, vocabulary and grammar intensity; read saved content and review comprehension questions, explanations, and English translations.
- **Vocabulary-aware learning** — create, update, and list personal vocabulary; use saved meanings during word lookup; and import UTF-8 CSV or TSV exports, including Anki-style exports with mapped columns.
- **Dictionary lookups and notes** — tap reading tokens for cached or backend dictionary entries, English translations when available, grammar details, and per-token annotations.
- **Authenticated learner data** — register, log in, refresh and revoke sessions through JWT-based API endpoints; the Android client stores its session locally using Android Keystore-backed encryption.
- **Offline-aware Android client** — cache readings, dictionary entries, vocabulary, learner state, annotations, and pending learning events in Room; queue activity for WorkManager-based synchronization when connectivity is available.
- **Learner-state signals** — send lookup, encounter, and question-answer events to the backend, where learner word state is persisted and updated.

## Screenshots

### Vocabulary

<img src="Vocab.png" alt="Vocabulary screen" width="320">

### Reader

<img src="Generation.png" alt="Reader screen" width="320">

### Comprehension check

<img src="Comprehension.png" alt="Comprehension check screen" width="320">

## Architecture

| Layer | Implementation | Responsibility |
| --- | --- | --- |
| Android app | Kotlin, Jetpack Compose, Navigation, Retrofit | Reader UI, vocabulary import, settings, authenticated API access, and local interaction flows. |
| On-device storage | Room, DataStore, WorkManager | Caches reading-related data, stores preferences, and queues/synchronizes learning events. |
| API | Python 3.12+, FastAPI, Pydantic | Auth, vocabulary and import endpoints, readings, dictionary lookups, annotations, learner state, and event ingestion. |
| Server persistence | SQLAlchemy, Alembic | Stores users, refresh tokens, vocabulary, imports, readings, dictionary cache, learner state, annotations, and learning events. |
| External services | Optional OpenAI-compatible generation provider and Korean Basic Dictionary API | Kept behind server-side provider adapters; credentials are not included in the Android build. |

The development database defaults to SQLite. PostgreSQL is supported through `DATABASE_URL`, and schema changes are applied with Alembic migrations rather than at application startup.

## AI component and limitations

The backend exposes a reading-generation endpoint and validates returned content against the application's `GeneratedReading` schema before storing it. It has adapters for an OpenAI-compatible Responses API (including the documented KI:connect configuration) and for a custom compatible generation endpoint. Requests include the selected reading controls and the learner's known terms.

A real provider is **optional**: without a server-side provider configuration, the generation endpoint reports a setup error rather than returning a generated reading. `OPENAI_API_KEY`, or the custom provider URL and token, must be supplied only on the backend. The codebase also contains a deterministic `StubGenerationProvider` for tests and development validation; it is not a live LLM integration.

This repository does not establish production LLM operations. Provider credentials, model availability, output quality, safety controls, evaluation, monitoring, rate limits, privacy review, and operational deployment remain the responsibility of a deployer. Generated content is schema-validated, but that is not a guarantee of linguistic accuracy or pedagogical suitability.

## Repository layout

- `backend/` — FastAPI application, SQLAlchemy models, Alembic migrations, and pytest suite.
- `android/` — Kotlin/Jetpack Compose Android app, Room database, WorkManager sync, and Retrofit API client.
- `PLAN.md` — roadmap and scope notes.
- `PROGRESS.md` — implementation progress, validation evidence, and documented limitations.

## Quick start

### Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

The API never creates database tables at startup. Apply Alembic migrations before starting each environment, including local development and deployments. The development default is SQLite; set `DATABASE_URL` to PostgreSQL before deployment.

Copy `backend/.env.example` to `backend/.env` only for local development. The file is Git-ignored; do not reuse its development JWT secret in a deployment.

### Android

Install JDK 21, Android SDK Platform 36, and Android Build Tools 36.0.0. Point `android/local.properties` at that SDK (the file is ignored by Git), then build from `android/`:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug --offline
```

`BACKEND_BASE_URL` is a Gradle property and must end with `/`. Debug builds default to `http://10.0.2.2:8000/`, which reaches a backend running on the development machine from the Android emulator. Override it for another backend:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug -PBACKEND_BASE_URL=https://api.example/
```

For a physical phone on the same Wi-Fi network as the development machine, build with the machine's LAN address, for example:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug -PBACKEND_BASE_URL=http://<your-computer-lan-ip>:8000/
```

The `-PBACKEND_BASE_URL` override applies only to that build. Reuse it whenever rebuilding for a physical phone, and ensure the backend listens on `0.0.0.0:8000` and the Windows firewall permits the connection. Release builds require an explicitly supplied HTTPS `BACKEND_BASE_URL`; the Gradle build fails if the emulator HTTP default is retained.

## Configuration

### Backend configuration

- `ENVIRONMENT` — `development` (default), `test`, or `production`. Production rejects the default development JWT secret.
- `DATABASE_URL` — SQLAlchemy database connection URL.
- `JWT_SECRET` — required non-default signing secret in production.
- `OPENAI_API_KEY` — optional server-side key for OpenAI-compatible reading generation. When set, this takes precedence over a custom provider.
- `MODEL_PROVIDER` and `BASE_URL` — select an OpenAI-compatible API. Use `MODEL_PROVIDER=kiconnect` with `BASE_URL=https://chat.kiconnect.nrw/api/v1` for KI:connect. `KICONNECT_API_KEY` is accepted as an alias for `OPENAI_API_KEY`.
- `GENERATION_PROVIDER_URL` and `GENERATION_PROVIDER_TOKEN` — optional settings for a compatible custom generation provider; configure both or neither.
- `GENERATION_DEFAULT_MODEL` — fallback model identifier used when the client does not select one; defaults to `GPT5-mini-Studierende`.
- `GENERATION_TIMEOUT_SECONDS` — provider request timeout in seconds; defaults to `120`.
- `KOREAN_DICTIONARY_API_KEY` — optional National Institute of Korean Language Korean Basic Dictionary API key, used server-side when a word is not in the signed-in user's saved vocabulary.
- `KOREAN_DICTIONARY_URL` — dictionary endpoint; defaults to `https://krdict.korean.go.kr/api/search`.
- `DICTIONARY_TIMEOUT_SECONDS` — dictionary request timeout in seconds; defaults to `20`.

For KI:connect, configure the backend `.env` as follows, then restart the backend:

```dotenv
MODEL_PROVIDER=kiconnect
BASE_URL=https://chat.kiconnect.nrw/api/v1
KICONNECT_API_KEY=replace-with-your-kiconnect-api-key
GENERATION_DEFAULT_MODEL=GPT5-mini-Studierende
```

Set `OPENAI_API_KEY` to use the default OpenAI endpoint, or set both custom-provider variables to call an app-specific generation endpoint. If neither is configured, generation returns a clear setup error. The Android settings screen can save a model identifier for generation requests; it is not an API key and does not grant access to provider credentials.

The dictionary endpoint returns a signed-in user's saved vocabulary meaning first. Otherwise, it reads a cached Korean Basic Dictionary entry or fetches one through the backend-only dictionary key. Dictionary responses include a Korean definition and, when available, an English translation.

### Vocabulary import

The Android importer accepts UTF-8, header-row CSV and TSV text files. In Anki, export notes as plain text with fields separated by commas or tabs, then map the term, meaning, and optional tags columns in the app. `.apkg` deck packages and `.colpkg` collection packages are not supported directly.

## Deployment

For local PostgreSQL development, start the supplied database container from the repository root:

```powershell
docker compose up -d database
```

Configure the backend with a PostgreSQL URL and production-only secrets, then apply migrations before starting Uvicorn:

```powershell
cd backend
$env:ENVIRONMENT = "production"
$env:DATABASE_URL = "postgresql+psycopg://graded_reader:replace-with-a-password@db.example/graded_reader"
$env:JWT_SECRET = "replace-with-a-long-random-secret"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Use HTTPS when exposing the API outside a development network. The supplied Compose PostgreSQL password is development-only; replace it with managed secrets and a production database before relying on it for learner data. Back up the database and test restoring it before deployment.

## Verification

Run the backend checks from `backend/` and the Android build from `android/`:

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.venv\Scripts\python.exe -m compileall -q app
.venv\Scripts\python.exe -m alembic upgrade head
.\gradlew.bat --no-daemon :app:assembleDebug --offline
```

After changing server models, create and review an Alembic migration and test it against a new database. See `PLAN.md` and `PROGRESS.md` for the project's planned work, completed phases, validation evidence, and known limits.
