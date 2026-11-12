from pathlib import Path

import chromadb

from app.api.responses import AppError


class VectorStore:
    def __init__(self, path: Path, model_name: str):
        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(
            name="gaokao_knowledge", metadata={"embedding_model": model_name}
        )
        configured = (self.collection.metadata or {}).get("embedding_model")
        if configured != model_name:
            if self.collection.count():
                raise AppError(409, "EMBEDDING_MODEL_MISMATCH", "Chroma collection uses a different embedding model")
            self.collection.modify(metadata={"embedding_model": model_name})

    def upsert(self, document_id: int, chunks: list[dict], vectors: list[list[float]]) -> None:
        self.collection.upsert(
            ids=[f"document-{document_id}-chunk-{chunk['chunk_index']}" for chunk in chunks],
            embeddings=vectors,
            documents=[chunk["content"] for chunk in chunks],
            metadatas=[{"document_id": document_id, "page_or_section": chunk["page_or_section"]} for chunk in chunks],
        )

    def search(self, vector: list[float], limit: int) -> list[tuple[str, float]]:
        result = self.collection.query(query_embeddings=[vector], n_results=limit, include=["distances"])
        return list(zip(result["ids"][0], result["distances"][0]))

    def delete(self, document_id: int) -> None:
        self.collection.delete(where={"document_id": document_id})
