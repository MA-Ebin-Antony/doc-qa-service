import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
import chromadb
from chromadb.utils import embedding_functions

from app.models import Base

DB_PATH = os.getenv("SQLITE_PATH", "data/qa_store.db")
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

CHROMA_PATH = os.getenv("CHROMA_PATH", "data/chroma_store")

_chroma_client = None
_embed_fn = None


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _get_embed_fn():
    global _embed_fn
    if _embed_fn is None:
        _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
    return _embed_fn


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_PATH, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    return _chroma_client


def get_collection(name: str = "documents"):
    client = get_chroma_client()
    try:
        return client.get_or_create_collection(
            name=name,
            embedding_function=_get_embed_fn(),
            metadata={"hnsw:space": "cosine"},
        )
    except ValueError:
        # recreate if there's an embedding function conflict (e.g. after a reset)
        client.delete_collection(name)
        return client.create_collection(
            name=name,
            embedding_function=_get_embed_fn(),
            metadata={"hnsw:space": "cosine"},
        )
