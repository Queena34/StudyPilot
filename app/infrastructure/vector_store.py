from uuid import UUID

from app.core.config import get_settings
from app.rag.embeddings import HashEmbedding
from app.rag.types import TextChunk


class CourseVectorStore:
    def __init__(self) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError("Install requirements-rag.txt for vector indexing") from exc
        settings = get_settings()
        client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port)
        self.collection = client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine", "schema_version": 1},
        )
        self.embedding = HashEmbedding()

    def add_document(
        self,
        *,
        user_id: UUID,
        course_id: UUID,
        document_id: UUID,
        filename: str,
        document_type: str,
        chunks: list[TextChunk],
    ) -> None:
        embeddings = self.embedding.embed([chunk.text for chunk in chunks])
        for start in range(0, len(chunks), 100):
            batch = chunks[start : start + 100]
            metadata = []
            for chunk in batch:
                item = {
                    "user_id": str(user_id),
                    "course_id": str(course_id),
                    "document_id": str(document_id),
                    "document_type": document_type,
                    "source_file": filename,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "schema_version": 1,
                }
                if chunk.section_title:
                    item["section_title"] = chunk.section_title
                metadata.append(item)
            self.collection.add(
                ids=[f"{document_id}:{chunk.chunk_index}" for chunk in batch],
                documents=[chunk.text for chunk in batch],
                embeddings=embeddings[start : start + 100],
                metadatas=metadata,
            )

    def delete_document(self, document_id: UUID) -> None:
        self.collection.delete(where={"document_id": str(document_id)})

    def count_document_chunks(self, document_id: UUID) -> int:
        result = self.collection.get(where={"document_id": str(document_id)}, include=[])
        return len(result.get("ids", []))

