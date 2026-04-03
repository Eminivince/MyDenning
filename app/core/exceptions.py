from fastapi import Request, status
from fastapi.responses import JSONResponse

import structlog

logger = structlog.get_logger(__name__)


class AppException(Exception):
    def __init__(self, status_code: int, detail: str, error_code: str | None = None):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code


class DocumentNotFoundError(AppException):
    def __init__(self, document_id: str):
        super().__init__(status.HTTP_404_NOT_FOUND, f"Document {document_id} not found", "DOCUMENT_NOT_FOUND")


class DocumentNotProcessedError(AppException):
    def __init__(self, document_id: str):
        super().__init__(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Document {document_id} not yet processed", "DOCUMENT_NOT_PROCESSED")


class PlaybookNotFoundError(AppException):
    def __init__(self, playbook_id: str):
        super().__init__(status.HTTP_404_NOT_FOUND, f"Playbook {playbook_id} not found", "PLAYBOOK_NOT_FOUND")


class InsufficientPermissionsError(AppException):
    def __init__(self):
        super().__init__(status.HTTP_403_FORBIDDEN, "Insufficient permissions", "FORBIDDEN")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )
