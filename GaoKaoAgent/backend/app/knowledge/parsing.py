import re
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile

from docx import Document
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.api.responses import AppError


ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def clean_text(value: str) -> str:
    value = value.replace("\x00", "").replace("\u00a0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line).strip())


def parse_document(filename: str, content: bytes) -> list[tuple[str, str]]:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError(422, "UNSUPPORTED_FILE", "Only PDF, DOCX and TXT files are supported")
    try:
        if extension == ".txt":
            sections = [("全文", content.decode("utf-8-sig"))]
        elif extension == ".docx":
            doc = Document(BytesIO(content))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    paragraphs.append(" | ".join(cell.text for cell in row.cells))
            sections = [("正文", "\n".join(paragraphs))]
        else:
            if not content.startswith(b"%PDF-"):
                raise ValueError("invalid PDF signature")
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted:
                raise ValueError("encrypted PDF")
            sections = [(f"第 {index} 页", page.extract_text() or "") for index, page in enumerate(reader.pages, 1)]
    except (UnicodeError, ValueError, OSError, KeyError, TypeError, BadZipFile, PdfReadError) as exc:
        raise AppError(422, "PARSE_FAILED", f"Cannot parse {extension[1:].upper()} document") from exc

    cleaned = [(label, clean_text(text)) for label, text in sections]
    cleaned = [(label, text) for label, text in cleaned if text]
    if not cleaned:
        raise AppError(422, "NO_TEXT", "Document has no extractable text; scanned PDFs require OCR")
    return cleaned

