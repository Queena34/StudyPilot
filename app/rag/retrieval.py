import re
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.rag.embeddings import HashEmbedding
from app.rag.types import RetrievedEvidence


class CourseRetriever:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = f"http://{settings.chroma_host}:{settings.chroma_port}/api/v1"
        self.collection_name = settings.chroma_collection
        self.embedding = HashEmbedding()

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
    ) -> list[RetrievedEvidence]:
        where = _where_filter(
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
                chapter_number = _chapter_number(query)
                if chapter_number is not None and document_ids:
                    chapter_response = await client.post(
                        f"{self.base_url}/collections/{collection_id}/get",
                        json={"where": where, "include": ["documents", "metadatas"]},
                    )
                    chapter_response.raise_for_status()
                    chapter_evidence = _chapter_evidence(
                        chapter_response.json(), chapter_number, top_k
                    )
                    if chapter_evidence:
                        return chapter_evidence
                    return []
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
                    section_title=metadata.get("section_title"),
                    text=text,
                    score=score,
                )
            )
        evidence.sort(key=lambda item: item.score, reverse=True)
        return evidence[:top_k]


def _where_filter(
    *,
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


_CHINESE_NUMBERS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def _chapter_number(query: str) -> int | None:
    match = re.search(r"(?:第\s*([一二三四五六七八九十零〇0-9]+)\s*章|chapter\s*([0-9]+))", query, re.I)
    if not match:
        return None
    value = match.group(1) or match.group(2)
    if value.isdigit():
        return int(value)
    if value in _CHINESE_NUMBERS:
        return _CHINESE_NUMBERS[value]
    if value.startswith("十"):
        return 10 + _CHINESE_NUMBERS.get(value[1:], 0)
    if "十" in value:
        tens, ones = value.split("十", 1)
        return _CHINESE_NUMBERS.get(tens, 1) * 10 + _CHINESE_NUMBERS.get(ones, 0)
    return None


def _chapter_marker(text: str, section_title: str | None = None) -> tuple[int, str] | None:
    searchable = f"{section_title}\n{text}" if section_title else text
    match = re.search(r"(?im)^\s*(?:chapter|section|unit|module)\s+([0-9]+)\s*[.:：-]?\s*([^\n]{0,120})", searchable)
    if match:
        title = f"Chapter {match.group(1)}"
        if match.group(2).strip():
            title += f". {match.group(2).strip()}"
        return int(match.group(1)), " ".join(title.split())
    match = re.search(r"(?m)^\s*第\s*([一二三四五六七八九十零〇0-9]+)\s*章([^\n]{0,120})", searchable)
    if match:
        number = _chapter_number(f"第{match.group(1)}章")
        if number is not None:
            return number, " ".join(match.group(0).split())
    for line in searchable.splitlines()[:12]:
        match = re.fullmatch(
            r"\s*([0-9]{1,2})(?:[.、:：]\s*|\s+)([A-Za-z\u3400-\u9fff][^\n]{2,100})\s*",
            line,
        )
        if match:
            return int(match.group(1)), " ".join(match.group(0).split())
    return None


def _chapter_evidence(payload: dict, target: int, top_k: int) -> list[RetrievedEvidence]:
    rows = []
    for chunk_id, text, metadata in zip(
        payload.get("ids") or [], payload.get("documents") or [], payload.get("metadatas") or [], strict=False
    ):
        if text and metadata:
            rows.append((chunk_id, text, metadata))
    selected: list[tuple[str, str, dict, str]] = []
    by_document: dict[str, list[tuple[str, str, dict]]] = {}
    for row in rows:
        by_document.setdefault(row[2]["document_id"], []).append(row)
    for document_rows in by_document.values():
        document_rows.sort(key=lambda row: int(row[2].get("chunk_index", 0)))
        markers = [_chapter_marker(row[1], row[2].get("section_title")) for row in document_rows]
        if target == 1 and not any(markers):
            selected.extend((*row, "第一部分（原文未标注章节）") for row in document_rows)
            continue
        active = False
        section_title = f"Chapter {target}"
        for row in document_rows:
            marker = _chapter_marker(row[1], row[2].get("section_title"))
            if marker:
                if marker[0] == target:
                    active = True
                    section_title = marker[1]
                elif active:
                    break
            if active:
                selected.append((*row, section_title))
    if not selected:
        return []
    limit = min(top_k, len(selected))
    indexes = sorted({round(index * (len(selected) - 1) / max(1, limit - 1)) for index in range(limit)})
    return [
        RetrievedEvidence(
            chunk_id=selected[index][0],
            document_id=selected[index][2]["document_id"],
            filename=selected[index][2]["source_file"],
            page_number=int(selected[index][2]["page_number"]),
            section_title=selected[index][3],
            text=selected[index][1],
            score=round(0.95 - position * 0.03, 4),
        )
        for position, index in enumerate(indexes)
    ]
