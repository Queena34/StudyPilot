"""Language detection for course material and learner questions.

Retrieval only works when the query is in the same language as the material, so
both sides have to be identified. The rule is a character-class ratio rather than
a model: it needs to be cheap enough to run on every chunk at ingestion and every
question at routing, and its failure modes need to be obvious.
"""

import re

#: Above this share of CJK characters the text is treated as Chinese. Technical
#: material mixes in English terms freely, so the bar is deliberately low.
CJK_RATIO_THRESHOLD = 0.10

_CJK = re.compile(r"[㐀-鿿]")
_LETTER = re.compile(r"[A-Za-z㐀-鿿]")


def detect_language(text: str) -> str:
    """Returns `zh` or `en`. Defaults to `en` when there is nothing to judge."""

    letters = _LETTER.findall(text or "")
    if not letters:
        return "en"
    cjk = len(_CJK.findall(text))
    return "zh" if cjk / len(letters) >= CJK_RATIO_THRESHOLD else "en"


def dominant_language(texts: list[str]) -> str:
    """The language of a body of material, weighted by how much text each carries.

    A single Chinese slide in an English deck should not flip the whole document.
    """

    if not texts:
        return "en"
    zh = sum(len(item) for item in texts if detect_language(item) == "zh")
    total = sum(len(item) for item in texts) or 1
    return "zh" if zh / total >= 0.5 else "en"
