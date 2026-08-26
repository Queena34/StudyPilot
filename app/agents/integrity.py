"""Academic integrity guard (PRD 8.7, roadmap section on teaching skills).

Runs before the tutor and quiz agents. It never blocks learning: three of the
four levels still produce a full answer, and only a live exam is refused. The
point is to decide *what kind* of help is appropriate, not whether to help.

Detection is deterministic on purpose. A rule that decides whether a student gets
help must be inspectable and testable, and must not vary run to run.
"""

from dataclasses import dataclass
from enum import Enum
import re


class IntegrityLevel(str, Enum):
    #: Ordinary studying: explain, summarise, generate practice, give hints.
    LEARNING_ALLOWED = "learning_allowed"
    #: Looks like graded work: teach the method, do not hand over the artifact.
    HINT_ONLY = "hint_only"
    #: Asks for something submittable as-is: give structure and a checklist.
    SUBMISSION_RISK = "submission_risk"
    #: Claims to be sitting an exam right now: no direct answers.
    LIVE_EXAM_PROHIBITED = "live_exam_prohibited"


@dataclass(frozen=True)
class IntegrityDecision:
    level: IntegrityLevel
    reason: str
    #: Extra instruction handed to the model; empty when nothing is restricted.
    answer_constraint: str = ""
    #: Short note shown to the learner. PRD 8.7 requires it stay brief.
    notice: str = ""

    @property
    def blocks_direct_answer(self) -> bool:
        return self.level is IntegrityLevel.LIVE_EXAM_PROHIBITED

    def as_dict(self) -> dict:
        return {
            "level": self.level.value,
            "reason": self.reason,
            "blocks_direct_answer": self.blocks_direct_answer,
        }


class AcademicIntegrityGuard:
    """Classifies one learner message into an integrity level."""

    def evaluate(
        self, message: str, *, language: str = "zh", history: list | None = None
    ) -> IntegrityDecision:
        normalized = " ".join(message.casefold().split())

        if _is_live_exam(normalized):
            return IntegrityDecision(
                IntegrityLevel.LIVE_EXAM_PROHIBITED,
                "The learner says they are sitting an exam or timed test right now.",
                notice=_LIVE_EXAM_NOTICE[language == "en"],
            )
        if _is_own_work_review(normalized):
            # Reviewing work the student has already done is core legitimate use,
            # and must not be restricted just because it mentions an assignment.
            return IntegrityDecision(
                IntegrityLevel.LEARNING_ALLOWED,
                "The learner finished the work themselves and asked for a review.",
            )
        if _is_submission_request(normalized):
            return IntegrityDecision(
                IntegrityLevel.SUBMISSION_RISK,
                "The learner asked for a finished piece of work that could be handed in.",
                answer_constraint=_SUBMISSION_CONSTRAINT,
                notice=_SUBMISSION_NOTICE[language == "en"],
            )
        if _is_graded_work_request(normalized):
            return IntegrityDecision(
                IntegrityLevel.HINT_ONLY,
                "The learner asked for the answer to what looks like assigned work.",
                answer_constraint=_HINT_CONSTRAINT,
                notice=_HINT_NOTICE[language == "en"],
            )
        return IntegrityDecision(
            IntegrityLevel.LEARNING_ALLOWED,
            "Ordinary studying: explanation, summary or practice.",
        )


def _is_live_exam(message: str) -> bool:
    """Only a claim of being in an exam *now*, not talk about exams in general."""

    present = (
        "正在考试", "在考试中", "考试进行中", "正在测验", "正在小测",
        "现在在考", "考场里", "监考", "正在答题卡",
        "i am in an exam", "i'm in an exam", "during my exam", "taking my exam right now",
        "the exam is happening", "proctored",
    )
    if any(term in message for term in present):
        return True
    # "还有 5 分钟交卷" style urgency paired with an answer demand.
    urgency = re.search(r"(?:还有|剩)\s*\d+\s*(?:分钟|秒).{0,10}(?:交卷|结束|考完)", message)
    return bool(urgency)


def _is_own_work_review(message: str) -> bool:
    """The student did the work and wants it checked, not done for them."""

    completed = (
        "做完了", "写完了", "答完了", "做好了", "算出来", "我的思路", "我的答案",
        "我的草稿", "我写了", "我算了", "我做了",
        "i finished", "i've finished", "i have finished", "i wrote", "my draft",
        "my reasoning", "my attempt", "my answer",
    )
    review = (
        "检查", "看看", "对不对", "复核", "有没有问题", "哪里错", "点评", "反馈",
        "check", "review", "feedback", "look over", "is this right",
    )
    return any(term in message for term in completed) and any(
        term in message for term in review
    )


def _is_submission_request(message: str) -> bool:
    """Asks for a deliverable that could be submitted without further work."""

    artifacts = (
        "论文", "报告", "作文", "读书笔记", "实验报告", "课程设计", "结课作业",
        "essay", "term paper", "lab report", "book review", "assignment writeup",
    )
    produce = (
        "帮我写", "帮我做", "替我写", "代写", "写一篇", "写一份", "生成一篇",
        "write me", "write my", "draft my", "do my", "produce a full",
    )
    if any(term in message for term in produce) and any(
        term in message for term in artifacts
    ):
        return True
    return any(term in message for term in ("代写", "帮我代做", "ghostwrite"))


def _is_graded_work_request(message: str) -> bool:
    """Asks for the answer to homework rather than for how to get there."""

    graded = ("作业", "习题册", "homework", "problem set", "pset", "graded")
    hand_over = (
        "答案", "直接给我", "帮我做", "帮我算", "做完", "解出来",
        "give me the answer", "just the answer", "solve it for me", "do it for me",
    )
    if any(term in message for term in graded) and any(
        term in message for term in hand_over
    ):
        return True
    # "直接给我答案" on its own is a hand-over request whatever the context.
    return bool(re.search(r"(?:直接|快点|马上)\s*(?:给我|告诉我)\s*(?:答案|结果)", message))


_HINT_CONSTRAINT = (
    "The student appears to be asking for the answer to assigned work. Teach the method "
    "instead of handing over the result: explain the relevant concept from the sources, "
    "give a worked example that is not the student's own task, and lay out the steps they "
    "should follow. Do not state the final answer to their specific problem."
)

_SUBMISSION_CONSTRAINT = (
    "The student is asking for a finished piece of work that could be submitted as their own. "
    "Do not write it. Provide an outline, the argument structure to consider, a checklist of "
    "what a strong version must contain, and the relevant course concepts with citations. "
    "Invite them to draft it themselves and offer to review their draft."
)

_HINT_NOTICE = {
    False: "这看起来是作业题，所以我讲方法和思路，不直接给出答案。",
    True: "This looks like assigned work, so I will teach the method rather than give the answer.",
}

_SUBMISSION_NOTICE = {
    False: "我不能代写可直接提交的作业，但可以帮你搭结构、列检查清单，并在你写完后帮你复核。",
    True: (
        "I cannot write work you would submit as your own, but I can help you structure it, "
        "give you a checklist, and review your draft."
    ),
}

_LIVE_EXAM_NOTICE = {
    False: (
        "如果你正在考试中，我不能提供答案。考试结束后我很乐意帮你把这部分内容彻底讲清楚，"
        "也可以带你复盘错题。"
    ),
    True: (
        "If you are currently sitting an exam, I cannot provide answers. Once it is over I am "
        "glad to work through this material with you properly."
    ),
}
