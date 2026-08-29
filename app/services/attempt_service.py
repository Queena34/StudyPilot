from uuid import UUID

from app.core.exceptions import AppError, ResourceNotFoundError
from app.domain.models import Attempt, Question
from app.infrastructure.repositories.practice_repository import PracticeRepository
from app.infrastructure.repositories.progress_repository import ProgressRepository
from app.llm.evaluation_gateway import (
    AnswerEvaluationGateway,
    EvaluationOutput,
)
from app.schemas.attempt import (
    AttemptCreate,
    AttemptRead,
    CriterionEvaluation,
    CriterionResult,
    EvaluationFeedback,
)
from app.schemas.practice import QuestionType
from app.schemas.tutor import Citation


class AttemptService:
    def __init__(
        self,
        repository: PracticeRepository,
        progress_repository: ProgressRepository,
        gateway: AnswerEvaluationGateway | None = None,
    ) -> None:
        self.repository = repository
        self.progress_repository = progress_repository
        self.gateway = gateway or AnswerEvaluationGateway()

    async def submit(
        self, user_id: UUID, question_id: UUID, data: AttemptCreate
    ) -> AttemptRead:
        question = await self.repository.get_question(user_id, question_id)
        if question is None:
            raise ResourceNotFoundError("题目")
        answer = data.answer.strip()
        if not answer:
            raise AppError("EMPTY_ANSWER", "答案不能为空", status_code=422)
        if question.question_type == QuestionType.SINGLE_CHOICE.value:
            evaluation, model_name = _evaluate_single_choice(question, answer)
        elif question.question_type == QuestionType.MULTIPLE_CHOICE.value:
            evaluation, model_name = _evaluate_multiple_choice(question, answer)
        else:
            evaluation, model_name = await self.gateway.evaluate(
                question=question.content,
                answer=answer,
                reference_answer=question.reference_answer,
                rubric=question.rubric_json,
                sources=question.source_refs_json,
                include_language_feedback=data.include_language_feedback,
            )
        results, score = _score_evaluation(
            evaluation, question.rubric_json, question.source_refs_json
        )
        attempt = Attempt(
            user_id=user_id,
            question_id=question.id,
            answer=answer,
            score=score,
            criterion_results_json=[item.model_dump(mode="json") for item in results],
            feedback_json=evaluation.feedback.model_dump(mode="json"),
            question_snapshot_json={
                "content": question.content,
                "question_type": question.question_type,
                "difficulty": question.difficulty,
                "options": question.options_json,
                "reference_answer": question.reference_answer,
                "knowledge_points": question.knowledge_points_json,
            },
            rubric_snapshot_json=question.rubric_json,
            source_refs_json=question.source_refs_json,
            evaluation_model=model_name,
        )
        await self.progress_repository.record_attempt(
            attempt,
            course_id=question.course_id,
            topics=question.knowledge_points_json,
            errors=evaluation.feedback.knowledge_errors,
        )
        return _to_read(attempt)

    async def list(
        self, user_id: UUID, question_id: UUID, *, page: int, size: int
    ) -> list[AttemptRead]:
        if await self.repository.get_question(user_id, question_id) is None:
            raise ResourceNotFoundError("题目")
        attempts = await self.repository.list_attempts(
            user_id, question_id, offset=(page - 1) * size, limit=size
        )
        return [_to_read(item) for item in attempts]


def _evaluate_single_choice(question: Question, answer: str) -> tuple[EvaluationOutput, str]:
    normalized = answer.upper()
    options = question.options_json or []
    allowed = {str(item["id"]).upper() for item in options}
    if normalized not in allowed:
        raise AppError("INVALID_OPTION", "答案必须是题目中的选项编号", status_code=422)
    correct = next((item for item in options if item.get("is_correct")), None)
    if correct is None:
        raise AppError("QUESTION_DATA_INVALID", "题目缺少正确答案", status_code=500)
    is_correct = normalized == str(correct["id"]).upper()
    ratio = 1.0 if is_correct else 0.0
    return (
        EvaluationOutput(
            criterion_results=[
                CriterionEvaluation(
                    criterion_index=index,
                    earned_ratio=ratio,
                    reason="选择正确。" if is_correct else f"正确选项是 {correct['id']}。",
                    evidence_ids=item.get("evidence_ids", []),
                )
                for index, item in enumerate(question.rubric_json)
            ],
            feedback=EvaluationFeedback(
                summary="回答正确。" if is_correct else "回答错误，请对照课程资料复习。",
                covered_concepts=question.knowledge_points_json if is_correct else [],
                missing_concepts=[] if is_correct else question.knowledge_points_json,
                knowledge_errors=[] if is_correct else ["选择了不受课程资料支持的选项。"],
                language_feedback=[],
                recommended_topics=[] if is_correct else question.knowledge_points_json,
            ),
        ),
        "deterministic-choice-grader",
    )


def _evaluate_multiple_choice(question: Question, answer: str) -> tuple[EvaluationOutput, str]:
    """Grade a multi-answer question on the options chosen, comma separated.

    Partial credit is the standard negative-marking form: each correct option
    earns a share and each wrong one gives that share back. All-or-nothing would
    score two right out of three the same as picking at random, and rewarding
    the correct picks alone would make selecting everything a perfect answer.
    """

    options = question.options_json or []
    allowed = {str(item["id"]).upper() for item in options}
    chosen = {part.strip().upper() for part in answer.split(",") if part.strip()}
    if not chosen or not chosen <= allowed:
        raise AppError("INVALID_OPTION", "答案必须是题目中的选项编号", status_code=422)
    correct = {str(item["id"]).upper() for item in options if item.get("is_correct")}
    if not correct:
        raise AppError("QUESTION_DATA_INVALID", "题目缺少正确答案", status_code=500)

    hits = chosen & correct
    misses = chosen - correct
    ratio = max(0.0, (len(hits) - len(misses)) / len(correct))
    is_correct = chosen == correct
    expected = "、".join(sorted(correct))
    if is_correct:
        reason = "全部选对。"
    elif not misses:
        reason = f"选对但不完整，完整答案是 {expected}。"
    else:
        reason = f"包含错误选项，正确答案是 {expected}。"
    return (
        EvaluationOutput(
            criterion_results=[
                CriterionEvaluation(
                    criterion_index=index,
                    earned_ratio=ratio,
                    reason=reason,
                    evidence_ids=item.get("evidence_ids", []),
                )
                for index, item in enumerate(question.rubric_json)
            ],
            feedback=EvaluationFeedback(
                summary=reason,
                covered_concepts=question.knowledge_points_json if is_correct else [],
                missing_concepts=[] if is_correct else question.knowledge_points_json,
                knowledge_errors=[] if not misses else ["选择了不受课程资料支持的选项。"],
                language_feedback=[],
                recommended_topics=[] if is_correct else question.knowledge_points_json,
            ),
        ),
        "deterministic-choice-grader",
    )


def _score_evaluation(
    evaluation: EvaluationOutput, rubric: list[dict], sources: list[dict]
) -> tuple[list[CriterionResult], float]:
    if len(evaluation.criterion_results) != len(rubric):
        raise AppError("INVALID_EVALUATION", "批改结果与评分标准不一致", status_code=503)
    allowed_evidence = {item["citation_id"] for item in sources}
    by_index = {item.criterion_index: item for item in evaluation.criterion_results}
    if set(by_index) != set(range(len(rubric))):
        raise AppError("INVALID_EVALUATION", "批改维度索引不完整", status_code=503)
    results: list[CriterionResult] = []
    total = 0.0
    for index, item in enumerate(rubric):
        evaluation_item = by_index[index]
        if not set(evaluation_item.evidence_ids) <= allowed_evidence:
            raise AppError("INVALID_EVALUATION_CITATION", "批改结果包含无效引用", status_code=503)
        weight = float(item["weight"])
        points = round(100 * weight * evaluation_item.earned_ratio, 2)
        total += points
        results.append(
            CriterionResult(
                **evaluation_item.model_dump(),
                criterion=item["criterion"],
                weight=weight,
                points=points,
            )
        )
    return results, round(min(100.0, max(0.0, total)), 2)


def _to_read(attempt: Attempt) -> AttemptRead:
    return AttemptRead(
        id=attempt.id,
        question_id=attempt.question_id,
        answer=attempt.answer,
        score=attempt.score,
        criterion_results=[
            CriterionResult.model_validate(item) for item in attempt.criterion_results_json
        ],
        feedback=EvaluationFeedback.model_validate(attempt.feedback_json),
        reference_answer=attempt.question_snapshot_json["reference_answer"],
        sources=[Citation.model_validate(item) for item in attempt.source_refs_json],
        evaluation_model=attempt.evaluation_model,
        created_at=attempt.created_at,
    )
