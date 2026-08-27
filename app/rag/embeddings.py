"""Text embeddings for course material retrieval.

Two implementations behind one interface. `DenseEmbedding` is what runs in
production: a retrieval-tuned English model, chosen because course material is
retrieved in its own language and queries are translated into that language
before they reach here (see `app/agents/query_translation.py`). `HashEmbedding`
is a deterministic fallback with no model download, used by tests and by any
deployment that cannot fetch the model.

The hash embedding cannot match across languages — a Chinese question and an
English passage share almost no tokens, so its scores sit at the noise floor.
That was the system's behaviour until the dense model replaced it; it remains
useful only where determinism matters more than retrieval quality.
"""

from functools import lru_cache
import hashlib
import logging
import math
import os
import re

logger = logging.getLogger(__name__)

#: Retrieval-tuned, 384 dimensions, ~67 MB. Small enough to bake into the image.
DENSE_MODEL_NAME = "BAAI/bge-small-en-v1.5"
DENSE_DIMENSIONS = 384


class HashEmbedding:
    """Deterministic local baseline. No semantics, no model, no network."""

    def __init__(self, dimensions: int = DENSE_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector


class DenseEmbedding:
    """Sentence-transformer embeddings served through ONNX, no torch required."""

    def __init__(self, model_name: str = DENSE_MODEL_NAME) -> None:
        self.model_name = model_name
        self.dimensions = DENSE_DIMENSIONS

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [list(map(float, vector)) for vector in _model(self.model_name).embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]


@lru_cache(maxsize=2)
def _model(model_name: str):
    from fastembed import TextEmbedding

    # The image bakes the model at this path so a container never downloads at
    # runtime; outside Docker fastembed falls back to its own cache directory.
    return TextEmbedding(model_name=model_name, cache_dir=os.getenv("FASTEMBED_CACHE_PATH") or None)


@lru_cache(maxsize=1)
def get_embedding():
    """The dense model when it can be loaded, the hash baseline otherwise.

    A deployment without the model must still start and serve; it degrades to
    keyword-grade retrieval rather than failing, and says so in the log.
    """

    try:
        embedding = DenseEmbedding()
        embedding.embed(["warmup"])
        return embedding
    except Exception as error:  # noqa: BLE001 - any load failure degrades the same way
        logger.warning(
            "dense embedding unavailable (%s); falling back to hash embedding, "
            "cross-language retrieval will not work",
            type(error).__name__,
        )
        return HashEmbedding()


def _tokens(text: str) -> list[str]:
    normalized = text.lower()
    latin = re.findall(r"[a-z0-9_-]+", normalized)
    cjk_runs = re.findall(r"[㐀-鿿]+", normalized)
    cjk: list[str] = []
    for run in cjk_runs:
        cjk.extend(run)
        cjk.extend(run[index : index + 2] for index in range(len(run) - 1))
    return latin + cjk
