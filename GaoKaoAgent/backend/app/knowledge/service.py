import logging
from pathlib import Path
from uuid import uuid4

from app.api.responses import AppError
from app.core.config import PROJECT_ROOT, Settings
from app.knowledge.chunking import split_sections
from app.knowledge.models import ModelGateway
from app.knowledge.parsing import ALLOWED_EXTENSIONS, parse_document
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.vectors import VectorStore


logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
STORAGE_ROOT = PROJECT_ROOT / "storage"


class KnowledgeService:
    def __init__(
        self, repository: KnowledgeRepository, gateway: ModelGateway,
        settings: Settings, storage_root: Path = STORAGE_ROOT,
    ):
        self.repository = repository
        self.gateway = gateway
        self.settings = settings
        self.storage_root = storage_root

    def _vectors(self) -> VectorStore:
        return VectorStore(self.storage_root / "chroma", self.settings.embedding_model)

    def get_document(self, document_id: int) -> dict:
        document = self.repository.get_document(document_id)
        if document is None:
            raise AppError(404, "NOT_FOUND", "Knowledge document not found")
        return self.public_document(document)

    @staticmethod
    def public_document(document: dict) -> dict:
        return {key: value for key, value in document.items() if key != "storage_path"}

    def upload(self, filename: str, content: bytes, metadata: dict) -> dict:
        name = filename.replace("\\", "/").split("/")[-1].strip()
        extension = Path(name).suffix.lower()
        if not name or extension not in ALLOWED_EXTENSIONS:
            raise AppError(422, "UNSUPPORTED_FILE", "Only PDF, DOCX and TXT files are supported")
        if not content:
            raise AppError(422, "EMPTY_FILE", "Uploaded file is empty")
        if len(content) > MAX_UPLOAD_BYTES:
            raise AppError(413, "FILE_TOO_LARGE", "Maximum document size is 10 MB")
        sections = parse_document(name, content)
        chunks = split_sections(sections)
        if len(chunks) > 2000:
            raise AppError(413, "TOO_MANY_CHUNKS", "Document has too many text chunks")
        directory = self.storage_root / "uploads"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{uuid4().hex}{extension}"
        path.write_bytes(content)
        try:
            document_id = self.repository.create_document(
                {**metadata, "original_name": name, "file_type": extension[1:],
                 "storage_path": str(path)}, chunks,
            )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        if self.gateway.embedding_ready:
            self.index(document_id)
        return self.get_document(document_id)

    def index(self, document_id: int) -> dict:
        document = self.get_document(document_id)
        if not self.gateway.embedding_ready:
            raise AppError(503, "EMBEDDING_NOT_CONFIGURED", "Embedding API is not configured")
        chunks = self.repository.get_chunks(document_id)
        if not chunks:
            raise AppError(422, "NO_TEXT", "Document has no text chunks")
        self.repository.set_status(document_id, "indexing")
        try:
            vectors = self._vectors()
            for start in range(0, len(chunks), 32):
                batch = chunks[start:start + 32]
                embeddings = self.gateway.embed([chunk["content"] for chunk in batch])
                vectors.upsert(document_id, batch, embeddings)
            self.repository.set_status(document_id, "ready", chunks)
        except Exception:
            self.repository.set_status(document_id, "failed")
            raise
        return self.get_document(document_id)

    def search(self, question: str, limit: int) -> list[dict]:
        if not self.gateway.embedding_ready:
            raise AppError(503, "EMBEDDING_NOT_CONFIGURED", "Embedding API is not configured")
        vector = self.gateway.embed([question])[0]
        matches = self._vectors().search(vector, limit * 3)
        details = self.repository.matching_chunks([identifier for identifier, _ in matches])
        results = []
        for identifier, distance in matches:
            if identifier in details:
                results.append({**details[identifier], "distance": distance})
            if len(results) == limit:
                break
        return results

    def answer(self, question: str, limit: int) -> dict:
        results = self.search(question, limit)
        if not results:
            return {"answer": "未检索到可用资料，无法据此回答。", "sources": []}
        if not self.gateway.chat_ready:
            raise AppError(503, "LLM_NOT_CONFIGURED", "LLM API is not configured; use search for source passages")
        context = "\n\n".join(
            f"[{index}] {item['original_name']}，{item['page_or_section']}，"
            f"来源：{item['source_name']}，适用年份：{item['applicable_year'] or '未标注'}\n"
            f"{item['content']}"
            for index, item in enumerate(results, 1)
        )
        return {"answer": self.gateway.answer(question, context), "sources": results}

    def delete(self, document_id: int) -> None:
        document = self.repository.get_document(document_id)
        if document is None:
            raise AppError(404, "NOT_FOUND", "Knowledge document not found")
        self.repository.delete_document(document_id)
        chroma_path = self.storage_root / "chroma"
        if chroma_path.exists():
            from chromadb import PersistentClient
            from chromadb.errors import NotFoundError
            try:
                client = PersistentClient(path=str(chroma_path))
                client.get_collection("gaokao_knowledge").delete(where={"document_id": document_id})
            except NotFoundError:
                pass  # No collection was created for a pending document.
            except Exception:
                logger.exception("Unable to remove vector entries for document %s", document_id)
        Path(document["storage_path"]).unlink(missing_ok=True)

