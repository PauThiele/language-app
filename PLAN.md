# Korean Graded Reader — Implementation Plan

## Purpose and rules

This is the durable roadmap for continuing without Codex session history.

- The product is an **Android-first Korean graded-reading app** backed by FastAPI.
- The backend owns learner modeling, generated-reading validation, vocabulary imports, dictionary enrichment, and offline-event synchronization.
- Android is offline-safe: Room stores reader data, dictionary entries, learner state, annotations, and unsent events; DataStore stores the answer-time preference.
- Database changes are migration-led. Do not create tables at runtime; use Alembic migrations.
- Keep `PROGRESS.md` as the live current-status tracker. Update this document only for durable roadmap or acceptance-criteria changes.
- Do not infer additional product scope from this document. Requirements not represented by the current project specification/contracts require a product decision.

## Existing technical contract

- **Backend:** FastAPI, SQLAlchemy, Alembic; SQLite is the development default and PostgreSQL uses `DATABASE_URL`. JWT access/refresh tokens are persisted and refresh tokens are revocable. Production rejects the default JWT secret. Generation is server-side and provider-agnostic; its URL and token must be configured together.
- **Android:** Kotlin, Jetpack Compose, Room, DataStore, Retrofit/OkHttp, and WorkManager. `ReaderApi` covers generation, dictionary lookup, and event synchronization; an OkHttp interceptor provides authentication.
- **Readings:** A title, text/content, and comprehension questions. Questions contain options, a correct option, evidence sentence IDs, explanations, and, where supplied, target lemmas and grammar.
- **Dictionary/learning:** Dictionary entries have lemma, gloss, optional part of speech, forms, and source. Learner-specific encounters/lookups are tracked. Events cover lookups, encounters, and answers, including time, optional lemma/provider/target lemmas, correctness, and `lookup_before_answer`.
- **Persistence rules:** Vocabulary imports retain filename, delimiter, column mapping, and imported/updated/skipped counts. Annotations are unique per user/reading/token. Pending events are removed only after successful upload; failures increment attempts and retry. Daily generation quotas reset by date and are backend-enforced.

## Phase roadmap

### Phase 0 — Product and technical design **(complete)**

**Goal:** Establish the client/server architecture and product boundaries.

**Requirements and acceptance criteria**

- Define the Android-first Korean graded-reader scope and the backend ownership boundaries above.
- Select the established persistence/client stack: SQLAlchemy/Alembic, Room, DataStore, Retrofit/OkHttp, and WorkManager.
- Define core persisted concepts and network contracts for users, readings, vocabulary, dictionary data, learner state, annotations, and events.
- Establish migration-led schema ownership and offline-safe local Android storage as architectural constraints.

**Exit evidence:** Phase 1 implements the architecture and contract decisions.

### Phase 1 — Project Foundation **(complete; commit `3f77355`)**

**Goal:** Create runnable Android and backend foundations with initial models, contracts, and a reader proof of concept.

**Requirements and acceptance criteria**

- Android and FastAPI project structures exist.
- Initial SQLAlchemy models, Pydantic schemas, Room entities, DataStore settings repository, Retrofit contract, WorkManager sync scaffold, and Compose reader proof of concept exist.
- Alembic owns the initial schema and application startup does not create tables.
- Runtime settings validate production secrets and provider configuration.
- Providers are injectable in tests; configured providers make authenticated, timed requests.
- Backend service tests exist; pytest, syntax compilation, migration upgrade, and FastAPI health validation pass for the foundation.

**Exit evidence:** Completed in `3f77355`; see `PROGRESS.md` for recorded environment validation and limitations.

### Phase 2 — Android integration and core reader workflow **(next)**

**Goal:** Connect Android screens and proof-of-concept state to repositories, Room, and the API.

**Requirements and acceptance criteria**

- Replace hard-coded reader state with repository-backed UI state.
- Wire generation, persisted readings, questions, and explanations through the existing API and Room contracts.
- Configure the network stack used by `ReaderApi`, including base URL and the auth-interceptor integration point.
- Keep locally saved reader content available without a connection.
- Provide explicit loading, unavailable-generation, retry, and error behavior.

**Exit criteria:** A user can request a reading, read a persisted result, answer questions, and view explanations; UI data comes from repositories rather than hard-coded view-model samples.

### Phase 3 — Authentication and account session lifecycle

**Goal:** Complete the existing JWT access/refresh-token account model.

**Requirements and acceptance criteria**

- Provide registration and sign-in using the existing user model and password hashing.
- Issue access/refresh pairs, persist refresh-token records, and revoke them.
- Persist the authenticated client session safely and attach access tokens to protected Android API requests.
- Refresh expired access tokens when possible; otherwise return to authentication.
- Retain production-secret validation and never place provider/backend secrets in the Android app.

**Exit criteria:** A user can register/sign in, retain a valid session across restarts, call protected endpoints, refresh an expired access token, and sign out so its refresh session is unusable.

### Phase 4 — Vocabulary management and Anki import

**Goal:** Make vocabulary usable, including the specified import audit trail.

**Requirements and acceptance criteria**

- Provide authenticated vocabulary creation, retrieval, and update using normalized terms, optional meanings, and tags.
- Enforce the unique-per-user vocabulary-term rule.
- Accept the intended Anki-delimited input and apply its column mapping.
- Record filename, delimiter, column mapping, and imported/updated/skipped counts for every import.
- Make imported vocabulary available to the generation and learner-model workflows and Android client.

**Exit criteria:** A user can import supported vocabulary, receive an accurate summary, avoid duplicates, and use the resulting vocabulary in the app.

### Phase 5 — Dictionary enrichment and reader annotations

**Goal:** Deliver in-reader word help using dictionary, learner-state, and annotation contracts.

**Requirements and acceptance criteria**

- Resolve a selected token to a normalized lemma and dictionary entry.
- Return/cache lemma, gloss, part of speech, forms, and source.
- Surface learner-specific encounter and lookup information where supplied.
- Persist lookup effects in learner state and queue the corresponding event offline.
- Create, update, and retrieve annotations while preserving the user/reading/token uniqueness rule.

**Exit criteria:** A reader can select a word, view dictionary data, record an offline-safe lookup, and persist a token annotation without duplicates.

### Phase 6 — Reading generation, validation, and quotas

**Goal:** Complete controlled backend generation and expose its existing request controls.

**Requirements and acceptance criteria**

- Generate readings from genre, length, new-word intensity, and grammar intensity.
- Use the configured server-side provider only; keep the injectable provider abstraction and explicit unavailable result when not configured.
- Validate generated content before accepting it, including question structure, answers, evidence sentence IDs, and explanations.
- Preserve target lemma/grammar data where generated questions provide it.
- Enforce each user's daily generation quota and date-based reset.

**Exit criteria:** A valid provider response becomes a persisted, validated reading. Invalid, unavailable, and over-quota requests fail explicitly and do not create a misleading successful reading.

### Phase 7 — Learning-event ingestion and learner modeling

**Goal:** Turn reader activity into the backend-owned learner model.

**Requirements and acceptance criteria**

- Accept authenticated batches of uniquely identified learning events.
- Process lookup, encounter, and answer events with their established fields, including correctness and lookup-before-answer context.
- Update learner word-state encounters, lookups, correct/incorrect answers, and confidence.
- Make ingestion idempotent so offline retries do not double-count activity.
- Keep learner state isolated by user and lemma.

**Exit criteria:** Replaying a successful event batch does not change state; distinct activity updates only the correct user's word state.

### Phase 8 — Offline-first synchronization

**Goal:** Complete the durable local event queue and sync behavior.

**Requirements and acceptance criteria**

- Queue reader activity as durable pending events without a network connection.
- Schedule WorkManager sync using the existing batch contract.
- Upload batches, remove only accepted events, and retain failed events for retry while incrementing attempt counts.
- Reconcile local dictionary/learner-state data after successful backend responses without discarding saved readings or annotations.
- Run the sync path with the Phase 3 authenticated client.

**Exit criteria:** Offline activity survives restart, syncs after connectivity returns, does not duplicate learner-model changes, and is deleted from Room only after success.

### Phase 9 — Settings and learning-flow completion

**Goal:** Integrate the existing answer-time preference and finish reader interactions that produce learning signals.

**Requirements and acceptance criteria**

- Surface and persist the existing `use_answer_time` DataStore preference.
- Apply it consistently to answer interactions and event data supported by the contract.
- Record whether a lookup happened before an answer.
- Display stored explanations and target vocabulary/grammar information supplied by generation.
- Keep settings and learning actions usable for locally stored content.

**Exit criteria:** The answer-time setting persists across launches and the completed reader flow records answer/lookup context accurately for later sync.

### Phase 10 — Quality, security, and operational verification

**Goal:** Make completed workflows dependable and safe to operate.

**Requirements and acceptance criteria**

- Add focused coverage for sessions, imports, dictionary/annotation rules, generation validation/quotas, event idempotency, and sync retries.
- Validate Android-facing API contracts, including UI-handled failures.
- Exercise Alembic upgrades from a clean database; migrations remain the only schema-creation mechanism.
- Verify production rejects unsafe default secrets and incomplete provider configuration.
- Verify the primary reader flow online and with cached content plus deferred events.

**Exit criteria:** Targeted automated tests and clean migration checks pass, and primary flows have explicit success and failure behavior.

### Phase 11 — Release readiness and handoff

**Goal:** Make deployment and continued maintenance repeatable without session-only knowledge.

**Requirements and acceptance criteria**

- Document backend setup, required environment variables, migration execution, and PostgreSQL deployment configuration.
- Document Android build/setup requirements, required SDK tooling, and backend-base-URL configuration.
- Ensure production builds contain no runtime table creation, development JWT secret, provider token, or other backend secret.
- Maintain known operational limits and unresolved issues in `PROGRESS.md`.
- Leave `PLAN.md`, `README.md`, migrations, tests, and configuration examples sufficient for another agent to continue and verify the system.

**Exit criteria:** A new maintainer can configure the backend, apply migrations, build Android, identify required settings, and continue the roadmap from repository-local documentation.

## Sequencing and handoff

1. Phase 2 makes the foundation's Android contracts real in the UI.
2. Phase 3 provides the authenticated session for protected user data.
3. Phases 4–6 add vocabulary, dictionary/annotations, and validated reading generation.
4. Phases 7–9 complete learner updates, offline synchronization, and settings-driven reader behavior.
5. Phases 10–11 verify and document the assembled system.

The current phase and next action are maintained in `PROGRESS.md`, not in this document.
