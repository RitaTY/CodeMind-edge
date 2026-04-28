import os
from pathlib import Path
from dotenv import load_dotenv

_root = Path(__file__).parent.parent
load_dotenv(_root / ".env", override=False)


AZURE_ENDPOINT   = os.environ.get("AZURE_OPENAI_ENDPOINT")
AZURE_KEY        = os.environ.get("AZURE_OPENAI_KEY")
AZURE_VERSION    = os.environ.get("AZURE_OPENAI_VERSION",    "2025-01-01-preview")
AZURE_DEPLOYMENT = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-5.4-mini")

_REQUIRED = {
    "AZURE_OPENAI_ENDPOINT": AZURE_ENDPOINT,
    "AZURE_OPENAI_KEY":      AZURE_KEY,
}
_missing = [k for k, v in _REQUIRED.items() if not v]
if _missing:
    raise EnvironmentError(
        f"Missing required environment variables: {', '.join(_missing)}\n"
        f"Copy .env.example → .env and fill in your credentials."
    )

SHARD_DIR       = str(_root / ".qdrant-edge")
VECTOR_NAME     = "code-vector"
VECTOR_DIM      = 384          # bge-small-en-v1.5

EMBED_MODEL     = "BAAI/bge-small-en-v1.5"
EMBED_CACHE_DIR = str(_root / ".embed-cache")

SUMMARY_CACHE   = str(_root / ".summary-cache.json")
MAX_CHUNK_LINES = 120          # split functions larger than this
TOP_K_DEFAULT   = 5            # default results returned per query

SKIP_DIRS  = {".git", "__pycache__", "node_modules", ".venv", "venv",
              "env", ".env", "dist", "build", ".qdrant-edge", ".embed-cache"}
SKIP_EXTS  = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin",
              ".jpg", ".jpeg", ".png", ".gif", ".svg", ".ico",
              ".zip", ".tar", ".gz", ".lock", ".min.js"}
CODE_EXTS  = {".py", ".js", ".ts", ".go", ".java", ".rs", ".rb",
              ".cpp", ".c", ".cs", ".php", ".swift", ".kt"}
