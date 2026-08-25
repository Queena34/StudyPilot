from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import UploadFile

from app.core.exceptions import AppError
from app.infrastructure.file_storage import LocalFileStorage


@pytest.mark.asyncio
async def test_save_utf8_text_and_delete(tmp_path) -> None:
    storage = LocalFileStorage(str(tmp_path))
    upload = UploadFile(filename="notes.txt", file=BytesIO("课程笔记".encode()))
    stored = await storage.save_upload(
        upload,
        user_id=uuid4(),
        course_id=uuid4(),
        document_id=uuid4(),
        suffix=".txt",
        max_bytes=1024,
    )
    assert stored.size_bytes > 0
    assert len(stored.checksum_sha256) == 64
    assert (tmp_path / stored.storage_key).exists()
    storage.delete(stored.storage_key)
    assert not (tmp_path / stored.storage_key).exists()


@pytest.mark.asyncio
async def test_rejects_fake_pdf_and_cleans_up(tmp_path) -> None:
    storage = LocalFileStorage(str(tmp_path))
    upload = UploadFile(filename="fake.pdf", file=BytesIO(b"not a pdf"))
    with pytest.raises(AppError) as error:
        await storage.save_upload(
            upload,
            user_id=uuid4(),
            course_id=uuid4(),
            document_id=uuid4(),
            suffix=".pdf",
            max_bytes=1024,
        )
    assert error.value.code == "INVALID_FILE_CONTENT"
    assert list(tmp_path.rglob("*")) == []


@pytest.mark.asyncio
async def test_rejects_oversized_file(tmp_path) -> None:
    storage = LocalFileStorage(str(tmp_path))
    upload = UploadFile(filename="large.txt", file=BytesIO(b"12345"))
    with pytest.raises(AppError) as error:
        await storage.save_upload(
            upload,
            user_id=uuid4(),
            course_id=uuid4(),
            document_id=uuid4(),
            suffix=".txt",
            max_bytes=4,
        )
    assert error.value.code == "FILE_TOO_LARGE"
