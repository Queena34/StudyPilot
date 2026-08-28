"""Detect how a document divides itself into parts.

Learners study and ask by chapter, but material expresses that structure in
whatever way its format happens to use. A textbook writes "Chapter 3."; a Beamer
handout has no numbers at all and starts each deck with a title slide carrying
the author and institution; Markdown uses headings. Modelling only numbered
chapters left a slide deck with no structure at all, so a `Section` is an ordered,
titled part of one document. Its index is the number the document claims for
itself where it states one — a textbook opening on Chapter 0 must still answer
"第一章" with Chapter 1 — and its position in the document otherwise.

Detectors are tried in order of how much they can be trusted. When none applies
the document is one section, which is stated rather than guessed at: inventing
structure is what buried a real chapter under an alcohol experiment.
"""

from dataclasses import dataclass
import re

from app.rag.types import ParsedDocument, ParsedPage


@dataclass(frozen=True)
class Section:
    index: int
    title: str
    page_from: int
    page_to: int

    def as_dict(self) -> dict:
        return {
            "index": self.index,
            "title": self.title,
            "page_from": self.page_from,
            "page_to": self.page_to,
        }


#: A section must span at least this many pages to be believed, so a stray line
#: that merely looks like a heading cannot become one.
MIN_SECTION_PAGES = 1

_EXPLICIT_HEADING = re.compile(
    r"(?im)^\s*((?:chapter|section|unit|module)\s+(\d+)\s*[.:：-]?\s*[^\n]{0,120})$"
)
_CJK_HEADING = re.compile(r"(?m)^\s*(第\s*([一二三四五六七八九十百零〇0-9]+)\s*章[^\n]{0,120})$")
_MARKDOWN_HEADING = re.compile(r"(?m)^(#{1,3})\s+(.+)$")

#: A title slide repeats the same author and affiliation lines across a deck, so
#: the pair is discovered from the document rather than hard-coded.
_AFFILIATION = re.compile(
    r"(?im)^\s*((?:[A-Z][\w.'’-]+\s+){0,3}(?:university|universiteit|université|institute|college|school)[^\n]{0,60})$"
)


def detect_sections(document: ParsedDocument) -> list[Section]:
    """The document's own parts, or one section covering all of it."""

    for detector in (_explicit_chapters, _title_slides, _markdown_headings):
        sections = detector(document)
        if len(sections) > 1:
            return sections
    pages = document.pages
    if not pages:
        return []
    return [Section(1, "全文", pages[0].page_number, pages[-1].page_number)]


def _explicit_chapters(document: ParsedDocument) -> list[Section]:
    """Headings that name themselves: `Chapter 3. Inference`, `第三章 统计推断`."""

    starts: list[tuple[int, str]] = []
    for page in document.pages:
        title = _first_explicit_heading(page.text)
        if title and (not starts or starts[-1][1] != title):
            starts.append((page.page_number, title))
    # A textbook that numbers its own chapters is the authority on those numbers:
    # "第一章" must reach Chapter 1 even when the book opens with a Chapter 0.
    return _to_sections(starts, document.pages, numbered=True)


def _title_slides(document: ParsedDocument) -> list[Section]:
    """Deck boundaries in a slide handout, found by the repeated affiliation line.

    A Beamer title slide reads: deck title, author, institution. The institution
    line recurs on every deck's first slide and almost nowhere else, which makes
    it a reliable boundary without knowing the author's name in advance.
    """

    affiliations: dict[str, int] = {}
    for page in document.pages:
        for match in _AFFILIATION.finditer(page.text):
            key = " ".join(match.group(1).split())
            affiliations[key] = affiliations.get(key, 0) + 1
    if not affiliations:
        return []
    affiliation, occurrences = max(affiliations.items(), key=lambda item: item[1])
    if occurrences < 2:
        return []

    starts: list[tuple[int, str]] = []
    for page in document.pages:
        for title in _titles_above(page.text, affiliation):
            starts.append((page.page_number, title))
    # Several decks can begin on one handout page, so keep only the first per page.
    deduped: list[tuple[int, str]] = []
    for page_number, title in starts:
        if not deduped or deduped[-1][0] != page_number:
            deduped.append((page_number, title))
    return _to_sections(deduped, document.pages)


def _markdown_headings(document: ParsedDocument) -> list[Section]:
    if len(document.pages) != 1:
        return []
    text = document.pages[0].text
    titles = [
        " ".join(match.group(2).split())
        for match in _MARKDOWN_HEADING.finditer(text)
        if len(match.group(1)) <= 2
    ]
    page = document.pages[0].page_number
    return [
        Section(index, title, page, page) for index, title in enumerate(titles, start=1)
    ]


def _titles_above(text: str, affiliation: str) -> list[str]:
    """The line two above the affiliation: title, author, institution."""

    lines = [line.strip() for line in text.splitlines()]
    found = []
    for index, line in enumerate(lines):
        if " ".join(line.split()) == affiliation and index >= 2:
            candidate = " ".join(lines[index - 2].split())
            if 3 <= len(candidate) <= 120:
                found.append(candidate)
    return found


def _first_explicit_heading(text: str) -> str | None:
    for pattern in (_EXPLICIT_HEADING, _CJK_HEADING):
        match = pattern.search(text)
        if match:
            return " ".join(match.group(1).split())
    return None


def _to_sections(
    starts: list[tuple[int, str]],
    pages: list[ParsedPage],
    *,
    numbered: bool = False,
) -> list[Section]:
    """Turn heading positions into sections spanning the pages between them.

    With `numbered`, a heading that states its own chapter number keeps it; the
    ordinal position is only the fallback for material that numbers nothing.
    """

    if len(starts) < 2:
        return []
    last_page = pages[-1].page_number
    sections: list[Section] = []
    for position, (page_number, title) in enumerate(starts, start=1):
        page_to = starts[position][0] - 1 if position < len(starts) else last_page
        if page_to - page_number + 1 < MIN_SECTION_PAGES:
            continue
        claimed = chapter_number(title) if numbered else None
        index = claimed if claimed is not None else len(sections) + 1
        sections.append(Section(index, title, page_number, page_to))
    return sections if len(sections) > 1 else []


def section_for_page(sections: list[Section], page_number: int) -> Section | None:
    for section in sections:
        if section.page_from <= page_number <= section.page_to:
            return section
    return None


_CHINESE_NUMBERS = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def chapter_number(text: str) -> int | None:
    """The chapter number a piece of text names, in either language."""

    match = re.search(r"(?:第\s*([一二三四五六七八九十零〇0-9]+)\s*章|chapter\s*([0-9]+))", text, re.I)
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
