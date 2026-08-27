"""Translate a learner's question into the language of their material.

Retrieval compares a query against passages in one vector space, and an
English-tuned model places a Chinese question nowhere near the English passage
that answers it. Rather than accept a weaker multilingual model, the query is
moved into the material's language first, which also lets the retriever use a
model built for retrieval instead of for sentence similarity.

Only the retrieval query is translated. What the learner reads is still produced
in the language they chose.
"""

import logging

import httpx

from app.core.config import get_settings
from app.rag.language import detect_language

logger = logging.getLogger(__name__)

_TARGET_NAMES = {"en": "English", "zh": "Simplified Chinese"}

_PROMPT = """Translate this study question into {target}, for use as a search query
over course material written in {target}.

Keep technical terms, symbols, formulas, chapter and page references exactly as a
textbook in {target} would write them. Do not answer the question, do not explain
it, and do not add anything. Return only the translated question.

Question: {question}"""


class QueryTranslationGateway:
    """Returns the query unchanged whenever translation is unnecessary or fails.

    Retrieval degrading to the original wording is always better than a turn that
    errors out, so every failure path returns the input.
    """

    async def to_material_language(self, query: str, material_language: str) -> str:
        target = _TARGET_NAMES.get(material_language)
        if target is None or detect_language(query) == material_language:
            return query

        settings = get_settings()
        if not settings.anthropic_api_key:
            return query

        payload = {
            "model": settings.anthropic_model,
            "max_tokens": 300,
            "temperature": 0,
            "messages": [
                {"role": "user", "content": _PROMPT.format(target=target, question=query[:1000])}
            ],
        }
        if "deepseek.com" in settings.anthropic_base_url:
            payload["thinking"] = {"type": "disabled"}
        try:
            async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                response = await client.post(
                    f"{settings.anthropic_base_url.rstrip('/')}/v1/messages",
                    headers={
                        "x-api-key": settings.anthropic_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            logger.warning("query translation failed (%s); using the original", type(error).__name__)
            return query

        translated = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
        # A model that returned nothing, or answered in the wrong language, is no
        # better than the original query.
        if not translated or detect_language(translated) != material_language:
            return query
        return translated[:1000]
