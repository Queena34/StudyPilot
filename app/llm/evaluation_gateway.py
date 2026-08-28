import json
import re
from html import escape

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.rag.retrieval import _search_terms
from app.schemas.attempt import CriterionEvaluation, EvaluationFeedback


class EvaluationOutput(BaseModel):
    criterion_results: list[CriterionEvaluation]
    feedback: EvaluationFeedback


class AnswerEvaluationGateway:
    async def evaluate(
        self,
        *,
        question: str,
        answer: str,
        reference_answer: str,
        rubric: list[dict],
        sources: list[dict],
        include_language_feedback: bool,
    ) -> tuple[EvaluationOutput, str]:
        settings = get_settings()
        if not settings.anthropic_api_key:
            return _fallback_evaluation(answer, reference_answer, rubric), "evaluation-fallback"

        prompt = f"""Evaluate a student's answer using only the immutable rubric and sources.
Question: {escape(question)}
Student answer: {escape(answer)}
Reference answer: {escape(reference_answer)}
Rubric JSON: {json.dumps(rubric, ensure_ascii=False)}
Sources JSON: {json.dumps(sources, ensure_ascii=False)}
Include language feedback: {include_language_feedback}

Return only one JSON object with exactly this shape:
{{
  "criterion_results": [
    {{"criterion_index": 0, "earned_ratio": 0.0, "reason": "...", "evidence_ids": ["c1"]}}
  ],
  "feedback": {{
    "summary": "...",
    "covered_concepts": [],
    "missing_concepts": [],
    "knowledge_errors": [],
    "language_feedback": [],
    "recommended_topics": []
  }}
}}
criterion_results must contain exactly one entry per rubric item, in the same order.
earned_ratio is between 0 and 1. Every evidence id must come from Sources JSON.
Include every feedback field even when its value is an empty array. Do not decide a total score.

Score each rubric item on its own terms, independently of the others. A partial
answer is normal and expected: an item the answer does state earns full credit
even when the answer leaves other items unaddressed, and an item it does not
state earns zero. Do not lower a covered item because the answer is incomplete
overall — the uncovered items already carry that.
Judge only whether the item's content is present, not how briefly, how
confidently or how fluently it is put. An answer that states the point in a few
words, or hedges while stating it, has still stated it.
Judge meaning rather than wording. required_concepts name the ideas that must be
present, not phrases that must be copied: an equivalent statement of the idea
counts in full ("the expectation is zero" for "zero mean", "cannot be observed"
for "not directly observable"). A statement that merely sounds related without
conveying the idea does not count at all.
Give partial credit within a single item only when that item is itself partly
addressed, for example one of two required concepts."""
        payload = {
            "model": settings.anthropic_model,
            "max_tokens": 1800,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        }
        if "deepseek.com" in settings.anthropic_base_url:
            payload["thinking"] = {"type": "disabled"}
        for attempt in range(2):
            request_payload = dict(payload)
            if attempt:
                request_payload["messages"] = [
                    {
                        "role": "user",
                        "content": prompt
                        + "\nIMPORTANT: The previous response was invalid. Return only valid JSON, "
                        + "include every required field, and preserve the rubric item count.",
                    }
                ]
            try:
                async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
                    response = await client.post(
                        f"{settings.anthropic_base_url.rstrip('/')}/v1/messages",
                        headers={
                            "x-api-key": settings.anthropic_api_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json=request_payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                text = "".join(
                    block.get("text", "")
                    for block in data.get("content", [])
                    if block.get("type") == "text"
                )
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
                output = EvaluationOutput.model_validate(json.loads(raw))
                if len(output.criterion_results) == len(rubric):
                    return output, data.get("model", settings.anthropic_model)
            except (
                httpx.HTTPError,
                json.JSONDecodeError,
                ValidationError,
                KeyError,
                TypeError,
            ):
                continue
        return _fallback_evaluation(answer, reference_answer, rubric), "evaluation-fallback"


def _fallback_evaluation(
    answer: str, reference_answer: str, rubric: list[dict]
) -> EvaluationOutput:
    answer_terms = _search_terms(answer)
    reference_terms = _search_terms(reference_answer)
    reference_overlap = len(answer_terms & reference_terms) / max(1, min(10, len(reference_terms)))
    results: list[CriterionEvaluation] = []
    covered: list[str] = []
    missing: list[str] = []
    for index, item in enumerate(rubric):
        concepts = item.get("required_concepts", [])
        matched = [
            concept
            for concept in concepts
            if _search_terms(concept) and _search_terms(concept) <= answer_terms
        ]
        covered.extend(matched)
        missing.extend(concept for concept in concepts if concept not in matched)
        concept_ratio = len(matched) / max(1, len(concepts))
        ratio = round(min(1.0, max(concept_ratio, reference_overlap)), 4)
        results.append(
            CriterionEvaluation(
                criterion_index=index,
                earned_ratio=ratio,
                reason="根据答案对评分要点和参考资料关键词的覆盖程度计算。",
                evidence_ids=item.get("evidence_ids", []),
            )
        )
    average = sum(item.earned_ratio for item in results) / max(1, len(results))
    return EvaluationOutput(
        criterion_results=results,
        feedback=EvaluationFeedback(
            summary="答案基本覆盖评分要点。" if average >= 0.6 else "答案仍需补充关键概念。",
            covered_concepts=list(dict.fromkeys(covered)),
            missing_concepts=list(dict.fromkeys(missing)),
            knowledge_errors=[],
            language_feedback=[],
            recommended_topics=list(dict.fromkeys(missing)),
        ),
    )
