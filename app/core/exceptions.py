from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class ResourceNotFoundError(AppError):
    def __init__(self, resource: str) -> None:
        super().__init__(
            "RESOURCE_NOT_FOUND",
            f"{resource}不存在或无权访问",
            status_code=404,
        )


class ConflictError(AppError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=409)

