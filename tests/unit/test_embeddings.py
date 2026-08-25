import math

from app.rag.embeddings import HashEmbedding


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    embedding = HashEmbedding(dimensions=32)

    first, second = embedding.embed(["retrieval augmented generation"] * 2)

    assert first == second
    assert len(first) == 32
    assert math.isclose(sum(value * value for value in first), 1.0)


def test_empty_text_produces_zero_vector() -> None:
    assert HashEmbedding(dimensions=8).embed([""])[0] == [0.0] * 8
