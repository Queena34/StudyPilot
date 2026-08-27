"""Keep the implementation spec honest.

A specification that drifts from the code is worse than none: it is read as
authoritative while being wrong. These checks pin the few claims that go stale
fastest — the constants a reader would copy, and the counts they would quote.
"""

from pathlib import Path
import re

from app.agents.presenters import CITATION_SNIPPET_LIMIT
from app.core.config import Settings
from app.rag.chunking import TextChunker
from app.rag.embeddings import DENSE_DIMENSIONS, DENSE_MODEL_NAME
from app.rag.language import CJK_RATIO_THRESHOLD

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs/ARCHITECTURE.md"
PAGE = ROOT / "docs/architecture.html"


def _spec() -> str:
    return SPEC.read_text(encoding="utf-8")


def test_the_spec_quotes_the_real_constants() -> None:
    text = _spec()
    chunker = TextChunker()

    assert f"max_chars={chunker.max_chars}" in text
    assert f"overlap_chars={chunker.overlap_chars}" in text
    assert DENSE_MODEL_NAME in text
    assert f"{DENSE_DIMENSIONS} 维" in text
    assert f"{int(CJK_RATIO_THRESHOLD * 100)}%" in text
    assert f"CITATION_SNIPPET_LIMIT = {CITATION_SNIPPET_LIMIT}" in text
    assert Settings().chroma_collection in text


def test_the_spec_counts_the_migrations_it_claims() -> None:
    revisions = sorted(
        path.name.split("_")[0]
        for path in (ROOT / "migrations/versions").glob("[0-9]*.py")
    )

    assert f"迁移 0001–{revisions[-1]}" in _spec()


def test_the_spec_counts_the_evaluation_suites_it_claims() -> None:
    # router_v1 is kept for historical comparison; v2 supersedes it as a suite.
    superseded = {"router_v1.json"}
    suites = [
        path
        for path in (ROOT / "tests/evals/baselines").glob("*.json")
        if path.name not in superseded
    ]
    claimed = re.search(r"(\d+) 套离线评测", _spec())

    assert claimed, "规模一行应写明离线评测套数"
    assert int(claimed.group(1)) == len(suites)


def test_the_spec_names_every_module_it_describes() -> None:
    text = _spec()

    for module in (
        "app/agents/query_translation.py",
        "app/rag/language.py",
        "app/tasks/reindex.py",
    ):
        assert (ROOT / module).exists(), f"{module} 不存在"
        assert Path(module).name in text, f"{module} 未出现在说明书中"


def test_the_web_version_tracks_the_markdown() -> None:
    page = PAGE.read_text(encoding="utf-8")

    # The two are separate files, so the facts that appear in both must agree.
    assert DENSE_MODEL_NAME in page
    assert f"max_chars={TextChunker().max_chars}" in page
    for heading in ("引用校验与修复重试", "跨语言检索"):
        assert heading in page, f"网页版缺少「{heading}」一节"
