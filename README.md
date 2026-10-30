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

The first indexing run downloads the sentence-transformer model and requires
internet access. The default Chroma database is written to
`server/data/chroma/`. Re-run the indexing command after adding, changing, or
removing source documents. If the collection is empty, the API also attempts to
index the local source files at startup.

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
| `MEMORY_DATABASE_PATH` | SQLite conversation memory | `<project>/server/data/memory.sqlite3` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Chunking settings in characters | `900` / `150` |
| `RETRIEVAL_K` | Chunks requested per vector search | `8` |
| `RELEVANCE_THRESHOLD` | Minimum similarity for evidence use | `0.35` |
| `CORS_ORIGINS` | Allowed browser origins | `http://localhost:8501` |
| `POLICY_API_URL` | API URL used by the Streamlit client | `http://localhost:8000` |

Settings can be provided through environment variables. In development, the
server loads the project-root `.env` file and also supports `server/.env`.
Deployment environments should provide secrets through environment variables
or a secret manager.

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

## Docker

Configure `.env`, place policy files in `server/data/documents/`, then index
and start the services from the project root:

```powershell
docker compose run --build --rm server python -m ingestion.index_documents
docker compose up --build -d
```

Docker Compose uses persistent volumes for Chroma and conversation memory and
mounts source documents read-only. Reindex after policy files change; stop the
running server before reindexing. The initial indexing run downloads the local
embedding model.

## Tests

From the project root with the virtual environment active:

```powershell
$env:PYTHONPATH = "server"
python -m pytest tests
```

## Current boundaries

- Retrieval uses vector similarity search; BM25, reciprocal-rank fusion, and
  graph retrieval are not implemented.
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
