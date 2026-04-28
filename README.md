# CodeMind

A local, privacy-first semantic search engine for codebases. Ask questions about your code in plain English and get back relevant snippets along with an LLM-generated explanation — all running on your machine.

Built with [Qdrant Edge](https://qdrant.tech/documentation/edge/) (an in-process vector database, like SQLite but for vectors), so your code never leaves your machine during indexing or retrieval.

---

## What It Does

- **Indexes** a repository by parsing it into function/class-level chunks
- **Summarizes** each chunk using an LLM (cached, so it only runs once per function)
- **Embeds** everything locally using `fastembed` (CPU, no GPU required)
- **Stores** vectors on disk via Qdrant Edge — no server, no Docker
- **Answers** natural language queries by retrieving the most semantically relevant code and passing it to an LLM for explanation

---

## Project Structure

```
codemind/
├── codemind/                   # Core package
│   ├── config.py               # All env vars and constants
│   ├── parser.py               # Walks repo, extracts function/class chunks
│   ├── Embedder_working.py     # Generates embeddings via fastembed (local CPU)
│   ├── summarizes_this.py      # Generates + caches LLM summaries per chunk
│   ├── Llm_azure.py            # Azure OpenAI client (summarize + answer)
│   ├── store.py                # Qdrant Edge CRUD — upsert, search, count
│   ├── query_usage.py          # Query pipeline: embed → search → return
│   ├── indexer.py              # Orchestrates: parse → summarize → embed → store
│   ├── cli.py                  # Terminal interface (typer + rich)
│   └── server.py               # FastAPI web server
│
├── frontend/                   # Web UI
│   ├── index.html
│   ├── styles.css
│   └── app.js
│
├── demo/
│   └── sample_repo/            # Example codebase to test against
│       ├── auth.py
│       ├── cache.py
│       ├── database.py
│       ├── api.py
│       └── retry.py
│
├── .env.example                # Copy this to .env and fill in your keys
├── pyproject.toml              # Package definition and dependencies
├── .qdrant-edge/               # Auto-created: local vector database (gitignore this)
├── .embed-cache/               # Auto-created: fastembed model cache
└── .summary-cache.json         # Auto-created: LLM summary cache
```

---

## Prerequisites

- **Python 3.12** — `qdrant-edge-py` ships pre-compiled binaries that are only compatible with Python 3.12. Other versions will fail to install or import.

  On macOS you can install it via Homebrew:
  ```bash
  brew install python@3.12
  ```

- An **Azure OpenAI** account with a deployment of `gpt-5.4-mini` (or any `gpt-4o`/`gpt-3.5` class model).

---

## Setup

### 1. Clone and enter the project

```bash
git clone <your-repo-url>
cd codemind
```

### 2. Create a virtual environment using Python 3.12

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -e .
```

This installs the `codemind` CLI tool and **all dependencies**, including `qdrant-edge-py` (the local vector database), `fastembed` (local embedding model), `openai`, `typer`, `rich`, `fastapi`, and `uvicorn`.

> **Note on `qdrant-edge-py`**: This package provides the Qdrant Edge in-process vector database. It is included automatically via `pyproject.toml` — you do not need to install it separately. If you see a binary import error, double-check that your virtual environment is using Python 3.12 (`python --version`).

### 4. Configure your API keys

```bash
cp .env.example .env
```

Then open `.env` and fill in your Azure OpenAI credentials:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_KEY=your_api_key_here
AZURE_OPENAI_VERSION=2025-01-01-preview
AZURE_OPENAI_DEPLOYMENT=gpt-5.4-mini
```

---

## Running

### Index a repository

Point it at any folder on your machine:

```bash
codemind index ./demo/sample_repo
```

This will:
1. Parse all Python/JS/TS/Go/etc. files into function-level chunks
2. Generate one-line LLM summaries per chunk (cached to `.summary-cache.json`)
3. Embed everything locally using `BAAI/bge-small-en-v1.5`
4. Store vectors in `.qdrant-edge/` on disk

For large repos, summaries are the slowest step. They are cached, so re-indexing the same repo is fast.

To force a full re-index from scratch:

```bash
codemind index ./your-repo --force
```

To skip LLM summaries (faster, lower quality retrieval):

```bash
codemind index ./your-repo --no-summarise
```

---

### Query from the CLI

```bash
codemind ask "where is retry logic implemented?"
codemind ask "how does authentication work?"
codemind ask "how is the cache invalidated?"

```
<img width="769" height="689" alt="Screenshot 2026-04-28 at 4 54 56 PM" src="https://github.com/user-attachments/assets/e062d014-3b01-4a02-b18e-464f2066b17b" />

```
To skip the LLM explanation and just see raw retrieval results:

```bash
codemind ask "where is JWT validated?" --no-llm
```

Control how many results are returned:

```bash
codemind ask "database connection pooling" --top-k 10
```

---

### Check index stats

```bash
codemind info
```

<img width="597" height="179" alt="Screenshot 2026-04-28 at 4 54 26 PM" src="https://github.com/user-attachments/assets/1ab29394-b214-4f09-a736-620c2bcce2ec" />

---

### Use the Web UI

Start the web server:

```bash
uvicorn codemind.server:app --port 8000 --reload
```
<img width="1419" height="729" alt="Screenshot 2026-04-28 at 5 08 00 PM" src="https://github.com/user-attachments/assets/d13be6b7-b460-4b37-8462-e83bfd5a2f11" />


Open your browser at **http://127.0.0.1:8000** and type your question in the search bar.

---
<img width="1600" height="772" alt="WhatsApp Image 2026-04-28 at 17 10 59" src="https://github.com/user-attachments/assets/88b44d49-2f73-43f7-aef9-2d9a38fa09e2" />

<img width="1438" height="740" alt="Screenshot 2026-04-28 at 5 08 20 PM" src="https://github.com/user-attachments/assets/cbe62eed-cb64-4127-a500-be6535d6bd42" />


## How It Works


<img width="2310" height="5421" alt="NLLM Codebase Embedding-2026-04-27-192426" src="https://github.com/user-attachments/assets/6e610cfa-1665-4fdf-913e-fe139cb060c3" />



---

## Key Design Decisions

**Why Qdrant Edge?**
It runs in-process with zero infrastructure. No Docker, no server, no background service. Think of it as SQLite for vector search. Data is persisted on disk and locked to one process at a time.

**Why function-level chunking?**
Whole-file embeddings are too coarse. Line-level is too noisy. Function/class level is the right granularity for "what does this code do" questions.

**Why embed `name + summary + code + file` together?**
Raw code embeddings capture syntax, not intent. Adding the LLM-generated summary like "retries HTTP requests with exponential backoff" dramatically improves how well a natural language query matches the right chunk.

**Why cache summaries?**
LLM calls are slow and cost money. Summaries are deterministic for a given chunk. The cache (`uuid5` keyed by `file::name`) means re-indexing only calls the LLM for new or changed functions.

---

## What You Can Ask

Architecture questions:
```
"How is database connection pooling implemented?"
"What does the auth module do?"
```

Feature questions:
```
"Where is retry logic with backoff?"
"How is the cache invalidated?"
```

Debugging questions:
```
"Where are JWT tokens validated?"
"What happens when a user login fails?"
```

---

## Supported Languages

Python, JavaScript, TypeScript, Go, Java, Rust, Ruby, C++, C, C#, PHP, Swift, Kotlin.

Python uses AST parsing for exact function boundaries. All other languages use regex heuristics.

---

## Gitignore Recommendations

Add these to your `.gitignore`:

```
.qdrant-edge/
.embed-cache/
.summary-cache.json
.venv/
.env
```
