# Project Issues: Meaning, Impact, and Recommended Fixes

This guide explains the reported issues in the policy chatbot, why they matter,
and how to address them. The retrieval issues are related: a stale Chroma index
causes inferred metadata filters to exclude vector results, while the filters
are too strict even when the index is healthy.

## At a glance

| Priority | Issue | Main risk |
|---|---|---|
| P0 | Stale Chroma index is not repaired on startup | Hybrid retrieval runs with missing chunk and parent metadata |
| P0 | Inferred metadata is used as a hard filter | Relevant policy passages disappear from search results |
| P1 | Deployment files and environment-file paths disagree | Compose may fail before the services start |
| P1 | Conversation APIs have no authentication | A caller can access or delete history if they know its ID |
| P2 | `RELEVANCE_THRESHOLD` is not configured or applied | Changing the environment value has no effect |
| P2 | “Confidence” is a reranker score | Clients may present an uncalibrated ranking value as probability |
| P2 | Sources include all retrieved passages | The response can list sources that were not cited |
| P2 | Tests use the default persistent memory database | Test runs can write to or contaminate project data |

## 1. Stale Chroma index and startup rebuild

### What it means

The current index is reported to contain 54 chunks without the metadata used by
hybrid retrieval (`parent_id`, `policy_type`, `region`, and `payment_method`),
and its parent-document store is empty. The code already has a repair path:
`KnowledgeBase.ensure_index_current()` checks for required metadata and populated
parent store, then indexes the source documents when either is missing.

The problem is the FastAPI lifespan in `server/api/main.py`: it calls this
method only when `chunk_count` is zero. A nonempty but incomplete index
therefore skips the check that would repair it.

### Impact

The vector index and parent store are out of sync. Even if child chunks are
searchable, the application cannot reliably return their full parent sections.
The chatbot may also keep using stale metadata until the index is explicitly
rebuilt.

### Recommended fix

Call the index validation method on every startup, without first checking
whether the chunk count is zero. Keep the validation inside the method so a
healthy index can be reused and an incomplete one can be rebuilt. After repair,
verify that chunks have the required metadata and that their parent records
exist. Make rebuilds safe to repeat and ensure failures are visible in startup
logs and health reporting rather than presenting a broken index as healthy.

For ongoing reliability, validate the entire collection (or an index/schema
version), not just one chunk: a single well-formed chunk does not prove that
every stored chunk and parent record is current.

### How to verify

- Start with a nonempty index missing required metadata and an empty parent
  store; startup should rebuild it.
- Start again with the repaired index; startup should not create duplicate or
  stale chunks.
- Confirm each indexed child can resolve its parent document.

## 2. Inferred metadata filters suppress vector results

### What it means

`infer_metadata_filters()` recognizes words such as “card”, “dispute”, “refund”,
and “fee”, then `VectorRetriever.search()` passes the inferred values to Chroma
as a `where` filter. BM25 applies corresponding metadata checks as well.

If existing Chroma records do not have a queried field, they cannot satisfy
that Chroma filter. For example, a card question can filter on
`payment_method=card`, even though the stale chunks have no `payment_method`.
Vector search then returns no matches; BM25 may still contribute because it
handles missing metadata differently. This is consistent with the reported
fallback answers, including the refund question, but does not by itself prove
the cause of every fallback.

### Recommended fix

Do not treat keywords in a question as proof that all relevant documents must
have a particular metadata value. Use inferred metadata as a **ranking boost**:

1. Retrieve a broad candidate set from vector search and BM25.
2. Fuse and rerank those candidates as usual.
3. Give a modest, measurable preference to candidates whose metadata matches
   the inferred topic, region, or payment method.
4. Keep candidates with missing or different inferred metadata eligible.

Reserve hard filtering for explicit constraints in the request (for example,
“only show the India policy”), and only when the index has the required
metadata. Treat missing metadata as unknown, not as evidence that a document
is irrelevant.

### How to verify

- A card or refund query should still return semantically relevant documents
  whose metadata is missing.
- Matching metadata should improve ranking without removing otherwise relevant
  results.
- An explicitly constrained query should apply a hard filter only when the
  requested field is available and the user clearly asked for that constraint.

## 3. First-keyword policy-type inference mislabels documents

### What it means

Ingestion assigns one `policy_type` to a document using the first matching
category in a fixed keyword list. The classification examines a limited
portion of the document text. A document can therefore be labelled “disputes”
because it mentions chargebacks, even when its primary purpose is onboarding.
That label is then used by retrieval and can exclude it from an onboarding
question.

### Recommended fix

Prefer reviewed, authoritative document metadata when available (for example,
a curated document manifest). If labels must be inferred, use the filename,
title, headings, and section content as signals; allow ambiguous or mixed
documents to remain unclassified or carry multiple application-level labels.
Do not assign a single category solely because one keyword appeared first.

Regardless of how labels are produced, use inferred policy type as a ranking
signal rather than a mandatory retrieval condition. This makes imperfect
classification less damaging.

### How to verify

Add a test document whose main subject is onboarding but whose text mentions
disputes. An onboarding query should still retrieve it, and its classification
should not be determined by the incidental keyword alone.

## 4. Docker client filename and Compose environment file

### What it means

Docker's `COPY` source paths are relative to the build context. If the client
Dockerfile copies `streamlit_app.py` while the build context contains only
`app.py`, the client image build fails with a missing-file error.

Separately, Compose declares a root `.env` as the server's `env_file`. In this
workspace, the root `.env` is absent; `.env.example` and `server/.env` are
present. Compose's `env_file` does not automatically substitute
`server/.env`, so Compose may fail before starting the server.

### Workspace-specific status

In the inspected workspace, `client/Dockerfile` already copies and runs
`app.py`, so the filename mismatch is not present in that file here. However,
`BACKEND_ARCHITECTURE.md` and `PROJECT_STRUCTURE.md` still refer to
`client/streamlit_app.py`; update those references and confirm the commit or
deployment branch contains the matching `client/app.py` and Dockerfile.

The root `.env` expected by Compose is absent in this workspace, so the
environment-file path still needs to be reconciled.

### Recommended fix

- Keep the client Dockerfile's `COPY` source and Streamlit command aligned with
  the committed client entrypoint (`app.py` in this workspace).
- Point Compose's `env_file` to the actual development file, such as
  `./server/.env`, or create a root `.env` from `.env.example`. The latter
  should contain real local values only in an ignored, uncommitted file.
- For production, inject secrets through the deployment platform or a secret
  manager rather than relying on a developer's local `.env`.
- Update architecture and setup documentation to use the current client
  filename.

### How to verify

Run `docker compose config` to check environment-file resolution, then build
both images with `docker compose build`. Do not include real `.env` contents in
logs, documentation, or commits.

## 5. `RELEVANCE_THRESHOLD` currently has no effect

### What it means

The reported environment variable is not declared in `server/config.py` and is
not used by the application code. Pydantic Settings is configured to ignore
extra settings, so an undeclared variable can be silently ignored. Putting it
in `.env` does not make it an active threshold.

### Recommended fix

First decide what the threshold is meant to control. If it is intended to
reject low-ranking retrieval results, declare a typed setting, validate its
range, and apply it at a clearly defined point in retrieval or answer
generation. Calibrate it against representative questions and labeled results.
Do not use an uncalibrated reranker score as a probability or introduce a
threshold without measuring its effect on correct answers and fallbacks.

If the project does not need this behavior, remove the unused variable from
environment files and documentation instead.

### How to verify

Test values below, at, and above the threshold boundary, plus invalid
configuration. Confirm that changing the setting changes the intended
behavior, rather than merely loading into a settings object.

## 6. “Confidence” is a reranker score

### What it means

The API's `confidence` value is currently the highest cross-encoder reranker
score among retrieved results. A reranker score orders candidate passages; it
is not necessarily a calibrated probability that the answer is correct. The
name can mislead UI users, and the API schema's 0-to-1 constraint may also be
inappropriate if the model emits scores outside that range.

### Recommended fix

Prefer renaming the field to `ranking_score` or `retrieval_score` across the
backend schema, API response, Streamlit UI, tests, and docs. Do not label it as
answer confidence or display it as a percentage. If clients depend on the
existing field, deprecate it deliberately and document the migration.

If a true confidence estimate is needed, calibrate it using evaluation data
and define what event the probability represents (for example, whether the
answer is fully supported). Keep that separate from the reranker score.

### How to verify

Check that the API contract and UI label describe the returned value accurately
and accept the score range the selected reranker can actually produce.

## 7. Sources list retrieved passages, not just cited passages

### What it means

Answer generation currently builds `sources` from every passage in the
retrieved result list. Citation validation checks that answer citations match
available sources, but the response can still list relevant passages that the
answer did not cite.

### Recommended fix

After generation, parse the citations from the answer, validate each citation
against the retrieved passages, and return only the unique document/page
references actually cited. Reuse a single citation parser for validation and
source construction so their rules cannot drift. Continue rejecting unknown
citations and answers with no valid citation, as the existing grounding flow
intends.

### How to verify

Given two retrieved documents and an answer citing only one, assert that the
response includes only the cited document. Also test duplicate citations,
invalid citations, and page-less citations if that format is supported.

## 8. Conversation endpoints have no authentication

### What it means

The chat, conversation-history, and conversation-delete routes do not require
an authenticated identity. Conversation IDs are client supplied or returned by
the API; knowing an ID is not proof that the caller owns the conversation.
Without authorization, someone who obtains another ID may read or delete that
history. The document-listing and chunk-inspection routes are also exposed
without authentication. CORS settings do not provide API authentication.

### Recommended fix

For a private single-user deployment, require an API key or equivalent
authentication at the server boundary. For multi-user use, authenticate users
with the deployment's identity provider and bind each stored conversation to
the authenticated owner. Check ownership on every history, delete, and chat
request; do not rely on an unguessable conversation ID alone. Decide explicitly
whether document-inspection routes and health checks are public. Add rate
limits and avoid logging credentials or conversation contents unnecessarily.

### How to verify

Unauthenticated requests to protected routes should be rejected. An
authenticated user must not be able to read or delete another user's
conversation by changing the conversation ID.

## 9. Tests should use a temporary memory database

### What it means

`RAGService` creates `ConversationMemory` using
`Settings.memory_database_path`. Tests in `test_rag_graph.py` construct
`Settings` without overriding that path, so answer tests can read and write the
default persistent database under `server/data/`. This can leave test data
behind, affect later runs, or touch a developer's saved memory database.

### Recommended fix

Give each test or test fixture a `tmp_path`-based `memory_database_path` and
pass it into `Settings`. Keep tests isolated so their results do not depend on
the checked-in or local SQLite database. Apply the same rule to any future
test that constructs `ConversationMemory` or `RAGService`.

### How to verify

Run the RAG tests repeatedly and confirm that they pass independently without
creating or modifying `server/data/memory.sqlite3`.

## Recommended implementation order

1. Make startup validate and repair a nonempty stale index; verify the
   resulting chunk metadata and parent records.
2. Stop using inferred metadata as a hard filter; keep broad candidates and
   test that missing or imperfect labels do not suppress relevant results.
3. Reconcile Compose's `env_file` with the real local file and build both
   images.
4. Add authentication and conversation ownership checks before exposing the
   service beyond a trusted local environment.
5. Correct the score semantics and make `sources` reflect validated citations.
6. Either implement a measured, typed relevance threshold or remove the
   unused setting.
7. Isolate persistent memory in tests and synchronize the project documentation
   with the actual entrypoint and API behavior.

Run the focused Python test suite after the code changes, then use
`docker compose config` and `docker compose build` to validate deployment
configuration. For retrieval, include regression cases for stale metadata,
missing metadata, mixed-topic documents, and the reported refund question.

## Implementation status

The following changes have now been applied in the project:

| Issue | Implemented change |
|---|---|
| Stale, nonempty Chroma index | Startup always runs index validation. Validation checks metadata across all chunks and verifies every referenced parent exists before reusing the collection. |
| Missing/inferred metadata used as a filter | Vector and BM25 retrieval no longer apply query-inferred hard filters. Metadata matches softly boost fused and final ranking; missing or conflicting labels remain searchable. |
| First-keyword policy-type labels | The existing inference remains heuristic, but a mistaken label can no longer exclude a result from BM25 or Chroma retrieval. |
| Docker paths and environment files | The client Dockerfile already used `app.py`; stale setup references now use that name. Compose's server `env_file` now points at `./server/.env`. The root `.env` supplies the shared Compose token through interpolation, but is no longer a required server `env_file`. |
| `RELEVANCE_THRESHOLD` | Added as an optional typed setting and applied to raw reranker scores. When unset, no score threshold is applied. |
| Misleading confidence field | Renamed the API and RAG result field to `reranker_score`; the UI displays a numeric score, not a percentage. This is an API response contract change. |
| Sources broader than citations | Response sources now include only retrieved document/page references cited in the generated answer; citation validation still rejects unsupported citations. |
| Unauthenticated APIs | A bearer token is required for chat, conversation, and document routes whenever configured; `/health` remains public. Local development may run without a token and logs a warning, while other environments fail closed. Compose passes the root `.env` token to both containers so the API and client use the same value. This shared token is intended for a trusted private deployment, not per-user identity. |
| Tests writing persistent memory | RAG tests now pass a `tmp_path` SQLite database to each test service. |

Focused regression tests were added for stale-index repair, metadata-soft
ranking, missing and conflicting metadata, threshold behavior, cited-source
selection, and API bearer-token checks.

### Evaluation status

The reported `15/53` no-answer count is a historical observation
(approximately `28.3%`); it is not a controlled result for the benchmark in
[RETRIEVAL_EVALUATION.md](./RETRIEVAL_EVALUATION.md). That file contains 25
policy-grounded questions, expected answers, and columns for observed
before/after answers. The benchmark has not yet been run against both versions,
so no measured post-fix no-answer rate is claimed. Fill in the actual API
responses and calculate the rate only after running the same question set,
model, policy files, and evaluation settings on both versions.
