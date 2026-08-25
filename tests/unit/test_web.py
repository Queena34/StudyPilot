from fastapi.testclient import TestClient

from app.main import app


def test_home_page_serves_studypilot_workspace() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert "StudyPilot" in response.text
    assert "AI 学习教练" in response.text


def test_static_assets_are_available() -> None:
    client = TestClient(app)

    assert client.get("/static/styles.css").status_code == 200
    javascript = client.get("/static/app.js")
    assert javascript.status_code == 200
    assert 'const API = "/api/v1"' in javascript.text
    assert "followDocument" in javascript.text
    assert "30 * 1024 * 1024" in javascript.text


def test_upload_control_explains_selection_and_progress() -> None:
    response = TestClient(app).get("/")

    assert 'id="file-picker-title"' in response.text
    assert 'id="upload-status"' in response.text
    assert "最大 30 MB" in response.text
    assert "请先选择文件" in response.text
