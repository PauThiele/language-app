# Korean Graded Reader

An Android-first Korean graded-reading app with a FastAPI backend. The backend owns learner modeling, generated-reading validation, vocabulary imports, dictionary enrichment, and offline-safe learning-event synchronization.

## Layout

- `backend/` — FastAPI API, SQLAlchemy models, and pytest suite.
- `android/` — Kotlin/Jetpack Compose Android client with Room-backed offline data.

## Backend quick start

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

## Backend configuration

- `ENVIRONMENT` — `development` (default), `test`, or `production`. Production rejects the default development JWT secret.
- `DATABASE_URL` — SQLAlchemy database connection URL.
- `JWT_SECRET` — required non-default signing secret in production.
- `OPENAI_API_KEY` — optional server-side key for OpenAI-compatible reading generation. When set, this takes precedence over a custom provider.
- `MODEL_PROVIDER` and `BASE_URL` — select an OpenAI-compatible API. Use `MODEL_PROVIDER=kiconnect` with `BASE_URL=https://chat.kiconnect.nrw/api/v1` for KI:connect. `KICONNECT_API_KEY` is accepted as an alias for `OPENAI_API_KEY`.
- `GENERATION_PROVIDER_URL` and `GENERATION_PROVIDER_TOKEN` — optional server-side settings for a compatible custom generation provider; configure both or neither.
- `GENERATION_TIMEOUT_SECONDS` — provider request timeout in seconds; defaults to `120`.
- `KOREAN_DICTIONARY_API_KEY` — optional National Institute of Korean Language Korean Basic Dictionary API key. The server uses it only when a word is not in the signed-in user's saved vocabulary.
- `KOREAN_DICTIONARY_URL` — Dictionary endpoint; defaults to `https://krdict.korean.go.kr/api/search`.
- `DICTIONARY_TIMEOUT_SECONDS` — dictionary request timeout in seconds; defaults to `20`.

The app's generation endpoint supports OpenAI-compatible Responses APIs or a compatible custom provider. For KI:connect, configure the backend `.env` as follows, then restart the backend:

```dotenv
MODEL_PROVIDER=kiconnect
BASE_URL=https://chat.kiconnect.nrw/api/v1
KICONNECT_API_KEY=replace-with-your-kiconnect-api-key
GENERATION_DEFAULT_MODEL=GPT5-mini-Studierende
```

Set `OPENAI_API_KEY` to use the default OpenAI endpoint, or set both custom-provider variables to call an app-specific generation endpoint. If neither is configured, generation returns a clear setup error instead of silently showing a sample reading.

The dictionary endpoint returns the signed-in user's saved vocabulary meaning first. When a word is not in that vocabulary, it reads a cached National Institute of Korean Language dictionary entry or fetches one using the backend-only dictionary API key. Each dictionary response includes the Korean definition and, when available, an English translation. The API key is never included in the Android build. Older AI-generated or Korean-only cache entries are refreshed with the normal dictionary source on their next lookup.

## PostgreSQL deployment

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
$env:GENERATION_PROVIDER_URL = "https://provider.example/readings"
$env:GENERATION_PROVIDER_TOKEN = "replace-with-a-provider-secret"
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Set the provider URL and token together, or leave both unset. Do not commit a production `.env`, database password, JWT secret, or provider token. Production startup rejects the documented development JWT secret; use HTTPS when exposing the API outside a development network.

### Deployment order

1. Provision PostgreSQL and create a dedicated database user with only the permissions required by the application and Alembic migrations.
2. Supply `ENVIRONMENT=production`, a PostgreSQL `DATABASE_URL`, and a unique `JWT_SECRET` through the deployment platform's secret store.
3. Set `GENERATION_PROVIDER_URL` and `GENERATION_PROVIDER_TOKEN` together only when a real generation provider is ready. They are server-side secrets and must never be sent to Android.
4. Run `python -m alembic upgrade head` as a release step before starting or rolling out the API. Never rely on application startup to create or upgrade tables.
5. Start the API behind TLS and a process manager or platform service. Run the verification commands below against the release candidate before promoting it.

The supplied Compose PostgreSQL password is development-only. Replace it with managed secrets and a production database before deployment. Back up the database and test restoring it before relying on it for learner data.

## Android setup and build

Install JDK 21, Android SDK Platform 36, and Android Build Tools 36.0.0. Point `android/local.properties` at that SDK (the file is ignored by Git), then build from `android/`:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug --offline
```

The Gradle wrapper uses `android/.gradle-user-home/` by default. This keeps this project's Gradle cache separate from the machine-wide cache and avoids cache-lock conflicts with other builds. The local cache is ignored by Git; set `GRADLE_USER_HOME` explicitly when CI or another environment should use a different cache location. The first build for a new local cache must run without `--offline` so Gradle can populate it.

`BACKEND_BASE_URL` is a Gradle property and must end with `/`. Debug builds default to `http://10.0.2.2:8000/`, which reaches a backend running on the development machine from the Android emulator. Override it for another backend:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug -PBACKEND_BASE_URL=https://api.example/
```

Use an HTTPS URL for release builds. Debug-only cleartext support is intentionally limited to the development manifest; physical devices need a reachable host address rather than `10.0.2.2`.

For a physical phone on the same Wi-Fi network as the development machine, build with the machine's LAN address, for example:

```powershell
.\gradlew.bat --no-daemon :app:assembleDebug -PBACKEND_BASE_URL=http://<your-computer-lan-ip>:8000/
```

The `-PBACKEND_BASE_URL` override applies only to that build. Reuse it whenever rebuilding for a physical phone, and ensure the backend listens on `0.0.0.0:8000` and the Windows firewall permits the connection.

The app's **Settings** screen includes a Generation model field. Its saved value is sent with every generation request; leave it blank to use the backend default, `GPT5-mini-Studierende`. Override it with `GENERATION_DEFAULT_MODEL` in the backend environment when deploying to a provider with a different model identifier. The selected model is not an API key and does not grant the app access to provider credentials.

### Vocabulary import

The Android importer accepts UTF-8, header-row CSV and TSV text files. In Anki, export notes as plain text with fields separated by commas or tabs, then map the term, meaning, and optional tags columns in the app. `.apkg` deck packages and `.colpkg` collection packages are not supported directly.

Release builds require an explicitly supplied HTTPS `BACKEND_BASE_URL`; the Gradle build fails if the emulator HTTP default is retained. Configure release signing credentials through your secure CI or local Gradle user configuration, not in this repository. The Android app contains no backend database, JWT, or generation-provider secrets.

## Verification and handoff

Run the backend checks from `backend/` and the Android build from `android/`:

```powershell
.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
.venv\Scripts\python.exe -m compileall -q app
.venv\Scripts\python.exe -m alembic upgrade head
.\gradlew.bat --no-daemon :app:assembleDebug --offline
```

`PLAN.md` is the durable roadmap and `PROGRESS.md` records completed phases, validation evidence, and known limits. The deterministic generation provider remains a development scaffold; configure a real provider before release. After changing models, create and review an Alembic migration, test it against a new database, then record the maintenance result in `PROGRESS.md`.
