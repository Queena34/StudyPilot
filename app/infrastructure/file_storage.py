import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile

from app.core.exceptions import AppError

CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class StoredUpload:
    storage_key: str
    checksum_sha256: str
    size_bytes: int


class LocalFileStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_path(self, storage_key: str) -> Path:
        path = (self.root / storage_key).resolve()
        if not path.is_relative_to(self.root):
            raise AppError("INVALID_STORAGE_KEY", "文件存储路径不合法", status_code=400)
        return path

    def resolve(self, storage_key: str) -> Path:
        """Resolve a persisted key without allowing access outside the upload root."""
        return self._safe_path(storage_key)

    async def save_upload(
        self,
        upload: UploadFile,
        *,
        user_id: UUID,
        course_id: UUID,
        document_id: UUID,
        suffix: str,
        max_bytes: int,
    ) -> StoredUpload:
        storage_key = f"{user_id}/{course_id}/{document_id}/original{suffix}"
        destination = self._safe_path(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=False)
        digest = hashlib.sha256()
        size = 0
        sample = b""

        try:
            with destination.open("xb") as target:
                while chunk := await upload.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > max_bytes:
                        raise AppError(
                            "FILE_TOO_LARGE",
                            f"文件大小不能超过{max_bytes // (1024 * 1024)}MB",
                            status_code=413,
                        )
                    if len(sample) < 4096:
                        sample += chunk[: 4096 - len(sample)]
                    digest.update(chunk)
                    target.write(chunk)
            if size == 0:
                raise AppError("EMPTY_FILE", "不能上传空文件", status_code=400)
            self._validate_signature(suffix, sample)
        except Exception:
            self._remove_document_tree(destination)
            raise
        finally:
            await upload.close()

        return StoredUpload(storage_key, digest.hexdigest(), size)

    @staticmethod
    def _validate_signature(suffix: str, sample: bytes) -> None:
        if suffix == ".pdf" and not sample.startswith(b"%PDF-"):
            raise AppError("INVALID_FILE_CONTENT", "文件内容不是有效的PDF", status_code=415)
        if suffix in {".md", ".txt"}:
            if b"\x00" in sample:
                raise AppError("INVALID_FILE_CONTENT", "文本文件包含不支持的二进制内容", status_code=415)
            try:
                sample.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise AppError(
                    "UNSUPPORTED_TEXT_ENCODING", "文本文件必须使用UTF-8编码", status_code=415
                ) from exc

    def delete(self, storage_key: str) -> None:
        path = self._safe_path(storage_key)
        if path.exists():
            path.unlink()
        self._remove_document_tree(path)

    def _remove_document_tree(self, path: Path) -> None:
        document_dir = path.parent
        if document_dir.is_relative_to(self.root):
            shutil.rmtree(document_dir, ignore_errors=True)
        for parent in document_dir.parents:
            if parent == self.root:
                break
            try:
                parent.rmdir()
            except OSError:
                break
