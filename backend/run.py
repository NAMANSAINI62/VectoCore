"""Runner for VectoCore Semantic Cache Engine backend."""

import os
import sys
from pathlib import Path

# Ensure backend directory is on sys.path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

import uvicorn
from app.config.settings import get_settings
from app.services.embedding_service import get_embedding_service

if __name__ == "__main__":
    settings = get_settings()
    port = settings.PORT
    print("=" * 60)
    print(f"Verifying embedding engine ({settings.EMBEDDING_MODEL_NAME})...")
    try:
        service = get_embedding_service()
        _ = service.embed_query("VectoCore embedding engine warmup")
        print("Embedding engine ready!")
    except Exception as exc:
        print(f"Warning: Embedding warmup encountered: {exc}")
    print(f"Starting FastAPI backend on http://127.0.0.1:{port}...")
    print("=" * 60)
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=port,
        reload=True,
        reload_includes=["*.py", ".env"],
    )
