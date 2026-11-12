from urllib.parse import urlparse

import httpx

from app.api.responses import AppError
from app.core.config import Settings


class ModelGateway:
    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def embedding_ready(self) -> bool:
        return all((self.settings.embedding_api_base_url, self.settings.embedding_api_key, self.settings.embedding_model))

    @property
    def chat_ready(self) -> bool:
        return all((self.settings.llm_api_base_url, self.settings.llm_api_key, self.settings.llm_model))

    def _post(self, base_url: str, key: str, endpoint: str, payload: dict) -> dict:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError(503, "MODEL_NOT_CONFIGURED", "Model API base URL is invalid")
        try:
            with httpx.Client(timeout=30) as client:
                response = client.post(
                    f"{base_url.rstrip('/')}/{endpoint}",
                    headers={"Authorization": f"Bearer {key}"}, json=payload,
                )
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AppError(502, "MODEL_API_ERROR", "Model API request failed") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.embedding_ready:
            raise AppError(503, "EMBEDDING_NOT_CONFIGURED", "Embedding API is not configured")
        result = self._post(
            self.settings.embedding_api_base_url, self.settings.embedding_api_key,
            "embeddings", {"model": self.settings.embedding_model, "input": texts},
        )
        try:
            entries = sorted(result["data"], key=lambda item: item["index"])
            vectors = [entry["embedding"] for entry in entries]
            if len(vectors) != len(texts) or any(not vector for vector in vectors):
                raise ValueError("incomplete embeddings")
            return vectors
        except (KeyError, TypeError, ValueError) as exc:
            raise AppError(502, "MODEL_API_ERROR", "Embedding API returned invalid data") from exc

    def answer(self, question: str, context: str) -> str:
        if not self.chat_ready:
            raise AppError(503, "LLM_NOT_CONFIGURED", "LLM API is not configured")
        result = self._post(
            self.settings.llm_api_base_url, self.settings.llm_api_key,
            "chat/completions",
            {"model": self.settings.llm_model, "temperature": 0,
             "messages": [
                 {"role": "system", "content": "仅根据提供的资料回答高考招生政策或专业问题。资料不足时明确说无法据此回答。不要承诺录取结果，并在相关陈述后引用资料编号。"},
                 {"role": "user", "content": f"资料：\n{context}\n\n问题：{question}"},
             ]},
        )
        try:
            content = result["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("empty answer")
            return content.strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AppError(502, "MODEL_API_ERROR", "LLM API returned invalid data") from exc

