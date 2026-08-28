import re
from collections import Counter
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.rag.embeddings import get_embedding
from app.rag.sections import chapter_number as _chapter_number
from app.rag.types import RetrievedEvidence


class CourseRetriever:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = f"http://{settings.chroma_host}:{settings.chroma_port}/api/v1"
        self.collection_name = settings.chroma_collection
        self.embedding = get_embedding()

    async def retrieve(
        self,
        *,
        user_id: UUID,
        course_id: UUID,
        query: str,
        top_k: int,
        document_types: list[str] | None = None,
        document_ids: list[UUID] | None = None,
        page_from: int | None = None,
        page_to: int | None = None,
        section: int | None = None,
    ) -> list[RetrievedEvidence]:
        where = _where_filter(
            section=section,
            user_id=user_id,
            course_id=course_id,
            document_types=document_types,
            document_ids=document_ids,
            page_from=page_from,
            page_to=page_to,
        )
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                collection_response = await client.get(
                    f"{self.base_url}/collections/{self.collection_name}"
                )
                if collection_response.status_code == 404:
                    return []
                collection_response.raise_for_status()
                collection_id = collection_response.json()["id"]
                # A named section is now part of the metadata filter rather than a
                # separate scan of the whole collection: sections are assigned at
                # ingestion, so retrieval is an ordinary filtered query.
                response = await client.post(
                    f"{self.base_url}/collections/{collection_id}/query",
                    json={
                        "query_embeddings": self.embedding.embed([query]),
                        "n_results": min(max(top_k * 3, top_k), 30),
                        "where": where,
                        "include": ["documents", "metadatas", "distances"],
                    },
                )
                response.raise_for_status()
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise AppError(
                "RETRIEVAL_UNAVAILABLE",
                "课程知识库暂时不可用，请稍后重试",
                status_code=503,
            ) from exc

        payload = response.json()
        ids = (payload.get("ids") or [[]])[0]
        documents = (payload.get("documents") or [[]])[0]
        metadatas = (payload.get("metadatas") or [[]])[0]
        distances = (payload.get("distances") or [[]])[0]
        query_terms = _search_terms(query)
        evidence: list[RetrievedEvidence] = []
        for chunk_id, text, metadata, distance in zip(
            ids, documents, metadatas, distances, strict=False
        ):
            if not text or not metadata:
                continue
            vector_score = max(0.0, 1.0 - float(distance))
            terms = _search_terms(text)
            lexical_score = len(query_terms & terms) / max(1, len(query_terms))
            score = 0.7 * vector_score + 0.3 * lexical_score
            evidence.append(
                RetrievedEvidence(
                    chunk_id=chunk_id,
                    document_id=metadata["document_id"],
                    filename=metadata["source_file"],
                    page_number=int(metadata["page_number"]),
                    # The detected section name is authoritative; the parser's
                    # per-page guess is only a fallback for material indexed
                    # before sections existed.
                    section_title=metadata.get("section_name")
                    or metadata.get("section_title"),
                    text=text,
                    score=score,
                )
            )
        evidence.sort(key=lambda item: item.score, reverse=True)
        return evidence[:top_k]


def _where_filter(
    *,
    section: int | None = None,
    user_id: UUID,
    course_id: UUID,
    document_types: list[str] | None,
    document_ids: list[UUID] | None,
    page_from: int | None,
    page_to: int | None,
) -> dict:
    conditions: list[dict] = [
        {"user_id": str(user_id)},
        {"course_id": str(course_id)},
    ]
    if document_types:
        conditions.append({"document_type": {"$in": document_types}})
    if document_ids:
        conditions.append({"document_id": {"$in": [str(item) for item in document_ids]}})
    if section is not None:
        conditions.append({"section_index": section})
    if page_from is not None:
        conditions.append({"page_number": {"$gte": page_from}})
    if page_to is not None:
        conditions.append({"page_number": {"$lte": page_to}})
    return {"$and": conditions}


def _search_terms(text: str) -> set[str]:
    lowered = text.lower()
    terms = set(re.findall(r"[a-z0-9_-]+", lowered))
    terms.update(re.findall(r"[\u3400-\u9fff]", lowered))
    return terms
