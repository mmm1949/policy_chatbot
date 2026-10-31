# Merchant Policy RAG Chatbot

A document-grounded chatbot for answering questions about merchant policies.
The project was developed in two major updates: first, a basic retrieval-
augmented generation (RAG) application; then a more capable conversational
workflow with persistent memory, managed prompts, and latency improvements.

This README explains both stages and documents how to configure, run, and
maintain the current application.

## Development updates

### Update 1: Basic RAG chatbot

The first version established the document question-answering pipeline:

1. **Load policy documents.** Read PDF, DOCX, HTML, and HTM files from
   `server/data/documents/`. PDF extraction handles text and tables; scanned
   image-only pages are not OCR-processed.
2. **Prepare the knowledge base.** Split extracted content into overlapping
   chunks while preserving source and page metadata. Create embeddings locally
   with `sentence-transformers/all-MiniLM-L6-v2` and store the chunks and
   vectors in Chroma.
3. **Retrieve evidence.** For a question, search the persistent Chroma index
   for similar policy chunks.
4. **Generate a grounded response.** Send the question and retrieved excerpts
   to the configured Groq chat model. Return an answer with source and page
   citations rather than treating the model's general knowledge as policy.

This version provided the foundation: a local policy index, semantic vector
search, and answers tied to retrieved policy content.

### Update 2: Agentic memory, prompt management, and faster responses

The second update extended the basic RAG pipeline into a LangGraph workflow
that can interpret conversation context, decide which processing steps are
needed, and check its answer before returning it.

- **Persistent conversational memory:** Store exchanges in SQLite, isolated by
  conversation ID. The workflow loads recent messages and can recall up to
  three relevant older exchanges to resolve follow-up references. Memory
  informs the conversation, but is never used as policy evidence.
- **Prompt management:** Keep prompts for classification, follow-up rewriting,
  query refinement, evidence assessment, answering, grounding, and social
  responses in versioned files under `server/prompts/`. `PromptManager` loads
  the selected prompt set using `PROMPT_VERSION`.
- **Intent-aware workflow:** Classify messages as policy questions, follow-ups,
  greetings, or out-of-scope requests. Rewrite follow-ups as standalone
  retrieval queries using the current conversation's context.
- **Evidence and grounding checks:** Check whether retrieved policy excerpts
  are sufficient, then verify the drafted answer's claims and citations.
  Discard unsupported drafts and return a fixed no-answer response when the
  available evidence is insufficient or grounding fails.
- **Bounded query refinement:** If the initial evidence check fails, generate
  at most two additional search queries and run one refinement pass.
- **Latency improvements:** Run evidence assessment and answer drafting
  concurrently, and handle common standalone greetings locally without
  classification and response-generation calls. These reduce serial work and
  unnecessary model calls; response times are not benchmarked here.
- **Conversation controls:** Persist exchanges across API restarts, expose
  history retrieval and deletion endpoints, and limit retained conversation
  history.

## Current request workflow

```text
Policy files
  -> extract text and tables
  -> split into overlapping chunks with source metadata
  -> create local sentence-transformer embeddings
  -> store chunks and vectors in Chroma

Chat message
  -> load recent and relevant conversation history
  -> classify the message
  -> rewrite follow-ups when needed
  -> retrieve policy chunks from Chroma
  -> assess evidence and draft an answer concurrently
  -> optionally refine retrieval once
  -> verify evidence and citations
  -> save the exchange and return answer, confidence, and sources
```

The Streamlit client sends chat requests to the FastAPI server. LangGraph
orchestrates the backend steps, SQLite stores conversation history, and Chroma
stores the policy knowledge base. Groq is used for language-model tasks;
embeddings are generated locally.
A conversational assistant that answers merchant-policy questions from the
project's indexed policy documents. Its major capabilities include:

- **Traditional RAG:** Ingests PDF, DOCX, and HTML policy files, extracts
  their text and tables, creates searchable chunks, and generates answers from
  retrieved policy evidence rather than relying only on model knowledge.

- **Agentic RAG workflow:** Uses LangGraph to classify requests, rewrite
  contextual follow-ups, retrieve evidence, and make one bounded refinement
  pass of up to two searches when needed. Greetings are handled without
  document retrieval, while unrelated requests use a safe fallback.

- **Grounded responses:** Checks that answer citations match retrieved sources
  and asks the model to verify factual claims against those sources. If
  grounding still fails after refinement, the assistant returns a no-answer
  response instead of presenting an unsupported answer.

- **Prompt management:** Keeps named prompts for classification, follow-up
  rewriting, query refinement, answers, and grounding in versioned directories
  such as `server/prompts/v1/`. Select a prompt set with `PROMPT_VERSION`.

- **Hybrid retrieval:** Combines BM25 keyword search for exact identifiers and
  policy terms with Chroma vector search for semantic matches. Reciprocal Rank
  Fusion combines the rankings, then a local BGE cross-encoder reranks up to 20
  candidates and returns up to 5.

- **Metadata-aware search:** Adds document name, policy type, region, version,
  effective date, and payment-method metadata during indexing. Supported
  filters are inferred from the user's query and applied before fusion;
  unspecified metadata remains eligible as a fallback.

- **Parent-section and table retrieval:** Matches small searchable chunks but
  returns their stored parent sections. Extracted tables are kept whole so
  answers can include related rows and context.

- **Conversation memory:** Stores bounded conversation history in SQLite,
  separated by conversation ID. History can help interpret follow-ups, but is
  never treated as policy evidence.

- **Faster common paths:** Clearly policy-related questions bypass the LLM
  classifier; standalone greetings are answered locally. The answer path avoids
  a separate LLM evidence-sufficiency call, and the UI displays responses
  without a simulated typing delay.

- **Web interface and API:** Provides a Streamlit chat UI and a FastAPI backend
  for chat, conversation history, document listings, and indexed-chunk
  inspection. Answers include source/page citations and a retrieval confidence
  score.

The application uses Groq for chat-model tasks. Sentence-transformer embeddings,
BM25 search, and cross-encoder reranking run locally; the reranker uses CUDA
when available and CPU otherwise.

### Basic RAG

The first version established the document question-answering pipeline:

1. **Load policy documents.** Read PDF, DOCX, HTML, and HTM files from
   `server/data/documents/`. PDF extraction handles text and tables; scanned
   image-only pages are not OCR-processed.
2. **Prepare the knowledge base.** Split extracted content into overlapping
   chunks while preserving source and page metadata. Create embeddings locally
   with `sentence-transformers/all-MiniLM-L6-v2` and store the chunks and
   vectors in Chroma.
3. **Retrieve evidence.** For a question, search the persistent Chroma index
   for similar policy chunks.
4. **Generate a grounded response.** Send the question and retrieved excerpts
   to the configured Groq chat model. Return an answer with source and page
   citations rather than treating the model's general knowledge as policy.

This version provided the foundation: a local policy index, semantic vector
search, and answers tied to retrieved policy content.

### Agentic memory, prompt management, and faster responses

The second update extended the basic RAG pipeline into a LangGraph workflow
that can interpret conversation context, decide which processing steps are
needed, and check its answer before returning it.

- **Persistent conversational memory:** Store exchanges in SQLite, isolated by
  conversation ID. The workflow loads recent messages and can recall up to
  three relevant older exchanges to resolve follow-up references. Memory
  informs the conversation, but is never used as policy evidence.
- **Prompt management:** Keep prompts for classification, follow-up rewriting,
  query refinement, evidence assessment, answering, grounding, and social
  responses in versioned files under `server/prompts/`. `PromptManager` loads
  the selected prompt set using `PROMPT_VERSION`.
- **Intent-aware workflow:** Classify messages as policy questions, follow-ups,
  greetings, or out-of-scope requests. Rewrite follow-ups as standalone
  retrieval queries using the current conversation's context.
- **Evidence and grounding checks:** Check whether retrieved policy excerpts
  are sufficient, then verify the drafted answer's claims and citations.
  Discard unsupported drafts and return a fixed no-answer response when the
  available evidence is insufficient or grounding fails.
- **Bounded query refinement:** If the initial evidence check fails, generate
  at most two additional search queries and run one refinement pass.
- **Latency improvements:** Run evidence assessment and answer drafting
  concurrently, and handle common standalone greetings locally without
  classification and response-generation calls. These reduce serial work and
  unnecessary model calls; response times are not benchmarked here.
- **Conversation controls:** Persist exchanges across API restarts, expose
  history retrieval and deletion endpoints, and limit retained conversation
  history.

## Hybrid retrieval, metadata, and parent context

At indexing time, each source is tagged with its document name, broad policy
type, region, document version, effective date, and payment method. The indexer
infers these tags from document names and text. It recognizes explicit version
labels and ISO effective dates; missing or ambiguous values are marked
`unspecified`. Query-time rules detect supported policy types, regions, payment
methods, explicit version numbers, and ISO effective dates. Those filters are
applied to both the Chroma vector search and the BM25 candidate set before
fusion. Documents tagged `unspecified` (and general policy documents where
appropriate) remain eligible, so incomplete source metadata does not silently
remove otherwise useful evidence. This is rule-based metadata inference, not an
LLM-selected search router.

The BM25 and vector result lists are fused by Reciprocal Rank Fusion (RRF) with
the configurable `RRF_CONSTANT` (default `60`). A local BGE cross-encoder then
reranks up to `RETRIEVAL_K` candidates and keeps `RERANKER_TOP_K` (default `5`).
The selected child chunks point to persisted parent sections; extracted tables
are kept whole as parent documents so a matching row can be returned with its
surrounding table context. Parent text is stored in
`server/data/chroma/parents.sqlite3`.

The first chat request downloads the configured cross-encoder model if it is
not already cached. `RERANKER_DEVICE=auto` uses CUDA when available and CPU
otherwise; set `RERANKER_MODEL` to another compatible Sentence Transformers
cross-encoder when needed. Metadata inference
is deliberately conservative: if a document mentions multiple regions or
payment methods, the tag is `unspecified`. For accurate region/version/date
filtering, make those values explicit in the source documents. Existing
vector-only collections are refreshed from the source documents on API startup
when the required hybrid-search metadata is absent; the CLI indexing command
also rebuilds the collection.
## Features

### Policy knowledge base

- Supports PDF, DOCX, HTML, and HTM source files.
- Extracts PDF text and tables; scanned image-only PDF content requires OCR
  outside the current pipeline.
- Preserves document and page metadata for citations.
- Uses configurable overlapping chunks and local sentence-transformer
  embeddings.
- Stores vectors persistently in Chroma and supports reindexing after source
  files change.
- Provides document and indexed-chunk inspection through the API.

### Conversational RAG

- Separates policy questions, follow-ups, greetings, and out-of-scope messages.
- Uses recent history and up to three matching older exchanges to understand
  follow-ups within the same conversation.
- Keeps conversation memory separate from policy evidence.
- Checks whether policy evidence supports an answer and validates grounding and
  citations before returning it.
- Performs at most one retrieval refinement pass with up to two additional
  queries.
- Returns the configured no-answer response when evidence is missing,
  insufficient, or fails grounding validation.
- Returns answer confidence and source/page citations. Confidence is the
  highest retrieved-chunk similarity for a grounded answer; it is a retrieval
  score, not a calibrated probability.

### Prompt and response management

- Stores named prompts in versioned directories, currently
  `server/prompts/v1/`.
- Selects the prompt directory through `PROMPT_VERSION`.
- Handles common standalone pleasantries locally; generated social responses
  are restricted to pleasantries and do not answer factual policy questions.

### Conversation memory

- Persists exchanges in SQLite, isolated by conversation ID.
- Loads the latest 12 messages and recalls up to three relevant older exchanges.
- Retains up to 200 exchanges per conversation and 256 active conversations by
  default.
- Supports reading and deleting a conversation through the API.
- Persists across API restarts. A local SQLite file is intended for a
  single-server deployment; use shared persistent storage for multi-replica
  deployments.

## Technology stack

| Area | Technology |
|---|---|
| User interface | Streamlit |
| API | FastAPI |
| Workflow orchestration | LangGraph |
| Chat model | Groq, configured with `GROQ_MODEL` |
| Embeddings | Local `sentence-transformers/all-MiniLM-L6-v2` by default |
| Vector store | Persistent Chroma |
| Conversation memory | SQLite |
| Document formats | PDF, DOCX, HTML, HTM |

## Run locally

### 1. Configure the environment

From the project root, copy the example configuration:

```powershell
Copy-Item .env.example .env
```

Set `GROQ_API_KEY` in `.env` to a key from your Groq account. Do not put
credentials in source files or commit `.env`. The chat model uses Groq; the
embedding model runs locally and does not need an embedding API key.

### 2. Add and index policy documents

Place source files in:

```text
server/data/documents/
```

Create a Python environment, install server dependencies, and index the files
from the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r server\requirements.txt
python -m pip install pytest
$env:PYTHONPATH = "server"
python -m ingestion.index_documents
```

The first indexing run downloads the sentence-transformer embedding model, so
it needs internet access. The BGE cross-encoder is downloaded on the first chat
request if not already cached. The generated Chroma database is stored in
`server/data/chroma/` by default. Re-run the indexing command after adding,
removing, or changing source documents; the command updates the collection from
the files in `server/data/documents/`. The server also automatically indexes
source files at startup if the Chroma collection is empty or lacks the
metadata/parent records required by hybrid retrieval.

### 3. Start the API and client

In the first PowerShell terminal, from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "server"
python -m uvicorn api.main:app --reload
```

In a second terminal:

```powershell
.\.venv\Scripts\Activate.ps1
$env:POLICY_API_URL = "http://localhost:8000"
python -m streamlit run client\streamlit_app.py
```

Open `http://localhost:8501` to use the chatbot. The API is available at
`http://localhost:8000`, and interactive API documentation is at
`http://localhost:8000/docs`.

## Configuration

| Setting | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | Groq chat API key | Required |
| `GROQ_MODEL` | Groq chat model | `openai/gpt-oss-120b` |
| `PROMPT_VERSION` | Prompt set directory version | `v1` |
| `EMBEDDING_MODEL` | Local sentence-transformer model | `sentence-transformers/all-MiniLM-L6-v2` |
| `DOCUMENT_DIRECTORY` | Original policy documents | `<project>/server/data/documents` |
| `CHROMA_PERSIST_DIRECTORY` | Persistent vector database | `<project>/server/data/chroma` |
| `MEMORY_DATABASE_PATH` | Persistent SQLite conversation memory | `<project>/server/data/memory.sqlite3` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Text chunking settings | `900` / `150` |
| `RETRIEVAL_K` | Maximum hybrid candidates passed to the reranker | `20` |
| `RERANKER_TOP_K` | Number of parent sections/tables returned after reranking | `5` |
| `RRF_CONSTANT` | Reciprocal Rank Fusion smoothing constant | `60` |
| `RERANKER_MODEL` | Local Sentence Transformers cross-encoder | `BAAI/bge-reranker-base` |
| `RERANKER_DEVICE` | Reranker execution device (`auto`, `cpu`, or `cuda`) | `auto` |
| `CORS_ORIGINS` | Allowed browser origins | `http://localhost:8501` |
| `POLICY_API_URL` | API URL used by the Streamlit client | `http://localhost:8000` |

Settings can be provided through environment variables. In development, the
server loads the project-root `.env` file and also supports `server/.env`.
Deployment environments should provide secrets through environment variables
or a secret manager.

The source files are the durable originals; Chroma stores the indexed chunks and
embeddings, and the adjacent SQLite database stores parent sections and tables.
Back up both folders. If you restore the documents but lose the index or parent
database, rerun `python -m ingestion.index_documents`.

### Response-time notes

The BM25 corpus and reranker are loaded lazily and cached in the running process;
the first request can take longer while the cross-encoder is downloaded and
loaded. `RERANKER_DEVICE=auto` uses CUDA when available and CPU otherwise.
Clearly policy-related questions bypass the LLM classifier, and answers no
longer make a separate LLM evidence-sufficiency call before citation and
grounding checks. The UI displays the answer as soon as the API returns it,
without an artificial word-by-word delay. API logs report total request time
and routing/grounding decisions.

## API

| Method and path | Description |
|---|---|
| `GET /health` | Check API health. |
| `POST /chat` | Submit a policy question and optional conversation ID. |
| `GET /conversations/{conversation_id}` | Get retained messages for a conversation. |
| `DELETE /conversations/{conversation_id}` | Delete retained conversation history. |
| `GET /documents` | List indexed documents and chunk counts. |
| `GET /documents/{document_name}/chunks?offset=0&limit=20` | Inspect indexed chunks for a document. |

Example chat request:

```json
{
  "question": "What is the settlement schedule?",
  "conversation_id": "optional-existing-conversation-id"
}
```

The response contains `answer`, `confidence`, `sources`, and
`conversation_id`. If no conversation ID is supplied, the API creates one.
Chat responses include `answer`, `confidence`, `sources`, and
`conversation_id`. If retrieval returns no evidence or the answer fails
grounding verification after its bounded refinement pass, the API returns the
configured no-answer message instead of presenting an unsupported answer. The
refinement is bounded to one extra pass with at most two additional search
queries.


## Docker

Configure `.env`, place policy files in `server/data/documents/`, then index
and start the services from the project root:

```powershell
docker compose run --build --rm server python -m ingestion.index_documents
docker compose up --build -d
```

Docker uses a persistent named volume for Chroma (including the parent-section
SQLite database) and the local documents folder as a read-only bind mount. Run
the indexing command before starting the API, and repeat it after policy source
files change. Stop the running server before reindexing so the Chroma database
is not open in two processes. The first indexing run downloads the local
embedding model; the cross-encoder downloads on the first chat request.

## Tests

From the project root with the virtual environment active:

```powershell
$env:PYTHONPATH = "server"
python -m pytest tests
```

## Current boundaries

- Retrieval combines BM25 keyword search, vector similarity, and reciprocal
  rank fusion; graph retrieval is not implemented.
- Policy files are indexed from the configured local directory. There is no
  document-upload UI or ingestion API.
- Scanned image-only PDF pages are not OCR-processed.
- Conversation recall uses bounded SQLite history and term overlap. It is
  conversation context, not a separate vector memory or a source of policy
  facts.
- Confidence is based on retrieved-chunk similarity and should not be read as a
  calibrated probability.

For detailed internals, see [BACKEND_ARCHITECTURE.md](./BACKEND_ARCHITECTURE.md)
and [PROJECT_STRUCTURE.md](./PROJECT_STRUCTURE.md).
