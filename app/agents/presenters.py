"""Presentation and configuration helpers shared by the learning agents.

These were extracted from `TutorService` so that agents can render business
answers without importing the service that now depends on them.
"""

import re

from app.core.exceptions import AppError
from app.domain.models import Document
from app.schemas.practice import Difficulty, PracticeSetCreate, QuestionType


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
    topic = context_topic or (topic_match.group(1).strip() if topic_match else None)
    return PracticeSetCreate(
        topic=topic,
        question_type=question_type,
        difficulty=difficulty,
        question_count=count,
        language=language,
        prioritize_weak_topics=any(term in normalized for term in ("薄弱", "弱项", "weak")),
        scope=scope,
    )


