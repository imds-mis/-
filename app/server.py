from __future__ import annotations

import os
from pathlib import Path
import uvicorn
from .main import create_app


def build_app():
    return create_app(
        database_url=os.getenv("DATABASE_URL", "sqlite:///./medical_documents.db"),
        storage_root=Path(os.getenv("STORAGE_ROOT", "./data")),
        qr_secret=os.environ.get("QR_SIGNING_SECRET", "dev-only-change-me"),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "http://localhost:8080"),
        stt_url=os.getenv("STT_URL") or None,
    )


app = build_app()

if __name__ == "__main__":
    uvicorn.run("app.server:app", host="0.0.0.0", port=int(os.getenv("PORT", "8080")), reload=False)
