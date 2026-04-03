import numpy as np
import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)


class EmbeddingService:
    """Generates vector embeddings for text chunks using sentence-transformers."""

    def __init__(self):
        self._model = None
        self._settings = get_settings()

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info("loading_embedding_model", model=self._settings.embedding_model)
            self._model = SentenceTransformer(self._settings.embedding_model)
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        model = self._get_model()
        embeddings = model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return embeddings.tolist()

    async def embed_single(self, text: str) -> list[float]:
        results = await self.embed_texts([text])
        return results[0] if results else []

    async def compute_similarity(self, embedding1: list[float], embedding2: list[float]) -> float:
        a = np.array(embedding1)
        b = np.array(embedding2)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
