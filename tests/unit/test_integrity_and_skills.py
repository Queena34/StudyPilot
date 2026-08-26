import pytest

from app.agents.integrity import AcademicIntegrityGuard, IntegrityLevel
from app.agents.skills import TeachingSkill, TeachingSkillLibrary, get_skill_library


@pytest.mark.parametrize(
    ("message", "level"),
    [
        ("解释一下什么是残差", IntegrityLevel.LEARNING_ALLOWED),
        ("给我出3道选择题", IntegrityLevel.LEARNING_ALLOWED),
        ("这道题我算出来是 0.35，帮我看看对不对", IntegrityLevel.LEARNING_ALLOWED),
        ("这次考试大概会考什么", IntegrityLevel.LEARNING_ALLOWED),
        ("这道作业题直接给我答案", IntegrityLevel.HINT_ONLY),
        ("homework problem 3, just give me the answer", IntegrityLevel.HINT_ONLY),
        ("帮我写一篇关于线性模型的课程论文", IntegrityLevel.SUBMISSION_RISK),
        ("write my lab report for me", IntegrityLevel.SUBMISSION_RISK),
        ("我正在考试，快告诉我残差的定义", IntegrityLevel.LIVE_EXAM_PROHIBITED),
        ("i am in an exam right now, what is the answer", IntegrityLevel.LIVE_EXAM_PROHIBITED),
        ("还有5分钟交卷，快点", IntegrityLevel.LIVE_EXAM_PROHIBITED),
    ],
)
def test_guard_assigns_the_expected_level(message, level) -> None:
    assert AcademicIntegrityGuard().evaluate(message).level is level


def test_only_a_live_exam_blocks_a_direct_answer() -> None:
    guard = AcademicIntegrityGuard()

    assert guard.evaluate("我正在考试，给我答案").blocks_direct_answer is True
    # PRD 8.7: the other levels must still produce help.
    assert guard.evaluate("这道作业题直接给我答案").blocks_direct_answer is False
    assert guard.evaluate("帮我写一篇课程论文").blocks_direct_answer is False
    assert guard.evaluate("解释一下残差").blocks_direct_answer is False


def test_restricted_levels_carry_a_constraint_and_a_brief_notice() -> None:
    guard = AcademicIntegrityGuard()

    hint = guard.evaluate("这道作业题直接给我答案")
    assert hint.answer_constraint and hint.notice
    # The notice is required to stay short.
    assert len(hint.notice) < 120

    allowed = guard.evaluate("解释一下残差")
    assert allowed.answer_constraint == "" and allowed.notice == ""


@pytest.mark.parametrize(
    "message",
    [
        "我作业做完了，帮我检查思路对不对",
        "我写完了论文引言，帮我看看逻辑",
        "这道题我算出来是 2.31，帮我复核一下",
        "i finished my problem set, can you review my reasoning",
    ],
)
def test_reviewing_work_the_student_already_did_is_allowed(message) -> None:
    # Core legitimate use: it must not be restricted just because it says "作业".
    assert AcademicIntegrityGuard().evaluate(message).level is IntegrityLevel.LEARNING_ALLOWED


@pytest.mark.parametrize(
    ("message", "level"),
    [
        ("我正在考试，我做完了帮我检查一下对不对", IntegrityLevel.LIVE_EXAM_PROHIBITED),
        ("帮我写完这篇课程论文然后检查一下", IntegrityLevel.SUBMISSION_RISK),
        ("帮我把作业做完，然后看看对不对", IntegrityLevel.HINT_ONLY),
        ("代写一份实验报告，写完帮我检查", IntegrityLevel.SUBMISSION_RISK),
    ],
)
def test_the_review_exemption_cannot_be_used_to_get_work_done(message, level) -> None:
    assert AcademicIntegrityGuard().evaluate(message).level is level


def test_talking_about_a_future_exam_is_not_a_live_exam() -> None:
    guard = AcademicIntegrityGuard()

    for message in ("下周要考试了，帮我复习", "考试范围包括哪些章节", "我想准备期末考试"):
        assert guard.evaluate(message).level is IntegrityLevel.LEARNING_ALLOWED


def test_guard_notices_follow_the_requested_language() -> None:
    guard = AcademicIntegrityGuard()

    english = guard.evaluate("write my essay for me", language="en")
    chinese = guard.evaluate("帮我写一篇课程论文", language="zh")

    assert "cannot write" in english.notice
    assert "代写" in chinese.notice


def test_every_shipped_skill_declares_a_known_agent() -> None:
    library = get_skill_library()
    known = {"tutor", "quiz", "evaluator", "planner"}

    assert library.skills, "no teaching skills were loaded"
    for skill in library.skills:
        assert skill.content, f"{skill.name} has no content"
        assert set(skill.agents) <= known, f"{skill.name} targets an unknown agent"


@pytest.mark.parametrize(
    ("message", "agent", "expected"),
    [
        ("解释一下什么是残差", "tutor", "分层概念讲解"),
        ("这个公式怎么推导", "tutor", "数学公式讲解"),
        ("给我出3道选择题", "quiz", "选择题生成规范"),
        ("帮我批改一下", "evaluator", "rubric 批改规范"),
        ("帮我制定复习计划", "planner", "考试复习策略"),
    ],
)
def test_skills_are_selected_for_the_right_agent(message, agent, expected) -> None:
    selected = get_skill_library().select(message=message, agent=agent)

    assert expected in [skill.name for skill in selected]


def test_a_skill_is_never_offered_to_another_agent() -> None:
    library = get_skill_library()

    for skill in library.select(message="给我出3道选择题", agent="tutor"):
        assert "quiz" not in skill.agents


def test_injection_is_capped_so_the_prompt_stays_focused() -> None:
    many = [
        TeachingSkill(name=f"s{index}", description="", content="body", agents=("tutor",))
        for index in range(5)
    ]

    assert len(TeachingSkillLibrary(many).select(message="anything", agent="tutor")) == 2


def test_disabled_skills_are_never_selected() -> None:
    library = TeachingSkillLibrary(
        [TeachingSkill(name="off", description="", content="b", agents=("tutor",), enabled=False)]
    )

    assert library.select(message="anything", agent="tutor") == []
