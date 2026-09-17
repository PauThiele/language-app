# Project Progress

## Current phase

**Phase 11 — Release readiness and handoff (complete)**

## Completed work

- Initial Android and FastAPI project structures exist.
- Initial database models, API contracts, Room entities, DataStore preference repository, and a Compose reader proof of concept exist.
- A basic backend service test file exists.
- Backend schema ownership is migration-led through Alembic; runtime configuration validates production secrets and provider settings, and generation providers are injectable for tests.
- The backend runs in `backend/.venv` on the bundled Python 3.12.13 runtime; `pytest -q -p no:cacheprovider` (5 passed), syntax compilation, Alembic upgrade, and FastAPI health validation pass.
- Phase 2 replaces the hard-coded Android reader sample with a repository-backed `ReaderViewModel`, Room-persisted generated-reading payloads, and Compose states for loading, errors, retry, saved content, questions, and explanations.
- The Android Retrofit client now uses `BuildConfig.BACKEND_BASE_URL` and a reusable `AuthInterceptor`/`AccessTokenProvider` integration point for Phase 3 token persistence.
- Generated readings are saved to Room immediately after a successful API response; a Room 2-to-3 migration adds durable full-reading payload storage so saved content remains readable offline.
- Generation failures explicitly distinguish offline, authentication-required, quota, unavailable-provider, and other server failures.
- The Android project includes a Gradle 8.12 wrapper, uses aligned Java/Kotlin JVM 21 targets, and builds successfully with `gradlew.bat --no-daemon :app:assembleDebug --offline` on September 1, 2026.
- Phase 3 adds backend registration, login, refresh-token rotation, and logout revocation using the existing password hashing and persisted refresh-token records.
- Android now provides registration and sign-in UI, encrypts persisted access/refresh tokens with an Android Keystore AES-GCM key, disables backups for that session data, and attaches the access token to protected API requests.
- The authenticated OkHttp client refreshes invalid access tokens once with the persisted refresh token; failed or revoked refreshes clear the session and return the user to authentication.
- Backend auth lifecycle coverage verifies registration, login, protected-token acceptance, refresh rotation, and logout revocation. On September 1, 2026, `pytest -q -p no:cacheprovider` (7 passed), Alembic upgrade, backend syntax compilation, and `:app:assembleDebug --offline` all pass.
- Phase 4 adds authenticated vocabulary retrieval, creation, and updates, with uniqueness enforced per user on NFC-normalized, case-folded terms rather than raw spelling.
- Anki-delimited imports now validate the selected column names, retain the source filename and mapping audit data, update normalized duplicates, create learner-word state for imported terms, and report imported/updated/skipped totals.
- Android now caches vocabulary in Room and provides add/edit vocabulary plus a document-picker Anki import flow with previewed, editable term/meaning/tag column mappings and an import summary.
- On September 1, 2026, backend validation passes with `pytest -q -p no:cacheprovider` (9 passed), Alembic upgrade through `0002_normalize_vocabulary_unique`, and syntax compilation; Android `:app:assembleDebug --offline` also passes.
- Phase 5 adds authenticated dictionary lookup responses with NFC-normalized lemmas, cached dictionary details, and learner-specific encounter and lookup counts.
- Android reader tokens now open a dictionary dialog; successful lookups are cached in Room, update local lookup state, and enqueue uniquely identified lookup events so activity is retained while offline.
- Token annotations are stored locally by the reading/token key and are also backed by authenticated annotation list and upsert endpoints. The backend preserves one annotation per user, reading, and token while allowing note updates.
- On September 1, 2026, Phase 5 validation passes with `pytest -q -p no:cacheprovider` (11 passed), backend syntax compilation, Alembic upgrade, and `:app:assembleDebug --offline`.
- Phase 6 exposes genre, length, new-word intensity, and grammar intensity in the Android reader and sends these controls through the existing generation API request.
- Configured generation providers now distinguish unavailable transport/provider failures from malformed generated content, and generated readings receive structural validation before persistence.
- Validation now requires meaningful reading text, unique and well-formed sentences/tokens/questions/options, valid correct answers and evidence references, and non-empty explanations while preserving supplied target lemmas and grammar.
- Generation resets a user’s quota count when the quota date changes, rejects over-quota requests before provider work, and persists only a valid generated reading.
- On September 1, 2026, Phase 6 validation passes with `pytest -q -p no:cacheprovider` (20 passed), backend syntax compilation, Alembic upgrade, and `:app:assembleDebug --offline`.
- Phase 7 accepts authenticated learning-event batches with UUID event IDs and processes lookup, encounter, and question-answer activity without crossing user boundaries.
- Backend event ingestion now tracks encounter, lookup, correct/incorrect answer, and lookup-before-answer effects in each user’s NFC-normalized learner-word state; duplicate event IDs in a retried batch do not reapply changes.
- Opening a generated or saved Android reading now queues reading-opened and per-token encounter events, while the first response to each question queues answer context and successful dictionary lookups mark the relevant lemma as looked up.
- Android learning-event payloads now preserve reading and sentence identifiers in addition to lemma, correctness, target lemmas, and lookup-before-answer context.
- On September 1, 2026, Phase 7 validation passes with `pytest -q -p no:cacheprovider` (21 passed), backend syntax compilation, Alembic upgrade, and `:app:assembleDebug --offline`.
- Phase 8 completes the authenticated WorkManager event-sync path: pending Room events survive offline use, drain in 100-event batches after connectivity returns, and are removed only after the backend accepts or identifies them as idempotent duplicates.
- Failed sync or reconciliation runs retain the attempted events, increment only those events' retry counts, and use WorkManager exponential backoff; signed-out runs retain the queue without spinning retries, and successful sign-in schedules a new sync.
- After each accepted batch, Android refreshes learner-word state and best-effort dictionary cache entries without touching saved readings or annotations.
- On September 1, 2026, Phase 8 validation passes with `pytest -q -p no:cacheprovider` (21 passed), backend syntax compilation, Alembic upgrade, and `:app:assembleDebug --offline`.
- Phase 9 surfaces the persisted `use_answer_time` DataStore setting in the reader. When enabled, the app measures and displays elapsed time for each first comprehension response; disabling it leaves answer behavior and queued event data unchanged because the current API contract has no answer-duration field.
- The reader locks each question after its first answer, queues the existing correctness and lookup-before-answer context, and displays generated explanations plus reading- and question-level target vocabulary and grammar for generated and locally saved readings.
- On September 1, 2026, Phase 9 validation passes with `pytest -q -p no:cacheprovider` (21 passed), backend syntax compilation, Alembic upgrade, and `:app:assembleDebug --offline`.
- Phase 10 adds an authenticated FastAPI contract test covering the token response, generated-reading fields consumed by Android, dictionary response fields, unauthenticated failure, and replay of a deferred learning event without duplicate learner changes.
- Runtime configuration coverage now explicitly rejects a production deployment using the development JWT secret and either incomplete generation-provider setting; existing focused tests cover sessions, imports, dictionary/annotation uniqueness, generation validation and quotas, and learning-event idempotency.
- On September 1, 2026, Phase 10 verification passes with `pytest -q -p no:cacheprovider` (23 passed), backend syntax compilation, an Alembic upgrade from a newly created SQLite database with the expected schema, and `:app:assembleDebug --offline`.
- Phase 11 documents local and PostgreSQL backend setup, production environment configuration, migration ordering, TLS and secret-handling expectations, Android SDK/build requirements, backend URL configuration, release signing guidance, and maintenance handoff procedures in `README.md`.
- Android release configuration now rejects a non-HTTPS `BACKEND_BASE_URL`, preventing the committed emulator HTTP default from being packaged in a release artifact.
- On September 1, 2026, Phase 11 validation passes with `pytest -q -p no:cacheprovider` (23 passed), backend syntax compilation, Alembic upgrade, `:app:assembleDebug --offline`, an expected failure for a release build using the HTTP default URL, and a successful HTTPS-configured release APK package. The complete offline release lint chain cannot run because `com.android.tools.lint:lint-gradle:31.9.2` is absent from the local Gradle cache; the release package validation excluded only `lintVitalAnalyzeRelease`, `lintVitalReportRelease`, and `lintVitalRelease`.

## Known issues

- The existing generator is a deterministic scaffold, not a configured production LLM provider.
- Upload handling and full test coverage are incomplete.

## Next task

All currently planned phases are complete. Address known issues or record the next product-approved phase in `PLAN.md` before further implementation.

## Final verification — September 1, 2026

### Verified automatically

- Backend: `pytest -q -p no:cacheprovider` passes with 23 tests; Python compilation, the FastAPI `/health` response, and the normal database migration upgrade pass.
- Fresh-database migration: Alembic upgrades a newly created SQLite database through `0002_normalize_vocabulary_unique`; the resulting tables match SQLAlchemy metadata plus `alembic_version`.
- Android: `:app:assembleDebug --offline`, `:app:testDebugUnitTest --offline`, and network-enabled `:app:lint` pass. The unit-test task has no Android unit-test sources.
- Release packaging: `:app:preReleaseBuild --offline` fails as expected when the default `http://10.0.2.2:8000/` URL is used. `:app:assembleRelease --offline -PBACKEND_BASE_URL=https://api.example/` passes, including `lintVitalAnalyzeRelease`, `lintVitalReportRelease`, and `lintVitalRelease`.
- Release configuration audit: generated release `BuildConfig` contains the supplied HTTPS backend URL only; cleartext traffic is declared only in the debug manifest; Android source contains no backend database, JWT, or generation-provider configuration values. The built artifact is `android/app/build/outputs/apk/release/app-release-unsigned.apk` and is intentionally unsigned because no release signing credentials are stored in the repository.

### Verified manually

- None in this QA run. No emulator or physical Android device was used.

### Requires deployment or external infrastructure

- Provide a production PostgreSQL database, a unique production `JWT_SECRET`, and paired generation-provider URL/token values through the deployment secret store; run Alembic migrations there before rollout.
- Configure secure release signing and produce a signed APK or Android App Bundle in CI; validate the signed artifact and its distribution channel.
- Exercise the deployed HTTPS API, real generation provider, authentication lifecycle, database backup/restore, and observability/operational procedures.

### Known limitations

- The deterministic generator remains a development scaffold until a production generation provider is configured and accepted.
- Android automated unit coverage is absent, and no emulator/physical-device, offline/reconnect, background WorkManager, or UI accessibility testing has been performed.
- The repository had pre-existing working-tree changes when this verification began; this QA pass intentionally made no product-code changes. `git diff --check` reports an existing trailing blank line in `android/app/src/main/java/com/gradedreader/korean/learning/EventSyncWorker.kt`.