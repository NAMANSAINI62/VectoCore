"""Runner for Semantic Cache Engine backend."""

import os
import sys
from pathlib import Path

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Enforce cache directory on D: drive where disk space is abundant
os.environ["FASTEMBED_CACHE_PATH"] = "D:\\fastembed_cache"
os.environ["HF_HOME"] = "D:\\huggingface_cache"
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import uvicorn
from app.config.settings import get_settings
from app.services.embedding_service import get_embedding_service

if __name__ == "__main__":
    settings = get_settings()
    port = settings.PORT
    print("=" * 60)
    print("Pre-warming multilingual local embedding engine (MiniLM / BGE)...")
    try:
        service = get_embedding_service()
        # Warmup embedding with 1 test query
        _ = service.embed_query("Semantic cache engine warmup")
        print("Embedding engine loaded successfully in memory!")
    except Exception as exc:
        print(f"Warning: Local embedding pre-warm encountered: {exc}")
    print(f"Starting FastAPI backend on http://127.0.0.1:{port}...")
    print("=" * 60)
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=True,
        reload_includes=["*.py", ".env"],
    )
