from io import BytesIO

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.core.config import get_settings
from app.knowledge.models import ModelGateway
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.main import app


def docx_bytes(text: str) -> bytes:
    document = Document()
    document.add_paragraph(text)
    output = BytesIO()
    document.save(output)
    return output.getvalue()


def pdf_bytes() -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 72 720 Td (Admission policy example) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def scanned_pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class TestGateway:
    embedding_ready = True
    chat_ready = True

    def embed(self, texts):
        return [[float("policy" in text.lower()), float("example" in text.lower()), 1.0] for text in texts]

    def answer(self, question, context):
        assert "招生政策" in context
        assert "测试来源" in context
        return "根据测试资料回答 [1]。"


@pytest.fixture
def knowledge_client(tmp_path):
    with TestClient(app) as client:
        original = client.app.state.knowledge_service
        service = KnowledgeService(
            KnowledgeRepository(client.app.state.database), ModelGateway(get_settings()),
            get_settings(), tmp_path,
        )
        client.app.state.knowledge_service = service
        created = []
        try:
            yield client, service, created
        finally:
            for document_id in created:
                if service.repository.get_document(document_id):
                    service.delete(document_id)
            client.app.state.knowledge_service = original


def upload(client, filename, content):
    return client.post(
        "/api/v1/knowledge-documents",
        data={"document_type": "policy", "source_name": "测试来源", "applicable_year": "2026"},
        files={"file": (filename, content)},
    )


def test_upload_parse_and_manage_without_api(knowledge_client):
    client, service, created = knowledge_client
    samples = [
        ("policy.txt", "招生政策\n\n  选科要求  ".encode()),
        ("charter.docx", docx_bytes("招生政策与专业介绍")),
        ("policy.pdf", pdf_bytes()),
    ]
    for filename, content in samples:
        response = upload(client, filename, content)
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        created.append(data["id"])
        assert data["ingest_status"] == "pending_embedding"
        assert data["chunk_count"] >= 1
        assert "storage_path" not in data
        assert client.get(f"/api/v1/knowledge-documents/{data['id']}").status_code == 200

    listing = client.get("/api/v1/knowledge-documents", params={"status": "pending_embedding"})
    assert listing.status_code == 200
    assert listing.json()["meta"]["total"] >= 3
    assert all("storage_path" not in item for item in listing.json()["data"])
    assert client.post("/api/v1/knowledge-search", json={"question": "招生政策"}).json()["code"] == "EMBEDDING_NOT_CONFIGURED"
    assert client.post(f"/api/v1/knowledge-documents/{created[0]}/index").status_code == 503
    invalid = upload(client, "wrong.exe", b"not a document")
    assert invalid.status_code == 422
    assert upload(client, "broken.docx", b"not a zip file").status_code == 422
    assert upload(client, "scanned.pdf", scanned_pdf_bytes()).status_code == 422
    assert client.post("/api/v1/knowledge-qa", json={"question": "   "}).status_code == 422

    deleted = created.pop()
    path = service.repository.get_document(deleted)["storage_path"]
    assert client.delete(f"/api/v1/knowledge-documents/{deleted}").status_code == 200
    assert client.get(f"/api/v1/knowledge-documents/{deleted}").status_code == 404
    from pathlib import Path
    assert not Path(path).exists()


def test_chroma_retrieval_and_grounded_answer(knowledge_client):
    client, service, created = knowledge_client
    response = upload(client, "policy.txt", "招生政策示例：选科要求为物理。".encode())
    assert response.status_code == 201
    document_id = response.json()["data"]["id"]
    created.append(document_id)

    service.gateway = TestGateway()
    service.settings.embedding_model = "test-embedding-v1"
    indexed = client.post(f"/api/v1/knowledge-documents/{document_id}/index")
    assert indexed.status_code == 200, indexed.text
    assert indexed.json()["data"]["ingest_status"] == "ready"

    search = client.post("/api/v1/knowledge-search", json={"question": "招生政策"})
    assert search.status_code == 200, search.text
    passage = search.json()["data"][0]
    assert passage["original_name"] == "policy.txt"
    assert passage["source_name"] == "测试来源"
    assert "选科要求" in passage["content"]

    answer = client.post("/api/v1/knowledge-qa", json={"question": "招生政策是什么？"})
    assert answer.status_code == 200, answer.text
    assert "[1]" in answer.json()["data"]["answer"]
    assert answer.json()["data"]["sources"][0]["document_id"] == document_id

    assert client.delete(f"/api/v1/knowledge-documents/{document_id}").status_code == 200
    created.remove(document_id)
    assert service._vectors().collection.count() == 0
    assert client.post("/api/v1/knowledge-search", json={"question": "招生政策"}).json()["data"] == []

