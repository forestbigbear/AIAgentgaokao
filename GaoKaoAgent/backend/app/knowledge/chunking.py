from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str
    page_or_section: str


def split_sections(sections: list[tuple[str, str]], size: int = 800, overlap: int = 120) -> list[TextChunk]:
    if size <= overlap or overlap < 0:
        raise ValueError("chunk size must exceed overlap")
    chunks: list[TextChunk] = []
    for label, text in sections:
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                boundary = max(text.rfind("\n", start + size // 2, end), text.rfind("。", start + size // 2, end))
                if boundary > start:
                    end = boundary + 1
            segment = text[start:end].strip()
            if segment:
                chunks.append(TextChunk(len(chunks), segment, label))
            if end == len(text):
                break
            start = max(start + 1, end - overlap)
    return chunks

