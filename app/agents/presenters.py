"""Presentation and configuration helpers shared by the learning agents.

These were extracted from `TutorService` so that agents can render business
answers without importing the service that now depends on them.
"""

import re

from app.core.exceptions import AppError
from app.domain.models import Document
from app.schemas.practice import Difficulty, PracticeSetCreate, QuestionType
from app.schemas.study_plan import StudyPlanCreate


#: A citation is only useful if it carries the sentence that supports the claim.
#: At 300 characters it usually did not: passages run to a few thousand and the
#: supporting line sits as often in the middle as at the start. This matches the
#: chunker's own ceiling, so a citation carries the whole passage the model saw.
CITATION_SNIPPET_LIMIT = 3200


def _evidence_status(evidence: list) -> str:
    if not evidence:
        return "insufficient"
    if evidence[0].score >= 0.2 or len(evidence) >= 2 and evidence[1].score >= 0.15:
        return "sufficient"
    return "partial"


def _remove_unknown_citations(answer: str, evidence_count: int) -> str:
    def replace(match: re.Match) -> str:
        index = int(match.group(1))
        return match.group(0) if 1 <= index <= evidence_count else ""

    cleaned = re.sub(r"\[c(\d+)]", replace, answer)
    if not cleaned.strip():
        raise AppError("ANSWER_GENERATION_FAILED", "暂时无法生成可靠回答", status_code=503)
    return cleaned


def _followups(status: str) -> list[str]:
    if status == "catalog":
        return ["请概括这些资料的主题。", "这些资料有哪些共同知识点？"]
    if status == "business_data":
        return ["我下一步应该学什么？", "帮我安排一份复习计划。"]
    if status == "practice_created":
        return ["批改后解释我的错误。", "再生成一组更难的题。"]
    if status == "general":
        return ["我现在有哪些课程资料？", "帮我解释一个课程概念。"]
    if status == "insufficient":
        return ["要不要换一个关键词提问？", "是否需要上传更多课程资料？"]
    return ["能否用一个具体例子说明？", "请根据这些内容出一道练习题。"]


def _document_inventory_answer(documents: list[Document], language: str) -> str:
    if not documents:
        if language == "en":
            return "There are no course materials in this course yet."
        return "这门课目前还没有上传课程资料。"

    status_zh = {
        "ready": "已就绪",
        "queued": "等待处理",
        "processing": "正在处理",
        "failed": "处理失败",
        "uploaded": "已上传",
    }
    status_en = {
        "ready": "ready",
        "queued": "queued",
        "processing": "processing",
        "failed": "failed",
        "uploaded": "uploaded",
    }
    if language == "en":
        lines = [f"This course currently has {len(documents)} material(s):"]
        for index, document in enumerate(reversed(documents), start=1):
            details = [status_en.get(document.status, document.status)]
            if document.page_count:
                details.append(f"{document.page_count} pages")
            if document.chunk_count:
                details.append(f"{document.chunk_count} knowledge chunks")
            lines.append(f"{index}. {document.filename} ({', '.join(details)})")
        return "\n".join(lines)

    lines = [f"这门课目前共有 {len(documents)} 份课程资料："]
    for index, document in enumerate(reversed(documents), start=1):
        details = [status_zh.get(document.status, document.status)]
        if document.page_count:
            details.append(f"{document.page_count} 页")
        if document.chunk_count:
            details.append(f"{document.chunk_count} 个知识片段")
        lines.append(f"{index}. {document.filename}（{'、'.join(details)}）")
    return "\n".join(lines)


def _progress_answer(topics: list, total_attempts: int, language: str) -> str:
    if not topics:
        if language == "en":
            return "You have not completed any graded practice yet, so mastery data is unavailable."
        return "你还没有完成已批改的练习，目前还无法计算知识点掌握度。"
    overall = sum(item.mastery_score for item in topics) / len(topics)
    weakest = sorted(topics, key=lambda item: item.mastery_score)[:3]
    if language == "en":
        names = ", ".join(f"{item.display_topic} ({item.mastery_score:.0%})" for item in weakest)
        return f"Overall mastery: {overall:.0%} from {total_attempts} attempts. Focus next on: {names}."
    names = "、".join(f"{item.display_topic}（{item.mastery_score:.0%}）" for item in weakest)
    return f"你目前的总体掌握度约为 {overall:.0%}，已完成 {total_attempts} 次作答。建议优先加强：{names}。"


def _study_plan_answer(plans: list, language: str) -> str:
    if not plans:
        if language == "en":
            return "There is no study plan for this course yet. Create one in the Study Plan tab."
        return "这门课还没有学习计划。你可以在“学习计划”中设置天数和每日时间后生成。"
    plan = plans[0]
    completed = sum(task.status == "completed" for task in plan.tasks)
    total = len(plan.tasks)
    completion_rate = completed / max(1, total)
    pending = next((task for task in plan.tasks if task.status != "completed"), None)
    if language == "en":
        next_text = f" Next: {pending.title}." if pending else " All tasks are complete."
        return f"Your latest plan is {completed}/{total} tasks complete ({completion_rate:.0%}).{next_text}"
    next_text = f"下一项：{pending.title}。" if pending else "所有任务都已完成。"
    return f"你最新的学习计划已完成 {completed}/{total} 项（{completion_rate:.0%}）。{next_text}"


def _practice_created_answer(practice_set, language: str) -> str:
    count = len(practice_set.questions)
    if language == "en":
        return f'I created and saved "{practice_set.title}" with {count} question(s). Answer them below for grading.'
    return f"已为你生成并保存“{practice_set.title}”，共 {count} 道题。请直接在下方作答，提交后会自动批改。"


def _general_answer(language: str) -> str:
    if language == "en":
        return "I am your StudyPilot coach. I can explain uploaded materials with citations, review progress, show study plans, and help you create targeted practice."
    return "我是你的 StudyPilot 学习教练。我可以基于课程资料带引用讲解知识、查看学习进度和计划，也可以帮你进行针对性练习。"


def _practice_configuration(
    message: str, language, scope, *, options=None, context_topic: str | None = None
) -> PracticeSetCreate:
    # Questions are what the learner will be examined in, which is not always the
    # language they are being taught in. An explicit choice wins over the
    # conversation's explanation language.
    practice_language = getattr(options, "language", None) or language
    normalized = " ".join(message.casefold().split())
    number_match = re.search(r"(10|[1-9])\s*(?:道|题|questions?)", normalized)
    chinese_numbers = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    chinese_match = re.search(r"([一两二三四五六七八九十])\s*道", normalized)
    default_count = options.question_count if options else 3
    count = int(number_match.group(1)) if number_match else (
        chinese_numbers[chinese_match.group(1)] if chinese_match else default_count
    )
    if any(term in normalized for term in ("选择题", "单选", "multiple choice")):
        question_type = QuestionType.SINGLE_CHOICE
    elif any(term in normalized for term in ("概念题", "概念解释", "concept question")):
        question_type = QuestionType.CONCEPT
    elif any(term in normalized for term in ("简答题", "问答题", "short answer")):
        question_type = QuestionType.SHORT_ANSWER
    else:
        question_type = QuestionType(options.question_type) if options else QuestionType.SHORT_ANSWER
    if any(term in normalized for term in ("基础", "简单", "basic", "easy")):
        difficulty = Difficulty.BASIC
    elif any(term in normalized for term in ("困难", "挑战", "高级", "advanced", "hard")):
        difficulty = Difficulty.ADVANCED
    else:
        difficulty = Difficulty(options.difficulty) if options else Difficulty.MEDIUM
    topic_match = re.search(r"(?:关于|针对|topic[:：]?)\s*([^,，。.!?？]{2,80})", message, re.I)
    topic = context_topic or _clean_topic(topic_match.group(1) if topic_match else None)
    return PracticeSetCreate(
        topic=topic,
        question_type=question_type,
        difficulty=difficulty,
        question_count=count,
        language=practice_language,
        prioritize_weak_topics=any(term in normalized for term in ("薄弱", "弱项", "weak")),
        scope=scope,
    )



#: Trailing question-form wording the topic pattern otherwise swallows, so that
#: "关于残差的简答题" asks about residuals rather than about short-answer questions.
_TOPIC_TRAILER = re.compile(
    r"(?:的)?\s*(?:\d+|[一两二三四五六七八九十])?\s*(?:道|个)?\s*"
    r"(?:单选题|选择题|多选题|简答题|问答题|概念解释题|概念题|练习题|练习|测验|题目|题)\s*$"
)
_TOPIC_TRAILER_EN = re.compile(
    r"[\s,]*(?:\d+\s*)?(?:multiple[- ]choice|short[- ]answer|concept)?\s*"
    r"(?:questions?|quiz|exercises?|practice)\s*$",
    re.I,
)


def _clean_topic(topic: str | None) -> str | None:
    """Keep the subject, drop the request wording wrapped around it."""

    if not topic:
        return None
    cleaned = topic.strip()
    for _ in range(3):
        stripped = _TOPIC_TRAILER.sub("", cleaned).strip()
        stripped = _TOPIC_TRAILER_EN.sub("", stripped).strip()
        if stripped == cleaned:
            break
        cleaned = stripped
    return cleaned or None


def _requests_new_plan(message: str) -> bool:
    """Distinguish "make me a plan" from "show me my plan"."""

    normalized = " ".join(message.casefold().split())
    creation = ("制定", "制订", "生成", "安排一份", "帮我排", "做一份", "新建",
                "create", "make me", "build me", "generate")
    if not any(term in normalized for term in creation):
        return False
    reading = ("查看", "看一下我的", "我的计划完成", "show me my", "what does my")
    return not any(term in normalized for term in reading)


def _study_plan_configuration(message: str) -> StudyPlanCreate:
    normalized = " ".join(message.casefold().split())
    days_match = re.search(r"(\d{1,2})\s*(?:天|days?)", normalized)
    minutes_match = re.search(r"(\d{2,3})\s*(?:分钟|minutes?|mins?)", normalized)
    hours_match = re.search(r"(\d)\s*(?:小时|hours?)", normalized)
    daily_minutes = 60
    if minutes_match:
        daily_minutes = int(minutes_match.group(1))
    elif hours_match:
        daily_minutes = int(hours_match.group(1)) * 60
    return StudyPlanCreate(
        duration_days=min(max(int(days_match.group(1)), 1), 28) if days_match else 7,
        daily_minutes=min(max(daily_minutes, 15), 480),
        include_weekends="不含周末" not in normalized and "no weekend" not in normalized,
    )


def _study_plan_created_answer(plan, weak_topics: list, language: str) -> str:
    focus = "、".join(str(item).strip().rstrip("。.") for item in weak_topics[:3])
    if language == "en":
        text = (
            f'I created "{plan.title}" covering {plan.start_date} to {plan.end_date}, '
            f"with {len(plan.tasks)} task(s) at {plan.daily_minutes} minutes per day."
        )
        return f"{text} It focuses on: {focus}." if focus else text
    text = (
        f"已为你生成“{plan.title}”，覆盖 {plan.start_date} 至 {plan.end_date}，"
        f"共 {len(plan.tasks)} 项任务，每天 {plan.daily_minutes} 分钟。"
    )
    return f"{text}重点针对：{focus.rstrip('。.')}。" if focus else text


def _no_pending_question_answer(language: str) -> str:
    if language == "en":
        return "You have no unanswered practice question right now. Ask me to generate one first."
    return "你目前没有待作答的练习题。可以先让我生成一组练习，再把答案发给我批改。"


def _extract_submitted_answer(message: str, question) -> str:
    """Strip the submission phrasing so only the answer itself is graded."""

    cleaned = re.sub(
        r"^\s*(?:答案|answer)\s*[：:]\s*", "", message.strip(), flags=re.I
    )
    cleaned = re.sub(
        r"(?:我的答案|我的回答|我答|我选)\s*(?:是|为)?\s*[：:]?\s*", "", cleaned
    )
    cleaned = re.sub(
        r"^(?:帮我批改|帮我改一下|评一下我的答案|给我打分|grade my answer|check my answer)\s*[，,：:]?\s*",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = cleaned.strip(" ，,。.！!")
    if question.question_type == QuestionType.SINGLE_CHOICE.value:
        option = re.search(r"\b([A-D])\b", cleaned.upper())
        if option:
            return option.group(1)
    return cleaned or message.strip()


def _attempt_feedback_answer(question, attempt, language: str) -> str:
    feedback = attempt.feedback
    lines: list[str] = []
    if language == "en":
        lines.append(f"**Score: {attempt.score} / {attempt.max_score}**")
        lines.append(f"> Question: {question.content[:160]}")
        if feedback.summary:
            lines.append(f"\n{feedback.summary}")
        if feedback.knowledge_errors:
            lines.append("\n**What went wrong**")
            lines += [f"- {item}" for item in feedback.knowledge_errors]
        if feedback.missing_concepts:
            lines.append("\n**Concepts you did not cover**")
            lines += [f"- {item}" for item in feedback.missing_concepts]
        if feedback.recommended_topics:
            lines.append("\n**Review next**")
            lines += [f"- {item}" for item in feedback.recommended_topics]
    else:
        lines.append(f"**得分：{attempt.score} / {attempt.max_score}**")
        lines.append(f"> 题目：{question.content[:160]}")
        if feedback.summary:
            lines.append(f"\n{feedback.summary}")
        if feedback.knowledge_errors:
            lines.append("\n**存在的问题**")
            lines += [f"- {item}" for item in feedback.knowledge_errors]
        if feedback.missing_concepts:
            lines.append("\n**未覆盖的要点**")
            lines += [f"- {item}" for item in feedback.missing_concepts]
        if feedback.recommended_topics:
            lines.append("\n**建议复习**")
            lines += [f"- {item}" for item in feedback.recommended_topics]
    return "\n".join(lines)


def _answer_format_mismatch_answer(question, language: str) -> str:
    options = "、".join(
        str(item.get("id")) for item in (question.options_json or []) if item.get("id")
    )
    if language == "en":
        return (
            "The question waiting for you is multiple choice, so please reply with one "
            f"option ({options}).\n\n> {question.content[:160]}"
        )
    return (
        f"当前待作答的是选择题，请直接回复选项编号（{options}）。"
        f"\n\n> {question.content[:160]}"
    )


def _with_integrity_notice(answer: str, integrity) -> str:
    """PRD 8.7: the notice must be brief and must not replace the help itself."""

    notice = getattr(integrity, "notice", "")
    return f"> {notice}\n\n{answer}" if notice else answer
