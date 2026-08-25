from app.rag.chunking import TextChunker
from app.rag.types import ParsedDocument, ParsedPage


def test_chunker_preserves_page_and_section_metadata() -> None:
    document = ParsedDocument(
        [
            ParsedPage(1, "# Introduction\n\nFirst concept.", "Introduction"),
            ParsedPage(2, "Second concept.", "Chapter 2"),
        ]
    )

    chunks = TextChunker(max_chars=80, overlap_chars=10).split(document)

    assert [chunk.chunk_index for chunk in chunks] == [0, 1]
    assert [chunk.page_number for chunk in chunks] == [1, 2]
    assert [chunk.section_title for chunk in chunks] == ["Introduction", "Chapter 2"]


def test_chunker_never_exceeds_configured_size() -> None:
    document = ParsedDocument([ParsedPage(1, "a" * 45 + "\n\n" + "b" * 45)])

    chunks = TextChunker(max_chars=50, overlap_chars=20).split(document)

    assert len(chunks) == 2
    assert all(len(chunk.text) <= 50 for chunk in chunks)


def test_chunker_windows_oversized_paragraph_with_overlap() -> None:
    document = ParsedDocument([ParsedPage(1, "abcdefghij")])

    chunks = TextChunker(max_chars=6, overlap_chars=2).split(document)

    assert [chunk.text for chunk in chunks] == ["abcdef", "efghij", "ij"]
