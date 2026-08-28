from fastapi.testclient import TestClient

from app.main import app


def test_home_page_serves_studypilot_workspace() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "StudyPilot" in response.text
    assert "AI 学习教练" in response.text
    assert 'window.location.protocol === "file:"' in response.text


def test_static_assets_are_available() -> None:
    client = TestClient(app)

    assert client.get("/static/styles.css").status_code == 200
    javascript = client.get("/static/app.js")
    assert javascript.status_code == 200
    assert 'const API = "/api/v1"' in javascript.text
    assert "followDocument" in javascript.text
    assert "30 * 1024 * 1024" in javascript.text
    assert "addChatPractice" in javascript.text
    assert "result.practice_set" in javascript.text
    assert "renderChatDocumentOptions" in javascript.text
    assert "updateDocumentChoiceState" in javascript.text
    assert "updateScopePageLimits" in javascript.text
    assert "citation-item" in javascript.text
    assert "richText" in javascript.text
    assert "renderMessageMath" in javascript.text
    assert "normalizeMathEscapes" in javascript.text
    assert 'class="math-block"' in javascript.text


def test_upload_control_explains_selection_and_progress() -> None:
    response = TestClient(app).get("/")

    assert 'id="file-picker-title"' in response.text
    assert 'id="upload-status"' in response.text
    assert "最大 30 MB" in response.text
    assert "请先选择文件" in response.text


def test_tutor_workspace_has_retrieval_scope_controls() -> None:
    response = TestClient(app).get("/")

    assert 'id="chat-document-type"' in response.text
    assert 'id="chat-document"' in response.text
    assert 'id="chat-document-choices"' in response.text
    assert 'id="chat-page-from"' in response.text
    assert 'id="chat-page-to"' in response.text
    assert 'id="scope-hint"' in response.text
    assert 'id="chat-question-type"' in response.text
    assert 'id="chat-difficulty"' in response.text
    assert 'id="chat-question-count"' in response.text
    assert "针对已经学的" in response.text
    assert "/static/vendor/katex/katex.min.js?v=0.16.11" in response.text


def test_workspace_exposes_the_full_learning_loop() -> None:
    page = TestClient(app).get("/").text

    # Every stage of the loop needs somewhere to happen in the UI.
    for element in (
        "conversation-select",   # pick up an earlier conversation
        "practice-history",      # past practice sets
        "practice-detail",       # one set, with sources and rubric
        "score-trend",           # how scores moved
        "common-errors",         # what keeps going wrong
        "recent-practice",       # what was practised lately
    ):
        assert f'id="{element}"' in page


def test_destructive_actions_are_present_and_reachable() -> None:
    page = TestClient(app).get("/").text

    for element in ("edit-course", "delete-course", "reset-progress"):
        assert f'id="{element}"' in page


def test_client_script_wires_the_new_panels() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    for symbol in (
        "loadConversations",
        "openConversation",
        "loadPracticeHistory",
        "renderPracticeSet",
        "loadInsights",
        "openCourseDialog",
        "rubricHtml",
        "sourcesHtml",
    ):
        assert f"function {symbol}" in javascript
    assert "/practice-sets?size=" in javascript
    assert "/reprocess" in javascript


def test_irreversible_actions_ask_for_confirmation() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    # Deleting a course, deleting material and clearing progress cannot be undone.
    assert javascript.count("confirm(") >= 3
    assert "无法恢复" in javascript


def test_settings_dialog_covers_the_documented_preferences() -> None:
    page = TestClient(app).get("/").text

    assert 'id="settings-dialog"' in page
    assert 'id="open-settings"' in page
    # PRD 8.6: language, explanation style, and the practice defaults.
    for element in (
        "pref-explanation-language",
        "pref-answer-language",
        "pref-explanation-style",
        "pref-question-type",
        "pref-difficulty",
        "pref-question-count",
        "pref-language-feedback",
    ):
        assert f'id="{element}"' in page


def test_preferences_seed_the_forms_and_reach_the_requests() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    assert "function loadPreferences" in javascript
    assert "function applyPreferenceDefaults" in javascript
    # A saved preference is useless unless it actually travels with the request.
    assert "state.preferences?.explanation_language" in javascript
    assert "state.preferences?.include_language_feedback" in javascript
    # The answer language reaches requests by seeding the practice-language
    # selectors, which the learner can then override for a single set.
    assert 'set("#practice-language", preferences.answer_language)' in javascript
    assert 'set("#chat-practice-language", preferences.answer_language)' in javascript


def test_a_single_weak_topic_can_be_removed() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    assert "data-delete-topic" in javascript
    assert "/topics/${encodeURIComponent(topic)}" in javascript


def test_practice_language_can_be_chosen_in_both_places() -> None:
    page = TestClient(app).get("/").text

    # Taught in Chinese, examined in English is the normal case here.
    assert 'id="practice-language"' in page
    assert 'id="chat-practice-language"' in page


def test_chosen_practice_language_reaches_the_request() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    assert 'language:$("#chat-practice-language").value' in javascript
    assert 'language:$("#practice-language").value' in javascript


def test_a_choice_question_is_answered_by_choosing() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    # The options are the answer; typing the letter as well was redundant.
    assert "function answerFormHtml" in javascript
    assert "function selectedAnswer" in javascript
    assert 'input[type="radio"]:checked' in javascript
    # No separate text box is rendered alongside options.
    assert '（如 A）' not in javascript


def test_a_degraded_answer_is_marked_as_one() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    # A fallback that reads like a normal answer is what misleads; the reason is
    # already in the response, so the UI has no excuse for hiding it.
    assert "function fallbackNoticeHtml" in javascript
    assert "result.fallback_reason" in javascript
    for reason in (
        "model_unconfigured",
        "provider_request_failed",
        "empty_model_response",
        "citation_validation_failed",
        "citation_retry_failed",
    ):
        assert reason in javascript, f"前端缺少 {reason} 的说明"


def test_a_replayed_fallback_is_still_marked() -> None:
    javascript = TestClient(app).get("/static/app.js").text

    # Stored messages keep model_name but not the reason.
    assert 'message.model_name === "retrieval-fallback"' in javascript
