# Merchant Policy RAG Chatbot

A traditional retrieval-augmented generation application for merchant policy
questions. The Streamlit client sends a question and conversation ID to FastAPI.
The server keeps bounded, persistent conversation history in SQLite, recalls
relevant older exchanges for follow-ups, retrieves similar chunks from a
persistent Chroma vector database, then asks the configured Groq chat model to
answer from policy chunks and cite their source documents.

## LangGraph RAG workflow

```text
PDF / DOCX / HTML files
    → extract text and tables
    → split into overlapping chunks with source/page metadata
    → create local sentence-transformer embeddings
    → store chunks and vectors in Chroma

Merchant question
    → recall recent and relevant earlier messages from this conversation
    → classify as policy, follow-up, greeting, or out-of-scope
    → rewrite follow-ups using conversation context only
    → retrieve relevant Chroma chunks
    → concurrently assess evidence and draft an answer
    → refine into up to two searches once if needed; discard drafts if evidence is insufficient
    → verify grounding/citations before returning
    → return answer, confidence, and source/page citations
```

Groq is used for text generation. Embeddings are generated locally with
`sentence-transformers/all-MiniLM-L6-v2`; Groq's chat API is not used for
embeddings. LangGraph orchestrates classification, follow-up rewriting,
retrieval, one bounded retrieval-refinement pass, relevance checking, answer
drafting, grounding verification, and memory updates. Evidence assessment and
answer drafting run concurrently to reduce serial model latency; drafts are
discarded unless evidence sufficiency and grounding checks pass. Common
standalone greetings are handled locally without model calls. The retrieval layer is
vector-only; graph retrieval, BM25, admin uploads, and an ingestion API are not
included. Documents are added to the server's documents folder and indexed with
a command-line script. Named, versioned prompts are stored under
`server/prompts/v1/` and loaded through the prompt manager. Conversation memories
can clarify references but are never policy evidence.
Select the active template set with `PROMPT_VERSION` (default `v1`); add a new
versioned directory before switching a deployment.

Conversation memory is stored in SQLite and isolated by conversation ID. The
graph recalls the latest 12 messages plus up to three relevant older exchanges
from the same conversation, and retains up to 200 exchanges per conversation and
256 active conversations. Restarting the API does not clear memory. Selecting
**New conversation** starts a fresh, isolated conversation; deleting a
conversation removes its saved exchanges. The default database is
`server/data/memory.sqlite3`; configure `MEMORY_DATABASE_PATH` to select another
location. For multi-replica deployments, use a shared production database rather
than a local SQLite file.

## 1. Configure Groq

From the project root, make the local environment file:

```powershell
Copy-Item .env.example .env
```

Open `.env` and enter the API key created in your Groq account:

```dotenv
GROQ_API_KEY=your-groq-api-key
GROQ_MODEL=openai/gpt-oss-120b
```

Keep the key in this root `.env` file. Do not add it to Python code, the Streamlit
client, or source control. `.env` is excluded by `.gitignore`. `EMBEDDING_MODEL`
selects the local embedding model and does not require an embedding API key.

## 2. Put policy files in the data folder

Copy the files you want indexed into:

```text
server/data/documents/
```

Supported types: PDF, DOCX, HTML, and HTM. PDFs are processed by direct text and
table extraction only; image-only scanned pages are not OCR processed and will
not contribute searchable text. Keep the original source files in this directory
so you can rebuild the index later.

## 3. Install and index

Use Python 3.11 or 3.12. From the project root in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r server\requirements.txt
python -m pip install pytest
$env:PYTHONPATH = "server"
python -m ingestion.index_documents
```

The first indexing run downloads the sentence-transformer model, so it needs
internet access. The generated Chroma database is stored in
`server/data/chroma/` by default. Re-run the indexing command after adding,
removing, or changing source documents; the command updates the collection from
the files in `server/data/documents/`. The server also automatically indexes
source files at startup if the Chroma collection is empty.

To inspect stored chunks, expand a document in the Streamlit sidebar and select
**Show indexed chunks**. The API also exposes
`GET /documents/{document_name}/chunks?offset=0&limit=20`.

## 4. Start the API and chat UI

Keep the virtual environment active. In the first PowerShell terminal, from the
project root:

```powershell
$env:PYTHONPATH = "server"
python -m uvicorn api.main:app --reload
```

In a second terminal:

```powershell
.\.venv\Scripts\Activate.ps1
$env:POLICY_API_URL = "http://localhost:8000"
python -m streamlit run client\streamlit_app.py
```

Open `http://localhost:8501` and ask a merchant policy question. The server API
is at `http://localhost:8000`; interactive API docs are at `/docs`.

## Data and configuration

| Setting | Purpose | Default |
|---|---|---|
| `GROQ_API_KEY` | Groq chat API key | Required |
| `GROQ_MODEL` | Groq chat model | `openai/gpt-oss-120b` |
| `PROMPT_VERSION` | Versioned prompt set | `v1` |
| `EMBEDDING_MODEL` | Local Hugging Face sentence-transformer model | `sentence-transformers/all-MiniLM-L6-v2` |
| `DOCUMENT_DIRECTORY` | Original PDFs, DOCX, and HTML files | `<project>/server/data/documents` |
| `CHROMA_PERSIST_DIRECTORY` | Persistent vector database | `<project>/server/data/chroma` |
| `MEMORY_DATABASE_PATH` | Persistent SQLite conversation memory | `<project>/server/data/memory.sqlite3` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | Text chunking settings | `900` / `150` |
| `RETRIEVAL_K` | Number of similar chunks to retrieve | `8` |
| `RELEVANCE_THRESHOLD` | Minimum cosine-similarity score to answer | `0.35` |

The source files are the durable originals; Chroma stores the indexed chunks and
embeddings. Back up both folders. If you restore the documents but lose the
Chroma data, rerun `python -m ingestion.index_documents`.

## API

- `GET /health`
- `GET /documents`
- `GET /conversations/{conversation_id}`
- `DELETE /conversations/{conversation_id}`
- `POST /chat` with `{"question":"What is the settlement schedule?"}`

Chat responses include `answer`, `confidence`, `sources`, and
`conversation_id`. If evidence is missing, insufficient, or fails grounding
verification, the API returns the configured no-answer message instead of
generating an unsupported answer. The retrieval refinement is bounded to one
extra pass with at most two additional search queries.

## Docker

Configure `.env`, place documents under `server/data/documents/`, then start:

```powershell
docker compose run --build --rm server python -m ingestion.index_documents
docker compose up --build -d
```

Docker uses a persistent named volume for Chroma and the local documents folder
as a read-only bind mount. Run the indexing command before starting the API, and
repeat it after policy source files change. Stop the running server before
reindexing so the Chroma database is not open in two processes. The first
indexing run also downloads the local embedding model.

## Tests

From the project root:

```powershell
$env:PYTHONPATH = "server"
python -m pytest tests
```
