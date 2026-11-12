from app.db.connection import Database


class KnowledgeRepository:
    def __init__(self, database: Database):
        self.database = database

    def create_document(self, data: dict, chunks: list) -> int:
        with self.database.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO knowledge_documents "
                "(original_name, file_type, storage_path, document_type, source_name, source_url, "
                "applicable_region, applicable_year, published_at, ingest_status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending_embedding')",
                (data["original_name"], data["file_type"], data["storage_path"],
                 data["document_type"], data["source_name"], data["source_url"],
                 data["applicable_region"], data["applicable_year"], data["published_at"]),
            )
            document_id = cursor.lastrowid
            cursor.executemany(
                "INSERT INTO knowledge_chunks (document_id, chunk_index, content, page_or_section) "
                "VALUES (%s, %s, %s, %s)",
                [(document_id, chunk.index, chunk.content, chunk.page_or_section) for chunk in chunks],
            )
            return document_id

    def get_document(self, document_id: int) -> dict | None:
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM knowledge_documents AS d "
                "LEFT JOIN knowledge_chunks AS c ON c.document_id = d.id "
                "WHERE d.id = %s GROUP BY d.id", (document_id,),
            )
            return cursor.fetchone()

    def list_documents(self, page: int, page_size: int, status: str | None) -> tuple[list[dict], int]:
        where = " WHERE d.ingest_status = %s" if status else ""
        params = (status,) if status else ()
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS total FROM knowledge_documents AS d{where}", params)
            total = cursor.fetchone()["total"]
            cursor.execute(
                "SELECT d.*, COUNT(c.id) AS chunk_count FROM knowledge_documents AS d "
                "LEFT JOIN knowledge_chunks AS c ON c.document_id = d.id" + where +
                " GROUP BY d.id ORDER BY d.id DESC LIMIT %s OFFSET %s",
                (*params, page_size, (page - 1) * page_size),
            )
            return cursor.fetchall(), total

    def get_chunks(self, document_id: int) -> list[dict]:
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT chunk_index, content, page_or_section FROM knowledge_chunks "
                "WHERE document_id = %s ORDER BY chunk_index", (document_id,),
            )
            return cursor.fetchall()

    def set_status(self, document_id: int, status: str, chunks: list[dict] | None = None) -> None:
        with self.database.transaction() as connection, connection.cursor() as cursor:
            if chunks is not None:
                cursor.executemany(
                    "UPDATE knowledge_chunks SET chroma_id = %s WHERE document_id = %s AND chunk_index = %s",
                    [(f"document-{document_id}-chunk-{chunk['chunk_index']}", document_id,
                      chunk["chunk_index"]) for chunk in chunks],
                )
            cursor.execute(
                "UPDATE knowledge_documents SET ingest_status = %s WHERE id = %s",
                (status, document_id),
            )

    def matching_chunks(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        placeholders = ", ".join(["%s"] * len(ids))
        with self.database.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT c.chroma_id, c.content, c.page_or_section, d.id AS document_id, "
                "d.original_name, d.source_name, d.source_url, d.applicable_region, "
                "d.applicable_year, d.published_at, d.document_type "
                "FROM knowledge_chunks AS c JOIN knowledge_documents AS d ON d.id = c.document_id "
                f"WHERE d.ingest_status = %s AND c.chroma_id IN ({placeholders})",
                ("ready", *ids),
            )
            return {row["chroma_id"]: row for row in cursor.fetchall()}

    def delete_document(self, document_id: int) -> None:
        with self.database.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("DELETE FROM knowledge_chunks WHERE document_id = %s", (document_id,))
            cursor.execute("DELETE FROM knowledge_documents WHERE id = %s", (document_id,))

